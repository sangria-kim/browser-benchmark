"""Normalize explicit facts. Retain evidence; do not infer PM or availability."""
import copy
import re

from pipeline.deduplicate import canonical, digest, feature_identity, event_identity
from schemas.validate import ContractError, validate_record, validate_transition


def attach_accepted_chrome_history(bundle, accepted):
    """Attach accepted snapshots to a fresh, explicitly compared observation.

    This does not rewrite a source snapshot or infer an upstream change. An
    older observation, historical replay or unrelated revision is rejected.
    Normal prefix-preserving bundles still follow the original merge contract.
    """
    if not bundle.get('temporal_comparison'):
        return bundle
    from pipeline.temporal import instant
    result = copy.deepcopy(bundle)
    previous = {s['source_item_id']: s for s in accepted}
    for index, item in enumerate(result['source_items']):
        old = previous.get(item['source_item_id'])
        if not old or item['revisions'][:len(old['revisions'])] == old['revisions']:
            continue
        if (len(item['revisions']) != 1 or item['evidence']['source_revision'] != bundle['revision']
                or instant(item['observed_at']) < instant(old['observed_at'])):
            raise ContractError('Fresh endpoint observation required to attach accepted source history')
        snapshot = item['revisions'][0]
        existing = [r['revision_id'] for r in old['revisions']]
        if snapshot['revision_id'] in existing:
            if snapshot['revision_id'] != existing[-1]:
                raise ContractError('Endpoint observation would replay an older accepted snapshot')
            retained = copy.deepcopy(old)
            retained['temporal_scope'] = copy.deepcopy(item['temporal_scope'])
            result['source_items'][index] = retained
        else:
            item['revisions'] = copy.deepcopy(old['revisions']) + item['revisions']
            validate_transition('source_item', old, item)
    return result


def merge_sources(previous, incoming):
    """Accept only prefix-preserving source updates; never infer deletions."""
    result = {x['source_item_id']: copy.deepcopy(x) for x in previous}
    for item in incoming:
        validate_record('source_item', item)
        ident = item['source_item_id']
        if ident in result:
            # An older cached bundle is safe to replay, but cannot roll back facts.
            old = result[ident]
            if len(item['revisions']) < len(old['revisions']) and item['revisions'] == old['revisions'][:len(item['revisions'])]:
                continue
            validate_transition('source_item', old, item)
            if (item['revisions'] == old['revisions'] and old['lifecycle'] == 'removed'
                    and item['lifecycle'] != 'removed'):
                # Absence does not append a definition snapshot. Replaying that
                # old positive snapshot cannot undo an accepted removal.
                continue
        result[ident] = copy.deepcopy(item)
    return list(result.values())


def normalize_browser_facts(sources, facts, features=(), events=()):
    """Explicit fact adapter, independent of document parsing and PM selection.

    canonical_key must be a verified upstream identity or a reviewed mapping,
    not a title. Uninterpreted browser source units are deliberately omitted.
    Facts from translated/repeated notices share one event only when all
    semantic dimensions match. To record a recurrence, provide predecessor.
    """
    source_map = {s['source_item_id']: s for s in sources}
    catalog = {f['feature_id']: copy.deepcopy(f) for f in features}
    history = {e['event_id']: copy.deepcopy(e) for e in events}
    for fact in facts:
        evidence = [source_map[s] for s in fact['source_item_ids']]
        if not evidence or any(s['experiment_kind'] or s['record_status'] == 'unparsed' for s in evidence):
            raise ContractError('Feature facts need interpreted browser evidence')
        browser = evidence[0]['browser']
        if any(s['browser'] != browser for s in evidence):
            raise ContractError('Do not merge browser products')
        key = fact['canonical_key']
        fid = fact.get('feature_id') or feature_identity(browser, key)
        if fid in catalog and (catalog[fid]['browser'], catalog[fid]['canonical_key']) != (browser, key):
            raise ContractError('Feature ID collision')
        feature = catalog.setdefault(fid, dict(schema_version=2, feature_id=fid, browser=browser,
            canonical_key=key, title=fact['title'], aliases=[], source_item_ids=[], event_ids=[], lifecycle='unknown', legacy=False))
        before, after = fact.get('before'), fact.get('after')
        eid = event_identity(fid, fact['event_type'], fact.get('version'), fact['channel'], fact['platform'], before, after, fact.get('predecessor'))
        source_refs = [{k: v for k, v in s['evidence'].items() if k != 'excerpt'} for s in evidence]
        event = dict(schema_version=2, event_id=eid, feature_id=fid, browser=browser,
            event_type=fact['event_type'], version=fact.get('version'), channel=fact['channel'], platform=sorted(set(fact['platform'])),
            observed_at=min(s['observed_at'] for s in evidence), announced_at=fact.get('announced_at'), effective_at=fact.get('effective_at'),
            sources=source_refs, source_item_ids=list(fact['source_item_ids']), summary=fact['summary'], before=before, after=after,
            verification_status=fact['verification_status'], origin=fact.get('origin', 'daily'), correction_of=None, revision=1)
        if fact.get('predecessor'):
            event['previous_event_id'] = fact['predecessor']
        if eid in history:
            old = history[eid]
            for field in ('feature_id', 'event_type', 'version', 'channel', 'platform', 'before', 'after'):
                if old[field] != event[field]:
                    raise ContractError('Event ID collision')
            # Additional evidence does not create a second event or change its first observation.
            old['source_item_ids'] = sorted(set(old['source_item_ids'] + event['source_item_ids']))
            refs = {canonical(s): s for s in old['sources']}
            refs.update({canonical(s): s for s in event['sources']})
            old['sources'] = [refs[k] for k in sorted(refs)]
        else:
            history[eid] = event
        feature['source_item_ids'] = sorted(set(feature['source_item_ids'] + fact['source_item_ids']))
        if eid not in feature['event_ids']:
            feature['event_ids'].append(eid)
    return list(catalog.values()), list(history.values())


