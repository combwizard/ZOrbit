/* Empty slots and "Keep slots in place", for a menu's item list. Pure: no DOM, so Node can load it too (tests/js/slots.js does).

   An empty slot is the item {"empty": true}. It takes its place in the ring and holds nothing. In a menu that keeps its slots in place
   the other items never move when one is added, removed or dragged: an item added fills the first empty slot (else a new slot at the end),
   deleting one leaves an empty slot, and dropping one on another slot swaps the two. These functions edit the array they are given and say
   what they did; app.js decides when a menu is one that keeps its slots. */
(function (root) {
  'use strict';
  const isEmpty = it => !!it && typeof it === 'object' && it.empty === true;
  const blank = () => ({ empty: true });

  /* Index of the first empty slot, or -1. */
  function firstEmpty(items) {
    for (let i = 0; i < items.length; i++) if (isEmpty(items[i])) return i;
    return -1;
  }

  /* Puts an item in the first empty slot, else at the end. Returns the index it went to. */
  function place(items, item) {
    const at = firstEmpty(items);
    if (at < 0) { items.push(item); return items.length - 1; }
    items[at] = item;
    return at;
  }

  /* Empties slot i. Returns the item that was there, or undefined when there is no such slot. */
  function clear(items, i) {
    if (!Number.isInteger(i) || i < 0 || i >= items.length) return undefined;
    const was = items[i];
    items[i] = blank();
    return was;
  }

  /* Swaps slots a and b (either may be empty). Returns false when either is out of range or they are the same slot. */
  function swap(items, a, b) {
    const ok = i => Number.isInteger(i) && i >= 0 && i < items.length;
    if (!ok(a) || !ok(b) || a === b) return false;
    const t = items[a]; items[a] = items[b]; items[b] = t;
    return true;
  }

  /* Takes off the last slot when it is empty. Returns whether it did. */
  function trimEnd(items) {
    if (!items.length || !isEmpty(items[items.length - 1])) return false;
    items.pop();
    return true;
  }

  /* Adds an empty slot at the end. Returns its index. */
  function addSlot(items) {
    items.push(blank());
    return items.length - 1;
  }

  const ZSlots = { isEmpty, blank, firstEmpty, place, clear, swap, trimEnd, addSlot };
  if (root) root.ZSlots = ZSlots;
  if (typeof module !== 'undefined') module.exports = ZSlots;
})(typeof window !== 'undefined' ? window : null);
