"""Private Edge policy comparison and ordered replay of one collection per window."""
import argparse
from collections import Counter, defaultdict
import json
import os
import re
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from pipeline.collectors.browser.collector import canonical, digest, json_bytes
from pipeline.run_daily import durable, git, read, require_external, run_lock
from pipeline.source_item_shards import (EDGE_POLICY, EDGE_SHARDS, edge_policy_paths, edge_policy_shards,
                                         read_edge_policies, validate_edge_policy_shard)
from pipeline.temporal import instant
from schemas.validate import ContractError
from pipeline.git_objects import git_tree, read_blobs

SOURCE = 'edge-policies'
CHUNK_BYTES = 4 * 1024 * 1024


def checksum(value):
    return digest(canonical(value))


def indexed(rows):
    items = {r['source_item_id']: r for r in rows}
    if len(items) != len(rows) or any(r['source_id'] != SOURCE for r in rows):
        raise ContractError('Invalid Edge policy inventory')
    return items


POSITION_KEY = re.compile(r':(?:p|li|tr|pre|blockquote|dt|dd|div|span|unparsed):[0-9]+$|:location:[0-9a-f]+:[0-9]+$')


def policy_fingerprint(row, visible):
    # These product fields are independent of heading IDs and DOM locations.
    return checksum([visible, row.get('channel'), row.get('platform'), row.get('lifecycle'), row['record_status']])


def document_content(rows, content):
    """Count full normalized facts without treating a DOM slot as a policy identity."""
    counts, references = Counter(), {}
    for row in sorted(rows, key=lambda r: r['source_item_id']):
        fingerprint = policy_fingerprint(row, content[row['source_item_id']])
        counts[fingerprint] += 1
        references[fingerprint] = dict(source_item_id=row['source_item_id'],
                                       revision_id=row['revisions'][-1]['revision_id'])
    return counts, references


def document_units(before, after, previous_seen, seen, previous_content, content):
    # Reconcile moved full content across anchor/position boundaries as well.
    # Keep an unchanged explicit anchor independent of unrelated nearby slots.
    grouped = set()
    endpoints = []
    for items, ids, hashes in [(before, previous_seen, previous_content), (after, seen, content)]:
        contents = defaultdict(set)
        for ident in ids:
            row = items[ident]
            if POSITION_KEY.search(row['item_key']):
                grouped.add(ident)
            # A reused explicit ID can now point to another visible paragraph.
            contents[row['evidence']['url'], policy_fingerprint(row, hashes[ident])].add(ident)
        endpoints.append(contents)
    old, new = endpoints
    moves, outgoing, incoming = [], set(), set()
    for key in old.keys() & new.keys():
        left, right = old[key] - new[key], new[key] - old[key]
        if left and right:
            moves.append((left, right))
            outgoing.update(left)
            incoming.update(right)
    # When a persistent explicit anchor changes text, retain its identity unless
    # both texts moved between keys or one side moved to/from a positional unit.
    positional = grouped.copy()
    movable = positional | (previous_seen ^ seen) | (outgoing & incoming)
    for left, right in moves:
        if (left | right) & positional:
            grouped.update(left | right)
        elif left & movable and right & movable:
            grouped.update((left | right) & movable)
    return grouped


def document_changes(before, after, previous_seen, seen, status, grouped, previous_day, previous_content):
    old_docs, new_docs = defaultdict(list), defaultdict(list)
    for items, ids, docs in [(before, previous_seen, old_docs), (after, seen, new_docs)]:
        for ident in ids & grouped:
            row = items[ident]
            docs[row['evidence']['url']].append(row)
    previous_urls = {before[k]['evidence']['url'] for k in previous_seen}
    historical_urls = {r['evidence']['url'] for r in before.values()}
    changes = []
    for url in sorted((old_docs.keys() | new_docs.keys()) & status['documents_seen'].keys()):
        if url not in previous_urls and url in historical_urls:
            continue
        old, old_refs = document_content(old_docs[url], previous_content)
        new, new_refs = document_content(new_docs[url], status['visible_content'])
        if old == new:
            continue
        event = dict(item_id='edge-policy-' + checksum(url), scope='policy_document',
                     type='changed' if url in previous_urls else 'added', url=url,
                     document_sha256=status['documents_seen'][url])
        if event['type'] == 'added':
            dates = [r.get('published_at') for r in new_docs[url]]
            event['origin'] = 'backfill' if all(d and d < previous_day for d in dates) else 'first_observed'
        for name, diff, refs in [('removed_content', old - new, old_refs), ('added_content', new - old, new_refs)]:
            event[name] = [dict(fingerprint=k, count=diff[k], **refs[k]) for k in sorted(diff)]
        changes.append(event)
    return changes


