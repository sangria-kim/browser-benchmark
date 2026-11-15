'use strict';
const $ = (id) => document.getElementById(id);
const names = {all:'전체 브라우저',chrome:'Chrome',edge:'Edge',firefox:'Firefox',safari:'Safari',brave:'Brave',whale:'Whale',opera:'Opera',vivaldi:'Vivaldi'};
const colors = {all:'#beb2f4',chrome:'#dec477',edge:'#75c7b7',firefox:'#e7a575',safari:'#8cbef1',brave:'#e89f88',whale:'#86cbbd',opera:'#dd8b9c',vivaldi:'#e49393'};
const channelNames={stable:'정식',beta:'Beta',nightly:'Nightly',developer:'개발자',unknown:'단계 미확인','source-main':'소스 관찰',experiment_source_main:'소스 실험',stable_and_beta:'정식 · Beta',Proposed:'제안',Planned:'예정',stable_browser_with_optional_windows_preview_update:'정식 · Windows 미리보기 필요',public_rollout_announced:'공개 배포 발표',stable_browser_early_preview_feature:'정식 · 초기 미리보기 기능','Developer trial / Finch plan':'개발자 시험 · 실험 배포 계획'};
const statusNames = {todo:'작업 전',done:'작업 완료',excluded:'작업 대상 아님',unlinked:'기록 미연결'};
const changeNames = {added:'등록 추가',removed:'등록 삭제',modified:'등록 변경',registration:'등록 추가',removal:'등록 삭제',expiry_extension:'만료 연장',improvement:'개선',bug_fix:'오류 수정',behavior_fix:'동작 수정',behavior_change:'동작 변경',channel_expansion:'채널 확대',stable_release_inclusion:'정식판 수록',rollout_expansion:'배포 확대',verification_pending:'근거 재확인',pending_verification:'검증 대기',planned_milestone_change:'목표 버전 변경',announcement:'공식 발표',default_change:'기본값 변경',source_behavior_change:'소스 동작 변경',source_scope_change:'소스 범위 변경',planned_retirement:'종료 예고',flag_registration:'flag 등록',options_modified:'선택지 변경',beta_feature_change:'Beta 변경',beta_feature_observation:'Beta 관찰',experiment_observed:'실험 관찰',experiment_observation:'실험 관찰',experimental_observation:'실험 관찰',deprecation_announcement:'종료 예고',support_scope_change:'지원 범위 변경',rollout:'배포',feature_rollout:'기능 배포',release_inclusion:'릴리스 수록',stable_adoption:'정식판 반영',stable_introduction:'정식판 도입',registration_with_options:'선택지 등록',planned_scope_expansion:'범위 확대 예정',planned_milestone_confirmation:'목표 버전 확인',policy_observation:'정책 관찰'};
const selectionNames = {selected:'분석 선정',watch:'관찰 중',pending_verification:'검증 대기',excluded:'분석 제외'};
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const readable = value => value == null || value === 'unknown' ? '미확인' : typeof value === 'object' ? JSON.stringify(value,null,2) : String(value);
const safeURL = value => {try {const u=new URL(value);return u.protocol==='https:'?u.href:'#';}catch{return '#';}};
const link = (url,label,cls='') => `<a class="${cls}" href="${esc(safeURL(url))}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
const instant=value=>Date.parse(/^\d{4}-\d{2}-\d{2}$/.test(value)?value+'T00:00:00+09:00':value);
const date = value => !value ? '미확인' : /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : Number.isNaN(Date.parse(value)) ? String(value) : new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
const icon = browser => `<span class="browser-icon" style="--browser-color:${colors[browser]||colors.all}">${browser==='all'?'◉':esc(names[browser]?.[0]||'C')}</span>`;
const tag = (text,cls='') => `<span class="tag ${cls}">${esc(text)}</span>`;
let data, rows=[], page=1, openId=null;
const pageSize=18;
let detailId=null, openerId=null;
const params=new URLSearchParams(location.search);
let browser=Object.hasOwn(names,params.get('browser'))?params.get('browser'):'all';
let view=params.get('view')==='flags'?'flags':'features';
function extra(e){return data.catalog.events[e.event_id]||{};}
function wt(e){return extra(e).webtoon||{status:'unlinked'};}
function eventDate(e){return e.observed_at||e.assessed_at||'';}
function featureCount(items){return new Set(items.map(e=>e.feature_id)).size;}
function delta(e){const d=e.delta;if(typeof d==='string')return d;return d?.after||d?.observation||d?.change_kind||e.summary;}
function updateURL(){const p=new URLSearchParams();if(view!=='features')p.set('view',view);if(browser!=='all')p.set('browser',browser);for(const id of ['search','platform','status','change','sort'])if($(id).value&&$(id).value!=='new')p.set(id,$(id).value);if($('ai').checked)p.set('ai','1');history.replaceState(null,'',location.pathname+(p.size?'?'+p:'')+location.hash);}
function renderCards(){
 $('browser-cards').innerHTML=Object.entries(names).map(([id,name])=>{const es=data.events.filter(e=>id==='all'||e.browser===id);const latest=es.map(eventDate).sort().at(-1);return `<button class="browser-card" data-browser="${id}" aria-pressed="${browser===id}" aria-label="${name}, ${featureCount(es)}개 기능 필터"><span class="browser-top">${icon(id)}${name}</span><strong>${featureCount(es)}</strong><small>개 기능</small><span class="date">${latest?date(latest)+' <span>업데이트</span>':'수집 대기'}</span></button>`;}).join('');
}
function renderBrowserFilters(){
 $('browser-filters').hidden=view==='flags';
 $('browser-filter-boxes').innerHTML=Object.entries(names).map(([id,name])=>{const es=data.events.filter(e=>id==='all'||e.browser===id);return `<button class="browser-filter-box" data-browser="${id}" aria-pressed="${browser===id}">${icon(id)}<span>${id==='all'?'전체':esc(name)}</span><span class="filter-count">${featureCount(es)}</span></button>`;}).join('');
}
function renderOverview(){
 const es=data.events.filter(e=>browser==='all'||e.browser===browser), linked=es.filter(e=>wt(e).status!=='unlinked'),done=es.filter(e=>wt(e).status==='done');
 $('overview').innerHTML=`<div class="metric"><span class="metric-label">${names[browser]} · 수집된 변화</span><div class="metric-line"><strong>${featureCount(es)}</strong><small>개 기능 / ${es.length}개 변경 사건</small></div><div class="progress"><span style="width:100%;background:var(--accent)"></span></div></div><div class="metric webtoon"><span class="metric-label">모찌 & 푸딩 · 웹툰 연결</span><div class="metric-line"><strong>${done.length}</strong><small>개 사건에 완성본 연결 · 상태 확인 ${linked.length}/${es.length}</small></div><div class="progress"><span style="width:${es.length?done.length/es.length*100:0}%"></span></div></div><div class="metric tip"><span class="metric-label">CHROME EXPERIMENTS</span><p><b>${data.flags.length.toLocaleString()}</b>개 flag의 소스 변경 이력도 확인하세요.<br>실험실에서 등록·삭제·변경과 공식 diff를 따로 탐색합니다.</p></div>`;
}
function setOptions(){
 const ps=view==='features'?[...new Set(data.events.flatMap(e=>Array.isArray(e.platform)?e.platform:[e.platform]).filter(Boolean))].sort():['Android','Windows','macOS','Linux','ChromeOS','Desktop','iOS'];
 $('platform').innerHTML='<option value="">전체 플랫폼</option>'+ps.map(p=>`<option value="${esc(p)}">${esc(p)}</option>`).join('');
 const actions=[...new Set(data.flags.flatMap(f=>f.history.map(h=>h.action)))].sort();
 $('change').innerHTML='<option value="">전체 변경</option>'+actions.map(a=>`<option value="${esc(a)}">${esc(changeNames[a]||a)}</option>`).join('');
}
function flagPlatform(f){return [...new Set(f.history.map(h=>h.platform).filter(Boolean))].join(', ')||'미확인';}
function flagMatchesPlatform(f,p){const masks={Android:'kOsAndroid',Windows:'kOsWin',macOS:'kOsMac',Linux:'kOsLinux',ChromeOS:'kOsCrOS',Desktop:'kOsDesktop',iOS:'iOS'};return flagPlatform(f).includes(masks[p]||p)||f.body.includes(p);}
function render(){
 renderCards();renderBrowserFilters();renderOverview();updateURL();
 const isFlag=view==='flags';
 for(const id of ['status-label','ai-label'])$(id).hidden=isFlag;
 $('change-label').hidden=!isFlag;
 for(const id of ['features','flags']){const b=$(id+'-tab');b.setAttribute('aria-selected',String(view===id));b.tabIndex=view===id?0:-1;}
 $('results-panel').setAttribute('aria-labelledby',view+'-tab');
 $('table-eyebrow').textContent=isFlag?'CHROME FLAGS LAB':'FEATURE EXPLORER';
 $('table-title').textContent=isFlag?'Chrome flags 실험실':(browser==='all'?'모든 브라우저':names[browser])+'의 기능 변화';
 $('table-description').textContent=isFlag?'등록부와 소스에서 관찰한 변화입니다. flag 추가·삭제는 제품 출시·철회의 증거가 아닙니다.':'기능별로 필터에 맞는 최신 변경을 보여줍니다. 카드를 누르면 상세 내용과 이전 이력을 확인할 수 있어요.';
 $('search').placeholder=isFlag?'flag ID, 소스 키워드 검색':'기능명, 버전, 키워드 검색';
 const q=$('search').value.trim().toLocaleLowerCase(),p=$('platform').value,s=$('status').value,c=$('change').value;
 rows=(isFlag?data.flags:data.events).filter(e=>{
   if(isFlag)return (!q||[e.id,e.body].join(' ').toLowerCase().includes(q))&&(!p||flagMatchesPlatform(e,p))&&(!c||e.history.some(h=>h.action===c));
   return (browser==='all'||e.browser===browser)&&(!q||[e.summary,e.feature_id,e.event_id,e.version,e.delta,readable(e.delta)].join(' ').toLowerCase().includes(q))&&(!p||(Array.isArray(e.platform)?e.platform:[e.platform]).includes(p))&&(!s||wt(e).status===s)&&(!$('ai').checked||e.ai_related);
 });
 const matchedEvents=rows.length;
 if(!isFlag){
  const latest=new Map();
  for(const e of rows){const old=latest.get(e.feature_id);if(!old||eventDate(e)>eventDate(old)||(eventDate(e)===eventDate(old)&&e.event_id>old.event_id))latest.set(e.feature_id,e);}
  rows=[...latest.values()];
 }
 const sort=$('sort').value;
 rows.sort((a,b)=>sort==='name'?(a.summary||a.id).localeCompare(b.summary||b.id,'ko'):((isFlag?a.date:eventDate(a)).localeCompare(isFlag?b.date:eventDate(b)))*(sort==='old'?1:-1)||String(a.event_id||a.id).localeCompare(b.event_id||b.id));
 page=Math.max(1,Math.min(page,Math.ceil(rows.length/pageSize)||1));
 $('result-count').textContent=`${isFlag?rows.length.toLocaleString()+'개 flag':matchedEvents+'개 변경 사건 · '+rows.length+'개 기능'}`;
 $('scope-note').textContent=isFlag?'날짜: 소스 기록 기준 · OS mask ≠ 설치본 지원':'날짜: 근거 확인일(KST) · 출시일과 구분';
 $('table-head').innerHTML='<tr><th style="width:29%">FLAG ID</th><th style="width:13%">최근 기록 · UTC</th><th style="width:14%">변경 유형</th><th style="width:16%">소스 OS MASK</th><th style="width:16%">만료 · 소스 기본값</th><th style="width:12%">공식 근거</th></tr>';
 const visible=rows.slice((page-1)*pageSize,page*pageSize);
 $('table-body').innerHTML=isFlag?visible.map(flagRow).join(''):'';
 $('feature-grid').innerHTML=isFlag?'':visible.map(featureCard).join('');
 $('feature-grid').hidden=isFlag||!rows.length;
 $('empty').hidden=rows.length>0;
 const waiting=!isFlag&&browser!=='all'&&!data.events.some(e=>e.browser===browser);
 $('empty-title').textContent=waiting?`${names[browser]} 조사 결과를 기다리고 있어요`:'조건에 맞는 항목이 없어요';
 $('empty-description').textContent=waiting?'조사 결과가 공개 데이터에 반영되면 기능 수와 변경 이력이 표시됩니다.':'검색어를 줄이거나 필터를 초기화해 보세요.';
 document.querySelector('.table-scroll').hidden=!isFlag||rows.length===0;
 $('page-info').textContent=rows.length?`${(page-1)*pageSize+1}–${Math.min(page*pageSize,rows.length)} / ${rows.length.toLocaleString()} · ${page} / ${Math.ceil(rows.length/pageSize)} 페이지`:'0개 결과';
 $('prev').disabled=page===1;$('next').disabled=page*pageSize>=rows.length;
 if(openId)attachMediaFallbacks();
}
function featureCard(e){
 const x=extra(e),w=wt(e),platforms=(Array.isArray(e.platform)?e.platform:[e.platform]).filter(Boolean);
 return `<button class="feature-card" data-detail="${esc(e.event_id)}" aria-haspopup="dialog" aria-label="${esc(e.feature_title||e.summary)} 상세 보기" style="--browser-color:${colors[e.browser]||colors.all}"><span class="card-top"><span class="browser-cell">${icon(e.browser)}${esc(names[e.browser]||e.browser)}</span><span class="card-date">${date(eventDate(e))}</span></span><span class="card-title">${esc(e.feature_title||e.summary)}</span><span class="card-platform">${esc(platforms.map(readable).join(' · ')||'플랫폼 미확인')}</span><span class="card-bottom">${tag(statusNames[w.status],w.status)}<span class="card-open">${x.media?.length?'▧ 예시 · ':''}자세히 ↗</span></span></button>`;
}
function openFeature(id){
 const e=data.events.find(e=>e.event_id===id);if(!e)return;
 detailId=id;
 $('detail-content').innerHTML=eventDetail(e);
 $('feature-dialog').setAttribute('aria-label',(e.feature_title||e.summary)+' 상세');
 if(!$('feature-dialog').open){openerId=id;$('feature-dialog').showModal();}
 $('detail-content').scrollTop=0;
 attachMediaFallbacks();
}
function mediaHTML(m){return `<div class="media-frame">${m.type==='image'?`<img src="${esc(safeURL(m.url))}" alt="${esc(m.label)}" loading="lazy" referrerpolicy="no-referrer">`:m.type==='video'?`<video src="${esc(safeURL(m.url))}" controls preload="none" playsinline aria-label="${esc(m.label)}"></video>`:''}<p>${link(m.url,m.label)} · ${esc(m.note||'공식 화면 · 직접 실행한 결과가 아닙니다.')}</p></div>`;}
function attachMediaFallbacks(){document.querySelectorAll('.media-frame img,.media-frame video').forEach(el=>el.addEventListener('error',()=>{el.hidden=true;const p=document.createElement('p');p.textContent='미리보기를 불러오지 못했습니다. 아래 원본 링크에서 확인하세요.';el.after(p);},{once:true}));}

function scopeHTML(scope){
 if(typeof scope!=='object'||!scope)return esc(readable(scope));
 const labels={conditions:'적용 조건',region:'지역',language:'언어',account:'계정',korea_availability:'한국 제공',korean_language:'한국어',korean_language_support:'한국어',real_test:'직접 시험',device_test:'직접 시험',default:'소스 기본값',dependency:'의존 조건',platform_evidence:'플랫폼 근거',expiry_milestone:'만료 milestone',installed_build_exposure:'설치본 노출'};
 return Object.entries(scope).filter(([k,v])=>v!=null).map(([k,v])=>`${esc(labels[k]||k)}: ${esc(v==='not_run'?'미실행':readable(v))}`).join('<br>');
}

function eventDetail(e){
 const x=extra(e),w=wt(e),d=e.delta,prev=data.events.find(p=>p.event_id===e.previous_event_id);
 const before=x.comparison?.before||(d&&typeof d==='object'?d.before:null),after=x.comparison?.after||(d&&typeof d==='object'?d.after:null);
 const history=data.events.filter(p=>p.feature_id===e.feature_id&&p.event_id!==e.event_id).sort((a,b)=>eventDate(b).localeCompare(eventDate(a)));
 return `<div class="detail"><div class="detail-top"><div><p class="eyebrow">${esc(e.feature_id)}</p><h3>${esc(e.summary)}</h3><p>${esc(names[e.browser]||e.browser)} · 버전 ${esc(readable(e.version))} · ${esc((Array.isArray(e.platform)?e.platform:[e.platform]).filter(Boolean).join(" · "))}</p><div class="badge-line">${tag(selectionNames[e.selection_status]||e.selection_status)}${e.priority?tag(e.priority):''}${tag(channelNames[e.channel]||e.channel||'단계 미확인')}</div></div>${link(e.feature_url||e.document_url,'기능 원문')}</div><div class="detail-grid"><div class="detail-box"><h4>무엇이 달라졌나요?</h4><div class="before-after"><div><small>BEFORE · 변경 전</small><p>${esc(before||prev?.summary||'원문에 분리된 변경 전 설명이 없습니다. 아래 변경 근거를 확인하세요.')}</p></div><div><small>AFTER · 변경 후</small><p>${esc(after||e.summary)}</p></div></div><p>${esc(typeof d==='string'?d:readable(d))}</p><h4 style="margin-top:20px">적용 조건과 근거 수준</h4><p>${scopeHTML(e.scope)}</p><p class="mono">${esc(e.verification_status?.includes('source')?'소스 근거 · 설치본 확인 여부는 원문 참조':'공식 자료 근거 · 직접 시험 여부는 원문 참조')}</p><p>발표일 ${esc(date(e.announced_at))} · 적용일 ${esc(date(e.effective_at))}<br>근거 확인일 ${esc(date(e.observed_at))} (KST)</p></div><div class="detail-box"><h4>실제 예시 · 공식 화면</h4>${x.media?.length?x.media.map(mediaHTML).join(''):'<div class="media-placeholder"><strong>확인된 예시가 아직 연결되지 않았어요</strong><p>공식 근거는 아래에서 확인할 수 있습니다.<br>출처 문서를 실제 캡처나 시연 영상으로 대신 표시하지 않습니다.</p></div>'}<h4 style="margin-top:22px">모찌 & 푸딩 웹툰</h4>${tag(statusNames[w.status],w.status)}<p>${esc(w.note||'이 사건과 일치하는 제작 기록을 아직 연결하지 않았습니다.')}</p>${w.url?link(w.url,'최종 웹툰 열기'):''}${w.scope?`<p>제작 범위: ${esc(w.scope)}</p>`:''}</div></div><div class="source-list">${link(e.document_url,'구조화 사건')}${(e.sources||[]).filter(s=>s.url).map((s,i)=>link(s.url,s.title||`공식 출처 ${i+1}`)).join('')}${(e.reports||[]).map(r=>link(r.url,r.date+' 보고서')).join('')}</div>${e.comparison_question?`<p><b>비교 질문</b> · ${esc(e.comparison_question)}</p>`:''}${history.length?`<details class="history"><summary>이 기능의 다른 변경 이력 ${history.length}건</summary><ul>${history.map(h=>`<li>${date(eventDate(h))} · <button class="history-event" data-history="${esc(h.event_id)}">${esc(h.summary)}</button></li>`).join('')}</ul></details>`:''}</div>`;
}
function flagRow(f){const last=[...f.history].sort((a,b)=>b.date.localeCompare(a.date))[0],isOpen=openId===f.id;return `<tr><td><button class="feature-button mono" data-open="${esc(f.id)}" aria-expanded="${isOpen}">⚑ ${esc(f.id)}</button><span class="sub">${isOpen?'접기 −':'소스 이력 보기 +'}</span></td><td class="mono">${esc(f.date||'미확인')}</td><td>${tag(changeNames[last?.action]||last?.action||'문서 확인')}</td><td class="mono">${esc(last?.platform||'문서에서 확인')}</td><td><span class="sub" style="margin:0">${esc(f.expiry||'만료 미확인')}</span><span class="sub">${esc(f.default_state||'기본값 미확인')}</span></td><td>${link(last?.url||f.links[0]?.url||f.document_url,'소스 보기')}</td></tr>${isOpen?`<tr class="detail-row"><td colspan="6"><div class="detail"><div class="detail-top"><div><p class="eyebrow">SOURCE OBSERVATION ONLY</p><h3>${esc(f.id)}</h3><p>chrome://flags/#${esc(f.id)} · 설치본에서의 존재·노출은 미확인</p></div>${link(f.document_url,'flag 원문')}</div><div class="detail-grid"><div class="detail-box"><h4>등록·만료·기본값 · 기록된 원문</h4><div class="evidence-body">${esc(f.body)}</div></div><div class="detail-box"><h4>변경 타임라인</h4>${f.history.length?`<ol class="history">${[...f.history].reverse().map(h=>`<li><span class="mono">${esc(h.date)}</span> · ${tag(changeNames[h.action]||h.action)}<br>${esc(h.platform)} ${h.url?link(h.url,'diff'):''}</li>`).join('')}</ol>`:'<p>표 형식 이력은 없습니다. 원문과 아래 공식 근거에서 확인하세요.</p>'}<div class="source-list">${f.links.map(l=>link(l.url,l.label)).join('')}</div>${f.related_events.length?`<h4 style="margin-top:22px">관련 기능 변화</h4>${f.related_events.map(id=>{const e=data.events.find(e=>e.event_id===id);return `<p>${link(e.document_url,e.summary)}</p>`;}).join('')}`:''}</div></div></div></td></tr>`:''}`;}
function reset(){for(const id of ['search','platform','status','change'])$(id).value='';$('sort').value='new';$('ai').checked=false;browser='all';page=1;openId=null;render();}
function switchView(next){view=next;if(next==='flags')browser='chrome';page=1;openId=null;setOptions();$('status').value='';$('ai').checked=false;$('search').value='';render();}
async function init(){try{
 const response=await fetch('data.json');if(!response.ok)throw new Error('HTTP '+response.status);data=await response.json();
 $('updated').textContent=date(data.updated_at)+' KST';$('event-count').textContent=data.events.length;$('flag-count').textContent=data.flags.length.toLocaleString();
 $('source-ref').textContent=`기준 ${data.source.ref} · ${data.source.sha.slice(0,7)} · 웹툰 대조 ${data.catalog.checked_at}`;
 setOptions();for(const id of ['search','platform','status','change','sort'])if(params.has(id))$(id).value=params.get(id);if(!$('sort').value)$('sort').value='new';$('ai').checked=params.get('ai')==='1';
 for(const id of ['browser-cards','browser-filter-boxes'])$(id).addEventListener('click',ev=>{const b=ev.target.closest('[data-browser]');if(!b)return;browser=b.dataset.browser;if(view==='flags')switchView('features');else{page=1;openId=null;render();}const replacement=[...$(id).querySelectorAll('[data-browser]')].find(el=>el.dataset.browser===browser);replacement?.focus({preventScroll:true});});
 document.querySelector('.tabs').addEventListener('click',ev=>{const b=ev.target.closest('[data-view]');if(b)switchView(b.dataset.view);});
 document.querySelector('.tabs').addEventListener('keydown',ev=>{if(['ArrowLeft','ArrowRight'].includes(ev.key)){ev.preventDefault();switchView(view==='features'?'flags':'features');$(view+'-tab').focus();}});
 for(const id of ['search','platform','status','change','sort','ai'])$(id).addEventListener(id==='search'?'input':'change',()=>{page=1;openId=null;render();});
 $('reset').onclick=reset;$('empty-reset').onclick=reset;
 $('prev').onclick=()=>{page--;openId=null;render();};$('next').onclick=()=>{page++;openId=null;render();};
 $('table-body').addEventListener('click',ev=>{const b=ev.target.closest('[data-open]');if(b){const id=b.dataset.open;openId=openId===id?null:id;render();const focusButton=[...document.querySelectorAll('.feature-button')].find(el=>el.dataset.open===id);focusButton?.focus({preventScroll:true});}});
 $('feature-grid').addEventListener('click',ev=>{const card=ev.target.closest('[data-detail]');if(card)openFeature(card.dataset.detail);});
 $('detail-content').addEventListener('click',ev=>{const item=ev.target.closest('[data-history]');if(item)openFeature(item.dataset.history);});
 $('detail-close').onclick=()=>$('feature-dialog').close();
 $('feature-dialog').addEventListener('close',()=>{detailId=null;$('detail-content').innerHTML='';render();const opener=[...document.querySelectorAll('[data-detail]')].find(el=>el.dataset.detail===openerId);(opener||$('reset')).focus({preventScroll:true});});
 document.addEventListener('keydown',ev=>{if(ev.key==='/'&&!$('feature-dialog').open&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){ev.preventDefault();$('search').focus();}});
 render();
 startWebtoonSync();
}catch(error){$('updated').textContent='자료 로드 실패';$('table-body').innerHTML=`<tr><td>자료를 불러오지 못했습니다. 잠시 후 새로고침해 주세요. ${esc(error.message)}</td></tr>`;}}
function startWebtoonSync(){
 const baseline=structuredClone(data.catalog);
 let lastSha='', lastChecked=baseline.checked_at;
 const source='work/browser-benchmark';
 async function refresh(){
  if(document.hidden)return;
  $('sync-refresh').disabled=true;
  try{
   const result=await WebtoonFeed.load(fetch);
   if(instant(result.feed.checked_at)<instant(lastChecked))throw new Error('Older snapshot');
   if(result.sha!==lastSha){
    data.catalog=WebtoonFeed.merge(baseline,result.feed);
    lastSha=result.sha;lastChecked=result.feed.checked_at;
    if(!$('feature-dialog').open)render();
   }
   $('sync-state').textContent=`웹툰 대조 ${result.feed.checked_at} · ${source} @ ${lastSha.slice(0,7)} · 소유자 검토 전 자료`;
   $('sync-state').dataset.state='live';
  }catch{
   $('sync-state').textContent=lastSha?`웹툰 갱신 지연 · 마지막 성공 ${lastChecked} · ${source} @ ${lastSha.slice(0,7)} · 소유자 검토 전 자료`:`웹툰 자동 갱신 연결 대기 · 배포본 대조 ${baseline.checked_at} 유지`;
   $('sync-state').dataset.state='stale';
  }finally{$('sync-refresh').disabled=false;}
 }
 $('sync-refresh').onclick=refresh;
 refresh();
 setInterval(refresh,5*60*1000);
}
init();
