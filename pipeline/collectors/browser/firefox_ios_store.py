"""Read version-scoped publisher notes from the fixed US App Store listing."""
import json
import re
from datetime import date, datetime, timezone

from pipeline.firefox_ios_store import APP_STORE_ID, APP_STORE_URL, MOZILLA_DEVELOPER
from .html import Node, Tree


VERSION = r'\d+(?:\.\d+)+'
FOOTER = 'Enjoying Firefox? Leave a review.'
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
WEEKDAYS = 'Mon Tue Wed Thu Fri Sat Sun'.split()


def store_stamp(value):
    match = re.fullmatch(r'(\w{3}) (\w{3}) (\d{2}) (\d{4}) (\d{2}):(\d{2}):(\d{2})'
                         r' GMT\+0000 \(Coordinated Universal Time\)', value)
    if not match or match[2] not in MONTHS:
        raise ValueError('Invalid App Store version timestamp')
    stamp = datetime(int(match[4]), MONTHS.index(match[2]) + 1, int(match[3]),
                     *(int(match[i]) for i in (5, 6, 7)), tzinfo=timezone.utc)
    if match[1] != WEEKDAYS[stamp.weekday()]:
        raise ValueError('Conflicting App Store version timestamp')
    return stamp


def units(response):
    if response.url != APP_STORE_URL:
        raise ValueError('Unexpected final Firefox iOS App Store URL')
    html = response.text()
    nodes = list(Tree(html).root.walk())
    canonical = [n.attrs.get('href') for n in nodes
                 if n.tag == 'link' and 'canonical' in n.attrs.get('rel', '').split()]
    if (canonical != [APP_STORE_URL] or '</html>' not in html.lower()
            or [n.attrs.get('lang') for n in nodes if n.tag == 'html'] != ['en-US']):
        raise ValueError('Unexpected Firefox iOS App Store page or locale')

    def script(ident):
        raw, = [n for n in nodes if n.tag == 'script' and n.attrs.get('id') == ident]
        return json.loads(''.join(raw.children))

    author = script('software-application')['author']
    if author['name'] != 'Mozilla' or author['url'] != MOZILLA_DEVELOPER:
        raise ValueError('Unexpected Firefox iOS App Store publisher')
    product, = [p for p in script('serialized-server-data')['data']
                if p.get('intent', {}).get('$kind') == 'ProductPageIntent']
    intent = product['intent']
    if (intent['id'], intent['storefront'], intent['language']) != (APP_STORE_ID, 'us', 'en-US'):
        raise ValueError('Unexpected Firefox iOS App Store product identity')
    shelf = product['data']['shelfMapping']['mostRecentVersion']
    structured = {}
    for group in shelf['seeAllAction']['pageData']['shelves']:
        for row in group['items']:
            if row.get('$kind') != 'TitledParagraph':
                continue
            version = row['primarySubtitle']
            if not re.fullmatch(VERSION, version) or version in structured:
                raise ValueError('Invalid or duplicate App Store version')
            structured[version] = (store_stamp(row['secondarySubtitle']), ' '.join(row['text'].split()))

    containers = [n for n in nodes if n.attrs.get('data-testid') == 'content-modal'
                  and any(t.tag in ('h1', 'h2', 'h3') and t.text() == 'Version History' for t in n.walk())]
    if len(containers) != 1:
        raise ValueError('Missing or ambiguous App Store version history')
    result = {}
    for entry in containers[0].walk():
        if entry.tag != 'li':
            continue
        metadata, = [n for n in entry.walk() if n.has_class('metadata')]
        version_node, = [n for n in metadata.children if isinstance(n, Node) and n.tag == 'span']
        time_node, = [n for n in metadata.children if isinstance(n, Node) and n.tag == 'time']
        text_node, = [n for n in entry.walk() if n.tag == 'p']
        version = version_node.text()
        stamp, raw = structured[version]
        printed = time_node.attrs.get('datetime', '')
        if (version in result or stamp.date().isoformat() != printed
                or date.fromisoformat(printed).isoformat() != printed
                or text_node.text() != raw or not raw):
            raise ValueError('App Store version, date or notes disagree with visible history')
        passage = raw.partition(FOOTER)[0].strip()
        if not passage:
            raise ValueError('Missing Firefox iOS App Store release-note text')
        result[version] = (stamp, {
            'key': f'app-store-{version}', 'section': 'App Store Version History', 'text': passage,
            'parsed': True,
        })
    if not result or result.keys() != structured.keys():
        raise ValueError('Missing or incomplete Firefox iOS App Store version history')
    return result
