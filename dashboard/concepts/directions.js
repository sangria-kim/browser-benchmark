'use strict';
const extraDesigns = [
  {
    id: 'observatory',
    name: '관측소 대시보드',
    en: 'Browser Observatory',
    type: 'GitHub Pages',
    description: '운영 화면의 브라우저 필터로 그날 수집한 카드를 좁혀 봅니다.',
    source: '브라우저 관측소 · GitHub Pages',
    url: 'https://sangria-kim.github.io/browser-benchmark/',
    influence: '실제 운영 스타일시트와 헤더, 브라우저별 집계 및 카드 배치를 사용했습니다.',
  },
  {
    id: 'calendar',
    name: '업데이트 달력',
    en: 'Date Book',
    type: '월간 달력',
    description: '자료가 있는 날을 달력에서 골라 그날의 업데이트와 발행호를 펼칩니다.',
    source: 'Stendig Calendars',
    url: 'https://stendigcalendars.com/',
    influence: '벽걸이 달력의 큰 숫자와 월간 격자를 날짜 탐색에 적용했습니다.',
  },
  {
    id: 'cinema',
    name: '사용 장면 상영관',
    en: 'Scene Select',
    type: '장면 탐색',
    description: '사용자 과제 하나를 골라 바뀐 동작과 실제 화면을 한 장면씩 봅니다.',
    source: 'Criterion Channel',
    url: 'https://www.criterionchannel.com/',
    influence: '상영작을 고르는 목록과 선택한 작품을 크게 보는 상영 화면을 참고했습니다.',
  },
];
const roundTwoState = { browser: 'all', query: '', sceneId: '' };
const obsNames = {
  all: '전체',
  chrome: 'Chrome',
  edge: 'Edge',
  firefox: 'Firefox',
  safari: 'Safari',
  brave: 'Brave',
  whale: 'Whale',
  opera: 'Opera',
  vivaldi: 'Vivaldi',
};
function resetDirection() {
  roundTwoState.browser = 'all';
  roundTwoState.query = '';
  roundTwoState.sceneId = '';
}
function viewLinks(d, view, day) {
  return `<nav class="round-views" aria-label="보기">${[
    ['cards', '업데이트 카드'],
    ['letter', '한 장 뉴스레터'],
  ]
    .map(
      ([id, label]) =>
        `<a href="${route(d, id, day)}" ${view === id ? 'aria-current="page"' : ''}>${label}</a>`,
    )
    .join('')}</nav>`;
}
function selectDate(view, day) {
  const label = view === 'letter' ? '예시 발행일' : '수집일 · KST';
  return `<label class="round-date">${label}<select id="round-date">${days.map((date) => `<option value="${date}" ${date === day ? 'selected' : ''}>${view === 'letter' ? issueOf(date) : date}</option>`).join('')}</select></label>`;
}
function missingFilter() {
  return `<label class="missing-toggle"><input type="checkbox" id="missing" ${missingOnly ? 'checked' : ''}> 화면 미확보만</label>`;
}
function sampleMediaLabel(s) {
  const item = mediaOf(s)[0];
  if (!item) return '실제 화면 미확보';
  return (s.media.length ? '공식 ' : '내 ') + (item.type === 'video' ? '영상' : '화면');
}
function calendarIssue(day, items) {
  const issue = issueOf(day);
  const lines = items
    .map(
      (s, i) => `<section class="slip-item"><p>${browserName(s)} · ${esc(s.platform.join(' / '))} · ${esc(version(s))} · ${esc(s.stage)}</p>
    <h3><button class="headline" data-story="${esc(s.id)}">${esc(s.title)}</button></h3>${i === 0 ? `<p>${esc(s.brief)}</p>` : ''}</section>`,
    )
    .join('');
  return `<article class="letter date-slip"><div class="slip-date"><span>예시 발행일</span><strong>${issue.slice(8)}</strong>
    <span>${issue.slice(0, 7).replace('-', ' / ')}</span></div>
    <div class="slip-stories"><div class="letter-top"><h2>하루의 업데이트</h2><span>${issue.replaceAll('-', '.')}호</span></div>
    ${lines}</div><div class="letter-questions"><h3>삼성 브라우저에서 짚어볼 점</h3>
    ${items
      .slice(0, 2)
      .map((s) => `<p><b>${esc(s.topic)}</b> ${esc(s.question)}</p>`)
      .join('')}</div>
    <footer class="letter-foot"><span>수집 ${day} · 발췌 카드 ${items.length}건</span><span>1 / 1</span></footer></article>`;
}
function printableIssue(d, day, items) {
  return `<section class="letter-wrap"><div class="letter-tools"><span>다음 날 아침 발행을 가정한 예시입니다.</span><button data-print>인쇄 / PDF</button></div>${d.id === 'calendar' ? calendarIssue(day, items) : issueSheet(d, day, items)}</section>`;
}
function observatoryCard(s) {
  return `<button class="feature-card" data-story="${esc(s.id)}" aria-haspopup="dialog">
  <span class="card-top"><span class="browser-cell"><span class="browser-icon">${obsNames[s.browser][0]}</span>${obsNames[s.browser]}</span><span class="card-date">${s.day}</span></span>
  <strong class="card-title">${esc(s.title)}</strong>
  <span class="card-platform">${esc(s.platform.join(' · '))} · ${esc(version(s))} · ${esc(s.stage)}</span>
  <span class="card-bottom"><span class="tag">${sampleMediaLabel(s)}</span><span class="card-open">자세히 ↗</span></span></button>`;
}
function observatoryResults(items) {
  const query = roundTwoState.query.trim().toLocaleLowerCase();
  const result = items.filter(
    (s) =>
      (roundTwoState.browser === 'all' || s.browser === roundTwoState.browser) &&
      (!missingOnly || !mediaOf(s).length) &&
      [s.title, obsNames[s.browser], browsers[s.browser], s.topic, version(s), ...s.platform]
        .join(' ')
        .toLocaleLowerCase()
        .includes(query),
  );
  return `<p class="results-line" role="status">예시 카드 ${items.length}건 중 ${result.length}건</p>${result.length ? `<div class="feature-grid">${result.map(observatoryCard).join('')}</div>` : '<p class="empty">조건에 맞는 카드가 없습니다. 브라우저나 검색어를 바꿔 보세요.</p>'}`;
}
function observatory(d, view, day, items) {
  const summary = Object.entries(obsNames)
    .map(([id, name]) => {
      const count = id === 'all' ? items.length : items.filter((s) => s.browser === id).length;
      return `<button class="browser-card" data-obs="${id}" aria-pressed="${id === roundTwoState.browser}">
    <span class="browser-top"><span class="browser-icon">${id === 'all' ? '◎' : name[0]}</span>${name}</span>
    <strong>${count}</strong><small>건</small><span class="date">당일 발췌 카드</span></button>`;
    })
    .join('');
  const hero = `<div class="observatory-ui obs-hero"><div class="masthead">
    <div><p class="eyebrow"><span class="signal"></span> BROWSER OBSERVATORY <span class="muted">/ 브라우저 벤치마크</span></p>
    <h1>브라우저의 변화, <span>한눈에.</span></h1><p class="intro">날짜별 기능 업데이트와 실제 화면, 삼성 브라우저의 검토 질문을 살펴보세요.</p></div>
    <div class="header-meta">${link(d.url, '운영 대시보드')}</div></div></div>`;
  const controls = `<div class="round-tools obs-controls">${viewLinks(d, view, day)}${selectDate(view, day)}</div>`;
  if (view === 'letter') return hero + controls + printableIssue(d, day, items);
  return (
    hero +
    controls +
    `<section class="observatory-ui obs-content">
  <div class="section-line"><h2>브라우저별 업데이트</h2><span>${day} · 시안 발췌 기준</span></div>
  <div class="browser-cards">${summary}</div><div class="explorer-head"><div><p class="eyebrow">FEATURE EXPLORER</p><h2>${dateText(day)} 기능 변화</h2></div></div>
  <div class="toolbar"><label class="search"><span aria-hidden="true">⌕</span><input id="obs-query" type="search" aria-label="카드 검색" placeholder="기능명, 브라우저, 플랫폼 검색" value="${esc(roundTwoState.query)}"></label>${missingFilter()}</div>
  <div id="obs-results">${observatoryResults(items)}</div></section>`
  );
}
function monthGrid(d, view, day) {
  const display = view === 'letter' ? issueOf(day) : day;
  const [year, month, number] = display.split('-').map(Number);
  const first = new Date(Date.UTC(year, month - 1, 1)).getUTCDay();
  const length = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const archived = new Map(days.map((date) => [view === 'letter' ? issueOf(date) : date, date]));
  const cells = Array.from({ length }, (_, i) => {
    const n = i + 1;
    const iso = display.slice(0, 8) + String(n).padStart(2, '0');
    if (!archived.has(iso)) return `<span class="silent-date">${n}</span>`;
    return `<a href="${route(d, view, archived.get(iso))}" ${n === number ? 'aria-current="date"' : ''} aria-label="${dateText(iso)} ${view === 'letter' ? '뉴스레터' : '수집 카드'}">${n}<i></i></a>`;
  }).join('');
  return `<section class="wall" aria-label="월간 탐색"><div class="wall-head"><h1>업데이트 달력</h1><span>${year}</span></div>
  <div class="wall-month"><b>${String(month).padStart(2, '0')}</b><span>${new Intl.DateTimeFormat('en', { month: 'long', timeZone: 'UTC' }).format(new Date(display + 'T00:00Z')).toUpperCase()}</span></div>
  <div class="month-grid">${'일월화수목금토'
    .split('')
    .map((v) => `<small>${v}</small>`)
    .join('')}${'<i></i>'.repeat(first)}${cells}</div>
  <p class="calendar-key"><i></i>${view === 'letter' ? '예시 뉴스레터 발행일' : '업데이트 수집일'} · KST</p></section>`;
}
function calendarView(d, view, day, items) {
  const shown = items.filter((s) => !missingOnly || !mediaOf(s).length);
  return `<div class="calendar-desk">${monthGrid(d, view, day)}<div class="day-page">
  ${viewLinks(d, view, day)}
  ${
    view === 'letter'
      ? printableIssue(d, day, items)
      : `<div class="day-leaf"><header><span>수집한 업데이트</span><b>${day.slice(0, 4)}</b></header>
  <h2>${dateText(day)}</h2><div class="leaf-meta"><span>발췌 카드 ${items.length}건</span>${missingFilter()}</div>
  <div class="tickets">${shown.map((s) => card(s, 'ticket')).join('') || '<p class="empty">이 날짜의 카드는 모두 화면 자료가 있습니다.</p>'}</div>
  <a class="tear-link" href="${route(d, 'letter', day)}">${stamp(issueOf(day))}호 뉴스레터 펼치기 ↗</a></div>`
  }
  </div></div>`;
}
function sceneVisual(s) {
  const m = mediaOf(s)[0];
  if (!m) return `<div class="unfilmed"><b>${esc(s.topic)}</b><span>실제 화면 미확보</span></div>`;
  return `<figure class="evidence cinema-evidence">${mediaTag(m.type, m.url, m.label || s.title)}<figcaption>${sampleMediaLabel(s)} · ${link(m.url, '원본 열기')}</figcaption></figure>`;
}
function cinemaLetter(d, day, items) {
  return `<section class="letter-wrap"><div class="letter-tools"><span>다음 날 아침 발행을 가정한 예시입니다.</span><button data-print>인쇄 / PDF</button></div>
  <article class="letter programme"><div class="letter-top"><strong>사용 장면 상영관</strong><span>${issueOf(day).replaceAll('-', '.')}호</span></div>
  <h2>사용 장면 브리핑</h2><div class="programme-items">${items
    .map(
      (s, i) => `<section><small>장면 ${i + 1} · ${esc(s.topic)}</small>
  <h3><button class="headline" data-story="${esc(s.id)}">${esc(s.title)}</button></h3><p>${browserName(s)} · ${esc(s.platform.join(' / '))} · ${esc(version(s))} · ${esc(s.stage)}</p><p>${esc(s.brief)}</p></section>`,
    )
    .join('')}</div>
  <div class="letter-questions"><h3>삼성 브라우저에서 짚어볼 점</h3>${items
    .slice(0, 2)
    .map((s) => `<p><b>${esc(s.topic)}</b> ${esc(s.question)}</p>`)
    .join(
      '',
    )}</div><footer class="letter-foot"><span>수집 ${day} · ${items.length}개 장면</span><span>1 / 1</span></footer></article></section>`;
}
function cinema(d, view, day, items) {
  const shown = items.filter((s) => !missingOnly || !mediaOf(s).length);
  const s = shown.find((s) => s.id === roundTwoState.sceneId) || shown[0];
  const bar = `<div class="cinema-bar"><div><span class="projector" aria-hidden="true">▶</span><h1>사용 장면 상영관</h1></div>${viewLinks(d, view, day)}${selectDate(view, day)}</div>`;
  if (view === 'letter') return bar + cinemaLetter(d, day, items);
  const reels = shown
    .map(
      (item, i) => `<button class="reel" data-scene="${esc(item.id)}" aria-pressed="${item === s}">
    <span>${String(i + 1).padStart(2, '0')} / ${esc(item.topic)}</span>
    <b>${esc(item.task)}</b><small>${browserName(item)} · ${esc(version(item))} · ${esc(item.platform.join(' / '))}</small></button>`,
    )
    .join('');
  return (
    bar +
    `<section class="screening"><div class="screening-head"><span>${dateText(day)} · 장면 ${shown.length}개</span>${missingFilter()}</div>
  ${
    s
      ? `<div class="screen"><div class="scene-text"><p class="scene-index">SCENE ${String(shown.indexOf(s) + 1).padStart(2, '0')} <span>/ ${String(shown.length).padStart(2, '0')}</span></p>
    <p class="scene-task">사용자 과제 · ${esc(s.task)}</p>
    <h2><button class="headline" data-story="${esc(s.id)}">${esc(s.title)}</button></h2>
    <p class="scene-change">${esc(s.brief)}</p><div class="scene-byline">${browserName(s)} ${stage(s)} ${meta(s)}</div>
    <button class="scene-open" data-story="${esc(s.id)}">기능 상세 · 근거 보기 ↗</button></div><div class="screen-image">${sceneVisual(s)}</div></div>
    <nav class="filmstrip" aria-label="사용 장면 선택">${reels}</nav>`
      : '<p class="empty">이 날짜에 화면 미확보 장면이 없습니다.</p>'
  }</section>`
  );
}
