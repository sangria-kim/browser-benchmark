"""Export a pinned public data tree; verify and activate a managed import.

Run this trusted tool from a separately reviewed checkout. Never execute code from
an incoming package. Python 3.9+; install schemas/requirements.txt.
"""
import argparse
import fcntl
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from pipeline.normalize import validate_graph
from pipeline.normalize.storage import records
from pipeline.reporting.core import render, instant
from schemas.validate import ContractError, validate_dataset, validate_record

VERSION = '1.1'
MANIFEST = 'manifest.json'
MARKER = '.browser-benchmark-import.json'
MARKER_VALUE = {'managed_by': 'browser-benchmark-data-import', 'contract_version': VERSION}
LINK_POLICY = 'preserve-relative-allowlisted-or-immutable-source-url'
# Positive policy, maintained with the trusted importer, not supplied by a package.
POLICY = json.loads((ROOT / 'config/export-allowlist.json').read_text())
LINK = re.compile(r'\]\((<?[^\s)]+>?)(?:\s+["\'][^\n]*?["\'])?\)')
REFERENCE_LINK = re.compile(r'^\s*\[[^\]\n]+\]:\s*(<?[^\s]+>?)', re.M)
HTML_LINK = re.compile(r'\b(?:href|src)\s*=\s*["\']([^"\']+)["\']', re.I)
SECRET = re.compile(r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16})\b')
SECRET_KEYS = {'password', 'passwd', 'access_token', 'refresh_token', 'api_key', 'client_secret', 'private_key', 'authorization', 'cookie', 'set_cookie'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def safe_path(value):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_. /-]+', value)
            or any(p in ('', '.', '..') or p.startswith('.') for p in value.split('/'))
            or any(p.endswith((' ', '.')) for p in value.split('/'))):
        raise ContractError('Unsafe package path: ' + repr(value))
    return value


def data_kind(path, payload=None):
    safe_path(path)
    if path in POLICY['exact_paths']:
        return POLICY['exact_paths'][path]
    for rule in POLICY['rules']:
        if re.fullmatch(rule['pattern'], path):
            if payload is not None and path.startswith('data/event-revisions/'):
                value = json.loads(payload)
                return 'experiment-events' if 'experiment_id' in value else 'feature-events'
            return rule['data_kind']
    raise ContractError('Path is outside the trusted allowlist: ' + path)


def git(repository, *args):
    return subprocess.check_output(['git', '-C', str(repository), *args], stderr=subprocess.PIPE)


def git_tree(repository, sha):
    result = {}
    for entry in git(repository, 'ls-tree', '-r', '-z', sha).split(b'\0'):
        if not entry:
            continue
        header, path = entry.split(b'\t', 1)
        mode, kind, oid = header.decode().split()
        result[path.decode('utf-8')] = (mode, kind, oid)
    return result


def read_blobs(repository, entries):
    """One Git process; immutable object IDs prevent branch movement mixing bytes."""
    process = subprocess.Popen(['git', '-C', str(repository), 'cat-file', '--batch'],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for path, (mode, kind, oid) in sorted(entries.items()):
            if mode != '100644' or kind != 'blob':
                raise ContractError('Only non-executable regular data files are allowed: ' + path)
            process.stdin.write((oid + '\n').encode())
            process.stdin.flush()
            header = process.stdout.readline().decode().split()
            if len(header) != 3 or header[0] != oid or header[1] != 'blob':
                raise ContractError('Invalid Git blob response')
            size = int(header[2])
            data = process.stdout.read(size)
            if len(data) != size or process.stdout.read(1) != b'\n':
                raise ContractError('Truncated Git blob')
            yield path, data
    finally:
        process.stdin.close()
        process.stdout.close()
        process.stderr.close()
        process.wait()


def regular_files(root):
    """Reject symlinks, special files and case-fold aliases before any reads."""
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ContractError('Expected a real package directory')
    found, folded = {}, set()
    for current, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            path = Path(current) / name
            safe_path(path.relative_to(root).as_posix())
            mode = path.lstat().st_mode
            if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)) or (stat.S_ISREG(mode) and mode & 0o111):
                raise ContractError('Symlink or special file rejected: ' + str(path))
        for name in files:
            path = Path(current) / name
            relative = path.relative_to(root).as_posix()
            safe_path(relative)
            if relative.casefold() in folded:
                raise ContractError('Case-insensitive package path collision')
            folded.add(relative.casefold())
            found[relative] = path
    return found


