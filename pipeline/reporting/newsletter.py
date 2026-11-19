"""Project public feature evidence into Korean cards and a compact daily edition."""
from collections import defaultdict
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
    ('프로필 데이터 분리', '프로필을 바꿔 앱을 열 때 이전 계정의 탭이나 기록이 잠시 노출될 수 있을까?'),
    ('브라우저 실행 단축', '같은 기기에서 브라우저를 다시 열 때 첫 페이지를 조작할 수 있기까지 얼마나 기다릴까?'),
    ('그래픽 프로세스 격리', '격리 설정을 바꾸면 지원 기기에서 영상 재생과 페이지 그리기의 안정성이 어떻게 달라질까?'),
    ('공지 날짜 정정', '공지 날짜 정정을 실제 업데이트와 구별해 사용자에게 어떻게 보여줄까?'),
    ('기본 브라우저 지정', '시스템 설정으로 이동한 사용자가 기본 브라우저 지정을 마치고 원래 탭으로 돌아올 수 있을까?'),
    ('데이터 절약', '데이터 절약을 켰을 때 절약량과 페이지 품질의 변화를 사용자가 확인할 수 있을까?'),
    ('웹 도구 기본값', 'AI가 페이지 도구를 호출하기 전에 사용자가 대상 사이트와 수행할 작업을 확인할 수 있을까?'),
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


def read_if_present(path, default):
    return read(path) if path.is_file() else default


def instant(stamp):
    return datetime.fromisoformat(stamp.replace('Z', '+00:00'))


def kst_day(stamp):
    return instant(stamp).astimezone(KST).date().isoformat()


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


PENDING_TITLE = '한글 기능 제목 편집 대기'


def short_title(identifier, candidates, overrides, summaries):
    candidates = [v for v in candidates if isinstance(v, str) and v.strip()]
    if identifier in overrides:
        return overrides[identifier]
    specific = summaries.get('subjects', {}).get('feature_event:' + identifier, {})
    for title in candidates:
        if title and specific.get('title') == title:
            return specific['summary']
        if title in summaries.get('titles', {}):
            return summaries['titles'][title]
    for title in candidates:
        sentence = re.split(r'[.!?]\s|\n', title)[0].strip()
        if len(sentence) <= 48 and re.search('[가-힣]', sentence):
            return sentence
        # Translate only the documented action. Negations, removals and other
        # operations require their own copy instead of inheriting an addition.
        addition = r'^(?:adds?|introduces?) (?:a |an |the )?(?:new )?'
        if re.match(addition + r'(?:button|control) (?:that |to |for )(?:switch(?:es|ing)?|chang(?:e|es|ing)|adjust(?:s|ing)?) (?:the )?(?:video )?playback (?:speed|rate)\b', sentence, re.I):
            return '재생 속도 조절 버튼 추가'
        if re.match(addition + r'(?:keyboard )?shortcut to copy (?:the )?(?:current )?tab (?:URL|address)\b', sentence, re.I):
            return '현재 탭 주소 복사 단축키 추가'
        if re.match(addition + r'support for (?:using )?vertical tabs\b', sentence, re.I):
            return '세로 탭 지원 추가'
    return PENDING_TITLE


