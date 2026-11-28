"""Verify a future Firefox iOS rollout from cutoff-pinned Mozilla meeting notes."""
import hashlib
import json
import re
from datetime import timedelta, timezone
from urllib.parse import urlencode

from pipeline.temporal import instant

API = 'https://wiki.mozilla.org/api.php'
PREFIX = 'Firefox/Channels/Meetings/'


def meeting_requests(cutoff):
    end = instant(cutoff).astimezone(timezone.utc)
    thursday = end.date() - timedelta(days=(end.weekday() - 3) % 7)
    for offset in (0, 7):
        title = PREFIX + (thursday - timedelta(days=offset)).isoformat()
        query = dict(action='query', format='json', formatversion='2', prop='revisions', titles=title,
                     rvprop='ids|timestamp|content', rvslots='main', rvlimit='1',
                     rvstart=end.isoformat().replace('+00:00', 'Z'), rvdir='older')
        yield title, API + '?' + urlencode(query)


def pinned_revision(response, title, url, cutoff):
    if response.url != url:
        raise ValueError('Unexpected Mozilla schedule response URL')
    data = json.loads(response.body)
    if data.get('error') or data.get('warnings') or data.get('batchcomplete') is not True:
        raise ValueError('Incomplete Mozilla schedule response')
    pages = data['query']['pages']
    if not isinstance(pages, list) or len(pages) != 1:
        raise ValueError('Ambiguous Mozilla schedule page')
    page = pages[0]
    if page.get('title') != title or page.get('ns') != 0 or 'redirect' in page:
        raise ValueError('Wrong Mozilla schedule page identity')
    if page.get('missing') is True:
        if page.get('revisions'):
            raise ValueError('Missing schedule page has revisions')
        return None
    if type(page.get('pageid')) is not int or page['pageid'] <= 0:
        raise ValueError('Invalid Mozilla schedule page ID')
    revisions = page.get('revisions', [])
    if revisions == []:
        return None  # This page had no revision at the requested cutoff.
    if not isinstance(revisions, list) or len(revisions) != 1:
        raise ValueError('Ambiguous Mozilla schedule revision')
    revision = revisions[0]
    stamp = instant(revision['timestamp'])
    slot = revision['slots']['main']
    if (type(revision.get('revid')) is not int or revision['revid'] <= 0
            or stamp > instant(cutoff) or stamp.date().isoformat() < title.removeprefix(PREFIX)
            or slot.get('contentmodel') != 'wikitext' or slot.get('contentformat') != 'text/x-wiki'
            or not isinstance(slot.get('content'), str) or not slot['content'].strip()):
        raise ValueError('Unverified Mozilla schedule revision or timestamp')
    return revision


def scheduled_release(version, cutoff, fetch):
    """Return a proof, not feature evidence. Unrecognized or stale wording cannot defer."""
    if not re.fullmatch(r'\d+(?:\.\d+)+', version):
        raise ValueError('Invalid Firefox iOS schedule version')
    identity = re.compile(r'(?<![\d.])' + re.escape(version) + r'(?![\d.])')
    wording = re.compile(r'\*+\s+Firefox iOS ' + re.escape(version)
                         + r' scheduled to start phased rollout at (\d{2}:\d{2}) UTC on (\d{4}-\d{2}-\d{2})\.?')
    for title, url in meeting_requests(cutoff):
        response = fetch(url)
        revision = pinned_revision(response, title, url, cutoff)
        if revision is None:
            continue
        sections = re.split(r'(?m)^==\s*([^=\n]+?)\s*==\s*$', revision['slots']['main']['content'])
        schedules = [sections[i + 1] for i in range(1, len(sections), 2) if sections[i] == 'Schedule Update']
        if len(schedules) != 1:
            raise ValueError('Missing or ambiguous Mozilla Schedule Update section')
        section, = schedules
        if any(marker in section.lower() for marker in ('<!--', '{{', '<nowiki')):
            raise ValueError('Unsupported markup in Mozilla schedule')
        lines = [' '.join(line.split()) for line in section.splitlines() if identity.search(line)]
        if not lines:
            continue
        # A newer cancellation, build-only notice or conflicting time must not
        # fall through to an older positive schedule for this version.
        matches = [wording.fullmatch(line) for line in lines]
        if any(match is None for match in matches):
            return None
        stamps = {instant(match[2] + 'T' + match[1] + ':00Z') for match in matches}
        if len(stamps) != 1:
            return None
        scheduled, = stamps
        published = instant(revision['timestamp'])
        if not instant(cutoff) < scheduled <= published + timedelta(days=14):
            return None
        return dict(state='scheduled', version=version, scheduled_at=scheduled.isoformat(),
                    recheck_at=scheduled.isoformat(), published_at=published.isoformat(),
                    revision_id=revision['revid'], source_url='https://wiki.mozilla.org/index.php?'
                    + urlencode(dict(title=title, oldid=revision['revid'])), evidence_quote=lines[0].lstrip('* '),
                    response_sha256=hashlib.sha256(response.body).hexdigest(), observed_at=response.observed_at)
    return None
