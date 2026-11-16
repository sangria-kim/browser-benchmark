"""Collector-to-selection/report regressions for item facts and raw provenance."""
import copy
import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from test_browser_collectors import source, response
from pipeline.collectors.browser import BrowserCollector
from pipeline.normalize import validate_graph
from pipeline.selection import run as select
from pipeline.selection.core import decision, semantic, digest
from pipeline.reporting import run as report, render
from pipeline.reporting.core import judged_subject

ROOT = Path(__file__).resolve().parents[1]


class BrowserRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo, self.private = self.base / 'repo', self.base / 'private'
        shutil.copytree(ROOT / 'config', self.repo / 'config')
        self.source = source('edge-stable')
        self.path = self.repo / 'data/source-items/edge/edge-stable.json'
        self.day = 16

    def collect(self, *, version='150.0', sibling='Sibling text.', suffix='', text='Synthetic test evidence.', channel=None, platform=None):
        html = f'<title>Chrome {version}</title><div class="content"><h2 id="changes">Changes</h2><p id="one">{text}</p><p id="two">{sibling}</p></div>{suffix}'
        config = copy.deepcopy(self.source)
        if channel: config['channels'] = [channel]
        if platform: config['platforms'] = [platform]
        with patch('pipeline.collectors.browser.collector.datetime', wraps=datetime) as clock:
            clock.now.return_value = datetime.fromisoformat(f'2026-11-{self.day}T04:00:00+00:00')
            state = BrowserCollector(self.repo, self.private, lambda url: response(url, html)).collect(config, f'2026-11-{self.day}T06:00:00Z', '2026-10-28')
        self.assertEqual('complete', state['status'])
        return json.loads(self.path.read_text())

    def provider(self, context, rules):
        result = decision('selected', 'Synthetic benchmark.', priority='P2', question='Compare task?', readiness='conditional')
        result['evidence_source_item_ids'] = [s['source_item_id'] for s in context['sources']]
        result['benchmark'] = dict(user_impact='Task changes.', material_change='New behavior.', steps=['Run task'], metrics=['Errors'], conditions='Fixture.', completion='Repeat.', evidence_quotes=[context['subject']['summary']])
        return result

    def select(self):
        result = select(self.repo, self.private, assessed_at=f'2026-11-{self.day}T05:00:00Z', provider=self.provider, model_id='fixture')
        self.assertEqual([], result['failures'])
        return result

    def report(self, day=None):
        day = day or self.day
        return report(self.repo, self.private, day=f'2026-11-{day}', cutoff=f'2026-11-{day}T06:00:00Z', collection='complete', evaluation='complete')

    def test_document_comment_and_sibling_changes_do_not_reassess_unchanged_item(self):
        original = self.collect()
        self.select()
        old_report = self.report()['report']
        old_markdown = render(old_report)
        self.day = 17
        comment = self.collect(suffix='<!-- unrelated page comment -->')
        self.assertNotEqual(original[0]['evidence']['content_sha256'], comment[0]['evidence']['content_sha256'])
        self.assertEqual(2, self.select()['cached'])
        self.assertEqual('no_changes', self.report()['report']['outcome'])
        self.day = 18
        changed = self.collect(sibling='Changed sibling text.', suffix='<!-- unrelated page comment -->')
        result = self.select()
        self.assertEqual((1, 1), (result['cached'], len(result['created'])))
        one = next(r for r in changed if r['item_key'] == 'one')
        self.assertNotEqual(one['source_item_id'], result['created'][0]['subject_id'])
        self.assertEqual(1, len(self.report()['report']['items']))
        self.day = 19
        self.collect(sibling='Changed sibling text.', text='Changed own text.')
        result = self.select()
        self.assertEqual((1, 1), (result['cached'], len(result['created'])))
        self.assertEqual(one['source_item_id'], result['created'][0]['subject_id'])
        self.assertFalse(self.report(day=16)['created'])
        self.assertEqual(old_markdown, (self.repo / old_report['markdown_path']).read_text())
        validate_graph(self.repo)

    def test_metadata_change_restores_old_assessed_facts_and_report(self):
        original = self.collect()
        selected = self.select()
        old_report = self.report()['report']
        self.day = 17
        current = self.collect(version='151.0', channel='beta', platform='linux')
        self.select()
        self.report()
        by_id = {r['source_item_id']: r for r in current}
        for assessment in selected['created']:
            restored, _ = judged_subject(self.repo, by_id[assessment['subject_id']], assessment, str(self.path))
            old = next(r for r in original if r['source_item_id'] == assessment['subject_id'])
            for field in ('version', 'channel', 'platform', 'item_type', 'record_status'):
                self.assertEqual(old[field], restored[field])
        self.assertFalse(self.report(day=16)['created'])
        self.assertEqual(old_report, json.loads((self.repo / 'data/reports/history/2026-11-16/revision-1.json').read_text()))

    def test_metadata_only_changes_and_reversions_have_unique_revision_ids(self):
        original = self.collect()
        for channel, kind in [('beta', 'security'), ('stable', 'general'), ('beta', 'security'), ('stable', 'general')]:
            with patch('pipeline.collectors.browser.collector.item_type', return_value=kind):
                current = self.collect(channel=channel)
        for row in current:
            revisions = row['revisions']
            self.assertEqual(5, len(revisions))
            self.assertEqual(5, len({r['revision_id'] for r in revisions}))
            self.assertEqual(1, len({r['content_sha256'] for r in revisions}))
            self.assertEqual(original[0]['version'], row['version'])
        # Type alone must count, even when document bytes and channel are equal.
        with patch('pipeline.collectors.browser.collector.item_type', return_value='fix'):
            changed = self.collect()
        self.assertTrue(all(len(r['revisions']) == 6 and r['item_type'] == 'fix' for r in changed))

    def test_legacy_fingerprint_and_incomplete_snapshot_survive_collector_upgrade(self):
        original = self.collect()
        for row in original:
            row.pop('item_content_sha256')
            for revision in row['revisions']:
                revision['revision_id'] = '0-' + revision['revision_id']
                for field in ('channel', 'platform', 'version', 'item_type', 'record_status', 'lifecycle', 'item_content_sha256'):
                    revision.pop(field, None)
        self.path.write_text(json.dumps(original))
        selected = self.select()
        # Recreate an immutable pre-fix fingerprint, with the old algorithm.
        for assessment in selected['created']:
            subject = next(r for r in original if r['source_item_id'] == assessment['subject_id'])
            assessment['input_revision'] = 'semantic-sha256:' + digest(semantic(subject, legacy=True))
            path = self.repo / f'data/assessments/source_item/{assessment["assessment_id"]}.json'
            path.write_text(json.dumps(assessment))
        frozen = self.report()['report']
        self.day = 17
        changed = self.collect(version='151.0', channel='beta')
        for row in changed:
            old = next(r for r in original if r['source_item_id'] == row['source_item_id'])
            self.assertEqual(old['revisions'], row['revisions'][:1])
            self.assertEqual(3, len(row['revisions']))
        self.select()
        self.assertFalse(self.report(day=16)['created'])
        self.assertEqual(frozen, json.loads((self.repo / 'data/reports/history/2026-11-16/revision-1.json').read_text()))

    def test_full_item_digest_detects_change_beyond_public_excerpt(self):
        text = 'Synthetic test evidence. ' + 'unchanged ' * 40
        original = self.collect(text=text + 'old ending')
        self.select()
        self.day = 17
        changed = self.collect(text=text + 'new ending')
        one = lambda rows: next(r for r in rows if r['item_key'] == 'one')
        self.assertEqual(one(original)['summary'], one(changed)['summary'])
        self.assertNotEqual(one(original)['item_content_sha256'], one(changed)['item_content_sha256'])
        self.assertEqual(1, len(self.select()['created']))
