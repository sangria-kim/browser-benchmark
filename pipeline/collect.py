"""Collect registered browser updates privately and save classified features."""
import argparse
from collections import defaultdict
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import re
import uuid

from pipeline.collectors.browser import BrowserCollector
from pipeline.collectors.browser.collector import EXCERPT_LIMIT, atomic_json
from pipeline.deduplicate import feature_identity
from pipeline.source_item_shards import EDGE_POLICY, EDGE_SHARDS
from pipeline.run_daily import digest, durable, encoded, pending_recovery, read, require_external, run_lock, store_changes
from pipeline.temporal import instant
from schemas.validate import load_config, validate_record, validate_transition


def registered_sources(root, requested):
    registry = load_config(root / 'config/sources.yml')
    validate_record('sources_config', registry)
    enabled = {s['source_id']: s for s in registry['sources'] if s['enabled']}
    missing = set(requested or ()) - enabled.keys()
    if missing:
        raise ValueError('Unknown or disabled sources: ' + ', '.join(sorted(missing)))
    return [s for key, s in enabled.items() if not requested or key in requested], registry['baseline']['backfill_since']


def source_path(source):
    return Path('data/source-items') / source['browser'] / (source['source_id'] + '.json')


def collect_sources(repository, private_dir, *, source_ids=None, cutoff=None, transport=None,
                    origin='daily', resume=False, reviewed_attributions=None, brave_release_metadata=None):
    """Keep every observed unit private until the collection agent classifies it."""
    root, private = Path(repository).resolve(), Path(private_dir).resolve()
    require_external(root, private)
    sources, since = registered_sources(root, source_ids)
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_path = private / 'feature-run.json'
    work = private / 'work'
    with run_lock(private):
        if work.is_symlink() or state_path.is_symlink():
            raise ValueError('Invalid collection workspace')
        if resume:
            state = read(state_path)
            if (state['repository'] != str(root) or state['status'] not in ('collecting', 'partial', 'complete')
                    or source_ids and sorted(source_ids) != sorted(state['sources'])
                    or cutoff and cutoff != state['cutoff']):
                raise ValueError('Resume requires the same repository, sources and cutoff')
            verify_workspace(work, state)
            sources, since = registered_sources(root, state['sources'])
        else:
            if state_path.exists() or work.exists() or work.is_symlink():
                raise ValueError('Use a new private run directory or resume the existing run')
            cutoff = cutoff or datetime.now(timezone.utc).isoformat()
            instant(cutoff)
            state = dict(repository=str(root), cutoff=cutoff, origin=origin,
                         sources=[s['source_id'] for s in sources], workspace_id=uuid.uuid4().hex)
            work.mkdir(mode=0o700)
            durable(work / '.owner', state['workspace_id'].encode())
        config_hash = digest(encoded([sources, since, reviewed_attributions or {}, brave_release_metadata]))
        if resume and state['config_hash'] != config_hash:
            raise ValueError('Resume requires the original source registry and metadata inputs')
        state['config_hash'] = config_hash
        state['status'] = 'collecting'
        durable(state_path, encoded(state))
        observed, statuses = {}, []
        collector = BrowserCollector(root, work / 'browser', transport, resume=resume,
            reviewed_attributions=reviewed_attributions, brave_release_metadata=brave_release_metadata,
            write_records=False)
        for source in sources:
            result = collector.collect(source, state['cutoff'], since, state['origin'])
            statuses.append({k: result[k] for k in ('source_id', 'status', 'cutoff')})
            rows = []
            for ident in sorted(collector.parsed_ids):
                row = collector.records[ident]
                if row['temporal_scope']['status'] in ('in_period', 'unknown'):
                    if ident in collector.classification_text:
                        row = dict(row, classification_text=collector.classification_text[ident])
                    rows.append(row)
            path = work / 'candidates' / source_path(source).name
            atomic_json(path, rows)
            observed[source['source_id']] = digest(path.read_bytes())
        complete = all(s['status'] == 'complete' for s in statuses)
        state.update(status='complete' if complete else 'partial', complete=complete, observed=observed)
        durable(state_path, encoded(state))
    return {'browser': statuses, 'complete': complete}


def verify_workspace(work, state):
    marker = work / '.owner'
    if work.is_symlink() or marker.is_symlink() or marker.read_text() != state['workspace_id']:
        raise ValueError('Collection workspace ownership changed')


