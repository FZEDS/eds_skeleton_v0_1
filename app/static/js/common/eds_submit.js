// app/static/js/common/eds_submit.js
// Build FormData and POST to /cdi/generate or /cdd/generate; preview and confirm helpers.
(function(){
  'use strict';
  if (window.EDS_SUBMIT) return;

  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>Array.from(document.querySelectorAll(s));

  const defaults = {
    containerSelector: 'body',
    previewBtnSelector: '#btn-preview',
    submitBtnSelector:  '#btn-submit',
    confirmOverlaySelector: '#confirm-overlay',
    confirmBodySelector:    '#confirm-body',
    confirmCloseSelector:   '#close-confirm',
    confirmFixSelector:     '#confirm-fix',
    confirmSubmitSelector:  '#confirm-submit',
  };

  const st = { opts: Object.assign({}, defaults), attached: false };

  function endpoint(){ return (window.EDS_DOC === 'cdd') ? '/cdd/generate' : '/cdi/generate'; }

  function buildFormData(){
    const root = document.querySelector(st.opts.containerSelector) || document.body;
    const fd = new FormData();
    const fields = root.querySelectorAll('input[name], select[name], textarea[name]');
    const ALWAYS_INCLUDE = new Set([
      'rep_name','employee_name','part_time_payload','ae_json',
      'clauses_selected_json','clauses_custom_json','clauses_params_json'
    ]);
    fields.forEach(el=>{
      if (el.disabled) return;
      const name = el.getAttribute('name');
      if (!name) return;
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute('type')||'').toLowerCase();
      if (tag === 'input' && (type === 'checkbox')){
        if (el.checked) fd.append(name, el.value || 'on');
        return;
      }
      if (tag === 'input' && type === 'radio'){
        if (el.checked) fd.append(name, el.value);
        return;
      }
      let val = el.value;
      if (type === 'number' && typeof val === 'string'){
        val = val.replace(',', '.');
      }
      const isRequired = el.required || el.dataset?.required === 'true';
      const forceInclude = (name === 'ssn') || ALWAYS_INCLUDE.has(name);
      if (!forceInclude && !isRequired && (val==='' || val==null)) return;
      fd.append(name, val ?? '');
    });

    // Dimensions de classification et contextes additionnels (EDS_CTX)
    try{
      const ctx = (window.EDS_CTX || {});
      ['annexe','segment','statut','coeff_key','trv_fulltime_mode'].forEach((k)=>{
        const v = ctx[k];
        if (v != null && String(v).trim() !== ''){
          fd.append(k, String(v));
        }
      });
    }catch(_){ /* noop */ }

    // Ancienneté (global) — si non présente, calculer depuis #seniority_years / #seniority_months
    try{
      if (!fd.has('anciennete_months')){
        const yEl = document.getElementById('seniority_years');
        const mEl = document.getElementById('seniority_months');
        if (yEl || mEl){
          const y = parseInt(yEl?.value || '0', 10) || 0;
          const m = parseInt(mEl?.value || '0', 10) || 0;
          const months = (y*12) + m;
          fd.append('anciennete_months', String(months));
        }
      }
    }catch(_){ /* noop */ }

    // Non-conformités & overrides (facultatifs)
    try{
      const map = window.EDS_NON_COMPLIANCES || new Map();
      const arr = Array.from(map.values ? map.values() : []);
      if (arr && arr.length) fd.append('non_compliance_json', JSON.stringify(arr));
    }catch(_){/* noop */}
    try{
      const set = window.EDS_OVERRIDES_STEPS || new Set();
      const arr = Array.from(set.values ? set.values() : []);
      if (arr && arr.length) fd.append('overrides_steps', JSON.stringify(arr));
    }catch(_){/* noop */}

    return fd;
  }

  async function post(fd, { preview=false } = {}){
    if (preview) fd.append('preview', '1');
    const url = endpoint();
    const r = await fetch(url, { method: 'POST', body: fd });
    if (!r.ok) throw new Error('HTTP '+r.status);
    const blob = await r.blob();
    const ct = (r.headers.get('Content-Type')||'').toLowerCase();
    if (ct.includes('application/pdf')){
      const urlObj = URL.createObjectURL(blob);
      window.open(urlObj, '_blank');
      return;
    }
    // Fallback: JSON or text
    try{ console.log(await r.json()); }catch(_){ console.log(await r.text()); }
  }

  function summarizeIssues(){
    try{
      const arr = Array.from((window.EDS_NON_COMPLIANCES||new Map()).values());
      if (!arr || !arr.length) return '<div class="muted">Aucune non‑conformité détectée.</div>';
      return '<ul>'+arr.map(it=>{
        const s = (it.step!=null)? ` (étape ${it.step})` : '';
        const m = (it.message || '').replace(/</g,'&lt;');
        return `<li>${m}${s}</li>`;
      }).join('')+'</ul>';
    }catch(_){ return '<div class="muted">—</div>'; }
  }

  function showConfirm(){
    const ov = $(st.opts.confirmOverlaySelector); if (!ov) return false;
    const body = $(st.opts.confirmBodySelector);
    if (body) body.innerHTML = summarizeIssues();
    ov.style.display = 'block';
    return true;
  }

  function hideConfirm(){ const ov = $(st.opts.confirmOverlaySelector); if (ov) ov.style.display = 'none'; }

  function bindConfirmHandlers(){
    $(st.opts.confirmCloseSelector)?.addEventListener('click', hideConfirm);
    $(st.opts.confirmFixSelector)?.addEventListener('click', ()=>{
      let targetStep = null;
      try{
        const issues = Array.from((window.EDS_NON_COMPLIANCES||new Map()).values());
        if (issues.length){ targetStep = Math.min(...issues.map(it=> parseInt(it.step||0,10)).filter(Boolean)); }
        if (!targetStep && window.EDS_OVERRIDES_STEPS && window.EDS_OVERRIDES_STEPS.size){
          targetStep = Math.min(...Array.from(window.EDS_OVERRIDES_STEPS));
        }
      }catch(_){ /* noop */ }
      if (targetStep && window.EDS_STEPS && typeof window.EDS_STEPS.goto==='function'){
        window.EDS_STEPS.goto(targetStep-1);
      }
      hideConfirm();
    });
    $(st.opts.confirmSubmitSelector)?.addEventListener('click', async ()=>{
      hideConfirm();
      try{ await post(buildFormData(), { preview:false }); }catch(e){ if(window.EDS_DEBUG) console.warn('submit failed', e); }
    });
  }

  function attach(){
    if (st.attached) return; st.attached = true;
    bindConfirmHandlers();
    $(st.opts.previewBtnSelector)?.addEventListener('click', async (e)=>{
      e.preventDefault();
      try{ await post(buildFormData(), { preview:true }); }catch(err){ if(window.EDS_DEBUG) console.warn('preview failed', err); }
    });
    $(st.opts.submitBtnSelector)?.addEventListener('click', (e)=>{
      e.preventDefault();
      // Si overlay présent, proposer une confirmation; sinon soumettre directement
      if (!showConfirm()){
        post(buildFormData(), { preview:false }).catch(err=>{ if(window.EDS_DEBUG) console.warn('submit failed', err); });
      }
    });
  }

  window.EDS_SUBMIT = {
    init(opts){ st.opts = Object.assign({}, defaults, (opts||{})); attach(); },
    buildFormData,
    preview(){ return post(buildFormData(), { preview:true }); },
    submit(){ return post(buildFormData(), { preview:false }); },
  };
})();
