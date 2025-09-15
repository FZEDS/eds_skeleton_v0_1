// app/static/js/common/eds_pending.js
(function(){
  'use strict';

  if (window._EDS_PENDING_ATTACHED) return; window._EDS_PENDING_ATTACHED = true;

  // Petit store global (clé → valeur) pour le contexte manquant
  window.EDS_CTX = window.EDS_CTX || {};

  const $ = (s)=>document.querySelector(s);
  const on = (el, ev, fn)=> el && el.addEventListener(ev, fn, false);

  function escapeHtml(str){
    return String(str||'').replace(/[&<>"']/g, m => (
      {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]
    ));
  }

  function asId(s){ return 'ask_'+ String(s||'').replace(/[^a-z0-9_\-]/gi,'_'); }

  function buildControl(q){
    const id = asId(q.id || (q.writes && q.writes[0]) || 'q');
    const name = (Array.isArray(q.writes) && q.writes.length) ? q.writes[0] : (q.id || id);
    const label = q.label || name;
    const type = String(q.type || 'text').toLowerCase();
    const required = !!q.required;
    const placeholder = q.placeholder || '';
    const help = q.help || '';
    const reqAttr = required ? ' required' : '';

    let html = '';
    if (type === 'enum'){
      const opts = Array.isArray(q.options) ? q.options : [];
      const optionsHtml = ['<option value="">-- Choisir --</option>']
        .concat(opts.map(o=>`<option value="${escapeHtml(o.value)}">${escapeHtml(o.label||o.value)}</option>`))
        .join('');
      html = `
        <label for="${id}">${escapeHtml(label)}</label>
        <select id="${id}" name="${escapeHtml(name)}"${reqAttr}>${optionsHtml}</select>
        ${help ? `<div class="text-small text-muted">${escapeHtml(help)}</div>`:''}`;
    } else if (type === 'boolean'){
      html = `
        <div class="line-check-right">
          <label for="${id}">${escapeHtml(label)}</label>
          <input id="${id}" name="${escapeHtml(name)}" type="checkbox"${reqAttr}>
        </div>
        ${help ? `<div class="text-small text-muted">${escapeHtml(help)}</div>`:''}`;
    } else if (type === 'number'){
      const min = (q.min!=null) ? ` min="${q.min}"` : '';
      const max = (q.max!=null) ? ` max="${q.max}"` : '';
      const step = (q.step!=null) ? ` step="${q.step}"` : '';
      html = `
        <label for="${id}">${escapeHtml(label)}</label>
        <input id="${id}" name="${escapeHtml(name)}" type="number"${min}${max}${step} placeholder="${escapeHtml(placeholder)}"${reqAttr}>
        ${help ? `<div class="text-small text-muted">${escapeHtml(help)}</div>`:''}`;
    } else if (type === 'date'){
      html = `
        <label for="${id}">${escapeHtml(label)}</label>
        <input id="${id}" name="${escapeHtml(name)}" type="date"${reqAttr}>
        ${help ? `<div class="text-small text-muted">${escapeHtml(help)}</div>`:''}`;
    } else {
      // text, textarea, search… → input text par défaut
      html = `
        <label for="${id}">${escapeHtml(label)}</label>
        <input id="${id}" name="${escapeHtml(name)}" type="text" placeholder="${escapeHtml(placeholder)}"${reqAttr}>
        ${help ? `<div class="text-small text-muted">${escapeHtml(help)}</div>`:''}`;
    }
    // raison (brève)
    const reason = q.reason ? `<div class="text-small text-muted" style="margin-top:4px">${escapeHtml(String(q.reason))}</div>` : '';
    return `<div class="stack">${html}${reason}</div>`;
  }

  function getValueFor(el){
    if (!el) return null;
    if (el.type === 'checkbox') return !!el.checked;
    const v = el.value;
    if (el.type === 'number'){
      const n = parseFloat(String(v).replace(',','.'));
      return Number.isNaN(n) ? null : n;
    }
    return (v===''?null:v);
  }

  function applyAnswerToUI(key, val){
    try{
      if (key === 'work_time_mode'){
        // Mappe sur les radios existantes + régime
        if (val === 'standard'){
          const a = document.getElementById('wt_35'); const r = document.getElementById('reg_full');
          if (a){ a.checked = true; a.dispatchEvent(new Event('change', {bubbles:true})); }
          if (r){ r.checked = true; r.dispatchEvent(new Event('change', {bubbles:true})); }
        } else if (val === 'part_time'){
          const a = document.getElementById('wt_35'); const r = document.getElementById('reg_part');
          if (a){ a.checked = true; a.dispatchEvent(new Event('change', {bubbles:true})); }
          if (r){ r.checked = true; r.dispatchEvent(new Event('change', {bubbles:true})); }
        } else if (val === 'forfait_hours'){
          const a = document.getElementById('wt_fh_pay'); if (a){ a.checked = true; a.dispatchEvent(new Event('change', {bubbles:true})); }
        } else if (val === 'forfait_days'){
          const a = document.getElementById('wt_fd'); if (a){ a.checked = true; a.dispatchEvent(new Event('change', {bubbles:true})); }
        }
        return;
      }
      if (key === 'anciennete_months'){
        // Répartit en années/mois si possible et pousse dans les champs globaux
        const m = parseInt(String(val||'0'), 10) || 0;
        const y = Math.floor(m / 12);
        const r = m % 12;
        const yr = document.getElementById('seniority_years');
        const mo = document.getElementById('seniority_months');
        if (yr){ yr.value = String(y); yr.dispatchEvent(new Event('input', {bubbles:true})); }
        if (mo){ mo.value = String(r); mo.dispatchEvent(new Event('input', {bubbles:true})); }
        return;
      }
      if (key === 'classification_level'){
        const el = document.getElementById('classification_level');
        if (el){ el.value = String(val||''); el.dispatchEvent(new Event('input', {bubbles:true})); }
        return;
      }
      // Par défaut: stocker dans le contexte global (pour les appels /api/resolve)
      window.EDS_CTX[key] = val;
    }catch(_){/* no-op */}
  }

  async function handlePendingInputs(pending){
    try{
      const modal = document.getElementById('askOnDemandModal');
      const form  = document.getElementById('askOnDemandForm');
      const box   = document.getElementById('askQuestionsContainer');
      if (!modal || !form || !box) return;

      box.innerHTML = '';
      const list = Array.isArray(pending) ? pending : [];
      list.forEach(q => { box.insertAdjacentHTML('beforeend', buildControl(q)); });

      // Ouvre la modale
      modal.classList.add('show');
      modal.style.display = 'block';
      modal.setAttribute('aria-hidden', 'false');
      try{ document.body.classList.add('modal-open'); }catch(_){ }

      const submitBtn = document.getElementById('askSubmitBtn');
      const submit = async ()=>{
        // Validation simple + collecte
        const inputs = Array.from(form.querySelectorAll('input, select, textarea'));
        const answers = [];
        let hasError = false;
        inputs.forEach(el => {
          const name = el.getAttribute('name');
          if (!name) return;
          const required = el.hasAttribute('required');
          const val = getValueFor(el);
          if (required && (val===null || val==='')){
            el.classList.add('input-error');
            hasError = true;
            return;
          } else {
            el.classList.remove('input-error');
          }
          answers.push({ key: name, value: val });
        });
        if (hasError) return;

        // Applique au contexte/UI
        answers.forEach(a => applyAnswerToUI(a.key, a.value));

        // Ferme la modale
        modal.classList.remove('show');
        modal.style.display = 'none';
        modal.setAttribute('aria-hidden', 'true');
        try{ document.body.classList.remove('modal-open'); }catch(_){ }

        // Notifie et relance les calculs
        document.dispatchEvent(new CustomEvent('eds:ctx_updated'));
      };

      on(submitBtn, 'click', ()=>{
        try{ if (typeof form.reportValidity === 'function' && !form.reportValidity()) return; }catch(_){ }
        submit();
      });
    }catch(e){ if (window.EDS_DEBUG) console.warn('handlePendingInputs failed', e); }
  }

  // Expose global
  window.handlePendingInputs = handlePendingInputs;
})();
