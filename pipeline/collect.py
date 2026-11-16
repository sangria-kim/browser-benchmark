"""Browser collection entry point; operation records are written only privately.

python -m pipeline.collect --private-dir /outside/repository/state --source firefox-beta
Exit 0 means all requested sources are complete; exit 2 means partial coverage.
"""
import argparse
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from schemas.validate import load_config, validate_record
from pipeline.collectors.browser import BrowserCollector


def collect_browsers(repository, private_dir, source_ids=None, cutoff=None, transport=None, origin='baseline', resume=False):
    repository = Path(repository)
    registry = load_config(repository / 'config/sources.yml')
    validate_record('sources_config', registry)
    known = {s['source_id'] for s in registry['sources']}
    if source_ids and set(source_ids) - known:
        raise ValueError('Unknown source IDs: ' + ', '.join(sorted(set(source_ids) - known)))
    if resume and not cutoff:
        raise ValueError('Resume requires the original explicit cutoff')
    cutoff = cutoff or datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(cutoff.replace('Z', '+00:00')).tzinfo is None:
        raise ValueError('Cutoff needs a timezone')
    collector = BrowserCollector(repository, private_dir, transport, resume=resume)
    return [collector.collect(s, cutoff, registry['baseline']['backfill_since'], origin)
            for s in registry['sources'] if s['enabled'] and (not source_ids or s['source_id'] in source_ids)]



def collect_sources(repository, private_dir, *, kind='browser', source_ids=None, cutoff=None,
                    transport=None, origin='baseline', resume=False, chrome_provider=None,
                    chrome_bundle=None, previous_bundle=None, sample_paths=None, max_files=None, max_trees=None):
    """Collect into a private candidate, normalize, then validate/publish once.

    The original collectors retain their public APIs. This shared entry point
    is the transaction boundary used by daily orchestration. A partial run can
    publish valid retained evidence, but its private status remains partial.
    """
    from pipeline.collectors.chrome import collect as collect_chrome, Gitiles
    from pipeline.normalize import publish
    from scripts.migrate_dataset import prepare
    repository, private_dir = Path(repository).resolve(), Path(private_dir).resolve()
    if kind not in ('browser', 'chrome', 'all'):
        raise ValueError('Unknown collector kind')
    if private_dir == repository or repository in private_dir.parents:
        raise ValueError('Private state must be outside the repository')
    if resume and not cutoff:
        raise ValueError('Resume requires the original explicit cutoff')
    cutoff = cutoff or datetime.now(timezone.utc).isoformat()
    private_dir.mkdir(parents=True, exist_ok=True)
    result = {'browser': [], 'chrome': None}
    with tempfile.TemporaryDirectory(prefix='candidate-', dir=private_dir) as temp:
        stage = Path(temp)
        for name in ('config', 'data', 'features', 'experiments', 'releases'):
            if (repository / name).exists():
                shutil.copytree(repository / name, stage / name)
        if kind in ('browser', 'all'):
            result['browser'] = collect_browsers(stage, private_dir / 'browser', source_ids, cutoff, transport, origin, resume)
        if kind in ('chrome', 'all'):
            if chrome_bundle is None:
                config = load_config(repository / 'config/chrome-source-scope.yml')
                provider = chrome_provider or Gitiles(config['repository_url'], config['baseline_ref'])
                chrome_bundle = collect_chrome(config, provider, private_dir / 'chrome', observed_at=cutoff,
                    origin=origin, sample_paths=sample_paths, max_files=max_files, max_trees=max_trees, previous=previous_bundle)
            result['chrome'] = chrome_bundle['coverage']
        changes = prepare(stage, chrome_bundle if kind in ('chrome', 'all') else None, cutoff)
        result['counts'] = publish(repository, changes, private_dir / 'publication')
    result['complete'] = (all(r['status'] == 'complete' for r in result['browser'])
                          and (result['chrome'] is None or result['chrome']['complete']))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--kind', choices=['browser', 'chrome', 'all'], default='browser')
    parser.add_argument('--source', action='append')
    parser.add_argument('--cutoff')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--origin', choices=['baseline', 'daily', 'backfill'], default='baseline')
    parser.add_argument('--chrome-bundle', type=Path, help='Replay a durable private handoff instead of fetching')
    parser.add_argument('--previous-bundle', type=Path)
    parser.add_argument('--checkout', type=Path)
    parser.add_argument('--revision')
    parser.add_argument('--sample-path', action='append')
    parser.add_argument('--max-files', type=int)
    parser.add_argument('--max-trees', type=int)
    args = parser.parse_args()
    provider = None
    if args.checkout or args.revision:
        from pipeline.collectors.chrome import LocalCheckout, Gitiles
        config = load_config(args.repository / 'config/chrome-source-scope.yml')
        provider = LocalCheckout(args.checkout, args.revision or 'HEAD') if args.checkout else Gitiles(config['repository_url'], args.revision)
    results = collect_sources(args.repository, args.private_dir, kind=args.kind, source_ids=args.source, cutoff=args.cutoff,
        origin=args.origin, resume=args.resume, chrome_provider=provider,
        chrome_bundle=load_config(args.chrome_bundle) if args.chrome_bundle else None,
        previous_bundle=load_config(args.previous_bundle) if args.previous_bundle else None,
        sample_paths=args.sample_path, max_files=args.max_files, max_trees=args.max_trees)
    return 0 if results['complete'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
