"""Reconcile Mozilla's release-note snapshot with the public Firefox iOS release list."""
import hashlib
import io
import json
import re
from datetime import date, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from zipfile import ZipFile

from pipeline.temporal import instant, policy_day
from .firefox_ios_store import APP_STORE_URL, units as store_units
from .html import Tree, blocks, date_value, publication_value, reconcile_modification


NOTES_API = 'https://api.github.com/repos/mozilla/release-notes'
SHIPPING = 'https://api.github.com/repos/mozilla-mobile/firefox-ios/releases'
SHIPPING_ID = 'https://api.github.com/repositories/26133979/releases'
VERSION = r'\d+(?:\.\d+)+'
PREFIX = 'releases/firefox-for-ios-'
SUFFIX = '-release.json'
SHA = r'[0-9a-f]{40}'


def detail_url(version):
    return f'https://www.firefox.com/en-US/firefox/ios/{version}/releasenotes/'


def page(collector, url, *, mutable=False, cached_only=False):
    if cached_only:
        if url not in collector.progress['responses']:
            raise ValueError('Missing cutoff-pinned Firefox iOS snapshot response')
    else:
        if not collector.budget(url, 'pages'):
            raise ValueError('Firefox iOS inventory page limit reached')
        collector.state['pages'] += 1
    response = collector.get_page(url) if mutable else collector.get(url)
    if response.url != url:
        raise ValueError('Unexpected final Mozilla inventory URL')
    return response


def release_archive(collector, *, cached_only=False):
    end = instant(collector.cutoff).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    query = urlencode({'sha': 'master', 'until': end, 'per_page': 1})
    commits = json.loads(page(collector, f'{NOTES_API}/commits?{query}', cached_only=cached_only).body)
    if not isinstance(commits, list) or len(commits) != 1:
        raise ValueError('Missing Mozilla release-note snapshot at cutoff')
    commit = commits[0]
    sha = commit['sha']
    tree = commit['commit']['tree']['sha']
    if (not re.fullmatch(SHA, sha) or not re.fullmatch(SHA, tree)
            or instant(commit['commit']['committer']['date']) > instant(collector.cutoff)):
        raise ValueError('Invalid Mozilla snapshot identity or commit time')
    index = json.loads(page(collector, f'{NOTES_API}/git/trees/{tree}?recursive=1', cached_only=cached_only).body)
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
    archive = page(collector, f'https://codeload.github.com/mozilla/release-notes/zip/{sha}', cached_only=cached_only)
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


def page_dates(nodes, date_field, body, day):
    publications, modifications = [day], []
    # Mozilla prints the release date beside the product/version summary. A note,
    # independently scoped object, or page footer can have its own dates.
    date_nodes = set(date_field.walk())
    product_path = {body, date_field, *body.ancestors(), *date_field.ancestors()}
    owners = set(body.ancestors()).intersection(date_field.ancestors())
    owners = {n for n in owners if n.tag in ('main', 'article')}
    for node in nodes:
        ancestors = list(node.ancestors())
        in_head = node.tag == 'meta' and node.parent.tag == 'head' and node.parent.parent.tag == 'html'
        if not in_head and node not in date_nodes:
            lineage = (node, *ancestors)
            if (not any(n is body or n in owners for n in lineage)
                    or any(n.tag in ('aside', 'footer', 'nav', 'li')
                           or n.tag in ('article', 'section') and n not in product_path
                           or 'itemscope' in n.attrs and n not in product_path for n in lineage)):
                continue
        fields = {word.lower() for attr in ('property', 'name', 'itemprop')
                  for word in (node.attrs.get(attr) or '').split()}
        published = bool(fields & {'date', 'datepublished', 'publication_date', 'article:published_time'})
        modified = bool(fields & {'datemodified', 'article:modified_time'})
        if published and modified:
            raise ValueError('Conflicting Firefox iOS date field roles')
        if not modified and (node is date_field or node in date_nodes and node.tag == 'time'):
            published = True
        if not (published or modified):
            continue
        values = [publication_value(node.attrs[key]) for key in ('datetime', 'content') if key in node.attrs]
        if not values or node is date_field or node.tag == 'time':
            label = publication_value(node.text())
            if label or not values:
                values.append(label)
        if not all(values):
            raise ValueError('Unverified Firefox iOS publication or modification metadata')
        (modifications if modified else publications).extend(values)
    return (reconcile_modification(publications, 'Firefox iOS publication dates'),
            reconcile_modification(modifications, 'Firefox iOS modification dates'))


