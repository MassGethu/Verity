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

const cloudUploadForm=document.getElementById('cloud-upload-form');
if(cloudUploadForm)cloudUploadForm.addEventListener('submit',async event=>{
 event.preventDefault();
 const files=[...cloudUploadForm.querySelector('[name=resumes]').files],status=document.getElementById('cloud-upload-status'),button=cloudUploadForm.querySelector('button');
 if(!files.length||files.length>10||files.some(file=>!file.name.toLowerCase().endsWith('.pdf')||file.size>5*1024*1024||!file.size)){status.textContent='Select 1–10 PDFs, at most 5 MB each.';return;}
 const post=async(url,data)=>{const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':window.verityCSRF(),'X-Requested-With':'XMLHttpRequest'},body:JSON.stringify(data),signal:AbortSignal.timeout(80000)});const result=await response.json();if(!response.ok)throw Error(result.error||'Upload request failed');return result;};
 button.disabled=true;let successes=0;
 try{
  status.textContent='Authorising private uploads…';
  const prepared=await post(cloudUploadForm.dataset.prepareUrl,{files:files.map(file=>({name:file.name,size:file.size}))});
  const errors=[];
  for(let i=0;i<files.length;i++){
   status.textContent=`Uploading ${i+1} of ${files.length}: ${files[i].name}`;
   try{
    const response=await fetch(prepared.uploads[i].url,{method:'PUT',headers:{'Content-Type':'application/pdf','x-upsert':'false'},body:files[i],signal:AbortSignal.timeout(80000)});
    if(!response.ok)throw Error('Private storage upload failed.');
    await post(cloudUploadForm.dataset.completeUrl,{ticket:prepared.uploads[i].ticket});successes++;
   }catch(error){errors.push(`${files[i].name}: ${error.message}`);}
  }
  if(!errors.length){location.reload();return;}
  status.textContent=`${successes} uploaded and queued. ${errors.join(' ')} Reload to process accepted files.`;
 }catch(error){status.textContent=error.message;}
 finally{button.disabled=false;}
});
