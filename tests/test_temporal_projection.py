import copy
import json
from pathlib import Path
import tempfile
import unittest
import shutil

from pipeline.temporal import dated_scope, scope_semantics
from pipeline.collectors.chrome import collect
from pipeline.collectors.chrome.temporal import compare
from pipeline.collectors.chrome.parser import parse, semantic_expression, literal, auxiliary_definitions, references, conventional_include_guard
from pipeline.collectors.chrome.generated import blink_features, INPUT, GENERATOR, TEMPLATE
from pipeline.collectors.browser import BrowserCollector
from pipeline.normalize.corrections import parser_aliases
from pipeline.normalize.core import source_definition
from schemas.validate import load_config, validate_record
from test_chrome_collectors import MemoryProvider, fixture_files, ROOT
from test_browser_collectors import source, response

CUTOFF = '2026-11-16T12:53:40+00:00'
BOUNDARY = '2025-12-31T14:00:34Z'


class TemporalTests(unittest.TestCase):
    def test_initial_history_reconciliation_preserves_snapshots_and_later_changes(self):
        from pipeline.normalize.core import attach_accepted_chrome_history, normalize_chrome, merge_sources
        a, b = self.bundles('BASE_FEATURE(kSame, base::FEATURE_ENABLED_BY_DEFAULT);',
                            'BASE_FEATURE(kSame, base::FEATURE_DISABLED_BY_DEFAULT);')
        old, history = normalize_chrome(a, a['source_items'])
        projected = attach_accepted_chrome_history(self.project(a, b), a['source_items'])
        sources = merge_sources(a['source_items'], projected['source_items'])
        current, migrated = normalize_chrome(projected, sources, old, history)
        self.assertEqual(history, migrated)
        for source_item in a['source_items']:
            after = next(s for s in sources if s['source_item_id'] == source_item['source_item_id'])
            self.assertEqual(source_item['revisions'], after['revisions'][:len(source_item['revisions'])])
        files = fixture_files(False)
        files['components/temporal.cc'] = 'BASE_FEATURE(kSame, "NewName", base::FEATURE_DISABLED_BY_DEFAULT);'
        with tempfile.TemporaryDirectory() as tmp:
            c = collect(load_config(ROOT / 'config/chrome-source-scope.yml'), MemoryProvider(files, 'c' * 40), tmp,
                        observed_at='2026-11-16T01:00:00Z')
        later = attach_accepted_chrome_history(self.project(a, c), sources)
        _, changed = normalize_chrome(later, merge_sources(sources, later['source_items']), current, migrated)
        self.assertEqual(len(migrated) + 1, len(changed))
        self.assertTrue(all(event in changed for event in history))
        stale = copy.deepcopy(self.project(a, b))
        for item in stale['source_items']:
            item['observed_at'] = '2025-01-01T00:00:00Z'
        with self.assertRaises(ValueError):
            attach_accepted_chrome_history(stale, sources)

    def test_incremental_handoff_attaches_only_exact_accepted_suffix(self):
        from pipeline.normalize.core import attach_accepted_chrome_history, merge_sources
        a, b = self.bundles('BASE_FEATURE(kSame, base::FEATURE_ENABLED_BY_DEFAULT);',
                            'BASE_FEATURE(kSame, base::FEATURE_DISABLED_BY_DEFAULT);')
        projected = self.project(a, b)
        accepted = merge_sources(a['source_items'],
                                attach_accepted_chrome_history(projected, a['source_items'])['source_items'])
        files = fixture_files(False)
        files['components/temporal.cc'] = 'BASE_FEATURE(kSame, "NewName", base::FEATURE_DISABLED_BY_DEFAULT);'
        with tempfile.TemporaryDirectory() as tmp:
            c = collect(load_config(ROOT / 'config/chrome-source-scope.yml'), MemoryProvider(files, 'c' * 40), tmp,
                        previous=projected, observed_at='2026-11-16T01:00:00Z')
        incoming = self.project(a, c)
        result = attach_accepted_chrome_history(incoming, accepted)
        old = {i['source_item_id']: i for i in accepted}
        for row in result['source_items']:
            history = old[row['source_item_id']]['revisions']
            self.assertEqual(history, row['revisions'][:len(history)])
        self.assertEqual(result, attach_accepted_chrome_history(result, accepted))
        for mode in ('tampered', 'unrelated', 'stale', 'wrong_endpoint', 'altered_replay'):
            bad = copy.deepcopy(incoming)
            row = bad['source_items'][0]
            if mode == 'tampered':
                row['revisions'][0]['title'] = 'altered snapshot'
            elif mode == 'unrelated':
                row['revisions'][0]['revision_id'] = 'unrelated'
            elif mode == 'wrong_endpoint':
                row['evidence']['source_revision'] = 'd' * 40
            elif mode == 'altered_replay':
                row['revisions'] = row['revisions'][:1]
                row['revisions'][0]['title'] = 'altered accepted snapshot'
            else:
                row['observed_at'] = '2025-01-01T00:00:00Z'
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                attach_accepted_chrome_history(bad, accepted)

    def test_carried_identity_is_context_not_current_endpoint_change(self):
        from pipeline.normalize.core import attach_accepted_chrome_history, merge_sources
        a, b = self.bundles('', 'BASE_FEATURE(kCarried, base::FEATURE_ENABLED_BY_DEFAULT);')
        projected = self.project(a, b)
        accepted = merge_sources(a['source_items'],
                                attach_accepted_chrome_history(projected, a['source_items'])['source_items'])
        with tempfile.TemporaryDirectory() as tmp:
            c = collect(load_config(ROOT / 'config/chrome-source-scope.yml'),
                        MemoryProvider(fixture_files(False), 'c' * 40, False), tmp,
                        previous=projected, observed_at='2026-11-16T01:00:00Z')
        result = attach_accepted_chrome_history(self.project(a, c), accepted)
        carried = next(e for e in result['experiments'] if e['symbol'] == 'kCarried')
        self.assertEqual('context', carried['temporal_scope']['status'])
        self.assertEqual('unknown', carried['temporal_scope']['change'])
        old = {s['source_item_id']: s for s in accepted}
        source = next(s for s in result['source_items'] if s['source_item_id'] in carried['source_item_ids'])
        self.assertEqual(old[source['source_item_id']]['revisions'], source['revisions'])
        self.assertEqual('context', source['temporal_scope']['status'])

    def test_carried_fact_cannot_affect_current_family_or_satisfy_dependency(self):
        text = 'BASE_FEATURE(kSame, base::FEATURE_ENABLED_BY_DEFAULT);'
        a, b = self.bundles(text, text)
        fact = next(f for f in b['facts'] if f['semantic']['symbol'] == 'kSame')
        source = next(s for s in b['source_items'] if s['source_item_id'] == fact['source_item_id'])
        experiment = next(e for e in b['experiments'] if e['experiment_id'] == fact['experiment_id'])
        carried_fact, carried_source, carried_experiment = map(copy.deepcopy, (fact, source, experiment))
        carried_fact['source_item_id'] = carried_source['source_item_id'] = 'carried-source'
        carried_fact['experiment_id'] = carried_experiment['experiment_id'] = 'carried-experiment'
        carried_experiment['source_item_ids'] = ['carried-source']
        carried_source['evidence']['source_revision'] = a['revision']
        carried_fact['semantic']['default'] = 'base::FEATURE_DISABLED_BY_DEFAULT'
        b['facts'].append(carried_fact)
        b['source_items'].append(carried_source)
        b['experiments'].append(carried_experiment)
        result = self.project(a, b)
        scopes = {e['experiment_id']: e['temporal_scope'] for e in result['experiments']}
        self.assertEqual('unchanged', scopes[fact['experiment_id']]['status'])
        self.assertEqual('context', scopes['carried-experiment']['status'])
        fact['semantic']['references'].append({'kind': 'depends_on', 'target_id': 'carried-experiment'})
        result = self.project(a, b)
        scope = next(e['temporal_scope'] for e in result['experiments'] if e['experiment_id'] == fact['experiment_id'])
        self.assertEqual('unknown', scope['status'])

    def test_enum_initializers_and_masked_comment_references(self):
        values = auxiliary_definitions('enum class Mode { kFirst = 7, kNext, kReset = 20, kLast };')
        self.assertEqual(['7', '(7) + 1', '20', '(20) + 1'],
                         [values[k][0]['expression'] for k in ('kFirst', 'kNext', 'kReset', 'kLast')])
        self.assertTrue(all(len(v) == 1 and v[0]['namespace'] == 'Mode' for v in values.values()))
        self.assertEqual(['features::kDemo'], references('/*' + ' ' * 200000 + '*/ features\n :: kDemo'))
        array = auxiliary_definitions('const FeatureEntry::FeatureParam kParams[]{ {"x", "true"} };')
        self.assertEqual(1, len(array['kParams']))
        self.assertEqual([], array['kParams'][0]['refs'])

    def test_equality_uses_do_not_create_auxiliary_initializers(self):
        text = ('namespace metrics {\nconstexpr base::FeatureState kDefault = base::FEATURE_ENABLED_BY_DEFAULT;\n'
                'bool Check() { return kDefault == base::FEATURE_ENABLED_BY_DEFAULT; }\n'
                'bool Other() { return metrics::kDefault == base::FEATURE_DISABLED_BY_DEFAULT; }\n'
                'BASE_FEATURE(kDemo, kDefault);\n}')
        definitions = auxiliary_definitions(text)
        self.assertEqual(1, len(definitions['kDefault']))
        self.assertEqual('base::FEATURE_ENABLED_BY_DEFAULT', definitions['kDefault'][0]['expression'])
        a, b = self.bundles(text, text.replace('kDefault = base::FEATURE_ENABLED_BY_DEFAULT',
                                              'kDefault = base::FEATURE_DISABLED_BY_DEFAULT'))
        feature = next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'metrics::kDemo')
        self.assertEqual('changed', feature['temporal_scope']['change'])
        a, b = self.bundles(text, text.replace('return kDefault ==', 'return kDefault !='))
        feature = next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'metrics::kDemo')
        self.assertEqual('unchanged', feature['temporal_scope']['status'])

    def test_http_rate_limit_respects_retry_after(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        from pipeline.collectors.browser.transport import HTTPTransport
        error = HTTPError('https://example.invalid', 429, 'Slow down', {'Retry-After': '121'}, None)
        with patch('pipeline.collectors.browser.transport.urlopen', side_effect=[error, ValueError('stop')]), \
             patch('pipeline.collectors.browser.transport.time.sleep') as sleep:
            with self.assertRaisesRegex(ValueError, 'stop'):
                HTTPTransport()('https://example.invalid')
        self.assertEqual([60, 60, 1], [c.args[0] for c in sleep.call_args_list])

    def test_opera_typo_needs_exact_official_heading_and_article(self):
        from urllib.error import HTTPError
        broken = 'https://blogs.opera.com/desktop/2026/03/opera-130-0-5823-0-developer-update/'
        replacement = 'https://blogs.opera.com/desktop/2026/03/opera-130-0-5846-0-developer-update/'
        evidence = 'https://blogs.opera.com/desktop/changelog-for-130/'
        pages = {evidence: response(evidence, '<h4>130.0.5846.0 – 2026-03-23 <a href="' + broken + '">blog post</a></h4>'),
                 replacement: response(replacement, '<title>Opera 130.0.5846.0</title><meta property="article:published_time" content="2026-03-23T10:00:00Z">')}
        with tempfile.TemporaryDirectory() as tmp:
            collector = BrowserCollector(Path(tmp) / 'repo', Path(tmp) / 'private')
            collector.source, collector.state, collector.get = source('opera-desktop'), {}, pages.__getitem__
            error = HTTPError(broken, 404, 'Missing', {}, None)
            self.assertEqual(replacement, collector.verified_document_replacement(broken, error))
            self.assertEqual(broken, collector.state['corrected_links'][0]['original_url'])
            pages[replacement] = response(replacement, '<title>Opera 135.0.5960.0</title>')
            self.assertIsNone(collector.verified_document_replacement(broken, error))

    def test_timestamp_boundary_and_printed_calendar_day(self):
        for value, expected in [('2025-12-31T14:59:59Z', 'before_period'),
                                ('2025-12-31T15:00:00Z', 'in_period'),
                                ('2026-01-01', 'in_period'), ('2025-12-31', 'before_period'),
                                ('2026-11-16T12:53:41Z', 'after_cutoff'), (None, 'unknown')]:
            self.assertEqual(expected, dated_scope('2026-01-01', CUTOFF, value, 'publication')['status'])
        self.assertEqual(scope_semantics(dated_scope('2026-01-01', CUTOFF, '2026-01-01', 'publication')),
                         scope_semantics(dated_scope('2026-01-01', '2026-11-17T00:00:00Z', '2026-01-01', 'publication')))

    def bundles(self, before, after, partial=False):
        config = load_config(ROOT / 'config/chrome-source-scope.yml')
        old_files, new_files = fixture_files(False), fixture_files(False)
        old_files['components/temporal.cc'] = before
        new_files['components/temporal.cc'] = after
        with tempfile.TemporaryDirectory() as old, tempfile.TemporaryDirectory() as new:
            a = collect(config, MemoryProvider(old_files, 'a' * 40, not partial), old, observed_at='2026-11-16T00:00:00Z')
            b = collect(config, MemoryProvider(new_files, 'b' * 40), new, observed_at='2026-11-16T00:00:00Z')
        return a, b

    def project(self, a, b):
        return compare(b, a, since='2026-01-01', cutoff=CUTOFF, boundary_time=BOUNDARY, current_time=CUTOFF)

    def test_endpoint_semantics_not_file_hash_lines_or_comments(self):
        a, b = self.bundles('BASE_FEATURE(kSame, base::FEATURE_DISABLED_BY_DEFAULT);\nBASE_FEATURE(kChanged, base::FEATURE_DISABLED_BY_DEFAULT);\nBASE_FEATURE(kGone, base::FEATURE_ENABLED_BY_DEFAULT);',
                           '// file edit\n\nBASE_FEATURE( kSame ,base::FEATURE_DISABLED_BY_DEFAULT );\nBASE_FEATURE(kChanged, base::FEATURE_ENABLED_BY_DEFAULT);\nBASE_FEATURE(kNew, base::FEATURE_ENABLED_BY_DEFAULT);')
        result = self.project(a, b)
        scopes = {e['symbol']: e['temporal_scope'] for e in result['experiments']}
        self.assertEqual('unchanged', scopes['kSame']['status'])
        self.assertEqual('changed', scopes['kChanged']['change'])
        self.assertEqual('added', scopes['kNew']['change'])
        self.assertNotIn('kGone', scopes)
        self.assertEqual([], result['removed_candidates'])
        for s in result['source_items']:
            validate_record('source_item', s)

    def test_baseline_failure_never_proves_new_definition(self):
        for partial, text in [(True, ''), (False, 'BASE_FEATURE(kBroken);')]:
            a, b = self.bundles(text, 'BASE_FEATURE(kNew, base::FEATURE_ENABLED_BY_DEFAULT);', partial)
            scope = next(e['temporal_scope'] for e in self.project(a, b)['experiments'] if e['symbol'] == 'kNew')
            self.assertEqual('unknown', scope['status'])

    def test_symbolic_feature_default_and_name_initializers(self):
        cases = [
            ('constexpr base::FeatureState kDefault = base::FEATURE_DISABLED_BY_DEFAULT;\nBASE_FEATURE(kDemo, kDefault);',
             'constexpr base::FeatureState kDefault = base::FEATURE_ENABLED_BY_DEFAULT;\nBASE_FEATURE(kDemo, kDefault);'),
            ('constexpr base::FeatureState ENABLED = base::FEATURE_DISABLED_BY_DEFAULT;\nBASE_FEATURE(kDemo, ENABLED);',
             'constexpr base::FeatureState ENABLED = base::FEATURE_ENABLED_BY_DEFAULT;\nBASE_FEATURE(kDemo, ENABLED);'),
            ('#define DEFAULT_STATE base::FEATURE_DISABLED_BY_DEFAULT\nBASE_FEATURE(kDemo, DEFAULT_STATE);',
             '#define DEFAULT_STATE base::FEATURE_ENABLED_BY_DEFAULT\nBASE_FEATURE(kDemo, DEFAULT_STATE);'),
            ('const char kName[] = "Old"; BASE_FEATURE(kDemo, kName, base::FEATURE_ENABLED_BY_DEFAULT);',
             'const char kName[] = "New"; BASE_FEATURE(kDemo, kName, base::FEATURE_ENABLED_BY_DEFAULT);'),
        ]
        for old, new in cases:
            with self.subTest(old=old):
                a, b = self.bundles(old, new)
                item = next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'kDemo')
                self.assertEqual('changed', item['temporal_scope']['change'])
        pattern = ('namespace gwp_asan::internal {\n#if BUILDFLAG(IS_WIN) || BUILDFLAG(IS_APPLE) || '
                   'BUILDFLAG(IS_LINUX) || BUILDFLAG(IS_CHROMEOS) || '
                   '(BUILDFLAG(IS_ANDROID) && defined(ARCH_CPU_64_BITS))%s\n'
                   'constexpr base::FeatureState kDefaultEnabled = base::FEATURE_ENABLED_BY_DEFAULT;\n#else\n'
                   'constexpr base::FeatureState kDefaultEnabled = base::FEATURE_DISABLED_BY_DEFAULT;\n#endif\n'
                   'BASE_FEATURE(kGwpAsanMalloc, kDefaultEnabled);\nBASE_FEATURE(kGwpAsanPartitionAlloc, kDefaultEnabled);\n}')
        a, b = self.bundles(pattern % '', pattern % ' || BUILDFLAG(IS_IOS)')
        result = self.project(a, b)
        changed = [e for e in result['experiments'] if e['symbol'].startswith('gwp_asan::internal::kGwp')]
        self.assertEqual(2, len(changed))
        self.assertTrue(all(e['temporal_scope']['change'] == 'changed' for e in changed))
        facts = [f for f in b['facts'] if f['experiment_id'] in {e['experiment_id'] for e in changed}]
        self.assertTrue(all(len(f['semantic']['options']) == 2 and all(o['conditions'] for o in f['semantic']['options']) for f in facts))
        # Formatting a condition cannot manufacture a semantic change.
        a, b = self.bundles(pattern % ' || BUILDFLAG(IS_IOS)', (pattern % ' || BUILDFLAG(IS_IOS)').replace(' || ', '  ||  '))
        self.assertTrue(all(e['temporal_scope']['change'] == 'unchanged' for e in self.project(a, b)['experiments'] if e['symbol'].startswith('gwp_asan::internal::kGwp')))

    def test_wrapper_object_macros_keep_conditions_and_literal_parameter_names(self):
        old = ('#if A\n#define STATE base::FEATURE_ENABLED_BY_DEFAULT\n#else\n'
               '#define STATE base::FEATURE_DISABLED_BY_DEFAULT\n#endif\n'
               '#define DEFINE_DEMO(name) BASE_FEATURE(name, STATE)\nDEFINE_DEMO(kDemo);')
        a, b = self.bundles(old, old.replace('FEATURE_ENABLED_BY_DEFAULT', 'FEATURE_DISABLED_BY_DEFAULT', 1))
        item = next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'kDemo')
        self.assertEqual('changed', item['temporal_scope']['change'])
        self.assertEqual('STATE', item['default_state'])
        fact = next(f for f in b['facts'] if f['experiment_id'] == item['experiment_id'])
        self.assertEqual(2, len(fact['semantic']['options']))
        self.assertTrue(all(o['conditions'] for o in fact['semantic']['options']))
        # Wrapper-definition arms and object-definition arms remain independent.
        nested = ('#if A\n#define STATE base::FEATURE_ENABLED_BY_DEFAULT\n#else\n#define STATE base::FEATURE_DISABLED_BY_DEFAULT\n#endif\n'
                  '#if PLATFORM\n#define DEFINE_DEMO(name) BASE_FEATURE(name, STATE)\n#else\n'
                  '#define DEFINE_DEMO(name) BASE_FEATURE(name, base::FEATURE_DISABLED_BY_DEFAULT)\n#endif\nDEFINE_DEMO(kDemo);')
        a, b = self.bundles(nested, nested.replace('FEATURE_ENABLED_BY_DEFAULT', 'FEATURE_DISABLED_BY_DEFAULT', 1))
        self.assertTrue(all(e['temporal_scope']['change'] == 'changed' for e in self.project(a, b)['experiments'] if e['symbol'] == 'kDemo'))
        country = old.replace('BASE_FEATURE(name, STATE)', 'BASE_FEATURE_WITH_COUNTRY_RESTRICTIONS(name, STATE, "us")').replace('BY_DEFAULT', 'FOR_COUNTRIES')
        a, b = self.bundles(country, country.replace('FEATURE_ENABLED_FOR_COUNTRIES', 'FEATURE_DISABLED_FOR_COUNTRIES', 1))
        self.assertEqual('changed', next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'kDemo')['temporal_scope']['change'])
        values, _, _ = parse('demo.cc', '#define DEFINE_DEMO(name) BASE_FEATURE(name, "name", base::FEATURE_ENABLED_BY_DEFAULT)\nDEFINE_DEMO(kDemo);')
        self.assertEqual('name', values[0].value)

    def test_wrapper_redefinition_does_not_change_earlier_calls(self):
        old = ('#define DEFINE_DEMO(name) BASE_FEATURE(name, base::FEATURE_ENABLED_BY_DEFAULT)\n'
               'DEFINE_DEMO(kSame);\n')
        new = (old + '#undef DEFINE_DEMO\n'
               '#define DEFINE_DEMO(name) BASE_FEATURE(name, base::FEATURE_DISABLED_BY_DEFAULT)\n'
               'DEFINE_DEMO(kOther);\n')
        rows = [e for e in self.project(*self.bundles(old, new))['experiments']
                if e['symbol'] in {'kSame', 'kOther'}]
        self.assertEqual(2, len(rows))
        self.assertEqual({'kSame': ('unchanged', 'base::FEATURE_ENABLED_BY_DEFAULT'),
                          'kOther': ('added', 'base::FEATURE_DISABLED_BY_DEFAULT')},
                         {e['symbol']: (e['temporal_scope']['change'], e['default_state']) for e in rows})

    def test_wrapper_uses_without_a_proven_definition_are_unknown(self):
        text = ('DEFINE_DEMO(kBefore);\n'
                '#define DEFINE_DEMO(name) BASE_FEATURE(name, base::FEATURE_ENABLED_BY_DEFAULT)\n'
                '#if PLATFORM\n#undef DEFINE_DEMO\n#endif\nDEFINE_DEMO(kConditional);\n'
                '#undef DEFINE_DEMO\nDEFINE_DEMO(kAfter);\n'
                '#define DEFINE_DEMO(name) OTHER_FEATURE(name)\nDEFINE_DEMO(kUnsupported);\n')
        values, _, _ = parse('features.cc', text)
        self.assertEqual(['kBefore', 'kConditional', 'kAfter', 'kUnsupported'], [v.symbol for v in values])
        self.assertFalse(any(v.parsed for v in values))

    def test_wrapper_macro_ambiguity_undef_and_missing_arms_are_unknown(self):
        for prelude in (
            '#if A\n#define STATE base::FEATURE_ENABLED_BY_DEFAULT\n#endif\n',
            '#define STATE base::FEATURE_ENABLED_BY_DEFAULT\n#define STATE base::FEATURE_DISABLED_BY_DEFAULT\n',
            '#define STATE base::FEATURE_ENABLED_BY_DEFAULT\n#undef STATE\n',
            'constexpr auto STATE = base::FEATURE_ENABLED_BY_DEFAULT;\n#define STATE base::FEATURE_DISABLED_BY_DEFAULT\n',
        ):
            text = prelude + '#define DEFINE_DEMO(name) BASE_FEATURE(name, STATE)\nDEFINE_DEMO(kDemo);'
            with self.subTest(prelude=prelude):
                a, b = self.bundles(text, text)
                self.assertEqual('unknown', next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'kDemo')['temporal_scope']['status'])
        # Macro aliases expand at use time and retain the caller's namespace.
        old = ('namespace demo { constexpr auto kState = base::FEATURE_ENABLED_BY_DEFAULT;\n'
               '#define STATE ALIAS\n#define ALIAS kState\n#define DEFINE_DEMO(name) BASE_FEATURE(name, STATE)\nDEFINE_DEMO(kDemo); }')
        a, b = self.bundles(old, old.replace('FEATURE_ENABLED_BY_DEFAULT', 'FEATURE_DISABLED_BY_DEFAULT'))
        self.assertEqual('changed', next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'demo::kDemo')['temporal_scope']['change'])

    def test_local_condition_macro_value_is_unknown_not_platform_predicate(self):
        for body in (
            '#if A\nBASE_FEATURE(kDemo, base::FEATURE_ENABLED_BY_DEFAULT);\n#endif',
            '#if A\n#define STATE base::FEATURE_ENABLED_BY_DEFAULT\n#else\n#define STATE base::FEATURE_DISABLED_BY_DEFAULT\n#endif\n#define DEFINE_DEMO(name) BASE_FEATURE(name, STATE)\nDEFINE_DEMO(kDemo);',
        ):
            a, b = self.bundles('#define A 1\n' + body, '#define A 0\n' + body)
            item = next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'kDemo')
            self.assertEqual('unknown', item['temporal_scope']['status'])
        a, b = self.bundles('#if BUILDFLAG(IS_ANDROID)\nBASE_FEATURE(kDemo, base::FEATURE_ENABLED_BY_DEFAULT);\n#endif',
                            '#if BUILDFLAG(IS_IOS)\nBASE_FEATURE(kDemo, base::FEATURE_ENABLED_BY_DEFAULT);\n#endif')
        self.assertEqual('changed', next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'kDemo')['temporal_scope']['change'])

    def test_whole_header_guard_is_structural_but_other_macro_conditions_remain_unknown(self):
        header = ('// Header comment\n#ifndef DEMO_H_\n#define DEMO_H_\n'
                  '#if BUILDFLAG(IS_WIN)\nconstexpr auto kState = base::FEATURE_ENABLED_BY_DEFAULT;\n'
                  '#else\nconstexpr auto kState = base::FEATURE_DISABLED_BY_DEFAULT;\n#endif\n'
                  'namespace switches { const char kDemo[] = "demo"; }\n#endif // DEMO_H_\n')
        self.assertEqual('DEMO_H_', conventional_include_guard(header))
        invalid = [header.replace('#define DEMO_H_', '#define DEMO_H_ 1'),
                   header + 'int outside;\n', 'int before;\n' + header,
                   header.replace('#endif // DEMO_H_', '#else\nint other;\n#endif'),
                   header.replace('namespace switches', '#undef DEMO_H_\nnamespace switches'),
                   header.replace('namespace switches', '#if defined(DEMO_H_)\n#endif\nnamespace switches'),
                   header.replace('#endif // DEMO_H_', '')]
        self.assertTrue(all(conventional_include_guard(value) is None for value in invalid))
        bundles = []
        for revision, guard, state in [('a', 'DEMO_H_', 'ENABLED'), ('b', 'RENAMED_H_', 'DISABLED')]:
            files = fixture_files(False)
            files['components/demo.h'] = header.replace('DEMO_H_', guard).replace('FEATURE_ENABLED_BY_DEFAULT', 'FEATURE_' + state + '_BY_DEFAULT')
            files['components/demo.cc'] = 'BASE_FEATURE(kGuarded, kState);'
            with tempfile.TemporaryDirectory() as tmp:
                bundles.append(collect(load_config(ROOT / 'config/chrome-source-scope.yml'), MemoryProvider(files, revision * 40), tmp,
                                       observed_at='2026-11-16T00:00:00Z'))
        projected = self.project(*bundles)
        switch = next(e for e in projected['experiments'] if e['symbol'] == 'switches::kDemo')
        feature = next(e for e in projected['experiments'] if e['symbol'] == 'kGuarded')
        self.assertEqual('unchanged', switch['temporal_scope']['status'])
        self.assertEqual([], switch['build_conditions'])
        self.assertEqual('changed', feature['temporal_scope']['change'])
        fact = next(f for f in bundles[1]['facts'] if f['experiment_id'] == feature['experiment_id'])
        self.assertEqual([], fact['semantic']['unresolved_references'])
        self.assertEqual(2, len(fact['semantic']['options']))
        self.assertTrue(all('H_' not in str(o['conditions']) for o in fact['semantic']['options']))
        # Invalid guard-like files retain the existing conservative behavior.
        for value in invalid[:1] + invalid[4:6]:
            files['components/demo.h'] = value
            with tempfile.TemporaryDirectory() as tmp:
                unknown = collect(load_config(ROOT / 'config/chrome-source-scope.yml'), MemoryProvider(files, 'c' * 40), tmp,
                                  observed_at='2026-11-16T00:00:00Z')
            item = next(e for e in self.project(bundles[0], unknown)['experiments'] if e['symbol'] == 'switches::kDemo')
            self.assertEqual('unknown', item['temporal_scope']['status'])

    def test_guard_literals_are_tokens_but_raw_string_directives_are_not(self):
        header = ('#ifndef DEMO_H_\n#define DEMO_H_\n'
                  'BASE_FEATURE(kDemo, base::FEATURE_ENABLED_BY_DEFAULT);\n#endif\n')
        literals = ('"not-empty"', "'x'", 'R"(not-empty)"', '""')
        invalid = [header.replace('#define DEMO_H_', '#define DEMO_H_ ' + literal) for literal in literals]
        invalid += [literal + '\n' + header for literal in literals]
        invalid += [header + literal + '\n' for literal in literals]
        invalid += [header.replace('#endif', '#endif ' + literal) for literal in literals]
        for value in invalid:
            with self.subTest(value=value):
                self.assertIsNone(conventional_include_guard(value))
                files = fixture_files(False)
                files['components/demo.h'] = value
                bundles = []
                for revision in ('a', 'b'):
                    with tempfile.TemporaryDirectory() as tmp:
                        bundles.append(collect(load_config(ROOT / 'config/chrome-source-scope.yml'),
                                               MemoryProvider(files, revision * 40), tmp,
                                               observed_at='2026-11-16T00:00:00Z'))
                item = next(e for e in self.project(*bundles)['experiments'] if e['symbol'] == 'kDemo')
                self.assertEqual('unknown', item['temporal_scope']['status'])
                self.assertIn('!defined(DEMO_H_)', item['build_conditions'])
        # Raw-string contents must neither end the wrapper nor count as macro
        # uses. They are real tokens inside the wrapper, not CPP directives.
        raw_body = 'constexpr char kText[] = R"(\n#endif\n#else\n#define DEMO_H_\n)";\n'
        self.assertEqual('DEMO_H_', conventional_include_guard(header.replace('BASE_FEATURE', raw_body + 'BASE_FEATURE')))

    def test_symbolic_default_conditions_survive_normalization_contract(self):
        from pipeline.normalize.core import normalize_chrome
        from schemas.validate import ContractError
        text = '#if A\nconstexpr auto kDefault = base::FEATURE_ENABLED_BY_DEFAULT;\n#else\nconstexpr auto kDefault = base::FEATURE_DISABLED_BY_DEFAULT;\n#endif\nBASE_FEATURE(kDemo, kDefault);'
        a, b = self.bundles(text, text.replace("FEATURE_ENABLED_BY_DEFAULT", "FEATURE_DISABLED_BY_DEFAULT", 1))
        projected = self.project(a, b)
        catalog, events = normalize_chrome(projected, projected['source_items'])
        item = next(e for e in catalog if e['symbol'] == 'kDemo')
        validate_record('experiment', item)
        self.assertEqual(2, len(item['source_definition']['options']))
        self.assertTrue(all(o['conditions'] for o in item['source_definition']['options']))
        event = next(e for e in events if e['experiment_id'] == item['experiment_id'])
        validate_record('experiment_event', event)
        for field in ('before', 'after'):
            invalid_event = copy.deepcopy(event)
            invalid_event[field] = copy.deepcopy(event['after'])
            invalid_event[field]['source_definition']['options'][0]['conditions'] = [123]
            with self.assertRaises(ContractError): validate_record('experiment_event', invalid_event)
        for path in (ROOT / 'data/experiment-events').glob('*.json'):
            for accepted in json.loads(path.read_text()): validate_record('experiment_event', accepted)
        malformed = copy.deepcopy(item)
        malformed['source_definition']['options'][0]['conditions'] = [123]
        with self.assertRaises(ContractError): validate_record('experiment', malformed)
        malformed = copy.deepcopy(item)
        malformed['source_definition']['options'][0]['unexpected'] = True
        with self.assertRaises(ContractError): validate_record('experiment', malformed)

    def test_unsupported_or_ambiguous_default_dependencies_are_unknown(self):
        for text in (
            'BASE_FEATURE(kDemo, UnknownDefault());',
            'BASE_FEATURE(kDemo, missing_constant);',
            'constexpr base::FeatureState kDefault = ChooseState(); BASE_FEATURE(kDemo, kDefault);',
            'constexpr auto kDefault = kOther; constexpr auto kOther = kDefault; BASE_FEATURE(kDemo, kDefault);',
            '#if A\nconstexpr auto kDefault = base::FEATURE_ENABLED_BY_DEFAULT;\n#endif\nBASE_FEATURE(kDemo, kDefault);',
            'constexpr auto kDefault = base::FEATURE_ENABLED_BY_DEFAULT; constexpr auto kDefault = base::FEATURE_DISABLED_BY_DEFAULT; BASE_FEATURE(kDemo, kDefault);',
            'BASE_FEATURE(kDemo, condition ? base::FEATURE_ENABLED_BY_DEFAULT : base::FEATURE_DISABLED_BY_DEFAULT);',
        ):
            with self.subTest(text=text):
                a, b = self.bundles(text, text)
                item = next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'kDemo')
                self.assertEqual('unknown', item['temporal_scope']['status'])

    def test_github_rest_and_monthly_publication_timestamp_boundaries_without_metadata(self):
        dates = ['2025-12-31T14:59:59Z', '2025-12-31T15:00:00Z', '2025-12-31T15:00:01Z',
                 '2026-01-02T00:00:00Z', '2026-01-02T00:00:01Z']
        releases = [dict(id=i, html_url='https://github.com/brave/brave-browser/releases/tag/v' + str(i),
                         published_at=date, tag_name='v' + str(i), body='- A documented browser capability.') for i, date in enumerate(dates, 1)]
        sections = ''.join('<section id="r{0}"><a href="/brave/brave-browser/releases/tag/v{0}">Release</a>'
                           '<relative-time class="no-wrap" datetime="{1}"></relative-time>'
                           '<div class="markdown-body"><p>A documented browser capability.</p></div></section>'.format(i, date)
                           for i, date in enumerate(dates, 1))
        payload = {'payload': {'releasesIndexRoute': {'filterPhrase': 'created:2026-01-01..2026-01-31', 'page': 1,
                    'toc': [{'id': i, 'anchorId': 'r' + str(i)} for i in range(1, 6)]},
                    'releasesIndexRoute.Results': {'value': sections}}}
        for monthly in (False, True):
            with self.subTest(monthly=monthly), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                collector = BrowserCollector(root / 'repo', root / 'private', lambda url: response(url, json.dumps(payload if monthly else releases)))
                if monthly:
                    collector.collect_github = lambda: collector.collect_github_months(set())
                state = collector.collect(source('brave-releases'), '2026-01-02T00:00:00Z', '2026-01-01')
                rows = json.loads(collector.destination.read_text())
                self.assertEqual(3, len(rows))
                self.assertEqual(set(dates[1:4]), {r['temporal_scope']['evidence_date'] for r in rows})
                self.assertTrue(all(r['temporal_scope']['status'] == 'in_period' for r in rows))
                self.assertEqual(2, len(state['excluded_by_date']))

    def test_condition_change_and_unresolved_relation(self):
        a, b = self.bundles('#if WIN\nBASE_FEATURE(kSame, base::FEATURE_DISABLED_BY_DEFAULT);\n#endif',
                           '#if MAC\nBASE_FEATURE(kSame, base::FEATURE_DISABLED_BY_DEFAULT);\n#endif')
        self.assertEqual('changed', next(e['temporal_scope']['change'] for e in self.project(a, b)['experiments'] if e['symbol'] == 'kSame'))
        target = next(f for f in b['facts'] if f['semantic']['symbol'] == 'kSame')
        target['semantic']['unresolved_references'] = ['kMissing']
        self.assertEqual('unknown', next(e['temporal_scope']['status'] for e in self.project(a, b)['experiments'] if e['symbol'] == 'kSame'))
        with self.assertRaises(ValueError):
            compare(b, a, since='2026-01-01', cutoff=CUTOFF, boundary_time='2025-12-31T15:00:00Z', current_time=CUTOFF)
        with self.assertRaises(ValueError):
            compare(b, a, since='2026-01-01', cutoff=CUTOFF, boundary_time=BOUNDARY, current_time='2026-11-16T15:10:29Z')

    def test_unresolved_boundary_reference_cannot_prove_new_definition(self):
        a, b = self.bundles('BASE_FEATURE(kOld, base::FEATURE_ENABLED_BY_DEFAULT);',
                            'BASE_FEATURE(kOld, base::FEATURE_ENABLED_BY_DEFAULT); BASE_FEATURE(kNew, base::FEATURE_ENABLED_BY_DEFAULT);')
        next(f for f in a['facts'] if f['semantic']['symbol'] == 'kOld')['semantic']['unresolved_references'] = ['kNew']
        new = next(e for e in self.project(a, b)['experiments'] if e['symbol'] == 'kNew')
        self.assertEqual('unknown', new['temporal_scope']['status'])

    def test_multi_release_heading_dates_do_not_use_page_modified_date(self):
        config = source('edge-stable')
        html = '<meta name="date" content="2026-11-16"><div class="content"><h2 id="old">Version 1 — December 31, 2025</h2><p>Old item.</p><h2 id="new">Version 2 — January 1, 2026</h2><h3>Features</h3><p>New item.</p><h2>Undated policy</h2><p>Unknown item.</p></div>'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            collector = BrowserCollector(root / 'repo', root / 'private', lambda url: response(url, html))
            state = collector.collect(config, CUTOFF, '2026-01-01')
            rows = json.loads(collector.destination.read_text())
        self.assertEqual({'before_period', 'in_period', 'unknown'}, {r['temporal_scope']['status'] for r in rows})
        self.assertEqual({'in_period': 1, 'before_period': 1, 'after_cutoff': 0, 'date_unknown': 1}, state['temporal_coverage'])

    def test_wrapper_expansion_and_impossible_implicit_arm(self):
        text = '#if ANDROID\n#define DEFINE_DEMO(name) BASE_FEATURE_WITH_COUNTRY_RESTRICTIONS(name, base::FEATURE_ENABLED_FOR_COUNTRIES, "us")\n#else\n#define DEFINE_DEMO(name) BASE_FEATURE(name, base::FEATURE_DISABLED_BY_DEFAULT)\n#endif\nDEFINE_DEMO(kExample);'
        values, _, errors = parse('features.cc', text)
        self.assertFalse(errors)
        self.assertEqual(2, len(values))
        self.assertTrue(all(v.parsed for v in values))
        text = '#if A || B\nBASE_FEATURE(kExample,\n#if A\nbase::FEATURE_ENABLED_BY_DEFAULT);\n#elif B\nbase::FEATURE_DISABLED_BY_DEFAULT);\n#endif\n#endif'
        values, _, _ = parse('features.cc', text)
        self.assertEqual(2, len(values))
        self.assertTrue(all(v.parsed for v in values))
        self.assertEqual('x', literal('"\\x78"'))

    def test_parser_alias_requires_unique_exact_definition_correspondence(self):
        a, b = self.bundles('BASE_FEATURE(kSame, base::FEATURE_ENABLED_BY_DEFAULT);', 'BASE_FEATURE(kSame, base::FEATURE_ENABLED_BY_DEFAULT);')
        old, new = copy.deepcopy(a['experiments']), copy.deepcopy(b['experiments'])
        for records, bundle in [(old, a), (new, b)]:
            facts = {f['experiment_id']: f for f in bundle['facts']}
            for r in records:
                r['source_definition'] = source_definition(facts[r['experiment_id']])
        target = next(r for r in new if r['symbol'] == 'kSame')
        target.update(experiment_id='corrected-id', symbol='correct::kSame')
        aliases = parser_aliases(old, new, [])
        self.assertEqual(1, len(aliases))
        self.assertEqual('corrected-id', aliases[0]['target_id'])
        from pipeline.normalize.core import normalize_chrome
        previous, history = normalize_chrome(a, a['source_items'])
        accepted = next(r for r in previous if r['symbol'] == 'kSame')
        original_id = accepted['experiment_id']
        accepted['experiment_id'] = 'prior-parser-id'
        for event in history:
            if event['experiment_id'] == original_id:
                event['experiment_id'] = 'prior-parser-id'
        _, corrected_history = normalize_chrome(a, a['source_items'], previous, history)
        self.assertEqual(history, corrected_history)
        duplicate = copy.deepcopy(target)
        duplicate['experiment_id'] = 'ambiguous-id'
        self.assertFalse(parser_aliases(old, new + [duplicate], []))

    def test_generated_blink_and_mojo_defaults_have_source_locations(self):
        data = {'parameters': {'base_feature': {'default': ''}, 'base_feature_status': {'default': ''},
                               'status': {'valid_keys': ['Android', 'Win']}},
                'data': [{'name': 'Visible', 'status': 'stable'}, {'name': 'Absent', 'base_feature': 'none'},
                         {'name': 'Conditional', 'status': {'Android': 'stable', 'default': 'test'}}]}
        raw = json.dumps(data).replace('"name":', 'name:')
        generator = "if feature['base_feature'] == 'none':\n pass\nelif feature['base_feature'] == '':\n feature['base_feature'] = feature['name']"
        template = "BASE_FEATURE(k{{feature.base_feature}} feature.base_feature_status == 'enabled' feature.status == 'stable' feature.status[platform] == 'stable'"
        values, errors = blink_features({INPUT: raw, GENERATOR: generator, TEMPLATE: template})
        self.assertFalse(errors)
        self.assertEqual({'kVisible', 'kConditional'}, {v.symbol for v in values})
        self.assertTrue(all(v.path == INPUT and v.line > 0 for v in values))
        self.assertIn('ENABLED_BY_DEFAULT', values[0].default)
        self.assertIn('DISABLED_BY_DEFAULT', values[1].default)
        self.assertTrue(blink_features({INPUT: raw, GENERATOR: 'changed rules', TEMPLATE: template})[1])
        values, _, errors = parse('features.mojom', 'module webnn.mojom.features; [EnableIf=is_apple] feature kDemo {const string name = "Demo"; [EnableIf=is_mac] const bool default_state = true; [EnableIf=is_ios] const bool default_state = false;};')
        self.assertEqual(2, len(values))
        self.assertEqual('webnn::mojom::features::kDemo', values[0].qualified_symbol)
        self.assertNotEqual(values[0].default, values[1].default)
        self.assertTrue(all(v.parsed and len(v.conditions) == 2 for v in values))
        self.assertEqual(2, len(blink_features({INPUT: json.dumps(data), GENERATOR: generator, TEMPLATE: template})[0]))
        values, _, _ = parse('feature.mojom', 'module viz.mojom; feature EnableVizTestApis {const string name = "EnableVizTestApis"; const bool default_state = false;};')
        self.assertTrue(values[0].parsed)
        self.assertEqual('viz::mojom::EnableVizTestApis', values[0].qualified_symbol)
        from pipeline.collectors.chrome.generated import MOJO_GENERATOR, mojo_missing_default_is_disabled
        generator = '  def _IsFeatureOnByDefault(self, kind):\n    for constant in kind.constants:\n      if constant.name == "default_state":\n        return constant.value == "true"\n    return False\n  def _FeatureName(self, kind):\n    pass'
        self.assertTrue(mojo_missing_default_is_disabled({MOJO_GENERATOR: generator}))
        text = 'module content.mojom; feature kLegacy {const string name = "Legacy"; const bool enabled_state = true;};'
        self.assertFalse(parse('old.mojom', text)[0][0].parsed)
        legacy = parse('old.mojom', text, mojo_default_disabled=True)[0][0]
        self.assertTrue(legacy.parsed)
        self.assertEqual('base::FEATURE_DISABLED_BY_DEFAULT', legacy.default)  # enabled_state is ignored, not aliased.

    def test_enterprise_public_gate_and_archive_dates(self):
        config = source('chrome-enterprise')
        archive = 'https://support.google.com/chrome/a/answer/10314655?hl=en'
        api = 'https://release-notes-787862449254.us-central1.run.app'
        public = dict(id=10, name='Public capability', summary='Public product fact.',
                      created={'when': '2025-12-01 12:00:00'}, updated={'when': '2026-01-01 12:00:00'},
                      is_releasenotes_publish_ready=True, is_releasenotes_content_reviewed=True,
                      creator_email='person@example.invalid', owner_emails=['owner@example.invalid'])
        hidden = []
        for i, field in enumerate(('confidential', 'unlisted', 'deleted')):
            row = copy.deepcopy(public)
            row.update(id=20 + i, name='Private title must not escape')
            row[field] = True
            hidden.append(row)
        rows = [public] + hidden
        mapping = {archive: response(archive, '<a href="#144">Chrome 144: January 7, 2026</a><a href="#143">Chrome 143: December 10, 2025</a><a class="zippy" name="144">Chrome 144</a><div><h3>Updates</h3><p>New release fact.</p></div><a class="zippy" name="143">Chrome 143</a><div><p>Old release fact.</p></div>'),
                   api + '/versions': response(api + '/versions', json.dumps({'versions': [{'value': '158'}]})),
                   api + '/features?version=158&lang=en': response(api, json.dumps({'features': rows, 'total_count': len(rows)}))}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            collector = BrowserCollector(root / 'repo', root / 'private', mapping.__getitem__)
            state = collector.collect(config, CUTOFF, '2026-01-01')
            output = collector.destination.read_text()
            records = json.loads(output)
        self.assertEqual('complete', state['status'])
        self.assertEqual(3, state['enterprise_publication_excluded'])
        self.assertEqual(2, len(records))
        for sensitive in ('person@example', 'owner@example', 'Private title', 'Old release fact'):
            self.assertNotIn(sensitive, output)
        self.assertTrue(all(r['temporal_scope']['status'] == 'in_period' for r in records))
        self.assertEqual({'2026-01-01', '2026-01-07'}, {r['temporal_scope']['evidence_date'] for r in records})

    def test_enterprise_identity_requires_official_id_full_body_and_title(self):
        from pipeline.normalize.core import normalize_browser_catalog
        def item(sid, upstream, body, title='Same title', version='153', status=False):
            return dict(source_item_id=sid, source_id='chrome-platform-status' if status else 'chrome-enterprise',
                        record_status='parsed', item_key=upstream, item_content_sha256=body, title=title, version=version,
                        evidence={'url': 'https://chromestatus.com/feature/' + upstream if status else
                                  'https://release-notes-787862449254.us-central1.run.app/features?version=' + version + '&lang=en'})
        rows = [item('status', '10', 'a' * 64, status=True), item('v153', '10', 'a' * 64),
                item('v154', '10', 'a' * 64, version='154'), item('different-body', '10', 'b' * 64),
                item('different-id', '11', 'a' * 64), item('different-title', '12', 'a' * 64, title='Other title')]
        catalog = normalize_browser_catalog(rows)
        main = next(r for r in catalog if 'status' in r['source_item_ids'])
        self.assertEqual({'status', 'v153', 'v154'}, set(main['source_item_ids']))
        self.assertEqual(set(r['source_item_id'] for r in rows), set(s for f in catalog for s in f['source_item_ids']))
        self.assertEqual(4, len(catalog))

    def test_scope_deselection_preserves_judgment_history_without_removal(self):
        from pipeline.selection import run
        from pipeline.selection.core import decision
        from pipeline.normalize import load_dataset
        config = source('edge-stable')
        html = '<div class="content"><h2>January 1, 2026</h2><p id="one">A concrete browser task.</p></div>'
        def provider(context, rules):
            result = decision('selected', 'Compare the documented task.', priority='P2', question='Does task completion differ?', readiness='conditional')
            result['evidence_source_item_ids'] = [s['source_item_id'] for s in context['sources']]
            result['benchmark'] = dict(user_impact='Task completion.', material_change='Documented behavior.', steps=['Run task'],
                                      metrics=['Errors'], conditions='Fixture.', completion='Repeat.', evidence_quotes=[context['subject']['summary']])
            return result
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo, private = root / 'repo', root / 'private'
            shutil.copytree(ROOT / 'config', repo / 'config')
            collector = BrowserCollector(repo, private, lambda url: response(url, html))
            collector.collect(config, CUTOFF, '2026-01-01')
            first = run(repo, private, assessed_at='2026-12-01T00:00:00Z', provider=provider, model_id='fixture')
            self.assertEqual('selected', first['created'][0]['status'])
            original = copy.deepcopy(load_dataset(repo)['assessment'])
            rows = json.loads(collector.destination.read_text())
            rows[0]['temporal_scope'] = dated_scope('2026-01-01', CUTOFF)
            collector.destination.write_text(json.dumps(rows))
            second = run(repo, private, assessed_at='2026-12-02T00:00:00Z', provider=provider, model_id='fixture')
            self.assertFalse(second['failures'])
            self.assertEqual('excluded', second['created'][0]['status'])
            self.assertEqual('deterministic', second['created'][0]['evaluator'])
            dataset = load_dataset(repo)
            self.assertIn(original[0], dataset['assessment'])
            selected = next(s for s in dataset['selected'] if s['selection_kind'] == 'features')
            self.assertEqual([], selected['current'])
            self.assertEqual(['selected', 'deselected'], [h['action'] for h in selected['history']])
            self.assertEqual([], dataset['feature_event'])
            self.assertEqual([], dataset['experiment_event'])

    def test_github_month_payload_uses_publication_not_commit_date(self):
        config = source('brave-releases')
        query = 'created:2026-01-01..2026-01-31'
        html = '<section id="release-v1"><a href="/brave/brave-browser/releases/tag/v1">Release</a><relative-time class="no-wrap" datetime="2026-01-01T02:00:00Z"></relative-time><relative-time datetime="2025-12-31 14:00:00 UTC"></relative-time><div class="markdown-body"><p>Release capability.</p></div></section>'
        payload = {'payload': {'releasesIndexRoute': {'filterPhrase': query, 'page': 1, 'toc': [{'id': '10', 'anchorId': 'release-v1'}]},
                               'releasesIndexRoute.Results': {'value': html}}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            collector = BrowserCollector(root / 'repo', root / 'private', lambda url: response(url, json.dumps(payload)))
            collector.collect_github = lambda: collector.collect_github_months(set())
            state = collector.collect(config, '2026-01-31T23:00:00Z', '2026-01-01')
            rows = json.loads(collector.destination.read_text())
        self.assertEqual('partial', state['status'])  # Older-created complement is still unproven.
        self.assertEqual(1, state['release_search_unique'])
        self.assertEqual(1, len(rows))
        self.assertEqual('2026-01-01T02:00:00Z', rows[0]['temporal_scope']['evidence_date'])


if __name__ == '__main__':
    unittest.main()
