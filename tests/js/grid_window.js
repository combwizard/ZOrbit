/* Which cards of a long grid get built (zorbit/studio_ui/gridwindow.js).
   Run by tests/test_grid_window.py:  node tests/js/grid_window.js */
'use strict';
const assert = require('assert');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const G = require(path.join(root, 'zorbit', 'studio_ui', 'gridwindow.js'));
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const at = (top, more = {}) => G.range({ top, height: 800, rowH: 150, cols: 10, total: 13000, margin: 300, ...more });

test('the top of the list builds the rows in view and the margin below', () => {
  const r = at(0);
  assert.strictEqual(r.first, 0);
  assert.strictEqual(r.padTop, 0);
  assert.strictEqual(r.end, 80);                                 // (800 + 300) / 150 rounds up to 8 rows
  assert.strictEqual(r.padBottom, (1300 - 8) * 150);
});

test('a window keeps the grid its whole height wherever it is', () => {
  for (const top of [0, 149, 150, 5000, 100000, 194000]) {
    const r = at(top), rows = (r.end - r.first) / 10;
    assert.strictEqual(r.padTop + rows * 150 + r.padBottom, 1300 * 150, 'at ' + top);
  }
});

test('it starts on a row and covers the view with the margin', () => {
  const r = at(30000);
  assert.strictEqual(r.first % 10, 0);
  assert.ok(r.padTop <= 30000 - 300);
  assert.ok(r.padTop + ((r.end - r.first) / 10) * 150 >= 30000 + 800 + 300);
});

test('the end of the list stops at the last card, in a row that is not full', () => {
  const r = at(1e6, { total: 13005 });
  assert.strictEqual(r.end, 13005);
  assert.strictEqual(r.first, 13000);                             // scrolled past the end: the last row, until the position clamps
  assert.strictEqual(r.padBottom, 0);
  const s = at(1301 * 150 - 800, { total: 13005 });
  assert.strictEqual(s.end, 13005);
  assert.strictEqual(s.padBottom, 0);
});

test('a short list is built whole, with no padding', () => {
  assert.deepStrictEqual(at(0, { total: 7 }), { first: 0, end: 7, padTop: 0, padBottom: 0 });
});

test('before a row can be measured it builds a first batch', () => {
  assert.deepStrictEqual(at(0, { rowH: 0 }), { first: 0, end: G.UNMEASURED, padTop: 0, padBottom: 0 });
  assert.deepStrictEqual(at(0, { rowH: 0, total: 5 }), { first: 0, end: 5, padTop: 0, padBottom: 0 });
});

test('no cards, odd numbers and one column do no harm', () => {
  assert.deepStrictEqual(at(0, { total: 0 }), { first: 0, end: 0, padTop: 0, padBottom: 0 });
  const one = at(0, { cols: 1, total: 100 });
  assert.strictEqual(one.first, 0);
  assert.strictEqual(one.end, 8);
  const odd = G.range({ top: -50, height: undefined, rowH: 150, cols: 0, total: 100, margin: undefined });
  assert.strictEqual(odd.first, 0);
  assert.ok(odd.end >= 1);
  assert.ok(Number.isFinite(odd.padBottom));
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); } catch (e) { failed++; console.log('FAIL ' + name + '\n  ' + String(e.message).split('\n').join('\n  ')); }
}
console.log((tests.length - failed) + ' of ' + tests.length + ' grid window checks pass');
process.exit(failed ? 1 : 0);
