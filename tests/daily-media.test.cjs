const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('merged source retains official and device-local evidence with its original identity', () => {
  const source = {
    id: 'source-before-merge', day: '2026-11-17', version: '문서 150', stage: '과거 보강',
    media: [{type:'image', url:'https://example.org/official.png'}],
  };
  const card = {id:'event-after-merge',day:source.day,media:[],related_sources:[source]};
  const stored = new Map([['browser-benchmark:daily:media:'+source.id,JSON.stringify({type:'video',url:'https://example.org/local.mp4'})]]);
  const node = {textContent:JSON.stringify({cards:[card],issues:[],drafts:[]}),addEventListener(){}};
  const context = vm.createContext({
    URL,location:{protocol:'https:'},window:{addEventListener(){}},
    document:{getElementById:()=>node,addEventListener(){}},
    localStorage:{getItem:key=>stored.get(key)||null},
  });
  vm.runInContext(fs.readFileSync('dashboard/daily/app.js','utf8').replace(/render\(\);\s*$/,''),context);
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
