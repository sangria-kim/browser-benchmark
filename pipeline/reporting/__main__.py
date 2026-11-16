"""Create a daily KST report from stored judgments and evidence."""
import argparse
import json
from pathlib import Path
from .core import run, STATES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path.cwd())
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--date', required=True)
    parser.add_argument('--cutoff', required=True)
    parser.add_argument('--previous-cutoff')
    parser.add_argument('--collection', choices=STATES, default='unknown')
    parser.add_argument('--evaluation', choices=STATES, default='unknown')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    result = run(args.repository, args.private_dir, day=args.date, cutoff=args.cutoff,
                 previous_cutoff=args.previous_cutoff, collection=args.collection,
                 evaluation=args.evaluation, dry_run=args.dry_run)
    report = result['report']
    print(json.dumps({key: report[key] for key in ('report_id', 'revision', 'markdown_path', 'outcome', 'completeness')}, ensure_ascii=False))
    return 0 if args.collection == args.evaluation == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