def save_features(repository, private_dir, decisions, *, allow_partial=False):
    """Close a classified run after its evidence and catalog are durable."""
    root, private = Path(repository).resolve(), Path(private_dir).resolve()
    require_external(root, private)
    if not isinstance(decisions, list):
        raise ValueError('Expected a list of classified features')
    sources, _ = registered_sources(root, None)
    catalog_path = 'data/catalog/features/catalog.json'
    state_path, work = private / 'feature-run.json', private / 'work'
    with run_lock(private), run_lock(root) as writer:
        pending_recovery(root, writer)
        if state_path.is_symlink():
            raise ValueError('Invalid collection state')
        state = read(state_path)
        if state['repository'] != str(root) or work.is_symlink():
            raise ValueError('Invalid collection workspace')
        signature = digest(encoded(decisions))
        txn = work / 'transaction'
        if state['status'] == 'saved':
            if state['decisions'] != signature:
                raise ValueError('This run already has a different final classification')
            return state['saved_items']
        if state['status'] == 'cleaning' and not work.exists():
            return finish_run(state_path, work, state, signature)
        verify_workspace(work, state)
        journal = txn / 'publication.json'
        if state['status'] == 'cleaning' or (state['status'] == 'saving' and journal.exists()
                                               and read(journal)['status'] == 'published'):
            return finish_run(state_path, work, state, signature)
        if state['status'] not in ('complete', 'partial', 'saving') or not (state['complete'] or allow_partial):
            raise ValueError('Finish collection or explicitly accept partial coverage')
        observed = state['observed']
        requested = {}
        for choice in decisions:
            fields = ('source_item_id', 'revision_id', 'canonical_key', 'title')
            if not isinstance(choice, dict) or not all(isinstance(choice.get(k), str) and choice[k].strip() for k in fields):
                raise ValueError('Feature classification needs a source item, revision, key and title')
            ident = choice['source_item_id']
            by_feature = requested.setdefault(ident, {})
            if choice['canonical_key'] in by_feature:
                raise ValueError('Repeated feature classification for this source item')
            by_feature[choice['canonical_key']] = choice
        before = {}

        def existing(path):
            target = root / path
            raw = target.read_bytes() if target.exists() else None
            before[path] = digest(raw) if raw is not None else None
            return json.loads(raw) if raw is not None else []

        catalog = existing(catalog_path)
        features = {(row['browser'], row['canonical_key']): row for row in catalog}
        unpinned_owners = defaultdict(list)
        for feature in catalog:
            for ident in feature['source_item_ids']:
                if ident not in feature.get('source_revision_ids', {}):
                    unpinned_owners[ident].append(feature)
        changes = {}
        for source in sources:
            sid = source['source_id']
            if not requested or sid not in observed:
                continue
            rel = source_path(source)
            raw = (work / 'candidates' / rel.name).read_bytes()
            if digest(raw) != observed[sid]:
                raise ValueError('Private candidates differ from the collected content')
            candidates = {r['source_item_id']: r for r in json.loads(raw)}
            for ident in sorted(requested.keys() & candidates.keys()):
                choices, row = requested.pop(ident).values(), candidates[ident]
                revision = row['revisions'][-1]['revision_id']
                if (any(choice['revision_id'] != revision for choice in choices)
                        or row['source_id'] != sid or row['browser'] != source['browser']
                        or row['record_status'] != 'parsed'):
                    raise ValueError('Classification does not match the observed source revision')
                excerpt = row['evidence']['excerpt']
                classification_text = row.pop('classification_text', excerpt)
                validate_record('source_item', row)
                target = rel.as_posix()
                if target == EDGE_POLICY and (root / EDGE_SHARDS[0]).exists():
                    target = EDGE_SHARDS[int(ident[4:6], 16)]
                if target not in changes:
                    changes[target] = {r['source_item_id']: r for r in existing(target)}
                prior = changes[target].get(ident)
                if prior:
                    validate_transition('source_item', prior, row)
                    prior_cutoff = prior.get('temporal_scope', {}).get('cutoff')
                    if prior_cutoff and instant(row['temporal_scope']['cutoff']) < instant(prior_cutoff):
                        raise ValueError('A newer source window is already saved')
                    # Older catalogs displayed the then-current source. Freeze that view before replacing it.
                    old_id = prior['revisions'][-1]['revision_id']
                    appended = row['revisions'][len(prior['revisions']):]
                    display_id = next((r['revision_id'] for r in appended if r.get('restores_revision_id') == old_id),
                                      old_id)
                    for owner in unpinned_owners[ident]:
                        owner.setdefault('source_revision_ids', {})[ident] = [display_id]
                changes[target][ident] = row
                for choice in choices:
                    quote = choice.get('evidence_quote', excerpt)
                    if len(excerpt) == EXCERPT_LIMIT and 'evidence_quote' not in choice:
                        raise ValueError('Choose an evidence_quote for each feature in a long item')
                    if not isinstance(quote, str) or not quote.strip() or len(quote) > 1200 or quote not in classification_text:
                        raise ValueError('The evidence_quote must be a passage of up to 1200 characters from this item')
                    key = (row['browser'], choice['canonical_key'])
                    if key not in features:
                        feature = dict(schema_version=2, feature_id=feature_identity(*key), browser=key[0],
                            canonical_key=key[1], title=choice['title'], aliases=[], source_item_ids=[],
                            event_ids=[], lifecycle='unknown', legacy=False)
                        features[key] = feature
                        catalog.append(feature)
                    feature = features[key]
                    # An undated citation cannot displace known in-period evidence.
                    if feature.get('temporal_scope', {}).get('status') != 'in_period' or row['temporal_scope']['status'] == 'in_period':
                        feature['temporal_scope'] = row['temporal_scope']
                    feature['source_item_ids'] = sorted(set(feature['source_item_ids']) | {ident})
                    revisions = feature.setdefault('source_revision_ids', {}).setdefault(ident, [])
                    if 'evidence_quote' in choice:
                        feature.setdefault('source_revision_excerpts', {})[revision] = quote
                    if revision not in revisions:
                        revisions.append(revision)
        if requested:
            raise ValueError('Classification refers to an unobserved source item')
        if changes:
            changes = {path: [rows[k] for k in sorted(rows)] for path, rows in changes.items()}
            changes[catalog_path] = sorted(catalog, key=lambda row: row['feature_id'])
        state.update(status='saving', decisions=signature, saved_items=len(decisions))
        durable(state_path, encoded(state))
        store_changes(root, txn, changes, before, writer)
        return finish_run(state_path, work, state, signature)


