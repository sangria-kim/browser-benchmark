import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('validator', ROOT / 'scripts/validate_whale_index.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

class WhaleIndexTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'releases/whale/4.0/items-android-backfill-2026-11-03.json').read_text())

    def test_complete_body(self):
        self.assertEqual(validator.validate(self.data), 13)

    def test_single_kind_complete_body(self):
        for kind, count in [('improvement', 11), ('fix', 2)]:
            with self.subTest(kind=kind):
                self.setUp()
                self.data['items'] = [item for item in self.data['items']
                                      if item['event_type'] == kind]
                self.data['expected_counts'] = {'improvement': 0, 'fix': 0}
                self.data['expected_counts'][kind] = count
                self.assertEqual(validator.validate(self.data), count)

    def test_unexpected_kind_rejected(self):
        self.data['items'][0]['event_type'] = 'other'
        with self.assertRaisesRegex(ValueError, 'invalid item kind'):
            validator.validate(self.data)

    def test_missing_expected_kind_rejected(self):
        del self.data['expected_counts']['fix']
        with self.assertRaisesRegex(ValueError, 'expected counts required'):
            validator.validate(self.data)

    def test_zero_expected_kind_with_items_rejected(self):
        self.data['expected_counts']['fix'] = 0
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            validator.validate(self.data)

    def test_missing_item_cannot_succeed(self):
        self.data['items'].pop()
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            validator.validate(self.data)

    def test_duplicate_item(self):
        self.data['items'][1]['item_id'] = self.data['items'][0]['item_id']
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            validator.validate(self.data)

    def test_ios_android_same_version(self):
        self.data['items'][0]['product'] = 'iOS'
        with self.assertRaisesRegex(ValueError, 'mixed product'):
            validator.validate(self.data)

    def test_backfill_is_not_new_report(self):
        self.data['items'][0]['selection_status'] = 'selected'
        with self.assertRaisesRegex(ValueError, 'historical'):
            validator.validate(self.data)

    def test_partial_is_allowed_without_success_claim(self):
        self.data['items'].pop()
        self.data['collection_status'] = 'partial'
        validator.validate(self.data)

    def test_empty_success_rejected(self):
        self.data['items'] = []
        with self.assertRaisesRegex(ValueError, 'empty'):
            validator.validate(self.data)

    def test_invalid_ordinal(self):
        self.data['items'][0]['source_item_number'] = 99
        with self.assertRaisesRegex(ValueError, 'noncontiguous'):
            validator.validate(self.data)

if __name__ == '__main__':
    unittest.main()
