"""Fixed-commit export and isolated internal-repository import integration tests."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import export_dataset as exporter
from pipeline.selection import run as select
from pipeline.reporting import run as report
from pipeline.selection.core import decision
from schemas.validate import ContractError

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = 'https://github.com/example/browser-data'


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='browser-export-test-', dir=str(Path(tempfile.gettempdir()).resolve()))
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'public'
        self.source.mkdir()
        for name in ('sources.yml', 'chrome-source-scope.yml', 'export-allowlist.json'):
            self.write('config/' + name, (ROOT / 'config' / name).read_bytes())
        self.write('docs/dataset-contract.md', '# Fixture contract\n')
        self.write('data/aliases/corrections.json', [])
        self.write('data/compatibility/legacy-index.json', {'index_version': 1, 'inventory_status': 'legacy', 'features': [], 'flags': [], 'releases': []})
        fixture = json.loads((ROOT / 'schemas/tests/fixtures/valid-dataset.json').read_text())
        paths = {'source_item': 'data/source-items/chrome/fixture.json', 'feature': 'data/catalog/features/catalog.json',
                 'feature_event': 'data/events/fixture.json', 'experiment': 'data/catalog/chrome-experiments/catalog.json',
                 'experiment_event': 'data/experiment-events/events.json'}
        for kind, name in paths.items():
            self.write(name, fixture[kind])
        def provider(context, rules):
            result = decision('selected', 'Synthetic benchmark.', priority='P2', question='Compare completion?', readiness='conditional', revisit='Review support.')
            result['evidence_source_item_ids'] = [s['source_item_id'] for s in context['sources']]
            result['benchmark'] = {'user_impact': 'Task changes.', 'material_change': 'New behavior.', 'steps': ['Run task'], 'metrics': ['Errors'], 'conditions': 'Fixture.', 'completion': 'Repeat.', 'evidence_quotes': ['Synthetic test evidence.']}
            return result
        select(self.source, self.base / 'selection-private', assessed_at='2026-11-16T05:00:00Z', provider=provider, model_id='fixture')
        report(self.source, self.base / 'selection-private', day='2026-11-16', cutoff='2026-11-16T06:00:00Z', collection='partial', evaluation='complete')
        self.write('reports/2026-11-16.md', '# Manual report\n[Evidence](../data/source-items/chrome/fixture.json)\n')
        # These exist in the public commit but must never enter a data package.
        for name in ('.github/workflows/dashboard.yml', 'dashboard/app.js', 'scripts/private.py', 'private/run.json', 'features/credentials.json'):
            self.write(name, 'PRIVATE NOT FOR EXPORT\n')
        self.git(self.source, 'init', '-q')
        self.commit()
        self.package = self.base / 'package'
        self.consumer = self.base / 'company'
        self.consumer.mkdir()
        self.git(self.consumer, 'init', '-q')
        self.owned = {'.github/workflows/company.yml': b'company workflow\n', 'dashboard/app.js': b'company UI\n', 'notes.md': b'company notes\n'}
        for name, value in self.owned.items():
            path = self.consumer / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value)
        self.git(self.consumer, 'add', '.')
        self.git(self.consumer, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Company initial')
        self.company_initial = self.git(self.consumer, 'rev-parse', 'HEAD')
        self.managed = self.consumer / 'vendor/browser-benchmark'
        exporter.initialize(self.managed)
        self.private = self.base / 'import-private'

    def git(self, root, *args):
        return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE).decode().strip()

    def write(self, name, value):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, (dict, list)):
            value = exporter.encoded(value)
        path.write_bytes(value.encode() if isinstance(value, str) else value)

    def commit(self):
        self.git(self.source, 'add', '.')
        self.git(self.source, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Public fixture')
        return self.git(self.source, 'rev-parse', 'HEAD')

    def export(self, path=None, **kw):
        return exporter.export(self.source, 'HEAD', path or self.package, source_repository=PUBLIC, **kw)

    def activate(self, result, package=None, **kw):
        return exporter.activate(package or self.package, self.managed, self.private, expected_commit=result['source_commit'], expected_manifest=result['manifest_sha256'], **kw)

    def rehash(self, package=None):
        root = package or self.package
        manifest = json.loads((root / 'manifest.json').read_text())
        for row in manifest['files']:
            path = root / row['path']
            if path.exists():
                raw = path.read_bytes()
                row.update(bytes=len(raw), sha256=exporter.digest(raw))
        (root / 'manifest.json').write_bytes(exporter.encoded(manifest))
        return exporter.digest((root / 'manifest.json').read_bytes())

    def test_full_and_selected_export_internal_commit_and_idempotence(self):
        result = self.export()
        self.assertEqual((1, 1), (result['records']['feature'], result['records']['experiment']))
        self.assertEqual(2, result['records']['selected'])
        for name in self.owned:
            self.assertFalse((self.package / name).exists())
        self.assertFalse((self.package / 'features/credentials.json').exists())
        self.assertEqual((self.source / 'reports/2026-11-16.md').read_bytes(), (self.package / 'reports/2026-11-16.md').read_bytes())
        self.assertTrue(self.activate(result)['activated'])
        pointer_before = (self.managed / 'current.json').read_bytes()
        self.assertFalse(self.activate(result)['activated'])
        self.assertEqual(pointer_before, (self.managed / 'current.json').read_bytes())
        self.assertTrue(exporter.resolve(self.managed).is_dir())
        for name, value in self.owned.items():
            self.assertEqual(value, (self.consumer / name).read_bytes())
        self.git(self.consumer, 'add', 'vendor/browser-benchmark')
        self.git(self.consumer, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'Import data')
        self.assertEqual(self.company_initial, self.git(self.consumer, 'rev-parse', 'HEAD^'))
        self.assertNotEqual(result['source_commit'], self.git(self.consumer, 'rev-parse', 'HEAD'))

    def test_dirty_tree_and_branch_movement_do_not_mix_source_commits(self):
        expected = self.git(self.source, 'rev-parse', 'HEAD')
        original = (self.source / 'reports/2026-11-16.md').read_bytes()
        def change(_):
            self.write('reports/2026-11-16.md', '# Later public commit\n')
            self.commit()
            self.write('reports/2026-11-16.md', 'UNCOMMITTED SECRET\n')
        result = self.export(after_pin=change)
        self.assertEqual(expected, result['source_commit'])
        self.assertEqual(original, (self.package / 'reports/2026-11-16.md').read_bytes())
        self.assertNotEqual(expected, self.git(self.source, 'rev-parse', 'HEAD'))

    def test_new_snapshot_deletions_do_not_delete_other_paths(self):
        first = self.export()
        self.activate(first)
        old = exporter.resolve(self.managed)
        (self.source / 'reports/2026-11-16.md').unlink()
        self.commit()
        package = self.base / 'second'
        second = self.export(package)
        self.activate(second, package)
        self.assertFalse((exporter.resolve(self.managed) / 'reports/2026-11-16.md').exists())
        self.assertTrue((old / 'reports/2026-11-16.md').exists())
        for name, value in self.owned.items():
            self.assertEqual(value, (self.consumer / name).read_bytes())

    def test_failed_activation_preserves_pointer_and_retry_succeeds(self):
        first = self.export()
        self.activate(first)
        before = (self.managed / 'current.json').read_bytes()
        self.write('reports/2026-11-16.md', '# Next revision\n')
        self.commit()
        package = self.base / 'second'
        second = self.export(package)
        def fail(*_):
            raise OSError('Injected pointer replacement failure')
        with self.assertRaises(OSError):
            self.activate(second, package, replace=fail)
        self.assertEqual(before, (self.managed / 'current.json').read_bytes())
        self.assertTrue(self.activate(second, package)['activated'])

    def test_missing_and_excluded_relative_links_reject_export(self):
        for target in ('../missing.md', '../dashboard/app.js', '../../../../escape'):
            self.write('reports/2026-11-16.md', '[Broken](' + target + ')\n')
            self.commit()
            with self.assertRaisesRegex(ContractError, 'relative link'):
                self.export()
            self.assertFalse(self.package.exists())

    def test_allowed_path_symlink_and_executable_are_rejected(self):
        target = self.source / 'reports/2026-11-16.md'
        target.unlink()
        target.symlink_to('../dashboard/app.js')
        self.commit()
        with self.assertRaisesRegex(ContractError, 'regular data'):
            self.export()
        target.unlink()
        target.write_text('# File\n')
        target.chmod(0o755)
        self.commit()
        with self.assertRaisesRegex(ContractError, 'regular data'):
            self.export()

    def test_manifest_hash_version_traversal_and_extra_files(self):
        result = self.export()
        pristine = (self.package / 'manifest.json').read_bytes()
        for mutation in ('version', 'traversal', 'wrong_kind', 'duplicate', 'sha', 'credentials'):
            value = json.loads(pristine)
            if mutation == 'version': value['contract_version'] = '9.0'
            if mutation == 'traversal': value['files'][0]['path'] = '../escape.json'
            if mutation == 'wrong_kind': value['files'][0]['data_kind'] = 'reports'
            if mutation == 'duplicate': value['files'].append(value['files'][0])
            if mutation == 'sha': value['source_commit'] = '0' * 40
            if mutation == 'credentials': value['source_repository'] = 'https://user:password@example.invalid/repository'
            raw = exporter.encoded(value)
            (self.package / 'manifest.json').write_bytes(raw)
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):
                exporter.verify(self.package, expected_commit=result['source_commit'], expected_manifest=exporter.digest(raw))
        (self.package / 'manifest.json').write_bytes(pristine)
        (self.package / 'unlisted.json').write_text('{}')
        with self.assertRaisesRegex(ContractError, 'unlisted'):
            self.activate(result)
        (self.package / 'unlisted.json').unlink()
        with self.assertRaisesRegex(ContractError, 'trusted handoff'):
            exporter.verify(self.package, expected_commit=result['source_commit'], expected_manifest='0' * 64)

    def test_package_symlink_and_missing_file_preserve_last_good(self):
        result = self.export()
        self.activate(result)
        before = (self.managed / 'current.json').read_bytes()
        path = self.package / 'reports/2026-11-16.md'
        path.unlink()
        with self.assertRaises(ContractError): self.activate(result)
        path.symlink_to(self.consumer / 'notes.md')
        with self.assertRaises(ContractError): self.activate(result)
        self.assertEqual(before, (self.managed / 'current.json').read_bytes())

    def test_forged_hashes_do_not_bypass_schema_or_reference_validation(self):
        result = self.export()
        path = self.package / 'data/events/fixture.json'
        pristine = path.read_bytes()
        for field, value in [('feature_id', 'missing'), ('schema_version', 99)]:
            rows = json.loads(pristine)
            rows[0][field] = value
            path.write_bytes(exporter.encoded(rows))
            forged = self.rehash()
            with self.subTest(field=field), self.assertRaises(ContractError):
                exporter.verify(self.package, expected_commit=result['source_commit'], expected_manifest=forged)
        path.write_bytes(pristine)

    def test_frozen_report_and_archive_refs_are_validated_separately(self):
        report(self.source, self.base / 'selection-private', day='2026-11-16', cutoff='2026-11-16T07:00:00Z', collection='complete', evaluation='complete')
        self.commit()
        result = self.export()
        self.assertEqual(1, result['records']['report'])
        path = self.package / 'data/reports/history/2026-11-16/revision-1.json'
        value = json.loads(path.read_text())
        value['items'][0]['evidence'][0]['revision_id'] = 'missing-revision'
        path.write_bytes(exporter.encoded(value))
        forged = self.rehash()
        with self.assertRaises(ContractError):
            exporter.verify(self.package, expected_commit=result['source_commit'], expected_manifest=forged)

    def test_user_owned_root_and_unsafe_pointer_are_rejected(self):
        with self.assertRaises(ContractError): exporter.initialize(self.consumer)
        result = self.export()
        with self.assertRaises(ContractError):
            exporter.activate(self.package, self.consumer, self.private, expected_commit=result['source_commit'], expected_manifest=result['manifest_sha256'])
        self.activate(result)
        pointer = json.loads((self.managed / 'current.json').read_text())
        pointer['snapshot'] = '../../dashboard'
        (self.managed / 'current.json').write_bytes(exporter.encoded(pointer))
        with self.assertRaises(ContractError): exporter.resolve(self.managed)
        with self.assertRaises(ContractError): self.activate(result)

    def test_forged_manifest_cannot_allow_execution_code(self):
        result = self.export()
        name = '.github/workflows/evil.yml'
        target = self.package / name
        target.parent.mkdir(parents=True)
        target.write_text('workflow')
        manifest = json.loads((self.package / 'manifest.json').read_text())
        manifest['files'].append(dict(path=name, data_kind='documentation', bytes=8, sha256=exporter.digest(b'workflow')))
        raw = exporter.encoded(manifest)
        (self.package / 'manifest.json').write_bytes(raw)
        with self.assertRaises(ContractError):
            exporter.verify(self.package, expected_commit=result['source_commit'], expected_manifest=exporter.digest(raw))

    def test_frozen_report_rejects_rehashed_judgment(self):
        result = self.export()
        path = self.package / 'data/reports/history/2026-11-16/revision-1.json'
        value = json.loads(path.read_text())
        value['items'][0]['details']['reasons'] = ['Rewritten private judgment']
        path.write_bytes(exporter.encoded(value))
        forged = self.rehash()
        with self.assertRaisesRegex(ContractError, 'frozen assessment'):
            exporter.verify(self.package, expected_commit=result['source_commit'], expected_manifest=forged)

    def test_staged_copy_is_checked_again_before_activation(self):
        from unittest.mock import patch
        result = self.export()
        original = exporter.verify
        checks = []
        def verify_with_mutation(package, **kw):
            checks.append(str(package))
            if len(checks) == 2:
                (Path(package) / 'reports/2026-11-16.md').write_text('Changed during staging')
            return original(package, **kw)
        with patch.object(exporter, 'verify', side_effect=verify_with_mutation):
            with self.assertRaises(ContractError): self.activate(result)
        self.assertFalse((self.managed / 'current.json').exists())

    def test_legacy_monthly_event_provenance_hash_and_fragment(self):
        from pipeline.selection.core import digest
        path = next((self.source / 'data/assessments/feature_event').glob('*.json'))
        assessment = json.loads(path.read_text())
        original = {'event_id': assessment['subject_id'], 'summary': 'Original recovered event'}
        monthly = 'experiments/chrome/monthly/2026-11-source-index-2026-11-12.json'
        self.write(monthly, {'events': [original]})
        assessment['input_revision'] = monthly + '#event_id=' + assessment['subject_id'] + ':sha256:' + digest(original)
        path.write_bytes(exporter.encoded(assessment))
        # Frozen report snapshots keep the same assessment fields and identity.
        self.commit()
        result = self.export()
        target = self.package / monthly
        target.write_bytes(exporter.encoded({'events': [dict(original, summary='Changed evidence')]}))
        forged = self.rehash()
        with self.assertRaisesRegex(ContractError, 'provenance hash'):
            exporter.verify(self.package, expected_commit=result['source_commit'], expected_manifest=forged)

    def test_report_rejects_snapshot_from_another_cutoff(self):
        result = self.export()
        path = self.package / 'data/reports/history/2026-11-16/revision-1.json'
        value = json.loads(path.read_text())
        value['cutoff'] = '2026-11-16T07:00:00Z'
        path.write_bytes(exporter.encoded(value))
        forged = self.rehash()
        with self.assertRaisesRegex(ContractError, 'snapshot kind/cutoff'):
            exporter.verify(self.package, expected_commit=result['source_commit'], expected_manifest=forged)

    def test_credentials_inside_allowed_data_are_rejected(self):
        self.write('reports/2026-11-16.md', '-----BEGIN PRIVATE KEY-----\nfixture\n')
        self.commit()
        with self.assertRaisesRegex(ContractError, 'Credential'):
            self.export()


if __name__ == '__main__':
    unittest.main()
