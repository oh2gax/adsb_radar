/* replay.js - replay of the recorded traffic on the scope (desktop page; the recorder is replay.py).
 *
 * The scope is fed from the recording instead of the live feed: chunks of 5 minutes
 * (/api/replay/chunk, every 1-10 s depending on the speed), positions interpolated between the samples,
 * the labels and the extended label's Comm-B values as they were, the go-around marks from the recorded
 * events, the QNH from the METAR of that time, the history line from the recording. radar.js asks
 * window.Replay for the time (radarNow) and the Comm-B values; everything else goes through its normal
 * update (ingestAircraft), so the scope behaves exactly as live.
 *
 * The bar at the bottom of the scope: REPLAY / LIVE, the day (◀ day ▶, the last REPLAY_DAYS days), a
 * link to share, −10 / −1 min, play / pause, +1 / +10 min, the replay time, a UTC time box (14:40,
 * 1440, 14:40:30), the speeds 1×–60×, and a 24-hour slider with the day's go-arounds. An inverted
 * banner at the top of the scope says REPLAY. A link /?replay=2026-11-04T15:33Z&speed=10&sel=461AAA
 * &c=60.32,24.96&r=20 opens that moment.
 *
 * The mobile app (/app, window.RADAR_APP) gets the same controls as a sheet at the bottom of the scope
 * (bigger buttons, the phone's number keyboard for the UTC time, Share instead of Link); its top bar
 * says REPLAY instead of a banner (app.js), and /app?replay=… opens a moment there.
 */
