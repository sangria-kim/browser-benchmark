import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from pipeline.collectors.browser import BrowserCollector, Response
from pipeline.collectors.browser.collector import digest, minimal, docc_items, markdown_items
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

    def collect(self, s, mapping, cutoff=CUTOFF):
        self.transport = Transport(mapping)
        state = BrowserCollector(self.root, self.private, self.transport).collect(s, cutoff, '2026-10-28')
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
        first = 'https://api.github.com/repos/brave/brave-browser/releases?per_page=10&page=1'
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

    def test_capped_api_resume_uses_pinned_cache_and_finishes(self):
        s = source('chrome-platform-status');s['discovery']['max_documents'] = 1
        url = 'https://chromestatus.com/api/v0/features?num=100&start=0'
        mapping = {url: response(url, {'total_count': 2, 'features': [{'id':1,'name':'A'}, {'id':2,'name':'B'}]})}
        state, records = self.collect(s, mapping)
        self.assertEqual('partial', state['status'])
        self.assertEqual(1, len(records))
        no_network = Transport({})
        resumed = BrowserCollector(self.root, self.private, no_network, resume=True).collect(s, CUTOFF, '2026-10-28')
        self.assertEqual('complete', resumed['status'])
        self.assertEqual(2, resumed['stored_records'])
        self.assertEqual([], no_network.calls)

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
            if s['parser'] != 'html_document':
                continue
            with self.subTest(source=s['source_id']):
                html = wrappers[s['browser']] % '<h2>Fixed</h2><ul><li id="note-1">Fixed crash</li><li id="note-2">Security update</li></ul>'
                state, records = self.collect(s, {s['url']:response(s['url'], html)})
                self.assertEqual('complete', state['status'])
                self.assertEqual(2, len(records))


if __name__ == '__main__':
    unittest.main()
