/* The order of Favourites (zorbit/studio_ui/favorder.js): the list on show, where a dragged key lands, and which gap a point is at.
   Run by tests/test_fav_order.py:  node tests/js/fav_order.js */
'use strict';
const assert = require('assert');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const O = require(path.join(root, 'zorbit', 'studio_ui', 'favorder.js'));
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

const scores = { a: 1, b: 5, c: 3, d: 0 };
const show = order => O.sorted(['a', 'b', 'c', 'd'], order, k => k, k => scores[k]).join('');

test('with no order the list is most used first, and a tie keeps the order it came in', () => {
  assert.strictEqual(show([]), 'bcad');
  assert.strictEqual(show(undefined), 'bcad');
  assert.strictEqual(O.sorted(['x', 'y', 'z'], [], k => k, () => 0).join(''), 'xyz');
});

test('with an order the list follows it, whatever the scores say', () => {
  assert.strictEqual(show(['d', 'a', 'c', 'b']), 'dacb');
});

test('an item the order does not know goes after the ones it does, most used first', () => {
  assert.strictEqual(show(['d', 'a']), 'dabc');
});

test('a saved key that is not on show takes no place in the list', () => {
  assert.strictEqual(show(['gone', 'd', 'alsogone', 'a', 'c', 'b']), 'dacb');
});

test('the list given is not changed', () => {
  const items = ['a', 'b'];
  O.sorted(items, ['b', 'a'], k => k, () => 0);
  assert.deepStrictEqual(items, ['a', 'b']);
});

test('a key moves back into a gap', () => {
  assert.deepStrictEqual(O.moved(['a', 'b', 'c', 'd'], 'c', 0), ['c', 'a', 'b', 'd']);
  assert.deepStrictEqual(O.moved(['a', 'b', 'c', 'd'], 'd', 1), ['a', 'd', 'b', 'c']);
});

test('a key moves on into a gap, counted as the list stands before the move', () => {
  assert.deepStrictEqual(O.moved(['a', 'b', 'c', 'd'], 'a', 2), ['b', 'a', 'c', 'd']);
  assert.deepStrictEqual(O.moved(['a', 'b', 'c', 'd'], 'a', 4), ['b', 'c', 'd', 'a']);
});

test('the gaps on either side of a key change nothing', () => {
  assert.strictEqual(O.moved(['a', 'b', 'c'], 'b', 1), null);
  assert.strictEqual(O.moved(['a', 'b', 'c'], 'b', 2), null);
});

test('a key that is not in the list changes nothing', () => {
  assert.strictEqual(O.moved(['a', 'b'], 'x', 0), null);
});

test('moved leaves the list it was given alone', () => {
  const keys = ['a', 'b', 'c'];
  O.moved(keys, 'a', 3);
  assert.deepStrictEqual(keys, ['a', 'b', 'c']);
});

/* Cards 100 wide and tall with a gap of 10: rows of three, the last one short. */
const card = (col, row) => ({ left: col * 110, right: col * 110 + 100, top: row * 110, bottom: row * 110 + 100 });
const grid = [card(0, 0), card(1, 0), card(2, 0), card(0, 1), card(1, 1)];
const at = (x, y, rects = grid) => O.gapAt(rects, x, y, 10);

test('a point on the left half of a card is the gap before it, on the right half the gap after it', () => {
  assert.strictEqual(at(10, 50).index, 0);
  assert.strictEqual(at(90, 50).index, 1);
  assert.strictEqual(at(120, 50).index, 1);
  assert.strictEqual(at(200, 50).index, 2);
});

test('the marker sits in the middle of the gap, as tall as the row', () => {
  assert.deepStrictEqual(at(120, 50), { index: 1, x: 105, top: 0, bottom: 100 });
  assert.deepStrictEqual(at(120, 160), { index: 4, x: 105, top: 110, bottom: 210 });
});

test('the end of a row is the gap before the first card of the next, with the marker where the point is', () => {
  assert.deepStrictEqual(at(300, 50), { index: 3, x: 325, top: 0, bottom: 100 });
  assert.deepStrictEqual(at(5, 160), { index: 3, x: -5, top: 110, bottom: 210 });
});

test('the space between two rows belongs to the row below', () => {
  assert.strictEqual(at(10, 105).index, 3);
});

test('past the end of a short row is the end of the list', () => {
  assert.strictEqual(at(300, 160).index, 5);
});

test('below the last row is the end of the list, wherever across', () => {
  assert.strictEqual(at(5, 500).index, 5);
  assert.strictEqual(at(5, 500).top, 110);
});

test('above the first row is still the first row', () => {
  assert.strictEqual(at(150, -20).index, 1);
});

test('a hovered card lifted a pixel does not start a new row', () => {
  const lifted = grid.map((r, i) => (i === 1 ? { ...r, top: r.top - 1, bottom: r.bottom - 1 } : r));
  assert.strictEqual(at(200, 50, lifted).index, 2);
});

test('with only the first part of a long list drawn, a gap still counts from the start', () => {
  assert.strictEqual(at(5, 500, grid.slice(0, 3)).index, 3);
});

test('no cards, no gap', () => {
  assert.strictEqual(O.gapAt([], 0, 0, 10), null);
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); } catch (e) { failed++; console.error('FAIL ' + name + '\n' + e.message); }
}
if (failed) { console.error(failed + ' failed'); process.exit(1); }
console.log('fav order checks pass (' + tests.length + ')');
