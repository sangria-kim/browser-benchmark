"""Drive the collection CLIs with a local transport and an isolated feature graph."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline import browser_status, run_daily
from pipeline.collectors.browser import Response
from pipeline.feature_enrichment import read_jobs, verified_candidate
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

    def cli(self, name, cutoff=NOW, *, resume=False, manual=False, expected=0, sid=SID):
        self.calls.clear()
        private = self.folder / 'runs' / name
        entry = 'collect' if manual else 'run_daily'
        args = [entry, '--repository', str(self.root), '--private-dir', str(private if manual else private.parent)]
        if not manual:
            args += ['--run-id', name]
        args += ['--resume'] if resume else ['--cutoff', cutoff, '--source', sid]
        if manual and not resume:
            args += ['--mode', 'manual', '--since', '2026-11-01']
        with patch('sys.argv', args), patch('pipeline.collectors.browser.collector.HTTPTransport', return_value=self.transport):
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
