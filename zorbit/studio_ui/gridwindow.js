/* Which cards of a long grid to build, for the Library and the browser. Pure: no DOM, so Node can load it too (tests/js/grid_window.js does).

   A library can hold thousands of items, and a page with a card for each of them scrolls at a few frames a second. So only the
   cards near the view exist, and padding on the grid stands for the rows above and below: the scrollbar stays true. Every row
   has the same height (names are one line, thumbnails are square), so the rows on show follow from the scroll position. */
(function (root) {
  'use strict';
  const UNMEASURED = 60;           // cards to build before a row can be measured: enough to fill a window, and they show what a row is

  /* top: how far the grid's top has scrolled above the view. height: the view's height. rowH: a row with its gap (0 when not
     measured: the grid is not laid out yet). cols: cards in a row. total: cards in the list. margin: pixels built beyond each edge.
     Gives { first, end } (the cards to build, end not included) and the padding, in pixels, for the rows left out. */
  function range({ top, height, rowH, cols, total, margin }) {
    const c = Math.max(1, Math.floor(cols) || 1), n = Math.max(0, Math.floor(total) || 0);
    if (!(rowH > 0) || !n) return { first: 0, end: Math.min(n, UNMEASURED), padTop: 0, padBottom: 0 };
    const rows = Math.ceil(n / c), pad = Math.max(0, margin || 0), t = Number(top) || 0, h = Math.max(0, Number(height) || 0);
    const from = Math.min(rows - 1, Math.max(0, Math.floor((t - pad) / rowH)));     // past the end (a shorter list, before the scroll position clamps): the last row
    const to = Math.min(rows, Math.max(from + 1, Math.ceil((t + h + pad) / rowH)));  // not included
    return { first: from * c, end: Math.min(n, to * c), padTop: from * rowH, padBottom: (rows - to) * rowH };
  }

  const ZGridWindow = { UNMEASURED, range };
  if (root) root.ZGridWindow = ZGridWindow;
  if (typeof module !== 'undefined') module.exports = ZGridWindow;
})(typeof window !== 'undefined' ? window : null);
