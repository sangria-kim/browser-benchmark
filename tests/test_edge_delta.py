"""Private Edge pilot from a verified collector checkpoint to replayed source shards."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import edge_delta as delta
from pipeline.collectors.browser import BrowserCollector, Response
from pipeline.collectors.browser.cache import seed_cache
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
                      visible_content={r['source_item_id']: delta.checksum(r['title']) for r in (after if seen is None else seen)},
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

    def test_baseline_records_only_actual_observations_and_accepts_legacy_unknown(self):
        for known in (True, False):
            with self.subTest(known=known):
                status_path = self.first / 'state.json'
                state = json.loads(status_path.read_bytes())
                status = state['stages']['collect']['result']['browser'][0]
                if known:
                    status['observed_ids'] = [self.one['source_item_id']]
                    status['visible_content'].pop(self.two['source_item_id'])
                else:
                    status.pop('observed_ids')
                durable(status_path, json_bytes(state))
                base = delta.initialize(self.repo, self.store, self.sha, self.first)
                first = self.checkpoint(2, self.old, self.old, seen=[self.one])
                tip = delta.advance(self.repo, self.store, base, first)
                self.assertNotIn('changes', delta.blob(self.store, tip))
                again = self.checkpoint(3, self.old, self.old, seen=[self.one])
                tip = delta.advance(self.repo, self.store, tip, again)
                self.assertEqual(set(), delta.restore(self.repo, self.store, tip)[1])

    def test_markup_and_position_changes_use_actual_document_content(self):
        cfg = source('edge-policies')
        url = cfg['url'] + '/example'
        def collect(day, tag, paragraphs, anchor=None, heading_id='policy', heading='Example'):
            def transport(target):
                if target == cfg['url']:
                    return Response(target, f'<a href="{url}">Example</a>'.encode())
                body = ''.join(f'<{tag}>{text}</{tag}>' for text in paragraphs)
                if anchor:
                    body += f'<p id="fixed">{anchor}</p>'
                return Response(url + '-canonical', f'<div class="content"><h2 id="{heading_id}">{heading}</h2>{body}</div>'.encode())
            repo = self.root / 'observations'
            status = BrowserCollector(repo, self.root / f'capture-{day}', transport).collect(
                cfg, f'2026-11-{day}T00:00:00Z', '2026-01-01')
            self.assertEqual('complete', status['status'])
            return status, delta.indexed(delta.read_edge_policies(repo)[0])

        original = ['First definition', 'Second definition', 'Third definition']
        first, before = collect(16, 'p', original)
        second, retagged = collect(17, 'li', original)
        changes, evidence = delta.compare(before, retagged, second, set(), first['cutoff'], set(first['observed_ids']), first['visible_content'])
        self.assertEqual([], changes)
        self.assertEqual(retagged, delta.replay(before, set(), changes, evidence)[0])
        third, after = collect(18, 'li', original[1:])
        changes, evidence = delta.compare(retagged, after, third, set(), second['cutoff'], set(second['observed_ids']), second['visible_content'])
        event, = changes
        self.assertEqual(('policy_document', 'changed'), (event['scope'], event['type']))
        lost, = event['removed_content']
        self.assertEqual(original[0], retagged[lost['source_item_id']]['summary'])
        self.assertEqual([], event['added_content'])
        self.assertEqual((after, set()), delta.replay(retagged, set(), changes, evidence))
        fourth, mixed = collect(19, 'p', original[1:], anchor='Anchor added')
        changes, _ = delta.compare(after, mixed, fourth, set(), third['cutoff'], set(third['observed_ids']), third['visible_content'])
        added, = changes
        self.assertEqual(('added', 'fixed'), (added['type'], mixed[added['item_id']]['item_key']))
        fifth, fewer = collect(20, 'p', original[1:])
        changes, _ = delta.compare(mixed, fewer, fifth, set(), fourth['cutoff'], set(fourth['observed_ids']), fourth['visible_content'])
        removed, = changes
        self.assertEqual(('removed', added['item_id']), (removed['type'], removed['item_id']))


        sixth, renamed = collect(21, 'p', original[1:], heading_id='security-version-1.2')
        changes, patches = delta.compare(fewer, renamed, sixth, set(), fifth['cutoff'],
                                         set(fifth['observed_ids']), fifth['visible_content'])
        self.assertEqual([], changes)
        self.assertEqual(renamed, delta.replay(fewer, set(), changes, patches)[0])
        seventh, edited = collect(22, 'p', original[1:], heading_id='security-version-1.2', heading='Changed heading')
        changes, _ = delta.compare(renamed, edited, seventh, set(), sixth['cutoff'],
                                   set(sixth['observed_ids']), sixth['visible_content'])
        event, = changes
        self.assertEqual(url + '-canonical', event['url'])
        self.assertEqual((2, 2), (len(event['added_content']), len(event['removed_content'])))
        changes, _ = delta.compare(renamed, edited, seventh, set(), sixth['cutoff'], set(sixth['observed_ids']), None)
        self.assertEqual([], changes)

    def test_backfill_uses_korean_calendar_day_for_the_same_instant(self):
        before = delta.indexed([self.one])
        fixed = dict(self.record('3'), published_at='2026-11-18')
        positional = dict(self.record('4'), item_key='Example:p:1', published_at='2026-11-18',
                          evidence={'url': 'https://example.org/another', 'content_sha256': 'a'*64})
        after = delta.indexed([self.one, fixed, positional])
        hashes = {k: delta.checksum(v['item_key']) for k, v in after.items()}
        end = '2026-11-20T00:00:00Z'
        status = dict(status='complete', cutoff=end, last_successful_cutoff=end, observed_ids=list(after),
                      visible_content=hashes, documents_seen={r['evidence']['url']: 'a'*64 for r in after.values()})
        for since in ('2026-11-18T15:00:00Z', '2026-11-19T00:00:00+09:00'):
            with self.subTest(since=since):
                changes, _ = delta.compare(before, after, status, set(), since, set(before),
                                           {k: hashes[k] for k in before})
                self.assertEqual(['backfill', 'backfill'], [c['origin'] for c in changes])
                self.assertEqual({'policy_document', 'record'}, {c.get('scope', 'record') for c in changes})

    def test_anchor_reassigned_between_paragraphs_matches_visible_content(self):
        cfg = source('edge-policies')
        url = cfg['url'] + '/reused-anchor'
        repo = self.root / 'anchor-reassignment'
        def collect(day, fixed):
            def transport(target):
                if target == cfg['url']:
                    return Response(target, f'<a href="{url}">Policy</a>'.encode())
                body = ''.join('<p' + (' id="fixed"' if i == fixed else '') + '>' + text + '</p>'
                               for i, text in enumerate(['First definition', 'Second definition']))
                return Response(url, f'<div class="content">{body}</div>'.encode())
            status = BrowserCollector(repo, self.root / f'anchor-{day}', transport).collect(
                cfg, f'2026-11-{day}T00:00:00Z', '2026-01-01')
            self.assertEqual('complete', status['status'])
            return status, delta.indexed(delta.read_edge_policies(repo)[0])
        first, before = collect(18, 0)
        second, after = collect(19, 1)
        changes, evidence = delta.compare(before, after, second, set(), first['cutoff'],
                                          set(first['observed_ids']), first['visible_content'])
        self.assertEqual([], changes)
        self.assertEqual(after, delta.replay(before, set(), changes, evidence)[0])

    def test_legacy_edge_cache_without_capture_time_stops_before_replay(self):
        cfg = source('edge-policies')
        repo, cache = self.root / 'capture', self.root / 'old-cache'
        cutoff = '2026-11-19T00:00:00Z'
        durable(cache / 'edge-policies-progress.json', json_bytes({
            'cutoff': cutoff, 'responses': {cfg['url']: {'url': cfg['url'], 'headers': {}, 'sha256': 'a'*64}},
            'documents': []}))
        self.shards(repo, [])
        for _ in range(2):
            status = BrowserCollector(repo, cache, lambda _: self.fail('unexpected network'), resume=True).collect(
                cfg, cutoff, '2026-01-01')
            self.assertEqual('partial', status['status'])
            self.assertIn('no observation time', status['errors'][0]['reason'])
            self.assertIsNone(status['last_successful_cutoff'])
            self.assertEqual([], delta.read_edge_policies(repo)[0])

    def test_redirected_edge_cache_preserves_observation_time_on_replay(self):
        cfg = source('edge-policies')
        cutoff = '2026-11-19T00:00:00Z'
        url = cfg['url'] + '/sample'
        def transport(target):
            if target == cfg['url']:
                return Response(target, f'<a href="{url}">Policy</a>'.encode())
            return Response(url + '-canonical', b'<div class="content"><p>Definition</p></div>')
        original = self.root / 'original-cache'
        repo = self.root / 'network-capture'
        status = BrowserCollector(repo, original, transport).collect(cfg, cutoff, '2026-01-01')
        self.assertEqual('complete', status['status'])
        expected = delta.read_edge_policies(repo)[0]
        self.assertTrue(expected)
        for n in (1, 2):
            cache, replay = self.root / f'cache-{n}', self.root / f'replay-{n}'
            seed_cache(original, cache, cutoff)
            status = BrowserCollector(replay, cache, lambda _: self.fail('unexpected network'), resume=True).collect(
                cfg, cutoff, '2026-01-01')
            self.assertEqual('complete', status['status'])
            self.assertEqual(expected, delta.read_edge_policies(replay)[0])

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
        changes, evidence = delta.compare(before, after, status, set(), first['cutoff'], set(first['observed_ids']), first['visible_content'])
        self.assertEqual(['added', 'removed'], sorted(p['type'] for p in changes))
        self.assertEqual(1, len(evidence))
        self.assertEqual(after, delta.replay(before, set(), changes, evidence)[0])
        self.assertEqual(4, len(calls))
