import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.reporting.newsletter import DASHBOARD, kst_day, latest_reports, make_cards, make_issue, read, source_owners
from scripts.build_daily_dashboard import write_home


class DailyNewsletterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = DASHBOARD.parent
        cls.events = [read(p) for p in cls.root.glob('data/events/*.json')]
        cls.reports = [read(p) for p in cls.root.glob('data/reports/history/*/*.json')]
        cls.catalog = read(DASHBOARD / 'catalog.json')
        cls.selection = read(cls.root / 'data/selected/features/current.json')
        cls.cards = make_cards(cls.events, cls.reports, cls.catalog, source_owners(cls.selection))

    def test_card_identity_and_scope(self):
        by_id = {c['id']: c for c in self.cards}
        self.assertEqual(len(self.cards), len(by_id))
        for event in self.events:
            card = by_id[event['event_id']]
            self.assertEqual(kst_day(event['observed_at']), card['day'])
            self.assertEqual(event['browser'], card['browser'])
            self.assertTrue(card['version'] and card['stage'] and card['platform'])
            self.assertRegex(card['title'], '[가-힣]')
            self.assertEqual({m['url'] for m in self.catalog['events'].get(card['id'], {}).get('media', [])
                              if m['type'] in ('image', 'video')}, {m['url'] for m in card['media']})

    def test_source_documents_keep_their_observed_scope(self):
        source = next(c for c in self.cards if c['id'] == 'src-e4381df11e821f72c25e02d9')
        self.assertEqual('2026-11-17', source['day'])
        self.assertEqual('문서 152 / 153 / 154', source['version'])
        self.assertEqual(4, len(source['sources']))
        self.assertIn('과거 보강', source['stage'])
        self.assertEqual(['플랫폼 미확인'], source['platform'])

    def test_editions_have_distinct_issue_and_publication_dates(self):
        reports = latest_reports(self.reports)
        for day in {c['day'] for c in self.cards} | set(reports):
            rows = [c for c in self.cards if c['day'] == day]
            issue = make_issue(day, self.cards, '2026-11-19', reports.get(day))
            self.assertEqual(len(rows), issue['count'])
            self.assertLessEqual(len(issue['stories']), 3)
            for story in issue['stories']:
                self.assertIn(story['id'], {c['id'] for c in rows})
                self.assertTrue(story['question'] and story['platform'])
        self.assertEqual('2026-11-19', read(DASHBOARD/'daily/initial-issues.json')[0]['generated'])

    def test_archive_revision_and_inert_embedded_source_text(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            issue = dict(day='2026-12-01', generated='2026-12-02', revision=2, stories=[], count=0, completeness=None)
            target = root/'reports/generated/2026-12-01/newsletter-r2.json'
            target.parent.mkdir(parents=True)
            target.write_text(json.dumps(issue))
            event = dict(self.events[0], summary='공식 변경 </script> 새 자료', observed_at='2026-12-02T15:01:00Z')
            payload = dict(events=[event], catalog={'events':{}}, source={'sha':'a'*40}, built_at='2026-12-04T00:00:00Z')
            write_home(root, root, payload, [], {})
            html = (root/'index.html').read_text()
            encoded = html.split('id="daily-data">')[1].split('</script>')[0]
            data = json.loads(encoded)
            self.assertEqual(event['summary'],data['cards'][0]['original'])
            self.assertIn(issue,data['issues'])
            self.assertEqual('2026-12-03',data['cards'][0]['day'])
