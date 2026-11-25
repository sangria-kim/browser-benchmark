"""Find full-window evidence in every reachable version before the first weekly settlement."""
from datetime import timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import subprocess

from pipeline.temporal import instant


ROOTS = ('data/catalog/features', 'data/source-items')
# Reproduce the object-set digest and inclusive maximum with the offline audit below.
AUDITED_COMMIT = '1d38f6d421258d871fb28212849015aed50e08d8'
AUDITED_OBJECTS = 'd3e0c94b92ee8bfd5a1ce8a710cc5d9f5cf3b1c7f699c5112cca8cbf3432b163'
AUDITED_MAXIMUM = instant('2026-11-21T23:00:00Z')


def windows(rows):
    # A damaged historical row cannot erase valid windows from the other rows.
    scopes = set()
    for row in rows:
        scope = row.get('temporal_scope') if isinstance(row, dict) else None
        if isinstance(scope, dict) and isinstance(scope.get('since'), str) and isinstance(scope.get('cutoff'), str):
            scopes.add((scope['since'], scope['cutoff']))
    result = set()
    for since, end in scopes:
        try:
            result.add((since, instant(end)))
        except (ValueError, OverflowError):
            continue
    return result


def matches_checkout(root, ref):
    diff = subprocess.run(['git', '-C', str(root), 'diff', '--no-ext-diff', '--quiet', ref, '--', *ROOTS])
    if diff.returncode == 1:
        return False
    diff.check_returncode()
    return not subprocess.check_output(['git', '-C', str(root), 'ls-files', '-z', '--others', '--', *ROOTS])


def needs_history(scopes, since, cutoff):
    if (since, cutoff) in scopes:
        raise ValueError('Existing evidence has this weekly cutoff and historical window; '
                         'the original publication cannot be verified')
    return any(end >= cutoff for _, end in scopes)


@lru_cache(maxsize=4096)
def committed_windows(root, oid):
    from pipeline.normalize.storage import records
    raw = subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', oid])
    try:
        return windows(records(json.loads(raw)))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None  # This version supplies no bound. Still check the preceding valid blobs.


@lru_cache(maxsize=64)
def evidence_tree(root, commit):
    """Keep physical roots distinct, including trees that a Mac cannot check out together."""
    from pipeline.normalize.storage import PATHS
    from pipeline.receipt_history import direct_git_children
    found = {}
    for folder, (_, kind, tree) in direct_git_children(root, commit).items():
        if folder.casefold() != 'data' or kind != b'tree':
            continue
        raw = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-rz', tree, '--',
                                       'catalog/features', 'source-items'])
        for entry in raw.split(b'\0'):
            if not entry:
                continue
            info, name = entry.split(b'\t', 1)
            suffix = os.fsdecode(name)
            mode, _, oid = info.decode('ascii').split()
            canonical = Path('data') / suffix
            if mode in ('100644', '100755') and any(canonical.match(PATHS[k]) for k in ('feature', 'source_item')):
                found[folder + '/' + suffix] = oid
    return found


def alias_evidence_tree(root, commit):
    # Only a same-byte spelling repair compares the logical data paths.
    found = {}
    for physical, oid in evidence_tree(root, commit).items():
        _, suffix = physical.split('/', 1)
        found.setdefault(suffix, set()).add(oid)
    return found


def matching_rows(root, oid, since, cutoff):
    from pipeline.normalize.storage import records
    if (since, cutoff) not in (committed_windows(root, oid) or ()):
        return set()
    raw = subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', oid])
    return {hashlib.sha256(json.dumps(row, sort_keys=True).encode()).digest()
            for row in records(json.loads(raw)) if (since, cutoff) in windows([row])}


def check_alias_transition(root, parent, child, since, cutoff):
    previous = alias_evidence_tree(root, parent)
    for rel, oids in alias_evidence_tree(root, child).items():
        old = previous.get(rel, set())
        if oids == old:
            continue
        added = set().union(*(matching_rows(root, oid, since, cutoff) for oid in oids - old))
        if added and not added.issubset(set().union(*(matching_rows(root, oid, since, cutoff) for oid in old))):
            raise ValueError('New evidence after the receipt alias cannot verify the original publication')


