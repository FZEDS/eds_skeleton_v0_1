// app/static/js/common/eds_steps.js
// Factorised step orchestration: navigation, completion, sanitisation, overrides.
// Safe-by-default: does not auto-initialise; consume via window.EDS_STEPS.init(opts).
(function(){
  'use strict';
  if (window.EDS_STEPS) return;

  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>Array.from(document.querySelectorAll(s));

  const DEFAULTS = {
    stepSelector: '.step',
    summarySelector: '#steps',
    progressSelector: '#progress',
    nextSelector: '[data-next]',
    prevSelector: '[data-prev]',
    requiredAttr: 'data-required',
  };

  const state = {
    opts: Object.assign({}, DEFAULTS),
    steps: [],
    index: 0,
    checkers: new Map(),  // idx -> fn(stepEl) -> boolean
    requiredPicker: null, // fn(stepEl) -> [elements]
    errorPredicate: null, // fn(stepEl) -> boolean
  };

  // Globals shared with other modules
  window.EDS_OVERRIDES_STEPS = window.EDS_OVERRIDES_STEPS || new Set();
  window.EDS_NON_COMPLIANCES = window.EDS_NON_COMPLIANCES || new Map();

  function coerceInt(x){
    try{ const n = parseInt(String(x),10); return Number.isNaN(n) ? null : n; }catch(_){ return null; }
  }

  function stepEl(idx){ return state.steps[idx] || null; }

  function setNextDisabled(stepIdx, disabled){
    const s = stepEl(stepIdx);
    if (!s) return;
    const btn = s.querySelector(state.opts.nextSelector);
    if (btn){ btn.disabled = !!disabled; btn.classList.toggle('disabled', !!disabled); }
  }

  function defaultRequiredPicker(stepIdx){
    const s = stepEl(stepIdx);
    if (!s) return [];
    // Ignorer les champs requis qui sont masqués (display:none) dans le step
    return Array.from(s.querySelectorAll(`[${state.opts.requiredAttr}="true"]`)).filter(el => {
      try{ return !!(el.offsetParent !== null && getComputedStyle(el).display !== 'none'); }catch(_){ return true; }
    });
  }

  function defaultErrorPredicate(stepIdx){
    const s = stepEl(stepIdx);
    if (!s) return false;
    const errs = Array.from(s.querySelectorAll('.error-msg'));
    return errs.some(e => getComputedStyle(e).display !== 'none');
  }

  function hasVisibleError(stepIdx){
    const pred = state.errorPredicate || defaultErrorPredicate;
    return !!pred(stepIdx);
  }

  function sanitizeStepInputs(stepIdx){
    const s = stepEl(stepIdx); if (!s) return;
    try{
      if (stepIdx === 0){
        const siren = s.querySelector('input[name="siren_number"]');
        if (siren && siren.value){ siren.value = siren.value.replace(/\D+/g,'').slice(0,9); }
        const cp = s.querySelector('input[name="employer_postal_code"]');
        if (cp && cp.value){ cp.value = cp.value.replace(/\D+/g,'').slice(0,5); }
        const last = s.querySelector('input[name="rep_last_name"]')?.value?.trim() || '';
        const first= s.querySelector('input[name="rep_first_name"]')?.value?.trim() || '';
        const hidden = $('#rep_name_hidden'); if (hidden) hidden.value = [first,last].filter(Boolean).join(' ');
      }
      if (stepIdx === 1){
        const last = s.querySelector('input[name="employee_last_name"]')?.value?.trim() || '';
        const first= s.querySelector('input[name="employee_first_name"]')?.value?.trim() || '';
        const hidden = $('#employee_name_hidden'); if (hidden) hidden.value = [first,last].filter(Boolean).join(' ');
        const ssn = s.querySelector('input[name="ssn"]');
        if (ssn && ssn.value){ ssn.value = ssn.value.replace(/[^\d ]+/g,'').trim(); }
      }
    }catch(_){ /* no-op */ }
  }

  function requiredFields(stepIdx){
    const picker = state.requiredPicker || defaultRequiredPicker;
    const reqs = picker(stepIdx) || [];
    // Filtre params de clause si clause non cochée
    return reqs.filter(el => {
      const paramsBlock = el.closest('.clause-params');
      if (paramsBlock){
        const item = el.closest('.clause-item');
        const cb = item && item.querySelector('input[type="checkbox"][data-key]');
        if (cb && !cb.checked) return false;
      }
      return true;
    });
  }

  function allRequiredFilled(stepIdx){
    const s = stepEl(stepIdx); if (!s) return false;
    const reqs = requiredFields(stepIdx);
    return reqs.every(el=>{
      if(el.type === 'radio'){
        const group = s.querySelectorAll(`input[name="${el.name}"]`);
        return Array.from(group).some(r=>r.checked);
      }
      if(el.type === 'checkbox') return el.checked;
      if(el.checkValidity) return !!el.value?.trim() && el.checkValidity();
      return !!el.value?.trim();
    });
  }

  function computeStepCompletion(){
    const done = new Array(state.steps.length).fill(false);
    // Appel checker spécifique si fourni, sinon défaut "required + !errors"
    state.steps.forEach((node, idx)=>{
      const checker = state.checkers.get(idx);
      let ok = false;
      if (typeof checker === 'function'){
        try { ok = !!checker(node, idx); } catch(_){ ok = false; }
      } else {
        ok = allRequiredFilled(idx) && !hasVisibleError(idx);
      }
      const stepNum = coerceInt(node.getAttribute('data-step')) || (idx+1);
      if (window.EDS_OVERRIDES_STEPS && window.EDS_OVERRIDES_STEPS.has(stepNum)) ok = true;
      done[idx] = ok;
    });
    return done;
  }

  function updateProgressUI(){
    const total = state.steps.length || 1;
    const doneFlags = computeStepCompletion();
    const doneCount = doneFlags.filter(Boolean).length;
    const bar = $(state.opts.progressSelector);
    if (bar) bar.style.width = Math.round((doneCount/total)*100) + '%';

    const items = $$(state.opts.summarySelector + ' li');
    const firstIncomplete = doneFlags.indexOf(false);
    items.forEach((li, idx)=>{
      li.classList.toggle('current', idx===state.index);
      li.classList.toggle('done', doneFlags[idx]);
      const blocked = (firstIncomplete !== -1 && idx > firstIncomplete);
      li.classList.toggle('blocked', blocked && !doneFlags[idx]);
      li.classList.toggle('incomplete', idx === firstIncomplete);
      if (idx === firstIncomplete) li.setAttribute('title','À compléter'); else li.removeAttribute('title');
      li.setAttribute('aria-current', idx===state.index ? 'step' : 'false');
    });
  }

  function tryGoto(idx){
    if (idx<0 || idx>=state.steps.length) return;
    state.index = idx;
    state.steps.forEach((s, i)=>{
      const on = (i === state.index);
      s.setAttribute('aria-hidden', on ? 'false' : 'true');
      s.style.display = on ? '' : 'none';
    });
    updateProgressUI();
  }

  function bindNavigation(){
    // Summary clicks
    $$(state.opts.summarySelector + ' li').forEach(li=>{
      li.addEventListener('click', ()=>{
        const n = coerceInt(li.getAttribute('data-step'));
        if (n && n>=1 && n<=state.steps.length) tryGoto(n-1);
      });
    });
    // Next/Prev
    $$(state.opts.nextSelector).forEach(btn=>{
      btn.addEventListener('click', (e)=>{
        e.preventDefault();
        sanitizeStepInputs(state.index);
        // Optionally gate by completion of current
        if (state.index < state.steps.length-1) tryGoto(state.index+1);
      });
    });
    $$(state.opts.prevSelector).forEach(btn=>{
      btn.addEventListener('click', (e)=>{
        e.preventDefault();
        if (state.index>0) tryGoto(state.index-1);
      });
    });
  }

  function bindOverrideHandlers(){
    document.addEventListener('click', (e)=>{
      const btn = e.target;
      if (!btn || !btn.id) return;
      // Generic: *_override marks current step as override and enables Next
      if (btn.id.endsWith('_override')){
        const stepNode = btn.closest(state.opts.stepSelector);
        if (!stepNode) return;
        const stepNum = coerceInt(stepNode.getAttribute('data-step')) || (state.index+1);
        btn.classList.add('is-on');
        btn.setAttribute('aria-pressed','true');
        stepNode.dataset.override = 'on';
        window.EDS_OVERRIDES_STEPS.add(stepNum);
        setNextDisabled(state.index, false);
        updateProgressUI();
      }
      if (btn.id.endsWith('_fix')){
        const stepNode = btn.closest(state.opts.stepSelector);
        if (!stepNode) return;
        const stepNum = coerceInt(stepNode.getAttribute('data-step')) || (state.index+1);
        delete stepNode.dataset.override;
        window.EDS_OVERRIDES_STEPS.delete(stepNum);
        updateProgressUI();
      }
    });
  }

  const API = {
    init(opts){
      state.opts = Object.assign({}, DEFAULTS, (opts||{}));
      state.steps = $$(state.opts.stepSelector);
      state.index = 0;
      bindNavigation();
      bindOverrideHandlers();
      tryGoto(0);
    },
    setChecker(idx, fn){ state.checkers.set(idx, fn); },
    setRequiredPicker(fn){ state.requiredPicker = fn; },
    setErrorPredicate(fn){ state.errorPredicate = fn; },
    updateProgress: updateProgressUI,
    sanitizeStepInputs,
    next(){ if (state.index < state.steps.length-1) tryGoto(state.index+1); },
    prev(){ if (state.index>0) tryGoto(state.index-1); },
    goto(n){ tryGoto(n); },
    get index(){ return state.index; },
    get total(){ return state.steps.length; },
  };

  window.EDS_STEPS = API;
})();
