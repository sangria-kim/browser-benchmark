import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.reporting.newsletter import DASHBOARD, PENDING_TITLE, kst_day, latest_reports, make_cards, make_issue, newsletter_files, read, source_owners
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
            if card['title_pending']:
                self.assertEqual(PENDING_TITLE, card['title'])
            else:
                self.assertRegex(card['title'], '[가-힣]')
                self.assertLessEqual(len(card['title']), 48)
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

    def test_new_english_evidence_never_uses_a_clipped_raw_headline(self):
        draft = dict(self.events[0], event_id='new-playback', title=None, after=None,
                     summary='Adds a button that switches playback speed without leaving the video.')
        unknown = dict(draft, event_id='unknown-action', summary='A different previously unseen operation.')
        cards = make_cards([draft, unknown], [], {'events': {}})
        by_id = {c['id']: c for c in cards}
        self.assertEqual('재생 속도 조절 버튼 추가', by_id['new-playback']['title'])
        self.assertTrue(by_id['unknown-action']['title_pending'])
        issue = make_issue(cards[0]['day'], cards, '2026-12-01')
        self.assertEqual(1, issue['pending'])
        self.assertEqual(['new-playback'], [s['id'] for s in issue['stories']])
        translated = dict(unknown, title='편집자가 확인한 한글 제목')
        self.assertEqual(translated['title'], make_cards([translated], [], {'events': {}})[0]['title'])

    def test_later_materialization_keeps_source_card_on_original_day(self):
        sid = 'src-7c79c98a33925d760454e795'
        event = dict(self.events[0], event_id='later-event', source_item_ids=[sid], observed_at='2026-12-01T00:00:00Z')
        cards = make_cards([event], self.reports, {'events': {}}, source_owners(self.selection))
        self.assertEqual('2026-11-17', next(c['day'] for c in cards if c['id'] == sid))
        media = {'type': 'image', 'url': 'https://example.org/official.png', 'label': '공식 원천 화면'}
        catalog = {'events': {}, 'sources': {sid: {'media': [media]}}}
        same_day = make_cards([dict(event, observed_at='2026-11-17T00:00:00Z')], self.reports, catalog)
        merged = next(c for c in same_day if c['id'] == 'later-event')
        original = next(s for s in merged['related_sources'] if s['id'] == sid)
        self.assertEqual([media], original['media'])
        self.assertIn('과거 보강', original['stage'])
        self.assertEqual([], merged['media'])
        self.assertNotIn(sid, {c['id'] for c in same_day})

    def test_planned_milestones_use_only_current_individual_api_targets(self):
        card = next(c for c in self.cards if c['id'].startswith('chrome-css-corner-'))
        self.assertEqual('목표 159', card['version'])
        self.assertEqual(['플랫폼 미확인'], card['platform'])
        self.assertEqual({'Desktop': '159', 'Android': '159', 'iOS': '159', 'WebView': '159'}, card['targets'])
        archived = next(i for i in read(DASHBOARD/'daily/initial-issues.json') if i['day'] == card['day'])
        self.assertEqual(card['targets'], next(s['targets'] for s in archived['stories'] if s['id'] == card['id']))

    def test_unsaved_days_are_drafts_until_report_publication(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            event = dict(self.events[0], observed_at='2026-12-01T00:00:00Z')
            payload = dict(events=[event], catalog={'events':{}}, source={'sha':'0'*40})
            def homepage(stamp):
                write_home(root, root, dict(payload, built_at=stamp), [], {})
                text = (root/'index.html').read_text().split('id="daily-data">')[1].split('</script>')[0]
                return json.loads(text)
            a = homepage('2026-12-01T00:00:00Z')
            b = homepage('2026-12-02T00:00:00Z')
            self.assertEqual(a['issues'], [])
            self.assertEqual(a['drafts'], b['drafts'])
            self.assertIsNone(a['drafts'][0]['generated'])
            report = dict(date='2026-12-02', revision=1, cutoff='2026-12-02T04:00:00Z', items=[])
            def publish():
                return newsletter_files(root, {'feature_event': [event]}, report, {})
            outputs = publish()
            for relative, body in outputs.items():
                path = root/relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body)
            self.assertEqual({}, publish())
            saved = homepage('2026-12-03T00:00:00Z')
            self.assertEqual([], saved['drafts'])
            self.assertEqual({'2026-12-01','2026-12-02'}, {i['day'] for i in saved['issues']})
            self.assertTrue(all(i['generated'] for i in saved['issues']))
