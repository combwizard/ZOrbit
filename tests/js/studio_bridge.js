/* The "Show ZBrush's state on the ring" switch in Studio's app.js: how it reads and writes bridge.show_state, the Full-only note, the
   save summary and the message for a bad value. app.js is one closure with no exports, so this loads it into a vm with a stand-in
   page (every DOM call is accepted, the few elements the switch uses are real enough to inspect) and a line added at its end that
   hands out the functions under test.
   Run by tests/test_studio_bridge.py:  node tests/js/studio_bridge.js */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.join(__dirname, '..', '..');
const ui = f => path.join(root, 'zorbit', 'studio_ui', f);

/* A stand-in for anything the page might touch: callable, indexable, and it answers with more of itself. */
function anything() {
  const target = function () {};
  return new Proxy(target, {
    get: (t, p) => (p === Symbol.toPrimitive ? () => '' : p === 'then' ? undefined : p === 'length' ? 0 : anything()),
    apply: () => anything(),
    construct: () => anything(),
    set: () => true,
  });
}
/* An element that keeps what the switch's code puts on it, and shrugs at the rest. */
function element(tag) {
  const el = { tag, attrs: {}, kids: [], on: {}, style: anything(), dataset: {}, classList: anything(), checked: false, value: '',
    setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(type, fn) { (this.on[type] = this.on[type] || []).push(fn); },
    append(...c) { this.kids.push(...c); },
    replaceChildren(...c) { this.kids = c; } };
  return new Proxy(el, { get: (t, p) => (p in t ? t[p] : p === 'then' ? undefined : anything()), set: (t, p, v) => { t[p] = v; return true; } });
}
const textOf = n => (typeof n === 'string' ? n : (n.kids || []).map(textOf).join(' '));
const find = (n, pred, out = []) => { if (typeof n !== 'string') { if (pred(n)) out.push(n); (n.kids || []).forEach(k => find(k, pred, out)); } return out; };

const document = new Proxy({ readyState: 'complete', createElement: element, createTextNode: s => String(s), querySelector: sel => (sel === '#skipLink' ? null : element('div')), querySelectorAll: () => [],
  addEventListener() {}, documentElement: anything(), body: anything() }, { get: (t, p) => (p in t ? t[p] : anything()) });
const sandbox = { document, console, setTimeout: () => 0, clearTimeout() {}, setInterval: () => 0, clearInterval() {}, URLSearchParams, requestAnimationFrame: () => 0,
  cancelAnimationFrame() {}, addEventListener() {}, removeEventListener() {}, location: { search: '' }, __ZORBIT_MODE__: 'studio', localStorage: anything(),
  matchMedia: () => anything(), navigator: { userAgent: 'node' }, getComputedStyle: () => anything(), innerWidth: 1200, innerHeight: 800, devicePixelRatio: 1,
  ResizeObserver: function () { return anything(); }, MutationObserver: function () { return anything(); }, IntersectionObserver: function () { return anything(); } };
sandbox.window = sandbox;
const win = sandbox;
vm.createContext(sandbox);
for (const f of ['look.js', 'mode.js']) vm.runInContext(fs.readFileSync(ui(f), 'utf8'), sandbox, { filename: f });   // they put ZLook and ZMode on `window`

const src = fs.readFileSync(ui('app.js'), 'utf8');
const tail = /\}\)\(\);\s*$/;
assert(tail.test(src), 'app.js no longer ends with its closing })();');
const hook = 'window.__t = { S, describeProblem, describeChanges, bridgeShowState, bridgeStateRow, fullOnlyChanges };\n})();';
vm.runInContext(src.replace(tail, hook), sandbox, { filename: 'app.js' });
const T = win.__t;
assert(T, 'app.js did not hand out its functions');
const { S } = T;

const LABEL = 'Show ZBrush’s state on the ring';
const open = cfg => { S.cfg = JSON.parse(JSON.stringify(cfg)); S.savedStr = JSON.stringify(cfg); S.defaults = { hint: true, flick: true }; S.ready = true; };
const row = () => T.bridgeStateRow();
const switchOf = r => find(r, n => n.tag === 'input' && n.attrs['aria-label'] === LABEL)[0];
const flip = async (r, to) => { const inp = switchOf(r); inp.checked = to; for (const f of inp.on.change) await f(); };
const problem = raw => T.describeProblem(raw);

