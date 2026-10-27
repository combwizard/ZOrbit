/* Live ring demo. Ports MODES / _slot_state / _compose from zorbit/ring.py. Classic script. */
(function (global) {
  'use strict';

  function cubicBezier(x1, y1, x2, y2) {
    function bez(t, a, b) {
      return 3 * a * Math.pow(1 - t, 2) * t + 3 * b * (1 - t) * t * t + t * t * t;
    }
    function dbez(t, a, b) {
      return 3 * a * Math.pow(1 - t, 2) + 6 * (b - a) * (1 - t) * t + 3 * (1 - b) * t * t;
    }
    return function (x) {
      if (x <= 0) return 0;
      if (x >= 1) return 1;
      var t = x, i, d;
      for (i = 0; i < 8; i++) {
        d = dbez(t, x1, x2);
        if (Math.abs(d) < 1e-6) break;
        t -= (bez(t, x1, x2) - x) / d;
        t = Math.min(1, Math.max(0, t));
      }
      return bez(t, y1, y2);
    };
  }

  var EASE = cubicBezier(0.25, 0.1, 0.25, 1.0);
  var EASE_OUT = cubicBezier(0.22, 1, 0.36, 1);

  var MODES = {
    smooth: { stagger: 0, dur: 180, fade: 120, curve: [0.34, 1.4, 0.64, 1], scale: 0.8 },
    bounce: { stagger: 0, dur: 340, fade: 160, curve: [0.34, 1.8, 0.5, 1], scale: 0.5 },
    pop:    { stagger: 0, dur: 130, fade: 100, curve: [0.2, 0.9, 0.3, 1], scale: 0.72 },
    zoom:   { stagger: 0, dur: 260, fade: 160, curve: [0.22, 1, 0.36, 1], scale: 1.35 },
    fade:   { stagger: 0, dur: 220, fade: 220, curve: [0.25, 0.1, 0.25, 1], scale: 1.0 },
    drift:  { stagger: 0, dur: 280, fade: 200, curve: [0.22, 1, 0.36, 1], scale: 1.0, drift: 10 },
    fancy:  { stagger: 0, dur: 500, fade: 280, curve: [0.34, 1.56, 0.64, 1], scale: 0.25, travel: 1.0, dot_pop: true },
    spiral: { stagger: 30, dur: 600, fade: 280, curve: [0.2, 0.85, 0.3, 1], scale: 0.2, travel: 1.0, rot: -150, dot_pop: true },
    ripple: { stagger: 0, dur: 550, fade: 280, curve: [0.16, 1, 0.3, 1], scale: 0.6, travel: 0.86, blur: 4, blur_ms: 450, ripples: true, dot_pop: true },
    breath: { stagger: 0, dur: 700, fade: 300, curve: [0.25, 0.8, 0.25, 1], scale: 0.5, travel: 0.4, blur: 6, blur_ms: 600, halo: true, dot_pop: true },
    mist:   { stagger: 0, dur: 600, fade: 300, curve: [0.22, 1, 0.36, 1], scale: 1.15, travel: -0.45, blur: 10, blur_ms: 600, dot_pop: true },
    snappy: { stagger: 0, dur: 0, fade: 0, curve: [0, 0, 1, 1], scale: 1.0 }
  };
  var MODE_NAMES = Object.keys(MODES);
  var HOVER_MS = 120;
  var MAX_SECTOR = 90;

  var MENUS = {
    brushes: {
      title: 'Brushes',
      items: [
        { label: 'Standard', kind: 'brush', icon: 'Standard' },
        { label: 'ClayBuildup', kind: 'brush', icon: 'ClayBuildup' },
        { label: 'Move', kind: 'brush', icon: 'Move' },
        { label: 'DamStandard', kind: 'brush', icon: 'DamStandard' },
        { label: 'TrimDynamic', kind: 'brush', icon: 'TrimDynamic' },
        { label: 'hPolish', kind: 'brush', icon: 'hPolish' },
        { label: 'Inflate', kind: 'brush', icon: 'Inflat' },
        { label: 'More Brushes', kind: 'menu', menu: 'more' },
        { label: 'Tools', kind: 'menu', menu: 'tools' }
      ]
    },
    more: {
      title: 'More Brushes',
      items: [
        { label: 'Pinch', kind: 'brush', icon: 'Pinch' },
        { label: 'Clay', kind: 'brush', icon: 'Clay' },
        { label: 'ClayTubes', kind: 'brush', icon: 'ClayTubes' },
        { label: 'Move Topological', kind: 'brush', icon: 'Move Topological' },
        { label: 'SnakeHook', kind: 'brush', icon: 'SnakeHook' },
        { label: 'Flatten', kind: 'brush', icon: 'Flatten' },
        { label: 'Layer', kind: 'brush', icon: 'Layer' },
        { label: 'Slash3', kind: 'brush', icon: 'Slash3' }
      ]
    },
    tools: {
      title: 'Tools',
      items: [
        { label: 'Clear Mask', kind: 'press' },
        { label: 'Invert Mask', kind: 'press' },
        { label: 'View Mask', kind: 'toggle' },
        { label: 'Symmetry', kind: 'toggle' },
        { label: 'PolyFrame', kind: 'toggle' },
        { label: 'LazyMouse', kind: 'toggle' },
        { label: 'Backface', kind: 'toggle' },
        { label: 'SubDivide', kind: 'menu', menu: 'subdiv' },
        { label: 'Fresh Start', kind: 'steps', icon: 'Standard' }
      ]
    },
    subdiv: {
      title: 'SubDivide',
      items: [
        { label: '0.25', kind: 'set' },
        { label: '0.50', kind: 'set' },
        { label: '0.75', kind: 'set' },
        { label: '1.00', kind: 'set' },
        { label: '1.25', kind: 'set' },
        { label: '1.50', kind: 'set' },
        { label: '1.75', kind: 'set' },
        { label: '2.00', kind: 'set' }
      ]
    }
  };

  function glyph(label) {
    if (label.length <= 4) return label;
    return label.split(/\s+/).slice(0, 2).map(function (w) { return w[0]; }).join('').toUpperCase();
  }

  function iconUrl(name) {
    return 'brush-icons/' + encodeURIComponent(name.replace(/ /g, '-')) + '.png';
  }

  /* Warm the cache so icons are decoded before the first open animation. */
  function preloadIcons() {
    Object.keys(MENUS).forEach(function (id) {
      MENUS[id].items.forEach(function (it) {
        if (it.icon) { var im = new Image(); im.src = iconUrl(it.icon); }
      });
    });
  }

  function spaceTitle(title) {
    return title.toUpperCase().split('').join(' ');
  }

  function RingDemo(mount, opts) {
    opts = opts || {};
    this.mount = mount;
    this.onPick = opts.onPick || function () {};
    this.radius = 145;
    this.slot = 72;
    this.dead = 38;
    this.animName = 'spiral';
    this.menuId = 'brushes';
    this.stack = [];
    this.reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.raf = 0;
    this.t0 = 0;
    this.hover = null;
    this.focusI = 0;
    this.hv = [];
    this.press = null;
    this.speed = opts.speed || 1;
    this.root = null;
    this.scale = 1;
    preloadIcons();
    this._bind();
    this._resize();
    this.open('brushes', this.animName, true);
  }

  RingDemo.prototype._bind = function () {
    var self = this;
    this._onResize = function () { self._resize(); self._layout(); };
    window.addEventListener('resize', this._onResize);
    this._onKey = function (e) { self._keydown(e); };
    window.addEventListener('keydown', this._onKey);
  };

  RingDemo.prototype._resize = function () {
    var w = this.mount.clientWidth || 420;
    var h = this.mount.clientHeight || 420;
    var avail = Math.min(w, h, 480);
    // mist needs extra room (travel -0.45)
    var base = 2 * (this.radius * 1.45 + this.slot * 0.62 + 34);
    this.scale = Math.min(1, avail / base);
  };

  RingDemo.prototype.open = function (menuId, animName, fromLoad) {
    this.menuId = menuId;
    this.animName = animName || this.animName;
    this.menu = MENUS[menuId];
    this.n = this.menu.items.length;
    this.step = 360 / this.n;
    this.R = this.radius * this.scale;
    this.S = this.slot * this.scale;
    this.D = this.dead * this.scale;
    this.flickR = this.R + this.S * 0.56;
    this.anim = MODES[this.animName] || MODES.smooth;
    this.curve = cubicBezier.apply(null, this.anim.curve);
    this.seats = [];
    var i;
    for (i = 0; i < this.n; i++) {
      var a = (this.step * i) * Math.PI / 180;
      this.seats.push([Math.sin(a), -Math.cos(a)]);
    }
    this.hv = [];
    for (i = 0; i < this.n; i++) this.hv.push([0, 0, 0]);
    this.hover = null;
    this.focusI = 0;
    this._build();
    this._layout();
    if (this.reduce || this.anim.dur <= 0) {
      this.t0 = performance.now() - 1e6;
      this._paint(performance.now());
    } else {
      this.t0 = performance.now();
      this._start();
    }
    if (!fromLoad) this._announce(this.menu.title);
  };

  RingDemo.prototype.replay = function (animName) {
    if (animName) this.animName = animName;
    this.open(this.menuId, this.animName, true);
  };

  /* 1 is the app's real timing; lower is slower. */
  RingDemo.prototype.setSpeed = function (speed) {
    this.speed = Math.min(2, Math.max(0.1, Number(speed) || 1));
  };

  RingDemo.prototype._build = function () {
    var self = this;
    this.mount.innerHTML = '';
    var size = Math.ceil(2 * (this.R * (1 + Math.max(0, -(this.anim.travel || 0))) + this.S * 0.62 + 34 * this.scale));
    size = Math.max(size, Math.ceil(2 * (this.R + this.S * 0.62 + 40 * this.scale)));
    this.size = size;
    this.centre = size / 2;

    var root = document.createElement('div');
    root.className = 'ring';
    root.style.setProperty('--ring-size', size + 'px');
    root.style.setProperty('--slot', this.S + 'px');
    root.setAttribute('role', 'group');
    root.setAttribute('aria-label', this.menu.title + ' radial menu');

    var halo = document.createElement('div');
    halo.className = 'ring-halo';
    root.appendChild(halo);
    this.haloEl = halo;

    var ripples = document.createElement('div');
    ripples.className = 'ring-ripples';
    var r1 = document.createElement('div'); r1.className = 'ring-ripple';
    var r2 = document.createElement('div'); r2.className = 'ring-ripple';
    ripples.appendChild(r1); ripples.appendChild(r2);
    root.appendChild(ripples);
    this.rippleEls = [r1, r2];

    var svg = this._staticSvg();
    root.appendChild(svg);
    this.staticEl = svg;

    var dot = document.createElement('div');
    dot.className = 'ring-dot';
    root.appendChild(dot);
    this.dotEl = dot;

    this.slotEls = [];
    this.labelEls = [];
    this.menu.items.forEach(function (it, i) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ring-slot' + (it.kind === 'menu' ? ' is-menu' : '');
      btn.setAttribute('aria-label', it.label + (it.kind === 'menu' ? ', submenu' : ''));
      btn.tabIndex = i === 0 ? 0 : -1;
      btn.dataset.index = String(i);

      var disc = document.createElement('span');
      disc.className = 'ring-disc';
      if (it.icon) {
        disc.classList.add('has-icon');
        var img = document.createElement('img');
        img.src = iconUrl(it.icon);
        img.alt = '';
        img.draggable = false;
        img.decoding = 'async';
        img.addEventListener('error', function () {
          img.remove();
          disc.classList.remove('has-icon');
          disc.insertBefore(document.createTextNode(glyph(it.label)), disc.firstChild);
        });
        disc.appendChild(img);
      } else {
        disc.textContent = glyph(it.label);
      }
      if (it.kind === 'menu') {
        var badge = document.createElement('span');
        badge.className = 'ring-badge';
        badge.setAttribute('aria-hidden', 'true');
        disc.appendChild(badge);
      }
      btn.appendChild(disc);

      var lab = document.createElement('span');
      lab.className = 'ring-label';
      lab.textContent = it.label;
      lab.setAttribute('aria-hidden', 'true');

      btn.addEventListener('click', function (e) {
        e.preventDefault();
        if (e.detail === 0) self._activate(i);   /* keyboard; pointer picks happen on pointerup */
      });
      btn.addEventListener('focus', function () {
        self.focusI = i;
        self._setHover(i, performance.now());
      });

      root.appendChild(btn);
      root.appendChild(lab);
      self.slotEls.push(btn);
      self.labelEls.push(lab);
    });

    root.addEventListener('pointerdown', function (e) {
      if (e.button !== 0) return;
      e.preventDefault();
      self.press = { id: e.pointerId, armed: true, ox: e.clientX, oy: e.clientY };
      try { root.setPointerCapture(e.pointerId); } catch (err) {}
      self._pointer(e);
    });
    root.addEventListener('pointermove', function (e) { self._pointer(e); });
    root.addEventListener('pointerup', function (e) { self._release(e); });
    root.addEventListener('pointercancel', function () { self.press = null; });
    root.addEventListener('pointerleave', function () {
      if (!self.press) self._setHover(null, performance.now());
    });

    this.mount.appendChild(root);
    this.root = root;
  };

  RingDemo.prototype._staticSvg = function () {
    var s = this.size;
    var cx = this.centre, cy = this.centre;
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'ring-static');
    svg.setAttribute('viewBox', '0 0 ' + s + ' ' + s);
    svg.setAttribute('width', String(s));
    svg.setAttribute('height', String(s));
    svg.setAttribute('aria-hidden', 'true');

    function circle(r, a) {
      var c = document.createElementNS(ns, 'circle');
      c.setAttribute('cx', cx); c.setAttribute('cy', cy); c.setAttribute('r', r);
      c.setAttribute('fill', 'none');
      c.setAttribute('stroke', 'rgba(248,107,51,' + a + ')');
      c.setAttribute('stroke-width', '1');
      svg.appendChild(c);
    }
    circle(this.R * 0.28, 0.05);
    circle(this.R * 0.52, 0.03);
    circle(this.R * 0.76, 0.02);

    var r0 = 8 * this.scale;
    var r1 = this.R - this.S / 2 - 6 * this.scale;
    var i;
    for (i = 0; i < this.n; i++) {
      var ux = this.seats[i][0], uy = this.seats[i][1];
      var sub = this.menu.items[i].kind === 'menu';
      var line = document.createElementNS(ns, 'line');
      line.setAttribute('x1', cx + ux * r0);
      line.setAttribute('y1', cy + uy * r0);
      line.setAttribute('x2', cx + ux * r1);
      line.setAttribute('y2', cy + uy * r1);
      line.setAttribute('stroke', sub ? 'rgba(77,200,233,0.35)' : 'rgba(248,107,51,0.30)');
      line.setAttribute('stroke-width', '1');
      svg.appendChild(line);
    }

    var title = document.createElementNS(ns, 'text');
    title.setAttribute('x', cx);
    title.setAttribute('y', cy + 18 * this.scale);
    title.setAttribute('text-anchor', 'middle');
    title.setAttribute('fill', 'rgba(248,107,51,0.85)');
    title.setAttribute('font-size', String(Math.max(9, 9 * this.scale)));
    title.setAttribute('font-family', 'Segoe UI, system-ui, sans-serif');
    title.setAttribute('font-weight', '700');
    title.setAttribute('letter-spacing', '0.14em');
    title.textContent = spaceTitle(this.menu.title);
    svg.appendChild(title);

    var hint = document.createElementNS(ns, 'text');
    hint.setAttribute('x', cx);
    hint.setAttribute('y', cy + 30 * this.scale);
    hint.setAttribute('text-anchor', 'middle');
    hint.setAttribute('fill', 'rgba(255,255,255,0.22)');
    hint.setAttribute('font-size', String(Math.max(8, 8 * this.scale)));
    hint.setAttribute('font-family', 'Segoe UI, system-ui, sans-serif');
    hint.textContent = 'click or drag';
    svg.appendChild(hint);

    return svg;
  };

  RingDemo.prototype._layout = function () {
    /* seats are applied each frame; nothing sticky besides size */
  };

  RingDemo.prototype._openMs = function () {
    var a = this.anim;
    var tail = Math.max(a.dur, a.fade, a.blur_ms || 0, a.dot_pop ? 420 : 0);
    return a.stagger * Math.max(0, this.n - 1) + tail + 40;
  };

  RingDemo.prototype._slotState = function (i, now) {
    var a = this.anim;
    var el = (now - this.t0) * this.speed - a.stagger * i;
    if (a.dur <= 0) return { sc: 1, alpha: 1, dx: 0, dy: 0, rot: 0, blur: 0 };
    var p = Math.min(1, Math.max(0, el / a.dur));
    var e = this.curve(p);
    var alpha = a.fade ? Math.min(1, Math.max(0, el / a.fade)) : 1;
    var sc = a.scale + (1 - a.scale) * e;
    var travel = (a.travel || 0) * (1 - e);
    var ux = this.seats[i][0], uy = this.seats[i][1];
    var dx = -ux * this.R * travel;
    var dy = -uy * this.R * travel + (a.drift || 0) * this.scale * (1 - e);
    var rot = (a.rot || 0) * (1 - e);
    var blur = 0;
    if (a.blur) {
      var bp = Math.min(1, Math.max(0, el / a.blur_ms));
      blur = a.blur * this.scale * (1 - EASE_OUT(bp));
    }
    return { sc: sc, alpha: alpha, dx: dx, dy: dy, rot: rot, blur: blur };
  };

  RingDemo.prototype._setHover = function (idx, now) {
    var i;
    for (i = 0; i < this.n; i++) {
      var target = i === idx ? 1 : 0;
      if (this.hv[i][1] !== target) {
        var cur = this._hoverVal(i, now);
        this.hv[i] = [cur, target, now];
      }
    }
    this.hover = idx;
    if (!this.raf) this._start();
  };

  RingDemo.prototype._hoverVal = function (i, now) {
    var h = this.hv[i];
    var p = Math.min(1, Math.max(0, (now - h[2]) / HOVER_MS));
    return h[0] + (h[1] - h[0]) * EASE(p);
  };

  RingDemo.prototype._indexAt = function (x, y) {
    var dx = x - this.centre, dy = y - this.centre;
    var dist = Math.hypot(dx, dy);
    if (dist < this.D) return null;
    var ang = (Math.atan2(dx, -dy) * 180 / Math.PI + 360) % 360;
    var i = Math.round(ang / this.step) % this.n;
    var off = Math.abs((ang - i * this.step + 180) % 360 - 180);
    if (off > MAX_SECTOR / 2) return null;
    return i;
  };

  RingDemo.prototype._pointer = function (e) {
    var rect = this.root.getBoundingClientRect();
    var x = e.clientX - rect.left;
    var y = e.clientY - rect.top;
    var i = this._indexAt(x, y);
    var now = performance.now();
    this._setHover(i, now);
    this.lastX = e.clientX;
    this.lastY = e.clientY;

    var p = this.press;
    if (p && !p.armed && Math.hypot(e.clientX - p.ox, e.clientY - p.oy) > this.S * 0.35) p.armed = true;

    if (i !== null && p && (e.buttons & 1)) {
      var dist = Math.hypot(x - this.centre, y - this.centre);
      var it = this.menu.items[i];
      if (it.kind === 'menu' && dist >= this.R - this.S * 0.15) {
        this._activate(i);
        return;
      }
      if (it.kind !== 'menu' && dist >= this.flickR) {
        this._activate(i);
      }
    }
  };

  /* Release over a slot picks it; release in the middle goes back up a level. */
  RingDemo.prototype._release = function (e) {
    var p = this.press;
    if (!p || p.id !== e.pointerId) return;
    this.press = null;
    var rect = this.root.getBoundingClientRect();
    var x = e.clientX - rect.left;
    var y = e.clientY - rect.top;
    var i = this._indexAt(x, y);
    if (i !== null) {
      if (p.armed) this._activate(i);
      return;
    }
    if (Math.hypot(x - this.centre, y - this.centre) < this.D && this.stack.length) this.back();
  };

  RingDemo.prototype._activate = function (i) {
    var it = this.menu.items[i];
    if (!it) return;
    if (it.kind === 'menu' && it.menu && MENUS[it.menu]) {
      this.stack.push(this.menuId);
      this.open(it.menu, this.animName, true);
      if (this.press) {
        /* the same press carries on into the submenu, but must move before a release picks */
        this.press.armed = false;
        this.press.ox = this.lastX;
        this.press.oy = this.lastY;
      }
      return;
    }
    this.press = null;
    this.onPick(it.label);
    var self = this;
    setTimeout(function () { self.replay(); }, 450);
  };

  RingDemo.prototype.back = function () {
    if (!this.stack.length) return;
    var id = this.stack.pop();
    this.open(id, this.animName, true);
  };

  RingDemo.prototype._keydown = function (e) {
    if (!this.root || !this.mount.contains(document.activeElement) && document.activeElement !== document.body) {
      /* still allow Esc when focus is inside the ring */
    }
    var inRing = this.root && (this.root.contains(document.activeElement) || document.activeElement === this.root);
    if (e.key === 'Escape') {
      if (this.stack.length) {
        e.preventDefault();
        this.back();
      }
      return;
    }
    if (!inRing && document.activeElement && document.activeElement.classList &&
        !document.activeElement.classList.contains('ring-slot')) return;

    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      this.focusI = (this.focusI + 1) % this.n;
      this._focusSlot(this.focusI);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      this.focusI = (this.focusI - 1 + this.n) % this.n;
      this._focusSlot(this.focusI);
    } else if (e.key === 'Enter' || e.key === ' ') {
      if (document.activeElement && document.activeElement.classList.contains('ring-slot')) {
        /* click handler fires */
      }
    } else if (e.key === 'Home') {
      e.preventDefault();
      this._focusSlot(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      this._focusSlot(this.n - 1);
    }
  };

  RingDemo.prototype._focusSlot = function (i) {
    var j;
    for (j = 0; j < this.n; j++) this.slotEls[j].tabIndex = j === i ? 0 : -1;
    this.focusI = i;
    this.slotEls[i].focus();
    this._setHover(i, performance.now());
  };

  RingDemo.prototype._announce = function () {};

  RingDemo.prototype._start = function () {
    var self = this;
    if (this.raf) cancelAnimationFrame(this.raf);
    var tick = function (now) {
      var busy = self._paint(now);
      if (busy) self.raf = requestAnimationFrame(tick);
      else self.raf = 0;
    };
    this.raf = requestAnimationFrame(tick);
  };

  RingDemo.prototype._paint = function (now) {
    var el = (now - this.t0) * this.speed;
    var a = this.anim;
    var i;

    if (el < 100 && a.dur > 0) this.staticEl.classList.remove('show');
    else this.staticEl.classList.add('show');

    if (a.halo) {
      var hp = EASE_OUT(Math.min(1, el / 900));
      this.haloEl.style.opacity = String(hp > 0.01 ? 1 : 0);
      this.haloEl.style.transform = 'scale(' + hp + ')';
    } else {
      this.haloEl.style.opacity = '0';
      this.haloEl.style.transform = 'scale(0)';
    }

    if (a.ripples) {
      for (i = 0; i < 2; i++) {
        var delay = i * 140;
        var p = (el - delay) / 1000;
        var rip = this.rippleEls[i];
        if (p > 0 && p < 1) {
          var rr = 5 * this.scale * (0.1 + 23.9 * EASE_OUT(p));
          rip.style.width = rip.style.height = (rr * 2) + 'px';
          rip.style.opacity = String(0.9 * (1 - p));
          rip.style.transform = 'translate(-50%, -50%)';
        } else {
          rip.style.opacity = '0';
        }
      }
    } else {
      this.rippleEls[0].style.opacity = '0';
      this.rippleEls[1].style.opacity = '0';
    }

    var ds = 1;
    if (a.dot_pop) {
      var dp = Math.min(1, el / 420);
      ds = dp < 0.6 ? 1.35 * EASE_OUT(dp / 0.6) : 1.35 - 0.35 * EASE((dp - 0.6) / 0.4);
    } else if (a.dur <= 0 || el > 50) {
      ds = 1;
    } else {
      ds = Math.min(1, el / 50);
    }
    this.dotEl.style.transform = 'scale(' + ds + ')';

    var stillHover = false;
    for (i = 0; i < this.n; i++) {
      var st = this._slotState(i, now);
      var h = this._hoverVal(i, now);
      if (Math.abs(h - this.hv[i][1]) > 0.001) stillHover = true;
      var k = st.sc * (1 + 0.12 * h);
      var ux = this.seats[i][0], uy = this.seats[i][1];
      var px = this.centre + ux * this.R + st.dx;
      var py = this.centre + uy * this.R + st.dy;
      var btn = this.slotEls[i];
      var lab = this.labelEls[i];
      /* PIL rotate is counter-clockwise; CSS is clockwise — negate */
      var rot = -st.rot;
      btn.style.left = px + 'px';
      btn.style.top = py + 'px';
      btn.style.opacity = String(st.alpha);
      btn.style.transform = 'scale(' + k + ') rotate(' + rot + 'deg)';
      if (st.blur > 0.3) btn.style.filter = 'blur(' + st.blur + 'px)';
      else btn.style.filter = '';
      if (h > 0.5) btn.classList.add('hov');
      else btn.classList.remove('hov');

      var ly = py + (this.S / 2) * (1 + 0.12 * h) * st.sc + 2 * this.scale;
      lab.style.left = px + 'px';
      lab.style.top = ly + 'px';
      lab.style.opacity = String(st.alpha);
      lab.style.transform = 'translate(-50%, 0)';
    }

    var openBusy = el < this._openMs() + (a.ripples ? 1000 : 0);
    return openBusy || stillHover;
  };

  global.RadialRing = {
    MODES: MODES,
    MODE_NAMES: MODE_NAMES,
    MENUS: MENUS,
    RingDemo: RingDemo
  };
})(window);
