const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const model=require('../dashboard/research-model.js');
test('source strings and URLs cannot become executable links',()=>{
 for(const u of ['javascript:alert(1)','data:text/html,<svg onload=alert(1)>','//evil.test','/path'])assert.equal(model.safeURL(u),'#');
 assert.equal(model.safeURL('https://example.org/evidence'),'https://example.org/evidence');
});
test('all-source and experiment filters retain kinds, statuses, platform and KST date',()=>{
 const r={title:'safe source',id:'source-id',browser:'safari',platform:['macOS'],date:'2026-11-15T23:30:00Z',experiment_kind:'base_feature',status:'excluded',event_type:'baseline',build_conditions:['BUILDFLAG(IS_MAC)']};
 assert.equal(model.matches(r,{browser:'safari',kind:'base_feature',status:'excluded',from:'2026-11-16',to:'2026-11-16',build:'is_mac'}),true);
 for(const f of [{browser:'chrome'},{kind:'flag_entry'},{kind:'command_switch'},{status:'selected'},{platform:'Android'},{to:'2026-11-15'},{ai:true},{webtoon:'done'}])assert.equal(model.matches(r,f),false);
 assert.equal(model.matches(r,{query:'source-id'}),true);
});
test('malicious fact and report strings are escaped by actual detail renderer',()=>{
 const node=()=>({value:'',innerHTML:'',setAttribute(){}}),context=vm.createContext({URL,URLSearchParams,Intl,Date,ResearchModel:model,location:{search:''},document:{getElementById:node}});
 context.fetch=async path=>({ok:true,json:async()=>context.resourceData[path]});
 vm.runInContext(fs.readFileSync('dashboard/resources.js','utf8'),context);
 vm.runInContext(fs.readFileSync('dashboard/app.js','utf8').replace(/init\(\);\s*$/,''),context);
 context.d={row:{id:'<img src=x onerror=alert(1)>',key:'source_item:x',subject_kind:'source_item',title:'<script>alert(1)</script>',browser:'chrome',platform:[],current_status:'unassessed'},fact:{summary:'<svg onload=alert(1)>'},assessments:[],selection_history:[],current_owner:null,related:[],evidence:[{url:'javascript:alert(1)',excerpt:'<script>bad()</script>'}],revisions:[],reports:[],legacy_flags:[]};
 vm.runInContext('data={catalog:{events:{}}}',context);
 const html=vm.runInContext('detailHTML(d)',context);
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<svg onload'));assert.ok(!html.includes('href="javascript:'));assert.match(html,/&lt;script&gt;/);
});
test('unmapped cards have no fourth webtoon status; mapped statuses remain exact',()=>{
 const node=()=>({value:''}),context=vm.createContext({URL,URLSearchParams,Intl,Date,ResearchModel:model,location:{search:''},document:{getElementById:node}});
 context.fetch=async path=>({ok:true,json:async()=>context.resourceData[path]});
 vm.runInContext(fs.readFileSync('dashboard/resources.js','utf8'),context);
 vm.runInContext(fs.readFileSync('dashboard/app.js','utf8').replace(/init\(\);\s*$/,''),context);
 context.r={id:'source',key:'source_item:source',subject_kind:'source_item',title:'Example',browser:'safari',platform:[],date:'2026-11-16',detail:'details/x.json'};
 vm.runInContext('data={catalog:{events:{}}}',context);
 const card=vm.runInContext('featureCard(r)',context);
 assert.ok(!card.includes('기록 미연결'));assert.ok(!card.includes('검증 대기'));assert.ok(!card.includes('원천 항목'));
 const html=fs.readFileSync('dashboard/index.html','utf8');
 assert.ok(!html.includes('value="unlinked"'));
 for(const status of ['todo','done','excluded'])assert.ok(html.includes(`value="${status}"`));
});
test('actual renderer applies only visible filters after switching data layers',async()=>{
 const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',innerHTML:'',textContent:'',checked:false,hidden:false,setAttribute(){}});return nodes.get(id);};
 const context=vm.createContext({URL,URLSearchParams,Intl,Date,ResearchModel:model,location:{search:'',pathname:'/'},history:{replaceState(){}},document:{getElementById:node,querySelector:node}});
 context.fetch=async path=>({ok:true,json:async()=>context.resourceData[path]});
 vm.runInContext(fs.readFileSync('dashboard/resources.js','utf8'),context);
 vm.runInContext(fs.readFileSync('dashboard/app.js','utf8').replace(/init\(\);\s*$/,''),context);
 context.feature={id:'feature',key:'feature_event:feature',subject_kind:'feature_event',title:'Feature',browser:'chrome',platform:['Windows'],date:'2026-11-16',detail:'details/f.json'};
 context.experiment={...context.feature,id:'experiment',key:'experiment:experiment',subject_kind:'experiment',title:'Experiment',experiment_kind:'base_feature',ai_related:false};
 context.input={selected:{features:[context.feature],flags:[]},history:[],catalog:{events:{}},counts:{source_item:119959,feature:3853,experiment:1},experiment_counts:{base_feature:1},indexes:{source_item:'sources.json',experiment:'experiments.json'}};
 context.resourceData={'sources.json':[context.feature],'experiments.json':[context.experiment]};
 vm.runInContext("data=input;view='all';",context);
 node('sort').value='new';node('membership').value='current';node('all-kind').value='source_item';node('ai').checked=true;
 await vm.runInContext('render()',context);
 assert.equal(node('result-count').textContent,'근거 항목 0건');
 assert.equal(node('source-totals').textContent,'전체 자료 · 기능 카탈로그 3,853개 · 수집한 근거 항목 119,959건 · Chrome 실험 카탈로그 1개');
 // The user changes only the layer. Hidden stale values must not affect results.
 node('all-kind').value='experiment';node('status').value='done';
 await vm.runInContext('render()',context);
 assert.equal(node('ai-label').hidden,true);assert.equal(node('status-label').hidden,true);
 assert.match(node('result-count').textContent,/1개 항목/);assert.match(node('feature-grid').innerHTML,/Experiment/);
 // Visible kind filtering must still work.
 node('kind').value='command_switch';await vm.runInContext('render()',context);assert.match(node('result-count').textContent,/0개 항목/);
 // A feature view ignores hidden experiment and PM filters, while retaining platform filtering.
 node('ai').checked=false;node('status').value='';node('change').value='removed';node('build').value='IS_ANDROID';node('judgment-status').value='excluded';
 await vm.runInContext("view='features';render()",context);
 assert.equal(node('kind-label').hidden,true);assert.equal(node('build-label').hidden,true);assert.equal(node('change-label').hidden,true);assert.equal(node('judgment-status-label').hidden,true);
 assert.match(node('result-count').textContent,/1개 항목/);
 node('platform').value='Android';await vm.runInContext('render()',context);assert.match(node('result-count').textContent,/0개 항목/);
});

