"""Find pre-settlement full-window evidence when a later revision moved its cutoff."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess

from pipeline.run_daily import git
from pipeline.source_item_shards import EDGE_PART, EDGE_POLICY, EDGE_SHARDS
from pipeline.temporal import instant


ROOTS = ('data/catalog/features', 'data/source-items')


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


def alias_evidence_tree(root, commit):
    """Compare logical file versions even when the correction renames DATA itself."""
    from pipeline.normalize.storage import PATHS
    from pipeline.receipt_history import direct_git_children
    found = {}
    for name, (_, kind, tree) in direct_git_children(root, commit).items():
        if name.casefold() != 'data' or kind != b'tree':
            continue
        for line in git(root, '-c', 'core.quotePath=true', 'ls-tree', '-r', tree.decode(), '--',
                        'catalog/features', 'source-items').splitlines():
            info, name = line.split('\t', 1)
            rel = 'data/' + name
            mode, _, oid = info.split()
            if mode in ('100644', '100755') and any(Path(rel).match(PATHS[k]) for k in ('feature', 'source_item')):
                found.setdefault(rel, set()).add(oid)
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
    patterns = (PATHS['feature'], PATHS['source_item'])
    output = git(root, '-c', 'core.quotePath=true', 'log', '--format=', '--raw', '-m', '--root',
                 '--full-history', '--no-renames', '--no-abbrev', ref, '--', *ROOTS)
    versions = {}
    for line in output.splitlines():
        if not line.startswith(':'):
            continue
        info, rel = line.split('\t', 1)
        if any(Path(rel).match(pattern) for pattern in patterns):
            old_mode, new_mode, old, new, _ = info[1:].split()
            versions.setdefault(rel, set()).update(oid for mode, oid in ((old_mode, old), (new_mode, new))
                                                   if mode in ('100644', '100755'))
    tips = {}
    for line in git(root, '-c', 'core.quotePath=true', 'ls-tree', '-r', ref, '--', *ROOTS).splitlines():
        info, rel = line.split('\t', 1)
        mode, _, oid = info.split()
        if mode in ('100644', '100755') and rel in versions:
            tips[rel] = oid
    return tips, versions


@lru_cache(maxsize=256)
def check_committed(root, ref, since, cutoff, *, checked_earlier=False):
    """A surviving source row cannot go back to an earlier cutoff in a normal save."""
    tips, versions = evidence_versions(root, ref)
    inspect = set()
    if not checked_earlier:
        for rel, oid in tips.items():
            scopes = committed_windows(root, oid)
            if scopes is None or needs_history(scopes, since, cutoff):
                inspect.add(rel)
    # Retired data files have no surviving timestamp bound. The Edge migration
    # preserved every row in the current shards, which provide the same bound.
    earlier_shards = set(EDGE_SHARDS).issubset(tips) and not any(path.startswith(EDGE_PART) for path in inspect)
    for rel in versions.keys() - tips.keys():
        if rel != EDGE_POLICY or not earlier_shards:
            inspect.add(rel)
    # A single source file usually proves the conflict before the shared catalog.
    for rel in sorted(inspect, key=lambda path: (not path.startswith('data/source-items/'), path)):
        for oid in sorted(versions[rel] - {tips.get(rel)}):
            needs_history(committed_windows(root, oid) or (), since, cutoff)
