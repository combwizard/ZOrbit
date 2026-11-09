/* The grids' own scroll bar: where its thumb goes and where a drag takes the list (zorbit/studio_ui/scrollbar.js).
   Run by tests/test_scroll_bar.py:  node tests/js/scroll_bar.js */
'use strict';
const assert = require('assert');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const B = require(path.join(root, 'zorbit', 'studio_ui', 'scrollbar.js'));
const tests = [];
const test = (name, fn) => tests.push([name, fn]);
const near = (a, b) => assert.ok(Math.abs(a - b) < 1e-6, `${a} is not ${b}`);

test('no thumb when everything fits', () => {
  assert.strictEqual(B.geometry({ clientH: 500, scrollH: 500, top: 0 }).show, false);
  assert.strictEqual(B.geometry({ clientH: 500, scrollH: 501, top: 0 }).show, false);   // a rounding pixel is not a list to scroll
  assert.strictEqual(B.geometry({ clientH: 0, scrollH: 900, top: 0 }).show, false);     // hidden
});
test('the thumb is as tall as the share on show, and runs from top to bottom', () => {
  const g0 = B.geometry({ clientH: 500, scrollH: 2000, top: 0 });
  assert.ok(g0.show); near(g0.thumbH, 125); near(g0.thumbTop, 0);
  near(B.geometry({ clientH: 500, scrollH: 2000, top: 1500 }).thumbTop, 375);           // at the end: touches the bottom
  near(B.geometry({ clientH: 500, scrollH: 2000, top: 750 }).thumbTop, 187.5);
});
test('a long list keeps a thumb you can hit', () => {
  const g = B.geometry({ clientH: 500, scrollH: 100000, top: 99500 });
  near(g.thumbH, B.MIN_THUMB); near(g.thumbTop, 500 - B.MIN_THUMB);
});
test('a scroll position out of range (before it clamps) keeps the thumb on the track', () => {
  near(B.geometry({ clientH: 500, scrollH: 2000, top: 9999 }).thumbTop, 375);
  near(B.geometry({ clientH: 500, scrollH: 2000, top: -5 }).thumbTop, 0);
});
test('dragging the thumb moves the list in proportion, and stops at the ends', () => {
  const at = (startTop, dy) => B.topFor({ startTop, dy, clientH: 500, scrollH: 2000 });
  near(at(0, 375), 1500);            // the whole track: the whole list
  near(at(0, 100), 400);
  near(at(400, -100), 0);
  near(at(0, -50), 0);
  near(at(1400, 500), 1500);
  near(at(0, 0), 0);
});
test('the thumb tracks the pointer: dragging by its own geometry puts it under the pointer again', () => {
  const clientH = 700, scrollH = 31000;
  for (const [start, dy] of [[0, 33], [5000, 210], [20000, -400]]) {
    const before = B.geometry({ clientH, scrollH, top: start }).thumbTop;
    const top = B.topFor({ startTop: start, dy, clientH, scrollH });
    near(B.geometry({ clientH, scrollH, top }).thumbTop, before + dy);
  }
});
test('nothing to scroll: a drag goes nowhere', () => {
  assert.strictEqual(B.topFor({ startTop: 0, dy: 100, clientH: 500, scrollH: 400 }), 0);
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); } catch (e) { failed++; console.log('FAIL', name, '\n ', e.message); }
}
if (failed) { console.log(`${failed} of ${tests.length} failed`); process.exit(1); }
console.log(`scroll bar checks pass (${tests.length})`);
