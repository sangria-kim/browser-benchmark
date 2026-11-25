"""Durable per-browser results for a pinned scheduled collection."""
from datetime import timezone
import json
import re
import subprocess

from pipeline import daily_status
from pipeline.run_daily import digest, encoded, git, read
from pipeline.temporal import instant

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


def validate_detail(rel, detail):
    if (not isinstance(detail, dict) or set(detail) != {'version', 'scope', 'browsers', 'checksum'}
            or type(detail['version']) is not int or detail['version'] != 1
            or detail['checksum'] != value_hash({k: v for k, v in detail.items() if k != 'checksum'})):
        raise ValueError('Invalid browser detail or checksum')
    scope = detail['scope']
    if (not isinstance(scope, dict) or set(scope) != {'mode', 'cutoff', 'start', 'origin', 'registry', 'expected'}
            or scope['origin'] not in ('daily', 'baseline', 'backfill') or not valid(HASH, scope['registry'])
            or scope['cutoff'] != instant(scope['cutoff']).astimezone(timezone.utc).isoformat()
            or instant(scope['start']) > instant(scope['cutoff']) or rel != detail_path(scope['mode'], scope['cutoff'])):
        raise ValueError('Invalid browser status scope')
    if scope['mode'] == 'daily':
        daily_status.scheduled_cutoff(scope['cutoff'])
        if scope['origin'] != 'daily':
            raise ValueError('Invalid daily browser origin')
    groups = scope['expected']
    outcomes = detail['browsers']
    all_ids = set()
    if not isinstance(groups, dict) or not groups or not isinstance(outcomes, dict) or groups.keys() != outcomes.keys():
        raise ValueError('Invalid expected browsers')
    for browser, sources in groups.items():
        if (not re.fullmatch('[a-z]+', browser) or not isinstance(sources, list) or not sources
                or any(not valid(IDENT, s) for s in sources) or sources != sorted(set(sources))
                or all_ids.intersection(sources)):
            raise ValueError('Invalid expected sources')
        all_ids.update(sources)
        outcome = outcomes[browser]
        if outcome == dict(status='incomplete', change_count=None, collected_feature_count=None):
            continue
        if (not isinstance(outcome, dict) or set(outcome) != {'status', 'classification', 'effects',
                'change_count', 'collected_feature_count'} or outcome['status'] != 'complete'
                or not valid(HASH, outcome['classification']) or not isinstance(outcome['effects'], list)):
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


def check_registry(root, scope, *, historical=False):
    from pipeline.collect import registered_sources
    registry = root / 'config/sources.yml'
    if digest(registry.read_bytes()) != scope['registry']:
        if historical:
            return
        raise ValueError('Browser scope does not match the current registry fingerprint')
    sources, _ = registered_sources(root, None, mode=scope['mode'])
    expected = {}
    for source in sources:
        expected.setdefault(source['browser'], []).append(source['source_id'])
    if {name: sorted(ids) for name, ids in expected.items()} != scope['expected']:
        raise ValueError('Browser scope does not match the pinned registry')


def transition(old, new):
    if old['scope'] != new['scope'] or any(outcome['status'] == 'complete' and outcome != new['browsers'][browser]
            for browser, outcome in old['browsers'].items()):
        raise ValueError('Cannot change pinned scope or accepted browser outcome')


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


def check_delta(root, old, new, graph, changes):
    """Enforce ownership at the final writer, including legacy unpinned readers."""
    from pipeline.source_item_shards import EDGE_POLICY, EDGE_SHARDS
    accepted = [browser for browser, row in new['browsers'].items() if row['status'] == 'complete'
                and old['browsers'][browser]['status'] != 'complete']
    if len(accepted) != 1:
        raise ValueError('Publish exactly one newly verified browser')
    browser, = accepted
    selected = {}
    for effect in new['browsers'][browser]['effects']:
        path = f"data/source-items/{browser}/{effect['source_id']}.json"
        if path == EDGE_POLICY and (root / EDGE_SHARDS[0]).exists():
            path = EDGE_SHARDS[int(effect['item'][4:6], 16)]
        selected.setdefault(path, set()).add(effect['item'])
    selected_features = {e['feature_id'] for e in new['browsers'][browser]['effects']}
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


def check_effects(detail, index):
    features, items = index
    for browser, outcome in detail['browsers'].items():
        for effect in outcome.get('effects', []):
            feature = features.get(effect['feature_id'], {})
            ident, revision = effect['item'], effect['revision']
            item = items.get(ident, {})
            snapshot = next((r for r in item.get('revisions', []) if r['revision_id'] == revision), None)
            quote = feature.get('source_revision_excerpts', {}).get(revision)
            if (feature.get('browser') != browser or item.get('browser') != browser
                    or item.get('source_id') != effect['source_id'] or ident not in feature['source_item_ids']
                    or revision not in feature.get('source_revision_ids', {}).get(ident, [])
                    or snapshot is None or value_hash(snapshot) != effect['snapshot']
                    or effect['quote'] is not None and value_hash(quote) != effect['quote']):
                raise ValueError('Accepted browser evidence or feature link changed: ' + ident)


def validate_tree(root, *, graph=None, base=None):
    """Check durable effects against proposed data, including absent Git-tracked receipts."""
    from pipeline.normalize.storage import load_dataset

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

    tracked, modified = set(), set()
    # HEAD anchors local writes. CI passes the previous push or PR base so a deletion
    # already committed in the checked-out head is also visible.
    ref = base or 'HEAD'
    if base and not re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}', base):
        raise ValueError('Invalid browser status comparison commit')
    if (root / '.git').exists():
        head = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', '--quiet', 'HEAD'],
                              stdout=subprocess.DEVNULL, check=False)
        if head.returncode not in (0, 1) or base and head.returncode:
            raise ValueError('Cannot verify browser status comparison commit')
        if head.returncode == 0:
            names = git(root, 'ls-tree', '-r', '-z', '--name-only', ref, '--', FOLDER)
            tracked = set(filter(None, names.split('\0')))
            if not tracked <= paths:
                raise ValueError('Committed browser detail is missing: ' + ', '.join(sorted(tracked - paths)))
            if tracked:
                names = git(root, 'diff', '--name-only', '--no-renames', '-z', ref, '--', FOLDER)
                modified = set(filter(None, names.split('\0')))
    elif base:
        raise ValueError('Browser status comparison needs a Git checkout')
    if not paths:
        return

    index = effect_index(graph if graph is not None else load_dataset(root))
    checked_scopes = set()
    for rel in sorted(paths):
        detail = read(safe_path(root, rel))
        validate_detail(rel, detail)
        historical = rel in tracked
        if historical and rel in modified:
            previous = json.loads(git(root, 'show', ref + ':' + rel))
            validate_detail(rel, previous)
            transition(previous, detail)
            historical = previous == detail
        scope = detail['scope']
        key = (scope['mode'], scope['registry'], value_hash(scope['expected']), historical)
        if key not in checked_scopes:
            check_registry(root, scope, historical=historical)
            checked_scopes.add(key)
        check_aggregate(root, detail, {})
        check_effects(detail, index)
