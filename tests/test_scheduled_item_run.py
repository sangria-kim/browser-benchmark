"""Run the 07:00 scheduled CLI against an unmodified registry and isolated data."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from pipeline.run_daily import commit_candidate, read

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = '2026-11-26T07:00:00+09:00'
BETA = 'https://www.firefox.com/en-US/firefox/beta/notes/'
ANDROID = 'https://www.firefox.com/en-US/firefox/android/notes/'


def install_synthetic_transport():
    """Child-process fixture. Two real Firefox parsers, 19 empty source results."""
    from pipeline.collectors.browser import collector
    from pipeline.collectors.browser.transport import Response

    def offline(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo'):
            raise RuntimeError('External network disabled by the scheduled CLI fixture')

    sys.addaudithook(offline)
    fixture = Path(os.environ['SCHEDULED_ITEM_FIXTURE'])

    def fetch(url):
        with (fixture / 'requests').open('a', encoding='utf-8') as log:
            log.write(url + '\n')
        if url == BETA:
            body = '<h2>New</h2><p id="tabs">You can now group tabs.</p>'
        elif url == ANDROID:
            if not (fixture / 'android-ready').exists():
                raise TimeoutError('Synthetic Android outage')
            body = '<h2>Fixed</h2><p id="fix">Fixed a startup issue.</p>'
        else:
            raise AssertionError(f'Unexpected test URL: {url}')
        page = (f'<html><head><meta property="article:published_time" content="2026-11-24">'
                f'</head><body><div class="c-release-notes">{body}</div></body></html>')
        return Response(url, page.encode(), observed_at='2026-11-26T07:01:00+09:00')

    real_collect = collector.BrowserCollector.collect

    def collect_source(self, source, cutoff, *args, **kwargs):
        sid = source['source_id']
        if sid in ('firefox-beta', 'firefox-android'):
            return real_collect(self, source, cutoff, *args, **kwargs)
        self.parsed_ids = set()
        return {'source_id': sid, 'cutoff': cutoff, 'status': 'complete'}

    collector.HTTPTransport = lambda: fetch
    collector.BrowserCollector.collect = collect_source


class ScheduledItemRunTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.repo = self.folder / 'data-repo'
        shutil.copytree(ROOT / 'config', self.repo / 'config')
        commit_candidate(self.repo)
        self.run_dir = self.folder / 'state' / 'daily-20261126-0700'
        bootstrap = self.folder / 'bootstrap'
        bootstrap.mkdir()
        (bootstrap / 'sitecustomize.py').write_text(
            'import os, traceback\n'
            'try:\n'
            '    from test_scheduled_item_run import install_synthetic_transport\n'
            '    install_synthetic_transport()\n'
            'except BaseException:\n'
            '    traceback.print_exc()\n'
            '    os._exit(1)\n')
        self.env = dict(os.environ, SCHEDULED_ITEM_FIXTURE=str(self.folder),
                        PYTHONPATH=os.pathsep.join(map(str, (bootstrap, ROOT / 'tests', ROOT))))
        self.receipt = self.repo / 'data/daily-status/2026-11-26.json'
        self.detail = self.repo / 'data/browser-status/daily/2026-11-25T220000.000000Z.json'

    def cli(self, *args, expected=0):
        result = subprocess.run(
            [sys.executable, '-B', '-m', 'pipeline.run_daily', '--repository', str(self.repo),
             '--private-dir', str(self.run_dir.parent), '--run-id', self.run_dir.name, *map(str, args)],
            cwd=ROOT, env=self.env, text=True, capture_output=True, timeout=45)
        self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
        return result.stdout

    def assert_receipt(self, status, collected, changed):
        receipt = read(self.receipt)
        self.assertEqual((CUTOFF, status, collected, changed),
                         (receipt['cutoff'], receipt['status'], receipt['collected_feature_count'], receipt['change_count']))

    def test_official_url_saved_before_recovery_then_counted_once(self):
        metadata = self.folder / 'attributions.json'
        metadata.write_text(json.dumps({'a' * 64: []}))
        schedule = ('--daily-status', '--cutoff', CUTOFF, '--reviewed-attributions', metadata)
        self.assertFalse(json.loads(self.cli(*schedule, expected=2))['collection_complete'])
        state = read(self.run_dir / 'feature-run.json')
        enabled = [s['source_id'] for s in read(self.repo / 'config/sources.yml')['sources']
                   if s['enabled'] and s['browser'] not in ('brave', 'vivaldi', 'opera')]
        self.assertEqual(21, len(enabled))
        self.assertEqual(sorted(enabled), sorted(state['sources']))
        self.assertEqual(sorted(enabled), state['daily_status']['enabled'])
        self.assertEqual('2026-10-27T07:00:00+09:00', state['start'])
        self.assertEqual(['firefox-android'], [sid for sid, result in state['source_results'].items()
                                              if result['status'] != 'complete'])
        candidates = self.run_dir / 'work/candidates'
        beta, = read(candidates / 'firefox-beta.json')
        self.assertEqual(BETA, beta['evidence']['url'])
        self.assertIn('group tabs', beta['evidence']['excerpt'])
        item = self.run_dir / 'item.json'
        item.write_text(json.dumps({'browser': 'firefox', 'source_id': 'firefox-beta', 'canonical_key': 'group-tabs',
                                    'title': 'Group tabs', 'url': beta['evidence']['url']}))
        self.cli('--record-incomplete')
        self.assert_receipt('incomplete', None, None)
        first = json.loads(self.cli('--save-item', item))
        self.assertTrue(first['changed'])
        catalog = self.repo / 'data/catalog/features/catalog.json'
        feature, = read(catalog)
        self.assertEqual(first['feature_id'], feature['feature_id'])
        self.assertEqual({}, feature['feature_facts'])
        source, = read(self.repo / 'data/source-items/firefox/firefox-beta.json')
        self.assertEqual(('reference', BETA), (source['record_status'], source['evidence']['url']))
        self.assert_receipt('incomplete', None, None)
        self.assertEqual('incomplete', read(self.detail)['browsers']['firefox']['status'])

        (self.folder / 'android-ready').touch()
        self.assertTrue(json.loads(self.cli(*schedule, '--resume'))['collection_complete'])
        self.assertEqual([BETA, ANDROID, ANDROID], (self.folder / 'requests').read_text().splitlines())
        public = {path: path.read_bytes() for path in (self.repo / 'data').rglob('*.json')}
        self.assertEqual(first['feature_id'], json.loads(self.cli('--save-item', item))['feature_id'])
        self.assertEqual(public, {path: path.read_bytes() for path in (self.repo / 'data').rglob('*.json')})
        self.cli('--record-incomplete')
        self.assert_receipt('incomplete', None, None)

        fixed, = read(candidates / 'firefox-android.json')
        self.assertIn('startup issue', fixed['evidence']['excerpt'])

        def identity(row):
            return dict(source_item_id=row['source_item_id'], revision_id=row['revisions'][-1]['revision_id'])

        # URL-only publication used its own reference. Link the observed candidate
        # to the same feature key when completing the browser's dispositions.
        classification = dict(decisions=[dict(**identity(beta), canonical_key='group-tabs', title='Group tabs',
                                              change_kind='evidence_only')],
                              dispositions=[dict(**identity(beta), source_id='firefox-beta', disposition='selected'),
                                            dict(**identity(fixed), source_id='firefox-android', disposition='excluded')])
        scope = read(self.detail)['scope']['expected']
        self.assertEqual({'chrome', 'edge', 'firefox', 'safari', 'whale'}, set(scope))
        for index, browser in enumerate(sorted(scope)):
            choices = self.run_dir / (browser + '.json')
            choices.write_text(json.dumps(classification if browser == 'firefox' else dict(decisions=[], dispositions=[])))
            self.cli('--save-browser', browser, '--save-features', choices)
            if index < len(scope) - 1:
                self.assert_receipt('incomplete', None, None)
        self.assert_receipt('complete', 1, 1)
        self.assertTrue(all(row['status'] == 'complete' for row in read(self.detail)['browsers'].values()))
        published, = read(catalog)
        self.assertEqual(first['feature_id'], published['feature_id'])
