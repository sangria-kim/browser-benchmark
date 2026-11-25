"""Collect registered browser updates privately and save classified features."""
import argparse
from collections import defaultdict
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import shutil
import re
import uuid

from pipeline.collectors.browser import BrowserCollector
from pipeline.collectors.browser.collector import EXCERPT_LIMIT, atomic_json
from pipeline.deduplicate import feature_identity
from pipeline.daily_status import add_receipt, classified_decisions, scheduled_cutoff
from pipeline.source_item_shards import EDGE_POLICY, EDGE_SHARDS
from pipeline.run_daily import digest, durable, encoded, git, pending_recovery, read, require_external, run_lock, store_changes
from pipeline.temporal import instant, window_start
from schemas.validate import load_config, validate_record, validate_transition


WEEKLY_ONLY_BROWSERS = frozenset({'brave', 'opera', 'vivaldi'})


def registered_sources(root, requested, *, mode):
    registry = load_config(root / 'config/sources.yml')
    validate_record('sources_config', registry)
    enabled = {s['source_id']: s for s in registry['sources'] if s['enabled']}
    missing = set(requested or ()) - enabled.keys()
    if missing:
        raise ValueError('Unknown or disabled sources: ' + ', '.join(sorted(missing)))
    if mode == 'daily':
        daily = {sid: source for sid, source in enabled.items() if source['browser'] not in WEEKLY_ONLY_BROWSERS}
        weekly_only = set(requested or ()) - daily.keys()
        if weekly_only:
            raise ValueError('Weekly-only sources require --mode manual for on-demand collection: '
                             + ', '.join(sorted(weekly_only)))
        enabled = daily
    return [s for key, s in enabled.items() if not requested or key in requested], registry['baseline']['backfill_since']


def source_path(source):
    return Path('data/source-items') / source['browser'] / (source['source_id'] + '.json')


FEATURE_CATALOG = "data/catalog/features/catalog.json"


def file_digest(path):
    return digest(path.read_bytes()) if path.exists() else None


