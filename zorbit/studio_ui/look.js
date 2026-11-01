/* ZOrbit look resolver for Studio. Pure: no DOM, no globals of app.js, so Node can load it too (tests/js/look_parity.js does).

   It mirrors zorbit/looks.py (LookSet, check_look, check_presets) and config.py (_check_menu_look), so the Look screen can show
   where each value comes from while a slider is being dragged, and the mock UI works without Python. Python stays the truth:
   tests/test_look_parity.py runs both against tests/fixtures/look_cases.json.

   Layers, lowest first:  default, theme (colours of a theme other than dark), global preset (ring.look), global (the keys of
   cfg.ring), menu preset (menu.look), menu (the keys in menu.look), slot (item.style). Roles (bg, accent, ...) are resolved after
   the merge. Colours merge one by one: the origin of 'colors.accent' is the layer that last set it.

   A target says where the screen is editing:  { level: 'global' }  { level: 'menu', menu: id }  { level: 'menu', menu, slot: n }
   { level: 'preset', name }. The preset level sees only default, theme and the look's own keys.

   ctx = { looks, defaults, colors, theme, animations }: looks is get_options().looks (the schema), defaults the ring defaults,
   colors get_options().theme_ring_colors ({dark, light, ...}), theme the theme in force (dark, light or zbrush), animations the
   animation names. Without looks (an older backend) the schema is FALLBACK_SCHEMA, global level only, and hasPresets() is false.

   Reading:  explain(cfg, target, ctx) -> { values, origins }  (same shape as looks.LookSet.explain)
             resolve(cfg, target, ctx) -> { key: { value, origin, name, eff, sub } } for the keys of that level
             problems(cfg, ctx) -> the loader's messages about looks (the looks object, ring.look, menu looks and look values)
   Editing (they change cfg, never commit, tidy an empty ring object or redraw; the caller does):
             set / clear / isSet / clearAll / usePreset / newPreset / duplicate / rename / remove (delete, optionally baking)
             summary / usersOf / changed. A key is 'radius', or 'colors.bg' for one colour.
   Pin or drop: set() drops a value that equals what the level would inherit from the default or the theme; any other value is
   written, even when a preset gives the same, so a later change to the preset does not move it. Only clear() removes it. */
