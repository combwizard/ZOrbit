"""Loads and validates radial.json.

Schema (all keys optional except menus):

{
  "bridge": {"mode": "auto", "key": "F9"},
      # mode "message": post to the listener window inside ZBrush (no keystroke)
      # mode "key":     press the bridge key, which must be bound natively in ZBrush to
      #                 Zplugin > ZOrbit > Apply (Ctrl+Alt+click it, press the key, Preferences >
      #                 Hotkeys > Store)
      # mode "auto":    message if the listener is alive, else key; and key as a fallback if a message
      #                 was not picked up within 0.5 s
  "ring": {"radius": 145, "slot": 72, "dead_zone": 38, "tap_ms": 250, "timeout_s": 20,
           "animation": "smooth",            # smooth bounce pop zoom fade drift fancy spiral ripple breath
                                             # mist snappy
           "labels": "name",                 # name | none
           "tag_colors": "tint",             # none | tint | glow | both: how a brush's first tag shows on its slot
           "tag_band": "medium",             # none | hairline | narrow | medium | wide: a band through the slots,
                                             # coloured per slot by its tag
           "tag_band_opacity": 0.45,         # 0 to 1
           "tag_glow_opacity": 0.4,          # 0 to 1: the halo of glow and both
           "tag_tint_opacity": 0.3,          # 0 to 1: the tag colour over a slot's icon, for tint and both
           "tag_tint_style": "gradient",     # flat | gradient (stronger towards the rim)
           "tag_tint_blend": "multiply",     # multiply | overlay
           "flick": true,                    # moving out past a slot picks it without releasing the hotkey
           "hover_submenus": true,           # reaching a submenu slot opens that submenu, centred on it
           "colors": {"bg": "#222327", "accent": "#f86b33", "highlight": "#4dc8e9", "text": "#f0f0f0",
                      "lines": "#f86b33"}},
  "browser": {"hotkey": "Alt+B"},         # opens the browser popout (tabs per kind, tags, search, folders)
  "menus": {
    "<id>": {
      "title": "Brushes",
      "hotkey": "Q",                   # optional; menus without one are submenus only
      "swallow": true,                 # hide the hotkey from ZBrush (default true)
      "animation": "spiral",           # optional; this menu's open animation instead of ring.animation
      "fan": true,                     # optional; opened as a submenu, its items fan out from that slot
                                       # and the ring stays (default false: a new ring centred on the slot)
      "items": [ <item>, ... ]         # drawn clockwise from the top
    }
  }
}

<item> is one action plus an optional "label" and "icon" (path to a .png/.zbp, or a brush name):
  {"brush": "ClayBuildup"}                       select a brush (loaded from its .zbp if needed)
  {"alpha": "Alpha 58"}                          select an alpha (imported from its file if needed)
  {"material": "SkinShade4"}                     select a material (Material:Load replaces the selected slot)
  {"texture": "Txtr01"}                          select a texture (imported from its file if needed)
  {"press": "Tool:Masking:Clear"}                press any ZBrush button by item path
  {"set": "Draw:Draw Size", "value": 64}         set a slider or value
  {"toggle": "Transform:Activate Symmetry"}      flip a switch
  {"steps": [<action>, ...]}                     run several actions in order
  {"menu": "<id>"}                               open another ring in place
  {"auto": "brush"}                              a slot the app fills with a brush you pick often (usage.py)
  {"tag": "blocking"}                            a submenu of every brush carrying that tag (tags.py), most used first
  {"browser": "", "kind": "alpha"}               open the browser (tabs: brush alpha material texture) on that
                                                 tab (default brush); a tag key filters it ("" = everything)

Menu ids starting with "tag:" are reserved for the submenus a tag slot opens.
"""
import difflib
import json
import os
import re
from dataclasses import dataclass, field

ACTION_KEYS = ("brush", "alpha", "material", "texture", "press", "set", "toggle", "steps", "menu", "auto", "tag",
               "browser")
ASSET_KINDS = ("brush", "alpha", "material", "texture")     # the kinds of the browser and of tags
AUTO_KINDS = ("brush",)
ANIMATIONS = ("smooth", "bounce", "pop", "zoom", "fade", "drift", "fancy", "spiral", "ripple", "breath", "mist",
              "snappy")
LABEL_MODES = ("name", "none")
TAG_COLOR_MODES = ("none", "tint", "glow", "both")
TAG_BANDS = ("none", "hairline", "narrow", "medium", "wide")
TINT_STYLES = ("flat", "gradient")
TINT_BLENDS = ("multiply", "overlay")