def collect_sources(repository, private_dir, *, source_ids=None, cutoff=None, transport=None,
                    daily_status=False, mode=None, since=None,
                    origin=None, resume=False, reviewed_attributions=None, brave_release_metadata=None):
    """Collect only into this run's private workspace, checkpointing each source."""
    root, private = Path(repository).resolve(), Path(private_dir).resolve()
    require_external(root, private)
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    state_path, work = private / 'feature-run.json', private / 'work'
    with run_lock(private), run_lock(root) as writer:
        pending_recovery(root, writer)
        if work.is_symlink() or state_path.is_symlink():
            raise ValueError('Invalid collection workspace')
        if resume:
            state = read(state_path)
            if daily_status and cutoff:
                scheduled_cutoff(cutoff)
            if (state.get('run_id') != private.name or state['repository'] != str(root)
                    or state['status'] not in ('collecting', 'partial', 'complete')
                    or source_ids and sorted(source_ids) != sorted(state['sources'])
                    or cutoff and instant(cutoff) != instant(state['cutoff'])
                    or mode and mode != state['mode'] or origin and origin != state['origin']
                    or daily_status != ('daily_status' in state)):
                raise ValueError('Resume requires the same run, mode, origin, sources and cutoff')
            verify_workspace(work, state)
            if daily_status:
                check_status_inputs(root, state)
            source_ids, cutoff, mode, origin = state['sources'], state['cutoff'], state['mode'], state['origin']
            if since is None:
                since = state['manual_since']
        else:
            if state_path.exists() or work.exists():
                raise ValueError('Use a new private run directory or resume the existing run')
            cutoff = cutoff or datetime.now(timezone.utc).isoformat()
            mode = mode or ('daily' if daily_status else 'manual')
            origin = origin or 'daily'
        sources, policy_since = registered_sources(root, source_ids, mode=mode)
        registry = root / 'config/sources.yml'
        policy = load_config(registry)['baseline']
        days = policy.get('daily_window_days', 30)
        start = window_start(mode, cutoff, policy_since, days, since)
        if daily_status:
            if mode != 'daily' or origin != 'daily':
                raise ValueError('Daily status requires daily mode and daily origin')
            scheduled_cutoff(cutoff)
        code_root = Path(__file__).resolve().parents[1]
        # Standalone fixture/data directories have no Git history of their own.
        code_commit = git(code_root, 'rev-parse', 'HEAD')
        base_commit = git(root, 'rev-parse', 'HEAD') if (root / '.git').exists() else code_commit
        inputs = dict(registry=file_digest(registry), base_commit=base_commit, code_commit=code_commit,
                      start=start, cutoff=cutoff, mode=mode, origin=origin,
                      sources=[source['source_id'] for source in sources],
                      metadata=digest(encoded([reviewed_attributions or {}, brave_release_metadata])))
        config_hash = digest(encoded(inputs))
        if resume:
            if state['config_hash'] != config_hash:
                raise ValueError('Resume requires the original commit, window, registry and metadata inputs')
        else:
            state = dict(**inputs, repository=str(root), run_id=private.name, timezone='Asia/Seoul',
                         manual_since=since, config_hash=config_hash, workspace_id=uuid.uuid4().hex,
                         observed={}, source_results={})
            if daily_status:
                enabled, _ = registered_sources(root, None, mode=mode)
                state['daily_status'] = dict(enabled=sorted(s['source_id'] for s in enabled),
                                             registry=inputs['registry'], catalog=file_digest(root / FEATURE_CATALOG))
            work.mkdir(mode=0o700)
            durable(work / '.owner', state['workspace_id'].encode())
        if daily_status and not resume:
            check_status_inputs(root, state)
        state.update(status='collecting', complete=False)
        durable(state_path, encoded(state))
        for source in sources:
            sid = source['source_id']
            path = work / 'candidates' / source_path(source).name
            previous = state['source_results'].get(sid)
            try:
                if previous and previous.get('checkpoint_invalid'):
                    raise ValueError('Invalid source checkpoint; use a fresh run')
                if previous and previous['status'] == 'complete':
                    if path.is_symlink() or file_digest(path) != state['observed'][sid]:
                        raise ValueError('Completed candidate checkpoint checksum mismatch; use a fresh run')
                    continue
                collector = BrowserCollector(root, work / 'browser', transport, resume=resume,
                    reviewed_attributions=reviewed_attributions, brave_release_metadata=brave_release_metadata,
                    write_records=False)
                collector.window_start = None if mode == 'legacy' else start
                collector.policy_since = policy_since
                collector.checkpoint_context = digest(encoded([state['workspace_id'], config_hash, sid]))
                collector.attempt_seconds = policy.get('source_attempt_seconds', 900)
                result = collect_one(collector, source, state, private)
                rows = []
                for ident in sorted(collector.parsed_ids):
                    row = collector.records[ident]
                    if collector.publication_status(row['temporal_scope']['evidence_date']) in ('in_period', 'unknown'):
                        if ident in collector.classification_text:
                            row = dict(row, classification_text=collector.classification_text[ident])
                        rows.append(row)
                atomic_json(path, rows)
                state['observed'][sid] = file_digest(path)
                status = {k: result[k] for k in ('source_id', 'status', 'cutoff')}
                if result.get('errors'):
                    status['errors'] = result['errors']
            except Exception as error:
                state['observed'].pop(sid, None)
                status = dict(source_id=sid, cutoff=cutoff, status='partial',
                              errors=[dict(url=source['url'], reason=f'{type(error).__name__}: {error}')])
                # A damaged completed checkpoint is never replayed as a fresh snapshot.
                if previous and (previous.get('checkpoint_invalid') or previous['status'] == 'complete'):
                    status['checkpoint_invalid'] = True
            state['source_results'][sid] = status
            durable(state_path, encoded(state))
        statuses = list(state['source_results'].values())
        complete = bool(sources) and all(s['status'] == 'complete' for s in statuses)
        state.update(status='complete' if complete else 'partial', complete=complete)
        durable(state_path, encoded(state))
    return {'browser': statuses, 'complete': complete}


def collect_one(collector, source, state, private):
    if source['source_id'] == 'chrome-platform-status':
        # The first comparison facts for legacy summary-only records survive run cleanup.
        folder = private.parent / ('.browser-benchmark-comparison-' + str(os.getuid()))
        folder.mkdir(mode=0o700, exist_ok=True)
        if folder.is_symlink() or folder.stat().st_uid != os.getuid() or folder.stat().st_mode & 0o077:
            raise ValueError('Unsafe private comparison directory')
        baseline = folder / (digest(state['repository'].encode()) + '.json')
        if baseline.is_symlink():
            raise ValueError('Linked ChromeStatus comparison file')
        initial = read(baseline) if baseline.exists() else {}
        collector.chrome_status_baselines = dict(initial)
    result = collector.collect(source, state['cutoff'], state['start'][:10], state['origin'])
    if (source['source_id'] == 'chrome-platform-status' and result['status'] == 'complete'
            and collector.chrome_status_baselines != initial):
        durable(baseline, encoded(collector.chrome_status_baselines))
    return result


