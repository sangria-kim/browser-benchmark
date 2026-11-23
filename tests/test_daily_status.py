"""Exercise what the consumer can infer from the exact scheduled result."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline import collect, run_daily
from pipeline.collectors.browser import BrowserCollector, Response
from pipeline.daily_status import validate_receipt, validate_tree

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = '2026-11-16T23:00:00Z'
REL = 'data/daily-status/2026-11-17.json'


class StatusTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.root = self.dir / 'repo'
        self.run = self.dir / 'collection'
        shutil.copytree(ROOT / 'config', self.root / 'config')
        self.registry = self.root / 'config/sources.yml'
        self.configure({'firefox-beta'})
        self.status = self.root / REL
        self.body = (ROOT / 'tests/fixtures/browser/releases.html').read_text().replace('entry-content', 'c-release-notes')
        self.body = self.body.replace('Tab grouping added.</li>',
                                      'Tab grouping added.</li><li id="feature-b">Tab grouping now available.</li>')

    def configure(self, enabled):
        data = json.loads(self.registry.read_bytes())
        others = {}
        for source in data['sources']:
            if source['browser'] != 'firefox':
                others.setdefault(source['browser'], source['source_id'])
        for source in data['sources']:
            source['enabled'] = source['source_id'] in enabled | set(others.values())
        self.registry.write_text(json.dumps(data))

    def scan(self, cutoff=CUTOFF, incomplete_source=None, **options):
        real_collect = BrowserCollector.collect

        def synthetic_coverage(collector, source, boundary, since, origin):
            sid = source['source_id']
            if sid == 'firefox-beta':
                return real_collect(collector, source, boundary, since, origin)
            collector.parsed_ids = set()
            return dict(source_id=sid, cutoff=boundary,
                        status='partial' if sid == incomplete_source else 'complete')

        with patch.object(BrowserCollector, 'collect', synthetic_coverage):
            return collect.collect_sources(self.root, self.run, cutoff=cutoff, daily_status=True,
                transport=lambda url: Response(url, self.body.encode()), **options)

    def decisions(self, kind='product_change'):
        rows = json.loads((self.run / 'work/candidates/firefox-beta.json').read_bytes())
        return [dict(source_item_id=row['source_item_id'],
                     revision_id=row['revisions'][-1]['revision_id'],
                     canonical_key='tab-groups', title='Tab groups', change_kind=kind)
                for row in rows if row['item_key'] in ('feature-a', 'feature-b')]

    def test_confirmed_empty_collection_creates_valid_zero(self):
        self.assertTrue(self.scan()['complete'])
        self.assertFalse(self.status.exists())
        self.assertEqual(0, collect.save_features(self.root, self.run, []))
        self.assertEqual(dict(date='2026-11-17', cutoff='2026-11-17T08:00:00+09:00',
                              status='complete', change_count=0), json.loads(self.status.read_bytes()))
        validate_tree(self.root)
        self.assertFalse((self.root / collect.FEATURE_CATALOG).exists())

    def test_complete_subset_is_not_a_complete_day(self):
        self.configure({'firefox-beta', 'firefox-ios'})
        self.assertTrue(self.scan(source_ids=['firefox-beta'])['complete'])
        with self.assertRaisesRegex(ValueError, 'all pinned sources'):
            collect.save_features(self.root, self.run, [], allow_partial=True)
        collect.mark_incomplete(self.root, self.run)
        record = json.loads(self.status.read_bytes())
        self.assertEqual(('incomplete', None), (record['status'], record['change_count']))
        self.assertTrue((self.run / 'work/candidates/firefox-beta.json').exists())
        self.assertFalse((self.root / collect.FEATURE_CATALOG).exists())

    def test_full_run_with_one_source_failure_has_null_count(self):
        self.configure({'firefox-beta', 'firefox-ios'})
        self.assertFalse(self.scan(incomplete_source='firefox-ios')['complete'])
        collect.mark_incomplete(self.root, self.run)
        self.assertIsNone(json.loads(self.status.read_bytes())['change_count'])
        self.assertFalse((self.root / collect.FEATURE_CATALOG).exists())

    def test_two_citations_for_one_feature_count_once(self):
        self.scan()
        choices = self.decisions()
        self.assertEqual(2, len(choices))
        self.assertEqual(2, collect.save_features(self.root, self.run, choices))
        self.assertEqual(1, json.loads(self.status.read_bytes())['change_count'])
        catalog, = json.loads((self.root / collect.FEATURE_CATALOG).read_bytes())
        self.assertEqual(2, len(catalog['source_item_ids']))

    def test_evidence_only_for_an_existing_feature_counts_zero(self):
        self.scan()
        collect.save_features(self.root, self.run, self.decisions())
        self.run = self.dir / 'next'
        self.body = self.body.replace('Tab grouping now available.', 'Updated grouping help link.')
        next_cutoff = '2026-11-17T23:00:00Z'
        self.scan(cutoff=next_cutoff)
        choice = self.decisions('evidence_only')
        self.assertTrue(choice)
        collect.save_features(self.root, self.run, choice)
        self.assertEqual(0, json.loads((self.root / 'data/daily-status/2026-11-18.json').read_bytes())['change_count'])

    def test_same_cutoff_with_different_feature_and_same_count_is_rejected(self):
        self.scan()
        collect.save_features(self.root, self.run, self.decisions())
        catalog = self.root / collect.FEATURE_CATALOG
        prior = catalog.read_bytes(), self.status.read_bytes()
        self.run = self.dir / 'same-cutoff-different-feature'
        self.scan()
        new = [dict(choice, canonical_key='another-feature', title='Another feature')
               for choice in self.decisions()]
        with self.assertRaisesRegex(ValueError, 'after the daily status is complete'):
            collect.save_features(self.root, self.run, new)
        self.assertEqual(prior, (catalog.read_bytes(), self.status.read_bytes()))

    def test_wrong_scope_or_altered_candidates_never_certify_zero(self):
        with self.assertRaisesRegex(ValueError, 'daily origin'):
            self.scan(origin='backfill')
        self.scan()
        candidates = self.run / 'work/candidates/firefox-beta.json'
        candidates.write_text('[]')
        with self.assertRaisesRegex(ValueError, 'candidates differ'):
            collect.save_features(self.root, self.run, [])
        self.assertFalse(self.status.exists())

    def test_registry_changes_invalidate_the_pinned_coverage(self):
        self.scan()
        self.configure({'firefox-beta', 'firefox-ios'})
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            collect.save_features(self.root, self.run, [])
        self.assertFalse(self.status.exists())

    def test_incomplete_can_recover_but_cannot_downgrade_complete(self):
        self.scan()
        collect.mark_incomplete(self.root, self.run)
        collect.save_features(self.root, self.run, [])
        complete = self.status.read_bytes()
        self.run = self.dir / 'same-day-retry'
        self.scan()
        collect.mark_incomplete(self.root, self.run)
        self.assertEqual(complete, self.status.read_bytes())

    def test_failure_after_status_write_rolls_back_status_and_feature_files(self):
        self.scan()
        original = collect.store_changes

        def inject(root, txn, changes, before, writer):
            def fail_after_status(path, value):
                run_daily.durable(path, value)
                if path == self.status.resolve():
                    raise OSError('synthetic write failure')
            return original(root, txn, changes, before, writer, replace=fail_after_status)

        with patch.object(collect, 'store_changes', inject), self.assertRaises(OSError):
            collect.save_features(self.root, self.run, self.decisions())
        self.assertFalse(self.status.exists())
        self.assertFalse((self.root / collect.FEATURE_CATALOG).exists())
        self.assertFalse((self.root / 'data/source-items/firefox/firefox-beta.json').exists())
        collect.save_features(self.root, self.run, self.decisions())
        self.assertEqual(1, json.loads(self.status.read_bytes())['change_count'])

    def test_catalog_drift_does_not_silently_certify_zero(self):
        self.scan()
        catalog = self.root / collect.FEATURE_CATALOG
        catalog.parent.mkdir(parents=True)
        catalog.write_text('[]')
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            collect.save_features(self.root, self.run, [])
        self.assertFalse(self.status.exists())

    def test_misclassified_new_feature_cannot_be_saved_as_evidence_only(self):
        self.scan()
        with self.assertRaisesRegex(ValueError, 'existing feature'):
            collect.save_features(self.root, self.run, self.decisions('evidence_only'))
        self.assertFalse(self.status.exists())

    def test_receipt_directory_must_not_be_a_symlink(self):
        self.scan()
        self.status.parent.parent.mkdir()
        target = self.root / 'different-directory'
        target.mkdir()
        self.status.parent.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Unsafe daily status target'):
            collect.mark_incomplete(self.root, self.run)
        with self.assertRaisesRegex(ValueError, 'Invalid daily status folder'):
            validate_tree(self.root)
        self.assertEqual([], list(target.iterdir()))

    def test_receipt_contract_rejects_invalid_state_count_and_day(self):
        valid = dict(date='2026-11-17', cutoff='2026-11-17T08:00:00+09:00',
                     status='complete', change_count=0)
        validate_receipt(REL, valid)
        for invalid in [dict(valid, change_count=True), dict(valid, status='incomplete'),
                        dict(valid, cutoff='2026-11-17T08:00:00Z'),
                        dict(valid, date='2026-11-16'), dict(valid, diagnostic='private')]:
            with self.assertRaises(ValueError):
                validate_receipt(REL, invalid)
