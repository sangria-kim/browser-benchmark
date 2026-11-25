"""Drive the collection CLIs with a local transport and an isolated feature graph."""
from contextlib import redirect_stdout
from email.message import Message
from io import BytesIO, StringIO
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline import browser_status, run_daily
from pipeline.collectors.browser import HTTPTransport, Response
from pipeline.feature_enrichment import read_jobs, verified_candidate, verified_reference
from pipeline.feature_item import item_delta
from pipeline.daily_status import receipt
from pipeline.normalize import validate_graph

ROOT = Path(__file__).resolve().parents[1]
HOME = 'https://chromereleases.googleblog.com/'
URL = HOME + '2026/04/release.html'
SID = 'chrome-releases'
NOW = '2026-11-25T07:00:00+09:00'
APRIL = '2026-04-10T07:00:00+09:00'


def card(url):
    return (f'<div class="post"><h3 class="post-title"><a href="{url}">Release</a></h3>'
            '<div class="post-header"><span class="publishdate" itemprop="datePublished">2026-04-01</span></div></div>')


def article(tabs='Tab groups are available.'):
    return ('<meta property="article:published_time" content="2026-04-01"><div class="post-body">'
            f'<p id="tabs">{tabs}</p><p id="toolbar">Toolbar color is available on Android.</p></div>')


class FeatureReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name).resolve()
        self.root = self.folder / 'repo'
        shutil.copytree(ROOT / 'config', self.root / 'config')
        self.sources = run_daily.read(self.root / 'config/sources.yml')['sources']
        self.payloads = {HOME: card(URL), URL: article()}
        self.calls = []

    def apply(self, request, candidate=None):
        delta = item_delta(self.root, request, self.sources, observed_at=APRIL, candidate=candidate)
        validate_graph(self.root, delta.changes)
        for rel, obj in delta.changes.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(run_daily.encoded(obj))
        return delta.effect

    def select(self, title='Tab groups', url=URL, **kwargs):
        return self.apply(dict(browser='chrome', source_id=SID, canonical_key=title.lower().replace(' ', '-'),
                               url=url, title=title, **kwargs))['feature_id']

    def transport(self, url):
        self.calls.append(url)
        result = self.payloads[url]
        if isinstance(result, Exception):
            raise result
        if isinstance(result, Response):
            return result
        return Response(url, result.encode())

    def cli(self, name, cutoff=NOW, *, resume=False, manual=False, expected=0, sid=SID, transport=None):
        self.calls.clear()
        private = self.folder / 'runs' / name
        entry = 'collect' if manual else 'run_daily'
        args = [entry, '--repository', str(self.root), '--private-dir', str(private if manual else private.parent)]
        if not manual:
            args += ['--run-id', name]
        args += ['--resume'] if resume else ['--cutoff', cutoff, '--source', sid]
        if manual and not resume:
            args += ['--mode', 'manual', '--since', '2026-11-01']
        with patch('sys.argv', args), patch('pipeline.collectors.browser.collector.HTTPTransport', return_value=transport or self.transport):
            with redirect_stdout(StringIO()), self.assertRaises(SystemExit) as end:
                runpy.run_path(str(ROOT / 'pipeline' / (entry + '.py')), run_name='__main__')
        self.assertEqual(expected, end.exception.code)
        self.state = run_daily.read(private / 'feature-run.json')
        self.work = private / 'work'
        self.products = run_daily.read(self.work / 'candidates' / (sid + '.json'))
        return {job['feature_id']: job for job in read_jobs(self.work, self.state, sid)}

    def select_review(self, job, facts):
        row = job['candidate']
        request = dict(browser='chrome', feature_id=job['feature_id'], source_id=SID, source_item_id=row['source_item_id'],
                       revision_id=row['revisions'][-1]['revision_id'], facts=facts)
        return request, verified_candidate(self.work, self.state, request)

    def test_after_30_days_identical_bytes_then_enrichment_of_one_feature(self):
        first = self.select(facts={'version': '150'})
        other = self.select('Toolbar color')
        april = self.cli('april', APRIL)
        self.assertEqual([HOME, URL], self.calls)
        self.assertEqual(2, len(self.products))
        original_catalog = (self.root / browser_status.CATALOG).read_bytes()
        rel, value = receipt(APRIL, 2, 2)
        history = self.root / rel
        history.parent.mkdir(parents=True)
        existing_receipt = run_daily.encoded(value)
        history.write_bytes(existing_receipt)
        run_daily.commit_candidate(self.root)
        november = self.cli('november')
        self.assertEqual([HOME, URL], self.calls)
        self.assertEqual([], self.products)
        self.assertEqual(april[first]['content_sha256'], november[first]['content_sha256'])
        self.assertEqual(original_catalog, (self.root / browser_status.CATALOG).read_bytes())
        self.assertEqual(['platform', 'channel', 'rollout_status'], november[first]['missing_fields'])
        self.assertNotIn('Android', november[first]['candidate']['classification_text'])
        self.assertIn('Android', november[other]['candidate']['classification_text'])
        self.payloads[URL] = article('Tab groups are rolling out on Windows.')
        jobs = self.cli('manual', manual=True)
        self.assertEqual([HOME, URL], self.calls)
        self.assertEqual([], self.products)
        req, row = self.select_review(jobs[first], {'platform': ['Windows'], 'rollout_status': 'rolling out'})
        with self.assertRaises(ValueError):
            verified_candidate(self.work, self.state, dict(req, feature_id=other))
        with self.assertRaises(ValueError):
            verified_candidate(self.work, self.state, dict(req, facts={'version': '151'}))
        self.assertFalse(self.apply(req, row)['changed'])
        next_jobs = self.cli('next', '2026-11-26T07:00:00+09:00')
        self.assertEqual(['channel'], next_jobs[first]['missing_fields'])
        self.assertEqual(4, len(next_jobs[other]['missing_fields']))
        self.assertEqual([], self.products)
        self.payloads[URL] = article()
        missing_again = self.cli('again', '2026-11-27T07:00:00+09:00')
        self.assertEqual(['channel'], missing_again[first]['missing_fields'])
        features = {f['feature_id']: f for f in run_daily.read(self.root / browser_status.CATALOG)}
        self.assertEqual(['Windows'], features[first]['feature_facts']['platform']['value'])
        self.assertEqual({}, features[other]['feature_facts'])
        self.assertEqual(2, len(features))
        self.assertEqual(existing_receipt, history.read_bytes())

    def test_failure_resume_and_publisher_wait(self):
        first = self.select()
        self.payloads[URL] = OSError('offline')
        self.assertIn('error', self.cli('retry')[first])
        self.assertTrue(self.state['complete'])
        self.assertEqual([], self.products)
        self.payloads[URL] = article()
        self.assertIn('candidate', self.cli('retry', resume=True)[first])
        self.assertEqual([URL], self.calls)
        self.assertIn('candidate', self.cli('retry', resume=True)[first])
        self.assertEqual([], self.calls)
        self.payloads[URL] = Response(URL, b'', 429, {'Retry-After': '3600'})
        self.assertIn('error', self.cli('limit')[first])
        self.assertEqual([HOME, URL], self.calls)
        self.cli('limit', resume=True)
        self.assertEqual([], self.calls)
        self.cli('fresh', expected=2)
        self.assertEqual([], self.calls)

    def test_unchanged_legacy_source_is_progressively_enrolled(self):
        self.cli('initial', APRIL)
        row = next(r for r in self.products if r['item_key'] == 'tabs')
        effect = self.apply(dict(browser='chrome', canonical_key='groups', title='Tab groups',
                                 source_item_id=row['source_item_id'], revision_id=row['revisions'][-1]['revision_id']),
                            candidate=row)
        cat = self.root / browser_status.CATALOG
        features = run_daily.read(cat)
        del features[0]['feature_facts']
        cat.write_bytes(run_daily.encoded(features))
        self.assertEqual({}, self.cli('before'))
        self.assertEqual([HOME], self.calls)
        jobs = self.cli('observed', APRIL)
        self.assertIn('candidate', jobs[effect['feature_id']])
        self.assertNotIn('tabs', [r['item_key'] for r in self.products])
        shutil.rmtree(self.work)
        self.assertIn('candidate', self.cli('after')[effect['feature_id']])
        self.assertEqual([HOME, URL], self.calls)
        self.assertEqual([], self.products)

    def test_budget_rotation_and_raw_integrity(self):
        urls = [HOME + f'2026/04/entry-{i}.html' for i in range(6)]
        self.payloads[HOME] = ''.join(card(u) for u in urls)
        for url in urls:
            self.select('Tab groups', url)
            self.payloads[url] = article()
        self.cli('round1')
        first_reads = set(self.calls[1:])
        self.assertEqual(4, len(first_reads))
        jobs = self.cli('round2')
        self.assertEqual(set(urls), first_reads | set(self.calls[1:]))
        job = next(iter(jobs.values()))
        (self.work / 'browser/cache' / job['content_sha256']).write_bytes(b'mutated')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.select_review(job, {'channel': 'stable'})

    def test_old_chromestatus_unit_reuses_enumeration_and_only_missing_facts(self):
        sid = 'chrome-platform-status'
        url = 'https://chromestatus.com/feature/12345'
        first = self.apply(dict(browser='chrome', source_id=sid, url=url, title='Tab groups', canonical_key='tabs'))['feature_id']
        api = 'https://chromestatus.com/api/v0/features?num=100&start=0'
        row = dict(id=12345, name='Tab groups', summary='Tab groups is shipped on Windows in the stable channel.',
                   created=dict(when='2026-04-01T02:00:00Z'), updated=dict(when='2026-04-02T02:00:00Z'),
                   browsers=dict(chrome=dict(desktop=150, status=dict(text='Shipped'))))
        self.payloads[api] = json.dumps(dict(total_count=1, features=[row]))
        job = self.cli('old-api', sid=sid)[first]
        self.assertEqual([api], self.calls)
        self.assertEqual([], self.products)
        self.assertIn('Desktop 150', job['candidate']['classification_text'])
        request = dict(browser='chrome', feature_id=first, source_id=sid,
                       facts=dict(version='150', platform=['Windows'], rollout_status='shipped', channel='stable'),
                       source_item_id=job['candidate']['source_item_id'],
                       revision_id=job['candidate']['revisions'][-1]['revision_id'])
        self.apply(request, verified_candidate(self.work, self.state, request))
        self.assertEqual({}, self.cli('known', sid=sid))
        self.assertEqual([api], self.calls)
        self.assertEqual([], self.products)

    def test_ambiguous_shared_block_has_no_feature_candidate(self):
        first = self.select()
        other = self.select('Toolbar color')
        self.payloads[URL] = '<div class="post-body"><p>Toolbar color and Tab groups on Android.</p></div>'
        jobs = self.cli('ambiguous')
        self.assertEqual({first, other}, set(jobs))
        self.assertFalse(any('candidate' in job for job in jobs.values()))
        self.assertTrue(all('content_sha256' in job for job in jobs.values()))
        self.assertEqual([], self.products)

    def test_direct_wire_response_headers_survive_source_checkpoint(self):
        self.select()
        calls = []
        def open_request(request, timeout):
            url = request.full_url
            calls.append(url)
            body = self.payloads[url].encode()
            response = BytesIO(body)
            response.url, response.status, response.headers = url, 200, Message()
            response.headers['Content-Length'] = str(len(body))
            response.headers['Content-Type'] = 'text/html'
            return response
        with patch('pipeline.collectors.browser.transport.urlopen', side_effect=open_request), patch(
                'pipeline.collectors.browser.transport.build_opener') as opener:
            opener.return_value.open.side_effect = open_request
            jobs = self.cli('real-headers', transport=HTTPTransport())
        self.assertEqual([HOME, URL], calls)
        self.assertIn('candidate', next(iter(jobs.values())))
        checkpoint = run_daily.read(self.work / 'browser' / (SID + '-progress.json'))
        self.assertEqual('text/html', checkpoint['responses'][URL]['headers']['content-type'])

    def test_rolling_and_retry_only_document_exclude_future_sections(self):
        sid = 'edge-stable'
        edge = next(s['url'] for s in self.sources if s['source_id'] == sid)
        fid = self.apply(dict(browser='edge', canonical_key='tabs', title='Tab groups', source_id=sid, url=edge))['feature_id']
        self.payloads[edge] = ('<div class="content"><h2>Version 151, November 28, 2026</h2>'
                               '<p>Tab groups will ship on Windows.</p></div>')
        job = self.cli('rolling', sid=sid)[fid]
        self.assertEqual([], self.products)
        self.assertNotIn('candidate', job)
        self.assertIn('candidate', self.cli('later', '2026-11-30T07:00:00+09:00', sid=sid)[fid])
        first = self.select()
        self.payloads[URL] = ('<div class="post-body"><h2>November 28, 2026</h2>'
                              '<p>Tab groups will ship on Windows.</p></div>')
        self.assertNotIn('candidate', self.cli('retry-age')[first])
        self.assertEqual([], self.products)

    def test_enterprise_old_public_panels_and_api_share_original_requests(self):
        sid = 'chrome-enterprise'
        archive = 'https://support.google.com/chrome/a/answer/10314655?hl=en'
        api = 'https://release-notes-787862449254.us-central1.run.app'
        details = api + '/features?version=101&lang=en'
        ids = [self.apply(dict(browser='chrome', source_id=sid, url=url, title=title, canonical_key=key))['feature_id']
               for url, title, key in [(archive, 'Workspaces', 'workspaces'), (details, 'Tab groups', 'tabs'),
                                       (details, 'Hidden folders', 'folders'), (details, 'Tab themes', 'themes')]]
        self.payloads[archive] = ('<a href="#101">April 1, 2026</a><a class="zippy" name="101">Version</a>'
                                  '<div><p id="archive">Workspaces are available on Windows.</p></div>')
        self.payloads[api + '/versions'] = json.dumps(dict(versions=[dict(value='101')]))
        row = dict(id=12345, name='Tab groups', summary='Tab groups is available on Windows.',
                   is_releasenotes_publish_ready=True, is_releasenotes_content_reviewed=True,
                   created=dict(when='2026-04-01'), updated=dict(when='2026-04-02'))
        self.payloads[details] = json.dumps(dict(total_count=3, features=[
            row, dict(row, id=12346, name='Hidden folders', confidential=True, summary='Hidden folders on Windows.'),
            dict(row, id=12347, name='Tab themes', summary='Tab themes on Windows.', created=dict(when='2026-11-30'))]))
        jobs = self.cli('enterprise', sid=sid, expected=0)
        self.assertEqual([archive, api + '/versions', details], self.calls)
        self.assertEqual([], self.products)
        self.assertTrue(all('candidate' in jobs[fid] for fid in ids[:2]))
        self.assertTrue(all('candidate' not in jobs[fid] and not jobs[fid].get('reference_review') for fid in ids[2:]))
        alternate = details.replace('version=101&lang=en', 'lang=en&version=101#theme')
        other = self.apply(dict(browser='chrome', source_id=sid, url=alternate, title='Group layouts', canonical_key='layouts'))['feature_id']
        self.payloads[details] = json.dumps(dict(total_count=1, features=[
            dict(row, summary='Tab groups and Group layouts are available on Windows.')]))
        mixed = self.cli('enterprise-mixed', sid=sid)
        self.assertNotIn('candidate', mixed[ids[1]])
        self.assertNotIn('candidate', mixed[other])
        self.assertEqual([archive, api + '/versions', details], self.calls)

    def store_via_cli(self, request, *, run=None):
        decision = self.folder / 'feature.json'
        decision.write_bytes(run_daily.encoded(request))
        entry = 'run_daily' if run else 'collect'
        args = [entry, '--repository', str(self.root), '--private-dir', str(self.folder / ('runs' if run else 'manual')),
                '--save-item', str(decision)]
        if run:
            args += ['--run-id', run]
        output = StringIO()
        with patch('sys.argv', args), redirect_stdout(output), self.assertRaises(SystemExit) as end:
            runpy.run_path(str(ROOT / 'pipeline' / (entry + '.py')), run_name='__main__')
        self.assertEqual(0, end.exception.code)
        return json.loads(output.getvalue())

    def test_operator_enrichment_from_verified_reference_with_translated_title(self):
        base = dict(browser='chrome', source_id=SID, url=URL)
        first = self.store_via_cli(dict(base, canonical_key='tabs', title='탭 그룹', facts={'version': '150'}))['feature_id']
        sibling = self.store_via_cli(dict(base, canonical_key='toolbar', title='도구 모음'))['feature_id']
        self.payloads[URL] = article('Tab groups is available on Windows.')
        jobs = self.cli('translation')
        self.assertTrue(jobs[first]['reference_review'])
        self.assertNotIn('candidate', jobs[first])
        request = dict(source_id=SID, url=URL, browser='chrome', feature_id=first, facts={'platform': ['Windows']})
        reviewed = dict(request, reference_review=True)
        self.assertFalse(self.store_via_cli(reviewed, run='translation')['changed'])
        self.assertFalse(self.store_via_cli(reviewed, run='translation')['changed'])
        self.assertFalse((self.root / 'data/daily-status').exists())
        with self.assertRaises(ValueError):
            verified_reference(self.work, self.state, dict(request, facts={'version': '151'}))
        with self.assertRaises(ValueError):
            verified_reference(self.work, self.state, dict(request, url=HOME))
        by_id = {f['feature_id']: f for f in run_daily.read(self.root / browser_status.CATALOG)}
        self.assertEqual(['Windows'], by_id[first]['feature_facts']['platform']['value'])
        self.assertEqual({}, by_id[sibling]['feature_facts'])
        self.assertEqual([], self.products)

    def test_standalone_fact_uses_official_reference_and_preserves_original_parsed_bytes(self):
        self.cli('before', APRIL)
        row = next(r for r in self.products if r['item_key'] == 'tabs')
        old = row['revisions'][-1]
        selection = dict(browser='chrome', source_id=SID, source_item_id=row['source_item_id'],
                         revision_id=old['revision_id'], canonical_key='tabs', title='탭 그룹')
        fid = self.store_via_cli(selection, run='before')['feature_id']
        req = dict(browser='chrome', source_id=SID, feature_id=fid, url=URL, facts={'platform': ['Windows']})
        self.assertFalse(self.store_via_cli(req)['changed'])
        graph = validate_graph(self.root)
        f, = graph['feature']
        cited = f['feature_facts']['platform']
        sources = {r['source_item_id']: r for r in graph['source_item']}
        self.assertEqual('reference', sources[cited['source_item_id']]['record_status'])
        self.assertEqual(URL, sources[cited['source_item_id']]['evidence']['url'])
        self.assertEqual('', sources[cited['source_item_id']]['evidence']['excerpt'])
        self.assertNotEqual(old['revision_id'], cited['revision_id'])
        self.assertEqual(old, sources[row['source_item_id']]['revisions'][-1])
        self.assertFalse(self.store_via_cli(req)['changed'])
        self.assertEqual(graph, validate_graph(self.root))

    def test_reference_decision_pins_the_reviewed_bytes_and_preserves_prior_citation(self):
        self.payloads[URL] = article('Tab groups are supported.')
        self.cli('first', APRIL)
        row = next(r for r in self.products if r['item_key'] == 'tabs')
        original_revision = row['revisions'][-1]
        request = dict(browser='chrome', source_id=SID, source_item_id=row['source_item_id'],
                       revision_id=original_revision['revision_id'], canonical_key='tabs', title='탭 그룹',
                       facts={'version': '150'})
        fid = self.store_via_cli(request, run='first')['feature_id']
        peer = self.store_via_cli(dict(request, canonical_key='folders', title='탭 폴더'), run='first')['feature_id']
        before = {f['feature_id']: f for f in validate_graph(self.root)['feature']}
        day, history = receipt(APRIL, 2, 2)
        historical = self.root / day
        historical.parent.mkdir(parents=True)
        historical.write_bytes(run_daily.encoded(history))
        frozen = historical.read_bytes()
        self.payloads[URL] = article('Tab groups are available on Windows.')
        job = self.cli('later')[fid]
        self.assertTrue(job['reference_review'])
        raw_hash = run_daily.digest(self.payloads[URL].encode())
        decision = dict(browser='chrome', source_id=SID, url=URL, feature_id=fid,
                        reference_review=True, facts={'platform': ['Windows']})
        self.assertFalse(self.store_via_cli(decision, run='later')['changed'])
        def state():
            return {p: p.read_bytes() for p in (self.root / 'data').rglob('*.json')}
        first_save = state()
        self.assertFalse(self.store_via_cli(decision, run='later')['changed'])
        self.assertEqual(first_save, state())
        graph = validate_graph(self.root)
        features = {f['feature_id']: f for f in graph['feature']}
        evidence = {r['source_item_id']: r for r in graph['source_item']}
        fact = features[fid]['feature_facts']['platform']
        actual = next(r for r in evidence[fact['source_item_id']]['revisions'] if r['revision_id'] == fact['revision_id'])
        progress = run_daily.read(self.work / 'browser' / (SID + '-progress.json'))
        checked_at = progress['responses'][URL]['observed_at']
        self.assertEqual(checked_at, actual['observed_at'])
        self.assertEqual(checked_at, actual['evidence']['observed_at'])
        self.assertEqual(raw_hash, actual['content_sha256'])
        self.assertEqual(raw_hash, actual['evidence']['content_sha256'])
        self.assertEqual('', actual['evidence']['excerpt'])
        self.assertNotEqual(original_revision['revision_id'], actual['revision_id'])
        self.assertEqual(original_revision, evidence[row['source_item_id']]['revisions'][-1])
        self.assertEqual(before[fid]['feature_facts']['version'], features[fid]['feature_facts']['version'])
        self.assertEqual(before[peer], features[peer])
        self.assertEqual(frozen, historical.read_bytes())

    def test_enterprise_anchor_enrichment_keeps_publisher_panel_and_cutoff(self):
        sid = 'chrome-enterprise'
        archive = 'https://support.google.com/chrome/a/answer/10314655?hl=en'
        api = 'https://release-notes-787862449254.us-central1.run.app'
        def select(anchor, title, key):
            return self.store_via_cli(dict(browser='chrome', source_id=sid, url=archive + '#' + anchor,
                                           canonical_key=key, title=title))['feature_id']
        future = select('165', 'Workspaces', 'future-workspaces')
        current = select('164', 'Team menus', 'current-menus')
        translated = select('164', '탭 폴더', 'current-folders')
        old = select('100', 'Old shortcuts', 'old-shortcuts')
        absent = select('166', 'Missing panel', 'missing')
        self.payloads[archive] = (
            '<a href="#100">April 1, 2026</a><a class="zippy" name="100">Version</a><div><p>Old shortcuts on Mac.</p></div>'
            '<a href="#164">November 11, 2026</a><a class="zippy" name="164">Version</a><div><p>Team menus on Linux.</p><p>Tab folders support ChromeOS.</p></div>'
            '<a href="#165">November 28, 2026</a><a class="zippy" name="165">Version</a><div><p>Workspaces run on Windows.</p></div>'
            '<a href="#166">November 29, 2026</a>')
        self.payloads[api + '/versions'] = json.dumps({'versions': [{'value': '164'}]})
        self.payloads[api + '/features?version=164&lang=en'] = json.dumps({'total_count': 0, 'features': []})
        req = dict(browser='chrome', source_id=sid, feature_id=future, facts={'platform': ['Windows']})
        for name in ('plain', 'wrapped'):
            if name == 'wrapped':
                self.payloads[archive] = '<div class="answer">' + self.payloads[archive] + '</div>'
            with self.subTest(layout=name):
                jobs = self.cli(name, sid=sid)
                window = run_daily.read(self.work / 'windows' / (sid + '.json'))
                self.assertEqual('after_cutoff', window[archive + '#165'])
                self.assertEqual('after_cutoff', window[archive + '#166'])
                self.assertEqual('before_period', window[archive + '#100'])
                self.assertEqual([archive, api + '/versions', api + '/features?version=164&lang=en'], self.calls)
                for fid in (future, absent):
                    self.assertFalse(jobs[fid].get('candidate') or jobs[fid].get('reference_review'))
                with self.assertRaises(ValueError):
                    self.store_via_cli(dict(req, url=archive + '#165', reference_review=True), run=name)
        later = self.cli('later', '2026-11-30T07:00:00+09:00', sid=sid)[future]['candidate']
        self.assertIn('Windows', later['classification_text'])
        with self.assertRaises(ValueError):
            self.store_via_cli(dict(req, source_item_id=later['source_item_id'],
                                    revision_id=later['revisions'][-1]['revision_id']), run='wrapped')
        self.assertTrue(jobs[translated]['reference_review'])
        self.assertEqual(['Team menus on Linux.', 'Tab folders support ChromeOS.'], jobs[translated]['review_passages'])
        raw_req = dict(req, feature_id=translated, url=archive + '#164', reference_review=True,
                       facts={'platform': ['ChromeOS']})
        self.store_via_cli(raw_req, run='wrapped')
        for fid, value in ((old, 'Mac'), (current, 'Linux')):
            row = jobs[fid]['candidate']
            self.assertIn(value, row['classification_text'])
            self.assertNotIn('Windows', row['classification_text'])
            self.store_via_cli(dict(req, feature_id=fid, source_item_id=row['source_item_id'],
                                    revision_id=row['revisions'][-1]['revision_id'], facts={'platform': [value]}),
                               run='wrapped')
        features = {f['feature_id']: f for f in validate_graph(self.root)['feature']}
        self.assertEqual({}, features[future]['feature_facts'])
        self.assertEqual(['Linux'], features[current]['feature_facts']['platform']['value'])
        self.assertEqual(['Mac'], features[old]['feature_facts']['platform']['value'])
        self.assertEqual(['ChromeOS'], features[translated]['feature_facts']['platform']['value'])

    def test_enterprise_archive_spellings_share_panel_owners_and_verified_passages(self):
        sid = 'chrome-enterprise'
        base = 'https://support.google.com/chrome/a/answer/10314655'
        archive = base + '?hl=en'
        api = 'https://release-notes-787862449254.us-central1.run.app'
        def feature(title, key, url):
            return self.store_via_cli(dict(browser='chrome', source_id=sid, title=title,
                                           canonical_key=key, url=url))['feature_id']
        groups = feature('Tab groups', 'groups', archive + '#164')
        menus = feature('Team menus', 'menus', base + '#164')
        folders = feature('탭 폴더', 'folders', base + '#164')
        spaces = feature('Private spaces', 'spaces', base + '#163')
        with self.assertRaises(ValueError):
            feature('Other language', 'other-language', base + '?hl=fr#164')
        mixed = 'Compared with Team menus, Tab groups now ship on Windows.'
        quote = 'Tab folders on Linux.'
        self.payloads[archive] = (
            '<a href="#164">November 11, 2026</a><a class="zippy" name="164">Version</a>'
            f'<div><p>{mixed}</p><p>{quote}</p></div>'
            '<a href="#163">November 3, 2026</a><a class="zippy" name="163">Version</a>'
            '<div><p>Unlike Team menus, Private spaces now work on Android.</p></div>')
        self.payloads[api + '/versions'] = json.dumps({'versions': [{'value': '164'}]})
        self.payloads[api + '/features?version=164&lang=en'] = json.dumps({'total_count': 0, 'features': []})
        jobs = self.cli('aliases', sid=sid)
        self.assertEqual([archive, api + '/versions', api + '/features?version=164&lang=en'], self.calls)
        with self.subTest('ambiguous paragraph'):
            self.assertFalse(any(jobs[fid].get('candidate') for fid in (groups, menus)))
        with self.subTest('other panel'):
            self.assertEqual('Unlike Team menus, Private spaces now work on Android.', jobs[spaces]['candidate']['classification_text'])
        with self.subTest('explicit verified passage'):
            self.assertTrue(jobs[folders].get('reference_review'))
            self.assertEqual([mixed, quote], jobs[folders]['review_passages'])
            request = dict(browser='chrome', source_id=sid, url=base + '#164', feature_id=folders,
                           reference_review=True, facts={'platform': ['Linux']})
            with self.assertRaises(ValueError):
                self.store_via_cli(dict(request, evidence_quote='Unlike Team menus, Private spaces now work on Android.'), run='aliases')
            result = self.store_via_cli(dict(request, evidence_quote=quote), run='aliases')
            self.assertEqual((folders, False), (result['feature_id'], result['changed']))
            graph = validate_graph(self.root)
            features = {f['feature_id']: f for f in graph['feature']}
            self.assertFalse(features[menus]['feature_facts'])
            fact = features[folders]['feature_facts']['platform']
            row = next(r for r in graph['source_item'] if r['source_item_id'] == fact['source_item_id'])
            self.assertEqual(base + '#164', row['evidence']['url'])
            self.assertEqual(quote, features[folders]['source_revision_excerpts'][fact['revision_id']])

    def test_unlisted_enterprise_version_cannot_bypass_publisher_visibility(self):
        sid = 'chrome-enterprise'
        api = 'https://release-notes-787862449254.us-central1.run.app'
        stale = api + '/features?version=101&lang=en'
        current = api + '/features?version=102&lang=en'
        saved_url = stale.replace('version=101&lang=en', 'lang=en&version=101#item')
        fid = self.apply(dict(browser='chrome', source_id=sid, url=saved_url, title='Tab groups', canonical_key='tabs'))['feature_id']
        archive = 'https://support.google.com/chrome/a/answer/10314655?hl=en'
        self.payloads[archive] = ('<a href="#101">April 1, 2026</a><a class="zippy" name="101">Version</a>'
                                  '<div><p>Historical public notes.</p></div>')
        self.payloads[api + '/versions'] = json.dumps(dict(versions=[dict(value='102')]))
        self.payloads[current] = json.dumps(dict(total_count=0, features=[]))
        self.payloads[stale] = json.dumps(dict(total_count=1, features=[dict(id=12345, confidential=True)]))
        job = self.cli('unlisted', sid=sid)[fid]
        self.assertFalse(job.get('reference_review'))
        self.assertNotIn('candidate', job)
        self.assertEqual([archive, api + '/versions', current], self.calls)
        request = dict(feature_id=fid, browser='chrome', source_id=sid, url=saved_url, facts={'platform': ['Windows']})
        with self.assertRaises(ValueError):
            verified_reference(self.work, self.state, request)

    def test_future_index_prevents_detail_reinspection_across_resume(self):
        future = HOME + '2026/11/upcoming.html'
        fid = self.select('Upcoming tabs', future)
        peer = self.select('Toolbars', URL)
        self.payloads[HOME] = card(future).replace('2026-04-01', '2026-11-28') + card(URL)
        self.payloads[future] = '<div class="post-body"><p>Upcoming tabs will ship on Windows.</p></div>'
        self.payloads[URL] = OSError('try peer later')
        jobs = self.cli('fixed')
        self.assertNotIn('candidate', jobs[fid])
        self.assertNotIn(future, self.calls)
        self.assertIn('error', jobs[peer])
        self.payloads[URL] = '<div class="post-body"><p>Toolbars on ChromeOS.</p></div>'
        jobs = self.cli('fixed', resume=True)
        self.assertNotIn('candidate', jobs[fid])
        self.assertFalse(jobs[fid].get('reference_review'))
        self.assertIn('candidate', jobs[peer])
        self.assertNotIn(future, self.calls)
        jobs = self.cli('available', '2026-11-30T07:00:00+09:00')
        self.assertIn('candidate', jobs[fid])
