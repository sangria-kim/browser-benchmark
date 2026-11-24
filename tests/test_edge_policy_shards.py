"""Round-trip, fail-closed, and next-run contracts for Edge policy buckets."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.collect import collect_sources, save_features
from pipeline.collectors.browser import BrowserCollector
from pipeline.collectors.browser.collector import atomic_bytes, write_edge_shards
from pipeline.normalize import load_dataset
from pipeline.reporting.core import path_index
from pipeline.source_item_shards import (EDGE_POLICY, EDGE_SHARDS, edge_policy_shards,
                                         read_edge_policies)
from schemas.validate import ContractError
from test_browser_collectors import ROOT, response, source


def row(id_tail, revisions=None):
    return {'source_item_id': 'src-' + id_tail.ljust(24, '0'), 'source_id': 'edge-policies',
            'browser': 'edge', 'revisions': revisions or []}


class EdgePolicyShardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        self.private = Path(self.temp.name) / 'private'

    def put(self, rel, value):
        file = self.root / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(value), encoding='utf-8')

    def partition(self, rows):
        parts = edge_policy_shards(rows)
        for rel, value in parts.items():
            self.put(rel, value)
        return parts

    def test_round_trip_preserves_all_fields_revisions_and_order(self):
        rows = [row('00', [{'excerpt': '한글', 'earlier': [1, None, False]},
                           {'excerpt': 'Second'}]), row('0f'), row('ff')]
        self.put(EDGE_POLICY, rows)
        self.assertEqual((rows, False), read_edge_policies(self.root))
        self.assertEqual(rows, load_dataset(self.root)['source_item'])
        (self.root / EDGE_POLICY).unlink()
        parts = self.partition(rows)
        self.assertEqual(tuple(parts), EDGE_SHARDS)
        self.assertEqual(len(parts[EDGE_SHARDS[1]]), 0)
        self.assertEqual((rows, True), read_edge_policies(self.root))
        self.assertEqual(rows, load_dataset(self.root)['source_item'])
        self.assertEqual(parts, edge_policy_shards(rows))

    def test_mixed_missing_unexpected_and_wrong_bucket_rejected(self):
        rows = [row('00')]
        self.partition(rows)
        def reject():
            with self.assertRaises(ContractError):
                read_edge_policies(self.root)
            with self.assertRaises(ContractError):
                load_dataset(self.root)
        self.put(EDGE_POLICY, rows)
        reject()
        (self.root / EDGE_POLICY).unlink()
        (self.root / EDGE_SHARDS[-1]).unlink()
        reject()
        self.put(EDGE_SHARDS[-1], [])
        wrong = EDGE_SHARDS[-1].replace('ff.json', 'gg.json')
        self.put(wrong, [])
        reject()
        (self.root / wrong).unlink()
        self.put(EDGE_SHARDS[-1], rows)
        reject()
        self.put(EDGE_SHARDS[-1], [])
        self.put(EDGE_SHARDS[0], rows + rows)
        reject()

    def test_no_silent_reordering_or_oversize_bucket(self):
        with self.assertRaises(ContractError):
            edge_policy_shards([row('ff'), row('00')])
        with self.assertRaises(ContractError):
            edge_policy_shards([row('00'), row('00')])
        with patch('pipeline.source_item_shards.MAX_SHARD_BYTES', 100):
            with self.assertRaisesRegex(ContractError, 'storage limit'):
                edge_policy_shards([row('00', [{'excerpt': '가' * 50}])])

    def test_failed_write_rolls_back_exact_bytes_and_same_input_can_retry(self):
        prior = [row('00'), row('ff')]
        self.partition(prior)
        before = {p: (self.root / p).read_bytes() for p in EDGE_SHARDS}
        next_rows = [row('00', [{'excerpt': '새 기록'}]), row('ff', [{'excerpt': 'More'}])]
        calls = []
        def fail_second(path, raw):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('synthetic interrupted write')
            atomic_bytes(path, raw)
        with self.assertRaises(OSError):
            write_edge_shards(self.root, next_rows, write=fail_second)
        self.assertEqual(before, {p: (self.root / p).read_bytes() for p in EDGE_SHARDS})
        write_edge_shards(self.root, next_rows)
        self.assertEqual((next_rows, True), read_edge_policies(self.root))
        write_edge_shards(self.root, next_rows, write=lambda *_: self.fail('deterministic rerun should not write'))

    def test_next_collection_retains_shard_paths_and_prior_revision(self):
        shutil.copytree(ROOT / 'config', self.root / 'config')
        config = source('edge-policies')
        config['enabled'] = True
        registry = json.loads((self.root / 'config/sources.yml').read_text())
        registry['sources'] = [config if s['source_id'] == config['source_id'] else s
                               for s in registry['sources']]
        self.put('config/sources.yml', registry)
        url = config['url'] + '/fixture'
        def collect_fixture(collector):
            for key, message in current.items():
                collector.emit(url, response(url, message),
                               {'key': key, 'section': 'Policy', 'text': message, 'parsed': True},
                               date='2026-11-15')
            collector.state['pagination_exhausted'] = True
        current = {'one': 'Initial policy text.', 'two': 'Retained policy text.'}
        with patch.object(BrowserCollector, 'collect_html', collect_fixture):
            BrowserCollector(self.root, self.private).collect(config, '2026-11-16T00:00:00Z', '2026-01-01')
            previous, mode = read_edge_policies(self.root)
            self.assertFalse(mode)
            self.assertEqual(2, len(previous))
            self.partition(previous)
            (self.root / EDGE_POLICY).unlink()
            paths = path_index(self.root, {})
            current = {'one': 'Changed policy text.', 'three': 'New policy text.'}
            result = collect_sources(self.root, self.private / 'next', source_ids=['edge-policies'],
                                     cutoff='2026-11-17T00:00:00Z', origin='daily')
        self.assertTrue(result['complete'])
        self.assertEqual(previous, read_edge_policies(self.root)[0])
        candidates = json.loads((self.private / 'next/work/candidates/edge-policies.json').read_text())
        save_features(self.root, self.private / 'next', [
            dict(source_item_id=r['source_item_id'], revision_id=r['revisions'][-1]['revision_id'],
                 canonical_key=r['item_key'], title=r['title']) for r in candidates])
        latest, mode = read_edge_policies(self.root)
        self.assertTrue(mode)
        self.assertEqual(3, len(latest))
        by_id = {r['source_item_id']: r for r in latest}
        paths_after = path_index(self.root, {})
        for old in previous:
            ident = old['source_item_id']
            self.assertEqual(paths['source_item', ident], paths_after['source_item', ident])
            self.assertEqual(old['revisions'], by_id[ident]['revisions'][:len(old['revisions'])])
        self.assertEqual(2, len(next(r['revisions'] for r in latest if r['item_key'] == 'one')))
        self.assertEqual(set(EDGE_SHARDS), {p.relative_to(self.root).as_posix()
                         for p in (self.root / EDGE_POLICY).parent.glob('*.json')})
