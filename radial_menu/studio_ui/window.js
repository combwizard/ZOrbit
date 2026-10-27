// Custom window chrome: the header replaces the Windows title bar (studio.py removes it).
// Dragging is native: the header has `app-region: drag` and WebView2 non-client regions are enabled.
(function () {
  var root = document.documentElement;
  function api() { return window.pywebview && window.pywebview.api; }
  function setMax(on) { root.classList.toggle('is-max', !!on); }
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
      call('open_url', chip.dataset.url || 'https://github.com/combwizard/zbrush-radial-menu/releases/tag/' + chip.textContent.trim());
    });
    checkUpdate();
    call('win_is_maximized').then(setMax);
  }
  // Update check (Settings > Studio > Check for updates): "v0.5.1 (dot) v0.5.3" when GitHub has a newer release.
  var UPDATE_DOT = '<svg class="upd-dot" viewBox="0 0 12 12" width="11" height="11" aria-hidden="true">' +
    '<circle cx="6" cy="6" r="6" fill="currentColor"/><path d="M6 8.7V3.6M3.8 5.7L6 3.5l2.2 2.2" fill="none" ' +
    'stroke="#141416" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  function checkUpdate() {
    var chip = document.getElementById('versionChip');
    if (!chip) return Promise.resolve(null);
    // Resolves with the reply ({current, latest, url, newer}; latest is null when GitHub was not reached) so Settings can say what happened.
    return call('check_update').then(function (u) {
      if (!u) return null;
      window.RadialUpdate.last = u;
      chip.dataset.url = u.url;
      chip.classList.toggle('has-update', !!u.newer);
      if (u.newer) {
        chip.innerHTML = '<span>v' + u.current + '</span>' + UPDATE_DOT + '<span class="upd-new">v' + u.latest + '</span>';
        chip.title = 'Version ' + u.latest + ' is available. Click for its release notes.';
      } else {
        chip.textContent = 'v' + u.current;
        chip.title = 'Release notes';
      }
      return u;
    }, function () { return { latest: null, newer: false }; });
  }
  window.RadialUpdate = { check: checkUpdate };
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
        document.documentElement.classList.toggle('is-max', !!on);
      });
    }, 120);
  });
})();
