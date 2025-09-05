// app/static/js/common/eds_worktime.js
(function () {
  'use strict';

  // ---------- Mini helpers ----------
  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>Array.from(document.querySelectorAll(s));
  const on = (el, ev, fn)=> el && el.addEventListener(ev, fn, false);

  function escapeHtml(str){
    return String(str||'').replace(/[&<>"']/g, m => (
      {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]
    ));
  }
  function nodeEmpty(n){
    if (!n) return true;
    const txt = (n.textContent || '').trim();
    const hasChild = n.children && n.children.length>0;
    return (!txt && !hasChild);
  }
  function show(selOrNode, yes){
    const n = (typeof selOrNode === 'string') ? $(selOrNode) : selOrNode;
    if (n) n.style.display = yes ? 'block' : 'none';
  }
  function round1(x){
    const n = parseFloat(String(x).replace(',','.'));
    return Number.isFinite(n) ? Math.round(n*10)/10 : null;
  }

  // ---------- Contexte ----------
  let step = null; // assigné dans init()

  function getIdcc() {
    const v = parseInt($('#idcc')?.value || '', 10);
    return Number.isNaN(v) ? null : v;
  }
  function getCategorie() {
    return ($('#categorie')?.value || 'non-cadre').toLowerCase();
  }
  function getAsOf() {
    return $('#contract_start')?.value || new Date().toISOString().slice(0, 10);
  }

  function getRegime() {
    return step?.querySelector('input[name="work_time_regime"]:checked')?.value || null;
  }
  function getUiModeRaw() {
    return step?.querySelector('input[name="work_time_mode"]:checked')?.value || null;
  }
  function apiModeFromUi() {
    const raw = getUiModeRaw();
    const reg = getRegime();
    if (!raw) return null;
    if (raw === 'standard_35h') return (reg === 'temps_partiel') ? 'part_time' : 'standard';
    if (raw === 'modalite_2')   return 'forfait_hours_mod2';
    return raw; // 'forfait_hours' | 'forfait_days'
  }

  // ---------- Unité / nommage (hebdo ↔ mensuel) ----------
  function isPartTimeMonthly(){
    return !!$('#pt_org_month')?.checked;
  }
  function setStdHoursUnit(unit /* 'week'|'month' */){
    const span = $('#std_hours_unit');
    const inp  = $('#weekly_hours_std');
    const hid  = $('#weekly_hours_hidden');
    if (span) span.textContent = (unit === 'month' ? 'mois' : 'semaine');

    if (!inp) return;
    if (unit === 'month'){
      // UI lisible en "mois" ; le back veut toujours weekly_hours → on passe par le hidden
      inp.name = 'monthly_hours';
      inp.placeholder = 'ex. 104';
      inp.removeAttribute('readonly');
      if (hid) hid.name = 'weekly_hours';
    } else {
      // mode hebdo : le champ visible est weekly_hours ; on neutralise le hidden
      inp.name = 'weekly_hours';
      if (hid) hid.name = 'weekly_hours_hidden';
    }
  }
  function setHiddenWeeklyValue(val){
    const h = $('#weekly_hours_hidden');
    if (h) h.value = (val==null || val==='') ? '' : String(val);
  }

  // ---------- UI helpers ----------
  function radioWrapper(id){
    const el = document.getElementById(id);
    return el ? el.closest('.radio') : null;
  }
  function setModeOptionVisibleById(id, visible){
    const w = radioWrapper(id);
    if (w) w.style.display = visible ? '' : 'none';
  }
  function setModeOptionVisible(modeKey, visible){
    if (modeKey === 'forfait_days') setModeOptionVisibleById('wt_fd', visible);
    if (modeKey === 'forfait_hours'){
      setModeOptionVisibleById('wt_fh_pay', visible);
      setModeOptionVisibleById('wt_fh_repos', visible);
    }
    if (modeKey === 'forfait_hours_mod2') setModeOptionVisibleById('wt_m2', visible);
  }
  function setNextDisabled(disabled){
    const btn = step?.querySelector('[data-next]');
    if (btn){ btn.disabled = !!disabled; btn.classList.toggle('disabled', !!disabled); }
  }
  function ensureErrNode(id, parent){
    let n = document.getElementById(id);
    if (!n){
      n = document.createElement('small');
      n.id = id; n.className = 'error-msg'; n.setAttribute('aria-live','polite');
      (parent || step)?.appendChild(n);
    }
    return n;
  }
  function clearError(input, errNode){
    input?.classList.remove('input-error');
    input?.setCustomValidity?.('');
    if (errNode){ errNode.innerHTML=''; errNode.style.display='none'; }
    setNextDisabled(false);
  }

  // version avec option d’override
  function showErrorEx(input, errNode, msg, fixTo, opts){
    const allowOverride = !!(opts && opts.allowOverride);
    input.classList.add('input-error');
    input.setCustomValidity?.(msg);

    let html = `<span>${escapeHtml(msg)}</span>`;
    if (fixTo != null) {
      html += ` <button type="button" class="btn" id="${errNode.id}_fix">Ramener à ${escapeHtml(String(fixTo))}</button>`;
    }
    if (allowOverride) {
      html += ` <button type="button" class="btn-ghost" id="${errNode.id}_override">Continuer quand même</button>`;
    }
    errNode.innerHTML = html;
    errNode.style.display = 'block';

    const fixBtn = document.getElementById(errNode.id + '_fix');
    if (fixBtn) on(fixBtn, 'click', ()=>{
      input.value = String(fixTo);
      input.dispatchEvent(new Event('input', {bubbles:true}));
      clearError(input, errNode);
    });

    const ovrBtn = document.getElementById(errNode.id + '_override');
    if (ovrBtn) on(ovrBtn, 'click', ()=>{
      step.dataset.override = 'on';
      ovrBtn.classList.add('is-on');
      setNextDisabled(false);
      input.setCustomValidity?.('');
    });

    // par défaut on bloque le bouton Suivant tant qu’on n’a pas corrigé/overridé
    if (!allowOverride || step?.dataset?.override !== 'on') {
      setNextDisabled(true);
    }
  }

  // ---------- Zoom par catégorie ----------
  function normalizeCategoryUI(){
    // 1) source principale: champ générique
    let c = ($('#categorie')?.value || '').trim().toLowerCase();
    // 2) pour Syntec, si un sélecteur dédié existe, on le privilégie
    const syntecSel = $('#syntec_cat')?.value?.trim().toLowerCase();
    if (syntecSel) c = syntecSel; // valeurs attendues: "cadre" | "etam"

    const isNonCadre = [
      'non-cadre','non cadre','noncadre','etam',
      'ouvrier','employe','employé','technicien',
      'agent de maitrise','agent de maîtrise','am'
    ].includes(c);

    const isCadre = [
      'cadre','ic','ingenieur','ingénieur'
    ].includes(c);

    return { raw: c, isNonCadre, isCadre };
  }

  function labelFromCategorie(){
    const idcc = getIdcc();
    const cl   = ($('#classification_level')?.value || '').toLowerCase();
    const { isNonCadre, isCadre } = normalizeCategoryUI();

    // Syntec (1486) : affiche "Cadres (IC)" / "ETAM (...)"
    if (idcc === 1486){
      if (isNonCadre) return 'ETAM (employés/techniciens/AM)';
      if (isCadre)    return 'Cadres (IC)';
      // défaut raisonnable si indéterminé
      return 'ETAM (employés/techniciens/AM)';
    }

    // HCR (1979) : conserve la logique AM, mais ne déclenche "Cadres" que si c'est vraiment "cadre"
    if (idcc === 1979){
      if (isCadre) return 'Cadres';
      if (/ma[iî]trise|am\b/.test(cl)) return 'Agents de maîtrise';
      return 'Employés';
    }

    // par défaut (autres CCN)
    return isCadre ? 'Cadres' : 'non‑cadres';
  }

  function updateZoomSummary(){
    const sum = $('#zoom_cat_summary');
    if (!sum) return;
    sum.textContent = ` Zoom sur la durée de travail des ${labelFromCategorie()}`;
  }
  async function refreshZoomByCategory(){
    const panel = $('#zoom_by_cat');
    const body  = $('#zoom_cat_body');
    if (!panel || !body) return;

    body.innerHTML = '';
    panel.classList.remove('callout-info','callout-ccn','callout-warn');
    panel.classList.add('callout-info');

    let res = {};
    try{
      const idcc = getIdcc();
      const q = new URLSearchParams({ theme: 'temps_travail', categorie: getCategorie(), as_of: getAsOf() });
      if (idcc) q.append('idcc', String(idcc));
      const r = await fetch('/api/resolve?'+q.toString());
      res = await r.json();
    }catch(e){ res = {}; }

    const items = Array.isArray(res.explain) ? res.explain.filter(x => x.slot === 'step5.zoom.category') : [];

    if (items.length){
      const hasWarn = items.some(x => String(x.kind||'').toLowerCase().includes('warn'));
      const hasCCN  = items.some(x => String(x.kind||'').toLowerCase()==='ccn');
      panel.classList.add(hasWarn ? 'callout-warn' : (hasCCN ? 'callout-ccn' : 'callout-info'));
      const html = items.map(x=>{
        const text = escapeHtml(x.text||'').replace(/\n/g,'<br>');
        const ref  = x.url ? `<small><a href="${x.url}" target="_blank" rel="noopener">${escapeHtml(x.ref||'Réf.')}</a></small>`
                           : (x.ref ? `<small>${escapeHtml(x.ref)}</small>` : '');
        return `<div style="margin-top:6px">${text}${ref?'<br>'+ref:''}</div>`;
      }).join('');
      body.innerHTML = html;
    }else{
      body.innerHTML =
        `<div style="margin-top:6px">
          Rappels généraux : à temps complet, la référence est 35h/semaine. Les heures au‑delà relèvent
          des heures supplémentaires (majoration ou repos équivalent). Le forfait‑jours suppose autonomie,
          suivi de la charge et garanties d’accord. En cas de doute, se référer à la CCN.
        </div>`;
      panel.classList.add('callout-info');
    }

    panel.style.display = 'block';
  }

  // ---------- State règles/bornes ----------
  let lastCaps = {};
  let lastBounds = {};

  function applyCapabilities(caps){
    lastCaps = caps || {};
    const wm = lastCaps.work_time_modes || {};

    setModeOptionVisible('forfait_days', !(wm.forfait_days === false));
    setModeOptionVisible('forfait_hours', !(wm.forfait_hours === false));
    setModeOptionVisible('forfait_hours_mod2', !(wm.forfait_hours_mod2 === false));

    // Si l’option choisie vient d’être masquée -> rebascule sur 35h
    const selected = step?.querySelector('input[name="work_time_mode"]:checked');
    if (selected) {
      const wrap = selected.closest('.radio');
      if (wrap && getComputedStyle(wrap).display === 'none'){
        const fallback = $('#wt_35');
        if (fallback) { fallback.checked = true; onModeChange(); }
      }
    }

    const dfl = (caps.defaults || {});
    if (dfl.forfait_days_per_year){
      const fj = $('#forfait_days_per_year');
      if (fj && !fj.value) fj.placeholder = String(dfl.forfait_days_per_year);
    }
  }

  function renderExplain(items){
    if (!Array.isArray(items)) return;

    const SLOT = {
      'step5.block.fh':          '#fh_card',
      'step5.block.fd':          '#fd_guard',
      'step5.block.fd.info':     '#fd_info',
      'step5.block.m2':          '#m2_card',     // Modalité 2
      'step5.block.std':         '#std_card',
      'step5.footer':            '#worktime_card',
      'step5.part_time.header':  '#pt_header',
      'step5.part_time.fixed':   '#pt_fixed_card',
      'step5.part_time.flex':    '#pt_flex_card',      // conservé s'il existe encore dans le DOM
      'step5.part_time.coupures':'#pt_coupures_card',
      'step5.part_time.modif':   '#pt_modif_card',
    };

    // reset slots
    Object.values(SLOT).forEach(sel=>{
      const n = $(sel); if(!n) return;
      n.innerHTML = ''; n.style.display='none';
      n.classList.remove('callout-info','callout-warn','callout-ccn');
      if (!n.classList.contains('callout')) n.classList.add('callout');
    });

    items.forEach(it=>{
      const node = $(SLOT[it.slot] || '#worktime_card'); if(!node) return;
      const kind = String(it.kind||'info').toLowerCase();

      node.classList.remove('callout-info','callout-warn','callout-ccn');
      if (kind === 'warn' || kind === 'guard')      node.classList.add('callout-warn');
      else if (kind === 'ccn')                       node.classList.add('callout-ccn');
      else                                           node.classList.add('callout-info');

      const ref = it.url
        ? `<small><a href="${it.url}" target="_blank" rel="noopener">${escapeHtml(it.ref || 'Réf.')}</a></small>`
        : (it.ref ? `<small>${escapeHtml(it.ref)}</small>` : '');

      const div = document.createElement('div');
      div.style.marginTop = '4px';
      const htmlText = escapeHtml(it.text || '').replace(/\n/g, '<br>');
      div.innerHTML = `${htmlText}${ref ? '<br>'+ref : ''}`;
      node.appendChild(div);
      node.style.display = 'block';
    });
  }

  // --- Bandeau "Conformité" par régime (TC / TP) ---
  function renderRegimeConformity(){
    const card = $('#regime_conformity_card');
    if (!card) return;

    const regime = getRegime();
    card.className = 'callout callout-info';
    card.style.display = 'none';
    card.innerHTML = '';

    if (regime === 'temps_complet') {
      card.innerHTML =
        `<strong>Conformité Temps complet</strong><br>
         min <b>35</b> h/sem · max <b>48</b> h/sem · moyenne <b>44</b> h sur 12 semaines.<br>
         <small>C. trav., L3121‑20 s. (48h/sem max ; moy. 44h/12 sem)</small>`;
      card.style.display = 'block';
    } else if (regime === 'temps_partiel') {
      card.innerHTML =
        `<strong>Conformité Temps partiel</strong><br>
         Hebdomadaire : min <b>24</b> h/sem · max <b>34.9</b> h/sem.<br>
         <small>C. trav., L3123‑27 à L3123‑34 (temps partiel)</small><br>
         L'entreprise devra s'assurer que son temps de travail réel ne dépasse pas ce qui est prévu dans son contrat. A défaut, le salarié peut réclamer le paiement d'heures supplémentaires. 💡 Si cela ne correspondra pas à la réalité de son travail, vous pouvez envisager un autre mode d'organisation du temps de travail (forfait jours, etc.)<br>
         <small>C. trav., L3121‑27 & L3123‑27</small>`;
      card.style.display = 'block';
    }
  }

  // ---------- Validations ----------
  function validateStandard(){
    const input = $('#weekly_hours_std');
    if (!input) return;
    const err = ensureErrNode('std_err', input.parentElement);
    clearError(input, err);

    const reg = getRegime();
    const monthlyMode = (reg === 'temps_partiel') && isPartTimeMonthly();
    const v   = parseFloat(String(input.value||'').replace(',', '.'));

    // BORNES EFFECTIVES = API en priorité, sinon attributs HTML (fallback)
    const wMin = (lastBounds && typeof lastBounds.weekly_hours_min === 'number') ? lastBounds.weekly_hours_min : null;
    const wMax = (lastBounds && typeof lastBounds.weekly_hours_max === 'number') ? lastBounds.weekly_hours_max : null;

    if (!Number.isNaN(v)){
      if (monthlyMode){
        const mMin = (wMin!=null) ? round1(wMin * (52/12)) : null;  // 24 → 104
        const mMax = (wMax!=null) ? round1(wMax * (52/12)) : null;  // 34.9 → ~151.1
        if (mMin!=null && v < mMin){
          showErrorEx(input, err, `En‑dessous du minimum (${mMin} h/mois).`, mMin, { allowOverride:true }); return;
        }
        if (mMax!=null && v > mMax){
          showErrorEx(input, err, `Au‑delà du maximum (${mMax} h/mois).`, mMax, { allowOverride:false }); return;
        }
      } else {
        if (wMin!=null && v < wMin){
          const allowOverride = (reg === 'temps_partiel'); // dérogations légales
          const msg = allowOverride
            ? `En‑dessous du minimum légal (${wMin} h/sem) — nécessite une dérogation.`
            : `En‑dessous du minimum autorisé (${wMin} h/sem).`;
          showErrorEx(input, err, msg, wMin, { allowOverride }); return;
        }
        if (wMax!=null && v > wMax){
          showErrorEx(input, err, `Au‑delà du maximum (${wMax} h/sem).`, wMax, { allowOverride:false }); return;
        }
      }
    }
  }

  function validateFJ(){
    const input = $('#forfait_days_per_year');
    if (!input) return;
    const err = ensureErrNode('fd_err', input.parentElement);
    clearError(input, err);

    const v = parseInt(input.value || '', 10);
    const dmax = lastBounds.days_per_year_max;

    if (!Number.isNaN(v) && dmax!=null && v > dmax){
      showErrorEx(input, err, `Au‑delà du plafond (${dmax} jours/an).`, dmax, { allowOverride:false });
      return;
    }
  }
  function validateFH(){
    const input = $('#weekly_hours_fh');
    if (!input) return;
    const err = ensureErrNode('fh_err', input.parentElement);
    clearError(input, err);

    const v  = parseFloat(String(input.value||'').replace(',', '.'));
    const mn = lastBounds.weekly_hours_min;
    const mx = lastBounds.weekly_hours_max;

    if (!Number.isNaN(v)){
      if (mn!=null && v < mn){ showErrorEx(input, err, `En‑dessous du minimum (${mn} h/sem).`, mn, { allowOverride:false }); return; }
      if (mx!=null && v > mx){ showErrorEx(input, err, `Au‑delà du maximum (${mx} h/sem).`, mx, { allowOverride:false }); return; }
    }
  }
  function validateM2(){
    const input = $('#weekly_hours_m2');
    if (!input) return;
    const err = ensureErrNode('m2_err', input.parentElement);
    clearError(input, err);

    const v  = parseFloat(String(input.value||'').replace(',', '.'));
    const mn = lastBounds.weekly_hours_min;
    const mx = lastBounds.weekly_hours_max;

    if (!Number.isNaN(v)){
      if (mn!=null && v < mn){ showErrorEx(input, err, `En‑dessous du minimum (${mn} h/sem).`, mn, { allowOverride:false }); return; }
      if (mx!=null && v > mx){ showErrorEx(input, err, `Au‑delà du maximum (${mx} h/sem).`, mx, { allowOverride:false }); return; }
    }
  }

  // ---------- Avertissement < 24 h/sem (hebdo) ou < 104 h/mois (mensuel) ----------
  function ensurePtFloorHintNode(){
    let n = $('#pt_floor_hint');
    if (!n){
      const host = $('#weekly_hours_std')?.parentElement || step;
      n = document.createElement('div');
      n.id = 'pt_floor_hint';
      n.className = 'callout callout-warn';
      n.style.display = 'none';
      n.style.marginTop = '8px';
      host?.appendChild(n);
    }
    return n;
  }

  function renderPtFloorHintWeekly(floorW){
    const node = ensurePtFloorHintNode();
    const monthly = Math.round((floorW * 52) / 12); // ex. 24h => ~104h
    node.innerHTML =
      `<div>
        <strong>Durée minimale en temps partiel</strong><br>
        Si vous mentionnez une durée <b>inférieure à ${floorW} h / semaine</b> (ou <b>${monthly} h / mois</b>),
        cela n'est légalement possible que si :
        <ul style="margin:6px 0 0 18px">
          <li><b>demande écrite et motivée du salarié</b> (contraintes personnelles) ou <b>cumul d’emplois</b> permettant d’atteindre au moins ${floorW} h hebdo (ou un temps plein) ;</li>
          <li><b>salarié étudiant de moins de 26 ans</b> poursuivant des études ;</li>
          <li><b>accord de branche étendu</b> fixant un plancher inférieur assorti de garanties.</li>
        </ul>
        <small>Réfs : C. trav. L3123‑7, L3123‑27, L3123‑30, L3123‑31. Vérifier la CCN.</small>
      </div>`;
  }
  function renderPtFloorHintMonthly(floorM){
    const node = ensurePtFloorHintNode();
    node.innerHTML =
      `<div>
        <strong>Durée minimale en temps partiel (mensuelle)</strong><br>
        Si vous mentionnez une durée <b>inférieure à ${floorM} h / mois</b>,
        cela n'est légalement possible que si :
        <ul style="margin:6px 0 0 18px">
          <li><b>demande écrite et motivée du salarié</b> (contraintes personnelles) ou <b>cumul d’emplois</b> permettant d’atteindre au moins ${floorM} h/mois (ou un temps plein) ;</li>
          <li><b>salarié étudiant de moins de 26 ans</b> poursuivant des études ;</li>
          <li><b>accord de branche étendu</b> fixant un plancher inférieur assorti de garanties.</li>
        </ul>
        <small>Réfs : C. trav. L3123‑7, L3123‑27, L3123‑30, L3123‑31. Vérifier la CCN.</small>
      </div>`;
  }

  function maybeShowPartTimeFloorHint(){
    const isPT = $('#reg_part')?.checked;
    const std  = $('#weekly_hours_std');
    if (!isPT || !std) { show('#pt_floor_hint', false); return; }

    const monthlyMode = isPartTimeMonthly();
    const v = parseFloat(String(std.value||'').replace(',','.'));

    const wFloor = (lastBounds && typeof lastBounds.weekly_hours_min === 'number')
      ? lastBounds.weekly_hours_min : 24;
    const mFloor = round1(wFloor * (52/12)); // ≈ 104

    const hint = $('#pt_floor_hint');
    const err  = ensureErrNode('std_err', std.parentElement);

    if (monthlyMode){
      renderPtFloorHintMonthly(mFloor);
      if (!Number.isNaN(v) && v < mFloor){
        show(hint, true);
        const msg = `En‑dessous du minimum légal (${mFloor} h/mois) — nécessite une dérogation.`;
        showErrorEx(std, err, msg, mFloor, { allowOverride:true });
      } else {
        show(hint, false); clearError(std, err);
      }
    } else {
      renderPtFloorHintWeekly(wFloor);
      if (!Number.isNaN(v) && v < wFloor){
        show(hint, true);
        const msg = `En‑dessous du minimum légal (${wFloor} h/sem) — nécessite une dérogation.`;
        showErrorEx(std, err, msg, wFloor, { allowOverride:true });
      } else {
        show(hint, false); clearError(std, err);
      }
    }
  }

  // ---------- Temps partiel : obligations (durée + organisation obligatoires) ----------
  function ensurePtOrgErrNode(){
    const host = $('#pt_org_fixed')?.closest('.vlist') || $('#blk_part_time') || step;
    return ensureErrNode('pt_org_err', host);
  }

  function validatePartTimeRequired(){
    const reg = getRegime();
    const std = $('#weekly_hours_std');

    // Si on n'est pas en temps partiel, on nettoie l'erreur éventuelle et on sort.
    const orgErr = ensurePtOrgErrNode();
    if (reg !== 'temps_partiel') {
      if (orgErr) { orgErr.innerHTML = ''; orgErr.style.display = 'none'; }
      return;
    }

    let hasError = false;

    // 1) Durée : obligatoire (hebdo OU mensuel selon choix)
    if (std){
      const val = (std.value || '').trim();
      const errStd = ensureErrNode('std_err', std.parentElement);
      const monthlyMode = isPartTimeMonthly();
      if (!val){
        const label = monthlyMode ? 'mensuelle (heures/mois)' : 'hebdomadaire (heures/semaine)';
        showErrorEx(std, errStd, `Veuillez renseigner une durée ${label}.`, null, { allowOverride: false });
        hasError = true;
      }
    }

    // 2) Organisation : obligatoire (hebdo "fixed" OU "monthly")
    const orgSelected = !!($('#pt_org_fixed')?.checked || $('#pt_org_month')?.checked);
    if (!orgSelected){
      orgErr.innerHTML = `<span>Veuillez sélectionner une organisation du temps partiel (déterminée par jour ou mensuelle par semaine).</span>`;
      orgErr.style.display = 'block';
      setNextDisabled(true);
      hasError = true;
    } else {
      orgErr.innerHTML = '';
      orgErr.style.display = 'none';
    }

    if (!hasError){
      // On laisse les autres validations (plancher/plafond) décider de l'état final du bouton.
      setNextDisabled(false);
    }
  }

  // ---------- API & (ré)affichage ----------
  function updateStdMinMaxForCurrentUnit(){
    const std = $('#weekly_hours_std');
    if (!std) return;
    const reg = getRegime();
    const monthlyMode = (reg === 'temps_partiel') && isPartTimeMonthly();

    const wMin = (lastBounds && typeof lastBounds.weekly_hours_min === 'number') ? lastBounds.weekly_hours_min : null;
    const wMax = (lastBounds && typeof lastBounds.weekly_hours_max === 'number') ? lastBounds.weekly_hours_max : null;

    if (monthlyMode){
      // on autorise < 104 pour déclencher l'override → min=1 ; max = borne convertie si dispo
      std.min = '1';
      std.max = (wMax!=null) ? String(round1(wMax * (52/12))) : (std.max||'');
    } else {
      // hebdo : min=1 en TP pour déclencher l'override ; max = borne API
      if (reg === 'temps_partiel'){
        std.min = '1';
        std.max = (wMax!=null) ? String(wMax) : (std.max||'');
      } else {
        // temps complet → 35 fixes (géré ailleurs)
      }
    }
  }

  async function refreshFromApi(){
    const idcc   = getIdcc();
    const mode   = apiModeFromUi();
    const as_of  = getAsOf();
    const cat    = getCategorie();

    if (!mode) return;

    let payload = {};
    try{
      const q = new URLSearchParams({ work_time_mode: mode, as_of, categorie: cat });
      if (idcc) q.append('idcc', String(idcc));
      const r = await fetch('/api/temps/bounds?' + q.toString());
      payload = await r.json();
    }catch(e){
      console.warn('temps/bounds failed', e);
      payload = {};
    }

    lastBounds = payload.bounds || {};
    applyCapabilities(payload.capabilities || {});
    renderExplain(Array.isArray(payload.explain) ? payload.explain : []);

    // Bandeau générique si l’API n’a rien envoyé (standard/part_time)
    const card = $('#worktime_card');
    if (card){
      const hasContent = !!(card.textContent && card.textContent.trim().length);
      if (!hasContent) {
        card.className = 'callout';
        card.style.display = 'none';
        const rule = payload.rule || {};
        if (mode==='standard' || mode==='part_time'){
          const mn = lastBounds.weekly_hours_min, mx = lastBounds.weekly_hours_max;
          if (mn!=null || mx!=null){
            card.classList.add('callout-info');
            const span = (mn!=null && mx!=null)
              ? `Plage : <b>${mn}</b>–<b>${mx}</b> h/sem.`
              : (mn!=null ? `Minimum : <b>${mn}</b> h/sem.` : `Maximum : <b>${mx}</b> h/sem.`);
            card.innerHTML = `<strong>Conformité (temps de travail)</strong><br>${span} ${rule.source_ref ? `<small>${escapeHtml(rule.source_ref)}</small>` : ''}`;
            card.style.display = 'block';
          }
        } else if (mode==='forfait_days'){
          const dmax = lastBounds.days_per_year_max;
          if (dmax!=null){
            card.classList.add('callout-info');
            card.innerHTML = `<strong>Conformité (forfait‑jours)</strong><br>Plafond : <b>${dmax}</b> jours/an.`;
            card.style.display = 'block';
          }
        }
      }
    }

    // Fallback cartouches Modalité 2 si besoin
    if (mode==='forfait_hours_mod2'){
      const n = $('#m2_card');
      if (n && nodeEmpty(n)){
        const mn = lastBounds.weekly_hours_min, mx = lastBounds.weekly_hours_max, dcap = lastBounds.days_per_year_max;
        const ref = (payload.rule && payload.rule.source_ref) ? payload.rule.source_ref : 'Syntec — Modalité 2';
        if (mn!=null || mx!=null || dcap!=null){
          n.className = 'callout-info';
          let seg = '';
          if (mn!=null || mx!=null){
            seg += (mn!=null && mx!=null) ? `min <b>${mn}</b> h/sem · max <b>${mx}</b> h/sem` :
                   (mn!=null ? `min <b>${mn}</b> h/sem` : `max <b>${mx}</b> h/sem`);
          }
          if (dcap!=null) seg += (seg ? ' · ' : '') + `plafond <b>${dcap}</b> j/an`;
          n.innerHTML = `<strong>Conformité (Modalité 2)</strong><br>${seg}. <small>${escapeHtml(ref)}</small>`;
          n.style.display='block';
        }
      }
      if ($('#m2_days_cap') && lastBounds.days_per_year_max!=null){
        $('#m2_days_cap').value = String(lastBounds.days_per_year_max);
      }
    }

    // Bornes + revalidations
    const std = $('#weekly_hours_std');
    if ((mode==='standard' || mode==='part_time') && std){
      // Hebdo/mensuel : bornes et validations adaptées
      updateStdMinMaxForCurrentUnit();
      validateStandard();
      maybeShowPartTimeFloorHint();
      validatePartTimeRequired();
    }
    const fh = $('#weekly_hours_fh');
    if (mode==='forfait_hours' && fh){
      if (lastBounds.weekly_hours_min!=null) fh.min = String(lastBounds.weekly_hours_min);
      if (lastBounds.weekly_hours_max!=null) fh.max = String(lastBounds.weekly_hours_max);
      validateFH();
    }
    const m2 = $('#weekly_hours_m2');
    if (mode==='forfait_hours_mod2' && m2){
      if (lastBounds.weekly_hours_min!=null) m2.min = String(lastBounds.weekly_hours_min);
      if (lastBounds.weekly_hours_max!=null) m2.max = String(lastBounds.weekly_hours_max);
      validateM2();
    }
    const fd = $('#forfait_days_per_year');
    if (mode==='forfait_days' && fd){
      if (lastBounds.days_per_year_max!=null) fd.max = String(lastBounds.days_per_year_max);
      validateFJ();
    }
  }

  // ---------- Temps partiel : sérialisation & UI ----------
  function ptSerialize(){
    // A) Hebdomadaire déterminée par jour
    const days = ['mon','tue','wed','thu','fri','sat','sun'];
    const fixed = { days:[], total_hours:0 };
    days.forEach(k=>{
      const on  = $('#pt_'+k+'_on')?.checked;
      const hrs = parseFloat(String($('#pt_'+k+'_hours')?.value || '').replace(',','.'));
      if (on && !Number.isNaN(hrs) && hrs>0){
        fixed.days.push({ day:k, hours:+hrs.toFixed(2) });
        fixed.total_hours += hrs;
      }
    });
    fixed.total_hours = +fixed.total_hours.toFixed(2);

    // B) Mensuelle par semaine (1→4)
    const monthly = { weeks:[], total_hours:0 };
    [1,2,3,4].forEach(i=>{
      const on  = $('#pt_w'+i+'_on')?.checked;
      const hrs = parseFloat(String($('#pt_w'+i+'_hours')?.value || '').replace(',','.'));
      if (on && !Number.isNaN(hrs) && hrs>0){
        monthly.weeks.push({ week:i, hours:+hrs.toFixed(2) });
        monthly.total_hours += hrs;
      }
    });
    monthly.total_hours = +monthly.total_hours.toFixed(2);

    // C) Organisation choisie
    const org = ( $('#pt_org_fixed')?.checked ? 'fixed' : ($('#pt_org_month')?.checked ? 'monthly' : null) );

    // D) Cadre / coupures (IDs conservés pour compat PDF)
    const flex = {
      frame: $('#pt_flex_frame')?.value || 'code',
      breaks_max: parseInt($('#pt_breaks_max')?.value || '',10) || null,
      break_max_hours: parseFloat(String($('#pt_break_max_hours')?.value || '').replace(',','.')) || null,
      counterparties: $('#pt_break_counterparties')?.value || ''
    };

    // E) Modifs de répartition
    const modif = {
      reasons: ($('#pt_modif_reasons')?.value || '').trim(),
      notice_days: parseInt($('#pt_modif_notice_days')?.value || '',10) || null,
      notice_unit: $('#pt_modif_notice_unit')?.value || 'jours'
    };

    // F) Priorité d’affectation (inchangé)
    const priority = {
      reply_days: parseInt($('#pt_priority_reply_days')?.value || '',10) || null
    };

    const payload = { organization: org, fixed, monthly, flex, modif, priority };
    $('#part_time_payload')?.setAttribute('value', JSON.stringify(payload));
    return payload;
  }

  function ptApplyTotalsToWeekly(){
    const p = ptSerialize();

    // Sorties UI (totaux)
    const outWeek = $('#pt_total_hours');
    if (outWeek){
      const val = ($('#pt_org_fixed')?.checked) ? p.fixed.total_hours : 0;
      outWeek.textContent = (Math.round(val * 10) / 10).toFixed(1);
    }
    const outMonth = $('#pt_total_hours_month');
    if (outMonth){
      const val = ($('#pt_org_month')?.checked) ? p.monthly.total_hours : 0;
      outMonth.textContent = (Math.round(val * 10) / 10).toFixed(1);
    }

    // Alimente l'UX + le back :
    // - en mensuel → champ visible = heures/mois ; hidden weekly = mois/4
    // - en hebdo   → champ visible = heures/sem ; hidden weekly vide
    const input = $('#weekly_hours_std');
    if (input && $('#reg_part')?.checked){
      if ($('#pt_org_month')?.checked){
        const m = p.monthly.total_hours || 0;
        input.value = m ? String(round1(m)) : '';
        setHiddenWeeklyValue( m ? round1(m/4) : '' );
      } else {
        const w = p.fixed.total_hours || 0;
        input.value = w ? String(round1(w)) : '';
        setHiddenWeeklyValue('');
      }
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    validatePartTimeRequired();
  }

  function ptToggleUI(){
    const isPT = $('#reg_part')?.checked;
    show('#blk_part_time', isPT);
    if (!isPT) return;

    const orgMonthly = !!$('#pt_org_month')?.checked;
    const orgFixed   = !!$('#pt_org_fixed')?.checked;

    // Afficher/masquer les sous-blocs si présents
    show('#pt_fixed_box',   orgFixed);
    show('#pt_monthly_box', orgMonthly);

    // Zone "commune" (coupures & co) — si renommée, on tente les 2 IDs pour compat
    const commonBox = $('#pt_common_box') || $('#pt_flex_box');
    if (commonBox) show(commonBox, true);

    // Activer/désactiver inputs hebdo
    ['mon','tue','wed','thu','fri','sat','sun'].forEach(k=>{
      const cb = $('#pt_'+k+'_on');
      const h  = $('#pt_'+k+'_hours');
      if (h){ h.disabled = !(orgFixed && cb?.checked); if (!orgFixed) h.value=''; }
      if (cb && !orgFixed) cb.checked = false;
    });

    // Activer/désactiver inputs mensuels
    [1,2,3,4].forEach(i=>{
      const cb = $('#pt_w'+i+'_on');
      const h  = $('#pt_w'+i+'_hours');
      if (h){ h.disabled = !(orgMonthly && cb?.checked); if (!orgMonthly) h.value=''; }
      if (cb && !orgMonthly) cb.checked = false;
    });

    // Bascule du label & des names
    setStdHoursUnit(orgMonthly ? 'month' : 'week');

    ptApplyTotalsToWeekly();
    updateStdMinMaxForCurrentUnit();
  }

  function ptResetAll(){
    show('#blk_part_time', false);

    // Hebdo
    ['mon','tue','wed','thu','fri','sat','sun'].forEach(k=>{
      const cb = document.getElementById('pt_'+k+'_on');
      const h  = document.getElementById('pt_'+k+'_hours');
      if (cb) cb.checked = false;
      if (h) { h.value=''; h.disabled = true; }
    });
    if ($('#pt_org_fixed'))  $('#pt_org_fixed').checked  = false;

    // Mensuel
    [1,2,3,4].forEach(i=>{
      const cb = document.getElementById('pt_w'+i+'_on');
      const h  = document.getElementById('pt_w'+i+'_hours');
      if (cb) cb.checked = false;
      if (h) { h.value=''; h.disabled = true; }
    });
    if ($('#pt_org_month'))  $('#pt_org_month').checked  = false;

    const outm = $('#pt_total_hours_month'); if (outm) outm.textContent = '0.0';
    const outw = $('#pt_total_hours');       if (outw) outw.textContent = '0.0';

    if ($('#pt_floor_hint')) show('#pt_floor_hint', false);
    const err = $('#std_err'); if (err) { err.innerHTML=''; err.style.display='none'; }
    setHiddenWeeklyValue('');
    ptSerialize();
  }

  // ---------- Logique dépliante ----------
  function onRegimeChange(){
    const regime = getRegime();

    // Nettoie un éventuel override précédent
    if (step && step.dataset) step.dataset.override = '';

    if (regime === 'temps_partiel'){
      // Masque les modalités temps complet ; affiche le bloc standard (champ commun)
      show('#wt_modalities', false);
      show('#blk_forfait_hours', false);
      show('#blk_forfait_days',  false);
      show('#blk_modalite_2',    false);
      show('#blk_standard',      true);

      const std = $('#weekly_hours_std');
      if (std){
        // Champ vierge, éditable, plafond figé (34,9 en hebdo), min=1 pour déclencher l’override
        std.removeAttribute('readonly');
        std.min = '1';
        std.max = '34.9';
        std.value = ''; // ✨ vide par défaut
        const err = ensureErrNode('std_err', std.parentElement);
        clearError(std, err);
        const hint = $('#pt_floor_hint'); if (hint) hint.style.display = 'none';
      }

      // Côté API on reste sur "35h" pour pointer le mode 'part_time'
      const r35 = $('#wt_35'); if (r35) r35.checked = true;

      // UI TP
      ptToggleUI();
      const commonBox = $('#pt_common_box') || $('#pt_flex_box'); if (commonBox) show(commonBox, true);

      // Recharges & validations
      refreshFromApi();
      validatePartTimeRequired();
      setStdHoursUnit( isPartTimeMonthly() ? 'month' : 'week' );
      updateStdMinMaxForCurrentUnit();

    } else if (regime === 'temps_complet'){
      // Ré‑affiche les modalités
      show('#wt_modalities', true);

      const std = $('#weekly_hours_std');
      if (std){
        // Standard 35h = valeur fixée à 35, non éditable
        setStdHoursUnit('week');
        std.setAttribute('readonly','');
        std.min = '35';
        std.max = '35';
        std.value = '35';
        const err = ensureErrNode('std_err', std.parentElement);
        clearError(std, err);
        const hint = $('#pt_floor_hint'); if (hint) hint.style.display = 'none';
        setHiddenWeeklyValue('');
      }

      // Si aucune modalité n’est cochée, force 35h par défaut
      if (!step.querySelector('input[name="work_time_mode"]:checked')) {
        const def = $('#wt_35');
        if (def) def.checked = true;
      }

      // Referme proprement le bloc temps partiel puis affiche la sous‑modalité choisie
      ptResetAll();
      onModeChange(); // gère le sous-bloc actif + charge bornes/hints

    } else {
      // Aucun choix
      show('#wt_modalities', false);
      show('#blk_standard', false);
      show('#blk_forfait_hours', false);
      show('#blk_forfait_days', false);
      show('#blk_modalite_2', false);
      ptResetAll();
    }

    renderRegimeConformity();
    document.dispatchEvent(new CustomEvent('eds:worktime_changed'));
  }

  function onModeChange(){
    const m   = getUiModeRaw();
    const reg = getRegime();

    // Affiche le sous‑bloc correspondant
    show('#blk_standard',      m === 'standard_35h');
    show('#blk_forfait_hours', m === 'forfait_hours');
    show('#blk_forfait_days',  m === 'forfait_days');
    show('#blk_modalite_2',    m === 'modalite_2');

    // Harmonise le champ standard
    const std = $('#weekly_hours_std');
    if (std && m === 'standard_35h'){
      if (reg === 'temps_complet'){
        setStdHoursUnit('week');
        std.setAttribute('readonly','');
        std.min = '35';
        std.max = '35';
        std.value = '35';
        const err = ensureErrNode('std_err', std.parentElement);
        clearError(std, err);
        const hint = $('#pt_floor_hint'); if (hint) hint.style.display = 'none';
      } else {
        // temps partiel + "35h" coché côté UI → champ éditable
        setStdHoursUnit( isPartTimeMonthly() ? 'month' : 'week' );
        std.removeAttribute('readonly');
        std.min = '1';
        std.max = isPartTimeMonthly() ? String(round1((lastBounds?.weekly_hours_max ?? 34.9) * (52/12))) : '34.9';
        if (std.value === '35') std.value = ''; // au cas où on venait de TC→TP
        const err = ensureErrNode('std_err', std.parentElement);
        clearError(std, err);
        const hint = $('#pt_floor_hint'); if (hint) hint.style.display = 'none';
      }
    }

    // Recharges / validations
    refreshFromApi();
    validatePartTimeRequired();

    // Notifie le reste de l'appli
    document.dispatchEvent(new CustomEvent('eds:worktime_changed'));
  }

  // ---------- Init (sûr & idempotent) ----------
  let _inited = false;
  function init(){
    if (_inited) return;
    step = document.querySelector('.step[data-step="5"]');
    if (!step) return;
    _inited = true;

    // Écouteurs directs
    $$('#reg_full, #reg_part').forEach(r => on(r, 'change', onRegimeChange));
    $$('#wt_35, #wt_fh_pay, #wt_fh_repos, #wt_fd, #wt_m2').forEach(r => on(r, 'change', onModeChange));

    on($('#weekly_hours_std'), 'input', ()=>{ validateStandard(); maybeShowPartTimeFloorHint(); validatePartTimeRequired(); document.dispatchEvent(new CustomEvent('eds:worktime_changed')); });
    on($('#weekly_hours_fh'), 'input',  ()=>{ validateFH();      document.dispatchEvent(new CustomEvent('eds:worktime_changed')); });
    on($('#weekly_hours_m2'), 'input',  ()=>{ validateM2();      document.dispatchEvent(new CustomEvent('eds:worktime_changed')); });
    on($('#forfait_days_per_year'), 'input', ()=>{ validateFJ(); document.dispatchEvent(new CustomEvent('eds:worktime_changed')); });

    // Délégation de secours
    on(step, 'change', (e)=>{
      const t = e.target;
      if (!t) return;
      if (t.name === 'work_time_regime') onRegimeChange();
      if (t.name === 'work_time_mode')   onModeChange();

      // Hebdo (jours)
      if (t.id && /^pt_(mon|tue|wed|thu|fri|sat|sun)_(on|hours)$/.test(t.id)){
        if (t.id.endsWith('_on'))    ptToggleUI();
        if (t.id.endsWith('_hours')) ptApplyTotalsToWeekly();
        validatePartTimeRequired();
      }

      // Mensuel (semaines 1→4)
      if (t.id && /^pt_w[1-4]_(on|hours)$/.test(t.id)){
        if (t.id.endsWith('_on'))    ptToggleUI();
        if (t.id.endsWith('_hours')) ptApplyTotalsToWeekly();
        validatePartTimeRequired();
      }

      if (t.id && ['pt_org_fixed','pt_org_month'].includes(t.id)) {
        ptToggleUI(); ptSerialize(); validatePartTimeRequired();
      }
    });

    // Temps partiel — écouteurs directs (hebdo)
    ['mon','tue','wed','thu','fri','sat','sun'].forEach(k=>{
      on($('#pt_'+k+'_on'),    'change', ()=>{ ptToggleUI(); ptApplyTotalsToWeekly(); });
      on($('#pt_'+k+'_hours'), 'input',  ()=>{ ptApplyTotalsToWeekly(); });
    });

    // Temps partiel — écouteurs directs (mensuel S1→S4)
    [1,2,3,4].forEach(i=>{
      on($('#pt_w'+i+'_on'),    'change', ()=>{ ptToggleUI(); ptApplyTotalsToWeekly(); });
      on($('#pt_w'+i+'_hours'), 'input',  ()=>{ ptApplyTotalsToWeekly(); });
    });

    // Cadre / coupures / modifs / priorité
    on($('#pt_flex_frame'),           'change', ()=> ptSerialize());
    on($('#pt_breaks_max'),           'input',  ()=> ptSerialize());
    on($('#pt_break_max_hours'),      'input',  ()=> ptSerialize());
    on($('#pt_break_counterparties'), 'input',  ()=> ptSerialize());
    on($('#pt_modif_reasons'),        'input',  ()=> ptSerialize());
    on($('#pt_modif_notice_days'),    'input',  ()=> ptSerialize());
    on($('#pt_modif_notice_unit'),    'change', ()=> ptSerialize());
    on($('#pt_priority_reply_days'),  'input',  ()=> ptSerialize());

    // Choix d’organisation (hebdo/mensuel)
    on($('#pt_org_fixed'),  'change', ()=>{ ptToggleUI(); ptSerialize(); validatePartTimeRequired(); });
    on($('#pt_org_month'),  'change', ()=>{ ptToggleUI(); ptSerialize(); validatePartTimeRequired(); });

    // État initial (rien d’ouvert tant que l’utilisateur n’a pas choisi)
    show('#wt_modalities', false);
    show('#blk_standard', false);
    show('#blk_forfait_hours', false);
    show('#blk_forfait_days', false);
    show('#blk_modalite_2', false);
    ptResetAll();

    // Bascule initiale du label (au cas où l'état serait restauré)
    setStdHoursUnit( isPartTimeMonthly() ? 'month' : 'week' );

    // Zoom & bandeaux visibles dès l’arrivée
    updateZoomSummary();
    refreshZoomByCategory();
    renderRegimeConformity();

    // Hook public
    window.EDS_WT = window.EDS_WT || {};
    window.EDS_WT.refresh   = refreshFromApi;
    window.EDS_WT.forceInit = init;
  }

  // Lance init selon l’état du DOM
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once:true });
  } else {
    init();
  }

})();
