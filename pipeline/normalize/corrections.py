"""Explicit evidence corrections preserve IDs and archive previous facts."""
import copy

from schemas.validate import ContractError, validate_record


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
