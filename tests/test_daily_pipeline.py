"""Feature-only collection, retention, concurrency and publication recovery."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline import collect, run_daily
from pipeline.collectors.browser import Response
from pipeline.selection import run as run_selection
from pipeline.selection.core import decision
from schemas.validate import ContractError
from scripts import build_dashboard

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

    @property
    def candidates(self):
        return self.private / 'work/candidates/firefox-beta.json'

    def scan(self, **kw):
        return collect.collect_sources(self.root, self.private, source_ids=['firefox-beta'], cutoff=CUTOFF,
            transport=lambda url: Response(url, self.body.encode()), **kw)

    def choose(self):
        row = next(row for row in run_daily.read(self.candidates) if row['item_key'] == 'feature-a')
        return [dict(source_item_id=row['source_item_id'], revision_id=row['revisions'][-1]['revision_id'],
                     canonical_key='tab-groups', title='Tab groups')]

    def save(self, decisions, **kw):
        return collect.save_features(self.root, self.private, decisions, **kw)

    def dashboard(self):
        (self.root / 'dashboard').mkdir(exist_ok=True)
        (self.root / 'dashboard/card-summaries.json').write_text('{}')
        legacy = dict(events=[], flags=[], source={}, built_at=CUTOFF, updated_at=CUTOFF, catalog={})
        output = self.root.parent / 'site'
        with patch.object(build_dashboard, 'ROOT', self.root):
            build_dashboard.build_research(output, legacy, '')
        return output

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

    def test_one_source_revision_can_support_two_features(self):
        self.body = self.body.replace('Tab grouping added.', 'Share tab groups and customize captions per site.')
        self.scan()
        first, = self.choose()
        second = dict(first, canonical_key='site-captions', title='Site captions')
        with self.assertRaises(ValueError):
            self.save([first, first])
        self.assertEqual(2, self.save([first, second]))
        self.assertEqual(1, len(run_daily.read(self.evidence)))
        catalog = run_daily.read(self.catalog)
        self.assertEqual({'tab-groups', 'site-captions'}, {f['canonical_key'] for f in catalog})
        for feature in catalog:
            self.assertEqual({first['source_item_id']: [first['revision_id']]}, feature['source_revision_ids'])

    def test_reused_anchor_displays_the_revision_confirmed_for_each_feature(self):
        self.scan()
        first, = self.choose()
        self.save([first])
        self.private = self.private.parent / 'next'
        self.body = self.body.replace('Tab grouping added.', 'Translate a PDF.')
        self.scan()
        second = dict(self.choose()[0], canonical_key='pdf-translation', title='PDF translation')
        self.assertEqual(first['source_item_id'], second['source_item_id'])
        self.assertNotEqual(first['revision_id'], second['revision_id'])
        self.save([second])

        output = self.dashboard()
        rows = build_dashboard.read_resource(output / 'indexes/feature.json.gz')
        evidence = {r['title']: build_dashboard.read_resource(output / r['detail'])['evidence'] for r in rows}
        for decision, excerpt in [(first, 'Tab grouping added.'), (second, 'Translate a PDF.')]:
            citation, = evidence[decision['title']]
            self.assertEqual(excerpt, citation['excerpt'])
            self.assertEqual(decision['revision_id'], citation['revision_id'])

    def test_two_selected_sources_keep_their_dashboard_cards_after_linking_one_feature(self):
        self.body = self.body.replace('Tab grouping added.</li>',
            'You can now group tabs into named workspaces.</li>'
            '<li id="feature-b">Users can now share saved tab groups with other users.</li>')
        self.scan()
        rows = [r for r in run_daily.read(self.candidates) if r['item_key'] in ('feature-a', 'feature-b')]
        self.evidence.parent.mkdir(parents=True)
        self.evidence.write_text(json.dumps(rows))

        def select(context, rules):
            result = decision('selected', 'Tab groups changed.', priority='P2',
                              question='Can users group their tabs?', readiness='conditional')
            source, = context['sources']
            result['evidence_source_item_ids'] = [source['source_item_id']]
            result['benchmark'] = dict(user_impact='Group tabs.', material_change='Named groups.',
                steps=['Create a group'], metrics=['Completion'], conditions='Beta channel',
                completion='Group exists', evidence_quotes=[source['evidence']['excerpt']])
            return result

        historical = run_selection(self.root, self.root.parent / 'selection', assessed_at=CUTOFF,
                                   provider=select, model_id='fixture')
        current = historical['selected']['features']['current']
        self.assertEqual(2, len(current))
        expected = {(r['subject_id'], r['assessment_id'], r['catalog_id']) for r in current}
        selection_path = self.root / 'data/selected/features/current.json'
        selection = run_daily.read(selection_path)
        for change in selection['history']:
            del change['catalog_id']
        selection_path.write_text(json.dumps(selection))
        decisions = [dict(canonical_key='tab-groups', title='Tab groups', source_item_id=r['source_item_id'],
                          revision_id=r['revisions'][-1]['revision_id']) for r in rows]
        self.assertEqual(2, self.save(decisions))
        output = self.dashboard()
        dashboard = build_dashboard.read_resource(output / 'data.json')
        day, = dashboard['dates']
        for cards in (dashboard['selected']['features'], build_dashboard.read_resource(output / day['path'])['rows']):
            self.assertEqual(expected, {(r['id'], r['assessment_id'], r['catalog_id']) for r in cards})
            self.assertTrue(all(r['current_selected'] for r in cards))
        feature, = build_dashboard.read_resource(output / 'indexes/feature.json.gz')
        detail = build_dashboard.read_resource(output / feature['detail'])
        self.assertEqual({r['evidence']['excerpt'] for r in rows}, {e['excerpt'] for e in detail['evidence']})

        # Imported assessments can precede the first published snapshot.
        for path in (self.root / 'data/selected').rglob('*.json'):
            snapshot = run_daily.read(path)
            snapshot['as_of'] = '2026-11-17T06:00:00Z'
            path.write_text(json.dumps(snapshot))
        output = self.dashboard()
        past = build_dashboard.read_resource(output / day['path'])
        self.assertEqual(expected, {(r['id'], r['assessment_id'], r['catalog_id']) for r in past['rows']})

    def test_two_feature_quotes_survive_cleanup_including_text_after_character_220(self):
        start = 'Tab grouping added.'
        end = 'PDF documents can now be translated.'
        filler = 'Release background. ' * 15
        self.body = self.body.replace(start, start + ' ' + filler + end)
        self.scan()
        first, = self.choose()
        first['evidence_quote'] = start
        second = dict(first, canonical_key='translate-pdf', title='Translate PDF', evidence_quote=end)
        for invalid in ({k: v for k, v in second.items() if k != 'evidence_quote'},
                        dict(second, evidence_quote='Text from a different item.')):
            with self.assertRaisesRegex(ValueError, 'evidence_quote'):
                self.save([first, invalid])
            self.assertTrue(self.candidates.exists())
            self.assertFalse(self.evidence.exists())
        self.assertEqual(2, self.save([first, second]))
        self.assertFalse((self.private / 'work').exists())
        self.assertNotIn(filler, self.catalog.read_text() + self.evidence.read_text())
        output = self.dashboard()
        rows = build_dashboard.read_resource(output / 'indexes/feature.json.gz')
        for r in rows:
            citation, = build_dashboard.read_resource(output / r['detail'])['evidence']
            self.assertEqual(start if r['title'] == first['title'] else end, citation['excerpt'])
            self.assertEqual(first['revision_id'], citation['revision_id'])

    def test_existing_feature_without_pins_keeps_its_last_displayed_revision(self):
        self.scan()
        first, = self.choose()
        self.save([first])
        legacy = run_daily.read(self.catalog)
        legacy[0].pop('source_revision_ids')
        self.catalog.write_text(json.dumps(legacy))
        self.private = self.private.parent / 'next'
        self.body = self.body.replace('Tab grouping added.', 'Translate a PDF.')
        self.scan()
        second = dict(self.choose()[0], canonical_key='pdf-translation', title='PDF translation')
        self.save([second])
        expected = {choice['canonical_key']: {choice['source_item_id']: [choice['revision_id']]}
                    for choice in [first, second]}
        self.assertEqual(expected, {f['canonical_key']: f['source_revision_ids'] for f in run_daily.read(self.catalog)})

    def test_empty_classification_detects_missing_evidence_and_can_retry(self):
        self.scan()
        self.save(self.choose())
        self.private = self.private.parent / 'next'
        self.scan()
        previous = self.evidence.read_bytes()
        self.evidence.unlink()
        with self.assertRaisesRegex(ContractError, 'Missing source_item'):
            self.save([])
        self.assertTrue(self.candidates.exists())
        self.evidence.write_bytes(previous)
        self.assertEqual(0, self.save([]))
        self.assertFalse(self.candidates.exists())

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