def check_public_content(path, data):
    text = data.decode('utf-8')
    if SECRET.search(text):
        raise ContractError('Credential signature in allowed data: ' + path)
    if path.endswith(('.json', '.yml')):
        value = json.loads(text)
        def check(item):
            if isinstance(item, dict):
                for key, child in item.items():
                    if key.lower().replace('-', '_') in SECRET_KEYS and child:
                        raise ContractError('Credential field in allowed data: ' + path)
                    check(child)
            elif isinstance(item, list):
                for child in item:
                    check(child)
        check(value)


def check_links(root, files):
    """Preserve relative paths. Missing or excluded targets fail closed."""
    directories = {'.'}
    for name in files:
        directories.update(str(p) for p in Path(name).parents if str(p) != '.')
    count = 0
    for name in files:
        if not name.endswith('.md'):
            continue
        text = (root / name).read_text()
        for target in LINK.findall(text) + REFERENCE_LINK.findall(text) + HTML_LINK.findall(text):
            target = target.strip('<>')
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            decoded = unquote(url.path)
            if '\\' in decoded or decoded.startswith('/'):
                raise ContractError('Unsafe local link: ' + name + ' -> ' + target)
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(name), decoded))
            if resolved not in files and resolved not in directories:
                raise ContractError('Missing or excluded relative link: ' + name + ' -> ' + target)
            count += 1
    return count


def json_at(root, path):
    return json.loads((root / path).read_text())


