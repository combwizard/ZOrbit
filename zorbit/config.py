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
  "ring": {"radius": 145, "slot": 72, "dead_zone": 38, "hub": 10, "tap_ms": 250, "timeout_s": 20,
           # hub: diameter in px of the hub in the middle, 0 to 64 (0 = no hub); dead_zone is separate
           # hub_style (dot disc ring icon), hub_color, hub_glow, slot_corner, border_width, icon_scale,
           # glow_color, glow_opacity, label_color, when_full (grow rings more): see looks.py
           "look": "soft",                   # a built-in look or one of "looks" below; the keys here win over it
           "animation": "smooth",            # smooth bounce pop zoom fade drift fancy spiral ripple breath
                                             # mist snappy
           "labels": "name",                 # name | none
           "slot_shape": "circle",           # circle rounded squircle hexagon octagon diamond
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
           "hint": true,                     # the line of help under the menu's title; false leaves it out
           "tag_limit": 12,                  # slots in a tag fan, 4 to 24; a tag with more items ends in More...
           "colors": {"bg": "#222327", "accent": "#f86b33", "highlight": "#4dc8e9", "text": "#f0f0f0",
                      "lines": "#f86b33"}},
  "looks": {"My look": {"slot_shape": "hexagon", "hub": 14}},    # named looks: any of the look keys of "ring"
  "browser": {"hotkey": "Alt+B",          # opens the browser popout (tabs per kind, tags, search, folders)
              "quit_after_minutes": 30},  # optional; 0 or absent: off. Minutes (1-1440) a hidden browser waits, then quits
  "profile": {"next_hotkey": "Alt+P"},    # optional, no default: steps to the next profile (needs ZBrush in front)
  "menus": {
    "<id>": {
      "title": "Brushes",
      "hotkey": "Q",                   # optional; menus without one are submenus only
      "swallow": true,                 # hide the hotkey from ZBrush (default true)
      "animation": "spiral",           # optional; this menu's open animation instead of ring.animation
      "fan": true,                     # optional; opened as a submenu, its items fan out from that slot
                                       # and the ring stays (default false: a new ring centred on the slot)
      "look": "soft",                  # optional; a look name, or {"preset": "soft", "hub": 14, ...} (look keys)
      "icon": "ClayBuildup",           # optional; the icon of a hub_style "icon" hub (a brush name or a full path)
      "keep_slots": true,              # optional; Studio only: editing never moves the other items (empty slots stay)
      "items": [ <item>, ... ]         # drawn clockwise from the top
    }
  }
}

<item> is one action plus an optional "label", "icon" (full path to a .png/.zbp, or a brush name) and "style"
(an object of the style keys in looks.py, such as {"glow_color": "#ff8800", "slot_shape": "hexagon"}):
  {"brush": "ClayBuildup"}                       select a brush (loaded from its .zbp if needed)
  {"alpha": "Alpha 58"}                          select an alpha (imported from its file if needed)
  {"material": "SkinShade4"}                     select a material (Material:Load replaces the selected slot)
  {"texture": "Txtr01"}                          select a texture (imported from its file if needed)
  {"press": "Tool:Masking:Clear"}                press any ZBrush button by item path
  {"set": "Draw:Draw Size", "value": 64}         set a slider or value
  {"toggle": "Transform:Activate Symmetry"}      flip a switch
  {"capture": "D:/Pictures/ZBrush"}              save the document as a time-stamped PNG in that folder ("" = ZBrush in Windows'
                                                 Pictures folder; capture.py)
  {"tool": "D:/Models/Hero.ztl"}                 load that tool (Tool:Load Tool); fileitem.py
  {"project": "D:/Projects/Hero.zpr"}            open that project (File:Open); a folder instead of a file means the
                                                 newest .zpr in it, worked out at each pick
  {"layout": "D:/Layouts/Sculpt.cfg"}            load that ZBrush UI layout (Preferences:Config:Load Ui); fileitem.py
  {"steps": [<action>, ...]}                     run several actions in order
  {"menu": "<id>"}                               open another ring in place
  {"auto": "brush"}                              a slot the app fills with a brush you pick often (usage.py)
  {"tag": "blocking"}                            a submenu of every brush carrying that tag (tags.py), most used first
                                                 (Favourites can follow your own order, see expand.py)
  {"browser": "", "kind": "alpha"}               open the browser (tabs: brush alpha material texture) on that
                                                 tab (default brush); a tag key filters it ("" = everything)
  {"recent": "project"}                          a fan of ZBrush's recent projects ("tool": tools, "any": both), each a
                                                 Project or Tool item (recent.py, expand.py)
  {"empty": true}                                a slot that holds nothing: drawn as a faint outline, never picked

