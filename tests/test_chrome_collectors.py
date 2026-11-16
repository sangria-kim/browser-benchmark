import copy
import json
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

from pipeline.collectors.chrome import collect, Gitiles, LocalCheckout
from pipeline.collectors.chrome.parser import parse, auxiliary_definitions
from pipeline.collectors.chrome.providers import canonical, digest
from schemas.validate import load_config, validate_record

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/chrome'
NOW = '2026-11-16T00:00:00Z'


class MemoryProvider:
    def __init__(self, files, revision='a' * 40, complete=True):
        self.files, self.revision, self.complete = files, revision, complete
        self.pinned = False
        self.reads = []

    def pin(self):
        self.pinned = True
        return self.revision

    def enumerate(self, state_dir, max_trees=None):
        assert self.pinned
        return {'paths': sorted(self.files), 'complete': self.complete, 'unsupported': []}

    def read(self, path):
        assert self.pinned
        self.reads.append(path)
        return self.files[path].encode()


def fixture_files(unresolved=True):
    definitions = (FIXTURES / 'definitions.cc').read_text()
    registry = (FIXTURES / 'about_flags.cc').read_text()
    if not unresolved:
        definitions = '\n'.join(line for line in definitions.splitlines() if 'kUnresolved' not in line and 'kUnknown' not in line)
        registry = '\n'.join(line for line in registry.splitlines() if 'unknown-demo' not in line)
    return {'chrome/browser/about_flags.cc': registry, 'components/demo/features.cc': definitions,
            'ios/chrome/browser/flags/about_flags.mm': 'const FeatureEntry kFeatureEntries[] = {{"ios-demo", "IOS", "IOS", kOsIos, FEATURE_VALUE_TYPE(features::kHidden)}};',
            'chrome/browser/flag_descriptions.h': '// definitions inline in fixture',
            'chrome/browser/flag-metadata.json': json.dumps([{'name': 'old-demo', 'expiry_milestone': 120, 'owners': ['private@example.org']}, {'name': 'never-demo', 'expiry_milestone': -1}, {'name': 'demo', 'expiry_milestone': 141}]),
            'chrome/browser/flag-never-expire-list.json': '["never-demo"]',
            'chrome/browser/expired_flags_list.h': 'const ExpiredFlag kExpired[] = {{"old-demo", 120}};',
            'ios/chrome/browser/flags/ios_chrome_flag_descriptions.h': '// no definitions',
            'tools/flags/generate_expired_list.py': '# expiry generator',
            'tools/flags/generate_unexpire_flags.py': '# unexpiry generator',
            'chrome/VERSION': 'MAJOR=140\nMINOR=0\nBUILD=0\nPATCH=0\n'}


