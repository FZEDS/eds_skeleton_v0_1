// app/static/js/cdd.js — logique conditionnelle spécifique CDD (motif/terme/renouvellement)
(function(){
  'use strict';
  if (window._EDS_CDD_ATTACHED) return; // idempotent
  window._EDS_CDD_ATTACHED = true;

  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>Array.from(document.querySelectorAll(s));
  const ALLOW_IMPRECISE = new Set(['remplacement','saisonnier','usage']);

  function selectedReason(){
    return document.querySelector('input[name="cdd_reason"]:checked')?.value || '';
  }

  function toggleReason(){
    const val = selectedReason();
    const showRemp  = (val === 'remplacement');
    const showOther = (val === 'autre');
    const boxRemp   = $('#cdd_replacement_box');
    const boxOther  = $('#cdd_reason_other_box');
    if (boxRemp)  boxRemp.style.display  = showRemp  ? '' : 'none';
    if (boxOther) boxOther.style.display = showOther ? '' : 'none';

    // Restreindre l’accès au « sans terme précis » aux motifs admissibles
    try{
      const imp = $('#cdd_term_imprecise');
      const fix = $('#cdd_term_fixed');
      const allowed = ALLOW_IMPRECISE.has(val);
      if (imp){
        imp.disabled = !allowed;
        const wrap = imp.closest('.radio'); if (wrap) wrap.style.opacity = allowed ? '' : '0.6';
      }
      if (!allowed && imp?.checked && fix){
        fix.checked = true; fix.dispatchEvent(new Event('change'));
      }
    }catch(_){ /* noop */ }

    // Afficher le bloc contrôle licenciement éco si accroissement
    const acc = $('#cdd_acc_box');
    if (acc) acc.style.display = (val === 'accroissement') ? '' : 'none';

    updateHints(); updateEcoCheck();
  }

  function toggleTerm(){
    const k = document.querySelector('input[name="cdd_term_kind"]:checked')?.value || '';
    const fixed = (k === 'fixed');
    const boxFixed = $('#cdd_term_fixed_box');
    const boxImpr  = $('#cdd_term_imprecise_box');
    if (boxFixed) boxFixed.style.display = fixed ? '' : 'none';
    if (boxImpr)  boxImpr.style.display  = fixed ? 'none' : '';

    const end  = $('#contract_end');
    const minv = $('#cdd_min_duration_value');
    const ev   = $('#cdd_term_event');
    if (end)  { if (fixed) end.setAttribute('data-required','true'); else end.removeAttribute('data-required'); }
    if (minv) { if (!fixed) minv.setAttribute('data-required','true'); else minv.removeAttribute('data-required'); }
    if (ev)   { if (!fixed) ev.setAttribute('data-required','true'); else ev.removeAttribute('data-required'); }

    updateHints();
  }

  function toggleRenewable(){
    const chk = $('#cdd_renewable');
    const num = $('#cdd_renewals_max');
    if (!chk || !num) return;
    num.disabled = !chk.checked;
    if (!chk.checked) { num.value = '0'; }
    updateHints(); updateEcoCheck();
  }

  function updateHints(){
    // Durée maximale par motif
    try{
      const val = selectedReason();
      const node = $('#cdd_hint_duration_max');
      if (node){
        let html = '';
        if (val === 'remplacement'){
          html = '<strong>Durée maximale — Remplacement</strong><br>'+
                 'Général : <b>18 mois</b> (renouvellements inclus). Cas particuliers : '+
                 '<b>9 mois</b> si attente d’une embauche CDI ; <b>24 mois</b> si départ définitif avant suppression du poste ou mission à l’étranger. '+
                 '<small>Réf. L1242‑8, L1242‑2, L1242‑7.</small>';
        } else if (val === 'accroissement'){
          html = '<strong>Durée maximale — Accroissement temporaire</strong><br>'+
                 'Général : <b>18 mois</b>. Cas particuliers : <b>24 mois</b> pour une commande exceptionnelle à l’export (min. 6 mois) ou mission à l’étranger.';
        } else if (val === 'saisonnier'){
          html = '<strong>Durée — Emploi saisonnier</strong><br>'+
                 'Sans plafond générique en mois : la durée est liée à la <b>saison</b>. Le contrat peut être sans terme précis (événement : fin de saison).';
        } else if (val === 'usage'){
          html = '<strong>Durée — CDD d’usage</strong><br>'+
                 'Pas de plafond légal unique en mois ; contrat souvent sans terme précis, conforme aux usages du secteur (D1242‑1).';
        } else if (val === 'autre'){
          html = '<strong>Durée maximale</strong><br>'+
                 'À défaut de cas spécial, repère général : <b>18 mois</b> (renouvellements inclus).';
        }
        node.style.display = html ? 'block' : 'none';
        node.innerHTML = html || '';
      }
    }catch(_){ }

    // Carence (entre deux CDD)
    try{
      const val = selectedReason();
      const node = $('#cdd_carence_motif');
      if (node){
        let html = '';
        if (val){
          const generic = 'Règle générale (même poste) : délai de carence <b>= 1/3</b> de la durée du contrat (si > 14 jours) ou <b>= 1/2</b> (si ≤ 14 jours).';
          const exceptions = 'Pas de carence notamment pour les <b>CDD saisonniers</b>, les <b>CDD d’usage</b>, certains <b>remplacements</b> et cas prévus par accord.';
          html = `<strong>Carence entre deux CDD</strong><br>${generic}<br>${exceptions} <small>Réf. L1244‑3, L1244‑4.</small>`;
        }
        node.style.display = html ? 'block' : 'none';
        node.innerHTML = html || '';
      }
    }catch(_){ }

    // --- Overlay YAML CCN (serveur) : remplace dynamiquement les hints si disponibles ---
    try{
      const idccEl = document.getElementById('idcc');
      const idcc = idccEl ? parseInt(idccEl.value || '', 10) : null;
      const reason = selectedReason();
      if (reason){
        const q = new URLSearchParams({});
        if (idcc && !Number.isNaN(idcc)) q.append('idcc', String(idcc));
        q.append('reason', reason);
        fetch('/api/cdd/rules?'+q.toString())
          .then(r=>r.json())
          .then(js=>{
            if (!js) return;
            const ex = Array.isArray(js.explain) ? js.explain : [];
            const dur = ex.find(e => e.slot === 'step4.duration');
            const car = ex.find(e => e.slot === 'step4.carence');
            const ren = ex.find(e => e.slot === 'step4.renewals');
            const nodeDur = document.getElementById('cdd_hint_duration_max');
            const nodeCar = document.getElementById('cdd_carence_motif');
            const nodeRen = document.getElementById('cdd_hint_renewals');
            if (dur && nodeDur){ nodeDur.style.display='block'; nodeDur.innerHTML = dur.text; }
            if (car && nodeCar){ nodeCar.style.display='block'; nodeCar.innerHTML = car.text; }
            if (ren && nodeRen){ nodeRen.style.display='block'; nodeRen.innerHTML = ren.text; }

            // Suggestion de valeur pour cdd_renewals_max (sans bloquer l'override)
            try{
              const sug = Array.isArray(js.suggest) ? js.suggest : [];
              const val = sug.find(s => s.field === 'cdd_renewals_max')?.value;
              const chk = document.getElementById('cdd_renewable');
              const inp = document.getElementById('cdd_renewals_max');
              if (chk?.checked && inp && (inp.value==='' || inp.value==='0' || inp.value==null)){
                if (typeof val === 'number') inp.value = String(parseInt(val,10));
              }
            }catch(_){ }
          })
          .catch(()=>{});
      }
    }catch(_){ }
  }

  function step4El(){ return document.querySelector('.step[data-step="4"]'); }
  function setNextDisabled(disabled){
    try{ const btn = step4El()?.querySelector('[data-next]'); if (btn){ btn.disabled = !!disabled; btn.classList.toggle('disabled', !!disabled); } }catch(_){ }
  }

  function updateEcoCheck(){
    try{
      const isAcc = (selectedReason() === 'accroissement');
      const yes   = document.getElementById('cdd_eco_layoff_yes')?.checked;
      const notes = document.getElementById('cdd_eco_layoff_notes')?.value?.trim() || '';
      const warn  = document.getElementById('cdd_acc_warn');
      const key   = 'cdd_eco_layoff_recent_ui';
      window.EDS_NON_COMPLIANCES = window.EDS_NON_COMPLIANCES || new Map();
      if (!isAcc){
        window.EDS_NON_COMPLIANCES.delete(key);
        if (warn){ warn.style.display='none'; warn.innerHTML=''; }
        setNextDisabled(false);
        return;
      }
      if (yes){
        if (warn){
          warn.style.display='block';
          warn.innerHTML = '<strong>Interdiction présumée</strong> : un CDD pour accroissement d’activité est en principe interdit lorsqu’un licenciement économique est intervenu dans les 6 mois sur le même poste dans l’établissement, sauf exception prévue par accord (ex. PSE). Renseignez une justification le cas échéant.';
        }
        // Non-conformité (hard) côté UI
        window.EDS_NON_COMPLIANCES.set(key, {
          key,
          step: 4,
          field: 'cdd_eco_layoff_6m',
          severity: 'hard',
          message: 'Accroissement : licenciement économique ≤ 6 mois sur le poste — CDD en principe interdit (sauf exception via accord/PSE).',
          suggested: null,
        });
        // Laisser l’utilisateur continuer: on ne bloque pas définitivement, mais on affiche un bouton disabled tant qu’il n’override pas via l’overlay final
        setNextDisabled(false);
      } else {
        window.EDS_NON_COMPLIANCES.delete(key);
        if (warn){ warn.style.display='none'; warn.innerHTML=''; }
        setNextDisabled(false);
      }
    }catch(_){ }
  }

  function attach(){
    $$('input[name="cdd_reason"]').forEach(el=> el.addEventListener('change', toggleReason));
    $$('input[name="cdd_term_kind"]').forEach(el=> el.addEventListener('change', toggleTerm));
    $('#cdd_renewable')?.addEventListener('change', toggleRenewable);
    // Accroissement — écouteurs dédiés
    $('#cdd_eco_layoff_yes')?.addEventListener('change', updateEcoCheck);
    $('#cdd_eco_layoff_no')?.addEventListener('change', updateEcoCheck);
    $('#cdd_eco_layoff_notes')?.addEventListener('input', updateEcoCheck);
    toggleReason(); toggleTerm(); toggleRenewable();
    updateEcoCheck();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', attach);
  } else {
    attach();
  }
})();
