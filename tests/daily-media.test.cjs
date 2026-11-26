const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function loadDaily(cards, stored = new Map(), daily_status = {}, extra = {}) {
  const node = {textContent:JSON.stringify({cards,issues:[],drafts:[],daily_status,...extra}),addEventListener(){}};
  const context = vm.createContext({
    URL,location:{protocol:'https:'},window:{addEventListener(){}},
    document:{getElementById:()=>node,addEventListener(){}},
    localStorage:{getItem:key=>stored.get(key)||null},
  });
  vm.runInContext(fs.readFileSync('dashboard/daily/app.js','utf8').replace(/render\(\);\s*$/,''),context);
  return context;
}

test('Firefox permission evidence distinguishes stable and beta and keeps both note anchors', () => {
  const context = loadDaily([]);
  const event = JSON.parse(fs.readFileSync('data/events/firefox-local-network-permissions-stable-160-20261110.json','utf8'));
  const links = event.sources.map(source => context.sourceLink(source.url || source));
  assert.match(links[0], /#note-792488"[^>]*>Firefox Android 160\.0 정식판 릴리스 노트/);
  assert.match(links[1], /#note-792402"[^>]*>Firefox 160\.0 베타 릴리스 노트/);
  assert.match(links[2], />support\.mozilla\.org ↗</);
});

test('merged source retains official and device-local evidence with its original identity', () => {
  const source = {
    id: 'source-before-merge', day: '2026-11-17', version: '문서 150', stage: '과거 보강',
    media: [{type:'image', url:'https://example.org/official.png'}],
  };
  const card = {id:'event-after-merge',day:source.day,media:[],related_sources:[source]};
  const stored = new Map([['browser-benchmark:daily:media:'+source.id,JSON.stringify({type:'video',url:'https://example.org/local.mp4'})]]);
  const context = loadDaily([card], stored);
  const result = vm.runInContext(`JSON.stringify({
    media:evidenceMedia(byId.get('event-after-merge')).map(i=>[i.owner.id,i.owner.version,i.local,i.media.type]),
    archive:byId.get('source-before-merge').stage,
    label:mediaLabel(byId.get('event-after-merge'))
  })`,context);
  assert.deepEqual(JSON.parse(result),{
    media:[[source.id,source.version,false,'image'],[source.id,source.version,true,'video']],
    archive:source.stage,label:'원천 공식 화면',
  });
});

test('board shows saved cards in partial runs and keeps a confirmed zero day', () => {
  const partialDay = '2026-11-26';
  const zeroDay = '2026-11-27';
  const card = {id:'f1', day:partialDay, title:'탭 꾸미기', original:'탭 꾸미기', browser:'edge',
    stage:'베타', platform:['Windows'], version:'158', media:[], collection_kind:'근거 보강'};
  const context = loadDaily([card], new Map(), {
    [partialDay]:{status:'incomplete',change_count:null,collected_feature_count:null},
    [zeroDay]:{status:'complete',change_count:0,collected_feature_count:0},
  });
  assert.equal(vm.runInContext('days[0]', context), zeroDay);
  for (const layout of ['board','observatory']) {
    const partial = vm.runInContext(`
      state={layout:'${layout}',day:'${partialDay}'};
      (()=>{ const nodes={}; const node=document.getElementById;
        document.getElementById=id=>nodes[id] ||= {};
        updates(); document.getElementById=node;
        return JSON.stringify(nodes);
      })();
    `, context);
    assert.match(partial,/수집 미완료/);
    assert.doesNotMatch(partial,/오늘 업데이트 없음/);
    assert.match(partial,/탭 꾸미기/);
    assert.match(partial,/근거 보강/);
  }
  const zero = vm.runInContext(`
    state={layout:'board',day:'${zeroDay}'};
    (()=>{ const nodes={}; document.getElementById=id=>nodes[id] ||= {};
      updates();
      return JSON.stringify(nodes);
    })();
  `, context);
  assert.match(zero,/수집 완료 · 오늘 업데이트 없음/);
  assert.match(zero,/오늘 저장된 기능 카드가 없습니다/);
});

test('newsletter keeps details for a legacy card hidden from the same-day board', () => {
  const day = '2026-11-26';
  const card = {id:'daily-edge', day, title:'아침 수집 기능', browser:'edge', media:[]};
  const story = {id:'editorial-edge', day, title:'편집 제목', browser:'edge',
    stage:'정식판', platform:['Windows'], version:'158', media:[], question:'질문'};
  const context = loadDaily([card], new Map(), {}, {
    detail_cards:[story], drafts:[{day,revision:0,stories:[story],count:1}],
  });
  const rendered = vm.runInContext(`
    state={issue:editions[0]};
    (()=>{ const nodes={}; document.getElementById=id=>nodes[id] ||= {};
      letter();
      return [nodes.panel.innerHTML, byDay.get('${day}').length, byId.get('editorial-edge').title];
    })();
  `, context);
  assert.match(rendered[0],/<button data-card="editorial-edge">편집 제목<\/button>/);
  assert.equal(rendered[1], 1);
  assert.equal(rendered[2], '편집 제목');
});
