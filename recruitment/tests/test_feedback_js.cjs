const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
function harness(draft){
 const elements={},callbacks={};for(const id of ['compose-data','open-gmail','feedback-editor','draft-status','copy-status'])elements[id]={textContent:'',disabled:false,addEventListener:(event,fn)=>callbacks[id+':'+event]=fn};
 elements['compose-data'].textContent=JSON.stringify(draft);let opened;
 const context={document:{getElementById:id=>elements[id],querySelectorAll:()=>[]},window:{open:(url,...args)=>opened={url,args}},URLSearchParams,navigator:{}};
 vm.runInNewContext(fs.readFileSync('static/js/feedback.js','utf8'),context);
 return {elements,callbacks,open:()=>opened};
}
const draft={email:'test+demo@example.com',subject:'Feedback & next steps ✓',body:'First line\nSecond + line & unicode ✓'};
const h=harness(draft);h.callbacks['open-gmail:click']();const url=new URL(h.open().url);
assert.equal(url.origin,'https://mail.google.com');assert.equal(url.searchParams.get('to'),draft.email);assert.equal(url.searchParams.get('su'),draft.subject);assert.equal(url.searchParams.get('body'),draft.body);
h.callbacks['feedback-editor:input']();assert.equal(h.elements['open-gmail'].disabled,true);assert.match(h.elements['draft-status'].textContent,/Unsaved/);
const long=harness({...draft,body:'x'.repeat(9000)});long.callbacks['open-gmail:click']();assert.equal(long.open(),undefined);assert.match(long.elements['copy-status'].textContent,/too long/);
console.log('Gmail encoding, unsaved draft lock, and oversized-draft fallback: passed');
