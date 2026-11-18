"""Project public feature evidence into Korean cards and a compact daily edition."""
import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')
DASHBOARD = Path(__file__).resolve().parents[2] / 'dashboard'
CHANNELS = {
    'stable': '정식판', 'beta': '베타', 'developer': '개발자판', 'nightly': '나이틀리',
    'stable_and_beta': '정식·베타', 'Proposed': '제안', 'Planned': '계획',
    'source-main': '소스 관찰', 'experiment_source_main': '소스 실험',
    'public_rollout_announced': '배포 발표', 'Developer trial / Finch plan': '개발자 시험 계획',
    'stable_browser_early_preview_feature': '정식판 내 초기 미리보기',
    'stable_browser_with_optional_windows_preview_update': '정식판 · Windows 미리보기 필요',
}
QUESTIONS = (
    ('로컬 네트워크|내부망|주변 기기', '사이트가 주변 기기에 접근하려는 이유를 허용 전에 알 수 있을까? 한 번 준 권한은 어디서 되돌릴까?'),
    ('단축키|키보드|접근성', '키보드만 사용할 때 같은 작업을 끝낼 수 있을까? 시스템 단축키나 보조 기술과 충돌하는 단계는 어디일까?'),
    ('다크 모드|웹사이트를 어둡게', '야간에 밝은 페이지를 열 때 글자와 이미지의 가독성을 어떻게 유지할까?'),
    ('캡처|스크린샷', '민감한 탭의 캡처 허용 범위와 저장 결과를 사용자가 예측할 수 있을까?'),
    ('패스키|로그인|인증|프로필', '다른 기기나 계정에서 다시 로그인할 때 어느 인증 수단을 선택해야 하는지 알 수 있을까?'),
    ('권한|알림|차단|추적', '허용 또는 차단의 영향을 선택 전에 알 수 있을까? 잘못 고른 설정을 되돌리는 데 몇 단계가 필요할까?'),
    ('재생|영상|오디오|미디어', '탭이나 출력 기기를 바꿔도 현재 재생 상태를 알 수 있고 같은 위치에서 이어볼 수 있을까?'),
    ('탭|분할|창마다', '탭이 많을 때 원하는 페이지를 찾고 원래 읽던 위치로 돌아가는 데 몇 단계가 필요할까?'),
    ('AI|Gemini|검색|주소창', '검색과 AI 중 어느 동작이 실행되는지, 어떤 페이지 내용이 전달되는지 실행 전에 알 수 있을까?'),
    ('지원|종료|예고|목표|목록', '지원 범위가 바뀔 때 영향을 받는 사용자를 어떻게 식별하고 대체 경로를 언제 안내할까?'),
)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def kst_day(stamp):
    return datetime.fromisoformat(stamp.replace('Z', '+00:00')).astimezone(KST).date().isoformat()


def safe_url(value):
    try:
        url = urlsplit(value or '')
        return value if url.scheme == 'https' and url.hostname and not (url.username or url.password) else ''
    except ValueError:
        return ''


def text_value(value):
    if isinstance(value, dict):
        return ' · '.join(f'{k} {text_value(v)}' for k, v in value.items() if v)
    if isinstance(value, list):
        return ' / '.join(str(v) for v in value)
    return str(value or '')


def short_title(identifier, candidates, overrides, summaries):
    if identifier in overrides:
        return overrides[identifier]
    specific = summaries['subjects'].get('feature_event:' + identifier, {})
    for title in candidates:
        if title and specific.get('title') == title:
            return specific['summary']
        if title in summaries['titles']:
            return summaries['titles'][title]
    for title in candidates:
        if title and re.search('[가-힣]', title):
            return re.split(r'[.!?]\s|\n', title)[0][:70]
    topic = next((t for t in reversed(candidates) if t), identifier)
    return f'{topic[:48]} · 공식 문서 변경'


