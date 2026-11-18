"""Build a portable homepage while preserving the full research explorer."""
import json
from pipeline.reporting.newsletter import DASHBOARD, kst_day, latest_reports, make_cards, make_issue, read, source_owners


def write_home(output, root, payload, reports, selection):
    cards = make_cards(payload['events'], reports, payload['catalog'], source_owners(selection))
    daily = DASHBOARD / 'daily'
    current = latest_reports(reports)
    editions = {(i['day'], i['revision']): i for i in read(daily / 'initial-issues.json')}
    for archive in sorted(root.glob('reports/generated/*/newsletter-r*.json')):
        issue = read(archive)
        editions[issue['day'], issue['revision']] = issue
    for day in {c['day'] for c in cards} | set(current):
        report = current.get(day)
        key = (day, report['revision'] if report else 0)
        if key not in editions:
            editions[key] = make_issue(day, cards, kst_day(payload['built_at']), report)
    data = dict(cards=cards, issues=sorted(editions.values(), key=lambda i: (i['day'], i['revision']), reverse=True),
                source=payload['source'])
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', r'\u003c')
    html = (daily / 'page.html').read_text()
    html = html.replace('<!--STYLE-->', (daily / 'style.css').read_text())
    html = html.replace('<!--APP-->', (daily / 'app.js').read_text())
    (output / 'index.html').write_text(html.replace('<!--DATA-->', encoded))
