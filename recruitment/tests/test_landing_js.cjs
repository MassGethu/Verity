/* Exercise fallback, playback cleanup and live motion preferences without a
   browser dependency. Visual Motion behavior is checked in the real browser. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('static/js/landing.js', 'utf8');

function fixture({motionAvailable = false, reduced = false} = {}) {
  let focused, now = 0, nextId = 0;
  const pending = new Map(), views = new Map();
  class Element {
    constructor(text = '', dataset = {}) {
      this.textContent = text; this.dataset = dataset; this.style = {};
      this.attributes = {}; this.events = {}; this.children = []; this.selectors = {};
      this.hidden = false; this.disabled = false;
      const classes = new Set();
      this.classList = {add: value => classes.add(value), toggle: (value, enabled) => enabled ? classes.add(value) : classes.delete(value)};
    }
    querySelector(selector) { return this.selectors[selector] || null; }
    querySelectorAll(selector) { const result = this.selectors[selector]; return Array.isArray(result) ? result : result ? [result] : []; }
    addEventListener(name, fn) { this.events[name] = fn; }
    setAttribute(name, value) { this.attributes[name] = value; }
    getAttribute(name) { return this.attributes[name] ?? null; }
    focus() { focused = this; }
    append(child) { this.children = this.children.filter(item => item !== child); this.children.push(child); child.parent = this; }
    getBoundingClientRect() { return {top: (this.parent?.children.indexOf(this) || 0) * 100}; }
  }
  const preference = {matches: reduced, addEventListener: (_, fn) => preference.change = fn};
  const compact = {matches: true, addEventListener: (_, fn) => compact.change = fn};
  const header = new Element(), menu = new Element(), nav = new Element(), link = new Element();
  nav.selectors.a = [link];
  const ranking = new Element();
  for (const [id, fit, strength] of [['priya',91,3], ['arjun',87,2], ['rahul',84,3]]) {
    const element = new Element('', {candidate:id,fit:String(fit),strength:String(strength)});
    element.selectors['.rank-number'] = new Element(); ranking.append(element);
  }
  const fit = new Element('Rubric fit', {sort:'fit'}), evidence = new Element('Evidence', {sort:'evidence'});
  fit.setAttribute('aria-pressed', 'true'); evidence.setAttribute('aria-pressed', 'false');
  const guide = new Element('', {demo:'guide'}), feedback = new Element('', {demo:'feedback'});
  const followUp = new Element('Follow-up: How did you test access restrictions?');
  const steps = [new Element(),new Element(),new Element()];
  const guideState = new Element(), guideReplay = new Element();
  Object.assign(guide.selectors, {'[data-replay]':guideReplay,'.guide-preview-step':steps,'[data-guide-follow-up]':followUp,'[data-guide-demo-state]':guideState});
  const sentence = new Element('Document a deployed project, including your Docker setup.'), gmail = new Element(), feedbackState = new Element(), feedbackReplay = new Element();
  Object.assign(feedback.selectors, {'[data-replay]':feedbackReplay,'[data-edited-sentence]':sentence,'[data-gmail-preview]':gmail,'[data-feedback-state]':feedbackState,'.email-preview p':[sentence]});
  const workflow = new Element(), track = new Element(), score = new Element('86',{score:'86'});
  workflow.selectors['.workflow-track i'] = track;
  const doc = new Element();
  Object.assign(doc.selectors, {'.site-header':header,'.menu-toggle':menu,'#site-navigation':nav,'[data-ranking]':ranking,'[data-sort]':[fit,evidence],'[data-ranking-status]':new Element(),'[data-demo]':[guide,feedback],'[data-workflow]':workflow,'.workflow-track i':track,'[data-score]':score});
  const schedule = (fn, delay, interval = false) => { const id = ++nextId; pending.set(id,{fn,at:now+delay,delay,interval}); return id; };
  const advance = ms => {
    const end = now + ms;
    while (true) {
      const entry = [...pending].sort((a,b)=>a[1].at-b[1].at)[0];
      if (!entry || entry[1].at > end) break;
      const [id, task] = entry; now = task.at;
      if (task.interval) task.at += task.delay; else pending.delete(id);
      task.fn();
    }
    now = end;
  };
  let cancelled = 0;
  const motion = {
    animate: () => ({stop: () => cancelled++}),
    inView: (element, enter) => { views.set(element, enter); return () => {}; },
    scroll: () => () => {}, hover: () => () => {}, press: () => () => {}, stagger: () => 0, spring: () => {},
  };
  const window = {Motion:motionAvailable ? motion : undefined,matchMedia:query => query.includes('reduced-motion') ? preference : compact,addEventListener:()=>{}};
  vm.runInNewContext(source, {window,document:doc,performance:{now:()=>now},setTimeout:(fn,ms)=>schedule(fn,ms),setInterval:(fn,ms)=>schedule(fn,ms,true),clearTimeout:id=>pending.delete(id),clearInterval:id=>pending.delete(id),Promise,fetch:()=>{throw Error('Landing must not make requests');}});
  return {menu,header,nav,link,ranking,fit,evidence,guide,guideState,guideReplay,followUp,steps,feedback,feedbackReplay,feedbackState,sentence,gmail,preference,pending,views,advance,focus:()=>focused,cancelled:()=>cancelled};
}

for (const settings of [{}, {motionAvailable:true,reduced:true}]) {
  const f = fixture(settings);
  f.evidence.events.click();
  assert.deepEqual(f.ranking.children.map(e=>e.dataset.candidate), ['priya','rahul','arjun']);
  assert.deepEqual(f.ranking.children.map(e=>e.dataset.fit), ['91','84','87']);
  assert.equal(f.evidence.getAttribute('aria-pressed'), 'true');
  f.guideReplay.events.click(); f.feedbackReplay.events.click();
  assert.equal(f.pending.size, 0, 'Fallback and reduced motion cannot start timers');
  assert.match(f.guideState.textContent, /Guide prepared/);
  assert.match(f.feedbackState.textContent, /saved/);
  f.menu.events.click(); assert.equal(f.menu.getAttribute('aria-expanded'), 'true');
  f.header.events.keydown({key:'Escape'}); assert.equal(f.menu.getAttribute('aria-expanded'), 'false'); assert.equal(f.focus(), f.menu);
}
{
  const f = fixture({motionAvailable:true});
  const original = f.followUp.textContent;
  const leave = f.views.get(f.guide)();
  f.advance(1200);
  assert.notEqual(f.followUp.textContent, original);
  assert.match(f.guideState.textContent, /Shortlisted/);
  leave();
  assert.equal(f.pending.size, 0); assert.equal(f.followUp.textContent, original);
  f.guideReplay.events.click(); f.advance(4200);
  assert.equal(f.pending.size, 0); assert.equal(f.guideReplay.disabled, false);
  f.feedbackReplay.events.click(); f.advance(2300); assert.match(f.sentence.textContent, /Docker/);
  f.preference.matches = true; f.preference.change();
  assert.equal(f.pending.size, 0, 'Changing reduced motion clears active playbacks');
  assert.equal(f.gmail.style.opacity, ''); assert.equal(f.feedbackReplay.disabled, false); assert.ok(f.cancelled() > 0);
  f.guideReplay.events.click(); assert.equal(f.pending.size, 0);
}
console.log('Landing fallback, ranking, menu, bounded playback, viewport exit and reduced-motion change: passed');