An item that cannot be used (no target yet, a submenu that is gone) is reported and drawn as an empty slot, so the slots
after it stay where they are. A menu with nothing but such items is dropped.

Menu ids starting with "tag:" are reserved for the submenus a tag slot opens, ids starting with "recent:" for the fan
of a recent slot, and ids starting with "more:" for the More submenu of a full ring.
Ids that are names a JavaScript object already has (__proto__, constructor, toString and the like) are reserved too.
"""
import json
import os
import re
from dataclasses import dataclass, field, replace

import looks as L
import theme as T

ACTION_KEYS = ("brush", "alpha", "material", "texture", "press", "set", "toggle", "capture", "tool", "project", "layout",
               "steps", "menu", "auto", "tag", "browser", "recent", "empty")
FILE_EXTS = {"tool": ".ztl", "project": ".zpr", "layout": ".cfg"}     # what a Tool, a Project and a Layout item must end with (a project may be a folder)
_FILE_EXAMPLES = {"tool": "C:\\Models\\Hero.ztl", "project": "C:\\Projects\\Hero.zpr", "layout": "C:\\Layouts\\Sculpt.cfg"}
ASSET_KINDS = ("brush", "alpha", "material", "texture")     # the kinds of the browser and of tags
AUTO_KINDS = ("brush",)
RECENT_KINDS = ("project", "tool", "any")                   # what a recent slot lists: projects, tools, or both
RECENT_LABELS = {"project": "Recent projects", "tool": "Recent tools", "any": "Recent"}   # its label when it has none
NO_STEP = ("menu", "steps", "auto", "tag", "browser", "recent", "empty")   # the kinds a step of steps cannot be
ANIMATIONS = L.ANIMATIONS
LABEL_MODES = L.LABEL_MODES
TAG_COLOR_MODES = L.TAG_COLOR_MODES
TAG_BANDS = L.TAG_BANDS
TINT_STYLES = L.TINT_STYLES
TINT_BLENDS = L.TINT_BLENDS
SLOT_SHAPES = L.SLOT_SHAPES
HUB_STYLES = L.HUB_STYLES
WHEN_FULL = L.WHEN_FULL
RESERVED_MENU_IDS = L.RESERVED_MENU_IDS         # the names a JavaScript object already has (see looks.py)

# every ring key at its default; the colours are the Dark theme's and the colour keys hold roles (see looks.py).
# default_ring() gives another theme's colours. What the ring draws is Config.ring, with the roles resolved.
DEFAULT_RING = {**L.BEHAVIOUR_DEFAULTS, **L.LOOK_DEFAULTS, "colors": T.ring_colors("dark")}
_RING_SWITCHES = L.SWITCHES
_RING_CHOICES = L.CHOICES
_RING_RANGES = L.RANGES
_did_you_mean = L.did_you_mean

_NAMED_VK = {
    "space": 0x20, "tab": 0x09, "enter": 0x0D, "backspace": 0x08, "insert": 0x2D, "delete": 0x2E,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "`": 0xC0, "~": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD, "\\": 0xDC, ";": 0xBA,
    "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
MENU_KEYS = ("title", "hotkey", "swallow", "animation", "fan", "look", "icon", "keep_slots", "items")
BRIDGE_KEYS = ("mode", "key")
BROWSER_KEYS = ("hotkey", "quit_after_minutes")
BROWSER_QUIT_MAX = 1440            # minutes: a day
PROFILE_KEYS = ("next_hotkey",)
ITEM_KEYS = ACTION_KEYS + ("label", "icon", "style", "value", "kind")
DEFAULT_BRIDGE_KEY = "F9"          # used when radial.json has no usable bridge.key
VK_F10 = 0x79                       # Windows' menu-bar key: never usable as the bridge key
_MODS = {"ctrl": "ctrl", "control": "ctrl", "alt": "alt", "shift": "shift"}
PATH_FIXES = {"transform:polyf": "Transform:Pf"}     # a path that was wrong (the shelf says PolyF): old menus still work


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
    glow: str = ""            # #rrggbb of style.glow_color, resolved by load(): kept until the ring reads style
    style: dict = field(default_factory=dict)   # the valid keys of the item's "style", roles still roles


@dataclass
class Menu:
    id: str
    title: str
    items: list
    hotkey: Hotkey | None = None
    swallow: bool = True
    animation: str = ""       # one of ANIMATIONS, or "" for ring.animation
    fan: bool = False         # opened as a submenu: fan out in place instead of a new ring
    look: dict | None = None  # the complete look this menu is drawn with (roles resolved); None: use Config.ring
    look_spec: dict = field(default_factory=dict)   # {"preset": name or "", **the menu's own look keys}
    icon: str = ""            # the icon of a hub_style "icon" hub
    # Set by expand.Expander on the menu it hands the ring (auto slots filled, tag colours stamped), so that handing it
    # back in leaves it as it is: filling it twice would read the filled auto slots as brushes the menu pins.
    filled: bool = field(default=False, compare=False, repr=False)


@dataclass
class Config:
    path: str
    mtime: float
    bridge_mode: str = "auto"
    bridge_key: Hotkey = field(default_factory=lambda: parse_hotkey(DEFAULT_BRIDGE_KEY))
    browser_key: Hotkey | None = None
    browser_quit_minutes: int = 0      # a hidden browser quits after this long unused; 0 = never
    profile_key: Hotkey | None = None
    ring: dict = field(default_factory=lambda: L.LookSet().global_look())    # the resolved global look
    looks: L.LookSet = field(default_factory=L.LookSet)
    menus: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


def idle_quit_minutes(browser) -> int:
    """browser.quit_after_minutes of a radial.json "browser" section (a dict, else anything): a whole number from 1 to
    1440 minutes, else 0 (never). The app and the browser process both read the setting through this."""
    v = browser.get("quit_after_minutes") if isinstance(browser, dict) else None
    return v if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= BROWSER_QUIT_MAX else 0


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


def retag(cfg: dict, renamed: dict) -> int:
    """Points the {"tag": key} and {"browser": key} slots of every menu in a raw config dict at the key
    renamed gives ({old key: new key}). Changes cfg in place and returns how many items changed."""
    n = 0
    if renamed:
        for m in (cfg.get("menus") or {}).values():
            for it in (m.get("items") or []) if isinstance(m, dict) else ():
                if isinstance(it, dict):
                    hit = False
                    for k in ("tag", "browser"):
                        if isinstance(it.get(k), str) and it[k] in renamed:
                            it[k] = renamed[it[k]]
                            hit = True
                    n += hit
    return n


def relook(menus: dict, renamed: dict) -> int:
    """Points the "look" of every menu in a raw menus dict (a name, or the "preset" of an object) at the name
    renamed gives ({old name: new name}). Changes menus in place and returns how many menus changed."""
    n = 0
    for m in (menus or {}).values() if renamed else ():
        if not isinstance(m, dict):
            continue
        v = m.get("look")
        if isinstance(v, str) and v in renamed:
            m["look"] = renamed[v]
            n += 1
        elif isinstance(v, dict) and isinstance(v.get("preset"), str) and v["preset"] in renamed:
            v["preset"] = renamed[v["preset"]]
            n += 1
    return n


def _bad_asset_name(name) -> bool:
    """A brush, alpha, material or texture name is a plain name, never a path (it is looked up by file name)."""
    return isinstance(name, str) and (any(c in name for c in "\\/:") or ".." in name)


def _check_icon(icon, where, errors) -> str:
    """The icon value of an item or a menu; a problem with it is reported under where."""
    icon = str(icon or "")
    if _network_path(icon):
        errors.append(f"{where}: icon '{icon}' must be a plain file path on this PC, not a network path")
        return ""
    if icon:
        icon_problem = _icon_problem(icon)
        if icon_problem:
            errors.append(f"{where}: {icon_problem}")      # the item and its icon value stay: only a warning
    return icon


def _check_menu_look(raw, mid, looks, errors) -> dict:
    """A menu's "look" (a name, or an object with a "preset" and look keys) as {"preset": name or "", **valid
    keys}. A name that is no look is reported and the menu follows the ring's look."""
    spec = {"preset": ""}
    if raw is None:
        return spec
    if isinstance(raw, str):
        raw = {"preset": raw}
    elif not isinstance(raw, dict):
        errors.append(f'menu {mid}: look must be a look name or an object like {{"preset": "soft", "hub": 14}}; '
                      f'ignored')
        return spec
    name = raw.get("preset") or ""
    if name:
        if isinstance(name, str) and looks.preset(name) is not None:
            spec["preset"] = name
        else:
            errors.append(f"menu {mid}: look {name!r} unknown; using the ring's look")
    spec.update(L.check_look({k: v for k, v in raw.items() if k != "preset"}, errors, f"menu {mid}: look.",
                             L.LOOK_KEYS))
    return spec