def source_definition(fact):
    semantic = fact['semantic']
    return dict(version=1, semantic_sha256=fact['semantic_sha256'], expression=semantic['definition'],
                options=copy.deepcopy(semantic.get('options', [])),
                unresolved_references=sorted(set(semantic.get('unresolved_references', []))))


def experiment_state(experiment):
    """A source semantic snapshot. Paths/commits/line offsets are evidence only."""
    fields = ('experiment_kind', 'symbol', 'flag_id', 'title', 'description', 'build_conditions', 'platform',
              'default_state', 'expiry_milestone', 'never_expire', 'ui_exposure', 'product_channel',
              'product_revision', 'installed_availability', 'verification_status', 'lifecycle', 'relationships', 'source_definition')
    return {k: copy.deepcopy(experiment[k]) for k in fields if k in experiment}


def normalize_chrome(bundle, sources, experiments=(), events=(), *, observed_at=None):
    if bundle.get('bundle_version') != 1:
        raise ContractError('Unsupported Chromium handoff version')
    source_map = {s['source_item_id']: s for s in sources}
    catalog = {x['experiment_id']: copy.deepcopy(x) for x in experiments}
    history = {x['event_id']: copy.deepcopy(x) for x in events}
    facts = {f['experiment_id']: f for f in bundle['facts']}
    if len(facts) != len(bundle['facts']):
        raise ContractError('Duplicate Chromium fact identity')
    from .corrections import parser_aliases
    identified = []
    for value in bundle['experiments']:
        record = copy.deepcopy(value)
        record['source_definition'] = source_definition(facts[value['experiment_id']])
        identified.append(record)
    corrected_ids = {a['target_id'] for a in parser_aliases(experiments, identified, [])}
    removals = {r['experiment_id']: r for r in bundle.get('removed_candidates', [])}
    for incoming in bundle['experiments']:
        current = copy.deepcopy(incoming)
        ident = current['experiment_id']
        if ident in removals and ident in catalog:
            continue
        fact = facts[ident]
        source = source_map[fact['source_item_id']]
        if (source['evidence']['content_sha256'] != fact['semantic_sha256']
                or source['evidence']['source_revision'] != fact['source_revision']):
            # An old private handoff must not roll a newer public catalog back.
            if ident in catalog:
                continue
            raise ContractError('Handoff fact is not the current source evidence')
        if digest(fact['semantic']) != fact['semantic_sha256']:
            raise ContractError('Handoff semantic hash mismatch')
        current['source_definition'] = source_definition(fact)
        old = catalog.get(ident)
        if old and old.get('source_definition'):
            accepted = {location['revision'] for location in old['source_locations'] if location['path'] == fact['definition']['path']}
            positions = {r['source_revision']: index for index, r in enumerate(source['revisions'])}
            if (len(accepted) != 1 or next(iter(accepted)) not in positions
                    or positions[fact['source_revision']] < positions[next(iter(accepted))]):
                # Also defend direct callers that pass an older source array
                # instead of merge_sources' current prefix-preserving output.
                continue
        if old and old['lifecycle'] == 'removed' and current['lifecycle'] != 'removed':
            last = history[old['event_ids'][-1]] if old['event_ids'] else None
            # The last definition snapshot can still be A after removal at B.
            # Require a new appended positive snapshot C, not replayed A.
            if (not last or last['event_type'] != 'removed'
                    or not _revision_follows(source, fact['source_revision'], last['previous_source_revision'])):
                continue
        if old:
            if (old['canonical_key'], old['experiment_kind']) != (current['canonical_key'], current['experiment_kind']):
                raise ContractError('Experiment ID collision')
            current['source_item_ids'] = sorted(set(old['source_item_ids'] + current['source_item_ids']))
            current['event_ids'] = list(old['event_ids'])
            current['aliases'] = sorted(set(old['aliases'] + current['aliases']))
            current['legacy'] = old['legacy'] or current['legacy']
        before, after = experiment_state(old) if old else None, experiment_state(current)
        same_revision = bool(old and any(loc['revision'] == fact['source_revision'] and loc['path'] == fact['definition']['path'] for loc in old['source_locations']))
        initial_projection = bool(old and 'temporal_scope' not in old and current.get('temporal_scope'))
        unchanged_projection = current.get('temporal_scope', {}).get('change') == 'unchanged'
        if before != after and not same_revision and ident not in corrected_ids and not initial_projection and not unchanged_projection:
            kind = 'baseline' if old is None else 'changed'
            if old and old['lifecycle'] == 'removed' and current['lifecycle'] != 'removed':
                kind = 'restored'
            elif old and old['default_state'] != current['default_state']:
                kind = 'default_change'
            elif old and (old['expiry_milestone'], old['never_expire']) != (current['expiry_milestone'], current['never_expire']):
                kind = 'expiry_change'
            prior_id = current['event_ids'][-1] if current['event_ids'] else None
            eid = event_identity(ident, kind, None, 'source', current['platform'], before, after, prior_id)
            event = dict(schema_version=2, event_id=eid, experiment_id=ident, experiment_kind=current['experiment_kind'],
                event_type=kind, source_item_ids=list(current['source_item_ids']), source_revision=fact['source_revision'],
                previous_source_revision=history[prior_id]['source_revision'] if prior_id else None,
                observed_at=source['observed_at'], effective_at=None, before=before, after=after,
                summary=('Source baseline: ' if old is None else 'Source definition changed: ') + (current['title'] or current['symbol'] or current['flag_id'] or ident),
                verification_status='source_only', origin=source['origin'], correction_of=None, revision=1)
            if 'temporal_scope' in current:
                event['temporal_scope'] = copy.deepcopy(current['temporal_scope'])
            if eid in history and history[eid] != event:
                raise ContractError('Experiment event ID collision')
            history[eid] = event
            current['event_ids'].append(eid)
        catalog[ident] = current
    # Absence in a partial run is never removal. Only a collector's verified
    # two-complete-tree diff is accepted, with matching scope and revisions.
    for removed in bundle.get('removed_candidates', []):
        _remove_experiment(removed, bundle, catalog, history, source_map, facts, observed_at)
    return list(catalog.values()), list(history.values())


