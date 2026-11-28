"""Durable per-browser results for a pinned scheduled collection."""
from datetime import timezone
import json
import re

from pipeline import daily_status
from pipeline.run_daily import digest, encoded, git, read, repository_head
from pipeline.temporal import instant, policy_day, window_start

FOLDER = 'data/browser-status'
MODES = ('daily', 'weekly_reconcile')
CATALOG = 'data/catalog/features/catalog.json'
IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]*')
HASH = re.compile(r'[a-f0-9]{64}')


def detail_path(mode, cutoff):
    if mode not in MODES:
        raise ValueError('Invalid browser status mode')
    if re.search(r'[.,]\d{6}\d*[1-9]', cutoff):
        raise ValueError('Browser cutoff exceeds microsecond precision')
    stamp = instant(cutoff).astimezone(timezone.utc).strftime('%Y-%m-%dT%H%M%S.%fZ')
    return f'{FOLDER}/{mode}/{stamp}.json'


def is_detail(path):
    return bool(re.fullmatch(r'data/browser-status/(daily|weekly_reconcile)/\d{4}-\d{2}-\d{2}T\d{6}\.\d{6}Z\.json', path))


def safe_path(root, rel):
    path = root / rel
    if path != path.resolve() or root not in path.parents or path.exists() and not path.is_file():
        raise ValueError('Unsafe browser publication path: ' + rel)
    return path


def value_hash(value):
    return digest(encoded(value))


def initial(scope):
    return dict(version=1, scope=scope, browsers={name: dict(status='incomplete', change_count=None,
                collected_feature_count=None) for name in scope['expected']})


def seal(detail):
    detail['checksum'] = value_hash({k: v for k, v in detail.items() if k != 'checksum'})
    return detail


def valid(pattern, value):
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def validate_scope(scope):
    if (not isinstance(scope, dict) or set(scope) != {'mode', 'cutoff', 'start', 'origin', 'registry', 'expected'}
            or scope['origin'] not in ('daily', 'baseline', 'backfill') or not valid(HASH, scope['registry'])
            or scope['cutoff'] != instant(scope['cutoff']).astimezone(timezone.utc).isoformat()
            or instant(scope['start']) > instant(scope['cutoff']) or scope['mode'] not in MODES):
        raise ValueError('Invalid browser status scope')
    if scope['mode'] == 'daily':
        daily_status.scheduled_cutoff(scope['cutoff'])
        if scope['origin'] != 'daily':
            raise ValueError('Invalid daily browser origin')
    groups = scope['expected']
    all_ids = set()
    if not isinstance(groups, dict) or not groups:
        raise ValueError('Invalid expected browsers')
    for browser, sources in groups.items():
        if (not re.fullmatch('[a-z]+', browser) or not isinstance(sources, list) or not sources
                or any(not valid(IDENT, s) for s in sources) or sources != sorted(set(sources))
                or all_ids.intersection(sources)):
            raise ValueError('Invalid expected sources')
        all_ids.update(sources)


