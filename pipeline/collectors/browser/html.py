"""Small DOM reader with explicit source content boundaries. No script execution."""
import re
import hashlib
import json
from html.parser import HTMLParser
from urllib.parse import urljoin, urldefrag
from datetime import datetime

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

    def text(self):
        if self.tag in SKIP:
            return ''
        return ' '.join(' '.join(c.text() if isinstance(c, Node) else c for c in self.children).split())

    def has_class(self, name):
        return name in self.attrs.get('class', '').split()

    def ancestors(self):
        node = self.parent
        while node:
            yield node
            node = node.parent


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
    match = re.search(r'\b(20\d{2}-\d{2}-\d{2})\b', value or '')
    if match:
        try:
            return datetime.strptime(match[1], '%Y-%m-%d').date().isoformat()
        except ValueError:
            pass
    match = re.search(r'([A-Z][a-z]+ \d{1,2}, 20\d{2})', value or '')
    if match:
        try:
            return datetime.strptime(match[1], '%B %d, %Y').date().isoformat()
        except ValueError:
            pass
    return None


def published(tree):
    for n in tree.walk():
        if n.tag == 'meta' and n.attrs.get('property', n.attrs.get('name')) in (
                'article:published_time', 'date', 'datePublished', 'publication_date'):
            found = date_value(n.attrs.get('content'))
            if found:
                return found
        if n.tag == 'time' or n.has_class('c-release-date'):
            found = date_value(n.attrs.get('datetime', n.text()))
            if found:
                return found
    return None


def boundary(tree, source_id):
    nodes = list(tree.walk())
    # Select the publisher's product body, never navigation, replies or author cards.
    selectors = {
        'chrome-releases': [('class', 'post-body')],
        'chrome-enterprise': [('class', 'article-content'), ('class', 'answer')],
        'chrome-blog': [('class', 'article-body'), ('class', 'uni-article__body')],
        'firefox': [('class', 'c-release-notes')],
        'firefox-security': [('id', 'main-content'), ('tag', 'main')],
        'edge': [('class', 'content')],
        'safari-technology-preview': [('class', 'body'), ('class', 'entry-content')],
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
            # Learn has a title-only .content before its complete article body.
            return max(matches, key=lambda n: len(n.text())) if key == 'edge' else matches[0]
    return None


def links(tree, base):
    for n in tree.walk():
        if n.tag == 'a' and n.attrs.get('href') and not any(a.tag in {'nav', 'footer', 'header'} for a in n.ancestors()):
            url = urldefrag(urljoin(base, n.attrs['href']))[0]
            if url.startswith('https://'):
                yield url, n.text(), n


def next_links(tree, base):
    result = []
    for n in tree.walk():
        if n.tag not in {'a', 'link'} or not n.attrs.get('href'):
            continue
        attrs = n.attrs
        label = (n.text() + ' ' + attrs.get('aria-label', '') + ' ' + attrs.get('title', '')).lower()
        if ('next' in attrs.get('rel', '').split() or n.has_class('next') or
                n.has_class('blog-pager-older-link') or attrs.get('id') == 'Blog1_blog-pager-older-link' or
                attrs.get('rel') == 'next' or label.strip() in {'next', 'next page', 'older posts', 'older', '다음'}):
            result.append(urldefrag(urljoin(base, attrs['href']))[0])
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
    covered = set()
    for n in body.walk():
        if any(id(a) in covered or a.tag in SKIP for a in n.ancestors()):
            continue
        if n.tag in SKIP:
            covered.add(id(n))
            continue
        text = n.text()
        if re.fullmatch(r'h[1-6]', n.tag):
            level = int(n.tag[1])
            headings = {k: v for k, v in headings.items() if k < level}
            headings[level] = n.attrs.get('id') or text or section
            section = ' / '.join(headings[k] for k in sorted(headings))
            covered.add(id(n))
            continue
        if n.tag in {'p', 'li', 'tr', 'pre', 'blockquote', 'dt', 'dd'} and (text or (n.tag in {'li', 'tr'} and any(c.tag in {'img', 'iframe', 'object'} for c in n.walk()))):
            # Parent list entries own their complete nested definition.
            key = n.attrs.get('id')
            issue = re.search(r'\b(?:CVE-\d{4}-\d+|VB-\d+|DNA-\d+)\b|\((\d{7,})\)', text)
            if not key and issue:
                key = issue[1] or issue[0]
            prefix = section + ':' + n.tag
            counters[prefix] = counters.get(prefix, 0) + 1
            key = key or prefix + ':' + str(counters[prefix])
            result.append({'key': key, 'text': text, 'section': section, 'parsed': bool(text)})
            covered.add(id(n))
        elif any(isinstance(c, str) and c.strip() for c in n.children):
            # Plain text in an unfamiliar div/span is retained, never dropped.
            direct = ' '.join(c.strip() for c in n.children if isinstance(c, str) and c.strip())
            if direct:
                prefix = section + ':unparsed'
                counters[prefix] = counters.get(prefix, 0) + 1
                result.append({'key': n.attrs.get('id') or prefix + ':' + str(counters[prefix]),
                               'text': '', 'section': section, 'parsed': False})
    return unique_unit_keys(result)
