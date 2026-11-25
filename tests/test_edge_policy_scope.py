"""Scheduled Edge coverage and the classifier's receipt of direct-link evidence."""
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urljoin

from pipeline import collect
from pipeline.collect import collect_one
from pipeline.collectors.browser import Response
from pipeline.collectors.browser.html import Tree, boundary, blocks
from pipeline.run_daily import encoded, read

ROOT = Path(__file__).resolve().parents[1]
DAILY = '2026-11-24T07:00:00+09:00'
WEEKLY = '2026-11-29T10:00:00+09:00'
POLICY = 'https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies'
RELEASE_CHANNELS = ('edge-stable', 'edge-beta', 'edge-mobile-stable', 'edge-mobile-beta')
SECTION = 'feature-updates'


class EdgePolicyScopeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.repo = self.folder / 'repo'
        shutil.copytree(ROOT / 'config', self.repo / 'config')
        self.sources = read(self.repo / 'config/sources.yml')['sources']
        self.edge_notes = {s['source_id']: s['url'] for s in self.sources
                           if s['browser'] == 'edge' and s['source_id'] != 'edge-policies'}
        self.calls = []
        self.scanned = []
        self.empty = False

    def request(self, url):
        self.calls.append(url)
        sid = next((sid for sid, target in self.edge_notes.items() if target == url), None)
        if sid is None:
            self.fail(f'Unexpected collection request: {url}')
        # The target feature uses the parser's positional key, with no DOM ID.
        html = f"""<div class="content">
            <h2 id="{SECTION}">November 10, 2026</h2>
            <p>Add tab sharing in {sid}. See
              <a href="microsoft-edge-policies/examplepolicy">the support policy</a>.</p>
            <p id="different">Other feature. See <a href="{POLICY}/different">other conditions</a>,
              <a href="{POLICY}#examplepolicy">the catalog</a> and
              <a href="https://example.org/policy">external details</a>.</p>
            <footer><a href="{POLICY}/footer">Footer policy</a></footer></div>""".encode()
        return Response(url, html, observed_at='2026-11-29T11:00:00+09:00')

    def collect_one(self, collector, source, state, private):
        self.scanned.append(source['source_id'])
        if source['browser'] == 'edge' and not self.empty:
            return collect_one(collector, source, state, private)
        collector.parsed_ids = set()
        return dict(source_id=source['source_id'], status='complete', cutoff=state['cutoff'])

    def cli(self, run, cutoff, *options, edge_calls=None):
        argv = ['pipeline.run_daily', '--repository', str(self.repo), '--private-dir', str(self.folder),
                '--run-id', run, *options]
        if cutoff:
            argv.extend(['--cutoff', cutoff])
        with patch('sys.argv', argv), patch('pipeline.collect.collect_one', side_effect=self.collect_one):
            with patch('pipeline.collectors.browser.collector.HTTPTransport', return_value=self.request):
                with redirect_stdout(StringIO()), self.assertRaises(SystemExit) as result:
                    runpy.run_path(str(ROOT / 'pipeline/run_daily.py'), run_name='__main__')
        state = read(self.folder / run / 'feature-run.json')
        errors = {sid: item['errors'] for sid, item in state['source_results'].items()
                  if item.get('errors')}
        self.assertEqual(0, result.exception.code, errors)
        self.assertEqual(list(self.edge_notes.values()) if edge_calls is None else edge_calls, self.calls)
        self.calls.clear()

    def decisions(self, run, select_stable=False):
        decisions, dispositions = [], []
        for path in (run / 'work/candidates').glob('*.json'):
            for row in read(path):
                sid = row['source_id']
                item_id = row['source_item_id']
                revision = row['revisions'][-1]['revision_id']
                selected = select_stable and sid == 'edge-stable' and row['item_key'] == SECTION + ':p:1'
                dispositions.append(dict(source_id=sid, source_item_id=item_id, revision_id=revision,
                                         disposition='selected' if selected else 'excluded'))
                if selected:
                    decisions.append(dict(source_item_id=item_id, revision_id=revision,
                                          canonical_key='tab-sharing', title='Tab sharing',
                                          evidence_quote='Add tab sharing in edge-stable.',
                                          change_kind='product_change'))
        return dict(decisions=decisions, dispositions=dispositions)

    def test_daily_and_weekly_use_enabled_scope_and_save(self):
        status = self.repo / 'data/daily-status/2026-11-24.json'
        weekly = {s['source_id'] for s in self.sources if s['enabled']}
        weekly_only = {s['source_id'] for s in self.sources
                       if s['enabled'] and s['browser'] in {'brave', 'vivaldi', 'opera'}}
        daily = weekly - weekly_only
        self.assertEqual((21, 30, 9), (len(daily), len(weekly), len(weekly_only)))
        self.assertEqual(7, len(self.edge_notes))
        for name, cutoff, sources, flags in (('day', DAILY, daily, ('--daily-status',)),
                                             ('week', WEEKLY, weekly, ('--mode', 'weekly_reconcile'))):
            with self.subTest(name=name):
                self.scanned.clear()
                self.cli(name, cutoff, *flags)
                self.assertCountEqual(sources, self.scanned)
                run = self.folder / name
                state = read(run / 'feature-run.json')
                self.assertEqual(sources, set(state['observed']))
                self.assertEqual(sources, set(state['source_results']))
                self.assertEqual(sources, {path.stem for path in (run / 'work/candidates').glob('*.json')})
                self.assertEqual({'complete'}, {s['status'] for s in state['source_results'].values()})
                for sid in RELEASE_CHANNELS:
                    rows = read(run / 'work/candidates' / (sid + '.json'))
                    if name == 'week' and sid == 'edge-stable':
                        # The accepted, unchanged daily item needs no second classification.
                        self.assertEqual(['different'], [row['item_key'] for row in rows])
                    else:
                        self.assertEqual({SECTION + ':p:1', 'different'}, {r['item_key'] for r in rows})
                self.assertFalse((run / 'work/candidates/edge-policies.json').exists())
                if name == 'day':
                    pinned = state['daily_status']['enabled']
                    self.assertEqual(daily, set(pinned))
                    classification = run / 'classification.json'
                    classification.write_bytes(encoded(self.decisions(run, select_stable=True)))
                    self.cli(name, None, '--save-features', str(classification), edge_calls=[])
                    receipt = status.read_bytes()
                    record = read(status)
                    self.assertEqual(('complete', 1, 1), (record['status'],
                                     record['collected_feature_count'], record['change_count']))
                else:
                    classification = run / 'classification.json'
                    classification.write_bytes(encoded(self.decisions(run)))
                    self.cli(name, None, '--save-features', str(classification), edge_calls=[])
                    self.assertEqual(receipt, status.read_bytes())
                self.assertEqual('saved', read(run / 'feature-run.json')['status'])

    def test_complete_empty_daily_scope_certifies_zero(self):
        self.empty = True
        self.cli('empty', DAILY, '--mode', 'daily', '--daily-status', edge_calls=[])
        self.assertEqual(21, len(self.scanned))
        run = self.folder / 'empty'
        self.assertEqual(21, len(list((run / 'work/candidates').glob('*.json'))))
        classification = run / 'classification.json'
        classification.write_bytes(encoded(dict(decisions=[], dispositions=[])))
        self.cli('empty', None, '--save-features', str(classification), edge_calls=[])
        record = read(self.repo / 'data/daily-status/2026-11-24.json')
        self.assertEqual(('complete', 0, 0), (record['status'], record['change_count'],
                                              record['collected_feature_count']))

    def test_explicit_daily_rejects_weekly_only_sources_before_any_scan(self):
        with self.assertRaisesRegex(ValueError, '--mode manual.*brave-blog'):
            self.cli('mixed', DAILY, '--mode', 'daily', '--source', 'edge-stable', '--source', 'brave-blog')
        self.assertEqual([], self.scanned)
        self.assertEqual([], self.calls)
        self.assertFalse((self.folder / 'mixed/feature-run.json').exists())

    def test_manual_and_legacy_keep_weekly_only_sources(self):
        targets = ['brave-blog', 'vivaldi-desktop', 'opera-mobile']
        options = [part for sid in targets for part in ('--source', sid)]
        for mode in ('manual', 'legacy'):
            self.scanned.clear()
            self.cli(mode, DAILY, '--mode', mode, *options, edge_calls=[])
            self.assertCountEqual(targets, self.scanned)
        argv = ['pipeline.collect', '--repository', str(self.repo), '--private-dir',
                str(self.folder / 'direct'), '--cutoff', DAILY, *options]
        self.scanned.clear()
        with patch('sys.argv', argv), patch('pipeline.collect.collect_one', side_effect=self.collect_one):
            with redirect_stdout(StringIO()):
                self.assertEqual(0, collect.main())
        self.assertCountEqual(targets, self.scanned)

    def test_partial_weekly_request_cannot_be_saved_as_full_reconciliation(self):
        urls = [self.edge_notes['edge-stable']]
        self.cli('diagnostic', WEEKLY, '--mode', 'weekly_reconcile', '--source', 'edge-stable', edge_calls=urls)
        run = self.folder / 'diagnostic'
        classification = run / 'classification.json'
        classification.write_bytes(encoded(self.decisions(run)))
        with self.assertRaisesRegex(ValueError, 'all enabled sources'):
            self.cli('diagnostic', None, '--save-features', str(classification), edge_calls=[])
        self.assertFalse((self.repo / 'data').exists())

    def test_unpublished_previous_scope_cannot_be_resumed_or_finalized(self):
        with patch.object(collect, 'WEEKLY_ONLY_BROWSERS', frozenset()):
            self.cli('previous', DAILY, '--daily-status')
        run = self.folder / 'previous'
        self.assertEqual(30, len(read(run / 'feature-run.json')['daily_status']['enabled']))
        self.scanned.clear()
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            self.cli('previous', DAILY, '--daily-status', '--resume', edge_calls=[])
        classification = run / 'classification.json'
        classification.write_bytes(encoded(self.decisions(run)))
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            self.cli('previous', None, '--save-features', str(classification), edge_calls=[])
        self.assertEqual([], self.scanned)
        self.assertEqual([], self.calls)
        self.assertFalse((self.repo / 'data').exists())

    def test_disabled_policy_rejected_before_transport(self):
        argv = ['pipeline.collect', '--repository', str(self.repo), '--private-dir',
                str(self.folder / 'manual'), '--source', 'edge-policies', '--cutoff', DAILY]
        with patch('sys.argv', argv):
            with patch('pipeline.collectors.browser.collector.HTTPTransport', return_value=self.request):
                with self.assertRaisesRegex(ValueError, 'Unknown or disabled sources: edge-policies'):
                    collect.main()
        self.assertEqual([], self.calls)

    def test_classifier_can_trace_only_the_selected_item_direct_link(self):
        self.cli('day', DAILY, '--daily-status')
        run = self.folder / 'day'
        classification = self.decisions(run, select_stable=True)
        choice, = classification['decisions']
        row, = [candidate for candidate in read(run / 'work/candidates/edge-stable.json')
                if candidate['source_item_id'] == choice['source_item_id']]
        revision = row['revisions'][-1]
        self.assertEqual(choice['revision_id'], revision['revision_id'])
        evidence = revision['evidence']
        digest = evidence['content_sha256']
        raw = (run / 'work/browser/cache' / digest).read_bytes()
        self.assertEqual(digest, sha256(raw).hexdigest())
        body = boundary(Tree(raw.decode()).root, row['source_id'])
        unit, = [u for u in blocks(body) if u['key'] == row['item_key']]
        self.assertEqual(evidence['section'], unit['section'])
        self.assertEqual(evidence['excerpt'], unit['text'])
        paragraph, = [node for node in body.walk() if node.tag == 'p' and node.text() == unit['text']]
        link, = [node for node in paragraph.walk() if node.tag == 'a']
        href = link.attrs['href']
        detail = urljoin(evidence['url'], href)
        self.assertEqual(POLICY + '/examplepolicy', detail)

        # The one detailed read is a separate, synthetic classifier action.
        def read_detail(url):
            self.assertEqual(detail, url)
            return 'Windows 140 and later.'

        quote = read_detail(detail)
        self.assertNotIn(quote, evidence['excerpt'])
        memo = run / 'edge-policy-evidence.md'
        memo_text = '\n'.join((row['source_item_id'], revision['revision_id'], digest, href,
                              detail, evidence['observed_at'], quote))
        memo.write_text(memo_text, encoding='utf-8')
        collect.save_features(self.repo, run, classification)
        self.assertFalse((run / 'work').exists())
        self.assertEqual(memo_text, memo.read_text(encoding='utf-8'))
        self.assertEqual([], self.calls)
