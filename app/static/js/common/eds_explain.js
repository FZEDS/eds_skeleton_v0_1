// app/static/js/common/eds_explain.js
// Factorised rendering of backend explain[] hints into UI slots.
// Provides:
//   - window.renderExplain(items)
//   - window.EDS_EXPLAIN.configureTargets(map)
//   - window.SLOT_TARGETS (merged defaults + custom)
(function(){
  'use strict';
  if (window._EDS_EXPLAIN_ATTACHED) return;
  window._EDS_EXPLAIN_ATTACHED = true;

  const DEFAULT_SLOT_TARGETS = {
    'step4.header':            '#step4_header_card',
    'step5.header':            '#slot_step5_header',
    'step5.footer':            '#worktime_card',
    'step5.block.fh':          '#fh_card',
    'step5.block.fd':          '#fd_guard',
    'step5.block.m2':          '#m2_card',
    'step6.footer':            '#salary_card',
    'step6.more.minima':       '#salary_more_minima_body',
    'step6.more.ccn_primes':   '#salary_more_primes_body',
    'step7.card':              '#probation_zoom_body',
    'step7.prior':             '#essai_prior',
    'step7.renewal':           '#essai_renewal',
    'step8.card':              '#notice_card',
    'step8.conges':            '#cp_card',
    'step10.card':             '#cp_card',
  };

  function mergeSlotTargets(base, extra){
    const out = Object.assign({}, base || {});
    if (extra && typeof extra === 'object'){
      Object.keys(extra).forEach(k => { if (extra[k]) out[k] = extra[k]; });
    }
    return out;
  }

  // Install defaults once (non-destructive)
  window.SLOT_TARGETS = mergeSlotTargets(DEFAULT_SLOT_TARGETS, window.SLOT_TARGETS);

  function clearSlot(sel){
    const node = (typeof sel === 'string') ? document.querySelector(sel) : sel;
    if(!node) return;
    node.innerHTML = '';
    node.style.display = 'none';
    node.classList.remove('callout-info','callout-ccn','callout-warn');
    if (!node.classList.contains('callout')) node.classList.add('callout');
  }

  function renderExplain(explainItems){
    // Clean the common Step 5 slots prior to rendering, to prevent stale hints
    [
      '#slot_step5_header', '#worktime_card', '#fh_card', '#fd_guard', '#fd_info', '#m2_card', '#mod_card',
      '#pt_header', '#pt_fixed_card', '#pt_flex_card', '#pt_coupures_card', '#pt_modif_card'
    ].forEach(sel=> clearSlot(sel));

    if(!Array.isArray(explainItems) || explainItems.length===0) return;

    const bySlot = new Map();
    explainItems.forEach(it=>{
      const slot = it.slot || 'step5.footer';
      if(!bySlot.has(slot)) bySlot.set(slot, []);
      const k = String(it.kind || 'info').toLowerCase();
      it._kind = (k==='guard'?'warn':k);
      bySlot.get(slot).push(it);
    });

    const rank = k => (k==='warn'?3 : (k==='ccn'?2 : 1));

    const escapeHtml = (str)=> String(str||'').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
    const renderRich = (raw)=>{
      const s = String(raw||'');
      const lines = s.split('\n');
      let html = '';
      let ul = [];
      const pushUl = ()=>{ if (ul.length){ html += '<ul>'+ul.map(x=>`<li>${escapeHtml(x)}</li>`).join('')+'</ul>'; ul = []; } };
      lines.forEach(line=>{
        const t = line.trim();
        if (t.startsWith('- ')){
          ul.push(t.slice(2));
        } else {
          pushUl();
          html += escapeHtml(t) + '<br>';
        }
      });
      pushUl();
      if (html.endsWith('<br>')) html = html.slice(0,-4);
      return html;
    };

    bySlot.forEach((items, slot)=>{
      const targetSel = (window.SLOT_TARGETS && window.SLOT_TARGETS[slot]);
      if(!targetSel) return;
      const node = document.querySelector(targetSel);
      if(!node) return;

      node.classList.add('callout');
      node.classList.remove('callout-info','callout-ccn','callout-warn');
      const variant = items.map(x=>x._kind).sort((a,b)=>rank(b)-rank(a))[0] || 'info';
      node.classList.add( variant==='warn' ? 'callout-warn' : (variant==='ccn' ? 'callout-ccn' : 'callout-info') );
      node.setAttribute('role', variant==='warn' ? 'alert' : 'region');
      node.setAttribute('aria-label', variant==='warn' ? 'Avertissement' : (variant==='ccn' ? 'Information CCN' : 'Information'));

      if (slot === 'step5.header' && items.length > 1){
        const kindRanked = items.map(x=>x._kind).sort((a,b)=>rank(b)-rank(a))[0] || 'info';
        const emote = (kindRanked==='warn' ? '⚠️' : (kindRanked==='ccn' ? '📘' : '💡'));
        const body = items.map(x=> renderRich(x.text||'')).join('<br>');
        const refs = items.map(x=>{
          if (x.url) return `<a href="${x.url}" target="_blank" rel="noopener">${escapeHtml(x.ref||'Réf.')}</a>`;
          if (x.ref) return escapeHtml(x.ref);
          return null;
        }).filter(Boolean).join(' · ');
        const refHtml = refs ? `<br><small>${refs}</small>` : '';
        node.innerHTML = `<div class="co-line" style="margin:8px 0"><span class="co-chip ${kindRanked}">${emote}</span><div class="co-body">${body}${refHtml}</div></div>`;
      } else {
        node.innerHTML = items.map(x=>{
          const emote = (x._kind==='warn' ? '⚠️' : (x._kind==='ccn' ? '📘' : '💡'));
          const ref = (x.url) ? `<small><a href="${x.url}" target="_blank" rel="noopener">${escapeHtml(x.ref||'Réf.')}</a></small>`
                              : (x.ref ? `<small>${escapeHtml(x.ref)}</small>` : '');
          const body = renderRich(x.text||'');
          return `<div class="co-line" style="margin:8px 0"><span class="co-chip ${x._kind}">${emote}</span><div class="co-body">${body}${ref?'<br>'+ref:''}</div></div>`;
        }).join('');
      }

      node.style.display = 'block';
      const det = node.closest('details'); if (det) det.style.display = 'block';
    });
  }

  // Expose
  window.renderExplain = window.renderExplain || renderExplain;
  window.EDS_EXPLAIN = window.EDS_EXPLAIN || {};
  window.EDS_EXPLAIN.configureTargets = function(map){
    window.SLOT_TARGETS = mergeSlotTargets(window.SLOT_TARGETS || {}, map || {});
  }
})();