test('computed hash/report detail paths follow new encoding and old JSON remains compatible',async()=>{
 const context=vm.createContext({URL,URLSearchParams,Intl,Date,TextEncoder,crypto:require('node:crypto').webcrypto,fetch:async()=>{},location:{search:''},document:{getElementById(){}}});
 vm.runInContext(fs.readFileSync('dashboard/resources.js','utf8'),context);
 vm.runInContext(fs.readFileSync('dashboard/app.js','utf8').replace(/init\(\);\s*$/,''),context);
 const digest=require('node:crypto').createHash('sha256').update('source_item:한글').digest('hex');
 vm.runInContext('data={resource_encoding:"gzip"}',context);
 assert.equal(await vm.runInContext('detailPath("source_item:한글")',context),'details/'+digest+'.json.gz');
 vm.runInContext('data={}',context);
 assert.equal(await vm.runInContext('detailPath("source_item:한글")',context),'details/'+digest+'.json');
});

test('Korean card summaries are searchable while original titles remain available',()=>{
 const copy=require('../dashboard/card-summaries.json');
 const row={title:'Local Network Access restrictions for Background Fetch',key:'source_item:example',id:'example',platform:[]};
 const original={...row};
 assert.equal(model.cardTitle(row,copy),'백그라운드 다운로드의 내부망 접근 제한');
 assert.equal(model.matches(row,{query:'내부망 접근'},'unlinked',copy),true);
 assert.equal(model.matches(row,{query:'Background Fetch'},'unlinked',copy),true);
 assert.deepEqual(row,original);
 assert.equal(model.cardTitle({...row,title:'A new unmapped feature'},copy),'A new unmapped feature');
 assert.equal(model.cardTitle({...row,title:'constructor'},copy),'constructor');
});
test('identical quick-search titles keep the exact event and release stage',()=>{
 const copy=require('../dashboard/card-summaries.json');
 const row={title:'퀵서치',key:'feature_event:whale-desktop-quick-search-ai-briefing-5-41-429-2-20261102'};
 assert.equal(model.cardTitle(row,copy),'선택한 글의 AI 요약·검색 연결 베타');
 assert.equal(model.cardTitle({...row,key:'feature_event:whale-desktop-quick-search-answer-toggles-5-41-429-3-stable-20261106'},copy),'퀵서치 결과 표시 설정 정식판 수록');
 assert.equal(model.cardTitle({...row,title:'Changed source title'},copy),'Changed source title');
});
test('card rendering shows a Korean summary and retains the escaped source title',()=>{
 const node=()=>({value:''}),context=vm.createContext({URL,URLSearchParams,Intl,Date,ResearchModel:model,location:{search:''},document:{getElementById:node}});
 context.fetch=async()=>{throw Error('Unexpected request');};
 vm.runInContext(fs.readFileSync('dashboard/resources.js','utf8'),context);
 vm.runInContext(fs.readFileSync('dashboard/app.js','utf8').replace(/init\(\);\s*$/,''),context);
 context.copy=require('../dashboard/card-summaries.json');
 context.row={title:'Permission Policy Merger: "direct-sockets-private" with "local-network" and "loopback-network"',key:'source_item:x',id:'x',browser:'chrome',platform:[],date:'2026-11-17'};
 vm.runInContext('data={catalog:{events:{}},card_summaries:copy}',context);
 const html=vm.runInContext('featureCard(row)',context);
 assert.match(html,/>로컬 네트워크 접근 권한 통합<\/span>/);
 assert.match(html,/aria-label="로컬 네트워크 접근 권한 통합 상세 보기"/);
 assert.match(html,/title="Permission Policy Merger: &quot;direct-sockets-private&quot;/);
});

test('report cards resolve subject-specific summaries and preserve frozen titles',async()=>{
 const nodes=new Map();
 const node=id=>{
  if(!nodes.has(id))nodes.set(id,{value:'',innerHTML:'',textContent:''});
  return nodes.get(id);
 };
 const context=vm.createContext({URL,URLSearchParams,Intl,Date,ResearchModel:model,
  location:{search:'',pathname:'/'},history:{replaceState(){}},document:{getElementById:node}});
 const copy=require('../dashboard/card-summaries.json');
 const items=Object.entries(copy.subjects).map(([key,entry])=>{
  const [subject_kind,subject_id]=key.split(':');
  return {subject_kind,subject_id,selection_kind:'features',timing:'backfill',action:'selected',
   details:{title:entry.title,browser:'whale'}};
 });
 items.push({...items[0],details:{title:'Changed source title',browser:'whale'}});
 items.push({...items[0],subject_id:'unmapped-event'});
 const report={date:'2026-11-16',revision:1,cutoff:'2026-11-16T12:00:00Z',outcome:'Fixture',
  completeness:{collection:'complete',evaluation:'complete'},items,catalog_transitions:[]};
 const original=JSON.stringify(report);
 context.fetch=async()=>({ok:true,json:async()=>report});
 context.input={card_summaries:copy,reports:[{date:report.date,revision:1,path:'report.json',markdown:'https://example.org/report'}]};
 vm.runInContext(fs.readFileSync('dashboard/resources.js','utf8'),context);
 vm.runInContext(fs.readFileSync('dashboard/app.js','utf8').replace(/init\(\);\s*$/,''),context);
 vm.runInContext("data=input;view='reports';browser='all'",context);
 node('report-date').value=report.date;
 node('report-revision').value='1';
 await vm.runInContext('renderReport()',context);
 const titles=[...node('report-content').innerHTML.matchAll(/class="card-title" title="([^"]*)">([^<]*)<\/span>/g)];
 assert.deepEqual(titles.map(match=>match[2]),[...Object.values(copy.subjects).map(entry=>entry.summary),'Changed source title','퀵서치']);
 assert.deepEqual(titles.map(match=>match[1]),items.map(item=>item.details.title));
 assert.equal(JSON.stringify(report),original);
});
