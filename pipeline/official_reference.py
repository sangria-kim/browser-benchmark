"""Publisher URL scope and the immutable evidence representation for link-only citations."""
import re
from urllib.parse import parse_qsl, unquote, urlsplit, urlunsplit

from pipeline.deduplicate import digest, stable_id


# Some parsers publish a different public address from their discovery endpoint.
# Anchor these rules to the entire URL, including organization and repository on shared hosts.
DETAIL_URLS = {
    'firefox-ios': r'https://www\.firefox\.com/en-US/firefox/ios/\d+(?:\.\d+)*/releasenotes/',
    'firefox-beta': r'https://www\.firefox\.com/en-US/firefox/\d+(?:\.\d+)*beta/releasenotes/',
    'firefox-android': r'https://www\.firefox\.com/en-US/firefox/android/\d+(?:\.\d+)*/releasenotes/',
    'brave-releases': r'https://github\.com/brave/brave-browser/releases/tag/[A-Za-z0-9_.-]+',
    'chrome-enterprise': (r'https://(?:support\.google\.com/chrome/a/answer/10314655'
                          r'|chromeenterprise\.google/release-notes/?)'),
    'chrome-blog': r'https://blog\.google/(?:products/chrome|products-and-platforms/products/chrome)/[\w-]+/',
    'whale-notices': r'https://forum\.whale\.naver\.com/topic/\d+(?:-[^/]+)?/',
}


def normalize_url(value):
    if not isinstance(value, str) or re.search(r'[\s\\\x00-\x1f\x7f]', value):
        raise ValueError('Invalid official URL')
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not re.fullmatch(r'[a-zA-Z0-9.-]+(?::443)?', parts.netloc)
            or not parts.hostname or parts.port not in (None, 443)):
        raise ValueError('Official citations need an HTTPS publisher URL')
    path = parts.path or '/'
    if (re.search(r'%(?:2f|5c|25|3f|23|0[0-9a-f]|1[0-9a-f]|7f)', path, re.I)
            or '//' in path or any(p in ('.', '..') for p in unquote(path).split('/'))):
        raise ValueError('Invalid publisher path')
    return urlunsplit(('https', parts.hostname.lower(), path, parts.query, parts.fragment))


def accepts_url(source, url, *, observed=False):
    """Match a normalized URL. The pinned Chrome feed can include cross-category articles."""
    parts = urlsplit(url)
    base = urlunsplit((parts.scheme, parts.netloc, parts.path, '', ''))
    sid = source['source_id']
    if parts.query:
        query = parse_qsl(parts.query, keep_blank_values=True)
        if sid == 'chrome-enterprise':
            if base == 'https://release-notes-787862449254.us-central1.run.app/features':
                return (len(query) == 2 and dict(query).get('lang') == 'en'
                        and re.fullmatch(r'[0-9]+', dict(query).get('version', '')) is not None)
            if query != [('hl', 'en')]:
                return False
        elif sid == 'whale-release-history':
            return (base == source['url'] and len(query) == 1 and query[0][0] == 'id'
                    and query[0][1].isdigit())
        else:
            return False
    if base == source['url']:
        return True
    if sid == 'chrome-blog' and observed and parts.netloc == 'blog.google':
        return bool(re.fullmatch(r'/(?:[\w-]+/)+', parts.path))
    if sid in DETAIL_URLS:
        return re.fullmatch(DETAIL_URLS[sid], base) is not None
    pattern = source['discovery']['include_url_pattern']
    return bool(pattern and re.fullmatch(pattern, base))


def reference_row(source, url, observed_at):
    key = 'official-url:' + digest(url)
    ident = stable_id('src', [source['source_id'], url, key])
    checksum = digest({'kind': 'official_url', 'source_id': source['source_id'], 'url': url})
    evidence = dict(url=url, section=None, source_revision=None, content_sha256=checksum,
                    observed_at=observed_at, excerpt='')
    snapshot = dict(title=None, summary=None, evidence=evidence, published_at=None, observed_at=observed_at,
                    channel='unknown', platform=['unknown'], version=None, item_type='unknown',
                    record_status='reference', lifecycle='unknown')
    revision = dict(snapshot, revision_id=stable_id('sr', [ident, checksum]),
                    content_sha256=checksum, source_revision=None)
    return dict(snapshot, schema_version=2, source_id=source['source_id'], browser=source['browser'],
                source_item_id=ident, item_key=key, origin='reference', experiment_kind=None,
                source_location=url, source_symbol=None, revisions=[revision])
