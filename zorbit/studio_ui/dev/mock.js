/* Browser-only stand-in for pywebview's js_api. Loaded by index.html only when the URL has ?mock.
   Backed by window.__RADIAL_MOCK__ (recorded real responses from dev/mock_data.js).
   Extra URL switches for visual testing: ?problems (sample problems), ?status=down (ZBrush and the app off; Start app is refused
   with reason "zbrush"), ?status=up (the app already runs; by default ZBrush runs and the app does not until Start app succeeds),
   ?startfail (start_app answers reason "failed" with three log lines after 1.5 s), ?legacy (legacy_only: key-bridge listener card),
   ?nocheck (zbrush_check_ok false: the ZBrush card says "Could not check"),
   ?lag=300 (artificial latency in ms for preview calls and for the ZScript install/remove, so the busy row is visible), ?broken (get_config fails to parse: recovery screen),
   ?conflict (the first save without force reports "file changed on disk"), ?blocked (a save without force is
   refused as "no ring can open" until forced), ?nozbrush (get_library: ZBrush not found, no brushes), ?nolib (ZBrush
   found but no .zbp files in its folders), ?liberr (get_library reports an error), ?thumbfail (the first two get_thumbs
   calls are rejected, then they work), ?already (the first "Add a ZBrush folder" says the folder is already listed), ?busy
   (install/remove report that another operation is running), ?update (check_update finds a newer release), ?unreach
   (check_update cannot reach GitHub), ?prefsfail (set_pref is rejected).
   Tags (state in localStorage rm_tags, seeded with the two starters and a few tagged brushes): ?tags=empty (no tags, nothing tagged),
   ?tagsmany (30 tags with long names), ?tagfail (every tag change is refused), ?tagexists (create and rename always clash with
   the first tag). The first two keep their state in memory only, so a reload starts clean. */
