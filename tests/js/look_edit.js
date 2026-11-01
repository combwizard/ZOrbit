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

const SL = { level: 'menu', menu: 'main', slot: 0 };

test('a slot keeps its style on the item: written when it differs, dropped when it says the default, removed when empty', () => {
  const cfg = fresh();
  assert(Z.set(cfg, SL, 'slot_shape', 'hexagon', ctx));
  assert.deepStrictEqual(cfg.menus.main.items[0], { brush: 'A', style: { slot_shape: 'hexagon' } });
  assert(Z.isSet(cfg, SL, 'slot_shape', ctx));
  assert.strictEqual(Z.resolve(cfg, SL, ctx).slot_shape.origin, 'slot');
  assert(Z.set(cfg, SL, 'slot_shape', 'circle', ctx));        // the default again: dropped, and the empty style goes
  assert.deepStrictEqual(cfg.menus.main.items[0], { brush: 'A' });
  Z.set(cfg, SL, 'border_width', 4, ctx);
  Z.set(cfg, SL, 'glow_color', '#ff8800', ctx);
  assert.strictEqual(Z.ownCount(cfg, SL, ctx), 2);
  assert(Z.clear(cfg, SL, 'border_width', ctx));
  assert.deepStrictEqual(cfg.menus.main.items[0].style, { glow_color: '#ff8800' });
  assert.strictEqual(Z.clearAll(cfg, SL, ctx), 1);
  assert(!('style' in cfg.menus.main.items[0]));
});

test('a slot pins a value that its menu gives, and reads the menu around it', () => {
  const cfg = fresh();
  cfg.menus.main.look = { slot_shape: 'hexagon', border_width: 5 };
  assert.strictEqual(Z.resolve(cfg, SL, ctx).slot_shape.origin, 'menu');
  assert.strictEqual(Z.resolve(cfg, SL, ctx).border_width.value, 5);
  Z.set(cfg, SL, 'slot_shape', 'hexagon', ctx);               // the same as the menu says: kept, so a later change of the menu does not move it
  assert.deepStrictEqual(cfg.menus.main.items[0].style, { slot_shape: 'hexagon' });
  Z.set(cfg, SL, 'border_width', 2, ctx);                     // the default, but the menu says 5: the slot must say 2
  assert.strictEqual(cfg.menus.main.items[0].style.border_width, 2);
  assert.strictEqual(Z.explain(cfg, SL, ctx).values.border_width, 2);
  assert.strictEqual(Z.explain(cfg, SL, ctx).origins.border_width.from, 'slot');
  assert.strictEqual(Z.explain(cfg, M, ctx).values.border_width, 5);          // the menu is untouched
});

test('the slot-only keys read as their defaults and drop when they are set to them', () => {
  const cfg = fresh();
  const r = Z.resolve(cfg, SL, ctx);
  assert.strictEqual(r.size.value, 1);
  assert.strictEqual(r.fill_color.value, '');
  assert.strictEqual(r.size.origin, 'default');
  Z.set(cfg, SL, 'size', 1.1, ctx);
  assert.strictEqual(cfg.menus.main.items[0].style.size, 1.1);
  assert.strictEqual(Z.resolve(cfg, SL, ctx).size.origin, 'slot');
  Z.set(cfg, SL, 'size', 1, ctx);
  assert(!('style' in cfg.menus.main.items[0]));
  Z.set(cfg, SL, 'fill_color', 'accent', ctx);                // a role stays a role in the file
  assert.strictEqual(cfg.menus.main.items[0].style.fill_color, 'accent');
  assert.strictEqual(Z.resolve(cfg, SL, ctx).fill_color.eff, opts.theme_ring_colors.dark.accent);
});

test('a slot takes style keys only, and only the keys of its level are listed', () => {
  const cfg = fresh();
  assert.throws(() => Z.set(cfg, SL, 'radius', 100, ctx));
  assert.throws(() => Z.set(cfg, SL, 'colors.bg', '#000000', ctx));
  assert.throws(() => Z.set(cfg, { level: 'menu', menu: 'main', slot: 5 }, 'size', 1.2, ctx));       // no such item
  const slotKeys = Z.keysAt(ctx, 'slot');
  assert.deepStrictEqual(slotKeys.slice().sort(), ['border_color', 'border_width', 'fill_color', 'glow_color', 'icon_scale', 'label_color', 'size', 'slot_corner', 'slot_shape']);
  assert.deepStrictEqual(Z.groups(ctx, 'slot').map(g => g.id), ['slots', 'glow', 'labels']);
  assert(!Z.keysAt(ctx, 'menu').includes('size'));
  assert.strictEqual(Z.levelOf(SL), 'slot');
  assert.strictEqual(Z.levelOf(M), 'menu');
});

test('a style that is not an object is replaced when a slot is edited', () => {
  const cfg = fresh();
  cfg.menus.main.items[0].style = 'hexagon';
  Z.set(cfg, SL, 'size', 1.2, ctx);
  assert.deepStrictEqual(cfg.menus.main.items[0].style, { size: 1.2 });
});

