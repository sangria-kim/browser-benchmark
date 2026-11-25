"""Immutable whole-weekly settlement, separate from the browser-detail consumer contract."""
from pathlib import Path
import re

from pipeline import browser_status
from pipeline.run_daily import git, read
from pipeline.temporal import instant

FOLDER = 'data/weekly-status'
FIRST_GUARDED_CUTOFF = '2026-11-29T10:00:00+09:00'


def guarded(cutoff):
    return instant(cutoff) >= instant(FIRST_GUARDED_CUTOFF)


def path(cutoff):
    name = browser_status.detail_path('weekly_reconcile', cutoff).rsplit('/', 1)[1]
    return f'{FOLDER}/{name}'


def is_receipt(rel):
    return bool(re.fullmatch(r'data/weekly-status/\d{4}-\d{2}-\d{2}T\d{6}\.\d{6}Z\.json', rel))


def receipt(scope, signature, selected):
    # A full historical retry still closes the cutoff. Its new observations cannot
    # reconstruct the original selection made before settlement records existed.
    ids = sorted(selected) if guarded(scope['cutoff']) else None
    value = dict(version=1, scope=scope, status='complete', classification=signature, feature_ids=ids,
                 collected_feature_count=len(ids) if ids is not None else None)
    return browser_status.seal(value)


def validate(rel, value):
    required = {'version', 'scope', 'status', 'classification', 'feature_ids', 'collected_feature_count', 'checksum'}
    if (not isinstance(value, dict) or set(value) != required or type(value['version']) is not int
            or value['version'] != 1 or value['status'] != 'complete'
            or not browser_status.valid(browser_status.HASH, value['classification'])
            or value['checksum'] != browser_status.value_hash({k: v for k, v in value.items() if k != 'checksum'})):
        raise ValueError('Invalid whole weekly result')
    scope = value['scope']
    browser_status.validate_scope(scope)
    if scope['mode'] != 'weekly_reconcile' or rel != path(scope['cutoff']):
        raise ValueError('Invalid whole weekly scope or cutoff')
    ids, count = value['feature_ids'], value['collected_feature_count']
    if guarded(scope['cutoff']):
        if (not isinstance(ids, list) or any(not browser_status.valid(browser_status.IDENT, fid) for fid in ids)
                or ids != sorted(set(ids)) or type(count) is not int or count != len(ids)):
            raise ValueError('Invalid whole weekly collected feature count')
    elif ids is not None or count is not None:
        raise ValueError('Unmarked historical weekly totals cannot be reconstructed')


def check_features(value, features):
    if any(features.get(fid, {}).get('browser') not in value['scope']['expected']
           for fid in value['feature_ids'] or ()):
        raise ValueError('Whole weekly classification refers to a missing or out-of-scope feature')


def read_current(root, cutoff):
    rel = path(cutoff)
    target = browser_status.safe_path(root, rel)
    value = None
    if target.exists():
        value = read(target)
        validate(rel, value)
    if (root / '.git').exists() and git(root, 'ls-tree', 'HEAD', '--', rel):
        if value is None or git(root, 'diff', '--name-only', 'HEAD', '--', rel):
            raise ValueError('Committed whole weekly result is missing or changed')
    return value


def require_unclaimed(root, scope, *, scoped):
    """Check the two publication routes under the same repository lock."""
    cutoff = scope['cutoff']
    if read_current(root, cutoff) is not None:
        raise ValueError('This cutoff already has a completed whole weekly publication')
    other = browser_status.read_current(root, browser_status.detail_path('weekly_reconcile', cutoff))
    if other is not None:
        if not scoped:
            raise ValueError('Browser outcomes already exist; finish this cutoff with --save-browser')
        return
    if scoped and not guarded(cutoff):
        raise ValueError('Unmarked weekly cutoff predates browser settlement; its original result is unknown')


def check_prior_evidence(root, scope, graph, replacements):
    """Check persisted rows in the proposed graph, restoring old rows for replaced files."""
    from pipeline.normalize.storage import PATHS, records
    cutoff = instant(scope['cutoff'])
    since = scope['start'][:10]

    def check(rows):
        for row in rows:
            prior = row.get('temporal_scope', {})
            if prior.get('since') == since and prior.get('cutoff') and instant(prior['cutoff']) == cutoff:
                raise ValueError('Existing evidence has this weekly cutoff and historical window; '
                                 'the original publication cannot be verified')

    for kind, ident in [('feature', 'feature_id'), ('source_item', 'source_item_id')]:
        replaced_ids = set()
        for rel, value in replacements.items():
            if Path(rel).match(PATHS[kind]):
                replaced_ids.update(row[ident] for row in records(value))
                previous = browser_status.safe_path(root, rel)
                if previous.exists():
                    check(records(read(previous)))
        check(row for row in graph[kind] if row[ident] not in replaced_ids)
