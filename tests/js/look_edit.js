/* The editing half of Studio's look.js: pin or drop, the canonical form of a menu's look, Apply, rename, delete and bake.
   Run by tests/test_look_parity.py:  node tests/js/look_edit.js */
'use strict';
const assert = require('assert');
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const Z = require(path.join(root, 'zorbit', 'studio_ui', 'look.js'));
const opts = JSON.parse(fs.readFileSync(path.join(root, 'tests', 'fixtures', 'look_options.json'), 'utf8'));
const ctx = { looks: opts.looks, defaults: opts.ring_defaults, colors: opts.theme_ring_colors, animations: opts.animations, theme: 'dark' };
const G = { level: 'global' }, M = { level: 'menu', menu: 'main' };
const fresh = () => ({ ring: {}, menus: { main: { title: 'Main', items: [{ brush: 'A' }] }, other: { title: 'Other', items: [{ brush: 'B' }] } } });
const tests = [];
const test = (name, fn) => tests.push([name, fn]);

test('a value equal to the default is dropped, any other is written', () => {
  const cfg = fresh();
  assert(Z.set(cfg, G, 'radius', 200, ctx));
  assert.strictEqual(cfg.ring.radius, 200);
  assert(Z.set(cfg, G, 'radius', 145, ctx));
  assert(!('radius' in cfg.ring));
  assert(!Z.set(cfg, G, 'radius', 145, ctx));
});

test('a value equal to what a look gives is pinned, and only clear removes it', () => {
  const cfg = fresh();
  cfg.ring.look = 'tiles';                                   // tiles: hub_style ring, hub 14
  assert(Z.set(cfg, G, 'hub', 14, ctx));
  assert.strictEqual(cfg.ring.hub, 14);
  assert(Z.set(cfg, G, 'hub', 14, ctx) === false);
  assert(Z.clear(cfg, G, 'hub', ctx));
  assert(!('hub' in cfg.ring));
  assert.strictEqual(Z.resolve(cfg, G, ctx).hub.value, 14);
  assert.strictEqual(Z.resolve(cfg, G, ctx).hub.origin, 'global-preset');
});

test('a menu keeps its settings under a canonical look: a name, an object, or nothing', () => {
  const cfg = fresh();
  Z.set(cfg, M, 'hub', 30, ctx);
  assert.deepStrictEqual(cfg.menus.main.look, { hub: 30 });
  Z.usePreset(cfg, M, 'soft', { keep: true }, ctx);
  assert.deepStrictEqual(cfg.menus.main.look, { preset: 'soft', hub: 30 });
  Z.clear(cfg, M, 'hub', ctx);
  assert.strictEqual(cfg.menus.main.look, 'soft');
  Z.set(cfg, M, 'labels', 'none', ctx);
  assert.deepStrictEqual(cfg.menus.main.look, { preset: 'soft', labels: 'none' });
  Z.usePreset(cfg, M, '', { keep: true }, ctx);
  assert.deepStrictEqual(cfg.menus.main.look, { labels: 'none' });
  Z.clear(cfg, M, 'labels', ctx);
  assert(!('look' in cfg.menus.main));
});

test('a menu setting equal to the default is dropped only when the ring gives the default too', () => {
  const cfg = fresh();
  cfg.ring.hub = 30;
  Z.set(cfg, M, 'hub', 10, ctx);                             // 10 is the default, but the ring says 30: the menu must say 10
  assert.deepStrictEqual(cfg.menus.main.look, { hub: 10 });
  delete cfg.ring.hub;
  Z.set(cfg, M, 'hub', 10, ctx);
  assert(!('look' in cfg.menus.main));
});