def validate_content(content, ids):
    if (not isinstance(content, dict) or content.keys() != set(ids)
            or any(not isinstance(h, str) or not re.fullmatch('[0-9a-f]{64}', h) for h in content.values())):
        raise ContractError('Invalid Edge visible content inventory')


def compare(before, after, status, retired, previous_cutoff, previous_seen, previous_content):
    """Keep semantic changes separate from compatibility evidence and revision tails."""
    if status['status'] != 'complete' or status['last_successful_cutoff'] != status['cutoff']:
        raise ContractError('Edge policy source is incomplete. Retain the last successful cutoff.')
    if instant(status['cutoff']) <= instant(previous_cutoff):
        raise ContractError('Edge policy window must advance')
    previous_day = instant(previous_cutoff).astimezone(ZoneInfo('Asia/Seoul')).date().isoformat()
    seen = set(status['observed_ids'])
    if before.keys() - after.keys() or seen - after.keys() or not seen:
        raise ContractError('Missing policy history or observations')
    content = status.get('visible_content')
    if content is not None:
        validate_content(content, seen)
    comparable = previous_seen is not None and previous_content is not None and content is not None
    changes, grouped = [], set()
    if comparable:
        validate_content(previous_content, previous_seen)
        grouped = document_units(before, after, previous_seen, seen, previous_content, content)
        changes = document_changes(before, after, previous_seen, seen, status, grouped, previous_day, previous_content)
    evidence = []
    for ident, row in sorted(after.items()):
        old = before.get(ident, {})
        revisions = old.get('revisions', [])
        if row['revisions'][:len(revisions)] != revisions or old.keys() - row.keys():
            raise ContractError('Retained policy history changed')
        url = row['evidence']['url']
        if ident not in seen:
            if row != old:
                raise ContractError('Unobserved policy was modified')
            # Require a complete, successfully parsed version of the same document.
            # Omission of an entire page from an index cannot prove removal.
            if (comparable and ident in previous_seen and ident not in grouped
                    and url in status['documents_seen'] and old['record_status'] == 'parsed'):
                changes.append(dict(item_id=ident, type='removed', url=url,
                                    document_sha256=status['documents_seen'][url]))
            continue
        fields = {k: v for k, v in row.items() if k != 'revisions' and (k not in old or old[k] != v)}
        tail = row['revisions'][len(revisions):]
        if not fields and not tail and ident not in retired:
            continue
        patch = dict(item_id=ident, fields=fields, revisions=tail)
        if list(old) != list(row):
            patch['key_order'] = list(row)
        if (not comparable or ident in grouped
                or (old and ident not in previous_seen and ident not in retired)):
            evidence.append(patch)
            continue
        if not old or ident in retired:
            # Discovery time cannot establish a release date.
            patch.update(type='added', origin='restored' if ident in retired else 'first_observed')
            published = row.get('published_at')
            if published and published < previous_day and ident not in retired:
                patch['origin'] = 'backfill'
        elif policy_fingerprint(old, previous_content[ident]) != policy_fingerprint(row, content[ident]):
            patch['type'] = 'changed'
        else:
            evidence.append(patch)
            continue
        patch.update(url=url, document_sha256=row['evidence']['content_sha256'])
        changes.append(patch)
    return changes, evidence


def replay(items, retired, changes, evidence):
    """Return a new view. Keep removed records addressable by historical reports."""
    result, removed, applied = items.copy(), retired.copy(), set()
    for patch in changes + evidence:
        ident = patch['item_id']
        if ident in applied:
            raise ContractError('Duplicate item in Edge policy interval')
        applied.add(ident)
        if patch.get('scope') == 'policy_document':
            continue
        if patch.get('type') == 'removed':
            if ident not in items or ident in removed:
                raise ContractError('Unexpected removal')
            removed.add(ident)
        else:
            old = items.get(ident, {})
            result[ident] = dict(old, **patch['fields'], revisions=old.get('revisions', []) + patch['revisions'])
            if 'key_order' in patch:
                result[ident] = {k: result[ident][k] for k in patch['key_order']}
            if result[ident]['source_item_id'] != ident:
                raise ContractError('Policy patch identity mismatch')
            removed.discard(ident)
    return result, removed


