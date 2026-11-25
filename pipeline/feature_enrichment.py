"""Private, bounded reinspection of missing facts on already selected features."""
import copy
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
import re
from urllib.parse import urldefrag

from pipeline import browser_status
from pipeline.collectors.browser.collector import atomic_json, digest, identity, minimal
from pipeline.collectors.browser.html import Tree, blocks, boundary, modification, published
from pipeline.collectors.browser.safari_preview import retry_deadline, stop_safari_requests, verified_release_dates
from pipeline.feature_item import FACT_FIELDS, missing_facts
from pipeline.official_reference import accepts_url, normalize_url
from pipeline.run_daily import read, run_lock
from pipeline.temporal import instant

MAX_DOCUMENTS = 4
MAX_FEATURES_PER_DOCUMENT = 16


class FeatureIndex:
    def __init__(self, repository, private):
        catalog = repository / browser_status.CATALOG
        self.by_browser = defaultdict(list)
        for feature in read(catalog) if catalog.exists() else ():
            self.by_browser[feature['browser']].append(feature)
        self.folder = private.parent / ('.feature-enrichment-' + digest(str(repository).encode()))
        self.folder.mkdir(mode=0o700, exist_ok=True)
        if self.folder.is_symlink() or self.folder.stat().st_uid != os.getuid() or self.folder.stat().st_mode & 0o077:
            raise ValueError('Unsafe private feature reinspection directory')

    def source(self, collector, previous):
        return SourceReview(self, collector, previous)


