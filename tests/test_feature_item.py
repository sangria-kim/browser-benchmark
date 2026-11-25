"""The feature-item contract against the real registry, graph validator and dashboard builder."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline import browser_status, collect
from pipeline.collectors.browser import Response
from pipeline.feature_item import FACT_FIELDS, item_delta, missing_facts
from pipeline.normalize import validate_graph
from pipeline.official_reference import accepts_url, normalize_url
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