(function (root) {
  'use strict';

  const ROLES = ['bg', 'accent', 'highlight', 'text', 'lines'];
  const GEOMETRY = ['radius', 'slot', 'dead_zone'];
  const BEHAVIOUR = {
    tap_ms: { kind: 'range', min: 0, max: 1000 }, timeout_s: { kind: 'range', min: 2, max: 120 },
    flick: { kind: 'switch' }, hover_submenus: { kind: 'switch' }, animation: { kind: 'choice' },
  };
  const RING_ONLY = new Set(['tap_ms', 'timeout_s', 'flick', 'hover_submenus', 'animation', 'look']);
  const RANK = { default: 0, theme: 1, 'global-preset': 2, global: 3, 'menu-preset': 4, menu: 5, slot: 6, preset: 7 };
  const GROUP_ID = { Slots: 'slots', Hub: 'hub', Glow: 'glow', Labels: 'labels', Colours: 'colours', 'Tag colours': 'tags', 'When full': 'when_full' };
  const FALLBACK_DARK = { bg: '#222327', accent: '#f86b33', highlight: '#4dc8e9', text: '#f0f0f0', lines: '#f86b33' };

  /* What Studio knows without get_options().looks: the first pass's keys, at the global level. */
  const fb = (group, kind, def, extra) => Object.assign({ group, kind, default: def, full: true, levels: ['global'] }, extra);
  const FALLBACK_SCHEMA = {
    radius: fb('Slots', 'range', 145, { full: false, min: 60, max: 400 }), slot: fb('Slots', 'range', 72, { full: false, min: 32, max: 160 }),
    dead_zone: fb('Slots', 'range', 38, { full: false, min: 10, max: 120 }),
    slot_shape: fb('Slots', 'choice', 'circle', { full: false, choices: ['circle', 'rounded'] }),
    hub: fb('Hub', 'range', 10, { min: 0, max: 40 }),
    labels: fb('Labels', 'choice', 'name', { full: false, choices: ['name', 'none'] }),
    colors: fb('Colours', 'colors', null, { choices: ROLES }),
    tag_colors: fb('Tag colours', 'choice', 'tint', { choices: ['none', 'tint', 'glow', 'both'] }),
    tag_band: fb('Tag colours', 'choice', 'medium', { choices: ['none', 'hairline', 'narrow', 'medium', 'wide'] }),
    tag_band_opacity: fb('Tag colours', 'range', 0.45, { min: 0, max: 1 }), tag_glow_opacity: fb('Tag colours', 'range', 0.4, { min: 0, max: 1 }),
    tag_tint_opacity: fb('Tag colours', 'range', 0.3, { min: 0, max: 1 }),
    tag_tint_style: fb('Tag colours', 'choice', 'gradient', { choices: ['flat', 'gradient'] }),
    tag_tint_blend: fb('Tag colours', 'choice', 'multiply', { choices: ['multiply', 'overlay'] }),
  };

  const has = (o, k) => o != null && Object.prototype.hasOwnProperty.call(o, k);
  const isObj = o => o !== null && typeof o === 'object' && !Array.isArray(o);
  const clone = o => (o === undefined ? undefined : JSON.parse(JSON.stringify(o)));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const sameColour = (a, b) => String(a).toLowerCase() === String(b).toLowerCase();
  const isHex = v => typeof v === 'string' && /^#[0-9a-fA-F]{6}$/.test(v);
  /* Python's repr of a value, close enough for the loader's messages. */
  const pyr = v => (typeof v === 'string' ? "'" + v + "'" : v === true ? 'True' : v === false ? 'False' : v === null ? 'None' : Array.isArray(v) ? '[' + v.map(pyr).join(', ') + ']' : typeof v === 'object' ? JSON.stringify(v) : String(v));
  const split = key => { const i = String(key).indexOf('.'); return i < 0 ? [String(key), null] : [key.slice(0, i), key.slice(i + 1)]; };
  const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');

  /* ---------------------------------------------------------------- the context */
  function prep(ctx) {
    ctx = ctx || {};
    const looks = ctx.looks && ctx.looks.schema ? ctx.looks : null;
    const schema = looks ? looks.schema : FALLBACK_SCHEMA;
    const defaults = ctx.defaults || {};
    const colors = ctx.colors || {};
    const dark = colors.dark || FALLBACK_DARK;
    const theme = ctx.theme || 'dark';
    const themeColors = theme === 'dark' ? null : (colors[theme] || (defaults.colors) || null);
    const at = lv => Object.keys(schema).filter(k => (schema[k].levels || []).includes(lv));
    const lookKeys = at('global');
    const base = {};
    for (const k of Object.keys(defaults)) if (k !== 'colors' && k !== 'look') base[k] = defaults[k];
    for (const k of lookKeys) if (k !== 'colors' && !has(base, k)) base[k] = schema[k].default;
    base.colors = Object.assign({}, dark);
    const builtinList = looks && Array.isArray(looks.builtin) ? looks.builtin : [];
    const builtin = {};
    for (const b of builtinList) builtin[b.id] = b;
    let pattern = null;
    try { pattern = looks && looks.name ? new RegExp(looks.name.pattern, looks.name.flags || 'u') : null; } catch (e) { pattern = null; }
    return { schema, base, dark, theme, themeColors, lookKeys, lookSet: new Set(lookKeys), styleSet: new Set(at('slot')),
      ringSet: new Set(lookKeys.concat(Object.keys(BEHAVIOUR), ['look'])), builtin, builtinList, hasPresets: !!looks && builtinList.length > 0,
      reserved: new Set(looks && looks.reserved ? looks.reserved : []), nameSpec: looks && looks.name ? looks.name : { max: 32 }, pattern,
      animations: ctx.animations || null, at };
  }
  const hasPresets = ctx => prep(ctx).hasPresets;
  const specOf = (p, k) => p.schema[k] || BEHAVIOUR[k] || null;

  /* ---------------------------------------------------------------- reading a look out of the config (looks.check_look and friends) */
  function checkLook(p, raw, errors, prefix, allow) {
    const out = {};
    for (const k of Object.keys(raw)) {
      const v = raw[k];
      if (!allow.has(k)) { errors.push(prefix + k + (RING_ONLY.has(k) ? ': is a ring setting, not part of a look; ignored' : ': unknown setting')); continue; }
      if (k === 'look') continue;
      const s = specOf(p, k);
      if (!s) continue;
      if (s.kind === 'colors') {
        if (!isObj(v)) { errors.push(prefix + 'colors: must be an object like {"accent": "#f86b33"}'); continue; }
        const got = {};
        for (const ck of Object.keys(v)) {
          if (ROLES.includes(ck)) {
            if (isHex(v[ck])) got[ck] = v[ck]; else errors.push(prefix + 'colors.' + ck + ': ' + pyr(v[ck]) + ' is not a #rrggbb colour');
          } else errors.push(prefix + 'colors.' + ck + ': unknown colour');
        }
        if (Object.keys(got).length) out.colors = got;
      } else if (s.kind === 'colour') {
        if ((typeof v === 'string' && ROLES.includes(v)) || isHex(v) || (v === '' && s.allow_empty)) out[k] = v;
        else errors.push(prefix + k + ': ' + pyr(v) + ' is not a #rrggbb colour or a theme colour (' + ROLES.join(', ') + ')');
      } else if (s.kind === 'range') {
        if (typeof v === 'number' && Number.isFinite(v) && v >= s.min && v <= s.max) out[k] = v;
        else errors.push(prefix + k + ': ' + pyr(v) + ' must be a number from ' + s.min + ' to ' + s.max);
      } else if (s.kind === 'switch') {
        if (typeof v === 'boolean') out[k] = v; else errors.push(prefix + k + ': ' + pyr(v) + ' must be true or false');
      } else if (s.kind === 'choice') {
        const choices = s.choices || (k === 'animation' ? p.animations : null);
        if (typeof v === 'string' && (!choices || choices.includes(v))) out[k] = v;
        else errors.push(prefix + k + ': ' + pyr(v) + ' unknown; one of ' + (choices || []).join(', '));
      }
    }
    return out;
  }

  /* '' if name can be the name of a user look, else what is wrong with it (the words looks.valid_name uses). */
  function nameProblemIn(p, name) {
    const max = p.nameSpec.max || 32;
    if (typeof name !== 'string' || (p.pattern ? !p.pattern.test(name) : !/^[\w](?:[\w -]*[\w])?$/.test(name)) || name.length > max) return 'name must be 1 to ' + max + ' letters, digits, spaces, - or _';
    if (has(p.builtin, name.toLowerCase()) || p.reserved.has(name)) return 'that name is a built-in look or is reserved, give it another';
    return '';
  }
  const nameProblem = (name, ctx) => nameProblemIn(prep(ctx), name);

  function checkPresets(p, raw, errors) {
    const out = Object.create(null);
    if (raw === undefined || raw === null) return out;
    if (!isObj(raw)) { errors.push('looks: must be an object like {"My look": {"slot_shape": "hexagon"}}; ignored'); return out; }
    const seen = Object.create(null);
    for (const name of Object.keys(raw)) {
      let v = raw[name];
      const bad = nameProblemIn(p, name);
      if (bad) { errors.push('looks.' + name + ': ' + bad + '; ignored'); continue; }
      const fold = name.toLowerCase();
      if (has(seen, fold)) { errors.push('looks.' + name + ': same name as ' + pyr(seen[fold]) + ' apart from capitals; ignored'); continue; }
      seen[fold] = name;
      if (!isObj(v)) { errors.push('looks.' + name + ': not an object; ignored'); delete seen[fold]; continue; }
      if (has(v, 'preset')) { errors.push('looks.' + name + '.preset: a look cannot be based on another look; ignored'); v = Object.assign({}, v); delete v.preset; }
      out[name] = checkLook(p, v, errors, 'looks.' + name + '.', p.lookSet);
    }
    return out;
  }
  /* The looks of a config: the user's valid ones, the ring's valid keys and the ring's preset ('' when none or unknown). */
  function loadSet(cfg, p, errors) {
    const presets = checkPresets(p, cfg && cfg.looks, errors);
    let ringRaw = {};
    if (cfg && cfg.ring !== undefined && cfg.ring !== null) {
      if (isObj(cfg.ring)) ringRaw = cfg.ring; else errors.push('ring: must be an object like {"radius": 145, "animation": "smooth"}');
    }
    const ring = checkLook(p, ringRaw, errors, 'ring.', p.ringSet);
    let ringLook = '';
    if (ringRaw.look) {
      if (typeof ringRaw.look === 'string' && (has(presets, ringRaw.look) || has(p.builtin, ringRaw.look))) ringLook = ringRaw.look;
      else errors.push('ring.look: ' + pyr(ringRaw.look) + ' unknown; one of ' + Object.keys(p.builtin).concat(Object.keys(presets)).join(', '));
    }
    return { presets, ring, ringLook };
  }
  const presetDict = (set, p, name) => {
    if (typeof name !== 'string' || !name) return null;
    if (has(set.presets, name)) return set.presets[name];
    return has(p.builtin, name) ? (p.builtin[name].look || {}) : null;
  };
  /* config._check_menu_look: { preset: name or '', ...valid keys } */
  function checkMenuLook(p, set, raw, mid, errors) {
    const spec = { preset: '' };
    if (raw === undefined || raw === null) return spec;
    if (typeof raw === 'string') raw = { preset: raw };
    else if (!isObj(raw)) { errors.push('menu ' + mid + ': look must be a look name or an object like {"preset": "soft", "hub": 14}; ignored'); return spec; }
    const name = raw.preset || '';
    if (name) {
      if (typeof name === 'string' && presetDict(set, p, name) !== null) spec.preset = name;
      else errors.push('menu ' + mid + ': look ' + pyr(name) + " unknown; using the ring's look");
    }
    const rest = {};
    for (const k of Object.keys(raw)) if (k !== 'preset') rest[k] = raw[k];
    Object.assign(spec, checkLook(p, rest, errors, 'menu ' + mid + ': look.', p.lookSet));
    return spec;
  }

  /* The loader's messages about looks, in the loader's order: the looks object, the ring's keys and its look, then each menu's look. */
  function problems(cfg, ctx) {
    const p = prep(ctx), errors = [], set = loadSet(cfg, p, errors);
    const menus = cfg && isObj(cfg.menus) ? cfg.menus : {};
    for (const id of Object.keys(menus)) if (isObj(menus[id]) && menus[id].look !== undefined) checkMenuLook(p, set, menus[id].look, id, errors);
    return errors;
  }

  /* ---------------------------------------------------------------- the layers */
  const colourOf = (v, colors) => (typeof v === 'string' && ROLES.includes(v) && has(colors, v) ? colors[v] : v);
  function globalLayers(p, set) {
    const L = [{ src: 'default', name: '', vals: p.base }];
    if (p.themeColors) L.push({ src: 'theme', name: '', vals: { colors: p.themeColors } });
    if (set.ringLook) L.push({ src: 'global-preset', name: set.ringLook, vals: presetDict(set, p, set.ringLook) });
    L.push({ src: 'global', name: '', vals: set.ring });
    return L;
  }
  function menuLayers(p, set, spec) {
    const L = globalLayers(p, set);
    if (spec.preset && presetDict(set, p, spec.preset) !== null) L.push({ src: 'menu-preset', name: spec.preset, vals: presetDict(set, p, spec.preset) });
    const keys = {};
    for (const k of Object.keys(spec)) if (k !== 'preset') keys[k] = spec[k];
    L.push({ src: 'menu', name: '', vals: keys });
    return L;
  }
  function fold(layers) {
    const vals = {}, org = {};
    for (const { src, name, vals: layer } of layers) {
      for (const k of Object.keys(layer || {})) {
        const v = layer[k];
        if (k === 'colors') {
          if (!vals.colors) vals.colors = {};
          for (const ck of Object.keys(v)) { vals.colors[ck] = v[ck]; org['colors.' + ck] = { from: src, name }; }
        } else { vals[k] = clone(v); org[k] = { from: src, name }; }
      }
    }
    return { vals, org };
  }
  const COLOUR_VALUE_KEYS = ['hub_color', 'glow_color', 'label_color', 'fill_color', 'border_color'];
  function finish(vals, p) {
    const out = Object.assign({}, vals);
    out.colors = Object.assign({}, vals.colors);
    for (const k of COLOUR_VALUE_KEYS) if (has(out, k)) out[k] = colourOf(out[k], out.colors);
    if (p.theme !== 'dark') out.theme = p.theme;
    return out;
  }

  /* Everything one target resolves to. */
  function compute(cfg, target, ctx) {
    const p = prep(ctx), set = loadSet(cfg, p, []);
    const level = (target && target.level) || 'global';
    let layers, style = null, errors = [];
    if (level === 'preset') {
      const dict = presetDict(set, p, target.name) || {};
      layers = [{ src: 'default', name: '', vals: p.base }];
      if (p.themeColors) layers.push({ src: 'theme', name: '', vals: { colors: p.themeColors } });
      layers.push({ src: 'preset', name: target.name, vals: dict });
    } else if (level === 'menu' && menuIn(cfg, target)) {
      const m = menuIn(cfg, target);
      layers = menuLayers(p, set, checkMenuLook(p, set, m.look, target.menu, errors));
      if (Number.isInteger(target.slot) && Array.isArray(m.items) && isObj(m.items[target.slot]) && m.items[target.slot].style !== undefined) {
        const raw = m.items[target.slot].style;
        style = isObj(raw) ? checkLook(p, raw, errors, 'style.', p.styleSet) : {};
      }
    } else layers = globalLayers(p, set);
    const { vals, org } = fold(layers);
    let values = finish(vals, p);
    if (style) {
      const st = Object.assign({}, style);
      for (const k of COLOUR_VALUE_KEYS) if (has(st, k)) st[k] = colourOf(st[k], values.colors);
      values = Object.assign({}, values, st);
      for (const k of Object.keys(style)) org[k] = { from: 'slot', name: '' };
    }
    return { p, set, raw: vals, org, values, level };
  }
  const menuIn = (cfg, target) => (cfg && isObj(cfg.menus) && target && has(cfg.menus, target.menu) && isObj(cfg.menus[target.menu]) ? cfg.menus[target.menu] : null);

  /* {values, origins}: the resolved look at the target and where every value comes from (looks.LookSet.explain). */
  function explain(cfg, target, ctx) {
    const c = compute(cfg, target, ctx);
    return { values: c.values, origins: c.org };
  }

  const OWN_ORIGIN = { global: 'global', menu: 'menu', preset: 'preset' };
  const keysAt = (ctx, level) => prep(ctx).at(level === 'preset' ? 'global' : level);
  const groupId = title => GROUP_ID[title] || String(title).toLowerCase().replace(/[^a-z0-9]+/g, '_');
  /* The groups of a level in schema order: [{ id, title, keys, full }]; full: every key in it is Full-only. */
  function groups(ctx, level) {
    const p = prep(ctx), out = [];
    for (const k of keysAt(ctx, level)) {
      const title = p.schema[k].group;
      let g = out.find(x => x.title === title);
      if (!g) { g = { id: groupId(title), title, keys: [], full: true }; out.push(g); }
      g.keys.push(k);
      if (!p.schema[k].full) g.full = false;
    }
    return out;
  }
  const groupOf = (ctx, key) => groupId(prep(ctx).schema[split(key)[0]].group);

  /* What the controls read: { key: { value, origin, name, eff, sub } } for the keys of the target's level. value is the
     look's own value (a role stays a role); eff is a colour key's colour as #rrggbb; 'colors' has sub[name] per colour. */
  function resolve(cfg, target, ctx) {
    const c = compute(cfg, target, ctx), out = {}, ownFrom = OWN_ORIGIN[c.level];
    // an own value that says what the level would take anyway (a file written by hand, or by an older Studio) is shown as inherited
    const org = name => {
      const o = c.org[name] || { from: 'default', name: '' };
      if (o.from !== ownFrom) return o;
      if (!redundant(cfg, target, name, ctx)) return o;
      const sh = shadow(cfg, target);
      dropKey(sh, target, name);
      return compute(sh, target, ctx).org[name] || { from: 'default', name: '' };
    };
    for (const k of keysAt(ctx, c.level)) {
      const s = c.p.schema[k];
      if (s.kind === 'colors') {
        const sub = {};
        let top = null;
        for (const n of ROLES) {
          const o = org('colors.' + n);
          sub[n] = { value: c.values.colors[n], origin: o.from, name: o.name };
          if (!top || RANK[o.from] > RANK[top.from]) top = o;
        }
        out.colors = { value: Object.assign({}, c.values.colors), origin: top.from, name: top.name, sub };
      } else {
        const o = org(k);
        const e = { value: c.raw[k], origin: o.from, name: o.name };
        if (s.kind === 'colour') e.eff = colourOf(c.raw[k], c.values.colors);
        out[k] = e;
      }
    }
    return out;
  }
  function originOf(cfg, target, key, ctx) {
    const [k, sub] = check(key, ctx);
    const c = compute(cfg, target, ctx), o = c.org[sub ? k + '.' + sub : k];
    return o ? o.from : 'default';
  }

  /* ---------------------------------------------------------------- editing */
  function check(key, ctx) {
    const [k, sub] = split(key), p = prep(ctx);
    if (!has(p.schema, k)) throw new Error('unknown look key: ' + key);
    if (sub !== null && !(p.schema[k].kind === 'colors' && ROLES.includes(sub))) throw new Error('unknown look key: ' + key);
    return [k, sub];
  }

  /* The object that holds the look keys of a target; null when there is none yet and create is false. For a menu it is the
     look object itself (a look written as a name becomes {preset: name} when create is true); canon() puts it back. */
  function holder(cfg, target, create) {
    const lv = target && target.level;
    if (lv === 'global') {
      if (cfg && isObj(cfg.ring)) return cfg.ring;
      if (!create) return null;
      cfg.ring = {};
      return cfg.ring;
    }
    if (lv === 'preset') {
      if (cfg && isObj(cfg.looks) && has(cfg.looks, target.name) && isObj(cfg.looks[target.name])) return cfg.looks[target.name];
      if (create) throw new Error('no such look: ' + target.name);
      return null;
    }
    if (lv === 'menu') {
      const m = menuIn(cfg, target);
      if (!m) { if (create) throw new Error('no such menu: ' + target.menu); return null; }
      if (isObj(m.look)) return m.look;
      if (!create) return null;
      m.look = typeof m.look === 'string' && m.look ? { preset: m.look } : {};
      return m.look;
    }
    throw new Error('look level not supported: ' + lv);
  }
  /* A menu's look in its canonical form: a name when only a preset is set, an object when there are keys, removed when empty. */
  function canon(cfg, target) {
    if (!target || target.level !== 'menu') return;
    const m = menuIn(cfg, target);
    if (!m || !has(m, 'look')) return;
    const v = m.look;
    if (!isObj(v)) { if (v === '' || v === null) delete m.look; return; }
    const pr = typeof v.preset === 'string' ? v.preset : '';
    const rest = Object.keys(v).filter(k => k !== 'preset');
    if (!rest.length) { if (pr) m.look = pr; else delete m.look; return; }
    if (Object.keys(v)[0] !== 'preset' || (!pr && has(v, 'preset'))) {
      const o = {};
      if (pr) o.preset = pr;
      for (const k of rest) o[k] = v[k];
      m.look = o;
    }
  }
  const ownKeys = (cfg, target) => {
    const o = holder(cfg, target, false);
    return o ? Object.keys(o).filter(k => k !== 'preset' && k !== 'look') : [];
  };

  /* A copy of the parts of cfg a target's resolution reads, so the level can be looked at as if its own key were not there. */
  function shadow(cfg, target) {
    const s = { ring: clone(cfg.ring), looks: clone(cfg.looks), menus: {} };
    if (target.level === 'menu' && menuIn(cfg, target)) s.menus[target.menu] = { look: clone(menuIn(cfg, target).look), items: [] };
    return s;
  }
  function dropKey(cfg, target, key) {
    const [k, sub] = split(key), o = holder(cfg, target, false);
    if (!o) return false;
    if (sub !== null) {
      if (!isObj(o.colors) || !has(o.colors, sub)) return false;
      delete o.colors[sub];
      if (!Object.keys(o.colors).length) delete o.colors;
    } else {
      if (!has(o, k)) return false;
      delete o[k];
    }
    canon(cfg, target);
    return true;
  }

  /* Writes a value, or drops the key when it equals what the level would take from the default or the theme anyway. */
  function set(cfg, target, key, value, ctx) {
    const [k, sub] = check(key, ctx);
    if (k === 'colors' && sub === null) throw new Error('set one colour at a time: colors.<name>');
    const before = JSON.stringify(cfg);
    const sh = shadow(cfg, target);
    dropKey(sh, target, key);
    const c = compute(sh, target, ctx), name = sub ? 'colors.' + sub : k;
    const inh = c.org[name] || { from: 'default' };
    const inhValue = sub ? c.values.colors[sub] : c.raw[k];
    const drop = (inh.from === 'default' || inh.from === 'theme') && (sub ? sameColour(value, inhValue) : same(value, inhValue));
    if (drop) { dropKey(cfg, target, key); return JSON.stringify(cfg) !== before; }
    const o = holder(cfg, target, true);
    if (sub !== null) { if (!isObj(o.colors)) o.colors = {}; o.colors[sub] = value; } else o[k] = value;
    canon(cfg, target);
    return JSON.stringify(cfg) !== before;
  }
  /* Removes the key (all five colours for 'colors'), whatever it holds. Returns true when cfg changed. */
  function clear(cfg, target, key, ctx) {
    const [k, sub] = check(key, ctx);
    if (sub === null && k === 'colors') {
      const o = holder(cfg, target, false);
      if (!o || !has(o, 'colors')) return false;
      delete o.colors; canon(cfg, target);
      return true;
    }
    return dropKey(cfg, target, key);
  }
  /* Is the key written at this level? ('colors' when any colour is.) */
  function isSet(cfg, target, key, ctx) {
    const [k, sub] = check(key, ctx), o = holder(cfg, target, false);
    if (!o || !has(o, k)) return false;
    if (k === 'colors') { if (!isObj(o.colors)) return false; if (sub === null) return Object.keys(o.colors).some(n => !redundant(cfg, target, 'colors.' + n, ctx)); return has(o.colors, sub) && !redundant(cfg, target, key, ctx); }
    return !redundant(cfg, target, key, ctx);
  }
  /* Does the level write a value it would take from the default or the theme anyway? Such a value is not a setting of its own
     (it hides nothing, and Reset has nothing to undo), though it stays in the file until something clears it. */
  function redundant(cfg, target, key, ctx) {
    const [k, sub] = split(key), o = holder(cfg, target, false);
    if (!o || !has(o, k)) return false;
    if (sub !== null && !(isObj(o.colors) && has(o.colors, sub))) return false;
    const sh = shadow(cfg, target);
    dropKey(sh, target, key);
    const c = compute(sh, target, ctx), name = sub ? 'colors.' + sub : k, inh = c.org[name] || { from: 'default' };
    if (inh.from !== 'default' && inh.from !== 'theme') return false;
    return sub ? sameColour(o.colors[sub], c.values.colors[sub]) : same(o[k], c.raw[k]);
  }
  /* The look keys the level writes, whatever their values. */
  const rawKeys = (cfg, target, ctx) => { const p = prep(ctx), o = holder(cfg, target, false); return o ? Object.keys(o).filter(k => p.lookSet.has(k)) : []; };
  /* The settings of its own a level has (each colour is one): ['hub', 'colors.bg', ...]. */
  function settings(cfg, target, ctx) {
    const o = holder(cfg, target, false), out = [];
    for (const k of rawKeys(cfg, target, ctx)) {
      if (k === 'colors') { if (isObj(o.colors)) for (const n of Object.keys(o.colors)) if (!redundant(cfg, target, 'colors.' + n, ctx)) out.push('colors.' + n); }
      else if (!redundant(cfg, target, k, ctx)) out.push(k);
    }
    return out;
  }
  const changed = (cfg, target, ctx) => settings(cfg, target, ctx).map(k => split(k)[0]).filter((k, i, a) => a.indexOf(k) === i);
  const ownCount = (cfg, target, ctx) => settings(cfg, target, ctx).length;
  /* Removes every look key of the level. Returns how many settings of its own that was. */
  function clearAll(cfg, target, ctx) {
    const n = ownCount(cfg, target, ctx), o = holder(cfg, target, false);
    if (!o) return 0;
    for (const k of rawKeys(cfg, target, ctx)) delete o[k];
    canon(cfg, target);
    return n;
  }

  /* The settings that Apply removes: the level's own style settings (slot shape and detail, hub, glow, labels, when full), and
     any setting the look itself gives. Ring size (radius, slot, dead zone), colours and tag colours stay unless the look sets them. */
  const KEEPS = new Set(GEOMETRY.concat(['colors']));
  function applyClears(cfg, target, dict, ctx) {
    const o = holder(cfg, target, false), gone = [];
    if (!o) return gone;
    for (const k of rawKeys(cfg, target, ctx)) {
      const keepIt = KEEPS.has(k) || String(k).startsWith('tag_');
      if (k === 'colors') {
        const theirs = isObj(dict.colors) ? Object.keys(dict.colors) : [];
        for (const n of Object.keys(o.colors || {})) if (theirs.includes(n)) gone.push('colors.' + n);
      } else if (!keepIt || has(dict, k)) gone.push(k);
    }
    return gone;
  }

  /* Uses a look at a level. Unless keep is true, the level's own settings that would hide it are removed first. Returns the
     number of settings removed. name '' follows the level above (a menu uses the ring's look; the ring uses none). */
  function usePreset(cfg, target, name, o, ctx) {
    const p = prep(ctx), keep = !!(o && o.keep);
    const dict = name ? presetDict({ presets: checkPresets(p, cfg.looks, []), ring: {}, ringLook: '' }, p, name) : {};
    if (name && dict === null) throw new Error('no such look: ' + name);
    let cleared = 0;
    if (!keep) {
      const gone = applyClears(cfg, target, dict || {}, ctx);
      const real = gone.filter(key => !redundant(cfg, target, key, ctx)).length;      // a setting that said nothing new is removed without being counted
      for (const key of gone) dropKey(cfg, target, key);
      cleared = real;
    }
    if (target.level === 'global') {
      const r = holder(cfg, target, !!name && name !== 'classic');
      if (r) { if (name && name !== 'classic') r.look = name; else delete r.look; }
    } else if (target.level === 'menu') {
      const set1 = loadSet(cfg, p, []);
      const m = menuIn(cfg, target);
      let want = name;
      if (name === 'classic' && !set1.ringLook) want = '';            // the ring has no look: a menu with none is the same thing
      if (want) holder(cfg, target, true).preset = want;
      else if (m && isObj(m.look)) delete m.look.preset;
      else if (m && typeof m.look === 'string') delete m.look;
      canon(cfg, target);
    } else throw new Error('a look cannot be used at the ' + target.level + ' level');
    return cleared;
  }
  /* The look a level uses: the preset's name, '' for none. */
  function presetOf(cfg, target) {
    if (target.level === 'global') return cfg && cfg.ring && typeof cfg.ring.look === 'string' ? cfg.ring.look : '';
    const m = menuIn(cfg, target);
    if (!m) return '';
    if (typeof m.look === 'string') return m.look;
    return isObj(m.look) && typeof m.look.preset === 'string' ? m.look.preset : '';
  }
  /* Who uses a user look: { global: bool, menus: [ids] }. */
  function usersOf(cfg, name) {
    const out = { global: presetOf(cfg, { level: 'global' }) === name, menus: [] };
    if (cfg && isObj(cfg.menus)) for (const id of Object.keys(cfg.menus)) if (presetOf(cfg, { level: 'menu', menu: id }) === name) out.menus.push(id);
    return out;
  }

  /* The user looks as {name: dict}, in the file's order. */
  const userLooks = cfg => (cfg && isObj(cfg.looks) ? cfg.looks : {});
  const lookDict = (cfg, name, ctx) => {
    const p = prep(ctx);
    if (has(userLooks(cfg), name) && isObj(cfg.looks[name])) return cfg.looks[name];
    return has(p.builtin, name) ? p.builtin[name].look : null;
  };
  /* A new look from what the target shows now: every setting that is not the default or the theme's, without ring size unless geometry is true. */
  function newPreset(cfg, target, name, o, ctx) {
    const bad = nameProblem(name, ctx);
    if (bad) throw new Error(bad);
    const c = compute(cfg, target, ctx), dict = {}, geometry = !!(o && o.geometry);
    for (const k of keysAt(ctx, target.level)) {
      if (!geometry && GEOMETRY.includes(k)) continue;
      if (c.p.schema[k].kind === 'colors') {
        const cols = {};
        for (const n of ROLES) { const g = c.org['colors.' + n]; if (g && g.from !== 'default' && g.from !== 'theme') cols[n] = c.values.colors[n]; }
        if (Object.keys(cols).length) dict.colors = cols;
      } else if (c.org[k] && c.org[k].from !== 'default' && c.org[k].from !== 'theme') dict[k] = clone(c.raw[k]);
    }
    if (!isObj(cfg.looks)) cfg.looks = {};
    cfg.looks[name] = dict;
    return dict;
  }
  function duplicate(cfg, from, to, ctx) {
    const bad = nameProblem(to, ctx);
    if (bad) throw new Error(bad);
    const src = lookDict(cfg, from, ctx);
    if (src === null) throw new Error('no such look: ' + from);
    if (!isObj(cfg.looks)) cfg.looks = {};
    cfg.looks[to] = clone(src);
    return cfg.looks[to];
  }
  /* Renames a user look and every reference to it (ring.look, menu looks). Keeps the order of the looks. Returns how many references changed. */
  function rename(cfg, from, to, ctx) {
    const bad = nameProblem(to, ctx);
    if (bad) throw new Error(bad);
    if (!has(userLooks(cfg), from)) throw new Error('no such look: ' + from);
    const moved = {};
    for (const k of Object.keys(cfg.looks)) moved[k === from ? to : k] = cfg.looks[k];
    cfg.looks = moved;
    let n = 0;
    if (cfg.ring && cfg.ring.look === from) { cfg.ring.look = to; n++; }
    for (const m of Object.values(isObj(cfg.menus) ? cfg.menus : {})) {
      if (!isObj(m)) continue;
      if (m.look === from) { m.look = to; n++; } else if (isObj(m.look) && m.look.preset === from) { m.look.preset = to; n++; }
    }
    return n;
  }
  /* Deletes a user look. Whoever used it either keeps its settings as their own (bake: the look's keys are written to them,
     their own keys winning) or goes back to the level above. Returns who used it. */
  function remove(cfg, name, o, ctx) {
    const users = usersOf(cfg, name), dict = has(userLooks(cfg), name) ? clone(cfg.looks[name]) : {};
    const bake = !!(o && o.bake);
    const lay = (host) => {                               // the look's keys under the host's own
      for (const k of Object.keys(dict)) {
        if (k === 'colors') { host.colors = Object.assign({}, dict.colors, isObj(host.colors) ? host.colors : {}); }
        else if (!has(host, k)) host[k] = clone(dict[k]);
      }
    };
    if (users.global) {
      const r = holder(cfg, { level: 'global' }, true);
      delete r.look;
      if (bake) lay(r);
    }
    for (const id of users.menus) {
      const t = { level: 'menu', menu: id }, l = holder(cfg, t, true);
      delete l.preset;
      if (bake) lay(l);
      canon(cfg, t);
    }
    if (isObj(cfg.looks)) { delete cfg.looks[name]; if (!Object.keys(cfg.looks).length) delete cfg.looks; }
    return users;
  }

  /* One line for a look: { preset, builtin, count, text }, e.g. 'Soft + 2 changes', 'Custom (3 changes)', 'Same as all menus'. */
  function labelOf(name, ctx) { const p = prep(ctx); return has(p.builtin, name) ? p.builtin[name].label : name; }
  function summary(cfg, target, ctx) {
    const p = prep(ctx), name = presetOf(cfg, target);
    const known = !!name && (has(p.builtin, name) || has(userLooks(cfg), name));
    let count = 0;
    try { count = ownCount(cfg, target, ctx); } catch (e) { count = 0; }
    const label = !name ? '' : known ? labelOf(name, ctx) : name + ' (missing)';
    let text;
    if (name) text = count ? label + ' + ' + plural(count, 'change') : label;
    else if (count) text = 'Custom (' + plural(count, 'change') + ')';
    else text = target.level === 'menu' ? 'Same as all menus' : 'Classic';
    return { preset: name, builtin: has(p.builtin, name), known, count, text };
  }

  const ZLook = { ROLES, GEOMETRY, FALLBACK_SCHEMA, prep, hasPresets, explain, resolve, originOf, problems, groups, groupOf, keysAt, holder, set, clear, clearAll, isSet,
    changed, settings, redundant, ownCount, usePreset, presetOf, usersOf, userLooks, lookDict, newPreset, duplicate, rename, remove, summary, labelOf, nameProblem, applyClears };
  if (root) root.ZLook = ZLook;
  if (typeof module !== 'undefined') module.exports = ZLook;
})(typeof window !== 'undefined' ? window : null);
