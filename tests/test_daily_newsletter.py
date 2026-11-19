import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pipeline.reporting.newsletter import DASHBOARD, PENDING_TITLE, kst_day, latest_reports, make_cards, make_issue, newsletter_files, read, source_owners
import test_reporting
from scripts.archive_newsletters import archive
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

    def test_missing_previous_report_revisions_use_their_own_cutoff(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            first = dict(self.events[0], event_id='morning', observed_at='2026-12-01T00:00:00Z',
                         revision=1, summary='오전의 원래 기능', title=None, after=None)
            updated = dict(first, revision=2, summary='나중에 정정된 기능')
            later = dict(first, event_id='afternoon', observed_at='2026-12-01T05:01:00Z', summary='오후의 기능')
            fact_archive = root/'data/event-revisions/morning/revision-1.json'
            fact_archive.parent.mkdir(parents=True)
            fact_archive.write_text(json.dumps(first))
            item = dict(subject_kind='feature_event', subject_id='morning', selection_kind='features',
                        details={'subject_revision':1})
            r1 = dict(date='2026-12-01', revision=1, cutoff='2026-12-01T01:00:00Z', items=[item],
                      completeness={'collection':'partial','evaluation':'complete'})
            r2 = dict(r1, revision=2, cutoff='2026-12-01T06:00:00Z')
            for report in [r1, r2]:
                path = root / ('data/reports/history/2026-12-01/revision-%s.json' % report['revision'])
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(report))
            current = dict(date='2026-12-02', revision=1, cutoff='2026-12-02T04:00:00Z', items=[])
            dataset = {'feature_event':[updated,later], 'report':[r2]}
            editions = newsletter_files(root,dataset,current,{})
            early = json.loads(editions['reports/generated/2026-12-01/newsletter-r1.json'])
            late = json.loads(editions['reports/generated/2026-12-01/newsletter-r2.json'])
            self.assertEqual(['오전의 원래 기능'], [s['title'] for s in early['stories']])
            self.assertEqual(2, late['count'])
            self.assertEqual(r1['completeness'], early['completeness'])
            for name, contents in editions.items():
                path = root/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(contents)
            self.assertEqual({}, newsletter_files(root,dataset,current,{}))


class NewsletterArchiveTests(unittest.TestCase):
    setUp = test_reporting.ReportingTests.setUp
    write = test_reporting.ReportingTests.write
    provider = test_reporting.ReportingTests.provider
    execute = test_reporting.ReportingTests.execute
    selected = test_reporting.ReportingTests.selected
    report = test_reporting.ReportingTests.report

    def test_publication_and_homepage_share_the_requested_repository_copy(self):
        board = self.repo / 'dashboard/daily'
        board.mkdir(parents=True)
        event = self.data['feature_event'][0]
        headline = '다른 저장소에서 편집한 기능 제목'
        (board/'titles.json').write_text(json.dumps({event['event_id']: headline}))
        self.selected()
        self.report()
        archive(self.repo)
        editions = [json.loads(p.read_text()) for p in self.repo.glob('dashboard/daily/editions/*/newsletter-r*.json')]
        self.assertIn(headline, [s['title'] for i in editions for s in i['stories']])
        out = self.base/'preview'
        out.mkdir()
        write_home(out, self.repo, dict(events=[event], catalog={'events':{}}, source={'sha':'1'*40}), [], {})
        data = json.loads((out/'index.html').read_text().split('id="daily-data">')[1].split('</script>')[0])
        self.assertEqual(headline, data['cards'][0]['title'])
        self.assertEqual(len(editions), len(data['issues']))

    def test_next_report_recovers_edition_for_a_legacy_report(self):
        self.selected()
        first = self.report()['report']
        path = self.repo/'dashboard/daily/editions/2026-11-16/newsletter-r1.json'
        self.assertFalse(path.exists())
        self.report('2026-11-17', '2026-11-17T06:00:00Z')
        archive(self.repo)
        recovered = json.loads(path.read_text())
        self.assertEqual((first['date'], first['revision']), (recovered['day'], recovered['revision']))
        self.assertTrue(recovered['generated'])
        saved = path.read_bytes()
        self.report('2026-11-17', '2026-11-17T06:00:00Z')
        self.assertEqual([], archive(self.repo))
        self.assertEqual(saved,path.read_bytes())
