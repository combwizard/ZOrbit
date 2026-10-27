/* Browser-only stand-in for pywebview's js_api. Loaded by index.html only when the URL has ?mock.
   Backed by window.__RADIAL_MOCK__ (recorded real responses from dev/mock_data.js).
   Extra URL switches for visual testing: ?problems (sample problems), ?status=down (app/ZBrush off),
   ?lag=300 (artificial latency in ms for preview calls), ?broken (get_config fails to parse: recovery screen),
   ?conflict (the first save without force reports "file changed on disk"), ?blocked (a save without force is
   refused as "no ring can open" until forced). */
(function () {
  var M = window.__RADIAL_MOCK__ || {};
  var q = new URLSearchParams(location.search);
  var lag = +(q.get('lag') || 0);
  var sleep = function (ms) { return new Promise(function (r) { setTimeout(r, ms); }); };
  var clone = function (o) { return JSON.parse(JSON.stringify(o)); };
  var ticks = 0;
  var saved = clone(M.get_config.config);
  var mtime = 1700000000000000000, conflictDone = false;
  var BROKEN_ERR = "Expecting ',' delimiter: line 12 column 5 (char 301)";

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
    if (q.has('problems')) out.push('menu brushes item 3: sample problem for the problems bar (?problems)', 'bridge.key must not use Ctrl or Shift (ZBrush reads them as mask/smooth); use a bare F-key');
    return out;
  }

  var api = {
    get_config: function () {
      return sleep(40).then(function () {
        var r = clone(M.get_config);
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
            message: 'Saving this would leave no ring that can open, so the radial menu would stop working.' };
        }
        saved = clone(cfg); mtime += 1000000;
        return { saved: true, problems: validate(cfg), time: Date.now() / 1000, mtime_ns: mtime };
      });
    },
    // Both mark the file as repaired for this tab, so the reload after them boots normally even with ?broken.
    restore_backup: function () { try { sessionStorage.setItem('rm_repaired', '1'); } catch (e) {} return sleep(200).then(function () { return { ok: true, message: 'Restored the last good backup (mock).' }; }); },
    reset_config: function () { try { sessionStorage.setItem('rm_repaired', '1'); } catch (e) {} return sleep(200).then(function () { return { ok: true, message: 'Reset to the default menus (mock).' }; }); },
    preview_ring: function (cfg, menuId, hover) {
      return sleep(60 + lag).then(function () {
        var m = cfg && cfg.menus && cfg.menus[menuId];
        if (!m || !(m.items || []).length) return { image: null, problems: ['menu ' + menuId + ' has no usable items'] };
        if (hover === 0 && menuId === 'brushes' && M.preview_ring_hover0) return M.preview_ring_hover0;
        return M.preview_ring[menuId] || M.preview_ring.brushes;
      });
    },
    preview_animation: function (cfg, menuId) {
      return sleep(350 + lag).then(function () { return M.preview_animation; });
    },
    get_options: function () { return sleep(10).then(function () { return clone(M.get_options); }); },
    get_library: function () { return sleep(250).then(function () { return clone(M.get_library); }); },
    get_thumbs: function (names) {
      return sleep(70).then(function () {
        var out = {};
        (names || []).forEach(function (n) { out[n] = (M.get_thumbs && M.get_thumbs[n]) || null; });
        return out;
      });
    },
    get_auto_slots: function (cfg, menuId) {
      return sleep(30).then(function () { return { slots: menuId === 'brushes' ? ['Pinch', null] : [] }; });
    },
    get_suggestions: function () { return sleep(60).then(function () { return clone(M.get_suggestions); }); },
    get_status: function () {
      ticks++;
      return sleep(40).then(function () {
        var s = clone(M.get_status);
        s.app_log.push(new Date().toISOString().replace('T', ' ').slice(0, 23) + " mock refresh #" + ticks);
        s.app_log = s.app_log.slice(-12);
        if (q.get('status') === 'down') { s.app_running = false; s.zbrush_running = false; s.listener = null; s.last_pick = null; }
        return s;
      });
    },
    start_app: function () { return sleep(300).then(function () { return { ok: true, message: 'Started (mock: nothing was launched).' }; }); },
    open_folder: function (which) { console.log('[mock] open_folder', which); return Promise.resolve(true); },
    get_zscript_bridge: function () {
      var z = JSON.parse(localStorage.getItem('rm_zscript') || '{}');
      return sleep(120).then(function () { return { bundled: true, installs: [
        { name: 'ZBrush 2022', year: 2022, path: 'C:\\Programs\\ZBrush 2022', python: false, installed: !!z.a, current: !!z.a, zplugs: 'C:\\Programs\\ZBrush 2022\\ZStartup\\ZPlugs64' },
        { name: 'ZBrush 2024', year: 2024, path: 'C:\\Program Files\\Maxon ZBrush 2024', python: false, installed: true, current: false, zplugs: 'C:\\Program Files\\Maxon ZBrush 2024\\ZStartup\\ZPlugs64' }] }; });
    },
    install_zscript_bridge: function () { try { localStorage.setItem('rm_zscript', '{"a":1}'); } catch (e) {} return sleep(300).then(function () { return { ok: true, message: 'Installed (mock). Restart ZBrush so it loads the plugin.' }; }); },
    remove_zscript_bridge: function () { try { localStorage.removeItem('rm_zscript'); } catch (e) {} return sleep(200).then(function () { return { ok: true, message: 'Removed (mock).' }; }); },
    add_zbrush_folder: function () { return Promise.resolve({ ok: false, cancelled: true }); },
    get_prefs: function () { return Promise.resolve(JSON.parse(localStorage.getItem('rm_prefs') || '{"show_licence": true}')); },
    set_pref: function (k, v) { var p = JSON.parse(localStorage.getItem('rm_prefs') || '{"show_licence": true}'); p[k] = v; try { localStorage.setItem('rm_prefs', JSON.stringify(p)); } catch (e) {} return Promise.resolve(p); },
    set_dirty: function () { return Promise.resolve(true); },
    close_now: function () { console.log('[mock] close_now'); return Promise.resolve(true); },
    win_minimize: function () { return Promise.resolve(); },
    win_close: function () { return Promise.resolve(); },
    win_toggle_maximize: function () { return Promise.resolve(false); },
    win_is_maximized: function () { return Promise.resolve(false); },
    get_app_info: function () { return Promise.resolve({ version: '0.6.0' }); },
    check_update: function () { return sleep(300).then(function () { return q.has('update') ? { newer: true, current: '0.6.0', latest: '0.7.0', url: 'https://github.com/combwizard/zbrush-radial-menu/releases' } : { newer: false, current: '0.6.0', latest: '0.6.0', url: 'https://github.com/combwizard/zbrush-radial-menu/releases' }; }); },
    open_url: function (url) { console.log('[mock] open_url', url); return Promise.resolve(true); },
  };
  window.pywebview = { api: api };
  setTimeout(function () { window.dispatchEvent(new Event('pywebviewready')); }, 0);
})();
