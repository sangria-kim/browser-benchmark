"""Reconcile Mozilla's release-note snapshot with the public Firefox iOS release list."""
import hashlib
import io
import json
import re
from datetime import date, timezone
from urllib.parse import urlencode
from zipfile import ZipFile

from pipeline.temporal import instant, policy_day
from .html import Tree, blocks, date_value, modification, publication_value


NOTES_API = 'https://api.github.com/repos/mozilla/release-notes'
SHIPPING = 'https://api.github.com/repos/mozilla-mobile/firefox-ios/releases'
SHIPPING_ID = 'https://api.github.com/repositories/26133979/releases'
VERSION = r'\d+(?:\.\d+)+'
PREFIX = 'releases/firefox-for-ios-'
SUFFIX = '-release.json'
SHA = r'[0-9a-f]{40}'


def detail_url(version):
    return f'https://www.firefox.com/en-US/firefox/ios/{version}/releasenotes/'


def page(collector, url, *, mutable=False):
    if not collector.budget(url, 'pages'):
        raise ValueError('Firefox iOS inventory page limit reached')
    collector.state['pages'] += 1
    response = collector.get_page(url) if mutable else collector.get(url)
    if response.url != url:
        raise ValueError('Unexpected final Mozilla inventory URL')
    return response


def release_archive(collector):
    end = instant(collector.cutoff).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    query = urlencode({'sha': 'master', 'until': end, 'per_page': 1})
    commits = json.loads(page(collector, f'{NOTES_API}/commits?{query}').body)
    if not isinstance(commits, list) or len(commits) != 1:
        raise ValueError('Missing Mozilla release-note snapshot at cutoff')
    commit = commits[0]
    sha = commit['sha']
    tree = commit['commit']['tree']['sha']
    if (not re.fullmatch(SHA, sha) or not re.fullmatch(SHA, tree)
            or instant(commit['commit']['committer']['date']) > instant(collector.cutoff)):
        raise ValueError('Invalid Mozilla snapshot identity or commit time')
    index = json.loads(page(collector, f'{NOTES_API}/git/trees/{tree}?recursive=1').body)
    if index['sha'] != tree or index['truncated'] is not False:
        raise ValueError('Incomplete Mozilla release-note tree')
    expected = {}
    for entry in index['tree']:
        path = entry['path']
        if path.startswith(PREFIX) and path.endswith(SUFFIX):
            if (path in expected or entry['type'] != 'blob' or not re.fullmatch(SHA, entry['sha'])
                    or entry['mode'] != '100644'):
                raise ValueError('Invalid Mozilla iOS release-note tree entry')
            expected[path] = entry['sha']
    if not expected:
        raise ValueError('Missing Firefox iOS release records in Mozilla tree')
    archive = page(collector, f'https://codeload.github.com/mozilla/release-notes/zip/{sha}')
    records = {}
    total = 0
    with ZipFile(io.BytesIO(archive.body)) as zipped:
        if zipped.comment != sha.encode():
            raise ValueError('Mozilla release-note archive commit mismatch')
        for member in zipped.infolist():
            prefix = f'release-notes-{sha}/'
            path = member.filename.removeprefix(prefix)
            if not path.startswith(PREFIX) or not path.endswith(SUFFIX):
                continue
            collector.check_time()
            total += member.file_size
            if (path == member.filename or path not in expected or member.file_size > 1024 * 1024
                    or total > 32 * 1024 * 1024):
                raise ValueError('Unexpected or oversized Firefox iOS archive entry')
            raw = zipped.read(member)
            if hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest() != expected.pop(path):
                raise ValueError('Firefox iOS record differs from the pinned Git tree')
            row = json.loads(raw)
            if row.get('is_public') is False:
                continue
            version = path[len(PREFIX):-len(SUFFIX)]
            if (row.get('is_public') is not True or not re.fullmatch(VERSION, version)
                    or row.get('version') != version or row.get('product') != 'Firefox for iOS'
                    or row.get('channel') != 'Release' or row.get('slug') != f'firefox-for-ios-{version}-release'):
                raise ValueError('Invalid public Firefox iOS release identity: ' + path)
            records[version] = row
    if expected or not records:
        raise ValueError('Incomplete Firefox iOS release-note archive')
    return sha, records