def _network_path(path) -> bool:
    return isinstance(path, str) and path.strip().startswith(("\\\\", "//"))


ICON_EXTS = (".png", ".zbp", ".zmt", ".exr", ".psd", ".bmp", ".jpg", ".jpeg", ".tif", ".tiff")     # files an icon can be


def _icon_problem(icon: str) -> str:
    """What is wrong with an icon, or "". An icon is a brush name or a full path. A text with a \\ or / in it, or
    that ends in a file extension the app reads, is meant as a path: a relative one is looked up from wherever the
    app runs, so it is refused, and a full path to a file that is not there is only noticed."""
    text = icon.strip()
    if not (any(c in text for c in "\\/") or os.path.splitext(text)[1].lower() in ICON_EXTS):
        return ""                                       # a brush name
    if not (os.path.splitdrive(text)[0] and os.path.isabs(text)):
        return f"icon '{icon}' must be a full path, such as C:\\Art\\clay.png"
    if not os.path.isfile(text):
        return f"icon file not found: {icon}"
    return ""


def _capture_problem(folder: str) -> str:
    """What is wrong with the folder of a capture item, or "". It is a full path on this PC, made when it is missing,
    so a relative path (looked up from wherever the app runs), a network share and a picture file are refused."""
    text = folder.strip()
    if not text:
        return ""                                       # the default folder (capture.default_folder)
    if _network_path(text):
        return "must be a folder on this PC, not a network path"
    if not (os.path.splitdrive(text)[0] and os.path.isabs(text)):
        return f"'{folder}' must be a full path, such as C:\\Pictures\\ZBrush"
    if os.path.splitext(text.rstrip("\\/"))[1].lower() in ICON_EXTS or os.path.isfile(text):
        return f"'{folder}' must be a folder, not a file"
    return ""


