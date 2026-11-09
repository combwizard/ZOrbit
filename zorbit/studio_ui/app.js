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
  look: '<circle cx="12" cy="12" r="9"/><path d="M12 7.2l4.2 2.4v4.8L12 16.8l-4.2-2.4V9.6z"/>',
  settings: '<path d="M4 7h8M18 7h2M4 12h5M13 12h7M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="11" cy="12" r="2"/><circle cx="9" cy="17" r="2"/>',
  status: '<path d="M3 12h4l2.5-6 4 12 2.5-6H21"/>',
  setup: '<path d="M5 7l1.5 1.5L9 6M5 12l1.5 1.5L9 11M5 17l1.5 1.5L9 16"/><path d="M12 7h8M12 12h8M12 17h8"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  minus: '<path d="M5 12h14"/>',
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
  revert: '<path d="M3.5 12a8.5 8.5 0 1 0 2.8-6.3L3.5 8.3"/><path d="M3.5 3.5v4.8h4.8"/><path d="M12 7.5V12l3.2 1.9"/>',
  save: '<path d="M5 3.5h10.6L20.5 8.4V19a1.5 1.5 0 0 1-1.5 1.5H5A1.5 1.5 0 0 1 3.5 19V5A1.5 1.5 0 0 1 5 3.5z"/><path d="M7.5 20.5v-6.5h9v6.5"/><path d="M7.5 3.5v4h7"/>',
  redo: '<path d="M20 12a8 8 0 1 0-3 6.2M20 5v5h-5"/>',
  record: '<circle cx="12" cy="12" r="5" fill="currentColor" stroke="none"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.4"/>',
  external: '<path d="M14 5h5v5M19 5l-8 8M18 14v4a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h4"/>',
  k_brush: '<path d="M20 4c-5.200.8-9.200 4.800-10.600 9.300l1.300 1.300C15.200 13.200 19.200 9.200 20 4z"/><path d="M9.300 13.600C6.800 13.100 4.800 14.800 4.800 17.200c0 1.500-.6 2.500-1.600 3 3.200.6 7.200-.6 7.200-4"/>',
  k_press: '<path d="M7 4.500l10.500 7.200-4.800 1.100 2.600 5.200-2.100 1-2.600-5.200L7 16.500z"/>',
  k_set: '<path d="M4 12h6M16 12h4"/><circle cx="13" cy="12" r="3"/>',
  k_toggle: '<rect x="3" y="7.500" width="18" height="9" rx="4.500"/><circle cx="16.500" cy="12" r="2.300" fill="currentColor" stroke="none"/>',
  k_capture: '<path d="M4 8.500a1.500 1.500 0 0 1 1.500-1.500h2.300l1.500-2.300h5.400l1.500 2.300h2.300A1.500 1.500 0 0 1 20 8.500v8a1.500 1.500 0 0 1-1.500 1.500h-13A1.500 1.500 0 0 1 4 16.500z"/><circle cx="12" cy="12.500" r="3.200"/>',
  k_tool: '<path d="M12 3.500l7.500 4.300v8.400L12 20.500l-7.500-4.300V7.800z"/><path d="M4.500 7.800L12 12.100l7.500-4.300M12 12.100v8.400"/>',
  k_project: '<path d="M3.500 7.500a1.500 1.500 0 0 1 1.500-1.500h4.200l1.800 2h8a1.500 1.500 0 0 1 1.500 1.500v7.500a1.500 1.500 0 0 1-1.500 1.500H5a1.500 1.500 0 0 1-1.500-1.500z"/>',
  k_layout: '<rect x="3.500" y="5" width="17" height="14" rx="1.500"/><path d="M9.500 5v14M9.500 12h11"/>',
  k_steps: '<path d="M12 4l8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4M4 16l8 4 8-4"/>',
  k_menu: '<circle cx="12" cy="12" r="8.500"/><path d="M10 8.500l5 3.500-5 3.500z" fill="currentColor"/>',
  k_auto: '<path d="M19.500 12a7.500 7.500 0 0 1-13 5.100M4.500 12a7.500 7.500 0 0 1 13-5.100"/><path d="M17.500 3.500v3.400h-3.400M6.500 20.500v-3.400h3.400"/>',
  k_alpha: '<circle cx="12" cy="12" r="8.500"/><circle cx="12" cy="12" r="3.200" fill="currentColor" stroke="none" opacity=".5"/>',
  k_material: '<circle cx="12" cy="12" r="8"/><path d="M7.500 15.500a6 6 0 0 0 9-6.500"/><circle cx="9.300" cy="9.300" r="1.300" fill="currentColor" stroke="none"/>',
  k_texture: '<rect x="4.500" y="4.500" width="15" height="15" rx="1.300"/><path d="M12 4.500v15M4.500 12h15"/><path d="M4.500 4.500h7.500v7.500H4.500zM12 12h7.500v7.500H12z" fill="currentColor" stroke="none" opacity=".45"/>',
  side_l: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M9 4.5v15"/>',
  side_r: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M15 4.5v15"/>',
  swap_h: '<path d="M4 9h15M15 5l4 4-4 4M20 15H5M9 11l-4 4 4 4"/>',
  k_empty: '<circle cx="12" cy="12" r="8" stroke-dasharray="3.200 3.200"/>',
  k_browser: '<rect x="4.500" y="4.500" width="6" height="6" rx="1.300"/><rect x="13.500" y="4.500" width="6" height="6" rx="1.300"/><rect x="4.500" y="13.500" width="6" height="6" rx="1.300"/><rect x="13.500" y="13.500" width="6" height="6" rx="1.300"/>',
  tag: '<path d="M20.600 13.400l-7.200 7.200a2 2 0 0 1-2.800 0L3 13V3h10l7.600 7.600a2 2 0 0 1 0 2.800z"/><circle cx="7.500" cy="7.500" r="1.300" fill="currentColor" stroke="none"/>',
  pin: '<path d="M9 4h6l-.8 5.500L17 13H7l2.800-3.500z"/><path d="M12 13v7"/>',
  strip: '<rect x="2.500" y="9" width="5" height="6" rx="1.200"/><rect x="9.500" y="9" width="5" height="6" rx="1.200"/><rect x="16.500" y="9" width="5" height="6" rx="1.200"/>',
  chev_u: '<path d="M6 15l6-6 6 6"/>',
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
/* Roving tabindex: a list is one Tab stop (the row `cur`, else its first row); the arrow keys move inside it. */
function setRoving(rows, cur) { const stop = rows.includes(cur) ? cur : rows[0]; rows.forEach(x => { x.tabIndex = x === stop ? 0 : -1; }); }
/* Row buttons are reached with the mouse or a shortcut (Delete, F2, Alt+Up/Down), not the Tab key. */
function noTab(btn) { btn.tabIndex = -1; return btn; }

/* ================================================================== state */
const ACTIONS = ['brush', 'alpha', 'material', 'texture', 'press', 'set', 'toggle', 'capture', 'tool', 'project', 'layout', 'steps', 'menu', 'auto', 'tag', 'browser', 'recent', 'empty'];
const FILE_KINDS = ['tool', 'project', 'layout'];                  // the items that name a file on this PC (FILE_EXTS in config.py)
/* What a Recent item lists (RECENT_KINDS and RECENT_LABELS in config.py): its Shows choice, its label when it has none, and its line in the item list. */
const RECENT = {
  project: { shows: 'Projects', label: 'Recent projects', sub: 'recent projects', what: 'projects' },
  tool: { shows: 'Tools', label: 'Recent tools', sub: 'recent tools', what: 'tools' },
  any: { shows: 'Both', label: 'Recent', sub: 'recent projects and tools', what: 'projects and tools' },
};
const KIND = {
  brush: { label: 'Brush', icon: 'k_brush', hint: 'Select a brush' },
  alpha: { label: 'Alpha', icon: 'k_alpha', hint: 'Select an alpha' },
  material: { label: 'Material', icon: 'k_material', hint: 'Select a material' },
  texture: { label: 'Texture', icon: 'k_texture', hint: 'Select a texture' },
  press: { label: 'Press', icon: 'k_press', hint: 'Press any ZBrush button' },
  set: { label: 'Set', icon: 'k_set', hint: 'Set a slider or value' },
  toggle: { label: 'Toggle', icon: 'k_toggle', hint: 'Flip a switch' },
  capture: { label: 'Capture', icon: 'k_capture', hint: 'Save the picture as a PNG' },
  tool: { label: 'Tool', icon: 'k_tool', hint: 'Load a tool from a file' },
  project: { label: 'Project', icon: 'k_project', hint: 'Open a project, or the newest in a folder' },
  layout: { label: 'Layout', icon: 'k_layout', hint: 'Load a UI layout from a file' },
  steps: { label: 'Steps', icon: 'k_steps', hint: 'Run several actions in order' },
  menu: { label: 'Submenu', icon: 'k_menu', hint: 'Open another ring' },
  auto: { label: 'Auto', icon: 'k_auto', hint: 'A slot filled with a brush you pick often' },
  tag: { label: 'Tag', icon: 'tag', hint: 'Every item with a tag: brushes first, most used first (or your own order on Favourites), then alphas, materials and textures' },
  browser: { label: 'Browser', icon: 'k_browser', hint: 'Open the browser' },
  recent: { label: 'Recent', icon: 'clock', hint: 'A fan of the projects and tools ZBrush opened last' },
  empty: { label: 'Empty slot', icon: 'k_empty', hint: 'Holds its place in the ring and does nothing' },
};
/* The kinds of asset the library holds (brushes, alphas, materials, textures) and their wording; every "brush/brushes" string reads from here. */
const KINDS = {
  brush:    { one: 'brush',    many: 'brushes',   tab: 'Brushes',   ext: '.zbp', exts: '.zbp', files: 'a .zbp file', eg: 'ClayBuildup' },
  alpha:    { one: 'alpha',    many: 'alphas',    tab: 'Alphas',    ext: '.psd', exts: '.psd, .bmp, .jpg, .jpeg, .png, .tif or .tiff', files: 'a .psd, .bmp, .jpg, .png or .tif file', eg: 'Alpha 058' },
  material: { one: 'material', many: 'materials', tab: 'Materials', ext: '.zmt', exts: '.zmt', files: 'a .zmt file', eg: 'SkinShade4' },
  texture:  { one: 'texture',  many: 'textures',  tab: 'Textures',  ext: '.psd', exts: '.psd, .jpg, .jpeg, .png, .bmp, .tif, .tiff or .exr', files: 'a .psd, .jpg, .png, .bmp, .tif or .exr file', eg: 'Txtr01' },
};
const LIB_KINDS = Object.keys(KINDS);
const own = (o, k) => o != null && Object.prototype.hasOwnProperty.call(o, k);
const isLib = k => typeof k === 'string' && own(KINDS, k);
/* Names every object already has (constructor, __proto__, toString ...); never menu ids. */
const RESERVED_IDS = new Set(Object.getOwnPropertyNames(Object.prototype));
const hasMenu = id => typeof id === 'string' && !!S.cfg && own(S.cfg.menus, id);
const menuOf = id => (hasMenu(id) ? S.cfg.menus[id] : undefined);
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
  accent: ['Accent', 'Centre dot, hover and title'],
  highlight: ['Highlight', 'Submenus'],
  text: ['Text', 'Labels'],
  lines: ['Lines', 'Spokes and guides'],
};
const BRIDGE_INFO = {
  auto: ['Auto', 'Recommended. Uses the plugin’s listener inside ZBrush when it is running and falls back to the bridge key otherwise (or if a message is not picked up within half a second).'],
  message: ['Message', 'Posts a message to a small window the plugin keeps inside ZBrush (its listener). No keystroke is sent, so nothing can collide with your own shortcuts. Needs the ZOrbit plugin loaded in ZBrush. If the plugin is not listening, the pick is dropped and logged.'],
  key: ['Key', 'Presses the bridge key. Bind that key in ZBrush to Zplugin > ZOrbit > Apply (Ctrl+Alt+click the button, press the key, then Preferences > Hotkeys > Store).'],
};
const FALLBACK_DEFAULTS = { radius: 145, slot: 72, dead_zone: 38, hub: 10, tap_ms: 250, timeout_s: 20, tag_limit: 12, animation: 'smooth', labels: 'name', slot_shape: 'circle', tag_colors: 'tint', flick: true, hover_submenus: true, hint: true,
  tag_band: 'medium', tag_band_opacity: 0.45, tag_glow_opacity: 0.4, tag_tint_opacity: 0.3, tag_tint_style: 'gradient', tag_tint_blend: 'multiply',
  colors: { bg: '#222327', accent: '#f86b33', highlight: '#4dc8e9', text: '#f0f0f0', lines: '#f86b33' } };
const FALLBACK_RANGES = { radius: [60, 400], slot: [32, 160], dead_zone: [10, 120], hub: [0, 40], tap_ms: [0, 1000], timeout_s: [2, 120], tag_limit: [4, 24],
  tag_band_opacity: [0, 1], tag_glow_opacity: [0, 1], tag_tint_opacity: [0, 1] };

const params = new URLSearchParams(location.search);
const POPOUT = window.__ZORBIT_MODE__ === 'popout';       // the browser popout (popout.html), not the Studio
const S = {
  cfg: null, savedStr: '', path: '', defaults: FALLBACK_DEFAULTS, opts: null,
  problems: [], problemsOpen: false, problemMenus: new Set(), problemItems: new Map(), problemTips: new Map(),
  scroll: Object.create(null), shown: false,
  screen: 'menus', menuId: null, itemIdx: null, tab: 'item',
  cameFrom: null,                              // { menuId, itemIdx }: where a submenu was opened from (drives the Back chip)
  suggestions: [],
  version: 0, hist: [], histI: 0,
  tags: [], tagMap: new Map(), itemTags: {}, favOrder: {}, tagMtime: null, tagsErr: '', tagsLoaded: false, tagsPath: '', palette: null,   // see "tags" below
  lib: { kind: 'brush', cat: 'All', q: '', size: 112 },
  dock: { kind: 'brush', cat: 'All', q: '' },
  pop: { kind: 'brush', cat: 'All', q: '', size: 96 }, popOnTop: true, popSide: 'left', popColumn: true,   // the popout's browser state, whether its window stays above others, and the side of its folders column
  status: null,
  prefs: { setup_done: true, mode: '', theme: 'dark', theme_effective: 'dark' },   // setup_done: boot tests === false, so a failed get_prefs never sends anyone to Setup
  ready: false, fatal: false,                 // ready after the first screen is up; fatal when the recovery screen is showing
  saving: false, savePromise: null, mtimeNs: null,
  dirtySent: undefined, dirtySeq: 0, dirtyFlight: null,
  profile: '', active: '', profiles: [], profilesOn: false,   // the profile Studio edits, the one the app uses, every name, and whether profiles exist at all (not when a menus file is pinned)
};
const R = {};               // region renderers registered by the visible screen
/* The screens in rail order: Alt+1 to Alt+6 follow it, and so do the rail titles (index.html carries the same words for the first paint). */
const SCREEN_ORDER = ['menus', 'look', 'library', 'settings', 'status', 'setup'];
const SCREEN_LABEL = { menus: 'Menus', look: 'Look', library: 'Library', settings: 'Settings', status: 'Status', setup: 'Setup' };
const railTitle = name => SCREEN_LABEL[name] + ' (Alt+' + (SCREEN_ORDER.indexOf(name) + 1) + ')';

/* Per-kind library state: S.libs[kind] (see emptyLib). lib(kind) never throws, ensureLib(kind) loads a kind the first time it is shown. */
S.libs = Object.fromEntries(LIB_KINDS.map(k => [k, emptyLib()]));
const lib = kind => (isLib(kind) ? S.libs[kind] : S.libs.brush);
const ensureLib = kind => { const L = lib(kind); if (!L.loaded && !L.busy) loadLibrary(kind); };

/* Per-kind usage (get_usage): the picks of the Recent folder, newest first, and the scores that order Favourites. recentSet holds nameKey()s,
   recentT maps a nameKey() to the time of its last pick. Not to be confused with usageMap(), which is where the menus use an item. */
const emptyUsage = () => ({ recent: [], recentSet: new Set(), recentT: new Map(), scores: Object.create(null), loaded: false, sig: '', mtime: null });
S.usage = Object.fromEntries(LIB_KINDS.map(k => [k, emptyUsage()]));
const usageOf = kind => (isLib(kind) ? S.usage[kind] : S.usage.brush);

const kindOf = it => ACTIONS.find(k => it && k in it) || 'brush';
const targetOf = it => { const k = kindOf(it); return k === 'steps' || k === 'empty' || k === 'recent' ? '' : String(it[k] ?? ''); };      // a Recent item's value is a choice, not a target
const isPath = s => /[\\/]/.test(s) || /\.(png|zbp|zmt|psd|jpg|jpeg|bmp|tif|tiff)$/i.test(s);
const ring = () => S.cfg.ring || {};
const ringNum = k => { const v = ring()[k]; return typeof v === 'number' ? v : S.defaults[k]; };
const ranges = () => (S.opts && S.opts.ring_ranges) || FALLBACK_RANGES;
/* What look.js needs to resolve a look (see its header): the schema of get_options, the ring defaults, the theme colours, the theme in force. */
/* The toast text for settings that using a look removed. */
const clearedText = n => (n === 1 ? 'Cleared your own setting' : 'Cleared ' + n + ' of your own settings');
const lookCtx = () => ({ looks: S.opts && S.opts.looks, defaults: S.defaults, colors: S.opts && S.opts.theme_ring_colors, animations: S.opts && S.opts.animations, theme: S.themeEff || 'dark' });
const menus = () => S.cfg.menus;
const curMenu = () => menuOf(S.menuId);
const curItem = () => { const m = curMenu(); return m && S.itemIdx !== null ? m.items[S.itemIdx] : undefined; };

/* ---- Simple and Full mode. The mode only changes what Studio shows; the ring, the app and radial.json never see it.
   An undecided mode, a failed get_prefs and the popout (which never reads prefs) all show everything. */
const isFull = () => S.prefs.mode !== 'simple';
const MODE = window.ZMode;      // mode.js: what Simple hides, shared with look-screen.js and the tests
const kindIsFull = MODE.kindIsFull;
const { FULL_CARDS, menuFullSet } = MODE;
const modeCtx = () => ({ defaults: S.defaults, kindOf, menuOf });
/* Names (deduplicated, in settings order) of Full-only settings that differ from the defaults. where: 'look' or 'settings' keeps the ones that screen shows. */
const fullOnlyChanges = (cfg, where) => MODE.fullOnlyChanges(cfg, where, modeCtx());
const needsFull = cfg => MODE.needsFull(cfg, modeCtx());
/* Would going to this problem target land on something Simple hides? */
const targetNeedsFull = t => MODE.targetNeedsFull(t, modeCtx());
/* A capture item's folder as the list shows it: the folder, or Pictures\ZBrush when it is empty (the default folder). */
const captureFolder = it => String(it.capture ?? '').trim() || 'Pictures\\ZBrush';
/* A tool, project or layout item's label when it has none, as _default_label in config.py: the file's name without a .zpr,
   .ztl or .cfg (any case), so a folder keeps its whole name. */
function fileLabel(k, path) {
  const name = String(path ?? '').trim().replace(/[\\/]+$/, '').split(/[\\/]/).pop();
  return name.replace(/(.+)\.(zpr|ztl|cfg)$/i, '$1');
}
/* One line saying what an item targets; the item rows and the read-only line in Simple share it. */
function itemSub(it) {
  const k = kindOf(it);
  return k === 'empty' ? 'nothing here' : k === 'auto' ? 'filled from your picks' : k === 'recent' ? (own(RECENT, it.recent) ? RECENT[it.recent].sub : '(not set)') : k === 'tag' ? (it.tag ? 'all items tagged ' + tagName(it.tag) : '(not set)') : k === 'browser' ? 'opens the ' + K(it.kind).one + ' browser' + (it.browser ? ' for ' + tagName(it.browser) : '') : k === 'steps' ? plural((it.steps || []).length, 'step') : k === 'capture' ? captureFolder(it) : (k === 'set' ? `${targetOf(it)} = ${it.value}` : targetOf(it) || '(not set)');
}

function defaultLabel(it) {
  const k = kindOf(it);
  if (isLib(k)) return String(it[k] || '');
  if (k === 'menu') { const m = menuOf(it.menu); return (m && m.title) || String(it.menu || ''); }
  if (k === 'steps') return 'Steps';
  if (k === 'auto') return 'Auto';
  if (k === 'recent') return own(RECENT, it.recent) ? RECENT[it.recent].label : 'Recent';
  if (k === 'empty') return 'Empty slot';
  if (k === 'tag') return tagName(it.tag);
  if (k === 'capture') return 'Capture';
  if (FILE_KINDS.includes(k)) return fileLabel(k, it[k]);
  if (k === 'browser') return it.browser && S.tagMap.has(it.browser) ? tagName(it.browser) : 'Browser';   // as _default_label in config.py
  return String(it[k] || '').split(':').pop();
}
/* A tag's label, or its key when the tag is not (or not yet) known. */
function tagName(key) { const t = S.tagMap.get(key); return (t && t.label) || String(key || ''); }
const itemLabel = it => String(it.label || defaultLabel(it) || '(empty)');
const FILE_LABEL = { tool: 'Tool file', project: 'Project file or folder', layout: 'Layout file' };     // the field labels of the file items

function actionValid(a, nested) {
  if (!a || typeof a !== 'object') return false;
  const kinds = ACTIONS.filter(k => k in a);
  if (kinds.length !== 1) return false;
  const k = kinds[0];
  if (k === 'set' && !(typeof a.value === 'number' && Number.isFinite(a.value))) return false;   // a number, as config.py demands
  if (k === 'steps') {
    if (nested || !Array.isArray(a.steps) || !a.steps.length) return false;
    return a.steps.every(s => actionValid(s, true) && !('menu' in s) && !('steps' in s) && !('auto' in s) && !('tag' in s) && !('browser' in s) && !('recent' in s) && !('empty' in s));   // steps cannot open menus, nest steps, be auto slots, open tags, the browser or recent files, or be an empty slot
  }
  if (k === 'auto') return a.auto === 'brush';
  if (k === 'recent') return own(RECENT, a.recent);
  if (k === 'empty') return a.empty === true;                                      // always usable: the slot only holds its place
  if (k === 'browser') return typeof a.browser === 'string' && (a.kind === undefined || isLib(a.kind));          // '' = every item; kind: which tab it opens on
  if (typeof a[k] !== 'string') return false;                                       // null or a number from a hand edit: unusable, never a crash
  if (k === 'capture') return true;                                                // a folder, and "" is the default folder: empty is usable
  if (isLib(k) && (/[\\/:]/.test(a[k]) || a[k].includes('..'))) return false;      // an asset is a plain name, never a path (config.py _bad_asset_name)
  return a[k].trim() !== '';
}
/* The menus the loader keeps (config.py load): an object whose id does not start with "tag:" and that has an item left, where
   a submenu item only counts while its target is kept too. A submenu whose own items all go takes the slots that open it
   with it, and so on down the chain, so this settles by dropping menus until none changes. */
function liveMenus() {
  const menus = S.cfg.menus;
  const live = new Set(Object.keys(menus).filter(id => menus[id] && typeof menus[id] === 'object' && !id.startsWith('tag:')));
  const ok = it => actionValid(it, false) && (!('menu' in it) || live.has(it.menu));
  for (let changed = true; changed;) {
    changed = false;
    for (const id of Array.from(live)) {
      const items = menus[id].items;
      if (!Array.isArray(items) || !items.some(ok)) { live.delete(id); changed = true; }
    }
  }
  return live;
}
/* A tag slot whose tag does not exist stays usable: the loader keeps it as an empty slot and the Problems panel warns. */
const itemUsable = it => actionValid(it, false) && (!('menu' in it) || liveMenus().has(it.menu));
/* The ring's slots, as indices into menu.items. Every item holds its place, since config.py load draws one it cannot use as an empty slot. A menu it drops has no ring. */
function slotIdx(menuId) {
  const m = menuOf(menuId);
  return m && Array.isArray(m.items) && liveMenus().has(menuId) ? m.items.map((_, i) => i) : [];
}

/* Builds an item with a tidy key order (action, value, label, icon). */
function makeItem(kind, target, extra = {}) {
  const it = {};
  if (kind === 'empty') return { empty: true };
  if (kind === 'steps') it.steps = extra.steps || [];
  else if (kind === 'auto') it.auto = 'brush';
  else if (kind === 'recent') it.recent = own(RECENT, target) ? target : 'any';
  else it[kind] = target || '';
  if (kind === 'browser' && isLib(extra.kind) && extra.kind !== 'brush') it.kind = extra.kind;
  if (kind === 'set') it.value = extra.value !== undefined ? extra.value : '';
  if (extra.label) it.label = extra.label;
  if (extra.icon) it.icon = extra.icon;
  return it;
}
/* A target lives in one of these namespaces: each library kind's names, ZBrush item paths (press, set, toggle), menu ids and tags.
   Switching kind keeps a target only inside its own namespace, so a brush name never lands in a path field. */
const nsOf = k => (isLib(k) ? k : k === 'menu' ? 'menu' : k === 'tag' || k === 'browser' ? 'tag' : k === 'capture' ? 'folder' : k === 'recent' ? 'recent' : FILE_KINDS.includes(k) ? k : 'path');
const TARGET_NOUN = { brush: 'brush', alpha: 'alpha', material: 'material', texture: 'texture', press: 'button path', set: 'value path', toggle: 'switch path', capture: 'folder', tool: 'tool file', project: 'project file or folder', layout: 'layout file', menu: 'submenu', tag: 'tag', browser: 'tag filter' };
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
const NO_STEP = ['menu', 'tag', 'browser', 'recent', 'empty'];
/* Returns { item, lost }: lost lists, in words, what the switch could not carry over (empty when nothing was lost). */
function convertItem(it, kind) {
  const old = kindOf(it);
  if (old === kind) return { item: it, lost: [] };
  if (old === 'empty') return { item: makeItem(kind, '', kind === 'steps' ? { steps: [makeItem('brush', '')] } : {}), lost: [] };      // nothing to carry over
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
/* Who else uses a hotkey: a menu id, BROWSER for browser.hotkey, PROFILE for profile.next_hotkey, or null. exceptId is the menu (or BROWSER, PROFILE) being edited. */
const BROWSER = ':browser';                     // not a valid menu id (':' is rejected), so it never collides with one
const PROFILE = ':profile';                     // the same, for profile.next_hotkey
function hotkeyOwner(str, exceptId) {
  const n = hkNorm(str);
  if (!n) return null;
  for (const [id, m] of Object.entries(S.cfg.menus)) if (id !== exceptId && hkNorm(m.hotkey) === n) return id;
  const b = S.cfg.browser;
  if (exceptId !== BROWSER && b && typeof b === 'object' && hkNorm(b.hotkey) === n) return BROWSER;
  const p = S.cfg.profile;
  if (exceptId !== PROFILE && p && typeof p === 'object' && hkNorm(p.next_hotkey) === n) return PROFILE;
  return null;
}
const ownerName = id => (id === BROWSER ? 'the browser' : id === PROFILE ? 'the next-profile hotkey' : '“' + (menuOf(id).title || id) + '”');
function hkChips(str, cls = '') {
  const w = h('span', { class: 'hk ' + cls });
  String(str).split(/\+(?=.)/).forEach(p => w.append(h('kbd', null, p)));
  return w;
}
// A title as an id: accents dropped ("Détails" -> "details"), anything but letters, digits, - and _ becomes _.
function menuSlug(s) {
  let id = String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9_-]+/g, '_').replace(/^_+|_+$/g, '') || 'menu';
  if (/^\d+$/.test(id)) id = 'm_' + id;
  return id;
}
// self: the menu being renamed, which may keep its own id
function uniqueId(base, self) {
  const id = menuSlug(base);
  let n = 2, out = id;
  while ((hasMenu(out) || RESERVED_IDS.has(out)) && out !== self) out = id + '_' + n++;
  return out;
}
// A menu that has never been saved, whose id is still the one made from its title, takes a new id when the title
// changes: nothing outside Studio (the ring, learned auto slots) knows the id yet. A saved menu, or an id typed by
// hand, stays as it is.
function idFollowsTitle(id, oldTitle) {
  let saved = {};
  try { saved = JSON.parse(S.savedStr).menus || {}; } catch (e) { /* nothing saved yet */ }
  if (own(saved, id)) return false;
  const s = menuSlug(oldTitle);
  return id === s || new RegExp('^' + s + '_\\d+$').test(id);
}
// The id the menu should have after its title went from oldTitle to its current one, or null to keep it.
function idForTitle(id, oldTitle) {
  const m = menuOf(id);
  if (!m || !idFollowsTitle(id, oldTitle)) return null;
  const nid = uniqueId(m.title, id);
  return nid !== id ? nid : null;
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
  if (S.popMode === 'strip') { call('popout_strip_note', String(msg)).catch(() => {}); return; }   // the browser's strip has no room: near the cursor
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
let activeTour = null;                                        // { end }: the guided tour, while it is open (see the tour section)
function modal({ title, body, actions }) {
  if (typeof openPopover === 'function') openPopover();      // a dialog always closes any open dropdown first
  if (activeTour) activeTour.end();                          // and the tour: its end() frees #app before this dialog makes it inert again
  if (activeModal) activeModal.close(undefined);             // a newer dialog replaces the open one (e.g. the window X over a Revert confirm)
  return new Promise(resolve => {
    const prev = document.activeElement;
    const me = { close: v => close(v) };
    let closed = false;
    const box = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
      h('h2', null, title), h('div', { class: 'modal-body' }, body),
      h('div', { class: 'modal-actions' }, actions.map(a => h('button', { class: 'btn ' + (a.kind || ''), type: 'button', dataset: { v: a.value }, 'data-focus': a.focus, onclick: async e => {
        if (a.check) { const b = e.currentTarget; b.disabled = true; let ok = false; try { ok = await a.check(); } finally { b.disabled = false; } if (!ok) return; }   // a check that answers false keeps the dialog open
        close(a.value);
      } }, a.text))));
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
/* Entries are { icon, label, hint, fn }; { checked: true|false } makes a radio row (a tick before the label), { sep: true } a divider. onClose runs when it closes, however it closes. */
function popover(anchor, entries, { onClose = null } = {}) {
  if (openPopover) { const same = openPopover.anchor === anchor; openPopover(); if (same) return; }   // a second click on the anchor closes it
  const row = en => en.sep ? h('div', { class: 'pop-sep', role: 'separator' }) : h('button', { class: 'pop-item', role: en.checked === undefined ? 'menuitem' : 'menuitemradio',
      'aria-checked': en.checked === undefined ? null : String(!!en.checked), type: 'button', onclick: () => { close(); en.fn(); } },
    en.checked === undefined ? null : h('span', { class: 'pop-tick' }, en.checked ? icon('check', 14) : null),
    en.icon ? icon(en.icon, 16) : null, h('span', { class: 'pop-text' }, h('b', null, en.label), en.hint ? h('small', null, en.hint) : null));
  const pop = h('div', { class: 'popover', role: 'menu' }, entries.map(row));
  document.body.append(pop);
  const r = anchor.getBoundingClientRect();
  pop.style.left = clamp(r.left, 8, Math.max(8, innerWidth - pop.offsetWidth - 8)) + 'px';
  // Below the anchor if it fits, else above, else on whichever side has more room; a list taller than that scrolls inside the popover.
  const roomBelow = innerHeight - r.bottom - 6 - 8, roomAbove = r.top - 6 - 8, natural = pop.offsetHeight;
  const below = natural <= roomBelow || (natural > roomAbove && roomBelow >= roomAbove);
  const hgt = Math.max(96, Math.min(natural, below ? roomBelow : roomAbove));
  pop.style.maxHeight = hgt + 'px';
  pop.style.top = Math.max(8, below ? r.bottom + 6 : r.top - 6 - Math.min(natural, hgt)) + 'px';
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
    if (onClose) onClose();
  }
  close.anchor = anchor;
  document.addEventListener('mousedown', onDown, true);
  document.addEventListener('keydown', onKey, true);
  openPopover = close;
  ($('.pop-item[aria-checked="true"]', pop) || $('.pop-item', pop)).focus();     // a radio list opens on the chosen row
}

/* ================================================================== thumbnails */
const THUMB_BATCH = { brush: 40, other: 8 };   // names per get_thumbs call: the backend decodes a batch on a pool and returns it together, so a small batch lands sooner
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
  /* 0: a card on show in its scroller, 1: within the pre-load margin, 2: further away (or hidden). A picture asked for without a card (el null) counts as on show. */
  rank(k) {
    let best = 2;
    for (const w of this.waiting.get(k) || []) {
      const el = w.el;
      if (!el) return 0;
      if (!el.isConnected) continue;
      const r = el.getBoundingClientRect();
      if (!r.width && !r.height) continue;
      const root = el._io && el._io.root, rr = root ? root.getBoundingClientRect() : { top: 0, bottom: innerHeight };
      if (r.bottom > rr.top && r.top < rr.bottom) return 0;
      if (r.bottom > rr.top - 320 && r.top < rr.bottom + 320) best = 1;
    }
    return best;
  },
  forgetMisses(kind) { for (const [k, v] of Array.from(this.cache)) if (!v && (!kind || k.startsWith(kind + '|'))) this.cache.delete(k); },
  async flush() {
    this.timer = null;
    if (this.busy) { this.timer = setTimeout(() => this.flush(), 10); return; }   // one call in flight at a time: the slider cannot stack them
    const batch = [];
    let res = 0, kind = '';
    let ents = Array.from(this.queue);
    if (ents.length > THUMB_BATCH.other) {                        // more waiting than one call takes: the cards on show go first, then the ones near, then the rest (a stable sort keeps the order inside each)
      const rank = new Map(ents.map(([k]) => [k, this.rank(k)]));
      ents = ents.sort((a, b) => rank.get(a[0]) - rank.get(b[0]));
    }
    for (const [k, q] of ents) {                                  // up to 40 brushes or 8 others of one size and kind per call: the first cards of a big library fill in sooner
      if (batch.length && batch.length >= (THUMB_BATCH[kind] || THUMB_BATCH.other)) break;
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
    if (url) { el.classList.remove('fallback'); el.replaceChildren(h('img', { src: url, alt: '', draggable: 'false' })); el._got = el._res; }   // _got: the size of the picture on show
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
/* After the misses of a kind were forgotten (a rescan): the cards on show that fell back to initials ask for their picture again. */
function retryMissedThumbs(kind) {
  for (const t of document.querySelectorAll('.thumb.fallback')) if (t._io && t._load && t._kind === kind) { t._io.unobserve(t); t._io.observe(t); }
}
function itemThumb(it, size = 30) {
  const k = kindOf(it);
  let name = null, kind = 'brush';                                 // an icon override is always a brush name
  if (it.icon && !isPath(it.icon)) name = it.icon;
  else if (!it.icon && isLib(k)) { name = it[k]; kind = k; }
  else if (!it.icon && k === 'steps') for (const s of Array.isArray(it.steps) ? it.steps : []) { const sk = s && LIB_KINDS.find(x => typeof s[x] === 'string' && s[x]); if (sk) { name = s[sk]; kind = sk; break; } }
  if (name) return thumb(name, { size, kind });
  const g = h('span', { class: 'thumb glyph k-' + k, style: { '--sz': size + 'px' } }, icon(KIND[k].icon, Math.round(size * 0.52)));
  return g;
}

/* ================================================================== ring preview + animation loaders */
const SAMPLE_MENU = 'sample:tags';             // not a menu: the backend's sample ring of library brushes in the user's tag colours
const RingLoader = {
  cache: new Map(), ver: -1, gen: 0, queue: {}, cur: null, busy: false,   // gen: bumped by tag edits, which S.version does not see; queue: lane -> waiting request
  key: (m, hv, path, variant) => m + '|' + (hv === null || hv === undefined ? 'n' : hv) + '|' + (path && path.length ? path.join('.') : '') + (variant ? '|v:' + variant.key : ''),
  sync() { if (this.ver !== S.version) { this.cache.clear(); this.ver = S.version; } },
  peek(menuId, hover, path, variant) { this.sync(); return this.cache.get(this.key(menuId, hover, path, variant)) || null; },
  /* path: item indices of the fan submenus to show open (null: none). variant: { key, cfg() } draws from a config of its own (a copy with
     another look on one menu) instead of S.cfg; key tells its pictures apart, and the menu it changes is the one to preview. */
  get(menuId, hover, path, lane = 'main', variant = null) {
    this.sync();
    const k = this.key(menuId, hover, path, variant), c = this.cache.get(k);
    if (c) return Promise.resolve(c);
    return new Promise(res => {
      // the same picture asked for twice (several previews on one screen) shares one backend call
      const same = [this.cur, ...Object.values(this.queue)].find(q => q && q.k === k && q.ver === S.version && q.gen === this.gen);
      if (same) { same.waiters.push(res); return; }
      if (this.queue[lane]) this.settle(this.queue[lane], null);   // latest request wins within a lane; other lanes keep theirs
      this.queue[lane] = { menuId, hover: hover === undefined ? null : hover, path: path && path.length ? path : null, variant, k, ver: S.version, gen: this.gen, res, waiters: [] };
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
      const cfg = q.variant ? q.variant.cfg() : S.cfg;
      out = q.menuId === SAMPLE_MENU ? await call('preview_tags', cfg, q.hover, 1.0, q.variant ? q.variant.menu : null) : await call('preview_ring', cfg, q.menuId, q.hover, 1.0, q.path);
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
      set('idle'); toast((res && res.problems && res.problems[0]) || 'Could not render the animation.', { tone: 'warn' }); restore(); return;
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
    // last: the latest pointer position, so pressing or releasing Ctrl (copy instead of move) updates the cue without a mouse move
    this.active = { payload, ghost, zone: null, last: null, onKey: e => {
      if (e.key === 'Escape') this.end(null, false);
      else if (e.key === 'Control' && !e.repeat && this.active && this.active.last) this.move({ clientX: this.active.last.x, clientY: this.active.last.y, ctrlKey: e.type === 'keydown' });
    } };
    document.addEventListener('keydown', this.active.onKey, true);
    document.addEventListener('keyup', this.active.onKey, true);
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
    a.last = { x: ev.clientX, y: ev.clientY };
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
    document.removeEventListener('keyup', a.onKey, true);
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
const NAMED_KEYS = { Space: 'Space', Tab: 'Tab', Enter: 'Enter', NumpadEnter: 'Enter', Backspace: 'Backspace', Insert: 'Insert', Delete: 'Delete',
  Home: 'Home', End: 'End', PageUp: 'PageUp', PageDown: 'PageDown' };          // the names config.py reads (_NAMED_VK, case-insensitive)
const CODE_KEYS = { Backquote: '`', Minus: '-', Equal: '=', BracketLeft: '[', BracketRight: ']', Backslash: '\\',
  Semicolon: ';', Quote: "'", Comma: ',', Period: '.', Slash: '/' };
/* What the same keys type with Shift held, on the layout CODE_KEYS describes (a US one). */
const CODE_KEYS_SHIFT = { Backquote: '~', Minus: '_', Equal: '+', BracketLeft: '{', BracketRight: '}', Backslash: '|',
  Semicolon: ':', Quote: '"', Comma: '<', Period: '>', Slash: '?' };
/* Dead keys: on US-International the ' and ` keys are dead keys, so a keydown has key "Dead" while its code (Quote, Backquote) is the
   place the app means (the same virtual key as a US keyboard). Other layouts also have a dead key at one of those places (a German
   ^ is on Backquote but is another virtual key), so when the browser can say what the layout types there (getLayoutMap), that decides. */
const DEAD_KEY_CODES = ['Quote', 'Backquote'];
let layoutMap = null;
try {
  const kb = navigator.keyboard;
  if (kb && kb.getLayoutMap) {
    const load = () => kb.getLayoutMap().then(m => { layoutMap = m; }, () => {});
    load();
    if (kb.addEventListener) kb.addEventListener('layoutchange', load);
  }
} catch (e) { layoutMap = null; }
function deadKeyIsUs(c) {
  if (!DEAD_KEY_CODES.includes(c)) return false;
  let typed = null;
  try { typed = layoutMap ? layoutMap.get(c) : null; } catch (e) { typed = null; }
  return typed == null || typed === CODE_KEYS[c];       // unknown: take the dead key at this place as the US one
}
/* The key of a keydown as config.py names it: { key } or { error } (a sentence for the user). The app matches the virtual key the
   user's layout gives a letter or digit, so those are read from what was typed (letters) or the physical digit row. A punctuation
   key is named by its place on a US keyboard, which only means the same key on a layout that types that character there. */
function keyFromEvent(e) {
  const c = e.code || '';
  if (/^Numpad/.test(c) && c !== 'NumpadEnter') return { error: 'Numpad keys cannot be recorded. Use the main row.' };   // the app has no numpad key names, and a numpad digit would record as the main row's
  if (/^[a-z]$/i.test(e.key)) return { key: e.key.toUpperCase() };     // the typed character, so Dvorak/AZERTY record what the user pressed
  if (/^Digit[0-9]$/.test(c)) return { key: c[5] };                    // by position, so AZERTY's & is 1
  if (/^[0-9]$/.test(e.key)) return { key: e.key };
  if (/^Key[A-Z]$/.test(c)) return { key: c[3] };                      // other layouts (Cyrillic, Greek...) and dead keys: fall back to the physical key
  if (/^F([1-9]|1\d|2[0-4])$/.test(c)) return { key: c };
  if (NAMED_KEYS[c]) return { key: NAMED_KEYS[c] };
  if (CODE_KEYS[c]) {
    if (e.key === CODE_KEYS[c] || e.key === CODE_KEYS_SHIFT[c]) return { key: CODE_KEYS[c] };
    if (e.key === 'Dead' && deadKeyIsUs(c)) return { key: CODE_KEYS[c] };         // US-International: ' and ` wait for the next letter
    return { error: 'This key is in a different place on your keyboard layout. Pick another.' };
  }
  return { key: null };
}
/* refuse(key): a sentence when this field must not take that key (after the modifier checks), else ''. */
function hotkeyField({ value, mods = { ctrl: true, alt: true, shift: true }, onChange, placeholder = 'Not set', noMessage, what = 'Hotkey', refuse = null, altMessage = 'Alt is not allowed here.' }) {
  let rec = false;
  const field = h('div', { class: 'hk-field', role: 'button', tabindex: '0', title: 'Press Enter to record a new one', dataset: { fk: 'hk:' + what } });
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
    const got = keyFromEvent(e), key = got.key;
    if (got.error) { say(got.error); return; }
    if (!key) { say('That key is not supported. Use a letter, digit, F1-F24, space, tab, enter, backspace, insert, delete, home, end, pageup, pagedown or one of ` - = [ ] \\ ; \' , . /'); return; }
    for (const m of ['ctrl', 'alt', 'shift']) {
      if (e[m + 'Key'] && !mods[m]) {
        say(m === 'alt' ? altMessage : (m === 'ctrl' ? 'Ctrl' : 'Shift') + ' cannot be used here: ZBrush reads it as ' + (m === 'ctrl' ? 'mask' : 'smooth') + '. Use a bare F-key.');
        return;
      }
    }
    const no = refuse ? refuse(key) : '';
    if (no) { say(no); return; }
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
  field.onkeydown = e => { if (!rec && !e.repeat && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); start(); } };
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
/* now: ask for the ring picture at once instead of after previewSoon's pause, for a single click (+, -, a swap) rather than typing.
   Quick clicks still cost at most one picture in flight and one waiting, since the loader keeps only the latest request. */
function commit({ inspector = false, now = false } = {}) { touch(); refreshRegions(inspector); if (now && R.preview) { previewSoon.cancel(); R.preview(); } }
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
/* What the Settings screen draws from the config: when this is the same before and after an undo, Settings is left alone (and keeps focus). */
const settingsSig = () => JSON.stringify([S.cfg.ring, S.cfg.bridge, S.cfg.browser, S.cfg.profile, S.menuId]);
function applySnap(e) {
  const sigBefore = R.settings ? settingsSig() : '', lookBefore = R.look ? lookSig() : '';
  S.cfg = JSON.parse(e.cfg);
  const ids = Object.keys(S.cfg.menus);
  S.menuId = hasMenu(e.menuId) ? e.menuId : (hasMenu(S.menuId) ? S.menuId : (ids[0] || null));
  const m = curMenu();
  S.itemIdx = m && S.menuId === e.menuId && Number.isInteger(e.itemIdx) && e.itemIdx >= 0 && e.itemIdx < (m.items || []).length ? e.itemIdx : null;
  if (S.itemIdx === null && S.tab === 'item') S.tab = 'menu';           // no item to show; any other tab stays where it was
  S.version++; updateDirty(); validateSoon(); previewSoon(); updateHistButtons();
  renderAllMenus(); if (R.settings && settingsSig() !== sigBefore) R.settings(); if (R.look && lookSig() !== lookBefore) R.look();
  const row = $('.irow.sel'); if (row) row.scrollIntoView({ block: 'nearest' });
}
function undo() { snapSoon.cancel(); pushSnap(); if (S.histI > 0) { S.histI--; applySnap(S.hist[S.histI]); toast('Undone', { ms: 1400 }); } }
function redo() { snapSoon.cancel(); pushSnap(); if (S.histI < S.hist.length - 1) { S.histI++; applySnap(S.hist[S.histI]); toast('Redone', { ms: 1400 }); } }

/* ---------- menu operations */
/* from: where this menu was opened from (a submenu item or an Open button), which the Back chip returns to. Any other way of
   picking a menu leaves the trail. */
function selectMenu(id, { keepItem = false, from = null } = {}) {
  if (!hasMenu(id)) return;
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
  if (!hasMenu(targetId) || targetId === S.menuId) return;
  selectMenu(targetId, { from: { menuId: S.menuId, itemIdx: Number.isInteger(itemIdx) ? itemIdx : null } });
}
function goBack() {
  const c = S.cameFrom;
  if (!c || !hasMenu(c.menuId)) { S.cameFrom = null; if (R.itemList) R.itemList(); return; }
  selectMenu(c.menuId);
  const m = curMenu();
  if (c.itemIdx !== null && m && m.items[c.itemIdx]) selectItem(c.itemIdx);
}
function selectItem(i, { focusTarget = false, keepTab = false } = {}) {
  S.itemIdx = i;
  if (i !== null) S.tab = 'item';
  else if (S.tab === 'item' && !keepTab) S.tab = 'menu';
  rememberSel();
  if (R.itemList) R.itemList();
  if (R.overlay) R.overlay();
  if (R.right) R.right();
  const row = $('.irow.sel'); if (row) row.scrollIntoView({ block: 'nearest' });
  if (focusTarget) { const t = $('[data-focus="target"]'); if (t) t.focus(); }
}
function addMenu() {
  const id = uniqueId('New menu');
  S.cfg.menus[id] = { title: 'New menu', keep_slots: true, items: Array.from({ length: 8 }, ZSlots.blank) };     // eight outlines to fill, in places that stay put
  S.menuId = id; S.itemIdx = null; S.tab = 'menu';
  commit({ inspector: true }); if (R.head) R.head();
  if (R.preview) R.preview();
  if (R.renameMenu) R.renameMenu(id);
  return id;
}
function dupMenu(id) {
  const src = menuOf(id); if (!src) return;
  const nid = uniqueId(id + '_copy');
  const copy = clone(src); copy.title = (src.title || id) + ' copy'; delete copy.hotkey;
  S.cfg.menus = Object.fromEntries(Object.entries(S.cfg.menus).flatMap(([k, v]) => (k === id ? [[k, v], [nid, copy]] : [[k, v]]))); S.menuId = nid; S.itemIdx = null;
  commit({ inspector: true }); if (R.head) R.head(); if (R.preview) R.preview();
  toast('Duplicated. The copy has no hotkey, so it works as a submenu.', { ms: 3600 });
}
async function deleteMenu(id) {
  const m = menuOf(id); if (!m) return;
  const refs = referrers(id).filter(r => r.menuId !== id);
  const body = [h('p', null, `Delete the menu "${m.title || id}" and its ${m.items.length} item${m.items.length === 1 ? '' : 's'}?`)];
  if (refs.length) {
    body.push(h('p', { class: 'warn-text' }, `It is opened as a submenu from ${refs.length} item${refs.length === 1 ? '' : 's'}. Those items will be removed too:`));
    body.push(h('ul', { class: 'ref-list' }, refs.map(r => h('li', null, h('b', null, menuOf(r.menuId).title || r.menuId), ' / item ' + (r.index + 1) + ' ', h('span', { class: 'mono' }, '"' + itemLabel(r.item) + '"')))));
  }
  const ok = await modal({ title: 'Delete menu', body, actions: [{ text: 'Cancel', value: false, focus: true }, { text: refs.length ? 'Delete menu and links' : 'Delete menu', kind: 'danger', value: true }] });
  if (!ok) return;
  if (!hasMenu(id)) return;
  const fresh = referrers(id).filter(r => r.menuId !== id);     // the config may have changed while the dialog was open
  sealSnap();
  delete menuMore[id];
  if (S.itemIdx !== null && S.menuId !== id) {
    const here = keeps(menuOf(S.menuId)) ? [] : fresh.filter(r => r.menuId === S.menuId).map(r => r.index);       // a menu that keeps its slots only empties them
    S.itemIdx = here.includes(S.itemIdx) ? null : S.itemIdx - here.filter(x => x < S.itemIdx).length;
  }
  fresh.sort((a, b) => b.index - a.index).forEach(r => { const mm = menuOf(r.menuId); if (mm) { if (keeps(mm)) ZSlots.clear(mm.items, r.index); else mm.items.splice(r.index, 1); } });
  const ids = Object.keys(S.cfg.menus), pos = ids.indexOf(id);
  delete S.cfg.menus[id];
  if (S.menuId === id) { const rest = Object.keys(S.cfg.menus); S.menuId = rest[Math.min(pos, rest.length - 1)] || null; S.itemIdx = null; }
  if (S.itemIdx !== null && curMenu() && S.itemIdx >= curMenu().items.length) S.itemIdx = null;
  commit({ inspector: true }); if (R.head) R.head(); if (R.preview) R.preview();
  const fa = document.activeElement;
  if (R.focusMenu && (!fa || fa === document.body || !fa.isConnected)) R.focusMenu();      // the Delete button (the Menu tab's, or the row's) went with the menu: the next row takes the keyboard
  undoToast(`Deleted "${m.title || id}"`);
}
/* What is wrong with newId as the id of menu oldId, in words, or null when it is fine (or unchanged). */
function menuIdProblem(oldId, newId) {
  newId = newId.trim();
  if (newId === oldId) return null;
  if (!newId) return 'The id cannot be empty.';
  if (/^tag:/.test(newId)) return 'Ids starting with "tag:" are reserved for tag submenus.';
  if (RESERVED_IDS.has(newId)) return 'That id is reserved. Pick another.';
  if (!/^[A-Za-z0-9_-]+$/.test(newId)) return 'Use letters, digits, - and _ only.';
  if (/^\d+$/.test(newId)) return 'The id cannot be only digits.';
  if (hasMenu(newId)) return 'Another menu already uses that id.';
  return null;
}
// Moves a menu to a new id in place (same position in the file) and points every item that opened it at the new id.
function moveMenuId(oldId, newId) {
  const out = Object.fromEntries(Object.entries(S.cfg.menus).map(([k, v]) => [k === oldId ? newId : k, v]));
  S.cfg.menus = out;
  for (const m of Object.values(out)) (m.items || []).forEach(it => { if (it && it.menu === oldId) it.menu = newId; });
  if (S.menuId === oldId) S.menuId = newId;
  if (own(menuMore, oldId)) { menuMore[newId] = menuMore[oldId]; delete menuMore[oldId]; }
}
function renameMenuId(oldId, newId) {
  newId = newId.trim();
  if (newId === oldId) return null;
  const bad = menuIdProblem(oldId, newId);
  if (bad) return bad;
  moveMenuId(oldId, newId);
  commit({ inspector: true }); if (R.head) R.head();
  return null;
}
function moveMenu(id, beforeId) {
  if (id === beforeId) return;
  const ids = Object.keys(S.cfg.menus).filter(k => k !== id);
  const at = beforeId ? ids.indexOf(beforeId) : ids.length;
  ids.splice(at < 0 ? ids.length : at, 0, id);
  S.cfg.menus = Object.fromEntries(ids.map(k => [k, S.cfg.menus[k]])); commit();
}

/* ---------- item operations */
/* A menu that keeps its slots in place (keep_slots): adding puts an item in the first empty slot, deleting empties its slot and a drag swaps two slots,
   so no other item moves (slots.js). Without the switch an item is inserted and removed with the ones after it shifting, as ever. */
const keeps = m => !!m && m.keep_slots === true;
/* The Keep slots in place switch. Off, the menu closes up like any other, so its empty slots go; on, nothing moves. Either way it is one undo step. */
function setKeepSlots(menuId, on) {
  const m = menuOf(menuId); if (!m || keeps(m) === on) return;
  const title = m.title || menuId, sel = menuId === S.menuId ? curItem() : null;
  sealSnap();
  let gone = 0;
  if (on) m.keep_slots = true;
  else {
    delete m.keep_slots;
    const kept = m.items.filter(it => !ZSlots.isEmpty(it));
    gone = m.items.length - kept.length; m.items = kept;
    if (menuId === S.menuId) { const j = sel ? kept.indexOf(sel) : -1; S.itemIdx = j >= 0 ? j : null; if (S.itemIdx === null && S.tab === 'item') S.tab = 'menu'; }
  }
  commit({ inspector: true, now: gone > 0 }); if (R.head) R.head();
  undoToast(on ? `Slots in "${title}" now stay in place` : `Slots in "${title}" no longer stay in place` + (gone ? `. Removed ${plural(gone, 'empty slot')}.` : ''), { ms: 3800 });
}
/* Where the selection goes after the item at i left the list. */
function dropSel(m, menuId, i) {
  if (menuId !== S.menuId) return;
  if (S.itemIdx === i) S.itemIdx = m.items.length ? Math.min(i, m.items.length - 1) : null;
  else if (S.itemIdx !== null && S.itemIdx > i) S.itemIdx--;
}
function addItem(kind, at = null) {
  const m = curMenu(); if (!m) return;
  const it = makeItem(kind, '');
  if (kind === 'steps') it.steps = [makeItem('brush', '')];
  let i;
  if (keeps(m) && at === null) i = kind === 'empty' ? ZSlots.addSlot(m.items) : ZSlots.place(m.items, it);      // an empty slot is a new slot, not one to fill
  else { i = at === null ? m.items.length : at; m.items.splice(i, 0, it); }
  S.itemIdx = i; S.tab = 'item';
  commit({ inspector: true }); if (R.head) R.head();
  const row = $('.irow.sel'); if (row) row.scrollIntoView({ block: 'nearest' });
  const t = $('[data-focus="target"]'); if (t) t.focus();
}
function insertAsset(menuId, kind, name, at = null, silent = false) {
  const m = menuOf(menuId); if (!m || !isLib(kind)) return;
  const sel = menuId === S.menuId ? curItem() : null;
  if (!silent) sealSnap();
  let i;
  if (keeps(m) && at === null) i = ZSlots.place(m.items, { [kind]: name });                     // the first empty slot, else a new one at the end
  else { i = at === null || at > m.items.length ? m.items.length : at; m.items.splice(i, 0, { [kind]: name }); }
  if (sel) { const j = m.items.indexOf(sel); S.itemIdx = j >= 0 ? j : i; }                        // the empty slot that was selected is now this item
  commit({ inspector: true }); if (R.head) R.head();
  flashRow(menuId, i);
  if (!silent) undoToast(`Added ${name} to "${m.title || menuId}"`);
}
/* An asset dropped on slot i of a menu that keeps its slots: it fills an empty slot or replaces what was there (one undo step). */
function putAsset(menuId, i, kind, name) {
  const m = menuOf(menuId); if (!m || !m.items[i] || !isLib(kind)) return;
  const was = m.items[i], title = m.title || menuId;
  sealSnap();
  m.items[i] = { [kind]: name };
  commit({ inspector: true }); if (R.head) R.head();
  flashRow(menuId, i);
  undoToast(ZSlots.isEmpty(was) ? `Put ${name} in slot ${i + 1} of "${title}"` : `Replaced "${itemLabel(was)}" with ${name}`);
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
  if (keeps(m)) S.itemIdx = ZSlots.place(m.items, clone(m.items[i]));
  else { m.items.splice(i + 1, 0, clone(m.items[i])); S.itemIdx = i + 1; }
  S.tab = 'item';
  commit({ inspector: true }); if (R.head) R.head();
}
function delItem(i, menuId = S.menuId) {
  const m = menuOf(menuId); if (!m || !m.items[i]) return;
  sealSnap();
  if (keeps(m) && !ZSlots.isEmpty(m.items[i])) {                  // the slot stays, empty, and the selection with it
    const was = ZSlots.clear(m.items, i);
    commit({ inspector: true }); if (R.head) R.head();
    undoToast(`Cleared "${itemLabel(was)}"`, { ms: 3800 });
    return;
  }
  const removed = m.items.splice(i, 1)[0];                        // an empty slot of a keeping menu goes for good: the way to drop a slot
  dropSel(m, menuId, i);
  commit({ inspector: true }); if (R.head) R.head();
  undoToast(ZSlots.isEmpty(removed) ? 'Removed the empty slot' : `Removed "${itemLabel(removed)}"`, { ms: 3800 });
}
function moveItem(menuId, from, to) {
  const m = menuOf(menuId); if (!m) return;
  if (keeps(m)) { swapSlots(menuId, from, to > from ? to - 1 : to); return; }       // `to` counts gaps; a keeping menu swaps instead, so no neighbour moves
  const sel = menuId === S.menuId ? curItem() : null;
  const [it] = m.items.splice(from, 1);
  const t = to > from ? to - 1 : to;
  m.items.splice(clamp(t, 0, m.items.length), 0, it);
  if (sel) S.itemIdx = m.items.indexOf(sel);
  commit({ inspector: true });
}
/* Swaps slots a and b of a menu that keeps its slots (either may be empty, which makes it a move). The picture glides the pictures of the two
   across the ring first (R.glide, before the config changes), and both rows flash. */
function swapSlots(menuId, a, b) {
  const m = menuOf(menuId); if (!m || a === b || !m.items[a] || !m.items[b]) return;
  const sel = menuId === S.menuId ? curItem() : null;
  if (menuId === S.menuId && R.glide) R.glide([...(ZSlots.isEmpty(m.items[a]) ? [] : [[a, b]]), ...(ZSlots.isEmpty(m.items[b]) ? [] : [[b, a]])]);
  if (!ZSlots.swap(m.items, a, b)) return;
  if (sel) S.itemIdx = m.items.indexOf(sel);
  commit({ inspector: true, now: menuId === S.menuId });
  flashRow(menuId, a); flashRow(menuId, b);
}
/* Moves item `index` of menu fromId to the end of menu toId (the first empty slot when that menu keeps its slots), or copies it there (a deep copy) when `copy` is set. */
function transferItem(fromId, index, toId, copy) {
  const src = menuOf(fromId), dst = menuOf(toId);
  if (!src || !dst || fromId === toId || !src.items[index]) return;
  const it = src.items[index];
  if (it.menu === toId) { toast('A menu cannot open itself, so that item stays where it is.', { tone: 'warn' }); return; }
  sealSnap();
  const label = itemLabel(it), dstName = dst.title || toId;
  const put = x => (keeps(dst) ? ZSlots.place(dst.items, x) : dst.items.push(x) - 1);
  let at;
  if (copy) at = put(clone(it));
  else {
    if (keeps(src)) ZSlots.clear(src.items, index); else src.items.splice(index, 1);
    at = put(it);
    if (S.menuId === fromId) { if (!keeps(src)) dropSel(src, fromId, index); }                  // stay on this menu: the selection moves on like after a delete (a keeping menu leaves it on the emptied slot)
    else if (S.menuId === toId) S.itemIdx = at;
  }
  commit({ inspector: true }); if (R.head) R.head();
  if (!copy && R.preview) R.preview();
  flashRow(toId, at);                                           // the new row, if its list is on screen
  const mrow = $(`.mrow[data-id="${CSS.escape(toId)}"]`);      // and the menu it went to
  if (mrow) { mrow.classList.remove('flash'); void mrow.offsetWidth; mrow.classList.add('flash'); setTimeout(() => mrow.classList.remove('flash'), 1400); }
  undoToast(`${copy ? 'Copied' : 'Moved'} "${label}" to "${dstName}"`);
}
/* "Move to menu...": a popover with the other menus, so an item can change menus without dragging. `then` runs after the move (the caller puts the focus back). */
function moveToMenuPopover(anchor, menuId, index, then) {
  const others = Object.keys(S.cfg.menus).filter(id => id !== menuId);
  if (!others.length || !menuOf(menuId) || !menuOf(menuId).items[index]) return;
  popover(anchor, others.map(id => { const mm = menuOf(id); return { icon: 'k_menu', label: mm.title || id, hint: plural((mm.items || []).length, 'item'), fn: () => { transferItem(menuId, index, id, false); if (then) then(); } }; }));
}
function dropOnMenu(menuId, payload, at) {
  if (payload.type === 'asset') insertAsset(menuId, payload.kind, payload.name, at);
  else if (payload.type === 'item' && payload.menuId === menuId) moveItem(menuId, payload.index, at === null ? menuOf(menuId).items.length : at);
}
/* The same for a menu that keeps its slots; `row` is the slot dropped on (null: none, an asset then goes to the first empty slot). */
function dropOnSlot(menuId, payload, row) {
  if (!menuOf(menuId)) return;
  if (payload.type === 'item') { if (payload.menuId === menuId && row !== null) swapSlots(menuId, payload.index, row); }
  else if (row === null) insertAsset(menuId, payload.kind, payload.name, null);
  else putAsset(menuId, row, payload.kind, payload.name);
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
function parseValue(s) {
  const t = s.trim();
  if (!/^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$/.test(t)) return s;     // 5, -5, 0.5, .5, 5. and 1e-3
  const n = Number(t);
  return Number.isFinite(n) ? n : s;                                         // 1e999 is not a number JSON can hold
}
const validValue = v => typeof v === 'number' && Number.isFinite(v);
const VALUE_HINT = 'Use a number, e.g. 32';
/* A text link that is a button; it does not take focus from a field on mouse down, so the field does not blur first. */
const linkBtn = (text, fn) => h('button', { class: 'link', type: 'button', onmousedown: e => e.preventDefault(), onclick: fn }, text);
function sectionTitle(t, sub) { return h('div', { class: 'sect' }, h('span', null, t), sub ? h('em', null, sub) : null); }

/* ================================================================== MENUS screen */
function buildMenusScreen(root) {
  root.replaceChildren();
  const listEl = h('div', { class: 'mlist', role: 'listbox', 'aria-label': 'Menus', title: 'Up and Down move through the menus. Alt+Up/Down moves the selected menu.' });
  const left = h('aside', { class: 'col menus-col' },
    h('div', { class: 'col-head' }, h('span', { class: 'micro' }, 'Menus'), h('span', { class: 'count' }, '', ), iconBtn('plus', 'Add menu', () => addMenu(), 'accent')),
    listEl,
    h('button', { class: 'dashed', type: 'button', onclick: () => addMenu() }, icon('plus', 14), 'Add menu'),
    h('button', { class: 'btn small import-menu', type: 'button', title: 'Add a menu someone shared with you, from a menu file', onclick: e => ioRun([e.currentTarget], importMenu) }, icon('folder', 12), 'Import menu...'));
  const head = h('div', { class: 'center-head' });
  const stageBox = buildStage();
  const itemsEl = h('div', { class: 'ilist', role: 'listbox', 'aria-label': 'Items in this menu', title: 'Up and Down move through the items. Alt+Up/Down moves the selected item. M moves it to another menu.' });
  const itemsHead = h('div', { class: 'col-head slim' });
  const itemsNote = h('div', { class: 'items-note', hidden: true });
  const itemsPanel = h('div', { class: 'items-panel' }, itemsHead, itemsNote, itemsEl);
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
  const refreshMenuSel = () => {
    const rows = menuRows();
    rows.forEach(x => { const on = x.dataset.id === S.menuId; x.classList.toggle('sel', on); x.setAttribute('aria-selected', on ? 'true' : 'false'); });
    setRoving(rows, menuRowOf(S.menuId));
  };
  R.menuList = () => {
    const ids = Object.keys(S.cfg.menus);
    setText($('.count', left), String(ids.length));
    const sig = JSON.stringify(ids.map(id => { const m = menuOf(id); return [id, m.title || '', m.hotkey || '', (m.items || []).length]; }));
    if (sig === listEl._sig) { refreshMenuSel(); listEl._sel = S.menuId; return; }
    listEl._sig = sig;
    const act = document.activeElement, fr = act && listEl.contains(act) ? act.closest('.mrow') : null;
    const had = !!act && listEl.contains(act), fid = fr ? fr.dataset.id : null, fidx = fr ? menuRows().indexOf(fr) : -1, prevSel = listEl._sel;
    listEl.replaceChildren();
    if (!ids.length) { listEl.append(emptyState('menus', 'No menus yet', 'Create a menu to get started. Give it a hotkey to open it from ZBrush.', { text: 'Add menu', fn: addMenu })); return; }
    ids.forEach(id => {
      const m = menuOf(id);
      const n = (m.items || []).length;
      // the full title, hotkey and item count, for when the row is too narrow to show them
      const row = h('div', { class: 'mrow' + (id === S.menuId ? ' sel' : '') + (m.hotkey ? '' : ' subonly'), role: 'option', 'aria-selected': id === S.menuId ? 'true' : 'false', tabindex: '-1', dataset: { id },
        title: [m.title || id, m.hotkey ? 'Hotkey: ' + m.hotkey : 'Submenu: no hotkey', plural(n, 'item')].join('\n') });
      const title = h('div', { class: 'mrow-title' }, m.title || id);
      row.append(
        h('div', { class: 'mrow-main' }, title, h('div', { class: 'mrow-meta' }, h('span', { class: 'mono' }, id))),
        h('div', { class: 'mrow-side' },
          menuWarn(id),
          m.hotkey ? hkChips(m.hotkey, 'sm') : h('span', { class: 'sub-ico', role: 'img', 'aria-label': 'Submenu', title: 'Submenu: no hotkey, so it can only be opened from another menu' }, icon('k_menu', 14)),
          h('span', { class: 'pill-n', title: plural(n, 'item') }, String(n))),
        h('div', { class: 'mrow-actions' },
          noTab(iconBtn('edit', 'Rename (F2)', e => { e.stopPropagation(); R.renameMenu(id); })),
          noTab(iconBtn('copy', 'Duplicate', e => { e.stopPropagation(); dupMenu(id); })),
          noTab(iconBtn('trash', 'Delete (Del key)', e => { e.stopPropagation(); deleteMenu(id); }, 'danger'))));
      row.addEventListener('click', () => { if (id !== S.menuId) selectMenu(id); });
      title.addEventListener('dblclick', () => R.renameMenu(id));
      row.addEventListener('keydown', e => {
        if (e.target !== row) return;
        const i = ids.indexOf(id);
        const go = j => { selectMenu(ids[j]); const t = menuRowOf(ids[j]); if (t) t.focus(); };
        if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {     // Alt+Up/Down moves the menu in the list, like an item
          e.preventDefault();
          if (e.key === 'ArrowUp' ? i > 0 : i < ids.length - 1) {
            moveMenu(id, e.key === 'ArrowUp' ? ids[i - 1] : (ids[i + 2] || null));
            const t = menuRowOf(id); if (t) t.focus();
          }
        }
        else if (e.key === 'ArrowDown' && ids[i + 1]) { e.preventDefault(); go(i + 1); }
        else if (e.key === 'ArrowUp' && ids[i - 1]) { e.preventDefault(); go(i - 1); }
        else if (e.key === 'Home' && i > 0) { e.preventDefault(); go(0); }
        else if (e.key === 'End' && i < ids.length - 1) { e.preventDefault(); go(ids.length - 1); }
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
    setRoving(menuRows(), menuRowOf(S.menuId));
    if (had) {
      const rows = menuRows();
      const t = fid !== null && fid === prevSel && menuRowOf(S.menuId) ? menuRowOf(S.menuId)
        : (fid !== null ? (menuRowOf(fid) || rows[clamp(fidx, 0, rows.length - 1)]) : null);
      if (t) t.focus();
    }
  };
  /* Puts the keyboard on the selected menu's row (else the first row, else the list's Add menu button): after the control that had it is gone. */
  R.focusMenu = () => { const t = menuRowOf(S.menuId) || menuRows()[0] || $('button', listEl) || $('.dashed', left); if (t) t.focus(); };
  R.renameMenu = id => {
    const row = $(`.mrow[data-id="${CSS.escape(id)}"]`, listEl); if (!row) return;
    const title = $('.mrow-title', row), m = menuOf(id);
    const inp = h('input', { class: 'inp rename', type: 'text', value: m.title || '', 'aria-label': 'Menu title' });
    title.replaceChildren(inp); row.classList.add('renaming');
    inp.focus(); inp.select();
    let done = false;
    const finish = ok => {
      if (done) return; done = true;
      if (ok) {
        const v = inp.value.trim();
        if (v && v !== m.title) {
          const old = m.title || ''; m.title = v;
          const nid = idForTitle(id, old); if (nid) moveMenuId(id, nid);       // one undo step for title and id
          commit({ inspector: true }); if (R.head) R.head(); return;
        }
      }
      listEl._sig = null;                                       // the row holds the input: force a rebuild
      if (R.menuList) R.menuList();                             // gone when the blur comes from leaving the screen
    };
    // Only Enter and Escape are ours; everything else (Ctrl+S, Alt+1..6) still reaches the window, after the new title is taken in
    inp.addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.stopPropagation(); finish(true); }
      else if (e.key === 'Escape') { e.stopPropagation(); finish(false); }
      else if (((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 's') || (e.altKey && !e.ctrlKey && screenKey(e) !== null)) finish(true);
    });
    inp.addEventListener('blur', () => finish(true));
    inp.addEventListener('click', e => e.stopPropagation());
  };

  /* --- items list */
  const addBtn = h('button', { class: 'btn small', type: 'button', onclick: e => popover(e.currentTarget, Object.keys(KIND).filter(k => isFull() || !kindIsFull(k)).map(k => ({ icon: KIND[k].icon, label: KIND[k].label, hint: KIND[k].hint, fn: () => addItem(k) }))) }, icon('plus', 13), 'Add item');
  R.itemList = () => {
    const m = curMenu();
    const back = S.cameFrom && S.cameFrom.menuId !== S.menuId ? menuOf(S.cameFrom.menuId) : null;
    if (!back && S.cameFrom) S.cameFrom = null;
    itemsHead.replaceChildren(...[back ? h('button', { class: 'chip back', type: 'button', title: 'Back to ' + (back.title || S.cameFrom.menuId), onclick: goBack }, icon('chevL', 12), h('span', { class: 'back-txt' }, 'Back to ' + (back.title || S.cameFrom.menuId))) : null,
      h('span', { class: 'micro' }, 'Items'), h('span', { class: 'count' }, m ? String(m.items.length) : '0'), h('span', { class: 'spacer' }), m ? addBtn : null].filter(Boolean));
    R.itemNote();
    renderItemList(itemsEl, S.menuId, false);
  };
  R.itemNote = () => {
    const full = S.menuId ? ringNote(S.menuId) : null;
    itemsNote.hidden = !full;
    itemsNote.classList.toggle('warn', !!full && full.tooBig);
    if (full) itemsNote.replaceChildren(icon('alert', 13), full.text, ...(full.link && S.opts && S.opts.looks ? [' ', linkBtn('Change in Look', () => goToProblem({ kind: 'look', level: 'menu', menuId: S.menuId, key: 'when_full', group: 'when_full' }))] : []));
    else itemsNote.replaceChildren();
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
      dock.relayout();
      dock.scroller().scrollTop = dockScroll;
      R.badges = () => dock.updateBadges();
    }
    if (S.tab !== 'brushes') R.badges = null;
  };
  R.libRefresh = kind => { if (dock && kind === S.dock.kind) dock.refresh(); };

  R.head(); R.menuList(); R.itemList(); R.right();
  stageBox.start();
}

/* Reusable item list: used by the Menus screen and the Library screen's target panel. */
function renderItemList(box, menuId, compact) {
  const m = menuOf(menuId);
  box.classList.toggle('compact', compact);
  const refreshSel = () => {
    const rows = $$('.irow', box);
    rows.forEach(x => {
      const on = !compact && +x.dataset.i === S.itemIdx;
      x.classList.toggle('sel', on); x.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    setRoving(rows, compact ? rows[box._rov] : rows[S.itemIdx]);       // one Tab stop per list: the selected row (a compact list has no selection: the last one focused)
  };
  if (!box._rovBound) {
    box._rovBound = true;
    box.addEventListener('focusin', e => { const x = e.target.closest && e.target.closest('.irow'); if (x && x.parentElement === box) { box._rov = +x.dataset.i; setRoving($$('.irow', box), x); } });
  }
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
    const sub = itemSub(it);
    const row = h('div', { class: 'irow k-' + k + (!compact && i === S.itemIdx ? ' sel' : '') + (ok ? '' : ' bad'), role: 'option', tabindex: '-1', dataset: { i, menu: menuId },
      title: itemLabel(it) + '\n' + KIND[k].label + ': ' + sub,                    // the full name and target, for a row too narrow to show them
      'aria-selected': !compact && i === S.itemIdx ? 'true' : 'false' },
      compact ? null : h('span', { class: 'grip', 'aria-hidden': 'true' }, icon('grip', 14)),
      h('span', { class: 'inum mono' }, String(i + 1)),
      itemThumb(it, compact ? 26 : 32),
      h('span', { class: 'imain' }, h('span', { class: 'iname' }, isLib(k) ? tagDot(k, it[k]) : keyTag(it) ? keyDot(keyTag(it)) : null, itemLabel(it)),
        compact ? null : h('span', { class: 'isub mono' }, sub)),
      h('span', { class: 'ikind', title: KIND[k].hint }, icon(KIND[k].icon, 13), compact ? null : KIND[k].label),
      itemWarn(menuId, i, ok),
      h('span', { class: 'iacts' },
        compact ? null : noTab(iconBtn('copy', 'Duplicate item', e => { e.stopPropagation(); S.itemIdx = i; dupItem(i); })),
        noTab(iconBtn('trash', compact ? 'Delete item' : 'Delete (Del key)', e => { e.stopPropagation(); if (e.detail > 1) return; delItem(i, menuId); }, 'danger'))));
    // Up, Down, Home and End move through the list (in the editor the selection goes with them); Delete removes the row
    row.addEventListener('keydown', e => {
      if (e.target !== row) return;
      const rows = $$('.irow', box);
      const go = j => { if (!compact) selectItem(j); const t = $$('.irow', box)[j]; if (t) t.focus(); };
      if (!compact && e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
        e.preventDefault();
        const to = e.key === 'ArrowUp' ? i - 1 : i + 2;
        if (to >= 0 && to <= m.items.length) { moveItem(menuId, i, to); const r = $$('.irow', box)[e.key === 'ArrowUp' ? i - 1 : i + 1]; if (r) r.focus(); }
      }
      else if (e.key === 'ArrowDown' && rows[i + 1]) { e.preventDefault(); go(i + 1); }
      else if (e.key === 'ArrowUp' && rows[i - 1]) { e.preventDefault(); go(i - 1); }
      else if (e.key === 'Home' && i > 0) { e.preventDefault(); go(0); }
      else if (e.key === 'End' && i < rows.length - 1) { e.preventDefault(); go(rows.length - 1); }
      else if (e.key === 'Enter' && !compact) { e.preventDefault(); selectItem(i, { focusTarget: true }); }
      else if (e.key === 'Delete') { e.preventDefault(); delItem(i, menuId); }
      else if ((e.key === 'm' || e.key === 'M') && !compact && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); moveToMenuPopover(row, menuId, i); }
    });
    if (!compact) {
      row.addEventListener('click', () => selectItem(i));
      row.addEventListener('dblclick', () => { if (k === 'menu' && hasMenu(it.menu)) openSubmenu(it.menu, i); });
    }
    if (k !== 'empty') DnD.source(row, () => ({ type: 'item', menuId, index: i }), () => h('span', { class: 'ghost-chip' }, itemThumb(it, 22), itemLabel(it)));       // an empty slot is only ever dropped on
    box.append(row);
  });
  const insertIndex = y => {
    const rows = $$('.irow', box);
    for (let j = 0; j < rows.length; j++) { const r = rows[j].getBoundingClientRect(); if (y < r.top + r.height / 2) return j; }
    return rows.length;
  };
  const rowAt = y => { const rows = $$('.irow', box); for (let j = 0; j < rows.length; j++) { const r = rows[j].getBoundingClientRect(); if (y >= r.top && y < r.bottom) return j; } return null; };     // the row under the pointer
  const clear = () => { $$('.ins-before, .drop-row', box).forEach(r => r.classList.remove('ins-before', 'drop-row')); box.classList.remove('ins-end', 'drop-over'); };
  DnD.zone(box, {
    accept: p => p.type === 'asset' || (p.type === 'item' && p.menuId === menuId),
    over: (p, x, y) => {
      clear(); box.classList.add('drop-over');
      const rows = $$('.irow', box);
      if (keeps(menuOf(menuId))) {                                 // the row under the pointer is the slot it lands on
        const j = rowAt(y);
        if (j !== null && !(p.type === 'item' && p.index === j)) rows[j].classList.add('drop-row');
        return;
      }
      const j = insertIndex(y);
      if (j < rows.length) rows[j].classList.add('ins-before'); else box.classList.add('ins-end');
    },
    leave: clear,
    drop: (p, x, y) => (keeps(menuOf(menuId)) ? dropOnSlot(menuId, p, rowAt(y)) : dropOnMenu(menuId, p, insertIndex(y))),
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

/* ---------- the ring picture and its overlay (the Menus stage and the Look preview) */
const SVG_NS = 'http://www.w3.org/2000/svg';
const svgEl = (name, attrs) => { const e = document.createElementNS(SVG_NS, name); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
/* RingView lays a picture of the ring, an SVG overlay and (optionally) number badges in one box, so they move and scale together; the box is
   the whole picture, which with a fan open is not square and not centred on the ring. The overlay is drawn from the layout map that preview_ring
   sends with the picture (layout, in the picture's pixels): a mark for each slot in the slot's own shape, and the bar where a dropped item goes.
   It picks as the ring does (ZLook.slotAt, ZLook.gapAt). While the layout does not fit the menu (count() slots, a More slot allowing for
   fewer), the marks are hidden and the hit tests answer null.
     opts: { wrap, img, count(): the menu's slots or null to trust the layout, badge(slot, i): the text of a number badge or null for none (omit for no badges) }
     setShown(layout): the layout of the picture now in img.    place(fanBox, D, size): puts the box in wrap (fanBox: { w, h, cx, cy } or null).
     rebuild(): draws the marks again (after the layout, the size of the box or the number of items changed).
     paint({ hover, sel, moving, drop, gap }): ring indices (or -1/null), the slot a drop would land on, and the gap bar { x, y, ang, len, noop } or null.
     glide(moves): [[from, to], ...] ring indices; ghosts of those slots' pictures glide across the ring to each other's place over the old picture, which
       is masked there, until endGlide() (called once the new picture is in). Returns the glide { done, settled } or null (reduced motion, no picture).
     valid(), layout(), isMore(i), slotAt(clientX, clientY) -> ring index or null, gapAt(clientX, clientY) -> gap or null. */
function makeRingView({ wrap, img, count, badge = null }) {
  const box = h('div', { class: 'ring-box' });
  const svg = svgEl('svg', { class: 'ring-svg', 'aria-hidden': 'true', focusable: 'false' });
  const ov = h('div', { class: 'ring-ov' }, svg);
  box.append(img, ov);
  wrap.prepend(box);
  let lay = null, marks = [], state = { hover: null, sel: null, moving: null, drop: null, gap: null }, gl = null;
  const valid = () => { if (!lay || !Array.isArray(lay.slots) || !lay.slots.length || !Array.isArray(lay.size) || !Array.isArray(lay.centre)) return false; const n = count(); return n === null || ZLook.layoutFits(lay, n); };
  /* The point in the picture, measured from the ring's centre. */
  const rel = (cx, cy) => {
    const r = box.getBoundingClientRect();
    if (!lay || !r.width || !r.height) return null;
    return { x: (cx - r.left) / r.width * lay.size[0] - lay.centre[0], y: (cy - r.top) / r.height * lay.size[1] - lay.centre[1] };
  };
  const outline = (s, cx, cy, grow, cls) => {
    const r = s.size / 2 + grow, pts = ZLook.shapePoints(s.shape, cx, cy, s.size / 2, grow);
    if (pts) return svgEl('polygon', { class: cls, points: pts.map(p => p[0].toFixed(2) + ',' + p[1].toFixed(2)).join(' ') });
    if (s.shape === 'rounded') return svgEl('rect', { class: cls, x: cx - r, y: cy - r, width: 2 * r, height: 2 * r, rx: 2 * r * (Number.isFinite(s.corner) ? s.corner : 0.28) });
    return svgEl('circle', { class: cls, cx, cy, r });
  };
  function rebuild() {
    svg.replaceChildren(); marks = [];
    for (const b of $$('.slot-ov', ov)) b.remove();
    const ok = valid();
    ov.classList.toggle('stale', !ok);
    if (!ok) return;
    const [w, ht] = lay.size, k = w / (box.clientWidth || w);              // k: picture pixels to a screen pixel
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + ht);
    lay.slots.forEach((s, i) => {
      const cx = lay.centre[0] + s.x, cy = lay.centre[1] + s.y, g = svgEl('g', { class: 'mk' });
      g.append(outline(s, cx, cy, 0, 'mk-f'), outline(s, cx, cy, 5 * k, 'mk-h'), outline(s, cx, cy, 5 * k, 'mk-r'));
      svg.append(g);
      const text = badge ? badge(s, i) : null;
      let bd = null;
      if (text !== null && text !== undefined) {
        bd = h('div', { class: 'slot-ov', style: { left: cx / w * 100 + '%', top: cy / ht * 100 + '%', width: s.size / w * 100 + '%', height: s.size / ht * 100 + '%' } }, h('span', { class: 'slot-n mono' }, text));
        ov.append(bd);
      }
      marks.push({ g, bd });
    });
    paint(state);
  }
  function paint(next) {
    state = Object.assign({ hover: null, sel: null, moving: null, drop: null, gap: null }, next);
    const bar = svg.querySelector('.gap-bar'); if (bar) bar.remove();
    if (!valid()) return;
    marks.forEach((m, i) => {
      for (const [cls, on] of [['hov', state.hover === i], ['sel', state.sel === i], ['moving', state.moving === i], ['drop', state.drop === i]]) { m.g.classList.toggle(cls, on); if (m.bd) m.bd.classList.toggle(cls, on); }
    });
    const g = state.gap;
    if (g) {
      const a = g.ang * Math.PI / 180, ux = Math.sin(a), uy = -Math.cos(a), cx = lay.centre[0] + g.x, cy = lay.centre[1] + g.y, half = g.len / 2;
      svg.append(svgEl('line', { class: 'gap-bar' + (g.noop ? ' noop' : ''), x1: cx - ux * half, y1: cy - uy * half, x2: cx + ux * half, y2: cy + uy * half }));
    }
  }
  const MASK = ['mask-image', '-webkit-mask-image', 'mask-composite', '-webkit-mask-composite'];
  /* The moving pictures: the ring picture cropped to a slot's box, on an arm centred on the ring that turns from the slot's angle to the other's
     (the ghost turns back by the same, so it stays upright). The old picture is masked where the slots were, so nothing shows twice. */
  function glide(moves) {
    endGlide(true);
    const reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || !moves.length || !valid() || !box.clientWidth || !img.src || img.classList.contains('pending')) return null;
    const [w, ht] = lay.size, k = box.clientWidth / w, src = img.currentSrc || img.src, [ox, oy] = lay.centre;
    const at = i => { const sl = lay.slots[i]; return { x: sl.x, y: sl.y, a: Math.atan2(sl.x, -sl.y) * 180 / Math.PI, r: Math.hypot(sl.x, sl.y) * k, size: sl.size }; };
    const holes = new Set(moves.flat());
    img.style.setProperty('mask-image', Array.from(holes, i => { const p = at(i), R = p.size * 0.62 * k; return `radial-gradient(circle at ${(ox + p.x) * k}px ${(oy + p.y) * k}px, transparent ${R}px, #000 ${R + 1.5}px)`; }).join(','));
    img.style.setProperty('-webkit-mask-image', img.style.getPropertyValue('mask-image'));
    img.style.setProperty('mask-composite', 'intersect'); img.style.setProperty('-webkit-mask-composite', 'source-in');
    const layer = h('div', { class: 'ring-glide' }), anims = [], opt = { duration: 250, easing: 'ease-in-out', fill: 'both' };
    moves.forEach(([fi, ti], n) => {
      const f = at(fi), t = at(ti), gs = f.size * 1.2 * k, d = ((t.a - f.a + 540) % 360) - 180;       // d: the short way round
      const mid = (f.r + t.r) / 2 + (moves.length > 1 ? (n ? -1 : 1) * 0.45 * f.size * k : 0);          // two passing each other take an outer and an inner lane
      const arm = h('div', { class: 'gl-arm', style: { left: ox * k + 'px', top: oy * k + 'px' } });
      const ghost = h('div', { class: 'gl-ghost', style: { width: gs + 'px', height: gs + 'px', left: -gs / 2 + 'px', top: -gs / 2 + 'px', backgroundImage: 'url(' + JSON.stringify(src) + ')',
        backgroundSize: w * k + 'px ' + ht * k + 'px', backgroundPosition: -((ox + f.x) * k - gs / 2) + 'px ' + -((oy + f.y) * k - gs / 2) + 'px' } });
      arm.append(ghost); layer.append(arm);
      anims.push(arm.animate([f.a, f.a + d / 2, f.a + d].map(a => ({ transform: `rotate(${a}deg)` })), opt));
      anims.push(ghost.animate([[f.r, f.a], [mid, f.a + d / 2], [t.r, f.a + d]].map(([r, a]) => ({ transform: `translateY(${-r}px) rotate(${-a}deg)` })), opt));
    });
    box.append(layer);
    const g = gl = { layer, settled: false, done: null };
    g.done = Promise.all(anims.map(a => a.finished)).catch(() => {}).then(() => { g.settled = true; });
    return g;
  }
  /* Takes the ghosts away (they fade, or go at once with `now`) and gives the picture its slots back. */
  function endGlide(now) {
    if (!gl) return;
    const g = gl; gl = null;
    for (const p of MASK) img.style.removeProperty(p);
    if (now) g.layer.remove();
    else g.layer.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 160, easing: 'ease-out', fill: 'forwards' }).finished.catch(() => {}).then(() => g.layer.remove());
  }
  return {
    box, ov, rebuild, paint, valid, glide, endGlide,
    gliding: () => gl,
    layout: () => (valid() ? lay : null),
    setShown(layout) { lay = layout || null; },
    isMore: i => !!(lay && lay.slots[i] && lay.slots[i].more),
    place(fan, D, size) {
      const st = box.style;
      if (!fan) { st.left = st.top = st.width = st.height = ''; return; }          // the stylesheet puts the box over the whole of wrap
      const k = D / size;
      st.left = D / 2 - fan.cx * k + 'px'; st.top = D / 2 - fan.cy * k + 'px'; st.width = fan.w * k + 'px'; st.height = fan.h * k + 'px';
    },
    slotAt(cx, cy) { if (!valid()) return null; const p = rel(cx, cy); return p ? ZLook.slotAt(lay, p.x, p.y) : null; },
    gapAt(cx, cy) { if (!valid()) return null; const p = rel(cx, cy); return p ? ZLook.gapAt(lay, p.x, p.y) : null; },
  };
}

/* The note above the item list when a menu has more items than its ring holds at its radius. What the ring does comes from the layout map of
   the menu's own picture (layout.full, which follows the menu's look and its When full choice); fit says how many items the menu has. Until the
   picture arrives the note of the same menu with as many items stays; with none yet there is no note. Returns null when the items fit,
   else { text, tooBig, link }; tooBig: the grown ring's window would not fit the screen (ring.py pushes it against the edges then). */
const ringNoteMemo = { menuId: null, n: -1, note: null };
function ringNote(menuId) {
  const m = menuOf(menuId), n = m && Array.isArray(m.items) ? m.items.length : 0;
  const res = RingLoader.peek(menuId, null, null), lay = res && res.image && res.layout && res.layout.full ? res.layout : null;
  if (!lay) return ringNoteMemo.menuId === menuId && ringNoteMemo.n === n ? ringNoteMemo.note : null;
  const f = lay.full, fit = res.fit, count = fit ? fit.items : n, link = !!(S.opts && S.opts.looks);
  const holds = 'At a radius of ' + Math.round(f.radius) + ' px this ring holds ' + f.capacity + (f.capacity === 1 ? ' item' : ' items') + '. ';
  let note = null;
  if (f.mode === 'rings') note = { text: 'This ring is full: ' + plural(Math.max(1, count - f.capacity), 'item') + (count - f.capacity === 1 ? ' goes' : ' go') + ' on a second ring.', tooBig: false };
  else if (f.more_slot !== null && f.more_slot !== undefined) note = { text: 'This ring is full: ' + plural(f.more_items, 'item') + (f.more_items === 1 ? ' is' : ' are') + ' in the More submenu.', tooBig: false };
  else if (f.grown) {
    const slot = Math.max(...lay.slots.map(s => s.size)) / (lay.scale || 1);
    const tooBig = 2 * (f.needed + slot * 0.62 + 34) > Math.min(screen.availWidth || Infinity, screen.availHeight || Infinity);
    const label = isFull() ? 'Ring radius' : 'Ring size';
    note = { text: holds + 'With ' + f.n + ' it grows to ' + Math.round(f.needed) + ' px. ' + (tooBig ? 'It is too big for this screen, so it is pushed against the edges. ' : '')
      + (link ? '' : (isFull() ? 'Raise ' + label + ', lower Slot size or move some items into a submenu.' : 'Raise ' + label + ' or move some items into a submenu.')), tooBig };
  }
  if (note) note.link = link;
  Object.assign(ringNoteMemo, { menuId, n, note });
  return note;
}
function buildStage() {
  const img = h('img', { class: 'ring-img pending', alt: 'Ring preview', draggable: false });     // hidden until the first image has decoded, so no broken-image icon
  const wrap = h('div', { class: 'ring-wrap' });
  const emptyEl = h('div', { class: 'stage-empty' });
  const errEl = h('div', { class: 'stage-err' });
  const info = h('div', { class: 'stage-info' });
  const busy = h('span', { class: 'stage-busy', title: 'Updating preview' });
  const playBtn = h('button', { class: 'btn small stage-play', type: 'button' });
  const tip = h('div', { class: 'stage-tip' }, 'Hover to preview, click to select, drag slots or items between slots');
  const trash = h('div', { class: 'stage-trash', 'aria-hidden': 'true' }, icon('trash', 14), 'Delete');     // only there while an item of this menu is being dragged
  // + and -: one more empty slot at the end, or one less (only an empty last slot can go); for a menu that keeps its slots in place
  const minusBtn = iconBtn('minus', 'Remove the last slot', () => {
    const m = curMenu(); if (!keeps(m) || !ZSlots.trimEnd(m.items)) return;
    if (S.itemIdx !== null && S.itemIdx >= m.items.length) { S.itemIdx = null; if (S.tab === 'item') S.tab = 'menu'; }
    commit({ inspector: true, now: true }); if (R.head) R.head();
  });
  const plusBtn = iconBtn('plus', 'Add an empty slot at the end', () => {
    const m = curMenu(); if (!keeps(m)) return;
    ZSlots.addSlot(m.items); commit({ inspector: true, now: true }); if (R.head) R.head();
  });
  const slotsN = h('span', { class: 'slots-n mono' });
  const slotsBar = h('div', { class: 'stage-slots', role: 'group', 'aria-label': 'Number of slots', hidden: true }, minusBtn, slotsN, plusBtn);
  const el = h('div', { class: 'stage', tabindex: '0', 'aria-label': 'Ring preview. Use arrow keys to move between items.' },
    h('div', { class: 'stage-rings', 'aria-hidden': 'true' }), wrap, emptyEl, errEl, info, tip, busy, playBtn, slotsBar, trash);
  el.classList.add('loading');
  let curSize = 447, hoverRing = null, gap = null, dropAt = null, idxs = [], haveImage = false;   // gap: the bar { x, y, ang, len, k, text, noop } while a drag is over the ring; dropAt: { j, ix, text } for a menu that keeps its slots
  let box = null, baseVer = -1, shownPath = '';     // box: size and ring centre of the image while a fan is open (null: square, ring in the middle); baseVer: the version curSize was read at
  // number badges: the item's number; the More slot has none
  const view = makeRingView({ wrap, img, count: () => idxs.length, badge: (s, i) => (s.more || idxs[i] === undefined ? null : String(idxs[i] + 1)) });
  /* Ring slot i is which item of the menu (its index in menu.items)? null for a More slot. */
  const itemOf = i => { const L = view.layout(); return L && L.slots[i] && !L.slots[i].more && idxs[i] !== undefined ? idxs[i] : null; };
  const ringOf = ix => { const L = view.layout(); if (!L || ix === null || ix === undefined) return -1; for (let i = 0; i < L.slots.length; i++) if (itemOf(i) === ix) return i; return -1; };
  const nSlots = () => { const L = view.layout(); return L ? L.slots.length : idxs.length; };
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
    drawMarks();
  }
  /* With a fan open the image is bigger than the ring and not centred on it: it is laid out so its ring centre sits in the middle of wrap. */
  function placeImg() { view.place(box, wrap.clientWidth || curSize, curSize); }
  /* Item indices (in the ring's own order) of the fan to show open: the hovered slot, else the selected one, when it is a submenu whose menu has "fan" or a tag with brushes. */
  function fanPath() {
    const m = curMenu(); if (!m) return null;
    const at = hoverRing !== null ? itemOf(hoverRing) : S.itemIdx, j = at === null ? -1 : idxs.indexOf(at);
    const it = j >= 0 && itemUsable(m.items[at]) ? m.items[at] : null, t = it && 'menu' in it ? menuOf(it.menu) : null;      // an incomplete item is an empty slot on the ring: no fan
    if (it && 'tag' in it) return tagItemCount(it.tag) > 0 ? [j] : null;     // the expander turns it into a fan submenu of its items
    return t && t.fan === true && it.menu !== S.menuId ? [j] : null;
  }
  /* The marks again, for the picture and items now. */
  function paintSlotsBar() {
    const m = curMenu(), on = keeps(m);
    slotsBar.hidden = !on;
    if (!on) return;
    const n = m.items.length, free = n > 0 && ZSlots.isEmpty(m.items[n - 1]);
    setText(slotsN, plural(n, 'slot'));
    minusBtn.disabled = !free;
    minusBtn.title = n === 0 ? 'No slots to remove' : free ? 'Remove the last slot' : 'The last slot is in use';
    minusBtn.setAttribute('aria-label', minusBtn.title);
  }
  function drawMarks() {
    paintSlotsBar();
    idxs = slotIdx(S.menuId);
    if (hoverRing !== null && hoverRing >= nSlots()) { hoverRing = null; wrap.classList.remove('over-slot'); }   // the ring shrank (undo, menu switch)
    if (gap && gap.k > nSlots()) gap = null;
    view.rebuild();
    paintMarks();
  }
  function paintMarks() {
    const moving = DnD.active && DnD.active.payload.type === 'item' && DnD.active.payload.menuId === S.menuId ? DnD.active.payload : null;   // the slot being dragged
    view.paint({ hover: hoverRing, sel: ringOf(S.itemIdx), moving: moving ? ringOf(moving.index) : null, drop: dropAt && !dropAt.noop ? dropAt.j : null, gap });
    const m = curMenu();
    if (!idxs.length) { info.classList.remove('on'); return; }
    if (trash.classList.contains('over') && moving) {           // over the trash: say what goes, whatever redraws the ring meanwhile
      const it = m && m.items[moving.index];
      info.replaceChildren(h('span', null, 'Release to delete '), h('b', null, it ? itemLabel(it) : 'this item')); info.classList.add('on');
    } else if (dropAt) {
      info.replaceChildren(h('b', null, dropAt.text)); info.classList.add('on');
    } else if (gap) {
      info.replaceChildren(h('b', null, gap.text)); info.classList.add('on');
    } else if (hoverRing !== null && view.isMore(hoverRing)) {
      info.replaceChildren(h('b', null, 'More'), h('span', { class: 'mono' }, ' ' + plural(view.layout().full.more_items, 'item') + ' in a submenu')); info.classList.add('on');
    } else if (hoverRing !== null && m && m.items[itemOf(hoverRing)] && ZSlots.isEmpty(m.items[itemOf(hoverRing)])) {
      info.replaceChildren(h('b', null, 'Empty slot'), h('span', { class: 'mono' }, ' drop something here')); info.classList.add('on');
    } else if (hoverRing !== null && m && m.items[itemOf(hoverRing)] && !itemUsable(m.items[itemOf(hoverRing)])) {
      info.replaceChildren(h('b', null, itemLabel(m.items[itemOf(hoverRing)])), h('span', { class: 'mono' }, ' incomplete')); info.classList.add('on');
    } else if (hoverRing !== null && m && m.items[itemOf(hoverRing)]) {
      const it = m.items[itemOf(hoverRing)];
      info.replaceChildren(h('b', null, itemLabel(it)), h('span', { class: 'mono' }, ' ' + KIND[kindOf(it)].label.toLowerCase() + (['steps', 'auto'].includes(kindOf(it)) ? '' : kindOf(it) === 'recent' ? ' / ' + itemSub(it) : kindOf(it) === 'tag' ? ' / ' + tagName(it.tag) : kindOf(it) === 'browser' ? ' / ' + (it.browser ? tagName(it.browser) : 'all ' + K(it.kind).many) : ' / ' + targetOf(it))));
      info.classList.add('on');
    } else info.classList.remove('on');
  }
  let wantedUrl = '';
  const reveal = () => { img.classList.remove('pending'); el.classList.remove('loading'); };   // the shimmer stays until a decoded image can take its place
  /* The picture and its layout (and the fan box) change together. */
  function setImg(url, nextBox, lay) {
    const g = view.gliding();
    if (g && !g.settled) { wantedUrl = url; g.done.then(() => { if (wantedUrl === url) setImg(url, nextBox, lay); }); return; }   // the new picture waits for the ghosts to arrive
    const apply = () => { box = nextBox; view.setShown(lay); placeImg(); drawMarks(); view.endGlide(); };
    if (img.getAttribute('src') === url) { wantedUrl = url; apply(); return; }
    wantedUrl = url;
    if (!img.getAttribute('src')) {
      img.src = url; apply();
      img.decode().catch(() => {}).then(() => { if (wantedUrl === url || img.getAttribute('src') === url) reveal(); });
      return;
    }
    const pre = new Image(); pre.src = url;
    pre.decode().catch(() => {}).then(() => { if (wantedUrl === url) { img.src = url; apply(); reveal(); } });   // picture, layout and placement change together
  }
  function showRes(res, path) {
    el.classList.remove('busy');
    if (res && res.image) {
      el.classList.remove('err'); haveImage = true;
      const w = res.width || res.size, ht = res.height || res.size, cx = res.centre ? res.centre[0] : w / 2, cy = res.centre ? res.centre[1] : ht / 2;
      const fanned = !!path && (Math.abs(w - ht) > 1.5 || Math.abs(cx - w / 2) > 1.5 || Math.abs(cy - ht / 2) > 1.5);
      if (!fanned) { if (res.size && res.size !== curSize) curSize = res.size; baseVer = S.version; if (R.itemNote) R.itemNote(); }     // only the plain ring says how big the ring is, and how full it is
      setImg(res.image, fanned ? { w, h: ht, cx, cy } : null, res.layout || null);
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
    paintSlotsBar();
    idxs = slotIdx(S.menuId);
    emptyEl.replaceChildren();
    const has = idxs.length > 0;
    if (!has) el.classList.remove('err', 'busy');
    wrap.hidden = !has; emptyEl.hidden = has; playBtn.hidden = !has; tip.hidden = !has;
    if (!m) { emptyEl.append(emptyState('menus', 'No menu selected', 'Pick or create a menu on the left.')); return; }
    if (!has) {
      emptyEl.append(m.items.length
        ? emptyState('alert', 'No usable items yet', 'Fill in the target of an item (see the problems panel). The ring opens once one item is complete.')
        : emptyState('plus', 'This menu is empty', 'Add an item from the Library tab or create one. The ring appears as soon as it has one.', { text: 'Add item', fn: () => addItem('brush') }));
      return;
    }
    drawMarks();
  }

  /* Before a swap: pairs of item indices [from, to]; the picture of each glides to the other's place until the new picture arrives. */
  let glideTimer = 0;
  R.glide = pairs => {
    if (!el.isConnected || !el.offsetParent || player.state !== 'idle' || !view.valid()) return;
    const moves = pairs.map(([a, b]) => [ringOf(a), ringOf(b)]).filter(([f, t]) => f >= 0 && t >= 0 && f !== t);
    clearTimeout(glideTimer);
    if (view.glide(moves)) glideTimer = setTimeout(() => view.endGlide(), 4000);          // the picture never came: give the slots back
  };
  R.overlay = () => { drawMarks(); if (idxs.length && player.state === 'idle' && (fanPath() || []).join() !== shownPath) requestImage(); };      // a new selection may open or close a fan
  R.preview = () => { player.stop(); refresh(); if (idxs.length) requestImage(); };
  el.addEventListener('keydown', e => {
    const m = curMenu(); if (!m || !idxs.length || e.target !== el) return;
    const pos = idxs.indexOf(S.itemIdx);
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); selectItem(idxs[(pos + 1) % idxs.length]); el.focus(); }
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); selectItem(idxs[pos < 0 ? idxs.length - 1 : (pos - 1 + idxs.length) % idxs.length]); el.focus(); }
  });
  wrap.addEventListener('pointermove', e => { if (player.state === 'idle' && !DnD.active) setHover(view.slotAt(e.clientX, e.clientY)); });
  wrap.addEventListener('pointerleave', () => setHover(null));
  wrap.addEventListener('click', e => {
    if (player.state === 'playing') { player.stop(); return; }
    if (!view.valid()) return;                                     // no map of the slots yet (the picture is being redrawn): the list and the arrow keys still select
    const j = view.slotAt(e.clientX, e.clientY);
    if (j !== null && view.isMore(j)) { el.focus({ preventScroll: true }); return; }     // More is not an item: it cannot be selected
    selectItem(j === null ? null : itemOf(j), { keepTab: true });     // empty space clears the selection, and the inspector stays on its tab
    el.focus({ preventScroll: true });
  });
  /* A ring slot is a drag source too: it moves like a row of the item list. A plain click still selects. */
  DnD.source(wrap, e => {
    if (player.state !== 'idle') return null;
    const j = view.slotAt(e.clientX, e.clientY), ix = j === null ? null : itemOf(j), m = curMenu();
    return ix === null || !m || ZSlots.isEmpty(m.items[ix]) ? null : { type: 'item', menuId: S.menuId, index: ix };       // an empty slot is only ever dropped on
  }, e => {
    const m = curMenu(), j = view.slotAt(e.clientX, e.clientY), it = m && j !== null && m.items[itemOf(j)];
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
  /* Where a drop at gap k lands in the item list; k === null (the dead zone) and the gap after the last slot mean the end. A gap before a More
     slot is the first item in More, which is the first item the ring does not show. */
  const itemIndexFor = k => { const m = curMenu(); if (!m) return 0; return k === null || k >= nSlots() ? m.items.length : (idxs[k] === undefined ? m.items.length : idxs[k]); };
  const slotLabel = j => { const m = curMenu(), ix = itemOf(j), it = m && ix !== null && m.items[ix]; return it ? itemLabel(it) : view.isMore(j) ? 'More' : ''; };
  // Dropping an item where it already is changes nothing: its own two gaps (before it, after it)
  function staysPut(p, k) {
    if (p.type !== 'item' || k === null) return false;
    const at = itemIndexFor(k);
    if (at === p.index || at === p.index + 1) return true;
    const L = view.layout(), j = idxs.indexOf(p.index), shown = nSlots() - (L && L.full && L.full.more_slot !== null && L.full.more_slot !== undefined ? 1 : 0);
    return j >= 0 && j < shown && (k === j || k === j + 1);
  }
  function gapText(p, g) {
    const n = nSlots(), move = p.type === 'item', k = g.k;
    if (staysPut(p, k)) return 'Stays in place';
    if (g.into_more) return move ? 'Move into More' : 'Insert into More';
    if (move && k === n && idxs.indexOf(p.index) === 0) return 'Move to the end';
    return n === 1 ? (move ? 'Move after ' : 'Insert after ') + slotLabel(0) : (move ? 'Move between ' : 'Insert between ') + slotLabel(k - 1) + ' and ' + slotLabel(k % n);
  }
  /* A menu that keeps its slots: what a drop here does, by the slot under the pointer. ix: that slot's item (null: none, or More), j: its place in the ring. */
  function slotDrop(p, x, y) {
    const m = curMenu(), j = view.slotAt(x, y), ix = j === null ? null : itemOf(j), it = ix === null ? null : m.items[ix], name = p.name || 'it';
    if (p.type === 'item') {
      if (!it || ix === p.index) return { j: null, ix: null, text: 'Stays in place', noop: true };
      return { j, ix, text: ZSlots.isEmpty(it) ? 'Move to empty slot' : 'Swap with ' + itemLabel(it) };
    }
    if (!it) return { j: null, ix: null, text: ZSlots.firstEmpty(m.items) >= 0 ? `Put ${name} in the first empty slot` : `Add ${name} in a new slot` };
    return { j, ix, text: ZSlots.isEmpty(it) ? `Put ${name} here` : `Replace ${itemLabel(it)}` };
  }
  DnD.zone(el, {
    accept: p => !!curMenu() && (!!idxs.length ? (p.type === 'asset' || (p.type === 'item' && p.menuId === S.menuId)) : p.type === 'asset'),   // no menu: nothing to add to
    over: (p, x, y) => {
      if (keeps(curMenu())) {
        const d = slotDrop(p, x, y);
        if (!dropAt || dropAt.j !== d.j || dropAt.text !== d.text) { dropAt = d; gap = null; paintMarks(); }
        el.classList.add('drop-over'); el.classList.remove('drop-end');
        return;
      }
      const g = view.gapAt(x, y), k = g ? g.k : null, noop = !!g && staysPut(p, k);
      if (k !== (gap ? gap.k : null) || (gap && gap.noop !== noop)) {
        gap = g ? Object.assign({}, g, { text: gapText(p, g), noop }) : null;
        paintMarks();
      }
      el.classList.add('drop-over'); el.classList.toggle('drop-end', k === null);
    },
    leave: () => { gap = null; dropAt = null; paintMarks(); el.classList.remove('drop-over', 'drop-end'); },
    drop: (p, x, y) => {
      if (keeps(curMenu())) { dropOnSlot(S.menuId, p, slotDrop(p, x, y).ix); return; }
      const g = view.gapAt(x, y), k = g ? g.k : null, at = itemIndexFor(k);
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
    start() { refresh(); if (idxs.length) requestImage(); },
  };
}

/* ---------- item inspector */
function buildItemInspector() {
  R.itemHint = null;                                  // set below by the kinds that have a hint to repaint when a library finishes loading
  const box = h('div', { class: 'insp' });
  const m = curMenu(), it = curItem();
  if (!m) return emptyState('menus', 'No menu selected', '');
  if (!it) {
    box.append(emptyState('k_press', 'No item selected', 'Click a slot in the ring or an item in the list to edit it.', m.items.length ? null : { text: 'Add item', fn: () => addItem('brush') }));
    return box;
  }
  const i = S.itemIdx, k = kindOf(it);
  const locked = !isFull() && kindIsFull(k);          // a Full-only item in Simple: shown read-only, still deletable, duplicable and convertible
  const moveBtn = iconBtn('k_menu', Object.keys(S.cfg.menus).length > 1 ? 'Move to menu...' : 'Move to menu (there is no other menu)', e => moveToMenuPopover(e.currentTarget, S.menuId, i, () => {
    const t = $('.irow.sel') || $('.items-panel .col-head .btn'); if (t) t.focus();       // the inspector was rebuilt around the next item
  }));
  moveBtn.disabled = Object.keys(S.cfg.menus).length < 2;
  box.append(h('div', { class: 'insp-head' }, itemThumb(it, 36), h('div', { class: 'insp-title' }, h('b', null, itemLabel(it)), h('span', null, `Item ${i + 1} of ${m.items.length}`)),
    h('div', { class: 'spacer' }), moveBtn, iconBtn('copy', 'Duplicate item', () => dupItem(i)), iconBtn('trash', 'Delete item', e => { if (e.detail > 1) return; delItem(i); const t = $('.irow.sel') || $('.items-panel .col-head .btn'); if (t) t.focus(); }, 'danger')));    // delItem already selected the neighbour, as the row's own button does

  /* action type */
  const seg = h('div', { class: 'kinds', role: 'radiogroup', 'aria-label': 'Action type' }, Object.keys(KIND).filter(kk => kk === k || ((isFull() || !kindIsFull(kk)) && kk !== 'empty')).map(kk =>
    h('button', { class: 'kind' + (kk === k ? ' on' : '') + ' k-' + kk, type: 'button', role: 'radio', 'aria-checked': kk === k ? 'true' : 'false', title: KIND[kk].hint,
      onclick: () => {
        if (kk === k) return;
        sealSnap();
        const r = convertItem(it, kk);
        m.items[i] = r.item; commit({ inspector: true });
        const t = $('[data-focus="target"]');
        if (t && !t.value) t.focus(); else { const kb = $('.kinds .kind.on'); if (kb) kb.focus(); }      // the inspector was rebuilt: keep the keyboard on the type picker
        if (r.lost.length) undoToast(`Switched to ${KIND[kk].label}. Dropped ${joinList(r.lost)}.`, { ms: 6500 });
      } },
      icon(KIND[kk].icon, 18), h('span', null, KIND[kk].label))));
  if (k === 'empty') box.append(h('div', { class: 'slot-note' }, icon('k_empty', 15), h('span', null, 'This slot is empty. Drag something into it from the Library, or choose a type below.')));
  box.append(field('Action', seg, KIND[k].hint + '.'));
  if (k === 'empty') return box;                      // nothing else to set: it has no target, label or icon

  const hintEl = h('div', { class: 'fhint' });
  const labelInp = textInput(it.label || '', v => { if (v.trim()) it.label = v; else delete it.label; commit(); updateHead(); }, { placeholder: defaultLabel(it), label: 'Label' });
  const updateHead = () => { setText($('.insp-title b', box), itemLabel(it)); labelInp.placeholder = defaultLabel(it); };

  if (locked) {
    box.append(field(KIND[k].label, h('div', { class: 'locked-line' }, KIND[k].label + ': ' + itemSub(it)),
      [linkBtn('Edit in Full mode', () => setMode('full'))]));
    if (k === 'auto') return box;
  } else if (k === 'auto') {
    box.append(field('Right now', autoNow(m, i), 'The brush you pick most often from any ring, apart from the brushes this menu already has. Picks fade with a two-week half-life. A newcomer has to come out on top twice in a row before it takes a slot, and it takes the slot of a brush you have stopped using, so the rest of the ring stays put.'));
    return box;
  } else if (k === 'tag' || k === 'browser') {
    box.append(tagTargetField(it, k, updateHead));
  } else if (k === 'recent') {
    box.append(recentField(it, updateHead));
  } else if (k !== 'steps') {
    const placeholders = { ...Object.fromEntries(LIB_KINDS.map(lk => [lk, 'Search ' + K(lk).many + ', e.g. ' + K(lk).eg])), press: 'Item path, e.g. Tool:Masking:Clear', set: 'Item path, e.g. Draw:Draw Size', toggle: 'Item path, e.g. Transform:Activate Symmetry', capture: 'The ZBrush folder in your Pictures folder', tool: 'D:\\Models\\Hero.ztl', project: 'D:\\Projects\\Hero.zpr, or a folder', layout: 'D:\\Layouts\\Sculpt.cfg', menu: 'Pick a menu' };
    let touched = false;                                   // "required" hints wait until the field has been edited or left once
    let inp, openBtn = null;
    const isFile = FILE_KINDS.includes(k);                 // a path to a file on this PC, with Browse buttons and no ZBrush path suggestions
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
      inp = textInput(targetOf(it), v => { touched = true; it[k] = v.trim(); commit(); updateHint(); updateHead(); }, { mono: !isLib(k), placeholder: placeholders[k], focus: 'target', label: k === 'capture' ? 'Folder' : isFile ? FILE_LABEL[k] : 'Target' });
      inp.addEventListener('change', () => { it[k] = inp.value.trim(); inp.value = it[k]; commit(); updateHint(); });
      inp.addEventListener('blur', () => { touched = true; updateHint(); });
      if (k === 'capture') {
        // A folder has no suggestions from ZBrush's paths. Browse... fills the field by firing the same input event typing does.
        openBtn = h('button', { class: 'btn small', type: 'button', onclick: async () => {
          let picked = null;
          try { picked = await call('choose_folder'); } catch (e) { toast('Could not open the folder dialog: ' + e.message, { tone: 'warn' }); return; }
          if (typeof picked !== 'string' || !picked.trim()) return;                 // cancelled: nothing changes
          inp.value = picked.trim(); inp.dispatchEvent(new Event('input'));
        } }, icon('folder', 13), 'Browse...');
      } else if (isFile) {
        // Browse... fills the field the same way typing does. Cancelling changes nothing.
        const browse = (text, dlg, args, withIcon) => h('button', { class: 'btn small', type: 'button', onclick: async () => {
          let picked = null;
          try { picked = await call(dlg, ...args); } catch (e) { toast('Could not open the ' + (dlg === 'choose_folder' ? 'folder' : 'file') + ' dialog: ' + e.message, { tone: 'warn' }); return; }
          if (typeof picked !== 'string' || !picked.trim()) return;               // cancelled: nothing changes
          inp.value = picked.trim(); inp.dispatchEvent(new Event('input'));
        } }, withIcon ? icon('folder', 13) : null, text);
        openBtn = k !== 'project' ? browse('Browse...', 'choose_file', [k], false)           // only a project can be a folder
          : [browse('Browse file...', 'choose_file', ['project'], false), browse('Browse folder...', 'choose_folder', [], true)];
      } else combo(inp, q => matchOpts(isLib(k) ? libOpts(k) : pathOpts(), q), { thumb: isLib(k) ? k : null, mono: !isLib(k) });
    }
    const tlabel = isLib(k) ? KIND[k].label : { press: 'Button path', set: 'Slider or value path', toggle: 'Switch path', capture: 'Folder', menu: 'Submenu', ...FILE_LABEL }[k];
    const wrap = h('div', { class: 'target-row' + (k === 'capture' || isFile ? ' browse-under' : '') }, isLib(k) ? h('span', { class: 'tthumb' }) : null, inp, openBtn);
    box.append(field(tlabel, wrap, hintEl));
    function updateHint() {
      const v = targetOf(it).trim(); hintEl.className = 'fhint'; hintEl.replaceChildren();
      if (!v && touched && k !== 'capture') { hintEl.classList.add('bad'); hintEl.append('A target is required. '); }     // an empty folder is the default one
      if (isLib(k)) {
        const tt = $('.tthumb', wrap); if (tt) tt.replaceChildren(thumb(v || null, { size: 30, kind: k }));
        const L = lib(k), W = K(k);
        if (L.state === 'loading' || L.state === 'idle') hintEl.append('Reading your ' + W.one + ' library...');
        else if (L.state === 'error') { hintEl.classList.add('warn'); hintEl.append(`Your ${W.one} library could not be read: `, linkBtn('see Library', () => { S.lib.kind = k; showScreen('library'); }), '.'); }
        else if (!L.zbrushFound && !L.sources.some(s => s.added)) { hintEl.classList.add('warn'); hintEl.append('ZBrush was not found: ', linkBtn('see Setup', () => showScreen('setup')), '.'); }
        else if (v && L.items.length && !L.byName.has(nameKey(v))) { hintEl.classList.add('warn'); hintEl.append(`Not found in your ${W.one} folders. ZBrush can still select it if it is loaded there; a picture needs ${W.files} with this name.`); }
        else if (!v) hintEl.append('Type to search your library.');
      } else if (k === 'menu') {
        const t = menuOf(v);
        if (openBtn) openBtn.disabled = !t || v === S.menuId;
        if (t) hintEl.append('Opens ', h('b', null, t.title || v), ` (${plural(t.items.length, 'item')}). `, linkBtn('Open it', () => openSubmenu(v)));
        else {
          if (v) { hintEl.classList.add('bad'); hintEl.append('No menu with this id. '); }
          hintEl.append(h('button', { class: 'link', type: 'button', onmousedown: e => e.preventDefault(), onclick: () => {
            const nid = uniqueId(it.label || v || 'submenu'), keep = S.menuId, mi = S.itemIdx;
            S.cfg.menus[nid] = { title: it.label || (v ? v : 'Submenu'), keep_slots: true, items: [] };
            it.menu = nid; S.menuId = keep; S.itemIdx = mi; commit({ inspector: true }); toast('Created an empty submenu. Open it to add items.', { action: { text: 'Open', fn: () => { if (S.menuId === keep) openSubmenu(nid, mi); else selectMenu(nid); } } });
          } }, 'Create a new submenu'));
        }
      } else if (k === 'capture') {
        hintEl.append(v ? 'Each capture is a PNG in this folder, named by the time. The folder is made if it is missing.' : 'Empty: captures go to the ZBrush folder in your Pictures folder.');
      } else if (isFile) {
        hintEl.append(k === 'tool' ? 'Loads this tool into the Tool palette.' : k === 'layout' ? 'Loads this UI layout. It lasts until ZBrush closes, unless you press Store Config in ZBrush (Preferences > Config).' : 'Opens this project. Give a folder to always open its newest project. ZBrush asks first if the open project has unsaved changes.');
      } else {
        const s = S.suggestions.find(x => x.path.replace(/\s/g, '').toLowerCase() === v.replace(/\s/g, '').toLowerCase());
        if (s) hintEl.append('Known item: ' + s.source);
        else if (!v) hintEl.append('Type to see suggestions from your ZBrush hotkeys, your macros and a built-in list, or paste any ZBrush item path.');
        else hintEl.append('Custom path. ZBrush item paths ignore case.');
      }
    }
    updateHint();
    R.itemHint = updateHint;
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
    box.append(field('Steps', buildSteps(it), 'Steps can select brushes, alphas, materials and textures, press buttons, set values, flip switches, save captures, load tools and layouts, and open projects (no submenus).'));
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
  const style = styleField(m, i, it);
  if (style) box.append(style);
  return box;
}

/* The Style field of an item: what its own style (item.style, the look keys a slot can set) changes, a button to edit it on the Look screen's slot
   level and one to remove it. Simple mode shows it, read-only, only for an item that has a style (null when there is nothing to show). */
const SHAPE_NAME = { circle: 'Circle', rounded: 'Rounded square', squircle: 'Squircle', hexagon: 'Hexagon', octagon: 'Octagon', diamond: 'Diamond' };
function styleChipText(key, v) {
  const pct = x => Math.round(x * 100) + '%';
  switch (key) {
    case 'slot_shape': return SHAPE_NAME[v] || String(v);
    case 'slot_corner': return 'Corners ' + pct(v);
    case 'border_width': return 'Rim ' + v + ' px';
    case 'icon_scale': return 'Icon ' + pct(v);
    case 'label_color': return 'Label ' + v;
    case 'glow_color': return 'Glow ' + v;
    case 'size': return v > 1 ? 'Larger' : v < 1 ? 'Smaller' : 'Size ' + pct(v);
    case 'fill_color': return 'Fill ' + v;
    case 'border_color': return 'Rim ' + v;
    default: return key;
  }
}
/* The settings an item's style has of its own, as chip texts: a value that says what the menu gives anyway is not a setting. */
function styleChips(menuId, i) {
  const m = menuOf(menuId), it = m && m.items && m.items[i];
  if (!it || !isPlainObj(it.style) || !window.ZLook) return [];
  let keys = [];
  try { keys = ZLook.settings(S.cfg, { level: 'menu', menu: menuId, slot: i }, lookCtx()); } catch (e) { keys = []; }
  return keys.filter(k => k !== 'colors' && !(typeof it.style[k] === 'string' && it.style[k] === '')).map(k => styleChipText(k, it.style[k]));
}
function styleField(m, i, it) {
  const chips = styleChips(S.menuId, i), has = isPlainObj(it.style) && Object.keys(it.style).length > 0;
  const line = chips.length ? h('div', { class: 'style-chips' }, chips.map(t => h('span', { class: 'tag' }, t))) : h('div', { class: 'locked-line' }, has ? 'Its own style says nothing the menu does not already say' : "Follows the menu's look");
  if (!isFull()) return has ? field('Style', line, ['Set in Full mode. ', linkBtn('Edit in Full mode', () => setMode('full'))]) : null;
  const usable = slotIdx(S.menuId).includes(i);
  const edit = h('button', { class: 'btn small', type: 'button', disabled: !usable, title: usable ? 'Open the Look screen at this slot' : 'This menu has nothing complete yet, so it has no ring',
    onclick: () => goToProblem({ kind: 'look', level: 'menu', menuId: S.menuId, slot: i, key: null, group: null }) }, icon('look', 12), 'Edit in Look');
  const reset = h('button', { class: 'btn small', type: 'button', disabled: !has, onclick: () => {
    sealSnap(); delete it.style; commit({ inspector: true });
    undoToast('Removed the style of "' + itemLabel(it) + '"');
  } }, icon('undo', 12), 'Reset style');
  return field('Style', h('div', { class: 'style-box' }, line, h('div', { class: 'btn-row' }, edit, reset)), 'The shape, size, colours and glow of this slot on its own. Anything it does not set follows the look of the menu.');
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

const STEP_KINDS = ['brush', 'alpha', 'material', 'texture', 'press', 'set', 'toggle', 'capture', 'tool', 'project', 'layout'];
function buildSteps(it) {
  const host = h('div', { class: 'steps' });
  const render = f => {                                          // f: { j, k } the control to focus afterwards (step j; k = type, up, down or rm)
    host.replaceChildren();
    if (!Array.isArray(it.steps)) it.steps = [];
    it.steps.forEach((st, j) => {
      const sk = kindOf(st);
      const sel = h('select', { class: 'inp sel', 'aria-label': 'Step ' + (j + 1) + ' type', onchange: () => {
        const nk = sel.value, was = targetOf(st), keep = nsOf(nk) === nsOf(sk) ? was : '', lost = [];
        if (hasText(was) && !hasText(keep)) lost.push(`the ${TARGET_NOUN[sk]} "${was.trim()}"`);
        if (sk === 'set' && nk !== 'set' && hasText(st.value)) lost.push(`the value ${st.value}`);
        sealSnap();
        it.steps[j] = makeItem(nk, keep); commit({ inspector: false }); render({ j, k: 'type' });
        if (lost.length) undoToast(`Step ${j + 1} is now ${KIND[nk].label}. Dropped ${joinList(lost)}.`, { ms: 6500 });
      } },
        STEP_KINDS.map(x => h('option', { value: x, selected: x === sk }, KIND[x].label)));
      const tin = textInput(targetOf(st), v => { st[sk] = v; commit(); }, { mono: !isLib(sk), placeholder: isLib(sk) ? KIND[sk].label + ' name' : sk === 'capture' ? 'The ZBrush folder in your Pictures folder' : sk === 'tool' ? 'D:\\Models\\Hero.ztl' : sk === 'project' ? 'D:\\Projects\\Hero.zpr, or a folder' : sk === 'layout' ? 'D:\\Layouts\\Sculpt.cfg' : 'Item path', label: 'Step ' + (j + 1) + ' target' });
      tin.addEventListener('change', () => { st[sk] = tin.value.trim(); tin.value = st[sk]; commit(); });
      tin.classList.add('stgt');
      if (isLib(sk)) ensureLib(sk);
      if (sk !== 'capture' && !FILE_KINDS.includes(sk)) combo(tin, q => matchOpts(isLib(sk) ? libOpts(sk) : pathOpts(), q), { thumb: isLib(sk) ? sk : null, mono: !isLib(sk) });   // a folder has no ZBrush path suggestions
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
          actBtn('up', iconBtn('up', 'Move step up', () => { if (j > 0) { [it.steps[j - 1], it.steps[j]] = [it.steps[j], it.steps[j - 1]]; commit(); render({ j: j - 1, k: 'up' }); } })),
          actBtn('down', iconBtn('down', 'Move step down', () => { if (j < it.steps.length - 1) { [it.steps[j + 1], it.steps[j]] = [it.steps[j], it.steps[j + 1]]; commit(); render({ j: j + 1, k: 'down' }); } })),
          actBtn('rm', iconBtn('trash', 'Remove step', e => { if (e.detail > 1) return; it.steps.splice(j, 1); commit(); render({ j: Math.min(j, it.steps.length - 1), k: 'rm' }); }, 'danger'))));
      host.append(row);
    });
    if (!it.steps.length) host.append(h('div', { class: 'fhint bad' }, 'Add at least one step.'));
    host.append(h('div', { class: 'step-add' }, h('span', { class: 'micro' }, 'Add'), STEP_KINDS.map(x =>
      h('button', { class: 'btn small', type: 'button', onclick: () => { it.steps.push(makeItem(x, '')); commit(); render(); const ins = $$('.step .inp.mono, .step input', host); const last = $$('.step', host).pop(); if (last) $$('input', last)[0].focus(); } }, icon(KIND[x].icon, 12), KIND[x].label))));
    if (f) {                                                      // the control that had focus was rebuilt: focus its successor
      const row = $$('.step', host)[f.j], c = row && (f.k === 'type' ? $('select', row) : $(`[data-act="${f.k}"]`, row));
      const t = c || $('.step-add .btn', host);
      if (t) t.focus();
    }
  };
  const actBtn = (act, b) => { b.dataset.act = act; return b; };
  render();
  return host;
}

/* ---------- menu properties */
/* Whether a mouse button or pen is down right now (a field left by a click sees its change event before the click). */
let pointerHeld = false;
const menuMore = {};      // menu id -> whether the Menu tab's More section is open, when the person chose; the panel is rebuilt by every commit
addEventListener('pointerdown', () => { pointerHeld = true; }, true);
addEventListener('pointerup', () => { pointerHeld = false; }, true);
addEventListener('pointercancel', () => { pointerHeld = false; }, true);

/* The Look section of the Menu tab: which look the menu uses (the ring's, a built-in or one of yours), and a way into the Look screen.
   A menu with settings of its own shows them as one read-only line, "Custom (2 changes)" or "Soft + 2 changes". */
function buildMenuLook(id) {
  const ctx = lookCtx(), T = { level: 'menu', menu: id }, m = menuOf(id);
  const sum = ZLook.summary(S.cfg, T, ctx), glob = ZLook.summary(S.cfg, { level: 'global' }, ctx);
  const mine = Object.keys(ZLook.userLooks(S.cfg)).filter(n => ZLook.nameProblem(n, ctx) === '');
  const custom = sum.count > 0 || (!!sum.preset && !sum.known);
  const current = custom ? '~custom' : sum.preset;
  const sel = h('select', { class: 'inp sel', 'aria-label': 'Look for this menu', dataset: { fk: 'menu:look' }, onchange: () => {
    const v = sel.value;
    if (v === '~custom') return;
    let n = 0;
    if (v === '') { n = ZLook.ownCount(S.cfg, T, ctx); delete m.look; } else n = ZLook.usePreset(S.cfg, T, v, { keep: false }, ctx);
    commit({ inspector: true });
    const what = v === '' ? 'This menu follows the ring’s look' : ZLook.labelOf(v, ctx) + ' is the look of this menu';
    undoToast(what + (n ? '. ' + clearedText(n) + '.' : '.'));
  } },
  custom ? h('option', { value: '~custom', selected: true, disabled: true }, sum.text) : null,
  h('option', { value: '', selected: current === '' }, 'Same as all menus (Global: ' + glob.text + ')'),
  h('optgroup', { label: 'Built-in' }, ((ctx.looks && ctx.looks.builtin) || []).map(b => h('option', { value: b.id, selected: current === b.id }, b.label))),
  mine.length ? h('optgroup', { label: 'Yours' }, mine.map(n => h('option', { value: n, selected: current === n }, n))) : null);
  const hint = h('div', { class: 'fhint' }, custom
    ? 'This menu has settings of its own' + (sum.preset && sum.known ? ' on top of ' + ZLook.labelOf(sum.preset, ctx) : '') + '. Change them in Look, or clear them to pick a look here.'
    : sum.preset ? 'Only this menu uses ' + sum.text + '. The other menus keep following the look for all menus.' : 'This menu follows the look chosen for all menus. Pick another to give this menu its own.');
  const edit = h('button', { class: 'btn', type: 'button', onclick: () => goToProblem({ kind: 'look', level: 'menu', menuId: id, key: null, group: null }) }, icon('look', 13), 'Edit in Look');
  const clearBtn = h('button', { class: 'btn', type: 'button', disabled: sum.count === 0, title: sum.count ? 'Remove the settings this menu has of its own' : 'This menu has no settings of its own', onclick: () => {
    const n = ZLook.clearAll(S.cfg, T, ctx);
    commit({ inspector: true });
    undoToast(clearedText(n) + '.');
  } }, icon('undo', 13), 'Clear own settings');
  return h('div', { class: 'field' }, sel, hint, h('div', { class: 'btn-row' }, edit, clearBtn));
}

function buildMenuProps() {
  const m = curMenu(), id = S.menuId;
  const box = h('div', { class: 'insp' });
  if (!m) return emptyState('menus', 'No menu selected', '');
  const full = isFull();
  // The id follows the title when the field is left, not on every key: the panel is rebuilt around the new id.
  const title0 = m.title || '';
  const titleInp = textInput(m.title || '', v => { m.title = v; commit(); if (R.head) R.head(); }, { placeholder: id, label: 'Menu title',
    onChange: () => {
      const nid = idForTitle(id, title0);
      if (!nid) return;
      // The panel is rebuilt around the new id. With a mouse button down (the click that left the field), that waits
      // for the click to land, or the button under the pointer would be swapped out and the click lost; then the
      // keyboard goes back to the same field in the new panel.
      const run = () => {
        if (!hasMenu(id) || hasMenu(nid)) return;            // changed meanwhile (the click deleted or renamed it)
        const fa = document.activeElement, label = fa && fa.isConnected && box.contains(fa) && fa.getAttribute('aria-label');
        moveMenuId(id, nid); commit({ inspector: true }); if (R.head) R.head();
        const back = label && $(`.insp [aria-label="${label}"]`);
        if (back) back.focus();
      };
      if (pointerHeld) addEventListener('pointerup', () => setTimeout(run, 0), { once: true, capture: true });
      else run();
    } });
  box.append(sectionTitle('Menu', 'Shown in the list and at the ring centre'), field('Title', titleInp));
  const idErr = h('div', { class: 'fhint bad id-err', role: 'alert', hidden: true });
  const idInp = textInput(id, () => {}, { mono: true, label: 'Menu id' });
  let idTimer = null;
  const idShow = msg => { clearTimeout(idTimer); idTimer = null; idErr.textContent = msg || ''; idErr.hidden = !msg; idInp.classList.toggle('bad', !!msg); };
  idInp.addEventListener('input', () => idShow(menuIdProblem(id, idInp.value)));          // live: red as soon as it is wrong, clear as soon as it is right
  const idCommit = () => {
    const had = document.activeElement === idInp;
    const bad = renameMenuId(id, idInp.value);                                             // null: renamed (the panel is rebuilt) or unchanged
    if (!bad) {
      idShow(''); if (idInp.value !== id && idInp.isConnected) idInp.value = id;
      if (!idInp.isConnected) {                                                            // renamed: the panel was rebuilt, so the keyboard goes to the new Id field, else to the menu's row
        const fa = document.activeElement;
        if (had) { const ni = $('.insp input[aria-label="Menu id"]'); if (ni) ni.focus(); }
        else if (R.focusMenu && (!fa || fa === document.body || !fa.isConnected)) R.focusMenu();
      }
      return;
    }
    idInp.value = id; idShow(bad); idInp.classList.remove('bad');                          // back to the old id; the reason stays for a moment
    idTimer = setTimeout(() => idShow(''), 3000);
  };
  idInp.addEventListener('change', idCommit);
  idInp.addEventListener('keydown', e => { if (e.key === 'Escape') { e.stopPropagation(); idInp.value = id; idShow(''); } });
  const idNotes = [h('div', { class: 'fhint' }, 'Used to link submenus. Renaming updates the items that open this menu.')];
  if (m.items.some(x => kindOf(x) === 'auto')) idNotes.push(h('div', { class: 'fhint' }, 'Renaming resets the learned auto slots for this menu.'));
  const more = [];                                                                        // Full: Id, Look, Open animation and Fan out, folded under More
  if (full) more.push(field('Id', idInp, h('div', { class: 'id-notes' }, idErr, ...idNotes)));

  // The file order decides: of two menus with one hotkey, the first opens (and any menu beats the browser).
  const clash = owner => {
    if (owner === BROWSER) return 'Also used by the browser, which will not open with it.';
    if (owner === PROFILE) return 'Also used by the next-profile hotkey, which will not step profiles with it.';
    const ids = Object.keys(S.cfg.menus);
    return ids.indexOf(owner) < ids.indexOf(id) ? `Also used by ${ownerName(owner)}, which comes first and wins; this menu will not open with it.` : `Also used by ${ownerName(owner)}, which will not open with it.`;
  };
  const owner0 = m.hotkey ? hotkeyOwner(m.hotkey, id) : null;
  let syncSwallow = () => {};
  const hk = hotkeyField({ what: 'Hotkey for this menu', value: m.hotkey || '', placeholder: 'No hotkey (submenu only)', onChange: str => {
    if (str) m.hotkey = str; else delete m.hotkey;
    const owner = str ? hotkeyOwner(str, id) : null;
    if (owner) hk.say(clash(owner), 'warn');
    syncSwallow();
    commit(); if (R.head) R.head();
  } });
  box.append(field('Hotkey', hk, m.hotkey ? 'Hold or tap this key in ZBrush to open the ring. Click the field and press a combination to change it.' : 'Without a hotkey this menu can only be opened as a submenu from another menu.'));
  if (owner0) hk.say(clash(owner0), 'warn');

  box.append(h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Keep slots in place'),
    h('div', { class: 'fhint' }, 'Deleting leaves an empty slot and dropping swaps two slots, so the other items never move.')),
    toggleSwitch(keeps(m), v => setKeepSlots(S.menuId, v), 'Keep slots in place')));

  const swallowSw = toggleSwitch(m.swallow !== false, v => { if (v) delete m.swallow; else m.swallow = false; commit(); }, 'Swallow hotkey');
  const swallowNeed = h('div', { class: 'fhint warn' }, 'Set a hotkey first.');
  syncSwallow = () => { const none = !m.hotkey; $('input', swallowSw).disabled = none; swallowSw.title = none ? 'Set a hotkey first' : ''; swallowNeed.hidden = !none; };   // a submenu has no key to hide
  syncSwallow();
  if (full) box.append(h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Swallow hotkey'),
    h('div', { class: 'fhint' }, 'Hides the key from ZBrush while the ring is in use, so it does not also trigger ZBrush\'s own shortcut for that key. Turn off if you want the key to keep working in ZBrush too.'), swallowNeed),
    swallowSw));

  if (!full && menuFullSet(m)) {
    const set = [m.fan === true ? 'Fan out' : '', m.swallow === false ? 'Swallow hotkey' : '', MODE.lookHasOwn(m.look) ? 'A look with its own settings' : ''].filter(Boolean);
    box.append(h('div', { class: 'fhint' }, joinList(set) + (set.length === 1 ? ' is' : ' are') + ' set for this menu in Full mode. ', linkBtn('Switch to Full mode', () => setMode('full'))));
  }
  const refs = referrers(id);
  if (full) box.append(sectionTitle('Used by'), refs.length
    ? h('div', { class: 'refs' }, refs.map(r => h('button', { class: 'chip cyan', type: 'button', title: 'Go to this item', onclick: () => { selectMenu(r.menuId); selectItem(r.index); } },
      icon('k_menu', 12), (menuOf(r.menuId).title || r.menuId) + ' / ' + (r.index + 1))))
    : h('div', { class: 'fhint' }, m.hotkey ? 'Opened from ZBrush by its hotkey.' : 'Nothing opens this menu yet. Add a Submenu item in another menu that points to it.'));

  if (full && S.opts && S.opts.looks) more.push(sectionTitle('Look', 'Shapes, hub, glow and colours of this menu'), buildMenuLook(id));

  const animTitle = a => { const t = typeof a === 'string' ? a : String(a === undefined || a === null ? '' : a); return t ? t[0].toUpperCase() + t.slice(1) : ''; };
  const ringAnim = () => ring().animation || S.defaults.animation;
  const animBox = [sectionTitle('Open animation'), h('div', { class: 'field' }, h('div', { class: 'fhint' },
    m.animation ? 'Opens with ' + animTitle(m.animation) + '. ' : 'Opens like all menus (' + animTitle(ringAnim()) + '). ',
    S.opts && S.opts.looks ? linkBtn('Edit in Look', () => goToProblem({ kind: 'look', level: 'menu', menuId: id, key: 'animation', group: 'opening' })) : null))];
  if (full) {
    more.push(...animBox, sectionTitle('As a submenu'), h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Fan out when opened from another menu'),
      h('div', { class: 'fhint' }, 'Instead of a new ring, the items spread out around this menu\'s slot and the ring stays in view.' + (m.hotkey ? ' This only applies when it is opened as a submenu; its hotkey still opens a ring.' : ''))),
      toggleSwitch(m.fan === true, v => { if (v) m.fan = true; else delete m.fan; commit(); }, 'Fan out when opened from another menu')));
    // Open when something in it is set, unless the person has chosen: the choice is kept per menu, outside the panel, which a commit rebuilds
    const moreSum = () => {
      const n = [!!m.look && (typeof m.look !== 'object' || Object.keys(m.look).length > 0), !!m.animation, m.fan === true].filter(Boolean).length;
      return { n, text: 'Look, open animation, fan out' + (n ? ' · ' + n + ' set' : '') };
    };
    const ms = moreSum();
    const openNow = own(menuMore, id) ? menuMore[id] : ms.n > 0;
    if (openNow) menuMore[id] = true;                           // built open by the rule: it stays open until the person closes it
    const sec = foldSection({ id: 'menu-more', flat: true, title: 'More', summary: ms.text, open: openNow,
      onToggle: v => { menuMore[id] = v; foldSum(sec, moreSum().text); } }, ...more);      // the fan switch does not rebuild the panel, so the summary is made again on every toggle
    box.append(sec);
  } else box.append(...animBox);
  box.append(sectionTitle('Manage'), h('div', { class: 'btn-row' },
    h('button', { class: 'btn', type: 'button', onclick: () => dupMenu(id) }, icon('copy', 13), 'Duplicate'),
    h('button', { class: 'btn', type: 'button', title: 'Save this menu and the submenus it opens to a file you can share', onclick: e => ioRun([e.currentTarget], () => exportMenu(id)) }, icon('folder', 13), 'Export menu...'),
    h('button', { class: 'btn danger-o', type: 'button', onclick: () => deleteMenu(id) }, icon('trash', 13), 'Delete menu')));
  return box;
}

/* ================================================================== tags */
/* Tags live in tags.json and the backend writes it as they change, so they are not part of Save, Revert or undo.
   S.tags / S.tagMap / S.itemTags mirror the last snapshot any tag call returned (see webapi.TagApi). */
const TAG_PALETTE_FALLBACK = ['#A8DF23', '#C77DFF', '#FFD166', '#5EEAD4', '#F472B6', '#E8413C', '#F86B33', '#4DC8E9'];   // as tags.PALETTE in tags.py
const browsers = new Map();            // browser state object (S.lib, S.dock) -> its live browser, so a tag change can repaint it
let tagMgr = null, tagPick = null;     // repaint hooks of the open tag manager and tag picker
const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : /(s|sh|ch|x)$/.test(w) ? 'es' : 's');
/* What a tag's count in the picker and the manager counts (the chips count one tab: see renderTags). */
const allKindsText = n => plural(n, 'item') + ' across brushes, alphas, materials and textures';

const tagsOf = (kind, name) => { const l = S.itemTags[tagKey(kind, name)]; return l ? l.filter(k => S.tagMap.has(k)) : []; };
const isFav = (kind, name) => tagsOf(kind, name).includes(FAV);
/* The order a tab's Favourites were dragged into, as nameKey()s; empty while the tab is most used first (see favorder.js). */
const favOrderOf = kind => { const o = S.favOrder[kind]; return Array.isArray(o) ? o : []; };
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
      const fanOrder = cur === FAV && favOrderOf('brush').length ? 'brushes first, in your order' : 'brushes first (most used first)';
      if (t && !n) { hint.classList.add('warn'); hint.append('No item has this tag yet; the slot stays empty until one does. '); }
      else if (n > ringNum('tag_limit')) hint.append('Opens a fan of the first ' + (ringNum('tag_limit') - 1) + ' of ', h('b', null, plural(n, 'item')), ': ' + fanOrder + ', then alphas, materials and textures. A fan holds ' + ringNum('tag_limit') + ' slots, so the last one, More..., opens the browser on this tag. ');
      else hint.append('Opens a fan of ', h('b', null, plural(n, 'item')), ': ' + fanOrder + ', then alphas, materials and textures. A fan holds at most ' + ringNum('tag_limit') + ' slots. ');
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

/* The Shows select of a Recent item: projects, tools or both (item.recent). A value the loader does not know is kept and shown as unknown. */
function recentField(it, updateHead) {
  const cur = String(it.recent ?? '');
  const hint = h('div', { class: 'fhint' });
  const paintHint = () => {
    hint.className = 'fhint'; hint.replaceChildren();
    if (!own(RECENT, it.recent)) { hint.classList.add('bad'); hint.append('Pick what the fan shows. '); return; }
    hint.append('Opens a fan of the ' + RECENT[it.recent].what + ' ZBrush opened last, newest first, from its own list of recent files. The fan holds at most ' + ringNum('tag_limit') + ' slots (Tag fan slots). A pick opens the file as a Project or Tool item does.');
  };
  const sel = h('select', { class: 'inp sel', 'aria-label': 'Shows', dataset: { focus: 'target' }, onchange: () => { it.recent = sel.value; commit(); paintHint(); updateHead(); } },
    !own(RECENT, cur) ? h('option', { value: cur }, `Unknown '${cur}'`) : null,
    Object.keys(RECENT).map(v => h('option', { value: v }, RECENT[v].shows)));
  sel.value = cur;
  paintHint();
  return field('Shows', sel, hint);
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
/* How many ring items point at a tag ({"tag": key}). The browser window holds no menus, so it asks the backend (get_tag_uses, which reads
   radial.json) when the delete confirmation is about to show: see loadTagUses. */
let tagUses = Object.create(null);
async function loadTagUses() {
  if (!POPOUT) return;
  let r = null;
  try { r = await call('get_tag_uses'); } catch (e) { r = null; }
  tagUses = Object.assign(Object.create(null), r && r.ok && r.uses && typeof r.uses === 'object' ? r.uses : null);
}
function tagRingUses(key) {
  if (POPOUT) return tagUses[key] || 0;
  let n = 0;
  for (const m of Object.values(S.cfg.menus)) for (const it of (m.items || [])) if (it && (it.tag === key || it.browser === key)) n++;
  return n;
}

/* After a merge: points the ring items that used tag `from` ({tag} and {browser} items) at tag `to`, as one step of the editor's history
   (Ctrl+Z puts them back). The merge itself is in tags.json and not part of Undo. Returns how many items changed. */
function retargetTag(from, to) {
  if (POPOUT || !S.cfg) return 0;
  const hits = [];
  for (const m of Object.values(S.cfg.menus)) for (const it of (m.items || [])) if (it && (it.tag === from || it.browser === from)) hits.push(it);
  if (!hits.length) return 0;
  sealSnap();
  for (const it of hits) { if (it.tag === from) it.tag = to; if (it.browser === from) it.browser = to; }
  commit({ inspector: true }); sealSnap();
  return hits.length;
}

/* Takes a get_tags answer or a changing call's answer. A changing call reports its own failure in `error`, which is not a
   problem with the file, so only get_tags answers (mutated = false) set S.tagsErr. Returns true when anything on screen changed. */
let tagSeq = 0, tagSeqApplied = 0;       // tag calls are numbered when they start: an answer to an older call never replaces a newer one
function applyTagSnapshot(res, mutated = false, seq = ++tagSeq) {
  if (!res || typeof res !== 'object') return false;
  // Answers can land out of order (two picker clicks, a focus reload over a write). The order of the calls decides, not the file's
  // time: a tags.json that was deleted or put back from a copy has an older time and is still the newest state.
  if (seq < tagSeqApplied) return false;
  tagSeqApplied = seq;
  if (res.unchanged) { S.tagMtime = res.mtime_ns; return false; }
  if (!Array.isArray(res.tags)) return false;
  const err = mutated ? (res.ok ? '' : S.tagsErr) : (res.error ? String(res.error) : '');
  const sig = JSON.stringify([res.tags, res.items || {}, res.favourite_order || {}]);
  const changed = !S.tagsLoaded || sig !== S._tagSig || err !== S.tagsErr;
  const keysChanged = S.tagsLoaded && S.tags.map(t => t.key).join('\n') !== res.tags.map(t => t.key).join('\n');   // a tag came or went: slots that use it are right or wrong now
  if (err && err !== S.tagsErr) toast(err, { tone: 'warn', ms: 5000 });
  S.tags = res.tags; S.tagMap = new Map(res.tags.map(t => [t.key, t]));
  S.itemTags = res.items && typeof res.items === 'object' ? res.items : {};
  S.favOrder = res.favourite_order && typeof res.favourite_order === 'object' ? res.favourite_order : {};
  const favTag = S.tagMap.get(FAV);                         // the star's colour follows the Favourites tag (its colour can be changed)
  if (favTag && /^#[0-9a-f]{6}$/i.test(favTag.color || '')) document.documentElement.style.setProperty('--fav', favTag.color);
  else document.documentElement.style.removeProperty('--fav');
  if (Array.isArray(res.palette) && res.palette.length) S.palette = res.palette;
  const pathMoved = !!res.path && !!S.tagsPath && String(res.path) !== S.tagsPath;   // another profile's tags file: its Recent list differs too
  if (res.path) S.tagsPath = String(res.path);
  S.tagMtime = res.mtime_ns === undefined ? S.tagMtime : res.mtime_ns;
  S.tagsErr = err; S._tagSig = sig; S.tagsLoaded = true;
  if (changed) tagsChanged(keysChanged);
  if (pathMoved) reloadUsage();
  return changed;
}
async function loadTags(force = false) {
  let res = null;
  const seq = ++tagSeq;
  try { res = await call('get_tags', force ? null : S.tagMtime, S.tagsPath); } catch (e) { res = null; }   // the path too: a switch between two profiles without a tags file is not "unchanged"
  applyTagSnapshot(res, false, seq);
}
/* Every tag change goes through here: the answer carries the fresh snapshot, a refusal is toasted. A name that clashes
   (res.exists) is left to the caller, which can offer to use or merge into the other tag. */
async function tagCall(name, ...args) {
  let res;
  const seq = ++tagSeq;
  try { res = await call(name, ...args); } catch (e) { res = { ok: false, error: 'Could not save the tags: ' + ((e && e.message) || e) }; }
  if (!res || typeof res !== 'object') res = { ok: false, error: 'Could not save the tags.' };
  applyTagSnapshot(res, true, seq);
  if (!res.ok && !res.exists) toast(res.error || 'That tag change did not work.', { tone: 'warn', ms: 4500 });
  return res;
}
/* The rail dots on Status and Settings, looked at again a moment after the tags changed (one quiet look, however many changes come). */
const railDotsSoon = debounce(() => { if (S.ready && !S.fatal) { refreshAppDown(); refreshZsBadge(); } }, 600);
function tagsChanged(keysChanged = false) {
  if (keysChanged && !POPOUT && S.cfg && S.ready) { validateSoon(); railDotsSoon(); }   // the problems pill and the row markers name tags that may be gone (or back)
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
    return h('button', { class: 'tp-row' + (st === 'all' ? ' on' : ''), type: 'button', role: 'menuitemcheckbox', title: allKindsText(t.count), 'aria-checked': st === 'all' ? 'true' : st === 'some' ? 'mixed' : 'false', dataset: { k: t.key },
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
      if (!c) { hex.classList.add('bad'); msg.dataset.for = 'colour'; msg.classList.add('bad'); msg.textContent = 'Use a colour like #A8DF23.'; msg.hidden = false; return; }
      hex.classList.remove('bad'); clearColourMsg(); setColor(c);
    });
    const clearColourMsg = () => { if (msg.dataset.for === 'colour') { delete msg.dataset.for; msg.classList.remove('bad'); msg.hidden = true; msg.textContent = ''; } };
    hex.addEventListener('input', () => { hex.classList.remove('bad'); clearColourMsg(); });
    const swatches = () => (S.palette || TAG_PALETTE_FALLBACK).map(c => h('button', { class: 'tm-pc', type: 'button', style: { '--tag': c }, title: c, 'aria-label': 'Colour ' + c, 'aria-pressed': c.toLowerCase() === tag.color.toLowerCase() ? 'true' : 'false', onclick: () => setColor(c) }));
    sw.addEventListener('click', () => { const open = pal.hidden; pal.hidden = !open; sw.setAttribute('aria-expanded', open ? 'true' : 'false'); });
    pal.append(h('div', { class: 'tm-pcs' }), hex);
    inp.addEventListener('change', async () => {
      const v = inp.value.trim();
      msg.hidden = true; clearColourMsg();
      if (v === tag.label) { inp.value = tag.label; return; }
      const r = await tagCall('rename_tag', tag.key, v);
      if (r.ok) return;
      inp.value = tag.label;
      const other = r.exists && S.tagMap.get(r.exists);
      if (other) {
        msg.replaceChildren('A tag called "' + other.label + '" already exists. ',
          h('button', { class: 'link', type: 'button', onclick: async () => {
            await loadTagUses();                              // the browser window reads the ring items from radial.json just now
            const from = tag.label, srcKey = tag.key, uses = tagRingUses(srcKey);
            const useText = !uses ? '' : ' ' + plural(uses, 'ring item') + (uses === 1 ? ' uses' : ' use') + ' "' + from + '". ' + (uses === 1 ? 'It then uses' : 'They then use') + ' "' + other.label + '" instead.'
              + (POPOUT ? ' ZOrbit changes them in radial.json now.' : ' That change is in the editor until you press Save, and Undo takes it back.');
            const ok = await modal({ title: 'Merge "' + from + '" into "' + other.label + '"?',
              body: h('p', null, 'Items tagged "' + from + '" get "' + other.label + '" instead, and "' + from + '" is removed.' + useText),
              actions: [{ text: 'Cancel', value: false, focus: true }, { text: 'Merge', value: true, kind: 'danger' }] });
            if (ok) {
              const m = await tagCall('merge_tags', srcKey, other.key);
              if (m.ok) {
                if (POPOUT) {      // no menus here: the backend has already pointed the ring items in radial.json at the kept tag
                  const moved = Number(m.ring_items) || 0;
                  toast('Merged "' + from + '" into "' + other.label + '"' + (m.ring_error ? '. ' + m.ring_error + ' Ring items that used "' + from + '" were not changed.' : moved ? '. ' + plural(moved, 'ring item') + (moved === 1 ? ' now uses' : ' now use') + ' it.' : ''),
                    { tone: m.ring_error ? 'warn' : 'ok', ms: m.ring_error ? 7000 : moved ? 4000 : 2600 });
                } else {
                  const moved = retargetTag(srcKey, other.key);       // the ring items that pointed at the removed tag
                  toast('Merged "' + from + '" into "' + other.label + '"' + (moved ? '. ' + plural(moved, 'ring item') + (moved === 1 ? ' now uses' : ' now use') + ' it. Save to keep that.' : ''), { tone: 'ok', ms: moved ? 5000 : 2600 });
                }
              }
            }
            openTagManager();                                 // the confirm replaced this dialog: bring it back
          } }, 'Merge into ' + other.label),
          ' or ', h('button', { class: 'link', type: 'button', onclick: () => { msg.hidden = true; inp.focus(); } }, 'keep them separate'), '.');
        msg.hidden = false;
      }
    });
    const remove = async () => {
      await loadTagUses();                                // the browser window reads the ring items from radial.json just now
      const uses = tagRingUses(tag.key);
      const text = (tag.count ? 'It is on ' + plural(tag.count, 'item') + (uses ? ', used by ' + plural(uses, 'ring item') : '') : 'It is not on any item' + (uses ? ', but ' + plural(uses, 'ring item') + (uses === 1 ? ' uses' : ' use') + ' it' : '')) + '. The items keep working.' + (uses ? ' Tag slots that use it go empty and Browser slots open unfiltered until you pick another tag.' : '');
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
      setText(n, plural(t.count, 'item')); n.title = allKindsText(t.count);
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
const usageFlight = Object.create(null);                                      // kind -> the get_usage call in flight, so a burst of triggers makes one call
/* Takes a get_usage or forget_recent answer. Returns true when anything the browsers show changed. */
const usageSeq = Object.create(null), usageSeqApplied = Object.create(null);                    // kind -> usage calls started / the newest one applied (as tagSeq)
function applyUsage(kind, res, seq = usageSeq[kind] = (usageSeq[kind] || 0) + 1) {
  if (!res || res.ok === false || !Array.isArray(res.recent)) return false;
  const u = usageOf(kind);
  if (seq < (usageSeqApplied[kind] || 0)) return false;       // an answer to an older call never replaces a newer one (a replaced usage.json has an older time and still wins)
  usageSeqApplied[kind] = seq;
  const scores = Object.assign(Object.create(null), res.scores && typeof res.scores === 'object' ? res.scores : null);
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
    const seq = usageSeq[kind] = (usageSeq[kind] || 0) + 1;
    try { res = await call('get_usage', kind); } catch (e) { res = null; }
    applyUsage(kind, res, seq);
  })().finally(() => { delete usageFlight[kind]; }));
}
/* Every kind a browser is showing: on window focus (the other window may have picked something) and when the popout is shown. */
function reloadUsage() { for (const k of new Set(Array.from(browsers.values()).map(b => b.kind()))) loadUsage(k); }
/* "Remove from Recent" for one or several items of a kind. */
async function forgetRecent(kind, names) {
  let res = null;
  const seq = usageSeq[kind] = (usageSeq[kind] || 0) + 1;
  try { for (const n of names) res = await call('forget_recent', kind, n); } catch (e) { res = null; }
  if (res && res.ok !== false && Array.isArray(res.recent)) applyUsage(kind, res, seq);
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
  addFolder: true,                                                 // the Add a folder button under the folders: only Studio can open the picker and write studio.json
  tools: () => h('button', { class: 'btn small', type: 'button', title: 'Open the browser in its own window', onclick: openBrowserFromButton }, icon('k_browser', 13), 'Browser'),
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
    return u ? { n: u.length, titles: Array.from(new Set(u.map(x => (menuOf(x.menuId) || {}).title || x.menuId))) } : null;
  },
};

/* The browser in its own window (the Library toolbar, the top bar): the app shows it if it is running, else a new one starts. It needs neither ZBrush nor the app. */
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
  const b = h('button', { class: 'btn small rescan-btn', type: 'button', title: 'Look for ' + K(kind).one + ' files again', dataset: { label, kind }, onclick: () => rescanLibrary(b.dataset.kind) });   // setKind moves dataset.kind, so read it now
  paintRescanBtn(b);
  return b;
}
/* Reads the folders again. A rescan that fails keeps showing the items it had (and says why); one that works says how many it found and,
   when there was a list to compare with, what changed. */
async function rescanLibrary(kind) {
  const L = lib(kind), w = K(kind);
  if (L.busy) return;
  const old = L.loaded && L.state === 'ready' && { items: L.items, sorted: L.sorted, byName: L.byName, sources: L.sources, zbrushFound: L.zbrushFound };
  await loadLibrary(kind, true);
  if (L.error) {
    const msg = L.error;
    if (old && old.items.length && L.state === 'error') {            // loadLibrary emptied the list: put back what was on show
      Object.assign(L, { items: old.items, sorted: old.sorted, byName: old.byName, sources: old.sources, zbrushFound: old.zbrushFound, error: null, state: 'ready', _tree: null, _tc: null });
      if (R.libRefresh) R.libRefresh(kind);
    }
    toast(msg || 'Could not read the ' + w.one + ' folders.', { tone: 'warn', ms: 4500 });
    return;
  }
  const n = L.items.length;
  let text = 'Found ' + plural(n, w.one);
  if (old && old.items.length && n) {
    const added = L.items.filter(b => !old.byName.has(nameKey(b.name))).length, gone = old.items.filter(b => !L.byName.has(nameKey(b.name))).length;
    text += added || gone ? [added ? ', ' + added + ' new' : '', gone ? ', ' + gone + ' gone' : ''].join('') : ', no changes';
  }
  toast(text, n ? {} : { tone: 'warn' });
}
/* What the grid says when there is no library to show: a read error, no ZBrush, or no files in the folders searched. */
function libEmptyState(kind) {
  const L = lib(kind), w = K(kind);
  let el;
  if (L.state === 'error') el = emptyState('alert', 'Could not read the ' + w.one + ' library', L.error || 'The backend could not list your ZBrush ' + w.one + ' folders.');
  else if (!L.zbrushFound && !L.sources.some(s => s.added)) {
    // The Setup screen lists the ZBrush installs ZOrbit knows. The browser window has no way to open Studio, so it only says where to look.
    el = emptyState('library', 'No ' + w.many + ' to show', 'ZBrush was not found. ZOrbit Studio reads the ' + w.one + ' folders of a ZBrush that has run at least once. Start ZBrush once, then press Rescan' + (POPOUT ? '. If it is still not found, open Studio from the tray icon and add its folder in Setup.' : '.'),
      POPOUT ? null : { text: 'Find ZBrush in Studio', fn: () => showScreen('setup') });
  }
  else {
    el = emptyState('library', 'No ' + w.many + ' found', 'No ' + w.exts + ' files in these folders:');
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
  const clearBtn = h('button', { class: 'ibtn', type: 'button', title: 'Clear search', 'aria-label': 'Clear search', hidden: !st.q, onclick: () => { clearQuery(); renderGrid(); rehighlight(); search.focus(); } }, icon('x', 13));
  const count = h('span', { class: 'b-count mono' });
  const orderBtn = h('button', { class: 'btn small b-order', type: 'button', hidden: true, title: 'Forget your order for this tab and go back to most used first', onclick: () => forgetOrder() }, 'Most used');
  const fchips = h('span', { class: 'filter-chips', hidden: true });     // the popout's toolbar: the filters that are on (styles.css shows them only while its column is collapsed)
  const grid = h('div', { class: 'bgrid' });
  const libWarn = h('div', { class: 'fhint warn lib-warn', role: 'status', hidden: true, style: 'margin-bottom: 10px' });   // a folder that could not be read while the others were: its items are the ones it had
  const scroll = h('div', { class: 'b-scroll', tabindex: '-1' }, libWarn, grid);   // tabindex: it can hold the keyboard while the focused card has scrolled away (paintWindow)
  const scrollHost = ZScrollBar.attach(scroll, document);        // its own scroll bar, which a pen can drag (scrollbar.js)
  const side = h('div', { class: 'lib-side' });
  const catsBox = h('div', { class: 'cats', role: 'listbox', 'aria-label': 'Folders' });
  const tagSec = h('div', { class: 'tag-sec', role: 'group', 'aria-label': 'Tags' });                     // full: the Tags section under Folders
  const tagRow = h('div', { class: 'tagrow', role: 'group', 'aria-label': 'Filter by tag', hidden: true });   // compact: the same chips, wrapped
  const addFolderBtn = !compact && host.addFolder ? h('button', { class: 'btn small lib-addfolder', type: 'button', onclick: async () => {     // the same list as Settings > Library folders, for the tab on show
    const kind = st.kind;
    addFolderBtn.disabled = true;
    let r = null;
    try { r = await call('add_library_folder', kind); } catch (e) { toast('Could not add the folder: ' + e.message, { tone: 'warn', ms: 5000 }); }
    addFolderBtn.disabled = false;
    if (!r || r.cancelled) return;
    toast(r.message || (r.ok ? 'Added.' : 'That did not work.'), !r.ok ? { tone: 'warn', ms: 5000 } : r.already ? { ms: 4000 } : { tone: 'ok', ms: 4000 });
    if (r.ok && !r.already) await loadLibrary(kind, true);
  } }, icon('folder', 12), 'Add a folder...') : null;
  side.append(...[catsBox, addFolderBtn, tagSec].filter(Boolean));
  const lazy = makeLazyIO(scroll);
  let curRes = compact ? 128 : resFor(st.size), lastSig = '';
  let built = '', gridKind = '';         // built: kind + names of the list on show (renderGrid keeps its cards when the list is the same); gridKind: the kind they were made for
  let win = null;                        // the list on show and the part of it that has cards: { list, first, end, cols, rowH, pool } (see paintWindow)
  let winFrame = 0, winMeasure = false;  // a paintWindow waiting for the next frame, and whether it measures the rows again
  let focusAway = false;                 // the card with the keyboard (rov) scrolled away, and the scroller holds the keyboard for it
  let rov = null, rovEl = null;          // the card that is the grid's one Tab stop (name, node)
  const sel = new Set();                 // names of the selected items
  let anchor = null;                     // the last plain or Ctrl click: where a Shift-click range starts
  if (!st.open) st.open = new Set();
  if (!(st.tags instanceof Set)) st.tags = new Set();     // the tags to show, kept on the state like st.cat
  st.tagAll = !!st.tagAll;                                // how they combine: false = an item with any of them, true = an item with all of them (the Any / All switch)
  st.untagged = !!st.untagged;                            // the virtual "Untagged" chip: items without any tag
  if (st.cat.includes('/')) st.open.add(st.cat.split('/')[0]);   // a folder chosen from outside (a link) starts unfolded

  const searchBox = h('label', { class: 'searchbox' }, icon('search', 14), search, clearBtn);
  const onSearch = debounce(() => { st.q = search.value; clearBtn.hidden = !st.q; renderGrid(); if (host.firstMatch) highlightFirst(); }, 120);   // flushed by move and pickSelected: a key right after typing acts on the new list
  search.addEventListener('input', onSearch);
  search.addEventListener('keydown', e => { if (e.key === 'Escape' && search.value) { e.stopPropagation(); clearBtn.click(); } });
  let autoHl = false;                    // the selection is only the highlight put on the first match (the popout), so Esc leaves it alone
  function clearQuery() { onSearch.cancel(); search.value = ''; st.q = ''; clearBtn.hidden = true; }

  /* The selected items and their action strip. A click selects one, Ctrl-click adds or removes one, Shift-click selects a
     range of the items on show. The strip tags them or adds them to the menu being edited. */
  const hint = h('div', { class: 'b-hint' });
  const addBtn = h('button', { class: 'btn primary small as-add', type: 'button', onclick: () => { const names = shownSel(); if (names.length === 1) host.primary(names[0], st.kind); else if (names.length) host.primaryMany(names, st.kind); } });
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
    root.append(...[tabs && tabs.el, dockHint, tools, tagRow, orderBtn, count, scrollHost, strip].filter(Boolean));
  } else {
    const size = h('input', { type: 'range', min: 84, max: 220, step: 4, value: st.size, 'aria-label': 'Thumbnail size' });
    const paint = () => size.style.setProperty('--pct', ((st.size - 84) / (220 - 84)) * 100 + '%');
    size.addEventListener('input', () => {
      st.size = +size.value; grid.style.setProperty('--card', st.size + 'px'); paint();
      if (host.onSize) host.onSize(st.size);
      const r = resFor(st.size);
      if (r !== curRes) { curRes = r; $$('.bcard .thumb', grid).forEach(t => rethumb(t, r)); }
      paintWindowSoon(true);                                   // the rows have another height now
    });
    paint(); grid.style.setProperty('--card', st.size + 'px');
    rescan = rescanBtn(st.kind);
    tools = h('div', { class: 'b-tools' }, searchBox, h('div', { class: 'size-ctl' }, icon('library', 13), size), rescan, fchips, host.tools ? host.tools() : null);
    root.append(side, h('div', { class: 'lib-main' }, tabs ? tabs.el : null, tools, h('div', { class: 'b-sub' }, hint, count, orderBtn), scrollHost, strip));
  }

  /* --- tag filter: an item shows when it carries any chosen tag (or every one, with the Any / All switch on All); "Untagged" shows the items without a tag */
  const tagFilterOn = () => st.untagged || st.tags.size > 0;
  const allMode = () => st.tagAll && st.tags.size > 1;     // the switch only shows with two or more tags, and with one tag Any and All are the same
  function pruneTagSel() { if (S.tagsLoaded) for (const k of Array.from(st.tags)) if (!S.tagMap.has(k)) st.tags.delete(k); }
  const tagMatch = b => {
    if (!tagFilterOn()) return true;
    const ks = tagsOf(st.kind, b.name);
    return st.untagged ? !ks.some(k => k !== FAV) : ZTagFilter.match(ks, st.tags, st.tagAll);     // untagged: no ordinary tag (see tagCounts)
  };
  /* The items on show: in name order, except Favourites (the tab's own order if it has one, else most used first by the usage scores)
     and Recent (newest pick first). L().sorted is in name order and sort is stable, so ties keep it. */
  const filtered = () => {
    pruneTagSel();
    const q = st.q.trim().toLowerCase(), terms = q ? q.split(/\s+/) : [];
    const list = L().sorted.filter(b => catMatch(b, st.cat, host, st.kind) && (!terms.length || terms.every(t => b.name.toLowerCase().includes(t))) && tagMatch(b));
    const u = usageOf(st.kind);
    if (st.cat === '@fav') return ZFavOrder.sorted(list, favOrderOf(st.kind), b => nameKey(b.name), b => u.scores[b.name.toLowerCase()] || 0);
    if (st.cat === '@recent') list.sort((a, b) => (u.recentT.get(nameKey(b.name)) || 0) - (u.recentT.get(nameKey(a.name)) || 0));
    return list;
  };
  /* The selected items that are on show. renderGrid drops the rest, but a pick must never act on an item the filter hides. */
  function shownSel() {
    const shown = new Set(filtered().map(b => b.name));
    return Array.from(sel).filter(n => shown.has(n));
  }
  /* The popout keeps the first match highlighted: after a filter changes by hand it moves there again. */
  function rehighlight() { if (host.firstMatch) highlightFirst(); }
  /* Picks a folder; the two usage folders read get_usage afresh. */
  function setCat(cat) { st.cat = cat; mark(); if (usageCat(cat)) loadUsage(st.kind); }
  /* The mouse's Back and Forward buttons walk the tabs and folders this browser has been on, like the pages of a web browser.
     Kept on st, because the Library screen makes a new browser each time it opens. */
  const nav = st.nav || (st.nav = { list: [{ kind: st.kind, cat: st.cat }], at: 0 });
  let replaying = false;
  function mark() {
    if (replaying) return;
    const cur = nav.list[nav.at];
    if (cur.kind === st.kind && cur.cat === st.cat) return;
    nav.list.splice(nav.at + 1);
    nav.list.push({ kind: st.kind, cat: st.cat });
    if (nav.list.length > 50) nav.list.shift();
    nav.at = nav.list.length - 1;
  }
  mark();                                                      // a link may have set the folder while no browser was open
  /* One step back (-1) or forward (1). False when there is nowhere to go, so the caller can use the button for something else. */
  function navStep(d) {
    const to = nav.list[nav.at + d];
    if (!to) return false;
    nav.at += d; replaying = true;
    try {
      if (to.kind !== st.kind) setKind(to.kind);
      st.cat = to.cat;
      if (to.cat.includes('/')) st.open.add(to.cat.split('/')[0]);
      if (usageCat(to.cat)) loadUsage(st.kind);
      renderAll(); rehighlight();
      scroll.scrollTop = 0;
    } finally { replaying = false; }
    return true;
  }
  function toggleTag(key) {
    if (key === '@untagged') { st.untagged = !st.untagged; if (st.untagged) st.tags.clear(); }
    else { st.untagged = false; if (st.tags.has(key)) st.tags.delete(key); else st.tags.add(key); }
    renderTags(); renderGrid(); rehighlight();
  }
  function clearTagFilter() { st.tags.clear(); st.untagged = false; st.tagAll = false; renderTags(); renderGrid(); rehighlight(); }
  function setTagAll(all) { if (st.tagAll === all) return; st.tagAll = all; renderTags(); renderGrid(); rehighlight(); }
  /* The Any / All switch, shown while two or more tags are chosen. */
  function tagModeSwitch() {
    const btn = (all, text, tip) => h('button', { class: 'seg-btn' + (st.tagAll === all ? ' on' : ''), type: 'button', role: 'radio', 'aria-checked': st.tagAll === all ? 'true' : 'false', title: tip,
      dataset: { tm: all ? 'all' : 'any' }, onclick: () => setTagAll(all) }, text);
    return h('div', { class: 'tag-mode' }, h('span', { class: 'micro' }, 'Match'),
      h('div', { class: 'mode-seg', role: 'radiogroup', 'aria-label': 'Match items with any or all of the chosen tags' },
        btn(false, 'Any', `Show ${W().many} with at least one of the chosen tags`), btn(true, 'All', `Show only ${W().many} with every one of the chosen tags`)));
  }
  /* The filters that are on, as chips in the toolbar with an x that clears each: a tag filter ("Filtered: Blocking") and a folder ("Folder: My Brushes").
     The folders and tags column shows the same, so the chips only appear when the popout has collapsed it (styles.css). */
  const folderName = cat => cat === '@fav' ? 'Favourites' : cat === '@recent' ? 'Recent' : cat === '@used' ? 'In my menus' : cat.split('/').join(' / ');
  function paintFilterChips() {
    if (compact) return;
    const chip = (text, clearText, fn) => h('button', { class: 'fchip', type: 'button', title: clearText, 'aria-label': clearText, onclick: fn },
      h('span', { class: 'fc-text' }, text), icon('x', 11));
    const chips = [];
    if (st.cat !== 'All') chips.push(chip('Folder: ' + folderName(st.cat), 'Clear the folder filter', () => { setCat('All'); renderAll(); rehighlight(); }));
    if (st.untagged) chips.push(chip('Filtered: Untagged', 'Clear the tag filter', clearTagFilter));
    else if (st.tags.size) chips.push(chip('Filtered: ' + Array.from(st.tags).map(k => (S.tagMap.get(k) || { label: k }).label).join(allMode() ? ' + ' : ', '), 'Clear the tag filter', clearTagFilter));
    fchips.hidden = !chips.length;
    fchips.replaceChildren(...chips);
  }
  /* The chips: a list under Folders in the full browser, a wrapped row under the category in the dock. */
  function renderTags() {
    const host = compact ? tagRow : tagSec;
    const act = document.activeElement, fr = act && host.contains(act) ? act.closest('[data-tk], [data-tm]') : null, fk = fr ? (fr.dataset.tk !== undefined ? fr.dataset.tk : 'tm:' + fr.dataset.tm) : null;
    pruneTagSel();
    paintFilterChips();
    const counts = tagCounts(st.kind);
    // With All on, a chip counts the items that carry every chosen tag and this one too: what choosing it would leave. A chip at 0 is dimmed.
    const narrow = allMode() ? ZTagFilter.narrowedCounts(lib(st.kind).items.map(b => tagsOf(st.kind, b.name)), st.tags, true) : null;
    const chip = (key, label, n, color) => {
      const on = key === '@untagged' ? st.untagged : st.tags.has(key);
      const dim = !!narrow && key !== '@untagged' && !on && n === 0;
      return h('button', { class: 'tagchip' + (on ? ' on' : '') + (dim ? ' none-left' : ''), type: 'button', 'aria-pressed': on ? 'true' : 'false',
        title: label + ': ' + plural(n, W().one) + (narrow && key !== '@untagged' ? (on ? ' with all the chosen tags' : ' with all the chosen tags and this one') : ' on this tab'), style: color ? { '--tag': color } : null,
        dataset: { tk: key }, onclick: () => toggleTag(key) },
        h('i', { class: 'tdot' + (color ? '' : ' none') }), h('span', { class: 'tc-name' }, label), h('span', { class: 'tc-n mono' }, String(n)));
    };
    const userTags = S.tags.filter(t => t.key !== FAV);                // Favourites has its own folder, not a chip
    const chips = userTags.map(t => chip(t.key, t.label, (narrow ? narrow.get(t.key) : counts.byKey.get(t.key)) || 0, t.color));
    if (userTags.length) chips.push(chip('@untagged', 'Untagged', counts.untagged, null));
    const clear = tagFilterOn() ? h('button', { class: 'link tag-clear', type: 'button', onclick: clearTagFilter }, 'Clear') : null;
    if (compact) {
      tagRow.hidden = !userTags.length;
      tagRow.replaceChildren(...[st.tags.size > 1 ? tagModeSwitch() : null, ...chips, clear, isFull() ? h('button', { class: 'ibtn tag-manage', type: 'button', title: 'Manage tags...', 'aria-label': 'Manage tags', onclick: () => openTagManager() }, icon('tag', 14)) : null].filter(Boolean));
    } else {
      tagSec.replaceChildren(...[h('div', { class: 'tag-head' }, h('span', { class: 'micro side-title' }, 'Tags'), clear),
        st.tags.size > 1 ? tagModeSwitch() : null,
        userTags.length ? h('div', { class: 'tagchips' }, chips) : h('div', { class: 'tag-none fhint' }, `No tags yet. Select ${W().many} and press Tag to make one.`),
        S.tagsErr ? h('div', { class: 'fhint bad' }, S.tagsErr) : null,
        isFull() || POPOUT ? manageTagsBtn('btn small tag-manage') : null].filter(Boolean));
    }
    if (fk !== null) { const t = $$('[data-tk], [data-tm]', host).find(x => (x.dataset.tk !== undefined ? x.dataset.tk : 'tm:' + x.dataset.tm) === fk); if (t) t.focus(); }
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
      btn = h('button', { class: 'bstar', type: 'button', tabindex: '-1',      // the card is the Tab stop; Ctrl+D stars it, Enter adds it
        onclick: e => { e.stopPropagation(); const n = card.dataset.name; setFavs(sel.size > 1 && sel.has(n) ? Array.from(sel) : [n], !isFav(st.kind, n)); },
        ondblclick: e => e.stopPropagation() }, icon('star', 14));          // a double-click must not pick the item
      box.append(btn);
    }
    const text = on ? 'Remove from Favourites' : 'Add to Favourites';
    btn.classList.toggle('on', on);
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.title = text; btn.setAttribute('aria-label', text + ': ' + name);
  }
  /* --- dragging a card to a new place in Favourites. One card moves, whatever is selected. The pointer drag of the Library (DnD, through
     the zone below) and the native drag of the popout share these; the list comes from filtered() and only the gap from the cards that
     exist (see paintWindow). A drag that cannot reorder, or a drop elsewhere, goes on as any other drag. */
  const canReorder = () => st.cat === '@fav' && !st.q.trim() && !search.value.trim() && !tagFilterOn() && L().state === 'ready';
  const dropMark = h('div', { class: 'bdrop', 'aria-hidden': 'true' });
  let reorder = null;                    // the drag on show: { name, x, y }, the last place the pointer was over the grid; stop: see watchDragEnd
  /* The gap counts from the start of the list, and the first card that exists may be far into it. */
  function gapAtPoint(x, y) {
    const g = ZFavOrder.gapAt(cardEls().map(c => c.getBoundingClientRect()), x, y, parseFloat(getComputedStyle(grid).columnGap) || 0);
    if (g && win) g.index += win.first;
    return g;
  }
  function paintDrop(name, x, y) {
    if (!reorder || reorder.name !== name) { endReorder(); reorder = { name, x, y }; const c = cardEls().find(e => e.dataset.name === name); if (c) c.classList.add('reordering'); }
    reorder.x = x; reorder.y = y;
    const g = gapAtPoint(x, y), box = scroll.getBoundingClientRect();
    if (!g) { dropMark.remove(); return; }
    dropMark.style.left = (g.x - box.left + scroll.scrollLeft) + 'px'; dropMark.style.top = (g.top - box.top + scroll.scrollTop) + 'px'; dropMark.style.height = (g.bottom - g.top) + 'px';
    if (dropMark.parentNode !== scroll) scroll.append(dropMark);      // not in the grid: paintWindow takes every child of the grid for a card
  }
  function endReorder() {
    if (reorder && reorder.stop) reorder.stop();
    reorder = null; dropMark.remove(); edgeSpeed = 0;
    $$('.bcard.reordering', grid).forEach(c => c.classList.remove('reordering'));
  }
  /* A native drag can scroll its card out of the part of the list that exists, and a card that is gone may never hear dragend. No mouse
     move reaches the page during a native drag, so the first one with the card gone means the drag is over. */
  function watchDragEnd(card) {
    const moved = () => { if (!card.isConnected) endReorder(); };
    window.addEventListener('mousemove', moved, true);
    reorder.stop = () => window.removeEventListener('mousemove', moved, true);
  }
  function dropInGap(name, x, y) {
    const g = gapAtPoint(x, y), next = g && canReorder() ? ZFavOrder.moved(filtered().map(b => nameKey(b.name)), nameKey(name), g.index) : null;
    if (next) tagCall('set_favourite_order', st.kind, next);                  // its answer repaints every browser (tagsChanged); no change saves nothing
  }
  /* Most used: forgets the tab's order, once asked. There while the tab has one and Favourites is on show. */
  function paintOrderBtn() { orderBtn.hidden = !(st.cat === '@fav' && favOrderOf(st.kind).length); }
  async function forgetOrder() {
    const kind = st.kind;
    const ok = await modal({ title: 'Back to most used first?', body: h('p', null, `Your order for ${K(kind).many} is forgotten, and your favourite ${K(kind).many} go back to most used first.`),
      actions: [{ text: 'Cancel', value: false, focus: true }, { text: 'Most used', kind: 'danger', value: true }] });
    if (ok) tagCall('set_favourite_order', kind, null);
  }
  /* A pointer drag scrolls the grid when it nears the top or bottom edge, and a scroll moves the marker: the card under the pointer changed. */
  let edgeSpeed = 0, edgeFrame = 0, edgeTime = 0;                              // px per ms, by the clock: a screen's refresh rate must not set the speed
  function edgeScroll(y) {
    const r = scroll.getBoundingClientRect(), near = 32;
    edgeSpeed = y < r.top + near ? -0.6 : y > r.bottom - near ? 0.6 : 0;
    const step = t => {
      edgeFrame = 0;
      if (!edgeSpeed) return;
      scroll.scrollTop += edgeSpeed * Math.min(t - edgeTime, 50); edgeTime = t;
      edgeFrame = requestAnimationFrame(step);
    };
    if (edgeSpeed && !edgeFrame) { edgeTime = performance.now(); edgeFrame = requestAnimationFrame(step); }
  }
  scroll.addEventListener('scroll', () => { if (reorder) paintDrop(reorder.name, reorder.x, reorder.y); });
  DnD.zone(scroll, {
    accept: p => p.type === 'asset' && p.from === st && canReorder(),         // only a card of this grid: a drag from the popout has no .from
    over: (p, x, y) => { paintDrop(p.name, x, y); edgeScroll(y); },
    leave: endReorder,
    drop: (p, x, y) => dropInGap(p.name, x, y),
  });
  scroll.addEventListener('dragover', e => {                                   // the popout: the page's own handler refused the drag a moment ago (bindNativeDrop)
    if (!reorder || !DnD.native.mine(e.dataTransfer) || !canReorder()) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';                                        // what the card allows, so the same drag can land in Studio
    paintDrop(reorder.name, e.clientX, e.clientY);
  });
  scroll.addEventListener('dragleave', e => { if (reorder && !scroll.contains(e.relatedTarget)) dropMark.remove(); });
  scroll.addEventListener('drop', e => {
    if (!reorder) return;
    e.preventDefault();
    const name = reorder.name;
    endReorder();
    dropInGap(name, e.clientX, e.clientY);
  });
  function makeCard(b) {
    const on = sel.has(b.name);
    const card = h('div', { class: 'bcard' + (on ? ' sel' : ''), tabindex: '-1', role: 'button', 'aria-pressed': on ? 'true' : 'false', dataset: { name: b.name } },   // renderGrid gives one card tabindex 0
      h('div', { class: 'bthumb' }, thumb(b.name, { size: 0, lazy, cls: 'fill', res: curRes, kind: st.kind }),
        h('button', { class: 'badd', type: 'button', tabindex: '-1', title: host.cardTitle(st.kind), 'aria-label': host.cardLabel(b.name, st.kind), onclick: e => { e.stopPropagation(); host.primary(b.name, st.kind); } }, icon(host.primaryIcon(st.kind), 14))),
      h('div', { class: 'bname', title: b.name }, b.name));           // the title: a long name is cut off, and in a pack the end of it tells two items apart
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
        const names = shownSel();
        if (names.length > 1 && sel.has(b.name)) host.primaryMany(names, st.kind); else { setSel(b.name); host.primary(b.name, st.kind); }
      } else if (e.key === ' ') {
        e.preventDefault();
        if (e.ctrlKey || e.metaKey) { if (sel.has(b.name)) sel.delete(b.name); else sel.add(b.name); anchor = b.name; paintSel(); } else setSel(b.name);
      }
    });
    if (host.dnd) DnD.source(card, () => ({ type: 'asset', kind: st.kind, name: b.name, from: canReorder() ? st : null }), () => h('span', { class: 'ghost-chip' }, thumb(b.name, { size: 26, kind: st.kind }), b.name));
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
        if (canReorder()) { endReorder(); reorder = { name: b.name, x: e.clientX, y: e.clientY }; card.classList.add('reordering'); watchDragEnd(card); }
      });
      card.addEventListener('dragend', endReorder);                          // Esc, or a drop anywhere else: nothing was saved
    }
    paintBadge(card);
    paintTags(card);
    paintFav(card);
    return card;
  }
  const cardEls = () => Array.from(grid.querySelectorAll('.bcard[data-name]'));
  /* A card made earlier, put back on show: only what changes without a rebuild (selection, a picture still to come) is brought up to date. */
  function reuseCard(card) {
    const on = sel.has(card.dataset.name);
    card.classList.toggle('sel', on); card.setAttribute('aria-pressed', on ? 'true' : 'false');
    const t = card.querySelector('.thumb');
    if (t && t._io && (!t.querySelector('img') || t._got !== t._res)) t._io.observe(t);      // renderGrid let go of every thumbnail: the unfinished ones ask again
    return card;
  }
  /* The grid is one Tab stop: the card that has the keyboard (or was clicked) is the one with tabindex 0. */
  grid.addEventListener('focusin', e => {
    const c = e.target.closest && e.target.closest('.bcard[data-name]');
    if (c) focusAway = false;
    if (!c || c.classList.contains('skel') || (c === rovEl && rov === c.dataset.name)) return;
    if (rovEl) rovEl.tabIndex = -1;
    c.tabIndex = 0; rovEl = c; rov = c.dataset.name;
  });
  /* The Tab stop among the cards that exist: the card it belongs to, or while that one has no card, the first on show. */
  function paintTabStop() {
    if (rovEl && rovEl.isConnected && rovEl.dataset.name === rov) return;
    if (rovEl) rovEl.tabIndex = -1;
    rovEl = cardNamed(rov) || grid.querySelector('.bcard[data-name]');
    if (rovEl) rovEl.tabIndex = 0;
  }
  const cardNamed = name => (name ? Array.from(grid.children).find(c => c.dataset.name === name) : null) || null;
  function measureWindow() {
    const c = grid.querySelector('.bcard[data-name]'), high = c ? c.getBoundingClientRect().height : 0;   // not offsetHeight: it is rounded, and the padding would jump by the difference at each row
    if (!high) return;                                         // not laid out (hidden, or taken off the page for a while): what was measured stays
    const cs = getComputedStyle(grid);
    win.cols = Math.max(1, cs.gridTemplateColumns.split(' ').filter(Boolean).length);       // the resolved columns
    win.rowH = high + (parseFloat(cs.rowGap) || 0);
  }
  /* Cards win.list[a] up to b, in order, reusing the ones the last list had. */
  function cardsFor(a, b) {
    const frag = document.createDocumentFragment();
    for (let i = a; i < b; i++) {
      const it = win.list[i], old = win.pool && win.pool.get(it.name), card = old ? reuseCard(old) : makeCard(it);
      card.tabIndex = -1;
      card.classList.toggle('reordering', !!reorder && reorder.name === it.name);   // the card being dragged, scrolled back into view
      frag.append(card);
    }
    return frag;
  }
  function dropCard(card) {
    const t = card.querySelector('.thumb');
    if (t && t._io) t._io.unobserve(t);
    card.remove();
  }
  /* A library can hold thousands of items, so only the cards near the view exist (gridwindow.js); padding on the grid stands for
     the rest. This brings them up to date with the scroll position. Called for each new list, each scroll and each resize. */
  function paintWindow(measure = false) {
    if (!win || (win.rowH && !scroll.clientHeight)) return;    // hidden: the cards and the padding wait as they are, so the scroll position can be put back
    if (measure || !win.rowH) measureWindow();
    const r = ZGridWindow.range({ top: scroll.getBoundingClientRect().top - grid.getBoundingClientRect().top, height: scroll.clientHeight,
      rowH: win.rowH, cols: win.cols, total: win.list.length, margin: 480 });
    const changed = r.first !== win.first || r.end !== win.end, act = document.activeElement;
    const held = changed && act && act !== document.body && grid.contains(act) ? act.closest('.bcard') : null, heldAt = held ? win.first + Array.prototype.indexOf.call(grid.children, held) : -1;
    const hadFocus = !!held && (heldAt < r.first || heldAt >= r.end);
    if (hadFocus) act.blur();                                   // first: taking away a focused element forces a layout, and part way through the swap the list is shorter, so the scroll position would clamp
    if (changed) {
      if (r.first >= win.end || r.end <= win.first) {           // a jump: nothing stays
        Array.from(grid.children).forEach(dropCard);
        grid.append(cardsFor(r.first, r.end));
      } else {
        for (let i = win.first; i < r.first; i++) dropCard(grid.firstElementChild);
        for (let i = win.end; i > r.end; i--) dropCard(grid.lastElementChild);
        if (r.first < win.first) grid.prepend(cardsFor(r.first, win.first));
        if (r.end > win.end) grid.append(cardsFor(win.end, r.end));
      }
      win.first = r.first; win.end = r.end;
    }
    grid.style.paddingTop = r.padTop + 'px';                    // before anything that forces a layout: with the new cards and the old padding the list is shorter, and the scroll position would clamp to it
    grid.style.paddingBottom = r.padBottom + 'px';
    if (changed) {
      paintTabStop();
      if (hadFocus) {                                           // the card with the keyboard scrolled away: the scroller holds the keyboard, so Enter or Ctrl+D cannot land on a card nobody chose
        focusAway = true;
        scroll.focus({ preventScroll: true });
      } else if (focusAway && document.activeElement === scroll && rovEl && rovEl.dataset.name === rov) {   // and it is back
        rovEl.focus({ preventScroll: true });
      }
    }
    if (!win.rowH && win.end > 0) {                             // the first cards are there to measure: now the real window
      measureWindow();
      if (win.rowH) paintWindow();
    }
  }
  function paintWindowSoon(measure = false) {
    winMeasure = winMeasure || measure;
    if (!winFrame) winFrame = requestAnimationFrame(() => { const m = winMeasure; winFrame = 0; winMeasure = false; paintWindow(m); });
  }
  scroll.addEventListener('scroll', () => paintWindowSoon(), { passive: true });
  new ResizeObserver(() => paintWindowSoon(true)).observe(scroll);
  /* Scrolls item i of the list on show into view (only as far as it takes) and gives back its card. */
  function revealCard(i) {
    if (!win.rowH) measureWindow();
    const row = Math.floor(i / win.cols), lastRow = Math.floor((win.list.length - 1) / win.cols);
    const y = grid.getBoundingClientRect().top - scroll.getBoundingClientRect().top + scroll.scrollTop + row * win.rowH;
    if (!row) scroll.scrollTop = 0;                            // the first and last rows go right to the edge, past the scroller's padding
    else if (row === lastRow) scroll.scrollTop = scroll.scrollHeight;
    else if (y < scroll.scrollTop) scroll.scrollTop = y;
    else if (y + win.rowH > scroll.scrollTop + scroll.clientHeight) scroll.scrollTop = y + win.rowH - scroll.clientHeight;
    paintWindow();
    return cardNamed(win.list[i].name);
  }
  function paintCount(list) {
    const f = tagFilterOn();
    let t = list.length + ' ' + (list.length === 1 ? W().one : W().many) + (st.cat !== 'All' || st.q || f ? ' of ' + L().items.length : '');
    if (f) t += ' · ' + (st.untagged ? 'untagged' : plural(st.tags.size, 'tag'));
    setText(count, t);
  }
  /* keep: put the scroll position back once enough cards are drawn (a rescan or a refresh must not throw you to the top). */
  function renderGrid(keep = false) {
    paintOrderBtn();
    const loading = L().state === 'loading' || L().state === 'idle';
    if (!loading) {
      const gone = Array.from(sel).filter(n => !L().byName.has(nameKey(n)));
      if (gone.length) { gone.forEach(n => sel.delete(n)); paintSel(); }
    }
    const usable = !loading && L().state !== 'error' && L().items.length > 0;
    libWarn.hidden = !(usable && L().error);
    setText(libWarn, usable && L().error ? L().error : '');
    const list = usable ? filtered() : null;
    const sig = list ? list.map(b => b.name).join('\n') : '';
    const dropHidden = () => {
      const onShow = new Set(list.map(b => b.name)), hidden = Array.from(sel).filter(n => !onShow.has(n));       // a filter, folder or search can hide what was selected: it is no longer selected
      if (hidden.length) { hidden.forEach(n => sel.delete(n)); if (anchor && hidden.includes(anchor)) anchor = null; paintSel(); }
    };
    if (usable && list.length && built === st.kind + '\n' + sig) {          // the same cards in the same order are on show: keep them, repaint what a library reload can change
      lastSig = sig;
      dropHidden(); paintCount(list);
      if (keep) { cardEls().forEach(c => { paintBadge(c); paintTags(c); paintFav(c); }); retryMissedThumbs(st.kind); }
      return;
    }
    let keepTop = keep ? scroll.scrollTop : null;
    const act = document.activeElement, focusName = act && act.classList && act.classList.contains('bcard') && grid.contains(act) ? act.dataset.name : null;
    const pool = new Map(usable && gridKind === st.kind ? cardEls().map(c => [c.dataset.name, c]) : []);   // cards of this kind already built: reused by name, not made again
    $$('.thumb', grid).forEach(t => { if (t._io) t._io.unobserve(t); });   // the old cards are about to go: do not keep them in the observer
    grid.replaceChildren();
    grid.style.paddingTop = grid.style.paddingBottom = '';
    win = null;
    lastSig = ''; built = ''; gridKind = ''; rovEl = null;
    if (loading) {
      setText(count, 'Scanning...');
      for (let i = 0; i < 24; i++) grid.append(h('div', { class: 'bcard skel' }, h('div', { class: 'bthumb' }, h('span', { class: 'thumb fill loading' })), h('div', { class: 'bname' }, ' ')));
      return;
    }
    if (!usable) {
      setText(count, `0 ${W().many}`);
      grid.append(h('div', { class: 'grid-empty' }, libEmptyState(st.kind)));
      return;
    }
    lastSig = sig;
    dropHidden();
    paintCount(list);
    if (!list.length) {
      let e;
      if (tagFilterOn()) {
        e = emptyState('tag', st.untagged ? `Every ${W().one} here has a tag` : `No ${W().many} with ` + (st.tags.size === 1 ? 'that tag' : allMode() ? 'all of those tags' : 'those tags'),
          st.q || st.cat !== 'All' ? 'The search and the folder narrow it too.' : `Select ${W().many} and press Tag, or right-click ${aOrAn(W().one)}.`, { text: 'Clear the tag filter', fn: clearTagFilter });
      } else if (st.q) {
        const where = st.cat === '@used' ? 'In my menus' : st.cat === '@fav' ? 'Favourites' : st.cat === '@recent' ? 'Recent' : st.cat.split('/').join(' / ');
        e = emptyState('search', `No ${W().many} match "${st.q}"`, st.cat !== 'All' ? `Only "${where}" was searched.` : 'Check the spelling.');
        e.append(h('div', { class: 'btn-row' },
          h('button', { class: 'btn small', type: 'button', onclick: () => { clearQuery(); renderAll(); rehighlight(); } }, 'Clear search'),
          st.cat !== 'All' ? h('button', { class: 'btn small primary', type: 'button', onclick: () => { setCat('All'); renderAll(); rehighlight(); } }, 'Search all folders') : null));
      } else if (st.cat === '@fav') {
        e = emptyState('star', 'No favourites yet', `Hover ${aOrAn(W().one)} and press its star, or press Ctrl+D.`, { text: `Show all ${W().many}`, fn: () => { setCat('All'); renderAll(); } });
      } else if (st.cat === '@recent') {
        e = emptyState('clock', 'Nothing picked yet', 'Items you pick in ZBrush show up here, newest first.', { text: `Show all ${W().many}`, fn: () => { setCat('All'); renderAll(); } });
      } else {
        e = emptyState('search', 'Nothing in this category', st.cat === '@used' ? `${W().tab} you put into a menu show up here.` : '', { text: `Show all ${W().many}`, fn: () => { setCat('All'); renderAll(); } });
      }
      grid.append(h('div', { class: 'grid-empty' }, e));
      return;
    }
    gridKind = st.kind;
    const have = new Set(list.map(b => b.name));
    rov = [rov, anchor, sel.values().next().value].find(n => n && have.has(n)) || list[0].name;       // the card that is the one Tab stop of the grid
    win = { list, first: 0, end: 0, cols: 1, rowH: 0, pool };
    built = st.kind + '\n' + sig;
    paintWindow();                                             // the first cards, measured, and the padding for the rest
    scroll.scrollTop = keepTop === null ? 0 : keepTop;         // a new list starts at the top; a rescan or a refresh must not throw you there
    paintWindow();
    win.pool = null;
    if (focusName && have.has(focusName)) {                    // the card that had the keyboard is still in the list: it keeps it
      const c = revealCard(list.findIndex(b => b.name === focusName));
      if (c) c.focus({ preventScroll: true });
    }
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
        renderAll(); rehighlight();
      };
      const r = h('div', { class: 'cat' + (st.cat === id ? ' on' : '') + (o.kid ? ' kid' : '') + (o.group ? ' group' : ''), role: 'option', tabindex: '-1', 'aria-selected': st.cat === id ? 'true' : 'false', title: label, dataset: { id },      // the list is one Tab stop (setRoving below); the arrow keys move inside it
        onclick: activate, onkeydown: e => {
          if (e.target !== r || e.ctrlKey || e.metaKey || e.altKey) return;
          const rs = $$('.cat', catsBox), at = rs.indexOf(r);
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); }
          else if (e.key === 'ArrowDown' && rs[at + 1]) { e.preventDefault(); rs[at + 1].focus(); }
          else if (e.key === 'ArrowUp' && rs[at - 1]) { e.preventDefault(); rs[at - 1].focus(); }
          else if (e.key === 'Home' && at > 0) { e.preventDefault(); rs[0].focus(); }
          else if (e.key === 'End' && at < rs.length - 1) { e.preventDefault(); rs[rs.length - 1].focus(); }
          else if (o.hasKids && e.key === 'ArrowRight' && !st.open.has(id)) { e.preventDefault(); toggle(); }      // a folder with sub-folders opens and closes with Right and Left
          else if (o.hasKids && e.key === 'ArrowLeft' && st.open.has(id)) { e.preventDefault(); toggle(); }
        } },
        o.hasKids ? h('button', { class: 'cat-chev' + (st.open.has(id) ? ' open' : ''), type: 'button', tabindex: '-1', 'aria-label': (st.open.has(id) ? 'Collapse ' : 'Expand ') + label, 'aria-expanded': st.open.has(id) ? 'true' : 'false',
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
    const crs = $$('.cat', catsBox), nr = fid !== null ? crs.find(r => r.dataset.id === fid) : null;
    setRoving(crs, nr || crs.find(r => r.dataset.id === st.cat));          // one Tab stop: the row that had the keyboard, else the open folder
    if (nr) {
      const t = (onChev && $('button.cat-chev', nr)) || nr;
      t.focus();
    }
  }
  catsBox.addEventListener('focusin', e => { const x = e.target.closest && e.target.closest('.cat'); if (x) setRoving($$('.cat', catsBox), x); });
  function renderAll(keep = false) { if (L().state === 'ready') renderCats(); renderTags(); renderGrid(keep); }

  /* --- keyboard help for the popout: a highlight that follows the arrow keys and Enter picks */
  function highlightFirst() {
    const first = filtered()[0];
    if (!first) { if (sel.size) setSel(null); return; }
    setSel(first.name);
    autoHl = true;
  }
  /* Moves the highlight one card (dx) or one row (dy). The row length is however many cards sit at the first card's height. */
  function move(dx, dy) {
    onSearch.flush();
    if (!win || !win.list.length) return false;
    measureWindow();
    const list = win.list, act = document.activeElement, away = act === scroll && focusAway, onCard = away || (!!act && act.classList.contains('bcard') && grid.contains(act));
    const from = away ? rov : onCard ? act.dataset.name : anchor;   // from the card that has the keyboard (or had it, and scrolled away), else from the highlight
    const at = from ? list.findIndex(b => b.name === from) : -1;
    const to = at < 0 ? 0 : clamp(at + dx + dy * win.cols, 0, list.length - 1);
    revealCard(to);                                            // first: the card may not exist yet, and setSel gives it the focus
    setSel(list[to].name, onCard);
    return true;
  }
  /* Home and End on a card: the first or the last card on show. */
  function moveEdge(last) {
    onSearch.flush();
    if (!win || !win.list.length) return false;
    const to = last ? win.list.length - 1 : 0;
    revealCard(to);
    setSel(win.list[to].name, true);
    return true;
  }
  /* Studio's Library and the dock: the arrow keys on a card move to the next one (the popout's window handler does the same from its search box). */
  scroll.addEventListener('keydown', e => {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey || !e.target.classList || !(e.target.classList.contains('bcard') || e.target === scroll)) return;
    const dx = e.key === 'ArrowLeft' ? -1 : e.key === 'ArrowRight' ? 1 : 0, dy = e.key === 'ArrowUp' ? -1 : e.key === 'ArrowDown' ? 1 : 0;
    if (dx || dy) { e.preventDefault(); move(dx, dy); }
    else if (e.key === 'Home' || e.key === 'End') { e.preventDefault(); moveEdge(e.key === 'End'); }
  });
  function pickSelected() {
    onSearch.flush();
    const names = shownSel();
    if (!names.length) return false;
    if (names.length === 1) host.primary(names[0], st.kind); else host.primaryMany(names, st.kind);
    return true;
  }
  /* A fresh look: no search, no folder, only the given tag (or none), the first match highlighted. */
  function setFilter(tag) {
    clearQuery(); st.untagged = false; st.tagAll = false; st.tags = new Set(tag && tag !== FAV ? [tag] : []);
    setCat(tag === FAV ? '@fav' : 'All');                       // Favourites is a folder, not a chip
    renderAll(); highlightFirst(); scroll.scrollTop = 0;
  }

  /* Every word that names the kind on show: the ones set once here, and the repaint of the lists reads W() as it goes. */
  function paintStrings() {
    const w = W(), tagText = `Tag the selected ${w.many}`;
    search.placeholder = `Search ${w.many}...`; search.setAttribute('aria-label', `Search ${w.many}`);
    tagBtn.title = tagText; tagBtn.setAttribute('aria-label', tagText);
    strip.setAttribute('aria-label', `Selected ${w.many}`);
    if (addFolderBtn) addFolderBtn.title = `Add a folder of your own ${w.many}. ZBrush 2026 and newer.`;
    if (dockHint) setText(dockHint, `Click ${aOrAn(w.one)} and press Add, or drag it onto the ring or the list.`);
  }
  /* Switches to another kind: its own folders and selection, the same search text and tag filter. */
  function setKind(kind) {
    if (kind === st.kind || !isLib(kind)) return;
    st.kind = kind;
    sel.clear(); anchor = null; autoHl = false;
    st.cat = 'All'; st.open = new Set(); mark();
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
    kind: () => st.kind, setKind, navStep,
    refresh() { renderAll(true); paintTarget(); },                  // after a library load: the scroll position stays
    relayout() { paintWindow(true); },                              // just put on the page: measure now, so a scroll position can be put back this frame (the ResizeObserver comes a frame later)
    hasSel: () => sel.size > 0,
    focusSearch(select = true) { search.focus(); if (select) search.select(); },
    typeChar(ch) { search.value += ch; search.dispatchEvent(new Event('input', { bubbles: true })); },
    inSearch: el => !!el && el.closest && !!el.closest('.searchbox'),
    searchValue: () => search.value,
    highlightFirst, move, moveEdge, pickSelected, setFilter,
    updateBadges() { $$('.bcard[data-name]', grid).forEach(paintBadge); paintTarget(); if (L().state === 'ready') { renderCats(); if (st.cat === '@used') renderGrid(); } },
    /* After a tag change: dots, chips, and the grid itself when the tag filter now shows other items. */
    updateTags() {
      $$('.bcard[data-name]', grid).forEach(c => { paintTags(c); paintFav(c); });
      renderTags(); paintFavBtn();
      if (L().state === 'ready') renderCats();                 // the Favourites count
      paintOrderBtn();
      if (L().state === 'ready' && filtered().map(b => b.name).join('\n') !== lastSig) renderGrid(true);   // the view stays where it is
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
  browser.relayout();                                 // showScreen puts the scroll position back next
  R.libRefresh = kind => { if (kind === S.lib.kind) browser.refresh(); };
  R.badges = () => browser.updateBadges();
  const list = h('div', { class: 'ilist' });          // kept between repaints, so a tag change does not send it back to the top
  R.libTarget = () => {
    const hadSel = !!document.activeElement && document.activeElement.matches && document.activeElement.matches('.target-sel select') && target.contains(document.activeElement);
    const top = list.scrollTop, same = list._menu === S.menuId;
    target.replaceChildren();
    const ids = Object.keys(S.cfg.menus), m = curMenu();
    const sel = h('select', { class: 'inp sel', 'aria-label': 'Target menu', onchange: () => selectMenu(sel.value) }, ids.map(id => h('option', { value: id, selected: id === S.menuId }, (menuOf(id).title || id))));
    target.append(h('div', { class: 'col-head' }, h('span', { class: 'micro' }, 'Add to menu')),
      h('div', { class: 'target-sel' }, ids.length ? sel : null),
      h('div', { class: 'items-panel' }, list),
      h('div', { class: 'target-foot' }, h('button', { class: 'btn small', type: 'button', onclick: () => showScreen('menus') }, 'Open in Menus editor', icon('chevR', 12))));
    renderItemList(list, S.menuId, true);
    if (same) list.scrollTop = top;                   // the same menu: it was detached just now, which resets the scroll
    if (!m) list.replaceChildren(emptyState('menus', 'No menus', 'Create a menu in the Menus screen first.'));
    if (hadSel) sel.focus();
  };
  R.libTarget();
}

/* ================================================================== SETTINGS screen */
/* The Browser buttons of the top bar and the Library toolbar: the browser can take a moment to start, so say so first. */
function openBrowserFromButton() { toast('Opening the browser...', { ms: 2500 }); return openBrowserWindow(); }
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
/* After the last ring key is dropped, an empty ring object goes too when the saved file had none, so a slider put back leaves nothing to save. */
function dropIfEmpty(name) {
  const o = S.cfg[name];
  if (!o || typeof o !== 'object' || Object.keys(o).length) return;
  let had = true;
  try { had = name in JSON.parse(S.savedStr); } catch (e) { /* keep it */ }
  if (!had) delete S.cfg[name];
}
const tidyRing = () => dropIfEmpty('ring');
/* Sets a ring value, or drops its key when it equals the default (the file then says nothing about it). */
function ringSet(k, v) {
  if (v !== S.defaults[k]) ensureRing()[k] = v; else delete ensureRing()[k];
}
function putRing(k, v) {
  if (v !== S.defaults[k]) { setRing(k, v); return; }
  ringSet(k, v); tidyRing(); commit();
}
/* get/put/clear/isSet let a row drive more than its own key (see sizeRow); the defaults are the plain one-key behaviour. */
function sliderRow({ label, hint, key, step = 1, unit = '', scale = 1, onLive, limits = null, get = () => ringNum(key), put = v => putRing(key, v),
  clear = () => { delete ensureRing()[key]; tidyRing(); commit(); }, isSet = () => key in ring() && ring()[key] !== S.defaults[key], numMax = null, dflt = S.defaults[key] }) {   // scale: shown = stored * scale (0-1 opacity as 0-100 %); limits: [min, max] when ring_ranges has none for the key; numMax: the number box's top when it goes past the slider's; dflt: the reset button's default
  const [lo, hi] = limits || ranges()[key] || [0, 100];
  const min = lo * scale, max = hi * scale, nmax = numMax === null ? max : numMax * scale;
  const disp = v => Number((v * scale).toFixed(6)), store = d => Number((d / scale).toFixed(6));
  const range = h('input', { type: 'range', min, max, step, value: disp(get()), 'aria-label': label, dataset: { fk: key + '/range' } });
  const num = h('input', { class: 'inp mono num', type: 'number', min, max: nmax, step, value: disp(get()), 'aria-label': label + ' value', dataset: { fk: key + '/num' } });
  const reset = iconBtn('undo', 'Reset to default (' + disp(dflt) + (scale !== 1 ? unit : '') + ')', () => { clear(); sync(get()); onLive && onLive(); }, 'reset');
  reset.dataset.fk = key + '/reset';
  const note = h('span', { class: 'num-hint', role: 'status' });
  let noteT = 0;
  const say = t => { clearTimeout(noteT); note.textContent = t; if (t) noteT = setTimeout(() => { note.textContent = ''; }, 2000); };
  const sync = v => { range.value = num.value = disp(v); range.style.setProperty('--pct', ((v - lo) / (hi - lo)) * 100 + '%'); reset.style.visibility = isSet() ? 'visible' : 'hidden'; };
  range.addEventListener('input', () => { const v = store(Number(range.value)); put(v); sync(v); onLive && onLive(); });
  num.addEventListener('change', () => {
    const raw = num.value.trim(), n = Number(raw);
    if (raw === '' || !Number.isFinite(n)) { sync(get()); say(''); return; }     // nothing usable typed: keep what was there
    const snapped = Number((min + Math.round((n - min) / step) * step).toFixed(6)), v = store(clamp(snapped, min, nmax));
    say(n < min || n > nmax ? 'Kept within ' + min + ' to ' + nmax : '');
    if (v !== get()) { put(v); onLive && onLive(); }
    sync(v);
  });
  sync(get());
  return h('div', { class: 'srow' }, h('div', { class: 'slabel' }, h('span', null, label), hint ? h('small', null, hint) : null), h('div', { class: 'sctl' }, range, h('span', { class: 'nwrap' }, num, unit ? h('em', null, unit) : null, note), reset));
}
/* Simple mode's one size slider: it moves radius, slot and dead zone together, keeping the proportions the ring had when the gesture began. */
function sizeRow(live) {
  const KEYS = ['radius', 'slot', 'dead_zone'];
  // base is the ring at the start of a gesture; slot and dead zone are scaled from it, not from their last rounded
  // value, so a slow drag does not drift. A run of arrow keys keeps one base (a 1 px step from a fresh base would
  // round slot and dead zone to no change at all); it is taken again when something else moved the radius since
  // this row last wrote it (undo, say), on a new pointer gesture and when the row gets focus.
  let base = null, last = null;
  const row = sliderRow({ label: 'Ring size', hint: 'How big the ring is. Slots and the dead zone scale with it.', key: 'radius', unit: 'px', onLive: live,
    put: v => {
      if (!base || ringNum('radius') !== last) base = { radius: ringNum('radius'), slot: ringNum('slot'), dead_zone: ringNum('dead_zone') };
      const f = base.radius ? v / base.radius : 1;
      ringSet('radius', v);
      for (const k of ['slot', 'dead_zone']) { const [lo, hi] = ranges()[k] || [0, 1000]; ringSet(k, clamp(Math.round(base[k] * f), lo, hi)); }
      tidyRing(); commit();
      last = ringNum('radius');
    },
    clear: () => { for (const k of KEYS) delete ensureRing()[k]; tidyRing(); commit(); base = null; },
    isSet: () => KEYS.some(k => k in ring() && ring()[k] !== S.defaults[k]) });
  for (const ev of ['pointerdown', 'focusin']) row.addEventListener(ev, () => { base = null; }, true);
  return row;
}
function switchRow({ label, hint, key }) {
  const v = ring()[key];
  return h('div', { class: 'srow' }, h('div', { class: 'slabel' }, h('span', null, label), h('small', null, hint)),
    h('div', { class: 'sctl switch' }, toggleSwitch(typeof v === 'boolean' ? v : S.defaults[key], on => putRing(key, on), label)));
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
    rb.title = railTitle('settings') + (n ? ' – ' + (n === 1 ? 'a ZBrush plugin needs' : n + ' ZBrush plugins need') + ' updating' + (isFull() ? '' : ' (Setup, step 1, or Full mode)') : '');
  }
  const tb = document.querySelector('.toc-item[data-card="set-older-zbrush"]');
  if (tb) { tb.classList.toggle('has-badge', n > 0); tb.title = n ? 'Update available' : ''; }
}
async function refreshZsBadge() {
  try { setZsBadge(zsOutdated(await call('get_zscript_bridge'))); } catch (e) { /* no badge */ }
}

function card(title, sub, ...kids) { return h('section', { class: 'card' }, h('h2', { class: 'card-title' }, title, sub ? h('em', null, sub) : null), ...kids); }

/* A card (or, with flat, a section of the Menu tab) whose body folds away. The head is a button that says whether it is open (aria-expanded) and
   shows a one-line summary while it is closed. o: { id (the element's id; the body's is id + '-body'), title, sub, summary, open, onToggle(open), flat }.
   The caller keeps the open/closed choice outside the element (the screens are rebuilt wholesale) and passes it back as o.open. foldOpen only
   changes the DOM and never rebuilds, so the focus stays on the head. */
function foldSection(o, ...kids) {
  const body = h('div', { class: 'fold-body', id: o.id + '-body' }, ...kids);
  const head = h('button', { class: 'fold-head', type: 'button', 'aria-expanded': 'false', 'aria-controls': o.id + '-body', dataset: { fk: 'fold:' + o.id },
    onclick: () => { const v = !foldIsOpen(el); foldOpen(el, v); if (o.onToggle) o.onToggle(v); } },
  h('span', { class: 'fold-chev', 'aria-hidden': 'true' }), h('span', { class: 'fold-title' }, o.title), o.sub ? h('em', null, o.sub) : null, h('span', { class: 'fold-sum' }, o.summary || ''));
  const el = h('section', { class: 'fold' + (o.flat ? ' flat' : ' card'), id: o.id }, h('h2', { class: 'card-title' }, head), body);
  foldOpen(el, !!o.open);
  return el;
}
const foldIsOpen = el => !!el && el.classList.contains('open');
/* Opens or closes a foldSection (anything else is left alone). */
function foldOpen(el, v) {
  if (!el || !el.classList || !el.classList.contains('fold')) return;
  const head = el.querySelector('.fold-head'), body = el.querySelector('.fold-body'), chev = el.querySelector('.fold-chev');
  el.classList.toggle('open', !!v);
  head.setAttribute('aria-expanded', v ? 'true' : 'false');
  body.hidden = !v;
  chev.replaceChildren(icon(v ? 'chevD' : 'chevR', 13));
}
const foldSum = (el, text) => { const s = el && el.querySelector && el.querySelector('.fold-sum'); if (s && s.textContent !== text) s.textContent = text; };

/* The rows for the ZScript plugin on ZBrush 2022 to 2025 (install, update, remove, forget, add a folder), shared by
   Settings > Older ZBrush and the Setup screen. paint({installs, bundled}) draws into box; every action ends by calling
   refresh() so the caller can look again (Settings fetches, Setup forces its own poll). extra(z) may add a node to a row. */
function legacyRows(box, { refresh, extra } = {}) {
  // Runs one install or remove. The whole row is locked while it runs (the elevation prompt can sit open for minutes).
  // later: after that many ms of waiting the button says laterText (a plain copy is quick; an administrator prompt is not)
  const act = (name, path, btn, rowBtns, busyText, later, laterText) => async () => {
    const was = rowBtns.map(b => b.disabled), label = [...btn.childNodes];
    rowBtns.forEach(b => { b.disabled = true; });
    btn.classList.add('running'); btn.replaceChildren(h('span', { class: 'spin' }), busyText);
    const slow = later ? setTimeout(() => { if (btn.classList.contains('running')) btn.replaceChildren(h('span', { class: 'spin' }), laterText); }, later) : 0;
    let res = null;
    try { res = await call(name, path); }
    catch (e) { toast('That did not work: ' + e.message, { tone: 'warn' }); }
    clearTimeout(slow);
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
      const [stext, scls] = !z.installed ? ['Plugin not installed', 'tag dim'] : (z.current ? ['Plugin installed', 'tag cyan'] : ['Plugin update available', 'tag amber']);
      const main = h('button', { class: 'btn small' + (z.installed && z.current ? '' : ' primary'), type: 'button', disabled: !r.bundled }, z.installed ? (z.current ? 'Reinstall' : 'Update') : 'Install');
      const rm = z.installed ? h('button', { class: 'btn small danger-ghost', type: 'button' }, icon('trash', 12), 'Remove') : null;
      const forget = z.added ? iconBtn('x', 'Forget this folder', async () => {
        forget.disabled = true;
        try { const res = await call('forget_zbrush_folder', z.path); toast(res.message || (res.ok ? 'Forgot that folder.' : 'That did not work.'), { tone: res.ok ? 'ok' : 'warn', ms: 4000 }); }
        catch (e) { toast('Could not forget the folder: ' + e.message, { tone: 'warn' }); }
        refresh();
      }) : null;
      const rowBtns = [main, rm, forget].filter(Boolean);
      main.onclick = act('install_zscript_bridge', z.path, main, rowBtns, 'Installing...', 4000, 'Installing... approve the prompt if Windows asks');
      if (rm) rm.onclick = async () => {
        const ok = await modal({ title: `Remove the plugin from ${z.name}?`,
          body: [h('p', null, 'This deletes the ZOrbit plugin files from this ZBrush install:'), h('p', { class: 'modal-path mono' }, z.path),
            /program files/i.test(z.path) ? h('p', null, 'This folder is under Program Files. If your account cannot change it, Windows asks you to approve the removal.') : null],
          actions: [{ text: 'Cancel', value: false, focus: true }, { text: 'Remove', value: true, kind: 'danger' }] });
        if (ok) act('remove_zscript_bridge', z.path, rm, rowBtns, 'Removing...', 4000, 'Removing... approve the prompt if Windows asks')();
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
      // A ZBrush 2026 or later (python: true) has no ZScript plugin, so this list never shows it: Setup does, with its registered state and Fix.
      const viaSetup = r.ok && r.python && S.screen !== 'setup' ? { text: 'Open Setup', fn: () => showScreen('setup') } : null;
      const extra = viaSetup ? ' It is a newer ZBrush, so it is listed in Setup.' : '';
      if (r.already) toast((r.message || 'That folder is already listed.') + extra, Object.assign({ ms: 4000 }, viaSetup ? { action: viaSetup } : {}));
      else if (!r.cancelled) toast((r.message || (r.ok ? 'Added.' : 'That did not work.')) + extra, Object.assign({ tone: r.ok ? 'ok' : 'warn', ms: 5000 }, viaSetup ? { action: viaSetup } : {}));
      if (r.ok) refreshSetupBadge();
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
  R.gotoCard = id => {
    let it = tocItems.find(t => t.card.id === id);
    if (it) it.btn.click();
  };
  let tocRaf = 0;
  const unpin = () => { if (pinned) { pinned = null; markActive(); } };
  for (const ev of ['wheel', 'keydown', 'pointerdown', 'touchstart']) scroll.addEventListener(ev, unpin, { passive: true });
  scroll.addEventListener('scroll', () => { if (!tocRaf) tocRaf = requestAnimationFrame(() => { tocRaf = 0; markActive(); }); }, { passive: true });

  const build = () => {
    const full = isFull();
    page.replaceChildren();
    page.append(h('div', { class: 'page-head' }, h('h1', null, 'Settings', h('em', null, 'Appearance and behaviour')), h('p', null, (full ? 'The theme, how the ring behaves, and how the app talks to ZBrush.' : 'The theme, and how the ring behaves.') + ' The ring\u2019s size, shape, colours and open animation are on the Look screen. Changes are saved with the Save button.')));
    const hiddenSet = full ? [] : fullOnlyChanges(S.cfg, 'settings');      // not a .card, so it is not in the contents list
    if (hiddenSet.length) page.append(h('div', { class: 'mode-note', role: 'status' }, 'Changed in Full mode and not shown here: ' + hiddenSet.join(', ') + '. ', linkBtn('Switch to Full mode', () => setMode('full'))));

    /* --- theme: a Studio preference kept per PC, not part of S.cfg, so Save, Revert and undo never see it */
    const themeNote = S.prefs.theme === 'system' ? h('div', { class: 'fhint', role: 'status', style: { marginTop: '6px' } }, 'Windows is set to ' + (S.themeEff === 'light' ? 'Light' : 'Dark') + ' right now, so that is what ZOrbit is using.') : null;
    let zbNote = null;                                         // Match ZBrush: which stored scheme is in use, with its colours
    if (S.prefs.theme === 'zbrush') {
      const src = S.prefs.theme_source, tk = S.prefs.theme_tokens || {};
      if (src && typeof src === 'object') {
        const d = new Date(src.stored * 1000), ok = !isNaN(d);
        const when = ok ? d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) + ' ' + pad2(d.getHours()) + ':' + pad2(d.getMinutes()) : '';
        const sw = [['--bg1', 'Main'], ['--bg2', 'Palette'], ['--bg3', 'Button'], ['--text', 'Text'], ['--accent', 'Switch']]
          .filter(([k]) => tk[k]).map(([k, name]) => h('i', { class: 'zb-sw', title: name + ' ' + tk[k], style: { background: tk[k] } }));
        zbNote = h('div', { class: 'fhint zb-src', role: 'status', title: src.path || null }, h('span', null, 'ZBrush ' + src.year + (when ? ', stored ' + when : '')),
          sw.length ? h('span', { class: 'zb-sws', role: 'img', 'aria-label': 'Main, Palette, Button, Text and Switch colours' }, sw) : null);
      } else zbNote = h('div', { class: 'fhint zb-src', role: 'status' }, 'No stored ZBrush colours found, so Dark is used. In ZBrush: Preferences > Config > Store Config.');
    }
    const themeCard = card('Theme', 'How Studio, the browser and the ring look',
      choiceCards([['dark', 'Dark', 'The default look.'], ['light', 'Light', 'For ZBrush and Windows set to a light theme.'],
        ['system', 'Follow Windows', 'Uses the Windows app colour mode and changes with it.'],
        ['zbrush', 'Match ZBrush', 'Uses the colours you last stored in ZBrush.']], THEMES.includes(S.prefs.theme) ? S.prefs.theme : 'dark', async v => {
        if (v === S.prefs.theme) return;
        const ok = await setPref('theme', v);
        if (!ok) { if (R.settings) R.settings(); return; }             // the pick did not stick: draw the old one again
        syncTheme();
      }, 'four', 'Theme'),
      h('div', { class: 'fhint', style: { marginTop: '8px' } }, 'Applies to Studio, the browser and the ring. ' + (full ? 'A colour you set under Look > Colours still wins. ' : '') + 'Themes are experimental: the colours will change as they are tuned.'), zbNote, themeNote);
    page.append(themeCard);

    /* --- browser (browser.hotkey; the object is dropped again when it ends up empty) */
    const browserObj = () => { if (!S.cfg.browser || typeof S.cfg.browser !== 'object') S.cfg.browser = {}; return S.cfg.browser; };
    const bOwner = hotkey => (hotkey ? hotkeyOwner(hotkey, BROWSER) : null);
    const bsay = owner => (owner === PROFILE ? 'Also used by the next-profile hotkey. The browser keeps this key, so that hotkey will not step profiles.'
      : owner ? `Also used by ${ownerName(owner)}. That menu wins, so this hotkey will not open the browser.` : '');
    const bhk = hotkeyField({ what: 'Browser hotkey', value: (S.cfg.browser && typeof S.cfg.browser === 'object' && S.cfg.browser.hotkey) || '', placeholder: 'No hotkey', onChange: str => {
      const b = browserObj();
      if (str) b.hotkey = str; else delete b.hotkey;
      if (!Object.keys(b).length) delete S.cfg.browser;
      const owner = bOwner(str);
      bhk.say(bsay(owner), 'warn');
      phk.say(psay(pOwner(S.cfg.profile && S.cfg.profile.next_hotkey)), 'warn');
      commit();
    } });

    /* --- quit hidden browser after (browser.quit_after_minutes; 0 is off and drops the key; Full only, see the card below) */
    const qGet = () => { const q = S.cfg.browser && typeof S.cfg.browser === 'object' ? S.cfg.browser.quit_after_minutes : undefined; return Number.isInteger(q) && q >= 1 && q <= 1440 ? q : 0; };
    const qSet = v => { const b = browserObj(); if (v) b.quit_after_minutes = v; else delete b.quit_after_minutes; if (!Object.keys(b).length) delete S.cfg.browser; commit(); };

    /* --- next profile (profile.next_hotkey; the object is dropped again when it ends up empty; Full only, see the card below) */
    const profileObj = () => { if (!S.cfg.profile || typeof S.cfg.profile !== 'object') S.cfg.profile = {}; return S.cfg.profile; };
    const pOwner = hotkey => (hotkey ? hotkeyOwner(hotkey, PROFILE) : null);
    const psay = owner => (owner === BROWSER ? 'Also used by the browser. The browser wins, so this hotkey will not step profiles.'
      : owner ? `Also used by ${ownerName(owner)}. That menu wins, so this hotkey will not step profiles.` : '');
    const phk = hotkeyField({ what: 'Next profile hotkey', value: (S.cfg.profile && typeof S.cfg.profile === 'object' && S.cfg.profile.next_hotkey) || '', placeholder: 'No hotkey', onChange: str => {
      const p = profileObj();
      if (str) p.next_hotkey = str; else delete p.next_hotkey;
      if (!Object.keys(p).length) delete S.cfg.profile;
      const owner = pOwner(str);
      phk.say(psay(owner), 'warn');
      bhk.say(bsay(bOwner(S.cfg.browser && S.cfg.browser.hotkey)), 'warn');
      commit();
    } });

    /* --- behaviour (with the browser hotkey, a setting of the same kind) */
    page.append(card('Behaviour', null,
      switchRow({ label: 'Flick to pick', hint: 'Moving the cursor out past a slot picks it straight away, without releasing the hotkey or clicking.', key: 'flick' }),
      switchRow({ label: 'Show the hint', hint: 'The line of help under the menu’s title, such as “click a slot, centre or right-click cancels”. Turn it off for a cleaner ring.', key: 'hint' }),
      ...(full ? [
        switchRow({ label: 'Open submenus on hover', hint: 'Reaching a submenu slot opens that submenu, centred on the slot. Keep holding the hotkey to pick in it by releasing or flicking.', key: 'hover_submenus' }),
        sliderRow({ label: 'Tap time', hint: 'A hotkey press shorter than this is a tap: the ring stays open for a click. Holding longer and releasing picks the item under the cursor.', key: 'tap_ms', step: 10, unit: 'ms' }),
        sliderRow({ label: 'Tag fan slots', hint: 'How many slots a tag fan holds. A tag with more items than that ends in a More slot that opens the browser on the tag.', key: 'tag_limit', unit: ' ' }),   // a blank unit keeps the number box in line with the sliders around it
        sliderRow({ label: 'Auto-close', hint: 'An open ring closes by itself after this long.', key: 'timeout_s', unit: 's' })] : []),
      h('div', { class: 'srow' }, h('div', { class: 'slabel' }, h('span', null, 'Browser hotkey'), h('small', null, 'Shows the browser; pressed over it, it gives ZBrush the keyboard back. The browser also opens from a Browser slot, the Browser button at the top and the tray menu.')),
        h('div', { class: 'sctl' }, bhk)),
      ...(full ? [sliderRow({ label: 'Quit hidden browser after', hint: 'Gives its memory back after this long unused. The next press starts it again, a moment slower. 0 keeps it ready.', key: 'quit_after_minutes', unit: 'min',
          limits: [0, 240], numMax: 1440, dflt: 0, get: qGet, put: qSet, clear: () => qSet(0), isSet: () => qGet() !== 0 }),
        h('div', { class: 'srow' }, h('div', { class: 'slabel' }, h('span', null, 'Next profile hotkey'), h('small', null, 'Steps to the next profile while ZBrush is in front. Each profile has its own; a new profile copies it from the one in use.')),
        h('div', { class: 'sctl' }, phk))] : [])));
    { const o0 = bOwner(S.cfg.browser && S.cfg.browser.hotkey); if (o0) bhk.say(bsay(o0), 'warn'); }
    { const o1 = pOwner(S.cfg.profile && S.cfg.profile.next_hotkey); if (o1) phk.say(psay(o1), 'warn'); }

    /* --- library folders: the user's own folders of brushes, alphas, materials and textures. Acts straight away; the lists live in studio.json, not in the menus */
    const lfBox = h('div', { class: 'lf-kinds' }, h('div', { class: 'fhint' }, 'Looking for your folders...'));
    let lfGen = 0;                                             // a slower earlier answer must not paint over a newer one
    const lfPaint = folders => {
      lfBox.replaceChildren(...LIB_KINDS.map(kind => {
        const w = K(kind), rows = Array.isArray(folders && folders[kind]) ? folders[kind] : [];
        const list = rows.map(f => {
          const tags = [];
          if (f.error) tags.push(h('span', { class: 'tag amber', title: String(f.error) }, 'Cannot be read'));
          else if (!f.exists) tags.push(h('span', { class: 'tag amber' }, 'Missing'));
          else if (typeof f.count === 'number') tags.push(h('span', { class: 'tag dim' }, plural(f.count, 'file') + (f.hidden > 0 ? ', ' + f.hidden + ' hidden' : '')));
          const forget = iconBtn('x', 'Forget this folder', async () => {
            forget.disabled = true;
            let r = null;
            try { r = await call('forget_library_folder', kind, f.path); }
            catch (e) { toast('Could not forget the folder: ' + e.message, { tone: 'warn' }); }
            forget.disabled = false;
            // Undo puts it back where it was; the answer has its path and place. Taking it out is saved at once, so this is the only way back.
            const back = r && r.ok && typeof r.removed === 'string' ? { text: 'Undo', fn: async () => {
              let r2 = null;
              try { r2 = await call('add_library_folder', kind, r.removed, r.index); }
              catch (e) { toast('Could not put the folder back: ' + e.message, { tone: 'warn', ms: 5000 }); }
              lfAfter(kind, r2, 'Put it back.');
            } } : null;
            lfAfter(kind, r, 'Forgot that folder.', back && { ms: 7000, action: back });
          });
          return h('div', { class: 'zrow' }, h('div', { class: 'grow' }, h('div', { class: 'zname' }, f.name || f.path, ...tags), h('div', { class: 'zpath mono', title: f.path }, f.path)),
            h('div', { class: 'btn-row' }, forget));
        });
        if (!list.length) list.push(h('div', { class: 'fhint' }, 'None added.'));
        const add = h('button', { class: 'btn small', type: 'button', onclick: async () => {
          add.disabled = true;
          let r = null;
          try { r = await call('add_library_folder', kind); }
          catch (e) { toast('Could not add the folder: ' + e.message, { tone: 'warn' }); }
          add.disabled = false;
          lfAfter(kind, r, 'Added.');
        } }, icon('folder', 12), 'Add a folder...');
        return h('div', { class: 'lf-kind' }, h('div', { class: 'flabel' }, w.tab), h('div', { class: 'zrows' }, ...list), h('div', { class: 'btn-row' }, add));
      }));
    };
    // What add and forget answer: say it, paint the lists they hand back, and when this page holds that kind's library, read it again so the Library screen and the dock follow.
    const lfAfter = async (kind, r, fallback, extra) => {
      if (!r || r.cancelled) return;
      toast(r.message || (r.ok ? fallback : 'That did not work.'), !r.ok ? { tone: 'warn', ms: 5000 } : r.already ? { ms: 4000 } : Object.assign({ tone: 'ok', ms: 4000 }, extra));
      if (r.folders) { ++lfGen; lfPaint(r.folders); }
      else if (!r.ok) { lfLook(); return; }                    // refused without a list (the file changed under the card): paint what is there now
      if (r.ok && !r.already) {
        await loadLibrary(kind, true);                         // also a kind not read yet, or one still being read: its list then has the folder
        lfLook();                                              // the counts fill in once the folder has been read
      }
    };
    const lfLook = async () => {
      if (R.libfolders && R.libfolders !== lfLook) return R.libfolders();   // this card was rebuilt (undo, reload): paint the live one
      const gen = ++lfGen;
      let r;
      try { r = await call('get_library_folders'); if (gen !== lfGen) return; }
      catch (e) { if (gen !== lfGen) return; lfBox.replaceChildren(h('div', { class: 'fhint bad' }, 'Could not read your folders: ' + e.message)); return; }
      if (r && r.ok && r.folders) lfPaint(r.folders);
      else { lfBox.replaceChildren(h('div', { class: 'fhint bad' }, (r && r.message) || 'Could not read your folders.')); return; }
      // A kind with folders that this page has not read yet: read it now, so the rows get their counts (and Cannot be read) without a visit to the Library.
      const unread = LIB_KINDS.filter(k => (r.folders[k] || []).length && !lib(k).loaded && !lib(k).busy);
      if (!unread.length) return;
      try {
        await Promise.all(unread.map(k => loadLibrary(k)));
        if (gen !== lfGen) return;
        const r2 = await call('get_library_folders');
        if (gen === lfGen && r2 && r2.ok && r2.folders) lfPaint(r2.folders);
      } catch (e) { /* the rows stay without counts; the Library screen will say */ }
    };
    page.append(card('Library folders', 'Your own folders of brushes, alphas, materials and textures, searched after ZBrush’s own. ZBrush 2026 and newer. Acts straight away.', lfBox));
    R.libfolders = lfLook;
    lfLook();

    /* --- studio (preferences of this window, saved immediately, not part of the menus file) */
    const updNote =h('div', { class: 'fhint upd-status', role: 'status' });
    const updBtn = h('button', { class: 'btn small primary', type: 'button', hidden: true, title: 'Get the new version',
      onclick: () => openUpdate(window.RadialUpdate && window.RadialUpdate.last) }, 'Install update');
    let updTok = 0;
    const paintUpdate = u => {
      if (!u || S.prefs.check_updates === false) { updNote.textContent = ''; updBtn.hidden = true; return; }
      const newer = !!(u.newer && u.latest);
      updNote.textContent = newer ? 'Version ' + u.latest + ' available' + (u.skipped ? '. You chose not to be reminded about it.' : '') : (u.latest ? 'Up to date' : 'Could not reach GitHub');
      updNote.className = 'fhint upd-status' + (newer ? ' new' : (u.latest ? '' : ' warn'));
      updBtn.hidden = !newer;
      updBtn.textContent = u.can_install ? 'Install update' : 'Download update';
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
    else if (window.RadialUpdate && window.RadialUpdate.pending) {      // Studio opened on Settings: paint when the first check answers
      const tok = updTok;
      window.RadialUpdate.pending.then(u => { if (tok === updTok && u && document.contains(updNote)) paintUpdate(u); }, () => {});
    }
    const wnBtn = h('button', { class: 'btn small', type: 'button', title: 'The release notes up to this version', onclick: async e => {
      const b = e.currentTarget; b.disabled = true;
      try { if (!(await showWhatsNew({ all: true, remember: false }))) toast('There is nothing to show yet.', { ms: 2500 }); }
      catch (err) { toast('Could not load the release notes.', { tone: 'warn' }); }
      b.disabled = false;
    } }, "What's new");
    const tourBtn = h('button', { class: 'btn small', type: 'button', title: 'A short tour of this window', onclick: () => startTour() }, 'Take the tour');
    const verEl = h('span', { class: 'mono' }, '');
    call('get_app_info').then(i => { if (i && i.version) verEl.textContent = 'v' + i.version; }).catch(() => {});
    const gplLink = h('button', { class: 'link', type: 'button', onclick: async () => {
      try { await call('open_url', 'https://www.gnu.org/licenses/gpl-3.0.html'); } catch (e) { toast('Could not open the link.', { tone: 'warn' }); } } }, 'GPL-3.0');
    page.append(card('Studio', 'Preferences for this window. Saved straight away.',
      h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Check for updates'),
        h('div', { class: 'fhint' }, 'When Studio opens, it asks GitHub for the newest release and shows it next to the version at the top, where you can install it. Nothing about you or your menus is sent.'), updNote,
          h('div', { class: 'btn-row', style: { marginTop: '8px' } }, updBtn, wnBtn, tourBtn)),
        toggleSwitch(S.prefs.check_updates !== false, async v => {
          const ok = await setPref('check_updates', v);
          if (!ok) return false;
          if (v) checkNow(); else { updTok++; updNote.textContent = ''; updBtn.hidden = true; if (window.RadialUpdate) window.RadialUpdate.check(); }
          return true;
        }, 'Check for updates')),
      h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Version'),
        h('div', { class: 'fhint' }, 'ZOrbit Studio ', verEl, ', licensed under ', gplLink, '. Free to use, change and share.')))));

    /* --- import and export (one file with the menus, the ring settings and the tags) */
    const ioBtns = [
      h('button', { class: 'btn small', type: 'button', title: 'Save the menus, ring settings and tags to a file', onclick: () => ioRun(ioBtns, exportSettings) }, icon('folder', 12), 'Export...'),
      h('button', { class: 'btn small', type: 'button', title: 'Load menus, ring settings and tags from a file', onclick: () => ioRun(ioBtns, importSettings) }, icon('folder', 12), 'Import...')];
    page.append(card('Import and export', 'Back up your setup or move it to another PC.',
      h('div', { class: 'field row' }, h('div', { class: 'grow' }, h('span', { class: 'flabel' }, 'Settings file'),
        h('div', { class: 'fhint' }, 'The file holds your menus, the ring settings and your tags. The Studio window preferences and the usage counts are not included, as they belong to this PC. Export saves what is on screen, unsaved changes included. Import shows what is in a file first, and the menus and settings it loads can be undone.'),
        h('div', { class: 'fhint', style: { marginTop: '6px' } }, 'Export... saves this profile’s menus, settings and tags. To bring a file in as a new profile, use New profile... in the top bar.')),
        h('div', { class: 'btn-row' }, ...ioBtns))));
    if (full) {
      /* --- bridge */
      const bridge = () => { if (!S.cfg.bridge || typeof S.cfg.bridge !== 'object') S.cfg.bridge = {}; return S.cfg.bridge; };
      const bmode = (S.cfg.bridge && S.cfg.bridge.mode) || 'auto';
      const keyWrap = h('div', { class: 'bridge-key' });
      let paintZNote = () => {};      // the Older ZBrush card's paragraph about binding the key; set further down
      const paintKey = () => {
        const mode = (S.cfg.bridge && S.cfg.bridge.mode) || 'auto';
        keyWrap.classList.toggle('dim', mode === 'message');
        keyWrap.replaceChildren(field('Bridge key', hotkeyField({ what: 'Bridge key', value: (S.cfg.bridge && S.cfg.bridge.key) || '', mods: { ctrl: false, alt: false, shift: false }, placeholder: 'F9 (the default)',
          altMessage: 'Alt cannot be used here: ZBrush does not act on an Alt key that ZOrbit sends. Use a bare F-key.',
          refuse: k => k === 'F10' ? 'F10 cannot be used here: Windows keeps it for the menu bar, so ZBrush never acts on it. Use F9, F11 or another F-key.' : '',
          onChange: v => { if (v) bridge().key = v; else { delete bridge().key; dropIfEmpty('bridge'); } commit(); paintZNote(); } }),
          mode === 'message' ? 'Not used in Message mode, but kept in case you switch back.' : 'Must be bound in ZBrush to Zplugin > ZOrbit > Apply. Use a bare F-key other than F10: ZBrush reads Ctrl and Shift as mask and smooth, and does not act on Alt combinations or F10 when ZOrbit sends them.'));
      };
      page.append(card('ZBrush bridge', 'How a pick reaches ZBrush',
        h('div', { class: 'fhint' }, 'Applies to the profile you are editing. Each profile keeps its own bridge key.'),
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
          : ['After installing, restart ZBrush, Ctrl+Alt+click Zplugin > ZOrbit > Apply, press ', h('b', null, zkey), ' and choose Preferences > Hotkeys > Store. (Only F9 works without this step.)'];
        znote.hidden = !zCount;
        znote.replaceChildren('ZBrush 2022 to 2025 cannot run the plugin that ZBrush 2026 loads, so they get a ZScript plugin with the same Zplugin > ZOrbit palette. It cannot receive messages, so every pick there uses the bridge key, whatever the mode above. ', ...bind, ' If your account cannot write to a ZBrush folder, installing there asks for administrator rights.');
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
    }
  };
  // Rebuilt after an undo, a revert or a reload: the control that had focus gets it back (found by its data-fk key, else its label), and the scroll stays.
  const fkOf = el => el.dataset.fk || [el.tagName, el.type || '', el.getAttribute('aria-label') || '', (el.closest('[role="radiogroup"]') || el).getAttribute('aria-label') || '', el.dataset.v || ''].join('|');
  const focusables = () => $$('input, button, select, textarea, [tabindex]', page);
  R.settings = () => {
    const act = document.activeElement, key = act && page.contains(act) ? fkOf(act) : null, top = scroll.scrollTop;
    build(); buildToc();
    scroll.scrollTop = top;
    const again = key && focusables().find(el => fkOf(el) === key && !el.disabled);
    if (again) again.focus({ preventScroll: true });
  };
  build();
  buildToc();
}

/* ================================================================== STATUS screen */
let statusTimer = null, statusBusy = false, appStarting = false, appSlow = false;   // appSlow: the start call has taken more than a few seconds (it may block for ten)
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
    rb.title = railTitle('status') + (S.appDown === true ? ' \u2013 The app is not running' : '');
  }
}
/* One quiet look at the status for the rail dot, from outside the Status screen. */
async function refreshAppDown() {
  try { const st = await call('get_status'); noteStatus(st); return st; } catch (e) { return null; }     // no dot
}

/* The label of a Start app button: the call can block for ten seconds, so after a few it says it is still going. */
const startLabel = () => (appSlow ? 'Still starting...' : 'Starting...');
/* Starts the app and says how it went. Shared by the Status and Setup screens. paint() is called when the starting state
   flips (appStarting and appSlow are the flags to read). Resolves to { log, starting }, or null when a start is already
   under way. log: the lines a failed start brought back (empty when it wrote none). starting: the app is still coming up,
   which is progress, not an error. The caller looks again at the status afterwards. */
async function startAppFlow({ paint }) {
  if (appStarting) return null;
  appStarting = true; appSlow = false; paint();
  const slow = setTimeout(() => { appSlow = true; paint(); }, 4000);
  let r = null;
  try { r = await call('start_app'); }
  catch (e) { toast('Could not start the app: ' + (e.message || e), { tone: 'warn', ms: 5000 }); }
  clearTimeout(slow);
  appStarting = false; appSlow = false; paint();
  const out = { log: [], starting: false };
  if (r && r.ok && r.restarted) toast(r.was ? `Restarted the app. It was ZOrbit ${r.was}.` : 'Restarted the app.', { tone: 'ok', ms: 4500 });
  else if (r && r.ok) toast('Started.', { tone: 'ok', ms: 3000 });
  else if (r && r.reason === 'older') toast(r.message || `The app running is ZOrbit ${r.was || 'older'}, older than this Studio, and could not be restarted.`, { tone: 'warn', ms: 6000 });
  else if (r && r.starting) { out.starting = true; toast(r.message || 'The app is still starting.', { ms: 6500 }); }
  else if (r && r.reason === 'failed') {
    out.log = (Array.isArray(r.lines) ? r.lines : Array.isArray(r.log) ? r.log : []).map(String);
    const msg = r.message || 'The app did not start.';
    toast(out.log.length ? msg.replace(/log:\s*$/, 'log are shown here.') : msg, { tone: 'warn', ms: 6000 });     // "...its log:" would point at nothing in a toast
  } else if (r) toast(r.message || (r.reason === 'zbrush' ? 'ZBrush must be running first.' : 'Could not start the app.'), { tone: 'warn', ms: 4500 });
  return out;
}
/* After a start that is still coming up: looks at the status once a second (up to 15 s) until the app shows as running or the user
   leaves the screen. look() is the screen's own refresh. */
async function watchStart(look) {
  const screen = S.screen;
  for (let i = 0; i < 15 && S.screen === screen; i++) {
    await sleep(1000);
    if (S.screen !== screen) return;
    await look();
    if (S.appDown === false) return;
  }
}

function buildStatusScreen(root) {
  root.replaceChildren();
  const page = h('div', { class: 'settings status' });
  const grid = h('div', { class: 'status-grid' });
  const logBox = h('div', { class: 'logbox mono', tabindex: '0', role: 'log', 'aria-live': 'off', 'aria-label': 'App log' });   // it is rebuilt every few seconds, so no live announcements
  const stamp = h('span', { class: 'stamp mono' });
  let startLog = [];                       // lines a failed start brought back; kept (highlighted) until the app runs or Start is pressed again
  let curLines = [];                       // the raw lines on screen now: what Copy log copies
  let cardLines = [];                      // [title, text] of the cards on screen now: what Copy report says about them
  let lastAsk = 0;                         // when the last get_status was asked

  // The Start app button lives on the app card. One element, moved into each freshly built card.
  const startBtn = h('button', { class: 'btn small primary start-btn', type: 'button', onclick: () => startApp() });
  const paintStart = st => {
    const running = !!(st && st.app_running);
    const older = running && !!st.app_older;                       // it runs, but it is an older ZOrbit than this Studio: the button restarts it
    const noZ = !!st && !st.zbrush_running && st.zbrush_check_ok !== false;
    const off = appStarting || (running && !older) || noZ || !st;
    startBtn.disabled = off;
    startBtn.replaceChildren(...(appStarting ? [h('span', { class: 'spin' }), startLabel()] : [icon(older ? 'refresh' : 'play', 12), older ? 'Restart app' : running ? 'Running' : 'Start app']));
    startBtn.classList.toggle('running', appStarting);
    startBtn.title = appStarting ? (appSlow ? 'Still waiting for the app. This can take up to ten seconds.' : 'Starting the app...') : older ? 'Stop the app and start this version' : running ? 'The app is already running' : noZ ? 'ZBrush must be running first'
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
    if (out.starting) watchStart(refresh);    // still coming up: look every second for a while, not every three
  }

  const folder = which => async () => { try { await call('open_folder', which); } catch (e) { toast('Could not open the folder.', { tone: 'warn' }); } };
  const copyLog = async () => {
    if (!curLines.length) { toast('The log is empty.', { ms: 1800 }); return; }
    const ok = await copyText(curLines.join('\n'));
    toast(ok ? `Copied ${curLines.length} line${curLines.length === 1 ? '' : 's'}` : 'Could not copy the log.', { tone: ok ? 'ok' : 'warn', ms: 2200 });
  };
  const copyReport = async ev => {
    const btn = ev.currentTarget;
    btn.disabled = true;
    try {
      const res = await call('get_report', cardLines);
      const ok = await copyText(res.text);
      toast(ok ? 'Copied the report, with your user name and folders hidden. Look it over before you post it.' : 'Could not copy the report.', { tone: ok ? 'ok' : 'warn', ms: 4000 });
    } catch (e) { toast('Could not make the report.', { tone: 'warn' }); }
    btn.disabled = false;
  };
  const reportBug = async () => {
    try { await call('open_url', await call('get_bug_url')); } catch (e) { toast('Could not open the bug form.', { tone: 'warn' }); }
  };
  page.append(h('div', { class: 'page-head' }, h('h1', null, 'Status'), h('p', null, 'Whether ZBrush and the ZOrbit app are running, and whether the bridge between them is healthy.')),
    grid,
    card('App log', 'Last lines of radiald.log', logBox,
      h('div', { class: 'btn-row between' }, h('div', { class: 'btn-row' },
        h('button', { class: 'btn', type: 'button', onclick: copyLog }, icon('copy', 13), 'Copy log'),
        h('button', { class: 'btn', type: 'button', title: 'Copy the versions, this screen and the logs for a bug report, with your user name and folders hidden', onclick: copyReport }, icon('copy', 13), 'Copy report'),
        h('button', { class: 'btn', type: 'button', title: 'Open the bug form on GitHub, with the versions filled in. Paste the report into it.', onclick: reportBug }, icon('external', 13), 'Report a bug'),
        h('button', { class: 'btn', type: 'button', title: 'Where the app log is kept', onclick: folder('data') }, icon('folder', 13), 'Open logs folder'),
        h('button', { class: 'btn', type: 'button', title: 'The folder of the profile you are editing', onclick: folder('config') }, icon('external', 13), 'Open menus folder')),
        h('span', { class: 'live' }, h('i', { class: 'livedot' }), 'Auto-refresh every 3 s ', stamp))));
  root.append(h('div', { class: 'settings-scroll' }, page));

  const stat = (title, ok, text, sub, tone, extra) => {
    cardLines.push([title, sub ? `${text}. ${sub}` : text]);
    return h('div', { class: 'scard ' + (tone || (ok ? 'ok' : 'off')) }, h('div', { class: 'micro' }, title),
      h('div', { class: 'sval' + (extra ? ' has-act' : '') }, h('i', { class: 'sdot' }), text, extra || null), sub ? h('div', { class: 'ssub' }, sub) : null);
  };
  const tickStamp = () => {
    if (!S.statusAt) { setText(stamp, ''); return; }
    const s = Math.max(0, Math.floor((Date.now() - S.statusAt) / 1000));
    setText(stamp, 'Updated ' + (s < 90 ? s + ' s' : Math.round(s / 60) + ' min') + ' ago');
  };
  const paint = st => {
    if (!st) return;
    const l = st.listener;
    const keyOnly = st.bridge_mode === 'key' || !!st.legacy_only;      // a listener is not part of the picture
    const unsure = st.zbrush_check_ok === false;                       // the process look-up itself failed: do not claim ZBrush is off
    const closed = !unsure && st.zbrush_running === false;             // no ZBrush: the plugin's listener cannot be there, so a leftover record is no problem
    const ltone = keyOnly || closed ? 'neutral' : (!l ? 'off' : (l.alive && l.verified ? 'ok' : 'warn'));
    const ltext = keyOnly ? 'Not needed (key bridge)' : (closed ? 'ZBrush closed' : (!l ? 'Not found' : (!l.alive ? 'Stale' : (l.verified ? 'Connected' : 'Found, unverified'))));
    const lsub = keyOnly ? 'Picks arrive through the bridge key'
      : (closed ? 'The plugin’s listener only exists while ZBrush runs.'
        : (!l ? 'The plugin in ZBrush has not set up its listener window. Restart ZBrush so the plugin loads.'
          : (!l.alive ? 'The plugin’s listener window is gone. Restart ZBrush.'
            : (l.verified ? 'Picks are delivered by message.' : 'The plugin’s listener is there, but it has not answered a pick yet.'))));
    const hadFocus = document.activeElement === startBtn;
    paintStart(st);
    cardLines = [];
    grid.replaceChildren(
      unsure ? stat('ZBrush', false, 'Could not check', 'Studio could not tell whether ZBrush is running.', 'neutral')
        : stat('ZBrush', st.zbrush_running, st.zbrush_running ? 'Running' : 'Not running', st.zbrush_running ? null : 'The app starts together with ZBrush.'),
      stat('ZOrbit app',st.app_running, st.app_running ? 'Running' : 'Not running',
        st.app_running ? (st.app_older ? `The app running is ZOrbit ${st.app_version || 'older'}, older than this Studio.` : 'Listening for your hotkeys.') : (st.zbrush_running || unsure ? 'Press Start app to launch it.' : 'Open ZBrush first; the app starts with it.'), st.app_running && st.app_older ? 'warn' : null, startBtn),
      stat('Bridge listener', ltone === 'ok', ltext, lsub, ltone),
      h('div', { class: 'scard last' }, h('div', { class: 'micro' }, 'Last pick'), h('div', { class: 'sval mono small' }, st.last_pick || 'Nothing picked yet'), h('div', { class: 'ssub' }, 'The most recent item sent to ZBrush.')));
    cardLines.push(['Last pick', st.last_pick || 'Nothing picked yet']);
    if (hadFocus && !startBtn.disabled) startBtn.focus();
    if (st.app_running) startLog = [];
    const atBottom = logBox.scrollTop + logBox.clientHeight >= logBox.scrollHeight - 8;
    const backend = (st.app_log || []).map(String);
    const extra = startLog.filter(x => !backend.includes(x));
    curLines = backend.concat(extra).slice(-LOG_LINES);
    const forced = new Set(extra);
    const today = localDate(new Date());
    const logSig = today + '\u0001' + curLines.join('\n') + '\u0001' + extra.join('\n');
    if (logSig === logBox._sig) { tickStamp(); return; }           // same lines: leave the box alone, so a selection in it survives
    logBox._sig = logSig;
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
    catch (e) { cardLines = [['Status', 'Unavailable']]; grid.replaceChildren(h('div', { class: 'scard off' }, h('div', { class: 'micro' }, 'Status'), h('div', { class: 'sval' }, h('i', { class: 'sdot' }), 'Unavailable'), h('div', { class: 'ssub' }, String(e.message || e)))); }
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
  if (!rb || (d && d.failed)) return;                       // a failed check says nothing about the installs: the dot stays as it was
  const bad = !!(d && d.hard_fail);
  rb.classList.toggle('has-badge', bad);
  rb.title = railTitle('setup') + (bad ? ' – Something needs attention' : '');
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
const PICK_VIA = { listener: 'the plugin', key: 'the bridge key', zscript: 'ZScript', 'zscript-fallback': 'ZScript (by script)' };
const ADMIN_ZBRUSH = 'ZBrush is running as administrator, so ZOrbit cannot see its window and the ring will not open. Close ZBrush and start it without Run as administrator.';

/* The bridge key as the user would say it: what Settings holds, else the default. */
const bridgeKeyName = () => String((S.cfg && S.cfg.bridge && S.cfg.bridge.key) || 'F9').trim() || 'F9';

/* What to tell the user when the app did not send a pick. reason is the text radiald.py writes to activity.json
   (see Daemon.send and press_bridge_key); an unknown one gets a general sentence that points at the log. */
function unsentHint(reason, key) {
  const r = String(reason || '');
  if (/^no live listener/.test(r)) return { text: 'The plugin is not answering in ZBrush, and the bridge mode is Message, so nothing was sent. Restart ZBrush so the plugin loads, or set the bridge mode to Auto.', settings: true };
  if (/not in front/.test(r)) return { text: 'ZBrush was not the front window when you picked, so nothing was sent. Click ZBrush once, press ' + key + ' over the canvas and pick again.' };
  if (/request file/.test(r)) return { text: 'ZOrbit could not save the pick to its data folder, so nothing was sent. Check that the folder can be written to; Status can open it.', status: true };
  if (/did not take/.test(r)) return { text: 'ZBrush did not take the pick, by the bridge key or by script. Check that Zplugin > ZOrbit > Apply has the bridge key (' + bridgeKeyName() + ') as its hotkey.', settings: true };
  return { text: 'ZOrbit could not send that pick to ZBrush. The app log on Status says why.', status: true };
}

/* The menu the Setup screen talks about: the one on Q, else the first with a hotkey, else the first. */
function setupMenu() {
  const menus = (S.cfg && S.cfg.menus) || {}, ids = Object.keys(menus), hk = id => menus[id] && menus[id].hotkey;
  const id = ids.find(i => hkNorm(hk(i)) === 'q') || ids.find(i => hk(i)) || ids[0];
  return id ? { id, title: menus[id].title || id, hotkey: hk(id) || '' } : null;
}

/* The three steps from one get_setup answer. Pure: the same data gives the same steps, and every field in a step is
   something that is drawn (nothing that ticks, like ages), so JSON of a step tells whether it needs painting again.
   ctx: { menu: setupMenu() (its hotkey is the key step 3 names), startLog: the lines a failed Start app brought back }. */
function deriveSteps(d, tryFrom, ctx) {
  const installs = d.installs || [], unmatched = d.unmatched_procs || [], env = d.env || {}, zb = d.zbrush || {};
  const now = typeof d.now === 'number' ? d.now : Date.now() / 1000;
  const topProc = i => { const have = (i.procs || []).map(p => p.state); return PROC_PRIORITY.find(s => have.includes(s)) || null; };
  const plugin = i => i.plugin || {};
  const list = names => (names.length < 3 ? names.join(' and ') : names.slice(0, -1).join(', ') + ' and ' + names[names.length - 1]);

  /* 1. ZBrush found */
  const ready = installs.filter(i => i.ready), unready = installs.filter(i => !i.ready);
  // The title says what is true: a step that is not done must not read as a done one.
  const s1 = { id: 'found', title: ready.length ? 'ZBrush found' : (installs.length ? 'ZBrush found, plugin not set up' : 'No ZBrush found'),
    state: ready.length ? 'ok' : (installs.length ? 'warn' : 'off'),
    modern: installs.filter(i => i.kind === 'modern').map(i => {
      const st = plugin(i).state;
      return { name: i.name, path: i.path, added: !!i.added, proc: topProc(i),
        tag: st === 'ok' ? 'Plugin registered' : (st === 'no_bridge' ? 'Plugin folder missing' : 'Plugin not registered'),
        tone: st === 'ok' ? 'cyan' : (st === 'no_bridge' ? 'dim' : 'amber'),
        fix: !!env.can_fix && st !== 'ok' && st !== 'no_bridge' };
    }),
    legacy: { bundled: !!d.bundled, installs: installs.filter(i => i.kind === 'legacy').map(i => ({ name: i.name, path: i.path, added: !!i.added,
      installed: !!plugin(i).installed, current: !!plugin(i).current, zplugs: plugin(i).zplugs, proc: topProc(i) })) },
    others: (env.other_zorbit || []).map(o => ({ path: o.path, exists: o.exists !== false })),
    bridgeMissing: !!(d.bridge && d.bridge.kind === 'missing') };
  // Done, but with a row still worth seeing: a ZBrush without the plugin, an update to install, or another ZOrbit registered. The step then stays open.
  s1.unfinished = unready.length > 0 || s1.legacy.installs.some(z => z.installed && !z.current) || s1.others.length > 0 || s1.bridgeMissing;
  s1.detail = ready.length
    ? list(ready.map(i => i.name)) + (ready.length === 1 ? ' is ready.' : ' are ready.') + (unready.length ? ' ' + list(unready.map(i => i.name)) + (unready.length === 1 ? ' still needs' : ' still need') + ' the plugin.' : '')
    : (installs.length ? 'ZBrush was found, but the ZOrbit plugin is not set up for it yet.' : 'No ZBrush was found. Add its folder if you have one.');

  /* 2. Plugin loaded in ZBrush */
  const procs = [];
  for (const i of installs) for (const p of (i.procs || [])) procs.push({ name: i.name, ready: !!i.ready, state: p.state, why: p.why || '' });
  const adminProcs = unmatched.filter(u => u.elevated !== false);
  const elevated = adminProcs.length > 0;
  // A ZBrush running as administrator cannot be read, but a verified listener window it owns shows the plugin did load.
  for (const u of adminProcs) if (u.loaded) procs.push({ name: 'ZBrush', ready: true, state: 'loaded', why: '' });
  const worst = PROC_PRIORITY.slice(1).map(s => procs.find(p => p.state === s)).find(Boolean);
  const loaded = procs.filter(p => p.state === 'loaded');
  const s2 = { id: 'loaded', title: loaded.length ? 'Plugin loaded in ZBrush' : 'Plugin not loaded in ZBrush', locked: false,
    rows: procs.map(p => ({ name: p.name, state: p.state, why: p.why })),
    elevated,
    app: { running: !!(d.app && d.app.running), zbrush: !!zb.running, checkOk: zb.check_ok !== false },
    startLog: Array.isArray(ctx.startLog) ? ctx.startLog : [] };
  // Done, but with its body still worth seeing: the app is not running (Start app is in there), a failed start's log, or a ZBrush run as administrator. The step then stays open.
  s2.unfinished = !s2.app.running || s2.startLog.length > 0 || elevated;
  if (loaded.length) {
    const names = [...new Set(loaded.map(p => p.name))];
    s2.state = 'ok'; s2.detail = list(names) + (names.length === 1 ? ' has the plugin.' : ' have the plugin.');
  } else if (!procs.length && !adminProcs.length && unmatched.length) {
    s2.state = 'warn'; s2.detail = 'ZBrush is running from a folder Studio does not know, so it cannot check the plugin there. Add that folder with Add a ZBrush folder in step 1.';
  } else if (!procs.length && !adminProcs.length) {
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
    s2.state = 'warn'; s2.detail = ADMIN_ZBRUSH;
  }

  /* 3. Try the ring */
  const a = d.activity || null, lp = d.last_pick || null;
  const opened = !!(a && a.ring && a.ring.at > tryFrom);
  const pk = a && a.pick && a.pick.at > tryFrom && a.pick.source === 'ring' ? a.pick : null;
  const sent = !!(pk && pk.sent);
  const did = !!(sent && lp && lp.ok && lp.at >= pk.at - 2 && (lp.seq == null || pk.seq == null || lp.seq === pk.seq));
  const key = (ctx.menu && ctx.menu.hotkey) || 'Q';
  const bridgeKey = bridgeKeyName();
  let hint = null;
  if (pk && !sent) hint = unsentHint(pk.reason, key);
  else if (sent && !did && now - pk.at > 4) {
    // ZBrush did answer, with a failure: the bridge log line says what (the same seq, so it is this pick)
    const failed = !!(lp && lp.ok === false && pk.seq != null && lp.seq === pk.seq && lp.at >= pk.at - 2);
    hint = failed ? { text: lp.text } : ({ key: { text: 'ZBrush did not react to the bridge key (' + bridgeKey + '). Bind it to Zplugin > ZOrbit > Apply (Settings > ZBrush bridge, in Full mode).', settings: true },
      listener: { text: 'The plugin did not act on the pick. Open the logs folder from Status and read bridge.log.', status: true },
      zscript: { text: 'ZBrush did not react to ' + bridgeKey + '. Check that Zplugin > ZOrbit > Apply has that hotkey.' } }[String(pk.route).replace(/-fallback$/, '')]
      || { text: 'ZBrush did not confirm the pick. Open the logs folder from Status and read bridge.log.', status: true });
  }
  if (!hint && elevated && !opened) hint = { text: ADMIN_ZBRUSH };            // the ring never opens, so there is no pick to explain
  const locked3 = s2.state !== 'ok';
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
  return [s1, s2, s3];
}

const USER_GUIDE_URL = 'https://zorbit.lol/docs/';
const SETUP_WHERE = [
  ['Menus', 'Edit the rings and what each slot does', 'menus'],
  ['Library', 'Every brush ZBrush can load, with tags', 'library'],
  ['Look', 'Ring size, slot shape, labels, colours and the open animation', 'look'],
  ['Settings', 'Theme, behaviour and the browser hotkey. Full mode adds the bridge', 'settings'],
  ['Status', 'Is everything running, and the logs', 'status'],
  ['User guide', 'The whole manual, at zorbit.lol/docs', null]];

function buildSetupScreen(root) {
  root.replaceChildren();
  const st = S.setup = S.setup || { data: null, tryFrom: Date.now() / 1000, busy: false, lastAsk: 0, open: new Set() };   // tryFrom outlives a screen switch; Start over resets it
  const first = S.prefs.setup_done === false;       // decided once: the footer must not swap itself when the switch below is used
  const list = h('ol', { class: 'setup-steps', 'aria-label': 'Setup steps' });
  const errBox = h('div', { hidden: true, role: 'alert' });
  const foot = h('div', { class: 'setup-foot' });
  // Always there, above the footer: where to go once the steps are done. The description is the tooltip.
  const next = h('section', { class: 'setup-next', 'aria-label': 'Next' },
    h('div', { class: 'micro' }, 'Next'),
    h('div', { class: 'setup-chips' }, ...SETUP_WHERE.map(([name, text, screen]) => h('button', { class: 'chip', type: 'button', title: text,
      onclick: screen ? () => showScreen(screen) : async () => { try { await call('open_url', USER_GUIDE_URL); } catch (e) { toast('Could not open the link.', { tone: 'warn' }); } } },
      name, screen ? null : icon('external', 12))),
      h('button', { class: 'btn small', type: 'button', title: 'A short tour of this window', onclick: () => startTour() }, 'Take the tour')),
    h('div', { class: 'fhint' }, 'Studio starts in Simple mode, which shows the settings most people use. The switch at the top turns on Full mode.'));
  root.append(h('div', { class: 'settings-scroll' }, h('div', { class: 'settings setup' },
    h('div', { class: 'page-head' }, h('h1', null, 'Setup'), h('p', null, 'Everything ZOrbit needs, and what still needs doing.')), errBox, list, next, foot)));

  const els = new Map();
  let steps = null;                                 // the last steps drawn: tells the timer whether step 3 is being waited on

  // The Start app button lives on step 2. One element, moved into each freshly built step.
  const startBtn = h('button', { class: 'btn small primary start-btn', type: 'button', onclick: () => startApp() });
  const paintStart = () => {
    const d = st.data, running = !!(d && d.app && d.app.running);
    const noZ = !!d && !(d.zbrush && d.zbrush.running) && !(d.zbrush && d.zbrush.check_ok === false);
    startBtn.disabled = appStarting || running || noZ || !d;
    startBtn.replaceChildren(...(appStarting ? [h('span', { class: 'spin' }), startLabel()] : [icon('play', 12), running ? 'Running' : 'Start app']));
    startBtn.classList.toggle('running', appStarting);
    startBtn.title = appStarting ? (appSlow ? 'Still waiting for the app. This can take up to ten seconds.' : 'Starting the app...') : running ? 'The app is already running' : noZ ? 'ZBrush must be running first' : 'Start the ZOrbit app';
    if (appStarting) startBtn.setAttribute('aria-busy', 'true'); else startBtn.removeAttribute('aria-busy');
  };
  async function startApp() {
    if (appStarting) return;
    st.startLog = [];
    const out = await startAppFlow({ paint: paintStart });
    if (!out) return;
    st.startLog = out.log;                          // shown in step 2 until the app runs or Start app is pressed again
    await ask(true);
    if (out.starting) watchStart(() => ask(false));
  }

  // The state is a glyph and a name as well as a colour: a tick, a warning triangle, a cross or a clock, read out as "OK", "Needs attention", "Not working" or "Not checked yet".
  const CHECK_STATE = { ok: ['check', 'OK'], warn: ['alert', 'Needs attention'], off: ['x', 'Not working'], pending: ['clock', 'Not checked yet'] };
  const subCheck = (tone, text, sub, extra) => h('div', { class: 'sub-check ' + tone }, (([ico, word]) => h('span', { class: 'sdot sglyph', role: 'img', title: word, 'aria-label': word }, icon(ico, 11)))(CHECK_STATE[tone] || CHECK_STATE.warn),
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
        const forget = r.added ? iconBtn('x', 'Forget this folder', async () => {          // a folder added by hand can be taken off the list again
          forget.disabled = true;
          try { const res = await call('forget_zbrush_folder', r.path); toast(res.message || (res.ok ? 'Forgot that folder.' : 'That did not work.'), { tone: res.ok ? 'ok' : 'warn', ms: 4000 }); }
          catch (e) { toast('Could not forget the folder: ' + e.message, { tone: 'warn' }); }
          ask(true);
        }) : null;
        return h('div', { class: 'zrow' }, h('div', { class: 'grow' }, h('div', { class: 'zname' }, r.name, h('span', { class: 'tag ' + r.tone }, r.tag), procTag(r.proc)), h('div', { class: 'zpath mono', title: r.path }, r.path)),
          fix || forget ? h('div', { class: 'btn-row' }, fix, forget) : null);
      })));
      const box = h('div', { class: 'zrows' });
      const lz = legacyRows(box, { refresh: () => ask(true), extra: z => procTag(z.proc) });
      if (s.legacy.installs.length) { lz.paint(s.legacy); out.push(box); }
      if (s.bridgeMissing) out.push(note('The plugin folder is missing from this install. Reinstall ZOrbit.', true));
      for (const o of s.others) out.push(note('Also registered: ' + o.path + (o.exists
        ? ' (another ZOrbit folder in ZBRUSH_PLUGIN_PATH; ZBrush loads both, so remove the old one in Windows’ environment variables)'
        : ' (missing; an old entry in ZBRUSH_PLUGIN_PATH that you can remove in Windows’ environment variables)')));
      out.push(h('div', { class: 'btn-row' }, h('button', { class: 'btn small' + (s.state === 'off' ? ' primary' : ''), type: 'button', onclick: () => lz.addFolder() }, icon('folder', 12), 'Add a ZBrush folder...')));
      return out;
    },
    loaded(s) {
      const tone = { loaded: 'ok', restart: 'warn', starting: 'warn', unknown: 'warn', not_loaded: 'off' };
      const rows = s.rows.map(p => subCheck(tone[p.state] || 'warn', [p.name, ' ', procTag(p.state)], p.why && !['loaded', 'restart', 'starting'].includes(p.state) && p.why !== s.detail ? p.why : ''));      // the step's own line already says it for a restart or a start, and for the worst of the rest
      if (s.elevated) rows.push(subCheck('warn', 'ZBrush is running as administrator', s.state === 'ok' ? 'ZOrbit cannot see its window, so the ring will not open. Close ZBrush and start it without Run as administrator.' : ''));
      rows.push(subCheck(s.app.running ? 'ok' : (s.app.zbrush ? 'warn' : 'pending'), ['App ', h('span', { class: 'tag ' + (s.app.running ? 'cyan' : 'dim') }, s.app.running ? 'Running' : 'Not running')],
        s.app.running ? 'Listening for your hotkeys.' : (s.app.zbrush || !s.app.checkOk ? 'Press Start app to launch it.' : 'It starts together with ZBrush.'), startBtn));
      const out = [h('div', { class: 'sub-checks' }, ...rows)];
      if (s.startLog.length && !s.app.running) {                  // the last Start app failed: what the app wrote, and where the whole log is
        out.push(note('The app did not start. The last lines of its log:', true),
          h('div', { class: 'logbox mono start-log', tabindex: '0', role: 'log', 'aria-label': 'Last lines of the app log' }, s.startLog.map(l => h('div', { class: 'logline err' }, l))),
          h('div', { class: 'btn-row' }, h('button', { class: 'btn small', type: 'button', onclick: () => showScreen('status') }, 'Open Status')));
      }
      return out;
    },
    try(s) {
      const out = [h('div', { class: 'sub-checks' }, ...s.checks.map(c => subCheck(c.ok ? 'ok' : 'pending', c.label, c.sub)))];
      if (s.hint) {
        out.push(note(s.hint.text, true));
        if (s.hint.settings) out.push(h('div', { class: 'btn-row' }, h('button', { class: 'btn small', type: 'button', onclick: () => openSettingsCard('set-zbrush-bridge') }, 'Open Settings')));
        if (s.hint.status) out.push(h('div', { class: 'btn-row' }, h('button', { class: 'btn small', type: 'button', onclick: () => showScreen('status') }, 'Open Status')));
      }
      out.push(h('div', { class: 'btn-row' }, h('button', { class: 'btn small', type: 'button', title: 'Forget what happened so far and watch for a new try',
        onclick: () => { st.tryFrom = Date.now() / 1000; paint(true); } }, icon('refresh', 12), 'Start over')));
      return out;
    } };

  /* A step that is done folds to its head (a tick, the title and one line); the user opens it again with a click, and st.open
     remembers that. A step that needs attention, is waiting or is locked never folds: its body is the thing to read. */
  const foldable = s => s.state === 'ok' && !s.unfinished;
  const isFolded = s => foldable(s) && !st.open.has(s.id);
  const renderStep = (el, s, n) => {
    const parts = String(s.detail || '').split('{key}');
    const detail = h('div', { class: 'sdetail' }, ...parts.flatMap((t, i) => (i ? [hkChips(s.key || 'Q', 'sm'), t] : [t])));
    const body = ((own(bodies, s.id) ? bodies[s.id](s) : null) || []).filter(Boolean);
    const can = foldable(s) && body.length > 0, folded = can && isFolded(s), bodyId = 'sbody-' + s.id;
    const headKids = [h('b', { class: 'stitle' }, s.title), detail];
    const head = can
      ? h('button', { class: 'sfold', type: 'button', 'aria-expanded': String(!folded), 'aria-controls': bodyId, onclick: () => {
        if (st.open.has(s.id)) st.open.delete(s.id); else st.open.add(s.id);
        const cur = steps && steps.find(x => x.id === s.id);
        if (!cur) return;
        draw(el, cur, n);
        const again = el.querySelector('.sfold'); if (again) again.focus();         // the button was rebuilt: the keyboard stays on it
      } }, h('span', { class: 'schev', 'aria-hidden': 'true' }, icon(folded ? 'chevR' : 'chevD', 14)), h('span', { class: 'shead' }, ...headKids))
      : h('div', { class: 'shead' }, ...headKids);
    el.replaceChildren(h('div', { class: 'snum', 'aria-hidden': 'true' }, s.state === 'ok' ? icon('check', 14) : String(n)),
      h('div', { class: 'smain' }, head, body.length ? h('div', { class: 'sbody', id: bodyId, hidden: folded }, ...body) : null));
  };
  /* One step's li: its classes, its signature (what is drawn, folded or not) and its content. */
  const sigOf = s => JSON.stringify(s) + (isFolded(s) ? '|folded' : '');
  function draw(el, s, n) {
    el.className = 'sstep ' + s.state + (s.locked ? ' locked' : '') + (isFolded(s) ? ' folded' : '');
    el._sig = sigOf(s);
    renderStep(el, s, n);
  }

  // Draws what changed. force: redraw every step (after an action of ours), else a step that is mid-action keeps its buttons.
  function paint(force) {
    const d = st.data;
    if (!d) return;
    steps = deriveSteps(d, st.tryFrom, { menu: setupMenu(), startLog: st.startLog });
    steps.forEach((s, i) => {
      let el = els.get(s.id);
      if (!el) { el = h('li', { class: 'sstep', dataset: { step: s.id } }); els.set(s.id, el); list.append(el); }
      if (!force && (el._sig === sigOf(s) || el.querySelector('.btn.running'))) { el.className = 'sstep ' + s.state + (s.locked ? ' locked' : '') + (el.classList.contains('folded') ? ' folded' : ''); return; }   // the body is not redrawn, so the fold class stays as drawn
      draw(el, s, i + 1);
    });
    paintStart();
  }
  const paintErr = () => {
    errBox.hidden = !st.err; errBox.style.marginBottom = st.err ? '12px' : '';
    errBox.replaceChildren(...(st.err ? [h('div', { class: 'scard off' }, h('div', { class: 'micro' }, 'Setup'), h('div', { class: 'sval' }, h('i', { class: 'sdot' }), 'Setup check unavailable'), h('div', { class: 'ssub' }, st.err), st.data ? h('div', { class: 'ssub' }, 'The steps below are from the last check that worked.') : null)] : []));
  };
  // One get_setup. A caller that forces one waits for a poll already in flight, so what it changed is in the answer.
  async function ask(force) {
    while (st.busy) { if (!force) return; await sleep(60); }
    st.busy = true; st.lastAsk = Date.now();
    try {
      const d = await call('get_setup');
      if (!d || d.failed || !Array.isArray(d.installs)) {         // the check itself failed: say so, keep the last good answer (if any) on screen, and keep asking
        st.err = (d && d.error) || 'The setup check failed (see studio.log).';
      } else {
        st.data = d; st.err = '';
        if (d.app && d.app.running) st.startLog = [];
        noteSetupStatus(d); setSetupBadge(d);
        if (S.screen === 'setup') paint(force);
      }
    } catch (e) { st.err = String(e.message || e); }
    finally { st.busy = false; }
    // An action (Fix, Install, Forget...) waits for this answer to redraw its button. A failed check still redraws the
    // last good steps, so a button never stays on "Fixing..." while the checks keep failing.
    if (st.err && force && st.data && S.screen === 'setup') paint(true);
    paintErr();
  }
  R.setup = () => ask(true);

  // The footer is built once: Finish / Skip on a first run, else a Done tag and a switch to bring Setup back.
  const menuNow = setupMenu();
  const finish = async withToast => {
    if (!await setPref('setup_done', true)) return;
    if (withToast) {                             // the app runs once ZBrush has loaded the plugin; before that, Q does nothing yet
      const key = (menuNow && menuNow.hotkey) || 'Q', live = !!(st.data && st.data.app && st.data.app.running);
      toast(live ? `Setup done. Press ${key} over ZBrush whenever you like.` : `Setup done. Once ZBrush has started with the plugin, press ${key} over it.`, { tone: 'ok', ms: 4500 });
    }
    showScreen('menus');
    offerTour().catch(() => {});
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
const RING_CARD = { tap_ms: 'set-behaviour', timeout_s: 'set-behaviour', flick: 'set-behaviour', hover_submenus: 'set-behaviour', hint: 'set-behaviour', tag_limit: 'set-behaviour' };
/* The ring keys the Look screen shows, with the group each one is in (look-screen.js has the same groups). */
const RING_LOOK = { radius: 'slots', slot: 'slots', dead_zone: 'slots', slot_shape: 'slots', slot_corner: 'slots', border_width: 'slots', icon_scale: 'slots', size: 'slots', fill_color: 'slots', border_color: 'slots',
  hub: 'hub', hub_style: 'hub', hub_color: 'hub', hub_glow: 'hub', glow_color: 'glow', glow_opacity: 'glow', labels: 'labels', label_color: 'labels', colors: 'colours',
  tag_colors: 'tags', tag_band: 'tags', tag_band_opacity: 'tags', tag_glow_opacity: 'tags', tag_tint_opacity: 'tags', tag_tint_style: 'tags', tag_tint_blend: 'tags', when_full: 'when_full', animation: 'opening' };
/* Where a problem with a look setting leads: the Look screen at a level ('global', 'menu' with menuId, 'preset' with name), at the group and control of key. */
const lookTarget = (key, where = {}) => Object.assign({ kind: 'look', level: 'global', key, group: RING_LOOK[key] }, where);
const RING_NAME = { radius: 'Ring radius', slot: 'Slot size', dead_zone: 'Dead zone', hub: 'Hub', tap_ms: 'Tap time', timeout_s: 'Auto-close', flick: 'Flick to pick',
  hover_submenus: 'Open submenus on hover', hint: 'Hint line', tag_limit: 'Tag fan slots', animation: 'Open animation', labels: 'Labels', slot_shape: 'Slot shape', tag_colors: 'Tag colours',
  slot_corner: 'Corner roundness', border_width: 'Rim width', icon_scale: 'Icon size', hub_style: 'Hub style', hub_color: 'Hub colour', hub_glow: 'Hub glow',
  glow_color: 'Glow colour', glow_opacity: 'Glow opacity', label_color: 'Label colour', when_full: 'When full', size: 'Size', fill_color: 'Fill colour', border_color: 'Rim colour',
  tag_band: 'Band', tag_band_opacity: 'Band opacity', tag_glow_opacity: 'Glow opacity', tag_tint_opacity: 'Icon tint opacity', tag_tint_style: 'Icon tint style', tag_tint_blend: 'Icon tint blend' };
const isPlainObj = o => o !== null && typeof o === 'object' && !Array.isArray(o);
const unq = s => String(s).replace(/^(['"])(.*)\1$/, '$2');
/* "(did you mean mode?)" at the end of a loader message, as a sentence of its own ('' when there is none). */
const didYouMean = s => { const d = /\(did you mean (.+)\?\)\s*$/.exec(String(s)); return d ? ' Did you mean ' + d[1] + '?' : ''; };
/* What is wrong with one look setting, from the loader's text after "<key>: " (nm is the setting's name); null when it is not one it knows. */
function lookValueReason(nm, body) {
  let r;
  if ((r = /^(.+) must be a (?:whole )?number from (\S+) to (\S+)$/s.exec(body))) return `${nm} ${unq(r[1])} is outside ${r[2]} to ${r[3]}`;
  if ((r = /^(.+) must be true or false$/s.exec(body))) return `${nm} must be on or off, not ${unq(r[1])}`;
  if ((r = /^(.+) unknown; one of /s.exec(body))) return `${nm} ${unq(r[1])} is not one of the available choices`;
  if ((r = /^(.+) is not a #rrggbb colour or a theme colour/s.exec(body))) return `${nm} ${unq(r[1])} is not a #rrggbb value or a theme colour`;
  if (body.startsWith('is a ring setting, not part of a look')) return `${nm} is a ring setting, not part of a look, so it is ignored here`;
  if (body.startsWith('unknown setting')) return `${nm} is not a known look setting`;
  return null;
}
const lookLabel = key => RING_NAME[key] || key;
function describeProblem(raw) {
  const out = (text, target) => ({ text, raw, target: target || null });
  const cfgMenus = (S.cfg && S.cfg.menus) || {};
  const titleOf = id => '\u201c' + ((menuOf(id) && menuOf(id).title) || id) + '\u201d';
  const known = id => !!menuOf(id) && typeof menuOf(id) === 'object';
  let m;
  /* What is wrong with one item, in words that follow "Menu item 3": t is the loader's text after the item number (": ..." or " step 2: ..."), and null when it is not one it knows. */
  const itemReason = t => {
    let r;
    if ((r = /^ step (\d+)(: .*)$/s.exec(t))) {                      // a step inside a Steps item: the same reasons, led by the step number
      if (r[2].startsWith(': steps cannot open menus')) return `step ${r[1]} cannot be a submenu, more steps, an auto slot, a tag, the browser or a Recent item`;
      const inner = itemReason(r[2]);
      return inner ? `step ${r[1]} ${inner}` : null;
    }
    if (t === ': not an object') return 'is not an object';
    if (t.startsWith(': needs exactly one of ')) return 'needs exactly one action (a brush, a press and so on), no more and no less';
    if (t === ": 'set' needs a 'value'") return 'needs a value';
    if (t === ": 'set' value must be a number") return 'has a value that is not a number';
    if (t.startsWith(": 'steps' must be a non-empty list")) return 'needs at least one step, and steps cannot hold other steps';
    if (t.startsWith(": 'auto' must be one of ")) return 'has an auto slot that is not supported (only brushes can be auto)';
    if (t.startsWith(": 'recent' must be ")) return 'is a Recent item that does not say what it shows (projects, tools or both)';
    if (t.startsWith(": 'browser' must be a string")) return 'has a browser filter that is not a tag';
    if (t.startsWith(": browser 'kind' must be one of ")) return 'opens a browser tab that does not exist';
    if (t.startsWith(': capture folder ')) return 'has a capture folder that cannot be used: ' + t.slice(': capture folder '.length);
    if ((r = /^: (tool|project|layout) must be on this PC, not a network path$/.exec(t))) return `has a ${r[1]} on a network path. Use a file on this PC`;
    if ((r = /^: (tool|project|layout) '(.*)' must be a full path, such as (.*)$/s.exec(t))) return `has the ${r[1]} ${r[2]}, which is not a full path. Use a path such as ${r[3]}`;
    if ((r = /^: project '(.*)' must be a \.zpr file or a folder$/s.exec(t))) return `has the project ${r[1]}, which must be a .zpr file or a folder`;
    if ((r = /^: (tool|project|layout) '(.*)' must be a (\.\w+) file$/s.exec(t))) return `has the ${r[1]} ${r[2]}, which must be a ${r[3]} file`;
    if ((r = /^: '(\w+)' must be a non-empty string$/.exec(t))) return 'needs a ' + (own(TARGET_NOUN, r[1]) ? TARGET_NOUN[r[1]] : 'target');
    if ((r = /^: (\w+) name (.+) must not contain /s.exec(t))) return `has the ${r[1]} name ${r[2]}, which looks like a path. Use only the name, without \\ / : or ..`;
    if ((r = /^: submenu (.+) does not exist$/s.exec(t))) return `opens the submenu ${unq(r[1])}, which does not exist`;
    if ((r = /^: submenu (.+) has no usable items$/s.exec(t))) return `opens ${titleOf(unq(r[1]))}, which has no usable items, so this slot stays empty`;
    if ((r = /^: unknown setting (.+)$/s.exec(t))) return `has an unknown setting ${r[1].replace(/\s*\(did you mean .*$/s, '')}.` + didYouMean(r[1]);
    if ((r = /^: tag (.+) does not exist; the slot stays empty$/s.exec(t))) return `uses the tag ${unq(r[1])}, which does not exist, so the slot stays empty`;
    if ((r = /^: tag (.+) does not exist; the browser opens unfiltered$/s.exec(t))) return `filters by the tag ${unq(r[1])}, which does not exist, so the browser opens unfiltered`;
    if (t.startsWith(': style must be an object')) return 'has a style that is not an object of look settings, so it is ignored';
    if ((r = /^: style\.(\w+): (.*)$/s.exec(t))) { const why = lookValueReason(lookLabel(r[1]), r[2]); return 'has a style setting that is ignored: ' + (why || lookLabel(r[1]) + ': ' + r[2]); }
    if (/^: unknown setting 'glow' \(glow is now style\.glow_color\)$/.test(t)) return 'has a glow colour saved the old way. Set it again under Glow';
    if (/^: icon .+ must be a plain file path/s.test(t)) return 'has an icon on a network path. Use a file on this PC';
    if ((r = /^: icon (.+) must be a full path, such as /s.exec(t))) return `has the icon ${r[1]}, which is not a full path. Use a path such as C:\\Art\\clay.png, or a brush name`;
    if ((r = /^: icon file not found: (.+)$/s.exec(t))) return `has an icon file that was not found (${r[1]}). Check the path`;
    return null;
  };
  // "menu <id> item <n><rest>": the id is matched against the real menus first, so an id with spaces still resolves
  const ids = Object.keys(cfgMenus).sort((x, y) => y.length - x.length);
  const owner = ids.find(id => raw.startsWith('menu ' + id + ' item ') || raw.startsWith('menu ' + id + ': '));
  const mid = owner !== undefined ? owner : ((m = /^menu (\S+)(?: item |: )/.exec(raw)) ? m[1] : null);
  if (mid !== null) {
    const rest = raw.slice(('menu ' + mid).length);
    if ((m = /^ item (\d+)(.*)$/s.exec(rest))) {
      const n = +m[1], why = itemReason(m[2]), sty = /^: style(?:\.(\w+))?(?::| must be)/.exec(m[2]);
      // a problem with an item's style leads to the Look screen's slot level, at the control of the key
      const where = known(mid) ? (sty ? lookTarget(sty[1] || '_style', { level: 'menu', menuId: mid, slot: n - 1 }) : { kind: 'item', menuId: mid, index: n - 1 }) : null;
      return out(titleOf(mid) + ' item ' + n + (why ? ' ' + why : m[2]), where);
    }
    const tgt = field => (known(mid) ? { kind: 'menu', menuId: mid, field } : null);
    if (rest === ': no usable items') return out(titleOf(mid) + ' has no usable items', tgt());
    if (rest === ': not an object') return out(titleOf(mid) + ' is not a valid menu', tgt());
    if ((m = /^: hotkey (.+) already used by menu (.+)$/s.exec(rest))) {
      const other = m[2];
      return out(`${titleOf(mid)} and ${titleOf(other)} both use the hotkey ${unq(m[1])}; only ${titleOf(other)} (the first) will open it`, tgt('hotkey'));
    }
    if (rest.startsWith(': that id is reserved')) return out(`The id of ${titleOf(mid)} is reserved. Give it another in the Id field`, tgt('id'));
    if ((m = /^: ids starting with '(\w+:)'/.exec(rest))) return out(`The id of ${titleOf(mid)} cannot start with “${m[1]}”; those ids are reserved for the menus ZOrbit makes itself`, tgt('id'));
    if ((m = /^: hotkey (.+) not understood$/s.exec(rest))) return out(`The hotkey ${unq(m[1])} on ${titleOf(mid)} is not understood`, tgt('hotkey'));
    if ((m = /^: animation (.+) unknown; using ring\.animation$/s.exec(rest))) return out(`${titleOf(mid)} has an unknown animation (${unq(m[1])}); the one for all menus is used instead`, known(mid) ? lookTarget('animation', { level: 'menu', menuId: mid }) : null);
    if ((m = /^: unknown setting (.+)$/s.exec(rest))) return out(`${titleOf(mid)} has an unknown setting ${m[1].replace(/\s*\(did you mean .*$/s, '')}.` + didYouMean(m[1]), tgt());
    if ((m = /^: (swallow|fan) (.+) must be true or false; using (true|false)$/s.exec(rest))) return out(`${titleOf(mid)}: ${m[1] === 'fan' ? 'Fan out' : 'Swallow hotkey'} must be on or off, not ${unq(m[2])}; it is ${m[3] === 'true' ? 'on' : 'off'} for now`, tgt(m[1]));
    const lookAt = key => (known(mid) ? lookTarget(key, { level: 'menu', menuId: mid }) : null);
    if ((m = /^: look (.+) unknown; using the ring's look$/s.exec(rest))) return out(`${titleOf(mid)} uses the look ${unq(m[1])}, which does not exist; the ring's look is used instead`, lookAt('_look'));
    if (rest.startsWith(': look must be a look name or an object')) return out(`The look of ${titleOf(mid)} must be a look name or an object of look settings, so it is ignored`, lookAt('_look'));
    if ((m = /^: look\.(\w+): (.*)$/s.exec(rest))) { const why = lookValueReason(lookLabel(m[1]), m[2]); return out(`${titleOf(mid)}, look: ${why || lookLabel(m[1]) + ': ' + m[2]}`, lookAt(m[1])); }
    if ((m = /^: look\.colors\.(\w+): (.*)$/s.exec(rest))) return out(`${titleOf(mid)}, look: ${COLOR_INFO[m[1]] ? COLOR_INFO[m[1]][0] : m[1]} colour ${m[2]}`, lookAt('colors'));
    return out(titleOf(mid) + rest, tgt());
  }
  if ((m = /^ring\.colors\.(\w+): (.+) is not a #rrggbb colour$/s.exec(raw))) {
    const nm = COLOR_INFO[m[1]] ? COLOR_INFO[m[1]][0] : m[1];
    return out(`${nm} colour ${unq(m[2])} is not a #rrggbb value`, lookTarget('colors'));
  }
  if ((m = /^ring\.colors\.(\w+): unknown colour(.*)$/s.exec(raw))) return out(`Ring colour “${m[1]}” is not one of the five colours.` + didYouMean(m[2]), lookTarget('colors'));
  if (raw.startsWith('ring: must be an object')) return out('The ring section is not an object, so every ring setting uses its default', lookTarget('radius'));
  if ((m = /^ring\.(\w+): unknown setting(.*)$/s.exec(raw))) return out(`The ring setting “${m[1]}” is not known.` + didYouMean(m[2]), null);
  if ((m = /^ring\.look: (.+) unknown; one of /s.exec(raw))) return out(`The ring uses the look ${unq(m[1])}, which does not exist, so the default look is used`, lookTarget('_look'));
  if ((m = /^ring\.(\w+): (.*)$/s.exec(raw))) {
    const key = m[1], body = m[2], nm = RING_NAME[key] || key, card = RING_CARD[key];
    const target = own(RING_LOOK, key) ? lookTarget(key) : card ? { kind: 'settings', card, key } : null;
    const why = lookValueReason(nm, body);
    return out(why || `${nm}: ${body}`, target);
  }
  if (raw.startsWith('looks: must be an object')) return out('The looks section is not an object, so every look in it is ignored', lookTarget('_look'));
  if (raw.startsWith('looks.')) {
    const names = Object.keys((S.cfg && S.cfg.looks) || {}).sort((x, y) => y.length - x.length);
    const nm = names.find(n => raw.startsWith('looks.' + n + ': ') || raw.startsWith('looks.' + n + '.'));
    const lname = nm !== undefined ? nm : ((m = /^looks\.([^:.]+)/.exec(raw)) ? m[1] : null);
    if (lname !== null) {
      const rest = raw.slice(('looks.' + lname).length), q = '“' + lname + '”';
      const there = !!(S.cfg && S.cfg.looks && own(S.cfg.looks, lname) && ZLook.nameProblem(lname, lookCtx()) === '');
      const gal = lookTarget('_look'), on = key => (there ? lookTarget(key, { level: 'preset', name: lname }) : gal);
      if (rest.startsWith(': name must be')) return out(`The look ${q} has a name that is not allowed (1 to 32 letters, digits, spaces, - or _), so it is ignored. Rename it in the file`, gal);
      if (rest.startsWith(': that name is a built-in look')) return out(`The look ${q} has the name of a built-in look, or a reserved name, so it is ignored. Rename it in the file`, gal);
      if ((m = /^: same name as (.+) apart from capitals; ignored$/s.exec(rest))) return out(`The look ${q} has the same name as ${'“' + unq(m[1]) + '”'} apart from capitals, so it is ignored`, gal);
      if (rest.startsWith(': not an object')) return out(`The look ${q} is not an object, so it is ignored`, gal);
      if (rest.startsWith('.preset:')) return out(`The look ${q} names another look; a look cannot be based on another one, so that is ignored`, on('_look'));
      if ((m = /^\.colors\.(\w+): (.*)$/s.exec(rest))) return out(`The look ${q}: ${COLOR_INFO[m[1]] ? COLOR_INFO[m[1]][0] : m[1]} colour ${m[2]}`, on('colors'));
      if ((m = /^\.(\w+): (.*)$/s.exec(rest))) { const why = lookValueReason(lookLabel(m[1]), m[2]); return out(`The look ${q}: ${why || lookLabel(m[1]) + ': ' + m[2]}`, on(m[1])); }
    }
  }
  const bridge = { kind: 'settings', card: 'set-zbrush-bridge' };
  if ((m = /^bridge\.mode (.+) unknown; using auto$/s.exec(raw))) return out(`Bridge mode ${unq(m[1])} is unknown; Auto is used instead`, bridge);
  if ((m = /^bridge\.key (.+) not understood(?:; using (.+))?$/s.exec(raw))) return out(`The bridge key ${unq(m[1])} is not understood` + (m[2] ? `; ${m[2]} is used instead` : ''), bridge);
  if (raw.startsWith('bridge.key must not use Ctrl or Shift')) {
    const using = /; using ([^;]+)$/.exec(raw);
    return out('The bridge key cannot use Ctrl or Shift, because ZBrush reads them as mask and smooth. Use a bare F-key' + (using ? `; ${using[1]} is used instead` : ''), bridge);
  }
  if ((m = /^bridge\.key (.+) does not reach ZBrush:.*?(?:; using ([^;]+))?$/s.exec(raw))) return out(`The bridge key ${unq(m[1])} cannot be used: ZBrush does not act on Alt combinations or F10 when ZOrbit sends them. Use a bare F-key such as F9 or F11` + (m[2] ? `; ${m[2]} is used instead` : ''), bridge);
  if (raw.startsWith('bridge: must be an object')) return out('The bridge section is not an object, so the defaults are used', bridge);
  if ((m = /^bridge\.(\w+): unknown setting(.*)$/s.exec(raw))) return out(`The bridge setting “${m[1]}” is not known.` + didYouMean(m[2]), bridge);
  if (raw.startsWith('bridge.key ')) return out('The bridge key ' + raw.slice('bridge.key '.length), bridge);
  const browserCard = { kind: 'settings', card: 'set-behaviour', fk: 'hk:Browser hotkey' };   // the recorder is the last row of the card, so it is focused too
  if ((m = /^browser\.hotkey (.+) not understood$/s.exec(raw))) return out(`The browser hotkey ${unq(m[1])} is not understood`, browserCard);
  if ((m = /^browser\.hotkey (.+) already used by menu (.+)$/s.exec(raw))) return out(`The browser hotkey ${unq(m[1])} is also used by ${titleOf(m[2])}; that menu wins, so the browser will not open with it`, browserCard);
  if ((m = /^browser\.(\w+): unknown setting(.*)$/s.exec(raw))) return out(`The browser setting “${m[1]}” is not known.` + didYouMean(m[2]), browserCard);
  if ((m = /^browser\.quit_after_minutes (.+) must be a whole number of minutes from 1 to 1440, or 0 for never; using 0$/s.exec(raw))) return out(`Quit hidden browser after is ${unq(m[1])}, which is not a whole number of minutes from 1 to 1440. It is set to 0, so the browser is kept ready`, { ...browserCard, fk: 'quit_after_minutes/num' });   // the number box of the row
  if (raw.startsWith('browser: ')) return out('The browser settings are not valid: ' + raw.slice('browser: '.length), browserCard);
  const profileCard = { kind: 'settings', card: 'set-behaviour', fk: 'hk:Next profile hotkey' };   // the recorder is the last row of the card, so it is focused too
  if ((m = /^profile\.next_hotkey (.+) not understood$/s.exec(raw))) return out(`The next-profile hotkey ${unq(m[1])} is not understood`, profileCard);
  if ((m = /^profile\.next_hotkey (.+) already used by menu (.+)$/s.exec(raw))) return out(`The next-profile hotkey ${unq(m[1])} is also used by ${titleOf(m[2])}; that menu wins, so the next-profile hotkey will not step profiles`, profileCard);
  if ((m = /^profile\.next_hotkey (.+) already used by browser\.hotkey$/s.exec(raw))) return out(`The next-profile hotkey ${unq(m[1])} is also used by the browser; the browser wins, so the next-profile hotkey will not step profiles`, profileCard);
  if ((m = /^profile\.(\w+): unknown setting(.*)$/s.exec(raw))) return out(`The profile setting “${m[1]}” is not known.` + didYouMean(m[2]), profileCard);
  if (raw.startsWith('profile: ')) return out('The profile settings are not valid: ' + raw.slice('profile: '.length), profileCard);
  if ((m = /^tags\.json could not be read: (.*); tag slots stay empty until it is fixed$/s.exec(raw))) return out(`The tags file could not be read (${m[1]}). Tag slots stay empty until it is fixed`, null);
  if (raw.startsWith('config could not be read: ')) return out('The menus could not be checked: ' + raw.slice('config could not be read: '.length), null);
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
  return tips ? h('span', { class: 'mwarn', role: 'img', title: tips.join('\n'), 'aria-label': 'Problem: ' + tips.join('. ') }, icon('alert', 13)) : null;
}
function itemWarn(menuId, i, ok) {
  const tips = S.problemTips.get(menuId + '#' + i);
  if (ok && !tips) return null;
  const text = tips ? tips.join('\n') : 'This item is incomplete. The ring shows an empty slot here until you fill it in.';
  return h('span', { class: 'iwarn', role: 'img', title: text, 'aria-label': 'Problem: ' + text.replace(/\n/g, '. ') }, icon('alert', 14));
}
function paintMarkers() {
  $$('.mrow').forEach(row => {
    const want = S.problemTips.get(row.dataset.id), cur = $('.mwarn', row);
    if (!want) { if (cur) cur.remove(); return; }
    if (cur) { cur.title = want.join('\n'); cur.setAttribute('aria-label', 'Problem: ' + want.join('. ')); return; }
    const side = $('.mrow-side', row); if (side) side.prepend(menuWarn(row.dataset.id));
  });
  $$('.irow').forEach(row => {
    const menuId = row.dataset.menu, i = +row.dataset.i, want = S.problemTips.get(menuId + '#' + i), cur = $('.iwarn', row);
    const m = menuOf(menuId), bad = !m || !m.items[i] || !itemUsable(m.items[i]);
    if (!want && !bad) { if (cur) cur.remove(); return; }
    const title = want ? want.join('\n') : 'This item is incomplete. The ring shows an empty slot here until you fill it in.';
    if (cur) { cur.title = title; cur.setAttribute('aria-label', 'Problem: ' + title.replace(/\n/g, '. ')); return; }
    const acts = $('.iacts', row), el = itemWarn(menuId, i, !bad);
    if (el) row.insertBefore(el, acts);
  });
}

function goToProblem(t) {
  S.problemsOpen = false; renderProblems();
  if (!t) return;
  if (!isFull() && targetNeedsFull(t)) { setMode('full'); toast('Switched to Full mode to show this.', { ms: 3500 }); }
  if (t.kind === 'look') {
    const same = S.screen === 'look';
    if (typeof window.lookOpenAt === 'function') window.lookOpenAt(t, same);     // the level, menu or look to show
    showScreen('look', { fresh: true });
    const go = () => { if (R.lookGoto) R.lookGoto(t.key, t.group); };
    if (same) go(); else requestAnimationFrame(go);
    return;
  }
  if (t.kind === 'settings') {
    const same = S.screen === 'settings';
    showScreen('settings', { fresh: true });
    const go = () => { if (R.gotoCard) R.gotoCard(t.card); if (t.fk) { const el = $('#screen-settings [data-fk="' + t.fk + '"]'); if (el && !el.disabled) el.focus({ preventScroll: true }); } };
    if (same) go(); else requestAnimationFrame(go);
    return;
  }
  showScreen('menus', { fresh: true });
  if (t.kind === 'item') {
    const m = menuOf(t.menuId); if (!m) return;
    selectMenu(t.menuId);
    if (t.index >= 0 && t.index < (m.items || []).length) selectItem(t.index);
    return;
  }
  if (t.kind === 'menu') {
    if (!hasMenu(t.menuId)) return;
    if (t.field === 'id' || t.field === 'fan') menuMore[t.menuId] = true;       // a hidden field cannot take the focus
    selectMenu(t.menuId); S.tab = 'menu'; if (R.right) R.right();
    const mr = $('.mrow.sel'); if (mr) mr.scrollIntoView({ block: 'nearest' });
    const el = t.field === 'hotkey' ? $('.insp .hk-field') : t.field === 'id' ? $('.insp input[aria-label="Menu id"]')
      : t.field === 'swallow' ? $('.insp input[aria-label="Swallow hotkey"]') : t.field === 'fan' ? $('.insp input[aria-label="Fan out when opened from another menu"]') : null;
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
    const ix = t.kind === 'item' ? t.index : t.kind === 'look' && Number.isInteger(t.slot) ? t.slot : null;      // an item's style problem marks the item too
    if (ix !== null) {
      if (!itemsWith.has(t.menuId)) itemsWith.set(t.menuId, new Set());
      itemsWith.get(t.menuId).add(ix); tip(t.menuId + '#' + ix, e.text);
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
/* True when `after` holds a problem that `before` did not. */
const newProblems = (before, after) => { const had = new Set(before.map(String)); return after.some(p => !had.has(String(p))); };
/* Takes a freshly loaded get_config result (boot, or "reload from disk") and makes it the current and saved config. */
/* Makes a loaded config safe to draw: menus is an object, every menu has an items list. Returns a sentence about the first thing that
   cannot be drawn at all (a menu that is not an object, items that are not a list of objects), else ''. The loader reports these as
   problems and carries on, but the screens would throw on them. */
function normaliseMenus(cfg) {
  if (!cfg.menus || typeof cfg.menus !== 'object' || Array.isArray(cfg.menus)) cfg.menus = {};   // an array would lose menus on save
  for (const sec of ['ring', 'bridge', 'browser', 'profile']) {        // a hand-edited "ring": "big": the loader uses the defaults, and so does Studio
    const v = cfg[sec];
    if (v !== undefined && (!v || typeof v !== 'object' || Array.isArray(v))) delete cfg[sec];
  }
  if (cfg.ring && cfg.ring.colors !== undefined && (!cfg.ring.colors || typeof cfg.ring.colors !== 'object' || Array.isArray(cfg.ring.colors))) delete cfg.ring.colors;
  for (const [id, m] of Object.entries(cfg.menus)) {
    if (!m || typeof m !== 'object' || Array.isArray(m)) return `The menu "${id}" is not an object.`;
    if (m.items === undefined || m.items === null) m.items = [];
    else if (!Array.isArray(m.items)) return `The items of the menu "${id}" are not a list.`;
    const at = m.items.findIndex(it => !it || typeof it !== 'object' || Array.isArray(it));
    if (at >= 0) return `Item ${at + 1} of the menu "${id}" is not an object.`;
  }
  return '';
}
/* Returns '' when the config was taken, else why it was not (see normaliseMenus); the current config is then left alone. */
function adoptConfig(res) {
  const bad = normaliseMenus(res.config);
  if (bad) return bad;
  S.cfg = res.config;
  S.path = res.path || S.path || ''; S.problems = res.problems || [];
  S.mtimeNs = res.mtime_ns !== undefined ? res.mtime_ns : null;
  S.savedStr = JSON.stringify(S.cfg); resetHistory(S.savedStr);
  takeProfile(res);
  return '';
}
/* Takes a get_config answer as the editor's new state and redraws everything that shows it (a reload, a profile switch).
   Returns '' when it was taken, else why not; the editor is then left alone. */
function adoptAndRender(res) {
  validateSoon.cancel(); snapSoon.cancel();
  const bad = adoptConfig(res);
  if (bad) return bad;
  S.cameFrom = null;
  if (!hasMenu(S.menuId)) S.menuId = Object.keys(S.cfg.menus)[0] || null;
  const m = curMenu();
  if (!m || S.itemIdx === null || S.itemIdx >= (m.items || []).length) S.itemIdx = null;
  if (S.itemIdx === null && S.tab === 'item') S.tab = 'menu';
  rememberSel();
  S.version++; updateDirty(); renderProblems(); previewSoon();
  renderAllMenus(); if (R.settings) R.settings(); if (R.look) R.look(); if (R.libTarget) R.libTarget();
  renderProfile();
  return '';
}
async function reloadFromDisk() {
  let res;
  const prof = editProfile();
  try { res = await call('get_config', ...(prof ? [prof] : [])); } catch (e) { toast('Could not reload: ' + (e.message || e), { tone: 'err' }); return false; }
  if (!res || !res.config) { toast('Could not reload: ' + ((res && res.error) || 'the file cannot be read'), { tone: 'err' }); return false; }
  const bad = adoptAndRender(res);
  if (bad) { toast('Could not reload: ' + bad, { tone: 'err' }); return false; }
  toast('Reloaded the file from disk.', { tone: 'ok', ms: 2600 });
  return true;
}

/* ---- profiles. A profile is one set of menus, ring settings and tags in a folder of its own; the app uses the active one, and the button in the
   top bar shows the one Studio edits and picks another. The backend does the file work (switch_profile, create_profile, rename_profile, delete_profile). */
/* The profile fields of a get_config answer (or of a switch_profile one). */
function takeProfile(res) {
  if (!res || typeof res !== 'object') return;
  if (typeof res.profile === 'string') S.profile = res.profile;
  if (typeof res.active === 'string') S.active = res.active;
  if (Array.isArray(res.profiles)) S.profiles = res.profiles.map(String);
  if (res.enabled !== undefined) S.profilesOn = !!res.enabled;
}
/* The names and the active profile of a create, rename or delete answer. */
function takeNames(res) {
  if (!res || typeof res !== 'object') return;
  if (Array.isArray(res.names)) S.profiles = res.names.map(String);
  if (typeof res.active === 'string') S.active = res.active;
}
/* The profile fields and the path of a get_config answer, without touching the config being edited. */
function adoptProfileInfo(res) {
  if (!res || typeof res !== 'object') return;
  takeProfile(res);
  if (res.path) S.path = String(res.path);
  renderProfile();
}
/* What save_config and get_config are told: the profile Studio edits, or nothing when there are no profiles. */
const editProfile = () => (S.profilesOn && S.profile ? S.profile : null);
function renderProfile() {
  const b = $('#profileBtn');
  if (!b) return;
  b.hidden = !S.profilesOn || !S.profile;
  setText($('.profile-name', b), S.profile);
  const off = !!S.active && S.active !== S.profile;
  b.classList.toggle('not-active', off);
  const tip = off ? `Editing ${S.profile}. The app is using ${S.active}.` : 'Profile: ' + S.profile;
  b.title = tip; b.setAttribute('aria-label', tip);
}
let profileBusy = false;                                      // a switch is under way (its dialogs included)
let warnedActive = '', deletedAsked = '';                     // the app's profile the focus check already spoke about; the missing profile it already asked about
function openProfileMenu(anchor) {
  const entries = S.profiles.map(n => ({ label: n, checked: n === S.profile, hint: n === S.active && n !== S.profile ? 'in use' : '', fn: () => switchProfile(n) }));
  entries.push({ sep: true },
    { icon: 'plus', label: 'New profile...', fn: newProfile },
    { icon: 'edit', label: 'Rename...', fn: renameProfile },
    { icon: 'copy', label: 'Duplicate', fn: duplicateProfile },
    { icon: 'trash', label: 'Delete...', fn: deleteProfile },
    { icon: 'folder', label: 'Open profiles folder', fn: openProfilesFolder });
  anchor.setAttribute('aria-expanded', 'true');
  popover(anchor, entries, { onClose: () => anchor.setAttribute('aria-expanded', 'false') });
}
/* Makes `name` the profile Studio edits (the backend also makes it the app's). Edits not saved yet are asked about first. fromApp: the app moved first, and the toast says so.
   Resolves true when it switched. */
async function switchProfile(name, { fromApp = false } = {}) {
  if (!name || name === S.profile || profileBusy) return false;
  profileBusy = true;
  try {
    if (dirtyNow()) {
      const v = await modal({ title: 'Unsaved changes', body: unsavedBody('Switching profile'), actions: [
        { text: 'Keep editing', value: 'keep', focus: true },
        { text: 'Switch without saving', value: 'discard', kind: 'danger-ghost' },
        { text: 'Save and switch', value: 'save', kind: 'primary' }] });
      if (v === 'save') { const out = await save(); if (out !== 'saved' && out !== 'reloaded') return false; }
      else if (v !== 'discard') return false;
    }
    return await performSwitch(name, fromApp);
  } finally { profileBusy = false; }
}
/* The switch itself, with no question asked. */
async function performSwitch(name, fromApp = false) {
  let res;
  try { res = await call('switch_profile', name); } catch (e) { res = { ok: false, message: 'Could not switch profile: ' + ((e && e.message) || e) }; }
  if (!res || !res.ok) { toast((res && res.message) || 'Could not switch profile.', { tone: 'err' }); return false; }
  if (S.fatal) { location.reload(); return true; }
  const bad = res.config ? adoptAndRender(res) : 'unreadable';
  if (bad) { S.savedStr = JSON.stringify(S.cfg); location.reload(); return true; }      // the backend has switched but the page cannot show that profile: boot shows the recovery screen for it
  profileChanged();
  toast(fromApp ? `The app switched to ${name}.` : `Switched to ${name}. The app and the browser follow.`, { tone: 'ok' });
  return true;
}
/* What follows a change of profile besides the config: the tags file and the Recent list belong to the profile too. */
function profileChanged() { warnedActive = ''; loadTags(); reloadUsage(); }
/* A dialog with one text box. Resolves the trimmed text, or null when cancelled. submit(text) (optional) does the work and answers '' when done or a message,
   which is shown under the box with the dialog left open. extra is more content below the box; ctl, if given, gets ctl.input. */
function promptModal({ title, label, value = '', confirm = 'OK', hint = '', extra = null, submit = null, ctl = null }) {
  const inp = h('input', { class: 'inp', type: 'text', value, spellcheck: 'false', autocomplete: 'off', 'data-focus': true });
  if (ctl) ctl.input = inp;
  const msg = h('p', { class: 'warn-text', role: 'alert', hidden: true });
  const say = t => { msg.textContent = t || ''; msg.hidden = !t; };
  inp.addEventListener('input', () => say(''));
  inp.addEventListener('keydown', e => {
    if (e.key !== 'Enter' || e.isComposing) return;
    e.preventDefault();
    const box = inp.closest('.modal'), ok = box && $('.btn.primary', box);
    if (ok) ok.click();
  });
  let text = '';
  const done = modal({ title, body: [h('label', { class: 'modal-field' }, label, inp), hint ? h('p', { class: 'modal-hint' }, hint) : null, extra, msg],
    actions: [{ text: 'Cancel', value: false }, { text: confirm, value: true, kind: 'primary', check: async () => {
      const t = inp.value.trim();
      const bad = t ? (submit ? await submit(t) : '') : 'Type a name first.';
      say(bad);
      if (bad) { inp.focus(); inp.select(); return false; }
      text = t;
      return true;
    } }] });
  inp.focus(); inp.select();
  return done.then(v => (v ? text : null));
}
/* create_profile for the dialogs: { res } on success, { err } with the words to show otherwise. */
async function createProfileCall(name, source) {
  let res;
  try { res = await call('create_profile', name, source); } catch (e) { return { err: 'Could not create the profile: ' + ((e && e.message) || e) }; }
  return res && res.ok ? { res } : { err: (res && res.message) || 'The profile could not be created.' };
}
async function newProfile() {
  let source = 'starter', picking = false, made = null;
  const ctl = {}, note = h('p', { class: 'modal-hint', hidden: true });
  const n = (v, one, many) => { v = +v || 0; return v + ' ' + (v === 1 ? one : many); };
  const sources = [['starter', 'Starter menus'], ['empty', 'Empty'], ['copy', 'Copy of ' + S.profile], ['file', 'From a file...']];
  const rows = sources.map(([v, text]) => h('button', { class: 'radio-row', type: 'button', role: 'radio', 'aria-checked': 'false', dataset: { v },
    title: v === 'copy' && dirtyNow() ? 'The saved version of ' + S.profile + ', without your unsaved changes' : null, onclick: () => choose(v, true) }, h('i', { class: 'radio-dot' }), text));
  const rowOf = v => rows.find(r => r.dataset.v === v);
  const mark = v => { source = v; rows.forEach(r => r.setAttribute('aria-checked', r.dataset.v === v ? 'true' : 'false')); setRoving(rows, rowOf(v)); };
  async function choose(v, focus) {
    if (picking) return;
    if (v !== 'file') { note.hidden = true; mark(v); if (focus) rowOf(v).focus(); return; }
    picking = true;
    let res;
    try { res = await call('pick_profile_file'); } catch (e) { res = { ok: false, message: 'Could not read the file: ' + ((e && e.message) || e) }; }
    picking = false;
    if (res && res.ok) {
      mark('file');
      if (res.name) ctl.input.value = res.name;
      const probs = (res.problems || []).length, file = String(res.path || '').split(/[\\/]/).pop() || 'The file';
      note.textContent = `${file}: ${n(res.menus, 'menu', 'menus')}, ${res.has_tags ? n(res.tags, 'tag', 'tags') : 'no tags'}` + (probs ? `. ${n(probs, 'problem', 'problems')} in the menus.` : '');
      note.hidden = false;
    } else {
      note.hidden = true; mark('starter');                       // cancelled, or refused: back to Starter menus
      if (res && !res.cancelled) toast(res.message || 'That file could not be read.', { tone: 'warn', ms: 5000 });
    }
    rowOf(source).focus();
  }
  const group = h('div', { class: 'radios', role: 'radiogroup', 'aria-label': 'Start the new profile from' }, rows);
  group.addEventListener('keydown', e => {
    if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
    const at = rows.indexOf(document.activeElement);
    if (at < 0) return;
    const k = rows.length;
    const to = { ArrowRight: (at + 1) % k, ArrowDown: (at + 1) % k, ArrowLeft: (at + k - 1) % k, ArrowUp: (at + k - 1) % k, Home: 0, End: k - 1 }[e.key];
    if (to === undefined) return;
    e.preventDefault();
    if (rows[to].dataset.v === 'file') rows[to].focus();         // choosing it opens a file dialog: the arrows only get there, Enter or Space choose it
    else choose(rows[to].dataset.v, true);
  });
  mark('starter');
  const name = await promptModal({ title: 'New profile', label: 'Name', confirm: 'Create', ctl, extra: [h('div', { class: 'modal-cap' }, 'Start from'), group, note],
    submit: async t => {
      if (picking) return 'Wait for the file dialog to close.';
      const out = await createProfileCall(t, source);
      if (out.err) return out.err;
      made = out.res;
      return '';
    } });
  if (name === null || !made) return;
  takeNames(made); renderProfile();
  await switchProfile(made.name || name);
}
/* "Default" gives "Default 2", then "Default 3"... the first one nobody has. */
function freeProfileName(base) {
  const stem = String(base).replace(/ \d+$/, '') || String(base), have = new Set(S.profiles.map(x => x.toLowerCase()));
  let k = 2;
  while (have.has(`${stem} ${k}`.toLowerCase())) k++;
  return `${stem} ${k}`;
}
async function duplicateProfile() {
  let made = null;
  const name = await promptModal({ title: 'Duplicate profile', label: 'Name of the copy', value: freeProfileName(S.profile), confirm: 'Duplicate',
    hint: dirtyNow() ? 'The copy is made from the saved version of ' + S.profile + ', not your unsaved changes.' : '',
    submit: async t => {
      const out = await createProfileCall(t, 'copy');
      if (out.err) return out.err;
      made = out.res;
      return '';
    } });
  if (name === null || !made) return;
  takeNames(made); renderProfile();
  await switchProfile(made.name || name);
}
async function renameProfile() {
  const old = S.profile;
  let done = null;
  const name = await promptModal({ title: 'Rename profile', label: 'Name', value: old, confirm: 'Rename',
    submit: async t => {
      if (t === old) return '';
      let res;
      try { res = await call('rename_profile', old, t); } catch (e) { return 'Could not rename the profile: ' + ((e && e.message) || e); }
      if (!res || !res.ok) return (res && res.message) || 'The profile could not be renamed.';
      done = res;
      return '';
    } });
  if (name === null || !done) return;
  S.profile = done.name || name; takeNames(done); renderProfile();
  try { adoptProfileInfo(await call('get_config', S.profile)); } catch (e) { /* the path in the top bar catches up at the next reload */ }
  toast(done.message || `Renamed to ${S.profile}.`, { tone: 'ok' });
}
async function deleteProfile() {
  const name = S.profile;
  if (S.profiles.length < 2) { toast('The last profile cannot be deleted.', { tone: 'warn' }); return; }
  const body = [h('p', null, 'Its menus, tags and usage go to profiles\\.deleted and are removed after 30 days.')];
  if (name === S.active) body.push(h('p', null, 'The app switches to another profile.'));
  if (dirtyNow()) body.push(h('p', { class: 'warn-text' }, 'Your unsaved changes in it are lost.'));
  const ok = await modal({ title: `Delete the profile ${name}?`, body, actions: [{ text: 'Cancel', value: false, focus: true }, { text: 'Delete profile', kind: 'danger', value: true }] });
  if (!ok) return;
  let res;
  try { res = await call('delete_profile', name); } catch (e) { res = { ok: false, message: 'Could not delete the profile: ' + ((e && e.message) || e) }; }
  if (!res || !res.ok) { toast((res && res.message) || 'The profile could not be deleted.', { tone: 'err' }); return; }
  if (res.reload) {                                            // the editor's own profile went: the backend now edits another
    let cfg = null;
    try { cfg = await call('get_config'); } catch (e) { cfg = null; }
    const bad = cfg && cfg.config ? adoptAndRender(cfg) : 'unreadable';
    if (bad) { S.savedStr = JSON.stringify(S.cfg); location.reload(); return; }
    profileChanged();
  } else { takeNames(res); renderProfile(); }
  toast(res.message || `Deleted ${name}.`, { tone: 'ok' });
}
async function openProfilesFolder() {
  try { await call('open_folder', 'profiles'); } catch (e) { toast('Could not open the folder.', { tone: 'warn' }); }
}
/* When Studio gets the focus: the app's profile may have changed (tray, another window), or this profile may be gone. A clean editor follows the app;
   one with edits keeps them and says so, once per change. */
async function checkProfile() {
  if (!S.ready || S.fatal || !S.profilesOn || profileBusy) return;
  let res;
  try { res = await call('get_profiles'); } catch (e) { return; }
  if (!res || res.ok === false || !Array.isArray(res.names)) return;
  if (res.enabled === false) { S.profilesOn = false; renderProfile(); return; }
  S.profiles = res.names.map(String); S.active = String(res.active || S.active); renderProfile();
  if (activeModal) return;                                     // a dialog is open: it keeps the screen
  if (!S.profiles.includes(S.profile)) {
    if (deletedAsked === S.profile) return;
    deletedAsked = S.profile;
    const to = S.profiles.includes(S.active) ? S.active : S.profiles[0];
    if (!to) return;
    const v = await modal({ title: `The profile ${S.profile} was deleted`,
      body: h('p', null, `It was removed outside this window. Switch to ${to}, or keep editing: the next save will say it is missing.`),
      actions: [{ text: 'Keep editing', value: 'keep', focus: true }, { text: `Switch to ${to}`, value: 'switch', kind: 'primary' }] });
    if (v === 'switch') switchProfile(to);
    return;
  }
  deletedAsked = '';
  if (S.active === S.profile) { warnedActive = ''; return; }
  if (warnedActive === S.active) return;
  warnedActive = S.active;                                     // one try, or one warning, per change of the app's profile
  const to = S.active;
  if (dirtyNow()) toast(`The app switched to ${to}. Save keeps your changes in ${S.profile}.`, { tone: 'warn', ms: 20000, action: { text: 'Reload', fn: () => switchProfile(to) } });
  else switchProfile(to, { fromApp: true });
}
/* save_config said the profile is gone. Switch away (the edits are dropped), make it again (the edits go in), or cancel. */
async function profileGone(r, { allowUnusable = false } = {}) {
  const name = S.profile;
  try {
    const g = await call('get_profiles');
    if (g && Array.isArray(g.names)) { S.profiles = g.names.map(String); S.active = String(g.active || S.active); renderProfile(); }
  } catch (e) { /* the names stay as they were */ }
  const to = S.profiles.includes(S.active) ? S.active : (S.profiles.find(x => x !== name) || '');
  const v = await modal({ title: `Profile ${name} no longer exists`,
    body: [h('p', null, (r && r.message) || `The profile ${name} was deleted or renamed outside this window. Your changes are still here.`),
      h('p', null, `Make it again creates it and saves your changes in it.` + (to ? ` Switching to ${to} drops your unsaved changes.` : ''))],
    actions: [{ text: 'Cancel', value: 'cancel', focus: true }, to ? { text: `Switch to ${to}`, value: 'switch', kind: 'danger-ghost' } : null, { text: 'Make it again', value: 'again', kind: 'primary' }].filter(Boolean) });
  if (v === 'switch') return (await performSwitch(to)) ? 'reloaded' : 'failed';
  if (v === 'again') {
    const out = await createProfileCall(name, 'starter');
    if (out.err) { toast(out.err, { tone: 'err' }); return 'failed'; }
    takeNames(out.res); renderProfile();
    S.mtimeNs = null;
    return doSave({ force: true, allowUnusable });             // lands in the profile just made
  }
  return 'cancelled';
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
  // What an import replaces: the editor's own menus when it holds edits not saved yet, else what radial.json holds now.
  const mine = Object.keys(S.cfg.menus).length, yourMenus = dirtyNow() ? mine : (+info.current_menus || mine), yourTags = +info.current_tags || 0;
  const probs = (info.problems || []).map(String), shown = probs.slice(0, 5);
  const merge = { text: 'Merge tags', value: 'merge', kind: 'primary', focus: true }, replace = { text: 'Replace tags', value: 'replace', kind: 'danger-ghost' };
  const mode = await modal({ title: `Import settings from ${name}?`,
    body: h('div', { class: 'changes' },
      h('p', { class: 'modal-path mono' }, info.path || name),
      h('p', null, counts.length ? 'The file holds ' + counts.join(' and ') + '.' : 'The file holds nothing to import.'),
      hasCfg ? h('p', null, h('b', null, 'Menus and settings. '), `The file’s ${n(info.menus, 'menu', 'menus')} ${info.menus === 1 ? 'replaces' : 'replace'} your ${yourMenus}, and its ring settings replace yours. `,
        'They load into the editor and nothing is written until you press Save. Undo brings yours back' + (dirtyNow() ? ', unsaved changes included.' : '.')) : h('p', null, 'The editor is not touched.'),
      hasTags ? h('p', null, h('b', null, 'Tags. '), 'They are saved straight away, and Undo does not bring them back. ',
        `Merge tags adds the file’s tags to your ${yourTags}. Replace tags swaps your ${yourTags} for the file’s and keeps a copy of the old tags file.` + (hasCfg ? ' Either button also loads the file’s menus and settings into the editor, as above.' : '')) : null,
      probs.length ? h('div', { class: 'changes-list' }, h('div', { class: 'chg-group' }, h('div', { class: 'micro' }, n(probs.length, 'problem', 'problems') + ' in the menus'),
        h('ul', null, shown.map(p => h('li', null, describeProblem(p).text)), probs.length > shown.length ? h('li', null, `and ${probs.length - shown.length} more`) : null))) : null),
    actions: hasTags ? [{ text: 'Cancel', value: null }, merge, replace] : [{ text: 'Cancel', value: null, focus: !hasCfg }, { text: 'Import', value: 'none', kind: 'primary', focus: hasCfg }] });
  if (!mode) return;
  let res;
  try { res = await call('apply_import', mode); } catch (e) { res = { ok: false, message: 'Import failed: ' + (e.message || e) }; }
  if (mode !== 'none') await loadTags(true);                     // the tags may have changed even when the call reports a problem
  if (!res || !res.ok) { toast((res && (res.message || res.error)) || 'The import did not work.', { tone: 'warn', ms: 5000 }); return; }
  if (res.config) {
    const bad = normaliseMenus(res.config);
    if (bad) { toast(`Nothing was loaded into the editor. ${bad}`, { tone: 'warn', ms: 6000 }); return; }
    snapSoon.cancel(); validateSoon.cancel(); pushSnap();       // files an edit still waiting, so Undo goes back to it; mtimeNs and savedStr stay as they were
    const priorProblems = S.problems.slice();
    S.cfg = res.config;
    S.problems = res.problems || [];
    if (newProblems(priorProblems, S.problems)) S.problemsOpen = true;
    if (!hasMenu(S.menuId)) S.menuId = Object.keys(S.cfg.menus)[0] || null;
    const m = curMenu();
    if (!m || S.itemIdx === null || S.itemIdx >= (m.items || []).length) S.itemIdx = null;
    if (S.itemIdx === null && S.tab === 'item') S.tab = 'menu';
    commit({ inspector: true }); if (R.head) R.head();
    renderProblems(); if (R.settings) R.settings(); if (R.look) R.look(); if (R.libTarget) R.libTarget();
  }
  const bits = [];
  if (res.config) bits.push('Loaded the menus and settings into the editor. Save to keep them.');
  if (res.tags_message) bits.push(res.tags_message);
  if (res.config && (res.problems || []).length) bits.push(n(res.problems.length, 'problem', 'problems') + ' to look at.');
  const msg = bits.join(' ') || 'Imported.', tone = res.config && (res.problems || []).length ? 'warn' : 'ok';
  if (res.config) undoToast(msg, { tone, ms: 7000 }); else toast(msg, { tone, ms: 5000 });
}
/* ---- share one menu: Export menu... writes a menu and the submenus it opens to a small file, Import menu... adds them next to the current menus */
async function exportMenu(id) {
  if (!S.cfg || S.fatal || !S.ready || !hasMenu(id)) return;
  let res;
  try { res = await call('export_menu', S.cfg, id); } catch (e) { toast('Could not export: ' + (e.message || e), { tone: 'err' }); return; }
  if (!res || res.cancelled) return;
  toast(res.message || (res.ok ? 'Exported the menu' + (res.path ? ' to ' + res.path : '.') : 'The export did not work.'), { tone: res.ok ? 'ok' : 'warn', ms: 5000 });
}
async function importMenu() {
  if (!S.cfg || S.fatal || !S.ready) return;
  let info;
  try { info = await call('pick_menu_import', S.cfg); } catch (e) { toast('Could not read the file: ' + (e.message || e), { tone: 'err' }); return; }
  if (!info || info.cancelled) return;
  if (!info.ok) { toast(info.message || 'That file could not be imported.', { tone: 'warn', ms: 5000 }); return; }
  const q = t => '“' + t + '”', n = (v, one, many) => { v = +v || 0; return v + ' ' + (v === 1 ? one : many); };
  const list = info.menus || [], title = info.title || (list[0] && list[0].title) || 'menu';
  const subs = list.filter(m => m.id !== info.root).map(m => m.title || m.id);
  const lines = [];
  for (const r of info.renames || []) {
    if (r.title !== r.old_title) lines.push(`${q(r.old_title)} is taken, so it comes in as ${q(r.title)}.`);
    else if (r.id !== r.old_id && isFull()) lines.push(`The id ${r.old_id} ${hasMenu(r.old_id) ? 'is taken' : 'cannot be used here'}, so it comes in as ${r.id}.`);
  }
  const tags = +info.tags || 0, fresh = +info.new_tags || 0;
  const miss = Object.entries(info.missing || {}).filter(([, v]) => v && v.length).map(([k, v]) => {
    const names = v.slice(0, 6).join(', ') + (v.length > 6 ? ` and ${v.length - 6} more` : '');
    return n(v.length, k, k === 'brush' ? 'brushes' : k + 's') + ': ' + names;
  });
  const probs = (info.problems || []).map(String), shown = probs.slice(0, 5);
  const group = (head, items, more) => h('div', { class: 'changes-list' }, h('div', { class: 'chg-group' }, h('div', { class: 'micro' }, head),
    h('ul', null, items.map(t => h('li', null, t)), more ? h('li', null, more) : null)));
  const ok = await modal({ title: `Import the menu ${q(title)}?`,
    body: h('div', { class: 'changes' },
      h('p', { class: 'modal-path mono' }, info.path || ''),
      h('p', null, `The file holds the menu ${q(title)}` + (subs.length ? ` and ${n(subs.length, 'submenu', 'submenus')}: ${subs.join(', ')}.` : '.')),
      lines.length ? h('div', null, lines.map(t => h('p', null, t))) : null,
      tags ? h('p', null, h('b', null, 'Tags. '), `It brings ${n(tags, 'tag', 'tags')}` + (fresh ? ` (${fresh} not among yours yet). They are added to your tags straight away, and Undo does not take them out.` : ' (you have them all already).')) : null,
      miss.length ? group('Not found on this PC', miss) : null,
      miss.length ? h('p', null, 'They still import and show as missing until you install them.') : null,
      probs.length ? group(n(probs.length, 'problem', 'problems') + ' in the menus', shown.map(p => describeProblem(p).text), probs.length > shown.length ? `and ${probs.length - shown.length} more` : '') : null,
      h('p', null, 'It comes in with no hotkey. Give it one in the Menu tab, or open it from another menu. Nothing is written until you press Save.')),
    actions: [{ text: 'Cancel', value: false }, { text: 'Import', value: true, kind: 'primary', focus: true }] });
  if (!ok) return;
  let res;
  try { res = await call('apply_menu_import', S.cfg); } catch (e) { res = { ok: false, message: 'Import failed: ' + (e.message || e) }; }
  if (tags || (res && res.tags_message)) await loadTags(true);          // the tags may have changed even when the call reports a problem
  if (!res || !res.ok) { toast((res && (res.message || res.error)) || 'The import did not work.', { tone: 'warn', ms: 5000 }); return; }
  const add = res.menus || {}, ids = Object.keys(add);
  if (!ids.length || !own(add, res.root)) { toast('The file held no menu to add.', { tone: 'warn', ms: 5000 }); return; }
  const reserved = ids.find(k => RESERVED_IDS.has(k));
  if (reserved) { toast(`Nothing was added. The file has a menu with the reserved id ${reserved}.`, { tone: 'warn', ms: 6000 }); return; }
  const clash = ids.find(k => hasMenu(k));                          // the editor may have changed while the dialog was open
  if (clash) { toast(`Nothing was added. The editor already has a menu with the id ${clash}. Try again.`, { tone: 'warn', ms: 6000 }); return; }
  const bad = normaliseMenus({ menus: add });
  if (bad) { toast(`Nothing was added. ${bad}`, { tone: 'warn', ms: 6000 }); return; }
  snapSoon.cancel(); validateSoon.cancel(); pushSnap();                 // files an edit still waiting, so Undo goes back to the state before the import
  for (const k of ids) S.cfg.menus[k] = add[k];
  S.menuId = res.root; S.itemIdx = null; S.tab = 'menu';
  const found = (res.problems || []).map(String);                       // for the new menus only; the validation that commit starts then replaces the list with the whole editor's
  if (found.length) { const had = new Set(S.problems.map(String)); S.problems = S.problems.concat(found.filter(p => !had.has(p))); S.problemsOpen = true; }
  commit({ inspector: true }); if (R.head) R.head(); if (R.preview) R.preview();
  renderProblems();
  const subN = ids.length - 1, name = (add[res.root].title || res.root);
  undoToast(`Imported ${q(name)}` + (subN ? ` and ${n(subN, 'submenu', 'submenus')}` : '') + '. Save to keep ' + (ids.length === 1 ? 'it' : 'them') + '.' + (res.tags_message ? ' ' + res.tags_message : ''), { tone: found.length ? 'warn' : 'ok', ms: 7000 });
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
  const snap = JSON.stringify(S.cfg), prior = (S.problems || []).slice();
  try {
    const r = await call('save_config', S.cfg, S.mtimeNs, !!force, !!allowUnusable, editProfile());
    if (r && r.profile_missing) return await profileGone(r, { allowUnusable });
    if (r && r.saved) {
      S.savedStr = snap; S.problems = r.problems || [];
      if (r.mtime_ns !== undefined) S.mtimeNs = r.mtime_ns;
      const t = r.time ? new Date(r.time * 1000).toLocaleTimeString() : '';
      const tail = S.appDown === false ? '. The app picks it up straight away.' : (S.appDown === true ? '. The app is not running: start it from Status.' : '');
      let said = S.problems.length ? `Saved at ${t} with ${S.problems.length} problem${S.problems.length === 1 ? '' : 's'}` : `Saved at ${t}${tail}`;
      if (r.kept_broken) said += (said.endsWith('.') ? ' ' : '. ') + 'The file it replaced was not valid JSON and is kept as radial.json.broken.';
      toast(said, { tone: S.problems.length ? 'warn' : 'ok', ms: r.kept_broken ? 7000 : tail && S.appDown === true ? 4800 : 3800 });
      if (R.status) R.status(); else refreshAppDown();      // one quiet look, so the rail dot is right
      if (newProblems(prior, S.problems)) S.problemsOpen = true;     // the toast and the pill already count them; the panel opens for a new one only
      return 'saved';
    }
    if (r && r.conflict) {
      const v = await modal({ title: 'The file changed on disk',
        body: h('div', null, h('p', null, r.message || 'The menus file was changed by something else after Studio loaded it. Saving now would overwrite those changes.'),
          h('p', null, 'Reload discards your unsaved changes.')),
        actions: [{ text: 'Cancel', value: 'cancel', focus: true }, { text: 'Overwrite', value: 'overwrite', kind: 'danger-ghost' }, { text: 'Reload from disk', value: 'reload' }] });
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
          probs.length ? h('div', { class: 'changes-list' }, h('div', { class: 'chg-group' }, h('ul', null, probs.map(p => h('li', null, describeProblem(String(p)).text))))) : null),
        actions: [{ text: 'Keep editing', value: 'keep', kind: 'primary', focus: true }, { text: 'Save anyway', value: 'force', kind: 'danger-ghost' }] });
      return v === 'force' ? doSave({ allowUnusable: true }) : 'cancelled';   // never carries force: a new disk change still warns
    }
    toast((r && r.message) || 'The menus file could not be saved.', { tone: 'err' });
    return 'failed';
  } catch (e) { toast('Save failed: ' + (e.message || e), { tone: 'err' }); return 'failed'; }
}
async function revert() {
  if (!dirtyNow()) return;
  const body = unsavedBody('', n => (n ? (n === 1 ? 'This change is discarded' : `These ${n} changes are discarded`) : 'Your unsaved changes are discarded') + ' and Studio goes back to the last saved version.');
  const ok = await modal({ title: 'Revert changes', body, actions: [{ text: 'Keep editing', value: false, focus: true }, { text: 'Revert', kind: 'danger', value: true }] });
  if (!ok) return;
  S.cfg = JSON.parse(S.savedStr);
  if (!hasMenu(S.menuId)) S.menuId = Object.keys(S.cfg.menus)[0] || null;
  S.itemIdx = null; S.version++; updateDirty(); validateSoon(); previewSoon(); pushSnap();
  renderAllMenus(); if (R.settings) R.settings(); if (R.look) R.look(); if (R.libTarget) R.libTarget();
  toast('Reverted to the last saved version.', { ms: 2200 });
}

/* ================================================================== close guard */
// Lists what differs between the saved config and the current one, grouped by area.
function describeChanges() {
  let before = {};
  try { before = JSON.parse(S.savedStr || '{}') || {}; } catch (e) { before = {}; }
  const after = S.cfg || {};
  const groups = [];
  const q = s => '\u201c' + s + '\u201d';
  const itemName = it => it.empty === true ? 'Empty slot' : it.label || it.brush || it.alpha || it.material || it.texture || it.press || it.toggle || it.set || ('capture' in it ? 'Capture' : '') || ('tool' in it ? 'Tool' : '') || ('project' in it ? 'Project' : '') || ('layout' in it ? 'Layout' : '') ||(it.menu ? 'Submenu ' + it.menu : it.steps ? 'Steps' : it.tag ? 'Tag ' + it.tag : 'browser' in it ? 'Browser' + (it.browser ? ' ' + it.browser : '') : 'recent' in it ? (own(RECENT, it.recent) ? RECENT[it.recent].label : 'Recent') : 'item');
  const bm = before.menus || {}, am = after.menus || {};
  for (const id of Object.keys(am)) {
    const a = am[id] || {}, b = own(bm, id) ? bm[id] : undefined;
    const title = a.title || id;
    if (!b) { groups.push({ area: 'Menu ' + q(title), lines: ['New menu with ' + (a.items || []).length + ' item' + ((a.items || []).length === 1 ? '' : 's')] }); continue; }
    const lines = [];
    if ((a.title || '') !== (b.title || '')) lines.push('Renamed from ' + q(b.title || id));
    if ((a.hotkey || '') !== (b.hotkey || '')) lines.push('Hotkey: ' + (b.hotkey || 'none') + ' \u2192 ' + (a.hotkey || 'none'));
    if ((a.animation || '') !== (b.animation || '')) lines.push('Open animation: ' + (b.animation || 'same as all menus') + ' \u2192 ' + (a.animation || 'same as all menus'));
    if ((a.fan === true) !== (b.fan === true)) lines.push('Fan out as a submenu: ' + (b.fan === true ? 'on' : 'off') + ' \u2192 ' + (a.fan === true ? 'on' : 'off'));
    if ((a.swallow !== false) !== (b.swallow !== false)) lines.push('Swallow hotkey: ' + (b.swallow !== false ? 'on' : 'off') + ' \u2192 ' + (a.swallow !== false ? 'on' : 'off'));
    if ((a.keep_slots === true) !== (b.keep_slots === true)) lines.push('Keep slots in place: ' + (b.keep_slots === true ? 'on' : 'off') + ' \u2192 ' + (a.keep_slots === true ? 'on' : 'off'));
    if ((a.icon || '') !== (b.icon || '')) lines.push('Hub icon: ' + (b.icon || 'none') + ' \u2192 ' + (a.icon || 'none'));
    if (JSON.stringify(a.look) !== JSON.stringify(b.look)) {
      const tb = ZLook.summary(before, { level: 'menu', menu: id }, lookCtx()).text, ta = ZLook.summary(after, { level: 'menu', menu: id }, lookCtx()).text;
      lines.push(tb === ta ? 'Look settings changed (' + ta + ')' : 'Look: ' + tb + ' \u2192 ' + ta);
    }
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
      if (i >= 0) { changed.push([added[i], r]); added.splice(i, 1); removed.splice(removed.indexOf(r), 1); }
    }
    const blanks = l => l.filter(it => it && it.empty === true).length;      // empty slots are counted, not named one by one
    if (blanks(added)) lines.push('Added ' + plural(blanks(added), 'empty slot'));
    if (blanks(removed)) lines.push('Removed ' + plural(blanks(removed), 'empty slot'));
    for (const it of added) if (!(it && it.empty === true)) lines.push('Added ' + q(itemName(it)));
    for (const it of removed) if (!(it && it.empty === true)) lines.push('Removed ' + q(itemName(it)));
    for (const [it, was] of changed) {
      const bare = x => { const c = Object.assign({}, x); delete c.style; return JSON.stringify(c); };
      lines.push(bare(it) === bare(was) ? 'Style of ' + q(itemName(it)) + ' changed' : 'Changed ' + q(itemName(it)));      // only the style differs
    }
    // reordered: compare the items present on both sides, one-for-one, in their old and new order
    const left = new Map();
    for (const k of kept) left.set(k, (left.get(k) || 0) + 1);
    const keptBefore = bi.map(key).filter(k => (left.get(k) || 0) > 0 && left.set(k, left.get(k) - 1));
    if (JSON.stringify(keptBefore) !== JSON.stringify(kept)) lines.push('Items reordered');
    if (!lines.length && JSON.stringify(a) !== JSON.stringify(b)) lines.push('Changed');      // a setting this list has no words for yet
    if (lines.length) groups.push({ area: 'Menu ' + q(title), lines });
  }
  for (const id of Object.keys(bm)) if (!am[id]) groups.push({ area: 'Menu ' + q(bm[id].title || id), lines: ['Deleted'] });
  const ringLines = [], lookLines = [];
  const br = before.ring || {}, ar = after.ring || {};
  const bl = isPlainObj(before.looks) ? before.looks : {}, al = isPlainObj(after.looks) ? after.looks : {};
  const lookNames = [];
  for (const name of Object.keys(al)) {
    if (!own(bl, name)) lookNames.push('Added look ' + q(name));
    else if (JSON.stringify(al[name]) !== JSON.stringify(bl[name])) lookNames.push('Changed look ' + q(name));
  }
  for (const name of Object.keys(bl)) if (!own(al, name)) lookNames.push('Deleted look ' + q(name));
  const gname = v => (v ? ZLook.labelOf(v, lookCtx()) : 'none');
  if ((br.look || '') !== (ar.look || '')) lookNames.push('Global look: ' + gname(br.look) + ' \u2192 ' + gname(ar.look));
  if (lookNames.length) groups.push({ area: 'Looks', lines: lookNames });
  const NAMES = { radius: 'Ring radius', slot: 'Slot size', dead_zone: 'Dead zone', hub: 'Hub', tap_ms: 'Tap time', timeout_s: 'Auto-close', animation: 'Open animation', labels: 'Labels', slot_shape: 'Slot shape', tag_colors: 'Tag colours',
    tag_band: 'Tag band', tag_band_opacity: 'Tag band opacity', tag_glow_opacity: 'Tag glow opacity', tag_tint_opacity: 'Tag tint opacity', tag_tint_style: 'Tag tint style', tag_tint_blend: 'Tag tint blend',
    flick: 'Flick to pick', hover_submenus: 'Open submenus on hover', hint: 'Hint line', tag_limit: 'Tag fan slots' };
  for (const k of new Set([...Object.keys(br), ...Object.keys(ar)])) {
    if (k === 'colors' || k === 'look') continue;
    if (JSON.stringify(br[k]) !== JSON.stringify(ar[k])) (own(RING_LOOK, k) ? lookLines : ringLines).push((NAMES[k] || lookLabel(k)) + ': ' + (br[k] ?? 'default') + ' \u2192 ' + (ar[k] ?? 'default'));
  }
  const bc = br.colors || {}, ac = ar.colors || {};
  for (const k of new Set([...Object.keys(bc), ...Object.keys(ac)])) {
    if (bc[k] !== ac[k]) lookLines.push('Colour ' + k + ': ' + (bc[k] || 'default') + ' \u2192 ' + (ac[k] || 'default'));
  }
  if (lookLines.length) groups.push({ area: 'Look', lines: lookLines });
  if (ringLines.length) groups.push({ area: 'Settings', lines: ringLines });
  const bb = before.bridge || {}, ab = after.bridge || {};
  const bridgeLines = [];
  if ((bb.mode || 'auto') !== (ab.mode || 'auto')) bridgeLines.push('Mode: ' + (bb.mode || 'auto') + ' \u2192 ' + (ab.mode || 'auto'));
  if ((bb.key || '') !== (ab.key || '')) bridgeLines.push('Bridge key: ' + (bb.key || 'F9 (default)') + ' \u2192 ' + (ab.key || 'F9 (default)'));
  if (bridgeLines.length) groups.push({ area: 'ZBrush bridge', lines: bridgeLines });
  const bwb = before.browser || {}, bwa = after.browser || {};
  const quitOf = w => (Number.isInteger(w.quit_after_minutes) && w.quit_after_minutes > 0 ? w.quit_after_minutes + ' min' : 'off');
  const bwLines = [];
  if ((bwb.hotkey || '') !== (bwa.hotkey || '')) bwLines.push('Hotkey: ' + (bwb.hotkey || 'none') + ' → ' + (bwa.hotkey || 'none'));
  if (quitOf(bwb) !== quitOf(bwa)) bwLines.push('Quit hidden browser after: ' + quitOf(bwb) + ' → ' + quitOf(bwa));
  if (bwLines.length) groups.push({ area: 'Browser', lines: bwLines });
  const pfb = before.profile || {}, pfa = after.profile || {};
  if ((pfb.next_hotkey || '') !== (pfa.next_hotkey || '')) groups.push({ area: 'Profile', lines: ['Next profile hotkey: ' + (pfb.next_hotkey || 'none') + ' → ' + (pfa.next_hotkey || 'none')] });
  const known = new Set(['menus', 'ring', 'looks', 'bridge', 'browser', 'profile']);
  const other = [...new Set([...Object.keys(before), ...Object.keys(after)])].filter(k => !known.has(k) && JSON.stringify(before[k]) !== JSON.stringify(after[k]));
  if (other.length) groups.push({ area: 'Other', lines: other.map(k => 'Changed ' + k) });
  return groups;
}

/* The body of the dialogs that ask about unsaved changes: how many, and what they are. `doing` completes "... without saving loses them".
   With `intro` the first line is that text instead (Revert says it discards them, so "without saving" would be wrong). */
function unsavedBody(doing, intro) {
  const groups = describeChanges();
  const count = groups.reduce((n, g) => n + g.lines.length, 0);
  return h('div', { class: 'changes' },
    h('p', null, intro ? intro(count) : count ? `You have ${count} unsaved change${count === 1 ? '' : 's'}. ${doing} without saving loses ${count === 1 ? 'it' : 'them'}.` : `You have unsaved changes. ${doing} without saving loses them.`),
    groups.length ? h('div', { class: 'changes-list' }, groups.map(g => h('div', { class: 'chg-group' },
      h('div', { class: 'micro' }, g.area),
      h('ul', null, g.lines.map(l => h('li', null, l)))))) : null);
}
async function openCloseDialog() {
  if (S.closeDialogOpen) return;
  if (!dirtyNow()) { call('close_now').catch(() => {}); return; }
  S.closeDialogOpen = true;
  const v = await modal({ title: 'Unsaved changes', body: unsavedBody('Closing'), actions: [
    { text: 'Keep editing', value: 'keep' },
    { text: 'Close without saving', value: 'discard', kind: 'danger-ghost' },
    { text: 'Save and close', value: 'save', kind: 'primary' }] });
  S.closeDialogOpen = false;
  if (v === 'save') { const out = await save(); if (out === 'saved' && !dirtyNow()) call('close_now').catch(() => {}); }
  else if (v === 'discard') call('close_now').catch(() => {});
}
// Called by studio.py when the window is about to close and the page has unsaved changes.
window.__studioRequestClose = () => { openCloseDialog(); return true; };

function applyPrefs() {
  const full = isFull();                                    // roving tabindex: the chosen button is the one Tab stop
  modeBtns().forEach(b => { const on = (b.dataset.mode === 'full') === full; b.classList.toggle('on', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1; });
}
const modeBtns = () => $$('#modeSeg .seg-btn');          // none in the popout
/* Rebuilds what the mode changes, in place: showScreen would return early for the screen already shown. */
function applyMode() {
  if (openPopover) openPopover();
  if (comboClose) comboClose();
  if (S.screen === 'menus' && R.right) {
    const tb = $('.tab-body'), top = tb ? tb.scrollTop : 0;
    R.right();
    const nb = $('.tab-body'); if (nb) nb.scrollTop = top;
  } else if (S.screen === 'settings' && R.settings) R.settings();
  else if (S.screen === 'look' && R.look) R.look();
  for (const b of browsers.values()) b.updateTags();
}
/* Switches the mode. The pref is set at once, so what the caller does next already sees it; a failed save puts the old mode back. */
async function setMode(v) {
  if (!S.ready || S.fatal || v === S.prefs.mode || (v !== 'simple' && v !== 'full')) return;
  const ok = setPref('mode', v);
  applyMode();
  if (!(await ok)) applyMode();
}
/* Settings, at one card; Full-only cards switch to Full first. */
function openSettingsCard(id) {
  if (!isFull() && FULL_CARDS.has(id)) { setMode('full'); toast('Switched to Full mode to show this.', { ms: 3500 }); }
  showScreen('settings');
  requestAnimationFrame(() => R.gotoCard && R.gotoCard(id));
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

// ---- theme
/* The setting is S.prefs.theme (dark, light, system, which follows Windows, or zbrush, which takes the colours ZBrush stored); S.themeEff
   is the one in force (dark, light or zbrush). The CSS is dark until
   <html data-theme="light"> says otherwise. The ring colours the Colours rows start from belong to the theme, and the cached ring
   pictures were drawn in the old one (their keys do not say), so both are swapped here. */
const THEMES = ['dark', 'light', 'system', 'zbrush'];
/* Match ZBrush: data-theme is the base (dark or light) the scheme sits on, and its colours are inline custom properties on <html>, which
   the washes in styles.css (colour-mix of --accent, --cyan and --ink) follow. themeVars remembers which, so another theme can take them off. */
let themeVars = [];
const tokenKey = t => (t && typeof t === 'object') ? JSON.stringify(Object.entries(t).sort()) : '';   // what the popout compares to see a changed scheme
function applyTheme(eff, base, tokens) {
  eff = eff === 'light' || eff === 'zbrush' ? eff : 'dark';
  S.themeEff = eff;
  const root = document.documentElement;
  root.dataset.theme = eff === 'zbrush' ? (base === 'light' ? 'light' : 'dark') : eff;
  themeVars.forEach(k => root.style.removeProperty(k));
  themeVars = [];
  if (eff === 'zbrush' && tokens && typeof tokens === 'object') {
    for (const [k, v] of Object.entries(tokens)) {
      if (!/^--[a-z0-9-]+$/.test(k) || typeof v !== 'string') continue;
      root.style.setProperty(k, v); themeVars.push(k);
    }
  }
  S.themeTokens = tokenKey(eff === 'zbrush' ? tokens : null);
  const tc = S.opts && S.opts.theme_ring_colors && S.opts.theme_ring_colors[eff];
  if (tc && typeof tc === 'object') S.defaults = Object.assign({}, S.defaults, { colors: Object.assign({}, FALLBACK_DEFAULTS.colors, tc) });
  RingLoader.cache.clear(); RingLoader.gen++;
  FrameLoader.cache.clear(); FrameLoader.gen++;
}
/* Takes S.prefs.theme_effective, theme_base and theme_tokens in: applies them, tells the backend when the theme or a Match ZBrush scheme
   changed (the window frame follows), and redraws what the theme touches in place. Settings is rebuilt even when nothing changed,
   because its note and Reset titles depend on the setting. */
function syncTheme(rebuild = true) {
  const was = S.themeEff, wasTokens = S.themeTokens;
  applyTheme(S.prefs.theme_effective, S.prefs.theme_base, S.prefs.theme_tokens);
  if (S.themeEff !== was || S.themeTokens !== wasTokens) call(POPOUT ? 'popout_theme_changed' : 'theme_changed', S.themeEff).catch(() => {});
  if (POPOUT) return;                                       // the browser holds no picture drawn from the theme
  if (rebuild && ((S.screen === 'settings' && R.settings) || (S.screen === 'look' && R.look))) {
    if (openPopover) openPopover();
    if (comboClose) comboClose();
    (S.screen === 'look' ? R.look : R.settings)();          // build() ends in R.preview()
  } else if (R.preview) R.preview();
}
/* Follow Windows: the page's colour scheme moves with the Windows app mode, and the pages are told at once. Python reads the same
   registry value at start and each time the browser is shown, so this is only for a flip while the window is open. */
function watchSystemTheme() {
  const mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)');
  if (!mq) return;
  mq.addEventListener('change', () => {
    if (S.prefs.theme !== 'system' || !(S.ready || POPOUT) || S.fatal) return;
    S.prefs.theme_effective = S.prefs.theme_base = mq.matches ? 'light' : 'dark';
    S.prefs.theme_tokens = {};
    // Windows flipped on its own (a schedule, say): the Settings page is only rebuilt when nobody is typing or
    // recording a key in it, so the flip never throws away what they were doing. The pictures follow either way.
    syncTheme(!typingInSettings());
  });
}
const typingInSettings = () => {
  const a = document.activeElement;
  return !!(a && a.closest && a.closest('#screen-settings, #screen-look') && a.matches('input, textarea, select, [contenteditable], .hk-field'));
};
/* Match ZBrush: a Store Config in ZBrush changes the colours while the setting stays "zbrush", so the page asks again when its window
   gets the focus. Studio compares theme_sig; the browser has no signature in its state, so it compares the tokens. */
function watchZbrushTheme() {
  let busy = false;
  window.addEventListener('focus', async () => {
    if (S.prefs.theme !== 'zbrush' || !(S.ready || POPOUT) || S.fatal || busy) return;
    busy = true;
    try {
      const p = await call(POPOUT ? 'popout_get_state' : 'get_prefs');
      if (!p || typeof p !== 'object' || S.prefs.theme !== 'zbrush') return;
      const same = POPOUT ? p.theme_effective === S.themeEff && tokenKey(p.theme_tokens) === S.themeTokens
        : p.theme_sig === S.prefs.theme_sig && p.theme_effective === S.themeEff;
      if (same) return;
      for (const k of ['theme_effective', 'theme_base', 'theme_tokens', 'theme_sig', 'theme_source']) if (k in p) S.prefs[k] = p[k];
      if (THEMES.includes(p.theme)) S.prefs.theme = p.theme;
      syncTheme(!typingInSettings());
    } catch (e) { /* the colours stay as they are */ }
    finally { busy = false; }
  });
}
// The browser: Popout.show() calls this when the setting or Windows' mode changed since it was last shown. It has updated the frame itself.
window.__popoutTheme = o => {
  if (!o) return false;
  if (THEMES.includes(o.setting)) S.prefs.theme = o.setting;
  applyTheme(o.effective, o.base, o.tokens);
  S.prefs.theme_effective = S.themeEff;
  return true;
};

/* Alt+1 to Alt+6: the screen's index in SCREEN_ORDER, read from the physical digit key so it works on AZERTY (where the row types & and é unshifted), or null. */
const screenKey = e => { const m = /^Digit([1-6])$/.exec(e.code || ''); return m ? +m[1] - 1 : null; };
// look-screen.js builds the Look screen; it is looked up when the screen is shown, so a missing file only costs that screen
const buildLookScreenLazy = root => { if (typeof window.buildLookScreen === 'function') window.buildLookScreen(root); else root.replaceChildren(h('div', { class: 'fhint warn', style: { padding: '24px' } }, 'The Look screen could not be loaded.')); };
/* What look-screen.js needs from this closure: it is loaded after app.js and cannot see inside it. */
window.ZStudio = { h, $, $$, S, R, icon, iconBtn, linkBtn, card, foldSection, foldOpen, foldIsOpen, foldSum, choiceCards, sliderRow, sizeRow, toggleSwitch, call, clamp, own, normHex,
  commit, toast, ring, ringNum, ranges, ensureRing, tidyRing, slotIdx, menuOf, kindOf, isLib, firstTag, isFull, setMode, fullOnlyChanges,
  RingLoader, SAMPLE_MENU, COLOR_INFO, FALLBACK_DEFAULTS, showScreen, railTitle, makePlayer, FrameLoader, ANIM_INFO,
  lookCtx, clearedText, modal, promptModal, popover, undoToast, sealSnap, previewSoon, plural, hasMenu, selectMenu, debounce, FALLBACK_RANGES, makeRingView, itemLabel };
const SCREEN_BUILD = { menus: buildMenusScreen, look: buildLookScreenLazy, library: buildLibraryScreen, settings: buildSettingsScreen, status: buildStatusScreen, setup: buildSetupScreen };
const SCREENS = Object.fromEntries(SCREEN_ORDER.map(k => [k, SCREEN_BUILD[k]]));
// the element that scrolls on each screen (its position is remembered when you leave and put back when you return)
const SCREEN_SCROLLER = { menus: '.ilist', look: '.look-scroll', library: '.b-scroll', settings: '.settings-scroll', status: '.settings-scroll', setup: '.settings-scroll' };
const scrollerOf = name => { const root = $('#screen-' + name); return root ? $(SCREEN_SCROLLER[name] || '.settings-scroll', root) : null; };
let lastScreenChain = Promise.resolve();   // writes run one after another, so two quick switches cannot land out of order
const saveLastScreen = name => { lastScreenChain = lastScreenChain.then(() => call('set_pref', 'last_screen', name)).catch(() => {}); };
/* The screens visited, for the mouse's Back and Forward buttons. A new visit drops whatever was ahead, like a web browser. */
const screenNav = { list: [], at: -1, replay: false };
function noteScreen(name) {
  if (screenNav.replay) return;
  screenNav.list.splice(screenNav.at + 1);
  screenNav.list.push(name);
  if (screenNav.list.length > 50) screenNav.list.shift();
  screenNav.at = screenNav.list.length - 1;
}
/* Back (-1) or forward (1): first through the folders and tabs of the Library browser, then through the screens. */
function navStudio(d) {
  if (!S.ready || S.fatal || document.querySelector('.tour-card')) return;
  const b = S.screen === 'library' ? browsers.get(S.lib) : null;
  if (b && b.navStep(d)) return;
  const to = screenNav.list[screenNav.at + d];
  if (!to) return;
  screenNav.at += d; screenNav.replay = true;
  try { showScreen(to); } finally { screenNav.replay = false; }
}
/* Wires the mouse's Back and Forward buttons (buttons 3 and 4) to `step`. The web view would otherwise try to go back a page itself. */
function installMouseNav(step) {
  const isNav = e => { if (e.button === 3 || e.button === 4) { e.preventDefault(); return true; } return false; };
  window.addEventListener('mousedown', isNav, true);
  window.addEventListener('auxclick', isNav, true);
  window.addEventListener('mouseup', e => {
    if (!isNav(e)) return;
    if ($('#overlay-root').firstElementChild || $('.popover')) return;       // a dialog or a menu has the pointer
    step(e.button === 3 ? -1 : 1);
  }, true);
}
function showScreen(name, { fresh = false } = {}) {
  name = Object.keys(SCREENS).find(k => k === name) || 'menus';     // the name from the list, never the one passed in (a link or studio.json)
  if (openPopover) openPopover();
  if (comboClose) comboClose();
  if (S.shown && name === S.screen) return;
  noteScreen(name);
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
  const since = refresh && L.loaded && L.state === 'ready' && L.signature ? L.signature : '';      // the list the page holds: the backend answers "unchanged" without it when the folders still give that list
  try { r = await call('get_library', ...(since ? [true, kind, since] : [!!refresh, kind])); } catch (e) { r = { error: String((e && e.message) || e) }; }
  r = r || {};
  const gotList = r.unchanged || (Array.isArray(r.items) ? r.items : Array.isArray(r.brushes) ? r.brushes : []).length > 0;
  if (refresh && r.error && !gotList && L.loaded && L.state === 'ready' && L.items.length) {   // a rescan that brought no list at all (the call failed): keep what is on show, report the error; one unreadable folder still brings the others' list
    L.error = String(r.error); L.busy = false; paintRescan();
    if (R.libRefresh) R.libRefresh(kind);                                  // the error shows above the list
    return;
  }
  if (since && r.unchanged && r.signature === since) {                    // the same list: keep it, and take only what may differ beside it
    const was = JSON.stringify([L.sources, L.zbrushFound, L.error]);
    L.sources = Array.isArray(r.sources) ? r.sources : [];
    L.zbrushFound = r.zbrush_found !== false;
    L.error = r.error ? String(r.error) : null;
    L.state = L.error && !L.items.length ? 'error' : 'ready';        // one folder that cannot be read: the others' items still show, with the error above them
    L.busy = false;
    popScanned[kind] = Date.now();
    Thumbs.forgetMisses(kind);
    if (was !== JSON.stringify([L.sources, L.zbrushFound, L.error])) { if (R.libRefresh) R.libRefresh(kind); }
    else retryMissedThumbs(kind);
    paintRescan();
    return;
  }
  L.signature = r.signature || '';
  L.items = Array.isArray(r.items) ? r.items : Array.isArray(r.brushes) ? r.brushes : [];
  L.sources = Array.isArray(r.sources) ? r.sources : [];
  L.zbrushFound = r.zbrush_found !== false;
  L.error = r.error ? String(r.error) : null;
  L.sorted = L.items.slice().sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true }));
  L.byName = new Map(L.items.map(b => [nameKey(b.name), b]));
  L._tree = L._tc = null;
  L.state = L.error && !L.items.length ? 'error' : 'ready';          // the backend keeps an unreadable folder's items and reads the others: show them, with the error above
  L.loaded = true; L.busy = false;
  if (refresh) Thumbs.forgetMisses(kind);
  if (R.libRefresh) R.libRefresh(kind);
  if (S.screen === 'menus' && S.tab === 'item') {                          // the inspector resolves names against the library: repaint its hints, never rebuild it (the user may be typing in it)
    if (R.itemHint) R.itemHint();
    if (tagField && tagField.sel.isConnected) tagField.paint();
  }
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
  const tooNew = !isErr && !!(res && res.too_new);              // made by a newer ZOrbit: nothing here may touch the files, so only Open folder is offered
  const backup = !isErr && !tooNew && !!(res && res.backup_exists);
  const loading = $('#screens > .loading'); if (loading) loading.remove();
  // The screens need the menus: the rail and Alt+1 to Alt+6 do nothing until the file is fixed, so the rail looks that way.
  $$('.rail-btn').forEach(b => { b.classList.remove('on'); b.setAttribute('aria-current', 'false'); b.setAttribute('aria-disabled', 'true'); b.title = 'Fix or reset the menus file first'; });
  $('#saveBtn').disabled = true; $('#revertBtn').disabled = true;
  modeBtns().forEach(b => { b.disabled = true; });
  if (!isErr) { takeProfile(res); renderProfile(); }          // the picker stays usable: another profile may be fine
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
  const logsBtn = h('button', { class: 'btn', type: 'button', title: 'Where the logs are kept', onclick: async () => { try { await call('open_folder', 'data'); } catch (e) { toast('Could not open the folder.', { tone: 'warn' }); } } }, icon('folder', 13), 'Open logs folder');
  const restoreBtn = backup ? h('button', { class: 'btn', type: 'button', onclick: async () => {
    const ok = await modal({ title: 'Restore the backup?',
      body: h('p', null, 'Replaces your menus file with the last saved backup. The current file is kept as radial.json.broken.'),
      actions: [{ text: 'Cancel', value: false, focus: true }, { text: 'Restore backup', value: true, kind: 'danger' }] });
    if (ok) run(restoreBtn, 'restore_backup');
  } }, icon('undo', 13), 'Restore backup') : null;
  const resetBtn = h('button', { class: 'btn danger-ghost', type: 'button', onclick: async () => {
    const ok = await modal({ title: 'Start from defaults?',
      body: h('p', null, 'This replaces your menus file with the built-in default menus. Your current file is kept as radial.json.broken next to it. An older radial.json.broken is replaced.'),
      actions: [{ text: 'Cancel', value: false, focus: true }, { text: 'Start from defaults', value: true, kind: 'danger' }] });
    if (ok) run(resetBtn, 'reset_config');
  } }, 'Start from defaults');
  $$('.screen').forEach(sc => { sc.hidden = sc.id !== 'screen-menus'; });
  $('#screen-menus').replaceChildren(h('div', { class: 'fatal' }, icon('alert', 36), h('h2', null, tooNew ? 'These files are from a newer ZOrbit' : 'Could not read your menus file'),
    path ? h('p', { class: 'fatal-path mono' }, path) : null,
    h('pre', { class: 'fatal-err mono' }, msg),
    h('p', { class: 'fatal-lead' }, tooNew ? 'Nothing has been changed, and Studio will not change these files.' : backup ? 'Nothing has been changed. You can fix the file yourself, restore the last good backup, or start again from the defaults.' : 'Nothing has been changed. You can fix the file yourself or start again from the defaults.'),
    h('div', { class: 'btn-row' }, ...(tooNew ? [folderBtn] : [folderBtn, logsBtn, restoreBtn, resetBtn, h('button', { class: 'btn primary', type: 'button', onclick: () => location.reload() }, 'Try again')]))));
}

/* ================================================================== after the first screen: what's new, old files, an old app */
const openLink = async url => { try { await call('open_url', url); } catch (e) { toast('Could not open the link.', { tone: 'warn' }); } };
/* Text with `code`, **bold** and #123 (a GitHub issue of ZOrbit) in it, as nodes. Never innerHTML. */
function mdInline(text) {
  return String(text == null ? '' : text).split(/(`[^`]+`|\*\*[^*]+\*\*|(?<![\w/#&])#\d+)/).filter(Boolean).map(part => {
    let m;
    if ((m = /^`([^`]+)`$/.exec(part))) return h('code', null, m[1]);
    if ((m = /^\*\*([^*]+)\*\*$/.exec(part))) return h('b', null, m[1]);
    if (/^#\d+$/.test(part)) return h('button', { class: 'link', type: 'button', title: 'Open issue ' + part + ' on GitHub', onclick: () => openLink('https://github.com/combwizard/zorbit/issues/' + part.slice(1)) }, part);
    return part;
  });
}
function whatsNewBody(sections) {
  return sections.map(s => h('section', { class: 'wn-sec' },
    h('h3', null, /^unreleased$/i.test(s.version) ? 'Not released yet' : String(s.version) + (s.date ? ' (' + s.date + ')' : '')),
    (s.summary || []).map(p => h('p', null, mdInline(p))),
    s.items && s.items.length ? h('ul', null, s.items.map(i => h('li', null, mdInline(i)))) : null,
    s.url ? h('button', { class: 'link', type: 'button', onclick: () => openLink(s.url) }, 'Full release notes') : null));
}
/* The release notes dialog. all: every section up to this version (the Settings button), else only what is new since the last one seen.
   Resolves false when there was nothing to show. Closing it, however it closes, records this version as seen (remember). */
async function showWhatsNew({ all = false, remember = true } = {}) {
  const d = await call('get_whats_new', all);
  const secs = d && Array.isArray(d.sections) ? d.sections : [];
  if (!secs.length) return false;
  const cur = String(d.current || '');
  await modal({ title: `What's new in ZOrbit ${cur}`.trim(), body: h('div', { class: 'wn' }, whatsNewBody(secs)), actions: [{ text: 'Close', value: true, kind: 'primary', focus: true }] });
  if (remember && cur) setPref('seen_version', cur);
  return true;
}
/* The update dialog (the version chip, or the button in Settings > Studio), for a newer release. A copy Setup installed
   (check_update's can_install): download_update fetches the setup and checks its SHA-256; installUpdate deals with unsaved
   changes and hands over to install_update, which starts Setup and closes Studio. Setup opens Studio again when it is done.
   A portable copy gets the release page instead. "Don't remind me again" stores the version as skipped_version: the top
   stops pointing it out until a newer one comes, and Settings > Studio still offers it. */
let updateOpen = false;
/* The new release's notes (check_update's notes), drawn like a What's new section, or only a link when it has none. */
function updateNotes(u) {
  const n = u.notes;
  if (!n || !((n.summary || []).length || (n.items || []).length))
    return h('button', { class: 'link', type: 'button', onclick: () => openLink(u.url) }, `Release notes for ${u.latest}`);
  return h('div', { class: 'wn upd-notes', tabindex: '0', 'aria-label': `Release notes for ${u.latest}` }, whatsNewBody([n]),
    n.blog ? h('button', { class: 'link', type: 'button', onclick: () => openLink(n.blog) }, 'More about this release on the blog') : null);
}
async function openUpdate(u) {
  if (updateOpen || !u || !u.newer) return;
  updateOpen = true;
  try {
    const skip = u.skipped ? [] : [{ text: "Don't remind me again", value: 'skip' }];
    if (!u.can_install) {
      const v = await modal({ title: 'Update ZOrbit', body: h('div', { class: 'upd' },
        h('p', { class: 'upd-ver mono' }, `v${u.current} to v${u.latest}`),
        updateNotes(u),
        h('p', null, u.installed
          ? 'Studio could not confirm the setup file of this release, so it will not install it. Download the new version from its release page.'
          : 'This copy of ZOrbit was not installed with Setup, so it cannot update itself. Download the new version from its release page.')),
      actions: [...skip, { text: 'Later', value: 'later' }, { text: 'Open the download page', value: 'page', kind: 'primary', focus: true }] });
      if (v === 'page') openLink(u.url);
      else if (v === 'skip') await skipUpdate(u);
      return;
    }
    const fill = h('i'), bar = h('div', { class: 'upd-bar', hidden: true }, fill);
    const spin = h('span', { class: 'spin', hidden: true }), text = h('span', null, '');
    const status = h('p', { class: 'upd-line', role: 'status' }, spin, text);
    const say = (t, { busy = false, warn = false } = {}) => { text.textContent = t; spin.hidden = !busy; status.classList.toggle('warn', warn); };
    let fetching = false;
    const show = p => {
      if (!fetching) return;                                   // a late poll reply after the download ended
      const pct = p && p.total ? Math.min(100, Math.round(100 * p.done / p.total)) : 0;
      bar.hidden = false; fill.style.width = pct + '%';
      say(`Downloading... ${pct} %`, { busy: true });
    };
    let p0 = null;
    try { p0 = await call('get_update_progress'); } catch (e) { p0 = null; }
    const ready = !!(p0 && p0.state === 'ready' && p0.version === u.latest);
    if (p0 && p0.state === 'downloading') say('Downloading...', { busy: true });
    else if (ready) say('Downloaded. Ready to install.');
    else if (p0 && p0.state === 'failed' && p0.message) say(p0.message, { warn: true });
    const download = async () => {
      fetching = true;
      say('Downloading...', { busy: true });
      const poll = setInterval(async () => { try { show(await call('get_update_progress')); } catch (e) { /* the next poll tries again */ } }, 250);
      let r;
      try { r = await call('download_update'); }
      catch (e) { r = { ok: false, message: 'The download did not work: ' + ((e && e.message) || e) }; }
      finally { clearInterval(poll); fetching = false; }
      if (!r || !r.ok) { bar.hidden = true; say((r && r.message) || 'The download did not work.', { warn: true }); return false; }
      fill.style.width = '100%';
      say('Downloaded and checked.');
      return true;
    };
    const v = await modal({ title: 'Update ZOrbit', body: h('div', { class: 'upd' },
      h('p', { class: 'upd-ver mono' }, `v${u.current} to v${u.latest}`),
      updateNotes(u),
      h('p', null, 'Studio closes while Setup runs and opens again when it is done. Setup restarts the ring app too. Afterwards, restart ZBrush so it loads the new plugin.'),
      status, bar),
    actions: [...skip,
      { text: 'Later', value: 'later' },
      { text: ready ? 'Install and restart' : 'Download and install', value: 'install', kind: 'primary', focus: true, check: download }] });
    if (v === 'install') await installUpdate();
    else if (v === 'skip') await skipUpdate(u);
  } finally { updateOpen = false; }
}
async function skipUpdate(u) {
  if (!(await setPref('skipped_version', u.latest))) return;
  if (window.RadialUpdate) window.RadialUpdate.check();           // the chip goes back to the plain version
  toast(`You will not be reminded about ZOrbit ${u.latest} again. Settings > Studio still offers it.`, { ms: 6000 });
}
/* After the download: unsaved changes are saved or dropped first (as on close), then Setup starts and Studio closes. */
async function installUpdate() {
  if (dirtyNow()) {
    const v = await modal({ title: 'Unsaved changes', body: unsavedBody('Updating'), actions: [
      { text: 'Keep editing', value: 'keep' },
      { text: 'Update without saving', value: 'discard', kind: 'danger-ghost' },
      { text: 'Save and update', value: 'save', kind: 'primary' }] });
    if (v === 'save') { const out = await save(); if (out !== 'saved' || dirtyNow()) return; }
    else if (v !== 'discard') return;
  }
  let r;
  try { r = await call('install_update'); } catch (e) { r = { ok: false, message: 'Setup did not start: ' + ((e && e.message) || e) }; }
  if (r && r.ok) toast('Installing the update. Studio opens again when it is done.', { ms: 8000 });
  else toast((r && r.message) || 'Setup did not start.', { tone: 'warn', ms: 7000 });
}
window.__studioUpdate = u => openUpdate(u);
/* Menus or tags an older ZOrbit left where this one does not look (get_strays). Add them as a profile or set them aside; Escape asks again next start. */
async function offerStrays() {
  if (S.fatal || !S.profilesOn) return;
  const d = await call('get_strays');
  if (!d || !d.found) return;
  const n = (v, one, many) => v + ' ' + (v === 1 ? one : many);
  const what = [d.menus ? n(d.menus, 'menu', 'menus') : '', d.tags ? n(d.tags, 'tag', 'tags') : ''].filter(Boolean).join(' and ') || 'menus and tags';
  const when = typeof d.when === 'number' ? ' on ' + localDate(new Date(d.when * 1000)) : '';
  const inp = h('input', { class: 'inp', type: 'text', value: d.name || 'From an older version', spellcheck: 'false', autocomplete: 'off' });
  const msg = h('p', { class: 'warn-text', role: 'alert', hidden: true });
  const say = t => { msg.textContent = t || ''; msg.hidden = !t; };
  inp.addEventListener('input', () => say(''));
  inp.addEventListener('keydown', e => {
    if (e.key !== 'Enter' || e.isComposing) return;
    e.preventDefault();
    const box = inp.closest('.modal'), ok = box && $('.btn.primary', box);
    if (ok) ok.click();
  });
  let res = null;
  const run = async (fn, fail) => {
    let r;
    try { r = await fn(); } catch (e) { r = { ok: false, message: fail + ((e && e.message) || e) }; }
    if (r && r.ok) { res = r; return true; }
    say((r && r.message) || fail);
    return false;
  };
  const v = await modal({ title: 'Files from an older ZOrbit',
    body: [h('p', null, `An older version of ZOrbit saved ${what}${when} in a place this version no longer reads.`),
      h('p', null, 'You can add them as a profile, or set them aside in the pre-profiles folder.'),
      h('label', { class: 'modal-field' }, 'Profile name', inp), msg],
    actions: [
      { text: 'Set aside', value: 'aside', check: () => run(() => call('adopt_strays', 'aside'), 'Could not set the files aside: ') },
      { text: 'Add as a profile', value: 'profile', kind: 'primary', focus: true, check: () => {
        const t = inp.value.trim();
        if (!t) { say('Type a name first.'); inp.focus(); return Promise.resolve(false); }
        return run(() => call('adopt_strays', 'profile', t), 'Could not add the profile: ');
      } }] });
  if (v === 'profile' && res) {
    takeNames(res); renderProfile();
    toast(`Made the profile ${res.name}.`, { tone: 'ok', ms: 7000, action: { text: 'Switch', fn: () => switchProfile(res.name) } });
  } else if (v === 'aside') {
    toast('Set aside in the pre-profiles folder.', { tone: 'ok', ms: 7000, action: { text: 'Open folder', fn: async () => { try { await call('open_folder', 'pre-profiles'); } catch (e) { toast('Could not open the folder.', { tone: 'warn' }); } } } });
  }
}
/* The running app is older than this Studio (an upgrade while ZBrush was open): say so, with a way to restart it. */
async function warnOlderApp() {
  if (S.fatal) return;
  const st = await refreshAppDown();
  if (!st || !st.app_older || !st.app_running) return;
  toast(`The app running is ZOrbit ${st.app_version || 'older'}, older than this Studio.`, { tone: 'warn', ms: 9000, action: { text: 'Restart app', fn: async () => {
    await startAppFlow({ paint: () => {} });
    await refreshAppDown();
    if (S.screen === 'status' && R.status) R.status();
  } } });
}
/* Skipped on the Setup screen, the recovery screen and a ?screen= page. A failed call only skips its own step. */
async function afterBoot() {
  if (S.fatal || S.screen === 'setup' || S.prefs.setup_done === false || params.has('screen')) return;
  try { await showWhatsNew(); } catch (e) { /* no release notes this time */ }
  try { await offerStrays(); } catch (e) { /* asks again next start */ }
  try { await offerTour(); } catch (e) { /* offered again next start */ }      // after every dialog: a dialog ends the tour
  try { await warnOlderApp(); } catch (e) { /* no toast */ }
}

/* ================================================================== tour */
/* The guided tour (#41). A stop names the screen it needs and the element to light up. A stop whose element is missing,
   hidden or squeezed to nothing (profiles off, a narrow window) is skipped. */
const TOUR_STOPS = [
  { screen: null, target: () => $('.rail'), title: 'Screens', text: 'Studio has six screens. Click one here, or press Alt+1 to Alt+6. Status and Setup are there when something is not working.' },
  { screen: 'menus', target: () => $('#screen-menus .stage'), title: 'The ring', text: 'How the ring will look. Drag brushes onto it, drag slots to reorder them, and click one to edit it. The menus are listed on the left: a menu with a hotkey opens over ZBrush, one without is a submenu.' },
  { screen: 'menus', target: () => $('#screen-menus .right-col .tabs'), title: 'Item, Menu, Library', text: 'Item edits the slot you clicked, Menu edits the whole ring, and Library lists brushes to drag in.' },
  { screen: 'look', target: () => $('#screen-look .look-left .mini-stage'), title: 'Look', text: 'How the ring looks and opens: its size, the shape of the slots, labels, colours and the open animation. It applies to every menu, and the preview here shows any menu you pick and plays the animation.' },
  { screen: null, target: () => $('#modeSeg'), title: 'Simple and Full', text: 'Simple shows the everyday controls. Full shows every control. The ring is the same in both.' },
  { screen: null, target: () => [$('#revertBtn'), $('#saveBtn')], title: 'Save', text: 'Nothing reaches the ring until you save. Then it applies straight away. Revert goes back to what was saved. You can take this tour again from Setup or Settings > Studio.' }
];
/* The bounding box of a stop's element(s) on screen, or null when none of them can be seen. */
function tourRect(stop) {
  let t = null;
  try { t = stop.target(); } catch (e) { /* no target */ }
  const rs = (Array.isArray(t) ? t : [t]).filter(el => el && el.isConnected && !el.closest('[hidden]')).map(el => el.getBoundingClientRect())
    .filter(r => r.width > 0 && r.height > 0 && r.right > 0 && r.bottom > 0 && r.left < innerWidth && r.top < innerHeight);
  if (!rs.length) return null;
  return { left: Math.min(...rs.map(r => r.left)), top: Math.min(...rs.map(r => r.top)), right: Math.max(...rs.map(r => r.right)), bottom: Math.max(...rs.map(r => r.bottom)) };
}
/* Where the card goes beside the lit box r (w by h): right, else below, else left, else above, whichever fits with a 12px margin;
   when none does, over the bottom of the box. Always clamped into the window. */
function tourCardPos(r, w, hgt) {
  const W = innerWidth, H = innerHeight, gap = 12, m = 12;
  const fits = [[r.right + gap, r.top, r.right + gap + w <= W - m], [r.left, r.bottom + gap, r.bottom + gap + hgt <= H - m],
    [r.left - gap - w, r.top, r.left - gap - w >= m], [r.left, r.top - gap - hgt, r.top - gap - hgt >= m]];
  const c = fits.find(f => f[2]) || [(r.left + r.right - w) / 2, r.bottom - hgt - gap];
  return [clamp(c[0], m, Math.max(m, W - m - w)), clamp(c[1], m, Math.max(m, H - m - hgt))];
}
/* Opens the tour. Returns false when it cannot (still loading, a recovery screen, a dialog or a tour already open). */
function startTour() {
  if (S.fatal || !S.ready || activeTour || activeModal) return false;
  if (openPopover) openPopover();
  if (comboClose) comboClose();
  const ret = S.screen, prev = document.activeElement;
  let dead = false, cur = -1, stops = [];
  const hole = h('div', { class: 'tour-hole', 'aria-hidden': 'true' });
  const count = h('span', { class: 'tour-count' });
  const title = h('h2', { id: 'tourTitle' }), text = h('p', { id: 'tourText' });
  const endBtn = h('button', { class: 'link tour-end', type: 'button', onclick: () => end() }, 'End tour');
  const backBtn = h('button', { class: 'btn small', type: 'button', onclick: () => back() }, 'Back');
  const nextBtn = h('button', { class: 'btn small primary', type: 'button', onclick: () => next() }, 'Next');
  const card = h('div', { class: 'tour-card', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'tourTitle', 'aria-describedby': 'tourText' },
    h('div', { 'aria-live': 'polite', 'aria-atomic': 'true' }, count, title, text), h('div', { class: 'tour-actions' }, endBtn, backBtn, nextBtn));   // each stop is read out whole
  const layer = h('div', { class: 'tour' }, hole, card);
  const eat = e => { if (e.target === layer) { e.preventDefault(); e.stopPropagation(); } };   // a click on the dim part goes nowhere
  layer.addEventListener('mousedown', eat); layer.addEventListener('click', eat);
  /* A stop can be shown when its screen is up and its element can be seen (checked again at each step: the window may have changed). */
  const usable = stop => { if (stop.screen && S.screen !== stop.screen) showScreen(stop.screen); return !!tourRect(stop); };
  /* Puts the lit box and the card at the current stop. False when the element can no longer be seen. */
  const place = () => {
    const r = tourRect(stops[cur]);
    if (!r) return false;
    const pad = 6;
    hole.style.left = (r.left - pad) + 'px'; hole.style.top = (r.top - pad) + 'px';
    hole.style.width = (r.right - r.left + 2 * pad) + 'px'; hole.style.height = (r.bottom - r.top + 2 * pad) + 'px';
    const [x, y] = tourCardPos({ left: r.left - pad, top: r.top - pad, right: r.right + pad, bottom: r.bottom + pad }, card.offsetWidth, card.offsetHeight);
    card.style.left = x + 'px'; card.style.top = y + 'px';
    return true;
  };
  // The lit box follows its element when that changes size on its own (a column settling, a late layout).
  const ro = typeof ResizeObserver === 'function' ? new ResizeObserver(() => { if (!dead && cur >= 0) place(); }) : null;
  const show = (i, fromBack) => {
    cur = i;
    if (ro) { ro.disconnect(); let t = null; try { t = stops[i].target(); } catch (e) { /* none */ } (Array.isArray(t) ? t : [t]).forEach(el => { if (el) ro.observe(el); }); }
    count.textContent = (i + 1) + ' of ' + stops.length;
    title.textContent = stops[i].title; text.textContent = stops[i].text;
    backBtn.disabled = i === 0;
    nextBtn.textContent = i === stops.length - 1 ? 'Done' : 'Next';
    place();
    (fromBack && !backBtn.disabled ? backBtn : nextBtn).focus();     // Back keeps the focus on Back
    requestAnimationFrame(() => { if (!dead) place(); });      // the screen may still be settling
  };
  const find = dir => { for (let i = cur + dir; i >= 0 && i < stops.length; i += dir) if (usable(stops[i])) return i; return -1; };
  const next = () => { if (cur < 0) return; const i = find(1); if (i < 0) end(); else show(i); };
  const back = () => { if (cur < 0) return; const i = find(-1); if (i >= 0) show(i, true); };
  const onResize = () => { if (cur >= 0 && !place()) next(); };
  const onKey = e => {
    if ((e.ctrlKey || e.altKey || e.metaKey) && e.key !== 'F4') { e.preventDefault(); e.stopPropagation(); return; }   // Ctrl+S, Ctrl+Z and Alt+1 to Alt+6 wait until the tour is over; Alt+F4 still closes the window
    const stop = () => { e.preventDefault(); e.stopPropagation(); };
    if (e.key === 'Escape') { stop(); end(); }
    else if (e.key === 'ArrowRight') { stop(); next(); }
    else if (e.key === 'ArrowLeft') { stop(); back(); }
    else if (e.key === 'Tab') {
      const f = $$('button', card).filter(x => !x.disabled);
      if (!f.length) return;
      const first = f[0], last = f[f.length - 1];
      if (!card.contains(document.activeElement)) { stop(); first.focus(); }
      else if (e.shiftKey && document.activeElement === first) { stop(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { stop(); first.focus(); }
    }
  };
  function end() {
    if (dead) return;
    dead = true;
    if (activeTour === me) activeTour = null;
    document.removeEventListener('keydown', onKey, true);
    window.removeEventListener('resize', onResize);
    if (ro) ro.disconnect();
    layer.remove();
    const app = $('#app'); if (app && !activeModal) app.inert = false;     // a dialog that is open keeps the page behind it inert
    if (ret && ret !== S.screen && own(SCREENS, ret)) showScreen(ret);
    if (S.prefs.tour_seen === false) setPref('tour_seen', true);
    if (prev && prev !== document.body && prev.focus && document.contains(prev)) prev.focus();
    else {                                                           // Settings and Setup were drawn again: back to their Take the tour button
      const again = $$('#screen-' + S.screen + ' button').find(b => b.textContent === 'Take the tour');
      if (again) again.focus();
    }
  }
  const me = { end };
  activeTour = me;
  showScreen('menus');
  document.addEventListener('keydown', onKey, true);
  window.addEventListener('resize', onResize);
  const appEl = $('#app'); if (appEl) appEl.inert = true;
  $('#overlay-root').append(layer);
  // Measure after the Menus screen has been laid out; the lit box and card appear in place, then move with a transition.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (dead) return;
    stops = TOUR_STOPS.filter(usable);
    if (!stops.length) { end(); return; }
    show(0);
    requestAnimationFrame(() => { if (!dead) layer.classList.add('in'); });
  }));
  return true;
}
function endTour() { if (activeTour) activeTour.end(); }
window.startTour = startTour;                                  // the file is one closure: the docs screenshot tool calls this from the page
/* The first time Studio is ready after Setup: asks once. Whatever the answer (even Escape), it is not asked again. */
async function offerTour() {
  if (S.prefs.tour_seen !== false || S.fatal || !S.ready) return;
  const v = await modal({ title: 'Take a short tour of Studio?',
    body: h('p', null, 'A few stops around this window, about a minute. It only shows where things are; nothing is changed. You can take it later from Setup or Settings > Studio.'),
    actions: [{ text: 'Not now', value: false }, { text: 'Take the tour', value: true, kind: 'primary', focus: true }] });
  setPref('tour_seen', true);
  if (v === true) startTour();                                // modal() has already closed and freed #app by now
}

async function boot() {
  const [cfgR, optR, prefR] = await Promise.allSettled([call('get_config'), call('get_options'), call('get_prefs')]);
  const pv = prefR.status === 'fulfilled' && prefR.value ? prefR.value : {};
  applyTheme(pv.theme_effective, pv.theme_base, pv.theme_tokens);   // before any screen, the recovery one too
  if (cfgR.status === 'rejected') { recovery(cfgR.reason instanceof Error ? cfgR.reason : new Error(String(cfgR.reason))); return; }
  const cfgRes = cfgR.value;
  if (cfgRes && cfgRes.too_new) { recovery(Object.assign({}, cfgRes, { config: null })); return; }
  if (!cfgRes || !cfgRes.config || typeof cfgRes.config !== 'object' || Array.isArray(cfgRes.config)) { recovery(cfgRes || new Error('Studio got no menus file from the app.')); return; }
  const opts = optR.status === 'fulfilled' ? optR.value : null;     // a failed get_options just means the FALLBACK_* lists are used
  if (prefR.status === 'fulfilled' && prefR.value) S.prefs = Object.assign(S.prefs, prefR.value);
  const badMenus = adoptConfig(cfgRes);
  if (badMenus) { recovery(Object.assign({}, cfgRes, { config: null, error: badMenus + ' Studio cannot show a file like that.' })); return; }
  S.opts = opts; S.defaults = Object.assign({}, FALLBACK_DEFAULTS, cfgRes.defaults || (opts && opts.ring_defaults) || {});
  S.defaults.colors = Object.assign({}, FALLBACK_DEFAULTS.colors, S.defaults.colors || {});
  applyTheme(S.prefs.theme_effective, S.prefs.theme_base, S.prefs.theme_tokens);   // again, now that the options with each theme's colours are in
  if (prefR.status === 'fulfilled' && prefR.value && S.prefs.mode !== 'simple' && S.prefs.mode !== 'full') {   // first start with this build: new installs get Simple, a config that needs Full gets Full
    S.prefs.mode = S.prefs.setup_done === false ? 'simple' : (needsFull(S.cfg) ? 'full' : 'simple');
    call('set_pref', 'mode', S.prefs.mode).catch(() => {});
  }
  const ids = Object.keys(S.cfg.menus);
  const wantMenu = params.get('menu');                                  // the ids are taken from the config, never from the URL
  S.menuId = ids.find(id => id === wantMenu) || ids.find(id => S.cfg.menus[id].hotkey) || ids[0] || null;
  const m0 = curMenu();
  if (params.has('item') && m0 && m0.items[+params.get('item')]) { S.itemIdx = +params.get('item'); S.tab = 'item'; }
  else S.tab = params.get('tab') || 'menu';
  if (params.get('q')) S.lib.q = params.get('q');
  if (params.get('cat')) S.lib.cat = params.get('cat');
  S.lib.kind = LIB_KINDS.find(k => k === params.get('kind')) || S.lib.kind;
  if (params.get('dock')) S.dock.cat = params.get('dock');
  renderProfile();
  updateDirty(); renderProblems();
  applyPrefs();
  loadLibrary(); loadSuggestions(); loadTags();
  showScreen(params.get('screen') || (S.prefs.setup_done === false ? 'setup' : (S.prefs.last_screen || 'menus')));
  S.ready = true;
  rememberSel(); updateHistButtons();
  $('#saveBtn').disabled = false;
  modeBtns().forEach(b => { b.disabled = false; });
  refreshZsBadge();
  if (S.screen !== 'setup') refreshSetupBadge();
  if (S.screen !== 'status') refreshAppDown();
  if (params.has('hover')) { /* debug aid */ }
  document.documentElement.classList.add('ready');
  afterBoot();
}

/* The top bar drops the Ctrl+S hint, then the word Studio, then turns Revert and Save into icons, and last shows
   Unsaved changes as its dot alone, each only when it has no room left without that step. After that the profile
   name shortens. The spacer takes the free space, so a spacer with no width means the bar is full. */
function fitTopbar() {
  const bar = $('.topbar'), gap = $('.topbar > .spacer');
  if (!bar || !gap) return;
  const steps = ['no-kbd', 'no-studio', 'no-label', 'no-dirty-text'];
  bar.classList.remove(...steps);
  for (const c of steps) {
    if (gap.getBoundingClientRect().width >= 1) break;
    bar.classList.add(c);
  }
}
/* Fits the bar again when the window changes size and when what is in it changes (Unsaved changes, the problems
   pill, the profile name, the version). Only the classes on the bar itself change, so this does not feed itself. */
function watchTopbar() {
  const bar = $('.topbar');
  if (!bar) return;
  const fit = () => fitTopbar();
  if (typeof ResizeObserver === 'function') new ResizeObserver(fit).observe(bar);
  new MutationObserver(fit).observe(bar, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['hidden'] });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fit);
  fit();
}

function init() {
  watchSystemTheme();
  watchZbrushTheme();
  if (POPOUT) { initPopout(); return; }
  $('#revertBtn').prepend(icon('revert', 15, 'tb-ico')); $('#saveBtn').prepend(icon('save', 15, 'tb-ico'));   // shown only when the bar is full (fitTopbar)
  watchTopbar();
  $$('.rail-btn').forEach(b => b.addEventListener('click', () => { if (S.ready && !S.fatal) showScreen(b.dataset.screen); }));
  $('#saveBtn').addEventListener('click', () => save());
  $('#revertBtn').addEventListener('click', revert);
  $('#undoBtn').append(icon('undo', 16)); $('#redoBtn').append(icon('redo', 16));
  $('#browserBtn').prepend(icon('k_browser', 13));
  $('#browserBtn').addEventListener('click', openBrowserFromButton);   // works before the config loads: the browser needs none
  $('#profileBtn').addEventListener('click', e => { if ((S.ready || S.fatal) && S.profilesOn) openProfileMenu(e.currentTarget); });
  const modeSeg = $('#modeSeg');                                       // Simple / Full; the popout has no such control
  if (modeSeg) {
    modeBtns().forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));
    modeSeg.addEventListener('keydown', e => {
      if (e.ctrlKey || e.altKey || e.metaKey || e.shiftKey || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) return;
      const btns = modeBtns(), at = btns.indexOf(document.activeElement);
      if (at < 0) return;
      e.preventDefault();
      const to = btns[(at + 1) % btns.length];
      setMode(to.dataset.mode); to.focus();
    });
  }
  $('#undoBtn').addEventListener('click', () => { if (S.ready && !S.fatal) undo(); });
  $('#redoBtn').addEventListener('click', () => { if (S.ready && !S.fatal) redo(); });
  $('#problemsBtn').addEventListener('click', e => {
    S.problemsOpen = !S.problemsOpen; renderProblems();
    if (S.problemsOpen && e.detail === 0) { const first = $('#problemsList .problem.go') || $('#problemsPanel'); if (first) first.focus(); }   // opened with the keyboard: the first entry takes it (Escape gives it back to the pill)
  });
  document.addEventListener('mousedown', e => { if (S.problemsOpen && !e.target.closest('#problemsPanel, #problemsBtn')) closeProblems(false); }, true);
  window.addEventListener('keydown', e => {
    if (e.key !== 'Escape' || !S.problemsOpen || e.defaultPrevented || $('#overlay-root').firstElementChild) return;
    e.preventDefault(); closeProblems(true);
  });
  window.addEventListener('resize', () => { if (S.problemsOpen) placeProblemsPanel(); });
  window.addEventListener('keydown', e => {
    const ours = ((e.ctrlKey || e.metaKey) && !e.altKey && /^[szy]$/i.test(e.key)) || (e.altKey && !e.ctrlKey && !e.shiftKey && screenKey(e) !== null);
    if ($('#overlay-root').firstElementChild) { if (ours) e.preventDefault(); return; }   // a dialog is open: our shortcuts stay quiet, and the web view must not get Ctrl+S either
    // a text box keeps its own undo; a slider, switch, select or colour swatch does not, so Ctrl+Z there undoes the config
    const edEl = e.target && e.target.closest && e.target.closest('input, textarea, [contenteditable]');
    const ed = !!edEl && (edEl.matches('textarea, [contenteditable]:not([contenteditable="false"])') || !edEl.type || /^(text|search|number|url|email|password|tel)$/i.test(edEl.type));
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 's') { e.preventDefault(); if (S.ready && !S.fatal) save(); }
    else if (!S.ready || S.fatal) return;
    else if ((e.ctrlKey || e.metaKey) && !e.altKey && !ed && e.key.toLowerCase() === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
    else if ((e.ctrlKey || e.metaKey) && !e.altKey && !ed && e.key.toLowerCase() === 'y') { e.preventDefault(); redo(); }
    else if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && !ed && e.key.toLowerCase() === 'd') {     // Ctrl+D stars the card in focus (or the selection it is in)
      const card = e.target && e.target.closest && e.target.closest('.bcard[data-name]');
      const b = card && Array.from(browsers.values()).find(x => x.el.contains(card));
      if (b) { e.preventDefault(); b.toggleFav(card.dataset.name); }
    }
    else if (e.altKey && !e.ctrlKey && !e.shiftKey && screenKey(e) !== null) { e.preventDefault(); showScreen(SCREEN_ORDER[screenKey(e)]); }
  });
  installMouseNav(navStudio);
  window.addEventListener('focus', debounce(() => { if (S.ready && !S.fatal) { loadTags(); reloadUsage(); } }, 300));      // tags.json may have changed (the popout, a hand edit), and picks add to Recent
  window.addEventListener('focus', debounce(checkProfile, 300));                                                                   // the app's profile may have changed (the tray), or this one may be gone
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
/* The popout is one long-lived process, so a brush saved in ZBrush after it started is not in its list. Whenever the window is shown, or a tab is
   opened, the library of that kind is read again if the last read is more than a minute old. popScanned: kind -> when (R.libRefresh stamps it). */
const popScanned = Object.create(null), POP_RESCAN_MS = 60000;
function popRescanIfOld(kind) {
  const L = lib(kind);
  if (L.loaded && !L.busy && Date.now() - (popScanned[kind] || 0) > POP_RESCAN_MS) loadLibrary(kind, true);
}
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
    // ok means the app took the pick and passed it on; whether ZBrush then selected it is in its log, so the toast says "sent"
    if (r && r.ok) toast('Sent ' + name + ' to ZBrush', { tone: 'ok', ms: 1400 });
    else toast((r && r.error) || 'ZOrbit is not running. It starts and stops with ZBrush. Start ZBrush, or press Start app on Studio’s Status screen.', { tone: 'warn', ms: 3800 });
  },
  primaryMany(names, kind) { const w = K(kind).one; toast(`ZBrush takes one ${w} at a time. Select a single ${w}.`, { tone: 'warn', ms: 2600 }); },
  cardTitle: () => 'Select in ZBrush',
  cardLabel: (name, kind) => 'Select ' + name + ' in ZBrush',
  enterHint: 'Press Enter to select it in ZBrush.',
  hint: () => [],                                          // the popout shows no hint line
  badge: null,                                       // no "In my menus" folder, no badges: the popout knows nothing of menus
  onKind: kind => { if (popTabs) popTabs.paint(); call('popout_set_kind', kind).catch(() => {}); popRescanIfOld(kind); },   // the header tabs follow every switch
  onSize: debounce(px => { call('popout_set_size', px).catch(() => {}); }, 400),
};

/* The browser's mark (assets/browser.ico): a dark disc with a 2x2 grid of outlined tiles, three in the accent and the last in cyan. */
function popLogo() {
  const tile = (x, y, c) => `<rect x="${x}" y="${y}" width="4.5" height="4.5" rx=".8" fill="var(--bg1)" stroke="var(${c})" stroke-width="1"/>`;
  const s = h('span', { class: 'pop-logo', 'aria-hidden': 'true' });
  s.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18"><circle cx="12" cy="12" r="10.85" fill="var(--bg1)" stroke="color-mix(in srgb, var(--ink) 16%, transparent)" stroke-width=".32"/>'
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
  const toStrip = h('button', { class: 'ibtn strip-btn', type: 'button', title: 'Show as a strip', 'aria-label': 'Show as a strip',
    onclick: () => { call('popout_strip_show').catch(() => toast('Could not show the strip.', { tone: 'warn' })); } }, icon('strip', 15));
  const head = h('header', { class: 'pop-head' },
    popLogo(), (popTabs = kindTabs(() => S.pop.kind, k => popBrowser.setKind(k), 'pop')).el,
    h('div', { class: 'spacer' }), side, col, toStrip, pin,
    h('div', { class: 'winctl' }, h('button', { class: 'winbtn close', type: 'button', title: 'Close', 'aria-label': 'Close', onclick: popHide }, icon('x', 14))));
  popBrowser = makeBrowser({ compact: false, st: S.pop, host: POP_HOST, kindUi: 'none' });   // the tabs live in the header
  root.replaceChildren(head, h('div', { class: 'pop-body' }, popBrowser.el));
  R.libRefresh = kind => {
    popScanned[kind] = Date.now();
    if (popStrip && kind === S.strip.kind) popStrip.paint();
    if (kind !== S.pop.kind) return;
    const had = popBrowser.hasSel();                  // a rescan keeps the highlight and the scroll position; the first list highlights its first item
    popBrowser.refresh();
    if (!had) popBrowser.highlightFirst();
  };
}

/* Called by popout.py each time the window is shown. Starts from a clean slate: no search, no folder, the given tag only, the first match
   highlighted. A tag the page has not heard of (made in the Studio a moment ago) is looked for once more with a forced reload. */
window.__popoutShow = o => {
  if (o && o.mode === 'strip') return showStrip(o);
  const tag = (o && o.tag) || null, kind = o && isLib(o.kind) ? o.kind : null, reset = !o || o.reset !== false;
  if (!popBrowser) { popWant = { tag, kind, reset }; return false; }
  setPopMode('browser');
  if (kind) popBrowser.setKind(kind);
  if (reset || tag) popBrowser.setFilter(tag);          // a tab switch alone keeps the search and tag filter
  popBrowser.focusSearch();
  popRescanIfOld(popBrowser.kind());                    // a brush saved in ZBrush since the last read
  reloadUsage();                                        // picks made since the window was last shown
  const stale = !!tag && !S.tagMap.has(tag);
  loadTags(stale).then(() => { if (stale && S.tagMap.has(tag)) popBrowser.setFilter(tag); });
  return true;
};
window.__popoutFocus = () => { if (popBrowser) popBrowser.focusSearch(false); return document.hasFocus(); };

/* ---------- the strip (popout.py, popout.json "strip"): one tab's favourites in your order, in a small window that stays on top and never
   takes the keyboard. A click picks at once. The window is the size of .strip: the page measures it and popout.py fits the window (fitNow,
   popout_strip_size). A window cannot show a menu outside itself, so the menu takes the strip's place while it is open. S.strip: kind, orient
   wrap and fold (folded here) come from popout.json through __popoutShow; the last pick (the accent rim) is the page's own. No keys are handled here. */
S.strip = { kind: 'brush', orient: 'vertical', wrap: false, folded: false, last: '' };
let popStrip = null;
const STRIP_CELL = 48, STRIP_GAP = 4, STRIP_LINE = 10;          // px, and how many favourites one line holds before the +N button

function setPopMode(mode) {
  if ((S.popMode || 'browser') === mode) return;
  S.popMode = mode;
  document.body.classList.toggle('strip-mode', mode === 'strip');
  if (mode === 'strip') {                                        // nothing of the browser stays open over the strip
    if (openPopover) openPopover();
    if (activeModal) activeModal.close(undefined);
    if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
  } else if (popStrip) popStrip.closeMenu(false);
}

/* __popoutShow({mode: 'strip', kind, orient, wrap, fold}): draws the strip and answers its size, which popout.py gives the window before it shows. */
function showStrip(o) {
  if (isLib(o.kind)) S.strip.kind = o.kind;
  S.strip.orient = o.orient === 'horizontal' ? 'horizontal' : 'vertical';
  S.strip.wrap = !!o.wrap;
  S.strip.folded = !!o.fold;
  if (!popStrip) { popWant = o; return null; }                   // still booting: it sends its size once it is drawn
  setPopMode('strip');
  popStrip.closeMenu(false);
  ensureLib(S.strip.kind); popRescanIfOld(S.strip.kind); loadUsage(S.strip.kind); loadTags();
  popStrip.paint();
  return popStrip.fitNow();
}

function buildStrip() {
  const st = S.strip;
  const cells = h('div', { class: 'strip-cells' });
  const label = h('span', { class: 'strip-kind' });
  const menuBtn = h('button', { class: 'strip-menu', type: 'button', 'aria-haspopup': 'menu', 'aria-expanded': 'false', onclick: () => (menu ? closeMenu() : openMenu()) },
    icon('star', 16), label);
  const more = h('button', { class: 'strip-more', type: 'button', onclick: () => set({ wrap: !st.wrap }) });
  const openBtn = iconBtn('k_browser', 'Open the browser', () => { call('popout_open_browser', false).catch(() => {}); }, 'strip-open');
  const fold = iconBtn('chev_u', 'Fold the strip', () => {
    st.folded = !st.folded; paint();
    call('popout_strip_set', { fold: st.folded }).catch(() => {});     // remembered: the strip comes back folded
  }, 'strip-fold');
  const root = h('div', { class: 'strip', role: 'toolbar', 'aria-label': 'Favourites strip' },
    h('div', { class: 'strip-grip', title: 'Drag to move the strip' }, icon('grip', 14)),
    menuBtn, h('div', { class: 'strip-sep' }), cells, more, h('div', { class: 'strip-sep after' }), openBtn, fold);
  document.body.append(root);

  /* The tab's favourites as the browser's Favourites folder lists them: your order, else most used first. null while the library loads. */
  function items() {
    const L = lib(st.kind);
    if (L.state !== 'ready') return null;
    const u = usageOf(st.kind);
    return ZFavOrder.sorted(L.sorted.filter(b => isFav(st.kind, b.name)), favOrderOf(st.kind), b => nameKey(b.name), b => u.scores[b.name.toLowerCase()] || 0);
  }
  /* Up to STRIP_LINE a line, fewer when the screen is too short (or narrow) for them and the buttons. */
  const perLine = () => clamp(Math.floor(((st.orient === 'horizontal' ? screen.availWidth : screen.availHeight) - 260 + STRIP_GAP) / (STRIP_CELL + STRIP_GAP)), 3, STRIP_LINE);
  const favCount = k => (lib(k).state === 'ready' ? lib(k).sorted.filter(b => isFav(k, b.name)).length
    : Object.keys(S.itemTags).filter(x => x.startsWith(k + ':') && tagsOf(k, x.slice(k.length + 1)).includes(FAV)).length);

  let built = '';
  function paint() {
    const list = items(), per = perLine(), k = st.kind, n = list ? list.length : 0, many = n > per;
    const shown = list ? (st.wrap || !many ? list : list.slice(0, per)) : null;
    root.classList.toggle('horiz', st.orient === 'horizontal');
    root.classList.toggle('folded', st.folded);
    setText(label, KINDS[k].tab);
    const menuText = `Favourite ${K(k).many}: the strip's menu`;
    menuBtn.title = menuText; menuBtn.setAttribute('aria-label', menuText);
    const foldText = st.folded ? 'Unfold the strip' : 'Fold the strip';
    fold.title = foldText; fold.setAttribute('aria-label', foldText);
    cells.style.setProperty('--per', per);
    cells.classList.toggle('short', !shown || shown.length <= per);
    more.hidden = !many;
    setText(more, st.wrap ? 'Less' : '+' + (n - per));
    more.title = st.wrap ? `Show the first ${per} only` : `Show all ${n} favourite ${K(k).many}`;
    const sig = k + '|' + (shown ? shown.map(b => b.name).join('\n') : '?');
    if (sig !== built) {                                         // the same names keep their thumbnails
      built = sig;
      cells.replaceChildren(...(!shown ? [0, 1, 2].map(() => h('div', { class: 'strip-cell skel' }, h('span', { class: 'thumb loading' })))
        : shown.length ? shown.map(cell) : [h('button', { class: 'strip-empty', type: 'button', title: `No favourite ${K(k).many} yet. Click to open the browser and star some.`,
          'aria-label': `No favourite ${K(k).many} yet. Open the browser`, onclick: () => { call('popout_open_browser', true).catch(() => {}); } }, icon('star', 16))]));
    }
    for (const c of $$('.strip-cell[data-name]', cells)) paintCell(c);
    fitSoon();
  }
  /* The tag band (the first tag other than Favourites, as on the browser's cards) and the rim of the last pick. */
  function paintCell(c) {
    const name = c.dataset.name, t = firstTag(st.kind, name);
    c.classList.toggle('tagged', !!t);
    if (t) c.style.setProperty('--tag', t.color); else c.style.removeProperty('--tag');
    c.classList.toggle('last', st.last === tagKey(st.kind, name));
  }
  function cell(b) {
    const c = h('button', { class: 'strip-cell', type: 'button', draggable: 'true', dataset: { name: b.name }, 'aria-label': 'Select ' + b.name + ' in ZBrush',
      onclick: () => pick(b.name) }, thumb(b.name, { size: STRIP_CELL, res: 128, kind: st.kind }));     // 128: the browser's own pictures, cached already
    c.addEventListener('dragstart', e => {                       // the browser's native drag: to a new place here, or onto Studio
      const dt = e.dataTransfer;
      if (!dt) return;
      dt.effectAllowed = 'copy';
      dt.setData(ITEM_MIME, JSON.stringify({ kind: st.kind, name: b.name }));
      dt.setData('text/plain', ITEM_TEXT + st.kind + ':' + b.name);
      drag = { name: b.name }; c.classList.add('reordering'); hover(null);
    });
    c.addEventListener('dragend', endDrag);
    return c;
  }

  async function pick(name) {
    if (popPicking) return;
    popPicking = true;
    const kind = st.kind;
    let r;
    try { r = await call('popout_pick', name, kind); } catch (e) { r = { ok: false, error: 'Could not reach ZOrbit: ' + ((e && e.message) || e) }; }
    popPicking = false;
    if (r && r.ok) { st.last = tagKey(kind, name); for (const c of $$('.strip-cell[data-name]', cells)) paintCell(c); }
    else toast((r && r.error) || 'ZOrbit is not running. It starts and stops with ZBrush. Start ZBrush, or press Start app on Studio’s Status screen.', { tone: 'warn' });
  }

  /* The name of the thumbnail under the mouse, in a pill outside the window (popout.py draws it), beside the strip's edge. */
  let hoverSeq = 0, hoverOn = '';
  function hover(name, el) {
    if (name && (menu || drag)) return;
    if (!name && !hoverOn) return;
    hoverOn = name || '';
    let rect = null;
    if (name) {
      const c = el.getBoundingClientRect(), s = root.getBoundingClientRect();
      rect = st.orient === 'horizontal' ? [c.left, s.top, c.right, s.bottom] : [s.left, c.top, s.right, c.bottom];
    }
    call('popout_strip_hover', ++hoverSeq, name || null, rect, st.orient === 'horizontal' ? 'below' : 'right').catch(() => {});
  }
  root.addEventListener('mouseover', e => {
    const c = e.target.closest && e.target.closest('.strip-cell[data-name]');
    if (c) { if (c.dataset.name !== hoverOn) hover(c.dataset.name, c); } else hover(null);
  });
  root.addEventListener('mouseleave', () => hover(null));

  /* Your order, as in the browser's Favourites: drag a thumbnail to a gap. ZFavOrder.gapAt reads lines that run across, so a vertical strip's
     rectangles are given to it turned on their side, and its answer turned back. */
  let drag = null;
  const mark = h('div', { class: 'strip-drop', 'aria-hidden': 'true' });
  function gapAt(x, y) {
    const vert = st.orient !== 'horizontal';
    const turn = r => (vert ? { left: r.top, top: r.left, right: r.bottom, bottom: r.right } : r);
    const g = ZFavOrder.gapAt($$('.strip-cell[data-name]', cells).map(c => turn(c.getBoundingClientRect())), vert ? y : x, vert ? x : y, STRIP_GAP);
    return g && (vert ? { index: g.index, y: g.x, left: g.top, right: g.bottom } : { index: g.index, x: g.x, top: g.top, bottom: g.bottom });
  }
  function paintMark(x, y) {
    const g = gapAt(x, y), box = cells.getBoundingClientRect();
    if (!g) { mark.remove(); return; }
    if (g.y !== undefined) Object.assign(mark.style, { left: (g.left - box.left) + 'px', top: (g.y - box.top - 1) + 'px', width: (g.right - g.left) + 'px', height: '2px' });
    else Object.assign(mark.style, { left: (g.x - box.left - 1) + 'px', top: (g.top - box.top) + 'px', width: '2px', height: (g.bottom - g.top) + 'px' });
    if (mark.parentNode !== cells) cells.append(mark);
  }
  function endDrag() { drag = null; mark.remove(); $$('.strip-cell.reordering', cells).forEach(c => c.classList.remove('reordering')); }
  cells.addEventListener('dragover', e => {
    if (!drag || !e.dataTransfer) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';                          // what the thumbnail allows, so the same drag can land in Studio
    paintMark(e.clientX, e.clientY);
  });
  cells.addEventListener('dragleave', e => { if (drag && !cells.contains(e.relatedTarget)) mark.remove(); });
  cells.addEventListener('drop', e => {
    if (!drag) return;
    e.preventDefault();
    const name = drag.name, g = gapAt(e.clientX, e.clientY), list = items();
    endDrag();
    const next = g && list ? ZFavOrder.moved(list.map(b => nameKey(b.name)), nameKey(name), g.index) : null;
    if (next) tagCall('set_favourite_order', st.kind, next);   // its answer repaints the strip and every browser (tagsChanged)
  });

  /* The menu: the tabs with their favourite counts, the orientation, Open browser and Hide strip. It takes the strip's place under the grip and
     the menu button (which closes it again), and the window takes its size. It closes on a choice, or a moment after the mouse leaves the window
     (a click in ZBrush never reaches this page). */
  let menu = null, menuTimer = 0;
  function openMenu() {
    if (menu) return;
    hover(null);
    const row = (label, fn, o = {}) => h('button', { class: 'pop-item' + (o.on ? ' on' : ''), type: 'button', role: o.radio ? 'menuitemradio' : 'menuitem',
      'aria-checked': o.radio ? String(!!o.on) : null, onclick: () => { closeMenu(false); fn(); } },
    o.radio ? h('span', { class: 'pop-tick' }, o.on ? icon('check', 14) : null) : icon(o.icon, 15),
    h('span', { class: 'pop-text' }, h('b', null, label)), o.count === undefined ? null : h('span', { class: 'pi-count' }, String(o.count)));
    menu = h('div', { class: 'strip-pop', role: 'menu', 'aria-label': 'Strip' },
      LIB_KINDS.map(k => row(KINDS[k].tab, () => set({ kind: k }), { on: k === st.kind, count: favCount(k), icon: KIND[k].icon })),
      h('div', { class: 'pop-sep', role: 'separator' }),
      row('Vertical', () => set({ orient: 'vertical' }), { radio: true, on: st.orient !== 'horizontal' }),
      row('Horizontal', () => set({ orient: 'horizontal' }), { radio: true, on: st.orient === 'horizontal' }),
      h('div', { class: 'pop-sep', role: 'separator' }),
      row('Open browser', () => { call('popout_open_browser', false).catch(() => {}); paint(); }, { icon: 'k_browser' }),
      row('Hide strip', () => { call('popout_strip_hide').catch(() => {}); paint(); }, { icon: 'x' }));
    menuBtn.after(menu);
    root.classList.add('menu-open');
    menuBtn.setAttribute('aria-expanded', 'true');
    fitSoon();
  }
  function closeMenu(refit = true) {
    clearTimeout(menuTimer);
    if (!menu) return;
    menu.remove(); menu = null;
    root.classList.remove('menu-open');
    menuBtn.setAttribute('aria-expanded', 'false');
    if (refit) fitSoon();
  }
  document.documentElement.addEventListener('mouseleave', () => { clearTimeout(menuTimer); if (menu) menuTimer = setTimeout(() => closeMenu(), 700); });
  document.documentElement.addEventListener('mouseenter', () => clearTimeout(menuTimer));

  /* orient, kind or wrap: drawn at once, saved, and the window fitted again. */
  async function set(changes) {
    Object.assign(st, changes);
    if (changes.kind) { built = ''; ensureLib(st.kind); popRescanIfOld(st.kind); loadUsage(st.kind); }
    paint();
    try { await call('popout_strip_set', changes); } catch (e) { toast('Could not save the strip.', { tone: 'warn' }); }
  }

  /* The window's size: .strip's own. Sent only when it changed. */
  let lastFit = '';
  const measure = () => { const r = root.getBoundingClientRect(); return { w: Math.ceil(r.width), h: Math.ceil(r.height) }; };
  function sendFit(f) {
    const key = JSON.stringify(f);
    if (key === lastFit || S.popMode !== 'strip') return;
    lastFit = key;
    call('popout_strip_size', f.w, f.h).catch(() => {});
  }
  const fitSoon = debounce(() => { if (S.popMode === 'strip') sendFit(measure()); }, 16);
  function fitNow() { fitSoon.cancel(); const f = measure(); lastFit = JSON.stringify(f); return f; }   // popout.py sizes the window with the answer

  const api = { el: root, kind: () => st.kind, paint, fitNow, closeMenu, updateTags: paint, updateUsage: paint, resend: () => { lastFit = ''; fitSoon(); } };
  browsers.set(st, api);                                         // tag and usage changes repaint it as they do the browser
  return api;
}

async function bootPopout() {
  S.cfg = { menus: {} };                             // the popout has no menus; the tag manager asks get_tag_uses for the ring items that use a tag
  let state = null;
  try { state = await call('popout_get_state'); } catch (e) { state = null; }
  applyTheme(state && state.theme_effective, state && state.theme_base, state && state.theme_tokens);
  if (state) {
    if (THEMES.includes(state.theme)) S.prefs.theme = state.theme;
    S.prefs.theme_effective = S.themeEff;
    S.popOnTop = state.on_top !== false;
    if (+state.size >= 84) S.pop.size = clamp(+state.size, 84, 220);
    S.popSide = state.side === 'right' ? 'right' : 'left';
    S.popColumn = state.column !== false;
    if (state.profile) S.profile = String(state.profile);
    if (state.tag === FAV) S.pop.cat = '@fav';           // Favourites is a folder, not a chip
    else if (state.tag) S.pop.tags = new Set([String(state.tag)]);
    if (isLib(state.kind)) S.pop.kind = state.kind;
    const sp = state.strip || {};
    if (isLib(sp.kind)) S.strip.kind = sp.kind;
    S.strip.orient = sp.orient === 'horizontal' ? 'horizontal' : 'vertical';
    S.strip.wrap = !!sp.wrap;
    S.strip.folded = !!sp.fold;
  }
  buildPopout($('#app'));                            // makeBrowser loads the library of the starting tab
  popStrip = buildStrip();                           // drawn when __popoutShow asks for the strip
  const tags = loadTags();
  if (state && state.strip && state.strip.on) {      // the strip comes up by itself: measured with its favourites in, not as an empty frame
    const k = S.strip.kind, t0 = Date.now();           // 4 s at most: a library that never loads must not keep this polling, nor the strip waiting
    const libDone = (async () => { ensureLib(k); while ((lib(k).busy || !lib(k).loaded) && Date.now() - t0 < 4000) await sleep(50); })();
    await Promise.race([Promise.all([tags, loadUsage(k), libDone]), sleep(4000)]);
  }
  S.ready = true;
  document.documentElement.classList.add('ready');
  if (popWant) {
    const w = popWant; popWant = undefined;
    window.__popoutShow(w);
    if (w.mode === 'strip') popStrip.resend();      // the window went up at a guessed size
  }
  window.__popoutBooted = true;                      // popout.py waits for this before it puts the strip up at a start
}

/* A pen stroke that reaches the page as a mouse scrolls the grid, as a pen's stroke does once the window is in front. While a Wintab
   program (ZBrush) has the foreground, the Wacom driver moves the cursor as a mouse, so the press that brings this window to the front
   arrives as a mouse and would pick up the card under it. The page cannot tell that from a mouse: popout.py reads the raw input and says
   whether a pen moved the cursor last (__popoutPen). Only that press, the one that brought the window to the front: from then on the
   pen arrives as a pen and scrolls by itself, and a mouse press always drags. A tap still picks. */
const PEN_PAN = { SLOP: 4, FOCUS_MS: 400 };           // px before a press becomes a scroll; how soon after the window took the focus its press counts
function installPenPan() {
  let penLast = false, focusAt = -1e9, pan = null;
  window.__popoutPen = on => { penLast = !!on; return true; };
  window.addEventListener('focus', e => { if (e.target === window) focusAt = performance.now(); });
  window.addEventListener('pointerdown', e => {
    pan = null;
    if (e.pointerType !== 'mouse' || e.button !== 0 || !penLast) return;
    if (document.hasFocus() && performance.now() - focusAt > PEN_PAN.FOCUS_MS) return;    // the window was in front already
    const sc = e.target && e.target.closest && e.target.closest('.b-scroll');
    if (sc) pan = { id: e.pointerId, sc, x: e.clientX, y: e.clientY, top: sc.scrollTop, moved: false };
  }, true);
  // Before anything else sees it (window, capture): the card's own drag and the scroll bar's look at dragstart.
  window.addEventListener('dragstart', e => { if (pan) { e.preventDefault(); e.stopPropagation(); } }, true);
  window.addEventListener('pointermove', e => {
    if (!pan || e.pointerId !== pan.id) return;
    if (!(e.buttons & 1)) { pan = null; return; }
    const dy = e.clientY - pan.y;
    if (!pan.moved) {
      if (Math.abs(dy) < PEN_PAN.SLOP && Math.abs(e.clientX - pan.x) < PEN_PAN.SLOP) return;
      pan.moved = true;
      try { pan.sc.setPointerCapture(e.pointerId); } catch (err) { /* the pointer is gone: the moves stop by themselves */ }
    }
    pan.sc.scrollTop = pan.top - dy;                  // the list follows the pen, as a pen's own scroll does
  }, true);
  const end = e => {
    if (!pan || e.pointerId !== pan.id) return;
    const moved = pan.moved;
    pan = null;
    if (!moved) return;                               // a tap: its click picks, as always
    const eat = ev => { ev.stopPropagation(); ev.preventDefault(); };
    window.addEventListener('click', eat, { capture: true, once: true });
    setTimeout(() => window.removeEventListener('click', eat, { capture: true }), 0);
  };
  window.addEventListener('pointerup', end, true);
  window.addEventListener('pointercancel', end, true);
}

function initPopout() {
  const inStrip = () => S.popMode === 'strip';                               // the strip never has the keyboard: none of this runs there
  installMouseNav(d => { if (popBrowser && !inStrip()) popBrowser.navStep(d); });
  window.addEventListener('keydown', e => {
    if (!popBrowser || e.isComposing || inStrip()) return;
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
    // A field the keys belong to. The size slider is not one for Enter and letters (they go to the search box); its own arrows still move it.
    const t = e.target, field = t && t.closest && t.closest('input, textarea, select, [contenteditable]'), inSearch = popBrowser.inSearch(t);
    const typing = !!field && !(field.matches && field.matches('input[type="range"]'));
    if (e.key.startsWith('Arrow')) {
      if (field && !inSearch) return;
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
  /* After a mouse click on a control (a tag chip, a folder, a tab, Rescan, the pin), the keyboard goes back to the search box, so Enter picks
     the highlighted card and letters search instead of the control toggling again. Only for a pointer click (detail > 0): a keyboard user who
     tabbed to a control and pressed Enter or Space (detail 0) keeps their focus. Capture phase, before the control's own handler, so the
     chips' and folders' habit of putting the focus back on themselves after a repaint finds it already on the search box. */
  document.addEventListener('click', e => {
    const t = e.target;
    if (!popBrowser || inStrip() || !(e.detail > 0) || !t || !t.closest) return;
    if (!t.closest('button, a, [role="option"], [role="tab"]')) return;       // a click on the card itself keeps its focus: Ctrl+D, Space and Enter work on it
    if (t.closest('input, textarea, select, [contenteditable], #overlay-root, .popover, #toasts')) return;
    popBrowser.focusSearch(false);
  }, true);
  window.addEventListener('contextmenu', e => {                              // the web view's own menu is a window of another
    if (inStrip() || !(e.target && e.target.closest && e.target.closest('.bcard'))) e.preventDefault();   // process and would read as leaving
  });
  installPenPan();
  window.addEventListener('focus', debounce(() => { if (S.ready) { loadTags(); reloadUsage(); } }, 300));      // tags.json may have changed (the Studio), and picks add to Recent
  // The window stays on top beside the Studio, so it may never get focus while a tag changes there. get_tags answers "unchanged" from a
  // file time check, so asking every 5 s costs next to nothing; a hidden window does not ask.
  setInterval(() => { if (S.ready && !document.hidden) loadTags(); }, 5000);
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
// Here and not in init(), which waits for the API: the window can take focus before that. The link comes before this script.
if ($('#skipLink')) ZSkipLink.guard($('#skipLink'), $('#screens'), document);
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => whenReady(init)); else whenReady(init);
})();
