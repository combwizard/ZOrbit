"""The theme: Dark, Light, Follow Windows or Match ZBrush, one setting for the PC.

It is kept as "theme" in studio.json (Studio's own file, per PC, never per profile) and applies to the ring, the
browser and Studio. Everything that draws asks here: the ring and the toast for their neutrals and colour defaults,
the two windows for their background and frame, Studio for the defaults it shows. A colour set under ring.colors in
radial.json still wins over the theme's default, because config.load applies the theme before the file's colours.

PRESETS holds the fixed palettes, so a new fixed preset is a new entry. "system" is not a preset: it picks dark or
light from Windows' app colour mode (effective()). "zbrush" is built from the colours ZBrush stored last
(zbrush_colors.py; _zbrush_preset() says what goes where), on top of the dark or light preset, whichever its
background is closer to; without a stored scheme it is dark. This module imports no other zorbit module but paths
and zbrush_colors, since config.py imports it.
"""
import colorsys
import copy
import json
import os

import zbrush_colors

try:
    import winreg
except ImportError:                       # not Windows: the app does not run there, but the tests may
    winreg = None

NAMES = ("dark", "light", "system", "zbrush")   # what studio.json may hold
CONCRETE = ("dark", "light")              # the fixed presets
EFFECTIVE = ("dark", "light", "zbrush")   # what effective() can give
DEFAULT = "dark"

# Contrast ratios (WCAG) are given against the surfaces they sit on, like the :root block of styles.css. The ring
# is drawn over ZBrush's canvas, not over its own background, so the label pill is checked over canvases from
# #3a3a3a (a dark ZBrush) to #b0b0b0 (a light one).
PRESETS = {
    "dark": {
        "label": "Dark",
        "base": "dark",
        "web": {},                            # the CSS of the dark :root block as it is
        "ring": {
            "colors": {"bg": "#222327", "accent": "#f86b33", "highlight": "#4dc8e9", "text": "#f0f0f0",
                       "lines": "#f86b33"},
            "pill": (0, 0, 0, 140),               # under each label
            "hint": (255, 255, 255, 140),         # the hint line under the title
            "badge": (0, 0, 0, 217),              # the submenu badge
            "placeholder": ((0x2a, 0x2a, 0x35), (0x5a, 0x5a, 0x6a)),   # disc gradient, rim then centre
        },
        "toast": {"pill": (24, 25, 29, 235), "text": "#f0f0f0"},        # 15.4:1
        "window": {"background": "#1a1b1e", "dwm_dark": 1, "border": "#2b2f35"},
    },
    "light": {
        "label": "Light",
        "base": "light",
        "web": {},                            # the CSS of the [data-theme="light"] block as it is
        "ring": {
            "colors": {"bg": "#f3f4f6",           # the disc
                       "accent": "#a8360f",       # Studio's light accent too. 6.0:1 on the disc; 4.8 to 5.8:1 on the pill over the canvases
                       "highlight": "#066785",    # 5.8:1 on the disc; 4.7 to 5.7:1 on the pill
                       "text": "#1b1c20",         # 15.5:1 on the disc; 12.4 to 15.1:1 on the pill
                       "lines": "#a8360f"},
            "pill": (255, 255, 255, 210),
            "hint": (27, 28, 32, 178),            # 6.0:1 on the disc
            "badge": (255, 255, 255, 230),
            "placeholder": ((0xda, 0xdd, 0xe3), (0xbc, 0xc1, 0xcb)),   # the glyph on it: 7.7:1
        },
        "toast": {"pill": (243, 244, 246, 235), "text": "#1b1c20"},     # 15.5:1
        "window": {"background": "#f3f4f6", "dwm_dark": 0, "border": "#c9cdd4"},
    },
}

_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
_cache = {}                               # path -> (bytes, setting): the file is small, and a stat can miss a quick rewrite


