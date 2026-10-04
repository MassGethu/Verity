const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/interview_guide.js', 'utf8');
class Element {
  constructor(value='') { this.value=value; this.textContent=''; this.hidden=true; this.disabled=false; this.events={}; this.selectors={}; this.dataset={}; }
  addEventListener(name,fn) {this.events[name]=fn;}
  querySelector(selector) {return this.selectors[selector] || null;}
  querySelectorAll(selector) {return this.selectors[selector] || [];}
}
function fixture(auto=false) {
  const state=new Element(); state.textContent=JSON.stringify({auto_prepare:auto,revision:2,generate_url:'/generate',save_url:'/save'});
  const panel=new Element(), progress=new Element(), form=new Element(), status=new Element(), copy=new Element(), regen=new Element(), submit=new Element(), disabled=new Element(); disabled.disabled=true;
  const revision=new Element('2'), replace=new Element(); replace.checked=true;
  regen.selectors={'[name=replace]':replace,'[name=revision]':revision}; form.selectors={'button[type=submit]':submit};
  const fields=['question','purpose','follow_up'].map((name)=>{const field=new Element(name+' text');field.dataset.field=name;return field;});
  const card=new Element();card.dataset.questionId='profile-1';card.selectors={'[data-field]':fields,blockquote:[{innerText:'Actual résumé passage'}]};
  panel.selectors={'button':[submit,disabled],'[data-guide-generate]':[regen],'[data-guide-question]':[card],'[name=revision]':[revision],'[data-guide-source]':[]};
  const elements={'guide-state':state,'interview-guide':panel,'guide-progress':progress,'guide-edit-form':form,'guide-save-status':status,'copy-guide':copy};
  const requests=[],events={};let reloads=0,copied='',ok=true,result={revision:3},confirmation=true;
  const window={verityCSRF:()=> 'csrf',location:{reload:()=>reloads++},addEventListener:(name,fn)=>events[name]=fn,confirm:()=>confirmation};
  vm.runInNewContext(source,{window,document:{getElementById:id=>elements[id]},fetch:async(url,options)=>{requests.push({url,...options});return {ok,json:async()=>result};},navigator:{clipboard:{writeText:async text=>copied=text}}});
  return {requests,form,status,copy,regen,revision,progress,disabled,events,fields,reloads:()=>reloads,copied:()=>copied,response:(success,data)=>{ok=success;result=data;},confirm:value=>confirmation=value};
}
const flush=async()=>{for(let n=0;n<8;n++) await Promise.resolve();};
(async()=>{
  const automatic=fixture(true);await flush();assert.equal(automatic.requests.length,1);assert.equal(automatic.requests[0].headers['X-CSRFToken'],'csrf');assert.equal(JSON.parse(automatic.requests[0].body).replace,false);assert.equal(automatic.reloads(),1);
  const f=fixture();f.form.events.input();f.response(false,{error:'Revision conflict'});await f.form.events.submit({preventDefault(){}});assert.match(f.status.textContent,/Revision conflict.*text remains/);assert.equal(f.fields[0].value,'question text');
  let prevented=false;f.events.beforeunload({preventDefault(){prevented=true;}});assert.ok(prevented);
  await f.copy.events.click();assert.match(f.copied(),/Unsaved recruiter edits/);assert.match(f.copied(),/Actual résumé passage/);
  f.confirm(false);f.regen.events.submit({preventDefault(){}});assert.equal(f.requests.length,1,'Unsaved regeneration cancelled');
  f.response(true,{revision:4});await f.form.events.submit({preventDefault(){}});assert.equal(f.revision.value,4);assert.match(f.status.textContent,/edits saved/);
  f.response(false,{error:'Provider unavailable'});f.regen.events.submit({preventDefault(){}});await flush();assert.match(f.progress.textContent,/Provider unavailable/);assert.equal(f.disabled.disabled,true,'Failed preparation preserves disabled controls');
  console.log('Guide automatic POST, CSRF, edit conflicts, revisions, copy citations and regeneration protection: passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
