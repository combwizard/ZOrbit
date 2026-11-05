/* What Simple mode hides, in one place. Pure: no DOM, no globals of app.js, so Node can load it too (tests/js/mode_gating.js does).

   The mode only changes what Studio shows; the ring, the app and radial.json never see it. These tables and tests say which settings,
   item types and problem targets belong to Full only, so app.js and look-screen.js agree on when to show a "set in Full mode" note
   and when a link has to switch to Full first.

   Functions that need the config's own helpers take a small context object:
     ctx = { defaults, kindOf, menuOf }
   defaults is the ring defaults (S.defaults), kindOf(item) the item's type name, menuOf(id) a menu of the config or undefined. */
(function (root) {
  'use strict';

  /* Item types that only Full offers. The everyday types (Brush, Alpha, Material, Texture, Press, Toggle, Submenu) are in both modes. */
  const FULL_KINDS = new Set(['set', 'capture', 'tool', 'project', 'layout', 'steps', 'auto', 'tag', 'browser']);
  const kindIsFull = k => FULL_KINDS.has(k);

  /* Ring settings that only Full shows, with the names the "changed in Full mode" note uses. The hint line is not here: both modes
     have its switch. */
  const FULL_RING = { tag_colors: 'Tag colours', tag_band: 'Tag colours', tag_band_opacity: 'Tag colours', tag_glow_opacity: 'Tag colours', tag_tint_opacity: 'Tag colours',
    tag_tint_style: 'Tag colours', tag_tint_blend: 'Tag colours', colors: 'Colours', hover_submenus: 'Open submenus on hover', tag_limit: 'Tag fan slots', hub: 'Hub', hub_style: 'Hub', hub_color: 'Hub', hub_glow: 'Hub',
    glow_color: 'Glow', glow_opacity: 'Glow', label_color: 'Label colour', slot_corner: 'Slot detail', border_width: 'Slot detail', icon_scale: 'Slot detail', tap_ms: 'Tap time', timeout_s: 'Auto-close' };
  const FULL_CARDS = new Set(['set-zbrush-bridge', 'set-older-zbrush']);
  /* Of the names above, the ones that live on the Look screen; the rest are on Settings. */
  const LOOK_FULL_NAMES = new Set(['Tag colours', 'Colours', 'Hub', 'Glow', 'Label colour', 'Slot detail']);

  const isObj = v => !!v && typeof v === 'object' && !Array.isArray(v);

  /* A menu look that only names a look ("soft", or {preset: "soft"}) is what Simple's Use for button writes. Any other key is a Full setting. */
  const lookHasOwn = look => isObj(look) && Object.keys(look).some(k => k !== 'preset');
  /* A menu with fan out or swallow turned off, or a look with settings of its own: the Menu tab shows those fields only in Full. (A menu's own
     open animation is set on the Look screen, which Simple has.) */
  const menuFullSet = m => !!m && (m.fan === true || m.swallow === false || lookHasOwn(m.look));

  /* Names (deduplicated, in settings order) of Full-only settings that differ from the defaults. where: 'look' or 'settings' keeps the ones that screen shows. */
  function fullOnlyChanges(cfg, where, ctx) {
    const defaults = (ctx && ctx.defaults) || {};
    const names = [], add = n => { if (!names.includes(n) && (!where || LOOK_FULL_NAMES.has(n) === (where === 'look'))) names.push(n); };
    const r = isObj(cfg && cfg.ring) ? cfg.ring : {};
    for (const k of Object.keys(FULL_RING)) {
      if (k === 'colors' || !(k in r)) continue;
      if (JSON.stringify(r[k]) !== JSON.stringify(defaults[k])) add(FULL_RING[k]);
    }
    if (isObj(r.colors) && Object.keys(r.colors).some(c => String(r.colors[c]).toLowerCase() !== String((defaults.colors || {})[c]).toLowerCase())) add('Colours');
    const b = cfg && cfg.bridge;
    if (isObj(b)) {
      const key = String(b.key || '').trim().toLowerCase();
      if ((b.mode !== undefined && b.mode !== 'auto') || (key && key !== 'f9')) add('ZBrush bridge');
    }
    const p = cfg && cfg.profile;
    if (isObj(p) && p.next_hotkey) add('Next profile hotkey');
    const w = cfg && cfg.browser;
    if (isObj(w) && typeof w.quit_after_minutes === 'number' && w.quit_after_minutes !== 0) add('Quit hidden browser after');
    return names;
  }

  /* The Look-screen names of look keys ('hub', 'colors.bg', ...) that only Full shows, deduplicated, in the order given. */
  function fullOnlyLookNames(keys) {
    const names = [];
    for (const key of keys || []) {
      const n = FULL_RING[String(key).split('.')[0]];
      if (n && LOOK_FULL_NAMES.has(n) && !names.includes(n)) names.push(n);
    }
    return names;
  }

  /* Does this config hold something Simple hides? Then a fresh start would pick Full. */
  const needsFull = (cfg, ctx) => fullOnlyChanges(cfg, undefined, ctx).length > 0
    || Object.values((cfg && cfg.menus) || {}).some(m => m && (menuFullSet(m) || (Array.isArray(m.items) && m.items.some(it => kindIsFull(ctx.kindOf(it))))));

  /* Would going to this problem target land on something Simple hides? */
  function targetNeedsFull(t, ctx) {
    if (!t) return false;
    if (t.kind === 'settings') return FULL_CARDS.has(t.card) || !!(t.key && FULL_RING[t.key]);
    if (t.kind === 'look') return Number.isInteger(t.slot) || t.level === 'preset' || !!(t.key && FULL_RING[t.key] && LOOK_FULL_NAMES.has(FULL_RING[t.key]));      // the slot level and editing a look are Full only
    if (t.kind === 'menu') return t.field === 'id' || t.field === 'swallow' || t.field === 'fan';
    if (t.kind === 'item') { const m = ctx.menuOf(t.menuId), it = m && m.items && m.items[t.index]; return !!it && kindIsFull(ctx.kindOf(it)); }
    return false;
  }

  const ZMode = { FULL_KINDS, FULL_RING, FULL_CARDS, LOOK_FULL_NAMES, kindIsFull, lookHasOwn, menuFullSet, fullOnlyChanges, fullOnlyLookNames, needsFull, targetNeedsFull };
  if (root) root.ZMode = ZMode;
  if (typeof module !== 'undefined') module.exports = ZMode;
})(typeof window !== 'undefined' ? window : null);