class SourceReview:
    def __init__(self, index, collector, previous):
        self.collector = collector
        source = collector.source
        self.sid = source['source_id']
        self.history = index.folder / (self.sid + '.json')
        if self.history.is_symlink():
            raise ValueError('Invalid feature reinspection history')
        self.prior = read(self.history) if self.history.exists() else {}
        self.links = defaultdict(list)
        self.document_owners = defaultdict(dict)
        self.by_id = {row['source_item_id']: row for row in previous}
        self.units = defaultdict(list)
        self.wait = self.prior.get('retry_after')
        self.wait = self.wait if self.wait and instant(self.wait) > datetime.now(timezone.utc) else None
        for feature in index.by_browser[source['browser']]:
            for ident in feature['source_item_ids']:
                row = self.by_id.get(ident)
                if row and not row['item_key'].startswith('feature-facts:'):
                    url = normalize_url(row['evidence']['url'])
                    if accepts_url(source, url, observed=True):
                        self.links[url].append((feature, row))
                        self.document_owners[urldefrag(url)[0]][feature['feature_id']] = feature

    def observe(self, url, response, unit, title=None):
        if unit['parsed'] and url in self.links:
            self.units[url].append((unit, title, response))

    def linked_facts(self, features):
        rows = dict(self.by_id)
        remaining = {ident for feature in features for ident in feature['source_item_ids']} - rows.keys()
        if remaining:
            folder = self.collector.destination.parent
            for path in sorted(folder.glob('*.json')):
                if not remaining:
                    break
                if path == self.collector.destination:
                    continue
                if path.name.startswith('edge-policies.part-') and not any(
                        path.stem.endswith(ident[4:6]) for ident in remaining):
                    continue
                for row in read(path):
                    ident = row['source_item_id']
                    if ident in remaining:
                        rows[ident] = row
                        remaining.remove(ident)
        return rows

    def run(self, prior_jobs=()):
        c = self.collector
        previous_urls = {job['url'] for job in prior_jobs}
        previous_jobs = {(job['url'], job['feature_id']): job for job in prior_jobs}
        queued, enrolled_now = defaultdict(list), defaultdict(set)
        for url, owners in self.links.items():
            for feature, row in owners:
                enrolled = self.prior.get(url, {}).get('features', [])
                if row['source_item_id'] in c.seen and 'feature_facts' not in feature and feature['feature_id'] not in enrolled:
                    enrolled_now[url].add(feature['feature_id'])
                if ('feature_facts' in feature or feature['feature_id'] in enrolled
                        or row['source_item_id'] in c.seen):
                    if not set(FACT_FIELDS) <= feature.get('feature_facts', {}).keys():
                        queued[url].append((feature, row))
        # Select a bounded group before reading any additional source files.
        # At the same cutoff a resume reuses its previously selected documents.
        ordered = sorted(queued, key=lambda url: (url not in previous_urls, self.prior.get(url, {}).get('attempt', ''), url))
        jobs, touched = [], {}
        halted = False
        for url in ordered:
            if len(touched) >= MAX_DOCUMENTS:
                break
            tried = self.prior.get(url, {}).get('tried', {})
            owners = sorted(queued[url], key=lambda pair: (
                (url, pair[0]['feature_id']) not in previous_jobs,
                tried.get(pair[0]['feature_id'], ''), pair[0]['feature_id']))
            owners = list({f['feature_id']: (f, r) for f, r in owners}.values())[:MAX_FEATURES_PER_DOCUMENT]
            linked = self.linked_facts([f for f, _ in owners])
            by_feature = {}
            for feature, row in owners:
                slots = missing_facts(feature, linked)
                if slots:
                    by_feature.setdefault(feature['feature_id'], (feature, row, slots))
            if not by_feature:
                continue
            # A complete product checkpoint can resume a failed supplemental
            # read without regenerating earlier, possibly API-backed evidence.
            if prior_jobs:
                for fid in list(by_feature):
                    prior = previous_jobs.get((url, fid))
                    if prior and 'error' not in prior:
                        jobs.append(dict(prior, missing_fields=list(by_feature.pop(fid)[2])))
            touched[url] = [f['feature_id'] for f, _ in owners]
            if not by_feature:
                continue
            response, units, error = None, [], None
            try:
                response, units = self.evidence(url, halted)
            except Exception as exc:
                error = str(exc)
                halted = True
                self.note_failure(exc, url)
            for feature, row, slots in by_feature.values():
                job = dict(feature_id=feature['feature_id'], title=feature['title'], source_id=self.sid,
                           url=url, citation=row['source_item_id'], missing_fields=list(slots))
                if error is not None:
                    job['error'] = error
                else:
                    matched = [entry for entry in units if self.matches(feature, row, url, entry)]
                    if len(matched) == 1:
                        unit, _, evidence = matched[0]
                        try:
                            job['candidate'] = self.candidate(feature, url, unit, evidence)
                        except TimeoutError as exc:
                            job['error'] = str(exc)
                        job['content_sha256'] = c.cache_body(evidence.body, verify=True)
                    elif response is not None:
                        job['content_sha256'] = c.cache_body(response.body, verify=True)
                    else:
                        job['observed_sha256'] = sorted({c.cache_body(e.body, verify=True) for _, _, e in units})
                jobs.append(job)
        if touched or enrolled_now:
            with run_lock(self.history):
                history = read(self.history) if self.history.exists() else {}
                if self.wait:
                    history['retry_after'] = max(history.get('retry_after', ''), self.wait)
                for url in touched.keys() | enrolled_now.keys():
                    entry = history.setdefault(url, {})
                    entry['features'] = sorted(set(entry.get('features', [])) | enrolled_now[url] | set(touched.get(url, [])))
                    if url in touched:
                        entry['attempt'] = c.observed_at
                        entry.setdefault('tried', {}).update(dict.fromkeys(touched[url], c.observed_at))
                atomic_json(self.history, history)
        return jobs

    def evidence(self, url, halted):
        c = self.collector
        if self.units.get(url):
            return None, self.units[url]
        target = urldefrag(url)[0]
        if any(e['url'] == target for e in c.state['errors']):
            raise ValueError('The registered collector could not verify this document')
        if target not in c.cache and target not in c.progress['responses']:
            used = max(c.new_documents, c.state['documents'])
            if self.wait or halted or c.enrichment_blocked or used >= c.source['discovery']['max_documents']:
                raise ValueError('Deferred by the source request limit or publisher response')
            c.new_documents = used + 1
        response = c.get(target, direct=True)
        if urldefrag(normalize_url(response.url))[0] != target:
            raise ValueError('Official evidence URL redirected')
        rendered = response.text()
        if '<html' in rendered.lower() and '</html>' not in rendered.lower():
            raise ValueError('Truncated HTML evidence')
        tree = Tree(rendered).root
        body = boundary(tree, self.sid, document_url=target)
        if body is None:
            return response, []
        if self.sid == 'safari-technology-preview':
            match = re.fullmatch(c.source['discovery']['include_url_pattern'], target)
            if not match:
                raise ValueError('Unrecognized WebKit release evidence')
            dates = verified_release_dates(response, int(match[1]), None, self.sid)
        else:
            dates = published(tree, self.sid, product_body=body), modification(tree, body)
        if any(c.publication_status(value) == 'after_cutoff' for value in dates if value):
            raise ValueError('Only evidence after the run cutoff was observed')
        return response, [(u, None, response) for u in blocks(body) if u['parsed']]

    def note_failure(self, error, url):
        now = datetime.now(timezone.utc)
        limits = [retry_deadline(str(value), now) for name, value in (getattr(error, 'headers', None) or {}).items()
                  if name.lower() == 'retry-after']
        until = max((date for date in limits if date is not None), default=None)
        if until is None and getattr(error, 'code', None) == 429:
            until = now + timedelta(seconds=30)
        if until is not None:
            self.wait = until.isoformat()
        if self.sid == 'safari-technology-preview':
            stop_safari_requests(self.collector, error, url, [url])

    @staticmethod
    def labels(feature):
        return {value.casefold().strip() for value in [feature['title'], *feature['aliases']]
                if isinstance(value, str) and value.strip()}

    def matches(self, feature, citation, url, entry):
        unit, title, _ = entry
        passage = ' '.join(filter(None, (title, unit['text']))).casefold()
        def named(owner):
            return any(re.search(r'(?<!\w)' + re.escape(label) + r'(?!\w)', passage)
                       for label in self.labels(owner))
        if not named(feature):
            # A previously selected quote can identify a translated catalog title.
            ident = identity('src', [self.sid, url, unit['key']])
            if ident != citation['source_item_id'] or any(sibling['feature_id'] != feature['feature_id']
                    and row['source_item_id'] == ident for sibling, row in self.links[url]):
                return False
            pins = feature.get('source_revision_ids', {}).get(ident, [])
            quotes = feature.get('source_revision_excerpts', {})
            if not any(quotes.get(pin) and quotes[pin].casefold() in passage for pin in pins):
                return False
        return not any(named(sibling) for fid, sibling in self.document_owners[urldefrag(url)[0]].items()
                       if fid != feature['feature_id'])

    def candidate(self, feature, url, unit, response):
        # Reuse the normal source-row hash, revision and validation code, keeping
        # evidence-only units and their metrics out of product discovery.
        c = copy.copy(self.collector)
        c.source = dict(c.source, channels=[], platforms=[])
        c.fact_review = None
        c.write_records = True
        c.state = dict(discovered=0, processed=0, duplicate=0, unparsed=0)
        c.seen, c.parsed_ids, c.classification_text = {}, set(), {}
        key = 'feature-facts:' + feature['feature_id']
        ident = identity('src', [self.sid, url, key])
        c.records = {ident: copy.deepcopy(self.by_id[ident])} if ident in self.by_id else {}
        c.emit(url, response, dict(unit, key=key), title=feature['title'])
        row = c.records[ident]
        return dict(row, classification_text=minimal(unit['text'], None))