def _revision_follows(source, candidate, previous):
    """Use append-only snapshot order, never dates or lexical Git SHA order."""
    positions = {r['source_revision']: index for index, r in enumerate(source['revisions'])}
    return candidate in positions and previous in positions and positions[candidate] > positions[previous]


def _remove_experiment(removed, bundle, catalog, history, sources, facts, observed_at):
    # No guessed field mapping: the collector's verified diff has a fixed shape.
    if not bundle.get('coverage', {}).get('complete'):
        raise ContractError('Removal needs complete collection evidence')
    ident = removed['experiment_id']
    old = catalog[ident]
    if old['lifecycle'] == 'removed':
        return
    if not observed_at or removed.get('proof') != 'absent_from_complete_pinned_tree':
        raise ContractError('Removal needs proof and an explicit observation time')
    if removed['scope_sha256'] != bundle['scope_sha256'] or removed['after_revision'] != bundle['revision']:
        raise ContractError('Removal scope/revision mismatch')
    source = sources[removed['source_item_id']]
    definition_path = facts[ident]['definition']['path']
    accepted_revisions = {location['revision'] for location in old['source_locations'] if location['path'] == definition_path}
    # The proof must extend the currently accepted positive definition. An old
    # A -> B proof cannot remove a later C restoration (or a same-meaning C
    # observation). Absence retains the A evidence, so hashes alone do not order
    # these states. The catalog's pinned location records accepted provenance.
    if (accepted_revisions != {removed['before_revision']}
            or source['evidence']['source_revision'] != removed['before_revision']):
        return
    before = experiment_state(old)
    old['lifecycle'] = 'removed'
    after = experiment_state(old)
    prior_id = old['event_ids'][-1] if old['event_ids'] else None
    eid = event_identity(ident, 'removed', None, 'source', old['platform'], before, after, prior_id)
    history[eid] = dict(schema_version=2, event_id=eid, experiment_id=ident, experiment_kind=old['experiment_kind'],
        event_type='removed', source_item_ids=list(old['source_item_ids']), source_revision=removed['after_revision'],
        previous_source_revision=removed['before_revision'], observed_at=observed_at, effective_at=None,
        before=before, after=after, summary='Source definition absent from verified complete tree: ' + ident,
        verification_status='source_only', origin='daily', correction_of=None, revision=1)
    old['event_ids'].append(eid)


