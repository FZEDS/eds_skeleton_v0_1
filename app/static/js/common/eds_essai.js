// app/static/js/eds_essai.js
(function(){
  'use strict';
  if (window._EDS_ESSAI_ATTACHED) return;
  window._EDS_ESSAI_ATTACHED = true;

  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>Array.from(document.querySelectorAll(s));
  const parseNum = (v)=> v==null ? NaN : parseFloat(String(v).replace(',', '.'));

  // ----- Contexte minimum -----
  function getIdcc(){ const v = parseInt($('#idcc')?.value || '', 10); return Number.isNaN(v) ? null : v; }
  function getCategorie(){ return ($('#categorie')?.value || 'non-cadre').toLowerCase(); }
  function coeffFromClassif(){
    const raw = $('#classification_level')?.value || '';
    const m1 = raw.match(/co[eé]f(?:ficient)?\s*[:\-]?\s*(\d{2,3})/i);
    if (m1) return parseInt(m1[1], 10);
    const all = Array.from(raw.matchAll(/\b(\d{2,3})\b/g)).map(m => parseInt(m[1], 10));
    return all.length ? Math.max(...all) : null;
  }
  function getCoeff(){
    const c = coeffFromClassif();
    if (c!=null) return c;
    try{
      const v = (window.EDS_CTX && window.EDS_CTX.coeff!=null) ? window.EDS_CTX.coeff : null;
      if (v==null || v==='') return null;
      const n = parseInt(String(v), 10);
      return Number.isNaN(n) ? null : n;
    }catch(_){ return null; }
  }

  // ----- Helpers UI locaux (autonomes) -----
  function getStepNumber(){
    // Détection robuste: lire l'attribut data-step du conteneur du champ 'probation_months'
    const host = document.getElementById('probation_months')?.closest('.step');
    const n = host?.getAttribute?.('data-step');
    const parsed = n ? parseInt(n, 10) : NaN;
    if (!Number.isNaN(parsed)) return parsed;
    // Fallback: selon le type de document
    return (window.EDS_DOC === 'cdd') ? 8 : 7;
  }
  function stepEl(){ return document.querySelector(`.step[data-step="${getStepNumber()}"]`); }
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
  function clearError(input, errNode, ncKey){
    input?.classList.remove('input-error');
    input?.setCustomValidity?.('');
    if (errNode){ errNode.textContent=''; errNode.style.display='none'; }
    if (window.EDS_NON_COMPLIANCES && ncKey){ window.EDS_NON_COMPLIANCES.delete(ncKey); }
    setNextDisabled(false);
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
          if (window.EDS_OVERRIDES_STEPS) window.EDS_OVERRIDES_STEPS.add(stepNumber);
          setNextDisabled(false);
        });
      },0);
    }

    if (window.EDS_NON_COMPLIANCES && ncKey){
      window.EDS_NON_COMPLIANCES.set(ncKey, {
        key: ncKey, step: stepNumber, field: input?.name || 'probation_months',
        severity: 'hard', message: msg, suggested: fixTo ?? null,
      });
    }
    setNextDisabled(true);
  }

  // Petit utilitaire : un nœud a-t-il du contenu utile ?
  function hasContent(n){
    if (!n) return false;
    const txt = (n.textContent || '').trim();
    return !!txt || (n.children && n.children.length>0);
  }

  // Affichage conditionnel du bandeau "Renouvellement"
  function toggleRenewalHint(){
    const sel = stepEl()?.querySelector('select[name="probation_renewal_requested"]');
    const box = document.getElementById('essai_renewal');
    if (!sel || !box) return;
    // On cache si "Non", on montre si "Oui" ET s'il y a du contenu (injecté par le backend via explain[])
    box.style.display = (sel.value === 'oui' && hasContent(box)) ? 'block' : 'none';
  }

  // ----- Rendu bandeau principal -----
  function renderCard(maxm, rule){
    const card = $('#bounds_card');
    if(!card) return;
    if (maxm==null){ card.style.display='none'; card.textContent=''; return; }
    if (card.textContent && card.textContent.trim().length) return;
    const ref = rule?.source_ref || '';
    const url = rule?.url || '';
    const refHtml = url ? `<a href="${url}" target="_blank" rel="noopener">${ref || 'Réf.'}</a>` : (ref || '');
    card.className = 'callout';
    card.style.display = 'block';
    card.innerHTML = `<strong>Conformité (période d’essai)</strong><br>Plafond : <b>${maxm} mois</b>. ${refHtml ? `<small>${refHtml}</small>` : ''}`;
  }

  // ----- Appel API + validation -----
  async function refresh(){
    // Ne rien faire si l'étape 7 (Période d’essai) n'est pas visible
    const stepNum = getStepNumber();
    const isStep7Visible = !!document.querySelector(`.step[data-step="${stepNum}"][aria-hidden="false"]`);
    if (!isStep7Visible) return;
    const idcc  = getIdcc();
    const cat   = getCategorie();
    const coeff = getCoeff();
    const as_of = $('#contract_start')?.value || new Date().toISOString().slice(0,10);

    let bounds = {}, rule = {}, suggest = [];
    try{
      const q = new URLSearchParams({ categorie: cat, date: as_of });
      if (idcc)  q.append('idcc', String(idcc));
      if (coeff!=null) q.append('coeff', String(coeff));
      try{
        const ctx = (window.EDS_CTX || {});
        if (ctx.annexe) q.append('annexe', String(ctx.annexe));
        if (ctx.statut) q.append('statut', String(ctx.statut));
      }catch(_){ }

      // Contexte CDD : type et durée estimée
      try{
        if (window.EDS_DOC === 'cdd'){
          q.append('contract_type', 'cdd');
          const end = document.getElementById('contract_end')?.value || '';
          let durWeeks = null;
          if (end){
            const t0 = Date.parse(as_of);
            const t1 = Date.parse(end);
            if (!Number.isNaN(t0) && !Number.isNaN(t1) && t1>t0){
              durWeeks = Math.round((t1 - t0) / (7*24*3600*1000));
            }
          } else {
            // Sans terme précis: utiliser la durée minimale si présente
            const v = document.getElementById('cdd_min_duration_value')?.value;
            const u = document.getElementById('cdd_min_duration_unit')?.value || 'jours';
            if (v){
              const n = parseInt(String(v),10);
              if (!Number.isNaN(n)){
                durWeeks = (u === 'mois') ? Math.round((n*30)/7) : Math.round(n/7);
              }
            }
          }
          if (durWeeks!=null){ q.append('duration_weeks', String(durWeeks)); }
        }
      }catch(_){ }

      // plus de pré‑check via /api/resolve: l'étape 4 collecte déjà les infos nécessaires

      const r = await fetch('/api/essai/bounds?'+q.toString());
      const js = await r.json();

      // Hints / capabilities fournis par le backend
      if (Array.isArray(js?.explain) && window.renderExplain) {
        window.renderExplain(js.explain);
      }
      if (js?.capabilities && window.mergeCapabilities) {
        window.mergeCapabilities(js.capabilities);
      }

      bounds  = js?.bounds || {};
      rule    = js?.rule   || {};
      suggest = Array.isArray(js?.suggest) ? js.suggest : [];
    }catch(e){
      if (window.EDS_DEBUG) console.warn('essai/bounds failed', e);
    }

    // Fallback minimal si backend muet (on garde ta logique existante)
    let maxm = (typeof bounds?.max_months === 'number') ? bounds.max_months : null;
    if (maxm == null){
      maxm = (cat === 'cadre') ? 4 : 2;
      rule = rule || {};
      if (!rule.source_ref) rule.source_ref = 'C. trav., L1221-19 à L1221-25';
    }

    renderCard(maxm, rule);

    // Après rendu des explain[], on ajuste la visibilité du bandeau "renouvellement"
    toggleRenewalHint();

    // Validation
    const input = $('#probation_months');
    const err   = ensureErrNode('probation_err', input?.parentElement);
    if(!input || !err) return;

    const stepNumber = getStepNumber();
    const ncKey = 'essai_ui';

    clearError(input, err, ncKey);

    const v = parseNum(input.value);
    if(!Number.isNaN(v) && v > maxm){
      const s = suggest.find(x => x.field === 'probation_months');
      const fixTo = (s && s.value!=null) ? s.value : maxm;
      const ref = rule?.source_ref || '';
      showError(input, err, `Au-delà du plafond (${maxm} mois). ${ref ? 'Réf. ' + ref : ''}`, stepNumber, fixTo, ncKey);
    } else {
      setNextDisabled(false);
    }
  }

  // ----- Listeners -----
  $('#probation_months')?.addEventListener('input', refresh);
  ['#categorie','#contract_start'].forEach(sel=> $(sel)?.addEventListener('change', refresh));
  document.querySelector('input[name="classification_level"]')?.addEventListener('input', refresh);
  stepEl()?.querySelector('select[name="probation_renewal_requested"]')
    ?.addEventListener('change', toggleRenewalHint);

  // Expose
  window.EDS_ESSAI = window.EDS_ESSAI || {};
  window.EDS_ESSAI.refresh = refresh;

  document.addEventListener('DOMContentLoaded', ()=>{
    const stepNum = getStepNumber();
    if (document.querySelector(`.step[data-step="${stepNum}"][aria-hidden="false"]`)){
      refresh();
    }
  });
  document.addEventListener('eds:ctx_updated', refresh, false);
})();
