/* Live ring demo. Ports MODES / _slot_state / _compose and the fans from zorbit/ring.py. Classic script. */
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
  var FAN_SLOT = 0.86;
  var FAN_DEPTH = 3;
  var FAN_SPAN = [130, 110];
  var FAN_TURNS = [0, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90];
  var FAN_MS = 220;
  var FAN_GRACE = 120;

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
      fan: true,
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
      fan: true,
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
      fan: true,
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

  var NS = 'http://www.w3.org/2000/svg';

  /* A slot path is [ring index, fan index, ...]; its key names it in this.fans. */
  function key(path) { return path.join('.'); }

  function startsWith(path, head) { return key(path.slice(0, head.length)) === key(head); }

  /* Angle a, in radians, brought into -pi..pi. */
  function wrap(a) {
    a = (a + Math.PI) % (2 * Math.PI);
    if (a < 0) a += 2 * Math.PI;
    return a - Math.PI;
  }

  function RingDemo(mount, opts) {
    opts = opts || {};
    this.mount = mount;
    this.onPick = opts.onPick || function () {};
    this.bounds = opts.bounds || null;     /* fans stay inside this element ... */
    this.topBar = opts.topBar || null;     /* ... and below this one */
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
    this.openPath = [];                        /* path of open fans, e.g. [8, 7] */
    this.fans = {};
    this._layouts = {};
    this._outTimer = 0;
    this.work = null;
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
    /* the gaps between fan slots lie outside the ring's box: follow the cursor there too */
    this._onMove = function (e) {
      if (!self.root || self.press || !self.openPath.length || self.root.contains(e.target)) return;
      self._pointer(e);
    };
    window.addEventListener('pointermove', this._onMove);
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
    this.openPath = [];
    this.fans = {};
    this._layouts = {};
    clearTimeout(this._outTimer);
    this._outTimer = 0;
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
      var s = self._makeSlot(it);
      s.btn.tabIndex = i === 0 ? 0 : -1;
      s.btn.dataset.index = String(i);
      s.btn.addEventListener('click', function (e) {
        e.preventDefault();
        if (e.detail === 0) self._activate(i);   /* keyboard; pointer picks happen on pointerup */
      });
      s.btn.addEventListener('focus', function () {
        self.focusI = i;
        self._focusPath([i]);
      });
      root.appendChild(s.btn);
      root.appendChild(s.lab);
      self.slotEls.push(s.btn);
      self.labelEls.push(s.lab);
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
      if (self.press) return;
      var now = performance.now();
      self._setHover(null, now);
      if (self.openPath.length) self._updateOpen({ path: null, how: null }, now);
    });

    this.mount.appendChild(root);
    this.root = root;
  };

  /* A slot button and its label, not yet placed. */
  RingDemo.prototype._makeSlot = function (it) {
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'ring-slot' + (it.kind === 'menu' ? ' is-menu' : '');
    btn.setAttribute('aria-label', it.label + (it.kind === 'menu' ? ', submenu' : ''));

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
    return { btn: btn, lab: lab };
  };

  RingDemo.prototype._staticSvg = function () {
    var s = this.size;
    var cx = this.centre, cy = this.centre;
    var ns = NS;
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

  /* target: a ring index, a slot path, or null. */
  RingDemo.prototype._setHover = function (target, now) {
    this.hover = target === null || target === undefined ? null : (typeof target === 'number' ? [target] : target);
    this._applyHover(now);
  };

  /* Eases every slot toward its look: hovered if it is under the cursor or on the open path. */
  RingDemo.prototype._applyHover = function (now) {
    var self = this, marks = {};
    [this.hover || [], this.openPath].forEach(function (p) {
      for (var k = 1; k <= p.length; k++) marks[key(p.slice(0, k))] = true;
    });
    [{ base: [], hv: this.hv }].concat(this._openFans().map(function (f) { return { base: f.path, hv: f.hv }; }))
      .forEach(function (e) {
        for (var i = 0; i < e.hv.length; i++) {
          var target = marks[key(e.base.concat([i]))] ? 1 : 0;
          if (e.hv[i][1] !== target) e.hv[i] = [self._hoverVal(e.hv, i, now), target, now];
        }
      });
    if (!this.raf) this._start();
  };

  RingDemo.prototype._hoverVal = function (hv, i, now) {
    var h = hv[i];
    var p = Math.min(1, Math.max(0, (now - h[2]) / HOVER_MS));
    return h[0] + (h[1] - h[0]) * EASE(p);
  };

  /* ---- fans: a submenu whose menu says fan opens in place, in an arc beyond its slot ---- */

  RingDemo.prototype._item = function (path) {
    if (!path || !path.length) return null;
    if (path.length === 1) return this.menu.items[path[0]];
    var fan = this.fans[key(path.slice(0, -1))];
    return fan ? fan.menu.items[path[path.length - 1]] : null;
  };

  /* Centre of the slot at path, relative to the ring centre. */
  RingDemo.prototype._nodePos = function (path) {
    if (path.length === 1) return [this.seats[path[0]][0] * this.R, this.seats[path[0]][1] * this.R];
    return this.fans[key(path.slice(0, -1))].pos[path[path.length - 1]];
  };

  RingDemo.prototype._openFans = function () {
    var out = [];
    for (var k = 1; k <= this.openPath.length; k++) out.push(this.fans[key(this.openPath.slice(0, k))]);
    return out;
  };

  /* The page area fans must stay in, relative to the ring centre (the app uses the monitor's). */
  RingDemo.prototype._workArea = function () {
    if (!this.bounds || !this.root) return null;
    var b = this.bounds.getBoundingClientRect(), r = this.root.getBoundingClientRect();
    var top = Math.max(b.top, 0, this.topBar ? this.topBar.getBoundingClientRect().bottom : 0);
    var cx = r.left + this.centre, cy = r.top + this.centre, m = 10;
    return {
      l: Math.max(b.left, 0) + m - cx, r: Math.min(b.right, window.innerWidth) - m - cx,
      t: top + m - cy, b: Math.min(b.bottom, window.innerHeight) - m - cy
    };
  };

  /* With no fan open, lay fans out afresh for where the page has scrolled to. */
  RingDemo.prototype._refreshWork = function () {
    if (this.openPath.length) return;
    this._layouts = {};
    this.work = this._workArea();
  };

  /* True when the slot at path is a submenu that fans out here: its menu says so, it is not already open on
     the way here, it is no deeper than FAN_DEPTH, and it has room (if not, it opens as a ring). */
  RingDemo.prototype._fannable = function (path) {
    var it = this._item(path);
    if (!it || it.kind !== 'menu' || path.length > FAN_DEPTH) return false;
    var m = MENUS[it.menu];
    if (!m || !m.fan || !m.items.length || it.menu === this.menuId) return false;
    for (var k = 1; k < path.length; k++) if (this.fans[key(path.slice(0, k))].menuId === it.menu) return false;
    return this._layoutFor(path).pen <= this.S * FAN_SLOT * 0.5;
  };

  RingDemo.prototype._layoutFor = function (path) {
    var k = key(path), lay = this._layouts[k];
    if (lay) return lay;
    var menu = MENUS[this._item(path).menu];
    var cs = this.S * FAN_SLOT, pad = 4 * this.scale, i, j;
    var anchor = this._nodePos(path), axis;
    if (path.length === 1) {                 /* straight out from the ring centre */
      axis = Math.atan2(anchor[1], anchor[0]);
    } else {                                 /* on along the way the parent fan points */
      var pp = this._nodePos(path.slice(0, -1));
      axis = Math.atan2(anchor[1] - pp[1], anchor[0] - pp[0]);
    }
    var taken = [[0, 0, this.R - this.S * 0.6]];
    for (i = 0; i < this.n; i++) taken.push([this.seats[i][0] * this.R, this.seats[i][1] * this.R, this.S * 0.56 + pad]);
    for (j = 1; j < path.length; j++) {
      this.fans[key(path.slice(0, j))].pos.forEach(function (p) { taken.push([p[0], p[1], cs * 0.56 + pad]); });
    }
    lay = this._layouts[k] = this._fanLayout(path.length, menu.items.length, anchor, axis, taken);
    return lay;
  };

  /* Seats for n slots in an arc around anchor, centred on axis, as _fan_layout in ring.py: spaced so
     neighbours and labels clear, two staggered rows past a size limit, turned away from slots and edges. */
  RingDemo.prototype._fanLayout = function (depth, n, anchor, axis, taken) {
    var cs = this.S * FAN_SLOT, g = cs * 1.3, k, t;
    var span = (depth === 1 ? FAN_SPAN[0] : FAN_SPAN[1]) * Math.PI / 180;
    var r = this.S * (depth === 1 ? 1.5 : 1.3), r2 = r, step = 0;
    if (n > 1) {
      step = 2 * Math.asin(Math.min(1, g / (2 * r)));
      if (step * (n - 1) > span) {
        step = span / (n - 1);
        r = r2 = g / (2 * Math.sin(step / 2));
        if (r > 1.4 * this.R) {              /* too far out: two staggered rows instead */
          r = Math.max(this.S * 1.5, g / (2 * Math.sin(step)));
          var sinS = r * Math.sin(step);
          r2 = Math.max(r + 0.8 * cs, r * Math.cos(step) + Math.sqrt(Math.max(0, g * g - sinS * sinS)));
        }
      }
    }
    var offs = [];
    for (k = 0; k < n; k++) offs.push((k - (n - 1) / 2) * step);
    /* smallest change first: turning a little beats pushing out, which beats turning a lot */
    var tries = [];
    FAN_TURNS.forEach(function (turn) {
      [1, 1.35, 1.7].forEach(function (push, j) { tries.push([Math.abs(turn) + 40 * j, turn, push]); });
    });
    tries.sort(function (a, b) { return a[0] - b[0] || a[1] - b[1] || a[2] - b[2]; });
    var best = null;
    for (t = 0; t < tries.length; t++) {
      var ax = axis + tries[t][1] * Math.PI / 180, dists = [], pos = [];
      for (k = 0; k < n; k++) {
        var d = (k % 2 ? r2 : r) * tries[t][2];
        dists.push(d);
        pos.push([anchor[0] + d * Math.cos(ax + offs[k]), anchor[1] + d * Math.sin(ax + offs[k])]);
      }
      var pen = this._fanPenalty(pos, cs, taken), rank = Math.round(pen / 4);
      if (!best || rank < best.rank || (rank === best.rank && tries[t][0] < best.cost)) {
        best = { rank: rank, cost: tries[t][0], axis: ax, dists: dists, pos: pos, pen: pen };
      }
      if (pen < 4) break;
    }
    var half = (n - 1) * step / 2 + Math.asin(Math.min(1, cs * 0.6 / best.dists[0])) + 6 * Math.PI / 180;
    return {
      axis: best.axis, offs: offs, dists: best.dists, pos: best.pos, pen: best.pen,
      half: Math.min(half, 85 * Math.PI / 180), reach: Math.max.apply(null, best.dists) + cs * 0.75
    };
  };

  /* How badly fan slots at pos overlap discs in taken and leave the work area (pixels; leaving counts 4x). */
  RingDemo.prototype._fanPenalty = function (pos, cs, taken) {
    var rc = cs * 0.56 + 4 * this.scale, w = this.work, pen = 0;
    var e = cs * 0.62, lab = cs * 0.62 + 20 * this.scale;
    pos.forEach(function (p) {
      taken.forEach(function (t) { pen += Math.max(0, rc + t[2] - Math.hypot(p[0] - t[0], p[1] - t[1])); });
      if (w) {
        pen += 4 * (Math.max(0, w.l - (p[0] - e)) + Math.max(0, p[0] + e - w.r) +
                    Math.max(0, w.t - (p[1] - e)) + Math.max(0, p[1] + lab - w.b));
      }
    });
    return pen;
  };

  /* The fan of the slot at path; its elements are made on first use. */
  RingDemo.prototype._fan = function (path) {
    var k = key(path), fan = this.fans[k];
    if (fan) return fan;
    var self = this, it = this._item(path), menu = MENUS[it.menu], cs = this.S * FAN_SLOT;
    fan = { path: path.slice(), menuId: it.menu, menu: menu, cs: cs, hv: [], slotEls: [], labelEls: [], tOpen: 0 };
    var el = document.createElement('div');
    el.className = 'ring-fan';
    el.setAttribute('role', 'group');
    el.setAttribute('aria-label', menu.title);
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'ring-fan-lines');
    svg.setAttribute('aria-hidden', 'true');
    el.appendChild(svg);
    fan.linesEl = svg;
    menu.items.forEach(function (item, i) {
      var s = self._makeSlot(item), p = path.concat([i]);
      s.btn.classList.add('is-fan');
      s.btn.style.setProperty('--slot', cs + 'px');
      s.lab.style.setProperty('--slot', cs + 'px');
      s.btn.addEventListener('click', function (e) {
        e.preventDefault();
        if (e.detail === 0) self._activatePath(p);
      });
      s.btn.addEventListener('focus', function () { self._focusPath(p); });
      el.appendChild(s.btn);
      el.appendChild(s.lab);
      fan.slotEls.push(s.btn);
      fan.labelEls.push(s.lab);
      fan.hv.push([0, 0, 0]);
    });
    this.root.appendChild(el);
    fan.el = el;
    this.fans[k] = fan;
    return fan;
  };

  /* Seats a fan on its layout and draws the dashed lines out to its slots. */
  RingDemo.prototype._placeFan = function (fan, lay) {
    var sc = this.scale, cs = fan.cs, c = this.centre, s = this.size;
    fan.anchor = this._nodePos(fan.path);
    fan.anchorR = fan.path.length === 1 ? this.S / 2 : cs / 2;
    fan.axis = lay.axis; fan.offs = lay.offs; fan.dists = lay.dists; fan.pos = lay.pos;
    fan.half = lay.half; fan.reach = lay.reach;
    var a = this.anim;
    fan.dur = Math.min(a.dur, FAN_MS);
    fan.fade = fan.dur ? Math.max(1, Math.min(a.fade, 150)) : 0;
    fan.stagger = fan.dur ? 25 : 0;
    fan.total = fan.stagger * Math.max(0, fan.pos.length - 1) + Math.max(fan.dur, fan.fade);

    var svg = fan.linesEl;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    svg.setAttribute('width', String(s));
    svg.setAttribute('height', String(s));
    svg.setAttribute('viewBox', '0 0 ' + s + ' ' + s);
    var ax = fan.anchor[0], ay = fan.anchor[1];
    fan.pos.forEach(function (p) {
      var L = Math.hypot(p[0] - ax, p[1] - ay);
      if (L < 1) return;
      var ux = (p[0] - ax) / L, uy = (p[1] - ay) / L;
      var t0 = fan.anchorR * 1.12 + 2 * sc, t1 = L - cs * 0.56 - 2 * sc;
      var line = document.createElementNS(NS, 'line');
      line.setAttribute('x1', c + ax + ux * t0);
      line.setAttribute('y1', c + ay + uy * t0);
      line.setAttribute('x2', c + ax + ux * t1);
      line.setAttribute('y2', c + ay + uy * t1);
      line.setAttribute('stroke', 'rgba(248,107,51,0.75)');
      line.setAttribute('stroke-width', String(1.3 * sc));
      line.setAttribute('stroke-dasharray', 5 * sc + ' ' + 4 * sc);
      svg.appendChild(line);
    });
  };

  RingDemo.prototype._setOpen = function (path, now) {
    var cur = this.openPath, k, self = this;
    clearTimeout(this._outTimer);
    this._outTimer = 0;
    if (key(path) === key(cur)) return;
    for (k = 1; k <= path.length; k++) {
      var p = path.slice(0, k), fan = this._fan(p);
      if (key(cur.slice(0, k)) !== key(p)) {   /* newly opened: grows out of its slot */
        this._placeFan(fan, this._layoutFor(p));
        fan.tOpen = now;
        fan.hv = fan.hv.map(function () { return [0, 0, 0]; });
      }
    }
    this.openPath = path.slice();
    Object.keys(this.fans).forEach(function (fk) {
      var f = self.fans[fk];
      f.el.classList.toggle('open', path.length >= f.path.length && startsWith(path, f.path));
    });
    this._applyHover(now);
  };

  /* Opens and closes fans as the cursor moves: onto a fan submenu's slot opens it, onto anything else closes
     what hangs below it at once, and leaving a fan closes it FAN_GRACE later. */
  RingDemo.prototype._updateOpen = function (hit, now) {
    var self = this, cur = this.openPath, want, at = true;
    if (hit.how === 'disc') {
      want = this._fannable(hit.path) ? hit.path : hit.path.slice(0, -1);
    } else if (hit.how === 'sector') {       /* on the angle of a ring slot, off its disc */
      want = cur.length && cur[0] === hit.path[0] ? hit.path : [];
      at = !want.length;
    } else if (hit.how === 'wedge') {
      want = hit.path;
      at = false;
    } else {
      want = [];
      at = false;
    }
    this._want = want;
    if (key(want) === key(cur)) {
      clearTimeout(this._outTimer);
      this._outTimer = 0;
    } else if (at || startsWith(want, cur)) {
      this._setOpen(want, now);
    } else if (!this._outTimer) {
      this._outTimer = setTimeout(function () {
        self._outTimer = 0;
        self._setOpen(self._want, performance.now());
      }, FAN_GRACE);
    }
  };

  /* Keyboard focus: a fan submenu opens, anything else closes what hangs below it. */
  RingDemo.prototype._focusPath = function (path) {
    var now = performance.now();
    this._refreshWork();
    if (!this._quiet) this._setOpen(this._fannable(path) ? path : path.slice(0, -1), now);
    this._setHover(path, now);
  };

  RingDemo.prototype._inWedge = function (fan, rx, ry) {
    var vx = rx - fan.anchor[0], vy = ry - fan.anchor[1], d = Math.hypot(vx, vy);
    if (d < fan.anchorR || d > fan.reach) return false;
    return Math.abs(wrap(Math.atan2(vy, vx) - fan.axis)) <= fan.half;
  };

  /* Index of the deepest open fan's slot the cursor has gone out past, or null. */
  RingDemo.prototype._fanFlick = function (rx, ry) {
    var fan = this.fans[key(this.openPath)];
    var vx = rx - fan.anchor[0], vy = ry - fan.anchor[1];
    var off = wrap(Math.atan2(vy, vx) - fan.axis);
    if (Math.abs(off) > fan.half) return null;
    var k = 0, j;
    for (j = 1; j < fan.offs.length; j++) if (Math.abs(off - fan.offs[j]) < Math.abs(off - fan.offs[k])) k = j;
    return Math.hypot(vx, vy) >= fan.dists[k] + fan.cs * 0.56 ? k : null;
  };

  /* {path, how} at rx, ry from the ring centre. how: 'disc' (on a slot), 'wedge' (in an open fan but on none
     of its slots), 'sector' (in a ring slot's angle) or null. */
  RingDemo.prototype._hit = function (rx, ry) {
    var fans = this._openFans(), f, k, i;
    for (f = fans.length - 1; f >= 0; f--) {   /* deepest first */
      var rr = fans[f].cs / 2 * 1.12 + 4 * this.scale;
      for (k = 0; k < fans[f].pos.length; k++) {
        if (Math.hypot(rx - fans[f].pos[k][0], ry - fans[f].pos[k][1]) <= rr) return { path: fans[f].path.concat([k]), how: 'disc' };
      }
    }
    for (i = 0; i < this.n; i++) {
      if (Math.hypot(rx - this.seats[i][0] * this.R, ry - this.seats[i][1] * this.R) <= this.S / 2) return { path: [i], how: 'disc' };
    }
    for (f = fans.length - 1; f >= 0; f--) {
      if (this._inWedge(fans[f], rx, ry)) return { path: fans[f].path, how: 'wedge' };
    }
    i = this._indexAt(rx + this.centre, ry + this.centre);
    return i === null ? { path: null, how: null } : { path: [i], how: 'sector' };
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
    var rx = e.clientX - rect.left - this.centre;
    var ry = e.clientY - rect.top - this.centre;
    var now = performance.now();
    this._refreshWork();
    var hit = this._hit(rx, ry);
    this._updateOpen(hit, now);
    this._setHover(hit.how === 'disc' || hit.how === 'sector' ? hit.path : null, now);
    this.lastX = e.clientX;
    this.lastY = e.clientY;

    var p = this.press;
    if (p && !p.armed && Math.hypot(e.clientX - p.ox, e.clientY - p.oy) > this.S * 0.35) p.armed = true;
    if (!p || !(e.buttons & 1)) return;

    if (this.openPath.length) {                  /* out past a fan slot: pick it, or fan out further */
      var k = this._fanFlick(rx, ry);
      if (k !== null) {
        var fp = this.openPath.concat([k]);
        if (this._fannable(fp)) this._setOpen(fp, now);
        else this._activatePath(fp);
        return;
      }
    }
    if (hit.how !== 'sector' && hit.how !== 'disc' || hit.path.length !== 1) return;
    var i = hit.path[0];
    var dist = Math.hypot(rx, ry);
    var it = this.menu.items[i];
    if (it.kind === 'menu' && dist >= this.R - this.S * 0.15) {
      if (!this._fannable([i])) this._activate(i);
      return;
    }
    if (it.kind !== 'menu' && dist >= this.flickR) {
      this._activate(i);
    }
  };

  /* Release over a slot picks it; release in the middle goes back up a level. */
  RingDemo.prototype._release = function (e) {
    var p = this.press;
    if (!p || p.id !== e.pointerId) return;
    this.press = null;
    var rect = this.root.getBoundingClientRect();
    var rx = e.clientX - rect.left - this.centre;
    var ry = e.clientY - rect.top - this.centre;
    var hit = this._hit(rx, ry);
    if (hit.how === 'disc' || hit.how === 'sector') {
      if (p.armed) this._activatePath(hit.path);
      return;
    }
    if (hit.how === 'wedge') return;
    if (Math.hypot(rx, ry) < this.D && this.stack.length) this.back();
  };

  RingDemo.prototype._activate = function (i) {
    this._activatePath([i]);
  };

  RingDemo.prototype._activatePath = function (path) {
    var it = this._item(path);
    if (!it) return;
    if (it.kind === 'menu') {
      this._refreshWork();
      if (this._fannable(path)) {            /* a fan opens in place; releasing on its slot keeps it open */
        if (!startsWith(this.openPath, path)) this._setOpen(path, performance.now());
        return;
      }
    }
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
      if (this.openPath.length) {
        e.preventDefault();
        var inFan = document.activeElement && document.activeElement.closest &&
          document.activeElement.closest('.ring-fan');
        this._setOpen([], performance.now());
        if (inFan) {                         /* back to the ring, without the focus opening the fan again */
          this._quiet = true;
          this._focusSlot(this.focusI);
          this._quiet = false;
        }
        return;
      }
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
      var h = this._hoverVal(this.hv, i, now);
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
    var fanBusy = this._paintFans(now);
    return openBusy || stillHover || fanBusy;
  };

  /* Open fans: lines fade in and slots grow out of the slot they opened from. True while still moving. */
  RingDemo.prototype._paintFans = function (now) {
    var self = this, busy = false, c = this.centre;
    this._openFans().forEach(function (fan) {
      var el = (now - fan.tOpen) * self.speed;
      if (el < fan.total + 20) busy = true;
      fan.linesEl.style.opacity = String(fan.fade ? Math.min(1, el / fan.fade) : 1);
      var ax = fan.anchor[0], ay = fan.anchor[1];
      for (var k = 0; k < fan.pos.length; k++) {
        var e = 1, alpha = 1;
        if (fan.dur > 0) {
          var ek = el - fan.stagger * k;
          e = self.curve(Math.min(1, Math.max(0, ek / fan.dur)));
          alpha = Math.min(1, Math.max(0, ek / fan.fade));
        }
        var h = self._hoverVal(fan.hv, k, now);
        if (Math.abs(h - fan.hv[k][1]) > 0.001) busy = true;
        var sc = 0.6 + 0.4 * e;
        var px = c + ax + (fan.pos[k][0] - ax) * e;
        var py = c + ay + (fan.pos[k][1] - ay) * e;
        var btn = fan.slotEls[k], lab = fan.labelEls[k];
        btn.style.left = px + 'px';
        btn.style.top = py + 'px';
        btn.style.opacity = String(alpha);
        btn.style.transform = 'scale(' + sc * (1 + 0.12 * h) + ')';
        btn.classList.toggle('hov', h > 0.5);
        btn.style.zIndex = h > 0.5 ? '2' : '';
        lab.style.left = px + 'px';
        lab.style.top = py + (fan.cs / 2) * (1 + 0.12 * h) * sc + 2 * self.scale + 'px';
        lab.style.opacity = String(alpha);
        lab.style.zIndex = h > 0.5 ? '2' : '';
      }
    });
    return busy;
  };

  global.RadialRing = {
    MODES: MODES,
    MODE_NAMES: MODE_NAMES,
    MENUS: MENUS,
    RingDemo: RingDemo
  };
})(window);
