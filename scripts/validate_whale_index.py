"""Validate explicit Whale body indexes; no network, scheduling or checkpoint writes.
Usage: python3 scripts/validate_whale_index.py [INDEX ...]
Without paths, validate all items-*-backfill-*.json under releases/whale.
"""
import collections
import json
from pathlib import Path
import sys


def validate(data):
    def require(condition, message):
        if not condition:
            raise ValueError(message)
    require(data.get('schema_version') == 1, 'schema_version must be 1')
    require(data.get('browser') == 'whale', 'browser must be whale')
    require(data.get('product') in ('Desktop', 'Android', 'iOS'), 'explicit product required')
    require(data.get('collection_scope') == 'single_official_body', 'body scope required')
    require(data.get('collection_status') in ('success', 'partial', 'failed'), 'invalid status')
    items = data.get('items', [])
    require(isinstance(items, list), 'items must be an array')
    counts = collections.Counter()
    ids = set()
    numbers = collections.defaultdict(set)
    required = {'item_id', 'browser', 'version', 'product', 'platform', 'summary',
                'sources', 'section', 'source_item_number', 'event_type', 'observed_at',
                'announced_at', 'effective_at', 'selection_status', 'selection_reason',
                'priority', 'priority_reason', 'comparison_question', 'benchmark_readiness',
                'revisit_trigger', 'assessed_at', 'selection_rule_version', 'novelty'}
    for item in items:
        require(required <= item.keys(), 'missing item fields')
        require(item['item_id'] not in ids, 'duplicate item_id')
        ids.add(item['item_id'])
        for key in ('browser', 'version', 'product'):
            require(item[key] == data[key], 'mixed ' + key)
        require(item['platform'] == [data['product']] if data['product'] != 'Desktop'
                else isinstance(item['platform'], list), 'platform mismatch')
        require(item['sources'] == [data['source_url']], 'source mismatch')
        require(item['event_type'] in ('improvement', 'fix'), 'invalid item kind')
        require(item['summary'].strip(), 'empty summary')
        require(item['selection_status'] in ('selected', 'watch', 'pending_verification', 'excluded'), 'invalid selection')
        require(item['selection_rule_version'] == 'pm-selection-v2', 'selection rule mismatch')
        require(item['priority'] in (None, 'P1', 'P2'), 'invalid priority')
        if item['novelty'] in ('historical_baseline', 'historical_backfill'):
            require(item['selection_status'] != 'selected', 'historical item cannot trigger new report')
        kind = item['event_type']
        require(item['source_item_number'] not in numbers[kind], 'duplicate source ordinal')
        numbers[kind].add(item['source_item_number'])
        counts[kind] += 1
    expected = data.get('expected_counts')
    require(isinstance(expected, dict) and set(expected) == {'improvement', 'fix'}, 'expected counts required')
    require(all(type(n) is int and n >= 0 for n in expected.values()), 'invalid expected counts')
    if data['collection_status'] == 'success':
        require(bool(items), 'empty body is not success')
        require(all(counts[kind] == count for kind, count in expected.items()),
                'incomplete body counts')
        for kind, count in expected.items():
            require(numbers[kind] == set(range(1, count + 1)), 'noncontiguous source ordinals')
    return len(items)


def main():
    paths = [Path(p) for p in sys.argv[1:]] or sorted(Path('releases/whale').glob('*/items-*-backfill-*.json'))
    if not paths:
        raise ValueError('no indexes found')
    total = 0
    ids = set()
    for path in paths:
        data = json.loads(path.read_text(encoding='utf-8'))
        total += validate(data)
        current = {item['item_id'] for item in data['items']}
        if ids & current:
            raise ValueError('duplicate item_id across indexes')
        ids |= current
    print(f'Validated {len(paths)} body indexes, {total} items')

if __name__ == '__main__':
    main()