def event_scope(event):
    version = event.get('version')
    platforms = event.get('platform') or []
    if event['event_type'] == 'planned_retirement':
        return ('예고 문서 ' + version if version else '버전 미확인'), platforms, {}
    if not (event['event_type'].startswith('planned_milestone') or event.get('channel') in ('Proposed', 'Planned')):
        return version or '미확인', platforms, {}
    delta = event.get('delta') or {}
    delta = delta if isinstance(delta, dict) else {}
    fields = delta.get('current_individual_api_state') or delta.get('individual_api_status') or delta.get('current_individual_state') or {}
    fields = fields if isinstance(fields, dict) else {}
    names = {'desktop': 'Desktop', 'android': 'Android', 'ios': 'iOS', 'webview': 'WebView'}
    targets = {name: str(fields[key]) for key, name in names.items()
               if isinstance(fields.get(key), int) and fields[key] > 0}
    milestones = list(dict.fromkeys(targets.values()))
    target = version or delta.get('current_target_milestone') or ' / '.join(milestones)
    return (f'목표 {target}' if target else '목표 미확인'), platforms, targets


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
    featured = read_if_present(board / 'daily/featured.json', {})
    overrides = read_if_present(board / 'daily/titles.json', {})
    source_copy = read_if_present(board / 'daily/source-copy.json', {})
    summaries = read_if_present(board / 'card-summaries.json', {'subjects': {}, 'titles': {}})
    cards = []
    event_sources = defaultdict(set)
    for event in events:
        for sid in event.get('source_item_ids', []):
            event_sources[kst_day(event['observed_at']), sid].add(event['event_id'])
    for e in events:
        ident = e['event_id']
        copy = featured.get(ident, {})
        scope = e.get('scope') or {}
        scope = scope if isinstance(scope, dict) else {'conditions': scope}
        candidates = [e.get('summary'), e.get('title'), (e.get('after') or {}).get('title') if isinstance(e.get('after'), dict) else None]
        title = copy.get('title') or short_title(ident, candidates, overrides, summaries)
        channel = e.get('channel')
        stage = copy.get('stage') or CHANNELS.get(channel)
        if not stage and 'source' in (e.get('verification_status') or '') and e.get('source_revision'):
            stage = '소스 관찰'
        version, platforms, targets = event_scope(e)
        source_list = [s if isinstance(s, str) else s.get('url') for s in e['sources']]
        cards.append(dict(id=ident, browser=e['browser'], title=title, day=kst_day(e['observed_at']),
                          original=e.get('summary'), brief=copy.get('brief') or e.get('summary') or title,
                          stage=stage or '단계 미확인', version=version, platform=platforms, targets=targets,
                          builds=text_value(scope.get('builds')), condition=copy.get('condition') or text_value(scope.get('conditions')),
                          announced=e.get('announced_at'), effective=e.get('effective_at'), delta=text_value(e.get('delta')),
                          device_test=text_value(scope.get('real_test')) or '실기 확인 기록 없음', sources=[u for u in source_list if safe_url(u)],
                          record='data/events/' + ident + '.json', featured=bool(copy),
                          media=catalog.get('events', {}).get(ident, {}).get('media', [])))
        q = e.get('comparison_question') or ''
        cards[-1]['question'] = question_for(cards[-1], copy.get('question') or (q if re.search('[가-힣]', q) else ''))

    # Freeze the observation on first selection. Routine source rechecks must not move older cards.
    source_ids = set()
    source_groups = defaultdict(list)
    for report in sorted(reports, key=lambda r: (r['date'], r['revision'])):
        for item in report['items']:
            ident = item['subject_id']
            if (item['selection_kind'] != 'features' or item['subject_kind'] != 'source_item'
                    or item['action'] != 'selected' or ident in source_ids):
                continue
            source_ids.add(ident)
            day = kst_day(item['observed_at'] or item['discovered_at'])
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
                        day=day, stage=basis + ' · ' + stage,
                        version=f'문서 {version}' if version else '미확인', platform=platform, builds='',
                        condition='공식 문서에서 확인한 내용입니다. 설치본의 적용 여부는 미확인입니다.',
                        announced=item['announced_at'], effective=item['effective_at'], delta='', device_test='실기 확인 기록 없음',
                        record=fact['subject_path'], sources=urls, featured=bool(copy),
                        media=catalog.get('sources', {}).get(ident, {}).get('media', []))
            owner = (owners or {}).get(ident)
            group = (owner or ident, card['day'], fact['title'], fact['summary'], stage, basis, tuple(card['platform']), item['announced_at'])
            card['question'] = question_for(card, copy.get('question'))
            source_groups[group].append(card)

    event_cards = {c['id']: c for c in cards}
    for source_rows in source_groups.values():
        first = source_rows[0]
        targets = set().union(*(event_sources[c['day'], c['id']] for c in source_rows))
        if len(targets) == 1:
            primary = event_cards[targets.pop()]
            related = source_rows
        else:
            # Keep the individual observation for media captions before combining versions.
            primary = dict(first, media_version=first['version'])
            versions = sorted({c['version'].removeprefix('문서 ') for c in source_rows if c['version'] != '미확인'})
            if versions:
                primary['version'] = '문서 ' + ' / '.join(versions)
            cards.append(primary)
            related = source_rows[1:]
        if related:
            primary.setdefault('related_sources', []).extend(related)
            primary['sources'] = list(dict.fromkeys(primary['sources'] + [u for c in related for u in c['sources']]))
            primary['records'] = list(dict.fromkeys(primary.get('records', [primary['record']]) + [c['record'] for c in related]))

    def prepare(card):
        card['title_pending'] = card['title'] == PENDING_TITLE
        card['media'] = [m for m in card['media'] if m['type'] in ('image', 'video') and safe_url(m['url'])]
        card['platform'] = ['플랫폼 미확인' if p == 'unknown' else p for p in card['platform']] or ['플랫폼 미확인']

    for card in cards:
        prepare(card)
        for source in card.get('related_sources', []):
            prepare(source)
    return sorted(cards, key=lambda c: (not c['featured'], c['stage'] != '정식판', not c['media'], c['browser'], c['id']))


