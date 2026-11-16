import copy
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
from types import SimpleNamespace
import unittest

from pipeline.collectors.browser.brave_metadata import validate, capture, request_page, digest, REPOSITORY
from pipeline.collectors.browser import BrowserCollector
from pipeline.collectors.browser.transport import Response
from pipeline import run_daily
from test_browser_collectors import source

CUTOFF = '2026-11-16T12:53:40.560982+00:00'


def row(ident=1, published='2026-01-01T01:00:00Z'):
    return dict(id=ident, tag_name='v' + str(ident), url='https://github.com/brave/brave-browser/releases/tag/v' + str(ident),
                created_at='2025-12-01T00:00:00Z', published_at=published, is_draft=False)


def page(rows, cursor=None, end='A', more=False, total=None):
    value = dict(cursor=cursor, end_cursor=end if rows else None, has_next_page=more, total_count=len(rows) if total is None else total, records=rows)
    value['sha256'] = digest(value)
    return value


def bundle(pages):
    return dict(version=1, repository=REPOSITORY, cutoff=CUTOFF, started_at='2026-11-16T13:00:00Z',
                observed_at='2026-11-16T13:01:00Z', complete=True, pages=pages,
                first_page_recheck={'sha256': pages[0]['sha256'], 'observed_at': '2026-11-16T13:00:59Z'})


def rehash(value):
    for p in value['pages']:
        p['sha256'] = digest({k: v for k, v in p.items() if k != 'sha256'})
    value['first_page_recheck']['sha256'] = value['pages'][0]['sha256']
    return value


