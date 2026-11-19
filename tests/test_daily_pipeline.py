"""Feature-only collection, retention, concurrency and publication recovery."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline import collect, run_daily
from pipeline.collectors.browser import Response

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = '2026-11-16T06:00:00Z'


class DailyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'repository'
        self.private = Path(temp.name) / 'scan'
        shutil.copytree(ROOT / 'config', self.root / 'config')
        self.body = (ROOT / 'tests/fixtures/browser/releases.html').read_text().replace('entry-content', 'c-release-notes')
        self.evidence = self.root / 'data/source-items/firefox/firefox-beta.json'
        self.catalog = self.root / 'data/catalog/features/catalog.json'
        self.candidates = self.private / 'work/candidates/firefox-beta.json'

    def scan(self, **kw):
        return collect.collect_sources(self.root, self.private, source_ids=['firefox-beta'], cutoff=CUTOFF,
            transport=lambda url: Response(url, self.body.encode()), **kw)

    def choose(self):
        row = next(row for row in run_daily.read(self.candidates) if row['item_key'] == 'feature-a')
        return [dict(source_item_id=row['source_item_id'], revision_id=row['revisions'][-1]['revision_id'],
                     canonical_key='tab-groups', title='Tab groups')]

    def save(self, decisions, **kw):
        return collect.save_features(self.root, self.private, decisions, **kw)

    def test_collect_and_save_only_feature_evidence(self):
        self.assertTrue(self.scan()['complete'])
        self.assertFalse((self.root / 'data').exists())
        rows = run_daily.read(self.candidates)
        self.assertGreater(len(rows), 1)
        self.assertIn('security', {r['item_type'] for r in rows})
        decisions = self.choose()
        keep = self.private / 'features.json'
        keep.write_text(json.dumps(decisions))
        self.assertEqual(1, self.save(decisions))
        self.assertEqual(['feature-a'], [r['item_key'] for r in run_daily.read(self.evidence)])
        self.assertEqual(['tab-groups'], [r['canonical_key'] for r in run_daily.read(self.catalog)])
        self.assertFalse((self.private / 'work').exists())
        self.assertTrue(keep.exists())
        self.assertEqual(1, self.save(decisions))
        with self.assertRaises(ValueError):
            self.save([])
        with self.assertRaises(ValueError):
            self.scan()

    def test_zero_confirmed_keeps_old_catalog_and_releases_workspace(self):
        self.scan()
        self.save(self.choose())
        before = self.evidence.read_bytes(), self.catalog.read_bytes()
        self.private = self.private.parent / 'next'
        self.scan()
        self.save([])
        self.assertEqual(before, (self.evidence.read_bytes(), self.catalog.read_bytes()))
        self.assertFalse((self.private / 'work').exists())

    def test_unfinished_and_corrupt_inputs_remain_for_retry(self):
        self.scan()
        choices = self.choose()
        for choice in (dict(choices[0], revision_id='stale'), dict(choices[0], source_item_id='missing')):
            with self.assertRaises(ValueError):
                self.save([choice])
        self.candidates.write_text('[]')
        with self.assertRaisesRegex(ValueError, 'collected content'):
            self.save(choices)
        self.assertFalse(self.evidence.exists())
        self.assertTrue(self.candidates.exists())

    def test_partial_requires_explicit_acceptance(self):
        self.body = '<html><main></main></html>'
        self.assertFalse(self.scan()['complete'])
        with self.assertRaisesRegex(ValueError, 'partial'):
            self.save([])
        self.assertFalse(self.scan(resume=True)['complete'])
        self.save([], allow_partial=True)
        self.assertFalse(self.candidates.exists())

    def test_concurrent_store_is_refused(self):
        self.scan()
        with run_daily.run_lock(self.root):
            with self.assertRaisesRegex(RuntimeError, 'lock'):
                self.save(self.choose())

    def test_resume_recovers_interrupted_write(self):
        self.scan()
        decisions = self.choose()
        def interrupt(path, raw):
            run_daily.durable(path, raw)
            raise KeyboardInterrupt()
        def crash(*args):
            run_daily.store_changes(*args, replace=interrupt)
        with patch.object(collect, 'store_changes', crash), self.assertRaises(KeyboardInterrupt):
            self.save(decisions)
        self.assertTrue(self.evidence.exists())
        self.assertFalse(self.catalog.exists())
        self.save(decisions)
        self.assertTrue(self.catalog.exists())
        self.assertFalse(self.candidates.exists())

    def test_unrelated_edit_survives_recovery(self):
        self.scan()
        def crash(*args):
            def interrupt(path, raw):
                run_daily.durable(path, b'user edit')
                raise KeyboardInterrupt()
            run_daily.store_changes(*args, replace=interrupt)
        decisions = self.choose()
        with patch.object(collect, 'store_changes', crash), self.assertRaises(KeyboardInterrupt):
            self.save(decisions)
        with self.assertRaisesRegex(RuntimeError, 'Recovery conflict'):
            self.save(decisions)
        self.assertEqual(b'user edit', self.evidence.read_bytes())