def document_metadata(response, version, day, cutoff):
    expected_url = detail_url(version)
    text = response.text()
    root = Tree(text).root
    nodes = list(root.walk())
    def values(cls):
        return [n.text() for n in nodes if n.has_class(cls)]
    canonical = [n.attrs.get('href') for n in nodes if n.tag == 'link' and 'canonical' in n.attrs.get('rel', '').split()]
    dates = [n for n in nodes if n.has_class('c-release-date')]
    bodies = [n for n in nodes if n.has_class('c-release-notes')]
    if (response.url != expected_url or canonical != [expected_url] or '</html>' not in text.lower()
            or [n.attrs.get('lang') for n in nodes if n.tag == 'html'] != ['en-US']
            or values('c-release-version') != [version] or values('c-release-product') != ['Firefox for iOS Release']
            or len(dates) != 1 or date_value(dates[0].text()) != day or len(bodies) != 1):
        raise ValueError('Inconsistent Firefox iOS version, locale, product or publication day')
    publication, modified = page_dates(nodes, dates[0], bodies[0], day)
    if modified and (instant(modified) > instant(cutoff) if len(modified) > 10 else modified > policy_day(cutoff)):
        raise ValueError('Only a Firefox iOS HTML revision after cutoff is available')
    return publication, bodies[0]


def document_units(body, notes, *, window_anchors=False):
    units = blocks(body, window_anchors=window_anchors)
    if ({u['key'] for u in units} != set(notes) or len(units) != len(notes)
            or (not notes and body.text())):
        raise ValueError('Firefox iOS HTML note IDs disagree with the pinned release record')
    locations = {n.attrs['id']: n for n in body.walk() if n.tag == 'li' and n.attrs.get('id') in notes}
    for unit in units:
        note = notes[unit['key']]
        # Only accept text for which the live rendering agrees with the cutoff snapshot.
        # Unsupported Markdown or additional visible content needs verification.
        if unit['key'] not in locations or not matches_note(note, unit, locations[unit['key']]):
            raise ValueError('Firefox iOS note content differs from the pinned release record')
    return units