test('colours are set one at a time and dropped when they equal the theme', () => {
  const cfg = fresh();
  Z.set(cfg, G, 'colors.accent', '#112233', ctx);
  assert.deepStrictEqual(cfg.ring.colors, { accent: '#112233' });
  assert.strictEqual(Z.resolve(cfg, G, ctx).colors.sub.accent.origin, 'global');
  assert.strictEqual(Z.resolve(cfg, G, ctx).colors.sub.bg.origin, 'default');
  Z.set(cfg, G, 'colors.accent', opts.theme_ring_colors.dark.accent.toUpperCase(), ctx);
  assert(!('colors' in cfg.ring));
});

test('Apply removes the settings that would hide the look, and keeps ring size and colours', () => {
  const cfg = fresh();
  Object.assign(cfg.ring, { radius: 200, slot_shape: 'hexagon', hub: 20, labels: 'none', colors: { bg: '#111111' }, tag_band: 'wide', tap_ms: 300 });
  const n = Z.usePreset(cfg, G, 'tiles', {}, ctx);
  assert.strictEqual(n, 3);                                  // slot_shape, hub, labels
  assert.deepStrictEqual(cfg.ring, { radius: 200, colors: { bg: '#111111' }, tag_band: 'wide', tap_ms: 300, look: 'tiles' });
  Z.usePreset(cfg, G, 'classic', { keep: true }, ctx);
  assert(!('look' in cfg.ring));
});

test('a value written at the default (a starter file) is not a setting of its own', () => {
  const cfg = fresh();
  Object.assign(cfg.ring, { radius: 145, labels: 'name', hub: 30, colors: { accent: opts.theme_ring_colors.dark.accent } });
  assert.strictEqual(Z.resolve(cfg, G, ctx).radius.origin, 'default');
  assert(!Z.isSet(cfg, G, 'labels', ctx) && !Z.isSet(cfg, G, 'colors.accent', ctx) && Z.isSet(cfg, G, 'hub', ctx));
  assert.deepStrictEqual(Z.settings(cfg, G, ctx), ['hub']);
  assert.strictEqual(Z.explain(cfg, G, ctx).origins.radius.from, 'global');          // looks.py counts it: the origins mirror it
  assert.strictEqual(Z.usePreset(cfg, G, 'tiles', {}, ctx), 1);                      // hub counts; labels and radius go quietly
  assert(!('labels' in cfg.ring) && 'radius' in cfg.ring && !('hub' in cfg.ring));
});

test('Apply, keep my changes removes nothing', () => {
  const cfg = fresh();
  cfg.ring.hub = 20;
  assert.strictEqual(Z.usePreset(cfg, M, 'tiles', { keep: true }, ctx), 0);
  assert.strictEqual(cfg.ring.hub, 20);
  assert.strictEqual(cfg.menus.main.look, 'tiles');
});

test('a look made from what the ring shows leaves out ring size unless asked', () => {
  const cfg = fresh();
  Object.assign(cfg.ring, { look: 'soft', radius: 200, hub: 22, colors: { lines: '#abcdef' } });
  const dict = Z.newPreset(cfg, G, 'Mine', {}, ctx);
  assert(!('radius' in dict));
  assert.strictEqual(dict.hub, 22);
  assert.strictEqual(dict.slot_shape, 'squircle');            // from soft
  assert.deepStrictEqual(dict.colors, { lines: '#abcdef' });
  Z.newPreset(cfg, G, 'Sized', { geometry: true }, ctx);
  assert.strictEqual(cfg.looks.Sized.radius, 200);
  assert.deepStrictEqual(Object.keys(cfg.looks), ['Mine', 'Sized']);
  assert.throws(() => Z.newPreset(cfg, G, 'soft', {}, ctx));
  assert(Z.nameProblem('Soft', ctx) && Z.nameProblem('', ctx) && Z.nameProblem('a'.repeat(33), ctx) && !Z.nameProblem('Café 2', ctx));
});