def shipping_versions(collector):
    if collector.source['url'] != SHIPPING:
        raise ValueError('Unexpected Firefox iOS shipping registry URL')
    result = {}
    ids = set()
    page_number = 1
    expect_empty = False
    while True:
        url = f'{SHIPPING}?per_page=100&page={page_number}'
        response = page(collector, url, mutable=True)
        rows = json.loads(response.body)
        if not isinstance(rows, list) or len(rows) > 100 or (not rows and page_number == 1):
            raise ValueError('Invalid Firefox iOS shipping list')
        if expect_empty:
            if rows:
                raise ValueError('Firefox iOS shipping list omitted its next page')
            break
        for row in rows:
            if type(row.get('draft')) is not bool or type(row.get('prerelease')) is not bool:
                raise ValueError('Unknown Firefox iOS release visibility')
            ident = row['id']
            if type(ident) is not int or ident in ids:
                raise ValueError('Duplicate or invalid GitHub release ID')
            ids.add(ident)
            if row['draft'] or row['prerelease']:
                continue
            tag = row['tag_name']
            if tag.startswith('focus/klar-'):
                continue
            match = re.fullmatch(r'(?:firefox-v|v)?(\d+(?:\.\d+)*)(?:-rel)?', tag)
            if not match:
                if re.fullmatch(r'(?:firefox-v|v)?[\d.]+(?:b\d+|-b|RC\d+)', tag):
                    continue
                raise ValueError('Unrecognized public Firefox iOS shipping tag')
            stamp = instant(row['published_at'])
            version = match[1] if '.' in match[1] else match[1] + '.0'
            if version in result and result[version] != stamp:
                raise ValueError('Conflicting Firefox iOS shipping aliases for ' + version)
            result[version] = stamp
        links = response.headers.get('link', response.headers.get('Link', ''))
        next_links = re.findall(r'<([^>]+)>;\s*rel="next"', links)
        if not next_links:
            if 'rel="next"' in links or 'rel="last"' in links:
                raise ValueError('Unverified end of Firefox iOS shipping pagination')
            expect_empty = True
            page_number += 1
            continue
        page_number += 1
        if len(rows) != 100 or len(next_links) != 1 or next_links[0] not in {
                f'{root}?per_page=100&page={page_number}' for root in (SHIPPING, SHIPPING_ID)}:
            raise ValueError('Incomplete or unexpected Firefox iOS shipping pagination')
    if not result:
        raise ValueError('No public Firefox iOS shipping versions')
    return result


def checked_notes(collector, row):
    published = row['release_date']
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', published) or date.fromisoformat(published).isoformat() != published:
        raise ValueError('Invalid Firefox iOS publication day')
    if instant(row['modified']) > instant(collector.cutoff):
        raise ValueError('Only a Firefox iOS release revision after cutoff is available')
    if not isinstance(row.get('notes'), list):
        raise ValueError('Firefox iOS notes must be an explicit array')
    notes = {}
    for note in row['notes']:
        ident = note['id']
        if (note.get('is_public') is not True or type(ident) is not int or ident <= 0
                or not isinstance(note.get('note'), str) or not note['note'].strip()
                or not isinstance(note.get('tag'), str) or f'note-{ident}' in notes):
            raise ValueError('Invalid or duplicate Firefox iOS note')
        if instant(note['modified']) > instant(collector.cutoff):
            raise ValueError('Only a Firefox iOS item revision after cutoff is available')
        notes[f'note-{ident}'] = note
    return notes


# The public item hash includes this visible, invariant Firefox.com control.
# Never use a live, unverified suffix as part of a cutoff-pinned note.
ROLLOUT = ('This feature is part of a progressive roll out. What is a progressive roll out? '
           'Certain new Firefox features are released gradually. This means some users will see the feature '
           'before everyone does. This approach helps to get early feedback to catch bugs and improve behavior '
           'quickly, meaning more Firefox users overall have a better experience.')


def matches_note(note, unit, node):
    # Match the publisher's plain, bold and numbered reference-link Markdown.
    # Retain unfamiliar syntax, so unsupported rendering leaves coverage partial.
    lines = []
    references = {}
    for line in note['note'].splitlines():
        definition = re.fullmatch(r'\s*\[(\d+)\]:\s+(https?://\S+)\s*', line)
        if definition:
            key, href = definition.groups()
            if key in references:
                return False
            references[key] = href
        else:
            lines.append(line)
    hrefs = []
    def link(match):
        hrefs.append(references.get(match[2]))
        return ' ' + match[1] + ' '
    text = re.sub(r'\[([^\[\]]+)\]\[(\d+)\]', link, ' '.join(lines))
    text = re.sub(r'\*\*([^*]+)\*\*', r' \1 ', text)
    if note.get('progressive_rollout') is True:
        text += ' ' + ROLLOUT
    actual_links = [n.attrs.get('href') for n in node.walk() if n.tag == 'a']
    return (unit['parsed'] and unit['section'] == (note['tag'] or 'document')
            and unit['text'] == ' '.join(text.split()) and None not in hrefs and hrefs == actual_links)


