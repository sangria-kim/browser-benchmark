"""Publish a single selected feature while the collector continues its private survey."""
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from pipeline import browser_status, collect, daily_status, weekly_status
from pipeline.feature_enrichment import verified_candidate, verified_reference
from pipeline.feature_item import ALIAS_PATH, item_delta
from pipeline.official_reference import enterprise_archive_anchor, normalize_url
from pipeline.run_daily import digest, durable, encoded, pending_recovery, publication_commits, read, require_external, run_lock, store_changes
from pipeline.temporal import instant


def pin_inputs(root, work, state):
    # Scheduled runs already have a graph baseline. Unscheduled runs need one
    # for incremental writes without changing the legacy batch writer contract.
    paths = {ALIAS_PATH}
    if not state.get('browser_pin'):
        paths.add(browser_status.CATALOG)
        sources, _ = collect.registered_sources(root, state['sources'], mode=state['mode'])
        paths.update(collect.source_path(source).as_posix() for source in sources)
        if collect.EDGE_POLICY in paths:
            paths.update(collect.EDGE_SHARDS)
    before = {rel: collect.file_digest(browser_status.safe_path(root, rel)) for rel in paths}
    value = dict(workspace=state['workspace_id'], config=state['config_hash'], before=before)
    state['item_pin'] = browser_status.value_hash(value)
    durable(work / 'item-pin.json', encoded(value))


def manifest(state, sid):
    return dict(workspace=state['workspace_id'], config=state['config_hash'], source_id=sid,
                cutoff=state['cutoff'], result=state['source_results'][sid], candidates=state['observed'].get(sid))


def seal_source(work, state, sid):
    """Preserve selected source generations without copying large caches or candidate arrays."""
    info = manifest(state, sid)
    generation = browser_status.value_hash(info)
    folder = work / 'generations' / sid / generation
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    for kind, checksum in (('candidates', info['candidates']), ('enrichment', info['result'].get('enrichment_sha256')),
                           ('windows', info['result'].get('window_sha256'))):
        if checksum:
            path = browser_status.safe_path(work, f'{kind}/{sid}.json')
            target = browser_status.safe_path(work, f'generations/{sid}/{generation}/{kind}.json')
            if not target.exists():
                os.link(path, target)
            if collect.file_digest(target) != checksum:
                raise ValueError('Private source generation checksum mismatch')
    durable(folder / 'manifest.json', encoded(info))
    return generation


def checked_source(work, state, sid, *, windows=False):
    generation = state.get('generations', {}).get(sid)
    if (sid not in state['sources'] or not browser_status.valid(browser_status.IDENT, sid)
            or not browser_status.valid(browser_status.HASH, generation)):
        raise ValueError('No published source checkpoint for this selection')
    prefix = f'generations/{sid}/{generation}/'
    info = read(browser_status.safe_path(work, prefix + 'manifest.json'))
    result = info['result']
    if (info != manifest(state, sid) or browser_status.value_hash(info) != generation
            or result['source_id'] != sid or result['cutoff'] != state['cutoff']
            or result['status'] not in ('partial', 'complete') or result.get('checkpoint_invalid')):
        raise ValueError('Invalid selected source generation')
    if state.get('browser_pin'):
        checkpoint = read(browser_status.safe_path(work, f'checkpoints/{sid}.json'))
        if checkpoint != collect.source_checkpoint(state, sid):
            raise ValueError('Invalid selected source checkpoint')
    files = [('candidates', info['candidates']), ('enrichment', result.get('enrichment_sha256'))]
    if windows:
        if not result.get('window_sha256'):
            raise ValueError('A scheduled URL needs its source window checkpoint')
        files = [('windows', result['window_sha256'])]
    selected = []
    for kind, checksum in files:
        if checksum:
            target = browser_status.safe_path(work, prefix + kind + '.json')
            current = browser_status.safe_path(work, f'{kind}/{sid}.json')
            raw = target.read_bytes()
            if digest(raw) != checksum or not current.samefile(target) and collect.file_digest(current) != checksum:
                raise ValueError('Selected private source checksum mismatch')
            if kind in ('candidates', 'windows'):
                selected = json.loads(raw)
    return selected


