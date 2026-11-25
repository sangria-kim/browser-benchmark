"""Small DOM reader with explicit source content boundaries. No script execution."""
import re
import hashlib
import json
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urldefrag, urlsplit
from datetime import datetime

from pipeline.temporal import SEOUL, instant

VOID = {'br', 'img', 'meta', 'link', 'hr', 'input', 'source', 'wbr', 'area', 'base', 'embed'}
SKIP = {'script', 'style', 'nav', 'footer', 'form', 'noscript'}


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self, excluded=()):
        if self.tag in SKIP or id(self) in excluded:
            return ''
        return ' '.join(' '.join(c.text(excluded) if isinstance(c, Node) else c for c in self.children).split())

    def has_class(self, name):
        return name in (self.attrs.get('class') or '').split()

    def ancestors(self):
        node = self.parent
        while node:
            yield node
            node = node.parent


class UnresolvedChromeSignoff(Node):
    pass


class Tree(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = Node('document')
        self.stack = [self.root]
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def date_value(value):
    match = re.search(r'\b(20\d{2}-\d{2}-\d{2})(?!\d)', value or '')
    if match:
        try:
            return datetime.strptime(match[1], '%Y-%m-%d').date().isoformat()
        except ValueError:
            pass
    for expression, formats in [
            (r'([A-Z][a-z]+ \d{1,2}, 20\d{2})', ('%B %d, %Y', '%b %d, %Y')),
            (r'(\d{1,2} [A-Z][a-z]+ 20\d{2})', ('%d %B %Y', '%d %b %Y'))]:
        match = re.search(expression, value or '')
        if match:
            for format in formats:
                try:
                    return datetime.strptime(match[1], format).date().isoformat()
                except ValueError:
                    pass
    return None


def publication_value(value):
    """Keep an explicit timestamp intact, or extract a printed calendar date."""
    value = (value or '').strip()
    if re.match(r'^20\d{2}-\d{2}-\d{2}[Tt ]\d{2}:', value):
        if re.fullmatch(r'20\d{2}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})', value):
            try:
                instant(value)
                return value
            except ValueError:
                pass
        # A timestamp with no usable timezone does not date an item.
        return None
    return date_value(value)


def date_owner(node):
    """Find the nearest independently identified publisher article."""
    return next((parent for parent in (node, *node.ancestors()) if parent.tag == 'article'
                 or parent.has_class('post') or parent.has_class('post-outer')
                 or any(kind in parent.attrs.get('itemtype', '') for kind in ('Article', 'BlogPosting'))), None)


def belongs_to_document(node, body):
    ancestors = list(node.ancestors())
    if any(a.tag in ('aside', 'footer', 'nav') or a.has_class('comments') or a.has_class('comment')
           or 'Comment' in a.attrs.get('itemtype', '') for a in ancestors):
        return False
    owner = date_owner(node)
    return owner is None or body is not None and owner is date_owner(body)


def firefox_advisory_summaries(body):
    for node in body.walk():
        # Each subitem can also have a dl.summary. Mozilla puts only the
        # document summary directly inside its advisory container.
        if node.tag != 'dl' or not node.has_class('summary') or not node.parent.has_class('advisory'):
            continue
        article = date_owner(node)
        if (article is None or article.tag != 'article' or date_owner(article.parent) is not None
                or (article is not body and body not in article.ancestors())):
            continue
        if belongs_to_document(node, article) and not any(a.tag == 'header' for a in node.ancestors()):
            yield node


def published(tree, source_id=None, *, product_body=None):
    nodes = tree.walk()
    if source_id == 'firefox-security' and product_body is not None:
        # Mozilla's unit boundary wraps its primary article. Only the article's
        # advisory summary owns the Announced field; keep the unit boundary intact.
        summaries = list(firefox_advisory_summaries(product_body))
        if len(summaries) > 1:
            return None
        if summaries:
            product_body = summaries[0]
            nodes = [n for n in product_body.children
                     if isinstance(n, Node) and n.tag == 'dt' and n.text() == 'Announced']
            if len(nodes) != 1:
                return None
        else:
            nodes = (n for n in tree.walk() if not any(a.tag == 'header' for a in n.ancestors()))
    for n in nodes:
        if product_body is not None and not belongs_to_document(n, product_body):
            continue
        if n.attrs.get('itemprop') == 'dateModified':
            continue
        if n.tag == 'meta' and n.attrs.get('property', n.attrs.get('name')) in (
                'article:published_time', 'date', 'datePublished', 'publication_date'):
            found = publication_value(n.attrs.get('content'))
            if found:
                return found
        if source_id == 'firefox-security' and n.tag == 'dt' and n.text() == 'Announced':
            siblings = n.parent.children
            following = next((v for v in siblings[siblings.index(n)+1:] if isinstance(v, Node)), None)
            if following and following.tag == 'dd':
                return publication_value(following.text())
        if source_id == 'safari-technology-preview' and n.has_class('date'):
            found = publication_value(n.text())
            if found:
                return found
        if n.tag == 'time' or n.has_class('c-release-date'):
            found = publication_value(n.attrs.get('datetime')) or publication_value(n.text())
            if found:
                return found
        if (source_id == 'chrome-releases' and n.has_class('publishdate') and
                n.attrs.get('itemprop') == 'datePublished' and
                any(a.has_class('post-header') for a in n.ancestors())):
            found = publication_value(n.text())
            if found:
                return found
    return None


def reconcile_modification(values, context):
    """Agree on a single publication day or instant and retain the best precision."""
    days = {value for value in values if value and len(value) == 10}
    timestamps = [value for value in values if value and len(value) > 10]
    instants = {instant(value) for value in timestamps}
    if len(days) > 1 or len(instants) > 1:
        raise ValueError('Conflicting ' + context)
    if timestamps and days:
        # A printed day may use the source offset or the KST comparison calendar.
        possible_days = {value[:10] for value in timestamps}
        possible_days.add(instant(timestamps[0]).astimezone(SEOUL).date().isoformat())
        if not days <= possible_days:
            raise ValueError('Conflicting ' + context)
    return timestamps[0] if timestamps else next(iter(days), None)


def modification(tree, product_body=None, *, page_metadata_only=False):
    """Use explicit publisher modification fields; generic <time> can mean publication."""
    values = []
    for node in tree.walk():
        if page_metadata_only and (node.tag != 'meta' or node.parent.tag not in ('head', 'document')):
            continue
        if (node.attrs.get('property') != 'article:modified_time'
                and node.attrs.get('itemprop') != 'dateModified'):
            continue
        if not belongs_to_document(node, product_body if product_body is not None else tree):
            continue
        value = publication_value(node.attrs.get('content') or node.attrs.get('datetime') or node.text())
        if value:
            values.append(value)
    return reconcile_modification(values, 'document modification dates')


def chrome_post_header(link):
    """A date on a Blogger post header belongs only to that post's permalink."""
    ancestors = list(link.ancestors())
    header = next((node for node in ancestors if node.has_class('post-header')), None)
    if header is not None:
        return header
    if not any(node.has_class('post-title') for node in ancestors):
        return None
    post = next((node for node in ancestors if node.has_class('post') or node.has_class('post-outer')), None)
    headers = [node for node in post.walk() if node.has_class('post-header')] if post else []
    return headers[0] if len(headers) == 1 else None


# Chrome Releases uses a shared Blogger profile. The profile identifies the
# publisher; the exact terminal byline AND organization identify the signature.
# SHA-256(byline + newline + organization) keeps names out of product data.
CHROME_BYLINES = {
    # Chrome release team and release managers, confirmed by the publisher:
    # https://developer.chrome.com/blog/chrome-updates
    # https://groups.google.com/a/chromium.org/g/chromium-dev/c/_lQnOytt6-0
    '54ec03626e5944437d9581b7591c38ac18b91ca98eb9b97be02e0e607c306210',
    'b3d0566429985ce0d830337725b01cc74dcd30eaac586259cc5401efa8ca2c62',
    'a3652cc2cae1578adefe85ec71ff5d2b3a3c142ba15ebf4497b8e624b8307cd1',
    '589546fe23ed1e6eb5d2c4ea4eba3121e738c95cb082770ad46669f67d1a6ca8',
    '7a0278ff9e86653af7198d6bc0ec8f3bd57b1eb8d9858aa7e949196d6be055d4',
}


# These two ChromeOS signatures recur in the publisher's archive, but the
# shared profile does not identify the signer. Bind this narrower review to
# the exact inert article template. A page footer can change independently.
# https://chromereleases.googleblog.com/2025/11/
# https://chromereleases.googleblog.com/2026/07/long-term-support-channel-update-for.html
REVIEWED_CHROME_TEMPLATES = {
    'https://chromereleases.googleblog.com/2026/10/beta-channel-update-for-chromeos_0669100502.html':
        'd2c7b5c6bf08b688a370379fd8186234b724b7d52d35340363c25f88fb7280ff',
    'https://chromereleases.googleblog.com/2026/10/dev-channel-update-for-chromeos_0448562495.html':
        '6500b52b994e67d38d550a92fa50d04ba6cb31aa3b800d693aacd21cd17b2af4',
    'https://chromereleases.googleblog.com/2026/10/early-stable-update-for-desktop_01255863767.html':
        'd4414328a55f6777ca578462df7eeadf2038021b6efb69f5e57a1ea0b57a429d',
    'https://chromereleases.googleblog.com/2026/10/long-term-support-channel-update-for_0661547040.html':
        '79c1b1575a2f8635f931d0345b0dde1de2be210df010848f55b7c29262dc5951',
    'https://chromereleases.googleblog.com/2026/10/stable-channel-update-for-desktop_0562499947.html':
        '257e6dc64ad28e78984f0e6320ee5455414abdc896e4d18ddab7b0c84433fb8a',
    'https://chromereleases.googleblog.com/2026/11/beta-channel-update-for-chromeos.html':
        '72f1fc7a630046761383732f8569c94e6f21c03efece221363ed1e48e7a161c2',
    'https://chromereleases.googleblog.com/2026/11/beta-channel-update-for-chromeos_01835406967.html':
        'd6f77237d38bf16ab61231387decf14b12242c7130b39bfd44d88cb51e1f4268',
    'https://chromereleases.googleblog.com/2026/11/long-term-support-channel-update-for.html':
        '7f79a3b3e2bf1a98751706f9e0fce79b7f1ea2a8c1c2760b7ff7f6a0a5ed4a5a',
    'https://chromereleases.googleblog.com/2026/11/stable-channel-update-for-chromeos_01089491269.html':
        '40b94389aabfe379499f6af4421ede374c8ac9d983b1c8b0e4d7d8c840c72724',
    'https://chromereleases.googleblog.com/2026/11/stable-channel-update-for-chromeos_01679457768.html':
        'c39a8b2dd45a729d9450dc8951219511f8a5eaaa621ef11e69e02bbab6838d22',
}


def chrome_byline_matches(author, text, publisher, reviewed_template):
    if (author is None or author.tag != 'span' or 'itemscope' not in author.attrs or
            author.attrs.get('itemtype') not in {'http://schema.org/Person', 'https://schema.org/Person'}):
        return False
    # Only direct fields of the terminal Person card describe this author.
    fields = [child for child in author.children if isinstance(child, Node) or child.strip()]
    if not all(isinstance(child, Node) and child.tag == 'meta' for child in fields):
        return False
    names = [field.attrs.get('content') for field in fields if field.attrs.get('itemprop') == 'name']
    if names:
        return names == [text]
    urls = [field.attrs.get('content') for field in fields if field.attrs.get('itemprop') == 'url']
    signature = hashlib.sha256((text + '\n' + publisher).encode()).hexdigest()
    if urls != ['https://plus.google.com/116899029375914044550']:
        return False
    return signature in CHROME_BYLINES or reviewed_template


def inline_product_container(node):
    inline_tags = {'a', 'span', 'strong', 'b', 'em', 'i', 'u', 'code', 'br', 'small', 'sup', 'sub', 'font'}
    return node.tag in {'div', 'span'} and all(c is node or c.tag in inline_tags for c in node.walk())


def anchored_chrome_line(line):
    # blocks() can also emit an ordinary node's direct text with that node's
    # own ID. A wrapper around several paragraphs does not own their units.
    for node, _, text in line:
        if text.strip() and any(a.attrs.get('id') and
                                (a is node or a.tag == 'p' or inline_product_container(a))
                                for a in (node, *node.ancestors())):
            return True
    return False


def remove_chrome_post_signoff(fragment, author, reviewed_template, reviewed_signoffs):
    # Blogger places the unmarked byline on its own line before the publisher
    # label, in adjacent paragraphs or on opposite sides of a line break.
    lines = [[]]

    def visit(node):
        if node.tag in SKIP:
            return
        separates_lines = node.tag in {'p', 'div', 'br', 'li'}
        if separates_lines and lines[-1]:
            lines.append([])
        for index, child in enumerate(node.children):
            if isinstance(child, Node):
                visit(child)
            else:
                lines[-1].append((node, index, child))
        if separates_lines and lines[-1]:
            lines.append([])

    visit(fragment)
    lines = [line for line in lines if any(text.strip() for _, _, text in line)]
    if len(lines) < 2:
        return
    # Inline elements do not introduce spaces: adjacent fragments must not
    # turn an unrecognized token into an audited signature.
    publisher = ' '.join(''.join(text for _, _, text in lines[-1]).split())
    if publisher not in {'Google Chrome', 'Google ChromeOS', 'Google Chrome OS'}:
        return
    # A structured product unit (for example a list item or linked feature)
    # keeps its own text and identity even when it uses a known byline string.
    plain = {'document', 'p', 'div', 'span', 'b', 'strong', 'i', 'em', 'font', 'u', 'small'}
    publisher_nodes = {a for node, _, part in lines[-1] if part.strip() for a in (node, *node.ancestors())}
    if anchored_chrome_line(lines[-1]) or any(a.tag not in plain and a.tag != 'a' for a in publisher_nodes):
        return
    signature_line = lines[-2]
    signature_nodes = {a for node, _, part in signature_line if part.strip() for a in (node, *node.ancestors())}
    product_link = any(a.tag == 'a' and a.attrs.get('href') not in {
        'https://www.google.com/chrome', 'https://www.google.com/chrome/',
    } for a in publisher_nodes)
    if product_link:
        author = None
    # A separate product link owns its normal row. A combined, unanchored
    # signoff + link in the same paragraph stays private pending review.
    shares_block = any(a.tag == 'p' or inline_product_container(a) for a in publisher_nodes & signature_nodes)
    anchored = anchored_chrome_line(signature_line)
    if not product_link or (shares_block and not anchored):
        for node, index, _ in lines[-1]:
            node.children[index] = ''
    if anchored or any(a.tag not in plain for a in signature_nodes):
        return
    text = ''.join(part for _, _, part in signature_line).strip()
    confirmed = (hashlib.sha256(text.encode()).hexdigest() in reviewed_signoffs
                 or chrome_byline_matches(author, text, publisher, reviewed_template))
    if len(text) > 64 and not confirmed:
        return
    for node, index, _ in signature_line:
        node.children[index] = ''
    # Raw ambiguous content remains in the private response cache. Its stable
    # unresolved key prevents completion; a confirmed credit is not a feature.
    if not confirmed:
        fragment.children.append(UnresolvedChromeSignoff('document', parent=fragment))


def expand_chrome_post_templates(body, reviewed_signoffs, document_url):
    # Chrome Releases stores the article markup in an inert Blogger template.
    # Its noscript copy remains excluded by SKIP.
    for content in body.children:
        if not isinstance(content, Node) or not content.has_class('post-content'):
            continue
        for index, child in enumerate(content.children):
            if (not isinstance(child, Node) or child.tag != 'script' or
                    child.attrs.get('type') != 'text/template' or 'src' in child.attrs):
                continue
            template = ''.join(child.children)
            fragment = Tree(template).root
            children = [part for part in fragment.children if isinstance(part, Node) or part.strip()]
            authors = [n for n in fragment.walk() if n.attrs.get('itemprop') == 'author']
            template_hash = hashlib.sha256(template.encode()).hexdigest()
            reviewed_template = REVIEWED_CHROME_TEMPLATES.get(document_url) == template_hash
            author = None
            if authors and authors[-1] is children[-1]:
                if len(authors) == 1 or reviewed_template:
                    author = authors[-1]
            for node in list(fragment.walk())[1:]:
                if node.attrs.get('itemprop') == 'author' or node.tag == 'header':
                    node.parent.children.remove(node)
            remove_chrome_post_signoff(fragment, author, reviewed_template, reviewed_signoffs if authors else ())
            fragment.parent = content
            content.children[index] = fragment


def boundary(tree, source_id, reviewed_signoffs=(), *, document_url=None):
    nodes = list(tree.walk())
    # Select the publisher's product body, never navigation, replies or author cards.
    selectors = {
        'chrome-releases': [('class', 'post-body')],
        'chrome-enterprise': [('class', 'article-content'), ('class', 'answer'), ('class', 'article-content-container')],
        'chrome-blog': [('class', 'article-body'), ('class', 'uni-article__body'), ('class', 'article-container')],
        'firefox': [('class', 'c-release-notes')],
        'firefox-security': [('id', 'main-content'), ('tag', 'main')],
        'edge': [('class', 'content')],
        'safari-technology-preview': [('class', 'body'), ('class', 'entry-content'), ('class', 'bodycopy')],
        'safari-security': [('id', 'article-body'), ('class', 'main')],
        'brave-blog': [('class', 'prose'), ('tag', 'article')],
        'whale-notices': [('attr', ('data-role', 'commentContent'))],
        'opera': [('class', 'entry-content'), ('class', 'content')],
        'vivaldi': [('class', 'entry-content')],
    }
    key = source_id if source_id in selectors else source_id.split('-')[0]
    for kind, value in selectors.get(key, []):
        matches = []
        for n in nodes:
            if ((kind == 'class' and n.has_class(value)) or
                (kind == 'id' and n.attrs.get('id') == value) or
                (kind == 'tag' and n.tag == value) or
                (kind == 'attr' and n.attrs.get(value[0]) == value[1])):
                matches.append(n)
        if matches:
            if key == 'chrome-releases':
                expand_chrome_post_templates(matches[0], reviewed_signoffs, document_url)
            # Learn has a title-only .content before its complete article body.
            return max(matches, key=lambda n: len(n.text())) if key == 'edge' else matches[0]
    return None


def links(tree, base):
    for n in tree.walk():
        if n.tag == 'a' and n.attrs.get('href') and not any(a.tag in {'nav', 'footer', 'header'} for a in n.ancestors()):
            url = urldefrag(urljoin(base, n.attrs['href']))[0]
            if url.startswith('https://'):
                yield url, n.text(), n


def chrome_archive_before(node, url, since, exact_start=None):
    if node.tag != 'a' or node.attrs.get('id') != 'Blog1_blog-pager-older-link':
        return False
    target = urlsplit(url)
    if (target.scheme, target.netloc, target.path) != (
            'https', 'chromereleases.googleblog.com', '/search'):
        return False
    cursors = parse_qs(target.query, keep_blank_values=True).get('updated-max', [])
    if len(cursors) != 1 or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{2}:\d{2}', cursors[0]):
        return False
    try:
        cursor = datetime.fromisoformat(cursors[0])
        midnight = datetime.strptime(since, '%Y-%m-%d').replace(tzinfo=cursor.tzinfo)
    except ValueError:
        return False
    # The publisher's offset determines its calendar day. Keep the entire
    # boundary day, including a cursor that lands exactly at its midnight.
    return cursor < midnight and (exact_start is None or cursor < instant(exact_start))


def next_links(tree, base, chrome_releases_since=None, exact_start=None):
    result = []
    for n in tree.walk():
        if n.tag not in {'a', 'link'} or not n.attrs.get('href'):
            continue
        attrs = n.attrs
        if attrs.get('aria-disabled') == 'true' or 'disabled' in attrs or any(a.has_class('ipsPagination_inactive') or a.attrs.get('aria-disabled') == 'true' for a in n.ancestors()):
            continue
        label = (n.text() + ' ' + attrs.get('aria-label', '') + ' ' + attrs.get('title', '')).lower()
        if ('next' in attrs.get('rel', '').split() or n.has_class('next') or
                n.has_class('blog-pager-older-link') or attrs.get('id') == 'Blog1_blog-pager-older-link' or
                attrs.get('rel') == 'next' or label.strip() in {'next', 'next page', 'older posts', 'older', '다음'}):
            url = urldefrag(urljoin(base, attrs['href']))[0]
            if chrome_releases_since and chrome_archive_before(n, url, chrome_releases_since, exact_start):
                continue
            result.append(url)
    return list(dict.fromkeys(result))


def item_type(text):
    text = text.lower()
    if re.search(r'cve-\d|security|vulnerab|보안', text):
        return 'security'
    if re.search(r'\bfix(?:ed|es)?\b|resolved|수정', text):
        return 'fix'
    return 'general'


def unique_unit_keys(units):
    """Keep each source location when an issue/anchor is reused in one document.

    An issue reference is not a unique source-unit identifier. Keep the first
    original key for compatibility, then use section and occurrence to retain
    further locations. Text does not enter the key, so corrections keep IDs.
    """
    used, occurrences = set(), {}
    for unit in units:
        original = unit['key']
        context = json.dumps([original, unit['section']], ensure_ascii=False,
                             separators=(',', ':')).encode('utf-8')
        context_key = hashlib.sha256(context).hexdigest()[:24]
        occurrences[context_key] = occurrences.get(context_key, 0) + 1
        if original in used:
            ordinal = occurrences[context_key]
            candidate = original + ':location:' + context_key + ':' + str(ordinal)
            while candidate in used:
                ordinal += 1
                candidate = original + ':location:' + context_key + ':' + str(ordinal)
            unit['key'] = candidate
        used.add(unit['key'])
    return units


def omit_attributions(body):
    """Omit explicit credit fields before ancestor text and headings are read."""
    marker = '[image attribution omitted]'
    credit_classes = {'photo-credit', 'image-credit', 'picture-credit',
                      'photo-attribution', 'image-attribution'}
    byline_tags = {'a', 'b', 'em', 'i', 'small', 'span', 'strong'}
    for node in list(body.walk()):
        if credit_classes.intersection((node.attrs.get('class') or '').split()):
            node.children = [marker]
            node.attrs.pop('href', None)
            continue
        if node.tag != 'p':
            continue
        content = [child for child in node.children if isinstance(child, Node) or child.strip()]
        # This is an explicitly labeled, standalone byline field. Do not infer
        # an author from an unmarked name or a sentence elsewhere in prose.
        text = node.text()
        if (re.match(r'^(?:Written|Authored|Posted) by\s*:', text, re.I)
                and all(child.tag in byline_tags for child in node.walk() if child is not node)):
            node.children = ['[author attribution omitted]']
        # Opera also uses a standalone bold byline with an explicit product
        # role. The full field must match; "By default" product prose cannot.
        elif (len(content) == 1 and isinstance(content[0], Node) and content[0].tag in {'strong', 'b'}
                and re.fullmatch(r'By [^,\n]+, Product (?:Manager|Director)', text)):
            node.children = ['[author attribution omitted]']

    # Publishers often split a credit label and its linked contributor across
    # inline tags. Replace the credited link only, keeping product text before
    # or after it. An ordinary product sentence such as "image by uploading"
    # is not a credit. No personal-name or unmarked-byline inference is used.
    credit_label = re.compile(
        r'(?:^|[.!?]\s+)(?:(?:main|header|featured|cover)\s+)?'
        r'(?:photo|image|photograph|illustration)\s+(?:by|credits?\s*:)\s*'
        r'(?:' + re.escape(marker) + r'(?:\s*,\s*(?:and\b\s*)?|\s+(?:and\b|&)\s*))*$', re.I)
    containers = {'p', 'li', 'td', 'th', 'figcaption', 'div', 'blockquote',
                  'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'document'}
    line_boundaries = containers | {'br'}
    for link in list(body.walk()):
        if link.tag != 'a':
            continue
        owner = next((n for n in link.ancestors() if n.tag in containers), body)
        preceding = []

        def before(node):
            if node is link:
                return True
            if node is not owner and node.tag in line_boundaries:
                preceding.clear()
                return False
            if node.tag in SKIP:
                return False
            for child in node.children:
                if isinstance(child, Node):
                    if before(child):
                        return True
                else:
                    preceding.append(child)
            return False

        before(owner)
        if credit_label.search(' '.join(' '.join(preceding).split())):
            link.children = [marker]
            link.attrs.pop('href', None)


def blocks(body, *, visible_sections=False):
    """Partition body into source units, retaining unsupported leaf text as unresolved.

    A list entry or table row is one unit. Paragraphs outside those units are
    separate units. Keys prefer upstream anchors/issue IDs; positional fallback
    is deliberately local to a section, and is not a semantic deduplication key.
    """
    omit_attributions(body)
    result, counters, section, headings = [], {}, 'document', {}
    heading_dates, visible_headings = {}, {}
    suppressed = set()
    # Explicit author/reporter fields are outside the public product record.
    for n in body.walk():
        if 'author' in (n.attrs.get('itemprop') or '').split() or 'author' in (n.attrs.get('rel') or '').split():
            suppressed.add(id(n))
        if n.tag == 'time' and (n.attrs.get('itemprop') == 'datePublished' or date_value(n.text())):
            suppressed.add(id(n))
    for n in body.walk():
        if n.tag == 'dt' and n.text(suppressed).lower() in {'reporter', 'reported by', 'author'}:
            suppressed.add(id(n))
            siblings = n.parent.children
            following = next((v for v in siblings[siblings.index(n)+1:] if isinstance(v, Node)), None)
            if following and following.tag == 'dd':
                suppressed.add(id(following))
    covered = set(suppressed)
    for n in body.walk():
        within = []
        for ancestor in n.ancestors():
            if ancestor is body.parent:
                break
            within.append(ancestor)
        if id(n) in covered or any(id(a) in covered or a.tag in SKIP for a in within):
            continue
        if n.tag in SKIP:
            covered.add(id(n))
            continue
        if isinstance(n, UnresolvedChromeSignoff):
            result.append({'key': 'chrome-post-signoff', 'text': '',
                           'section': 'post sign-off', 'parsed': False})
            continue
        # Suppression must also apply to ancestor aggregates and headings, not
        # only to the traversal of the author/reporter node itself.
        text = n.text(suppressed)
        if re.fullmatch(r'h[1-6]', n.tag):
            level = int(n.tag[1])
            headings = {k: v for k, v in headings.items() if k < level}
            heading_dates = {k: v for k, v in heading_dates.items() if k < level}
            if date_value(text):
                heading_dates[level] = date_value(text)
            if visible_sections:
                visible_headings = {k: v for k, v in visible_headings.items() if k < level}
                if text:
                    visible_headings[level] = text
            headings[level] = n.attrs.get('id') or text or section
            section = ' / '.join(headings[k] for k in sorted(headings))
            covered.add(id(n))
            continue
        if (n.tag in {'p', 'li', 'tr', 'pre', 'blockquote', 'dt', 'dd'} or inline_product_container(n)) and (text or (n.tag in {'li', 'tr'} and any(c.tag in {'img', 'iframe', 'object'} for c in n.walk()))):
            # Parent list entries own their complete nested definition.
            key = n.attrs.get('id')
            issue = re.search(r'\b(?:CVE-\d{4}-\d+|VB-\d+|DNA-\d+)\b|\((\d{7,})\)', text)
            if not key and issue:
                key = issue[1] or issue[0]
            prefix = section + ':' + n.tag
            counters[prefix] = counters.get(prefix, 0) + 1
            key = key or prefix + ':' + str(counters[prefix])
            result.append({'key': key, 'text': text, 'section': section, 'parsed': bool(text),
                           'date': heading_dates[max(heading_dates)] if heading_dates else None})
            if visible_sections:
                result[-1]['visible_headings'] = list(visible_headings.values())
            covered.add(id(n))
        elif any(isinstance(c, str) and c.strip() for c in n.children):
            # Plain text in an unfamiliar div/span is retained, never dropped.
            direct = ' '.join(c.strip() for c in n.children if isinstance(c, str) and c.strip())
            if direct:
                prefix = section + ':unparsed'
                counters[prefix] = counters.get(prefix, 0) + 1
                ordinary = n.tag in {'div', 'span', 'a', 'strong', 'b', 'em', 'i', 'u', 'code', 'small', 'font', 'document', 'figcaption'}
                result.append({'key': n.attrs.get('id') or prefix + ':' + str(counters[prefix]),
                               'text': direct if ordinary else '', 'section': section, 'parsed': ordinary,
                               'date': heading_dates[max(heading_dates)] if heading_dates else None})
                if visible_sections:
                    result[-1]['visible_headings'] = list(visible_headings.values())
    return unique_unit_keys(result)
