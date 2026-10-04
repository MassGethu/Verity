'use strict';
window.verityCSRF=()=>document.querySelector('[name=csrfmiddlewaretoken]')?.value || document.cookie.split('; ').find(x=>x.startsWith('csrftoken='))?.split('=')[1] || '';
document.querySelectorAll('form[data-busy]').forEach(form=>form.addEventListener('submit',()=>{const button=form.querySelector('button[type=submit],button:not([type])');if(button){button.textContent='Working…';button.setAttribute('aria-busy','true');}form.querySelectorAll('button').forEach(b=>setTimeout(()=>b.disabled=true,0));}));

const configurationNotice=document.querySelector('[data-config-notice]');
if(configurationNotice){
  try{if(sessionStorage.getItem('verity-config-notice-dismissed'))configurationNotice.hidden=true;}catch(_){}
  configurationNotice.querySelector('[data-dismiss-notice]').addEventListener('click',()=>{
    configurationNotice.hidden=true;
    try{sessionStorage.setItem('verity-config-notice-dismissed','1');}catch(_){}
  });
}
