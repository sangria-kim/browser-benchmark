import argparse
import json
from .core import load_rules, run

parser = argparse.ArgumentParser(description='Evaluate public evidence without credentials.')
parser.add_argument('--repository', default='.')
parser.add_argument('--private-dir', required=True)
parser.add_argument('--assessed-at', required=True, help='Explicit ISO 8601 evaluation time')
parser.add_argument('--rules')
parser.add_argument('--revisit', help='JSON object mapping subject IDs to durable trigger tokens')
parser.add_argument('--decisions', help='Private JSON object: subject IDs to structured provider decisions')
parser.add_argument('--model-id', help='Real model identity that produced --decisions; never label authored rules as a model')
parser.add_argument('--dry-run', action='store_true')
args = parser.parse_args()
decisions = json.load(open(args.decisions)) if args.decisions else None
result = run(args.repository, args.private_dir, assessed_at=args.assessed_at,
             rules=load_rules(args.rules), revisit=json.load(open(args.revisit)) if args.revisit else None,
             provider=(lambda context, rules: decisions[context['subject_id']]) if decisions is not None else None,
             model_id=args.model_id,
             dry_run=args.dry_run)
print(json.dumps({'created': len(result['created']), 'imported': len(result['imported']),
                  'cached': result['cached'], 'failed': len(result['failures']),
                  'selected': {k: len(v['current']) for k, v in result['selected'].items()}}))
raise SystemExit(2 if result['failures'] else 0)
