/* traffic.js - the EFHK traffic window: landings and departures at EFHK from MODE-S Wind's
 * database (/api/efhk_traffic). Sidebar "EFHK traffic" → Show. In the window: ARR / DEP /
 * BOTH and 1h / 3h / 6h / 12h / 1d; newest first, a line at each change of the UTC day.
 * A row of an aircraft that is on the scope can be clicked: the aircraft blinks and, with
 * TopSky labels, is selected (its extended label opens). Choices, place and size are
 * remembered; the window asks for new rows every 60 s while it is open.
 */
(function () {
  const win = document.getElementById('trWindow');
  const body = document.getElementById('trBody');
  const count = document.getElementById('trCount');
  const cb = document.getElementById('trOn');
  if (!win || !body || !cb || typeof AtcWindow === 'undefined') return;

  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) { return null; } };
  const KINDS = ['arr', 'dep', 'both'], HOURS = [1, 3, 6, 12, 24];
  let kind = KINDS.includes(ls('trKind')) ? ls('trKind') : 'both';
  let hours = HOURS.includes(+ls('trHours')) ? +ls('trHours') : 3;
  let on = ls('trOn') === '1';
  let timer = null, liveTimer = null, seq = 0;
  const aw = AtcWindow.make(win, { key: 'trGeom', head: win.querySelector('.wn-head') });
  const esc = t => String(t ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const pad = n => String(n).padStart(2, '0');
  const hhmm = t => { const d = new Date(t * 1000); return pad(d.getUTCHours()) + ':' + pad(d.getUTCMinutes()); };
  const dayKey = t => new Date(t * 1000).toISOString().slice(0, 10);
  const dayTxt = t => { const d = new Date(t * 1000); return pad(d.getUTCDate()) + '.' + pad(d.getUTCMonth() + 1) + '.'; };
  const hasAc = icao => typeof window.radarHasAircraft === 'function' && window.radarHasAircraft(icao);

  function markButtons() {
    win.querySelectorAll('[data-kind]').forEach(b => b.classList.toggle('on', b.dataset.kind === kind));
    win.querySelectorAll('[data-hours]').forEach(b => b.classList.toggle('on', +b.dataset.hours === hours));
  }

  function render(d) {
    const what = kind === 'arr' ? 'arrivals' : kind === 'dep' ? 'departures' : 'traffic';
    const span = hours === 24 ? '1 d' : hours + ' h';
    count.textContent = d.error ? '' : kind === 'both' ? `${d.arr} arr · ${d.dep} dep · last ${span}`
      : `${kind === 'arr' ? d.arr : d.dep} ${what} · last ${span}`;
    if (d.error) { body.innerHTML = `<p class="wx-none">${esc(d.error)}</p>`; return; }
    const rows = d.rows || [];
    if (!rows.length) { body.innerHTML = `<p class="wx-none">No ${what} in the last ${span}.</p>`; return; }
    const both = kind === 'both';
    const cols = both ? 7 : 6;
    let html = '<table class="tr-table"><thead><tr><th>UTC</th>' + (both ? '<th>A/D</th>' : '') +
               '<th>CALLSIGN</th><th>REG</th><th>TYPE</th><th>RWY</th><th></th></tr></thead><tbody>';
    let prevDay = dayKey(d.now || Date.now() / 1000);
    for (const r of rows) {
      const day = dayKey(r.t);
      if (day !== prevDay) { html += `<tr class="tr-day"><td colspan="${cols}">── ${dayTxt(r.t)} ──</td></tr>`; prevDay = day; }
      const ga = r.ga ? (r.ga > 1 ? 'GA' + r.ga : 'GA') : '';
      html += `<tr data-icao="${esc(r.icao)}" title="${esc(r.icao)}${r.ga ? ' · ' + r.ga + ' go-around' + (r.ga > 1 ? 's' : '') + ' before landing' : ''}">` +
              `<td>${hhmm(r.t)}</td>` + (both ? `<td>${r.kind === 'arr' ? 'ARR' : 'DEP'}</td>` : '') +
              `<td class="tr-cs">${esc(r.callsign || r.icao)}</td><td>${esc(r.reg || '')}</td><td>${esc(r.type || '')}</td>` +
              `<td>${esc(r.rwy || '---')}</td><td class="tr-ga">${ga}</td></tr>`;
    }
    body.innerHTML = html + '</tbody></table>';
    markLive();
  }

  // rows of aircraft on the scope now can be clicked
  function markLive() {
    body.querySelectorAll('tr[data-icao]').forEach(tr => {
      const live = hasAc(tr.dataset.icao);
      tr.classList.toggle('live', live);
      tr.title = tr.title.replace(/ · click: show on the scope$/, '') + (live ? ' · click: show on the scope' : '');
    });
  }
  body.addEventListener('click', e => {
    const tr = e.target.closest('tr.live');
    if (tr && typeof window.radarSelect === 'function') window.radarSelect(tr.dataset.icao);
  });

  async function load() {
    if (!on) return;
    const my = ++seq;
    try {
      const r = await fetch(`/api/efhk_traffic?kind=${kind}&hours=${hours}`, { cache: 'no-store' });
      const d = await r.json();
      if (my === seq) render(d);
    } catch (_) {
      if (my === seq) { count.textContent = ''; body.innerHTML = '<p class="wx-none">Radar server not reachable.</p>'; }
    }
  }

  win.querySelectorAll('[data-kind]').forEach(b => b.addEventListener('click', () => {
    kind = b.dataset.kind; ls('trKind', kind); markButtons(); body.textContent = 'Loading…'; load();
  }));
  win.querySelectorAll('[data-hours]').forEach(b => b.addEventListener('click', () => {
    hours = +b.dataset.hours; ls('trHours', String(hours)); markButtons(); body.textContent = 'Loading…'; load();
  }));

  function setOn(v) {
    on = v; cb.checked = v; ls('trOn', v ? '1' : '0');
    clearInterval(timer); clearInterval(liveTimer); timer = liveTimer = null;
    if (v) {
      aw.show(); load();
      timer = setInterval(() => { if (!document.hidden) load(); }, 60000);
      liveTimer = setInterval(markLive, 5000);
    } else aw.hide();
  }
  cb.addEventListener('change', () => setOn(cb.checked));
  document.getElementById('trClose').addEventListener('click', () => setOn(false));
  markButtons();
  setOn(on);
})();
