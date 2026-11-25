import contextlib
import copy
from datetime import datetime, timedelta, timezone
from email.message import Message
from io import BytesIO, StringIO
from urllib.error import HTTPError, URLError
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline.collectors.browser import BrowserCollector, Response
from pipeline.collectors.browser.transport import HTTPTransport
from pipeline.collectors.browser.safari_preview import (
    APPLE_INDEX, CATEGORY, RELEASE_ONE_BUNDLE, RELEASE_ONE_DOCC, RELEASE_ONE_MARKDOWN, RELEASE_ONE_TITLE)



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
        self.proof_calls = []
        self.proof = {}

    def request(self, url, *, direct=False, if_modified_since=None, before_send=None):
        if direct:
            if getattr(self, 'real_direct_transport', False):
                return HTTPTransport()(url, direct=True, if_modified_since=if_modified_since, before_send=before_send)
            before_send()
            self.proof_calls.append((url, if_modified_since))
            result = self.proof[url, if_modified_since]
            if isinstance(result, Exception):
                raise result
            return result
        self.calls.append(url)
        result = self.pages[url]
        if isinstance(result, Exception):
            raise result
        return Response(url, result.encode())

    def run_cli(self, name, mode='daily', expected=0, extra=()):
        argv = ['pipeline.run_daily', '--repository', str(self.repo), '--private-dir', str(self.root / 'runs'),
                '--run-id', name, '--source', SID, '--mode', mode, '--cutoff', CUTOFF, *extra]
        with patch('sys.argv', argv), patch('pipeline.collectors.browser.collector.HTTPTransport', return_value=getattr(self, 'cli_transport', self.request)):
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

    def test_pr34_exact_publication_timestamp_from_head_or_article_byline(self):
        dates = [('Nov 25, 2026', '2026-11-25T07:00:01+09:00'), ('Oct 25, 2026', '2026-10-25T22:00:00Z'),
                 ('Nov 24, 2026', '2026-11-24T22:00:00Z'), ('Oct 25, 2026', '2026-10-25T21:59:59Z')]
        self.pages[APPLE_INDEX] = apple(range(1, 5))
        self.pages[CATEGORY] = page(range(1, 5))
        previous_ids = None
        for field in ('head', 'byline', 'article'):
            for version, (day, stamp) in enumerate(dates, 1):
                text = article(version, None)
                printed = f'<p class="date">{day}</p>'
                if field == 'head':
                    text = text.replace('</head>', f'<meta name="datePublished" content="{stamp}"></head>')
                elif field == 'byline':
                    printed = f'<time class="date" datetime="{stamp}">{day}</time>'
                else:
                    text = text.replace('<article>', f'<article><meta itemprop="datePublished" content="{stamp}">')
                self.pages[release_url(version)] = text.replace('</h1>', f'</h1><div class="byline">{printed}</div>')
            with self.subTest(field=field):
                _, rows = self.run_cli('pr34-' + field)
                actual = {(row['evidence']['url'], row['temporal_scope']['evidence_date'],
                           row['temporal_scope']['precision']) for row in rows}
                self.assertEqual({(release_url(v), dates[v - 1][1], 'timestamp') for v in (2, 3)}, actual)
                ids = {r['source_item_id'] for r in rows}
                if previous_ids is not None:
                    self.assertEqual(previous_ids, ids)
                previous_ids = ids

    def test_pr34_owned_byline_permalinks_at_all_six_signed_boundaries(self):
        moments = ['2026-10-25T21:59:59Z', '2026-10-25T22:00:00Z', '2026-10-25T22:00:01Z',
                   '2026-11-25T06:59:59+09:00', '2026-11-25T07:00:00+09:00', '2026-11-25T07:00:01+09:00']
        self.pages[APPLE_INDEX] = apple(range(1, 7))
        self.pages[CATEGORY] = page(range(1, 7))
        expected = {(release_url(n), moments[n - 1], 'timestamp') for n in (2, 3, 4, 5)}
        stable_ids = None
        for layout in ('direct', 'neutral', 'bookmark', 'absolute', 'metadata-wrapper', 'mixed'):
            for n, at in enumerate(moments, 1):
                url = release_url(n)
                day = 'Oct 25, 2026' if n <= 3 else 'Nov 25, 2026'
                stamp = f'<time class="entry-date published" datetime="{at}">{day}</time>'
                if layout == 'neutral':
                    stamp = '<span><em>' + stamp + '</em></span>'
                elif layout != 'direct':
                    permalink = url if layout == 'absolute' else url.removeprefix('https://webkit.org')
                    stamp = f'<span class="posted-on"><a href="{permalink}" rel="bookmark"><span>{stamp}</span></a></span>'
                if layout == 'mixed':
                    other = ('<a rel="bookmark" href="https://example.org/other"><time class="date published" '
                             'itemprop="datePublished" datetime="2025-02-01T12:00:00Z">Feb 1, 2025</time></a>')
                    stamp = other + stamp
                byline = f'<div class="byline"><p class="date">{day}</p>{stamp}</div>'
                if layout == 'metadata-wrapper':
                    byline = f'<header><div class="entry-meta">{byline}</div></header>'
                self.pages[url] = article(n, None).replace('</h1>', '</h1>' + byline)
            with self.subTest(layout=layout):
                _, rows = self.run_cli('six-' + layout)
                self.assertEqual(expected, {(r['evidence']['url'], r['temporal_scope']['evidence_date'],
                                             r['temporal_scope']['precision']) for r in rows})
                ids = {r['source_item_id'] for r in rows}
                if stable_ids is not None:
                    self.assertEqual(stable_ids, ids)
                stable_ids = ids

    def test_pr34_byline_dates_keep_author_publication_and_update_roles(self):
        url = release_url(1)
        published = '2026-02-01T12:00:00Z'
        updated = '2026-11-02T12:00:00Z'
        byline = (f'<div class="byline"><a rel="bookmark" href="{url}"><span class="date">'
                  f'<time class="entry-date published" datetime="{published}">Feb 1, 2026</time></span></a>'
                  '<span class="date"><span class="updated">'
                  f'<time datetime="{updated}">Nov 2, 2026</time></span></span>'
                  '<a rel="author" href="/author/alice/"><span class="date">'
                  '<time itemprop="datePublished dateModified" datetime="2027-01-01">Jan 1, 2027</time>'
                  '</span></a></div>')
        self.pages[url] = article(1, None).replace('</h1>', '</h1>' + byline)
        _, rows = self.run_cli('byline-owner-roles')
        row, = rows
        self.assertEqual((published[:10], updated, 'item_change'),
                         (row['published_at'], row['temporal_scope']['evidence_date'], row['temporal_scope']['basis']))

    def test_pr34_uncertain_or_conflicting_published_permalink_cannot_downgrade_to_day(self):
        own = release_url(1)
        stamp = '<time class="entry-date published" datetime="2026-11-02T00:00:00Z">Nov 2, 2026</time>'
        for name, anchor in [('unowned', '<a rel="bookmark">'), ('different', f'<a rel="bookmark" href="{release_url(2)}">'),
                             ('conflict', f'<a rel="bookmark" href="{own}">')]:
            byline = '<div class="byline"><p class="date">Nov 2, 2026</p>' + anchor + stamp + '</a></div>'
            if name == 'conflict':
                byline = byline.replace('>Nov 2, 2026</time>', '>Oct 3, 2026</time>')
            self.pages[own] = article(1, None).replace('</h1>', '</h1>' + byline)
            with self.subTest(name=name):
                state, rows = self.run_cli('wrong-bookmark-' + name, expected=2)
                self.assertIn(own, state['pending'])
                self.assertEqual([], rows)

    def test_pr34_reconciles_only_article_owned_revision_fields(self):
        url = release_url(1)
        original = article(1, '2026-02-15').replace('<article>', '<article><meta name="dateModified" content="2026-11-01">')
        unrelated = ('<section><div class="byline"><time class="date" datetime="2027-01-01">Jan 1, 2027</time></div>'
                     '<meta itemprop="dateModified" content="2027-01-01"></section>'
                     '<footer><meta property="article:modified_time" content="2027-01-01"></footer>')
        self.pages[url] = original.replace('</article>', unrelated + '</article>').replace(
            '<p id="tabs">', '<div class="byline"><time class="date" datetime="2027-01-01">Jan 1, 2027</time></div><p id="tabs">')
        _, rows = self.run_cli('pr34-related')
        row, = rows
        self.assertEqual(('2026-02-15', '2026-11-01', 'item_change'),
                         (row['published_at'], row['temporal_scope']['evidence_date'], row['temporal_scope']['basis']))
        for name, conflict in [('modified', '<meta property="dateModified" content="2026-11-02">'),
                               ('published', '<meta name="datePublished" content="2026-02-20">'),
                               ('roles', '<meta itemprop="dateModified datePublished" content="2026-11-01">'),
                               ('late', '<meta name="article:modified_time" content="2026-11-25T07:00:01+09:00">')]:
            with self.subTest(name=name):
                self.pages[url] = original.replace('</head>', conflict + '</head>')
                state, rows = self.run_cli('pr34-conflict-' + name, expected=2)
                self.assertIn(url, state['pending'])
                self.assertEqual([], rows)

    def test_pr34_stop_blocked_webkit_host_and_resume(self):
        self.pages[APPLE_INDEX] = apple([3, 2, 1])
        self.pages[CATEGORY] = page([3, 2, 1])
        urls = [release_url(v) for v in (3, 2, 1)]
        now = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
        for case, failure in [('limited', HTTPError(urls[0], 429, 'rate limited', {'Retry-After': '3600'}, None)),
                              ('forbidden', HTTPError(urls[0], 403, 'forbidden', {}, None)),
                              ('timeout', TimeoutError('timeout')), ('url-timeout', URLError(TimeoutError('timeout')))]:
            with self.subTest(case=case), patch('pipeline.collectors.browser.safari_preview.datetime', wraps=datetime) as clock:
                clock.now.return_value = now
                for v in (1, 2, 3):
                    self.pages[release_url(v)] = article(v, '2026-11-01')
                self.pages[urls[0]] = failure
                self.calls.clear()
                state, _ = self.run_cli('pr34-' + case, expected=2)
                self.assertEqual([APPLE_INDEX, CATEGORY, urls[0]], self.calls)
                self.assertEqual(set(urls), set(state['pending']))
                self.pages[urls[0]] = article(3, '2026-11-01')
                if case == 'limited':
                    self.calls.clear()
                    clock.now.return_value = now + timedelta(seconds=3599)
                    state, _ = self.run_cli('pr34-' + case, expected=2, extra=['--resume'])
                    self.assertEqual([], self.calls)
                    self.assertEqual(set(urls), set(state['pending']))
                    clock.now.return_value = now + timedelta(hours=1)
                self.calls.clear()
                state, rows = self.run_cli('pr34-' + case, extra=['--resume'])
                self.assertEqual([APPLE_INDEX, CATEGORY, *urls], self.calls)
                self.assertEqual((3, []), (len(rows), state['pending']))

    def test_pr34_transport_defers_429_without_sending_past_deadline(self):
        self.cli_transport = HTTPTransport()
        now = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
        for label, blocked in [('category', CATEGORY), ('detail', release_url(1))]:
            clock = [0]
            wire = []
            refused = [False]
            def send(request, timeout):
                url = request.full_url
                wire.append((url, clock[0]))
                if url == blocked and not refused[0]:
                    refused[0] = True
                    clock[0] = 899
                    raise HTTPError(url, 429, 'rate limited', {'Retry-After': '30'}, BytesIO())
                result = BytesIO(self.pages[url].encode())
                result.url, result.status, result.headers = url, 200, {}
                return result

            def advance(seconds):
                clock[0] += seconds

            with self.subTest(blocked=label), patch('pipeline.collectors.browser.transport.urlopen', side_effect=send), \
                    patch('pipeline.collectors.browser.transport.build_opener') as opener, \
                    patch('pipeline.collectors.browser.transport.time.sleep', side_effect=advance), \
                    patch('pipeline.collectors.browser.collector.monotonic', side_effect=lambda: clock[0]), \
                    patch('pipeline.collectors.browser.safari_preview.datetime', wraps=datetime) as wall:
                opener.return_value.open.side_effect = send
                wall.now.side_effect = lambda tz: now + timedelta(seconds=clock[0])
                name = 'wire-cutoff-' + label
                state, _ = self.run_cli(name, expected=2)
                expected = [APPLE_INDEX, CATEGORY] + ([release_url(1)] if label == 'detail' else [])
                self.assertEqual(expected, [u for u, _ in wire])
                self.assertIn(blocked, state['pending'])
                wire.clear()
                clock[0] = 928
                self.run_cli(name, expected=2, extra=['--resume'])
                self.assertEqual([], wire)
                clock[0] = 929
                state, rows = self.run_cli(name, extra=['--resume'])
                self.assertEqual([APPLE_INDEX, CATEGORY, release_url(1)], [u for u, _ in wire])
                self.assertEqual((1, []), (len(rows), state['pending']))

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

    def test_dated_section_cannot_redate_a_verified_release(self):
        self.pages[release_url(1)] = article(1, None).replace('</h1>', '</h1><div class="byline"><p class="date">Nov 2, 2026</p></div>').replace(
            '<p id="tabs">', '<h2>Compared with Feb 1, 2026</h2><p id="tabs">')
        _, rows = self.run_cli('dated-heading')
        row, = rows
        self.assertEqual(('2026-11-02', 'day', 'in_period'),
                         (row['published_at'], row['temporal_scope']['precision'], row['temporal_scope']['status']))

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

    def test_archive_rejects_unusable_release_cards_and_dynamic_pagination(self):
        first = page([1])
        for name, attributes in [('insecure', f'href="{release_url(2).replace("https:", "http:")}"'),
                                 ('missing-link', '')]:
            with self.subTest(name=name):
                second = f'<a class="tile-link" {attributes}>Release Notes for Safari Technology Preview 2</a>'
                self.pages[CATEGORY] = first.replace('</div>', second + '</div>', 1)
                state, _ = self.run_cli(name, expected=2)
                self.assertTrue(state['pending'])
        self.pages[CATEGORY] = first.replace('</div>', '<button>Load more</button></div>', 1)
        state, _ = self.run_cli('load-more', expected=2)
        self.assertIn('pagination', str(state['errors']))
        news = '<a class="tile-link" href="https://webkit.org/blog/999/engine-news/">A WebKit engineering update</a>'
        self.pages[CATEGORY] = first.replace('</div>', news + '</div>', 1)
        _, rows = self.run_cli('news-card')
        self.assertEqual([release_url(1)], [r['evidence']['url'] for r in rows])
        self.assertNotIn('https://webkit.org/blog/999/engine-news/', self.calls)

    def configure_release_one(self):
        self.pages[APPLE_INDEX] = apple([2, 1], year=2016)
        self.pages[CATEGORY] = page([2])
        self.pages[release_url(2)] = article(2, '2016-04-01')
        since = 'Sun, 25 Oct 2026 21:59:59 GMT'
        identifier = '/documentation/' + RELEASE_ONE_BUNDLE + '/stp-release-1'
        metadata = dict(title=RELEASE_ONE_TITLE, role='article', documentType='article',
                        framework='Safari Technology Preview Release Notes', identifier=identifier)
        md = ['<!--' + json.dumps(metadata) + '-->', '# ' + RELEASE_ONE_TITLE, 'Summary.', '## Overview', 'Overview.']
        def paragraph(text):
            return dict(type='paragraph', inlineContent=[dict(type='text', text=text)])
        content = [dict(type='heading', level=2, text='Overview'), paragraph('Overview.')]
        for heading in ('Browser Differences', 'JavaScript Improvements', 'HTML Enhancements', 'Web Inspector Changes', 'Behavior Changes'):
            md.extend(['### ' + heading, '- A documented item.'])
            content.extend([dict(type='heading', level=3, text=heading),
                            dict(type='unorderedList', items=[dict(content=[paragraph('A documented item.')])])])
        md.extend(['---', 'Copyright &copy; 2026 Apple Inc. All rights reserved. | '
                   '[Terms of Use](https://www.apple.com/legal/internet-services/terms/site.html) | '
                   '[Privacy Policy](https://www.apple.com/privacy/privacy-policy)'])
        doc = dict(kind='article', metadata=dict(role='article', title=RELEASE_ONE_TITLE),
                   identifier=dict(url='doc://com.apple.' + RELEASE_ONE_BUNDLE + identifier),
                   abstract=[dict(type='text', text='Summary.')], sections=[], primaryContentSections=[dict(kind='content', content=content)])
        for url, media, body, tag in ((RELEASE_ONE_MARKDOWN, 'text/markdown', '\n'.join(md), '"md"'),
                                      (RELEASE_ONE_DOCC, 'application/json', json.dumps(doc), '"docc"')):
            self.proof[url, None] = Response(url, body.encode(), 200, {
                'Content-Type': media, 'ETag': tag, 'Last-Modified': 'Thu, 06 Aug 2026 02:56:49 GMT', 'Vary': 'Accept-Encoding'})
            self.proof[url, since] = Response(url, b'', 304, {'ETag': tag, 'Vary': 'Accept-Encoding'})
        for response in self.proof.values():
            response.observed_at = '2026-11-25T12:00:52Z'
            response.headers.update({'Date': 'Wed, 25 Nov 2026 12:00:50 GMT', 'Age': '2', 'Cache-Control': 'public, max-age=300'})
        return since

    def test_release_one_four_live_requests_and_only_daily_coverage(self):
        since = self.configure_release_one()
        state, rows = self.run_cli('old-first')
        self.assertEqual([APPLE_INDEX, CATEGORY, release_url(2)], self.calls)
        self.assertEqual([(RELEASE_ONE_MARKDOWN, None), (RELEASE_ONE_DOCC, None),
                          (RELEASE_ONE_MARKDOWN, since), (RELEASE_ONE_DOCC, since)], self.proof_calls)
        self.assertEqual((2, 5, [], []), (state['pages'], state['documents'], rows, state['pending']))
        receipt = state['preview_inventory']['release_one_exclusion']
        self.assertEqual(since, receipt['if_modified_since'])
        self.assertEqual(CUTOFF, receipt['cutoff'])
        self.assertFalse((self.repo / 'data').exists())
        for mode in ('weekly_reconcile', 'manual', 'legacy'):
            self.proof_calls.clear()
            state, _ = self.run_cli('mode-' + mode, mode, expected=2)
            self.assertIn('Missing canonical WebKit release URL', str(state['errors']))
            self.assertEqual([], self.proof_calls)
        self.pages[CATEGORY] = page([1, 2])
        self.pages[release_url(1)] = article(1, '2016-03-30')
        self.run_cli('use-webkit')
        self.assertEqual([], self.proof_calls)
        self.pages[CATEGORY] = page([2])
        self.pages[APPLE_INDEX] = apple([3, 2, 1], year=2016)
        state, _ = self.run_cli('missing-third', expected=2)
        self.assertIn('#stp-release-3', str(state['pending']))
        self.assertNotIn('release_one_exclusion', state['preview_inventory'])

    def test_release_one_refuses_ambiguous_identity_time_and_validators(self):
        since = self.configure_release_one()
        original = copy.deepcopy(self.proof)
        for name, url, condition, field, value in [
                ('wrong-doc', RELEASE_ONE_DOCC, None, 'body', self.proof[RELEASE_ONE_DOCC, None].body.replace(b'stp-release-1', b'stp-release-2')),
                ('conflict-md', RELEASE_ONE_MARKDOWN, None, 'body', self.proof[RELEASE_ONE_MARKDOWN, None].body.replace(b'A documented item.', b'Changed.')),
                ('truncated', RELEASE_ONE_MARKDOWN, None, 'body', b'<!-- truncated -->'),
                ('empty', RELEASE_ONE_DOCC, None, 'body', b'{}'),
                ('redirected', RELEASE_ONE_MARKDOWN, None, 'url', 'https://developer.apple.com/other'),
                ('bad-mime', RELEASE_ONE_DOCC, None, 'Content-Type', 'text/html'),
                ('weak', RELEASE_ONE_DOCC, None, 'ETag', 'W/"docc"'),
                ('malformed-time', RELEASE_ONE_MARKDOWN, None, 'Last-Modified', 'unknown'),
                ('inclusive', RELEASE_ONE_MARKDOWN, None, 'Last-Modified', 'Sun, 25 Oct 2026 22:00:00 GMT'),
                ('post-cutoff', RELEASE_ONE_DOCC, None, 'Last-Modified', 'Wed, 25 Nov 2026 12:00:00 GMT'),
                ('unexpected-variant', RELEASE_ONE_DOCC, None, 'Vary', '*'),
                ('md-changed', RELEASE_ONE_MARKDOWN, since, 'status', 200),
                ('docc-changed', RELEASE_ONE_DOCC, since, 'status', 200),
                ('conditional-body', RELEASE_ONE_DOCC, since, 'body', b'x'),
                ('stale-tag', RELEASE_ONE_MARKDOWN, since, 'ETag', '"different"'),
                ('observation-before-cutoff', RELEASE_ONE_DOCC, since, 'observed_at', '2026-11-23T10:00:00Z'),
                ('conditional-later', RELEASE_ONE_MARKDOWN, since, 'Last-Modified', 'Wed, 25 Nov 2026 12:00:00 GMT')]:
            with self.subTest(name=name):
                self.proof = copy.deepcopy(original)
                r = self.proof[url, condition]
                if field in ('url', 'body', 'status', 'observed_at'):
                    setattr(r, field, value)
                else:
                    r.headers[field] = value
                state, rows = self.run_cli(name, expected=2)
                self.assertEqual([], rows)
                self.assertEqual(1, len(state['errors']))
                self.assertIn('#stp-release-1', state['pending'][0])
                self.assertNotIn('release_one_exclusion', state['preview_inventory'])

    def test_release_one_stale_freshness_or_duplicate_response_fields_block(self):
        since = self.configure_release_one()
        original = copy.deepcopy(self.proof)
        for i, (condition, headers) in enumerate([
                (None, {'Date': 'Mon, 23 Nov 2026 12:00:50 GMT', 'Age': '7200', 'Cache-Control': 'max-age=300, stale-if-error=14400',
                        'Warning': '110 cache "Response is stale"'}),
                (since, {'Date': 'Tue, 24 Nov 2026 21:59:59 GMT'}),
                (since, {'Date': 'Wed, 25 Nov 2026 12:10:00 GMT'}),
                (None, {'Age': '301'}), (since, {'Age': 'invalid'}), (since, {'Age': '300'}),
                (since, {'Warning': '111 cache "Revalidation failed"'}),
                (None, {'Cache-Status': 'edge; hit; ttl=-5'}), (since, {'Expires': 'Mon, 23 Nov 2026 12:00:50 GMT'}),
                (since, {'ETag': '"wrong"', 'etag': '"md"'}),
                (None, {'last-modified': 'Thu, 06 Aug 2026 02:56:49 GMT'}),
                (since, {'date': 'Wed, 25 Nov 2026 12:00:50 GMT'}),
                (None, {'content-type': 'text/markdown'})]):
            with self.subTest(case=i):
                self.proof = copy.deepcopy(original)
                self.proof[RELEASE_ONE_MARKDOWN, condition].headers.update(headers)
                state, rows = self.run_cli('stale-' + str(i), expected=2)
                self.assertTrue(state['pending'])
                self.assertEqual([], rows)
                self.assertNotIn('release_one_exclusion', state['preview_inventory'])

    def test_real_direct_transport_charges_retries_and_keeps_duplicate_wire_headers(self):
        since = self.configure_release_one()
        self.real_direct_transport = True
        wire = []
        duplicate = False
        stop_after_first = False
        clock = [0]

        def send(request, timeout):
            nonlocal duplicate
            fields = {k.lower(): v for k, v in request.header_items()}
            self.assertEqual(('GET', 'no-cache', 'identity'), (request.get_method(), fields['cache-control'], fields['accept-encoding']))
            self.assertNotIn('if-none-match', fields)
            key = (request.full_url, fields.get('if-modified-since'))
            wire.append(key)
            if len(wire) == 1:
                if stop_after_first:
                    clock[0] += 901
                raise HTTPError(key[0], 429, 'Rate limit', Message(), BytesIO())
            fixture = self.proof[key]
            headers = Message()
            for k, v in fixture.headers.items():
                headers[k] = v
            if key[1] is not None:
                if duplicate:
                    headers['etag'] = headers['ETag']
                raise HTTPError(key[0], 304, 'Not modified', headers, BytesIO())
            result = BytesIO(fixture.body)
            result.url, result.status, result.headers = key[0], fixture.status, headers
            return result

        with patch('pipeline.collectors.browser.transport.build_opener') as opener, patch('pipeline.collectors.browser.transport.time.sleep'), \
                patch('pipeline.collectors.browser.collector.monotonic', side_effect=lambda: clock[0]), \
                patch('pipeline.collectors.browser.safari_preview.datetime') as clock_timestamp:
            from datetime import datetime
            clock_timestamp.now.return_value = datetime.fromisoformat('2026-11-25T12:00:52+00:00')
            opener.return_value.open.side_effect = send
            state, _ = self.run_cli('wire-retry')
            self.assertEqual(5, len(wire))
            self.assertEqual(6, state['documents'])  # One WebKit detail plus five Apple attempts.
            self.assertEqual([2, 1, 1, 1], [v['http_attempts'] for v in state['preview_inventory']['release_one_requests']])
            wire.clear()
            duplicate = True
            state, _ = self.run_cli('wire-duplicate', expected=2)
            self.assertIn('Duplicate Apple release-1 HTTP header: etag', str(state['errors']))
            wire.clear()
            stop_after_first = True
            state, _ = self.run_cli('wire-deadline', expected=2)
            self.assertEqual([(RELEASE_ONE_MARKDOWN, None)], wire)
            self.assertIn('time budget', str(state['errors']))

    def test_release_one_budget_resume_fresh_gets_and_cache_integrity(self):
        since = self.configure_release_one()
        registry = json.loads(self.registry.read_text())
        src = next(s for s in registry['sources'] if s['source_id'] == SID)
        src['discovery']['max_documents'] = 4
        self.registry.write_text(json.dumps(registry))
        for name, corrupt in [('continued', None), ('bad-cache', 'cache'), ('new-identity', 'etag')]:
            self.proof_calls.clear()
            self.configure_release_one()
            state, _ = self.run_cli(name, expected=2)
            self.assertEqual(4, state['documents'])
            self.assertEqual(3, len(self.proof_calls))
            work = self.root / 'runs' / name / 'work/browser'
            progress = json.loads((work / (SID + '-progress.json')).read_text())
            journal = progress['apple_release_one']['requests']
            self.assertEqual(3, len(journal))
            if corrupt == 'cache':
                (work / 'cache' / journal[RELEASE_ONE_MARKDOWN + ' full']['sha256']).write_bytes(b'altered')
            elif corrupt == 'etag':
                self.proof[RELEASE_ONE_MARKDOWN, None].headers['ETag'] = '"changed"'
            self.proof_calls.clear()
            state, _ = self.run_cli(name, expected=2 if corrupt else 0, extra=['--resume'])
            if corrupt:
                self.assertIn('checksum' if corrupt == 'cache' else 'changed on resume', str(state['errors']))
                self.assertNotIn('release_one_exclusion', state['preview_inventory'])
            else:
                self.assertEqual(len(self.proof_calls), 4)
                self.assertEqual((RELEASE_ONE_DOCC, since), self.proof_calls[-1])
                self.assertIn('release_one_exclusion', state['preview_inventory'])

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
