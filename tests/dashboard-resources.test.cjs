const {test}=require('node:test');
const assert=require('node:assert/strict');
const {gzipSync}=require('node:zlib');
const {createLoader}=require('../dashboard/resources.js');
const payload={id:'원천-1',detail:'details/abc.json.gz',values:[null,false,0,'한글']};
const bytes=gzipSync(JSON.stringify(payload));
test('native gzip loader preserves values and shares successful requests',async()=>{
 let calls=0;const load=createLoader(async()=>{calls++;return new Response(bytes);});
 const [a,b]=await Promise.all([load('a.json.gz'),load('a.json.gz')]);
 assert.deepEqual(a,payload);assert.equal(a,b);assert.equal(calls,1);
});
test('old plain JSON and HTTP-decoded gzip remain readable',async()=>{
 const old=createLoader(async()=>new Response(JSON.stringify(payload)),null);
 assert.deepEqual(await old('a.json'),payload);
 const decoded=createLoader(async()=>new Response(JSON.stringify(payload),{headers:{'Content-Encoding':'gzip'}}),null);
 assert.deepEqual(await decoded('a.json.gz'),payload);
});
test('HTTP failure, corrupt gzip and wrong format fail visibly and can retry',async()=>{
 for(const bad of [()=>new Response('failed',{status:503}),()=>new Response(bytes.subarray(0,15)),()=>new Response('{}')]){
  let calls=0;const load=createLoader(async()=>++calls===1?bad():new Response(bytes));
  await assert.rejects(load('retry.json.gz'));assert.deepEqual(await load('retry.json.gz'),payload);assert.equal(calls,2);
 }
});
test('missing native API has an explicit error; failed requests are not cached',async()=>{
 let calls=0;const load=createLoader(async()=>{calls++;return new Response(bytes);},null);
 await assert.rejects(load('a.json.gz'),/최신 브라우저/);await assert.rejects(load('a.json.gz'),/최신 브라우저/);assert.equal(calls,2);
});
