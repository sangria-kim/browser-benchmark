const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const feed=require('../dashboard/webtoon-feed.js');
const snapshot=require('../dashboard/webtoons.json');
const result='https://www.notion.so/415c9dbcdcf38188a221dcee8c19707f';
const sample=events=>({schema_version:1,checked_at:'2026-11-16T08:30:00+09:00',events});

test('checked-in feed has valid statuses and exact repository event IDs',()=>{
 feed.validate(snapshot);
 const ids=new Set(fs.readdirSync('data/events').filter(p=>p.endsWith('.json')).map(p=>JSON.parse(fs.readFileSync('data/events/'+p,'utf8')).event_id));
 for(const id of Object.keys(snapshot.events))assert.ok(ids.has(id),`Unknown event ${id}`);
});
test('status updates preserve examples, support corrections, and are idempotent',()=>{
 const baseline={checked_at:'2026-11-15',events:{example:{media:[{url:'https://example.com/demo.png'}],webtoon:{status:'todo'}}}};
 const update=sample({example:{status:'done',url:result},'safari-future-event':{status:'todo'}});
 const merged=feed.merge(baseline,update);
 assert.equal(merged.events.example.webtoon.status,'done');
 assert.deepEqual(merged.events.example.media,baseline.events.example.media);
 assert.equal(baseline.events.example.webtoon.status,'todo');
 assert.deepEqual(feed.merge(merged,update),merged);
 assert.deepEqual(feed.merge(merged,sample({example:{status:'excluded',note:'Scope corrected'}})).events.example.webtoon,{status:'excluded',note:'Scope corrected'});
});
test('rejects missing completion proof, unsafe links, and operational exports atomically',()=>{
 for(const entry of [{status:'done'},{status:'unknown'},{status:'done',url:'javascript:alert(1)'},{status:'done',url:'https://evil.com/'+result},{status:'done',url:result+'?token=private'},{status:'todo',email:'private@example.com'}])assert.throws(()=>feed.validate(sample({example:entry})));
 assert.throws(()=>feed.validate({...sample({}),logs:'not public'}));
 assert.throws(()=>feed.validate({...sample({}),checked_at:'yesterday'}));
});
test('resolves explicit source ref and downloads exactly the recorded SHA',async()=>{
 const sha='a'.repeat(40),calls=[];
 const loaded=await feed.load(async(url,options)=>{
  calls.push(url);assert.equal(options.credentials,'omit');
  return {ok:true,json:async()=>calls.length===1?[{sha}]:sample({example:{status:'todo'}})};
 });
 assert.match(calls[0],/sha=work%2Fbrowser-benchmark/);
 assert.equal(calls[1],`https://raw.githubusercontent.com/sangria-kim/browser-benchmark/${sha}/dashboard/webtoons.json`);
 assert.equal(loaded.sha,sha);
 await assert.rejects(feed.load(async()=>({ok:false})),/unavailable/);
});

// Exercise the real renderer with zero events and an incoming Safari event.
function appContext(events){
 const nodes=new Map();
 const node=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',value:'',checked:false,hidden:false,disabled:false,dataset:{},setAttribute(){}});return nodes.get(id);};
 const context=vm.createContext({URL,URLSearchParams,Intl,Date,console,location:{search:'?browser=safari',pathname:'/'},history:{replaceState(){}},document:{getElementById:node,querySelector:node},setInterval(){}});
 let app=fs.readFileSync('dashboard/app.js','utf8').replace(/init\(\);\s*$/,'');
 vm.runInContext(app,context);
 context.input={events,flags:[],catalog:{events:{}}};
 vm.runInContext('data=input;render();',context);
 return {nodes,context,node};
}
test('Safari is selectable before collection; real events fill its card and results',()=>{
 const empty=appContext([]);
 assert.match(empty.node('browser-cards').innerHTML,/data-browser="safari" aria-pressed="true"/);
 assert.match(empty.node('empty-title').textContent,/Safari 조사 결과/);
 assert.match(empty.node('browser-cards').innerHTML,/수집 대기/);
 const filled=appContext([{event_id:'safari-example',feature_id:'safari-example',browser:'safari',summary:'Safari feature',platform:['macOS'],observed_at:'2026-11-16',version:'27',event_type:'improvement'}]);
 assert.equal(filled.node('empty').hidden,true);
 assert.match(filled.node('result-count').textContent,/1개 변경 사건 · 1개 기능/);
 assert.match(filled.node('feature-grid').innerHTML,/Safari feature/);
});


test('multiple events of one feature become one latest card; detail retains prior events',()=>{
 const base={feature_id:'safari-tabs',browser:'safari',platform:['macOS'],version:'27',event_type:'improvement'};
 const state=appContext([{...base,event_id:'old',observed_at:'2026-11-15',summary:'Earlier version'}, {...base,event_id:'new',observed_at:'2026-11-16',summary:'Latest version'}]);
 assert.equal((state.node('feature-grid').innerHTML.match(/class="feature-card"/g)||[]).length,1);
 assert.match(state.node('feature-grid').innerHTML,/Latest version/);
 assert.match(state.node('result-count').textContent,/2개 변경 사건 · 1개 기능/);
 assert.match(vm.runInContext('eventDetail(data.events[1])',state.context),/data-history="old"/);
});

test('refresh keeps verified data on errors and rejects older snapshots',async()=>{
 const state=appContext([{event_id:'safari-example',feature_id:'safari-example',browser:'safari',summary:'Safari',platform:['macOS'],observed_at:'2026-11-16'}]);
 vm.runInContext("data.catalog.checked_at='2026-11-16';",state.context);
 let response=new Error('offline');
 state.context.structuredClone=structuredClone;
 state.context.fetch=()=>{};
 state.context.WebtoonFeed={merge:feed.merge,load:async()=>{if(response instanceof Error)throw response;return response;}};
 vm.runInContext('startWebtoonSync()',state.context);
 await new Promise(setImmediate);
 assert.equal(state.node('sync-state').dataset.state,'stale');
 response={sha:'b'.repeat(40),feed:sample({'safari-example':{status:'done',url:result}})};
 await state.node('sync-refresh').onclick();
 assert.equal(state.node('sync-state').dataset.state,'live');
 assert.equal(vm.runInContext("wt(data.events[0]).status",state.context),'done');
 response=new Error('network failure');
 await state.node('sync-refresh').onclick();
 assert.match(state.node('sync-state').textContent,/갱신 지연/);
 assert.equal(vm.runInContext("wt(data.events[0]).status",state.context),'done');
 response={sha:'c'.repeat(40),feed:{...sample({'safari-example':{status:'todo'}}),checked_at:'2026-11-15'}};
 await state.node('sync-refresh').onclick();
 assert.equal(vm.runInContext("wt(data.events[0]).status",state.context),'done');
 assert.equal(state.node('sync-refresh').disabled,false);
});
