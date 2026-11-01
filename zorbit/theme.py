"""The theme: Dark, Light or Follow Windows, one setting for the PC.

It is kept as "theme" in studio.json (Studio's own file, per PC, never per profile) and applies to the ring, the
browser and Studio. Everything that draws asks here: the ring and the toast for their neutrals and colour defaults,
the two windows for their background and frame, Studio for the defaults it shows. A colour set under ring.colors in
radial.json still wins over the theme's default, because config.load applies the theme before the file's colours.

PRESETS is the only place the palettes live, so a new preset is a new entry. "system" is not a preset: it picks
dark or light from Windows' app colour mode (effective()). This module imports no other zorbit module but paths,
since config.py imports it.
"""
import json
import os

try:
    import winreg
except ImportError:                       # not Windows: the app does not run there, but the tests may
    winreg = None

NAMES = ("dark", "light", "system")       # what studio.json may hold
CONCRETE = ("dark", "light")              # the presets
DEFAULT = "dark"

# Contrast ratios (WCAG) are given against the surfaces they sit on, like the :root block of styles.css. The ring
# is drawn over ZBrush's canvas, not over its own background, so the label pill is checked over canvases from
# #3a3a3a (a dark ZBrush) to #b0b0b0 (a light one).
PRESETS = {
    "dark": {
        "label": "Dark",
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
        "ring": {
            "colors": {"bg": "#f3f4f6",           # the disc
                       "accent": "#b93d12",       # 5.1:1 on the disc; 4.1 to 5.0:1 on the pill over the canvases
                       "highlight": "#076e8d",    # 5.3:1 on the disc; 4.2 to 5.1:1 on the pill
                       "text": "#1b1c20",         # 15.5:1 on the disc; 12.4 to 15.1:1 on the pill
                       "lines": "#b93d12"},
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
_cache = {}                               # path -> (mtime_ns, size, setting)


def effective(name) -> str:
    """The preset a setting comes to: dark or light. "system" asks Windows; anything unknown is dark."""
    if name in CONCRETE:
        return name
    if name == "system":
        return "light" if _apps_use_light() else "dark"
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
    """What studio.json says: dark, light or system. Missing, unreadable or odd files say dark. Re-read only when
    the file's time or size changed (the app asks twice a second)."""
    path = path or _default_path()
    try:
        st = os.stat(path)
    except OSError:
        _cache.pop(path, None)
        return DEFAULT
    hit = _cache.get(path)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    setting = DEFAULT
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("theme") in NAMES:
            setting = data["theme"]
    except (OSError, ValueError):
        pass
    _cache[path] = (st.st_mtime_ns, st.st_size, setting)
    return setting


def current(path=None) -> str:
    """The preset in force: the setting, with "system" resolved."""
    return effective(read_setting(path))


def preset(name) -> dict:
    """The palette of a setting (resolved). Read it, do not change it."""
    return PRESETS[effective(name)]


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