DEFAULT_RING = {"radius": 145, "slot": 72, "dead_zone": 38, "tap_ms": 250, "timeout_s": 20,
                "animation": "smooth", "labels": "name", "tag_colors": "tint", "flick": True, "hover_submenus": True,
                "tag_band": "medium", "tag_band_opacity": 0.45, "tag_glow_opacity": 0.4, "tag_tint_opacity": 0.3,
                "tag_tint_style": "gradient", "tag_tint_blend": "multiply",
                "colors": {"bg": "#222327", "accent": "#f86b33", "highlight": "#4dc8e9", "text": "#f0f0f0",
                           "lines": "#f86b33"}}
_RING_SWITCHES = ("flick", "hover_submenus")
_RING_CHOICES = {"tag_colors": TAG_COLOR_MODES, "tag_band": TAG_BANDS, "tag_tint_style": TINT_STYLES,
                 "tag_tint_blend": TINT_BLENDS}
_RING_RANGES = {"radius": (60, 400), "slot": (32, 160), "dead_zone": (10, 120), "tap_ms": (0, 1000),
                "timeout_s": (2, 120), "tag_band_opacity": (0, 1), "tag_glow_opacity": (0, 1),
                "tag_tint_opacity": (0, 1)}

_NAMED_VK = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "`": 0xC0, "~": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
    "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
MENU_KEYS = ("title", "hotkey", "swallow", "animation", "fan", "items")
DEFAULT_BRIDGE_KEY = "F9"          # used when radial.json has no usable bridge.key
_MODS = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift"}


@dataclass(frozen=True)
class Hotkey:
    vk: int
    ctrl: bool = False
    alt: bool = False
    shift: bool = False
    text: str = ""


@dataclass
class Item:
    label: str
    kind: str                 # one of ACTION_KEYS
    data: dict                # the raw action dict ({"brush": ...}, {"steps": [...]}, ...)
    icon: str = ""            # explicit icon, else derived from a brush action
    auto: bool = False        # put into an auto slot by the app (from usage.json), not by the user
    tag: str = ""             # tag key of a tag item (and of the submenu it opens)
    color: str = ""           # #rrggbb from the item's tag, stamped by expand.py, never by the loader


@dataclass
class Menu:
    id: str
    title: str
    items: list
    hotkey: Hotkey | None = None
    swallow: bool = True
    animation: str = ""       # one of ANIMATIONS, or "" for ring.animation
    fan: bool = False         # opened as a submenu: fan out in place instead of a new ring


@dataclass
class Config:
    path: str
    mtime: float
    bridge_mode: str = "auto"
    bridge_key: Hotkey | None = field(default_factory=lambda: parse_hotkey(DEFAULT_BRIDGE_KEY))
    browser_key: Hotkey | None = None
    ring: dict = field(default_factory=lambda: json.loads(json.dumps(DEFAULT_RING)))
    menus: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


def parse_hotkey(text: str) -> Hotkey | None:
    """'Q', 'Alt+G', 'Ctrl+Shift+1', 'F9', '`'. Returns None if unparseable."""
    if not text or not isinstance(text, str):
        return None
    parts = [p.strip() for p in re.split(r"\+(?=.)", text.strip()) if p.strip()]
    mods = {"ctrl": False, "alt": False, "shift": False}
    for p in parts[:-1]:
        m = _MODS.get(p.lower())
        if m is None:
            return None
        mods[m] = True
    key = parts[-1].lower() if parts else ""
    if len(key) == 1 and ("a" <= key <= "z" or "0" <= key <= "9"):
        vk = ord(key.upper())
    elif re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", key):
        vk = 0x70 + int(key[1:]) - 1
    elif key in _NAMED_VK:
        vk = _NAMED_VK[key]
    else:
        return None
    return Hotkey(vk, mods["ctrl"], mods["alt"], mods["shift"], text.strip())


def asset_of(action):
    """(kind, name) of a brush, alpha, material or texture action; None for any other action."""
    for k in ASSET_KINDS:
        if k in action and isinstance(action[k], str):
            return k, action[k]
    return None


def _did_you_mean(key, known) -> str:
    near = difflib.get_close_matches(str(key), list(known), n=1)
    return f" (did you mean {near[0]}?)" if near else ""


