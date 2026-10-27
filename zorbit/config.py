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
           "flick": true,                    # moving out past a slot picks it without releasing the hotkey
           "hover_submenus": true,           # reaching a submenu slot opens that submenu, centred on it
           "colors": {"bg": "#222327", "accent": "#f86b33", "highlight": "#4dc8e9", "text": "#f0f0f0",
                      "lines": "#f86b33"}},
  "menus": {
    "<id>": {
      "title": "Brushes",
      "hotkey": "Q",                   # optional; menus without one are submenus only
      "swallow": true,                 # hide the hotkey from ZBrush (default true)
      "animation": "spiral",           # optional; this menu's open animation instead of ring.animation
      "items": [ <item>, ... ]         # drawn clockwise from the top
    }
  }
}

<item> is one action plus an optional "label" and "icon" (path to a .png/.zbp, or a brush name):
  {"brush": "ClayBuildup"}                       select a brush (loaded from its .zbp if needed)
  {"press": "Tool:Masking:Clear"}                press any ZBrush button by item path
  {"set": "Draw:Draw Size", "value": 64}         set a slider or value
  {"toggle": "Transform:Activate Symmetry"}      flip a switch
  {"steps": [<action>, ...]}                     run several actions in order
  {"menu": "<id>"}                               open another ring in place
  {"auto": "brush"}                              a slot the app fills with a brush you pick often (usage.py)
"""
import json
import os
import re
from dataclasses import dataclass, field

ACTION_KEYS = ("brush", "press", "set", "toggle", "steps", "menu", "auto")
AUTO_KINDS = ("brush",)
ANIMATIONS = ("smooth", "bounce", "pop", "zoom", "fade", "drift", "fancy", "spiral", "ripple", "breath", "mist",
              "snappy")
LABEL_MODES = ("name", "none")

DEFAULT_RING = {"radius": 145, "slot": 72, "dead_zone": 38, "tap_ms": 250, "timeout_s": 20,
                "animation": "smooth", "labels": "name", "flick": True, "hover_submenus": True,
                "colors": {"bg": "#222327", "accent": "#f86b33", "highlight": "#4dc8e9", "text": "#f0f0f0",
                           "lines": "#f86b33"}}
_RING_SWITCHES = ("flick", "hover_submenus")
_RING_RANGES = {"radius": (60, 400), "slot": (32, 160), "dead_zone": (10, 120), "tap_ms": (0, 1000),
                "timeout_s": (2, 120)}

_NAMED_VK = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "`": 0xC0, "~": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
    "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
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


@dataclass
class Menu:
    id: str
    title: str
    items: list
    hotkey: Hotkey | None = None
    swallow: bool = True
    animation: str = ""       # one of ANIMATIONS, or "" for ring.animation


@dataclass
class Config:
    path: str
    mtime: float
    bridge_mode: str = "auto"
    bridge_key: Hotkey | None = None
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
            errors.append(f"{where}: 'steps' must be a non-empty list of brush/press/set/toggle actions")
            return False
        for i, s in enumerate(a["steps"]):
            if not _check_action(s, errors, f"{where} step {i + 1}", allow_nested=False):
                return False
            if "menu" in s or "steps" in s or "auto" in s:
                errors.append(f"{where} step {i + 1}: steps cannot open menus, nest steps or be auto slots")
                return False
    elif k == "auto" and a["auto"] not in AUTO_KINDS:
        errors.append(f"{where}: 'auto' must be one of {', '.join(AUTO_KINDS)}")
        return False
    elif not isinstance(a[k], str) or not a[k].strip():
        errors.append(f"{where}: '{k}' must be a non-empty string")
        return False
    return True


def _default_label(a: dict, menus_raw: dict) -> str:
    if "brush" in a:
        return a["brush"]
    if "menu" in a:
        m = menus_raw.get(a["menu"], {})
        return (m.get("title") if isinstance(m, dict) else None) or a["menu"]
    if "steps" in a:
        return "Steps"
    if "auto" in a:
        return "Auto"
    for k in ("press", "set", "toggle"):
        if k in a:
            return a[k].split(":")[-1]
    return "?"


def load(path: str) -> Config:
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
        cfg.bridge_key = parse_hotkey(bridge["key"])
        if cfg.bridge_key is None:
            errors.append(f"bridge.key {bridge['key']!r} not understood")
        elif cfg.bridge_key.ctrl or cfg.bridge_key.shift:
            errors.append("bridge.key must not use Ctrl or Shift (ZBrush reads them as mask/smooth); "
                          "use a bare F-key")
            cfg.bridge_key = None
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
    menus_raw = raw.get("menus") or {}
    if not isinstance(menus_raw, dict) or not menus_raw:
        errors.append("menus: must be a non-empty object of id -> menu")
        menus_raw = {}
    used_keys = {}
    for mid, m in menus_raw.items():
        if not isinstance(m, dict):
            errors.append(f"menu {mid}: not an object")
            continue
        items = []
        for i, it in enumerate(m.get("items") or []):
            where = f"menu {mid} item {i + 1}"
            if not _check_action(it, errors, where):
                continue
            kind = next(k for k in ACTION_KEYS if k in it)
            if kind == "menu" and it["menu"] not in menus_raw:
                errors.append(f"{where}: submenu {it['menu']!r} does not exist")
                continue
            items.append(Item(label=str(it.get("label") or _default_label(it, menus_raw)), kind=kind,
                              data={k: v for k, v in it.items() if k not in ("label", "icon")},
                              icon=str(it.get("icon") or "")))
        if not items:
            errors.append(f"menu {mid}: no usable items")
            continue
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
        cfg.menus[mid] = Menu(id=mid, title=str(m.get("title") or mid), items=items, hotkey=hk,
                              swallow=bool(m.get("swallow", True)), animation=anim)
    if not any(m.hotkey for m in cfg.menus.values()):
        errors.append("no menu has a hotkey, so nothing can open the ring")
    return cfg
