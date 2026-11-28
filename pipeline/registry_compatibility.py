"""Recognize description-only registry updates without replacing pinned hashes."""
from functools import lru_cache
import json
import subprocess

from pipeline.run_daily import digest, git, repository_head

PATH = 'config/sources.yml'


def contract(raw):
    value = json.loads(raw)
    # Keep every field except this explicitly documentary field. In particular,
    # URL, enabled state, discovery limits and baseline policy remain exact.
    for source in value['sources']:
        source.pop('scope_note', None)
    return value


@lru_cache(maxsize=64)
def historical_registries(root, head):
    snapshots = {}
    revisions = git(root, 'rev-list', '--full-history', head, '--', PATH).splitlines()
    for commit in revisions:
        entries = git(root, 'ls-tree', commit, '--', PATH).splitlines()
        if not entries:
            continue
        mode, kind, oid = entries[0].split('\t', 1)[0].split()
        if kind != 'blob' or mode not in ('100644', '100755'):
            continue
        raw = subprocess.check_output(['git', '-C', str(root), 'cat-file', 'blob', oid])
        snapshots[digest(raw)] = raw
    return snapshots


def compatible(root, previous, current, *, ref=None):
    """Require the old bytes in ancestry, never a supplied or invented old hash."""
    head = ref or repository_head(root)
    if not head:
        return False
    snapshots = historical_registries(root, head)
    old = snapshots.get(previous)
    new = snapshots.get(current)
    if ref is None:
        raw = (root / PATH).read_bytes()
        if digest(raw) == current:
            new = raw
    return old is not None and new is not None and contract(old) == contract(new)
