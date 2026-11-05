/* trafficlist.js - the TRAFFIC window (index.html #tlWindow, 2026-11-05): all aircraft in a table that
 * moves and resizes like the other ATC windows (atcwin.js). radar.js fills the rows (#trafficList) once
 * a second while the window is open. Here: open / close (WINDOWS → TRAFFIC LIST, ls tlOn), sorting by
 * a click on CALLSIGN / LVL / NM (the hidden #trafficSort), and a click on a row selects that aircraft
 * on the scope (a second click releases it); the ↗ opens flightradar24 / ADS-B Exchange.
 */
(function () {
  const win = document.getElementById('tlWindow');
  const body = document.getElementById('trafficList');
  const cb = document.getElementById('tlOn');
  const sortSel = document.getElementById('trafficSort');
  if (!win || !body || !cb || typeof AtcWindow === 'undefined') return;
  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) { return null; } };
  const aw = AtcWindow.make(win, { key: 'tlGeom', head: win.querySelector('.wn-head') });

  function setOn(v) {
    cb.checked = v; ls('tlOn', v ? '1' : '0');
    if (v) { aw.show(); try { _trafficBuildTs = 0; _trafficLastHTML = ''; } catch (_) {} } else aw.hide();
    if (typeof requestDraw === 'function') requestDraw();
  }
  cb.addEventListener('change', () => setOn(cb.checked));
  document.getElementById('tlClose').addEventListener('click', () => setOn(false));

  // sorting: CALLSIGN A→Z / Z→A, LVL low→high / high→low, NM near→far / far→near
  const SORTS = { label: ['labelAsc', 'labelDesc'], alt: ['altAsc', 'altDesc'], range: ['rangeAsc', 'rangeDesc'] };
  function markSort() {
    const v = sortSel ? sortSel.value : '';
    win.querySelectorAll('th[data-sort]').forEach(th => {
      const [a, d] = SORTS[th.dataset.sort];
      th.classList.toggle('asc', v === a); th.classList.toggle('desc', v === d);
    });
  }
  win.querySelectorAll('th[data-sort]').forEach(th => th.addEventListener('click', () => {
    if (!sortSel) return;
    const [a, d] = SORTS[th.dataset.sort];
    sortSel.value = sortSel.value === a ? d : a;
    sortSel.dispatchEvent(new Event('change'));
    try { _trafficBuildTs = 0; } catch (_) {}
    markSort();
    if (typeof requestDraw === 'function') requestDraw();
  }));
  markSort();

  // a row selects its aircraft on the scope (as in the EFHK TRAFFIC window); again = release
  body.addEventListener('click', e => {
    if (e.target.closest('a')) return;                  // ↗: the link opens in a new tab
    const tr = e.target.closest('tr[data-hex]');
    if (!tr || !tr.dataset.hex) return;
    const hex = tr.dataset.hex;
    const sel = typeof selectedHex === 'function' ? selectedHex() : null;
    if (sel === hex) { if (window.radarDeselect) window.radarDeselect(); }
    else if (window.radarSelect) window.radarSelect(hex);
    body.querySelectorAll('tr.sel').forEach(r => r.classList.remove('sel'));
    if (sel !== hex) tr.classList.add('sel');
    try { _trafficBuildTs = 0; } catch (_) {}
  });

  setOn(ls('tlOn') === '1');
})();
