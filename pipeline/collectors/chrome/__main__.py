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
    parser.add_argument('--output', help='Public schema-v2 source array, never an operations report')
    parser.add_argument('--sample-path', action='append', help='Bounded sample; always partial')
    parser.add_argument('--max-files', type=int)
    parser.add_argument('--max-trees', type=int)
    parser.add_argument('--previous-bundle', help='Private handoff from prior pinned revision')
    args = parser.parse_args()
    config = load_config(args.config)
    provider = LocalCheckout(args.checkout, args.revision or 'HEAD') if args.checkout else Gitiles(config['repository_url'], args.revision or config['baseline_ref'])
    previous = json.loads(Path(args.previous_bundle).read_text()) if args.previous_bundle else None
    result = collect(config, provider, args.state_dir, sample_paths=args.sample_path,
                     max_files=args.max_files, max_trees=args.max_trees, previous=previous)
    if args.output:
        atomic_json(args.output, result['source_items'])
    print(json.dumps({'revision': result['revision'], 'coverage': result['coverage'], 'handoff': str(Path(args.state_dir) / 'handoff.json')}, indent=2))
    return 0 if result['coverage']['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
