"""Integration checks use the actual public contracts, not a parallel PM rule set."""
import json
import tempfile
import unittest
from pathlib import Path
from scripts.build_dashboard import ROOT, build
from pipeline.selection.core import as_of


class ResearchDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name)
        cls.payload = build(cls.output)
        cls.data = json.loads((cls.output/'data.json').read_text())

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def read(self, path):
        return json.loads((self.output/path).read_text())

    def test_selected_default_matches_contract_and_keeps_source_only_subjects(self):
        for kind in ('features', 'flags'):
            source = json.loads((ROOT/f'data/selected/{kind}/current.json').read_text())
            expected = {(r['subject_kind'],r['subject_id'],r['assessment_id']) for r in source['current']}
            actual = {(r['subject_kind'],r['id'],r['assessment_id']) for r in self.data['selected'][kind]}
            self.assertEqual(expected, actual)
        self.assertTrue(any(r['subject_kind']=='source_item' for r in self.data['selected']['features']))
        self.assertEqual(65,len(self.data['selected']['features']))
        self.assertEqual(2,len(self.data['selected']['flags']))

    def test_date_views_match_t5_without_unioning_archived_history(self):
        for date in self.data['dates']:
            snapshot = self.read(date['path'])
            expected = as_of(ROOT,snapshot['cutoff'])
            self.assertEqual({(r['subject_kind'],r['subject_id'],r['assessment_id']) for p in expected.values() for r in p['current']},
                             {(r['subject_kind'],r['id'],r['assessment_id']) for r in snapshot['rows']})
        keys = [r['key'] for r in self.data['history']]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertTrue(any(not r['current_selected'] for r in self.data['history']))

    def test_all_sources_and_three_experiment_kinds_are_preserved(self):
        sources = self.read(self.data['indexes']['source_item'])
        expected = {r['source_item_id'] for p in (ROOT/'data/source-items').glob('*/*.json') for r in json.loads(p.read_text())}
        self.assertEqual(expected,{r['id'] for r in sources})
        self.assertEqual(4844,len(sources))
        experiments = self.read(self.data['indexes']['experiment'])
        self.assertEqual(2670,len(experiments))
        self.assertEqual({'flag_entry':2364,'command_switch':278,'base_feature':28},self.data['experiment_counts'])
        self.assertEqual(113,len(self.read(self.data['indexes']['feature'])))
        self.assertTrue(any(r['browser']=='safari' for r in sources))

    def test_original_events_and_media_are_exact_and_lazy(self):
        self.assertLess((self.output/'data.json').stat().st_size,200000)
        self.assertNotIn('events',self.data)
        self.assertNotIn('flags',self.data)
        for row in self.data['history']:
            d=self.read(row['detail'])
            self.assertEqual(row['id'],d['row']['id'])
            if row['subject_kind']=='feature_event':
                original=json.loads((ROOT/'data/events'/f'{row["id"]}.json').read_text())
                for key,value in original.items():
                    self.assertEqual(value,d['fact'][key])
        self.assertEqual(json.loads((ROOT/'dashboard/catalog.json').read_text()),self.data['catalog'])

    def test_report_revision_items_and_frozen_evidence_are_exact(self):
        for entry in self.data['reports']:
            report = self.read(entry['path'])
            original = json.loads((ROOT/f'data/reports/history/{entry["date"]}/revision-{entry["revision"]}.json').read_text())
            self.assertEqual(original, report)
            for item in report['items']:
                import hashlib
                key=item['subject_kind']+':'+item['subject_id']
                path='details/'+hashlib.sha256(key.encode()).hexdigest()+'.json'
                detail=self.read(path)
                self.assertEqual(key,detail['row']['key'])
                self.assertTrue(any(a['assessment_id']==item['assessment_id'] for a in detail['assessments']))
        current=self.read(self.data['reports'][0]['path'])
        self.assertEqual(4,len(current['items']))
        self.assertEqual('partial',current['completeness']['collection'])
        self.assertEqual('complete',current['completeness']['evaluation'])
        self.assertTrue(all(i['timing']=='backfill' for i in current['items'] if i['selection_kind']=='flags'))

    def test_replaced_owner_is_not_fabricated_deselection(self):
        replaced=[self.read(r['detail']) for r in self.data['history'] if not r['current_selected']]
        self.assertTrue(replaced)
        for detail in replaced:
            original = [a for p in (ROOT/'data/assessments').glob('*/*.json') for a in [json.loads(p.read_text())] if a['subject_id']==detail['row']['id']]
            self.assertEqual({a['assessment_id'] for a in original},{a['assessment_id'] for a in detail['assessments']})
        self.assertTrue(any(d['current_owner'] and d['current_owner']['key']!=d['row']['key'] for d in replaced))

    def test_legacy_flags_and_relative_resources_survive(self):
        experiments=self.read(self.data['indexes']['experiment'])
        retained=set()
        for row in experiments:
            detail=self.read(row['detail'])
            retained.update(f['id'] for f in detail['legacy_flags'])
        expected={p.stem for p in (ROOT/'experiments/chrome').glob('*.md') if p.stem!='README'}
        self.assertEqual(expected,retained)
        for name in ['data.json','research-model.js','app.js','style.css']:
            self.assertTrue((self.output/name).exists())
        self.assertNotIn('src="/',(self.output/'index.html').read_text())
