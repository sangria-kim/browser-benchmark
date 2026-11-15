import json
import tempfile
import unittest
from pathlib import Path
from scripts.build_dashboard import ROOT, build


class DashboardDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name)
        cls.data = build(cls.output)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_every_event_and_flag_is_preserved(self):
        expected = {json.loads(p.read_text())['event_id'] for p in (ROOT/'data/events').glob('*.json')}
        self.assertEqual(expected, {d['event_id'] for d in self.data['events']})
        flags = {p.stem for p in (ROOT/'experiments/chrome').glob('*.md') if p.name != 'README.md'}
        self.assertEqual(flags, {f['id'] for f in self.data['flags']})

    def test_original_evidence_not_reclassified(self):
        for e in self.data['events']:
            original = json.loads((ROOT/'data/events'/f'{e["event_id"]}.json').read_text())
            for key, value in original.items():
                self.assertEqual(value, e[key], (e['event_id'], key))

    def test_webtoon_is_explicit_and_channel_difference_is_retained(self):
        catalog = self.data['catalog']['events']
        self.assertNotIn('chrome-android-headphone-disconnect-pause-source-20261114', catalog)
        brave = catalog['brave-split-view-edge-drag-restore-stable-1-99-55-20261105']['webtoon']
        self.assertIn('Beta 1.99.48', brave['scope'])
        for entry in catalog.values():
            if entry.get('webtoon', {}).get('status') == 'done':
                self.assertTrue(entry['webtoon']['url'].startswith('https://'))

    def test_flag_timelines_and_relative_deployment(self):
        flag = next(f for f in self.data['flags'] if f['id']=='android-vertical-tabs')
        self.assertTrue(any(h['date']=='2026-07-21' for h in flag['history']))
        html = (self.output/'index.html').read_text()
        self.assertIn('href="style.css"',html)
        self.assertIn('src="app.js"',html)
        self.assertEqual(self.data['source']['sha'].__len__(),40)

    def test_public_catalog_has_no_operational_exports(self):
        text = (ROOT/'dashboard/catalog.json').read_text()
        for forbidden in ['mailto:', '@gmail.com', 'Sentinel_', 'notion-file-block://', 'X-Amz-', 'Gmail']:
            self.assertNotIn(forbidden,text)


if __name__ == '__main__':
    unittest.main()
