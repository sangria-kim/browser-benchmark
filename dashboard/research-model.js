/* Pure presentation rules shared by the browser and regression tests. */
(function(root){
 'use strict';
 const safeURL=value=>{try{const u=new URL(value);return u.protocol==='https:'?u.href:'#';}catch{return '#';}};
 const day=value=>!value?'':/^\d{4}-\d{2}-\d{2}$/.test(value)?value:new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(value));
 function cardTitle(row,copy={}){
  const subject=copy.subjects?.[row.key];
  if(subject?.title===row.title)return subject.summary;
  return Object.hasOwn(copy.titles||{},row.title)?copy.titles[row.title]:row.title;
 }
 function matches(row,f,webtoon='unlinked',copy={}){
  return (!f.browser||f.browser==='all'||row.browser===f.browser)&&(!f.query||[row.title,cardTitle(row,copy),row.id,row.catalog_id].join(' ').toLowerCase().includes(f.query.toLowerCase()))&&(!f.platform||row.platform.includes(f.platform))&&(!f.kind||row.experiment_kind===f.kind)&&(!f.status||row.status===f.status)&&(!f.webtoon||webtoon===f.webtoon)&&(!f.ai||!!row.ai_related)&&(!f.change||row.event_type===f.change)&&(!f.build||(row.build_conditions||[]).join(' ').toLowerCase().includes(f.build.toLowerCase()))&&(!f.from||day(row.date)>=f.from)&&(!f.to||day(row.date)<=f.to);
 }
 const api={safeURL,day,matches,cardTitle};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.ResearchModel=api;
})(globalThis);
