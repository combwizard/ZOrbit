/* Runs Studio's look resolver (zorbit/studio_ui/look.js) over tests/fixtures/look_cases.json and checks that it gives the values,
   the origins and the loader's messages that zorbit/looks.py gives. The fixtures come from tools/make_look_cases.py.
   Run by tests/test_look_parity.py:  node tests/js/look_parity.js   (exit 1 and a list of what differs when it does not match) */
'use strict';
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..', '..');
const Z = require(path.join(root, 'zorbit', 'studio_ui', 'look.js'));
const cases = JSON.parse(fs.readFileSync(path.join(root, 'tests', 'fixtures', 'look_cases.json'), 'utf8'));
const opts = JSON.parse(fs.readFileSync(path.join(root, 'tests', 'fixtures', 'look_options.json'), 'utf8'));

function sorted(v) {
  if (Array.isArray(v)) return v.map(sorted);
  if (v && typeof v === 'object') return Object.fromEntries(Object.keys(v).sort().map(k => [k, sorted(v[k])]));
  return v;
}
const same = (a, b) => JSON.stringify(sorted(a)) === JSON.stringify(sorted(b));
function diff(got, want) {
  const out = [];
  for (const k of new Set([...Object.keys(got), ...Object.keys(want)])) {
    if (!same(got[k], want[k])) out.push(k + ': got ' + JSON.stringify(got[k]) + ', want ' + JSON.stringify(want[k]));
  }
  return out;
}

let failed = 0;
for (const c of cases) {
  const ctx = { looks: opts.looks, defaults: opts.ring_defaults, colors: opts.theme_ring_colors, animations: opts.animations, theme: c.theme };
  const cfg = { ring: c.ring, looks: c.looks, menus: c.menus };
  const t = c.target;
  const target = 'slot' in t ? { level: 'menu', menu: t.menu, slot: t.slot } : 'menu' in t ? { level: 'menu', menu: t.menu } : { level: 'global' };
  const got = Z.explain(cfg, target, ctx);
  const problems = Z.problems(cfg, ctx);
  const bad = [...diff(got.values, c.expected.values).map(l => '  values.' + l), ...diff(got.origins, c.expected.origins).map(l => '  origins.' + l)];
  if (!same(problems, c.expected.problems)) bad.push('  problems: got ' + JSON.stringify(problems) + ', want ' + JSON.stringify(c.expected.problems));
  if (bad.length) { failed++; console.log('FAIL ' + c.name + '\n' + bad.join('\n')); }
}
console.log((cases.length - failed) + ' of ' + cases.length + ' look cases match looks.py (ring, menu and slot levels)');
process.exit(failed ? 1 : 0);