(function () {
  var M = window.__RADIAL_MOCK__ || {};
  var q = new URLSearchParams(location.search);
  var lag = +(q.get('lag') || 0);
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var clone = function (o) { return JSON.parse(JSON.stringify(o)); };
  var ticks = 0, thumbCalls = 0, alreadyDone = false, appStarted = false;
  var saved = clone(M.get_config.config);
  var mtime = 1700000000000000000, conflictDone = false;
  var TAG_PALETTE = ['#F86B33', '#4DC8E9', '#A8DF23', '#E8413C', '#C77DFF', '#FFD166', '#5EEAD4', '#F472B6'];
  var tagsMode = q.get('tags') === 'empty' ? 'empty' : q.has('tagsmany') ? 'many' : 'saved';
  var tagMtime = 1700000000000000000, tagStore = null;
  var BROKEN_ERR = "Expecting ',' delimiter: line 12 column 5 (char 301)";

  // The items the ring would draw: one action each, submenu targets that exist (the order preview_ring's indices count in)
  function usable(m) {
    return (m.items || []).filter(function (it) {
      return ['brush', 'press', 'set', 'toggle', 'steps', 'menu', 'auto'].filter(function (k) { return k in it; }).length === 1;
    });
  }

  function validate(cfg) {
    var out = [];
    var menus = (cfg && cfg.menus) || {};
    var ids = Object.keys(menus);
    var seen = {};
    if (!ids.length) out.push('menus: must be a non-empty object of id -> menu');
    ids.forEach(function (id) {
      var m = menus[id], good = 0;
      (m.items || []).forEach(function (it, i) {
        var kinds = ['brush', 'press', 'set', 'toggle', 'steps', 'menu', 'auto'].filter(function (k) { return k in it; });
        var where = 'menu ' + id + ' item ' + (i + 1);
        if (kinds.length !== 1) { out.push(where + ': needs exactly one of brush, press, set, toggle, steps, menu, auto'); return; }
        var k = kinds[0];
        if (k === 'steps') { if (!Array.isArray(it.steps) || !it.steps.length) { out.push(where + ": 'steps' must be a non-empty list of brush/press/set/toggle actions"); return; } }
        else if (k === 'set' && !('value' in it)) { out.push(where + ": 'set' needs a 'value'"); return; }
        else if (k === 'set' && typeof it.value !== 'number') { out.push(where + ": 'set' value must be a number"); return; }
        else if (typeof it[k] !== 'string' || !it[k].trim()) { out.push(where + ": '" + k + "' must be a non-empty string"); return; }
        if (k === 'menu' && !menus[it.menu]) { out.push(where + ": submenu '" + it.menu + "' does not exist"); return; }
        good++;
      });
      if (!good) out.push('menu ' + id + ': no usable items');
      if (m.hotkey) {
        var key = String(m.hotkey).toLowerCase();
        if (seen[key]) out.push('menu ' + id + ": hotkey '" + m.hotkey + "' already used by menu " + seen[key]);
        else seen[key] = id;
      }
    });
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
    if (tagsMode === 'empty') return st;
    if (tagsMode === 'many') {
      for (var i = 0; i < 30; i++) st.tags.push({ key: 'tag-' + (i + 1), label: (i % 3 ? 'Sculpting pass number ' : 'A rather long tag name for ') + (i + 1), color: TAG_PALETTE[i % 8] });
      names.slice(0, 40).forEach(function (n, i) { st.items[key(n)] = [st.tags[i % 30].key].concat(i % 4 === 0 ? [st.tags[(i + 7) % 30].key] : []); });
      return st;
    }
    st.tags = [{ key: 'blocking', label: 'Blocking', color: '#F86B33' }, { key: 'detailing', label: 'Detailing', color: '#4DC8E9' }];
    names.slice(0, 12).forEach(function (n, i) {
      if (i % 6 === 5) return;
      st.items[key(n)] = i % 5 === 4 ? ['blocking', 'detailing'] : [i % 2 ? 'detailing' : 'blocking'];
    });
    return st;
  }
  function tagState() {
    if (tagStore) return tagStore;
    var st = null;
    if (tagsMode === 'saved') { try { st = JSON.parse(localStorage.getItem('rm_tags')); } catch (e) { st = null; } }
    if (!st || !Array.isArray(st.tags) || !st.items) st = tagSeed();
    tagStore = st;
    return st;
  }
  function tagSave() {
    tagMtime += 1000000;
    if (tagsMode === 'saved') { try { localStorage.setItem('rm_tags', JSON.stringify(tagStore)); } catch (e) {} }
  }
  function findTag(st, key) { return st.tags.filter(function (t) { return t.key === key; })[0] || null; }
  function hasTag(st, key) { return !!findTag(st, key); }
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
    var other = st.tags.filter(function (t) { return t.key !== ignore && (q.has('tagexists') || t.label.toLowerCase() === low); })[0];
    if (other) return { err: { ok: false, exists: other.key, error: "A tag called '" + other.label + "' already exists." } };
    return { label: label };
  }
  function tagSnapshot() {
    var st = tagState(), count = {};
    st.tags.forEach(function (t) { count[t.key] = 0; });
    Object.keys(st.items).forEach(function (ik) { st.items[ik].forEach(function (k) { if (k in count) count[k]++; }); });
    return { ok: true, tags: st.tags.map(function (t) { return { key: t.key, label: t.label, color: t.color, count: count[t.key] }; }),
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

  var api = {
    get_config: function () {
      return sleep(40).then(function () {
        var r = clone(M.get_config);
        r.config = clone(saved);                                   // what the last mock save wrote, so Reload from disk is honest
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
    preview_ring: function (cfg, menuId, hover, scale, openPath) {
      return sleep(60 + lag).then(function () {
        var m = cfg && cfg.menus && cfg.menus[menuId];
        if (!m || !(m.items || []).length) return { image: null, problems: ['menu ' + menuId + ' has no usable items'] };
        var res = clone((hover === 0 && menuId === 'brushes' && M.preview_ring_hover0) || M.preview_ring[menuId] || M.preview_ring.brushes);
        res.width = res.height = res.size; res.centre = [res.size / 2, res.size / 2];
        var it = openPath && openPath.length ? usable(m)[openPath[0]] : null, sub = it && it.menu ? cfg.menus[it.menu] : null;
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
    get_options: function () { return sleep(10).then(function () { return clone(M.get_options); }); },
    get_library: function (refresh) {
      return sleep(refresh ? 700 : 250).then(function () {
        var lib = clone(M.get_library), n = lib.brushes.length;
        var sources = [
          { label: 'ZBrush 2026 brush presets', path: 'C:\\Users\\david\\OneDrive\\Documents\\ZBrush 2026 Assets\\ZStartup\\BrushPresets', exists: true, count: n },
          { label: 'ZBrush 2022 brush presets', path: 'C:\\Program Files\\Maxon ZBrush 2022\\ZStartup\\BrushPresets', exists: false, count: 0 }];
        if (q.has('liberr')) return { brushes: [], categories: [], sources: [], zbrush_found: true, error: 'Could not read the brush folders: [WinError 5] Access is denied (mock)' };
        if (q.has('nozbrush')) return { brushes: [], categories: [], sources: [], zbrush_found: false, error: null };
        if (q.has('nolib')) { sources[0].count = 0; return { brushes: [], categories: [], sources: sources, zbrush_found: true, error: null }; }
        return { brushes: lib.brushes, categories: lib.categories, sources: sources, zbrush_found: true, error: null };
      });
    },
    get_thumbs: function (names, size) {
      console.log('[mock] get_thumbs', (names || []).length, 'names, size', size);
      if (q.has('thumbfail') && ++thumbCalls <= 2) return sleep(70).then(function () { throw new Error('thumbnail service unavailable (mock)'); });
      return sleep(70).then(function () {
        var out = {};
        (names || []).forEach(function (n) { out[n] = (M.get_thumbs && M.get_thumbs[n]) || null; });
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
        if (!findTag(st, key)) return tagUnknown(key);
        tagDrop(st, key);
        return { ok: true, key: key };
      });
    },
    merge_tags: function (src, dst) {
      return tagChange(function (st) {
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
    get_auto_slots: function (cfg, menuId) {
      return sleep(30).then(function () { return { slots: menuId === 'brushes' ? ['Pinch', null] : [] }; });
    },
    get_suggestions: function () { return sleep(60).then(function () { return clone(M.get_suggestions); }); },
    get_status: function () {
      ticks++;
      return sleep(40).then(function () {
        var s = clone(M.get_status), down = q.get('status') === 'down';
        s.zbrush_running = !down && !q.has('nocheck');
        s.app_running = s.zbrush_running && (appStarted || q.get('status') === 'up');
        s.listener = down ? null : { verified: true, alive: true };
        if (down) s.last_pick = null;
        s.bridge_mode = (saved.bridge && saved.bridge.mode) || 'auto';
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
      var z = JSON.parse(localStorage.getItem('rm_zscript') || '{}');
      var forgotten = JSON.parse(localStorage.getItem('rm_zforgot') || '{}');
      return sleep(120).then(function () {
        var installs = [
          { name: 'ZBrush 2022', year: 2022, path: 'C:\\Programs\\ZBrush 2022', python: false, installed: !!z.a, current: !!z.a, added: true, zplugs: 'C:\\Programs\\ZBrush 2022\\ZStartup\\ZPlugs64' },
          { name: 'ZBrush 2024', year: 2024, path: 'C:\\Program Files\\Maxon ZBrush 2024', python: false, installed: true, current: false, added: false, zplugs: 'C:\\Program Files\\Maxon ZBrush 2024\\ZStartup\\ZPlugs64' }]
        if (q.has('nozs')) installs = [];
        return { bundled: true, installs: installs.filter(function (i) { return !(i.added && forgotten[i.path]); }) };
      });
    },
    install_zscript_bridge: function () {
      if (q.has('busy')) return sleep(150).then(function () { return { ok: false, busy: true, message: 'Another install or removal is still running. Wait for it to finish.' }; });
      return sleep(300 + lag).then(function () { try { localStorage.setItem('rm_zscript', '{"a":1}'); } catch (e) {} return { ok: true, message: 'Installed (mock). Restart ZBrush so it loads the plugin.' }; });
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
    get_prefs: function () { return Promise.resolve(Object.assign({ show_licence: true, check_updates: true, last_screen: 'menus' }, JSON.parse(localStorage.getItem('rm_prefs') || '{}'))); },
    set_pref: function (k, v) { if (q.has('prefsfail') && k !== 'last_screen') return sleep(80).then(function () { throw new Error('disk full (mock)'); }); var p = Object.assign({ show_licence: true, check_updates: true, last_screen: 'menus' }, JSON.parse(localStorage.getItem('rm_prefs') || '{}')); p[k] = v; try { localStorage.setItem('rm_prefs', JSON.stringify(p)); } catch (e) {} return Promise.resolve(p); },
    set_dirty: function () { return Promise.resolve(true); },
    close_now: function () { console.log('[mock] close_now'); return Promise.resolve(true); },
    win_minimize: function () { return Promise.resolve(); },
    win_close: function () { return Promise.resolve(); },
    win_toggle_maximize: function () { return Promise.resolve(false); },
    win_is_maximized: function () { return Promise.resolve(false); },
    get_app_info: function () { return Promise.resolve({ version: '0.7.1' }); },
    check_update: function () { var p = JSON.parse(localStorage.getItem('rm_prefs') || '{}'); if (p.check_updates === false) return Promise.resolve({ newer: false, current: '0.7.1', latest: null, url: 'https://github.com/combwizard/zorbit/releases' }); return sleep(300).then(function () { if (q.has('unreach')) return { newer: false, current: '0.7.1', latest: null, url: 'https://github.com/combwizard/zorbit/releases' }; return q.has('update') ? { newer: true, current: '0.7.1', latest: '0.7.1', url: 'https://github.com/combwizard/zorbit/releases' } : { newer: false, current: '0.7.1', latest: '0.7.1', url: 'https://github.com/combwizard/zorbit/releases' }; }); },
    open_url: function (url) { console.log('[mock] open_url', url); return Promise.resolve(true); },
  };
  window.pywebview = { api: api };
  setTimeout(function () { window.dispatchEvent(new Event('pywebviewready')); }, 0);
})();
