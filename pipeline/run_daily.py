"""Daily feature collection, writer lock and publication recovery.

Run ``python -m pipeline.run_daily --help``. No Git delivery or scheduler changes.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile


# Only these outputs may replace public files. All other inputs are read-only.
OUTPUTS = ('data/source-items/', 'data/catalog/features/')
CODE_REPOSITORY = Path(__file__).resolve().parents[1]


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


def publication_commits(root):
    code = git(CODE_REPOSITORY, 'rev-parse', 'HEAD')
    return code, git(root, 'rev-parse', 'HEAD') if (root / '.git').exists() else code


def predates_browser_pins(commit):
    """Identify the producing collector from its local Git tree, including on shallow clones."""
    if not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit):
        return False
    try:
        if git(CODE_REPOSITORY, 'cat-file', '-t', commit) != 'commit':
            return False
        entries = git(CODE_REPOSITORY, 'ls-tree', '--name-only', commit, '--',
                      'pipeline/collect.py', 'pipeline/browser_status.py')
    except subprocess.CalledProcessError:
        return False
    return entries.splitlines() == ['pipeline/collect.py']


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
    # Pre-feature-only runners can leave a pending journal in the same lock.
    permitted = ('data/', 'reports/generated/') if state.get('version') in (1, 2) else OUTPUTS
    from pipeline.daily_status import status_path
    from pipeline.browser_status import is_detail, safe_path
    from pipeline.weekly_status import is_receipt as weekly_path
    version = state.get('version')
    receipt_allowed = version in (4, 5)
    expected = state['stages']['validate']['outputs']
    changed = {p for p in set(state['inputs']) | set(expected) if state['inputs'].get(p) != expected.get(p)}
    if set(journal['files']) != changed or (version == 6 and sum(weekly_path(p) for p in changed) != 1):
        raise ValueError('Recovery journal inventory mismatch')
    for rel, row in journal['files'].items():
        allowed = rel.startswith(permitted) or (receipt_allowed and status_path(rel)) or (version == 5 and is_detail(rel))
        allowed = allowed or (version == 6 and weekly_path(rel))
        if (not allowed or Path(rel).is_absolute() or '..' in Path(rel).parts
                or row != {'before': state['inputs'].get(rel), 'after': expected.get(rel)}
                or row['after'] is None):
            raise ValueError('Unsafe recovery journal entry')
        backup = run_dir / 'backup' / rel
        if version in (5, 6):
            safe_path(run_dir, 'backup/' + rel)
        if row['before'] is not None and (backup.is_symlink() or digest(backup.read_bytes()) != row['before']):
            raise ValueError('Recovery backup checksum mismatch')
    # Validate every path before rolling back any. Preserve third-party edits.
    for rel, row in journal['files'].items():
        path = root / rel
        if (path.is_symlink() or root not in path.resolve().parents
                or receipt_allowed and status_path(rel) and path.parent.is_symlink()):
            raise RuntimeError('Unsafe recovery target: ' + rel)
        if version in (5, 6):
            safe_path(root, rel)
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


def pending_recovery(root, writer):
    writer.seek(0)
    pending = writer.read().strip()
    if pending:
        recover_publication(root, Path(json.loads(pending)['run_dir']))


def store_changes(root, txn, changes, before, writer, *, replace=durable):
    """Validate the graph, then journal only the files that will change."""
    from pipeline.normalize import validate_graph
    from pipeline.collectors.browser.collector import json_bytes
    from pipeline.daily_status import previous_receipt, scheduled_cutoff, status_path, validate_receipt
    from pipeline import browser_status, weekly_status
    whole = {rel for rel in changes if weekly_status.is_receipt(rel)}
    details = {rel for rel in changes if browser_status.is_detail(rel)}
    if len(details) + len(whole) > 1:
        raise ValueError('Publish one weekly or browser result at a time')
    for rel in whole:
        result = changes[rel]
        weekly_status.validate(rel, result)
        weekly_status.require_unclaimed(root, result['scope'], scoped=False)
        browser_status.check_registry(root, result['scope'])
    for rel in details:
        detail = changes[rel]
        browser_status.validate_detail(rel, detail)
        previous = browser_status.read_current(root, rel)
        first_browser = previous is None
        if detail['scope']['mode'] == 'weekly_reconcile':
            weekly_status.require_unclaimed(root, detail['scope'], scoped=True)
        if previous is None:
            previous = browser_status.initial(detail['scope'])
        browser_status.transition(previous, detail)
        browser_status.check_registry(root, detail['scope'])
        browser_status.check_aggregate(root, detail, changes)
    receipts = {rel for rel in changes if status_path(rel)}
    if whole and receipts:
        raise ValueError('Whole weekly publication cannot write a daily receipt')
    for rel in receipts:
        validate_receipt(rel, changes[rel])
        scheduled_cutoff(changes[rel]['cutoff'])
        detail_rel = browser_status.detail_path('daily', changes[rel]['cutoff'])
        if detail_rel not in details and browser_status.read_current(root, detail_rel) is not None:
            raise ValueError('Finish this daily cutoff with --save-browser')
        if (root / rel).parent.is_symlink():
            raise ValueError('Invalid daily status folder')
    status_files = receipts | details | whole
    feature_changes = {rel: value for rel, value in changes.items() if rel not in status_files}
    # Failed collection may publish an incomplete status without touching feature data.
    if whole or details or feature_changes or not receipts or any(changes[rel]['status'] == 'complete' for rel in receipts):
        graph = validate_graph(root, feature_changes)
        for rel in whole:
            result = changes[rel]
            weekly_status.check_prior_evidence(root, result['scope'], graph, feature_changes)
            weekly_status.check_features(result, {f['feature_id']: f for f in graph['feature']})
        for rel in details:
            if first_browser and changes[rel]['scope']['mode'] == 'weekly_reconcile':
                weekly_status.check_prior_evidence(root, changes[rel]['scope'], graph, feature_changes)
            browser_status.check_effects(changes[rel], browser_status.effect_index(graph))
            browser_status.check_delta(root, previous, changes[rel], graph, feature_changes)
    payloads = {p: json_bytes(rows) for p, rows in changes.items()}
    payloads = {p: raw for p, raw in payloads.items() if digest(raw) != before[p]}

    def check_dependencies(expected):
        marker = read(browser_status.safe_path(txn, 'scope.json'))
        if publication_commits(root) != (marker['code_commit'], marker['base_commit']):
            raise ValueError('Browser publication commit changed; use a fresh collection')
        for rel, checksum in expected.items():
            path = browser_status.safe_path(root, rel)
            if (digest(path.read_bytes()) if path.exists() else None) != checksum:
                raise ValueError('Concurrent edit to browser publication input: ' + rel)

    if details or whole:
        check_dependencies(before)
    if not payloads:
        return
    after = {p: digest(raw) for p, raw in payloads.items()}
    inputs = {p: before[p] for p in payloads}
    for rel in payloads:
        path = root / rel
        if path.is_symlink() or root not in path.resolve().parents or not (rel.startswith(OUTPUTS) or rel in status_files):
            raise ValueError('Invalid feature output path')
        old = path.read_bytes() if path.exists() else None
        if (digest(old) if old is not None else None) != before[rel]:
            raise ValueError('Concurrent edit to feature output')
        if old is not None:
            if rel in receipts and previous_receipt(rel, old, changes[rel]['cutoff'])['status'] == 'complete':
                raise ValueError('Cannot change data after the daily status is complete')
            durable(txn / 'backup' / rel, old)
    version = 6 if whole else 5 if details else 4 if receipts else 3
    state = dict(version=version, repository=str(root), inputs=inputs, stages={'validate': {'outputs': after}})
    durable(txn / 'state.json', encoded(state))
    journal = dict(status='writing', files={p: dict(before=inputs[p], after=after[p]) for p in after})
    durable(txn / 'publication.json', encoded(journal))
    writer.seek(0)
    writer.truncate()
    writer.write(json.dumps({'run_dir': str(txn)}))
    writer.flush()
    os.fsync(writer.fileno())
    try:
        if details or whole:
            check_dependencies(before)
        for rel, raw in payloads.items():
            path = root / rel
            if (digest(path.read_bytes()) if path.exists() else None) != inputs[rel]:
                raise ValueError('Concurrent edit during feature publication')
            replace(path, raw)
        if any(digest((root / rel).read_bytes()) != after[rel] for rel in after):
            raise ValueError('Concurrent edit after feature publication')
        if details or whole:
            check_dependencies({**before, **after})
        journal['status'] = 'published'
        durable(txn / 'publication.json', encoded(journal))
    except Exception:
        recover_publication(root, txn)
        raise


if __name__ == '__main__':
    from pipeline.collect import main
    raise SystemExit(main(daily=True))
