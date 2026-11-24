"""Public result for a verified 08:00 Asia/Seoul collection, not a report."""
from datetime import time, timedelta, timezone
import json
from pathlib import Path
import re

from pipeline.temporal import instant

FOLDER = 'data/daily-status'
KST = timezone(timedelta(hours=9))


def status_path(path):
    return bool(re.fullmatch(r'data/daily-status/\d{4}-\d{2}-\d{2}\.json', path))


def receipt(cutoff, count, collected_count):
    local = instant(cutoff).astimezone(KST)
    if local.time() != time(8):
        raise ValueError('Daily status requires the 08:00 Asia/Seoul cutoff')
    day = local.date().isoformat()
    return f'{FOLDER}/{day}.json', dict(date=day, cutoff=local.isoformat(),
                                       status='incomplete' if count is None else 'complete',
                                       collected_feature_count=collected_count, change_count=count)


def validate_receipt(path, value):
    fields = {'date', 'cutoff', 'status', 'collected_feature_count', 'change_count'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('Invalid daily status fields')
    count = value['change_count']
    if count is not None and (type(count) is not int or count < 0):
        raise ValueError('Invalid daily change count')
    collected = value['collected_feature_count']
    if count is None:
        if collected is not None:
            raise ValueError('Incomplete daily status has no confirmed feature total')
    elif type(collected) is not int or collected < count:
        raise ValueError('Invalid collected feature count')
    if not isinstance(value['cutoff'], str):
        raise ValueError('Invalid daily cutoff')
    expected_path, expected_value = receipt(value['cutoff'], count, collected)
    if path != expected_path or value != expected_value:
        raise ValueError('Invalid daily status date, cutoff or state')


def validate_tree(root):
    folder = root / FOLDER
    if folder.is_symlink():
        raise ValueError('Invalid daily status folder')
    if not folder.exists():
        return
    if not folder.is_dir():
        raise ValueError('Invalid daily status folder')
    for target in folder.iterdir():
        if target.is_symlink() or not target.is_file():
            raise ValueError('Invalid daily status file')
        validate_receipt(target.relative_to(root).as_posix(), json.loads(target.read_bytes()))


def add_receipt(root, changes, before, cutoff, count, collected_count):
    """An incomplete retry cannot downgrade an accepted receipt."""
    from pipeline.run_daily import digest
    from pipeline.collectors.browser.collector import json_bytes

    rel, value = receipt(cutoff, count, collected_count)
    target = root / rel
    if target.is_symlink() or target.parent.is_symlink() or root not in target.resolve().parents:
        raise ValueError('Unsafe daily status target')
    raw = target.read_bytes() if target.exists() else None
    if raw is not None:
        previous = json.loads(raw)
        validate_receipt(rel, previous)
        if previous['status'] == 'complete':
            if count is not None and (previous != value or any(
                    digest(json_bytes(rows)) != before[name] for name, rows in changes.items())):
                raise ValueError('Cannot change data after the daily status is complete')
            return
    before[rel] = digest(raw) if raw is not None else None
    changes[rel] = value


def classified_decisions(classification, inventory):
    """Require a final disposition for each exact observed candidate revision."""
    if (not isinstance(classification, dict) or set(classification) != {'decisions', 'dispositions'}
            or not all(isinstance(value, list) for value in classification.values())):
        raise ValueError('Daily classification requires private decisions and dispositions arrays')

    dispositions = {}
    fields = ('source_id', 'source_item_id', 'revision_id')
    for row in classification['dispositions']:
        if not isinstance(row, dict) or set(row) != {*fields, 'disposition'}:
            raise ValueError('Invalid daily candidate disposition fields')
        if not all(isinstance(row[k], str) and row[k] for k in fields):
            raise ValueError('Daily candidate disposition requires exact source, item and revision IDs')
        key = tuple(row[k] for k in fields)
        if key not in inventory or key in dispositions:
            raise ValueError('Unknown or repeated daily candidate disposition')
        kind = row['disposition']
        if kind not in ('selected', 'excluded', 'unchanged'):
            raise ValueError('Daily candidate disposition is not final')
        dispositions[key] = kind
    if dispositions.keys() != inventory:
        raise ValueError('Daily classification does not cover all observed candidates')

    eligible = {(item, revision) for _, item, revision in inventory}
    selected = {(item, revision) for (_, item, revision), value in dispositions.items() if value == 'selected'}
    if len(eligible) != len(inventory):
        raise ValueError('Daily candidate identities are ambiguous')
    included = set()
    for row in classification['decisions']:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) and row[k] for k in fields[1:]):
            raise ValueError('Invalid daily feature decision identity')
        included.add((row['source_item_id'], row['revision_id']))
    if included != selected:
        raise ValueError('Daily decisions must match the selected candidate dispositions')
    return classification['decisions']


if __name__ == '__main__':
    validate_tree(Path(__file__).resolve().parents[1])
