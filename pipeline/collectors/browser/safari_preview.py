"""Join Apple's numbered release inventory to WebKit's canonical article evidence."""
import re
from urllib.parse import urljoin

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


def verified_publication(response, version, year, source_id):
    root = Tree(response.text()).root
    canonical = [n.attrs.get('href') for n in root.walk() if n.tag == 'link' and n.attrs.get('rel') == 'canonical']
    body = boundary(root, source_id)
    article = next((n for n in body.ancestors() if n.tag == 'article'), None) if body else None
    titles = [title_version(n.text()) for n in article.children if getattr(n, 'tag', None) == 'h1'] if article else []
    if canonical != [response.url] or titles != [version]:
        raise ValueError('Cannot verify canonical WebKit release identity')
    dates = [publication_value(n.attrs.get('content')) for n in root.walk()
             if n.tag == 'meta' and n.parent.tag == 'head' and n.attrs.get('property') == 'article:published_time']
    dates.extend(publication_value(n.text()) for n in article.walk()
                 if n.has_class('date') and n.parent.has_class('byline'))
    if None in dates:
        raise ValueError('Malformed WebKit publication date')
    for n in root.walk():
        if (n.tag == 'meta' and n.parent.tag == 'head' and n.attrs.get('property') == 'article:modified_time'
                and not publication_value(n.attrs.get('content'))):
            raise ValueError('Malformed WebKit modification date')
    date = reconcile_modification(dates, 'WebKit publication dates')
    if not date or (year and int(date[:4]) != year):
        raise ValueError('Unverified WebKit Technology Preview publication date')
    return date


def collect_safari_preview(collector):
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
    for version in reversed(versions):
        url = urls.get(version)
        if not url:
            target = APPLE_INDEX + '#stp-release-' + str(version)
            collector.problem(target, 'Missing canonical WebKit release URL')
            continue
        # Undated category cards cannot exclude an older article modified in
        # the window. Keep the normal detail-side publication and revision rules.
        if not collector.budget(url, 'documents'):
            return
        state['documents'] += 1
        try:
            response = collector.get(url)
            if response.url != url:
                raise ValueError('Unexpected redirect from canonical WebKit release URL')
            date = verified_publication(response, version, years.get(version), collector.source['source_id'])
            collector.document(url, response=response, publication_date=date, publication_verified=True)
            collector.document_done(url)
        except Exception as error:
            collector.problem(url, str(error))
