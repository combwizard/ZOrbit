/* Browser-only stand-in for pywebview's js_api. Loaded by index.html only when the URL has ?mock.
   Backed by window.__RADIAL_MOCK__ (recorded real responses from dev/mock_data.js).
   Extra URL switches for visual testing: ?problems (sample problems), ?status=down (ZBrush and the app off; Start app is refused
   with reason "zbrush"), ?status=up (the app already runs; by default ZBrush and the app both run; with ?appoff, ?startfail or any other ?status the app stays off until Start app succeeds),
   ?startfail (start_app answers reason "failed" with three log lines after 1.5 s), ?legacy (legacy_only: key-bridge listener card),
   ?nocheck (zbrush_check_ok false: the ZBrush card says "Could not check"),
   ?lag=300 (artificial latency in ms for preview calls and for the ZScript install/remove, so the busy row is visible), ?broken (get_config fails to parse: recovery screen),
   ?conflict (the first save without force reports "file changed on disk"), ?blocked (a save without force is
   refused as "no ring can open" until forced), ?nozbrush (get_library: ZBrush not found, no brushes), ?nolib (ZBrush
   found but no .zbp files in its folders), ?liberr (get_library reports an error), ?thumbfail (the first two get_thumbs
   calls are rejected, then they work), ?already (the first "Add a ZBrush folder" says the folder is already listed), ?busy
   (install/remove report that another operation is running), ?update (check_update finds a newer release), ?unreach
   (check_update cannot reach GitHub), ?prefsfail (set_pref is rejected).
   Tags (state in localStorage rm_tags, seeded with the built-in Favourites tag (always first, cannot be renamed, merged or deleted), the two
   starters and a few tagged brushes, three of them starred): ?tags=empty (only Favourites, nothing tagged),
   ?tagsmany (Favourites and 30 tags with long names), ?tagfail (every tag change is refused), ?tagexists (create and rename always clash with
   the first ordinary tag). The first two keep their state in memory only, so a reload starts clean.
   Usage (get_usage / forget_recent; state in localStorage rm_usage_<kind>): a made-up Recent list of six items of that kind and scores for 24
   (the order of Favourites); a pick in the popout moves that item to the front of Recent. ?usage=empty (nothing picked yet, no scores).
   Import and export (Settings): ?importfail (the picked file is refused with a message), ?importcancel (the file dialog is closed),
   ?importtags (the file holds tags only); an import changes the ring accent to cyan so it can be seen.
   get_library/get_thumbs answer for every kind (brush, alpha, material, texture); the ?nozbrush/?nolib/?liberr switches apply to all of them.
   The popout page (popout.html?mock): ?nopick (a pick is refused as "ZOrbit is not running"), ?tag=blocking (opens filtered, as --tag does),
   ?kind=alpha (opens on that tab, else the last one, kept in localStorage rm_pop_kind);
   Keep on top is kept in localStorage rm_pop_on_top (on until switched off), and the popout_* calls only log.
   ?kinds adds a Tag item ({"tag": "blocking"}) and a Browser item ({"browser": ""}) to the end of the Tools menu, so the two newer
   kinds can be seen (the recorded config has none). The default stays the faithful recording.
   Setup screen (get_setup; state in localStorage rm_env for the registered folder and rm_zscript for the ZScript plugin, which Settings > Older
   ZBrush shares): ?firstrun (setup_done is false until Finish or Skip, so Studio opens on Setup; a reload does it again),
   ?zb=2026|2022|both|none|multi (which ZBrush installs exist; default both = 2026 plus the two older ones, multi adds 2027 and runs two),
   ?noenv (ZBRUSH_PLUGIN_PATH not set until Fix), ?fixfail (Fix is refused), ?nobridge (the plugin folder is missing: no Fix),
   ?zbrun=off (no ZBrush process), ?zbstale (it started before the plugin: restart), ?zbstart (it is still starting), ?noloaded (it never loaded the plugin),
   ?elevated (the ZBrush is running as administrator and cannot be matched to an install), ?appoff (the app is not running), ?otherbridge (another ZOrbit
   folder is registered too, one of them missing), ?bridgemode=key (picks go through the bridge key), ?ringtried=open|sent|done (step 3 starts part
   way, measured from when Setup is first shown), ?ringauto (once step 3 opens, the ring opens after 2 s, a pick follows after 4 s and ZBrush answers
   after 6 s; with ?bridgemode=key ZBrush never answers, so the hint shows). In the console, __mock.ring('open'), ('pick') and ('ack') do the same by hand. */
