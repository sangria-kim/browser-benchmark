'use strict';
const stories = JSON.parse(document.querySelector('#stories').textContent);
const days = [...new Set(stories.map((s) => s.day))].sort().reverse();
const browsers = {
  firefox: 'Firefox',
  edge: 'Edge',
  whale: '웨일',
  brave: 'Brave',
  opera: 'Opera',
  vivaldi: 'Vivaldi',
};
const designs = [
  {
    id: 'edition',
    name: '모닝 에디션',
    en: 'Morning Edition',
    type: '신문형',
    description: '첫 기사와 짧은 단신으로 오늘의 변화를 읽습니다.',
    source: 'Linear Changelog',
    url: 'https://linear.app/changelog',
    influence: '날짜와 제목, 짧은 설명으로 한 가지 변화를 전하는 기사 구성.',
  },
  {
    id: 'log',
    name: '릴리스 타임라인',
    en: 'Release Log',
    type: '시간순',
    description: '수집 시각을 따라 변경 사항과 발표 단계를 훑습니다.',
    source: 'GitHub Changelog',
    url: 'https://github.blog/changelog/',
    influence: '날짜별 변경 이력과 변경 유형을 함께 읽는 방식.',
  },
  {
    id: 'board',
    name: '브라우저 보드',
    en: 'Browser Board',
    type: '제품별 비교',
    description: '같은 날의 업데이트를 브라우저별 열에 나란히 놓습니다.',
    source: 'Web Platform Dashboard',
    url: 'https://web.dev/blog/web-platform-dashboard-evolution',
    influence: '브라우저와 모바일 지원 범위를 나란히 비교하는 구조.',
  },
  {
    id: 'atlas',
    name: '스크린 아틀라스',
    en: 'Screen Atlas',
    type: '화면 중심',
    description: '공식 화면을 먼저 펼치고, 미확보 항목을 한곳에 모읍니다.',
    source: 'Apple Developer Videos',
    url: 'https://developer.apple.com/videos/',
    influence: '이미지와 제목으로 영상 자료를 탐색하는 라이브러리 구성.',
  },
  {
    id: 'notes',
    name: 'PM 비교 노트',
    en: 'Field Notes',
    type: '질문 중심',
    description: '기능 카드와 삼성 브라우저에서 확인할 질문을 짝지어 읽습니다.',
    source: 'GOV.UK Service Manual',
    url: 'https://www.gov.uk/service-manual/user-research/plan-user-research-for-your-service',
    influence: '제품에 대한 가정을 사용자 과제로 검증할 수 있는 질문으로 바꾸는 방식.',
  },
  ...extraDesigns,
];
const app = document.querySelector('#app');
const dialog = document.querySelector('#detail');
const esc = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
const dateText = (iso) =>
  new Intl.DateTimeFormat('ko-KR', {
    month: 'long',
    day: 'numeric',
    weekday: 'short',
    timeZone: 'UTC',
  }).format(new Date(iso + 'T00:00:00Z'));
const stamp = (iso) => iso.slice(5).replace('-', '.');
const route = (design, view, day) => '#' + [design.id, view, day].join('/');
const issueOf = (day) => stories.find((s) => s.day === day).issue;
const link = (url, label) =>
  '<a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">' + esc(label) + ' ↗</a>';
