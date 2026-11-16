"""Daily transaction boundaries, crash recovery and real fixture integration."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pipeline import run_daily as daily

ROOT = Path(__file__).resolve().parents[1]


def options():
    return dict(kind='browser', sources=['firefox-beta'], origin='baseline',
        collection_cutoff='2026-11-16T06:00:00Z', previous_cutoff=None,
        sample_paths=None, max_files=2, max_trees=2, model_id=None,
        assessed_at='2026-11-16T06:00:00Z', report_cutoff='2026-11-16T06:00:00Z', day='2026-11-16')


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'repo'
        self.root.mkdir()
        self.private = self.base / 'private'
        (self.root / 'data').mkdir()
        (self.root / 'data/value.json').write_text('[1]\n')
        daily.git(self.root, 'init', '-q')
        daily.commit_candidate(self.root)
        self.calls = []

    def execute(self, stage, root, run_dir, opts):
        self.calls.append(stage)
        if stage == 'collect':
            (root / 'data/value.json').write_text('[2]\n')
        return {'complete': True, 'stage': stage}

    def run_candidate(self, **kw):
        return daily.run(self.root, self.private, 'fixture', options=options(), execute=self.execute, **kw)

    def test_shadow_resume_and_publish_same_candidate(self):
        before = daily.inventory(self.root)
        state = self.run_candidate()
        self.assertEqual('complete', state['status'])
        self.assertEqual(before, daily.inventory(self.root))
        self.assertEqual(list(daily.STAGES), self.calls)
        state = self.run_candidate(resume=True, publish=True)
        self.assertEqual(list(daily.STAGES), self.calls)
        self.assertTrue(state['published'])
        self.assertEqual('[2]\n', (self.root / 'data/value.json').read_text())
        self.assertEqual(state, self.run_candidate(resume=True, publish=True))

    def test_failed_stage_restarts_from_previous_snapshot(self):
        real = self.execute
        def fail(stage, root, run_dir, opts):
            if stage == 'select':
                (root / 'data/value.json').write_text('broken')
                raise RuntimeError('interrupt')
            return real(stage, root, run_dir, opts)
        with self.assertRaises(RuntimeError):
            daily.run(self.root, self.private, 'fixture', options=options(), execute=fail)
        self.assertEqual('[1]\n', (self.root / 'data/value.json').read_text())
        state = self.run_candidate(resume=True)
        self.assertEqual('complete', state['status'])
        self.assertEqual(1, self.calls.count('collect'))
        self.assertEqual('[2]\n', (self.private / 'fixture/select/data/value.json').read_text())

    def test_partial_and_assessment_failure_keep_public_last_good(self):
        for stage_to_fail in ('collect', 'select'):
            with self.subTest(stage=stage_to_fail):
                private = self.base / stage_to_fail
                def partial(stage, root, run_dir, opts):
                    result = self.execute(stage, root, run_dir, opts)
                    result['complete'] = stage != stage_to_fail
                    return result
                result = daily.run(self.root, private, 'partial', options=options(), execute=partial)
                self.assertEqual('partial', result['status'])
                self.assertIn('report', result['stages'])
                self.assertEqual('[1]\n', (self.root / 'data/value.json').read_text())
                with self.assertRaises(ValueError):
                    daily.run(self.root, private, 'partial', resume=True, publish=True, execute=partial)

    def test_explicit_partial_publish_keeps_partial_status(self):
        def partial(stage, root, run_dir, opts):
            return dict(self.execute(stage, root, run_dir, opts), complete=False)
        state = daily.run(self.root, self.private, 'fixture', options=options(), execute=partial,
                          publish=True, allow_partial=True)
        self.assertTrue(state['published'])
        self.assertEqual('partial', state['status'])

    def test_retry_collection_keeps_base_but_rebuilds_downstream(self):
        self.run_candidate()
        self.run_candidate(resume=True, retry_collection=True)
        self.assertEqual(list(daily.STAGES) * 2, self.calls)
        self.assertEqual('[1]\n', (self.private / 'fixture/base/data/value.json').read_text())

    def test_dirty_and_long_running_concurrent_edit_refused(self):
        (self.root / 'data/value.json').write_text('[3]\n')
        with self.assertRaisesRegex(ValueError, 'clean starting'):
            self.run_candidate(publish=True)
        shutil.rmtree(self.private)
        daily.commit_candidate(self.root)
        self.run_candidate()
        (self.root / 'data/value.json').write_text('[4]\n')
        with self.assertRaisesRegex(RuntimeError, 'Concurrent'):
            self.run_candidate(resume=True, publish=True)
        self.assertEqual('[4]\n', (self.root / 'data/value.json').read_text())

    def test_concurrent_lock_is_shared_across_private_directories(self):
        with daily.run_lock(self.root):
            with self.assertRaisesRegex(RuntimeError, 'lock'):
                daily.run(self.root, self.base / 'other-private', 'other', options=options(), execute=self.execute)

    def test_snapshot_and_private_input_tampering_refused(self):
        self.run_candidate()
        (self.private / 'fixture/base/data/value.json').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'base snapshot'):
            self.run_candidate(resume=True)

    def test_resume_rejects_added_response_or_decision_files(self):
        def interrupt(stage, root, run_dir, opts):
            raise KeyboardInterrupt()
        for filename in ('responses.json', 'decisions.json'):
            with self.subTest(filename=filename):
                private = self.base / filename
                with self.assertRaises(KeyboardInterrupt):
                    daily.run(self.root, private, 'pinned', options=options(), execute=interrupt)
                run_dir = private / 'pinned'
                self.assertEqual({}, daily.read(run_dir / 'state.json')['private_inputs'])
                daily.durable(run_dir / 'inputs' / filename, b'{}')
                with self.assertRaisesRegex(ValueError, 'private input inventory'):
                    daily.run(self.root, private, 'pinned', resume=True, execute=self.execute)
                self.assertEqual([], self.calls)

    def test_resume_rejects_modified_or_missing_private_input(self):
        source = self.base / 'responses.json'
        source.write_text('{}')
        def interrupt(stage, root, run_dir, opts):
            raise KeyboardInterrupt()
        for change in ('modified', 'missing'):
            with self.subTest(change=change):
                private = self.base / change
                with self.assertRaises(KeyboardInterrupt):
                    daily.run(self.root, private, 'pinned', options=options(),
                              input_files={'responses': source}, execute=interrupt)
                target = private / 'pinned/inputs/responses.json'
                if change == 'modified':
                    target.write_text('{"changed": true}')
                else:
                    target.unlink()
                with self.assertRaisesRegex(ValueError, 'private input inventory'):
                    daily.run(self.root, private, 'pinned', resume=True, execute=self.execute)
                self.assertEqual([], self.calls)

    def test_private_input_links_and_nonregular_entries_are_rejected(self):
        directory = self.base / 'inputs'
        directory.mkdir()
        source = self.base / 'external.json'
        source.write_text('{}')
        target = directory / 'responses.json'
        target.symlink_to(source)
        with self.assertRaisesRegex(ValueError, 'Nonregular or linked'):
            daily.private_input_inventory(directory)
        target.unlink()
        target.mkdir()
        with self.assertRaisesRegex(ValueError, 'Nonregular or linked'):
            daily.private_input_inventory(directory)
        target.rmdir()
        os.mkfifo(target)
        with self.assertRaisesRegex(ValueError, 'Nonregular or linked'):
            daily.private_input_inventory(directory)
        target.unlink()
        link = self.base / 'linked-inputs'
        link.symlink_to(directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'Linked private input directory'):
            daily.private_input_inventory(link)

    def test_worker_and_stage_boundary_reject_late_private_input(self):
        run_dir = self.base / 'worker'
        daily.durable(run_dir / 'state.json', daily.encoded({'private_inputs': {}}))
        daily.durable(run_dir / 'inputs/decisions.json', b'{}')
        with self.assertRaisesRegex(ValueError, 'private input inventory'):
            daily.worker('select', self.root, run_dir, options())
        def inject(stage, root, run_dir, opts):
            result = self.execute(stage, root, run_dir, opts)
            daily.durable(run_dir / 'inputs/decisions.json', b'{}')
            return result
        with self.assertRaisesRegex(ValueError, 'private input inventory'):
            daily.run(self.root, self.private, 'late', options=options(), execute=inject)
        self.assertEqual(['collect'], self.calls)

    def test_publication_error_rolls_back_and_crash_recovers(self):
        state = self.run_candidate()
        run_dir = self.private / 'fixture'
        def error(path, data):
            daily.durable(path, data)
            raise OSError('failed after replacement')
        with self.assertRaises(OSError):
            daily.publish_candidate(self.root, run_dir, state, replace=error)
        self.assertEqual('[1]\n', (self.root / 'data/value.json').read_text())
        def crash(path, data):
            daily.durable(path, data)
            raise KeyboardInterrupt('process death')
        with self.assertRaises(KeyboardInterrupt):
            daily.publish_candidate(self.root, run_dir, state, replace=crash)
        self.assertEqual('[2]\n', (self.root / 'data/value.json').read_text())
        self.assertTrue(daily.recover_publication(self.root, run_dir))
        self.assertEqual('[1]\n', (self.root / 'data/value.json').read_text())

    def test_crash_journal_detected_from_other_private_root(self):
        state = self.run_candidate()
        run_dir = self.private / 'fixture'
        with daily.run_lock(self.root) as lock:
            lock.write(json.dumps({'run_dir': str(run_dir)})); lock.flush()
        def crash(path, data):
            daily.durable(path, data)
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            daily.publish_candidate(self.root, run_dir, state, replace=crash)
        daily.run(self.root, self.base / 'new-state', 'new', options=options(), execute=self.execute)
        self.assertEqual('[1]\n', (self.root / 'data/value.json').read_text())

    def test_unrelated_edit_during_publication_rolls_back_only_our_outputs(self):
        state = self.run_candidate()
        def edit(path, data):
            daily.durable(path, data)
            (self.root / 'data/user.json').write_text('user work')
        with self.assertRaisesRegex(RuntimeError, 'during publication'):
            daily.publish_candidate(self.root, self.private / 'fixture', state, replace=edit)
        self.assertEqual('[1]\n', (self.root / 'data/value.json').read_text())
        self.assertEqual('user work', (self.root / 'data/user.json').read_text())

    def test_recovery_rejects_tampered_journal_and_backup(self):
        state = self.run_candidate()
        directory = self.private / 'fixture'
        def crash(path, data):
            daily.durable(path, data)
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            daily.publish_candidate(self.root, directory, state, replace=crash)
        journal = daily.read(directory / 'publication.json')
        changed = copy.deepcopy(journal)
        changed['files']['../outside'] = changed['files'].pop('data/value.json')
        daily.durable(directory / 'publication.json', daily.encoded(changed))
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            daily.recover_publication(self.root, directory)
        daily.durable(directory / 'publication.json', daily.encoded(journal))
        (directory / 'backup/data/value.json').write_text('corrupt backup')
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            daily.recover_publication(self.root, directory)
        self.assertEqual('[2]\n', (self.root / 'data/value.json').read_text())

    def test_recovery_refuses_to_overwrite_unrelated_edit(self):
        state = self.run_candidate()
        def crash(path, data):
            daily.durable(path, data)
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            daily.publish_candidate(self.root, self.private / 'fixture', state, replace=crash)
        (self.root / 'data/value.json').write_text('user edit')
        with self.assertRaisesRegex(RuntimeError, 'Recovery conflict'):
            daily.recover_publication(self.root, self.private / 'fixture')
        self.assertEqual('user edit', (self.root / 'data/value.json').read_text())

    def test_real_fixture_collection_selection_report_build_export(self):
        # Reuse the minimal contract fixture, but exercise actual subprocess
        # stage code, transport parsing, normalization, evaluation and exporter.
        shutil.rmtree(self.root / 'data')
        for name in ('pipeline', 'scripts', 'schemas', 'rules', 'config', 'dashboard'):
            shutil.copytree(ROOT / name, self.root / name, ignore=shutil.ignore_patterns('__pycache__'))
        for doc in (self.root / 'pipeline').rglob('README.md'):
            doc.write_text('# Fixture documentation\n')
        (self.root / 'dashboard/catalog.json').write_text('{"events":{}}')
        (self.root / 'docs').mkdir()
        (self.root / 'docs/dataset-contract.md').write_text('# Fixture\n')
        fixture = json.loads((ROOT / 'schemas/tests/fixtures/valid-dataset.json').read_text())
        paths = {'source_item':'data/source-items/chrome/fixture.json', 'feature':'data/catalog/features/catalog.json',
                 'feature_event':'data/events/event-test.json', 'experiment':'data/catalog/chrome-experiments/catalog.json',
                 'experiment_event':'data/experiment-events/events.json'}
        for kind, path in paths.items():
            daily.durable(self.root / path, daily.encoded(fixture[kind][0] if kind == 'feature_event' else fixture[kind]))
        source = next(s for s in json.loads((ROOT / 'config/sources.yml').read_text())['sources'] if s['source_id'] == 'firefox-beta')
        responses = self.base / 'responses.json'
        responses.write_text(json.dumps({source['url']: {'body': (ROOT / 'tests/fixtures/browser/releases.html').read_text()}}))
        daily.commit_candidate(self.root)
        result = daily.run(self.root, self.private, 'real', options=options(), input_files={'responses':responses})
        self.assertEqual('partial', result['status']) # A bounded source is not full registered coverage.
        validation = result['stages']['validate']['result']
        self.assertGreater(validation['counts']['source_item'], 1)
        self.assertGreaterEqual(validation['counts']['assessment'], 2)
        self.assertEqual(1, validation['counts']['report'])
        self.assertIn('synthetic', validation['provenance'])
        manifest = daily.read(self.private / 'real/validation-export/manifest.json')
        self.assertEqual(validation['export']['source_commit'], manifest['source_commit'])
        snapshot = daily.inventory(self.private / 'real/report')
        again = daily.run(self.root, self.private, 'real', resume=True)
        self.assertEqual(result, again)
        self.assertEqual(snapshot, daily.inventory(self.private / 'real/report'))
        self.assertFalse((self.root / 'data/reports').exists())
        # Accept the fixture candidate in its isolated repository, then observe
        # identical bytes again and finally a real evidence text change.
        daily.run(self.root, self.private, 'real', resume=True, publish=True, allow_partial=True)
        daily.commit_candidate(self.root)
        second = daily.run(self.root, self.private, 'same-bytes', options=options(), input_files={'responses':responses})
        self.assertEqual(0, second['stages']['select']['result']['created'])
        self.assertEqual(validation['counts']['feature_event'], second['stages']['validate']['result']['counts']['feature_event'])
        response_map = json.loads(responses.read_text())
        response_map[source['url']]['body'] = response_map[source['url']]['body'].replace('Feature one', 'Feature one changed')
        # Ensure this fixture changes actual response content, not only its time.
        response_map[source['url']]['body'] += '<p>Additional evidence.</p>'
        responses.write_text(json.dumps(response_map))
        changed = daily.run(self.root, self.private, 'changed-bytes', options=options(), input_files={'responses':responses})
        self.assertGreater(changed['stages']['select']['result']['created'], 0)
        self.assertEqual(validation['counts']['feature_event'], changed['stages']['validate']['result']['counts']['feature_event'])