/* A ring layout like Ring.layout_map gives: one ring, or two (inner slots inside, the rest outside, offset half a step). */
function ringLayout(n, o) {
  o = o || {};
  const dead = 30, size = 60, centre = [250, 250], inner = o.inner, shape = o.shape || 'circle';
  const rings = [], slots = [], gaps = [];
  const add = (ring, first, count, r, offset, rmin) => {
    const step = 360 / count;
    rings.push({ r, first, n: count, offset, step, rmin });
    for (let j = 0; j < count; j++) {
      const a = (offset + step * j) * Math.PI / 180;
      slots.push({ i: first + j, ring, x: Math.sin(a) * r, y: -Math.cos(a) * r, size, shape, corner: 0.28, ang: offset + step * j, half: Math.min(step, 90) / 2, more: !!o.more && first + j === n - 1 });
    }
    const lo = ring > 0 ? 0 : 1, hi = ring === 0 && inner ? count - 1 : count;
    for (let j = lo; j <= hi; j++) { const g = (offset + step * (j - 0.5)) * Math.PI / 180; gaps.push({ k: first + j, x: Math.sin(g) * r, y: -Math.cos(g) * r, ang: (offset + step * (j - 0.5) + 360) % 360 }); }
  };
  if (inner) { add(0, 0, inner, 100, 0, dead); add(1, inner, n - inner, 190, 360 / (n - inner) / 2, 145); } else add(0, 0, n, 100, 0, dead);
  return { scale: 1, size: [500, 500], centre, dead, hub: { style: 'dot', r: 5 }, rings, slots, gaps,
    full: { mode: inner ? 'rings' : 'grow', when_full: o.more ? 'more' : inner ? 'rings' : 'grow', n, capacity: inner || n, needed: 100, radius: 100, grown: false, rings: inner ? 2 : 1, more_slot: o.more ? n - 1 : null }, fans: [] };
}
const pol = (r, a) => [Math.sin(a * Math.PI / 180) * r, -Math.cos(a * Math.PI / 180) * r];

test('slotAt picks on a slot first, then by the slot whose angle the point is in', () => {
  const L = ringLayout(8);
  assert.strictEqual(Z.slotAt(L, 0, -100), 0);                // on slot 0's disc
  assert.strictEqual(Z.slotAt(L, ...pol(100, 45)), 1);
  assert.strictEqual(Z.slotAt(L, ...pol(170, 52)), 1);        // beyond the disc, inside the wedge of slot 1 (45 +- 22.5)
  assert.strictEqual(Z.slotAt(L, ...pol(60, 358)), 0);        // the wedge of slot 0 wraps past 360
  assert.strictEqual(Z.slotAt(L, 0, 0), null);                // the dead zone
  assert.strictEqual(Z.slotAt(L, ...pol(20, 90)), null);
  assert.strictEqual(Z.slotAt(null, 1, 1), null);
});

test('a sparse ring answers only within a wedge of 90 degrees at most', () => {
  const L = ringLayout(2);                                    // slots at 0 and 180, step 180: each answers to +- 45
  assert.strictEqual(Z.slotAt(L, ...pol(150, 40)), 0);
  assert.strictEqual(Z.slotAt(L, ...pol(150, 90)), null);     // between the wedges
  assert.strictEqual(Z.slotAt(L, ...pol(150, 140)), 1);
});

test('a rounded slot answers anywhere in its box, a hexagon only inside its corners', () => {
  assert(Z.insideShape('rounded', 29, 29, 30) && !Z.insideShape('circle', 29, 29, 30) && !Z.insideShape('hexagon', 29, 0, 30));
  assert(Z.insideShape('hexagon', 0, 29, 30) && Z.insideShape('hexagon', 25, 14, 30));
  assert(Z.insideShape('diamond', 33, 0, 30) && !Z.insideShape('diamond', 30, 30, 30));
  assert(Z.insideShape('squircle', 20, 20, 30) && !Z.insideShape('squircle', 26, 26, 30));
  // a slot's own shape wins over the wedge of its neighbour: a big rounded slot 1 reaches into the wedge of slot 0
  const L = ringLayout(8, { shape: 'rounded' });
  L.slots[1].size = 120;
  assert.strictEqual(Z.slotAt(L, ...pol(100, 45).map((v, i) => v + (i ? 55 : -55))), 1);
});

test('with two rings the band a point is in decides the ring, and each ring has its own angles', () => {
  const L = ringLayout(10, { inner: 4 });                     // inner slots at 0 90 180 270; outer 6 slots at 30 90 150 210 270 330
  assert.strictEqual(Z.slotAt(L, ...pol(100, 90)), 1);
  assert.strictEqual(Z.slotAt(L, ...pol(120, 30)), 0);        // still the inner band (below rmin 145): slot 0 (0 +- 45)
  assert.strictEqual(Z.slotAt(L, ...pol(160, 20)), 4);        // the outer band: slot 4 is the one at 30
  assert.strictEqual(Z.slotAt(L, ...pol(160, 80)), 5);        // outer slot at 90
  assert.strictEqual(Z.slotAt(L, ...pol(10, 80)), null);
});