@lru_cache(maxsize=64)
def evidence_versions(root, ref):
    """Use tree metadata only. Keep the tip and distinct prior blobs for each JSON file."""
    from pipeline.normalize.storage import PATHS
    # Fold just the reserved root and preserve every physical spelling in Git output.
    patterns = [':(glob)[dD][aA][tT][aA]/' + PATHS[k].split('/', 1)[1] for k in ('feature', 'source_item')]
    output = subprocess.check_output(['git', '-C', str(root), 'log', '--format=', '--raw', '-z', '-m', '--root',
                                      '--full-history', '--no-renames', '--no-abbrev', ref, '--', *patterns])
    versions = {}
    fields = iter(output.split(b'\0'))
    for header in fields:
        if not header:
            continue
        rel = os.fsdecode(next(fields))
        old_mode, new_mode, old, new, _ = header.strip().decode('ascii').removeprefix(':').split()
        versions.setdefault(rel, set()).update(oid for mode, oid in ((old_mode, old), (new_mode, new))
                                               if mode in ('100644', '100755'))
    return evidence_tree(root, ref), versions


def evidence_oids(root, ref):
    tips, versions = evidence_versions(root, ref)
    return frozenset(tips.values()).union(*versions.values())


def oid_digest(oids):
    return hashlib.sha256(''.join(oid + '\n' for oid in sorted(oids)).encode('ascii')).hexdigest()


@lru_cache(maxsize=64)
def audited_oids(root, ref, anchor, digest):
    # Listing the reachable commits never requests an unknown anchor from a promisor remote.
    ancestors = subprocess.check_output(['git', '-C', str(root), 'rev-list', ref])
    if anchor.encode() not in ancestors.splitlines():
        return frozenset()
    oids = evidence_oids(root, anchor)
    return oids if oid_digest(oids) == digest else frozenset()


@lru_cache(maxsize=256)
def check_committed(root, ref, since, cutoff, *, checked_earlier=False):
    tips, versions = evidence_versions(root, ref)
    checked = set()
    if cutoff > AUDITED_MAXIMUM:
        checked.update(audited_oids(root, ref, AUDITED_COMMIT, AUDITED_OBJECTS))
    priority = set()
    for rel, oid in tips.items():
        if oid in checked:
            continue
        if not (checked_earlier and rel.startswith('data/')):
            scopes = committed_windows(root, oid)
            if scopes is None or needs_history(scopes, since, cutoff):
                priority.add(rel)
        checked.add(oid)
    # A revert or a partial row restoration can make any older blob contain a
    # later observation. A current row can prioritise inspection, never bound it.
    for rel in sorted(versions, key=lambda path: (path not in priority, '/source-items/' not in path, path)):
        for oid in sorted(versions[rel] - checked):
            needs_history(committed_windows(root, oid) or (), since, cutoff)
            checked.add(oid)


def audit(root, ref):
    """Read and verify each historical evidence blob once. Return a reproducible checkpoint."""
    from pipeline.normalize.storage import records
    commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--verify', ref + '^{commit}']).decode().strip()
    shallow = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--is-shallow-repository']).strip()
    if shallow != b'false':
        raise ValueError('Audit requires complete Git history')
    oids = evidence_oids(root, commit)
    maximum = None
    size = rows = 0
    for oid in sorted(oids):
        raw = subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', oid])
        hasher = hashlib.new({40: 'sha1', 64: 'sha256'}[len(oid)])
        hasher.update(b'blob ' + str(len(raw)).encode() + b'\0')
        hasher.update(raw)
        if hasher.hexdigest() != oid:
            raise ValueError('Git evidence blob does not match its object ID: ' + oid)
        values = records(json.loads(raw))
        size += len(raw)
        rows += len(values)
        for _, end in windows(values):
            if maximum is None or end > maximum:
                maximum = end
    return dict(commit=commit, object_digest=oid_digest(oids), objects=len(oids), bytes=size, rows=rows,
                maximum=maximum.astimezone(timezone.utc).isoformat() if maximum is not None else None)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Audit all historical feature and source evidence from local Git objects.')
    parser.add_argument('--audit', required=True, metavar='COMMIT')
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    args = parser.parse_args()
    os.environ.update(GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1', GIT_ALLOW_PROTOCOL='')
    print(json.dumps(audit(args.repo, args.audit), indent=2))
