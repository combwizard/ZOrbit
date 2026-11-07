/* What Simple mode hides (zorbit/studio_ui/mode.js): which item types, ring settings and problem targets are Full only.
   Run by tests/test_mode_gating.py:  node tests/js/mode_gating.js */
'use strict';
const assert = require('assert');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const M = require(path.join(root, 'zorbit', 'studio_ui', 'mode.js'));
const ACTIONS = ['brush', 'alpha', 'material', 'texture', 'press', 'set', 'toggle', 'capture', 'tool', 'project', 'layout', 'steps', 'menu', 'auto', 'tag', 'browser', 'recent', 'empty'];
const kindOf = it => ACTIONS.find(k => it && k in it) || 'brush';
const defaults = { radius: 145, hint: true, hub: 10, tap_ms: 250, tag_limit: 12, colors: { bg: '#101010' } };
const fresh = () => ({
  ring: {},
  menus: {
    main: { title: 'Main', hotkey: 'Q', items: [{ brush: 'A' }, { press: 'Tool:Move' }, { toggle: 'Draw:Zadd' }, { menu: 'other' }] },
    other: { title: 'Other', items: [{ brush: 'B' }] },
  },
});
const ctxFor = cfg => ({ defaults, kindOf, menuOf: id => (cfg.menus && Object.prototype.hasOwnProperty.call(cfg.menus, id) ? cfg.menus[id] : undefined) });
const needs = cfg => M.needsFull(cfg, ctxFor(cfg));
const target = (t, cfg) => M.targetNeedsFull(t, ctxFor(cfg || fresh()));
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('the hint line is not a Full setting', () => {
  assert(!('hint' in M.FULL_RING));
  const cfg = fresh();
  cfg.ring.hint = false;
  assert.deepStrictEqual(M.fullOnlyChanges(cfg, undefined, ctxFor(cfg)), []);
  assert(!needs(cfg));
  assert(!target({ kind: 'settings', card: 'set-behaviour', key: 'hint' }));
});

test('Press and Toggle are everyday item types; Set, Capture, Tool, Project, Layout, Steps, Auto, Tag and Browser are Full only', () => {
  for (const k of ['brush', 'alpha', 'material', 'texture', 'press', 'toggle', 'menu', 'empty']) assert(!M.kindIsFull(k), k);
  for (const k of ['set', 'capture', 'tool', 'project', 'layout', 'steps', 'auto', 'tag', 'browser', 'recent']) assert(M.kindIsFull(k), k);
  const cfg = fresh();
  assert(!needs(cfg));
  cfg.menus.other.items.push({ steps: [] });
  assert(needs(cfg));
});

test('a next-profile hotkey is a Full setting: the note names it, and it needs Full', () => {
  const cfg = fresh();
  cfg.profile = { next_hotkey: 'Alt+P' };
  assert.deepStrictEqual(M.fullOnlyChanges(cfg, 'settings', ctxFor(cfg)), ['Next profile hotkey']);
  assert.deepStrictEqual(M.fullOnlyChanges(cfg, 'look', ctxFor(cfg)), []);
  assert(needs(cfg));
  delete cfg.profile;

  cfg.browser = { quit_after_minutes: 30 };
  assert.deepStrictEqual(M.fullOnlyChanges(cfg, 'settings', ctxFor(cfg)), ['Quit hidden browser after']);
  assert.deepStrictEqual(M.fullOnlyChanges(cfg, 'look', ctxFor(cfg)), []);
  assert(needs(cfg));
  cfg.browser = { quit_after_minutes: 0 };
  assert(!needs(cfg));
  delete cfg.browser;
  assert(!needs(cfg));
});

test('a look picked for a menu by name is not a Full setting; one with settings of its own is', () => {
  const cfg = fresh();
  cfg.menus.main.look = 'soft';
  assert(!needs(cfg));
  cfg.menus.main.look = { preset: 'soft' };
  assert(!needs(cfg));
  cfg.menus.main.look = {};
  assert(!needs(cfg));
  cfg.menus.main.look = { hub: 30 };
  assert(needs(cfg));
  cfg.menus.main.look = { preset: 'soft', hub: 30 };
  assert(needs(cfg));
});