def project_is_folder(path: str) -> bool:
    """Whether the path of a Project item names a folder: any value that does not end in .zpr (any case), whether the
    folder is there or not (a folder on a drive that is not plugged in, or one with a dot in its name)."""
    return not path.strip().lower().endswith(FILE_EXTS["project"])


def _file_problem(kind: str, path: str) -> str:
    """What is wrong with the path of a tool, project or layout item, or "". A full path on this PC: a tool must end
    .ztl and a layout .cfg; a project is a .zpr file or a folder, so an existing file that is not .zpr, or anything
    ending .ztl, is refused. The file need not be there: a drive may be unplugged."""
    text = path.strip()
    ext = FILE_EXTS[kind]
    if _network_path(text):
        return "must be on this PC, not a network path"
    if not (os.path.splitdrive(text)[0] and os.path.isabs(text)):
        return f"'{path}' must be a full path, such as {_FILE_EXAMPLES[kind]}"
    if kind == "project":
        if text.lower().endswith(".ztl") or (not text.lower().endswith(ext) and os.path.isfile(text)):
            return f"'{path}' must be a .zpr file or a folder"
        return ""
    if text.lower().endswith(ext):
        return ""
    return f"'{path}' must be a {ext} file"


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
                          f"toggle/capture/tool/project/layout actions")
            return False
        for i, s in enumerate(a["steps"]):
            if not _check_action(s, errors, f"{where} step {i + 1}", allow_nested=False):
                return False
            if any(x in s for x in NO_STEP):
                errors.append(f"{where} step {i + 1}: steps cannot open menus, nest steps, be auto slots, "
                              f"be empty slots or open tags, the browser or recent files")
                return False
    elif k == "auto" and a["auto"] not in AUTO_KINDS:
        errors.append(f"{where}: 'auto' must be one of {', '.join(AUTO_KINDS)}")
        return False
    elif k == "recent" and (not isinstance(a[k], str) or a[k] not in RECENT_KINDS):
        errors.append(f"{where}: 'recent' must be project, tool or any")
        return False
    elif k == "empty":
        if a[k] is not True:
            errors.append(f"{where}: 'empty' must be true")
            return False
    elif k == "browser":
        if not isinstance(a[k], str):
            errors.append(f"{where}: 'browser' must be a string (a tag key, or \"\" for everything)")
            return False
        if "kind" in a and a["kind"] not in ASSET_KINDS:
            errors.append(f"{where}: browser 'kind' must be one of {', '.join(ASSET_KINDS)}")
            return False
    elif k == "capture" and not isinstance(a[k], str):
        errors.append(f"{where}: 'capture' must be a folder path, or \"\" for the default folder")
        return False
    elif k != "capture" and (not isinstance(a[k], str) or not a[k].strip()):
        errors.append(f"{where}: '{k}' must be a non-empty string")
        return False
    elif k == "capture" and _capture_problem(a[k]):
        errors.append(f"{where}: capture folder {_capture_problem(a[k])}")
        return False
    elif k in FILE_EXTS and (why := _file_problem(k, a[k])):
        errors.append(f"{where}: {k} {why}")
        return False
    elif k in ASSET_KINDS and _bad_asset_name(a[k]):
        errors.append(f"{where}: {k} name '{a[k]}' must not contain \\ / : or ..")
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
    if "recent" in a:
        return RECENT_LABELS.get(a["recent"], "Recent")
    if "tag" in a:
        return (tags.label(a["tag"]) if tags is not None and tags.has(a["tag"]) else "") or a["tag"]
    if "browser" in a:
        return (tags.label(a["browser"]) if tags is not None and tags.has(a["browser"]) else "") or "Browser"
    if "empty" in a:
        return ""
    for k in ("press", "set", "toggle"):
        if k in a:
            return a[k].split(":")[-1]
    if "capture" in a:
        return "Capture"
    for k in FILE_EXTS:
        if k in a:
            name = os.path.basename(a[k].strip().rstrip("\\/"))
            return name if k == "project" and project_is_folder(a[k]) else os.path.splitext(name)[0]
    return "?"


