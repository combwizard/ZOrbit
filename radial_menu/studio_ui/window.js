// Custom window chrome: the header replaces the Windows title bar (studio.py removes it).
// Dragging is native: the header has `app-region: drag` and WebView2 non-client regions are enabled.
(function () {
  var root = document.documentElement;
  function api() { return window.pywebview && window.pywebview.api; }
  function setMax(on) { root.classList.toggle('is-max', !!on); }
  function call(name) {
    var a = api();
    if (!a || typeof a[name] !== 'function') return Promise.resolve(null);   // mock mode: no window
    return a[name]();
  }
  function wire() {
    var min = document.getElementById('winMin'), max = document.getElementById('winMax'),
        close = document.getElementById('winClose'), chip = document.getElementById('versionChip');
    if (min) min.addEventListener('click', function () { call('win_minimize'); });
    if (max) max.addEventListener('click', function () { call('win_toggle_maximize').then(setMax); });
    if (close) close.addEventListener('click', function () { call('win_close'); });
    call('get_app_info').then(function (info) { if (info && chip) chip.textContent = 'v' + info.version; });
    call('win_is_maximized').then(setMax);
  }
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
