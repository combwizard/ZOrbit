"""The radial overlay: round icon slots on a ring, animated, in a non-activating layered window.

Look: slots of round icons around a glowing accent centre dot,
hairline spokes and faint guide rings; hover = accent border, soft ring, glow, 1.12x scale and accent label;
submenus use the highlight colour and a small badge (an arrow, or a fan for one that fans out); an auto slot nothing has filled yet is a faint "+".
Tag colours: an item that carries a colour (config.Item.color, from its first tag) gets a rim and its icon
tinted (ring.tag_tint_*), a soft halo (ring.tag_glow_opacity), or both, as ring.tag_colors says; its hover
border, spoke and label take the colour too. A band through the slot centres (ring.tag_band) shows each slot's
colour, faint for one without; it is left out when no slot has a colour. A tag slot is a solid disc in the tag colour with a tag glyph whatever ring.tag_colors says; one with no
brushes is a faint tag glyph and nothing else of it is coloured.
Looks: what is drawn comes from a _Look (the ring's settings with the menu's look over them), what is picked and
how the ring behaves from ring_cfg. A slot can take a shape (shapes.py), a style of its own (item.style) and a
glow colour; a fan with a look of its own is drawn in it; the hub is a dot, disc, ring or the menu's icon.
All of it is drawn into the sprites when they are built, so a frame costs the same as before.
Every disc is drawn before any label, and a label sits on a soft pill in the theme's colour, so a neighbouring disc never hides a name. The radius is
a minimum: a ring with many items grows until neighbouring slots are SLOT_GAP slot widths apart.
Sprites are kept between opens (_sprite_cache), so a menu opened again starts at once.
Selection is by angle outside a dead zone; a slot covers at most a quarter of the circle, so a ring of one to
three slots has gaps between them.

Flicking: moving the cursor out past a slot's outer edge picks it straight away (ring.flick), and reaching a
submenu's disc opens it (ring.hover_submenus). Either way a submenu opens centred on that slot, still in hold
mode while the hotkey is down, so one stroke can run through a submenu into its items.

Fans: a submenu whose menu says "fan" opens in place instead: its items spread in an arc on the outer side of
its slot, joined to it by dashed lines, and the ring stays. A fan slot that is itself a fan submenu fans out
again, further out (up to FAN_DEPTH deep). A menu already open on the way there opens as a ring instead, so
menus that point at each other cannot loop, and so does a fan with no room (by a screen edge). self.open is the path of open fans, e.g. [3, 1]: slot 3's fan,
then the fan of its slot 1. The window grows to hold the open fans and shrinks when they close. A fan stays
open while the cursor is on its slot or inside its wedge, and closes FAN_GRACE after the cursor leaves.

Motion: every slot is a pre-rendered sprite (idle and hover look). Each frame only scales, fades, moves,
rotates or blurs sprites and composites them, so a frame costs a few milliseconds. Open animations are
staggered per slot (modes below); hover eases over 120 ms; closing is instant so picks never wait. Fan slot
sprites are rendered while the ring is idle, so a fan opens without a hitch.

The window never takes focus (WS_EX_NOACTIVATE from creation, MA_NOACTIVATE on clicks), so the target app
keeps keyboard focus and sees every key-up.

Lifecycle: Ring(...).show(x, y) -> owner calls key_released() when the hotkey goes up -> the ring calls
on_done(item_or_None, reason, at) exactly once and destroys itself. at: screen position of the picked slot
for a flick or submenu hover (where a submenu should open), else None.
"""
import ctypes
import hashlib
import math
import os
import threading
import time
import traceback
from collections import OrderedDict

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import layout
import shapes
import tags
import theme
import win32 as W
from shapes import SLOT_CORNER   # noqa: F401  (a rounded slot's corner share; it lives in shapes now)

SS = 3                      # supersampling for sprites (drawn large, reduced once)
TIMER_TICK = 1
CLASS_NAME = "ZOrbitRing"
HOVER_MS = 120
MAX_SECTOR = layout.MAX_SECTOR   # widest angle (degrees) a single slot answers to (layout.py; app.js copies it)
TAG_BANDS = {"hairline": 0.0, "narrow": 0.36, "medium": 0.62, "wide": 0.9}   # band width, relative to a slot
FAN_SLOT = 0.86             # fan slot size, relative to a ring slot
FAN_DEPTH = 3               # fans inside fans, at most this deep
FAN_SPAN = (130.0, 110.0)   # widest arc (degrees) of a first fan and of a deeper one
FAN_TURNS = (0, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90)   # turns tried to dodge slots and edges
FAN_MS = 220                # longest fan open animation (per slot)
FAN_GRACE = 0.12            # seconds a fan stays open after the cursor leaves it
SLOT_GAP = layout.SLOT_GAP       # neighbouring slot centres are at least this many slot widths apart (layout.py; app.js copies it)
SPRITE_MENUS = 8            # menus whose sprites are kept between opens
_instances = {}
_sprite_cache = OrderedDict()   # key (see Ring._sprite_key) -> (sprites, labels, dot), least recently used first
SLOT_SPRITES = 160          # single slots kept, so a menu that changed by one slot redraws only that slot
_slot_cache = OrderedDict()     # key (see Ring._slot_key) -> (slot sprites, label sprites), least recently used first
_sprite_lock = threading.Lock()
_class_registered = False
_wndproc_ref = None
try:
    _winmm = ctypes.WinDLL("winmm")
except OSError:
    _winmm = None


# --- easing --------------------------------------------------------------------------------------
def cubic_bezier(x1, y1, x2, y2):
    """CSS cubic-bezier timing function (y may overshoot 1)."""
    def bez(t, a, b):
        return 3 * a * (1 - t) ** 2 * t + 3 * b * (1 - t) * t * t + t ** 3

    def dbez(t, a, b):
        return 3 * a * (1 - t) ** 2 + 6 * (b - a) * (1 - t) * t + 3 * (1 - b) * t * t

    def f(x):
        if x <= 0:
            return 0.0
        if x >= 1:
            return 1.0
        t = x
        for _ in range(8):                         # Newton on x(t) = x
            d = dbez(t, x1, x2)
            if abs(d) < 1e-6:
                break
            t -= (bez(t, x1, x2) - x) / d
            t = min(max(t, 0.0), 1.0)
        return bez(t, y1, y2)
    return f


EASE = cubic_bezier(0.25, 0.1, 0.25, 1.0)
EASE_OUT = cubic_bezier(0.22, 1, 0.36, 1)

# Only spiral staggers its slots (one after another, clockwise); every other mode animates all slots
# together.
# mode: stagger ms, move/scale duration ms, opacity duration ms, curve, scale from, travel (fraction of the
# way from the seat to the centre the slot starts at; negative = beyond the seat), rotation from (deg),
# blur from (px), drift (px below), extras
MODES = {
    "smooth": dict(stagger=0, dur=180, fade=120, curve=(0.34, 1.4, 0.64, 1), scale=0.8),
    "bounce": dict(stagger=0, dur=340, fade=160, curve=(0.34, 1.8, 0.5, 1), scale=0.5),
    "pop":    dict(stagger=0, dur=130, fade=100, curve=(0.2, 0.9, 0.3, 1), scale=0.72),
    "zoom":   dict(stagger=0, dur=260, fade=160, curve=(0.22, 1, 0.36, 1), scale=1.35),
    "fade":   dict(stagger=0, dur=220, fade=220, curve=(0.25, 0.1, 0.25, 1), scale=1.0),
    "drift":  dict(stagger=0, dur=280, fade=200, curve=(0.22, 1, 0.36, 1), scale=1.0, drift=10),
    "fancy":  dict(stagger=0, dur=500, fade=280, curve=(0.34, 1.56, 0.64, 1), scale=0.25, travel=1.0, dot_pop=True),
    "spiral": dict(stagger=30, dur=600, fade=280, curve=(0.2, 0.85, 0.3, 1), scale=0.2, travel=1.0, rot=-150,
                   dot_pop=True),
    "ripple": dict(stagger=0, dur=550, fade=280, curve=(0.16, 1, 0.3, 1), scale=0.6, travel=0.86, blur=4,
                   blur_ms=450, ripples=True, dot_pop=True),
    "breath": dict(stagger=0, dur=700, fade=300, curve=(0.25, 0.8, 0.25, 1), scale=0.5, travel=0.4, blur=6,
                   blur_ms=600, halo=True, dot_pop=True),
    "mist":   dict(stagger=0, dur=600, fade=300, curve=(0.22, 1, 0.36, 1), scale=1.15, travel=-0.45, blur=10,
                   blur_ms=600, dot_pop=True),
    "snappy": dict(stagger=0, dur=0, fade=0, curve=(0, 0, 1, 1), scale=1.0),
}
MODE_NAMES = list(MODES)


_FONT_CACHE = {}            # (font file, px) -> loaded font, or None when it would not load


def _fonts_dir():
    return os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")


def _load_font(name, px):
    path = os.path.join(_fonts_dir(), name)
    key = (path, px)
    if key not in _FONT_CACHE:
        try:
            if not os.path.isfile(path):           # Pillow would go looking in the other font folders
                raise OSError(path)
            _FONT_CACHE[key] = ImageFont.truetype(path, px, index=0)   # index 0 picks the first face of a .ttc
        except OSError:
            _FONT_CACHE[key] = None
    return _FONT_CACHE[key]