/* Objects made inside the vm have another Object.prototype, so deepStrictEqual would call equal things different. */
const same = (a, b, msg) => assert.strictEqual(JSON.stringify(a), JSON.stringify(b), msg);
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('the switch is labelled, says what it shows and that it needs ZBrush 2026 or newer', () => {
  open({ menus: {} });
  const r = row(), text = textOf(r);
  assert(switchOf(r), 'no switch with the label');
  assert(text.includes(LABEL));
  assert(text.includes('lit while its switch is on') && text.includes('what its slider is at') && text.includes('dimmed'));
  assert(text.includes('ZBrush 2026 or newer'));
  assert(!/\w'\w/.test(LABEL) && !text.includes("'s state"), 'interface text uses the curly apostrophe');
});

test('a profile without the key, with true, with false and with a bad value loads with the switch in the right position', () => {
  for (const [bridge, on] of [[undefined, true], [{}, true], [{ mode: 'key' }, true], [{ show_state: true }, true], [{ show_state: false }, false],
    [{ show_state: 'yes' }, true], [{ show_state: 0 }, true], [{ show_state: null }, true], ['nonsense', true]]) {
    const cfg = { menus: {} };
    if (bridge !== undefined) cfg.bridge = bridge;
    open(cfg);
    assert.strictEqual(switchOf(row()).checked, on, JSON.stringify(bridge));
  }
});

test('turning it off writes show_state: false and keeps the other bridge settings', async () => {
  open({ menus: {}, bridge: { mode: 'message', key: 'F11' } });
  await flip(row(), false);
  same(S.cfg.bridge, { mode: 'message', key: 'F11', show_state: false });
});

test('turning it on again removes the key, and the bridge block when nothing else is in it and the file had none', async () => {
  open({ menus: {} });
  await flip(row(), false);
  same(S.cfg.bridge, { show_state: false });
  await flip(row(), true);
  assert(!('bridge' in S.cfg), 'an empty bridge block was left behind');
  assert.strictEqual(JSON.stringify(S.cfg), S.savedStr, 'back where it started, so Save stays off');
});

test('turning it on keeps a bridge block the file already had, and keeps the other keys', async () => {
  open({ menus: {}, bridge: { show_state: false } });
  await flip(row(), true);
  same(S.cfg.bridge, {});
  open({ menus: {}, bridge: { show_state: false, key: 'F11' } });
  await flip(row(), true);
  same(S.cfg.bridge, { key: 'F11' });
});

test('a saved true is dropped when the switch is turned on, not written back', async () => {
  open({ menus: {}, bridge: { show_state: true, key: 'F11' } });
  await flip(row(), false);
  assert.strictEqual(S.cfg.bridge.show_state, false);
  await flip(row(), true);
  same(S.cfg.bridge, { key: 'F11' });
});

test('a bridge section that is not an object is replaced when the switch is turned off, and left alone when it is turned on', async () => {
  open({ menus: {}, bridge: 'nonsense' });
  await flip(row(), true);
  assert.strictEqual(S.cfg.bridge, 'nonsense');
  await flip(row(), false);
  same(S.cfg.bridge, { show_state: false });
});

test('the save summary names the change, in the ZBrush bridge group, both ways', () => {
  open({ menus: {} });
  S.cfg.bridge = { show_state: false };
  let g = T.describeChanges().find(x => x.area === 'ZBrush bridge');
  same(g.lines, [LABEL + ': on → off']);
  open({ menus: {}, bridge: { show_state: false } });
  delete S.cfg.bridge.show_state;
  g = T.describeChanges().find(x => x.area === 'ZBrush bridge');
  same(g.lines, [LABEL + ': off → on']);
});

test('the save summary says nothing when true becomes absent, and lists it beside the other bridge changes', () => {
  open({ menus: {}, bridge: { show_state: true } });
  delete S.cfg.bridge.show_state;
  assert(!T.describeChanges().some(x => x.area === 'ZBrush bridge'));
  open({ menus: {} });
  S.cfg.bridge = { mode: 'key', show_state: false };
  const g = T.describeChanges().find(x => x.area === 'ZBrush bridge');
  same(g.lines, ['Mode: auto → key', LABEL + ': on → off']);
});

test('the parser message for a bad value reads as a sentence and leads to the ZBrush bridge card', () => {
  open({ menus: {}, bridge: { show_state: 'yes' } });
  for (const [raw, shown] of [["bridge.show_state 'yes' must be true or false; using true", 'yes'], ['bridge.show_state 1 must be true or false; using true', '1'],
    ['bridge.show_state None must be true or false; using true', 'None'], ["bridge.show_state ['a'] must be true or false; using true", "['a']"]]) {
    const p = problem(raw);
    assert.strictEqual(p.text, `${LABEL} must be on or off, not ${shown}; it is on for now`);
    same(p.target, { kind: 'settings', card: 'set-zbrush-bridge' });
    assert.strictEqual(p.raw, raw);
  }
});

test('the neighbouring bridge messages still read as before', () => {
  open({ menus: {} });
  assert.strictEqual(problem("bridge.mode 'fast' unknown; using auto").text, 'Bridge mode fast is unknown; Auto is used instead');
  assert.strictEqual(problem("bridge.key 'Ctrl+Q+Q' not understood; using F9").text, 'The bridge key Ctrl+Q+Q is not understood; F9 is used instead');
  assert.strictEqual(problem('bridge.moed: unknown setting (did you mean mode?)').text, 'The bridge setting “moed” is not known. Did you mean mode?');
});

test('Full only: the note names ZBrush bridge when show_state is false and not when it is true or absent', () => {
  const ctx = { defaults: {} };
  same(T.fullOnlyChanges({ bridge: { show_state: false } }, undefined, ctx), ['ZBrush bridge']);
  same(T.fullOnlyChanges({ bridge: { show_state: false, mode: 'key' } }, undefined, ctx), ['ZBrush bridge']);
  same(T.fullOnlyChanges({ bridge: { show_state: true } }, undefined, ctx), []);
  same(T.fullOnlyChanges({ bridge: {} }, undefined, ctx), []);
  same(T.fullOnlyChanges({}, undefined, ctx), []);
});

(async () => {
  let failed = 0;
  for (const [name, fn] of tests) {
    try { await fn(); } catch (e) { failed++; console.log('FAIL: ' + name + '\n  ' + (e && e.stack || e)); }
  }
  if (failed) { console.log(failed + ' of ' + tests.length + ' failed'); process.exit(1); }
  console.log('studio bridge checks pass (' + tests.length + ')');
})();
