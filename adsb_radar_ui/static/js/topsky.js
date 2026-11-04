/* topsky.js - TopSky-style labels for the radar (optional "Label style: TopSky").
 *
 * Ported from MODE-S Wind's ATC display (static/js/atc_display.js): labels in three
 * lines with a leader line, placed automatically so that they do not overlap each
 * other, the aircraft symbols, the vectors or the trails, and the extended label of
 * the aircraft under the mouse or the selected (clicked) one, with the Comm-B values
 * the server decodes from MODE-S Wind's Beast feed (/api/ac/<hex>, ehs.py).
 *
 * A generic European radar-display look after the conventions of systems such as
 * Thales TopSky - not a copy of any one system. A research display, not for ATC.
 */
const Topsky = (() => {
  const LH = 13;                         // line height, px (12 px font)
  const HIT_PX = 10;                     // the mouse within 10 px of the symbol
  const POLL_MS = 2000;
  // 8 directions (NE first), each near (22 px) and far (44 px) = 16 label positions
  const DIRS = [[1, -1], [1, 0], [1, 1], [0, 1], [-1, 1], [-1, 0], [-1, -1], [0, -1]];
  const ALL = Array.from({ length: 16 }, (_, i) => i);
  const pad3 = v => String(v).padStart(3, '0');
  const sgn = v => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v);
  const norm180 = d => ((d % 360) + 540) % 360 - 180;
  const trend = vr => !Number.isFinite(vr) ? ' ' : vr >= 300 ? '↑' : vr <= -300 ? '↓' : ' ';
  const EMG = new Set(['7500', '7600', '7700']);

  // The normal label: callsign (+ emergency squawk) / level, trend and selected level
  // in hundreds of feet (019↑060) / ground speed in tens of knots and type (19 AT75).
  // ac: normalized aircraft (radar.js); cs: the label text; lvl3(alt): 3-digit level.
  function labelLines(ac, cs, lvl3) {
    const sel = Number.isFinite(ac.sel_alt_ft) && ac.sel_alt_ft > 0 ? pad3(Math.round(ac.sel_alt_ft / 100)) : '';
    const l2 = ((Number.isFinite(ac.alt) ? lvl3(ac.alt) : '---') + trend(ac.vr) + sel).trimEnd();
    const gs = Number.isFinite(ac.gs) ? String(Math.round(ac.gs / 10)).padStart(2, '0') : '--';
    return [cs, l2, `${gs} ${ac.type || ''}`.trimEnd()];
  }

  // The six lines of the extended label. x: /api/ac reply (null while on its way);
  // o: { cs, lvl3, center: [lat, lon] }. A value not heard within 20 s shows as ---.
  function extLines(ac, x, o) {
    x = x || {};
    const b5 = x.b50 || {}, b6 = x.b60 || {};
    const vr = ac.vr;
    const l1 = [o.cs, ac.type, ac.reg].filter(Boolean).join('  ');
    const selA = Number.isFinite(ac.sel_alt_ft) && ac.sel_alt_ft > 0 ? ac.sel_alt_ft : x.sel;
    const lvl = (Number.isFinite(ac.alt) ? o.lvl3(ac.alt) : '---') + trend(vr);
    const mode = x.app ? '  APP' : x.ap ? '  AP' : '';
    const l2 = `${lvl}  sel ${selA != null ? pad3(Math.round(selA / 100)) : '---'}  VR ${Number.isFinite(vr) ? sgn(Math.round(vr / 10) * 10) : '---'}${mode}`;
    const gs = Number.isFinite(ac.gs) ? ac.gs : b5.gs;
    const l3 = `GS ${gs != null ? Math.round(gs) : '---'}  TAS ${b5.tas != null ? Math.round(b5.tas) : '---'}  IAS ${b6.ias != null ? Math.round(b6.ias) : '---'}  M${b6.mach != null ? '.' + pad3(Math.round(b6.mach * 1000)) : ' ---'}`;
    // track and heading magnetic (true track less the declination), drift, roll
    const decl = x.decl ?? 0, trkT = Number.isFinite(ac.hdg) ? ac.hdg : b5.trk;
    const mtrk = trkT != null ? Math.round(((trkT - decl) % 360 + 360) % 360) : null;
    const mh = b6.mhdg != null ? Math.round((b6.mhdg % 360 + 360) % 360) : null;
    const dr = mtrk != null && mh != null ? Math.round(norm180(mtrk - mh)) : null;
    const roll = b5.roll;
    const l4 = `MH ${mh != null ? pad3(mh) : '---'}  TRK ${mtrk != null ? pad3(mtrk) : '---'}  DR ${dr == null ? '---' : dr ? (dr < 0 ? 'L' : 'R') + Math.abs(dr) : '0'}  ROLL ${roll == null ? '---' : Math.abs(roll) < 0.5 ? '0' : (roll < 0 ? 'L' : 'R') + Math.round(Math.abs(roll))}`;
    // wind with its head / tail and cross components on the track, the temperature
    const wd = x.wdir, ws = x.wspd, t = x.temp;
    let l5 = wd != null && ws != null ? `W ${pad3(Math.round(wd) % 360 || 360)}/${Math.round(ws)}` : 'W ---';
    if (wd != null && ws != null && trkT != null) {
      const rel = (wd - trkT) * Math.PI / 180, hw = Math.round(ws * Math.cos(rel)), xw = Math.round(ws * Math.sin(rel));
      l5 += `  ${hw >= 0 ? 'HW' : 'TW'} ${Math.abs(hw)}  XW ${Math.abs(xw)}${xw > 0 ? 'R' : xw < 0 ? 'L' : ''}`;
    }
    l5 += `  SAT ${t != null ? sgn(Math.round(t)) : '---'}`;
    // distance and bearing from the radar centre, NACp, squawk
    let l6 = '';
    if (o.center && Number.isFinite(ac.lat) && Number.isFinite(ac.lon)) {
      const dy = (ac.lat - o.center[0]) * 60, dx = (ac.lon - o.center[1]) * 60 * Math.cos(ac.lat * Math.PI / 180);
      l6 = `${Math.hypot(dx, dy).toFixed(1)} NM ${pad3(Math.round((Math.atan2(dx, dy) * 180 / Math.PI + 360) % 360) % 360)}°  `;
    }
    l6 += `NACp ${x.nacp ?? '-'}${ac.squawk ? '  SQ ' + ac.squawk : ''}`;
    return [l1, l2, l3, l4, l5, l6];
  }

  // Labels with leader lines, placed so that they do not overlap: each tries 16
  // positions and takes the one with the least overlap with the labels already
  // placed, the symbols and the obstacles (vectors, trails), inside the canvas; it
  // keeps its last position (pos[key]) while that stays free, so labels do not jump.
  // Extended first, then the selected, then from the lowest up (approach traffic).
  // items: { key, p:{x,y}, lines, sel, ext, alt, emg }
  // P: { text, leader, extBg, emg, font }. Returns key -> label box.
  function drawLabels(g, items, W, H, obst, pos, P) {
    g.save();
    g.font = P.font;
    g.textBaseline = 'top'; g.textAlign = 'left';
    for (const it of items) {
      const ws = it.lines.map((t, i) => g.measureText(t + (i === 0 && it.emg ? ' ' + it.emg : '')).width);
      it.w = Math.ceil(Math.max(...ws)) + 4;
      it.h = it.lines.length * LH + 2;
    }
    const syms = items.map(it => ({ x: it.p.x - 6, y: it.p.y - 6, w: 12, h: 12, key: it.key }));
    const ov = (a, b) => Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) *
                         Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
    const rectFor = (it, k) => {
      const [dx, dy] = DIRS[k % 8], r = k < 8 ? 22 : 44, u = dx && dy ? 0.7071 : 1;
      const ax = it.p.x + dx * r * u, ay = it.p.y + dy * r * u;
      const x = dx > 0 ? ax : dx < 0 ? ax - it.w : ax - it.w / 2;
      const y = dy < 0 ? ay - it.h : dy > 0 ? ay : ay - it.h / 2;
      return { x, y, w: it.w, h: it.h, ax, ay, ux: dx * u, uy: dy * u };
    };
    items.sort((a, b) => (!!b.ext - !!a.ext) || (!!b.sel - !!a.sel) || (a.alt - b.alt));
    const placed = [], rects = {};
    for (const it of items) {
      const prev = pos[it.key];
      const order = prev != null ? [prev, ...ALL.filter(i => i !== prev)] : ALL;
      let best = null, bestCost = Infinity;
      for (const k of order) {
        const R = rectFor(it, k);
        let cost = k >= 8 ? 1 : 0;                       // a near position first
        for (const q of placed) cost += ov(R, q) * 4;
        for (const q of syms) if (q.key !== it.key) cost += ov(R, q) * 8;
        for (const q of obst) cost += ov(R, q) * 2;
        // outside the canvas: a fixed cost, more the more of the label is outside
        if (R.x < 0 || R.y < 0 || R.x + R.w > W || R.y + R.h > H)
          cost += 50 + (R.w * R.h - Math.max(0, Math.min(R.x + R.w, W) - Math.max(R.x, 0)) * Math.max(0, Math.min(R.y + R.h, H) - Math.max(R.y, 0))) * 8;
        if (k === prev && cost <= 1) { best = { k, R }; break; }
        if (cost < bestCost) { bestCost = cost; best = { k, R }; }
      }
      pos[it.key] = best.k;
      placed.push(best.R);
      const R = best.R;
      rects[it.key] = R;
      if (it.ext) {                                      // extended: a backing and a thin frame
        g.globalAlpha = 0.92;
        g.fillStyle = P.extBg;
        g.fillRect(R.x - 3, R.y - 2, R.w + 6, R.h + 3);
        g.globalAlpha = 0.6;
        g.strokeStyle = P.text; g.lineWidth = 1;
        g.strokeRect(Math.round(R.x - 3) + 0.5, Math.round(R.y - 2) + 0.5, Math.round(R.w + 6) - 1, Math.round(R.h + 3) - 1);
        g.globalAlpha = 1;
      }
      g.strokeStyle = it.sel ? P.text : P.leader; g.lineWidth = 1;
      g.beginPath(); g.moveTo(it.p.x + R.ux * 7, it.p.y + R.uy * 7); g.lineTo(R.ax, R.ay); g.stroke();
      g.fillStyle = P.text;
      it.lines.forEach((t, i) => g.fillText(t, R.x + 2, R.y + 1 + i * LH));
      if (it.emg) {                                      // emergency squawk after the callsign
        g.fillStyle = P.emg || P.text;
        g.fillText(it.emg, R.x + 2 + g.measureText(it.lines[0] + ' ').width, R.y + 1);
      }
    }
    g.restore();
    return rects;
  }

  // Small boxes every 6 px along a line (a vector) as label obstacles
  function lineObstacles(x1, y1, x2, y2, out) {
    const n = Math.max(1, Math.ceil(Math.hypot(x2 - x1, y2 - y1) / 6));
    for (let i = 0; i <= n; i++) {
      const x = x1 + (x2 - x1) * i / n, y = y1 + (y2 - y1) * i / n;
      out.push({ x: x - 2, y: y - 2, w: 4, h: 4 });
    }
  }

  // Hover + selection on the radar canvas. opts: { active(), targets() -> [[key, x, y]],
  // rects() -> label boxes of the last draw }. The aircraft under the mouse gets the
  // extended label; a click selects an aircraft (extended until clicked again or
  // another / empty spot is clicked). Values from /api/ac/<key> every 2 s.
  function interaction(canvas, opts) {
    let hov = null, sel = null, mx = -1, my = -1;
    const data = {}, timers = {};
    const poll = k => fetch(`/api/ac/${encodeURIComponent(k)}`, { cache: 'no-store' })
      .then(r => (r.ok ? r.json() : null)).catch(() => null)
      .then(d => { if (d && (k === hov || k === sel)) data[k] = d; });
    function watch() {
      for (const k of Object.keys(timers)) {
        if (k !== hov && k !== sel) { clearInterval(timers[k]); delete timers[k]; delete data[k]; }
      }
      for (const k of [hov, sel]) {
        if (k && !timers[k]) {
          poll(k);
          timers[k] = setInterval(() => { if (!document.hidden) poll(k); }, POLL_MS);
        }
      }
    }
    function nearest() {
      let best = null, bd = HIT_PX;
      for (const [k, x, y] of opts.targets()) {
        const d = Math.hypot(x - mx, y - my);
        if (d <= bd) { bd = d; best = k; }
      }
      return best;
    }
    function onLabel(k) {
      const R = k && (opts.rects() || {})[k];
      return !!R && mx >= R.x - 4 && mx <= R.x + R.w + 4 && my >= R.y - 3 && my <= R.y + R.h + 2;
    }
    canvas.addEventListener('mousemove', e => {
      const r = canvas.getBoundingClientRect();
      mx = e.clientX - r.left; my = e.clientY - r.top;
      if (!opts.active()) { if (hov) { hov = null; watch(); } canvas.style.cursor = ''; return; }
      const k = onLabel(hov) ? hov : nearest();
      canvas.style.cursor = k ? 'pointer' : '';
      if (k !== hov) { hov = k; watch(); }
    });
    canvas.addEventListener('mouseleave', () => { mx = my = -1; if (hov) { hov = null; watch(); } canvas.style.cursor = ''; });
    canvas.addEventListener('click', e => {
      if (!opts.active()) return;
      const r = canvas.getBoundingClientRect();
      mx = e.clientX - r.left; my = e.clientY - r.top;
      const k = nearest();
      if (k) sel = (k === sel) ? null : k;     // click an aircraft: select it / click again: release
      else if (!onLabel(sel)) sel = null;      // click on empty scope: release (its own label: keep)
      watch();
    });
    return {
      hover: () => hov, selected: () => sel, data: k => data[k] || null,
      clear: () => { hov = sel = null; watch(); },
      forget: present => {           // aircraft gone from the feed
        if (hov && !present.has(hov)) hov = null;
        if (sel && !present.has(sel)) sel = null;
        watch();
      },
    };
  }

  return { labelLines, extLines, drawLabels, lineObstacles, interaction, EMG };
})();
