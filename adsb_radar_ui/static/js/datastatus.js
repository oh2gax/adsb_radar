/* datastatus.js - the downloaded data (/api/data_status): AIP Finland (installed AIRAC, last / next check,
 * the next amendment) and the sources of the active areas, NOTAM (NAV WRNG) and AUP / UUP (last / next
 * check, last change, count). Shown in the left pane's STATUS section (#dataStatus) and in the app's DATA
 * section (#appDataStatus); refreshed every minute. Times in UTC; a failed check in red (an alarm).
 * Alarms: a failed check, a check overdue (its keeper has stopped) or this status not reachable. They
 * are also in window.radarDataAlarm ('' = none), which radar.js writes on the scope ("DATA: …").
 */
(function () {
  const boxes = () => ['dataStatus', 'appDataStatus'].map(id => document.getElementById(id)).filter(Boolean);
  if (!boxes().length) return;
  const p = n => String(n).padStart(2, '0');
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  function hm(t, now) {                                    // 05:12Z, or 07.11. 05:12Z on another day
    if (!t) return '--';
    const d = new Date(t * 1000), n = new Date(now * 1000);
    const day = d.getUTCDate() === n.getUTCDate() && d.getUTCMonth() === n.getUTCMonth() ? '' : `${p(d.getUTCDate())}.${p(d.getUTCMonth() + 1)}. `;
    return `${day}${p(d.getUTCHours())}:${p(d.getUTCMinutes())}Z`;
  }
  const dmy = iso => iso ? iso.slice(8, 10) + '.' + iso.slice(5, 7) + '.' + iso.slice(0, 4) : '--';
  const row = (k, v, err, late) => `<div class="ds-r"><span class="ds-k">${k}</span><span class="ds-v">${v}` +
    (err ? `<span class="ds-err"> · check failed: ${esc(err)}</span>` : '') +
    (late && !err ? `<span class="ds-err"> · check overdue</span>` : '') + `</span></div>`;
  // a check is overdue when its next check is this much past (a slow download is not an alarm)
  const GRACE = { aip: 3600, notam: 1200, aup: 1200 };
  const late = (k, s, now) => !!(s && s.next_check && now > s.next_check + GRACE[k]);
  let lastOk = 0, fails = 0, lastData = null;
  function setAlarm(txt) {
    if ((window.radarDataAlarm || '') === txt) return;
    window.radarDataAlarm = txt;
    if (typeof window.requestDraw === 'function') window.requestDraw();
  }
  function alarmOf(d) {                                    // "AIP CHECK FAILED · NOTAM CHECK OVERDUE"
    const failed = [], over = [];
    [['aip', 'AIP'], ['notam', 'NOTAM'], ['aup', 'AUP']].forEach(([k, name]) => {
      const s = d[k] || {};
      if (s.error) failed.push(name); else if (late(k, s, d.now)) over.push(name);
    });
    const out = [];
    if (failed.length) out.push(failed.join(', ') + ' CHECK FAILED');
    if (over.length) out.push(over.join(', ') + ' CHECK OVERDUE');
    return out.length ? 'DATA: ' + out.join(' · ') : '';
  }
  function render(d) {
    const now = d.now, a = d.aip || {}, n = d.notam || {}, u = d.aup || {};
    const aip = a.installed
      ? `AIRAC ${dmy(a.effective)}${a.amdt ? ' (AMDT ' + esc(a.amdt) + ')' : ''}<br>checked ${hm(a.last_check, now)} · next ${hm(a.next_check, now)}` +
        (a.next_airac ? `<br>next AIRAC ${dmy(a.next_airac)}, installed that day` : '')
      : `not installed yet · next check ${hm(a.next_check, now)}`;
    const notam = `checked ${hm(n.last_check, now)} · next ${hm(n.next_check, now)}<br>changed ${hm(n.last_change, now)}` +
                  (n.n != null ? ` · ${n.n} activation${n.n === 1 ? '' : 's'}` : '');
    const aup = (u.files && u.files.length ? esc(u.files.join(', ')) + '<br>' : '') +
                `checked ${hm(u.last_check, now)} · next ${hm(u.next_check, now)}<br>changed ${hm(u.last_change, now)}` +
                (u.n != null ? ` · ${u.n} area${u.n === 1 ? '' : 's'}` : '');
    return row('AIP', aip, a.error, late('aip', a, now)) + row('NOTAM', notam, n.error, late('notam', n, now)) +
           row('AUP', aup, u.error, late('aup', u, now));
  }
  // this status could not be read: keep the last one, marked old (after two misses, ~2 min)
  function stale() {
    const t = lastOk ? hm(lastOk, Date.now() / 1000) : '--';
    const head = `<div class="ds-r ds-old"><span class="ds-err">Status not updated since ${t} (server not reachable)</span></div>`;
    boxes().forEach(b => { b.innerHTML = head + (lastData ? render(lastData) : ''); });
    setAlarm('DATA: STATUS NOT UPDATED');
  }
  async function load() {
    try {
      const r = await fetch('/api/data_status', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const d = await r.json();
      lastData = d; lastOk = Date.now() / 1000; fails = 0;
      const html = render(d);
      boxes().forEach(b => { b.innerHTML = html; });
      setAlarm(alarmOf(d));
    } catch (e) {
      if (++fails >= 2) stale();
    }
  }
  load();
  setInterval(load, 60000);
  window.dataStatusReload = load;
})();