def question_for(card, preferred):
    if preferred:
        return preferred
    for pattern, question in QUESTIONS:
        if re.search(pattern, card['title'], re.I):
            return question
    return f'‘{card["title"]}’에서 달라지는 사용 단계를 삼성 브라우저에서도 확인할 수 있을까?'


def latest_reports(reports):
    latest = {}
    for report in reports:
        if report['revision'] > latest.get(report['date'], {}).get('revision', 0):
            latest[report['date']] = report
    return latest


def make_cards(events, reports, catalog, owners=None, board=DASHBOARD):
    featured = read(board / 'daily/featured.json')
    overrides = read(board / 'daily/titles.json')
    source_copy = read(board / 'daily/source-copy.json')
    summaries = read(board / 'card-summaries.json')
    cards = []
    event_sources = {sid for e in events for sid in e.get('source_item_ids', [])}
    for e in events:
        ident = e['event_id']
        copy = featured.get(ident, {})
        scope = e.get('scope') or {}
        scope = scope if isinstance(scope, dict) else {'conditions': scope}
        candidates = [e.get('summary'), (e.get('after') or {}).get('title') if isinstance(e.get('after'), dict) else None]
        title = copy.get('title') or short_title(ident, candidates, overrides, summaries)
        channel = e.get('channel')
        stage = copy.get('stage') or CHANNELS.get(channel)
        if not stage and 'source' in (e.get('verification_status') or '') and e.get('source_revision'):
            stage = '소스 관찰'
        version = e.get('version') or '미확인'
        if e['event_type'].startswith('planned_milestone') or channel in ('Proposed', 'Planned'):
            version = f'목표 {version}' if e.get('version') else '목표 미확인'
        elif e['event_type'] == 'planned_retirement':
            version = f'예고 문서 {version}'
        source_list = [s if isinstance(s, str) else s.get('url') for s in e['sources']]
        cards.append(dict(id=ident, browser=e['browser'], title=title, day=kst_day(e['observed_at']),
                          original=e.get('summary'), brief=copy.get('brief') or e.get('summary') or title,
                          stage=stage or '단계 미확인', version=version, platform=e.get('platform') or [],
                          builds=text_value(scope.get('builds')), condition=copy.get('condition') or text_value(scope.get('conditions')),
                          announced=e.get('announced_at'), effective=e.get('effective_at'), delta=text_value(e.get('delta')),
                          device_test=text_value(scope.get('real_test')) or '실기 확인 기록 없음', sources=[u for u in source_list if safe_url(u)],
                          record='data/events/' + ident + '.json', featured=bool(copy),
                          media=catalog['events'].get(ident, {}).get('media', [])))
        q = e.get('comparison_question') or ''
        cards[-1]['question'] = question_for(cards[-1], copy.get('question') or (q if re.search('[가-힣]', q) else ''))

    # Freeze the observation on first selection. Routine source rechecks must not move older cards.
    source_ids = set()
    source_groups = {}
    for report in sorted(reports, key=lambda r: (r['date'], r['revision'])):
        for item in report['items']:
            ident = item['subject_id']
            if (item['selection_kind'] != 'features' or item['subject_kind'] != 'source_item'
                    or item['action'] != 'selected' or ident in event_sources or ident in source_ids):
                continue
            source_ids.add(ident)
            fact = item['details']
            urls = [url for url in item['source_urls'] if safe_url(url)]
            copy = source_copy.get(fact['title'], {})
            title = copy.get('title') or short_title(ident, [fact['title'], fact['summary']], overrides, summaries)
            version = fact.get('version')
            if not version and urls:
                version = next(iter(parse_qs(urlsplit(urls[0]).query).get('version', [])), None)
            platform = fact.get('platform') or []
            if fact['title'].startswith('On macOS,') and not set(platform) - {'unknown'}:
                platform = ['macOS']
            for url in urls:
                release = re.fullmatch(r'/[a-zA-Z-]+/firefox/(?:android/)?([0-9.]+(?:beta)?)/releasenotes/?', urlsplit(url).path)
                if not version and urlsplit(url).hostname == 'www.firefox.com' and release:
                    version = release.group(1)
            stage = CHANNELS.get(fact.get('channel'), '단계 미확인')
            basis = {'backfill': '과거 보강', 'initial': '초기 기준선'}.get(item['timing'], '원천 문서')
            card = dict(id=ident, browser=fact['browser'], title=title, original=fact['title'], brief=copy.get('brief') or fact['summary'],
                        day=kst_day(item['observed_at'] or item['discovered_at']), stage=basis + ' · ' + stage,
                        version=f'문서 {version}' if version else '미확인', platform=platform, builds='',
                        condition='공식 문서에서 확인한 내용입니다. 설치본의 적용 여부는 미확인입니다.',
                        announced=item['announced_at'], effective=item['effective_at'], delta='', device_test='실기 확인 기록 없음',
                        record=fact['subject_path'], sources=urls, featured=bool(copy),
                        media=catalog.get('sources', {}).get(ident, {}).get('media', []))
            owner = (owners or {}).get(ident)
            group = (owner or ident, card['day'], fact['title'], fact['summary'], stage, basis, tuple(card['platform']), item['announced_at'])
            if group in source_groups:
                grouped = source_groups[group]
                grouped['sources'] = list(dict.fromkeys(grouped['sources'] + urls))
                if version and version not in grouped['document_versions']:
                    grouped['document_versions'].append(version)
                if card['record'] not in grouped['records']:
                    grouped['records'].append(card['record'])
                continue
            card['document_versions'] = [version] if version else []
            card['records'] = [card['record']]
            card['question'] = question_for(card, copy.get('question'))
            source_groups[group] = card
            cards.append(card)
    for card in source_groups.values():
        if card['document_versions']:
            card['version'] = '문서 ' + ' / '.join(sorted(card['document_versions']))
    for card in cards:
        card['media'] = [m for m in card['media'] if m['type'] in ('image', 'video') and safe_url(m['url'])]
        card['platform'] = ['플랫폼 미확인' if p == 'unknown' else p for p in card['platform']] or ['플랫폼 미확인']
    return sorted(cards, key=lambda c: (not c['featured'], c['stage'] != '정식판', not c['media'], c['browser'], c['id']))


