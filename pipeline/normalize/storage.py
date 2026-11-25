"""Validate the whole candidate graph before a rollback-protected publication."""
import copy
import fcntl
import json
import os
import tempfile
from pathlib import Path

from pipeline.deduplicate import AliasIndex
from pipeline.run_daily import pending_recovery, run_lock
from pipeline.source_item_shards import EDGE_PART, MAX_SHARD_BYTES, edge_policy_paths, validate_edge_policy_shard
from schemas.validate import ContractError, load_config, validate_dataset, validate_transition, validate_record, KINDS

PATHS = {
    'source_item': 'data/source-items/*/*.json',
    'feature': 'data/catalog/features/*.json',
    'feature_event': 'data/events/*.json',
    'experiment': 'data/catalog/chrome-experiments/*.json',
    'experiment_event': 'data/experiment-events/*.json',
    'assessment': 'data/assessments/*/*.json',
    'selected': 'data/selected/*/*.json',
    'report': 'data/reports/current/*.json',
}


def records(value):
    return value if isinstance(value, list) else [value]


def load_source_items(repository, replacements=None):
    root = Path(repository)
    replacements = replacements or {}
    pattern = PATHS['source_item']
    paths = {p.relative_to(root).as_posix() for p in root.glob(pattern)}
    paths.update(p for p in replacements if Path(p).match(pattern))
    paths.update(p.relative_to(root).as_posix() for p in root.glob(EDGE_PART + '*'))
    sharded = {p for p in edge_policy_paths(paths) if p.startswith(EDGE_PART)}
    result = []
    for rel in sorted(paths):
        path = root / rel
        if rel in sharded and (path.is_symlink() or
                               (rel not in replacements and path.stat().st_size > MAX_SHARD_BYTES)):
            raise ContractError('Unsafe Edge policy shard file')
        values = replacements[rel] if rel in replacements else load_config(path)
        if rel in sharded:
            validate_edge_policy_shard(rel, values)
        result.extend(records(values))
    if len(result) != len({r['source_item_id'] for r in result}):
        raise ContractError('Duplicate current source_item identity')
    return result


def load_dataset(repository, replacements=None):
    root = Path(repository)
    replacements = replacements or {}
    result = {}
    for kind, pattern in PATHS.items():
        if kind == 'source_item':
            result[kind] = load_source_items(root, replacements)
            continue
        paths = {str(p.relative_to(root)) for p in root.glob(pattern)}
        paths.update(p for p in replacements if Path(p).match(pattern))
        result[kind] = [r for p in sorted(paths) for r in records(replacements[p] if p in replacements else load_config(root / p))]
        id_field = KINDS[kind][1]
        if id_field:
            ids = [r[id_field] for r in result[kind]]
            if len(ids) != len(set(ids)):
                raise ContractError('Duplicate current ' + kind + ' identity')
    return result


def validate_graph(repository, replacements=None):
    dataset = load_dataset(repository, replacements)
    registry = load_config(Path(repository) / 'config/sources.yml')
    validate_record('sources_config', registry)
    validate_dataset(dataset, {s['source_id'] for s in registry['sources']} | {'legacy', 'chromium-source'})
    alias_path = 'data/aliases/corrections.json'
    aliases = (replacements or {}).get(alias_path)
    if aliases is None:
        path = Path(repository) / alias_path
        aliases = load_config(path) if path.exists() else []
    AliasIndex(aliases, {k: {r[k + '_id'] for r in dataset[k]} for k in ('feature', 'experiment')},
               {s['source_item_id'] for s in dataset['source_item']})
    # Every feature/evidence writer shares this validation. A later run may append
    # evidence, but cannot replace a quote or revision certified at an earlier cutoff.
    from pipeline.browser_status import validate_tree as validate_browser_status
    validate_browser_status(Path(repository).resolve(), graph=dataset)
    return dataset


