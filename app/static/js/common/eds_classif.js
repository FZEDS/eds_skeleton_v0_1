(function(){
  'use strict';
  if (window._EDS_CLASSIF_ATTACHED) return;
  window._EDS_CLASSIF_ATTACHED = true;

  const $  = (s)=>document.querySelector(s);
  const $$ = (s)=>Array.from(document.querySelectorAll(s));
  const escapeHtml = (str)=> String(str||'').replace(/[&<>"']/g, m => (
    {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]
  ));

  function getIdcc(){
    const v = parseInt($('#idcc')?.value || '', 10);
    return Number.isNaN(v) ? null : v;
  }

  function mapBackendCategory(schema, key){
    const mapping = schema?.meta?.mapping?.categorie_to_backend;
    // si c'est un objet {cadre: "cadre", agent: "non-cadre", ...}
    if (mapping && typeof mapping === 'object' && !Array.isArray(mapping)) {
      const val = mapping[key];
      if (typeof val === 'string' && val.trim()) return val;
    }
    // fallback sûr
    return key === 'cadre' ? 'cadre' : 'non-cadre';
  }

  function formatTemplate(schema){
    const fmt = schema?.meta?.mapping?.classification_format;
    return (typeof fmt === 'string' && fmt.trim())
      ? fmt
      : '{cat} Position {pos} — Coef {coeff}';
  }

  function renderPositions(schema, cat){
    const posBox = $('#classif_pos_container');
    if(!posBox) return;
    posBox.innerHTML = '';

    const fmt = formatTemplate(schema);
    const positions = Array.isArray(cat?.positions) ? cat.positions : [];
    positions.forEach(p=>{
      const id = `syn_pos_${cat.key}_${p.pos}_${p.coeff}`;
      const labelText = p.label || `${cat.cat_code || ''} ${p.pos || ''} — Coef ${p.coeff || ''}`;
      const row = document.createElement('div');
      row.className = 'radio';
      row.innerHTML =
        `<input type="radio" name="syntec_pos" id="${id}" value="${p.coeff}">
         <label class="label" for="${id}">${escapeHtml(labelText)}</label>
         ${p.tooltip ? `<span class="help" title="${escapeHtml(p.tooltip)}">?</span>` : ''}`;
      posBox.appendChild(row);

      row.querySelector('input').addEventListener('change', (e)=>{
        if(!e.target.checked) return;
        const text = fmt
          .replace('{cat}',   cat.cat_code || '')
          .replace('{pos}',   p.pos || '')
          .replace('{coeff}', (p.coeff!=null ? String(p.coeff) : ''))
          .replace('{text}',  p.label || '');

        const cl = $('#classification_level');
        if (cl){
          cl.value = text;
          // Déclenche les autres thèmes (salaire, essai, préavis) déjà branchés sur cet event
          cl.dispatchEvent(new Event('input'));
        }
        // En bonus, on peut rafraîchir le temps de travail / salaire si exposés globalement
        if (window.EDS_SAL?.refresh) window.EDS_SAL.refresh();
        if (window.EDS_WT?.refresh)  window.EDS_WT.refresh();
      });
    });

    // Pré‑sélectionne la première position
    const first = posBox.querySelector('input[name="syntec_pos"]');
    if (first) { first.checked = true; first.dispatchEvent(new Event('change')); }
  }

  function renderSchema(schema){
    const catBox = $('#classif_cat_container');
    const posBox = $('#classif_pos_container');
    const fb     = $('#classif_fallback');
    if (!catBox || !posBox) return;

    catBox.innerHTML = '';
    posBox.innerHTML = '';

    const cats = Array.isArray(schema?.categories) ? schema.categories : [];

    if (!cats.length){
      if (fb){
        fb.style.display = 'block';
        // Fallback handlers (saisie libre)
        const fbCat = $('#fallback_cat');
        const catHidden = $('#categorie');
        fbCat?.addEventListener('change', (e)=>{
          if (catHidden){ catHidden.value = e.target.value; catHidden.dispatchEvent(new Event('change')); }
        });

        const fbLevel = $('#fallback_level');
        const cl = $('#classification_level');
        fbLevel?.addEventListener('input', (e)=>{
          if (cl){ cl.value = e.target.value; cl.dispatchEvent(new Event('input')); }
        });
      }
      return;
    }
    if (fb) fb.style.display = 'none';

    // Catégories (radios)
    cats.forEach(c=>{
      const id = `syn_cat_${c.key}`;
      const row = document.createElement('div');
      row.className = 'radio';
      row.innerHTML =
        `<input type="radio" name="syntec_cat" id="${id}" value="${c.key}" data-cat-code="${c.cat_code || ''}">
         <label class="label" for="${id}">${escapeHtml(c.label || c.key)}</label>
         ${c.tooltip ? `<span class="help" title="${escapeHtml(c.tooltip)}">?</span>` : ''}`;
      catBox.appendChild(row);

      row.querySelector('input').addEventListener('change', (e)=>{
        if(!e.target.checked) return;
        // Map “front → backend” (cadre/non‑cadre)
        const backVal = mapBackendCategory(schema, c.key);
        const catHidden = $('#categorie');
        if (catHidden){
          catHidden.value = backVal;
          catHidden.dispatchEvent(new Event('change'));
          catHidden.dispatchEvent(new Event('input')); // progression
        }
        renderPositions(schema, c);
      });
    });

    // Pré‑sélectionne la 1ère catégorie
    const first = catBox.querySelector('input[name="syntec_cat"]');
    if (first){ first.checked = true; first.dispatchEvent(new Event('change')); }
  }

  async function refresh(){
    let schema = {};
    try{
      const q = new URLSearchParams();
      const idcc = getIdcc();
      if (idcc) q.append('idcc', String(idcc));
      const r = await fetch('/api/classif/schema?'+q.toString());
      const js = await r.json();
      schema = js?.schema || {};
    }catch(e){
      schema = {};
      if (window.EDS_DEBUG) console.warn('classif/schema failed', e);
    }
    renderSchema(schema);
  }

  // Expose & listeners
  window.EDS_CLASSIF = window.EDS_CLASSIF || {};
  window.EDS_CLASSIF.refresh = refresh;

  document.addEventListener('DOMContentLoaded', refresh);
  $('#idcc')?.addEventListener('input', refresh);
  $('#idcc')?.addEventListener('change', refresh);
})();
