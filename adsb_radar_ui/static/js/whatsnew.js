/* whatsnew.js - the "What's new" window (doc/whats_new.md via /api/whatsnew), with the tabs
 * USER GUIDES (from 2026-11-05: the PDF guides of doc/guides.md, opened from /doc/<file>) and ABOUT
 * (doc/about.md: what RADAR is, the data sources and credits).
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
  const gbody = document.getElementById('wnGuides');
  const abody = document.getElementById('wnAbout');
  const tabs = [...win.querySelectorAll('[data-wntab]')];
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
  const fmtIso = d => (/^\d{4}-\d\d-\d\d$/.test(d || '') ? d.slice(8) + '.' + d.slice(5, 7) + '.' + d.slice(0, 4) : esc(d || ''));
  function guides(gs) {
    if (!gs.length) return '<p>No user guides on this system.</p>';
    return '<p class="wn-intro">The guides open as PDF in a new browser tab.</p>' + gs.map(g => {
      const meta = [g.version ? 'Version ' + esc(g.version) : '', g.date ? fmtIso(g.date) : '',
                    g.pages ? esc(g.pages) + ' pages' : '', g.size ? (g.size / 1e6).toFixed(1) + ' MB' : ''].filter(Boolean).join(' · ');
      return '<section class="wn-entry wn-guide"><h3>' + esc(g.title) + '</h3><div class="wn-gmeta">' + meta + '</div>' +
             render(g.lines || []) + '<div class="wn-gbtns"><a class="wn-gbtn" href="' + esc(g.url) + '" target="_blank" rel="noopener">Open PDF</a>' +
             '<a class="wn-gbtn" href="' + esc(g.url) + '" download>Download</a></div></section>';
    }).join('');
  }
  function showTab(t) {
    t = t === 'guides' || t === 'about' ? t : 'news';
    tabs.forEach(b => b.classList.toggle('on', b.dataset.wntab === t));
    body.hidden = t !== 'news'; if (gbody) gbody.hidden = t !== 'guides'; if (abody) abody.hidden = t !== 'about';
    try { localStorage.setItem('wnTab', t); } catch (_) { /* private mode */ }
  }
  tabs.forEach(b => b.addEventListener('click', () => showTab(b.dataset.wntab)));
  const fmtVer = v => { const d = v.slice(2); return d.slice(0, 2) + '.' + d.slice(2, 4) + '.' + d.slice(4); };

  let loaded = false, aw = null;
  async function open() {
    if (!aw && typeof AtcWindow !== 'undefined') aw = AtcWindow.make(win, { key: 'wnGeom', head: win.querySelector('.wn-head') });
    if (aw) aw.show(); else win.hidden = false;
    let t0 = null; try { t0 = localStorage.getItem('wnTab'); } catch (_) { /* private mode */ }
    showTab(t0);
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
      if (gbody) gbody.innerHTML = guides(d.guides || []);
      if (abody) abody.innerHTML = (d.about || []).map(a => '<section class="wn-entry"><h3><span>' + esc(a.title) + '</span></h3>' +
                                     render(a.lines || []) + '</section>').join('') || '<p>No information.</p>';
      loaded = true;
    } catch (_) {
      body.textContent = 'Could not load the notes.';
      if (gbody) gbody.textContent = 'Could not load the guides.';
    }
  }
  const close = () => { win.hidden = true; };
  link.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); win.hidden ? open() : close(); });
  document.getElementById('wnClose').addEventListener('click', close);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && !win.hidden) close(); });
})();
