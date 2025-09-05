// app/static/js/common/eds_salary.js

(function(){
  'use strict';
  if (window._EDS_SAL_V2_ATTACHED) return;
  window._EDS_SAL_V2_ATTACHED = true;

  // ---------- Dom helpers ----------
  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>Array.from(document.querySelectorAll(s));
  function parseNum(v){ if(v==null||v==='') return null; const n=parseFloat(String(v).replace(',', '.')); return Number.isNaN(n)?null:n; }
  function fmt2(n){ try{ return (Math.round(Number(n)*100)/100).toFixed(2); }catch{ return String(n); } }

  // Brancher les slots additionnels de la step 6 (si renderExplain est utilisé ailleurs)
  window.SLOT_TARGETS = window.SLOT_TARGETS || {};
  window.SLOT_TARGETS['step6.footer'] = '#salary_card';
  window.SLOT_TARGETS['step6.more']   = '#salary_more_body';
  window.SLOT_TARGETS['step6.primes'] = '#salary_primes_body';

  // ---------- Contexte ----------
  function getIdcc(){ const v = parseInt($('#idcc')?.value || '', 10); return Number.isNaN(v) ? null : v; }
  function getCategorie(){ return ($('#categorie')?.value || 'non-cadre').toLowerCase(); }
  function getUiWorkTimeRaw(){ return document.querySelector('input[name="work_time_mode"]:checked')?.value || 'standard_35h'; }
  function getWorkTimeModeForApi(){
    const wt = getUiWorkTimeRaw();
    const regime = document.querySelector('input[name="work_time_regime"]:checked')?.value || 'temps_complet';
    if (wt === 'standard_35h') return (regime === 'temps_partiel') ? 'part_time' : 'standard';
    if (wt === 'modalite_2')   return 'forfait_hours_mod2';
    return wt; // 'forfait_hours' | 'forfait_days'
  }
  function getWeeklyHours(){
    const ui = getUiWorkTimeRaw();
    if (ui === 'standard_35h')  return parseNum($('#weekly_hours_std')?.value);
    if (ui === 'forfait_hours') return parseNum($('#weekly_hours_fh')?.value);
    if (ui === 'modalite_2')    return parseNum($('#weekly_hours_m2')?.value);
    return null;
  }
  function getForfaitDays(){
    return (getUiWorkTimeRaw() === 'forfait_days')
      ? (parseInt($('#forfait_days_per_year')?.value || '', 10) || null)
      : null;
  }
  function coeffFromClassif(){
    const raw = $('#classification_level')?.value || '';
    const m1 = raw.match(/co[eé]f(?:ficient)?\s*[:\-]?\s*(\d{2,3})/i);
    if (m1) return parseInt(m1[1], 10);
    const all = Array.from(raw.matchAll(/\b(\d{2,3})\b/g)).map(m => parseInt(m[1], 10));
    return all.length ? Math.max(...all) : null;
  }
  function getAsOf(){ return $('#contract_start')?.value || new Date().toISOString().slice(0,10); }

  // ---------- Ciblage tolérant (deux conventions d'IDs) ----------
  const inpMonthly = ()=> document.getElementById('salary_gross_monthly') || document.getElementById('salary_monthly');
  const inpYearly  = ()=> document.getElementById('salary_gross_annual')  || document.getElementById('salary_yearly');
  const inpHourly  = ()=> document.getElementById('salary_hourly'); // optionnel, peut ne pas exister

  const errMonthly = ()=> document.getElementById('salary_err') || document.getElementById('sal_monthly_err') || ensureErrNode('sal_monthly_err', inpMonthly()?.parentElement);
  const errYearly  = ()=> document.getElementById('sal_yearly_err')  || ensureErrNode('sal_yearly_err',  inpYearly()?.parentElement);
  const errHourly  = ()=> document.getElementById('sal_hourly_err')  || (inpHourly() ? ensureErrNode('sal_hourly_err',  inpHourly()?.parentElement) : null);

  // ---------- UI helpers ----------
  function stepEl(){ return document.querySelector('.step[data-step="6"]'); }
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
  function clearError(input, errNode){
    input?.classList.remove('input-error');
    input?.setCustomValidity?.('');
    if (errNode){ errNode.textContent=''; errNode.style.display='none'; }
    setNextDisabled(false);
  }
  function showError(input, errNode, msg, fixTo){
    if(!errNode) return;
    input?.classList.add('input-error');
    input?.setCustomValidity?.(msg);
    let html = `<span>${msg}</span>`;
    if (fixTo!=null) html += ` <button type="button" class="btn" id="${errNode.id}_fix">Ramener à ${fmt2(fixTo)} €</button>`;
    html += ` <button type="button" class="btn-ghost" id="${errNode.id}_override">Continuer quand même</button>`;
    errNode.innerHTML = html; errNode.style.display='block';
    setNextDisabled(true);
    setTimeout(()=>{
      const fixBtn = $('#'+errNode.id+'_fix');
      if (fixBtn) fixBtn.addEventListener('click', ()=>{
        if(input){ input.value = String(fmt2(fixTo)); input.dispatchEvent(new Event('input')); }
        clearError(input, errNode);
      });
      const overrideBtn = $('#'+errNode.id+'_override');
      if (overrideBtn) overrideBtn.addEventListener('click', ()=> setNextDisabled(false));
    },0);
  }

  // ---------- 13e mois (tolère 2 IDs) ----------
  function has13th(){ return !!($('#has_13th_month')?.checked || $('#bonus13_enabled')?.checked); }
  function toggle13thBoxes(){
    const box  = $('#bonus13_fields') || $('#has_13th_fields');
    const on = has13th();
    if (box) box.style.display = on ? 'block' : 'none';
    // champs libres
    const selW = $('#bonus13_when'); const freeW = $('#bonus13_when_free_wrap');
    if (selW && freeW) freeW.style.display = (selW.value === 'autre') ? 'block' : 'none';
    const selB = $('#bonus13_base'); const freeB = $('#bonus13_base_free_wrap');
    if (selB && freeB) freeB.style.display = (selB.value === 'autre') ? 'block' : 'none';
  }

  // ---------- Conversions ----------
  const WEEKS_PER_MONTH = 52/12;
  function weeklyHoursForCalc(){
    const mode = getWorkTimeModeForApi();
    if (mode === 'forfait_days') return null; // pas d'horaire de référence
    const wh = getWeeklyHours();
    return (wh && wh>0) ? wh : 35; // filet
  }

  let SYNCING = false;
  function fromMonthly(){
    if (SYNCING) return; SYNCING = true;
    const m = parseNum(inpMonthly()?.value);
    const wh = weeklyHoursForCalc();
    const months = has13th()?13:12;
    if (m!=null){
      if (inpYearly()) inpYearly().value = fmt2(m*months);
      if (inpHourly() && wh!=null) inpHourly().value = fmt2(m/(wh*WEEKS_PER_MONTH));
    }else{
      if (inpYearly()) inpYearly().value = '';
      if (inpHourly()) inpHourly().value = '';
    }
    SYNCING = false;
  }
  function fromYearly(){
    if (SYNCING) return; SYNCING = true;
    const y = parseNum(inpYearly()?.value);
    const wh = weeklyHoursForCalc();
    const months = has13th()?13:12;
    if (y!=null){
      const m = y / months;
      if (inpMonthly()) inpMonthly().value = fmt2(m);
      if (inpHourly() && wh!=null) inpHourly().value = fmt2(m/(wh*WEEKS_PER_MONTH));
    }
    SYNCING = false;
  }
  function fromHourly(){
    if (SYNCING) return; SYNCING = true;
    const h = parseNum(inpHourly()?.value);
    const wh = weeklyHoursForCalc();
    const months = has13th()?13:12;
    if (h!=null && wh!=null){
      const m = h * wh * WEEKS_PER_MONTH;
      if (inpMonthly()) inpMonthly().value = fmt2(m);
      if (inpYearly())  inpYearly().value  = fmt2(m*months);
    }
    SYNCING = false;
  }

  // ---------- Bandeau clair (mensuel principal) ----------
  function renderBanner(minima, rule){
    const card = $('#salary_card');
    if(!card) return;

    const floorM  = (typeof minima?.monthly_min_eur === 'number') ? minima.monthly_min_eur : null;
    const base    = (typeof minima?.base_min_eur     === 'number') ? minima.base_min_eur     : null;
    const details = minima?.details || {};
    const ccnM    = (typeof details?.ccn_monthly_floor_eur === 'number') ? details.ccn_monthly_floor_eur : null;
    const applied = Array.isArray(minima?.applied) ? minima.applied : [];
    const source  = (rule?.source || '').toLowerCase();  // 'ccn' ou 'code_travail'
    const sourceRef = rule?.source_ref || '';

    if (floorM==null){ card.style.display='none'; card.textContent=''; return; }

    const months = has13th()?13:12;
    const annual = floorM * months;

    const tag =
      applied.includes('forfait_jours_122pct') ? ' (forfait‑jours 122 %)' :
      applied.includes('forfait_jours_120pct') ? ' (forfait‑jours 120 %)' :
      applied.includes('modalite2_115pct')     ? ' (modalité 2 115 %)' : '';

    const catLbl = (getCategorie()==='cadre') ? 'Cadre' : 'Non‑cadre';
    const cls    = ($('#classification_level')?.value || '').trim();
    const mode   = getWorkTimeModeForApi();
    const wh     = weeklyHoursForCalc();
    const contexte = (mode === 'forfait_days') ? 'en forfait‑jours' : `à ${wh!=null ? wh+'h / semaine' : '35h / semaine'}`;

    const appliedLabel = (source === 'ccn') ? 'minimum conventionnel' : 'minimum légal (SMIC)';
    const rows = [];
    rows.push(`Plancher <b>mensuel</b> appliqué (${appliedLabel}) : <b>${fmt2(floorM)} €</b>.`);
    if (ccnM!=null) rows.push(`Référence CCN : <b>${fmt2(ccnM)} €</b>${tag}${base!=null ? ` (base coef : ${fmt2(base)} €)` : ''}.`);
    rows.push(`Soit à titre indicatif <b>${fmt2(annual)} € / an</b>${has13th() ? ' (13ᵉ inclus)' : ''}.`);

    card.className = 'callout';
    card.style.display='block';
    card.innerHTML =
      `Contrat <b>${catLbl}${cls ? ' ' + cls : ''}</b> ${contexte}.<br>` +
      rows.join('<br>') +
      (sourceRef ? `<br><small>${sourceRef}</small>` : ``);
  }

  // ---------- API + validation ----------
  async function refreshSalaire(){
    // nettoyage erreurs
    clearError(inpMonthly(), errMonthly());
    clearError(inpYearly(),  errYearly());
    if (inpHourly()) clearError(inpHourly(),  errHourly());

    const idcc  = getIdcc();
    const cat   = getCategorie();
    const coeff = coeffFromClassif();
    const mode  = getWorkTimeModeForApi();
    const wh    = getWeeklyHours();
    const fj    = getForfaitDays();
    const as_of = getAsOf();

    let minima = {}, rule = {};
    try{
      const q = new URLSearchParams({ categorie: cat, work_time_mode: mode, as_of });
      if(idcc) q.append('idcc', String(idcc));
      if(coeff!=null) q.append('coeff', String(coeff));
      if(wh!=null && !Number.isNaN(wh)) q.append('weekly_hours', String(wh));
      if(fj!=null) q.append('forfait_days_per_year', String(fj));
      const cl = $('#classification_level')?.value || '';
      if (cl) q.append('classification_level', cl);
      q.append('has_13th_month', has13th() ? 'true' : 'false'); // pris en compte par l'engine (ratios CCN)

      const r = await fetch('/api/salaire/bounds?'+q.toString());
      const js = await r.json();
      minima = js?.minima || {};
      rule   = js?.rule   || {};
      if (js?.explain && typeof window.renderExplain === 'function') window.renderExplain(js.explain); // ok, on écrase ensuite avec renderBanner()
      if (js?.capabilities && typeof window.mergeCapabilities === 'function') window.mergeCapabilities(js.capabilities);
    }catch(e){ if(window.EDS_DEBUG) console.warn('salaire/bounds failed', e); }

    // Bandeau “mensuel d'abord”
    renderBanner(minima, rule);

    // Seuils & valeurs
    const floorM = (typeof minima?.monthly_min_eur==='number') ? minima.monthly_min_eur : null;
    const months = has13th()?13:12;
    const whCalc = weeklyHoursForCalc();
    const floorY = (floorM!=null) ? floorM*months : null;
    const floorH = (floorM!=null && whCalc!=null) ? floorM/(whCalc*WEEKS_PER_MONTH) : null;

    const vM = parseNum(inpMonthly()?.value);
    const vY = parseNum(inpYearly()?.value);
    const vH = parseNum(inpHourly()?.value);

    // Erreurs (avec “ramener à”)
    if (floorM!=null && vM!=null && vM < floorM) showError(inpMonthly(), errMonthly(), `Doit être ≥ ${fmt2(floorM)} € / mois.`, floorM);
    if (floorY!=null && vY!=null && vY < floorY) showError(inpYearly(),  errYearly(),  `Doit être ≥ ${fmt2(floorY)} € / an.`,   floorY);
    if (floorH!=null && vH!=null && vH < floorH && errHourly()) showError(inpHourly(),  errHourly(),  `Doit être ≥ ${fmt2(floorH)} € / heure.`, floorH);

    if (typeof window.updateProgressUI === 'function') window.updateProgressUI();
  }

  // ---------- Listeners ----------
  function attachListeners(){
    // 13e mois
    $('#has_13th_month')?.addEventListener('change', ()=>{ toggle13thBoxes(); fromMonthly(); refreshSalaire(); });
    $('#bonus13_enabled')?.addEventListener('change', ()=>{ toggle13thBoxes(); fromMonthly(); refreshSalaire(); });
    $('#bonus13_when')?.addEventListener('change', toggle13thBoxes);
    $('#bonus13_base')?.addEventListener('change', toggle13thBoxes);

    // liaisons entre champs
    inpMonthly()?.addEventListener('input', ()=>{ fromMonthly(); refreshSalaire(); });
    inpYearly()?.addEventListener('input',  ()=>{ fromYearly();  refreshSalaire(); });
    if (inpHourly()) inpHourly().addEventListener('input', ()=>{ fromHourly(); refreshSalaire(); });

    // Contexte influant
    $$('#wt_35, #wt_fh_pay, #wt_fh_repos, #wt_fd, #wt_m2').forEach(r => r.addEventListener('change', ()=>{ fromMonthly(); refreshSalaire(); }));
    $$('#reg_full, #reg_part').forEach(r => r.addEventListener('change', ()=>{ fromMonthly(); refreshSalaire(); }));
    $('#weekly_hours_std')?.addEventListener('input', ()=>{ fromMonthly(); refreshSalaire(); });
    $('#weekly_hours_fh')?.addEventListener('input',  ()=>{ fromMonthly(); refreshSalaire(); });
    $('#weekly_hours_m2')?.addEventListener('input',  ()=>{ fromMonthly(); refreshSalaire(); });
    $('#forfait_days_per_year')?.addEventListener('input', ()=>{ fromMonthly(); refreshSalaire(); });
    $('#contract_start')?.addEventListener('change', refreshSalaire);
    $('#classification_level')?.addEventListener('input', refreshSalaire);
    $('#idcc')?.addEventListener('input', refreshSalaire);
    $('#idcc')?.addEventListener('change', refreshSalaire);
  }

  // ---------- Boot ----------
  document.addEventListener('DOMContentLoaded', ()=>{
    toggle13thBoxes();
    fromMonthly();         // initialise annuel/horaire si mensuel présent
    refreshSalaire();
  });
  attachListeners();

  // API externe minimale
  window.EDS_SAL = window.EDS_SAL || {};
  window.EDS_SAL.refresh = refreshSalaire;
})();
