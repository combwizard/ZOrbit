/* Landing page glue: download link, animation chips, toasts, reveal and pointer effects. */
(function () {
  'use strict';

  var RELEASES_API = 'https://api.github.com/repos/combwizard/zorbit/releases/latest';
  var CACHE_KEY = 'zorbit.release.v1';
  var FALLBACK = 'https://github.com/combwizard/zorbit/releases/latest';

  function toast(msg) {
    var host = document.getElementById('toasts');
    if (!host) return;
    var el = document.createElement('div');
    el.className = 'toast';
    el.textContent = msg;
    host.appendChild(el);
    requestAnimationFrame(function () { el.classList.add('in'); });
    setTimeout(function () {
      el.classList.remove('in');
      setTimeout(function () { el.remove(); }, 220);
    }, 2200);
  }

  function setDownloadLinks(url, version) {
    document.querySelectorAll('a.download').forEach(function (a) {
      a.href = url;
      if (version && a.classList.contains('primary')) {
        var label = a.dataset.baseLabel || a.textContent.trim();
        a.dataset.baseLabel = label.indexOf('Download') === 0 ? 'Download' : label;
        if (a.dataset.baseLabel === 'Download') a.textContent = 'Download v' + version;
      }
    });
  }

  function enhanceDownloads() {
    var cached = null;
    try { cached = JSON.parse(sessionStorage.getItem(CACHE_KEY) || 'null'); } catch (e) {}
    if (cached && cached.url) {
      setDownloadLinks(cached.url, cached.version);
      return;
    }
    fetch(RELEASES_API, { headers: { Accept: 'application/vnd.github+json' } })
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(function (data) {
        var assets = data.assets || [];
        var setup = assets.find(function (a) { return /^ZOrbitSetup-.*\.exe$/i.test(a.name); });
        var version = (data.tag_name || '').replace(/^v/, '');
        var url = setup && setup.browser_download_url ? setup.browser_download_url : FALLBACK;
        try { sessionStorage.setItem(CACHE_KEY, JSON.stringify({ url: url, version: version })); } catch (e) {}
        setDownloadLinks(url, setup ? version : null);
      })
      .catch(function () { /* keep FALLBACK href */ });
  }

  function buildAnimRow(ring) {
    var row = document.getElementById('animRow');
    if (!row || !window.RadialRing) return;
    window.RadialRing.MODE_NAMES.forEach(function (name) {
      var chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'anim-chip' + (name === ring.animName ? ' on' : '');
      chip.textContent = name;
      chip.setAttribute('aria-pressed', name === ring.animName ? 'true' : 'false');
      chip.addEventListener('click', function () {
        row.querySelectorAll('.anim-chip').forEach(function (c) {
          c.classList.remove('on');
          c.setAttribute('aria-pressed', 'false');
        });
        chip.classList.add('on');
        chip.setAttribute('aria-pressed', 'true');
        ring.replay(name);
      });
      row.appendChild(chip);
    });
  }

  var SPEED_KEY = 'zorbit.speed.v1';

  function initialSpeed() {
    var input = document.getElementById('speedRange');
    if (!input) return 0.6;
    var saved = null;
    try { saved = localStorage.getItem(SPEED_KEY); } catch (e) {}
    if (saved !== null && !isNaN(Number(saved))) input.value = saved;
    return Number(input.value) || 0.6;
  }

  function speedControl(ring) {
    var input = document.getElementById('speedRange');
    var out = document.getElementById('speedOut');
    if (!input || !out) return;
    function show() {
      var v = Number(input.value);
      out.textContent = (Math.round(v * 100) / 100) + '×';
      var min = Number(input.min), max = Number(input.max);
      input.style.setProperty('--fill', ((v - min) / (max - min) * 100) + '%');
      ring.setSpeed(v);
    }
    input.addEventListener('input', show);
    input.addEventListener('change', function () {
      try { localStorage.setItem(SPEED_KEY, input.value); } catch (e) {}
      ring.replay();
    });
    show();
  }

  function recordingKeys() {
    var host = document.getElementById('keysRec');
    if (!host || !host.dataset.cycle) return;
    var combos = host.dataset.cycle.split('|');
    var i = 0;
    function render(combo, pop) {
      host.querySelectorAll('kbd, i').forEach(function (n) { n.remove(); });
      combo.split('+').forEach(function (k, j) {
        if (j) {
          var plus = document.createElement('i');
          plus.textContent = '+';
          host.appendChild(plus);
        }
        var kbd = document.createElement('kbd');
        kbd.textContent = k;
        if (pop) kbd.className = 'pop';
        host.appendChild(kbd);
      });
    }
    render(combos[0], false);
    if (REDUCE) return;
    var timer = 0;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting && !timer) {
          timer = setInterval(function () { i = (i + 1) % combos.length; render(combos[i], true); }, 1600);
        } else if (!en.isIntersecting && timer) {
          clearInterval(timer);
          timer = 0;
        }
      });
    });
    io.observe(host);
  }

  var REDUCE = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var FINE = window.matchMedia('(hover: hover) and (pointer: fine)').matches;

  function scrollProgress() {
    var bar = document.querySelector('.progress');
    if (!bar) return;
    var queued = false;
    function update() {
      queued = false;
      var max = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.setProperty('--p', max > 0 ? Math.min(1, window.scrollY / max).toFixed(4) : '0');
    }
    window.addEventListener('scroll', function () {
      if (!queued) { queued = true; requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }

  function heroSpotlight() {
    var hero = document.getElementById('hero');
    if (!hero || REDUCE || !FINE) return;
    hero.addEventListener('pointermove', function (e) {
      var r = hero.getBoundingClientRect();
      hero.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      hero.style.setProperty('--my', (e.clientY - r.top) + 'px');
    });
  }

  function tilt() {
    if (REDUCE || !FINE) return;
    document.querySelectorAll('.feature-media, .spotlight-media').forEach(function (el) {
      el.classList.add('tilt');
      el.addEventListener('pointermove', function (e) {
        var r = el.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width;
        var y = (e.clientY - r.top) / r.height;
        el.classList.add('tilting');
        el.style.setProperty('--ry', ((x - 0.5) * 10).toFixed(2) + 'deg');
        el.style.setProperty('--rx', ((0.5 - y) * 8).toFixed(2) + 'deg');
        el.style.setProperty('--gx', (x * 100).toFixed(1) + '%');
        el.style.setProperty('--gy', (y * 100).toFixed(1) + '%');
      });
      el.addEventListener('pointerleave', function () {
        el.classList.remove('tilting');
        el.style.setProperty('--rx', '0deg');
        el.style.setProperty('--ry', '0deg');
      });
    });
  }

  function countUp() {
    var nodes = document.querySelectorAll('.stat-n[data-count]');
    if (!nodes.length || REDUCE) return;
    function fmt(el, v) {
      var dec = Number(el.dataset.decimals || 0);
      return (el.dataset.prefix || '') + v.toFixed(dec);
    }
    function run(el) {
      var from = Number(el.dataset.from || 0);
      var to = Number(el.dataset.count);
      var dur = 1400, t0 = performance.now();
      (function tick(now) {
        var p = Math.min(1, (now - t0) / dur);
        var k = 1 - Math.pow(1 - p, 4);
        el.textContent = fmt(el, from + (to - from) * k);
        if (p < 1) requestAnimationFrame(tick);
      })(t0);
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { run(en.target); io.unobserve(en.target); }
      });
    }, { threshold: 0.6 });
    nodes.forEach(function (el) {
      el.textContent = fmt(el, Number(el.dataset.from || 0));
      io.observe(el);
    });
  }

  var BURST_COLOURS = ['#f86b33', '#ff9a6a', '#f0c040', '#4dc8e9', '#a8df23', '#f0f0f0'];

  function burst(x, y) {
    var n = 28;
    for (var i = 0; i < n; i++) {
      var p = document.createElement('span');
      p.className = 'burst';
      p.style.left = x + 'px';
      p.style.top = y + 'px';
      p.style.background = BURST_COLOURS[i % BURST_COLOURS.length];
      var a = (i / n) * Math.PI * 2 + Math.random() * 0.4;
      var d = 70 + Math.random() * 90;
      var s = 0.6 + Math.random() * 0.9;
      document.body.appendChild(p);
      p.animate([
        { transform: 'translate(0, 0) scale(' + s + ')', opacity: 1 },
        { transform: 'translate(' + Math.cos(a) * d + 'px,' + (Math.sin(a) * d + 30) + 'px) scale(0)', opacity: 0 }
      ], { duration: 700 + Math.random() * 400, easing: 'cubic-bezier(.22,1,.36,1)' })
        .onfinish = (function (el) { return function () { el.remove(); }; })(p);
    }
  }

  function downloadBursts() {
    if (REDUCE) return;
    document.querySelectorAll('a.btn.primary.download').forEach(function (a) {
      a.addEventListener('click', function (e) {
        var r = a.getBoundingClientRect();
        burst(e.clientX || r.left + r.width / 2, e.clientY || r.top + r.height / 2);
      });
    });
  }

  function reviewWall() {
    var wall = document.getElementById('reviewWall');
    if (!wall || REDUCE) return;
    wall.querySelectorAll('.wall-track').forEach(function (track) {
      Array.prototype.slice.call(track.children).forEach(function (card) {
        var copy = card.cloneNode(true);
        copy.setAttribute('aria-hidden', 'true');
        copy.setAttribute('inert', '');
        track.appendChild(copy);
      });
    });
    wall.classList.add('live');

    var btn = document.getElementById('wallPause');
    if (!btn) return;
    btn.hidden = false;
    btn.addEventListener('click', function () {
      btn.setAttribute('aria-pressed', String(wall.classList.toggle('paused')));
    });
  }

  function reveal() {
    var nodes = document.querySelectorAll('.section-head, .price-card, .feature, .spotlight, .wall, .steps li, .stat, .cta > *');
    nodes.forEach(function (n) {
      n.classList.add('reveal');
      var sibs = n.parentElement ? Array.prototype.indexOf.call(n.parentElement.children, n) : 0;
      if (n.matches('.stat, .steps li, .cta > *')) n.style.setProperty('--d', Math.min(sibs, 5) * 90 + 'ms');
    });
    if (REDUCE) {
      nodes.forEach(function (n) { n.classList.add('in'); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) {
          en.target.classList.add('in');
          io.unobserve(en.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
    nodes.forEach(function (n) { io.observe(n); });
  }

  function boot() {
    enhanceDownloads();
    reviewWall();
    reveal();
    scrollProgress();
    heroSpotlight();
    tilt();
    countUp();
    downloadBursts();
    recordingKeys();

    var mount = document.getElementById('ringMount');
    if (!mount || !window.RadialRing) return;

    var ring = new window.RadialRing.RingDemo(mount, {
      speed: initialSpeed(),
      onPick: function (label) { toast('Picked ' + label); }
    });
    buildAnimRow(ring);
    speedControl(ring);

    var replay = document.getElementById('replayBtn');
    if (replay) replay.addEventListener('click', function () { ring.replay(); });

    window.__radialRing = ring;
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
