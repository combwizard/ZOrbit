/* Empty slots and Keep slots in place (zorbit/studio_ui/slots.js): where an added item goes, what delete and a swap leave behind.
   Run by tests/test_slots.py:  node tests/js/slots.js */
'use strict';
const assert = require('assert');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const Z = require(path.join(root, 'zorbit', 'studio_ui', 'slots.js'));
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

const E = () => ({ empty: true });
const names = items => items.map(it => (Z.isEmpty(it) ? '_' : it.brush));

test('an empty slot is {empty: true} and nothing else is', () => {
  assert(Z.isEmpty(E()));
  assert(!Z.isEmpty({ brush: 'A' }));
  assert(!Z.isEmpty({ empty: false }));
  assert(!Z.isEmpty(null));
  assert.deepStrictEqual(Z.blank(), { empty: true });
});

test('firstEmpty finds the first gap, or -1', () => {
  assert.strictEqual(Z.firstEmpty([{ brush: 'A' }, E(), E()]), 1);
  assert.strictEqual(Z.firstEmpty([{ brush: 'A' }, { brush: 'B' }]), -1);
  assert.strictEqual(Z.firstEmpty([]), -1);
});

test('place fills the first empty slot and leaves the others where they are', () => {
  const items = [{ brush: 'A' }, E(), { brush: 'C' }, E()];
  assert.strictEqual(Z.place(items, { brush: 'X' }), 1);
  assert.deepStrictEqual(names(items), ['A', 'X', 'C', '_']);
  assert.strictEqual(Z.place(items, { brush: 'Y' }), 3);
  assert.deepStrictEqual(names(items), ['A', 'X', 'C', 'Y']);
});

test('place appends when every slot is in use, and into an empty list', () => {
  const items = [{ brush: 'A' }, { brush: 'B' }];
  assert.strictEqual(Z.place(items, { brush: 'X' }), 2);
  assert.deepStrictEqual(names(items), ['A', 'B', 'X']);
  const none = [];
  assert.strictEqual(Z.place(none, { brush: 'X' }), 0);
  assert.deepStrictEqual(names(none), ['X']);
});

test('clear empties a slot and hands back what was in it', () => {
  const items = [{ brush: 'A' }, { brush: 'B' }, { brush: 'C' }];
  assert.deepStrictEqual(Z.clear(items, 1), { brush: 'B' });
  assert.deepStrictEqual(names(items), ['A', '_', 'C']);
  assert.strictEqual(items.length, 3);
});

test('clear on a slot that does not exist changes nothing', () => {
  const items = [{ brush: 'A' }];
  assert.strictEqual(Z.clear(items, 5), undefined);
  assert.strictEqual(Z.clear(items, -1), undefined);
  assert.strictEqual(Z.clear(items, 1.5), undefined);
  assert.deepStrictEqual(names(items), ['A']);
});

test('swap exchanges two slots, empty or not', () => {
  const items = [{ brush: 'A' }, { brush: 'B' }, E()];
  assert(Z.swap(items, 0, 1));
  assert.deepStrictEqual(names(items), ['B', 'A', '_']);
  assert(Z.swap(items, 1, 2));                           // a move into an empty slot leaves an empty one behind
  assert.deepStrictEqual(names(items), ['B', '_', 'A']);
});

test('swap refuses the same slot and slots out of range', () => {
  const items = [{ brush: 'A' }, { brush: 'B' }];
  assert(!Z.swap(items, 1, 1));
  assert(!Z.swap(items, 0, 2));
  assert(!Z.swap(items, -1, 0));
  assert.deepStrictEqual(names(items), ['A', 'B']);
});

test('trimEnd removes the last slot only when it is empty', () => {
  const items = [{ brush: 'A' }, E(), E()];
  assert(Z.trimEnd(items));
  assert(Z.trimEnd(items));
  assert.deepStrictEqual(names(items), ['A']);
  assert(!Z.trimEnd(items));                              // the last slot is in use
  assert.deepStrictEqual(names(items), ['A']);
  assert(!Z.trimEnd([]));
});

test('addSlot appends an empty slot and says where', () => {
  const items = [{ brush: 'A' }];
  assert.strictEqual(Z.addSlot(items), 1);
  assert.strictEqual(Z.addSlot(items), 2);
  assert.deepStrictEqual(names(items), ['A', '_', '_']);
  assert.notStrictEqual(items[1], items[2]);              // separate objects: editing one never touches the other
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); } catch (e) { failed++; console.log('FAIL ' + name + '\n  ' + String(e.message).split('\n').join('\n  ')); }
}
console.log((tests.length - failed) + ' of ' + tests.length + ' slot checks pass');
process.exit(failed ? 1 : 0);
