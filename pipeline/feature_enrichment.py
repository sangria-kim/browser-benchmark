"""Private, bounded reinspection of missing facts on already selected features."""
import copy
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
import os
import re
from urllib.parse import parse_qsl, unquote, urldefrag, urlsplit

from pipeline import browser_status
from pipeline.collectors.browser.collector import atomic_json, digest, identity, minimal
from pipeline.collectors.browser.html import Tree, blocks, boundary, modification, published
from pipeline.collectors.browser.safari_preview import retry_deadline, stop_safari_requests, verified_release_dates
from pipeline.feature_item import FACT_FIELDS, missing_facts
from pipeline.official_reference import ENTERPRISE_ARCHIVE, accepts_url, enterprise_archive_anchor, normalize_url
from pipeline.run_daily import read, run_lock
from pipeline.temporal import instant

MAX_DOCUMENTS = 4
MAX_FEATURES_PER_DOCUMENT = 16


def enterprise_version_query(url):
    parts = urlsplit(url)
    if (parts.hostname, parts.path) == ('release-notes-787862449254.us-central1.run.app', '/features'):
        return tuple(sorted(parse_qsl(parts.query)))
    return None


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
        self.enterprise_urls = defaultdict(set)
        self.archive_links = defaultdict(set)
        self.restricted_raw, self.hashes = set(), {}
        self.wait = self.prior.get('retry_after')
        self.wait = self.wait if self.wait and instant(self.wait) > datetime.now(timezone.utc) else None
        for feature in index.by_browser[source['browser']]:
            for ident in feature['source_item_ids']:
                row = self.by_id.get(ident)
                if row and not row['item_key'].startswith('feature-facts:'):
                    url = normalize_url(row['evidence']['url'])
                    if accepts_url(source, url, observed=True):
                        self.links[url].append((feature, row))
                        self.document_owners[self.document_key(url)][feature['feature_id']] = feature
                        if self.sid == 'chrome-enterprise':
                            query = enterprise_version_query(url)
                            if query is not None:
                                self.enterprise_urls[query].add(url)
                            anchor = enterprise_archive_anchor(url)
                            if anchor is not None:
                                self.archive_links[anchor].add(url)

    def publisher_page(self, url):
        if self.sid == 'chrome-enterprise' and enterprise_archive_anchor(url) is not None:
            return ENTERPRISE_ARCHIVE
        return urldefrag(url)[0]

    def document_key(self, url):
        if self.sid == 'chrome-enterprise':
            query = enterprise_version_query(url)
            if query is not None:
                return ('enterprise', query)
        return self.publisher_page(url)

    def after_cutoff(self, url):
        # The same resume can skip the product parser of a completed source.
        # Keep its authoritative document exclusion with the response checkpoint.
        if url in self.links or url in self.document_owners:
            blocked = self.collector.progress.setdefault('enrichment_after_cutoff', [])
            if url not in blocked:
                blocked.append(url)
                self.collector.write_progress()

    def archive_targets(self, anchor):
        return self.archive_links.get('', set()) | self.archive_links.get(anchor, set())

    def archive_unit_targets(self, unit):
        release = re.match(r'release:(\d+):', unit['key'])
        return self.archive_targets(release[1]) if release else ()

    def begin_enterprise_page(self, url):
        for target in self.enterprise_urls.get(enterprise_version_query(url), ()):
            self.units.setdefault(target, [])
            self.restricted_raw.add(target)

    def eligible_unit(self, unit, dates=()):
        return unit['parsed'] and all(self.collector.publication_status(value) != 'after_cutoff'
                                      for value in (*dates, unit.get('date')) if value)

    def observe(self, url, response, unit, title=None, *, dates=()):
        targets = (url,)
        if self.sid == 'chrome-enterprise':
            if enterprise_archive_anchor(url) is not None:
                targets = self.archive_unit_targets(unit)
            else:
                targets = self.enterprise_urls.get(enterprise_version_query(url), targets)
        for target in targets:
            if target not in self.links:
                continue
            # Remember that the registered parser examined this document even
            # if it supplied no eligible unit. HTML fallback must not undo it.
            units = self.units[target]
            if self.eligible_unit(unit, dates):
                units.append((unit, title, response))
            else:
                self.restricted_raw.add(target)

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

    def run(self, prior_jobs=(), *, review_only=False):
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
            if review_only:
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
                        job['content_sha256'] = self.raw_hash(evidence)
                    else:
                        # An explicitly reviewed URL can supplement the existing
                        # feature even when its catalog title is translated.
                        # Never offer an unfiltered API envelope or a future unit.
                        observed = [response] if response is not None else [e for _, _, e in units]
                        hashes = sorted({self.raw_hash(e) for e in observed})
                        if len(hashes) == 1:
                            job['content_sha256'] = hashes[0]
                        if (len(hashes) == 1 and url not in self.restricted_raw
                                and all(self.publisher_page(e.url) == self.publisher_page(url) for e in observed)):
                            try:
                                observation = self.candidate(feature, url, None, observed[0])
                            except TimeoutError as exc:
                                job['error'] = str(exc)
                            else:
                                job.update(reference_review=True, reviewed_observation=observation,
                                           review_passages=[minimal(unit['text'], None) for unit, _, _ in units])
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

    def raw_hash(self, response):
        key = id(response)
        if key not in self.hashes:
            self.hashes[key] = self.collector.cache_body(response.body, verify=True)
        return self.hashes[key]

    def evidence(self, url, halted):
        c = self.collector
        target = urldefrag(url)[0]
        if {url, target}.intersection(c.progress.get('enrichment_after_cutoff', ())):
            return None, []
        if url in self.units:
            return None, self.units[url]
        if self.sid == 'chrome-enterprise' and enterprise_archive_anchor(url) is not None:
            # Only the publisher's dated panel can support an archive citation.
            # Never reinterpret an absent, future or failed panel as the whole page.
            return None, []
        if self.sid == 'chrome-enterprise' and enterprise_version_query(url) is not None:
            raise ValueError('No publisher-filtered Enterprise observations for this version in the current run')
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
        if self.sid == 'safari-technology-preview':
            match = re.fullmatch(c.source['discovery']['include_url_pattern'], target)
            if not match:
                raise ValueError('Unrecognized WebKit release evidence')
            dates = verified_release_dates(response, int(match[1]), None, self.sid)
        else:
            dates = published(tree, self.sid, product_body=body), modification(tree, body)
        if any(c.publication_status(value) == 'after_cutoff' for value in dates if value):
            raise ValueError('Only evidence after the run cutoff was observed')
        anchor = unquote(urlsplit(url).fragment)
        units = blocks(body, window_anchors=bool(anchor)) if body is not None else []
        if anchor:
            units = [u for u in units if anchor in u.pop('window_anchors', [])]
        if any(not self.eligible_unit(u) for u in units):
            self.restricted_raw.add(url)
        scoped = [(u, None, response) for u in units if self.eligible_unit(u)]
        return (None if anchor else response), scoped

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
        if self.sid == 'chrome-enterprise' and enterprise_archive_anchor(url) is not None:
            owners = (owner for target in self.archive_unit_targets(unit) for owner, _ in self.links[target])
        else:
            owners = self.document_owners[self.document_key(url)].values()
        return not any(named(owner) for owner in owners if owner['feature_id'] != feature['feature_id'])

    def candidate(self, feature, url, unit, response):
        # Reuse the normal source-row hash, revision and validation code, keeping
        # evidence-only units and their metrics out of product discovery.
        c = copy.copy(self.collector)
        c.source = dict(c.source, channels=[], platforms=[])
        c.fact_review = None
        c.write_records = True
        c.state = dict(discovered=0, processed=0, duplicate=0, unparsed=0)
        c.seen, c.parsed_ids, c.classification_text = {}, set(), {}
        raw_review = unit is None
        key = 'feature-facts:' + feature['feature_id']
        if raw_review:
            key += ':reviewed-document'
            unit = dict(section='', text='', parsed=True)
        ident = identity('src', [self.sid, url, key])
        c.records = {ident: copy.deepcopy(self.by_id[ident])} if ident in self.by_id else {}
        c.emit(url, response, dict(unit, key=key), title=None if raw_review else feature['title'],
               reviewed_document=raw_review)
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
    verify_body(work, job, row['evidence']['content_sha256'])
    return row


