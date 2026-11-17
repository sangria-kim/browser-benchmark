"""Integration checks use the actual public contracts, not a parallel PM rule set."""
import json
import gzip
import tempfile
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from scripts.build_dashboard import ROOT, build, write_resource, read_resource
from pipeline.normalize import load_dataset
from pipeline.selection.core import build_contexts, load_rules, project


class ResearchDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name)
        (cls.output/'details').mkdir()
        (cls.output/'details/stale.json').write_text('{}')
        cls.payload = build(cls.output)
        cls.data = json.loads((cls.output/'data.json').read_text())
        cls.dataset = load_dataset(ROOT)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def read(self, path):
        return read_resource(self.output/path)

    def test_compressed_resources_are_deterministic_and_references_exist(self):
        self.assertEqual('gzip', self.data['resource_encoding'])
        for name in ('details', 'indexes', 'dates', 'reports'):
            self.assertEqual([], list((self.output/name).glob('*.json')))
        def references(value):
            if isinstance(value, dict):
                for v in value.values(): references(v)
            elif isinstance(value, list):
                for v in value: references(v)
            elif isinstance(value, str) and value.startswith(('details/', 'indexes/', 'dates/', 'reports/')) and value.endswith('.json.gz'):
                self.assertTrue((self.output/value).is_file(), value)
        references(self.data)
        for path in self.output.glob('*/*.json.gz'):
            value=self.read(path.relative_to(self.output).as_posix())
            references(value)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);value={'id':'한글-1','detail':'details/abc.json.gz','values':[None,False,0]}
            write_resource(root,'one.json.gz',value);write_resource(root,'two.json.gz',value)
            first=(root/'one.json.gz').read_bytes()
            self.assertEqual(first,(root/'two.json.gz').read_bytes())
            self.assertEqual(b'\0\0\0\0',first[4:8])
            self.assertEqual(0,first[3] & 8)  # No filename in gzip header.
            self.assertEqual(value,json.loads(gzip.decompress(first)))

    def test_selected_default_matches_contract_and_keeps_source_only_subjects(self):
        for kind in ('features', 'flags'):
            source = json.loads((ROOT/f'data/selected/{kind}/current.json').read_text())
            expected = {(r['subject_kind'],r['subject_id'],r['assessment_id']) for r in source['current']}
            actual = {(r['subject_kind'],r['id'],r['assessment_id']) for r in self.data['selected'][kind]}
            self.assertEqual(expected, actual)
            self.assertEqual(len(expected), len(self.data['selected'][kind]))

    def test_date_views_match_t5_without_unioning_archived_history(self):
        contexts, _ = build_contexts(self.dataset)
        rules = load_rules()
        for date in self.data['dates']:
            snapshot = self.read(date['path'])
            cutoff = snapshot['cutoff']
            expected = project(self.dataset, contexts, self.dataset['assessment'], rules, cutoff, as_of=cutoff)
            self.assertEqual({(r['subject_kind'],r['subject_id'],r['assessment_id']) for p in expected.values() for r in p['current']},
                             {(r['subject_kind'],r['id'],r['assessment_id']) for r in snapshot['rows']})
        keys = [r['key'] for r in self.data['history']]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertTrue(any(not r['current_selected'] for r in self.data['history']))

    def test_all_sources_and_three_experiment_kinds_are_preserved(self):
        for kind in ('source_item', 'feature', 'experiment'):
            rows = self.read(self.data['indexes'][kind])
            expected = {r[kind + '_id'] for r in self.dataset[kind]}
            self.assertEqual(expected, {r['id'] for r in rows})
            self.assertEqual(len(expected), len(rows))
            self.assertEqual(len(expected), self.data['counts'][kind])
        kinds = Counter(r['experiment_kind'] for r in self.dataset['experiment'])
        self.assertEqual({'flag_entry', 'command_switch', 'base_feature'}, set(kinds))
        self.assertEqual(dict(kinds), self.data['experiment_counts'])
        sources = self.read(self.data['indexes']['source_item'])
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
        archives = set((ROOT/'data/reports/history').glob('*/*.json'))
        for entry in self.data['reports']:
            report = self.read(entry['path'])
            path = ROOT/f'data/reports/history/{entry["date"]}/revision-{entry["revision"]}.json'
            archives.remove(path)
            original = json.loads(path.read_text())
            self.assertEqual(original, report)
            self.assertEqual(len(original['items']), entry['count'])
            self.assertEqual(original['completeness'], entry['completeness'])
            for item in report['items']:
                import hashlib
                key=item['subject_kind']+':'+item['subject_id']
                path='details/'+hashlib.sha256(key.encode()).hexdigest()+'.json.gz'
                detail=self.read(path)
                self.assertEqual(key,detail['row']['key'])
                self.assertTrue(any(a['assessment_id']==item['assessment_id'] for a in detail['assessments']))
        self.assertFalse(archives)
        baseline = self.read('reports/2026-11-16-r1.json.gz')
        self.assertEqual(4,len(baseline['items']))
        self.assertEqual('partial',baseline['completeness']['collection'])
        self.assertEqual('complete',baseline['completeness']['evaluation'])
        self.assertTrue(all(i['timing']=='backfill' for i in baseline['items'] if i['selection_kind']=='flags'))

    def test_replaced_owner_is_not_fabricated_deselection(self):
        replaced=[self.read(r['detail']) for r in self.data['history'] if not r['current_selected']]
        self.assertTrue(replaced)
        assessments = defaultdict(set)
        for a in self.dataset['assessment']:
            assessments[a['subject_kind'], a['subject_id']].add(a['assessment_id'])
        for detail in replaced:
            row = detail['row']
            self.assertEqual(assessments[row['subject_kind'], row['id']],
                             {a['assessment_id'] for a in detail['assessments']})
        self.assertTrue(any(d['current_owner'] and d['current_owner']['key']!=d['row']['key'] for d in replaced))

    def test_legacy_flags_and_relative_resources_survive(self):
        experiments=self.read(self.data['indexes']['experiment'])
        retained=set()
        for row in experiments:
            detail=self.read(row['detail'])
            retained.update(f['id'] for f in detail['legacy_flags'])
        expected={p.stem for p in (ROOT/'experiments/chrome').glob('*.md') if p.stem!='README'}
        self.assertEqual(expected,retained)
        for name in ['data.json','research-model.js','resources.js','app.js','style.css']:
            self.assertTrue((self.output/name).exists())
        self.assertNotIn('src="/',(self.output/'index.html').read_text())