test('gapAt finds the gap beside the nearest slot of the ring, and the wrap before the first slot', () => {
  const L = ringLayout(8);
  const a = Z.gapAt(L, ...pol(100, 25));                      // just after slot 0
  assert.strictEqual(a.k, 1);
  assert(Math.abs(a.ang - 22.5) < 0.01 && Math.abs(a.len - 75) < 0.01);
  assert.strictEqual(Z.gapAt(L, ...pol(100, 70)).k, 2);       // 70 is after slot 1 (at 45) and before slot 2 (at 90)
  assert.strictEqual(Z.gapAt(L, ...pol(100, 350)).k, 8);      // before slot 0: the wrap, which is the end of the list
  assert.strictEqual(Z.gapAt(L, ...pol(100, 340)).k, 8);      // after slot 7 (at 315): the same gap
  assert.strictEqual(Z.gapAt(L, 5, 5), null);                 // the dead zone
});

test('gapAt across two rings: the first ring wraps to the boundary, the second to the end', () => {
  const L = ringLayout(10, { inner: 4 });
  const wrap = Z.gapAt(L, ...pol(100, 350));
  assert.strictEqual(wrap.k, 4);                              // the end of the inner ring is before the first outer item
  assert(Math.abs(wrap.ang - 315) < 0.01 && Math.abs(Math.hypot(wrap.x, wrap.y) - 100) < 0.5);
  const start = Z.gapAt(L, ...pol(190, 10));                  // outer ring, just after the spot where it wraps: before its first slot
  assert.strictEqual(start.k, 4);
  const end = Z.gapAt(L, ...pol(190, 350));                   // just before the spot: after its last slot
  assert.strictEqual(end.k, 10);
  assert(Math.abs(Math.hypot(end.x, end.y) - 190) < 0.5);
  assert.strictEqual(Z.gapAt(L, ...pol(190, 100)).k, 6);      // between outer slots at 90 and 150: k = first + 2
});

test('a gap beside the More slot puts an item into More', () => {
  const L = ringLayout(6, { more: true });                    // five items and a More slot at index 5
  assert.strictEqual(Z.gapAt(L, ...pol(100, 275)).k, 5);      // between slot 4 (at 240) and More (at 300)
  assert(Z.gapAt(L, ...pol(100, 275)).into_more);
  assert.strictEqual(Z.gapAt(L, ...pol(100, 330)).k, 6);      // after More: the end
  assert(Z.gapAt(L, ...pol(100, 330)).into_more);
  assert(!Z.gapAt(L, ...pol(100, 30)).into_more);
});

test('a layout fits a menu with as many items, or more when it has a More slot', () => {
  assert(Z.layoutFits(ringLayout(8), 8));
  assert(!Z.layoutFits(ringLayout(8), 9) && !Z.layoutFits(ringLayout(8), 7));
  assert(Z.layoutFits(ringLayout(6, { more: true }), 11));
  assert(!Z.layoutFits(ringLayout(6, { more: true }), 4));
  assert(!Z.layoutFits(null, 3) && !Z.layoutFits({ slots: [] }, 0));
});

test('shapePoints gives the outline of the polygon shapes', () => {
  assert.strictEqual(Z.shapePoints('circle', 0, 0, 10), null);
  assert.strictEqual(Z.shapePoints('rounded', 0, 0, 10), null);
  assert.strictEqual(Z.shapePoints('hexagon', 0, 0, 10).length, 6);
  assert.strictEqual(Z.shapePoints('octagon', 0, 0, 10).length, 8);
  assert.strictEqual(Z.shapePoints('diamond', 0, 0, 10).length, 4);
  assert.strictEqual(Z.shapePoints('squircle', 0, 0, 10).length, 96);
  const hex = Z.shapePoints('hexagon', 0, 0, 10);
  assert(Math.abs(hex[0][0]) < 1e-9 && Math.abs(hex[0][1] + 10) < 1e-9);                  // pointy top: circumradius r
  const dia = Z.shapePoints('diamond', 0, 0, 10);
  assert(Math.abs(Math.hypot(dia[0][0], dia[0][1]) - 11.5) < 1e-9);                       // a tip reaches 1.15 r
  const oct = Z.shapePoints('octagon', 0, 0, 10);
  assert(Math.abs(Math.max(...oct.map(p => p[1])) - 10) < 1e-9);                          // flat top: the apothem is r
});

let failed = 0;
for (const [name, fn] of tests) {
  try { fn(); } catch (e) { failed++; console.log('FAIL ' + name + '\n  ' + String(e.message).split('\n').join('\n  ')); }
}
console.log((tests.length - failed) + ' of ' + tests.length + ' look editing checks pass');
process.exit(failed ? 1 : 0);