(function () {
  var M = window.__RADIAL_MOCK__ || {};
  var q = new URLSearchParams(location.search);
  var lag = +(q.get('lag') || 0);
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var clone = function (o) { return JSON.parse(JSON.stringify(o)); };
  var ticks = 0, thumbCalls = 0, alreadyDone = false, appStarted = false;
  var saved = clone(M.get_config.config);
  var TAG_DEFAULTS = { tag_colors: 'tint', tag_band: 'medium', tag_band_opacity: 0.45, tag_glow_opacity: 0.4, tag_tint_opacity: 0.3, tag_tint_style: 'gradient', tag_tint_blend: 'multiply' };
  var KINDS = ['brush', 'alpha', 'material', 'texture', 'press', 'set', 'toggle', 'steps', 'menu', 'auto', 'tag', 'browser'];
  if (q.has('kinds') && saved.menus && saved.menus.tools) saved.menus.tools.items.push({ tag: 'blocking' }, { browser: '' });
  var mtime = 1700000000000000000, conflictDone = false;
  var FAV = 'favourite';
  var TAG_PALETTE = ['#F86B33', '#4DC8E9', '#A8DF23', '#E8413C', '#C77DFF', '#FFD166', '#5EEAD4', '#F472B6'];
  var tagsMode = q.get('tags') === 'empty' ? 'empty' : q.has('tagsmany') ? 'many' : 'saved';
  var tagMtime = 1700000000000000000, tagStore = null;
  var BROKEN_ERR = "Expecting ',' delimiter: line 12 column 5 (char 301)";

  // Python's repr of a string, close enough for the messages: 'x'
  function pyr(v) { return typeof v === 'string' ? "'" + v + "'" : String(v); }

  // The items the ring would draw: one action each, submenu targets that exist (the order preview_ring's indices count in)
  function usable(m) {
    return (m.items || []).filter(function (it) {
      var ks = KINDS.filter(function (k) { return k in it; });
      if (ks.length !== 1) return false;
      var k = ks[0];                       // config.py: every string target but a browser's must be non-empty
      return k === 'steps' || k === 'auto' || k === 'browser' || (typeof it[k] === 'string' && it[k].trim() !== '');
    });
  }

  function validate(cfg) {
    var out = [];
    var menus = (cfg && cfg.menus) || {};
    var ids = Object.keys(menus);
    var seen = {}, st = tagState();
    var ringc = (cfg && cfg.ring) || {};
    if (ringc.tag_colors !== undefined && ['none', 'tint', 'glow', 'both'].indexOf(ringc.tag_colors) < 0) out.push('ring.tag_colors: ' + pyr(ringc.tag_colors) + ' unknown; one of none, tint, glow, both');
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
            if (sk.some(function (x) { return ['menu', 'steps', 'auto', 'tag', 'browser'].indexOf(x) >= 0; })) {
              out.push(where + ' step ' + (j + 1) + ': steps cannot open menus, nest steps, be auto slots or open tags or the browser'); return;
            }
          }
        }
        else if (k === 'browser') { if (typeof it.browser !== 'string') { out.push(where + ": 'browser' must be a string (a tag key, or \"\" for all brushes)"); return; } }
        else if (k === 'set' && !('value' in it)) { out.push(where + ": 'set' needs a 'value'"); return; }
        else if (k === 'set' && typeof it.value !== 'number') { out.push(where + ": 'set' value must be a number"); return; }
        else if (typeof it[k] !== 'string' || !it[k].trim()) { out.push(where + ": '" + k + "' must be a non-empty string"); return; }
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
    if (q.has('problems')) out.push('menu brushes item 3: sample problem for the problems panel (?problems)', 'bridge.key must not use Ctrl or Shift (ZBrush reads them as mask/smooth); use a bare F-key',
      'ring.radius: 500 must be a number from 60 to 400', "menu tools: hotkey 'Q' already used by menu brushes");
    return out;
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
    st.tags.push({ key: 'blocking', label: 'Blocking', color: '#F86B33' }, { key: 'detailing', label: 'Detailing', color: '#4DC8E9' });
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
      items: clone(st.items), palette: TAG_PALETTE.slice(), mtime_ns: tagMtime, path: 'C:\\Users\\mock\\AppData\\Roaming\\ZOrbit\\tags.json', error: null };
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
      sources: [{ label: 'ZBrush 2026 brush presets', path: 'C:\\Users\\david\\OneDrive\\Documents\\ZBrush 2026 Assets\\ZStartup\\BrushPresets', exists: true },
                { label: 'ZBrush 2022 brush presets', path: 'C:\\Program Files\\Maxon ZBrush 2022\\ZStartup\\BrushPresets', exists: false }] },
    alpha: { suffix: ' Alpha', ext: '.psd', cats: ['My Alphas', 'ZBrush', 'Lightbox/HardSurfaceAlphas'],
      sources: [{ label: 'ZBrush 2026 alphas', path: 'C:\\Users\\david\\OneDrive\\Documents\\ZBrush 2026 Assets\\ZStartup\\Alphas', exists: true },
                { label: 'ZBrush 2022 alphas', path: 'C:\\Program Files\\Maxon ZBrush 2022\\ZStartup\\Alphas', exists: false }] },
    material: { suffix: ' Mat', ext: '.zmt', cats: ['My Materials', 'ZBrush/MatCap', 'Lightbox/Standard'],
      sources: [{ label: 'ZBrush 2026 materials', path: 'C:\\Users\\david\\OneDrive\\Documents\\ZBrush 2026 Assets\\ZStartup\\Materials', exists: true },
                { label: 'ZBrush 2022 materials', path: 'C:\\Program Files\\Maxon ZBrush 2022\\ZStartup\\Materials', exists: false }] },
    texture: { suffix: ' Tex', ext: '.psd', cats: ['My Textures', 'ZBrush', 'Lightbox/Panoramas'],
      sources: [{ label: 'ZBrush 2026 textures', path: 'C:\\Users\\david\\OneDrive\\Documents\\ZBrush 2026 Assets\\ZStartup\\Textures', exists: true },
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
        return { name: name, source: cat.split('/')[0], category: cat, path: 'C:\\Users\\david\\ZBrush Assets\\' + cat.replace(/\//g, '\\') + '\\' + name + A.ext };
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
  var lsGet = function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } };
  var envRegistered = function () { return !q.has('noenv') || lsGet('rm_env') === '1'; };
  var bridgeOk = function () { return !q.has('nobridge'); };
  var BRIDGE_DIR = 'C:\\Program Files\\ZOrbit\\bridge';
  var zbStartedAt = Date.now() / 1000 - 600;                 // the mock's ZBrush started ten minutes before the page opened
  var zInstalledNow = false, fixedAt = 0;                   // the plugin was installed / the folder registered during this page's life: a running ZBrush predates it
  var bridgeMode = function () { return q.get('bridgemode') || (saved.bridge && saved.bridge.mode) || 'auto'; };
  var MODERN = [{ name: 'ZBrush 2026', year: 2026, path: 'C:\\Program Files\\Maxon ZBrush 2026', python: true, added: false },
    { name: 'ZBrush 2027', year: 2027, path: 'C:\\Program Files\\Maxon ZBrush 2027', python: true, added: false }];
  var modernInstalls = function () { return zbMode === 'none' || zbMode === '2022' ? [] : (zbMode === 'multi' ? MODERN : MODERN.slice(0, 1)); };
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
      if (q.has('elevated') && !unmatched.length) { unmatched.push({ pid: pid, started: started, elevated: true }); return; }
      if (q.has('zbstart')) { state = 'starting'; why = 'Started a few seconds ago.'; }
      else if (q.has('zbstale')) { state = 'restart'; why = 'Started before the plugin was set up.'; }
      else if (q.has('noloaded')) { state = 'not_loaded'; why = inst.name + ' is running, but the plugin did not load. See bridge.log.'; }
      else if (inst.kind === 'modern') {
        if (!ok) { state = 'not_loaded'; why = 'The plugin folder is missing.'; }
        else if (!reg) { state = 'not_loaded'; why = inst.name + ' does not know where the plugin is.'; }
        else if (keyMtime > started) { state = 'restart'; why = 'Registered after this ZBrush started.'; }
        else { state = 'loaded'; loadedPid = pid; evidence = 'listener.json'; }
      } else if (!inst.ready) { state = 'not_loaded'; why = 'The ZOrbit plugin is not installed for this ZBrush.'; }
      else if (zInstalledNow && inst.path === 'C:\\Programs\\ZBrush 2022') { state = 'restart'; why = 'Installed after this ZBrush started.'; }
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
    get_config: function () {
      return sleep(40).then(function () {
        var r = clone(M.get_config);
        r.config = clone(saved);                                   // what the last mock save wrote, so Reload from disk is honest
        r.defaults = Object.assign({}, r.defaults, TAG_DEFAULTS);
        if (q.has('broken') && !sessionStorage.getItem('rm_repaired')) return { config: null, error: BROKEN_ERR, path: r.path, backup_exists: true, problems: [], mtime_ns: null };
        r.problems = q.has('problems') ? validate(r.config) : r.problems;
        r.mtime_ns = mtime; r.backup_exists = true;
        return r;
      });
    },
    validate: function (cfg) { return sleep(30).then(function () { return { problems: validate(cfg) }; }); },
    save_config: function (cfg, mtime_ns, force, allow_unusable) {
      return sleep(180).then(function () {
        if (q.has('conflict') && !force && !conflictDone) {
          conflictDone = true; mtime += 1000000;
          return { saved: false, conflict: true, message: 'radial.json was changed on disk after Studio loaded it (mock).', mtime_ns: mtime };
        }
        if (q.has('blocked') && !allow_unusable) {
          return { saved: false, blocked: true, problems: ['menu brushes: no usable items', 'no menu has a hotkey, so nothing can open the ring'],
            message: 'Saving this would leave no ring that can open, so ZOrbit would stop working.' };
        }
        saved = clone(cfg); mtime += 1000000;
        return { saved: true, problems: validate(cfg), time: Date.now() / 1000, mtime_ns: mtime };
      });
    },
    // Both mark the file as repaired for this tab, so the reload after them boots normally even with ?broken.
    restore_backup: function () { try { sessionStorage.setItem('rm_repaired', '1'); } catch (e) {} return sleep(200).then(function () { return { ok: true, message: 'Restored the last good backup (mock).' }; }); },
    reset_config: function () { try { sessionStorage.setItem('rm_repaired', '1'); } catch (e) {} return sleep(200).then(function () { return { ok: true, message: 'Reset to the default menus (mock).' }; }); },
    // Export and import: the picked file is a made-up bundle. ?importfail refuses it, ?importcancel is a closed dialog, ?importtags a tags-only file.
    export_settings: function (cfg) {
      return sleep(150).then(function () {
        if (q.has('importcancel')) return { ok: false, cancelled: true };
        return { ok: true, path: 'C:\\Users\\mock\\Documents\\ZOrbit settings 2026-10-30.json', message: 'Exported ' + Object.keys((cfg && cfg.menus) || {}).length + ' menus and the tags to ZOrbit settings 2026-10-30.json (mock).' };
      });
    },
    pick_import: function () {
      return sleep(150).then(function () {
        if (q.has('importcancel')) return { ok: false, cancelled: true };
        if (q.has('importfail')) return { ok: false, message: "That file is not valid JSON: Expecting ',' delimiter: line 12 column 5 (mock)." };
        var tagsOnly = q.has('importtags'), n = Object.keys(saved.menus || {}).length;
        return { ok: true, path: 'C:\\Users\\mock\\Documents\\ZOrbit settings 2026-10-30.json', kind: tagsOnly ? 'tags' : 'bundle', has_config: !tagsOnly, menus: tagsOnly ? 0 : n,
          has_tags: true, tags: 4, new_tags: 2, items: 17, problems: tagsOnly || !q.has('problems') ? [] : validate(saved), version: '0.9.0' };
      });
    },
    apply_import: function (tag_mode) {
      return sleep(200).then(function () {
        var tagsOnly = q.has('importtags'), msg = '';
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
    preview_tags: function () {                                   // the backend's sample ring; the recorded data has it once regenerated
      return sleep(60 + lag).then(function () {
        var res = clone(M.preview_tags || M.preview_ring[Object.keys(M.preview_ring)[0]]);
        res.width = res.height = res.size; res.centre = [res.size / 2, res.size / 2];
        return res;
      });
    },
    preview_ring: function (cfg, menuId, hover, scale, openPath) {
      return sleep(60 + lag).then(function () {
        var m = cfg && cfg.menus && cfg.menus[menuId];
        if (!m || !(m.items || []).length) return { image: null, problems: ['menu ' + menuId + ' has no usable items'] };
        var res = clone((hover === 0 && menuId === 'brushes' && M.preview_ring_hover0) || M.preview_ring[menuId] || M.preview_ring.brushes);
        res.width = res.height = res.size; res.centre = [res.size / 2, res.size / 2];
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
      return sleep(350 + lag).then(function () { return M.preview_animation; });
    },
    get_options: function () {
      return sleep(10).then(function () {
        var o = clone(M.get_options);
        o.favourite_tag = FAV;
        o.actions = KINDS.slice(); o.asset_kinds = ['brush', 'alpha', 'material', 'texture']; o.tag_colors = ['none', 'tint', 'glow', 'both'];
        o.tag_bands = ['none', 'hairline', 'narrow', 'medium', 'wide']; o.tint_styles = ['flat', 'gradient']; o.tint_blends = ['multiply', 'overlay'];
        o.ring_defaults = Object.assign({}, o.ring_defaults, TAG_DEFAULTS);
        o.ring_ranges = Object.assign({}, o.ring_ranges, { tag_band_opacity: [0, 1], tag_glow_opacity: [0, 1], tag_tint_opacity: [0, 1] });
        return o;
      });
    },
    get_library: function (refresh, kind) {
      kind = ASSET_KIND[kind] ? kind : 'brush';
      return sleep(refresh ? 700 : 250).then(function () {
        var A = ASSET_KIND[kind], lib = libFor(kind), n = lib.items.length;
        var sources = A.sources.map(function (src, i) { return { label: src.label, path: src.path, exists: src.exists, count: i === 0 ? n : 0 }; });
        if (q.has('liberr')) return { kind: kind, items: [], brushes: [], categories: [], sources: [], zbrush_found: true, error: 'Could not read the ' + kind + ' folders: [WinError 5] Access is denied (mock)' };
        if (q.has('nozbrush')) return { kind: kind, items: [], brushes: [], categories: [], sources: [], zbrush_found: false, error: null };
        if (q.has('nolib')) { sources[0].count = 0; return { kind: kind, items: [], brushes: [], categories: [], sources: sources, zbrush_found: true, error: null }; }
        var out = { kind: kind, items: lib.items, categories: lib.categories, sources: sources, zbrush_found: true, error: null };
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
    get_tags: function (since) {
      return sleep(40).then(function () {
        if (since !== null && since !== undefined && since === tagMtime) return { unchanged: true, mtime_ns: tagMtime };
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
        return { ok: true, key: dst };
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
        s.app_running = appRunning();
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
        var t = Date.now();
        return { ok: false, running: false, reason: 'failed', message: 'The app did not start. The log below says why.',
          log: [stamp(t) + ' ZOrbit starting', stamp(t + 120) + " error: could not register hotkey 'Q' (already taken by another program)", stamp(t + 130) + ' ZOrbit failed to start; exiting'] };
      });
      return sleep(1000).then(function () { appStarted = true; return { ok: true, running: true, message: 'Started (mock: nothing was launched).' }; });
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
      return sleep(60).then(function () { setupTimers(); return setupSnapshot(); });
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
      if (q.has('already') && !alreadyDone) { alreadyDone = true; return sleep(100).then(function () { return { ok: true, already: true, message: 'C:\\Programs\\ZBrush 2022 is already listed.' }; }); }
      return Promise.resolve({ ok: false, cancelled: true });
    },
    forget_zbrush_folder: function (path) {
      var f = JSON.parse(localStorage.getItem('rm_zforgot') || '{}'); f[path] = 1;
      try { localStorage.setItem('rm_zforgot', JSON.stringify(f)); } catch (e) {}
      return sleep(100).then(function () { return { ok: true, message: 'Forgot ' + path + '. The folder itself was not touched.' }; });
    },
    // ?firstrun answers setup_done false until Finish or Skip, so a reload goes back to Setup
    get_prefs: function () { var p = Object.assign({ show_licence: true, check_updates: true, last_screen: 'menus', setup_done: true }, JSON.parse(localStorage.getItem('rm_prefs') || '{}')); if (firstRun()) p.setup_done = false; return Promise.resolve(p); },
    set_pref: function (k, v) { if (q.has('prefsfail') && k !== 'last_screen') return sleep(80).then(function () { throw new Error('disk full (mock)'); }); var p = Object.assign({ show_licence: true, check_updates: true, last_screen: 'menus', setup_done: true }, JSON.parse(localStorage.getItem('rm_prefs') || '{}')); p[k] = v; try { localStorage.setItem('rm_prefs', JSON.stringify(p)); } catch (e) {} if (k === 'setup_done' && v === true) firstDone = true; if (firstRun()) p.setup_done = false; return Promise.resolve(p); },
    set_dirty: function () { return Promise.resolve(true); },
    close_now: function () { console.log('[mock] close_now'); return Promise.resolve(true); },
    win_minimize: function () { return Promise.resolve(); },
    win_close: function () { return Promise.resolve(); },
    win_toggle_maximize: function () { return Promise.resolve(false); },
    win_is_maximized: function () { return Promise.resolve(false); },
    get_app_info: function () { return Promise.resolve({ version: '0.9.0' }); },
    check_update: function () { var p = JSON.parse(localStorage.getItem('rm_prefs') || '{}'); if (p.check_updates === false) return Promise.resolve({ newer: false, current: '0.9.0', latest: null, url: 'https://github.com/combwizard/zorbit/releases' }); return sleep(300).then(function () { if (q.has('unreach')) return { newer: false, current: '0.9.0', latest: null, url: 'https://github.com/combwizard/zorbit/releases' }; return q.has('update') ? { newer: true, current: '0.9.0', latest: '0.9.0', url: 'https://github.com/combwizard/zorbit/releases' } : { newer: false, current: '0.9.0', latest: '0.9.0', url: 'https://github.com/combwizard/zorbit/releases' }; }); },
    open_url: function (url) { console.log('[mock] open_url', url); return Promise.resolve(true); },
    open_browser: function () { console.log('[mock] open_browser'); return Promise.resolve({ ok: true, started: false }); },
    // The browser popout (popout.html?mock). A pick only logs; ?nopick answers like a popout whose app is gone.
    popout_pick: function (name, kind) {
      console.log('[mock] popout_pick', name, kind);
      return sleep(60).then(function () {
        if (q.has('nopick')) return { ok: false, error: 'ZOrbit is not running' };
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
    popout_get_state: function () {
      var onTop = true, kind = null, side = 'left', column = true;
      try { onTop = localStorage.getItem('rm_pop_on_top') !== '0'; kind = localStorage.getItem('rm_pop_kind'); side = localStorage.getItem('rm_pop_side') || 'left'; column = localStorage.getItem('rm_pop_column') !== '0'; } catch (e) {}
      return Promise.resolve({ on_top: onTop, size: 96, side: side, column: column, tag: q.get('tag') || null, kind: q.get('kind') || kind || 'brush', tags_path: '' });
    },
    popout_log: function (msg) { console.log('[mock] popout_log', msg); return Promise.resolve(true); },
  };
  window.pywebview = { api: api };
  setTimeout(function () { window.dispatchEvent(new Event('pywebviewready')); }, 0);
})();
