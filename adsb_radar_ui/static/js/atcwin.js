/* atcwin.js - shared behaviour of the ATC-style windows on the scope (METAR & TAF,
 * EFHK traffic): drag by the title bar, resize from the lower-right corner (CSS resize),
 * keep inside the scope, and remember position and size in this browser.
 *
 *   const w = AtcWindow.make(el, { key: 'wxGeom', head: el.querySelector('.wn-head') });
 *   w.show() / w.hide()   - shows / hides and restores the remembered place and size
 *
 * Without a remembered place the window stays where its CSS puts it (its default).
 */
const AtcWindow = (() => {
  const ls = (k, v) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (_) { return null; } };

  function make(win, opt) {
    const stage = win.parentElement;
    const head = opt.head || win.querySelector('.wn-head');

    function save() {
      if (win.hidden) return;
      const s = stage.getBoundingClientRect(), r = win.getBoundingClientRect();
      ls(opt.key, JSON.stringify({ left: Math.round(r.left - s.left), top: Math.round(r.top - s.top),
                                   width: Math.round(r.width), height: Math.round(r.height) }));
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
      keepInside();
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
      const up = () => { document.removeEventListener('mousemove', move); document.removeEventListener('mouseup', up); save(); };
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
    });
    let t = null;
    if (window.ResizeObserver) new ResizeObserver(() => { clearTimeout(t); t = setTimeout(save, 300); }).observe(win);
    window.addEventListener('resize', keepInside);
    return {
      show() { win.hidden = false; restore(); },
      hide() { win.hidden = true; },
    };
  }
  return { make };
})();