def _font(px: int, bold=True):
    px = max(6, px)
    for name in (("segoeuib.ttf", "seguisb.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        f = _load_font(name, px)
        if f is not None:
            return f
    return ImageFont.load_default()


# Code point ranges Segoe UI draws: Latin (with its extensions), Greek, Cyrillic, general punctuation, currency.
_SEGOE_RANGES = ((0x0000, 0x024F), (0x0370, 0x03FF), (0x0400, 0x052F), (0x1E00, 0x1FFF), (0x2000, 0x206F),
                 (0x20A0, 0x20CF))
_HANGUL = ((0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF))
_KANA = ((0x3040, 0x30FF),)
_WIDE_FONTS = {                                    # bold, regular: Chinese, Japanese, Korean, symbols
    "zh": ("msyhbd.ttc", "msyh.ttc"), "ja": ("YuGothB.ttc", "YuGothM.ttc"),
    "ko": ("malgunbd.ttf", "malgun.ttf"), "sym": ("seguisym.ttf", "seguisym.ttf"),
}


def _in(ch, ranges):
    c = ord(ch)
    return any(lo <= c <= hi for lo, hi in ranges)


def _font_for(text: str, px: int, bold=True):
    """The font for text: Segoe UI when every character is Latin, Greek, Cyrillic or common punctuation,
    otherwise the first of YaHei, Yu Gothic, Malgun Gothic and Segoe UI Symbol that loads (Yu Gothic comes first
    for text with kana, Malgun first for Hangul), then the Segoe chain. Loaded fonts are cached."""
    if all(_in(ch, _SEGOE_RANGES) for ch in text):
        return _font(px, bold)
    first = "ko" if any(_in(ch, _HANGUL) for ch in text) else "ja" if any(_in(ch, _KANA) for ch in text) else "zh"
    px = max(6, px)
    for lang in (first,) + tuple(k for k in ("zh", "ja", "ko", "sym") if k != first):
        f = _load_font(_WIDE_FONTS[lang][0 if bold else 1], px)
        if f is not None:
            return f
    return _font(px, bold)


def _sprite_get(key):
    with _sprite_lock:
        val = _sprite_cache.get(key)
        if val is not None:
            _sprite_cache.move_to_end(key)
        return val


def _slot_get(key, make):
    """One slot's (sprites, label) for key, from _slot_cache or made now. A menu whose whole-menu entry missed
    (a slot added, moved or changed) then draws only the slots that are new."""
    with _sprite_lock:
        val = _slot_cache.get(key)
        if val is not None:
            _slot_cache.move_to_end(key)
            return val
    val = make()
    with _sprite_lock:
        _slot_cache[key] = val
        while len(_slot_cache) > SLOT_SPRITES:
            _slot_cache.popitem(last=False)
    return val


def _sprite_put(key, val):
    """Keeps val for key; only the SPRITE_MENUS most recently used entries stay. An older entry of the same menu
    at the same scale goes first (key[0] and key[3]), so dragging a slider does not push other menus out."""
    with _sprite_lock:
        for old in [k for k in _sprite_cache if k != key and k[0] == key[0] and k[3] == key[3]]:
            del _sprite_cache[old]
        _sprite_cache[key] = val
        _sprite_cache.move_to_end(key)
        while len(_sprite_cache) > SPRITE_MENUS:
            _sprite_cache.popitem(last=False)


def _icon_sig(im):
    """A short fingerprint of an icon image: same picture, same signature, however many objects hold it."""
    if im is None:
        return None
    return (im.size, im.mode, hashlib.blake2b(im.tobytes(), digest_size=8).hexdigest())


def _shorten(draw, text, font, maxw):
    """text cut short with an ellipsis until it is no wider than maxw pixels in font."""
    if draw.textbbox((0, 0), text, font=font)[2] <= maxw:
        return text
    while len(text) > 1 and draw.textbbox((0, 0), text + "…", font=font)[2] > maxw:
        text = text[:-1]
    return text + "…"


def _rgb(c: str):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _rgba(c: str, a: float):
    return _rgb(c) + (int(round(255 * a)),)


def _mix(c1: str, c2: str, t: float):
    """RGB tuple t of the way from colour c1 to colour c2."""
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(_rgb(c1), _rgb(c2)))


def _fade(im, a: float):
    if a >= 0.999:
        return im
    if a <= 0.001:
        return None
    out = im.copy()
    out.putalpha(out.getchannel("A").point([int(v * a) for v in range(256)]))
    return out


ROLES = ("bg", "accent", "highlight", "text", "lines")


def _role(v, colors):
    """A colour setting as #rrggbb: a theme role (bg, accent, highlight, text, lines) takes the colour the theme
    gives it, a hex colour is passed on and "" stays "" (no colour of its own). Kept in one place so the looks
    module can take it over."""
    if not isinstance(v, str) or not v:
        return ""
    if v in ROLES:
        return colors.get(v) or colors.get("accent", "")
    return v


def _chrome(it, look):
    """The colour an item's rim, spoke, hover and fan lines take: its tag colour, except for an empty tag slot,
    which stays faint all over (its colour only tints the glyph). A slot carrying a tag keeps its colour even
    when the look has tag colours off."""
    return it.color if (it.tag or look.tags_on) and it.kind != "tag" else ""


def _num(v, default, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return min(hi, max(lo, v)) if v == v else default


# Look keys that reach the sprites (so are part of the cache key) and ring keys that do not. Every key of
# config.DEFAULT_RING is in exactly one of them: a guard test checks it, so a new setting has to be classified.
SPRITE_LOOK_KEYS = ("slot", "slot_shape", "slot_corner", "border_width", "icon_scale", "hub", "hub_style",
                    "hub_color", "hub_glow", "glow_color", "glow_opacity", "labels", "label_color", "tag_colors",
                    "tag_glow_opacity", "tag_tint_opacity", "tag_tint_style", "tag_tint_blend", "theme", "colors")
NOT_IN_SPRITES = frozenset(("radius", "dead_zone", "tap_ms", "timeout_s", "animation", "flick", "hover_submenus", "hint",
                            "tag_limit", "tag_band", "tag_band_opacity", "look", "when_full"))
HUB_STYLES = ("dot", "disc", "ring", "icon")


class _Look:
    """The look of one ring or fan, read once from a settings dict (the ring's, with a menu's look over it):
    sizes, shapes, parsed colours and the settings the sprites are drawn from. Never changed after it is made."""

    def __init__(self, d):
        colors = dict(d["colors"])
        colors.setdefault("lines", colors["accent"])
        set_ = object.__setattr__
        set_(self, "colors", colors)
        set_(self, "bg", colors["bg"])
        set_(self, "accent", colors["accent"])
        set_(self, "hi", colors["highlight"])
        set_(self, "text", colors["text"])
        set_(self, "lines", colors["lines"])
        set_(self, "theme", d.get("theme", "dark"))
        set_(self, "pre", theme.preset(self.theme)["ring"])        # the theme's pill, hint, badge, placeholder
        set_(self, "radius", d.get("radius", 145))
        set_(self, "slot", d.get("slot", 72))
        set_(self, "dead_zone", d.get("dead_zone", 38))
        shape = d.get("slot_shape", "circle")
        set_(self, "slot_shape", shape if shape in shapes.SHAPES else "circle")
        set_(self, "slot_corner", _num(d.get("slot_corner"), SLOT_CORNER, 0.0, 0.5))
        set_(self, "border_width", _num(d.get("border_width"), 2, 0, 6))
        set_(self, "icon_scale", _num(d.get("icon_scale"), 1.0, 0.5, 1.0))
        set_(self, "labels", d.get("labels", "name"))
        set_(self, "label_color", _role(d.get("label_color", "text"), colors) or colors["text"])
        set_(self, "glow_color", _role(d.get("glow_color", ""), colors))
        set_(self, "glow_opacity", _num(d.get("glow_opacity"), 0.55, 0.0, 1.0))
        set_(self, "hub", max(0, d.get("hub", 10)))
        style = d.get("hub_style", "dot")
        set_(self, "hub_style", style if style in HUB_STYLES else "dot")
        set_(self, "hub_color", _role(d.get("hub_color", "accent"), colors) or colors["accent"])
        set_(self, "hub_glow", _num(d.get("hub_glow"), 1.0, 0.0, 1.0))
        set_(self, "when_full", d.get("when_full", "grow"))
        set_(self, "tag_colors", d.get("tag_colors", "tint"))
        set_(self, "tag_glow_opacity", d.get("tag_glow_opacity", 0.4))
        set_(self, "tag_tint_opacity", d.get("tag_tint_opacity", 0.3))
        set_(self, "tag_tint_style", d.get("tag_tint_style", "gradient"))
        set_(self, "tag_tint_blend", d.get("tag_tint_blend", "multiply"))
        set_(self, "tag_band", d.get("tag_band", "medium"))
        set_(self, "tag_band_opacity", d.get("tag_band_opacity", 0.45))
        set_(self, "tags_on", self.tag_colors != "none" or self.tag_band != "none")   # as the Expander gates them
        set_(self, "sig", _look_sig(self))

    def __setattr__(self, name, value):
        raise AttributeError("a look is read-only")


def _look_sig(look):
    """What the sprites are drawn from, as a hashable tuple (a look's part of the sprite cache key)."""
    return tuple((look.bg, look.accent, look.hi, look.text) if k == "colors" else getattr(look, k)
                 for k in SPRITE_LOOK_KEYS)


def _merged(ring_cfg, over):
    """The ring's settings with a menu's look laid over them (its colours merge key by key)."""
    out = {**ring_cfg, **over}
    if isinstance(over.get("colors"), dict):
        out["colors"] = {**ring_cfg["colors"], **over["colors"]}
    return out


def _item_sig(it):
    """What an item's sprites are drawn from, apart from its icon."""
    return (it.kind, it.label, it.color, it.tag, getattr(it, "glow", ""), tuple(sorted(_style(it).items())),
            _is_more(it))


def _style(it):
    return getattr(it, "style", None) or {}


def _glyph_more(draw, cx, cy, size, fill):
    """Three dots in a row, size across: the glyph of a More slot."""
    r = size * 0.075
    for k in (-1, 0, 1):
        x = cx + k * size * 0.24
        draw.ellipse((x - r, cy - r, x + r, cy + r), fill=fill)


def _is_more(it):
    """A slot that opens a paged-out part of its menu: a submenu whose id starts with "more:"."""
    return it.kind == "menu" and str(it.data.get("menu", "")).startswith("more:")


def _tint_icon(icon, col, amount, style, blend):
    """icon (RGBA, a disc) with colour col laid over it by multiply or overlay; gradient makes it stronger
    towards the rim and weaker in the middle."""
    rgb = icon.convert("RGB")
    over = Image.new("RGB", icon.size, _rgb(col))
    mixed = ImageChops.overlay(rgb, over) if blend == "overlay" else ImageChops.multiply(rgb, over)
    if style == "gradient":                        # radial_gradient: 0 at the centre, 128 at the disc's edge
        lut = [int(min(255, amount * 255 * (0.4 + min(1.0, v / 128)))) for v in range(256)]
        mask = Image.radial_gradient("L").resize(icon.size, Image.BILINEAR).point(lut)
    else:
        mask = Image.new("L", icon.size, int(amount * 255))
    out = Image.composite(mixed, rgb, mask).convert("RGBA")
    out.putalpha(icon.getchannel("A"))
    return out


def _blit(canvas, im, x, y):
    """alpha_composite im at (x, y), clipped to the canvas (Pillow refuses offsets off its top or left)."""
    x, y = int(x), int(y)
    l, t = max(0, -x), max(0, -y)
    r, b = min(im.size[0], canvas.size[0] - x), min(im.size[1], canvas.size[1] - y)
    if r > l and b > t:
        canvas.alpha_composite(im, (x + l, y + t), (l, t, r, b))


def _glyph_tag(draw, cx, cy, size, fill):
    """A luggage tag (outline, a ring hole near the blunt end) pointing up and right, size across."""
    a = math.radians(-45)
    ca, sa = math.cos(a), math.sin(a)

    def pt(x, y):                                  # tag space (x along the tag) to the picture
        return cx + (x * ca - y * sa) * size, cy + (x * sa + y * ca) * size
    draw.polygon([pt(-0.5, -0.27), pt(0.06, -0.27), pt(0.5, 0.0), pt(0.06, 0.27), pt(-0.5, 0.27)],
                 outline=fill, width=max(1, int(size * 0.1)))
    hx, hy = pt(-0.27, 0.0)
    hr = size * 0.07
    draw.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), outline=fill, width=max(1, int(size * 0.07)))


def _glyph_star(draw, cx, cy, size, fill):
    """A five-point star, outline like the luggage tag, size across, one point straight up."""
    pts = []
    for i in range(10):
        a = math.radians(-90 + i * 36)
        r = size * (0.55 if i % 2 == 0 else 0.23)
        pts.append((cx + math.cos(a) * r, cy + 0.05 * size + math.sin(a) * r))
    draw.polygon(pts, outline=fill, width=max(1, int(size * 0.07)))


def _glyph_grid(draw, cx, cy, size, fill):
    """Four small rounded squares in a 2x2 grid, size across."""
    q, g = size * 0.43, size * 0.14
    for dx in (-1, 1):
        for dy in (-1, 1):
            x0, y0 = cx + (g / 2 if dx > 0 else -g / 2 - q), cy + (g / 2 if dy > 0 else -g / 2 - q)
            draw.rounded_rectangle((x0, y0, x0 + q, y0 + q), radius=q * 0.25, fill=fill)


def _glyph_fan(draw, ox, oy, radius, fill):
    """A folding fan: three blades with small gaps, a quarter circle from (ox, oy) opening up and right."""
    box = (ox - radius, oy - radius, ox + radius, oy + radius)
    for a0, a1 in ((-90, -68), (-56, -34), (-22, 0)):
        draw.pieslice(box, a0, a1, fill=fill)


def _wndproc(hwnd, msg, wparam, lparam):
    ring = _instances.get(int(hwnd) if hwnd else 0)
    if ring is not None:
        try:
            r = ring._on_message(msg, wparam, lparam)
            if r is not None:
                return r
        except Exception:                         # never let an exception unwind into Windows
            ring._log("ring error:\n" + traceback.format_exc())
            ring._finish(None, "error")
            return 0
    return W.DefWindowProcW(hwnd, msg, wparam, lparam)


def _register_class():
    global _class_registered, _wndproc_ref
    if _class_registered:
        return
    _wndproc_ref = W.WNDPROC(_wndproc)
    wc = W.WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(W.WNDCLASSEXW)
    wc.lpfnWndProc = _wndproc_ref
    wc.hInstance = W.GetModuleHandleW(None)
    wc.hCursor = W.LoadCursorW(None, ctypes.c_void_p(32512))   # IDC_ARROW
    wc.lpszClassName = CLASS_NAME
    if not W.RegisterClassExW(ctypes.byref(wc)):
        raise ctypes.WinError(ctypes.get_last_error())
    _class_registered = True


