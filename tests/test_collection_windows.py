"""Exercise scheduled collection, bounded discovery, recovery and offline saving without a network."""
import contextlib
from io import StringIO
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch

from pipeline import collect
from pipeline.collectors.browser import Response
from pipeline.run_daily import encoded, git, read, run_lock

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = '2026-11-24T08:00:00+09:00'
UTC = '2026-11-23T23:00:00Z'
START = '2026-10-25T08:00:00+09:00'
OBSERVED = '2026-11-24T09:00:00+09:00'
HOME = 'https://chromereleases.googleblog.com/'


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
        self.cli('ordered', [sid])
        self.assertEqual([home, older, new], self.calls)
        self.assertEqual(1, len(self.candidates('ordered', sid)))
        self.payloads[new] = self.article('2026-11-09', changed='2026-11-24T08:00:01+09:00', body='entry-content')
        self.cli('future', [sid, 'firefox-ios'], expected=2)
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

    def test_racing_saves_in_three_modes_keep_one_revision_and_one_daily_status(self):
        self.configure_small_registry()
        with run_lock(self.repo), self.assertRaisesRegex(RuntimeError, 'lock'):
            self.cli('week', mode='weekly_reconcile')
        self.cli('week', mode='weekly_reconcile')
        self.observed_at = '2026-11-24T09:01:00+09:00'
        self.cli('manual', mode='manual')
        self.observed_at = '2026-11-24T09:02:00+09:00'
        self.cli('day', extra=['--daily-status'])
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
        self.cli('stale', extra=['--daily-status'])
        self.cli('week', mode='weekly_reconcile')
        self.save('week', self.decisions('week'))
        self.assertFalse((self.repo / 'data/daily-status').exists())
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            self.save('stale', self.decisions('stale'))
        self.cli('manual', mode='manual')
        self.save('manual', [])
        self.cli('day', extra=['--daily-status'])
        self.save('day', self.decisions('day'))
        status = self.repo / 'data/daily-status/2026-11-24.json'
        self.assertEqual((0, 0), (read(status)['collected_feature_count'], read(status)['change_count']))
        self.cli('after-gap', cutoff='2027-01-04T08:00:00+09:00', extra=['--daily-status'])
        self.assertEqual('2026-12-05T08:00:00+09:00', self.state('after-gap')['start'])
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
        self.cli('pages', [sid], expected=2)
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
        self.cli('v3', [sid], extra=self.brave_bundle([recent, ancient], 3))
        result, = self.candidates('v3', sid)
        self.assertEqual(recent['updated_at'], result['temporal_scope']['evidence_date'])
        self.assertEqual(2, len(self.calls))
        old = [{key: val for key, val in r.items() if key != 'updated_at'} for r in [recent, ancient]]
        self.calls.clear()
        self.cli('v2', [sid], extra=self.brave_bundle(old, 2), expected=2)
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
        self.cli('bounded', [sid], extra=metadata, expected=2)
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
            self.cli('missing', [sid], extra=self.brave_bundle([entry], 3), expected=2)
        self.assertIn('absent from frozen metadata: 1001', str(self.state('missing')['source_results'][sid]))

    def test_daily_stale_positive_and_excluded_decisions_refuse_changed_weekly_catalog(self):
        self.configure_small_registry()
        self.cli('waiting', extra=['--daily-status'])
        positive = self.decisions('waiting')
        excluded = dict(decisions=[], dispositions=[dict(item, disposition='excluded')
                                                    for item in positive['dispositions']])
        catalog = self.repo / collect.FEATURE_CATALOG
        receipt = self.repo / 'data/daily-status/2026-11-24.json'
        self.cli('weekly-before', mode='weekly_reconcile')
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
        self.cli('new-daily-same-cutoff', extra=['--daily-status'])
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
        self.cli('product', mode='weekly_reconcile')
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