def validate_detail(rel, detail):
    if (not isinstance(detail, dict) or set(detail) != {'version', 'scope', 'browsers', 'checksum'}
            or type(detail['version']) is not int or detail['version'] != 1
            or detail['checksum'] != value_hash({k: v for k, v in detail.items() if k != 'checksum'})):
        raise ValueError('Invalid browser detail or checksum')
    scope = detail['scope']
    validate_scope(scope)
    if rel != detail_path(scope['mode'], scope['cutoff']):
        raise ValueError('Invalid browser detail path')
    groups = scope['expected']
    outcomes = detail['browsers']
    if not isinstance(outcomes, dict) or groups.keys() != outcomes.keys():
        raise ValueError('Invalid browser outcome scope')
    for browser, sources in groups.items():
        outcome = outcomes[browser]
        if outcome == dict(status='incomplete', change_count=None, collected_feature_count=None):
            continue
        incomplete = isinstance(outcome, dict) and outcome.get('status') == 'incomplete'
        fields = {'status', 'effects', 'change_count', 'collected_feature_count'}
        if not incomplete:
            fields.add('classification')
        if (not isinstance(outcome, dict) or set(outcome) != fields or not isinstance(outcome['effects'], list)
                or incomplete and (not outcome['effects'] or outcome['change_count'] is not None
                                   or outcome['collected_feature_count'] is not None)
                or not incomplete and (outcome['status'] != 'complete' or not valid(HASH, outcome['classification']))):
            raise ValueError('Invalid accepted browser outcome')
        identities, changed, collected = set(), set(), set()
        for effect in outcome['effects']:
            if (not isinstance(effect, dict) or set(effect) != {'feature_id', 'source_id', 'item', 'revision',
                    'snapshot', 'quote', 'changed'} or effect['source_id'] not in sources
                    or not all(valid(IDENT, effect[k]) for k in ('feature_id', 'item', 'revision'))
                    or not valid(HASH, effect['snapshot']) or type(effect['changed']) is not bool
                    or effect['quote'] is not None and not valid(HASH, effect['quote'])):
                raise ValueError('Invalid accepted browser effect')
            key = effect['feature_id'], effect['item'], effect['revision']
            if key in identities:
                raise ValueError('Duplicate browser effect')
            identities.add(key)
            collected.add(key[0])
            if effect['changed']:
                changed.add(key[0])
        if incomplete:
            continue
        for key, ids in [('change_count', changed), ('collected_feature_count', collected)]:
            if type(outcome[key]) is not int or outcome[key] != len(ids):
                raise ValueError('Invalid browser feature total')


def read_current(root, rel):
    """A committed outcome remains the minimum accepted result in this checkout."""
    target = safe_path(root, rel)
    value = read(target) if target.exists() else None
    if target.exists():
        validate_detail(rel, value)
    if (root / '.git').exists() and git(root, 'ls-tree', 'HEAD', '--', rel):
        if value is None:
            raise ValueError('Committed browser detail is missing')
        committed = json.loads(git(root, 'show', 'HEAD:' + rel))
        validate_detail(rel, committed)
        transition(committed, value)
    return value


def registry_facts(root, mode):
    return registry_snapshot((root / 'config/sources.yml').read_bytes(), mode)


def registry_snapshot(raw, mode):
    from pipeline.collect import select_sources
    registry = json.loads(raw)
    groups = {}
    for source in select_sources(registry, None, mode=mode):
        groups.setdefault(source['browser'], []).append(source['source_id'])
    return digest(raw), registry['baseline'], {k: sorted(v) for k, v in groups.items()}


def check_window(scope, policy):
    mode = scope['mode']
    start = window_start(mode, scope['cutoff'], policy['backfill_since'], policy.get('daily_window_days', 30))
    if re.search(r'[.,]\d{6}\d*[1-9]', scope['start']) or instant(scope['start']) != instant(start):
        if mode == 'weekly_reconcile':
            raise ValueError('Weekly result requires the full registered history')
        raise ValueError('Daily window differs from the registered policy')


def check_registry(root, scope, *, historical=False, facts=None, continuing=False, registry_ref=None):
    fingerprint, policy, expected = facts if facts is not None else registry_facts(root, scope['mode'])
    if fingerprint != scope['registry']:
        if historical:
            return
        from pipeline.registry_compatibility import compatible
        if not continuing or not compatible(root, scope['registry'], fingerprint, ref=registry_ref):
            raise ValueError('Browser scope does not match the current registry fingerprint')
    check_window(scope, policy)
    if expected != scope['expected']:
        raise ValueError('Browser scope does not match the pinned registry')


def check_continuation(root, previous, current):
    """Allow new observations under the same contract; retain the original scope."""
    validate_scope(previous)
    validate_scope(current)
    if dict(previous, registry=current['registry']) != current:
        raise ValueError('Browser scope differs from the first published result')
    check_registry(root, current)
    check_registry(root, previous, continuing=True)


def effect_key(effect):
    return effect['feature_id'], effect['item'], effect['revision']


