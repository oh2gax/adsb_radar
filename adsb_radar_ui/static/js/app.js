/* app.js - the RADAR mobile app (/app).
 *
 * The scope is the desktop one (radar.js / topsky.js). The desktop sidebar is in the page, hidden
 * (#appControls): radar.js reads and drives its controls, and the menu here sets them, so both pages
 * behave the same. The app keeps its own settings (app.html prefixes every localStorage key).
 *
 * Touch: one finger moves the map, two fingers pinch-zoom around the fingers, a tap selects an
 * aircraft (TopSky: its extended label stays open; both styles: its history line), a tap on empty
 * scope releases it. Views: Radar, EFHK traffic, METAR & TAF, What's new (full pages).
 */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) { return null; } };
  const esc = t => String(t ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const pad = n => String(n).padStart(2, '0');
  const canvasEl = $('radarCanvas');

  // ---- toast ----
  let toastTimer = null;
  function toast(txt, ms) {
    const el = $('appToast');
    el.textContent = txt; el.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, ms || 2200);
  }

  // ---- the hidden desktop controls ----
  function setControl(id, value) {
    const el = $(id); if (!el) return;
    if (el.type === 'checkbox') el.checked = !!value; else el.value = String(value);
    el.dispatchEvent(new Event('change', { bubbles: true }));
    requestDraw();
  }
  function controlValue(id) {
    const el = $(id); if (!el) return null;
    return el.type === 'checkbox' ? el.checked : el.value;
  }

  // chips: one choice of a select (data-select = the select's id)
  document.querySelectorAll('.app-chips[data-select]').forEach(group => {
    group.addEventListener('click', e => {
      const b = e.target.closest('button[data-v]'); if (!b) return;
      setControl(group.dataset.select, b.dataset.v);
      syncMenu();
    });
  });
  // switches: a checkbox (data-check = the checkbox's id)
  document.querySelectorAll('input[data-check]').forEach(cb => {
    cb.addEventListener('change', () => setControl(cb.dataset.check, cb.checked));
  });
  // map layers: all lines of one category (the desktop's group checkbox)
  document.querySelectorAll('#appLayers input[data-ovcat]').forEach(cb => {
    cb.addEventListener('change', () => {
      const g = document.querySelector(`#overlayList input[data-ovcat="${cb.dataset.ovcat}"]`);
      if (g) { g.checked = cb.checked; g.dispatchEvent(new Event('change', { bubbles: true })); }
      requestDraw();
    });
  });
  function syncMenu() {
    document.querySelectorAll('.app-chips[data-select]').forEach(group => {
      const v = String(controlValue(group.dataset.select));
      group.querySelectorAll('button[data-v]').forEach(b => b.classList.toggle('on', b.dataset.v === v));
    });
    document.querySelectorAll('input[data-check]').forEach(cb => { cb.checked = !!controlValue(cb.dataset.check); });
    document.querySelectorAll('#appLayers input[data-ovcat]').forEach(cb => {
      const g = document.querySelector(`#overlayList input[data-ovcat="${cb.dataset.ovcat}"]`);
      cb.closest('label').hidden = !g;
      if (g) cb.checked = g.checked;
    });
    const qi = $('qnhInfo');
    $('appQnh').textContent = qi && qi.textContent ? qi.textContent : `QNH ${Math.round(qnh)}`;
    $('appWake').checked = ls('appWake') === '1';
  }

  // ---- menu ----
  const drawer = $('appDrawer'), shade = $('appShade');
  function menu(open) {
    if (open) syncMenu();
    drawer.classList.toggle('open', open);
    drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
    $('appMenuBtn').setAttribute('aria-expanded', open ? 'true' : 'false');
    shade.hidden = !open;
  }
  $('appMenuBtn').addEventListener('click', () => menu(true));
  $('appMenuClose').addEventListener('click', () => menu(false));
  shade.addEventListener('click', () => menu(false));
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && drawer.classList.contains('open')) { menu(false); e.stopPropagation(); } }, true);

  // ---- views ----
  const VIEWS = { radar: null, traffic: 'vTraffic', wx: 'vWx', news: 'vNews' };
  let view = 'radar';
  function show(v) {
    view = v;
    for (const [k, id] of Object.entries(VIEWS)) if (id) $(id).hidden = k !== v;
    document.querySelectorAll('.app-tile[data-view]').forEach(t => t.classList.toggle('on', t.dataset.view === v));
    if (v === 'traffic') trLoad();
    if (v === 'wx') { wxLoad(); wxShowTab(wxTab); }
    if (v === 'news') newsLoad();
    updateBar();
    requestDraw();
  }
  document.querySelectorAll('.app-tile[data-view]').forEach(t => t.addEventListener('click', () => { show(t.dataset.view); menu(false); }));

  // ---- the bar: title, range and targets, UTC, feed ----
  function updateBar() {
    const d = new Date();
    $('appUtc').textContent = pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes());
    const title = $('appTitle'), sub = $('appSub');
    if (view === 'radar') {
      let n = 0;
      for (const a of aircraft.values()) if (Number.isFinite(a.lat) && Number.isFinite(a.lon)) n++;
      title.textContent = 'RADAR';
      sub.textContent = `${fmtRange(rangeNm)} NM · ${n} target${n === 1 ? '' : 's'}`;
    } else if (view === 'traffic') { title.textContent = 'EFHK TRAFFIC'; sub.textContent = trSub; }
    else if (view === 'wx') {
      title.textContent = 'METAR & TAF';
      sub.textContent = wxTab === 'rep' && R ? `Reports · last ${R.opt.hours} h · ${R.count()} message${R.count() === 1 ? '' : 's'}` : `${wxIcao} · refreshed every 10 min`;
    }
    else { title.textContent = "WHAT'S NEW"; sub.textContent = `RADAR ${window.RADAR_VERSION || ''}`; }
    const st = $('status'), feed = $('appFeed');
    const bad = !!(st && st.classList.contains('warn'));
    feed.className = 'app-feed ' + (bad ? 'bad' : (typeof lastDataOkMs !== 'undefined' && Date.now() - lastDataOkMs < 10000 ? 'ok' : ''));
    feed.title = st ? st.textContent : '';
  }
  setInterval(updateBar, 1000);

  // ---- theme button: steps through the themes ----
  const THEMES = [['gray', 'Gray (ATC)'], ['green', 'Green (EL)'], ['full-el', 'Full EL (mono)'], ['full-el-yellow', 'Full EL (yellow)']];
  $('appThemeBtn').addEventListener('click', () => {
    const i = THEMES.findIndex(t => t[0] === theme);
    const next = THEMES[(i + 1) % THEMES.length];
    setControl('themeSelect', next[0]);
    toast('Theme: ' + next[1], 1500);
  });

  // ---- zoom buttons ----
  $('appZoomIn').addEventListener('click', () => { const b = $('zoomIn'); if (b) b.click(); });
  $('appZoomOut').addEventListener('click', () => { const b = $('zoomOut'); if (b) b.click(); });
  $('appHome').addEventListener('click', () => setCenter(window.RADAR_CENTER.lat, window.RADAR_CENTER.lon, true));

  // ---- touch: move with one finger, pinch-zoom with two ----
  const fingers = new Map();
  let gest = null, swallowClickUntil = 0;
  const scopeR = () => Math.max(10, Math.min(canvasEl.clientWidth, canvasEl.clientHeight) / 2 - 24);
  function startGesture() {
    const r = canvasEl.getBoundingClientRect();
    const p = [...fingers.values()];
    gest = { lat: center.lat, lon: center.lon, range: rangeNm, moved: gest ? gest.moved : false, n: p.length, r };
    if (p.length === 1) { gest.x = p[0].x; gest.y = p[0].y; }
    else {
      gest.d = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) || 1;
      const mx = (p[0].x + p[1].x) / 2 - r.left - r.width / 2, my = (p[0].y + p[1].y) / 2 - r.top - r.height / 2;
      const R = scopeR(), cosc = Math.cos(center.lat * Math.PI / 180);
      gest.plat = center.lat - (my / R * rangeNm) / 60;                 // the place between the fingers
      gest.plon = center.lon + (mx / R * rangeNm) / (60 * cosc);
    }
  }
  canvasEl.addEventListener('pointerdown', e => {
    if (e.pointerType === 'mouse') return;
    try { canvasEl.setPointerCapture(e.pointerId); } catch (_) {}
    fingers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (fingers.size <= 2) startGesture();
  });
  canvasEl.addEventListener('pointermove', e => {
    if (!fingers.has(e.pointerId) || !gest) return;
    fingers.set(e.pointerId, { x: e.clientX, y: e.clientY });
    const p = [...fingers.values()];
    const R = scopeR();
    if (p.length === 1 && gest.n === 1) {
      const dx = p[0].x - gest.x, dy = p[0].y - gest.y;
      if (!gest.moved && Math.hypot(dx, dy) < 8) return;               // a small wobble is still a tap
      gest.moved = true;
      const nmPerPx = rangeNm / R;
      const la = gest.lat + (dy * nmPerPx) / 60;
      setCenter(la, gest.lon - (dx * nmPerPx) / (60 * Math.cos(la * Math.PI / 180)), false);
    } else if (p.length >= 2 && gest.n >= 2) {
      gest.moved = true;
      const d = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y) || 1;
      setRange(gest.range * gest.d / d, false);
      const r = gest.r;
      const mx = (p[0].x + p[1].x) / 2 - r.left - r.width / 2, my = (p[0].y + p[1].y) / 2 - r.top - r.height / 2;
      const la = gest.plat + (my / R * rangeNm) / 60;
      setCenter(la, gest.plon - (mx / R * rangeNm) / (60 * Math.cos(la * Math.PI / 180)), false);
    } else return;
    wheelUntil = Date.now() + 300;          // radar.js: the map is moving (cheap redraw, labels keep their place)
    requestDraw();
  });
  function endFinger(e) {
    if (!fingers.has(e.pointerId)) return;
    fingers.delete(e.pointerId);
    if (fingers.size) { startGesture(); return; }                     // one finger left after a pinch
    if (gest && gest.moved) {
      swallowClickUntil = Date.now() + 500;
      savePrefs();
      setCenter(center.lat, center.lon, true);                         // store the centre, reload the map data
    }
    gest = null;
  }
  canvasEl.addEventListener('pointerup', endFinger);
  canvasEl.addEventListener('pointercancel', endFinger);
  canvasEl.addEventListener('click', e => {                             // capture: before the selection
    if (Date.now() < swallowClickUntil) { e.stopImmediatePropagation(); e.preventDefault(); }
  }, true);
  canvasEl.addEventListener('contextmenu', e => e.preventDefault());

  // ---- my position from the phone's GPS (the own-position triangle of radar.js) ----
  let gpsWatch = null, gpsFirst = false;
  function gpsOff(msg) {
    if (gpsWatch != null) navigator.geolocation.clearWatch(gpsWatch);
    gpsWatch = null; ownPos.on = false;
    $('appGps').classList.remove('on', 'wait');
    requestDraw();
    if (msg) toast(msg, 3500);
  }
  $('appGps').addEventListener('click', () => {
    if (gpsWatch != null) { gpsOff('My position: off'); return; }
    if (!('geolocation' in navigator)) { toast('This browser has no location service.', 3000); return; }
    gpsFirst = true;
    $('appGps').classList.add('wait');
    gpsWatch = navigator.geolocation.watchPosition(p => {
      ownPos.lat = p.coords.latitude; ownPos.lon = p.coords.longitude; ownPos.on = true;
      const b = $('appGps'); b.classList.remove('wait'); b.classList.add('on');
      if (gpsFirst) {
        gpsFirst = false;
        setCenter(ownPos.lat, ownPos.lon, true);
        toast(`My position (±${Math.round(p.coords.accuracy)} m)`, 2000);
      }
      requestDraw();
    }, err => {
      gpsOff(err.code === 1 ? 'Location not allowed: allow it for this site in the browser settings.' : 'No position from the phone: ' + err.message);
    }, { enableHighAccuracy: true, maximumAge: 10000, timeout: 30000 });
  });

  // ---- keep the screen on ----
  let wakeLock = null;
  async function wake() {
    if (ls('appWake') !== '1' || !('wakeLock' in navigator) || document.hidden) return;
    try { wakeLock = await navigator.wakeLock.request('screen'); } catch (_) { wakeLock = null; }
  }
  $('appWake').addEventListener('change', e => {
    ls('appWake', e.target.checked ? '1' : '0');
    if (e.target.checked) { if (!('wakeLock' in navigator)) toast('This browser cannot keep the screen on.', 3000); wake(); }
    else if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
  });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) wake(); });
  wake();
  document.addEventListener('click', () => { if (!wakeLock) wake(); }, { once: true });

  // ---- reset ----
  $('appReset').addEventListener('click', () => {
    if (!confirm("Reset the app's settings? (The desktop page keeps its own.)")) return;
    localStorage.clear(); location.reload();
  });

  // ---- EFHK traffic (/api/efhk_traffic) ----
  const KINDS = ['arr', 'dep', 'both'], HOURS = [1, 3, 6, 12, 24];
  let trKind = KINDS.includes(ls('trKind')) ? ls('trKind') : 'both';
  let trHours = HOURS.includes(+ls('trHours')) ? +ls('trHours') : 3;
  let trSub = '', trTimer = null, trSeq = 0;
  const hhmm = t => { const d = new Date(t * 1000); return pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()); };
  const dayKey = t => new Date(t * 1000).toISOString().slice(0, 10);
  function trButtons() {
    document.querySelectorAll('#trKinds button').forEach(b => b.classList.toggle('on', b.dataset.kind === trKind));
    document.querySelectorAll('#trHours button').forEach(b => b.classList.toggle('on', +b.dataset.hours === trHours));
  }
  function trRender(d) {
    const span = trHours === 24 ? '1 d' : trHours + ' h';
    trSub = `last ${span} · tap: its track`;
    const what = trKind === 'arr' ? 'arrivals' : trKind === 'dep' ? 'departures' : 'traffic';
    $('trCountM').textContent = d.error ? '' : (trKind === 'both' ? `${d.arr} arr · ${d.dep} dep` : `${trKind === 'arr' ? d.arr : d.dep} ${what}`) +
      ` · last ${span}` + (d.note ? ' · radar only' : '');
    const body = $('trBodyM');
    if (d.error) { body.innerHTML = `<p class="app-none">${esc(d.error)}</p>`; return; }
    const rows = d.rows || [];
    if (!rows.length) { body.innerHTML = `<p class="app-none">No ${what} in the last ${span}.</p>`; return; }
    const both = trKind === 'both';
    let html = '<table class="app-tbl"><thead><tr><th>UTC</th>' + (both ? '<th>A/D</th>' : '') +
               '<th>CALLSIGN</th><th>TYPE</th><th>RWY</th><th></th></tr></thead><tbody>';
    let prev = dayKey(d.now || Date.now() / 1000);
    for (const r of rows) {
      const day = dayKey(r.t);
      if (day !== prev) { const x = new Date(r.t * 1000); html += `<tr class="day"><td colspan="${both ? 6 : 5}">── ${pad(x.getUTCDate())}.${pad(x.getUTCMonth() + 1)}. ──</td></tr>`; prev = day; }
      const ga = r.ga ? (r.ga > 1 ? 'GA' + r.ga : 'GA') : '';
      const tag = [r.callsign || r.icao, hhmm(r.t), r.kind === 'arr' ? 'ARR' : 'DEP', r.rwy || '', ga].filter(Boolean).join(' ');
      const live = window.radarHasAircraft(r.icao);
      html += `<tr data-icao="${esc(r.icao)}" data-t="${r.t}" data-tag="${esc(tag)}"${live ? ' class="live"' : ''}>` +
              `<td>${hhmm(r.t)}</td>` + (both ? `<td>${r.kind === 'arr' ? 'ARR' : 'DEP'}</td>` : '') +
              `<td class="cs">${esc(r.callsign || r.icao)}</td><td>${esc(r.type || '')}</td><td>${esc(r.rwy || '---')}</td><td class="ga">${ga}</td></tr>`;
    }
    body.innerHTML = html + '</tbody></table>';
  }
  async function trLoad() {
    trButtons();
    clearInterval(trTimer);
    trTimer = setInterval(() => { if (view === 'traffic' && !document.hidden) trLoad(); }, 60000);
    const my = ++trSeq;
    try {
      const d = await (await fetch(`/api/efhk_traffic?kind=${trKind}&hours=${trHours}`, { cache: 'no-store' })).json();
      if (my === trSeq) { trRender(d); updateBar(); }
    } catch (_) { if (my === trSeq) $('trBodyM').innerHTML = '<p class="app-none">Radar server not reachable.</p>'; }
  }
  $('trKinds').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; trKind = b.dataset.kind; ls('trKind', trKind); $('trBodyM').textContent = 'Loading…'; trLoad(); });
  $('trHours').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; trHours = +b.dataset.hours; ls('trHours', String(trHours)); $('trBodyM').textContent = 'Loading…'; trLoad(); });
  $('trBodyM').addEventListener('click', async e => {
    const tr = e.target.closest('tr[data-icao]'); if (!tr) return;
    tr.classList.add('sel');
    const n = await window.radarShowTrack(tr.dataset.icao, +tr.dataset.t, tr.dataset.tag);
    tr.classList.remove('sel');
    if (!n) { toast('No track recorded for that flight (tracks are kept for 24 h).', 3000); return; }
    show('radar');
    toast(tr.dataset.tag, 2500);
  });

  // ---- METAR & TAF (/api/wx) ----
  const ICAO_RE = /^[A-Z][A-Z0-9]{3}$/;
  let wxList = (ls('wxList') || 'EFHK,EFTU,EFTP').split(',').filter(x => ICAO_RE.test(x)).slice(0, 6);
  if (!wxList.length) wxList = ['EFHK'];
  let wxIcao = ICAO_RE.test(ls('wxIcao') || '') ? ls('wxIcao') : wxList[0];
  let wxTimer = null;
  function wxChips() {
    $('wxChips').innerHTML = wxList.map(i => `<button type="button" data-icao="${i}" class="${i === wxIcao ? 'on' : ''}">${i}</button>`).join('');
  }
  function ageMin(ddhhmm) {
    const m = /^(\d{2})(\d{2})(\d{2})Z$/.exec(ddhhmm || ''); if (!m) return null;
    const now = new Date();
    let t = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), +m[1], +m[2], +m[3]);
    if (t - now.getTime() > 2 * 86400e3) t = Date.UTC(now.getUTCFullYear(), now.getUTCMonth() - 1, +m[1], +m[2], +m[3]);
    return Math.round((now.getTime() - t) / 60000);
  }
  function ageTxt(tm, oldMin) {
    const a = ageMin(tm); if (a == null) return '';
    const txt = a < 60 ? `${a} min ago` : a < 2880 ? `${Math.floor(a / 60)} h ${a % 60} min ago` : `${Math.round(a / 1440)} days ago`;
    return ` · ${tm.slice(2, 4)}:${tm.slice(4, 6)}Z · <span class="${a > oldMin ? 'old' : ''}">${txt}</span>`;
  }
  async function wxLoad() {
    wxChips(); updateBar();
    clearInterval(wxTimer);
    wxTimer = setInterval(() => { if (view === 'wx' && !document.hidden) wxLoad(); }, 120000);
    try {
      const d = await (await fetch(`/api/wx?icao=${encodeURIComponent(wxIcao)}`, { cache: 'no-store' })).json();
      if (d.error) { $('wxBodyM').innerHTML = `<p class="app-none">${esc(d.error)}</p>`; return; }
      const sec = (name, text, tm, err, old) => `<h4>${name}${text ? ageTxt(tm, old) : ''}</h4>` +
        (text ? `<pre>${esc(text)}</pre>` : `<p>${!err || err === 'not available' ? `No ${name} for ${esc(d.icao)}` : `${name} not available: ${esc(err)}`}</p>`);
      $('wxBodyM').innerHTML = sec('METAR', d.metar, d.metar_time, d.metar_error, 90) + sec('TAF', d.taf, d.taf_time, d.taf_error, 720);
    } catch (_) { $('wxBodyM').innerHTML = '<p class="app-none">Radar server not reachable.</p>'; }
  }
  $('wxChips').addEventListener('click', e => { const b = e.target.closest('button[data-icao]'); if (!b) return; wxIcao = b.dataset.icao; ls('wxIcao', wxIcao); $('wxBodyM').textContent = 'Loading…'; wxLoad(); });
  $('wxForm').addEventListener('submit', e => {
    e.preventDefault();
    const v = ($('wxIcao').value || '').trim().toUpperCase();
    if (!ICAO_RE.test(v)) { toast('An ICAO code has 4 letters, e.g. EFOU.', 2500); return; }
    wxIcao = v; ls('wxIcao', v);
    wxList = [v, ...wxList.filter(x => x !== v)].slice(0, 6); ls('wxList', wxList.join(','));
    $('wxIcao').value = ''; $('wxIcao').blur();
    $('wxBodyM').textContent = 'Loading…'; wxLoad();
  });

  // ---- METAR & TAF page: tab REPORTS (pilot reports from MODE-S Wind, reports.js) ----
  const R = typeof WxReports !== 'undefined' ? WxReports : null;
  let wxTab = ls('wxTab') === 'rep' && R ? 'rep' : 'wx';
  function wxShowTab(t) {
    wxTab = t; ls('wxTab', t);
    document.querySelectorAll('#wxTabsM button').forEach(b => b.classList.toggle('on', b.dataset.wxtab === t));
    const rep = t === 'rep';
    document.querySelector('#vWx .app-wx-bar').hidden = rep; $('wxBodyM').hidden = rep;
    $('wxRepBarM').hidden = !rep; $('wxRepListM').hidden = !rep;
    if (rep && R) { R.load(); renderRepM(); }
    updateBar();
  }
  function renderRepM() {
    if (!R) return;
    const list = R.filtered(), dot = R.hasNew();
    $('wxRepNM').textContent = `(${list.length})`;
    $('wxRepDotM').hidden = !dot; $('appWxDot').hidden = !dot;
    menuDot();
    if (view !== 'wx' || wxTab !== 'rep') return;
    $('wxRepBarM').innerHTML = R.barHtml();
    $('wxRepListM').innerHTML = R.html(list) + `<div class="rp-foot">${R.footer()}</div>`;
    R.markSeen();
  }
  if (R) {
    R.bindBar($('wxRepBarM'));
    R.onChange(renderRepM);
    document.querySelectorAll('#wxTabsM button').forEach(b => b.addEventListener('click', () => wxShowTab(b.dataset.wxtab)));
  } else $('wxTabsM').hidden = true;

  // ---- What's new (/api/whatsnew; the dot marks a version not opened in the app yet) ----
  const ver = window.RADAR_VERSION || '';
  // the ☰ dot: an unread What's new or a new pilot report near EFHK
  function menuDot() { $('appMenuDot').hidden = $('appNewsDot').hidden && (!R || !R.hasNew()); }
  if (ver && ls('seenVersion') !== ver) { $('appNewsDot').hidden = false; }
  menuDot();
  const inline = t => esc(t).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>').replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>');
  function mdLines(lines) {
    let html = '', depth = 0, para = [];
    const flush = () => { if (para.length) { html += '<p>' + inline(para.join(' ')) + '</p>'; para = []; } };
    const close = to => { while (depth > to) { html += '</ul>'; depth--; } };
    for (const l of lines) {
      const m = l.match(/^(\s*)[-*]\s+(.*)$/);
      if (m) { flush(); const d = m[1].length >= 2 ? 2 : 1; while (depth < d) { html += '<ul>'; depth++; } close(d); html += '<li>' + inline(m[2]) + '</li>'; }
      else if (!l.trim()) { flush(); close(0); }
      else { close(0); para.push(l.trim()); }
    }
    flush(); close(0);
    return html;
  }
  let newsLoaded = false;
  async function newsLoad() {
    ls('seenVersion', ver); $('appNewsDot').hidden = true; menuDot();
    if (newsLoaded) return;
    try {
      const d = await (await fetch('/api/whatsnew', { cache: 'no-store' })).json();
      const es = d.entries || [];
      $('newsBody').innerHTML = es.length ? es.map(e => `<h3>${esc(e.version)}${e.version === ver ? ' · CURRENT' : ''}</h3>` +
        (e.title ? `<p><b>${inline(e.title)}</b></p>` : '') + mdLines(e.lines || [])).join('') : '<p>No notes found.</p>';
      // the user guides (doc/guides.md) first, as in the desktop window's USER GUIDES tab
      const gs = d.guides || [];
      if (gs.length) $('newsBody').insertAdjacentHTML('afterbegin', '<h3>USER GUIDES</h3>' + gs.map(g =>
        `<p><a href="${esc(g.url)}" target="_blank" rel="noopener"><b>${esc(g.title)}</b></a><br><small>` +
        [g.version ? 'Version ' + esc(g.version) : '', g.pages ? esc(g.pages) + ' pages' : '', g.size ? (g.size / 1e6).toFixed(1) + ' MB' : ''].filter(Boolean).join(' · ') +
        ' · PDF</small></p>').join(''));
      newsLoaded = true;
    } catch (_) { $('newsBody').textContent = 'Could not load the notes.'; }
  }
  $('appNewsBtn').addEventListener('click', () => { show('news'); menu(false); });

  // ---- start ----
  show('radar');
  updateBar();
  // the overlay list is built by radar.js after its meta loads; refresh the menu's map switches then
  setTimeout(syncMenu, 1500);
})();