const group = (items, key) => {
  const groups = new Map();
  for (const s of items) groups.set(s[key], [...(groups.get(s[key]) || []), s]);
  return [...groups];
};
function httpsUrl(value) {
  try {
    const u = new URL(value);
    return u.protocol === 'https:' && !u.username && !u.password ? u.href : '';
  } catch {
    return '';
  }
}
function localKey(s) {
  return 'browser-benchmark:concepts:media:' + s.id;
}
function localMedia(s) {
  try {
    const item = JSON.parse(localStorage.getItem(localKey(s)));
    if (item && ['image', 'video'].includes(item.type) && httpsUrl(item.url)) return item;
  } catch {
    /* The permanent catalog still works when storage is unavailable. */
  }
  return null;
}
function mediaOf(s) {
  if (s.media.length) return s.media;
  const local = localMedia(s);
  return local ? [local] : [];
}
function browserName(s) {
  return (
    '<span class="browser-name"><i class="dot ' +
    esc(s.browser) +
    '"></i>' +
    esc(browsers[s.browser]) +
    '</span>'
  );
}
function version(s) {
  return s.version || '버전 미공개';
}
function meta(s) {
  return '<span class="meta">' + esc(version(s)) + ' · ' + esc(s.platform.join(' / ')) + '</span>';
}
function stage(s) {
  return '<span class="stage">' + esc(s.stage) + '</span>';
}
function mark() {
  return '<span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>';
}
function header(design) {
  const tools = design
    ? '<div class="switcher"><label>시안 <select id="switch-design">' +
      designs
        .map(
          (d, i) =>
            '<option value="' +
            d.id +
            '" ' +
            (d === design ? 'selected' : '') +
            '>' +
            String(i + 1).padStart(2, '0') +
            ' ' +
            d.name +
            '</option>',
        )
        .join('') +
      '</select></label><a href="#gallery">전체 시안</a></div>'
    : '<a class="source-jump" href="#references">디자인 참고 자료 ↘</a>';
  return (
    '<header class="topbar"><div class="top-in"><a class="brand" href="#gallery">' +
    mark() +
    '브라우저 관측소</a>' +
    tools +
    '</div></header>'
  );
}
function art(id) {
  if (id === 'observatory') return '<i class="obs-mini"></i>';
  if (id === 'calendar') return '<i class="calendar-mini">11</i>';
  if (id === 'cinema') return '<i class="film-mini">▶</i>';
  if (id === 'edition') return '<i class="sun"></i><i class="horizon"></i>';
  if (id === 'log') return '<i class="wave"></i><i class="pulse"></i>';
  if (id === 'board')
    return '<i class="slab one">Firefox</i><i class="slab two">Edge</i><i class="slab three">웨일</i>';
  if (id === 'atlas') return '<i class="lens"></i><i class="frame"></i>';
  return '<i class="rule-paper"></i><i class="question-mark">?</i><i class="binding"></i>';
}
function cover(d) {
  return (
    '<div class="cover cover-' +
    d.id +
    '" aria-hidden="true"><div class="art">' +
    art(d.id) +
    '</div><div class="cover-type">' +
    d.type +
    '</div><div class="cover-name">' +
    d.en.replace(' ', '<br>') +
    '</div></div>'
  );
}
function references() {
  return (
    '<details id="references"><summary>디자인 참고 자료 <span>8개 사이트</span></summary><div class="refs">' +
    designs
      .map(
        (d) =>
          '<p><strong>' + d.name + '</strong> ' + d.influence + ' ' + link(d.url, d.source) + '</p>',
      )
      .join('') +
    '</div></details>'
  );
}
function gallery() {
  function tiles(list) {
    return list
      .map(
        (d) => `<a class="choice" href="${route(d, 'cards', days[0])}">
      ${cover(d)}<div class="choice-body"><div class="choice-title">
      <span class="choice-index">${String(designs.indexOf(d) + 1).padStart(2, '0')}</span><h2>${d.name}</h2><span class="circle-arrow" aria-hidden="true">↗</span>
      </div><p>${d.description}</p></div></a>`,
      )
      .join('');
  }
  const candidates = designs.filter((d) => ['edition', 'board'].includes(d.id));
  const archive = designs.slice(0, 5).filter((d) => !candidates.includes(d));
  return (
    header() +
    `<main id="main" tabindex="-1" class="gallery wrap">
  <div class="gallery-head"><div><div class="eyebrow">BROWSER BENCHMARK</div><h1>대시보드 디자인 시안</h1></div>
  <p>같은 날짜의 카드와 뉴스레터를 열어<br>세 가지 새 구성과 우선 후보를 비교하세요.</p></div>
  <div class="collection-label"><strong>추가 시안</strong><span>2026.11 · 수집 자료 ${stories.length}건 발췌</span></div>
  <div class="covers new-directions">${tiles(extraDesigns)}</div>
  <div class="collection-label"><strong>우선 후보</strong><span>1차 시안에서 선택</span></div>
  <div class="covers candidates">${tiles(candidates)}</div>
  <details class="earlier"><summary>이전 시안 02 · 04 · 05</summary><div class="covers new-directions">${tiles(archive)}</div></details>
  ${references()}</main>`
  );
}
function dateNav(d, view, day) {
  const isIssue = view === 'letter';
  return (
    '<nav class="dates" aria-label="' +
    (isIssue ? '뉴스레터 발행일' : '카드 수집일') +
    '"><strong>' +
    (isIssue ? '예시 발행일' : '수집일 · KST') +
    '</strong><div>' +
    days
      .map(
        (date) =>
          '<a href="' +
          route(d, view, date) +
          '" ' +
          (date === day ? 'aria-current="date"' : '') +
          '>' +
          stamp(isIssue ? issueOf(date) : date) +
          '</a>',
      )
      .join('') +
    '</div></nav>'
  );
}
function mast(d, view, day) {
  return (
    '<div class="mast"><div class="mast-info"><span class="eyebrow">BROWSER BENCHMARK</span><span>' +
    d.name +
    '</span></div><h1>' +
    d.en +
    '</h1><nav class="views" aria-label="보기"><a href="' +
    route(d, 'cards', day) +
    '" ' +
    (view === 'cards' ? 'aria-current="page"' : '') +
    '>업데이트 카드</a><a href="' +
    route(d, 'letter', day) +
    '" ' +
    (view === 'letter' ? 'aria-current="page"' : '') +
    '>한 장 뉴스레터</a></nav></div>'
  );
}
function card(s, extra = '', preview = '') {
  return (
    '<button class="story ' +
    extra +
    '" data-story="' +
    esc(s.id) +
    '">' +
    preview +
    '<span class="story-inner"><span class="byline">' +
    browserName(s) +
    stage(s) +
    '</span><strong class="story-title">' +
    esc(s.title) +
    '</strong>' +
    meta(s) +
    '<span class="open-arrow" aria-hidden="true">↗</span></span></button>'
  );
}
function mediaFrame(s) {
  const m = mediaOf(s)[0];
  if (!m) return '';
  const visual =
    m.type === 'image'
      ? '<img src="' + esc(m.url) + '" alt="" loading="lazy">'
      : '<span class="play" aria-hidden="true">▶</span>';
  return (
    '<span class="sheet-preview">' +
    visual +
    '<span class="media-tag">' +
    (s.media.length ? '공식 ' : '내 ') +
    (m.type === 'image' ? '화면' : '영상') +
    '</span></span>'
  );
}
function storyLayout(d, items) {
  if (!items.length) return '<p class="empty">이 날짜의 시안 카드에는 미확보 항목이 없습니다.</p>';
  if (d.id === 'edition')
    return (
      '<div class="edition-grid">' +
      items
        .map((s, i) =>
          card(s, i === 0 ? 'lead' : '', i === 0 ? '<span class="lead-label">주요 기사</span>' : ''),
        )
        .join('') +
      '</div>'
    );
  if (d.id === 'log')
    return (
      '<div class="timeline">' +
      group(
        [...items].sort((a, b) => a.time.localeCompare(b.time)),
        'time',
      )
        .map(
          ([time, batch]) =>
            '<section><h3>' +
            esc(time) +
            ' <small>KST</small></h3><div>' +
            batch.map((s) => card(s)).join('') +
            '</div></section>',
        )
        .join('') +
      '</div>'
    );
  if (d.id === 'board')
    return (
      '<div class="board-grid">' +
      group(items, 'browser')
        .map(
          ([b, batch]) =>
            '<section class="lane"><h3>' +
            browserName(batch[0]) +
            '<span>' +
            batch.length +
            '</span></h3>' +
            batch.map((s) => card(s)).join('') +
            '</section>',
        )
        .join('') +
      '</div>'
    );
  if (d.id === 'atlas') {
    const available = items.filter((s) => mediaOf(s).length);
    const missing = items.filter((s) => !mediaOf(s).length);
    return (
      '<div class="atlas-layout">' +
      (available.length
        ? '<section><h3>화면 자료 <small>' +
          available.length +
          '</small></h3><div class="contact-sheet">' +
          available.map((s) => card(s, '', mediaFrame(s))).join('') +
          '</div></section>'
        : '') +
      (missing.length
        ? '<section class="pending"><h3>실제 화면 미확보 <small>' +
          missing.length +
          '</small></h3>' +
          missing.map((s) => card(s)).join('') +
          '</section>'
        : '') +
      '</div>'
    );
  }
  return (
    '<div class="notebook">' +
    items
      .map(
        (s) =>
          '<div class="note-row">' +
          card(s, '', '<span class="note-topic">' + esc(s.topic) + '</span>') +
          '<div class="margin-note"><small>삼성 브라우저 검토 질문</small><p>' +
          esc(s.question) +
          '</p></div></div>',
      )
      .join('') +
    '</div>'
  );
}
let missingOnly = false;
function cardsView(d, day, items) {
  const shown = missingOnly ? items.filter((s) => !mediaOf(s).length) : items;
  return (
    '<div class="workspace">' +
    dateNav(d, 'cards', day) +
    '<section class="day-content"><div class="day-head"><div><div class="eyebrow">DAILY UPDATES</div><h2>' +
    dateText(day) +
    '</h2></div><label class="missing-toggle"><input type="checkbox" id="missing" ' +
    (missingOnly ? 'checked' : '') +
    '> 화면 미확보만</label></div><p class="countline">수집 카드 ' +
    items.length +
    '건 · ' +
    new Set(items.map((s) => s.browser)).size +
    '개 브라우저' +
    (missingOnly ? ' · 미확보 ' + shown.length + '건' : '') +
    '</p>' +
    storyLayout(d, shown) +
    '</section></div>'
  );
}
function issueSheet(d, day, items) {
  const [lead, ...others] = items;
  const issue = issueOf(day);
  const headlines = others
    .map(
      (s) => `<p><b>${browserName(s)}</b><button data-story="${esc(s.id)}">${esc(s.title)}</button></p>`,
    )
    .join('');
  const questions = items
    .slice(0, 2)
    .map((s) => `<p><b>${esc(s.topic)}</b> ${esc(s.question)}</p>`)
    .join('');
  return `<article class="letter">
      <div class="letter-top"><span>브라우저 관측소</span><span>${issue.replaceAll('-', '.')}호</span></div>
      <div class="letter-heading">
        <div class="eyebrow">${d.en.toUpperCase()} &nbsp; / &nbsp; DAILY BRIEF</div>
        <h2><button class="headline" data-story="${esc(lead.id)}">${esc(lead.title)}</button></h2>
        <p>${browserName(lead)} · ${esc(version(lead))} · ${esc(lead.platform.join(' / '))} · ${esc(lead.stage)}</p>
        <p class="standfirst">${esc(lead.brief)}</p>
      </div>
      ${headlines ? `<div class="brief-list"><h3>함께 볼 변화</h3>${headlines}</div>` : ''}
      <div class="letter-questions"><h3>삼성 브라우저에서 짚어볼 점</h3>${questions}</div>
      <footer class="letter-foot"><span>수집 ${day} · 발췌 카드 ${items.length}건</span><span>1 / 1</span></footer>
    </article>`;
}
function newsletter(d, day, items) {
  return `<div class="workspace letter-space">${dateNav(d, 'letter', day)}${printableIssue(d, day, items)}</div>`;
}
function viewState() {
  const [id, mode, day] = location.hash.slice(1).split('/');
  return {
    design: designs.find((d) => d.id === id),
    view: mode === 'letter' ? 'letter' : 'cards',
    day: days.includes(day) ? day : days[0],
  };
}
function render() {
  const { design: d, view, day } = viewState();
  if (dialog.open) dialog.close();
  document.body.dataset.design = d ? d.id : 'gallery';
  document.title =
    (d
      ? d.name + ' · ' + (view === 'letter' ? '한 장 뉴스레터' : '업데이트 카드')
      : '대시보드 디자인 시안') + ' | 브라우저 관측소';
  if (!d) {
    app.innerHTML = gallery();
    if (location.hash === '#references') {
      const refs = document.querySelector('#references');
      refs.open = true;
      refs.scrollIntoView();
      refs.querySelector('summary').focus({ preventScroll: true });
    }
    return;
  }
  const items = stories.filter((s) => s.day === day);
  const newPage = { observatory, calendar: calendarView, cinema }[d.id];
  const content = newPage
    ? newPage(d, view, day, items)
    : mast(d, view, day) + (view === 'letter' ? newsletter(d, day, items) : cardsView(d, day, items));
  app.innerHTML =
    header(d) +
    '<main class="studio wrap" id="main" tabindex="-1">' +
    content +
    '<footer class="design-foot"><span>디자인 참고 · ' +
    link(d.url, d.source) +
    '</span><a href="#gallery">시안 비교 ↗</a></footer></main>';
}
function mediaTag(type, url, label) {
  return type === 'video'
    ? '<video controls playsinline preload="metadata" aria-label="' +
        esc(label) +
        '" src="' +
        esc(url) +
        '"></video>'
    : '<img src="' + esc(url) + '" alt="' + esc(label) + '">';
}
function mediaPanel(s) {
  const media = mediaOf(s);
  const entry = `<details class="attach"><summary>${media.length ? '이 기기의 자료 수정' : '화면 자료 추가'}</summary>
  <form id="attach">
    <p>해당 기능·플랫폼의 실제 이미지나 영상 주소를 입력하세요. 확인한 자료는 이 브라우저에 저장됩니다.</p>
    <label>형식 <select name="kind"><option value="image">이미지</option><option value="video">동영상</option></select></label>
    <label>자료 주소 <input name="url" type="url" required placeholder="https://" autocomplete="off"></label>
    <button type="submit">미리 보기</button><div id="candidate" aria-live="polite"></div>
  </form>
  ${media.length ? '<button type="button" data-clear-media>이 기기의 등록 해제 · 미확보로 되돌리기</button><p data-clear-error role="status"></p>' : ''}
  </details>`;
  const figures = media
    .map(
      (m) => `<figure class="evidence">${mediaTag(m.type, m.url, m.label || s.title)}
  <figcaption>${esc(m.note || '이 기기에서 추가한 자료')} · ${link(m.url, '원본 열기')}</figcaption></figure>`,
    )
    .join('');
  const missing =
    '<div class="no-media"><strong>실제 화면 미확보</strong><p>같은 버전·플랫폼의 화면을 찾으면 이 카드에 추가하세요.</p></div>';
  const state = s.media.length ? '공식 자료' : media.length ? '내가 추가한 자료' : '미확보';
  return `<section class="detail-media"><h3>실제 화면 <span>${state}</span></h3>${figures || missing}${s.media.length ? '' : entry}</section>`;
}
let activeStory;
let opener;
function evidenceLink(value) {
  const url = new URL(value);
  const release = url.pathname.match(/\/firefox\/(?:android\/)?([\d.]+)(beta)?\/releasenotes/);
  const label = release
    ? `Firefox ${release[1]} ${release[2] ? '베타' : '정식판'} 릴리스 노트`
    : url.hostname;
  return link(value, label);
}
function showDetail(s, trigger) {
  if (trigger) opener = trigger;
  activeStory = s;
  const builds = Object.values(s.builds).join(' / ');
  const facts = [
    ['브라우저 버전', version(s) + (builds ? ' · 빌드 ' + builds : '')],
    ['플랫폼', s.platform.join(' / ')],
    ['발표일', s.announced || '미확인'],
    ['적용일', s.effective || '미확인'],
    ['수집일 (KST)', s.day],
    ['증거 수준', '공식 문서 확인 · 실기 미검증'],
  ]
    .map(([label, value]) => `<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`)
    .join('');
  dialog.innerHTML = `<div class="detail-top"><span>기능 상세</span><button data-close aria-label="상세 닫기" autofocus>닫기 ×</button></div>
 <div class="detail-body">
   <div class="byline">${browserName(s)}${stage(s)}</div><h2 id="detail-title">${esc(s.title)}</h2>
   <p class="intro">${esc(s.brief)}</p><dl class="facts">${facts}</dl>
   <p class="condition">${esc(s.condition)}</p>${mediaPanel(s)}
   <section class="detail-question"><h3>삼성 브라우저 검토 질문</h3><p>${esc(s.question)}</p></section>
   <div class="official"><h3>공식 근거</h3>${s.sources.map(evidenceLink).join(' ')}</div>
 </div>`;
  if (!dialog.open) dialog.showModal();
  dialog.scrollTop = 0;
}
dialog.addEventListener('close', () => {
  dialog.querySelectorAll('video').forEach((v) => v.pause());
  dialog.replaceChildren();
  if (opener?.isConnected) opener.focus({ preventScroll: true });
  activeStory = null;
});
dialog.addEventListener('click', (event) => {
  if (event.target === dialog || event.target.closest('[data-close]')) dialog.close();
  if (event.target.closest('[data-clear-media]') && activeStory && !activeStory.media.length) {
    try {
      localStorage.removeItem(localKey(activeStory));
      refreshAfterMediaEdit(activeStory);
    } catch {
      dialog.querySelector('[data-clear-error]').textContent =
        '등록을 해제할 수 없습니다. 브라우저 저장 권한을 확인하세요.';
    }
  }
});
document.addEventListener(
  'error',
  (event) => {
    const el = event.target;
    if (!el.matches?.('.sheet-preview img, .evidence img, .evidence video')) return;
    const text = document.createElement('span');
    text.className = 'load-error';
    text.textContent = el.closest('figure')
      ? '자료를 불러오지 못했습니다. 원본 링크를 확인하세요.'
      : '원본 연결 확인 필요';
    el.replaceWith(text);
  },
  true,
);
function refreshAfterMediaEdit(s) {
  dialog.close();
  // Refresh counts after closing. Restore focus even if the filter removed this card.
  dialog.addEventListener(
    'close',
    () => {
      render();
      const trigger = [...document.querySelectorAll('[data-story]')].find(
        (el) => el.dataset.story === s.id,
      );
      (trigger || document.querySelector('#missing') || document.querySelector('#main')).focus({
        preventScroll: true,
      });
      if (trigger) showDetail(s, trigger);
    },
    { once: true },
  );
}
dialog.addEventListener('submit', (event) => {
  if (!event.target.matches('#attach')) return;
  event.preventDefault();
  const form = event.target;
  const region = form.querySelector('#candidate');
  const url = httpsUrl(form.elements.url.value);
  if (!url) {
    region.textContent = 'HTTPS 자료 주소를 입력하세요.';
    return;
  }
  const s = activeStory;
  const type = form.elements.kind.value;
  const preview = document.createElement(type === 'image' ? 'img' : 'video');
  preview.setAttribute('aria-label', '추가할 화면 미리 보기');
  if (type === 'video') preview.controls = true;
  const status = document.createElement('p');
  status.textContent = '자료를 불러오는 중입니다.';
  const confirm = document.createElement('button');
  confirm.type = 'button';
  confirm.hidden = true;
  confirm.textContent = '이 카드에 저장';
  const ready = () => {
    status.textContent = '화면과 플랫폼이 이 카드와 일치하는지 확인하세요.';
    confirm.hidden = false;
  };
  preview.addEventListener(type === 'image' ? 'load' : 'loadeddata', ready, { once: true });
  preview.addEventListener('error', () => {
    status.textContent = '열 수 없는 자료입니다. 직접 열리는 이미지나 영상 주소를 확인하세요.';
    confirm.hidden = true;
  });
  confirm.addEventListener('click', () => {
    try {
      localStorage.setItem(
        localKey(s),
        JSON.stringify({ type, url, label: s.title, note: '이 기기에서 추가한 자료' }),
      );
    } catch {
      status.textContent = '이 브라우저에서 저장할 수 없습니다. 저장 권한을 확인하세요.';
      return;
    }
    refreshAfterMediaEdit(s);
  });
  region.replaceChildren(preview, status, confirm);
  preview.src = url;
});
dialog.addEventListener('input', (event) => {
  if (event.target.closest('#attach') && ['url', 'kind'].includes(event.target.name))
    dialog.querySelector('#candidate').replaceChildren();
});
app.addEventListener('click', (event) => {
  const option = event.target.closest('[data-obs], [data-scene]');
  if (option) {
    if (option.dataset.obs) roundTwoState.browser = option.dataset.obs;
    if (option.dataset.scene) roundTwoState.sceneId = option.dataset.scene;
    render();
    document
      .querySelector(
        option.dataset.obs ? '[data-obs][aria-pressed="true"]' : '[data-scene][aria-pressed="true"]',
      )
      .focus({ preventScroll: true });
    return;
  }
  const button = event.target.closest('[data-story]');
  if (button)
    showDetail(
      stories.find((s) => s.id === button.dataset.story),
      button,
    );
  if (event.target.closest('[data-print]')) window.print();
  if (event.target.closest('a[href="#references"]') && location.hash === '#references') render();
});
app.addEventListener('input', (event) => {
  if (event.target.id !== 'obs-query') return;
  roundTwoState.query = event.target.value;
  const items = stories.filter((s) => s.day === viewState().day);
  document.querySelector('#obs-results').innerHTML = observatoryResults(items);
});
app.addEventListener('change', (event) => {
  const { design, view, day } = viewState();
  if (event.target.id === 'round-date') location.hash = route(design, view, event.target.value);
  if (event.target.id === 'switch-design')
    location.hash = route(
      designs.find((d) => d.id === event.target.value),
      view,
      day,
    );
  if (event.target.id === 'missing') {
    missingOnly = event.target.checked;
    render();
    document.querySelector('#missing').focus();
  }
});
document.querySelector('.skip').addEventListener('click', (event) => {
  event.preventDefault();
  document.querySelector('#main').focus();
});
window.addEventListener('hashchange', () => {
  missingOnly = false;
  resetDirection();
  render();
  if (location.hash !== '#references') {
    window.scrollTo(0, 0);
    document.querySelector('#main').focus({ preventScroll: true });
  }
});
render();
