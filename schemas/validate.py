"""Validate contract records and cross-record references. Python 3.9+.

Install schemas/requirements.txt. Missing validation dependencies are fatal.
This is not a replacement JSON Schema implementation.
"""
import argparse
import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent
KINDS = {
    'source_item': ('source-item', 'source_item_id'),
    'feature': ('feature', 'feature_id'),
    'feature_event': ('feature-event', 'event_id'),
    'experiment': ('experiment', 'experiment_id'),
    'experiment_event': ('experiment-event', 'event_id'),
    'assessment': ('assessment', 'assessment_id'),
    'selected': ('selected', None),
    'report': ('report', 'report_id'),
    'legacy_feature_event': ('legacy-feature-event', 'event_id'),
    'sources_config': ('sources-config', None),
    'chrome_scope_config': ('chrome-scope-config', None),
}


class ContractError(ValueError):
    """Invalid public contract or reference."""


def load_config(path):
    """The .yml files deliberately use JSON-compatible YAML."""
    with open(path, encoding='utf-8') as stream:
        return json.load(stream)


@lru_cache(maxsize=None)
def validator(kind):
    if kind not in KINDS:
        raise ContractError('Unknown record kind: ' + kind)
    schema = load_config(ROOT / (KINDS[kind][0] + '.schema.json'))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_record(kind, record):
    """Raise ContractError on an invalid record; return the input on success."""
    errors = sorted(validator(kind).iter_errors(record), key=lambda e: str(e.path))
    if errors:
        error = errors[0]
        raise ContractError('%s:%s: %s' % (kind, '/'.join(map(str, error.path)), error.message))
    scope = record.get('temporal_scope')
    if scope:
        from pipeline.temporal import dated_scope, instant
        if instant(scope['since'] + 'T00:00:00+09:00') > instant(scope['cutoff']):
            raise ContractError('Temporal window ends before it starts')
        if scope['basis'] == 'endpoint_comparison':
            if not scope['baseline_revision'] or not scope['current_revision'] or scope['precision'] != 'interval' or scope['evidence_date'] is not None:
                raise ContractError('Endpoint scope needs two revisions and interval precision')
            if (not scope.get('baseline_committed_at') or not scope.get('current_committed_at')
                    or instant(scope['baseline_committed_at']) >= instant(scope['since'] + 'T00:00:00+09:00')
                    or instant(scope['current_committed_at']) < instant(scope['since'] + 'T00:00:00+09:00')
                    or instant(scope['current_committed_at']) > instant(scope['cutoff'])):
                raise ContractError('Endpoint commit times do not fit the source window')
            expected = {'added': 'in_period', 'changed': 'in_period', 'unchanged': 'unchanged', 'unknown': 'unknown'}
            if scope['status'] != 'context' and expected.get(scope['change']) != scope['status']:
                raise ContractError('Endpoint change and eligibility differ')
        elif scope['status'] != 'context':
            expected = dated_scope(scope['since'], scope['cutoff'], scope['evidence_date'], scope['basis'])
            if (scope['status'], scope['precision']) != (expected['status'], expected['precision']):
                raise ContractError('Dated eligibility differs from evidence date')
    if kind == 'source_item':
        if 'reference' in (record['record_status'], record['origin']) or record['item_key'].startswith('official-url:'):
            from pipeline.official_reference import normalize_url, reference_row
            expected = reference_row(record, normalize_url(record['evidence']['url']), record['observed_at'])
            if record != expected:
                raise ContractError('Official reference must preserve the URL snapshot without source or release facts')
        ids = [r['revision_id'] for r in record['revisions']]
        if len(ids) != len(set(ids)):
            raise ContractError('Duplicate source revision IDs')
        prior_ids = set()
        for revision in record['revisions']:
            if revision.get('restores_revision_id') and revision['restores_revision_id'] not in prior_ids:
                raise ContractError('Fact restoration must reference an earlier source revision')
            prior_ids.add(revision['revision_id'])
        latest = record['revisions'][-1]
        for field in ('title', 'summary', 'evidence', 'observed_at', 'published_at'):
            if latest[field] != record[field]:
                raise ContractError('Latest source revision differs: ' + field)
        for field in ('channel', 'platform', 'version', 'item_type', 'record_status', 'lifecycle', 'item_content_sha256'):
            if field in latest and latest[field] != record.get(field):
                raise ContractError('Latest source revision differs: ' + field)
        if latest['content_sha256'] != record['evidence']['content_sha256']:
            raise ContractError('Source evidence hash differs from revision')
        if latest['source_revision'] != record['evidence']['source_revision']:
            raise ContractError('Source evidence revision differs from snapshot')
        if record['experiment_kind'] and record['item_type'] != record['experiment_kind']:
            raise ContractError('Experiment source kind mismatch')
    if kind == 'experiment':
        if (record['product_channel'] is None) != (record['product_revision'] is None):
            raise ContractError('Product channel needs a pinned product revision')
        if record['verification_status'] == 'source_only' and record['installed_availability'] != 'unknown':
            raise ContractError('Source presence cannot prove installed availability')
    if kind == 'assessment':
        if record['evaluator'] == 'model' and (not record['model_id'] or not record['prompt_version']):
            raise ContractError('Model assessment needs model and prompt versions')
        if record['supersedes'] == record['assessment_id']:
            raise ContractError('Assessment cannot supersede itself')
    if kind == 'sources_config':
        ids = [s['source_id'] for s in record['sources']]
        if len(ids) != len(set(ids)):
            raise ContractError('Duplicate source IDs')
        if set(s['browser'] for s in record['sources'] if s['enabled']) != set(record['browsers']):
            raise ContractError('Each browser needs an enabled registered source')
    return record


