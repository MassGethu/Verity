'use strict';
const processButton=document.getElementById('process-batch');
if(processButton)processButton.addEventListener('click',async()=>{
 const queue=JSON.parse(document.getElementById('processing-queue').textContent),status=document.getElementById('processing-status'),log=document.getElementById('processing-log');
 processButton.disabled=true;let successes=0;
 for(let i=0;i<queue.length;i++){
  const item=queue[i];status.textContent=`Processing ${i+1} of ${queue.length}: ${item.name}`;
  const line=document.createElement('li');log.append(line);
  try{const res=await fetch(item.url,{method:'POST',headers:{'X-CSRFToken':window.verityCSRF()},signal:AbortSignal.timeout(80000)});const data=await res.json();if(!res.ok)throw new Error(data.error||'Processing failed');line.textContent=`${data.name}: ${Math.round(data.score)}/100 · complete`;successes++;}
  catch(error){line.textContent=`${item.name}: ${error.message}`;}
 }
 status.textContent=`${successes} of ${queue.length} completed. Reload to view updated ranking.`;processButton.textContent='Refresh ranking';processButton.disabled=false;processButton.onclick=()=>location.reload();
},{once:true});
