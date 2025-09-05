// app/static/js/eds_preavis.js
(function(){
  'use strict';
  if (window._EDS_PREAVIS_ATTACHED) return;
  window._EDS_PREAVIS_ATTACHED = true;

  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>Array.from(document.querySelectorAll(s));
  const parseNum = (v)=> v==null ? NaN : parseFloat(String(v).replace(',', '.'));

  // ---------- Contexte ----------
  function getIdcc(){ const v=parseInt($('#idcc')?.value||'',10); return Number.isNaN(v)?null:v; }
  function getCategorie(){ return ($('#categorie')?.value || 'non-cadre').toLowerCase(); }
  function coeffFromClassif(){
    const raw = $('#classification_level')?.value || '';
    const m1 = raw.match(/co[eé]f(?:ficient)?\s*[:\-]?\s*(\d{2,3})/i);
    if (m1) return parseInt(m1[1],10);
    const all = Array.from(raw.matchAll(/\b(\d{2,3})\b/g)).map(m => parseInt(m[1],10));
    return all.length ? Math.max(...all) : null;
  }
  function ancienneteMonths(){
    const y = parseInt($('#seniority_years')?.value || '0', 10) || 0;
    const m = parseInt($('#seniority_months')?.value || '0', 10) || 0;
    return (y*12)+m;
  }
  function escapeHtml(str){
    return String(str).replace(/[&<>"']/g, m => (
      {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]
    ));
  }

  // ---------- Helpers d’erreur / override ----------

  function nodeEmpty(n){
    if (!n) return true;
    const txt = (n.textContent || '').trim();
    const hasChild = n.children && n.children.length>0;
    return (!txt && !hasChild);
  }

  function stepEl(){ return document.querySelector('.step[data-step="8"]'); }
  function setNextDisabled(disabled){
    const btn = stepEl()?.querySelector('[data-next]');
    if (btn){ btn.disabled = !!disabled; btn.classList.toggle('disabled', !!disabled); }
  }
  function ensureErrNode(id, parent){
    let n = document.getElementById(id);
    if(!n){
      n = document.createElement('small');
      n.id = id; n.className='error-msg'; n.setAttribute('aria-live','polite'); n.style.display='none';
      (parent || document.body).appendChild(n);
    }
    return n;
  }
  function anyVisibleErrors(){
    const s = stepEl(); if (!s) return false;
    return Array.from(s.querySelectorAll('.error-msg')).some(e=> getComputedStyle(e).display!=='none');
  }
  function clearError(input, errNode, ncKey){
    input?.classList.remove('input-error');
    input?.setCustomValidity?.('');
    if (errNode){ errNode.textContent=''; errNode.style.display='none'; }
    if (window.EDS_NON_COMPLIANCES && ncKey){ window.EDS_NON_COMPLIANCES.delete(ncKey); }
    setNextDisabled(anyVisibleErrors());
  }
  function showError(input, errNode, msg, stepNumber, fixTo, ncKey){
    input?.classList.add('input-error');
    input?.setCustomValidity?.(msg);

    if (errNode){
      let html = `<span>${msg}</span>`;
      if (fixTo != null){
        html += ` <button type="button" class="btn" id="${errNode.id}_fix">Ramener à ${fixTo}</button>`;
      }
      html += ` <button type="button" class="btn-ghost" id="${errNode.id}_override">Continuer quand même</button>`;
      errNode.innerHTML = html; errNode.style.display='block';

      setTimeout(()=>{
        const fixBtn = $('#'+errNode.id+'_fix');
        if (fixBtn) fixBtn.addEventListener('click', ()=>{
          if(input){ input.value = String(fixTo); input.dispatchEvent(new Event('input')); }
          clearError(input, errNode, ncKey);
        });
        const overrideBtn = $('#'+errNode.id+'_override');
        if (overrideBtn) overrideBtn.addEventListener('click', ()=>{
          // Marque visuelle de l’override + état global
          overrideBtn.classList.add('is-on');
          if (window.EDS_OVERRIDES_STEPS) window.EDS_OVERRIDES_STEPS.add(stepNumber);
          // Ne pas masquer l’erreur (on assume la dérogation), mais réactiver le bouton si plus aucune autre erreur
          setNextDisabled(anyVisibleErrors());
        });
      },0);
    }

    if (window.EDS_NON_COMPLIANCES && ncKey){
      window.EDS_NON_COMPLIANCES.set(ncKey, {
        key: ncKey, step: stepNumber, field: input?.name || '',
        severity: 'hard', message: msg, suggested: fixTo ?? null,
      });
    }
    setNextDisabled(true);
  }

  // ---------- Rendu cartes ----------
  function renderNoticeCard(demMin, licMin, rule){
    const card = $('#notice_card'); if(!card) return;
    if (card.textContent && card.textContent.trim().length) return;
    const ref = rule?.source_ref || '';
    card.className = 'callout';
    card.style.display='block';
    const d = (demMin==null)?'—':demMin; const l=(licMin==null)?'—':licMin;
    card.innerHTML = `<strong>Conformité (préavis)</strong><br>Minima : démission <b>${d}</b> mois · licenciement <b>${l}</b> mois. <small>${escapeHtml(ref||'')}</small>`;
  }
  function renderCpCard(minDays, sugg, ref){
    const card = $('#cp_card'); if(!card) return;
    if (card.textContent && card.textContent.trim().length) return;
    if(minDays==null && sugg==null){ card.style.display='none'; card.textContent=''; return; }
    const unit = ($('#cp_unit')?.value || 'ouvrés');
    card.className='callout';
    card.style.display='block';
    card.innerHTML = `<strong>Conformité (congés)</strong><br>Minimum <b>${minDays??'—'}</b> ${unit} · suggestion <b>${sugg??'—'}</b>. <small>${escapeHtml(ref||'')}</small>`;
  }

  // ---------- Préavis ----------
  async function refreshNotice(){
    const idcc   = getIdcc();
    const cat    = getCategorie();
    const coeff  = coeffFromClassif();
    const ancM   = ancienneteMonths();

    let demMin=null, licMin=null, ref='', suggest=[];
    try{
      const q = new URLSearchParams({ categorie: cat, anciennete_months: String(ancM) });
      if (idcc)   q.append('idcc', String(idcc));
      if (coeff!=null) q.append('coeff', String(coeff));
      const r = await fetch('/api/preavis/bounds?'+q.toString());
      const js = await r.json();
      if (js?.explain && window.renderExplain) window.renderExplain(js.explain);
      if (js?.capabilities && window.mergeCapabilities) window.mergeCapabilities(js.capabilities);
      demMin  = js?.notice?.demission ?? null;
      licMin  = js?.notice?.licenciement ?? null;
      ref     = js?.rule?.source_ref || '';
      suggest = Array.isArray(js?.suggest) ? js.suggest : [];
    }catch(e){ if(window.EDS_DEBUG) console.warn('preavis/bounds failed', e); }

    renderNoticeCard(demMin, licMin, {source_ref: ref});

    const dem = $('#notice_dem'), lic = $('#notice_lic');
    const demErr = ensureErrNode('notice_dem_err', dem?.parentElement);
    const licErr = ensureErrNode('notice_lic_err', lic?.parentElement);

    // Auto-préremplissage si vide
    if(dem && (dem.value==='' || dem.value==null) && demMin!=null){ dem.value = String(demMin); }
    if(lic && (lic.value==='' || lic.value==null) && licMin!=null){ lic.value = String(licMin); }

    const ncKeyDem = 'preavis_dem_ui';
    const ncKeyLic = 'preavis_lic_ui';
    clearError(dem, demErr, ncKeyDem);
    clearError(lic, licErr, ncKeyLic);

    if(dem && demMin!=null){
      const v = parseNum(dem.value);
      if(!Number.isNaN(v) && v < demMin){
        const s = suggest.find(x => x.field === 'notice_resignation_months');
        const fixTo = (s && s.value!=null) ? s.value : demMin;
        showError(dem, demErr, `Inférieur au minimum (${demMin} mois). Réf. ${ref}`, 8, fixTo, ncKeyDem);
      }
    }
    if(lic && licMin!=null){
      const v = parseNum(lic.value);
      if(!Number.isNaN(v) && v < licMin){
        const s = suggest.find(x => x.field === 'notice_dismissal_months');
        const fixTo = (s && s.value!=null) ? s.value : licMin;
        showError(lic, licErr, `Inférieur au minimum (${licMin} mois). Réf. ${ref}`, 8, fixTo, ncKeyLic);
      }
    }
    setNextDisabled(anyVisibleErrors());
  }

  // ---------- Congés ----------
  async function refreshLeaves(){
    const idcc = getIdcc();
    const ancM = ancienneteMonths();
    const unit = ($('#cp_unit')?.value || 'ouvrés');

    let minDays=null, sugg=null, ref='';
    try{
      const q = new URLSearchParams({ unit, anciennete_months: String(ancM) });
      if (idcc) q.append('idcc', String(idcc));
      const r = await fetch('/api/conges/bounds?'+q.toString());
      const js = await r.json();
      if (js?.explain && window.renderExplain) window.renderExplain(js.explain); // conserver les hints backend
      if (js?.capabilities && window.mergeCapabilities) window.mergeCapabilities(js.capabilities);
      minDays = js?.conges?.min_days ?? null;
      sugg    = js?.conges?.suggested_days ?? null;
      ref     = js?.rule?.source_ref || '';
    }catch(e){ if(window.EDS_DEBUG) console.warn('conges/bounds failed', e); }

    renderCpCard(minDays, sugg, ref);

    const cp = $('#cp_days_number'); const err = ensureErrNode('cp_err', cp?.parentElement);
    const ncKey = 'cp_ui';
    clearError(cp, err, ncKey);

    // Validation : si rempli et < minimum => erreur (ramener à min légal/CCN si applicable)
    if (cp && cp.value && minDays!=null){
      const v = parseInt(cp.value, 10);
      if(!Number.isNaN(v) && v < minDays){
        showError(cp, err, `En‑dessous du minimum (${minDays} ${unit}). Réf. ${ref}`, 8, minDays, ncKey);
      }
    }
    setNextDisabled(anyVisibleErrors());
  }

  // ---------- Orchestrateur ----------
  async function refresh(){
    await refreshNotice();
    await refreshLeaves();
  }

  // ---------- Listeners ----------
  ['#seniority_years','#seniority_months'].forEach(sel=> $(sel)?.addEventListener('input', refresh));
  ['#notice_dem','#notice_lic'].forEach(sel=> $(sel)?.addEventListener('input', refresh));
  ['#categorie'].forEach(sel=> $(sel)?.addEventListener('change', refresh));
  document.querySelector('input[name="classification_level"]')?.addEventListener('input', refresh);

  ['#cp_days_number','#cp_unit'].forEach(sel=> $(sel)?.addEventListener('input', refresh));

  // Expose
  window.EDS_PREAVIS = window.EDS_PREAVIS || {};
  window.EDS_PREAVIS.refresh = refresh;

  document.addEventListener('DOMContentLoaded', refresh);
})();
