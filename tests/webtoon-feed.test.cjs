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

// Exercise the real renderer using the compact selected-card contract.
function appContext(events){
 const nodes=new Map();
 const node=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',value:'',checked:false,hidden:false,disabled:false,dataset:{},setAttribute(){}});return nodes.get(id);};
 const context=vm.createContext({URL,URLSearchParams,Intl,Date,console,ResearchModel:require('../dashboard/research-model.js'),location:{search:'?browser=safari',pathname:'/'},history:{replaceState(){}},document:{getElementById:node,querySelector:node},setInterval(){},setTimeout(){}});
 let app=fs.readFileSync('dashboard/app.js','utf8').replace(/init\(\);\s*$/,'');
 context.fetch=async()=>{throw Error('Unexpected resource request');};
 vm.runInContext(fs.readFileSync('dashboard/resources.js','utf8'),context);
 vm.runInContext(app,context);
 const latest=new Map();for(const e of events){const old=latest.get(e.feature_id);if(!old||e.observed_at>old.observed_at)latest.set(e.feature_id,e);}
 const row=e=>({key:'feature_event:'+e.event_id,id:e.event_id,subject_kind:'feature_event',title:e.summary,browser:e.browser,platform:e.platform,date:e.observed_at,catalog_id:e.feature_id,current_status:'selected',current_selected:true,detail:'details/example.json'});
 context.input={selected:{features:[...latest.values()].map(row),flags:[]},history:events.map(row),catalog:{events:{}},counts:{source_item:events.length,feature:latest.size,experiment:0},experiment_counts:{}};
 node('sort').value='new';node('membership').value='current';
 vm.runInContext("data=input;browser='safari';render();",context);
 return {nodes,context,node};
}
test('Safari is selectable with zero selected cards; collected and selected counts are distinguished',()=>{
 const empty=appContext([]);
 assert.match(empty.node('browser-cards').innerHTML,/data-browser="safari" aria-pressed="true"/);
 assert.match(empty.node('empty-title').textContent,/Safari.*선정 항목/);
 assert.match(empty.node('browser-cards').innerHTML,/현재 선정 없음/);
 const filled=appContext([{event_id:'safari-example',feature_id:'safari-example',browser:'safari',summary:'Safari feature',platform:['macOS'],observed_at:'2026-11-16',version:'27',event_type:'improvement'}]);
 assert.equal(filled.node('empty').hidden,true);
 assert.match(filled.node('result-count').textContent,/1개 항목/);
 assert.match(filled.node('feature-grid').innerHTML,/Safari feature/);
});

test('Chrome experiment shortcut opens the current selection and focuses its tab',()=>{
 const state=appContext([]);
 state.context.input.selected.flags=[{key:'experiment:flag',subject_kind:'experiment',title:'Selected flag',
  browser:'chrome',platform:['Windows'],date:'2026-11-16',experiment_kind:'flag_entry'}];
 state.node('membership').value='history';
 state.node('from-date').value='2099-01-01';
 state.node('search').value='different feature';
 let focused=false, scrolled=false;
 state.node('flags-tab').focus=()=>{focused=true;};
 state.node('explorer').scrollIntoView=()=>{scrolled=true;};
 vm.runInContext('openSelectedExperiments()',state.context);
 assert.match(state.node('browser-cards').innerHTML,/data-experiment-shortcut\s+aria-current="true"[\s\S]*?현재 선정 1개/);
 assert.match(state.node('browser-cards').innerHTML,/data-browser="chrome" aria-pressed="false"/);
 assert.match(state.node('feature-grid').innerHTML,/Selected flag/);
 assert.equal(focused && scrolled,true);
});

test('selected projection renders one current card; detail links preserve earlier event identity',()=>{
 const base={feature_id:'safari-tabs',browser:'safari',platform:['macOS'],version:'27',event_type:'improvement'};
 const old={...base,event_id:'old',observed_at:'2026-11-15',summary:'Earlier version'},latest={...base,event_id:'new',observed_at:'2026-11-16',summary:'Latest version'};
 const state=appContext([old,latest]);
 assert.equal((state.node('feature-grid').innerHTML.match(/class="feature-card"/g)||[]).length,1);
 assert.match(state.node('feature-grid').innerHTML,/Latest version/);
 state.context.detail={row:state.context.input.selected.features[0],fact:latest,assessments:[],selection_history:[],current_owner:null,related:[state.context.input.history[0]],evidence:[],revisions:[],reports:[],legacy_flags:[]};
 assert.match(vm.runInContext('detailHTML(detail)',state.context),/data-detail="feature_event:old"/);
});

test('refresh keeps verified data on errors and rejects older snapshots',async()=>{
 const state=appContext([{event_id:'safari-example',feature_id:'safari-example',browser:'safari',summary:'Safari',platform:['macOS'],observed_at:'2026-11-16'}]);
 vm.runInContext("data.catalog.checked_at='2026-11-16';",state.context);
 let response=new Error('offline');
 state.context.structuredClone=structuredClone;
 state.context.fetch=()=>{};
 state.context.WebtoonFeed={merge:feed.merge,load:async()=>{if(response instanceof Error)throw response;return response;}};
 vm.runInContext('startWebtoonSync()',state.context);
 assert.match(state.node('sync-state').textContent,/자동 확인 대기/);
 await state.node('sync-refresh').onclick();
 assert.equal(state.node('sync-state').dataset.state,'stale');
 response={sha:'b'.repeat(40),feed:sample({'safari-example':{status:'done',url:result}})};
 await state.node('sync-refresh').onclick();
 assert.equal(state.node('sync-state').dataset.state,'live');
 assert.equal(vm.runInContext("wt(data.selected.features[0]).status",state.context),'done');
 response=new Error('network failure');
 await state.node('sync-refresh').onclick();
 assert.match(state.node('sync-state').textContent,/갱신 지연/);
 assert.equal(vm.runInContext("wt(data.selected.features[0]).status",state.context),'done');
 response={sha:'c'.repeat(40),feed:{...sample({'safari-example':{status:'todo'}}),checked_at:'2026-11-15'}};
 await state.node('sync-refresh').onclick();
 assert.equal(vm.runInContext("wt(data.selected.features[0]).status",state.context),'done');
 assert.equal(state.node('sync-refresh').disabled,false);
});


test('automatic status checks are scheduled only for 09:00 and 10:00 KST',()=>{
 const {context}=appContext([]);
 for(const [now,expected] of [
  ['2026-11-16T08:59:00+09:00','2026-11-16T00:00:00.000Z'],
  ['2026-11-16T09:00:00+09:00','2026-11-16T01:00:00.000Z'],
  ['2026-11-16T09:59:00+09:00','2026-11-16T01:00:00.000Z'],
  ['2026-11-16T10:00:00+09:00','2026-11-17T00:00:00.000Z'],
  ['2026-12-31T23:59:00+09:00','2027-01-01T00:00:00.000Z']
 ])assert.equal(vm.runInContext(`nextWebtoonCheck(new Date('${now}')).toISOString()`,context),expected);
});
