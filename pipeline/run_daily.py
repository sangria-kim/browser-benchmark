"""One serialized daily candidate. State, logs and validation exports stay private.

Run ``python -m pipeline.run_daily --help``. No Git delivery or scheduler changes.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

STAGES = ('collect', 'select', 'report', 'validate')
# Only these outputs may replace public files. All other inputs are read-only.
OUTPUTS = ('data/', 'reports/generated/')
INPUTS = ('config', 'data', 'features', 'experiments', 'releases', 'rules',
          'schemas', 'pipeline', 'scripts', 'templates', 'reports', 'docs', 'dashboard', 'AGENTS.md')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def sync_dir(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        sync_dir(path.parent)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read(path):
    return json.loads(Path(path).read_text())


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE).decode().strip()


def inventory(root):
    """Include untracked candidate inputs for shadow runs; reject links/special files."""
    result = {}
    for name in INPUTS:
        base = root / name
        if base.is_symlink():
            raise ValueError('Linked input directory: ' + name)
        if not base.exists():
            continue
        for path in ([base] if base.is_file() else sorted(base.rglob('*'))):
            if '__pycache__' in path.parts or path.name == '.DS_Store':
                continue
            if path.is_symlink():
                raise ValueError('Linked input: ' + str(path))
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError('Nonregular input: ' + str(path))
            result[str(path.relative_to(root))] = digest(path.read_bytes())
    return result


def private_input_inventory(directory):
    """Hash the complete regular-file set; never follow private input links."""
    if directory.is_symlink():
        raise ValueError('Linked private input directory')
    if not directory.exists():
        return {}
    if not directory.is_dir():
        raise ValueError('Non-directory private inputs')
    result = {}
    for path in sorted(directory.iterdir()):
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ValueError('Nonregular or linked private input: ' + path.name)
        fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError('Nonregular private input: ' + path.name)
            result[path.name] = digest(stream.read())
    return result


def verify_private_inputs(run_dir, state):
    if private_input_inventory(run_dir / 'inputs') != state.get('private_inputs', {}):
        raise ValueError('Pinned private input inventory changed')


def require_external(root, private):
    if root == private or root in private.parents or private in root.parents:
        raise ValueError('Private state must be outside and separate from the repository')


@contextmanager
def run_lock(repository):
    # A stable per-user, per-repository location prevents alternate state dirs
    # from bypassing serialization. flock is released by the OS on process exit.
    folder = Path('/tmp').resolve() / ('browser-benchmark-locks-' + str(os.getuid()))
    folder.mkdir(mode=0o700, exist_ok=True)
    if folder.is_symlink() or folder.stat().st_uid != os.getuid() or folder.stat().st_mode & 0o077:
        raise ValueError('Unsafe global lock directory')
    path = folder / (digest(str(repository.resolve()).encode()) + '.lock')
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError('Another daily run holds the repository lock') from error
        yield stream


def commit_candidate(root):
    if not (root / '.git').exists():
        git(root, 'init', '-q')
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Validation candidate', '-c', 'user.email=validation@example.invalid',
        '-c', 'core.hooksPath=/dev/null', 'commit', '--allow-empty', '-qm', 'Private validation only')
    return git(root, 'rev-parse', 'HEAD')


def copy_snapshot(source, target):
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns('.git', 'dist', '__pycache__'))


def recover_publication(root, run_dir):
    journal_path = run_dir / 'publication.json'
    if not journal_path.exists():
        return False
    journal = read(journal_path)
    if journal['status'] != 'writing':
        return False
    state = read(run_dir / 'state.json')
    if state['repository'] != str(root):
        raise ValueError('Recovery journal belongs to another repository')
    expected = state['stages']['validate']['outputs']
    changed = {p for p in set(state['inputs']) | set(expected) if state['inputs'].get(p) != expected.get(p)}
    if set(journal['files']) != changed:
        raise ValueError('Recovery journal inventory mismatch')
    for rel, row in journal['files'].items():
        if (not rel.startswith(OUTPUTS) or Path(rel).is_absolute() or '..' in Path(rel).parts
                or row != {'before': state['inputs'].get(rel), 'after': expected.get(rel)}
                or row['after'] is None):
            raise ValueError('Unsafe recovery journal entry')
        backup = run_dir / 'backup' / rel
        if row['before'] is not None and (backup.is_symlink() or digest(backup.read_bytes()) != row['before']):
            raise ValueError('Recovery backup checksum mismatch')
    # Validate every path before rolling back any. Preserve third-party edits.
    for rel, row in journal['files'].items():
        path = root / rel
        if path.is_symlink() or root not in path.resolve().parents:
            raise RuntimeError('Unsafe recovery target: ' + rel)
        current = digest(path.read_bytes()) if path.exists() else None
        if current not in (row['before'], row['after']):
            raise RuntimeError('Recovery conflict; preserve journal and reconcile: ' + rel)
    for rel, row in journal['files'].items():
        path = root / rel
        if row['before'] is None:
            if path.exists():
                path.unlink()
                sync_dir(path.parent)
        else:
            durable(path, (run_dir / 'backup' / rel).read_bytes())
    journal['status'] = 'rolled_back'
    durable(journal_path, encoded(journal))
    return True


def publish_candidate(root, run_dir, state, *, allow_partial=False, replace=durable):
    if state['status'] != 'complete' and not (allow_partial and state['status'] == 'partial'):
        raise ValueError('Incomplete candidates cannot publish; keep the last accepted state')
    if not state['started_clean']:
        raise ValueError('Publication requires a clean starting worktree')
    if git(root, 'rev-parse', 'HEAD') != state['source_commit'] or inventory(root) != state['inputs']:
        raise RuntimeError('Concurrent input edit; start a new candidate')
    if git(root, 'status', '--porcelain'):
        raise RuntimeError('Dirty worktree; start a new candidate')
    candidate = run_dir / 'validate'
    after = inventory(candidate)
    changes = {p for p in set(state['inputs']) | set(after) if state['inputs'].get(p) != after.get(p)}
    if any(not p.startswith(OUTPUTS) for p in changes):
        raise ValueError('Stage modified an input outside managed output paths')
    if any(p not in after for p in changes):
        raise ValueError('Daily publication cannot delete accepted files')
    journal = {'status': 'writing', 'files': {p: {'before': state['inputs'].get(p), 'after': after[p]} for p in sorted(changes)}}
    for rel, row in journal['files'].items():
        if row['before'] is not None:
            durable(run_dir / 'backup' / rel, (root / rel).read_bytes())
    durable(run_dir / 'publication.json', encoded(journal))
    # A final check closes the lengthy backup/validation preparation window.
    if inventory(root) != state['inputs'] or git(root, 'rev-parse', 'HEAD') != state['source_commit']:
        journal['status'] = 'cancelled'
        durable(run_dir / 'publication.json', encoded(journal))
        raise RuntimeError('Concurrent input edit before publication')
    try:
        for rel in journal['files']:
            # Advisory lock covers cooperating writers; detect other edits too.
            path = root / rel
            current = digest(path.read_bytes()) if path.exists() else None
            if current != journal['files'][rel]['before']:
                raise RuntimeError('Concurrent output edit during publication: ' + rel)
            replace(path, (candidate / rel).read_bytes())
        if inventory(root) != after or git(root, 'rev-parse', 'HEAD') != state['source_commit']:
            raise RuntimeError('Concurrent input edit during publication')
        journal['status'] = 'published'
        durable(run_dir / 'publication.json', encoded(journal))
    except Exception:
        recover_publication(root, run_dir)
        raise
    return len(changes)


def worker(stage, root, run_dir, options):
    """Executed in a new interpreter from the frozen stage code, never live code."""
    verify_private_inputs(run_dir, read(run_dir / 'state.json'))
    if stage == 'collect':
        from pipeline.collect import collect_sources
        from pipeline.collectors.browser.transport import Response
        responses = read(run_dir / 'inputs/responses.json') if (run_dir / 'inputs/responses.json').exists() else None
        def transport(url):
            row = responses[url]
            return Response(url, row['body'].encode(), row.get('status', 200), row.get('headers', {}))
        result = collect_sources(root, run_dir / 'collection', kind=options['kind'], source_ids=options['sources'],
            cutoff=options['collection_cutoff'], origin=options['origin'], resume=True,
            transport=transport if responses is not None else None,
            chrome_bundle=read(run_dir / 'inputs/chrome.json') if (run_dir / 'inputs/chrome.json').exists() else None,
            previous_bundle=read(run_dir / 'inputs/previous.json') if (run_dir / 'inputs/previous.json').exists() else None,
            reviewed_attributions=read(run_dir / 'inputs/attributions.json') if (run_dir / 'inputs/attributions.json').exists() else None,
            brave_release_metadata=read(run_dir / 'inputs/brave.json') if (run_dir / 'inputs/brave.json').exists() else None,
            sample_paths=options['sample_paths'], max_files=options['max_files'], max_trees=options['max_trees'])
        from schemas.validate import load_config
        enabled = {s['source_id'] for s in load_config(root / 'config/sources.yml')['sources'] if s['enabled']}
        result['requested_complete'] = result['complete']
        result['complete'] = (result['complete'] and options['kind'] == 'all'
                              and (not options['sources'] or set(options['sources']) == enabled))
        return result
    if stage == 'select':
        from pipeline.selection import run, load_rules
        decisions = read(run_dir / 'inputs/decisions.json') if (run_dir / 'inputs/decisions.json').exists() else None
        result = run(root, run_dir / 'evaluation', assessed_at=options['assessed_at'],
            rules=load_rules(root / 'rules/pm/pm-selection-v3.json'),
            provider=(lambda context, rules: decisions[context['subject_id']]) if decisions is not None else None,
            model_id=options['model_id'])
        return {'complete': not result['failures'], 'failed': len(result['failures']), 'cached': result['cached'],
                'created': len(result['created']), 'sources': len(result['coverage'])}
    if stage == 'report':
        from pipeline.reporting import run
        state = read(run_dir / 'state.json')
        result = run(root, run_dir / 'reporting', day=options['day'], cutoff=options['report_cutoff'],
            previous_cutoff=options['previous_cutoff'],
            collection='complete' if state['stages']['collect']['result']['complete'] else 'partial',
            evaluation='complete' if state['stages']['select']['result']['complete'] else 'partial')
        return {'report_id': result['report']['report_id'], 'revision': result['report']['revision'],
                'items': len(result['report']['items'])}
    if stage == 'validate':
        from pipeline.normalize import validate_graph
        from scripts.build_dashboard import build, read_resource as read_dashboard_json
        from scripts.export_dataset import export
        graph = validate_graph(root)
        sha = commit_candidate(root)
        build(root / 'dist')
        payload = read(root / 'dist/data.json')
        for kind in ('features', 'flags'):
            selected = read(root / ('data/selected/' + kind + '/current.json'))
            expected = {(r['subject_kind'], r['subject_id'], r['assessment_id']) for r in selected['current']}
            actual = {(r['subject_kind'], r['id'], r['assessment_id']) for r in payload['selected'][kind]}
            if expected != actual:
                raise ValueError('Dashboard/selected mismatch')
        for entry in payload['reports']:
            rendered = read_dashboard_json(root / 'dist' / entry['path'])
            original = read(root / ('data/reports/history/%s/revision-%s.json' % (entry['date'], entry['revision'])))
            if rendered != original:
                raise ValueError('Dashboard/report mismatch')
        package = run_dir / 'validation-export'
        if package.exists():
            shutil.rmtree(package)
        result = export(root, sha, package, source_repository='https://example.invalid/private-validation-only')
        return {'counts': {k: len(v) for k, v in graph.items()}, 'export': result,
                'provenance': 'synthetic private validation only; export the actual delivery commit separately'}
    raise ValueError('Unknown stage')


def subprocess_stage(stage, root, run_dir, options, *, lock_fd=None):
    env = dict(os.environ, PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE='1')
    with (run_dir / (stage + '.log')).open('ab') as log:
        subprocess.run([sys.executable, '-m', 'pipeline.run_daily', '--worker', stage, str(run_dir)],
                       cwd=root, env=env, stdout=log, stderr=log, check=True,
                       pass_fds=() if lock_fd is None else (lock_fd,))
    return read(run_dir / (stage + '-result.json'))


def run(repository, private_dir, run_id, *, resume=False, publish=False, allow_partial=False, retry_collection=False,
        options=None, input_files=None, execute=subprocess_stage, browser_cache_from=None):
    root, private = Path(repository).resolve(), Path(private_dir).resolve()
    require_external(root, private)
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', run_id):
        raise ValueError('Unsafe run ID')
    private.mkdir(parents=True, exist_ok=True, mode=0o700)
    run_dir = private / run_id
    with run_lock(root) as lock:
        # The global lock also identifies an interrupted publisher, even when a
        # subsequent caller chooses a different private state directory.
        lock.seek(0)
        pending = lock.read().strip()
        if pending:
            recover_publication(root, Path(json.loads(pending)['run_dir']))
        # Recover every journal in this state root before any new run.
        for old in private.glob('*/publication.json'):
            metadata = read(old.parent / 'state.json')
            if metadata['repository'] == str(root):
                recover_publication(root, old.parent)
        path = run_dir / 'state.json'
        if path.exists():
            if not resume:
                raise ValueError('Run exists; use --resume with its frozen options')
            state = read(path)
            if state['repository'] != str(root):
                raise ValueError('Run belongs to another repository')
            options = state['options']
            if state.get('published') or (run_dir / 'publication.json').exists() and read(run_dir / 'publication.json')['status'] == 'published':
                state['published'] = True
                durable(path, encoded(state))
                return state
            if retry_collection:
                state['stages'] = {}
                state['status'] = 'running'
                # Retry keeps the source snapshot/cache/revision but uses actual
                # new evaluation/report time, never backdates new judgments.
                options['assessed_at'] = None
                options['report_cutoff'] = None
        else:
            if resume:
                raise ValueError('No checkpoint to resume')
            if run_dir.exists():
                raise ValueError('Incomplete initialization; use a new run ID')
            run_dir.mkdir(mode=0o700)
            options = dict(options or {})
            initial = inventory(root)
            state = {'version': 1, 'repository': str(root), 'source_commit': git(root, 'rev-parse', 'HEAD'),
                     'started_clean': not git(root, 'status', '--porcelain'), 'inputs': initial,
                     'options': options, 'stages': {}, 'status': 'running', 'published': False}
            if publish and not state['started_clean']:
                raise ValueError('Publication requires a clean starting worktree')
            base = run_dir / 'base'
            for rel in initial:
                durable(base / rel, (root / rel).read_bytes())
            if inventory(root) != initial or git(root, 'rev-parse', 'HEAD') != state['source_commit']:
                raise RuntimeError('Inputs changed during snapshot')
            for name, source in (input_files or {}).items():
                if name not in ('responses', 'chrome', 'previous', 'decisions', 'attributions', 'brave'):
                    raise ValueError('Unknown private input')
                durable(run_dir / 'inputs' / (name + '.json'), Path(source).read_bytes())
            if browser_cache_from:
                require_external(root, Path(browser_cache_from).resolve())
                from pipeline.collectors.browser.cache import seed_cache
                provenance = seed_cache(browser_cache_from, run_dir / 'collection/browser', options['collection_cutoff'])
                durable(run_dir / 'inputs/browser-cache-provenance.json', encoded(provenance))
            state['private_inputs'] = private_input_inventory(run_dir / 'inputs')
        durable(path, encoded(state))
        if inventory(run_dir / 'base') != state['inputs']:
            raise ValueError('Pinned base snapshot changed')
        verify_private_inputs(run_dir, state)
        previous = run_dir / 'base'
        for stage in STAGES:
            verify_private_inputs(run_dir, state)
            completed = state['stages'].get(stage, {})
            target = run_dir / stage
            if completed.get('status') == 'done':
                if inventory(target) != completed['outputs']:
                    raise ValueError('Completed snapshot changed: ' + stage)
                previous = target
                continue
            if stage == 'select' and not options.get('assessed_at'):
                options['assessed_at'] = datetime.now(timezone.utc).isoformat()
            if stage == 'report' and not options.get('report_cutoff'):
                options['report_cutoff'] = datetime.now(timezone.utc).isoformat()
                options['day'] = (datetime.fromisoformat(options['report_cutoff']) + timedelta(hours=9)).date().isoformat()
            state['stages'][stage] = {'status': 'running'}
            durable(path, encoded(state))
            copy_snapshot(previous, target)
            try:
                result = (subprocess_stage(stage, target, run_dir, options, lock_fd=lock.fileno())
                          if execute is subprocess_stage else execute(stage, target, run_dir, options))
                outputs = inventory(target)
                # Commit the checkpoint only after stage bytes reach storage.
                for rel in outputs:
                    with (target / rel).open('rb') as stream:
                        os.fsync(stream.fileno())
                for directory in sorted({(target / rel).parent for rel in outputs}, key=lambda p: len(p.parts), reverse=True):
                    sync_dir(directory)
                state['stages'][stage] = {'status': 'done', 'result': result, 'outputs': outputs}
                durable(path, encoded(state))
            except Exception as error:
                state['status'] = 'failed'
                state['stages'][stage] = {'status': 'failed', 'error_type': type(error).__name__}
                durable(path, encoded(state))
                raise
            previous = target
        state['status'] = 'complete' if all(state['stages'][s]['result']['complete'] for s in ('collect', 'select')) else 'partial'
        durable(path, encoded(state))
        if publish:
            lock.seek(0)
            lock.truncate()
            lock.write(json.dumps({'run_dir': str(run_dir)}))
            lock.flush()
            os.fsync(lock.fileno())
            state['published_files'] = publish_candidate(root, run_dir, state, allow_partial=allow_partial)
            state['published'] = True
            durable(path, encoded(state))
        return state


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--worker':
        stage, run_dir = sys.argv[2], Path(sys.argv[3])
        result = worker(stage, Path.cwd(), run_dir, read(run_dir / 'state.json')['options'])
        durable(run_dir / (stage + '-result.json'), encoded(result))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--retry-collection', action='store_true')
    parser.add_argument('--publish', action='store_true', help='Publish only a complete validated candidate from clean inputs')
    parser.add_argument('--allow-partial', action='store_true', help='Explicitly publish valid partial evidence; report stays incomplete')
    parser.add_argument('--kind', choices=['browser', 'chrome', 'all'], default='all')
    parser.add_argument('--source', action='append')
    parser.add_argument('--origin', choices=['baseline', 'daily', 'backfill'], default='baseline')
    parser.add_argument('--cutoff', help='Frozen collection window; report cutoff uses actual completion time')
    parser.add_argument('--previous-cutoff')
    parser.add_argument('--sample-path', action='append')
    parser.add_argument('--max-files', type=int, default=20)
    parser.add_argument('--max-trees', type=int, default=20)
    parser.add_argument('--chrome-bundle', type=Path)
    parser.add_argument('--browser-cache-from', type=Path, help='Checksum-verified raw response carry-forward at the same cutoff; reparse every document')
    parser.add_argument('--reviewed-attributions', type=Path, help='Private human-reviewed document SHA256 to attribution-line SHA256 list; new content remains unresolved')
    parser.add_argument('--brave-release-metadata', type=Path, help='Private verified full GitHub release metadata; hash-frozen for this new run')
    parser.add_argument('--previous-bundle', type=Path)
    parser.add_argument('--responses', type=Path, help='Private fixture URL map; this is replay, not live collection')
    parser.add_argument('--decisions', type=Path)
    parser.add_argument('--model-id')
    args = parser.parse_args()
    if args.max_files < 1 or args.max_trees < 1:
        parser.error('Budgets must be positive')
    if args.retry_collection and not args.resume:
        parser.error('--retry-collection requires --resume')
    if bool(args.decisions) != bool(args.model_id):
        parser.error('--decisions and its actual --model-id are required together')
    options = dict(kind=args.kind, sources=args.source, origin=args.origin,
        collection_cutoff=args.cutoff or datetime.now(timezone.utc).isoformat(), previous_cutoff=args.previous_cutoff,
        sample_paths=args.sample_path, max_files=args.max_files, max_trees=args.max_trees,
        model_id=args.model_id, assessed_at=None, report_cutoff=None, day=None)
    state = run(args.repository, args.private_dir, args.run_id, resume=args.resume, publish=args.publish,
        browser_cache_from=args.browser_cache_from,
        retry_collection=args.retry_collection, allow_partial=args.allow_partial, options=options,
        input_files={k: v for k, v in dict(chrome=args.chrome_bundle, previous=args.previous_bundle, attributions=args.reviewed_attributions, brave=args.brave_release_metadata,
                                         responses=args.responses, decisions=args.decisions).items() if v})
    print(json.dumps({k: state[k] for k in ('status', 'published', 'source_commit')}))
    return 0 if state['status'] == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