class ParserTests(unittest.TestCase):
    def test_features_switches_aliases_and_declarations(self):
        candidates, declarations, errors = parse('components/demo/features.cc', (FIXTURES / 'definitions.cc').read_text())
        self.assertFalse(errors)
        self.assertEqual(len(declarations), 3)
        self.assertEqual(len(candidates), 13)
        hidden = next(c for c in candidates if c.symbol == 'kHidden')
        self.assertEqual(hidden.qualified_symbol, 'features::kHidden')
        self.assertTrue(hidden.parsed)
        self.assertEqual(sum(not c.parsed for c in candidates), 2)
        self.assertEqual(next(c for c in candidates if c.symbol == 'kDirect').default, 'base::FEATURE_ENABLED_BY_DEFAULT')
        self.assertTrue(any(c.alias == 'kHidden' for c in candidates))
        self.assertEqual(next(c for c in candidates if c.symbol == 'kWide').value, 'wide-switch')

    def test_branch_conditions_are_not_flattened(self):
        cs, _, _ = parse('features.cc', (FIXTURES / 'definitions.cc').read_text())
        linked = [c for c in cs if c.symbol == 'kLinked']
        self.assertEqual(len(linked), 2)
        self.assertEqual(linked[0].conditions, ['BUILDFLAG(IS_WIN)'])
        self.assertIn('!((BUILDFLAG(IS_WIN))) && (BUILDFLAG(IS_MAC))', linked[1].conditions)
        self.assertIn('IS_MAC', next(c for c in cs if c.symbol == 'kOtherPlatform').conditions[0])

    def test_registry_options_and_unknown_preserved(self):
        cs, _, _ = parse('chrome/browser/about_flags.cc', (FIXTURES / 'about_flags.cc').read_text())
        self.assertEqual(len(cs), 5)
        self.assertEqual(sum(c.parsed for c in cs), 4)
        self.assertIn('features::kHidden', cs[0].refs)
        self.assertEqual(cs[0].platforms, ['kOsWin'])
        auxiliary = auxiliary_definitions((FIXTURES / 'about_flags.cc').read_text())
        self.assertIn('kChoices', auxiliary)
        self.assertIn('switches::kSecond', auxiliary['kChoices'][0]['refs'])

    def test_std_array_and_conditional_row_do_not_truncate_table(self):
        text = 'constexpr auto kFeatureEntries = std::to_array<flags_ui::FeatureEntry>({\n{"conditional", "C", "C", kOsAll,\n#if WIN\nFEATURE_VALUE_TYPE(features::kA)},\n#else\nFEATURE_VALUE_TYPE(features::kB)},\n#endif\n{"after", "A", "A", kOsAll, FEATURE_VALUE_TYPE(features::kAfter)},\n});'
        cs, _, _ = parse('ios/chrome/browser/flags/about_flags.mm', text)
        self.assertTrue(any(c.symbol == 'after' and c.parsed for c in cs))
        self.assertTrue(any(not c.parsed for c in cs))

    def test_unsupported_switch_pointer_is_preserved(self):
        cs, _, _ = parse('demo_switches.cc', 'const char* kPointer = "pointer";')
        self.assertEqual(len(cs), 1)
        self.assertFalse(cs[0].parsed)

    def test_comment_and_string_macros_do_not_become_candidates(self):
        text = '// BASE_FEATURE(kFalse, "False", base::FEATURE_ENABLED_BY_DEFAULT);\nconst char kText[]="BASE_FEATURE(kFalse)";'
        self.assertEqual(parse('features.cc', text)[0], [])

    def test_unknown_registration_row_is_retained(self):
        cs, _, _ = parse('chrome/browser/about_flags.cc', 'FeatureEntry kFeatureEntries[] = {\nGENERATED_FLAGS\n};')
        self.assertEqual(len(cs), 1)
        self.assertFalse(cs[0].parsed)

    def test_macro_template_is_not_feature(self):
        cs, ds, _ = parse('features.h', '#define MY_FEATURE(name) BASE_FEATURE(name, "X", base::FEATURE_ENABLED_BY_DEFAULT)\n')
        self.assertFalse(cs)
        self.assertEqual(len(ds), 1)


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / 'config/chrome-source-scope.yml')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

    def run_collect(self, files=None, directory=None, **kwargs):
        return collect(self.config, MemoryProvider(files or fixture_files()), directory or self.temp.name, observed_at=NOW, **kwargs)

    def test_records_valid_reconcile_and_no_owner(self):
        result = self.run_collect()
        for row in result['source_items']:
            validate_record('source_item', row)
        for row in result['experiments']:
            validate_record('experiment', row)
            self.assertEqual(row['verification_status'], 'source_only')
            self.assertIsNone(row['product_channel'])
            self.assertEqual(row['installed_availability'], 'unknown')
        coverage = result['coverage']
        self.assertEqual(coverage['candidate_count'], coverage['parsed_count'] + coverage['unparsed_count'])
        self.assertEqual(coverage['unparsed_count'], 3)
        self.assertFalse(coverage['complete'])
        self.assertNotIn('private@example.org', json.dumps(result['source_items']))
        self.assertNotIn('owners', json.dumps(result['source_items']))

    def test_expiry_never_expiry_and_options(self):
        result = self.run_collect()
        exps = {e['flag_id']: e for e in result['experiments'] if e['flag_id']}
        self.assertEqual(exps['old-demo']['lifecycle'], 'expired')
        self.assertEqual(exps['demo']['lifecycle'], 'active')
        self.assertTrue(exps['never-demo']['never_expire'])
        facts = {f['definition']['symbol']: f for f in result['facts']}
        self.assertEqual(len(facts['switch-demo']['semantic']['references']), 2)
        self.assertEqual(len(facts['demo']['semantic']['options']), 2)
        self.assertIn('"fast"', str(facts['demo']['semantic']['options']))
        self.assertEqual(exps['demo']['title'], 'Demo name')

    def test_unlinked_features_and_alias_relationship(self):
        result = self.run_collect(fixture_files(False))
        self.assertTrue(result['coverage']['complete'], result['coverage'])
        by_symbol = {e['symbol']: e for e in result['experiments']}
        self.assertEqual(by_symbol['features::kModern']['ui_exposure'], 'not_registered')
        self.assertEqual(by_symbol['features::kHidden']['ui_exposure'], 'registered')
        alias = by_symbol['features::kAlias']
        self.assertEqual(alias['relationships'], [{'kind': 'alias_of', 'target_id': by_symbol['features::kHidden']['experiment_id']}])

    def test_rerun_preserves_ids_and_history(self):
        one = self.run_collect()
        two = collect(self.config, MemoryProvider(fixture_files()), self.temp.name, observed_at='2026-11-17T00:00:00Z')
        self.assertEqual(one['source_items'], two['source_items'])
        self.assertTrue((Path(self.temp.name) / 'handoff.json').exists())

    def test_private_state_must_be_external(self):
        with self.assertRaises(ValueError):
            self.run_collect(directory=ROOT / 'data/state')

    def test_missing_required_path_prevents_complete(self):
        files = fixture_files(False)
        del files['chrome/browser/expired_flags_list.h']
        result = self.run_collect(files)
        self.assertFalse(result['coverage']['complete'])
        self.assertIn('chrome/browser/expired_flags_list.h', result['coverage']['missing_required_paths'])

    def test_invalid_metadata_and_empty_registry_prevent_complete(self):
        files = fixture_files(False)
        files['chrome/browser/flag-metadata.json'] = '{invalid'
        files['chrome/browser/about_flags.cc'] = '// empty'
        result = self.run_collect(files)
        self.assertFalse(result['coverage']['complete'])
        reasons = [v['reason'] for v in result['coverage']['errors']]
        self.assertIn('invalid_expiry_metadata', reasons)
        self.assertIn('missing_flag_table', reasons)

    def test_failed_auxiliary_inputs_keep_last_good_materializations(self):
        files = fixture_files(False)
        registry = files['chrome/browser/about_flags.cc']
        title_block = re.search(r'namespace flag_descriptions \{.*?\n\}', registry, re.S)[0]
        files['chrome/browser/flag_descriptions.h'] = title_block
        registry = registry.replace(title_block, '')
        option_blocks = re.findall(r'const FeatureEntry::(?:Choice|FeatureParam|FeatureVariation).*?;\n', registry, re.S)
        files['components/demo/options.h'] = '\n'.join(option_blocks)
        for block in option_blocks:
            registry = registry.replace(block, '')
        files['chrome/browser/about_flags.cc'] = registry
        one = self.run_collect(files)
        self.assertTrue(one['coverage']['complete'], one['coverage'])
        failures = [
            ['chrome/browser/flag-metadata.json', 'chrome/browser/expired_flags_list.h'],
            ['chrome/browser/flag_descriptions.h'],
            ['components/demo/options.h'],
            ['components/demo/features.cc'],
        ]
        for failed_paths in failures:
            with self.subTest(failed_paths=failed_paths), tempfile.TemporaryDirectory() as temp:
                provider = MemoryProvider(files, 'b' * 40)
                original_read = provider.read
                def read(path):
                    if path in failed_paths:
                        raise OSError('fixture unavailable')
                    return original_read(path)
                provider.read = read
                partial = collect(self.config, provider, temp, previous=one, observed_at=NOW)
                self.assertFalse(partial['coverage']['complete'])
                self.assertEqual(partial['source_items'], one['source_items'])
                self.assertEqual(partial['experiments'], one['experiments'])
                self.assertEqual(partial['facts'], one['facts'])
                recovered = collect(self.config, MemoryProvider(files, 'b' * 40), temp, observed_at=NOW)
                self.assertTrue(recovered['coverage']['complete'])
                old_demo = next(e for e in recovered['experiments'] if e['flag_id'] == 'old-demo')
                self.assertEqual((old_demo['lifecycle'], old_demo['expiry_milestone']), ('expired', 120))
                self.assertTrue(all(len(r['revisions']) == 2 for r in recovered['source_items']))

    def test_missing_auxiliary_paths_and_new_candidates_remain_unknown(self):
        files = fixture_files(False)
        one = self.run_collect(files)
        del files['chrome/browser/flag-metadata.json']
        del files['chrome/browser/expired_flags_list.h']
        files['new/features.cc'] = 'BASE_FEATURE(kNew, "New", base::FEATURE_ENABLED_BY_DEFAULT);'
        with tempfile.TemporaryDirectory() as temp:
            partial = collect(self.config, MemoryProvider(files, 'b' * 40), temp, previous=one, observed_at=NOW)
        old_demo = next(e for e in partial['experiments'] if e['flag_id'] == 'old-demo')
        self.assertEqual((old_demo['lifecycle'], old_demo['expiry_milestone']), ('expired', 120))
        new = next(e for e in partial['experiments'] if e['symbol'] == 'kNew')
        self.assertEqual(new['lifecycle'], 'unknown')
        self.assertIsNone(new['default_state'])
        new_source = next(r for r in partial['source_items'] if r['source_item_id'] in new['source_item_ids'])
        self.assertEqual(new_source['record_status'], 'unparsed')
        self.assertEqual(new_source['lifecycle'], 'unknown')

    def test_incomplete_tree_preserves_known_options_despite_existing_unresolved_ref(self):
        files = fixture_files(False)
        registry = files['chrome/browser/about_flags.cc']
        blocks = re.findall(r'const FeatureEntry::(?:Choice|FeatureParam|FeatureVariation).*?;\n', registry, re.S)
        files['components/demo/options.h'] = '\n'.join(blocks)
        for block in blocks:
            registry = registry.replace(block, '')
        registry = registry.replace('FEATURE_WITH_PARAMS_VALUE_TYPE(features::kHidden,',
                                    'FEATURE_WITH_PARAMS_VALUE_TYPE(features::kMissing,')
        files['chrome/browser/about_flags.cc'] = registry
        one = self.run_collect(files)
        prior_fact = next(f for f in one['facts'] if f['definition']['symbol'] == 'demo')
        self.assertEqual(len(prior_fact['semantic']['options']), 2)
        self.assertIn('features::kMissing', prior_fact['semantic']['unresolved_references'])
        self.assertIn('components/demo/options.h', {d['path'] for d in prior_fact['dependencies']})
        for legacy in (False, True):
            with self.subTest(legacy_bundle=legacy), tempfile.TemporaryDirectory() as temp:
                previous = copy.deepcopy(one)
                if legacy:
                    for fact in previous['facts']:
                        fact.pop('dependencies', None)
                limited = dict(files)
                del limited['components/demo/options.h']
                partial = collect(self.config, MemoryProvider(limited, 'b' * 40, False), temp,
                                  previous=previous, observed_at=NOW)
                self.assertFalse(partial['coverage']['errors'])
                self.assertFalse(partial['coverage']['complete'])
                old_fact = next(f for f in previous['facts'] if f['definition']['symbol'] == 'demo')
                new_fact = next(f for f in partial['facts'] if f['definition']['symbol'] == 'demo')
                self.assertEqual(new_fact, old_fact)
                eid, sid = old_fact['experiment_id'], old_fact['source_item_id']
                self.assertEqual(next(e for e in partial['experiments'] if e['experiment_id'] == eid),
                                 next(e for e in previous['experiments'] if e['experiment_id'] == eid))
                self.assertEqual(next(r for r in partial['source_items'] if r['source_item_id'] == sid),
                                 next(r for r in previous['source_items'] if r['source_item_id'] == sid))

    def test_partial_tree_does_not_downgrade_known_ui_exposure(self):
        files = fixture_files(False)
        one = self.run_collect(files)
        with tempfile.TemporaryDirectory() as temp:
            partial = collect(self.config, MemoryProvider(files, 'b' * 40, False), temp, previous=one, observed_at=NOW)
        self.assertFalse(partial['coverage']['complete'])
        self.assertEqual({e['experiment_id']:e['ui_exposure'] for e in one['experiments']},
                         {e['experiment_id']:e['ui_exposure'] for e in partial['experiments']})

    def test_budget_and_resume(self):
        first_provider = MemoryProvider(fixture_files(False))
        first = collect(self.config, first_provider, self.temp.name, max_files=2, observed_at=NOW)
        self.assertFalse(first['coverage']['complete'])
        second_provider = MemoryProvider(fixture_files(False))
        second = collect(self.config, second_provider, self.temp.name, observed_at=NOW)
        self.assertTrue(second['coverage']['complete'])
        self.assertTrue(set(first_provider.reads).isdisjoint(second_provider.reads))

    def test_sample_is_always_partial(self):
        result = self.run_collect(fixture_files(False), sample_paths=list(fixture_files(False)))
        self.assertFalse(result['coverage']['complete'])
        self.assertFalse(result['coverage']['tree_complete'])

    def test_revision_and_line_changes_do_not_change_semantics(self):
        one = self.run_collect(fixture_files(False))
        files = {p: ('\n' + s if p.endswith(('.cc', '.h', '.mm')) else s) for p, s in fixture_files(False).items()}
        with tempfile.TemporaryDirectory() as temp:
            two = collect(self.config, MemoryProvider(files, 'b' * 40), temp, previous=one, observed_at=NOW)
        self.assertEqual({r['source_item_id']: r['semantic_sha256'] for r in one['facts']}, {r['source_item_id']: r['semantic_sha256'] for r in two['facts']})
        self.assertTrue(all(len(r['revisions']) == 2 for r in two['source_items']))

    def test_deletion_requires_two_complete_trees(self):
        one = self.run_collect(fixture_files(False))
        files = fixture_files(False)
        files['components/demo/features.cc'] = files['components/demo/features.cc'].replace('BASE_FEATURE(kModern, base::FEATURE_ENABLED_BY_DEFAULT);', '')
        with tempfile.TemporaryDirectory() as temp:
            two = collect(self.config, MemoryProvider(files, 'b' * 40), temp, previous=one, observed_at=NOW)
        self.assertEqual(len(two['removed_candidates']), 1)
        self.assertTrue(any(e['symbol'] == 'features::kModern' and e['lifecycle'] == 'removed' for e in two['experiments']))
        with tempfile.TemporaryDirectory() as temp:
            partial = collect(self.config, MemoryProvider(files, 'b' * 40, False), temp, previous=one, observed_at=NOW)
        self.assertFalse(partial['removed_candidates'])
        self.assertEqual(len(partial['source_items']), len(one['source_items']))

    def test_metadata_only_flags_are_preserved_without_owners_or_ui_claim(self):
        files = fixture_files(False)
        files['chrome/browser/flag-metadata.json'] = '[{"name":"metadata-only","expiry_milestone":135,"owners":["private@example.org"]}]'
        result = self.run_collect(files)
        experiment = next(e for e in result['experiments'] if e['flag_id'] == 'metadata-only')
        self.assertEqual(experiment['ui_exposure'], 'not_registered')
        self.assertEqual(experiment['lifecycle'], 'expired')
        row = next(r for r in result['source_items'] if r['source_item_id'] in experiment['source_item_ids'])
        self.assertEqual(row['record_status'], 'parsed')
        self.assertNotIn('owners', json.dumps(row))
        self.assertNotIn('private@example.org', json.dumps(row))

    def test_expiry_boundary_is_inclusive(self):
        files = fixture_files(False)
        files['chrome/browser/flag-metadata.json'] = '[{"name":"demo","expiry_milestone":140}]'
        result = self.run_collect(files)
        self.assertEqual(next(e for e in result['experiments'] if e['flag_id'] == 'demo')['lifecycle'], 'expired')

    def test_long_definition_tail_changes_semantic_hash(self):
        files = fixture_files(False)
        files['demo_switches.cc'] = 'const char kLong[] = "' + 'x' * 1300 + 'a";'
        one = self.run_collect(files)
        files['demo_switches.cc'] = files['demo_switches.cc'].replace('a";', 'b";')
        with tempfile.TemporaryDirectory() as temp:
            two = collect(self.config, MemoryProvider(files, 'b' * 40), temp, previous=one, observed_at=NOW)
        before = next(f for f in one['facts'] if f['definition']['symbol'] == 'kLong')
        after = next(f for f in two['facts'] if f['definition']['symbol'] == 'kLong')
        self.assertNotEqual(before['semantic_sha256'], after['semantic_sha256'])
        self.assertEqual(before['source_item_id'], after['source_item_id'])
        self.assertTrue(all(len(r['evidence']['excerpt']) <= 1200 for r in two['source_items']))

    def test_unsupported_entry_blocks_only_source_scope(self):
        provider = MemoryProvider(fixture_files(False))
        provider.enumerate = lambda state_dir, max_trees=None: {'paths': sorted(provider.files), 'complete': True, 'unsupported': ['docs/link.txt']}
        result = collect(self.config, provider, self.temp.name, observed_at=NOW)
        self.assertTrue(result['coverage']['complete'])
        provider.enumerate = lambda state_dir, max_trees=None: {'paths': sorted(provider.files), 'complete': True, 'unsupported': ['demo/features.cc']}
        result = collect(self.config, provider, self.temp.name, observed_at=NOW)
        self.assertFalse(result['coverage']['complete'])

    def test_wrong_auxiliary_namespace_is_unresolved(self):
        files = fixture_files(False)
        files['chrome/browser/about_flags.cc'] = files['chrome/browser/about_flags.cc'].replace('kOsAll, MULTI_VALUE_TYPE(kChoices)', 'kOsAll, MULTI_VALUE_TYPE(other::kChoices)')
        result = self.run_collect(files)
        fact = next(f for f in result['facts'] if f['definition']['symbol'] == 'switch-demo')
        self.assertEqual(fact['semantic']['options'], [])
        self.assertIn('other::kChoices', fact['semantic']['unresolved_references'])

    def test_namespace_collision_not_merged(self):
        files = fixture_files(False)
        files['other/features.cc'] = 'namespace other { BASE_FEATURE(kHidden, "OtherHidden", base::FEATURE_ENABLED_BY_DEFAULT); }'
        result = self.run_collect(files)
        by_symbol = {e['symbol']: e for e in result['experiments']}
        self.assertNotEqual(by_symbol['other::kHidden']['experiment_id'], by_symbol['features::kHidden']['experiment_id'])
        self.assertEqual(by_symbol['other::kHidden']['ui_exposure'], 'not_registered')


