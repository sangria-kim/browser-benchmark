import contextlib
import hashlib
import io
import json
from pathlib import Path
import runpy
import shutil
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from pipeline.collectors.browser import Response
from pipeline.collectors.browser.firefox_ios import NOTES_API, SHIPPING, detail_url


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
