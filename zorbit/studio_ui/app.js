/* ZOrbit Studio front-end.
   Plain JS, no dependencies. The config object (S.cfg) is the single source of truth; every backend call
   receives the whole thing. Sections: helpers, state + config logic, backend loaders (ring / frames / thumbs),
   UI primitives (toast, modal, popover, drag and drop, combobox, hotkey recorder), then the four screens.
   The same file drives the browser popout (popout.html sets window.__ZORBIT_MODE__ = 'popout'): makeBrowser takes a
   `host` that says what a pick does, and buildPopout wraps it in the popout's header. */
(() => {
'use strict';

/* ================================================================== helpers */
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const clone = o => JSON.parse(JSON.stringify(o));
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const sleep = ms => new Promise(r => setTimeout(r, ms));
function debounce(fn, ms) {
  let t = null;
  const d = (...a) => { clearTimeout(t); t = setTimeout(() => { t = null; fn(...a); }, ms); };
  d.cancel = () => { clearTimeout(t); t = null; };
  d.flush = () => { if (t) { clearTimeout(t); t = null; fn(); } };
  return d;
}

function append(el, kids) {
  for (const c of kids) {
    if (c === null || c === undefined || c === false) continue;
    if (Array.isArray(c)) append(el, c);
    else el.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
}
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  let value;
  if (attrs) for (const k in attrs) {
    const v = attrs[k];
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style') {
      if (typeof v === 'string') el.style.cssText = v;
      else for (const p in v) p.startsWith('--') ? el.style.setProperty(p, v[p]) : (el.style[p] = v[p]);
    }
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k.slice(0, 2) === 'on' && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else if (k === 'value') value = v;
    else if (k === 'checked' || k === 'disabled' || k === 'readOnly' || k === 'selected') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  append(el, kids);
  if (value !== undefined) el.value = value;
  return el;
}

const ICONS = {
  menus: '<circle cx="12" cy="12" r="2"/><circle cx="12" cy="4.6" r="1.9"/><circle cx="18.4" cy="8.3" r="1.9"/><circle cx="18.4" cy="15.7" r="1.9"/><circle cx="12" cy="19.4" r="1.9"/><circle cx="5.6" cy="15.7" r="1.9"/><circle cx="5.6" cy="8.3" r="1.9"/>',
  library: '<rect x="4" y="4" width="7" height="7" rx="1.6"/><rect x="13" y="4" width="7" height="7" rx="1.6"/><rect x="4" y="13" width="7" height="7" rx="1.6"/><rect x="13" y="13" width="7" height="7" rx="1.6"/>',
  settings: '<path d="M4 7h8M18 7h2M4 12h5M13 12h7M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="11" cy="12" r="2"/><circle cx="9" cy="17" r="2"/>',
  status: '<path d="M3 12h4l2.5-6 4 12 2.5-6H21"/>',
  setup: '<path d="M5 7l1.5 1.5L9 6M5 12l1.5 1.5L9 11M5 17l1.5 1.5L9 16"/><path d="M12 7h8M12 12h8M12 17h8"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  copy: '<rect x="8.5" y="8.5" width="11" height="11" rx="2"/><path d="M15.5 8.5V6.5a2 2 0 0 0-2-2h-7a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h2"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4"/>',
  trash: '<path d="M5 7h14M10 11v6M14 11v6M6.5 7l1 12a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1l1-12M9 7V4.5h6V7"/>',
  grip: '<g fill="currentColor" stroke="none"><circle cx="9" cy="6" r="1.4"/><circle cx="15" cy="6" r="1.4"/><circle cx="9" cy="12" r="1.4"/><circle cx="15" cy="12" r="1.4"/><circle cx="9" cy="18" r="1.4"/><circle cx="15" cy="18" r="1.4"/></g>',
  chevD: '<path d="M6 9l6 6 6-6"/>',
  chevR: '<path d="M9 6l6 6-6 6"/>',
  chevL: '<path d="M15 6l-6 6 6 6"/>',
  up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  down: '<path d="M12 5v14M6 13l6 6 6-6"/>',
  play: '<path d="M8 5.5l11 6.5-11 6.5z" fill="currentColor"/>',
  stop: '<rect x="6.5" y="6.5" width="11" height="11" rx="1.8" fill="currentColor" stroke="none"/>',
  search: '<circle cx="11" cy="11" r="6"/><path d="M20 20l-4.5-4.5"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  refresh: '<path d="M19.500 12a7.500 7.500 0 0 1-13 5.100M4.500 12a7.500 7.500 0 0 1 13-5.100"/><path d="M17.500 3.500v3.400h-3.400M6.500 20.500v-3.400h3.400"/>',
  alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17v.4"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  undo: '<path d="M4 12a8 8 0 1 1 3 6.2M4 5v5h5"/>',
  redo: '<path d="M20 12a8 8 0 1 0-3 6.2M20 5v5h-5"/>',
  record: '<circle cx="12" cy="12" r="5" fill="currentColor" stroke="none"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.4"/>',
  external: '<path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4"/>',
  k_brush: '<path d="M20 4c-5.200.8-9.200 4.800-10.600 9.300l1.300 1.300C15.200 13.200 19.200 9.200 20 4z"/><path d="M9.300 13.600C6.800 13.100 4.800 14.800 4.800 17.200c0 1.500-.6 2.500-1.600 3 3.200.6 7.200-.6 7.200-4"/>',
  k_press: '<path d="M7 4.500l10.500 7.200-4.800 1.100 2.600 5.200-2.100 1-2.600-5.200L7 16.500z"/>',
  k_set: '<path d="M4 12h6M16 12h4"/><circle cx="13" cy="12" r="3"/>',
  k_toggle: '<rect x="3" y="7.500" width="18" height="9" rx="4.500"/><circle cx="16.500" cy="12" r="2.300" fill="currentColor" stroke="none"/>',
  k_steps: '<path d="M12 4l8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4M4 16l8 4 8-4"/>',
  k_menu: '<circle cx="12" cy="12" r="8.500"/><path d="M10 8.500l5 3.500-5 3.500z" fill="currentColor"/>',
  k_auto: '<path d="M19.500 12a7.500 7.500 0 0 1-13 5.100M4.500 12a7.500 7.500 0 0 1 13-5.100"/><path d="M17.500 3.500v3.400h-3.400M6.500 20.500v-3.400h3.400"/>',
  k_alpha: '<circle cx="12" cy="12" r="8.500"/><circle cx="12" cy="12" r="3.200" fill="currentColor" stroke="none" opacity=".5"/>',
  k_material: '<circle cx="12" cy="12" r="8"/><path d="M7.500 15.500a6 6 0 0 0 9-6.500"/><circle cx="9.300" cy="9.300" r="1.300" fill="currentColor" stroke="none"/>',
  k_texture: '<rect x="4.500" y="4.500" width="15" height="15" rx="1.300"/><path d="M12 4.500v15M4.500 12h15"/><path d="M4.500 4.500h7.500v7.500H4.500zM12 12h7.500v7.500H12z" fill="currentColor" stroke="none" opacity=".45"/>',
  side_l: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M9 4.5v15"/>',
  side_r: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M15 4.5v15"/>',
  swap_h: '<path d="M4 9h15M15 5l4 4-4 4M20 15H5M9 11l-4 4 4 4"/>',
  k_browser: '<rect x="4.500" y="4.500" width="6" height="6" rx="1.300"/><rect x="13.500" y="4.500" width="6" height="6" rx="1.300"/><rect x="4.500" y="13.500" width="6" height="6" rx="1.300"/><rect x="13.500" y="13.500" width="6" height="6" rx="1.300"/>',
  tag: '<path d="M20.600 13.400l-7.200 7.200a2 2 0 0 1-2.800 0L3 13V3h10l7.600 7.600a2 2 0 0 1 0 2.800z"/><circle cx="7.500" cy="7.500" r="1.300" fill="currentColor" stroke="none"/>',
  pin: '<path d="M9 4h6l-.8 5.500L17 13H7l2.800-3.500z"/><path d="M12 13v7"/>',
  star: '<path d="M12 2.800l2.900 5.900 6.500.9-4.700 4.600 1.100 6.500L12 17.600l-5.800 3.100 1.100-6.500L2.600 9.600l6.500-.9z"/>',
  clock: '<circle cx="12" cy="12" r="8.500"/><path d="M12 7.500V12l3 2"/>',
  logo: '<circle cx="12" cy="12" r="2.200" fill="currentColor" stroke="none"/><circle cx="12" cy="3.800" r="1.700"/><circle cx="19.100" cy="7.900" r="1.700"/><circle cx="19.100" cy="16.100" r="1.700"/><circle cx="12" cy="20.200" r="1.700"/><circle cx="4.900" cy="16.100" r="1.700"/><circle cx="4.900" cy="7.900" r="1.700"/>',
};
function icon(name, size = 16, cls = '') {
  const s = h('span', { class: 'ico ' + cls, 'aria-hidden': 'true', style: { '--sz': size + 'px' } });
  s.innerHTML = `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ''}</svg>`;
  return s;
}
function iconBtn(name, title, onclick, cls = '') {
  return h('button', { class: 'ibtn ' + cls, type: 'button', title, 'aria-label': title, onclick }, icon(name, 15));
}
function setText(el, t) { if (el.textContent !== t) el.textContent = t; }

/* ================================================================== state */
const ACTIONS = ['brush', 'alpha', 'material', 'texture', 'press', 'set', 'toggle', 'steps', 'menu', 'auto', 'tag', 'browser'];
const KIND = {
  brush: { label: 'Brush', icon: 'k_brush', hint: 'Select a brush' },
  alpha: { label: 'Alpha', icon: 'k_alpha', hint: 'Select an alpha' },
  material: { label: 'Material', icon: 'k_material', hint: 'Select a material' },
  texture: { label: 'Texture', icon: 'k_texture', hint: 'Select a texture' },
  press: { label: 'Press', icon: 'k_press', hint: 'Press any ZBrush button' },
  set: { label: 'Set', icon: 'k_set', hint: 'Set a slider or value' },
  toggle: { label: 'Toggle', icon: 'k_toggle', hint: 'Flip a switch' },
  steps: { label: 'Steps', icon: 'k_steps', hint: 'Run several actions in order' },
  menu: { label: 'Submenu', icon: 'k_menu', hint: 'Open another ring' },
  auto: { label: 'Auto', icon: 'k_auto', hint: 'A slot filled with a brush you pick often' },
  tag: { label: 'Tag', icon: 'tag', hint: 'Every item with a tag: brushes first, most used first, then alphas, materials and textures' },
  browser: { label: 'Browser', icon: 'k_browser', hint: 'Open the browser' },
};
/* The kinds of asset the library holds (brushes, alphas, materials, textures) and their wording; every "brush/brushes" string reads from here. */
const KINDS = {
  brush:    { one: 'brush',    many: 'brushes',   tab: 'Brushes',   ext: '.zbp', eg: 'ClayBuildup' },
  alpha:    { one: 'alpha',    many: 'alphas',    tab: 'Alphas',    ext: '.psd', eg: 'Alpha 058' },
  material: { one: 'material', many: 'materials', tab: 'Materials', ext: '.zmt', eg: 'SkinShade4' },
  texture:  { one: 'texture',  many: 'textures',  tab: 'Textures',  ext: '.psd', eg: 'Txtr01' },
};
const LIB_KINDS = Object.keys(KINDS);
const isLib = k => typeof k === 'string' && Object.prototype.hasOwnProperty.call(KINDS, k);
const K = k => (isLib(k) ? KINDS[k] : KINDS.brush);
const aOrAn = w => (/^[aeiou]/i.test(w) ? 'an ' : 'a ') + w;
const emptyLib = () => ({ items: [], sorted: [], byName: new Map(), state: 'idle', loaded: false, busy: false, sources: [], zbrushFound: true, error: null, _tree: null, _tc: null });
const ANIM_INFO = {
  smooth: 'Slots scale in together with a slight overshoot.',
  bounce: 'Bigger, springier overshoot.',
  pop: 'Quick and crisp, no overshoot.',
  zoom: 'Slots settle down from slightly larger.',
  fade: 'A soft fade-in with no movement.',
  drift: 'Slots rise gently into place.',
  fancy: 'Slots fly out from the centre dot.',
  spiral: 'Slots spin out from the centre, one after another.',
  ripple: 'Out from the centre, with expanding rings.',
  breath: 'A soft halo grows as the slots ease out.',
  mist: 'Slots sharpen in from outside.',
  snappy: 'No animation at all. Instant.',
};
const COLOR_INFO = {
  bg: ['Background', 'Slot fill'],
  accent: ['Accent', 'Centre dot, hover and labels'],
  highlight: ['Highlight', 'Submenus'],
  text: ['Text', 'Labels'],
  lines: ['Lines', 'Spokes and guides'],
};
const BRIDGE_INFO = {
  auto: ['Auto', 'Recommended. Uses the listener inside ZBrush when it is alive and falls back to the bridge key otherwise (or if a message is not picked up within half a second).'],
  message: ['Message', 'Posts a message to a small listener window inside ZBrush. No keystroke is sent, so nothing can collide with your own shortcuts. Needs the ZOrbit plugin loaded in ZBrush.'],
  key: ['Key', 'Presses the bridge key. Bind that key in ZBrush to Zplugin > ZOrbit > Apply (Ctrl+Alt+click the button, press the key, then Preferences > Hotkeys > Store).'],
};
const FALLBACK_DEFAULTS = { radius: 145, slot: 72, dead_zone: 38, tap_ms: 250, timeout_s: 20, animation: 'smooth', labels: 'name', tag_colors: 'tint', flick: true, hover_submenus: true,
  tag_band: 'medium', tag_band_opacity: 0.45, tag_glow_opacity: 0.4, tag_tint_opacity: 0.3, tag_tint_style: 'gradient', tag_tint_blend: 'multiply',
  colors: { bg: '#222327', accent: '#f86b33', highlight: '#4dc8e9', text: '#f0f0f0', lines: '#f86b33' } };
const FALLBACK_RANGES = { radius: [60, 400], slot: [32, 160], dead_zone: [10, 120], tap_ms: [0, 1000], timeout_s: [2, 120],
  tag_band_opacity: [0, 1], tag_glow_opacity: [0, 1], tag_tint_opacity: [0, 1] };

const params = new URLSearchParams(location.search);
const POPOUT = window.__ZORBIT_MODE__ === 'popout';       // the browser popout (popout.html), not the Studio
const S = {
  cfg: null, savedStr: '', path: '', defaults: FALLBACK_DEFAULTS, opts: null,
  problems: [], problemsOpen: false, problemMenus: new Set(), problemItems: new Map(), problemTips: new Map(),
  scroll: {}, shown: false,
  screen: 'menus', menuId: null, itemIdx: null, tab: 'item',
  cameFrom: null,                              // { menuId, itemIdx }: where a submenu was opened from (drives the Back chip)
  suggestions: [],
  version: 0, hist: [], histI: 0,
  tags: [], tagMap: new Map(), itemTags: {}, tagMtime: null, tagsErr: '', tagsLoaded: false, tagsPath: '', palette: null,   // see "tags" below
  lib: { kind: 'brush', cat: 'All', q: '', size: 112 },
  dock: { kind: 'brush', cat: 'All', q: '' },
  pop: { kind: 'brush', cat: 'All', q: '', size: 96 }, popOnTop: true, popSide: 'left', popColumn: true,   // the popout's browser state, whether its window stays above others, and the side of its folders column
  status: null,
  prefs: { show_licence: true, setup_done: true },   // setup_done: boot tests === false, so a failed get_prefs never sends anyone to Setup
  ready: false, fatal: false,                 // ready after the first screen is up; fatal when the recovery screen is showing
  saving: false, savePromise: null, mtimeNs: null,
  dirtySent: undefined, dirtySeq: 0, dirtyFlight: null,
};
const R = {};               // region renderers registered by the visible screen

/* Per-kind library state: S.libs[kind] (see emptyLib). lib(kind) never throws, ensureLib(kind) loads a kind the first time it is shown. */
S.libs = Object.fromEntries(LIB_KINDS.map(k => [k, emptyLib()]));
const lib = kind => S.libs[kind] || S.libs.brush;
const ensureLib = kind => { const L = lib(kind); if (!L.loaded && !L.busy) loadLibrary(kind); };

/* Per-kind usage (get_usage): the picks of the Recent folder, newest first, and the scores that order Favourites. recentSet holds nameKey()s,
   recentT maps a nameKey() to the time of its last pick. Not to be confused with usageMap(), which is where the menus use an item. */
const emptyUsage = () => ({ recent: [], recentSet: new Set(), recentT: new Map(), scores: {}, loaded: false, sig: '', mtime: null });
S.usage = Object.fromEntries(LIB_KINDS.map(k => [k, emptyUsage()]));
const usageOf = kind => S.usage[kind] || S.usage.brush;

const kindOf = it => ACTIONS.find(k => it && k in it) || 'brush';
const targetOf = it => { const k = kindOf(it); return k === 'steps' ? '' : String(it[k] ?? ''); };
const isPath = s => /[\\/]/.test(s) || /\.(png|zbp|zmt|psd|jpg|jpeg|bmp|tif|tiff)$/i.test(s);
const ring = () => S.cfg.ring || {};
const ringNum = k => { const v = ring()[k]; return typeof v === 'number' ? v : S.defaults[k]; };
const ranges = () => (S.opts && S.opts.ring_ranges) || FALLBACK_RANGES;
const menus = () => S.cfg.menus;
const curMenu = () => S.cfg.menus[S.menuId];
const curItem = () => { const m = curMenu(); return m && S.itemIdx !== null ? m.items[S.itemIdx] : undefined; };

function defaultLabel(it) {
  const k = kindOf(it);
  if (isLib(k)) return String(it[k] || '');
  if (k === 'menu') { const m = S.cfg.menus[it.menu]; return (m && m.title) || String(it.menu || ''); }
  if (k === 'steps') return 'Steps';
  if (k === 'auto') return 'Auto';
  if (k === 'tag') return tagName(it.tag);
  if (k === 'browser') return it.browser && S.tagMap.has(it.browser) ? tagName(it.browser) : 'Browser';   // as _default_label in config.py
  return String(it[k] || '').split(':').pop();
}
/* A tag's label, or its key when the tag is not (or not yet) known. */
function tagName(key) { const t = S.tagMap.get(key); return (t && t.label) || String(key || ''); }
const itemLabel = it => String(it.label || defaultLabel(it) || '(empty)');

function actionValid(a, nested) {
  if (!a || typeof a !== 'object') return false;
  const kinds = ACTIONS.filter(k => k in a);
  if (kinds.length !== 1) return false;
  const k = kinds[0];
  if (k === 'set' && !(typeof a.value === 'number' && Number.isFinite(a.value))) return false;   // a number, as config.py demands
  if (k === 'steps') {
    if (nested || !Array.isArray(a.steps) || !a.steps.length) return false;
    return a.steps.every(s => actionValid(s, true) && !('menu' in s) && !('steps' in s) && !('auto' in s) && !('tag' in s) && !('browser' in s));   // steps cannot open menus, nest steps, be auto slots or open tags or the browser
  }
  if (k === 'auto') return a.auto === 'brush';
  if (k === 'browser') return typeof a.browser === 'string' && (a.kind === undefined || isLib(a.kind));          // '' = every item; kind: which tab it opens on
  return typeof a[k] === 'string' && a[k].trim() !== '';
}
/* A tag slot whose tag does not exist stays usable: the loader keeps it as an empty slot and the Problems panel warns. */
const itemUsable = it => actionValid(it, false) && (!('menu' in it) || !!S.cfg.menus[it.menu]);
function usableIdx(menuId) {
  const m = S.cfg.menus[menuId];
  const out = [];
  if (m && Array.isArray(m.items)) m.items.forEach((it, i) => { if (itemUsable(it)) out.push(i); });
  return out;
}

/* Builds an item with a tidy key order (action, value, label, icon). */
function makeItem(kind, target, extra = {}) {
  const it = {};
  if (kind === 'steps') it.steps = extra.steps || [];
  else if (kind === 'auto') it.auto = 'brush';
  else it[kind] = target || '';
  if (kind === 'browser' && isLib(extra.kind) && extra.kind !== 'brush') it.kind = extra.kind;
  if (kind === 'set') it.value = extra.value !== undefined ? extra.value : '';
  if (extra.label) it.label = extra.label;
  if (extra.icon) it.icon = extra.icon;
  return it;
}
/* A target lives in one of these namespaces: each library kind's names, ZBrush item paths (press, set, toggle), menu ids and tags.
   Switching kind keeps a target only inside its own namespace, so a brush name never lands in a path field. */
const nsOf = k => (isLib(k) ? k : k === 'menu' ? 'menu' : k === 'tag' || k === 'browser' ? 'tag' : 'path');
const TARGET_NOUN = { brush: 'brush', alpha: 'alpha', material: 'material', texture: 'texture', press: 'button path', set: 'value path', toggle: 'switch path', menu: 'submenu', tag: 'tag', browser: 'tag filter' };
/* Brush names are compared ignoring case and spaces (the guide says neither matters). */
const nameKey = s => String(s === undefined || s === null ? '' : s).toLowerCase().replace(/\s+/g, '');
/* An asset's key in tags.json: its kind, a colon and its name in lower case without spaces (tags.item_key in Python). */
const tagKey = (kind, s) => kind + ':' + nameKey(s);
/* The built-in Favourites tag (always the first tag, cannot be renamed, merged or deleted). It is not a colour cue: see firstTag. */
const FAV = 'favourite';
const libOpts = kind => lib(kind).sorted.map(b => ({ value: b.name, sub: b.category }));
const hasText = v => String(v === undefined || v === null ? '' : v).trim() !== '';
const joinList = a => (a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' and ' + a[a.length - 1]);
/* Kinds that cannot be a step (and so are dropped when an item becomes Steps). */
const NO_STEP = ['menu', 'tag', 'browser'];
/* Returns { item, lost }: lost lists, in words, what the switch could not carry over (empty when nothing was lost). */
function convertItem(it, kind) {
  const old = kindOf(it);
  if (old === kind) return { item: it, lost: [] };
  const label = it.label, icon = it.icon, lost = [];
  const oldSteps = old === 'steps' && Array.isArray(it.steps) ? it.steps : [];
  const oldTarget = targetOf(it);
  let target = '', value, steps, carriedStep = false;
  if (kind === 'auto') {
    if (hasText(oldTarget)) lost.push(`the ${TARGET_NOUN[old]} "${oldTarget.trim()}"`);
    if (old === 'set' && hasText(it.value)) lost.push(`the value ${it.value}`);
  } else if (old === 'steps') {
    const first = oldSteps[0];
    if (first && nsOf(kindOf(first)) === nsOf(kind)) {
      target = targetOf(first); value = first.value; carriedStep = true;
      if (kind !== 'set' && kindOf(first) === 'set' && hasText(first.value)) lost.push(`the value ${first.value}`);
    }
  } else if (old !== 'auto') {
    if (kind === 'steps') {
      if (!NO_STEP.includes(old) && (hasText(oldTarget) || (old === 'set' && hasText(it.value)))) steps = [makeItem(old, oldTarget, { value: it.value })];
      else steps = [];
    } else target = nsOf(old) === nsOf(kind) ? oldTarget : '';
  }
  if (kind !== 'auto' && kind !== 'steps' && old !== 'auto' && old !== 'steps' && hasText(oldTarget) && !hasText(target)) lost.push(`the ${TARGET_NOUN[old]} "${oldTarget.trim()}"`);
  if (kind === 'steps' && NO_STEP.includes(old) && hasText(oldTarget)) lost.push(`the ${TARGET_NOUN[old]} "${oldTarget.trim()}"`);
  if (kind !== 'set' && kind !== 'steps' && kind !== 'auto' && old === 'set' && hasText(it.value)) lost.push(`the value ${it.value}`);
  if (old === 'steps' && kind !== 'steps') {
    const n = oldSteps.length - (carriedStep ? 1 : 0);
    if (n > 0) lost.push((carriedStep ? n + ' other step' : n + ' step') + (n === 1 ? '' : 's'));
  }
  if (kind === 'auto') {
    if (hasText(label)) lost.push(`the label "${String(label).trim()}"`);
    if (hasText(icon)) lost.push(`the icon "${String(icon).trim()}"`);
  }
  const item = kind === 'auto' ? makeItem('auto', '') : makeItem(kind, target, { value, steps, label, icon });
  return { item, lost };
}

function usageMap() {
  if (S._usage && S._usageV === S.version) return S._usage;
  const m = new Map();
  for (const [id, menu] of Object.entries(S.cfg.menus)) {
    (menu.items || []).forEach((it, i) => {
      const keys = [];
      const add = a => { for (const kd of LIB_KINDS) if (a && a[kd]) keys.push(tagKey(kd, a[kd])); };
      add(it);
      if (it && Array.isArray(it.steps)) it.steps.forEach(add);
      for (const k of keys) {
        if (!m.has(k)) m.set(k, []);
        m.get(k).push({ menuId: id, index: i });
      }
    });
  }
  S._usage = m; S._usageV = S.version;
  return m;
}

function hkNorm(s) {
  if (!s) return '';
  const parts = String(s).split(/\+(?=.)/).map(p => p.trim().toLowerCase());
  const key = parts.pop();
  const mods = parts.map(p => (p === 'control' ? 'ctrl' : p)).sort();
  return [...mods, key].join('+');
}
/* Who else uses a hotkey: a menu id, BROWSER for browser.hotkey, or null. exceptId is the menu (or BROWSER) being edited. */
const BROWSER = ':browser';                     // not a valid menu id (':' is rejected), so it never collides with one
function hotkeyOwner(str, exceptId) {
  const n = hkNorm(str);
  if (!n) return null;
  for (const [id, m] of Object.entries(S.cfg.menus)) if (id !== exceptId && hkNorm(m.hotkey) === n) return id;
  const b = S.cfg.browser;
  if (exceptId !== BROWSER && b && typeof b === 'object' && hkNorm(b.hotkey) === n) return BROWSER;
  return null;
}
const ownerName = id => (id === BROWSER ? 'the browser' : '“' + (S.cfg.menus[id].title || id) + '”');
function hkChips(str, cls = '') {
  const w = h('span', { class: 'hk ' + cls });
  String(str).split(/\+(?=.)/).forEach(p => w.append(h('kbd', null, p)));
  return w;
}
function uniqueId(base) {
  let id = (base || 'menu').toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || 'menu';
  if (/^\d+$/.test(id)) id = 'm_' + id;
  let n = 2, out = id;
  while (S.cfg.menus[out]) out = id + '_' + n++;
  return out;
}
function referrers(menuId) {
  const out = [];
  for (const [id, m] of Object.entries(S.cfg.menus)) (m.items || []).forEach((it, i) => { if (it && it.menu === menuId) out.push({ menuId: id, index: i, item: it }); });
  return out;
}

/* ================================================================== backend wrapper */
async function call(name, ...args) {
  const p = window.pywebview && window.pywebview.api;
  if (!p || typeof p[name] !== 'function') throw new Error('Backend method not available: ' + name);
  try { return await p[name](...args); }
  catch (e) { console.error('api.' + name, e); throw e; }
}

/* ================================================================== toasts, modal, popover */
/* Tones: 'ok' (check), 'warn' (amber), 'err' (red, stays until closed). The timer pauses while the pointer is over a toast or focus
   is inside it, and a toast with the same text as one on screen replaces it instead of stacking. */
function toast(msg, o = {}) {
  const root = $('#toasts');
  const text = String(msg), tone = o.tone || '', err = tone === 'err';
  let t = $$('.toast', root).find(x => x._msg === text && !x._dying);
  const fresh = !t;
  if (fresh) {
    t = h('div', { class: 'toast' });
    Object.assign(t, { _msg: text, _hold: new Set(), _dying: false, _left: 0, _started: 0, _timer: 0, _err: false, _back: null });
    t._kill = () => {
      if (t._dying) return;
      t._dying = true; clearTimeout(t._timer); t.classList.remove('in');
      if (t.contains(document.activeElement) && t._back && document.contains(t._back)) t._back.focus();
      setTimeout(() => t.remove(), 220);
    };
    t._arm = () => { clearTimeout(t._timer); if (t._err || t._dying || t._hold.size) return; t._started = Date.now(); t._timer = setTimeout(t._kill, t._left); };
    const hold = (who, on) => {
      if (on) { if (!t._hold.size && t._started) t._left = Math.max(1200, t._left - (Date.now() - t._started)); t._hold.add(who); clearTimeout(t._timer); }
      else { t._hold.delete(who); t._arm(); }
    };
    t.addEventListener('pointerenter', () => hold('ptr', true));
    t.addEventListener('pointerleave', () => hold('ptr', false));
    t.addEventListener('focusin', e => { if (e.relatedTarget && !t.contains(e.relatedTarget)) t._back = e.relatedTarget; hold('focus', true); });
    t.addEventListener('focusout', e => { if (!t.contains(e.relatedTarget)) hold('focus', false); });
  }
  clearTimeout(t._timer);
  t._err = err;
  t.className = 'toast' + (tone ? ' ' + tone : '') + (!fresh && t.classList.contains('in') ? ' in' : '');
  if (err) t.setAttribute('role', 'alert'); else t.removeAttribute('role');     // #toasts is the polite live region; only errors announce themselves
  const ico = tone === 'ok' ? 'check' : (tone === 'warn' || err) ? 'alert' : null;
  t.replaceChildren(...[ico ? h('span', { class: 'toast-ico' }, icon(ico, 15)) : null, h('span', { class: 'toast-msg' }, text),
    o.action ? h('button', { class: 'toast-act', type: 'button', onclick: () => { o.action.fn(); t._kill(); } }, o.action.text) : null,
    h('button', { class: 'ibtn toast-x', type: 'button', title: 'Dismiss', 'aria-label': 'Dismiss: ' + text, onclick: () => t._kill() }, icon('x', 12))].filter(Boolean));
  if (!fresh && !t.contains(document.activeElement)) t._hold.delete('focus');   // the focused child was just replaced: no focusout will come
  if (fresh) {
    root.append(t);
    requestAnimationFrame(() => t.classList.add('in'));
    while (root.children.length > 4) root.firstChild.remove();
  }
  t._left = o.ms || (o.action ? 5200 : 3200); t._started = 0;
  t._arm();
}

let activeModal = null;                                       // { close }: at most one dialog at a time
function modal({ title, body, actions }) {
  if (typeof openPopover === 'function') openPopover();      // a dialog always closes any open dropdown first
  if (activeModal) activeModal.close(undefined);             // a newer dialog replaces the open one (e.g. the window X over a Revert confirm)
  return new Promise(resolve => {
    const prev = document.activeElement;
    const me = { close: v => close(v) };
    let closed = false;
    const box = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
      h('h2', null, title), h('div', { class: 'modal-body' }, body),
      h('div', { class: 'modal-actions' }, actions.map(a => h('button', { class: 'btn ' + (a.kind || ''), type: 'button', dataset: { v: a.value }, 'data-focus': a.focus, onclick: () => close(a.value) }, a.text))));
    const scrim = h('div', { class: 'scrim', onmousedown: e => { if (e.target === scrim) close(undefined); } }, box);
    function close(v) {
      if (closed) return;
      closed = true;
      document.removeEventListener('keydown', onKey, true);
      scrim.classList.remove('in');
      setTimeout(() => scrim.remove(), 160);
      if (activeModal === me) { activeModal = null; const app = $('#app'); if (app) app.inert = false; }
      if (prev && prev.focus && document.contains(prev)) prev.focus();
      resolve(v);
    }
    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(undefined); }
      else if (e.key === 'Tab') {
        const f = $$('button, input, select, textarea, a[href], [tabindex="0"]', box).filter(x => !x.disabled);
        if (!f.length) return;
        const first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
    }
    document.addEventListener('keydown', onKey, true);
    activeModal = me;
    const appEl = $('#app'); if (appEl) appEl.inert = true;    // Tab and screen readers cannot reach the page behind
    $('#overlay-root').append(scrim);
    requestAnimationFrame(() => scrim.classList.add('in'));
    const primary = $('.btn[data-focus]', box) || $('.btn.primary', box) || $('.btn:last-child', box);
    if (primary) primary.focus();
  });
}

let openPopover = null;
function popover(anchor, entries) {
  if (openPopover) { const same = openPopover.anchor === anchor; openPopover(); if (same) return; }   // a second click on the anchor closes it
  const pop = h('div', { class: 'popover', role: 'menu' }, entries.map(en => h('button', { class: 'pop-item', role: 'menuitem', type: 'button', onclick: () => { close(); en.fn(); } },
    en.icon ? icon(en.icon, 16) : null, h('span', { class: 'pop-text' }, h('b', null, en.label), en.hint ? h('small', null, en.hint) : null))));
  document.body.append(pop);
  const r = anchor.getBoundingClientRect();
  pop.style.left = Math.min(r.left, innerWidth - pop.offsetWidth - 8) + 'px';
  const below = r.bottom + 6 + pop.offsetHeight < innerHeight;
  pop.style.top = (below ? r.bottom + 6 : r.top - pop.offsetHeight - 6) + 'px';
  requestAnimationFrame(() => pop.classList.add('in'));
  const onDown = e => { if (!pop.contains(e.target) && !anchor.contains(e.target)) close(); };
  const onKey = e => {
    const items = $$('.pop-item', pop), i = items.indexOf(document.activeElement);
    if (e.key === 'Escape') { e.preventDefault(); close(); }
    else if (e.key === 'Home') { e.preventDefault(); items[0].focus(); }
    else if (e.key === 'End') { e.preventDefault(); items[items.length - 1].focus(); }
    else if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
  };
  function close() {
    const had = pop.contains(document.activeElement);            // focus goes back to the anchor, not to the page
    pop.remove(); document.removeEventListener('mousedown', onDown, true); document.removeEventListener('keydown', onKey, true); openPopover = null;
    if (had && document.contains(anchor)) anchor.focus();
  }
  close.anchor = anchor;
  document.addEventListener('mousedown', onDown, true);
  document.addEventListener('keydown', onKey, true);
  openPopover = close;
  $('.pop-item', pop).focus();
}

/* ================================================================== thumbnails */
const Thumbs = {
  cache: new Map(), waiting: new Map(), queue: new Map(), timer: null, busy: false,
  key: (name, res, kind) => kind + '|' + res + '|' + name,       // a thumbnail is cached per kind and size
  request(name, res, kind, cb, el) {
    const k = this.key(name, res, kind);
    if (this.cache.has(k)) { cb(this.cache.get(k)); return; }
    if (!this.waiting.has(k)) this.waiting.set(k, []);
    this.waiting.get(k).push({ cb, el });
    this.queue.set(k, { name, res, kind });
    if (!this.timer) this.timer = setTimeout(() => this.flush(), 30);
  },
  forgetMisses(kind) { for (const [k, v] of Array.from(this.cache)) if (!v && (!kind || k.startsWith(kind + '|'))) this.cache.delete(k); },
  async flush() {
    this.timer = null;
    if (this.busy) { this.timer = setTimeout(() => this.flush(), 10); return; }   // one call in flight at a time: the slider cannot stack them
    const batch = [];
    let res = 0, kind = '';
    for (const [k, q] of this.queue) {                            // FIFO, up to 40 names of one size and kind per call
      if (batch.length >= 40) break;
      if (res && (q.res !== res || q.kind !== kind)) continue;
      this.queue.delete(k);
      const all = this.waiting.get(k) || [];
      const live = all.filter(w => !w.el || w.el.isConnected);
      all.filter(w => !live.includes(w)).forEach(w => w.cb(null, true));   // its card is gone: let it ask again if it comes back
      if (!live.length) { this.waiting.delete(k); continue; }
      this.waiting.set(k, live);
      res = q.res; kind = q.kind; batch.push({ k, name: q.name });
    }
    if (this.queue.size) this.timer = setTimeout(() => this.flush(), 10);
    if (!batch.length) return;
    let out = null;
    this.busy = true;
    try { out = (await call('get_thumbs', batch.map(b => b.name), res, kind)) || {}; } catch (e) { out = null; }
    this.busy = false;
    for (const { k, name } of batch) {
      const ws = this.waiting.get(k) || [];
      this.waiting.delete(k);
      if (out) { const url = out[name] || null; this.cache.set(k, url); ws.forEach(w => w.cb(url)); }
      else ws.forEach(w => w.cb(null, true));                    // the call failed: cache nothing, so a later request tries again
    }
  },
};
/* One observer per scroller, so the 320px pre-load margin is measured from the scroller's own edges. */
function makeLazyIO(root) {
  const io = new IntersectionObserver(entries => {
    for (const e of entries) if (e.isIntersecting) { io.unobserve(e.target); if (e.target._load) e.target._load(); }
  }, { root, rootMargin: '320px' });
  return io;
}

function initials(name) {
  const parts = String(name || '?').replace(/([a-z])([A-Z])/g, '$1 $2').split(/[\s_\-.]+/).filter(Boolean);
  const a = (parts[0] || '?')[0] || '?';
  const b = parts.length > 1 ? parts[1][0] : ((parts[0] || '')[1] || '');
  return (a + b).toUpperCase();
}
/* Round/square brush thumbnail with shimmer placeholder and an initials fallback. `lazy` is an observer from makeLazyIO:
   the thumbnail is fetched when it nears the scroller's view. `res` is the pixel size asked of the backend (128 or 256). */
function thumb(name, { size = 28, lazy = null, cls = '', res = 128, kind = 'brush' } = {}) {
  const el = h('span', { class: 'thumb ' + cls, style: { '--sz': size + 'px' } });
  el._res = res; el._kind = kind;
  const done = (url, failed) => {
    el.classList.remove('loading');
    if (url) { el.classList.remove('fallback'); el.replaceChildren(h('img', { src: url, alt: '', draggable: 'false' })); }
    else if (!el.querySelector('img')) { el.classList.add('fallback'); el.textContent = initials(name); }
    if (failed && el._io) setTimeout(() => {                       // look again in a while, or when it scrolls back into view
      const root = el._io.root;
      if (root ? root.contains(el) : el.isConnected) el._io.observe(el);
    }, 3000);
  };
  if (!name) { done(null); return el; }
  const load = () => { const r = el._res; Thumbs.request(name, r, el._kind, (url, failed) => { if (r === el._res) done(url, failed); }, el); };
  if (lazy) { el._io = lazy; el._load = load; }                    // kept even when the picture is already cached, so a size change can refetch it
  const k = Thumbs.key(name, res, kind);
  if (Thumbs.cache.has(k)) { done(Thumbs.cache.get(k)); return el; }
  el.classList.add('loading');
  if (lazy) lazy.observe(el); else load();
  return el;
}
/* Asks a lazy thumbnail for another size: it keeps its picture until the new one arrives, and only fetches when in view. */
function rethumb(el, res) {
  if (el._res === res || !el._io) return;
  el._res = res;
  el._io.unobserve(el); el._io.observe(el);
}
function itemThumb(it, size = 30) {
  const k = kindOf(it);
  let name = null, kind = 'brush';                                 // an icon override is always a brush name
  if (it.icon && !isPath(it.icon)) name = it.icon;
  else if (!it.icon && isLib(k)) { name = it[k]; kind = k; }
  else if (!it.icon && k === 'steps') for (const s of it.steps || []) { const sk = s && LIB_KINDS.find(x => s[x]); if (sk) { name = s[sk]; kind = sk; break; } }
  if (name) return thumb(name, { size, kind });
  const g = h('span', { class: 'thumb glyph k-' + k, style: { '--sz': size + 'px' } }, icon(KIND[k].icon, Math.round(size * 0.52)));
  return g;
}

/* ================================================================== ring preview + animation loaders */
const SAMPLE_MENU = 'sample:tags';             // not a menu: the backend's sample ring of library brushes in the user's tag colours
const RingLoader = {
  cache: new Map(), ver: -1, gen: 0, queue: {}, cur: null, busy: false,   // gen: bumped by tag edits, which S.version does not see; queue: lane -> waiting request
  key: (m, hv, path) => m + '|' + (hv === null || hv === undefined ? 'n' : hv) + '|' + (path && path.length ? path.join('.') : ''),
  sync() { if (this.ver !== S.version) { this.cache.clear(); this.ver = S.version; } },
  peek(menuId, hover, path) { this.sync(); return this.cache.get(this.key(menuId, hover, path)) || null; },
  get(menuId, hover, path, lane = 'main') {      // path: item indices of the fan submenus to show open (null: none)
    this.sync();
    const k = this.key(menuId, hover, path), c = this.cache.get(k);
    if (c) return Promise.resolve(c);
    return new Promise(res => {
      // the same picture asked for twice (several previews on one screen) shares one backend call
      const same = [this.cur, ...Object.values(this.queue)].find(q => q && q.k === k && q.ver === S.version && q.gen === this.gen);
      if (same) { same.waiters.push(res); return; }
      if (this.queue[lane]) this.settle(this.queue[lane], null);   // latest request wins within a lane; other lanes keep theirs
      this.queue[lane] = { menuId, hover: hover === undefined ? null : hover, path: path && path.length ? path : null, k, ver: S.version, gen: this.gen, res, waiters: [] };
      this.pump();
    });
  },
  settle(q, out) { q.res(out); for (const w of q.waiters) w(out); },
  async pump() {
    const lane = Object.keys(this.queue)[0];                  // oldest lane first, so lanes take turns
    if (this.busy || !lane) return;
    this.busy = true;
    const q = this.queue[lane]; delete this.queue[lane]; this.cur = q;
    let out;
    try {
      out = q.menuId === SAMPLE_MENU ? await call('preview_tags', S.cfg, q.hover, 1.0) : await call('preview_ring', S.cfg, q.menuId, q.hover, 1.0, q.path);
      if (out && out.image && q.ver === this.ver && q.gen === this.gen) {
        this.cache.set(q.k, out);
        if (this.cache.size > 60) this.cache.delete(this.cache.keys().next().value);
      }
    } catch (e) { out = { image: null, problems: [String(e && e.message || e)], error: true }; }
    this.busy = false; this.cur = null;
    this.settle(q, out);
    this.pump();
  },
};
const FrameLoader = {
  cache: new Map(), ver: -1, gen: 0,
  async get(menuId, ringAnim = false) {          // ringAnim: ring.animation even if the menu has its own
    if (this.ver !== S.version) { this.cache.clear(); this.ver = S.version; }
    const k = menuId + (ringAnim ? '|ring' : '');
    if (this.cache.has(k)) return this.cache.get(k);
    const ver = S.version, gen = this.gen;
    const res = await call('preview_animation', S.cfg, menuId, 30, ringAnim);
    if (res && res.frames && res.frames.length && ver === S.version && gen === this.gen) this.cache.set(k, res);
    return res;
  },
};
/* Plays animation frames into an <img>. restore() puts the static image back. */
function makePlayer(getImg, restore, onState) {
  const p = { state: 'idle', timer: null, token: 0 };
  const set = s => { p.state = s; onState && onState(s); };
  p.stop = () => { clearTimeout(p.timer); p.token++; if (p.state !== 'idle') { set('idle'); restore(); } };
  p.play = async (menuId, ringAnim = false) => {
    if (p.state === 'playing') { p.stop(); return; }
    if (p.state === 'loading') return;
    const tok = ++p.token;
    set('loading');
    let res = null;
    try { res = await FrameLoader.get(menuId, ringAnim); } catch (e) { /* toast below */ }
    if (tok !== p.token) return;
    if (!res || !res.frames || !res.frames.length) {
      set('idle'); toast((res && res.problems && res.problems[0]) || 'Could not render the animation.', { tone: 'warn' }); return;
    }
    set('playing');
    let i = 0;
    const tick = () => {
      if (tok !== p.token) return;
      if (i >= res.frames.length) { p.timer = setTimeout(() => { if (tok === p.token) p.stop(); }, 500); return; }
      const img = getImg(); if (img) img.src = res.frames[i++];
      p.timer = setTimeout(tick, res.interval_ms || 33);
    };
    tick();
  };
  return p;
}

/* ================================================================== drag and drop (pointer based) */
const DnD = {
  active: null, recent: false,
  zone(el, handlers) { el.dataset.dz = '1'; el._dz = handlers; },
  source(el, getPayload, ghostFn) {
    el.addEventListener('pointerdown', e => {
      if (e.button !== 0 || e.target.closest('button, input, select, textarea, a, [data-nodrag]')) return;
      const payload = getPayload(e);                         // gets the pointerdown event, so a source can pick by position
      if (!payload) return;
      const sx = e.clientX, sy = e.clientY;
      let started = false;
      const move = ev => {
        if (!started) {
          if (Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) return;
          started = true; DnD.begin(payload, ghostFn ? ghostFn(e) : h('span', null, '...'));
        }
        DnD.move(ev);
      };
      const up = ev => {
        window.removeEventListener('pointermove', move, true);
        window.removeEventListener('pointerup', up, true);
        window.removeEventListener('pointercancel', up, true);
        if (started) DnD.end(ev, ev.type === 'pointerup');
      };
      window.addEventListener('pointermove', move, true);
      window.addEventListener('pointerup', up, true);
      window.addEventListener('pointercancel', up, true);
    });
  },
  begin(payload, ghostEl) {
    const ghost = h('div', { class: 'drag-ghost' }, ghostEl);
    document.body.append(ghost);
    document.body.classList.add('dragging');
    this.active = { payload, ghost, zone: null, onKey: e => { if (e.key === 'Escape') this.end(null, false); } };
    document.addEventListener('keydown', this.active.onKey, true);
    window.dispatchEvent(new Event('zorbit-dnd'));           // lets a view dim what is being dragged
  },
  findZone(x, y, payload) {
    let el = document.elementFromPoint(x, y);
    while (el) {
      const z = el.closest && el.closest('[data-dz]');
      if (!z) return null;
      if (z._dz.accept(payload)) return z;
      el = z.parentElement;
    }
    return null;
  },
  move(ev) {
    const a = this.active; if (!a) return;
    a.ghost.style.transform = `translate(${ev.clientX + 14}px, ${ev.clientY + 14}px)`;
    const z = this.findZone(ev.clientX, ev.clientY, a.payload);
    if (z !== a.zone) { if (a.zone) a.zone._dz.leave && a.zone._dz.leave(); a.zone = z; }
    if (z) z._dz.over(a.payload, ev.clientX, ev.clientY, ev);
    a.ghost.classList.toggle('ok', !!z);
  },
  end(ev, drop) {
    const a = this.active; if (!a) return;
    this.active = null;
    document.removeEventListener('keydown', a.onKey, true);
    if (a.zone) a.zone._dz.leave && a.zone._dz.leave();
    if (drop && ev && a.zone) a.zone._dz.drop(a.payload, ev.clientX, ev.clientY, ev);
    a.ghost.remove();
    document.body.classList.remove('dragging');
    window.dispatchEvent(new Event('zorbit-dnd'));
    this.recent = true; setTimeout(() => { this.recent = false; }, 60);
  },
};
window.addEventListener('click', e => { if (DnD.recent) { e.stopPropagation(); e.preventDefault(); } }, true);

/* ---------- drag and drop between windows (HTML5)
   The browser popout is a window of another process, so its drags cannot be pointer events. Its cards are draggable the native way and
   carry the item as ITEM_MIME (JSON {kind, name}) and as "zorbit:<kind>:<name>" in text/plain, for a drag that loses custom types.
   LEGACY_MIME (a bare brush name, from a popout of an older version) is still read. The Studio takes them in here and hands them to the
   same zones the pointer drags use, so an item from the popout lands exactly like one from the Library. While a drag is over the page
   only the types can be read, not the data: so the kind of a drag in flight is unknown until it drops (the zones do not look at it). */
const ITEM_MIME = 'application/x-zorbit-item', LEGACY_MIME = 'application/x-zorbit-brush', ITEM_TEXT = 'zorbit:';
DnD.native = {
  zone: null, idle: 0,
  mine: dt => !!dt && Array.from(dt.types || []).some(t => t === ITEM_MIME || t === LEGACY_MIME),
  item(dt) {                                                 // only at drop time; anything that is not ours gives null, else {kind, name}
    let kind = '', name = '';
    try {
      const j = dt.getData(ITEM_MIME);
      if (j) { try { const o = JSON.parse(j); if (o && typeof o === 'object') { kind = o.kind; name = o.name; } } catch (e) { /* not JSON: try the next form */ } }
      if (!name) { const n = dt.getData(LEGACY_MIME); if (n) { kind = 'brush'; name = n; } }
      if (!name) { const m = /^zorbit:([a-z]+):(.+)$/s.exec(dt.getData('text/plain') || ''); if (m) { kind = m[1]; name = m[2]; } }
    } catch (e) { return null; }
    name = typeof name === 'string' ? name.trim() : '';
    return isLib(kind) && name && name.length <= 260 && !/[\x00-\x1f]/.test(name) ? { kind, name } : null;
  },
  over(x, y, ev) {                                           // true when a zone would take the item
    const p = { type: 'asset', kind: null, name: '' };
    const z = DnD.findZone(x, y, p);
    if (z !== this.zone) { this.leave(); this.zone = z; }
    if (z) z._dz.over(p, x, y, ev);
    clearTimeout(this.idle); this.idle = setTimeout(() => this.leave(), 2500);  // a drag that ends away from us sends nothing more (long: a still cursor may get no dragover)
    return !!z;
  },
  leave() {
    clearTimeout(this.idle);
    const z = this.zone; this.zone = null;
    if (z && z._dz.leave) z._dz.leave();
  },
  drop(item, x, y, ev) {
    const p = { type: 'asset', ...item };
    const z = DnD.findZone(x, y, p);
    this.leave();
    if (z && item && item.name) z._dz.drop(p, x, y, ev);
    return !!z;
  },
};
(function bindNativeDrop() {
  const editable = t => !!(t && t.closest && t.closest('input, textarea, [contenteditable]'));
  const files = dt => !!dt && Array.from(dt.types || []).includes('Files');
  const ours = dt => !POPOUT && DnD.native.mine(dt) && S.ready && !S.fatal;
  const onOver = e => {
    const dt = e.dataTransfer;
    if (ours(dt)) {
      const ok = DnD.native.over(e.clientX, e.clientY, e);
      e.preventDefault();
      if (dt) dt.dropEffect = ok ? 'copy' : 'none';
      return;
    }
    if (!files(dt) && editable(e.target)) return;            // text dragged within a text box keeps working
    e.preventDefault();                                      // nothing else is dropped here: no file or link may navigate the page
    if (dt) dt.dropEffect = 'none';
  };
  document.addEventListener('dragenter', onOver, true);
  document.addEventListener('dragover', onOver, true);
  document.addEventListener('dragleave', e => {
    if (!DnD.native.zone || e.relatedTarget) return;
    const x = e.clientX, y = e.clientY;
    if ((x === 0 && y === 0) || x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) DnD.native.leave();   // truly outside: an edge pixel is still ours
  }, true);
  document.addEventListener('drop', e => {
    const dt = e.dataTransfer, item = !POPOUT && S.ready && !S.fatal && dt ? DnD.native.item(dt) : null;   // the plain text form counts too
    if (item || ours(dt)) {
      e.preventDefault();
      if (item) DnD.native.drop(item, e.clientX, e.clientY, e); else DnD.native.leave();
      return;
    }
    DnD.native.leave();
    if (!files(dt) && editable(e.target)) return;
    e.preventDefault();
  }, true);
})();

/* ================================================================== combobox (autocomplete) */
let comboClose = null, comboSeq = 0;
function combo(input, getOpts, o = {}) {
  let list = null, items = [], active = -1, typed = false, picking = false;
  const lid = 'combo-list-' + (++comboSeq), oid = i => lid + '-o' + i;
  input.setAttribute('role', 'combobox');
  input.setAttribute('aria-autocomplete', 'list');
  input.setAttribute('aria-expanded', 'false');
  input.setAttribute('aria-controls', lid);
  const sync = () => {                                        // aria-activedescendant follows the highlighted option
    input.setAttribute('aria-expanded', list ? 'true' : 'false');
    if (list && active >= 0) input.setAttribute('aria-activedescendant', oid(active)); else input.removeAttribute('aria-activedescendant');
  };
  const close = () => {
    if (list) list.remove();
    list = null; active = -1; sync();
    window.removeEventListener('scroll', onScroll, true);
    if (comboClose === close) comboClose = null;
  };
  const onScroll = e => { if (list && !list.contains(e.target)) close(); };
  const position = () => {
    const r = input.getBoundingClientRect();
    list.style.left = r.left + 'px'; list.style.width = Math.max(r.width, 260) + 'px';
    const below = r.bottom + 6 + Math.min(list.scrollHeight, 280) < innerHeight || r.top < 300;
    if (below) { list.style.top = r.bottom + 4 + 'px'; list.style.bottom = ''; }
    else { list.style.bottom = innerHeight - r.top + 4 + 'px'; list.style.top = ''; }
  };
  const setActive = i => {
    active = i;
    $$('.combo-opt', list).forEach((n, j) => { n.classList.toggle('active', j === i); n.setAttribute('aria-selected', j === i ? 'true' : 'false'); });
    const n = $$('.combo-opt', list)[i]; if (n) n.scrollIntoView({ block: 'nearest' });
    sync();
  };
  const render = () => {
    items = getOpts(typed ? input.value.trim().toLowerCase() : '');
    if (!items.length) { close(); return; }
    if (!list) {
      if (comboClose) comboClose();
      list = h('div', { class: 'combo-list', id: lid, role: 'listbox' }); document.body.append(list);
      comboClose = close; window.addEventListener('scroll', onScroll, true);
    }
    if (active >= items.length) active = -1;
    list.replaceChildren(...items.map((it, i) => h('div', { class: 'combo-opt' + (i === active ? ' active' : ''), id: oid(i), role: 'option', 'aria-selected': i === active ? 'true' : 'false',
      onmousedown: e => { e.preventDefault(); pick(i); } },
      o.thumb ? thumb(it.value, { size: 24, kind: o.thumb }) : null,
      h('span', { class: 'combo-main' }, h('b', { class: o.mono ? 'mono' : '' }, it.label || it.value), it.sub ? h('small', null, it.sub) : null))));
    position(); sync();
  };
  const pick = i => {
    const it = items[i]; if (!it) return;
    input.value = it.value; close();
    picking = true;                                           // our own input listener would re-render the list and reopen it
    try {
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    } finally { picking = false; }
    o.onPick && o.onPick(it);
  };
  input.addEventListener('focus', () => { typed = false; render(); });
  input.addEventListener('input', () => { if (picking) return; typed = true; active = -1; render(); });
  input.addEventListener('blur', () => close());
  input.addEventListener('keydown', e => {
    if (!list) { if (e.key === 'ArrowDown') { typed = typed || false; render(); } return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setActive((active + 1) % items.length); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive((active - 1 + items.length) % items.length); }
    else if (e.key === 'Enter') { if (active >= 0) { e.preventDefault(); pick(active); } else close(); }
    else if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(); }
    else if (e.key === 'Tab' && active >= 0) pick(active);      // Tab takes the highlighted option and moves on
  });
}
function matchOpts(all, q, cap = 60) {
  if (!q) return all.slice(0, cap);
  const terms = q.split(/\s+/);
  const starts = [], rest = [];
  for (const o of all) {
    const hay = o._hay || (o._hay = ((o.label || '') + ' ' + o.value).toLowerCase());   // sub (category, source) is shown, not matched
    if (!terms.every(t => hay.includes(t))) continue;
    (o.value.toLowerCase().startsWith(terms[0]) ? starts : rest).push(o);
    if (starts.length + rest.length > 400) break;
  }
  return starts.concat(rest).slice(0, cap);
}
const pathOpts = () => S.suggestions.map(s => ({ value: s.path, sub: s.source }));
const menuOpts = () => Object.entries(S.cfg.menus).map(([id, m]) => ({ value: id, label: id, sub: m.title }));

/* ================================================================== hotkey recorder */
const CODE_KEYS = { Backquote: '`', Minus: '-', Equal: '=', BracketLeft: '[', BracketRight: ']', Backslash: '\\',
  Semicolon: ';', Quote: "'", Comma: ',', Period: '.', Slash: '/' };
function keyFromEvent(e) {
  if (e.key === 'Dead' || e.key === 'Process' || e.key === 'Unidentified') return null;   // dead keys and IME composition
  const c = e.code;
  if (/^[a-z]$/i.test(e.key)) return e.key.toUpperCase();     // the typed character, so Dvorak/AZERTY record what the user pressed
  if (/^[0-9]$/.test(e.key)) return e.key;
  if (/^Key[A-Z]$/.test(c)) return c[3];                      // other layouts (Cyrillic, Greek...): fall back to the physical key
  if (/^Digit[0-9]$/.test(c)) return c[5];
  if (/^F([1-9]|1\d|2[0-4])$/.test(c)) return c;
  return CODE_KEYS[c] || null;
}
function hotkeyField({ value, mods = { ctrl: true, alt: true, shift: true }, onChange, placeholder = 'Not set', noMessage, what = 'Hotkey' }) {
  let rec = false;
  const field = h('div', { class: 'hk-field', role: 'button', tabindex: '0', title: 'Press Enter to record a new one' });
  const msg = h('div', { class: 'hk-msg', 'aria-live': 'polite' });
  const recBtn = h('button', { class: 'btn small', type: 'button' }, 'Record');
  const clearBtn = h('button', { class: 'btn small danger-o', type: 'button' }, 'Clear');
  const paint = (live) => {
    field.classList.toggle('rec', rec);
    field.setAttribute('aria-label', rec ? what + ', listening for a key combination. Escape cancels.' : what + (value ? ', currently ' + value : ', not set'));
    recBtn.textContent = rec ? 'Listening...' : 'Record';
    field.replaceChildren();
    if (rec) field.append(h('span', { class: 'hk-listen' }, live || 'Press a key combination'));
    else if (value) field.append(hkChips(value));
    else field.append(h('span', { class: 'hk-empty' }, placeholder));
    clearBtn.hidden = !value || rec;
  };
  const say = (t, tone) => { msg.textContent = t || ''; msg.className = 'hk-msg' + (t ? ' ' + (tone || 'err') : ''); };
  const stop = () => { rec = false; window.removeEventListener('keydown', onKey, true); window.removeEventListener('mousedown', onAway, true); paint(); };
  const onAway = e => { if (!field.contains(e.target) && !recBtn.contains(e.target)) stop(); };
  const onKey = e => {
    e.preventDefault(); e.stopPropagation();
    if (e.key === 'Escape') { say(''); stop(); return; }
    if (['Control', 'Alt', 'Shift', 'Meta', 'AltGraph'].includes(e.key)) {
      const live = [e.ctrlKey && 'Ctrl', e.altKey && 'Alt', e.shiftKey && 'Shift'].filter(Boolean);
      paint(live.length ? live.join('+') + '+...' : null); field.classList.add('rec'); return;
    }
    if (e.metaKey) { say('The Windows key cannot be used.'); return; }
    const key = keyFromEvent(e);
    if (!key) { say('That key is not supported. Use a letter, digit, F1-F24 or one of ` - = [ ] \\ ; \' , . /'); return; }
    for (const m of ['ctrl', 'alt', 'shift']) {
      if (e[m + 'Key'] && !mods[m]) {
        say(m === 'alt' ? 'Alt is not allowed here.' : (m === 'ctrl' ? 'Ctrl' : 'Shift') + ' cannot be used here: ZBrush reads it as ' + (m === 'ctrl' ? 'mask' : 'smooth') + '. Use a bare F-key or Alt.');
        return;
      }
    }
    const str = [e.ctrlKey && 'Ctrl', e.altKey && 'Alt', e.shiftKey && 'Shift', key].filter(Boolean).join('+');
    value = str; say(''); stop(); onChange(str);
  };
  const start = () => {
    if (rec) { stop(); return; }
    rec = true; say(''); paint();
    window.addEventListener('keydown', onKey, true); window.addEventListener('mousedown', onAway, true);
    field.focus();
  };
  recBtn.onclick = start;
  field.onclick = start;
  field.onkeydown = e => { if (!rec && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); start(); } };
  clearBtn.onclick = () => { value = ''; say(''); paint(); onChange(''); };
  paint();
  const wrap = h('div', { class: 'hk-wrap' }, h('div', { class: 'hk-row' }, field, recBtn, clearBtn), noMessage ? null : msg);
  wrap.say = say; wrap.setValue = v => { value = v; paint(); };
  return wrap;
}

/* ================================================================== mutation core */
let validateGen = 0;                                              // a slower earlier validation must not overwrite a newer one
const validateSoon = debounce(async () => {
  const gen = ++validateGen;
  try { const r = await call('validate', S.cfg); if (gen !== validateGen) return; S.problems = (r && r.problems) || []; renderProblems(); } catch (e) { /* keep old */ }
}, 350);
const previewSoon = debounce(() => { if (R.preview) R.preview(); }, 150);
const snapSoon = debounce(() => pushSnap(), 450);

function touch() { S.version++; updateDirty(); validateSoon(); previewSoon(); snapSoon(); updateHistButtons(); }
function refreshRegions(inspector) {
  if (R.menuList) R.menuList();
  if (R.itemList) R.itemList();
  if (R.overlay) R.overlay();
  if (R.libTarget) R.libTarget();
  if (R.badges) R.badges();
  if (inspector && R.right && S.tab !== 'brushes') R.right();
}
function commit({ inspector = false } = {}) { touch(); refreshRegions(inspector); }
function renderAllMenus() { refreshRegions(true); if (R.head) R.head(); }

/* History entries are { cfg, menuId, itemIdx, id }: cfg is the JSON string (cheap to compare), the selection is where the
   user was while sitting at that state, so Undo puts them back on what they were editing. */
let histSeq = 0;
const newEntry = str => ({ cfg: str, menuId: S.menuId, itemIdx: S.itemIdx, id: ++histSeq });
function resetHistory(str) { S.hist = [newEntry(str)]; S.histI = 0; updateHistButtons(); }
function histPending() { const cur = S.hist[S.histI]; return !!S.cfg && !!cur && JSON.stringify(S.cfg) !== cur.cfg; }
function updateHistButtons() {
  const u = $('#undoBtn'), r = $('#redoBtn'); if (!u || !r) return;
  const live = !!S.cfg && S.ready && !S.fatal, pending = live && histPending();
  u.disabled = !live || !(S.histI > 0 || pending);
  r.disabled = !live || pending || S.histI >= S.hist.length - 1;      // a change not yet filed would be lost by Redo
}
function pushSnap() {
  const s = JSON.stringify(S.cfg), cur = S.hist[S.histI];
  if (cur && s === cur.cfg) { cur.menuId = S.menuId; cur.itemIdx = S.itemIdx; updateHistButtons(); return; }
  S.hist.splice(S.histI + 1); S.hist.push(newEntry(s));
  if (S.hist.length > 100) S.hist.shift();
  S.histI = S.hist.length - 1;
  updateHistButtons();
}
/* While the config sits unchanged at the current history entry, the entry follows the selection. */
function rememberSel() {
  const cur = S.hist[S.histI];
  if (cur && S.cfg && JSON.stringify(S.cfg) === cur.cfg) { cur.menuId = S.menuId; cur.itemIdx = S.itemIdx; }
}
/* Files the change just made as its own history entry (and the state before it, if an edit was still waiting), and
   returns that entry's id. A toast's Undo is only honoured while this entry is still the current one. */
function sealSnap() { snapSoon.cancel(); pushSnap(); return S.hist[S.histI].id; }
function undoToast(msg, o = {}) {
  const at = sealSnap();
  toast(msg, Object.assign({}, o, { action: { text: 'Undo', fn: () => {
    if (S.hist[S.histI].id !== at || histPending()) { toast('That change was already undone or followed by another', { ms: 2800 }); return; }
    undo();
  } } }));
}
function applySnap(e) {
  S.cfg = JSON.parse(e.cfg);
  const ids = Object.keys(S.cfg.menus);
  S.menuId = S.cfg.menus[e.menuId] ? e.menuId : (S.cfg.menus[S.menuId] ? S.menuId : (ids[0] || null));
  const m = curMenu();
  S.itemIdx = m && S.menuId === e.menuId && Number.isInteger(e.itemIdx) && e.itemIdx >= 0 && e.itemIdx < (m.items || []).length ? e.itemIdx : null;
  if (S.itemIdx === null && S.tab === 'item') S.tab = 'menu';
  else if (S.itemIdx !== null && S.tab === 'menu') S.tab = 'item';
  S.version++; updateDirty(); validateSoon(); previewSoon(); updateHistButtons();
  renderAllMenus(); if (R.settings) R.settings();
  const row = $('.irow.sel'); if (row) row.scrollIntoView({ block: 'nearest' });
}
function undo() { snapSoon.cancel(); pushSnap(); if (S.histI > 0) { S.histI--; applySnap(S.hist[S.histI]); toast('Undone', { ms: 1400 }); } }
function redo() { snapSoon.cancel(); pushSnap(); if (S.histI < S.hist.length - 1) { S.histI++; applySnap(S.hist[S.histI]); toast('Redone', { ms: 1400 }); } }

/* ---------- menu operations */
/* from: where this menu was opened from (a submenu item or an Open button), which the Back chip returns to. Any other way of
   picking a menu leaves the trail. */
function selectMenu(id, { keepItem = false, from = null } = {}) {
  if (!S.cfg.menus[id]) return;
  S.menuId = id;
  S.cameFrom = from;
  if (!keepItem) S.itemIdx = null;
  if (S.tab === 'item' && S.itemIdx === null) S.tab = 'menu';
  rememberSel();
  renderAllMenus();
  if (R.preview) R.preview();
  if (R.libTarget) R.libTarget();
}
function openSubmenu(targetId, itemIdx = S.itemIdx) {
  if (!S.cfg.menus[targetId] || targetId === S.menuId) return;
  selectMenu(targetId, { from: { menuId: S.menuId, itemIdx: Number.isInteger(itemIdx) ? itemIdx : null } });
}
function goBack() {
  const c = S.cameFrom;
  if (!c || !S.cfg.menus[c.menuId]) { S.cameFrom = null; if (R.itemList) R.itemList(); return; }
  selectMenu(c.menuId);
  const m = curMenu();
  if (c.itemIdx !== null && m && m.items[c.itemIdx]) selectItem(c.itemIdx);
}
function selectItem(i, { focusTarget = false } = {}) {
  S.itemIdx = i;
  if (i !== null) S.tab = 'item';
  else if (S.tab === 'item') S.tab = 'menu';
  rememberSel();
  if (R.itemList) R.itemList();
  if (R.overlay) R.overlay();
  if (R.right) R.right();
  const row = $('.irow.sel'); if (row) row.scrollIntoView({ block: 'nearest' });
  if (focusTarget) { const t = $('[data-focus="target"]'); if (t) t.focus(); }
}
function addMenu() {
  const id = uniqueId('menu');
  S.cfg.menus[id] = { title: 'New menu', items: [] };
  S.menuId = id; S.itemIdx = null; S.tab = 'menu';
  commit({ inspector: true }); if (R.head) R.head();
  if (R.preview) R.preview();
  if (R.renameMenu) R.renameMenu(id);
  return id;
}
function dupMenu(id) {
  const src = S.cfg.menus[id]; if (!src) return;
  const nid = uniqueId(id + '_copy');
  const copy = clone(src); copy.title = (src.title || id) + ' copy'; delete copy.hotkey;
  const out = {};
  for (const [k, v] of Object.entries(S.cfg.menus)) { out[k] = v; if (k === id) out[nid] = copy; }
  S.cfg.menus = out; S.menuId = nid; S.itemIdx = null;
  commit({ inspector: true }); if (R.head) R.head(); if (R.preview) R.preview();
  toast('Duplicated. The copy has no hotkey, so it works as a submenu.', { ms: 3600 });
}
async function deleteMenu(id) {
  const m = S.cfg.menus[id]; if (!m) return;
  const refs = referrers(id).filter(r => r.menuId !== id);
  const body = [h('p', null, `Delete the menu "${m.title || id}" and its ${m.items.length} item${m.items.length === 1 ? '' : 's'}?`)];
  if (refs.length) {
    body.push(h('p', { class: 'warn-text' }, `It is opened as a submenu from ${refs.length} item${refs.length === 1 ? '' : 's'}. Those items will be removed too:`));
    body.push(h('ul', { class: 'ref-list' }, refs.map(r => h('li', null, h('b', null, S.cfg.menus[r.menuId].title || r.menuId), ' / item ' + (r.index + 1) + ' ', h('span', { class: 'mono' }, '"' + itemLabel(r.item) + '"')))));
  }
  const ok = await modal({ title: 'Delete menu', body, actions: [{ text: 'Cancel', value: false, focus: true }, { text: refs.length ? 'Delete menu and links' : 'Delete menu', kind: 'danger', value: true }] });
  if (!ok) return;
  if (!S.cfg.menus[id]) return;
  const fresh = referrers(id).filter(r => r.menuId !== id);     // the config may have changed while the dialog was open
  sealSnap();
  if (S.itemIdx !== null && S.menuId !== id) {
    const here = fresh.filter(r => r.menuId === S.menuId).map(r => r.index);
    S.itemIdx = here.includes(S.itemIdx) ? null : S.itemIdx - here.filter(x => x < S.itemIdx).length;
  }
  fresh.sort((a, b) => b.index - a.index).forEach(r => { const mm = S.cfg.menus[r.menuId]; if (mm) mm.items.splice(r.index, 1); });
  const ids = Object.keys(S.cfg.menus), pos = ids.indexOf(id);
  delete S.cfg.menus[id];
  if (S.menuId === id) { const rest = Object.keys(S.cfg.menus); S.menuId = rest[Math.min(pos, rest.length - 1)] || null; S.itemIdx = null; }
  if (S.itemIdx !== null && curMenu() && S.itemIdx >= curMenu().items.length) S.itemIdx = null;
  commit({ inspector: true }); if (R.head) R.head(); if (R.preview) R.preview();
  undoToast(`Deleted "${m.title || id}"`);
}
/* What is wrong with newId as the id of menu oldId, in words, or null when it is fine (or unchanged). */
function menuIdProblem(oldId, newId) {
  newId = newId.trim();
  if (newId === oldId) return null;
  if (!newId) return 'The id cannot be empty.';
  if (/^tag:/.test(newId)) return 'Ids starting with "tag:" are reserved for tag submenus.';
  if (!/^[A-Za-z0-9_-]+$/.test(newId)) return 'Use letters, digits, - and _ only.';
  if (/^\d+$/.test(newId)) return 'The id cannot be only digits.';
  if (S.cfg.menus[newId]) return 'Another menu already uses that id.';
  return null;
}
function renameMenuId(oldId, newId) {
  newId = newId.trim();
  if (newId === oldId) return null;
  const bad = menuIdProblem(oldId, newId);
  if (bad) return bad;
  const out = {};
  for (const [k, v] of Object.entries(S.cfg.menus)) out[k === oldId ? newId : k] = v;
  S.cfg.menus = out;
  for (const m of Object.values(out)) (m.items || []).forEach(it => { if (it && it.menu === oldId) it.menu = newId; });
  if (S.menuId === oldId) S.menuId = newId;
  commit({ inspector: true }); if (R.head) R.head();
  return null;
}
function moveMenu(id, beforeId) {
  if (id === beforeId) return;
  const ids = Object.keys(S.cfg.menus).filter(k => k !== id);
  const at = beforeId ? ids.indexOf(beforeId) : ids.length;
  ids.splice(at < 0 ? ids.length : at, 0, id);
  const out = {}; ids.forEach(k => { out[k] = S.cfg.menus[k]; });
  S.cfg.menus = out; commit();
}

/* ---------- item operations */
function addItem(kind, at = null) {
  const m = curMenu(); if (!m) return;
  const it = makeItem(kind, '');
  if (kind === 'steps') it.steps = [makeItem('brush', '')];
  const i = at === null ? m.items.length : at;
  m.items.splice(i, 0, it);
  S.itemIdx = i; S.tab = 'item';
  commit({ inspector: true }); if (R.head) R.head();
  const row = $('.irow.sel'); if (row) row.scrollIntoView({ block: 'nearest' });
  const t = $('[data-focus="target"]'); if (t) t.focus();
}
function insertAsset(menuId, kind, name, at = null, silent = false) {
  const m = S.cfg.menus[menuId]; if (!m || !isLib(kind)) return;
  const i = at === null || at > m.items.length ? m.items.length : at;
  const sel = menuId === S.menuId ? curItem() : null;
  if (!silent) sealSnap();
  m.items.splice(i, 0, { [kind]: name });
  if (sel) S.itemIdx = m.items.indexOf(sel);
  commit({ inspector: true }); if (R.head) R.head();
  flashRow(menuId, i);
  if (!silent) undoToast(`Added ${name} to "${m.title || menuId}"`);
}
/* Scrolls the row to view and flashes it, in whichever item lists are on screen (Menus editor, Library target panel). */
function flashRow(menuId, i) {
  for (const r of $$('.irow')) {
    if (r.dataset.menu !== menuId || +r.dataset.i !== i) continue;
    r.scrollIntoView({ block: 'nearest' });
    r.classList.remove('flash'); void r.offsetWidth; r.classList.add('flash');
    setTimeout(() => r.classList.remove('flash'), 1400);
  }
}
function dupItem(i) {
  const m = curMenu(); if (!m || !m.items[i]) return;
  m.items.splice(i + 1, 0, clone(m.items[i]));
  S.itemIdx = i + 1; S.tab = 'item';
  commit({ inspector: true }); if (R.head) R.head();
}
function delItem(i, menuId = S.menuId) {
  const m = S.cfg.menus[menuId]; if (!m || !m.items[i]) return;
  sealSnap();
  const removed = m.items.splice(i, 1)[0];
  if (menuId === S.menuId) {
    if (S.itemIdx === i) S.itemIdx = m.items.length ? Math.min(i, m.items.length - 1) : null;
    else if (S.itemIdx !== null && S.itemIdx > i) S.itemIdx--;
  }
  commit({ inspector: true }); if (R.head) R.head();
  undoToast(`Removed "${itemLabel(removed)}"`, { ms: 3800 });
}
function moveItem(menuId, from, to) {
  const m = S.cfg.menus[menuId]; if (!m) return;
  const sel = menuId === S.menuId ? curItem() : null;
  const [it] = m.items.splice(from, 1);
  const t = to > from ? to - 1 : to;
  m.items.splice(clamp(t, 0, m.items.length), 0, it);
  if (sel) S.itemIdx = m.items.indexOf(sel);
  commit({ inspector: true });
}
/* Moves item `index` of menu fromId to the end of menu toId, or copies it there (a deep copy) when `copy` is set. */
function transferItem(fromId, index, toId, copy) {
  const src = S.cfg.menus[fromId], dst = S.cfg.menus[toId];
  if (!src || !dst || fromId === toId || !src.items[index]) return;
  const it = src.items[index];
  if (it.menu === toId) { toast('A menu cannot open itself, so that item stays where it is.', { tone: 'warn' }); return; }
  sealSnap();
  const label = itemLabel(it), dstName = dst.title || toId;
  if (copy) dst.items.push(clone(it));
  else {
    src.items.splice(index, 1); dst.items.push(it);
    if (S.menuId === fromId) { S.menuId = toId; S.itemIdx = dst.items.length - 1; S.tab = 'item'; S.cameFrom = null; }   // follow the item to its new menu
    else if (S.menuId === toId) S.itemIdx = dst.items.length - 1;
  }
  commit({ inspector: true }); if (R.head) R.head();
  if (!copy && R.preview) R.preview();
  if (!copy) { const row = $('.irow.sel'); if (row) row.scrollIntoView({ block: 'nearest' }); }
  undoToast(`${copy ? 'Copied' : 'Moved'} "${label}" to "${dstName}"`);
}
function dropOnMenu(menuId, payload, at) {
  if (payload.type === 'asset') insertAsset(menuId, payload.kind, payload.name, at);
  else if (payload.type === 'item' && payload.menuId === menuId) moveItem(menuId, payload.index, at === null ? S.cfg.menus[menuId].items.length : at);
}

/* ================================================================== shared UI bits */
function emptyState(iconName, title, text, action) {
  return h('div', { class: 'empty' }, h('div', { class: 'empty-ico' }, icon(iconName, 34)), h('h3', null, title), text ? h('p', null, text) : null,
    action ? h('button', { class: 'btn small', type: 'button', onclick: action.fn }, action.text) : null);
}
function toggleSwitch(checked, onChange, label) {
  const inp = h('input', { type: 'checkbox', checked, 'aria-label': label, onchange: async () => { const want = inp.checked; if (await onChange(want) === false) inp.checked = !want; } });
  return h('label', { class: 'toggle' }, inp, h('span', { class: 'track' }));
}
function field(label, control, hint) {
  return h('div', { class: 'field' }, h('span', { class: 'flabel' }, label), control, hint ? h('div', { class: 'fhint' }, hint) : null);
}
function textInput(value, onInput, o = {}) {
  const inp = h('input', { class: 'inp ' + (o.mono ? 'mono' : ''), type: 'text', value, placeholder: o.placeholder || '', spellcheck: 'false', autocomplete: 'off', 'aria-label': o.label, dataset: o.focus ? { focus: o.focus } : null });
  inp.addEventListener('input', () => onInput(inp.value));
  if (o.onChange) inp.addEventListener('change', () => o.onChange(inp.value, inp));
  return inp;
}
/* A 'set' value must be a number (config.py rejects anything else): plain decimals become numbers, the rest stays text so it can be flagged. */
function parseValue(s) { const t = s.trim(); return /^-?\d+(\.\d+)?$/.test(t) ? Number(t) : s; }
const validValue = v => typeof v === 'number' && Number.isFinite(v);
const VALUE_HINT = 'Use a number, e.g. 32';
function sectionTitle(t, sub) { return h('div', { class: 'sect' }, h('span', null, t), sub ? h('em', null, sub) : null); }

/* ================================================================== MENUS screen */
function buildMenusScreen(root) {
  root.replaceChildren();
  const listEl = h('div', { class: 'mlist', role: 'listbox', 'aria-label': 'Menus' });
  const left = h('aside', { class: 'col menus-col' },
    h('div', { class: 'col-head' }, h('span', { class: 'micro' }, 'Menus'), h('span', { class: 'count' }, '', ), iconBtn('plus', 'Add menu', () => addMenu(), 'accent')),
    listEl,
    h('button', { class: 'dashed', type: 'button', onclick: () => addMenu() }, icon('plus', 14), 'Add menu'));
  const head = h('div', { class: 'center-head' });
  const stageBox = buildStage();
  const itemsEl = h('div', { class: 'ilist', role: 'listbox', 'aria-label': 'Items in this menu', title: 'Alt+Up/Down moves the selected item' });
  const itemsHead = h('div', { class: 'col-head slim' });
  const itemsPanel = h('div', { class: 'items-panel' }, itemsHead, itemsEl);
  const center = h('section', { class: 'col center-col' }, head, stageBox.el, itemsPanel);
  const rightEl = h('aside', { class: 'col right-col' });
  root.append(left, center, rightEl);

  /* --- header */
  R.head = () => {
    const m = curMenu();
    head.replaceChildren();
    if (!m) return;
    head.append(h('div', { class: 'head-title' }, h('h1', null, m.title || S.menuId), h('span', { class: 'idchip mono' }, S.menuId),
      m.hotkey ? hkChips(m.hotkey) : h('span', { class: 'tag cyan' }, 'submenu only')));
    setText($('.count', left), String(Object.keys(S.cfg.menus).length));
  };

  /* --- menu list */
  // Rebuilt only when what it shows changed; a plain selection change just moves the `sel` class, so the clicked row keeps focus.
  const menuRows = () => $$('.mrow', listEl);
  const menuRowOf = id => menuRows().find(r => r.dataset.id === id);
  const refreshMenuSel = () => menuRows().forEach(r => { const on = r.dataset.id === S.menuId; r.classList.toggle('sel', on); r.setAttribute('aria-selected', on ? 'true' : 'false'); });
  R.menuList = () => {
    const ids = Object.keys(S.cfg.menus);
    setText($('.count', left), String(ids.length));
    const sig = JSON.stringify(ids.map(id => { const m = S.cfg.menus[id]; return [id, m.title || '', m.hotkey || '', (m.items || []).length]; }));
    if (sig === listEl._sig) { refreshMenuSel(); listEl._sel = S.menuId; return; }
    listEl._sig = sig;
    const act = document.activeElement, fr = act && listEl.contains(act) ? act.closest('.mrow') : null;
    const had = !!act && listEl.contains(act), fid = fr ? fr.dataset.id : null, fidx = fr ? menuRows().indexOf(fr) : -1, prevSel = listEl._sel;
    listEl.replaceChildren();
    if (!ids.length) { listEl.append(emptyState('menus', 'No menus yet', 'Create a menu to get started. Give it a hotkey to open it from ZBrush.', { text: 'Add menu', fn: addMenu })); return; }
    ids.forEach(id => {
      const m = S.cfg.menus[id];
      const row = h('div', { class: 'mrow' + (id === S.menuId ? ' sel' : '') + (m.hotkey ? '' : ' subonly'), role: 'option', 'aria-selected': id === S.menuId ? 'true' : 'false', tabindex: '0', dataset: { id } });
      const title = h('div', { class: 'mrow-title' }, m.title || id);
      row.append(
        h('div', { class: 'mrow-main' }, title, h('div', { class: 'mrow-meta' }, h('span', { class: 'mono' }, id))),
        h('div', { class: 'mrow-side' },
          menuWarn(id),
          m.hotkey ? hkChips(m.hotkey, 'sm') : h('span', { class: 'tag cyan', title: 'No hotkey: this menu can only be opened from another menu' }, 'submenu'),
          h('span', { class: 'pill-n', title: (m.items || []).length + ' items' }, String((m.items || []).length))),
        h('div', { class: 'mrow-actions' },
          iconBtn('edit', 'Rename (F2)', e => { e.stopPropagation(); R.renameMenu(id); }),
          iconBtn('copy', 'Duplicate', e => { e.stopPropagation(); dupMenu(id); }),
          iconBtn('trash', 'Delete (Delete)', e => { e.stopPropagation(); deleteMenu(id); }, 'danger')));
      row.addEventListener('click', () => { if (id !== S.menuId) selectMenu(id); });
      title.addEventListener('dblclick', () => R.renameMenu(id));
      row.addEventListener('keydown', e => {
        if (e.target !== row) return;
        const i = ids.indexOf(id);
        if (e.key === 'ArrowDown' && ids[i + 1]) { e.preventDefault(); selectMenu(ids[i + 1]); $(`.mrow[data-id="${CSS.escape(ids[i + 1])}"]`, listEl).focus(); }
        else if (e.key === 'ArrowUp' && ids[i - 1]) { e.preventDefault(); selectMenu(ids[i - 1]); $(`.mrow[data-id="${CSS.escape(ids[i - 1])}"]`, listEl).focus(); }
        else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectMenu(id); }
        else if (e.key === 'F2') { e.preventDefault(); R.renameMenu(id); }
        else if (e.key === 'Delete') { e.preventDefault(); deleteMenu(id); }
      });
      DnD.source(row, () => ({ type: 'menu', id }), () => h('span', { class: 'ghost-chip' }, icon('menus', 14), m.title || id));
      DnD.zone(row, {
        accept: p => p.type === 'asset' || (p.type === 'menu' && p.id !== id) || (p.type === 'item' && p.menuId !== id),
        over: (p, x, y, ev) => {
          const r = row.getBoundingClientRect();
          row.classList.remove('drop-brush', 'drop-copy', 'ins-before', 'ins-after');
          if (p.type === 'asset') row.classList.add('drop-brush');
          else if (p.type === 'item') { row.classList.add('drop-brush'); if (ev && ev.ctrlKey) row.classList.add('drop-copy'); }   // Ctrl copies instead of moving
          else row.classList.add(y < r.top + r.height / 2 ? 'ins-before' : 'ins-after');
        },
        leave: () => row.classList.remove('drop-brush', 'drop-copy', 'ins-before', 'ins-after'),
        drop: (p, x, y, ev) => {
          if (p.type === 'asset') insertAsset(id, p.kind, p.name, null);
          else if (p.type === 'item') transferItem(p.menuId, p.index, id, !!(ev && ev.ctrlKey));
          else { const r = row.getBoundingClientRect(); const ids2 = Object.keys(S.cfg.menus); const before = y < r.top + r.height / 2 ? id : ids2[ids2.indexOf(id) + 1]; moveMenu(p.id, before || null); }
        },
      });
      listEl.append(row);
    });
    listEl._sel = S.menuId;
    if (had) {
      const rows = menuRows();
      const t = fid !== null && fid === prevSel && menuRowOf(S.menuId) ? menuRowOf(S.menuId)
        : (fid !== null ? (menuRowOf(fid) || rows[clamp(fidx, 0, rows.length - 1)]) : null);
      if (t) t.focus();
    }
  };
  R.renameMenu = id => {
    const row = $(`.mrow[data-id="${CSS.escape(id)}"]`, listEl); if (!row) return;
    const title = $('.mrow-title', row), m = S.cfg.menus[id];
    const inp = h('input', { class: 'inp rename', type: 'text', value: m.title || '', 'aria-label': 'Menu title' });
    title.replaceChildren(inp); row.classList.add('renaming');
    inp.focus(); inp.select();
    let done = false;
    const finish = ok => {
      if (done) return; done = true;
      if (ok) { const v = inp.value.trim(); if (v && v !== m.title) { m.title = v; commit({ inspector: true }); if (R.head) R.head(); return; } }
      listEl._sig = null;                                       // the row holds the input: force a rebuild
      R.menuList();
    };
    // Only Enter and Escape are ours; everything else (Ctrl+S, Alt+1..6) still reaches the window, after the new title is taken in
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.stopPropagation(); finish(true); }
      else if (e.key === 'Escape') { e.stopPropagation(); finish(false); }
      else if (((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 's') || (e.altKey && !e.ctrlKey && /^[1-6]$/.test(e.key))) finish(true);
    });
    inp.addEventListener('blur', () => finish(true));
    inp.addEventListener('click', e => e.stopPropagation());
  };

  /* --- items list */
  const addBtn = h('button', { class: 'btn small', type: 'button', onclick: e => popover(e.currentTarget, Object.keys(KIND).map(k => ({ icon: KIND[k].icon, label: KIND[k].label, hint: KIND[k].hint, fn: () => addItem(k) }))) }, icon('plus', 13), 'Add item');
  R.itemList = () => {
    const m = curMenu();
    const back = S.cameFrom && S.cameFrom.menuId !== S.menuId ? S.cfg.menus[S.cameFrom.menuId] : null;
    if (!back && S.cameFrom) S.cameFrom = null;
    itemsHead.replaceChildren(...[back ? h('button', { class: 'chip back', type: 'button', title: 'Back to ' + (back.title || S.cameFrom.menuId), onclick: goBack }, icon('chevL', 12), h('span', { class: 'back-txt' }, 'Back to ' + (back.title || S.cameFrom.menuId))) : null,
      h('span', { class: 'micro' }, 'Items'), h('span', { class: 'count' }, m ? String(m.items.length) : '0'), h('span', { class: 'spacer' }), m ? addBtn : null].filter(Boolean));
    renderItemList(itemsEl, S.menuId, false);
  };

  /* --- right column */
  const tabs = h('div', { class: 'tabs', role: 'tablist' });
  const body = h('div', { class: 'tab-body' });
  rightEl.append(tabs, body);
  let dock = null, dockScroll = 0;
  R.right = () => {
    if (S.tab === 'brushes') { /* keep the dock alive */ } else if (dock) { dockScroll = dock.scroller().scrollTop; }
    tabs.replaceChildren(...[['item', 'Item'], ['menu', 'Menu'], ['brushes', 'Library']].map(([k, label]) =>
      h('button', { class: 'tab' + (S.tab === k ? ' on' : ''), role: 'tab', type: 'button', 'aria-selected': S.tab === k ? 'true' : 'false',
        onclick: () => { S.tab = k; R.right(); } }, label)));
    body.replaceChildren();
    body.className = 'tab-body tab-' + S.tab;
    if (S.tab === 'item') body.append(buildItemInspector());
    else if (S.tab === 'menu') body.append(buildMenuProps());
    else {
      if (!dock) dock = makeBrowser({ compact: true, st: S.dock });
      body.append(dock.el);
      dock.scroller().scrollTop = dockScroll;
      R.badges = () => dock.updateBadges();
    }
    if (S.tab !== 'brushes') R.badges = null;
  };
  R.playAnim = () => stageBox.playAnim();
  R.libRefresh = kind => { if (dock && kind === S.dock.kind) dock.refresh(); };

  R.head(); R.menuList(); R.itemList(); R.right();
  stageBox.start();
}

/* Reusable item list: used by the Menus screen and the Library screen's target panel. */
function renderItemList(box, menuId, compact) {
  const m = S.cfg.menus[menuId];
  box.classList.toggle('compact', compact);
  const refreshSel = () => $$('.irow', box).forEach(r => {
    const on = !compact && +r.dataset.i === S.itemIdx;
    r.classList.toggle('sel', on); r.setAttribute('aria-selected', on ? 'true' : 'false');
  });
  // Rebuilt only when a row would look different; a plain selection change just moves the `sel` class, so focus stays put.
  const sig = m ? JSON.stringify([menuId, compact, (m.items || []).map(it => [itemLabel(it), itemUsable(it), it, isLib(kindOf(it)) ? (firstTag(kindOf(it), it[kindOf(it)]) || {}).color || '' : keyTag(it) ? [keyTag(it).label, keyTag(it).color] : ''])]) : 'none';
  if (sig === box._sig) { refreshSel(); box._sel = compact ? null : S.itemIdx; return; }
  box._sig = sig;
  const switched = box._menu !== menuId, keepTop = box.scrollTop, prevSel = box._sel;
  box._menu = menuId;
  const act = document.activeElement, fr = act && box.contains(act) ? act.closest('.irow') : null;
  const had = !!act && box.contains(act), fi = fr ? +fr.dataset.i : null;
  box.replaceChildren();
  if (!m) { box.append(emptyState('menus', 'No menu selected', '')); return; }
  if (!m.items.length) {
    box.append(emptyState('plus', 'No items yet', compact ? 'Drag an item here or press + on a card.' : 'Drag an item here from the Library tab, or use Add item.'));
  }
  m.items.forEach((it, i) => {
    const k = kindOf(it), ok = itemUsable(it);
    const row = h('div', { class: 'irow k-' + k + (!compact && i === S.itemIdx ? ' sel' : '') + (ok ? '' : ' bad'), role: 'option', tabindex: '0', dataset: { i, menu: menuId },
      'aria-selected': !compact && i === S.itemIdx ? 'true' : 'false' },
      compact ? null : h('span', { class: 'grip', 'aria-hidden': 'true' }, icon('grip', 14)),
      h('span', { class: 'inum mono' }, String(i + 1)),
      itemThumb(it, compact ? 26 : 32),
      h('span', { class: 'imain' }, h('span', { class: 'iname' }, isLib(k) ? tagDot(k, it[k]) : keyTag(it) ? keyDot(keyTag(it)) : null, itemLabel(it)),
        compact ? null : h('span', { class: 'isub mono' }, k === 'auto' ? 'filled from your picks' : k === 'tag' ? (it.tag ? 'all items tagged ' + tagName(it.tag) : '(not set)') : k === 'browser' ? 'opens the ' + K(it.kind).one + ' browser' + (it.browser ? ' for ' + tagName(it.browser) : '') : k === 'steps' ? `${(it.steps || []).length} step${(it.steps || []).length === 1 ? '' : 's'}` : (k === 'set' ? `${targetOf(it)} = ${it.value}` : targetOf(it) || '(not set)'))),
      h('span', { class: 'ikind', title: KIND[k].hint }, icon(KIND[k].icon, 13), compact ? null : KIND[k].label),
      itemWarn(menuId, i, ok),
      h('span', { class: 'iacts' },
        compact ? null : iconBtn('copy', 'Duplicate item', e => { e.stopPropagation(); S.itemIdx = i; dupItem(i); }),
        iconBtn('trash', compact ? 'Delete item' : 'Delete (Delete)', e => { e.stopPropagation(); if (e.detail > 1) return; delItem(i, menuId); }, 'danger')));
    if (!compact) {
      row.addEventListener('click', () => selectItem(i));
      row.addEventListener('dblclick', () => { if (k === 'menu' && S.cfg.menus[it.menu]) openSubmenu(it.menu, i); });
      row.addEventListener('keydown', e => {
        if (e.target !== row) return;
        const rows = $$('.irow', box);
        if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
          e.preventDefault();
          const to = e.key === 'ArrowUp' ? i - 1 : i + 2;
          if (to >= 0 && to <= m.items.length) { moveItem(menuId, i, to); const r = $$('.irow', box)[e.key === 'ArrowUp' ? i - 1 : i + 1]; if (r) r.focus(); }
        }
        else if (e.key === 'ArrowDown' && rows[i + 1]) { e.preventDefault(); selectItem(i + 1); $$('.irow', box)[i + 1].focus(); }
        else if (e.key === 'ArrowUp' && rows[i - 1]) { e.preventDefault(); selectItem(i - 1); $$('.irow', box)[i - 1].focus(); }
        else if (e.key === 'Enter') { e.preventDefault(); selectItem(i, { focusTarget: true }); }
        else if (e.key === 'Delete') { e.preventDefault(); delItem(i, menuId); }
      });
    }
    DnD.source(row, () => ({ type: 'item', menuId, index: i }), () => h('span', { class: 'ghost-chip' }, itemThumb(it, 22), itemLabel(it)));
    box.append(row);
  });
  const insertIndex = y => {
    const rows = $$('.irow', box);
    for (let j = 0; j < rows.length; j++) { const r = rows[j].getBoundingClientRect(); if (y < r.top + r.height / 2) return j; }
    return rows.length;
  };
  const clear = () => { $$('.ins-before', box).forEach(r => r.classList.remove('ins-before')); box.classList.remove('ins-end', 'drop-over'); };
  DnD.zone(box, {
    accept: p => p.type === 'asset' || (p.type === 'item' && p.menuId === menuId),
    over: (p, x, y) => {
      clear(); box.classList.add('drop-over');
      const j = insertIndex(y), rows = $$('.irow', box);
      if (j < rows.length) rows[j].classList.add('ins-before'); else box.classList.add('ins-end');
    },
    leave: clear,
    drop: (p, x, y) => dropOnMenu(menuId, p, insertIndex(y)),
  });
  refreshSel();
  box._sel = compact ? null : S.itemIdx;
  box.scrollTop = switched ? 0 : keepTop;                      // another menu starts at the top, the same menu keeps its place
  if (had) {                                                   // the focused row was replaced: focus its successor
    const rows = $$('.irow', box);
    const t = switched ? (rows[S.itemIdx] || rows[0])
      : fi !== null && fi === prevSel && rows[S.itemIdx] ? rows[S.itemIdx]
      : (fi !== null ? rows[clamp(fi, 0, rows.length - 1)] : (!compact && S.itemIdx !== null ? rows[S.itemIdx] : null));
    if (t) t.focus();
  } else if (switched && !compact) { const sr = $('.irow.sel', box); if (sr) sr.scrollIntoView({ block: 'nearest' }); }
}

/* ---------- the ring stage (live preview with overlay) */
// Widest angle (degrees) one slot answers to. A copy of MAX_SECTOR in zorbit/ring.py (Ring._index_at): keep the two in step.
const MAX_SECTOR = 90;
function buildStage() {
  const img = h('img', { class: 'ring-img pending', alt: 'Ring preview', draggable: false });     // hidden until the first image has decoded, so no broken-image icon
  const ov = h('div', { class: 'ring-ov' });
  const wrap = h('div', { class: 'ring-wrap' }, img, ov);
  const emptyEl = h('div', { class: 'stage-empty' });
  const errEl = h('div', { class: 'stage-err' });
  const info = h('div', { class: 'stage-info' });
  const busy = h('span', { class: 'stage-busy', title: 'Updating preview' });
  const playBtn = h('button', { class: 'btn small stage-play', type: 'button' });
  const tip = h('div', { class: 'stage-tip' }, 'Hover to preview, click to select, drag slots or items between slots');
  const trash = h('div', { class: 'stage-trash', 'aria-hidden': 'true' }, icon('trash', 14), 'Delete');     // only there while an item of this menu is being dragged
  const el = h('div', { class: 'stage', tabindex: '0', 'aria-label': 'Ring preview. Use arrow keys to move between items.' },
    h('div', { class: 'stage-rings', 'aria-hidden': 'true' }), wrap, emptyEl, errEl, info, tip, busy, playBtn, trash);
  el.classList.add('loading');
  let curSize = 447, hoverRing = null, gap = null, idxs = [], marks = [], haveImage = false;   // gap: {k, text, noop} while a drag is over the ring
  let box = null, baseVer = -1, shownPath = '';     // box: size and ring centre of the image while a fan is open (null: square, ring in the middle); baseVer: the version curSize was read at

  const geom = () => ({ R: ringNum('radius'), slot: ringNum('slot'), dead: ringNum('dead_zone') });
  const player = makePlayer(() => img, () => requestImage(), st => {
    if (st === 'playing') { box = null; placeImg(); }          // the animation frames are the plain square ring
    el.classList.toggle('playing', st === 'playing');
    playBtn.replaceChildren(st === 'loading' ? h('span', { class: 'spin' }) : icon(st === 'playing' ? 'stop' : 'play', 12), st === 'loading' ? 'Rendering...' : (st === 'playing' ? 'Stop' : 'Preview animation'));
    playBtn.disabled = st === 'loading';
  });
  player.stop(); playBtn.replaceChildren(icon('play', 12), 'Preview animation');
  playBtn.onclick = () => { if (idxs.length) player.play(S.menuId); };

  function layout() {
    const cw = el.clientWidth, ch = el.clientHeight;
    const avail = Math.min(cw - 24, ch - 56);
    const D = Math.max(120, Math.min(curSize, avail));
    wrap.style.width = wrap.style.height = D + 'px';
    placeImg();
    buildMarks();
  }
  /* With a fan open the image is bigger than the ring and not centred on it: it is laid out so its ring centre sits in the middle of wrap. */
  function placeImg() {
    const st = img.style;
    if (!box) { st.position = st.left = st.top = st.width = st.height = st.maxWidth = ''; return; }
    const D = wrap.clientWidth || curSize, k = D / curSize;
    st.position = 'absolute'; st.maxWidth = 'none';
    st.left = D / 2 - box.cx * k + 'px'; st.top = D / 2 - box.cy * k + 'px'; st.width = box.w * k + 'px'; st.height = box.h * k + 'px';
  }
  /* Item indices (in the ring's own order) of the fan to show open: the hovered slot, else the selected one, when it is a submenu whose menu has "fan" or a tag with brushes. */
  function fanPath() {
    const m = curMenu(); if (!m) return null;
    const at = hoverRing !== null ? idxs[hoverRing] : S.itemIdx, j = idxs.indexOf(at);
    const it = j >= 0 ? m.items[at] : null, t = it && 'menu' in it ? S.cfg.menus[it.menu] : null;
    if (it && 'tag' in it) return tagItemCount(it.tag) > 0 ? [j] : null;     // the expander turns it into a fan submenu of its items
    return t && t.fan === true && it.menu !== S.menuId ? [j] : null;
  }
  function buildMarks() {
    ov.replaceChildren(); marks = [];
    idxs = usableIdx(S.menuId);
    const n = idxs.length;
    if (hoverRing !== null && hoverRing >= n) { hoverRing = null; wrap.classList.remove('over-slot'); }   // the ring shrank (undo, menu switch)
    if (gap && gap.k > n) gap = null;
    if (!n) { info.classList.remove('on'); return; }
    const g = geom(), D = wrap.clientWidth || curSize, k = D / curSize, c = D / 2, step = (2 * Math.PI) / n;
    idxs.forEach((itemIndex, j) => {
      const a = step * j, d = g.slot * k;
      const m = h('div', { class: 'slot-ov', style: { left: c + Math.sin(a) * g.R * k + 'px', top: c - Math.cos(a) * g.R * k + 'px', width: d + 'px', height: d + 'px' } },
        h('span', { class: 'slot-n mono' }, String(itemIndex + 1)));
      marks.push(m); ov.append(m);
    });
    paintMarks();
  }
  function paintMarks() {
    const moving = DnD.active && DnD.active.payload.type === 'item' && DnD.active.payload.menuId === S.menuId ? DnD.active.payload : null;   // the slot being dragged
    marks.forEach((m, j) => {
      m.classList.toggle('sel', idxs[j] === S.itemIdx);
      m.classList.toggle('hov', hoverRing === j);
      m.classList.toggle('moving', !!moving && idxs[j] === moving.index);
    });
    const old = $('.gap-ov', ov); if (old) old.remove();
    const m = curMenu();
    if (trash.classList.contains('over') && moving) {           // over the trash: say what goes, whatever redraws the ring meanwhile
      const it = m && m.items[moving.index];
      info.replaceChildren(h('span', null, 'Release to delete '), h('b', null, it ? itemLabel(it) : 'this item')); info.classList.add('on');
    } else if (gap) {
      const g = geom(), D = wrap.clientWidth || curSize, sc = D / curSize, c = D / 2, a = (gap.k - 0.5) * ((2 * Math.PI) / idxs.length);
      ov.append(h('div', { class: 'gap-ov' + (gap.noop ? ' noop' : ''), style: {
        left: c + Math.sin(a) * g.R * sc + 'px', top: c - Math.cos(a) * g.R * sc + 'px', height: g.slot * sc * 1.25 + 'px',
        transform: `translate(-50%, -50%) rotate(${a}rad)` } }));
      info.replaceChildren(h('b', null, gap.text)); info.classList.add('on');
    } else if (hoverRing !== null && m && m.items[idxs[hoverRing]]) {
      const it = m.items[idxs[hoverRing]];
      info.replaceChildren(h('b', null, itemLabel(it)), h('span', { class: 'mono' }, ' ' + KIND[kindOf(it)].label.toLowerCase() + (['steps', 'auto'].includes(kindOf(it)) ? '' : kindOf(it) === 'tag' ? ' / ' + tagName(it.tag) : kindOf(it) === 'browser' ? ' / ' + (it.browser ? tagName(it.browser) : 'all ' + K(it.kind).many) : ' / ' + targetOf(it))));
      info.classList.add('on');
    } else info.classList.remove('on');
  }
  /* Angle of a point in degrees, clockwise from 12 o'clock; null in the dead zone (or with no slots). */
  function angleAt(x, y) {
    if (!idxs.length) return null;
    const r = wrap.getBoundingClientRect();
    const k = r.width / curSize;
    const dx = (x - r.left) / k - curSize / 2, dy = (y - r.top) / k - curSize / 2;
    if (Math.hypot(dx, dy) < geom().dead) return null;
    let ang = (Math.atan2(dx, -dy) * 180) / Math.PI;
    if (ang < 0) ang += 360;
    return ang;
  }
  /* The insertion gap nearest a point: k in 1..n, "before ring slot k" (n is the gap before slot 0, so the end of the list). Null in the dead zone. */
  function gapAt(x, y) {
    const ang = angleAt(x, y), n = idxs.length;
    return ang === null ? null : clamp(Math.round(ang / (360 / n) + 0.5), 1, n);
  }
  function hitTest(x, y) {
    const n = idxs.length, ang = angleAt(x, y); if (ang === null) return null;
    const step = 360 / n, i = Math.round(ang / step) % n;
    const off = Math.abs((((ang - i * step + 180) % 360) + 360) % 360 - 180);      // degrees from that slot's direction
    return off <= Math.min(step, MAX_SECTOR) / 2 ? i : null;                       // the app picks nothing in the gaps of a sparse ring
  }
  let wantedUrl = '';
  const reveal = () => { img.classList.remove('pending'); el.classList.remove('loading'); };   // the shimmer stays until a decoded image can take its place
  function setImg(url, nextBox) {
    if (img.getAttribute('src') === url) { wantedUrl = url; box = nextBox; placeImg(); return; }
    wantedUrl = url;
    if (!img.getAttribute('src')) {
      img.src = url; box = nextBox; placeImg();
      img.decode().catch(() => {}).then(() => { if (wantedUrl === url || img.getAttribute('src') === url) reveal(); });
      return;
    }
    const pre = new Image(); pre.src = url;
    pre.decode().catch(() => {}).then(() => { if (wantedUrl === url) { img.src = url; box = nextBox; placeImg(); reveal(); } });   // picture and placement change together
  }
  function showRes(res, path) {
    el.classList.remove('busy');
    if (res && res.image) {
      el.classList.remove('err'); haveImage = true;
      const w = res.width || res.size, ht = res.height || res.size, cx = res.centre ? res.centre[0] : w / 2, cy = res.centre ? res.centre[1] : ht / 2;
      const fanned = !!path && (Math.abs(w - ht) > 1.5 || Math.abs(cx - w / 2) > 1.5 || Math.abs(cy - ht / 2) > 1.5);
      if (!fanned) { if (res.size && res.size !== curSize) curSize = res.size; baseVer = S.version; }     // only the plain ring says how big the ring is
      setImg(res.image, fanned ? { w, h: ht, cx, cy } : null);
      layout();
    } else if (res) {
      el.classList.add('err'); el.classList.remove('loading');
      errEl.replaceChildren(h('b', null, 'Could not render the preview'), h('span', null, (res.problems || []).slice(0, 2).join(' / ') || 'Unknown error'));
    }
  }
  function requestImage() {
    if (!idxs.length) return;
    const mid = S.menuId, want = hoverRing, ver = S.version, path = fanPath(), pk = path ? path.join() : '';
    shownPath = pk;
    const hit = RingLoader.peek(mid, want, path);
    if (hit && (!path || baseVer === ver)) { showRes(hit, path); return; }
    el.classList.add('busy');
    const load = async () => {
      if (path && baseVer !== ver) {                 // a fan picture cannot say how big the ring is: read that from the plain ring first
        const base = await RingLoader.get(mid, null, null);
        if (base && base.image && mid === S.menuId && ver === S.version) { curSize = base.size; baseVer = ver; }
      }
      return RingLoader.get(mid, want, path);
    };
    load().then(res => {
      if (!res || mid !== S.menuId || ver !== S.version || want !== hoverRing || pk !== shownPath || player.state !== 'idle') { if (res && !res.image) showRes(res); return; }
      showRes(res, path);
    });
  }
  function setHover(j) {
    if (j === hoverRing) return;
    hoverRing = j; wrap.classList.toggle('over-slot', j !== null);
    paintMarks(); requestImage();
  }
  function refresh() {
    const m = curMenu();
    idxs = usableIdx(S.menuId);
    emptyEl.replaceChildren();
    const has = idxs.length > 0;
    if (!has) el.classList.remove('err', 'busy');
    wrap.hidden = !has; emptyEl.hidden = has; playBtn.hidden = !has; tip.hidden = !has;
    if (!m) { emptyEl.append(emptyState('menus', 'No menu selected', 'Pick or create a menu on the left.')); return; }
    if (!has) {
      emptyEl.append(m.items.length
        ? emptyState('alert', 'No usable items yet', 'Fill in the target of each item (see the problems panel). Incomplete items are skipped by the app.')
        : emptyState('plus', 'This menu is empty', 'Add an item from the Library tab or create one. The ring appears as soon as it has one.', { text: 'Add item', fn: () => addItem('brush') }));
      return;
    }
    buildMarks();
  }

  R.overlay = () => { buildMarks(); if (idxs.length && player.state === 'idle' && (fanPath() || []).join() !== shownPath) requestImage(); };      // a new selection may open or close a fan
  R.preview = () => { player.stop(); refresh(); if (idxs.length) requestImage(); };
  el.addEventListener('keydown', e => {
    const m = curMenu(); if (!m || !idxs.length || e.target !== el) return;
    const pos = idxs.indexOf(S.itemIdx);
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); selectItem(idxs[(pos + 1) % idxs.length]); el.focus(); }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); selectItem(idxs[pos < 0 ? idxs.length - 1 : (pos - 1 + idxs.length) % idxs.length]); el.focus(); }
  });
  wrap.addEventListener('pointermove', e => { if (player.state === 'idle' && !DnD.active) setHover(hitTest(e.clientX, e.clientY)); });
  wrap.addEventListener('pointerleave', () => setHover(null));
  wrap.addEventListener('click', e => {
    if (player.state === 'playing') { player.stop(); return; }
    const j = hitTest(e.clientX, e.clientY);
    selectItem(j === null ? null : idxs[j]);
    el.focus({ preventScroll: true });
  });
  /* A ring slot is a drag source too: it moves like a row of the item list. A plain click still selects. */
  DnD.source(wrap, e => {
    if (player.state !== 'idle') return null;
    const j = hitTest(e.clientX, e.clientY);
    return j === null ? null : { type: 'item', menuId: S.menuId, index: idxs[j] };
  }, e => {
    const m = curMenu(), it = m && m.items[idxs[hitTest(e.clientX, e.clientY)]];
    return it ? h('span', { class: 'ghost-chip' }, itemThumb(it, 22), itemLabel(it)) : h('span', null, '...');
  });
  window.addEventListener('zorbit-dnd', function onDnd() {
    if (!el.isConnected) { window.removeEventListener('zorbit-dnd', onDnd); return; }
    if (DnD.active) setHover(null);
    const p = DnD.active && DnD.active.payload, m = curMenu();
    const can = !!p && !!m && p.type === 'item' && p.menuId === S.menuId && !!m.items[p.index];      // library items cannot be deleted, only ring items
    el.classList.toggle('can-trash', can); trash.setAttribute('aria-hidden', can ? 'false' : 'true');
    if (!can) trash.classList.remove('over');
    paintMarks();
  });
  /* Where a drop at gap k lands in the item list; k === null (the dead zone) and the gap before slot 0 mean the end. */
  const itemIndexFor = k => { const m = curMenu(); if (!m) return 0; return k === null || k >= idxs.length ? m.items.length : idxs[k]; };
  const slotLabel = j => { const m = curMenu(), it = m && m.items[idxs[j]]; return it ? itemLabel(it) : ''; };
  // Dropping an item where it already is changes nothing: its own two gaps (before it, after it)
  const staysPut = (p, k) => { const j = p.type === 'item' ? idxs.indexOf(p.index) : -1; return j >= 0 && k !== null && (k === j || k === j + 1); };
  function gapText(p, k) {
    const n = idxs.length, move = p.type === 'item';
    if (staysPut(p, k)) return 'Stays in place';
    if (move && k === n && idxs.indexOf(p.index) === 0) return 'Move to the end';
    return n === 1 ? (move ? 'Move after ' : 'Insert after ') + slotLabel(0) : (move ? 'Move between ' : 'Insert between ') + slotLabel(k - 1) + ' and ' + slotLabel(k % n);
  }
  DnD.zone(el, {
    accept: p => !!curMenu() && (!!idxs.length ? (p.type === 'asset' || (p.type === 'item' && p.menuId === S.menuId)) : p.type === 'asset'),   // no menu: nothing to add to
    over: (p, x, y) => {
      const k = gapAt(x, y), noop = staysPut(p, k);
      if (k !== (gap ? gap.k : null) || (gap && gap.noop !== noop)) {
        gap = k === null ? null : { k, text: gapText(p, k), noop };
        paintMarks();
      }
      el.classList.add('drop-over'); el.classList.toggle('drop-end', k === null);
    },
    leave: () => { gap = null; paintMarks(); el.classList.remove('drop-over', 'drop-end'); },
    drop: (p, x, y) => {
      const k = gapAt(x, y), at = itemIndexFor(k);
      if (p.type === 'item') {
        if (!staysPut(p, k) && at !== p.index && at !== p.index + 1) moveItem(S.menuId, p.index, at);
        return;
      }
      insertAsset(S.menuId, p.kind, p.name, at);
    },
  });
  /* The trash: an item dropped here is deleted, with the same undo toast as the Delete key. As a child of the stage it is the nearer zone, so the ring's gap bar gives way to it. */
  DnD.zone(trash, {
    accept: p => p.type === 'item' && p.menuId === S.menuId,
    over: () => { if (!trash.classList.contains('over')) { trash.classList.add('over'); paintMarks(); } },
    leave: () => { trash.classList.remove('over'); paintMarks(); },
    drop: p => { delItem(p.index, p.menuId); },
  });
  new ResizeObserver(() => { if (haveImage || idxs.length) layout(); }).observe(el);

  return {
    el,
    playAnim: () => { if (idxs.length) player.play(S.menuId); },
    start() { refresh(); if (idxs.length) requestImage(); },
  };
}

/* ---------- item inspector */
function buildItemInspector() {
  const box = h('div', { class: 'insp' });
  const m = curMenu(), it = curItem();
  if (!m) return emptyState('menus', 'No menu selected', '');
  if (!it) {
    box.append(emptyState('k_press', 'No item selected', 'Click a slot in the ring or an item in the list to edit it.', m.items.length ? null : { text: 'Add item', fn: () => addItem('brush') }));
    return box;
  }
  const i = S.itemIdx, k = kindOf(it);
  box.append(h('div', { class: 'insp-head' }, itemThumb(it, 36), h('div', { class: 'insp-title' }, h('b', null, itemLabel(it)), h('span', null, `Item ${i + 1} of ${m.items.length}`)),
    h('div', { class: 'spacer' }), iconBtn('copy', 'Duplicate item', () => dupItem(i)), iconBtn('trash', 'Delete item', e => { if (e.detail > 1) return; delItem(i); selectItem(null); }, 'danger')));

  /* action type */
  const seg = h('div', { class: 'kinds', role: 'radiogroup', 'aria-label': 'Action type' }, Object.keys(KIND).map(kk =>
    h('button', { class: 'kind' + (kk === k ? ' on' : '') + ' k-' + kk, type: 'button', role: 'radio', 'aria-checked': kk === k ? 'true' : 'false', title: KIND[kk].hint,
      onclick: () => {
        if (kk === k) return;
        sealSnap();
        const r = convertItem(it, kk);
        m.items[i] = r.item; commit({ inspector: true });
        const t = $('[data-focus="target"]'); if (t && !t.value) t.focus();
        if (r.lost.length) undoToast(`Switched to ${KIND[kk].label}. Dropped ${joinList(r.lost)}.`, { ms: 6500 });
      } },
      icon(KIND[kk].icon, 18), h('span', null, KIND[kk].label))));
  box.append(field('Action', seg, KIND[k].hint + '.'));

  const hintEl = h('div', { class: 'fhint' });
  const labelInp = textInput(it.label || '', v => { if (v.trim()) it.label = v; else delete it.label; commit(); updateHead(); }, { placeholder: defaultLabel(it), label: 'Label' });
  const updateHead = () => { setText($('.insp-title b', box), itemLabel(it)); labelInp.placeholder = defaultLabel(it); };

  if (k === 'auto') {
    box.append(field('Right now', autoNow(m, i), 'The brush you pick most often from any ring, apart from the brushes this menu already has. Picks fade with a two-week half-life. A newcomer has to come out on top twice in a row before it takes a slot, and it takes the slot of a brush you have stopped using, so the rest of the ring stays put.'));
    return box;
  }
  if (k === 'tag' || k === 'browser') {
    box.append(tagTargetField(it, k, updateHead));
  } else if (k !== 'steps') {
    const placeholders = { ...Object.fromEntries(LIB_KINDS.map(lk => [lk, 'Search ' + K(lk).many + ', e.g. ' + K(lk).eg])), press: 'Item path, e.g. Tool:Masking:Clear', set: 'Item path, e.g. Draw:Draw Size', toggle: 'Item path, e.g. Transform:Activate Symmetry', menu: 'Pick a menu' };
    let touched = false;                                   // "required" hints wait until the field has been edited or left once
    let inp, openBtn = null;
    if (isLib(k)) ensureLib(k);                            // its load repaints this inspector (loadLibrary)
    if (k === 'menu') {
      // A pick list rather than free text: only real menus, never this one (a menu cannot open itself).
      const cur = String(it.menu ?? '');
      const others = Object.entries(S.cfg.menus).filter(([mid]) => mid !== S.menuId);
      const menuName = (mid, mm) => (mm.title && mm.title !== mid ? `${mm.title} (${mid})` : mid);
      const known = others.some(([mid]) => mid === cur);
      inp = h('select', { class: 'inp sel', 'aria-label': 'Submenu', dataset: { focus: 'target' }, onchange: () => { touched = true; it.menu = inp.value; commit(); updateHint(); updateHead(); } },
        h('option', { value: '', selected: !cur }, 'Pick a menu...'),
        others.map(([mid, mm]) => h('option', { value: mid, selected: mid === cur }, menuName(mid, mm))),
        cur && !known ? h('option', { value: cur, selected: true }, cur === S.menuId ? cur + ' (this menu)' : cur + ' (missing)') : null);
      inp.addEventListener('blur', () => { touched = true; updateHint(); });
      openBtn = iconBtn('chevR', 'Open this submenu', () => openSubmenu(it.menu, S.itemIdx));
    } else {
      inp = textInput(targetOf(it), v => { touched = true; it[k] = v.trim(); commit(); updateHint(); updateHead(); }, { mono: !isLib(k), placeholder: placeholders[k], focus: 'target', label: 'Target' });
      inp.addEventListener('change', () => { it[k] = inp.value.trim(); inp.value = it[k]; commit(); updateHint(); });
      inp.addEventListener('blur', () => { touched = true; updateHint(); });
      combo(inp, q => matchOpts(isLib(k) ? libOpts(k) : pathOpts(), q), { thumb: isLib(k) ? k : null, mono: !isLib(k) });
    }
    const tlabel = isLib(k) ? KIND[k].label : { press: 'Button path', set: 'Slider or value path', toggle: 'Switch path', menu: 'Submenu' }[k];
    const wrap = h('div', { class: 'target-row' }, isLib(k) ? h('span', { class: 'tthumb' }) : null, inp, openBtn);
    box.append(field(tlabel, wrap, hintEl));
    function updateHint() {
      const v = targetOf(it).trim(); hintEl.className = 'fhint'; hintEl.replaceChildren();
      if (!v && touched) { hintEl.classList.add('bad'); hintEl.append('A target is required. '); }
      if (isLib(k)) {
        const tt = $('.tthumb', wrap); if (tt) tt.replaceChildren(thumb(v || null, { size: 30, kind: k }));
        const L = lib(k), W = K(k);
        if (L.state === 'loading' || L.state === 'idle') hintEl.append('Reading your ' + W.one + ' library...');
        else if (v && L.state === 'ready' && L.items.length && !L.byName.has(nameKey(v))) { hintEl.classList.add('warn'); hintEl.append(`Not found in your ${W.one} library. ZBrush needs ${aOrAn(W.ext)} file with this name.`); }
        else if (!v) hintEl.append('Type to search your library.');
      } else if (k === 'menu') {
        const t = S.cfg.menus[v];
        if (openBtn) openBtn.disabled = !t || v === S.menuId;
        if (t) hintEl.append('Opens ', h('b', null, t.title || v), ` (${t.items.length} items). `, h('button', { class: 'link', type: 'button', onmousedown: e => e.preventDefault(), onclick: () => openSubmenu(v) }, 'Open it'));
        else {
          if (v) { hintEl.classList.add('bad'); hintEl.append('No menu with this id. '); }
          hintEl.append(h('button', { class: 'link', type: 'button', onmousedown: e => e.preventDefault(), onclick: () => {
            const nid = uniqueId(it.label || v || 'submenu'), keep = S.menuId, mi = S.itemIdx;
            S.cfg.menus[nid] = { title: it.label || (v ? v : 'Submenu'), items: [] };
            it.menu = nid; S.menuId = keep; S.itemIdx = mi; commit({ inspector: true }); toast('Created an empty submenu. Open it to add items.', { action: { text: 'Open', fn: () => { if (S.menuId === keep) openSubmenu(nid, mi); else selectMenu(nid); } } });
          } }, 'Create a new submenu'));
        }
      } else {
        const s = S.suggestions.find(x => x.path.replace(/\s/g, '').toLowerCase() === v.replace(/\s/g, '').toLowerCase());
        if (s) hintEl.append('Known item: ' + s.source);
        else if (!v) hintEl.append('Type to see suggestions from your hotkeys and plugins, or paste any ZBrush item path.');
        else hintEl.append('Custom path. ZBrush item paths ignore case.');
      }
    }
    updateHint();
    if (k === 'set') {
      let vTouched = false;
      const vhint = h('span', { class: 'vhint' });
      const paintVal = () => {
        const show = !validValue(it.value) && (vTouched || hasText(it.value));       // not on a fresh item until it was edited or left
        vhint.textContent = show ? (hasText(it.value) ? VALUE_HINT : 'A value is required. ' + VALUE_HINT) : '';
        if (vhint.parentElement) vhint.parentElement.classList.toggle('bad', show);
        val.classList.toggle('bad', show);
      };
      const val = textInput(it.value === undefined ? '' : String(it.value), v => { vTouched = true; it.value = parseValue(v); commit(); paintVal(); }, { mono: true, placeholder: 'e.g. 64 or 0.5', label: 'Value' });
      val.inputMode = 'decimal';
      val.addEventListener('blur', () => { vTouched = true; paintVal(); });
      box.append(field('Value', val, vhint));
      paintVal();
    }
  } else {
    box.append(field('Steps', buildSteps(it), 'Steps can select brushes, alphas, materials and textures, press buttons, set values and flip switches (no submenus).'));
  }

  const iconInp = textInput(it.icon || '', v => { if (v.trim()) it.icon = v.trim(); else delete it.icon; commit(); updateIcon(); }, { placeholder: 'Optional: brush name or path to a .png / .zbp', label: 'Icon override', mono: !!it.icon && isPath(it.icon) });
  combo(iconInp, q => matchOpts(libOpts('brush'), q), { thumb: 'brush' });
  const iconPrev = h('span', { class: 'tthumb' });
  function updateIcon() { const v = (it.icon || '').trim(); iconPrev.replaceChildren(v && !isPath(v) ? thumb(v, { size: 30 }) : h('span', { class: 'thumb glyph', style: { '--sz': '30px' } }, icon(v ? 'k_press' : 'k_brush', 15))); iconPrev.style.opacity = v ? '1' : '.45'; }
  updateIcon();
  box.append(sectionTitle('Appearance'),
    field('Label', labelInp, 'Shown under the icon. Leave empty to use the default.'),
    field('Icon', h('div', { class: 'target-row' }, iconPrev, iconInp), isLib(k)
      ? `By default the icon comes from the ${K(k).one}. Use a brush name or a full path to a .png or .zbp to override it.`
      : 'Use a brush name or a full path to a .png or .zbp as the icon.'));
  return box;
}

/* The brush the app puts into auto slot i of menu m at the moment (read from usage.json). */
function autoNow(m, i) {
  const el = h('div', { class: 'target-row' }, h('span', { class: 'fhint' }, 'Loading...'));
  const j = m.items.slice(0, i).filter(x => kindOf(x) === 'auto' && itemUsable(x)).length;
  call('get_auto_slots', S.cfg, S.menuId).then(r => {
    const name = r && r.slots ? r.slots[j] : null;
    el.replaceChildren(...(name ? [thumb(name, { size: 30 }), h('b', null, name)]
      : [h('span', { class: 'fhint' }, 'Empty. It fills when you pick a brush from any ring that this menu does not have.')]));
  }).catch(() => el.replaceChildren(h('span', { class: 'fhint' }, 'Could not read your brush usage.')));
  return el;
}

const STEP_KINDS = ['brush', 'alpha', 'material', 'texture', 'press', 'set', 'toggle'];
function buildSteps(it) {
  const host = h('div', { class: 'steps' });
  const render = () => {
    host.replaceChildren();
    if (!Array.isArray(it.steps)) it.steps = [];
    it.steps.forEach((st, j) => {
      const sk = kindOf(st);
      const sel = h('select', { class: 'inp sel', 'aria-label': 'Step ' + (j + 1) + ' type', onchange: () => {
        const nk = sel.value, was = targetOf(st), keep = nsOf(nk) === nsOf(sk) ? was : '', lost = [];
        if (hasText(was) && !hasText(keep)) lost.push(`the ${TARGET_NOUN[sk]} "${was.trim()}"`);
        if (sk === 'set' && nk !== 'set' && hasText(st.value)) lost.push(`the value ${st.value}`);
        sealSnap();
        it.steps[j] = makeItem(nk, keep); commit({ inspector: false }); render();
        if (lost.length) undoToast(`Step ${j + 1} is now ${KIND[nk].label}. Dropped ${joinList(lost)}.`, { ms: 6500 });
      } },
        STEP_KINDS.map(x => h('option', { value: x, selected: x === sk }, KIND[x].label)));
      const tin = textInput(targetOf(st), v => { st[sk] = v; commit(); }, { mono: !isLib(sk), placeholder: isLib(sk) ? KIND[sk].label + ' name' : 'Item path', label: 'Step ' + (j + 1) + ' target' });
      tin.addEventListener('change', () => { st[sk] = tin.value.trim(); tin.value = st[sk]; commit(); });
      tin.classList.add('stgt');
      if (isLib(sk)) ensureLib(sk);
      combo(tin, q => matchOpts(isLib(sk) ? libOpts(sk) : pathOpts(), q), { thumb: isLib(sk) ? sk : null, mono: !isLib(sk) });
      const vhint = h('div', { class: 'fhint bad svhint', hidden: true });
      const row = h('div', { class: 'step' }, h('span', { class: 'snum mono' }, String(j + 1)), sel, tin,
        sk === 'set' ? (() => {
          let vTouched = false;
          const paint = () => {
            const show = !validValue(st.value) && (vTouched || hasText(st.value));
            vhint.textContent = show ? (hasText(st.value) ? VALUE_HINT : 'A value is required. ' + VALUE_HINT) : ''; vhint.hidden = !show; v.classList.toggle('bad', show);
          };
          const v = textInput(st.value === undefined ? '' : String(st.value), x => { vTouched = true; st.value = parseValue(x); commit(); paint(); }, { mono: true, placeholder: 'value', label: 'Step value' });
          v.classList.add('vin'); v.addEventListener('blur', () => { vTouched = true; paint(); });
          paint(); return v;
        })() : null,
        sk === 'set' ? vhint : null,
        h('span', { class: 'sacts' },
          iconBtn('up', 'Move step up', () => { if (j > 0) { [it.steps[j - 1], it.steps[j]] = [it.steps[j], it.steps[j - 1]]; commit(); render(); } }),
          iconBtn('down', 'Move step down', () => { if (j < it.steps.length - 1) { [it.steps[j + 1], it.steps[j]] = [it.steps[j], it.steps[j + 1]]; commit(); render(); } }),
          iconBtn('trash', 'Remove step', e => { if (e.detail > 1) return; it.steps.splice(j, 1); commit(); render(); }, 'danger')));
      host.append(row);
    });
    if (!it.steps.length) host.append(h('div', { class: 'fhint bad' }, 'Add at least one step.'));
    host.append(h('div', { class: 'step-add' }, h('span', { class: 'micro' }, 'Add'), STEP_KINDS.map(x =>
      h('button', { class: 'btn small', type: 'button', onclick: () => { it.steps.push(makeItem(x, '')); commit(); render(); const ins = $$('.step .inp.mono, .step input', host); const last = $$('.step', host).pop(); if (last) $$('input', last)[0].focus(); } }, icon(KIND[x].icon, 12), KIND[x].label))));
  };
  render();
  return host;
}

/* ---------- menu properties */
function buildMenuProps() {
  const m = curMenu(), id = S.menuId;
  const box = h('div', { class: 'insp' });
  if (!m) return emptyState('menus', 'No menu selected', '');
  const titleInp = textInput(m.title || '', v => { m.title = v; commit(); if (R.head) R.head(); }, { placeholder: id, label: 'Menu title' });
  box.append(sectionTitle('Menu', 'Shown in the list and at the ring centre'), field('Title', titleInp));
  const idErr = h('div', { class: 'fhint bad id-err', role: 'alert', hidden: true });
  const idInp = textInput(id, () => {}, { mono: true, label: 'Menu id' });
  let idTimer = null;
  const idShow = msg => { clearTimeout(idTimer); idTimer = null; idErr.textContent = msg || ''; idErr.hidden = !msg; idInp.classList.toggle('bad', !!msg); };
  idInp.addEventListener('input', () => idShow(menuIdProblem(id, idInp.value)));          // live: red as soon as it is wrong, clear as soon as it is right
  const idCommit = () => {
    const bad = renameMenuId(id, idInp.value);                                             // null: renamed (the panel is rebuilt) or unchanged
    if (!bad) { idShow(''); if (idInp.value !== id && idInp.isConnected) idInp.value = id; return; }
    idInp.value = id; idShow(bad); idInp.classList.remove('bad');                          // back to the old id; the reason stays for a moment
    idTimer = setTimeout(() => idShow(''), 3000);
  };
  idInp.addEventListener('change', idCommit);
  idInp.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); idInp.value = id; idShow(''); } });
  const idNotes = [h('div', { class: 'fhint' }, 'Used to link submenus. Renaming updates the items that open this menu.')];
  if (m.items.some(x => kindOf(x) === 'auto')) idNotes.push(h('div', { class: 'fhint' }, 'Renaming resets the learned auto slots for this menu.'));
  box.append(field('Id', idInp, h('div', { class: 'id-notes' }, idErr, ...idNotes)));

  const owner0 = m.hotkey ? hotkeyOwner(m.hotkey, id) : null;
  const hk = hotkeyField({ what: 'Hotkey for this menu', value: m.hotkey || '', placeholder: 'No hotkey (submenu only)', onChange: str => {
    if (str) m.hotkey = str; else delete m.hotkey;
    const owner = str ? hotkeyOwner(str, id) : null;
    if (owner) hk.say(`Also used by ${ownerName(owner)}. Only one of them will open.`, 'warn');
    commit(); if (R.head) R.head();
  } });
  box.append(field('Hotkey', hk, m.hotkey ? 'Hold or tap this key in ZBrush to open the ring. Click the field and press a combination to change it.' : 'Without a hotkey this menu can only be opened as a submenu from another menu.'));
  if (owner0) hk.say(`Also used by ${ownerName(owner0)}. Only one of them will open.`, 'warn');

  box.append(h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Swallow hotkey'),
    h('div', { class: 'fhint' }, 'Hides the key from ZBrush while the ring is in use, so it does not also trigger ZBrush\'s own shortcut for that key. Turn off if you want the key to keep working in ZBrush too.')),
    toggleSwitch(m.swallow !== false, v => { if (v) delete m.swallow; else m.swallow = false; commit(); }, 'Swallow hotkey')));

  const refs = referrers(id);
  box.append(sectionTitle('Used by'), refs.length
    ? h('div', { class: 'refs' }, refs.map(r => h('button', { class: 'chip cyan', type: 'button', title: 'Go to this item', onclick: () => { selectMenu(r.menuId); selectItem(r.index); } },
      icon('k_menu', 12), (S.cfg.menus[r.menuId].title || r.menuId) + ' / ' + (r.index + 1))))
    : h('div', { class: 'fhint' }, m.hotkey ? 'Opened from ZBrush by its hotkey.' : 'Nothing opens this menu yet. Add a Submenu item in another menu that points to it.'));

  const anims = (S.opts && S.opts.animations) || Object.keys(ANIM_INFO);
  const animTitle = a => a[0].toUpperCase() + a.slice(1);
  const ringAnim = () => ring().animation || S.defaults.animation;
  const animHint = h('div', { class: 'fhint' });
  const paintAnimHint = () => setText(animHint, m.animation
    ? (ANIM_INFO[m.animation] || '') + ' Only this menu opens this way; the others use ' + animTitle(ringAnim()) + ' from Settings.'
    : 'Uses the open animation set in Settings (' + animTitle(ringAnim()) + '). Pick one to give this menu its own.');
  const animSel = h('select', { class: 'inp sel', 'aria-label': 'Open animation for this menu', onchange: () => {
    if (animSel.value) m.animation = animSel.value; else delete m.animation;
    paintAnimHint(); commit();
    previewSoon.flush();                       // the debounced preview would stop the player a moment after it started
    if (R.playAnim) R.playAnim();
  } }, h('option', { value: '', selected: !m.animation }, 'Same as Settings (' + animTitle(ringAnim()) + ')'),
    anims.map(a => h('option', { value: a, selected: m.animation === a }, animTitle(a))));
  paintAnimHint();
  box.append(sectionTitle('Open animation'), h('div', { class: 'field' }, animSel, animHint), h('div', { class: 'btn-row' },
    h('button', { class: 'btn', type: 'button', onclick: () => R.playAnim && R.playAnim() }, icon('play', 13), 'Preview animation')));
  box.append(sectionTitle('As a submenu'), h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Fan out when opened from another menu'),
    h('div', { class: 'fhint' }, 'Instead of a new ring, the items spread out around this menu\'s slot and the ring stays in view.' + (m.hotkey ? ' This only applies when it is opened as a submenu; its hotkey still opens a ring.' : ''))),
    toggleSwitch(m.fan === true, v => { if (v) m.fan = true; else delete m.fan; commit(); }, 'Fan out when opened from another menu')));
  box.append(sectionTitle('Manage'), h('div', { class: 'btn-row' },
    h('button', { class: 'btn', type: 'button', onclick: () => dupMenu(id) }, icon('copy', 13), 'Duplicate'),
    h('button', { class: 'btn danger-o', type: 'button', onclick: () => deleteMenu(id) }, icon('trash', 13), 'Delete menu')));
  return box;
}

/* ================================================================== tags */
/* Tags live in tags.json and the backend writes it as they change, so they are not part of Save, Revert or undo.
   S.tags / S.tagMap / S.itemTags mirror the last snapshot any tag call returned (see webapi.TagApi). */
const TAG_PALETTE_FALLBACK = ['#F86B33', '#4DC8E9', '#A8DF23', '#E8413C', '#C77DFF', '#FFD166', '#5EEAD4', '#F472B6'];
const browsers = new Map();            // browser state object (S.lib, S.dock) -> its live browser, so a tag change can repaint it
let tagMgr = null, tagPick = null;     // repaint hooks of the open tag manager and tag picker
const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : /(s|sh|ch|x)$/.test(w) ? 'es' : 's');

const tagsOf = (kind, name) => { const l = S.itemTags[tagKey(kind, name)]; return l ? l.filter(k => S.tagMap.has(k)) : []; };
const isFav = (kind, name) => tagsOf(kind, name).includes(FAV);
/* An asset's colour cue: its first tag other than Favourites (null when it has none). Favourites shows as a star instead. */
const firstTag = (kind, name) => { const k = tagsOf(kind, name).find(x => x !== FAV); return k ? S.tagMap.get(k) : null; };
/* The tags in the order lists show them: Favourites first, then the others as the backend sends them. */
const tagsFavFirst = () => S.tags.filter(t => t.key === FAV).concat(S.tags.filter(t => t.key !== FAV));
/* The colour dot of an asset's first tag (null when it has none), for the item list. */
function tagDot(kind, name) {
  const t = firstTag(kind, name);
  return t ? h('i', { class: 'tdot', style: { '--tag': t.color }, title: 'Tag: ' + t.label }) : null;
}
/* The gold star that stands in for the dot on Favourites (chips, the picker, the item list); its colour is the tag's (--fav, see applyTagSnapshot). */
const starGlyph = (size = 11) => h('i', { class: 'tdot star', 'aria-hidden': 'true' }, icon('star', size));
/* The tag a Tag or Browser item points at (null for other kinds, an empty filter or an unknown key), and its colour dot. */
const keyTag = it => { const key = it && (('tag' in it) ? it.tag : ('browser' in it) ? it.browser : ''); return key ? S.tagMap.get(key) || null : null; };
const keyDot = t => t.key === FAV ? h('i', { class: 'tdot star', title: 'Tag: ' + t.label }, icon('star', 11)) : h('i', { class: 'tdot', style: { '--tag': t.color }, title: 'Tag: ' + t.label });
/* How many items (of any kind) a tag has to show: the installed ones once every library is read, else what tags.json says.
   A kind whose library is not loaded yet has an unknown count, so a partial sum would undercount: until all four are
   loaded the answer is tags.json's total (it covers every kind, installed or not). */
function tagItemCount(key) {
  if (!S.tagMap.has(key)) return 0;
  if (LIB_KINDS.every(k => lib(k).state === 'ready')) return LIB_KINDS.reduce((n, k) => n + (tagCounts(k).byKey.get(key) || 0), 0);
  return S.tagMap.get(key).count || 0;
}
let tagField = null;                   // repaint hook of the tag picker in the item inspector

/* The Tag / Browser target in the item inspector: a list of the current tags with a dot for the colour of the chosen one
   (an <option> cannot be styled). A key that is not in tags.json is kept and shown as unknown rather than silently replaced. */
function tagTargetField(it, k, updateHead) {
  const isTag = k === 'tag';
  let touched = false;
  const dot = h('i', { class: 'tdot tt-dot none', 'aria-hidden': 'true' });
  const hint = h('div', { class: 'fhint' });
  const sel = h('select', { class: 'inp sel', 'aria-label': isTag ? 'Tag' : 'Tag filter', dataset: { focus: 'target' },
    onchange: () => { touched = true; it[k] = sel.value; commit(); paint(); updateHead(); } });
  sel.addEventListener('blur', () => { touched = true; paintHint(); });
  const paintHint = () => {
    const cur = String(it[k] ?? ''), t = S.tagMap.get(cur), n = tagItemCount(cur);
    hint.className = 'fhint'; hint.replaceChildren();
    if (cur && !t && S.tagsLoaded) {
      hint.classList.add('warn');
      hint.append(isTag ? 'This tag no longer exists; the slot stays empty until you pick another. ' : 'This tag no longer exists; the browser opens unfiltered. ');
    } else if (isTag && !cur) {
      if (touched) hint.classList.add('bad');
      hint.append('Pick a tag. ');
    } else if (isTag) {
      if (t && !n) { hint.classList.add('warn'); hint.append('No item has this tag yet; the slot stays empty until one does. '); }
      else hint.append('Opens a submenu of ', h('b', null, plural(n, 'item')), ': brushes first (most used first), then alphas, materials and textures. ');
    } else hint.append(t ? `Opens the browser on ${K(it.kind).tab}, filtered to this tag. ` : `Opens the browser on ${K(it.kind).tab} with every ${K(it.kind).one}. Pick a tag to filter it. `);
    hint.append(h('button', { class: 'link', type: 'button', onmousedown: e => e.preventDefault(), onclick: () => openTagManager() }, 'Manage tags...'));
  };
  const paint = () => {
    const cur = String(it[k] ?? ''), t = S.tagMap.get(cur), opts = [];
    if (!isTag) opts.push(h('option', { value: '' }, 'All ' + K(it.kind).many));
    else if (!cur) opts.push(h('option', { value: '' }, 'Pick a tag...'));
    if (cur && !t) opts.unshift(h('option', { value: cur }, S.tagsLoaded ? `Unknown tag '${cur}'` : cur));
    for (const x of tagsFavFirst()) opts.push(h('option', { value: x.key }, `${x.label} (${plural(x.count || 0, 'item')})`));
    sel.replaceChildren(...opts);
    sel.value = cur;
    const star = !!t && t.key === FAV;                      // Favourites shows a star in place of the dot
    dot.classList.toggle('none', !t);
    dot.classList.toggle('star', star);
    dot.replaceChildren(...(star ? [icon('star', 13)] : []));
    if (t) dot.style.setProperty('--tag', t.color); else dot.style.removeProperty('--tag');
    paintHint();
  };
  if (isTag) LIB_KINDS.forEach(ensureLib);                // tagItemCount is exact once every library is read (loadLibrary repaints this field)
  paint();
  tagField = { sel, paint };
  const tagRow = field(isTag ? 'Tag' : 'Tag filter', h('div', { class: 'target-row' }, dot, sel), hint);
  if (isTag) return tagRow;
  // A Browser slot also says which tab the browser opens on (item.kind; absent means brushes).
  const kindSel = h('select', { class: 'inp sel', 'aria-label': 'Browser tab', onchange: () => {
    const v = kindSel.value;
    if (v === 'brush') delete it.kind; else it.kind = v;
    commit(); paint(); updateHead();
  } }, LIB_KINDS.map(lk => h('option', { value: lk, selected: lk === (it.kind || 'brush') }, KINDS[lk].tab)));
  kindSel.value = it.kind || 'brush';
  const frag = document.createDocumentFragment();
  frag.append(tagRow, field('Shows', kindSel, 'Which tab the browser opens on.'));
  return frag;
}

/* How many installed items of one kind each tag is on, and how many carry none (the sidebar's counts). */
function tagCounts(kind) {
  const L = lib(kind), c = L._tc;
  if (c && c.items === S.itemTags && c.map === S.tagMap && c.src === L.items) return c;
  const byKey = new Map();
  let untagged = 0;
  for (const b of L.items) {
    const ks = tagsOf(kind, b.name);
    if (!ks.some(k => k !== FAV)) untagged++;              // "Untagged" means no ordinary tag: an item with only Favourites counts
    for (const k of ks) byKey.set(k, (byKey.get(k) || 0) + 1);
  }
  return (L._tc = { byKey, untagged, items: S.itemTags, map: S.tagMap, src: L.items });
}
/* How many ring items point at a tag ({"tag": key}). */
function tagRingUses(key) {
  let n = 0;
  for (const m of Object.values(S.cfg.menus)) for (const it of (m.items || [])) if (it && (it.tag === key || it.browser === key)) n++;
  return n;
}

/* Takes a get_tags answer or a changing call's answer. A changing call reports its own failure in `error`, which is not a
   problem with the file, so only get_tags answers (mutated = false) set S.tagsErr. Returns true when anything on screen changed. */
function applyTagSnapshot(res, mutated = false) {
  if (!res || typeof res !== 'object') return false;
  if (res.unchanged) { S.tagMtime = res.mtime_ns; return false; }
  if (!Array.isArray(res.tags)) return false;
  // Answers can land out of order (two picker clicks, a focus reload over a write): an older file state never replaces a newer one.
  if (S.tagsLoaded && typeof res.mtime_ns === 'number' && typeof S.tagMtime === 'number' && res.mtime_ns < S.tagMtime - 1000) return false;
  const err = mutated ? (res.ok ? '' : S.tagsErr) : (res.error ? String(res.error) : '');
  const sig = JSON.stringify([res.tags, res.items || {}]);
  const changed = !S.tagsLoaded || sig !== S._tagSig || err !== S.tagsErr;
  if (err && err !== S.tagsErr) toast(err, { tone: 'warn', ms: 5000 });
  S.tags = res.tags; S.tagMap = new Map(res.tags.map(t => [t.key, t]));
  S.itemTags = res.items && typeof res.items === 'object' ? res.items : {};
  const favTag = S.tagMap.get(FAV);                         // the star's colour follows the Favourites tag (its colour can be changed)
  if (favTag && /^#[0-9a-f]{6}$/i.test(favTag.color || '')) document.documentElement.style.setProperty('--fav', favTag.color);
  else document.documentElement.style.removeProperty('--fav');
  if (Array.isArray(res.palette) && res.palette.length) S.palette = res.palette;
  if (res.path) S.tagsPath = String(res.path);
  S.tagMtime = res.mtime_ns === undefined ? S.tagMtime : res.mtime_ns;
  S.tagsErr = err; S._tagSig = sig; S.tagsLoaded = true;
  if (changed) tagsChanged();
  return changed;
}
async function loadTags(force = false) {
  let res = null;
  try { res = await call('get_tags', force ? null : S.tagMtime); } catch (e) { res = null; }
  applyTagSnapshot(res);
}
/* Every tag change goes through here: the answer carries the fresh snapshot, a refusal is toasted. A name that clashes
   (res.exists) is left to the caller, which can offer to use or merge into the other tag. */
async function tagCall(name, ...args) {
  let res;
  try { res = await call(name, ...args); } catch (e) { res = { ok: false, error: 'Could not save the tags: ' + ((e && e.message) || e) }; }
  if (!res || typeof res !== 'object') res = { ok: false, error: 'Could not save the tags.' };
  applyTagSnapshot(res, true);
  if (!res.ok && !res.exists) toast(res.error || 'That tag change did not work.', { tone: 'warn', ms: 4500 });
  return res;
}
function tagsChanged() {
  for (const el of $$('.tag-path')) { setText(el, S.tagsPath); el.hidden = !S.tagsPath; }
  for (const b of browsers.values()) b.updateTags();
  if (R.itemList) R.itemList();
  if (R.libTarget) R.libTarget();
  if (tagMgr) tagMgr.paint();
  if (tagPick) tagPick.paint();
  if (tagField) { if (tagField.sel.isConnected) tagField.paint(); else tagField = null; }
  if (R.overlay) R.overlay();                          // a tag slot may now have (or no longer have) a fan to show
  RingLoader.cache.clear(); RingLoader.gen++;          // tags are not part of S.version: forget cached and in-flight previews
  FrameLoader.cache.clear(); FrameLoader.gen++;
  previewSoon();
}

/* A popover for tagging items of one kind: one checkable row per tag (ticked when all of them carry it, a dash when some do),
   and a field that makes a new tag and puts it on them. `at` is the pointer position for a right-click. `extras` are more rows
   under the tags, each { icon, label, fn } (the Recent folder adds "Remove from Recent"); a click closes the picker, then runs fn. */
function tagPicker(anchor, kind, names, at = null, extras = null) {
  if (!names.length) return;
  if (openPopover) { const same = openPopover.anchor === anchor; openPopover(); if (same && !at) return; }
  const keys = names.map(n => tagKey(kind, n));
  const list = h('div', { class: 'tp-list', role: 'group', 'aria-label': 'Tags' });
  const input = h('input', { class: 'inp tp-new', type: 'text', maxlength: 40, placeholder: 'New tag...', 'aria-label': 'New tag name', spellcheck: 'false', autocomplete: 'off' });
  const title = names.length === 1 ? names[0] : names.length + ' ' + K(kind).many;
  const pop = h('div', { class: 'popover tagpick', role: 'dialog', 'aria-label': 'Tags for ' + title },
    h('div', { class: 'tp-head' }, icon('tag', 13), h('b', null, title)), list, h('div', { class: 'tp-add' }, input));
  const stateOf = t => {
    const n = names.filter(nm => tagsOf(kind, nm).includes(t.key)).length;
    return n === 0 ? 'none' : n === names.length ? 'all' : 'some';
  };
  const row = t => {
    const st = stateOf(t);
    return h('button', { class: 'tp-row' + (st === 'all' ? ' on' : ''), type: 'button', role: 'menuitemcheckbox', 'aria-checked': st === 'all' ? 'true' : st === 'some' ? 'mixed' : 'false', dataset: { k: t.key },
      onclick: () => tagCall('tag_items', keys, st === 'all' ? [] : [t.key], st === 'all' ? [t.key] : []) },
      h('span', { class: 'tcheck' }, st === 'all' ? icon('check', 11) : st === 'some' ? h('i', { class: 'tdash' }) : null),
      t.key === FAV ? starGlyph(13) : h('i', { class: 'tdot', style: { '--tag': t.color } }), h('span', { class: 'tc-name' }, t.label), h('span', { class: 'tc-n mono' }, String(t.count)));
  };
  const extraRow = (x, i) => h('button', { class: 'tp-row tp-extra', type: 'button', role: 'menuitem', dataset: { k: '@x' + i }, onclick: () => { close(); x.fn(); } },
    h('span', { class: 'tcheck none' }, icon(x.icon, 12)), h('span', { class: 'tc-name' }, x.label));
  const paint = () => {
    const act = document.activeElement, fk = act && list.contains(act) ? act.dataset.k : null;
    list.replaceChildren(...(S.tags.length ? tagsFavFirst().map(row) : [h('div', { class: 'tp-empty fhint' }, 'No tags yet. Type a name below to make one.')]), ...(extras || []).map(extraRow));
    if (fk) { const r = $$('.tp-row', list).find(x => x.dataset.k === fk); if (r) r.focus(); }
  };
  input.addEventListener('keydown', async e => {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    const v = input.value.trim();
    if (!v || input.disabled) return;
    input.disabled = true;
    const r = await tagCall('create_tag', v);
    input.disabled = false;
    const key = r.ok ? r.key : r.exists;                       // the name of a tag that exists just puts that tag on them
    if (key) {
      input.value = '';
      await tagCall('tag_items', keys, [key], []);
    }
    if (document.contains(input)) input.focus();
  });
  document.body.append(pop);
  paint();
  const r = anchor.getBoundingClientRect();
  const x = at ? at.x : r.left, y = at ? at.y : r.bottom + 6;
  pop.style.left = clamp(x, 8, Math.max(8, innerWidth - pop.offsetWidth - 8)) + 'px';
  const room = innerHeight - y - 8;
  pop.style.top = (pop.offsetHeight <= room || at ? Math.max(8, Math.min(y, innerHeight - pop.offsetHeight - 8)) : Math.max(8, r.top - pop.offsetHeight - 6)) + 'px';
  requestAnimationFrame(() => pop.classList.add('in'));
  const onDown = e => { if (!pop.contains(e.target) && !anchor.contains(e.target)) close(); };
  const onKey = e => {
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
    const items = $$('.tp-row', pop).concat([input]), i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    else if (e.key === 'Home' && e.target !== input) { e.preventDefault(); items[0].focus(); }
    else if (e.key === 'End' && e.target !== input) { e.preventDefault(); items[items.length - 1].focus(); }
  };
  function close() {
    const had = pop.contains(document.activeElement);
    pop.remove(); document.removeEventListener('mousedown', onDown, true); document.removeEventListener('keydown', onKey, true);
    if (openPopover === close) openPopover = null;
    if (tagPick === me) tagPick = null;
    if (had && document.contains(anchor)) anchor.focus();
  }
  close.anchor = anchor;
  const me = { paint };
  tagPick = me;
  document.addEventListener('mousedown', onDown, true);
  document.addEventListener('keydown', onKey, true);
  openPopover = close;
  (S.tags.length ? $('.tp-row', pop) : input).focus();
}

/* The tag manager: rename, recolour, merge and delete tags, and make new ones. Every change is saved at once. */
function openTagManager() {
  const list = h('div', { class: 'tm-list' });
  const empty = h('div', { class: 'tm-empty fhint' }, 'No tags yet. Add one below, or select items in the Library and press Tag.');
  const warn = h('div', { class: 'fhint bad tm-warn', role: 'alert', hidden: true });
  const say = h('div', { class: 'fhint tm-say', role: 'status' });
  const rows = new Map();
  const newInp = h('input', { class: 'inp tm-new', type: 'text', maxlength: 40, placeholder: 'New tag name', 'aria-label': 'New tag name', spellcheck: 'false', autocomplete: 'off' });
  const addTag = async () => {
    const v = newInp.value.trim();
    if (!v || newInp.disabled) return;
    newInp.disabled = true;
    const r = await tagCall('create_tag', v);
    newInp.disabled = false;
    if (r.ok) {
      newInp.value = ''; say.textContent = '';
      const el = rows.get(r.key);
      if (el) el.scrollIntoView({ block: 'nearest' });
    } else if (r.exists) say.textContent = r.error || 'That tag already exists.';
    else say.textContent = '';
    newInp.focus();
  };
  newInp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } });
  newInp.addEventListener('input', () => { say.textContent = ''; });

  const makeRow = t0 => {
    let tag = t0;
    const sw = h('button', { class: 'tm-sw', type: 'button', 'aria-expanded': 'false' });
    const inp = h('input', { class: 'inp tm-label', type: 'text', maxlength: 40, spellcheck: 'false', autocomplete: 'off' });
    const n = h('span', { class: 'tm-n mono' });
    const del = h('button', { class: 'ibtn danger', type: 'button', onclick: () => remove() }, icon('trash', 15));
    const msg = h('div', { class: 'tm-msg fhint', role: 'status', hidden: true });
    const pal = h('div', { class: 'tm-pal', hidden: true });
    const hex = h('input', { class: 'inp mono tm-hex', type: 'text', maxlength: 7, placeholder: '#RRGGBB', spellcheck: 'false', autocomplete: 'off' });
    const setColor = async c => { if (c.toLowerCase() === tag.color.toLowerCase()) return; await tagCall('recolor_tag', tag.key, c.toUpperCase()); };
    hex.addEventListener('change', () => {
      const c = normHex(hex.value);
      if (!c) { hex.classList.add('bad'); return; }
      hex.classList.remove('bad'); setColor(c);
    });
    hex.addEventListener('input', () => hex.classList.remove('bad'));
    const swatches = () => (S.palette || TAG_PALETTE_FALLBACK).map(c => h('button', { class: 'tm-pc', type: 'button', style: { '--tag': c }, title: c, 'aria-label': 'Colour ' + c, 'aria-pressed': c.toLowerCase() === tag.color.toLowerCase() ? 'true' : 'false', onclick: () => setColor(c) }));
    sw.addEventListener('click', () => { const open = pal.hidden; pal.hidden = !open; sw.setAttribute('aria-expanded', open ? 'true' : 'false'); });
    pal.append(h('div', { class: 'tm-pcs' }), hex);
    inp.addEventListener('change', async () => {
      const v = inp.value.trim();
      msg.hidden = true;
      if (v === tag.label) { inp.value = tag.label; return; }
      const r = await tagCall('rename_tag', tag.key, v);
      if (r.ok) return;
      inp.value = tag.label;
      const other = r.exists && S.tagMap.get(r.exists);
      if (other) {
        msg.replaceChildren('A tag called "' + other.label + '" already exists. ',
          h('button', { class: 'link', type: 'button', onclick: async () => {
            const m = await tagCall('merge_tags', tag.key, other.key);
            if (m.ok) toast('Merged "' + tag.label + '" into "' + other.label + '"', { tone: 'ok', ms: 2600 });
          } }, 'Merge into ' + other.label),
          ' or ', h('button', { class: 'link', type: 'button', onclick: () => { msg.hidden = true; inp.focus(); } }, 'keep them separate'), '.');
        msg.hidden = false;
      }
    });
    const remove = async () => {
      const uses = tagRingUses(tag.key);
      const text = (tag.count ? 'It is on ' + plural(tag.count, 'item') + (uses ? ', used by ' + plural(uses, 'ring item') : '') : 'It is not on any item' + (uses ? ', but ' + plural(uses, 'ring item') + (uses === 1 ? ' uses' : ' use') + ' it' : '')) + '. The items keep working.' + (POPOUT ? ' Ring slots that use it stay empty until you pick another tag.' : '');
      const ok = await modal({ title: 'Delete tag "' + tag.label + '"?', body: h('p', null, text),
        actions: [{ text: 'Cancel', value: false, focus: true }, { text: 'Delete tag', value: true, kind: 'danger' }] });
      if (ok) await tagCall('delete_tag', tag.key);
      openTagManager();                                   // the confirm replaced this dialog: bring it back
    };
    const gap = h('span', { class: 'tm-gap', 'aria-hidden': 'true' });       // where a built-in tag's delete button would be
    const el = h('div', { class: 'tm-row', dataset: { key: tag.key } }, h('div', { class: 'tm-line' }, sw, inp, n, del, gap), pal, msg);
    el._update = t => {
      tag = t;
      const fixed = t.builtin === true || t.key === FAV;                      // Favourites: the colour can change, the name and the tag cannot
      inp.readOnly = fixed; del.hidden = fixed; gap.hidden = !fixed;
      el.classList.toggle('builtin', fixed);
      inp.title = fixed ? t.label + ' is built in: it cannot be renamed or deleted.' : '';
      sw.style.setProperty('--tag', t.color);
      sw.title = 'Colour of ' + t.label + ': ' + t.color + '. Click to change it.';
      sw.setAttribute('aria-label', 'Colour of ' + t.label + ', ' + t.color);
      if (document.activeElement !== inp) inp.value = t.label;
      inp.setAttribute('aria-label', 'Name of the tag ' + t.label);
      setText(n, plural(t.count, 'item'));
      del.title = 'Delete ' + t.label; del.setAttribute('aria-label', 'Delete the tag ' + t.label);
      $('.tm-pcs', pal).replaceChildren(...swatches());
      if (document.activeElement !== hex) hex.value = t.color.toUpperCase();
    };
    el._update(t0);
    return el;
  };
  const paint = () => {
    warn.hidden = !S.tagsErr; setText(warn, S.tagsErr || '');
    for (const [k, el] of rows) if (!S.tagMap.has(k)) { el.remove(); rows.delete(k); }
    const want = tagsFavFirst().map(t => {
      let el = rows.get(t.key);
      if (!el) { el = makeRow(t); rows.set(t.key, el); } else el._update(t);
      return el;
    });
    empty.hidden = want.length > 0;
    const have = Array.from(list.children);
    if (want.length !== have.length || want.some((el, i) => el !== have[i])) list.replaceChildren(...want);
  };
  const me = { paint };
  tagMgr = me;
  paint();
  const body = h('div', { class: 'tagmgr' },
    h('p', { class: 'fhint' }, 'Tags group your brushes, alphas, materials and textures. An item can carry several; the first one is its colour. Favourites is built in and shows as a star instead. Tags save as you go; they are not part of Save or Undo.'),
    warn, empty, list,
    h('div', { class: 'tm-add' }, newInp, h('button', { class: 'btn small', type: 'button', onclick: addTag }, icon('plus', 13), 'Add')), say);
  return modal({ title: 'Tags', body, actions: [{ text: 'Done', value: true, kind: 'primary', focus: true }] }).then(() => { if (tagMgr === me) tagMgr = null; });
}
const manageTagsBtn = (cls = 'btn small') => h('button', { class: cls, type: 'button', onclick: () => openTagManager() }, icon('tag', 13), 'Manage tags...');

/* ================================================================== browser (Library screen + Menus dock + popout) */
/* One tab per kind of asset. get() is the kind on show, set(kind) switches to another; paint() follows a change made elsewhere.
   Left and Right move between the tabs (and switch, as the tab bar of a tab list does). */
function kindTabs(get, set, cls = '') {
  const btns = new Map(LIB_KINDS.map(k => [k, h('button', { class: 'ktab', type: 'button', role: 'tab', dataset: { kind: k }, onclick: () => set(k) }, KINDS[k].tab)]));
  const el = h('div', { class: 'ktabs' + (cls ? ' ' + cls : ''), role: 'tablist', 'aria-label': 'Library' }, Array.from(btns.values()));
  const paint = () => {
    const cur = get();
    for (const [k, b] of btns) { const on = k === cur; b.classList.toggle('on', on); b.setAttribute('aria-selected', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1; }
  };
  el.addEventListener('keydown', e => {
    if ((e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
    const n = LIB_KINDS.length, to = LIB_KINDS[(Math.max(0, LIB_KINDS.indexOf(get())) + (e.key === 'ArrowRight' ? 1 : n - 1)) % n];
    e.preventDefault(); e.stopPropagation();                  // the popout's arrow keys move the highlight over the cards: not from here
    set(to); btns.get(to).focus();
  });
  paint();
  return { el, paint };
}

/* ---------- usage: what the Recent folder lists and how Favourites are ordered (get_usage / forget_recent) */
const usageCat = cat => cat === '@fav' || cat === '@recent';
const usageFlight = {};                                      // kind -> the get_usage call in flight, so a burst of triggers makes one call
/* Takes a get_usage or forget_recent answer. Returns true when anything the browsers show changed. */
function applyUsage(kind, res) {
  if (!res || res.ok === false || !Array.isArray(res.recent)) return false;
  const u = usageOf(kind);
  if (u.loaded && typeof res.mtime_ns === 'number' && typeof u.mtime === 'number' && res.mtime_ns < u.mtime) return false;   // an older answer never replaces a newer one
  const scores = res.scores && typeof res.scores === 'object' ? res.scores : {};
  const sig = JSON.stringify([res.recent, scores]), changed = !u.loaded || sig !== u.sig;
  u.recent = res.recent; u.scores = scores; u.sig = sig; u.loaded = true;
  u.mtime = typeof res.mtime_ns === 'number' ? res.mtime_ns : u.mtime;
  u.recentSet = new Set(res.recent.map(r => nameKey(r.name)));
  u.recentT = new Map(res.recent.map(r => [nameKey(r.name), +r.t || 0]));
  if (changed) for (const b of browsers.values()) if (b.kind() === kind) b.updateUsage();
  return changed;
}
function loadUsage(kind) {
  if (!isLib(kind)) return Promise.resolve();
  if (usageFlight[kind]) return usageFlight[kind];
  return (usageFlight[kind] = (async () => {
    let res = null;
    try { res = await call('get_usage', kind); } catch (e) { res = null; }
    applyUsage(kind, res);
  })().finally(() => { delete usageFlight[kind]; }));
}
/* Every kind a browser is showing: on window focus (the other window may have picked something) and when the popout is shown. */
function reloadUsage() { for (const k of new Set(Array.from(browsers.values()).map(b => b.kind()))) loadUsage(k); }
/* "Remove from Recent" for one or several items of a kind. */
async function forgetRecent(kind, names) {
  let res = null;
  try { for (const n of names) res = await call('forget_recent', kind, n); } catch (e) { res = null; }
  if (res && res.ok !== false && Array.isArray(res.recent)) applyUsage(kind, res);
  else { toast((res && res.error) || 'Could not remove it from Recent.', { tone: 'warn', ms: 3800 }); loadUsage(kind); }
}

function catTree(kind) {
  const L = lib(kind);
  if (L._tree) return L._tree;                               // loadLibrary clears it
  const counts = new Map();
  L.items.forEach(b => counts.set(b.category, (counts.get(b.category) || 0) + 1));
  const groups = new Map();
  for (const [cat, c] of counts) {
    const parts = cat.split('/'), top = parts[0];
    if (!groups.has(top)) groups.set(top, { id: top, count: 0, own: 0, kids: [] });
    const g = groups.get(top);
    g.count += c;
    if (parts.length === 1) g.own += c; else g.kids.push({ id: cat, label: parts.slice(1).join(' / '), count: c });
  }
  groups.forEach(g => g.kids.sort((a, b) => a.label.localeCompare(b.label, undefined, { sensitivity: 'base' })));
  return (L._tree = Array.from(groups.values()));
}
function catMatch(b, cat, host, kind) {
  if (cat === 'All') return true;
  if (cat === '@used') return !!(host.badge && host.badge(b.name, kind));
  if (cat === '@fav') return isFav(kind, b.name);
  if (cat === '@recent') return usageOf(kind).recentSet.has(nameKey(b.name));
  return b.category === cat || b.category.startsWith(cat + '/');
}
const resFor = px => (px > 160 ? 256 : 128);     // above 160 CSS px a 128 px thumbnail starts to look soft

/* Adds a brush, alpha, material or texture to the menu being edited. One the menu already has is not added silently. */
function addToCurrent(kind, name) {
  const m = curMenu();
  if (!m) { toast('Create or select a menu first.', { tone: 'warn' }); return; }
  const id = S.menuId, title = m.title || id;
  if ((usageMap().get(kind + ':' + nameKey(name)) || []).some(u => u.menuId === id)) {
    toast(`"${name}" is already in "${title}"`, { tone: 'warn', action: { text: 'Add anyway', fn: () => insertAsset(id, kind, name, null) } });
    return;
  }
  insertAsset(id, kind, name, null);
}

/* Adds several of one kind to the menu being edited as one undoable step; the ones it already has are skipped. */
function addManyToCurrent(kind, names) {
  const m = curMenu();
  if (!m) { toast('Create or select a menu first.', { tone: 'warn' }); return; }
  const id = S.menuId, title = m.title || id, used = usageMap();
  const fresh = names.filter(n => !(used.get(kind + ':' + nameKey(n)) || []).some(u => u.menuId === id));
  if (!fresh.length) { toast(`All ${names.length} are already in "${title}"`, { tone: 'warn' }); return; }
  sealSnap();
  fresh.forEach(n => insertAsset(id, kind, n, null, true));
  const skipped = names.length - fresh.length;
  undoToast(`Added ${plural(fresh.length, K(kind).one)} to "${title}"` + (skipped ? ` (${skipped} already there)` : ''));
}

/* What a browser does with a pick, and what it knows about menus. The Studio's browser adds the item to the menu being edited and marks
   the ones a menu already has; the popout's selects it in ZBrush and knows nothing of menus. Every callback gets the kind on show
   ('brush', 'alpha', 'material' or 'texture') as its LAST argument.
     dnd             cards can be dragged onto the Studio's drop zones
     primaryIcon(kind)   the icon of the pick button on a card and of the strip's button
     primaryLabel(kind)  the strip button's text ("Add to Brushes", "Select in ZBrush")
     canPrimary(n, kind) whether n selected items can be picked together
     primary(name, kind) the pick: a double-click, Enter, the strip button or a card's button
     primaryMany(names, kind)  the same for a selection of several (a single name goes to primary)
     cardTitle(kind), cardLabel(name, kind), enterHint   the card button's tooltip, a card's spoken label and the Enter hint in it
     hint(kind)      nodes for the line under the search box
     tools()         optional: a node for the end of the toolbar
     badge           null (no "In my menus" folder, no badges) or badge(name, kind) -> { n, titles } | null
     onSize(px)      optional: the thumbnail size changed
     onKind(kind)    optional: the browser switched to another kind */
const STUDIO_HOST = {
  dnd: true,
  tools: () => h('button', { class: 'btn small', type: 'button', title: 'Open the browser in its own window', onclick: openBrowserWindow }, icon('k_browser', 13), 'Browser'),
  primaryIcon: () => 'plus',
  primaryLabel() { const m = curMenu(); return m ? 'Add to ' + (m.title || S.menuId) : 'No menu to add to'; },
  canPrimary() { return !!curMenu(); },
  primary: (name, kind) => addToCurrent(kind, name),
  primaryMany(names, kind) { if (names.length === 1) addToCurrent(kind, names[0]); else if (names.length) addManyToCurrent(kind, names); },
  cardTitle() { const m = curMenu(); return 'Add to ' + ((m && m.title) || 'current menu'); },
  cardLabel: (name, kind) => 'Add ' + name + ' to the current menu',
  enterHint: 'Press Enter to add to the current menu.',
  hint(kind) {
    const m = curMenu(), n = m ? (m.title || S.menuId) : '';
    return ['Click ' + aOrAn(K(kind).one) + ' to select it, then Add to ', h('b', null, n || 'a menu'), '; or drag it onto a menu, the ring or the item list. Double-click or Enter adds it too. Ctrl-click or Shift-click selects several; right-click tags.'];
  },
  badge(name, kind) {
    const u = usageMap().get(tagKey(kind, name));
    return u ? { n: u.length, titles: Array.from(new Set(u.map(x => (S.cfg.menus[x.menuId] || {}).title || x.menuId))) } : null;
  },
};

/* The browser in its own window (the Library toolbar, Settings): the app shows it if it is running, else a new one starts. It needs neither ZBrush nor the app. */
async function openBrowserWindow() {
  let r;
  try { r = await call('open_browser'); } catch (e) { r = { ok: false, error: (e && e.message) || String(e) }; }
  if (!r || !r.ok) toast((r && r.error) || 'Could not open the browser.', { tone: 'warn', ms: 3800 });
}

/* ---------- finding items: rescan button and the empty states */
function paintRescanBtn(b) {
  const busy = lib(b.dataset.kind).busy;
  b.title = 'Look for ' + K(b.dataset.kind).one + ' files again';
  b.disabled = busy;
  b.setAttribute('aria-busy', busy ? 'true' : 'false');
  b.replaceChildren(busy ? h('span', { class: 'spin' }) : icon('refresh', 13), b.dataset.label);
}
function paintRescan() { $$('.rescan-btn').forEach(paintRescanBtn); }
function rescanBtn(kind, label = 'Rescan') {
  const b = h('button', { class: 'btn small rescan-btn', type: 'button', title: 'Look for ' + K(kind).one + ' files again', dataset: { label, kind }, onclick: () => rescanLibrary(kind) });
  paintRescanBtn(b);
  return b;
}
async function rescanLibrary(kind) {
  const L = lib(kind), w = K(kind);
  if (L.busy) return;
  await loadLibrary(kind, true);
  if (L.state === 'error') { toast(L.error || 'Could not read the ' + w.one + ' folders.', { tone: 'warn', ms: 4500 }); return; }
  const n = L.items.length;
  toast('Found ' + plural(n, w.one), n ? {} : { tone: 'warn' });
}
/* What the grid says when there is no library to show: a read error, no ZBrush, or no files in the folders searched. */
function libEmptyState(kind) {
  const L = lib(kind), w = K(kind);
  let el;
  if (L.state === 'error') el = emptyState('alert', 'Could not read the ' + w.one + ' library', L.error || 'The backend could not list your ZBrush ' + w.one + ' folders.');
  else if (!L.zbrushFound) el = emptyState('library', 'No ' + w.many + ' to show', 'ZBrush was not found. Studio reads the ' + w.one + ' folders of a ZBrush that has run at least once.');
  else {
    el = emptyState('library', 'No ' + w.many + ' found', 'No ' + w.ext + ' files in these folders:');
    if (L.sources.length) el.append(h('ul', { class: 'src-list mono' }, L.sources.map(s => h('li', { class: s.exists ? '' : 'miss' },
      h('span', { class: 'src-path' }, s.path), h('span', { class: 'src-n' }, ' ' + s.count + (s.count === 1 ? ' file' : ' files')), s.exists ? null : h('em', null, ' (missing)')))));
  }
  el.append(rescanBtn(kind, L.state === 'error' ? 'Retry' : 'Rescan'));
  return el;
}

/* kindUi: where the kind tabs go. 'tabs' (the default of the full browser) draws them above the toolbar, 'compact' (the dock's default)
   draws a tighter row, 'none' draws none: the host mounts its own (the popout's header) and calls setKind. */
function makeBrowser({ compact, st, host = STUDIO_HOST, kindUi = compact ? 'compact' : 'tabs' }) {
  const root = h('div', { class: 'browser ' + (compact ? 'compact' : 'full') });
  if (!isLib(st.kind)) st.kind = 'brush';
  ensureLib(st.kind);
  const L = () => lib(st.kind);                                  // the library of the kind on show
  const W = () => KINDS[st.kind];                                // its wording
  const search = h('input', { class: 'inp', type: 'text', value: st.q, spellcheck: 'false', autocomplete: 'off' });   // placeholder and label: paintStrings
  const clearBtn = h('button', { class: 'ibtn', type: 'button', title: 'Clear search', 'aria-label': 'Clear search', hidden: !st.q, onclick: () => { clearQuery(); renderGrid(); search.focus(); } }, icon('x', 13));
  const count = h('span', { class: 'b-count mono' });
  const grid = h('div', { class: 'bgrid' });
  const scroll = h('div', { class: 'b-scroll' }, grid);
  const side = h('div', { class: 'lib-side' });
  const catsBox = h('div', { class: 'cats', role: 'listbox', 'aria-label': 'Folders' });
  const tagSec = h('div', { class: 'tag-sec', role: 'group', 'aria-label': 'Tags' });                     // full: the Tags section under Folders
  const tagRow = h('div', { class: 'tagrow', role: 'group', 'aria-label': 'Filter by tag', hidden: true });   // compact: the same chips, wrapped
  side.append(catsBox, tagSec);
  const lazy = makeLazyIO(scroll);
  let token = 0, curRes = compact ? 128 : resFor(st.size), lastSig = '';
  const sel = new Set();                 // names of the selected items
  let anchor = null;                     // the last plain or Ctrl click: where a Shift-click range starts
  if (!st.open) st.open = new Set();
  if (!(st.tags instanceof Set)) st.tags = new Set();     // the tags to show (any of them), kept on the state like st.cat
  st.untagged = !!st.untagged;                            // the virtual "Untagged" chip: items without any tag
  if (st.cat.includes('/')) st.open.add(st.cat.split('/')[0]);   // a folder chosen from outside (a link) starts unfolded

  const searchBox = h('label', { class: 'searchbox' }, icon('search', 14), search, clearBtn);
  const onSearch = debounce(() => { st.q = search.value; clearBtn.hidden = !st.q; renderGrid(); if (host.firstMatch) highlightFirst(); }, 120);
  search.addEventListener('input', onSearch);
  search.addEventListener('keydown', e => { if (e.key === 'Escape' && search.value) { e.stopPropagation(); clearBtn.click(); } });
  let autoHl = false;                    // the selection is only the highlight put on the first match (the popout), so Esc leaves it alone
  function clearQuery() { onSearch.cancel(); search.value = ''; st.q = ''; clearBtn.hidden = true; }

  /* The selected items and their action strip. A click selects one, Ctrl-click adds or removes one, Shift-click selects a
     range of the items on show. The strip tags them or adds them to the menu being edited. */
  const hint = h('div', { class: 'b-hint' });
  const addBtn = h('button', { class: 'btn primary small as-add', type: 'button', onclick: () => host.primaryMany(Array.from(sel), st.kind) });
  const tagBtn = h('button', { class: 'btn small as-tag', type: 'button', onclick: () => tagPicker(tagBtn, st.kind, Array.from(sel)) },
    icon('tag', 13), compact ? null : 'Tag...');
  const favBtn = h('button', { class: 'btn small as-fav', type: 'button', 'aria-pressed': 'false', onclick: () => toggleFavs(Array.from(sel)) }, icon('star', 13));
  const stripThumb = h('span', { class: 'as-thumb' }), stripName = h('b'), stripCat = h('small');
  const strip = h('div', { class: 'add-strip', hidden: true, role: 'region' },
    stripThumb, h('div', { class: 'as-name' }, stripName, stripCat), favBtn, tagBtn, addBtn, iconBtn('x', 'Clear selection', () => setSel(null)));
  /* Favourites go through the same tag call as any tag, so its answer repaints every browser (tagsChanged). */
  const setFavs = (names, on) => (names.length ? tagCall('tag_items', names.map(n => tagKey(st.kind, n)), on ? [FAV] : [], on ? [] : [FAV]) : Promise.resolve());
  const toggleFavs = names => setFavs(names, !names.every(n => isFav(st.kind, n)));
  /* The strip's star: pressed while every selected item is a favourite. */
  function paintFavBtn() {
    const names = Array.from(sel), all = names.length > 0 && names.every(n => isFav(st.kind, n));
    const text = (all ? 'Remove the selected ' + W().many + ' from Favourites' : 'Add the selected ' + W().many + ' to Favourites') + ' (Ctrl+D)';
    favBtn.classList.toggle('on', all); favBtn.setAttribute('aria-pressed', all ? 'true' : 'false');
    favBtn.title = text; favBtn.setAttribute('aria-label', text);
  }
  function paintTarget() {
    const label = host.primaryLabel(st.kind), ic = host.primaryIcon(st.kind);
    hint.replaceChildren(...host.hint(st.kind));
    if (addBtn.dataset.label !== label || addBtn.dataset.icon !== ic) {
      addBtn.dataset.label = label; addBtn.dataset.icon = ic; addBtn.title = label;
      addBtn.replaceChildren(icon(ic, 13), h('span', { class: 'as-add-txt' }, label));
    }
    addBtn.disabled = !host.canPrimary(sel.size, st.kind);
  }
  /* Repaints the cards and the strip from `sel`; `focusName` is the card to give focus. */
  function paintSel(focusName = null) {
    autoHl = false;
    $$('.bcard', grid).forEach(c => {
      const on = sel.has(c.dataset.name);
      c.classList.toggle('sel', on); c.setAttribute('aria-pressed', on ? 'true' : 'false');
      if (on && c.dataset.name === focusName && document.activeElement !== c) c.focus({ preventScroll: true });
    });
    strip.hidden = sel.size === 0;
    if (sel.size === 1) {
      const b = L().byName.get(nameKey(sel.values().next().value));
      if (b) { stripThumb.replaceChildren(thumb(b.name, { size: 34, kind: st.kind })); setText(stripName, b.name); setText(stripCat, b.category); }
    } else if (sel.size > 1) {
      stripThumb.replaceChildren(h('span', { class: 'as-multi' }, String(sel.size)));
      setText(stripName, sel.size + ' selected'); setText(stripCat, host.canPrimary(sel.size, st.kind) ? 'Ctrl-click or Shift-click to change' : `ZBrush takes one ${W().one} at a time`);
    }
    addBtn.disabled = !host.canPrimary(sel.size, st.kind);
    paintFavBtn();
  }
  function setSel(name, focusCard = false) {
    const b = name ? L().byName.get(nameKey(name)) : null;
    sel.clear(); anchor = b ? b.name : null;
    if (b) sel.add(b.name);
    paintSel(focusCard && b ? b.name : null);
  }
  root.addEventListener('keydown', e => {
    if (e.key === 'Escape' && sel.size && !autoHl && !S.problemsOpen && !e.defaultPrevented) { e.preventDefault(); setSel(null); }
  });
  scroll.addEventListener('click', e => { if (sel.size && !e.target.closest('.bcard, button, a, input')) setSel(null); });
  scroll.addEventListener('keydown', e => {       // Ctrl+A in the grid selects every item on show
    if (!(e.ctrlKey || e.metaKey) || e.altKey || e.key.toLowerCase() !== 'a' || e.target.closest('input, textarea')) return;
    e.preventDefault();
    sel.clear(); for (const b of filtered()) sel.add(b.name);
    paintSel();
  });
  let tools, catSel = null, rescan = null, dockHint = null;
  const tabs = kindUi === 'none' ? null : kindTabs(() => st.kind, kind => setKind(kind), kindUi === 'compact' ? 'compact' : '');
  if (compact) {
    catSel = h('select', { class: 'inp sel', 'aria-label': 'Category', onchange: () => { setCat(catSel.value); renderGrid(); } });
    tools = h('div', { class: 'b-tools' }, searchBox, catSel);
    dockHint = h('div', { class: 'dock-hint' });
    root.append(...[tabs && tabs.el, dockHint, tools, tagRow, count, scroll, strip].filter(Boolean));
  } else {
    const size = h('input', { type: 'range', min: 84, max: 220, step: 4, value: st.size, 'aria-label': 'Thumbnail size' });
    const paint = () => size.style.setProperty('--pct', ((st.size - 84) / (220 - 84)) * 100 + '%');
    size.addEventListener('input', () => {
      st.size = +size.value; grid.style.setProperty('--card', st.size + 'px'); paint();
      if (host.onSize) host.onSize(st.size);
      const r = resFor(st.size);
      if (r !== curRes) { curRes = r; $$('.bcard .thumb', grid).forEach(t => rethumb(t, r)); }
    });
    paint(); grid.style.setProperty('--card', st.size + 'px');
    rescan = rescanBtn(st.kind);
    tools = h('div', { class: 'b-tools' }, searchBox, h('div', { class: 'size-ctl' }, icon('library', 13), size), rescan, host.tools ? host.tools() : null);
    root.append(side, h('div', { class: 'lib-main' }, tabs ? tabs.el : null, tools, h('div', { class: 'b-sub' }, hint, count), scroll, strip));
  }

  /* --- tag filter: an item shows when it carries any chosen tag; "Untagged" shows the items without a tag */
  const tagFilterOn = () => st.untagged || st.tags.size > 0;
  function pruneTagSel() { if (S.tagsLoaded) for (const k of Array.from(st.tags)) if (!S.tagMap.has(k)) st.tags.delete(k); }
  const tagMatch = b => {
    if (!tagFilterOn()) return true;
    const ks = tagsOf(st.kind, b.name);
    return st.untagged ? !ks.some(k => k !== FAV) : ks.some(k => st.tags.has(k));     // untagged: no ordinary tag (see tagCounts)
  };
  /* The items on show: in name order, except Favourites (most used first, by the usage scores) and Recent (newest pick first).
     L().sorted is in name order and sort is stable, so ties keep it. */
  const filtered = () => {
    pruneTagSel();
    const q = st.q.trim().toLowerCase(), terms = q ? q.split(/\s+/) : [];
    const list = L().sorted.filter(b => catMatch(b, st.cat, host, st.kind) && (!terms.length || terms.every(t => b.name.toLowerCase().includes(t))) && tagMatch(b));
    const u = usageOf(st.kind);
    if (st.cat === '@fav') list.sort((a, b) => (u.scores[b.name.toLowerCase()] || 0) - (u.scores[a.name.toLowerCase()] || 0));
    else if (st.cat === '@recent') list.sort((a, b) => (u.recentT.get(nameKey(b.name)) || 0) - (u.recentT.get(nameKey(a.name)) || 0));
    return list;
  };
  /* Picks a folder; the two usage folders read get_usage afresh. */
  function setCat(cat) { st.cat = cat; if (usageCat(cat)) loadUsage(st.kind); }
  function toggleTag(key) {
    if (key === '@untagged') { st.untagged = !st.untagged; if (st.untagged) st.tags.clear(); }
    else { st.untagged = false; if (st.tags.has(key)) st.tags.delete(key); else st.tags.add(key); }
    renderTags(); renderGrid();
  }
  function clearTagFilter() { st.tags.clear(); st.untagged = false; renderTags(); renderGrid(); }
  /* The chips: a list under Folders in the full browser, a wrapped row under the category in the dock. */
  function renderTags() {
    const host = compact ? tagRow : tagSec;
    const act = document.activeElement, fr = act && host.contains(act) ? act.closest('[data-tk]') : null, fk = fr ? fr.dataset.tk : null;
    pruneTagSel();
    const counts = tagCounts(st.kind);
    const chip = (key, label, n, color) => {
      const on = key === '@untagged' ? st.untagged : st.tags.has(key);
      return h('button', { class: 'tagchip' + (on ? ' on' : ''), type: 'button', 'aria-pressed': on ? 'true' : 'false', title: label + ' (' + plural(n, W().one) + ')', style: color ? { '--tag': color } : null,
        dataset: { tk: key }, onclick: () => toggleTag(key) },
        h('i', { class: 'tdot' + (color ? '' : ' none') }), h('span', { class: 'tc-name' }, label), h('span', { class: 'tc-n mono' }, String(n)));
    };
    const own = S.tags.filter(t => t.key !== FAV);                // Favourites has its own folder, not a chip
    const chips = own.map(t => chip(t.key, t.label, counts.byKey.get(t.key) || 0, t.color));
    if (own.length) chips.push(chip('@untagged', 'Untagged', counts.untagged, null));
    const clear = tagFilterOn() ? h('button', { class: 'link tag-clear', type: 'button', onclick: clearTagFilter }, 'Clear') : null;
    if (compact) {
      tagRow.hidden = !own.length;
      tagRow.replaceChildren(...[...chips, clear, h('button', { class: 'ibtn tag-manage', type: 'button', title: 'Manage tags...', 'aria-label': 'Manage tags', onclick: () => openTagManager() }, icon('tag', 14))].filter(Boolean));
    } else {
      tagSec.replaceChildren(...[h('div', { class: 'tag-head' }, h('span', { class: 'micro side-title' }, 'Tags'), clear),
        own.length ? h('div', { class: 'tagchips' }, chips) : h('div', { class: 'tag-none fhint' }, `No tags yet. Select ${W().many} and press Tag to make one.`),
        S.tagsErr ? h('div', { class: 'fhint bad' }, S.tagsErr) : null,
        manageTagsBtn('btn small tag-manage')].filter(Boolean));
    }
    if (fk !== null) { const t = $$('[data-tk]', host).find(x => x.dataset.tk === fk); if (t) t.focus(); }
  }
  const usedCount = () => { let n = 0; if (host.badge) for (const b of L().items) if (host.badge(b.name, st.kind)) n++; return n; }; // the "In my menus" folder
  function paintBadge(card) {
    const u = host.badge ? host.badge(card.dataset.name, st.kind) : null;
    card.classList.toggle('used', !!u);
    let bd = $('.bbadge', card);
    if (!u) { if (bd) bd.remove(); return; }
    if (!bd) { bd = h('span', { class: 'bbadge' }); $('.bthumb', card).append(bd); }
    bd.textContent = u.n > 1 ? String(u.n) : '';
    bd.classList.toggle('one', u.n < 2);
    bd.title = 'Used in: ' + u.titles.join(', ');
    if (u.n < 2) bd.replaceChildren(icon('check', 10));
  }
  /* Up to three dots (the first tag first) bottom-left of the thumbnail, and --tag, the first tag's colour, for the card's stripe.
     Favourites is not among them: it is the star (paintFav). */
  function paintTags(card) {
    const name = card.dataset.name, b = L().byName.get(nameKey(name)), fav = isFav(st.kind, name);
    const ks = tagsOf(st.kind, name).filter(k => k !== FAV).map(k => S.tagMap.get(k)), box = $('.bthumb', card);
    let dots = $('.tagdots', box);
    const tagText = ks.length ? 'Tags: ' + ks.map(t => t.label).join(', ') : '';
    card.title = name + (b ? '\n' + b.category : '') + (fav ? '\nFavourite' : '') + (tagText ? '\n' + tagText : '');
    card.setAttribute('aria-label', name + '.' + (fav ? ' Favourite.' : '') + (tagText ? ' ' + tagText + '.' : '') + ' ' + host.enterHint + (fav ? ' Ctrl+D removes it from Favourites.' : ' Ctrl+D adds it to Favourites.'));
    card.classList.toggle('tagged', ks.length > 0);
    if (!ks.length) { card.style.removeProperty('--tag'); if (dots) dots.remove(); return; }
    card.style.setProperty('--tag', ks[0].color);
    if (!dots) { dots = h('span', { class: 'tagdots', 'aria-hidden': 'true' }); box.append(dots); }
    dots.replaceChildren(...ks.slice(0, 3).map(t => h('i', { class: 'tdot', style: { '--tag': t.color } })));
  }
  /* The star at the top-right of the thumbnail: a filled gold star while the item is a favourite (always shown), an outline on hover
     otherwise. A real button, so the popout does not start a drag from it. On a card in a multi-selection it acts on the whole selection. */
  function paintFav(card) {
    const name = card.dataset.name, on = isFav(st.kind, name), box = $('.bthumb', card);
    let btn = $('.bstar', box);
    if (!btn) {
      btn = h('button', { class: 'bstar', type: 'button',
        onclick: e => { e.stopPropagation(); const n = card.dataset.name; setFavs(sel.size > 1 && sel.has(n) ? Array.from(sel) : [n], !isFav(st.kind, n)); },
        ondblclick: e => e.stopPropagation() }, icon('star', 14));          // a double-click must not pick the item
      box.append(btn);
    }
    const text = on ? 'Remove from Favourites' : 'Add to Favourites';
    btn.classList.toggle('on', on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.title = text; btn.setAttribute('aria-label', text + ': ' + name);
  }
  function makeCard(b) {
    const on = sel.has(b.name);
    const card = h('div', { class: 'bcard' + (on ? ' sel' : ''), tabindex: '0', role: 'button', 'aria-pressed': on ? 'true' : 'false', dataset: { name: b.name } },
      h('div', { class: 'bthumb' }, thumb(b.name, { size: 0, lazy, cls: 'fill', res: curRes, kind: st.kind }),
        h('button', { class: 'badd', type: 'button', title: host.cardTitle(st.kind), 'aria-label': host.cardLabel(b.name, st.kind), onclick: e => { e.stopPropagation(); host.primary(b.name, st.kind); } }, icon(host.primaryIcon(st.kind), 14))),
      h('div', { class: 'bname' }, b.name));
    card.addEventListener('click', e => {
      if (e.shiftKey && anchor && L().byName.has(nameKey(anchor))) {      // a range over the items on show, from the last plain click
        const names = filtered().map(x => x.name), a = names.indexOf(anchor), z = names.indexOf(b.name);
        if (a >= 0 && z >= 0) {
          if (!(e.ctrlKey || e.metaKey)) sel.clear();
          for (let i = Math.min(a, z); i <= Math.max(a, z); i++) sel.add(names[i]);
          paintSel(b.name);
          return;
        }
      }
      if (e.ctrlKey || e.metaKey) {
        if (sel.has(b.name)) sel.delete(b.name); else sel.add(b.name);
        anchor = b.name; paintSel(b.name);
        return;
      }
      setSel(b.name, true);
    });
    card.addEventListener('dblclick', e => { if (!e.ctrlKey && !e.shiftKey && !e.metaKey) host.primary(b.name, st.kind); });
    card.addEventListener('contextmenu', e => {                              // tag this item, or the whole selection when it is in it
      e.preventDefault();
      const names = sel.size > 1 && sel.has(b.name) ? Array.from(sel) : [b.name], kind = st.kind;
      tagPicker(card, kind, names, { x: e.clientX, y: e.clientY },
        st.cat === '@recent' ? [{ icon: 'clock', label: 'Remove from Recent', fn: () => forgetRecent(kind, names) }] : null);
    });
    card.addEventListener('keydown', e => {
      if (e.target !== card) return;
      if (e.key === 'Enter') {
        e.preventDefault();
        if (sel.size > 1 && sel.has(b.name)) host.primaryMany(Array.from(sel), st.kind); else { setSel(b.name); host.primary(b.name, st.kind); }
      } else if (e.key === ' ') {
        e.preventDefault();
        if (e.ctrlKey || e.metaKey) { if (sel.has(b.name)) sel.delete(b.name); else sel.add(b.name); anchor = b.name; paintSel(); } else setSel(b.name);
      }
    });
    if (host.dnd) DnD.source(card, () => ({ type: 'asset', kind: st.kind, name: b.name }), () => h('span', { class: 'ghost-chip' }, thumb(b.name, { size: 26, kind: st.kind }), b.name));
    if (host.nativeDrag) {                                                   // the popout: a drag the other window can take (see ITEM_MIME)
      card.setAttribute('draggable', 'true');
      let downOnButton = false;                                              // a press on the card's own button picks, it never drags
      card.addEventListener('pointerdown', e => { downOnButton = !!(e.target.closest && e.target.closest('button')); });
      card.addEventListener('dragstart', e => {
        if (downOnButton) { e.preventDefault(); return; }
        if (e.target !== card || !e.dataTransfer) return;
        const dt = e.dataTransfer, t = $('.thumb', card);
        dt.effectAllowed = 'copy';
        dt.setData(ITEM_MIME, JSON.stringify({ kind: st.kind, name: b.name }));
        dt.setData('text/plain', ITEM_TEXT + st.kind + ':' + b.name);
        if (t) { const r = t.getBoundingClientRect(); dt.setDragImage(t, Math.round(r.width / 2), Math.round(r.height / 2)); }
      });
    }
    paintBadge(card);
    paintTags(card);
    paintFav(card);
    return card;
  }
  function paintCount(list) {
    const f = tagFilterOn();
    let t = list.length + ' ' + (list.length === 1 ? W().one : W().many) + (st.cat !== 'All' || st.q || f ? ' of ' + L().items.length : '');
    if (f) t += ' · ' + (st.untagged ? 'untagged' : plural(st.tags.size, 'tag'));
    setText(count, t);
  }
  function renderGrid() {
    $$('.thumb', grid).forEach(t => { if (t._io) t._io.unobserve(t); });   // the old cards are about to go: do not keep them in the observer
    const my = ++token;
    grid.replaceChildren();
    lastSig = '';
    if (L().state === 'loading' || L().state === 'idle') {
      setText(count, 'Scanning...');
      for (let i = 0; i < 24; i++) grid.append(h('div', { class: 'bcard skel' }, h('div', { class: 'bthumb' }, h('span', { class: 'thumb fill loading' })), h('div', { class: 'bname' }, ' ')));
      return;
    }
    const gone = Array.from(sel).filter(n => !L().byName.has(nameKey(n)));
    if (gone.length) { gone.forEach(n => sel.delete(n)); paintSel(); }
    if (L().state === 'error' || !L().items.length) {
      setText(count, `0 ${W().many}`);
      grid.append(h('div', { class: 'grid-empty' }, libEmptyState(st.kind)));
      return;
    }
    const list = filtered();
    lastSig = list.map(b => b.name).join('\n');
    paintCount(list);
    if (!list.length) {
      let e;
      if (tagFilterOn()) {
        e = emptyState('tag', st.untagged ? `Every ${W().one} here has a tag` : `No ${W().many} with ` + (st.tags.size === 1 ? 'that tag' : 'those tags'),
          st.q || st.cat !== 'All' ? 'The search and the folder narrow it too.' : `Select ${W().many} and press Tag, or right-click ${aOrAn(W().one)}.`, { text: 'Clear the tag filter', fn: clearTagFilter });
      } else if (st.q) {
        const where = st.cat === '@used' ? 'In my menus' : st.cat === '@fav' ? 'Favourites' : st.cat === '@recent' ? 'Recent' : st.cat.split('/').join(' / ');
        e = emptyState('search', `No ${W().many} match "${st.q}"`, st.cat !== 'All' ? `Only "${where}" was searched.` : 'Check the spelling.');
        e.append(h('div', { class: 'btn-row' },
          h('button', { class: 'btn small', type: 'button', onclick: () => { clearQuery(); renderAll(); } }, 'Clear search'),
          st.cat !== 'All' ? h('button', { class: 'btn small primary', type: 'button', onclick: () => { st.cat = 'All'; renderAll(); } }, 'Search all folders') : null));
      } else if (st.cat === '@fav') {
        e = emptyState('star', 'No favourites yet', `Hover ${aOrAn(W().one)} and press its star, or press Ctrl+D.`, { text: `Show all ${W().many}`, fn: () => { st.cat = 'All'; renderAll(); } });
      } else if (st.cat === '@recent') {
        e = emptyState('clock', 'Nothing picked yet', 'Items you pick in ZBrush show up here, newest first.', { text: `Show all ${W().many}`, fn: () => { st.cat = 'All'; renderAll(); } });
      } else {
        e = emptyState('search', 'Nothing in this category', st.cat === '@used' ? `${W().tab} you put into a menu show up here.` : '', { text: `Show all ${W().many}`, fn: () => { st.cat = 'All'; renderAll(); } });
      }
      grid.append(h('div', { class: 'grid-empty' }, e));
      return;
    }
    let i = 0;
    const chunk = () => {
      if (my !== token) return;
      const frag = document.createDocumentFragment();
      for (const end = Math.min(i + 160, list.length); i < end; i++) frag.append(makeCard(list[i]));
      grid.append(frag);
      if (i < list.length) requestAnimationFrame(chunk);
    };
    chunk();
  }
  function renderCats() {
    const tree = catTree(st.kind);
    const favN = tagCounts(st.kind).byKey.get(FAV) || 0;                                   // the Favourites and Recent folders: no host.badge needed
    const u = usageOf(st.kind), recentN = u.recent.filter(r => L().byName.has(nameKey(r.name))).length;   // only the picks still in the library, as the grid shows
    if (compact) {
      const opts = [['@fav', `Favourites (${favN})`], ['@recent', `Recent (${recentN})`], ['All', `All ${W().many} (${L().items.length})`], host.badge ? ['@used', `In my menus (${usedCount()})`] : null].filter(Boolean);
      tree.forEach(g => { opts.push([g.id, `${g.id} (${g.count})`]); g.kids.forEach(k => opts.push([k.id, `   ${g.id} / ${k.label} (${k.count})`])); });
      catSel.replaceChildren(...opts.map(([v, t]) => h('option', { value: v, selected: v === st.cat }, t)));
      return;
    }
    const act = document.activeElement, fr = act && catsBox.contains(act) ? act.closest('.cat') : null;
    const fid = fr ? fr.dataset.id : null, onChev = !!fr && act.classList.contains('cat-chev');
    const row = (id, label, n, o = {}) => {
      const toggle = () => { st.open.has(id) ? st.open.delete(id) : st.open.add(id); renderCats(); };
      const activate = () => {
        if (o.hasKids && st.cat === id) { toggle(); return; }                // a click on the selected folder folds or unfolds it
        setCat(id);
        if (o.hasKids) st.open.add(id);
        renderAll();
      };
      const r = h('div', { class: 'cat' + (st.cat === id ? ' on' : '') + (o.kid ? ' kid' : '') + (o.group ? ' group' : ''), role: 'option', tabindex: '0', 'aria-selected': st.cat === id ? 'true' : 'false', title: label, dataset: { id },
        onclick: activate, onkeydown: e => { if (e.target === r && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); activate(); } } },
        o.hasKids ? h('button', { class: 'cat-chev' + (st.open.has(id) ? ' open' : ''), type: 'button', 'aria-label': (st.open.has(id) ? 'Collapse ' : 'Expand ') + label, 'aria-expanded': st.open.has(id) ? 'true' : 'false',
          onclick: e => { e.stopPropagation(); toggle(); } }, icon('chevR', 12)) : h('span', { class: 'cat-chev none' + (o.ico ? ' cat-ico' : '') }, o.ico ? icon(o.ico, 13) : null),
        h('span', { class: 'cat-name' }, label), h('span', { class: 'cat-n mono' }, String(n)));
      return r;
    };
    const rows = [h('div', { class: 'micro side-title' }, 'Folders'), row('@fav', 'Favourites', favN, { ico: 'star' }), row('@recent', 'Recent', recentN, { ico: 'clock' }),
      row('All', 'All', L().items.length), host.badge ? row('@used', 'In my menus', usedCount()) : null].filter(Boolean);
    tree.forEach(g => {
      const hasKids = g.kids.length > 0;
      rows.push(row(g.id, g.id, g.count, { group: true, hasKids }));
      if (hasKids && st.open.has(g.id)) g.kids.forEach(k => rows.push(row(k.id, k.label, k.count, { kid: true })));
    });
    catsBox.replaceChildren(...rows);
    if (fid !== null) {
      const nr = $$('.cat', catsBox).find(r => r.dataset.id === fid);
      const t = nr && ((onChev && $('button.cat-chev', nr)) || nr);
      if (t) t.focus();
    }
  }
  function renderAll() { if (L().state === 'ready') renderCats(); renderTags(); renderGrid(); }

  /* --- keyboard help for the popout: a highlight that follows the arrow keys and Enter picks */
  function highlightFirst() {
    const first = filtered()[0];
    if (!first) { if (sel.size) setSel(null); return; }
    setSel(first.name);
    autoHl = true;
  }
  /* Moves the highlight one card (dx) or one row (dy). The row length is however many cards sit at the first card's height. */
  function move(dx, dy) {
    const cards = $$('.bcard[data-name]', grid);
    if (!cards.length) return false;
    const top0 = cards[0].offsetTop;
    let cols = 0;
    while (cols < cards.length && cards[cols].offsetTop === top0) cols++;
    const at = anchor ? cards.findIndex(c => c.dataset.name === anchor) : -1;
    const to = at < 0 ? 0 : clamp(at + dx + dy * cols, 0, cards.length - 1);
    const onCard = document.activeElement && document.activeElement.classList.contains('bcard');
    setSel(cards[to].dataset.name, onCard);
    cards[to].scrollIntoView({ block: 'nearest' });
    return true;
  }
  function pickSelected() {
    const names = Array.from(sel);
    if (!names.length) return false;
    if (names.length === 1) host.primary(names[0], st.kind); else host.primaryMany(names, st.kind);
    return true;
  }
  /* A fresh look: no search, no folder, only the given tag (or none), the first match highlighted. */
  function setFilter(tag) {
    clearQuery(); st.untagged = false; st.tags = new Set(tag && tag !== FAV ? [tag] : []);
    setCat(tag === FAV ? '@fav' : 'All');                       // Favourites is a folder, not a chip
    renderAll(); highlightFirst(); scroll.scrollTop = 0;
  }

  /* Every word that names the kind on show: the ones set once here, and the repaint of the lists reads W() as it goes. */
  function paintStrings() {
    const w = W(), tagText = `Tag the selected ${w.many}`;
    search.placeholder = `Search ${w.many}...`; search.setAttribute('aria-label', `Search ${w.many}`);
    tagBtn.title = tagText; tagBtn.setAttribute('aria-label', tagText);
    strip.setAttribute('aria-label', `Selected ${w.many}`);
    if (dockHint) setText(dockHint, `Click ${aOrAn(w.one)} and press Add, or drag it onto the ring or the list.`);
  }
  /* Switches to another kind: its own folders and selection, the same search text and tag filter. */
  function setKind(kind) {
    if (kind === st.kind || !isLib(kind)) return;
    st.kind = kind;
    sel.clear(); anchor = null; autoHl = false;
    st.cat = 'All'; st.open = new Set();
    if (tabs) tabs.paint();
    paintStrings();
    if (rescan) { rescan.dataset.kind = kind; paintRescanBtn(rescan); }
    paintSel(); paintTarget();
    if (L().state !== 'ready') { catsBox.replaceChildren(); if (catSel) catSel.replaceChildren(); }   // not the last kind's folders
    renderAll();
    scroll.scrollTop = 0;
    ensureLib(kind);                                           // its load repaints through R.libRefresh
    loadUsage(kind);                                           // its Recent folder and Favourites order
    if (host.onKind) host.onKind(kind);
  }

  paintStrings();
  renderAll(); paintTarget();
  loadUsage(st.kind);                                          // the Recent count, and the order when a link opened Favourites or Recent
  const api = {
    el: root, scroller: () => scroll,
    kind: () => st.kind, setKind,
    refresh() { renderAll(); paintTarget(); },
    focusSearch(select = true) { search.focus(); if (select) search.select(); },
    typeChar(ch) { search.value += ch; search.dispatchEvent(new Event('input', { bubbles: true })); },
    inSearch: el => !!el && el.closest && !!el.closest('.searchbox'),
    searchValue: () => search.value,
    highlightFirst, move, pickSelected, setFilter,
    updateBadges() { $$('.bcard[data-name]', grid).forEach(paintBadge); paintTarget(); if (L().state === 'ready') { renderCats(); if (st.cat === '@used') renderGrid(); } },
    /* After a tag change: dots, chips, and the grid itself when the tag filter now shows other items. */
    updateTags() {
      $$('.bcard[data-name]', grid).forEach(c => { paintTags(c); paintFav(c); });
      renderTags(); paintFavBtn();
      if (L().state === 'ready') renderCats();                 // the Favourites count
      if (L().state === 'ready' && filtered().map(b => b.name).join('\n') !== lastSig) { const top = scroll.scrollTop; renderGrid(); scroll.scrollTop = top; }
    },
    /* After get_usage / forget_recent: the Recent count, and the grid when Favourites or Recent is on show and its order or members changed. */
    updateUsage() {
      if (L().state !== 'ready') return;
      renderCats();
      if (usageCat(st.cat) && filtered().map(b => b.name).join('\n') !== lastSig) { const top = scroll.scrollTop; renderGrid(); scroll.scrollTop = top; }
    },
    /* Ctrl+D: stars (or unstars) the selection, or the card named when it is not part of the selection. False when there is nothing to act on. */
    toggleFav(name = null) {
      const shown = new Set(filtered().map(b => b.name));      // a selection can outlive a folder change: only act on what is on screen
      const names = name && !sel.has(name) ? [name] : Array.from(sel).filter(n => shown.has(n));
      if (!names.length) return false;
      toggleFavs(names);
      return true;
    },
  };
  browsers.set(st, api);
  return api;
}

/* ================================================================== LIBRARY screen */
function buildLibraryScreen(root) {
  const browser = makeBrowser({ compact: false, st: S.lib });
  const target = h('aside', { class: 'col lib-target' });
  root.replaceChildren(browser.el, target);
  R.libRefresh = kind => { if (kind === S.lib.kind) browser.refresh(); };
  R.badges = () => browser.updateBadges();
  R.libTarget = () => {
    const hadSel = !!document.activeElement && document.activeElement.matches && document.activeElement.matches('.target-sel select') && target.contains(document.activeElement);
    target.replaceChildren();
    const ids = Object.keys(S.cfg.menus), m = curMenu();
    const sel = h('select', { class: 'inp sel', 'aria-label': 'Target menu', onchange: () => selectMenu(sel.value) }, ids.map(id => h('option', { value: id, selected: id === S.menuId }, (S.cfg.menus[id].title || id))));
    const list = h('div', { class: 'ilist' });
    target.append(h('div', { class: 'col-head' }, h('span', { class: 'micro' }, 'Add to menu')),
      h('div', { class: 'target-sel' }, ids.length ? sel : null),
      h('div', { class: 'items-panel' }, list),
      h('div', { class: 'target-foot' }, h('button', { class: 'btn small', type: 'button', onclick: () => showScreen('menus') }, 'Open in Menus editor', icon('chevR', 12))));
    renderItemList(list, S.menuId, true);
    if (!m) list.replaceChildren(emptyState('menus', 'No menus', 'Create a menu in the Menus screen first.'));
    if (hadSel) sel.focus();
  };
  R.libTarget();
}

/* ================================================================== SETTINGS screen */
function ensureRing() { if (!S.cfg.ring || typeof S.cfg.ring !== 'object') S.cfg.ring = {}; return S.cfg.ring; }
function setRing(k, v) { ensureRing()[k] = v; commit(); }
function setColor(k, v) { const r = ensureRing(); if (!r.colors || typeof r.colors !== 'object') r.colors = {}; r.colors[k] = v; commit(); }
function colorVal(k) { const c = ring().colors; return (c && typeof c[k] === 'string' ? c[k] : S.defaults.colors[k]); }

/* '#fff', 'fff', '#FFAA00' and 'ffaa00' all become '#rrggbb' in lower case; anything else is null. */
function normHex(v) {
  let t = String(v).trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(t)) t = t.replace(/./g, c => c + c);
  return /^[0-9a-f]{6}$/i.test(t) ? '#' + t.toLowerCase() : null;
}
function sliderRow({ label, hint, key, step = 1, unit = '', scale = 1, onLive }) {   // scale: shown = stored * scale (0-1 opacity as 0-100 %)
  const [lo, hi] = ranges()[key] || [0, 100];
  const min = lo * scale, max = hi * scale;
  const disp = v => Number((v * scale).toFixed(6)), store = d => Number((d / scale).toFixed(6));
  const range = h('input', { type: 'range', min, max, step, value: disp(ringNum(key)), 'aria-label': label });
  const num = h('input', { class: 'inp mono num', type: 'number', min, max, step, value: disp(ringNum(key)), 'aria-label': label + ' value' });
  const reset = iconBtn('undo', 'Reset to default (' + disp(S.defaults[key]) + (scale !== 1 ? unit : '') + ')', () => { delete ensureRing()[key]; commit(); sync(ringNum(key)); onLive && onLive(); }, 'reset');
  const note = h('span', { class: 'num-hint', role: 'status' });
  let noteT = 0;
  const say = t => { clearTimeout(noteT); note.textContent = t; if (t) noteT = setTimeout(() => { note.textContent = ''; }, 2000); };
  const sync = v => { range.value = num.value = disp(v); range.style.setProperty('--pct', ((v - lo) / (hi - lo)) * 100 + '%'); reset.style.visibility = key in ring() && ring()[key] !== S.defaults[key] ? 'visible' : 'hidden'; };
  range.addEventListener('input', () => { const v = store(Number(range.value)); setRing(key, v); sync(v); onLive && onLive(); });
  num.addEventListener('change', () => {
    const raw = num.value.trim(), n = Number(raw);
    if (raw === '' || !Number.isFinite(n)) { sync(ringNum(key)); say(''); return; }     // nothing usable typed: keep what was there
    const snapped = Number((min + Math.round((n - min) / step) * step).toFixed(6)), v = store(clamp(snapped, min, max));
    say(n < min || n > max ? 'Kept within ' + min + ' to ' + max : '');
    if (v !== ringNum(key)) { setRing(key, v); onLive && onLive(); }
    sync(v);
  });
  sync(ringNum(key));
  return h('div', { class: 'srow' }, h('div', { class: 'slabel' }, h('span', null, label), hint ? h('small', null, hint) : null), h('div', { class: 'sctl' }, range, h('span', { class: 'nwrap' }, num, unit ? h('em', null, unit) : null, note), reset));
}
function switchRow({ label, hint, key }) {
  const v = ring()[key];
  return h('div', { class: 'srow' }, h('div', { class: 'slabel' }, h('span', null, label), h('small', null, hint)),
    h('div', { class: 'sctl switch' }, toggleSwitch(typeof v === 'boolean' ? v : S.defaults[key], on => { if (on === S.defaults[key]) { delete ensureRing()[key]; commit(); } else setRing(key, on); }, label)));
}
/* A radio group: only the chosen card is a Tab stop; the arrow keys move and choose, Home and End jump to the ends. */
function choiceCards(items, current, onPick, cls = '', label = '') {
  const wrap = h('div', { class: 'choices ' + cls, role: 'radiogroup', 'aria-label': label || null });
  const has = items.some(it => it[0] === current);
  const btns = items.map(([v, title, desc, extra], i) => h('button', { class: 'choice' + (v === current ? ' on' : ''), type: 'button', role: 'radio',
    'aria-checked': v === current ? 'true' : 'false', tabindex: (has ? v === current : i === 0) ? '0' : '-1', dataset: { v },
    onclick: () => pick(i) }, extra || null, h('b', null, title), h('span', null, desc)));
  const pick = (i, focus) => {
    const v = items[i][0];
    btns.forEach((c, j) => { const on = j === i; c.classList.toggle('on', on); c.setAttribute('aria-checked', on ? 'true' : 'false'); c.tabIndex = on ? 0 : -1; });
    if (focus) btns[i].focus();
    onPick(v);
  };
  wrap.addEventListener('keydown', e => {
    if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
    const at = btns.indexOf(document.activeElement);
    if (at < 0) return;
    const n = btns.length;
    const to = { ArrowRight: (at + 1) % n, ArrowDown: (at + 1) % n, ArrowLeft: (at + n - 1) % n, ArrowUp: (at + n - 1) % n, Home: 0, End: n - 1 }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    if (to !== at) pick(to, true);
  });
  wrap.append(...btns);
  return wrap;
}
/* Badge on the Settings rail button and the "Older ZBrush" contents entry while an installed ZScript plugin
   is older than this build (found at startup and whenever that card refreshes). */
const zsOutdated = r => (r && r.installs ? r.installs.filter(z => z.installed && !z.current).length : 0);
function setZsBadge(n) {
  const rb = document.querySelector('.rail-btn[data-screen="settings"]');
  if (rb) {
    rb.classList.toggle('has-badge', n > 0);
    rb.title = 'Settings (Alt+3)' + (n ? ' – ' + (n === 1 ? 'a ZBrush plugin needs' : n + ' ZBrush plugins need') + ' updating' : '');
  }
  const tb = document.querySelector('.toc-item[data-card="set-older-zbrush"]');
  if (tb) { tb.classList.toggle('has-badge', n > 0); tb.title = n ? 'Update available' : ''; }
}
async function refreshZsBadge() {
  try { setZsBadge(zsOutdated(await call('get_zscript_bridge'))); } catch (e) { /* no badge */ }
}

function card(title, sub, ...kids) { return h('section', { class: 'card' }, h('h2', { class: 'card-title' }, title, sub ? h('em', null, sub) : null), ...kids); }

/* The rows for the ZScript plugin on ZBrush 2022 to 2025 (install, update, remove, forget, add a folder), shared by
   Settings > Older ZBrush and the Setup screen. paint({installs, bundled}) draws into box; every action ends by calling
   refresh() so the caller can look again (Settings fetches, Setup forces its own poll). extra(z) may add a node to a row. */
function legacyRows(box, { refresh, extra } = {}) {
  // Runs one install or remove. The whole row is locked while it runs (the elevation prompt can sit open for minutes).
  const act = (name, path, btn, rowBtns, busyText) => async () => {
    const was = rowBtns.map(b => b.disabled), label = [...btn.childNodes];
    rowBtns.forEach(b => { b.disabled = true; });
    btn.classList.add('running'); btn.replaceChildren(h('span', { class: 'spin' }), busyText);
    let res = null;
    try { res = await call(name, path); }
    catch (e) { toast('That did not work: ' + e.message, { tone: 'warn' }); }
    if (res && res.busy) {                               // another operation is running: say so, leave the row as it was
      toast(res.message || 'Another install or removal is still running.', { tone: 'warn', ms: 5000 });
      btn.classList.remove('running'); btn.replaceChildren(...label); rowBtns.forEach((b, i) => { b.disabled = was[i]; });
      return;
    }
    if (res) toast(res.message || (res.ok ? 'Done.' : 'That did not work.'), { tone: res.ok ? 'ok' : 'warn', ms: 5000 });
    refresh();
  };
  const paint = r => {
    const rows = r.installs.map(z => {
      const [stext, scls] = !z.installed ? ['Not installed', 'tag dim'] : (z.current ? ['Installed', 'tag cyan'] : ['Update available', 'tag amber']);
      const main = h('button', { class: 'btn small' + (z.installed && z.current ? '' : ' primary'), type: 'button', disabled: !r.bundled }, z.installed ? (z.current ? 'Reinstall' : 'Update') : 'Install');
      const rm = z.installed ? h('button', { class: 'btn small danger-ghost', type: 'button' }, icon('trash', 12), 'Remove') : null;
      const forget = z.added ? iconBtn('x', 'Forget this folder', async () => {
        forget.disabled = true;
        try { const res = await call('forget_zbrush_folder', z.path); toast(res.message || (res.ok ? 'Forgot that folder.' : 'That did not work.'), { tone: res.ok ? 'ok' : 'warn', ms: 4000 }); }
        catch (e) { toast('Could not forget the folder: ' + e.message, { tone: 'warn' }); }
        refresh();
      }) : null;
      const rowBtns = [main, rm, forget].filter(Boolean);
      main.onclick = act('install_zscript_bridge', z.path, main, rowBtns, 'Installing... approve the prompt');
      if (rm) rm.onclick = async () => {
        const ok = await modal({ title: `Remove the plugin from ${z.name}?`,
          body: [h('p', null, 'This deletes the ZOrbit plugin files from this ZBrush install:'), h('p', { class: 'modal-path mono' }, z.path)],
          actions: [{ text: 'Cancel', value: false, focus: true }, { text: 'Remove', value: true, kind: 'danger' }] });
        if (ok) act('remove_zscript_bridge', z.path, rm, rowBtns, 'Removing...')();
      };
      const ex = extra ? extra(z) : null;
      return h('div', { class: 'zrow' }, h('div', { class: 'grow' }, h('div', { class: 'zname' }, z.name, h('span', { class: scls }, stext), ex), h('div', { class: 'zpath mono', title: z.zplugs }, z.path)),
        h('div', { class: 'btn-row' }, main, rm, forget));
    });
    if (!rows.length) rows.push(h('div', { class: 'fhint' }, 'No ZBrush 2022 to 2025 was found. Add a ZBrush folder if you have one.'));
    else if (!r.bundled) rows.push(h('div', { class: 'fhint warn' }, 'This build has no compiled ZScript plugin (ZOrbitBridge.zsc), so there is nothing to install yet.'));
    box.replaceChildren(...rows);
  };
  const addFolder = async () => {
    try {
      const r = await call('add_zbrush_folder');
      if (r.already) toast(r.message || 'That folder is already listed.', { ms: 4000 });
      else if (!r.cancelled) toast(r.message, { tone: r.ok ? 'ok' : 'warn', ms: 5000 });
    } catch (e) { toast('Could not add the folder: ' + e.message, { tone: 'warn' }); }
    refresh();
  };
  return { paint, addFolder };
}

function buildSettingsScreen(root) {
  root.replaceChildren();
  const page = h('div', { class: 'settings' });
  const toc = h('nav', { class: 'toc', 'aria-label': 'Settings sections' });
  const scroll = h('div', { class: 'settings-scroll' }, h('div', { class: 'settings-layout' }, toc, page));
  root.append(scroll);

  // "On this page": built from the cards' titles after every build; highlights the section being read.
  let tocItems = [];
  let pinned = null;          // entry the user clicked; wins until they scroll by hand
  const sectionTop = el => el.getBoundingClientRect().top - scroll.getBoundingClientRect().top + scroll.scrollTop;
  const markActive = () => {
    if (!tocItems.length) return;
    const atEnd = scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 4;
    let active = tocItems[0];
    for (const it of tocItems) if (sectionTop(it.card) <= scroll.scrollTop + 90) active = it;
    if (atEnd) active = tocItems[tocItems.length - 1];
    if (pinned && tocItems.includes(pinned)) active = pinned;
    for (const it of tocItems) {
      const on = it === active;
      it.btn.classList.toggle('on', on);
      if (on) it.btn.setAttribute('aria-current', 'location'); else it.btn.removeAttribute('aria-current');
    }
  };
  const buildToc = () => {
    const cards = [...page.querySelectorAll(':scope > .card')];
    tocItems = cards.map((card, i) => {
      const t = card.querySelector('.card-title');
      const name = t ? [...t.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join('').trim() : 'Section ' + (i + 1);
      card.id = 'set-' + name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
      const btn = h('button', { class: 'toc-item', type: 'button', dataset: { card: card.id }, onclick: () => {
        pinned = item; markActive();
        scroll.scrollTo({ top: Math.max(0, sectionTop(card) - 20), behavior: 'smooth' });
        card.classList.remove('flash'); void card.offsetWidth; card.classList.add('flash');
      } }, name);
      const item = { card, btn };
      return item;
    });
    toc.replaceChildren(h('div', { class: 'micro toc-head' }, 'On this page'), ...tocItems.map(it => it.btn));
    markActive();
  };
  R.gotoCard = id => { const it = tocItems.find(t => t.card.id === id); if (it) it.btn.click(); };
  let tocRaf = 0;
  const unpin = () => { if (pinned) { pinned = null; markActive(); } };
  for (const ev of ['wheel', 'keydown', 'pointerdown', 'touchstart']) scroll.addEventListener(ev, unpin, { passive: true });
  scroll.addEventListener('scroll', () => { if (!tocRaf) tocRaf = requestAnimationFrame(() => { tocRaf = 0; markActive(); }); }, { passive: true });

  const build = () => {
    page.replaceChildren();
    page.append(h('div', { class: 'page-head' }, h('h1', null, 'Settings', h('em', null, 'Appearance and behaviour')), h('p', null, 'How the ring looks, how it opens, and how the app talks to ZBrush. Changes show in the previews straight away and are saved with the Save button.')));

    /* --- geometry with live preview */
    const pimg = h('img', { class: 'ring-img', alt: 'Ring preview', draggable: false });
    const dz = h('div', { class: 'dz-ring' });
    const pwrap = h('div', { class: 'mini-wrap' }, pimg, dz);
    const pbox = h('div', { class: 'mini-stage' }, h('div', { class: 'stage-rings', 'aria-hidden': 'true' }), pwrap, h('div', { class: 'mini-cap micro' }, 'Preview: ' + ((curMenu() && curMenu().title) || '')));
    let msize = 447;
    const paintDZ = () => { const k = (pwrap.clientWidth || 280) / msize, d = ringNum('dead_zone') * 2 * k; dz.style.width = dz.style.height = d + 'px'; };
    const live = () => { paintDZ(); };
    page.append(card('Ring geometry', 'Size and spacing of the ring', h('div', { class: 'split' },
      h('div', { class: 'split-main' },
        sliderRow({ label: 'Ring radius', hint: 'Distance from the centre to the slots', key: 'radius', unit: 'px', onLive: live }),
        sliderRow({ label: 'Slot size', hint: 'Diameter of each icon disc', key: 'slot', unit: 'px', onLive: live }),
        sliderRow({ label: 'Dead zone', hint: 'No slot is picked this close to the centre (dashed circle)', key: 'dead_zone', unit: 'px', onLive: live })),
      pbox)));
    R.preview = async () => {
      const none = !curMenu() || !usableIdx(S.menuId).length;
      pbox.classList.toggle('none', none); cbox.classList.toggle('none', none);
      paintTagPrev();                                          // its own picture: the sample ring when this menu has no tagged brush
      if (none) return;
      const ver = S.version;
      const res = await RingLoader.get(S.menuId, null);       // one request feeds the geometry, animation and colour previews
      if (!res || ver !== S.version || !res.image) return;
      cimg.src = res.image;
      if (settingsPlayer.state === 'idle') { pimg.src = res.image; aimg.src = res.image; }
      msize = res.size || msize; paintDZ();
    };

    /* --- animation */
    const aimg = h('img', { class: 'ring-img', alt: 'Animation preview', draggable: false });
    const abtn = h('button', { class: 'btn small stage-play', type: 'button' });
    const astage = h('div', { class: 'mini-stage anim' }, h('div', { class: 'stage-rings', 'aria-hidden': 'true' }), h('div', { class: 'mini-wrap' }, aimg), abtn);
    const restoreStatic = async () => { const res = await RingLoader.get(S.menuId, null); if (res && res.image && settingsPlayer.state === 'idle') aimg.src = res.image; };
    const settingsPlayer = makePlayer(() => aimg, restoreStatic, st => {
      abtn.replaceChildren(st === 'loading' ? h('span', { class: 'spin' }) : icon(st === 'playing' ? 'stop' : 'play', 12), st === 'loading' ? 'Rendering...' : (st === 'playing' ? 'Stop' : 'Replay'));
      abtn.disabled = st === 'loading';
    });
    settingsPlayer.stop(); abtn.replaceChildren(icon('play', 12), 'Replay');
    abtn.onclick = () => { if (usableIdx(S.menuId).length) settingsPlayer.play(S.menuId, true); else toast('The current menu has no usable items to animate.', { tone: 'warn' }); };
    restoreStatic();
    const anims = (S.opts && S.opts.animations) || Object.keys(ANIM_INFO);
    const cur = ring().animation || S.defaults.animation;
    const own = Object.entries(S.cfg.menus).filter(([, m]) => m.animation).map(([id, m]) => m.title || id);
    page.append(card('Open animation', 'Pick one to see it play', h('div', { class: 'split anim-split' }, astage,
      choiceCards(anims.map(a => [a, a[0].toUpperCase() + a.slice(1), ANIM_INFO[a] || '']), cur, v => { settingsPlayer.stop(); setRing('animation', v); setTimeout(() => abtn.onclick(), 0); }, 'anim-cards', 'Open animation')),
      h('div', { class: 'fhint' }, own.length
        ? 'Used by every menu except ' + own.map(t => '\u201c' + t + '\u201d').join(', ') + ', which ' + (own.length === 1 ? 'has its own' : 'have their own') + ' (set on the Menus screen).'
        : 'Used by every menu. A menu can have its own instead: pick it on the Menus screen.')));

    /* --- labels */
    const labelOpts = (S.opts && S.opts.labels) || ['name', 'none'];
    const LAB = { name: ['Icon and name', 'Each slot shows its label underneath.'], none: ['Icon only', 'A cleaner ring. Names appear only in this Studio.'] };
    page.append(card('Labels', null, choiceCards(labelOpts.map(l => [l, (LAB[l] || [l, ''])[0], (LAB[l] || [l, ''])[1]]), ring().labels || S.defaults.labels, v => setRing('labels', v), 'two', 'Labels')));

    /* --- tag colours: how a brush's first tag shows on its slot (tag slots always show their tag's colour).
       Three effects, each a switch with its own controls; tint and glow together are the stored tag_colors. */
    const tc = () => ring().tag_colors || S.defaults.tag_colors || 'tint';
    const tintOn = () => tc() === 'tint' || tc() === 'both', glowOn = () => tc() === 'glow' || tc() === 'both';
    const setTc = (tint, glow) => setRing('tag_colors', tint && glow ? 'both' : tint ? 'tint' : glow ? 'glow' : 'none');
    const bandDef = S.defaults.tag_band && S.defaults.tag_band !== 'none' ? S.defaults.tag_band : 'medium';
    let bandWas = ring().tag_band && ring().tag_band !== 'none' ? ring().tag_band : bandDef;     // the thickness to come back to
    const bandOn = () => (ring().tag_band || S.defaults.tag_band) !== 'none';
    const cap = t => t[0].toUpperCase() + t.slice(1);
    const tcRows = [];                                    // [row, is its effect on]: rows of a switched-off effect are dimmed and disabled
    const paintTc = () => {
      for (const [row, on] of tcRows) {
        const live = on();
        row.classList.toggle('off', !live);
        row.querySelectorAll('input, button').forEach(c => { c.disabled = !live; });
      }
    };
    const segRow = ({ label, hint, key, opts, on, onPick }) => {
      const row = h('div', { class: 'srow' }, h('div', { class: 'slabel' }, h('span', null, label), hint ? h('small', null, hint) : null),
        choiceCards(opts, onPick ? bandWas : ring()[key] || S.defaults[key], onPick || (v => setRing(key, v)), 'seg', label));
      tcRows.push([row, on]); return row;
    };
    const opacity = (key, on) => { const row = sliderRow({ label: 'Opacity', key, step: 5, scale: 100, unit: '%' }); tcRows.push([row, on]); return row; };
    const group = ({ label, hint, on, set, rows }) => h('div', { class: 'tgroup' },
      h('div', { class: 'tg-head' }, h('div', { class: 'slabel' }, h('span', null, label), h('small', null, hint)), toggleSwitch(on(), v => { set(v); paintTc(); }, label)),
      h('div', { class: 'tg-body' }, ...rows));
    const bandOpts = ((S.opts && S.opts.tag_bands) || ['none', 'hairline', 'narrow', 'medium', 'wide']).filter(v => v !== 'none').map(v => [v, cap(v), '']);
    const BLEND = { multiply: 'Darken', overlay: 'Keep highlights' };
    const timg = h('img', { class: 'ring-img pending', alt: 'Ring preview with the current tag colours', draggable: false, onload: () => timg.classList.remove('pending') });   // hidden until it has a picture
    const tcap = h('div', { class: 'mini-cap micro' });
    const tnote = h('div', { class: 'fhint' });
    const tbox = h('div', { class: 'mini-stage' }, h('div', { class: 'stage-rings', 'aria-hidden': 'true' }), h('div', { class: 'mini-wrap' }, timg), tcap);
    // The current menu when it has a tagged brush to show, else the backend's sample ring.
    const hasTagged = m => !!m && (m.items || []).some(it => { const ik = kindOf(it); return isLib(ik) && firstTag(ik, it[ik]); });
    let tTok = 0;
    const paintTagPrev = async () => {
      const sample = !hasTagged(curMenu()), tok = ++tTok, ver = S.version;
      tcap.textContent = sample ? 'Sample ring' : 'Preview: ' + (curMenu().title || S.menuId);
      tnote.textContent = sample ? 'This menu has no tagged items yet, so the sample puts your tags on a few library brushes.' : '';
      const res = await RingLoader.get(sample ? SAMPLE_MENU : S.menuId, null, null, 'tags');
      if (tok !== tTok || !res || ver !== S.version) return;
      if (res.image) timg.src = res.image;
      else if (res.error || (res.problems || []).length) tnote.textContent = 'No preview: ' + (res.problems || [])[0];
    };
    page.append(card('Tag colours', "How a brush's tags show on its slots", h('div', { class: 'split tag-split' }, h('div', { class: 'split-main' },
      group({ label: 'Icon tint', hint: 'A coloured rim, and the tag colour laid over the icon', on: tintOn, set: v => setTc(v, glowOn()), rows: [
        opacity('tag_tint_opacity', tintOn),
        segRow({ label: 'Style', hint: 'Gradient is stronger towards the rim', key: 'tag_tint_style', on: tintOn, opts: ((S.opts && S.opts.tint_styles) || ['flat', 'gradient']).map(v => [v, cap(v), '']) }),
        segRow({ label: 'Blend', key: 'tag_tint_blend', on: tintOn, opts: ((S.opts && S.opts.tint_blends) || ['multiply', 'overlay']).map(v => [v, BLEND[v] || cap(v), '']) })] }),
      group({ label: 'Glow', hint: 'A soft halo in the tag colour around the slot', on: glowOn, set: v => setTc(tintOn(), v), rows: [
        opacity('tag_glow_opacity', glowOn)] }),
      group({ label: 'Band', hint: 'A coloured strip through the slots, one stretch per slot', on: bandOn, set: v => setRing('tag_band', v ? bandWas : 'none'), rows: [
        segRow({ label: 'Thickness', on: bandOn, opts: bandOpts, onPick: v => { bandWas = v; setRing('tag_band', v); } }),
        opacity('tag_band_opacity', bandOn)] })),
      h('div', { class: 'tag-prev' }, tbox, tnote))));
    paintTc();

    /* --- colours (the preview is the same picture as the geometry card's: one request per edit) */
    const colorPaints = [];
    const colorRows = Object.keys(COLOR_INFO).map(k => {
      const sw = h('input', { type: 'color', class: 'swatch', value: colorVal(k), 'aria-label': COLOR_INFO[k][0] + ' colour' });
      const hex = h('input', { class: 'inp mono hex', type: 'text', value: colorVal(k), maxlength: '7', spellcheck: 'false', 'aria-label': COLOR_INFO[k][0] + ' hex value' });
      const hmsg = h('span', { class: 'hex-msg', role: 'status' });
      const rs = iconBtn('undo', 'Reset to default (' + S.defaults.colors[k] + ')', () => { const c = ring().colors; if (c) { delete c[k]; if (!Object.keys(c).length) delete ring().colors; } commit(); paint(); }, 'reset');
      const showReset = v => { rs.style.visibility = v.toLowerCase() !== S.defaults.colors[k].toLowerCase() ? 'visible' : 'hidden'; };
      const paint = () => { const v = colorVal(k); sw.value = v; hex.value = v; hex.classList.remove('bad'); hmsg.textContent = ''; showReset(v); };
      sw.addEventListener('input', () => { setColor(k, sw.value); paint(); });
      hex.addEventListener('input', () => {
        const n = normHex(hex.value), bad = !n;
        hex.classList.toggle('bad', bad); hmsg.textContent = bad ? 'Use #rrggbb' : '';
        if (n && hex.value.trim().replace('#', '').length === 6) { setColor(k, n); sw.value = n; showReset(n); }   // short forms wait for Enter or blur
      });
      const apply = () => { const n = normHex(hex.value); if (n && n !== colorVal(k).toLowerCase()) setColor(k, n); paint(); };
      hex.addEventListener('blur', apply);
      hex.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); apply(); } });
      colorPaints.push(paint);
      paint();
      return h('div', { class: 'crow' }, sw, h('div', { class: 'slabel' }, h('span', null, COLOR_INFO[k][0]), h('small', null, COLOR_INFO[k][1])), h('div', { class: 'hexwrap' }, hex, hmsg), rs);
    });
    const cimg = h('img', { class: 'ring-img', alt: 'Ring preview with the current colours', draggable: false });
    const cbox = h('div', { class: 'mini-stage' }, h('div', { class: 'stage-rings', 'aria-hidden': 'true' }), h('div', { class: 'mini-wrap' }, cimg), h('div', { class: 'mini-cap micro' }, 'Preview: ' + ((curMenu() && curMenu().title) || '')));
    page.append(card('Colours', 'Applied to the ring in the app', h('div', { class: 'split' }, h('div', { class: 'split-main' }, h('div', { class: 'colors' }, colorRows)), cbox),
      h('div', { class: 'btn-row' }, h('button', { class: 'btn small', type: 'button', onclick: () => { delete ensureRing().colors; commit(); colorPaints.forEach(f => f()); } }, icon('undo', 12), 'Reset all colours'))));

    /* --- behaviour */
    page.append(card('Behaviour', null,
      switchRow({ label: 'Flick to pick', hint: 'Moving the cursor out past a slot picks it straight away, without releasing the hotkey or clicking.', key: 'flick' }),
      switchRow({ label: 'Open submenus on hover', hint: 'Reaching a submenu slot opens that submenu, centred on the slot. Keep holding the hotkey to pick in it by releasing or flicking.', key: 'hover_submenus' }),
      sliderRow({ label: 'Tap time', hint: 'A hotkey press shorter than this is a tap: the ring stays open for a click. Holding longer and releasing picks the item under the cursor.', key: 'tap_ms', step: 10, unit: 'ms' }),
      sliderRow({ label: 'Auto-close', hint: 'An open ring closes by itself after this long.', key: 'timeout_s', unit: 's' })));

    /* --- bridge */
    const bridge = () => { if (!S.cfg.bridge || typeof S.cfg.bridge !== 'object') S.cfg.bridge = {}; return S.cfg.bridge; };
    const bmode = (S.cfg.bridge && S.cfg.bridge.mode) || 'auto';
    const keyWrap = h('div', { class: 'bridge-key' });
    let paintZNote = () => {};      // the Older ZBrush card's paragraph about binding the key; set further down
    const paintKey = () => {
      const mode = (S.cfg.bridge && S.cfg.bridge.mode) || 'auto';
      keyWrap.classList.toggle('dim', mode === 'message');
      keyWrap.replaceChildren(field('Bridge key', hotkeyField({ what: 'Bridge key', value: (S.cfg.bridge && S.cfg.bridge.key) || '', mods: { ctrl: false, alt: true, shift: false }, placeholder: 'Not set (F9 is the usual choice)',
        onChange: v => { if (v) bridge().key = v; else delete bridge().key; commit(); paintZNote(); } }),
        mode === 'message' ? 'Not used in Message mode, but kept in case you switch back.' : 'Must be bound in ZBrush to Zplugin > ZOrbit > Apply. Ctrl and Shift are rejected because ZBrush reads them as mask and smooth. A bare F-key is best.'));
    };
    page.append(card('ZBrush bridge', 'How a pick reaches ZBrush',
      choiceCards(['auto', 'message', 'key'].map(m => [m, BRIDGE_INFO[m][0], BRIDGE_INFO[m][1]]), bmode, v => { bridge().mode = v; commit(); paintKey(); }, 'bridge-cards', 'How a pick reaches ZBrush'),
      keyWrap));
    paintKey();

    /* --- ZScript bridge for ZBrush 2022-2025 (acts straight away, not part of the menus) */
    const zbox = h('div', { class: 'zrows' }, h('div', { class: 'fhint' }, 'Looking for ZBrush...'));
    let zCount = null;          // installs found by the last look; null until the first answer
    const znote = h('div', { class: 'fhint', hidden: true });
    // The plugin's Apply button brings F9 as its own hotkey (ZOrbitBridge.txt); any other key is bound by hand.
    // Derived from the key chosen above every time, and compared as a whole chord: "Alt+F9" is not "F9".
    paintZNote = () => {
      const zkey = ((S.cfg.bridge && S.cfg.bridge.key) || 'F9').trim();
      const bind = zkey.toLowerCase() === 'f9'
        ? ['After installing, restart ZBrush. Apply comes with ', h('b', null, 'F9'), ' as its hotkey, so there is nothing to bind.']
        : ['After installing, restart ZBrush, Ctrl+Alt+click Zplugin > ZOrbit > Apply, press', h('b', null, zkey), ' and choose Preferences > Hotkeys > Store. (Only F9 works without this step.)'];
      znote.hidden = !zCount;
      znote.replaceChildren('These versions have no Python API, so they get a ZScript plugin with the same Zplugin > ZOrbit palette. It has no listener, so every pick there uses the bridge key, whatever the mode above. ', ...bind, ' A ZBrush under Program Files asks for administrator rights to install.');
    };
    let zgen = 0;                                              // a slower earlier listing must not replace a newer one
    const zpaint = async () => {
      if (R.zpaint && R.zpaint !== zpaint) return R.zpaint();   // this card was rebuilt (undo, reload): paint the live one
      const gen = ++zgen;
      let r;
      try { r = await call('get_zscript_bridge'); if (gen !== zgen) return; } catch (e) { if (gen !== zgen) return; zbox.replaceChildren(h('div', { class: 'fhint bad' }, 'Could not look for ZBrush: ' + e.message)); return; }
      setZsBadge(zsOutdated(r));
      lz.paint(r);
      zCount = r.installs.length;
      paintZNote();
    };
    const lz = legacyRows(zbox, { refresh: zpaint });
    const addBtn = h('button', { class: 'btn small', type: 'button', onclick: () => lz.addFolder() }, icon('folder', 12), 'Add a ZBrush folder...');
    page.append(card('Older ZBrush', 'ZBrush 2022 to 2025. Acts straight away.', znote, zbox, h('div', { class: 'btn-row' }, addBtn)));
    paintZNote();
    R.zpaint = zpaint;
    zpaint();

    /* --- tags (saved as they change in tags.json, not part of the menus file) */
    page.append(card('Tags', 'Labels for your brushes, alphas, materials and textures. Saved straight away.',
      h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Brush tags'),
        h('div', { class: 'fhint' }, 'Tags group your brushes, alphas, materials and textures so you can filter the Library by them. An item can carry several. Tags are not part of Save or Undo.'),
        h('div', { class: 'fhint mono tag-path', hidden: !S.tagsPath }, S.tagsPath)),
        manageTagsBtn('btn'))));

    /* --- browser (browser.hotkey; the object is dropped again when it ends up empty) */
    const browserObj = () => { if (!S.cfg.browser || typeof S.cfg.browser !== 'object') S.cfg.browser = {}; return S.cfg.browser; };
    const bOwner = hotkey => (hotkey ? hotkeyOwner(hotkey, BROWSER) : null);
    const bsay = owner => (owner ? `Also used by ${ownerName(owner)}. That menu wins, so this hotkey will not open the browser.` : '');
    const bhk = hotkeyField({ what: 'Browser hotkey', value: (S.cfg.browser && typeof S.cfg.browser === 'object' && S.cfg.browser.hotkey) || '', placeholder: 'No hotkey (open it from a Browser slot)', onChange: str => {
      const b = browserObj();
      if (str) b.hotkey = str; else delete b.hotkey;
      if (!Object.keys(b).length) delete S.cfg.browser;
      const owner = bOwner(str);
      bhk.say(bsay(owner), 'warn');
      commit();
    } });
    page.append(card('Browser', 'A window of its own',
      h('div', { class: 'browser-key' }, field('Hotkey', bhk, 'Shows the browser; pressed over it, it gives ZBrush the keyboard back. The browser also opens from a Browser slot and the tray menu.')),
      h('div', { class: 'browser-open' }, h('button', { class: 'btn small', type: 'button', title: 'Open the browser in its own window', onclick: openBrowserWindow }, icon('k_browser', 13), 'Open the browser'))));
    { const o0 = bOwner(S.cfg.browser && S.cfg.browser.hotkey); if (o0) bhk.say(bsay(o0), 'warn'); }

    /* --- studio (preferences of this window, saved immediately, not part of the menus file) */
    const updNote = h('div', { class: 'fhint upd-status', role: 'status' });
    let updTok = 0;
    const paintUpdate = u => {
      if (!u || S.prefs.check_updates === false) { updNote.textContent = ''; return; }
      const newer = !!(u.newer && u.latest);
      updNote.textContent = newer ? 'Version ' + u.latest + ' available' : (u.latest ? 'Up to date' : 'Could not reach GitHub');
      updNote.className = 'fhint upd-status' + (newer ? ' new' : (u.latest ? '' : ' warn'));
    };
    const checkNow = async () => {
      const tok = ++updTok;
      updNote.textContent = 'Checking...'; updNote.className = 'fhint upd-status';
      let u = null;
      try { u = window.RadialUpdate && await window.RadialUpdate.check(); } catch (e) { u = { latest: null }; }
      if (tok !== updTok) return;
      if (u) paintUpdate(u); else updNote.textContent = '';
    };
    if (window.RadialUpdate && window.RadialUpdate.last) paintUpdate(window.RadialUpdate.last);
    page.append(card('Studio', 'Preferences for this window. Saved straight away.',
      h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Show the Licence button'),
        h('div', { class: 'fhint' }, 'The Licence screen is a joke: ZOrbit is free software and needs no licence. Turn this off to hide its button.')),
        toggleSwitch(licenceVisible(), async v => { const ok = await setPref('show_licence', v); if (ok) toast(v ? 'The Licence button is back. It missed you.' : 'Licence button hidden.', { ms: 2800 }); return ok; }, 'Show the Licence button')),
      h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Check for updates'),
        h('div', { class: 'fhint' }, 'When Studio opens, it asks GitHub for the newest release and shows it next to the version at the top. Nothing about you or your menus is sent.'), updNote),
        toggleSwitch(S.prefs.check_updates !== false, async v => {
          const ok = await setPref('check_updates', v);
          if (!ok) return false;
          if (v) checkNow(); else { updTok++; updNote.textContent = ''; if (window.RadialUpdate) window.RadialUpdate.check(); }
          return true;
        }, 'Check for updates'))));

    /* --- import and export (one file with the menus, the ring settings and the tags) */
    const ioBtns = [
      h('button', { class: 'btn small', type: 'button', title: 'Save the menus, ring settings and tags to a file', onclick: () => ioRun(ioBtns, exportSettings) }, icon('folder', 12), 'Export...'),
      h('button', { class: 'btn small', type: 'button', title: 'Load menus, ring settings and tags from a file', onclick: () => ioRun(ioBtns, importSettings) }, icon('folder', 12), 'Import...')];
    page.append(card('Import and export', 'Back up your setup or move it to another PC.',
      h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Settings file'),
        h('div', { class: 'fhint' }, 'The file holds your menus, the ring settings and your tags. The Studio window preferences and the usage counts are not included, as they belong to this PC. Export saves what is on screen, unsaved changes included. Import shows what is in a file first, and the menus and settings it loads can be undone.')),
        h('div', { class: 'btn-row' }, ...ioBtns))));
    R.preview();
  };
  R.settings = () => { build(); buildToc(); };
  build();
  buildToc();
}

/* ================================================================== STATUS screen */
let statusTimer = null, statusBusy = false, appStarting = false;
const LOG_LINES = 40;
const pad2 = n => String(n).padStart(2, '0');
const localDate = d => d.getFullYear() + '-' + pad2(d.getMonth() + 1) + '-' + pad2(d.getDate());

/* Copies text to the clipboard. Falls back to a throw-away textarea when the async API is missing or refused. */
async function copyText(text) {
  try {                                                      // a pending permission prompt must not hang the button: give up on it after a moment
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await Promise.race([navigator.clipboard.writeText(text), new Promise((_, no) => setTimeout(() => no(new Error('clipboard timed out')), 1200))]);
      return true;
    }
  } catch (e) { /* try the fallback */ }
  const prev = document.activeElement;
  const ta = h('textarea', { style: 'position:fixed;left:-9999px;top:0;opacity:0', 'aria-hidden': 'true', tabindex: '-1', readOnly: true });
  ta.value = text;
  document.body.append(ta); ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  ta.remove();
  if (prev && prev.focus && document.contains(prev)) prev.focus();
  return ok;
}

/* What the last get_status said, wherever it was asked from. S.appDown: true = ZBrush runs but the app does not (dot on the
   Status rail button), false = the app runs, null = unknown or ZBrush is off. S.statusAt is when that answer was made. */
function noteStatus(st) {
  if (!st) return;
  S.status = st;
  S.statusAt = typeof st.checked_at === 'number' ? st.checked_at * 1000 : Date.now();
  S.appDown = st.app_running ? false : (st.zbrush_running && st.zbrush_check_ok !== false ? true : null);
  const rb = document.querySelector('.rail-btn[data-screen="status"]');
  if (rb) {
    rb.classList.toggle('has-down', S.appDown === true);
    rb.title = 'Status (Alt+4)' + (S.appDown === true ? ' \u2013 The app is not running' : '');
  }
}
/* One quiet look at the status for the rail dot, from outside the Status screen. */
async function refreshAppDown() {
  try { noteStatus(await call('get_status')); } catch (e) { /* no dot */ }
}

/* Starts the app and says how it went. Shared by the Status and Setup screens. paint() is called when the starting state
   flips (appStarting is the flag to read). Resolves to { log } (the lines a failed start brought back), or null when a
   start is already under way. The caller looks again at the status afterwards. */
async function startAppFlow({ paint }) {
  if (appStarting) return null;
  appStarting = true; paint();
  let r = null;
  try { r = await call('start_app'); }
  catch (e) { toast('Could not start the app: ' + (e.message || e), { tone: 'warn', ms: 5000 }); }
  appStarting = false; paint();
  let log = [];
  if (r && r.ok && r.running) toast('Started.', { tone: 'ok', ms: 3000 });
  else if (r && r.reason === 'failed') {
    toast(r.message || 'The app did not start.', { tone: 'warn', ms: 6000 });
    log = Array.isArray(r.log) ? r.log.map(String) : [];
  } else if (r) toast(r.message || (r.reason === 'zbrush' ? 'ZBrush must be running first.' : 'Could not start the app.'), { tone: 'warn', ms: 4500 });
  return { log };
}

function buildStatusScreen(root) {
  root.replaceChildren();
  const page = h('div', { class: 'settings status' });
  const grid = h('div', { class: 'status-grid' });
  const logBox = h('div', { class: 'logbox mono', tabindex: '0', role: 'log', 'aria-live': 'off', 'aria-label': 'App log' });   // it is rebuilt every few seconds, so no live announcements
  const stamp = h('span', { class: 'stamp mono' });
  let startLog = [];                       // lines a failed start brought back; kept (highlighted) until the app runs or Start is pressed again
  let curLines = [];                       // the raw lines on screen now: what Copy log copies
  let lastAsk = 0;                         // when the last get_status was asked

  // The Start app button lives on the app card. One element, moved into each freshly built card.
  const startBtn = h('button', { class: 'btn small primary start-btn', type: 'button', onclick: () => startApp() });
  const paintStart = st => {
    const running = !!(st && st.app_running);
    const noZ = !!st && !st.zbrush_running && st.zbrush_check_ok !== false;
    const off = appStarting || running || noZ || !st;
    startBtn.disabled = off;
    startBtn.replaceChildren(...(appStarting ? [h('span', { class: 'spin' }), 'Starting...'] : [icon('play', 12), running ? 'Running' : 'Start app']));
    startBtn.classList.toggle('running', appStarting);
    startBtn.title = appStarting ? 'Starting the app...' : running ? 'The app is already running' : noZ ? 'ZBrush must be running first'
      : (st && st.zbrush_check_ok === false ? 'Could not check for ZBrush. Try anyway.' : 'Start the ZOrbit app');
    if (appStarting) startBtn.setAttribute('aria-busy', 'true'); else startBtn.removeAttribute('aria-busy');
  };
  async function startApp() {
    if (appStarting) return;
    startLog = [];
    const out = await startAppFlow({ paint: () => paintStart(S.status) });
    if (!out) return;
    startLog = out.log;
    while (statusBusy) await sleep(60);       // a poll already in flight may predate the launch
    await refresh();
    if (startLog.length) logBox.scrollTop = logBox.scrollHeight;
  }

  const folder = which => async () => { try { await call('open_folder', which); } catch (e) { toast('Could not open the folder.', { tone: 'warn' }); } };
  const copyLog = async () => {
    if (!curLines.length) { toast('The log is empty.', { ms: 1800 }); return; }
    const ok = await copyText(curLines.join('\n'));
    toast(ok ? `Copied ${curLines.length} line${curLines.length === 1 ? '' : 's'}` : 'Could not copy the log.', { tone: ok ? 'ok' : 'warn', ms: 2200 });
  };
  page.append(h('div', { class: 'page-head' }, h('h1', null, 'Status'), h('p', null, 'Whether ZBrush and the ZOrbit app are running, and whether the bridge between them is healthy.')),
    grid,
    card('App log', 'Last lines of radiald.log', logBox,
      h('div', { class: 'btn-row between' }, h('div', { class: 'btn-row' },
        h('button', { class: 'btn', type: 'button', onclick: copyLog }, icon('copy', 13), 'Copy log'),
        h('button', { class: 'btn', type: 'button', title: 'Where the app log is kept', onclick: folder('data') }, icon('folder', 13), 'Open logs folder'),
        h('button', { class: 'btn', type: 'button', title: 'Where radial.json lives', onclick: folder('config') }, icon('external', 13), 'Open config folder')),
        h('span', { class: 'live' }, h('i', { class: 'livedot' }), 'Auto-refresh every 3 s ', stamp))));
  root.append(h('div', { class: 'settings-scroll' }, page));

  const stat = (title, ok, text, sub, tone, extra) => h('div', { class: 'scard ' + (tone || (ok ? 'ok' : 'off')) }, h('div', { class: 'micro' }, title),
    h('div', { class: 'sval' + (extra ? ' has-act' : '') }, h('i', { class: 'sdot' }), text, extra || null), sub ? h('div', { class: 'ssub' }, sub) : null);
  const tickStamp = () => {
    if (!S.statusAt) { setText(stamp, ''); return; }
    const s = Math.max(0, Math.floor((Date.now() - S.statusAt) / 1000));
    setText(stamp, 'Updated ' + (s < 90 ? s + ' s' : Math.round(s / 60) + ' min') + ' ago');
  };
  const paint = st => {
    if (!st) return;
    const l = st.listener;
    const keyOnly = st.bridge_mode === 'key' || !!st.legacy_only;      // a listener is not part of the picture
    const ltone = keyOnly ? 'neutral' : (!l ? 'off' : (l.alive && l.verified ? 'ok' : 'warn'));
    const ltext = keyOnly ? 'Not needed (key bridge)' : (!l ? 'Not found' : (!l.alive ? 'Stale' : (l.verified ? 'Connected' : 'Found, unverified')));
    const lsub = keyOnly ? 'Picks arrive through the bridge key'
      : (!l ? 'The ZBrush plugin has not announced a listener window. Load the ZOrbit plugin in ZBrush.' : (!l.alive ? 'The listener window no longer exists. Restart ZBrush or reload the plugin.' : (l.verified ? 'Picks are delivered by message.' : 'The window exists, but no message has been confirmed yet.')));
    const unsure = st.zbrush_check_ok === false;                       // the process look-up itself failed: do not claim ZBrush is off
    const hadFocus = document.activeElement === startBtn;
    paintStart(st);
    grid.replaceChildren(
      unsure ? stat('ZBrush', false, 'Could not check', 'Studio could not tell whether ZBrush is running.', 'neutral')
        : stat('ZBrush', st.zbrush_running, st.zbrush_running ? 'Running' : 'Not running', st.zbrush_running ? null : 'The app starts together with ZBrush.'),
      stat('ZOrbit app',st.app_running, st.app_running ? 'Running' : 'Not running',
        st.app_running ? 'Listening for your hotkeys.' : (st.zbrush_running || unsure ? 'Press Start app to launch it.' : 'Open ZBrush first; the app starts with it.'), null, startBtn),
      stat('Bridge listener', ltone === 'ok', ltext, lsub, ltone),
      h('div', { class: 'scard last' }, h('div', { class: 'micro' }, 'Last pick'), h('div', { class: 'sval mono small' }, st.last_pick || 'Nothing picked yet'), h('div', { class: 'ssub' }, 'The most recent item sent to ZBrush.')));
    if (hadFocus && !startBtn.disabled) startBtn.focus();
    if (st.app_running) startLog = [];
    const atBottom = logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 8;
    const backend = (st.app_log || []).map(String);
    const extra = startLog.filter(x => !backend.includes(x));
    curLines = backend.concat(extra).slice(-LOG_LINES);
    const forced = new Set(extra);
    const today = localDate(new Date());
    logBox.replaceChildren(...(curLines.length ? curLines.map(line => {
      const m = /^(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)(\.\d+)?\s+(.*)$/.exec(line);
      const cls = /\bpick #/.test(line) ? 'pick' : (forced.has(line) || /\b(error|errors|fail\w*|exception|traceback|warn\w*)\b/i.test(line) ? 'err' : '');
      return h('div', { class: 'logline ' + cls }, m ? [h('span', { class: 't' }, (m[1] === today ? '' : m[1] + ' ') + m[2]), ' ', m[4]] : line);
    }) : [h('div', { class: 'logline dim' }, 'The log is empty.')]));
    if (atBottom) logBox.scrollTop = logBox.scrollHeight;
    tickStamp();
  };
  async function refresh() {
    if (statusBusy) return; statusBusy = true; lastAsk = Date.now();
    try { const st = await call('get_status'); noteStatus(st); paint(st); }
    catch (e) { grid.replaceChildren(h('div', { class: 'scard off' }, h('div', { class: 'micro' }, 'Status'), h('div', { class: 'sval' }, h('i', { class: 'sdot' }), 'Unavailable'), h('div', { class: 'ssub' }, String(e.message || e)))); }
    statusBusy = false;
  }
  R.status = refresh;
  if (S.status && !S.status._partial) paint(S.status);           // from the last answer (not one the Setup screen filled in, which has no log or last pick), so the stamp shows its real age
  refresh();
  clearInterval(statusTimer);
  // one beat per second: the stamp counts up, and a poll goes out once the last answer is 3 s old
  statusTimer = setInterval(() => {
    if (S.screen !== 'status' || document.hidden) return;
    tickStamp();
    if (Date.now() - lastAsk >= 2900) refresh();
  }, 1000);
}

/* ================================================================== SETUP screen */
/* Amber dot on the Setup rail button while a hard check fails (no ZBrush is ready, or a running one is not set up). */
function setSetupBadge(d) {
  const rb = document.querySelector('.rail-btn[data-screen="setup"]');
  if (!rb) return;
  const bad = !!(d && d.hard_fail);
  rb.classList.toggle('has-badge', bad);
  rb.title = 'Setup (Alt+6)' + (bad ? ' – Something needs attention' : '');
}
/* One quiet look for the rail dot, from outside the Setup screen. */
async function refreshSetupBadge() {
  try { setSetupBadge(await call('get_setup')); } catch (e) { /* no dot */ }
}
/* The Setup answer also says whether ZBrush and the app run, so the Status rail dot is kept right from it. Fields the
   Setup answer does not carry (log lines, last pick) stay as the last full get_status left them. */
function noteSetupStatus(d) {
  const app = d.app || {}, zb = d.zbrush || {};
  const had = S.status;
  noteStatus(Object.assign({}, had || {}, { app_running: !!app.running, zbrush_running: !!zb.running, zbrush_check_ok: zb.check_ok, checked_at: d.checked_at != null ? d.checked_at : d.now },
    had ? {} : { _partial: true }));
}

const PROC_PRIORITY = ['loaded', 'restart', 'starting', 'unknown', 'not_loaded'];
const PROC_TAG = { loaded: ['Plugin loaded', 'tag cyan'], restart: ['Restart ZBrush', 'tag amber'], starting: ['Starting', 'tag dim'], unknown: ['Not sure yet', 'tag dim'], not_loaded: ['No plugin loaded', 'tag dim'] };
const procTag = state => (PROC_TAG[state] ? h('span', { class: PROC_TAG[state][1] }, PROC_TAG[state][0]) : null);
const PICK_VIA = { listener: 'the listener', key: 'the bridge key', zscript: 'ZScript' };

/* The menu the Setup screen talks about: the one on Q, else the first with a hotkey, else the first. */
function setupMenu() {
  const menus = (S.cfg && S.cfg.menus) || {}, ids = Object.keys(menus), hk = id => menus[id] && menus[id].hotkey;
  const id = ids.find(i => hkNorm(hk(i)) === 'q') || ids.find(i => hk(i)) || ids[0];
  return id ? { id, title: menus[id].title || id, hotkey: hk(id) || '' } : null;
}

/* The five steps from one get_setup answer. Pure: the same data gives the same steps, and every field in a step is
   something that is drawn (nothing that ticks, like ages), so JSON of a step tells whether it needs painting again.
   ctx: { menu: setupMenu(), done: setup_done }. */
function deriveSteps(d, tryFrom, ctx) {
  const installs = d.installs || [], unmatched = d.unmatched_procs || [], env = d.env || {}, zb = d.zbrush || {};
  const now = typeof d.now === 'number' ? d.now : Date.now() / 1000;
  const topProc = i => { const have = (i.procs || []).map(p => p.state); return PROC_PRIORITY.find(s => have.includes(s)) || null; };
  const plugin = i => i.plugin || {};
  const list = names => (names.length < 3 ? names.join(' and ') : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1]);

  /* 1. ZBrush found */
  const ready = installs.filter(i => i.ready), unready = installs.filter(i => !i.ready);
  const s1 = { id: 'found', title: 'ZBrush found',
    state: ready.length ? 'ok' : (installs.length ? 'warn' : 'off'),
    modern: installs.filter(i => i.kind === 'modern').map(i => {
      const st = plugin(i).state;
      return { name: i.name, path: i.path, proc: topProc(i),
        tag: st === 'ok' ? 'Registered' : (st === 'no_bridge' ? 'Plugin folder missing' : 'Not registered'),
        tone: st === 'ok' ? 'cyan' : (st === 'no_bridge' ? 'dim' : 'amber'),
        fix: !!env.can_fix && st !== 'ok' && st !== 'no_bridge' };
    }),
    legacy: { bundled: !!d.bundled, installs: installs.filter(i => i.kind === 'legacy').map(i => ({ name: i.name, path: i.path, added: !!i.added,
      installed: !!plugin(i).installed, current: !!plugin(i).current, zplugs: plugin(i).zplugs, proc: topProc(i) })) },
    others: (env.other_zorbit || []).map(o => ({ path: o.path, exists: o.exists !== false })),
    bridgeMissing: !!(d.bridge && d.bridge.kind === 'missing') };
  s1.detail = ready.length
    ? list(ready.map(i => i.name)) + (ready.length === 1 ? ' is ready.' : ' are ready.') + (unready.length ? ' ' + list(unready.map(i => i.name)) + (unready.length === 1 ? ' still needs' : ' still need') + ' the plugin.' : '')
    : (installs.length ? 'ZBrush was found, but the ZOrbit plugin is not set up for it yet.' : 'No ZBrush was found. Add its folder if you have one.');

  /* 2. Plugin loaded in ZBrush */
  const procs = [];
  for (const i of installs) for (const p of (i.procs || [])) procs.push({ name: i.name, ready: !!i.ready, state: p.state, why: p.why || '' });
  const elevated = unmatched.some(u => u.elevated !== false);
  const worst = PROC_PRIORITY.slice(1).map(s => procs.find(p => p.state === s)).find(Boolean);
  const loaded = procs.filter(p => p.state === 'loaded');
  const s2 = { id: 'loaded', title: 'Plugin loaded in ZBrush', locked: false,
    rows: procs.map(p => ({ name: p.name, state: p.state, why: p.why })),
    elevated,
    app: { running: !!(d.app && d.app.running), zbrush: !!zb.running, checkOk: zb.check_ok !== false } };
  if (loaded.length) {
    const names = [...new Set(loaded.map(p => p.name))];
    s2.state = 'ok'; s2.detail = list(names) + (names.length === 1 ? ' has the plugin.' : ' have the plugin.');
  } else if (!procs.length && !unmatched.length) {
    s2.state = 'pending'; s2.detail = zb.check_ok === false ? 'Studio could not tell whether ZBrush is running.' : 'Start ZBrush. The plugin loads with it and starts the app.';
  } else if (worst && worst.state === 'restart') {
    s2.state = 'warn'; s2.detail = worst.name + ' was started before the plugin was set up. Restart it.';
  } else if (worst && worst.state === 'starting') {
    s2.state = 'warn'; s2.detail = worst.name + ' is starting...';
  } else if (worst && worst.state === 'unknown') {
    s2.state = 'warn'; s2.detail = worst.why || ('Studio cannot tell yet whether ' + worst.name + ' has the plugin.');
  } else if (procs.length) {
    const p = procs.find(x => x.state === 'not_loaded');
    s2.state = 'off'; s2.detail = (p && p.why) || (p ? p.name + ' is running without the plugin.' : 'The plugin did not load.');
  } else {
    s2.state = 'warn'; s2.detail = 'A ZBrush is running as administrator, so Studio cannot see which version it is.';
  }

  /* 3. Try the ring */
  const a = d.activity || null, lp = d.last_pick || null;
  const opened = !!(a && a.ring && a.ring.at > tryFrom);
  const pk = a && a.pick && a.pick.at > tryFrom && a.pick.source === 'ring' ? a.pick : null;
  const sent = !!(pk && pk.sent);
  const did = !!(sent && lp && lp.ok && lp.at >= pk.at - 2 && (lp.seq == null || pk.seq == null || lp.seq === pk.seq));
  let hint = null;
  if (pk && !sent) hint = { text: pk.reason || 'The app could not send that pick to ZBrush.' };
  else if (sent && !did && now - pk.at > 4) {
    hint = { key: { text: 'ZBrush did not react to the bridge key. Bind it to Zplugin > ZOrbit > Apply (Settings > ZBrush bridge).', settings: true },
      listener: { text: 'The plugin did not act on the pick. See bridge.log on the Status screen.' },
      zscript: { text: 'ZBrush did not react to F9. Check Zplugin > ZOrbit > Apply has the hotkey.' } }[pk.route]
      || { text: pk.reason || 'ZBrush did not confirm the pick.' };
  }
  const locked3 = s2.state !== 'ok';
  const key = (ctx.menu && ctx.menu.hotkey) || 'Q';
  const s3 = { id: 'try', title: 'Try the ring', locked: locked3, key,
    checks: [
      { label: 'Ring opened', ok: opened, sub: '' },
      { label: 'Pick sent', ok: sent, sub: sent ? '‘' + (pk.label || pk.item || 'item') + '’ via ' + (PICK_VIA[pk.route] || pk.route) : '' },
      { label: 'ZBrush did it', ok: did, sub: '' }],
    hint: locked3 ? null : hint };
  const all3 = opened && sent && did;
  s3.state = locked3 ? 'pending' : (all3 ? 'ok' : (hint ? 'warn' : 'pending'));
  s3.detail = locked3 ? 'Available once the plugin is loaded in ZBrush.'
    : (all3 ? 'The ring works. Press {key} over the canvas whenever you want a brush.' : 'Hover over ZBrush’s canvas, press {key}, and flick toward a brush.');

  /* 4. Your brushes */
  const m = ctx.menu;
  const s4 = { id: 'brushes', title: 'Your brushes', menu: m,
    state: m ? 'ok' : 'pending',
    detail: m ? (m.hotkey ? m.hotkey + ' opens the “' + m.title + '” ring. Swap in your own brushes if you like.' : 'The “' + m.title + '” ring has no hotkey yet. Swap in your own brushes if you like.') : 'There are no menus yet.' };

  /* 5. What's where */
  const s5 = { id: 'where', title: 'What’s where', state: ctx.done ? 'ok' : 'pending', detail: 'A quick map of Studio.' };
  return [s1, s2, s3, s4, s5];
}

const USER_GUIDE_URL = 'https://github.com/combwizard/zorbit/blob/main/docs/user-guide.md';
const SETUP_WHERE = [
  ['Menus', 'Edit the rings and what each slot does', 'menus'],
  ['Library', 'Every brush ZBrush can load, with tags', 'library'],
  ['Settings', 'Size, animation, colours, the bridge', 'settings'],
  ['Status', 'Is everything running, and the logs', 'status'],
  ['User guide', 'The whole manual, on GitHub', null]];

function buildSetupScreen(root) {
  root.replaceChildren();
  const st = S.setup = S.setup || { data: null, tryFrom: Date.now() / 1000, busy: false, lastAsk: 0 };   // tryFrom outlives a screen switch; Start over resets it
  const first = S.prefs.setup_done === false;       // decided once: the footer must not swap itself when the switch below is used
  const list = h('ol', { class: 'setup-steps', 'aria-label': 'Setup steps' });
  const errBox = h('div', { hidden: true, role: 'alert' });
  const foot = h('div', { class: 'setup-foot' });
  root.append(h('div', { class: 'settings-scroll' }, h('div', { class: 'settings setup' },
    h('div', { class: 'page-head' }, h('h1', null, 'Setup'), h('p', null, 'Everything ZOrbit needs, and what still needs doing.')), errBox, list, foot)));

  const els = new Map();
  let steps = null;                                 // the last steps drawn: tells the timer whether step 3 is being waited on

  // The Start app button lives on step 2. One element, moved into each freshly built step.
  const startBtn = h('button', { class: 'btn small primary start-btn', type: 'button', onclick: () => startApp() });
  const paintStart = () => {
    const d = st.data, running = !!(d && d.app && d.app.running);
    const noZ = !!d && !(d.zbrush && d.zbrush.running) && !(d.zbrush && d.zbrush.check_ok === false);
    startBtn.disabled = appStarting || running || noZ || !d;
    startBtn.replaceChildren(...(appStarting ? [h('span', { class: 'spin' }), 'Starting...'] : [icon('play', 12), running ? 'Running' : 'Start app']));
    startBtn.classList.toggle('running', appStarting);
    startBtn.title = appStarting ? 'Starting the app...' : running ? 'The app is already running' : noZ ? 'ZBrush must be running first' : 'Start the ZOrbit app';
    if (appStarting) startBtn.setAttribute('aria-busy', 'true'); else startBtn.removeAttribute('aria-busy');
  };
  async function startApp() {
    if (!await startAppFlow({ paint: paintStart })) return;
    await ask(true);
  }

  const subCheck = (tone, text, sub, extra) => h('div', { class: 'sub-check ' + tone }, h('i', { class: 'sdot' }),
    h('div', { class: 'grow' }, h('div', null, text), sub ? h('small', null, sub) : null), extra || null);
  const note = (text, warn) => h('div', { class: 'fhint' + (warn ? ' warn' : '') }, text);

  const bodies = {
    found(s) {
      const out = [];
      if (s.modern.length) out.push(h('div', { class: 'zrows' }, ...s.modern.map(r => {
        const fix = r.fix ? h('button', { class: 'btn small primary', type: 'button' }, 'Fix') : null;
        if (fix) fix.onclick = async () => {
          fix.disabled = true; fix.replaceChildren(h('span', { class: 'spin' }), 'Fixing...');
          try { const res = await call('register_plugin_path'); toast(res.message || (res.ok ? 'Done.' : 'That did not work.'), { tone: res.ok ? 'ok' : 'warn', ms: 5000 }); }
          catch (e) { toast('That did not work: ' + (e.message || e), { tone: 'warn' }); }
          ask(true);
        };
        return h('div', { class: 'zrow' }, h('div', { class: 'grow' }, h('div', { class: 'zname' }, r.name, h('span', { class: 'tag ' + r.tone }, r.tag), procTag(r.proc)), h('div', { class: 'zpath mono', title: r.path }, r.path)), fix);
      })));
      const box = h('div', { class: 'zrows' });
      const lz = legacyRows(box, { refresh: () => ask(true), extra: z => procTag(z.proc) });
      if (s.legacy.installs.length) { lz.paint(s.legacy); out.push(box); }
      if (s.bridgeMissing) out.push(note('The plugin folder is missing from this install. Reinstall ZOrbit.', true));
      for (const o of s.others) out.push(note('Also registered: ' + o.path + (o.exists ? '' : ' (missing)')));
      out.push(h('div', { class: 'btn-row' }, h('button', { class: 'btn small' + (s.state === 'off' ? ' primary' : ''), type: 'button', onclick: () => lz.addFolder() }, icon('folder', 12), 'Add a ZBrush folder...')));
      return out;
    },
    loaded(s) {
      const tone = { loaded: 'ok', restart: 'warn', starting: 'warn', unknown: 'warn', not_loaded: 'off' };
      const rows = s.rows.map(p => subCheck(tone[p.state] || 'warn', [p.name, ' ', procTag(p.state)], p.why && p.state !== 'loaded' ? p.why : ''));
      if (s.elevated) rows.push(subCheck('warn', 'A ZBrush is running as administrator', 'Studio cannot see which version it is, or whether it has the plugin.'));
      rows.push(subCheck(s.app.running ? 'ok' : (s.app.zbrush ? 'warn' : 'pending'), ['App ', h('span', { class: 'tag ' + (s.app.running ? 'cyan' : 'dim') }, s.app.running ? 'Running' : 'Not running')],
        s.app.running ? 'Listening for your hotkeys.' : (s.app.zbrush || !s.app.checkOk ? 'Press Start app to launch it.' : 'It starts together with ZBrush.'), startBtn));
      return [h('div', { class: 'sub-checks' }, ...rows)];
    },
    try(s) {
      const out = [h('div', { class: 'sub-checks' }, ...s.checks.map(c => subCheck(c.ok ? 'ok' : 'pending', c.label, c.sub)))];
      if (s.hint) {
        out.push(note(s.hint.text, true));
        if (s.hint.settings) out.push(h('div', { class: 'btn-row' }, h('button', { class: 'btn small', type: 'button', onclick: () => showScreen('settings') }, 'Open Settings')));
      }
      out.push(h('div', { class: 'btn-row' }, h('button', { class: 'btn small', type: 'button', title: 'Forget what happened so far and watch for a new try',
        onclick: () => { st.tryFrom = Date.now() / 1000; paint(true); } }, icon('refresh', 12), 'Start over')));
      return out;
    },
    brushes(s) {
      if (!s.menu) return [];
      const img = h('img', { class: 'ring-img pending', alt: 'Ring preview', draggable: false, onload: () => img.classList.remove('pending') });
      RingLoader.get(s.menu.id, null).then(res => { if (res && res.image && img.isConnected) img.src = res.image; });
      const stage = h('div', { class: 'mini-stage' }, h('div', { class: 'stage-rings', 'aria-hidden': 'true' }), h('div', { class: 'mini-wrap' }, img),
        h('div', { class: 'mini-cap micro' }, 'The ' + s.menu.title + ' ring' + (s.menu.hotkey ? ', on ' + s.menu.hotkey : '')));
      return [h('div', { class: 'setup-ring' }, stage),
        h('div', { class: 'btn-row' }, h('button', { class: 'btn small', type: 'button', onclick: () => { S.menuId = s.menu.id; S.itemIdx = null; S.tab = 'menu'; showScreen('menus'); } }, 'Change these brushes'))];
    },
    where() {
      return [h('div', { class: 'setup-where' }, ...SETUP_WHERE.map(([name, text, screen]) => h('div', { class: 'zrow' },
        h('div', { class: 'grow' }, h('b', null, name), h('small', null, text)),
        screen ? h('button', { class: 'btn small', type: 'button', onclick: () => showScreen(screen) }, 'Open')
          : h('button', { class: 'btn small', type: 'button', onclick: async () => { try { await call('open_url', USER_GUIDE_URL); } catch (e) { toast('Could not open the link.', { tone: 'warn' }); } } }, icon('external', 12), 'Open'))))];
    } };

  const renderStep = (el, s, n) => {
    const parts = String(s.detail || '').split('{key}');
    const detail = h('div', { class: 'sdetail' }, ...parts.flatMap((t, i) => (i ? [hkChips(s.key || 'Q', 'sm'), t] : [t])));
    const body = (bodies[s.id](s) || []).filter(Boolean);
    el.replaceChildren(h('div', { class: 'snum', 'aria-hidden': 'true' }, s.state === 'ok' ? icon('check', 14) : String(n)),
      h('div', { class: 'smain' }, h('b', { class: 'stitle' }, s.title), detail, body.length ? h('div', { class: 'sbody' }, ...body) : null));
  };

  // Draws what changed. force: redraw every step (after an action of ours), else a step that is mid-action keeps its buttons.
  function paint(force) {
    const d = st.data;
    if (!d) return;
    steps = deriveSteps(d, st.tryFrom, { menu: setupMenu(), done: S.prefs.setup_done !== false });
    steps.forEach((s, i) => {
      let el = els.get(s.id);
      if (!el) { el = h('li', { class: 'sstep', dataset: { step: s.id } }); els.set(s.id, el); list.append(el); }
      el.className = 'sstep ' + s.state + (s.locked ? ' locked' : '');
      const sig = JSON.stringify(s);
      if (!force && (el._sig === sig || el.querySelector('.btn.running'))) return;
      el._sig = sig;
      renderStep(el, s, i + 1);
    });
    paintStart();
  }
  const paintErr = () => {
    errBox.hidden = !st.err;
    errBox.replaceChildren(...(st.err ? [h('div', { class: 'scard off' }, h('div', { class: 'micro' }, 'Setup'), h('div', { class: 'sval' }, h('i', { class: 'sdot' }), 'Setup check unavailable'), h('div', { class: 'ssub' }, st.err))] : []));
  };
  // One get_setup. A caller that forces one waits for a poll already in flight, so what it changed is in the answer.
  async function ask(force) {
    while (st.busy) { if (!force) return; await sleep(60); }
    st.busy = true; st.lastAsk = Date.now();
    try {
      const d = await call('get_setup');
      st.data = d; st.err = '';
      noteSetupStatus(d); setSetupBadge(d);
      if (S.screen === 'setup') paint(force);
    } catch (e) { st.err = String(e.message || e); }
    finally { st.busy = false; }
    paintErr();
  }
  R.setup = () => ask(true);

  // The footer is built once: Finish / Skip on a first run, else a Done tag and a switch to bring Setup back.
  const menuNow = setupMenu();
  const finish = async withToast => {
    if (!await setPref('setup_done', true)) return;
    if (withToast) toast('Setup done. Press ' + ((menuNow && menuNow.hotkey) || 'Q') + ' over ZBrush whenever you like.', { tone: 'ok', ms: 4500 });
    showScreen('menus');
  };
  if (first) foot.append(h('button', { class: 'btn primary', type: 'button', onclick: () => finish(true) }, 'Finish'),
    h('button', { class: 'btn', type: 'button', onclick: () => finish(false) }, 'Skip for now'));
  else foot.append(h('span', { class: 'tag cyan' }, 'Done'),
    h('span', { class: 'foot-note' }, 'Show Setup on next start', toggleSwitch(!S.prefs.setup_done, v => setPref('setup_done', !v), 'Show Setup on next start')));

  if (st.data) paint(true);
  ask(true);
  clearInterval(statusTimer);
  // one beat per second; a look goes out once the last answer is old enough (sooner while step 3 is being waited on)
  statusTimer = setInterval(() => {
    if (S.screen !== 'setup' || document.hidden || st.busy) return;
    const s3 = steps && steps.find(s => s.id === 'try');
    const fast = !!s3 && !s3.locked && s3.state !== 'ok';
    if (Date.now() - st.lastAsk >= (fast ? 1400 : 1900)) ask(false);
  }, 1000);
}

/* ================================================================== shell: dirty state, problems, save, screens */
const dirtyNow = () => !!S.cfg && JSON.stringify(S.cfg) !== S.savedStr;
function updateDirty() {
  const d = dirtyNow();
  if (d !== S.dirtySent && !(S.dirtyFlight && S.dirtyFlight.d === d)) {
    // dirtySent only moves once the backend has acknowledged; a failed call leaves it alone so the next change retries
    const seq = ++S.dirtySeq;
    S.dirtyFlight = { d, seq };
    call('set_dirty', d)
      .then(() => { if (seq === S.dirtySeq) S.dirtySent = d; }, () => {})
      .then(() => { if (S.dirtyFlight && S.dirtyFlight.seq === seq) S.dirtyFlight = null; });
  }
  $('#dirty').hidden = !d;
  $('#revertBtn').disabled = !d;
  $('#saveBtn').classList.toggle('pending', d);
}
/* Turns one message from the loader (config.py) into plain words plus where to go to fix it.
   Returns { text, raw, target }; target is null when the format is not recognised. */
const RING_CARD = { radius: 'set-ring-geometry', slot: 'set-ring-geometry', dead_zone: 'set-ring-geometry', animation: 'set-open-animation',
  labels: 'set-labels', tag_colors: 'set-tag-colours', tag_band: 'set-tag-colours', tag_band_opacity: 'set-tag-colours', tag_glow_opacity: 'set-tag-colours',
  tag_tint_opacity: 'set-tag-colours', tag_tint_style: 'set-tag-colours', tag_tint_blend: 'set-tag-colours', colors: 'set-colours', tap_ms: 'set-behaviour', timeout_s: 'set-behaviour', flick: 'set-behaviour', hover_submenus: 'set-behaviour' };
const RING_NAME = { radius: 'Ring radius', slot: 'Slot size', dead_zone: 'Dead zone', tap_ms: 'Tap time', timeout_s: 'Auto-close', flick: 'Flick to pick',
  hover_submenus: 'Open submenus on hover', animation: 'Open animation', labels: 'Labels', tag_colors: 'Tag colours',
  tag_band: 'Band', tag_band_opacity: 'Band opacity', tag_glow_opacity: 'Glow opacity', tag_tint_opacity: 'Icon tint opacity', tag_tint_style: 'Icon tint style', tag_tint_blend: 'Icon tint blend' };
const unq = s => String(s).replace(/^(['"])(.*)\1$/, '$2');
function describeProblem(raw) {
  const out = (text, target) => ({ text, raw, target: target || null });
  const cfgMenus = (S.cfg && S.cfg.menus) || {};
  const titleOf = id => '\u201c' + ((cfgMenus[id] && cfgMenus[id].title) || id) + '\u201d';
  const known = id => !!cfgMenus[id] && typeof cfgMenus[id] === 'object';
  let m;
  // "menu <id> item <n><rest>": the id is matched against the real menus first, so an id with spaces still resolves
  const ids = Object.keys(cfgMenus).sort((x, y) => y.length - x.length);
  const own = ids.find(id => raw.startsWith('menu ' + id + ' item ') || raw.startsWith('menu ' + id + ': '));
  const mid = own !== undefined ? own : ((m = /^menu (\S+)(?: item |: )/.exec(raw)) ? m[1] : null);
  if (mid !== null) {
    const rest = raw.slice(('menu ' + mid).length);
    if ((m = /^ item (\d+)(.*)$/s.exec(rest))) {
      const n = +m[1];
      return out(titleOf(mid) + ' item ' + n + m[2], known(mid) ? { kind: 'item', menuId: mid, index: n - 1 } : null);
    }
    const tgt = field => (known(mid) ? { kind: 'menu', menuId: mid, field } : null);
    if (rest === ': no usable items') return out(titleOf(mid) + ' has no usable items', tgt());
    if (rest === ': not an object') return out(titleOf(mid) + ' is not a valid menu', tgt());
    if ((m = /^: hotkey (.+) already used by menu (.+)$/s.exec(rest))) {
      const other = m[2];
      return out(`${titleOf(mid)} and ${titleOf(other)} both use the hotkey ${unq(m[1])}; only ${titleOf(other)} (the first) will open it`, tgt('hotkey'));
    }
    if (rest.startsWith(': ids starting with')) return out(`The id of ${titleOf(mid)} cannot start with “tag:”; those ids are reserved for tag submenus`, tgt('id'));
    if ((m = /^: hotkey (.+) not understood$/s.exec(rest))) return out(`The hotkey ${unq(m[1])} on ${titleOf(mid)} is not understood`, tgt('hotkey'));
    if ((m = /^: animation (.+) unknown; using ring\.animation$/s.exec(rest))) return out(`${titleOf(mid)} has an unknown animation (${unq(m[1])}); the one from Settings is used instead`, tgt('animation'));
    return out(titleOf(mid) + rest, tgt());
  }
  if ((m = /^ring\.colors\.(\w+): (.+) is not a #rrggbb colour$/s.exec(raw))) {
    const nm = COLOR_INFO[m[1]] ? COLOR_INFO[m[1]][0] : m[1];
    return out(`${nm} colour ${unq(m[2])} is not a #rrggbb value`, { kind: 'settings', card: 'set-colours' });
  }
  if ((m = /^ring\.(\w+): (.*)$/s.exec(raw))) {
    const key = m[1], body = m[2], nm = RING_NAME[key] || key, card = RING_CARD[key];
    const target = card ? { kind: 'settings', card } : null;
    let r;
    if ((r = /^(.+) must be a number from (\S+) to (\S+)$/s.exec(body))) return out(`${nm} ${unq(r[1])} is outside ${r[2]} to ${r[3]}`, target);
    if ((r = /^(.+) must be true or false$/s.exec(body))) return out(`${nm} must be on or off, not ${unq(r[1])}`, target);
    if ((r = /^(.+) unknown; one of /s.exec(body))) return out(`${nm} ${unq(r[1])} is not one of the available choices`, target);
    return out(`${nm}: ${body}`, target);
  }
  const bridge = { kind: 'settings', card: 'set-zbrush-bridge' };
  if ((m = /^bridge\.mode (.+) unknown; using auto$/s.exec(raw))) return out(`Bridge mode ${unq(m[1])} is unknown; Auto is used instead`, bridge);
  if ((m = /^bridge\.key (.+) not understood$/s.exec(raw))) return out(`The bridge key ${unq(m[1])} is not understood`, bridge);
  if (raw.startsWith('bridge.key ')) return out('The bridge key ' + raw.slice('bridge.key '.length), bridge);
  const browserCard = { kind: 'settings', card: 'set-browser' };
  if ((m = /^browser\.hotkey (.+) not understood$/s.exec(raw))) return out(`The browser hotkey ${unq(m[1])} is not understood`, browserCard);
  if ((m = /^browser\.hotkey (.+) already used by menu (.+)$/s.exec(raw))) return out(`The browser hotkey ${unq(m[1])} is also used by ${titleOf(m[2])}; that menu wins, so the browser will not open with it`, browserCard);
  if (raw.startsWith('browser: ')) return out('The browser settings are not valid: ' + raw.slice('browser: '.length), browserCard);
  if (raw.startsWith('menus: must be a non-empty object')) return out('There are no menus yet; add one', { kind: 'screen', screen: 'menus' });
  if (raw.startsWith('no menu has a hotkey')) {
    const first = Object.keys(cfgMenus).find(known);
    return out('No menu has a hotkey, so nothing can open the ring', first ? { kind: 'menu', menuId: first, field: 'hotkey', global: true } : { kind: 'screen', screen: 'menus' });
  }
  return out(raw, null);
}

/* Amber markers on menu and item rows. Built with the row, and patched in place when the problems change. */
function menuWarn(id) {
  const tips = S.problemTips.get(id);
  return tips ? h('span', { class: 'mwarn', title: tips.join('\n') }, icon('alert', 13)) : null;
}
function itemWarn(menuId, i, ok) {
  const tips = S.problemTips.get(menuId + '#' + i);
  if (ok && !tips) return null;
  return h('span', { class: 'iwarn', title: tips ? tips.join('\n') : 'This item is incomplete and will be skipped' }, icon('alert', 14));
}
function paintMarkers() {
  $$('.mrow').forEach(row => {
    const want = S.problemTips.get(row.dataset.id), cur = $('.mwarn', row);
    if (!want) { if (cur) cur.remove(); return; }
    if (cur) { cur.title = want.join('\n'); return; }
    const side = $('.mrow-side', row); if (side) side.prepend(menuWarn(row.dataset.id));
  });
  $$('.irow').forEach(row => {
    const menuId = row.dataset.menu, i = +row.dataset.i, want = S.problemTips.get(menuId + '#' + i), cur = $('.iwarn', row);
    const m = S.cfg.menus[menuId], bad = !m || !m.items[i] || !itemUsable(m.items[i]);
    if (!want && !bad) { if (cur) cur.remove(); return; }
    const title = want ? want.join('\n') : 'This item is incomplete and will be skipped';
    if (cur) { cur.title = title; return; }
    const acts = $('.iacts', row), el = itemWarn(menuId, i, !bad);
    if (el) row.insertBefore(el, acts);
  });
}

function goToProblem(t) {
  S.problemsOpen = false; renderProblems();
  if (!t) return;
  if (t.kind === 'settings') {
    const same = S.screen === 'settings';
    showScreen('settings', { fresh: true });
    const go = () => { if (R.gotoCard) R.gotoCard(t.card); };
    if (same) go(); else requestAnimationFrame(go);
    return;
  }
  showScreen('menus', { fresh: true });
  if (t.kind === 'item') {
    const m = S.cfg.menus[t.menuId]; if (!m) return;
    selectMenu(t.menuId);
    if (t.index >= 0 && t.index < (m.items || []).length) selectItem(t.index);
    return;
  }
  if (t.kind === 'menu') {
    if (!S.cfg.menus[t.menuId]) return;
    selectMenu(t.menuId); S.tab = 'menu'; if (R.right) R.right();
    const mr = $('.mrow.sel'); if (mr) mr.scrollIntoView({ block: 'nearest' });
    const el = t.field === 'hotkey' ? $('.insp .hk-field') : t.field === 'id' ? $('.insp input[aria-label="Menu id"]') : t.field === 'animation' ? $('.insp select[aria-label="Open animation for this menu"]') : null;
    if (el) { el.focus(); el.scrollIntoView({ block: 'nearest' }); }
  }
}

function renderProblems() {
  const p = S.problems || [], pill = $('#problemsBtn'), panel = $('#problemsPanel');
  pill.hidden = !p.length;
  if (!p.length) S.problemsOpen = false;
  const open = S.problemsOpen && p.length > 0;
  panel.hidden = !open;
  pill.setAttribute('aria-expanded', open ? 'true' : 'false');
  if (!p.length) { S.problemMenus = new Set(); S.problemItems = new Map(); S.problemTips = new Map(); S._probSig = ''; S._markSig = ''; paintMarkers(); return; }
  setText($('#problemsCount'), p.length + (p.length === 1 ? ' problem' : ' problems'));
  const entries = p.map(describeProblem);
  // row markers: which menus / items carry a problem, with the plain-words text as their tooltip
  const menusWith = new Set(), itemsWith = new Map(), tips = new Map();
  const tip = (k, t) => { if (!tips.has(k)) tips.set(k, []); tips.get(k).push(t); };
  for (const e of entries) {
    const t = e.target;
    if (!t || !t.menuId || t.global) continue;
    menusWith.add(t.menuId); tip(t.menuId, e.text);
    if (t.kind === 'item') {
      if (!itemsWith.has(t.menuId)) itemsWith.set(t.menuId, new Set());
      itemsWith.get(t.menuId).add(t.index); tip(t.menuId + '#' + t.index, e.text);
    }
  }
  S.problemMenus = menusWith; S.problemItems = itemsWith; S.problemTips = tips;
  const markSig = JSON.stringify([...tips]);
  if (markSig !== S._markSig) { S._markSig = markSig; paintMarkers(); }
  // the list is rebuilt only when its content changed, so a click is never swallowed by a re-render
  const sig = entries.map(e => e.text + '\u0001' + e.raw + '\u0001' + JSON.stringify(e.target)).join('\u0002');
  if (sig !== S._probSig) {
    S._probSig = sig;
    $('#problemsList').replaceChildren(...entries.map(e => {
      const go = !!e.target;
      return h(go ? 'button' : 'div', { class: 'problem' + (go ? ' go' : ''), type: go ? 'button' : null, title: e.raw, onclick: go ? () => goToProblem(e.target) : null },
        icon('alert', 13), h('span', { class: 'ptext' }, e.text), go ? icon('chevR', 12) : null);
    }));
  }
  if (open) placeProblemsPanel();
}
function placeProblemsPanel() {
  const pill = $('#problemsBtn'), panel = $('#problemsPanel'), app = $('#app');
  if (!pill || pill.hidden) return;
  const r = pill.getBoundingClientRect(), a = app.getBoundingClientRect(), w = Math.min(560, a.width - 16);
  panel.style.width = w + 'px';
  panel.style.left = clamp(r.left - a.left, 8, Math.max(8, a.width - w - 8)) + 'px';
}
function closeProblems(refocus) {
  if (!S.problemsOpen) return;
  S.problemsOpen = false; renderProblems();
  if (refocus) $('#problemsBtn').focus();
}
/* Takes a freshly loaded get_config result (boot, or "reload from disk") and makes it the current and saved config. */
function adoptConfig(res) {
  S.cfg = res.config;
  if (!S.cfg.menus || typeof S.cfg.menus !== 'object' || Array.isArray(S.cfg.menus)) S.cfg.menus = {};   // an array would lose menus on save
  S.path = res.path || S.path || ''; S.problems = res.problems || [];
  S.mtimeNs = res.mtime_ns !== undefined ? res.mtime_ns : null;
  S.savedStr = JSON.stringify(S.cfg); resetHistory(S.savedStr);
}
async function reloadFromDisk() {
  let res;
  try { res = await call('get_config'); } catch (e) { toast('Could not reload: ' + (e.message || e), { tone: 'err' }); return false; }
  if (!res || !res.config) { toast('Could not reload: ' + ((res && res.error) || 'the file cannot be read'), { tone: 'err' }); return false; }
  validateSoon.cancel(); snapSoon.cancel();
  adoptConfig(res);
  if (!S.cfg.menus[S.menuId]) S.menuId = Object.keys(S.cfg.menus)[0] || null;
  const m = curMenu();
  if (!m || S.itemIdx === null || S.itemIdx >= (m.items || []).length) S.itemIdx = null;
  rememberSel();
  S.version++; updateDirty(); renderProblems(); previewSoon();
  renderAllMenus(); if (R.settings) R.settings(); if (R.libTarget) R.libTarget();
  toast('Reloaded the file from disk.', { tone: 'ok', ms: 2600 });
  return true;
}
/* ---- import and export: one file with the menus, the ring settings and the tags (the backend does the file work) */
let ioBusy = false;
async function ioRun(btns, fn) {
  if (ioBusy) return;
  ioBusy = true; btns.forEach(b => { b.disabled = true; });
  try { await fn(); } finally { ioBusy = false; btns.forEach(b => { b.disabled = false; }); }
}
async function exportSettings() {
  if (!S.cfg || S.fatal || !S.ready) return;
  let res;
  try { res = await call('export_settings', S.cfg); } catch (e) { toast('Could not export: ' + (e.message || e), { tone: 'err' }); return; }
  if (!res || res.cancelled) return;
  toast(res.message || (res.ok ? 'Exported the settings' + (res.path ? ' to ' + res.path : '.') : 'The export did not work.'), { tone: res.ok ? 'ok' : 'warn', ms: 5000 });
}
async function importSettings() {
  if (!S.cfg || S.fatal || !S.ready) return;
  let info;
  try { info = await call('pick_import'); } catch (e) { toast('Could not read the file: ' + (e.message || e), { tone: 'err' }); return; }
  if (!info || info.cancelled) return;
  if (!info.ok) { toast(info.message || 'That file could not be imported.', { tone: 'warn', ms: 5000 }); return; }
  const hasCfg = !!info.has_config, hasTags = !!info.has_tags;
  const name = String(info.path || '').split(/[\\/]/).pop() || 'this file';
  const n = (v, one, many) => { v = +v || 0; return v + ' ' + (v === 1 ? one : many); };
  const counts = [];
  if (hasCfg) counts.push(n(info.menus, 'menu', 'menus'));
  if (hasTags) counts.push(n(info.tags, 'tag', 'tags') + (info.new_tags ? `, ${info.new_tags} not among yours yet` : ''));
  const probs = (info.problems || []).map(String), shown = probs.slice(0, 5);
  const merge = { text: 'Merge tags', value: 'merge', kind: 'primary', focus: true }, replace = { text: 'Replace tags', value: 'replace', kind: 'danger-ghost' };
  const mode = await modal({ title: `Import settings from ${name}?`,
    body: h('div', { class: 'changes' },
      h('p', { class: 'modal-path mono' }, info.path || name),
      h('p', null, counts.length ? 'The file holds ' + counts.join(' and ') + '.' : 'The file holds nothing to import.'),
      hasCfg ? h('p', null, 'The menus and settings load into the editor. Save keeps them and Undo takes them back.') : h('p', null, 'The editor is not touched.'),
      hasTags ? h('p', null, 'Tags are saved straight away and are not part of Undo. Merge adds the file’s tags to yours; Replace swaps yours for the file’s and keeps a copy of the old tags file.') : null,
      probs.length ? h('div', { class: 'changes-list' }, h('div', { class: 'chg-group' }, h('div', { class: 'micro' }, n(probs.length, 'problem', 'problems') + ' in the menus'),
        h('ul', null, shown.map(p => h('li', null, p)), probs.length > shown.length ? h('li', null, `and ${probs.length - shown.length} more`) : null))) : null),
    actions: hasTags ? [{ text: 'Cancel', value: null }, merge, replace] : [{ text: 'Cancel', value: null, focus: !hasCfg }, { text: 'Import', value: 'none', kind: 'primary', focus: hasCfg }] });
  if (!mode) return;
  let res;
  try { res = await call('apply_import', mode); } catch (e) { res = { ok: false, message: 'Import failed: ' + (e.message || e) }; }
  if (mode !== 'none') await loadTags(true);                     // the tags may have changed even when the call reports a problem
  if (!res || !res.ok) { toast((res && (res.message || res.error)) || 'The import did not work.', { tone: 'warn', ms: 5000 }); return; }
  if (res.config) {
    snapSoon.cancel(); validateSoon.cancel(); pushSnap();       // files an edit still waiting, so Undo goes back to it; mtimeNs and savedStr stay as they were
    S.cfg = res.config;
    if (!S.cfg.menus || typeof S.cfg.menus !== 'object' || Array.isArray(S.cfg.menus)) S.cfg.menus = {};
    S.problems = res.problems || [];
    if (S.problems.length) S.problemsOpen = true;
    if (!S.cfg.menus[S.menuId]) S.menuId = Object.keys(S.cfg.menus)[0] || null;
    const m = curMenu();
    if (!m || S.itemIdx === null || S.itemIdx >= (m.items || []).length) S.itemIdx = null;
    if (S.itemIdx === null && S.tab === 'item') S.tab = 'menu';
    commit({ inspector: true }); if (R.head) R.head();
    renderProblems(); if (R.settings) R.settings(); if (R.libTarget) R.libTarget();
  }
  const bits = [];
  if (res.config) bits.push('Loaded the menus and settings into the editor. Save to keep them.');
  if (res.tags_message) bits.push(res.tags_message);
  if (res.config && (res.problems || []).length) bits.push(n(res.problems.length, 'problem', 'problems') + ' to look at.');
  const msg = bits.join(' ') || 'Imported.', tone = res.config && (res.problems || []).length ? 'warn' : 'ok';
  if (res.config) undoToast(msg, { tone, ms: 7000 }); else toast(msg, { tone, ms: 5000 });
}
function save() {
  if (!S.cfg || S.fatal || !S.ready) return Promise.resolve('skipped');
  if (S.saving) return S.savePromise;
  if (!dirtyNow()) { toast('Nothing to save', { ms: 1400 }); return Promise.resolve('clean'); }
  S.saving = true;
  const btn = $('#saveBtn'); btn.disabled = true; btn.setAttribute('aria-busy', 'true');
  S.savePromise = doSave().then(out => out, () => 'failed').then(out => {
    S.saving = false; S.savePromise = null;
    btn.disabled = false; btn.removeAttribute('aria-busy');
    updateDirty(); renderProblems();
    return out;
  });
  return S.savePromise;
}
/* One save attempt. Resolves to 'saved', 'reloaded' (the user chose the file on disk over their edit), 'cancelled' or
   'failed'. force skips the changed-on-disk check; allowUnusable skips the "no ring can open" check. They stay
   separate so confirming one warning never skips the other. */
async function doSave({ force = false, allowUnusable = false } = {}) {
  const snap = JSON.stringify(S.cfg);
  try {
    const r = await call('save_config', S.cfg, S.mtimeNs, !!force, !!allowUnusable);
    if (r && r.saved) {
      S.savedStr = snap; S.problems = r.problems || [];
      if (r.mtime_ns !== undefined) S.mtimeNs = r.mtime_ns;
      const t = r.time ? new Date(r.time * 1000).toLocaleTimeString() : '';
      const tail = S.appDown === false ? '. The app picks it up straight away.' : (S.appDown === true ? '. The app is not running: start it from Status.' : '');
      toast(S.problems.length ? `Saved at ${t} with ${S.problems.length} problem${S.problems.length === 1 ? '' : 's'}` : `Saved at ${t}${tail}`, { tone: S.problems.length ? 'warn' : 'ok', ms: tail && S.appDown === true ? 4800 : 3800 });
      if (R.status) R.status(); else refreshAppDown();      // one quiet look, so the rail dot is right
      if (S.problems.length) { S.problemsOpen = true; }
      return 'saved';
    }
    if (r && r.conflict) {
      const v = await modal({ title: 'The file changed on disk',
        body: h('p', null, r.message || 'The menus file was changed by something else after Studio loaded it. Saving now would overwrite those changes.'),
        actions: [{ text: 'Cancel', value: 'cancel' }, { text: 'Overwrite', value: 'overwrite', kind: 'danger-ghost' }, { text: 'Reload from disk', value: 'reload', kind: 'primary', focus: true }] });
      if (v === 'reload') return (await reloadFromDisk()) ? 'reloaded' : 'failed';
      if (v === 'overwrite') {
        // adopt the file's current stamp so this is a plain save of what the user saw; the no-usable-ring check still applies
        if (r.mtime_ns !== undefined && r.mtime_ns !== null) S.mtimeNs = r.mtime_ns;
        return doSave({ force: true, allowUnusable });   // force only skips the changed-on-disk check, so Overwrite cannot loop
      }
      return 'cancelled';
    }
    if (r && r.blocked) {
      const probs = r.problems || [];
      const v = await modal({ title: 'Save anyway?',
        body: h('div', { class: 'changes' }, h('p', null, r.message || 'Saving this would leave no ring that can open.'),
          probs.length ? h('div', { class: 'changes-list' }, h('div', { class: 'chg-group' }, h('ul', null, probs.map(p => h('li', null, p))))) : null),
        actions: [{ text: 'Keep editing', value: 'keep', kind: 'primary', focus: true }, { text: 'Save anyway', value: 'force', kind: 'danger-ghost' }] });
      return v === 'force' ? doSave({ allowUnusable: true }) : 'cancelled';   // never carries force: a new disk change still warns
    }
    toast((r && r.message) || 'The config could not be saved.', { tone: 'err' });
    return 'failed';
  } catch (e) { toast('Save failed: ' + (e.message || e), { tone: 'err' }); return 'failed'; }
}
async function revert() {
  if (!dirtyNow()) return;
  const ok = await modal({ title: 'Revert changes', body: h('p', null, 'Discard all unsaved changes and go back to the last saved config?'), actions: [{ text: 'Keep editing', value: false, focus: true }, { text: 'Revert', kind: 'danger', value: true }] });
  if (!ok) return;
  S.cfg = JSON.parse(S.savedStr);
  if (!S.cfg.menus[S.menuId]) S.menuId = Object.keys(S.cfg.menus)[0] || null;
  S.itemIdx = null; S.version++; updateDirty(); validateSoon(); previewSoon(); pushSnap();
  renderAllMenus(); if (R.settings) R.settings(); if (R.libTarget) R.libTarget();
  toast('Reverted to the saved config.', { ms: 2200 });
}

// Licence: a perfectly serious licence-activation panel. Then the punchline.
function buildLicenceScreen(root) {
  root.replaceChildren();
  const page = h('div', { class: 'settings licence' });
  const key = 'FCKGW-RHQQ2-YXRKT-8TG6W-2B7Q8';
  const quips = ['Already activated. Forever. You can stop typing.', 'Still activated. It was activated before you got here.',
    'Activation status: extremely activated.', 'The key is not checked. Nothing is checked. Go sculpt.'];
  let q = 0;
  const input = h('input', { class: 'inp mono', type: 'text', placeholder: 'XXXX-XXXX-XXXX-XXXX-XXXX', spellcheck: 'false', 'aria-label': 'Licence key' });
  const activate = h('button', { class: 'btn primary', type: 'button', onclick: () => { toast(quips[q++ % quips.length], { tone: 'ok', ms: 3500 }); input.value = ''; } }, icon('check', 13), 'Activate');
  input.addEventListener('keydown', e => { if (e.key === 'Enter') activate.click(); });
  const deactivate = h('button', { class: 'btn danger-ghost', type: 'button', onclick: () => toast('Nice try. You cannot un-free free software.', { tone: 'warn', ms: 3500 }) }, 'Deactivate this machine');
  const copyKey = h('button', { class: 'btn', type: 'button', onclick: async () => {
    try { await navigator.clipboard.writeText(key); toast('Copied. Share it with everyone. That is allowed.', { tone: 'ok', ms: 3000 }); }
    catch (e) { toast('Copy failed, but you are still licensed.', { ms: 3000 }); } } }, icon('copy', 13), 'Copy key');
  const link = (label, url) => h('button', { class: 'btn', type: 'button', onclick: async () => {
    try { await call('open_url', url); } catch (e) { toast('Could not open the link.', { tone: 'warn' }); } } }, icon('external', 13), label);
  const fine = (k, v) => h('div', { class: 'lic-row' }, h('span', { class: 'micro' }, k), h('span', { class: 'lic-val' }, v));

  page.append(
    h('div', { class: 'page-head' }, h('h1', null, 'Licence'), h('p', null, 'Manage your ZOrbit licence and activations.')),
    card('Licence status', null,
      h('div', { class: 'lic-status' },
        h('span', { class: 'lic-badge' }, h('i', { class: 'sdot' }), 'Activated'),
        h('span', { class: 'lic-tier' }, 'Lifetime licence')),
      h('div', { class: 'lic-grid' },
        fine('Licence key', h('span', { class: 'mono lic-key' }, key)),
        fine('Issued to', 'You'), fine('Seats', 'All of them'),
        fine('Expires', 'Never'), fine('Price paid', h('span', { class: 'mono' }, '0.00')), fine('Activations left', '\u221e')),
      h('div', { class: 'btn-row' }, copyKey, deactivate)),
    card('Activate a licence key', 'Got a key from somewhere?',
      h('div', { class: 'lic-activate' }, input, activate)),
    h('section', { class: 'card lic-reveal' },
      h('div', { class: 'lic-reveal-head' }, h('span', { class: 'lic-wink', 'aria-hidden': 'true' }, ';)'), h('h2', null, 'Just kidding.')),
      h('p', null, 'There is no licence key, no account, no trial and no expiry date. Nothing above checks anything.'),
      h('p', null, 'ZOrbit is free software under the GNU General Public License, version 3. Use it on as many machines as you like, share it with anyone, read the code and change it. If you share a changed version, it stays free too.'),
      h('p', { class: 'lic-big' }, 'You are licensed. Forever.'),
      h('div', { class: 'btn-row' },
        link('Read the GPL v3', 'https://www.gnu.org/licenses/gpl-3.0.html'),
        link('Source code on GitHub', 'https://github.com/combwizard/zorbit'))),
    h('div', { class: 'lic-hide' }, h('button', { class: 'linkish', type: 'button', onclick: () => {
      setPref('show_licence', false);
      toast('Fine. It is gone. Settings > Studio brings it back, if you ever miss it.', { ms: 4500 });
      showScreen('settings');
    } }, 'Hide this nonsense, it isn\u2019t funny\u2026')));
  root.append(h('div', { class: 'settings-scroll' }, page));
}

/* ================================================================== close guard */
// Lists what differs between the saved config and the current one, grouped by area.
function describeChanges() {
  let before = {};
  try { before = JSON.parse(S.savedStr || '{}') || {}; } catch (e) { before = {}; }
  const after = S.cfg || {};
  const groups = [];
  const q = s => '\u201c' + s + '\u201d';
  const itemName = it => it.label || it.brush || it.alpha || it.material || it.texture || it.press || it.toggle || it.set || (it.menu ? 'Submenu ' + it.menu : it.steps ? 'Steps' : it.tag ? 'Tag ' + it.tag : 'browser' in it ? 'Browser' + (it.browser ? ' ' + it.browser : '') : 'item');
  const bm = before.menus || {}, am = after.menus || {};
  for (const id of Object.keys(am)) {
    const a = am[id] || {}, b = bm[id];
    const title = a.title || id;
    if (!b) { groups.push({ area: 'Menu ' + q(title), lines: ['New menu with ' + (a.items || []).length + ' item' + ((a.items || []).length === 1 ? '' : 's')] }); continue; }
    const lines = [];
    if ((a.title || '') !== (b.title || '')) lines.push('Renamed from ' + q(b.title || id));
    if ((a.hotkey || '') !== (b.hotkey || '')) lines.push('Hotkey: ' + (b.hotkey || 'none') + ' \u2192 ' + (a.hotkey || 'none'));
    if ((a.animation || '') !== (b.animation || '')) lines.push('Open animation: ' + (b.animation || 'same as Settings') + ' \u2192 ' + (a.animation || 'same as Settings'));
    if ((a.fan === true) !== (b.fan === true)) lines.push('Fan out as a submenu: ' + (b.fan === true ? 'on' : 'off') + ' \u2192 ' + (a.fan === true ? 'on' : 'off'));
    if ((a.swallow !== false) !== (b.swallow !== false)) lines.push('Swallow hotkey: ' + (b.swallow !== false ? 'on' : 'off') + ' \u2192 ' + (a.swallow !== false ? 'on' : 'off'));
    const bi = b.items || [], ai = a.items || [];
    const key = it => JSON.stringify(it);
    const pool = new Map();                       // multiset of unchanged items
    for (const it of bi) pool.set(key(it), (pool.get(key(it)) || 0) + 1);
    const added = [], kept = [];
    for (const it of ai) { const k = key(it); if (pool.get(k)) { pool.set(k, pool.get(k) - 1); kept.push(k); } else added.push(it); }
    const removed = bi.filter(it => { const k = key(it); if (pool.get(k)) { pool.set(k, pool.get(k) - 1); return true; } return false; });
    const changed = [];
    for (const r of removed.slice()) {           // same name on both sides = an edited item
      const i = added.findIndex(x => itemName(x) === itemName(r));
      if (i >= 0) { changed.push(added[i]); added.splice(i, 1); removed.splice(removed.indexOf(r), 1); }
    }
    for (const it of added) lines.push('Added ' + q(itemName(it)));
    for (const it of removed) lines.push('Removed ' + q(itemName(it)));
    for (const it of changed) lines.push('Changed ' + q(itemName(it)));
    // reordered: compare the items present on both sides, one-for-one, in their old and new order
    const left = new Map();
    for (const k of kept) left.set(k, (left.get(k) || 0) + 1);
    const keptBefore = bi.map(key).filter(k => (left.get(k) || 0) > 0 && left.set(k, left.get(k) - 1));
    if (JSON.stringify(keptBefore) !== JSON.stringify(kept)) lines.push('Items reordered');
    if (lines.length) groups.push({ area: 'Menu ' + q(title), lines });
  }
  for (const id of Object.keys(bm)) if (!am[id]) groups.push({ area: 'Menu ' + q(bm[id].title || id), lines: ['Deleted'] });
  const ringLines = [];
  const br = before.ring || {}, ar = after.ring || {};
  const NAMES = { radius: 'Ring radius', slot: 'Slot size', dead_zone: 'Dead zone', tap_ms: 'Tap time', timeout_s: 'Auto-close', animation: 'Open animation', labels: 'Labels', tag_colors: 'Tag colours',
    tag_band: 'Tag band', tag_band_opacity: 'Tag band opacity', tag_glow_opacity: 'Tag glow opacity', tag_tint_opacity: 'Tag tint opacity', tag_tint_style: 'Tag tint style', tag_tint_blend: 'Tag tint blend',
    flick: 'Flick to pick', hover_submenus: 'Open submenus on hover' };
  for (const k of new Set([...Object.keys(br), ...Object.keys(ar)])) {
    if (k === 'colors') continue;
    if (JSON.stringify(br[k]) !== JSON.stringify(ar[k])) ringLines.push((NAMES[k] || k) + ': ' + (br[k] ?? 'default') + ' \u2192 ' + (ar[k] ?? 'default'));
  }
  const bc = br.colors || {}, ac = ar.colors || {};
  for (const k of new Set([...Object.keys(bc), ...Object.keys(ac)])) {
    if (bc[k] !== ac[k]) ringLines.push('Colour ' + k + ': ' + (bc[k] || 'default') + ' \u2192 ' + (ac[k] || 'default'));
  }
  if (ringLines.length) groups.push({ area: 'Settings', lines: ringLines });
  const bb = before.bridge || {}, ab = after.bridge || {};
  const bridgeLines = [];
  if ((bb.mode || 'auto') !== (ab.mode || 'auto')) bridgeLines.push('Mode: ' + (bb.mode || 'auto') + ' \u2192 ' + (ab.mode || 'auto'));
  if ((bb.key || '') !== (ab.key || '')) bridgeLines.push('Bridge key: ' + (bb.key || 'none') + ' \u2192 ' + (ab.key || 'none'));
  if (bridgeLines.length) groups.push({ area: 'ZBrush bridge', lines: bridgeLines });
  const bwb = before.browser || {}, bwa = after.browser || {};
  if ((bwb.hotkey || '') !== (bwa.hotkey || '')) groups.push({ area: 'Browser', lines: ['Hotkey: ' + (bwb.hotkey || 'none') + ' → ' + (bwa.hotkey || 'none')] });
  const known = new Set(['menus', 'ring', 'bridge', 'browser']);
  const other = [...new Set([...Object.keys(before), ...Object.keys(after)])].filter(k => !known.has(k) && JSON.stringify(before[k]) !== JSON.stringify(after[k]));
  if (other.length) groups.push({ area: 'Other', lines: other.map(k => 'Changed ' + k) });
  return groups;
}

async function openCloseDialog() {
  if (S.closeDialogOpen) return;
  if (!dirtyNow()) { call('close_now').catch(() => {}); return; }
  S.closeDialogOpen = true;
  const groups = describeChanges();
  const count = groups.reduce((n, g) => n + g.lines.length, 0);
  const body = h('div', { class: 'changes' },
    h('p', null, count ? `You have ${count} unsaved change${count === 1 ? '' : 's'}. Closing without saving loses ${count === 1 ? 'it' : 'them'}.` : 'You have unsaved changes. Closing without saving loses them.'),
    h('div', { class: 'changes-list' }, groups.map(g => h('div', { class: 'chg-group' },
      h('div', { class: 'micro' }, g.area),
      h('ul', null, g.lines.map(l => h('li', null, l)))))));
  const v = await modal({ title: 'Unsaved changes', body, actions: [
    { text: 'Keep editing', value: 'keep' },
    { text: 'Close without saving', value: 'discard', kind: 'danger-ghost' },
    { text: 'Save and close', value: 'save', kind: 'primary' }] });
  S.closeDialogOpen = false;
  if (v === 'save') { const out = await save(); if (out === 'saved' && !dirtyNow()) call('close_now').catch(() => {}); }
  else if (v === 'discard') call('close_now').catch(() => {});
}
// Called by studio.py when the window is about to close and the page has unsaved changes.
window.__studioRequestClose = () => { openCloseDialog(); return true; };

function licenceVisible() { return S.prefs.show_licence !== false; }
function applyPrefs() {
  const btn = document.querySelector('.rail-btn[data-screen="licence"]');
  if (btn) btn.hidden = !licenceVisible();
}
/* Resolves true when the backend stored it. On a failed write the old value comes back, a toast says so, and false lets
   a toggleSwitch put itself back. */
async function setPref(key, value) {
  const prev = S.prefs[key];
  S.prefs[key] = value;
  applyPrefs();
  try {
    const p = await call('set_pref', key, value);
    if (p && key in p && p[key] !== value) throw new Error('not stored');
    if (p) S.prefs = Object.assign(S.prefs, p);
    return true;
  } catch (e) {
    S.prefs[key] = prev; applyPrefs();
    toast('Could not save that preference', { tone: 'warn' });
    return false;
  }
}

const SCREENS = { menus: buildMenusScreen, library: buildLibraryScreen, settings: buildSettingsScreen, status: buildStatusScreen, setup: buildSetupScreen, licence: buildLicenceScreen };
// the element that scrolls on each screen (its position is remembered when you leave and put back when you return)
const SCREEN_SCROLLER = { menus: '.ilist', library: '.b-scroll', settings: '.settings-scroll', status: '.settings-scroll', setup: '.settings-scroll', licence: '.settings-scroll' };
const scrollerOf = name => { const root = $('#screen-' + name); return root ? $(SCREEN_SCROLLER[name] || '.settings-scroll', root) : null; };
let lastScreenChain = Promise.resolve();   // writes run one after another, so two quick switches cannot land out of order
const saveLastScreen = name => { lastScreenChain = lastScreenChain.then(() => call('set_pref', 'last_screen', name)).catch(() => {}); };
function showScreen(name, { fresh = false } = {}) {
  if (!SCREENS[name] || (name === 'licence' && !licenceVisible())) name = 'menus';
  if (openPopover) openPopover();
  if (comboClose) comboClose();
  if (S.shown && name === S.screen) return;
  if (S.shown) { const old = scrollerOf(S.screen); if (old) S.scroll[S.screen] = old.scrollTop; }
  for (const k of Object.keys(R)) delete R[k];
  clearInterval(statusTimer);
  S.screen = name; S.shown = true;
  if (S.ready) { S.prefs.last_screen = name; saveLastScreen(name); }
  const loading = $('#screens > .loading'); if (loading) loading.remove();
  $$('.rail-btn').forEach(b => { const on = b.dataset.screen === name; b.classList.toggle('on', on); b.setAttribute('aria-current', on ? 'page' : 'false'); });
  $$('.screen').forEach(s => { s.hidden = s.id !== 'screen-' + name; });
  SCREENS[name]($('#screen-' + name));
  const top = S.scroll[name];
  if (!fresh && top) requestAnimationFrame(() => { if (S.screen !== name) return; const el = scrollerOf(name); if (el) el.scrollTop = top; });
}

/* ================================================================== boot */
/* Reads one kind's library into S.libs[kind]. A rescan (refresh) keeps showing the current items until the new list arrives. */
async function loadLibrary(kind = 'brush', refresh = false) {
  const L = lib(kind);
  if (!refresh) L.state = 'loading';
  L.busy = true; paintRescan();
  let r = null;
  try { r = await call('get_library', !!refresh, kind); } catch (e) { r = { error: String((e && e.message) || e) }; }
  r = r || {};
  L.items = Array.isArray(r.items) ? r.items : Array.isArray(r.brushes) ? r.brushes : [];
  L.sources = Array.isArray(r.sources) ? r.sources : [];
  L.zbrushFound = r.zbrush_found !== false;
  L.error = r.error ? String(r.error) : null;
  L.sorted = L.items.slice().sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true }));
  L.byName = new Map(L.items.map(b => [nameKey(b.name), b]));
  L._tree = L._tc = null;
  L.state = L.error ? 'error' : 'ready';
  L.loaded = true; L.busy = false;
  if (refresh) Thumbs.forgetMisses(kind);
  if (R.libRefresh) R.libRefresh(kind);
  if (S.screen === 'menus' && R.right && S.tab === 'item') R.right();     // the inspector resolves names against the library
  paintRescan();
}
async function loadSuggestions() {
  try { S.suggestions = (await call('get_suggestions')) || []; } catch (e) { S.suggestions = []; }
  if (S.screen === 'menus' && S.tab === 'item' && R.right && !document.activeElement.closest('.insp')) R.right();
}

/* Shown instead of the app when the menus file cannot be read. `res` is the get_config result (config null, error set) or an Error. */
function recovery(res) {
  S.fatal = true; S.ready = false;
  const isErr = res instanceof Error;
  const msg = isErr ? (res.message || String(res)) : ((res && res.error) || 'The file could not be read.');
  const path = isErr ? '' : String((res && res.path) || '');
  const backup = !isErr && !!(res && res.backup_exists);
  const loading = $('#screens > .loading'); if (loading) loading.remove();
  $$('.rail-btn').forEach(b => { b.classList.remove('on'); b.setAttribute('aria-current', 'false'); });
  $('#saveBtn').disabled = true; $('#revertBtn').disabled = true;
  if (path) setPathHint(path);
  const run = async (btn, method) => {
    btn.disabled = true;
    try {
      const r = await call(method);
      toast((r && r.message) || (r && r.ok ? 'Done.' : 'That did not work.'), { tone: r && r.ok ? 'ok' : 'warn', ms: 4000 });
      if (r && r.ok) { setTimeout(() => location.reload(), 700); return; }
    } catch (e) { toast('That failed: ' + (e.message || e), { tone: 'err' }); }
    btn.disabled = false;
  };
  const folderBtn = h('button', { class: 'btn', type: 'button', onclick: async () => { try { await call('open_folder', 'config'); } catch (e) { toast('Could not open the folder.', { tone: 'warn' }); } } }, icon('folder', 13), 'Open folder');
  const restoreBtn = backup ? h('button', { class: 'btn', type: 'button', onclick: () => run(restoreBtn, 'restore_backup') }, icon('undo', 13), 'Restore backup') : null;
  const resetBtn = h('button', { class: 'btn danger-ghost', type: 'button', onclick: async () => {
    const ok = await modal({ title: 'Start from defaults?',
      body: h('p', null, 'This replaces your menus file with the built-in default menus. Anything in the current file is lost, so use Open folder first if you want to keep a copy.'),
      actions: [{ text: 'Cancel', value: false, focus: true }, { text: 'Start from defaults', value: true, kind: 'danger' }] });
    if (ok) run(resetBtn, 'reset_config');
  } }, 'Start from defaults');
  $$('.screen').forEach(sc => { sc.hidden = sc.id !== 'screen-menus'; });
  $('#screen-menus').replaceChildren(h('div', { class: 'fatal' }, icon('alert', 36), h('h2', null, 'Could not read your menus file'),
    path ? h('p', { class: 'fatal-path mono' }, path) : null,
    h('pre', { class: 'fatal-err mono' }, msg),
    h('p', { class: 'fatal-lead' }, backup ? 'Nothing has been changed. You can fix the file yourself, restore the last good backup, or start again from the defaults.' : 'Nothing has been changed. You can fix the file yourself or start again from the defaults.'),
    h('div', { class: 'btn-row' }, folderBtn, restoreBtn, resetBtn, h('button', { class: 'btn primary', type: 'button', onclick: () => location.reload() }, 'Try again'))));
}

async function boot() {
  const [cfgR, optR, prefR] = await Promise.allSettled([call('get_config'), call('get_options'), call('get_prefs')]);
  if (cfgR.status === 'rejected') { recovery(cfgR.reason instanceof Error ? cfgR.reason : new Error(String(cfgR.reason))); return; }
  const cfgRes = cfgR.value;
  if (!cfgRes || !cfgRes.config || typeof cfgRes.config !== 'object' || Array.isArray(cfgRes.config)) { recovery(cfgRes || new Error('The backend returned no config.')); return; }
  const opts = optR.status === 'fulfilled' ? optR.value : null;     // a failed get_options just means the FALLBACK_* lists are used
  if (prefR.status === 'fulfilled' && prefR.value) S.prefs = Object.assign(S.prefs, prefR.value);
  adoptConfig(cfgRes);
  S.opts = opts; S.defaults = Object.assign({}, FALLBACK_DEFAULTS, cfgRes.defaults || (opts && opts.ring_defaults) || {});
  S.defaults.colors = Object.assign({}, FALLBACK_DEFAULTS.colors, S.defaults.colors || {});
  const ids = Object.keys(S.cfg.menus);
  S.menuId = params.get('menu') && S.cfg.menus[params.get('menu')] ? params.get('menu') : (ids.find(id => S.cfg.menus[id].hotkey) || ids[0] || null);
  const m0 = curMenu();
  if (params.has('item') && m0 && m0.items[+params.get('item')]) { S.itemIdx = +params.get('item'); S.tab = 'item'; }
  else S.tab = params.get('tab') || 'menu';
  if (params.get('q')) S.lib.q = params.get('q');
  if (params.get('cat')) S.lib.cat = params.get('cat');
  if (isLib(params.get('kind'))) S.lib.kind = params.get('kind');
  if (params.get('dock')) S.dock.cat = params.get('dock');
  setPathHint(S.path);
  updateDirty(); renderProblems();
  applyPrefs();
  loadLibrary(); loadSuggestions(); loadTags();
  showScreen(params.get('screen') || (S.prefs.setup_done === false ? 'setup' : (S.prefs.last_screen || 'menus')));
  S.ready = true;
  rememberSel(); updateHistButtons();
  $('#saveBtn').disabled = false;
  refreshZsBadge();
  if (S.screen !== 'setup') refreshSetupBadge();
  if (S.screen !== 'status') refreshAppDown();
  if (params.has('hover')) { /* debug aid */ }
  document.documentElement.classList.add('ready');
}

/* The path in the top bar, with its Copy path button (hidden while there is no path). */
function setPathHint(path) {
  const el = $('#pathHint'), btn = $('#copyPath');
  el.textContent = path || ''; el.title = path || '';
  if (btn) btn.hidden = !path;
}

function init() {
  if (POPOUT) { initPopout(); return; }
  const cp = $('#copyPath');
  if (cp) {
    cp.append(icon('copy', 13));
    cp.addEventListener('click', async () => {
      const path = S.path || $('#pathHint').textContent;
      if (!path) return;
      if (await copyText(path)) toast('Path copied', { ms: 1800 }); else toast('Could not copy the path', { tone: 'warn' });
    });
  }
  const skip = $('#skipLink');
  if (skip) skip.addEventListener('click', e => { e.preventDefault(); const main = $('#screens'); if (main) main.focus(); });
  $$('.rail-btn').forEach(b => b.addEventListener('click', () => { if (S.ready && !S.fatal) showScreen(b.dataset.screen); }));
  $('#saveBtn').addEventListener('click', () => save());
  $('#revertBtn').addEventListener('click', revert);
  $('#undoBtn').append(icon('undo', 16)); $('#redoBtn').append(icon('redo', 16));
  $('#browserBtn').prepend(icon('k_browser', 13));
  $('#browserBtn').addEventListener('click', openBrowserWindow);   // works before the config loads: the browser needs none
  $('#undoBtn').addEventListener('click', () => { if (S.ready && !S.fatal) undo(); });
  $('#redoBtn').addEventListener('click', () => { if (S.ready && !S.fatal) redo(); });
  $('#problemsBtn').addEventListener('click', () => { S.problemsOpen = !S.problemsOpen; renderProblems(); });
  document.addEventListener('mousedown', e => { if (S.problemsOpen && !e.target.closest('#problemsPanel, #problemsBtn')) closeProblems(false); }, true);
  window.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || !S.problemsOpen || e.defaultPrevented || $('#overlay-root').firstElementChild) return;
    e.preventDefault(); closeProblems(true);
  });
  window.addEventListener('resize', () => { if (S.problemsOpen) placeProblemsPanel(); });
  window.addEventListener('keydown', e => {
    const ours = ((e.ctrlKey || e.metaKey) && !e.altKey && /^[szy]$/i.test(e.key)) || (e.altKey && !e.ctrlKey && !e.shiftKey && /^[1-6]$/.test(e.key));
    if ($('#overlay-root').firstElementChild) { if (ours) e.preventDefault(); return; }   // a dialog is open: our shortcuts stay quiet, and the web view must not get Ctrl+S either
    const ed = e.target && e.target.closest && e.target.closest('input, textarea, select, [contenteditable]');
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 's') { e.preventDefault(); if (S.ready && !S.fatal) save(); }
    else if (!S.ready || S.fatal) return;
    else if ((e.ctrlKey || e.metaKey) && !e.altKey && !ed && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    else if ((e.ctrlKey || e.metaKey) && !e.altKey && !ed && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); }
    else if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && !ed && e.key.toLowerCase() === 'd') {     // Ctrl+D stars the card in focus (or the selection it is in)
      const card = e.target && e.target.closest && e.target.closest('.bcard[data-name]');
      const b = card && Array.from(browsers.values()).find(x => x.el.contains(card));
      if (b) { e.preventDefault(); b.toggleFav(card.dataset.name); }
    }
    else if (e.altKey && !e.ctrlKey && !e.shiftKey && /^[1-6]$/.test(e.key)) { e.preventDefault(); const scr = ['menus', 'library', 'settings', 'status', 'licence', 'setup'][+e.key - 1]; if (scr !== 'licence' || licenceVisible()) showScreen(scr); }
  });
  window.addEventListener('focus', debounce(() => { if (S.ready && !S.fatal) { loadTags(); reloadUsage(); } }, 300));      // tags.json may have changed (the popout, a hand edit), and picks add to Recent
  window.addEventListener('focus', debounce(() => { if (S.ready && !S.fatal && S.screen !== 'setup') refreshSetupBadge(); }, 600));   // the Setup screen polls for itself
  window.addEventListener('beforeunload', e => { if (dirtyNow()) { e.preventDefault(); e.returnValue = ''; } });
  const showErr = msg => {
    console.error(msg);
    if (!params.has('mock') && !params.has('debug')) return;
    let bar = $('#errbar');
    if (!bar) { bar = h('div', { id: 'errbar', class: 'errbar' }); document.body.append(bar); }
    bar.append(h('div', null, String(msg)));
  };
  window.addEventListener('error', e => showErr('Uncaught: ' + e.message + ' (' + (e.filename || '').split('/').pop() + ':' + e.lineno + ')'));
  window.addEventListener('unhandledrejection', e => showErr('Unhandled rejection: ' + (e.reason && e.reason.message || e.reason)));
  window.__studio = { S, R, h };
  boot();
}

/* ================================================================== POPOUT (popout.html) */
/* The browser popout: a window of its own that stays open until it is closed (zorbit/popout.py). Picking a brush, alpha, material or texture
   selects it in ZBrush through the app and hands the keyboard back to ZBrush. The Python side calls __popoutShow({tag, kind}) each time the
   window is shown afresh (kind null keeps the current tab) and __popoutFocus() once it has the foreground. */
let popBrowser = null, popTabs = null, popWant, popPicking = false;
const popHide = () => { call('popout_hide').catch(() => {}); };
const POP_HOST = {
  dnd: false,
  nativeDrag: true,                                  // cards drag out to the Studio window, the OS way
  firstMatch: true,                                  // after a search, the first match is highlighted
  primaryIcon: kind => KIND[kind].icon,
  primaryLabel: () => 'Select in ZBrush',
  canPrimary: n => n === 1,
  async primary(name, kind) {
    if (popPicking) return;
    popPicking = true;
    let r;
    try { r = await call('popout_pick', name, kind); } catch (e) { r = { ok: false, error: 'Could not reach ZOrbit: ' + ((e && e.message) || e) }; }
    popPicking = false;
    if (r && r.ok) toast('Selected ' + name, { tone: 'ok', ms: 1400 });
    else toast((r && r.error) || 'ZOrbit is not running', { tone: 'warn', ms: 3800 });
  },
  primaryMany(names, kind) { const w = K(kind).one; toast(`ZBrush takes one ${w} at a time. Select a single ${w}.`, { tone: 'warn', ms: 2600 }); },
  cardTitle: () => 'Select in ZBrush',
  cardLabel: (name, kind) => 'Select ' + name + ' in ZBrush',
  enterHint: 'Press Enter to select it in ZBrush.',
  hint: () => [],                                          // the popout shows no hint line
  badge: null,                                       // no "In my menus" folder, no badges: the popout knows nothing of menus
  onKind: kind => { if (popTabs) popTabs.paint(); call('popout_set_kind', kind).catch(() => {}); },   // the header tabs follow every switch
  onSize: debounce(px => { call('popout_set_size', px).catch(() => {}); }, 400),
};

/* The browser's mark (assets/browser.ico): a dark disc with a 2x2 grid of outlined tiles, three in the accent and the last in cyan. */
function popLogo() {
  const tile = (x, y, c) => `<rect x="${x}" y="${y}" width="4.5" height="4.5" rx=".8" fill="var(--bg1)" stroke="var(${c})" stroke-width="1"/>`;
  const s = h('span', { class: 'pop-logo', 'aria-hidden': 'true' });
  s.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18"><circle cx="12" cy="12" r="10.85" fill="var(--bg1)" stroke="rgba(255,255,255,.16)" stroke-width=".32"/>'
    + tile(5.6, 5.6, '--accent') + tile(13.9, 5.6, '--accent') + tile(5.6, 13.9, '--accent') + tile(13.9, 13.9, '--cyan') + '</svg>';
  return s;
}

function buildPopout(root) {
  const pin = h('button', { class: 'ibtn pin-btn', type: 'button', onclick: () => setOnTop(!S.popOnTop) }, icon('pin', 15));
  const paintPin = () => {
    pin.setAttribute('aria-pressed', S.popOnTop ? 'true' : 'false'); pin.title = 'Keep on top'; pin.setAttribute('aria-label', 'Keep on top');
  };
  async function setOnTop(on) {
    S.popOnTop = on; paintPin();
    try { await call('popout_set_on_top', on); }
    catch (e) { S.popOnTop = !on; paintPin(); toast('Could not change Keep on top.', { tone: 'warn' }); }
  }
  paintPin();
  // The folders and tags column: shown or collapsed (popout.json "column"), on the left or the right ("side").
  // The column button is pressed while the column shows and draws it on its side; the side button only shows with it.
  const col = h('button', { class: 'ibtn col-btn', type: 'button', onclick: () => setColumn(!S.popColumn) });
  const side = h('button', { class: 'ibtn side-btn', type: 'button', onclick: () => setSide(S.popSide === 'right' ? 'left' : 'right') }, icon('swap_h', 15));
  const paintSide = () => {
    const right = S.popSide === 'right', label = 'Move the folders and tags to the ' + (right ? 'left' : 'right');
    const colLabel = (S.popColumn ? 'Hide' : 'Show') + ' the folders and tags';
    side.title = label; side.setAttribute('aria-label', label); side.hidden = !S.popColumn;
    col.replaceChildren(icon(right ? 'side_r' : 'side_l', 15)); col.title = colLabel; col.setAttribute('aria-label', colLabel);
    col.setAttribute('aria-pressed', S.popColumn ? 'true' : 'false');
    root.classList.toggle('side-right', right); root.classList.toggle('col-hidden', !S.popColumn);
  };
  async function setColumn(on) {
    S.popColumn = on; paintSide();
    try { await call('popout_set_column', on); }
    catch (e) { S.popColumn = !on; paintSide(); toast('Could not change the folders column.', { tone: 'warn' }); }
  }
  async function setSide(s) {
    const was = S.popSide;
    S.popSide = s; paintSide();
    try { await call('popout_set_side', s); }
    catch (e) { S.popSide = was; paintSide(); toast('Could not move the folders column.', { tone: 'warn' }); }
  }
  paintSide();
  const head = h('header', { class: 'pop-head' },
    popLogo(), (popTabs = kindTabs(() => S.pop.kind, k => popBrowser.setKind(k), 'pop')).el,
    h('div', { class: 'spacer' }), side, col, pin,
    h('div', { class: 'winctl' }, h('button', { class: 'winbtn close', type: 'button', title: 'Close', 'aria-label': 'Close', onclick: popHide }, icon('x', 14))));
  popBrowser = makeBrowser({ compact: false, st: S.pop, host: POP_HOST, kindUi: 'none' });   // the tabs live in the header
  root.replaceChildren(head, h('div', { class: 'pop-body' }, popBrowser.el));
  R.libRefresh = kind => { if (kind === S.pop.kind) { popBrowser.refresh(); popBrowser.highlightFirst(); } };
}

/* Called by popout.py each time the window is shown. Starts from a clean slate: no search, no folder, the given tag only, the first match
   highlighted. A tag the page has not heard of (made in the Studio a moment ago) is looked for once more with a forced reload. */
window.__popoutShow = o => {
  const tag = (o && o.tag) || null, kind = o && isLib(o.kind) ? o.kind : null, reset = !o || o.reset !== false;
  if (!popBrowser) { popWant = { tag, kind, reset }; return false; }
  if (kind) popBrowser.setKind(kind);
  if (reset || tag) popBrowser.setFilter(tag);          // a tab switch alone keeps the search and tag filter
  popBrowser.focusSearch();
  reloadUsage();                                        // picks made since the window was last shown
  const stale = !!tag && !S.tagMap.has(tag);
  loadTags(stale).then(() => { if (stale && S.tagMap.has(tag)) popBrowser.setFilter(tag); });
  return true;
};
window.__popoutFocus = () => { if (popBrowser) popBrowser.focusSearch(false); return document.hasFocus(); };

async function bootPopout() {
  S.cfg = { menus: {} };                             // the tag manager reads the ring items; the popout has none
  let state = null;
  try { state = await call('popout_get_state'); } catch (e) { state = null; }
  if (state) {
    S.popOnTop = state.on_top !== false;
    if (+state.size >= 84) S.pop.size = clamp(+state.size, 84, 220);
    S.popSide = state.side === 'right' ? 'right' : 'left';
    S.popColumn = state.column !== false;
    if (state.tag === FAV) S.pop.cat = '@fav';           // Favourites is a folder, not a chip
    else if (state.tag) S.pop.tags = new Set([String(state.tag)]);
    if (isLib(state.kind)) S.pop.kind = state.kind;
  }
  buildPopout($('#app'));                            // makeBrowser loads the library of the starting tab
  loadTags();
  S.ready = true;
  document.documentElement.classList.add('ready');
  if (popWant) { const w = popWant; popWant = undefined; window.__popoutShow(w); }
}

function initPopout() {
  window.addEventListener('keydown', e => {
    if (!popBrowser || e.isComposing) return;
    if ($('#overlay-root').firstElementChild || $('.popover')) return;       // a dialog or a popover has the keys
    if (e.key === 'Escape') {                                                // the search box and the selection take theirs first (they stop or prevent it)
      if (e.defaultPrevented) return;
      e.preventDefault(); call('popout_release_focus').catch(() => {});      // nothing left to clear: the keyboard goes back to ZBrush
      return;
    }
    if (e.key === 'Tab' && e.ctrlKey && !e.metaKey && !e.altKey) {           // Ctrl+Tab / Ctrl+Shift+Tab cycle the tabs
      const n = LIB_KINDS.length;
      e.preventDefault(); popBrowser.setKind(LIB_KINDS[(Math.max(0, LIB_KINDS.indexOf(popBrowser.kind())) + (e.shiftKey ? n - 1 : 1)) % n]);
      return;
    }
    if (e.key.toLowerCase() === 'd' && (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey) {   // Ctrl+D stars the highlighted item (or the selection)
      e.preventDefault();
      const card = e.target && e.target.closest && e.target.closest('.bcard[data-name]');
      popBrowser.toggleFav(card ? card.dataset.name : null);
      return;
    }
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
    const t = e.target, typing = !!(t && t.closest && t.closest('input, textarea, select, [contenteditable]')), inSearch = popBrowser.inSearch(t);
    if (e.key.startsWith('Arrow')) {
      if (typing && !inSearch) return;
      const dx = e.key === 'ArrowLeft' ? -1 : e.key === 'ArrowRight' ? 1 : 0, dy = e.key === 'ArrowUp' ? -1 : e.key === 'ArrowDown' ? 1 : 0;
      if (inSearch && dx && popBrowser.searchValue()) return;               // the caret moves inside a query
      e.preventDefault(); popBrowser.move(dx, dy);
    } else if (e.key === 'Enter') {
      if (typing && !inSearch) return;
      if (t && t.closest && t.closest('button, a, .bcard, [role="option"]')) return;   // the focused control has its own Enter
      e.preventDefault(); popBrowser.pickSelected();
    } else if (e.key.length === 1 && e.key !== ' ' && !typing) {
      e.preventDefault();                                                    // the key goes into the search box ourselves:
      popBrowser.focusSearch(false); popBrowser.typeChar(e.key);             // a focus change can swallow the first keypress
    }
  });
  window.addEventListener('contextmenu', e => {                              // the web view's own menu is a window of another
    if (!(e.target && e.target.closest && e.target.closest('.bcard'))) e.preventDefault();   // process and would read as leaving
  });
  window.addEventListener('focus', debounce(() => { if (S.ready) { loadTags(); reloadUsage(); } }, 300));      // tags.json may have changed (the Studio), and picks add to Recent
  const log = msg => { console.error(msg); try { call('popout_log', String(msg).slice(0, 500)).catch(() => {}); } catch (e) { /* no backend */ } };
  window.addEventListener('error', e => log('Uncaught: ' + e.message + ' (' + (e.filename || '').split('/').pop() + ':' + e.lineno + ')'));
  window.addEventListener('unhandledrejection', e => log('Unhandled rejection: ' + (e.reason && e.reason.message || e.reason)));
  window.__studio = { S, R, h };
  bootPopout();
}

function whenReady(fn) {
  const probe = POPOUT ? 'popout_get_state' : 'get_config';
  const ok = () => window.pywebview && window.pywebview.api && typeof window.pywebview.api[probe] === 'function';
  if (ok()) { fn(); return; }
  let done = false;
  const go = () => { if (done || !ok()) return; done = true; fn(); };
  window.addEventListener('pywebviewready', go);
  const iv = setInterval(() => { go(); if (done) clearInterval(iv); }, 150);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => whenReady(init)); else whenReady(init);
})();
