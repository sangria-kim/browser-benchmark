"""Stable Edge policy buckets keep report paths and every revision intact."""
import json
import re
from pathlib import Path

from schemas.validate import ContractError

EDGE_POLICY = 'data/source-items/edge/edge-policies.json'
EDGE_PART = EDGE_POLICY.removesuffix('.json') + '.part-'
EDGE_SHARDS = tuple(f'{EDGE_PART}{i:02x}.json' for i in range(256))
MAX_SHARD_BYTES = 32 * 1024 * 1024
ITEM_ID = re.compile(r'src-([0-9a-f]{2})[0-9a-f]{22}')


def edge_policy_paths(paths):
    """Resolve the optional source and fail closed on a partial shard set."""
    paths = set(paths)
    parts = {p for p in paths if p.startswith(EDGE_PART)}
    if not parts:
        return (EDGE_POLICY,) if EDGE_POLICY in paths else ()
    if EDGE_POLICY in paths or parts != set(EDGE_SHARDS):
        raise ContractError('Mixed, incomplete or unexpected Edge policy shard set')
    return EDGE_SHARDS


def _part(row):
    ident = row.get('source_item_id') if isinstance(row, dict) else None
    match = ITEM_ID.fullmatch(ident) if isinstance(ident, str) else None
    if not match or row.get('source_id') != 'edge-policies' or row.get('browser') != 'edge':
        raise ContractError('Invalid Edge policy shard record identity')
    return f'{EDGE_PART}{match[1]}.json'


def _ordered(rows):
    if not isinstance(rows, list):
        raise ContractError('Edge policy shard must be an array')
    last = ''
    for row in rows:
        _part(row)
        ident = row['source_item_id']
        if ident <= last:
            raise ContractError('Edge policy records must be ordered with unique IDs')
        last = ident


def _bounded(rows):
    # Match the collector and normalizer on-disk encoding; reserve ample headroom.
    size = len((json.dumps(rows, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    if size > MAX_SHARD_BYTES:
        raise ContractError('Edge policy shard exceeds the 32 MiB storage limit')


def validate_edge_policy_shard(path, rows):
    _ordered(rows)
    if any(_part(row) != path for row in rows):
        raise ContractError('Edge policy record in the wrong shard')
    _bounded(rows)


def edge_policy_shards(rows):
    """Partition an already sorted array; never silently reorder or drop rows."""
    _ordered(rows)
    shards = {path: [] for path in EDGE_SHARDS}
    for row in rows:
        shards[_part(row)].append(row)
    for shard in shards.values():
        _bounded(shard)
    return shards


def read_edge_policies(root):
    """Read accepted records and report whether future writes must be sharded."""
    root = Path(root)
    directory = (root / EDGE_POLICY).parent
    candidates = {p.relative_to(root).as_posix() for p in directory.glob('edge-policies.part-*')}
    if (root / EDGE_POLICY).exists() or (root / EDGE_POLICY).is_symlink():
        candidates.add(EDGE_POLICY)
    paths = edge_policy_paths(candidates)
    rows = []
    sharded = paths == EDGE_SHARDS
    for path in paths:
        file = root / path
        if file.is_symlink() or (sharded and file.stat().st_size > MAX_SHARD_BYTES):
            raise ContractError('Unsafe Edge policy shard file')
        value = json.loads(file.read_text(encoding='utf-8'))
        if sharded:
            validate_edge_policy_shard(path, value)
        if not isinstance(value, list):
            raise ContractError('Edge policy source must be an array')
        rows.extend(value)
    if len(rows) != len({r['source_item_id'] for r in rows}):
        raise ContractError('Duplicate Edge policy source item')
    return rows, sharded
