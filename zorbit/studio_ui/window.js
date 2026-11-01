// Custom window chrome: the header replaces the Windows title bar (studio.py removes it).
// Dragging is native: the header has `app-region: drag` and WebView2 non-client regions are enabled.
(function () {
  var root = document.documentElement;
  function api() { return window.pywebview && window.pywebview.api; }
  function setMax(on) {
    root.classList.toggle('is-max', !!on);
    var btn = document.getElementById('winMax'), label = on ? 'Restore' : 'Maximise';
    if (btn) { btn.title = label; btn.setAttribute('aria-label', label); }
  }
  function call(name, arg) {
    var a = api();
    if (!a || typeof a[name] !== 'function') return Promise.resolve(null);   // mock mode: no window
    return arg === undefined ? a[name]() : a[name](arg);
  }
  function wire() {
    var min = document.getElementById('winMin'), max = document.getElementById('winMax'),
        close = document.getElementById('winClose'), chip = document.getElementById('versionChip');
    if (min) min.addEventListener('click', function () { call('win_minimize'); });
    if (max) max.addEventListener('click', function () { call('win_toggle_maximize').then(setMax); });
    if (close) close.addEventListener('click', function () { call('win_close'); });
    call('get_app_info').then(function (info) {
      if (info && chip && !chip.classList.contains('has-update')) chip.textContent = 'v' + info.version;
    });
    if (chip) chip.addEventListener('click', function () {
      var u = window.RadialUpdate.last;     // a newer release (not one the user skipped): the update dialog (app.js)
      if (u && u.newer && !u.skipped && window.__studioUpdate) { window.__studioUpdate(u); return; }
      call('open_url', chip.dataset.url || 'https://github.com/combwizard/zorbit/releases');
    });
    checkUpdate();
    call('win_is_maximized').then(setMax);
  }
  // Update check (Settings > Studio > Check for updates): when GitHub has a newer release, the arrow dot beside the two
  // versions stacked, the new one on top and the current one under it.
  var UPDATE_DOT = '<svg class="upd-dot" viewBox="0 0 12 12" width="11" height="11" aria-hidden="true">' +
    '<circle cx="6" cy="6" r="6" fill="currentColor"/><path d="M6 8.7V3.6M3.8 5.7L6 3.5l2.2 2.2" fill="none" ' +
    'stroke="var(--on-accent)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  function checkUpdate() {
    var chip = document.getElementById('versionChip');
    if (!chip) return Promise.resolve(null);
    // Resolves with the reply ({current, latest, url, newer, can_install, skipped}; latest is null when GitHub was not reached) so Settings can say what happened.
    return window.RadialUpdate.pending = call('check_update').then(function (u) {
      if (!u) return null;
      window.RadialUpdate.last = u;
      var shown = !!(u.newer && !u.skipped);   // "Don't remind me again" for this version: the plain chip
      chip.dataset.url = shown ? u.url : 'https://github.com/combwizard/zorbit/releases/tag/v' + u.current;
      chip.classList.toggle('has-update', shown);
      if (shown) {
        chip.innerHTML = '<span class="upd-vers"><span class="upd-old">v' + u.current + '</span><span class="upd-new">v' + u.latest + '</span></span>' + UPDATE_DOT;
        chip.title = 'Version ' + u.latest + ' is available. ' + (u.can_install ? 'Click to install it.' : 'Click to download it.');
      } else {
        chip.textContent = 'v' + u.current;
        chip.title = 'Release notes';
      }
      return u;
    }, function () { return { latest: null, newer: false }; });
  }
  // last: the latest reply; pending: the check under way, for a Settings screen drawn before it answers.
  window.RadialUpdate = { check: checkUpdate, last: null, pending: null };
  window.RadialWin = { setMax: setMax };
  if (window.pywebview && window.pywebview.api) wire();
  else window.addEventListener('pywebviewready', wire, { once: true });
})();
// Keep the maximise/restore icon in step with Windows (double-click on the header, Win+Up, snapping).
(function () {
  var t = null;
  window.addEventListener('resize', function () {
    clearTimeout(t);
    t = setTimeout(function () {
      var a = window.pywebview && window.pywebview.api;
      if (a && a.win_is_maximized) a.win_is_maximized().then(function (on) {
        window.RadialWin.setMax(on);
      });
    }, 120);
  });
})();