def make_issue(day, cards, generated, report=None):
    rows = [c for c in cards if c['day'] == day]
    # Give each browser one headline before selecting a second from the same browser.
    picked, titles, browsers = [], set(), set()
    for first_pass in (True, False):
        for c in rows:
            if len(picked) == 3 or c['title'] in titles or (first_pass and c['browser'] in browsers):
                continue
            picked.append({k: c[k] for k in ('id', 'browser', 'title', 'platform', 'version', 'stage', 'question')})
            if c['featured']:
                picked[-1]['brief'] = c['brief']
            titles.add(c['title'])
            browsers.add(c['browser'])
    return dict(day=day, generated=generated, revision=report['revision'] if report else 0,
                completeness=report.get('completeness') if report else None, count=len(rows), stories=picked)


def source_owners(selection):
    return {r['subject_id']: r['catalog_id'] for r in selection.get('history', [])
            if r['subject_kind'] == 'source_item' and r.get('catalog_id')}


def issue_file(day, revision):
    return f'reports/generated/{day}/newsletter-r{revision}.json'


def new_report_issue(dataset, report, selection):
    reports = [r for r in dataset['report'] if r['date'] < report['date']] + [report]
    cutoff = datetime.fromisoformat(report['cutoff'].replace('Z', '+00:00'))
    events = [e for e in dataset['feature_event']
              if datetime.fromisoformat(e['observed_at'].replace('Z', '+00:00')) <= cutoff]
    cards = make_cards(events, reports, read(DASHBOARD / 'catalog.json'), source_owners(selection))
    return make_issue(report['date'], cards, datetime.now(KST).date().isoformat(), report)
