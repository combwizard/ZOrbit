/* The Skip to content link shows only after a Tab press (zorbit/studio_ui/skiplink.js).
   Run by tests/test_skip_link.py:  node tests/js/skip_link.js */
'use strict';
const assert = require('assert');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const L = require(path.join(root, 'zorbit', 'studio_ui', 'skiplink.js'));
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

function listeners() {
  const on = {};
  return {
    addEventListener(type, fn) { (on[type] = on[type] || []).push(fn); },
    fire(type, e) { (on[type] || []).forEach(fn => fn(e)); },
  };
}

/* A page with the link and the main region. focus() behaves as in a browser: it moves activeElement, then fires focus. */
function page({ hasMain = true } = {}) {
  const doc = { activeElement: null, ...listeners() };
  const el = () => {
    const self = {
      ...listeners(),
      focusArgs: null,
      focus(args) { self.focusArgs = args; doc.activeElement = self; self.fire('focus', {}); },
      blur() { if (doc.activeElement === self) doc.activeElement = null; },
    };
    return self;
  };
  const clock = { t: 100000 };
  return { doc, skip: el(), main: hasMain ? el() : null, clock, now: () => clock.t };
}
const start = p => L.guard(p.skip, p.main, p.doc, p.now);

test('focus already on the link when the guard starts moves to the main region', () => {
  const p = page();
  p.skip.focus();                                                // before init(): nothing is listening yet
  assert.strictEqual(p.doc.activeElement, p.skip);
  start(p);
  assert.strictEqual(p.doc.activeElement, p.main);
  assert.deepStrictEqual(p.main.focusArgs, { preventScroll: true });
});

test('focus elsewhere when the guard starts is left alone', () => {
  const p = page(), other = {};
  p.doc.activeElement = other;
  start(p);
  assert.strictEqual(p.doc.activeElement, other);
});

test('focus that lands later without a Tab press moves to the main region', () => {
  const p = page();
  start(p);
  p.skip.focus();
  assert.strictEqual(p.doc.activeElement, p.main);
});

test('a Tab press may land on the link', () => {
  const p = page();
  start(p);
  p.doc.fire('keydown', { key: 'Tab' });
  p.clock.t += 50;
  p.skip.focus();
  assert.strictEqual(p.doc.activeElement, p.skip);
});

test('a Tab press long ago does not count, and other keys never do', () => {
  const p = page();
  start(p);
  p.doc.fire('keydown', { key: 'Tab' });
  p.clock.t += L.TAB_MS + 1;
  p.skip.focus();
  assert.strictEqual(p.doc.activeElement, p.main);
  p.doc.fire('keydown', { key: 'a' });
  p.skip.focus();
  assert.strictEqual(p.doc.activeElement, p.main);
});

test('without a main region the link just lets go, at the start and later', () => {
  const p = page({ hasMain: false });
  p.skip.focus();
  start(p);
  assert.strictEqual(p.doc.activeElement, null);
  p.skip.focus();
  assert.strictEqual(p.doc.activeElement, null);
});

test('pressing the link goes to the main region instead of following the link', () => {
  const p = page();
  start(p);
  let prevented = false;
  p.skip.fire('click', { preventDefault() { prevented = true; } });
  assert.ok(prevented);
  assert.strictEqual(p.doc.activeElement, p.main);
});

let failed = 0;
for (const [name, fn] of tests) {
  try {
    fn();
  } catch (e) {
    failed++;
    console.log('FAIL ' + name + '\n' + e.message);
  }
}
if (failed) process.exit(1);
console.log('skip link checks pass');
