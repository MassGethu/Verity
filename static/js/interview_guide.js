'use strict';
(() => {
  const element = document.getElementById('guide-state');
  if (!element) return;
  const state = JSON.parse(element.textContent);
  const panel = document.getElementById('interview-guide');
  const progress = document.getElementById('guide-progress');
  let pending = false, dirty = false;
  const post = async (url, data) => {
    const response = await fetch(url, {method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':window.verityCSRF(),'X-Requested-With':'XMLHttpRequest'},body:JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'The guide could not be saved.');
    return result;
  };
  const generate = async (replace, revision) => {
    if (pending) return;
    pending = true;
    progress.hidden = false;
    progress.textContent = 'Preparing your interview guide… Your shortlist decision is already saved.';
    const previousButtons = [...panel.querySelectorAll('button')].map(button=>[button,button.disabled]);
    previousButtons.forEach(([button]) => button.disabled = true);
    try {
      await post(state.generate_url, {replace, revision});
      // Reload fresh saved data; do not alter the recruiter's ranking/decision.
      window.location.reload();
    } catch (error) {
      progress.textContent = error.message;
      previousButtons.forEach(([button,disabled]) => button.disabled = disabled);
      pending = false;
    }
  };
  panel.querySelectorAll('[data-guide-generate]').forEach(form => form.addEventListener('submit', event => {
    event.preventDefault();
    if (dirty && !window.confirm('Regenerating will replace your unsaved changes. Continue?')) return;
    generate(!!form.querySelector('[name=replace]')?.checked, Number(form.querySelector('[name=revision]').value));
  }));
  const editForm = document.getElementById('guide-edit-form');
  const saved = document.getElementById('guide-save-status');
  const questions = () => [...panel.querySelectorAll('[data-guide-question]')].map(question => ({id:question.dataset.questionId,...Object.fromEntries([...question.querySelectorAll('[data-field]')].map(field => [field.dataset.field,field.value]))}));
  editForm?.addEventListener('input', () => { dirty = true; saved.textContent = 'Unsaved recruiter edits'; });
  editForm?.addEventListener('submit', async event => {
    event.preventDefault();
    const button = editForm.querySelector('button[type=submit]');
    button.disabled = true;
    saved.textContent = 'Saving guide edits…';
    try {
      const result = await post(state.save_url, {revision:state.revision,questions:questions()});
      state.revision = result.revision;
      panel.querySelectorAll('[name=revision]').forEach(field => field.value = state.revision);
      dirty = false;
      saved.textContent = 'Recruiter edits saved';
    } catch (error) { saved.textContent = error.message+' Your current text remains on this page.'; }
    finally { button.disabled = false; }
  });
  const copy = document.getElementById('copy-guide');
  if (copy) {
    copy.hidden = false;
    copy.addEventListener('click', async () => {
      const cards = [...panel.querySelectorAll('[data-guide-question]')];
      const text = 'Evidence-based Interview Guide\n'+(dirty ? 'Unsaved recruiter edits\n' : '')+'\n'+questions().map((question,index)=>{
        const sources = [...cards[index].querySelectorAll('blockquote')].map(block=>block.innerText).join('\n');
        return `${index+1}. ${question.question}\nWhy ask: ${question.purpose}\n${question.follow_up ? 'Follow-up: '+question.follow_up+'\n' : ''}${sources}`;
      }).join('\n\n');
      try { await navigator.clipboard.writeText(text); saved.textContent = dirty ? 'Current unsaved guide copied; save to persist edits.' : 'Guide copied'; }
      catch (_) { saved.textContent = 'Clipboard unavailable. Select the question text to copy it manually.'; }
    });
  }
  panel.querySelectorAll('[data-guide-source]').forEach(link => link.addEventListener('click', () => {
    let source = document.getElementById(link.hash.slice(1));
    while (source) { if (source.tagName === 'DETAILS') source.open = true; source = source.parentElement; }
  }));
  window.addEventListener('beforeunload', event => {
    if (dirty) { event.preventDefault(); event.returnValue = ''; }
  });
  if (state.auto_prepare) generate(false, state.revision);
})();