def verified_run(run):
    state = read(run / 'state.json')
    if state['status'] not in ('partial', 'complete') or state['stages']['validate']['status'] != 'done':
        raise ContractError('Collection must finish data validation first')
    status, = [s for s in state['stages']['collect']['result']['browser'] if s['source_id'] == SOURCE]
    if status['status'] != 'complete' or status['last_successful_cutoff'] != status['cutoff']:
        raise ContractError('Incomplete Edge policy collection')
    expected = state['stages']['validate']['outputs']
    paths = (EDGE_POLICY,) if EDGE_POLICY in expected else EDGE_SHARDS
    for rel in paths:
        if expected.get(rel) != digest((run / 'validate' / rel).read_bytes()):
            raise ContractError('Edge policy snapshot differs from validated run')
    return status


def baseline(repository, sha):
    if not re.fullmatch('[0-9a-f]{40}', sha) or git(repository, 'rev-parse', sha + '^{commit}') != sha:
        raise ContractError('Pin the full baseline commit SHA')
    tree = git_tree(repository, sha)
    if edge_policy_paths(tree) != EDGE_SHARDS:
        raise ContractError('The commit must contain the complete shard migration')
    entries = {rel: tree[rel] for rel in EDGE_SHARDS}
    rows, hashes = [], {}
    for rel, data in read_blobs(repository, entries):
        values = json.loads(data)
        validate_edge_policy_shard(rel, values)
        rows.extend(values)
        hashes[rel] = digest(data)
    return indexed(rows), hashes


def blob(store, key):
    if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key):
        raise ContractError('Invalid content address')
    raw = (store / (key + '.json')).read_bytes()
    if digest(raw) != key:
        raise ContractError('Edge policy checksum mismatch')
    return json.loads(raw)


def save(store, value):
    raw = json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode()
    key = digest(raw)
    target = store / (key + '.json')
    if target.exists():
        blob(store, key)
    else:
        durable(target, raw)
    return key


def save_patches(store, patches):
    chunks, batch, size = [], [], 2
    for patch in patches:
        length = len(canonical(patch)) + 1
        if length + 2 > CHUNK_BYTES:
            raise ContractError('Policy patch exceeds the storage limit')
        if size + length > CHUNK_BYTES:
            chunks.append(save(store, batch))
            batch, size = [], 2
        batch.append(patch)
        size += length
    if batch:
        chunks.append(save(store, batch))
    return chunks


def patches(store, step, name):
    return [row for key in step.get(name, []) for row in blob(store, key)]


def restore(repository, store, tip):
    steps, visited = [], set()
    key = tip
    while True:
        if key in visited:
            raise ContractError('Repeated Edge policy interval')
        visited.add(key)
        step = blob(store, key)
        if step['source'] != SOURCE:
            raise ContractError('Unexpected source in Edge policy chain')
        if 'parent' not in step:
            break
        steps.append(step)
        key = step['parent']
    items, hashes = baseline(repository, step['baseline_commit'])
    if step['shards'] != hashes:
        raise ContractError('Baseline shard checksum mismatch')
    def verify_observations(receipt, records):
        if 'observations' in receipt:
            ids = blob(store, receipt['observations'])
            if not isinstance(ids, list) or ids != sorted(set(ids)) or set(ids) - records.keys():
                raise ContractError('Invalid policy observation inventory')
            if 'visible_content' in receipt:
                validate_content(blob(store, receipt['visible_content']), ids)

    verify_observations(step, items)
    retired = set()
    for update in reversed(steps):
        if update['since'] != step['cutoff'] or instant(update['cutoff']) <= instant(step['cutoff']):
            raise ContractError('Discontinuous Edge policy interval')
        changes = patches(store, update, 'changes')
        evidence = patches(store, update, 'evidence')
        items, retired = replay(items, retired, changes, evidence)
        if checksum(items) != update['result'] or checksum(sorted(retired)) != update['retired']:
            raise ContractError('Reconstructed policy inventory differs')
        verify_observations(update, items)
        step = update
    return items, retired, step


def shard_hashes(items):
    shards = edge_policy_shards([items[k] for k in sorted(items)])
    return {rel: digest(json_bytes(rows)) for rel, rows in shards.items()}


def verify_commit(repository, store, tip, commit):
    """Both consumers can use the existing contract only with identical source bytes."""
    items, retired, step = restore(repository, store, tip)
    _, committed = baseline(repository, commit)
    if shard_hashes(items) != committed:
        raise ContractError('Consumer commit differs from replayed Edge policy shards')
    return dict(commit=commit, tip=tip, cutoff=step['cutoff'], shards=len(committed),
                records=len(items), retired=len(retired))


