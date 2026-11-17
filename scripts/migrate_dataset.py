#!/usr/bin/env python3
"""Migrate legacy evidence and normalize a durable Chromium bundle, without PM.

python -m scripts.migrate_dataset --private-dir /private/state --chrome-bundle /private/handoff.json
All public files are staged and graph-validated before publication. A dry run
performs the same validation. Original release and Markdown files are preserved.
"""
import argparse
import copy
from datetime import datetime, timezone
from pathlib import Path

from schemas.validate import load_config
from pipeline.normalize import load_dataset, normalize_chrome, publish, validate_graph, merge_sources
from pipeline.normalize.core import normalize_browser_catalog
from pipeline.normalize.legacy import migrate_events, migrate_flag_documents, compatibility_index, resolve_predecessors


def prepare(repository, chrome_bundle=None, observed_at=None):
    root = Path(repository)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    old = load_dataset(root)
    legacy_sources, features, events = migrate_events(old['feature_event'], old['feature'])
    predecessor_sources, events = resolve_predecessors(root, events)
    _, features, events = migrate_events(events, features)
    sources = merge_sources(old['source_item'], legacy_sources + predecessor_sources)
    experiments, experiment_events = old['experiment'], old['experiment_event']
    if chrome_bundle is not None:
        from pipeline.normalize.core import attach_accepted_chrome_history
        chrome_bundle = attach_accepted_chrome_history(chrome_bundle, sources)
        sources = merge_sources(sources, chrome_bundle['source_items'])
        experiments, experiment_events = normalize_chrome(chrome_bundle, sources, experiments, experiment_events, observed_at=observed_at)
    flag_sources, experiments = migrate_flag_documents(root, experiments, observed_at, sources)
    sources = merge_sources(sources, flag_sources)
    features = normalize_browser_catalog(sources, features, events)
    if any('temporal_scope' in s for s in sources):
        from pipeline.temporal import project_legacy
        registry = load_config(root / 'config/sources.yml')
        project_legacy(sources, features, events, experiments, registry['baseline']['backfill_since'], observed_at)
        if chrome_bundle and chrome_bundle.get('temporal_comparison'):
            current_ids = {e['experiment_id'] for e in chrome_bundle['experiments']}
            current_sources = {s['source_item_id'] for s in chrome_bundle['source_items']}
            for record in experiments + sources:
                retained = (record.get('experiment_id') not in current_ids if 'experiment_id' in record else
                            record['source_id'] == 'chromium-source' and record['source_item_id'] not in current_sources)
                if retained:
                    record['temporal_scope'].update(status='context', change='unknown',
                        reason='Retained accepted identity is not in the current endpoint projection. No product removal is inferred.')
    changes = {}
    for event in old['feature_event']:
        if event['schema_version'] == 1:
            changes['data/event-revisions/' + event['event_id'] + '/schema-v1.json'] = event
    # Preserve all existing source file ownership; put new legacy evidence in
    # its own browser shard. A collection retry cannot erase historical sources.
    locations = {}
    for path in sorted((root / 'data/source-items').glob('*/*.json')):
        for row in load_config(path):
            locations[row['source_item_id']] = str(path.relative_to(root))
    shards = {}
    for source in sources:
        rel = locations.get(source['source_item_id'])
        if rel is None:
            rel = ('data/source-items/' + source['browser'] + '/legacy.json') if source['source_id'] == 'legacy' else 'data/source-items/chrome-experiments/collected.json'
        shards.setdefault(rel, []).append(source)
    changes.update({p: sorted(rows, key=lambda x: x['source_item_id']) for p, rows in shards.items()})
    changes['data/catalog/features/catalog.json'] = sorted(features, key=lambda x: x['feature_id'])
    changes['data/catalog/chrome-experiments/catalog.json'] = sorted(experiments, key=lambda x: x['experiment_id'])
    for event in events:
        changes['data/events/' + event['event_id'] + '.json'] = event
    changes['data/experiment-events/events.json'] = sorted(experiment_events, key=lambda x: x['event_id'])
    alias_path = root / 'data/aliases/corrections.json'
    changes['data/aliases/corrections.json'] = load_config(alias_path) if alias_path.exists() else []
    if chrome_bundle is not None:
        from pipeline.normalize.corrections import parser_aliases
        incoming_ids = {e['experiment_id'] for e in chrome_bundle['experiments']}
        incoming = [e for e in experiments if e['experiment_id'] in incoming_ids]
        changes['data/aliases/corrections.json'] = parser_aliases(old['experiment'], incoming, changes['data/aliases/corrections.json'])
    changes['data/compatibility/legacy-index.json'] = compatibility_index(root, features, experiments)
    validate_graph(root, changes)
    return changes


def migrate(repository, private_dir, chrome_bundle=None, observed_at=None, dry_run=False):
    changes = prepare(repository, chrome_bundle, observed_at)
    if dry_run:
        return {k: len(v) for k, v in validate_graph(repository, changes).items()}
    return publish(repository, changes, private_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--private-dir', type=Path, required=True)
    parser.add_argument('--chrome-bundle', type=Path)
    parser.add_argument('--observed-at')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    result = migrate(args.repository, args.private_dir, load_config(args.chrome_bundle) if args.chrome_bundle else None, args.observed_at, args.dry_run)
    # Counts are command output, not a committed operations record.
    print(result)


if __name__ == '__main__':
    main()