def merge_effects(previous, additions):
    # Retain the original product-change decision when a retry sees the stored link.
    effects = {effect_key(effect): effect for effect in previous}
    for effect in additions:
        key = effect_key(effect)
        old = effects.get(key)
        if old is None:
            effects[key] = effect
        elif dict(effect, changed=old['changed']) != old:
            raise ValueError('Cannot replace a confirmed feature effect')
    return [effects[key] for key in sorted(effects)]


def transition(old, new):
    if old['scope'] != new['scope'] or any(outcome['status'] == 'complete' and outcome != new['browsers'][browser]
            for browser, outcome in old['browsers'].items()):
        raise ValueError('Cannot change pinned scope or accepted browser outcome')
    for name, outcome in old['browsers'].items():
        current = {effect_key(e): e for e in new['browsers'][name].get('effects', [])}
        if any(current.get(effect_key(e)) != e for e in outcome.get('effects', [])):
            raise ValueError('Cannot remove a previously published item effect')


def aggregate(detail):
    outcomes = detail['browsers'].values()
    if any(outcome['status'] != 'complete' for outcome in outcomes):
        return None, None
    return tuple(sum(outcome[key] for outcome in outcomes) for key in ('change_count', 'collected_feature_count'))


def check_aggregate(root, detail, changes):
    if detail['scope']['mode'] == 'daily':
        rel, expected = daily_status.receipt(detail['scope']['cutoff'], *aggregate(detail))
        path = safe_path(root, rel)
        actual = changes[rel] if rel in changes else read(path) if path.exists() else None
        if actual != expected:
            raise ValueError('Daily aggregate differs from browser outcomes')


def check_delta(root, old, new, graph, changes, *, item_effect=None):
    """Enforce ownership at the final writer, including legacy unpinned readers."""
    from pipeline.source_item_shards import EDGE_POLICY, EDGE_SHARDS
    if item_effect is None:
        accepted = [name for name, row in new['browsers'].items() if row != old['browsers'][name]]
        if len(accepted) != 1 or new['browsers'][accepted[0]]['status'] != 'complete':
            raise ValueError('Publish exactly one newly verified browser')
        browser, = accepted
        effects = new['browsers'][browser]['effects']
    else:
        browser, = [name for name, ids in new['scope']['expected'].items() if item_effect['source_id'] in ids]
        prior = old['browsers'][browser]
        if prior['status'] != 'incomplete':
            raise ValueError('Cannot publish an item after browser completion')
        expected = dict(prior, effects=merge_effects(prior.get('effects', []), [item_effect]))
        if new['browsers'] != dict(old['browsers'], **{browser: expected}):
            raise ValueError('Item publication can only append its confirmed effect')
        effects = [item_effect]
    selected = {}
    for effect in effects:
        path = f"data/source-items/{browser}/{effect['source_id']}.json"
        if path == EDGE_POLICY and (root / EDGE_SHARDS[0]).exists():
            path = EDGE_SHARDS[int(effect['item'][4:6], 16)]
        selected.setdefault(path, set()).add(effect['item'])
    selected_features = {e['feature_id'] for e in effects}
    selected_items = set().union(*selected.values())
    advanced = set()
    for rel, rows in changes.items():
        target = safe_path(root, rel)
        prior = read(target) if target.exists() else []
        if rel == CATALOG:
            before = {r['feature_id']: r for r in prior}
            after = {r['feature_id']: r for r in rows}
            if not before.keys() <= after.keys() or not (after.keys() - before.keys()) <= selected_features:
                raise ValueError('Cannot add unclassified features or remove prior features')
            for fid, row in before.items():
                current = after[fid]
                if current == row:
                    continue
                if row['browser'] != browser:
                    raise ValueError('Cannot change another browser catalog row')
                if fid not in selected_features:
                    # A legacy reader of this browser may need its original display revision frozen.
                    if ({k: v for k, v in current.items() if k != 'source_revision_ids'} !=
                            {k: v for k, v in row.items() if k != 'source_revision_ids'}):
                        raise ValueError('Cannot change an unclassified feature')
                    pins = current.get('source_revision_ids', {})
                    old = row.get('source_revision_ids', {})
                    if any(pins.get(k) != v for k, v in old.items()) or not (pins.keys() - old.keys()) <= selected_items:
                        raise ValueError('Cannot change unrelated feature evidence')
            continue
        if rel not in selected:
            raise ValueError('Cannot change evidence outside the selected browser scope')
        before = {r['source_item_id']: r for r in prior}
        after = {r['source_item_id']: r for r in rows}
        if (not before.keys() <= after.keys() or any(before.get(ident) != after[ident]
                for ident in after.keys() - selected[rel])):
            raise ValueError('Cannot change an unselected evidence item')
        advanced.update(ident for ident in selected[rel] if ident in before
                        and before[ident]['revisions'][-1] != after[ident]['revisions'][-1])
    if advanced:
        for kind in ('feature', 'feature_event', 'experiment', 'experiment_event'):
            for owner in graph[kind]:
                if (owner.get('browser') != browser and
                        (advanced.intersection(owner['source_item_ids']) - owner.get('source_revision_ids', {}).keys())):
                    raise ValueError('Unpinned evidence has an outside owner; use full reconciliation')


