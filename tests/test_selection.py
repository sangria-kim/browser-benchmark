import copy
import json
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from pipeline.normalize import load_dataset, publish, validate_graph
from pipeline.selection import as_of, build_contexts, catalog_transitions, evaluate, input_hash, latest_assessments, load_rules, run
from pipeline.selection.core import decision, legacy_records
from schemas.validate import ContractError

ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-11-16T05:00:00Z'
LATER = '2026-11-17T05:00:00Z'


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / 'repo'
        self.private = self.base / 'private'
        self.repo.mkdir()
        shutil.copytree(ROOT / 'config', self.repo / 'config')
        self.data = json.loads((ROOT / 'schemas/tests/fixtures/valid-dataset.json').read_text())
        self.data.pop('assessment', None)
        self.data.pop('selected', None)
        self.data.pop('report', None)
        self.data.pop('export_manifest', None)
        self.paths = {'source_item':'data/source-items/chrome/test.json', 'feature':'data/catalog/features/test.json',
                      'feature_event':'data/events/test.json', 'experiment':'data/catalog/chrome-experiments/test.json',
                      'experiment_event':'data/experiment-events/test.json'}
        self.write()

    def write(self):
        for kind, path in self.paths.items():
            p = self.repo / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self.data[kind], indent=2) + '\n')

    def provider(self, context, rules):
        result = decision('selected', 'Synthetic fixture has an explicit change and benchmark.', priority='P2',
                          question='Can the same synthetic task be completed under each documented condition?',
                          readiness='conditional', revisit='Obtain supported builds.')
        result['evidence_source_item_ids'] = [s['source_item_id'] for s in context['sources']]
        result['benchmark'] = {'user_impact':'A synthetic task changes.', 'material_change':'The fixture documents a change.',
                               'steps':['Check support', 'Run the same synthetic task'], 'metrics':['Completion errors'],
                               'conditions':'Fixture only, not executed.', 'completion':'Record three repetitions.',
                               'evidence_quotes':['Synthetic test evidence.']}
        return result

    def execute(self, **kw):
        kw.setdefault('assessed_at', NOW)
        return run(self.repo, self.private, **kw)

    def test_structured_feature_and_flag_selected_without_source_mutation(self):
        before = {p: (self.repo / p).read_bytes() for p in self.paths.values()}
        result = self.execute(provider=self.provider, model_id='fixture-model-1')
        self.assertEqual((1, 1), tuple(len(result['selected'][k]['current']) for k in ('features','flags')))
        self.assertEqual(2, len(result['created']))
        self.assertEqual(before, {p: (self.repo / p).read_bytes() for p in self.paths.values()})
        validate_graph(self.repo)

    def test_rules_reassessment_deselect_reselect_and_asof(self):
        self.execute(provider=self.provider, model_id='fixture-model-1')
        rules = load_rules()
        rules['rule_version'] = 'test-v2'
        def exclude(context, rules):
            r = decision('excluded', 'Fixture benchmark no longer in research scope.', revisit='Review changed rules.')
            r['evidence_source_item_ids'] = [s['source_item_id'] for s in context['sources']]
            return r
        second = self.execute(assessed_at=LATER, rules=rules, provider=exclude, model_id='fixture-model-1')
        self.assertFalse(second['selected']['features']['current'])
        self.assertEqual('deselected', second['selected']['features']['history'][-1]['action'])
        third = self.execute(assessed_at='2026-11-18T05:00:00Z', provider=self.provider, model_id='fixture-model-1')
        self.assertEqual('reselected', third['selected']['features']['history'][-1]['action'])
        self.assertEqual(1, len(as_of(self.repo, NOW)['features']['current']))
        self.assertEqual(0, len(as_of(self.repo, LATER)['features']['current']))
        self.assertEqual(6, len(load_dataset(self.repo)['assessment']))

    def test_same_input_cache_and_observation_noise(self):
        first = self.execute(provider=self.provider, model_id='fixture-model-1')
        calls = []
        def forbidden(*args):
            calls.append(True)
            raise AssertionError('Cache miss')
        second = self.execute(assessed_at=LATER, provider=forbidden, model_id='fixture-model-1')
        self.assertEqual([], calls)
        self.assertEqual(2, second['cached'])
        self.assertEqual(first['selected'], second['selected'])
        context = next(iter(build_contexts(load_dataset(self.repo))[0].values()))
        changed = copy.deepcopy(context)
        changed['subject']['observed_at'] = LATER
        changed['subject']['source_revision'] = 'f'*40
        changed['sources'][0]['evidence']['line_start'] = 900
        self.assertEqual(input_hash(context, load_rules()), input_hash(changed, load_rules()))
        changed['sources'][0]['evidence']['content_sha256'] = 'f'*64
        self.assertNotEqual(input_hash(context, load_rules()), input_hash(changed, load_rules()))
        changed['subject']['summary'] = 'Actual changed evidence'
        self.assertNotEqual(input_hash(context, load_rules()), input_hash(changed, load_rules()))

    def test_failure_invalid_json_schema_reference_and_timeout_keep_last_good(self):
        self.execute(provider=self.provider, model_id='fixture-model-1')
        before = {k: (self.repo / ('data/selected/%s/current.json' % k)).read_bytes() for k in ('features','flags')}
        bad_outputs = ['{invalid', {'status':'excluded'}, dict(self.provider({'sources':self.data['source_item']}, {}), evidence_source_item_ids=['missing'])]
        for value in bad_outputs:
            result = self.execute(assessed_at=LATER, provider=lambda c,r:value, model_id='bad-model')
            self.assertEqual(2, len(result['failures']))
            self.assertEqual([], result['created'])
            self.assertEqual(before, {k: (self.repo / ('data/selected/%s/current.json' % k)).read_bytes() for k in before})
        def timeout(*args):
            raise TimeoutError('private provider message')
        self.assertEqual(2, len(self.execute(assessed_at=LATER, provider=timeout, model_id='bad-model')['failures']))
        retry = self.execute(assessed_at=LATER, provider=self.provider, model_id='bad-model')
        self.assertEqual(2, len(retry['created']))
        self.assertNotIn('private provider message', '\n'.join(p.read_text() for p in self.repo.rglob('*.json')))

    def test_initial_failure_does_not_publish_empty_selection(self):
        result = self.execute(provider=lambda c,r:'not json', model_id='fixture-model')
        self.assertEqual(2, len(result['failures']))
        self.assertFalse((self.repo / 'data/selected/features/current.json').exists())
        self.assertFalse(load_dataset(self.repo)['assessment'])

    def test_selected_model_requires_grounded_benchmark(self):
        def bad(context, rules):
            r = self.provider(context, rules)
            r['benchmark']['evidence_quotes'] = ['Invented official claim']
            return r
        result = self.execute(provider=bad, model_id='fixture-model')
        self.assertEqual(2, len(result['failures']))
        self.assertFalse(result['created'])

    def test_revisit_token_survives_next_run_and_retries(self):
        self.execute()
        second = self.execute(assessed_at=LATER, revisit={'event-test':'access-confirmed-1'})
        self.assertEqual(1, len(second['created']))
        third = self.execute(assessed_at='2026-11-18T05:00:00Z')
        self.assertEqual(0, len(third['created']))
        self.assertEqual(2, third['cached'])

    def test_assessment_and_dated_archive_and_history_are_immutable(self):
        self.execute(provider=self.provider, model_id='fixture-model')
        a = next(self.repo.glob('data/assessments/*/*.json'))
        snap = next(self.repo.glob('data/selected/history/*/*.json'))
        for path in (a, snap):
            value = json.loads(path.read_text())
            value['input_hash'] = 'f'*64
            with self.assertRaises(ContractError):
                publish(self.repo, {str(path.relative_to(self.repo)):value}, self.private)
        current = self.repo / 'data/selected/features/current.json'
        value = json.loads(current.read_text())
        value['history'] = []
        with self.assertRaises(ContractError):
            publish(self.repo, {str(current.relative_to(self.repo)):value}, self.private)

    def test_catalog_latest_event_does_not_duplicate_historical_card(self):
        self.execute(provider=self.provider, model_id='fixture-model')
        later = copy.deepcopy(self.data['feature_event'][0])
        later.update(event_id='event-second', observed_at=LATER, summary='A second fact')
        self.data['feature_event'].append(later)
        self.data['feature'][0]['event_ids'].append(later['event_id'])
        self.write()
        result = self.execute(assessed_at=LATER, provider=self.provider, model_id='fixture-model')
        self.assertEqual(1, len(result['selected']['features']['current']))
        self.assertEqual('event-second', result['selected']['features']['current'][0]['subject_id'])
        self.assertEqual(2, len(result['selected']['features']['history']))
        self.assertEqual('event-test', as_of(self.repo, NOW)['features']['current'][0]['subject_id'])
        transition = catalog_transitions(self.repo, NOW, LATER)[0]
        self.assertEqual('catalog_subject_replaced', transition['kind'])
        self.assertEqual('event-test', transition['previous']['subject_id'])
        self.assertEqual('event-second', transition['current']['subject_id'])

    def test_failed_new_owner_event_preserves_previous_card_and_historical_asof(self):
        self.execute(provider=self.provider, model_id='fixture-model')
        later = copy.deepcopy(self.data['feature_event'][0])
        later.update(event_id='event-second', observed_at=LATER, summary='A second fact')
        self.data['feature_event'].append(later)
        self.data['feature'][0]['event_ids'].append(later['event_id'])
        self.write()
        def timeout(context, rules):
            raise TimeoutError('New event evaluation unavailable')
        result = self.execute(assessed_at=LATER, provider=timeout, model_id='fixture-model')
        self.assertEqual(1, len(result['failures']))
        self.assertEqual('event-test', result['selected']['features']['current'][0]['subject_id'])
        self.assertEqual('event-test', as_of(self.repo, NOW)['features']['current'][0]['subject_id'])
        self.assertEqual([], catalog_transitions(self.repo, NOW, LATER))
        self.execute(assessed_at=LATER, provider=self.provider, model_id='fixture-model')
        self.assertEqual('event-second', as_of(self.repo, LATER)['features']['current'][0]['subject_id'])
        self.assertEqual('event-test', as_of(self.repo, NOW)['features']['current'][0]['subject_id'])

    def test_exclusion_keeps_all_source_records_and_pending_is_real_decision(self):
        before = (self.repo / self.paths['source_item']).read_bytes()
        self.data['feature_event'][0]['summary'] = 'Fixed various bugs and performance issues.'
        self.write()
        result = self.execute()
        self.assertEqual({'excluded','pending_verification'}, {a['status'] for a in result['created']})
        self.assertEqual(before, (self.repo / self.paths['source_item']).read_bytes())
        self.assertEqual(1, len(result['coverage']))

    def test_unseen_affirmative_user_tasks_select_without_new_profile(self):
        source = self.data['source_item'][0]
        for text in ('You can now group tabs into named workspaces.',
                     'Users can now resume interrupted downloads after reconnecting.',
                     'You can now filter saved passwords by account.',
                     'Websites now require permission before accessing local devices.',
                     'Users can now summarize pages using AI with source citations.'):
            source = copy.deepcopy(source)
            source.update(source_item_id='previously-unseen', summary=text)
            source['evidence']['excerpt'] = text
            context = {'subject_kind':'source_item', 'subject_id':source['source_item_id'],
                       'subject':source, 'sources':[source], 'catalog':None}
            result = evaluate(context, load_rules())
            self.assertEqual('selected', result['status'], text)
            self.assertEqual('conditional', result['benchmark_readiness'])
            self.assertTrue(any(r.startswith('Benchmark:') for r in result['reasons']))
            self.assertIn('Deterministic task-template', result['reasons'][0])

    def test_task_gates_reject_topic_keywords_negation_plans_and_missing_evidence(self):
        for text in ('Improved tabs passwords downloads and AI performance.',
                     'Users cannot now resume downloads.',
                     'Users can now resume downloads, but this is not yet available.',
                     'The proposal says users can now filter passwords.',
                     'You can now group tabs, a feature that will launch later.'):
            source = copy.deepcopy(self.data['source_item'][0])
            source['summary'] = source['evidence']['excerpt'] = text
            context = {'subject_kind':'source_item', 'subject_id':source['source_item_id'],
                       'subject':source, 'sources':[source], 'catalog':None}
            self.assertNotEqual('selected', evaluate(context, load_rules())['status'], text)
        source['summary'] = 'Users can now resume downloads.'
        source['evidence']['excerpt'] = 'A generic maintenance update.'
        self.assertNotEqual('selected', evaluate(context, load_rules())['status'])

    def test_real_default_profiles_are_source_only_conditional_not_launch_claims(self):
        contexts, _ = build_contexts(load_dataset(ROOT))
        flag_ids = {'actor-observe-screenshot-default', 'enable-parallel-downloading'}
        profiles = {c['subject']['after']['flag_id']: c for c in contexts.values()
                    if c['subject_kind'] == 'experiment_event'
                    and c['subject'].get('event_type') == 'baseline'
                    and (c['subject'].get('after') or {}).get('flag_id') in flag_ids}
        self.assertEqual(flag_ids, profiles.keys())
        rules = load_rules()
        for context in profiles.values():
            subject, catalog = context['subject'], context['catalog']
            scope = (catalog or {}).get('temporal_scope') or subject.get('temporal_scope')
            if scope and scope['status'] != 'in_period':
                self.assertEqual('excluded', evaluate(context, rules)['status'])
            # Exercise the retained source profile independently of today's window.
            unscoped = dict(context, subject=dict(subject), catalog=dict(catalog or {}))
            unscoped['subject'].pop('temporal_scope', None)
            unscoped['catalog'].pop('temporal_scope', None)
            result = evaluate(unscoped, rules)
            self.assertEqual('selected', result['status'])
            self.assertEqual('conditional', result['benchmark_readiness'])
            self.assertIn('Source-only baseline', ' '.join(result['reasons']))

    def test_real_legacy_judgments_and_whole_source_coverage(self):
        dataset = load_dataset(ROOT)
        dataset['assessment'] = []
        contexts, coverage = build_contexts(dataset)
        imported = legacy_records(ROOT, dataset, contexts, load_rules(), NOW)
        by_subject = {a['subject_id']:a for a in imported}
        events = {e['event_id']: e for e in dataset['feature_event']}
        counts = Counter()
        for path in (ROOT / 'data/event-revisions').glob('*/schema-v1.json'):
            old = json.loads(path.read_text())
            new = by_subject[old['event_id']]
            self.assertEqual(old['selection_status'], new['status'])
            self.assertEqual(old.get('comparison_question'), new['comparison_question'])
            self.assertEqual(old.get('priority'), new['priority'])
            self.assertEqual(old['selection_reason'], new['reasons'][0])
            self.assertEqual('legacy', new['evaluator'])
            self.assertEqual(events[old['event_id']]['source_item_ids'], new['evidence_source_item_ids'])
            self.assertIn(str(path.relative_to(ROOT)), new['input_revision'])
            counts[new['status']] += 1
        self.assertEqual({'selected':75,'watch':30,'pending_verification':13,'excluded':9}, dict(counts))
        recovered = by_subject['chrome-source-542d7914a86f0915025d40e699fa2de876d36e7d']
        self.assertEqual('watch', recovered['status'])
        self.assertIn('2026-11-source-index-2026-11-12.json', recovered['input_revision'])
        self.assertEqual({s['source_item_id'] for s in dataset['source_item']}, coverage.keys())
        self.assertTrue(all(k in contexts for k in coverage.values()))
        self.assertTrue(all(sid in {s['source_item_id'] for s in contexts[k]['sources']}
                            for sid, k in coverage.items()))
        standalone = {subject_id for kind, subject_id in contexts if kind == 'source_item'}
        self.assertEqual(standalone, {sid for sid, principal in coverage.items()
                                     if principal == ('source_item', sid)})
        pending_sources = set()
        for source in dataset['source_item']:
            if source['item_key'].startswith('flag-document:'):
                flag = source['item_key'].split(':', 1)[1]
                path = ROOT / 'experiments/chrome' / (flag + '.md')
                if path.exists() and 'PM 선별은 검증 대기입니다.' in path.read_text():
                    pending_sources.add(source['source_item_id'])
        imported_pending = {a['subject_id'] for a in imported
                            if a['subject_kind'] == 'source_item' and a['status'] == 'pending_verification'}
        self.assertTrue(pending_sources <= imported_pending)
        for assessment in imported:
            if assessment['subject_kind'] == 'source_item':
                self.assertIn(assessment['subject_id'], coverage)
                self.assertEqual([assessment['subject_id']], assessment['evidence_source_item_ids'])

    def test_shared_source_coverage_follows_latest_event(self):
        data = copy.deepcopy(self.data)
        data['experiment'], data['experiment_event'] = [], []
        later = dict(data['feature_event'][0], event_id='event-later', observed_at=LATER)
        data['feature_event'].append(later)
        data['feature'][0]['event_ids'].append(later['event_id'])
        _, coverage = build_contexts(data)
        self.assertEqual(('feature_event', 'event-later'), coverage['src-test'])
        data['feature_event'].reverse()
        _, reordered = build_contexts(data)
        self.assertEqual(coverage, reordered)

    def test_catalog_only_evidence_is_evaluated_hashed_and_order_stable(self):
        extra = copy.deepcopy(self.data['source_item'][0])
        extra.update(source_item_id='catalog-only', item_key='catalog-only')
        self.data['source_item'].append(extra)
        self.data['experiment'][0]['source_item_ids'].append('catalog-only')
        self.write()
        initial = self.execute(provider=self.provider, model_id='fixture-model')
        context, coverage = build_contexts(load_dataset(self.repo))
        principal = coverage['catalog-only']
        self.assertEqual(('experiment_event', 'exp-event-test'), principal)
        self.assertEqual(['catalog-only', 'src-test'], [s['source_item_id'] for s in context[principal]['sources']])
        first = next(a for a in initial['created'] if a['subject_id'] == principal[1])
        self.assertIn('catalog-only', first['evidence_source_item_ids'])
        old_hash = input_hash(context[principal], load_rules())
        self.data['source_item'].reverse()
        extra['evidence']['content_sha256'] = 'f' * 64
        extra['revisions'][-1]['evidence']['content_sha256'] = 'f' * 64
        extra['revisions'][-1]['content_sha256'] = 'f' * 64
        self.write()
        changed, _ = build_contexts(load_dataset(self.repo))
        self.assertNotEqual(old_hash, input_hash(changed[principal], load_rules()))
        seen = []
        def provider(c, rules):
            seen.extend(c['sources'])
            return self.provider(c, rules)
        result = self.execute(assessed_at=LATER, provider=provider, model_id='fixture-model')
        self.assertEqual(1, len(result['created']))
        self.assertEqual(first['assessment_id'], result['created'][0]['supersedes'])
        self.assertEqual('f' * 64, next(s for s in seen if s['source_item_id']=='catalog-only')['evidence']['content_sha256'])
        reordered = copy.deepcopy(load_dataset(self.repo))
        reordered['source_item'].reverse()
        reordered['experiment'][0]['source_item_ids'].reverse()
        same, _ = build_contexts(reordered)
        self.assertEqual(input_hash(changed[principal], load_rules()), input_hash(same[principal], load_rules()))

    def test_actual_catalog_only_source_content_change_invalidates_principal(self):
        data = load_dataset(ROOT)
        contexts, coverage = build_contexts(data)
        source = next(s for s in data['source_item'] if s['item_key'].startswith('flag-document:')
                      and coverage[s['source_item_id']][0] == 'experiment_event')
        principal = coverage[source['source_item_id']]
        before = input_hash(contexts[principal], load_rules())
        source['evidence']['content_sha256'] = 'f' * 64
        changed, _ = build_contexts(data)
        self.assertNotEqual(before, input_hash(changed[principal], load_rules()))

    def test_long_shared_heading_and_different_platform_do_not_merge_units(self):
        data = copy.deepcopy(self.data)
        data['experiment'], data['experiment_event'] = [], []
        source = data['source_item'][0]
        source['evidence']['section'] = 'A long shared release heading that contains more than forty characters'
        source['evidence']['excerpt'] = 'An exact full source statement about one concrete browser behavior.'
        second = copy.deepcopy(source)
        second.update(source_item_id='different-unit', item_key='different-unit')
        second['evidence']['excerpt'] = 'A completely different source statement under the same shared heading.'
        third = copy.deepcopy(source)
        third.update(source_item_id='android-unit', item_key='android-unit', platform=['Android'])
        data['source_item'].extend([second, third])
        contexts, coverage = build_contexts(data)
        self.assertEqual(('feature_event','event-test'), coverage['src-test'])
        self.assertEqual(('source_item','different-unit'), coverage['different-unit'])
        self.assertEqual(('source_item','android-unit'), coverage['android-unit'])
        self.assertEqual(3, len(contexts))
        # Different source units can share a truncated public prefix.
        second['evidence']['excerpt'] = source['evidence']['excerpt'] = 'x' * 220
        contexts, coverage = build_contexts(data)
        self.assertEqual(('source_item','different-unit'), coverage['different-unit'])


if __name__ == '__main__':
    unittest.main()
