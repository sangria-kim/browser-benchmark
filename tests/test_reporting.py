import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from test_selection import SelectionTests as SelectionFixture
from pipeline.reporting import run, render, window
from pipeline.reporting.core import timing
from pipeline.normalize import load_dataset, publish, validate_graph
from pipeline.selection import load_rules
from pipeline.selection.core import decision
from schemas.validate import ContractError


class ReportingTests(unittest.TestCase):
    setUp = SelectionFixture.setUp
    write = SelectionFixture.write
    provider = SelectionFixture.provider
    execute = SelectionFixture.execute

    def selected(self, at='2026-11-16T05:00:00Z'):
        return self.execute(assessed_at=at, provider=self.provider, model_id='fixture-model-1')

    def report(self, day='2026-11-16', cutoff='2026-11-16T06:00:00Z', **kw):
        return run(self.repo, self.private, day=day, cutoff=cutoff, **kw)

    def exclude(self, context, rules):
        result = decision('excluded', 'Fixture comparison no longer in scope.', revisit='Review scope.')
        result['evidence_source_item_ids'] = [s['source_item_id'] for s in context['sources']]
        return result

    def test_kst_boundary_and_cutoff(self):
        self.assertEqual('2026-11-15T14:59:59.999999Z', window('2026-11-16', '2026-11-15T15:00:00Z')[0])
        with self.assertRaises(ValueError): window('2026-11-16', '2026-11-16T15:00:00Z')
        with self.assertRaises(ValueError): window('2026-11-16', '2026-11-16T10:00:00')
        # Midnight is included; assessments after cutoff are absent.
        for values in self.data.values():
            for row in values:
                if 'observed_at' in row: row['observed_at'] = '2026-11-15T14:00:00Z'
                for revision in row.get('revisions', []):
                    revision['observed_at'] = '2026-11-15T14:00:00Z'
        self.write()
        self.selected('2026-11-15T15:00:00Z')
        self.assertEqual(2, len(self.report(cutoff='2026-11-15T15:00:00Z')['report']['items']))

    def test_feature_flag_retry_and_no_daily_repeat(self):
        self.selected()
        first = self.report(collection='complete', evaluation='complete')
        self.assertEqual({'features','flags'}, {i['selection_kind'] for i in first['report']['items']})
        self.assertEqual(2, len(first['report']['items']))
        before = {p: p.read_bytes() for p in self.repo.rglob('*') if p.is_file()}
        self.assertFalse(self.report(collection='complete', evaluation='complete')['created'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.repo.rglob('*') if p.is_file()})
        later = self.report('2026-11-17', '2026-11-17T06:00:00Z', collection='complete', evaluation='complete')['report']
        self.assertEqual([], later['items'])
        self.assertEqual('no_changes', later['outcome'])
        validate_graph(self.repo)

    def test_partial_unknown_failure_do_not_claim_no_changes(self):
        self.selected()
        for state in ['partial', 'failed', 'unknown']:
            result = self.report('2026-11-17', '2026-11-17T06:00:00Z', collection=state, evaluation='complete')['report']
            self.assertEqual('incomplete', result['outcome'])
            self.assertNotIn('새 선정 변화가 없습니다', render(result))
        result = self.report('2026-11-17', '2026-11-17T06:00:00Z', collection='complete', evaluation='failed')['report']
        self.assertEqual('incomplete', result['outcome'])

    def test_revision_append_preserves_handwritten_and_archives(self):
        handwritten = self.repo / 'reports/2026-11-16.md'
        handwritten.parent.mkdir(parents=True); handwritten.write_bytes(b'Owner report\n')
        self.selected()
        first = self.report()['report']
        old_md = (self.repo / first['markdown_path']).read_bytes()
        second = self.report(collection='partial', evaluation='complete')['report']
        self.assertEqual((2, 1), (second['revision'], second['supersedes_revision']))
        self.assertEqual(first['report_id'], second['report_id'])
        self.assertEqual(old_md, (self.repo / first['markdown_path']).read_bytes())
        self.assertEqual(b'Owner report\n', handwritten.read_bytes())
        self.assertEqual(1, len(load_dataset(self.repo)['report']))
        with self.assertRaises(ContractError):
            publish(self.repo, {'data/reports/history/2026-11-16/revision-1.json':second}, self.private)
        with self.assertRaises(ContractError):
            publish(self.repo, {}, self.private, text_files={first['markdown_path']:'replace'})

    def test_deselection_and_reselection_have_real_change_ids(self):
        self.selected()
        self.report()
        rules = load_rules(); rules['rule_version'] = 'fixture-reclass-v2'
        self.execute(assessed_at='2026-11-17T05:00:00Z', rules=rules, provider=self.exclude, model_id='fixture-model-1')
        second = self.report('2026-11-17', '2026-11-17T06:00:00Z')['report']
        self.assertEqual({'deselected'}, {i['action'] for i in second['items']})
        self.assertEqual({'reclassification'}, {i['timing'] for i in second['items']})
        self.selected('2026-11-18T05:00:00Z')
        third = self.report('2026-11-18', '2026-11-18T06:00:00Z')['report']
        self.assertEqual({'reselected'}, {i['action'] for i in third['items']})
        self.assertTrue(set(i['change_id'] for i in second['items']).isdisjoint(i['change_id'] for i in third['items']))
        validate_graph(self.repo)

    def test_owner_replacement_is_not_old_subject_deselection(self):
        self.selected(); self.report()
        original = copy.deepcopy(self.data['feature_event'][0])
        newer = copy.deepcopy(original); newer.update(event_id='event-newer', observed_at='2026-11-17T00:00:00Z', previous_event_id=original['event_id'])
        self.data['feature_event'].append(newer)
        self.write()
        def provider(context, rules):
            return self.exclude(context, rules) if context['subject_id'] == 'event-newer' else self.provider(context, rules)
        self.execute(assessed_at='2026-11-17T05:00:00Z', provider=provider, model_id='fixture-model-1')
        report = self.report('2026-11-17', '2026-11-17T06:00:00Z')['report']
        self.assertEqual(1, len(report['catalog_transitions']))
        transition = report['catalog_transitions'][0]
        self.assertEqual('selected', transition['previous']['status'])
        self.assertEqual('excluded', transition['current']['status'])
        self.assertNotIn('event-newer', [i['subject_id'] for i in report['items']])
        self.assertEqual('changes', report['outcome'])
        validate_graph(self.repo)
        broken = copy.deepcopy(report); broken['catalog_transitions'][0]['current']['catalog_id'] = 'unknown'
        with self.assertRaises(ContractError): validate_graph(self.repo, {'data/reports/current/daily-2026-11-17.json':broken})

    def test_late_backfill_correction_and_retirement(self):
        assessment = {'supersedes':None}
        self.assertEqual('backfill', timing({'origin':'baseline'}, assessment, '2026-11-16'))
        self.assertEqual('late_observation', timing({'announced_at':'2026-11-01','event_type':'planned_retirement'}, assessment, '2026-11-16'))
        self.assertEqual('correction', timing({'revision':2}, assessment, '2026-11-16'))
        event = self.data['feature_event'][0]
        event.update(event_type='planned_retirement', announced_at='2026-11-01', effective_at='2027-01-01', origin='daily')
        self.write(); self.selected()
        report = self.report()['report']
        item = next(i for i in report['items'] if i['selection_kind'] == 'features')
        self.assertEqual('2027-01-01', item['effective_at'])
        self.assertEqual('2026-11-16T05:00:00Z', item['discovered_at'])
        self.assertEqual('late_observation', item['timing'])
        self.assertIn('planned_retirement', render(report))

    def test_fixed_source_evidence_and_local_links(self):
        self.selected(); report = self.report()['report']
        for item in report['items']:
            for evidence in item['evidence']:
                self.assertTrue(evidence['content_sha256'])
                self.assertTrue(evidence['revision_id'])
                self.assertTrue((self.repo / evidence['record_path']).exists())
        import re
        markdown = self.repo / report['markdown_path']
        for target in re.findall(r'\]\(([^)]+)\)', markdown.read_text()):
            if not target.startswith('https:'):
                self.assertTrue((markdown.parent / target).exists(), target)
        frozen = markdown.read_bytes()
        self.data['source_item'][0]['evidence']['url'] = 'https://example.com/new'
        self.assertEqual(frozen.decode(), render(report))
        broken = copy.deepcopy(report); broken['items'][0]['evidence'][0]['content_sha256'] = 'f'*64
        with self.assertRaises(ContractError): validate_graph(self.repo, {'data/reports/current/daily-2026-11-16.json':broken})

    def test_cutoff_excludes_future_assessments_and_dry_run(self):
        self.selected()
        result = self.report(cutoff='2026-11-16T04:00:00Z', dry_run=True)
        self.assertEqual([], result['report']['items'])
        self.assertFalse((self.repo / 'data/reports').exists())
        self.assertFalse((self.repo / 'reports/generated').exists())

    def test_public_completeness_rejects_private_error_text(self):
        self.selected()
        with self.assertRaises(ValueError): self.report(collection='/private/log/timeout')

    def test_same_subject_reassessments_render_once_with_all_change_refs(self):
        self.selected()
        rules = load_rules(); rules['rule_version'] = 'fixture-change'
        self.execute(assessed_at='2026-11-16T05:30:00Z', rules=rules, provider=self.provider, model_id='fixture-model-1')
        report = self.report()['report']
        self.assertEqual(2, len(report['items']))
        self.assertTrue(all(len(i['related_change_ids']) == 1 for i in report['items']))
        self.assertEqual(2, render(report).count('### PM 선별과 비교 과제'))

    def test_source_only_later_observation_does_not_rewrite_old_report(self):
        # Remove feature ownership so the browser item is assessed directly.
        self.data['feature_event'] = []
        self.data['feature'] = []
        self.write(); self.selected()
        first = self.report()['report']
        sources = self.data['source_item']
        source = next(s for s in sources if not s.get('experiment_kind'))
        source['observed_at'] = '2026-11-17T00:00:00Z'
        source['evidence']['observed_at'] = source['observed_at']
        revision = copy.deepcopy(source['revisions'][-1])
        revision.update(revision_id='revision-next-observation', observed_at=source['observed_at'], evidence=copy.deepcopy(source['evidence']))
        source['revisions'].append(revision)
        self.write()
        second = self.report()
        self.assertFalse(second['created'])
        self.assertEqual(first, second['report'])

    def test_corrected_event_uses_assessed_archive_and_new_judgment(self):
        self.selected(); first = self.report()['report']
        original = copy.deepcopy(self.data['feature_event'][0])
        archive = self.repo / ('data/event-revisions/' + original['event_id'] + '/revision-1.json')
        archive.parent.mkdir(parents=True); archive.write_text(json.dumps(original))
        self.data['feature_event'][0].update(summary='Corrected factual statement', revision=2)
        self.write()
        # Unassessed correction cannot replace the old facts in a daily report.
        report = self.report()['report']
        feature = next(i for i in report['items'] if i['selection_kind'] == 'features')
        self.assertEqual(original['summary'], feature['details']['summary'])
        self.selected('2026-11-17T05:00:00Z')
        later = self.report('2026-11-17', '2026-11-17T06:00:00Z')['report']
        self.assertEqual(1, len(later['items']))
        self.assertEqual('correction', later['items'][0]['timing'])
        self.assertEqual('Corrected factual statement', later['items'][0]['details']['summary'])
        self.assertEqual(first, json.loads((self.repo / 'data/reports/history/2026-11-16/revision-1.json').read_text()))

    def test_publication_failure_rolls_back_json_and_text(self):
        self.selected()
        result = self.report(dry_run=True)
        import os
        calls = []
        def fail(source, target):
            calls.append(target)
            if len(calls) == 3: raise OSError('Synthetic publish failure')
            os.replace(source, target)
        with self.assertRaises(OSError):
            publish(self.repo, result['replacements'], self.private, text_files=result['text_files'], replace=fail)
        self.assertFalse(list((self.repo / 'data/reports').rglob('*.json')))
        self.assertFalse(list((self.repo / 'reports/generated').rglob('*.md')))


# Do not collect the imported helper class as another test suite.
del SelectionFixture
