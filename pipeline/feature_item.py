"""Prepare a transaction for one classifier-confirmed feature. No network or receipt writes."""
from dataclasses import dataclass
import json
import re
from pathlib import Path

from pipeline import browser_status
from pipeline.deduplicate import AliasIndex, digest as value_digest, feature_identity
from pipeline.official_reference import accepts_url, normalize_url, reference_row
from pipeline.run_daily import digest
from pipeline.source_item_shards import EDGE_POLICY, EDGE_SHARDS
from pipeline.temporal import instant
from schemas.validate import validate_record, validate_transition


FACT_FIELDS = ('version', 'platform', 'channel', 'rollout_status')
ALIAS_PATH = 'data/aliases/corrections.json'
REQUEST_FIELDS = {'browser', 'feature_id', 'canonical_key', 'title', 'description', 'source_id', 'url', 'source_item_id',
                  'revision_id', 'change_kind', 'facts', 'evidence_quote', 'disposition'}
GENERIC_UPDATE = re.compile(
    r'(?:maintenance(?: release| update)?|(?:general |minor )?bug fixes?|'
    r'security (?:fixes|patch(?:es)?)|(?:browser )?version (?:bump|update)(?: to \d+(?:\.\d+)*)?|'
    r'(?:bug fixes and (?:performance|stability) improvements|security updates?|maintenance and bug fixes)|'
    r'(?:update[ds]? to |version |v)?\d+(?:\.\d+)+|단순 버전 (?:상승|업데이트)|일반 오류 수정)[.!]?', re.I)


@dataclass
class ItemDelta:
    changes: dict
    before: dict
    effect: dict


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Expected a non-empty feature identifier or description')
    return value.strip()


def confirmed_fact(value, slot):
    if value is None or value == [] or isinstance(value, str) and value.strip().lower() in ('', 'unknown'):
        return None
    if slot == 'platform':
        if not isinstance(value, list):
            raise ValueError('Feature platform must be a list')
        if any(not isinstance(p, str) for p in value):
            raise ValueError('Invalid platform value')
        return sorted({p.strip() for p in value if p.strip().lower() not in ('', 'unknown')}) or None
    return text(value)


def missing_facts(feature, sources_by_id):
    """Old parsed rows only supply feature-level facts their pinned citation identifies."""
    known = set(feature.get('feature_facts', {}))
    for ident in feature['source_item_ids']:
        row = sources_by_id.get(ident)
        if row is None:
            continue
        pins = feature.get('source_revision_ids', {}).get(ident, [])
        snapshot = next((s for s in reversed(row['revisions']) if not pins or s['revision_id'] == pins[-1]), None)
        if snapshot is None:
            continue
        quote = feature.get('source_revision_excerpts', {}).get(snapshot['revision_id'])
        # ChromeStatus has one upstream feature per record. Other publishers can
        # list unrelated products in one release, or supply platform defaults.
        specific = row['source_id'] == 'chrome-platform-status' and row['item_key'].isdigit()
        versioned_note = ((row['source_id'] == 'chrome-enterprise' and row['item_key'].isdigit())
                          or (row['source_id'] in ('firefox-beta', 'firefox-releases', 'firefox-ios', 'firefox-android')
                              and re.fullmatch(r'note-[0-9]+', row['item_key'])))
        for slot in ('version', 'platform', 'channel'):
            facts = snapshot if slot in snapshot or snapshot != row['revisions'][-1] else row
            value = confirmed_fact(facts.get(slot), slot)
            if not value:
                continue
            values = value if isinstance(value, list) else [value]
            cited = quote and all(re.search(r'(?<!\w)' + re.escape(v) + r'(?!\w)', quote, re.I) for v in values)
            if specific or cited or slot == 'version' and versioned_note:
                known.add(slot)
    return tuple(slot for slot in FACT_FIELDS if slot not in known)


def resolve_feature(catalog, request, aliases):
    browser = request['browser']
    by_id = {row['feature_id']: row for row in catalog}
    index = AliasIndex(aliases)

    def lookup(name, *, key=False):
        ids = {f['feature_id'] for f in catalog if f['browser'] == browser and
               (name == f['feature_id'] or name in f['aliases'] or key and name == f['canonical_key'])}
        resolved = index.resolve('feature', name)
        if name in by_id or resolved != name:
            ids.add(resolved)
        if key:
            derived = feature_identity(browser, name)
            if index.resolve('feature', derived) != derived:
                ids.add(index.resolve('feature', derived))
        ids = {index.resolve('feature', i) for i in ids}
        if len(ids) > 1 or any(i not in by_id or by_id[i]['browser'] != browser for i in ids):
            raise ValueError('Ambiguous or cross-browser feature identity')
        return by_id[ids.pop()] if ids else None

    key = text(request['canonical_key']) if 'canonical_key' in request else None
    identified = lookup(text(request['feature_id'])) if 'feature_id' in request else None
    if 'feature_id' in request and identified is None:
        raise ValueError('Unknown existing feature ID')
    keyed = lookup(key, key=True) if key else None
    if identified and key and keyed != identified:
        raise ValueError('Feature ID and canonical key disagree')
    existing = identified or keyed
    if existing:
        return existing, False
    if not key:
        raise ValueError('New features require a canonical key')
    ident = feature_identity(browser, key)
    if ident in by_id:
        raise ValueError('Feature ID collision')
    return dict(schema_version=2, feature_id=ident, browser=browser, canonical_key=key, title=text(request.get('title')),
                aliases=[], source_item_ids=[], event_ids=[], lifecycle='unknown', legacy=False), True


