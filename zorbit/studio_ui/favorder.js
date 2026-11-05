/* The order of Favourites in the Library and the browser. Pure: no DOM, so Node can load it too (tests/js/fav_order.js does).

   A tab with no order of its own is most used first. With one, the items follow it and do not move by themselves; tags.py keeps the
   list to the items that carry Favourites and puts a new star at the end. Keys are nameKey()s, the item key without the kind. */
(function (root) {
  'use strict';

  /* The items in Favourites order, as a new array. order: the tab's saved keys, or empty for most used first. An item the order does not
     know (a star that has not reached this window yet) goes after the ones it does, most used first. Sort is stable, so a tie keeps the
     order the items came in. */
  function sorted(items, order, keyOf, scoreOf) {
    const place = new Map((order || []).map((k, i) => [k, i]));
    const rank = it => { const p = place.get(keyOf(it)); return p === undefined ? place.size : p; };
    return items.slice().sort((a, b) => rank(a) - rank(b) || scoreOf(b) - scoreOf(a));
  }

  /* The keys after the one named moves into a gap: gap 0 is before the first key, gap keys.length after the last. Gaps count the list as
     it is on show, with the key still in its old place. Null when that changes nothing or the key is not there. */
  function moved(keys, key, gap) {
    const from = keys.indexOf(key);
    if (from < 0 || gap === from || gap === from + 1) return null;
    const out = keys.slice();
    out.splice(from, 1);
    out.splice(gap > from ? gap - 1 : gap, 0, key);
    return out;
  }

  /* Which gap between the cards a point is at, and where to draw the marker. rects: the cards' { left, top, right, bottom } in list order.
     Only the cards drawn so far need be there: renderGrid draws a long list a part at a time, front first, so a gap still counts from the
     start of the list. The cards wrap in rows, and a row starts where a card is not to the right of the one before (by position across,
     so the small lift of a hovered card does not matter). A point in a row, or in the space above it, is at that row's gap nearest in x;
     below the last row it is at the end of the list. Returns { index, x, top, bottom }, or null without cards. gap: the grid's gap in px. */
  function gapAt(rects, x, y, gap = 0) {
    if (!rects.length) return null;
    const rows = [];
    let start = 0;
    for (let i = 1; i <= rects.length; i++) {
      if (i === rects.length || rects[i].left <= rects[i - 1].left) { rows.push([start, i]); start = i; }
    }
    const last = rows[rows.length - 1];
    const below = y > rects[last[1] - 1].bottom;
    const [from, to] = below ? last : rows.find(([, end]) => y <= rects[end - 1].bottom);
    let index = to;
    if (!below) for (let i = from; i < to; i++) if (x < (rects[i].left + rects[i].right) / 2) { index = i; break; }
    const near = rects[index === to ? to - 1 : index];
    return { index, x: index === to ? near.right + gap / 2 : near.left - gap / 2, top: near.top, bottom: near.bottom };
  }

  const ZFavOrder = { sorted, moved, gapAt };
  if (root) root.ZFavOrder = ZFavOrder;
  if (typeof module !== 'undefined') module.exports = ZFavOrder;
})(typeof window !== 'undefined' ? window : null);
