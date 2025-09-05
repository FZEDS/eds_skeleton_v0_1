(function(){
  'use strict';
  if (window._EDS_STEP4_ATTACHED) return;
  window._EDS_STEP4_ATTACHED = true;

  const $ = (s)=>document.querySelector(s);

  function refreshMissionBlocks(){
    const inContract = $('#mission_in_contract')?.checked;
    const inAnnex    = $('#mission_in_annex')?.checked;
    const contractEl = $('#mission_contract_fields');
    const annexEl    = $('#mission_annex_banner');
    if (contractEl) contractEl.style.display = inContract ? 'block' : 'none';
    if (annexEl)    annexEl.style.display    = inAnnex    ? 'block' : 'none';
  }

  document.addEventListener('DOMContentLoaded', refreshMissionBlocks);
  $('#mission_in_contract')?.addEventListener('change', refreshMissionBlocks);
  $('#mission_in_annex')?.addEventListener('change', refreshMissionBlocks);
})();
