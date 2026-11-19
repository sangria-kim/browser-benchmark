"""Save missing newsletter editions from frozen reports and dashboard settings."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline.normalize.storage import records
from pipeline.reporting.newsletter import newsletter_files, read
from pipeline.run_daily import durable, run_lock


def archive(root):
    root = Path(root).resolve()
    with run_lock(root):
        reports = [read(p) for p in sorted(root.glob('data/reports/history/*/revision-*.json'))]
        if not reports:
            return []
        events = [row for p in sorted(root.glob('data/events/*.json')) for row in records(read(p))]
        selection = read(root / 'data/selected/features/current.json')
        current = max(reports, key=lambda r: (r['date'], r['revision']))
        files = newsletter_files(root, {'report': reports, 'feature_event': events}, current, selection)
        paths = []
        for rel, body in files.items():
            path = root / 'dashboard/daily/editions' / Path(rel).relative_to('reports/generated')
            durable(path, body.encode())
            paths.append(path)
        return paths


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=ROOT)
    print(json.dumps({'created': len(archive(parser.parse_args().repository))}))
