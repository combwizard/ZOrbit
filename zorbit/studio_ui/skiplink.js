/* The Skip to content link: only a Tab press may show it. Takes its elements as arguments, so Node can run it with stand-ins too
   (tests/js/skip_link.js does).

   The link is the first focusable element, and WebView2 puts focus on that when the window hands it keyboard focus (on open, and
   on some activations), which would show the link with nobody pressing Tab. That can happen before this runs: the window is shown
   anyway when the page takes over 3 s to load. So focus already on the link counts too. */
(function (root) {
  'use strict';
  const TAB_MS = 1000;             // focus this soon after a Tab press came from that press

  function guard(skip, main, doc, now = Date.now) {
    let tabAt = 0;
    const away = () => { if (main) main.focus({ preventScroll: true }); else skip.blur(); };
    skip.addEventListener('click', e => { e.preventDefault(); if (main) main.focus(); });
    doc.addEventListener('keydown', e => { if (e.key === 'Tab') tabAt = now(); }, true);
    skip.addEventListener('focus', () => { if (now() - tabAt > TAB_MS) away(); });
    if (doc.activeElement === skip) away();
  }

  const ZSkipLink = { TAB_MS, guard };
  if (root) root.ZSkipLink = ZSkipLink;
  if (typeof module !== 'undefined') module.exports = ZSkipLink;
})(typeof window !== 'undefined' ? window : null);