def _check_action(a, errors, where, allow_nested=True) -> bool:
    if not isinstance(a, dict):
        errors.append(f"{where}: not an object")
        return False
    kinds = [k for k in ACTION_KEYS if k in a]
    if len(kinds) != 1:
        errors.append(f"{where}: needs exactly one of {', '.join(ACTION_KEYS)}")
        return False
    k = kinds[0]
    if k == "set" and "value" not in a:
        errors.append(f"{where}: 'set' needs a 'value'")
        return False
    if k == "set" and (isinstance(a["value"], bool) or not isinstance(a["value"], (int, float))):
        errors.append(f"{where}: 'set' value must be a number")
        return False
    if k == "steps":
        if not allow_nested or not isinstance(a["steps"], list) or not a["steps"]:
            errors.append(f"{where}: 'steps' must be a non-empty list of brush/alpha/material/texture/press/set/"
                          f"toggle actions")
            return False
        for i, s in enumerate(a["steps"]):
            if not _check_action(s, errors, f"{where} step {i + 1}", allow_nested=False):
                return False
            if any(x in s for x in ("menu", "steps", "auto", "tag", "browser")):
                errors.append(f"{where} step {i + 1}: steps cannot open menus, nest steps, be auto slots "
                              f"or open tags or the browser")
                return False
    elif k == "auto" and a["auto"] not in AUTO_KINDS:
        errors.append(f"{where}: 'auto' must be one of {', '.join(AUTO_KINDS)}")
        return False
    elif k == "browser":
        if not isinstance(a[k], str):
            errors.append(f"{where}: 'browser' must be a string (a tag key, or \"\" for everything)")
            return False
        if "kind" in a and a["kind"] not in ASSET_KINDS:
            errors.append(f"{where}: browser 'kind' must be one of {', '.join(ASSET_KINDS)}")
            return False
    elif not isinstance(a[k], str) or not a[k].strip():
        errors.append(f"{where}: '{k}' must be a non-empty string")
        return False
    return True


def _default_label(a: dict, menus_raw: dict, tags=None) -> str:
    got = asset_of(a)
    if got:
        return got[1]
    if "menu" in a:
        m = menus_raw.get(a["menu"], {})
        return (m.get("title") if isinstance(m, dict) else None) or a["menu"]
    if "steps" in a:
        return "Steps"
    if "auto" in a:
        return "Auto"
    if "tag" in a:
        return (tags.label(a["tag"]) if tags is not None and tags.has(a["tag"]) else "") or a["tag"]
    if "browser" in a:
        return (tags.label(a["browser"]) if tags is not None and tags.has(a["browser"]) else "") or "Browser"
    for k in ("press", "set", "toggle"):
        if k in a:
            return a[k].split(":")[-1]
    return "?"