def make_issue(day, cards, generated, report=None):
    rows = [c for c in cards if c['day'] == day]
    # Give each browser one headline before selecting a second from the same browser.
    picked, titles, browsers = [], set(), set()
    for first_pass in (True, False):
        for c in rows:
            if c['title_pending'] or len(picked) == 3 or c['title'] in titles or (first_pass and c['browser'] in browsers):
                continue
            picked.append({k: c[k] for k in ('id', 'browser', 'title', 'platform', 'version', 'stage', 'question')})
            if c.get('targets'):
                picked[-1]['targets'] = c['targets']
            if c['featured']:
                picked[-1]['brief'] = c['brief']
            titles.add(c['title'])
            browsers.add(c['browser'])
    return dict(day=day, generated=generated, revision=report['revision'] if report else 0,
                completeness=report.get('completeness') if report else None, count=len(rows), pending=sum(c['title_pending'] for c in rows), stories=picked)


def source_owners(selection):
    return {r['subject_id']: r['catalog_id'] for r in selection.get('history', [])
            if r['subject_kind'] == 'source_item' and r.get('catalog_id')}


def issue_file(day, revision):
    return f'reports/generated/{day}/newsletter-r{revision}.json'


def events_for_edition(root, events, visible_reports, cutoff):
    """Resolve corrections to the revision known in the retained report window."""
    items = {i['subject_id']: i for r in visible_reports for i in r['items']
             if i['subject_kind'] == 'feature_event'}
    for event in events:
        item = items.get(event['event_id'])
        details = item['details'] if item else {}
        revision = details.get('subject_revision')
        if revision and revision != event.get('revision'):
            archive_dir = Path('data/event-revisions') / event['event_id']
            pinned = Path(details.get('subject_path') or '')
            archive = root / archive_dir / f'revision-{revision}.json'
            if pinned.parent == archive_dir and (root / pinned).is_file():
                archive = root / pinned
            if archive.is_file():
                event = read(archive)
                if 'source_item_ids' not in event:
                    event['source_item_ids'] = [e['source_item_id'] for e in item.get('evidence', [])]
            else:
                # Old imports can retain only the report evidence. Do not use
                # versions or release scope introduced by a subsequent correction.
                event = dict(event_id=event['event_id'], revision=revision, browser=details['browser'],
                             event_type=details.get('event_type') or 'unknown', version=details.get('version'),
                             channel=details.get('channel'), platform=details.get('platform') or [],
                             observed_at=item['observed_at'], announced_at=item.get('announced_at'),
                             effective_at=item.get('effective_at'), summary=details['title'],
                             delta=details.get('summary'), sources=item['source_urls'],
                             source_item_ids=[e['source_item_id'] for e in item['evidence']])
        if instant(event['observed_at']) <= cutoff:
            yield event


def newsletter_files(root, dataset, report, selection):
    """Render missing editions for the standalone dashboard archive job."""
    board = root / 'dashboard'
    catalog = read_if_present(board / 'catalog.json', {'events': {}})
    initial = read_if_present(board / 'daily/initial-issues.json', [])
    stored = {(i['day'], i['revision']) for i in initial}
    for archive in board.glob('daily/editions/*/newsletter-r*.json'):
        issue = read(archive)
        stored.add((issue['day'], issue['revision']))
    current_key = report['date'], report['revision']
    history = {(r['date'], r['revision']): r for r in dataset.get('report', [])}
    for path in sorted(root.glob('data/reports/history/*/*.json')):
        if path.parent.name <= report['date']:
            r = read(path)
            history[r['date'], r['revision']] = r
    history[current_key] = report
    history = {key: r for key, r in sorted(history.items())
               if key <= current_key and instant(r['cutoff']) <= instant(report['cutoff'])}
    generated = datetime.now(KST).date().isoformat()
    files = {}

    def cards_at(key):
        cutoff = instant(history[key]['cutoff'])
        visible = [r for k, r in history.items() if k <= key and instant(r['cutoff']) <= cutoff]
        events = list(events_for_edition(root, dataset['feature_event'], visible, cutoff))
        changes = [r for r in selection.get('history', []) if instant(r['effective_at']) <= cutoff]
        return make_cards(events, visible, catalog, source_owners({'history': changes}), board)

    def missing(key):
        return key not in stored and not (root / issue_file(*key)).is_file()

    def save(day, revision, cards, basis):
        issue = make_issue(day, cards, generated, basis)
        files[issue_file(day, revision)] = json.dumps(issue, ensure_ascii=False, indent=2) + '\n'

    current_cards = cards_at(current_key)
    for key, basis in history.items():
        if missing(key):
            save(*key, current_cards if key == current_key else cards_at(key), basis)

    report_days = {key[0] for key in history}
    for day in sorted({c['day'] for c in current_cards} - report_days):
        if day < report['date'] and missing((day, 0)):
            save(day, 0, current_cards, None)
    return files
