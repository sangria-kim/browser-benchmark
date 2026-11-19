"""Private Edge pilot from a verified collector checkpoint to replayed source shards."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import edge_delta as delta
from pipeline.collectors.browser import BrowserCollector, Response
from test_browser_collectors import source
from pipeline.collectors.browser.collector import json_bytes
from pipeline.run_daily import commit_candidate, durable, git
from pipeline.source_item_shards import edge_policy_shards
from schemas.validate import ContractError


class PolicyDeltaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.store = self.root / 'store'
        self.one = self.record('1')
        self.two = self.record('2')
        self.old = [self.one, self.two]
        self.shards(self.repo, self.old)
        git(self.repo, 'init', '-q')
        self.sha = commit_candidate(self.repo)
        self.first = self.checkpoint(1, self.old, self.old)
        self.parent = delta.initialize(self.repo, self.store, self.sha, self.first)

    def record(self, ident):
        return dict(source_item_id='src-' + ident * 24, source_id=delta.SOURCE, browser='edge',
                    item_key=ident, title='Policy', record_status='parsed',
                    evidence={'url': 'https://example.org/policy', 'content_sha256': 'a'*64},
                    revisions=[{'revision_id': 'original'}])

    def shards(self, root, rows):
        hashes = {}
        for path, group in edge_policy_shards(rows).items():
            raw = json_bytes(group)
            durable(root / path, raw)
            hashes[path] = delta.digest(raw)
        return hashes

    def checkpoint(self, day, before, after, *, seen=None, complete=True, documents=True):
        run = self.root / str(day)
        self.shards(run / 'base', before)
        files = self.shards(run / 'validate', after)
        date = f'2026-11-{day + 10}T04:00:00Z'
        status = dict(source_id=delta.SOURCE, cutoff=date, status='complete' if complete else 'partial',
                      last_successful_cutoff=date if complete else None,
                      observed_ids=[r['source_item_id'] for r in (after if seen is None else seen)],
                      documents_seen={'https://example.org/policy': 'b'*64} if documents else {})
        state = dict(status='partial', stages={'validate': {'status': 'done', 'outputs': files},
                     'collect': {'result': {'browser': [status]}}})
        durable(run / 'state.json', json_bytes(state))
        return run

    def test_no_change_missing_page_and_partial_do_not_remove_history(self):
        run = self.checkpoint(2, self.old, self.old, seen=[self.one], documents=False)
        tip = delta.advance(self.repo, self.store, self.parent, run)
        self.assertEqual(2, delta.verify_commit(self.repo, self.store, tip, self.sha)['records'])
        step = delta.blob(self.store, tip)
        self.assertNotIn('changes', step)
        self.assertNotIn('evidence', step)
        self.assertEqual(tip, delta.advance(self.repo, self.store, self.parent, run))
        with self.assertRaisesRegex(ContractError, 'advance'):
            delta.advance(self.repo, self.store, tip, run)
        before = set(self.store.iterdir())
        partial = self.checkpoint(3, self.old, self.old, seen=[self.one], complete=False)
        with self.assertRaisesRegex(ContractError, 'Incomplete'):
            delta.advance(self.repo, self.store, tip, partial)
        self.assertEqual(before, set(self.store.iterdir()))

    def test_content_evidence_only_confirmed_removal_and_late_addition(self):
        changed = copy.deepcopy(self.old)
        changed[0]['title'] = 'Updated'
        for row in changed:
            row['evidence']['content_sha256'] = 'b'*64
            row['revisions'].append({'revision_id': 'new'})
        added = dict(self.record('3'), published_at='2026-01-03')
        changed.append(added)
        run = self.checkpoint(2, self.old, changed)
        tip = delta.advance(self.repo, self.store, self.parent, run)
        step = delta.blob(self.store, tip)
        changes = delta.patches(self.store, step, 'changes')
        self.assertEqual(['changed', 'added'], [p['type'] for p in changes])
        self.assertEqual('backfill', changes[-1]['origin'])
        self.assertEqual(self.two['source_item_id'], delta.patches(self.store, step, 'evidence')[0]['item_id'])
        run = self.checkpoint(3, changed, changed, seen=[changed[0], added])
        next_tip = delta.advance(self.repo, self.store, tip, run)
        items, retired, _ = delta.restore(self.repo, self.store, next_tip)
        self.assertEqual(delta.indexed(changed), items)
        self.assertEqual({self.two['source_item_id']}, retired)
        restored = self.checkpoint(4, changed, changed)
        final = delta.advance(self.repo, self.store, next_tip, restored)
        self.assertEqual(set(), delta.restore(self.repo, self.store, final)[1])
        # Failing a read leaves earlier verified tips usable.
        path = self.store / (step['evidence'][0] + '.json')
        path.write_text('[]')
        with self.assertRaisesRegex(ContractError, 'checksum'):
            delta.restore(self.repo, self.store, final)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            delta.restore(self.repo, self.store, final)
        self.assertEqual(delta.indexed(self.old), delta.restore(self.repo, self.store, self.parent)[0])

    def test_crash_before_receipt_can_retry_and_history_rewrites_fail(self):
        changed = [dict(self.one, title='New'), self.two]
        run = self.checkpoint(2, self.old, changed)
        save = delta.save
        def interrupt(store, value):
            if isinstance(value, dict) and 'parent' in value:
                raise OSError('interrupted')
            return save(store, value)
        with patch.object(delta, 'save', interrupt), self.assertRaises(OSError):
            delta.advance(self.repo, self.store, self.parent, run)
        tip = delta.advance(self.repo, self.store, self.parent, run)
        self.assertEqual(delta.indexed(changed), delta.restore(self.repo, self.store, tip)[0])
        bad = self.checkpoint(3, changed, [dict(changed[0], revisions=[]), changed[1]])
        with self.assertRaisesRegex(ContractError, 'history'):
            delta.advance(self.repo, self.store, tip, bad)

    def test_one_collection_feeds_semantic_and_compatibility_views(self):
        cfg = source('edge-policies')
        url = cfg['url'] + '/sample'
        messages = {'one': 'First definition', 'two': 'Second definition'}
        calls = []
        def transport(target):
            calls.append(target)
            if target == cfg['url']:
                body = f'<a href="{url}">Policy</a>'
            else:
                self.assertEqual(url, target)
                rows = ''.join(f'<p id="{k}">{v}</p>' for k, v in messages.items())
                body = f'<div class="content"><h2 id="policy">Policy</h2>{rows}</div>'
            return Response(target, body.encode())

        def collect(day):
            run = self.root / f'observed-{day}'
            collector = BrowserCollector(self.repo, run, transport)
            status = collector.collect(cfg, f'2026-11-{day}T00:00:00Z', '2026-01-01')
            self.assertEqual('complete', status['status'])
            return status, delta.indexed(delta.read_edge_policies(self.repo)[0])

        # Use the collector's real document parser and its retained historical rows.
        self.repo = self.root / 'observations'
        self.repo.mkdir()
        first, before = collect(18)
        messages.pop('two')
        messages['three'] = 'Third definition'
        status, after = collect(19)
        self.assertEqual([cfg['url'], url] * 2, calls)
        changes, evidence = delta.compare(before, after, status, set(), first['cutoff'])
        self.assertEqual(['added', 'removed'], sorted(p['type'] for p in changes))
        self.assertEqual(1, len(evidence))
        self.assertEqual(after, delta.replay(before, set(), changes, evidence)[0])
        self.assertEqual(4, len(calls))