class BraveMetadataTests(unittest.TestCase):
    def test_helper_writes_private_file_and_never_overwrites(self):
        from pipeline.collectors.browser.brave_metadata import main
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'metadata.json'
            with patch('sys.argv', ['helper', '--cutoff', CUTOFF, '--output', str(output)]), patch('pipeline.collectors.browser.brave_metadata.capture', return_value=bundle([page([row()])])):
                self.assertEqual(0, main())
                self.assertEqual(0o600, output.stat().st_mode & 0o777)
                with self.assertRaises(SystemExit): main()

    def test_complete_cursor_inventory_and_first_page_recheck(self):
        pages = [page([row()], more=True, total=2), page([row(2)], cursor='A', end='B', total=2)]
        self.assertEqual(2, len(validate(bundle(pages), CUTOFF)))
        replies, calls = iter(pages + [pages[0]]), []
        def request(cursor):
            calls.append(cursor)
            return next(replies)
        result = capture(CUTOFF, request=request)
        self.assertEqual([None, 'A', None], calls)
        self.assertEqual(2, len(validate(result, CUTOFF)))
        with self.assertRaises(ValueError):
            capture(CUTOFF, request=lambda cursor: pages[0], max_pages=1)

    def test_incomplete_duplicate_count_cursor_cutoff_repository_and_privacy_rejected(self):
        original = bundle([page([row()], more=True, total=2), page([row(2)], cursor='A', end='B', total=2)])
        cases = []
        v = copy.deepcopy(original); v['repository'] = 'other/repo'; cases.append(v)
        v = copy.deepcopy(original); v['cutoff'] = '2026-11-16T12:00:00Z'; cases.append(v)
        v = copy.deepcopy(original); v['observed_at'] = '2099-01-01T00:00:00Z'; cases.append(v)
        v = copy.deepcopy(original); v['pages'].pop(); cases.append(v)
        v = copy.deepcopy(original); v['pages'][1]['records'] = [row()]; cases.append(rehash(v))
        v = copy.deepcopy(original)
        for p in v['pages']: p['total_count'] = 3
        cases.append(rehash(v))
        v = copy.deepcopy(original); v['pages'][1]['end_cursor'] = 'A'; cases.append(rehash(v))
        v = copy.deepcopy(original); v['pages'][1]['cursor'] = 'wrong'; cases.append(rehash(v))
        v = copy.deepcopy(original); v['pages'][0]['records'][0]['owner_email'] = 'private@example.invalid'; cases.append(rehash(v))
        v = copy.deepcopy(original); v['first_page_recheck']['sha256'] = '0' * 64; cases.append(v)
        v = copy.deepcopy(original); v['complete'] = False; cases.append(v)
        for value in cases:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                validate(value, CUTOFF)

    def test_gh_boundary_uses_shell_false_and_minimizes_response(self):
        calls = []
        node = dict(databaseId=1, tagName='v1', url=row()['url'], createdAt=row()['created_at'], publishedAt=row()['published_at'], isDraft=False,
                    owner_email='private@example.invalid')
        raw = {'data': {'repository': {'nameWithOwner': REPOSITORY, 'isPrivate': False,
                'releases': {'totalCount': 1, 'pageInfo': {'hasNextPage': False, 'endCursor': 'A'}, 'nodes': [node]}}}}
        def runner(args, **kw):
            calls.append((args, kw))
            return SimpleNamespace(returncode=0, stdout=json.dumps(raw), stderr='')
        result = request_page(None, runner)
        self.assertFalse(calls[0][1]['shell'])
        self.assertEqual(['gh', 'api', 'graphql', '--input', '-'], calls[0][0])
        self.assertNotIn('owner_email', json.dumps(result))
        with self.assertRaises(RuntimeError) as failure:
            request_page(None, lambda *a, **k: SimpleNamespace(returncode=4, stdout='', stderr='SENSITIVE_TOKEN'))
        self.assertNotIn('SENSITIVE_TOKEN', str(failure.exception))
        raw['data']['repository']['isPrivate'] = True
        with self.assertRaises(ValueError): request_page(None, runner)

    def test_preboundary_created_release_is_recovered_by_publication_timestamp(self):
        record = row(9, '2025-12-31T15:00:00Z')  # Exactly Jan 1 KST; created in December.
        draft = row(10, None); draft['is_draft'] = True
        metadata = bundle([page([record, draft, row(11, '2025-12-31T14:59:59Z')])])
        api = 'https://api.github.com/repos/brave/brave-browser/releases?per_page=100&page=1'
        body_url = 'https://api.github.com/repos/brave/brave-browser/releases/9'
        body = dict(id=9, tag_name='v9', html_url=record['url'], draft=False, published_at=record['published_at'], body='- A new documented browser task.')
        calls = []
        def transport(url):
            calls.append(url)
            return Response(url, json.dumps([] if url == api else body).encode())
        with tempfile.TemporaryDirectory() as tmp:
            collector = BrowserCollector(Path(tmp) / 'repo', Path(tmp) / 'private', transport, brave_release_metadata=metadata)
            state = collector.collect(source('brave-releases'), CUTOFF, '2026-01-01')
            records = json.loads(collector.destination.read_text())
        self.assertEqual([api, body_url], calls)
        self.assertEqual('complete', state['status'])
        self.assertEqual(1, state['brave_metadata']['eligible_count'])
        self.assertEqual([], state['brave_metadata']['missing_release_ids'])
        self.assertEqual('in_period', records[0]['temporal_scope']['status'])
        self.assertEqual(record['published_at'], records[0]['temporal_scope']['evidence_date'])

    def test_metadata_must_cover_observed_public_release_ids(self):
        metadata = bundle([page([])])
        release = dict(id=9, tag_name='v9', html_url=row(9)['url'], draft=False, published_at=row(9)['published_at'], body='- A browser feature.')
        with tempfile.TemporaryDirectory() as tmp:
            collector = BrowserCollector(Path(tmp) / 'repo', Path(tmp) / 'private',
                                         lambda url: Response(url, json.dumps([release]).encode()), brave_release_metadata=metadata)
            state = collector.collect(source('brave-releases'), CUTOFF, '2026-01-01')
        self.assertEqual('partial', state['status'])
        self.assertTrue(any('absent from frozen metadata' in str(error) for error in state['errors']))

    def test_invalid_metadata_stays_partial_before_fetch_and_frozen_inputs_reject_edits(self):
        metadata = bundle([page([row()])]); metadata['cutoff'] = '2026-01-01T00:00:00Z'
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); calls = []
            collector = BrowserCollector(base / 'repo', base / 'private', lambda url: calls.append(url), brave_release_metadata=metadata)
            state = collector.collect(source('brave-releases'), CUTOFF, '2026-01-01')
            self.assertEqual('partial', state['status']); self.assertTrue(state['errors']); self.assertEqual([], calls)
            inputs = base / 'run/inputs'; inputs.mkdir(parents=True)
            path = inputs / 'brave.json'; path.write_text(json.dumps(bundle([page([row()])])))
            frozen = {'private_inputs': run_daily.private_input_inventory(inputs)}
            run_daily.verify_private_inputs(base / 'run', frozen)
            path.write_text('{}')
            with self.assertRaises(ValueError): run_daily.verify_private_inputs(base / 'run', frozen)


if __name__ == '__main__':
    unittest.main()
