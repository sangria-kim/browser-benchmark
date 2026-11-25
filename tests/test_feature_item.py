"""The feature-item contract against the real registry, graph validator and dashboard builder."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pipeline import browser_status, collect
from pipeline.collectors.browser import Response
from pipeline.feature_item import FACT_FIELDS, item_delta, missing_facts
from pipeline.normalize import validate_graph
from pipeline.official_reference import accepts_url, normalize_url, reference_row
from schemas.validate import validate_record
from scripts import build_dashboard

ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-11-25T00:00:00Z'
LATER = '2026-11-26T00:00:00Z'
URL = 'https://www.firefox.com/en-US/firefox/ios/160.0/releasenotes/'
REQUEST = dict(browser='firefox', url=URL, canonical_key='tab-share', title='Share a tab group')


class FeatureItemTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'repo'
        shutil.copytree(ROOT / 'config', self.root / 'config')
        self.sources = json.loads((self.root / 'config/sources.yml').read_text())['sources']
        self.registry = {s['source_id']: s for s in self.sources}

    def write(self, path, obj):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(obj))

    def apply(self, request=REQUEST, *, candidate=None, at=NOW):
        delta = item_delta(self.root, request, self.sources, observed_at=at, candidate=candidate)
        graph = validate_graph(self.root, delta.changes)
        for path, rows in delta.changes.items():
            self.write(path, rows)
        return delta.effect, graph

    def candidate(self, suffix=''):
        body = (ROOT / 'tests/fixtures/browser/releases.html').read_text().replace('entry-content', 'c-release-notes')
        long = 'Tab grouping added. ' * 18 + 'Send this group to another device.' + suffix
        private = self.root.parent / 'scan'
        collect.collect_sources(self.root, private, source_ids=['firefox-beta'], mode='manual', cutoff=NOW,
                                transport=lambda url: Response(url, body.replace('Tab grouping added.', long).encode()))
        rows = json.loads((private / 'work/candidates/firefox-beta.json').read_text())
        row = next(r for r in rows if r['item_key'] == 'feature-a')
        request = dict(browser='firefox', canonical_key='test-groups', title='Send a tab group',
                       source_item_id=row['source_item_id'], revision_id=row['revisions'][-1]['revision_id'])
        return row, request

    def test_reference_replay_has_one_stable_observation_and_no_source_claims(self):
        first, graph = self.apply()
        self.assertTrue(first['changed'])
        repeated, again = self.apply(dict(REQUEST, url=URL.replace('.com', '.COM:443')), at=LATER)
        self.assertFalse(repeated['changed'])
        self.assertEqual(graph, again)
        self.assertEqual({}, item_delta(self.root, REQUEST, self.sources, observed_at=LATER).changes)
        feature, = graph['feature']
        row, = graph['source_item']
        self.assertEqual(FACT_FIELDS, missing_facts(feature, {row['source_item_id']: row}))
        self.assertEqual(('reference', 'reference', None, None, None, ['unknown'], ''),
                         (row['origin'], row['record_status'], row['published_at'], row['summary'],
                          row['version'], row['platform'], row['evidence']['excerpt']))
        self.assertEqual(NOW, row['observed_at'])
        for bad in (dict(row, origin='backfill'), dict(row, version='160')):
            with self.assertRaises(ValueError):
                validate_record('source_item', bad)

    def test_legacy_and_url_only_features_in_real_dashboard(self):
        row, choice = self.candidate()
        self.apply(choice, candidate=row)
        old_rows = json.loads((self.root / browser_status.CATALOG).read_text())
        del old_rows[0]['feature_facts']
        self.write(browser_status.CATALOG, old_rows)
        effect, graph = self.apply()
        self.assertIn(old_rows[0], graph['feature'])
        self.write('dashboard/card-summaries.json', {})
        output = self.root.parent / 'site'
        legacy = dict(events=[], flags=[], source={}, built_at=NOW, updated_at=NOW, catalog={})
        with patch.object(build_dashboard, 'ROOT', self.root):
            build_dashboard.build_research(output, legacy, '')
        actual = build_dashboard.read_resource(output / 'indexes/feature.json.gz')
        self.assertEqual(2, len(actual))
        summary = next(r for r in actual if r['id'] == effect['feature_id'])
        self.assertEqual(([], []), (summary['versions'], summary['platform']))
        detail = build_dashboard.read_resource(output / summary['detail'])
        citation, = detail['evidence']
        self.assertEqual((URL, ''), (citation['url'], citation['excerpt']))

    def test_other_product_other_page_and_missing_slots(self):
        first, _ = self.apply(dict(REQUEST, facts={'version': '160', 'platform': []}))
        other, _ = self.apply(dict(REQUEST, title='Customize the toolbar', canonical_key='toolbar'))
        self.assertNotEqual(first['feature_id'], other['feature_id'])
        self.assertEqual(first['item'], other['item'])
        second_url = URL.replace('160.0', '161.0')
        follow, graph = self.apply(dict(REQUEST, url=second_url,
                                        facts=dict(version='161', platform=['iOS'], rollout_status='announced')))
        self.assertFalse(follow['changed'])
        self.assertNotEqual(first['item'], follow['item'])
        by_id = {f['feature_id']: f for f in graph['feature']}
        original = by_id[first['feature_id']]
        self.assertEqual({}, by_id[other['feature_id']]['feature_facts'])
        slots = original['feature_facts']
        self.assertEqual(('160', ['iOS'], 'announced'), tuple(slots[k]['value'] for k in ('version','platform','rollout_status')))
        self.assertEqual((first['item'], follow['item']), (slots['version']['source_item_id'], slots['platform']['source_item_id']))
        self.assertEqual(('channel',), missing_facts(original, {}))
        self.assertEqual([], graph['feature_event'])
        _, same = self.apply(dict(REQUEST, facts={'version': None, 'platform': ['unknown']}))
        self.assertEqual(graph['feature'], same['feature'])
        broken = copy.deepcopy(original)
        broken['feature_facts']['platform']['revision_id'] = first['revision']
        with self.assertRaisesRegex(ValueError, 'pinned item'):
            validate_graph(self.root, {browser_status.CATALOG: [broken]})

    def test_candidate_uses_raw_hash_and_optional_long_or_empty_quote(self):
        row, choice = self.candidate()
        revision = row['revisions'][-1]
        self.assertEqual(220, len(row['evidence']['excerpt']))
        first, graph = self.apply(dict(choice, evidence_quote=''), candidate=row)
        self.assertEqual(row['evidence'], graph['source_item'][0]['evidence'])
        self.assertEqual(revision, graph['source_item'][0]['revisions'][-1])
        other_choice = dict(choice, canonical_key='cross-device', evidence_quote='Send this group to another device.')
        _, graph = self.apply(other_choice, candidate=row)
        self.assertEqual(1, len(graph['source_item']))
        self.assertEqual(2, len(graph['feature']))
        self.assertEqual(revision['revision_id'], first['revision'])
        with self.assertRaisesRegex(ValueError, 'confirmed excerpt'):
            self.apply(dict(choice, evidence_quote='Tab grouping added.'), candidate=row)
        for modified in (dict(choice, url=URL), dict(choice, revision_id='rev-unobserved'),
                         dict(other_choice, evidence_quote='wrong passage')):
            with self.assertRaises(ValueError):
                self.apply(modified, candidate=row)
        with self.assertRaises(ValueError):
            self.apply(dict(choice, url=URL))

    def test_explicit_product_expansion_and_existing_evidence_only(self):
        one, _ = self.apply()
        again, _ = self.apply(dict(REQUEST, change_kind='product_change'))
        self.assertFalse(again['changed'])
        newer, graph = self.apply(dict(REQUEST, url=URL.replace('160.0', '161.0'), change_kind='product_change'))
        self.assertTrue(newer['changed'])
        self.assertEqual(one['feature_id'], newer['feature_id'])
        self.assertEqual(1, len(graph['feature']))
        with self.assertRaises(ValueError):
            self.apply(dict(REQUEST, canonical_key='new', change_kind='evidence_only'))

    def test_legacy_pinned_version_and_no_page_default(self):
        row, choice = self.candidate(' This feature requires version 160.')
        row['version'] = row['revisions'][-1]['version'] = '160'
        row['platform'] = row['revisions'][-1]['platform'] = ['Windows']
        _, graph = self.apply(dict(choice, evidence_quote='This feature requires version 160.'), candidate=row)
        feature = graph['feature'][0]
        feature.pop('feature_facts')
        self.write(browser_status.CATALOG, [feature])
        missing = missing_facts(feature, {row['source_item_id']: row})
        self.assertNotIn('version', missing)
        self.assertIn('platform', missing)
        _, graph = self.apply(dict(REQUEST, canonical_key=choice['canonical_key'],
                                   facts={'version': '999', 'platform': ['Android']}))
        self.assertNotIn('version', graph['feature'][0]['feature_facts'])
        self.assertEqual(['Android'], graph['feature'][0]['feature_facts']['platform']['value'])

    def test_identity_alias_and_conflicts(self):
        effect, graph = self.apply()
        feature = graph['feature'][0]
        feature['aliases'] = ['old-tab-share']
        self.write(browser_status.CATALOG, [feature])
        self.write('data/aliases/corrections.json', [
            dict(alias_id='alias-1', subject_kind='feature', old_id='retired-id', target_id=effect['feature_id'],
                 source_item_ids=[effect['item']], reason='Corrected identity', revision=1, supersedes=None)])
        for field, value in [('feature_id', 'retired-id'), ('canonical_key', 'old-tab-share'), ('feature_id', effect['feature_id'])]:
            request = dict(browser='firefox', url=URL)
            again, graph = self.apply(dict(request, **{field: value}))
            self.assertEqual(effect['feature_id'], again['feature_id'])
            self.assertFalse(again['changed'])
        for invalid in (dict(REQUEST, feature_id='unknown'), dict(REQUEST, feature_id='retired-id', canonical_key='unrelated')):
            with self.assertRaises(ValueError):
                self.apply(invalid)

    def test_known_fact_from_earlier_confirmed_revision_survives_later_gap(self):
        row, choice = self.candidate(' This feature requires version 160.')
        row['version'] = row['revisions'][-1]['version'] = '160'
        _, first = self.apply(dict(choice, evidence_quote='This feature requires version 160.'), candidate=row)
        next_row = copy.deepcopy(row)
        tail = copy.deepcopy(row['revisions'][-1])
        tail.update(revision_id='sr-later', version=None, title='Group tabs across windows')
        next_row.update(version=None, title=tail['title'])
        next_row['revisions'].append(tail)
        _, second = self.apply(dict(choice, revision_id='sr-later'), candidate=next_row, at=LATER)
        feature, = second['feature']
        self.assertNotIn('version', missing_facts(feature, {row['source_item_id']: next_row}))
        _, updated = self.apply(dict(REQUEST, canonical_key=choice['canonical_key'], facts=dict(version='999')))
        self.assertNotIn('version', updated['feature'][0]['feature_facts'])
        saved = next(r for r in updated['source_item'] if r['source_item_id'] == row['source_item_id'])
        self.assertEqual(first['source_item'][0]['revisions'], saved['revisions'][:1])

    def test_whale_topics_require_notice_observation_and_exclude_replies(self):
        source = self.registry['whale-notices']
        url = 'https://forum.whale.naver.com/topic/123/'
        request = dict(browser='whale', url=url, canonical_key='whale-tabs', title='Group tabs by project')
        for address in (url, url + '#comment-456'):
            with self.subTest(address=address), self.assertRaises(ValueError):
                self.apply(dict(request, url=address))
        private = self.root.parent / 'whale'
        pages = {source['url']: '<a href="' + url + '">Release</a>',
                 url: '<form><div data-role="commentContent"><p>Group tabs by project.</p></div></form>'}
        collect.collect_sources(self.root, private, source_ids=['whale-notices'], mode='manual', cutoff=NOW,
                                transport=lambda u: Response(u, pages[u].encode()))
        row, = json.loads((private / 'work/candidates/whale-notices.json').read_text())
        selected = dict(request, source_item_id=row['source_item_id'], revision_id=row['revisions'][-1]['revision_id'])
        self.apply(selected, candidate=row)
        _, replay = self.apply(request)
        self.assertEqual(1, len(replay['source_item']))
        self.apply(dict(request, canonical_key='another-whale-feature', title='Share the grouped tabs'))
        with self.assertRaises(ValueError):
            self.apply(dict(request, url=url + '#comment-456'))

    def test_first_selection_respects_versioned_official_note(self):
        path = ROOT / 'data/source-items/firefox/firefox-releases.json'
        row = next(r for r in json.loads(path.read_bytes()) if r['item_key'] == 'note-792196')
        self.assertEqual('157.0', row['version'])
        self.write(path.relative_to(ROOT), [row])
        choice = dict(browser='firefox', canonical_key='versioned-note', title=row['title'], facts=dict(version='999'),
                      source_item_id=row['source_item_id'], revision_id=row['revisions'][-1]['revision_id'])
        _, graph = self.apply(choice, candidate=row)
        self.assertNotIn('version', graph['feature'][0]['feature_facts'])
        self.assertNotIn('version', missing_facts(graph['feature'][0], {row['source_item_id']: row}))

    def test_cross_category_blog_requires_published_chrome_feed_membership(self):
        url = 'https://blog.google/products-and-platforms/platforms/android/switch-password-managers/'
        rows = json.loads((ROOT / 'data/source-items/chrome/chrome-blog.json').read_bytes())
        row = next(r for r in rows if r['evidence']['url'] == url)
        request = dict(browser='chrome', url=url, canonical_key='switch-passwords', title='Switch password managers')
        with self.assertRaises(ValueError):
            self.apply(request)
        self.write('data/source-items/chrome/chrome-blog.json', [row])
        self.apply(dict(request, source_item_id=row['source_item_id'], revision_id=row['revisions'][-1]['revision_id']),
                   candidate=row)
        repeat, graph = self.apply(request)
        self.assertFalse(repeat['changed'])
        self.assertEqual(1, len(graph['source_item']))

    def test_old_registered_citation_requires_same_row_in_authorizing_commit(self):
        registry_path = self.root / 'config/sources.yml'
        old_source = self.registry['edge-stable']
        req = dict(browser='edge', canonical_key='share-links', title='Share links', url=old_source['url'])
        _, original = self.apply(req)
        for args in [('init', '-q'), ('add', '.'), ('-c','user.name=Fixture','-c','user.email=fixture@example.test',
                                                     'commit','-qm','Accepted official citation')]:
            subprocess.run(['git', '-C', str(self.root), *args], check=True)
        registry = json.loads(registry_path.read_text())
        source = next(s for s in registry['sources'] if s['source_id'] == 'edge-stable')
        source['url'] += '-moved'
        self.write('config/sources.yml', registry)
        self.assertEqual(original['source_item'], validate_graph(self.root)['source_item'])
        altered = reference_row(old_source, old_source['url'], LATER)
        with self.assertRaises(ValueError):
            validate_graph(self.root, {'data/source-items/edge/edge-stable.json': [altered]})

    def test_graph_rejects_self_consistent_foreign_reference(self):
        source = self.registry['firefox-ios']
        rel = 'data/source-items/firefox/firefox-ios.json'
        for publisher, address in [(source, 'https://unrelated.example.com/another-product/'),
                                   (dict(source, browser='chrome'), URL)]:
            row = reference_row(publisher, address, NOW)
            validate_record('source_item', row)
            with self.subTest(address=address, browser=publisher['browser']), self.assertRaises(ValueError):
                validate_graph(self.root, {rel: [row]})

    def test_same_source_head_leaves_unselected_legacy_sibling_untouched(self):
        row, choice = self.candidate()
        self.apply(choice, candidate=row)
        _, graph = self.apply(dict(choice, canonical_key='sibling', title='Open shared groups'), candidate=row)
        for feature in graph['feature']:
            del feature['source_revision_ids']
            feature.pop('feature_facts')
        sibling = next(f for f in graph['feature'] if f['canonical_key'] == 'sibling')
        self.write(browser_status.CATALOG, graph['feature'])
        request = dict(browser='firefox', canonical_key=choice['canonical_key'], url=row['evidence']['url'],
                       facts=dict(platform=['iOS']), change_kind='product_change')
        effect, updated = self.apply(request)
        self.assertFalse(effect['changed'])
        self.assertIn(sibling, updated['feature'])
        self.assertEqual(graph['source_item'], updated['source_item'])
        updated_row = copy.deepcopy(row)
        tail = dict(row['revisions'][-1], revision_id='sr-new-product', version='161')
        updated_row['revisions'].append(tail)
        updated_row['version'] = '161'
        changed, latest = self.apply(dict(choice, revision_id='sr-new-product', change_kind='product_change'),
                                     candidate=updated_row, at=LATER)
        self.assertTrue(changed['changed'])
        owner = next(f for f in latest['feature'] if f['canonical_key'] == 'sibling')
        self.assertEqual([choice['revision_id']], owner['source_revision_ids'][row['source_item_id']])

    def test_url_replay_of_confirmed_long_item_quote(self):
        row, choice = self.candidate()
        quote = 'Send this group to another device.'
        self.assertNotIn(quote, row['evidence']['excerpt'])
        effect, graph = self.apply(dict(choice, evidence_quote=quote), candidate=row)
        request = dict(browser='firefox', url=row['evidence']['url'], feature_id=effect['feature_id'], evidence_quote=quote)
        again, replayed = self.apply(request, at=LATER)
        self.assertFalse(again['changed'])
        self.assertEqual(graph, replayed)
        with self.assertRaises(ValueError):
            self.apply(dict(request, evidence_quote='Tab grouping added.'))

    def test_publisher_url_boundaries_and_nonfeatures(self):
        valid = {'firefox-ios': URL, 'brave-releases': 'https://github.com/brave/brave-browser/releases/tag/v1.99.30',
                 'chrome-enterprise': 'https://release-notes-787862449254.us-central1.run.app/features?version=144&lang=en',
                 'edge-stable': self.registry['edge-stable']['url']+'#version-160',
                 'chrome-blog': 'https://blog.google/products-and-platforms/products/chrome/skills-in-chrome/'}
        for sid, url in valid.items():
            self.assertTrue(accepts_url(self.registry[sid], normalize_url(url)), sid)
        bad = [URL.replace('www.firefox.com', 'www.firefox.com.fake.com'), URL.replace('www.', 'x@www.'),
               URL.replace('.com/', '.com:8443/'), URL.replace('/ios/', '/ios/../android/'),
               URL.replace('/ios/', '/ios/%252e%252e/'), URL.replace('https:', 'http:')]
        for request in [dict(REQUEST, url=url) for url in bad] + [
                dict(REQUEST, browser='edge'), dict(REQUEST, source_id='firefox-security'),
                dict(REQUEST, title='Maintenance release'), dict(REQUEST, title='Version bump'),
                dict(REQUEST, disposition='excluded'), dict(REQUEST, browser='brave', url=valid['brave-releases'].replace('/brave/', '/someone/')),
                dict(REQUEST, browser='brave', url=valid['brave-releases'].replace('brave-browser', 'another-repo'))]:
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.apply(request)
        self.assertFalse((self.root / 'data').exists())
