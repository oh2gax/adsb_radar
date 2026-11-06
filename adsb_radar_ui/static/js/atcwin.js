/* atcwin.js - shared behaviour of the ATC-style windows on the scope (METAR & TAF,
 * EFHK traffic): drag by the title bar, resize from the lower-right corner (CSS resize),
 * keep inside the scope, and remember position and size in this browser.
 *
 *   const w = AtcWindow.make(el, { key: 'wxGeom', head: el.querySelector('.wn-head') });
 *   w.show() / w.hide()   - shows / hides and restores the remembered place and size
 *
 * Without a remembered place the window stays where its CSS puts it (its default).
 * AtcWindow.shiftAll(x0, x1): the scope's left edge moved from x0 to x1 on the screen (the left pane hidden /
 * shown). Every window remembers where its left edge was put on the screen (sx: by dragging it, or where it
 * first was) and goes back there - only as far right as needed while the pane is in the way.
 */
const AtcWindow = (() => {
  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) { return null; } };
  const all = [];

  function make(win, opt) {
    const stage = win.parentElement;
    const head = opt.head || win.querySelector('.wn-head');

    function save(moved) {                  // moved: dragged by the user - its new place on the screen (sx)
      if (win.hidden) return;
      const s = stage.getBoundingClientRect(), r = win.getBoundingClientRect(), old = geom(opt.key) || {};
      ls(opt.key, JSON.stringify({ left: Math.round(r.left - s.left), top: Math.round(r.top - s.top),
                                   width: Math.round(r.width), height: Math.round(r.height),
                                   sx: Math.round(moved || !Number.isFinite(old.sx) ? r.left : old.sx) }));
    }
    function keepInside() {                 // never lose a window outside the scope
      if (win.hidden) return;
      const s = stage.getBoundingClientRect(), r = win.getBoundingClientRect();
      if (r.left < s.left || r.top < s.top || r.right > s.right || r.bottom > s.bottom) {
        win.style.left = Math.max(0, Math.min(r.left - s.left, s.width - r.width)) + 'px';
        win.style.top = Math.max(0, Math.min(r.top - s.top, s.height - Math.min(r.height, s.height))) + 'px';
        win.style.right = 'auto';
      }
    }
    function restore() {
      let g = null;
      try { g = JSON.parse(ls(opt.key) || 'null'); } catch (_) { g = null; }
      if (g && Number.isFinite(g.left) && Number.isFinite(g.top)) {
        win.style.left = g.left + 'px'; win.style.top = g.top + 'px'; win.style.right = 'auto';
        if (g.width > 0) win.style.width = g.width + 'px';
        if (g.height > 0) win.style.height = g.height + 'px';
      }
      setTimeout(keepInside, 0);            // after the page's layout is final (the left pane hidden at start: sidepane.js)
    }
    if (head) head.addEventListener('mousedown', e => {
      if (e.button !== 0 || e.target.closest('button')) return;
      e.preventDefault();
      const s = stage.getBoundingClientRect(), r = win.getBoundingClientRect();
      const dx = e.clientX - r.left, dy = e.clientY - r.top;
      win.style.left = (r.left - s.left) + 'px'; win.style.top = (r.top - s.top) + 'px'; win.style.right = 'auto';
      const move = ev => {
        win.style.left = Math.max(0, Math.min(ev.clientX - s.left - dx, s.width - r.width)) + 'px';
        win.style.top = Math.max(0, Math.min(ev.clientY - s.top - dy, s.height - 30)) + 'px';
      };
      const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); save(true); };
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
    });
    let t = null;
    if (window.ResizeObserver) new ResizeObserver(() => { clearTimeout(t); t = setTimeout(() => save(false), 300); }).observe(win);
    window.addEventListener('resize', keepInside);
    all.push({ win, key: opt.key, save, stage });
    return {
      show() { win.hidden = false; restore(); },
      hide() { win.hidden = true; },
    };
  }
  const LATER = ['wnGeom'];                // windows made only when first opened (What's new): their remembered place
  function geom(k) { try { return JSON.parse(ls(k) || 'null'); } catch (_) { return null; } }
  function shiftStored(k, x0, x1) {
    const g = geom(k);
    if (!g || !Number.isFinite(g.left)) return;
    const sx = Number.isFinite(g.sx) ? g.sx : x0 + g.left;
    g.left = Math.max(0, Math.round(sx - x1)); g.sx = Math.round(sx);
    ls(k, JSON.stringify(g));
  }
  function shiftAll(x0, x1) {
    if (x0 === x1) return;
    for (const k of LATER) if (!all.some(w => w.key === k)) shiftStored(k, x0, x1);
    for (const w of all) {
      if (w.win.hidden) { shiftStored(w.key, x0, x1); continue; }
      if (!(w.win.style.left && w.win.style.right === 'auto')) continue;   // a right-anchored default stays
      const g = geom(w.key) || {}, cur = parseFloat(w.win.style.left) || 0;
      const sx = Number.isFinite(g.sx) ? g.sx : x0 + cur;
      const sw = w.stage.getBoundingClientRect().width, ww = w.win.getBoundingClientRect().width;
      w.win.style.left = Math.max(0, Math.min(sx - x1, sw - ww)) + 'px';
      w.save(false);
    }
  }
  return { make, shiftAll };
})();