def selected_source(sources, request, candidate):
    if candidate is None and ('source_item_id' in request or 'revision_id' in request):
        raise ValueError('A selected source revision must be supplied from a verified observation')
    if candidate is not None:
        if (candidate['source_item_id'] != request.get('source_item_id') or candidate['record_status'] != 'parsed'
                or candidate['revisions'][-1]['revision_id'] != request.get('revision_id')
                or candidate['browser'] != request['browser']):
            raise ValueError('Selected item differs from the observed revision')
        url = normalize_url(candidate['evidence']['url'])
        if ('url' in request and normalize_url(request['url']) != url
                or request.get('source_id', candidate['source_id']) != candidate['source_id']):
            raise ValueError('Official URL or source differs from selected candidate')
        sid = candidate['source_id']
    else:
        url, sid = normalize_url(request.get('url')), request.get('source_id')
    matches = [s for s in sources if s['enabled'] and s['browser'] == request['browser']
               and (sid is None or sid == s['source_id']) and accepts_url(s, url, observed=candidate is not None)]
    if len(matches) != 1:
        raise ValueError('Official URL needs one matching registered publisher source')
    return matches[0], url


def choose_evidence(feature, rows, source, url, candidate, observed_at):
    if candidate is None:
        # Prefer the already confirmed citation of this feature, never a sibling
        # entry just because it uses the same document URL.
        for ident in feature['source_item_ids']:
            old = rows.get(ident)
            if old is None:
                continue
            pins = feature.get('source_revision_ids', {}).get(ident)
            for snap in reversed(old['revisions']):
                if (not pins or snap['revision_id'] in pins) and normalize_url(snap['evidence']['url']) == url:
                    return old, snap, snap['evidence']['excerpt']
        row = reference_row(source, url, observed_at)
        old = rows.get(row['source_item_id'])
        if old and (old['item_key'] != row['item_key'] or old['evidence']['url'] != url
                    or old['record_status'] != 'reference'):
            raise ValueError('Official reference identity collision')
        row = old or row
        return row, row['revisions'][-1], ''
    row = dict(candidate)
    passage = row.pop('classification_text', row['evidence']['excerpt'])
    validate_record('source_item', row)
    ident = row['source_item_id']
    prior = rows.get(ident)
    if not prior and len(row['revisions']) != 1:
        raise ValueError('Candidate source history is missing')
    if prior:
        head = row['revisions'][-1]
        if (row['item_key'], row['browser'], row['source_id']) != (prior['item_key'], prior['browser'], prior['source_id']):
            raise ValueError('Candidate source identity differs from the stored item')
        if head['revision_id'] == prior['revisions'][-1]['revision_id']:
            # Identical observations can carry a different acquisition time.
            def content(snapshot):
                return dict(snapshot, observed_at=None, evidence=dict(snapshot['evidence'], observed_at=None))
            if row['revisions'][:-1] != prior['revisions'][:-1] or content(head) != content(prior['revisions'][-1]):
                raise ValueError('Candidate differs from already confirmed revision')
            row = prior
        validate_transition('source_item', prior, row)
        if row is not prior and prior.get('temporal_scope') and (
                not row.get('temporal_scope') or instant(row['temporal_scope']['cutoff']) <
                instant(prior['temporal_scope']['cutoff'])):
            raise ValueError('Cannot replace a newer source window')
    return row, row['revisions'][-1], passage