def finish_run(state_path, work, state, signature):
    if state['decisions'] != signature:
        raise ValueError('This run already has a different final classification')
    state.update(status='cleaning')
    durable(state_path, encoded(state))
    retired = work.with_name('.finished-' + state['workspace_id'])
    if work.exists():
        # Rename first so a crash part-way through removal cannot lose the owner marker of an active run.
        verify_workspace(work, state)
        work.rename(retired)
    if retired.exists():
        shutil.rmtree(retired)
    state.update(status='saved')
    state.pop('observed', None)
    durable(state_path, encoded(state))
    return state['saved_items']


def main(*, daily=False):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--private-dir', type=Path, required=True)
    if daily:
        parser.add_argument('--run-id', required=True)
    parser.add_argument('--allow-partial', action='store_true')
    parser.add_argument('--source', action='append')
    parser.add_argument('--cutoff')
    parser.add_argument('--origin', choices=['daily', 'baseline', 'backfill'], default='daily')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--brave-release-metadata', type=Path)
    parser.add_argument('--reviewed-attributions', type=Path)
    parser.add_argument('--save-features', type=Path, help='Save classified features from the private collection, offline')
    args = parser.parse_args()
    if daily:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', args.run_id):
            parser.error('Invalid run ID')
        args.private_dir = args.private_dir / args.run_id
    if args.save_features:
        if (args.private_dir / 'work').resolve() in args.save_features.resolve().parents:
            parser.error('Keep the final classification outside the temporary work directory')
        count = save_features(args.repository, args.private_dir, load_config(args.save_features),
                              allow_partial=args.allow_partial)
        print(f'Saved evidence for {count} classified items.')
        return 0
    result = collect_sources(args.repository, args.private_dir, source_ids=args.source, cutoff=args.cutoff,
        origin=args.origin, resume=args.resume,
        reviewed_attributions=load_config(args.reviewed_attributions) if args.reviewed_attributions else None,
        brave_release_metadata=load_config(args.brave_release_metadata) if args.brave_release_metadata else None)
    print(json.dumps({'collection_complete': result['complete'], 'candidates': str(args.private_dir / 'work/candidates')}))
    return 0 if result['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