class ProviderTests(unittest.TestCase):
    def test_gitiles_pin_resume_and_no_ref_reads(self):
        revision, requests = 'c' * 40, []
        def transport(url):
            requests.append(url)
            if '/refs/heads/main?' in url:
                data = {'commit': revision}
            elif url.endswith('/' + revision + '/?format=JSON'):
                data = {'entries': [{'name': 'src', 'type': 'tree'}]}
            else:
                data = {'entries': [{'name': 'features.cc', 'type': 'blob'}]}
            return (")]}'\n" + json.dumps(data)).encode()
        provider = Gitiles('https://chromium.googlesource.com/chromium/src', transport=transport)
        self.assertEqual(provider.pin(), revision)
        with tempfile.TemporaryDirectory() as temp:
            one = provider.enumerate(temp, max_trees=1)
            self.assertFalse(one['complete'])
            two = provider.enumerate(temp)
            self.assertTrue(two['complete'])
            self.assertEqual(two['paths'], ['src/features.cc'])
        self.assertTrue(all(revision in u for u in requests[1:]))
        self.assertEqual(len(requests), 3)

    def test_gitiles_rejects_truncated_tree(self):
        def transport(url):
            return json.dumps({'commit': 'd' * 40} if 'main?' in url else {'entries': [], 'next': 'page2'}).encode()
        provider = Gitiles('https://example.com/repo', transport=transport)
        provider.pin()
        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            provider.enumerate(temp)

    def test_clean_local_tree_uses_tracked_commit(self):
        with tempfile.TemporaryDirectory() as temp:
            def git(*args):
                return subprocess.check_output(['git', '-C', temp] + list(args), stderr=subprocess.PIPE).decode().strip()
            git('init', '-q')
            Path(temp, 'features.cc').write_text('BASE_FEATURE(kLocal, base::FEATURE_ENABLED_BY_DEFAULT);')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
            provider = LocalCheckout(temp)
            self.assertEqual(provider.pin(), git('rev-parse', 'HEAD'))
            self.assertEqual(provider.enumerate(temp)['paths'], ['features.cc'])
            self.assertIn(b'kLocal', provider.read('features.cc'))
            Path(temp, 'untracked.cc').write_text('dirty')
            with self.assertRaises(ValueError):
                provider.pin()


if __name__ == '__main__':
    unittest.main()
