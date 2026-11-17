/* Generated Pages assets only. Repository/export JSON keeps its own contract. */
(function(root){
 'use strict';
 function createLoader(fetcher=root.fetch.bind(root), Decompressor=root.DecompressionStream){
  const cache=new Map();
  async function load(path){
   const response=await fetcher(path);
   if(!response.ok)throw Error('HTTP '+response.status+' · '+path);
   if(!path.endsWith('.json.gz'))return response.json();
   const bytes=new Uint8Array(await response.arrayBuffer());
   if(bytes[0]===0x1f&&bytes[1]===0x8b){
    if(typeof Decompressor!=='function')throw Error('이 브라우저는 압축 자료 읽기를 지원하지 않습니다. 최신 브라우저에서 다시 열어 주세요.');
    return new Response(new Blob([bytes]).stream().pipeThrough(new Decompressor('gzip'))).json();
   }
   // Fetch already decodes a server's Content-Encoding. Do not decompress twice.
   if((response.headers.get('Content-Encoding')||'').split(',').some(v=>v.trim().toLowerCase()==='gzip')){
    return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
   }
   throw Error('압축 자료 형식이 올바르지 않습니다: '+path);
  }
  return function json(path){
   if(!cache.has(path))cache.set(path,load(path).catch(error=>{cache.delete(path);throw error;}));
   return cache.get(path);
  };
 }
 const api={createLoader};
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.DashboardResources=api;
})(globalThis);
