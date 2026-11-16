"""Lossless legacy event migration and compatibility links.

Historical evidence does not establish a complete source inventory. Existing
release and Markdown documents stay byte-for-byte at their public paths.
"""
import copy
import hashlib
import json
import re
from pathlib import Path

from pipeline.deduplicate import canonical, digest, stable_id
from schemas.validate import ContractError, validate_record


def legacy_source(browser, key, title, summary, url, observed_at, *, channel='unknown', platform=None, version=None,
                  published_at=None, section=None, source_revision=None, experiment_kind=None, source_location=None):
    published_at = published_at[:10] if isinstance(published_at, str) else None
    source_revision = source_revision if isinstance(source_revision, str) and source_revision else None
    ident = stable_id('src-legacy', [browser, key, url])
    # This hashes retained evidence, never pretends to hash the unavailable page.
    excerpt = (summary or title or '')[:1200]
    content_hash = digest({'title': title, 'excerpt': excerpt, 'url': url, 'section': section, 'source_revision': source_revision})
    evidence = dict(url=url, section=section, source_revision=source_revision, content_sha256=content_hash,
                    observed_at=observed_at, excerpt=excerpt)
    row = dict(schema_version=2, source_item_id=ident, source_id='legacy', browser=browser, item_key=key,
        item_type=experiment_kind or 'unknown', title=title, summary=excerpt or None, channel=channel or 'unknown',
        platform=platform or ['unknown'], version=version, published_at=published_at, observed_at=observed_at,
        evidence=evidence, record_status='legacy', origin='legacy', lifecycle='unknown', experiment_kind=experiment_kind,
        source_location=source_location or url, source_symbol=None)
    snapshot = {k: copy.deepcopy(row[k]) for k in ('title', 'summary', 'evidence', 'published_at', 'observed_at')}
    snapshot.update(revision_id=stable_id('rev-legacy', [ident, content_hash, source_revision]), content_sha256=content_hash, source_revision=source_revision)
    row['revisions'] = [snapshot]
    validate_record('source_item', row)
    return row


def migrate_events(events, existing_features=()):
    sources, migrated = [], []
    features = {f['feature_id']: copy.deepcopy(f) for f in existing_features}
    for original in events:
        event = copy.deepcopy(original)
        if event['schema_version'] == 1:
            validate_record('legacy_feature_event', event)
            ids = []
            for index, ref in enumerate(event['sources']):
                ref = {'url': ref} if isinstance(ref, str) else ref
                source = legacy_source(event['browser'], event['event_id'] + ':source:' + str(index), event['summary'], event['summary'],
                    ref['url'], ref.get('observed_at', event['observed_at']), channel=event['channel'], platform=event['platform'],
                    version=event['version'], published_at=event['announced_at'], section=ref.get('section'), source_revision=ref.get('source_revision', event.get('source_revision')))
                sources.append(source)
                ids.append(source['source_item_id'])
            event.update(schema_version=2, source_item_ids=ids, before=None, after=None, origin='legacy', correction_of=None, revision=1)
        validate_record('feature_event', event)
        fid = event['feature_id']
        feature = features.setdefault(fid, dict(schema_version=2, feature_id=fid, browser=event['browser'], canonical_key=fid,
            title=event['summary'], aliases=[], source_item_ids=[], event_ids=[], lifecycle='unknown', legacy=True))
        if feature['browser'] != event['browser']:
            raise ContractError('Legacy feature ID belongs to two browser products')
        feature['source_item_ids'] = sorted(set(feature['source_item_ids'] + event['source_item_ids']))
        if event['event_id'] not in feature['event_ids']:
            feature['event_ids'].append(event['event_id'])
        migrated.append(event)
    return sources, list(features.values()), migrated


