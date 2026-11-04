/* Browser-only stand-in for pywebview's js_api. Loaded by index.html only when the URL has ?mock.
   Backed by window.__RADIAL_MOCK__ (recorded real responses from dev/mock_data.js).
   Extra URL switches for visual testing: ?problems (sample problems), ?status=down (ZBrush and the app off; Start app is refused
   with reason "zbrush"), ?status=up (the app already runs; by default ZBrush and the app both run; with ?appoff, ?startfail or any other ?status the app stays off until Start app succeeds),
   ?startfail (start_app answers reason "failed" with three lines after 1.5 s; ?startfail=empty: no lines, "It wrote nothing to its log"),
   ?startwait (start_app answers starting: true after 2 s, and the app is up 6 s later), ?startslow (start_app takes 7 s, then works), ?legacy (legacy_only: key-bridge listener card),
   ?nocheck (zbrush_check_ok false: the ZBrush card says "Could not check"),
   ?lag=300 (artificial latency in ms for preview calls and for the ZScript install/remove, so the busy row is visible), ?broken (get_config fails to parse: recovery screen),
   ?conflict (the first save without force reports "file changed on disk"), ?keptbroken (the first save says the old file was not valid JSON and is kept as radial.json.broken),
   ?badmenus=null|noitems|string|items (get_config hands out a hand-edited file: a null menu, a menu without items, a menu that is a string, an item that is null),
   ?allproblems (validate lists one of every loader message, to read describeProblem's wording), ?blocked (a save without force is
   refused as "no ring can open" until forced), ?nozbrush (get_library: ZBrush not found, no brushes), ?nolib (ZBrush
   found but no .zbp files in its folders), ?liberr (get_library reports an error), ?thumbfail (the first two get_thumbs
   calls are rejected, then they work), ?already (the first "Add a ZBrush folder" says the folder is already listed), ?busy
   (install/remove report that another operation is running), ?update (check_update finds a newer release Studio can install: the
   update dialog downloads for two seconds; with ?portable it only links to the release, ?updatefail ends the download with the hash message;
   Don't remind me again stores skipped_version in rm_prefs, so clear it to see the chip again), ?unreach
   (check_update cannot reach GitHub), ?prefsfail (set_pref is rejected).
   Tags (state in localStorage rm_tags, seeded with the built-in Favourites tag (always first, cannot be renamed, merged or deleted), the two
   starters and a few tagged brushes, three of them starred): ?tags=empty (only Favourites, nothing tagged),
   ?tagsmany (Favourites and 30 tags with long names), ?tagfail (every tag change is refused), ?tagexists (create and rename always clash with
   the first ordinary tag). The first two keep their state in memory only, so a reload starts clean.
   Usage (get_usage / forget_recent; state in localStorage rm_usage_<kind>): a made-up Recent list of six items of that kind and scores for 24
   (the order of Favourites); a pick in the popout moves that item to the front of Recent. ?usage=empty (nothing picked yet, no scores).
   Import and export (Settings): ?importfail (the picked file is refused with a message), ?importcancel (the file dialog is closed),
   ?importtags (the file holds tags only), ?importnotags (the file holds no tags, so there is no Merge or Replace); pick_import reports menus,
   current_menus, tags, current_tags and has_tags like the backend; an import changes the ring accent to cyan so it can be seen.
   Share one menu (Menu tab > Export menu..., Menus list > Import menu...): export_menu, pick_menu_import and apply_menu_import answer for a made-up
   file holding "Sculpt" and its submenu "Brushes", placed against the cfg they are given (so a taken id or title is renamed), with 2 tags (1 new)
   and two missing brushes; ?importcancel closes the dialog, ?importfail refuses the file.
   get_library/get_thumbs answer for every kind (brush, alpha, material, texture); the ?nozbrush/?nolib/?liberr switches apply to all of them.
   get_library gives a "signature" and, when called with the one the page holds, answers {unchanged: true, ...} without items (logged to the console);
   ?libsig=changing makes every call give a new signature, so the full list always comes back.
   The popout page (popout.html?mock): ?nopick (a pick is refused as "ZOrbit is not running"), ?tag=blocking (opens filtered, as --tag does),
   ?kind=alpha (opens on that tab, else the last one, kept in localStorage rm_pop_kind);
   Keep on top is kept in localStorage rm_pop_on_top (on until switched off), and the popout_* calls only log.
   ?kinds adds a Tag item ({"tag": "blocking"}) and a Browser item ({"browser": ""}) to the end of the Tools menu, so the two newer
   kinds can be seen (the recorded config has none). The default stays the faithful recording.
   Profiles (the picker after the brand in the top bar): ?profiles=3 (three profiles, Creatures, Default and Hard surface, each with its own menus: the first menu's title carries the
   profile's name; the default is the one profile Default), ?profilesoff (enabled: false, as when a menus file is pinned: no picker), ?profilegone (the first save finds its profile deleted:
   save_config answers profile_missing). pick_profile_file follows ?importcancel and ?importfail. Profiles live in this page only: a reload starts again from the defaults.
   Studio mode: ?mode=simple|full (start Studio in that mode; the mock defaults to full so the screenshots keep their content).
   Theme: ?theme=dark|light|system|zbrush (start in that theme, on Studio and on popout.html; the mock defaults to dark. The Theme card in Settings changes it
   in this page only while ?theme= is given, else in localStorage rm_prefs; system follows the browser's prefers-color-scheme, which DevTools can emulate).
   zbrush uses a fixed sample scheme (the stock ZBrush grey) for theme_tokens, the ring colours and theme_source; ?zbnone says ZBrush has stored nothing,
   so zbrush resolves to dark with theme_source null (the "No stored ZBrush colours" line).
   get_options carries theme_ring_colors and themes, the defaults carry the colours of the theme in force, and the preview_* calls answer with
   preview_ring_light, preview_ring_hover0_light, preview_tags_light and preview_animation_light under light when the recording has them (else the dark pictures).
   Setup screen (get_setup; state in localStorage rm_env for the registered folder and rm_zscript for the ZScript plugin, which Settings > Older
   ZBrush shares): ?firstrun (setup_done is false until Finish or Skip, so Studio opens on Setup; a reload does it again; tour_seen
   is false until the tour is answered, so the tour is also offered after Finish or Skip),
   ?zb=2026|2022|both|none|multi (which ZBrush installs exist; default both = 2026 plus the two older ones, multi adds 2027 and runs two),
   ?setupfail (get_setup fails every time: only {now, checked_at, failed, error}), ?setupfail=later (the first two answers are good, then it fails),
   ?addmodern (Add a ZBrush folder picks a ZBrush 2027: ok, python: true, listed in Setup with Fix and Forget),
   ?noenv (ZBRUSH_PLUGIN_PATH not set until Fix), ?fixfail (Fix is refused), ?nobridge (the plugin folder is missing: no Fix),
   ?zbrun=off (no ZBrush process), ?zbstale (it started before the plugin: restart), ?zbstart (it is still starting), ?noloaded (it never loaded the plugin),
   ?elevated (the ZBrush is running as administrator and cannot be matched to an install; ?elevated=loaded: its listener answers, so the plugin counts as loaded), ?appoff (the app is not running), ?otherbridge (another ZOrbit
   folder is registered too, one of them missing), ?bridgemode=key (picks go through the bridge key), ?ringtried=open|sent|done (step 3 starts part
   way, measured from when Setup is first shown), ?ringauto (once step 3 opens, the ring opens after 2 s, a pick follows after 4 s and ZBrush answers
   after 6 s; with ?bridgemode=key ZBrush never answers, so the hint shows). In the console, __mock.ring('open'), ('pick') and ('ack') do the same by hand.
   Upgrades: ?whatsnew (get_whats_new answers two sections, 0.13.0 with a summary and 0.12.0 with five items, so Studio opens the What's new dialog; without it the list is empty
   unless the Settings button asks for all of them), ?strays (get_strays finds 3 menus and 5 tags from an older version, so Studio asks to add them as a profile or set them
   aside; adopt_strays works in this page only), ?appolder (the app runs as ZOrbit 0.12.0, older than this Studio: a toast and a Restart app button on Status; Start app
   answers restarted and the app is current), ?toonew (get_config answers config null with too_new: the recovery screen with only Open folder). */
