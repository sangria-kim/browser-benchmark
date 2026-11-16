"""All-item browser collection. PM selection is intentionally absent.

Coverage is conservative: explicit pagination exhaustion plus recognized content
is required. Limits, changing totals, unresolved blocks and HTTP failures leave
partial coverage. Re-run the same cutoff to retry; successful records survive.
"""
import copy
import hashlib
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag

from schemas.validate import validate_record, validate_transition, validate_dataset
from .html import Tree, boundary, blocks, links, next_links, published, date_value, item_type, unique_unit_keys
from .transport import HTTPTransport, Response


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(prefix, fields):
    return prefix + '-' + digest(canonical(fields))[:24]


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with open(temporary, 'w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def minimal(text, limit=220):
    # Do not expose API owners, handles, author signatures or contact addresses.
    text = re.sub(r'\S+@\S+', '[contact omitted]', text)
    css_rules = {'container', 'media', 'supports', 'font-face', 'function', 'scope', 'import', 'page',
                 'keyframes', 'layer', 'property', 'starting-style', 'view-transition', 'charset',
                 'namespace', 'custom-media', 'when', 'else', 'result', 'apply', 'nest', 'document',
                 'counter-style', 'font-feature-values', 'color-profile', 'position-try'}
    text = re.sub(r'(?<!\w)@([\w-]+)', lambda m: m[0] if m[1] in css_rules else '[contributor omitted]', text)
    text = re.sub(r'https?://\S+', '', text)
    return ' '.join(text.split())[:limit]


def json_body(response):
    text = response.text()
    if text.startswith(")]}'"):
        text = text.split('\n', 1)[1]
    return json.loads(text)


def markdown_items(text):
    section, counters, result = 'document', {}, []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            section = line.lstrip('# ').strip() or section
            continue
        counters[section] = counters.get(section, 0) + 1
        issue = re.search(r'\(#(\d+)\)|\b(CVE-\d{4}-\d+)\b', line)
        key = (issue[1] or issue[2]) if issue else str(counters[section])
        # Keep prose and unrecognized syntax too; no feature/security allowlist.
        result.append({'key': section + ':' + key, 'text': line.lstrip('-* '),
                       'section': section, 'parsed': not line.startswith(('```', '<'))})
    return unique_unit_keys(result)


def docc_text(value):
    if isinstance(value, list):
        return ' '.join(docc_text(v) for v in value)
    if not isinstance(value, dict):
        return ''
    if 'text' in value:
        return value['text']
    if 'code' in value:
        return value['code']
    return ' '.join(docc_text(value[k]) for k in ('inlineContent', 'content', 'items') if k in value)


def docc_items(data):
    result, section, count = [], 'document', {}
    def walk(content):
        nonlocal section
        for node in content:
            kind = node.get('type')
            if kind == 'heading':
                section = node.get('anchor') or node.get('text') or section
            elif kind in ('unorderedList', 'orderedList'):
                for entry in node.get('items', []):
                    add(entry, True)
            elif kind == 'paragraph':
                add(node, True)
            elif kind in ('aside', 'section') and 'content' in node:
                walk(node['content'])
            else:
                add(node, False)
    def add(node, parsed):
        count[section] = count.get(section, 0) + 1
        text = docc_text(node)
        issue = re.search(r'\((\d{7,})\)', text)
        key = issue[1] if issue else section + ':' + str(count[section])
        result.append({'key': key, 'section': section, 'text': text if parsed else '',
                       'parsed': parsed and bool(text)})
    for content_section in data.get('primaryContentSections', []):
        if content_section.get('kind') == 'content':
            walk(content_section.get('content', []))
        else:
            add(content_section, False)
    return unique_unit_keys(result)


class BrowserCollector:
    """One source per instance; transport is callable(url) -> Response.

    `private_dir` must be outside `repository`. Public files are arrays at
    data/source-items/<browser>/<source_id>.json. The private checkpoint contains
    pending URLs, reconciliation counts, errors and last successful cutoff.
    """
    def __init__(self, repository, private_dir, transport=None, resume=False):
        self.repository = Path(repository).resolve()
        self.private_dir = Path(private_dir).expanduser().resolve()
        if self.private_dir == self.repository or self.repository in self.private_dir.parents:
            raise ValueError('Private collection state must be outside the repository')
        self.transport = transport or HTTPTransport()
        self.resume = resume

    def collect(self, source, cutoff, since, origin='baseline'):
        self.source, self.cutoff, self.since, self.origin = source, cutoff, since, origin
        self.observed_at = datetime.now(timezone.utc).isoformat()
        self.progress_path = self.private_dir / (source['source_id'] + '-progress.json')
        prior_progress = json.loads(self.progress_path.read_text()) if self.resume and self.progress_path.exists() else {}
        self.progress = prior_progress if prior_progress.get('cutoff') == cutoff else {'cutoff': cutoff, 'responses': {}, 'documents': []}
        self.new_pages, self.new_documents = 0, 0

        self.destination = self.repository / 'data/source-items' / source['browser'] / (source['source_id'] + '.json')
        self.previous = json.loads(self.destination.read_text()) if self.destination.exists() else []
        self.records = {r['source_item_id']: r for r in self.previous}
        self.seen = {}
        state_path = self.private_dir / (source['source_id'] + '.json')
        prior_state = json.loads(state_path.read_text()) if state_path.exists() else {}
        self.state = {'source_id': source['source_id'], 'cutoff': cutoff, 'since': since,
                      'status': 'partial', 'discovered': 0, 'processed': 0, 'duplicate': 0,
                      'unparsed': 0, 'documents': 0, 'pages': 0, 'errors': [], 'pending': [],
                      'excluded_by_date': [], 'pagination_exhausted': False,
                      'last_successful_cutoff': prior_state.get('last_successful_cutoff')}
        self.cache = {}
        self.state_path = state_path
        try:
            parser = source['parser']
            if source['source_id'] == 'whale-release-history':
                self.collect_whale()
            elif parser == 'chromestatus':
                self.collect_chromestatus()
            elif parser == 'github_releases':
                self.collect_github()
            elif parser == 'github_markdown':
                self.collect_markdown()
            elif parser == 'apple_documentation':
                self.collect_apple()
            else:
                self.collect_html()
        except Exception as error:
            self.problem(source['url'], type(error).__name__ + ': ' + str(error))
        assert self.state['discovered'] == sum(self.state[k] for k in ('processed', 'duplicate', 'unparsed'))
        if self.state['pagination_exhausted'] and not self.state['errors'] and not self.state['unparsed'] and not self.state['pending'] and not any(r['record_status'] == 'unparsed' for k, r in self.records.items() if k in self.seen):
            self.state['status'] = 'complete'
            self.state['last_successful_cutoff'] = cutoff
        candidate = sorted(self.records.values(), key=lambda r: r['source_item_id'])
        validate_dataset({'source_item': candidate}, {source['source_id']})
        atomic_json(self.destination, candidate)
        self.state['pending'] = list(dict.fromkeys(self.state['pending'] + [e['url'] for e in self.state['errors']]))
        self.state['stored_records'] = len(candidate)
        atomic_json(state_path, self.state)
        return copy.deepcopy(self.state)

    def problem(self, url, error):
        self.state['errors'].append({'url': url, 'reason': error})

    def get(self, url):
        if url in self.cache:
            return self.cache[url]
        cached = self.progress['responses'].get(url)
        if cached:
            raw = (self.private_dir / 'cache' / cached['sha256']).read_bytes()
            response = Response(cached['url'], raw, 200, cached['headers'])
            self.cache[url] = response
            return response
        response = self.transport(url)
        if response.status != 200:
            raise ValueError('Unexpected HTTP status %s' % response.status)
        if not response.body:
            raise ValueError('Empty response')
        # Keep bytes private. Cache filenames are hashes, not author/URL names.
        cache_path = self.private_dir / 'cache' / digest(response.body)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if not cache_path.exists():
            cache_path.write_bytes(response.body)
        self.cache[url] = response
        self.progress['responses'][url] = {'url': response.url, 'sha256': digest(response.body), 'headers': response.headers}
        atomic_json(self.progress_path, self.progress)
        return response

    def budget(self, url, kind):
        cached = url in self.progress['responses'] if kind == 'pages' else url in self.progress['documents']
        if cached:
            return True
        field = 'new_' + kind
        if getattr(self, field) >= self.source['discovery']['max_' + kind]:
            self.problem(url, ('Page' if kind == 'pages' else 'Document') + ' limit reached')
            self.state['pending'] = [url]
            return False
        setattr(self, field, getattr(self, field) + 1)
        return True

    def document_done(self, url):
        if url not in self.progress['documents']:
            self.progress['documents'].append(url)
            atomic_json(self.progress_path, self.progress)

    def allowed_date(self, date, current=False):
        if date and date > self.cutoff[:10]:
            return False
        return current or not date or date >= self.since

    def emit(self, url, response, unit, date=None, revision=None, title=None, channel=None, platform=None, version=None):
        key = unit['key']
        ident = identity('src', [self.source['source_id'], url, key])
        fingerprint = digest(canonical([self.source['source_id'], url, key, unit,
                                        digest(response.body), date, revision, title, channel, platform, version]))
        if ident in self.seen and self.seen[ident] != fingerprint:
            raise ValueError('Source identity collision between distinct observations: ' + ident)
        self.state['discovered'] += 1
        if ident in self.seen:
            self.state['duplicate'] += 1
            return
        self.seen[ident] = fingerprint
        parsed = unit['parsed']
        self.state['processed' if parsed else 'unparsed'] += 1
        content_hash = digest(response.body)
        evidence = {'url': url, 'section': minimal(unit['section']) or None,
                    'source_revision': revision, 'content_sha256': content_hash,
                    'observed_at': self.observed_at, 'excerpt': minimal(unit['text']) if parsed else ''}
        source_channels = self.source['channels']
        source_platforms = self.source['platforms']
        record = {'schema_version': 2, 'source_item_id': ident, 'source_id': self.source['source_id'],
                  'browser': self.source['browser'], 'item_key': key,
                  'item_type': item_type(unit['section'] + ' ' + unit['text']) if parsed else 'unknown',
                  'title': minimal(title or unit['text'], 160) or None,
                  'summary': minimal(unit['text']) or None,
                  'channel': channel or (source_channels[0] if len(source_channels) == 1 else 'unknown'),
                  'platform': platform or (source_platforms if len(source_platforms) == 1 else ['unknown']),
                  'version': version, 'published_at': date, 'observed_at': self.observed_at,
                  'evidence': evidence, 'record_status': 'parsed' if parsed else 'unparsed',
                  'origin': self.origin, 'lifecycle': 'unknown', 'revisions': [],
                  'experiment_kind': None, 'source_location': url + '#' + key, 'source_symbol': None}
        # Hash the full item, not its truncated public excerpt or sibling document bytes.
        if parsed:
            record['item_content_sha256'] = digest(canonical([unit['section'], unit['text']]))
        old = self.records.get(ident)
        if old:
            if (old['item_key'], old['source_id'], old['evidence']['url']) != (key, self.source['source_id'], url):
                raise ValueError('Source ID hash collision')
            # A temporarily unresolved parser never erases valid facts.
            if not parsed and old['record_status'] == 'parsed':
                return
            comparison = ['title', 'summary', 'published_at', 'record_status', 'channel', 'platform', 'version', 'item_type', 'item_content_sha256']
            if (all(old.get(k) == record.get(k) for k in comparison) and
                    old['evidence']['content_sha256'] == content_hash and old['evidence']['source_revision'] == revision):
                self.state['processed' if parsed else 'unparsed'] -= 1
                self.state['duplicate'] += 1
                return
            record['revisions'] = copy.deepcopy(old['revisions'])
            record['origin'] = old['origin']
            # Older revisions did not freeze product metadata. Preserve the last
            # complete head before changing it; never edit existing snapshots.
            if any(k not in old['revisions'][-1] for k in ('channel', 'platform', 'version', 'item_type', 'record_status', 'lifecycle')):
                prior = copy.deepcopy(old['revisions'][-1])
                for field in ('channel', 'platform', 'version', 'item_type', 'record_status', 'lifecycle', 'item_content_sha256'):
                    if field in old:
                        prior[field] = copy.deepcopy(old[field])
                prior['restores_revision_id'] = prior['revision_id']
                prior['revision_id'] = identity('sr', [ident, 'complete-head', prior])
                record['revisions'].append(prior)
        snapshot = {k: copy.deepcopy(record[k]) for k in ('title', 'summary', 'evidence', 'published_at', 'observed_at',
                    'channel', 'platform', 'version', 'item_type', 'record_status', 'lifecycle',
                    'item_content_sha256') if k in record}
        revision_facts = {k: v for k, v in snapshot.items() if k != 'observed_at'}
        revision_facts['evidence'] = {k: v for k, v in evidence.items() if k != 'observed_at'}
        revision_id = identity('sr', [ident, revision_facts])
        if any(r['revision_id'] == revision_id for r in record['revisions']):
            # A->B->A is another occurrence of the same upstream content.
            revision_id = identity('sr', [ident, revision_facts, record['revisions'][-1]['revision_id']])
        snapshot.update(revision_id=revision_id, content_sha256=content_hash, source_revision=revision)
        record['revisions'].append(snapshot)
        validate_record('source_item', record)
        if old:
            validate_transition('source_item', old, record)
        self.records[ident] = record

    def unresolved(self, url, response, key='document', section='document'):
        self.emit(url, response, {'key': key, 'section': section, 'text': '', 'parsed': False})

    def persist_checkpoint(self, pending):
        self.state['pending'] = list(pending)
        # Per-document durable progress permits replay after interrupted runs.
        candidate = sorted(self.records.values(), key=lambda r: r['source_item_id'])
        validate_dataset({'source_item': candidate}, {self.source['source_id']})
        atomic_json(self.destination, candidate)
        atomic_json(self.state_path, self.state)

    def document(self, url, response=None, current=False):
        response = response or self.get(url)
        text = response.text()
        root = Tree(text).root
        canonical_url = urldefrag(response.url)[0]
        if '<html' in text.lower() and '</html>' not in text.lower():
            self.problem(url, 'Truncated HTML document')
        date = published(root)
        if not self.allowed_date(date, current):
            self.state['excluded_by_date'].append(url)
            return root
        body = boundary(root, self.source['source_id'])
        if body is None:
            self.unresolved(url, response)
            self.problem(url, 'Recognized product content boundary missing')
            return root
        units = blocks(body)
        if not units:
            self.unresolved(url, response)
            self.problem(url, 'No source units in product content')
        document_title = ' '.join(n.text() for n in root.walk() if n.tag == 'title')
        for unit in units:
            version_match = re.search(r'(?:version|firefox|chrome|safari|opera|vivaldi|brave)[ -]+(\d+(?:[.][\w]+)+)', unit['section'] + ' ' + document_title, re.I)
            self.emit(canonical_url, response, unit, date=date_value(unit['section']) or date,
                      version=version_match[1] if version_match else None)
        return root

    def index_link(self, node):
        if self.source['browser'] in {'opera', 'vivaldi'}:
            return any(a.tag in {'h2', 'h3'} for a in node.ancestors())
        return True

    def collect_html(self):
        source = self.source
        if source['parser'] == 'html_document':
            self.state['documents'] += 1
            try:
                self.document(source['url'], current=True)
                self.state['pagination_exhausted'] = True
            except Exception as error:
                self.problem(source['url'], str(error))
            return
        pattern = re.compile(source['discovery']['include_url_pattern'])
        pending_pages, visited_pages, documents, document_set = [source['url']], set(), [], set()
        enumeration_valid = True
        while pending_pages:
            if not self.budget(pending_pages[0], 'pages'):
                break
            url = pending_pages.pop(0)
            if url in visited_pages:
                self.problem(url, 'Pagination loop')
                continue
            visited_pages.add(url)
            try:
                response = self.get(url)
                self.state['pages'] += 1
                index_text = response.text()
                root = Tree(index_text).root
                if '<html' in index_text.lower() and '</html>' not in index_text.lower():
                    self.unresolved(url, response, key='index-truncated')
                    self.problem(url, 'Truncated HTML index')
                    enumeration_valid = False
                found = [(u, text) for u, text, n in links(root, url) if pattern.search(u) and u != source['url'] and self.index_link(n)]
                if not found:
                    self.unresolved(url, response, key='index')
                    self.problem(url, 'No registered document links in index')
                    enumeration_valid = False
                for doc, _ in found:
                    if doc not in document_set:
                        document_set.add(doc)
                        documents.append((doc, response, url == source['url']))
                if source['discovery']['pagination'] == 'next_link':
                    for next_url in next_links(root, url):
                        if urlparse(next_url).netloc != urlparse(source['url']).netloc:
                            self.problem(next_url, 'Unexpected pagination host')
                        elif next_url in visited_pages:
                            self.problem(next_url, 'Pagination loop')
                        elif next_url not in pending_pages:
                            pending_pages.append(next_url)
                # Do not infer completion from an SPA load-more button.
                if any(n.tag == 'button' and re.search(r'load more|show more|더 보기', n.text(), re.I) for n in root.walk()):
                    self.problem(url, 'Dynamic pagination requires another adapter')
            except Exception as error:
                enumeration_valid = False
                self.problem(url, str(error))
            self.persist_checkpoint(pending_pages + [d[0] for d in documents])
        self.state['pagination_exhausted'] = not pending_pages and enumeration_valid
        done = set()
        while documents:
            if not self.budget(documents[0][0], 'documents'):
                break
            url, discovery_response, current = documents.pop(0)
            if url in done:
                continue
            done.add(url)
            self.state['documents'] += 1
            try:
                root = self.document(url, current=current)
                self.document_done(url)
                if source['discovery']['follow_related_documents']:
                    body = boundary(root, source['source_id'])
                    if body:
                        for related, _, _ in links(body, url):
                            if pattern.search(related) and related not in document_set and related != source['url']:
                                document_set.add(related)
                                documents.append((related, self.cache[url], False))
            except Exception as error:
                self.problem(url, str(error))
                self.unresolved(url, discovery_response, key='discovered-document')
            self.persist_checkpoint(pending_pages + [d[0] for d in documents])
        self.state['pending'] = pending_pages + [d[0] for d in documents]

    def collect_chromestatus(self):
        total, start, seen_ids = None, 0, set()
        while True:
            url = 'https://chromestatus.com/api/v0/features?num=100&start=%s' % start
            if not self.budget(url, 'pages'):
                return
            response = self.get(url)
            self.state['pages'] += 1
            data = json_body(response)
            rows = data['features']
            observed_total = data['total_count']
            if not isinstance(rows, list) or not isinstance(observed_total, int):
                raise ValueError('ChromeStatus API shape changed')
            if total is not None and total != observed_total:
                self.problem(url, 'API total changed during enumeration')
            total = observed_total
            if not rows and start < total:
                self.problem(url, 'Empty API page before total')
                return
            for row_index, row in enumerate(rows):
                row = row if isinstance(row, dict) else {}
                ident = row.get('id')
                marker = 'chromestatus:' + (str(ident) if ident is not None else 'unparsed-' + str(start + row_index))
                if not self.budget(marker, 'documents'):
                    return
                self.state['documents'] += 1
                if ident is None:
                    self.unresolved(url, response, 'api-row:' + str(start + row_index))
                    self.document_done(marker)
                    continue
                seen_ids.add(str(ident))
                feature_url = 'https://chromestatus.com/feature/' + str(ident)
                # Do not copy raw API metadata: it includes personal owner emails.
                text = row.get('summary') or row.get('name') or ''
                self.emit(feature_url, response, {'key': str(ident), 'section': 'feature', 'text': text,
                          'parsed': bool(row.get('name'))}, title=row.get('name'),
                          date=date_value(row.get('created', {}).get('when', '')),
                          revision=row.get('updated', {}).get('when'))
                self.document_done(marker)
            start += len(rows)
            self.persist_checkpoint([url])
            if start >= total:
                self.state['pagination_exhausted'] = True
                self.state['pending'] = []
                if len(seen_ids) != total:
                    self.problem(url, 'Unique API IDs do not match total')
                return
        self.problem(url, 'Page limit reached')

    def collect_apple(self):
        base = self.source['url']
        endpoint = lambda u: 'https://developer.apple.com/tutorials/data' + urlparse(u).path.lower().removesuffix('.md') + '.json'
        response = self.get(endpoint(base))
        data = json_body(response)
        self.state['pages'] = 1
        pending, seen = [], set()
        refs = data.get('references', {})
        for section in data['topicSections']:
            for ident in section['identifiers']:
                reference = refs.get(ident, {})
                path = reference.get('url') or '/documentation/' + ident.split('/documentation/')[-1]
                url = urljoin('https://developer.apple.com', path).lower()
                if re.search(self.source['discovery']['include_url_pattern'], url):
                    pending.append(url)
                else:
                    self.unresolved(base, response, key='topic:' + ident)
        if not pending:
            self.unresolved(base, response, key='index')
            self.problem(base, 'No Safari release topics')
        self.state['pagination_exhausted'] = True
        while pending:
            if not self.budget(pending[0], 'documents'):
                break
            url = pending.pop(0)
            if url in seen:
                continue
            seen.add(url)
            self.state['documents'] += 1
            try:
                document = self.get(endpoint(url))
                data = json_body(document)
                date = date_value(docc_text(data.get('abstract', [])))
                if self.allowed_date(date, current=True):
                    units = docc_items(data)
                    if not units:
                        self.unresolved(url, document)
                    for unit in units:
                        self.emit(url, document, unit, date=date)
                    self.document_done(url)
                    # Topic sections are explicit continuations, not arbitrary related links.
                    for section in data.get('topicSections', []):
                        for ident in section.get('identifiers', []):
                            ref = data.get('references', {}).get(ident, {})
                            related = urljoin('https://developer.apple.com', ref.get('url', '')).lower()
                            if re.search(self.source['discovery']['include_url_pattern'], related) and related not in seen:
                                pending.append(related)
                else:
                    self.state['excluded_by_date'].append(url)
                    self.document_done(url)
            except Exception as error:
                self.unresolved(url, response, key='discovered-document')
                self.problem(url, str(error))
            self.persist_checkpoint(pending)
        self.state['pending'] = pending

    def collect_github(self):
        parts = urlparse(self.source['url']).path.strip('/').split('/')
        url = 'https://api.github.com/repos/%s/%s/releases?per_page=10&page=1' % tuple(parts[:2])
        visited = set()
        while url:
            if url in visited:
                self.problem(url, 'Pagination loop or page limit')
                self.state['pending'] = [url]
                return
            if not self.budget(url, 'pages'):
                return
            visited.add(url)
            response = self.get(url)
            self.state['pages'] += 1
            rows = json_body(response)
            if not isinstance(rows, list):
                raise ValueError('GitHub release response is not a list')
            for row_index, row in enumerate(rows):
                if not isinstance(row, dict) or not row.get('html_url') or 'id' not in row:
                    self.unresolved(url, response, key='release-row:' + str(row_index))
                    continue
                document_url = row['html_url']
                if not self.budget(document_url, 'documents'):
                    return
                self.state['documents'] += 1
                date = date_value(row.get('published_at'))
                if not self.allowed_date(date, current=self.state['pages'] == 1):
                    self.state['excluded_by_date'].append(document_url)
                    self.document_done(document_url)
                    continue
                units = markdown_items(row.get('body') or '')
                if not units:
                    self.unresolved(document_url, response)
                for unit in units:
                    unit['key'] = str(row['id']) + ':' + unit['key']
                    self.emit(document_url, response, unit, date=date, revision=row.get('tag_name'), version=row.get('tag_name'))
                self.document_done(document_url)
            link = response.headers.get('link', response.headers.get('Link', ''))
            next_urls = re.findall(r'<([^>]+)>;\s*rel="next"', link)
            url = next_urls[0] if next_urls else None
            if url and urlparse(url).netloc != 'api.github.com':
                raise ValueError('Unexpected GitHub pagination host')
            self.persist_checkpoint([url] if url else [])
        self.state['pagination_exhausted'] = True

    def collect_markdown(self):
        source_url = self.source['url']
        path = urlparse(source_url).path.replace('/blob/', '/', 1)
        response = self.get('https://raw.githubusercontent.com' + path)
        self.state['documents'] = 1
        units = markdown_items(response.text())
        if not units:
            self.unresolved(source_url, response)
        for unit in units:
            self.emit(source_url, response, unit)
        self.state['pagination_exhausted'] = True

    def collect_whale(self):
        # Official homepage script chunks/866-*.js calls this service/section.
        # https://v1.whale.naver.com/ko/whats_new/notice/ embeds the same notice board.
        base = 'https://notice.naver.com/api/v1/services/whalehomepage/notices/'
        total, seen = None, set()
        page = 1
        while True:
            url = base + '?sectionId=199&page=%s&pageSize=20' % page
            if not self.budget(url, 'pages'):
                return
            response = self.get(url)
            self.state['pages'] += 1
            data = json_body(response)
            rows, info = data['item'], data['pageInfo']
            if total is not None and total != info['totalSize']:
                self.problem(url, 'Whale API total changed')
            total = info['totalSize']
            if info['pageNum'] != page or (not rows and len(seen) < total):
                raise ValueError('Whale pagination mismatch')
            for row_index, row in enumerate(rows):
                if not isinstance(row, dict) or 'id' not in row:
                    self.unresolved(url, response, key='notice-row:' + str(row_index))
                    continue
                ident = str(row['id'])
                if not self.budget(base + ident, 'documents'):
                    return
                seen.add(ident)
                self.state['documents'] += 1
                public_url = self.source['url'] + '?id=' + ident
                date = date_value(row.get('regDate'))
                if not self.allowed_date(date, current=page == 1):
                    self.state['excluded_by_date'].append(public_url)
                    self.document_done(base + ident)
                    continue
                try:
                    detail = self.get(base + ident)
                    payload = json_body(detail)
                    payload = payload.get('item', payload)
                    content = payload.get('renderHtml') or payload.get('content') or payload.get('contents') or ''
                    root = Tree(content).root
                    units = blocks(root)
                    if not units:
                        self.unresolved(public_url, detail)
                    for unit in units:
                        self.emit(public_url, detail, unit, date=date, revision=row.get('modDate'))
                    self.document_done(base + ident)
                except Exception as error:
                    self.unresolved(public_url, response, 'notice:' + ident)
                    self.problem(public_url, str(error))
            if page >= info['totalPageSize']:
                self.state['pagination_exhausted'] = True
                self.state['pending'] = []
                if len(seen) != total:
                    self.problem(url, 'Whale unique IDs differ from total')
                return
            self.persist_checkpoint([base + '?sectionId=199&page=%s&pageSize=20' % (page + 1)])
            page += 1
        self.problem(url, 'Page limit reached')
