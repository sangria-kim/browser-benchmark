'use strict';
const data = JSON.parse(document.getElementById('daily-data').textContent);
const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
const brands = {
  chrome: ['Chrome', '크롬'],
  edge: ['Edge', '엣지'],
  firefox: ['Firefox', '파이어폭스'],
  safari: ['Safari', '사파리'],
  brave: ['Brave', '브레이브'],
  whale: ['웨일', 'Whale'],
  opera: ['Opera', '오페라'],
  vivaldi: ['Vivaldi', '비발디'],
};
const brand = (id) => brands[id]?.[0] || id;
const byId = new Map(data.cards.map((c) => [c.id, c]));
for (const c of data.cards) {
  for (const source of c.related_sources || []) byId.set(source.id, source);
}
const byDay = new Map();
for (const c of data.cards) {
  if (!byDay.has(c.day)) byDay.set(c.day, []);
  byDay.get(c.day).push(c);
}
const days = [...byDay.keys()].sort().reverse();
const editions = [...data.drafts, ...data.issues];
const issueDays = [...new Set(editions.map((i) => i.day))].sort().reverse();
const layoutNames = { board: '브라우저 보드', observatory: '관측소' };
const sections = { updates: '기능 카드', letter: '뉴스레터' };
const weekday = (day) =>
  new Intl.DateTimeFormat('ko-KR', { weekday: 'short', timeZone: 'UTC' }).format(
    new Date(day + 'T00:00:00Z'),
  );
const dateText = (day) => day.slice(5, 7) + '월 ' + day.slice(8) + '일 (' + weekday(day) + ')';
const href = (layout, section, day, rev) =>
  '#' + [layout, section, day, ...(rev == null ? [] : [rev])].join('/');
const mark = (browser) =>
  '<span class="browser-name"><i class="dot ' + esc(browser) + '"></i>' + esc(brand(browser)) + '</span>';
const chip = (value) => '<span class="chip">' + esc(value) + '</span>';
function scopeLine(c) {
  const targets = Object.keys(c.targets || {});
  const platforms = targets.length ? ['목표 ' + targets.join(' / ')] : c.platform;
  return [c.version === '미확인' ? '버전 미확인' : c.version, ...platforms].join(' · ');
}
let state,
  query = '',
  browserFilter = '',
  missing = false,
  generated = '';
let opened = null,
  opener = null;

