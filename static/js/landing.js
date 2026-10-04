/* Verity landing demonstrations only. No network calls or recruitment mutations. */
'use strict';
(() => {
  const motion = window.Motion;
  const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
  const animations = new Set();
  const cleanups = [];
  const demos = [];
  const canAnimate = () => !!motion && !preference.matches;
  const animate = (target, keyframes, options = {}) => {
    if (!canAnimate()) return null;
    const control = motion.animate(target, keyframes, options);
    animations.add(control);
    Promise.resolve(control).then(() => animations.delete(control));
    return control;
  };

  // The unenhanced navigation stays visible, including when JavaScript is absent.
  const header = document.querySelector('.site-header');
  const menu = document.querySelector('.menu-toggle');
  const navigation = document.querySelector('#site-navigation');
  const compact = window.matchMedia('(max-width: 800px)');
  const setMenu = (open, restoreFocus = false) => {
    header.classList.toggle('menu-open', open);
    menu.setAttribute('aria-expanded', String(open));
    if (restoreFocus) menu.focus();
  };
  const syncMenu = () => {
    menu.hidden = !compact.matches;
    setMenu(false);
  };
  header.classList.add('menu-enhanced');
  menu.addEventListener('click', () => setMenu(menu.getAttribute('aria-expanded') !== 'true'));
  navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', () => setMenu(false, compact.matches)));
  header.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') setMenu(false, true);
  });
  compact.addEventListener('change', syncMenu);
  syncMenu();

  const ranking = document.querySelector('[data-ranking]');
  const sortButtons = document.querySelectorAll('[data-sort]');
  const rankingAnimations = new Map();
  sortButtons.forEach(button => button.addEventListener('click', () => {
    if (button.getAttribute('aria-pressed') === 'true') return;
    rankingAnimations.forEach(control => control?.stop());
    rankingAnimations.clear();
    const candidates = Array.from(ranking.children);
    // Clear previous transforms before measuring to make rapid toggles deterministic.
    candidates.forEach(candidate => { candidate.style.transform = ''; });
    const before = new Map(candidates.map(candidate => [candidate.dataset.candidate, candidate.getBoundingClientRect().top]));
    const evidenceOrder = button.dataset.sort === 'evidence';
    candidates.sort((a, b) => evidenceOrder
      ? Number(b.dataset.strength) - Number(a.dataset.strength) || Number(b.dataset.fit) - Number(a.dataset.fit)
      : Number(b.dataset.fit) - Number(a.dataset.fit));
    candidates.forEach((candidate, index) => {
      ranking.append(candidate);
      candidate.querySelector('.rank-number').textContent = index + 1;
    });
    sortButtons.forEach(control => control.setAttribute('aria-pressed', String(control === button)));
    if (canAnimate()) candidates.forEach(candidate => {
      const delta = before.get(candidate.dataset.candidate) - candidate.getBoundingClientRect().top;
      if (delta) rankingAnimations.set(candidate.dataset.candidate, animate(candidate, { y: [delta, 0] }, { type: motion.spring, stiffness: 260, damping: 28 }));
    });
    document.querySelector('[data-ranking-status]').textContent = evidenceOrder
      ? 'Ordered by illustrative evidence strength; scores are unchanged.'
      : 'Ordered by illustrative rubric fit.';
  }));

  // Each playback has a bounded lifetime. Leaving the viewport resolves to its
  // complete state so no hidden timer runs or partial content remains stranded.
  document.querySelectorAll('[data-demo]').forEach(element => {
    const replay = element.querySelector('[data-replay]');
    const interview = element.dataset.demo === 'interview';
    const answer = element.querySelector('[data-sample-answer]');
    const original = answer?.textContent;
    const result = element.querySelector('[data-demo-result]');
    const timer = element.querySelector('[data-demo-timer]');
    const state = element.querySelector(interview ? '[data-demo-state]' : '[data-feedback-state]');
    const sentence = element.querySelector('[data-edited-sentence]');
    const edited = sentence?.textContent;
    const gmail = element.querySelector('[data-gmail-preview]');
    let handles = [], controls = [], played = false;
    const clear = () => {
      handles.forEach(id => { clearTimeout(id); clearInterval(id); });
      handles = [];
      controls.forEach(control => control?.stop());
      controls = [];
    };
    const completed = () => {
      clear();
      if (interview) {
        answer.textContent = original;
        timer.textContent = '01:42';
        result.style.opacity = '';
        result.style.visibility = '';
        result.style.transform = '';
        result.inert = false;
        state.textContent = 'Example answer submitted · advisory review complete';
      } else {
        sentence.textContent = edited;
        sentence.style.opacity = '';
        gmail.style.opacity = '';
        element.querySelectorAll('.email-preview p').forEach(p => { p.style.opacity = ''; p.style.transform = ''; });
        state.textContent = 'Recruiter edit saved';
      }
      replay.disabled = false;
    };
    const later = (fn, ms) => handles.push(setTimeout(fn, ms));
    const play = () => {
      completed();
      played = true;
      if (!canAnimate()) return;
      replay.disabled = true;
      if (interview) {
        answer.textContent = '';
        result.style.visibility = 'hidden';
        result.inert = true;
        state.textContent = 'Entering an example answer…';
        const started = performance.now();
        handles.push(setInterval(() => {
          const elapsed = performance.now() - started;
          answer.textContent = original.slice(0, Math.min(original.length, Math.floor(elapsed / 12)));
          const seconds = 102 - Math.min(7, Math.floor(elapsed / 1000));
          timer.textContent = `01:${String(seconds - 60).padStart(2, '0')}`;
        }, 40));
        later(() => { answer.textContent = original; state.textContent = 'Example answer submitted'; }, 3500);
        later(() => { state.textContent = 'Reviewing the example answer…'; }, 4100);
        later(() => {
          result.style.visibility = '';
          result.inert = false;
          controls.push(animate(result, { opacity: [0, 1], y: [8, 0] }, { duration: .45 }));
          state.textContent = 'Advisory review complete · original answer preserved';
        }, 5500);
        later(completed, 7500);
      } else {
        state.textContent = 'AI draft prepared · recruiter reviewing';
        sentence.textContent = 'Consider adding more detail to your deployment experience.';
        gmail.style.opacity = '0';
        controls.push(animate(element.querySelectorAll('.email-preview p'), { opacity: [0, 1], y: [4, 0] }, { duration: .35, delay: motion.stagger(.22) }));
        later(() => { state.textContent = 'Recruiter adds a concrete next step…'; sentence.textContent = edited; controls.push(animate(sentence, { opacity: [.3, 1] }, { duration: .5 })); }, 2200);
        later(() => { state.textContent = 'Recruiter edit saved'; controls.push(animate(gmail, { opacity: [0, 1] }, { duration: .4 })); }, 3700);
        later(completed, 4500);
      }
    };
    replay.hidden = false;
    replay.addEventListener('click', play);
    demos.push({ completed });
    if (motion) cleanups.push(motion.inView(element, () => {
      if (!played) play();
      return completed;
    }, { amount: .35 }));
  });

  const resetVisuals = () => {
    animations.forEach(control => control.stop());
    animations.clear();
    document.querySelectorAll('.hero-enter, .reveal, .reveal-group > *, .chain-card').forEach(element => {
      element.style.opacity = ''; element.style.transform = '';
    });
    document.querySelectorAll('.hero-card').forEach(element => { element.style.opacity = ''; element.style.translate = ''; });
    document.querySelectorAll('[data-bar]').forEach(element => { element.style.transform = ''; });
    document.querySelectorAll('[data-draw]').forEach(path => { path.style.strokeDasharray = ''; path.style.strokeDashoffset = ''; });
    document.querySelector('.workflow-track i').style.transform = '';
    const score = document.querySelector('[data-score]'); score.textContent = score.dataset.score;
    demos.forEach(demo => demo.completed());
  };
  if (canAnimate()) {
    animate('.hero-enter', { opacity: [0, 1], y: [16, 0] }, { duration: .65, delay: motion.stagger(.16), ease: [.22, 1, .36, 1] });
    animate('.hero-card', { opacity: [0, 1], translate: ['0 18px', '0 0px'] }, { duration: .8, delay: motion.stagger(.45, { startDelay: .65 }) });
    animate('[data-bar]', { scaleX: [0, 1] }, { duration: 1.1, delay: motion.stagger(.12, { startDelay: 1.1 }), ease: [.22, 1, .36, 1] });
    document.querySelectorAll('.reveal').forEach(element => {
      cleanups.push(motion.inView(element, () => {
        animate(element, { opacity: [0, 1], y: [18, 0] }, { duration: .65, ease: [.22, 1, .36, 1] });
      }, { amount: .15 }));
    });
    document.querySelectorAll('.reveal-group, [data-chain]').forEach(element => {
      cleanups.push(motion.inView(element, () => {
        animate(Array.from(element.children).filter(child => child.tagName !== 'svg'), { opacity: [0, 1], y: [12, 0] }, { duration: .55, delay: motion.stagger(.13) });
      }, { amount: .2 }));
    });
    document.querySelectorAll('[data-draw]').forEach(path => {
      cleanups.push(motion.inView(path.closest('section'), () => {
        const length = path.getTotalLength();
        path.style.strokeDasharray = String(length);
        animate(path, { strokeDashoffset: [length, 0] }, { duration: 1.3, delay: .2 });
      }, { amount: .2 }));
    });
    const workflow = document.querySelector('[data-workflow]');
    cleanups.push(motion.scroll(progress => {
      if (!canAnimate()) return;
      workflow.querySelector('.workflow-track i').style.transform = `scaleY(${progress})`;
      workflow.querySelectorAll('.workflow-step').forEach((step, index) => step.classList.toggle('is-active', progress >= index / 4));
    }, { target: workflow, offset: ['start 85%', 'end 45%'] }));
    const score = document.querySelector('[data-score]');
    cleanups.push(motion.inView(score, () => {
      animate(0, Number(score.dataset.score), { duration: 1, onUpdate: value => { score.textContent = Math.round(value); } });
      animate(document.querySelectorAll('.match-detail'), { opacity: [0, 1], y: [6, 0] }, { duration: .35, delay: motion.stagger(.08) });
    }));
    cleanups.push(motion.hover('.button, .segmented button, .replay', element => {
      if (!canAnimate()) return;
      animate(element, { y: -2 }, { duration: .18 });
      return () => animate(element, { y: 0 }, { duration: .18 });
    }));
    cleanups.push(motion.press('.button, .segmented button', element => {
      if (!canAnimate()) return;
      animate(element, { scale: .98 }, { duration: .12 });
      return () => animate(element, { scale: 1 }, { duration: .12 });
    }));
  }
  preference.addEventListener('change', () => {
    if (preference.matches) {
      cleanups.splice(0).forEach(cleanup => cleanup?.());
      resetVisuals();
      document.querySelectorAll('.button, .segmented button, .replay, .ranking-list li, .match-detail, [data-demo-result]').forEach(element => { element.style.transform = ''; element.style.opacity = ''; });
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) demos.forEach(demo => demo.completed());
  });
  window.addEventListener('pagehide', () => {
    cleanups.splice(0).forEach(cleanup => cleanup?.());
    resetVisuals();
  });
})();
