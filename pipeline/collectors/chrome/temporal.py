"""Compare current definition families with the same parser at a pinned boundary."""
import copy
import json
from collections import Counter, defaultdict

from pipeline.temporal import dated_scope, instant
from .providers import canonical, digest
from .parser import semantic_expression


def compare(current, baseline, *, since, cutoff, boundary_time, current_time):
    if instant(boundary_time) >= instant(since + 'T00:00:00+09:00'):
        raise ValueError('Baseline commit must precede the KST collection boundary')
    if instant(current_time) > instant(cutoff) or instant(current_time) < instant(since + 'T00:00:00+09:00'):
        raise ValueError('Current commit must fall within its explicit source window')
    if (current['parser_version'] != baseline['parser_version'] or not current.get('parser_sha256')
            or current['parser_sha256'] != baseline.get('parser_sha256') or current['scope_sha256'] != baseline['scope_sha256']):
        raise ValueError('Endpoint comparison needs the same parser and declared scope')
    if current['revision'] == baseline['revision']:
        raise ValueError('Endpoint revisions must differ')
    result = copy.deepcopy(current)

    def index(bundle, source_ids=None):
        facts = {f['experiment_id']: f for f in bundle['facts']
                 if source_ids is None or f['source_item_id'] in source_ids}
        groups, symbols = defaultdict(list), defaultdict(set)
        for f in facts.values():
            d = f['definition']
            key = d['kind'], f['semantic']['symbol'], d['path']
            groups[key].append(f)
            symbols[key[:2]].add(key)
        return facts, groups, symbols

    before, old_groups, old_symbols = index(baseline)
    observed = {s['source_item_id'] for s in current['source_items']
                if s['evidence']['source_revision'] == current['revision']}
    after, new_groups, new_symbols = index(current, observed)
    boundary_unresolved = {ref for fact in before.values() for ref in fact['semantic']['unresolved_references']}

    def signature(fact, facts, stack=()):
        semantic = fact['semantic']
        if not semantic['parsed'] or semantic['unresolved_references']:
            return None
        ident = fact['experiment_id']
        if ident in stack:
            # A known cycle is represented by symbol identity, not source IDs.
            return ['cycle', semantic['kind'], semantic['symbol']]
        refs = []
        for relation in semantic['references']:
            target = facts.get(relation['target_id'])
            if target is None:
                return None
            value = signature(target, facts, stack + (ident,))
            if value is None:
                return None
            refs.append([relation['kind'], value])
        # Paths, line locations, parser metadata, inferred expiry lifecycle and
        # whole-file hashes are not a change to a definition's own semantics.
        value = {k: v for k, v in semantic.items() if k not in {'references', 'options', 'lifecycle', 'parsed', 'unresolved_references'}}
        value['definition'] = semantic_expression(value['definition'])
        if semantic['kind'] != 'flag_entry':
            # Typed feature/switch values, defaults, conditions and aliases
            # fully describe their declaration; macro syntax is incidental.
            value.pop('definition')
        value['conditions'] = sorted(semantic_expression(c) for c in value['conditions'])
        if value['default'] is not None:
            if value['default'].startswith('{'):
                try:
                    states = json.loads(value['default'])
                    if isinstance(states, dict) and 'default' in states:
                        value['default'] = json.dumps({k: v for k, v in states.items() if k == 'default' or v != states['default']}, sort_keys=True)
                except ValueError:
                    pass
            value['default'] = semantic_expression(value['default'])
        value['options'] = sorted([{k: v for k, v in o.items() if k != 'path'} for o in semantic['options']], key=canonical)
        for option in value['options']:
            option['expression'] = semantic_expression(option['expression'])
            if 'conditions' in option:
                option['conditions'] = sorted(semantic_expression(c) for c in option['conditions'])
        value['references'] = sorted(refs, key=canonical)
        return value

    def family(facts, all_facts):
        values = [signature(f, all_facts) for f in facts]
        return None if any(v is None for v in values) else sorted(values, key=canonical)

    coverage = baseline['coverage']
    absence_proven = (coverage['tree_complete'] and coverage['mode'] == 'full_tree'
                      and not any(coverage.get(k) for k in ('unparsed_count', 'errors', 'pending_paths', 'missing_required_paths', 'unsupported_in_scope')))
    scopes = {}
    for key, facts in new_groups.items():
        old_key = key if key in old_groups else None
        alternatives = old_symbols.get(key[:2], set())
        if old_key is None and len(alternatives) == 1 and len(new_symbols[key[:2]]) == 1:
            old_key = next(iter(alternatives))
        now = family(facts, after)
        prior = family(old_groups[old_key], before) if old_key else None
        status, change, reason = 'unknown', 'unknown', 'Unresolved definition or dependency correspondence.'
        if now is not None and old_key and prior is not None:
            change = 'unchanged' if now == prior else 'changed'
            status = 'unchanged' if change == 'unchanged' else 'in_period'
            reason = 'Same-parser endpoint definition and dependency comparison.'
        elif now is not None and not alternatives and absence_proven and not any(
                ref == key[1] or ('::' not in ref and ref == key[1].split('::')[-1]) for ref in boundary_unresolved):
            status, change = 'in_period', 'added'
            reason = 'Absent from fully enumerated and parsed boundary tree; defined in current tree.'
        elif not old_key and not absence_proven:
            reason = 'Boundary enumeration or parsing cannot establish prior absence.'
        elif not old_key and any(ref == key[1] or ('::' not in ref and ref == key[1].split('::')[-1]) for ref in boundary_unresolved):
            reason = 'Boundary has an unresolved reference to this symbol; prior absence is not established.'
        scope = dated_scope(since, cutoff)
        scope.update(status=status, basis='endpoint_comparison', precision='interval',
                     baseline_revision=baseline['revision'], current_revision=current['revision'],
                     baseline_committed_at=boundary_time, current_committed_at=current_time,
                     change=change, reason=reason)
        for fact in facts:
            scopes[fact['experiment_id']] = scope
    # Retained evidence is not an observation of the current endpoint.
    for fact in result['facts']:
        if fact['source_item_id'] not in observed:
            scope = dated_scope(since, cutoff)
            scope.update(status='context', basis='endpoint_comparison', precision='interval',
                         baseline_revision=baseline['revision'], current_revision=current['revision'],
                         baseline_committed_at=boundary_time, current_committed_at=current_time,
                         change='unknown',
                         reason='Retained identity was not observed at the current endpoint.')
            scopes[fact['experiment_id']] = scope
    for experiment in result['experiments']:
        experiment['temporal_scope'] = copy.deepcopy(scopes[experiment['experiment_id']])
    by_source = {f['source_item_id']: scopes[f['experiment_id']] for f in result['facts']}
    for source in result['source_items']:
        source['temporal_scope'] = copy.deepcopy(by_source[source['source_item_id']])
    result['removed_candidates'] = []  # Current-definition projection, not deletion history.
    result['temporal_comparison'] = dict(version=1, since=since, cutoff=cutoff, boundary_time=boundary_time,
        current_committed_at=current_time,
        baseline_revision=baseline['revision'], current_revision=current['revision'],
        baseline_absence_proven=absence_proven, counts=dict(Counter(s['status'] for s in scopes.values())))
    result['coverage']['temporal_complete'] = not any(s['status'] == 'unknown' for s in scopes.values())
    result['coverage']['complete'] &= result['coverage']['temporal_complete']
    return result