def read_jobs(work, state, sid):
    expected = state['source_results'][sid].get('enrichment_sha256')
    if not expected:
        return []
    path = browser_status.safe_path(work, 'enrichment/' + sid + '.json')
    raw = path.read_bytes()
    if path.is_symlink() or digest(raw) != expected:
        raise ValueError('Feature reinspection checkpoint checksum mismatch')
    return json.loads(raw)


def verified_candidate(work, state, request):
    """Resolve a classifier selection from its exact feature-scoped reinspection."""
    sid = request['source_id']
    matches = [job for job in read_jobs(work, state, sid) if job['feature_id'] == request.get('feature_id')
               and job.get('candidate', {}).get('source_item_id') == request.get('source_item_id')]
    if len(matches) != 1:
        raise ValueError('No unique reinspection for the selected feature')
    job = matches[0]
    row = job['candidate']
    if (row['revisions'][-1]['revision_id'] != request.get('revision_id')
            or request.get('change_kind', 'evidence_only') != 'evidence_only'
            or set(request.get('facts', {})) - set(job['missing_fields'])):
        raise ValueError('Reinspection requires the observed revision and only missing facts')
    checksum = row['evidence']['content_sha256']
    if not re.fullmatch('[0-9a-f]{64}', checksum):
        raise ValueError('Invalid reinspection raw evidence hash')
    path = browser_status.safe_path(work, 'browser/cache/' + checksum)
    if path.is_symlink() or job['content_sha256'] != checksum or digest(path.read_bytes()) != checksum:
        raise ValueError('Feature reinspection raw evidence checksum mismatch')
    return row