def window_key(url):
    parts = urlsplit(normalize_url(url))
    def unreserved(match):
        char = chr(int(match[0][1:], 16))
        return char if char.isascii() and (char.isalnum() or char in '-._~') else match[0].upper()
    path = re.sub(r'%[0-9a-fA-F]{2}', unreserved, parts.path)
    query = tuple(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    if enterprise_archive_anchor(url) is not None:
        query = (('hl', 'en'),)
    return parts.netloc, path, query, unquote(parts.fragment)


def window_index(work, state, sid):
    bounds = {}
    for url, reason in checked_source(work, state, sid, windows=True).items():
        try:
            key = window_key(url)
        except ValueError:
            continue  # A parser's non-publisher diagnostic cannot match an official citation.
        bounds[key] = reason
    return bounds


def require_url_window(bounds, url, *, enrichment):
    key = window_key(url)
    for candidate in (key, (*key[:3], '')):
        reason = bounds.get(candidate)
        if reason == 'after_cutoff' or reason == 'before_period' and not enrichment:
            raise ValueError('Official URL is outside the scheduled source window: ' + url)


def check_prior_item_windows(root, work, state, browser, effects, inventory):
    # A fresh survey can learn a date which a former partial survey did not know.
    by_source = {}
    for effect in effects:
        if (effect['source_id'], effect['item'], effect['revision']) not in inventory:
            by_source.setdefault(effect['source_id'], []).append(effect)
    for sid, selected in by_source.items():
        bounds = window_index(work, state, sid)
        if not bounds:
            continue
        rel = f'data/source-items/{browser}/{sid}.json'
        files = {rel}
        if rel == collect.EDGE_POLICY and (root / collect.EDGE_SHARDS[0]).exists():
            files = {collect.EDGE_SHARDS[int(e['item'][4:6], 16)] for e in selected}
        urls = {r['source_item_id']: r['evidence']['url'] for name in files for r in read(browser_status.safe_path(root, name))}
        for effect in selected:
            require_url_window(bounds, urls[effect['item']], enrichment=not effect['changed'])


def checked_request(work, state, request):
    via_reference = request.get('reference_review', False)
    if type(via_reference) is not bool:
        raise ValueError('Invalid reference_review flag')
    selected = dict(request)
    selected.pop('reference_review', None)
    has_ids = 'source_item_id' in selected or 'revision_id' in selected
    if not has_ids and not via_reference:
        return selected, None
    sid = selected.get('source_id')
    if state is None or not isinstance(sid, str) or sid not in state['sources']:
        raise ValueError('A checkpoint selection needs its original run and source_id')
    candidates = checked_source(work, state, sid)
    if via_reference:
        return verified_reference(work, state, selected)
    if not selected.get('source_item_id') or not selected.get('revision_id'):
        raise ValueError('A checkpoint selection needs the observed item and revision')
    matches = [r for r in candidates if r['source_item_id'] == selected['source_item_id']]
    if not matches:
        return selected, verified_candidate(work, state, selected)
    if (len(matches) != 1 or matches[0]['source_id'] != sid
            or instant(matches[0]['temporal_scope']['cutoff']) != instant(state['cutoff'])
            or matches[0]['temporal_scope']['status'] not in ('in_period', 'unknown')):
        raise ValueError('Source candidate identity or collection window changed')
    return selected, matches[0]


def input_baseline(root, work, state, pin):
    path = browser_status.safe_path(work, 'item-pin.json')
    if not path.is_file():
        raise ValueError('Incremental publication needs a fresh collection at this cutoff')
    item_pin = read(path)
    keys = ('registry', 'base_commit', 'code_commit', 'start', 'cutoff', 'mode', 'origin', 'sources', 'metadata')
    if (browser_status.value_hash(item_pin) != state.get('item_pin') or item_pin['workspace'] != state['workspace_id']
            or item_pin['config'] != state['config_hash'] or state['config_hash'] != digest(encoded({k: state[k] for k in keys}))
            or state['registry'] != collect.file_digest(root / 'config/sources.yml')
            or publication_commits(root) != (state['code_commit'], state['base_commit'])):
        raise ValueError('Item publication baseline changed; use a fresh collection')
    before = dict(item_pin['before'])
    if pin:
        _, scheduled = collect.browser_baseline(root, work, state, pin)
        before.update(scheduled)
    else:
        folder = work / 'item-transactions'
        if folder.is_symlink():
            raise ValueError('Unsafe item transaction directory')
        for txn in sorted(folder.iterdir()) if folder.exists() else ():
            journal_file = browser_status.safe_path(work, txn.relative_to(work).as_posix() + '/publication.json')
            if not journal_file.exists():
                continue
            journal = read(journal_file)
            if journal['status'] != 'published':
                continue
            marker = read(browser_status.safe_path(txn, 'scope.json'))
            saved = read(browser_status.safe_path(txn, 'state.json'))
            if (marker['pin'] != state['item_pin'] or saved['repository'] != str(root)
                    or set(journal['files']) != set(saved['inputs'])):
                raise ValueError('Invalid manual item publication journal')
            for rel, change in journal['files'].items():
                if (rel not in before or before[rel] != change['before'] or change['before'] != saved['inputs'][rel]
                        or change['after'] != saved['stages']['validate']['outputs'][rel]):
                    raise ValueError('Broken manual item publication chain')
                before[rel] = change['after']
    before['config/sources.yml'] = state['registry']
    if any(collect.file_digest(browser_status.safe_path(root, rel)) != checksum for rel, checksum in before.items()):
        raise ValueError('Item publication baseline changed; use a fresh collection')
    return before


def append_outcome(root, scope, browser, delta):
    rel = browser_status.detail_path(scope['mode'], scope['cutoff'])
    target = browser_status.safe_path(root, rel)
    detail = browser_status.read_current(root, rel)
    if detail is None:
        detail = browser_status.initial(scope)
    elif detail['scope'] != scope:
        raise ValueError('Item scope differs from the first accepted publication')
    else:
        browser_status.check_aggregate(root, detail, {})
    outcome = detail['browsers'][browser]
    if outcome['status'] == 'complete':
        raise ValueError('Cannot append an item to a completed browser')
    outcome['effects'] = browser_status.merge_effects(outcome.get('effects', []), [delta.effect])
    delta.before[rel] = collect.file_digest(target)
    delta.changes[rel] = browser_status.seal(detail)
    if scope['mode'] == 'daily':
        daily_status.add_receipt(root, delta.changes, delta.before, scope['cutoff'], None, None)
    else:
        weekly_status.require_unclaimed(root, scope, scoped=True)
        delta.before[weekly_status.path(scope['cutoff'])] = None
    return next(e for e in outcome['effects'] if browser_status.effect_key(e) == browser_status.effect_key(delta.effect))


def save_item(repository, private_dir, request, *, standalone=False, manual=False):
    if not isinstance(request, dict):
        raise ValueError('--save-item expects one classifier-selected JSON object')
    root, private = Path(repository).resolve(), Path(private_dir).resolve()
    require_external(root, private)
    private.mkdir(mode=0o700, parents=True, exist_ok=True)
    work = private / 'work'
    with run_lock(root, wait=True) as writer:
        pending_recovery(root, writer)
        state_file = browser_status.safe_path(private, 'feature-run.json')
        state = read(state_file) if state_file.exists() else None
        pin = None
        baseline = {}
        if state is not None:
            if (state['repository'] != str(root) or state['run_id'] != private.name
                    or state['status'] not in ('complete', 'partial', 'collecting')
                    or manual and state['mode'] != 'manual'):
                raise ValueError('Item selection requires its original open collection')
            collect.verify_workspace(work, state)
            pin = collect.collection_pin(root, work, state)
            baseline = input_baseline(root, work, state, pin)
            sources, _ = collect.registered_sources(root, state['sources'], mode=state['mode'])
            code, base = state['code_commit'], state['base_commit']
        else:
            if not standalone or os.path.lexists(work):
                raise ValueError('A scheduled item requires an existing collection; use manual for a standalone URL')
            code, base = publication_commits(root)
            baseline['config/sources.yml'] = collect.file_digest(root / 'config/sources.yml')
            sources, _ = collect.registered_sources(root, None, mode='manual')
        selected, candidate = checked_request(work, state, request)
        delta = item_delta(root, selected, sources, observed_at=datetime.now(timezone.utc).isoformat(), candidate=candidate)
        fact_review = bool(request.get('reference_review')) or (
            candidate is not None and candidate['item_key'] == 'feature-facts:' + str(selected.get('feature_id')))
        if state and state['mode'] in browser_status.MODES and (candidate is None or fact_review):
            sid = delta.effect['source_id']
            # A classifier's independent citation can arrive before this source.
            # Its effect stays provisional until the browser validates the survey.
            if (state['status'] != 'collecting' or sid in state['source_results'] or sid in state['observed']
                    or sid in state.get('generations', {}) or (work / 'generations' / sid).exists()
                    or (work / 'checkpoints' / (sid + '.json')).exists()):
                bounds = window_index(work, state, sid)
                url = candidate['evidence']['url'] if fact_review else selected['url']
                require_url_window(bounds, url, enrichment=fact_review or request.get('reference_review', False))
        if any(rel in baseline and baseline[rel] != checksum for rel, checksum in delta.before.items()):
            raise ValueError('Stale item publication input')
        delta.before.update(baseline)
        marker = dict(code_commit=code, base_commit=base)
        if pin:
            effect = append_outcome(root, pin['scope'], selected['browser'], delta)
            marker.update(pin=state['browser_pin'], browser=selected['browser'], effect=effect)
            folder = work / 'browser-transactions'
        else:
            marker.update(pin=state['item_pin'] if state else None)
            folder = (work if state else private) / 'item-transactions'
        folder.mkdir(exist_ok=True, mode=0o700)
        if folder.is_symlink():
            raise ValueError('Unsafe item transaction folder')
        txn = folder / f'{len(list(folder.iterdir())):08d}-item'
        txn.mkdir()
        durable(txn / 'scope.json', encoded(marker))
        store_changes(root, txn, delta.changes, delta.before, writer, item_effect=delta.effect)
        return delta.effect