(function () {
  'use strict';
  const stage = document.querySelector('main.stage, main.app-stage');
  const APP = !!window.RADAR_APP;
  if (!stage || typeof ingestAircraft !== 'function') return;
  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) { return null; } };
  const esc = t => String(t ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const pad = n => String(n).padStart(2, '0');
  const DAY = 86400, CHUNK_S = 300, CHUNK_MIN = 5;
  const SPEEDS = [1, 2, 5, 10, 30, 60];
  const WD = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
  const GA_MARK_SEC = 1800;              // a GA mark lasts until the landing, at most 30 min (as live)

  const S = {
    active: false, playing: false, t: 0, speed: SPEEDS.includes(+ls('rpSpeed')) ? +ls('rpSpeed') : 10,
    range: null, events: [], evFrom: 0, evTo: -1, lastTick: 0, histT: 0, pendingSel: null, pendingUntil: 0, note: '',
  };
  const cache = new Map();               // `${m0}:${step}` -> {m0, step, data, loading, err}
  let tl = new Map(), tlKey = '';        // icao -> {s, id, cb, decl}: the loaded chunks merged

  const stepFor = sp => sp <= 5 ? 1 : sp <= 10 ? 2 : sp <= 30 ? 5 : 10;
  const dayStart = t => Math.floor(t / DAY) * DAY;
  const fmtT = t => { const d = new Date(t * 1000); return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}Z`; };
  const fmtD = t => { const d = new Date(t * 1000); return `${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}.${d.getUTCFullYear()}`; };

  // ---- data ----
  async function loadRange() {
    try { S.range = await (await fetch('/api/replay/range', { cache: 'no-store' })).json(); } catch (_) { S.range = null; }
    return S.range;
  }
  function fetchChunk(m0, step) {
    const key = m0 + ':' + step;
    if (cache.has(key)) return;
    const e = { m0, step, data: null, loading: true, err: null };
    cache.set(key, e);
    fetch(`/api/replay/chunk?t=${m0}&min=${CHUNK_MIN}&step=${step}`)
      .then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))
      .then(d => { e.data = d; })
      .catch(err => { e.err = String(err && err.message || err); setTimeout(() => cache.delete(key), 5000); })
      .finally(() => { e.loading = false; tlKey = ''; });
  }
  function wanted(t) {
    const step = stepFor(S.speed), m0 = Math.floor(t / CHUNK_S) * CHUNK_S;
    const keys = [[m0, step]];
    if (t - m0 > CHUNK_S - Math.max(60, S.speed * 25)) keys.push([m0 + CHUNK_S, step]);    // the next one in time
    return keys;
  }
  function current(t) { const [m0, step] = wanted(t)[0]; return cache.get(m0 + ':' + step); }
  function rebuildTimeline(t) {
    const step = stepFor(S.speed), m0 = Math.floor(t / CHUNK_S) * CHUNK_S;
    const use = [m0 - CHUNK_S, m0, m0 + CHUNK_S].map(m => cache.get(m + ':' + step)).filter(e => e && e.data);
    const key = use.map(e => e.m0).join(',') + ':' + step;
    if (key === tlKey) return;
    tlKey = key;
    tl = new Map();
    for (const e of use) for (const [icao, a] of Object.entries(e.data.ac || {})) {
      const x = tl.get(icao) || { s: [], id: [], cb: [], decl: a.decl };
      x.s.push(...a.s); x.id.push(...a.id); x.cb.push(...a.cb);
      if (a.decl != null) x.decl = a.decl;
      tl.set(icao, x);
    }
    // forget chunks far from the replay time
    for (const [k, e] of cache) if (!e.loading && (e.m0 < m0 - 2 * CHUNK_S || e.m0 > m0 + 3 * CHUNK_S || e.step !== step)) cache.delete(k);
  }
  function lastIdx(arr, t) {               // the last entry with arr[i][0] <= t (sorted), or -1
    let lo = 0, hi = arr.length - 1, r = -1;
    while (lo <= hi) { const mid = (lo + hi) >> 1; if (arr[mid][0] <= t) { r = mid; lo = mid + 1; } else hi = mid - 1; }
    return r;
  }
  async function loadEvents(t) {
    const d0 = dayStart(t);
    if (t >= S.evFrom && t <= S.evTo) return;
    S.evFrom = d0 - GA_MARK_SEC; S.evTo = d0 + DAY;
    try {
      const j = await (await fetch(`/api/replay/events?t0=${S.evFrom}&t1=${S.evTo}`)).json();
      S.events = j.events || [];
    } catch (_) { S.events = []; }
    drawMarks();
  }
  function gaFor(icao, t) {
    let ga = null;
    for (const e of S.events) {
      if (e.icao !== icao || e.t > t) continue;
      if (e.kind === 'ga' && t - e.t <= GA_MARK_SEC) ga = e;
      else if (e.kind === 'arr' && ga && e.t >= ga.t) ga = null;           // landed after it
    }
    return ga ? { age: t - ga.t, n: ga.ga || 1, rwy: ga.rwy } : null;
  }
  // the aircraft at time t, as /api/aircraft gives them
  function stateAt(t) {
    const step = stepFor(S.speed), maxAge = Math.max(4, step * 2.5), out = [];
    for (const [icao, a] of tl) {
      const i = lastIdx(a.s, t);
      if (i < 0) continue;
      const p = a.s[i];
      if (t - p[0] > maxAge || p[1] == null || p[2] == null) continue;
      let lat = p[1], lon = p[2], alt = p[3], gs = p[4], trk = p[5];
      const q = a.s[i + 1];
      if (q && q[1] != null && q[0] - p[0] <= step * 3 + 1 && q[0] > p[0]) {
        const f = (t - p[0]) / (q[0] - p[0]);
        lat += (q[1] - p[1]) * f; lon += (q[2] - p[2]) * f;
        if (alt != null && q[3] != null) alt = Math.round(alt + (q[3] - alt) * f);
        if (gs != null && q[4] != null) gs = Math.round(gs + (q[4] - gs) * f);
        if (trk != null && q[5] != null) trk = (trk + (((q[5] - trk + 540) % 360) - 180) * f + 360) % 360;
      }
      const j = lastIdx(a.id, t), id = j >= 0 ? a.id[j] : (a.id[0] || []);
      out.push({ hex: icao, flight: id[1] || '', squawk: id[2] || null, sel_alt_ft: id[3] ?? null, reg: id[4] || null, type: id[5] || null,
                 lat, lon, alt_baro: alt, gs, track: trk, baro_rate: p[6], pos_src: p[7] === 0 ? 'adsb' : 'feed', ga: gaFor(icao, t) });
    }
    return out;
  }
  function acData(hex) {                   // the extended label's Comm-B values at the replay time
    const a = tl.get(hex);
    if (!a) return null;
    const i = lastIdx(a.cb, S.t);
    return Object.assign({ decl: a.decl ?? 0 }, i >= 0 ? a.cb[i][1] : {});
  }
  function applyQnh() {                    // Auto QNH: the METAR of that time
    const c = current(S.t);
    const m = c && c.data && c.data.metar && c.data.metar[0];
    const q = m && /\bQ(\d{4})\b/.exec(m.text || '');
    if (q && qnhAuto) { qnh = +q[1]; const qi = document.getElementById('qnhInput'); if (qi) qi.value = q[1];
      const info = document.getElementById('qnhInfo'); if (info) info.textContent = `REPLAY · METAR ${m.station || ''}: Q${q[1]}`; }
  }

  // ---- the clock ----
  function tick() {
    const now = performance.now(), dt = S.lastTick ? (now - S.lastTick) / 1000 : 0;
    S.lastTick = now;
    if (!S.active) return;
    for (const [m0, step] of wanted(S.t)) fetchChunk(m0, step);
    const c = current(S.t);
    const ready = c && c.data;
    // close to the end of the recording: ask what is recorded now (a replay can run up to a minute ago)
    if (S.range && S.range.last && S.t > S.range.last - 120 && Date.now() - (S.rangeAsked || 0) > 30000) {
      S.rangeAsked = Date.now(); loadRange();
    }
    if (S.playing && ready) {
      S.t += Math.min(dt, 0.5) * S.speed;
      const end = (S.range && S.range.last) || (Date.now() / 1000 - 60);
      if (S.t >= end) { S.t = end; S.playing = false; S.note = 'End of the recording'; }
      if (dayStart(S.t) !== S.day) { S.day = dayStart(S.t); loadEvents(S.t); buildDays(); }
    }
    rebuildTimeline(S.t);
    if (ready) {
      const n = ingestAircraft(stateAt(S.t), S.t * 1000);
      lastDataOkMs = Date.now();
      setStatus(`REPLAY ${fmtD(S.t)} ${fmtT(S.t)} · ${S.speed}× · Targets: ${n}`, false);
      if (!n && !S.note) S.note = 'No recording at this time';
      else if (n && S.note === 'No recording at this time') S.note = '';
      applyQnh();
      if (S.pendingSel) {
        if (aircraft.has(S.pendingSel)) { window.radarSelect(S.pendingSel); S.pendingSel = null; }
        else if (S.t > S.pendingUntil) S.pendingSel = null;
      }
      // the history line: fetched for an hour past the replay time; ask again after half an hour
      if (selectedHex() && Math.abs(S.t - S.histT) > 1800) { S.histT = S.t; hist = null; histLastSel = null; }
    } else if (c && c.err) S.note = 'Recording not available: ' + c.err;
    updateUi(!ready && !(c && c.err) ? 'loading…' : '');
  }
  setInterval(tick, 100);

  // ---- control ----
  function seek(t) {
    const r = S.range;
    const lo = r && r.first ? r.first : t, hi = (r && r.last) || Date.now() / 1000;
    t = Math.max(lo, Math.min(hi, t));
    const jump = Math.abs(t - S.t) > 20 || t < S.t;
    S.t = t; S.note = '';
    if (jump) { resetTimeState(); hist = null; histLastSel = null; S.histT = t; }
    if (dayStart(t) !== S.day) { S.day = dayStart(t); buildDays(); }
    loadEvents(t);
    tlKey = '';
    updateUi();
  }
  async function start(t, o) {
    o = o || {};
    if (!S.range || o.reload) await loadRange();
    if (!S.range || !S.range.first) { show(true); S.note = 'Nothing recorded yet'; updateUi(); return; }
    if (!S.active) {
      S.active = true;
      resetTimeState(); aircraft = new Map(); hist = null; histLastSel = null;
    }
    if (o.speed && SPEEDS.includes(o.speed)) S.speed = o.speed;
    if (o.center) setCenter(o.center[0], o.center[1], true);
    if (o.range) setRange(o.range);
    S.t = 0;
    seek(t == null ? S.range.last - 600 : t);
    if (o.sel) { S.pendingSel = String(o.sel).toUpperCase(); S.pendingUntil = S.t + 900; }
    S.playing = o.play !== false;
    show(true);
  }
  function live() {
    if (!S.active) return;
    S.active = false; S.playing = false; S.note = '';
    resetTimeState(); aircraft = new Map(); hist = null; histLastSel = null;
    cache.clear(); tl = new Map(); tlKey = '';
    fetchData();
    if (qnhAuto) fetchQnh();
    if (location.search.includes('replay=')) history.replaceState(null, '', location.pathname);
    updateUi();
  }

  // ---- the bar and the banner ----
  const DESK_HTML = `<div id="rpBanner" class="rp-banner" hidden></div>
    <div id="rpBar" class="rp-window scope-obst" hidden>
      <div class="rp-row"><button type="button" class="rp-b" data-a="replay">▶ REPLAY</button><button type="button" class="rp-b" data-a="live">● LIVE</button>
        <button type="button" class="rp-b" data-a="dprev" title="The day before">◀</button><select id="rpDay" title="The day (UTC)"></select><button type="button" class="rp-b" data-a="dnext" title="The day after">▶</button>
        <span id="rpInfo" class="rp-info"></span><span class="rp-fill"></span>
        <button type="button" class="rp-b" data-a="link" title="Copy a link to this moment">Link</button><button type="button" class="rp-b" data-a="close" title="Close (back to live)">✕</button></div>
      <div class="rp-row"><button type="button" class="rp-b" data-j="-600">−10 min</button><button type="button" class="rp-b" data-j="-60">−1 min</button>
        <button type="button" class="rp-b rp-play" data-a="play" title="Play / pause (space)">❚❚</button>
        <button type="button" class="rp-b" data-j="60">+1 min</button><button type="button" class="rp-b" data-j="600">+10 min</button>
        <span id="rpTime" class="rp-time">--:--:--Z</span>
        <form id="rpForm" class="rp-form" autocomplete="off"><label>UTC <input id="rpUtc" maxlength="8" placeholder="14:40" title="Jump to a UTC time of the chosen day: 14:40, 1440 or 14:40:30"></label><button type="submit" class="rp-b">Go</button></form>
        <span class="rp-fill"></span><span class="rp-seg" id="rpSpeeds">${SPEEDS.map(v => `<button type="button" class="rp-b" data-sp="${v}">${v}×</button>`).join('')}</span></div>
      <div class="rp-row rp-slrow"><div class="rp-slider"><div id="rpMarks" class="rp-marks"></div>
        <input id="rpSlider" type="range" min="0" max="86399" step="1" value="0" aria-label="Time of the day (UTC)"><div class="rp-ticks">${[0, 3, 6, 9, 12, 15, 18, 21, 24].map(h => `<span style="left:${h / 24 * 100}%">${pad(h)}</span>`).join('')}</div></div></div>
      <div id="rpNote" class="rp-note"></div>
    </div>`;
  // the app: a sheet at the bottom of the scope, the same controls (ids / data-*) with bigger buttons
  const APP_HTML = `<div id="rpBanner" class="rp-banner" hidden></div>
    <div id="rpBar" class="rp-window app-rp scope-obst" hidden>
      <div class="rp-row"><span id="rpTime" class="rp-time">LIVE</span><span class="rp-fill"></span>
        <button type="button" class="rp-b" data-a="link" title="Share a link to this moment">Share</button><button type="button" class="rp-b" data-a="live">● LIVE</button><button type="button" class="rp-b" data-a="close" aria-label="Close (back to live)">✕</button></div>
      <div class="rp-row"><button type="button" class="rp-b" data-a="dprev" aria-label="The day before">◀</button><select id="rpDay" aria-label="The day (UTC)"></select><button type="button" class="rp-b" data-a="dnext" aria-label="The day after">▶</button>
        <span class="rp-fill"></span>
        <form id="rpForm" class="rp-form" autocomplete="off"><label>UTC <input id="rpUtc" maxlength="8" inputmode="numeric" placeholder="1440" aria-label="Jump to a UTC time of the chosen day: 1440 or 144030"></label><button type="submit" class="rp-b">Go</button></form></div>
      <div class="rp-row rp-slrow"><div class="rp-slider"><div id="rpMarks" class="rp-marks"></div>
        <input id="rpSlider" type="range" min="0" max="86399" step="1" value="0" aria-label="Time of the day (UTC)"><div class="rp-ticks">${[0, 6, 12, 18, 24].map(h => `<span style="left:${h / 24 * 100}%">${pad(h)}</span>`).join('')}</div></div></div>
      <div class="rp-row app-rp-big"><button type="button" class="rp-b" data-j="-600">−10′</button><button type="button" class="rp-b" data-j="-60">−1′</button>
        <button type="button" class="rp-b rp-play" data-a="play" aria-label="Play / pause">▶</button>
        <button type="button" class="rp-b" data-j="60">+1′</button><button type="button" class="rp-b" data-j="600">+10′</button></div>
      <div class="rp-row"><span class="rp-seg app-rp-sp" id="rpSpeeds">${SPEEDS.map(v => `<button type="button" class="rp-b" data-sp="${v}">${v}×</button>`).join('')}</span></div>
      <div class="app-rp-foot"><span id="rpNote" class="rp-note"></span><span id="rpInfo" class="rp-info"></span></div>
    </div>`;
  stage.insertAdjacentHTML('beforeend', APP ? APP_HTML : DESK_HTML);
  const bar = document.getElementById('rpBar'), banner = document.getElementById('rpBanner');
  const daySel = document.getElementById('rpDay'), slider = document.getElementById('rpSlider');
  function show(v) { bar.hidden = !v; ls('rpOpen', v ? '1' : '0'); if (v) { buildDays(); drawMarks(); } updateUi(); sheetSize(); requestDraw(); }
  // the app: the zoom buttons stay above the sheet (app.css uses --rp-h)
  function sheetSize() { if (APP) stage.style.setProperty('--rp-h', (bar.hidden ? 0 : bar.offsetHeight) + 'px'); }
  if (APP && typeof ResizeObserver === 'function') new ResizeObserver(sheetSize).observe(bar);
  function buildDays() {
    const keep = (S.range && S.range.days_kept) || 30, have = new Set(((S.range && S.range.days) || []).filter(d => d.minutes > 0).map(d => d.day));
    const today = dayStart(Date.now() / 1000);
    let html = '';
    for (let k = 0; k < keep; k++) {
      const d0 = today - k * DAY, iso = new Date(d0 * 1000).toISOString().slice(0, 10);
      html += `<option value="${d0}"${have.has(iso) ? '' : ' disabled'}${S.day === d0 ? ' selected' : ''}>${WD[new Date(d0 * 1000).getUTCDay()]} ${APP ? fmtD(d0).slice(0, 6) : fmtD(d0)}</option>`;
    }
    daySel.innerHTML = html;
  }
  function drawMarks() {
    const el = document.getElementById('rpMarks');
    if (!el || S.day == null) return;
    // go-arounds close together share one mark ("3GA"; the title lists them): 1.5 % of the day on the
    // desktop (~22 min), 5 % in the app's narrow sheet
    const gap = (APP ? 0.05 : 0.015) * DAY, groups = [];
    for (const e of S.events.filter(e => e.kind === 'ga' && e.t >= S.day && e.t < S.day + DAY).sort((a, b) => a.t - b.t)) {
      const g = groups[groups.length - 1];
      if (g && e.t - g[0].t < gap) g.push(e); else groups.push([e]);
    }
    const mid = g => (g[0].t + g[g.length - 1].t) / 2;
    for (let k = 1; k < groups.length; k++)             // marks still too close: one mark
      if (mid(groups[k]) - mid(groups[k - 1]) < gap) { groups[k - 1].push(...groups[k]); groups.splice(k, 1); k--; }
    el.innerHTML = groups.map(g => `<span style="left:${(g[0].t + g[g.length - 1].t) / 2 / DAY * 100 - S.day / DAY * 100}%" title="${esc(g.map(e => (e.callsign || e.icao) + ' ' + fmtT(e.t) + ' ' + (e.rwy || '')).join('\n'))}">${g.length > 1 ? g.length : ''}GA</span>`).join('');
  }
  function updateUi(extra) {
    document.querySelectorAll('#rpBar [data-a="replay"]').forEach(b => b.classList.toggle('on', S.active));
    document.querySelectorAll('#rpBar [data-a="live"]').forEach(b => b.classList.toggle('on', !S.active));
    document.querySelectorAll('#rpSpeeds [data-sp]').forEach(b => b.classList.toggle('on', +b.dataset.sp === S.speed));
    bar.querySelector('[data-a="play"]').textContent = S.playing ? '❚❚' : '▶';
    document.getElementById('rpTime').textContent = S.active ? fmtT(S.t) : 'LIVE';
    if (S.active && document.activeElement !== slider) slider.value = String(Math.floor(S.t - S.day));
    if (S.active && daySel.value !== String(S.day)) daySel.value = String(S.day);
    const r = S.range;
    document.getElementById('rpInfo').textContent = r && r.first ? `recorded ${fmtD(r.first).slice(0, 6)}–${fmtD(r.last).slice(0, 6)}` : '';
    const hint = APP && !S.active && !S.note && !extra ? '▶ plays from 10 min ago, or pick a day and a time' : '';
    document.getElementById('rpNote').textContent = [S.note, extra, hint].filter(Boolean).join(' · ');
    document.body.classList.toggle('replay-on', S.active);
    document.body.classList.toggle('replay-open', !bar.hidden);
    banner.hidden = !S.active;
    if (S.active) banner.textContent = `REPLAY · ${fmtD(S.t)} ${fmtT(S.t)} · ${S.playing ? S.speed + '×' : 'PAUSED'}`;
  }

  bar.addEventListener('click', e => {
    const b = e.target.closest('button'); if (!b) return;
    if (b.dataset.j) { if (!S.active) start(Date.now() / 1000 - 600 + +b.dataset.j, { play: false }); else seek(S.t + +b.dataset.j); return; }
    if (b.dataset.sp) { S.speed = +b.dataset.sp; ls('rpSpeed', String(S.speed)); tlKey = ''; updateUi(); return; }
    const a = b.dataset.a;
    if (a === 'replay') { if (!S.active) start(null); }
    else if (a === 'live') live();
    else if (a === 'close') { live(); show(false); }
    else if (a === 'play') { if (!S.active) start(null); else { S.playing = !S.playing; S.note = ''; updateUi(); } }
    else if (a === 'dprev' || a === 'dnext') {
      const base = S.active ? S.t : Date.now() / 1000;
      const t = base + (a === 'dprev' ? -DAY : DAY);
      if (!S.active) start(t, { play: false }); else seek(t);
    } else if (a === 'link') copyLink();
  });
  daySel.addEventListener('change', () => {
    const d0 = +daySel.value, tod = S.active ? S.t - S.day : 12 * 3600;
    if (!S.active) start(d0 + tod, { play: false }); else seek(d0 + tod);
  });
  slider.addEventListener('input', () => { if (!S.active) return; seek(S.day + +slider.value); });
  // the UTC time box: 14:40, 1440, 14:40:30 on the chosen day
  document.getElementById('rpForm').addEventListener('submit', e => {
    e.preventDefault();
    const inp = document.getElementById('rpUtc');
    const m = /^\s*(\d{1,2}):?(\d{2})(?::?(\d{2}))?\s*z?\s*$/i.exec(inp.value || '');
    if (!m || +m[1] > 23 || +m[2] > 59 || (m[3] && +m[3] > 59)) { inp.classList.add('invalid'); return; }
    inp.classList.remove('invalid');
    const d0 = S.active ? S.day : dayStart(Date.now() / 1000);
    const t = d0 + (+m[1]) * 3600 + (+m[2]) * 60 + (+(m[3] || 0));
    if (t > Date.now() / 1000) { S.note = 'That time is still ahead'; updateUi(); return; }
    const wasPlaying = S.playing;
    if (!S.active) start(t, { play: false });
    else { seek(t); S.playing = false; }
    S.note = wasPlaying ? 'Paused at ' + fmtT(t) : '';
    inp.value = ''; inp.blur();
  });
  document.addEventListener('keydown', e => {
    if (!S.active || /^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || '')) return;
    if (e.key === ' ') { e.preventDefault(); S.playing = !S.playing; updateUi(); }
  });
  function copyLink() {
    const t = S.active ? S.t : Date.now() / 1000;
    const p = new URLSearchParams({ replay: new Date(Math.floor(t) * 1000).toISOString().replace('.000', ''), speed: String(S.speed),
                                    c: `${center.lat.toFixed(4)},${center.lon.toFixed(4)}`, r: String(Math.round(rangeNm)) });
    const sel = selectedHex(); if (sel) p.set('sel', sel);
    const url = `${location.origin}${location.pathname}?${p.toString()}`;
    const done = () => { S.note = 'Link copied'; updateUi(); setTimeout(() => { if (S.note === 'Link copied') { S.note = ''; updateUi(); } }, 2500); };
    if (APP && navigator.share) {          // the phone's share sheet (messages, mail …)
      navigator.share({ title: `RADAR replay ${fmtD(t)} ${fmtT(t)}`, url }).catch(err => { if (!err || err.name !== 'AbortError') { S.note = url; updateUi(); } });
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(url).then(done, () => { S.note = url; updateUi(); });
    else { S.note = url; updateUi(); }
  }

  // the sidebar's Replay block
  const openBtn = document.getElementById('rpOpen');
  if (openBtn) openBtn.addEventListener('click', () => { show(bar.hidden); if (!bar.hidden && !S.active) loadRange().then(() => { buildDays(); updateUi(); }); });

  // a link to a moment: /?replay=2026-11-04T15:33Z&speed=10&sel=461AAA&c=60.32,24.96&r=20
  const q = new URLSearchParams(location.search);
  if (q.get('replay')) {
    const v = q.get('replay'), t = /^\d+$/.test(v) ? +v : Date.parse(/Z$|[+-]\d\d:?\d\d$/.test(v) ? v : v + 'Z') / 1000;
    const c = (q.get('c') || '').split(',').map(Number);
    if (Number.isFinite(t)) start(t, { speed: +q.get('speed') || undefined, sel: q.get('sel') || null, play: true,
      center: c.length === 2 && c.every(Number.isFinite) ? c : null, range: +q.get('r') || null });
  } else if (ls('rpOpen') === '1') { loadRange().then(() => show(true)); }

  window.Replay = {
    get active() { return S.active; },
    get isOpen() { return !bar.hidden; },
    open: () => { show(true); if (!S.active) loadRange().then(() => { buildDays(); updateUi(); }); },
    close: () => { live(); show(false); },
    nowMs: () => S.t * 1000,
    acData,
    start: (t, o) => start(t, o),
    live,
    state: () => ({ active: S.active, t: S.t, speed: S.speed, playing: S.playing, note: S.note, chunks: cache.size, aircraft: tl.size }),
  };
})();
