/* reports.js - pilot reports (ARS / WXREP / SIGMET) and the EFHK METARs with a windshear group, from
 * MODE-S Wind's database (/api/wx/reports, the last 24 h). Shared by the desktop METAR & TAF window
 * (wx.js) and the app's METAR & TAF page (app.js): filters, the rows, the new-report dot and the ARS
 * markers on the scope (radar.js draws window.radarArsMarks).
 *
 * Colour only for alarms: SEV / HVY phenomena in red (the theme decides, see the CSS); the rest in the
 * theme's text colour, the phenomena in bold.
 */
const WxReports = (() => {
  'use strict';
  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) { return null; } };
  const esc = t => String(t ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const pad = n => String(n).padStart(2, '0');
  const hhmm = t => { const d = new Date(t * 1000); return pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()); };
  const dayKey = t => new Date(t * 1000).toISOString().slice(0, 10);
  const GROUP = { ARS: 'ARS', AIREP: 'ARS', WXREP: 'WXREP', SIGMET: 'SIGMET', AIRMET: 'SIGMET' };
  const PH_RE = /\b((?:FBL|LGT|MOD|SEV|HVY)\s+)?(TURB|ICE|ICG|MTW|LLWS|WS|INVERSION|INV|TSGR|TS|VA|SS|CB|DS)\b/g;
  const WS_RE = /\bWS\s+(?:ALL\s+RWY|(?:R(?:WY)?\s?\d{2}[LRC]?\s*)+)/g;
  const POLL_MS = 5 * 60 * 1000;

  let data = null, err = null, loading = null;
  const subs = [];
  const opt = {
    hours: ls('repHours') === '24' ? 24 : 12,
    near: ls('repNear') === '1',
    kinds: (() => { try { return JSON.parse(ls('repKinds')) || null; } catch (_) { return null; } })() ||
           { ARS: true, WXREP: true, SIGMET: true, METARWS: true },
    onScope: ls('repOnScope') === '1',
  };

  function height(r) {
    // above the transition altitude (5000 ft in Finland) as a flight level, as the reports give it
    const f = v => v == null ? '' : v === 0 ? 'SFC' : v > 5000 ? 'FL' + String(Math.round(v / 100)).padStart(3, '0') : v + ' ft';
    if (r.lo_ft == null && r.hi_ft == null) return '';
    if (r.lo_ft === r.hi_ft || r.hi_ft == null) return f(r.lo_ft);
    return `${f(r.lo_ft)}–${f(r.hi_ft)}`.replace(/ ft–/, '–');
  }
  // all items of the last 24 h, newest first: {t, kind, group, ident, phen, height, near, raw, sev, lat, lon}
  function items() {
    if (!data) return [];
    const out = [];
    for (const r of data.reports || []) {
      const g = GROUP[r.kind];
      if (!g) continue;
      out.push({ t: r.obs_t || r.t, kind: r.kind, group: g, ident: r.ident || '', phen: r.phen || '', height: height(r),
                 near: !!r.near, raw: r.raw || '', sev: /\b(SEV|HVY)\b/.test(r.phen || ''), lat: r.lat, lon: r.lon });
    }
    for (const m of data.metars || [])
      out.push({ t: m.t, kind: 'METAR', group: 'METARWS', ident: data.station || '', phen: 'WS ' + (m.ws === 'ALL' ? 'ALL RWY' : m.ws),
                 height: '', near: true, raw: m.raw || '', sev: false });
    out.sort((a, b) => b.t - a.t);
    return out;
  }
  function filtered() {
    const since = Date.now() / 1000 - opt.hours * 3600;
    return items().filter(i => i.t >= since && opt.kinds[i.group] && (!opt.near || i.near));
  }
  function hl(raw, metar) {
    const h = esc(raw);
    if (metar) return h.replace(WS_RE, m => `<b>${m.trim()}</b> `);
    return h.replace(PH_RE, m => `<b${/^(SEV|HVY)/.test(m) ? ' class="rp-sev"' : ''}>${m}</b>`);
  }
  // the rows (a line at each UTC day change)
  function html(list) {
    if (err) return `<p class="rp-none">${esc(err)}</p>`;
    if (!data) return '<p class="rp-none">Loading…</p>';
    if (!list.length) return `<p class="rp-none">No reports in the last ${opt.hours} h${opt.near ? ' near ' + esc(data.station || 'EFHK') : ''}.</p>`;
    let out = '', prev = dayKey(Date.now() / 1000);
    for (const i of list) {
      const day = dayKey(i.t);
      if (day !== prev) { const d = new Date(i.t * 1000); out += `<div class="rp-day">── ${pad(d.getUTCDate())}.${pad(d.getUTCMonth() + 1)}. ──</div>`; prev = day; }
      out += `<div class="rp-it"><div class="rp-h"><span class="rp-t">${hhmm(i.t)}</span><span class="rp-k">${esc(i.kind)}</span>` +
             `<span>${esc(i.ident)}</span><span class="${i.sev ? 'rp-sev' : ''}">${esc(i.phen)}</span><span>${esc(i.height)}</span>` +
             (i.near && i.group !== 'METARWS' ? `<span class="rp-near">${esc(data.station || 'EFHK')}</span>` : '') + '</div>' +
             `<div class="rp-raw">${hl(i.raw, i.group === 'METARWS')}</div></div>`;
    }
    return out;
  }
  function footer() {
    if (!data || err) return '';
    const c = data.checked ? new Date(data.checked * 1000).toISOString().slice(11, 16) + 'Z' : '–';
    return `FMI ilmailusaa.fi via MODE-S Wind · checked ${c} · ${esc(data.station || 'EFHK')} = within ${data.near_nm || 30} NM of the airport, at or below 10 000 ft`;
  }

  // ---- the new-report dot: a report near the airport newer than the last time the list was seen ----
  function newest() { let m = 0; for (const i of items()) if (i.near && i.t > m) m = i.t; return m; }
  function hasNew() { const n = newest(); return n > 0 && n > (+ls('repSeen') || 0); }
  function markSeen() {                 // the list is on screen: what it shows is seen
    const n = newest();
    if (n && n > (+ls('repSeen') || 0)) { ls('repSeen', String(n)); notify(); }
  }
  // first use: what is already there is not "new"
  function firstSeen() { if (ls('repSeen') == null) { const n = newest(); ls('repSeen', String(n || Date.now() / 1000)); } }

  // ---- ARS markers on the scope (radar.js draws window.radarArsMarks) ----
  function updateMarks() {
    if (!opt.onScope || !data) { window.radarArsMarks = null; }
    else {
      const since = Date.now() / 1000 - opt.hours * 3600;
      window.radarArsMarks = items().filter(i => i.group === 'ARS' && i.t >= since && Number.isFinite(i.lat) && Number.isFinite(i.lon))
        .map(i => ({ lat: i.lat, lon: i.lon, sev: i.sev, text: [i.kind, i.phen, i.height, hhmm(i.t) + 'Z'].filter(Boolean).join(' ') }));
    }
    if (typeof requestDraw === 'function') requestDraw();
  }

  function notify() { updateMarks(); for (const f of subs) { try { f(); } catch (_) {} } }
  async function load() {
    if (loading) return loading;
    loading = (async () => {
      try {
        const d = await (await fetch('/api/wx/reports', { cache: 'no-store' })).json();
        data = d; err = d.error || null;
        firstSeen();
      } catch (_) { err = 'Radar server not reachable.'; }
      loading = null;
      notify();
    })();
    return loading;
  }
  function set(k, v) {
    opt[k] = v;
    ls('repHours', String(opt.hours)); ls('repNear', opt.near ? '1' : '0');
    ls('repKinds', JSON.stringify(opt.kinds)); ls('repOnScope', opt.onScope ? '1' : '0');
    notify();
  }
  // the choices above the list (the same for the desktop window and the app page)
  function barHtml() {
    const on = c => c ? ' class="on"' : '', k = opt.kinds, st = esc((data && data.station) || 'EFHK');
    return `<span class="rp-seg" data-rp="hours"><button type="button" data-v="12"${on(opt.hours === 12)}>12 h</button>` +
      `<button type="button" data-v="24"${on(opt.hours === 24)}>24 h</button></span>` +
      `<span class="rp-seg" data-rp="near"><button type="button" data-v="0"${on(!opt.near)}>ALL FINLAND</button>` +
      `<button type="button" data-v="1"${on(opt.near)}>NEAR ${st}</button></span>` +
      ['ARS', 'WXREP', 'SIGMET', 'METARWS'].map(g => `<label class="rp-chk"><input type="checkbox" data-rpk="${g}"${k[g] ? ' checked' : ''}><i></i>${g === 'METARWS' ? 'METAR WS' : g}</label>`).join('') +
      `<label class="rp-chk" title="ARS reports with a position as markers on the scope"><input type="checkbox" data-rpscope${opt.onScope ? ' checked' : ''}><i></i>ARS on scope</label>`;
  }
  function bindBar(el) {
    el.addEventListener('click', e => {
      const b = e.target.closest('[data-rp] button'); if (!b) return;
      const k = b.parentElement.dataset.rp;
      set(k, k === 'hours' ? +b.dataset.v : b.dataset.v === '1');
    });
    el.addEventListener('change', e => {
      const c = e.target;
      if (c.dataset.rpk) { opt.kinds[c.dataset.rpk] = c.checked; set('kinds', opt.kinds); }
      else if ('rpscope' in c.dataset) set('onScope', c.checked);
    });
  }
  load();
  setInterval(() => { if (!document.hidden) load(); }, POLL_MS);
  return { load, filtered, html, footer, hasNew, markSeen, opt, set, barHtml, bindBar, onChange: f => subs.push(f), count: () => filtered().length };
})();
