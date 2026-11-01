/* ZOrbit look resolver for Studio. Pure: no DOM, no globals of app.js, so Node can load it too.

   The Look screen edits "look keys" (radius, slot, hub, colours and so on). Today they live in cfg.ring and there is one level,
   Global. The API already takes a target, { level: 'global' }, and a ctx (the defaults to compare with), so that later phases
   add menu and slot levels, presets and more keys here without the screen having to change shape.

   resolve(cfg, target, ctx) -> { key: { value, origin } } for every key in KEYS. origin is where the value comes from:
     default   nothing was set; the built-in value
     theme     a colour of the light or Match ZBrush theme (colours only, and only while the user has set none)
     global    set in cfg.ring (a value that equals the default is not "set", see set())
   Colours are one key, 'colors', with one origin per colour in .sub[name] = { value, origin }; the key's own origin is
   'global' when any colour is set, else the common origin of the five.

   ctx = { defaults, theme }. defaults is what an unset key shows, colours included: Studio passes S.defaults, whose colours
   already are the theme's. theme is 'dark', 'light' or 'zbrush'; anything but 'dark' makes an unset colour a theme colour.

   set / clear / isSet / changed edit the cfg passed in and keep today's rule: a value equal to the default is dropped (as
   ringSet and putRing in app.js do), so the file says nothing about it. They do not commit, tidy an empty ring object or
   redraw; the caller does. A key is 'radius', or 'colors.bg' for one colour. */