def effect_index(graph):
    return ({r['feature_id']: r for r in graph['feature']}, {r['source_item_id']: r for r in graph['source_item']})


def displayed_excerpt(feature, snapshot):
    quote = feature.get('source_revision_excerpts', {}).get(snapshot['revision_id'])
    return quote if quote is not None else snapshot.get('evidence', {}).get('excerpt') or ''


def check_effects(detail, index):
    features, items = index
    for browser, outcome in detail['browsers'].items():
        for effect in outcome.get('effects', []):
            feature = features.get(effect['feature_id'], {})
            ident, revision = effect['item'], effect['revision']
            item = items.get(ident, {})
            snapshot = next((r for r in item.get('revisions', []) if r['revision_id'] == revision), None)
            if (feature.get('browser') != browser or item.get('browser') != browser
                    or item.get('source_id') != effect['source_id'] or ident not in feature['source_item_ids']
                    or revision not in feature.get('source_revision_ids', {}).get(ident, [])
                    or snapshot is None or value_hash(snapshot) != effect['snapshot']):
                raise ValueError('Accepted browser evidence or feature link changed: ' + ident)
            # Earlier receipts used null when the revision supplied the displayed text.
            expected = effect['quote'] or value_hash(displayed_excerpt({}, snapshot))
            if value_hash(displayed_excerpt(feature, snapshot)) != expected:
                raise ValueError('Accepted browser evidence or feature link changed: ' + ident + ' (excerpt)')


def receipt_inventory(root, head):
    """Check current names and file types in both the working tree and the committed tip."""
    from pipeline import receipt_history, weekly_status

    receipt_history.check_spelling((p.name for p in root.iterdir()), {'data'})
    data = root / 'data'
    if data.is_symlink() or data.exists() and not data.is_dir():
        raise ValueError('Invalid data directory')
    if data.exists():
        receipt_history.check_spelling((p.name for p in data.iterdir()), receipt_history.FOLDER_NAMES)
    folder = root / FOLDER
    if folder.is_symlink() or folder.exists() and not folder.is_dir():
        raise ValueError('Invalid browser status folder')
    paths = set()
    if folder.exists():
        for directory in folder.iterdir():
            if directory.is_symlink() or not directory.is_dir() or directory.name not in MODES:
                raise ValueError('Invalid browser status directory')
            for path in directory.iterdir():
                rel = path.relative_to(root).as_posix()
                if not is_detail(rel) or not safe_path(root, rel).is_file():
                    raise ValueError('Invalid browser status file')
                paths.add(rel)

    weekly_folder = root / weekly_status.FOLDER
    if weekly_folder.is_symlink() or weekly_folder.exists() and not weekly_folder.is_dir():
        raise ValueError('Invalid whole weekly status folder')
    if weekly_folder.exists():
        for path in weekly_folder.iterdir():
            rel = path.relative_to(root).as_posix()
            if not weekly_status.is_receipt(rel) or not safe_path(root, rel).is_file():
                raise ValueError('Invalid whole weekly status file')
            paths.add(rel)

    daily_paths = daily_status.tree_paths(root)
    all_paths = paths | daily_paths
    tracked = receipt_history.tracked_paths(root, head) if head else frozenset()
    for rel in all_paths - tracked:
        receipt_history.paths_for(rel)
    missing = tracked - all_paths
    if any(daily_status.status_path(rel) for rel in missing):
        raise ValueError('Committed daily status is missing: ' + ', '.join(sorted(missing)))
    if missing:
        raise ValueError('Committed browser detail is missing: ' + ', '.join(sorted(missing)))
    return paths, daily_paths, tracked