(function () {
  var M = window.__RADIAL_MOCK__ || {};
  var q = new URLSearchParams(location.search);
  var lag = +(q.get('lag') || 0);
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var clone = function (o) { return JSON.parse(JSON.stringify(o)); };
  var straysFound = q.has('strays'), appRestarted = false;
  var mockUpd = { state: 'idle', version: '', done: 0, total: 0, message: '', file: '' };
  // The release an older install (0.18.0) is offered in ?update: the real 0.18.1 notes, so the docs picture of the dialog is true.
  var UPD_NOTES = { version: '0.18.1', date: '2026-11-04', url: 'https://github.com/combwizard/zorbit/releases/tag/v0.18.1', blog: '',
    summary: ['ZOrbit 0.18.1 fixes **Install update**. Studio refused every release’s setup file, so it only offered the download page, and wrongly said your copy was not installed with Setup. If you are on 0.18.0 or older, install this version by hand once, and later updates work from Studio.'],
    items: ['**Install update** was not offered, because Studio refused every release’s setup file.', 'When an installed copy cannot trust a setup file, the dialog now says that.'] };
  var libSeq = {}, ticks = 0, thumbCalls = 0, alreadyDone = false, appStarted = false, setupCalls = 0, modernAdded = false, keptDone = false;
  var saved = clone(M.get_config.config);
  var TAG_DEFAULTS = { radius: 145, slot: 72, dead_zone: 38, labels: 'name', slot_corner: 0.28, border_width: 2, icon_scale: 1, hub_style: 'dot', hub_color: 'accent', hub_glow: 1,
    glow_color: '', glow_opacity: 0.55, label_color: 'text', when_full: 'grow', look: undefined,
    hub: 10, slot_shape: 'circle', tag_colors: 'tint', tag_band: 'medium', tag_band_opacity: 0.45, tag_glow_opacity: 0.4, tag_tint_opacity: 0.3, tag_tint_style: 'gradient', tag_tint_blend: 'multiply' };
  var KINDS = ['brush', 'alpha', 'material', 'texture', 'press', 'set', 'toggle', 'steps', 'menu', 'auto', 'tag', 'browser', 'empty'];
  if (q.has('kinds') && saved.menus && saved.menus.tools) saved.menus.tools.items.push({ tag: 'blocking' }, { browser: '' });
  var mtime = 1700000000000000000, conflictDone = false;
  var FAV = 'favourite';
  var TAG_PALETTE = ['#A8DF23', '#C77DFF', '#FFD166', '#5EEAD4', '#F472B6', '#E8413C', '#F86B33', '#4DC8E9'];   // as tags.PALETTE in tags.py
  var tagsMode = q.get('tags') === 'empty' ? 'empty' : q.has('tagsmany') ? 'many' : 'saved';
  var tagMtime = 1700000000000000000, tagStore = null;
  var BROKEN_ERR = "Expecting ',' delimiter: line 12 column 5 (char 301)";

  /* ---- profiles: `saved` stays the editing profile's saved config, so everything below that reads it needs no change */
  var P0 = (M.get_profiles && M.get_profiles.editing) || (M.get_config && typeof M.get_config.profile === 'string' && M.get_config.profile) || 'Default';
  var profilesOn = !q.has('profilesoff'), profileGoneDone = false, pickedFile = false;
  var profiles = { names: [P0], active: P0, editing: P0, saved: {} };
  if (q.has('profiles')) {
    var extra = ['Creatures', 'Hard surface', 'Props', 'Characters', 'Vehicles'].slice(0, Math.max(1, +q.get('profiles') || 3) - 1);
    profiles.names = [P0].concat(extra);
  }
  function profTitle(cfg, name) {                                  // a different first menu title, so a switch can be seen
    var ids = Object.keys(cfg.menus || {});
    if (ids.length) cfg.menus[ids[0]].title = (cfg.menus[ids[0]].title || ids[0]) + ' (' + name + ')';
    return cfg;
  }
  profiles.names.sort(function (a, b) { return a.localeCompare(b, undefined, { sensitivity: 'base' }); });
  profiles.names.forEach(function (n) { profiles.saved[n] = n === P0 ? clone(saved) : profTitle(clone(saved), n); });
  var profInfo = function () { return { profile: profiles.editing, active: profiles.active, profiles: profiles.names.slice(), enabled: profilesOn }; };
  var profFind = function (n) { var l = String(n).trim().toLowerCase(), hit = profiles.names.filter(function (x) { return x.toLowerCase() === l; })[0]; return hit === undefined ? null : hit; };
  var profFolder = function (n) { return 'C:\\Users\\you\\AppData\\Roaming\\ZOrbit' + (n === P0 ? '' : '\\profiles\\' + n); };
  var profSort = function () { profiles.names.sort(function (a, b) { return a.localeCompare(b, undefined, { sensitivity: 'base' }); }); };
  // The words create_profile and rename_profile refuse a name with (the backend's checks, close enough)
  function profNameProblem(name, ignore) {
    var t = typeof name === 'string' ? name.trim() : '';
    if (!t) return 'Give the profile a name.';
    if (/[\\/:*?"<>|]/.test(t)) return 'A profile name cannot contain \\ / : * ? " < > |';
    var hit = profFind(t);
    if (hit !== null && hit !== ignore) return 'There is already a profile called ' + hit + '.';
    return '';
  }

  // Python's repr of a string, close enough for the messages: 'x'
  function pyr(v) { return typeof v === 'string' ? "'" + v + "'" : String(v); }

  // The items the ring would draw: one action each, submenu targets that exist (the order preview_ring's indices count in)
  function usable(m) { return usableAt(m).map(function (i) { return m.items[i]; }); }
  function usableAt(m) {                    // their indices in m.items
    var out = [];
    (m.items || []).forEach(function (it, i) {
      var ks = KINDS.filter(function (k) { return k in it; });
      if (ks.length !== 1) return;
      var k = ks[0];                       // config.py: every string target but a browser's must be non-empty; an empty slot (true) always counts, so the ring keeps its place
      if (k === 'empty' ? it.empty === true : k === 'steps' || k === 'auto' || k === 'browser' || (typeof it[k] === 'string' && it[k].trim() !== '')) out.push(i);
    });
    return out;
  }

  // One of every message config.py can produce (menu ids are the recorded ones), for ?allproblems
  var ALL_PROBLEMS = [
    'bridge: must be an object like {"mode": "auto", "key": "F9"}', 'bridge.moed: unknown setting (did you mean mode?)', "bridge.mode 'fast' unknown; using auto",
    "bridge.key 'Ctrl+Q+Q' not understood; using F9", 'bridge.key must not use Ctrl or Shift (ZBrush reads them as mask/smooth); use a bare F-key; using F9',
    'ring: must be an object like {"radius": 145, "animation": "smooth"}', "ring.colors.bg: 'red' is not a #rrggbb colour", 'ring.colors.acent: unknown colour (did you mean accent?)',
    "ring.radius: 500 must be a number from 60 to 400", "ring.flick: 'yes' must be true or false", "ring.animation: 'spin' unknown; one of smooth, bounce, pop",
    "ring.labels: 'all' unknown; one of name, none", "ring.tag_band: 'huge' unknown; one of none, hairline, narrow, medium, wide", 'ring.raduis: unknown setting (did you mean radius?)',
    'menus: must be a non-empty object of id -> menu',
    'menu odd: not an object', "menu tag:x: ids starting with 'tag:' are reserved for tag submenus", "menu brushes: unknown setting 'hotkye' (did you mean hotkey?)",
    'menu brushes item 1: not an object', 'menu brushes item 2: needs exactly one of brush, alpha, material, texture, press, set, toggle, steps, menu, auto, tag, browser',
    "menu brushes item 3: 'set' needs a 'value'", "menu brushes item 3: 'set' value must be a number", "menu brushes item 4: 'steps' must be a non-empty list of brush/alpha/material/texture/press/set/toggle actions",
    'menu brushes item 4 step 2: not an object', "menu brushes item 4 step 1: 'brush' must be a non-empty string", 'menu brushes item 4 step 2: steps cannot open menus, nest steps, be auto slots, be empty slots or open tags or the browser',
    "menu brushes item 5: 'auto' must be one of brush", "menu brushes item 5: 'browser' must be a string (a tag key, or \"\" for everything)", "menu brushes item 5: browser 'kind' must be one of brush, alpha, material, texture",
    "menu brushes item 6: 'press' must be a non-empty string", "menu brushes item 6: brush name 'C:\\x\\Clay' must not contain \\ / : or ..", "menu brushes item 7: submenu 'nope' does not exist",
    "menu brushes item 7: unknown setting 'lable' (did you mean label?)", "menu brushes item 8: tag 'gone' does not exist; the slot stays empty", "menu brushes item 8: tag 'gone' does not exist; the browser opens unfiltered",
    "menu brushes item 9: icon '\\\\pc\\share\\a.png' must be a plain file path on this PC, not a network path", "menu brushes item 9: style.glow_color: 'orange' is not a #rrggbb colour or a theme colour (bg, accent, highlight, text, lines)", "menu brushes item 9: submenu 'tools' has no usable items",
    "menu brushes item 2: style.size: 3 must be a number from 0.75 to 1.25", "menu brushes item 2: style.slot_shape: 'star' unknown; one of circle, rounded, squircle, hexagon, octagon, diamond",
    "menu brushes item 2: style.slot_shap: unknown setting (did you mean slot_shape?)", "menu brushes item 3: style.tap_ms: is a ring setting, not part of a look; ignored",
    "menu brushes item 3: style.fill_color: 'red' is not a #rrggbb colour or a theme colour (bg, accent, highlight, text, lines)", 'menu brushes item 4: style must be an object like {"slot_shape": "hexagon"}; ignored',
    "menu brushes item 5: unknown setting 'glow' (glow is now style.glow_color)",
    'looks: must be an object like {"My look": {"slot_shape": "hexagon"}}; ignored', 'looks.Mine: not an object; ignored',
    'looks.My look!: name must be 1 to 32 letters, digits, spaces, - or _; ignored', 'looks.soft: that name is a built-in look or is reserved, give it another; ignored',
    "looks.mine: same name as 'Mine' apart from capitals; ignored", 'looks.Mine.preset: a look cannot be based on another look; ignored',
    'looks.Mine.hub: 99 must be a number from 0 to 64', "looks.Mine.slot_shape: 'star' unknown; one of circle, rounded, squircle, hexagon, octagon, diamond",
    "looks.Mine.hub_color: 'red' is not a #rrggbb colour or a theme colour (bg, accent, highlight, text, lines)", "looks.Mine.colors.bg: 'red' is not a #rrggbb colour",
    'looks.Mine.tap_ms: is a ring setting, not part of a look; ignored', "ring.look: 'Gone' unknown; one of classic, soft, tiles, crystal, circuit, diamonds, minimal",
    "menu brushes: look 'Nope' unknown; using the ring's look", 'menu brushes: look must be a look name or an object like {"preset": "soft", "hub": 14}; ignored',
    'menu brushes: look.hub: 99 must be a number from 0 to 64', 'menu brushes: look.tap_ms: is a ring setting, not part of a look; ignored',
    'menu tools: no usable items', "menu tools: hotkey 'Q' already used by menu brushes", "menu tools: hotkey 'Ctrl+Q+Q' not understood", "menu tools: animation 'spin' unknown; using ring.animation",
    "menu tools: swallow 'no' must be true or false; using true", "menu tools: fan 'yes' must be true or false; using false",
    'browser: must be an object like {"hotkey": "Alt+B"}', 'browser.hotkye: unknown setting (did you mean hotkey?)', "browser.hotkey 'Alt+B+B' not understood", "browser.hotkey 'Q' already used by menu brushes",
    'tags.json could not be read: Expecting value: line 1 column 1 (char 0); tag slots stay empty until it is fixed', 'config could not be read: boom', 'no menu has a hotkey, so nothing can open the ring', 'a message nobody has taught the page'];

  // The sample menu file placed against cfg like the backend's plan_import: a free id and a free title for each menu, links repointed.
  function menuImportPlan(cfg) {
    var have = (cfg && cfg.menus) || {}, taken = {}, out = {}, ren = [], map = {}, root = 'sculpt';
    var file = { sculpt: { title: 'Sculpt', items: [{ brush: 'ClayBuildup' }, { menu: 'brushes' }, { tag: 'rock' }] }, brushes: { title: 'Brushes', items: [{ brush: 'DamStandard' }] } };
    var titles = Object.keys(have).map(function (k) { return String(have[k].title || '').trim().toLowerCase(); });
    Object.keys(file).forEach(function (old) {
      var id = old, n = 2, t = file[old].title, nt = t;
      while (have[id] || taken[id]) id = old + '_' + n++;
      n = 2; while (titles.indexOf(nt.toLowerCase()) >= 0) nt = t + ' ' + n++;
      taken[id] = true; titles.push(nt.toLowerCase()); map[old] = id;
      out[id] = { title: nt, items: clone(file[old].items) };
      if (id !== old || nt !== t) ren.push({ old_id: old, id: id, old_title: t, title: nt });
    });
    Object.keys(out).forEach(function (id) { out[id].items.forEach(function (it) { if (it.menu) it.menu = map[it.menu]; }); });
    return { menus: out, root: map[root], renames: ren };
  }

  function validate(cfg) {
    var out = [];
    var menus = (cfg && cfg.menus) || {};
    var ids = Object.keys(menus);
    var seen = {}, st = tagState();
    if (window.ZLook) out.push.apply(out, window.ZLook.problems(cfg, mockCtx()));        // looks, ring.look, menu looks and every look value, from look.js
    if (!ids.length) out.push('menus: must be a non-empty object of id -> menu');
    ids.forEach(function (id) {
      var m = menus[id], good = 0;
      if (id.indexOf('tag:') === 0) { out.push('menu ' + id + ": ids starting with 'tag:' are reserved for tag submenus"); return; }
      (m.items || []).forEach(function (it, i) {
        var kinds = KINDS.filter(function (k) { return k in it; });
        var where = 'menu ' + id + ' item ' + (i + 1);
        if (kinds.length !== 1) { out.push(where + ': needs exactly one of ' + KINDS.join(', ')); return; }
        var k = kinds[0];
        if (k === 'steps') {
          if (!Array.isArray(it.steps) || !it.steps.length) { out.push(where + ": 'steps' must be a non-empty list of brush/alpha/material/texture/press/set/toggle actions"); return; }
          for (var j = 0; j < it.steps.length; j++) {
            var sk = KINDS.filter(function (x) { return it.steps[j] && x in it.steps[j]; });
            if (sk.some(function (x) { return ['menu', 'steps', 'auto', 'tag', 'browser', 'empty'].indexOf(x) >= 0; })) {
              out.push(where + ' step ' + (j + 1) + ': steps cannot open menus, nest steps, be auto slots, be empty slots or open tags or the browser'); return;
            }
          }
        }
        else if (k === 'empty') { if (it.empty !== true) { out.push(where + ": 'empty' must be true"); return; } }
        else if (k === 'browser') { if (typeof it.browser !== 'string') { out.push(where + ": 'browser' must be a string (a tag key, or \"\" for all brushes)"); return; } }
        else if (k === 'set' && !('value' in it)) { out.push(where + ": 'set' needs a 'value'"); return; }
        else if (k === 'set' && typeof it.value !== 'number') { out.push(where + ": 'set' value must be a number"); return; }
        else if (typeof it[k] !== 'string' || !it[k].trim()) { out.push(where + ": '" + k + "' must be a non-empty string"); return; }
        var gc = it.style && it.style.glow_color;
        if (gc && !(typeof gc === 'string' && /^(#[0-9a-fA-F]{6}|bg|accent|highlight|text|lines)$/.test(gc))) out.push(where + ': style.glow_color: ' + pyr(gc) + ' is not a #rrggbb colour or a theme colour (bg, accent, highlight, text, lines)');
        if (it.glow !== undefined) out.push(where + ": unknown setting 'glow' (glow is now style.glow_color)");
        if (k === 'menu' && !menus[it.menu]) { out.push(where + ": submenu '" + it.menu + "' does not exist"); return; }
        if (k === 'tag' && !hasTag(st, it.tag)) out.push(where + ': tag ' + pyr(it.tag) + ' does not exist; the slot stays empty');
        else if (k === 'browser' && it.browser && !hasTag(st, it.browser)) out.push(where + ': tag ' + pyr(it.browser) + ' does not exist; the browser opens unfiltered');
        good++;
      });
      if (!good) out.push('menu ' + id + ': no usable items');
      if (m.hotkey) {
        var key = String(m.hotkey).toLowerCase();
        if (seen[key]) out.push('menu ' + id + ": hotkey '" + m.hotkey + "' already used by menu " + seen[key]);
        else seen[key] = id;
      }
    });
    var bh = cfg && cfg.browser && cfg.browser.hotkey;
    if (bh) {
      var bkey = String(bh).toLowerCase();
      if (!/^((ctrl|alt|shift)\+)*([a-z0-9`~\-=\[\]\\;',.\/]|f([1-9]|1[0-9]|2[0-4])|space|tab|enter|backspace|insert|delete|home|end|pageup|pagedown)$/.test(bkey)) out.push('browser.hotkey ' + pyr(bh) + ' not understood');
      else if (seen[bkey]) out.push('browser.hotkey ' + pyr(bh) + ' already used by menu ' + seen[bkey]);
    }
    if (!ids.some(function (id) { return menus[id].hotkey; })) out.push('no menu has a hotkey, so nothing can open the ring');
    if (q.has('allproblems')) out.push.apply(out, ALL_PROBLEMS);
    if (q.has('problems')) out.push('menu brushes item 3: sample problem for the problems panel (?problems)', 'bridge.key must not use Ctrl or Shift (ZBrush reads them as mask/smooth); use a bare F-key',
      'ring.radius: 500 must be a number from 60 to 400', "menu tools: hotkey 'Q' already used by menu brushes");
    return out;
  }

  // ---- looks (zorbit/looks.py, studio.py _look_options): the get_options structure built from a short table
  var SHAPES = ['circle', 'rounded', 'squircle', 'hexagon', 'octagon', 'diamond'], HUBS = ['dot', 'disc', 'ring', 'icon'], WHEN_FULL = ['grow', 'rings', 'more'];
  var ROLES = ['bg', 'accent', 'highlight', 'text', 'lines'];
  var BUILTIN = [
    ['classic', 'Classic', 'Round slots with an accent dot: the look ZOrbit starts with.', {}],
    ['soft', 'Soft', 'Rounder, softer slots with a quiet disc in the middle.', { slot_shape: 'squircle', border_width: 1, icon_scale: 0.92, glow_opacity: 0.7, hub_style: 'disc', hub_glow: 0.6 }],
    ['tiles', 'Tiles', 'Square tiles with rounded corners and a ring in the middle.', { slot_shape: 'rounded', slot_corner: 0.22, icon_scale: 0.9, glow_opacity: 0.45, hub_style: 'ring', hub: 14 }],
    ['crystal', 'Crystal', 'Hexagons with a bright highlight glow.', { slot_shape: 'hexagon', icon_scale: 0.85, glow_opacity: 0.8, glow_color: 'highlight', hub_style: 'ring', hub: 16, hub_color: 'highlight' }],
    ['circuit', 'Circuit', 'Thin-rimmed octagons in the line colour.', { slot_shape: 'octagon', border_width: 1, label_color: 'highlight', glow_color: 'lines', glow_opacity: 0.4, hub_style: 'ring', hub: 12, hub_color: 'lines' }],
    ['diamonds', 'Diamonds', 'Diamond slots with small icons.', { slot_shape: 'diamond', icon_scale: 0.7, border_width: 2, hub_style: 'disc', hub: 12 }],
    ['minimal', 'Minimal', 'No rim, a faint glow and a tiny dot.', { border_width: 0, glow_opacity: 0.3, hub: 6, hub_glow: 0 }]];
  function mockLooks() {
    var G = ['global', 'menu'], GS = ['global', 'menu', 'slot'], SL = ['slot'], R = function (a, b) { return { min: a, max: b }; }, C = function (list) { return { choices: list }; };
    var TABLE = [   // key, group, kind, default, shown in Simple, extras, levels
      ['radius', 'Slots', 'range', 145, 1, R(60, 400), G], ['slot', 'Slots', 'range', 72, 1, R(32, 160), G], ['dead_zone', 'Slots', 'range', 38, 1, R(10, 120), G],
      ['slot_shape', 'Slots', 'choice', 'circle', 1, C(SHAPES), GS], ['slot_corner', 'Slots', 'range', 0.28, 0, R(0, 0.5), GS], ['border_width', 'Slots', 'range', 2, 0, R(0, 6), GS],
      ['icon_scale', 'Slots', 'range', 1, 0, R(0.5, 1), GS], ['size', 'Slots', 'range', 1, 0, R(0.75, 1.25), SL], ['fill_color', 'Slots', 'colour', '', 0, { allow_empty: true }, SL],
      ['border_color', 'Slots', 'colour', '', 0, { allow_empty: true }, SL],
      ['hub', 'Hub', 'range', 10, 0, R(0, 64), G], ['hub_style', 'Hub', 'choice', 'dot', 0, C(HUBS), G], ['hub_color', 'Hub', 'colour', 'accent', 0, { allow_empty: false }, G],
      ['hub_glow', 'Hub', 'range', 1, 0, R(0, 1), G], ['glow_color', 'Glow', 'colour', '', 0, { allow_empty: true }, GS], ['glow_opacity', 'Glow', 'range', 0.55, 0, R(0, 1), G],
      ['labels', 'Labels', 'choice', 'name', 1, C(['name', 'none']), G], ['label_color', 'Labels', 'colour', 'text', 0, { allow_empty: false }, GS],
      ['colors', 'Colours', 'colors', null, 0, C(ROLES), G],
      ['tag_colors', 'Tag colours', 'choice', 'tint', 0, C(['none', 'tint', 'glow', 'both']), G], ['tag_band', 'Tag colours', 'choice', 'medium', 0, C(['none', 'hairline', 'narrow', 'medium', 'wide']), G],
      ['tag_band_opacity', 'Tag colours', 'range', 0.45, 0, R(0, 1), G], ['tag_glow_opacity', 'Tag colours', 'range', 0.4, 0, R(0, 1), G], ['tag_tint_opacity', 'Tag colours', 'range', 0.3, 0, R(0, 1), G],
      ['tag_tint_style', 'Tag colours', 'choice', 'gradient', 0, C(['flat', 'gradient']), G], ['tag_tint_blend', 'Tag colours', 'choice', 'multiply', 0, C(['multiply', 'overlay']), G],
      ['when_full', 'When full', 'choice', 'grow', 1, C(WHEN_FULL), G]];
    var schema = {};
    TABLE.forEach(function (r) {
      var e = Object.assign({ group: r[1], kind: r[2], default: r[3], full: !r[4] }, r[5]);
      e.levels = r[6];
      schema[r[0]] = e;
    });
    return { schema: schema, roles: ROLES.slice(),
      builtin: BUILTIN.map(function (b) { return { id: b[0], label: b[1], blurb: b[2], look: clone(b[3]) }; }),
      reserved: ['__defineGetter__', '__defineSetter__', '__lookupGetter__', '__lookupSetter__', '__proto__', 'constructor', 'hasOwnProperty', 'isPrototypeOf', 'propertyIsEnumerable', 'toLocaleString', 'toString', 'valueOf'],
      menu_prefixes: ['tag:', 'more:'], name: { max: 32, pattern: '^[\\p{L}\\p{N}_](?:[\\p{L}\\p{N}_ -]{0,30}[\\p{L}\\p{N}_])?$', flags: 'u' } };
  }
  function mockOptions() {
    var o = clone(M.get_options);
    o.favourite_tag = FAV;
    o.actions = KINDS.slice(); o.asset_kinds = ['brush', 'alpha', 'material', 'texture']; o.tag_colors = ['none', 'tint', 'glow', 'both'];
    o.tag_bands = ['none', 'hairline', 'narrow', 'medium', 'wide']; o.tint_styles = ['flat', 'gradient']; o.slot_shapes = SHAPES.slice(); o.tint_blends = ['multiply', 'overlay'];
    o.hub_styles = HUBS.slice(); o.when_full = WHEN_FULL.slice();
    o.theme_ring_colors = themeRing(); o.themes = o.themes || THEMES.slice();
    o.ring_defaults = Object.assign({}, o.ring_defaults, TAG_DEFAULTS, { colors: clone(o.theme_ring_colors[themeEff()]) });
    delete o.ring_defaults.look;
    o.ring_ranges = Object.assign({}, o.ring_ranges, { hub: [0, 64], tag_band_opacity: [0, 1], tag_glow_opacity: [0, 1], tag_tint_opacity: [0, 1] });
    o.looks = q.has('nolooks') ? undefined : (o.looks && o.looks.schema ? o.looks : mockLooks());       // ?nolooks: an older backend without looks
    if (!o.looks) { delete o.looks; delete o.hub_styles; delete o.when_full; o.slot_shapes = ['circle', 'rounded']; o.ring_ranges.hub = [0, 40]; }
    return o;
  }
  // What look.js takes as context
  function mockCtx() { var o = mockOptions(); return { looks: o.looks, defaults: o.ring_defaults, colors: o.theme_ring_colors, animations: o.animations, theme: themeEff() }; }
  function lookPic(name) {
    var rec = (lightPics() && M.preview_looks_light) || M.preview_looks, hit = rec && rec[name];
    var res = clone(hit || (lightPics() && M.preview_tags_light) || M.preview_tags || M.preview_ring[Object.keys(M.preview_ring)[0]]);
    res.width = res.height = res.size; res.centre = [res.size / 2, res.size / 2];
    return res;
  }
  // studio._fit: how many items the menu's ring holds at its radius (SLOT_GAP is 1.25 slot widths), for the ring-full note
  function mockFit(cfg, menuId) {
    var m = cfg && cfg.menus && cfg.menus[menuId];
    if (!m || m.fan === true || !window.ZLook) return null;
    var v = window.ZLook.explain(cfg, { level: 'menu', menu: menuId }, mockCtx()).values, n = usable(m).length, x = 1.25 * v.slot / (2 * v.radius);
    var cap = x < 1 ? Math.max(1, Math.floor(Math.PI / Math.asin(x) + 1e-6)) : 1;
    return { items: n, capacity: cap, needed_radius: n < 2 ? 0 : 1.25 * v.slot / (2 * Math.sin(Math.PI / n)), full: n > cap, when_full: v.when_full || 'grow' };
  }

  // The layout map of preview_ring (Ring.layout_map) for the ring picture the mock hands out. The recorded map is used when it fits the menu; otherwise
  // a single ring is made up from the item count and the look in the config (mock only: the picture itself is the recorded one, so it does not
  // follow a changed radius, slot size, shape or a second ring or More slot, but the overlay and the notes do, which is what the mock is for).
  function mockLayout(cfg, menuId, res) {
    var m = cfg.menus[menuId], at = usableAt(m), n = at.length, Z = window.ZLook;
    if (res.layout && res.layout.slots && res.layout.slots.length === n) return res.layout;
    if (!Z || !n) return null;
    var ctx = mockCtx(), v = Z.explain(cfg, { level: 'menu', menu: menuId }, ctx).values, size = res.size || 447;
    var R = Math.max(v.radius, n >= 2 ? 1.25 * v.slot / (2 * Math.sin(Math.PI / n)) : 0), step = 360 / n, half = Math.min(step, 90) / 2;
    var cap = mockFit(cfg, menuId), r2 = function (x) { return Math.round(x * 100) / 100; }, slots = [], gaps = [];
    at.forEach(function (ix, i) {
      var sv = Z.explain(cfg, { level: 'menu', menu: menuId, slot: ix }, ctx).values, a = step * i * Math.PI / 180;
      slots.push({ i: i, ring: 0, x: r2(Math.sin(a) * R), y: r2(-Math.cos(a) * R), size: r2(v.slot * (sv.size || 1)), shape: sv.slot_shape || 'circle', corner: sv.slot_corner === undefined ? 0.28 : sv.slot_corner,
        ang: r2(step * i), half: half, more: false });
    });
    for (var k = 1; k <= n; k++) { var g = (step * (k - 0.5)) * Math.PI / 180; gaps.push({ k: k, x: r2(Math.sin(g) * R), y: r2(-Math.cos(g) * R), ang: r2(step * (k - 0.5)) }); }
    return { scale: 1, size: [size, size], centre: [size / 2, size / 2], dead: v.dead_zone, hub: { style: v.hub_style || 'dot', r: r2((v.hub === undefined ? 10 : v.hub) / 2) },
      rings: [{ r: r2(R), first: 0, n: n, offset: 0, step: r2(step), rmin: v.dead_zone }], slots: slots, gaps: gaps,
      full: { mode: 'grow', when_full: v.when_full || 'grow', n: n, capacity: cap ? cap.capacity : n, needed: r2(cap ? cap.needed_radius : R), radius: v.radius, grown: R > v.radius + 0.5, rings: 1, more_slot: null }, fans: [] };
  }

  // 'YYYY-MM-DD HH:MM:SS.mmm' in local time, like the app's log
  function stamp(ms) {
    var d = new Date(ms), p = function (n, w) { return String(n).padStart(w || 2, '0'); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds()) + '.' + p(d.getMilliseconds(), 3);
  }
  // 40 lines: three from yesterday (dates show), then today's (time only), with "failed" lines to exercise the styling
  function mockLog() {
    var msgs = M.get_status.app_log.slice(0, 10).map(function (l) { return l.replace(/^\S+ \S+ /, ''); });
    msgs.push('bridge message failed: listener window did not answer, using the bridge key');
    msgs.push("pick #7 'Orb': message failed, fell back to the bridge key");
    var now = Date.now(), y = now - 26 * 3600e3, out = [];
    out.push(stamp(y) + ' ZOrbit started (mock)', stamp(y + 4000) + " pick #1 'hPolish': brush hPolish: selected", stamp(y + 9000) + ' ring load failed: menu tools: no usable items');
    for (var i = 0; i < 36; i++) out.push(stamp(now - (37 - i) * 6000) + ' ' + msgs[i % msgs.length]);
    out.push(stamp(now) + ' mock refresh #' + ticks);
    return out;
  }

  // --- tags: the same shapes as zorbit/webapi.py's TagApi, kept in localStorage (rm_tags) or, for ?tags=empty and ?tagsmany, in memory
  function uniq(a) { return a.filter(function (x, i) { return a.indexOf(x) === i; }); }
  function tagSlug(label) {
    var s = label.toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^[-_]+|[-_]+$/g, '');
    if (!s || !/^[a-z]/.test(s)) s = 'tag-' + s;
    return s.slice(0, 32).replace(/[-_]+$/, '') || 'tag';
  }
  function tagItemKey(k) {
    k = typeof k === 'string' ? k.replace(/\s+/g, '').toLowerCase() : '';
    return /^[a-z]+:.+$/.test(k) ? k : null;
  }
  function tagSeed() {
    var st = { tags: [], items: {} }, names = ((M.get_library && M.get_library.brushes) || []).map(function (b) { return b.name; });
    var key = function (n) { return 'brush:' + n.replace(/\s+/g, '').toLowerCase(); };
    st.tags.push({ key: FAV, label: 'Favourites', color: '#FFD166', builtin: true });          // always first
    if (tagsMode === 'empty') return st;
    if (tagsMode === 'many') {
      for (var i = 0; i < 30; i++) st.tags.push({ key: 'tag-' + (i + 1), label: (i % 3 ? 'Sculpting pass number ' : 'A rather long tag name for ') + (i + 1), color: TAG_PALETTE[i % 8] });
      names.slice(0, 40).forEach(function (n, i) { st.items[key(n)] = [st.tags[1 + i % 30].key].concat(i % 4 === 0 ? [st.tags[1 + (i + 7) % 30].key] : []); });
      return st;
    }
    st.tags.push({ key: 'blocking', label: 'Blocking', color: '#A8DF23' }, { key: 'detailing', label: 'Detailing', color: '#C77DFF' });
    names.slice(0, 12).forEach(function (n, i) {
      if (i % 6 === 5) return;
      st.items[key(n)] = i % 5 === 4 ? ['blocking', 'detailing'] : [i % 2 ? 'detailing' : 'blocking'];
    });
    [0, 3, 5, 8].forEach(function (i) { if (names[i]) st.items[key(names[i])] = (st.items[key(names[i])] || []).concat([FAV]); });   // a few stars (one on an untagged brush)
    return st;
  }
  function tagState() {
    if (tagStore) return tagStore;
    var st = null;
    if (tagsMode === 'saved') { try { st = JSON.parse(localStorage.getItem('rm_tags')); } catch (e) { st = null; } }
    if (!st || !Array.isArray(st.tags) || !st.items) st = tagSeed();
    // An older stored state has no Favourites tag: put it first. Whatever is stored, it is built in and first.
    var fav = st.tags.filter(function (t) { return t.key === FAV; })[0] || { key: FAV, label: 'Favourites', color: '#FFD166' };
    fav.builtin = true; fav.label = 'Favourites';
    st.tags = [fav].concat(st.tags.filter(function (t) { return t.key !== FAV; }));
    tagStore = st;
    return st;
  }
  function tagSave() {
    tagMtime += 1000000;
    if (tagsMode === 'saved') { try { localStorage.setItem('rm_tags', JSON.stringify(tagStore)); } catch (e) {} }
  }
  function findTag(st, key) { return st.tags.filter(function (t) { return t.key === key; })[0] || null; }
  function hasTag(st, key) { return !!findTag(st, key); }
  var BUILTIN_ERR = { ok: false, error: 'Favourites is built in' };
  function tagUnknown(key) { return { ok: false, error: "Tag '" + key + "' does not exist." }; }
  function tagDrop(st, key) {
    st.tags = st.tags.filter(function (t) { return t.key !== key; });
    Object.keys(st.items).forEach(function (ik) {
      st.items[ik] = st.items[ik].filter(function (k) { return k !== key; });
      if (!st.items[ik].length) delete st.items[ik];
    });
  }
  function tagNextColor(st) {
    var used = st.tags.map(function (t) { return t.color; });
    return TAG_PALETTE.filter(function (c) { return used.indexOf(c) < 0; })[0] || TAG_PALETTE[st.tags.length % 8];
  }
  // { label } or { err }: 1 to 40 characters, no clash (case-insensitive) with another tag; ?tagexists clashes with the first other tag
  function tagLabel(st, label, ignore) {
    label = typeof label === 'string' ? label.trim() : '';
    if (label.length < 1 || label.length > 40) return { err: { ok: false, error: 'A tag name is 1 to 40 characters.' } };
    var low = label.toLowerCase();
    var other = st.tags.filter(function (t) { return t.key !== ignore && ((q.has('tagexists') && t.key !== FAV) || t.label.toLowerCase() === low); })[0];
    if (other) return { err: { ok: false, exists: other.key, error: "A tag called '" + other.label + "' already exists." } };
    return { label: label };
  }
  function tagSnapshot() {
    var st = tagState(), count = {};
    st.tags.forEach(function (t) { count[t.key] = 0; });
    Object.keys(st.items).forEach(function (ik) { st.items[ik].forEach(function (k) { if (k in count) count[k]++; }); });
    return { ok: true, tags: st.tags.map(function (t) { var o = { key: t.key, label: t.label, color: t.color, count: count[t.key] }; if (t.key === FAV) o.builtin = true; return o; }),
      items: clone(st.items), palette: TAG_PALETTE.slice(), mtime_ns: tagMtime, path: profFolder(profiles.editing) + '\\tags.json', error: null };
  }
  // Runs one change like TagStore._change: refused under ?tagfail; written (and the time bumped) only when it says ok
  function tagChange(apply) {
    return sleep(80 + lag).then(function () {
      if (q.has('tagfail')) return { ok: false, error: 'tags.json could not be written: Access is denied (mock)' };
      var res = apply(tagState());
      if (res.ok) tagSave();
      return Object.assign(tagSnapshot(), res);
    });
  }

  /* --- usage: the same shapes as get_usage / forget_recent in webapi.py, one store per kind in localStorage (rm_usage_<kind>).
     First read: six items of the library as the recent picks (newest first, a pick every 45 minutes) and a score for 24 of them. */
  var usageMem = {}, usageMtime = 1700000000000000000;
  function usageStore(kind) {
    if (usageMem[kind]) return usageMem[kind];
    var st = null;
    try { st = JSON.parse(localStorage.getItem('rm_usage_' + kind)); } catch (e) { st = null; }
    if (!st || !Array.isArray(st.recent) || !st.scores) {
      var names = libFor(kind).items.map(function (b) { return b.name; }), now = Math.floor(Date.now() / 1000);
      st = { recent: [], scores: {}, mtime: usageMtime };
      if (q.get('usage') !== 'empty' && names.length) {
        uniq([2, 5, 9, 14, 20, 27].map(function (i) { return names[i % names.length]; })).forEach(function (n, i) {
          st.recent.push({ name: n, t: now - 90 - i * 2700, count: Math.max(1, 14 - i * 2) });
        });
        names.slice(0, 24).forEach(function (n, i) { st.scores[n.toLowerCase()] = +(((i * 7) % 19) + 1 + (i % 3) / 4).toFixed(2); });
      }
    }
    return (usageMem[kind] = st);
  }
  function usageSave(kind) {
    var st = usageMem[kind];
    usageMtime = Math.max(usageMtime, st.mtime || 0) + 1000000;       // never behind what an earlier page life saved
    st.mtime = usageMtime;
    try { localStorage.setItem('rm_usage_' + kind, JSON.stringify(st)); } catch (e) {}
  }
  function usagePayload(kind) {
    var st = usageStore(kind);
    return { ok: true, kind: kind, recent: clone(st.recent.slice(0, 24)), scores: clone(st.scores), mtime_ns: st.mtime };
  }
  // No library, no usage: ?nozbrush, ?nolib and ?liberr leave the Recent folder empty and unsaved
  function usageOff() { return q.has('nozbrush') || q.has('nolib') || q.has('liberr'); }
  function usageEmpty(kind) { return { ok: true, kind: kind, recent: [], scores: {}, mtime_ns: usageMtime }; }
  function usagePick(kind, name) {                    // a pick in the popout: to the front of Recent, and a better score
    var st = usageStore(kind), key = name.replace(/\s+/g, '').toLowerCase(), old = st.recent.filter(function (r) { return r.name.replace(/\s+/g, '').toLowerCase() === key; })[0];
    st.recent = [{ name: name, t: Math.floor(Date.now() / 1000), count: (old ? old.count : 0) + 1 }].concat(st.recent.filter(function (r) { return r !== old; })).slice(0, 24);
    st.scores[name.toLowerCase()] = +((st.scores[name.toLowerCase()] || 0) + 1).toFixed(2);
    usageSave(kind);
  }

  /* The libraries of the four kinds. Brushes are the recording; an alpha, material or texture library is M.get_library_<kind> when one was
     recorded ({items|brushes, categories}), else made from the first 48 recorded brushes: the same pictures under new names. */
  var ASSET_KIND = {
    brush: { suffix: '', ext: '.ZBP', cats: null,
      sources: [{ label: 'ZBrush 2026 brush presets', path: 'C:\\Users\\you\\Documents\\ZBrush 2026 Assets\\ZStartup\\BrushPresets', exists: true },
                { label: 'ZBrush 2022 brush presets', path: 'C:\\Program Files\\Maxon ZBrush 2022\\ZStartup\\BrushPresets', exists: false }] },
    alpha: { suffix: ' Alpha', ext: '.psd', cats: ['My Alphas', 'ZBrush', 'Lightbox/HardSurfaceAlphas'],
      sources: [{ label: 'ZBrush 2026 alphas', path: 'C:\\Users\\you\\Documents\\ZBrush 2026 Assets\\ZStartup\\Alphas', exists: true },
                { label: 'ZBrush 2022 alphas', path: 'C:\\Program Files\\Maxon ZBrush 2022\\ZStartup\\Alphas', exists: false }] },
    material: { suffix: ' Mat', ext: '.zmt', cats: ['My Materials', 'ZBrush/MatCap', 'Lightbox/Standard'],
      sources: [{ label: 'ZBrush 2026 materials', path: 'C:\\Users\\you\\Documents\\ZBrush 2026 Assets\\ZStartup\\Materials', exists: true },
                { label: 'ZBrush 2022 materials', path: 'C:\\Program Files\\Maxon ZBrush 2022\\ZStartup\\Materials', exists: false }] },
    texture: { suffix: ' Tex', ext: '.psd', cats: ['My Textures', 'ZBrush', 'Lightbox/Panoramas'],
      sources: [{ label: 'ZBrush 2026 textures', path: 'C:\\Users\\you\\Documents\\ZBrush 2026 Assets\\ZStartup\\Textures', exists: true },
                { label: 'ZBrush 2022 textures', path: 'C:\\Program Files\\Maxon ZBrush 2022\\ZStartup\\Textures', exists: false }] }
  };
  var libCache = {};
  function libFor(kind) {
    if (libCache[kind]) return clone(libCache[kind]);
    var out, rec = M['get_library_' + kind], A = ASSET_KIND[kind];
    if (kind === 'brush') {
      var b = clone(M.get_library);
      out = { items: b.brushes, categories: b.categories };
    } else if (rec) {
      var r = clone(rec);
      out = { items: r.items || r.brushes || [], categories: r.categories || [] };
    } else {
      var items = ((M.get_library && M.get_library.brushes) || []).slice(0, 48).map(function (b, i) {
        var cat = A.cats[i % A.cats.length], name = b.name + A.suffix;
        return { name: name, source: cat.split('/')[0], category: cat, path: 'C:\\Users\\you\\ZBrush Assets\\' + cat.replace(/\//g, '\\') + '\\' + name + A.ext };
      });
      var counts = {};
      items.forEach(function (it) { counts[it.category] = (counts[it.category] || 0) + 1; });
      out = { items: items, categories: Object.keys(counts).map(function (id) { return { id: id, count: counts[id] }; }) };
    }
    libCache[kind] = out;
    return clone(out);
  }

  /* ---- Setup screen: one small model of ZBrush, the plugin and the app, read by get_status, get_setup and get_zscript_bridge */
  var zbMode = q.get('zb') || 'both';                       // 2026 | 2022 | both | none | multi
  var zbRunning = function () { return q.get('zbrun') !== 'off' && q.get('status') !== 'down' && !q.has('nocheck') && zbMode !== 'none'; };
  // By default the app runs along with ZBrush. ?appoff, ?startfail and a ?status other than up leave it off until Start app succeeds.
  var appRunning = function () { return zbRunning() && (appStarted || q.get('status') === 'up' || !(q.has('appoff') || q.has('startfail') || q.has('status'))); };
  var firstDone = false, firstRun = function () { return q.has('firstrun') && !firstDone; };   // ?firstrun holds until Finish or Skip in this page; a reload starts it again
  var tourDone = false;   // ?firstrun offers the tour (tour_seen false) until set_pref('tour_seen', true) in this page
  // Under ?firstrun or ?mode= the Studio mode lives only in this page (else one ?firstrun visit would flip every later
  // page to Simple): set_pref keeps it here and every reply reports it, so the app's merge of a reply cannot undo it.
  var pageMode = null;
  // The theme: stored in rm_prefs like the mode; an explicit ?theme= keeps it in this page only, so a reload goes back to the switch.
  var THEMES = ['dark', 'light', 'system', 'zbrush'], pageTheme = null;
  // Match ZBrush: a fixed sample scheme (the stock ZBrush grey). ?zbnone means ZBrush has stored nothing, so zbrush resolves to dark.
  var ZB_TOKENS = { '--bg0': '#1a1a1a', '--bg1': '#242424', '--bg2': '#3e3e3e', '--bg3': '#444444', '--text': '#e9eceb', '--sub': '#b8bab9', '--muted': '#b8bab9',
    '--accent': '#ff7700', '--on-accent': '#141416', '--cyan': '#4dc8e9' };
  var ZB_RING = { bg: '#444444', accent: '#ff7700', highlight: '#4dc8e9', text: '#e9eceb', lines: '#ff7700' };
  var ZB_SOURCE = { year: 2022, path: '%PUBLIC%\\Documents\\ZBrushData2022\\ZStartup\\CustomUserInterface2022.cfg', stored: 1793053562 };
  var zbNone = function () { return q.has('zbnone'); };
  var THEME_RING = { dark: { bg: '#222327', accent: '#f86b33', highlight: '#4dc8e9', text: '#f0f0f0', lines: '#f86b33' },     // as theme.py's PRESETS, for a recording that has none
    light: { bg: '#f3f4f6', accent: '#a8360f', highlight: '#066785', text: '#1b1c20', lines: '#a8360f' } };
  function themeSetting() {
    var t = pageTheme !== null ? pageTheme : (q.get('theme') || (function () { try { return JSON.parse(localStorage.getItem('rm_prefs') || '{}').theme; } catch (e) { return null; } })());
    return THEMES.indexOf(t) >= 0 ? t : 'dark';
  }
  function themeEff() {
    var t = themeSetting();
    if (t === 'zbrush') return zbNone() ? 'dark' : 'zbrush';
    if (t !== 'system') return t;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  function themeBase() { var e = themeEff(); return e === 'zbrush' ? 'dark' : e; }
  // theme_sig changes when ZBrush stores a new scheme; the mock's never does.
  function themeOf(p) {
    var e = themeEff(), s = themeSetting();
    p.theme = s; p.theme_effective = e; p.theme_base = themeBase();
    p.theme_tokens = e === 'zbrush' ? clone(ZB_TOKENS) : {};
    p.theme_sig = e + ':' + (e === 'zbrush' ? 'sample' : '');
    p.theme_source = s === 'zbrush' && !zbNone() ? clone(ZB_SOURCE) : null;
    return p;
  }
  function themeRing() {
    var r = clone(((M.get_options || {}).theme_ring_colors) || THEME_RING);
    if (!zbNone()) r.zbrush = clone(ZB_RING);
    return r;
  }
  var lightPics = function () { return themeEff() === 'light'; };
  function modeOf(p) { if (pageMode !== null) p.mode = pageMode; else if (q.get('mode')) p.mode = q.get('mode'); else if (firstRun()) p.mode = ''; return p; }
  var lsGet = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var envRegistered = function () { return !q.has('noenv') || lsGet('rm_env') === '1'; };
  var bridgeOk = function () { return !q.has('nobridge'); };
  var BRIDGE_DIR = 'C:\\Program Files\\ZOrbit\\bridge';
  var zbStartedAt = Date.now() / 1000 - 600;                 // the mock's ZBrush started ten minutes before the page opened
  var zInstalledNow = false, fixedAt = 0;                   // the plugin was installed / the folder registered during this page's life: a running ZBrush predates it
  var bridgeMode = function () { return q.get('bridgemode') || (saved.bridge && saved.bridge.mode) || 'auto'; };
  var MODERN = [{ name: 'ZBrush 2026', year: 2026, path: 'C:\\Program Files\\Maxon ZBrush 2026', python: true, added: false },
    { name: 'ZBrush 2027', year: 2027, path: 'C:\\Program Files\\Maxon ZBrush 2027', python: true, added: false }];
  var HAND_ADDED = { name: 'ZBrush 2027', year: 2027, path: 'D:\\Apps\\ZBrush 2027', python: true, added: true };
  var modernInstalls = function () {
    var base = zbMode === 'none' || zbMode === '2022' ? [] : (zbMode === 'multi' ? MODERN : MODERN.slice(0, 1));
    return modernAdded ? base.concat([HAND_ADDED]) : base;
  };
  // The ZScript installs (ZBrush 2022 to 2025): what Settings > Older ZBrush lists, and what Setup shows for those versions
  function zsInstalls() {
    var z = JSON.parse(lsGet('rm_zscript') || '{}');
    var forgotten = JSON.parse(lsGet('rm_zforgot') || '{}');
    var installs = [
      { name: 'ZBrush 2022', year: 2022, path: 'C:\\Programs\\ZBrush 2022', python: false, installed: !!z.a, current: !!z.a, added: true, zplugs: 'C:\\Programs\\ZBrush 2022\\ZStartup\\ZPlugs64' },
      { name: 'ZBrush 2024', year: 2024, path: 'C:\\Program Files\\Maxon ZBrush 2024', python: false, installed: true, current: false, added: false, zplugs: 'C:\\Program Files\\Maxon ZBrush 2024\\ZStartup\\ZPlugs64' }];
    if (q.has('nozs') || zbMode === 'none' || zbMode === '2026') installs = [];
    else if (zbMode === '2022') installs = installs.slice(0, 1);
    return installs.filter(function (i) { return !(i.added && forgotten[i.path]); });
  }
  var act = { ring: null, pick: null }, lastPick = null, pickSeq = 0, seeded = false, autoStarted = false;
  var pickRoute = function () { var i = runningInstalls()[0]; return bridgeMode() === 'key' ? 'key' : (i && i.kind === 'legacy' ? 'zscript' : 'listener'); };
  // The activity the daemon would write: stage 'open' (ring shown), 'pick' (a brush sent), 'ack' (ZBrush did it)
  function ringStage(stage, at) {
    var t = at || Date.now() / 1000;
    if (stage === 'open') { act.ring = { at: t, menu: 'brushes' }; act.pick = null; lastPick = null; return; }
    if (stage === 'pick') {
      if (!act.ring) act.ring = { at: t - 0.4, menu: 'brushes' };
      act.pick = { at: t, seq: ++pickSeq, menu: 'brushes', kind: 'brush', label: 'ClayBuildup', route: pickRoute(), sent: true, reason: null, source: 'ring', ack: null };
      return;
    }
    if (stage === 'ack') {
      if (!act.pick) ringStage('pick', t - 0.3);
      act.pick.ack = 'picked_up';
      lastPick = { text: "brush ClayBuildup: selected", at: t, seq: act.pick.seq, ok: true, source: 'ring' };
    }
  }
  var STAGES = ['open', 'pick', 'ack'];
  window.__mock = { ring: function (stage) { if (STAGES.indexOf(stage) < 0) { console.warn('[mock] ring(stage): open | pick | ack'); return; } ringStage(stage); } };
  // Which installs have a ZBrush running: the first (two with ?zb=multi)
  function runningInstalls() {
    if (!zbRunning()) return [];
    var all = modernInstalls().map(function (i) { return Object.assign({ kind: 'modern' }, i); }).concat(zsInstalls().map(function (i) { return Object.assign({ kind: 'legacy' }, i); }));
    return all.slice(0, zbMode === 'multi' ? 2 : 1);
  }
  function setupSnapshot() {
    var now = Date.now() / 1000, reg = envRegistered(), ok = bridgeOk(), started = zbStartedAt, keyMtime = fixedAt || zbStartedAt - 86400;
    var running = runningInstalls(), ids = running.map(function (i) { return i.path; });
    var installs = modernInstalls().map(function (i) {
      return Object.assign({ kind: 'modern', plugin: { state: !ok ? 'no_bridge' : reg ? 'ok' : 'unregistered' }, ready: reg && ok, procs: [] }, i);
    }).concat(zsInstalls().map(function (z) {
      return { name: z.name, year: z.year, path: z.path, python: false, added: z.added, kind: 'legacy', ready: z.installed, procs: [],
        plugin: { state: !z.installed ? 'missing' : (z.current ? 'ok' : 'outdated'), installed: z.installed, current: z.current, zplugs: z.zplugs } };
    }));
    var unmatched = [], loadedPid = null;
    installs.forEach(function (inst) {
      if (ids.indexOf(inst.path) < 0) return;
      var pid = 4000 + installs.indexOf(inst) * 100, state, why = '', evidence = '';
      if (q.has('elevated') && !unmatched.length) { unmatched.push({ pid: pid, started: started, elevated: true, loaded: q.get('elevated') === 'loaded' }); return; }
      if (q.has('zbstart')) { state = 'starting'; why = 'This ZBrush started a moment ago. The plugin loads with it.'; }
      else if (q.has('zbstale')) { state = 'restart'; why = 'This ZBrush started before the plugin was set up. Restart it.'; }
      else if (q.has('noloaded')) { state = 'not_loaded'; why = 'ZBrush has not loaded the plugin. Close it completely and start it from the Start menu, not from a program that was already open. If that does not help, read bridge.log in the logs folder, if it exists.'; }
      else if (inst.kind === 'modern') {
        if (!ok) { state = 'not_loaded'; why = 'The plugin folder is missing.'; }
        else if (!reg) { state = 'not_loaded'; why = 'ZBrush does not know where the plugin is. Press Fix in step 1, then restart ZBrush.'; }
        else if (keyMtime > started) { state = 'restart'; why = 'This ZBrush started before the plugin was set up. Restart it.'; }
        else { state = 'loaded'; loadedPid = pid; evidence = 'listener.json'; }
      } else if (!inst.ready) { state = 'not_loaded'; why = 'The ZOrbit plugin is not installed in this ZBrush. Press Install in step 1, then restart ZBrush.'; }
      else if (zInstalledNow && inst.path === 'C:\\Programs\\ZBrush 2022') { state = 'restart'; why = 'This ZBrush started before the plugin was installed. Restart it.'; }
      else { state = 'loaded'; evidence = 'zscript_hotkey.log'; }
      inst.procs.push({ pid: pid, started: started, age: now - started, state: state, evidence: evidence, why: why });
    });
    var hard = [];
    if (installs.length && !installs.some(function (i) { return i.ready; })) hard.push('No ZBrush install is set up for ZOrbit.');
    installs.forEach(function (i) { if (i.procs.length && !i.ready) hard.push('A running ' + i.name + ' is not set up for ZOrbit.'); });
    var other = q.has('otherbridge') ? [{ path: 'D:\\Projects\\zOrbit\\bridge', exists: true }, { path: 'C:\\Old\\ZOrbit\\bridge', exists: false }] : [];
    var entries = (reg ? [BRIDGE_DIR] : []).concat(other.map(function (o) { return o.path; }));
    return {
      now: now, checked_at: now,
      bridge: { dir: ok ? BRIDGE_DIR : null, dir_ok: ok, kind: ok ? 'installed' : 'missing' },
      env: { registered: reg, entries: entries, other_zorbit: other, key_mtime: keyMtime, can_fix: !reg && ok },
      installs: installs, unmatched_procs: unmatched,
      zbrush: { running: zbRunning(), check_ok: !q.has('nocheck') },
      listener: loadedPid ? { verified: now - 100, alive: true, pid: loadedPid, stale: false } : null,
      app: { running: appRunning() },
      bridge_mode: bridgeMode(), bundled: true,
      activity: act.ring || act.pick ? clone({ v: 1, pid: 4242, started: now - 900, opens: act.ring ? 1 : 0, picks: act.pick ? 1 : 0, ring: act.ring, pick: act.pick }) : null,
      last_pick: lastPick ? clone(lastPick) : null,
      hard_fail: hard.length > 0, hard_reasons: hard };
  }
  // ?ringtried and ?ringauto start from the moment the Setup screen is first built, so the events fall after its "try from" time
  function setupTimers() {
    var S = window.__studio && window.__studio.S, from = S && S.setup && S.setup.tryFrom;
    if (!from) return;
    var tried = q.get('ringtried');
    if (tried && !seeded) {
      seeded = true;
      ringStage('open', from + 0.05);
      if (tried === 'sent' || tried === 'done') ringStage('pick', from + 0.1);
      if (tried === 'done') ringStage('ack', from + 0.15);
    }
    if (q.has('ringauto') && !autoStarted && runningInstalls().length && pluginLoaded()) {
      autoStarted = true;
      setTimeout(function () { ringStage('open'); }, 2000);
      setTimeout(function () { ringStage('pick'); }, 4000);
      if (bridgeMode() !== 'key') setTimeout(function () { ringStage('ack'); }, 6000);    // key mode: the key is "not bound", so ZBrush never answers and the hint shows
    }
  }
  var pluginLoaded = function () { return setupSnapshot().installs.some(function (i) { return i.procs.some(function (p) { return p.state === 'loaded'; }); }); };

  var api = {
    get_config: function (profile) {
      return sleep(40).then(function () {
        if (q.has('toonew')) return Object.assign({ config: null, too_new: true, error: 'These files were made by ZOrbit 9.9.9, which is newer than this one (0.18.1). Install ZOrbit 9.9.9 or newer.', path: 'C:\\Users\\you\\AppData\\Roaming\\ZOrbit\\radial.json', backup_exists: false, problems: [], mtime_ns: null }, profInfo());
        if (typeof profile === 'string' && profile) {              // like the backend: asking for a profile makes it the one the editor holds
          var want = profFind(profile);
          if (want === null) return Object.assign({ config: null, error: 'There is no profile called ' + profile + '.', path: '', backup_exists: false, problems: [], mtime_ns: null }, profInfo());
          if (want !== profiles.editing) { profiles.editing = want; saved = clone(profiles.saved[want]); }
        }
        var r = clone(M.get_config);
        r.config = clone(saved);                                   // what the last mock save wrote, so Reload from disk is honest
        r.defaults = Object.assign({}, r.defaults, TAG_DEFAULTS, { colors: themeRing()[themeEff()] });
        Object.assign(r, profInfo());
        if (profiles.editing !== P0) r.path = profFolder(profiles.editing) + '\\radial.json';
        if (q.has('broken') && !sessionStorage.getItem('rm_repaired')) return Object.assign({ config: null, error: BROKEN_ERR, path: r.path, backup_exists: true, problems: [], mtime_ns: null }, profInfo());
        var bad = q.get('badmenus');
        if (bad && r.config.menus) {
          var ids = Object.keys(r.config.menus), id = ids[ids.length - 1];
          if (bad === 'null') r.config.menus[id] = null;
          else if (bad === 'noitems') delete r.config.menus[id].items;
          else if (bad === 'string') r.config.menus[id] = 'oops';
          else if (bad === 'items') r.config.menus[id].items.push(null);
        }
        r.problems = q.has('problems') ? validate(r.config) : r.problems;
        r.mtime_ns = mtime; r.backup_exists = true;
        return r;
      });
    },
    validate: function (cfg) { return sleep(30).then(function () { return { problems: validate(cfg) }; }); },
    save_config: function (cfg, mtime_ns, force, allow_unusable, profile) {
      return sleep(180).then(function () {
        if (q.has('profilegone') && !profileGoneDone && profiles.names.length > 1) {      // somebody deleted this profile while Studio was open
          profileGoneDone = true;
          var gone = profFind(profile || profiles.editing);
          profiles.names = profiles.names.filter(function (x) { return x !== gone; });
          if (profiles.active === gone) profiles.active = profiles.names[0];
        }
        var target = profile ? profFind(profile) : profiles.editing;
        if (profile && target === null) return { saved: false, profile_missing: true, message: 'The profile ' + profile + ' no longer exists.' };
        if (q.has('conflict') && !force && !conflictDone) {
          conflictDone = true; mtime += 1000000;
          return { saved: false, conflict: true, message: 'radial.json was changed on disk after Studio loaded it (mock).', mtime_ns: mtime };
        }
        if (q.has('blocked') && !allow_unusable) {
          return { saved: false, blocked: true, problems: ['menu brushes: no usable items', 'no menu has a hotkey, so nothing can open the ring'],
            message: 'Saving this would leave no ring that can open, so ZOrbit would stop working.' };
        }
        profiles.saved[target] = clone(cfg);
        if (target === profiles.editing) saved = clone(cfg);
        mtime += 1000000;
        var kept = q.has('keptbroken') && !keptDone; keptDone = true;
        return { saved: true, problems: validate(cfg), time: Date.now() / 1000, mtime_ns: mtime, kept_broken: kept };
      });
    },
    // Both mark the file as repaired for this tab, so the reload after them boots normally even with ?broken.
    restore_backup: function () { try { sessionStorage.setItem('rm_repaired', '1'); } catch (e) {} return sleep(200).then(function () { return { ok: true, kept_broken: true, message: 'Restored radial.json from radial.json.bak. The file it replaced is kept as radial.json.broken.' }; }); },
    reset_config: function () { try { sessionStorage.setItem('rm_repaired', '1'); } catch (e) {} return sleep(200).then(function () { return { ok: true, message: 'Started again from the default menus. The old file is kept as radial.json.broken.' }; }); },
    // Profiles. The editor holds `editing`, the app uses `active`; switching moves both.
    get_profiles: function () { return sleep(40).then(function () { return { ok: true, enabled: profilesOn, active: profiles.active, editing: profiles.editing, names: profiles.names.slice() }; }); },
    switch_profile: function (name) {
      var want = profFind(name);
      if (want === null) return sleep(80).then(function () { return { ok: false, message: 'There is no profile called ' + name + '.' }; });
      profiles.active = want;
      return api.get_config(want).then(function (r) { r.ok = true; return r; });
    },
    pick_profile_file: function () {
      return sleep(150).then(function () {
        if (q.has('importcancel')) return { ok: false, cancelled: true };
        if (q.has('importfail')) return { ok: false, message: "That file is not valid JSON: Expecting ',' delimiter: line 12 column 5 (mock)." };
        var name = 'Imported', k = 2;
        while (profFind(name) !== null) name = 'Imported ' + k++;
        pickedFile = true;
        return { ok: true, path: 'C:\\Users\\you\\Downloads\\ZOrbit settings.json', name: name, menus: 3, has_tags: true, tags: 4, problems: [], version: '0.18.1' };
      });
    },
    create_profile: function (name, source) {
      return sleep(120).then(function () {
        var bad = profNameProblem(name, null);
        if (bad) return { ok: false, message: bad };
        if (['starter', 'empty', 'copy', 'file'].indexOf(source) < 0) return { ok: false, message: 'Unknown starting point: ' + source };
        if (source === 'file' && !pickedFile) return { ok: false, message: 'Pick a file first.' };
        var n = name.trim(), cfg;
        if (source === 'empty') cfg = { menus: {} };
        else if (source === 'copy') cfg = clone(profiles.saved[profiles.editing]);
        else if (source === 'file') cfg = profTitle(clone(M.get_config.config), n);
        else cfg = clone(M.get_config.config);
        profiles.names.push(n); profSort(); profiles.saved[n] = cfg;
        return { ok: true, name: n, names: profiles.names.slice(), active: profiles.active, editing: profiles.editing, message: 'Created the profile ' + n + '.' };
      });
    },
    rename_profile: function (old, name) {
      return sleep(120).then(function () {
        var from = profFind(old);
        if (from === null) return { ok: false, message: 'There is no profile called ' + old + '.' };
        var bad = profNameProblem(name, from);
        if (bad) return { ok: false, message: bad };
        var n = name.trim();
        profiles.names = profiles.names.map(function (x) { return x === from ? n : x; }); profSort();
        profiles.saved[n] = profiles.saved[from]; if (n !== from) delete profiles.saved[from];
        if (profiles.active === from) profiles.active = n;
        if (profiles.editing === from) profiles.editing = n;
        return { ok: true, name: n, names: profiles.names.slice(), active: profiles.active, editing: profiles.editing, message: 'Renamed ' + from + ' to ' + n + '.' };
      });
    },
    delete_profile: function (name) {
      return sleep(150).then(function () {
        var gone = profFind(name);
        if (gone === null) return { ok: false, message: 'There is no profile called ' + name + '.' };
        if (profiles.names.length < 2) return { ok: false, message: 'The last profile cannot be deleted.' };
        profiles.names = profiles.names.filter(function (x) { return x !== gone; });
        delete profiles.saved[gone];
        var reload = gone === profiles.editing;
        if (profiles.active === gone) profiles.active = profiles.names[0];
        if (reload) { profiles.editing = profiles.active; saved = clone(profiles.saved[profiles.editing]); }
        return { ok: true, reload: reload, names: profiles.names.slice(), active: profiles.active, editing: profiles.editing, message: 'Deleted the profile ' + gone + '. Its files stay in profiles\\.deleted for 30 days.' };
      });
    },
    // Export and import: the picked file is a made-up bundle. ?importfail refuses it, ?importcancel is a closed dialog, ?importtags a tags-only file.
    export_settings: function (cfg) {
      return sleep(150).then(function () {
        if (q.has('importcancel')) return { ok: false, cancelled: true };
        return { ok: true, path: 'C:\\Users\\you\\Documents\\ZOrbit settings 2026-10-30.json', message: 'Exported ' + Object.keys((cfg && cfg.menus) || {}).length + ' menus and the tags to ZOrbit settings 2026-10-30.json (mock).' };
      });
    },
    pick_import: function () {
      return sleep(150).then(function () {
        if (q.has('importcancel')) return { ok: false, cancelled: true };
        if (q.has('importfail')) return { ok: false, message: "That file is not valid JSON: Expecting ',' delimiter: line 12 column 5 (mock)." };
        var tagsOnly = q.has('importtags'), noTags = q.has('importnotags') && !tagsOnly, n = Object.keys(saved.menus || {}).length;
        return { ok: true, path: 'C:\\Users\\you\\Documents\\ZOrbit settings 2026-10-30.json', kind: tagsOnly ? 'tags' : noTags ? 'config' : 'bundle', has_config: !tagsOnly, menus: tagsOnly ? 0 : n,
          current_menus: n, has_tags: !noTags, tags: noTags ? 0 : 4, new_tags: noTags ? 0 : 2, current_tags: tagState().tags.length, items: noTags ? 0 : 17, problems: tagsOnly || !q.has('problems') ? [] : validate(saved), version: '0.18.1' };
      });
    },
    apply_import: function (tag_mode) {
      return sleep(200).then(function () {
        var tagsOnly = q.has('importtags'), msg = '';
        if (q.has('importnotags') && !tagsOnly) tag_mode = 'none';
        if (tag_mode === 'merge' || tag_mode === 'replace') {
          var st = tagState();
          if (tag_mode === 'replace') { st.tags = st.tags.filter(function (t) { return t.key === FAV; }); st.items = {}; }   // Favourites is built in: it stays
          ['blocking', 'detailing', 'imported-a', 'imported-b'].forEach(function (k, i) {
            if (!hasTag(st, k)) st.tags.push({ key: k, label: k.replace('-', ' '), color: tagNextColor(st) });
          });
          tagSave();
          msg = tag_mode === 'merge' ? 'Merged the tags: 2 added.' : 'Replaced the tags with the 4 in the file.';
        }
        if (tagsOnly) return { ok: true, config: null, problems: [], tags_message: msg };
        var cfg = clone(saved);                                   // a visible change: another accent colour
        cfg.ring = Object.assign({}, cfg.ring); cfg.ring.colors = Object.assign({}, cfg.ring.colors, { accent: '#4dc8e9', lines: '#4dc8e9' });
        return { ok: true, config: cfg, problems: q.has('problems') ? validate(cfg) : [], tags_message: msg };
      });
    },
    // Share one menu: the made-up file holds "Sculpt" and its submenu "Brushes", which the recorded config has too, so the preview shows renames.
    export_menu: function (cfg, menu_id) {
      return sleep(150).then(function () {
        if (q.has('importcancel')) return { ok: false, cancelled: true };
        var m = cfg && cfg.menus && cfg.menus[menu_id];
        if (!m) return { ok: false, message: 'There is no menu "' + menu_id + '" to export.' };
        return { ok: true, path: 'C:\\Users\\you\\Documents\\' + (m.title || menu_id) + ' menu.json', message: 'Saved "' + (m.title || menu_id) + '" to ' + (m.title || menu_id) + ' menu.json (mock).' };
      });
    },
    pick_menu_import: function (cfg) {
      return sleep(150).then(function () {
        if (q.has('importcancel')) return { ok: false, cancelled: true };
        if (q.has('importfail')) return { ok: false, message: 'Sculpt menu.json is not a ZOrbit menu file.' };
        var plan = menuImportPlan(cfg);
        return { ok: true, path: 'C:\\Users\\you\\Documents\\Sculpt menu.json', version: '0.18.1', root: plan.root, title: plan.menus[plan.root].title,
          menus: Object.keys(plan.menus).map(function (id) { return { id: id, title: plan.menus[id].title, items: plan.menus[id].items.length }; }), renames: plan.renames,
          tags: 2, new_tags: 1, tagged_items: 3, missing: { brush: ['OrbCracks', 'TrimSmooth'] }, problems: [] };
      });
    },
    apply_menu_import: function (cfg) {
      return sleep(200).then(function () {
        var plan = menuImportPlan(cfg), st = tagState();
        if (!hasTag(st, 'rock')) { st.tags.push({ key: 'rock', label: 'Rock', color: tagNextColor(st) }); tagSave(); }
        return { ok: true, menus: plan.menus, root: plan.root, title: plan.menus[plan.root].title, problems: [], tags_message: 'Added 1 tag to yours; 1 matched a tag you have by name.',
          message: 'Imported the menu.' };
      });
    },
    preview_tags: function () {                                   // the backend's sample ring; the recorded data has it once regenerated
      return sleep(60 + lag).then(function () {
        var res = clone((lightPics() && M.preview_tags_light) || M.preview_tags || M.preview_ring[Object.keys(M.preview_ring)[0]]);
        res.width = res.height = res.size; res.centre = [res.size / 2, res.size / 2];
        if (!res.layout) delete res.layout;                       // the recording of an older backend has none: no overlay
        return res;
      });
    },
    preview_ring: function (cfg, menuId, hover, scale, openPath) {
      return sleep(60 + lag).then(function () {
        var m = cfg && cfg.menus && cfg.menus[menuId];
        if (!m || !(m.items || []).length) return { image: null, problems: ['menu ' + menuId + ' has no usable items'] };
        var pics = (lightPics() && M.preview_ring_light) || M.preview_ring, hov0 = (lightPics() && M.preview_ring_hover0_light) || M.preview_ring_hover0;
        var res = clone((hover === 0 && menuId === 'brushes' && hov0) || pics[menuId] || pics.brushes || M.preview_ring[menuId] || M.preview_ring.brushes);
        res.width = res.height = res.size; res.centre = [res.size / 2, res.size / 2];
        res.fit = mockFit(cfg, menuId);
        res.layout = mockLayout(cfg, menuId, res) || undefined;
        var it = openPath && openPath.length ? usable(m)[openPath[0]] : null, sub = it && it.menu ? cfg.menus[it.menu] : null;
        if (it && it.tag) {                                          // a tag slot with brushes is a fan of them, like the expander makes
          var tn = (tagSnapshot().tags.filter(function (t) { return t.key === it.tag; })[0] || {}).count || 0;
          if (tn) sub = { fan: true, items: new Array(Math.min(tn, 12)) };
        }
        if (!(sub && sub.fan === true && it.menu !== menuId)) return res;
        // No Python here: a fan is faked as a wider canvas with the ring on the left and dashed lines to a few discs on the right
        return new Promise(function (resolve) {
          var base = new Image();
          base.onload = function () {
            var s = res.size, w = Math.round(s * 1.5), c = document.createElement('canvas'), g;
            c.width = w; c.height = s; g = c.getContext('2d');
            g.drawImage(base, 0, 0);
            var n = Math.min(Math.max((sub.items || []).length, 1), 5), ax = s / 2, ay = s / 2;
            g.strokeStyle = 'rgba(255,255,255,.35)'; g.fillStyle = '#2b2c31'; g.setLineDash([4, 4]); g.lineWidth = 1.5;
            for (var i = 0; i < n; i++) {
              var a = (n === 1 ? 0 : -0.9 + (1.8 * i) / (n - 1)), x = s * 0.95 + Math.cos(a) * s * 0.3, y = ay + Math.sin(a) * s * 0.34;
              g.beginPath(); g.moveTo(ax, ay); g.lineTo(x, y); g.stroke();
              g.beginPath(); g.arc(x, y, 24, 0, 6.2832); g.fill(); g.setLineDash([]); g.stroke(); g.setLineDash([4, 4]);
            }
            res.image = c.toDataURL('image/png'); res.size = w; res.width = w; res.height = s; res.centre = [s / 2, s / 2];
            resolve(res);
          };
          base.onerror = function () { resolve(res); };
          base.src = res.image;
        });
      });
    },
    preview_animation: function (cfg, menuId) {
      return sleep(350 + lag).then(function () { return (lightPics() && M.preview_animation_light) || M.preview_animation; });
    },
    get_options: function () { return sleep(10).then(mockOptions); },
    // The look previews: the recorded pictures of each built-in look when there are some, else the plain ring picture (a user look has no picture of its own here).
    preview_look: function (cfg, preset) {
      return sleep(60 + lag).then(function () { var out = lookPic(preset); out.problems = []; return out; });
    },
    preview_looks: function (cfg, names) {
      return sleep(120 + lag).then(function () {
        var ctx = mockCtx(), known = ctx.looks.builtin.map(function (b) { return b.id; }).concat(Object.keys((cfg && cfg.looks) || {})), out = {};
        (names || known).forEach(function (n) { if (known.indexOf(n) >= 0) out[n] = lookPic(n); });
        return { looks: out, problems: [] };
      });
    },
    resolve_look: function (cfg, menuId, slot) {
      return sleep(30).then(function () {
        var ctx = mockCtx(), Z = window.ZLook, t = menuId ? (slot === null || slot === undefined ? { level: 'menu', menu: menuId } : { level: 'menu', menu: menuId, slot: slot }) : { level: 'global' };
        var ex = Z.explain(cfg, t, ctx), name = slot === null || slot === undefined ? Z.presetOf(cfg, t) : '';
        return { values: ex.values, origins: ex.origins, preset: name ? { name: name, builtin: ctx.looks.builtin.some(function (b) { return b.id === name; }) } : null,
          fit: menuId ? mockFit(cfg, menuId) : null, problems: Z.problems(cfg, ctx) };
      });
    },
    get_library: function (refresh, kind, since) {
      kind = ASSET_KIND[kind] ? kind : 'brush';
      var libCalls = (libSeq[kind] = (libSeq[kind] || 0) + 1);
      return sleep(refresh ? 700 : 250).then(function () {
        var A = ASSET_KIND[kind], lib = libFor(kind), n = lib.items.length;
        var sig = 'mock-' + kind + '-' + n + (q.get('libsig') === 'changing' ? '-' + libCalls : '');       // like the backend: a hash of what was found
        if (since && since === sig && !q.has('liberr') && !q.has('nozbrush') && !q.has('nolib')) {
          console.log('[mock] get_library', kind, 'unchanged');
          return { kind: kind, unchanged: true, signature: sig, sources: A.sources.map(function (src, i) { return { label: src.label, path: src.path, exists: src.exists, count: i === 0 ? n : 0 }; }), zbrush_found: true, error: null };
        }
        var sources = A.sources.map(function (src, i) { return { label: src.label, path: src.path, exists: src.exists, count: i === 0 ? n : 0 }; });
        if (q.has('liberr')) return { kind: kind, items: [], brushes: [], categories: [], sources: [], zbrush_found: true, error: 'Could not read the ' + kind + ' folders: [WinError 5] Access is denied (mock)' };
        if (q.has('nozbrush')) return { kind: kind, items: [], brushes: [], categories: [], sources: [], zbrush_found: false, error: null };
        if (q.has('nolib')) { sources[0].count = 0; return { kind: kind, items: [], brushes: [], categories: [], sources: sources, zbrush_found: true, error: null }; }
        var out = { kind: kind, items: lib.items, categories: lib.categories, sources: sources, zbrush_found: true, error: null, signature: sig };
        if (kind === 'brush') out.brushes = lib.items;      // the alias the backend keeps for one release
        return out;
      });
    },
    get_thumbs: function (names, size, kind) {
      kind = ASSET_KIND[kind] ? kind : 'brush';
      console.log('[mock] get_thumbs', (names || []).length, kind, 'names, size', size);
      if (q.has('thumbfail') && ++thumbCalls <= 2) return sleep(70).then(function () { throw new Error('thumbnail service unavailable (mock)'); });
      return sleep(70).then(function () {
        var out = {}, own = M['get_thumbs_' + kind], suffix = ASSET_KIND[kind].suffix;
        (names || []).forEach(function (n) {
          var v = null;
          if (kind === 'brush') v = (M.get_thumbs && M.get_thumbs[n]) || null;
          else if (own && own[n]) v = own[n];
          else if (!own || !(n in own)) {                  // a synthesised name: the picture of the brush it was made from
            var base = n.length > suffix.length && n.slice(-suffix.length) === suffix ? n.slice(0, -suffix.length) : null;
            v = (base && M.get_thumbs && M.get_thumbs[base]) || null;
          }
          out[n] = v;
        });
        return out;
      });
    },
    get_tag_uses: function () {           // the popout's tag manager: ring items that use each tag, from radial.json
      var uses = {};
      Object.keys(saved.menus || {}).forEach(function (id) { (saved.menus[id].items || []).forEach(function (it) {
        var k = typeof it.tag === 'string' && it.tag ? it.tag : typeof it.browser === 'string' && it.browser ? it.browser : null;
        if (k) uses[k] = (uses[k] || 0) + 1; }); });
      return sleep(30).then(function () { return { ok: true, uses: uses }; });
    },
    get_tags: function (since, since_path) {
      return sleep(40).then(function () {
        // unchanged only for the same file: the path travels with the time, so a switch to another profile is a change
        if (since !== null && since !== undefined && since === tagMtime && (since_path === undefined || since_path === null || since_path === profFolder(profiles.editing) + '\\tags.json')) return { unchanged: true, mtime_ns: tagMtime };
        return tagSnapshot();
      });
    },
    create_tag: function (label, color) {
      return tagChange(function (st) {
        var lb = tagLabel(st, label, null);
        if (lb.err) return lb.err;
        if (color !== null && color !== undefined && !/^#[0-9a-f]{6}$/i.test(color)) return { ok: false, error: 'A tag colour is #RRGGBB.' };
        var base = tagSlug(lb.label), key = base, n = 2;
        while (hasTag(st, key)) { var suf = '-' + n++; key = base.slice(0, 32 - suf.length) + suf; }
        st.tags.push({ key: key, label: lb.label, color: color ? color.toUpperCase() : tagNextColor(st) });
        return { ok: true, key: key };
      });
    },
    rename_tag: function (key, label) {
      return tagChange(function (st) {
        if (key === FAV) return BUILTIN_ERR;
        var t = findTag(st, key);
        if (!t) return tagUnknown(key);
        var lb = tagLabel(st, label, key);
        if (lb.err) return lb.err;
        t.label = lb.label;
        return { ok: true, key: key };
      });
    },
    recolor_tag: function (key, color) {
      return tagChange(function (st) {
        var t = findTag(st, key);
        if (!t) return tagUnknown(key);
        if (!/^#[0-9a-f]{6}$/i.test(color || '')) return { ok: false, error: 'A tag colour is #RRGGBB.' };
        t.color = color.toUpperCase();
        return { ok: true, key: key };
      });
    },
    delete_tag: function (key) {
      return tagChange(function (st) {
        if (key === FAV) return BUILTIN_ERR;
        if (!findTag(st, key)) return tagUnknown(key);
        tagDrop(st, key);
        return { ok: true, key: key };
      });
    },
    merge_tags: function (src, dst) {
      return tagChange(function (st) {
        if (src === FAV) return BUILTIN_ERR;
        if (!findTag(st, src)) return tagUnknown(src);
        if (!findTag(st, dst)) return tagUnknown(dst);
        if (src === dst) return { ok: false, error: 'A tag cannot be merged into itself.' };
        Object.keys(st.items).forEach(function (ik) {
          var lst = st.items[ik], i = lst.indexOf(src);
          if (i < 0) return;
          if (lst.indexOf(dst) >= 0) lst.splice(i, 1); else lst[i] = dst;
        });
        tagDrop(st, src);
        var res = { ok: true, key: dst };
        if (window.__ZORBIT_MODE__ === 'popout') {     // the popout (no menus of its own) points the ring items in radial.json at the kept tag
          var moved = 0;
          Object.keys(saved.menus || {}).forEach(function (id) { (saved.menus[id].items || []).forEach(function (it) {
            var hit = false;
            ['tag', 'browser'].forEach(function (k) { if (it[k] === src) { it[k] = dst; hit = true; } });
            if (hit) moved++; }); });
          res.ring_items = moved;
        }
        return res;
      });
    },
    set_item_tags: function (itemKey, keys) {
      return tagChange(function (st) {
        var ik = tagItemKey(itemKey);
        if (!ik) return { ok: false, error: "'" + itemKey + "' is not an item key like 'brush:name'." };
        var ks = uniq(keys || []);
        for (var i = 0; i < ks.length; i++) if (!findTag(st, ks[i])) return tagUnknown(ks[i]);
        if (ks.length) st.items[ik] = ks; else delete st.items[ik];
        return { ok: true };
      });
    },
    tag_items: function (itemKeys, add, remove) {
      return tagChange(function (st) {
        var iks = (itemKeys || []).map(tagItemKey);
        if (iks.indexOf(null) >= 0) return { ok: false, error: "Item keys look like 'brush:name'." };
        for (var i = 0; i < (add || []).length; i++) if (!findTag(st, add[i])) return tagUnknown(add[i]);
        uniq(iks).forEach(function (ik) {
          var lst = (st.items[ik] || []).filter(function (k) { return (remove || []).indexOf(k) < 0; });
          uniq(add || []).forEach(function (k) { if (lst.indexOf(k) < 0) lst.push(k); });
          if (lst.length) st.items[ik] = lst; else delete st.items[ik];
        });
        return { ok: true };
      });
    },
    get_usage: function (kind) {
      kind = ASSET_KIND[kind] ? kind : 'brush';
      return sleep(50 + lag).then(function () { return usageOff() ? usageEmpty(kind) : usagePayload(kind); });
    },
    forget_recent: function (kind, name) {
      kind = ASSET_KIND[kind] ? kind : 'brush';
      return sleep(60 + lag).then(function () {
        var st = usageStore(kind), key = String(name).replace(/\s+/g, '').toLowerCase();
        st.recent = st.recent.filter(function (r) { return r.name.replace(/\s+/g, '').toLowerCase() !== key; });
        usageSave(kind);
        return usagePayload(kind);
      });
    },
    get_auto_slots: function (cfg, menuId) {
      return sleep(30).then(function () { return { slots: menuId === 'brushes' ? ['Pinch', null] : [] }; });
    },
    get_suggestions: function () { return sleep(60).then(function () { return clone(M.get_suggestions); }); },
    get_status: function () {
      ticks++;
      return sleep(40).then(function () {
        var s = clone(M.get_status), down = q.get('status') === 'down';
        s.zbrush_running = zbRunning();
        s.app_running = appRunning() || (q.has('appolder') && zbRunning());
        s.app_version = q.has('appolder') ? (appRestarted ? '0.18.1' : '0.18.0') : null;
        s.app_older = q.has('appolder') && !appRestarted && s.app_running;
        s.listener = down ? null : { verified: true, alive: true };
        if (down) s.last_pick = null;
        s.bridge_mode = bridgeMode();
        s.legacy_only = q.has('legacy');
        s.checked_at = Date.now() / 1000;
        s.zbrush_check_ok = !q.has('nocheck');
        s.app_log = mockLog();
        return s;
      });
    },
    start_app: function () {
      console.log('[mock] start_app');
      if (q.get('status') === 'down') return sleep(300).then(function () { return { ok: false, running: false, reason: 'zbrush', message: 'ZBrush is not running. Start ZBrush first.' }; });
      if (q.has('startfail')) return sleep(1500).then(function () {
        var t = Date.now(), lines = q.get('startfail') === 'empty' ? [] : [stamp(t) + ' ZOrbit starting', stamp(t + 120) + " error: could not register hotkey 'Q' (already taken by another program)", stamp(t + 130) + ' ZOrbit failed to start; exiting'];
        // the same words as studio.py: the colon only when there are lines to follow it
        return { ok: false, running: false, reason: 'failed', lines: lines, log: lines.slice(),
          message: 'The app did not start.' + (lines.length ? ' The last lines of its log:' : ' It wrote nothing to its log.') };
      });
      if (q.has('startwait')) return sleep(2000).then(function () {
        setTimeout(function () { appStarted = true; }, 6000);
        return { ok: false, running: false, starting: true, message: 'The app is still starting (a first start can take a few seconds while Windows scans it). Status turns green when it is up.' };
      });
      if (q.has('appolder') && !appRestarted) return sleep(1500).then(function () { appRestarted = true; return { ok: true, running: true, restarted: true, was: '0.12.0', message: 'Restarted the app. It was ZOrbit 0.12.0.' }; });
      return sleep(q.has('startslow') ? 7000 : 1000).then(function () { appStarted = true; return { ok: true, running: true, message: 'Started.' }; });
    },
    open_folder: function (which) { console.log('[mock] open_folder', which); return Promise.resolve(true); },
    get_zscript_bridge: function () {
      return sleep(120).then(function () { return { bundled: true, installs: zsInstalls() }; });
    },
    install_zscript_bridge: function () {
      if (q.has('busy')) return sleep(150).then(function () { return { ok: false, busy: true, message: 'Another install or removal is still running. Wait for it to finish.' }; });
      return sleep(300 + lag).then(function () { zInstalledNow = true; try { localStorage.setItem('rm_zscript', '{"a":1}'); } catch (e) {} return { ok: true, message: 'Installed (mock). Restart ZBrush so it loads the plugin.' }; });
    },
    // The Setup screen's one look at everything (see setupSnapshot). ?ringtried / ?ringauto start their clocks from here.
    get_setup: function () {
      return sleep(60).then(function () {
        var n = ++setupCalls, later = q.get('setupfail') === 'later';
        if (q.has('setupfail') && (!later || n > 2)) {         // as studio.py: only these four keys, no installs list the page could take for "nothing found"
          var t = Date.now() / 1000;
          return { now: t, checked_at: t, failed: true, error: 'The setup check failed: [WinError 5] Access is denied (mock) (see studio.log)' };
        }
        setupTimers(); return setupSnapshot();
      });
    },
    register_plugin_path: function () {
      if (q.has('fixfail')) return sleep(300).then(function () { return { ok: false, changed: false, restart: false, message: 'Could not write ZBRUSH_PLUGIN_PATH (mock): access denied.' }; });
      return sleep(300 + lag).then(function () {
        try { localStorage.setItem('rm_env', '1'); } catch (e) {}
        fixedAt = Date.now() / 1000;
        return { ok: true, changed: true, restart: true, message: 'Registered (mock). Restart ZBrush so it loads the plugin.' };
      });
    },
    remove_zscript_bridge: function () {
      if (q.has('busy')) return sleep(150).then(function () { return { ok: false, busy: true, message: 'Another install or removal is still running. Wait for it to finish.' }; });
      return sleep(200 + lag).then(function () { try { localStorage.removeItem('rm_zscript'); } catch (e) {} return { ok: true, message: 'Removed (mock).' }; });
    },
    add_zbrush_folder: function () {
      // A ZBrush 2026 or later: ok, python: true. It joins the modern installs (Setup lists it, with Fix while it is unregistered, and Forget).
      if (q.has('addmodern') && !modernAdded) return sleep(100).then(function () { modernAdded = true; return { ok: true, python: true, message: 'Added ZBrush 2027.' }; });
      if (q.has('already') && !alreadyDone) { alreadyDone = true; return sleep(100).then(function () { return { ok: true, already: true, message: 'C:\\Programs\\ZBrush 2022 is already listed.' }; }); }
      return Promise.resolve({ ok: false, cancelled: true });
    },
    forget_zbrush_folder: function (path) {
      if (path === HAND_ADDED.path) { modernAdded = false; return sleep(100).then(function () { return { ok: true, message: 'Forgot ZBrush 2027.' }; }); }
      var f = JSON.parse(localStorage.getItem('rm_zforgot') || '{}'); f[path] = 1;
      try { localStorage.setItem('rm_zforgot', JSON.stringify(f)); } catch (e) {}
      return sleep(100).then(function () { return { ok: true, message: 'Forgot ' + path + '. The folder itself was not touched.' }; });
    },
    // ?firstrun answers setup_done false until Finish or Skip, so a reload goes back to Setup
    get_prefs: function () { var p = Object.assign({ check_updates: true, last_screen: 'menus', setup_done: true, mode: 'full', seen_version: '', tour_seen: true }, JSON.parse(localStorage.getItem('rm_prefs') || '{}')); if (firstRun()) p.setup_done = false; if (q.has('firstrun') && !tourDone) p.tour_seen = false; return Promise.resolve(themeOf(modeOf(p))); },
    set_pref: function (k, v) { if (q.has('prefsfail') && k !== 'last_screen') return sleep(80).then(function () { throw new Error('disk full (mock)'); }); if (k === 'theme' && THEMES.indexOf(v) < 0) return Promise.reject(new Error('theme: ' + v + ' is not a theme (mock)')); var p = Object.assign({ check_updates: true, last_screen: 'menus', setup_done: true, mode: 'full', seen_version: '', tour_seen: true }, JSON.parse(localStorage.getItem('rm_prefs') || '{}')); p[k] = v; var pageOnly = (k === 'mode' && (q.has('firstrun') || q.get('mode'))) || (k === 'theme' && q.get('theme')); if (pageOnly) { if (k === 'theme') pageTheme = v; else pageMode = v; } else try { localStorage.setItem('rm_prefs', JSON.stringify(p)); } catch (e) {} if (k === 'setup_done' && v === true) firstDone = true; if (k === 'tour_seen' && v === true) tourDone = true; if (firstRun()) p.setup_done = false; if (q.has('firstrun') && !tourDone) p.tour_seen = false; return Promise.resolve(themeOf(modeOf(p))); },
    set_dirty: function () { return Promise.resolve(true); },
    close_now: function () { console.log('[mock] close_now'); return Promise.resolve(true); },
    win_minimize: function () { return Promise.resolve(); },
    win_close: function () { return Promise.resolve(); },
    win_toggle_maximize: function () { return Promise.resolve(false); },
    win_is_maximized: function () { return Promise.resolve(false); },
    get_app_info: function () { return Promise.resolve({ version: '0.18.1' }); },
    check_update: function () { var p = JSON.parse(localStorage.getItem('rm_prefs') || '{}'); if (p.check_updates === false) return Promise.resolve({ newer: false, current: '0.18.1', latest: null, url: 'https://github.com/combwizard/zorbit/releases' }); return sleep(300).then(function () { if (q.has('unreach')) return { newer: false, current: '0.18.1', latest: null, url: 'https://github.com/combwizard/zorbit/releases' }; return q.has('update') ? { newer: true, current: '0.18.0', latest: '0.18.1', url: 'https://github.com/combwizard/zorbit/releases', can_install: !q.has('portable'), skipped: p.skipped_version === '0.18.1', notes: UPD_NOTES } : { newer: false, current: '0.18.1', latest: '0.18.1', url: 'https://github.com/combwizard/zorbit/releases' }; }); },
    // The update download: about two seconds of progress; ?updatefail ends it with the hash message.
    get_update_progress: function () { return Promise.resolve(Object.assign({}, mockUpd)); },
    download_update: function () {
      if (mockUpd.state === 'ready') return Promise.resolve({ ok: true, version: '0.18.1', message: '' });
      mockUpd = { state: 'downloading', version: '0.18.1', done: 0, total: 31457280, message: '', file: '' };
      var step = function (n) { return sleep(100).then(function () { mockUpd.done = Math.round(mockUpd.total * n / 20); return n < 20 ? step(n + 1) : null; }); };
      return step(1).then(function () {
        if (q.has('updatefail')) { mockUpd = { state: 'failed', version: '0.18.1', done: 0, total: 0, message: 'The downloaded file does not match the SHA-256 of the release, so it was deleted.', file: '' }; return { ok: false, version: '0.18.1', message: mockUpd.message }; }
        mockUpd.state = 'ready'; return { ok: true, version: '0.18.1', message: '' };
      });
    },
    install_update: function () { console.log('[mock] install_update: Setup would start and Studio close'); return Promise.resolve({ ok: true, message: '' }); },
    get_whats_new: function (all) {
      return sleep(60).then(function () {
        if (!q.has('whatsnew') && all !== true) return { current: '0.18.1', url: 'https://github.com/combwizard/zorbit/releases', sections: [] };
        return { current: '0.18.1', url: 'https://github.com/combwizard/zorbit/releases', sections: [
          { version: '0.13.0', date: '2026-11-01', url: 'https://github.com/combwizard/zorbit/releases/tag/v0.13.0',
            summary: ['Profiles keep a whole set of menus, settings and tags for each kind of work (#19). The `radial.json` file of your first profile stays where it was, and **nothing you made is lost** on the way in.'], items: [] },
          { version: '0.12.0', date: '2026-10-12', url: 'https://github.com/combwizard/zorbit/releases/tag/v0.12.0', summary: [],
            items: ['Studio opens in **Simple** mode on a new install.', 'The browser remembers its size and side.', 'A pick during a stroke waits for the stroke to end.',
              'Tag colours can be a band, a glow or a tint.', 'Fixed the ring flicker with reduced motion (#92).'] }] };
      });
    },
    get_strays: function () {
      return sleep(60).then(function () { return straysFound ? { found: true, menus: 3, tags: 5, when: Date.now() / 1000 - 86400 * 20, name: 'From an older version' } : { found: false, menus: null, tags: null, when: null, name: 'From an older version' }; });
    },
    adopt_strays: function (how, name) {
      return sleep(150).then(function () {
        if (how === 'aside') { straysFound = false; return { ok: true, folder: 'C:\\Users\\you\\AppData\\Roaming\\ZOrbit\\pre-profiles' }; }
        var bad = profNameProblem(name, null);
        if (bad) return { ok: false, message: bad };
        var n = name.trim();
        profiles.names.push(n); profSort(); profiles.saved[n] = clone(M.get_config.config);
        straysFound = false;
        return { ok: true, name: n, names: profiles.names.slice(), active: profiles.active, editing: profiles.editing, message: 'Created the profile ' + n + '.' };
      });
    },
    open_url: function (url) { console.log('[mock] open_url', url); return Promise.resolve(true); },
    open_browser: function () { console.log('[mock] open_browser'); return Promise.resolve({ ok: true, started: false }); },
    // The browser popout (popout.html?mock). A pick only logs; ?nopick answers like a popout whose app is gone.
    popout_pick: function (name, kind) {
      console.log('[mock] popout_pick', name, kind);
      return sleep(60).then(function () {
        if (q.has('nopick')) return { ok: false, error: 'ZOrbit is not running. It starts and stops with ZBrush. Start ZBrush, or press Start app on Studio’s Status screen.' };
        if (name && ASSET_KIND[kind] && !usageOff()) usagePick(kind, String(name));          // ZBrush selected it: it is now the newest Recent
        return { ok: true };
      });
    },
    popout_hide: function () { console.log('[mock] popout_hide'); return Promise.resolve(true); },
    popout_release_focus: function () { console.log('[mock] popout_release_focus'); return Promise.resolve(true); },
    popout_set_on_top: function (flag) {
      console.log('[mock] popout_set_on_top', flag);
      try { localStorage.setItem('rm_pop_on_top', flag ? '1' : '0'); } catch (e) {}
      return Promise.resolve(true);
    },
    popout_set_kind: function (kind) {
      console.log('[mock] popout_set_kind', kind);
      try { localStorage.setItem('rm_pop_kind', kind); } catch (e) {}
      return Promise.resolve(true);
    },
    popout_set_column: function (shown) {
      console.log('[mock] popout_set_column', shown);
      try { localStorage.setItem('rm_pop_column', shown ? '1' : '0'); } catch (e) {}
      return Promise.resolve(true);
    },
    popout_set_side: function (side) {
      console.log('[mock] popout_set_side', side);
      try { localStorage.setItem('rm_pop_side', side); } catch (e) {}
      return Promise.resolve(true);
    },
    popout_set_size: function (px) { console.log('[mock] popout_set_size', px); return Promise.resolve(true); },
    theme_changed: function (eff) { console.log('[mock] theme_changed', eff); return Promise.resolve(true); },
    popout_theme_changed: function (eff) { console.log('[mock] popout_theme_changed', eff); return Promise.resolve(true); },
    popout_get_state: function () {
      var onTop = true, kind = null, side = 'left', column = true;
      try { onTop = localStorage.getItem('rm_pop_on_top') !== '0'; kind = localStorage.getItem('rm_pop_kind'); side = localStorage.getItem('rm_pop_side') || 'left'; column = localStorage.getItem('rm_pop_column') !== '0'; } catch (e) {}
      return Promise.resolve({ on_top: onTop, size: 96, side: side, column: column, tag: q.get('tag') || null, kind: q.get('kind') || kind || 'brush', tags_path: '', profile: profiles.editing, theme: themeSetting(), theme_effective: themeEff(), theme_base: themeBase(), theme_tokens: themeEff() === 'zbrush' ? clone(ZB_TOKENS) : {} });
    },
    popout_log: function (msg) { console.log('[mock] popout_log', msg); return Promise.resolve(true); },
  };
  window.pywebview = { api: api };
  setTimeout(function () { window.dispatchEvent(new Event('pywebviewready')); }, 0);
})();
