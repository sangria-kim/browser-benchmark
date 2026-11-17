"""Explicit evidence corrections preserve IDs and archive previous facts."""
import copy

from schemas.validate import ContractError, validate_record
from pipeline.deduplicate import stable_id


def correct_event(kind, previous, updates, evidence_source_item_ids):
    """Return (current, archived) for a caller's staged publication.

    A correction is explicit; a changed source hash alone is not permission to
    rewrite an event. PM projections are not authored by this operation.
    """
    if kind not in ('feature_event', 'experiment_event'):
        raise ValueError('Only factual event corrections are supported')
    validate_record(kind, previous)
    forbidden = {'event_id', 'feature_id', 'experiment_id', 'experiment_kind', 'browser', 'schema_version',
                 'revision', 'selection_status', 'selection_reason', 'priority', 'priority_reason', 'assessment_id',
                 'assessed_at', 'selection_rule_version', 'comparison_question', 'benchmark_readiness', 'revisit_trigger'}
    if forbidden.intersection(updates) or not evidence_source_item_ids:
        raise ContractError('Correction must preserve identity and PM judgment and cite evidence')
    current = copy.deepcopy(previous)
    current.update(copy.deepcopy(updates))
    current['source_item_ids'] = sorted(set(previous['source_item_ids'] + list(evidence_source_item_ids)))
    current['revision'] += 1
    validate_record(kind, current)
    return current, copy.deepcopy(previous)


def correction_files(kind, current, archived):
    """Current files and revision archives have separate reader paths."""
    # Experiment events normally use an array shard. The caller must replace
    # that shard, not add this singleton next to an existing copy of the ID.
    archive = 'data/event-revisions/' + current['event_id'] + '/revision-' + str(archived['revision']) + '.json'
    return archive, archived


def parser_aliases(previous, current, aliases):
    """Match a corrected parser identity only by exact definition correspondence.

    A terminal symbol alone is insufficient. Require the same definition path,
    kind, flag ID, expression and branch conditions, with one candidate each.
    Existing catalogs and event subjects remain addressable.
    """
    from collections import defaultdict
    from pipeline.collectors.chrome.parser import semantic_expression
    def signature(record):
        definition = record.get('source_definition')
        if not definition or not record['source_locations']:
            return None
        return (record['experiment_kind'], (record.get('symbol') or '').split('::')[-1], record.get('flag_id'),
                record['source_locations'][0]['path'], semantic_expression(definition['expression']),
                tuple(sorted(semantic_expression(c) for c in record['build_conditions'])))
    old, new = defaultdict(list), defaultdict(list)
    current_ids = {r['experiment_id'] for r in current}
    previous_ids = {r['experiment_id'] for r in previous}
    for record in previous:
        if record['experiment_id'] not in current_ids and signature(record):
            old[signature(record)].append(record)
    for record in current:
        if record['experiment_id'] not in previous_ids and signature(record):
            new[signature(record)].append(record)
    result = copy.deepcopy(aliases)
    existing = {a['old_id'] for a in aliases if a['subject_kind'] == 'experiment'}
    for key in old.keys() & new.keys():
        if len(old[key]) != 1 or len(new[key]) != 1:
            continue
        before, after = old[key][0], new[key][0]
        if before['experiment_id'] in existing:
            continue
        pair = [before['experiment_id'], after['experiment_id']]
        result.append(dict(alias_id=stable_id('alias-parser', pair), subject_kind='experiment',
            old_id=pair[0], target_id=pair[1], source_item_ids=sorted(set(before['source_item_ids'] + after['source_item_ids'])),
            reason='Parser identity correction: exact definition path, expression, kind and branch correspondence. Not a product addition or removal.',
            revision=1, supersedes=None))
    return result