def validate_contents(root, files):
    for path in POLICY['required_paths']:
        if path not in files:
            raise ContractError('Missing required dataset path: ' + path)
    for path in files:
        if path != MANIFEST:
            check_public_content(path, (root / path).read_bytes())
    dataset = validate_graph(root)
    validate_record('chrome_scope_config', json_at(root, 'config/chrome-source-scope.yml'))
    for assessment in dataset['assessment']:
        revision = assessment.get('input_revision') or ''
        if ':sha256:' in revision:
            provenance, expected = revision.rsplit(':sha256:', 1)
            archived_path, separator, fragment = provenance.partition('#')
            safe_path(archived_path)
            if archived_path not in files:
                raise ContractError('Missing assessed fact provenance: ' + archived_path)
            raw = (root / archived_path).read_bytes()
            hashes = {digest(raw)}
            if archived_path.endswith('.json'):
                value = json.loads(raw)
                if separator:
                    if fragment != 'event_id=' + assessment['subject_id'] or not isinstance(value, dict):
                        raise ContractError('Invalid assessed fact fragment')
                    matches = [r for r in value.get('events', []) if r.get('event_id') == assessment['subject_id']]
                    if len(matches) != 1:
                        raise ContractError('Missing or duplicate assessed legacy event')
                    value = matches[0]
                    hashes.clear()
                hashes.add(digest(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()))
            elif separator:
                raise ContractError('Unsupported assessed fact fragment')
            if expected not in hashes:
                raise ContractError('Assessed fact provenance hash mismatch')
    # Archive projections each have their own full history. Never union them.
    for path in sorted(root.glob('data/selected/history/*/*.json')):
        snapshot = json.loads(path.read_text())
        validate_dataset(dict(dataset, selected=[snapshot], report=[]))
        expected = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        projection_hash = hashlib.sha256(json.dumps([snapshot['current'], snapshot['history']], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if not path.stem.endswith(expected) and not (path.stem.endswith(snapshot['input_hash']) and snapshot['input_hash'] == projection_hash):
            raise ContractError('Selection snapshot filename/hash mismatch')
    for path in sorted(root.glob('data/event-revisions/*/*.json')):
        record = json.loads(path.read_text())
        kind = 'legacy_feature_event' if record.get('schema_version') == 1 else ('experiment_event' if 'experiment_id' in record else 'feature_event')
        validate_record(kind, record)
        if record['event_id'] != path.parent.name:
            raise ContractError('Event archive owner mismatch')
        if kind != 'legacy_feature_event':
            current = dataset[kind]
            validate_dataset(dict(dataset, **{kind: [r for r in current if r['event_id'] != record['event_id']] + [record]}, report=[]))
    def path_reference(path):
        safe_path(path)
        if path not in files:
            raise ContractError('Missing data reference: ' + path)
        return json_at(root, path) if path.endswith('.json') else None
    def report_paths(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.endswith('_path') and isinstance(child, str):
                    path_reference(child)
                elif key.endswith('_paths') and isinstance(child, list):
                    for path in child:
                        path_reference(path)
                else:
                    report_paths(child)
        elif isinstance(value, list):
            for child in value:
                report_paths(child)
    archives = {}
    source_index = {r['source_item_id']: r for r in dataset['source_item']}
    for path in sorted(root.glob('data/reports/history/*/*.json')):
        report = json.loads(path.read_text())
        validate_dataset(dict(dataset, report=[report]))
        if path.parent.name != report['date'] or path.name != 'revision-%s.json' % report['revision']:
            raise ContractError('Report archive path mismatch')
        key = report['report_id'], report['revision']
        if key in archives:
            raise ContractError('Duplicate report revision')
        archives[key] = report
        report_paths(report)
        snapshots = {}
        for snapshot_path in report.get('selection_snapshot_paths', []):
            snapshot = path_reference(snapshot_path)
            if snapshot['selection_kind'] in snapshots or instant(snapshot['as_of']) != instant(report['cutoff']):
                raise ContractError('Report selection snapshot kind/cutoff mismatch')
            snapshots[snapshot['selection_kind']] = snapshot
        if 'selection_snapshot_paths' in report and set(snapshots) != {'features', 'flags'}:
            raise ContractError('Report requires both fixed selection snapshots')
        for item in report['items']:
            if snapshots:
                snapshot = snapshots[item['selection_kind']]
                changes = {r['change_id'] for r in snapshot['history']}
                if not {item['change_id'], *item.get('related_change_ids', [])}.issubset(changes):
                    raise ContractError('Report change absent from its fixed selection snapshot')
            if 'details' not in item:
                continue
            assessment = path_reference(item['details']['assessment_path'])
            for field, original in [('assessment_rule_version', 'rule_version'), ('status', 'status'), ('priority', 'priority'), ('reasons', 'reasons'), ('comparison_question', 'comparison_question'), ('benchmark_readiness', 'benchmark_readiness')]:
                if item['details'].get(field) != assessment[original]:
                    raise ContractError('Report frozen assessment differs: ' + field)
            if assessment['assessment_id'] != item['assessment_id']:
                raise ContractError('Report assessment path points to another record')
            subject = records(path_reference(item['details']['subject_path']))
            id_key = 'source_item_id' if item['subject_kind'] == 'source_item' else 'event_id'
            if not any(r[id_key] == item['subject_id'] for r in subject):
                raise ContractError('Report subject path points to another record')
            for evidence in item.get('evidence', []):
                source_revision = next(r for r in source_index[evidence['source_item_id']]['revisions'] if r['revision_id'] == evidence['revision_id'])
                for field in ('content_sha256', 'source_revision', 'observed_at'):
                    if evidence[field] != source_revision[field]:
                        raise ContractError('Report frozen source revision differs: ' + field)
                for field in ('url', 'section', 'excerpt'):
                    if evidence.get(field) != source_revision['evidence'].get(field):
                        raise ContractError('Report frozen evidence differs: ' + field)
                if not any(r['source_item_id'] == evidence['source_item_id'] for r in records(path_reference(evidence['record_path']))):
                    raise ContractError('Report evidence path points to another record')
        if report.get('generator_version') == 'daily-selected-v1':
            if (root / report['markdown_path']).read_text() != render(report):
                raise ContractError('Frozen report Markdown differs from metadata')
    for report in dataset['report']:
        if archives.get((report['report_id'], report['revision'])) != report:
            raise ContractError('Current report lacks identical immutable revision')
    for (ident, revision), report in archives.items():
        previous = report.get('supersedes_revision')
        if previous is not None and (ident, previous) not in archives:
            raise ContractError('Missing prior report revision')
    index = json_at(root, 'data/compatibility/legacy-index.json')
    if index.get('index_version') != 1 or index.get('inventory_status') != 'legacy':
        raise ContractError('Unsupported legacy compatibility index')
    for items in index.values():
        if not isinstance(items, list):
            continue
        for item in items:
            path_reference(item['path'])
            for key, kind in [('feature_ids', 'feature'), ('experiment_ids', 'experiment')]:
                valid = {r[kind + '_id'] for r in dataset[kind]}
                if not set(item.get(key, [])).issubset(valid):
                    raise ContractError('Missing legacy compatibility catalog reference')
            if digest((root / item['path']).read_bytes()) != item['sha256']:
                raise ContractError('Legacy compatibility hash mismatch: ' + item['path'])
    links = check_links(root, files)
    return {'records': {kind: len(value) for kind, value in dataset.items()}, 'relative_links': links}


def verify(package, *, expected_commit, expected_manifest=None):
    root = Path(package)
    files = regular_files(root)
    if MANIFEST not in files:
        raise ContractError('Missing manifest')
    raw = files[MANIFEST].read_bytes()
    if expected_manifest is not None and digest(raw) != expected_manifest:
        raise ContractError('Manifest digest differs from trusted handoff')
    manifest = json.loads(raw)
    validate_record('export_manifest', manifest)
    provenance = urlsplit(manifest['source_repository'])
    if provenance.scheme != 'https' or not provenance.hostname or provenance.username or provenance.password or provenance.query or provenance.fragment:
        raise ContractError('Source repository must be a public HTTPS URL without credentials or query')
    if manifest['contract_version'] != VERSION:
        raise ContractError('Unsupported import contract version')
    if manifest['source_commit'] != expected_commit:
        raise ContractError('Unexpected source commit')
    inventory = {}
    for entry in manifest['files']:
        path = safe_path(entry['path'])
        data_kind(path)  # Check the trusted path rule before reading content.
        if path in inventory or path == MANIFEST or path not in files:
            raise ContractError('Missing or duplicate inventory path')
        payload = files[path].read_bytes()
        if entry['data_kind'] != data_kind(path, payload):
            raise ContractError('Wrong allowlist data kind')
        if len(payload) != entry['bytes'] or digest(payload) != entry['sha256']:
            raise ContractError('Package hash/length mismatch: ' + path)
        inventory[path] = entry
    if set(files) != set(inventory) | {MANIFEST}:
        raise ContractError('Package contains unlisted files')
    result = validate_contents(root, inventory)
    result.update(files=len(inventory), bytes=sum(e['bytes'] for e in inventory.values()),
                  manifest_sha256=digest(raw), source_commit=expected_commit)
    return result


def export(repository, ref, output, *, source_repository, after_pin=None):
    # Resolve once before reading the policy, tree or any source bytes.
    sha = git(repository, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()
    if not re.fullmatch('[0-9a-f]{40}', sha):
        raise ContractError('Expected SHA-1 Git source commit')
    if after_pin:
        after_pin(sha)
    tree = git_tree(repository, sha)
    # The source commit must explicitly carry the same reviewed policy as the tool.
    policy_entry = tree.get('config/export-allowlist.json')
    if policy_entry is None or policy_entry[:2] != ('100644', 'blob'):
        raise ContractError('Source commit has no regular export allowlist')
    committed_policy = json.loads(git(repository, 'cat-file', 'blob', policy_entry[2]))
    if committed_policy != POLICY:
        raise ContractError('Source/trusted export allowlist mismatch; review tool version')
    chosen = {}
    for path, entry in tree.items():
        try:
            data_kind(path)
        except ContractError:
            continue
        chosen[path] = entry
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ContractError('Export destination must not exist')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.data-export-', dir=output.parent))
    try:
        entries = []
        for path, payload in read_blobs(repository, chosen):
            target = stage / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            entries.append(dict(path=path, sha256=digest(payload), bytes=len(payload), data_kind=data_kind(path, payload)))
        manifest = dict(contract_version=VERSION, source_repository=source_repository, source_ref=ref,
                        source_commit=sha, files=entries, link_policy=LINK_POLICY)
        (stage / MANIFEST).write_bytes(encoded(manifest))
        result = verify(stage, expected_commit=sha)
        os.rename(stage, output)
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def no_symlink_ancestors(path):
    path = Path(path).absolute()
    if any(part.is_symlink() for part in (path,) + tuple(path.parents)):
        raise ContractError('Managed path has a symlink ancestor')
    return path


def initialize(managed):
    root = no_symlink_ancestors(managed)
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise ContractError('Initialize only an empty dedicated import subtree')
    (root / MARKER).write_bytes(encoded(MARKER_VALUE))
    (root / 'snapshots').mkdir()


def check_managed(managed):
    root = no_symlink_ancestors(managed)
    marker = root / MARKER
    if marker.is_symlink() or not marker.is_file() or json.loads(marker.read_text()) != MARKER_VALUE:
        raise ContractError('Missing explicit managed-subtree marker')
    snapshots = root / 'snapshots'
    if snapshots.is_symlink() or not snapshots.is_dir():
        raise ContractError('Unsafe snapshot directory')
    pointer = root / 'current.json'
    if pointer.is_symlink() or (pointer.exists() and not pointer.is_file()):
        raise ContractError('Unsafe current pointer')
    return root


def resolve(managed, *, verify_data=True):
    root = check_managed(managed)
    pointer = json_at(root, 'current.json')
    if not isinstance(pointer, dict) or set(pointer) != {'contract_version', 'source_commit', 'manifest_sha256', 'snapshot'} or pointer['contract_version'] != VERSION:
        raise ContractError('Invalid import pointer')
    sha, package_hash = pointer['source_commit'], pointer['manifest_sha256']
    if not isinstance(sha, str) or not isinstance(package_hash, str) or not re.fullmatch('[0-9a-f]{40}', sha) or not re.fullmatch('[0-9a-f]{64}', package_hash):
        raise ContractError('Invalid pointer hash')
    if pointer['snapshot'] != 'snapshots/' + package_hash:
        raise ContractError('Pointer escaped its content-addressed snapshot')
    snapshot = root / pointer['snapshot']
    if verify_data:
        verify(snapshot, expected_commit=sha, expected_manifest=package_hash)
    return snapshot


def activate(package, managed, private_dir, *, expected_commit, expected_manifest, replace=os.replace):
    root = check_managed(managed)
    private = no_symlink_ancestors(private_dir)
    # Locks/staging stay outside the consumer repository, not merely outside its data subtree.
    consumer = root
    while consumer.parent != consumer and not (consumer / '.git').exists():
        consumer = consumer.parent
    boundary = consumer if (consumer / '.git').exists() else root
    if private == boundary or boundary in private.parents:
        raise ContractError('Private staging/locks must be outside the consumer repository')
    private.mkdir(parents=True, exist_ok=True)
    with open(private / ('import-' + digest(str(root).encode()) + '.lock'), 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        check_managed(root)
        result = verify(package, expected_commit=expected_commit, expected_manifest=expected_manifest)
        snapshot = root / 'snapshots' / result['manifest_sha256']
        pointer = dict(contract_version=VERSION, source_commit=expected_commit,
                       manifest_sha256=result['manifest_sha256'], snapshot='snapshots/' + result['manifest_sha256'])
        if (root / 'current.json').exists():
            current = resolve(root)
            if current == snapshot:
                return dict(result, activated=False)
        with tempfile.TemporaryDirectory(prefix='import-stage-', dir=private) as directory:
            stage = Path(directory) / 'package'
            # Copy only already inventoried regular files, then verify the copy again.
            stage.mkdir()
            for name, source in regular_files(package).items():
                target = stage / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with open(source, 'rb', opener=lambda p, flags: os.open(p, flags | os.O_NOFOLLOW)) as stream:
                    target.write_bytes(stream.read())
            verify(stage, expected_commit=expected_commit, expected_manifest=expected_manifest)
            if snapshot.exists() or snapshot.is_symlink():
                verify(snapshot, expected_commit=expected_commit, expected_manifest=expected_manifest)
            else:
                # The final digest name only ever names a verified, durable copy.
                # Staging can be on another filesystem; publication cannot be.
                with tempfile.TemporaryDirectory(prefix='.snapshot-', dir=snapshot.parent) as directory:
                    candidate = Path(directory) / 'package'
                    shutil.copytree(stage, candidate)
                    verify(candidate, expected_commit=expected_commit, expected_manifest=expected_manifest)
                    for path in regular_files(candidate).values():
                        with open(path, 'rb') as stream:
                            os.fsync(stream.fileno())
                    for current_dir, _, _ in os.walk(candidate, topdown=False):
                        fsync_directory(Path(current_dir))
                    os.rename(candidate, snapshot)
                    fsync_directory(snapshot.parent)
            # Single same-filesystem pointer replacement is the activation boundary.
            descriptor, temporary = tempfile.mkstemp(prefix='.current-', dir=root)
            try:
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(encoded(pointer))
                    stream.flush()
                    os.fsync(stream.fileno())
                replace(temporary, root / 'current.json')
                fsync_directory(root)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        return dict(result, activated=True)


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    out = commands.add_parser('export')
    out.add_argument('--repository', type=Path, default=ROOT)
    out.add_argument('--ref', required=True)
    out.add_argument('--source-repository', required=True)
    out.add_argument('--output', type=Path, default=Path('dist/data-export/v1'))
    check = commands.add_parser('verify')
    add_package_arguments(check)
    init = commands.add_parser('init')
    init.add_argument('--managed', type=Path, required=True)
    imp = commands.add_parser('import')
    add_package_arguments(imp)
    imp.add_argument('--managed', type=Path, required=True)
    imp.add_argument('--private-dir', type=Path, required=True)
    current = commands.add_parser('resolve')
    current.add_argument('--managed', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'export':
            result = export(args.repository, args.ref, args.output, source_repository=args.source_repository)
        elif args.command == 'verify':
            result = verify(args.package, expected_commit=args.expected_commit, expected_manifest=args.manifest_sha256)
        elif args.command == 'init':
            initialize(args.managed)
            result = {'initialized': True}
        elif args.command == 'resolve':
            print(resolve(args.managed))
            return
        else:
            result = activate(args.package, args.managed, args.private_dir, expected_commit=args.expected_commit,
                              expected_manifest=args.manifest_sha256)
        print(json.dumps(result, sort_keys=True))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


def add_package_arguments(parser):
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--manifest-sha256', required=True)


if __name__ == '__main__':
    main()
