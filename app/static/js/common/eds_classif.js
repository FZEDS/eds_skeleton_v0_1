(function(){
  'use strict';
  if (window._EDS_CLASSIF_ATTACHED) return;
  window._EDS_CLASSIF_ATTACHED = true;

  const $  = (sel, root=document)=> root.querySelector(sel);
  const $$ = (sel, root=document)=> Array.from(root.querySelectorAll(sel));
  function classifStepRoot(){
    try{
      const el = document.getElementById('classif_pos_container')
             || document.getElementById('classif_cat_container')
             || document.getElementById('classif_questions')
             || document.getElementById('classif_coeff_container');
      const step = el ? el.closest('.step') : null;
      return step || document;
    }catch(_){ return document; }
  }

  function escapeHtml(str){
    return String(str||'').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  }

  function getIdcc(){
    const raw = document.getElementById('idcc')?.value || '';
    const n = parseInt(raw, 10);
    return Number.isNaN(n) ? null : n;
  }

  function getCtx(){ window.EDS_CTX = window.EDS_CTX || {}; return window.EDS_CTX; }

  function normalize(value){
    if (value === null || value === undefined) return null;
    const txt = String(value).trim();
    return txt ? txt.toUpperCase() : null;
  }

  function mapBackendCategory(schema, key){
    const mapping = schema?.meta?.mapping?.categorie_to_backend;
    if (mapping && typeof mapping === 'object' && !Array.isArray(mapping)){
      const target = mapping[key];
      if (typeof target === 'string' && target.trim()) return target;
    }
    return key === 'cadre' ? 'cadre' : 'non-cadre';
  }

  function buildPromptHtml(schema, question, currentValue){
    const id = `q_${question.id}`;
    const label = question.label || question.id;
    const prompt = question.prompt ? `<div class="text-small text-muted" style="margin:2px 0 4px">${escapeHtml(question.prompt)}</div>` : '';
    const help = question.help ? `<div class="text-small text-muted">${escapeHtml(question.help)}</div>` : '';
    const required = question.required ? ' required' : '';
    const placeholder = question.placeholder ? ` placeholder="${escapeHtml(question.placeholder)}"` : '';
    const reason = question.reason ? `<div class="text-small text-muted" style="margin-top:4px">${escapeHtml(question.reason)}</div>` : '';
    const current = currentValue != null ? String(currentValue) : '';

    const type = String(question.type || 'text').toLowerCase();
    if (type === 'enum'){
      const options = Array.isArray(question.options) ? question.options : [];
      const asVList = Array.isArray(schema?.meta?.ui?.vlist_for) && schema.meta.ui.vlist_for.includes(question.id);
      const asButtons = Array.isArray(schema?.meta?.ui?.buttons_for) && schema.meta.ui.buttons_for.includes(question.id);

      if (asVList){
        const radios = options.map((opt, idx) => {
          const cid = `q_${question.id}_${idx}`;
          const checked = current && String(opt.value) === current ? ' checked' : '';
          const tip = opt.tooltip ? `<span class=\"help\" title=\"${escapeHtml(opt.tooltip)}\">?</span>` : '';
          return `
            <div class=\"radio\">
              <input type=\"radio\" name=\"q_${escapeHtml(question.id)}\" id=\"${cid}\" data-qid=\"${escapeHtml(question.id)}\" value=\"${escapeHtml(opt.value)}\"${checked}>
              <label class=\"label\" for=\"${cid}\">${escapeHtml(opt.label || opt.value)}</label>
              ${tip}
            </div>`;
        }).join('');
        return `
          <div class=\"stack\">
            <span class=\"subtle-label\">${escapeHtml(label)}</span>
            ${prompt}
            <div class=\"vlist\">${radios}</div>
            ${help}${reason}
          </div>`;
      }

      if (asButtons){
        const buttons = options.map(opt => {
          const isActive = current && String(opt.value) === current ? ' is-active' : '';
          return `<button type=\"button\" class=\"btn-toggle${isActive}\" data-qid=\"${escapeHtml(question.id)}\" data-value=\"${escapeHtml(opt.value)}\">${escapeHtml(opt.label || opt.value)}</button>`;
        }).join('');
        return `
          <div class=\"stack\" data-qid=\"${escapeHtml(question.id)}\">
            <span class=\"subtle-label\">${escapeHtml(label)}</span>
            ${prompt}
            <div class=\"button-toggle\" data-qid=\"${escapeHtml(question.id)}\">${buttons}</div>
            ${help}${reason}
          </div>`;
      }

      const opts = ['<option value="">-- Choisir --</option>']
        .concat(options.map(opt => {
          const sel = current && String(opt.value) === current ? ' selected' : '';
          return `<option value=\"${escapeHtml(opt.value)}\"${sel}>${escapeHtml(opt.label || opt.value)}</option>`;
        }));
      return `
        <div class=\"stack\" data-qid=\"${escapeHtml(question.id)}\">
          <label for=\"${id}\">${escapeHtml(label)}</label>
          ${prompt}
          <select id=\"${id}\" data-qid=\"${escapeHtml(question.id)}\"${required}>${opts.join('')}</select>
          ${help}${reason}
        </div>`;
    }
    if (type === 'boolean'){
      return `
        <div class="stack" data-qid="${escapeHtml(question.id)}">
          <div class="line-check-right">
            <label for="${id}">${escapeHtml(label)}</label>
            <input id="${id}" type="checkbox" data-qid="${escapeHtml(question.id)}"${currentValue ? ' checked' : ''}${required}>
          </div>
          ${help}${reason}
        </div>`;
    }
    if (type === 'number'){
      const min = question.min != null ? ` min="${question.min}"` : '';
      const max = question.max != null ? ` max="${question.max}"` : '';
      const step = question.step != null ? ` step="${question.step}"` : '';
      return `
        <div class="stack" data-qid="${escapeHtml(question.id)}">
          <label for="${id}">${escapeHtml(label)}</label>
          ${prompt}
          <input id="${id}" type="number" data-qid="${escapeHtml(question.id)}"${min}${max}${step}${placeholder}${required}>
          ${help}${reason}
        </div>`;
    }
    const inputType = (type === 'date') ? 'date' : 'text';
    return `
      <div class="stack" data-qid="${escapeHtml(question.id)}">
        <label for="${id}">${escapeHtml(label)}</label>
        ${prompt}
        <input id="${id}" type="${inputType}" data-qid="${escapeHtml(question.id)}"${placeholder}${required}>
        ${help}${reason}
      </div>`;
  }

  function evalWhen(question, ctx){
    try{
      const when = question && question.when;
      if (!when) return true;
      if (when.equals){
        const { key, value } = when.equals;
        return ctx[key] === value;
      }
      if (when.in){
        const { key, values } = when.in;
        return Array.isArray(values) ? values.includes(ctx[key]) : false;
      }
      if (when.isset){
        const k = when.isset;
        return ctx[k] !== undefined && ctx[k] !== null && ctx[k] !== '';
      }
      if (Array.isArray(when.any)){
        return when.any.some(cond => evalWhen({ when: cond }, ctx));
      }
      if (Array.isArray(when.all)){
        return when.all.every(cond => evalWhen({ when: cond }, ctx));
      }
      return true;
    }catch(_){ return true; }
  }

  function visibleQuestions(schema){
    const all = Array.isArray(schema?.questions) ? schema.questions : [];
    const ctx = getCtx();
    return all.filter(q => evalWhen(q, ctx));
  }

  function renderQuestions(schema){
    const stepRoot = classifStepRoot();
    const wrapper = $( '#classif_questions', stepRoot);
    const box = $( '#classif_questions_box', stepRoot);
    if (!wrapper || !box){
      if (window.EDS_DEBUG) console.warn('EDS classif: questions container missing');
      return;
    }
    const questions = Array.isArray(schema?.questions) ? schema.questions : [];
    if (!questions.length){
      wrapper.style.display = 'none';
      box.innerHTML = '';
      return;
    }
    const ctx = getCtx();
    const list = visibleQuestions(schema);
    box.innerHTML = list.map(q => buildPromptHtml(schema, q, ctx[q.id])).join('');
    wrapper.style.display = list.length ? 'block' : 'none';

    Array.from(box.querySelectorAll('[data-qid]')).forEach(el =>{
      const qid = el.getAttribute('data-qid'); if (!qid) return;
      const tag = (el.tagName || '').toUpperCase();
      const type = (el.type || '').toLowerCase();
      if (tag === 'BUTTON'){
        const ctxVal = ctx[qid];
        if (ctxVal != null && String(ctxVal) === String(el.dataset.value)){
          el.classList.add('is-active');
        }
        el.addEventListener('click', ()=>{
          Array.from(box.querySelectorAll(`button[data-qid="${qid}"]`)).forEach(btn => btn.classList.remove('is-active'));
          el.classList.add('is-active');
          applyAnswer(schema, qid, el.dataset.value);
        });
      } else if (tag === 'SELECT'){
        if (ctx[qid] != null){ el.value = String(ctx[qid]); }
        el.addEventListener('change', ()=> applyAnswer(schema, qid, el.value));
      } else if (type === 'radio'){
        // Ne jamais écraser la valeur d'un input radio
        el.addEventListener('change', ()=> applyAnswer(schema, qid, el.value));
      } else if (type === 'checkbox'){
        if (ctx[qid] != null) el.checked = !!ctx[qid];
        el.addEventListener('change', ()=> applyAnswer(schema, qid, el.checked));
      } else {
        if (ctx[qid] != null) el.value = ctx[qid];
        el.addEventListener('input', ()=> applyAnswer(schema, qid, el.value));
        el.addEventListener('change', ()=> applyAnswer(schema, qid, el.value));
      }
    });
  }

  function applyAnswer(schema, qid, value){
    const ctx = getCtx();
    ctx[qid] = value;

    const question = (Array.isArray(schema?.questions) ? schema.questions : []).find(q => String(q.id) === String(qid));
    if (question && Array.isArray(question.writes)){
      question.writes.forEach(key => {
        ctx[key] = value;
        if (key === 'classification_level'){
          const hidden = document.getElementById('classification_level');
          if (hidden){ hidden.value = String(value||''); hidden.dispatchEvent(new Event('input', { bubbles: true })); }
        }
      });
    }

    if (qid === 'annexe'){
      try{
        const map = schema?.meta?.mapping?.categorie_to_backend || {};
        const cat = map && typeof map === 'object' ? map[value] : null;
        const hidden = document.getElementById('categorie');
        if (hidden && cat){ hidden.value = cat; hidden.dispatchEvent(new Event('change', { bubbles: true })); }
      }catch(_){ }
    }

    renderQuestions(schema);
    renderCoefficients(schema);
    document.dispatchEvent(new CustomEvent('eds:ctx_updated'));
  }

  function bestCoeffEntry(schema){
    const entries = Array.isArray(schema?.coeff_catalog) ? schema.coeff_catalog : [];
    if (!entries.length) return null;
    const ctx = getCtx();
    const annexe = normalize(ctx.annexe);
    if (!annexe) return null;
    const segment = normalize(ctx.segment);
    const statut = normalize(ctx.statut);

    let best = null;
    entries.forEach(entry => {
      const match = entry.match || {};
      const mAnnexe = normalize(match.annexe);
      const mSegment = normalize(match.segment);
      const mStatut = normalize(match.statut);

      let score = 0;
      if (mAnnexe){
        if (mAnnexe !== annexe) return;
        score += 5;
      }
      if (mSegment){
        if (!segment || mSegment !== segment) return;
        score += 3;
      } else if (segment){
        score += 0.5;
      }
      if (mStatut){
        if (!statut || mStatut !== statut) return;
        score += 1.5;
      } else if (statut){
        score += 0.2;
      }

      if (!best || score > best.score) best = { score, entry };
    });
    return best ? best.entry : null;
  }

  function ensureCoeffContainer(stepRoot){
    let block = $('#classif_coeff_block', stepRoot);
    let container = $('#classif_coeff_container', stepRoot);
    if (!block){
      block = document.createElement('div');
      block.id = 'classif_coeff_block';
      block.className = 'fieldset';
      block.style.marginTop = '10px';
      const title = document.createElement('h4');
      title.style.margin = '0 0 6px';
      title.textContent = 'Coefficient / groupe';
      block.appendChild(title);
      const helper = document.createElement('div');
      helper.className = 'muted';
      helper.style.marginTop = '2px';
      helper.style.marginBottom = '6px';
      helper.textContent = 'Sélectionnez le coefficient correspondant au poste. Les libellés résument la position conventionnelle.';
      block.appendChild(helper);
      const questions = $('#classif_questions', stepRoot);
      if (questions){
        questions.insertAdjacentElement('afterend', block);
      } else {
        const posCol = $('#classif_pos_container', stepRoot)?.parentElement;
        posCol?.appendChild(block);
      }
    }
    if (!container){
      container = document.createElement('div');
      container.id = 'classif_coeff_container';
      container.className = 'vlist';
      container.setAttribute('role','radiogroup');
      container.setAttribute('aria-label','Coefficient CCN');
      block.appendChild(container);
    }
    return { block, container };
  }

  function updateClassificationLevel(option){
    const ctx = getCtx();
    const parts = [];
    if (ctx.annexe) parts.push(`Annexe ${ctx.annexe}`);
    if (ctx.segment) parts.push(ctx.segment);
    if (ctx.statut) parts.push(ctx.statut);
    const descriptor = parts.length ? ` (${parts.join(' · ')})` : '';
    const text = (option?.label || option?.value || '') + descriptor;
    const hidden = document.getElementById('classification_level');
    if (hidden){ hidden.value = text; hidden.dispatchEvent(new Event('input', { bubbles: true })); }
  }

  function renderCoefficients(schema){
    const stepRoot = classifStepRoot();
    const entry = bestCoeffEntry(schema);
    const { block, container } = ensureCoeffContainer(stepRoot);

    if (!entry || !Array.isArray(entry.options) || !entry.options.length){
      container.innerHTML = '';
      block.style.display = 'none';
      const hidden = document.getElementById('coeff_value');
      if (hidden) hidden.value = '';
      delete getCtx().coeff;
      return;
    }

    const ctx = getCtx();
    const current = ctx.coeff || document.getElementById('coeff_value')?.value || '';
    container.innerHTML = '';

    entry.options.forEach(opt => {
      const id = `ccn_coeff_${opt.value}`;
      const row = document.createElement('div');
      row.className = 'radio';
      row.innerHTML = `
        <input type="radio" name="ccn_coeff_auto" id="${id}" value="${escapeHtml(opt.value)}">
        <label class="label" for="${id}">${escapeHtml(opt.label || opt.value)}</label>
        ${opt.tooltip ? `<span class="help" title="${escapeHtml(opt.tooltip)}">?</span>` : ''}`;
      container.appendChild(row);
      const input = row.querySelector('input');
      if (!input) return;
      if (current && String(current).toUpperCase() === String(opt.value).toUpperCase()){
        input.checked = true;
        updateClassificationLevel(opt);
      }
      input.addEventListener('change', ()=>{
        if (!input.checked) return;
        const hidden = document.getElementById('coeff_value');
        if (hidden){ hidden.value = String(opt.value); }
        ctx.coeff = opt.value;          // valeur telle quelle (peut être alphanumérique)
        ctx.coeff_key = opt.value;      // clé exacte choisie (pour les segments non numériques, ex. DEM)
        updateClassificationLevel(opt);
        document.dispatchEvent(new CustomEvent('eds:ctx_updated'));
      });
    });

    block.style.display = 'block';
    if (current && !ctx.coeff) ctx.coeff = current;
    const checked = container.querySelector('input[name="ccn_coeff_auto"]:checked');
    if (!checked){
      const first = container.querySelector('input[name="ccn_coeff_auto"]');
      if (first){
        first.checked = true;
        first.dispatchEvent(new Event('change'));
      }
    }
  }

  function renderSchema(schema){
    const stepRoot = classifStepRoot();
    const catBox = $('#classif_cat_container', stepRoot);
    const posBox = $('#classif_pos_container', stepRoot);
    const fallback = $('#classif_fallback', stepRoot);
    if (!catBox || !posBox) return;

    catBox.innerHTML = '';
    posBox.innerHTML = '';

    const cats = Array.isArray(schema?.categories) ? schema.categories : [];

    if (!cats.length){
      if (fallback) fallback.style.display = 'none';
      const catCol = catBox.parentElement; if (catCol) catCol.style.display = 'none';
      const posCol = posBox.parentElement; if (posCol) posCol.style.gridColumn = '1 / -1';
      ensureCoeffContainer(stepRoot); // prepare container
      return;
    }

    if (fallback) fallback.style.display = 'none';
    const catCol = catBox.parentElement; if (catCol) catCol.style.display = '';
    const posCol = posBox.parentElement; if (posCol) posCol.style.gridColumn = '';

    cats.forEach(cat => {
      const id = `syn_cat_${cat.key}`;
      const row = document.createElement('div');
      row.className = 'radio';
      row.innerHTML = `
        <input type="radio" name="syntec_cat" id="${id}" value="${escapeHtml(cat.key)}" data-cat-code="${escapeHtml(cat.cat_code || '')}">
        <label class="label" for="${id}">${escapeHtml(cat.label || cat.key)}</label>
        ${cat.tooltip ? `<span class="help" title="${escapeHtml(cat.tooltip)}">?</span>` : ''}`;
      catBox.appendChild(row);

      row.querySelector('input').addEventListener('change', e => {
        if (!e.target.checked) return;
        const mapped = mapBackendCategory(schema, cat.key);
        const hidden = document.getElementById('categorie');
        if (hidden){
          hidden.value = mapped;
          hidden.dispatchEvent(new Event('change'));
          hidden.dispatchEvent(new Event('input'));
        }
        renderPositions(schema, cat);
      });
    });

    const first = catBox.querySelector('input[name="syntec_cat"]');
    if (first){ first.checked = true; first.dispatchEvent(new Event('change')); }
  }

  function renderPositions(schema, category){
    const stepRoot = classifStepRoot();
    const posBox = $('#classif_pos_container', stepRoot);
    if (!posBox) return;
    posBox.innerHTML = '';

    const fmt = schema?.meta?.mapping?.classification_format || '{cat} Position {pos} — Coef {coeff}';
    const positions = Array.isArray(category?.positions) ? category.positions : [];

    positions.forEach(pos => {
      const id = `syn_pos_${category.key}_${pos.pos}_${pos.coeff}`;
      const label = pos.label || `${category.cat_code || ''} ${pos.pos || ''} — Coef ${pos.coeff || ''}`;
      const row = document.createElement('div');
      row.className = 'radio';
      row.innerHTML = `
        <input type="radio" name="syntec_pos" id="${id}" value="${escapeHtml(pos.coeff)}">
        <label class="label" for="${id}">${escapeHtml(label)}</label>
        ${pos.tooltip ? `<span class="help" title="${escapeHtml(pos.tooltip)}">?</span>` : ''}`;
      posBox.appendChild(row);

      row.querySelector('input').addEventListener('change', e => {
        if (!e.target.checked) return;
        const text = fmt
          .replace('{cat}', category.cat_code || '')
          .replace('{pos}', pos.pos || '')
          .replace('{coeff}', pos.coeff != null ? String(pos.coeff) : '')
          .replace('{text}', pos.label || '');
        const hidden = document.getElementById('classification_level');
        if (hidden){ hidden.value = text; hidden.dispatchEvent(new Event('input')); }
        if (window.EDS_SAL?.refresh) window.EDS_SAL.refresh();
        if (window.EDS_WT?.refresh)  window.EDS_WT.refresh();
      });
    });

    const first = posBox.querySelector('input[name="syntec_pos"]');
    if (first){ first.checked = true; first.dispatchEvent(new Event('change')); }
  }

  async function refresh(){
    let schema = {};
    try{
      const params = new URLSearchParams();
      const idcc = getIdcc();
      if (idcc) params.append('idcc', String(idcc));
      const res = await fetch('/api/classif/schema?' + params.toString());
      const json = await res.json();
      schema = json?.schema || {};
      LAST_SCHEMA = schema;
      if (window.EDS_DEBUG) console.debug('EDS classif schema', {
        idcc,
        keys: Object.keys(schema || {}),
        hasQuestions: Array.isArray(schema?.questions),
        categoriesLen: Array.isArray(schema?.categories) ? schema.categories.length : 'n/a'
      });
    }catch(e){
      schema = {};
      console.warn('EDS classif: schema fetch failed', e);
    }

    renderSchema(schema);
    renderQuestions(schema);
    renderCoefficients(schema);
  }

  window.EDS_CLASSIF = window.EDS_CLASSIF || {};
  window.EDS_CLASSIF.refresh = refresh;
  window.EDS_CLASSIF.renderQuestions = () => {
    try{
      const schema = LAST_SCHEMA || {};
      renderQuestions(schema);
      renderCoefficients(schema);
    }catch(e){ console.warn('EDS classif: renderQuestions failed', e); }
  };
  window.EDS_CLASSIF.renderCoefficients = () => {
    try{ renderCoefficients(LAST_SCHEMA || {}); }catch(e){ console.warn('EDS classif: renderCoefficients failed', e); }
  };

  let LAST_SCHEMA = null;

  document.addEventListener('DOMContentLoaded', refresh);
  const idccField = document.getElementById('idcc');
  idccField?.addEventListener('input', refresh);
  idccField?.addEventListener('change', refresh);
  document.addEventListener('eds:ctx_updated', () => {
    try{ renderCoefficients(LAST_SCHEMA || {}); }catch(e){ console.warn('EDS classif: ctx listener failed', e); }
  }, false);
})();
