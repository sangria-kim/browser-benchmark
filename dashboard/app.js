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
const temporalHTML = scope => !scope ? '' : `<section class="detail-box"><h4>수집 기간과 근거</h4><p>${esc(scope.since)} 이후 · ${{in_period:'기간 내 근거 확인',before_period:'기간 이전',after_cutoff:'수집 마감 이후',unchanged:'연초와 같은 정의',unknown:'날짜 또는 대응 미확인',context:'비교 문맥'}[scope.status]||esc(scope.status)}</p><p>근거 날짜 ${esc(scope.evidence_date||'정확한 날짜 없음')} · 정밀도 ${esc(scope.precision)}<br>수집 마감 ${esc(scope.cutoff)}</p><p>${esc(scope.reason)}</p>${scope.baseline_revision?`<p class="mono">${esc(scope.baseline_revision)} → ${esc(scope.current_revision)}<br>commit 시각 ${esc(scope.baseline_committed_at)} → ${esc(scope.current_committed_at)}</p><p>현재 정의의 양 끝 비교입니다. 삭제·중간 변경 후 원복 이력은 포함하지 않습니다.</p>`:''}</section>`;
let data, rows=[], page=1, browser='all', view='features', dataset=[], datedRows=null;
let detailId=null, opener=null, detailToken=0, renderToken=0, currentReport=null, restoringURL=true;
const pageSize=18, params=new URLSearchParams(location.search);
const views=['features','flags','reports','all'];
const kindNames={flag_entry:'UI flag',base_feature:'Base feature',command_switch:'Command switch'};
selectionNames.unassessed='판단 없음';
const controls=['search','platform','status','change','sort','ai','membership','judgment-date','all-kind','judgment-status','kind','from-date','to-date','build'];
const detailPath=async key=>{
 const bytes=new TextEncoder().encode(key), digest=await crypto.subtle.digest('SHA-256',bytes);
 return 'details/'+Array.from(new Uint8Array(digest),x=>x.toString(16).padStart(2,'0')).join('')+'.json'+(data?.resource_encoding==='gzip'?'.gz':'');
};
const json=DashboardResources.createLoader();
function extra(row){return row.subject_kind==='feature_event'?data.catalog.events[row.id]||{}:{};}
function wt(row){return extra(row).webtoon||{status:'unlinked'};}
function buttonDetail(row,label){return `<button class="history-event" data-detail="${esc(row.key)}" data-path="${esc(row.detail||'')}">${esc(label||row.title)}</button>`;}
function currentFeatureRows(){return data.selected.features;}
function renderCards(){
 $('browser-cards').innerHTML=Object.entries(names).map(([id,name])=>{const es=currentFeatureRows().filter(r=>id==='all'||r.browser===id),latest=es.map(r=>r.date).sort().at(-1);return `<button class="browser-card" data-browser="${id}" aria-pressed="${browser===id}" aria-label="${name}, 현재 선정 ${es.length}개 필터"><span class="browser-top">${icon(id)}${name}</span><strong>${es.length}</strong><small>개 선정</small><span class="date">${latest?date(latest)+' 업데이트':'현재 선정 없음'}</span></button>`;}).join('');
 $('browser-filter-boxes').innerHTML=Object.entries(names).map(([id,name])=>`<button class="browser-filter-box" data-browser="${id}" aria-pressed="${browser===id}">${icon(id)}<span>${id==='all'?'전체':esc(name)}</span><span class="filter-count">${currentFeatureRows().filter(r=>id==='all'||r.browser===id).length}</span></button>`).join('');
 $('overview').innerHTML=`<div class="metric"><span class="metric-label">현재 선정 · 기능 / 실험</span><div class="metric-line"><strong>${data.selected.features.length} / ${data.selected.flags.length}</strong><small>PM 판단 기준</small></div></div><div class="metric"><span class="metric-label">전체 보존 · 원천 / 기능</span><div class="metric-line"><strong>${data.counts.source_item.toLocaleString()}</strong><small>개 원천 · ${data.counts.feature}개 기능</small></div></div><div class="metric tip"><span class="metric-label">전체 Chrome 실험 · ${data.counts.experiment.toLocaleString()}</span><p>${Object.entries(kindNames).map(([k,n])=>`${n} ${data.experiment_counts[k]||0}`).join(' · ')}<br>현재 등록된 수집 자료 기준 · 전수 수집 완료를 뜻하지 않습니다.</p></div>`;
}
function updateURL(){const p=new URLSearchParams();if(view!=='features')p.set('view',view);if(browser!=='all')p.set('browser',browser);for(const id of controls){const el=$(id),v=el.type==='checkbox'?(el.checked?'1':''):el.value;if(v&&!['new','current','source_item'].includes(v))p.set(id,v);}if(view==='reports'){p.set('report-date',$('report-date').value);p.set('report-revision',$('report-revision').value);}history.replaceState(null,'',location.pathname+(p.size?'?'+p:'')+location.hash);}
function options(id,values,label){const old=$(id).value;$(id).innerHTML=`<option value="">${label}</option>`+values.map(v=>`<option value="${esc(v)}">${esc(changeNames[v]||v)}</option>`).join('');$(id).value=old;}
function filterScope(){
 const all=view==='all',experiments=view==='flags'||(all&&$('all-kind').value==='experiment');
 return {experiments,kind:experiments||(all&&$('all-kind').value==='source_item'),webtoon:view==='features',ai:view!=='reports'&&!experiments};
}
function configure(){
 const report=view==='reports',all=view==='all',scope=filterScope();
 $('judgment-toolbar').hidden=report;$('report-controls').hidden=!report;$('report-content').hidden=!report;
 document.querySelector('.toolbar').hidden=report;document.querySelector('.pagination').hidden=report;
 $('membership-label').hidden=all;$('membership').disabled=!!$('judgment-date').value;$('judgment-date-label').hidden=all;$('all-kind-label').hidden=!all;$('judgment-status-label').hidden=!all;
 $('kind-label').hidden=!scope.kind;$('build-label').hidden=!scope.experiments;
 $('status-label').hidden=!scope.webtoon;$('change-label').hidden=!scope.experiments;$('ai-label').hidden=!scope.ai;
 $('browser-filters').hidden=view==='flags';
 for(const v of views){$(v+'-tab').setAttribute('aria-selected',String(v===view));$(v+'-tab').tabIndex=v===view?0:-1;}
 $('results-panel').setAttribute('aria-labelledby',view+'-tab');
 $('table-eyebrow').textContent={features:'SELECTED FEATURES',flags:'SELECTED EXPERIMENTS',reports:'DAILY RESEARCH',all:'SOURCE EXPLORER'}[view];
 $('table-title').textContent={features:'비교해 볼 브라우저 기능',flags:'선정된 Chrome 실험',reports:'오늘의 판단과 변화',all:'전체 수집 자료 탐색'}[view];
 $('table-description').textContent=report?'리포트는 작성 시점의 사실과 판단을 보존합니다. 날짜와 revision을 선택하세요.':all?'전체 원천, 기능 카탈로그, 실험 카탈로그를 구분해 확인합니다. 원천 항목이 곧 기능 사건은 아닙니다.':scope.experiments?'선정된 소스 실험입니다. 제품 도입 여부와 등록·만료·기본값은 상세에서 확인하세요.':'현재 선정과 과거 판단을 살펴보세요. 카드를 누르면 사실·판단·웹툰을 함께 확인할 수 있어요.';
}
async function render(){
 const token=++renderToken;configure();renderCards();
 try{
  if(view==='reports'){await renderReport();if(token!==renderToken)return;$('feature-grid').hidden=true;$('empty').hidden=true;return;}
  if(view==='all')dataset=await json(data.indexes[$('all-kind').value]);
  else if($('judgment-date').value){const entry=data.dates.find(d=>d.date===$('judgment-date').value);datedRows=(await json(entry.path)).rows;dataset=datedRows.filter(r=>(!!r.experiment_kind)===(view==='flags'));}
  else dataset=$('membership').value==='history'?data.history.filter(r=>(!!r.experiment_kind)===(view==='flags')):data.selected[view];
  if(token!==renderToken)return;
  options('platform',[...new Set(dataset.flatMap(r=>r.platform))].sort(),'전체 플랫폼');
  options('change',[...new Set(dataset.map(r=>r.event_type).filter(Boolean))].sort(),'전체 변경');
  if(restoringURL){for(const id of ['platform','change'])if(params.has(id))$(id).value=params.get(id);restoringURL=false;}
  const scope=filterScope();
  const f={browser:view==='flags'?'all':browser,query:$('search').value.trim(),platform:$('platform').value,webtoon:scope.webtoon?$('status').value:'',ai:scope.ai&&$('ai').checked,kind:scope.kind?$('kind').value:'',status:view==='all'?$('judgment-status').value:'',change:scope.experiments?$('change').value:'',build:scope.experiments?$('build').value:'',from:$('from-date').value,to:$('to-date').value};
  rows=dataset.filter(r=>ResearchModel.matches(r,f,wt(r).status));
  const sort=$('sort').value;rows.sort((a,b)=>sort==='name'?a.title.localeCompare(b.title,'ko'):(a.date.localeCompare(b.date)*(sort==='old'?1:-1)||a.key.localeCompare(b.key)));
  page=Math.max(1,Math.min(page,Math.ceil(rows.length/pageSize)||1));
  $('feature-grid').innerHTML=rows.slice((page-1)*pageSize,page*pageSize).map(featureCard).join('');$('feature-grid').hidden=!rows.length;$('empty').hidden=!!rows.length;
  $('empty-title').textContent=view==='features'&&browser!=='all'?names[browser]+'의 조건에 맞는 선정 항목이 없습니다':'조건에 맞는 항목이 없습니다';
  $('empty-description').textContent=view==='features'?'선정되지 않은 자료도 전체 원천 목록에서 확인할 수 있습니다.':'검색어를 줄이거나 필터를 초기화해 보세요.';
  $('result-count').textContent=`${rows.length.toLocaleString()}개 항목`+($('judgment-date').value?` · ${$('judgment-date').value} 종료 시점 판단`:'');
  const counts=Object.entries(kindNames).map(([k,n])=>`${n} ${rows.filter(r=>r.experiment_kind===k).length}`).join(' · ');
  $('scope-note').textContent=view==='flags'||(view==='all'&&$('all-kind').value==='experiment')?counts:$('judgment-date').value?'판단 시간 기준 · 당시 저장된 사실 목록을 재현하지 않습니다.':'날짜: 근거 확인일(KST) · 출시일과 구분';
  $('page-info').textContent=rows.length?`${(page-1)*pageSize+1}–${Math.min(page*pageSize,rows.length)} / ${rows.length.toLocaleString()} · ${page}/${Math.ceil(rows.length/pageSize)} 페이지`:'0개 결과';$('prev').disabled=page===1;$('next').disabled=page*pageSize>=rows.length;
  updateURL();
 }catch(error){if(token!==renderToken)return;$('result-count').textContent='자료를 불러오지 못했습니다. 다시 선택하거나 새로고침해 주세요. '+error.message;$('feature-grid').innerHTML='';$('table-body').innerHTML='';$('report-content').innerHTML='';$('empty-title').textContent='자료를 불러오지 못했습니다';$('empty-description').textContent=error.message;$('empty').hidden=false;}
}
function featureCard(row){const w=wt(row);return `<button class="feature-card" data-detail="${esc(row.key)}" data-path="${esc(row.detail)}" aria-haspopup="dialog" aria-label="${esc(row.title)} 상세 보기" style="--browser-color:${colors[row.browser]||colors.all}"><span class="card-top"><span class="browser-cell">${icon(row.browser)}${esc(names[row.browser]||row.browser)}</span><span class="card-date">${esc(date(row.date))}</span></span><span class="card-title">${esc(row.title)}</span><span class="card-platform">${esc(row.platform.filter(p=>p!=='unknown').join(' · '))||' '}${row.versions?.length?' · 관찰 버전 '+esc(row.versions.join(', ')):''}</span><span class="card-bottom">${row.experiment_kind?tag(kindNames[row.experiment_kind]):w.status==='unlinked'?'<span></span>':tag(statusNames[w.status],w.status)}<span class="card-open">자세히 ↗</span></span></button>`;}
function assessmentHTML(a){return `<div class="assessment"><h4>${esc(date(a.assessed_at))} · ${esc(selectionNames[a.status]||a.status)}</h4><p>${esc(a.assessment_id)} · ${esc(a.rule_version)} · ${esc(a.evaluator||'')}</p><ul>${(a.reasons||[]).map(r=>`<li>${esc(r)}</li>`).join('')}</ul>${a.comparison_question?`<p><b>비교 질문</b> ${esc(a.comparison_question)}</p>`:''}${a.benchmark?`<details><summary>비교 과제 · 조건 · 측정</summary><pre class="evidence-body">${esc(readable(a.benchmark))}</pre></details>`:''}<p>다시 볼 조건: ${esc(a.revisit_trigger||'미기록')} · 이전 판단 ${esc(a.supersedes||'없음')}</p></div>`;}
function evidenceHTML(evidence){return evidence.map((s,i)=>`<div><p>${link(s.url,s.section||`공식 근거 ${i+1}`)}</p><p>${esc(s.excerpt||'')}</p><p class="mono">revision ${esc(s.revision_id||s.source_revision||'미기록')}<br>hash ${esc(s.content_sha256||'미기록')}</p></div>`).join('');}
async function openDetail(key,path='',snapshot=null){
 const token=++detailToken;detailId=key;
 if(!$('feature-dialog').open){opener=document.activeElement;$('feature-dialog').showModal();}
 $('detail-content').innerHTML='<div class="detail"><p role="status">상세를 불러오는 중…</p></div>';
 try{const detail=await json(path||await detailPath(key));if(token!==detailToken||!$('feature-dialog').open)return;
 $('feature-dialog').setAttribute('aria-label',detail.row.title+' 상세');$('detail-content').innerHTML=detailHTML(detail,snapshot);$('detail-content').scrollTop=0;attachMediaFallbacks();
 }catch(error){if(token===detailToken)$('detail-content').innerHTML='<div class="detail"><p>상세 자료를 불러오지 못했습니다. 닫은 뒤 다시 선택해 주세요.</p><p>'+esc(error.message)+'</p></div>';}
}
function detailHTML(d,snapshot){
 const row=d.row,f=d.fact,x=extra(row),w=wt(row),after=f.after||{},delta=f.delta||{};
 const chosen=$('judgment-date').value,cutoff=chosen?instant(chosen+'T23:59:59.999+09:00'):Infinity;
 const eligible=d.assessments.filter(a=>instant(a.assessed_at)<=cutoff),past=eligible.filter(a=>!eligible.some(b=>b.supersedes===a.assessment_id))[0];
 const current=d.assessments.find(a=>!d.assessments.some(b=>b.supersedes===a.assessment_id));
 const before=f.before??delta.before??x.comparison?.before,changed=f.after??delta.after??x.comparison?.after??f.summary;
 const sourceOnly=row.subject_kind==='source_item';
 const frozen=snapshot?`<section class="detail-box frozen"><h4>리포트에 보존된 사실 · ${esc(currentReport?.date)} r${esc(currentReport?.revision)}</h4><h3>${esc(snapshot.details.title)}</h3><p>${esc(snapshot.details.summary)}</p><p>발표 ${esc(date(snapshot.announced_at))} · 사실 확인 ${esc(date(snapshot.observed_at))} · 판단 확인 ${esc(date(snapshot.discovered_at))}</p><p>유형 ${esc(snapshot.details.event_type||'원천 항목')} · ${esc(snapshot.timing)} · ${esc(snapshot.action)}</p><p>보고 당시 판단 ${esc(selectionNames[snapshot.details.status])} · 규칙 ${esc(snapshot.details.assessment_rule_version)}</p><ul>${snapshot.details.reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul><p>${esc(snapshot.details.comparison_question||'')}</p><p class="mono">${esc(snapshot.subject_id)} · ${esc(snapshot.assessment_id)}<br>${esc([snapshot.change_id,...(snapshot.related_change_ids||[])].join(' · '))}</p>${evidenceHTML(snapshot.evidence||[])}<p>아래는 같은 ID의 현재 저장 사실 및 판단 이력입니다. 위 보존 근거와 구분합니다.</p></section>`:'';
 return `<div class="detail">${frozen}<div class="detail-top"><div><p class="eyebrow">${esc(row.id)}</p><h3>${esc(row.title)}</h3><p>${esc(names[row.browser])} · 버전 ${esc(readable(f.version))} · ${esc(channelNames[f.channel]||f.channel||after.product_channel||'단계 미확인')} · ${esc(row.platform.join(' · '))}</p><div class="badge-line">${tag(sourceOnly?'원천 항목 · 기능 사건 아님':row.experiment_kind?kindNames[row.experiment_kind]:'기능 사건 / 카탈로그')}${tag(selectionNames[row.current_status])}${tag(row.current_selected?'현재 선정 목록':'현재 선정 목록 밖')}</div></div></div>
 <section class="detail-box"><h4>판단 시점</h4><p>현재 대상 판단: ${esc(selectionNames[current?.status]||'판단 없음')} · ${esc(date(current?.assessed_at))}</p>${chosen?`<p>선택일 ${esc(chosen)} 종료 시점: ${esc(selectionNames[past?.status]||'판단 없음')} · 현재 사실을 당시 사실로 간주하지 않습니다.</p>`:''}${d.current_owner&&d.current_owner.key!==row.key?`<p>현재 카탈로그 대표 항목: ${buttonDetail(d.current_owner)} · ${esc(selectionNames[d.current_owner.status])}<br>대표 사건 교체이며, 이 항목의 PM 선정 해제 판정을 뜻하지 않습니다.</p>`:''}${d.assessment_subject!==row.key?`<p>이 원천의 대표 평가 대상: ${buttonDetail({key:d.assessment_subject,title:d.assessment_subject})}</p>`:''}</section>
 ${temporalHTML(row.temporal_scope)}
 <div class="detail-grid"><section class="detail-box"><h4>${sourceOnly?'보존된 원천 사실':'이 사건에 기록된 변화'}</h4><div class="before-after"><div><small>BEFORE · 변경 전</small><pre class="evidence-body">${esc(before==null?'별도 변경 전 기록 없음':readable(before))}</pre></div><div><small>AFTER · 변경 후</small><pre class="evidence-body">${esc(readable(changed||f.title))}</pre></div></div><p>${esc(typeof delta==='string'?delta:'')}</p><p>발표 ${esc(date(f.announced_at||f.published_at))} · 적용 ${esc(date(f.effective_at))}<br>근거 확인 ${esc(date(f.observed_at||row.date))} (KST)</p><h4>적용 조건 · 근거 수준</h4><p>${scopeHTML(f.scope)}</p><p>${esc(f.verification_status||f.record_status||'미확인')}</p>${row.experiment_kind?'<p>소스 기본값·만료·등록은 제품 출시 또는 설치본 지원을 뜻하지 않습니다.</p>':''}<details><summary>저장된 사실 전체 · 기본값 / 만료 / 관계</summary><pre class="evidence-body">${esc(readable(f))}</pre></details></section>
 <section class="detail-box"><h4>실제 예시 · 공식 화면</h4>${x.media?.length?x.media.map(mediaHTML).join(''):'<p>확인된 예시가 아직 연결되지 않았습니다.</p>'}<h4>모찌 & 푸딩 웹툰</h4>${tag(statusNames[w.status],w.status)}<p>${esc(w.note||'이 사건과 일치하는 제작 기록이 없습니다.')}</p>${w.url?link(w.url,'최종 웹툰 열기'):''}${w.scope?`<p>제작 범위: ${esc(w.scope)}</p>`:''}</section></div>
 <section class="detail-box"><h4>공식 근거 · 현재 보존 기록</h4>${evidenceHTML(d.evidence)}${f.document_url?link(f.document_url,'구조화 사건'):''}${f.feature_url?link(f.feature_url,'기능 문서'):''}${(f.reports||[]).map(r=>link(r.url,r.date+' 기존 리포트')).join(' ')}</section>
 <details class="history" open><summary>판단 이력 ${d.assessments.length}건</summary>${[...d.assessments].reverse().map(assessmentHTML).join('')||'<p>공개 판단 기록이 없습니다.</p>'}</details>
 <details class="history"><summary>선정 변화 ${d.selection_history.length}건</summary>${d.selection_history.map(c=>`<p>${esc(date(c.effective_at))} · ${esc(c.action)} · ${esc(c.change_id)}</p>`).join('')}</details>
 ${d.related.length?`<details class="history" open><summary>같은 기능 / 실험의 다른 사건 ${d.related.length}건</summary>${d.related.map(r=>`<p>${esc(date(r.date))} · ${buttonDetail(r)} · ${esc(selectionNames[r.current_status])}</p>`).join('')}</details>`:''}
 ${(d.relationships||[]).length?`<h4>관련 기능 / 실험</h4>${d.relationships.map(r=>`<p>${buttonDetail(r)}</p>`).join('')}`:''}
 ${d.revisions.length?`<details class="history"><summary>원본·정정 사실 기록 ${d.revisions.length}건</summary>${d.revisions.map(r=>`<pre class="evidence-body">${esc(readable(r))}</pre>`).join('')}</details>`:''}
 ${d.legacy_flags.map(f=>`<details class="history"><summary>기존 flag 문서 · ${esc(f.id)}</summary>${link(f.document_url,'원문')}<pre class="evidence-body">${esc(f.body)}</pre></details>`).join('')}
 ${d.reports.length?`<h4>관련 리포트</h4>${d.reports.map(r=>`<p><button class="history-event" data-report="${esc(r.date)}" data-revision="${r.revision}">${esc(r.date)} · r${r.revision}</button></p>`).join('')}` : ''}</div>`;
}
function reportOptions(){const d=$('report-date').value;const reports=data.reports.filter(r=>r.date===d);$('report-revision').innerHTML=reports.map(r=>`<option value="${r.revision}">r${r.revision} · ${date(r.cutoff)}</option>`).join('');}
async function renderReport(){
 const token=renderToken;const entry=data.reports.find(r=>r.date===$('report-date').value&&String(r.revision)===$('report-revision').value);
 if(!entry){$('report-content').innerHTML='<p>공개 리포트가 없습니다.</p>';return;}
 const report=await json(entry.path);if(token!==renderToken)return;currentReport=report;
 const filtered=report.items.filter(i=>(browser==='all'||i.details.browser===browser)&&(!$('report-kind').value||i.selection_kind===$('report-kind').value));
 $('result-count').textContent=`${filtered.length}개 변화 · 전체 리포트 ${report.items.length}개`;$('scope-note').textContent='KST 기준 · 관측/판단일은 출시일이 아닙니다.';
 const completeness={complete:'완료',partial:'부분 완료',failed:'실패',unknown:'미확인'};
 $('report-content').innerHTML=`<section class="report-summary"><p class="eyebrow">${esc(report.date)} · REVISION ${report.revision}</p><h3>수집 ${esc(completeness[report.completeness.collection])} · 평가 ${esc(completeness[report.completeness.evaluation])}</h3><p>마감 ${esc(report.cutoff)} · ${esc(report.outcome)}</p>${report.completeness.collection!=='complete'||report.completeness.evaluation!=='complete'?'<p>미완료 범위가 있습니다. 결과가 없더라도 새로운 변화가 없다고 단정하지 않습니다.</p>':''}${link(entry.markdown,'보존된 Markdown 리포트')}</section><div class="feature-grid">${filtered.map(i=>`<button class="feature-card" data-report-item="${esc(i.subject_id)}" aria-haspopup="dialog"><span class="card-top">${esc(names[i.details.browser])} <span>${esc(i.selection_kind==='flags'?'실험':'기능')}</span></span><span class="card-title">${esc(i.details.title)}</span><span class="card-platform">${esc(i.timing==='backfill'?'과거 보강 · 신규 출시 아님':i.timing==='initial'?'초기 기준선 · 신규 출시 아님':'판단 / 사실 변화')}</span><span class="card-bottom">${esc(i.action)}<span class="card-open">보존 근거 보기 ↗</span></span></button>`).join('')}</div>${report.catalog_transitions.length?`<section class="detail"><h3>현재 대표 항목 교체</h3>${report.catalog_transitions.map(t=>`<p>${esc(t.catalog_id)} · ${buttonDetail({key:t.previous.subject_kind+':'+t.previous.subject_id,title:t.previous.subject_id})} → ${buttonDetail({key:t.current.subject_kind+':'+t.current.subject_id,title:t.current.subject_id})}<br>이전 항목의 PM 선정 해제를 새로 만든 기록이 아닙니다.</p>`).join('')}</section>`:''}`;updateURL();
}
function reset(){for(const id of controls){const el=$(id);if(el.type==='checkbox')el.checked=false;else el.value='';}$('sort').value='new';$('membership').value='current';$('all-kind').value='source_item';browser='all';page=1;render();}
function switchView(next){view=next;if(view==='flags')browser='chrome';page=1;for(const id of ['platform','status','kind','change','build','search','judgment-date'])$(id).value='';$('ai').checked=false;render();}
async function init(){try{
 data=await json('data.json');view=views.includes(params.get('view'))?params.get('view'):'features';browser=Object.hasOwn(names,params.get('browser'))?params.get('browser'):'all';if(view==='flags')browser='chrome';
 $('updated').textContent=date(data.updated_at)+' KST';$('event-count').textContent=data.selected.features.length;$('flag-count').textContent=data.selected.flags.length;
 $('source-ref').textContent=`기준 ${data.source.ref} · ${data.source.sha.slice(0,7)} · 웹툰 대조 ${data.catalog.checked_at}`;
 if(data.collection_scope)$('source-ref').textContent+=` · ${data.collection_scope.since} 이후 확인 · 출처별 수집 마감은 상세 근거 참조`;
 $('judgment-date').innerHTML='<option value="">현재</option>'+data.dates.map(d=>`<option value="${d.date}">${d.date} · ${d.count}개 선정</option>`).join('');
 $('report-date').innerHTML=[...new Set(data.reports.map(r=>r.date))].map(d=>`<option>${d}</option>`).join('');if(params.has('report-date'))$('report-date').value=params.get('report-date');reportOptions();if(params.has('report-revision'))$('report-revision').value=params.get('report-revision');
 for(const id of controls)if(params.has(id)){if($(id).type==='checkbox')$(id).checked=params.get(id)==='1';else $(id).value=params.get(id);}
 for(const id of ['browser-cards','browser-filter-boxes'])$(id).onclick=e=>{const b=e.target.closest('[data-browser]');if(!b)return;browser=b.dataset.browser;page=1;if(view==='flags'){view='features';for(const filter of ['kind','change','build','platform'])$(filter).value='';}render().then(()=>{[...$(id).querySelectorAll('[data-browser]')].find(el=>el.dataset.browser===browser)?.focus({preventScroll:true});});};
 document.querySelector('.tabs').onclick=e=>{const b=e.target.closest('[data-view]');if(b)switchView(b.dataset.view);};
 document.querySelector('.tabs').onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const index=e.key==='Home'?0:e.key==='End'?views.length-1:(views.indexOf(view)+(e.key==='ArrowRight'?1:views.length-1))%views.length;switchView(views[index]);$(views[index]+'-tab').focus();}};
 for(const id of controls)$(id).addEventListener(['search','build'].includes(id)?'input':'change',()=>{page=1;if(id==='membership')$('judgment-date').value='';if(id==='all-kind'){for(const filter of ['kind','change','platform','status','build'])$(filter).value='';}render();});
 $('report-date').onchange=()=>{reportOptions();render();};$('report-revision').onchange=render;$('report-kind').onchange=render;
 $('reset').onclick=reset;$('empty-reset').onclick=()=>{if(view==='features'||view==='flags'){const saved=browser;reset();browser=saved;view='all';$('all-kind').value='source_item';render();}else reset();};$('prev').onclick=()=>{page--;render();};$('next').onclick=()=>{page++;render();};
 document.addEventListener('click',e=>{const b=e.target.closest('[data-detail]');if(b)openDetail(b.dataset.detail,b.dataset.path);const ri=e.target.closest('[data-report-item]');if(ri){const item=currentReport.items.find(i=>i.subject_id===ri.dataset.reportItem);openDetail(item.subject_kind+':'+item.subject_id,'',item);}const r=e.target.closest('[data-report]');if(r){$('feature-dialog').close();view='reports';$('report-date').value=r.dataset.report;reportOptions();$('report-revision').value=r.dataset.revision;render();}});
 $('detail-close').onclick=()=>$('feature-dialog').close();$('feature-dialog').addEventListener('close',()=>{detailToken++;detailId=null;$('detail-content').innerHTML='';if(opener?.isConnected)opener.focus({preventScroll:true});else $('reset').focus({preventScroll:true});});
 document.addEventListener('keydown',e=>{if(e.key==='/'&&!$('feature-dialog').open&&!['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)){e.preventDefault();$('search').focus();}});
 document.querySelector('.table-scroll').hidden=true;
 await render();startWebtoonSync();
 }catch(e){$('updated').textContent='자료 로드 실패';$('result-count').textContent='자료를 불러오지 못했습니다. 새로고침해 주세요.';}}
function mediaHTML(m){return `<div class="media-frame">${m.type==='image'?`<img src="${esc(safeURL(m.url))}" alt="${esc(m.label)}" loading="lazy" referrerpolicy="no-referrer">`:m.type==='video'?`<video src="${esc(safeURL(m.url))}" controls preload="none" playsinline aria-label="${esc(m.label)}"></video>`:''}<p>${link(m.url,m.label)} · ${esc(m.note||'공식 화면 · 직접 실행한 결과가 아닙니다.')}</p></div>`;}
function attachMediaFallbacks(){document.querySelectorAll('.media-frame img,.media-frame video').forEach(el=>el.addEventListener('error',()=>{el.hidden=true;const p=document.createElement('p');p.textContent='미리보기를 불러오지 못했습니다. 아래 원본 링크에서 확인하세요.';el.after(p);},{once:true}));}

function scopeHTML(scope){
 if(typeof scope!=='object'||!scope)return esc(readable(scope));
 const labels={conditions:'적용 조건',region:'지역',language:'언어',account:'계정',korea_availability:'한국 제공',korean_language:'한국어',korean_language_support:'한국어',real_test:'직접 시험',device_test:'직접 시험',default:'소스 기본값',dependency:'의존 조건',platform_evidence:'플랫폼 근거',expiry_milestone:'만료 milestone',installed_build_exposure:'설치본 노출'};
 return Object.entries(scope).filter(([k,v])=>v!=null).map(([k,v])=>`${esc(labels[k]||k)}: ${esc(v==='not_run'?'미실행':readable(v))}`).join('<br>');
}

function nextWebtoonCheck(now=new Date()){
 const kst=new Date(now.getTime()+9*60*60*1000);
 for(const hour of [9,10]){
  const at=new Date(Date.UTC(kst.getUTCFullYear(),kst.getUTCMonth(),kst.getUTCDate(),hour-9));
  if(at>now)return at;
 }
 return new Date(Date.UTC(kst.getUTCFullYear(),kst.getUTCMonth(),kst.getUTCDate()+1,0));
}
function startWebtoonSync(){
 const baseline=structuredClone(data.catalog);
 let lastSha='', lastChecked=baseline.checked_at;
 const source='work/browser-benchmark';
 async function refresh(){
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
 $('sync-state').textContent=`웹툰 대조 ${baseline.checked_at} · 자동 확인 대기`;
 function schedule(){
  const at=nextWebtoonCheck();
  setTimeout(async()=>{
   // A suspended browser must not replay a missed check later in the day.
   if(Date.now()-at.getTime()<60*1000)await refresh();
   schedule();
  },at.getTime()-Date.now());
 }
 schedule();
}

init();
