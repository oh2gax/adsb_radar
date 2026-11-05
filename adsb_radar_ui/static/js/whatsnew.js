/* whatsnew.js - the "What's new" window (doc/whats_new.md via /api/whatsnew).
 * The link under the logo opens a scrollable window over the scope with the changes of
 * the ten newest versions, in the radar's own colours. A dot after the link marks a
 * version this browser has not opened yet. × / Esc / the link again closes it. Since 2026-11-05 the
 * window moves by its title and resizes from its corner like the other windows (atcwin.js, wnGeom).
 * (After MODE-S Wind's What's new window, web/templates/base.html.)
 */
(function () {
  const link = document.getElementById('whatsNewLink');
  const win = document.getElementById('wnWindow');
  const body = document.getElementById('wnBody');
  const dot = document.getElementById('whatsNewDot');
  if (!link || !win || !body) return;
  const ver = link.dataset.version || '';
  try { if (ver && localStorage.getItem('seenVersion') !== ver && dot) dot.hidden = false; } catch (_) { /* private mode */ }

  const esc = t => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const inline = t => esc(t).replace(/`([^`]+)`/g, '<code>$1</code>')
                           .replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>')
                           .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<i>$2</i>');
  // the small Markdown subset of the notes: bullets (two levels) and paragraphs
  function render(lines) {
    let html = '', depth = 0, para = [];
    const flush = () => { if (para.length) { html += '<p>' + inline(para.join(' ')) + '</p>'; para = []; } };
    const close = to => { while (depth > to) { html += '</ul>'; depth--; } };
    for (const l of lines) {
      const m = l.match(/^(\s*)[-*]\s+(.*)$/);
      if (m) {
        flush();
        const d = m[1].length >= 2 ? 2 : 1;
        while (depth < d) { html += '<ul>'; depth++; }
        close(d);
        html += '<li>' + inline(m[2]) + '</li>';
      } else if (!l.trim()) { flush(); close(0); }
      else { close(0); para.push(l.trim()); }
    }
    flush(); close(0);
    return html;
  }
  const fmtVer = v => { const d = v.slice(2); return d.slice(0, 2) + '.' + d.slice(2, 4) + '.' + d.slice(4); };

  let loaded = false, aw = null;
  async function open() {
    if (!aw && typeof AtcWindow !== 'undefined') aw = AtcWindow.make(win, { key: 'wnGeom', head: win.querySelector('.wn-head') });
    if (aw) aw.show(); else win.hidden = false;
    try { localStorage.setItem('seenVersion', ver); } catch (_) { /* private mode */ }
    if (dot) dot.hidden = true;
    if (loaded) return;
    try {
      const d = await (await fetch('/api/whatsnew', { cache: 'no-store' })).json();
      const es = d.entries || [];
      body.innerHTML = es.length ? es.map(e =>
        '<section class="wn-entry"><h3><span>' + esc(e.version) + '</span><span class="wn-date">' + fmtVer(e.version) + '</span>' +
        (e.version === ver ? '<span class="wn-current">CURRENT</span>' : '') + '</h3>' +
        (e.title ? '<div class="wn-etitle">' + inline(e.title) + '</div>' : '') +
        render(e.lines || []) + '</section>').join('') : '<p>No notes found.</p>';
      loaded = true;
    } catch (_) {
      body.textContent = 'Could not load the notes.';
    }
  }
  const close = () => { win.hidden = true; };
  link.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); win.hidden ? open() : close(); });
  document.getElementById('wnClose').addEventListener('click', close);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !win.hidden) close(); });
})();