def _held_slot(it, errors, where) -> Item:
    """The empty slot an item that cannot be used becomes. It keeps the item's style, so Look still shows it."""
    style = L.check_style(it["style"], errors, where) if isinstance(it, dict) and "style" in it else {}
    return Item(label="", kind="empty", data={"empty": True}, style=style)


def default_ring(theme: str = "dark") -> dict:
    """DEFAULT_RING with the colours a theme gives by default (no "theme" key)."""
    out = json.loads(json.dumps(DEFAULT_RING))
    out["colors"] = T.ring_colors(theme)
    return out


def _fix_paths(action: dict) -> dict:
    """The action with any path in PATH_FIXES replaced, steps included. A new dict: the raw action is not changed."""
    out = dict(action)
    for k in ("press", "set", "toggle"):
        if isinstance(out.get(k), str):
            out[k] = PATH_FIXES.get(out[k].lower(), out[k])
    if isinstance(out.get("steps"), list):
        out["steps"] = [_fix_paths(s) if isinstance(s, dict) else s for s in out["steps"]]
    return out


def load(path: str, tags=None, theme: str = "dark") -> Config:
    """tags: a tags.TagStore (anything with has(key) and label(key)); None skips the checks on tag names.
    theme: the preset in force (theme.current()): its colours are the defaults the file's ring.colors fill in,
    and cfg.ring carries it as "theme" when it is not dark, for the ring's neutrals (pill, hint, badge). It is
    per PC, so a "theme" key in the file itself is an unknown setting."""
    st = os.stat(path)
    with open(path, encoding="utf-8-sig") as f:         # -sig: an editor's byte-order mark is accepted
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError("radial.json must be a JSON object")
    cfg = Config(path=path, mtime=st.st_mtime)
    theme = T.effective(theme)
    errors = cfg.errors
    bridge = raw.get("bridge")
    if bridge is None:
        bridge = {}
    elif not isinstance(bridge, dict):
        errors.append('bridge: must be an object like {"mode": "auto", "key": "F9"}')
        bridge = {}
    for k in bridge:
        if k not in BRIDGE_KEYS:
            errors.append(f"bridge.{k}: unknown setting" + _did_you_mean(k, BRIDGE_KEYS))
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
        elif key.alt or key.vk == VK_F10:
            # Both arrive as Windows system keys, and ZBrush (checked in 2022 and 2025) runs no hotkey for them when
            # ZOrbit sends them, so every pick through the bridge key would be lost.
            errors.append(f"bridge.key {bridge['key']!r} does not reach ZBrush: it does not act on Alt combinations "
                          f"or F10 sent by ZOrbit; use a bare F-key such as F9 or F11; using {DEFAULT_BRIDGE_KEY}")
        else:
            cfg.bridge_key = key
    ring = raw.get("ring")
    if ring is None:
        ring = {}
    elif not isinstance(ring, dict):
        errors.append('ring: must be an object like {"radius": 145, "animation": "smooth"}')
        ring = {}
    presets = L.check_presets(raw.get("looks"), errors)     # first: the ring and the menus name them
    ring_vals = L.check_look(ring, errors, "ring.", L.RING_KEYS)
    if ring.get("look"):
        if isinstance(ring["look"], str) and (ring["look"] in presets or ring["look"] in L.BUILTIN):
            ring_vals["look"] = ring["look"]
        else:
            names = list(L.BUILTIN) + list(presets)
            errors.append(f"ring.look: {ring['look']!r} unknown; one of {', '.join(names)}")
    cfg.looks = L.LookSet(presets, ring_vals, theme)
    cfg.ring = cfg.looks.global_look()
    menus_raw = raw.get("menus") or {}
    if not isinstance(menus_raw, dict) or not menus_raw:
        errors.append("menus: must be a non-empty object of id -> menu")
        menus_raw = {}
    tag_error = str(getattr(tags, "error", "") or "")    # tags.json could not be read: said once, not per slot
    tag_error_said = False
    built = {}                  # id -> (raw menu, [(item number, Item)]) of the menus with something in them
    for mid, m in menus_raw.items():
        if not isinstance(m, dict):
            errors.append(f"menu {mid}: not an object")
            continue
        if mid.startswith("tag:"):
            errors.append(f"menu {mid}: ids starting with 'tag:' are reserved for tag submenus")
            continue
        if mid.startswith("more:"):
            errors.append(f"menu {mid}: ids starting with 'more:' are reserved for the More submenu")
            continue
        if mid.startswith("recent:"):
            errors.append(f"menu {mid}: ids starting with 'recent:' are reserved for the fans of recent slots")
            continue
        if mid in RESERVED_MENU_IDS:
            errors.append(f"menu {mid}: that id is reserved, give the menu another")
            continue
        for k in m:
            if k not in MENU_KEYS:
                errors.append(f"menu {mid}: unknown setting {k!r}" + _did_you_mean(k, MENU_KEYS))
        items = []              # (item number, Item); the number is None for a slot held for an unusable item
        for i, it in enumerate(m.get("items") or []):
            where = f"menu {mid} item {i + 1}"
            if not _check_action(it, errors, where):
                items.append((None, _held_slot(it, errors, where)))
                continue
            kind = next(k for k in ACTION_KEYS if k in it)
            if kind == "menu" and it["menu"] not in menus_raw:
                errors.append(f"{where}: submenu {it['menu']!r} does not exist")
                items.append((None, _held_slot(it, errors, where)))
                continue
            for k in it:
                if k == "glow":
                    errors.append(f"{where}: unknown setting 'glow' (glow is now style.glow_color)")
                elif k not in ITEM_KEYS:
                    errors.append(f"{where}: unknown setting {k!r}" + _did_you_mean(k, ITEM_KEYS))
            if tags is not None and kind == "tag" and not tags.has(it["tag"]):
                if tag_error:
                    if not tag_error_said:
                        errors.append(f"tags.json could not be read: {tag_error}; tag slots stay empty until it "
                                      f"is fixed")
                        tag_error_said = True
                else:
                    errors.append(f"{where}: tag {it['tag']!r} does not exist; the slot stays empty")
            elif tags is not None and kind == "browser" and it["browser"] and not tags.has(it["browser"]):
                if not tag_error:
                    errors.append(f"{where}: tag {it['browser']!r} does not exist; the browser opens unfiltered")
            icon = _check_icon(it.get("icon"), where, errors)
            style = L.check_style(it["style"], errors, where) if "style" in it else {}
            items.append((i + 1, Item(label=str(it.get("label") or _default_label(it, menus_raw, tags)), kind=kind,
                                      data=_fix_paths({k: v for k, v in it.items()
                                                       if k not in ("label", "icon", "style", "glow")}),
                                      icon=icon, tag=it["tag"] if kind == "tag" else "", style=style)))
        if all(n is None for n, _ in items):
            errors.append(f"menu {mid}: no usable items")
            continue
        built[mid] = (m, items)
    changed = True              # a submenu slot whose menu was dropped is held too, and may leave its own menu with nothing
    while changed:
        changed = False
        for mid in list(built):
            m, items = built[mid]
            for pos, (n, it) in enumerate(items):
                if it.kind == "menu" and it.data["menu"] not in built:
                    errors.append(f"menu {mid} item {n}: submenu {it.data['menu']!r} has no usable items")
                    changed = True
                    items[pos] = (None, replace(it, label="", kind="empty", data={"empty": True}, icon=""))
            if all(n is None for n, _ in items):
                errors.append(f"menu {mid}: no usable items")
                del built[mid]
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
        fan = m.get("fan", False)
        if not isinstance(fan, bool):
            errors.append(f"menu {mid}: fan {fan!r} must be true or false; using false")
            fan = False
        if not isinstance(m.get("keep_slots", False), bool):    # Studio's switch; the ring never reads it
            errors.append(f"menu {mid}: keep_slots {m['keep_slots']!r} must be true or false; using false")
        spec = _check_menu_look(m.get("look"), mid, cfg.looks, errors)
        look = cfg.looks.menu_look(spec)
        built_items = [it for _, it in items]
        for it in built_items:          # the shim: the renderer reads the glow colour here until it reads style
            it.glow = L.colour(it.style.get("glow_color", ""), look["colors"])
        cfg.menus[mid] = Menu(id=mid, title=str(m.get("title") or mid), items=built_items, hotkey=hk,
                              swallow=swallow, animation=anim, fan=fan, look=look, look_spec=spec,
                              icon=_check_icon(m.get("icon"), f"menu {mid}", errors))
    browser = raw.get("browser")
    if browser is None:
        browser = {}
    elif not isinstance(browser, dict):
        errors.append('browser: must be an object like {"hotkey": "Alt+B"}')
        browser = {}
    for k in browser:
        if k not in BROWSER_KEYS:
            errors.append(f"browser.{k}: unknown setting" + _did_you_mean(k, BROWSER_KEYS))
    if browser.get("hotkey"):
        hk = parse_hotkey(browser["hotkey"])
        if hk is None:
            errors.append(f"browser.hotkey {browser['hotkey']!r} not understood")
        elif (hk.vk, hk.ctrl, hk.alt, hk.shift) in used_keys:
            errors.append(f"browser.hotkey {browser['hotkey']!r} already used by menu "
                          f"{used_keys[(hk.vk, hk.ctrl, hk.alt, hk.shift)]}")
        else:
            cfg.browser_key = hk
    if "quit_after_minutes" in browser:
        q = browser["quit_after_minutes"]
        cfg.browser_quit_minutes = idle_quit_minutes(browser)
        if cfg.browser_quit_minutes == 0 and not (type(q) is int and q == 0):
            errors.append(f"browser.quit_after_minutes {q!r} must be a whole number of minutes from 1 to "
                          f"{BROWSER_QUIT_MAX}, or 0 for never; using 0")
    profile = raw.get("profile")
    if profile is None:
        profile = {}
    elif not isinstance(profile, dict):
        errors.append('profile: must be an object like {"next_hotkey": "Alt+P"}')
        profile = {}
    for k in profile:
        if k not in PROFILE_KEYS:
            errors.append(f"profile.{k}: unknown setting" + _did_you_mean(k, PROFILE_KEYS))
    if profile.get("next_hotkey"):
        hk = parse_hotkey(profile["next_hotkey"])
        if hk is None:
            errors.append(f"profile.next_hotkey {profile['next_hotkey']!r} not understood")
        elif (hk.vk, hk.ctrl, hk.alt, hk.shift) in used_keys:
            errors.append(f"profile.next_hotkey {profile['next_hotkey']!r} already used by menu "
                          f"{used_keys[(hk.vk, hk.ctrl, hk.alt, hk.shift)]}")
        elif cfg.browser_key and (hk.vk, hk.ctrl, hk.alt, hk.shift) == (
                cfg.browser_key.vk, cfg.browser_key.ctrl, cfg.browser_key.alt, cfg.browser_key.shift):
            errors.append(f"profile.next_hotkey {profile['next_hotkey']!r} already used by browser.hotkey")
        else:
            cfg.profile_key = hk
    if not any(m.hotkey for m in cfg.menus.values()):
        errors.append("no menu has a hotkey, so nothing can open the ring")
    return cfg