function parseRoute() {
  const [mode, tab, date, revision] = location.hash.slice(1).split('/');
  let saved;
  try {
    saved = localStorage.getItem('browser-benchmark:layout');
  } catch {}
  const layout = Object.hasOwn(layoutNames, mode) ? mode : saved === 'observatory' ? saved : 'board';
  const section = tab === 'letter' ? 'letter' : 'updates';
  const dates = section === 'letter' ? issueDays : days;
  const day = dates.includes(date) ? date : dates[0];
  const issue =
    editions.find((i) => i.day === day && String(i.revision) === revision) ||
    editions.find((i) => i.day === day);
  return { layout, section, day, issue };
}
function navLink(url, label, active) {
  return '<a href="' + esc(url) + '"' + (active ? ' aria-current="page"' : '') + '>' + esc(label) + '</a>';
}
function mediaURL(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && !u.username && !u.password ? u.href : '';
  } catch {
    return '';
  }
}
function external(url, label) {
  const safe = mediaURL(url);
  return safe
    ? '<a href="' + esc(safe) + '" target="_blank" rel="noopener noreferrer">' + esc(label) + ' ↗</a>'
    : '';
}
function sourceLink(value) {
  const url = new URL(value);
  const release = /^(?:www\.)?firefox\.com$/.test(url.hostname) &&
    url.pathname.match(/\/firefox\/(android\/|ios\/)?(\d+(?:\.\d+)*)(beta)?\/releasenotes\/?$/);
  if (!release) return external(value, url.hostname);
  const platform = { 'android/': ' Android', 'ios/': ' iOS' }[release[1]] || '';
  return external(value, `Firefox${platform} ${release[2]} ${release[3] ? '베타' : '정식판'} 릴리스 노트`);
}
const key = (c) => 'browser-benchmark:daily:media:' + c.id;
function localMedia(c) {
  try {
    const m = JSON.parse(localStorage.getItem(key(c)));
    return m && ['image', 'video'].includes(m.type) && mediaURL(m.url) ? m : null;
  } catch {
    return null;
  }
}
function evidenceMedia(card) {
  const items = [];
  for (const owner of [card, ...(card.related_sources || [])]) {
    for (const media of owner.media) items.push({ media, owner, local: false });
    const saved = localMedia(owner);
    if (saved) items.push({ media: saved, owner, local: true });
  }
  return items;
}
function mediaLabel(c) {
  const item = evidenceMedia(c)[0];
  if (!item) return '화면 미확보';
  return (
    (item.owner.id === c.id ? '' : '원천 ') +
    (item.local ? '내 ' : '공식 ') +
    (item.media.type === 'video' ? '영상' : '화면')
  );
}
function archive() {
  const { layout, section, day, issue } = state;
  const issues = data.issues.filter((i) => !generated || i.generated === generated);
  const entries = section === 'updates' ? days.map((d) => ({ day: d, count: byDay.get(d).length })) : issues;
  const option = (v, label, selected) =>
    '<option value="' + esc(v) + '"' + (selected ? ' selected' : '') + '>' + esc(label) + '</option>';
  const dates = entries.map((i) => {
    const active = i.day === day && (section === 'updates' || i.revision === issue?.revision);
    const url = href(layout, section, i.day, i.revision);
    const label = i.day + (i.revision > 1 ? ' · r' + i.revision : '');
    return { active, url, label, count: i.count };
  });
  const group =
    section === 'letter'
      ? '<label class="generated">뉴스레터 생성일<select id="generated">' +
        option('', '모든 생성일', !generated) +
        [...new Set(data.issues.map((i) => i.generated))]
          .sort()
          .reverse()
          .map((d) => option(d, d, d === generated))
          .join('') +
        '</select></label>'
      : '';
  $('archive').innerHTML =
    '<h2>' +
    (section === 'updates' ? '수집일' : '뉴스레터 보관함') +
    '</h2>' +
    group +
    '<label class="compact-date">' +
    (section === 'letter' ? '호 선택' : '수집일 선택') +
    '<select id="compact-day">' +
    (section === 'letter' && issue && !issue.generated
      ? option(href(layout, section, day, issue.revision), day + ' · 발행 전', true)
      : '') +
    dates.map((i) => option(i.url, i.label, i.active)).join('') +
    '</select></label><nav class="dates" aria-label="날짜 선택">' +
    dates
      .map(
        (i) =>
          '<a href="' +
          i.url +
          '" ' +
          (i.active ? 'aria-current="date"' : '') +
          '><span>' +
          i.label +
          '</span><small>' +
          i.count +
          '건</small></a>',
      )
      .join('') +
    '</nav>';
}
function storyCard(c) {
  return (
    '<button type="button" class="story" data-card="' +
    esc(c.id) +
    '" aria-haspopup="dialog"><span class="card-line">' +
    mark(c.browser) +
    chip(c.stage) +
    '</span><strong>' +
    esc(c.title) +
    '</strong><span class="scope">' +
    esc(scopeLine(c)) +
    '</span><span class="card-foot"><span>' +
    mediaLabel(c) +
    '</span><span aria-hidden="true">↗</span></span></button>'
  );
}
function counts(rows) {
  const browsers = ['', ...new Set([...Object.keys(brands), ...rows.map((c) => c.browser)])];
  return (
    '<div class="tally" role="group" aria-label="브라우저 필터">' +
    browsers
      .map((id) => {
        const n = id ? rows.filter((c) => c.browser === id).length : rows.length;
        return (
          '<button data-browser="' +
          esc(id) +
          '" aria-pressed="' +
          (browserFilter === id) +
          '"><span>' +
          (id ? mark(id) : '전체') +
          '</span><b>' +
          n +
          '</b><small>건</small></button>'
        );
      })
      .join('') +
    '</div>'
  );
}
function results() {
  const rows = byDay.get(state.day) || [];
  const term = query.trim().toLocaleLowerCase();
  const found = rows.filter(
    (c) =>
      (!browserFilter || c.browser === browserFilter) &&
      (!missing || !evidenceMedia(c).length) &&
      [c.title, c.original, c.browser, ...(brands[c.browser] || []), scopeLine(c), c.stage]
        .join(' ')
        .toLocaleLowerCase()
        .includes(term),
  );
  $('result-count').textContent =
    rows.length === found.length
      ? '카드 ' + rows.length + '건'
      : '전체 ' + rows.length + '건 중 ' + found.length + '건';
  if (!found.length) {
    $('results').innerHTML =
      '<p class="empty">조건에 맞는 기능 카드가 없습니다. <button data-reset>필터 초기화</button></p>';
  } else if (state.layout === 'board') {
    const ids = [...new Set(found.map((c) => c.browser))];
    $('results').innerHTML =
      '<div class="lanes">' +
      ids
        .map((id) => {
          const lane = found.filter((c) => c.browser === id);
          return (
            '<section class="lane"><h3>' +
            mark(id) +
            ' <small>' +
            lane.length +
            '</small></h3>' +
            lane.map(storyCard).join('') +
            '</section>'
          );
        })
        .join('') +
      '</div>';
  } else {
    $('results').innerHTML = '<div class="cards">' + found.map(storyCard).join('') + '</div>';
  }
}
function updates() {
  const rows = byDay.get(state.day) || [];
  const board = state.layout === 'board';
  const filters =
    '<div class="filters"><label class="search"><span aria-hidden="true">⌕</span><input id="query" type="search" aria-label="기능 카드 검색" placeholder="기능명, 브라우저, 플랫폼 검색" value="' +
    esc(query) +
    '"></label>' +
    (board
      ? '<label class="browser-select"><span>브라우저</span><select id="browser"><option value="">전체</option>' +
        Object.keys(brands)
          .map(
            (id) =>
              '<option value="' +
              id +
              '"' +
              (browserFilter === id ? ' selected' : '') +
              '>' +
              brand(id) +
              '</option>',
          )
          .join('') +
        '</select></label>'
      : '') +
    '<label class="check"><input type="checkbox" id="missing" ' +
    (missing ? 'checked' : '') +
    '> 화면 미확보만</label></div>';
  $('panel').innerHTML =
    '<div class="section-title"><div><p class="kicker">DAILY UPDATES</p><h2>' +
    dateText(state.day) +
    ' 기능 변화</h2></div><span id="result-count" role="status"></span></div>' +
    (!board ? counts(rows) : '') +
    filters +
    '<div id="results"></div>';
  results();
}
function letter() {
  const i = state.issue;
  if (!i) {
    $('panel').textContent = '생성된 뉴스레터가 없습니다.';
    return;
  }
  const qs = [...new Set(i.stories.map((c) => c.question))].slice(0, 2);
  const lines = i.stories
    .map((c, n) => {
      const headline = byId.has(c.id)
        ? '<button data-card="' + esc(c.id) + '">' + esc(c.title) + '</button>'
        : esc(c.title);
      return (
        '<section class="news-item"><p>' +
        mark(c.browser) +
        ' · ' +
        esc(scopeLine(c)) +
        ' · ' +
        esc(c.stage) +
        '</p><h3>' +
        headline +
        '</h3>' +
        (n === 0 && c.brief ? '<p class="brief">' + esc(c.brief) + '</p>' : '') +
        '</section>'
      );
    })
    .join('');
  const completeness = { partial: '일부 완료', failed: '실패', unknown: '미확인', complete: '완료' };
  const note = i.completeness
    ? '수집 ' +
      (completeness[i.completeness.collection] || '미확인') +
      ' · 평가 ' +
      (completeness[i.completeness.evaluation] || '미확인')
    : '공개 자료 기준';
  const publication = i.generated ? '생성 ' + i.generated : '발행 전 미리보기';
  const emptyText = i.pending
    ? '한글 기능 제목을 편집하고 있습니다.'
    : '이 호에 연결된 기능 카드가 없습니다.';
  $('panel').innerHTML =
    '<div class="letter-tools"><span>' +
    esc(publication) +
    ' · 한국시간</span><button data-print>인쇄 / PDF</button></div><article class="letter"><header><p class="kicker">BROWSER BENCHMARK / DAILY BRIEF</p><h2>브라우저 데일리</h2><div class="issue-line"><b>' +
    esc(i.day) +
    '호' +
    (i.revision > 1 ? ' · r' + i.revision : '') +
    '</b><span>수집 카드 ' +
    i.count +
    '건 · 주요 변화 ' +
    i.stories.length +
    '건' +
    (i.pending ? ' · 한글 제목 대기 ' + i.pending + '건' : '') +
    '</span></div></header>' +
    (lines || '<p class="empty">' + emptyText + '</p>') +
    (qs.length
      ? '<section class="questions"><h3>삼성 브라우저에서 짚어볼 점</h3>' +
        qs.map((q) => '<p>' + esc(q) + '</p>').join('') +
        '</section>'
      : '') +
    '<footer><span>' +
    esc(note) +
    ' · ' +
    esc(publication) +
    '</span><span>1 / 1</span></footer></article>';
}
function render() {
  state = parseRoute();
  const { layout, section, day, issue } = state;
  if (generated && section === 'letter' && issue?.generated !== generated) generated = '';
  document.body.dataset.layout = layout;
  document.body.dataset.section = section;
  document.title = layoutNames[layout] + ' · ' + sections[section] + ' · 브라우저 벤치마크';
  $('layouts').innerHTML = Object.entries(layoutNames)
    .map(([id, label]) =>
      navLink(href(id, section, day, section === 'letter' ? issue?.revision : null), label, id === layout),
    )
    .join('');
  $('hero').innerHTML =
    layout === 'board'
      ? '<div class="hero-name"><p class="kicker">브라우저 벤치마크 / 제품별 비교</p><h1>Browser Board<span>.</span></h1></div><p class="hero-note">같은 날의 기능 변화를<br>브라우저별로 비교하세요.</p>'
      : '<div class="hero-name"><p class="kicker"><i class="signal"></i>BROWSER OBSERVATORY</p><h1>브라우저의 변화, <span>한눈에.</span></h1><p>날짜별 기능 업데이트와 공식 근거를 살펴보세요.</p></div>';
  $('switcher').innerHTML =
    '<nav aria-label="자료 보기">' +
    Object.entries(sections)
      .map(([id, label]) =>
        navLink(
          href(
            layout,
            id,
            (id === 'updates' ? days : issueDays).includes(day)
              ? day
              : (id === 'updates' ? days : issueDays)[0],
          ),
          label,
          id === section,
        ),
      )
      .join('') +
    '</nav><span>KST · 한국시간</span>';
  archive();
  if (!day) $('panel').textContent = '아직 수집된 자료가 없습니다.';
  else if (section === 'letter') letter();
  else updates();
}
function player(type, url, label) {
  return type === 'video'
    ? '<video src="' +
        esc(url) +
        '" controls preload="metadata" playsinline aria-label="' +
        esc(label) +
        '"></video>'
    : '<img src="' + esc(url) + '" alt="' + esc(label) + '" referrerpolicy="no-referrer">';
}
function originalLink(path, label) {
  const prefix =
    'https://github.com/sangria-kim/browser-benchmark/blob/' + encodeURIComponent(data.source.sha) + '/';
  return external(prefix + path.split('/').map(encodeURIComponent).join('/'), label);
}
function showDetails(c, button) {
  if (button) opener = button;
  opened = c;
  const local = localMedia(c);
  const media = evidenceMedia(c);
  const facts = [
    ['버전', c.version],
    ['플랫폼', c.platform.join(' / ')],
    ['확인 단계', c.stage],
    ['실기 검증', c.device_test],
    ['수집일 (KST)', c.day],
    ['발표일', c.announced || '미확인'],
    ['적용일', c.effective || '미확인'],
  ];
  if (Object.keys(c.targets || {}).length) {
    facts.push([
      '확인된 플랫폼별 목표',
      Object.entries(c.targets)
        .map(([name, value]) => name + ' ' + value)
        .join(' / '),
    ]);
    facts.push(['출시 버전', '미확인']);
  }
  if (c.builds) facts.push(['빌드', c.builds]);
  const figures = media
    .map((item) => {
      const { media: m, owner } = item;
      const origin = item.local ? '이 브라우저에 저장한 자료' : '공식 제품 자료';
      const scope =
        owner.id !== c.id || owner.media_version
          ? '원천 자료 · ' +
            brand(owner.browser) +
            ' · ' +
            (owner.media_version || owner.version) +
            ' · ' +
            owner.platform.join(' / ') +
            ' · ' +
            owner.stage
          : '';
      const remove = item.local
        ? '<button type="button" data-remove="' + esc(owner.id) + '">이 브라우저의 등록 해제</button>'
        : '';
      return (
        '<figure>' +
        player(m.type, m.url, m.label || owner.title) +
        '<figcaption>' +
        esc([scope, origin, m.note].filter(Boolean).join(' · ')) +
        ' · ' +
        external(m.url, '원본') +
        '</figcaption>' +
        remove +
        '</figure>'
      );
    })
    .join('');
  const attach =
    '<details class="attach"><summary>화면 자료 ' +
    (local ? '수정' : '추가') +
    '</summary><form id="attach"><label>자료 형식<select name="kind"><option value="image">이미지</option><option value="video">동영상</option></select></label><label>실제 화면 주소<input type="url" name="url" required placeholder="https://"></label><button>미리 보기</button><div id="candidate" role="status"></div></form><p>저장한 자료는 이 브라우저의 두 화면에서 볼 수 있습니다. 팀에 공유하려면 ' +
    external(
      'https://github.com/sangria-kim/browser-benchmark/blob/work/browser-benchmark/dashboard/README.md#화면-자료-보강',
      '공용 등록 안내',
    ) +
    '를 확인하세요. 카드 ID <code>' +
    esc(c.id) +
    '</code></p>' +
    '</details>';
  const records = c.records || [c.record];
  $('detail-body').innerHTML =
    '<p class="detail-brand">' +
    mark(c.browser) +
    ' ' +
    chip(c.stage) +
    '</p><h2 id="detail-title">' +
    esc(c.title) +
    '</h2><p class="detail-brief">' +
    esc(c.brief) +
    '</p>' +
    (c.title_pending
      ? '<p>' +
        external(
          'https://github.com/sangria-kim/browser-benchmark/blob/work/browser-benchmark/dashboard/daily/titles.json',
          '한글 제목 등록',
        ) +
        ' · <code>' +
        esc(c.id) +
        '</code></p>'
      : '') +
    '<dl>' +
    facts.map(([k, v]) => '<div><dt>' + esc(k) + '</dt><dd>' + esc(v) + '</dd></div>').join('') +
    '</dl>' +
    (c.condition ? '<p>' + esc(c.condition) + '</p>' : '') +
    '<section class="evidence"><h3>실제 화면</h3>' +
    (figures || '<p class="unavailable">실제 화면 미확보</p>') +
    (c.media.length ? '' : attach) +
    '</section>' +
    '<section class="detail-question"><h3>삼성 브라우저 검토 질문</h3><p>' +
    esc(c.title_pending ? '한글 요약과 함께 검토 질문을 정리할 예정입니다.' : c.question) +
    '</p></section><section><h3>근거와 변경 내용</h3>' +
    (c.delta ? '<p>' + esc(c.delta) + '</p>' : '') +
    '<ul>' +
    c.sources.map((url) => '<li>' + sourceLink(url) + '</li>').join('') +
    records
      .map(
        (path, n) =>
          '<li>' + originalLink(path, '수집 기록' + (records.length > 1 ? ' ' + (n + 1) : '')) + '</li>',
      )
      .join('') +
    '</ul></section>';
  if (!$('detail').open) $('detail').showModal();
  $('detail').scrollTop = 0;
  $('detail-body')
    .querySelectorAll('figure img, figure video')
    .forEach((el) => {
      const failed = () => {
        if (el.isConnected && !el.hidden) {
          el.hidden = true;
          el.after(document.createTextNode('자료를 불러오지 못했습니다. 원본 주소를 확인하세요.'));
        }
      };
      el.addEventListener('error', failed, { once: true });
      if (el.error || (el.tagName === 'IMG' && el.complete && !el.naturalWidth)) failed();
    });
}
function redrawAfterMedia(message) {
  const c = opened;
  if (state.section === 'updates') results();
  showDetails(c);
  $('detail-body')
    .querySelector('.evidence h3')
    .insertAdjacentHTML('afterend', '<p role="status">' + esc(message) + '</p>');
  $('detail').querySelector('button').focus({ preventScroll: true });
}
$('detail').addEventListener('close', () => {
  $('detail-body').replaceChildren();
  const old = opened;
  opened = null;
  const focus = opener?.isConnected
    ? opener
    : [...document.querySelectorAll('[data-card]')].find((el) => el.dataset.card === old?.id) ||
      $('query') ||
      $('content');
  focus.focus({ preventScroll: true });
});
$('detail').addEventListener('click', (e) => {
  if (e.target === $('detail')) $('detail').close();
  const remove = e.target.closest('[data-remove]');
  const owner =
    remove &&
    opened &&
    [opened, ...(opened.related_sources || [])].find((c) => c.id === remove.dataset.remove);
  if (owner) {
    try {
      localStorage.removeItem(key(owner));
      redrawAfterMedia('로컬 등록을 해제했습니다.');
    } catch {
      redrawAfterMedia('저장소에 접근할 수 없습니다. 브라우저 설정을 확인하세요.');
    }
  }
});
$('detail').addEventListener('submit', (e) => {
  if (e.target.id !== 'attach') return;
  e.preventDefault();
  const form = e.target,
    c = opened,
    url = mediaURL(form.elements.url.value),
    type = form.elements.kind.value;
  const box = $('candidate');
  if (!url) {
    box.textContent = '사용자 정보가 없는 HTTPS 주소를 입력하세요.';
    return;
  }
  const el = document.createElement(type === 'video' ? 'video' : 'img');
  const save = document.createElement('button');
  save.type = 'button';
  save.textContent = '확인한 화면 저장';
  save.disabled = true;
  el.addEventListener(
    type === 'video' ? 'loadedmetadata' : 'load',
    () => {
      save.disabled = false;
    },
    { once: true },
  );
  el.addEventListener(
    'error',
    () => {
      if (el.parentElement === box) box.textContent = '자료를 열 수 없습니다. 형식과 주소를 확인하세요.';
    },
    { once: true },
  );
  if (type === 'video') {
    el.controls = true;
    el.preload = 'metadata';
  } else {
    el.alt = '등록할 실제 화면 미리 보기';
    el.referrerPolicy = 'no-referrer';
  }
  box.replaceChildren(el, save);
  el.src = url;
  save.onclick = () => {
    if (!box.isConnected || opened !== c) return;
    try {
      localStorage.setItem(key(c), JSON.stringify({ type, url }));
      redrawAfterMedia('이 브라우저에 저장했습니다.');
    } catch {
      box.textContent = '저장할 수 없습니다. 브라우저 저장소 설정을 확인하세요.';
    }
  };
});
document.addEventListener('input', (e) => {
  if (e.target.id === 'query') {
    query = e.target.value;
    results();
  }
  if (e.target.closest('#attach') && e.target.matches('input,select')) $('candidate')?.replaceChildren();
});
document.addEventListener('change', (e) => {
  if (e.target.id === 'compact-day') location.hash = e.target.value;
  if (e.target.id === 'generated') {
    generated = e.target.value;
    const issue = data.issues.find((i) => !generated || i.generated === generated);
    if (issue && generated && state.issue?.generated !== generated)
      location.hash = href(state.layout, 'letter', issue.day, issue.revision);
    else archive();
  }
  if (e.target.id === 'browser') {
    browserFilter = e.target.value;
    results();
  }
  if (e.target.id === 'missing') {
    missing = e.target.checked;
    results();
  }
});
document.addEventListener('click', (e) => {
  if (e.target.closest('.skip')) {
    e.preventDefault();
    $('content').focus();
    return;
  }
  const el = e.target.closest('a,button');
  if (!el) return;
  if (el.dataset.card) {
    const c = byId.get(el.dataset.card);
    if (c) showDetails(c, el);
  }
  if (el.hasAttribute('data-print')) window.print();
  if (el.hasAttribute('data-browser')) {
    browserFilter = el.dataset.browser;
    document
      .querySelectorAll('[data-browser]')
      .forEach((b) => b.setAttribute('aria-pressed', String(b === el)));
    results();
  }
  if (el.hasAttribute('data-reset')) {
    missing = false;
    browserFilter = '';
    query = '';
    updates();
    $('query').focus();
  }
});
window.addEventListener('hashchange', () => {
  if ($('detail').open) $('detail').close();
  const old = state,
    next = parseRoute();
  if (old.day !== next.day) {
    query = '';
    browserFilter = '';
    missing = false;
  }
  render();
  try {
    localStorage.setItem('browser-benchmark:layout', state.layout);
  } catch {}
  const target =
    old.layout !== state.layout
      ? '#layouts [aria-current]'
      : old.section !== state.section
        ? '#switcher [aria-current]'
        : '.dates [aria-current]';
  const dest = document.querySelector(target);
  if (dest?.getClientRects().length) dest.focus({ preventScroll: true });
  else $('compact-day')?.focus({ preventScroll: true });
});
if (location.protocol === 'file:')
  document.querySelectorAll('.research-link').forEach((a) => {
    a.href = 'https://sangria-kim.github.io/browser-benchmark/?view=features';
  });
render();