def verify_workspace(work, state):
    marker = work / '.owner'
    if work.is_symlink() or marker.is_symlink() or marker.read_text() != state['workspace_id']:
        raise ValueError('Collection workspace ownership changed')


def check_status_inputs(root, state):
    pinned = state['daily_status']
    enabled, _ = registered_sources(root, None, mode=state['mode'])
    if (pinned['registry'] != file_digest(root / 'config/sources.yml')
            or pinned['enabled'] != sorted(s['source_id'] for s in enabled)
            or pinned['catalog'] != file_digest(root / FEATURE_CATALOG)):
        raise ValueError('Daily status baseline changed; use a fresh collection')


def full_status_coverage(state):
    enabled = state['daily_status']['enabled']
    return (bool(enabled) and state.get('complete') is True and sorted(state['sources']) == enabled
            and sorted(state.get('observed', {})) == enabled)


def mark_incomplete(repository, private_dir):
    root, private = Path(repository).resolve(), Path(private_dir).resolve()
    require_external(root, private)
    with run_lock(private), run_lock(root) as writer:
        pending_recovery(root, writer)
        state_path, work = private / 'feature-run.json', private / 'work'
        if state_path.is_symlink():
            raise ValueError('Invalid collection state')
        state = read(state_path)
        if (state['repository'] != str(root) or state['origin'] != 'daily'
                or 'daily_status' not in state or state['status'] not in ('collecting', 'partial', 'complete', 'saving')):
            raise ValueError('No unfinished daily status run')
        verify_workspace(work, state)
        journal = work / 'transaction/publication.json'
        if state['status'] == 'saving' and journal.exists() and read(journal)['status'] == 'published':
            return
        changes, before = {}, {}
        add_receipt(root, changes, before, state['cutoff'], None, None)
        if changes:
            store_changes(root, private / 'status-transaction', changes, before, writer)


