// Étape 3 — CCN & AE (commun)

(function(){
  'use strict';
  if (window._EDS_CCN_AE_ATTACHED) return;
  window._EDS_CCN_AE_ATTACHED = true;

  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>Array.from(document.querySelectorAll(s));
  const on = (el, ev, fn)=> el && el.addEventListener(ev, fn, false);
  const callIf = (name, ...args)=>{
    const fn = (window && window[name]); if (typeof fn === 'function') return fn(...args);
  };

  /* ---------- Adhésion patronale (option B : info only) ---------- */
  function refreshAdhesionNote(){
    const val  = document.querySelector('input[name="adhesion_syndicat"]:checked')?.value;
    const note = $('#ccn_note');
    if (!note) { callIf('updateProgressUI'); return; }

    const htmlNon = `
      L’entreprise <strong>n’a pas adhéré</strong> à un syndicat employeur de la branche.
      <strong>Dans ce cas, seules les dispositions étendues</strong> par arrêté ministériel s’appliquent.
    `;
    const htmlOui = `
      L’entreprise <strong>adhère</strong> à une organisation patronale signataire.
      <strong>Des clauses non étendues peuvent s’appliquer en plus</strong> (ex. avenant minima en attente d’extension). <br>
      ⚠️ Le générateur applique par défaut les <strong>dispositions étendues</strong>. Vérifiez vos textes de branche
      et ajustez, si besoin, la rémunération/les clauses.
    `;

    if (val === 'oui') { note.innerHTML = htmlOui; note.style.display = 'block'; }
    else if (val === 'non') { note.innerHTML = htmlNon; note.style.display = 'block'; }
    else { note.style.display = 'none'; }

    callIf('updateProgressUI');
  }

  /* ---------- CCN : parsing/commit ---------- */
  function parseCCN(val){
    if(!val) return null;
    const m = /^\s*(\d{2,4})\b/.exec(String(val));
    return m ? parseInt(m[1],10) : null;
  }

  const idccHidden = $('#idcc');
  const ccnInput   = $('#ccn_search');
  const noCcn      = $('#no_ccn');
  let _lastCommittedIdcc = idccHidden?.value || '';

  function commitIdccIfChanged(newId){
    const newVal = (newId != null) ? String(newId) : '';
    if (String(_lastCommittedIdcc) === newVal) return; // pas de changement → pas de refresh
    if (idccHidden) {
      idccHidden.value = newVal;
      // Notifie les écouteurs (ex. eds_classif.js) qu'un nouvel IDCC est commité
      try {
        idccHidden.dispatchEvent(new Event('input', { bubbles: true }));
        idccHidden.dispatchEvent(new Event('change', { bubbles: true }));
      } catch(_){ /* noop */ }
    }
    _lastCommittedIdcc = newVal;

    // UI : si une CCN est saisie, décocher "Pas de CCN"
    if (noCcn && newVal) noCcn.checked = false;

    // Rafraîchis seulement quand l'IDCC est effectivement différent
    callIf('loadClassif');
    callIf('refreshAllThemes');
    callIf('refreshClausesCatalog');
    callIf('updateProgressUI');
  }

  function setIdccFromInput(){
    const parsed = parseCCN(ccnInput?.value || '');
    if (parsed != null) {
      // Un ID détecté → on commit
      commitIdccIfChanged(parsed);
    } else {
      // Pas d'ID dans le champ visible :
      // - si "Pas de CCN" est coché, on efface
      // - sinon on ne touche pas à l'idcc existant (ne pas l'écraser par vide)
      if (noCcn && noCcn.checked) {
        commitIdccIfChanged(null);
      }
    }
  }

  function refreshNoCcnUI(){
    const banner  = $('#no_ccn_banner');
    const checked = !!noCcn?.checked;
    if (banner) banner.style.display = checked ? 'block' : 'none';

    // accessibilité + anti-frappe parasite
    if (ccnInput){
      ccnInput.disabled = checked;
      ccnInput.setAttribute('aria-disabled', checked ? 'true':'false');
      if (checked) ccnInput.value = '';
    }

    // désactive les radios d’adhésion si "Pas de CCN"
    $$('input[name="adhesion_syndicat"]').forEach(r => r.disabled = checked);

    const note = $('#ccn_note');
    if (note && checked) note.style.display = 'none';
    if (!checked) refreshAdhesionNote();

    callIf('updateProgressUI');
  }

  function onCcnCommitted(){ setIdccFromInput(); }

  // --- Datalist dynamique (API /api/ccn/list) ---
  async function populateCcnDatalist(q=''){
    try{
      const url = q ? '/api/ccn/list?q='+encodeURIComponent(q) : '/api/ccn/list';
      const r = await fetch(url);
      const js = await r.json();
      const dl = $('#ccn-list'); if (!dl) return;
      dl.innerHTML = '';
      (js.items || []).forEach(it=>{
        const opt = document.createElement('option');
        opt.value = `${String(it.idcc).padStart(4,'0')} - ${it.label}`;
        dl.appendChild(opt);
      });
    }catch(e){
      if (window.EDS_DEBUG) console.warn('populateCcnDatalist failed', e);
    }
  }

  // petite déco pour ne pas spammer l'API au fil de la frappe
  let _ccnTimer = null;
  on(ccnInput, 'input', (e)=>{
    const v = (e.target.value || '').trim();
    if (_ccnTimer) window.clearTimeout(_ccnTimer);
    _ccnTimer = window.setTimeout(()=> populateCcnDatalist(v), 120);

    const typedId = parseCCN(v);
    if (typedId) commitIdccIfChanged(typedId);
  });

  on(ccnInput, 'blur', onCcnCommitted);
  on(ccnInput, 'change', onCcnCommitted);

  on(noCcn, 'change', ()=>{
    if(noCcn.checked){
      if(ccnInput) ccnInput.value='';
      commitIdccIfChanged(null);
    }
    refreshNoCcnUI();
  });

  $$('input[name="adhesion_syndicat"]').forEach(r=>{
    on(r, 'change', refreshAdhesionNote);
  });

  document.addEventListener('DOMContentLoaded', ()=>{
    populateCcnDatalist();
    refreshAdhesionNote();
    refreshNoCcnUI();
  }, { once:true });

  // Compat éventuelle
  window.EDS_CCN_AE = window.EDS_CCN_AE || {};
  // Restaure l'input visible (#ccn_search) à partir du hidden #idcc si nécessaire
  async function restoreCcnInputFromHidden(){
    const hid = idccHidden?.value || '';
    if (!ccnInput || !hid || ccnInput.value) return; // rien à faire
    try{
      // Essaye de récupérer le label via l'API pour afficher "NNNN - Libellé"
      const r = await fetch('/api/ccn/list?q=' + encodeURIComponent(hid));
      const js = await r.json();
      const items = js?.items || [];
      const match = items.find(it => String(it.idcc) === String(hid));
      if (match){
        ccnInput.value = `${String(match.idcc).padStart(4,'0')} - ${match.label}`;
      } else {
        ccnInput.value = String(hid).padStart(4,'0');
      }
    } catch(e){
      // fallback: au moins afficher l'ID
      ccnInput.value = String(hid).padStart(4,'0');
    }
  }

  window.EDS_CCN_AE.refresh = ()=>{ refreshAdhesionNote(); refreshNoCcnUI(); restoreCcnInputFromHidden(); };
  window.setIdccFromInput = setIdccFromInput;
  window.EDS_CCN_AE = window.EDS_CCN_AE || {};
  window.EDS_CCN_AE.commitFromInput = setIdccFromInput;

  /* ---------- AE (Accords d’entreprise) ---------- */
  (function(){
    if (window._EDS_CCN_AE_SUB_ATTACHED) return;
    window._EDS_CCN_AE_SUB_ATTACHED = true;

    function getCount(){ const n=parseInt($('#ae_count')?.value||'1',10); return (isNaN(n)?1:Math.max(1,Math.min(5,n))); }
    function isChecked(){ return !!$('#ae_exists')?.checked; }

    function snapshotCurrent(){
      const rows = $$('#ae_list .ae-row');
      const memo = {};
      rows.forEach(r=>{
        const idx = r.getAttribute('data-idx');
        memo['t'+idx] = $('#ae_title_'+idx)?.value || '';
        memo['d'+idx] = $('#ae_date_'+idx)?.value  || '';
      });
      return memo;
    }

    function renderRows(){
      const memo = snapshotCurrent();
      const target = $('#ae_list');
      if(!target) return;
      const count = getCount();

      let html = '';
      for(let i=1;i<=count;i++){
        const t = memo['t'+i] || '';
        const d = memo['d'+i] || '';
        html += `
          <div class="grid2 ae-row" data-idx="${i}" style="margin-bottom:8px">
            <div>
              <label>Liste des accords d’entreprise #${i}</label>
              <input id="ae_title_${i}" name="ae_title_${i}" placeholder="Intitulé ou objet (ex. Forfait‑jours, Durée du travail…)" value="${(t||'').replace(/"/g,'&quot;')}">
            </div>
            <div>
              <label>Date de l’accord</label>
              <input type="date" id="ae_date_${i}" name="ae_date_${i}" value="${d||''}">
            </div>
          </div>`;
      }
      target.innerHTML = html;

      $$('#ae_list input').forEach(inp => on(inp, 'input', serialize));
      serialize();
    }

    function serialize(){
      const exists = isChecked();
      const count  = getCount();
      const items  = [];
      for(let i=1;i<=count;i++){
        const title = ($('#ae_title_'+i)?.value || '').trim();
        const date  = ($('#ae_date_'+i)?.value  || '').trim();
        if (title || date) items.push({ title, date });
      }
      const payload = { exists, count, items };
      const hidden = $('#ae_json'); if (hidden) hidden.value = JSON.stringify(payload);
    }

    function toggleFields(){
      const onFlag = isChecked();
      const blk = $('#ae_fields');
      if (blk){ blk.style.display = onFlag ? 'block':'none'; }
      if (onFlag) renderRows(); else serialize();
    }

    function restore(){
      try{
        const raw = $('#ae_json')?.value || '';
        if(!raw) return;
        const js = JSON.parse(raw);
        if (js && typeof js === 'object'){
          if (js.exists) $('#ae_exists').checked = true;
          if (js.count)  $('#ae_count').value = String(Math.max(1,Math.min(5, parseInt(js.count,10) || 1)));
          toggleFields();
          if (Array.isArray(js.items)){
            setTimeout(()=>{
              js.items.slice(0,5).forEach((it,idx)=>{
                const i = idx+1;
                const t = $('#ae_title_'+i); const d = $('#ae_date_'+i);
                if (t) t.value = (it.title || '');
                if (d) d.value = (it.date  || '');
              });
              serialize();
            },0);
          }
        }
      }catch(e){ /* ignore */ }
    }

    on($('#ae_exists'), 'change', toggleFields);
    on($('#ae_count'),  'change', ()=>{ renderRows(); serialize(); });

    document.addEventListener('DOMContentLoaded', ()=>{
      toggleFields();
      restore();
    }, { once:true });
  })();

})();
