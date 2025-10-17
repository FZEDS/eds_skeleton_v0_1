// app/static/js/cdi.js — initialisation spécifique au formulaire CDI
(function(){
  'use strict';
  if (window._EDS_CDI_ATTACHED) return; // idempotent
  window._EDS_CDI_ATTACHED = true;

  const $  = (s)=>document.querySelector(s);

  function escapeHtml(str){
    return String(str||'').replace(/[&<>"']/g, m => (
      {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]
    ));
  }

  function submitFormData(url, fd){
    const form = document.createElement('form');
    form.method = 'post';
    form.action = url;
    for (const [k,v] of fd.entries()){
      const inp = document.createElement('input');
      inp.type='hidden';
      inp.name=k;
      inp.value=String(v ?? '');
      form.appendChild(inp);
    }
    document.body.appendChild(form);
    form.submit();
  }

  function overridePreviewWithIframe(){
    const prevBtn = $('#btn-preview');
    if (!prevBtn) return;
    prevBtn.addEventListener('click', async (e)=>{
      // Intercepte le preview par défaut pour utiliser l'overlay + iframe
      e.preventDefault();
      e.stopImmediatePropagation();
      const ov = $('#overlay');
      const body = $('#preview-body');
      if (body) body.innerHTML = '<div class="muted">Génération de l’aperçu…</div>';
      if (ov) ov.style.display = 'block';
      try{
        const fd = (window.EDS_SUBMIT && EDS_SUBMIT.buildFormData) ? EDS_SUBMIT.buildFormData() : new FormData();
        fd.append('preview','1');
        const r = await fetch('/cdi/generate', { method:'POST', body: fd });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const ct = (r.headers.get('content-type') || '').toLowerCase();
        if (ct.includes('application/pdf')){
          const blob = await r.blob();
          const url = URL.createObjectURL(blob);
          if (body){
            body.innerHTML = '';
            const iframe = document.createElement('iframe');
            iframe.style.width='100%';
            iframe.style.height='80vh';
            iframe.setAttribute('title','Aperçu PDF');
            iframe.src = url;
            body.appendChild(iframe);
          }
        } else {
          const txt = await r.text();
          if (body) body.innerHTML = '<pre>'+escapeHtml(txt)+'</pre>';
        }
      }catch(err){ if (body) body.innerHTML = '<div class="callout callout-warn">Aperçu indisponible : '+escapeHtml(String(err))+'</div>'; }
    }, { capture: true });

    const closeOverlay = $('#close-overlay');
    if (closeOverlay){
      closeOverlay.addEventListener('click', (e)=>{
        e.preventDefault();
        const ov = $('#overlay');
        if (ov) ov.style.display='none';
      }, { capture: true });
    }
  }

  function overrideConfirmSubmit(){
    const confirmSubmit = $('#confirm-submit');
    if (!confirmSubmit) return;
    confirmSubmit.addEventListener('click', (e)=>{
      // Soumission en POST réel (comme la version inline CDI)
      e.preventDefault();
      e.stopImmediatePropagation();
      try{
        const fd = (window.EDS_SUBMIT && EDS_SUBMIT.buildFormData) ? EDS_SUBMIT.buildFormData() : new FormData();
        const ov = $('#confirm-overlay');
        if (ov) ov.style.display='none';
        submitFormData('/cdi/generate', fd);
      }catch(err){ if (window.EDS_DEBUG) console.warn('CDI confirm-submit failed', err); }
    }, { capture: true });
  }

  function attach(){
    // 1) Orchestrateur d’étapes (commun)
    try{ if (window.EDS_STEPS) EDS_STEPS.init(); }catch(_){ /* noop */ }

    // 2) Clauses (commun)
    try{ if (window.EDS_CLAUSES){ EDS_CLAUSES.init(); EDS_CLAUSES.refresh(); } }catch(_){ /* noop */ }

    // 3) Soumission (commun) — garde l’overlay/iframe pour le preview via override
    try{ if (window.EDS_SUBMIT) EDS_SUBMIT.init(); }catch(_){ /* noop */ }
    overridePreviewWithIframe();
    overrideConfirmSubmit();

    // 4) Classification & Temps de travail (communs)
    try{ if (window.EDS_CLASSIF && EDS_CLASSIF.refresh) EDS_CLASSIF.refresh(); }catch(_){ /* noop */ }
    try{ if (window.EDS_WT && EDS_WT.forceInit) EDS_WT.forceInit(); }catch(_){ /* noop */ }
  }

  if (document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', attach, { once: true });
  } else {
    attach();
  }
})();