def document_units(response, version, row, notes, cutoff):
    expected_url = detail_url(version)
    text = response.text()
    root = Tree(text).root
    nodes = list(root.walk())
    def values(cls):
        return [n.text() for n in nodes if n.has_class(cls)]
    canonical = [n.attrs.get('href') for n in nodes if n.tag == 'link' and 'canonical' in n.attrs.get('rel', '').split()]
    dates = values('c-release-date')
    bodies = [n for n in nodes if n.has_class('c-release-notes')]
    if (response.url != expected_url or canonical != [expected_url] or '</html>' not in text.lower()
            or [n.attrs.get('lang') for n in nodes if n.tag == 'html'] != ['en-US']
            or values('c-release-version') != [version] or values('c-release-product') != ['Firefox for iOS Release']
            or len(dates) != 1 or date_value(dates[0]) != row['release_date'] or len(bodies) != 1):
        raise ValueError('Inconsistent Firefox iOS version, locale, product or publication day')
    for n in nodes:
        if n.tag == 'meta' and n.attrs.get('property') in ('article:published_time', 'article:modified_time'):
            stamp = publication_value(n.attrs.get('content'))
            if not stamp or (n.attrs['property'] == 'article:published_time' and stamp[:10] != row['release_date']):
                raise ValueError('Unverified Firefox iOS page date metadata')
    modified = modification(root, bodies[0])
    if modified and (instant(modified) > instant(cutoff) if len(modified) > 10 else modified > policy_day(cutoff)):
        raise ValueError('Only a Firefox iOS HTML revision after cutoff is available')
    units = blocks(bodies[0])
    if ({u['key'] for u in units} != set(notes) or len(units) != len(notes)
            or (not notes and bodies[0].text())):
        raise ValueError('Firefox iOS HTML note IDs disagree with the pinned release record')
    locations = {n.attrs['id']: n for n in bodies[0].walk() if n.tag == 'li' and n.attrs.get('id') in notes}
    for unit in units:
        note = notes[unit['key']]
        # Only accept text for which the live rendering agrees with the cutoff snapshot.
        # Unsupported Markdown or additional visible content needs verification.
        if unit['key'] not in locations or not matches_note(note, unit, locations[unit['key']]):
            raise ValueError('Firefox iOS note content differs from the pinned release record')
    return units


def collect_firefox_ios(collector):
    sha, records = release_archive(collector)
    history = collector.state['firefox_ios_inventory'] = {
        'snapshot': sha, 'public_records': len(records), 'verified_versions': [], 'empty_versions': [],
        'missing_shipping_versions': [], 'older_undated_shipping_versions': []}
    shipped = shipping_versions(collector)
    for version, stamp in shipped.items():
        if version in records or stamp > instant(collector.cutoff):
            continue
        # A GitHub publication is positive evidence of shipment. It cannot date a
        # missing Mozilla note, including one shipped before the lower boundary.
        if collector.publication_status(stamp.isoformat()) == 'before_period':
            history['older_undated_shipping_versions'].append(version)
        else:
            history['missing_shipping_versions'].append(version)
            collector.problem(detail_url(version), 'Shipped Firefox iOS version lacks a public Mozilla note record')
    if history['older_undated_shipping_versions']:
        collector.problem(SHIPPING, 'Older Firefox iOS shipments lack dated Mozilla records; note dates unverified')
    previous = {(r['evidence']['url'], r['item_key']): r for r in collector.previous}
    for version, row in records.items():
        url = detail_url(version)
        try:
            notes = checked_notes(collector, row)
            day = row['release_date']
            day_status = collector.publication_status(day)
            eligible = {key for key, note in notes.items() if day_status == 'in_period'
                        or collector.publication_status(note['modified']) == 'in_period'}
            empty_in_scope = not notes and (day_status == 'in_period'
                                            or collector.publication_status(row['modified']) == 'in_period')
            if day_status == 'after_cutoff' or not (eligible or empty_in_scope):
                collector.state['excluded_by_date'].append(url)
                continue
            if not collector.budget(url, 'documents'):
                break
            collector.state['documents'] += 1
            response = collector.get(url)
            units = document_units(response, version, row, notes, collector.cutoff)
            for unit in units:
                key = unit['key']
                if key in eligible:
                    old = previous.get((url, key))
                    collector.emit(url, response, unit, date=day, version=old['version'] if old else version,
                                   modified=notes[key]['modified'] if day_status == 'before_period' else None)
            history['verified_versions'].append(version)
            if not notes:
                history['empty_versions'].append(version)
            collector.document_done(url)
        except (ValueError, KeyError, TypeError, OSError) as error:
            collector.problem(url, str(error))
            if isinstance(error, TimeoutError) or getattr(error, 'code', None) in (403, 429):
                return
    else:
        collector.state['pagination_exhausted'] = True
