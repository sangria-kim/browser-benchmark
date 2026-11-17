import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from pipeline.collectors.browser import BrowserCollector, Response
from pipeline.collectors.browser.collector import digest, minimal, docc_items, markdown_items
from pipeline.collectors.browser.html import date_value, Tree, boundary, blocks
from pipeline.collectors.browser.cache import seed_cache
from schemas.validate import load_config, validate_dataset

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/browser'
REGISTRY = load_config(ROOT / 'config/sources.yml')
CUTOFF = '2026-11-16T00:00:00Z'


def source(name):
    return copy.deepcopy(next(s for s in REGISTRY['sources'] if s['source_id'] == name))


def response(url, value, headers=None, status=200):
    body = value.encode() if isinstance(value, str) else json.dumps(value).encode()
    return Response(url, body, status, headers or {})


class Transport:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        result = self.mapping[url]
        if isinstance(result, Exception):
            raise result
        return result


class CollectorsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'repo'
        self.root.mkdir()
        self.private = Path(self.tmp.name) / 'private'

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, s, mapping, cutoff=CUTOFF, since='2026-10-28'):
        self.transport = Transport(mapping)
        state = BrowserCollector(self.root, self.private, self.transport).collect(s, cutoff, since)
        records = json.loads((self.root / 'data/source-items' / s['browser'] / (s['source_id'] + '.json')).read_text())
        validate_dataset({'source_item': records}, {s['source_id']})
        self.assertEqual(state['discovered'], state['processed'] + state['duplicate'] + state['unparsed'])
        return state, records

    def release(self, url, body=None):
        return response(url, body or (FIXTURES / 'releases.html').read_text())

    def index(self, s, urls, next_url=None):
        text = ''.join('<h2><a href="%s">Release</a></h2>' % u for u in urls)
        if next_url:
            text += '<a rel="next" href="%s">next</a>' % next_url
        return response(s['url'], text)

    def test_all_types_pagination_language_duplicates_and_idempotence(self):
        s = source('vivaldi-desktop')
        en, ko = 'https://vivaldi.com/blog/release-en/', 'https://vivaldi.com/blog/release-ko/'
        second = s['url'] + 'page/2/'
        mapping = {s['url']: self.index(s, [en], second), second: self.index(s, [en, ko]),
                   en: self.release(en), ko: self.release(ko)}
        state, records = self.collect(s, mapping)
        self.assertEqual('complete', state['status'])
        self.assertEqual(8, len(records))
        self.assertEqual({'general', 'security', 'fix'}, {r['item_type'] for r in records})
        self.assertTrue(all('Navigation' not in str(r) and 'Personal reply' not in str(r) for r in records))
        again, same = self.collect(s, mapping, '2026-11-16T01:00:00Z')
        self.assertEqual(records, same)
        self.assertEqual(8, again['duplicate'])

    def test_chrome_releases_reads_inert_post_templates_once(self):
        s = source('chrome-releases')
        url = s['url'] + '2026/11/chromeos.html'
        future = s['url'] + '2026/11/future.html'
        fragment = '''
            <h2>ChromeOS changes</h2>
            <p id="rollout">Stable rollout for ChromeOS &amp; ChromeOS Flex.</p>
            <ul><li id="fix">Fixed a startup crash.</li></ul>
            <p>Example Signoff<br><a href="/team">Google ChromeOS</a></p>
            <span itemprop="author"><p>Author metadata</p></span>
            <nav><p>Template navigation</p></nav>
        '''
        html = '''
            <script type="text/template"><p>Outside the post body</p></script>
            <div class="post-header">
                <span class="publishdate" itemprop="datePublished">Friday, November 13, 2026</span>
            </div>
            <div class="post-body entry-content">
                <script type="text/template"><p>Outside the post content</p></script>
                <div class="post-content">
                    <script type="text/template">{fragment}</script>
                    <noscript>{fragment}</noscript>
                    <script><p>Inline script</p></script>
                    <script type="text/javascript"><p>Executable script</p></script>
                    <script type="text/template" src="example"><p>External script</p></script>
                    <nav><script type="text/template"><p>Navigation template</p></script></nav>
                    <p id="normal">Updated release notes.</p>
                </div>
            </div>
        '''.format(fragment=fragment)
        state, records = self.collect(s, {
            s['url']: self.index(s, [url, future]),
            url: self.release(url, html),
            future: self.release(future, html.replace('November 13', 'November 20')),
        })
        self.assertEqual('partial', state['status'])
        self.assertEqual(4, state['discovered'])
        self.assertEqual(1, state['unparsed'])
        self.assertEqual([future], state['excluded_by_date'])
        self.assertEqual({'2026-11-13'}, {r['published_at'] for r in records})
        self.assertEqual({
            'rollout': 'Stable rollout for ChromeOS & ChromeOS Flex.',
            'fix': 'Fixed a startup crash.',
            'normal': 'Updated release notes.',
            'chrome-post-signoff': None,
        }, {r['item_key']: r['title'] for r in records})

        s = source('vivaldi-desktop')
        url = 'https://vivaldi.com/blog/release/'
        _, records = self.collect(s, {s['url']: self.index(s, [url]), url: self.release(url, html)})
        self.assertEqual(['normal'], [r['item_key'] for r in records])

    def test_chrome_release_archive_keeps_boundary_day_and_stops_before_it(self):
        s = source('chrome-releases')
        home = s['url']
        archive = home + 'search?updated-max='
        boundary_page = archive + '2026-10-28T00:00:00-07:00'
        unknown_page = archive + '2026-10-27T23:59:59'
        before_boundary = archive + '2026-10-27T23:59:59-07:00'
        release_urls = [home + '2026/10/' + path + '.html'
                        for path in ('latest', 'boundary-1', 'boundary-2')]
        requests = [(home, boundary_page), (boundary_page, unknown_page),
                    (unknown_page, before_boundary)]
        mapping = {}
        for (page, next_page), release_url in zip(requests, release_urls):
            mapping[page] = response(page, '''
                <a href="{release}">Release</a>
                <a id="Blog1_blog-pager-older-link" href="{next_page}">Older Posts</a>
            '''.format(release=release_url, next_page=next_page))
            mapping[release_url] = self.release(release_url, '''
                <div class="post-header">
                    <span class="publishdate" itemprop="datePublished">October 28, 2026</span>
                </div>
                <div class="post-body"><p>Release evidence.</p></div>
            ''')
        state, records = self.collect(s, mapping)
        self.assertEqual('complete', state['status'])
        self.assertTrue(state['pagination_exhausted'])
        self.assertEqual(3, state['pages'])
        self.assertEqual(3, len(records))
        self.assertCountEqual(list(mapping), self.transport.calls)

    def test_partial_failure_preserves_previous_and_minimum_record(self):
        s = source('opera-desktop')
        url = 'https://blogs.opera.com/desktop/2026/11/test/'
        mapping = {s['url']: self.index(s, [url]), url: self.release(url)}
        _, before = self.collect(s, mapping)
        mapping[url] = RuntimeError('source unavailable')
        state, after = self.collect(s, mapping)
        self.assertEqual('partial', state['status'])
        self.assertTrue(all(r in after for r in before))
        self.assertEqual(1, state['unparsed'])
        self.assertIn(url, state['pending'])
        self.assertEqual(1, len([r for r in after if r['record_status'] == 'unparsed']))

    def test_changed_text_same_anchor_appends_snapshot(self):
        s = source('edge-stable')
        html = '<div class="content"><h2 id="a">Changes</h2><p id="fixed">Fixed crash.</p></div>'
        _, first = self.collect(s, {s['url']: response(s['url'], html)})
        _, second = self.collect(s, {s['url']: response(s['url'], html.replace('crash', 'freeze'))})
        self.assertEqual(first[0]['source_item_id'], second[0]['source_item_id'])
        self.assertEqual(first[0]['revisions'], second[0]['revisions'][:1])
        self.assertEqual(2, len(second[0]['revisions']))

    def test_safari_every_topic_every_item_including_unknown(self):
        s = source('safari-release-notes')
        base = 'https://developer.apple.com/tutorials/data/documentation/safari-release-notes'
        data = json.loads((FIXTURES / 'apple-release.json').read_text())
        mapping = {base + '.json': response(base + '.json', json.loads((FIXTURES / 'apple.json').read_text()))}
        for version in ('27', '26'):
            u = base + '/safari-' + version + '-release-notes.json'
            mapping[u] = response(u, data)
        legacy_url = base + '/safari-13_1-release_notes.json'
        mapping[legacy_url] = response(legacy_url, data)
        state, records = self.collect(s, mapping)
        self.assertEqual(12, len(records))
        self.assertEqual(3, state['unparsed'])
        self.assertEqual('partial', state['status'])
        self.assertEqual({'general', 'security', 'fix', 'unknown'}, {r['item_type'] for r in records})
        self.assertTrue(all(r['published_at'] == '2026-11-10' for r in records))

    def test_chromestatus_real_api_total_and_personal_metadata_excluded(self):
        s = source('chrome-platform-status')
        base = 'https://chromestatus.com/api/v0/features?num=100&start='
        row = {'id': 1, 'name': 'Feature', 'summary': 'Product fact', 'owner': 'private@example.org'}
        mapping = {base+'0': response(base+'0', {'total_count': 2, 'features': [row]}),
                   base+'1': response(base+'1', {'total_count': 2, 'features': [dict(row, id=2)]})}
        state, records = self.collect(s, mapping)
        self.assertEqual('complete', state['status'])
        self.assertEqual(2, len(records))
        self.assertNotIn('private@example.org', json.dumps(records))
        self.assertNotIn(s['url'], self.transport.calls)
        self.assertEqual(digest(mapping[base+'0'].body), next(r for r in records if r['item_key'] == '1')['evidence']['content_sha256'])

    def test_chromestatus_total_changed_repeated_ids_and_empty_page_partial(self):
        s = source('chrome-platform-status')
        base = 'https://chromestatus.com/api/v0/features?num=100&start='
        row = {'id': 1, 'name': 'Feature', 'summary': 'Product fact'}
        for rows, total in [([], 2), ([row], 2), ([dict(row, id=2)], 3)]:
            with self.subTest(rows=rows, total=total):
                mapping = {base+'0': response(base+'0', {'total_count': 2, 'features': [row]}),
                           base+'1': response(base+'1', {'total_count': total, 'features': rows})}
                state, _ = self.collect(s, mapping)
                self.assertEqual('partial', state['status'])

    def test_github_link_pagination_and_markdown_security(self):
        s = source('brave-releases')
        first = 'https://api.github.com/repos/brave/brave-browser/releases?per_page=100&page=1'
        second = first.replace('page=1', 'page=2')
        row = {'id': 1, 'html_url': s['url'] + '/tag/v1', 'tag_name': 'v1', 'published_at': '2026-11-10T00:00:00Z',
               'body': '## Security\n- Fixed CVE-2026-12345\n## General\n- Improved performance\n', 'author': {'login': 'private-name'}}
        state, records = self.collect(s, {first: response(first, [row], {'link':'<%s>; rel="next"' % second}), second: response(second, [])})
        self.assertEqual('complete', state['status'])
        self.assertEqual(2, len(records))
        self.assertNotIn('private-name', json.dumps(records))

    def test_whale_languages_kept_separate_api_total(self):
        s = source('whale-release-history')
        base = 'https://notice.naver.com/api/v1/services/whalehomepage/notices/'
        rows = [{'id': 1, 'regDate': '2026-11-10T00:00:00', 'modDate': 'v1'}, {'id': 2, 'regDate': '2026-11-10T00:00:00', 'modDate': 'v1'}]
        page = base + '?sectionId=199&page=1&pageSize=20'
        mapping = {page: response(page, {'item': rows, 'pageInfo': {'pageNum': 1, 'totalSize':2, 'totalPageSize':1}})}
        for row, text in zip(rows, ['Fixed crash', '충돌 수정']):
            mapping[base+str(row['id'])] = response(base+str(row['id']), {'item': {'content': '<p id="fix">'+text+'</p>'}})
        state, records = self.collect(s, mapping)
        self.assertEqual('complete', state['status'])
        self.assertEqual(2, len(records))
        self.assertEqual(2, len({r['source_item_id'] for r in records}))

    def test_caps_loop_empty_index_spa_and_unknown_body_are_partial(self):
        s = source('vivaldi-desktop')
        url = 'https://vivaldi.com/blog/example/'
        cases = [
            {s['url']: self.index(s, [url], s['url']), url: self.release(url)},
            {s['url']: response(s['url'], '<div id="app"></div>')},
            {s['url']: self.index(s, [url]), url: response(url, '<main><p>Not a recognized source body</p></main>')},
        ]
        for mapping in cases:
            with self.subTest(mapping=list(mapping)):
                state, _ = self.collect(s, mapping)
                self.assertEqual('partial', state['status'])
        s['discovery']['max_documents'] = 1
        state, _ = self.collect(s, {s['url']: self.index(s, [url,'https://vivaldi.com/blog/other/']), url:self.release(url)})
        self.assertEqual('partial', state['status'])
        self.assertTrue(state['pending'])

    def test_page_cap_and_partial_http_response(self):
        s = source('vivaldi-desktop');s['discovery']['max_pages'] = 1
        url = 'https://vivaldi.com/blog/release/'
        state, _ = self.collect(s, {s['url']: self.index(s, [url], s['url']+'page/2/'), url:self.release(url)})
        self.assertFalse(state['pagination_exhausted'])
        self.assertEqual('partial', state['status'])
        s = source('edge-stable')
        state, _ = self.collect(s, {s['url']: response(s['url'], 'truncated', status=206)})
        self.assertEqual('partial', state['status'])

    def test_capped_mutable_api_resume_refreshes_whole_epoch_and_finishes(self):
        s = source('chrome-platform-status');s['discovery']['max_documents'] = 1
        url = 'https://chromestatus.com/api/v0/features?num=100&start=0'
        mapping = {url: response(url, {'total_count': 2, 'features': [{'id':1,'name':'A'}, {'id':2,'name':'B'}]})}
        state, records = self.collect(s, mapping)
        self.assertEqual('partial', state['status'])
        self.assertEqual(1, len(records))
        fresh = Transport(mapping)
        resumed = BrowserCollector(self.root, self.private, fresh, resume=True).collect(s, CUTOFF, '2026-10-28')
        self.assertEqual('complete', resumed['status'])
        self.assertEqual(2, resumed['stored_records'])
        self.assertEqual([url], fresh.calls)

    def test_iso_and_publisher_dates_preserve_day_and_upper_bound(self):
        self.assertEqual('2026-01-01', date_value('2026-01-01T00:00:00+09:00'))
        self.assertEqual('2026-01-01', date_value('01 Jan 2026'))
        self.assertEqual('2026-11-04', date_value('Nov 4, 2026'))
        self.assertIsNone(date_value('2026-01-011'))
        s = source('vivaldi-desktop')
        urls = ['https://vivaldi.com/blog/' + v + '/' for v in ('old', 'new', 'future')]
        mapping = {s['url']: self.index(s, urls)}
        for url, day in zip(urls, ('2025-12-31', '2026-11-01', '2026-11-20')):
            mapping[url] = response(url, '<meta property="article:published_time" content="' + day + 'T12:00:00Z"><div class="entry-content"><p>Product change.</p></div>')
        state, rows = self.collect(s, mapping)
        self.assertEqual('complete', state['status'])
        self.assertEqual(1, len(rows))
        self.assertEqual(1, state['temporal_coverage']['in_period'])
        self.assertEqual([urls[0], urls[2]], state['excluded_by_date'])

    def test_html_publication_timestamps_survive_index_and_document_filters(self):
        s = source('vivaldi-desktop')
        urls = ['https://vivaldi.com/blog/' + name + '/'
                for name in ('before', 'start', 'indexed-start', 'cutoff', 'after', 'day', 'naive')]
        before, start, indexed_start, cutoff, after, day, naive = urls
        start_time = '2025-12-31T15:00:00Z'
        cutoff_time = '2026-11-16T12:53:40Z'
        index_dates = {indexed_start: start_time, cutoff: '2026-11-16'}
        index = ''.join('<article><h2><a href="%s">Release</a></h2>%s</article>' % (
            url, '<time datetime="%s"></time>' % index_dates[url] if url in index_dates else '') for url in urls)

        def article(url, metadata, heading=''):
            return response(url, metadata + '<div class="entry-content">' + heading + '<p>Product change.</p></div>')

        state, rows = self.collect(s, {
            s['url']: response(s['url'], index),
            before: article(before, '<meta property="article:published_time" content="2025-12-31T14:59:59Z">'),
            start: article(start, '<meta property="article:published_time" content="' + start_time + '">',
                           '<h2>Dec 31, 2025</h2>'),
            indexed_start: article(indexed_start, ''),
            cutoff: article(cutoff, '<time datetime="2026-11-16T21:53:40+09:00">Nov 16, 2026</time>'),
            after: article(after, '<meta property="article:published_time" content="2026-11-16T12:53:41Z">'),
            day: article(day, '<meta property="article:published_time" content="2026-11-16">'),
            naive: article(naive, '<meta property="article:published_time" content="2026-11-16T12:53:41">'),
        }, cutoff=cutoff_time, since='2026-01-01')
        self.assertEqual('complete', state['status'])
        self.assertEqual([before, after], state['excluded_by_date'])
        scopes = {r['evidence']['url']: r['temporal_scope'] for r in rows}
        self.assertEqual({start, indexed_start, cutoff, day, naive}, set(scopes))
        for url, value, precision in [(start, start_time, 'timestamp'),
                                      (indexed_start, start_time, 'timestamp'),
                                      (cutoff, '2026-11-16T21:53:40+09:00', 'timestamp'),
                                      (day, '2026-11-16', 'day')]:
            self.assertEqual(('in_period', value, precision),
                             tuple(scopes[url][key] for key in ('status', 'evidence_date', 'precision')))
        self.assertEqual('unknown', scopes[naive]['status'])

    def test_nested_docc_code_lists_and_inline_html(self):
        rows = docc_items({'primaryContentSections': [{'kind': 'content', 'content': [
            {'type': 'unorderedList', 'items': [{'content': [{'type': 'paragraph', 'inlineContent': [
                {'type': 'text', 'text': 'Fixed'}, {'type': 'codeVoice', 'code': ['first', 'second']}]}]}]}]}]})
        self.assertEqual('Fixed first second', rows[0]['text'])
        self.assertTrue(rows[0]['parsed'])
        body = Tree('<div><span>Updated <u>underlined</u> text.</span><custom>Unknown content</custom></div>').root
        rows = blocks(body)
        self.assertTrue(any(r['parsed'] and 'underlined' in r['text'] for r in rows))
        self.assertTrue(any(not r['parsed'] for r in rows))

    def test_forum_body_inside_form_omits_replies_and_inactive_next(self):
        s = source('whale-notices')
        url = 'https://forum.whale.naver.com/topic/123/'
        index = '<a href="' + url + '">Release</a><li class="ipsPagination_inactive"><a rel="next" href="' + s['url'] + '">Next</a></li>'
        html = '<form><div data-role="commentContent"><p>Official change.</p></div><div data-role="commentContent"><p>Private reply.</p></div></form>'
        state, rows = self.collect(s, {s['url']: response(s['url'], index), url: response(url, html)})
        self.assertEqual('complete', state['status'])
        self.assertEqual(['Official change.'], [r['title'] for r in rows])

    def test_reviewed_signoff_requires_document_and_line_hash(self):
        s = source('chrome-releases')
        url = s['url'] + '2026/11/test.html'
        html = '<div class="post-body"><div class="post-content"><script type="text/template"><p>Product change.</p><p>Example Person</p><p>Google Chrome</p><span itemprop="author"></span></script></div></div>'
        mapping = {s['url']: self.index(s, [url]), url: response(url, html)}
        review = {digest(html.encode()): [digest(b'Example Person')]}
        collector = BrowserCollector(self.root, self.private, Transport(mapping), reviewed_attributions=review)
        state = collector.collect(s, CUTOFF, '2026-01-01')
        self.assertEqual('complete', state['status'])
        self.assertNotIn('Example Person', collector.destination.read_text())
        mapping[url] = response(url, html.replace('Example Person', 'Fixed crash'))
        state = BrowserCollector(self.root, self.private, Transport(mapping), reviewed_attributions=review).collect(s, CUTOFF, '2026-01-01')
        self.assertEqual('partial', state['status'])
        self.assertEqual(1, state['unparsed'])

    def test_cache_handoff_reparses_and_rejects_corruption(self):
        s = source('edge-stable')
        self.collect(s, {s['url']: response(s['url'], '<div class="content"><p>Product change.</p></div>')})
        target = self.private.parent / 'new-cache'
        provenance = seed_cache(self.private, target, CUTOFF)
        self.assertTrue(provenance['blobs'])
        self.assertFalse((target / (s['source_id'] + '.json')).exists())
        progress = json.loads((target / (s['source_id'] + '-progress.json')).read_text())
        self.assertEqual([], progress['documents'])
        next((self.private / 'cache').iterdir()).write_bytes(b'changed')
        bad = self.private.parent / 'bad-cache'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            seed_cache(self.private, bad, CUTOFF)
        self.assertFalse(bad.exists())

    def test_explicit_security_attribution_is_not_published(self):
        self.assertNotIn('Example Person', minimal('CVE-2026-12345: Example Person'))
        self.assertNotIn('Example Person', minimal('Fixed crash. Reported by Example Person on 2026-11-01'))

    def test_google_custom_feed_total_and_product_body(self):
        s = source('chrome-blog')
        api = 'https://blog.google/api/v2/latest/?tags=chrome&site_id=2&paginate=50'
        article = 'https://blog.google/products-and-platforms/products/chrome/new/'
        mapping = {
            s['url']: response(s['url'], '<uni-latest-news-feed tag-slugs=\'[{"slug":"chrome"}]\' site-id="2"></uni-latest-news-feed>'),
            api: response(api, {'meta': {'total_count': 3}, 'next_page': None, 'results': [
                {'page_id': 1, 'url': '/products-and-platforms/products/chrome/old/', 'published': '2025-12-31T14:59:59Z'},
                {'page_id': 2, 'url': article, 'published': '2025-12-31T15:00:00Z'},
                {'page_id': 3, 'url': '/products-and-platforms/products/chrome/future/', 'published': '2026-11-16T12:53:41Z'}]}),
            article: response(article, '<section class="uni-article-hero"><p>Personal author.</p></section><section class="article-container"><uni-article-paragraph><p>New browser feature.</p></uni-article-paragraph></section>')}
        state, rows = self.collect(s, mapping, cutoff='2026-11-16T12:53:40Z', since='2026-01-01')
        self.assertEqual('complete', state['status'])
        self.assertEqual(3, state['api_total'])
        self.assertEqual('2026-11-16', state['latest_publication_date'])
        self.assertEqual(2, len(state['excluded_by_date']))
        self.assertEqual('chrome', state['index_evidence']['tag'])
        self.assertEqual(['New browser feature.'], [r['title'] for r in rows])
        self.assertEqual(('in_period', 'timestamp', '2025-12-31T15:00:00Z'),
                         tuple(rows[0]['temporal_scope'][key] for key in ('status', 'precision', 'evidence_date')))

    def test_google_resume_refreshes_same_total_changed_membership(self):
        s = source('chrome-blog')
        api = 'https://blog.google/api/v2/latest/?tags=chrome&site_id=2&paginate=50'
        page2 = 'https://blog.google/api/v2/latest?cursor=2'
        index = '<uni-latest-news-feed tag-slugs=\'[{"slug":"chrome"}]\' site-id="2"></uni-latest-news-feed>'
        def page(ident, following):
            return {'meta': {'total_count': 2}, 'next_page': following,
                    'results': [{'page_id': ident, 'url': '/products/chrome/' + str(ident) + '/',
                                 'published': '2026-11-01T12:00:00Z'}]}
        def article(ident):
            return 'https://blog.google/products/chrome/' + str(ident) + '/'
        state, _ = self.collect(s, {
            s['url']: response(s['url'], index), api: response(api, page(1, page2)),
            article(1): response(article(1), '<section class="article-container"><p>Old product fact.</p></section>'),
            page2: RuntimeError('Interrupted second page')})
        self.assertEqual('partial', state['status'])
        # Same count, different membership. A cached first page would silently
        # produce IDs 1+3 instead of the available current enumeration 2+3.
        fresh_pages = {s['url']: response(s['url'], index), api: response(api, page(2, page2)),
                       page2: response(page2, page(3, None))}
        transport = Transport(dict(fresh_pages, **{
            article(i): response(article(i), '<section class="article-container"><p>Current fact %s.</p></section>' % i)
            for i in (2, 3)}))
        collector = BrowserCollector(self.root, self.private, transport, resume=True)
        resumed = collector.collect(s, CUTOFF, '2026-10-28')
        self.assertEqual('complete', resumed['status'])
        self.assertEqual(2, resumed['api_total'])
        self.assertEqual({article(2), article(3)}, {collector.records[k]['evidence']['url'] for k in collector.seen})
        self.assertEqual([s['url'], api, article(2), page2, article(3)], transport.calls)
        # Another retry still refreshes enumeration, but reuses article bodies.
        cached_articles = Transport(fresh_pages)
        again = BrowserCollector(self.root, self.private, cached_articles, resume=True).collect(s, CUTOFF, '2026-10-28')
        self.assertEqual('complete', again['status'])
        self.assertEqual([s['url'], api, page2], cached_articles.calls)

    def test_nested_attribution_omitted_from_ancestors_and_section_labels(self):
        examples = [
            '<div><span>Browser update.</span><span itemprop="author">Example Person</span></div>',
            '<span>Browser update.<a rel="author noopener">Example Person</a></span>',
            '<p>Browser update.<span itemprop="author"><b>Example Person</b></span> Fixed crash.</p>',
            '<blockquote>Browser update.<dl><dt>Reporter</dt><dd><span>Example Person</span></dd><dt>Impact</dt><dd>High</dd></dl></blockquote>',
            '<div><h2>Changes <span itemprop="author">Example Person</span></h2><p>Browser update.</p></div>',
        ]
        for html in examples:
            with self.subTest(html=html):
                rows = blocks(Tree(html).root)
                self.assertNotIn('Example Person', json.dumps(rows))
                self.assertTrue(any('Browser update.' in r['text'] for r in rows))
                self.assertTrue(all(r['parsed'] for r in rows))
        s = source('edge-stable')
        state, records = self.collect(s, {s['url']: response(s['url'], '<div class="content">' + ''.join(examples) + '</div>')})
        self.assertEqual('complete', state['status'])
        self.assertNotIn('Example Person', json.dumps(records))
        self.assertTrue(any('Fixed crash.' in (r['summary'] or '') for r in records))
        self.assertTrue(any('Impact High' in (r['summary'] or '') for r in records))

    def test_explicit_image_credits_preserve_units_and_product_text(self):
        examples = [
            '<p><em>Main photo by</em> <a href="https://unsplash.com/@example">Example Person</a></p>',
            '<p><em>Main photo by <a href="https://unsplash.com/@example"><b>Example Person</b></a></em>.</p>',
            '<p>New tabs. Photo by <a href="https://example.com/credit">Example Person</a>. Fixed crash.</p>',
            '<p>New tabs. <span class="image-credit"><b>Example Person</b></span> Fixed crash.</p>',
            '<div><h2>Photo credit: <a href="https://example.com/credit">Example Person</a></h2><p>New tabs.</p></div>',
            '<div><h2>Changes <span class="photo-credit">Example Person</span></h2><p>New tabs.</p></div>',
            '<blockquote><p>Main photo by <a href="https://example.com/credit">Example Person</a></p><p>New tabs.</p></blockquote>',
        ]
        for html in examples:
            with self.subTest(html=html):
                rows = blocks(Tree(html).root)
                self.assertEqual(1, len(rows))
                self.assertNotIn('Example Person', json.dumps(rows))
                self.assertIn('[image attribution omitted]', json.dumps(rows))
                self.assertTrue(all(r['parsed'] for r in rows))
                if 'New tabs.' in html:
                    self.assertIn('New tabs.', rows[0]['text'])
                if 'Fixed crash.' in html:
                    self.assertIn('Fixed crash.', rows[0]['text'])
        product = '<p>Supply an image by <a href="https://example.com/help">uploading a file</a>.</p><p>Photo by date sorting is available.</p>'
        self.assertEqual(['Supply an image by uploading a file .', 'Photo by date sorting is available.'],
                         [r['text'] for r in blocks(Tree(product).root)])
        s = source('edge-stable')
        state, records = self.collect(s, {s['url']: response(s['url'], '<div class="content">' + ''.join(examples) + product + '</div>')})
        self.assertEqual('complete', state['status'])
        self.assertNotIn('Example Person', json.dumps(records))
        self.assertTrue(any('Fixed crash.' in (r['summary'] or '') for r in records))
        self.assertTrue(any('uploading a file' in (r['summary'] or '') for r in records))

    def test_explicit_standalone_byline_preserves_surrounding_product_text(self):
        html = '<blockquote><p>New tabs.</p><p>Written by: Dr. Example M. Person</p><p>Fixed crash.</p></blockquote>'
        rows = blocks(Tree(html).root)
        self.assertEqual(1, len(rows))
        self.assertEqual('New tabs. [author attribution omitted] Fixed crash.', rows[0]['text'])
        self.assertNotIn('Example', json.dumps(rows))
        for label in ('Authored by:', 'Posted by:'):
            self.assertEqual('[author attribution omitted]', blocks(Tree('<p>' + label + ' Example Person</p>').root)[0]['text'])
        for role in ('Manager', 'Director'):
            html = '<p><strong>By Example Person, Product ' + role + '</strong></p><p>New tabs.</p>'
            self.assertEqual(['[author attribution omitted]', 'New tabs.'], [r['text'] for r in blocks(Tree(html).root)])
        product = '<p>Code written by extensions now runs in isolation.</p><p>New tabs. Written by extensions, scripts use isolated worlds.</p>'
        self.assertNotIn('attribution omitted', json.dumps(blocks(Tree(product).root)))
        product = '<p><strong>By default, Product Manager integration is disabled.</strong></p>'
        self.assertNotIn('attribution omitted', json.dumps(blocks(Tree(product).root)))

    def test_html_page_and_document_caps_resume_without_repeating_requests(self):
        s = source('vivaldi-desktop');s['discovery']['max_pages'] = 1;s['discovery']['max_documents'] = 1
        one, two = 'https://vivaldi.com/blog/one/', 'https://vivaldi.com/blog/two/'
        page2 = s['url']+'page/2/'
        state, _ = self.collect(s, {s['url']:self.index(s,[one],page2), one:self.release(one)})
        self.assertEqual('partial', state['status'])
        transport = Transport({page2:self.index(s,[two]), two:self.release(two)})
        resumed = BrowserCollector(self.root, self.private, transport, resume=True).collect(s, CUTOFF, '2026-10-28')
        self.assertEqual('complete', resumed['status'])
        self.assertEqual(8, resumed['stored_records'])
        self.assertEqual({page2,two}, set(transport.calls))

    def test_unknown_api_rows_and_image_only_items_remain_unparsed(self):
        s = source('chrome-platform-status')
        url = 'https://chromestatus.com/api/v0/features?num=100&start=0'
        state, records = self.collect(s,{url:response(url,{'total_count':3,'features':[{}, None, {'id':1,'name':'Feature'}]})})
        self.assertEqual(3,len(records));self.assertEqual(2,state['unparsed'])
        self.assertEqual('partial',state['status'])
        s = source('edge-stable')
        state, records = self.collect(s,{s['url']:response(s['url'],'<div class="content"><ul><li id="one"><img src="x"></li><li id="two">Fixed crash</li></ul></div>')})
        self.assertEqual(2,len(records));self.assertEqual(1,state['unparsed'])

    def test_redirect_uses_canonical_release_url_and_version(self):
        s = source('firefox-beta')
        url = 'https://www.firefox.com/en-US/firefox/161.0beta/releasenotes/'
        html = '<html><head><title>Firefox 161.0beta release notes</title></head><body><section class="c-release-notes"><li id="note-1">Fixed crash.</li></section></body></html>'
        state, records = self.collect(s, {s['url']:response(url,html)})
        self.assertEqual('complete',state['status'])
        self.assertEqual(url,records[0]['evidence']['url'])
        self.assertEqual('161.0beta',records[0]['version'])

    def test_truncated_http_200_html_cannot_claim_complete(self):
        s = source('edge-stable')
        html = '<html><div class="content"><p id="one">Fixed crash.</p></div>'
        state, records = self.collect(s,{s['url']:response(s['url'],html)})
        self.assertEqual('partial',state['status'])
        self.assertEqual(1,len(records))

    def test_minimal_evidence_preserves_css_rules_and_omits_contacts(self):
        value = minimal('Fixed @container queries and @font-face. Thanks @alice, contact a@example.com')
        self.assertIn('@container',value);self.assertIn('@font-face',value)
        self.assertNotIn('@alice',value);self.assertNotIn('a@example.com',value)

    def test_repeated_cve_keeps_every_html_source_location_and_stable_corrections(self):
        s = source('edge-stable')
        html = '<div class="content"><h2 id="security">Security</h2><ul><li>Fixed renderer CVE-2026-12345</li><li>Fixed network CVE-2026-12345</li></ul></div>'
        state, records = self.collect(s,{s['url']:response(s['url'],html)})
        self.assertEqual('complete',state['status'])
        self.assertEqual(2,state['discovered']);self.assertEqual(2,state['processed'])
        self.assertEqual(0,state['duplicate']);self.assertEqual(2,len(records))
        self.assertEqual(2,len({r['item_key'] for r in records}))
        corrected = html.replace('network CVE','network stack CVE')
        _, new = self.collect(s,{s['url']:response(s['url'],corrected)})
        self.assertEqual({r['source_item_id'] for r in records},{r['source_item_id'] for r in new})
        self.assertEqual(2,len(new))

    def test_reused_docc_and_markdown_issue_ids_have_distinct_locations(self):
        paragraphs = [{'content':[{'type':'paragraph','inlineContent':[{'text':text}]}]} for text in
                      ['Fixed renderer. (12345678)','Fixed network. (12345678)']]
        data = {'primaryContentSections':[{'kind':'content','content':[
            {'type':'heading','anchor':'Security'}, {'type':'unorderedList','items':paragraphs},
            {'type':'heading','anchor':'General'}, {'type':'unorderedList','items':[paragraphs[0]]}]}]}
        units = docc_items(data)
        self.assertEqual(3,len(units));self.assertEqual(3,len({u['key'] for u in units}))
        units = markdown_items('## Security\n- Fixed renderer (#1234)\n- Fixed network (#1234)')
        self.assertEqual(2,len(units));self.assertEqual(2,len({u['key'] for u in units}))
        s = source('safari-release-notes')
        base = 'https://developer.apple.com/tutorials/data/documentation/safari-release-notes'
        index = {'topicSections':[{'identifiers':['doc://release']}], 'references':{'doc://release':{'url':'/documentation/safari-release-notes/safari-27-release-notes'}}}
        state, records = self.collect(s,{base+'.json':response(base+'.json',index),base+'/safari-27-release-notes.json':response(base+'/safari-27-release-notes.json',data)})
        self.assertEqual('complete',state['status']);self.assertEqual(3,len(records))
        self.assertEqual(3,state['processed']);self.assertEqual(0,state['duplicate'])

    def test_distinct_observations_with_colliding_record_ids_fail_explicitly(self):
        s = source('edge-stable')
        html = '<div class="content"><p id="first">First change</p><p id="second">Second change</p></div>'
        with patch('pipeline.collectors.browser.collector.identity', side_effect=lambda prefix, fields:prefix+'-forced-collision'):
            state, records = self.collect(s,{s['url']:response(s['url'],html)})
        self.assertEqual('partial',state['status'])
        self.assertTrue(any('identity collision' in e['reason'] for e in state['errors']))
        self.assertEqual('First change',records[0]['summary'])

    def test_truncated_index_preserves_known_items_and_cannot_exhaust_pagination(self):
        s = source('vivaldi-desktop');url='https://vivaldi.com/blog/release/'
        index = '<html><body><h2><a href="'+url+'">Release</a></h2>'
        state, records = self.collect(s,{s['url']:response(s['url'],index),url:self.release(url)})
        self.assertEqual('partial',state['status'])
        self.assertFalse(state['pagination_exhausted'])
        self.assertEqual(5,len(records));self.assertEqual(1,state['unparsed'])
        self.assertEqual(4,state['processed']);self.assertIn(s['url'],state['pending'])
        self.assertTrue(any(r['item_key']=='index-truncated' for r in records))

    def test_private_state_cannot_be_in_public_repository(self):
        with self.assertRaises(ValueError):
            BrowserCollector(self.root, self.root / '.private')

    def test_all_html_document_registry_adapters_have_recognized_boundary(self):
        wrappers = {'edge': '<div class="content">%s</div>', 'chrome': '<div class="article-content">%s</div>',
                    'firefox': '<section class="c-release-notes">%s</section>'}
        for s in REGISTRY['sources']:
            if s['parser'] != 'html_document' or s['source_id'] == 'chrome-enterprise':
                continue
            with self.subTest(source=s['source_id']):
                html = wrappers[s['browser']] % '<h2>Fixed</h2><ul><li id="note-1">Fixed crash</li><li id="note-2">Security update</li></ul>'
                state, records = self.collect(s, {s['url']:response(s['url'], html)})
                self.assertEqual('complete', state['status'])
                self.assertEqual(2, len(records))


if __name__ == '__main__':
    unittest.main()
