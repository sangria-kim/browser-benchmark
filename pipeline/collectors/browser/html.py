"""Small DOM reader with explicit source content boundaries. No script execution."""
import re
import hashlib
import json
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urldefrag, urlsplit
from datetime import datetime

from pipeline.temporal import instant

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
        return name in self.attrs.get('class', '').split()

    def ancestors(self):
        node = self.parent
        while node:
            yield node
            node = node.parent


class UnresolvedChromeSignoff(Node):
    pass


class ReviewedChromeSignoff(Node):
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


def published(tree, source_id=None):
    for n in tree.walk():
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


def remove_chrome_post_signoff(fragment, reviewed_signoffs=()):
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
            elif child.strip():
                lines[-1].append((node, index, child.strip()))
        if separates_lines and lines[-1]:
            lines.append([])

    visit(fragment)
    lines = [line for line in lines if line]
    if len(lines) < 2:
        return
    publisher = ' '.join(' '.join(text for _, _, text in lines[-1]).split())
    if publisher not in {'Google Chrome', 'Google ChromeOS', 'Google Chrome OS'}:
        return
    for node, index, _ in lines[-1]:
        node.children[index] = ''
    # The preceding line has no author marker. Keep its location without
    # exposing possible personal text or assuming that it is a byline.
    if len(lines[-2]) == 1:
        node, index, text = lines[-2][0]
        if len(text) <= 64 and not any(a.tag in {'li', 'a'} for a in (node, *node.ancestors())):
            node.children[index] = ''
            marker = ReviewedChromeSignoff if hashlib.sha256(text.encode()).hexdigest() in reviewed_signoffs else UnresolvedChromeSignoff
            fragment.children.append(marker('document', parent=fragment))


def expand_chrome_post_templates(body, reviewed_signoffs=()):
    # Chrome Releases stores the article markup in an inert Blogger template.
    # Its noscript copy remains excluded by SKIP.
    for content in body.children:
        if not isinstance(content, Node) or not content.has_class('post-content'):
            continue
        for index, child in enumerate(content.children):
            if (not isinstance(child, Node) or child.tag != 'script' or
                    child.attrs.get('type') != 'text/template' or 'src' in child.attrs):
                continue
            fragment = Tree(''.join(child.children)).root
            has_author_metadata = False
            for node in list(fragment.walk())[1:]:
                is_author = node.attrs.get('itemprop') == 'author'
                has_author_metadata |= is_author
                if is_author or node.tag == 'header':
                    node.parent.children.remove(node)
            if has_author_metadata:
                remove_chrome_post_signoff(fragment, reviewed_signoffs)
            fragment.parent = content
            content.children[index] = fragment


def boundary(tree, source_id, reviewed_signoffs=()):
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
                expand_chrome_post_templates(matches[0], reviewed_signoffs)
            # Learn has a title-only .content before its complete article body.
            return max(matches, key=lambda n: len(n.text())) if key == 'edge' else matches[0]
    return None


def links(tree, base):
    for n in tree.walk():
        if n.tag == 'a' and n.attrs.get('href') and not any(a.tag in {'nav', 'footer', 'header'} for a in n.ancestors()):
            url = urldefrag(urljoin(base, n.attrs['href']))[0]
            if url.startswith('https://'):
                yield url, n.text(), n


def chrome_archive_before(node, url, since):
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
    return cursor < midnight


def next_links(tree, base, chrome_releases_since=None):
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
            if chrome_releases_since and chrome_archive_before(n, url, chrome_releases_since):
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


def blocks(body):
    """Partition body into source units, retaining unsupported leaf text as unresolved.

    A list entry or table row is one unit. Paragraphs outside those units are
    separate units. Keys prefer upstream anchors/issue IDs; positional fallback
    is deliberately local to a section, and is not a semantic deduplication key.
    """
    result, counters, section, headings = [], {}, 'document', {}
    heading_dates = {}
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
        if isinstance(n, ReviewedChromeSignoff):
            result.append({'key': 'chrome-post-signoff', 'text': 'Publisher attribution omitted.',
                           'section': 'post sign-off', 'parsed': True})
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
            headings[level] = n.attrs.get('id') or text or section
            section = ' / '.join(headings[k] for k in sorted(headings))
            covered.add(id(n))
            continue
        inline_container = n.tag in {'div', 'span'} and all(c is n or c.tag in {'a', 'span', 'strong', 'b', 'em', 'i', 'u', 'code', 'br', 'small', 'sup', 'sub', 'font'} for c in n.walk())
        if (n.tag in {'p', 'li', 'tr', 'pre', 'blockquote', 'dt', 'dd'} or inline_container) and (text or (n.tag in {'li', 'tr'} and any(c.tag in {'img', 'iframe', 'object'} for c in n.walk()))):
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
    return unique_unit_keys(result)
