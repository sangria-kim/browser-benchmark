'use strict';
// Public status feed only. Never load Notion credentials or execute remote code.
const WebtoonFeed = (() => {
 const repository='sangria-kim/browser-benchmark';
 const ref='work/browser-benchmark';
 const path='dashboard/webtoons.json';
 const object=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
 function validate(feed){
  if(!object(feed)||feed.schema_version!==1||!object(feed.events)||typeof feed.checked_at!=='string'||!/^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(feed.checked_at)||!Number.isFinite(Date.parse(feed.checked_at)))throw new Error('Invalid feed');
  if(Object.keys(feed).some(k=>!['schema_version','checked_at','events'].includes(k)))throw new Error('Unexpected feed field');
  for(const [id,entry] of Object.entries(feed.events)){
   if(!/^[a-z0-9][a-z0-9-]{0,220}$/.test(id)||!object(entry)||!['todo','done','excluded'].includes(entry.status))throw new Error('Invalid status');
   if(Object.keys(entry).some(k=>!['status','url','scope','note'].includes(k)))throw new Error('Unexpected status field');
   for(const k of ['scope','note'])if(k in entry&&(typeof entry[k]!=='string'||entry[k].length>2000))throw new Error('Invalid description');
   if(entry.status==='done'&&!entry.url)throw new Error('Missing result');
   if('url' in entry){
    const url=new URL(entry.url);
    if(url.protocol!=='https:'||!['www.notion.so','notion.so','app.notion.com'].includes(url.hostname)||url.username||url.password||url.port||url.search||!/[a-f0-9]{32}$/.test(url.pathname.replaceAll('-','')))throw new Error('Invalid result URL');
   }
  }
  return feed;
 }
 function merge(baseline,feed){
  validate(feed);
  const catalog=JSON.parse(JSON.stringify(baseline));
  for(const [id,webtoon] of Object.entries(feed.events)){
   catalog.events[id]={...catalog.events[id],webtoon:{...webtoon}};
  }
  catalog.checked_at=feed.checked_at;
  return catalog;
 }
 async function load(request){
  // Resolve the explicit candidate branch once, then read an immutable commit.
  const options={cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(15000)};
  const head=await request(`https://api.github.com/repos/${repository}/commits?sha=${encodeURIComponent(ref)}&path=${path}&per_page=1`,options);
  if(!head.ok)throw new Error('Feed ref unavailable');
  const commits=await head.json(),sha=commits?.[0]?.sha;
  if(!/^[a-f0-9]{40}$/.test(sha))throw new Error('Invalid commit');
  const response=await request(`https://raw.githubusercontent.com/${repository}/${sha}/${path}`,options);
  if(!response.ok)throw new Error('Feed unavailable');
  return {sha,feed:validate(await response.json())};
 }
 return {validate,merge,load};
})();
if(typeof module!=='undefined')module.exports=WebtoonFeed;