def collect_firefox_ios(collector):
    sha, records = release_archive(collector)
    if collector.fact_review:
        collector.fact_review.firefox_records = records
    history = collector.state['firefox_ios_inventory'] = {
        'snapshot': sha, 'public_records': len(records), 'verified_versions': [], 'empty_versions': [],
        'missing_shipping_versions': [], 'older_undated_shipping_versions': [], 'app_store_versions': []}
    shipped = shipping_versions(collector)
    store_attempt = None

    def from_store(version, archived=None, *, backlog=False):
        nonlocal store_attempt
        if store_attempt is None:
            try:
                response = page(collector, APP_STORE_URL)
                store_records = store_units(response)
                store_attempt = (response, store_records, None)
                if collector.fact_review:
                    # The entire mixed-version page cannot be a feature proof.
                    collector.fact_review.restricted_raw.add(APP_STORE_URL)
                for store_stamp, store_unit in store_records.values():
                    status = collector.publication_status(store_stamp.isoformat())
                    if status != 'in_period':
                        collector.record_passage_window(APP_STORE_URL, status, store_unit['text'], [store_unit['key']])
            except (ValueError, KeyError, TypeError, OSError) as error:
                store_attempt = (None, {}, f'Unverified App Store version history: {error}')
        response, store_records, error = store_attempt
        if error:
            history['app_store_error'] = error
            if not backlog:
                collector.problem(APP_STORE_URL, error)
        entry = store_records.get(version)
        if entry is None:
            return False
        stamp, unit = entry
        # Store publication and GitHub Release publication are independent clocks.
        # The Store parser verifies the product, version, date and visible text.
        if archived is not None:
            # A Store summary cannot silently replace a known, different Mozilla note.
            # Do not let a substring or a different summary stand in for that note.
            notes = archived['notes']
            if (stamp.date().isoformat() != archived['release_date'] or len(notes) > 1
                    or notes and (notes[0].get('progressive_rollout') is True
                                  or ' '.join(notes[0]['note'].split()) != unit['text'].removeprefix('- '))):
                return False
        published = stamp.isoformat()
        status = collector.publication_status(published)
        if status == 'in_period':
            collector.emit(APP_STORE_URL, response, dict(unit), date=stamp.date().isoformat(),
                           date_evidence=published, version=version, window_anchors=[unit['key']])
        history['app_store_versions'].append(version)
        return True

    start_day = date.fromisoformat(policy_day(collector.window_start) if collector.window_start else collector.since)
    end_day = date.fromisoformat(policy_day(collector.cutoff))
    previous = {(r['evidence']['url'], r['item_key']): r for r in collector.previous}
    for version, row in records.items():
        url = detail_url(version)
        try:
            notes = checked_notes(collector, row)
            day = row['release_date']
            changed = {key for key, note in notes.items() if collector.publication_status(note['modified']) == 'in_period'}
            empty_change = not notes and collector.publication_status(row['modified']) == 'in_period'
            # A local printed day adjacent to either bound can resolve to a
            # qualifying offset timestamp on the versioned product page.
            printed = date.fromisoformat(day)
            if (printed > end_day + timedelta(days=1)
                    or printed < start_day - timedelta(days=1) and not (changed or empty_change)):
                collector.exclude_document(url, day)
                continue
            if not collector.budget(url, 'documents'):
                break
            collector.state['documents'] += 1
            try:
                response = collector.get(url)
            except HTTPError as error:
                if (error.code in (404, 410) and version in shipped
                        and shipped[version] <= instant(collector.cutoff) and from_store(version, row)):
                    collector.document_done(url)
                    continue
                raise
            publication, body = document_metadata(response, version, day, collector.cutoff)
            status = collector.publication_status(publication)
            eligible = set(notes) if status == 'in_period' else changed
            if status == 'after_cutoff' or not (eligible or not notes and (status == 'in_period' or empty_change)):
                collector.exclude_document(url, publication)
                collector.document_done(url)
                continue
            units = document_units(body, notes, window_anchors=bool(collector.window_start and not collector.write_records))
            for unit in units:
                key = unit['key']
                anchors = unit.pop('window_anchors', [key])
                if key in eligible:
                    old = previous.get((url, key))
                    collector.emit(url, response, unit, date=day, date_evidence=publication,
                                   version=old['version'] if old else version,
                                   modified=notes[key]['modified'] if status == 'before_period' else None,
                                   window_anchors=anchors)
                else:
                    # This note was verified against the public record and HTML,
                    # but neither its publication nor its edit is in this window.
                    modified = notes[key]['modified']
                    collector.record_passage_window(url, collector.publication_status(modified), unit['text'], anchors)
                    if collector.fact_review:
                        collector.fact_review.observe(url, response, unit, dates=(publication, modified))
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
    for version, stamp in shipped.items():
        if version in records or stamp > instant(collector.cutoff):
            continue
        # GitHub's source artifact is not the App Store publication date.
        older = collector.publication_status(stamp.isoformat()) == 'before_period'
        backlog = older and collector.collection_mode == 'daily'
        if from_store(version, backlog=backlog):
            continue
        if older:
            history['older_undated_shipping_versions'].append(version)
        else:
            history['missing_shipping_versions'].append(version)
            collector.problem(detail_url(version), 'Shipped Firefox iOS version lacks a verifiable publisher note')
    # Daily completion covers its window, not the entire undated legacy backlog.
    # Recheck these versions on every fresh run; never label them empty or dated.
    if history['older_undated_shipping_versions'] and collector.collection_mode != 'daily':
        collector.problem(SHIPPING, 'Older Firefox iOS shipments lack dated publisher records; note dates unverified')