def read_records(path, kind):
    """Read a singleton or a bounded JSON array. Paths never imply IDs."""
    value = load_config(path)
    records = value if isinstance(value, list) else [value]
    for record in records:
        validate_record(kind, record)
    return records


def validate_transition(kind, previous, current):
    """Check immutable histories before replacing an existing materialization."""
    validate_record(kind, previous)
    validate_record(kind, current)
    id_field = KINDS[kind][1]
    if id_field and previous[id_field] != current[id_field]:
        raise ContractError('An update cannot change its stable ID')
    if kind == 'assessment' and previous != current:
        raise ContractError('Assessment records are immutable')
    if kind == 'report' and previous != current:
        if (previous['date'] != current['date'] or
                current['revision'] != previous['revision'] + 1 or
                current['supersedes_revision'] != previous['revision']):
            raise ContractError('Report revisions must append to the same daily report')
    if kind == 'source_item':
        old = previous['revisions']
        if current['revisions'][:len(old)] != old:
            raise ContractError('Source revision history must be an unchanged prefix')
        for field in ('source_id', 'item_key', 'browser'):
            if previous[field] != current[field]:
                raise ContractError('Source identity changed: ' + field)
    if kind == 'selected':
        old = {v['change_id']: v for v in previous['history']}
        new = {v['change_id']: v for v in current['history']}
        if any(new.get(k) != v for k, v in old.items()):
            raise ContractError('Selection history must never be lost or rewritten')
    return current


