"""Private, complete GitHub release metadata; no credentials or release bodies.

Run separately: python -m pipeline.collectors.browser.brave_metadata --help.
The browser collector never invokes gh or reads authentication material.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit

from pipeline.temporal import instant

REPOSITORY = 'brave/brave-browser'
QUERY = '''query($cursor:String){repository(owner:"brave",name:"brave-browser"){
 nameWithOwner isPrivate releases(first:100,after:$cursor,orderBy:{field:CREATED_AT,direction:DESC}){
 totalCount pageInfo{hasNextPage endCursor} nodes{databaseId tagName url createdAt publishedAt isDraft}
 }}}'''
FIELDS = {'id', 'tag_name', 'url', 'created_at', 'published_at', 'is_draft'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def validate(bundle, cutoff, *, now=None):
    required = {'version', 'repository', 'cutoff', 'started_at', 'observed_at', 'complete', 'pages', 'first_page_recheck'}
    if not isinstance(bundle, dict) or set(bundle) != required or bundle['version'] != 1 or bundle['repository'] != REPOSITORY or bundle['complete'] is not True:
        raise ValueError('Incomplete or unsupported Brave metadata bundle')
    if instant(bundle['cutoff']) != instant(cutoff):
        raise ValueError('Brave metadata cutoff differs from the frozen collection window')
    start, observed = instant(bundle['started_at']), instant(bundle['observed_at'])
    if not instant(cutoff) <= start <= observed <= instant(now or stamp()):
        raise ValueError('Brave metadata observation times are invalid')
    if not isinstance(bundle['pages'], list) or not bundle['pages']:
        raise ValueError('Brave metadata pages are missing')
    cursor, total, ids, tags, ends, result = None, None, set(), set(), set(), []
    for index, page in enumerate(bundle['pages']):
        if not isinstance(page, dict) or set(page) != {'cursor', 'end_cursor', 'has_next_page', 'total_count', 'records', 'sha256'}:
            raise ValueError('Unexpected Brave metadata page fields')
        unsigned = {k: v for k, v in page.items() if k != 'sha256'}
        if page['sha256'] != digest(unsigned) or page['cursor'] != cursor:
            raise ValueError('Brave metadata page hash/cursor mismatch')
        if type(page['has_next_page']) is not bool or type(page['total_count']) is not int or page['total_count'] < 0:
            raise ValueError('Invalid Brave metadata pagination')
        if total is None:
            total = page['total_count']
        if page['total_count'] != total or not isinstance(page['records'], list) or len(page['records']) > 100:
            raise ValueError('Brave metadata inventory changed or exceeded page bounds')
        if page['has_next_page'] != (index < len(bundle['pages']) - 1):
            raise ValueError('Brave metadata cursor chain is truncated')
        end = page['end_cursor']
        if page['records'] and (not isinstance(end, str) or not end or end in ends):
            raise ValueError('Brave metadata end cursor did not advance')
        if not page['records'] and (page['has_next_page'] or total != 0 or end is not None):
            raise ValueError('Unexpected empty Brave metadata page')
        for row in page['records']:
            if not isinstance(row, dict) or set(row) != FIELDS or type(row['id']) is not int or row['id'] <= 0 or type(row['is_draft']) is not bool:
                raise ValueError('Invalid or nonminimal Brave release metadata')
            if not isinstance(row['tag_name'], str) or not row['tag_name'] or row['id'] in ids or row['tag_name'] in tags:
                raise ValueError('Duplicate or invalid Brave release identity')
            url = urlsplit(row['url'])
            if (url.scheme != 'https' or url.netloc != 'github.com' or url.query or url.fragment
                    or not url.path.startswith('/' + REPOSITORY + '/releases/tag/')
                    or unquote(url.path.split('/releases/tag/', 1)[1]) != row['tag_name']):
                raise ValueError('Brave release URL/repository mismatch')
            if instant(row['created_at']) > observed or (row['published_at'] is not None and instant(row['published_at']) > observed):
                raise ValueError('Brave release timestamp postdates observation')
            ids.add(row['id']); tags.add(row['tag_name']); result.append(row)
        cursor = end
        ends.add(end)
    if len(ids) != total:
        raise ValueError('Brave metadata unique count differs from totalCount')
    check = bundle['first_page_recheck']
    if not isinstance(check, dict) or set(check) != {'sha256', 'observed_at'} or check['sha256'] != bundle['pages'][0]['sha256'] or not start <= instant(check['observed_at']) <= observed:
        raise ValueError('Brave metadata first page changed during enumeration')
    return result


def request_page(cursor, runner=subprocess.run):
    response = runner(['gh', 'api', 'graphql', '--input', '-'], input=json.dumps({'query': QUERY, 'variables': {'cursor': cursor}}),
                      text=True, capture_output=True, check=False, shell=False)
    if response.returncode:
        # gh stderr can contain account/environment details. Never copy it.
        raise RuntimeError('gh GraphQL request failed; authenticate gh separately and retry a new metadata capture')
    raw = json.loads(response.stdout)
    if raw.get('errors'):
        raise ValueError('GitHub GraphQL returned errors')
    repo = raw.get('data', {}).get('repository')
    if not repo or repo.get('nameWithOwner') != REPOSITORY or repo.get('isPrivate') is not False:
        raise ValueError('Expected the public Brave repository')
    releases = repo['releases']
    records = [dict(id=n['databaseId'], tag_name=n['tagName'], url=n['url'], created_at=n['createdAt'],
                    published_at=n['publishedAt'], is_draft=n['isDraft']) for n in releases['nodes']]
    page = dict(cursor=cursor, end_cursor=releases['pageInfo']['endCursor'], has_next_page=releases['pageInfo']['hasNextPage'],
                total_count=releases['totalCount'], records=records)
    page['sha256'] = digest(page)
    return page


def capture(cutoff, *, request=request_page, max_pages=2000):
    started = stamp()
    if instant(cutoff) > instant(started):
        raise ValueError('Metadata cutoff must not be in the future')
    pages, cursor, cursors = [], None, set()
    for _ in range(max_pages):
        page = request(cursor)
        pages.append(page)
        if not page['has_next_page']:
            break
        cursor = page['end_cursor']
        if not cursor or cursor in cursors:
            raise ValueError('Brave metadata cursor repeated')
        cursors.add(cursor)
    else:
        raise ValueError('Brave metadata page budget reached; no complete bundle was written')
    first = request(None)
    result = dict(version=1, repository=REPOSITORY, cutoff=cutoff, started_at=started, observed_at=stamp(), complete=True,
                  pages=pages, first_page_recheck={'sha256': first['sha256'], 'observed_at': stamp()})
    result['observed_at'] = stamp()
    validate(result, cutoff)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cutoff', required=True)
    parser.add_argument('--output', type=Path, required=True, help='New private file outside the repository')
    parser.add_argument('--max-pages', type=int, default=2000)
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[3]
    output = args.output.expanduser().resolve()
    if output == repository or repository in output.parents or output.exists() or args.max_pages < 1:
        parser.error('Use a new private output outside the repository and a positive page budget')
    try:
        value = capture(args.cutoff, max_pages=args.max_pages)
    except (ValueError, RuntimeError, KeyError, TypeError, OSError):
        print('Metadata capture incomplete. No complete bundle written; authenticate gh separately or retry a new capture.')
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
    print(json.dumps({'complete': True, 'releases': sum(len(p['records']) for p in value['pages']), 'pages': len(value['pages']), 'sha256': digest(value)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
