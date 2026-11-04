/* wx.js - the METAR & TAF window on the scope (/api/wx?icao=XXXX).
 *
 * Sidebar "METAR & TAF": an ICAO code (EFHK by default), Apply and Show. The window
 * opens at the top right of the scope; drag it by its title bar, resize it from the
 * lower-right corner. Position, size, airport and on/off are remembered in this browser.
 * The reports come from the same NOAA source as MODE-S Wind (the server fetches them at
 * most every 10 minutes); the window asks again every 2 minutes while it is open.
 */
(function () {
  const win = document.getElementById('wxWindow');
  const body = document.getElementById('wxBody');
  const title = document.getElementById('wxTitle');
  const head = win && win.querySelector('.wx-head');
  const cb = document.getElementById('wxOn');
  const inp = document.getElementById('wxIcaoInput');
  const btn = document.getElementById('applyWx');
  const stage = win && win.parentElement;
  if (!win || !body || !cb || !inp || !stage) return;

  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) { return null; } };
  const ICAO_RE = /^[A-Z][A-Z0-9]{3}$/;
  let icao = (ls('wxIcao') || 'EFHK').toUpperCase();
  if (!ICAO_RE.test(icao)) icao = 'EFHK';
  let on = ls('wxOn') === '1';
  let timer = null, last = null;
  inp.value = icao;
  cb.checked = on;

  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  // "040550Z" -> minutes since that time (UTC; the day of month may be in the previous month)
  function ageMin(ddhhmm) {
    const m = /^(\d{2})(\d{2})(\d{2})Z$/.exec(ddhhmm || '');
    if (!m) return null;
    const now = new Date();
    let t = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), +m[1], +m[2], +m[3]);
    if (t - now.getTime() > 2 * 86400e3) t = Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, +m[1], +m[2], +m[3]);
    return Math.round((now.getTime() - t) / 60000);
  }
  function ageTxt(ddhhmm, oldMin) {
    const a = ageMin(ddhhmm);
    if (a == null) return '';
    const hhmm = ddhhmm.slice(2, 4) + ':' + ddhhmm.slice(4, 6) + 'Z';
    const txt = a < 60 ? `${a} min ago` : a < 48 * 60 ? `${Math.floor(a / 60)} h ${a % 60} min ago` : `${Math.round(a / 1440)} days ago`;
    return `<span class="wx-age${a > oldMin ? ' wx-old' : ''}">${hhmm} · ${txt}</span>`;
  }

  function render(d) {
    title.textContent = `METAR & TAF · ${d.icao || icao}`;
    if (d.error) { body.innerHTML = `<p class="wx-none">${esc(d.error)}</p>`; return; }
    const sec = (name, text, time, err, oldMin) =>
      `<div class="wx-sec"><span>${name}</span>${text ? ageTxt(time, oldMin) : ''}</div>` +
      (text ? `<pre class="wx-text">${esc(text)}</pre>`
            : `<p class="wx-none">${err === 'not available' || !err ? `No ${name} for ${esc(d.icao)}` : `${name} not available: ${esc(err)}`}</p>`);
    // a METAR older than 90 min (they come every 30 or 60 min) is marked; a TAF older than 12 h
    body.innerHTML = sec('METAR', d.metar, d.metar_time, d.metar_error, 90) + sec('TAF', d.taf, d.taf_time, d.taf_error, 720);
  }

  async function load() {
    if (!on) return;
    try {
      const r = await fetch(`/api/wx?icao=${encodeURIComponent(icao)}`, { cache: 'no-store' });
      last = await r.json();
      render(last);
    } catch (_) {
      title.textContent = `METAR & TAF · ${icao}`;
      body.innerHTML = '<p class="wx-none">Radar server not reachable.</p>';
    }
  }

  // ---- position and size (remembered); default: top right of the scope ----
  function applyGeom() {
    let g = null;
    try { g = JSON.parse(ls('wxGeom') || 'null'); } catch (_) { g = null; }
    if (g && Number.isFinite(g.left) && Number.isFinite(g.top)) {
      win.style.left = g.left + 'px'; win.style.top = g.top + 'px'; win.style.right = 'auto';
      if (g.width > 0) win.style.width = g.width + 'px';
      if (g.height > 0) win.style.height = g.height + 'px';
    }
    keepInside();
  }
  function saveGeom() {
    if (win.hidden) return;
    const s = stage.getBoundingClientRect(), r = win.getBoundingClientRect();
    ls('wxGeom', JSON.stringify({ left: Math.round(r.left - s.left), top: Math.round(r.top - s.top),
                                  width: Math.round(r.width), height: Math.round(r.height) }));
  }
  function keepInside() {             // never lose the window outside the scope
    if (win.hidden) return;
    const s = stage.getBoundingClientRect(), r = win.getBoundingClientRect();
    if (r.left < s.left || r.top < s.top || r.right > s.right || r.bottom > s.bottom) {
      const left = Math.max(0, Math.min(r.left - s.left, s.width - r.width));
      const top = Math.max(0, Math.min(r.top - s.top, s.height - Math.min(r.height, s.height)));
      win.style.left = left + 'px'; win.style.top = top + 'px'; win.style.right = 'auto';
    }
  }
  if (head) head.addEventListener('mousedown', e => {
    if (e.button !== 0 || e.target.closest('button')) return;
    e.preventDefault();
    const s = stage.getBoundingClientRect(), r = win.getBoundingClientRect();
    const dx = e.clientX - r.left, dy = e.clientY - r.top;
    win.style.left = (r.left - s.left) + 'px'; win.style.top = (r.top - s.top) + 'px'; win.style.right = 'auto';
    const move = ev => {
      const left = Math.max(0, Math.min(ev.clientX - s.left - dx, s.width - r.width));
      const top = Math.max(0, Math.min(ev.clientY - s.top - dy, s.height - 30));
      win.style.left = left + 'px'; win.style.top = top + 'px';
    };
    const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); saveGeom(); };
    document.addEventListener('mousemove', move);
    document.addEventListener('mouseup', up);
  });
  let rsTimer = null;
  if (window.ResizeObserver) new ResizeObserver(() => { clearTimeout(rsTimer); rsTimer = setTimeout(saveGeom, 300); }).observe(win);
  window.addEventListener('resize', keepInside);

  // ---- on / off and the airport ----
  function setOn(v) {
    on = v; cb.checked = v; ls('wxOn', v ? '1' : '0');
    win.hidden = !v;
    clearInterval(timer); timer = null;
    if (v) { applyGeom(); load(); timer = setInterval(() => { if (!document.hidden) load(); }, 120000); }
  }
  function apply() {
    const v = (inp.value || '').trim().toUpperCase();
    if (!ICAO_RE.test(v)) { inp.classList.add('invalid'); return; }
    inp.classList.remove('invalid');
    inp.value = v;
    const changed = v !== icao;
    icao = v; ls('wxIcao', v);
    if (changed) body.textContent = 'Loading…';
    if (on) load(); else setOn(true);
  }
  btn && btn.addEventListener('click', apply);
  inp.addEventListener('keydown', e => { if (e.key === 'Enter') apply(); });
  cb.addEventListener('change', () => setOn(cb.checked));
  document.getElementById('wxClose').addEventListener('click', () => setOn(false));
  setOn(on);
})();
