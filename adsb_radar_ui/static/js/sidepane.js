/* sidepane.js - the left pane of the desktop page (templates/_side.html, 2026-11-05).
 * radar.js keeps reading and driving the original controls; this file only draws them in the ATC style:
 *   - <span class="seg" data-for="<select id>">: one button per option of the hidden select
 *     (label = the option's data-s, else its value with data-num, else its text); a click sets the
 *     select and fires its change event; the buttons follow the select.
 *   - on / off: <label class="tg"> around a hidden check box (CSS :has(input:checked) inverts it).
 *   - sections open / close by their title (remembered, lpSec.<name>); a closed one shows a summary.
 *   - « hides the whole pane (paneHidden), » on the scope brings it back.
 *   - REPLAY is inverted while the replay bar is open.
 */
(() => {
  const side = document.querySelector('.side.lp');
  if (!side) return;
  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) { return null; } };
  const $ = id => document.getElementById(id);

  // --- choices as button rows
  const segs = [...side.querySelectorAll('.seg[data-for]')];
  function buildSeg(seg) {
    const sel = $(seg.dataset.for);
    if (!sel) return;
    seg.innerHTML = '';
    for (const o of sel.options) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = o.dataset.s || (seg.dataset.num ? o.value : o.text);
      b.title = o.text;
      b.dataset.v = o.value;
      b.addEventListener('click', () => {
        if (sel.value === o.value) return;
        sel.value = o.value;
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        refresh();
      });
      seg.appendChild(b);
    }
  }
  segs.forEach(buildSeg);

  // --- sections
  const secs = [...side.querySelectorAll('.lp-sec[data-sec]')];
  for (const s of secs) {
    const v = ls('lpSec.' + s.dataset.sec);
    s.classList.toggle('closed', v != null ? v === '0' : s.dataset.closed === '1');
    s.querySelector('.lp-h').addEventListener('click', () => {
      s.classList.toggle('closed');
      ls('lpSec.' + s.dataset.sec, s.classList.contains('closed') ? '0' : '1');
      refresh();
    });
  }
  const optText = id => { const e = $(id); return e && e.selectedOptions[0] ? (e.selectedOptions[0].dataset.s || e.selectedOptions[0].text) : ''; };
  const summary = {
    view: () => (($('rangeNm') || {}).value || '') + ' NM · ' + optText('themeSelect'),
    windows: () => ['tlOn', 'trOn', 'wxOn'].filter(id => $(id) && $(id).checked).length + ' open',
    labels: () => optText('labelStyle').replace('TOPSKY', 'TopSky').replace('CLASSIC', 'Classic'),
    targets: () => [$('showVector') && $('showVector').checked ? 'vector' : '', $('showTrail') && $('showTrail').checked ? 'trail' : ''].filter(Boolean).join(' · '),
    map: () => (side.querySelectorAll('#overlayList input[data-ovcat]:checked').length) + ' line sets',
    alt: () => { const q = $('qnhInput'); return q && q.value ? 'Q' + String(q.value).padStart(4, '0') + ($('qnhAuto') && $('qnhAuto').checked ? ' auto' : '') : ''; },
    own: () => ($('ownPosOn') && $('ownPosOn').checked ? 'shown' : 'off'),
    filter: () => ($('icaoFilter') && $('icaoFilter').value.trim() ? 'on' : 'off'),
    status: () => ((window.navdataInfo || '').match(/AIRAC [\d.]+/) || [''])[0],
  };

  // --- keep the buttons in step with the controls (radar.js and the app set them by code)
  const rpBtn = $('rpOpen');
  function refresh() {
    for (const seg of segs) {
      const sel = $(seg.dataset.for);
      if (!sel) continue;
      if (seg.children.length !== sel.options.length) buildSeg(seg);
      for (const b of seg.children) b.classList.toggle('on', b.dataset.v === sel.value);
    }
    for (const s of secs) {
      const el = s.querySelector('.lp-sum'), f = summary[s.dataset.sec];
      if (el && f) { const t = f(); if (el.textContent !== t) el.textContent = t; }
    }
    const bar = $('rpBar');
    if (rpBtn) rpBtn.classList.toggle('on', !!bar && !bar.hidden);
  }
  document.addEventListener('change', () => setTimeout(refresh, 0), true);
  document.addEventListener('click', () => setTimeout(refresh, 0), true);
  document.addEventListener('input', () => setTimeout(refresh, 0), true);
  setInterval(refresh, 1000);
  refresh();

  // --- ⌂ in the pane = the scope's ⌂
  const home = $('paneHome');
  if (home) home.addEventListener('click', () => { const b = $('btnHome'); if (b) b.click(); });

  // --- hide / show the whole pane
  const hideBtn = $('paneHide'), showBtn = $('btnPane');
  function setHidden(v) {
    document.body.classList.toggle('pane-hidden', v);
    if (showBtn) showBtn.hidden = !v;
    ls('paneHidden', v ? '1' : '0');
    window.dispatchEvent(new Event('resize'));        // the canvas and the windows follow the new width
    if (typeof requestDraw === 'function') requestDraw();
  }
  if (hideBtn) hideBtn.addEventListener('click', () => setHidden(true));
  if (showBtn) showBtn.addEventListener('click', () => setHidden(false));
  if (ls('paneHidden') === '1') setHidden(true);
})();