def effective(name) -> str:
    """The preset a setting comes to: dark, light or zbrush. "system" asks Windows; "zbrush" is dark until ZBrush
    has stored a scheme; anything unknown is dark."""
    if name in CONCRETE:
        return name
    if name == "system":
        return "light" if _apps_use_light() else "dark"
    if name == "zbrush":
        return "zbrush" if zbrush_colors.current() else "dark"
    return DEFAULT


def _apps_use_light() -> bool:
    """Windows' app colour mode. False only when the value is there and 0; a missing value means light, as it
    does for Windows itself. Without the registry (not Windows) the answer is dark."""
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY) as key:
            value, kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:                       # no key or value: Windows treats that as light
        return True
    return not (kind == winreg.REG_DWORD and value == 0)


def _default_path() -> str:
    import paths                          # at call time: the tests point CONFIG_DIR elsewhere
    return os.path.join(paths.CONFIG_DIR, "studio.json")


def read_setting(path=None) -> str:
    """What studio.json says: dark, light or system. Missing, unreadable or odd files say dark. The file is read
    each time (the app asks twice a second; it is a few hundred bytes) and parsed only when its bytes changed."""
    path = path or _default_path()
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        _cache.pop(path, None)
        return DEFAULT
    hit = _cache.get(path)
    if hit and hit[0] == raw:
        return hit[1]
    setting = DEFAULT
    try:
        data = json.loads(raw.decode("utf-8-sig"))
        if isinstance(data, dict) and data.get("theme") in NAMES:
            setting = data["theme"]
    except ValueError:
        pass
    _cache[path] = (raw, setting)
    return setting


def current(path=None) -> str:
    """The preset in force: the setting, with "system" and "zbrush" resolved."""
    return effective(read_setting(path))


def signature(path=None):
    """(the preset in force, the digest of the ZBrush scheme or ""). It changes when a new scheme is stored even
    though the name stays "zbrush", so the app and the browser compare this, not the name."""
    eff = current(path)
    scheme = zbrush_colors.current() if eff == "zbrush" else None
    return eff, scheme.digest if scheme else ""


def preset(name) -> dict:
    """The palette of a setting (resolved). Read it, do not change it. Every preset has "base" (dark or light, for
    the parts a ZBrush scheme does not give) and "web" (CSS custom properties over that base; empty for a fixed one)."""
    eff = effective(name)
    if eff == "zbrush":
        scheme = zbrush_colors.current()
        if scheme:
            return _zbrush_preset(scheme)
        eff = DEFAULT
    return PRESETS[eff]


def source():
    """Where Match ZBrush takes its colours: {"year", "path", "stored" (a POSIX time)}, or None."""
    s = zbrush_colors.current()
    return {"year": s.year, "path": s.path, "stored": s.mtime} if s else None


# --- Match ZBrush ------------------------------------------------------------------------------------------------
# What goes where. Each colour ZOrbit takes from the scheme is checked for contrast against what it sits on; a
# colour that fails is replaced by the base preset's, one by one, so a clashing scheme still gives a readable ring.
#   base           light when Main is light (luminance above 0.4), else dark: the label pill, hint, badge,
#                  placeholder and window frame mode, and every Studio colour the scheme does not give
#   ring  bg       Bt1, the button face           text      Text2, else Text1 (4.5:1 on bg)
#         accent   Sw1, the switch that is on     lines     the accent
#         highlight K1, unless it is the accent's hue (stock ZBrush makes both orange): then the base's
#   window         background Main, border Border2 (Palette1 when Border2 is Main)
#   toast          pill Main2, text the ring text (4.5:1 on the pill)
#   Studio         --bg0 Palette2  --bg1 Main  --bg2 Palette1  --bg3 Bt1  --text  --sub/--muted (text mixed towards
#                  --bg1)  --accent Sw1 (3:1 on --bg2)  --on-accent  --cyan the highlight
_zb_cache = {}


def _hex(rgb) -> str:
    return "#%02x%02x%02x" % tuple(rgb)