(function (root) {
  'use strict';

  const COLOUR_KEYS = ['bg', 'accent', 'highlight', 'text', 'lines'];

  /* The groups the Look screen shows, in order. full: only in Full mode. */
  const GROUPS = [
    { id: 'slots', title: 'Slots' },
    { id: 'hub', title: 'Hub', full: true },
    { id: 'labels', title: 'Labels' },
    { id: 'colours', title: 'Colours', full: true },
    { id: 'tags', title: 'Tag colours', full: true },
  ];

  /* Every look key this phase knows. A key listed here is valid at the levels named. */
  const KEYS = {
    radius: { group: 'slots', levels: ['global'] },
    slot: { group: 'slots', levels: ['global'] },
    dead_zone: { group: 'slots', levels: ['global'] },
    slot_shape: { group: 'slots', levels: ['global'] },
    hub: { group: 'hub', levels: ['global'], full: true },
    labels: { group: 'labels', levels: ['global'] },
    colors: { group: 'colours', levels: ['global'], full: true, subs: COLOUR_KEYS },
    tag_colors: { group: 'tags', levels: ['global'], full: true },
    tag_band: { group: 'tags', levels: ['global'], full: true },
    tag_band_opacity: { group: 'tags', levels: ['global'], full: true },
    tag_glow_opacity: { group: 'tags', levels: ['global'], full: true },
    tag_tint_opacity: { group: 'tags', levels: ['global'], full: true },
    tag_tint_style: { group: 'tags', levels: ['global'], full: true },
    tag_tint_blend: { group: 'tags', levels: ['global'], full: true },
  };

  const has = (o, k) => o != null && Object.prototype.hasOwnProperty.call(o, k);
  const isObj = o => o !== null && typeof o === 'object' && !Array.isArray(o);

  /* The object that holds the look keys of a target; null when there is none yet and create is false. Only the global
     level exists for now: other levels throw, so a screen that asks for one fails loudly instead of editing the wrong place. */
  function holder(cfg, target, create) {
    if (!target || target.level !== 'global') throw new Error('look level not supported: ' + (target && target.level));
    if (cfg && isObj(cfg.ring)) return cfg.ring;
    if (!create) return null;
    cfg.ring = {};
    return cfg.ring;
  }

  const split = key => { const i = String(key).indexOf('.'); return i < 0 ? [String(key), null] : [key.slice(0, i), key.slice(i + 1)]; };
  const sameColour = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();
  const defaultsOf = ctx => (ctx && ctx.defaults) || {};
  const colourDefaults = ctx => defaultsOf(ctx).colors || {};
  const baseOrigin = ctx => (ctx && ctx.theme && ctx.theme !== 'dark' ? 'theme' : 'default');

  function check(key) {
    const [k, sub] = split(key);
    if (!has(KEYS, k)) throw new Error('unknown look key: ' + key);
    if (sub !== null && !(KEYS[k].subs || []).includes(sub)) throw new Error('unknown look key: ' + key);
    return [k, sub];
  }

  /* Is v what a plain key would use? A value of the wrong type (a hand-edited file) is ignored, as the ring does. */
  const usable = (v, d) => v !== undefined && (d === undefined || typeof v === typeof d);

  function resolveColour(own, name, ctx) {
    const d = colourDefaults(ctx)[name];
    const v = isObj(own) && typeof own[name] === 'string' ? own[name] : null;
    if (v !== null && !sameColour(v, d)) return { value: v, origin: 'global' };
    return { value: d, origin: baseOrigin(ctx) };
  }

  function resolve(cfg, target, ctx) {
    const own = holder(cfg, target, false) || {};
    const d = defaultsOf(ctx);
    const out = {};
    for (const key of Object.keys(KEYS)) {
      if (key === 'colors') {
        const sub = {}, value = {};
        for (const name of COLOUR_KEYS) { sub[name] = resolveColour(own.colors, name, ctx); value[name] = sub[name].value; }
        const set = COLOUR_KEYS.some(n => sub[n].origin === 'global');
        out.colors = { value, origin: set ? 'global' : baseOrigin(ctx), sub };
      } else {
        const set = has(own, key) && usable(own[key], d[key]) && JSON.stringify(own[key]) !== JSON.stringify(d[key]);
        out[key] = { value: set ? own[key] : d[key], origin: set ? 'global' : 'default' };
      }
    }
    return out;
  }

  /* The origin of one key ('colors.bg' for one colour), without resolving the rest. */
  function originOf(cfg, target, key, ctx) {
    const [k, sub] = check(key);
    const r = resolve(cfg, target, ctx)[k];
    return sub ? r.sub[sub].origin : r.origin;
  }

  const isSet = (cfg, target, key, ctx) => originOf(cfg, target, key, ctx) === 'global';

  /* Writes a value, or drops the key when it equals the default. Returns true when cfg changed. */
  function set(cfg, target, key, value, ctx) {
    const [k, sub] = check(key);
    const before = JSON.stringify(cfg);
    const ring = holder(cfg, target, true);
    if (sub !== null) {
      if (sameColour(value, colourDefaults(ctx)[sub])) {
        if (isObj(ring.colors)) { delete ring.colors[sub]; if (!Object.keys(ring.colors).length) delete ring.colors; }
      } else {
        if (!isObj(ring.colors)) ring.colors = {};
        ring.colors[sub] = value;
      }
    } else if (k === 'colors') {
      throw new Error('set one colour at a time: colors.<name>');
    } else if (JSON.stringify(value) === JSON.stringify(defaultsOf(ctx)[k])) {
      delete ring[k];
    } else {
      ring[k] = value;
    }
    return JSON.stringify(cfg) !== before;
  }

  /* Removes the key (all five colours for 'colors'), whatever it holds. Returns true when cfg changed. */
  function clear(cfg, target, key) {
    const [k, sub] = check(key);
    const ring = holder(cfg, target, false);
    if (!ring) return false;
    if (sub !== null) {
      if (!isObj(ring.colors) || !has(ring.colors, sub)) return false;
      delete ring.colors[sub];
      if (!Object.keys(ring.colors).length) delete ring.colors;
      return true;
    }
    if (!has(ring, k)) return false;
    delete ring[k];
    return true;
  }

  /* The keys (never 'colors.x') that are set at this target, in KEYS order. */
  function changed(cfg, target, ctx) {
    const r = resolve(cfg, target, ctx);
    return Object.keys(KEYS).filter(k => r[k].origin === 'global');
  }

  const groupOf = key => KEYS[split(key)[0]].group;

  const ZLook = { COLOUR_KEYS, GROUPS, KEYS, resolve, originOf, isSet, set, clear, changed, groupOf };
  if (root) root.ZLook = ZLook;
  if (typeof module !== 'undefined') module.exports = ZLook;
})(typeof window !== 'undefined' ? window : null);
