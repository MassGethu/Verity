const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/js/upload.js','utf8');
function fixture(files,failFirst=false){
 const button={},status={},requests=[];let submit,reloads=0;
 const form={dataset:{prepareUrl:'/prepare',completeUrl:'/complete'},querySelector:s=>s==='button'?button:{files},addEventListener:(name,fn)=>submit=fn};
 vm.runInNewContext(source,{document:{getElementById:id=>id==='cloud-upload-form'?form:id==='cloud-upload-status'?status:null},window:{verityCSRF:()=> 'csrf'},location:{reload:()=>reloads++},AbortSignal:{timeout:()=>undefined},fetch:async(url,options)=>{
  requests.push({url,...options});
  if(url==='/prepare')return {ok:true,json:async()=>({uploads:files.map((f,i)=>({url:'https://storage/'+i,ticket:'ticket-'+i}))})};
  if(failFirst&&url==='https://storage/0')return {ok:false};
  return {ok:true,json:async()=>({id:1})};
 }});
 return {run:()=>submit({preventDefault(){}}),requests,status,reloads:()=>reloads};
}
(async()=>{
 const f=fixture([{name:'candidate.pdf',size:100}]);await f.run();
 assert.equal(f.requests.length,3);assert.equal(f.requests[0].headers['X-CSRFToken'],'csrf');
 assert.equal(f.requests[1].method,'PUT');assert.equal(f.requests[1].headers['Content-Type'],'application/pdf');
 assert.equal(JSON.parse(f.requests[2].body).ticket,'ticket-0');assert.equal(f.reloads(),1);
 const bad=fixture([{name:'too-large.pdf',size:6000000}]);await bad.run();assert.equal(bad.requests.length,0);
 const partial=fixture([{name:'one.pdf',size:20},{name:'two.pdf',size:30}],true);await partial.run();
 assert.match(partial.status.textContent,/1 uploaded and queued/);assert.equal(partial.reloads(),0);
 console.log('Direct private upload metadata, CSRF, raw PUT, ticket completion, limits and partial failures: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