def save_features(repository, private_dir, decisions, *, allow_partial=False):
    """Close a classified run after its evidence and catalog are durable."""
    root, private = Path(repository).resolve(), Path(private_dir).resolve()
    require_external(root, private)
    catalog_path = FEATURE_CATALOG
    state_path, work = private / 'feature-run.json', private / 'work'
    with run_lock(private), run_lock(root) as writer:
        pending_recovery(root, writer)
        if state_path.is_symlink():
            raise ValueError('Invalid collection state')
        state = read(state_path)
        if state['repository'] != str(root) or work.is_symlink():
            raise ValueError('Invalid collection workspace')
        daily_status = 'daily_status' in state
        weekly = state.get('mode') == 'weekly_reconcile'
        if not (daily_status or weekly) and not isinstance(decisions, list):
            raise ValueError('Expected a list of classified features')
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
        if daily_status:
            scheduled_cutoff(state['cutoff'])
            if allow_partial or not full_status_coverage(state):
                raise ValueError('Daily status requires all pinned sources; use --record-incomplete')
            check_status_inputs(root, state)
        sources, _ = registered_sources(root, None, mode=state.get('mode'))
        if weekly and (allow_partial or not state['complete'] or state['registry'] != file_digest(root / 'config/sources.yml')
                       or set(state['observed']) != {source['source_id'] for source in sources}):
            raise ValueError('Weekly reconciliation requires complete coverage of all enabled sources')
        if daily_status or weekly:
            inventory = set()
            for source in sources:
                rel = source_path(source)
                path = work / 'candidates' / rel.name
                sid = source['source_id']
                if path.is_symlink() or not path.is_file():
                    raise ValueError('Private candidates are missing or unsafe')
                raw = path.read_bytes()
                if digest(raw) != state['observed'][sid]:
                    raise ValueError('Private candidates differ from the collected content')
                for row in json.loads(raw):
                    key = (sid, row['source_item_id'], row['revisions'][-1]['revision_id'])
                    if row['source_id'] != sid or key in inventory:
                        raise ValueError('Private candidate identity mismatch')
                    inventory.add(key)
            decisions = classified_decisions(decisions, inventory)
        observed = state['observed']
        requested = {}
        for choice in decisions:
            fields = ('source_item_id', 'revision_id', 'canonical_key', 'title')
            if not isinstance(choice, dict) or not all(isinstance(choice.get(k), str) and choice[k].strip() for k in fields):
                raise ValueError('Feature classification needs a source item, revision, key and title')
            if daily_status and choice.get('change_kind') not in ('product_change', 'evidence_only'):
                raise ValueError('Daily classification requires change_kind')
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
        existing_features = set(features)
        changed_features = set()
        collected_features = set()
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
                if prior is None and len(row['revisions']) != 1:
                    raise ValueError('Source history changed since collection. Collect again.')
                if prior:
                    # Another mode can save this exact content while classification is pending.
                    # Keep the first stored observation and its immutable revision timestamps.
                    if prior['revisions'][-1]['revision_id'] == revision:
                        row = prior
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
                    if daily_status:
                        fid = feature_identity(*key)
                        collected_features.add(fid)
                        kind = choice['change_kind']
                        if kind == 'evidence_only' and key not in existing_features:
                            raise ValueError('Evidence-only decisions require an existing feature')
                        prior_links = features.get(key, {}).get('source_revision_ids', {}).get(ident, ())
                        same_legacy_link = (key in features and ident in features[key]['source_item_ids']
                                            and not prior_links and prior is not None
                                            and prior['revisions'][-1]['revision_id'] == revision)
                        if kind == 'product_change' and revision not in prior_links and not same_legacy_link:
                            changed_features.add(fid)
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
        if daily_status:
            add_receipt(root, changes, before, state['cutoff'], len(changed_features), len(collected_features))
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
        parser.add_argument('--daily-status', action='store_true', help='Pin a 07:00 KST collection for daily status')
        parser.add_argument('--record-incomplete', action='store_true', help='Publish only the incomplete receipt')
    parser.add_argument('--allow-partial', action='store_true')
    parser.add_argument('--source', action='append')
    parser.add_argument('--cutoff')
    parser.add_argument('--mode', choices=['daily', 'weekly_reconcile', 'manual', 'legacy'])
    parser.add_argument('--since', help='Manual lower bound: KST date or timezone-aware timestamp')
    parser.add_argument('--origin', choices=['daily', 'baseline', 'backfill'])
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--brave-release-metadata', type=Path)
    parser.add_argument('--reviewed-attributions', type=Path)
    parser.add_argument('--save-features', type=Path, help='Save classified features from the private collection, offline')
    args = parser.parse_args()
    if daily:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', args.run_id):
            parser.error('Invalid run ID')
        args.private_dir = args.private_dir / args.run_id
    if daily and args.record_incomplete:
        if args.save_features or args.allow_partial or args.resume or args.daily_status or args.source or args.cutoff or args.mode or args.since or args.origin:
            parser.error('--record-incomplete uses only the existing run')
        mark_incomplete(args.repository, args.private_dir)
        print('Recorded incomplete daily status (or preserved an existing complete result).')
        return 0
    if args.save_features:
        if args.mode or args.since:
            parser.error('Save uses the pinned collection mode and range')
        if daily and args.daily_status:
            parser.error('--daily-status is set when collecting, not when saving')
        if (args.private_dir / 'work').resolve() in args.save_features.resolve().parents:
            parser.error('Keep the final classification outside the temporary work directory')
        count = save_features(args.repository, args.private_dir, load_config(args.save_features),
                              allow_partial=args.allow_partial)
        print(f'Saved evidence for {count} classified items.')
        return 0
    result = collect_sources(args.repository, args.private_dir, source_ids=args.source, cutoff=args.cutoff,
        mode=args.mode or (None if args.resume else 'daily' if daily else 'manual'), since=args.since,
        origin=args.origin, resume=args.resume, daily_status=daily and args.daily_status,
        reviewed_attributions=load_config(args.reviewed_attributions) if args.reviewed_attributions else None,
        brave_release_metadata=load_config(args.brave_release_metadata) if args.brave_release_metadata else None)
    print(json.dumps({'collection_complete': result['complete'], 'candidates': str(args.private_dir / 'work/candidates')}))
    return 0 if result['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