test('rename follows every reference and keeps the order', () => {
  const cfg = fresh();
  cfg.looks = { A: { hub: 20 }, B: { hub: 30 }, C: {} };
  cfg.ring.look = 'B';
  cfg.menus.main.look = 'B';
  cfg.menus.other.look = { preset: 'B', labels: 'none' };
  assert.strictEqual(Z.rename(cfg, 'B', 'Bee', ctx), 3);
  assert.deepStrictEqual(Object.keys(cfg.looks), ['A', 'Bee', 'C']);
  assert.strictEqual(cfg.ring.look, 'Bee');
  assert.strictEqual(cfg.menus.main.look, 'Bee');
  assert.strictEqual(cfg.menus.other.look.preset, 'Bee');
  assert.deepStrictEqual(Z.usersOf(cfg, 'Bee'), { global: true, menus: ['main', 'other'] });
});

test('deleting a look can bake it into whoever used it', () => {
  const cfg = fresh();
  cfg.looks = { Big: { hub: 40, labels: 'none', colors: { accent: '#010203' } } };
  cfg.ring.look = 'Big';
  cfg.menus.main.look = { preset: 'Big', hub: 12 };
  cfg.menus.other.look = 'Big';
  Z.remove(cfg, 'Big', { bake: true }, ctx);
  assert(!('looks' in cfg));
  assert.deepStrictEqual(cfg.ring, { hub: 40, labels: 'none', colors: { accent: '#010203' } });
  assert.deepStrictEqual(cfg.menus.main.look, { hub: 12, labels: 'none', colors: { accent: '#010203' } });
  assert.deepStrictEqual(cfg.menus.other.look, { hub: 40, labels: 'none', colors: { accent: '#010203' } });
});

test('deleting a look without baking sends its users back to the level above', () => {
  const cfg = fresh();
  cfg.looks = { Big: { hub: 40 }, Keep: {} };
  cfg.ring.look = 'Big';
  cfg.menus.main.look = { preset: 'Big', labels: 'none' };
  cfg.menus.other.look = 'Big';
  Z.remove(cfg, 'Big', {}, ctx);
  assert.deepStrictEqual(cfg.looks, { Keep: {} });
  assert(!('look' in cfg.ring));
  assert.deepStrictEqual(cfg.menus.main.look, { labels: 'none' });
  assert(!('look' in cfg.menus.other));
  assert.deepStrictEqual(Z.problems(cfg, ctx), []);
});

test('the preset level edits the look itself', () => {
  const cfg = fresh();
  cfg.looks = { Mine: { hub: 20 } };
  const P = { level: 'preset', name: 'Mine' };
  Z.set(cfg, P, 'slot_shape', 'hexagon', ctx);
  assert.deepStrictEqual(cfg.looks.Mine, { hub: 20, slot_shape: 'hexagon' });
  assert.strictEqual(Z.resolve(cfg, P, ctx).hub.origin, 'preset');
  assert.strictEqual(Z.resolve(cfg, P, ctx).labels.origin, 'default');
  Z.set(cfg, P, 'hub', 10, ctx);                              // the default again: dropped
  assert.deepStrictEqual(cfg.looks.Mine, { slot_shape: 'hexagon' });
});

test('the summary says what a level uses', () => {
  const cfg = fresh();
  assert.strictEqual(Z.summary(cfg, M, ctx).text, 'Same as all menus');
  assert.strictEqual(Z.summary(cfg, G, ctx).text, 'Classic');
  cfg.menus.main.look = { preset: 'soft', hub: 3, colors: { bg: '#000000', text: '#ffffff' } };
  assert.strictEqual(Z.summary(cfg, M, ctx).text, 'Soft + 3 changes');
  cfg.menus.main.look = { hub: 3 };
  assert.strictEqual(Z.summary(cfg, M, ctx).text, 'Custom (1 change)');
  cfg.menus.main.look = 'Gone';
  assert.strictEqual(Z.summary(cfg, M, ctx).text, 'Gone (missing)');
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); } catch (e) { failed++; console.log('FAIL ' + name + '\n  ' + String(e.message).split('\n').join('\n  ')); }
}
console.log((tests.length - failed) + ' of ' + tests.length + ' look editing checks pass');
process.exit(failed ? 1 : 0);
