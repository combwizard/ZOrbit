/* ZOrbit Studio: the Look screen.

   Loaded after app.js, which is one closure and hands over what this file needs as window.ZStudio (see "What look-screen.js
   needs" there). look.js (window.ZLook) resolves and edits looks; this file draws the controls.

   - view.target says what is being edited: { level: 'global' }, { level: 'menu', menu } or { level: 'preset', name } (a look,
     built-in ones read-only). The level bar changes it. Everything that reads or writes a look key goes through lookAccess(key),
     which is the one place that knows the target.
   - lookRow puts the source badge and the "Reset" wording on a control row; a control that is not a row (cards, role colours) is
     built from the same pieces. The badge says where the value comes from (Default, Theme, Look: X, Global, This menu); clicking
     one that is inherited goes to the level that owns it.
   - The groups come from the schema (ZLook.groups). A new key joins a group in the schema; a new group is one more builder in
     GROUP_BUILD below.
   - The gallery under the preview lists the built-in looks and the user's: Apply (which removes the settings that would hide the
     look, with an undo toast), New from current, Duplicate, Rename, Delete, Edit. Its pictures come from preview_looks.
   - The preview is a RingView (app.js): the picture with an SVG overlay drawn from the layout map the backend sends, so a slot lights up
     under the pointer in its own shape. In Full mode a click on a slot opens the slot level for it (view.target.slot is the index of
     the item in menu.items); Escape or a click on empty space goes back to the menu level, and the arrow keys step through the slots.
   - The Opening group is not a look group: the open animation is a ring setting (and a menu's own), so it is drawn here from ring.animation and
     menu.animation by hand. Its Play button, and a pick, play the animation on the preview in place of the still (lookPlayer).
   - In Full mode the groups fold (foldSection in app.js). Whether one is open is view.fold[id] when the person chose, else Slots, else a group with
     settings of its own at the level; a closed group's heading carries a summary (GROUP_SUM) and how many settings are set here. A chip, a badge
     jump or a problem opens the group it goes to before it scrolls or focuses. Simple mode draws its groups open under a plain heading.
   Without get_options().looks (an older backend) only the global level and the first pass's controls are shown. */