def verify_body(work, job, checksum):
    if not re.fullmatch('[0-9a-f]{64}', checksum):
        raise ValueError('Invalid reinspection raw evidence hash')
    path = browser_status.safe_path(work, 'browser/cache/' + checksum)
    if path.is_symlink() or job['content_sha256'] != checksum or digest(path.read_bytes()) != checksum:
        raise ValueError('Feature reinspection raw evidence checksum mismatch')


def verified_reference(work, state, request):
    """Validate an operator's explicit missing-fact decision against a checked URL."""
    url = normalize_url(request.get('url'))
    matches = [job for job in read_jobs(work, state, request['source_id'])
               if job['feature_id'] == request.get('feature_id') and job['url'] == url and job.get('reference_review')]
    if (len(matches) != 1 or 'source_item_id' in request or 'revision_id' in request
            or request.get('change_kind', 'evidence_only') != 'evidence_only'
            or set(request.get('facts', {})) - set(matches[0]['missing_fields'])):
        raise ValueError('Reference review needs the observed URL, selected feature and only missing facts')
    job = matches[0]
    observed = job.get('reviewed_observation')
    if (not observed or observed['item_key'] != 'feature-facts:' + job['feature_id'] + ':reviewed-document'
            or observed['source_id'] != request['source_id'] or observed['evidence']['url'] != url):
        raise ValueError('A checked publisher observation is required for reference review')
    verify_body(work, job, observed['evidence']['content_sha256'])
    quote = request.get('evidence_quote')
    if quote:
        passage = next((text for text in job['review_passages'] if quote in text), None)
        if not passage:
            raise ValueError('Quote must match a passage from the selected official observation')
        observed = dict(observed, classification_text=passage)
    selected = dict(request, url=url, change_kind='evidence_only', source_item_id=observed['source_item_id'],
                    revision_id=observed['revisions'][-1]['revision_id'])
    return selected, observed
