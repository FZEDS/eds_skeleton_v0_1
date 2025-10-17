// app/static/js/common/eds_clauses.js
// Catalog + selection + params + custom clauses + serialization
// Usage:
//   window.EDS_CLAUSES.init();
//   window.EDS_CLAUSES.refresh();
(function(){
  'use strict';
  if (window.EDS_CLAUSES) return;

  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>Array.from(document.querySelectorAll(s));

  function ensureHidden(name){
    let el = document.getElementById(name);
    if (!el){
      el = document.createElement('input');
      el.type = 'hidden';
      el.id = name; el.name = name;
      document.body.appendChild(el);
    }
    return el;
  }

  function escapeHtml(str){
    return String(str||'').replace(/[&<>"']/g, m => (
      {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]
    ));
  }
  function escapeAttr(str){ return String(str||'').replace(/"/g,'&quot;'); }

  const state = {
    opts: {
      catalogContainerSelector: '#clauses_catalog',
      customListSelector: '#custom_clauses_list',
      hiddenSelectedSelector: '#clauses_selected_json',
      hiddenCustomSelector:   '#clauses_custom_json',
      hiddenParamsSelector:   '#clauses_params_json',
      addCustomBtnSelector:   '#btn_add_custom_clause',
      autoIncludeByFlag:      true,
    },
    items: [],
    selected: new Set(),
    paramsByKey: {},      // { key: {param: value, param__label: '...'} }
    customClauses: [],    // [{title, text}]
    requiredKeys: new Set(), // CCN defaults.auto_include (verrouillés)
    attached: false,
  };

  function hiddenSelected(){ return $(state.opts.hiddenSelectedSelector) || ensureHidden(state.opts.hiddenSelectedSelector.replace('#','')); }
  function hiddenCustom(){   return $(state.opts.hiddenCustomSelector)   || ensureHidden(state.opts.hiddenCustomSelector.replace('#','')); }
  function hiddenParams(){   return $(state.opts.hiddenParamsSelector)   || ensureHidden(state.opts.hiddenParamsSelector.replace('#','')); }

  function loadContext(){
    const ctx = {};
    try{ const v = parseInt($('#idcc')?.value || '',10); ctx.idcc = Number.isNaN(v)?null:v; }catch(_){ ctx.idcc = null; }
    ctx.doc = (window.EDS_DOC || 'cdi');
    return ctx;
  }

  async function fetchCatalog(){
    const ctx = loadContext();
    const q = new URLSearchParams({ doc: String(ctx.doc||'cdi') });
    if (ctx.idcc) q.append('idcc', String(ctx.idcc));
    // Contexte additionnel (si disponible) pour filtrer les clauses (when: ...)
    try {
      let wtm = null;
      if (typeof window.getWorkTimeModeForApi === 'function') {
        wtm = window.getWorkTimeModeForApi();
      }
      if (!wtm) {
        const el = document.querySelector('input[name="work_time_mode"]:checked');
        if (el && el.value) wtm = el.value;
      }
      if (wtm) q.append('work_time_mode', String(wtm));
    } catch(_){ /* noop */ }
    try {
      const UX = (window.EDS_CTX || {});
      if (UX.annexe)  q.append('annexe', String(UX.annexe));
      if (UX.segment) q.append('segment', String(UX.segment));
      if (UX.statut)  q.append('statut', String(UX.statut));
      if (UX.coeff_key) q.append('coeff', String(UX.coeff_key));
    } catch(_){ /* noop */ }
    const r = await fetch('/api/clauses/catalog?'+q.toString());
    const js = await r.json();
    const items = Array.isArray(js?.items) ? js.items : (Array.isArray(js) ? js : []);
    const req = js?.required_keys || js?.requiredKeys || [];
    try{ state.requiredKeys = new Set(Array.isArray(req) ? req : []); }catch(_){ state.requiredKeys = new Set(); }
    return items;
  }

  function renderParamControl(spec, key){
    const pid = `cp_${key}__${spec.key}`;
    const required = spec.required ? ' data-required="true" ' : '';
    const common = ` data-param="${escapeAttr(spec.key)}" data-ptype="${escapeAttr(spec.type||'text')}" ${required}`;
    const help = spec.help ? `<div class="text-small text-muted" style="margin-top:4px">${escapeHtml(spec.help)}</div>` : '';
    const value = state.paramsByKey[key]?.[spec.key] ?? spec.default ?? '';

    switch ((spec.type||'text').toLowerCase()){
      case 'number': case 'money': case 'percent':
        return `
          <div>
            <label for="${pid}">${escapeHtml(spec.label||spec.key)}${spec.required?' *':''}</label>
            <input id="${pid}" type="number" step="${spec.step||'0.01'}" placeholder="${escapeAttr(spec.placeholder||'')}" value="${escapeAttr(value)}" ${common}>
            ${help}
          </div>`;
      case 'enum': {
        const opts = (spec.options||[]).map(o=>{
          const sel = (String(value) === String(o.value)) ? ' selected' : '';
          return `<option value="${escapeAttr(o.value)}"${sel}>${escapeHtml(o.label||String(o.value))}</option>`;
        }).join('');
        return `
          <div>
            <label for="${pid}">${escapeHtml(spec.label||spec.key)}${spec.required?' *':''}</label>
            <select id="${pid}" ${common}>
              <option value="">—</option>
              ${opts}
            </select>
            ${help}
          </div>`;
      }
      case 'boolean':
        return `
          <div class="line-check-right">
            <label class="nowrap" for="${pid}">${escapeHtml(spec.label||spec.key)}${spec.required?' *':''}</label>
            <input id="${pid}" type="checkbox" ${common} ${value ? 'checked':''}>
          </div>
          ${help ? `<div class="text-small text-muted" style="margin-top:4px">${escapeHtml(spec.help)}</div>` : ''}`;
      default:
        return `
          <div>
            <label for="${pid}">${escapeHtml(spec.label||spec.key)}${spec.required?' *':''}</label>
            <input id="${pid}" type="text" placeholder="${escapeAttr(spec.placeholder||'')}" value="${escapeAttr(value)}" ${common}>
            ${help}
          </div>`;
    }
  }

  function getParamInputsForKey(key){
    return Array.from(document.querySelectorAll(`#clp_${CSS.escape(key)} [data-param]`));
  }
  function collectParamsForKey(key){
    const inputs = getParamInputsForKey(key);
    if (!inputs.length) return {};
    const out = {};
    inputs.forEach(el=>{
      const pkey = el.dataset.param;
      const ptype = (el.dataset.ptype||'text').toLowerCase();
      if (!pkey) return;
      let val = null;
      if (ptype === 'boolean'){
        val = !!el.checked;
      } else if (ptype === 'number' || ptype === 'money' || ptype === 'percent'){
        const n = parseFloat(String(el.value||'').replace(',', '.'));
        val = Number.isNaN(n) ? null : n;
      } else {
        val = (el.value || '').trim();
      }
      out[pkey] = val;
      if (ptype === 'enum'){
        const opt = el.options?.[el.selectedIndex];
        if (opt) out[pkey+'__label'] = (opt.text || '').trim();
      }
    });
    state.paramsByKey[key] = out;
    return out;
  }

  function restoreParamsForKey(key){
    const saved = state.paramsByKey[key] || {};
    getParamInputsForKey(key).forEach(el=>{
      const pkey = el.dataset.param;
      const ptype = (el.dataset.ptype||'text').toLowerCase();
      if (!(pkey in saved)) return;
      if (ptype === 'boolean') el.checked = !!saved[pkey];
      else el.value = (saved[pkey] ?? '');
    });
  }

  function renderParamsBlock(it){
    if (!Array.isArray(it.params) || !it.params.length) return '';
    const rows = it.params.map(p => renderParamControl(p, it.key)).join('');
    return `
      <div class="clause-params" id="clp_${it.key}" style="display:none;margin-top:8px;border:1px dashed #cbd5e1;border-radius:8px;padding:10px;background:#f9fafb">
        <div class="text-small" style="font-weight:700;margin-bottom:6px">Paramètres de cette clause</div>
        <div class="grid2">${rows}</div>
      </div>`;
  }

  function renderClauseFlags(flags){
    if (!flags) return '';
    const xs = [];
    if (flags.sensitive) xs.push('⚠️ clause sensible');
    if (flags.needs_parameters) xs.push('⚠️ paramètres à adapter');
    return xs.length ? `<div class="clause-flags">${xs.join(' · ')}</div>` : '';
  }

  function toggleParamsVisibility(item, cb){
    const box = document.getElementById('clp_'+item.key);
    if (!box) return;
    const show = !!(cb && cb.checked);
    box.style.display = show ? 'block' : 'none';
    if (show) restoreParamsForKey(item.key);
  }

  function serialize(){
    const sel = hiddenSelected();
    const cus = hiddenCustom();
    const par = hiddenParams();
    if (sel) sel.value = JSON.stringify(Array.from(state.selected));
    if (cus) cus.value = JSON.stringify(state.customClauses.filter(c => (c.title||c.text)));
    const out = {};
    state.selected.forEach(k=>{
      const p = collectParamsForKey(k);
      if (p && Object.keys(p).length) out[k] = p;
    });
    par.value = JSON.stringify(out);
  }

  function bindParamInputs(item){
    getParamInputsForKey(item.key).forEach(el=>{
      el.addEventListener('input', serialize);
      el.addEventListener('change', serialize);
    });
  }

  function renderCatalog(items){
    const box = $(state.opts.catalogContainerSelector); if (!box) return;
    state.items = Array.isArray(items) ? items : [];
    box.innerHTML = '';

    if (!state.items.length){
      box.innerHTML = `<div class="callout-muted">Aucune clause disponible pour le moment.</div>`;
      return;
    }

    // Restore state
    try{
      const selRaw = hiddenSelected()?.value || '[]';
      const sel = JSON.parse(selRaw);
      if (Array.isArray(sel)) { state.selected.clear(); sel.forEach(k=>state.selected.add(k)); }
      const pRaw = hiddenParams()?.value || '{}';
      const pObj = JSON.parse(pRaw);
      if (pObj && typeof pObj === 'object') state.paramsByKey = pObj;
    }catch(_){ }

    // Group CCN vs autres
    const ccnItems = state.items.filter(it => (it.group||'common') === 'ccn');
    const genItems = state.items.filter(it => (it.group||'common') !== 'ccn');
    const appendSection = (title)=>{
      const section = document.createElement('div');
      section.className = 'fieldset';
      section.innerHTML = `<h4 style="margin:0 0 6px">${escapeHtml(title)}</h4>`;
      box.appendChild(section);
      return section;
    };
    const secCcn = ccnItems.length ? appendSection('Clauses conventionnelles (CCN)') : null;
    const secGen = genItems.length ? appendSection('Clauses contractuelles (modèles personnalisables)') : null;

    function addItem(section, it){
      const id = `cl_${it.key}`;
      const required = state.requiredKeys.has(it.key);
      const checked = required || state.selected.has(it.key);
      const flags = renderClauseFlags(it.flags||{});
      const params = renderParamsBlock(it);
      const badge = required ? '<span style="margin-left:6px;font-size:12px;color:#374151;background:#e5e7eb;padding:1px 6px;border-radius:4px">obligatoire (CCN)</span>' : '';
      const disAttr = required ? ' disabled' : '';
      const itemHtml = `
        <div class="clause-item" data-key="${escapeAttr(it.key)}" style="border:1px solid #e5e7eb;border-radius:8px;padding:10px;margin:6px 0">
          <div class="line-check-right">
            <label class="nowrap" for="${id}">${escapeHtml(it.label||it.key)}${badge}</label>
            <input id="${id}" type="checkbox" data-key="${escapeAttr(it.key)}" ${checked?'checked':''}${disAttr}>
          </div>
          ${flags}
          ${it.synopsis ? `<div class="text-muted" style="margin:4px 0">${escapeHtml(it.synopsis)}</div>`:''}
          ${it.learn_more_html ? `<details class="muted" style="margin-top:4px"><summary>En savoir plus</summary><div class="mt-6">${it.learn_more_html}</div></details>`:''}
          ${params}
        </div>`;
      const wrap = document.createElement('div');
      wrap.innerHTML = itemHtml;
      section.appendChild(wrap.firstElementChild);
      const cb = section.querySelector(`#${CSS.escape(id)}`);
      if (cb){
        cb.addEventListener('change', ()=>{
          if (cb.checked) state.selected.add(it.key); else state.selected.delete(it.key);
          toggleParamsVisibility(it, cb);
          serialize();
        });
        toggleParamsVisibility(it, cb);
      }
      if (required && !state.selected.has(it.key)){
        state.selected.add(it.key);
      }
      bindParamInputs(it);
    }

    ccnItems.forEach(it => addItem(secCcn || box, it));
    genItems.forEach(it => addItem(secGen || box, it));

    // Auto‑sélection par flags (si demandé)
    if (state.opts.autoIncludeByFlag){
      let changed = false;
      state.items.forEach(it => {
        if (it.flags && it.flags.auto_include && !state.selected.has(it.key)){
          state.selected.add(it.key); changed = true;
        }
      });
      if (changed) serialize();
    }
    // S'assurer que les clés requises sont bien sérialisées
    serialize();
  }

  function renderCustomClauses(){
    const box = $(state.opts.customListSelector); if (!box) return;
    box.innerHTML = '';
    if (!state.customClauses.length){
      box.innerHTML = '<div class="muted">Aucune clause spécifique ajoutée.</div>';
      return;
    }
    state.customClauses.forEach((c, idx)=>{
      const row = document.createElement('div');
      row.className = 'custom-clause';
      row.innerHTML = `
        <div class="grid2" style="gap:8px;margin:8px 0">
          <div><input data-field="title" placeholder="Titre" value="${escapeAttr(c.title||'')}"></div>
          <div class="right"><button type="button" class="btn remove" data-idx="${idx}">Supprimer</button></div>
        </div>
        <div><textarea data-field="text" rows="3" placeholder="Contenu">${escapeHtml(c.text||'')}</textarea></div>`;
      box.appendChild(row);
    });
    // Bind
    $$(state.opts.customListSelector + ' input[data-field], ' + state.opts.customListSelector + ' textarea[data-field]').forEach(el=>{
      el.addEventListener('input', ()=>{
        const item = el.closest('.custom-clause');
        const idx = Array.from(box.querySelectorAll('.custom-clause')).indexOf(item);
        if (idx>=0){
          const title = item.querySelector('input[data-field="title"]').value;
          const text  = item.querySelector('textarea[data-field="text"]').value;
          state.customClauses[idx] = { title, text };
          serialize();
        }
      });
    });
    $$(state.opts.customListSelector + ' .remove').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        const idx = parseInt(btn.getAttribute('data-idx')||'-1',10);
        if (idx>=0){ state.customClauses.splice(idx,1); renderCustomClauses(); serialize(); }
      });
    });
  }

  function addCustomClause(){
    state.customClauses.push({ title: '', text: '' });
    renderCustomClauses();
    serialize();
  }

  function restoreCustom(){
    try{
      const raw = hiddenCustom()?.value || '[]';
      const arr = JSON.parse(raw);
      if (Array.isArray(arr)) state.customClauses = arr.slice(0, 20);
    }catch(_){ state.customClauses = []; }
  }

  async function refresh(){
    try{
      const items = await fetchCatalog();
      renderCatalog(items);
      restoreCustom();
      renderCustomClauses();
      serialize();
    }catch(e){
      const box = $(state.opts.catalogContainerSelector);
      if (box){ box.innerHTML = `<div class="muted">Échec du chargement des clauses.</div>`; }
      if (window.EDS_DEBUG) console.warn('clauses catalog failed', e);
    }
  }

  function attach(){
    if (state.attached) return;
    state.attached = true;
    hiddenSelected(); hiddenCustom(); hiddenParams();
    const btn = $(state.opts.addCustomBtnSelector);
    if (btn){ btn.addEventListener('click', addCustomClause); }
    // Refresh catalog when context changes (IDCC, classif...)
    document.addEventListener('eds:ctx_updated', ()=>{ refresh().catch(()=>{}); }, false);
  }

  window.EDS_CLAUSES = {
    init(opts){ state.opts = Object.assign({}, state.opts, (opts||{})); attach(); },
    refresh,
    serialize,
    addCustomClause,
    getSelected(){ return Array.from(state.selected); },
    setSelected(keys){ state.selected = new Set(Array.isArray(keys)?keys:[]); serialize(); },
    setParamsForKey(key, params){ state.paramsByKey[key] = params||{}; serialize(); },
  };
})();
