import contextlib
from io import StringIO
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline.collectors.browser import BrowserCollector, Response
from pipeline.collectors.browser.safari_preview import APPLE_INDEX, CATEGORY


ROOT = Path(__file__).resolve().parents[1]
SID = 'safari-technology-preview'
CUTOFF = '2026-11-25T07:00:00+09:00'
URL_251 = 'https://webkit.org/blog/18194/release-notes-for-safari-technology-preview-251/'


def release_url(n):
    if n == 251:
        return URL_251
    return f'https://webkit.org/blog/{1000 + n}/release-notes-for-safari-technology-preview-{n}/'


def apple(versions, year=2026):
    rows = [f'[Safari Technology Preview {n} Release Notes]'
            f'(/documentation/Safari-Technology-Preview-Release-Notes/stp-release-{n})' for n in versions]
    return '\n'.join(['# Safari Technology Preview Release Notes', '## Topics', f'### {year}', *rows,
                      'Copyright &copy; Apple | [Privacy Policy](https://www.apple.com/privacy/privacy-policy)'])


def page(versions, page_number=1, next_page=False):
    cards = ''.join(f'<a class="tile-link" href="{release_url(n)}">Release Notes for Safari Technology Preview {n}</a>'
                    for n in versions)
    link = f'<a class="page-numbers next" href="{CATEGORY}page/2/">Next</a>' if next_page else ''
    return (f'<html><div id="posts">{cards}</div><nav class="pagination">'
            f'<span aria-current="page">Page {page_number}</span>{link}</nav></html>')


def article(n, day, text='Tab search is available.', modified=None):
    date = f'<meta property="article:published_time" content="{day}">' if day else ''
    change = f'<meta property="article:modified_time" content="{modified}">' if modified else ''
    return (f'<html><head><link rel="canonical" href="{release_url(n)}">{date}{change}</head>'
            f'<article><h1>Release Notes for Safari Technology Preview {n}</h1>'
            f'<div class="bodycopy"><p id="tabs">{text}</p></div></article></html>')


class PreviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / 'repo'
        shutil.copytree(ROOT / 'config', self.repo / 'config')
        self.registry = self.repo / 'config/sources.yml'
        self.source = next(s for s in json.loads(self.registry.read_text())['sources'] if s['source_id'] == SID)
        self.pages = {APPLE_INDEX: apple([1]), CATEGORY: page([1]), release_url(1): article(1, '2026-11-01')}
        self.calls = []

    def request(self, url):
        self.calls.append(url)
        result = self.pages[url]
        if isinstance(result, Exception):
            raise result
        return Response(url, result.encode())

    def run_cli(self, name, mode='daily', expected=0, extra=()):
        argv = ['pipeline.run_daily', '--repository', str(self.repo), '--private-dir', str(self.root / 'runs'),
                '--run-id', name, '--source', SID, '--mode', mode, '--cutoff', CUTOFF, *extra]
        with patch('sys.argv', argv), patch('pipeline.collectors.browser.collector.HTTPTransport', return_value=self.request):
            with contextlib.redirect_stdout(StringIO()), self.assertRaises(SystemExit) as exit_status:
                runpy.run_path(str(ROOT / 'pipeline/run_daily.py'), run_name='__main__')
        work = self.root / 'runs' / name / 'work'
        state = json.loads((work / 'browser' / (SID + '.json')).read_text())
        self.assertEqual(expected, exit_status.exception.code, state['errors'])
        return state, json.loads((work / 'candidates' / (SID + '.json')).read_text())

    def test_weekly_recovers_251_and_preserves_existing_item_and_revision(self):
        # Seed the historical public row through the original html_index path.
        url = release_url(251)
        self.pages[url] = article(251, '2026-08-26T14:36:31-07:00')
        self.pages[CATEGORY] = page([251])
        old = BrowserCollector(self.repo, self.root / 'legacy', self.request)
        with patch('pipeline.collectors.browser.collector.collect_safari_preview', BrowserCollector.collect_html):
            state = old.collect(self.source, CUTOFF, '2026-01-01')
        self.assertEqual('complete', state['status'])
        existing, = old.records.values()
        self.assertEqual(url, existing['evidence']['url'])
        self.pages[APPLE_INDEX] = apple(range(252, 0, -1))
        self.pages[CATEGORY] = page([252, 250, 250], next_page=True)
        self.pages[CATEGORY + 'page/2/'] = page(range(249, 0, -1), page_number=2)
        for n in range(1, 253):
            self.pages.setdefault(release_url(n), article(n, '2026-02-10'))
        self.calls.clear()
        state, rows = self.run_cli('week', 'weekly_reconcile')
        self.assertEqual([251], state['preview_inventory']['historical_fallbacks'])
        self.assertEqual((3, 252), (state['pages'], state['documents']))
        self.assertEqual(1, self.calls.count(url))
        self.assertEqual(1, state['duplicate'])
        self.assertNotIn(existing['source_item_id'], [r['source_item_id'] for r in rows])
        self.pages[url] = article(251, '2026-08-26T14:36:31-07:00', 'Tab search was improved.')
        _, rows = self.run_cli('updated', 'weekly_reconcile')
        changed, = [r for r in rows if r['evidence']['url'] == url]
        self.assertEqual(existing['source_item_id'], changed['source_item_id'])
        self.assertEqual(existing['revisions'], changed['revisions'][:-1])

    def test_exact_dates_old_article_modification_and_unknown_or_future_revision(self):
        dates = ['2026-10-25T21:59:59Z', '2026-10-25T22:00:00Z', '2026-11-24T22:00:00Z',
                 '2026-11-24T22:00:01Z', '2026-02-10']
        self.pages[APPLE_INDEX] = apple(range(1, 6))
        self.pages[CATEGORY] = page(range(1, 6))
        for n, day in enumerate(dates, 1):
            self.pages[release_url(n)] = article(n, day, modified='2026-11-01' if n == 5 else None)
        _, rows = self.run_cli('bounds')
        self.assertEqual({release_url(n) for n in (2, 3, 5)}, {r['evidence']['url'] for r in rows})
        self.pages[release_url(1)] = article(1, None)
        self.pages[release_url(5)] = article(5, dates[-1], modified='2026-11-25T09:00:00+09:00')
        state, rows = self.run_cli('blocked', expected=2)
        self.assertEqual({release_url(1), release_url(5)}, set(state['pending']))
        self.assertEqual({release_url(2), release_url(3)}, {r['evidence']['url'] for r in rows})

    def test_verified_printed_webkit_date_controls_both_window_boundaries(self):
        # Page chrome can contain a more precise timestamp unrelated to this release.
        dates = [
            ('Oct 26, 2026', '2026-02-01T12:00:00Z'),
            ('Nov 25, 2026', '2026-12-01T12:00:00Z'),
            ('Oct 25, 2026', '2026-11-02T12:00:00Z'),
            ('Nov 26, 2026', '2026-11-02T12:00:00Z'),
        ]
        self.pages[APPLE_INDEX] = apple(range(1, 5))
        self.pages[CATEGORY] = page(range(1, 5))
        for n, (printed, unrelated) in enumerate(dates, 1):
            detail = article(n, None).replace('<article>', f'<time datetime="{unrelated}"></time><article>')
            self.pages[release_url(n)] = detail.replace('</h1>', f'</h1><div class="byline"><p class="date">{printed}</p></div>')
        _, rows = self.run_cli('printed')
        self.assertEqual({(release_url(1), '2026-10-26'), (release_url(2), '2026-11-25')},
                         {(r['evidence']['url'], r['published_at']) for r in rows})
        self.assertTrue(all(r['temporal_scope']['precision'] == 'day' for r in rows))

    def test_uncovered_older_version_and_conflicting_or_truncated_evidence(self):
        self.pages[APPLE_INDEX] = apple([1, 2], year=2020)
        self.pages[CATEGORY] = page([2])
        self.pages[release_url(2)] = article(2, '2020-03-01')
        state, _ = self.run_cli('apple-only', expected=2)
        self.assertIn('Missing canonical', str(state['errors']))
        self.pages[APPLE_INDEX] = apple([1], year=2020)
        self.pages[CATEGORY] = page([1])
        self.pages[release_url(1)] = article(1, '2020-03-01')
        for name, overrides in [
            ('wrong-year', {APPLE_INDEX: apple([1], year=2026)}),
            ('wrong-identity', {release_url(1): article(1, '2020-03-01').replace('Preview 1</h1>', 'Preview 3</h1>')}),
            ('missing-detail', {release_url(1): ValueError('HTTP 404')}),
            ('broken-index', {APPLE_INDEX: apple([1, 2]).split('Copyright')[0]}),
            ('broken-webkit', {CATEGORY: page([1]).removesuffix('</html>')}),
            ('conflicting-card', {CATEGORY: page([1]).replace('Preview 1</a>', 'Preview 3</a>')}),
            ('malformed-modified', {release_url(1): article(1, '2020-03-01', modified='invalid')}),
            ('missing-next', {CATEGORY: page([2], next_page=True).replace('page-numbers next', 'page-numbers').replace('>Next<', '>2<')}),
        ]:
            with self.subTest(name=name), patch.dict(self.pages, overrides):
                result, rows = self.run_cli(name, expected=2)
                self.assertTrue(result['errors'])
                self.assertEqual([], rows)

    def test_limits_and_revalidation_on_resume(self):
        registry = json.loads(self.registry.read_text())
        source = next(s for s in registry['sources'] if s['source_id'] == SID)
        source['discovery']['max_pages'] = 1
        self.registry.write_text(json.dumps(registry))
        state, _ = self.run_cli('limited', expected=2)
        self.assertEqual([APPLE_INDEX], self.calls)
        self.assertEqual([CATEGORY], state['pending'])
        self.pages[APPLE_INDEX] = apple([1, 2])
        state, _ = self.run_cli('limited', expected=2, extra=['--resume'])
        self.assertIn('Mutable enumeration changed', str(state['errors']))
        self.assertEqual([APPLE_INDEX, APPLE_INDEX], self.calls)
