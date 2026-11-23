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


def receipt(cutoff, count):
    local = instant(cutoff).astimezone(KST)
    if local.time() != time(8):
        raise ValueError('Daily status requires the 08:00 Asia/Seoul cutoff')
    day = local.date().isoformat()
    return f'{FOLDER}/{day}.json', dict(date=day, cutoff=local.isoformat(),
                                       status='incomplete' if count is None else 'complete',
                                       change_count=count)


def validate_receipt(path, value):
    if not isinstance(value, dict) or set(value) != {'date', 'cutoff', 'status', 'change_count'}:
        raise ValueError('Invalid daily status fields')
    count = value['change_count']
    if count is not None and (type(count) is not int or count < 0):
        raise ValueError('Invalid daily change count')
    if not isinstance(value['cutoff'], str):
        raise ValueError('Invalid daily cutoff')
    expected_path, expected_value = receipt(value['cutoff'], count)
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


def add_receipt(root, changes, before, cutoff, count):
    """An incomplete retry cannot downgrade an accepted receipt."""
    from pipeline.run_daily import digest
    from pipeline.collectors.browser.collector import json_bytes

    rel, value = receipt(cutoff, count)
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


if __name__ == '__main__':
    validate_tree(Path(__file__).resolve().parents[1])