def initialize(repository, store, commit, run):
    status = verified_run(run)
    items, hashes = baseline(repository, commit)
    expected = read(run / 'state.json')['stages']['validate']['outputs']
    if EDGE_POLICY in expected:
        # The last full collector run can precede the lossless shard migration.
        rows, _ = read_edge_policies(run / 'validate')
        expected = {p: digest(json_bytes(records)) for p, records in edge_policy_shards(rows).items()}
    if any(expected.get(p) != h for p, h in hashes.items()):
        raise ContractError('Baseline commit differs from last successful Edge source')
    receipt = dict(source=SOURCE, baseline_commit=commit, cutoff=status['cutoff'], shards=hashes)
    if 'observed_ids' in status:
        receipt.update(save_observations(store, status, items))
    return save(store, receipt)


def save_observations(store, status, items):
    ids = status['observed_ids']
    if len(set(ids)) != len(ids) or set(ids) - items.keys():
        raise ContractError('Invalid policy observation inventory')
    receipt = {'observations': save(store, sorted(ids))}
    if 'visible_content' in status:
        validate_content(status['visible_content'], ids)
        receipt['visible_content'] = save(store, {k: status['visible_content'][k] for k in sorted(ids)})
    return receipt


def advance(repository, store, parent, run):
    status = verified_run(run)
    items, retired, previous = restore(repository, store, parent)
    old, _ = read_edge_policies(run / 'base')
    if indexed(old) != items:
        raise ContractError('Collection did not start from the preceding policy state')
    after = indexed(read_edge_policies(run / 'validate')[0])
    previous_seen = set(blob(store, previous['observations'])) if 'observations' in previous else None
    content = blob(store, previous['visible_content']) if 'visible_content' in previous else None
    changes, evidence = compare(items, after, status, retired, previous['cutoff'], previous_seen, content)
    restored, removed = replay(items, retired, changes, evidence)
    if restored != after:
        raise ContractError('Policy replay differs from the full collector output')
    receipt = dict(source=SOURCE, parent=parent, since=previous['cutoff'], cutoff=status['cutoff'],
                   result=checksum(restored), retired=checksum(sorted(removed)))
    expected = read(run / 'state.json')['stages']['validate']['outputs']
    if shard_hashes(restored) != {rel: expected[rel] for rel in EDGE_SHARDS}:
        raise ContractError('Compatibility shard bytes differ from validated collection')
    receipt.update(save_observations(store, status, after))
    for name, rows in [('changes', changes), ('evidence', evidence)]:
        if rows:
            receipt[name] = save_patches(store, rows)
    return save(store, receipt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path.cwd())
    parser.add_argument('--store', type=Path, required=True, help='Private content-addressed directory')
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('--commit', required=True)
    init.add_argument('--run', required=True, type=Path)
    add = sub.add_parser('compare')
    add.add_argument('--parent', required=True)
    add.add_argument('--run', required=True, type=Path)
    check = sub.add_parser('restore')
    check.add_argument('--tip', required=True)
    check.add_argument('--output', type=Path, required=True, help='New private directory for compatibility shards')
    verify = sub.add_parser('verify-commit')
    verify.add_argument('--tip', required=True)
    verify.add_argument('--commit', required=True, help='Exact SHA used for dashboard or contract 1.2 export')
    args = parser.parse_args()
    root, store = args.repository.resolve(), args.store.resolve()
    require_external(root, store)
    store.mkdir(mode=0o700, parents=True, exist_ok=True)
    with run_lock(store):
        if args.command == 'verify-commit':
            print(json.dumps(verify_commit(root, store, args.tip, args.commit)))
            return
        if args.command == 'restore':
            output = args.output.resolve()
            require_external(root, output)
            require_external(store, output)
            if output.exists():
                raise ValueError('Restore destination must be new')
            items, _, _ = restore(root, store, args.tip)
            output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=output.parent) as temp:
                stage = Path(temp) / 'snapshot'
                for rel, rows in edge_policy_shards([items[k] for k in sorted(items)]).items():
                    durable(stage / rel, json_bytes(rows))
                os.rename(stage, output)
            return
        require_external(root, args.run.resolve())
        if args.command == 'init':
            tip = initialize(root, store, args.commit, args.run)
        else:
            tip = advance(root, store, args.parent, args.run)
        print(tip)


if __name__ == '__main__':
    main()
