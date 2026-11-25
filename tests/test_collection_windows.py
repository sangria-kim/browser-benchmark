"""Exercise scheduled collection, bounded discovery, recovery and offline saving without a network."""
import contextlib
from io import StringIO
import json
import multiprocessing
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urljoin

from pipeline import browser_status, collect, run_daily, weekly_evidence, weekly_status
from pipeline.daily_status import validate_tree
from pipeline.collectors.browser import Response
from pipeline.run_daily import encoded, git, read, run_lock

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = '2026-11-24T08:00:00+09:00'
STATUS_CUTOFF = '2026-11-24T07:00:00+09:00'
UTC = '2026-11-23T23:00:00Z'
START = '2026-10-25T08:00:00+09:00'
OBSERVED = '2026-11-24T09:00:00+09:00'
HOME = 'https://chromereleases.googleblog.com/'


def suspended_collection(argv, first_url, first_body, gate):
    def request(url):
        if url == first_url:
            return Response(url, first_body.encode(), observed_at=OBSERVED)
        gate.send('waiting')
        if not gate.poll(20) or gate.recv() != 'release':
            raise RuntimeError('Synthetic transport barrier expired')
        raise TimeoutError('Synthetic source outage')

    with patch('sys.argv', argv), patch('pipeline.collectors.browser.collector.HTTPTransport', return_value=request):
        with contextlib.redirect_stdout(StringIO()):
            runpy.run_path(str(ROOT / 'pipeline/run_daily.py'), run_name='__main__')


class WindowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name)
        self.repo = self.folder / 'repo'
        shutil.copytree(ROOT / 'config', self.repo / 'config')
        self.registry = self.repo / 'config/sources.yml'
        self.sources = {s['source_id']: s for s in read(self.registry)['sources']}
        self.payloads = {}
        self.calls = []
        self.observed_at = OBSERVED

    def request(self, url):
        self.calls.append(url)
        value = self.payloads[url]
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        return Response(url, value.encode(), observed_at=self.observed_at)

    def args(self, name, sources, cutoff, mode):
        args = ['--repository', str(self.repo), '--private-dir', str(self.folder / 'runs'), '--run-id', name]
        if cutoff:
            args += ['--cutoff', cutoff]
        if mode:
            args += ['--mode', mode]
        for sid in sources:
            args += ['--source', sid]
        return args

    def cli(self, name, sources=(), cutoff=CUTOFF, mode=None, extra=(), expected=0):
        argv = ['pipeline.run_daily', *self.args(name, sources, cutoff, mode), *extra]
        with patch('sys.argv', argv), patch('pipeline.collectors.browser.collector.HTTPTransport', return_value=self.request):
            with contextlib.redirect_stdout(StringIO()), self.assertRaises(SystemExit) as exit_status:
                runpy.run_path(str(ROOT / 'pipeline/run_daily.py'), run_name='__main__')
        self.assertEqual(expected, exit_status.exception.code)

    def state(self, name):
        return read(self.folder / 'runs' / name / 'feature-run.json')

    def candidates(self, name, sid):
        return read(self.folder / 'runs' / name / 'work/candidates' / (sid + '.json'))

    def save(self, name, classification, **options):
        return collect.save_features(self.repo, self.folder / 'runs' / name, classification, **options)

    def classified(self, name, sid):
        result = []
        for row in self.candidates(name, sid):
            result.append(dict(source_item_id=row['source_item_id'], revision_id=row['revisions'][-1]['revision_id'],
                               title='Tab groups', canonical_key='tab-groups'))
        return result

    @staticmethod
    def card(url, day, changed=None):
        edit = '<time itemprop="dateModified" datetime="%s"></time>' % changed if changed else ''
        return (f'<div class="post"><h3 class="post-title"><a href="{url}">Release</a></h3>'
                f'<div class="post-header"><span class="publishdate" itemprop="datePublished">{day}</span>'
                f'{edit}</div></div>')

    @staticmethod
    def article(date, text='Tab grouping added.', changed=None, body='post-body'):
        publication = f'<meta property="article:published_time" content="{date}">' if date else ''
        modification = f'<meta property="article:modified_time" content="{changed}">' if changed else ''
        return f'{publication}{modification}<div class="{body}"><p id="tabs">{text}</p></div>'

    def test_scheduled_window_reduces_both_requests_and_keeps_full_scan_recent_ids(self):
        edge = HOME + 'search?updated-max=2026-10-24T18:00:00-07:00'
        old = HOME + 'search?updated-max=2026-10-18T18:00:00-07:00'
        dates = dict(pinned='2026-04-10', edited='2026-03-10', recent='2026-11-11',
                     local='2026-10-24T17:00:00-07:00', unknown='malformed', archived='2026-07-01')
        urls = {name: HOME + '2026/10/' + name + '.html' for name in dates}

        def older(url):
            return f'<a id="Blog1_blog-pager-older-link" href="{url}">Older</a>'

        edit = '2026-11-15T10:00:00Z'
        self.payloads[HOME] = (self.card(urls['pinned'], dates['pinned']) +
                               self.card(urls['edited'], dates['edited'], edit) +
                               self.card(urls['recent'], dates['recent']) + older(edge))
        self.payloads[edge] = self.card(urls['local'], '2026-10-24') + self.card(urls['unknown'], 'broken') + older(old)
        self.payloads[old] = self.card(urls['archived'], dates['archived'])
        for name, url in urls.items():
            self.payloads[url] = self.article(dates[name], changed=edit if name == 'edited' else None)
        expected_ids = set()
        for mode, name, expected_work in [('legacy', 'baseline', (3, 6)), (None, 'scheduled', (2, 4)),
                                          ('weekly_reconcile', 'weekly', (3, 6))]:
            self.calls.clear()
            self.cli(name, ['chrome-releases'], mode=mode)
            self.assertEqual(expected_work, (sum(url not in urls.values() for url in self.calls),
                                             sum(url in urls.values() for url in self.calls)))
            rows = self.candidates(name, 'chrome-releases')
            eligible = [r for r in rows if r['evidence']['url'] in {urls[n] for n in ('edited', 'recent', 'local', 'unknown')}]
            ids = {r['source_item_id'] for r in eligible}
            self.assertEqual(4, len(ids))
            if name == 'baseline':
                expected_ids = ids
            else:
                self.assertEqual(expected_ids, ids)
            if name == 'scheduled':
                self.assertEqual(4, len(rows))
                self.assertEqual(START, self.state(name)['start'])
                self.assertEqual('daily', self.state(name)['mode'])
                self.assertEqual('unknown', next(r for r in rows if r['evidence']['url'] == urls['unknown'])['temporal_scope']['precision'])
        self.assertFalse((self.repo / 'data').exists())

    def test_exact_timestamp_and_calendar_boundaries_match_with_two_cutoff_offsets(self):
        api = 'https://chromestatus.com/api/v0/features?num=100&start=0'
        # A later creation is a future item. A later revision of an older item is tested separately.
        dates = ['2026-10-24T22:59:59Z', '2026-10-24T23:00:00Z', UTC, '2026-11-23T23:00:01Z',
                 '2026-10-25', '2026-11-24', '2026-10-24', '2026-11-25']
        self.payloads[api] = dict(total_count=len(dates), features=[
            dict(id=i, name='Tabs', summary='Organize tabs', created={'when': v}, updated={'when': v})
            for i, v in enumerate(dates)])
        for name, bound in [('utc', UTC), ('kst', CUTOFF)]:
            self.cli(name, ['chrome-platform-status'], cutoff=bound)
            rows = self.candidates(name, 'chrome-platform-status')
            self.assertEqual({'1', '2', '4', '5'}, {r['item_key'] for r in rows})
            self.assertEqual({'timestamp', 'day'}, {r['temporal_scope']['precision'] for r in rows})
            self.assertEqual(START, self.state(name)['start'])
        self.cli('manual', ['chrome-platform-status'], mode='manual', extra=['--since', '2026-11-24'])
        self.assertEqual({'2', '5'}, {r['item_key'] for r in self.candidates('manual', 'chrome-platform-status')})

    def test_unordered_old_page_keeps_next_page_and_future_revision_is_incomplete(self):
        sid = 'vivaldi-desktop'
        home = self.sources[sid]['url']
        older = home + '?page=2'
        old, new = 'https://vivaldi.com/blog/old/', 'https://vivaldi.com/blog/new/'
        self.payloads[home] = (f'<article><h2><a href="{old}">Old</a></h2><time datetime="2026-02-12"></time></article>'
                               f'<a rel="next" href="{older}">Next</a>')
        self.payloads[older] = f'<article><h2><a href="{new}">New</a></h2></article>'
        self.payloads[new] = self.article('2026-11-09', body='entry-content')
        self.cli('ordered', [sid], mode='manual')
        self.assertEqual([home, older, new], self.calls)
        self.assertEqual(1, len(self.candidates('ordered', sid)))
        self.payloads[new] = self.article('2026-11-09', changed='2026-11-24T08:00:01+09:00', body='entry-content')
        self.cli('future', [sid, 'firefox-ios'], mode='manual', expected=2)
        self.assertEqual([], self.candidates('future', sid))
        self.assertIn('after cutoff', str(self.state('future')['source_results'][sid]['errors']))

    def test_weekly_recovers_older_edits_without_changing_public_identity(self):
        sid = 'firefox-beta'
        url = self.sources[sid]['url']
        self.payloads[url] = self.article('2026-03-12', body='c-release-notes')
        self.cli('old', [sid], mode='manual', extra=['--since', '2026-01-01'])
        first, = self.classified('old', sid)
        self.save('old', [first])
        self.payloads[url] = self.article('2026-03-12', text='Tab groups can be shared.', body='c-release-notes')
        self.cli('day', [sid])
        self.assertEqual([], self.candidates('day', sid))
        self.cli('week', [sid], mode='weekly_reconcile')
        updated, = self.classified('week', sid)
        self.assertEqual(first['source_item_id'], updated['source_item_id'])
        self.assertNotEqual(first['revision_id'], updated['revision_id'])
        self.assertEqual(2, len(self.candidates('week', sid)[0]['revisions']))
        with self.assertRaisesRegex(ValueError, 'all enabled sources'):
            self.save('week', [])
        self.payloads[url] = self.article('2026-03-12', text='Tab groups can be shared.',
                                          changed='2026-11-19', body='c-release-notes')
        self.cli('revised', [sid])
        row, = self.candidates('revised', sid)
        self.assertEqual(('2026-03-12', '2026-11-19', 'item_change'),
                         (row['published_at'], row['temporal_scope']['evidence_date'], row['temporal_scope']['basis']))

    def test_interrupted_collection_replays_verified_responses_and_starts_new_run_fresh(self):
        source = 'chrome-releases'
        one, two = [HOME + '2026/11/' + name + '.html' for name in ('one', 'two')]
        self.payloads = {HOME: self.card(one, '2026-11-12') + self.card(two, '2026-11-13'),
                         one: self.article('2026-11-12'), two: KeyboardInterrupt()}
        with self.assertRaises(KeyboardInterrupt):
            self.cli('interrupted', [source])
        self.assertEqual(('collecting', False), (self.state('interrupted')['status'], self.state('interrupted')['complete']))
        self.payloads[two] = self.article('2026-11-13')
        self.calls.clear()
        self.cli('interrupted', cutoff=UTC, extra=['--resume'])
        self.assertEqual([two], self.calls)
        self.cli('control', [source])
        self.assertEqual(self.state('control')['observed'], self.state('interrupted')['observed'])
        self.payloads[one] = self.article('2026-11-12', 'New evidence.')
        self.calls.clear()
        self.cli('interrupted', cutoff=None, extra=['--resume'])
        self.assertEqual([], self.calls)
        self.cli('fresh', [source])
        self.assertIn(one, self.calls)
        self.assertNotEqual(self.state('fresh')['observed'], self.state('control')['observed'])

    def test_resume_rejects_changed_commit_window_registry_or_corrupt_checkpoint(self):
        sid = 'firefox-beta'
        self.payloads[self.sources[sid]['url']] = self.article('2026-11-10', body='c-release-notes')
        git(self.repo, 'init', '-q')
        def commit():
            git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid',
                '-c', 'core.hooksPath=/dev/null', 'commit', '-q', '--allow-empty', '-m', 'fixture')
        commit()
        self.cli('resume', [sid], mode='manual', extra=['--since', START])
        self.calls.clear()
        for options in [['--mode', 'daily'], ['--since', '2026-10-25'], ['--cutoff', '2026-11-24T08:00:01+09:00']]:
            with self.assertRaisesRegex(ValueError, 'Resume requires'):
                self.cli('resume', cutoff=None, extra=['--resume', *options])
        original = self.registry.read_bytes()
        self.registry.write_bytes(original + b'\n')
        with self.assertRaisesRegex(ValueError, 'original commit, window, registry'):
            self.cli('resume', cutoff=None, extra=['--resume'])
        self.registry.write_bytes(original)
        commit()
        with self.assertRaisesRegex(ValueError, 'original commit'):
            self.cli('resume', cutoff=None, extra=['--resume'])
        self.assertEqual([], self.calls)
        self.cli('damaged', [sid])
        path = self.folder / 'runs/damaged/work/candidates/firefox-beta.json'
        path.write_text('[]')
        for attempt in range(2):
            self.cli('damaged', cutoff=None, extra=['--resume'], expected=2)
            self.assertTrue(self.state('damaged')['source_results'][sid]['checkpoint_invalid'])

    def test_source_failure_before_parser_and_timeout_after_page_do_not_block_later_source(self):
        sid = 'firefox-beta'
        self.payloads[self.sources[sid]['url']] = self.article('2026-11-10', body='c-release-notes')
        bad = self.repo / 'data/source-items/edge/edge-beta.json'
        bad.parent.mkdir(parents=True)
        bad.write_text('{invalid')
        detail = HOME + '2026/11/current.html'
        self.payloads[HOME] = self.card(detail, '2026-11-10')
        self.payloads[detail] = TimeoutError('synthetic read timeout')
        self.cli('mixed', [sid, 'edge-beta', 'chrome-releases'], expected=2)
        state = self.state('mixed')
        self.assertEqual({'chrome-releases': 'partial', 'edge-beta': 'partial', sid: 'complete'},
                         {key: result['status'] for key, result in state['source_results'].items()})
        self.assertEqual(1, len(self.candidates('mixed', sid)))
        self.assertNotIn('edge-beta', state['observed'])
        self.assertIn('timeout', str(state['source_results']['chrome-releases']))
        # The Chrome cache metadata itself is bound to the run. Changing a header invalidates it.
        path = self.folder / 'runs/mixed/work/browser/chrome-releases-progress.json'
        progress = read(path)
        progress['responses'][HOME]['url'] = HOME + '?stale'
        path.write_bytes(encoded(progress))
        self.cli('mixed', cutoff=None, extra=['--resume'], expected=2)
        self.assertIn('checkpoint mismatch', str(self.state('mixed')['source_results']['chrome-releases']))
        with self.assertRaisesRegex(ValueError, 'partial'):
            self.save('mixed', [])

    def configure_small_registry(self):
        # One registered source per browser. Fixed single-document responses isolate the save/receipt contract.
        boundaries = {'chrome-releases': 'class="post-body"', 'edge-beta': 'class="content"',
                      'firefox-beta': 'class="c-release-notes"', 'safari-security': 'id="article-body"',
                      'brave-blog': 'class="prose"', 'whale-notices': 'data-role="commentContent"',
                      'opera-mobile': 'class="entry-content"', 'vivaldi-ios': 'class="entry-content"'}
        registry = read(self.registry)
        for source in registry['sources']:
            sid = source['source_id']
            source['enabled'] = sid in boundaries
            if source['enabled']:
                source['parser'] = 'html_document'
                self.payloads[source['url']] = ('<meta property="article:published_time" content="2026-11-10">'
                                                f'<div {boundaries[sid]}><p id="tabs">Tab grouping added.</p></div>')
        self.registry.write_bytes(encoded(registry))

    def decisions(self, name):
        selected = self.classified(name, 'firefox-beta')
        dispositions = []
        for path in (self.folder / 'runs' / name / 'work/candidates').glob('*.json'):
            for row in read(path):
                dispositions.append(dict(source_id=row['source_id'], source_item_id=row['source_item_id'],
                                         revision_id=row['revisions'][-1]['revision_id'],
                                         disposition='selected' if row['source_id'] == 'firefox-beta' else 'excluded'))
        return dict(decisions=[dict(choice, change_kind='product_change') for choice in selected],
                    dispositions=dispositions)

    def browser_choices(self, name, browser, *, select=True):
        state = self.state(name)
        decisions, dispositions = [], []
        for sid in state['sources']:
            if self.sources[sid]['browser'] != browser:
                continue
            for row in self.candidates(name, sid):
                ident = row['source_item_id']
                revision = row['revisions'][-1]['revision_id']
                dispositions.append(dict(source_id=sid, source_item_id=ident, revision_id=revision,
                                         disposition='selected' if select else 'excluded'))
                if select:
                    decisions.append(dict(source_item_id=ident, revision_id=revision, canonical_key='tab-groups',
                                          title='Tab groups', change_kind='product_change',
                                          evidence_quote=row['evidence']['excerpt']))
        return dict(decisions=decisions, dispositions=dispositions)

    def publish_browser(self, name, browser, choices):
        path = self.folder / (browser + '-classification.json')
        path.write_bytes(encoded(choices))
        self.cli(name, cutoff=None, extra=['--save-browser', browser, '--save-features', str(path)])

    def item(self, name, request, *, standalone=False):
        path = self.folder / 'item.json'
        path.write_bytes(encoded(request))
        if standalone:
            argv = ['collect', '--repository', str(self.repo), '--private-dir', str(self.folder / 'manual-url'),
                    '--save-item', str(path)]
            with patch('sys.argv', argv), contextlib.redirect_stdout(StringIO()), self.assertRaises(SystemExit) as rc:
                runpy.run_path(str(ROOT / 'pipeline/collect.py'), run_name='__main__')
            self.assertEqual(0, rc.exception.code)
        else:
            self.cli(name, cutoff=None, extra=['--save-item', str(path)])

    def test_item_cli_can_publish_before_another_source_returns(self):
        self.configure_small_registry()
        firefox = self.sources['firefox-beta']['url']
        args = self.args('active', ['firefox-beta', 'whale-notices'], STATUS_CUTOFF, None) + ['--daily-status']
        context = multiprocessing.get_context('spawn')
        gate, peer = context.Pipe()
        proc = context.Process(target=suspended_collection,
                               args=(['run_daily', *args], firefox, self.payloads[firefox], peer))
        proc.start()
        peer.close()
        try:
            self.assertTrue(gate.poll(20))
            self.assertEqual('waiting', gate.recv())
            state = self.folder / 'runs/active/feature-run.json'
            collector_owned = state.read_bytes()
            self.item('active', dict(browser='firefox', source_id='firefox-beta',
                                     **self.classified('active', 'firefox-beta')[0]))
            self.assertTrue(proc.is_alive())
            self.assertEqual(collector_owned, state.read_bytes())
            self.assertEqual(1, len(read(self.repo / collect.FEATURE_CATALOG)))
            receipt = read(self.repo / 'data/daily-status/2026-11-24.json')
            self.assertEqual(('incomplete', None, None), tuple(receipt[k] for k in ('status', 'change_count', 'collected_feature_count')))
        finally:
            if proc.is_alive():
                gate.send('release')
            gate.close()
            proc.join(20)
            if proc.is_alive():
                proc.terminate()
                proc.join()
        self.assertEqual(2, proc.exitcode)

    def test_item_cli_partial_source_bad_ids_retry_git_and_finished_survey(self):
        self.configure_small_registry()
        run_daily.commit_candidate(self.repo)
        firefox = self.sources['firefox-beta']['url']
        self.payloads[firefox] = self.payloads[firefox].replace('</div>', '<p id="sibling">Toolbar colors.</p></div>')
        edge = self.sources['edge-beta']['url']
        original = self.payloads[edge]
        self.payloads[edge] = TimeoutError('Edge offline')
        self.cli('day', cutoff=STATUS_CUTOFF, extra=['--daily-status'], expected=2)
        selected = next(r for r in self.candidates('day', 'firefox-beta') if r['item_key'] == 'tabs')
        request = dict(browser='firefox', source_id='firefox-beta', source_item_id=selected['source_item_id'],
                       revision_id=selected['revisions'][-1]['revision_id'], canonical_key='groups', title='Tab groups')
        with self.assertRaises(ValueError):
            self.item('day', dict(request, revision_id='wrong', url=firefox))
        source_file = self.folder / 'runs/day/work/candidates/firefox-beta.json'
        original_candidates = source_file.read_bytes()
        source_file.write_bytes(encoded([]))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.item('day', dict(request, url=firefox))
        source_file.write_bytes(original_candidates)
        self.assertFalse((self.repo / collect.FEATURE_CATALOG).exists())
        self.item('day', request)
        rel = browser_status.detail_path('daily', STATUS_CUTOFF)
        day = 'data/daily-status/2026-11-24.json'
        before = {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')}
        self.item('day', request)
        self.assertEqual(before, {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})
        self.assertEqual((None, None), tuple(read(self.repo / day)[k] for k in ('collected_feature_count', 'change_count')))
        missing = dict(decisions=[], dispositions=[])
        with self.assertRaisesRegex(ValueError, 'cover all'):
            self.publish_browser('day', 'firefox', missing)
        with self.assertRaisesRegex(ValueError, 'retain'):
            self.publish_browser('day', 'firefox', self.browser_choices('day', 'firefox', select=False))
        run_daily.commit_candidate(self.repo)
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            self.item('day', request)
        self.payloads[edge] = original
        self.cli('retry', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.assertIn('tabs', [r['item_key'] for r in self.candidates('retry', 'firefox-beta')])
        for name in read(self.repo / rel)['scope']['expected']:
            choice = self.browser_choices('retry', name, select=False)
            for disposition in choice['dispositions']:
                if disposition['source_item_id'] == selected['source_item_id']:
                    disposition['disposition'] = 'selected'
            self.publish_browser('retry', name, choice)
        self.assertEqual((1, 1), tuple(read(self.repo / day)[k] for k in ('collected_feature_count', 'change_count')))
        self.assertEqual(['groups'], [f['canonical_key'] for f in read(self.repo / collect.FEATURE_CATALOG)])
        run_daily.commit_candidate(self.repo)
        validate_tree(self.repo, complete_history=True)

    def test_weekly_item_cli_keeps_first_count_across_resume_and_new_cutoff(self):
        self.configure_small_registry()
        run_daily.commit_candidate(self.repo)
        cutoff = '2026-11-29T10:00:00+09:00'
        self.cli('week', cutoff=cutoff, mode='weekly_reconcile')
        req = dict(browser='firefox', source_id='firefox-beta', **self.classified('week', 'firefox-beta')[0])
        self.item('week', req)
        self.cli('week', cutoff=cutoff, mode='weekly_reconcile', extra=['--resume'])
        self.item('week', req)
        with self.assertRaisesRegex(ValueError, 'finish this cutoff'):
            self.save('week', self.decisions('week'))
        # Already published candidates still receive an explicit disposition,
        # and do not require a second copy of their feature decision.
        choices = self.browser_choices('week', 'firefox')
        choices['decisions'] = []
        self.publish_browser('week', 'firefox', choices)
        detail = self.repo / browser_status.detail_path('weekly_reconcile', cutoff)
        self.assertEqual((1, 1), tuple(read(detail)['browsers']['firefox'][k] for k in ('change_count', 'collected_feature_count')))
        with self.assertRaisesRegex(ValueError, 'completed browser'):
            self.item('week', req)
        run_daily.commit_candidate(self.repo)
        saved = detail.read_bytes()
        next_week = '2026-12-06T10:00:00+09:00'
        self.cli('week2', cutoff=next_week, mode='weekly_reconcile')
        all_excluded = dict(decisions=[], dispositions=[])
        for browser in read(detail)['scope']['expected']:
            all_excluded['dispositions'].extend(self.browser_choices('week2', browser, select=False)['dispositions'])
        self.save('week2', all_excluded)
        self.assertEqual(0, weekly_status.read_current(self.repo.resolve(), next_week)['collected_feature_count'])
        self.assertFalse((self.repo / 'data/daily-status').exists())
        self.assertEqual(saved, detail.read_bytes())

    def test_cli_same_url_shared_features_after_thirty_days_enrichment_and_public_reader(self):
        from pipeline.feature_enrichment import read_jobs
        from pipeline.normalize import load_dataset
        from scripts import build_dashboard
        first_cutoff, next_cutoff = '2026-04-10T07:00:00+09:00', '2026-11-25T07:00:00+09:00'
        sid, url = 'chrome-releases', HOME + '2026/04/release.html'

        def article(tabs='Tab groups are available.'):
            return ('<meta property="article:published_time" content="2026-04-01"><div class="post-body">'
                    f'<p id="tabs">{tabs}</p><p id="toolbar">Toolbar color is available on Android.</p></div>')

        self.configure_small_registry()
        registry = read(self.registry)
        registered = next(r for r in registry['sources'] if r['source_id'] == sid)
        registered['parser'] = self.sources[sid]['parser']
        self.registry.write_bytes(encoded(registry))
        for address, html in list(self.payloads.items()):
            self.payloads[address] = html.replace('2026-11-10', '2026-04-01')
        self.payloads.update({HOME: self.card(url, '2026-04-01'), url: article()})
        self.cli('april', cutoff=first_cutoff, extra=['--daily-status'])
        request = dict(browser='chrome', source_id=sid, url=url, canonical_key='tabs', title='Tab groups')
        self.item('april', dict(request, facts={'version': '150'}))
        self.item('april', dict(request, canonical_key='toolbar', title='Toolbar color'))
        # URL-only references need no quoted passages. Ordinary published units
        # still require final dispositions before this survey can close.
        daily_browsers = browser_status.registry_facts(self.repo, 'daily')[2]
        for name in daily_browsers:
            self.publish_browser('april', name, self.browser_choices('april', name, select=False))
        april = self.repo / 'data/daily-status/2026-04-10.json'
        frozen = april.read_bytes()
        self.assertEqual((2, 2), tuple(read(april)[k] for k in ('collected_feature_count', 'change_count')))
        before = {f['canonical_key']: f for f in load_dataset(self.repo)['feature']}
        tab = before['tabs']['feature_id']
        self.assertEqual(before['tabs']['source_item_ids'], before['toolbar']['source_item_ids'])
        run_daily.commit_candidate(self.repo)
        self.calls.clear()
        self.cli('same', cutoff=next_cutoff, extra=['--daily-status'])
        self.assertEqual(1, self.calls.count(url))
        self.assertEqual([], self.candidates('same', sid))
        def jobs(name):
            return {j['feature_id']: j for j in read_jobs((self.folder / 'runs' / name / 'work').resolve(), self.state(name), sid)}
        source_hash = run_daily.digest(article().encode())
        self.assertEqual(source_hash, jobs('same')[tab]['content_sha256'])
        self.assertIn('platform', jobs('same')[tab]['missing_fields'])
        self.payloads[url] = article('Tab groups are rolling out on Windows.')
        self.cli('facts', cutoff=next_cutoff, extra=['--daily-status'])
        job = jobs('facts')[tab]
        row = job['candidate']
        reviewed = dict(browser='chrome', source_id=sid, feature_id=tab, source_item_id=row['source_item_id'],
                        revision_id=row['revisions'][-1]['revision_id'], facts={'platform': ['Windows']})
        with self.assertRaises(ValueError):
            self.item('facts', dict(reviewed, feature_id=before['toolbar']['feature_id']))
        self.item('facts', reviewed)
        for name in daily_browsers:
            self.publish_browser('facts', name, self.browser_choices('facts', name, select=False))
        current = read(self.repo / 'data/daily-status/2026-11-25.json')
        self.assertEqual(('complete', 1, 0), tuple(current[k] for k in ('status', 'collected_feature_count', 'change_count')))
        self.assertEqual(frozen, april.read_bytes())
        self.payloads[url] = article()
        self.cli('later', cutoff='2026-11-26T07:00:00+09:00', extra=['--daily-status'])
        self.assertNotIn('platform', jobs('later')[tab]['missing_fields'])
        self.item('unused', dict(request, facts={'platform': []}), standalone=True)
        catalog = {f['canonical_key']: f for f in load_dataset(self.repo)['feature']}
        self.assertEqual(before['toolbar'], catalog['toolbar'])
        self.assertEqual((tab, ['Windows'], '150'), (catalog['tabs']['feature_id'],
                         catalog['tabs']['feature_facts']['platform']['value'], catalog['tabs']['feature_facts']['version']['value']))
        self.assertEqual([], catalog['tabs']['event_ids'])
        self.assertEqual(2, len(catalog))
        (self.repo / 'dashboard').mkdir()
        (self.repo / 'dashboard/card-summaries.json').write_bytes(encoded({}))
        output = self.folder / 'dashboard-fixture'
        legacy = dict(events=[], flags=[], source={}, built_at=next_cutoff, updated_at=next_cutoff, catalog={})
        with patch.object(build_dashboard, 'ROOT', self.repo):
            build_dashboard.build_research(output, legacy, '')
        summaries = build_dashboard.read_resource(output / 'indexes/feature.json.gz')
        for summary in summaries:
            published = build_dashboard.read_resource(output / summary['detail'])['fact']
            self.assertEqual(catalog[published['canonical_key']], published)
        self.assertEqual(frozen, april.read_bytes())
        validate_tree(self.repo, complete_history=True)

    def test_scheduled_url_respects_known_future_and_independent_manual(self):
        self.configure_small_registry()
        sid = 'chrome-releases'
        registry = read(self.registry)
        next(s for s in registry['sources'] if s['source_id'] == sid)['parser'] = self.sources[sid]['parser']
        self.registry.write_bytes(encoded(registry))
        url = HOME + '2026/11/future-release.html'
        self.payloads[HOME] = self.card(url, '2026-11-24')
        self.payloads[url] = self.article('2026-11-24T07:00:01+09:00')
        request = dict(browser='chrome', source_id=sid, url=url + '#tabs', canonical_key='preview', title='Tab preview')
        self.cli('survey', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.assertIn(url, self.calls)
        self.assertEqual([], self.candidates('survey', sid))
        for address in (request['url'], request['url'].replace('/future-', '/%66uture-')):
            with self.assertRaisesRegex(ValueError, 'window'):
                self.item('survey', dict(request, url=address))
        window = self.folder / 'runs/survey/work/windows' / (sid + '.json')
        sealed = window.read_bytes()
        window.write_bytes(encoded({}))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.item('survey', request)
        window.write_bytes(sealed)
        self.assertFalse((self.repo / collect.FEATURE_CATALOG).exists())
        for name in browser_status.registry_facts(self.repo, 'daily')[2]:
            self.publish_browser('survey', name, self.browser_choices('survey', name, select=False))
        receipt = self.repo / 'data/daily-status/2026-11-24.json'
        original = receipt.read_bytes()
        self.assertEqual(0, read(receipt)['change_count'])
        self.cli('next', cutoff='2026-11-25T07:00:00+09:00', extra=['--daily-status'])
        self.item('next', request)
        self.item('manual', request, standalone=True)
        self.assertEqual(1, len(read(self.repo / collect.FEATURE_CATALOG)))
        self.assertEqual(original, receipt.read_bytes())

    def test_url_can_be_stored_while_its_source_is_pending_but_cannot_settle_as_future_product(self):
        self.configure_small_registry()
        sid = 'chrome-releases'
        registry = read(self.registry)
        next(s for s in registry['sources'] if s['source_id'] == sid)['parser'] = self.sources[sid]['parser']
        self.registry.write_bytes(encoded(registry))
        url = HOME + '2026/11/future-release.html'
        self.payloads[HOME] = self.card(url, '2026-11-24')
        self.payloads[url] = self.article('2026-11-24T07:00:01+09:00')
        request = dict(browser='chrome', source_id=sid, url=url, title='Tab preview', canonical_key='preview')
        original_fetch = self.request
        early = []
        def fetch(address):
            if address == url and not early:
                self.item('held', request)
                early.extend(read(self.repo / collect.FEATURE_CATALOG))
            return original_fetch(address)
        with patch.object(self, 'request', fetch):
            self.cli('held', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.assertEqual(['preview'], [f['canonical_key'] for f in early])
        self.assertEqual([], self.candidates('held', sid))
        with self.assertRaisesRegex(ValueError, 'window'):
            self.publish_browser('held', 'chrome', self.browser_choices('held', 'chrome', select=False))
        pending = read(self.repo / 'data/daily-status/2026-11-24.json')
        self.assertEqual(('incomplete', None, None), tuple(pending[k] for k in ('status', 'change_count', 'collected_feature_count')))

    def test_mixed_document_keeps_each_real_anchor_in_its_own_window(self):
        self.configure_small_registry()
        sid = 'edge-beta'
        url = self.sources[sid]['url']
        self.payloads[url] = ('<div class="content"><h2 id="future-release">Version 160, November 28, 2026</h2>'
                              '<p id="share">Share tab groups.</p><h2 id="current-release">Version 159, November 20, 2026</h2>'
                              '<p id="save">Save tab groups.</p></div>')
        self.cli('mixed', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        present, = self.candidates('mixed', sid)
        self.assertEqual('save', present['item_key'])
        req = dict(browser='edge', source_id=sid, canonical_key='save-tabs', title='Save tab groups')
        for anchor in ('share', '%73hare', 'future-release'):
            with self.subTest(anchor=anchor), self.assertRaisesRegex(ValueError, 'window'):
                self.item('mixed', dict(req, url=url + '#' + anchor))
        self.item('mixed', dict(req, url=url + '#save'))
        self.item('mixed', dict(req, source_item_id=present['source_item_id'],
                                revision_id=present['revisions'][-1]['revision_id']))
        choices = self.browser_choices('mixed', 'edge')
        choices['decisions'] = []
        self.publish_browser('mixed', 'edge', choices)
        self.assertEqual(1, len(read(self.repo / collect.FEATURE_CATALOG)))

    def test_nested_release_fragments_use_the_owning_unit_and_section(self):
        self.configure_small_registry()
        sid = 'edge-beta'
        url = self.sources[sid]['url']
        self.payloads[url] = (
            '<div class="content" id="both"><section id="future-section">'
            '<h2 id="future-release"><a name="future-heading"></a><span id="future-date">November 28, 2026</span></h2>'
            '<a name="before-share"></a><p id="future-block"><span id="share"><a name="share-legacy" href="#href-only">'
            'Share tab groups.</a> Use C++, A&amp;B and drag-and-drop.</span></p></section>'
            '<section id="current-section"><h2 id="current-release">November 20, 2026</h2>'
            '<p id="save"><span id="save-detail"><i id="share:~:text=literal">Save tab groups.</i></span></p></section>'
            '<section><h2>April 1, 2026</h2><p><span id="mute">Mute tabs on Windows.</span></p></section></div>')
        self.item('manual', dict(browser='edge', source_id=sid, url=url + '#mute:~:text=Mute%20tabs', canonical_key='mute', title='Mute tabs'),
                  standalone=True)
        self.cli('nested', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        present, = self.candidates('nested', sid)
        self.assertEqual('save', present['item_key'])
        bounds = read(self.folder / 'runs/nested/work/windows/edge-beta.json')
        future = ('future-section', 'future-release', 'future-heading', 'future-date', 'future-block', 'before-share', 'share', 'share-legacy')
        req = dict(browser='edge', source_id=sid, canonical_key='save-tabs', title='Save tab groups')
        for fragment in future:
            with self.subTest(fragment=fragment):
                self.assertEqual('after_cutoff', bounds.get(url + '#' + fragment))
                with self.assertRaisesRegex(ValueError, 'window'):
                    self.item('nested', dict(req, url=url + '#' + fragment))
        for fragment in ('%73hare:~:text=Share%20tab', 'share:~:foo=1&text=Share&text=tab',
                         ':~:text=Share%20tab%20groups', ':~:text=Share,groups', ':~:text=Share&text=Share%20tab',
                         ':~:text=C++%2C%20A%26B', ':~:text=drag%2Dand%2Ddrop', 'save:~:text=Share%20tab'):
            with self.subTest(fragment=fragment), self.assertRaisesRegex(ValueError, 'window'):
                self.item('nested', dict(req, url=url + '#' + fragment))
        for fragment in ('both', 'current-release', 'current-section', 'save', 'save-detail', 'href-only'):
            self.assertNotIn(url + '#' + fragment, bounds)
        self.assertNotIn(url, bounds)
        self.assertEqual('before_period', bounds.get(url + '#mute'))
        review, = read(self.folder / 'runs/nested/work/enrichment/edge-beta.json')
        candidate = review['candidate']
        self.assertEqual('Mute tabs on Windows.', candidate['classification_text'])
        self.item('nested', dict(browser='edge', source_id=sid, feature_id=review['feature_id'],
                                 source_item_id=candidate['source_item_id'], revision_id=candidate['revisions'][-1]['revision_id'],
                                 facts={'platform': ['Windows']}))
        self.item('nested', dict(req, url=urljoin(url, '#share%3A~%3Atext%3Dliteral')))
        self.item('nested', dict(req, url=urljoin(url, '#save-detail:~:text=Save%20tab')))
        self.item('nested', dict(req, url=urljoin(url, '#save-detail:~:text=tab%20groups')))
        self.item('nested', dict(req, source_item_id=present['source_item_id'], revision_id=present['revisions'][-1]['revision_id']))
        for browser in browser_status.registry_facts(self.repo, 'daily')[2]:
            choices = self.browser_choices('nested', browser, select=(browser == 'edge'))
            choices['decisions'] = []
            self.publish_browser('nested', browser, choices)
        day = read(self.repo / 'data/daily-status/2026-11-24.json')
        self.assertEqual(('complete', 2, 1), tuple(day[k] for k in ('status', 'collected_feature_count', 'change_count')))
        evidence_urls = {r['evidence']['url'] for r in read(self.repo / 'data/source-items/edge/edge-beta.json')}
        self.assertTrue({url + '#mute:~:text=Mute%20tabs', url + '#share%3A~%3Atext%3Dliteral',
                         url + '#save-detail:~:text=Save%20tab'} <= evidence_urls)
        self.payloads[url] = '<div class="content"><p><span id="unknown">An undated update.</span></p></div>'
        self.cli('undated', [sid], cutoff='2026-11-25T07:00:00+09:00')
        self.assertNotIn(url + '#unknown', read(self.folder / 'runs/undated/work/windows/edge-beta.json'))
        self.item('manual', dict(req, url=url + '#unknown', canonical_key='independent', title='Independent feature'), standalone=True)

    def test_mixed_document_url_stays_provisional_without_a_dated_feature(self):
        self.configure_small_registry()
        sid = 'edge-beta'
        url = self.sources[sid]['url']
        self.payloads[url] = ('<div class="content"><h2>November 28, 2026</h2><p>Share tabs.</p>'
                              '<h2>November 20, 2026</h2><p id="save">Save tabs.</p></div>')
        for day, suffix in ((22, ''), (23, '#'), (24, '#:~:bogus=Share')):
            with self.subTest(suffix=suffix):
                name = f'mixed-{day}'
                self.cli(name, cutoff=f'2026-11-{day}T07:00:00+09:00', extra=['--daily-status'])
                req = dict(browser='edge', source_id=sid, canonical_key='share-tabs', title='Share tabs', url=url + suffix)
                self.item(name, req)
                self.assertIn('share-tabs', {f['canonical_key'] for f in read(self.repo / collect.FEATURE_CATALOG)})
                for browser in browser_status.registry_facts(self.repo, 'daily')[2]:
                    if browser != 'edge':
                        self.publish_browser(name, browser, self.browser_choices(name, browser, select=False))
                with self.assertRaisesRegex(ValueError, 'window'):
                    self.publish_browser(name, 'edge', self.browser_choices(name, 'edge', select=False))
                receipt = read(self.repo / f'data/daily-status/2026-11-{day}.json')
                self.assertEqual(('incomplete', None, None), tuple(receipt[k] for k in ('status', 'collected_feature_count', 'change_count')))

    def test_checked_old_passage_on_mixed_url_counts_only_as_enrichment(self):
        self.configure_small_registry()
        sid = 'edge-beta'
        url = self.sources[sid]['url']
        self.item('manual', dict(browser='edge', source_id=sid, canonical_key='mute', title='Mute tabs', url=url),
                  standalone=True)
        self.payloads[url] = ('<div class="content"><h2>November 28, 2026</h2><p>Share tabs.</p>'
                              '<h2>November 20, 2026</h2><p>Save tabs.</p>'
                              '<h2>April 1, 2026</h2><p>Mute tabs on Windows in stable 150 are enabled.</p></div>')
        self.cli('review', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        work = self.folder / 'runs/review/work'
        job, = read(work / 'enrichment/edge-beta.json')
        row = job['candidate']
        self.item('review', dict(browser='edge', source_id=sid, feature_id=job['feature_id'], source_item_id=row['source_item_id'],
                                 revision_id=row['revisions'][-1]['revision_id'], facts=dict(platform=['Windows'], channel='stable', version='150', rollout_status='enabled')))
        cache = work / 'browser/cache' / job['content_sha256']
        raw = cache.read_bytes()
        cache.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.publish_browser('review', 'edge', self.browser_choices('review', 'edge', select=False))
        cache.write_bytes(raw)
        run_daily.commit_candidate(self.repo)
        self.cli('fresh-review', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        fresh_work = self.folder / 'runs/fresh-review/work'
        self.assertFalse((fresh_work / 'enrichment/edge-beta.json').exists())
        proofs = read(fresh_work / 'windows/edge-beta.json')['enrichment_proofs']
        self.assertEqual([[job['feature_id'], row['source_item_id'], row['revisions'][-1]['revision_id'], job['content_sha256']]], proofs)
        for browser in browser_status.registry_facts(self.repo, 'daily')[2]:
            self.publish_browser('fresh-review', browser, self.browser_choices('fresh-review', browser, select=False))
        day = read(self.repo / 'data/daily-status/2026-11-24.json')
        self.assertEqual(('complete', 1, 0), tuple(day[k] for k in ('status', 'collected_feature_count', 'change_count')))

    def test_unresolved_fragment_on_mixed_page_needs_current_feature_to_finish(self):
        self.configure_small_registry()
        sid = 'edge-beta'
        url = self.sources[sid]['url']
        self.payloads[url] = ('<div class="content"><h2>November 28, 2026</h2><p>Share tabs on Windows.</p>'
                              '<h2>November 20, 2026</h2><p id="save">Save tabs on Windows.</p></div>')
        self.cli('mixed', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        req = dict(browser='edge', source_id=sid, canonical_key='save-tabs', title='Save tabs',
                   url=url + '#:~:text=on%20Windows')
        self.item('mixed', req)
        self.item('mixed', dict(req, url=url + '#missing'))
        self.item('mixed', dict(req, url=url))
        for browser in browser_status.registry_facts(self.repo, 'daily')[2]:
            if browser != 'edge':
                self.publish_browser('mixed', browser, self.browser_choices('mixed', browser, select=False))
        with self.assertRaisesRegex(ValueError, 'window'):
            self.publish_browser('mixed', 'edge', self.browser_choices('mixed', 'edge', select=False))
        position = self.repo / 'data/daily-status/2026-11-24.json'
        self.assertEqual(('incomplete', None), (read(position)['status'], read(position)['change_count']))
        run_daily.commit_candidate(self.repo)
        self.cli('fresh', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.cli('fresh', cutoff=STATUS_CUTOFF, extra=['--resume', '--daily-status'])
        with self.assertRaisesRegex(ValueError, 'window'):
            self.publish_browser('fresh', 'edge', self.browser_choices('fresh', 'edge'))
        choices = self.browser_choices('fresh', 'edge')
        choices['decisions'][0].update(canonical_key='save-tabs', title='Save tabs')
        self.publish_browser('fresh', 'edge', choices)
        self.assertEqual(('complete', 1, 1), tuple(read(position)[k] for k in ('status', 'collected_feature_count', 'change_count')))
        self.cli('next', cutoff='2026-11-30T07:00:00+09:00', extra=['--daily-status'])
        self.item('next', dict(req, url=url + '#:~:text=not%20on%20the%20page'))
        self.item('next', dict(req, url=url))
        self.publish_browser('next', 'edge', self.browser_choices('next', 'edge', select=False))

    def test_survey_cannot_finalize_nested_future_anchor_saved_before_source_returns(self):
        self.configure_small_registry()
        sid = 'edge-beta'
        url = self.sources[sid]['url']
        req = dict(browser='edge', source_id=sid, canonical_key='share-tabs', title='Share tab groups', url=url + '#share')
        request = self.request
        def fetch(address):
            if address == url:
                self.item('held', req)
            return request(address)
        self.payloads[url] = ('<div class="content"><h2>November 28, 2026</h2><p><span id="share">Share tab groups.</span></p>'
                              '<h2>November 20, 2026</h2><p id="save">Save tab groups.</p></div>')
        with patch.object(self, 'request', fetch):
            self.cli('held', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        for browser in browser_status.registry_facts(self.repo, 'daily')[2]:
            if browser != 'edge':
                self.publish_browser('held', browser, self.browser_choices('held', browser, select=False))
        with self.assertRaisesRegex(ValueError, 'window'):
            self.publish_browser('held', 'edge', self.browser_choices('held', 'edge', select=False))
        day = read(self.repo / 'data/daily-status/2026-11-24.json')
        self.assertEqual(('incomplete', None, None), tuple(day[k] for k in ('status', 'collected_feature_count', 'change_count')))

    def test_fresh_survey_cannot_finalize_a_reference_now_known_after_cutoff(self):
        self.configure_small_registry()
        sid = 'chrome-releases'
        registry = read(self.registry)
        next(s for s in registry['sources'] if s['source_id'] == sid)['parser'] = self.sources[sid]['parser']
        self.registry.write_bytes(encoded(registry))
        base, emerging = HOME + '2026/11/indexed.html', HOME + '2026/11/emerging.html'
        self.payloads[HOME] = self.card(base, '2026-11-22')
        self.payloads[base] = self.article('2026-11-22')
        self.cli('first', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        req = dict(browser='chrome', source_id=sid, url=emerging, canonical_key='tabs', title='Tab preview')
        self.item('first', req)
        run_daily.commit_candidate(self.repo)
        self.payloads[HOME] += self.card(emerging, '2026-11-24')
        self.payloads[emerging] = self.article('2026-11-24T07:00:01+09:00')
        self.cli('updated', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        with self.assertRaisesRegex(ValueError, 'window'):
            self.publish_browser('updated', 'chrome', self.browser_choices('updated', 'chrome', select=False))
        day = read(self.repo / 'data/daily-status/2026-11-24.json')
        self.assertEqual(('incomplete', None), (day['status'], day['change_count']))
        self.cli('following', cutoff='2026-11-25T07:00:00+09:00', extra=['--daily-status'])
        row = next(r for r in self.candidates('following', sid) if r['evidence']['url'] == emerging)
        self.item('following', dict(req, source_item_id=row['source_item_id'], revision_id=row['revisions'][-1]['revision_id'],
                                    change_kind='product_change'))
        for name in browser_status.registry_facts(self.repo, 'daily')[2]:
            choice = self.browser_choices('following', name, select=False)
            for disposition in choice['dispositions']:
                if disposition['source_item_id'] == row['source_item_id']:
                    disposition['disposition'] = 'selected'
            self.publish_browser('following', name, choice)
        self.assertEqual(1, read(self.repo / 'data/daily-status/2026-11-25.json')['change_count'])
        self.assertEqual(day, read(self.repo / 'data/daily-status/2026-11-24.json'))

    def test_committed_shared_original_revision_remains_open_for_another_feature(self):
        self.configure_small_registry()
        sid = 'firefox-beta'
        url = self.sources[sid]['url']
        self.payloads[url] = self.payloads[url].replace('Tab grouping added.', 'Save tab groups. Share tab groups.')
        self.cli('first', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        row, = self.candidates('first', sid)
        request = dict(browser='firefox', source_id=sid, source_item_id=row['source_item_id'],
                       revision_id=row['revisions'][-1]['revision_id'], canonical_key='tab-save', title='Save tab groups')
        self.item('first', request)
        evidence = self.repo / 'data/source-items/firefox/firefox-beta.json'
        first_bytes = evidence.read_bytes()
        first_effect, = read(self.repo / browser_status.detail_path('daily', STATUS_CUTOFF))['browsers']['firefox']['effects']
        run_daily.commit_candidate(self.repo)
        self.cli('fresh', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        with self.assertRaises(ValueError):
            self.publish_browser('fresh', 'firefox', dict(decisions=[], dispositions=[]))
        self.assertEqual([row['source_item_id']], [r['source_item_id'] for r in self.candidates('fresh', sid)])
        second = dict(request, canonical_key='tab-share', title='Share tab groups')
        self.item('fresh', second)
        self.item('fresh', second)
        for name in browser_status.registry_facts(self.repo, 'daily')[2]:
            choice = self.browser_choices('fresh', name, select=name == 'firefox')
            choice['decisions'] = []
            self.publish_browser('fresh', name, choice)
        receipt = read(self.repo / 'data/daily-status/2026-11-24.json')
        self.assertEqual((2, 2), (receipt['change_count'], receipt['collected_feature_count']))
        detail = read(self.repo / browser_status.detail_path('daily', STATUS_CUTOFF))
        self.assertIn(first_effect, detail['browsers']['firefox']['effects'])
        self.assertEqual(first_bytes, evidence.read_bytes())
        self.cli('following', cutoff='2026-11-25T07:00:00+09:00', extra=['--daily-status'])
        self.assertEqual([], self.candidates('following', sid))

    def test_item_cli_checkpoint_from_incomplete_source_and_atomic_rollback(self):
        from pipeline import item_publication
        self.configure_small_registry()
        sid, url = 'chrome-releases', HOME + '2026/11/release.html'
        registry = read(self.registry)
        next(s for s in registry['sources'] if s['source_id'] == sid)['parser'] = self.sources[sid]['parser']
        self.registry.write_bytes(encoded(registry))
        self.payloads[HOME] = self.card(url, '2026-11-10') + self.card(url.replace('release.html', 'second.html'), '2026-11-11')
        self.payloads[url] = self.article('2026-11-10')
        self.cli('survey', cutoff=STATUS_CUTOFF, extra=['--daily-status'], expected=2)
        self.assertEqual('partial', self.state('survey')['source_results'][sid]['status'])
        row, = self.candidates('survey', sid)
        request = dict(browser='chrome', source_id=sid, source_item_id=row['source_item_id'],
                       revision_id=row['revisions'][-1]['revision_id'], canonical_key='groups', title='Tab groups')
        def interrupt(root, txn, changes, before, writer, **kwargs):
            def replace(path, raw):
                run_daily.durable(path, raw)
                if path == root / collect.FEATURE_CATALOG:
                    raise OSError('fixture interrupted catalog write')
            return run_daily.store_changes(root, txn, changes, before, writer, replace=replace, **kwargs)
        with patch.object(item_publication, 'store_changes', interrupt), self.assertRaisesRegex(OSError, 'interrupted'):
            self.item('survey', request)
        self.assertEqual([], list((self.repo / 'data').rglob('*.json')))
        self.item('survey', request)
        result = read(self.repo / 'data/daily-status/2026-11-24.json')
        self.assertEqual(('incomplete', None, None), tuple(result[k] for k in ('status', 'collected_feature_count', 'change_count')))
        self.assertEqual(['groups'], [f['canonical_key'] for f in read(self.repo / collect.FEATURE_CATALOG)])

    def test_browser_cli_committed_partial_then_fresh_remaining_browsers(self):
        self.configure_small_registry()
        run_daily.commit_candidate(self.repo)
        edge = self.sources['edge-beta']['url']
        recovered = self.payloads[edge]
        self.payloads[edge] = TimeoutError('incomplete Edge')
        self.cli('first', cutoff=STATUS_CUTOFF, extra=['--daily-status'], expected=2)
        firefox = self.browser_choices('first', 'firefox')
        self.publish_browser('first', 'firefox', firefox)
        status = self.repo / 'data/daily-status/2026-11-24.json'
        detail = self.repo / browser_status.detail_path('daily', STATUS_CUTOFF)
        self.assertEqual((None, None), (read(status)['change_count'], read(status)['collected_feature_count']))
        outcomes = read(detail)['browsers']
        self.assertEqual((1, 1), (outcomes['firefox']['change_count'], outcomes['firefox']['collected_feature_count']))
        self.assertEqual(None, outcomes['edge']['change_count'])
        firefox_path = self.repo / 'data/source-items/firefox/firefox-beta.json'
        first_files = tuple(p.read_bytes() for p in (firefox_path, status, detail))
        self.publish_browser('first', 'firefox', firefox)
        with self.assertRaisesRegex(ValueError, 'different final'):
            self.publish_browser('first', 'firefox', self.browser_choices('first', 'firefox', select=False))
        with self.assertRaisesRegex(ValueError, 'finish this cutoff'):
            self.save('first', self.decisions('first'), allow_partial=True)
        self.assertEqual(first_files, tuple(p.read_bytes() for p in (firefox_path, status, detail)))
        run_daily.commit_candidate(self.repo)
        self.payloads[edge] = recovered
        with self.assertRaisesRegex(ValueError, 'original commit'):
            self.cli('first', cutoff=STATUS_CUTOFF, extra=['--daily-status', '--resume'])
        shutil.rmtree(self.folder / 'runs/first')
        self.cli('second', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        # A's original explicit quote and immutable revision must survive A's private cleanup.
        accepted_row, = read(firefox_path)
        snapshot = accepted_row['revisions'][0]
        snapshot['evidence']['excerpt'] = 'Changed original evidence'
        accepted_row['evidence']['excerpt'] = snapshot['evidence']['excerpt']
        firefox_path.write_bytes(encoded([accepted_row]))
        self.cli('drift', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        with self.assertRaisesRegex(ValueError, 'Accepted browser evidence'):
            self.publish_browser('drift', 'edge', self.browser_choices('drift', 'edge'))
        self.assertEqual(first_files[1:], (status.read_bytes(), detail.read_bytes()))
        firefox_path.write_bytes(first_files[0])
        for browser in outcomes.keys() - {'firefox'}:
            self.publish_browser('second', browser, self.browser_choices('second', browser, select=browser == 'edge'))
        self.assertEqual((2, 2), (read(status)['change_count'], read(status)['collected_feature_count']))
        self.assertEqual(outcomes['firefox'], read(detail)['browsers']['firefox'])
        self.assertEqual(first_files[0], firefox_path.read_bytes())
        self.assertEqual(2, len(read(self.repo / collect.FEATURE_CATALOG)))
        final = detail.read_bytes(), status.read_bytes()
        self.cli('second', cutoff=None, extra=['--record-incomplete'])
        self.assertEqual(final, (detail.read_bytes(), status.read_bytes()))
        validate_tree(self.repo)

    def test_browser_cli_zero_subset_and_checkpoint_guards(self):
        self.configure_small_registry()
        registry = read(self.registry)
        next(s for s in registry['sources'] if s['source_id'] == 'firefox-ios')['enabled'] = True
        self.registry.write_bytes(encoded(registry))
        self.cli('subset', ['firefox-beta', 'edge-beta'], cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        with self.assertRaisesRegex(ValueError, 'every pinned source'):
            self.publish_browser('subset', 'firefox', self.browser_choices('subset', 'firefox'))
        choices = self.browser_choices('subset', 'edge', select=False)
        with self.assertRaisesRegex(ValueError, 'cover all'):
            self.publish_browser('subset', 'edge', dict(choices, dispositions=[]))
        work = self.folder / 'runs/subset/work'
        for rel in ['checkpoints/edge-beta.json', 'candidates/edge-beta.json']:
            path = work / rel
            original = path.read_bytes()
            path.write_bytes(b'[]')
            with self.assertRaises(ValueError):
                self.publish_browser('subset', 'edge', choices)
            path.write_bytes(original)
        bad = self.browser_choices('subset', 'firefox')
        with self.assertRaises(ValueError):
            self.publish_browser('subset', 'edge', bad)
        self.publish_browser('subset', 'edge', choices)
        self.assertFalse((self.repo / collect.FEATURE_CATALOG).exists())
        rel = browser_status.detail_path('daily', STATUS_CUTOFF)
        detail = read(self.repo / rel)
        self.assertEqual(0, detail['browsers']['edge']['change_count'])
        self.assertIsNone(detail['browsers']['firefox']['change_count'])
        day = self.repo / 'data/daily-status/2026-11-24.json'
        self.assertIsNone(read(day)['change_count'])
        detail['scope']['expected'] = {'edge': ['edge-beta']}
        detail['browsers'] = {'edge': detail['browsers']['edge']}
        (self.repo / rel).write_bytes(encoded(browser_status.seal(detail)))
        day.write_bytes(encoded(dict(read(day), status='complete', change_count=0, collected_feature_count=0)))
        with self.assertRaisesRegex(ValueError, 'pinned registry'):
            validate_tree(self.repo)

    def test_committed_whole_daily_receipt_protects_every_retry(self):
        self.configure_small_registry()
        initial = run_daily.commit_candidate(self.repo)
        day = self.repo / 'data/daily-status/2026-11-24.json'
        self.cli('whole', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        original = self.folder / 'whole.json'
        original.write_bytes(encoded(self.decisions('whole')))
        self.cli('whole', cutoff=None, extra=['--save-features', str(original)])
        accepted = run_daily.commit_candidate(self.repo)
        record = read(day)
        self.assertEqual((1, 1), (record['collected_feature_count'], record['change_count']))
        self.cli('fresh', cutoff='2026-11-23T22:00:00Z', extra=['--daily-status'])
        empty = self.folder / 'fresh.json'
        empty.write_bytes(encoded(self.decisions('fresh')))
        self.assertEqual([], read(empty)['decisions'])
        after = encoded(dict(record, collected_feature_count=0, change_count=0))
        original_bytes = day.read_bytes()
        def final_writer():
            rel = day.relative_to(self.repo).as_posix()
            with run_lock(self.repo) as writer:
                run_daily.store_changes(self.repo.resolve(), self.folder / 'direct-txn',
                    {rel: json.loads(after)}, {rel: run_daily.digest(day.read_bytes()) if day.exists() else None}, writer)

        actions = {
            'saved replay': lambda: self.cli('whole', cutoff=None, extra=['--save-features', str(original)]),
            'scoped zero': lambda: self.publish_browser('fresh', 'firefox', self.browser_choices('fresh', 'firefox')),
            'record incomplete': lambda: self.cli('fresh', cutoff=None, extra=['--record-incomplete']),
            'strict zero': lambda: self.cli('fresh', cutoff=None, extra=['--save-features', str(empty)]),
            'final writer': final_writer,
            'CI': lambda: validate_tree(self.repo, base=accepted),
        }
        for raw in (None, after):
            for name, action in actions.items():
                with self.subTest(action=name, removed=raw is None):
                    if raw is None:
                        day.unlink(missing_ok=True)
                    else:
                        day.write_bytes(raw)
                    with self.assertRaises(ValueError):
                        action()
                    self.assertEqual(raw, day.read_bytes() if day.exists() else None)
                    self.assertFalse((self.repo / browser_status.FOLDER).exists())
        original_repo = self.repo
        for index, raw in enumerate((None, after)):
            self.repo = self.folder / f'damaged-commit-{index}'
            shutil.copytree(original_repo, self.repo)
            damaged = self.repo / day.relative_to(original_repo)
            if raw is None:
                damaged.unlink(missing_ok=True)
            else:
                damaged.write_bytes(raw)
            rejected = run_daily.commit_candidate(self.repo)
            for ref in (accepted, initial):
                with self.subTest(committed_change=raw, ref=ref), self.assertRaises(ValueError):
                    validate_tree(self.repo, base=ref)
            # A following push can touch only unrelated files while the damage remains.
            (self.repo / 'unrelated.txt').write_text('A later change')
            run_daily.commit_candidate(self.repo)
            with self.assertRaises(ValueError):
                validate_tree(self.repo, base=rejected)
            name = f'after-damage-{index}'
            self.cli(name, cutoff=STATUS_CUTOFF, extra=['--daily-status'])
            with self.assertRaises(ValueError):
                self.publish_browser(name, 'firefox', self.browser_choices(name, 'firefox'))
            with self.assertRaises(ValueError):
                self.cli(name, cutoff=None, extra=['--record-incomplete'])
            with self.assertRaises(ValueError):
                self.save(name, self.decisions(name))
            damaged.write_bytes(original_bytes)
            run_daily.commit_candidate(self.repo)
            for ref in (initial, accepted, rejected):
                validate_tree(self.repo, base=ref)
            self.cli(name, cutoff=None, extra=['--record-incomplete'])
            self.assertEqual(original_bytes, damaged.read_bytes())
        self.repo = original_repo
        day.write_bytes(original_bytes)
        self.cli('whole', cutoff=None, extra=['--save-features', str(original)])
        self.cli('tomorrow', cutoff='2026-11-25T07:00:00+09:00', extra=['--daily-status'])
        self.save('tomorrow', self.decisions('tomorrow'))
        run_daily.commit_candidate(self.repo)
        validate_tree(self.repo, base=accepted)
        self.assertEqual(original_bytes, day.read_bytes())

    def test_ci_cannot_add_browser_detail_to_a_committed_whole_daily_zero(self):
        self.configure_small_registry()
        self.cli('zero', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        for browser in ('chrome', 'edge', 'firefox', 'safari', 'whale'):
            self.publish_browser('zero', browser, self.browser_choices('zero', browser, select=False))
        detail = self.repo / browser_status.detail_path('daily', STATUS_CUTOFF)
        raw = detail.read_bytes()
        detail.unlink()
        accepted = run_daily.commit_candidate(self.repo)
        detail.write_bytes(raw)
        run_daily.commit_candidate(self.repo)
        with self.assertRaises(ValueError):
            validate_tree(self.repo, base=accepted)

    def test_recovery_preserves_committed_outputs_and_allows_unrelated_commits(self):
        self.configure_small_registry()
        template = self.repo
        for accepted in (False, True):
            with self.subTest(accepted=accepted):
                name = 'accepted' if accepted else 'unrelated'
                self.repo = self.folder / name
                shutil.copytree(template, self.repo)
                run_daily.commit_candidate(self.repo)
                self.cli(name, cutoff=STATUS_CUTOFF, extra=['--daily-status'])
                day = self.repo / 'data/daily-status/2026-11-24.json'
                original = run_daily.store_changes

                def interrupt(*args):
                    def stop_at_receipt(path, raw):
                        run_daily.durable(path, raw)
                        if path == day.resolve():
                            raise KeyboardInterrupt()
                    return original(*args, replace=stop_at_receipt)

                with patch.object(collect, 'store_changes', interrupt), self.assertRaises(KeyboardInterrupt):
                    self.save(name, self.decisions(name))
                if accepted:
                    run_daily.commit_candidate(self.repo)
                    files = {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')}
                    with self.assertRaisesRegex(RuntimeError, 'Git accepted'):
                        self.cli(name, cutoff=None, extra=['--record-incomplete'])
                    self.assertEqual(files, {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})
                else:
                    git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid',
                        '-c', 'core.hooksPath=/dev/null', 'commit', '--allow-empty', '-qm', 'Unrelated commit')
                    self.cli(name, cutoff=None, extra=['--record-incomplete'])
                    self.assertIsNone(read(day)['collected_feature_count'])
                    self.assertFalse((self.repo / collect.FEATURE_CATALOG).exists())

    def test_new_daily_window_uses_registered_policy_at_writer_and_ci(self):
        self.configure_small_registry()
        policy = read(self.registry)
        policy['baseline']['daily_window_days'] = 4
        policy['baseline']['backfill_since'] = '2026-11-22'
        self.registry.write_bytes(encoded(policy))
        base = run_daily.commit_candidate(self.repo)
        cutoff = '2026-11-23T22:00:00Z'
        # Simulate a producer that consistently pins the wrong window in all private files.
        with patch.object(collect, 'window_start', return_value=cutoff), patch.object(browser_status, 'check_window'):
            self.cli('short', cutoff=cutoff, extra=['--daily-status'])
        pm = self.folder / 'short.json'
        pm.write_bytes(encoded(self.decisions('short')))
        with self.assertRaisesRegex(ValueError, 'window'):
            self.cli('short', cutoff=None, extra=['--save-features', str(pm)])
        self.assertFalse((self.repo / 'data').exists())
        self.cli('floor', cutoff=cutoff, extra=['--daily-status'])
        detail = self.repo / browser_status.detail_path('daily', cutoff)
        choices = self.browser_choices('floor', 'firefox', select=False)
        original = run_daily.store_changes

        def tamper(root, txn, changes, before, writer):
            row = changes[detail.relative_to(self.repo).as_posix()]
            row['scope']['start'] = cutoff
            browser_status.seal(row)
            return original(root, txn, changes, before, writer)

        with patch.object(collect, 'store_changes', tamper), self.assertRaisesRegex(ValueError, 'window'):
            self.publish_browser('floor', 'firefox', choices)
        self.assertFalse(detail.exists())
        self.publish_browser('floor', 'firefox', choices)
        self.assertEqual('2026-11-22T00:00:00+09:00', read(detail)['scope']['start'])
        later = '2026-12-01T07:00:00+09:00'
        self.cli('four', cutoff=later, extra=['--daily-status'])
        self.publish_browser('four', 'firefox', self.browser_choices('four', 'firefox', select=False))
        second = self.repo / browser_status.detail_path('daily', later)
        row = read(second)
        self.assertEqual('2026-11-27T07:00:00+09:00', row['scope']['start'])
        row['scope']['start'] = '2026-11-26T22:00:00Z'  # Same instant.
        second.write_bytes(encoded(browser_status.seal(row)))
        validate_tree(self.repo, base=base)
        fixed = second.read_bytes()
        for invalid in (row['scope']['cutoff'], '2026-11-26T22:00:00.000001Z'):
            row['scope']['start'] = invalid
            second.write_bytes(encoded(browser_status.seal(row)))
            with self.subTest(start=invalid), self.assertRaisesRegex(ValueError, 'window'):
                validate_tree(self.repo, base=base)
        second.write_bytes(fixed)
        accepted = run_daily.commit_candidate(self.repo)
        policy['baseline']['daily_window_days'] = 7
        self.registry.write_bytes(encoded(policy))
        run_daily.commit_candidate(self.repo)
        validate_tree(self.repo, base=accepted)

    def test_batch_checks_second_parent_and_snapshot_policy(self):
        self.configure_small_registry()
        base = run_daily.commit_candidate(self.repo)
        # Keep an empty first-parent branch while the other publishes a browser.
        git(self.repo, 'branch', 'empty-base', base)
        self.cli('scoped', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.publish_browser('scoped', 'firefox', self.browser_choices('scoped', 'firefox'))
        accepted = run_daily.commit_candidate(self.repo)
        policy = read(self.registry)
        policy['baseline']['daily_window_days'] = 4
        self.registry.write_bytes(encoded(policy))
        run_daily.commit_candidate(self.repo)
        validate_tree(self.repo, base=base)
        git(self.repo, 'switch', '-q', 'empty-base')
        git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid',
            '-c', 'core.hooksPath=/dev/null', 'merge', '-q', '--no-ff', '-s', 'ours', '-m', 'Drop receipt', accepted)
        with self.assertRaisesRegex(ValueError, 'missing'):
            validate_tree(self.repo, base=base)

    def test_weekly_history_keeps_accepted_whole_and_browser_results_through_a_batch(self):
        self.configure_small_registry()
        initial = run_daily.commit_candidate(self.repo)
        first = weekly_status.FIRST_GUARDED_CUTOFF
        later = '2026-12-06T10:00:00+09:00'
        self.cli('whole', cutoff=first, mode='weekly_reconcile')
        self.save('whole', self.decisions('whole'))
        self.cli('partial', cutoff=later, mode='weekly_reconcile')
        self.publish_browser('partial', 'edge', self.browser_choices('partial', 'edge'))
        run_daily.commit_candidate(self.repo)
        marker = self.repo / weekly_status.path(first)
        detail = self.repo / browser_status.detail_path('weekly_reconcile', later)
        old = [p.read_bytes() for p in (marker, detail)]
        marker.write_bytes(encoded(browser_status.seal(dict(read(marker), collected_feature_count=0, feature_ids=[]))))
        detail.unlink()
        run_daily.commit_candidate(self.repo)
        with self.assertRaises(ValueError):
            validate_tree(self.repo, base=initial)
        for name, cutoff in [('whole-again', first), ('partial-again', later)]:
            self.cli(name, cutoff=cutoff, mode='weekly_reconcile')
            with self.assertRaises(ValueError):
                self.publish_browser(name, 'firefox', self.browser_choices(name, 'firefox'))
            with self.assertRaises(ValueError):
                self.save(name, self.decisions(name))
        for path, raw in zip((marker, detail), old):
            path.write_bytes(raw)
        run_daily.commit_candidate(self.repo)
        validate_tree(self.repo, base=initial)

    def test_full_weekly_freezes_cutoff_before_fresh_browser_save(self):
        self.configure_small_registry()
        run_daily.commit_candidate(self.repo)
        cutoff = '2026-11-29T10:00:00+09:00'
        self.cli('whole', cutoff=cutoff, mode='weekly_reconcile')
        classification = self.decisions('whole')
        firefox, = classification['decisions']
        firefox.pop('change_kind')  # Original whole-weekly classification contract.
        pm = self.folder / 'whole-weekly.json'
        pm.write_bytes(encoded(classification))
        self.cli('whole', cutoff=None, extra=['--save-features', str(pm)])
        catalog = self.repo / collect.FEATURE_CATALOG
        self.assertEqual(['firefox'], [row['browser'] for row in read(catalog)])
        run_daily.commit_candidate(self.repo)
        self.cli('fresh', cutoff='2026-11-29T01:00:00Z', mode='weekly_reconcile')
        fresh = self.browser_choices('fresh', 'firefox')
        self.assertEqual([], fresh['decisions'])
        prior = {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')}
        try:
            self.publish_browser('fresh', 'firefox', fresh)
        except ValueError:
            self.assertEqual(prior, {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})
        else:
            rel = browser_status.detail_path('weekly_reconcile', cutoff)
            total = read(self.repo / rel)['browsers']['firefox']['collected_feature_count']
            self.fail(f'Fresh scoped save accepted {total} Firefox features after whole weekly saved one')

    def test_stale_weekly_zero_cannot_freeze_a_new_restore_candidate(self):
        self.configure_small_registry()
        template = self.repo
        sid = 'firefox-beta'
        url = self.sources[sid]['url']
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        for case in ('committed', 'uncommitted', 'data-only'):
            with self.subTest(case=case):
                self.repo = self.folder / case
                shutil.copytree(template, self.repo)
                seed, waiting, interim, fresh = (case + suffix for suffix in ('-seed', '-old', '-interim', '-new'))
                self.cli(seed, [sid], cutoff='2026-11-27T10:00:00+09:00', mode='manual')
                self.save(seed, self.classified(seed, sid))
                if case != 'data-only':
                    run_daily.commit_candidate(self.repo)
                self.cli(waiting, cutoff=cutoff, mode='weekly_reconcile')
                self.assertEqual([], self.candidates(waiting, sid))
                pm = self.folder / (case + '-whole.json')
                pm.write_bytes(encoded(self.decisions(waiting)))
                with patch.dict(self.payloads, {url: self.payloads[url].replace('Tab grouping added.', 'Tab sorting added.')}):
                    self.cli(interim, [sid], cutoff='2026-11-28T10:00:00+09:00', mode='manual')
                    self.save(interim, self.classified(interim, sid))
                if case == 'committed':
                    run_daily.commit_candidate(self.repo)
                self.cli(fresh, cutoff=cutoff, mode='weekly_reconcile')
                restored, = self.candidates(fresh, sid)
                self.assertEqual('Tab grouping added.', restored['evidence']['excerpt'])
                original = {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')}
                with self.assertRaises(ValueError):
                    self.cli(waiting, cutoff=None, extra=['--save-features', str(pm)])
                self.assertEqual(original, {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})
                pm.write_bytes(encoded(self.decisions(fresh)))
                self.cli(fresh, cutoff=None, extra=['--save-features', str(pm)])
                self.assertEqual(1, read(self.repo / weekly_status.path(cutoff))['collected_feature_count'])

    def test_weekly_writer_rechecks_an_unchanged_source_immediately_before_publish(self):
        self.configure_small_registry()
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        self.cli('pending', cutoff=cutoff, mode='weekly_reconcile')
        pm = self.folder / 'pending.json'
        pm.write_bytes(encoded(self.decisions('pending')))
        original = run_daily.store_changes
        source = self.repo / 'data/source-items/edge/edge-beta.json'

        def concurrent(root, txn, changes, before, writer):
            self.assertNotIn('data/source-items/edge/edge-beta.json', changes)
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(b'[]')
            return original(root, txn, changes, before, writer)

        with patch.object(collect, 'store_changes', concurrent), self.assertRaisesRegex(ValueError, 'Concurrent edit'):
            self.cli('pending', cutoff=None, extra=['--save-features', str(pm)])
        self.assertEqual(b'[]', source.read_bytes())
        self.assertFalse((self.repo / weekly_status.path(cutoff)).exists())
        self.assertFalse((self.repo / collect.FEATURE_CATALOG).exists())

    def test_guarded_weekly_requires_input_baseline_from_its_producer(self):
        self.configure_small_registry()
        code = self.folder / 'previous-code'
        (code / 'pipeline').mkdir(parents=True)
        (code / 'pipeline/collect.py').write_text('# Old collector without evidence pins')
        run_daily.commit_candidate(code)
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        with patch.object(run_daily, 'CODE_REPOSITORY', code):
            self.cli('legacy-week', cutoff=cutoff, mode='weekly_reconcile')
            run = self.folder / 'runs/legacy-week'
            state_path, work = run / 'feature-run.json', run / 'work'
            state = read(state_path)
            state.pop('browser_pin')
            state_path.write_bytes(encoded(state))
            (work / '.owner').write_text(state['workspace_id'])
            (work / 'browser-pin.json').unlink()
            shutil.rmtree(work / 'checkpoints')
            pm = run / 'pm.json'
            pm.write_bytes(encoded(self.decisions('legacy-week')))
            with self.assertRaisesRegex(ValueError, 'original evidence baseline'):
                self.cli('legacy-week', cutoff=None, extra=['--save-features', str(pm)])
        self.assertFalse((self.repo / 'data').exists())

    def test_ci_checks_both_full_weekly_history_starts(self):
        self.configure_small_registry()
        base = run_daily.commit_candidate(self.repo)
        for name, cutoff in [('first', weekly_status.FIRST_GUARDED_CUTOFF), ('second', '2026-12-06T10:00:00+09:00')]:
            self.cli(name, cutoff=cutoff, mode='weekly_reconcile')
            self.save(name, self.decisions(name))
        # Execute the CI entry point against this fixture checkout.
        entry = self.repo / 'pipeline/daily_status.py'
        entry.parent.mkdir()
        shutil.copyfile(ROOT / 'pipeline/daily_status.py', entry)
        with patch('sys.argv', [str(entry), '--base-commit', base]):
            runpy.run_path(str(entry), run_name='__main__')
            target = self.repo / weekly_status.path(cutoff)
            altered = read(target)
            altered['scope']['start'] = '2025-12-31T10:00:00-05:00'
            target.write_bytes(encoded(browser_status.seal(altered)))
            runpy.run_path(str(entry), run_name='__main__')
            run_daily.commit_candidate(self.repo)
            runpy.run_path(str(entry), run_name='__main__')
            git(self.repo, 'switch', '-qc', 'different-start', base)
            target.parent.mkdir(parents=True, exist_ok=True)
            entry.parent.mkdir(exist_ok=True)
            shutil.copyfile(ROOT / 'pipeline/daily_status.py', entry)
            altered['scope']['start'] = '2026-12-04T00:00:00+09:00'
            target.write_bytes(encoded(browser_status.seal(altered)))
            with self.assertRaisesRegex(ValueError, 'full registered history'):
                runpy.run_path(str(entry), run_name='__main__')

    def test_full_weekly_zero_is_atomic_and_same_run_recovery_is_idempotent(self):
        self.configure_small_registry()
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        self.cli('whole', cutoff=cutoff, mode='weekly_reconcile')
        decisions = self.decisions('whole')
        for d in decisions['dispositions']:
            d['disposition'] = 'excluded'
        decisions['decisions'] = []
        pm = self.folder / 'zero.json'
        pm.write_bytes(encoded(decisions))
        save = ['--save-features', str(pm)]
        rel = weekly_status.path(cutoff)
        original = run_daily.store_changes

        def interrupted(root, txn, changes, before, writer):
            def crash(path, raw):
                run_daily.durable(path, raw)
                if path == root / rel:
                    raise KeyboardInterrupt()
            return original(root, txn, changes, before, writer, replace=crash)

        with patch.object(collect, 'store_changes', interrupted), self.assertRaises(KeyboardInterrupt):
            self.cli('whole', cutoff=None, extra=save)
        with run_lock(self.repo) as writer:
            run_daily.pending_recovery(self.repo.resolve(), writer)
        self.assertFalse((self.repo / rel).exists())
        with patch.object(collect, 'finish_run', side_effect=OSError('after publication')), self.assertRaises(OSError):
            self.cli('whole', cutoff=None, extra=save)
        record = read(self.repo / rel)
        self.assertEqual((0, []), (record['collected_feature_count'], record['feature_ids']))
        self.assertEqual(self.state('whole')['status'], 'saving')
        self.assertEqual([self.repo / rel], list((self.repo / 'data').rglob('*.json')))
        raw = (self.repo / rel).read_bytes()
        for _ in range(2):
            self.cli('whole', cutoff=None, extra=save)
            self.assertEqual(raw, (self.repo / rel).read_bytes())
        self.assertEqual('saved', self.state('whole')['status'])
        self.cli('fresh', cutoff=cutoff, mode='weekly_reconcile')
        with self.assertRaisesRegex(ValueError, 'completed whole weekly'):
            self.cli('fresh', cutoff=None, extra=save)
        self.assertFalse((self.repo / 'data/daily-status').exists())

    def test_full_weekly_deduplicates_evidence_and_ci_preserves_first_marker(self):
        self.configure_small_registry()
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        sid = 'firefox-beta'
        url = self.sources[sid]['url']
        self.cli('initial', [sid], cutoff=STATUS_CUTOFF, mode='manual')
        self.save('initial', self.classified('initial', sid))
        self.payloads[url] = self.payloads[url].replace('Tab grouping added.</p>',
            'Tab grouping documentation.</p><p id="another-tab">Tab grouping help.</p>')
        self.cli('full', cutoff=cutoff, mode='weekly_reconcile')
        choices = self.decisions('full')
        self.assertEqual(2, len(choices['decisions']))
        choices['decisions'][0]['change_kind'] = 'evidence_only'
        choices['decisions'][1].pop('change_kind')
        pm = self.folder / 'week.json'
        pm.write_bytes(encoded(choices))
        self.cli('full', cutoff=None, extra=['--save-features', str(pm)])
        marker = self.repo / weekly_status.path(cutoff)
        record = read(marker)
        self.assertEqual(1, record['collected_feature_count'])
        self.assertEqual([read(self.repo / collect.FEATURE_CATALOG)[0]['feature_id']], record['feature_ids'])
        self.assertNotIn('change_count', record)
        commit = run_daily.commit_candidate(self.repo)
        raw = marker.read_bytes()
        marker.write_bytes(raw + b'\n')
        with self.assertRaisesRegex(ValueError, 'Cannot change'):
            validate_tree(self.repo, base=commit)
        altered = browser_status.seal(dict(record, feature_ids=[], collected_feature_count=0))
        marker.write_bytes(encoded(altered))
        with self.assertRaisesRegex(ValueError, 'Cannot change'):
            validate_tree(self.repo, base=commit)
        marker.write_bytes(raw)
        rel = browser_status.detail_path('weekly_reconcile', cutoff)
        conflicting = self.repo / rel
        conflicting.parent.mkdir(parents=True)
        conflicting.write_bytes(encoded(browser_status.seal(browser_status.initial(record['scope']))))
        with self.assertRaisesRegex(ValueError, 'Conflicting'):
            validate_tree(self.repo)
        conflicting.unlink()
        marker.unlink()
        run_daily.commit_candidate(self.repo)
        with self.assertRaisesRegex(ValueError, 'missing'):
            validate_tree(self.repo, base=commit)

    def test_weekly_migration_keeps_historical_scope_and_blocks_unproven_counts(self):
        self.configure_small_registry()
        old = '2026-11-22T10:00:00+09:00'
        self.cli('early', cutoff=old, mode='weekly_reconcile')
        with self.assertRaisesRegex(ValueError, 'predates'):
            self.publish_browser('early', 'firefox', self.browser_choices('early', 'firefox'))
        just_before = '2026-11-29T00:59:59.999999Z'
        self.cli('before', cutoff=just_before, mode='weekly_reconcile')
        with self.assertRaisesRegex(ValueError, 'predates'):
            self.publish_browser('before', 'firefox', self.browser_choices('before', 'firefox'))
        # Existing v1 results carry their own scope and accepted effect.
        with patch.object(weekly_status, 'guarded', return_value=True):
            self.publish_browser('early', 'firefox', self.browser_choices('early', 'firefox'))
        self.publish_browser('early', 'edge', self.browser_choices('early', 'edge'))
        with self.assertRaisesRegex(ValueError, 'finish this cutoff'):
            self.save('early', self.decisions('early'))
        self.cli('historic-full', cutoff=just_before, mode='weekly_reconcile')
        self.save('historic-full', self.decisions('historic-full'))
        record = read(self.repo / weekly_status.path(just_before))
        self.assertIsNone(record['feature_ids'])
        self.assertIsNone(record['collected_feature_count'])
        self.assertFalse((self.repo / 'data/daily-status').exists())
        validate_tree(self.repo)

    def test_ci_accepts_exact_repair_after_invalid_names_and_file_types(self):
        self.configure_small_registry()
        entry = self.repo / 'pipeline/daily_status.py'
        entry.parent.mkdir()
        shutil.copyfile(ROOT / 'pipeline/daily_status.py', entry)
        def ci(base):
            with patch('sys.argv', [str(entry), '--base-commit', base]):
                runpy.run_path(str(entry), run_name='__main__')
        base = run_daily.commit_candidate(self.repo)
        self.cli('day', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.save('day', self.decisions('day'))
        week = weekly_status.FIRST_GUARDED_CUTOFF
        self.cli('week', cutoff=week, mode='weekly_reconcile')
        self.save('week', self.decisions('week'))
        later = '2026-12-06T10:00:00+09:00'
        self.cli('browser', cutoff=later, mode='weekly_reconcile')
        self.publish_browser('browser', 'edge', self.browser_choices('browser', 'edge'))
        day = self.repo / 'data/daily-status/2026-11-24.json'
        marker = self.repo / weekly_status.path(week)
        detail = self.repo / browser_status.detail_path('weekly_reconcile', later)
        originals = {p: p.read_bytes() for p in (day, marker, detail)}
        accepted = run_daily.commit_candidate(self.repo)
        branch = git(self.repo, 'branch', '--show-current')
        git(self.repo, 'branch', 'merge-base', accepted)
        ci(base)
        invalid = {
            day: day.with_suffix('.json.bak'),
            marker: marker.with_name('2026-13-35T700000.000000Z.json'),
            detail: detail.with_name('bad\u2028name.bak'),
        }
        git(self.repo, 'config', 'core.quotePath', 'false')
        for path, alias in invalid.items():
            path.rename(alias)
        renamed = run_daily.commit_candidate(self.repo)
        for ref in (base, accepted):
            with self.assertRaises(ValueError):
                ci(ref)
        for path, alias in invalid.items():
            alias.rename(path)
        day.write_bytes(encoded(dict(read(day), change_count=0, collected_feature_count=0)))
        run_daily.commit_candidate(self.repo)
        with self.assertRaises(ValueError):
            ci(renamed)
        day.unlink()
        day.mkdir()
        (day / 'not-a-receipt').write_text('broken')
        marker.unlink()
        marker.symlink_to(detail)
        detail.write_bytes(b'not json')
        run_daily.commit_candidate(self.repo)
        with self.assertRaises(ValueError):
            ci(renamed)
        shutil.rmtree(day)
        marker.unlink()
        for path, raw in originals.items():
            path.write_bytes(raw)
        repaired = run_daily.commit_candidate(self.repo)
        for ref in (base, accepted, renamed, repaired):
            ci(ref)
        (self.repo / 'unrelated.txt').write_text('next push')
        run_daily.commit_candidate(self.repo)
        ci(repaired)
        git(self.repo, 'switch', '-q', 'merge-base')
        git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid',
            '-c', 'core.hooksPath=/dev/null', 'merge', '-q', '--no-ff', '-m', 'Merge repair', branch)
        ci(accepted)

    def test_current_receipt_folder_case_is_exact_in_the_checkout_and_head(self):
        self.configure_small_registry()
        template = self.repo
        initial = run_daily.commit_candidate(template)
        self.cli('canonical-week', cutoff=weekly_status.FIRST_GUARDED_CUTOFF, mode='weekly_reconcile')
        self.save('canonical-week', self.decisions('canonical-week'))
        self.cli('canonical-detail', cutoff='2026-12-06T10:00:00+09:00', mode='weekly_reconcile')
        self.publish_browser('canonical-detail', 'edge', self.browser_choices('canonical-detail', 'edge'))
        self.cli('canonical-day', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.save('canonical-day', self.decisions('canonical-day'))
        # None of the three correctly named receipt directories is in Git yet.
        for index, rel in enumerate(('data', 'data/daily-status', 'data/weekly-status', 'data/browser-status')):
            self.repo = self.folder / f'case-{index}'
            shutil.copytree(template, self.repo)
            git(self.repo, 'config', 'core.ignoreCase', 'false')
            self.cli(f'pending-{index}', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
            folder = self.repo / rel
            alias = folder.with_name(folder.name.upper())
            intermediate = folder.with_name('move-between-spellings')
            folder.rename(intermediate)
            intermediate.rename(alias)
            for state in ('working', 'committed', 'corrected-worktree'):
                if state == 'committed':
                    incorrect = run_daily.commit_candidate(self.repo)
                if state == 'corrected-worktree':
                    alias.rename(intermediate)
                    intermediate.rename(folder)
                with self.subTest(rel=rel, state=state):
                    with self.assertRaises(ValueError):
                        validate_tree(self.repo, base=initial)
                    with self.assertRaises(ValueError):
                        self.cli(f'pending-{index}', cutoff=None, extra=['--record-incomplete'])
            # Stage both spellings explicitly even on a case-insensitive filesystem.
            folder.rename(intermediate)
            intermediate.rename(alias)
            git(self.repo, 'mv', '--', str(alias), str(intermediate))
            git(self.repo, 'mv', '--', str(intermediate), str(folder))
            # Similar names elsewhere do not reserve a receipt namespace.
            for other in ('data/WEEKLY-STATUS-ARCHIVE', 'data/archive/BROWSER-STATUS', 'DATA-LAKE'):
                directory = self.repo / other
                directory.mkdir(parents=True)
                (directory / 'notes').write_text('unrelated')
            corrected = run_daily.commit_candidate(self.repo)
            for ref in (initial, incorrect, corrected):
                validate_tree(self.repo, base=ref)
            self.cli(f'pending-{index}', cutoff=None, extra=['--record-incomplete'])

    def test_weekly_ci_checks_evidence_from_a_mixed_case_data_root_after_repair(self):
        self.configure_small_registry()
        entry = self.repo / 'pipeline/daily_status.py'
        entry.parent.mkdir()
        shutil.copyfile(ROOT / 'pipeline/daily_status.py', entry)
        base = run_daily.commit_candidate(self.repo)
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        rel = weekly_status.path(cutoff)
        self.cli('empty-week', cutoff=cutoff, mode='weekly_reconcile')
        excluded = self.decisions('empty-week')
        excluded['decisions'] = []
        for row in excluded['dispositions']:
            row['disposition'] = 'excluded'
        self.save('empty-week', excluded)
        zero = (self.repo / rel).read_bytes()
        run_daily.commit_candidate(self.repo)
        git(self.repo, 'switch', '-qc', 'misnamed-positive', base)
        self.cli('positive-week', cutoff=cutoff, mode='weekly_reconcile')
        self.save('positive-week', self.decisions('positive-week'))
        self.assertEqual(1, read(self.repo / rel)['collected_feature_count'])
        alias = self.repo / 'DaTa'
        bridge = self.repo / 'temporary-name'
        (self.repo / 'data').rename(bridge)
        bridge.rename(alias)
        wrong = run_daily.commit_candidate(self.repo)
        template = self.repo
        for strategy in ('direct', 'retired', 'coexisting'):
            self.repo = self.folder / f'repair-{strategy}'
            shutil.copytree(template, self.repo)
            alias = self.repo / 'DaTa'
            canonical = self.repo / 'data'
            bridge = self.repo / 'temporary-name'
            if strategy == 'coexisting':
                # Stage both physical roots in Git even on a case-insensitive disk.
                git(self.repo, 'config', 'core.ignoreCase', 'false')
                empty = self.folder / 'empty.json'
                empty.write_bytes(encoded([]))
                oid = git(self.repo, 'hash-object', '-w', str(empty))
                for path in (collect.FEATURE_CATALOG, 'data/source-items/firefox/firefox-beta.json'):
                    git(self.repo, 'update-index', '--add', '--cacheinfo', '100644', oid, path)
                git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=test@example.invalid',
                    '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'Keep both physical data roots')
                names = git(self.repo, 'ls-tree', '--name-only', 'HEAD').splitlines()
                self.assertEqual({'DaTa', 'data'}, {n for n in names if n.casefold() == 'data'})
                git(self.repo, 'read-tree', '--empty')
                alias.rename(bridge)
                bridge.rename(canonical)
            elif strategy == 'retired':
                kept = self.folder / 'saved-inputs'
                alias.rename(kept)
                run_daily.commit_candidate(self.repo)
                shutil.copytree(kept, canonical)
            else:
                git(self.repo, 'mv', '--', str(alias), str(bridge))
                git(self.repo, 'mv', '--', str(bridge), str(canonical))
            (self.repo / rel).write_bytes(zero)
            run_daily.commit_candidate(self.repo)
            entry = self.repo / 'pipeline/daily_status.py'
            for ref in (base, wrong):
                with self.subTest(strategy=strategy, ref=ref), self.assertRaisesRegex(ValueError, 'original publication'):
                    with patch('sys.argv', [str(entry), '--base-commit', ref]):
                        runpy.run_path(str(entry), run_name='__main__')

    def test_exact_weekly_data_root_can_be_restored_after_it_was_deleted(self):
        self.configure_small_registry()
        entry = self.repo / 'pipeline/daily_status.py'
        entry.parent.mkdir()
        shutil.copyfile(ROOT / 'pipeline/daily_status.py', entry)
        base = run_daily.commit_candidate(self.repo)
        git(self.repo, 'config', 'core.ignoreCase', 'false')
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        self.cli('first', cutoff=cutoff, mode='weekly_reconcile')
        pm = self.folder / 'first.json'
        pm.write_bytes(encoded(self.decisions('first')))
        args = ['--save-features', str(pm)]
        self.cli('first', cutoff=None, extra=args)
        marker = self.repo / weekly_status.path(cutoff)
        self.assertEqual(1, read(marker)['collected_feature_count'])
        data = self.repo / 'data'
        backup = self.folder / 'original'
        alias = self.repo / 'DaTa'
        data.rename(backup)
        backup.rename(alias)
        first = run_daily.commit_candidate(self.repo)
        alias.rename(backup)
        deleted = run_daily.commit_candidate(self.repo)
        # The original registry applies even if the repair comes after a policy change.
        registry = read(self.registry)
        registry['baseline']['daily_window_days'] = 4
        self.registry.write_bytes(encoded(registry))
        run_daily.commit_candidate(self.repo)
        backup.rename(data)
        restored = run_daily.commit_candidate(self.repo)
        self.assertEqual(git(self.repo, 'rev-parse', first + ':DaTa'), git(self.repo, 'rev-parse', restored + ':data'))
        for ref in (base, first, deleted, restored):
            with patch('sys.argv', [str(entry), '--base-commit', ref]):
                runpy.run_path(str(entry), run_name='__main__')
        self.cli('first', cutoff=None, extra=args)
        self.assertEqual(1, read(marker)['collected_feature_count'])

        def commit_tree(tree, *parents):
            args = [arg for parent in parents for arg in ('-p', parent)]
            return git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=t@example.invalid',
                       'commit-tree', tree, *args, '-m', 'Synthetic repair history')

        # The same marker with different evidence bytes is a different proposal.
        source = self.repo / 'data/source-items/firefox/firefox-beta.json'
        source.write_bytes(source.read_bytes() + b'\n')
        git(self.repo, 'add', '--', str(source))
        different = commit_tree(git(self.repo, 'write-tree'), deleted)
        git(self.repo, 'switch', '-q', '--detach', different)
        with self.assertRaisesRegex(ValueError, 'original publication'):
            validate_tree(self.repo, base=deleted)

        # An empty merge cannot hide a different submission on its other side.
        empty = git(self.repo, 'rev-parse', deleted + '^{tree}')
        removed = commit_tree(empty, different)
        merged = commit_tree(empty, deleted, removed)
        after_merge = commit_tree(git(self.repo, 'rev-parse', restored + '^{tree}'), merged)
        git(self.repo, 'switch', '-q', '--detach', after_merge)
        for ref in (base, removed, merged):
            with self.assertRaisesRegex(ValueError, 'original publication'):
                validate_tree(self.repo, base=ref)

    def test_restore_deleted_weekly_backup_with_unchanged_evidence(self):
        self.configure_small_registry()
        template = self.repo
        entry = template / 'pipeline/daily_status.py'
        entry.parent.mkdir()
        shutil.copyfile(ROOT / 'pipeline/daily_status.py', entry)
        base = run_daily.commit_candidate(template)
        week = weekly_status.FIRST_GUARDED_CUTOFF
        for scoped in (False, True):
            run = f'backup-{scoped}'
            self.repo = self.folder / run
            shutil.copytree(template, self.repo)
            self.cli(run, cutoff=week, mode='weekly_reconcile')
            pm = self.folder / (run + '.json')
            pm.write_bytes(encoded(self.browser_choices(run, 'firefox') if scoped else self.decisions(run)))
            save = ['--save-features', str(pm)] + (['--save-browser', 'firefox'] if scoped else [])
            self.cli(run, cutoff=None, extra=save)
            rel = browser_status.detail_path('weekly_reconcile', week) if scoped else weekly_status.path(week)
            marker = self.repo / rel
            original = marker.read_bytes()
            backup = marker.with_suffix('.json.bak')
            marker.rename(backup)
            first = run_daily.commit_candidate(self.repo)
            backup.unlink()
            gap = run_daily.commit_candidate(self.repo)
            (self.repo / 'unrelated.txt').write_text('ordinary commit')
            if not scoped:
                registry = self.repo / 'config/sources.yml'
                config = read(registry)
                config['baseline']['daily_window_days'] = 4
                registry.write_bytes(encoded(config))
            stable = run_daily.commit_candidate(self.repo)
            marker.write_bytes(original)
            run_daily.commit_candidate(self.repo)
            entry = self.repo / 'pipeline/daily_status.py'
            for ref in (base, first, gap, stable):
                with patch('sys.argv', [str(entry), '--base-commit', ref]):
                    runpy.run_path(str(entry), run_name='__main__')
            if scoped:
                self.cli('remaining', cutoff=week, mode='weekly_reconcile')
                self.publish_browser('remaining', 'edge', self.browser_choices('remaining', 'edge', select=False))
                self.assertEqual(1, read(marker)['browsers']['firefox']['collected_feature_count'])
                run_daily.commit_candidate(self.repo)
            else:
                self.cli(run, cutoff=None, extra=save)

            # The original backup name can also survive in a Git tree that was
            # removed in full. A retained-evidence gap may precede the full deletion.
            for parent in (first, gap):
                git(self.repo, 'switch', '-qc', 'full-gap-' + parent[:8], parent)
                data = self.repo / 'data'
                kept = self.folder / (run + parent[:8])
                data.rename(kept)
                removed = run_daily.commit_candidate(self.repo)
                kept.rename(data)
                if backup.exists():
                    backup.rename(marker)
                else:
                    marker.parent.mkdir(exist_ok=True, parents=True)
                    marker.write_bytes(original)
                fixed = run_daily.commit_candidate(self.repo)
                with patch('sys.argv', [str(entry), '--base-commit', removed]):
                    runpy.run_path(str(entry), run_name='__main__')
                if not scoped:
                    self.cli(run, cutoff=None, extra=save)
                git(self.repo, 'switch', '-qc', 'changed-full-gap-' + parent[:8], removed)
                git(self.repo, 'checkout', fixed, '--', 'data')
                evidence = self.repo / 'data/source-items/firefox/firefox-beta.json'
                evidence.write_bytes(evidence.read_bytes() + bytes([10]))
                run_daily.commit_candidate(self.repo)
                with self.assertRaisesRegex(ValueError, 'original publication'):
                    validate_tree(self.repo, base=removed)

            # A reappearing identical marker cannot cover a side branch on which
            # evidence changed during the gap, even if the final bytes match.
            git(self.repo, 'switch', '-qc', 'changed-evidence', gap)
            source = self.repo / 'data/source-items/firefox/firefox-beta.json'
            content = source.read_bytes()
            source.write_bytes(content + bytes([10]))
            run_daily.commit_candidate(self.repo)
            source.write_bytes(content)
            changed_side = run_daily.commit_candidate(self.repo)
            git(self.repo, 'switch', '-qc', 'mixed-gap', stable)
            git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=t@example.invalid', 'merge', '-q',
                '--no-ff', '-m', 'Join gap histories', changed_side)
            marker.parent.mkdir(exist_ok=True, parents=True)
            marker.write_bytes(original)
            run_daily.commit_candidate(self.repo)
            with self.assertRaisesRegex(ValueError, 'original publication'):
                validate_tree(self.repo, base=gap)

            git(self.repo, 'switch', '-qc', 'changed-mode', stable)
            marker.parent.mkdir(exist_ok=True, parents=True)
            marker.write_bytes(original)
            git(self.repo, 'add', '--chmod=+x', '--', rel)
            git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=t@example.invalid',
                'commit', '-qm', 'Different receipt mode')
            with self.assertRaisesRegex(ValueError, 'original publication'):
                validate_tree(self.repo, base=stable)

    def test_zero_weekly_backup_keeps_its_original_registry_after_deletion(self):
        self.configure_small_registry()
        template = self.repo
        entry = template / 'pipeline/daily_status.py'
        entry.parent.mkdir()
        shutil.copyfile(ROOT / 'pipeline/daily_status.py', entry)
        base = run_daily.commit_candidate(template)
        week = weekly_status.FIRST_GUARDED_CUTOFF
        for scoped in (False, True):
            run = f'zero-policy-{scoped}'
            self.repo = self.folder / run
            shutil.copytree(template, self.repo)
            self.cli(run, cutoff=week, mode='weekly_reconcile')
            choices = self.browser_choices(run, 'firefox', select=False) if scoped else self.decisions(run)
            choices['decisions'] = []
            for row in choices['dispositions']:
                row['disposition'] = 'excluded'
            pm = self.folder / (run + '.json')
            pm.write_bytes(encoded(choices))
            save = ['--save-features', str(pm)] + (['--save-browser', 'firefox'] if scoped else [])
            self.cli(run, cutoff=None, extra=save)
            rel = browser_status.detail_path('weekly_reconcile', week) if scoped else weekly_status.path(week)
            marker = self.repo / rel
            original = marker.read_bytes()
            alias = marker.with_suffix('.json.bak')
            marker.rename(alias)
            first = run_daily.commit_candidate(self.repo)
            alias.unlink()
            deleted = run_daily.commit_candidate(self.repo)
            # A fresh classification must not use the other route to replace the old zero.
            fresh = run + '-replacement'
            self.cli(fresh, cutoff=week, mode='weekly_reconcile')
            with self.assertRaisesRegex(ValueError, 'original publication'):
                if scoped:
                    replacement = self.folder / 'replacement.json'
                    replacement.write_bytes(encoded(self.decisions(fresh)))
                    self.cli(fresh, cutoff=None, extra=['--save-features', str(replacement)])
                else:
                    self.publish_browser(fresh, 'firefox', self.browser_choices(fresh, 'firefox'))
            self.assertFalse(git(self.repo, 'status', '--porcelain', '--', 'data'))
            registry = self.repo / 'config/sources.yml'
            before = registry.read_bytes()
            config = read(registry)
            config['baseline']['daily_window_days'] = 4
            registry.write_bytes(encoded(config))
            new_policy = run_daily.commit_candidate(self.repo)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_bytes(original)
            repaired = run_daily.commit_candidate(self.repo)
            entry = self.repo / 'pipeline/daily_status.py'
            for ref in (base, first, deleted, new_policy, repaired):
                with patch('sys.argv', [str(entry), '--base-commit', ref]):
                    runpy.run_path(str(entry), run_name='__main__')
            if not scoped:
                self.cli(run, cutoff=None, extra=save)

            # Re-sealing the earlier zero with today's registry is a different proposal.
            git(self.repo, 'switch', '-qc', 'altered', new_policy)
            marker.parent.mkdir(parents=True, exist_ok=True)
            changed = json.loads(original)
            changed['scope']['registry'] = browser_status.registry_facts(self.repo, 'weekly_reconcile')[0]
            marker.write_bytes(encoded(browser_status.seal(changed)))
            with self.assertRaisesRegex(ValueError, 'original publication'):
                validate_tree(self.repo, base=new_policy)
            run_daily.commit_candidate(self.repo)
            with self.assertRaisesRegex(ValueError, 'original publication'):
                validate_tree(self.repo, base=new_policy)

            # If the initial alias itself was invalid under its registry, a
            # subsequent change back to the matching policy cannot authorize it.
            git(self.repo, 'switch', '-qc', 'wrong-author-policy', base)
            registry.write_bytes(encoded(config))
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.write_bytes(original)
            wrong_policy = run_daily.commit_candidate(self.repo)
            alias.unlink()
            registry.write_bytes(before)
            run_daily.commit_candidate(self.repo)
            marker.write_bytes(original)
            run_daily.commit_candidate(self.repo)
            with self.assertRaisesRegex(ValueError, 'registry'):
                validate_tree(self.repo, base=wrong_policy)

            # A file with the same backup name and no valid receipt makes no claim.
            git(self.repo, 'switch', '-qc', 'unrelated-backup', base)
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.write_bytes(b'{}')
            run_daily.commit_candidate(self.repo)
            alias.unlink()
            run_daily.commit_candidate(self.repo)
            fresh = run + '-new'
            self.cli(fresh, cutoff=week, mode='weekly_reconcile')
            self.publish_browser(fresh, 'firefox', self.browser_choices(fresh, 'firefox'))
            run_daily.commit_candidate(self.repo)
            validate_tree(self.repo, base=base)

    def test_invalid_first_daily_blob_cannot_claim_the_cutoff(self):
        self.configure_small_registry()
        initial = run_daily.commit_candidate(self.repo)
        day = self.repo / 'data/daily-status/2026-11-24.json'
        day.parent.mkdir(parents=True)
        day.write_bytes(b'null')
        bad = run_daily.commit_candidate(self.repo)
        with self.assertRaises(ValueError):
            validate_tree(self.repo, base=initial)
        day.unlink()
        run_daily.commit_candidate(self.repo)
        self.cli('valid', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        pm = self.folder / 'valid.json'
        pm.write_bytes(encoded(self.decisions('valid')))
        self.cli('valid', cutoff=None, extra=['--save-features', str(pm)])
        run_daily.commit_candidate(self.repo)
        self.assertEqual(1, read(day)['collected_feature_count'])
        validate_tree(self.repo, base=bad)

    def test_current_alias_blocks_daily_replay_and_incomplete_even_when_original_exists(self):
        self.configure_small_registry()
        initial = run_daily.commit_candidate(self.repo)
        self.cli('saved', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        pm = self.folder / 'saved.json'
        pm.write_bytes(encoded(self.decisions('saved')))
        save = ['--save-features', str(pm)]
        self.cli('saved', cutoff=None, extra=save)
        run_daily.commit_candidate(self.repo)
        self.cli('retry', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        day = self.repo / 'data/daily-status/2026-11-24.json'
        original = day.read_bytes()
        for folder, name in ((weekly_status.FOLDER, 'bad-name.bak'),
                             (browser_status.FOLDER + '/daily', '2026-11-24T031000.000000Z.json'),
                             (day.parent.relative_to(self.repo), '2026-02-31.json')):
            alias = self.repo / folder / name
            alias.parent.mkdir(parents=True, exist_ok=True)
            alias.write_bytes(original)
            for state in ('working', 'committed', 'hidden-in-working-tree'):
                if state == 'committed':
                    run_daily.commit_candidate(self.repo)
                if state == 'hidden-in-working-tree':
                    alias.unlink()
                with self.subTest(folder=folder, state=state):
                    for name, args in (('saved', save), ('retry', ['--record-incomplete'])):
                        with self.assertRaises(ValueError):
                            self.cli(name, cutoff=None, extra=args)
                    with self.assertRaises(ValueError):
                        validate_tree(self.repo, base=initial)
                    self.assertEqual(original, day.read_bytes())
            run_daily.commit_candidate(self.repo)
            self.cli('saved', cutoff=None, extra=save)
            self.cli('retry', cutoff=None, extra=['--record-incomplete'])
            validate_tree(self.repo, base=initial)

    def test_shallow_daily_writers_require_history_for_every_snapshot_and_new_date(self):
        self.configure_small_registry()
        original = self.repo
        legacy = original / 'data/daily-status/2026-11-23.json'
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(encoded(dict(date='2026-11-23', cutoff='2026-11-23T08:00:00+09:00',
                                       status='complete', change_count=0, collected_feature_count=0)))
        run_daily.commit_candidate(original)
        self.cli('positive', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.save('positive', self.decisions('positive'))
        day = 'data/daily-status/2026-11-24.json'
        accepted = read(original / day)
        self.assertEqual((1, 1), (accepted['change_count'], accepted['collected_feature_count']))
        for case in ('present', 'zero', 'missing'):
            if case == 'zero':
                (original / day).write_bytes(encoded(dict(accepted, change_count=0, collected_feature_count=0)))
            elif case == 'missing':
                (original / day).unlink()
            run_daily.commit_candidate(original)
            self.repo = self.folder / case
            git(self.folder, 'clone', '-q', '--depth=1', original.as_uri(), str(self.repo))
            validate_tree(self.repo)  # Readers still accept the public 08:00 receipt.
            self.cli(case, cutoff=STATUS_CUTOFF, extra=['--daily-status'])
            files = {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')}
            with self.subTest(case=case, writer='incomplete'), self.assertRaisesRegex(ValueError, 'full history'):
                self.cli(case, cutoff=None, extra=['--record-incomplete'])
            with self.subTest(case=case, writer='browser'), self.assertRaisesRegex(ValueError, 'full history'):
                self.publish_browser(case, 'firefox', self.browser_choices(case, 'firefox'))
            pm = self.folder / (case + '.json')
            pm.write_bytes(encoded(self.decisions(case)))
            with self.subTest(case=case, writer='whole'), self.assertRaisesRegex(ValueError, 'full history'):
                self.cli(case, cutoff=None, extra=['--save-features', str(pm)])
            self.assertEqual(files, {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})
            self.assertEqual('true', git(self.repo, 'rev-parse', '--is-shallow-repository'))
        self.cli('tomorrow', cutoff='2026-11-25T07:00:00+09:00', extra=['--daily-status'])
        pm.write_bytes(encoded(self.decisions('tomorrow')))
        with self.assertRaisesRegex(ValueError, 'full history'):
            self.cli('tomorrow', cutoff=None, extra=['--save-features', str(pm)])
        git(self.repo, 'fetch', '-q', '--unshallow', 'origin')
        self.cli('tomorrow', cutoff=None, extra=['--save-features', str(pm)])
        self.assertEqual(0, read(self.repo / 'data/daily-status/2026-11-25.json')['change_count'])
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.cli('missing', cutoff=None, extra=['--record-incomplete'])

    def test_shallow_daily_signed_retry_and_detail_only_rollback_preserve_outputs(self):
        self.configure_small_registry()
        original = self.repo
        run_daily.commit_candidate(original)
        tip = run_daily.commit_candidate(original)
        self.repo = self.folder / 'clone'
        git(self.folder, 'clone', '-q', original.as_uri(), str(self.repo))
        self.cli('saved', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        pm = self.folder / 'saved.json'
        pm.write_bytes(encoded(self.decisions('saved')))
        self.cli('saved', cutoff=None, extra=['--save-features', str(pm)])
        git(self.repo, 'fetch', '-q', '--depth=1', 'origin', tip)
        with self.assertRaisesRegex(ValueError, 'full history'):
            self.cli('saved', cutoff=None, extra=['--save-features', str(pm)])
        git(self.repo, 'fetch', '-q', '--unshallow', 'origin')
        self.cli('saved', cutoff=None, extra=['--save-features', str(pm)])

        cutoff = '2026-11-25T07:00:00+09:00'
        self.cli('partial', cutoff=cutoff, extra=['--daily-status'])
        self.publish_browser('partial', 'firefox', self.browser_choices('partial', 'firefox', select=False))
        choice = self.browser_choices('partial', 'edge', select=False)
        detail = self.repo / browser_status.detail_path('daily', cutoff)
        prior = detail.read_bytes()
        store = run_daily.store_changes

        def interrupt(*args):
            def stop_after_detail(path, raw):
                run_daily.durable(path, raw)
                if path == detail.resolve():
                    raise KeyboardInterrupt()
            return store(*args, replace=stop_after_detail)

        with patch.object(collect, 'store_changes', interrupt), self.assertRaises(KeyboardInterrupt):
            self.publish_browser('partial', 'edge', choice)
        pending = detail.read_bytes()
        self.assertNotEqual(prior, pending)
        git(self.repo, 'fetch', '-q', '--depth=1', 'origin', tip)
        with self.assertRaisesRegex(ValueError, 'full history'):
            self.cli('partial', cutoff=None, extra=['--record-incomplete'])
        self.assertEqual(pending, detail.read_bytes())
        git(self.repo, 'fetch', '-q', '--unshallow', 'origin')
        self.cli('partial', cutoff=None, extra=['--record-incomplete'])
        self.assertEqual(prior, detail.read_bytes())

    def test_daily_save_detects_a_shallow_second_merge_parent(self):
        self.configure_small_registry()
        original = self.repo
        base = run_daily.commit_candidate(original)
        git(original, 'switch', '-qc', 'side')
        (original / 'side.txt').write_text('side history')
        side = run_daily.commit_candidate(original)
        git(original, 'switch', '-qc', 'first', base)
        run_daily.commit_candidate(original)
        git(original, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
            '-c', 'core.hooksPath=/dev/null', 'merge', '--no-ff', '-qm', 'Merge side', side)
        tip = git(original, 'rev-parse', 'HEAD')
        self.repo = self.folder / 'one-shallow-parent'
        git(self.folder, 'clone', '-q', '--depth=1', '--branch', 'side', original.as_uri(), str(self.repo))
        git(self.repo, 'fetch', '-q', 'origin', tip)
        git(self.repo, 'switch', '-q', '--detach', tip)
        self.assertEqual(side, (self.repo / '.git/shallow').read_text().strip())
        self.assertEqual(2, len(git(self.repo, 'rev-list', '--parents', '-1', tip).split()) - 1)
        self.cli('merged', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        with self.assertRaisesRegex(ValueError, 'full history'):
            self.cli('merged', cutoff=None, extra=['--record-incomplete'])
        self.assertFalse((self.repo / 'data').exists())

    def test_new_weekly_cutoff_saves_after_deepening_the_same_data_only_clone(self):
        self.configure_small_registry()
        run_daily.commit_candidate(self.repo)
        run_daily.commit_candidate(self.repo)
        shallow = self.folder / 'shallow'
        git(self.folder, 'clone', '--quiet', '--depth=1', self.repo.as_uri(), str(shallow))
        self.repo = shallow
        self.assertEqual('true', git(shallow, 'rev-parse', '--is-shallow-repository'))
        self.assertFalse((shallow / 'pipeline').exists())
        base = git(shallow, 'rev-parse', 'HEAD')
        cutoff = '2026-11-29T01:00:00Z'
        self.cli('shallow', cutoff=cutoff, mode='weekly_reconcile')
        pm = self.folder / 'new-week.json'
        pm.write_bytes(encoded(self.decisions('shallow')))
        save = ['--save-features', str(pm)]
        with self.assertRaisesRegex(ValueError, 'full history'):
            self.cli('shallow', cutoff=None, extra=save)
        self.assertFalse((shallow / 'data').exists())
        git(shallow, 'fetch', '-q', '--unshallow', 'origin')
        self.cli('shallow', cutoff=None, extra=save)
        accepted = read(shallow / weekly_status.path(cutoff))
        self.assertEqual(1, accepted['collected_feature_count'])
        validate_tree(shallow, base=base)

    def test_shallow_weekly_retry_cannot_change_routes_after_later_manual_evidence(self):
        self.configure_small_registry()
        template = self.repo
        sid = 'firefox-beta'
        url = self.sources[sid]['url']
        source = self.payloads[url]
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        for first in ('whole', 'browser'):
            self.repo = self.folder / ('original-' + first)
            shutil.copytree(template, self.repo)
            self.payloads[url] = source
            run_daily.commit_candidate(self.repo)
            self.cli(first, cutoff=cutoff, mode='weekly_reconcile')
            if first == 'whole':
                self.save(first, self.decisions(first))
                path = self.repo / weekly_status.path(cutoff)
                self.assertEqual(1, read(path)['collected_feature_count'])
            else:
                self.publish_browser(first, 'firefox', self.browser_choices(first, 'firefox'))
                path = self.repo / browser_status.detail_path('weekly_reconcile', cutoff)
                self.assertEqual(1, read(path)['browsers']['firefox']['collected_feature_count'])
            run_daily.commit_candidate(self.repo)
            self.payloads[url] = source.replace('Tab grouping added.', 'Tab grouping improved.')
            manual = 'manual-' + first
            self.cli(manual, [sid], cutoff='2026-12-01T07:00:00+09:00', mode='manual')
            self.save(manual, self.classified(manual, sid))
            run_daily.commit_candidate(self.repo)
            path.unlink()
            run_daily.commit_candidate(self.repo)
            origin = self.repo
            self.repo = self.folder / ('shallow-' + first)
            git(self.folder, 'clone', '-q', '--depth=1', origin.as_uri(), str(self.repo))
            fresh = 'retry-' + first
            self.cli(fresh, cutoff=cutoff, mode='weekly_reconcile')
            choices = self.browser_choices(fresh, 'firefox')
            self.assertEqual([], choices['decisions'])
            if first == 'whole':
                attempt = lambda: self.publish_browser(fresh, 'firefox', choices)
            else:
                pm = self.folder / 'fresh-whole.json'
                pm.write_bytes(encoded(self.decisions(fresh)))
                attempt = lambda: self.cli(fresh, cutoff=None, extra=['--save-features', str(pm)])
            files = {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')}
            with self.subTest(first=first), self.assertRaisesRegex(ValueError, 'full history'):
                attempt()
            git(self.repo, 'fetch', '-q', '--unshallow', 'origin')
            with self.assertRaisesRegex(ValueError, 'missing'):
                attempt()
            self.assertEqual(files, {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})
            later = 'later-' + first
            self.cli(later, cutoff='2026-12-06T10:00:00+09:00', mode='weekly_reconcile')
            self.save(later, self.decisions(later))

    def test_depth_change_during_receipt_publication_blocks_success_and_rollback(self):
        self.configure_small_registry()
        origin = self.repo
        run_daily.commit_candidate(origin)
        tip = run_daily.commit_candidate(origin)
        for name, mode, browser in (('whole-week', 'weekly_reconcile', None),
                                    ('browser-week', 'weekly_reconcile', 'edge'),
                                    ('browser-day', 'daily', 'edge')):
            self.repo = self.folder / name
            git(self.folder, 'clone', '-q', origin.as_uri(), str(self.repo))
            cutoff = STATUS_CUTOFF if mode == 'daily' else weekly_status.FIRST_GUARDED_CUTOFF
            self.cli(name, cutoff=cutoff, mode=mode, extra=['--daily-status'] if mode == 'daily' else [])
            if mode == 'daily':
                self.publish_browser(name, 'firefox', self.browser_choices(name, 'firefox', select=False))
            if browser:
                decisions = self.browser_choices(name, browser)
                target = browser_status.detail_path(mode, cutoff)
            else:
                decisions = self.decisions(name)
                target = weekly_status.path(cutoff)
            pm = self.folder / (name + '.json')
            pm.write_bytes(encoded(decisions))
            args = ['--save-features', str(pm)] + (['--save-browser', browser] if browser else [])
            store = run_daily.store_changes

            def shrink_after_last(root, txn, changes, before, writer):
                if mode == 'daily':
                    # The aggregate is still incomplete. Publish only the changed detail.
                    day = 'data/daily-status/2026-11-24.json'
                    self.assertEqual(read(root / day), changes[day])
                    changes = {path: value for path, value in changes.items() if path != day}
                def replace(path, raw):
                    run_daily.durable(path, raw)
                    if path == root / target:
                        git(root, 'fetch', '-q', '--depth=1', 'origin', tip)
                return store(root, txn, changes, before, writer, replace=replace)

            with self.subTest(name=name), patch.object(collect, 'store_changes', shrink_after_last):
                with self.assertRaisesRegex(ValueError, 'full history'):
                    self.cli(name, cutoff=None, extra=args)
            self.assertEqual(tip, git(self.repo, 'rev-parse', 'HEAD'))
            pending = {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')}
            with self.assertRaisesRegex(ValueError, 'full history'):
                self.cli(name, cutoff=None, extra=args)
            self.assertEqual(pending, {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})
            git(self.repo, 'fetch', '-q', '--unshallow', 'origin')
            self.cli(name, cutoff=None, extra=args)
            self.assertEqual(pending, {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})
            git(self.repo, 'fetch', '-q', '--depth=1', 'origin', tip)
            with self.assertRaisesRegex(ValueError, 'full history'):
                self.cli(name, cutoff=None, extra=args)

            if name == 'whole-week':
                # Older saved runs have no recorded marker checksum.
                state_path = self.folder / 'runs' / name / 'feature-run.json'
                old_state = read(state_path)
                old_state.pop('weekly_publication')
                state_path.write_bytes(encoded(old_state))
                with self.assertRaisesRegex(ValueError, 'full history'):
                    self.cli(name, cutoff=None, extra=args)
                git(self.repo, 'fetch', '-q', '--unshallow', 'origin')
                self.cli(name, cutoff=None, extra=args)

    def test_unmarked_prior_full_window_blocks_same_cutoff_but_not_next(self):
        self.configure_small_registry()
        sid = 'firefox-beta'
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        # A historical whole or manual full-window publication can leave identical public facts.
        self.cli('old-writer', [sid], cutoff=cutoff, mode='manual', extra=['--since', '2026-01-01'])
        self.save('old-writer', self.classified('old-writer', sid))
        prior = {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')}
        self.cli('new', cutoff='2026-11-29T01:00:00Z', mode='weekly_reconcile')
        with self.assertRaisesRegex(ValueError, 'original publication'):
            self.publish_browser('new', 'edge', self.browser_choices('new', 'edge'))
        with self.assertRaisesRegex(ValueError, 'original publication'):
            self.save('new', self.decisions('new'))
        self.assertEqual(prior, {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})
        later = '2026-12-06T10:00:00+09:00'
        self.cli('next', cutoff=later, mode='weekly_reconcile')
        self.publish_browser('next', 'edge', self.browser_choices('next', 'edge'))
        accepted = read(self.repo / browser_status.detail_path('weekly_reconcile', later))
        self.assertEqual(1, accepted['browsers']['edge']['collected_feature_count'])
        self.assertFalse((self.repo / weekly_status.path(later)).exists())

    def test_reverted_committed_weekly_evidence_blocks_only_its_own_cutoff(self):
        self.configure_small_registry()
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        sid = 'firefox-beta'
        url = self.sources[sid]['url']
        document = self.payloads[url]

        def manual(name, at, text):
            self.payloads[url] = document.replace('added', text)
            self.cli(name, [sid], cutoff=at, mode='manual', extra=['--since', '2026-01-01'])
            self.save(name, self.classified(name, sid))
            return run_daily.commit_candidate(self.repo)

        older = manual('older', '2026-11-22T10:00:00+09:00', 'added')
        template = self.repo
        # Obtain a valid earlier revision whose source and catalog blobs have
        # never appeared on the branch that will contain the witness.
        self.repo = self.folder / 'alternative'
        shutil.copytree(template, self.repo)
        manual('alternative', '2026-11-23T10:00:00+09:00', 'revised')
        files = (collect.FEATURE_CATALOG, 'data/source-items/firefox/firefox-beta.json')
        alternative = {rel: (self.repo / rel).read_bytes() for rel in files}
        self.repo = template
        witness = manual('witness', '2026-11-28T13:00:00-12:00', 'enhanced')
        for variant in ('revert', 'new-blobs'):
            self.repo = self.folder / variant
            shutil.copytree(template, self.repo)
            if variant == 'revert':
                git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=t@example.invalid',
                    '-c', 'core.hooksPath=/dev/null', 'revert', '--no-edit', witness)
            else:
                for rel, raw in alternative.items():
                    path = self.repo / rel
                    self.assertNotEqual(path.read_bytes(), raw)
                    path.write_bytes(raw)
                    self.assertNotEqual(git(self.repo, 'hash-object', rel), git(self.repo, 'rev-parse', older + ':' + rel))
                run_daily.commit_candidate(self.repo)
            restored = run_daily.commit_candidate(self.repo)
            for scoped in (False, True):
                name = variant + str(scoped)
                self.cli(name, cutoff=cutoff, mode='weekly_reconcile')
                pm = self.folder / (name + '.json')
                choices = self.browser_choices(name, 'firefox', select=False) if scoped else self.decisions(name)
                choices['decisions'] = []
                for item in choices['dispositions']:
                    item['disposition'] = 'excluded'
                pm.write_bytes(encoded(choices))
                args = ['--save-features', str(pm)] + (['--save-browser', 'firefox'] if scoped else [])
                with self.subTest(variant=variant, scoped=scoped), self.assertRaisesRegex(ValueError, 'original publication'):
                    self.cli(name, cutoff=None, extra=args)
                # Exercise CI even when the writer has correctly refused the proposal.
                with patch('pipeline.weekly_evidence.check_committed'):
                    self.cli(name, cutoff=None, extra=args)
                with self.assertRaisesRegex(ValueError, 'original publication'):
                    validate_tree(self.repo, base=witness)
                run_daily.commit_candidate(self.repo)
                with self.assertRaisesRegex(ValueError, 'original publication'):
                    validate_tree(self.repo, base=restored)
                git(self.repo, 'switch', '-qc', 'next-' + name, restored)
            name = variant + '-next'
            self.cli(name, cutoff='2026-12-06T10:00:00+09:00', mode='weekly_reconcile')
            self.publish_browser(name, 'firefox', self.browser_choices(name, 'firefox', select=False))
            run_daily.commit_candidate(self.repo)
            validate_tree(self.repo, base=older)

    def test_audited_evidence_shortcut_requires_reachable_digest_and_strictly_later_cutoff(self):
        self.configure_small_registry()
        older = run_daily.commit_candidate(self.repo)
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        self.cli('witness', ['firefox-beta'], cutoff=cutoff, mode='manual', extra=['--since', '2026-01-01'])
        self.save('witness', self.classified('witness', 'firefox-beta'))
        tip = run_daily.commit_candidate(self.repo)
        proof = weekly_evidence.audit(self.repo, tip)
        self.assertEqual('2026-11-29T01:00:00+00:00', proof['maximum'])
        self.assertGreater(proof['objects'], 0)
        bound = weekly_evidence.instant(proof['maximum'])
        future = weekly_evidence.instant('2026-11-29T01:00:00.000001Z')
        for label, anchor, digest, end, reads in (
                ('certified', tip, proof['object_digest'], future, False),
                ('wrong-digest', tip, '0' * 64, future, True),
                ('absent', 'a' * 40, proof['object_digest'], future, True),
                ('earlier-ancestor', older, weekly_evidence.audit(self.repo, older)['object_digest'], future, True),
                ('at-bound', tip, proof['object_digest'], bound, True)):
            with self.subTest(label=label), patch.object(weekly_evidence, 'AUDITED_COMMIT', anchor), \
                    patch.object(weekly_evidence, 'AUDITED_OBJECTS', digest), \
                    patch.object(weekly_evidence, 'AUDITED_MAXIMUM', bound), \
                    patch.object(weekly_evidence, 'committed_windows', wraps=weekly_evidence.committed_windows) as read_blob:
                weekly_evidence.check_committed.cache_clear()
                if end == bound:
                    with self.assertRaisesRegex(ValueError, 'original publication'):
                        weekly_evidence.check_committed(self.repo, tip, '2026-01-01', end)
                else:
                    weekly_evidence.check_committed(self.repo, tip, '2026-01-01', end)
                self.assertEqual(reads, bool(read_blob.call_count))

    def test_unmarked_weekly_window_survives_a_later_revision_in_writers_and_ci(self):
        self.configure_small_registry()
        base = run_daily.commit_candidate(self.repo)
        sid = 'firefox-beta'
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        source = self.repo / 'data/source-items/firefox/firefox-beta.json'
        self.cli('old', [sid], cutoff='2026-11-28T13:00:00-12:00', mode='manual', extra=['--since', '2026-01-01'])
        self.save('old', self.classified('old', sid))
        old = run_daily.commit_candidate(self.repo)
        original = source.read_bytes()
        source.write_bytes(b'{broken historical proposal')
        run_daily.commit_candidate(self.repo)
        source.write_bytes(original)
        run_daily.commit_candidate(self.repo)
        self.payloads[self.sources[sid]['url']] = self.payloads[self.sources[sid]['url']].replace('added', 'updated')
        self.cli('moved', [sid], cutoff=cutoff, mode='manual', extra=['--since', '2026-11-01'])
        self.save('moved', self.classified('moved', sid))
        moved = run_daily.commit_candidate(self.repo)
        template = self.repo
        for index, scoped in enumerate((False, True)):
            self.repo = self.folder / f'history-{index}'
            shutil.copytree(template, self.repo)
            name = f'old-week-{index}'
            self.cli(name, cutoff=cutoff, mode='weekly_reconcile')
            pm = self.folder / (name + '.json')
            pm.write_bytes(encoded(self.browser_choices(name, 'firefox') if scoped else self.decisions(name)))
            save = (['--save-browser', 'firefox'] if scoped else []) + ['--save-features', str(pm)]
            with self.assertRaisesRegex(ValueError, 'original publication'):
                self.cli(name, cutoff=None, extra=save)
            rel = browser_status.detail_path('weekly_reconcile', cutoff) if scoped else weekly_status.path(cutoff)
            # The same policy midnight is still the previous printed day in UTC.
            def alternate_start(root, txn, changes, before, writer):
                marker = changes[rel]
                marker['scope'] = dict(marker['scope'], start='2025-12-31T15:00:00+00:00')
                changes[rel] = browser_status.seal(marker)
                return run_daily.store_changes(root, txn, changes, before, writer)
            with patch.object(collect, 'store_changes', alternate_start):
                with self.assertRaisesRegex(ValueError, 'original publication'):
                    self.cli(name, cutoff=None, extra=save)
            self.assertFalse((self.repo / rel).exists())
            # Manufacture the false zero to check CI independently of the writer.
            with patch('pipeline.weekly_evidence.check_committed'):
                self.cli(name, cutoff=None, extra=save)
            marker = read(self.repo / rel)
            marker['scope']['start'] = '2025-12-31T15:00:00+00:00'
            (self.repo / rel).write_bytes(encoded(browser_status.seal(marker)))
            with self.assertRaisesRegex(ValueError, 'original publication'):
                validate_tree(self.repo, base=old)
            proposed = run_daily.commit_candidate(self.repo)
            for ref in (base, moved, proposed):
                with self.assertRaisesRegex(ValueError, 'original publication'):
                    validate_tree(self.repo, base=ref)
            (self.repo / rel).unlink()
            run_daily.commit_candidate(self.repo)
            validate_tree(self.repo, base=proposed)

        self.repo = self.folder / 'data-only'
        shutil.copytree(template, self.repo, ignore=shutil.ignore_patterns('.git'))
        self.cli('no-history', cutoff=cutoff, mode='weekly_reconcile')
        with self.assertRaisesRegex(ValueError, 'Git history'):
            self.publish_browser('no-history', 'firefox', self.browser_choices('no-history', 'firefox'))
        self.cli('new-week', cutoff='2026-12-06T10:00:00+09:00', mode='weekly_reconcile')
        self.publish_browser('new-week', 'firefox', self.browser_choices('new-week', 'firefox'))

    def test_first_weekly_marker_cannot_hide_earlier_evidence_on_a_merge_or_alias(self):
        self.configure_small_registry()
        base = run_daily.commit_candidate(self.repo)
        cutoff = weekly_status.FIRST_GUARDED_CUTOFF
        rel = weekly_status.path(cutoff)
        marker = self.repo / rel
        self.cli('manual-witness', ['firefox-beta'], cutoff=cutoff, mode='manual', extra=['--since', '2026-01-01'])
        self.save('manual-witness', self.classified('manual-witness', 'firefox-beta'))
        witness = run_daily.commit_candidate(self.repo)
        git(self.repo, 'switch', '-qc', 'marker-first', base)
        self.cli('excluded-week', cutoff=cutoff, mode='weekly_reconcile')
        excluded = self.decisions('excluded-week')
        excluded['decisions'] = []
        for row in excluded['dispositions']:
            row['disposition'] = 'excluded'
        self.save('excluded-week', excluded)
        saved = run_daily.commit_candidate(self.repo)
        validate_tree(self.repo, base=base)
        git(self.repo, '-c', 'user.name=Fixture', '-c', 'user.email=t@example.invalid', '-c', 'core.hooksPath=/dev/null',
            'merge', '--no-ff', '-qm', 'Merge receipts and evidence', witness)
        for ref in (base, witness, saved):
            with self.assertRaisesRegex(ValueError, 'original publication'):
                validate_tree(self.repo, base=ref)

        git(self.repo, 'switch', '-qc', 'first-spelling', base)
        git(self.repo, 'checkout', saved, '--', rel)
        alias = marker.with_suffix('.json.bak')
        marker.rename(alias)
        first_alias = run_daily.commit_candidate(self.repo)
        git(self.repo, 'checkout', witness, '--', 'data/catalog/features', 'data/source-items')
        run_daily.commit_candidate(self.repo)
        alias.rename(marker)
        run_daily.commit_candidate(self.repo)
        with self.assertRaisesRegex(ValueError, 'original publication'):
            validate_tree(self.repo, base=first_alias)

        # A spelling repair alone can retain its original registry and its exact bytes.
        git(self.repo, 'switch', '-qc', 'valid-spelling-repair', first_alias)
        policy = read(self.registry)
        policy['baseline']['daily_window_days'] = 4
        self.registry.write_bytes(encoded(policy))
        run_daily.commit_candidate(self.repo)
        alias.rename(marker)
        run_daily.commit_candidate(self.repo)
        validate_tree(self.repo, base=first_alias)

    def test_browser_cli_weekly_journal_recovery_and_same_run_resume(self):
        self.configure_small_registry()
        edge = self.sources['edge-beta']['url']
        recovered = self.payloads[edge]
        self.payloads[edge] = TimeoutError('incomplete Edge')
        weekly = '2026-11-29T10:00:00+09:00'
        self.cli('week', cutoff=weekly, mode='weekly_reconcile', expected=2)
        self.publish_browser('week', 'firefox', self.browser_choices('week', 'firefox'))
        rel = browser_status.detail_path('weekly_reconcile', weekly)
        detail = read(self.repo / rel)
        self.assertEqual('2026-01-01', detail['scope']['start'][:10])
        self.assertIn('brave', detail['scope']['expected'])
        self.payloads[edge] = recovered
        self.cli('week', cutoff=weekly, mode='weekly_reconcile', extra=['--resume'])
        choices = self.browser_choices('week', 'edge')
        paths = [self.repo / rel, self.repo / collect.FEATURE_CATALOG]
        before = [p.read_bytes() for p in paths]
        original = run_daily.store_changes

        def interrupted(root, txn, changes, previous, writer):
            def crash(path, raw):
                run_daily.durable(path, raw)
                if path == root / rel:
                    raise KeyboardInterrupt()
            return original(root, txn, changes, previous, writer, replace=crash)

        with patch.object(collect, 'store_changes', interrupted), self.assertRaises(KeyboardInterrupt):
            self.publish_browser('week', 'edge', choices)
        with run_lock(self.repo) as writer:
            run_daily.pending_recovery(self.repo.resolve(), writer)
        self.assertEqual(before, [p.read_bytes() for p in paths])
        self.assertFalse((self.repo / 'data/source-items/edge/edge-beta.json').exists())
        self.publish_browser('week', 'edge', choices)
        self.assertEqual(1, read(paths[0])['browsers']['edge']['change_count'])
        self.assertFalse((self.repo / 'data/daily-status').exists())
        with self.assertRaisesRegex(ValueError, 'finish this cutoff'):
            self.save('week', self.decisions('week'))
        validate_tree(self.repo)

    def test_browser_cli_refuses_shared_unpinned_foreign_owner(self):
        self.configure_small_registry()
        self.cli('manual-seed', ['firefox-beta'], cutoff=STATUS_CUTOFF, mode='manual')
        self.save('manual-seed', self.classified('manual-seed', 'firefox-beta'))
        catalog = self.repo / collect.FEATURE_CATALOG
        owner, = read(catalog)
        foreign = dict(owner, browser='edge', feature_id='feature-foreign', canonical_key='legacy-attachment')
        foreign.pop('source_revision_ids')
        catalog.write_bytes(encoded([owner, foreign]))
        url = self.sources['firefox-beta']['url']
        self.payloads[url] = self.payloads[url].replace('Tab grouping added.', 'Tab grouping now supports shortcuts.')
        self.cli('cross', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        prior = catalog.read_bytes()
        with self.assertRaisesRegex(ValueError, 'different browser owner'):
            self.publish_browser('cross', 'firefox', self.browser_choices('cross', 'firefox'))
        self.assertEqual(prior, catalog.read_bytes())
        self.assertFalse((self.repo / 'data/browser-status').exists())

    def test_browser_cli_frozen_complete_and_manual_are_immutable(self):
        self.configure_small_registry()
        self.cli('whole', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.save('whole', self.decisions('whole'))
        receipt = self.repo / 'data/daily-status/2026-11-24.json'
        original = receipt.read_bytes()
        self.cli('frozen', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        with self.assertRaisesRegex(ValueError, 'daily status is complete'):
            self.publish_browser('frozen', 'edge', self.browser_choices('frozen', 'edge'))
        self.cli('frozen', cutoff=None, extra=['--record-incomplete'])
        self.assertEqual(original, receipt.read_bytes())
        self.cli('manual', ['brave-blog'], cutoff=STATUS_CUTOFF, mode='manual')
        with self.assertRaisesRegex(ValueError, 'pinned daily status or weekly'):
            self.publish_browser('manual', 'brave', self.browser_choices('manual', 'brave'))
        self.assertFalse((self.repo / 'data/browser-status').exists())

    def test_browser_cli_final_zero_and_rejects_unrelated_evidence_drift(self):
        self.configure_small_registry()
        self.cli('zero', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.publish_browser('zero', 'firefox', self.browser_choices('zero', 'firefox', select=False))
        evidence = self.repo / 'data/source-items/edge/edge-beta.json'
        evidence.parent.mkdir(parents=True)
        evidence.write_bytes(b'[]')
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            self.publish_browser('zero', 'chrome', self.browser_choices('zero', 'chrome', select=False))
        self.cli('fresh', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        scope = read(self.repo / browser_status.detail_path('daily', STATUS_CUTOFF))['scope']
        for browser in scope['expected'].keys() - {'firefox'}:
            self.publish_browser('fresh', browser, self.browser_choices('fresh', browser, select=False))
        receipt = read(self.repo / 'data/daily-status/2026-11-24.json')
        self.assertEqual(('complete', 0, 0), (receipt['status'], receipt['change_count'], receipt['collected_feature_count']))
        self.assertEqual(b'[]', evidence.read_bytes())
        self.assertFalse((self.repo / collect.FEATURE_CATALOG).exists())
        validate_tree(self.repo)

    def test_browser_cli_rolls_back_after_daily_aggregate_write(self):
        self.configure_small_registry()
        self.cli('run', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        choices = self.browser_choices('run', 'firefox')
        original = run_daily.store_changes
        receipt = 'data/daily-status/2026-11-24.json'

        def fail(root, txn, changes, previous, writer):
            def fail_after_last(path, raw):
                run_daily.durable(path, raw)
                if path == root / receipt:
                    raise OSError('after aggregate')
            return original(root, txn, changes, previous, writer, replace=fail_after_last)

        with patch.object(collect, 'store_changes', fail), self.assertRaisesRegex(OSError, 'after aggregate'):
            self.publish_browser('run', 'firefox', choices)
        self.assertEqual([], list((self.repo / 'data').rglob('*.json')))
        self.publish_browser('run', 'firefox', choices)
        original = (self.repo / receipt).read_bytes()
        detail = self.repo / browser_status.detail_path('daily', STATUS_CUTOFF)
        actual = detail.with_suffix('.backup')
        detail.rename(actual)
        detail.symlink_to(actual)
        with self.assertRaisesRegex(ValueError, 'Unsafe browser publication'):
            self.publish_browser('run', 'edge', self.browser_choices('run', 'edge'))
        self.assertEqual(original, (self.repo / receipt).read_bytes())

    def test_strict_scheduled_save_rejects_state_and_candidate_replacement(self):
        self.configure_small_registry()
        for mode in ('daily', 'weekly_reconcile'):
            with self.subTest(mode=mode):
                args = ['--daily-status'] if mode == 'daily' else []
                self.cli(mode, cutoff=STATUS_CUTOFF, mode=mode, extra=args)
                run = self.folder / 'runs' / mode
                sid = 'firefox-beta'
                path = run / 'work/candidates' / (sid + '.json')
                self.assertTrue(read(path))
                path.write_bytes(encoded([]))
                state_path = run / 'feature-run.json'
                state = read(state_path)
                state['observed'][sid] = run_daily.digest(path.read_bytes())
                state_path.write_bytes(encoded(state))
                classification = run / 'whole.json'
                classification.write_bytes(encoded(self.decisions(mode)))
                with self.assertRaises(ValueError):
                    self.cli(mode, cutoff=None, extra=['--save-features', str(classification)])
                self.assertFalse((self.repo / 'data/daily-status').exists())
                self.assertFalse((self.repo / collect.FEATURE_CATALOG).exists())

    def test_implicit_browser_excerpt_blocks_overlapping_manual_quote(self):
        self.configure_small_registry()
        self.cli('manual-first', ['firefox-beta'], cutoff=STATUS_CUTOFF, mode='manual')
        self.cli('partial', ['firefox-beta'], cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        accepted = self.browser_choices('partial', 'firefox')
        choice, = accepted['decisions']
        full = choice.pop('evidence_quote')
        self.assertEqual('Tab grouping added.', full)
        self.publish_browser('partial', 'firefox', accepted)
        catalog = self.repo / collect.FEATURE_CATALOG
        detail = self.repo / browser_status.detail_path('daily', STATUS_CUTOFF)
        original = catalog.read_bytes(), detail.read_bytes()
        path = self.folder / 'manual-quote.json'
        path.write_bytes(encoded([dict(choice, evidence_quote='Tab grouping')]))
        with self.assertRaisesRegex(ValueError, 'Accepted browser evidence'):
            self.cli('manual-first', cutoff=None, extra=['--save-features', str(path)])
        self.assertEqual(original, (catalog.read_bytes(), detail.read_bytes()))
        effect, = read(detail)['browsers']['firefox']['effects']
        self.assertEqual(browser_status.value_hash(full), effect['quote'])
        path.write_bytes(encoded([dict(choice, evidence_quote=full)]))
        self.cli('manual-first', cutoff=None, extra=['--save-features', str(path)])
        self.assertEqual(original[1], detail.read_bytes())
        validate_tree(self.repo)

    def test_strict_scheduled_checkpoint_loss_and_legacy_format(self):
        self.configure_small_registry()
        for mode in ('daily', 'weekly_reconcile'):
            with self.subTest(mode=mode):
                name = 'format-' + mode
                args = ['--daily-status'] if mode == 'daily' else []
                self.cli(name, cutoff=STATUS_CUTOFF, mode=mode, extra=args)
                run = self.folder / 'runs' / name
                state_path, work = run / 'feature-run.json', run / 'work'
                state_raw = state_path.read_bytes()
                pin = work / 'browser-pin.json'
                checkpoint = work / 'checkpoints/firefox-beta.json'
                choice = run / 'pm.json'
                choice.write_bytes(encoded(self.decisions(name)))
                save = ['--save-features', str(choice)]
                for target in (pin, checkpoint):
                    original = target.read_bytes()
                    target.unlink()
                    with self.assertRaises(ValueError):
                        self.cli(name, cutoff=None, extra=save)
                    target.write_bytes(b'{}')
                    with self.assertRaises(ValueError):
                        self.cli(name, cutoff=None, extra=save)
                    target.write_bytes(original)
                for field, value in (('status', 'partial'), ('source_id', 'edge-beta'),
                                     ('cutoff', '2026-11-25T07:00:00+09:00')):
                    state = json.loads(state_raw)
                    state['source_results']['firefox-beta'][field] = value
                    state_path.write_bytes(encoded(state))
                    with self.assertRaises(ValueError):
                        self.cli(name, cutoff=None, extra=save)
                state = json.loads(state_raw)
                state.pop('browser_pin')
                state_path.write_bytes(encoded(state))
                with self.assertRaises(ValueError):
                    self.cli(name, cutoff=None, extra=save)
                pin.unlink()
                shutil.rmtree(work / 'checkpoints')
                with self.assertRaises(ValueError):
                    self.cli(name, cutoff=None, extra=save)
                # The first released pinned format used a plain workspace owner.
                (work / '.owner').write_text(state['workspace_id'])
                with self.assertRaisesRegex(ValueError, 'baseline changed'):
                    self.cli(name, cutoff=None, extra=save)
        self.assertFalse((self.repo / 'data').exists())

    def test_genuine_pre_pin_format_uses_its_recorded_local_code_tree(self):
        # Independent synthetic Git history works in CI with a depth-one checkout.
        code = self.folder / 'earlier-code'
        (code / 'pipeline').mkdir(parents=True)
        (code / 'pipeline/collect.py').write_text('# Pre-pin collector tree fixture')
        earlier = run_daily.commit_candidate(code)
        self.configure_small_registry()
        with patch.object(run_daily, 'CODE_REPOSITORY', code):
            self.cli('old', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
            run = self.folder / 'runs/old'
            state_path = run / 'feature-run.json'
            state = read(state_path)
            self.assertEqual(earlier, state['code_commit'])
            state.pop('browser_pin')
            state_path.write_bytes(encoded(state))
            work = run / 'work'
            (work / '.owner').write_text(state['workspace_id'])
            (work / 'browser-pin.json').unlink()
            shutil.rmtree(work / 'checkpoints')
            choice = run / 'pm.json'
            choice.write_bytes(encoded(self.decisions('old')))
            self.cli('old', cutoff=None, extra=['--save-features', str(choice)])
            self.cli('old', cutoff=None, extra=['--save-features', str(choice)])
        self.assertEqual(1, read(self.repo / 'data/daily-status/2026-11-24.json')['change_count'])

    def test_pre_pin_strict_save_requires_every_original_source_result(self):
        self.configure_small_registry()
        code = self.folder / 'old-code'
        (code / 'pipeline').mkdir(parents=True)
        (code / 'pipeline/collect.py').write_text('# Pre-pin collector tree fixture')
        run_daily.commit_candidate(code)
        sid = 'edge-beta'
        url = self.sources[sid]['url']
        with patch.object(run_daily, 'CODE_REPOSITORY', code):
            for mode in ('daily', 'weekly_reconcile'):
                invalid_results = dict(wrong_source={'source_id': 'firefox-beta'},
                                       wrong_cutoff={'cutoff': '2026-11-25T07:00:00+09:00'},
                                       errors={'errors': [{'reason': 'unresolved request'}]},
                                       corrupt={'checkpoint_invalid': True})
                for scenario in ('missing', 'partial', 'extra', *invalid_results, 'valid'):
                    with self.subTest(mode=mode, scenario=scenario):
                        name = mode + '-' + scenario
                        args = ['--daily-status'] if mode == 'daily' else []
                        responses = {url: TimeoutError('incomplete Edge')} if scenario == 'partial' else {}
                        with patch.dict(self.payloads, responses):
                            self.cli(name, cutoff=STATUS_CUTOFF, mode=mode, extra=args,
                                     expected=2 if scenario == 'partial' else 0)
                        run = self.folder / 'runs' / name
                        state_path, work = run / 'feature-run.json', run / 'work'
                        state = read(state_path)
                        state.pop('browser_pin')
                        (work / '.owner').write_text(state['workspace_id'])
                        (work / 'browser-pin.json').unlink()
                        shutil.rmtree(work / 'checkpoints')
                        if scenario == 'missing':
                            state['source_results'].pop(sid)
                        elif scenario == 'partial':
                            self.assertEqual('partial', state['source_results'][sid]['status'])
                            state.update(status='complete', complete=True)
                        elif scenario == 'extra':
                            state['source_results']['unregistered'] = state['source_results'][sid]
                        elif scenario in invalid_results:
                            state['source_results'][sid].update(invalid_results[scenario])
                        state_path.write_bytes(encoded(state))
                        choices = self.decisions(name)
                        for row in choices['dispositions']:
                            row['disposition'] = 'excluded'
                        choices['decisions'] = []
                        path = run / 'pm.json'
                        path.write_bytes(encoded(choices))
                        save = ['--save-features', str(path)]
                        if scenario == 'valid':
                            self.cli(name, cutoff=None, extra=save)
                            self.assertEqual('saved', read(state_path)['status'])
                        else:
                            prior = {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')}
                            with self.assertRaises(ValueError):
                                self.cli(name, cutoff=None, extra=save)
                            self.assertEqual(prior, {p: p.read_bytes() for p in (self.repo / 'data').rglob('*.json')})
                            self.assertEqual(state, read(state_path))
        receipt = read(self.repo / 'data/daily-status/2026-11-24.json')
        self.assertEqual(('complete', 0, 0), (receipt['status'], receipt['collected_feature_count'], receipt['change_count']))

    def test_old_null_quote_uses_its_own_immutable_revision_after_append(self):
        from pipeline.normalize.storage import publish
        self.configure_small_registry()
        self.cli('first', ['firefox-beta'], cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        accepted = self.browser_choices('first', 'firefox')
        choice, = accepted['decisions']
        full = choice.pop('evidence_quote')
        self.publish_browser('first', 'firefox', accepted)
        self.publish_browser('first', 'firefox', accepted)
        rel = browser_status.detail_path('daily', STATUS_CUTOFF)
        detail = read(self.repo / rel)
        effect, = detail['browsers']['firefox']['effects']
        effect['quote'] = None
        original = encoded(browser_status.seal(detail))
        (self.repo / rel).write_bytes(original)
        run_daily.commit_candidate(self.repo)
        url = self.sources['firefox-beta']['url']
        self.payloads[url] = self.payloads[url].replace(full, 'Tab grouping supports shortcuts.')
        self.cli('update', ['firefox-beta'], cutoff='2026-11-25T07:00:00+09:00', mode='manual')
        path = self.folder / 'update-pm.json'
        path.write_bytes(encoded(self.classified('update', 'firefox-beta')))
        self.cli('update', cutoff=None, extra=['--save-features', str(path)])
        catalog = read(self.repo / collect.FEATURE_CATALOG)
        feature, = catalog
        revisions = feature['source_revision_ids'][choice['source_item_id']]
        self.assertEqual(2, len(revisions))
        self.assertEqual(choice['revision_id'], revisions[0])
        feature['source_revision_excerpts'] = {revisions[0]: 'Tab grouping'}
        with self.assertRaisesRegex(ValueError, 'Accepted browser evidence'):
            publish(self.repo, {collect.FEATURE_CATALOG: catalog}, self.folder / 'normalize')
        feature['source_revision_excerpts'][revisions[0]] = full
        publish(self.repo, {collect.FEATURE_CATALOG: catalog}, self.folder / 'normalize')
        self.assertEqual(original, (self.repo / rel).read_bytes())
        validate_tree(self.repo)

    def test_browser_witness_protects_against_later_manual_and_weekly_saves(self):
        self.configure_small_registry()
        run_daily.commit_candidate(self.repo)
        sid = 'firefox-beta'
        self.cli('manual', [sid], cutoff=STATUS_CUTOFF, mode='manual')
        self.cli('week', cutoff=STATUS_CUTOFF, mode='weekly_reconcile')
        self.cli('day', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        accepted = self.browser_choices('day', 'firefox')
        self.publish_browser('day', 'firefox', accepted)
        run_daily.commit_candidate(self.repo)
        detail = self.repo / browser_status.detail_path('daily', STATUS_CUTOFF)
        catalog = self.repo / collect.FEATURE_CATALOG
        before = detail.read_bytes(), catalog.read_bytes()
        shorter = [dict(choice, evidence_quote='Tab grouping') for choice in accepted['decisions']]
        for name, classification in [('manual', shorter), ('week', dict(self.decisions('week'), decisions=shorter))]:
            path = self.folder / (name + '-overlap.json')
            path.write_bytes(encoded(classification))
            with self.assertRaisesRegex(ValueError, 'Accepted browser evidence or feature link changed'):
                self.cli(name, cutoff=None, extra=['--save-features', str(path)])
            self.assertEqual(before, (detail.read_bytes(), catalog.read_bytes()))
        path.write_bytes(encoded(accepted['decisions']))
        self.cli('manual', cutoff=None, extra=['--save-features', str(path)])
        self.assertEqual(before, (detail.read_bytes(), catalog.read_bytes()))
        validate_tree(self.repo)

    def test_browser_ci_compares_receipt_inventory_and_registry_with_git_base(self):
        self.configure_small_registry()
        base = run_daily.commit_candidate(self.repo)
        self.cli('one', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.publish_browser('one', 'firefox', self.browser_choices('one', 'firefox', select=False))
        detail_path = self.repo / browser_status.detail_path('daily', STATUS_CUTOFF)
        initial = detail_path.read_bytes()
        fake = read(detail_path)
        fake['scope']['registry'] = 'f' * 64
        detail_path.write_bytes(encoded(browser_status.seal(fake)))
        with self.assertRaisesRegex(ValueError, 'registry fingerprint'):
            validate_tree(self.repo)
        run_daily.commit_candidate(self.repo)
        with self.assertRaisesRegex(ValueError, 'registry fingerprint'):
            validate_tree(self.repo, base=base)
        detail_path.write_bytes(initial)
        accepted = run_daily.commit_candidate(self.repo)
        registry = read(self.registry)
        next(s for s in registry['sources'] if s['source_id'] == 'firefox-ios')['enabled'] = True
        self.registry.write_bytes(encoded(registry))
        validate_tree(self.repo, base=accepted)
        run_daily.commit_candidate(self.repo)
        validate_tree(self.repo, base=accepted)
        shutil.rmtree(self.repo / browser_status.FOLDER)
        with self.assertRaisesRegex(ValueError, 'Committed browser detail is missing'):
            validate_tree(self.repo)
        run_daily.commit_candidate(self.repo)
        with self.assertRaisesRegex(ValueError, 'Committed browser detail is missing'):
            validate_tree(self.repo, base=accepted)

    def test_normalize_and_browser_writers_share_one_repository_lock(self):
        from pipeline.normalize.storage import publish
        self.configure_small_registry()
        self.cli('day', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        choices = self.browser_choices('day', 'firefox', select=False)
        original = run_daily.store_changes

        def competing_normalization(root, txn, changes, previous, writer):
            with self.assertRaisesRegex(RuntimeError, 'repository lock'):
                publish(root, {}, self.folder / 'normalize')
            return original(root, txn, changes, previous, writer)

        with patch.object(collect, 'store_changes', competing_normalization):
            self.publish_browser('day', 'firefox', choices)

        def competing_collection(source, dest):
            with self.assertRaisesRegex(RuntimeError, 'repository lock'):
                self.cli('competitor', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
            source.replace(dest)

        publish(self.repo, {'data/aliases/corrections.json': []}, self.folder / 'normalize',
                replace=competing_collection)
        self.assertFalse((self.folder / 'runs/competitor/feature-run.json').exists())
        validate_tree(self.repo)

    def test_daily_cli_marks_partial_and_recovers_to_complete_zero(self):
        self.configure_small_registry()
        decisions = self.folder / 'decisions.json'
        decisions.write_bytes(encoded(dict(decisions=[], dispositions=[])))
        receipt = self.repo / 'data/daily-status/2026-11-24.json'
        self.cli('subset', ['firefox-beta'], cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        with self.assertRaisesRegex(ValueError, 'all pinned sources'):
            self.cli('subset', cutoff=None, extra=['--save-features', str(decisions)])
        self.assertFalse(receipt.exists())
        self.cli('subset', cutoff=None, extra=['--record-incomplete'])
        self.assertEqual(('incomplete', None, None), tuple(read(receipt)[key]
                         for key in ('status', 'change_count', 'collected_feature_count')))

        self.payloads = {url: body.replace('2026-11-10', '2026-01-10') for url, body in self.payloads.items()}
        firefox = self.sources['firefox-beta']['url']
        recovered = self.payloads[firefox]
        self.payloads[firefox] = TimeoutError('synthetic Firefox outage')
        self.cli('day', cutoff=STATUS_CUTOFF, extra=['--daily-status'], expected=2)
        self.assertEqual({'firefox-beta'}, {sid for sid, item in self.state('day')['source_results'].items()
                                           if item['status'] != 'complete'})
        self.cli('day', cutoff=None, extra=['--record-incomplete'])
        self.assertEqual(('incomplete', None, None), tuple(read(receipt)[key]
                         for key in ('status', 'change_count', 'collected_feature_count')))
        self.payloads[firefox] = recovered
        self.cli('day', cutoff=STATUS_CUTOFF, extra=['--daily-status', '--resume'])
        dispositions = [dict(item, disposition='excluded') for item in self.decisions('day')['dispositions']]
        decisions.write_bytes(encoded(dict(decisions=[], dispositions=dispositions)))
        self.cli('day', cutoff=None, extra=['--save-features', str(decisions)])
        self.assertEqual(('complete', 0, 0), tuple(read(receipt)[key]
                         for key in ('status', 'change_count', 'collected_feature_count')))

    def test_racing_saves_in_three_modes_keep_one_revision_and_one_daily_status(self):
        self.configure_small_registry()
        with run_lock(self.repo), self.assertRaisesRegex(RuntimeError, 'lock'):
            self.cli('week', cutoff=STATUS_CUTOFF, mode='weekly_reconcile')
        self.cli('week', cutoff=STATUS_CUTOFF, mode='weekly_reconcile')
        self.observed_at = '2026-11-24T09:01:00+09:00'
        self.cli('manual', cutoff=STATUS_CUTOFF, mode='manual')
        self.observed_at = '2026-11-24T09:02:00+09:00'
        self.cli('day', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        with self.assertRaisesRegex(ValueError, 'does not cover all'):
            self.save('week', dict(decisions=[], dispositions=[]))
        with self.assertRaisesRegex(ValueError, 'all enabled sources'):
            self.save('week', self.decisions('week'), allow_partial=True)
        week, manual, day = self.decisions('week'), self.classified('manual', 'firefox-beta'), self.decisions('day')
        self.save('day', day)
        status = self.repo / 'data/daily-status/2026-11-24.json'
        public = status.read_bytes()
        self.assertEqual((1, 1), (read(status)['collected_feature_count'], read(status)['change_count']))
        self.save('manual', manual)
        self.save('week', week)
        self.assertEqual(public, status.read_bytes())
        feature, = read(self.repo / collect.FEATURE_CATALOG)
        evidence, = read(self.repo / 'data/source-items/firefox/firefox-beta.json')
        self.assertEqual([evidence['source_item_id']], feature['source_item_ids'])
        self.assertEqual(1, len(evidence['revisions']))
        self.assertEqual([evidence['revisions'][0]['revision_id']], feature['source_revision_ids'][evidence['source_item_id']])
        self.assertEqual('2026-11-24T09:02:00+09:00', evidence['observed_at'])

    def test_weekly_save_first_preserves_daily_baseline_gate_and_does_not_backfill_gap(self):
        self.configure_small_registry()
        self.cli('stale', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.cli('week', cutoff=STATUS_CUTOFF, mode='weekly_reconcile')
        self.save('week', self.decisions('week'))
        self.assertFalse((self.repo / 'data/daily-status').exists())
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            self.save('stale', self.decisions('stale'))
        self.cli('manual', cutoff=STATUS_CUTOFF, mode='manual')
        self.save('manual', [])
        self.cli('day', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.save('day', self.decisions('day'))
        status = self.repo / 'data/daily-status/2026-11-24.json'
        self.assertEqual((0, 0), (read(status)['collected_feature_count'], read(status)['change_count']))
        self.cli('after-gap', cutoff='2027-01-04T07:00:00+09:00', extra=['--daily-status'])
        self.assertEqual('2026-12-05T07:00:00+09:00', self.state('after-gap')['start'])
        self.save('after-gap', self.decisions('after-gap'))
        self.assertEqual({'2026-11-24.json', '2027-01-04.json'}, {p.name for p in status.parent.iterdir()})

    def test_mutable_enumeration_changed_on_resume_cannot_certify_old_cutoff(self):
        sid = 'chrome-platform-status'
        registry = read(self.registry)
        next(source for source in registry['sources'] if source['source_id'] == sid)['discovery']['max_pages'] = 1
        self.registry.write_bytes(encoded(registry))
        base = 'https://chromestatus.com/api/v0/features?num=100&start='
        rows = [dict(id=i, name='Tabs', summary='Organize tabs', updated={'when': '2026-11-15'}) for i in (1, 2, 3)]
        self.payloads[base + '0'] = dict(total_count=2, features=[rows[0]])
        self.payloads[base + '1'] = dict(total_count=2, features=[rows[1]])
        self.cli('mutable', [sid], expected=2)
        self.payloads[base + '0'] = dict(total_count=2, features=[rows[2]])
        self.cli('mutable', cutoff=None, extra=['--resume'], expected=2)
        self.assertIn('Mutable enumeration changed', str(self.state('mutable')['source_results'][sid]))
        self.cli('new', [sid], expected=2)
        self.cli('new', cutoff=None, extra=['--resume'])
        self.assertEqual({'2', '3'}, {r['item_key'] for r in self.candidates('new', sid)})

    def test_offset_pagination_verifies_cached_prefix_before_extending_it(self):
        sid = 'brave-releases'
        api = 'https://api.github.com/repos/brave/brave-browser/releases?per_page=100&page='
        first, second = api + '1', api + '2'
        registry = read(self.registry)
        next(source for source in registry['sources'] if source['source_id'] == sid)['discovery']['max_pages'] = 1
        self.registry.write_bytes(encoded(registry))
        def release(number):
            return {'id': number, 'html_url': f'https://github.com/brave/brave-browser/releases/tag/v{number}',
                    'published_at': '2026-11-20T06:00:00Z', 'tag_name': f'v{number}', 'body': '- Tab groups.'}
        pages = {first: [release(1)], second: [release(2)]}
        def fetch(url):
            return Response(url, json.dumps(pages[url]).encode(),
                            headers={'Link': f'<{second}>; rel="next"'} if url == first else {},
                            observed_at=OBSERVED)
        self.request = fetch
        self.cli('pages', [sid], mode='manual', expected=2)
        pages[first] = [release(3)]
        self.cli('pages', cutoff=None, extra=['--resume'], expected=2)
        self.assertIn('Mutable enumeration changed', str(self.state('pages')['source_results'][sid]))

    def test_cooperative_time_budget_leaves_timed_out_source_retryable(self):
        sid = 'firefox-beta'
        url = self.sources[sid]['url']
        self.payloads[url] = self.article('2026-11-10', body='c-release-notes')
        registry = read(self.registry)
        registry['baseline']['source_attempt_seconds'] = 1
        self.registry.write_bytes(encoded(registry))
        clock = [0]
        original = self.request
        def slow(request_url):
            clock[0] = 2
            return original(request_url)
        self.request = slow
        with patch('pipeline.collectors.browser.collector.monotonic', side_effect=lambda: clock[0]):
            self.cli('timeout', [sid], expected=2)
        self.assertIn('time budget', str(self.state('timeout')['source_results'][sid]))
        self.calls.clear()
        self.cli('timeout', cutoff=None, extra=['--resume'])
        self.assertEqual([], self.calls)
        self.assertEqual(1, len(self.candidates('timeout', sid)))

    def test_only_future_modification_time_is_not_a_future_publication(self):
        sid = 'firefox-beta'
        url = self.sources[sid]['url']
        self.payloads[url] = ('<time itemprop="dateModified" datetime="2026-11-24T08:00:01+09:00"></time>'
                              '<div class="c-release-notes"><p>Prior version unavailable.</p></div>')
        self.cli('future-only', [sid], expected=2)
        self.assertEqual([], self.candidates('future-only', sid))
        self.assertIn('revision after cutoff', str(self.state('future-only')['source_results'][sid]))

    def test_article_owns_its_modification_and_explicit_edit_overrides_advisory_year(self):
        sid = 'firefox-beta'
        url = self.sources[sid]['url']
        self.payloads[url] = (self.article('2026-03-01', body='c-release-notes')
                              + '<article itemscope itemtype="https://schema.org/NewsArticle">'
                              + '<time itemprop="dateModified" datetime="2026-11-15"></time></article>')
        self.cli('sidebar', [sid])
        self.assertEqual([], self.candidates('sidebar', sid))
        sid = 'firefox-security'
        url = self.sources[sid]['url']
        detail = 'https://www.mozilla.org/en-US/security/advisories/mfsa2026-01/'
        self.payloads[url] = (f'<article><a href="{detail}">Advisory</a><time datetime="2026-03-01"></time>'
                              '<time itemprop="dateModified" datetime="2027-02-04"></time></article>')
        self.payloads[detail] = '<main><p id="item">An updated browser capability.</p></main>'
        self.cli('older-advisory', [sid], cutoff='2027-02-10T08:00:00+09:00')
        row, = self.candidates('older-advisory', sid)
        self.assertEqual(('2027-02-04', 'item_change'),
                         (row['temporal_scope']['evidence_date'], row['temporal_scope']['basis']))

    @staticmethod
    def firefox_advisory(day=None, surrounding='', summary_extra=''):
        date = f'<dt>Announced</dt><dd>{day}</dd>' if day else ''
        return ('<div id="main-content"><main>' + surrounding +
                '<article class="mzp-c-article"><div class="advisory"><dl class="summary">'
                + date + summary_extra + '</dl><p id="entry">Browser update.</p></div></article>'
                '</main><p id="other-unit">Additional product note.</p></div>')

    def test_firefox_advisory_announced_window_and_unchanged_queue(self):
        sid = 'firefox-security'
        dates = {'old': 'October 24, 2026', 'lower': 'October 25, 2026',
                 'unchanged': 'November 10, 2026', 'upper': 'November 24, 2026',
                 'future': 'November 25, 2026', 'undated': None}
        urls = {name: f'https://www.mozilla.org/en-US/security/advisories/mfsa2026-{i:02}/'
                for i, name in enumerate(dates, 1)}
        self.payloads[self.sources[sid]['url']] = ''.join(
            f'<a href="{url}">Advisory</a>' for url in urls.values())
        for name, day in dates.items():
            self.payloads[urls[name]] = self.firefox_advisory(day)

        self.cli('legacy', [sid], mode='legacy')
        baseline = self.candidates('legacy', sid)
        self.assertIn(urls['old'], {r['evidence']['url'] for r in baseline})
        prior_ids = {r['source_item_id'] for r in baseline if r['evidence']['url'] == urls['unchanged']}
        self.assertTrue(prior_ids)
        self.save('legacy', [choice for choice in self.classified('legacy', sid)
                             if choice['source_item_id'] in prior_ids])

        self.cli('daily', [sid])
        rows = self.candidates('daily', sid)
        self.assertEqual({(urls['lower'], '2026-10-25', 'day'),
                          (urls['upper'], '2026-11-24', 'day'),
                          (urls['undated'], None, 'unknown')},
                         {(r['evidence']['url'], r['published_at'], r['temporal_scope']['precision']) for r in rows})
        retained_urls = {urls[n] for n in ('lower', 'upper', 'undated')}
        fields = ('source_item_id', 'item_key', 'published_at', 'summary', 'item_content_sha256')
        self.assertEqual({tuple(r[f] for f in fields) for r in baseline if r['evidence']['url'] in retained_urls},
                         {tuple(r[f] for f in fields) for r in rows})
        self.assertTrue({'entry', 'other-unit'} <= {r['item_key'] for r in rows})

    def test_firefox_advisory_only_primary_summary_dates_the_document(self):
        sid = 'firefox-security'
        url = 'https://www.mozilla.org/en-US/security/advisories/mfsa2026-01/'
        self.payloads[self.sources[sid]['url']] = f'<a href="{url}">Advisory</a>'
        wrong = '<dl class="summary"><dt>Announced</dt><dd>January 2, 2026</dd></dl>'
        other_article = f'<article><div class="advisory">{wrong}</div></article>'
        surrounding = (f'<nav>{other_article}</nav><footer>{other_article}</footer>'
                       f'<div class="comments">{other_article}</div><aside>{other_article}</aside>'
                       f'<article>{wrong}{other_article}</article>')
        unrelated_date = '<dt class="c-release-date">January 2, 2026</dt><dd><time datetime="2026-01-02"></time></dd>'
        for name, value, extra, expected in [
                ('dated', 'November 10, 2026', '', '2026-11-10'),
                ('unknown', None, '', None),
                ('ambiguous', 'November 10, 2026', other_article, None)]:
            with self.subTest(name=name):
                self.payloads[url] = self.firefox_advisory(value, surrounding + extra, unrelated_date)
                self.cli(name, [sid])
                rows = self.candidates(name, sid)
                self.assertEqual({expected}, {r['published_at'] for r in rows})
                self.assertEqual({expected}, {r['temporal_scope']['evidence_date'] for r in rows})

    def test_firefox_layout_wrappers_cannot_substitute_a_page_header_date(self):
        sid = 'firefox-security'
        url = 'https://www.mozilla.org/en-US/security/advisories/mfsa2026-01/'
        self.payloads[self.sources[sid]['url']] = f'<a href="{url}">Notice</a>'
        header = ('<header><time datetime="2026-01-01"></time>'
                  '<article><div class="advisory"><dl class="summary">'
                  '<dt>Announced</dt><dd>January 1, 2026</dd></dl></div></article></header>')
        item_summary = '<dl class="summary"><dt>Announced</dt><dd>January 2, 2026</dd></dl>'
        subitems = f'<section>{item_summary}</section><div>{item_summary}</div>'
        for name, field, expected in [
                ('wrapped', '<dt>Announced</dt><dd>November 10, 2026</dd>', '2026-11-10'),
                ('empty', '<dt>Announced</dt><dd></dd>', None),
                ('missing', '', None),
                ('no-summary', None, None),
                ('conflict', '<dt>Announced</dt><dd>November 10, 2026</dd>'
                             '<dt>Announced</dt><dd>January 1, 2026</dd>', None)]:
            with self.subTest(name=name):
                summary = f'<dl class="summary">{field}</dl>' if field is not None else ''
                self.payloads[url] = (
                    '<div id="main-content">' + header + '<main><div><article><div><div class="advisory">'
                    + summary + subitems + '<p id="note">Browser update.</p>'
                    '</div></div></article></div></main></div>')
                self.cli(name, [sid])
                rows = self.candidates(name, sid)
                self.assertEqual({expected}, {r['published_at'] for r in rows})
                self.assertEqual({expected}, {r['temporal_scope']['evidence_date'] for r in rows})

    def brave_bundle(self, rows, version):
        from test_brave_metadata import bundle, page
        data = bundle([page(rows)])
        data.update(version=version, cutoff=CUTOFF, started_at='2026-11-24T08:01:00+09:00',
                    observed_at=OBSERVED)
        for field in ('first_page_recheck', 'oldest_page_check'):
            data[field]['observed_at'] = OBSERVED
        path = self.folder / f'brave-v{version}.json'
        path.write_bytes(encoded(data))
        return ['--brave-release-metadata', str(path)]

    def test_brave_v3_finds_only_recent_edit_and_v2_records_older_gap(self):
        from test_brave_metadata import row
        sid = 'brave-releases'
        api = 'https://api.github.com/repos/brave/brave-browser/releases'
        recent = dict(row(9, '2026-03-15T00:00:00Z'), updated_at='2026-11-19T00:00:00Z')
        ancient = dict(row(10, '2026-02-01T00:00:00Z'), updated_at='2026-03-01T00:00:00Z')
        self.payloads[api + '?per_page=100&page=1'] = []
        self.payloads[api + '/9'] = dict(id=9, tag_name='v9', html_url=recent['url'], draft=False,
                                         published_at=recent['published_at'], body='- Add tab groups.')
        self.cli('v3', [sid], mode='manual', extra=self.brave_bundle([recent, ancient], 3))
        result, = self.candidates('v3', sid)
        self.assertEqual(recent['updated_at'], result['temporal_scope']['evidence_date'])
        self.assertEqual(2, len(self.calls))
        old = [{key: val for key, val in r.items() if key != 'updated_at'} for r in [recent, ancient]]
        self.calls.clear()
        self.cli('v2', [sid], mode='manual', extra=self.brave_bundle(old, 2), expected=2)
        self.assertEqual([api + '?per_page=100&page=1'], self.calls)
        self.assertIn('2 older releases', str(self.state('v2')['source_results'][sid]))

    def test_brave_missing_bodies_make_progress_one_per_resume(self):
        from test_brave_metadata import row
        sid = 'brave-releases'
        registry = read(self.registry)
        next(s for s in registry['sources'] if s['source_id'] == sid)['discovery']['max_documents'] = 1
        self.registry.write_bytes(encoded(registry))
        api = 'https://api.github.com/repos/brave/brave-browser/releases'
        rows = [dict(row(i, '2026-11-17T00:00:00Z'), updated_at='2026-11-17T00:00:00Z') for i in (1, 2)]
        self.payloads[api + '?per_page=100&page=1'] = []
        for item in rows:
            self.payloads[api + '/' + str(item['id'])] = dict(id=item['id'], tag_name=item['tag_name'],
                html_url=item['url'], draft=False, published_at=item['published_at'], body='- Add tab groups.')
        metadata = self.brave_bundle(rows, 3)
        self.cli('bounded', [sid], mode='manual', extra=metadata, expected=2)
        self.assertEqual([api + '?per_page=100&page=1', api + '/1'], self.calls)
        self.calls.clear()
        self.cli('bounded', cutoff=None, extra=['--resume', *metadata])
        self.assertEqual([api + '/2'], self.calls)
        self.assertEqual(2, len(self.candidates('bounded', sid)))

    def test_brave_monthly_search_cannot_hide_a_release_missing_from_frozen_inventory(self):
        from urllib.parse import urlencode
        from test_brave_metadata import row
        sid = 'brave-releases'
        entry = dict(row(1, '2026-10-10T00:00:00Z'), updated_at='2026-10-10T00:00:00Z')
        api = 'https://api.github.com/repos/brave/brave-browser/releases?per_page=100&page=1'
        self.payloads[api] = [dict(id=1, tag_name='v1', html_url=entry['url'], draft=False,
                                   published_at=entry['published_at'], body='- Historical change.')]
        query = 'created:2026-10-01..2026-10-31'
        url = self.sources[sid]['url'] + '?' + urlencode({'q': query})
        self.payloads[url] = {'payload': {'releasesIndexRoute': {'filterPhrase': query, 'page': 1,
                              'toc': [{'id': 1001, 'anchorId': 'missing'}]},
                              'releasesIndexRoute.Results': {'value': '<section id="missing"></section>'}}}
        with patch('pipeline.collectors.browser.collector.GITHUB_REST_CAP', 1):
            self.cli('missing', [sid], mode='manual', extra=self.brave_bundle([entry], 3), expected=2)
        self.assertIn('absent from frozen metadata: 1001', str(self.state('missing')['source_results'][sid]))

    def test_daily_stale_positive_and_excluded_decisions_refuse_changed_weekly_catalog(self):
        self.configure_small_registry()
        self.cli('waiting', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        positive = self.decisions('waiting')
        excluded = dict(decisions=[], dispositions=[dict(item, disposition='excluded')
                                                    for item in positive['dispositions']])
        catalog = self.repo / collect.FEATURE_CATALOG
        receipt = self.repo / 'data/daily-status/2026-11-24.json'
        self.cli('weekly-before', cutoff=STATUS_CUTOFF, mode='weekly_reconcile')
        self.assertFalse(catalog.exists())
        self.assertFalse(receipt.exists())
        self.save('weekly-before', self.decisions('weekly-before'))
        accepted_catalog = catalog.read_bytes()
        self.assertFalse(receipt.exists())
        for classification in (excluded, positive):
            with self.assertRaisesRegex(ValueError, 'baseline changed'):
                self.save('waiting', classification)
            self.assertEqual(accepted_catalog, catalog.read_bytes())
            self.assertFalse(receipt.exists())
        self.cli('new-daily-same-cutoff', cutoff=STATUS_CUTOFF, extra=['--daily-status'])
        self.assertEqual(self.state('waiting')['cutoff'], self.state('new-daily-same-cutoff')['cutoff'])
        self.save('new-daily-same-cutoff', self.decisions('new-daily-same-cutoff'))
        self.assertEqual(('complete', 0, 0), tuple(read(receipt)[k]
                         for k in ('status', 'collected_feature_count', 'change_count')))

    def test_weekly_distinguishes_old_document_footer_from_real_item_change(self):
        self.configure_small_registry()
        sid = 'firefox-beta'
        url = self.sources[sid]['url']
        evidence = self.repo / 'data/source-items/firefox/firefox-beta.json'
        catalog = self.repo / collect.FEATURE_CATALOG
        self.payloads[url] = self.article('2026-03-01', body='c-release-notes') + '<footer>March.</footer>'
        self.cli('original', [sid], cutoff='2026-04-01T08:00:00+09:00',
                 mode='manual', extra=['--since', '2026-01-01'])
        self.save('original', self.classified('original', sid))
        prior_evidence, prior_catalog = evidence.read_bytes(), catalog.read_bytes()
        first, = read(evidence)
        first_feature, = read(catalog)
        self.payloads[url] = self.payloads[url].replace('March.</footer>', 'November.</footer>')
        self.cli('footer', mode='weekly_reconcile')
        self.assertEqual([], self.candidates('footer', sid))
        self.save('footer', self.decisions('footer'))
        self.assertEqual((prior_evidence, prior_catalog), (evidence.read_bytes(), catalog.read_bytes()))
        self.payloads[url] = self.payloads[url].replace('Tab grouping added.', 'Share tab groups.')
        self.cli('product', cutoff='2026-12-06T10:00:00+09:00', mode='weekly_reconcile')
        item, = self.candidates('product', sid)
        self.assertEqual(first['source_item_id'], item['source_item_id'])
        self.save('product', self.decisions('product'))
        revised, = read(evidence)
        feature, = read(catalog)
        self.assertEqual(first_feature['feature_id'], feature['feature_id'])
        self.assertEqual(first['source_item_id'], revised['source_item_id'])
        self.assertEqual(first['revisions'], revised['revisions'][:-1])
        self.assertEqual(2, len(revised['revisions']))
        self.assertEqual(2, len(feature['source_revision_ids'][first['source_item_id']]))
        self.assertFalse((self.repo / 'data/daily-status').exists())

    def test_modification_conflict_cannot_turn_a_recent_index_edit_into_zero(self):
        sid = 'chrome-releases'
        doc = HOME + '2026/03/updated.html'
        self.payloads[HOME] = self.card(doc, '2026-03-10', '2026-11-15T10:00:00Z')
        self.payloads[doc] = self.article('2026-03-10', changed='2026-03-11')
        self.cli('disagreement', [sid], expected=2)
        self.assertIn('Conflicting index and document modification', str(self.state('disagreement')['source_results'][sid]))
        for index, date in enumerate(('2026-11-15T19:00:00+09:00', '2026-11-15')):
            self.payloads[doc] = self.article('2026-03-10', changed=date)
            name = f'compatible-{index}'
            self.cli(name, [sid])
            row, = self.candidates(name, sid)
            self.assertEqual('timestamp', row['temporal_scope']['precision'])

    def test_modification_days_and_duplicate_page_fields_compare_by_precision(self):
        sid = 'chrome-releases'
        url = HOME + '2026/03/old-post.html'
        self.payloads[HOME] = self.card(url, '2026-03-10', '2026-11-15')
        self.payloads[url] = self.article('2026-03-10', changed='2026-03-13')
        self.cli('opposing-days', [sid], expected=2)
        self.assertIn('Conflicting index and document modification dates',
                      str(self.state('opposing-days')['source_results'][sid]))
        self.assertEqual([], self.candidates('opposing-days', sid))
        self.payloads[url] = self.article('2026-03-10', changed='2026-11-15')
        self.cli('matching-days', [sid])
        self.assertEqual('day', self.candidates('matching-days', sid)[0]['temporal_scope']['precision'])
        self.payloads[url] = ('<meta property="article:modified_time" content="2026-11-15T19:00:00+09:00">'
                              + self.article('2026-03-10', changed='2026-11-15T10:00:00Z'))
        self.cli('equivalent-page-times', [sid])
        row, = self.candidates('equivalent-page-times', sid)
        self.assertEqual('timestamp', row['temporal_scope']['precision'])
        self.payloads[url] = self.payloads[url].replace('19:00:00+09:00', '19:00:01+09:00')
        self.cli('opposing-page-times', [sid], expected=2)
        self.assertIn('Conflicting document modification dates',
                      str(self.state('opposing-page-times')['source_results'][sid]))

    def test_rolling_page_future_revision_blocks_certification_but_does_not_redate_sections(self):
        sid = 'edge-stable'
        url = self.sources[sid]['url']
        body = ('<div class="content"><h2>March 10, 2026</h2><p id="old">Old capability.</p>'
                '<h2>November 15, 2026</h2><p id="recent">Recent capability.</p>'
                '<time itemprop="dateModified" datetime="2026-11-26T00:00:00Z"></time></div>')
        def document(date):
            return f'<html><head><meta property="article:modified_time" content="{date}"></head><body>{body}</body></html>'
        self.payloads[url] = document('2026-11-24T08:00:01+09:00')
        self.cli('rolling-future', [sid], expected=2)
        self.assertEqual([], self.candidates('rolling-future', sid))
        self.assertIn('rolling document revision after cutoff', str(self.state('rolling-future')['source_results'][sid]))
        self.payloads[url] = document('2026-11-23T19:00:00+09:00')
        self.cli('rolling-current', [sid])
        row, = self.candidates('rolling-current', sid)
        self.assertEqual(('recent', '2026-11-15', 'publication'),
                         (row['item_key'], row['temporal_scope']['evidence_date'], row['temporal_scope']['basis']))

    def test_public_enterprise_rows_share_api_window_and_require_the_current_feature(self):
        sid = 'chrome-enterprise'
        archive = 'https://support.google.com/chrome/a/answer/10314655?hl=en'
        api = 'https://release-notes-787862449254.us-central1.run.app'
        versions, details = api + '/versions', api + '/features?version=150&lang=en'
        self.payloads[archive] = ('<a href="#149">April 1, 2026</a><a class="zippy" name="149">Version</a>'
                                  '<div><p>Old release.</p></div>')
        self.payloads[versions] = {'versions': [{'value': '150'}]}
        def note(ident, name, day, **flags):
            row = dict(id=ident, name=name, summary=name + ' on Windows.', is_releasenotes_publish_ready=True,
                       is_releasenotes_content_reviewed=True, created={'when': day}, updated={'when': day})
            return dict(row, **flags)
        entries = [note(110, 'Save tabs', '2026-11-24'), note(111, 'Share tabs', '2026-11-29'),
                   dict(note(109, 'Mute tabs', '2026-04-01'), summary='Mute tabs on Windows in stable 150 are enabled.'), note(108, 'Other tabs', '2026-04-01'), note(444, 'Hidden', '2026-11-24', confidential=True)]
        self.payloads[details] = dict(total_count=len(entries), features=entries)
        self.configure_small_registry()
        registry = read(self.registry)
        for source in registry['sources']:
            if source['browser'] == self.sources[sid]['browser']:
                source['enabled'] = source['source_id'] == sid
        self.registry.write_bytes(encoded(registry))
        cutoff = '2026-11-26T07:00:00+09:00'
        self.cli('mixed-api', cutoff=cutoff, extra=['--daily-status'])
        row, = self.candidates('mixed-api', sid)
        self.assertEqual('110', row['item_key'])
        self.assertEqual([archive, versions, details], [u for u in self.calls if u == archive or u.startswith(api)])
        window = read(self.folder / 'runs/mixed-api/work/windows/chrome-enterprise.json')
        self.assertNotIn('Hidden', str(window))
        self.assertNotIn('444', str(window))
        request = dict(browser='chrome', source_id=sid, canonical_key='save-tabs', title='Save tabs', url=details)
        self.item('mixed-api', request)
        for browser in browser_status.registry_facts(self.repo, 'daily')[2]:
            if browser != 'chrome':
                self.publish_browser('mixed-api', browser, self.browser_choices('mixed-api', browser, select=False))
        for fragment in ('#111', '#109', '#:~:text=Share%20tabs'):
            with self.subTest(fragment=fragment), self.assertRaisesRegex(ValueError, 'window'):
                self.item('mixed-api', dict(request, url=details + fragment))
        with self.assertRaisesRegex(ValueError, 'window'):
            self.publish_browser('mixed-api', 'chrome', self.browser_choices('mixed-api', 'chrome', select=False))
        position = self.repo / 'data/daily-status/2026-11-26.json'
        self.assertEqual(('incomplete', None), (read(position)['status'], read(position)['change_count']))
        run_daily.commit_candidate(self.repo)
        self.cli('fresh-api', cutoff=cutoff, extra=['--daily-status'])
        self.cli('fresh-api', cutoff=cutoff, extra=['--daily-status', '--resume'])
        choices = self.browser_choices('fresh-api', 'chrome')
        with self.assertRaisesRegex(ValueError, 'window'):
            self.publish_browser('fresh-api', 'chrome', choices)
        choices['decisions'][0].update(canonical_key='save-tabs', title='Save tabs')
        self.publish_browser('fresh-api', 'chrome', choices)
        self.assertEqual(('complete', 1, 1), tuple(read(position)[k] for k in ('status', 'collected_feature_count', 'change_count')))

        alternate = api + '/features?lang=en&version=150'
        self.item('manual', dict(browser='chrome', source_id=sid, canonical_key='mute-tabs', title='Mute tabs',
                                 url=alternate), standalone=True)
        self.item('manual', dict(browser='chrome', source_id=sid, canonical_key='wrong-row', title='Other tabs',
                                 url=details + '#110'), standalone=True)
        second_cutoff = '2026-11-27T07:00:00+09:00'
        self.cli('old-api', cutoff=second_cutoff, extra=['--daily-status'])
        work = self.folder / 'runs/old-api/work'
        jobs = read(work / 'enrichment/chrome-enterprise.json')
        other, = [j for j in jobs if j['url'] == details + '#110']
        self.assertNotIn('candidate', other)
        old, = [j for j in jobs if j['url'] == alternate]
        selected = old['candidate']
        self.item('old-api', dict(browser='chrome', source_id=sid, feature_id=old['feature_id'],
                                  source_item_id=selected['source_item_id'], revision_id=selected['revisions'][-1]['revision_id'],
                                  facts=dict(platform=['Windows'], channel='stable', version='150', rollout_status='enabled')))
        run_daily.commit_candidate(self.repo)
        self.cli('old-api-fresh', cutoff=second_cutoff, extra=['--daily-status'])
        for browser in browser_status.registry_facts(self.repo, 'daily')[2]:
            self.publish_browser('old-api-fresh', browser, self.browser_choices('old-api-fresh', browser, select=False))
        day = read(self.repo / 'data/daily-status/2026-11-27.json')
        self.assertEqual(('complete', 1, 0), tuple(day[k] for k in ('status', 'collected_feature_count', 'change_count')))

    def test_weekly_markdown_sections_share_the_registered_document_window(self):
        sid = 'brave-android-changelog'
        url = self.sources[sid]['url']
        self.payloads[url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')] = (
            '# November 24, 2026\n- Save tabs.\n# December 2, 2026\n- Share tabs.\n')
        self.configure_small_registry()
        registry = read(self.registry)
        for source in registry['sources']:
            if source['browser'] == self.sources[sid]['browser']:
                source['enabled'] = source['source_id'] == sid
        self.registry.write_bytes(encoded(registry))
        cutoff = '2026-11-29T10:00:00+09:00'
        self.cli('brave-window', cutoff=cutoff, mode='weekly_reconcile')
        row, = self.candidates('brave-window', sid)
        self.assertEqual('Save tabs.', row['evidence']['excerpt'])
        req = dict(browser='brave', source_id=sid, canonical_key='share', title='Share tabs', url=url)
        self.item('brave-window', req)
        with self.assertRaisesRegex(ValueError, 'window'):
            self.publish_browser('brave-window', 'brave', self.browser_choices('brave-window', 'brave', select=False))

    def test_enterprise_archive_count_and_independent_current_api(self):
        sid = 'chrome-enterprise'
        archive = 'https://support.google.com/chrome/a/answer/10314655?hl=en'
        api = 'https://release-notes-787862449254.us-central1.run.app'
        versions, details = api + '/versions', api + '/features?version=101&lang=en'
        self.payloads[versions] = {'versions': [{'value': '101'}]}
        self.payloads[details] = {'total_count': 1, 'features': [
            dict(id=12345, name='Tabs', summary='Group tabs.', is_releasenotes_publish_ready=True,
                 is_releasenotes_content_reviewed=True, created={'when': '2026-11-08'},
                 updated={'when': '2026-11-18'})]}
        panel = ('<a href="#101">November 10, 2026</a><a class="zippy" name="101">Version</a>'
                 '<div><p id="archive">Organize workspaces.</p></div>')
        for name, date, status, panels in [('normal', '2026-11-19', 0, 1), ('late', '2026-11-25', 2, 0)]:
            self.calls.clear()
            self.payloads[archive] = (f'<html><head><meta property="article:modified_time" content="{date}">'
                                      f'</head><body>{panel}</body></html>')
            self.cli(name, [sid], expected=status)
            self.assertEqual([archive, versions, details], self.calls)
            result = read(self.folder / 'runs' / name / 'work/browser/chrome-enterprise.json')
            self.assertEqual(panels, result['enterprise_archive_panels'])
            self.assertTrue(result['pagination_exhausted'])
            rows = self.candidates(name, sid)
            self.assertEqual({'12345', 'release:101:archive'} if panels else {'12345'},
                             {row['item_key'] for row in rows})
            self.assertEqual('complete' if panels else 'partial', result['status'])
            if not panels:
                self.assertIn('rolling document revision after cutoff', str(result['errors']))