def normalize_browser_catalog(sources, features=(), events=()):
    """Promote machine-identified ChromeStatus features, without launch claims.

    Other browser units remain eligible source-item assessment subjects. The
    minimal collector records do not encode enough semantics to infer a change
    type, supported before/after, or stable identity across unrelated notices.
    """
    catalog = {f['feature_id']: copy.deepcopy(f) for f in features}
    urls = {}
    for event in events:
        if event['browser'] != 'chrome':
            continue
        for ref in event['sources']:
            url = ref if isinstance(ref, str) else ref['url']
            urls.setdefault(url.rstrip('/'), set()).add(event['feature_id'])
    for source in sources:
        if source['source_id'] != 'chrome-platform-status' or source['record_status'] != 'parsed':
            continue
        key = source['item_key']
        url = 'https://chromestatus.com/feature/' + key
        if not re.fullmatch(r'[0-9]+', key) or source['evidence']['url'].rstrip('/') != url:
            continue
        canonical_key = 'chromestatus:' + key
        matches = urls.get(url, set())
        ident = next(iter(matches)) if len(matches) == 1 else feature_identity('chrome', canonical_key)
        if ident in catalog and len(matches) != 1 and (catalog[ident]['browser'], catalog[ident]['canonical_key']) != ('chrome', canonical_key):
            raise ContractError('Feature ID collision')
        feature = catalog.setdefault(ident, dict(schema_version=2, feature_id=ident, browser='chrome', canonical_key=canonical_key,
            title=source['title'] or canonical_key, aliases=[], source_item_ids=[], event_ids=[], lifecycle='unknown', legacy=False))
        feature['source_item_ids'] = sorted(set(feature['source_item_ids'] + [source['source_item_id']]))
    # Enterprise's official API repeats the same public feature across release
    # milestones. Match full source-unit hashes and upstream IDs, never titles
    # alone. Preserve every version-specific source and revision as evidence.
    status_owners = {}
    source_owners = {sid: f['feature_id'] for f in catalog.values() for sid in f['source_item_ids']}
    for source in sources:
        if source['source_id'] == 'chrome-platform-status' and source.get('item_content_sha256') and source['source_item_id'] in source_owners:
            identity = (source['item_key'], source['item_content_sha256'], source['title'])
            status_owners.setdefault(identity, set()).add(source_owners[source['source_item_id']])
    from urllib.parse import urlsplit, parse_qs
    for source in sources:
        if source['source_id'] != 'chrome-enterprise' or source['record_status'] != 'parsed' or not source.get('item_content_sha256'):
            continue
        url = urlsplit(source['evidence']['url'])
        if (url.scheme != 'https' or url.netloc != 'release-notes-787862449254.us-central1.run.app' or url.path != '/features'
                or not re.fullmatch(r'\d+', source['item_key']) or parse_qs(url.query).get('version') != [source['version']]):
            continue
        identity = (source['item_key'], source['item_content_sha256'], source['title'])
        matches = status_owners.get(identity, set())
        canonical_key = 'chrome-enterprise:' + source['item_key']
        ident = next(iter(matches)) if len(matches) == 1 else feature_identity('chrome', canonical_key)
        feature = catalog.setdefault(ident, dict(schema_version=2, feature_id=ident, browser='chrome', canonical_key=canonical_key,
            title=source['title'] or canonical_key, aliases=[], source_item_ids=[], event_ids=[], lifecycle='unknown', legacy=False))
        feature['source_item_ids'] = sorted(set(feature['source_item_ids'] + [source['source_item_id']]))
    return list(catalog.values())
