import copy
import json
import os
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

from pipeline.collect import collect_sources
from pipeline.collectors.browser import Response
from pipeline.collectors.chrome import collect
from pipeline.deduplicate import AliasIndex, digest
from pipeline.normalize import merge_sources, normalize_browser_facts, normalize_chrome, publish, validate_graph
from pipeline.normalize.core import normalize_browser_catalog
from pipeline.normalize.legacy import legacy_source, migrate_events, resolve_predecessors
from pipeline.selection.core import PM_FIELDS
from scripts.migrate_dataset import migrate, prepare
from schemas.validate import ContractError, load_config, validate_record, validate_dataset
from test_chrome_collectors import fixture_files, MemoryProvider

ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-11-16T00:00:00Z'


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name)
        self.repo = self.private / 'repository'
        self.repo.mkdir()
        shutil.copytree(ROOT / 'config', self.repo / 'config')

    def source(self, key='one', browser='chrome', channel='beta', platform=None):
        return legacy_source(browser, key, 'Same title', 'Document fact', 'https://example.com/' + key,
                             NOW, channel=channel, platform=platform or ['Windows'])

    def fact(self, sources, **updates):
        result = dict(canonical_key='upstream-42', title='Same title', source_item_ids=[s['source_item_id'] for s in sources],
            event_type='added', version='1', channel='beta', platform=['Windows'], before=None, after={'value': 'enabled'},
            summary='Explicit documented feature fact', verification_status='official_document_observation')
        result.update(updates)
        return result

    def bundle(self, files=None, revision='a' * 40, previous=None, complete=True):
        return collect(load_config(ROOT / 'config/chrome-source-scope.yml'), MemoryProvider(files or fixture_files(False), revision, complete),
                       self.private / revision, observed_at=NOW, previous=previous)

    def test_multisource_and_repeated_observation_not_new_event(self):
        sources = [self.source('english'), self.source('korean')]
        facts = [self.fact([s]) for s in sources]
        features, events = normalize_browser_facts(sources, facts)
        self.assertEqual((1, 1), (len(features), len(events)))
        self.assertEqual(set(s['source_item_id'] for s in sources), set(events[0]['source_item_ids']))
        old = copy.deepcopy(events)
        later = copy.deepcopy(sources)
        for s in later:
            s['observed_at'] = '2026-11-17T00:00:00Z'
        fs, es = normalize_browser_facts(later, facts, features, events)
        self.assertEqual(1, len(es))
        self.assertEqual(old[0]['observed_at'], es[0]['observed_at'])
        validate_dataset(dict(source_item=sources, feature=fs, feature_event=es))

    def test_beta_stable_platform_default_and_recurrence_are_distinct(self):
        source = self.source()
        facts = [self.fact([source]), self.fact([source], channel='stable'), self.fact([source], platform=['Android']),
                 self.fact([source], event_type='default_change', before={'value':'disabled'}, after={'value':'enabled'})]
        features, events = normalize_browser_facts([source], facts)
        self.assertEqual(4, len(events))
        _, recurrence = normalize_browser_facts([source], [self.fact([source], predecessor=events[-1]['event_id'])], features, events)
        self.assertEqual(5, len(recurrence))

    def test_similar_titles_and_different_products_never_force_merge(self):
        sources = [self.source('a'), self.source('b'), self.source('c', browser='edge')]
        facts = [self.fact([sources[0]]), self.fact([sources[1]], canonical_key='upstream-43'), self.fact([sources[2]])]
        features, events = normalize_browser_facts(sources, facts)
        self.assertEqual((3, 3), (len(features), len(events)))
        with self.assertRaises(ContractError):
            normalize_browser_facts(sources, [self.fact(sources)])

    def test_explicit_chromestatus_identity_only(self):
        good = self.source('123')
        good.update(source_id='chrome-platform-status', item_key='123', record_status='parsed')
        good['evidence']['url'] = 'https://chromestatus.com/feature/123'
        other = self.source('same-title')
        features = normalize_browser_catalog([good, other])
        self.assertEqual(1, len(features))
        self.assertEqual('chromestatus:123', features[0]['canonical_key'])
        self.assertEqual([], features[0]['event_ids'])
        self.assertEqual(1, len(normalize_browser_catalog([good], features)))

    def test_chrome_full_options_and_semantic_revision_rules(self):
        a = self.bundle()
        catalogs, events = normalize_chrome(a, a['source_items'])
        with_options = [e for e in catalogs if e['source_definition']['options']]
        self.assertTrue(with_options)
        expected = {f['experiment_id']: f['semantic']['options'] for f in a['facts']}
        for record in catalogs:
            self.assertEqual(expected[record['experiment_id']], record['source_definition']['options'])
        # Commit and line-number changes are evidence, not semantic changes.
        files = {p: ('\n' + s if p.endswith(('.cc', '.mm', '.h')) else s) for p, s in fixture_files(False).items()}
        b = self.bundle(files, 'b' * 40, a)
        sources = merge_sources(a['source_items'], b['source_items'])
        newer, same_events = normalize_chrome(b, sources, catalogs, events)
        self.assertEqual(len(events), len(same_events))
        # A real source default change is retained once; rerunning is idempotent.
        files['components/demo/features.cc'] = files['components/demo/features.cc'].replace('BASE_FEATURE(kHidden, "Hidden", base::FEATURE_DISABLED_BY_DEFAULT)', 'BASE_FEATURE(kHidden, "Hidden", base::FEATURE_ENABLED_BY_DEFAULT)')
        c = self.bundle(files, 'c' * 40, b)
        all_sources = merge_sources(sources, c['source_items'])
        final, changes = normalize_chrome(c, all_sources, newer, same_events)
        self.assertGreater(len(changes), len(events))
        self.assertTrue(any(e['event_type'] == 'default_change' for e in changes))
        self.assertEqual((final, changes), normalize_chrome(c, all_sources, final, changes))
        self.assertEqual((final, changes), normalize_chrome(a, all_sources, final, changes))
        validate_dataset(dict(source_item=all_sources, experiment=final, experiment_event=changes))

    def test_option_parameter_change_preserves_named_initializer_history(self):
        a = self.bundle()
        catalogs, events = normalize_chrome(a, a['source_items'])
        files = fixture_files(False)
        files['chrome/browser/about_flags.cc'] = files['chrome/browser/about_flags.cc'].replace('"mode", "fast"', '"mode", "careful"')
        b = self.bundle(files, 'b' * 40, a)
        catalogs, changed = normalize_chrome(b, merge_sources(a['source_items'], b['source_items']), catalogs, events)
        self.assertEqual(len(events) + 1, len(changed))
        event = next(e for e in changed if e['event_type'] == 'changed')
        self.assertIn('"fast"', str(event['before']['source_definition']['options']))
        self.assertIn('"careful"', str(event['after']['source_definition']['options']))
        self.assertTrue(any(o['symbol'] == 'kParams' for o in event['after']['source_definition']['options']))

    def test_unresolved_and_partial_do_not_delete_or_claim_rollout(self):
        a = self.bundle(fixture_files(True))
        catalogs, events = normalize_chrome(a, a['source_items'])
        self.assertTrue(any(s['record_status'] == 'unparsed' for s in a['source_items']))
        empty = dict(a, experiments=[], facts=[], removed_candidates=[], coverage={'complete': False})
        self.assertEqual((catalogs, events), normalize_chrome(empty, a['source_items'], catalogs, events))
        self.assertTrue(all(e['verification_status'] == 'source_only' and e['installed_availability'] == 'unknown' for e in catalogs))
        bad = copy.deepcopy(a)
        bad['facts'][0]['semantic']['definition'] += ' changed'
        with self.assertRaisesRegex(ContractError, 'hash mismatch'):
            normalize_chrome(bad, bad['source_items'])

    def test_verified_removal_restore_and_no_partial_guess(self):
        a = self.bundle()
        catalogs, events = normalize_chrome(a, a['source_items'])
        files = fixture_files(False)
        files['components/demo/features.cc'] = files['components/demo/features.cc'].replace('BASE_FEATURE(kModern, base::FEATURE_ENABLED_BY_DEFAULT);', '')
        b = self.bundle(files, 'b' * 40, a)
        self.assertEqual(1, len(b['removed_candidates']))
        sources = merge_sources(a['source_items'], b['source_items'])
        final, changes = normalize_chrome(b, sources, catalogs, events, observed_at=NOW)
        self.assertEqual(1, sum(e['event_type'] == 'removed' for e in changes))
        self.assertEqual((final, changes), normalize_chrome(b, sources, final, changes, observed_at=NOW))
        invalid = dict(b, coverage={'complete': False})
        with self.assertRaises(ContractError):
            normalize_chrome(invalid, sources, catalogs, events, observed_at=NOW)
        c = self.bundle(fixture_files(False), 'c' * 40, b)
        _, restored = normalize_chrome(c, merge_sources(sources, c['source_items']), final, changes)
        self.assertEqual(1, sum(e['event_type'] == 'restored' for e in restored))

    def test_old_positive_replay_cannot_restore_removed_definition(self):
        a = self.bundle()
        catalogs, events = normalize_chrome(a, a['source_items'])
        files = fixture_files(False)
        files['components/demo/features.cc'] = files['components/demo/features.cc'].replace('BASE_FEATURE(kModern, base::FEATURE_ENABLED_BY_DEFAULT);', '')
        b = self.bundle(files, 'b' * 40, a)
        sources = merge_sources(a['source_items'], b['source_items'])
        removed, history = normalize_chrome(b, sources, catalogs, events, observed_at=NOW)
        ident = b['removed_candidates'][0]['experiment_id']
        self.assertEqual('removed', next(e for e in removed if e['experiment_id'] == ident)['lifecycle'])
        replay_sources = merge_sources(sources, a['source_items'])
        self.assertEqual(sources, replay_sources)
        self.assertEqual((removed, history), normalize_chrome(a, replay_sources, removed, history))
        # Even direct stale source input cannot override the accepted event chain.
        self.assertEqual((removed, history), normalize_chrome(a, a['source_items'], removed, history))

    def test_old_removal_replay_cannot_remove_fresh_restoration(self):
        a = self.bundle()
        catalogs, events = normalize_chrome(a, a['source_items'])
        files = fixture_files(False)
        files['components/demo/features.cc'] = files['components/demo/features.cc'].replace('BASE_FEATURE(kModern, base::FEATURE_ENABLED_BY_DEFAULT);', '')
        b = self.bundle(files, 'b' * 40, a)
        sources = merge_sources(a['source_items'], b['source_items'])
        removed, history = normalize_chrome(b, sources, catalogs, events, observed_at=NOW)
        c = self.bundle(fixture_files(False), 'c' * 40, b)
        sources = merge_sources(sources, c['source_items'])
        restored, history = normalize_chrome(c, sources, removed, history)
        self.assertEqual(1, sum(e['event_type'] == 'restored' for e in history))
        self.assertEqual((restored, history), normalize_chrome(b, merge_sources(sources, b['source_items']), restored, history, observed_at=NOW))
        self.assertEqual((restored, history), normalize_chrome(b, b['source_items'], restored, history, observed_at=NOW))
        # The later removal proof C -> D still applies exactly once.
        d = self.bundle(files, 'd' * 40, c)
        again, final = normalize_chrome(d, merge_sources(sources, d['source_items']), restored, history, observed_at=NOW)
        self.assertEqual(2, sum(e['event_type'] == 'removed' for e in final))
        self.assertEqual((again, final), normalize_chrome(d, merge_sources(sources, d['source_items']), again, final, observed_at=NOW))

    def test_removal_extends_new_same_semantic_observation_without_new_event(self):
        a = self.bundle()
        catalogs, events = normalize_chrome(a, a['source_items'])
        d = self.bundle(fixture_files(False), 'd' * 40, a)
        sources = merge_sources(a['source_items'], d['source_items'])
        advanced, unchanged = normalize_chrome(d, sources, catalogs, events)
        self.assertEqual(events, unchanged)
        files = fixture_files(False)
        files['components/demo/features.cc'] = files['components/demo/features.cc'].replace('BASE_FEATURE(kModern, base::FEATURE_ENABLED_BY_DEFAULT);', '')
        e = self.bundle(files, 'e' * 40, d)
        proof = e['removed_candidates'][0]
        self.assertEqual('d' * 40, proof['before_revision'])
        removed, history = normalize_chrome(e, merge_sources(sources, e['source_items']), advanced, unchanged, observed_at=NOW)
        self.assertEqual(len(events) + 1, len(history))
        self.assertEqual('removed', next(row for row in removed if row['experiment_id'] == proof['experiment_id'])['lifecycle'])

    def test_explicit_correction_archives_old_fact_and_keeps_id(self):
        from pipeline.normalize.corrections import correct_event, correction_files
        source = self.source()
        _, events = normalize_browser_facts([source], [self.fact([source])])
        old = copy.deepcopy(events[0])
        current, archive = correct_event('feature_event', old, {'summary': 'Corrected official description'}, [source['source_item_id']])
        self.assertEqual(old, archive)
        self.assertEqual(old['event_id'], current['event_id'])
        self.assertEqual(2, current['revision'])
        path, saved = correction_files('feature_event', current, archive)
        self.assertTrue(path.startswith('data/event-revisions/'))
        self.assertEqual(old, saved)
        with self.assertRaises(ContractError):
            correct_event('feature_event', old, {'event_id': 'new'}, [source['source_item_id']])

    def test_alias_correction_keeps_history_and_rejects_cycle(self):
        first = dict(alias_id='alias-1', subject_kind='feature', old_id='old', target_id='wrong',
                     source_item_ids=['source'], reason='Explicit upstream mapping', revision=1, supersedes=None)
        correction = dict(first, alias_id='alias-2', target_id='right', revision=2, supersedes='alias-1', reason='Official correction')
        aliases = AliasIndex([first, correction], {'feature': {'wrong', 'right'}}, {'source'})
        self.assertEqual('right', aliases.resolve('feature', 'old'))
        self.assertEqual('wrong', aliases.entries[0]['target_id'])
        with self.assertRaisesRegex(ContractError, 'cycle'):
            AliasIndex([first, dict(first, alias_id='alias-3', old_id='wrong', target_id='old')])
        with self.assertRaisesRegex(ContractError, 'evidence'):
            AliasIndex([first], {'feature': {'wrong'}}, set())

    def test_immutable_source_history_rejects_rewrite_and_retains_missing(self):
        source = self.source()
        self.assertEqual([source], merge_sources([source], []))
        rewritten = copy.deepcopy(source)
        rewritten['revisions'][0]['revision_id'] = 'changed'
        with self.assertRaises(ContractError):
            merge_sources([source], [rewritten])

    def test_options_contract_is_typed_and_new_events_cannot_use_legacy_fields(self):
        a = self.bundle()
        catalogs, _ = normalize_chrome(a, a['source_items'])
        record = next(e for e in catalogs if e['source_definition']['options'])
        for mutation in [dict(symbol='x', path='../escape', expression='{}'), dict(symbol='x', path='x.cc', expression=42), dict(symbol='x', path='x.cc', expression='{}', owners=['private'])]:
            bad = copy.deepcopy(record)
            bad['source_definition']['options'] = [mutation]
            with self.assertRaises(ContractError):
                validate_record('experiment', bad)
        source = self.source()
        _, events = normalize_browser_facts([source], [self.fact([source])])
        event = dict(events[0], korea={'old': True})
        with self.assertRaises(ContractError):
            validate_record('feature_event', event)
        event['origin'] = 'legacy'
        validate_record('feature_event', event)

    def test_staged_validation_and_write_failure_leave_original_files(self):
        source = self.source()
        rel = 'data/source-items/chrome/legacy.json'
        (self.repo / rel).parent.mkdir(parents=True)
        (self.repo / rel).write_text(json.dumps([source]))
        before = (self.repo / rel).read_bytes()
        invalid = {rel: [source], 'data/catalog/features/catalog.json': [{'feature_id': 'missing'}]}
        with self.assertRaises(ContractError):
            publish(self.repo, invalid, self.private / 'transaction')
        self.assertEqual(before, (self.repo / rel).read_bytes())
        writes = []
        def fail_second(src, dst):
            writes.append(str(dst))
            if len(writes) == 2:
                raise OSError('simulated write failure')
            os.replace(src, dst)
        changes = {rel: [source], 'data/aliases/corrections.json': []}
        with self.assertRaises(OSError):
            publish(self.repo, changes, self.private / 'transaction', replace=fail_second)
        self.assertEqual(before, (self.repo / rel).read_bytes())
        self.assertFalse((self.repo / 'data/aliases/corrections.json').exists())
        publish(self.repo, changes, self.private / 'transaction')
        self.assertEqual([source], load_config(self.repo / rel))

    def test_alias_and_event_archive_cannot_be_rewritten(self):
        source = self.source()
        features, events = normalize_browser_facts([source], [self.fact([source])])
        row = dict(alias_id='alias-1', subject_kind='feature', old_id='retained-old-id', target_id=features[0]['feature_id'],
                   source_item_ids=[source['source_item_id']], reason='Source identity mapping', revision=1, supersedes=None)
        changes = {'data/source-items/chrome/legacy.json': [source], 'data/catalog/features/catalog.json': features,
                   'data/events/' + events[0]['event_id'] + '.json': events[0], 'data/aliases/corrections.json': [row],
                   'data/event-revisions/old/schema-v1.json': {'schema_version':1}}
        publish(self.repo, changes, self.private / 'transaction')
        bad = copy.deepcopy(row)
        bad['reason'] = 'Silently changed'
        with self.assertRaisesRegex(ContractError, 'append-only'):
            publish(self.repo, {'data/aliases/corrections.json': [bad]}, self.private / 'transaction')
        with self.assertRaisesRegex(ContractError, 'immutable'):
            publish(self.repo, {'data/event-revisions/old/schema-v1.json': {'schema_version':2}}, self.private / 'transaction')
        with self.assertRaisesRegex(ContractError, 'Missing experiment'):
            a = self.bundle()
            catalogs, experiment_events = normalize_chrome(a, a['source_items'])
            catalogs[0]['relationships'] = [{'kind':'controls','target_id':'absent'}]
            validate_dataset(dict(source_item=a['source_items'], experiment=catalogs, experiment_event=experiment_events))

    def test_real_legacy_127_ids_fields_links_and_judgments_survive(self):
        # The archive is the exact v1 input, outside all current-record globs.
        archives = sorted((ROOT / 'data/event-revisions').glob('*/schema-v1.json'))
        self.assertEqual(127, len(archives))
        originals = [load_config(p) for p in archives]
        sources, features, events = migrate_events(originals)
        self.assertEqual(111, len(features))
        self.assertEqual(Counter(selected=75, watch=30, pending_verification=13, excluded=9), Counter(e['selection_status'] for e in events))
        for old, event in zip(originals, events):
            self.assertEqual({k: v for k, v in old.items() if k != 'schema_version'}, {k: event[k] for k in old if k != 'schema_version'})
            current = load_config(ROOT / 'data/events' / (event['event_id'] + '.json'))
            # Current compatibility judgments can change. The migrated facts
            # and the original judgment in the v1 archive serve different roles.
            projected = PM_FIELDS | {'temporal_scope'}
            self.assertEqual({k: v for k, v in event.items() if k not in projected},
                             {k: v for k, v in current.items() if k not in projected})
        predecessors, resolved = resolve_predecessors(ROOT, events)
        self.assertEqual(1, len(predecessors))
        self.assertEqual(128, len(resolved))
        _, features, resolved = migrate_events(resolved, features)
        validate_dataset(dict(source_item=sources + predecessors, feature=features, feature_event=resolved))

    def test_materialized_graph_and_legacy_files_remain_linked(self):
        graph = validate_graph(ROOT)
        self.assertEqual(128, len(graph['feature_event']))
        self.assertGreaterEqual(len(graph['experiment']), 2198)
        index = load_config(ROOT / 'data/compatibility/legacy-index.json')
        self.assertEqual(1015, len(index['flags']))
        import hashlib
        for kind in ('flags', 'features', 'releases'):
            for row in index[kind]:
                self.assertEqual(row['sha256'], hashlib.sha256((ROOT / row['path']).read_bytes()).hexdigest())
        self.assertTrue(all(row['experiment_ids'] for row in index['flags']))

    def test_shared_entry_calls_both_real_collectors_and_retries(self):
        base = 'https://chromestatus.com/api/v0/features?num=100&start=0'
        def transport(url):
            self.assertEqual(base, url)
            return Response(url, json.dumps({'total_count': 1, 'features': [{'id': 123, 'name':'Example', 'summary':'Fact'}]}).encode())
        result = collect_sources(self.repo, self.private / 'run', kind='all', source_ids=['chrome-platform-status'],
            cutoff=NOW, transport=transport, chrome_provider=MemoryProvider(fixture_files(False)))
        self.assertEqual('complete', result['browser'][0]['status'])
        self.assertIsNotNone(result['chrome'])
        graph = validate_graph(self.repo)
        self.assertEqual(1, len(graph['feature']))
        self.assertTrue(graph['experiment_event'])
        before = {str(p.relative_to(self.repo)): p.read_bytes() for p in (self.repo / 'data').rglob('*.json')}
        retry = collect_sources(self.repo, self.private / 'run', kind='all', source_ids=['chrome-platform-status'],
            cutoff=NOW, transport=transport, resume=True, chrome_provider=MemoryProvider(fixture_files(False)))
        self.assertEqual(result['counts'], retry['counts'])
        self.assertEqual(before, {str(p.relative_to(self.repo)): p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})


if __name__ == '__main__':
    unittest.main()
