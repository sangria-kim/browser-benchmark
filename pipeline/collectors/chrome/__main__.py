"""Run with python -m pipeline.collectors.chrome --help."""
import argparse
import json
from pathlib import Path

from schemas.validate import load_config
from . import collect, Gitiles, LocalCheckout
from .providers import atomic_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', default='config/chrome-source-scope.yml')
    parser.add_argument('--checkout')
    parser.add_argument('--revision', help='Pinned commit or ref; default is configured main')
    parser.add_argument('--state-dir', required=True, help='Private state outside this repository; one directory per pinned run')
    parser.add_argument('--sample-path', action='append', help='Bounded sample; always partial')
    parser.add_argument('--max-files', type=int)
    parser.add_argument('--max-trees', type=int)
    parser.add_argument('--previous-bundle', help='Private handoff from prior pinned revision')
    parser.add_argument('--baseline-bundle', help='Same-parser verified pre-window handoff for endpoint comparison')
    parser.add_argument('--boundary-time', help='Verified baseline commit timestamp; must precede KST Jan1')
    parser.add_argument('--current-time', help='Verified current commit timestamp; must not exceed its source cutoff')
    parser.add_argument('--cutoff', help='Frozen evidence window for the endpoint comparison')
    args = parser.parse_args()
    config = load_config(args.config)
    provider = LocalCheckout(args.checkout, args.revision or 'HEAD') if args.checkout else Gitiles(config['repository_url'], args.revision or config['baseline_ref'])
    previous = json.loads(Path(args.previous_bundle).read_text()) if args.previous_bundle else None
    result = collect(config, provider, args.state_dir, sample_paths=args.sample_path,
                     max_files=args.max_files, max_trees=args.max_trees, previous=previous)
    if args.baseline_bundle:
        if not args.boundary_time or not args.current_time or not args.cutoff:
            parser.error('--baseline-bundle needs --boundary-time, --current-time and --cutoff')
        from .temporal import compare
        result = compare(result, load_config(args.baseline_bundle),
            since=config['baseline']['historical_backfill_since'], cutoff=args.cutoff, boundary_time=args.boundary_time, current_time=args.current_time)
        atomic_json(Path(args.state_dir) / 'handoff.json', result)
    print(json.dumps({'revision': result['revision'], 'coverage': result['coverage'], 'handoff': str(Path(args.state_dir) / 'handoff.json')}, indent=2))
    return 0 if result['coverage']['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