def item_delta(root, request, sources, *, observed_at, candidate=None):
    """Return files, optimistic read hashes and a browser-status-compatible effect.

    The caller supplies registered sources and (when selected) the exact row from
    its verified private checkpoint. Call under the repository publication lock.
    """
    root = Path(root).resolve()
    if not isinstance(request, dict) or request.keys() - REQUEST_FIELDS or 'browser' not in request:
        raise ValueError('Invalid feature selection')
    if request.get('disposition', 'selected') != 'selected':
        raise ValueError('Only classifier-selected product features can be saved')
    if 'title' not in request and 'description' in request:
        request = dict(request, title=request['description'])
    if 'title' in request and GENERIC_UPDATE.fullmatch(text(request['title'])):
        raise ValueError('A maintenance or version-only update is not a product feature')
    source, url = selected_source(sources, request, candidate)
    before = {}

    def read_rows(rel):
        path = browser_status.safe_path(root, rel)
        raw = path.read_bytes() if path.exists() else None
        before[rel] = digest(raw) if raw is not None else None
        return json.loads(raw) if raw is not None else []

    catalog = read_rows(browser_status.CATALOG)
    original_catalog = value_digest(catalog)
    feature, new = resolve_feature(catalog, request, read_rows(ALIAS_PATH))
    kind = request.get('change_kind', 'product_change' if new else 'evidence_only')
    if kind not in ('evidence_only', 'product_change') or new and kind == 'evidence_only':
        raise ValueError('Invalid product change or evidence-only decision')
    sid = source['source_id']
    target = f"data/source-items/{source['browser']}/{sid}.json"
    if target == EDGE_POLICY and (root / EDGE_SHARDS[0]).exists():
        ident = candidate['source_item_id'] if candidate else reference_row(source, url, observed_at)['source_item_id']
        target = EDGE_SHARDS[int(ident[4:6], 16)]
    rows = {r['source_item_id']: r for r in read_rows(target)}
    row, snap, passage = choose_evidence(feature, rows, source, url, candidate, observed_at)
    validate_record('source_item', row)
    ident, revision = row['source_item_id'], snap['revision_id']
    prior = rows.get(ident)
    previously_linked = ident in feature['source_item_ids']
    if prior:
        old_head = prior['revisions'][-1]['revision_id']
        # Before appending a source revision, freeze legacy readers at their old head.
        display = next((r['revision_id'] for r in row['revisions'][len(prior['revisions']):]
                        if r.get('restores_revision_id') == old_head), old_head)
        for owner in catalog:
            if ident in owner['source_item_ids'] and ident not in owner.get('source_revision_ids', {}):
                owner.setdefault('source_revision_ids', {})[ident] = [display]
    pins = feature.setdefault('source_revision_ids', {}).setdefault(ident, [])
    already = previously_linked and revision in pins
    quote = request.get('evidence_quote')
    if quote not in (None, ''):
        if not isinstance(quote, str) or not quote.strip() or len(quote) > 1200 or quote not in passage:
            raise ValueError('Quote must match a passage from the selected revision')
        if already and quote != browser_status.displayed_excerpt(feature, snap):
            raise ValueError('Cannot replace a confirmed excerpt')
        feature.setdefault('source_revision_excerpts', {})[revision] = quote
    facts = request.get('facts', {})
    if not isinstance(facts, dict) or facts.keys() - set(FACT_FIELDS):
        raise ValueError('Unknown feature fact')
    normalized = {slot: confirmed_fact(value, slot) for slot, value in facts.items()}
    # For old-format features, respect prior feature-specific evidence in other
    # source files as well. Read only until all outstanding references are found.
    linked = {k: rows[k] for k in feature['source_item_ids'] if k in rows}
    outstanding = set(feature['source_item_ids']) - linked.keys()
    open_inputs = {slot for slot, value in normalized.items() if value is not None} - feature.get('feature_facts', {}).keys()
    if open_inputs and outstanding:
        for path in sorted((root / 'data/source-items' / feature['browser']).glob('*.json')):
            if not outstanding:
                break
            others = read_rows(path.relative_to(root).as_posix())
            linked.update((r['source_item_id'], r) for r in others if r['source_item_id'] in outstanding)
            outstanding -= linked.keys()
    missing = missing_facts(feature, linked)
    slots = feature.setdefault('feature_facts', {})
    for slot, value in normalized.items():
        if value is not None and slot in missing:
            slots[slot] = dict(value=value, source_item_id=ident, revision_id=revision)
    feature['source_item_ids'] = sorted(set(feature['source_item_ids']) | {ident})
    if revision not in pins:
        pins.append(revision)
    scope = row.get('temporal_scope') if candidate is not None else None
    if scope and (feature.get('temporal_scope', {}).get('status') != 'in_period' or scope['status'] == 'in_period'):
        feature['temporal_scope'] = scope
    if new:
        catalog.append(feature)
    validate_record('feature', feature)
    rows[ident] = row
    changes = {}
    if row is not prior:
        changes[target] = [rows[k] for k in sorted(rows)]
    if value_digest(catalog) != original_catalog:
        changes[browser_status.CATALOG] = sorted(catalog, key=lambda f: f['feature_id'])
    effect = dict(feature_id=feature['feature_id'], source_id=sid, item=ident, revision=revision,
                  snapshot=browser_status.value_hash(snap), quote=browser_status.value_hash(browser_status.displayed_excerpt(feature, snap)),
                  changed=kind == 'product_change' and not already)
    return ItemDelta(changes, before, effect)
