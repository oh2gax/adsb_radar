/* datastatus.js - the downloaded data (/api/data_status): AIP Finland (installed AIRAC, last / next check,
 * the next amendment) and the sources of the active areas, NOTAM (NAV WRNG) and AUP / UUP (last / next
 * check, last change, count). Shown in the left pane's STATUS section (#dataStatus) and in the app's DATA
 * section (#appDataStatus); refreshed every minute. Times in UTC; a failed check in red (an alarm).
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
  const row = (k, v, err) => `<div class="ds-r"><span class="ds-k">${k}</span><span class="ds-v">${v}${err ? `<span class="ds-err"> · check failed: ${esc(err)}</span>` : ''}</span></div>`;
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
    return row('AIP', aip, a.error) + row('NOTAM', notam, n.error) + row('AUP', aup, u.error);
  }
  async function load() {
    try {
      const d = await (await fetch('/api/data_status', { cache: 'no-store' })).json();
      const html = render(d);
      boxes().forEach(b => { b.innerHTML = html; });
    } catch (e) { /* keep the last */ }
  }
  load();
  setInterval(load, 60000);
  window.dataStatusReload = load;
})();