test('fan out or a swallowed hotkey turned off on a menu needs Full', () => {
  for (const set of [m => { m.fan = true; }, m => { m.swallow = false; }]) {
    const cfg = fresh();
    set(cfg.menus.main);
    assert(needs(cfg));
  }
});

test('an open animation on a menu does not need Full: Look sets it in both modes', () => {
  const cfg = fresh();
  cfg.menus.main.animation = 'spiral';
  assert(!needs(cfg));
});

test('a Full ring setting that differs from the default needs Full', () => {
  const cfg = fresh();
  cfg.ring.hub = 30;
  assert.deepStrictEqual(M.fullOnlyChanges(cfg, undefined, ctxFor(cfg)), ['Hub']);
  assert.deepStrictEqual(M.fullOnlyChanges(cfg, 'look', ctxFor(cfg)), ['Hub']);
  assert.deepStrictEqual(M.fullOnlyChanges(cfg, 'settings', ctxFor(cfg)), []);
  assert(needs(cfg));
  cfg.ring.hub = 10;
  assert(!needs(cfg));
});

test('the Look-screen names of look keys that only Full shows', () => {
  assert.deepStrictEqual(M.fullOnlyLookNames(['hub', 'hub_style', 'colors.bg', 'radius', 'labels', 'glow_color']), ['Hub', 'Colours', 'Glow']);
  assert.deepStrictEqual(M.fullOnlyLookNames(['radius', 'slot_shape']), []);
  assert.deepStrictEqual(M.fullOnlyLookNames(undefined), []);
});

test('problem targets: a named look, Swallow hotkey and Fan out switch to Full; so does a hub or a slot', () => {
  assert(target({ kind: 'look', level: 'preset', name: 'soft' }));
  assert(target({ kind: 'menu', menuId: 'main', field: 'swallow' }));
  assert(target({ kind: 'menu', menuId: 'main', field: 'fan' }));
  assert(target({ kind: 'menu', menuId: 'main', field: 'id' }));
  assert(target({ kind: 'look', level: 'global', key: 'hub' }));
  assert(target({ kind: 'look', level: 'menu', menuId: 'main', slot: 0 }));
  assert(target({ kind: 'settings', card: 'set-zbrush-bridge' }));
});

test('problem targets: the everyday places stay in Simple', () => {
  assert(!target({ kind: 'look', level: 'menu', menuId: 'main', key: 'animation', group: 'opening' }));
  assert(!target({ kind: 'look', level: 'global', key: 'animation', group: 'opening' }));
  assert(!target({ kind: 'look', level: 'global', key: 'radius' }));
  assert(!target({ kind: 'look', level: 'menu', menuId: 'main', key: 'slot_shape' }));
  assert(!target({ kind: 'menu', menuId: 'main', field: 'hotkey' }));
  assert(!target({ kind: 'menu', menuId: 'main' }));
  assert(!target({ kind: 'settings', card: 'set-behaviour', key: 'flick' }));
  assert(!target(null));
});

test('problem targets: an item needs Full only when its type does', () => {
  const cfg = fresh();
  cfg.menus.other.items.push({ tag: 'hard' });
  assert(!target({ kind: 'item', menuId: 'main', index: 1 }, cfg));         // a Press item
  assert(!target({ kind: 'item', menuId: 'main', index: 2 }, cfg));         // a Toggle item
  assert(target({ kind: 'item', menuId: 'other', index: 1 }, cfg));         // a Tag item
  assert(!target({ kind: 'item', menuId: 'gone', index: 0 }, cfg));
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); } catch (e) { failed++; console.log('FAIL ' + name + '\n  ' + (e && e.message)); }
}
if (failed) { console.log(failed + ' of ' + tests.length + ' mode checks failed'); process.exit(1); }
console.log('mode gating checks pass (' + tests.length + ')');
