/* ZOrbit Studio: the Look screen.

   Loaded after app.js, which is one closure and hands over what this file needs as window.ZStudio (see "What look-screen.js
   needs" there). look.js (window.ZLook) resolves a look key to { value, origin }; this file draws the controls.

   Shape, for the phases that follow:
   - view.target says what is being edited: { level: 'global' } today. LEVELS lists the levels the level bar can show; a menu,
     slot or preset level is one more entry there, plus the same level in look.js (holder) and in lookAccess below.
   - lookAccess(key) is the one place a control reads and writes a look key. Every control goes through it, so a level change
     is made there and nowhere else. (The Simple "Ring size" slider, sizeRow in app.js, still writes cfg.ring itself.)
   - lookRow(row, ...) puts the source badge and the "Reset to default" wording on a control row; a control that is not a row
     (a group of cards, a colour row) is built from the same pieces.
   - GROUPS (look.js) are the cards on the right and the entries of the group nav. A new key joins a group; a new group is one
     more entry there and one more builder in `groups` below. */
(() => {
  'use strict';
  const K = window.ZStudio, Z = window.ZLook;
  if (!K || !Z) return;                                       // app.js or look.js did not load: app.js shows a note in place of this screen
  const { h, $, $$, S, R, icon, iconBtn, linkBtn, card, choiceCards, sliderRow, sizeRow, toggleSwitch, normHex, commit, tidyRing, usableIdx, menuOf, kindOf,
    isLib, firstTag, isFull, setMode, fullOnlyChanges, RingLoader, SAMPLE_MENU, COLOR_INFO } = K;

  /* The levels the bar offers. Only Global exists so far. */
  const LEVELS = [{ id: 'global', label: 'Global', hint: 'The look every menu starts from.' }];
  const view = { target: { level: 'global' }, menuId: null };     // outlives a rebuild of the screen

  const ORIGIN = {
    default: ['Default', 'The built-in value. Change the control to set your own.'],
    theme: ['Theme', 'The colour comes from the theme. Change the control to set your own.'],
    global: ['Global', 'Set here, for every menu. Reset to go back to the default.'],
  };
  const resetWord = () => 'Reset to default';                    // becomes "Reset to inherited" once there is something above the default

  const lookCtx = () => ({ defaults: S.defaults, theme: S.themeEff || 'dark' });
  const target = () => view.target;

  /* One look key as the controls see it. key is 'radius', or 'colors.bg' for one colour. */
  function lookAccess(key) {
    const [k, sub] = key.split('.');
    const read = () => Z.resolve(S.cfg, target(), lookCtx())[k];
    const a = {
      key,
      get: () => (sub ? read().sub[sub].value : read().value),
      origin: () => Z.originOf(S.cfg, target(), key, lookCtx()),
      isSet: () => Z.isSet(S.cfg, target(), key, lookCtx()),
      put: v => { if (Z.set(S.cfg, target(), key, v, lookCtx())) { tidyRing(); commit(); } },
      clear: () => { if (Z.clear(S.cfg, target(), key)) { tidyRing(); commit(); } },
    };
    a.slider = { get: a.get, put: a.put, clear: a.clear, isSet: a.isSet };     // what sliderRow takes
    return a;
  }

  /* What Settings > Ring look says: the groups with something set at the global level. */
  const SUMMARY_NAME = { radius: 'Ring size', slot: 'Ring size', dead_zone: 'Ring size', slot_shape: 'Slot shape', hub: 'Hub', labels: 'Labels', colors: 'Colours' };
  window.lookSummary = () => {
    const names = [];
    for (const k of Z.changed(S.cfg, { level: 'global' }, lookCtx())) {
      const n = SUMMARY_NAME[k] || 'Tag colours';
      if (!names.includes(n)) names.push(n);
    }
    return names.length ? 'Changed from the default: ' + names.join(', ') + '.' : 'Everything is at its default.';
  };
  /* What the screen draws from the config: when this is the same before and after an undo, the screen is left alone (and keeps focus). */
  window.lookSig = () => JSON.stringify([S.cfg.ring, Object.entries(S.cfg.menus).map(([id, m]) => [id, m && m.title])]);

  /* Rebuilt after an undo, a revert or a reload: the control that had focus gets it back (found by its data-fk key, else its label). */
  const lookFk = el => el.dataset.fk || [el.tagName, el.type || '', el.getAttribute('aria-label') || '', (el.closest('[role="radiogroup"]') || el).getAttribute('aria-label') || '', el.dataset.v || ''].join('|');

  window.buildLookScreen = root => {
    const target0 = view.target;
    let badges = [];                                          // repaint functions of the source badges
    const paintBadges = () => badges.forEach(f => f());
    const sectionRefs = [];                                   // [{ id, card, btn }], in order
    let pinned = null;

    /* ---- the preview (left column) */
    const img = h('img', { class: 'ring-img', alt: 'Ring preview', draggable: false });
    const dz = h('div', { class: 'dz-ring', 'aria-hidden': 'true' });
    const wrap = h('div', { class: 'mini-wrap' }, img, dz);
    const cap = h('div', { class: 'mini-cap micro' });
    const stage = h('div', { class: 'mini-stage' }, h('div', { class: 'stage-rings', 'aria-hidden': 'true' }), wrap, cap);
    let msize = 447, ptok = 0;
    const paintDZ = () => { const k = (wrap.clientWidth || 280) / msize, d = K.ringNum('dead_zone') * 2 * k; dz.style.width = dz.style.height = d + 'px'; };
    const live = () => { paintDZ(); paintBadges(); };
    const previewId = () => (view.menuId === SAMPLE_MENU ? SAMPLE_MENU : (view.menuId && menuOf(view.menuId) ? view.menuId : S.menuId));
    const paintCap = () => {
      const id = previewId(), m = id === SAMPLE_MENU ? null : menuOf(id);
      cap.textContent = id === SAMPLE_MENU ? 'Sample ring' : 'Preview: ' + ((m && m.title) || id || '');
    };
    R.preview = async () => {
      const id = previewId(), sample = id === SAMPLE_MENU, tok = ++ptok;
      paintCap();
      const none = !sample && (!menuOf(id) || !usableIdx(id).length);
      stage.classList.toggle('none', none);
      wrap.hidden = none;
      if (none) return;
      const ver = S.version;
      const res = await RingLoader.get(id, null, null, sample ? 'tags' : 'main');
      if (tok !== ptok || ver !== S.version || !res) return;
      if (res.image) img.src = res.image;
      else if (res.error || (res.problems || []).length) cap.textContent = 'No preview: ' + (res.problems || [])[0];
      msize = res.size || msize; paintDZ();
    };
    const peek = RingLoader.peek(previewId(), null, null);       // a rebuild shows the picture it had at once
    if (peek && peek.image) { img.src = peek.image; msize = peek.size || msize; }

    const picker = h('select', { class: 'inp sel', 'aria-label': 'Menu to preview', dataset: { fk: 'look:preview-menu' }, onchange: () => {
      view.menuId = picker.value; R.preview(); paintTagNote();
    } },
    ...Object.entries(S.cfg.menus).map(([id, m]) => h('option', { value: id, selected: id === previewId() }, (m && m.title) || id)),
    h('option', { value: SAMPLE_MENU, selected: previewId() === SAMPLE_MENU }, 'Sample ring with tags'));
    const left = h('aside', { class: 'look-left', 'aria-label': 'Ring preview' }, stage,
      h('label', { class: 'look-pick' }, h('span', { class: 'micro' }, 'Preview menu'), picker),
      h('div', { class: 'fhint' }, 'The dashed circle is the dead zone: no slot is picked this close to the centre.'));

    /* ---- level bar */
    const levelBar = h('div', { class: 'look-levels' }, h('h1', { class: 'look-title' }, 'Look'),
      h('div', { class: 'look-chips', role: 'radiogroup', 'aria-label': 'Where the look applies' },
        ...LEVELS.map(l => h('button', { class: 'look-chip' + (l.id === target0.level ? ' on' : ''), type: 'button', role: 'radio', 'aria-checked': l.id === target0.level ? 'true' : 'false',
          tabindex: l.id === target0.level ? '0' : '-1', title: l.hint, dataset: { level: l.id },
          onclick: () => { if (l.id !== view.target.level) { view.target = { level: l.id }; R.look(); } } }, l.label))),
      h('span', { class: 'look-levelnote' }, (LEVELS.find(l => l.id === target0.level) || LEVELS[0]).hint));

    /* ---- the pieces every control row is made from */
    /* The source badge: where the value comes from. A button, so it can take focus and later open the levels; for now it moves to the control. */
    const addBadge = (slabel, keys, access) => {
      const name = slabel.firstElementChild;
      const b = h('button', { class: 'lk-badge', type: 'button', onclick: () => { const c = slabel.closest('.srow, .crow, .tg-head, .lk-stack'); const f = c && $('input:not([disabled]), button.choice.on, button.choice:not([disabled])', c); if (f) f.focus(); } });
      const paint = () => {
        const os = keys.map(k => access(k).origin());
        const o = os.includes('global') ? 'global' : os[0];
        b.textContent = ORIGIN[o][0];
        b.className = 'lk-badge ' + o;
        b.title = ORIGIN[o][1];
        b.setAttribute('aria-label', 'Source: ' + ORIGIN[o][0] + '. ' + ORIGIN[o][1]);
      };
      const line = h('div', { class: 'lk-line' }, name, b);
      slabel.prepend(line);
      badges.push(paint); paint();
      return b;
    };
    /* A row from sliderRow (or sizeRow): the badge, the focus keys and the reset wording. */
    const lookRow = (row, keys) => {
      addBadge($('.slabel', row), keys, lookAccess);
      const base = 'look:' + keys[0];
      for (const el of $$('[data-fk]', row)) {
        const m = /\/(range|num|reset)$/.exec(el.dataset.fk);
        el.dataset.fk = m && m[1] === 'range' ? base : base + '/' + (m ? m[1] : 'x');
      }
      for (const r of $$('.reset', row)) { r.title = r.title.replace(/^Reset to default/, resetWord()); r.setAttribute('aria-label', r.title); }
      return row;
    };
    const slider = (key, o) => lookRow(sliderRow(Object.assign({ key, onLive: live }, o, lookAccess(key).slider)), [key]);

    /* A row of choice cards with the label above: Slot shape, Labels. */
    const choiceRow = ({ label, hint, key, items, cls }) => {
      const A = lookAccess(key);
      const wrapC = choiceCards(items, A.get(), v => { A.put(v); paintBadges(); paintReset(); }, cls, label);
      for (const b of $$('.choice', wrapC)) b.dataset.fk = 'look:' + key + '/' + b.dataset.v;
      const reset = iconBtn('undo', resetWord(), () => {
        const def = S.defaults[key], b = $$('.choice', wrapC).find(x => x.dataset.v === String(def));
        if (b) { b.click(); b.focus(); }
      }, 'reset');
      reset.dataset.fk = 'look:' + key + '/reset';
      const paintReset = () => { reset.style.visibility = A.isSet() ? 'visible' : 'hidden'; };
      paintReset();
      const slabel = h('div', { class: 'slabel' }, h('span', null, label), hint ? h('small', null, hint) : null);
      addBadge(slabel, [key], lookAccess);
      return h('div', { class: 'srow lk-stack' }, h('div', { class: 'lk-head' }, slabel, reset), wrapC);
    };

    /* ---- the groups */
    const groupSlots = () => {
      const full = isFull();
      const rows = full ? [
        slider('radius', { label: 'Ring radius', hint: 'Distance from the centre to the slots', unit: 'px' }),
        slider('slot', { label: 'Slot size', hint: 'Diameter of each icon disc', unit: 'px' }),
        slider('dead_zone', { label: 'Dead zone', hint: 'No slot is picked this close to the centre (dashed circle)', unit: 'px' })]
        : [lookRow(sizeRow(live), ['radius', 'slot', 'dead_zone'])];
      const shapeOpts = (S.opts && S.opts.slot_shapes) || ['circle', 'rounded'];
      const SHAPE = { circle: ['Circle', 'Round slots.'], rounded: ['Rounded square', 'Square slots with rounded corners, the same size.'] };
      rows.push(choiceRow({ label: 'Slot shape', key: 'slot_shape', cls: 'two', items: shapeOpts.map(v => [v, (SHAPE[v] || [v, ''])[0], (SHAPE[v] || [v, ''])[1]]) }));
      return card('Slots', full ? 'Size, spacing and shape' : 'How big the ring is, and its shape', ...rows);
    };
    const groupHub = () => card('Hub', 'The dot in the centre',
      slider('hub', { label: 'Hub', hint: 'Size of the accent dot in the centre, 0 for none', unit: 'px' }));
    const groupLabels = () => {
      const labelOpts = (S.opts && S.opts.labels) || ['name', 'none'];
      const LAB = { name: ['Icon and name', 'Each slot shows its label underneath.'], none: ['Icon only', 'A cleaner ring. Names appear only in this Studio.'] };
      return card('Labels', null, choiceRow({ label: 'Labels', key: 'labels', cls: 'two', items: labelOpts.map(l => [l, (LAB[l] || [l, ''])[0], (LAB[l] || [l, ''])[1]]) }));
    };
    const colourRow = name => {
      const A = lookAccess('colors.' + name), info = COLOR_INFO[name];
      const sw = h('input', { type: 'color', class: 'swatch', value: A.get(), 'aria-label': info[0] + ' colour', dataset: { fk: 'look:colors/' + name } });
      const hex = h('input', { class: 'inp mono hex', type: 'text', value: A.get(), maxlength: '7', spellcheck: 'false', 'aria-label': info[0] + ' hex value', dataset: { fk: 'look:colors/' + name + '/hex' } });
      const hmsg = h('span', { class: 'hex-msg', role: 'status' });
      const rs = iconBtn('undo', resetWord(), () => { A.clear(); paint(); }, 'reset');
      rs.dataset.fk = 'look:colors/' + name + '/reset';
      const showReset = () => { rs.title = resetWord() + ' (' + S.defaults.colors[name] + ')'; rs.setAttribute('aria-label', rs.title); rs.style.visibility = A.isSet() ? 'visible' : 'hidden'; paintBadges(); };
      const paint = () => { const v = A.get(); sw.value = v; hex.value = v; hex.classList.remove('bad'); hmsg.textContent = ''; showReset(); };
      sw.addEventListener('input', () => { A.put(sw.value); paint(); });
      hex.addEventListener('input', () => {
        const n = normHex(hex.value), bad = !n;
        hex.classList.toggle('bad', bad); hmsg.textContent = bad ? 'Use #rrggbb' : '';
        if (n && hex.value.trim().replace('#', '').length === 6) { A.put(n); sw.value = n; showReset(); }     // short forms wait for Enter or blur
      });
      const apply = () => { const n = normHex(hex.value); if (n && n !== A.get().toLowerCase()) A.put(n); paint(); };
      hex.addEventListener('blur', apply);
      hex.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); apply(); } });
      colourPaints.push(paint);
      const slabel = h('div', { class: 'slabel' }, h('span', null, info[0]), h('small', null, info[1]));
      addBadge(slabel, ['colors.' + name], lookAccess);
      showReset();
      return h('div', { class: 'crow lk-crow' }, sw, slabel, h('div', { class: 'hexwrap' }, hex, hmsg), rs);
    };
    const colourPaints = [];
    const groupColours = () => card('Colours', 'Applied to the ring in the app',
      h('div', { class: 'colors' }, Z.COLOUR_KEYS.map(colourRow)),
      h('div', { class: 'btn-row' }, h('button', { class: 'btn small', type: 'button', onclick: () => {
        for (const n of Z.COLOUR_KEYS) Z.clear(S.cfg, target(), 'colors.' + n);
        tidyRing(); commit(); colourPaints.forEach(f => f());
      } }, icon('undo', 12), 'Reset all colours')));

    /* Tag colours: how a brush's first tag shows on its slot (tag slots always show their tag's colour). Three effects, each a switch
       with its own controls; tint and glow together are the stored tag_colors. */
    const tagNote = h('div', { class: 'fhint' });
    const hasTagged = m => !!m && (m.items || []).some(it => { const ik = kindOf(it); return isLib(ik) && firstTag(ik, it[ik]); });
    function paintTagNote() {
      const id = previewId(), m = id === SAMPLE_MENU ? null : menuOf(id);
      tagNote.replaceChildren();
      if (id === SAMPLE_MENU || hasTagged(m)) return;
      tagNote.append('This menu has no tagged brushes, so these effects do not show on it. ',
        linkBtn('Preview the sample ring', () => { view.menuId = SAMPLE_MENU; picker.value = SAMPLE_MENU; R.preview(); paintTagNote(); }), '.');
    }
    const groupTags = () => {
      const A = k => lookAccess(k);
      const tc = () => A('tag_colors').get() || 'tint';
      const tintOn = () => tc() === 'tint' || tc() === 'both', glowOn = () => tc() === 'glow' || tc() === 'both';
      const setTc = (tint, glow) => { A('tag_colors').put(tint && glow ? 'both' : tint ? 'tint' : glow ? 'glow' : 'none'); paintBadges(); };
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
      const segRow = ({ label, hint, key, opts, on, onPick }) => {
        const row = h('div', { class: 'srow' }, h('div', { class: 'slabel' }, h('span', null, label), hint ? h('small', null, hint) : null),
          choiceCards(opts, onPick ? bandWas : A(key).get(), onPick || (v => { A(key).put(v); paintBadges(); }), 'seg', label));
        addBadge($('.slabel', row), [key], lookAccess);
        for (const b of $$('.choice', row)) b.dataset.fk = 'look:' + key + '/' + b.dataset.v;
        tcRows.push([row, on]); return row;
      };
      const opacity = (key, on) => { const row = slider(key, { label: 'Opacity', step: 5, scale: 100, unit: '%' }); tcRows.push([row, on]); return row; };
      const group = ({ label, hint, key, tag, on, set, rows }) => {
        const sw = toggleSwitch(on(), v => { set(v); paintTc(); }, label);
        sw.querySelector('input').dataset.fk = 'look:' + key + '/' + tag;
        const slabel = h('div', { class: 'slabel' }, h('span', null, label), h('small', null, hint));
        addBadge(slabel, [key], lookAccess);
        return h('div', { class: 'tgroup' }, h('div', { class: 'tg-head' }, slabel, sw), h('div', { class: 'tg-body' }, ...rows));
      };
      const bandOpts = ((S.opts && S.opts.tag_bands) || ['none', 'hairline', 'narrow', 'medium', 'wide']).filter(v => v !== 'none').map(v => [v, cap(v), '']);
      const BLEND = { multiply: 'Darken', overlay: 'Keep highlights' };
      const c = card('Tag colours', "How a brush's tags show on its slots", tagNote,
        group({ label: 'Icon tint', hint: 'A coloured rim, and the tag colour laid over the icon', key: 'tag_colors', tag: 'tint', on: tintOn, set: v => setTc(v, glowOn()), rows: [
          opacity('tag_tint_opacity', tintOn),
          segRow({ label: 'Style', hint: 'Gradient is stronger towards the rim', key: 'tag_tint_style', on: tintOn, opts: ((S.opts && S.opts.tint_styles) || ['flat', 'gradient']).map(v => [v, cap(v), '']) }),
          segRow({ label: 'Blend', key: 'tag_tint_blend', on: tintOn, opts: ((S.opts && S.opts.tint_blends) || ['multiply', 'overlay']).map(v => [v, BLEND[v] || cap(v), '']) })] }),
        group({ label: 'Glow', hint: 'A soft halo in the tag colour around the slot', key: 'tag_colors', tag: 'glow', on: glowOn, set: v => setTc(tintOn(), v), rows: [
          opacity('tag_glow_opacity', glowOn)] }),
        group({ label: 'Band', hint: 'A coloured strip through the slots, one stretch per slot', key: 'tag_band', tag: 'band', on: bandOn,
          set: v => { A('tag_band').put(v ? bandWas : 'none'); paintBadges(); }, rows: [
            segRow({ label: 'Thickness', key: 'tag_band', on: bandOn, opts: bandOpts, onPick: v => { bandWas = v; A('tag_band').put(v); paintBadges(); } }),
            opacity('tag_band_opacity', bandOn)] }));
      paintTc();
      return c;
    };
    const GROUP_BUILD = { slots: groupSlots, hub: groupHub, labels: groupLabels, colours: groupColours, tags: groupTags };

    /* ---- right column: the group nav, then the groups */
    const full = isFull();
    const hidden = full ? [] : fullOnlyChanges(S.cfg, 'look');
    const nav = h('nav', { class: 'look-nav', 'aria-label': 'Groups of settings' });
    const groupsBox = h('div', { class: 'look-groups' });
    if (hidden.length) groupsBox.append(h('div', { class: 'mode-note look-modenote', role: 'status' }, 'Changed in Full mode and not shown here: ' + hidden.join(', ') + '. ', linkBtn('Switch to Full mode', () => setMode('full'))));
    for (const g of Z.GROUPS.filter(x => full || !x.full)) {
      const c = GROUP_BUILD[g.id]();
      c.id = 'look-g-' + g.id;
      groupsBox.append(c);
      sectionRefs.push({ id: g.id, card: c, btn: null });
    }
    const scroll = h('div', { class: 'look-scroll' }, nav, groupsBox);

    const sectionTop = el => el.getBoundingClientRect().top - scroll.getBoundingClientRect().top + scroll.scrollTop;
    const navH = () => nav.offsetHeight || 0;
    const markActive = () => {
      if (!sectionRefs.length) return;
      const atEnd = scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 4;
      let active = sectionRefs[0];
      for (const s of sectionRefs) if (sectionTop(s.card) <= scroll.scrollTop + navH() + 24) active = s;
      if (atEnd) active = sectionRefs[sectionRefs.length - 1];
      if (pinned && sectionRefs.includes(pinned)) active = pinned;
      for (const s of sectionRefs) {
        const on = s === active;
        s.btn.classList.toggle('on', on);
        if (on) s.btn.setAttribute('aria-current', 'location'); else s.btn.removeAttribute('aria-current');
      }
    };
    const goGroup = (s, flash) => {
      pinned = s; markActive();
      scroll.scrollTo({ top: Math.max(0, sectionTop(s.card) - navH() - 12), behavior: 'smooth' });
      if (flash) { s.card.classList.remove('flash'); void s.card.offsetWidth; s.card.classList.add('flash'); }
    };
    for (const s of sectionRefs) {
      s.btn = h('button', { class: 'look-navbtn', type: 'button', onclick: () => goGroup(s, true) }, Z.GROUPS.find(x => x.id === s.id).title);
      nav.append(s.btn);
    }
    let raf = 0;
    const unpin = () => { if (pinned) { pinned = null; markActive(); } };
    for (const ev of ['wheel', 'keydown', 'pointerdown', 'touchstart']) scroll.addEventListener(ev, unpin, { passive: true });
    scroll.addEventListener('scroll', () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; markActive(); }); }, { passive: true });

    /* A problem's target: show the group, focus the control. The control is found by its data-fk key (look:<key>, or look:<key>/<part>). */
    R.lookGoto = (key, group) => {
      const s = sectionRefs.find(x => x.id === group) || sectionRefs[0];
      if (!s) return;
      goGroup(s, true);
      const el = $('[data-fk="look:' + key + '"]', scroll) || $('[data-fk^="look:' + key + '/"]', scroll);
      if (el) el.focus({ preventScroll: true });
    };

    root.replaceChildren(levelBar, h('div', { class: 'look-body' }, left, scroll));
    paintTagNote();
    markActive();
    R.preview();

    const focusables = () => $$('input, button, select, textarea, [tabindex]', root);
    R.look = () => {
      const act = document.activeElement, key = act && root.contains(act) ? lookFk(act) : null, top = scroll.scrollTop;
      window.buildLookScreen(root);
      const sc = $('.look-scroll', root);
      if (sc) sc.scrollTop = top;
      const again = key && focusables().find(el => lookFk(el) === key && !el.disabled);
      if (again) again.focus({ preventScroll: true });
    };
  };
})();