def validate_dataset(records_by_kind, source_ids=None, *, reference_check=None):
    """Validate a complete candidate dataset, not an isolated delta.

    records_by_kind maps canonical singular kind to a list of records.
    Optional source_ids includes registry IDs plus chromium-source and legacy.
    Legacy v1 compatibility records must be migrated before joining this graph.
    """
    index = {}
    for kind, records in records_by_kind.items():
        id_field = KINDS[kind][1]
        index[kind] = {}
        for record in records:
            validate_record(kind, record)
            if id_field:
                ident = record[id_field]
                if ident in index[kind]:
                    raise ContractError('Duplicate %s ID: %s' % (kind, ident))
                index[kind][ident] = record

    def require(kind, ident):
        if ident not in index.get(kind, {}):
            raise ContractError('Missing %s reference: %s' % (kind, ident))
        return index[kind][ident]

    def same_subject(a, b):
        if (a['subject_kind'], a['subject_id']) != (b['subject_kind'], b['subject_id']):
            raise ContractError('Assessment subject differs from reference')

    for kind in ('feature', 'feature_event', 'experiment', 'experiment_event'):
        for record in records_by_kind.get(kind, []):
            for ident in record['source_item_ids']:
                require('source_item', ident)
            if kind == 'feature':
                pins_by_source = record.get('source_revision_ids', {})
                pinned = {revision for pins in pins_by_source.values() for revision in pins}
                for fact in record.get('feature_facts', {}).values():
                    if fact['revision_id'] not in pins_by_source.get(fact['source_item_id'], []):
                        raise ContractError('Optional feature fact must cite a pinned item and revision')
                if record.get('source_revision_excerpts', {}).keys() - pinned:
                    raise ContractError('Feature excerpt must cite a confirmed source revision')
                for ident, pins in pins_by_source.items():
                    if ident not in record['source_item_ids']:
                        raise ContractError('Feature revision references an uncited source item')
                    source = require('source_item', ident)
                    confirmed = set(pins)
                    ordered = [r['revision_id'] for r in source['revisions'] if r['revision_id'] in confirmed]
                    if source['browser'] != record['browser'] or ordered != pins:
                        raise ContractError('Feature revision references must match the cited source history')
            if kind == 'feature_event':
                feature = require('feature', record['feature_id'])
                if feature['browser'] != record['browser']:
                    raise ContractError('Feature/event browser mismatch')
                for field in ('previous_event_id', 'correction_of'):
                    if record.get(field):
                        require('feature_event', record[field])
            if kind == 'experiment_event':
                experiment = require('experiment', record['experiment_id'])
                if experiment['experiment_kind'] != record['experiment_kind']:
                    raise ContractError('Experiment/event kind mismatch')
                if record['correction_of']:
                    require('experiment_event', record['correction_of'])
            if kind == 'experiment':
                for relationship in record['relationships']:
                    target_kind = 'feature' if relationship['kind'] == 'related_feature' else 'experiment'
                    target = require(target_kind, relationship['target_id'])
                    if relationship['kind'] == 'alias_of' and target['experiment_kind'] != record['experiment_kind']:
                        raise ContractError('Experiment alias kind mismatch')
            if kind in ('feature', 'experiment'):
                event_kind = kind + '_event'
                owner_key = kind + '_id'
                for ident in record['event_ids']:
                    if require(event_kind, ident)[owner_key] != record[owner_key]:
                        raise ContractError('Catalog/event owner mismatch')
    # Predecessor/correction edges are directed to older facts of the same owner.
    # Check combined edges so alternating predecessor/correction cycles fail too.
    for event_kind, owner_key in (('feature_event', 'feature_id'), ('experiment_event', 'experiment_id')):
        events = index.get(event_kind, {})
        edges = {}
        for ident, event in events.items():
            edges[ident] = []
            for field in ('previous_event_id', 'correction_of'):
                target = event.get(field)
                if target:
                    previous = require(event_kind, target)
                    if previous[owner_key] != event[owner_key]:
                        raise ContractError('Event history owner mismatch')
                    edges[ident].append(target)
        visiting, visited = set(), set()
        for ident in events:
            stack = [(ident, False)]
            while stack:
                current, leaving = stack.pop()
                if leaving:
                    visiting.remove(current)
                    visited.add(current)
                elif current not in visited:
                    if current in visiting:
                        raise ContractError('Event history cycle')
                    visiting.add(current)
                    stack.append((current, True))
                    stack.extend((target, False) for target in edges[current])
    for record in records_by_kind.get('source_item', []):
        if record['record_status'] == 'reference' and reference_check is not None:
            reference_check(record)
        elif source_ids is not None and record['source_id'] not in source_ids:
            raise ContractError('Unregistered source ID: ' + record['source_id'])
    for record in records_by_kind.get('assessment', []):
        require(record['subject_kind'], record['subject_id'])
        for ident in record['evidence_source_item_ids']:
            require('source_item', ident)
        seen = {record['assessment_id']}
        cursor = record
        while cursor['supersedes']:
            previous = require('assessment', cursor['supersedes'])
            same_subject(record, previous)
            if previous['assessment_id'] in seen:
                raise ContractError('Assessment supersedes cycle')
            seen.add(previous['assessment_id'])
            cursor = previous
    def validate_selection_links(item, selection_kind):
        subject_kind = item['subject_kind']
        subject = require(subject_kind, item['subject_id'])
        is_flag = selection_kind == 'flags'
        catalog_kind = 'experiment' if is_flag else 'feature'
        event_kind = catalog_kind + '_event'
        owner_key = catalog_kind + '_id'
        if subject_kind not in ('source_item', event_kind):
            raise ContractError('Selection kind does not match subject kind')
        expected_kind = subject.get('experiment_kind')
        if is_flag != (expected_kind is not None):
            raise ContractError('Selection kind does not match source experiment kind')
        if item['experiment_kind'] != expected_kind:
            raise ContractError('Selection experiment kind differs from subject')
        owner = subject[owner_key] if subject_kind == event_kind else None
        catalog_id = item.get('catalog_id')
        if catalog_id:
            catalog = require(catalog_kind, catalog_id)
            if owner is not None and owner != catalog_id:
                raise ContractError('Selection catalog owner differs from subject')
            if subject_kind == 'source_item' and subject['source_item_id'] not in catalog['source_item_ids']:
                raise ContractError('Selection catalog lacks source-item evidence')
            if is_flag and catalog['experiment_kind'] != expected_kind:
                raise ContractError('Selection catalog experiment kind differs from subject')
            owner = catalog_id
        for ident in item['event_ids']:
            event = require(event_kind, ident)
            if owner is not None and owner != event[owner_key]:
                raise ContractError('Selection event owner differs from subject')
            if subject_kind == 'source_item' and subject['source_item_id'] not in event['source_item_ids']:
                raise ContractError('Selection event lacks source-item evidence')
            if is_flag and event['experiment_kind'] != expected_kind:
                raise ContractError('Selection event experiment kind differs from subject')
            owner = event[owner_key]

    for selected in records_by_kind.get('selected', []):
        subjects = set()
        changes = set()
        for item in selected['current']:
            key = (item['subject_kind'], item['subject_id'])
            if key in subjects:
                raise ContractError('Duplicate current selection')
            subjects.add(key)
            assessment = require('assessment', item['assessment_id'])
            same_subject(item, assessment)
            if assessment['status'] != 'selected':
                raise ContractError('Current selection requires selected assessment')
            validate_selection_links(item, selected['selection_kind'])
        for item in selected['history']:
            if item['change_id'] in changes:
                raise ContractError('Duplicate selection change ID')
            changes.add(item['change_id'])
            assessment = require('assessment', item['assessment_id'])
            same_subject(item, assessment)
            validate_selection_links(item, selected['selection_kind'])
            if item['previous_assessment_id']:
                same_subject(item, require('assessment', item['previous_assessment_id']))
            if (item['action'] == 'deselected') == (assessment['status'] == 'selected'):
                raise ContractError('Selection action contradicts assessment')
    selection_changes = {}
    selection_change_kinds = {}
    for selected in records_by_kind.get('selected', []):
        for item in selected['history']:
            if item['change_id'] in selection_changes:
                raise ContractError('Duplicate global selection change ID')
            selection_changes[item['change_id']] = item
            selection_change_kinds[item['change_id']] = selected['selection_kind']
    for report in records_by_kind.get('report', []):
        if 'outcome' in report:
            has_changes = bool(report['items'] or report.get('catalog_transitions'))
            complete = all(v == 'complete' for v in report['completeness'].values())
            expected = 'changes' if has_changes else 'no_changes' if complete else 'incomplete'
            if report['outcome'] != expected:
                raise ContractError('Report outcome contradicts changes or completeness')
        changes_seen = set()
        for item in report['items']:
            if item['change_id'] in changes_seen:
                raise ContractError('Duplicate report selection change')
            changes_seen.add(item['change_id'])
            require(item['subject_kind'], item['subject_id'])
            same_subject(item, require('assessment', item['assessment_id']))
            if item['change_id'] not in selection_changes:
                raise ContractError('Missing report selection change: ' + item['change_id'])
            change = selection_changes[item['change_id']]
            same_subject(item, change)
            if change['assessment_id'] != item['assessment_id']:
                raise ContractError('Report change assessment mismatch')
            report_links = dict(item, experiment_kind=change['experiment_kind'],
                                catalog_id=change.get('catalog_id'))
            validate_selection_links(report_links, selection_change_kinds[item['change_id']])
            if not set(item['event_ids']).issubset(change['event_ids']):
                raise ContractError('Report events are not a subset of selection change events')
            if item.get('action', change['action']) != change['action']:
                raise ContractError('Report action differs from selection change')
            assessment = require('assessment', item['assessment_id'])
            if datetime.fromisoformat(assessment['assessed_at'].replace('Z', '+00:00')) > datetime.fromisoformat(report['cutoff'].replace('Z', '+00:00')):
                raise ContractError('Report assessment postdates cutoff')
            if item.get('discovered_at', change['effective_at']) != change['effective_at']:
                raise ContractError('Report discovery time differs from selection time')
            for ident in item.get('related_change_ids', []):
                if ident in changes_seen or ident not in selection_changes:
                    raise ContractError('Duplicate or missing related selection change')
                changes_seen.add(ident)
                same_subject(item, selection_changes[ident])
            for evidence in item.get('evidence', []):
                source = require('source_item', evidence['source_item_id'])
                if source['source_item_id'] not in assessment['evidence_source_item_ids']:
                    raise ContractError('Report evidence is not assessment evidence')
                revisions = [r for r in source['revisions'] if r['revision_id'] == evidence['revision_id']]
                if not revisions or revisions[0]['content_sha256'] != evidence['content_sha256'] or revisions[0]['evidence']['url'] != evidence['url']:
                    raise ContractError('Report source revision does not match archived evidence')
        for transition in report.get('catalog_transitions', []):
            before, after = transition['previous'], transition['current']
            if (before['subject_kind'], before['subject_id']) == (after['subject_kind'], after['subject_id']):
                raise ContractError('Catalog replacement requires different subjects')
            if 'selected' not in (before['status'], after['status']):
                raise ContractError('Report replacement must affect a selected card')
            for side in (before, after):
                assessment = require('assessment', side['assessment_id'])
                same_subject(side, assessment)
                if side['catalog_id'] != transition['catalog_id'] or side['status'] != assessment['status'] or side['assessed_at'] != assessment['assessed_at']:
                    raise ContractError('Report replacement contradicts assessment or owner')
                validate_selection_links(side, 'flags' if side['experiment_kind'] else 'features')
    return records_by_kind


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=sorted(KINDS))
    parser.add_argument('paths', nargs='+', type=Path)
    args = parser.parse_args()
    count = sum(len(read_records(path, args.kind)) for path in args.paths)
    print('Validated %s %s records' % (count, args.kind))


if __name__ == '__main__':
    main()