def _ratio(a, b) -> float:
    la, lb = _luminance(a), _luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _readable(candidates, on, need):
    """The first colour of candidates (None skipped) with at least need:1 against every colour in on."""
    for c in candidates:
        if c is not None and all(_ratio(c, o) >= need for o in on):
            return c
    return None


def _same_hue(a, b) -> bool:
    ha, sa, _ = colorsys.rgb_to_hsv(*(v / 255 for v in a))
    hb, sb, _ = colorsys.rgb_to_hsv(*(v / 255 for v in b))
    d = abs(ha - hb)
    return sa > 0.3 and sb > 0.3 and min(d, 1 - d) < 30 / 360


def _zbrush_preset(scheme) -> dict:
    hit = _zb_cache.get(scheme.digest)
    if hit:
        return hit
    g = scheme.get
    main = g("main")
    base = "light" if _luminance(main) > 0.4 else "dark"
    B = PRESETS[base]
    b_ring = {k: _rgb(v) for k, v in B["ring"]["colors"].items()}
    out = copy.deepcopy(B)
    out["label"] = f"ZBrush {scheme.year}"

    disc = g("bt1") or b_ring["bg"]
    text = _readable([g("text2"), g("text1")], [disc], 4.5) or b_ring["text"]
    accent = _readable([g("sw1")], [disc], 3) or b_ring["accent"]
    k1 = g("k1")
    highlight = (k1 if k1 and not _same_hue(k1, accent) and _ratio(k1, disc) >= 3 else None) or b_ring["highlight"]
    out["ring"]["colors"] = {"bg": _hex(disc), "accent": _hex(accent), "highlight": _hex(highlight),
                             "text": _hex(text), "lines": _hex(accent)}

    border = g("border2") if g("border2") and g("border2") != main else (g("palette1") or main)
    out["window"]["background"] = _hex(main)
    out["window"]["border"] = _hex(border)

    pill = g("main2") or main
    out["toast"] = {"pill": tuple(pill) + (235,),
                    "text": _hex(_readable([text], [pill], 4.5) or _rgb(B["toast"]["text"]))}

    p2 = g("palette2")                         # --bg0 is the deepest panel, darker than --bg1 in both bases
    bg0 = p2 if p2 and _luminance(p2) < _luminance(main) else _mix(main, (0, 0, 0), 0.3 if base == "dark" else 0.06)
    bg2 = g("palette1") or main
    web_text = _readable([text, g("text2"), g("text1")], [main, disc, bg2], 4.5) or _rgb(B["ring"]["colors"]["text"])
    sub = _readable([_mix(web_text, main, 0.4), _mix(web_text, main, 0.25)], [main, disc, bg2], 4.5) or web_text
    web_accent = _readable([g("sw1")], [main, bg2], 3) or b_ring["accent"]
    on_accent = max(((0x14, 0x14, 0x16), (255, 255, 255)), key=lambda c: _ratio(c, web_accent))
    out["base"] = base
    out["web"] = {"--bg0": _hex(bg0), "--bg1": _hex(main), "--bg2": _hex(bg2), "--bg3": _hex(disc),
                  "--text": _hex(web_text), "--sub": _hex(sub), "--muted": _hex(sub),
                  "--accent": _hex(web_accent), "--on-accent": _hex(on_accent), "--cyan": _hex(highlight)}
    _zb_cache.clear()                         # one scheme at a time
    _zb_cache[scheme.digest] = out
    return out


def ring_colors(name) -> dict:
    """A fresh copy of the five ring colours a setting gives by default."""
    return dict(preset(name)["ring"]["colors"])


def colorref(hex_colour: str) -> int:
    """'#rrggbb' as the COLORREF DwmSetWindowAttribute takes (0x00bbggrr)."""
    r, g, b = _rgb(hex_colour)
    return (b << 16) | (g << 8) | r


def _rgb(hex_colour: str):
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(rgb) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(hex_colour: str, rgba) -> float:
    """WCAG contrast between a text colour and an (r, g, b, a) fill, the fill taken as opaque."""
    la, lb = _luminance(_rgb(hex_colour)), _luminance(rgba[:3])
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)
