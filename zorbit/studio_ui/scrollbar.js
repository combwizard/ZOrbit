/* A scroll bar of our own over a scroll area's native one, for the Library and the browser grids. Pure geometry plus attach(),
   which builds it; Node loads the geometry (tests/js/scroll_bar.js does).

   Why: with a pen (Windows Ink), WebView2 feeds the native scroll bar the pen's position and a second, mouse position stuck where
   the pen pressed, by turns. The thumb jumps between the two every frame and stops wherever the last one put it. The page gets
   none of those events, so it cannot step in. This bar is an element: it gets pointer events and follows only the pointer that
   pressed it. The native bar stays (its 10 px keep the layout as it was), with its thumb made invisible and this bar on top, so
   the native one is never pressed. The wheel and the keyboard still scroll the area itself. */
(function (root) {
  'use strict';
  const MIN_THUMB = 24;            // px: a long list still has a thumb you can hit
  const REPEAT_MS = [300, 50];     // holding the track: the first repeat, then each next page

  /* clientH: the area's visible height (the track is as tall). scrollH: its content height. top: its scrollTop.
     Gives { show, thumbH, thumbTop }: no thumb when everything fits. */
  function geometry({ clientH, scrollH, top }) {
    const h = Math.max(0, Number(clientH) || 0), sh = Math.max(0, Number(scrollH) || 0);
    if (!(sh > h + 1) || !(h > 0)) return { show: false, thumbH: 0, thumbTop: 0 };
    const thumbH = Math.min(h, Math.max(MIN_THUMB, h * h / sh)), room = h - thumbH, max = sh - h;
    const t = Math.min(max, Math.max(0, Number(top) || 0));
    return { show: true, thumbH, thumbTop: room > 0 ? room * t / max : 0 };
  }

  /* The scrollTop for a thumb dragged dy px from where it was when scrollTop was startTop. */
  function topFor({ startTop, dy, clientH, scrollH }) {
    const g = geometry({ clientH, scrollH, top: startTop });
    if (!g.show) return 0;
    const room = clientH - g.thumbH, max = scrollH - clientH;
    const top = room > 0 ? startTop + dy * max / room : startTop;
    return Math.min(max, Math.max(0, top));
  }

  /* Builds the bar for scroll area `scroll` and gives back a wrapper holding the area and the bar: put the wrapper where the
     area would go. `doc` is the document (for the element factory). */
  function attach(scroll, doc) {
    const d = doc || document;
    const el = (cls, parent) => { const e = d.createElement('div'); e.className = cls; if (parent) parent.append(e); return e; };
    const host = el('sbar-host'), bar = el('sbar', null), thumb = el('sbar-thumb', bar);
    bar.setAttribute('aria-hidden', 'true');       // the area itself scrolls by keyboard
    host.append(scroll, bar);
    scroll.classList.add('sbar-own');

    let frame = 0;
    const paint = () => {
      frame = 0;
      const g = geometry({ clientH: scroll.clientHeight, scrollH: scroll.scrollHeight, top: scroll.scrollTop });
      bar.hidden = !g.show;
      if (!g.show) return;
      thumb.style.height = g.thumbH + 'px';
      thumb.style.transform = `translateY(${g.thumbTop}px)`;
    };
    const soon = () => { if (!frame) frame = requestAnimationFrame(paint); };
    scroll.addEventListener('scroll', soon, { passive: true });
    const ro = new ResizeObserver(soon);
    ro.observe(scroll);
    for (const c of scroll.children) ro.observe(c);    // the content: a new list, or the grid's padding as cards come and go

    let drag = null;                                    // { id, y, top } of the pointer that holds the thumb
    let repeat = 0;
    const stopRepeat = () => { clearTimeout(repeat); repeat = 0; };
    const page = (y, first) => {                        // one page toward y; again while held, until the thumb reaches it
      if (!bar.isConnected || bar.hidden) { stopRepeat(); return; }     // gone or nothing to scroll: no endless paging
      const r = thumb.getBoundingClientRect();
      const dir = y < r.top ? -1 : y > r.bottom ? 1 : 0;
      if (!dir) { stopRepeat(); return; }
      scroll.scrollBy({ top: dir * Math.max(40, scroll.clientHeight - 40) });
      repeat = setTimeout(() => page(y, false), REPEAT_MS[first ? 0 : 1]);
    };
    bar.addEventListener('pointerdown', e => {
      if (e.button !== 0 || drag) return;
      bar.setPointerCapture(e.pointerId);
      if (e.target === thumb) {
        drag = { id: e.pointerId, y: e.clientY, top: scroll.scrollTop };
        bar.classList.add('dragging');
      } else {
        drag = { id: e.pointerId, paging: true };
        page(e.clientY, true);
      }
    });
    bar.addEventListener('pointermove', e => {
      if (!drag || e.pointerId !== drag.id || drag.paging) return;      // only the pointer that pressed: never a second stream
      scroll.scrollTop = topFor({ startTop: drag.top, dy: e.clientY - drag.y, clientH: scroll.clientHeight, scrollH: scroll.scrollHeight });
    });
    const end = e => {
      if (!drag || e.pointerId !== drag.id) return;
      drag = null; stopRepeat();
      bar.classList.remove('dragging');
    };
    bar.addEventListener('mousedown', e => e.preventDefault());   // keeps the focus where it is; not on pointerdown, which would hide this mousedown from the click-outside closers of popovers
    bar.addEventListener('pointerup', end);
    bar.addEventListener('pointercancel', end);
    bar.addEventListener('lostpointercapture', end);
    bar.addEventListener('wheel', e => {                // the bar sits outside the area: pass the wheel on
      const k = e.deltaMode === 1 ? 40 : e.deltaMode === 2 ? scroll.clientHeight : 1;
      scroll.scrollBy({ top: e.deltaY * k, left: e.deltaX * k });
      e.preventDefault();
    }, { passive: false });
    const through = on => { bar.style.pointerEvents = on ? 'none' : ''; };   // a card dragged (the browser's own drag) lands on the grid under the bar
    d.addEventListener('dragstart', () => through(true), true);
    for (const t of ['dragend', 'drop']) d.addEventListener(t, () => through(false), true);
    paint();
    return host;
  }

  const ZScrollBar = { MIN_THUMB, geometry, topFor, attach };
  if (root) root.ZScrollBar = ZScrollBar;
  if (typeof module !== 'undefined') module.exports = ZScrollBar;
})(typeof window !== 'undefined' ? window : null);
