import contextlib
import hashlib
import io
from datetime import datetime
from html import escape
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from zipfile import ZipFile

from pipeline.collectors.browser import Response
from pipeline.collectors.browser.firefox_ios import NOTES_API, SHIPPING, detail_url
from pipeline.collectors.browser.firefox_ios_store import APP_STORE_ID, APP_STORE_URL, MOZILLA_DEVELOPER
from pipeline.collectors.browser.firefox_ios_schedule import meeting_requests
from pipeline.official_reference import accepts_url


ROOT = Path(__file__).resolve().parents[1]
SHA, TREE = 'a' * 40, 'b' * 40
CUTOFF = '2026-11-25T07:00:00+09:00'
COMMIT = f'{NOTES_API}/commits?sha=master&until=2026-11-24T22%3A00%3A00Z&per_page=1'
INDEX = f'{NOTES_API}/git/trees/{TREE}?recursive=1'
ARCHIVE = f'https://codeload.github.com/mozilla/release-notes/zip/{SHA}'
SHIPS = f'{SHIPPING}?per_page=100&page=1'
NEXT = f'{SHIPPING}?per_page=100&page=2'
DUO = 'Improved support for iPhone Duo.'


def note(ident, text, modified='2026-11-01T12:00:00Z'):
    return dict(id=ident, note=text, tag='New', is_public=True, modified=modified)


def release(v, day, notes):
    return dict(version=v, slug=f'firefox-for-ios-{v}-release', release_date=day,
                is_public=True, product='Firefox for iOS', channel='Release',
                notes=notes, modified='2026-11-01T12:00:00Z')


def ship(ident, tag, stamp='2026-11-01T12:00:00Z'):
    return dict(id=ident, draft=False, prerelease=False, tag_name=tag, published_at=stamp)


def html(row):
    version = row['version']
    items = ''.join(f'<li class="release-note" id="note-{n["id"]}">{n["note"]}</li>' for n in row['notes'])
    content = '<h3>New</h3><ul>' + items + '</ul>' if items else ''
    return (f'<html lang="en-US"><head><link rel="canonical" href="{detail_url(version)}"></head>'
            f'<span class="c-release-version">{version}</span><span class="c-release-product">Firefox for iOS Release</span>'
            f'<p class="c-release-date">{row["release_date"]}</p><section class="c-release-notes">{content}</section></html>')


def store_html(*rows):
    structured = []
    visible = []
    for version, published, text in rows:
        stamp = datetime.fromisoformat(published)
        structured.append({'$kind': 'TitledParagraph', 'primarySubtitle': version,
                           'secondarySubtitle': stamp.strftime('%a %b %d %Y %H:%M:%S GMT+0000')
                           + ' (Coordinated Universal Time)', 'text': text})
        visible.append(f'<li><p>{escape(text)}</p><div class="metadata"><span>{version}</span>'
                       f'<time datetime="{stamp.date()}">printed date</time></div></li>')
    shelf = {'seeAllAction': {'pageData': {'shelves': [{'items': structured}]}}}
    product = {'intent': {'$kind': 'ProductPageIntent', 'id': APP_STORE_ID, 'storefront': 'us', 'language': 'en-US'},
               'data': {'shelfMapping': {'mostRecentVersion': shelf}}}
    author = json.dumps({'author': {'name': 'Mozilla', 'url': MOZILLA_DEVELOPER}})
    data = json.dumps({'data': [product]})
    return (f'<html lang="en-US"><head><link rel="canonical" href="{APP_STORE_URL}">'
            f'<script id="software-application">{author}</script>'
            f'<script id="serialized-server-data">{data}</script></head>'
            f'<div data-testid="content-modal"><h2>Version History</h2><ul>{"".join(visible)}</ul></div></html>')


class FirefoxIosTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.repo = self.root / 'repo'
        shutil.copytree(ROOT / 'config', self.repo / 'config')
        self.legacy_file = self.repo / 'data/source-items/firefox/firefox-ios.json'
        self.legacy_file.parent.mkdir(parents=True)
        shutil.copyfile(ROOT / self.legacy_file.relative_to(self.repo), self.legacy_file)
        self.rows = {'160.0': release('160.0', '2026-11-10', [note(792483, DUO)]),
                     '161.0': release('161.0', '2026-11-23', [])}
        self.pages = {COMMIT: [dict(sha=SHA, commit={'tree': dict(sha=TREE), 'committer': dict(date='2026-11-24T21:59:00Z')})],
                      SHIPS: [ship(1, 'firefox-v160.0'), ship(2, 'v160'), ship(3, 'firefox-v161.0')], NEXT: []}
        self.calls = []
        self.prepare()

    def prepare(self):
        stream = io.BytesIO()
        tree = []
        with ZipFile(stream, 'w') as zipped:
            zipped.comment = SHA.encode()
            for v, row in self.rows.items():
                raw = json.dumps(row).encode()
                path = f'releases/firefox-for-ios-{v}-release.json'
                zipped.writestr(f'release-notes-{SHA}/{path}', raw)
                tree.append(dict(path=path, type='blob', mode='100644',
                                 sha=hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()))
                if isinstance(row.get('notes'), list):
                    self.pages[detail_url(v)] = html(row)
        self.pages[ARCHIVE] = stream.getvalue()
        self.pages[INDEX] = dict(sha=TREE, truncated=False, tree=tree)

    def request(self, url):
        self.calls.append(url)
        value = self.pages[url]
        if isinstance(value, (Exception, Response)):
            if isinstance(value, Exception):
                raise value
            return value
        if not isinstance(value, (str, bytes)):
            value = json.dumps(value)
        return Response(url, value.encode() if isinstance(value, str) else value)

    def cli(self, name, expected=0, mode='daily', resume=False, cutoff=CUTOFF):
        args = ['pipeline.run_daily', '--repository', str(self.repo), '--private-dir', str(self.root / 'runs'),
                '--run-id', name, '--source', 'firefox-ios', '--cutoff', cutoff, '--mode', mode]
        if mode == 'daily':
            args.append('--daily-status')
        if resume:
            args.append('--resume')
        with patch('sys.argv', args), patch('pipeline.collectors.browser.collector.HTTPTransport', return_value=self.request):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as exit_status:
                runpy.run_path(str(ROOT / 'pipeline/run_daily.py'), run_name='__main__')
        work = self.root / 'runs' / name / 'work'
        result = json.loads((work / 'browser/firefox-ios.json').read_text())
        self.assertEqual(expected, exit_status.exception.code, result['errors'])
        return result, json.loads((work / 'candidates/firefox-ios.json').read_text())

    def test_explicit_empty_alias_convergence_and_existing_revision(self):
        before = self.legacy_file.read_bytes()
        old, = json.loads(before)
        self.assertEqual('src-8edcb56ab979b6aeb74534a8', old['source_item_id'])
        self.assertEqual('ac695e5678b78a8f73e806a59a24fbf8e2b45a0be827980848e598859207f81e', old['item_content_sha256'])
        state, rows = self.cli('two')
        self.assertEqual(([], 1, 0, 'complete'), (rows, state['duplicate'], state['unparsed'], state['status']))
        self.assertEqual(['161.0'], state['firefox_ios_inventory']['empty_versions'])
        self.assertEqual([COMMIT, INDEX, ARCHIVE, SHIPS, NEXT, detail_url('160.0'), detail_url('161.0')], self.calls)
        self.assertEqual(before, self.legacy_file.read_bytes())
        self.rows['160.0']['notes'][0]['note'] = 'Improved tablet layout.'
        self.prepare()
        _, changed = self.cli('changed')
        row, = changed
        self.assertEqual(old['source_item_id'], row['source_item_id'])
        self.assertEqual(old['revisions'], row['revisions'][:-1])
        self.assertNotEqual(old['item_content_sha256'], row['item_content_sha256'])

    def test_missing_shipping_records_stay_partial_with_verifiable_empty(self):
        self.pages[SHIPS].extend([ship(4, 'firefox-v159.1'), ship(5, 'firefox-v99.1', '2025-01-01T00:00:00Z'),
                                  dict(ship(6, 'firefox-v161.1'), draft=True), ship(7, 'focus/klar-v159.1')])
        state, rows = self.cli('missing', expected=2)
        self.assertEqual([], rows)
        inventory = state['firefox_ios_inventory']
        self.assertEqual((['161.0'], ['159.1'], ['99.1']), (inventory['empty_versions'],
                         inventory['missing_shipping_versions'], inventory['older_undated_shipping_versions']))
        self.assertEqual('partial', state['status'])

    def test_store_fallback_matches_each_version_uses_store_time_and_keeps_primary(self):
        self.pages[SHIPS] += [
            ship(4, 'firefox-v159.1', '2026-11-02T03:00:00Z'),
            ship(5, 'firefox-v161.1', '2026-11-23T12:00:00Z'),
            ship(6, 'firefox-v99.1', '2025-01-01T00:00:00Z'),
            ship(7, 'firefox-v159.2', '2026-11-03T12:00:00Z'),
        ]
        self.pages[APP_STORE_URL] = store_html(
            ('159.1', '2026-11-05T16:20:00+00:00', 'Generic maintenance.'),
            ('159.2', '2026-11-06T16:20:00+00:00', 'Added a new view for tabs.'),
            ('160.0', '2026-11-10T16:20:00+00:00', 'Do not substitute an available Mozilla note.'),
            ('161.1', '2026-11-24T22:00:01+00:00', 'Not yet published at cutoff.'),
            ('99.1', '2025-01-03T16:20:00+00:00', 'Old notes.'),
            ('88.2', '2026-11-24T19:00:00+00:00', 'No matching Mozilla shipping version.'),
        )
        state, rows = self.cli('app-store')
        expected = {'app-store-159.1': 'Generic maintenance.', 'app-store-159.2': 'Added a new view for tabs.'}
        self.assertEqual(expected, {r['item_key']: r['evidence']['excerpt'] for r in rows})
        self.assertEqual(['159.1', '161.1', '99.1', '159.2'], state['firefox_ios_inventory']['app_store_versions'])
        self.assertEqual(['161.0'], state['firefox_ios_inventory']['empty_versions'])
        self.assertEqual(1, self.calls.count(APP_STORE_URL))
        windows = json.loads((self.root / 'runs/app-store/work/windows/firefox-ios.json').read_text())
        self.assertEqual('after_cutoff', windows[APP_STORE_URL + '#app-store-161.1'])
        self.assertEqual('before_period', windows[APP_STORE_URL + '#app-store-99.1'])
        self.assertEqual(1, state['duplicate'])
        for row in rows:
            self.assertEqual(APP_STORE_URL, row['evidence']['url'])
            self.assertEqual('timestamp', row['temporal_scope']['precision'])
        later, later_rows = self.cli('app-store-weekly', mode='weekly_reconcile')
        self.assertNotIn('161.1', {r['version'] for r in later_rows})
        self.assertEqual('complete', later['status'])
        source = {'source_id': 'firefox-ios', 'url': SHIPPING}
        self.assertTrue(accepts_url(source, APP_STORE_URL))
        for wrong in (APP_STORE_URL + '?at=ad', APP_STORE_URL + '#made-up',
                      APP_STORE_URL.replace('989804926', '989804927'), APP_STORE_URL.replace('/us/', '/de/')):
            self.assertFalse(accepts_url(source, wrong))

    def test_store_can_precede_github_without_changing_the_daily_window(self):
        self.pages[SHIPS] += [ship(4, 'firefox-v152.4', '2026-07-12T23:48:12Z'),
                              ship(5, 'firefox-v159.1', '2026-11-05T16:21:00Z')]
        self.pages[APP_STORE_URL] = store_html(
            ('152.4', '2026-07-12T08:01:43+00:00', 'Generic maintenance.'),
            ('159.1', '2026-11-05T16:20:00+00:00', 'New tab feature.'))
        state, rows = self.cli('independent-clocks')
        self.assertEqual(['152.4', '159.1'], state['firefox_ios_inventory']['app_store_versions'])
        self.assertEqual([], state['firefox_ios_inventory']['older_undated_shipping_versions'])
        self.assertEqual(['159.1'], [row['version'] for row in rows])

    def test_daily_backlog_survives_and_new_runs_recover_late_official_notes(self):
        self.pages[SHIPS].append(ship(4, 'firefox-v99.1', '2025-01-01T00:00:00Z'))
        self.pages[APP_STORE_URL] = HTTPError(APP_STORE_URL, 404, 'Not found', {}, None)
        state, _ = self.cli('old-backlog')
        self.assertEqual(['99.1'], state['firefox_ios_inventory']['older_undated_shipping_versions'])
        self.assertIn('404', state['firefox_ios_inventory']['app_store_error'])
        original = (self.root / 'runs/old-backlog/work/browser/firefox-ios.json').read_bytes()
        self.cli('old-backlog-weekly', mode='weekly_reconcile', expected=2)
        self.cli('old-backlog-manual', mode='manual', expected=2)
        # The shipping date stays old. A newly published official Store row is eligible.
        self.pages[APP_STORE_URL] = store_html(('99.1', '2026-11-20T12:00:00+00:00', 'New official note.'))
        state, rows = self.cli('late-store-evidence')
        self.assertEqual(['99.1'], state['firefox_ios_inventory']['app_store_versions'])
        self.assertEqual(['99.1'], [row['version'] for row in rows])
        self.assertEqual(original, (self.root / 'runs/old-backlog/work/browser/firefox-ios.json').read_bytes())

    def test_backlog_does_not_hide_a_current_missing_release_or_store_error(self):
        self.pages[SHIPS] += [ship(4, 'firefox-v99.1', '2025-01-01T00:00:00Z'),
                              ship(5, 'firefox-v161.1', '2026-11-23T12:00:00Z')]
        self.pages[APP_STORE_URL] = HTTPError(APP_STORE_URL, 429, 'Rate limited', {}, None)
        state, _ = self.cli('current-gap', expected=2)
        inventory = state['firefox_ios_inventory']
        self.assertEqual(['99.1'], inventory['older_undated_shipping_versions'])
        self.assertEqual(['161.1'], inventory['missing_shipping_versions'])
        self.assertIn('429', str(state['errors']))

    def schedule(self, *, cutoff=CUTOFF, text=None, published='2026-11-19T15:39:57Z'):
        requests = list(meeting_requests(cutoff))
        text = text or '** Firefox iOS 161.1 scheduled to start phased rollout at 03:00 UTC on 2026-11-26'
        title, url = requests[0]
        revision = dict(revid=12345, timestamp=published, slots={'main': {
            'contentmodel': 'wikitext', 'contentformat': 'text/x-wiki',
            'content': '== Schedule Update ==\n' + text + '\n== QA ==\n* Firefox RC 161.1 build 2 GREEN'}})
        self.pages[url] = dict(batchcomplete=True, query={'pages': [dict(pageid=123, ns=0, title=title, revisions=[revision])]})
        old_title, old_url = requests[1]
        self.pages[old_url] = dict(batchcomplete=True, query={'pages': [dict(ns=0, title=old_title, missing=True)]})
        return url

    def scheduled_fixture(self):
        self.pages[SHIPS].append(ship(4, 'firefox-v161.1', '2026-11-23T12:00:00Z'))
        self.pages[APP_STORE_URL] = store_html(('161.0', '2026-11-23T02:08:23+00:00', 'Maintenance.'))
        return self.schedule()

    def test_pinned_future_rollout_is_scheduled_not_an_empty_release(self):
        url = self.scheduled_fixture()
        state, rows = self.cli('scheduled')
        history = state['firefox_ios_inventory']
        proof = history['scheduled_versions']['161.1']
        self.assertEqual('scheduled', proof['state'])
        self.assertEqual('2026-11-26T03:00:00+00:00', proof['scheduled_at'])
        self.assertEqual(proof['scheduled_at'], proof['recheck_at'])
        self.assertEqual(12345, proof['revision_id'])
        self.assertEqual([], history['missing_shipping_versions'])
        self.assertNotIn('161.1', history['empty_versions'] + history['app_store_versions'])
        self.assertEqual([], rows)
        self.assertEqual(1, self.calls.count(url))
        self.cli('scheduled-weekly', mode='weekly_reconcile')

    def test_schedule_expires_and_fresh_store_evidence_recovers_without_rewriting_old_run(self):
        self.scheduled_fixture()
        self.cli('before-rollout')
        original = (self.root / 'runs/before-rollout/work/browser/firefox-ios.json').read_bytes()
        cutoff = '2026-11-27T07:00:00+09:00'
        self.pages[COMMIT.replace('11-24', '11-26')] = self.pages[COMMIT]
        self.schedule(cutoff=cutoff, published='2026-11-26T15:00:00Z')
        state, _ = self.cli('after-rollout', cutoff=cutoff, expected=2)
        self.assertEqual(['161.1'], state['firefox_ios_inventory']['missing_shipping_versions'])
        self.assertEqual({}, state['firefox_ios_inventory']['scheduled_versions'])
        self.pages[APP_STORE_URL] = store_html(('161.1', '2026-11-26T03:08:00+00:00', 'Verified maintenance.'))
        _, rows = self.cli('store-published', cutoff=cutoff)
        self.assertEqual(['161.1'], [row['version'] for row in rows])
        self.assertEqual(original, (self.root / 'runs/before-rollout/work/browser/firefox-ios.json').read_bytes())

    def test_conflicting_unrecognized_or_expired_schedule_never_defers(self):
        self.scheduled_fixture()
        good = '** Firefox iOS 161.1 scheduled to start phased rollout at 03:00 UTC on 2026-11-26'
        for name, text in (
                ('expired', good.replace('2026-11-26', '2026-11-24')),
                ('at-cutoff', good.replace('03:00 UTC on 2026-11-26', '22:00 UTC on 2026-11-24')),
                ('too-distant', good.replace('2026-11-26', '2026-12-30')),
                ('build-only', '** Firefox iOS 161.1 branches and gtb tomorrow'),
                ('conflicting', good + '\n' + good.replace('03:00', '04:00')),
                ('released', good + '\n** Firefox iOS 161.1 live @ 100% rollout'),
                ('ambiguous-cancellation', good + '\n** 161.1 rollout cancelled'),
                ('other-product', good.replace('Firefox iOS', 'Focus iOS')),
                ('other-version', good.replace('161.1', '161.10')),
                ('commented', '<!--\n' + good + '\n-->'),
                ('no-zone', good.replace(' UTC', ''))):
            with self.subTest(name=name):
                self.schedule(text=text)
                state, _ = self.cli(name, expected=2)
                self.assertEqual({}, state['firefox_ios_inventory']['scheduled_versions'])

    def test_schedule_requires_pinned_identity_time_and_readable_store(self):
        url = self.scheduled_fixture()
        valid = json.dumps(self.pages[url])
        for name, change in (
                ('later-revision', lambda d: d['query']['pages'][0]['revisions'][0].update(timestamp='2026-11-25T00:00:00Z')),
                ('wrong-title', lambda d: d['query']['pages'][0].update(title='Other page')),
                ('hidden-content', lambda d: d['query']['pages'][0]['revisions'][0]['slots']['main'].pop('content')),
                ('unfinished', lambda d: d.update(batchcomplete=False))):
            d = json.loads(valid)
            change(d)
            with self.subTest(name=name), patch.dict(self.pages, {url: d}):
                state, _ = self.cli(name, expected=2)
                self.assertIn('161.1', state['firefox_ios_inventory']['schedule_errors'])
        with patch.dict(self.pages, {url: Response('https://example.org/', valid.encode())}):
            self.cli('schedule-redirect', expected=2)
        with patch.dict(self.pages, {APP_STORE_URL: OSError('Store unavailable')}):
            self.calls.clear()
            self.cli('no-store-proof', expected=2)
            self.assertNotIn(url, self.calls)

    def test_actual_store_publication_and_primary_notes_take_priority_over_schedule(self):
        url = self.scheduled_fixture()
        self.pages[APP_STORE_URL] = store_html(('161.1', '2026-11-24T02:00:00+00:00', 'Published early.'))
        _, rows = self.cli('store-over-plan')
        self.assertEqual(['161.1'], [row['version'] for row in rows])
        self.assertNotIn(url, self.calls)
        self.rows['161.1'] = release('161.1', '2026-11-24', [note(777, 'Official release feature.')])
        self.prepare()
        self.calls.clear()
        _, rows = self.cli('primary-over-plan')
        self.assertEqual(['note-777'], [row['item_key'] for row in rows])
        self.assertNotIn(url, self.calls)

    def test_newer_store_version_or_newer_cancellation_blocks_old_schedule(self):
        url = self.scheduled_fixture()
        original = self.pages[APP_STORE_URL]
        self.pages[APP_STORE_URL] = store_html(('162.0', '2026-11-24T02:00:00+00:00', 'Newer publication.'))
        self.cli('newer-store', expected=2)
        self.assertNotIn(url, self.calls)
        self.pages[APP_STORE_URL] = original
        old_title, old_url = list(meeting_requests(CUTOFF))[1]
        old = json.loads(json.dumps(self.pages[url]))
        old['query']['pages'][0]['title'] = old_title
        old['query']['pages'][0]['revisions'][0]['timestamp'] = '2026-11-12T15:00:00Z'
        self.pages[old_url] = old
        self.pages[url]['query']['pages'][0]['revisions'][0]['slots']['main']['content'] = (
            '== Schedule Update ==\n** Firefox iOS 161.1 rollout cancelled\n== QA ==\n')
        self.calls.clear()
        self.cli('cancelled', expected=2)
        self.assertNotIn(old_url, self.calls)

    def test_schedule_cache_tamper_cannot_preserve_a_deferred_version_on_retry(self):
        self.scheduled_fixture()
        self.pages[SHIPS].append(ship(5, 'firefox-v161.2', '2026-11-23T13:00:00Z'))
        state, _ = self.cli('schedule-cache', expected=2)
        proof = state['firefox_ios_inventory']['scheduled_versions']['161.1']
        cached = self.root / 'runs/schedule-cache/work/browser/cache' / proof['response_sha256']
        cached.write_bytes(b'changed schedule')
        state, _ = self.cli('schedule-cache', expected=2, resume=True)
        self.assertEqual({}, state['firefox_ios_inventory']['scheduled_versions'])
        self.assertIn('checksum', state['firefox_ios_inventory']['schedule_errors']['161.1'])

    def test_previous_meeting_can_supply_schedule_when_latest_has_no_revision_at_cutoff(self):
        url = self.scheduled_fixture()
        old_title, old_url = list(meeting_requests(CUTOFF))[1]
        old = json.loads(json.dumps(self.pages[url]))
        old['query']['pages'][0]['title'] = old_title
        old['query']['pages'][0]['revisions'][0]['timestamp'] = '2026-11-12T15:00:00Z'
        self.pages[old_url] = old
        self.pages[url]['query']['pages'][0]['revisions'] = []
        state, _ = self.cli('previous-meeting')
        self.assertIn('161.1', state['firefox_ios_inventory']['scheduled_versions'])
        self.assertIn(old_url, self.calls)

    def test_store_missing_redirect_disagreement_rate_limit_and_wrong_publisher_stay_partial(self):
        self.pages[SHIPS].append(ship(4, 'firefox-v159.1'))
        exact = store_html(('159.1', '2026-11-05T16:20:00+00:00', 'Feature A.'))
        for label, store in (
                ('app-id', exact.replace(f'"id": "{APP_STORE_ID}"', '"id": "111"')),
                ('locale', exact.replace('lang="en-US"', 'lang="de"')),
                ('date', exact.replace('datetime="2026-11-05"', 'datetime="2026-11-06"')),
                ('other-version', exact.replace('159.1', '159.2')),
                ('duplicate', store_html(*[('159.1', '2026-11-05T16:20:00+00:00', 'Feature A.')] * 2)),
                ('publisher', exact.replace(MOZILLA_DEVELOPER, 'https://apps.apple.com/us/developer/other/id1')),
                ('wrong-record', exact.replace('<p>Feature A.</p>', '<p>Unrelated text</p>')),
                ('truncated', exact.removesuffix('</html>')),
                ('redirect', Response(APP_STORE_URL.replace('/us/', '/de/'), exact.encode())),
                ('rate-limit', HTTPError(APP_STORE_URL, 429, 'Rate limited', {}, None))):
            with self.subTest(label=label), patch.dict(self.pages, {APP_STORE_URL: store}):
                state, rows = self.cli(label, expected=2)
                self.assertEqual(['159.1'], state['firefox_ios_inventory']['missing_shipping_versions'])
                self.assertEqual('partial', state['status'])
                self.assertEqual([], rows)
                self.assertEqual([], state['firefox_ios_inventory']['app_store_versions'])

    def test_only_unavailable_primary_page_can_use_matching_app_store_note(self):
        url = detail_url('160.0')
        complete = store_html(('160.0', '2026-11-10T16:20:00+00:00', DUO))
        divergent = complete.replace(DUO, 'Different product change.')
        not_found = HTTPError(url, 404, 'Not found', {}, None)
        for label, detail, store, expected in (
                ('app-404', not_found, complete, 0),
                ('app-404-different', not_found, divergent, 2),
                ('app-404-containing', not_found, complete.replace(DUO, 'Wrong: ' + DUO), 2),
                ('app-403', HTTPError(url, 403, 'Denied', {}, None), complete, 2),
                ('app-wrong-data', html(self.rows['160.0']).replace(DUO, 'Changed.'), complete, 2)):
            with self.subTest(label=label), patch.dict(self.pages, {APP_STORE_URL: store, url: detail}):
                self.calls.clear()
                state, rows = self.cli(label, expected=expected)
                self.assertEqual(expected == 0, bool(rows))
                self.assertEqual(label.startswith('app-404'), APP_STORE_URL in self.calls)
                self.assertEqual(['160.0'] if expected == 0 else [], state['firefox_ios_inventory']['app_store_versions'])

    def test_shared_store_url_cannot_supply_another_versions_feature_facts(self):
        from pipeline.feature_enrichment import SourceReview

        review = SourceReview.__new__(SourceReview)
        review.sid = 'firefox-ios'
        owner = {'title': 'Tab grouping', 'aliases': []}
        citation = {'item_key': 'app-store-159.1'}
        other = ({'key': 'app-store-160.1', 'text': 'Tab grouping was added.'}, None, None)
        self.assertFalse(review.matches(owner, citation, APP_STORE_URL, other))

    def test_dates_and_older_modified_items_use_record_and_item_not_shipping(self):
        self.rows.update({
            '1.0': release('1.0', '2026-10-26', [note(1, 'Lower published.')]),
            '2.0': release('2.0', '2026-11-25', [note(2, 'Upper published.')]),
            '3.0': release('3.0', '2026-10-25', [note(3, 'Lower edit.', '2026-10-25T22:00:00Z'),
                                                    note(4, 'Earlier edit.', '2026-10-25T21:59:59Z'),
                                                    note(5, 'Upper edit.', '2026-11-24T22:00:00Z')]),
            '4.0': release('4.0', '2026-11-27', [note(6, 'Future release.')]),
        })
        self.pages[SHIPS].append(ship(10, 'firefox-v1.0', '2025-01-01T00:00:00Z'))
        self.prepare()
        old_url = detail_url('3.0')
        self.pages[old_url] = self.pages[old_url].replace('Earlier edit.</li>', '<span id="older-item">Earlier edit.</span></li>')
        _, rows = self.cli('boundary')
        self.assertEqual({'note-1', 'note-2', 'note-3', 'note-5'}, {r['item_key'] for r in rows})
        self.assertEqual('item_change', next(r for r in rows if r['item_key'] == 'note-5')['temporal_scope']['basis'])
        self.assertNotIn(detail_url('4.0'), self.calls)
        windows = json.loads((self.root / 'runs/boundary/work/windows/firefox-ios.json').read_bytes())
        self.assertEqual('before_period', windows.get(old_url + '#note-4'))
        self.assertEqual('before_period', windows.get(old_url + '#older-item'))
        self.assertEqual({'in_period', 'before_period'}, {r[0] for r in windows['mixed_documents'][detail_url('3.0')]})
        _, rows = self.cli('weekly', mode='weekly_reconcile')
        self.assertIn('note-4', {r['item_key'] for r in rows})
        self.rows['3.0']['notes'][0]['modified'] = '2026-11-24T22:00:01Z'
        self.prepare()
        state, rows = self.cli('future', expected=2)
        self.assertIn('after cutoff', str(state['errors']))
        self.assertNotIn('note-3', {r['item_key'] for r in rows})

    def test_old_feature_review_uses_pinned_notes_and_verified_version_html(self):
        version, day = '3.0', '2026-04-01'
        url = detail_url(version)
        stamp = day + 'T12:00:00Z'
        def record(text):
            return dict(release(version, day, [note(4, text, stamp)] if text else []), modified=stamp)
        text = 'Mute tabs is available on iPadOS.'
        live = html(record(text)).replace(text, f'<span id="note-9">{text}</span>')
        missing = detail_url('3.1')
        for target, key, title in ((url, 'mute', 'Mute tabs'), (url + '#note-4', 'translated', '음소거'),
                                   (url + '#note-9', 'wrong', 'Missing note'), (missing, 'absent', 'Absent version')):
            request = self.root / 'decision.json'
            request.write_text(json.dumps(dict(browser='firefox', source_id='firefox-ios', url=target,
                                               canonical_key=key, title=title)))
            args = ['collect', '--repository', str(self.repo), '--private-dir', str(self.root / 'manual'),
                    '--save-item', str(request)]
            with patch('sys.argv', args), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as rc:
                runpy.run_path(str(ROOT / 'pipeline/collect.py'), run_name='__main__')
            self.assertEqual(0, rc.exception.code)
        def reviews(name):
            path = self.root / 'runs' / name / 'work/enrichment/firefox-ios.json'
            return {j['url']: j for j in json.loads(path.read_bytes())}
        self.pages[SHIPS].append(ship(30, 'firefox-v3.0', stamp))
        def prepare_version(pinned, rendered):
            self.rows[version] = record(pinned)
            self.prepare()
            self.pages[url] = rendered
        for name, pinned, rendered in (
                ('empty', None, live), ('changed', 'Mute tabs.', live),
                ('wrong-version', text, live.replace('>3.0<', '>3.1<')),
                ('wrong-note', text, live.replace('id="note-4"', 'id="note-8"')),
                ('future-metadata', text, live.replace('</head>', '<meta itemprop="dateModified" content="2026-12-01"></head>'))):
            with self.subTest(name=name):
                prepare_version(pinned, rendered)
                self.cli(name)
                self.assertFalse(any(j.get('candidate') or j.get('reference_review') for j in reviews(name).values()))
        prepare_version(text, OSError('detail temporarily unavailable'))
        self.cli('retry')
        self.assertFalse(any(j.get('candidate') or j.get('reference_review') for j in reviews('retry').values()))
        self.pages[url] = live
        cached_zip = (self.root / 'runs/retry/work/browser/cache' / hashlib.sha256(self.pages[ARCHIVE]).hexdigest())
        cached_zip.write_bytes(b'tampered')
        self.calls.clear()
        self.cli('retry', resume=True)
        self.assertEqual([], self.calls)
        self.assertIn('checksum', reviews('retry')[url]['error'])
        cached_zip.write_bytes(self.pages[ARCHIVE])
        self.cli('retry', resume=True)
        jobs = reviews('retry')
        self.assertEqual([url], self.calls)
        self.assertEqual(text, jobs[url]['candidate']['classification_text'])
        self.assertEqual([text], jobs[url + '#note-4']['review_passages'])
        self.assertFalse(jobs[url + '#note-9'].get('candidate') or jobs[url + '#note-9'].get('reference_review'))
        self.assertIn('No pinned public', jobs[missing]['error'])
        self.pages[COMMIT.replace('11-24', '11-25')] = self.pages[COMMIT]
        self.cli('next-day', cutoff=CUTOFF.replace('11-25', '11-26'))
        self.assertEqual(jobs[url]['content_sha256'], reviews('next-day')[url]['content_sha256'])
        self.assertNotIn(missing, self.calls)

    def test_unknown_record_is_never_empty_or_complete(self):
        for label, changes in [('null', {'notes': None}), ('missing', {}), ('wrong-type', {'notes': {}}),
                               ('wrong-product', {'product': 'Firefox'}), ('wrong-version', {'version': '162.0'}),
                               ('private', {'is_public': False}), ('wrong-channel', {'channel': 'Nightly'})]:
            row = release('161.0', '2026-11-23', [])
            row.update(changes)
            if label == 'missing':
                row.pop('notes')
            self.rows['161.0'] = row
            self.prepare()
            with self.subTest(label=label):
                state, rows = self.cli(label, expected=2)
                self.assertTrue(state['errors'])
                self.assertNotIn('161.0', state.get('firefox_ios_inventory', {}).get('empty_versions', []))

    def test_html_evidence_and_inventory_must_agree(self):
        url = detail_url('160.0')
        original = self.pages[url]
        for label, replacement in [('wrong-text', original.replace(DUO, 'Another feature.')),
                ('day', original.replace('2026-11-10', '2026-11-11')), ('locale', original.replace('en-US"', 'de"')),
                ('wrong-note', original.replace('note-792483', 'note-42')), ('absent', OSError('HTTP 404')),
                ('redirect-current', Response(detail_url('161.0'), original.encode())),
                ('truncated', original.removesuffix('</html>'))]:
            with self.subTest(label=label), patch.dict(self.pages, {url: replacement}):
                state, rows = self.cli(label, expected=2)
                self.assertEqual([url], state['pending'])
                self.assertEqual([], rows)
        self.pages[INDEX]['truncated'] = True
        state, _ = self.cli('short-tree', expected=2)
        self.assertIn('Incomplete', str(state['errors']))
        self.pages[INDEX]['truncated'] = False
        self.pages[INDEX]['tree'][0]['sha'] = 'c' * 40
        state, _ = self.cli('changed-archive', expected=2)
        self.assertIn('pinned Git tree', str(state['errors']))
        self.prepare()
        self.pages[NEXT] = [ship(10, 'firefox-v162.0')]
        state, _ = self.cli('missing-next', expected=2)
        self.assertIn('omitted its next page', str(state['errors']))

    def test_partial_detail_retry_reuses_pinned_record_and_rejects_changed_text(self):
        url = detail_url('160.0')
        self.pages[url] = TimeoutError('timeout')
        state, _ = self.cli('resumed', expected=2)
        self.assertIn(url, state['pending'])
        self.calls.clear()
        self.pages[url] = html(self.rows['160.0'])
        state, rows = self.cli('resumed', resume=True)
        self.assertEqual('complete', state['status'])
        self.assertEqual([], rows)
        self.assertEqual([url, detail_url('161.0')], self.calls)

    def test_markdown_and_rollout_cannot_mask_different_visible_evidence_or_link(self):
        from pipeline.collectors.browser.firefox_ios import ROLLOUT
        item = note(12, '**Faster:** Read [page tips][1].\n\n  [1]: https://support.mozilla.org/tips')
        item['progressive_rollout'] = True
        self.rows['162.0'] = release('162.0', '2026-11-23', [item])
        self.prepare()
        url = detail_url('162.0')
        self.pages[url] = self.pages[url].replace(item['note'], '<strong>Faster:</strong> Read '
            '<a href="https://support.mozilla.org/tips">page tips</a>.' + '<div>' + ROLLOUT + '</div>')
        _, rows = self.cli('format')
        self.assertEqual(['note-12'], [r['item_key'] for r in rows])
        for name, edit in [('link-target', self.pages[url].replace('/tips"', '/other"')),
                           ('rollout-text', self.pages[url].replace('feedback', 'telemetry'))]:
            with patch.dict(self.pages, {url: edit}):
                state, rows = self.cli(name, expected=2)
                self.assertIn(url, state['pending'])
                self.assertEqual([], rows)

    def test_page_budget_resume_rechecks_shipping_prefix_and_pins_mozilla_snapshot(self):
        registry = self.repo / 'config/sources.yml'
        data = json.loads(registry.read_text())
        source = next(s for s in data['sources'] if s['source_id'] == 'firefox-ios')
        source['discovery']['max_pages'] = 4
        registry.write_text(json.dumps(data))
        state, _ = self.cli('limited', expected=2)
        self.assertIn(NEXT, state['pending'])
        self.assertEqual([COMMIT, INDEX, ARCHIVE, SHIPS], self.calls)
        self.pages[SHIPS].append(ship(30, 'firefox-v162.0'))
        self.calls.clear()
        state, _ = self.cli('limited', expected=2, resume=True)
        self.assertIn('Mutable enumeration changed', str(state['errors']))
        self.assertEqual([SHIPS], self.calls)

    def test_precise_publication_controls_items_and_empty_releases_at_both_boundaries(self):
        cases = [
            ('31.0', '2026-11-25', '2026-11-25T07:00:01+09:00'),
            ('32.0', '2026-10-26', '2026-10-26T06:59:59+09:00'),
            ('33.0', '2026-11-25', '2026-11-25T07:00:00+09:00'),
            ('34.0', '2026-10-26', '2026-10-26T07:00:00+09:00'),
            ('35.0', '2026-10-25', '2026-10-25T22:00:00Z'),
        ]
        for version, day, stamp in cases:
            ident = int(version.split('.')[0])
            self.rows[version] = release(version, day, [note(ident, 'A new feature.', '2026-10-01T00:00:00Z')])
            empty_version = '1' + version
            self.rows[empty_version] = release(empty_version, day, [])
            self.rows[empty_version]['modified'] = '2026-10-01T00:00:00Z'
        self.prepare()
        for version, day, stamp in cases:
            for v in (version, '1' + version):
                url = detail_url(v)
                self.pages[url] = self.pages[url].replace('</head>',
                    f'<meta property="article:published_time" content="{stamp}"></head>')
        state, rows = self.cli('precise-pub')
        self.assertEqual({'note-33', 'note-34', 'note-35'}, {r['item_key'] for r in rows})
        self.assertTrue(all(r['temporal_scope']['precision'] == 'timestamp' for r in rows))
        self.assertEqual({'161.0', '133.0', '134.0', '135.0'}, set(state['firefox_ios_inventory']['empty_versions']))
        self.assertTrue({detail_url(v) for v in ('31.0', '32.0', '131.0', '132.0')} <= set(state['excluded_by_date']))

    def test_conflicting_owned_timestamps_and_unrelated_page_times(self):
        url = detail_url('160.0')
        original = self.pages[url]
        meta = '<meta property="article:published_time" content="2026-11-10T11:00:00Z">'
        self.pages[url] = original.replace('</head>', meta + meta.replace('11:00:', '12:00:') + '</head>')
        state, _ = self.cli('conflicting-times', expected=2)
        self.assertIn('Conflicting Firefox iOS publication dates', str(state['errors']))
        self.pages[url] = original.replace('2026-11-10</p>',
            '<time datetime="2026-11-10T11:00:00">2026-11-10</time></p>')
        state, _ = self.cli('no-offset', expected=2)
        self.assertIn('Unverified Firefox iOS publication', str(state['errors']))
        self.pages[url] = original.replace('</html>', '<footer><time datetime="2026-12-01T00:00:00Z">December</time>'
                                           + meta.replace('2026-11-10', '2026-12-01') + '</footer></html>')
        state, _ = self.cli('footer-time')
        self.assertEqual(1, state['duplicate'])

    def test_page_owned_metadata_spellings_apply_publication_and_modification_cutoffs(self):
        row = release('31.0', '2026-11-25', [note(31, 'A product feature.')])
        self.rows['31.0'] = row
        self.prepare()
        url = detail_url('31.0')
        original = self.pages[url]
        stamp = '2026-11-25T07:00:01+09:00'
        public_fields = ('date', 'datePublished', 'publication_date', 'article:published_time')
        change_fields = ('dateModified', 'article:modified_time')
        for attr in ('name', 'property', 'itemprop'):
            for field in public_fields + change_fields:
                name = f'{attr}-{field.replace(":", "-")}'
                metadata = f'<meta {attr}="{field}" content="{stamp}">'
                with self.subTest(name=name), patch.dict(self.pages, {url: original.replace('</head>', metadata + '</head>')}):
                    state, rows = self.cli(name, expected=2 if field in change_fields else 0)
                    self.assertNotIn('note-31', {r['item_key'] for r in rows})
                    if field in change_fields:
                        self.assertIn('after cutoff', str(state['errors']))
                    else:
                        self.assertIn(url, state['excluded_by_date'])
        for tag, attr in [('time', 'datetime'), ('span', 'content')]:
            date = f'<{tag} itemprop="datePublished" {attr}="{stamp}">2026-11-25</{tag}>'
            with self.subTest(tag=tag), patch.dict(self.pages, {url: original.replace('2026-11-25</p>', date + '</p>')}):
                _, rows = self.cli(f'owned-{tag}')
                self.assertNotIn('note-31', {r['item_key'] for r in rows})
        bad = original.replace('</head>', '<meta itemprop="dateModified" content="2026-11-01T03:00:00Z">'
                               '<meta name="article:modified_time" content="2026-11-01T05:00:00Z"></head>')
        with patch.dict(self.pages, {url: bad}):
            state, _ = self.cli('conflicting-modifications', expected=2)
            self.assertIn('Conflicting', str(state['errors']))

        # A related article can share <main> with the release without owning its timestamp.
        unrelated = original.replace('</head>', '</head><main>').replace('</html>',
            '<article><meta name="datePublished" content="' + stamp + '"></article></main></html>')
        with patch.dict(self.pages, {url: unrelated}):
            _, rows = self.cli('nested-article')
            self.assertIn('note-31', {r['item_key'] for r in rows})
        owned = original.replace('<section class="c-release-notes">',
            '<section class="c-release-notes" itemprop="dateModified" content="' + stamp + '">')
        with patch.dict(self.pages, {url: owned}):
            state, _ = self.cli('product-body-metadata', expected=2)
            self.assertIn('after cutoff', str(state['errors']))