def publish(repository, replacements, private_dir, *, replace=os.replace, text_files=None):
    """Stage and validate all files, reject concurrent edits, rollback on failure.

    The private transaction directory contains backups, never public operation
    logs. In-process failures roll back. This is not a multi-file filesystem
    atomic commit under power loss; retain the private backup for recovery.
    """
    root, private = Path(repository).resolve(), Path(private_dir).resolve()
    text_files = text_files or {}
    if set(text_files) & set(replacements):
        raise ValueError('A path cannot contain both JSON and text')
    all_files = dict(replacements, **text_files)
    if private == root or root in private.parents:
        raise ValueError('Transaction state must be outside the repository')
    if any(rel.startswith(('data/browser-status/', 'data/daily-status/', 'data/weekly-status/')) for rel in all_files):
        raise ContractError('Collection receipts require the collection publication transaction')
    private.mkdir(parents=True, exist_ok=True)
    with run_lock(root) as writer, open(private / 'normalize.lock', 'a') as lock:
        pending_recovery(root, writer)
        fcntl.flock(lock, fcntl.LOCK_EX)
        initial = {str(p.relative_to(root)): p.read_bytes() for pattern in PATHS.values() for p in root.glob(pattern)}
        initial.update({p: (root / p).read_bytes() if (root / p).exists() else None for p in all_files})
        for rel, value in all_files.items():
            target = (root / rel).resolve()
            if target == root or root not in target.parents or '..' in Path(rel).parts or Path(rel).is_absolute():
                raise ValueError('Unsafe publication path')
            if rel in text_files:
                if not rel.startswith('reports/generated/'):
                    raise ValueError('Generated report text must stay in reports/generated/')
                if rel != 'reports/generated/README.md' and initial.get(rel) is not None and initial[rel] != value.encode():
                    raise ContractError('Generated report revisions are immutable')
                continue
            if rel.startswith('data/reports/history/') and initial.get(rel) and json.loads(initial[rel]) != value:
                raise ContractError('Report archives are immutable')
            if Path(rel).match(PATHS['report']) and initial.get(rel):
                validate_transition('report', json.loads(initial[rel]), value)
            if rel.startswith('data/event-revisions/') and initial.get(rel) and json.loads(initial[rel]) != value:
                raise ContractError('Event archives are immutable')
            if rel.startswith(('data/assessments/', 'data/selected/history/')) and initial.get(rel) and json.loads(initial[rel]) != value:
                raise ContractError('Assessment and dated selection archives are immutable')
            if rel.startswith('data/selected/') and Path(rel).match(PATHS['selected']) and initial.get(rel):
                validate_transition('selected', json.loads(initial[rel]), value)
            if rel == 'data/aliases/corrections.json' and initial.get(rel):
                old_aliases = json.loads(initial[rel])
                if value[:len(old_aliases)] != old_aliases:
                    raise ContractError('Alias corrections must be append-only')
            if rel.startswith('data/source-items/') and initial.get(rel):
                old = {r['source_item_id']: r for r in records(json.loads(initial[rel]))}
                new = {r['source_item_id']: r for r in records(value)}
                if not set(old).issubset(new):
                    raise ContractError('Source records cannot disappear')
                for ident in old:
                    validate_transition('source_item', old[ident], new[ident])
        graph = validate_graph(root, replacements)
        with tempfile.TemporaryDirectory(prefix='transaction-', dir=private) as temp:
            stage = Path(temp)
            changed = []
            for rel, value in all_files.items():
                content = value.encode() if rel in text_files else (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
                if initial.get(rel) == content:
                    continue
                staged = stage / 'new' / rel
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(content)
                if initial.get(rel) is not None:
                    backup = stage / 'old' / rel
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    backup.write_bytes(initial[rel])
                changed.append(rel)
            # Validate optimistic snapshot immediately before the first write.
            actual_paths = {str(p.relative_to(root)) for pattern in PATHS.values() for p in root.glob(pattern)}
            original_paths = {p for p, value in initial.items() if value is not None and any(Path(p).match(v) for v in PATHS.values())}
            if actual_paths != original_paths or any(((root / p).read_bytes() if (root / p).exists() else None) != content for p, content in initial.items()):
                raise ContractError('Concurrent dataset edit; rebuild candidate')
            written = []
            try:
                for rel in sorted(changed):
                    target = root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    replace(stage / 'new' / rel, target)
                    written.append(rel)
            except BaseException:
                for rel in reversed(written):
                    if initial[rel] is None:
                        (root / rel).unlink()
                    else:
                        os.replace(stage / 'old' / rel, root / rel)
                raise
        return {kind: len(rows) for kind, rows in graph.items()}