def load(path: str, tags=None) -> Config:
    """tags: a tags.TagStore (anything with has(key) and label(key)); None skips the checks on tag names."""
    st = os.stat(path)
    with open(path, encoding="utf-8-sig") as f:         # -sig: an editor's byte-order mark is accepted
        raw = json.load(f)
    cfg = Config(path=path, mtime=st.st_mtime)
    errors = cfg.errors
    bridge = raw.get("bridge") or {}
    cfg.bridge_mode = bridge.get("mode", "auto")
    if cfg.bridge_mode not in ("auto", "message", "key"):
        errors.append(f"bridge.mode {cfg.bridge_mode!r} unknown; using auto")
        cfg.bridge_mode = "auto"
    if bridge.get("key"):
        key = parse_hotkey(bridge["key"])
        if key is None:
            errors.append(f"bridge.key {bridge['key']!r} not understood; using {DEFAULT_BRIDGE_KEY}")
        elif key.ctrl or key.shift:
            errors.append("bridge.key must not use Ctrl or Shift (ZBrush reads them as mask/smooth); "
                          f"use a bare F-key; using {DEFAULT_BRIDGE_KEY}")
        else:
            cfg.bridge_key = key
    ring = raw.get("ring") or {}
    for k, v in ring.items():
        if k == "colors" and isinstance(v, dict):
            for ck, cv in v.items():
                if ck in DEFAULT_RING["colors"]:
                    if isinstance(cv, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", cv):
                        cfg.ring["colors"][ck] = cv
                    else:
                        errors.append(f"ring.colors.{ck}: {cv!r} is not a #rrggbb colour")
        elif k in _RING_RANGES:
            lo, hi = _RING_RANGES[k]
            if isinstance(v, (int, float)) and lo <= v <= hi:
                cfg.ring[k] = v
            else:
                errors.append(f"ring.{k}: {v!r} must be a number from {lo} to {hi}")
        elif k in _RING_SWITCHES:
            if isinstance(v, bool):
                cfg.ring[k] = v
            else:
                errors.append(f"ring.{k}: {v!r} must be true or false")
        elif k == "animation":
            if v in ANIMATIONS:
                cfg.ring[k] = v
            else:
                errors.append(f"ring.animation: {v!r} unknown; one of {', '.join(ANIMATIONS)}")
        elif k == "labels":
            if v in LABEL_MODES:
                cfg.ring[k] = v
            else:
                errors.append(f"ring.labels: {v!r} unknown; one of {', '.join(LABEL_MODES)}")
        elif k in _RING_CHOICES:
            if v in _RING_CHOICES[k]:
                cfg.ring[k] = v
            else:
                errors.append(f"ring.{k}: {v!r} unknown; one of {', '.join(_RING_CHOICES[k])}")
        else:
            errors.append(f"ring.{k}: unknown setting" + _did_you_mean(k, DEFAULT_RING))
    menus_raw = raw.get("menus") or {}
    if not isinstance(menus_raw, dict) or not menus_raw:
        errors.append("menus: must be a non-empty object of id -> menu")
        menus_raw = {}
    built = {}                  # id -> (raw menu, [(item number, Item)]) of the menus with something in them
    for mid, m in menus_raw.items():
        if not isinstance(m, dict):
            errors.append(f"menu {mid}: not an object")
            continue
        if mid.startswith("tag:"):
            errors.append(f"menu {mid}: ids starting with 'tag:' are reserved for tag submenus")
            continue
        for k in m:
            if k not in MENU_KEYS:
                errors.append(f"menu {mid}: unknown setting {k!r}" + _did_you_mean(k, MENU_KEYS))
        items = []
        for i, it in enumerate(m.get("items") or []):
            where = f"menu {mid} item {i + 1}"
            if not _check_action(it, errors, where):
                continue
            kind = next(k for k in ACTION_KEYS if k in it)
            if kind == "menu" and it["menu"] not in menus_raw:
                errors.append(f"{where}: submenu {it['menu']!r} does not exist")
                continue
            if tags is not None and kind == "tag" and not tags.has(it["tag"]):
                errors.append(f"{where}: tag {it['tag']!r} does not exist; the slot stays empty")
            elif tags is not None and kind == "browser" and it["browser"] and not tags.has(it["browser"]):
                errors.append(f"{where}: tag {it['browser']!r} does not exist; the browser opens unfiltered")
            items.append((i + 1, Item(label=str(it.get("label") or _default_label(it, menus_raw, tags)), kind=kind,
                                      data={k: v for k, v in it.items() if k not in ("label", "icon")},
                                      icon=str(it.get("icon") or ""), tag=it["tag"] if kind == "tag" else "")))
        if not items:
            errors.append(f"menu {mid}: no usable items")
            continue
        built[mid] = (m, items)
    changed = True              # a submenu slot whose menu was dropped goes too, and may empty its own menu
    while changed:
        changed = False
        for mid in list(built):
            m, items = built[mid]
            keep = []
            for n, it in items:
                if it.kind == "menu" and it.data["menu"] not in built:
                    errors.append(f"menu {mid} item {n}: submenu {it.data['menu']!r} has no usable items")
                    changed = True
                else:
                    keep.append((n, it))
            if not keep:
                errors.append(f"menu {mid}: no usable items")
                del built[mid]
            else:
                built[mid] = (m, keep)
    used_keys = {}
    for mid, (m, items) in built.items():
        hk = None
        if m.get("hotkey"):
            hk = parse_hotkey(m["hotkey"])
            if hk is None:
                errors.append(f"menu {mid}: hotkey {m['hotkey']!r} not understood")
            elif (hk.vk, hk.ctrl, hk.alt, hk.shift) in used_keys:
                errors.append(f"menu {mid}: hotkey {m['hotkey']!r} already used by menu "
                              f"{used_keys[(hk.vk, hk.ctrl, hk.alt, hk.shift)]}")
                hk = None
            else:
                used_keys[(hk.vk, hk.ctrl, hk.alt, hk.shift)] = mid
        anim = m.get("animation") or ""
        if anim and anim not in ANIMATIONS:
            errors.append(f"menu {mid}: animation {anim!r} unknown; using ring.animation")
            anim = ""
        swallow = m.get("swallow", True)
        if not isinstance(swallow, bool):
            errors.append(f"menu {mid}: swallow {swallow!r} must be true or false; using true")
            swallow = True
        cfg.menus[mid] = Menu(id=mid, title=str(m.get("title") or mid), items=[it for _, it in items], hotkey=hk,
                              swallow=swallow, animation=anim, fan=bool(m.get("fan", False)))
    browser = raw.get("browser") or {}
    if isinstance(browser, dict) and browser.get("hotkey"):
        hk = parse_hotkey(browser["hotkey"])
        if hk is None:
            errors.append(f"browser.hotkey {browser['hotkey']!r} not understood")
        elif (hk.vk, hk.ctrl, hk.alt, hk.shift) in used_keys:
            errors.append(f"browser.hotkey {browser['hotkey']!r} already used by menu "
                          f"{used_keys[(hk.vk, hk.ctrl, hk.alt, hk.shift)]}")
        else:
            cfg.browser_key = hk
    elif browser and not isinstance(browser, dict):
        errors.append("browser: must be an object like {\"hotkey\": \"Alt+B\"}")
    if not any(m.hotkey for m in cfg.menus.values()):
        errors.append("no menu has a hotkey, so nothing can open the ring")
    return cfg
