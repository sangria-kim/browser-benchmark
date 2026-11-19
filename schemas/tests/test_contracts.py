import copy
import json
from pathlib import Path
import re
import unittest

from jsonschema import Draft202012Validator
from schemas.validate import (ContractError, KINDS, load_config, validate_dataset,
                              validate_record, validate_transition)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / 'fixtures'


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.dataset = load_config(FIXTURES / 'valid-dataset.json')

    def test_all_schema_documents_valid(self):
        for path in (ROOT / 'schemas').glob('*.schema.json'):
            with self.subTest(path=path):
                Draft202012Validator.check_schema(load_config(path))
        self.assertEqual(len(KINDS), len(list((ROOT / 'schemas').glob('*.schema.json'))))

    def test_linked_fixture(self):
        validate_dataset(self.dataset, {'chrome-releases'})

    def test_invalid_schema_cases(self):
        for case in load_config(FIXTURES / 'invalid-cases.json'):
            with self.subTest(case=case['reason']):
                value = copy.deepcopy(self.dataset[case['kind']][0])
                cursor = value
                parts = case['field'].split('.')
                for part in parts[:-1]:
                    cursor = cursor[int(part)] if isinstance(cursor, list) else cursor[part]
                key = int(parts[-1]) if isinstance(cursor, list) else parts[-1]
                cursor[key] = case['value']
                with self.assertRaises(ContractError):
                    validate_record(case['kind'], value)

    def test_configs_and_scope(self):
        config = load_config(ROOT / 'config/sources.yml')
        validate_record('sources_config', config)
        scope = load_config(ROOT / 'config/chrome-source-scope.yml')
        validate_record('chrome_scope_config', scope)
        self.assertEqual(len(set(config['browsers'])), 8)
        self.assertEqual(set(scope['experiment_kinds']), {'flag_entry', 'base_feature', 'command_switch'})
        self.assertEqual(scope['baseline']['historical_backfill_since'], '2026-01-01')
        for source in config['sources']:
            pattern = source['discovery']['include_url_pattern']
            if pattern:
                re.compile(pattern)
        self.assertIn('ios/chrome/browser/flags/about_flags.mm', scope['required_paths'])
        self.assertIn('local_checkout', scope['input_modes'])

    def test_existing_event_ids_are_preserved_by_compatibility_schema(self):
        paths = list((ROOT / 'data/events').glob('*.json'))
        # This baseline is intentionally explicit; migration must retain these IDs.
        self.assertGreaterEqual(len(paths), 127)
        ids = []
        for path in paths:
            record = load_config(path)
            validate_record('legacy_feature_event' if record['schema_version'] == 1 else 'feature_event', record)
            ids.append(record['event_id'])
        self.assertEqual(len(ids), len(set(ids)))

    def test_missing_reference_fails(self):
        self.dataset['feature_event'][0]['source_item_ids'] = ['missing']
        with self.assertRaisesRegex(ContractError, 'Missing source_item'):
            validate_dataset(self.dataset)

    def test_feature_revisions_must_belong_to_the_cited_source(self):
        feature = self.dataset['feature'][0]
        feature['source_revision_ids'] = {'src-test': ['rev-test']}
        validate_dataset(self.dataset)
        for pins in ({'src-test': ['missing']}, {'uncited': ['rev-test']}, {'src-test': []}):
            with self.subTest(pins=pins), self.assertRaises(ContractError):
                feature['source_revision_ids'] = pins
                validate_dataset(self.dataset)

    def test_feature_excerpt_requires_its_confirmed_revision(self):
        feature = self.dataset['feature'][0]
        feature['source_revision_ids'] = {'src-test': ['rev-test']}
        feature['source_revision_excerpts'] = {'rev-test': 'Synthetic test evidence.'}
        validate_dataset(self.dataset)
        feature['source_revision_excerpts']['other-revision'] = 'Unconfirmed quote.'
        with self.assertRaisesRegex(ContractError, 'excerpt must cite'):
            validate_dataset(self.dataset)

    def test_selected_requires_selected_assessment(self):
        self.dataset['assessment'][0]['status'] = 'excluded'
        with self.assertRaisesRegex(ContractError, 'Current selection'):
            validate_dataset(self.dataset)

    def test_history_remains_after_deselection(self):
        old = self.dataset['selected'][0]
        current = copy.deepcopy(old)
        current['current'] = []
        validate_transition('selected', old, current)
        current['history'] = []
        with self.assertRaisesRegex(ContractError, 'never be lost'):
            validate_transition('selected', old, current)

    def test_assessment_is_immutable(self):
        old = self.dataset['assessment'][0]
        current = copy.deepcopy(old)
        current['status'] = 'watch'
        with self.assertRaisesRegex(ContractError, 'immutable'):
            validate_transition('assessment', old, current)

    def test_supersedes_cannot_change_subject(self):
        old = copy.deepcopy(self.dataset['assessment'][0])
        old['assessment_id'] = 'assessment-old'
        old['subject_kind'] = 'source_item'
        old['subject_id'] = 'src-test'
        self.dataset['assessment'][0]['supersedes'] = old['assessment_id']
        self.dataset['assessment'].append(old)
        with self.assertRaisesRegex(ContractError, 'subject differs'):
            validate_dataset(self.dataset)

    def test_revision_history_cannot_be_rewritten(self):
        old = self.dataset['source_item'][0]
        current = copy.deepcopy(old)
        current['revisions'][0]['revision_id'] = 'other'
        with self.assertRaisesRegex(ContractError, 'unchanged prefix'):
            validate_transition('source_item', old, current)

    def test_unknown_operations_field_rejected(self):
        self.dataset['source_item'][0]['retry_count'] = 3
        with self.assertRaises(ContractError):
            validate_record('source_item', self.dataset['source_item'][0])

    def test_source_only_not_installed(self):
        self.dataset['experiment'][0]['installed_availability'] = 'observed'
        with self.assertRaisesRegex(ContractError, 'Source presence'):
            validate_record('experiment', self.dataset['experiment'][0])

    def test_source_registry_id_required(self):
        with self.assertRaisesRegex(ContractError, 'Unregistered'):
            validate_dataset(self.dataset, {'different-source'})

    def test_model_provenance_required(self):
        self.dataset['assessment'][0]['evaluator'] = 'model'
        with self.assertRaisesRegex(ContractError, 'model and prompt'):
            validate_record('assessment', self.dataset['assessment'][0])

    def test_selection_history_event_reference_must_exist(self):
        self.dataset['selected'][0]['history'][0]['event_ids'] = ['missing-event']
        with self.assertRaisesRegex(ContractError, 'Missing feature_event'):
            validate_dataset(self.dataset)

    def test_flags_cannot_select_feature_event_even_with_flag_links(self):
        for collection in ('current', 'history'):
            with self.subTest(collection=collection):
                data = copy.deepcopy(self.dataset)
                selection = data['selected'][0]
                selection['selection_kind'] = 'flags'
                selection['current' if collection == 'history' else 'history'] = []
                item = selection[collection][0]
                item['experiment_kind'] = 'flag_entry'
                item['catalog_id'] = 'chrome-flag-entry-test'
                item['event_ids'] = ['exp-event-test']
                with self.assertRaisesRegex(ContractError, 'subject kind'):
                    validate_dataset(data)

    def test_selection_catalog_and_event_must_have_subject_owner(self):
        for collection in ('current', 'history'):
            for link in ('catalog_id', 'event_ids'):
                with self.subTest(collection=collection, link=link):
                    data = copy.deepcopy(self.dataset)
                    other_feature = copy.deepcopy(data['feature'][0])
                    other_feature.update(feature_id='chrome-other', canonical_key='other', event_ids=['event-other'])
                    other_event = copy.deepcopy(data['feature_event'][0])
                    other_event.update(event_id='event-other', feature_id='chrome-other')
                    data['feature'].append(other_feature)
                    data['feature_event'].append(other_event)
                    item = data['selected'][0][collection][0]
                    item[link] = 'chrome-other' if link == 'catalog_id' else ['event-other']
                    with self.assertRaisesRegex(ContractError, 'owner differs'):
                        validate_dataset(data)

    def source_selection_dataset(self, is_flag=False):
        data = copy.deepcopy(self.dataset)
        data['report'] = []
        assessment = data['assessment'][0]
        assessment.update(subject_kind='source_item', subject_id='src-test')
        selection = data['selected'][0]
        selection['selection_kind'] = 'flags' if is_flag else 'features'
        if is_flag:
            source = data['source_item'][0]
            source.update(experiment_kind='flag_entry', item_type='flag_entry')
        for item in selection['current'] + selection['history']:
            item.update(subject_kind='source_item', subject_id='src-test',
                        experiment_kind='flag_entry' if is_flag else None,
                        catalog_id='chrome-flag-entry-test' if is_flag else 'chrome-test',
                        event_ids=['exp-event-test'] if is_flag else ['event-test'])
        return data

    def test_source_item_selection_requires_surface_and_evidence_links(self):
        for is_flag in (False, True):
            data = self.source_selection_dataset(is_flag)
            validate_dataset(data)
            for collection in ('current', 'history'):
                with self.subTest(is_flag=is_flag, collection=collection):
                    bad = copy.deepcopy(data)
                    bad['selected'][0][collection][0]['experiment_kind'] = 'command_switch' if is_flag else 'flag_entry'
                    with self.assertRaisesRegex(ContractError, 'kind differs'):
                        validate_dataset(bad)
            bad = copy.deepcopy(data)
            bad['selected'][0]['selection_kind'] = 'features' if is_flag else 'flags'
            with self.assertRaisesRegex(ContractError, 'source experiment kind'):
                validate_dataset(bad)
            for kind in (('experiment', 'experiment_event') if is_flag else ('feature', 'feature_event')):
                with self.subTest(kind=kind):
                    bad = copy.deepcopy(data)
                    other = copy.deepcopy(bad['source_item'][0])
                    other['source_item_id'] = 'source-other'
                    bad['source_item'].append(other)
                    bad[kind][0]['source_item_ids'] = ['source-other']
                    with self.assertRaisesRegex(ContractError, 'source-item evidence'):
                        validate_dataset(bad)

    def test_event_history_rejects_other_owner(self):
        for field in ('previous_event_id', 'correction_of'):
            with self.subTest(field=field):
                data = copy.deepcopy(self.dataset)
                other_feature = copy.deepcopy(data['feature'][0])
                other_feature.update(feature_id='chrome-other', canonical_key='other', event_ids=['event-other'])
                other_event = copy.deepcopy(data['feature_event'][0])
                other_event.update(event_id='event-other', feature_id='chrome-other')
                data['feature'].append(other_feature)
                data['feature_event'].append(other_event)
                data['feature_event'][0][field] = 'event-other'
                with self.assertRaisesRegex(ContractError, 'history owner mismatch'):
                    validate_dataset(data)

    def test_event_history_rejects_self_and_mixed_edge_cycles(self):
        for field in ('previous_event_id', 'correction_of'):
            with self.subTest(field=field):
                data = copy.deepcopy(self.dataset)
                data['feature_event'][0][field] = 'event-test'
                with self.assertRaisesRegex(ContractError, 'history cycle'):
                    validate_dataset(data)
        other = copy.deepcopy(self.dataset['feature_event'][0])
        other.update(event_id='event-other', correction_of='event-test')
        self.dataset['feature_event'].append(other)
        self.dataset['feature_event'][0]['previous_event_id'] = 'event-other'
        with self.assertRaisesRegex(ContractError, 'history cycle'):
            validate_dataset(self.dataset)

    def test_experiment_correction_rejects_other_owner_and_cycle(self):
        data = copy.deepcopy(self.dataset)
        data['experiment_event'][0]['correction_of'] = 'exp-event-test'
        with self.assertRaisesRegex(ContractError, 'history cycle'):
            validate_dataset(data)
        data = copy.deepcopy(self.dataset)
        other = copy.deepcopy(data['experiment'][0])
        other.update(experiment_id='experiment-other', canonical_key='flag_entry:other', event_ids=['exp-event-other'])
        event = copy.deepcopy(data['experiment_event'][0])
        event.update(event_id='exp-event-other', experiment_id='experiment-other')
        data['experiment'].append(other)
        data['experiment_event'].append(event)
        data['experiment_event'][0]['correction_of'] = 'exp-event-other'
        with self.assertRaisesRegex(ContractError, 'history owner mismatch'):
            validate_dataset(data)


    def test_report_cannot_cite_experiment_for_feature_subject(self):
        self.dataset['report'][0]['items'][0]['event_ids'] = ['exp-event-test']
        with self.assertRaisesRegex(ContractError, 'Missing feature_event'):
            validate_dataset(self.dataset)

    def test_report_cannot_cite_another_feature_owner(self):
        feature = copy.deepcopy(self.dataset['feature'][0])
        feature.update(feature_id='chrome-other', canonical_key='other', event_ids=['event-other'])
        event = copy.deepcopy(self.dataset['feature_event'][0])
        event.update(event_id='event-other', feature_id='chrome-other')
        self.dataset['feature'].append(feature)
        self.dataset['feature_event'].append(event)
        self.dataset['report'][0]['items'][0]['event_ids'] = ['event-other']
        with self.assertRaisesRegex(ContractError, 'owner differs'):
            validate_dataset(self.dataset)

    def test_report_events_must_belong_to_referenced_selection_change(self):
        event = copy.deepcopy(self.dataset['feature_event'][0])
        event['event_id'] = 'same-owner-other-event'
        self.dataset['feature_event'].append(event)
        self.dataset['report'][0]['items'][0]['event_ids'] = [event['event_id']]
        with self.assertRaisesRegex(ContractError, 'subset of selection change'):
            validate_dataset(self.dataset)
        self.dataset['selected'][0]['history'][0]['event_ids'].append(event['event_id'])
        # Reports may cite a subset: every cited event belongs to the same change.
        validate_dataset(self.dataset)


if __name__ == '__main__':
    unittest.main()