def validate_tree(root, *, graph=None, base=None, complete_history=False):
    """Check durable effects against proposed data, including absent Git-tracked receipts."""
    from pipeline.normalize.storage import load_dataset
    from pipeline import receipt_history, weekly_status, weekly_evidence

    ref = repository_head(root)
    paths, daily_paths, tracked = receipt_inventory(root, ref)
    if base and not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', base):
        raise ValueError('Invalid browser status comparison commit')
    if base or complete_history:
        receipt_history.verify(root, base=base, complete_history=complete_history)
    modified = set()
    if tracked:
        names = git(root, 'diff', '--name-only', '--no-renames', '-z', ref, '--', *receipt_history.FOLDERS)
        modified = set(filter(None, names.split('\0')))
    for rel in daily_paths:
        raw = safe_path(root, rel).read_bytes()
        daily_status.validate_receipt(rel, json.loads(raw))
        if rel in tracked and rel in modified:
            daily_status.check_committed(root, rel, raw, ref=ref, tracked=True)
    if not paths:
        return

    index = effect_index(graph if graph is not None else load_dataset(root))
    facts_by_mode = {}
    for rel in sorted(paths):
        detail = read(safe_path(root, rel))
        whole = weekly_status.is_receipt(rel)
        if whole:
            weekly_status.validate(rel, detail)
            if detail_path('weekly_reconcile', detail['scope']['cutoff']) in paths:
                raise ValueError('Conflicting whole and browser weekly publications')
            weekly_status.check_features(detail, index[0])
        else:
            validate_detail(rel, detail)
        historical = rel in tracked
        if (base and not whole and not historical and detail['scope']['mode'] == 'weekly_reconcile'
                and not weekly_status.guarded(detail['scope']['cutoff'])):
            raise ValueError('New unmarked historical weekly browser result has no authoritative base')
        if historical and rel in modified:
            if whole:
                raise ValueError('Cannot change an accepted whole weekly result')
            previous = json.loads(git(root, 'show', ref + ':' + rel))
            validate_detail(rel, previous)
            transition(previous, detail)
            historical = previous == detail
        scope = detail['scope']
        mode = scope['mode']
        if (mode == 'weekly_reconcile' and (base or complete_history) and ref and rel not in tracked
                and weekly_status.guarded(scope['cutoff'])):
            receipt_history.require_committed_repair(root, ref, receipt_history.paths_for(rel), tracked)
            weekly_evidence.check_committed(root, ref, policy_day(scope['start']), instant(scope['cutoff']))
        if mode == 'daily' and rel not in tracked:
            day, _ = daily_status.receipt(scope['cutoff'], None, None)
            if day in tracked and json.loads(git(root, 'show', ref + ':' + day))['status'] == 'complete':
                raise ValueError('Cannot add browser outcomes after the daily status is complete')
        if mode not in facts_by_mode:
            facts_by_mode[mode] = registry_facts(root, mode)
        check_registry(root, scope, historical=historical, facts=facts_by_mode[mode], continuing=rel in tracked)
        if not whole:
            check_aggregate(root, detail, {})
            check_effects(detail, index)
