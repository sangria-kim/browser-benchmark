"""Evidence-based collection scope. Observation time never dates a product change."""
import copy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

POLICY_VERSION = 'dated-endpoints-v1'


def instant(value):
    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        raise ValueError('Temporal evidence timestamp needs a timezone')
    return value


def dated_scope(since, cutoff, date=None, basis='unknown', reason=None):
    """Printed dates compare as calendar days; timestamps compare as instants."""
    end = instant(cutoff)
    status, precision = 'unknown', 'unknown'
    if date:
        if len(date) == 10:
            datetime.strptime(date, '%Y-%m-%d')
            precision = 'day'
            status = 'before_period' if date < since else 'after_cutoff' if date > end.astimezone(ZoneInfo('Asia/Seoul')).date().isoformat() else 'in_period'
        else:
            value = instant(date)
            start = instant(since + 'T00:00:00+09:00')
            precision = 'timestamp'
            status = 'before_period' if value < start else 'after_cutoff' if value > end else 'in_period'
    return dict(version=1, since=since, cutoff=cutoff, status=status, basis=basis if date else 'unknown',
                evidence_date=date, precision=precision, baseline_revision=None, current_revision=None,
                change=None, reason=reason or ('Official item date.' if date else 'No supported item date.'))


def policy(dataset, cutoff=None):
    """Only materialized scopes activate the new projection for old readers."""
    if cutoff:
        frozen = next((r.get('collection_scope') for r in dataset.get('report', [])
                       if instant(r['cutoff']) == instant(cutoff) and r.get('collection_scope')), None)
        if frozen:
            return copy.deepcopy(frozen)
    rows = [s for s in dataset.get('source_item', []) if 'temporal_scope' in s]
    scopes = [s['temporal_scope'] for s in rows]
    if not scopes:
        return None
    windows = {(s['since'], s['cutoff']) for s in scopes}
    since = max(w[0] for w in windows)
    cutoff = max((w[1] for w in windows), key=instant)
    revisions = sorted({(s['baseline_revision'], s['current_revision'], s.get('baseline_committed_at'), s.get('current_committed_at'))
                        for s in scopes if s['basis'] == 'endpoint_comparison' and s['status'] != 'context'})
    source_windows = sorted({(s['source_id'], s['temporal_scope']['since'], s['temporal_scope']['cutoff']) for s in rows})
    return dict(version=POLICY_VERSION, since=since, cutoff=cutoff, timezone='Asia/Seoul',
                source_windows=[dict(source_id=source, since=start, cutoff=end) for source, start, end in source_windows],
                chrome_endpoints=[dict(baseline_revision=a, current_revision=b, baseline_committed_at=c, current_committed_at=d)
                                  for a, b, c, d in revisions])


def context_scope(context):
    subject, catalog = context['subject'], context.get('catalog') or {}
    if subject.get('experiment_kind'):
        return catalog.get('temporal_scope') or subject.get('temporal_scope')
    if context['subject_kind'] != 'source_item':
        return subject.get('temporal_scope')
    return subject.get('temporal_scope')


def eligible(context):
    scope = context_scope(context)
    return scope is None or scope['status'] == 'in_period'


def scope_semantics(scope):
    # A later observation window or commit with identical meaning does not
    # need a new PM judgment. Eligibility, dated evidence and change kind do.
    return {k: v for k, v in scope.items() if k not in {'cutoff', 'baseline_revision', 'current_revision',
            'baseline_committed_at', 'current_committed_at', 'reason'}} if scope else None


def project_legacy(sources, features, events, experiments, since, cutoff):
    """Retain old IDs and history; absence from this window is never deletion."""
    for source in sources:
        if 'temporal_scope' not in source:
            source['temporal_scope'] = dated_scope(since, cutoff, reason='Retained evidence has no reviewed item-date projection.')
    for event in events:
        # These are explicit product event dates, not source observation dates.
        date = event.get('announced_at') or event.get('effective_at')
        event['temporal_scope'] = dated_scope(since, cutoff, date, 'legacy_event')
    by_id = {s['source_item_id']: s for s in sources}
    for feature in features:
        scopes = [e['temporal_scope'] for e in events if e['feature_id'] == feature['feature_id']]
        scopes += [by_id[s]['temporal_scope'] for s in feature['source_item_ids']]
        feature['temporal_scope'] = copy.deepcopy(next((s for s in scopes if s['status'] == 'in_period'),
                                                     scopes[0] if scopes else dated_scope(since, cutoff)))
    for experiment in experiments:
        if 'temporal_scope' not in experiment:
            experiment['temporal_scope'] = dated_scope(since, cutoff, reason='No verified endpoint comparison for this retained experiment.')