(() => {
  'use strict';
  const K = window.ZStudio, Z = window.ZLook;
  if (!K || !Z) return;                                       // app.js or look.js did not load: app.js shows a note in place of this screen
  const { h, $, $$, S, R, icon, iconBtn, linkBtn, card, foldSection, foldOpen, foldIsOpen, foldSum, choiceCards, sliderRow, toggleSwitch, normHex, commit, tidyRing, usableIdx, menuOf, kindOf,
    isLib, firstTag, isFull, setMode, fullOnlyChanges, RingLoader, SAMPLE_MENU, COLOR_INFO, lookCtx, clearedText, modal, promptModal, popover, undoToast, plural, hasMenu, clamp,
    makeRingView, itemLabel } = K;

  const view = { target: { level: 'global' }, menuId: null, back: null, last: null, pinHover: false, pinOff: false,
    fold: {} };                                               // outlives a rebuild of the screen; fold: group id -> open, the person's own choices only (Full)
  /* The open animation plays into the preview's picture. One player for the screen: a rebuild stops it and points lookImg at the new picture;
     paintPlay is the current build's way of showing the state (the stage class and the Play button). */
  let lookImg = null, paintPlay = null;
  const lookPlayer = K.makePlayer(() => lookImg, () => { if (S.screen === 'look' && R.preview) R.preview(); }, st => { if (paintPlay) paintPlay(st); });      // R belongs to the next screen once Look is left
  const slotT = () => Z.isSlot(view.target);
  const target = () => view.target;
  const presetsOn = () => Z.hasPresets(lookCtx());
  const own = (o, k) => o != null && Object.prototype.hasOwnProperty.call(o, k);
  const isObj = o => o !== null && typeof o === 'object' && !Array.isArray(o);

  /* ---- where each value comes from, in the words of the badge */
  const lookName = n => Z.labelOf(n, lookCtx());
  const RANK = { default: 0, theme: 1, 'global-preset': 2, global: 3, 'menu-preset': 4, menu: 5, slot: 6, preset: 7 };
  const badgeText = (o, name) => ({ default: 'Default', theme: 'Theme', 'global-preset': 'Look: ' + lookName(name), global: 'Global', 'menu-preset': 'Look: ' + lookName(name),
    menu: 'This menu', slot: 'This slot', preset: 'This look' }[o] || o);
  const ownOrigin = () => (slotT() ? 'slot' : { global: 'global', menu: 'menu', preset: 'preset' }[target().level]);
  const badgeTitle = (o, name) => {
    const own1 = o === ownOrigin();
    if (own1) return o === 'slot' ? "Set for this slot only. Reset to follow the menu's look." : o === 'preset' ? 'Set in this look. Reset to go back to the default.' : o === 'menu' ? 'Set for this menu only. Reset to follow the level above.' : 'Set here, for every menu. Reset to go back to what the look or the default gives.';
    return ({ default: 'The built-in value. Change the control to set your own.', theme: 'The colour comes from the theme. Change the control to set your own.',
      'global-preset': 'From the look ' + lookName(name) + ', used for all menus. Click to see it.', 'menu-preset': 'From the look ' + lookName(name) + ', used for this menu. Click to see it.',
      global: 'Set for all menus, in Global. Click to go there.', menu: slotT() ? 'Set for this menu. Click to go there.' : '' }[o]) || '';
  };
  const resetWord = () => (target().level === 'global' ? 'Reset to default' : target().level === 'menu' ? 'Reset to inherited' : 'Reset to default');

  /* The values of the target, once per change of the config (S.version) and target. */
  let memo = null;
  const resolved = () => {
    const key = S.version + '|' + JSON.stringify(target()) + '|' + (S.themeEff || '');
    if (!memo || memo.key !== key) memo = { key, res: Z.resolve(S.cfg, target(), lookCtx()) };
    return memo.res;
  };
  const schemaOf = () => Z.prep(lookCtx()).schema;
  const keysHere = () => Z.keysAt(lookCtx(), Z.levelOf(target()));
  const hasKey = k => keysHere().includes(k);
  /* The values the target's menu gives (a slot inherits them): what the controls of a slot need to know about the menu around it. */
  let ambientMemo = null;
  const ambient = () => {
    const key = S.version + '|' + target().menu + '|' + (S.themeEff || '');
    if (!ambientMemo || ambientMemo.key !== key) ambientMemo = { key, vals: Z.explain(S.cfg, { level: 'menu', menu: target().menu }, lookCtx()).values };
    return ambientMemo.vals;
  };
  /* The slot's item and its place among the menu's usable items, for the words around the slot level. */
  const slotInfo = t => {
    const m = menuOf(t.menu), idxs = usableIdx(t.menu), at = idxs.indexOf(t.slot), it = m && m.items ? m.items[t.slot] : null;
    return { it, n: idxs.length, pos: at + 1, label: it ? itemLabel(it) : '', idxs };
  };

  /* One look key as the controls see it. key is 'radius', or 'colors.bg' for one colour. */
  function lookAccess(key) {
    const [k, sub] = key.split('.');
    const read = () => resolved()[k];
    const done = () => { tidyRing(); commit(); if (view.touch) view.touch(); };
    const a = {
      key,
      get: () => (sub ? read().sub[sub].value : read().value),
      eff: () => read().eff,                                  // a colour key's #rrggbb
      origin: () => (sub ? read().sub[sub].origin : read().origin),
      name: () => (sub ? read().sub[sub].name : read().name),
      isSet: () => Z.isSet(S.cfg, target(), key, lookCtx()),
      put: v => { if (Z.set(S.cfg, target(), key, v, lookCtx())) done(); },
      clear: () => { if (Z.clear(S.cfg, target(), key, lookCtx())) done(); },
    };
    a.slider = { get: a.get, put: a.put, clear: a.clear, isSet: a.isSet };     // what sliderRow takes
    return a;
  }
  const valueNow = key => { const r = resolved()[key]; return r ? r.value : undefined; };

  /* What the screen draws from the config: when this is the same before and after an undo, the screen is left alone (and keeps focus). */
  window.lookSig = () => JSON.stringify([S.cfg.ring, S.cfg.looks, Object.entries(S.cfg.menus).map(([id, m]) => [id, m && m.title, m && m.look, m && m.animation, m && Array.isArray(m.items) ? m.items.map(it => it && it.style) : null]), S.themeEff]);

  /* Opens the screen at a level: from a problem, the Menu tab's Edit in Look or the ring-full note. rebuild: the screen is showing already. */
  window.lookOpenAt = (t, rebuild) => {
    if (t.level === 'menu' && hasMenu(t.menuId)) view.target = Number.isInteger(t.slot) ? { level: 'menu', menu: t.menuId, slot: t.slot } : { level: 'menu', menu: t.menuId };
    else if (t.level === 'preset' && t.name && Z.lookDict(S.cfg, t.name, lookCtx())) view.target = { level: 'preset', name: t.name };
    else view.target = { level: 'global' };
    view.back = null;
    if (rebuild && R.look) R.look();
  };

  /* Rebuilt after an undo, a revert or a reload: the control that had focus gets it back (found by its data-fk key, else its label). */
  const lookFk = el => el.dataset.fk || [el.tagName, el.type || '', el.getAttribute('aria-label') || '', (el.closest('[role="radiogroup"]') || el).getAttribute('aria-label') || '', el.dataset.v || ''].join('|');

  /* ---------------------------------------------------------------- the words and pictures of the choice cards */
  const glyph = path => { const g = h('span', { class: 'lk-glyph', 'aria-hidden': 'true' }); g.innerHTML = '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round" stroke-linecap="round">' + path + '</svg>'; return g; };
  const SHAPE = {
    circle: ['Circle', 'Round slots.', '<circle cx="12" cy="12" r="8"/>'],
    rounded: ['Rounded square', 'Square, with corners you can round.', '<rect x="4" y="4" width="16" height="16" rx="4"/>'],
    squircle: ['Squircle', 'Softer than a rounded square.', '<path d="M12 4C18 4 20 6 20 12S18 20 12 20 4 18 4 12 6 4 12 4z"/>'],
    hexagon: ['Hexagon', 'Six sides.', '<path d="M12 3.5l7.4 4.25v8.5L12 20.5l-7.4-4.25v-8.5z"/>'],
    octagon: ['Octagon', 'Eight sides.', '<path d="M8.5 4h7L20 8.5v7L15.5 20h-7L4 15.5v-7z"/>'],
    diamond: ['Diamond', 'A square on its corner.', '<path d="M12 3.5l8.5 8.5-8.5 8.5L3.5 12z"/>'],
  };
  const HUB = {
    dot: ['Dot', 'A small filled dot.', '<circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/>'],
    disc: ['Disc', 'A larger filled disc.', '<circle cx="12" cy="12" r="7" fill="currentColor" stroke="none" opacity=".85"/>'],
    ring: ['Ring', 'An outline, open in the middle.', '<circle cx="12" cy="12" r="6.5"/>'],
    icon: ['Menu icon', 'The menu\'s icon or its first letter.', '<path d="M12 5.5l1.9 4.3 4.6.4-3.5 3 1.1 4.6L12 15.4 7.9 17.8 9 13.2 5.500 10.200l4.600-.4z"/>'],
  };
  const FULL_WHEN = {
    grow: ['Grow', 'The ring gets bigger until every slot fits.'],
    rings: ['Second ring', 'The slots that do not fit go in an outer ring.'],
    more: ['More slot', 'A last slot, More, opens the rest as a submenu.'],
  };
  const LABELS = { name: ['Icon and name', 'Each slot shows its label underneath.'], none: ['Icon only', 'A cleaner ring. Names appear only in this Studio.'] };

  /* ---------------------------------------------------------------- gallery pictures */
  const Thumbs = { cache: new Map(), shown: new Map(), theme: '', timer: 0, busy: false, again: false };
  const themeNow = () => S.themeEff || 'dark';
  const tagSig = () => (S.tags || []).map(t => t.key + t.color).join(',');
  /* A card shows the look itself: drawn over the defaults and the theme (preview_looks base "default"), never over the
     user's own ring settings or menu, so the only things besides the look that change it are the theme and the tags
     (the sample ring carries their colours). Editing a setting therefore never redraws the gallery. */
  const baseSig = () => JSON.stringify([themeNow(), tagSig()]);
  const thumbBase = () => 'default';
  function fetchThumbs() {
    Thumbs.timer = 0;
    if (Thumbs.busy) { Thumbs.again = true; return; }
    const g = view.gallery;
    if (!g) return;
    const need = g.cards().filter(c => !Thumbs.cache.has(c.sig));
    if (!need.length) return;
    Thumbs.busy = true;
    K.call('preview_looks', S.cfg, need.map(c => c.id), thumbBase(), 0.5).catch(() => null).then(res => {
      Thumbs.busy = false;
      for (const c of need) {
        const pic = res && res.looks && res.looks[c.id] && res.looks[c.id].image;
        if (pic) { Thumbs.cache.set(c.sig, pic); Thumbs.shown.set(c.id, pic); }
      }
      while (Thumbs.cache.size > 120) Thumbs.cache.delete(Thumbs.cache.keys().next().value);
      if (view.gallery) view.gallery.paintThumbs();
      if (Thumbs.again) { Thumbs.again = false; fetchThumbs(); }
    });
  }
  const wantThumbs = () => { clearTimeout(Thumbs.timer); Thumbs.timer = setTimeout(fetchThumbs, 250); };

  /* ---------------------------------------------------------------- names */
  const userNames = () => Object.keys(Z.userLooks(S.cfg)).filter(n => Z.nameProblem(n, lookCtx()) === '');
  const NAME_WORDS = { 'name must be': 'A name is 1 to 32 letters, digits, spaces, - or _.', 'that name is a built-in': 'That is the name of a built-in look or a reserved name. Give it another.' };
  function nameError(t, except) {
    const bad = Z.nameProblem(t, lookCtx());
    if (bad) return NAME_WORDS[Object.keys(NAME_WORDS).find(k => bad.startsWith(k))] || bad;
    const clash = userNames().find(n => n.toLowerCase() === t.toLowerCase() && n !== except);
    return clash ? 'There is already a look called “' + clash + '”. Names are the same apart from capitals.' : '';
  }
  function freeName(base) {
    base = base.slice(0, 30);
    for (let n = 1; n < 100; n++) {
      const t = n === 1 ? base : base.slice(0, 29 - String(n).length) + ' ' + n;
      if (!nameError(t, null)) return t;
    }
    return 'My look';
  }

  window.buildLookScreen = root => {
    paintPlay = null; R.preview = null;                       // the player puts the picture back through R.preview, which this build sets again
    lookPlayer.stop();
    fixTarget();
    const target0 = view.target, level0 = target0.level, sl0 = Z.isSlot(target0) ? target0.slot : null, curLevel = sl0 !== null ? 'slot' : level0;
    if (Thumbs.theme !== themeNow()) { Thumbs.cache.clear(); Thumbs.shown.clear(); Thumbs.theme = themeNow(); }
    let badges = [];                                          // repaint functions of the source badges
    const repaints = [];                                      // repaint functions of controls whose look depends on other values
    const sectionRefs = [];                                   // [{ id, card, btn }], in order
    let pinned = null;
    const paintBadges = () => badges.forEach(f => f());

    /* ---- the preview (left column) */
    const img = h('img', { class: 'ring-img', alt: 'Ring preview', draggable: false });
    lookImg = img;
    const dz = h('div', { class: 'dz-ring', 'aria-hidden': 'true' });
    const wrap = h('div', { class: 'mini-wrap' }, dz);
    const cap = h('div', { class: 'mini-cap micro' });
    const stage = h('div', { class: 'mini-stage look-stage', tabindex: '0', role: 'group', dataset: { fk: 'look:stage' },
      'aria-label': isFull() ? 'Ring preview. Click a slot to style it on its own. At the slot level the arrow keys move between slots and Escape goes back to the menu.' : 'Ring preview' },
    h('div', { class: 'stage-rings', 'aria-hidden': 'true' }), wrap, cap);
    let msize = 447, ptok = 0, lastFit = null, hoverPtr = null, glowInView = false;
    const previewCount = () => { const id = previewId(); return id === SAMPLE_MENU ? null : usableIdx(id).length; };
    const ring = makeRingView({ wrap, img, count: previewCount });
    const paintDZ = () => { const k = (wrap.clientWidth || 280) / msize, d = (Number(valueNow('dead_zone') !== undefined ? valueNow('dead_zone') : ambientDead()) || K.ringNum('dead_zone')) * 2 * k; dz.style.width = dz.style.height = d + 'px'; };
    const ambientDead = () => (slotT() ? ambient().dead_zone : undefined);
    const live = () => { paintDZ(); paintBadges(); };
    view.touch = () => { paintDZ(); paintBadges(); repaints.forEach(f => f()); if (view.gallery) view.gallery.refresh(); if (view.sums) view.sums(); };
    const previewId = () => {
      if (target().level === 'menu') return target().menu;
      return view.menuId === SAMPLE_MENU ? SAMPLE_MENU : (view.menuId && menuOf(view.menuId) ? view.menuId : S.menuId);
    };
    /* ring slot i is which item of the menu (its index in menu.items)? null for a More slot or when the layout does not fit. */
    const itemOfSlot = i => { const L = ring.layout(), idxs = usableIdx(previewId()); return L && L.slots[i] && !L.slots[i].more && idxs[i] !== undefined ? idxs[i] : null; };
    const slotOfItem = ix => { const L = ring.layout(); if (!L || ix === null || ix === undefined) return null; for (let i = 0; i < L.slots.length; i++) if (itemOfSlot(i) === ix) return i; return null; };
    const glowPinned = () => slotT() && (view.pinHover || (glowInView && !view.pinOff));
    /* What the picture shows lit: the slot under the pointer, else (when pinned) the selected one. */
    const hoverNow = () => (hoverPtr !== null ? hoverPtr : glowPinned() ? slotOfItem(target().slot) : null);
    const paintRing = () => ring.paint({ hover: hoverNow(), sel: slotT() ? slotOfItem(target().slot) : null });
    /* While a look is being edited, the picture shows a copy of the config in which the menu being previewed uses that look. */
    const previewVariant = id => {
      const t = target();
      if (t.level !== 'preset') return null;
      const mid = id === SAMPLE_MENU ? Object.keys(S.cfg.menus)[0] : id;
      return { key: 'preset:' + t.name + '@' + mid, menu: mid, cfg: () => {
        const c = JSON.parse(JSON.stringify(S.cfg));
        if (mid && c.menus[mid]) c.menus[mid].look = { preset: t.name };
        return c;
      } };
    };
    const paintCap = () => {
      const id = previewId(), m = id === SAMPLE_MENU ? null : menuOf(id), t = target();
      const base = id === SAMPLE_MENU ? 'Sample ring' : 'Preview: ' + ((m && m.title) || id || '');
      cap.textContent = t.level === 'preset' ? base + ' with ' + lookName(t.name) : base;
    };
    const showPicture = res => {
      if (res.image && img.getAttribute('src') !== res.image) img.src = res.image;
      ring.setShown(res.layout || null);
      ring.rebuild();
      paintRing();
    };
    R.preview = async () => {
      paintCap();
      if (lookPlayer.state !== 'idle') return;                // the animation owns the picture until it ends; it calls this again then
      const id = previewId(), sample = id === SAMPLE_MENU, tok = ++ptok;
      const none = !sample && (!menuOf(id) || !usableIdx(id).length);
      stage.classList.toggle('none', none);
      wrap.hidden = none;
      if (none) return;
      const ver = S.version, want = hoverNow();
      const res = await RingLoader.get(id, want, null, sample ? 'tags' : 'main', previewVariant(id));
      if (tok !== ptok || ver !== S.version || !res || lookPlayer.state !== 'idle') return;
      if (res.image) showPicture(res);
      else if (res.error || (res.problems || []).length) cap.textContent = 'No preview: ' + (res.problems || [])[0];
      msize = res.size || msize; paintDZ();
      lastFit = res.fit || null;
      if (paintFit) paintFit();
      paintLive();
    };
    const peek = RingLoader.peek(previewId(), null, null, previewVariant(previewId()));       // a rebuild shows the picture it had at once
    if (peek && peek.image) { img.src = peek.image; ring.setShown(peek.layout || null); msize = peek.size || msize; lastFit = peek.fit || null; }
    new ResizeObserver(() => { ring.rebuild(); paintRing(); }).observe(wrap);

    /* Hover lights a slot and shows its picture with the hover glow; in Full mode a click opens the slot level for it. */
    const setHoverPtr = j => { if (j === hoverPtr || lookPlayer.state !== 'idle') return; hoverPtr = j; stage.classList.toggle('over-slot', j !== null && isFull() && previewId() !== SAMPLE_MENU); paintRing(); R.preview(); };
    stage.addEventListener('pointermove', e => { if (level0 !== 'preset') setHoverPtr(ring.slotAt(e.clientX, e.clientY)); });
    stage.addEventListener('pointerleave', () => setHoverPtr(null));
    const goSlot = (mid, ix) => { view.last = mid; view.target = { level: 'menu', menu: mid, slot: ix }; view.back = null; R.look(); };
    const goMenuLevel = () => { view.target = { level: 'menu', menu: target().menu }; view.back = null; R.look(); };
    stage.addEventListener('click', e => {
      if (!isFull() || level0 === 'preset' || !presetsOn() || previewId() === SAMPLE_MENU || !ring.valid()) return;
      const j = ring.slotAt(e.clientX, e.clientY);
      if (j === null) { if (sl0 !== null) goMenuLevel(); return; }       // empty space: back to the menu
      const ix = itemOfSlot(j);
      if (ix !== null && !(sl0 !== null && ix === target().slot)) goSlot(previewId(), ix);
    });
    stage.addEventListener('keydown', e => {
      if (sl0 === null || e.target !== stage || e.altKey || e.ctrlKey || e.metaKey) return;
      if (e.key === 'Escape') { e.preventDefault(); goMenuLevel(); return; }
      const idxs = usableIdx(target().menu), at = idxs.indexOf(target().slot);
      const to = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? at + 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? at - 1 : e.key === 'Home' ? 0 : e.key === 'End' ? idxs.length - 1 : null;
      if (to === null || !idxs.length) return;
      e.preventDefault();
      goSlot(target().menu, idxs[(to + idxs.length) % idxs.length]);
    });

    const menuOptions = sample => [...Object.entries(S.cfg.menus).map(([id, m]) => h('option', { value: id, selected: id === previewId() }, (m && m.title) || id)),
      sample ? h('option', { value: SAMPLE_MENU, selected: previewId() === SAMPLE_MENU }, 'Sample ring with tags') : null];
    const picker = h('select', { class: 'inp sel', 'aria-label': 'Menu to preview', dataset: { fk: 'look:preview-menu' }, onchange: () => {
      view.menuId = picker.value; R.preview(); paintTagNote(); wantThumbs();
    } }, ...menuOptions(true));
    const pickLabel = h('label', { class: 'look-pick' }, h('span', { class: 'micro' }, 'Preview menu'), picker);
    pickLabel.hidden = level0 === 'menu';
    /* The slot level's line under the picture (read out when the slot changes) and the switch that keeps the hover glow on show. */
    const liveLine = h('div', { class: 'fhint look-live', role: 'status', 'aria-live': 'polite' });
    const glowSw = sl0 !== null ? toggleSwitch(glowPinned(), v => { if (v) { view.pinHover = true; view.pinOff = false; } else { view.pinHover = false; view.pinOff = true; } paintRing(); R.preview(); }, 'Show hover glow') : null;
    const glowRow = glowSw ? h('div', { class: 'look-glowsw' }, h('span', null, 'Show hover glow'), glowSw) : null;
    const paintLive = () => {
      if (sl0 === null) { liveLine.textContent = ''; return; }
      const i = slotInfo(target()), shape = Z.explain(S.cfg, target(), lookCtx()).values.slot_shape;
      liveLine.textContent = i.it ? 'Slot ' + i.pos + ' of ' + i.n + ': ' + i.label + ', ' + (shape || 'circle').replace('rounded', 'rounded square') : '';
    };
    const syncPin = () => { if (glowSw) { const on = glowPinned(), inp = glowSw.querySelector('input'); if (inp.checked !== on) inp.checked = on; } };
    const left = h('aside', { class: 'look-left', 'aria-label': 'Ring preview and looks' }, stage, liveLine, glowRow, pickLabel,
      isFull() ? h('div', { class: 'fhint' }, 'The dashed circle is the dead zone: no slot is picked this close to the centre.') : null);

    /* ---- the open animation, played on the preview */
    let playBtn = null;                                         // the Play button of the Opening group, when the group is on show
    const animTitle = a => { const t = typeof a === 'string' ? a : String(a === undefined || a === null ? '' : a); return t ? t[0].toUpperCase() + t.slice(1) : ''; };
    paintPlay = st => {
      stage.classList.toggle('playing', st === 'playing');      // hides the dashed circle and the hover marks, and ignores the pointer
      if (st !== 'idle') { hoverPtr = null; stage.classList.remove('over-slot'); }
      if (!playBtn) return;
      playBtn.replaceChildren(st === 'loading' ? h('span', { class: 'spin' }) : icon(st === 'playing' ? 'stop' : 'play', 12), st === 'loading' ? 'Rendering...' : (st === 'playing' ? 'Stop' : 'Replay'));
      playBtn.disabled = st === 'loading';
    };
    /* The ring's animation at the global level (even for a menu that has its own), the menu's own or inherited one at the menu level. The sample
       ring is no menu: the first one with something to show stands in. */
    const playNow = () => {
      if (lookPlayer.state === 'loading') return;
      const pid = previewId(), id = pid !== SAMPLE_MENU ? pid : Object.keys(S.cfg.menus).find(m => usableIdx(m).length);
      if (!id || !hasMenu(id) || !usableIdx(id).length) { K.toast('The current menu has no usable items to animate.', { tone: 'warn' }); return; }
      stage.scrollIntoView({ block: 'nearest' });               // the stacked layout of a narrow window
      lookPlayer.play(id, level0 !== 'menu');
    };
    R.lookPlay = playNow;                                       // a pick rebuilds the screen, then plays on the new one

    /* ---- level bar */
    const full = isFull();
    const levelBar = h('div', { class: 'look-levels' }, h('h1', { class: 'look-title' }, 'Look'));
    const goLevel = lv => {
      if (lv === 'menu' || lv === 'slot') {
        const id = view.last && hasMenu(view.last) ? view.last : S.menuId;
        if (!hasMenu(id)) return;
        view.target = { level: 'menu', menu: id };
        if (lv === 'slot') {                                    // the selected item if it is on the ring, else the first one
          const idxs = usableIdx(id);
          const ix = id === S.menuId && idxs.includes(S.itemIdx) ? S.itemIdx : (view.lastSlot && view.lastSlot.menu === id && idxs.includes(view.lastSlot.slot) ? view.lastSlot.slot : idxs[0]);
          if (ix === undefined) return;
          view.target = { level: 'menu', menu: id, slot: ix };
        }
      } else view.target = { level: 'global' };
      view.back = null;
      R.look();
    };
    if (presetsOn()) {
      const lvls = [['global', full ? 'Global' : 'All menus', full ? 'The look every menu starts from.' : 'The look for every menu.'],
        ['menu', 'This menu', full ? 'Only the menu you pick. Whatever you do not set here follows Global.' : 'Only the menu you pick.']];
      if (full) lvls.push(['slot', 'This slot', 'Only one slot of the menu. Whatever you do not set here follows the menu.']);
      const noSlots = () => !usableIdx(view.last && hasMenu(view.last) ? view.last : S.menuId).length;
      const chips = lvls.map(([id, label, hint]) => h('button', { class: 'look-chip' + (id === curLevel ? ' on' : ''), type: 'button', role: 'radio', 'aria-checked': id === curLevel ? 'true' : 'false',
        tabindex: id === curLevel || (curLevel === 'preset' && id === 'global') ? '0' : '-1', title: id === 'slot' && noSlots() && curLevel !== 'slot' ? 'The menu has no slot to pick yet.' : hint, dataset: { level: id, fk: 'look:level/' + id },
        'aria-disabled': id === 'slot' && noSlots() && curLevel !== 'slot' ? 'true' : null,
        onclick: () => { if (id === 'slot' && noSlots() && curLevel !== 'slot') return; if (id !== curLevel || curLevel === 'preset') goLevel(id); } }, label));
      const group = h('div', { class: 'look-chips', role: 'radiogroup', 'aria-label': 'Where the look applies' }, ...chips);
      group.addEventListener('keydown', e => {
        const at = chips.indexOf(document.activeElement);
        if (at < 0 || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) return;
        e.preventDefault();
        const to = e.key === 'Home' ? 0 : e.key === 'End' ? chips.length - 1 : (at + (e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? chips.length - 1 : 1)) % chips.length;
        chips[to].click(); const again = $('[data-level="' + lvls[to][0] + '"]', root); if (again) again.focus();
      });
      levelBar.append(group);
      if (level0 === 'menu') {
        const ms = h('select', { class: 'inp sel look-menusel', 'aria-label': 'Menu the look applies to', dataset: { fk: 'look:level-menu' }, onchange: () => { view.last = ms.value; view.target = { level: 'menu', menu: ms.value }; R.look(); } },
          ...Object.entries(S.cfg.menus).map(([id, m]) => h('option', { value: id, selected: id === target0.menu }, (m && m.title) || id)));
        levelBar.append(ms);
      }
      if (sl0 !== null) {
        const si = slotInfo(target0);
        const ss = h('select', { class: 'inp sel look-slotsel', 'aria-label': 'Slot the look applies to', dataset: { fk: 'look:level-slot' }, onchange: () => goSlot(target0.menu, +ss.value) },
          ...si.idxs.map((ix, n) => h('option', { value: ix, selected: ix === target0.slot }, 'Slot ' + (n + 1) + ': ' + itemLabel(menuOf(target0.menu).items[ix]))));
        const own = Z.ownCount(S.cfg, target0, lookCtx());
        const rs = h('button', { class: 'btn small', type: 'button', disabled: own === 0, dataset: { fk: 'look:slot-reset' }, title: own ? 'Remove the style of this slot' : 'This slot has no style of its own',
          onclick: () => { const n = Z.clearAll(S.cfg, target(), lookCtx()); tidyRing(); commit(); undoToast('Cleared the style of ' + itemLabel(menuOf(target0.menu).items[target0.slot]) + (n ? '' : '.')); R.look(); } }, icon('undo', 12), 'Reset slot');
        levelBar.append(ss, rs);
      }
      if (level0 === 'preset') {
        levelBar.append(h('span', { class: 'look-chip on look-presetchip', title: 'The look being edited' }, icon('look', 12), 'Look: ' + lookName(target0.name)));
      }
    }
    const levelNote = level0 === 'preset' ? 'You are editing a look. Menus that use it follow your changes.'
      : sl0 !== null ? "Only this slot. What you leave alone follows the menu's look."
      : level0 === 'menu' ? 'Only this menu. What you leave alone follows the look for all menus.' : full ? 'The look every menu starts from.' : 'The look for every menu.';
    levelBar.append(h('span', { class: 'look-levelnote' }, levelNote));

    /* ---- the pieces every control row is made from */
    const groupOfKey = k => Z.groupOf(lookCtx(), k);
    /* The source badge: where the value comes from. A button: on the level's own values it moves to the control, on inherited ones it goes to the level that owns them. */
    const addBadge = (slabel, keys) => {
      const name = slabel.firstElementChild;
      const accs = keys.map(k => lookAccess(k));
      const top = () => accs.map(a => ({ o: a.origin(), n: a.name() })).sort((x, y) => RANK[y.o] - RANK[x.o])[0];
      const b = h('button', { class: 'lk-badge', type: 'button', onclick: () => {
        const { o, n } = top();
        if (o === 'menu' && slotT()) jump({ level: 'menu', menu: target().menu }, keys[0]);
        else if (o === 'global' && ownOrigin() !== 'global') jump({ level: 'global' }, keys[0]);
        else if ((o === 'global-preset' || o === 'menu-preset') && n) jump({ level: 'preset', name: n }, keys[0]);
        else { const c = slabel.closest('.srow, .crow, .tg-head, .lk-stack'); const f = c && $('input:not([disabled]), button.choice.on, button.choice:not([disabled]), button.rc-chip[aria-checked="true"]', c); if (f) f.focus(); }
      } });
      const paint = () => {
        const { o, n } = top();
        b.textContent = badgeText(o, n);
        b.className = 'lk-badge ' + o + (o !== ownOrigin() && o !== 'default' && o !== 'theme' ? ' inh' : '');
        b.title = badgeTitle(o, n);
        b.setAttribute('aria-label', 'Source: ' + badgeText(o, n) + '. ' + badgeTitle(o, n));
      };
      slabel.prepend(h('div', { class: 'lk-line' }, name, b));
      badges.push(paint); paint();
      return b;
    };
    /* Goes to another level to the control of key; Done in the banner comes back. */
    const jump = (t, key) => {
      view.back = view.target.level === 'preset' ? view.back : view.target;
      view.target = t;
      const gid = groupOfKey(String(key).split('.')[0]);
      view.fold[gid] = true;                                    // the group is built open, so the control can take the focus
      R.look();
      if (R.lookGoto) R.lookGoto(key, gid);
    };
    /* A row from sliderRow: the badge, the focus keys and the reset wording. */
    const lookRow = (row, keys) => {
      addBadge($('.slabel', row), keys);
      const base = 'look:' + keys[0];
      for (const el of $$('[data-fk]', row)) {
        const m = /\/(range|num|reset)$/.exec(el.dataset.fk);
        el.dataset.fk = m && m[1] === 'range' ? base : base + '/' + (m ? m[1] : 'x');
      }
      for (const r of $$('.reset', row)) { r.title = S.defaults[keys[0]] === undefined ? resetWord() : r.title.replace(/^Reset to default/, resetWord()); r.setAttribute('aria-label', r.title); }
      return row;
    };
    const limitsOf = key => { const s = schemaOf()[key]; return s && s.min !== undefined ? [s.min, s.max] : null; };
    const slider = (key, o) => lookRow(sliderRow(Object.assign({ key, onLive: live, limits: limitsOf(key) }, o, lookAccess(key).slider)), [key]);

    /* Simple mode's one size slider: it moves radius, slot and dead zone together, keeping the proportions the ring had when the gesture began. */
    const sizeRowFor = () => {
      const KEYS = ['radius', 'slot', 'dead_zone'], A = Object.fromEntries(KEYS.map(k => [k, lookAccess(k)]));
      let base = null, last = null;
      const row = sliderRow({ label: 'Ring size', hint: 'How big the ring is. Slots and the dead zone (the dashed circle) scale with it.', key: 'radius', unit: 'px', onLive: live, limits: limitsOf('radius'),
        get: () => A.radius.get(),
        put: v => {
          if (!base || A.radius.get() !== last) base = { radius: A.radius.get(), slot: A.slot.get(), dead_zone: A.dead_zone.get() };
          const f = base.radius ? v / base.radius : 1, c = lookCtx();
          Z.set(S.cfg, target(), 'radius', v, c);
          for (const k of ['slot', 'dead_zone']) { const [lo, hi] = limitsOf(k) || [0, 1000]; Z.set(S.cfg, target(), k, clamp(Math.round(base[k] * f), lo, hi), c); }
          tidyRing(); commit();
          last = A.radius.get();
        },
        clear: () => { for (const k of KEYS) Z.clear(S.cfg, target(), k, lookCtx()); tidyRing(); commit(); base = null; },
        isSet: () => KEYS.some(k => A[k].isSet()) });
      for (const ev of ['pointerdown', 'focusin']) row.addEventListener(ev, () => { base = null; }, true);
      return lookRow(row, KEYS);
    };

    /* A row of choice cards with the label above: Slot shape, Hub style, Labels, When full. */
    const choiceRow = ({ label, hint, key, items, cls, dim }) => {
      const A = lookAccess(key);
      const wrapC = choiceCards(items, A.get(), v => { A.put(v); }, cls, label);
      for (const b of $$('.choice', wrapC)) b.dataset.fk = 'look:' + key + '/' + b.dataset.v;
      const reset = iconBtn('undo', resetWord(), () => { A.clear(); }, 'reset');
      reset.dataset.fk = 'look:' + key + '/reset';
      const slabel = h('div', { class: 'slabel' }, h('span', null, label), hint ? h('small', null, hint) : null);
      addBadge(slabel, [key]);
      const row = h('div', { class: 'srow lk-stack' }, h('div', { class: 'lk-head' }, slabel, reset), wrapC);
      const paint = () => {
        reset.style.visibility = A.isSet() ? 'visible' : 'hidden';
        const v = A.get(), btns = $$('.choice', wrapC);
        btns.forEach(b => { const on = b.dataset.v === String(v); b.classList.toggle('on', on); b.setAttribute('aria-checked', on ? 'true' : 'false'); b.tabIndex = on ? 0 : -1; });
        if (dim) { const off = dim(); row.classList.toggle('off', off); btns.forEach(b => { b.disabled = off; }); reset.disabled = off; }
      };
      paint(); repaints.push(paint);
      return row;
    };
    const itemsOf = (keyChoices, table, fallbackText) => keyChoices.map(v => { const t = table[v] || [v, fallbackText || '', '']; return [v, t[0], t[1], t[2] ? glyph(t[2]) : null]; });
    const choicesOf = key => { const s = schemaOf()[key]; return (s && s.choices) || []; };

    /* A colour that is a theme role or a fixed colour: chips Automatic (when the key allows none), the five roles filled with their colour here, and Custom. */
    const roleColorRow = ({ key, label, hint, dim }) => {
      const A = lookAccess(key), allowEmpty = !!(schemaOf()[key] || {}).allow_empty;
      const pal = () => (slotT() ? ambient().colors : resolved().colors.value);
      const isRole = v => Z.ROLES.includes(v);
      const kindOfValue = v => (v === '' ? '' : isRole(v) ? v : '#');
      const hexInp = h('input', { class: 'inp mono hex', type: 'text', maxlength: '7', spellcheck: 'false', 'aria-label': label + ' hex value', dataset: { fk: 'look:' + key + '/hex' } });
      const sw = h('input', { type: 'color', class: 'swatch', 'aria-label': label + ' colour', dataset: { fk: 'look:' + key + '/swatch' } });
      const hmsg = h('span', { class: 'hex-msg', role: 'status' });
      const custom = h('div', { class: 'rc-custom' }, sw, h('div', { class: 'hexwrap' }, hexInp, hmsg));
      const options = (allowEmpty ? [['', 'Automatic']] : []).concat(Z.ROLES.map(r => [r, COLOR_INFO[r][0]]), [['#', 'Custom']]);
      let lastCustom = null;
      const chips = options.map(([v, text]) => h('button', { class: 'rc-chip' + (v === '#' ? ' custom' : v === '' ? ' auto' : ''), type: 'button', role: 'radio', 'aria-checked': 'false', tabindex: '-1',
        dataset: { v, fk: 'look:' + key + '/' + (v === '' ? 'auto' : v === '#' ? 'custom' : v) }, onclick: () => pick(v) }, text));
      const group = h('div', { class: 'rc-chips', role: 'radiogroup', 'aria-label': label }, ...chips);
      group.addEventListener('keydown', e => {
        const at = chips.indexOf(document.activeElement);
        if (at < 0 || e.ctrlKey || e.altKey || e.metaKey || e.shiftKey) return;
        const n = chips.length, to = { ArrowRight: (at + 1) % n, ArrowDown: (at + 1) % n, ArrowLeft: (at + n - 1) % n, ArrowUp: (at + n - 1) % n, Home: 0, End: n - 1 }[e.key];
        if (to === undefined) return;
        e.preventDefault(); chips[to].click(); chips[to].focus();
      });
      const reset = iconBtn('undo', resetWord(), () => { A.clear(); }, 'reset');
      reset.dataset.fk = 'look:' + key + '/reset';
      function pick(v) {
        if (v === '#') { const cur = A.get(); A.put(lastCustom || (typeof cur === 'string' && cur.startsWith('#') ? cur : A.eff() || '#ffffff')); }
        else A.put(v);
      }
      const hexOk = s => /^#[0-9a-f]{6}$/i.test(s);
      sw.addEventListener('input', () => A.put(sw.value));
      hexInp.addEventListener('input', () => {
        const n = normHex(hexInp.value), bad = !n;
        hexInp.classList.toggle('bad', bad); hmsg.textContent = bad ? 'Use #rrggbb' : '';
        if (n && hexInp.value.trim().replace('#', '').length === 6) { A.put(n); sw.value = n; }
      });
      const applyHex = () => { const n = normHex(hexInp.value); if (n && n !== String(A.get()).toLowerCase()) A.put(n); paint(); };
      hexInp.addEventListener('blur', applyHex);
      hexInp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); applyHex(); } });
      const lum = c => { const n = parseInt(c.slice(1), 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255; return (0.299 * r + 0.587 * g + 0.114 * b) / 255; };
      const slabel = h('div', { class: 'slabel' }, h('span', null, label), hint ? h('small', null, hint) : null);
      addBadge(slabel, [key]);
      const row = h('div', { class: 'srow lk-stack lk-roles' }, h('div', { class: 'lk-head' }, slabel, reset), group, custom);
      function paint() {
        const v = A.get(), k = kindOfValue(v), colours = pal();
        chips.forEach(c => {
          const cv = c.dataset.v, on = cv === k;
          c.classList.toggle('on', on); c.setAttribute('aria-checked', on ? 'true' : 'false'); c.tabIndex = on ? 0 : -1;
          if (isRole(cv) && colours[cv]) { c.style.background = colours[cv]; c.style.color = lum(colours[cv]) > 0.55 ? '#111' : '#fff'; c.style.borderColor = ''; }
        });
        custom.hidden = k !== '#';
        if (k === '#' && hexOk(v)) { lastCustom = v; sw.value = v; if (document.activeElement !== hexInp) { hexInp.value = v; hexInp.classList.remove('bad'); hmsg.textContent = ''; } }
        reset.style.visibility = A.isSet() ? 'visible' : 'hidden';
        if (dim) { const off = dim(); row.classList.toggle('off', off); $$('button, input', row).forEach(c => { c.disabled = off; }); }
      }
      paint(); repaints.push(paint);
      return row;
    };

    /* ---- the groups */
    const groupSlots = () => {
      const rows = [];
      if (hasKey('radius')) rows.push(...(full ? [
        slider('radius', { label: 'Ring radius', hint: 'Distance from the centre to the slots', unit: 'px' }),
        slider('slot', { label: 'Slot size', hint: 'Diameter of each icon disc', unit: 'px' }),
        slider('dead_zone', { label: 'Dead zone', hint: 'No slot is picked this close to the centre (dashed circle)', unit: 'px' })] : [sizeRowFor()]));
      const shapes = choicesOf('slot_shape');
      const many = shapes.length > 2;
      const each = slotT() ? 'this slot' : 'each slot';
      rows.push(choiceRow({ label: 'Slot shape', key: 'slot_shape', cls: many ? 'lk-shapes' : 'two', items: itemsOf(shapes, full ? SHAPE : { ...SHAPE, rounded: [SHAPE.rounded[0], 'Square with rounded corners.', SHAPE.rounded[2]] }) }));
      if (full && hasKey('slot_corner')) {
        const off = () => valueNow('slot_shape') !== 'rounded';
        const r1 = slider('slot_corner', { label: 'Corner roundness', hint: 'How round the corners of a Rounded square are', unit: '%', scale: 100, step: 1 });
        repaints.push(() => { r1.classList.toggle('off', off()); $$('input, button', r1).forEach(c => { c.disabled = off(); }); }); repaints[repaints.length - 1]();
        rows.push(r1,
          slider('border_width', { label: 'Rim width', hint: 'The outline of ' + each + '. A tag-tinted rim is one pixel wider', unit: 'px' }),
          slider('icon_scale', { label: 'Icon size', hint: 'How much of the slot the icon fills', unit: '%', scale: 100, step: 1 }));
      }
      if (full && hasKey('size')) rows.push(
        slider('size', { label: 'Size of this slot', hint: 'Bigger or smaller than the ring\'s slot size. 100% is the same', unit: '%', scale: 100, step: 1 }),
        roleColorRow({ key: 'fill_color', label: 'Fill colour', hint: 'The inside of the slot. Automatic uses the theme\'s background' }),
        roleColorRow({ key: 'border_color', label: 'Rim colour', hint: 'The outline of the slot. Automatic uses the tag colour, else the accent' }));
      return card('Slots', slotT() ? 'The shape and size of this slot' : full ? 'Size, spacing and shape' : 'How big the ring is, and its shape', ...rows);
    };
    const groupHub = () => {
      const off = () => !(Number(valueNow('hub')) > 0);
      const rows = [slider('hub', { label: 'Hub size', hint: 'The marker in the centre. 0 for none', unit: 'px' })];
      if (hasKey('hub_style')) {
        const styles = choicesOf('hub_style');
        const r1 = choiceRow({ label: 'Hub style', key: 'hub_style', cls: 'four', items: itemsOf(styles, HUB), dim: off });
        rows.push(r1, roleColorRow({ key: 'hub_color', label: 'Hub colour', hint: 'A theme colour follows the theme, and any colours you set', dim: off }),
          (() => { const r2 = slider('hub_glow', { label: 'Hub glow', hint: 'The halo around the hub. 0 for none', unit: '%', scale: 100, step: 5 });
            repaints.push(() => { r2.classList.toggle('off', off()); $$('input, button', r2).forEach(c => { c.disabled = off(); }); }); repaints[repaints.length - 1](); return r2; })());
      }
      return card('Hub', 'The centre of the ring', ...rows);
    };
    const groupGlow = () => card('Glow', 'The halo around a slot',
      roleColorRow({ key: 'glow_color', label: 'Glow colour', hint: 'Automatic uses a tag\'s colour when the slot has one, else the accent or highlight' }),
      ...(hasKey('glow_opacity') ? [slider('glow_opacity', { label: 'Glow strength', hint: 'How strong the halo is', unit: '%', scale: 100, step: 5 })] : []));
    const groupLabels = () => {
      const labelOpts = choicesOf('labels');
      const rows = hasKey('labels') ? [choiceRow({ label: 'Labels', key: 'labels', cls: 'two', items: itemsOf(labelOpts, LABELS) })] : [];
      if (full && hasKey('label_color')) rows.push(roleColorRow({ key: 'label_color', label: 'Label colour', hint: slotT() ? 'The text under this slot' : 'The text under each slot', dim: () => (slotT() ? ambient().labels : valueNow('labels')) === 'none' }));
      return card('Labels', null, ...rows);
    };
    const colourRow = name => {
      const A = lookAccess('colors.' + name), info = COLOR_INFO[name];
      const sw = h('input', { type: 'color', class: 'swatch', value: A.get(), 'aria-label': info[0] + ' colour', dataset: { fk: 'look:colors/' + name } });
      const hex = h('input', { class: 'inp mono hex', type: 'text', value: A.get(), maxlength: '7', spellcheck: 'false', 'aria-label': info[0] + ' hex value', dataset: { fk: 'look:colors/' + name + '/hex' } });
      const hmsg = h('span', { class: 'hex-msg', role: 'status' });
      const rs = iconBtn('undo', resetWord(), () => { A.clear(); }, 'reset');
      rs.dataset.fk = 'look:colors/' + name + '/reset';
      const paint = () => {
        const v = A.get();
        sw.value = v;
        if (document.activeElement !== hex) { hex.value = v; hex.classList.remove('bad'); hmsg.textContent = ''; }
        rs.title = resetWord() + ' (' + (S.defaults.colors || {})[name] + ')'; rs.setAttribute('aria-label', rs.title); rs.style.visibility = A.isSet() ? 'visible' : 'hidden';
      };
      sw.addEventListener('input', () => { A.put(sw.value); });
      hex.addEventListener('input', () => {
        const n = normHex(hex.value), bad = !n;
        hex.classList.toggle('bad', bad); hmsg.textContent = bad ? 'Use #rrggbb' : '';
        if (n && hex.value.trim().replace('#', '').length === 6) { A.put(n); sw.value = n; }     // short forms wait for Enter or blur
      });
      const apply = () => { const n = normHex(hex.value); if (n && n !== A.get().toLowerCase()) A.put(n); paint(); };
      hex.addEventListener('blur', apply);
      hex.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); apply(); } });
      repaints.push(paint);
      const slabel = h('div', { class: 'slabel' }, h('span', null, info[0]), h('small', null, info[1]));
      addBadge(slabel, ['colors.' + name]);
      paint();
      return h('div', { class: 'crow lk-crow' }, sw, slabel, h('div', { class: 'hexwrap' }, hex, hmsg), rs);
    };
    const groupColours = () => card('Colours', 'Applied to the ring in the app',
      h('div', { class: 'colors' }, Z.ROLES.map(colourRow)),
      h('div', { class: 'btn-row' }, h('button', { class: 'btn small', type: 'button', onclick: () => {
        for (const n of Z.ROLES) Z.clear(S.cfg, target(), 'colors.' + n, lookCtx());
        tidyRing(); commit(); view.touch();
      } }, icon('undo', 12), 'Reset all colours')));

    /* Tag colours: how a brush's first tag shows on its slot (tag slots always show their tag's colour). Three effects, each a switch
       with its own controls; tint and glow together are the stored tag_colors. */
    const tagNote = h('div', { class: 'fhint' });
    const hasTagged = m => !!m && (m.items || []).some(it => { const ik = kindOf(it); return isLib(ik) && firstTag(ik, it[ik]); });
    function paintTagNote() {
      const id = previewId(), m = id === SAMPLE_MENU ? null : menuOf(id);
      tagNote.replaceChildren();
      if (id === SAMPLE_MENU || hasTagged(m)) return;
      tagNote.append('This menu has no tagged brushes, so these effects do not show on it. ');
      if (target().level !== 'menu') tagNote.append(linkBtn('Preview the sample ring', () => { view.menuId = SAMPLE_MENU; picker.value = SAMPLE_MENU; R.preview(); paintTagNote(); }), '.');
    }
    const groupTags = () => {
      const A = k => lookAccess(k);
      const tc = () => A('tag_colors').get() || 'tint';
      const tintOn = () => tc() === 'tint' || tc() === 'both', glowOn = () => tc() === 'glow' || tc() === 'both';
      const setTc = (tint, glow) => { A('tag_colors').put(tint && glow ? 'both' : tint ? 'tint' : glow ? 'glow' : 'none'); };
      const bandDef = S.defaults.tag_band && S.defaults.tag_band !== 'none' ? S.defaults.tag_band : 'medium';
      let bandWas = A('tag_band').get() && A('tag_band').get() !== 'none' ? A('tag_band').get() : bandDef;     // the thickness to come back to
      const bandOn = () => A('tag_band').get() !== 'none';
      const cap = t => t[0].toUpperCase() + t.slice(1);
      const tcRows = [];                                    // [row, is its effect on]: rows of a switched-off effect are dimmed and disabled
      const paintTc = () => {
        for (const [row, on] of tcRows) {
          const lv = on();
          row.classList.toggle('off', !lv);
          $$('input, button', row).forEach(c => { c.disabled = !lv; });
        }
      };
      repaints.push(paintTc);
      const segRow = ({ label, hint, key, opts, on, onPick }) => {
        const row = h('div', { class: 'srow' }, h('div', { class: 'slabel' }, h('span', null, label), hint ? h('small', null, hint) : null),
          choiceCards(opts, onPick ? bandWas : A(key).get(), onPick || (v => { A(key).put(v); }), 'seg', label));
        addBadge($('.slabel', row), [key]);
        for (const b of $$('.choice', row)) b.dataset.fk = 'look:' + key + '/' + b.dataset.v;
        tcRows.push([row, on]); return row;
      };
      const opacity = (key, on) => { const row = slider(key, { label: 'Opacity', step: 5, scale: 100, unit: '%' }); tcRows.push([row, on]); return row; };
      const group = ({ label, hint, key, tag, on, set, rows }) => {
        const sw = toggleSwitch(on(), v => { set(v); paintTc(); }, label);
        sw.querySelector('input').dataset.fk = 'look:' + key + '/' + tag;
        const slabel = h('div', { class: 'slabel' }, h('span', null, label), h('small', null, hint));
        addBadge(slabel, [key]);
        return h('div', { class: 'tgroup' }, h('div', { class: 'tg-head' }, slabel, sw), h('div', { class: 'tg-body' }, ...rows));
      };
      const bandOpts = ((K.S.opts && K.S.opts.tag_bands) || ['none', 'hairline', 'narrow', 'medium', 'wide']).filter(v => v !== 'none').map(v => [v, cap(v), '']);
      const BLEND = { multiply: 'Darken', overlay: 'Keep highlights' };
      const c = card('Tag colours', "How a brush's tags show on its slots", tagNote,
        group({ label: 'Icon tint', hint: 'A coloured rim, and the tag colour laid over the icon', key: 'tag_colors', tag: 'tint', on: tintOn, set: v => setTc(v, glowOn()), rows: [
          opacity('tag_tint_opacity', tintOn),
          segRow({ label: 'Style', hint: 'Gradient is stronger towards the rim', key: 'tag_tint_style', on: tintOn, opts: ((S.opts && S.opts.tint_styles) || ['flat', 'gradient']).map(v => [v, cap(v), '']) }),
          segRow({ label: 'Blend', key: 'tag_tint_blend', on: tintOn, opts: ((S.opts && S.opts.tint_blends) || ['multiply', 'overlay']).map(v => [v, BLEND[v] || cap(v), '']) })] }),
        group({ label: 'Glow', hint: 'A soft halo in the tag colour around the slot', key: 'tag_colors', tag: 'glow', on: glowOn, set: v => setTc(tintOn(), v), rows: [
          opacity('tag_glow_opacity', glowOn)] }),
        group({ label: 'Band', hint: 'A coloured strip through the slots, one stretch per slot', key: 'tag_band', tag: 'band', on: bandOn,
          set: v => { A('tag_band').put(v ? bandWas : 'none'); }, rows: [
            segRow({ label: 'Thickness', key: 'tag_band', on: bandOn, opts: bandOpts, onPick: v => { bandWas = v; A('tag_band').put(v); } }),
            opacity('tag_band_opacity', bandOn)] }));
      paintTc();
      return c;
    };
    let paintFit = null;
    const groupWhenFull = () => {
      const fit = h('div', { class: 'fhint lk-fit', role: 'status' });
      paintFit = () => {
        const f = lastFit;
        fit.textContent = !f ? '' : f.full ? 'The menu in the preview has ' + f.items + ' items and this ring holds ' + f.capacity + ' at its radius, so the choice applies to it.'
          : 'The menu in the preview has ' + f.items + ' items and this ring holds ' + f.capacity + ' at its radius, so none of this applies to it yet.';
      };
      paintFit();
      return card('When full', 'What a crowded ring does',
        choiceRow({ label: 'When there are more items than fit', key: 'when_full', cls: 'three', items: choicesOf('when_full').map(v => [v, (FULL_WHEN[v] || [v, ''])[0], (FULL_WHEN[v] || [v, ''])[1]]) }), fit);
    };
    /* Opening: ring.animation at the global level, menu.animation (or none, to follow the ring) at the menu level. Not a look key, so Z.resolve
       never sees it and the origin is worked out here. */
    const groupOpening = () => {
      const atMenu = level0 === 'menu', m = atMenu ? menuOf(target0.menu) : null;
      const allA = K.ring().animation || S.defaults.animation;
      const items = ((S.opts && S.opts.animations) || Object.keys(K.ANIM_INFO)).map(a => [a, animTitle(a), K.ANIM_INFO[a] || '']);
      if (atMenu) items.unshift(['', 'Same as all menus (' + animTitle(allA) + ')', 'Follows the animation set for all menus.']);
      const tiles = choiceCards(items, atMenu ? ((m && m.animation) || '') : allA, v => {
        if (atMenu) { if (!m) return; if (v) m.animation = v; else delete m.animation; } else K.ensureRing().animation = v;
        commit(); R.look();
        if (R.lookPlay) R.lookPlay();
      }, 'anim-cards', 'Open animation');
      for (const b of $$('.choice', tiles)) b.dataset.fk = 'look:animation/' + (b.dataset.v || 'inherit');
      playBtn = h('button', { class: 'btn small', type: 'button', dataset: { fk: 'look:opening-play' }, onclick: playNow }, icon('play', 12), 'Play');
      const row = [playBtn];
      const ringSet = K.ring().animation !== undefined && K.ring().animation !== S.defaults.animation;       // the starter file holds the default; that is not a choice
      if (!atMenu && ringSet) row.push(h('button', { class: 'btn small', type: 'button', dataset: { fk: 'look:animation/reset' }, title: 'Go back to the default (' + animTitle(S.defaults.animation) + ')',
        onclick: () => {
          delete K.ensureRing().animation; tidyRing(); commit(); R.look();
          const on = $('#look-g-opening .choice.on'); if (on) on.focus({ preventScroll: true });
          if (R.lookPlay) R.lookPlay();
        } }, icon('undo', 12), 'Reset to default'));
      const origin = atMenu ? (m && m.animation ? 'Set for this menu only.' : 'This menu follows the animation for all menus.')
        : ringSet ? 'Set for all menus.' : 'The default. Every menu uses it unless it has its own.';
      const own = atMenu ? [] : Object.entries(S.cfg.menus).filter(([, mm]) => mm && mm.animation);
      const goOwn = id => { view.last = id; view.target = { level: 'menu', menu: id }; view.back = null; view.fold.opening = true; R.look(); if (R.lookGoto) R.lookGoto('animation', 'opening'); };
      return card('Opening', 'How the ring appears', h('div', { class: 'btn-row', style: { marginBottom: '10px' } }, ...row), tiles, h('div', { class: 'fhint', style: { marginTop: '8px' } }, origin),
        own.length ? h('div', { class: 'fhint', style: { marginTop: '4px' } }, 'With an animation of their own: ', ...own.flatMap(([id, mm], i) => [i ? ', ' : '', linkBtn(menuTitle(id), () => goOwn(id)), ' (' + animTitle(mm.animation) + ')']), '.') : null);
    };
    const GROUP_BUILD = { slots: groupSlots, hub: groupHub, glow: groupGlow, labels: groupLabels, colours: groupColours, tags: groupTags, when_full: groupWhenFull, opening: groupOpening };

    /* ---- the gallery */
    const menuTitle = id => { const m = menuOf(id); return (m && m.title) || id; };
    const whereText = t => (t.level === 'menu' ? menuTitle(t.menu) : 'all menus');
    function applyTarget() { return level0 === 'preset' ? { level: 'global' } : target(); }
    view.gallery = null;
    const gallery = presetsOn() && sl0 === null ? buildGallery() : null;
    if (gallery) pickLabel.after(gallery.el);                     // under the picture and its preview menu, above the dead-zone hint, so it is on screen when Look opens

    function applyLook(id, keep) {
      const t = applyTarget(), c = lookCtx();
      const n = Z.usePreset(S.cfg, t, id, { keep }, c);
      tidyRing(); commit();
      undoToast(lookName(id) + ' is now the look for ' + whereText(t) + (n ? '. ' + clearedText(n) + '.' : '.'));
      R.look();
    }

    function buildGallery() {
      const c = lookCtx(), p = Z.prep(c);
      const el = h('section', { class: 'lk-gallery', 'aria-label': 'Looks' });
      const list = h('div', { class: 'lk-cards', role: 'listbox', 'aria-label': 'Looks', 'aria-orientation': 'horizontal' });
      const newBtn = h('button', { class: 'btn small', type: 'button', dataset: { fk: 'look:new' }, title: 'Save what the ring looks like now as a look of your own', onclick: () => newFromCurrent() }, icon('plus', 12), 'New from current');
      el.append(h('div', { class: 'lk-ghead' }, h('span', { class: 'micro' }, 'Looks'), newBtn), list);
      const cardsNow = () => {
        const base = baseSig();
        const out = p.builtinList.map(b => ({ id: b.id, label: b.label, blurb: b.blurb, builtin: true, sig: base + '|b:' + b.id }));
        for (const n of userNames()) out.push({ id: n, label: n, blurb: 'Your own look.', builtin: false, sig: base + '|u:' + n + JSON.stringify(S.cfg.looks[n]) });
        return out;
      };
      const imgs = new Map();
      let cards = [];
      const stateOf = id => {
        const g = Z.presetOf(S.cfg, { level: 'global' }), users = Z.usersOf(S.cfg, id);
        const chips = [];
        if (level0 === 'preset' && target0.name === id) chips.push(['Editing', 'edit']);
        if ((g || 'classic') === id) chips.push(['Global', 'glob']);
        if (level0 === 'menu' && Z.presetOf(S.cfg, target()) === id) chips.push(['This menu', 'menu']);
        const others = users.menus.filter(m => !(level0 === 'menu' && m === target0.menu));
        if (others.length) chips.push([plural(others.length, 'menu'), 'used']);
        const current = level0 === 'preset' ? target0.name === id : level0 === 'menu' ? Z.presetOf(S.cfg, target()) === id : (g || 'classic') === id;
        return { chips, current };
      };
      const verbFor = () => (level0 === 'menu' ? 'Use for ' + menuTitle(target0.menu) : 'Use for all menus');
      const move = (opts, from, to) => { const t = opts[clamp(to, 0, opts.length - 1)]; if (t) { opts.forEach(o => { o.tabIndex = o === t ? 0 : -1; }); t.focus(); } };
      function build() {
        cards = cardsNow();
        list.replaceChildren();
        const opts = [];
        for (const cd of cards) {
          const st = stateOf(cd.id), pic = h('img', { class: 'lk-pic', alt: '', draggable: false });
          imgs.set(cd.id, pic);
          const opt = h('div', { class: 'lk-opt', role: 'option', 'aria-selected': st.current ? 'true' : 'false', tabindex: '-1', dataset: { id: cd.id, fk: 'look:card/' + cd.id },
            'aria-label': cd.label + (cd.builtin ? ', built-in' : '') + (st.chips.length ? ', ' + st.chips.map(x => x[0]).join(', ') : '') + '. ' + cd.blurb,
            onkeydown: e => {
              const at = opts.indexOf(opt);
              if (e.key === 'Enter' && !e.ctrlKey && !e.altKey) { e.preventDefault(); applyLook(cd.id, false); }
              else if (e.key === ' ' ) { e.preventDefault(); }
              else if (e.key === 'ArrowRight' || e.key === 'ArrowLeft' || e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Home' || e.key === 'End') {
                e.preventDefault();
                const per = Math.max(1, getComputedStyle(list).gridTemplateColumns.split(' ').filter(Boolean).length), to = e.key === 'Home' ? 0 : e.key === 'End' ? opts.length - 1 : e.key === 'ArrowRight' ? at + 1 : e.key === 'ArrowLeft' ? at - 1 : e.key === 'ArrowDown' ? at + per : at - per;
                move(opts, at, to);
              }
            },
            ondblclick: () => applyLook(cd.id, false), onclick: () => { opts.forEach(o => { o.tabIndex = o === opt ? 0 : -1; }); opt.focus(); } },
          h('div', { class: 'lk-thumb' }, pic),
          h('div', { class: 'lk-name' }, h('b', null, cd.label), cd.builtin ? h('span', { class: 'tag lk-tag' }, 'Built-in') : null),
          h('div', { class: 'lk-blurb' }, cd.blurb),
          st.chips.length ? h('div', { class: 'lk-chipline' }, st.chips.map(([t, cls]) => h('span', { class: 'lk-mark ' + cls }, t))) : null);
          opts.push(opt);
          const foot = h('div', { class: 'lk-foot' }, h('button', { class: 'btn small' + (st.current ? '' : ' primary'), type: 'button', dataset: { fk: 'look:card/' + cd.id + '/use' }, onclick: () => applyLook(cd.id, false) }, verbFor()));
          if (full) foot.append(h('button', { class: 'ibtn lk-more', type: 'button', title: 'More for ' + cd.label, 'aria-label': 'More for ' + cd.label, 'aria-haspopup': 'menu', dataset: { fk: 'look:card/' + cd.id + '/more' },
            onclick: e => cardMenu(e.currentTarget, cd) }, icon('chevD', 14)));
          list.append(h('div', { class: 'lk-card' + (st.current ? ' cur' : ''), role: 'none' }, opt, foot));
        }
        const cur = opts.find(o => o.getAttribute('aria-selected') === 'true') || opts[0];
        if (cur) cur.tabIndex = 0;
        paintThumbs();
      }
      function paintThumbs() {
        for (const cd of cards) {
          const pic = imgs.get(cd.id);
          if (!pic) continue;
          const src = Thumbs.cache.get(cd.sig) || Thumbs.shown.get(cd.id);
          if (src && pic.getAttribute('src') !== src) pic.src = src;
          pic.classList.toggle('stale', !Thumbs.cache.has(cd.sig));
        }
        if (cards.some(cd => !Thumbs.cache.has(cd.sig))) wantThumbs();
      }
      /* After an edit: the marks may have changed (a used look, the current one). Pictures follow the new base. */
      let sigNow = '';
      function refresh() {
        const sig = JSON.stringify([userNames(), Z.presetOf(S.cfg, { level: 'global' }), level0 === 'menu' ? Z.presetOf(S.cfg, target()) : '', Object.keys(S.cfg.menus).map(id => Z.presetOf(S.cfg, { level: 'menu', menu: id }))]);
        if (sig !== sigNow) { sigNow = sig; const act = document.activeElement, key = act && list.contains(act) ? lookFk(act) : null; build(); const again = key && $$('[data-fk]', list).find(x => x.dataset.fk === key); if (again) again.focus({ preventScroll: true }); return; }
        cards = cardsNow(); paintThumbs();
      }
      sigNow = JSON.stringify([userNames(), Z.presetOf(S.cfg, { level: 'global' }), level0 === 'menu' ? Z.presetOf(S.cfg, target()) : '', Object.keys(S.cfg.menus).map(id => Z.presetOf(S.cfg, { level: 'menu', menu: id }))]);
      build();
      view.gallery = { cards: () => cards, paintThumbs, refresh };
      return { el, build, refresh };
    }

    /* The actions of one card in a menu. */
    function cardMenu(anchor, cd) {
      const entries = [{ icon: 'check', label: 'Use, keep my changes', hint: 'Does not remove the settings you made for ' + whereText(applyTarget()), fn: () => applyLook(cd.id, true) }, { sep: true }];
      entries.push({ icon: 'edit', label: cd.builtin ? 'View' : 'Edit', hint: cd.builtin ? 'Built-in looks cannot be changed' : 'Change this look. Menus that use it follow', fn: () => editLook(cd.id) });
      entries.push({ icon: 'copy', label: 'Duplicate', hint: cd.builtin ? 'Make a copy of your own to change' : null, fn: () => duplicateLook(cd.id) });
      if (!cd.builtin) entries.push({ icon: 'edit', label: 'Rename...', fn: () => renameLook(cd.id) }, { sep: true }, { icon: 'trash', label: 'Delete...', fn: () => deleteLook(cd.id) });
      popover(anchor, entries);
    }

    /* New from current: a look from what the target shows now. */
    async function newFromCurrent() {
      const c = lookCtx();
      const geo = h('input', { type: 'checkbox', id: 'lk-geo' }), also = h('input', { type: 'checkbox', id: 'lk-also', checked: true });
      const t = applyTarget();
      const extra = h('div', { class: 'lk-checks' },
        h('label', { class: 'lk-check' }, geo, h('span', null, h('b', null, 'Include ring size'), h('small', null, 'Radius, slot size and dead zone. Left out, the look fits any ring size.'))),
        h('label', { class: 'lk-check' }, also, h('span', null, h('b', null, 'Also use it here'), h('small', null, 'Use the new look for ' + whereText(t) + ' and clear the settings it now holds.'))));
      const name = await promptModal({ title: 'New look from current', label: 'Name of the look', value: freeName('My look'), confirm: 'Create look', extra, submit: async n => nameError(n, null),
        hint: 'Saves the shapes, hub, glow, labels and colours you see in the preview as a look you can use on any menu.' });
      if (!name) return;
      const source = level0 === 'preset' ? { level: 'global' } : target();
      Z.newPreset(S.cfg, source, name, { geometry: geo.checked }, c);
      let n = 0;
      if (also.checked) n = Z.usePreset(S.cfg, t, name, { keep: false }, c);
      tidyRing(); commit();
      undoToast('Saved the look “' + name + '”' + (also.checked ? ' and used it for ' + whereText(t) : '') + (n ? '. ' + clearedText(n) + '.' : '.'));
      R.look();
    }
    function editLook(id) {
      view.back = level0 === 'preset' ? view.back : view.target;
      view.target = { level: 'preset', name: id };
      R.look();
    }
    function duplicateLook(id) {
      const to = freeName(id + ' copy');
      Z.duplicate(S.cfg, id, to, lookCtx());
      commit();
      undoToast('Made “' + to + '” from ' + lookName(id) + '.');
      R.look();
    }
    async function renameLook(id) {
      const name = await promptModal({ title: 'Rename look', label: 'New name', value: id, confirm: 'Rename', submit: async n => nameError(n, id) });
      if (!name || name === id) return;
      const n = Z.rename(S.cfg, id, name, lookCtx());
      if (view.target.level === 'preset' && view.target.name === id) view.target = { level: 'preset', name };
      commit();
      undoToast('Renamed to “' + name + '”' + (n ? '. ' + plural(n, 'place') + ' that used it now use the new name.' : '.'));
      R.look();
    }
    async function deleteLook(id) {
      const users = Z.usersOf(S.cfg, id);
      let how = 'drop';
      if (users.global || users.menus.length) {
        const list = [...(users.global ? ['All menus (Global)'] : []), ...users.menus.map(menuTitle)];
        how = await modal({ title: 'Delete “' + id + '”?', body: [h('p', null, 'These use it:'), h('ul', { class: 'lk-users' }, list.map(t => h('li', null, t))),
          h('p', { class: 'modal-hint' }, 'They can keep the settings of the look as their own, or go back to the look above them.')],
        actions: [{ text: 'Cancel', value: null }, { text: 'Delete, they lose it', value: 'drop', kind: 'danger-o' }, { text: 'Delete and keep their look', value: 'bake', kind: 'primary', focus: true }] });
        if (!how) return;
      }
      Z.remove(S.cfg, id, { bake: how === 'bake' }, lookCtx());
      if (view.target.level === 'preset' && view.target.name === id) view.target = view.back || { level: 'global' };
      tidyRing(); commit();
      undoToast('Deleted “' + id + '”' + (how === 'bake' ? '. What used it kept its look.' : '.'));
      R.look();
    }

    /* ---- right column: the banner, the group nav, then the groups */
    const hidden = full ? [] : level0 === 'global' ? fullOnlyChanges(S.cfg, 'look')
      : level0 === 'menu' ? window.ZMode.fullOnlyLookNames(Z.settings(S.cfg, { level: 'menu', menu: target0.menu }, lookCtx())) : [];
    const nav = h('nav', { class: 'look-nav', 'aria-label': 'Groups of settings' });
    const groupsBox = h('div', { class: 'look-groups' });
    const readOnly = level0 === 'preset' && own(Z.prep(lookCtx()).builtin, target0.name);
    if (level0 === 'preset') {
      const users = Z.usersOf(S.cfg, target0.name), n = users.menus.length;
      const used = (users.global ? 'It is the look for all menus' + (n ? ' and ' + plural(n, 'menu') + ' use it' : '') : n ? plural(n, 'menu') + (n === 1 ? ' uses' : ' use') + ' it' : 'No menu uses it yet') + '.';
      const done = h('button', { class: 'btn small', type: 'button', dataset: { fk: 'look:done' }, onclick: () => { view.target = view.back || { level: 'global' }; view.back = null; R.look(); } }, 'Done');
      groupsBox.append(h('div', { class: 'look-banner', role: 'status' }, icon('look', 16),
        h('div', { class: 'grow' }, h('b', null, readOnly ? 'Viewing the built-in look ' + lookName(target0.name) + '.' : 'Editing look ' + target0.name + '.'), ' ' + used + (readOnly ? ' Built-in looks cannot be changed.' : ' Changes apply to all of them.')),
        readOnly ? h('button', { class: 'btn small primary', type: 'button', onclick: () => duplicateThenEdit(target0.name) }, icon('copy', 12), 'Duplicate to edit') : null, done));
    }
    function duplicateThenEdit(id) {
      const to = freeName(id + ' copy');
      Z.duplicate(S.cfg, id, to, lookCtx());
      commit();
      view.target = { level: 'preset', name: to };
      toast2('Made “' + to + '” from ' + lookName(id) + '. You are editing it now.');
      R.look();
    }
    const toast2 = m => K.toast(m, { ms: 3200 });
    if (hidden.length) groupsBox.append(h('div', { class: 'mode-note look-modenote', role: 'status' }, 'Changed in Full mode and not shown here: ' + hidden.join(', ') + '. ', linkBtn('Switch to Full mode', () => setMode('full'))));
    const inner = h('div', { class: 'look-ctl' + (readOnly ? ' ro' : '') });
    groupsBox.append(inner);

    /* ---- folding (Full only: Simple has three or four groups, drawn open under a plain heading).
       Open: the person's own choice (view.fold), else Slots, else a group with settings of its own at this level. A closed group says what it holds in
       one line (GROUP_SUM) and how many of its settings are set here. */
    const animSetHere = () => (level0 === 'menu' ? !!(menuOf(target0.menu) || {}).animation : level0 === 'global' && K.ring().animation !== undefined && K.ring().animation !== S.defaults.animation);
    const setCounts = () => {
      const out = {};
      let keys = Z.settings(S.cfg, target(), lookCtx());
      if (level0 === 'preset' && readOnly) {                    // a built-in look is not in cfg.looks, so Z.settings does not see it: read its own definition
        const dict = Z.lookDict(S.cfg, target0.name, lookCtx()) || {};
        keys = Object.keys(dict).filter(k => k !== 'preset').flatMap(k => (k === 'colors' && isObj(dict.colors) ? Object.keys(dict.colors).map(n => 'colors.' + n) : [k]));
      }
      for (const k of keys) {
        let gid; try { gid = groupOfKey(k.split('.')[0]); } catch (e) { continue; }
        out[gid] = (out[gid] || 0) + 1;
      }
      if (animSetHere()) out.opening = 1;
      return out;
    };
    const pct = v => (typeof v === 'number' ? Math.round(v * 100) + '%' : '');
    const colourWord = v => (v === '' || v === undefined || v === null ? 'automatic' : COLOR_INFO[v] ? COLOR_INFO[v][0].toLowerCase() : 'custom');      // a role by name, never a hex
    const GROUP_SUM = {
      slots: v => [v.radius !== undefined ? 'Radius ' + v.radius : '', v.slot !== undefined ? 'slot ' + v.slot : '', v.slot_shape ? (SHAPE[v.slot_shape] ? SHAPE[v.slot_shape][0] : v.slot_shape).toLowerCase() : ''].filter(Boolean).join(', '),
      hub: v => (Number(v.hub) > 0 ? [HUB[v.hub_style] ? HUB[v.hub_style][0] : '', v.hub + ' px'].filter(Boolean).join(', ') : 'No hub'),
      glow: v => [valueNow('glow_color') !== undefined ? colourWord(valueNow('glow_color')) + ' glow' : '', pct(v.glow_opacity)].filter(Boolean).join(', '),
      labels: v => (v.labels && LABELS[v.labels] ? LABELS[v.labels][0] : valueNow('label_color') !== undefined ? colourWord(valueNow('label_color')) + ' label colour' : ''),
      colours: () => plural(Z.ROLES.length, 'colour'),
      tags: v => (['tint', 'both'].includes(v.tag_colors) ? 'Tint, ' : '') + (['glow', 'both'].includes(v.tag_colors) ? 'glow, ' : '') + (v.tag_band && v.tag_band !== 'none' ? 'band, ' : '') || 'Off',
      when_full: v => (FULL_WHEN[v.when_full] ? FULL_WHEN[v.when_full][0] : ''),
      opening: () => {
        const allA = animTitle(K.ring().animation || S.defaults.animation), own1 = level0 === 'menu' ? (menuOf(target0.menu) || {}).animation : '';
        return level0 === 'menu' ? (own1 ? animTitle(own1) + ', this menu only' : allA + ', same as all menus') : allA + (animSetHere() ? ', all menus' : ', the default');
      },
    };
    const folds = [];                                           // [{ id, el }] of the groups that fold
    const sumOf = (gid, vals, counts) => {
      let t = '';
      try { t = GROUP_SUM[gid] ? GROUP_SUM[gid](vals) : ''; } catch (e) { t = ''; }
      t = t.replace(/, $/, '');
      t = t ? t[0].toUpperCase() + t.slice(1) : t;
      return t + (counts[gid] ? (t ? ' · ' : '') + counts[gid] + ' set here' : '');
    };
    /* Only the closed groups show their summary, so only those are made again. */
    const paintSums = () => {
      const closed = folds.filter(f => !foldIsOpen(f.el));
      if (!closed.length) return;
      const vals = Z.explain(S.cfg, target(), lookCtx()).values, counts = setCounts();
      for (const f of closed) foldSum(f.el, sumOf(f.id, vals, counts));
    };
    const foldGroup = (gid, cdv, counts, vals) => {
      const kids = [...cdv.children], head = kids.shift(), em = head.querySelector('em');
      const open = view.fold[gid] ?? (gid === 'slots' || !!counts[gid]);
      if (open) view.fold[gid] = true;                          // built open by the rule: it stays open until the person closes it, whatever the next rebuild computes
      return foldSection({ id: 'look-g-' + gid, title: head.childNodes[0].textContent, sub: em ? em.textContent : null, summary: sumOf(gid, vals, counts),
        open, onToggle: v => { view.fold[gid] = v; if (!v) paintSums(); markActive(); } }, ...kids);
    };
    const shown = Z.groups(lookCtx(), curLevel).filter(g => full || !g.full);
    if (curLevel === 'global' || curLevel === 'menu') shown.push({ id: 'opening', title: 'Opening', full: false });      // in both modes; not a look group, so the schema does not list it
    const counts0 = full ? setCounts() : {}, vals0 = full ? Z.explain(S.cfg, target(), lookCtx()).values : {};
    for (const g of shown) {
      if (!GROUP_BUILD[g.id]) continue;
      let cdv = GROUP_BUILD[g.id]();
      if (full) { cdv = foldGroup(g.id, cdv, counts0, vals0); folds.push({ id: g.id, el: cdv }); }
      cdv.id = 'look-g-' + g.id;
      // A built-in look is read-only: its controls are inert, but a group can still be opened to read
      if (readOnly) (full ? cdv.querySelector('.fold-body') : cdv).inert = true;
      inner.append(cdv);
      sectionRefs.push({ id: g.id, card: cdv, btn: null });
    }
    view.sums = folds.length ? paintSums : null;
    const scroll = h('div', { class: 'look-scroll' }, nav, groupsBox);

    const sectionTop = el => el.getBoundingClientRect().top - scroll.getBoundingClientRect().top + scroll.scrollTop;
    const navH = () => nav.offsetHeight || 0;
    const markActive = () => {
      if (!sectionRefs.length) return;
      const lastCard = sectionRefs[sectionRefs.length - 1].card;
      // at the bottom the last chip is the one in view, but only when its group is open: a folded heading is no more in view than the group above it
      const atEnd = scroll.scrollHeight > scroll.clientHeight + 4 && scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 4 && (!lastCard.classList.contains('fold') || foldIsOpen(lastCard));
      let active = sectionRefs[0];
      for (const s of sectionRefs) if (sectionTop(s.card) <= scroll.scrollTop + navH() + 24) active = s;
      if (atEnd) active = sectionRefs[sectionRefs.length - 1];
      if (pinned && sectionRefs.includes(pinned)) active = pinned;
      for (const s of sectionRefs) {
        const on = s === active;
        s.btn.classList.toggle('on', on);
        if (on) s.btn.setAttribute('aria-current', 'location'); else s.btn.removeAttribute('aria-current');
      }
      const g = active.id === 'glow';                       // the hover glow is shown on the selected slot while its group is in view
      if (g !== glowInView) { glowInView = g; if (!g) view.pinOff = false; if (sl0 !== null) { syncPin(); paintRing(); R.preview(); } }
    };
    const goGroup = (s, flash) => {
      if (!foldIsOpen(s.card) && s.card.classList.contains('fold')) { foldOpen(s.card, true); view.fold[s.id] = true; }      // open first: the scroll and the flash use the height it has then
      pinned = s; markActive();
      scroll.scrollTo({ top: Math.max(0, sectionTop(s.card) - navH() - 12), behavior: 'smooth' });
      if (flash) { s.card.classList.remove('flash'); void s.card.offsetWidth; s.card.classList.add('flash'); }
    };
    for (const s of sectionRefs) {
      s.btn = h('button', { class: 'look-navbtn', type: 'button', onclick: () => goGroup(s, true) }, (shown.find(x => x.id === s.id) || {}).title);
      nav.append(s.btn);
    }
    let raf = 0;
    const unpin = () => { if (pinned) { pinned = null; markActive(); } };
    for (const ev of ['wheel', 'keydown', 'pointerdown', 'touchstart']) scroll.addEventListener(ev, unpin, { passive: true });
    scroll.addEventListener('scroll', () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; markActive(); }); }, { passive: true });

    /* A problem's target: show the group, focus the control. The control is found by its data-fk key (look:<key>, or look:<key>/<part>). */
    R.lookGoto = (key, group) => {
      if (!key || String(key).startsWith('_')) {                         // a look as a whole: the gallery
        const first = left.querySelector('.lk-opt[tabindex="0"]') || left.querySelector('.lk-opt');
        if (first) { first.scrollIntoView({ block: 'nearest' }); first.focus({ preventScroll: true }); }
        return;
      }
      const cands = $$('[data-fk="look:' + key + '"], [data-fk^="look:' + key + '/"]', scroll).filter(e => !e.disabled && !/\/reset$/.test(e.dataset.fk));
      const el = cands.find(e => e.classList.contains('on') || e.getAttribute('aria-checked') === 'true') || cands[0];
      const s = (el && sectionRefs.find(x => x.card.contains(el))) || sectionRefs.find(x => x.id === group) || sectionRefs[0];
      if (!s) return;
      goGroup(s, true);                                                  // opens the group, so the control can take the focus
      if (el) el.focus({ preventScroll: true });
    };

    root.replaceChildren(levelBar, h('div', { class: 'look-body' }, left, scroll));
    paintTagNote();
    markActive();
    paintLive();
    R.preview();
    if (gallery) wantThumbs();

    const focusables = () => $$('input, button, select, textarea, [tabindex]', root);
    R.look = () => {
      const act = document.activeElement, key = act && root.contains(act) ? lookFk(act) : null, top = scroll.scrollTop, ltop = left.scrollTop;
      window.buildLookScreen(root);
      const sc = $('.look-scroll', root), lf = $('.look-left', root);
      if (sc) sc.scrollTop = top;
      if (lf) lf.scrollTop = ltop;
      const again = key && focusables().find(el => lookFk(el) === key && !el.disabled);
      if (again) again.focus({ preventScroll: true });
    };
  };

  /* A target that is gone (a deleted menu or look, an undo) or a level the backend cannot do: back to Global. */
  function fixTarget() {
    const t = view.target, c = lookCtx();
    if (!Z.hasPresets(c)) { view.target = { level: 'global' }; return; }
    if (t.level === 'preset' && !isFull()) { view.target = { level: 'global' }; return; }       // editing a look is Full only
    if (t.level === 'menu' && !hasMenu(t.menu)) view.target = { level: 'global' };
    else if (t.level === 'preset' && !Z.lookDict(S.cfg, t.name, c)) view.target = { level: 'global' };
    else if (Z.isSlot(t) && (!isFull() || !usableIdx(t.menu).includes(t.slot))) view.target = { level: 'menu', menu: t.menu };      // no slot level in Simple, or the item is gone or unusable
    if (view.target.level === 'menu') view.last = view.target.menu;
    if (Z.isSlot(view.target)) view.lastSlot = { menu: view.target.menu, slot: view.target.slot };
  }
})();