def compatibility_index(repository, features, experiments):
    root = Path(repository)
    feature_ids = {f['feature_id'] for f in features}
    flags = {}
    for experiment in experiments:
        if experiment['experiment_kind'] == 'flag_entry' and experiment['flag_id']:
            flags.setdefault(experiment['flag_id'], []).append(experiment['experiment_id'])
    index = {'index_version': 1, 'inventory_status': 'legacy', 'features': [], 'flags': [], 'releases': []}
    for path in sorted((root / 'features').rglob('*.md')):
        text = path.read_text()
        ids = sorted({x for x in re.findall(r'Feature ID:\s*`([^`]+)`', text) if x in feature_ids})
        index['features'].append({'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'feature_ids': ids})
    for path in sorted((root / 'experiments/chrome').glob('*.md')):
        if path.name == 'README.md':
            continue
        index['flags'].append({'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'flag_id': path.stem, 'experiment_ids': sorted(flags.get(path.stem, []))})
    for path in sorted((root / 'releases').rglob('*')):
        if path.is_file() and path.suffix in ('.json', '.md'):
            index['releases'].append({'path': str(path.relative_to(root)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'inventory_status': 'legacy'})
    return index


def migrate_flag_documents(repository, experiments, observed_at, previous_sources=()):
    """Retain all legacy flag document identities, including absent current flags.

    Exact flag IDs link only to unambiguous desktop registry owners, the scope
    explicitly declared by the old manifest. No title matching or iOS merge.
    Unknown lifecycle/default/expiry stays unknown. Detailed historical tables
    remain in their original documents through the compatibility index.
    """
    root = Path(repository)
    catalog = {e['experiment_id']: copy.deepcopy(e) for e in experiments}
    previous = {s['item_key']: s for s in previous_sources if s['source_id'] == 'legacy'}
    candidates = {}
    for e in catalog.values():
        if e['experiment_kind'] == 'flag_entry' and any(x['path'] == 'chrome/browser/about_flags.cc' for x in e['source_locations']):
            candidates.setdefault(e['flag_id'], []).append(e['experiment_id'])
    sources = []
    manifest_path = root / 'experiments/chrome/manifest.json'
    if not manifest_path.exists():
        return sources, list(catalog.values())
    manifest = json.loads(manifest_path.read_text())
    for path in sorted((root / 'experiments/chrome').glob('*.md')):
        if path.name == 'README.md':
            continue
        flag = path.stem
        key = 'flag-document:' + flag
        text = path.read_text()
        urls = re.findall(r'\]\((https://(?:github.com/chromium/chromium/commit/|chromium.googlesource.com/)[^\s)]+)\)', text)
        if not urls:
            # No product facts are invented; the old manifest supplies source evidence.
            revision = manifest['end_revision']
            url = 'https://github.com/chromium/chromium/blob/' + revision + '/chrome/browser/about_flags.cc'
        else:
            url = urls[-1]
            match = re.search(r'/commit/([0-9a-f]{40})', url)
            revision = match[1] if match else None
        source = previous.get(key) or legacy_source('chrome', key, flag, 'Legacy source registration evidence for ' + flag,
            url, observed_at, channel='source-main', source_revision=revision, experiment_kind='flag_entry',
            source_location='chrome/browser/about_flags.cc')
        sources.append(source)
        matches = candidates.get(flag, [])
        ident = matches[0] if len(matches) == 1 else stable_id('exp-legacy', ['flag_entry', 'chrome/browser/about_flags.cc', flag])
        if ident not in catalog:
            catalog[ident] = dict(schema_version=2, experiment_id=ident, experiment_kind='flag_entry', canonical_key='legacy:desktop-flag:' + flag,
                symbol=None, flag_id=flag, title=flag, description=None, source_item_ids=[], event_ids=[],
                source_locations=[dict(path='chrome/browser/about_flags.cc', revision=revision or 'legacy-evidence', line_start=None, line_end=None,
                    content_sha256=source['evidence']['content_sha256'])], build_conditions=[], platform=['unknown'], default_state=None,
                expiry_milestone=None, never_expire=None, ui_exposure='unknown', product_channel=None, product_revision=None,
                installed_availability='unknown', verification_status='source_only', lifecycle='unknown', relationships=[], aliases=[], legacy=True)
        catalog[ident]['source_item_ids'] = sorted(set(catalog[ident]['source_item_ids'] + [source['source_item_id']]))
        catalog[ident]['legacy'] = True
    return sources, list(catalog.values())


def resolve_predecessors(repository, events):
    """Resolve existing explicit predecessor IDs from retained monthly evidence.

    This is a reference repair, not title matching. Fail if evidence is absent or
    ambiguous. The original monthly PM judgment remains at its existing path.
    """
    result, sources = list(events), []
    ids = {e['event_id'] for e in result}
    needed = {}
    for event in result:
        ident = event.get('previous_event_id')
        if ident and ident not in ids:
            owners = needed.setdefault(ident, [])
            owners.append(event)
    if not needed:
        return sources, result
    records = {}
    for path in sorted((Path(repository) / 'experiments/chrome/monthly').glob('*.json')):
        data = json.loads(path.read_text())
        for row in data.get('events', []):
            if row.get('event_id') in needed:
                records.setdefault(row['event_id'], []).append(row)
    for ident, owners in needed.items():
        matches = records.get(ident, [])
        if len(matches) != 1 or len({o['feature_id'] for o in owners}) != 1:
            raise ContractError('Unresolved or ambiguous legacy predecessor: ' + ident)
        row, owner = matches[0], owners[0]
        source = legacy_source(owner['browser'], ident, row['summary'], row['summary'], row['source_url'], row['observed_at'],
            channel=row.get('channel'), platform=row.get('platform'), version=row.get('version'), source_revision=row.get('source_revision'))
        sources.append(source)
        result.append(dict(schema_version=2, event_id=ident, feature_id=owner['feature_id'], browser=owner['browser'],
            event_type='source_change', version=row.get('version'), channel=row.get('channel') or 'unknown', platform=row.get('platform') or ['unknown'],
            observed_at=row['observed_at'], announced_at=None, effective_at=None, sources=[{'url': row['source_url']}],
            source_item_ids=[source['source_item_id']], summary=row['summary'], before=None, after=None,
            verification_status=row['verification_status'], origin='legacy', correction_of=None, revision=1))
    return sources, result
