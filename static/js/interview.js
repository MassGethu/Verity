'use strict';
let state=JSON.parse(document.getElementById('interview-state').textContent);
const fields=[...document.querySelectorAll('[data-question]')], form=document.getElementById('interview-form'), label=document.getElementById('save-status'),timer=document.getElementById('timer');
let anchor=performance.now(),remaining=state.deadline ? new Date(state.deadline)-new Date(state.server_now) : 360000;
let dirty=false,saving=false,debounce=null,submitRequested=false;
fields.forEach(f=>f.value=state.answers[f.dataset.question]||'');
function sync(next){state={...state,...next};anchor=performance.now();remaining=state.deadline?new Date(state.deadline)-new Date(state.server_now):360000;if(state.status==='submitted')lock();else if(state.status==='active')label.textContent='All saved responses restored';}
function lock(){fields.forEach(f=>f.disabled=true);document.getElementById('submit-interview').disabled=true;label.textContent='Submitted · responses locked';document.getElementById('submitted-message').hidden=false;}
function snapshot(){return Object.fromEntries(fields.map(f=>[f.dataset.question,f.value]));}
async function post(payload){const res=await fetch(state.url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':window.verityCSRF()},body:JSON.stringify(payload),signal:AbortSignal.timeout(15000)});const data=await res.json();if(!res.ok)throw new Error(data.error||'Could not save');return data;}
async function save(submit=false){
 if(state.status!=='active')return;
 if(submit)submitRequested=true;
 if(saving)return;
 if(!dirty&&!submitRequested)return;
 saving=true;const answers=snapshot(),isSubmit=submitRequested;dirty=false;label.textContent='Saving…';
 try{const next=await post({action:isSubmit?'submit':'save',answers,revision:state.revision});sync(next);if(state.status==='submitted'){fields.forEach(f=>f.value=state.answers[f.dataset.question]||'');dirty=false;submitRequested=false;}else label.textContent=dirty?'Unsaved changes':'All responses saved';}
 catch(error){dirty=true;label.textContent=error.message+' Your current text remains on this page.';if(error.message.includes('revision conflict')){state.status='conflict';fields.forEach(f=>f.readOnly=true);document.getElementById('submit-interview').disabled=true;}}
 finally{saving=false;if(submitRequested&&state.status==='active')setTimeout(()=>save(true),1000);}
}
fields.forEach(f=>f.addEventListener('input',()=>{dirty=true;label.textContent='Unsaved changes';clearTimeout(debounce);debounce=setTimeout(()=>save(),1000);}));
document.getElementById('start-interview')?.addEventListener('click',async function(){this.disabled=true;try{sync(await post({action:'start'}));document.getElementById('interview-intro').hidden=true;form.hidden=false;label.textContent='Interview started';}catch(e){label.textContent=e.message;this.disabled=false;}});
let confirmSubmission=false;
form.addEventListener('submit',event=>{event.preventDefault();if(!confirmSubmission){confirmSubmission=true;document.getElementById('submit-interview').textContent='Confirm submission · lock answers';label.textContent='Click again to submit and lock all three responses.';return;}save(true);});
setInterval(()=>{if(dirty&&state.status==='active')save();},5000);
function tick(){if(state.status==='ready')return;const ms=Math.max(0,remaining-(performance.now()-anchor)),seconds=Math.ceil(ms/1000);timer.textContent=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;timer.classList.toggle('urgent',seconds<60);if(ms<=0&&state.status==='active'){fields.forEach(f=>f.readOnly=true);dirty=true;save(true);}if(state.status==='submitted')timer.textContent='Submitted';}
tick();setInterval(tick,250);
if(state.status==='submitted')lock();else if(state.status==='active')label.textContent='All saved responses restored';
window.addEventListener('beforeunload',event=>{if(dirty&&state.status==='active'){event.preventDefault();event.returnValue='';}});