class _Fan:
    """One fan: a submenu's items in an arc beyond its slot. Positions are relative to the ring centre, angles
    in radians (math convention, y down)."""

    def __init__(self, path, menu, anchor, anchor_r, cslot, axis, offs, dists, pos, step, half, reach):
        self.path = path                           # path of the slot it opens from
        self.menu = menu
        self.items = menu.items
        self.anchor, self.anchor_r = anchor, anchor_r
        self.cslot = cslot
        self.csizes = [cslot] * len(self.items)    # each slot's width: cslot times its item's style size
        self.axis, self.offs, self.dists, self.pos = axis, offs, dists, pos
        self.step, self.half, self.reach = step, half, reach   # slot spacing, wedge half-angle and length
        self.hv = [[0.0, 0.0, 0.0] for _ in self.items]
        self.t_open = 0.0
        self.look = None                           # its styling: its menu's own look, else the ring's
        self.sprites = self.labels = self.lines = None
        self.motion = (0, 0, 0, None)              # duration, fade, stagger (ms), curve
        self.total = 0


class Ring:
    def __init__(self, menu, ring_cfg: dict, icon_for, on_done, log, held: bool, nested=False, submenus=None):
        """menu: config.Menu. icon_for(item) -> PIL RGBA image or None. on_done(item|None, reason, at).
        held: True when opened by a hotkey that is still down (enables hold-and-release picking).
        nested: opened by flicking or hovering onto a submenu slot of another ring: the dead zone covers that
        slot's disc, and releasing the hotkey in the centre keeps the ring open for a click.
        submenus(menu_id) -> config.Menu or None: lets submenus that fan out open in place; without it every
        submenu is handed back through on_done."""
        self.menu = menu
        self.items = menu.items
        self.cfg = ring_cfg                        # behaviour keys (tap, flick, animation ...) are read from here
        self.look = _Look(_merged(ring_cfg, getattr(menu, "look", None) or {}))   # what is drawn: this menu's look
        self._looks = {}                           # fan menu id -> its _Look
        self._hub_img = None                       # (icon image or None,) of the hub icon, once asked
        self.icon_for = icon_for
        self.on_done = on_done
        self._log = log
        self.mode = "hold" if held else "click"
        self.nested = nested
        self.submenus = submenus
        self.anim_name = getattr(menu, "animation", "") or ring_cfg.get("animation", "smooth")
        self.anim = MODES.get(self.anim_name, MODES["smooth"])
        self.curve = cubic_bezier(*self.anim["curve"])
        self.hover = None                          # path of the slot under the cursor
        self.open = []                             # path of open fans
        self.fans = {}                             # path -> _Fan, kept while the ring lives
        self._layouts = {}
        self._menus = {}
        self._art = {}                             # menu id -> [(sprites, labels)] of its fan slots
        self._warm = None
        self._out_t = None
        self.done = False
        self.hwnd = None
        self.work = None
        self.cs = (0, 0)                           # ring centre on screen
        self._armed = True                         # False while flicks and hover hand-offs wait (see _fit_centre)
        self._dib = None
        self._last_key = None
        self._base_cache = None
        self._icons = {}                           # id(item) -> its icon image, for _sprite_key and the sprites

    # --- public ----------------------------------------------------------------------------------
    @classmethod
    def preview(cls, menu, ring_cfg: dict, icon_for, hover=None, scale=1.0, t=None, submenus=None,
                open_path=None, held=False, open_age=None):
        """Renders the ring to a PIL RGBA image without a window (Studio). t: seconds since open, or None
        for the settled look. open_path: indices of the fans to show open (needs submenus). The ring centre
        is in im.info["centre"] (and the hovered slot in im.info["hover_at"]): with a fan open the image is no
        longer square around it. im.info["layout"] is layout_map(): where every slot, gap and open fan is. hover: an item index, or a path (a tuple) for a slot inside an open fan.
        held: draw the hold-mode hint instead of the click-mode one. open_age: seconds since the fans opened,
        a number for all of them or {path: seconds}; None for settled."""
        r = cls(menu, ring_cfg, icon_for, lambda *a: None, lambda m: None, held=held, submenus=submenus)
        r._geometry(scale)
        r._relayout()
        r._prepare()
        now = 1000.0
        r.t0 = now - (t if t is not None else 10.0)
        path = tuple(open_path or ())
        for k in range(1, len(path) + 1):
            if not r._fannable(path[:k]):
                break
            age = open_age.get(path[:k]) if isinstance(open_age, dict) else open_age
            if age is None:
                age = 10.0
            r._set_open(path[:k], now - age)
        r.hover = None if hover is None else tuple(hover) if isinstance(hover, (tuple, list)) else (hover,)
        r._apply_hover(now, instant=True)
        im = r._compose(now)
        im.info["centre"] = r.centre
        if r.hover is not None:                    # where the hovered slot is, for a picture that draws a cursor
            try:
                x, y = r._node_pos(r.hover)
                im.info["hover_at"] = (r.centre[0] + x, r.centre[1] + y)
            except (KeyError, IndexError):
                pass
        im.info["layout"] = r.layout_map()
        return im

    @classmethod
    def preview_frames(cls, menu, ring_cfg: dict, icon_for, scale=1.0, fps=30, submenus=None):
        """Frames of the open animation (Studio animation preview). submenus: as for preview (the badges)."""
        r = cls(menu, ring_cfg, icon_for, lambda *a: None, lambda m: None, held=False, submenus=submenus)
        r._geometry(scale)
        r._relayout()
        r._prepare()
        total = r._open_ms() / 1000.0 + 0.15
        frames, now0 = [], 1000.0
        r.t0 = now0
        for k in range(int(total * fps) + 1):
            frames.append(r._compose(now0 + k / fps))
        if frames:
            frames[0].info["layout"] = r.layout_map()      # of the settled ring; the frames share one geometry
        return frames

    def layout_map(self):
        """Where everything of the ring is, as plain JSON numbers in preview pixels (y down), for Studio's overlay:
        {"scale", "size": [w, h] of the image, "centre": [x, y] of the ring centre in it, "dead": dead zone radius,
        "hub": {"style", "r"}, "rings": [{"r", "first", "n", "offset", "step", "rmin"}],
        "slots": [{"i", "ring", "x", "y", "size", "shape", "corner", "ang", "half", "more"}],
        "gaps": [{"k", "x", "y", "ang"}], "full": {"mode", "when_full", "n", "capacity", "needed", "radius",
        "grown", "rings", "more_slot"}, "fans": [{"path", "anchor": [x, y], "slots": [{"k", "x", "y", "size",
        "shape"}]}]}. x and y are from the ring centre. ang is in degrees clockwise from 12 o'clock and half is half
        the angle a slot answers to. A gap k is where an item dropped there would go in before ring slot k (1 to n,
        k = n after the last), midway between its neighbours. fans lists the open fans only. Call it after
        _geometry and _relayout (and with the fans open that should show)."""
        def r2(v):
            return round(float(v), 2)

        pl, look = self.plan, self.look
        rings = [{"r": r2(rp.radius), "first": rp.first, "n": rp.n, "offset": r2(rp.offset), "step": r2(rp.step),
                  "rmin": r2(max(rp.rmin, self.dead) if k == 0 else rp.rmin)} for k, rp in enumerate(pl.rings)]
        slots = []
        for i, it in enumerate(self.items):
            seat, (ux, uy) = pl.seats[i], self.seats[i]
            shape, corner = self._shape_of(it, look)
            slots.append({"i": i, "ring": seat.ring, "x": r2(ux * self.rad[i]), "y": r2(uy * self.rad[i]),
                          "size": r2(self.sizes[i]), "shape": shape, "corner": r2(_num(corner, SLOT_CORNER, 0.0, 0.5)),
                          "ang": r2(seat.angle), "half": r2(min(pl.rings[seat.ring].step, MAX_SECTOR) / 2),
                          "more": _is_more(it)})
        gaps = []
        for ring_k, rp in enumerate(pl.rings):
            # k is the item index a dropped item would take. A single ring has k = 1 to n (n: the wrap, after the
            # last). With two rings the inner one has 1 to its n - 1 (its wrap is the boundary) and the outer one
            # k = first (before its first slot, half a step back) to the end.
            lo = 0 if ring_k > 0 else 1
            hi = rp.n - 1 if ring_k == 0 and len(pl.rings) > 1 else rp.n
            for j in range(lo, hi + 1):
                a = rp.offset + rp.step * (j - 0.5)
                gaps.append({"k": rp.first + j, "x": r2(math.sin(math.radians(a)) * rp.radius),
                             "y": r2(-math.cos(math.radians(a)) * rp.radius), "ang": r2(a % 360)})
        more_slot = next((i for i, it in enumerate(self.items) if _is_more(it)), None)
        fans = []
        for fan in self._open_fans():
            fans.append({"path": list(fan.path), "anchor": [r2(fan.anchor[0]), r2(fan.anchor[1])],
                         "slots": [{"k": k, "x": r2(px), "y": r2(py), "size": r2(fan.csizes[k]),
                                    "shape": self._shape_of(fan.items[k], fan.look)[0]}
                                   for k, (px, py) in enumerate(fan.pos)]})
        return {"scale": self.scale, "size": list(self.size), "centre": [r2(self.centre[0]), r2(self.centre[1])],
                "dead": r2(self.dead), "hub": {"style": look.hub_style, "r": r2(look.hub / 2 * self.scale)},
                "rings": rings, "slots": slots, "gaps": gaps,
                "full": {"mode": pl.mode, "when_full": look.when_full, "n": self.n, "capacity": pl.capacity,
                         "needed": r2(pl.needed), "radius": r2(pl.radius), "grown": pl.grown,
                         "rings": len(pl.rings), "more_slot": more_slot},
                "fans": fans}

    def show(self, x: int, y: int) -> None:
        _register_class()
        work, scale = W.monitor_for_point(x, y)
        self._geometry(scale)
        self.cs, self.work = (x, y), work
        self._fit_centre()
        self._armed = self.cs == (x, y)            # moved in from an edge: see _fit_centre
        self._relayout()
        self._prepare()
        self.t0 = time.time()
        ex = W.WS_EX_NOACTIVATE | W.WS_EX_TOPMOST | W.WS_EX_TOOLWINDOW | W.WS_EX_LAYERED
        self.hwnd = W.CreateWindowExW(ex, CLASS_NAME, "ZOrbit", W.WS_POPUP, *self.origin, *self.size,
                                      None, None, W.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        _instances[int(self.hwnd)] = self
        period = False
        try:
            if _winmm is not None:
                _winmm.timeBeginPeriod(1)          # 10 ms timer ticks really are 10 ms while open
                period = True
            self._render(self.t0)
            W.ShowWindow(self.hwnd, W.SW_SHOWNOACTIVATE)
            W.SetWindowPos(self.hwnd, W.HWND_TOPMOST, 0, 0, 0, 0,
                           W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE | W.SWP_SHOWWINDOW)
            W.SetTimer(self.hwnd, TIMER_TICK, 10, None)
        except Exception:                          # no half-shown ring left on screen, and no leaked handles
            self.done = True
            hwnd, self.hwnd = self.hwnd, None
            _instances.pop(int(hwnd), None)
            W.DestroyWindow(hwnd)
            if period:
                _winmm.timeEndPeriod(1)
            self._free_dib()
            raise
        moved = f", centred at {self.cs} to fit the screen" if self.cs != (x, y) else ""
        self._log(f"ring '{self.menu.id}' shown at ({x},{y}) mode={self.mode} anim={self.anim_name} "
                  f"scale={scale:.2f}{moved}")

    def key_released(self) -> None:
        if self.done or self.mode != "hold":
            return
        if not self._armed:                        # the ring was moved in from an edge and the cursor has not
            self._stay_open("released before reaching the moved ring")   # reached it: a release picks nothing
            return
        path, how, node = self._current_hover()
        if node is not None and self._fannable(path):
            self._set_open(path, time.time())
            self._stay_open("released on a fan")
        elif how == "wedge":
            self._stay_open("released inside a fan")
        elif self.nested and node is None:
            self._stay_open("released in the centre of a submenu")
        elif not self.nested and node is None and (time.time() - self.t0) * 1000 < self.cfg["tap_ms"]:
            self._stay_open("tap")                 # a release over a slot picks it, however fast
        else:
            self._finish(node, "released")

    def _stay_open(self, why):
        self.mode = "click"                        # wait for a click
        self._static_cache = None                  # hint text changes
        self._log(f"{why}: ring stays open for a click")

    def cancel(self, reason="cancelled") -> None:
        self._finish(None, reason)

    # --- geometry --------------------------------------------------------------------------------
    def _geometry(self, scale):
        c = self.look
        self.scale = scale
        self.n = len(self.items)
        self.slot = c.slot * scale
        # a slot's own size is a share (0.75 to 1.25) of the ring's slot size, from its style
        self.sizes = [self.slot * _num(_style(it).get("size"), 1.0, 0.75, 1.25) for it in self.items]
        # the radius is a minimum: layout grows it until neighbours have room
        self.plan = layout.plan(self.sizes, c.radius * scale, c.when_full, c.labels != "none")
        self.R = self.plan.rings[0].radius                       # the first (inner) ring's radius
        self.step = self.plan.rings[0].step
        self.rad = [seat.radius for seat in self.plan.seats]     # each slot's distance from the centre
        self.dead = c.dead_zone * scale
        if self.nested:                            # entered on the parent's slot disc: no instant pick there
            self.dead = max(self.dead, max(self.sizes) / 2 + 4 * scale)
        past = [self.rad[i] + self.sizes[i] * 0.56 for i in range(self.n)]   # just past the hovered (1.12x) disc
        self.flick_r = max(past)                   # the cursor is "inside" the ring while it is closer than this
        # with a second ring only its slots flick: going out from an inner slot just meets the outer ring
        self.flick_at = past if len(self.plan.rings) < 2 else [
            math.inf if self.plan.seats[i].ring == 0 else past[i] for i in range(self.n)]
        grow = 1.0 + max(0.0, -self.anim.get("travel", 0.0))
        self.pad = max(self.sizes) * 0.62 + 34 * scale    # half the widest slot at 1.12x + glow + label
        # the ring's own square; the window adds open fans
        self.rsize = int(2 * max(self.rad[i] * grow + (self.sizes[i] * 0.62 + 34 * scale) for i in range(self.n)))
        self.hit_r = max(self.rad[i] + self.sizes[i] * 0.62 for i in range(self.n)) + 6 * scale   # clicks land inside
        self.seats = []
        for seat in self.plan.seats:
            a = math.radians(seat.angle)           # 0 at 12 o'clock, clockwise
            self.seats.append((math.sin(a), -math.cos(a)))

    def _fit_centre(self):
        """Moves the ring centre in from a screen edge so the whole ring disc is on the work area (the window is
        clamped there anyway; the ring itself would be cut off). The cursor then starts off-centre: _armed keeps
        that from picking anything."""
        wk = self.work
        if wk is None:
            return
        hr = self.rsize // 2
        (lo_x, hi_x), (lo_y, hi_y) = (wk.left + hr, wk.right - hr), (wk.top + hr, wk.bottom - hr)
        x, y = self.cs
        x = (lo_x + hi_x) // 2 if lo_x > hi_x else min(max(x, lo_x), hi_x)
        y = (lo_y + hi_y) // 2 if lo_y > hi_y else min(max(y, lo_y), hi_y)
        self.cs = (x, y)

    def _relayout(self):
        """Window origin and size for the ring plus its open fans, kept on the monitor's work area. Without a
        work area (Studio) the image just fits them."""
        hr = self.rsize // 2
        x0, y0, x1, y1 = -hr, -hr, self.rsize - hr, self.rsize - hr
        for fan in self._open_fans():
            for (px, py), cs in zip(fan.pos, fan.csizes):
                e = cs * 0.62 + 34 * self.scale
                x0, y0, x1, y1 = min(x0, px - e), min(y0, py - e), max(x1, px + e), max(y1, py + e)
        x0, y0, x1, y1 = math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)
        w, h = x1 - x0, y1 - y0
        ox, oy = self.cs[0] + x0, self.cs[1] + y0
        if self.work is not None:
            wk = self.work
            w, h = min(w, wk.right - wk.left), min(h, wk.bottom - wk.top)
            ox = min(max(ox, wk.left), wk.right - w)
            oy = min(max(oy, wk.top), wk.bottom - h)
        self.origin, self.size = (ox, oy), (w, h)
        self.centre = (self.cs[0] - ox, self.cs[1] - oy)   # ring centre in window coords
        self._free_dib()

    def _index_at(self, x, y):
        dx, dy = x - self.centre[0], y - self.centre[1]
        if math.hypot(dx, dy) < self.dead:
            return None
        ang = math.degrees(math.atan2(dx, -dy)) % 360          # 0 at top, clockwise
        rp = self.plan.rings[0]
        for later in self.plan.rings[1:]:                       # the ring whose band the cursor is in
            if math.hypot(dx, dy) >= later.rmin:
                rp = later
        j = int(round((ang - rp.offset) / rp.step)) % rp.n
        off = abs((ang - rp.offset - j * rp.step + 180) % 360 - 180)   # degrees from that slot's direction
        i = rp.first + j
        return i if off <= MAX_SECTOR / 2 and self.items[i].kind != "empty" else None    # an empty slot is nothing

    @staticmethod
    def _shape_of(it, look):
        """(shape, corner) of a slot: its own style over its ring's or fan's look."""
        st = _style(it)
        shape = st.get("slot_shape") or look.slot_shape
        corner = st.get("slot_corner")
        return (shape if shape in shapes.SHAPES else "circle"), (look.slot_corner if corner in (None, "") else corner)

    def _within(self, dx, dy, half, it, look):
        """Whether an offset from a slot's centre is on the slot: its shape, a box for a rounded one."""
        shape, corner = self._shape_of(it, look)
        return shapes.inside(shape, dx, dy, half, corner)

    def _hit(self, x, y):
        """(path, how) under window point x, y. how: "disc" (on a slot), "wedge" (inside an open fan but on
        none of its slots), "sector" (in a ring slot's angle) or None (dead zone or nowhere)."""
        rx, ry = x - self.centre[0], y - self.centre[1]
        fans = self._open_fans()
        for fan in reversed(fans):                 # deepest first
            for k, (px, py) in enumerate(fan.pos):
                rr = fan.csizes[k] / 2 * 1.12 + 4 * self.scale
                if fan.items[k].kind != "empty" and self._within(rx - px, ry - py, rr, fan.items[k], fan.look):
                    return fan.path + (k,), "disc"
        for i, (ux, uy) in enumerate(self.seats):
            if self.items[i].kind != "empty" and self._within(rx - ux * self.rad[i], ry - uy * self.rad[i],
                                                              self.sizes[i] / 2, self.items[i], self.look):
                return (i,), "disc"
        for fan in reversed(fans):
            if self._in_wedge(fan, rx, ry):
                return fan.path, "wedge"
        i = self._index_at(x, y)
        return (None, None) if i is None else ((i,), "sector")

    def _in_wedge(self, fan, rx, ry):
        vx, vy = rx - fan.anchor[0], ry - fan.anchor[1]
        d = math.hypot(vx, vy)
        if d < fan.anchor_r or d > fan.reach:
            return False
        return abs((math.atan2(vy, vx) - fan.axis + math.pi) % (2 * math.pi) - math.pi) <= fan.half

    def _fan_flick(self, rx, ry):
        """Index of the deepest open fan's slot the cursor has gone out past, or None."""
        fan = self.fans[tuple(self.open)]
        vx, vy = rx - fan.anchor[0], ry - fan.anchor[1]
        off = (math.atan2(vy, vx) - fan.axis + math.pi) % (2 * math.pi) - math.pi
        if abs(off) > fan.half:
            return None
        k = min(range(len(fan.offs)), key=lambda j: abs(off - fan.offs[j]))
        return k if math.hypot(vx, vy) >= fan.dists[k] + fan.csizes[k] * 0.56 else None

    def _current_hover(self):
        """(path, how, item) under the cursor; item is None between slots."""
        x, y = W.cursor_pos()
        path, how = self._hit(x - self.origin[0], y - self.origin[1])
        return path, how, (self._item(path) if how in ("disc", "sector") else None)

    def _item(self, path):
        if not path:
            return None
        if len(path) == 1:
            return self.items[path[0]]
        return self.fans[path[:-1]].items[path[-1]]

    def _node_pos(self, path):
        """Centre of the slot at path, relative to the ring centre."""
        if len(path) == 1:
            ux, uy = self.seats[path[0]]
            return ux * self.rad[path[0]], uy * self.rad[path[0]]
        return self.fans[path[:-1]].pos[path[-1]]

    def _size_at(self, path):
        """Width of the slot at path (a ring slot's own, or a fan slot's)."""
        if len(path) == 1:
            return self.sizes[path[0]]
        return self.fans[path[:-1]].csizes[path[-1]]

    def _node_screen(self, path):
        x, y = self._node_pos(path)
        return int(round(self.cs[0] + x)), int(round(self.cs[1] + y))

    # --- fans ------------------------------------------------------------------------------------
    def _submenu(self, mid):
        if mid not in self._menus:
            self._menus[mid] = self.submenus(mid) if self.submenus is not None and isinstance(mid, str) else None
        return self._menus[mid]

    def _fannable(self, path):
        """True when the slot at path is a submenu that fans out here: its menu says so, it is not already
        open on the way here, the fan would not be deeper than FAN_DEPTH, and it has room (by a screen edge
        it may not: then it opens as a ring like any other submenu)."""
        it = self._item(path)
        if it is None or it.kind != "menu" or len(path) > FAN_DEPTH:
            return False
        m = self._submenu(it.data.get("menu"))
        if m is None or not getattr(m, "fan", False) or not m.items:
            return False
        if m.id == self.menu.id or any(self.fans[path[:k]].menu.id == m.id for k in range(1, len(path))):
            return False
        return self._layout(path)[-1] <= self.slot * FAN_SLOT * 0.5

    def _fans_out(self, it):
        """The slot's submenu is set to fan out (its badge says so; by a screen edge it may still open as a ring)."""
        if it.kind != "menu" or self.submenus is None:
            return False
        m = self._submenu(it.data.get("menu"))
        return m is not None and getattr(m, "fan", False) and bool(m.items) and m.id != self.menu.id

    def _open_fans(self):
        return [self.fans[tuple(self.open[:k])] for k in range(1, len(self.open) + 1)]

    def _fan(self, path):
        """The fan of the slot at path, laid out (and rendered) on first use."""
        fan = self.fans.get(path)
        if fan is not None:
            return fan
        menu = self._submenu(self._item(path).data["menu"])
        cs = self.slot * FAN_SLOT
        anchor = self._node_pos(path)
        anchor_r = self._size_at(path) / 2
        fan = _Fan(path, menu, anchor, anchor_r, cs, *self._layout(path)[:-1])
        fan.csizes = self._fan_sizes(menu)
        fan.look = self._look_for(menu)
        art = self._fan_art(menu)
        fan.sprites, fan.labels = [a[0] for a in art], [a[1] for a in art]
        fan.lines = self._fan_lines(anchor, anchor_r, fan.pos, fan.csizes, _chrome(self._item(path), self._look_at(path)),
                                    fan.look)
        mode = MODES.get(menu.animation or self.cfg.get("animation", "smooth"), MODES["smooth"])
        dur = min(mode["dur"], FAN_MS)
        fade = max(1, min(mode["fade"], 150)) if dur else 0
        stagger = 25 if dur else 0
        fan.motion = (dur, fade, stagger, cubic_bezier(*mode["curve"]))
        fan.total = stagger * max(0, len(fan.items) - 1) + max(dur, fade)
        self.fans[path] = fan
        return fan

    def _look_for(self, menu):
        """The look a fan menu is drawn in: its own look over the ring's settings, else the ring's look (tag and
        More menus have none and inherit it). A fan takes styling only: its slot size stays a share of the ring's."""
        own = getattr(menu, "look", None)
        if not own:
            return self.look
        look = self._looks.get(menu.id)
        if look is None:
            look = self._looks[menu.id] = _Look(_merged(self.cfg, own))
        return look

    def _look_at(self, path):
        """The look of the ring or fan that holds the slot at path."""
        return self.look if len(path) == 1 else self.fans[path[:-1]].look

    def _layout(self, path):
        """_fan_layout for the slot at path, cached (its ancestors' fans must exist)."""
        lay = self._layouts.get(path)
        if lay is None:
            menu = self._submenu(self._item(path).data["menu"])
            sizes = self._fan_sizes(menu)
            cs, pad = max(sizes), 4 * self.scale
            anchor = self._node_pos(path)
            if len(path) == 1:                     # straight out from the ring centre
                axis = math.atan2(anchor[1], anchor[0])
            else:                                  # on along the way the parent fan points
                px, py = self._node_pos(path[:-1])
                axis = math.atan2(anchor[1] - py, anchor[0] - px)
            taken = [(0.0, 0.0, min(self.rad[i] - self.sizes[i] * 0.6 for i in range(self.n)))]
            taken += [(ux * self.rad[i], uy * self.rad[i], self.sizes[i] * 0.56 + pad)
                      for i, (ux, uy) in enumerate(self.seats)]
            for k in range(1, len(path)):
                fan = self.fans[path[:k]]
                taken += [(x, y, c * 0.56 + pad) for (x, y), c in zip(fan.pos, fan.csizes)]
            lay = self._layouts[path] = self._fan_layout(len(path), len(menu.items), anchor, axis, taken, cs)
        return lay

    def _fan_sizes(self, menu):
        """The width of each slot of a fan menu: the fan slot size times the item's own style size."""
        cs = self.slot * FAN_SLOT
        return [cs * _num(_style(it).get("size"), 1.0, 0.75, 1.25) for it in menu.items]

    def _fan_layout(self, depth, n, anchor, axis, taken, cs=None):
        """Seats for n slots in an arc around anchor, centred on axis: spaced so neighbours (and their
        labels) clear each other, the arc widened and pushed out as n grows, and past a size limit every other
        slot set further out. The arc turns away from ring slots, outer fans and the screen edge when it has
        to. cs: the widest slot of the fan. Returns (axis, offsets, distances, positions, step, wedge half-angle,
        wedge length, penalty)."""
        cs = cs or self.slot * FAN_SLOT
        g = cs * (1.3 if self.look.labels != "none" else 1.15)   # centre-to-centre gap
        span = math.radians(FAN_SPAN[0] if depth == 1 else FAN_SPAN[1])
        r = self.slot * (1.5 if depth == 1 else 1.3)
        r2, step = r, 0.0
        if n > 1:
            step = 2 * math.asin(min(1.0, g / (2 * r)))
            if step * (n - 1) > span:
                step = span / (n - 1)
                r = r2 = g / (2 * math.sin(step / 2))
                if r > 1.4 * self.R:               # too far out: two staggered rows instead
                    r = max(self.slot * 1.5, g / (2 * math.sin(step)))      # row neighbours are 2 steps apart
                    sin_s = r * math.sin(step)                              # outer row clears both inner neighbours
                    r2 = max(r + 0.8 * cs, r * math.cos(step) + math.sqrt(max(0.0, g * g - sin_s * sin_s)))
        offs = [(k - (n - 1) / 2) * step for k in range(n)]
        best = None
        # smallest change first: turning a little beats pushing out, which beats turning a lot
        tries = sorted((abs(turn) + 40 * k, turn, push) for turn in FAN_TURNS for k, push in enumerate((1.0, 1.35, 1.7)))
        for cost, turn, push in tries:
            ax = axis + math.radians(turn)
            dists = [(r2 if k % 2 else r) * push for k in range(n)]
            pos = [(anchor[0] + d * math.cos(ax + o), anchor[1] + d * math.sin(ax + o)) for d, o in zip(dists, offs)]
            pen = self._fan_penalty(pos, cs, taken)
            if best is None or (round(pen / 4), cost) < best[0]:
                best = ((round(pen / 4), cost), ax, dists, pos, pen)
            if pen < 4:
                break
        _, ax, dists, pos, pen = best
        half = (n - 1) * step / 2 + math.asin(min(1.0, cs * 0.6 / dists[0])) + math.radians(6)
        return ax, offs, dists, pos, step, min(half, math.radians(85)), max(dists) + cs * 0.75, pen

    def _fan_penalty(self, pos, cs, taken):
        """How badly fan slots at pos overlap discs in taken and leave the work area (pixels). Leaving it
        counts four times over."""
        rc = cs * 0.56 + 4 * self.scale
        pen = 0.0
        for px, py in pos:
            for tx, ty, tr in taken:
                pen += max(0.0, rc + tr - math.hypot(px - tx, py - ty))
            if self.work is not None:
                l, t = self.work.left - self.cs[0], self.work.top - self.cs[1]
                r, b = self.work.right - self.cs[0], self.work.bottom - self.cs[1]
                e, lab = cs * 0.62, cs * 0.62 + 20 * self.scale
                pen += 4 * (max(0.0, l - (px - e)) + max(0.0, px + e - r) + max(0.0, t - (py - e))
                            + max(0.0, py + lab - b))
        return pen

    def _fan_art(self, menu, upto=None):
        """(sprites, labels) of a fan's slots, rendered once per menu (upto: stop after that many)."""
        art = self._art.setdefault(menu.id, [])
        sizes = self._fan_sizes(menu)
        look = self._look_for(menu)
        while len(art) < len(menu.items) and (upto is None or len(art) < upto):
            it = menu.items[len(art)]
            cs = sizes[len(art)]
            art.append((self._slot_sprites(it, cs, look), self._label_sprites(it, cs, look)))
        return art

    def _warm_step(self):
        """Renders one fan slot ahead of time (called while idle). False when there is nothing left."""
        if self._warm is None:                     # fans reachable from here, nearest first
            self._warm, seen, frontier = [], {self.menu.id}, [self.items]
            for _ in range(FAN_DEPTH):
                nxt = []
                for items in frontier:
                    for it in items:
                        m = self._submenu(it.data.get("menu")) if it.kind == "menu" else None
                        if m is not None and getattr(m, "fan", False) and m.items and m.id not in seen:
                            seen.add(m.id)
                            self._warm.append(m)
                            nxt.append(m.items)
                frontier = nxt
        while self._warm:
            m = self._warm[0]
            done = len(self._art.get(m.id, ()))
            if done >= len(m.items):
                self._warm.pop(0)
                continue
            self._fan_art(m, upto=done + 1)
            return True
        return False

    def _set_open(self, path, now):
        path, cur = tuple(path), tuple(self.open)
        if path == cur:
            return
        for k in range(1, len(path) + 1):
            fan = self._fan(path[:k])
            if cur[:k] != path[:k]:                # newly opened: animate in from its slot
                fan.t_open = now
                fan.hv = [[0.0, 0.0, 0.0] for _ in fan.items]
        self.open = list(path)
        self._out_t = None
        self._relayout()
        self._apply_hover(now)

    def _update_open(self, path, how, now):
        """Opens and closes fans as the cursor moves: onto a fan submenu's slot opens it, onto anything else
        closes what hangs below it at once, and leaving a fan closes it after FAN_GRACE."""
        cur = tuple(self.open)
        if how == "disc":
            keep = self._fannable(path) and (self.cfg.get("hover_submenus", True) or cur[:len(path)] == path)
            want, now_ = (path if keep else path[:-1]), True
        elif how == "sector":                      # on the angle of a ring slot, off its disc
            want = path if cur[:1] == path else ()
            now_ = not want
        elif how == "wedge":
            want, now_ = path, False
        else:
            want, now_ = (), False
        if want == cur:
            self._out_t = None
        elif now_ or want[:len(cur)] == cur:
            self._set_open(want, now)
        elif self._out_t is None:
            self._out_t = now
        elif now - self._out_t >= FAN_GRACE:
            self._set_open(want, now)

    def _flick_or_hand_off(self, x, y, path, how):
        """Flicks out past a slot and submenu slots reached on hover. True when the ring finished."""
        flick, hover_sub = self.cfg.get("flick", True), self.cfg.get("hover_submenus", True)
        if how == "disc":
            it = self._item(path)
            if it.kind == "menu" and hover_sub and not self._fannable(path):
                self._finish(it, "hover", self._node_screen(path))
                return True
            return False
        rx, ry = x - self.centre[0], y - self.centre[1]
        if self.open:
            k = self._fan_flick(rx, ry)
            if k is not None:
                return self._flicked(tuple(self.open) + (k,), flick, hover_sub)
        if how == "sector" and math.hypot(rx, ry) >= self.flick_at[path[0]]:
            return self._flicked(path, flick, hover_sub)
        return False

    def _flicked(self, path, flick, hover_sub):
        if self._fannable(path):                   # going out past a fan submenu opens it
            if (flick or hover_sub) and tuple(self.open[:len(path)]) != path:
                self._set_open(path, time.time())
            return False
        if not flick or self._item(path).kind in ("auto", "tag", "empty"):   # empty slots: nothing to pick
            return False
        self._finish(self._item(path), "flick", self._node_screen(path))
        return True

    # --- sprites ---------------------------------------------------------------------------------
    def _prepare(self):
        lk = self.look
        self.c_bg, self.c_accent, self.c_hi = lk.bg, lk.accent, lk.hi
        self.c_text, self.c_lines, self.c_hub = lk.text, lk.lines, lk.hub_color
        self.pre = lk.pre                                                  # the theme's pill, hint, badge, placeholder
        self.f_glyph = _font(int(15 * self.scale * SS))
        t0 = time.perf_counter()
        key = self._sprite_key()
        cached = _sprite_get(key)
        hit = cached is not None
        if not hit:
            per = [_slot_get(self._slot_key(it, self.sizes[i]),
                             lambda it=it, i=i: (self._slot_sprites(it, self.sizes[i]),
                                                 self._label_sprites(it, self.sizes[i])))
                   for i, it in enumerate(self.items)]
            cached = ([p[0] for p in per], [p[1] for p in per], self._dot_sprite())
            _sprite_put(key, cached)
        self.sprites, self.labels, self._dot = cached
        ms = (time.perf_counter() - t0) * 1000
        self._log(f"ring '{self.menu.id}' sprites " + (f"from cache ({ms:.0f} ms)" if hit else f"built in {ms:.0f} ms"))
        self._static_cache = None
        self._base_cache = None
        self.hv = [[0.0, 0.0, 0.0] for _ in self.items]       # per slot: from, to, t0
        self._blend_cache = {}

    def _icon(self, it):
        """The icon image of an item (or None), asked of icon_for once per ring."""
        if id(it) not in self._icons:
            try:
                self._icons[id(it)] = self.icon_for(it)
            except Exception:
                self._icons[id(it)] = None
        return self._icons[id(it)]

    def _sprite_key(self):
        """What the ring's sprites are drawn from: the menu, each item's look (its icon by content, since a
        thumbnail can turn up later), and every setting that reaches a sprite."""
        items = tuple((_item_sig(it), _icon_sig(self._icon(it)),
                       self._fans_out(it) if it.kind == "menu" else False) for it in self.items)
        hub = None
        if self.look.hub > 0 and self.look.hub_style == "icon":
            hub = (getattr(self.menu, "icon", "") or "", self.menu.title, _icon_sig(self._hub_icon()))   # the menu's icon
        return self.menu.id, items, self.look.sig, self.scale, hub

    def _slot_key(self, it, size):
        """What one slot's sprites and label are drawn from: the item, its icon by content, whether it fans out,
        its width, and the ring's look, scale and slot size."""
        return (_item_sig(it), _icon_sig(self._icon(it)), self._fans_out(it) if it.kind == "menu" else False,
                size, self.look.sig, self.scale, self.slot)

    def _slot_sprites(self, it, size=None, look=None):
        """(idle, hover) RGBA sprites, drawn at the 1.12x hover size so scaling always reduces. size: the slot's
        width (a fan's is smaller than the ring's); look: the ring's or fan's look (None: this ring's)."""
        L = look or self.look
        st = _style(it)
        s = SS
        shape, corner = self._shape_of(it, L)
        D = (size or self.slot) * 1.12 * s         # disc diameter at full hover size, supersampled
        m = 30 * self.scale * s                    # margin for ring + glow
        C = int(D + 2 * m + shapes.pad_extra(shape, D))
        c = C / 2
        if it.kind == "empty":                     # a slot that holds nothing: a faint outline, the same on hover
            im = Image.new("RGBA", (C, C), (0, 0, 0, 0))
            shapes.draw(ImageDraw.Draw(im), shape, c, c, D / 2, corner, outline=_rgba(L.text, 0.22),
                        width=max(1, int(1.5 * self.scale * s)))
            out = im.resize((int(C / s), int(C / s)), Image.LANCZOS)
            return out, out
        sub = it.kind == "menu"
        fan = sub and self._fans_out(it)
        more = _is_more(it) and not getattr(it, "icon", "")
        col = _chrome(it, L)
        glow_own = _role(st.get("glow_color"), L.colors) or getattr(it, "glow", "")   # the slot's own glow colour
        hue = glow_own or col or L.glow_color or (L.hi if sub else L.accent)   # a glow colour of its own wins
        mode = L.tag_colors
        tint = bool(col) and (mode in ("tint", "both") or bool(it.tag))
        glow_a = L.tag_glow_opacity
        halo_col = glow_own or col
        soft = bool(halo_col) and mode in ("glow", "both") and glow_a > 0
        go = L.glow_opacity
        base = _role(st.get("fill_color"), L.colors) or L.bg
        rim = _role(st.get("border_color"), L.colors)
        bw = _num(st.get("border_width"), L.border_width, 0, 6)
        text = L.text
        icon = self._icon(it)
        ins = int((D - 16 * 1.12 * self.scale * s) * _num(st.get("icon_scale"), L.icon_scale, 0.5, 1.0))
        if icon is not None:
            icon = icon.convert("RGBA").resize((ins, ins), Image.LANCZOS)
            icon.putalpha(ImageChops.multiply(icon.getchannel("A"), shapes.icon_mask(shape, ins, corner)))
            amount = L.tag_tint_opacity
            if col and mode in ("tint", "both") and amount > 0:
                icon = _tint_icon(icon, col, amount, L.tag_tint_style, L.tag_tint_blend)
        solid = bool(col) and bool(it.tag) and sub and icon is None   # a tag slot: solid disc in the tag colour
        fill = _mix(base, col, 0.6) + (255,) if solid else (
            _mix(base, col, 0.45) + (235,) if tint else _rgba(base, 0.92))

        def disc(hover):
            im = Image.new("RGBA", (C, C), (0, 0, 0, 0))
            if hover:                              # glow + soft outer ring
                glow = Image.new("RGBA", (C, C), (0, 0, 0, 0))
                shapes.draw(ImageDraw.Draw(glow), shape, c, c, D / 2, corner, grow=4 * self.scale * s,
                            fill=_rgba(hue, go))
                glow = glow.filter(ImageFilter.GaussianBlur(12 * self.scale * s))
                im.alpha_composite(glow)
                shapes.draw(ImageDraw.Draw(im), shape, c, c, D / 2, corner, grow=3 * self.scale * s,
                            fill=_rgba(hue, 0.20 * go / 0.55))
            d = ImageDraw.Draw(im)
            r = D / 2
            border = _rgba(hue, 1.0) if hover else (_rgba(rim, 0.9) if rim else (
                _rgba(col, 0.9) if tint else _rgba(text, 0.10)))
            wv = max(2, bw) if hover else (bw + 1 if tint and bw > 0 else bw)    # a tinted idle rim is a step wider
            if wv > 0:
                shapes.draw(d, shape, c, c, r, corner, fill=fill, outline=border,
                            width=max(1, int(wv * self.scale * s)))
            else:                                  # no rim
                shapes.draw(d, shape, c, c, r, corner, fill=fill)
            if icon is not None:
                im.alpha_composite(icon, (int(c - ins / 2), int(c - ins / 2)))
            elif it.kind == "auto":                # an auto slot nothing has filled yet: faint, no disc
                gd = ImageDraw.Draw(im)
                l, t_, r_, b_ = gd.textbbox((0, 0), "+", font=self.f_glyph)
                gd.text((c - (r_ - l) / 2 - l, c - (b_ - t_) / 2 - t_), "+", font=self.f_glyph,
                        fill=_rgba(text, 0.35))
            elif it.kind == "tag":                 # a tag with no brushes (or no such tag): faint, no tint
                glyph = _glyph_star if it.tag == tags.FAVOURITE else _glyph_tag
                glyph(ImageDraw.Draw(im), c, c, ins * 0.42, _rgba(it.color or text, 0.35))
            elif solid:                            # tag slot: the disc is the tag colour
                glyph = _glyph_star if it.tag == tags.FAVOURITE else _glyph_tag
                glyph(ImageDraw.Draw(im), c, c, ins * 0.46, _rgba(text, 0.9))
            else:                                  # placeholder disc with a short glyph
                self._placeholder(im, shape, corner, c, ins / 2, L)
                gd = ImageDraw.Draw(im)
                if it.kind == "browser":           # the browser: a 2x2 grid
                    _glyph_grid(gd, c, c, ins * 0.46, _rgba(it.color or text, 0.95))
                elif more:                         # a More slot: three dots
                    _glyph_more(gd, c, c, ins * 0.5, _rgba(text, 0.9))
                else:
                    self._monogram(gd, it.label, c, text)
            if sub and not more:                   # submenu badge, bottom-right: a fan, or an arrow for a ring
                u = self.scale * s
                bw_ = 14 * u
                bx = by = c + r * shapes.badge(shape)   # a square's corner is further out than a circle's edge
                d.rounded_rectangle((bx - bw_ / 2, by - bw_ / 2, bx + bw_ / 2, by + bw_ / 2), radius=4 * u,
                                    fill=L.pre["badge"], outline=_rgba(L.hi, 1.0), width=max(1, int(u)))
                if fan:
                    _glyph_fan(d, bx - 4 * u, by + 4 * u, 8 * u, _rgba(L.hi, 1.0))
                else:
                    tri = 3.5 * u
                    d.polygon([(bx - tri * 0.7, by - tri), (bx - tri * 0.7, by + tri), (bx + tri, by)],
                              fill=_rgba(L.hi, 1.0))
            out = im.resize((int(C / s), int(C / s)), Image.LANCZOS)
            if soft and not hover:                 # soft halo in the glow or tag colour, blurred at 1x
                n = out.size[0]
                halo = Image.new("RGBA", (n, n), (0, 0, 0, 0))
                shapes.draw(ImageDraw.Draw(halo), shape, n / 2, n / 2, D / 2 / s, corner, grow=2 * self.scale,
                            fill=_rgba(halo_col, glow_a))
                halo = halo.filter(ImageFilter.GaussianBlur(8 * self.scale))
                halo.alpha_composite(out)
                out = halo
            return out
        return disc(False), disc(True)

    def _placeholder(self, im, shape, corner, c, pr, L):
        """A placeholder disc (a cheap radial gradient in the theme's colours) of half width pr, into im."""
        ph = Image.new("RGBA", im.size, (0, 0, 0, 0))
        pd = ImageDraw.Draw(ph)
        for k in range(12, 0, -1):
            t = k / 12
            g = tuple(int(a + (b - a) * (1 - t)) for a, b in zip(*L.pre["placeholder"]))
            shapes.draw(pd, shape, c, c, pr * t, corner, fill=g + (255,))
        im.alpha_composite(ph)

    def _monogram(self, gd, label, c, text):
        """A short glyph for a slot with no picture: the label when it is short, else its first two initials."""
        glyph = label if len(label) <= 4 else "".join(w[0] for w in label.split()[:2]).upper()
        gf = _font_for(glyph, int(15 * self.scale * SS))
        l, t_, r_, b_ = gd.textbbox((0, 0), glyph, font=gf)
        gd.text((c - (r_ - l) / 2 - l, c - (b_ - t_) / 2 - t_), glyph, font=gf, fill=_rgba(text, 0.9))

    def _label_sprites(self, it, size=None, look=None):
        """(idle, hover) label sprites: the name on a soft pill in the theme's colour, so it reads over a neighbouring disc."""
        L = look or self.look
        if L.labels == "none" or it.kind == "empty":
            return None
        s = SS
        font = _font_for(it.label, int(11 * self.scale * s))
        tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        text = _shorten(tmp, it.label, font, (size or self.slot) * 1.9 * s)
        l, _, r, _ = tmp.textbbox((0, 0), text, font=font, anchor="ls")          # anchor: left of the baseline
        top, bottom = tmp.textbbox((0, 0), "Åg", font=font, anchor="ls")[1::2]   # one line height for every label
        pad = int(6 * self.scale * s)
        Wd, Hd = r - l + 2 * pad, bottom - top + 2 * pad
        hx, vy = 5 * self.scale * s, 2 * self.scale * s                          # how far the pill reaches past the text
        pill = (pad - hx, pad - vy, Wd - pad + hx, Hd - pad + vy)
        idle = _role(_style(it).get("label_color"), L.colors) or L.label_color   # a slot's own name colour wins
        out = []
        for hover in (False, True):
            hue = (_chrome(it, L) or (L.hi if it.kind == "menu" else L.accent)) if hover else idle
            im = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle(pill, radius=(pill[3] - pill[1]) / 2, fill=L.pre["pill"])
            d.text((pad - l, pad - top), text, font=font, fill=_rgba(hue, 1.0), anchor="ls")
            out.append(im.resize((max(1, int(Wd / s)), max(1, int(Hd / s))), Image.LANCZOS))
        return out

    def _hub(self):
        """The centre dot's diameter in unscaled px (0 = none)."""
        return self.look.hub

    def _hub_icon(self):
        """The menu's icon image for a hub of style "icon" (None: no icon, or none found), asked of icon_for once."""
        if self._hub_img is None:
            img = None
            icon = getattr(self.menu, "icon", "") or ""
            if icon:
                import config as C
                try:
                    img = self.icon_for(C.Item(label=self.menu.title, kind="menu", data={"menu": self.menu.id},
                                               icon=icon))
                except Exception:
                    img = None
            self._hub_img = (img,)
        return self._hub_img[0]

    def _dot_sprite(self, look=None):
        """The centre hub: a dot, a disc, a ring or the menu's icon, in the hub colour with a soft glow (None: no hub)."""
        L = look or self.look
        if L.hub <= 0:
            return None
        s = SS
        k = L.hub / 10                             # margin and blur follow the size; 10 px is the original look
        d = 10 * self.scale * s * k
        m = 14 * self.scale * s * k
        C = int(d + 2 * m)
        c = C / 2
        hc, style = L.hub_color, L.hub_style
        rim = max(1, int(round(max(1.0, 0.12 * L.hub) * self.scale * s)))
        box = (c - d / 2, c - d / 2, c + d / 2, c + d / 2)
        im = Image.new("RGBA", (C, C), (0, 0, 0, 0))
        if L.hub_glow > 0:
            g = Image.new("RGBA", (C, C), (0, 0, 0, 0))
            gd = ImageDraw.Draw(g)
            if style == "ring":
                gd.ellipse(box, outline=_rgba(hc, 0.9 * L.hub_glow), width=rim)
            else:
                gd.ellipse(box, fill=_rgba(hc, 0.9 * L.hub_glow))
            im.alpha_composite(g.filter(ImageFilter.GaussianBlur(5 * self.scale * s * k * L.hub_glow)))
        draw = ImageDraw.Draw(im)
        if style == "dot":
            draw.ellipse(box, fill=_rgba(hc, 1.0))
        elif style == "ring":
            draw.ellipse(box, outline=_rgba(hc, 1.0), width=rim)
        else:                                      # disc, or the menu's icon on a disc
            draw.ellipse(box, fill=_rgba(L.bg, 0.92), outline=_rgba(hc, 1.0), width=rim)
            if style == "disc":                    # the surface of an untinted slot, so it reads as a disc, not a ring
                self._placeholder(im, "circle", SLOT_CORNER, c, d / 2 - rim, L)
            if style == "icon":
                self._hub_face(im, L, c, int(d) - 2 * rim)
        return im.resize((max(1, int(C / s)),) * 2, Image.LANCZOS)

    def _hub_face(self, im, L, c, ins):
        """The hub icon style's face, into im: the menu's icon in a circle, or a monogram of its title."""
        if ins < 2:
            return
        img = self._hub_icon()
        if img is not None:
            face = img.convert("RGBA").resize((ins, ins), Image.LANCZOS)
            face.putalpha(ImageChops.multiply(face.getchannel("A"), shapes.icon_mask("circle", ins)))
            im.alpha_composite(face, (int(c - ins / 2), int(c - ins / 2)))
            return
        self._placeholder(im, "circle", SLOT_CORNER, c, ins / 2, L)
        title = self.menu.title
        glyph = title if len(title) <= 4 else "".join(w[0] for w in title.split()[:2]).upper()
        f = _font_for(glyph, max(6, int(ins * 0.42)))
        gd = ImageDraw.Draw(im)
        l, t_, r_, b_ = gd.textbbox((0, 0), glyph, font=f)
        gd.text((c - (r_ - l) / 2 - l, c - (b_ - t_) / 2 - t_), glyph, font=f, fill=_rgba(L.text, 0.9))

    def _fan_lines(self, anchor, anchor_r, pos, sizes, color="", look=None):
        """Dashed lines from a fan's slot out to each of its slots (sizes: their widths), in color if it has one,
        else the lines colour of the fan's look: (image, top-left relative to the ring centre)."""
        s = SS
        m = 4 * self.scale
        xs, ys = [anchor[0]] + [p[0] for p in pos], [anchor[1]] + [p[1] for p in pos]
        x0, y0 = math.floor(min(xs) - m), math.floor(min(ys) - m)
        w, h = math.ceil(max(xs) + m) - x0, math.ceil(max(ys) + m) - y0
        im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        col = _rgba(color or (look or self.look).lines, 0.75)
        lw = max(1, int(1.3 * self.scale * s))
        dash, gap = 5 * self.scale, 4 * self.scale
        ax, ay = anchor
        for (px, py), cs in zip(pos, sizes):
            L = math.hypot(px - ax, py - ay)
            if L < 1:
                continue
            ux, uy = (px - ax) / L, (py - ay) / L
            t, t1 = anchor_r * 1.12 + 2 * self.scale, L - cs * 0.56 - 2 * self.scale
            while t < t1:
                te = min(t1, t + dash)
                d.line(((ax + ux * t - x0) * s, (ay + uy * t - y0) * s, (ax + ux * te - x0) * s,
                        (ay + uy * te - y0) * s), fill=col, width=lw)
                t = te + gap
        return im.resize((w, h), Image.LANCZOS), (x0, y0)

    def _static(self):
        """Guide rings, spokes, title and hint (no dot, no slots) on the ring's own square. Cached per hint
        text."""
        if self._static_cache is not None:
            return self._static_cache
        s = SS
        S = self.rsize * s
        cx = cy = self.rsize // 2 * s
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        hit = self.hit_r * s                       # invisible disc so clicks land on us
        d.ellipse((cx - hit, cy - hit, cx + hit, cy + hit), fill=(0, 0, 0, 1))
        lw = max(1, int(self.scale * s))
        self._band(im, cx, cy)
        for frac, a in ((0.28, 0.05), (0.52, 0.03), (0.76, 0.02)):
            r = self.R * frac * s
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=_rgba(self.c_lines, a), width=lw)
        # spokes start at the hub's edge; under a solid dot they were always hidden, so a dot keeps today's 8 px
        r0 = (8 if self.look.hub_style == "dot" else max(8, self._hub() / 2 + 3)) * self.scale * s
        rings = self.plan.rings
        for i, ((ux, uy), it, rad, size) in enumerate(zip(self.seats, self.items, self.rad, self.sizes)):
            if it.kind == "empty":                  # nothing to point at
                continue
            r1 = (rad - size / 2 - 6 * self.scale) * s
            start = r0
            if self.plan.seats[i].ring > 0:         # an outer slot's spoke starts just outside the ring before it
                inner = rings[self.plan.seats[i].ring - 1]
                start = (inner.radius + max(self.sizes[inner.first:inner.first + inner.n]) / 2 + 6 * self.scale) * s
                if r1 - start < 4 * self.scale * s:
                    continue
            colr = _rgba(_chrome(it, self.look), 0.35) if _chrome(it, self.look) else (
                _rgba(self.c_hi, 0.35) if it.kind == "menu" else _rgba(self.c_lines, 0.30))
            d.line((cx + ux * start, cy + uy * start, cx + ux * r1, cy + uy * r1), fill=colr, width=lw)
        for text, font, dy, colr in self._caption(d):
            l, t, r_, b = d.textbbox((0, 0), text, font=font)
            d.text((cx - (r_ - l) / 2 - l, cy + dy * self.scale * s - (b - t) / 2 - t), text, font=font, fill=colr)
        self._static_cache = im.resize((self.rsize, self.rsize), Image.LANCZOS)
        return self._static_cache

    def _hint_lines(self):
        """The hint for the ring's state as candidates, longest first: each a tuple of lines. None when the
        ring's hint setting is off."""
        if not self.cfg.get("hint", True):
            return []
        if not self._armed:
            return [("move into the ring",)]
        if self.mode == "hold":
            if self.cfg.get("flick", True):
                return [("release or flick to pick",), ("release to pick",)]
            return [("release to pick",)]
        return [("click a slot, centre or right-click cancels",), ("click a slot,", "centre or right-click cancels"),
                ("click to cancel",)]

    def _caption(self, d):
        """[(text, font, dy, colour)] for the title and the hint, dy in unscaled pixels below the centre. Both
        stay inside the free circle (inside the slot discs) whatever the ring's size: the title shrinks and
        then loses letters, the hint tries its shorter wordings and smaller sizes and is left out when none
        fits, so a small ring never has text across its slots or its centre dot."""
        s = SS
        # radius of the space inside the discs
        free = min(self.rad[i] - self.sizes[i] * 0.62 for i in range(self.n)) - 4 * self.scale

        def room(dy):                                              # width of that space at dy, supersampled
            return 2 * math.sqrt(max(0.0, free * free - (dy * self.scale) ** 2)) * s

        def width(text, font):
            box = d.textbbox((0, 0), text, font=font)
            return box[2] - box[0]
        out = []
        push = max(0.0, self._hub() / 2 - 5)                       # a dot bigger than the default 5 px radius
        ty = 18 + push                                             # pushes the text down to keep its gap
        title = self.menu.title.upper()
        for px in (9, 8, 7):
            font = _font_for(title, int(px * self.scale * s))
            text = " ".join(title)                                 # letter-spaced caps
            if width(text, font) <= room(ty):
                break
        else:
            while len(title) > 1 and width(" ".join(title + "…"), font) > room(ty):
                title = title[:-1]
            text = " ".join(title + "…")
        if width(text, font) <= room(ty):                          # a huge dot in a small ring leaves no room
            out.append((text, font, ty, _rgba(self.c_accent, 0.85)))
        for lines in self._hint_lines():
            for px in (10, 9, 8, 7):
                fonts = [_font_for(t, int(px * self.scale * s)) for t in lines]
                dys = [30 + push + 11 * k for k in range(len(lines))]
                if all(width(t, f) <= room(dy) for t, f, dy in zip(lines, fonts, dys)):
                    return out + [(t, f, dy, self.pre["hint"]) for t, f, dy in zip(lines, fonts, dys)]
        return out

    def _band(self, im, cx, cy):
        """The tag band (supersampled, into im): a ring through the slot centres, each slot's stretch of it in
        its colour and the rest faint."""
        width = TAG_BANDS.get(self.look.tag_band)
        cols = [_chrome(it, self.look) for it in self.items]
        if width is None or not any(cols):
            return
        a = self.look.tag_band_opacity
        s = SS
        w = max(2 * self.scale, self.slot * width) * s
        for rp in self.plan.rings:                 # one band per ring, through its slot centres
            band = Image.new("RGBA", im.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(band)               # fills replace, so each stretch overwrites the faint base
            ro, ri = rp.radius * s + w / 2, rp.radius * s - w / 2
            d.ellipse((cx - ro, cy - ro, cx + ro, cy + ro), fill=_rgba(self.c_text, a * 0.2))
            half = min(rp.step, MAX_SECTOR) / 2
            for j in range(rp.n):
                col = cols[rp.first + j]
                if col:
                    mid = rp.offset + rp.step * j - 90      # Pillow's 0 is 3 o'clock, ours 12
                    d.pieslice((cx - ro, cy - ro, cx + ro, cy + ro), mid - half, mid + half, fill=_rgba(col, a))
            d.ellipse((cx - ri, cy - ri, cx + ri, cy + ri), fill=(0, 0, 0, 0))
            im.alpha_composite(band)

    def _base(self, el):
        """A fresh canvas holding the invisible hit surface of the open fans and the ring's static layer
        (which fades in over the first 100 ms)."""
        fading = self.anim["dur"] > 0 and el < 100
        key = (self.mode, tuple(self.open), self.size, self._armed)
        if not fading and self._base_cache is not None and self._base_cache[0] == key:
            return self._base_cache[1].copy()
        canvas = Image.new("RGBA", self.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(canvas)
        cx, cy = self.centre
        for fan in self._open_fans():              # alpha 1 at 1x, so clicks between fan slots land on us
            ax, ay = cx + fan.anchor[0], cy + fan.anchor[1]
            arc = [fan.axis + fan.half * (j / 8 - 1) for j in range(17)]
            d.polygon([(ax, ay)] + [(ax + fan.reach * math.cos(a), ay + fan.reach * math.sin(a)) for a in arc],
                      fill=(0, 0, 0, 1))
            for (px, py), cs in zip(fan.pos, fan.csizes):
                r = cs * 0.62 + 6 * self.scale
                d.ellipse((cx + px - r, cy + py - r, cx + px + r, cy + py + r), fill=(0, 0, 0, 1))
        static = self._static()
        if fading:
            faded = _fade(static, max(0.0, el / 100))
            layer = faded.copy() if faded is not None else Image.new("RGBA", static.size, (0, 0, 0, 0))
            layer.putalpha(ImageChops.lighter(layer.getchannel("A"), static.getchannel("A").point(
                lambda v: 1 if v else 0)))                      # keep the invisible click disc
        else:
            layer = static
        hr = self.rsize // 2
        _blit(canvas, layer, cx - hr, cy - hr)
        if fading:
            return canvas
        self._base_cache = (key, canvas)
        return canvas.copy()

    # --- animation -------------------------------------------------------------------------------
    def _open_ms(self):
        a = self.anim
        tail = max(a["dur"], a["fade"], a.get("blur_ms", 0), 420 if a.get("dot_pop") else 0)
        return a["stagger"] * max(0, self.n - 1) + tail + 40

    def _set_hover(self, idx, now, instant=False):
        self.hover = None if idx is None else (idx,)
        self._apply_hover(now, instant)

    def _apply_hover(self, now, instant=False):
        """Eases every slot toward its look: hovered if it is under the cursor or on the open path."""
        marks = set()
        for p in (self.hover or (), tuple(self.open)):
            marks.update(tuple(p[:k]) for k in range(1, len(p) + 1))
        for base, hv in [((), self.hv)] + [(f.path, f.hv) for f in self._open_fans()]:
            for i, h in enumerate(hv):
                target = 1.0 if base + (i,) in marks else 0.0
                if h[1] != target:
                    hv[i] = [self._hover_val(hv, i, now), target, now - (10 if instant else 0)]

    @staticmethod
    def _hover_val(hv, i, now):
        f, to, t0 = hv[i]
        p = min(1.0, max(0.0, (now - t0) * 1000 / HOVER_MS))
        return f + (to - f) * EASE(p)

    def _slot_state(self, i, now):
        """(scale, alpha, dx, dy, rot, blur) for slot i at time now."""
        a = self.anim
        el = (now - self.t0) * 1000 - a["stagger"] * i
        if a["dur"] <= 0:
            return 1.0, 1.0, 0.0, 0.0, 0.0, 0.0
        p = min(1.0, max(0.0, el / a["dur"]))
        e = self.curve(p)
        alpha = min(1.0, max(0.0, el / a["fade"])) if a["fade"] else 1.0
        sc = a["scale"] + (1.0 - a["scale"]) * e
        travel = a.get("travel", 0.0) * (1.0 - e)
        ux, uy = self.seats[i]
        dx, dy = -ux * self.rad[i] * travel, -uy * self.rad[i] * travel
        dy += a.get("drift", 0) * self.scale * (1.0 - e)
        rot = a.get("rot", 0) * (1.0 - e)
        blur = 0.0
        if a.get("blur"):
            bp = min(1.0, max(0.0, el / a["blur_ms"]))
            blur = a["blur"] * self.scale * (1.0 - EASE_OUT(bp))
        return sc, alpha, dx, dy, rot, blur

    def _animating(self, now):
        if (now - self.t0) * 1000 < self._open_ms() + (1000 if self.anim.get("ripples") else 0):
            return True
        fans = self._open_fans()
        if any((now - f.t_open) * 1000 < f.total + 20 for f in fans):
            return True
        return any(h[1] != self._hover_val(hv, i, now)
                   for hv in [self.hv] + [f.hv for f in fans] for i, h in enumerate(hv))

    def _compose(self, now):
        el = (now - self.t0) * 1000
        a = self.anim
        canvas = self._base(el)
        cx, cy = self.centre
        if a.get("halo"):                          # breath: soft accent halo grows behind the dot
            p = EASE_OUT(min(1.0, el / 900))
            if p > 0.01:
                rad = 120 * self.scale * p
                halo = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
                ImageDraw.Draw(halo).ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=_rgba(self.c_hub, 0.12))
                canvas.alpha_composite(halo.filter(ImageFilter.GaussianBlur(rad * 0.35 + 1)))
        if a.get("ripples"):                       # two accent rings expanding from the dot
            d = ImageDraw.Draw(canvas)
            for delay in (0, 140):
                p = (el - delay) / 1000
                if 0 < p < 1:
                    rr = max(5, self._hub() / 2) * self.scale * (0.1 + 23.9 * EASE_OUT(p))
                    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=_rgba(self.c_hub, 0.9 * (1 - p)),
                              width=max(1, int(1.5 * self.scale)))
        ds = 1.0
        if a.get("dot_pop"):                       # 0 -> 1.35 -> 1 over 420 ms
            p = min(1.0, el / 420)
            ds = 1.35 * EASE_OUT(p / 0.6) if p < 0.6 else 1.35 - 0.35 * EASE((p - 0.6) / 0.4)
        if ds > 0.02 and self._dot is not None:    # None: hub 0, no dot
            dot = self._dot
            k = max(1, int(dot.size[0] * ds))
            dd = dot if k == dot.size[0] else dot.resize((k, k), Image.BILINEAR)
            _blit(canvas, dd, cx - k / 2, cy - k / 2)
        order = sorted(range(self.n), key=lambda i: self.hv[i][1])  # hovered slot drawn last (on top)
        labels = []
        for i in order:                            # every disc first, then every label, so no disc covers a name
            sc, alpha, dx, dy, rot, blur = self._slot_state(i, now)
            ux, uy = self.seats[i]
            px, py, h = cx + ux * self.rad[i] + dx, cy + uy * self.rad[i] + dy, self._hover_val(self.hv, i, now)
            self._draw_disc(canvas, ((), i), self.sprites[i], px, py, sc, alpha, h, rot, blur)
            labels.append((self.labels[i], px, py, sc, alpha, h, self.sizes[i]))
        for args in labels:
            self._draw_label(canvas, *args)
        for fan in self._open_fans():
            self._draw_fan(canvas, fan, now)
        return canvas

    def _draw_fan(self, canvas, fan, now):
        """A fan's lines and slots; the slots grow out of the slot it opened from."""
        el = (now - fan.t_open) * 1000
        dur, fade, stagger, curve = fan.motion
        cx, cy = self.centre
        ax, ay = fan.anchor
        im, (lx, ly) = fan.lines
        im = _fade(im, min(1.0, el / fade) if fade else 1.0)
        if im is not None:
            _blit(canvas, im, cx + lx, cy + ly)
        labels = []
        for k in sorted(range(len(fan.items)), key=lambda j: fan.hv[j][1]):
            e, alpha = 1.0, 1.0
            if dur > 0:
                ek = el - stagger * k
                e = curve(min(1.0, max(0.0, ek / dur)))
                alpha = min(1.0, max(0.0, ek / fade))
            px, py = cx + ax + (fan.pos[k][0] - ax) * e, cy + ay + (fan.pos[k][1] - ay) * e
            sc, h = 0.6 + 0.4 * e, self._hover_val(fan.hv, k, now)
            self._draw_disc(canvas, (fan.path, k), fan.sprites[k], px, py, sc, alpha, h, 0, 0.0)
            labels.append((fan.labels[k], px, py, sc, alpha, h, fan.csizes[k]))
        for args in labels:
            self._draw_label(canvas, *args)

    def _draw_disc(self, canvas, key, sprites, px, py, sc, alpha, h, rot, blur):
        """One slot's disc centred on px, py. key: blend cache key of that slot."""
        if alpha <= 0.001:
            return
        idle, hov = sprites
        hk = round(h, 2)
        if hk <= 0.0:
            spr = idle
        elif hk >= 1.0:
            spr = hov
        else:
            spr = self._blend_cache.get((key, hk))
            if spr is None:
                spr = Image.blend(idle, hov, hk)
                self._blend_cache[(key, hk)] = spr
        k = sc * (1.0 + 0.12 * h) / 1.12
        w0 = spr.size[0]
        wk = max(1, int(w0 * k))
        if wk != w0:
            spr = spr.resize((wk, wk), Image.BILINEAR)
        if rot:
            spr = spr.rotate(rot, resample=Image.BILINEAR)
        if blur > 0.3:
            spr = spr.filter(ImageFilter.GaussianBlur(blur))
        spr = _fade(spr, alpha)
        if spr is not None:
            _blit(canvas, spr, px - wk / 2, py - wk / 2)

    def _draw_label(self, canvas, labels, px, py, sc, alpha, h, slot):
        """The name under the slot centred on px, py (slot: its width at rest)."""
        if labels is None or alpha <= 0.001:
            return
        lab = Image.blend(*labels, h) if 0 < h < 1 else labels[1 if h >= 1 else 0]
        lab = _fade(lab, alpha)
        if lab is not None:
            ly = py + slot / 2 * (1.0 + 0.12 * h) * sc + 2 * self.scale
            _blit(canvas, lab, px - lab.size[0] / 2, ly)

    # --- window plumbing -------------------------------------------------------------------------
    def _render(self, now):
        self._push(self._compose(now))

    def _push(self, im):
        """Premultiply and hand the frame to Windows via UpdateLayeredWindow (which also moves and resizes
        the window when the open fans change)."""
        r, g, b, a = im.split()
        r, g, b = (ImageChops.multiply(ch, a) for ch in (r, g, b))
        data = Image.merge("RGBA", (r, g, b, a)).tobytes("raw", "BGRA")
        w, h = self.size
        screen = W.GetDC(None)
        try:
            if self._dib is None:
                bih = W.BITMAPINFOHEADER()
                bih.biSize = ctypes.sizeof(W.BITMAPINFOHEADER)
                bih.biWidth, bih.biHeight = w, -h     # top-down
                bih.biPlanes, bih.biBitCount = 1, 32
                bits = ctypes.c_void_p()
                hbmp = W.CreateDIBSection(screen, ctypes.byref(bih), 0, ctypes.byref(bits), None, 0)
                mem = W.CreateCompatibleDC(screen)
                old = W.SelectObject(mem, hbmp)
                self._dib = (hbmp, mem, old, bits)
            hbmp, mem, old, bits = self._dib
            ctypes.memmove(bits, data, len(data))
            blend = W.BLENDFUNCTION(W.AC_SRC_OVER, 0, 255, W.AC_SRC_ALPHA)
            pt_dst = W.w.POINT(*self.origin)
            sz = W.w.SIZE(w, h)
            pt_src = W.w.POINT(0, 0)
            W.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(pt_dst), ctypes.byref(sz), mem,
                                  ctypes.byref(pt_src), 0, ctypes.byref(blend), W.ULW_ALPHA)
        finally:
            W.ReleaseDC(None, screen)

    def _free_dib(self):
        if self._dib is not None:
            hbmp, mem, old, bits = self._dib
            W.SelectObject(mem, old)
            W.DeleteObject(hbmp)
            W.DeleteDC(mem)
            self._dib = None

    def _on_message(self, msg, wparam, lparam):
        if msg == W.WM_MOUSEACTIVATE:
            return W.MA_NOACTIVATE
        if msg == W.WM_TIMER and wparam == TIMER_TICK:
            self._tick()
            return 0
        if msg == W.WM_LBUTTONUP:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            path, how = self._hit(x, y)
            node = self._item(path) if how in ("disc", "sector") else None
            if node is not None and self._fannable(path):
                self._set_open(path, time.time())
                return 0
            if node is None and (self.mode == "hold" or how == "wedge"):
                return 0                           # stray press in the centre while holding, or between fan slots
            self._finish(node, "click")
            return 0
        if msg == W.WM_RBUTTONDOWN:
            self._finish(None, "right-click")
            return 0
        return None

    def _tick(self):
        if self.done:
            return
        now = time.time()
        if now - self.t0 > self.cfg["timeout_s"]:
            self._finish(None, "timeout")
            return
        x, y = W.cursor_pos()
        lx, ly = x - self.origin[0], y - self.origin[1]
        path, how = self._hit(lx, ly)
        over = how in ("disc", "wedge") or math.hypot(lx - self.centre[0], ly - self.centre[1]) <= self.hit_r
        if self.mode == "click" and not over and (W.key_down(W.VK_LBUTTON) or W.key_down(W.VK_RBUTTON)):
            self._finish(None, "clicked outside")
            return
        if not self._armed:
            # The ring was moved in from a screen edge, so it opened with the cursor off-centre, outside the flick
            # radius or on a slot: nothing is picked or opened by hover until the cursor has been inside and off
            # every slot.
            self._armed = how not in ("disc", "wedge") and math.hypot(
                lx - self.centre[0], ly - self.centre[1]) < self.flick_r
            if self._armed:
                self._static_cache = None          # the hint changes
        if self._armed and self._flick_or_hand_off(lx, ly, path, how):
            return
        if self._armed:
            self._update_open(path, how, now)
        hover = path if how in ("disc", "sector") else None
        if hover != self.hover:
            self.hover = hover
            self._apply_hover(now)
        key = (self.mode, self.hover, tuple(self.open), self._armed)
        if self._animating(now) or key != self._last_key:
            self._last_key = key
            self._render(now)
        elif self.submenus is not None:
            self._warm_step()

    def _finish(self, item, reason, at=None):
        if self.done:
            return
        self.done = True
        self._log(f"ring '{self.menu.id}' closed ({reason}): {item.label if item else None}")
        hwnd, self.hwnd = self.hwnd, None
        if hwnd:
            W.KillTimer(hwnd, TIMER_TICK)
            _instances.pop(int(hwnd), None)
            W.DestroyWindow(hwnd)                  # destroy, not hide: releases any pen capture
            if _winmm is not None:
                _winmm.timeEndPeriod(1)
        self._free_dib()
        self.on_done(item, reason, at)
