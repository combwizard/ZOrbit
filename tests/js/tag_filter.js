/* The tag filter's match rule (zorbit/studio_ui/tagfilter.js): Any and All, and the counts that go on the chips under All.
   Run by tests/test_tag_filter.py:  node tests/js/tag_filter.js */
'use strict';
const assert = require('assert');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const T = require(path.join(root, 'zorbit', 'studio_ui', 'tagfilter.js'));
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

// Four brushes: what tags each carries.
const items = { A: ['blocking', 'hard'], B: ['blocking'], C: ['hard', 'organic'], D: [], E: ['blocking', 'hard', 'organic', T.FAV] };
const names = Object.keys(items);
const show = (tags, all) => names.filter(n => T.match(items[n], new Set(tags), all));

test('Any shows an item with at least one of the tags', () => {
  assert.deepStrictEqual(show(['blocking', 'organic'], false), ['A', 'B', 'C', 'E']);
});

test('All shows only an item with every one of the tags', () => {
  assert.deepStrictEqual(show(['blocking', 'hard'], true), ['A', 'E']);
  assert.deepStrictEqual(show(['blocking', 'hard', 'organic'], true), ['E']);
});

test('with one tag, Any and All are the same', () => {
  assert.deepStrictEqual(show(['hard'], true), show(['hard'], false));
});

test('no tags shows everything, in either mode', () => {
  assert.deepStrictEqual(show([], true), names);
  assert.deepStrictEqual(show([], false), names);
});

test('an array of tags works as well as a Set, and an item with no tag list matches nothing', () => {
  assert(T.match(['x', 'y'], ['x'], true));
  assert(!T.match(undefined, new Set(['x']), false));
  assert(!T.match(undefined, new Set(['x']), true));
});

test('a tag nobody carries leaves nothing under All and the other tags\' items under Any', () => {
  assert.deepStrictEqual(show(['blocking', 'ghost'], true), []);
  assert.deepStrictEqual(show(['blocking', 'ghost'], false), ['A', 'B', 'E']);
});

test('counts under All are what choosing each tag next would leave', () => {
  const c = T.narrowedCounts(names.map(n => items[n]), new Set(['blocking', 'hard']), true);
  assert.strictEqual(c.get('blocking'), 2);              // A and E: the items shown
  assert.strictEqual(c.get('hard'), 2);
  assert.strictEqual(c.get('organic'), 1);               // E only: adding it would leave one
  assert(!c.has('ghost'));
});

test('counts leave Favourites out, as it is a folder and not a chip', () => {
  const c = T.narrowedCounts(names.map(n => items[n]), new Set(['blocking', 'hard']), true);
  assert(!c.has(T.FAV));
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); } catch (e) { failed++; console.log('FAIL ' + name + '\n  ' + String(e.message).split('\n').join('\n  ')); }
}
console.log((tests.length - failed) + ' of ' + tests.length + ' tag filter checks pass');
process.exit(failed ? 1 : 0);
