"""Join Apple's numbered release inventory to WebKit's canonical article evidence."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin

from pipeline.temporal import instant
from .html import Tree, boundary, next_links, publication_value, reconcile_modification


APPLE_INDEX = 'https://developer.apple.com/documentation/safari-technology-preview-release-notes.md'
CATEGORY = 'https://webkit.org/blog/category/safari-technology-preview/'
TITLE = re.compile(r'(?:Release Notes for )?Safari Technology Preview\s+(\d+|💯)(?=[\s,]|$)', re.I)
APPLE_LINK = re.compile(r'\[Safari Technology Preview (\d+) Release Notes\]'
                        r'\(/documentation/Safari-Technology-Preview-Release-Notes/stp-release-(\d+)\)', re.I)


def apple_versions(text):
    lines = text.splitlines()
    if ('# Safari Technology Preview Release Notes' not in lines
            or '## Topics' not in lines or 'Copyright &copy;' not in text
            or '[Privacy Policy](https://www.apple.com/privacy/privacy-policy)' not in text):
        raise ValueError('Incomplete Apple Technology Preview version index')
    years = {}
    year = None
    for line in lines:
        if line.startswith('### '):
            heading = re.fullmatch(r'### (20\d\d)', line)
            if not heading:
                raise ValueError('Unrecognized Apple Technology Preview year')
            year = int(heading[1])
        elif 'stp-release-' in line or line.startswith('[Safari Technology Preview'):
            match = APPLE_LINK.fullmatch(line.strip())
            if not year or not match or match[1] != match[2] or years.setdefault(int(match[1]), year) != year:
                raise ValueError('Conflicting Apple Technology Preview release entry')
    if not years:
        raise ValueError('No Apple Technology Preview release entries')
    return years


def title_version(title):
    match = TITLE.match(title)
    if not match:
        return None
    # WebKit uses the hundred-points emoji as the title of its 100th release.
    return 100 if match[1] == '💯' else int(match[1])


def category_page(response, page, urls, detail_pattern):
    text = response.text()
    root = Tree(text).root
    posts = [n for n in root.walk() if n.attrs.get('id') == 'posts']
    if len(posts) != 1 or '</html>' not in text.lower():
        raise ValueError('Incomplete WebKit Technology Preview category')
    for node in root.walk():
        if node.tag in ('button', 'a') or node.attrs.get('role') == 'button':
            label = ' '.join((node.text(), node.attrs.get('aria-label', ''), node.attrs.get('class', '')))
            if re.search(r'(?:load|show|view)[ -]+(?:more|older)|더 보기', label, re.I):
                raise ValueError('Unsupported dynamic WebKit category pagination')
    # Validate each raw card before resolving its URL. A link iterator can
    # discard a malformed release and turn incomplete coverage into success.
    cards = [node for node in posts[0].walk() if node.has_class('tile-link')]
    if not cards:
        raise ValueError('WebKit Technology Preview category has no cards')
    for tile in (n for n in posts[0].walk() if n.has_class('tile')):
        if sum(n.has_class('tile-link') for n in tile.walk()) != 1:
            raise ValueError('Incomplete WebKit Technology Preview category card')
    page_versions = set()
    for card in cards:
        href = card.attrs.get('href')
        label = card.text()
        if card.tag != 'a' or not href or not label:
            raise ValueError('Missing WebKit Technology Preview card title or URL')
        url = urljoin(response.url, href)
        version = title_version(label)
        match = detail_pattern.fullmatch(url)
        if not match and version is None:
            # A non-release news tile can share the category. Unknown release
            # layouts must not silently become unrelated news.
            if (re.fullmatch(r'https://webkit\.org/blog/\d+/[a-z0-9-]+/', url)
                    and not re.search(r'release notes|technology preview.*(?:\d|release)', label, re.I)
                    and not re.search(r'technology-preview.*\d|release-notes', url)):
                continue
        if not match or version != int(match[1]) or (version in urls and urls[version] != url):
            raise ValueError('Unverified WebKit Technology Preview card: ' + url)
        urls[version] = url
        page_versions.add(version)
    for n in posts[0].walk():
        if n.tag in ('h1', 'h2', 'h3', 'a'):
            version = title_version(n.text())
            if version is not None and version not in page_versions:
                raise ValueError('WebKit release heading has no matching card URL')
    nav = [n for n in root.walk() if n.tag == 'nav' and n.has_class('pagination')]
    if len(nav) != 1:
        raise ValueError('Missing WebKit category pagination')
    current = [n.text() for n in nav[0].walk() if n.attrs.get('aria-current') == 'page']
    if current != ['Page ' + str(page)]:
        raise ValueError('Wrong WebKit category page number')
    numbered = [page]
    for n in nav[0].walk():
        if n.tag == 'a' and n.has_class('page-numbers'):
            url = n.attrs['href']
            if url == CATEGORY:
                continue
            number = re.fullmatch(re.escape(CATEGORY) + r'page/([1-9]\d*)/', url)
            if not number:
                raise ValueError('Unexpected WebKit category pagination URL')
            numbered.append(int(number[1]))
    return max(numbered), next_links(nav[0], response.url)


def verified_release_dates(response, version, year, source_id):
    root = Tree(response.text()).root
    canonical = [n.attrs.get('href') for n in root.walk() if n.tag == 'link' and n.attrs.get('rel') == 'canonical']
    body = boundary(root, source_id)
    article = next((n for n in body.ancestors() if n.tag == 'article'), None) if body else None
    titles = [title_version(n.text()) for n in article.children if getattr(n, 'tag', None) == 'h1'] if article else []
    if canonical != [response.url] or titles != [version]:
        raise ValueError('Cannot verify canonical WebKit release identity')
    publications, modifications = [], []
    foreign_publication_time = False
    product_path = {body, *body.ancestors()}
    # The linked article determines ownership even when neutral presentation
    # wrappers separate a timestamp from its byline. Exclude linked authors and
    # other articles from both metadata and the surrounding printed date.
    def unrelated(n):
        rel = (n.attrs.get('rel') or '').lower().split()
        return (n.tag in ('aside', 'footer', 'nav', 'li', 'blockquote', 'figure', 'template', 'script', 'style')
                or any(n.has_class(c) for c in ('comment', 'comments', 'author', 'vcard', 'p-author', 'related-posts'))
                or 'author' in rel or (n.tag in ('article', 'section') or 'itemscope' in n.attrs) and n not in product_path)

    # HTML resolves relative permalinks against the first active base href.
    base_href = next((n.attrs['href'] for n in root.walk() if n.tag == 'base' and 'href' in n.attrs
                      and not any(a.tag in ('template', 'noscript') for a in n.ancestors())), '')
    document_base = urljoin(response.url, base_href or '')
    other_contexts = {n for n in article.walk() if unrelated(n)}
    other_links = {n for n in article.walk() if n.tag == 'a' and
                   (not (n.attrs.get('href') or '').strip() or urljoin(document_base, n.attrs['href']) != response.url)}
    excluded_text = {id(n) for n in other_contexts | other_links}
    for node in root.walk():
        head = (node.tag == 'meta' and node.parent.tag == 'head' and node.parent.parent.tag == 'html'
                and node.parent.parent.parent is root)
        fields = {word.lower() for attr in ('property', 'name', 'itemprop')
                  for word in (node.attrs.get(attr) or '').split()}
        published = bool(fields & {'article:published_time', 'datepublished', 'date', 'publication_date'})
        modified = bool(fields & {'article:modified_time', 'datemodified'})
        ambiguous_fields = published and modified
        byline_date = False
        foreign_date = False
        if not head:
            ancestors = list(node.ancestors())
            if article not in ancestors:
                continue
            lineage = [node, *ancestors[:ancestors.index(article)]]
            if any(n in other_contexts for n in lineage):
                continue
            byline = next((n for n in lineage if n.has_class('byline')), None)
            byline_date = byline is not None and body not in lineage and (node.tag == 'time' or node.has_class('date'))
            if byline_date:
                classes = {c for n in lineage[:lineage.index(byline) + 1] for c in (n.attrs.get('class') or '').split()}
                reports_publication = bool(classes & {'published', 'dt-published'})
                reports_update = bool(classes & {'updated', 'modified', 'dt-updated'})
                if not (reports_publication and reports_update):
                    ambiguous_fields |= reports_publication and modified or reports_update and published
                published |= reports_publication
                modified |= reports_update
                if not modified:
                    published = True
            if any(n in other_links for n in lineage):
                if byline is None or body in lineage or not published:
                    continue
                foreign_date = True
        if ambiguous_fields and not foreign_date:
            raise ValueError('Conflicting WebKit date field roles')
        if not (published or modified):
            continue
        values = [publication_value(node.attrs[key]) for key in ('datetime', 'content') if key in node.attrs]
        # A surrounding date label must not repeat a nested clock as a
        # different role (e.g. publication outside, modification inside).
        ignored = excluded_text
        if byline_date and node.tag != 'time':
            ignored = excluded_text | {id(n) for n in node.walk() if n is not node and n.tag == 'time'}
        if foreign_date and id(node) in ignored:
            ignored = ignored - {id(node)}
        label = node.text(ignored)
        if label and (not values or byline_date or node.tag == 'time'):
            values.append(publication_value(label))
        if foreign_date:
            # Use the same text/content/datetime precision as an owned date.
            # Without a verified publication instant this link prevents a
            # lower-precision day from settling a cutoff boundary.
            foreign_publication_time |= any(not value or len(value) > 10 for value in values)
            continue
        if not values and byline_date and node.tag != 'time' and not label:
            # A date wrapper can contain only a nested time or foreign link.
            continue
        if not values or not all(values):
            raise ValueError('Malformed WebKit publication or modification date')
        if published:
            publications.extend(values)
        if modified:
            modifications.extend(values)
    date = reconcile_modification(publications, 'WebKit publication dates')
    if foreign_publication_time and (not date or len(date) == 10):
        raise ValueError('Cannot attribute exact WebKit byline publication time to this release')
    if not date or (year and int(date[:4]) != year):
        raise ValueError('Unverified WebKit Technology Preview publication date')
    return date, reconcile_modification(modifications, 'WebKit modification dates')


RELEASE_ONE_PATH = '/documentation/safari-technology-preview-release-notes/stp-release-1'
RELEASE_ONE_MARKDOWN = 'https://developer.apple.com' + RELEASE_ONE_PATH + '.md'
RELEASE_ONE_DOCC = 'https://developer.apple.com/tutorials/data' + RELEASE_ONE_PATH + '.json'
RELEASE_ONE_TITLE = 'Safari Technology Preview 1 Release Notes'
RELEASE_ONE_BUNDLE = 'Safari-Technology-Preview-Release-Notes'


def release_one_markdown(response):
    match = re.fullmatch(r'<!--\s*(.*?)\s*-->\s*(.*?)\n---\s*\nCopyright &copy; \d{4} Apple Inc\. '
                         r'All rights reserved\. \| \[Terms of Use\]\(https://www.apple.com/legal/internet-services/terms/site.html\) '
                         r'\| \[Privacy Policy\]\(https://www.apple.com/privacy/privacy-policy\)\s*', response.text(), re.S)
    if not match:
        raise ValueError('Unrecognized Apple release-1 Markdown')
    meta = json.loads(match[1])
    if (meta.get('title') != RELEASE_ONE_TITLE or meta.get('documentType') != 'article' or meta.get('role') != 'article'
            or meta.get('framework') != 'Safari Technology Preview Release Notes'
            or meta.get('identifier') != RELEASE_ONE_PATH.replace('safari-technology-preview-release-notes', RELEASE_ONE_BUNDLE)):
        raise ValueError('Wrong Apple release-1 Markdown identity')
    return [line.strip() for line in match[2].splitlines() if line.strip()]


def release_one_docc(response):
    data = json.loads(response.text())
    identifier = 'doc://com.apple.' + RELEASE_ONE_BUNDLE + RELEASE_ONE_PATH.replace(
        'safari-technology-preview-release-notes', RELEASE_ONE_BUNDLE)
    if (data['identifier']['url'] != identifier or data['metadata']['title'] != RELEASE_ONE_TITLE
            or data['metadata']['role'] != 'article' or data['kind'] != 'article'):
        raise ValueError('Wrong Apple release-1 DocC identity')

    def inline(nodes):
        parts = []
        for node in nodes:
            if node['type'] == 'text':
                parts.append(node['text'])
            elif node['type'] == 'codeVoice':
                parts.append('`' + node['code'] + '`')
            elif node['type'] == 'reference':
                ref = data['references'][node['identifier']]
                parts.append('[' + ref['title'] + '](' + ref['url'] + ')')
            else:
                raise ValueError('Unsupported Apple release-1 inline content')
        line = ''.join(parts)
        if not line.strip() or '\n' in line:
            raise ValueError('Invalid Apple release-1 paragraph')
        return line

    lines = ['# ' + RELEASE_ONE_TITLE, inline(data['abstract'])]
    section, = data['primaryContentSections']
    if section['kind'] != 'content' or data.get('sections'):
        raise ValueError('Unrecognized Apple release-1 sections')
    for node in section['content']:
        if node['type'] == 'heading' and node['level'] in (2, 3):
            lines.append('#' * node['level'] + ' ' + node['text'])
        elif node['type'] == 'paragraph':
            lines.append(inline(node['inlineContent']))
        elif node['type'] == 'unorderedList' and node['items']:
            for item in node['items']:
                paragraph, = item['content']
                if paragraph['type'] != 'paragraph':
                    raise ValueError('Unsupported Apple release-1 product unit')
                lines.append('- ' + inline(paragraph['inlineContent']))
        else:
            raise ValueError('Unsupported Apple release-1 content')
    # Release 1 has five named product sections. Do not mistake two identically
    # truncated representations for a complete release.
    headings = ('Browser Differences', 'JavaScript Improvements', 'HTML Enhancements', 'Web Inspector Changes', 'Behavior Changes')
    groups = [line[4:] for line in lines if line.startswith('### ')]
    if '## Overview' not in lines or tuple(groups) != headings:
        raise ValueError('Missing substantive Apple release-1 product sections')
    for i, line in enumerate(lines):
        if line.startswith('### ') and (i + 1 == len(lines) or not lines[i + 1].startswith('- ')):
            raise ValueError('Empty Apple release-1 product section')
    return lines


PROOF_HEADERS = {'date', 'age', 'cache-control', 'expires', 'cache-status', 'warning', 'etag', 'last-modified',
                 'content-type', 'content-encoding', 'content-length', 'content-range', 'vary'}


def http_date(value):
    result = parsedate_to_datetime(value or '')
    if result.tzinfo is None or format_datetime(result, usegmt=True) != value:
        raise ValueError('Invalid Apple release-1 HTTP date')
    return result


def verify_freshness(headers, observed, cutoff):
    issued = http_date(headers.get('date'))
    raw_age = headers.get('age', '0')
    if not re.fullmatch(r'[0-9]+', raw_age):
        raise ValueError('Invalid Apple release-1 HTTP Age')
    age = max(int(raw_age), (observed - issued).total_seconds())
    if issued > observed or age > (observed - cutoff).total_seconds():
        raise ValueError('Apple release-1 response does not establish freshness at cutoff')
    if (re.search(r'(?:^|,)\s*11[0-3]\b', headers.get('warning', ''))
            or re.search(r'\b(?:fwd\s*=\s*stale\b|ttl\s*=\s*-\d+)', headers.get('cache-status', ''), re.I)):
        raise ValueError('Stale Apple release-1 HTTP response')

    # Compare both the age reported by the cache and the apparent age at the
    # client. An age equal to the freshness lifetime is already stale.
    lifetimes = {}
    for directive in headers.get('cache-control', '').lower().split(','):
        name, _, value = directive.strip().partition('=')
        if name.strip() in ('max-age', 's-maxage'):
            name = name.strip()
            if name in lifetimes or not re.fullmatch(r'[0-9]+', value.strip()):
                raise ValueError('Ambiguous Apple release-1 cache lifetime')
            lifetimes[name] = int(value.strip())
    if 'expires' in headers:
        lifetimes['expires'] = (http_date(headers['expires']) - issued).total_seconds()
    if not lifetimes or age >= min(lifetimes.values()):
        raise ValueError('Insufficient Apple release-1 cache freshness')


def apple_proof_request(collector, url, since, journal):
    attempts = collector.state['preview_inventory'].setdefault('release_one_requests', [])
    event = {'url': url, 'if_modified_since': since, 'http_attempts': 0, 'request_cache_control': 'no-cache'}
    attempts.append(event)
    progress = collector.progress['apple_release_one']

    def before_send():
        # Charge actual transport attempts, including retries after HTTP 429.
        if not collector.budget(url, 'documents'):
            raise ValueError('Apple release-1 proof request exceeds source budget')
        collector.state['documents'] += 1
        event['http_attempts'] += 1
        progress['http_attempts'] = progress.get('http_attempts', 0) + 1
        collector.write_progress()

    response = collector.transport(url, direct=True, if_modified_since=since, before_send=before_send)
    if not event['http_attempts']:
        raise ValueError('Unaccounted Apple release-1 HTTP request')
    headers = {}
    for name, value in response.headers.items():
        name = name.lower()
        if name in PROOF_HEADERS:
            if name in headers:
                raise ValueError('Duplicate Apple release-1 HTTP header: ' + name)
            headers[name] = value
    facts = dict(url=url, if_modified_since=since, final_url=response.url, status=response.status, sha256=collector.cache_body(response.body, verify=True),
                 etag=headers.get('etag'), last_modified=headers.get('last-modified'), content_type=headers.get('content-type'),
                 content_encoding=headers.get('content-encoding'), vary=headers.get('vary'))
    event.update(facts, observed_at=response.observed_at or datetime.now(timezone.utc).isoformat(),
                 request_cache_control='no-cache', response_headers=headers)
    verify_freshness(headers, instant(event['observed_at']), instant(collector.cutoff))
    key = url + ' ' + (since or 'full')
    prior = journal.get(key)
    if prior and {k: prior.get(k) for k in facts} != facts:
        raise ValueError('Apple release-1 proof changed on resume; start a fresh run')
    journal[key] = dict(event)
    collector.write_progress()
    collector.check_time()
    if (response.url != url or instant(event['observed_at']) < instant(collector.cutoff)
            or headers.get('content-encoding', 'identity').lower() != 'identity'
            or any(name.strip().lower() not in ('accept', 'accept-encoding', 'user-agent')
                   for name in headers.get('vary', '').split(',') if name.strip())):
        raise ValueError('Unexpected Apple release-1 representation')
    return response, facts


def exclude_old_apple_release_one(collector):
    start = instant(collector.window_start).astimezone(timezone.utc)
    before = start.replace(microsecond=0)
    if before == start:
        before -= timedelta(seconds=1)
    since = format_datetime(before, usegmt=True)
    journal = collector.progress.setdefault('apple_release_one', {}).setdefault('requests', {})
    for prior in journal.values():
        checksum = prior['sha256']
        if (not re.fullmatch(r'[a-f0-9]{64}', checksum)
                or hashlib.sha256((collector.private_dir / 'cache' / checksum).read_bytes()).hexdigest() != checksum):
            raise ValueError('Apple release-1 cached proof checksum mismatch')
    documents = []
    for url, media, parse in ((RELEASE_ONE_MARKDOWN, 'text/markdown', release_one_markdown),
                              (RELEASE_ONE_DOCC, 'application/json', release_one_docc)):
        response, facts = apple_proof_request(collector, url, None, journal)
        if (response.status != 200 or (facts['content_type'] or '').split(';')[0].lower() != media
                or not re.fullmatch(r'"[\x21\x23-\x7e\x80-\xff]+"', facts['etag'] or '')):
            raise ValueError('Unverified Apple release-1 full response or ETag')
        modified = http_date(facts['last_modified'])
        if modified > before:
            raise ValueError('Apple release-1 representation not verified before the window')
        documents.append((url, facts, parse(response)))
    if documents[0][2] != documents[1][2]:
        raise ValueError('Apple release-1 product content disagrees between Markdown and DocC')
    for url, full, _ in documents:
        response, facts = apple_proof_request(collector, url, since, journal)
        if (response.status != 304 or response.body or facts['etag'] != full['etag']
                or any(facts[k] is not None and facts[k] != full[k] for k in ('last_modified', 'content_type', 'vary'))):
            raise ValueError('Apple release-1 did not confirm the same representation before the window')
    semantic = hashlib.sha256(json.dumps(documents[0][2], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    decision = dict(version=1, cutoff=collector.cutoff, window_start=collector.window_start,
                    if_modified_since=since, product_text_sha256=semantic)
    collector.progress['apple_release_one']['verified'] = decision
    collector.write_progress()
    collector.state['preview_inventory']['release_one_exclusion'] = decision
    collector.state['excluded_by_date'].append(RELEASE_ONE_MARKDOWN)


def stop_webkit_requests(collector, error, url, pending):
    code = getattr(error, 'code', None)
    headers = {k.lower(): v for k, v in (getattr(error, 'headers', None) or {}).items()}
    value = headers.get('retry-after', '').strip()
    retry_at = None
    if value.isdigit():
        try:
            retry_at = datetime.now(timezone.utc) + timedelta(seconds=int(value))
        except (ValueError, OverflowError):
            retry_at = datetime.max.replace(tzinfo=timezone.utc)
    elif value:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is not None:
                retry_at = date.astimezone(timezone.utc)
        except (ValueError, TypeError, OverflowError):
            pass
    if code == 429 and retry_at is None:
        retry_at = datetime.now(timezone.utc) + timedelta(seconds=30)
    if not (code in (403, 429, 503) or retry_at or isinstance(error, TimeoutError)
            or isinstance(getattr(error, 'reason', None), TimeoutError)):
        return False
    collector.state['pending'] = list(pending)
    if retry_at:
        collector.progress['webkit_retry_after'] = dict(url=url, until=retry_at.isoformat(), pending=list(pending))
        collector.write_progress()
    return True


def collect_safari_preview(collector):
    wait = collector.progress.get('webkit_retry_after')
    if wait and datetime.now(timezone.utc) < instant(wait['until']):
        collector.state['pending'] = list(wait['pending'])
        collector.problem(wait['url'], 'WebKit requested retry after ' + wait['until'])
        return
    if wait:
        del collector.progress['webkit_retry_after']
        collector.write_progress()
    previous_proof = collector.progress.get('apple_release_one', {})
    if previous_proof.pop('verified', None):
        collector.write_progress()
    detail_pattern = re.compile(collector.source['discovery']['include_url_pattern'])
    urls = {}
    state = collector.state
    evidence = state['preview_inventory'] = {}

    def index(url):
        if not collector.budget(url, 'pages'):
            return None
        state['pages'] += 1
        try:
            response = collector.get(url, refresh=True)
            if response.url != url:
                raise ValueError('Unexpected Technology Preview index redirect')
            return response
        except Exception as error:
            collector.problem(url, str(error))
            if url.startswith(CATEGORY):
                stop_webkit_requests(collector, error, url, [url])
            return None

    apple = index(APPLE_INDEX)
    if not apple:
        return
    try:
        years = apple_versions(apple.text())
    except ValueError as error:
        collector.problem(APPLE_INDEX, str(error))
        return
    evidence['apple_versions'] = len(years)
    page = 1
    last_page = None
    while True:
        url = CATEGORY if page == 1 else CATEGORY + 'page/%d/' % page
        response = index(url)
        if not response:
            return
        observed_last, next_urls = category_page(response, page, urls, detail_pattern)
        if last_page is not None and observed_last != last_page:
            raise ValueError('WebKit category page count changed')
        last_page = observed_last
        expected_next = [CATEGORY + 'page/%d/' % (page + 1)] if page < last_page else []
        if next_urls != expected_next:
            raise ValueError('Incomplete WebKit Technology Preview pagination')
        if not next_urls:
            break
        page += 1
    evidence['category_pages'] = page
    evidence['category_versions'] = len(urls)
    categories = dict(urls)
    for record in collector.previous:
        url = record['evidence']['url']
        match = detail_pattern.fullmatch(url)
        if not match:
            raise ValueError('Unknown retained WebKit Technology Preview release URL')
        version = int(match[1])
        if urls.get(version) and urls[version] != url:
            raise ValueError('Canonical WebKit release URL differs from retained evidence')
        urls[version] = url

    # The category and Apple inventory each omit releases. A missing number
    # in their union (including retained URLs) has no verified dates or identity.
    versions = sorted(set(years) | set(urls))
    prior = 0
    for version in versions:
        if version != prior + 1:
            collector.problem(APPLE_INDEX, f'Missing Technology Preview releases {prior + 1}–{version - 1}')
        prior = version
    evidence['historical_fallbacks'] = sorted(v for v in urls if urls[v] and not categories.get(v))
    state['pagination_exhausted'] = True
    versions.reverse()
    targets = [urls.get(v) or APPLE_INDEX + '#stp-release-' + str(v) for v in versions]
    for position, version in enumerate(versions):
        url = urls.get(version)
        if not url:
            target = APPLE_INDEX + '#stp-release-' + str(version)
            if (version == 1 and collector.collection_mode == 'daily' and years.get(1) == 2016
                    and int(collector.window_start[:4]) > 2016 and not state['errors']):
                try:
                    exclude_old_apple_release_one(collector)
                except Exception as error:
                    collector.problem(target, str(error))
            else:
                collector.problem(target, 'Missing canonical WebKit release URL')
            continue
        # Undated category cards cannot exclude an older article modified in
        # the window. Keep the normal detail-side publication and revision rules.
        try:
            if not collector.budget(url, 'documents'):
                state['pending'] = targets[position:]
                return
            state['documents'] += 1
            response = collector.get(url)
            if response.url != url:
                raise ValueError('Unexpected redirect from canonical WebKit release URL')
            date, modified = verified_release_dates(response, version, years.get(version), collector.source['source_id'])
            collector.document(url, response=response, publication_date=date, publication_verified=True,
                               modified=modified if collector.window_start else None)
            collector.document_done(url)
        except Exception as error:
            collector.problem(url, str(error))
            if stop_webkit_requests(collector, error, url, targets[position:]):
                return
