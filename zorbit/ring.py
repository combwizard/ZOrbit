"""The radial overlay: round icon slots on a ring, animated, in a non-activating layered window.

Look: slots of round icons around a glowing accent centre dot,
hairline spokes and faint guide rings; hover = accent border, soft ring, glow, 1.12x scale and accent label;
submenus use the highlight colour and a small badge (an arrow, or a fan for one that fans out); an auto slot nothing has filled yet is a faint "+".
Tag colours: an item that carries a colour (config.Item.color, from its first tag) gets a rim and a slightly
tinted disc, a soft halo, or both, as ring.tag_colors says; its hover border, spoke and label take the colour
too. A tag slot is a solid disc in the tag colour with a tag glyph whatever ring.tag_colors says; one with no
brushes is a faint tag glyph and nothing else of it is coloured.
All of it is drawn into the sprites when they are built, so a frame costs the same as before.
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
import math
import os
import time

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import win32 as W

SS = 3                      # supersampling for sprites (drawn large, reduced once)
TIMER_TICK = 1
CLASS_NAME = "ZOrbitRing"
HOVER_MS = 120
MAX_SECTOR = 90.0           # widest angle (degrees) a single slot answers to
FAN_SLOT = 0.86             # fan slot size, relative to a ring slot
FAN_DEPTH = 3               # fans inside fans, at most this deep
FAN_SPAN = (130.0, 110.0)   # widest arc (degrees) of a first fan and of a deeper one
FAN_TURNS = (0, 15, -15, 30, -30, 45, -45, 60, -60, 75, -75, 90, -90)   # turns tried to dodge slots and edges
FAN_MS = 220                # longest fan open animation (per slot)
FAN_GRACE = 0.12            # seconds a fan stays open after the cursor leaves it
_instances = {}
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


def _font(px: int, bold=True):
    fonts = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    for name in (("segoeuib.ttf", "seguisb.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(os.path.join(fonts, name), max(6, px))
        except OSError:
            pass
    return ImageFont.load_default()


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


def _chrome(it):
    """The colour an item's rim, spoke, hover and fan lines take: its tag colour, except for an empty tag slot,
    which stays faint all over (its colour only tints the glyph)."""
    return it.color if it.kind != "tag" else ""


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
        except Exception as e:                    # never let an exception unwind into Windows
            ring._log(f"ring error: {e!r}")
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
        self.axis, self.offs, self.dists, self.pos = axis, offs, dists, pos
        self.step, self.half, self.reach = step, half, reach   # slot spacing, wedge half-angle and length
        self.hv = [[0.0, 0.0, 0.0] for _ in self.items]
        self.t_open = 0.0
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
        self.cfg = ring_cfg
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
        self._dib = None
        self._last_key = None
        self._base_cache = None

    # --- public ----------------------------------------------------------------------------------
    @classmethod
    def preview(cls, menu, ring_cfg: dict, icon_for, hover=None, scale=1.0, t=None, submenus=None,
                open_path=None):
        """Renders the ring to a PIL RGBA image without a window (Studio). t: seconds since open, or None
        for the settled look. open_path: indices of the fans to show open (needs submenus). The ring centre
        is in im.info["centre"]: with a fan open the image is no longer square around it."""
        r = cls(menu, ring_cfg, icon_for, lambda *a: None, lambda m: None, held=False, submenus=submenus)
        r._geometry(scale)
        r._relayout()
        r._prepare()
        now = 1000.0
        r.t0 = now - (t if t is not None else 10.0)
        path = tuple(open_path or ())
        for k in range(1, len(path) + 1):
            if not r._fannable(path[:k]):
                break
            r._set_open(path[:k], now - 10.0)
        r.hover = None if hover is None else (hover,)
        r._apply_hover(now, instant=True)
        im = r._compose(now)
        im.info["centre"] = r.centre
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
        return frames

    def show(self, x: int, y: int) -> None:
        _register_class()
        work, scale = W.monitor_for_point(x, y)
        self._geometry(scale)
        self.cs, self.work = (x, y), work
        self._relayout()
        self._prepare()
        self.t0 = time.time()
        ex = W.WS_EX_NOACTIVATE | W.WS_EX_TOPMOST | W.WS_EX_TOOLWINDOW | W.WS_EX_LAYERED
        self.hwnd = W.CreateWindowExW(ex, CLASS_NAME, "ZOrbit", W.WS_POPUP, *self.origin, *self.size,
                                      None, None, W.GetModuleHandleW(None), None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        _instances[int(self.hwnd)] = self
        if _winmm is not None:
            _winmm.timeBeginPeriod(1)              # 10 ms timer ticks really are 10 ms while open
        self._render(self.t0)
        W.ShowWindow(self.hwnd, W.SW_SHOWNOACTIVATE)
        W.SetWindowPos(self.hwnd, W.HWND_TOPMOST, 0, 0, 0, 0,
                       W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE | W.SWP_SHOWWINDOW)
        W.SetTimer(self.hwnd, TIMER_TICK, 10, None)
        self._log(f"ring '{self.menu.id}' shown at ({x},{y}) mode={self.mode} anim={self.anim_name} "
                  f"scale={scale:.2f}")

    def key_released(self) -> None:
        if self.done or self.mode != "hold":
            return
        path, how, node = self._current_hover()
        if node is not None and self._fannable(path):
            self._set_open(path, time.time())
            self._stay_open("released on a fan")
        elif how == "wedge":
            self._stay_open("released inside a fan")
        elif self.nested and node is None:
            self._stay_open("released in the centre of a submenu")
        elif not self.nested and (time.time() - self.t0) * 1000 < self.cfg["tap_ms"]:
            self._stay_open("tap")
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
        c = self.cfg
        self.scale = scale
        self.n = len(self.items)
        self.step = 360.0 / self.n
        self.R = c["radius"] * scale
        self.slot = c["slot"] * scale
        self.dead = c["dead_zone"] * scale
        if self.nested:                            # entered on the parent's slot disc: no instant pick there
            self.dead = max(self.dead, self.slot / 2 + 4 * scale)
        self.flick_r = self.R + self.slot * 0.56   # just past the hovered (1.12x) disc
        reach = self.R * (1.0 + max(0.0, -self.anim.get("travel", 0.0)))
        self.pad = self.slot * 0.62 + 34 * scale    # half slot at 1.12x + glow + label
        self.rsize = int(2 * (reach + self.pad))    # the ring's own square; the window adds open fans
        self.seats = []
        for i in range(self.n):
            a = math.radians(self.step * i)        # 0 at 12 o'clock, clockwise
            self.seats.append((math.sin(a), -math.cos(a)))

    def _relayout(self):
        """Window origin and size for the ring plus its open fans, kept on the monitor's work area. Without a
        work area (Studio) the image just fits them."""
        hr = self.rsize // 2
        x0, y0, x1, y1 = -hr, -hr, self.rsize - hr, self.rsize - hr
        for fan in self._open_fans():
            e = fan.cslot * 0.62 + 34 * self.scale
            for px, py in fan.pos:
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
        i = int(round(ang / self.step)) % self.n
        off = abs((ang - i * self.step + 180) % 360 - 180)      # degrees from that slot's direction
        return i if off <= MAX_SECTOR / 2 else None

    def _hit(self, x, y):
        """(path, how) under window point x, y. how: "disc" (on a slot), "wedge" (inside an open fan but on
        none of its slots), "sector" (in a ring slot's angle) or None (dead zone or nowhere)."""
        rx, ry = x - self.centre[0], y - self.centre[1]
        fans = self._open_fans()
        for fan in reversed(fans):                 # deepest first
            rr = fan.cslot / 2 * 1.12 + 4 * self.scale
            for k, (px, py) in enumerate(fan.pos):
                if math.hypot(rx - px, ry - py) <= rr:
                    return fan.path + (k,), "disc"
        for i, (ux, uy) in enumerate(self.seats):
            if math.hypot(rx - ux * self.R, ry - uy * self.R) <= self.slot / 2:
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
        return k if math.hypot(vx, vy) >= fan.dists[k] + fan.cslot * 0.56 else None

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
            return ux * self.R, uy * self.R
        return self.fans[path[:-1]].pos[path[-1]]

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
        anchor_r = self.slot / 2 if len(path) == 1 else cs / 2
        fan = _Fan(path, menu, anchor, anchor_r, cs, *self._layout(path)[:-1])
        art = self._fan_art(menu)
        fan.sprites, fan.labels = [a[0] for a in art], [a[1] for a in art]
        fan.lines = self._fan_lines(anchor, anchor_r, fan.pos, cs, _chrome(self._item(path)))
        mode = MODES.get(menu.animation or self.cfg.get("animation", "smooth"), MODES["smooth"])
        dur = min(mode["dur"], FAN_MS)
        fade = max(1, min(mode["fade"], 150)) if dur else 0
        stagger = 25 if dur else 0
        fan.motion = (dur, fade, stagger, cubic_bezier(*mode["curve"]))
        fan.total = stagger * max(0, len(fan.items) - 1) + max(dur, fade)
        self.fans[path] = fan
        return fan

    def _layout(self, path):
        """_fan_layout for the slot at path, cached (its ancestors' fans must exist)."""
        lay = self._layouts.get(path)
        if lay is None:
            menu = self._submenu(self._item(path).data["menu"])
            cs, pad = self.slot * FAN_SLOT, 4 * self.scale
            anchor = self._node_pos(path)
            if len(path) == 1:                     # straight out from the ring centre
                axis = math.atan2(anchor[1], anchor[0])
            else:                                  # on along the way the parent fan points
                px, py = self._node_pos(path[:-1])
                axis = math.atan2(anchor[1] - py, anchor[0] - px)
            taken = [(0.0, 0.0, self.R - self.slot * 0.6)]
            taken += [(ux * self.R, uy * self.R, self.slot * 0.56 + pad) for ux, uy in self.seats]
            for k in range(1, len(path)):
                taken += [(x, y, cs * 0.56 + pad) for x, y in self.fans[path[:k]].pos]
            lay = self._layouts[path] = self._fan_layout(len(path), len(menu.items), anchor, axis, taken)
        return lay

    def _fan_layout(self, depth, n, anchor, axis, taken):
        """Seats for n slots in an arc around anchor, centred on axis: spaced so neighbours (and their
        labels) clear each other, the arc widened and pushed out as n grows, and past a size limit every other
        slot set further out. The arc turns away from ring slots, outer fans and the screen edge when it has
        to. Returns (axis, offsets, distances, positions, step, wedge half-angle, wedge length, penalty)."""
        cs = self.slot * FAN_SLOT
        g = cs * (1.3 if self.cfg.get("labels", "name") != "none" else 1.15)   # centre-to-centre gap
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
        cs = self.slot * FAN_SLOT
        while len(art) < len(menu.items) and (upto is None or len(art) < upto):
            it = menu.items[len(art)]
            art.append((self._slot_sprites(it, cs), self._label_sprites(it, cs)))
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
        if how == "sector" and math.hypot(rx, ry) >= self.flick_r:
            return self._flicked(path, flick, hover_sub)
        return False

    def _flicked(self, path, flick, hover_sub):
        if self._fannable(path):                   # going out past a fan submenu opens it
            if (flick or hover_sub) and tuple(self.open[:len(path)]) != path:
                self._set_open(path, time.time())
            return False
        if not flick or self._item(path).kind in ("auto", "tag"):   # empty slots: nothing to pick
            return False
        self._finish(self._item(path), "flick", self._node_screen(path))
        return True

    # --- sprites ---------------------------------------------------------------------------------
    def _prepare(self):
        col = self.cfg["colors"]
        self.c_bg, self.c_accent, self.c_hi = col["bg"], col["accent"], col["highlight"]
        self.c_text, self.c_lines = col["text"], col.get("lines", col["accent"])
        self.f_label = _font(int(11 * self.scale * SS))
        self.f_glyph = _font(int(15 * self.scale * SS))
        self.f_title = _font(int(9 * self.scale * SS))
        self.sprites = [self._slot_sprites(it) for it in self.items]
        self.labels = [self._label_sprites(it) for it in self.items]
        self._static_cache = None
        self._base_cache = None
        self._dot = self._dot_sprite()
        self.hv = [[0.0, 0.0, 0.0] for _ in self.items]       # per slot: from, to, t0
        self._blend_cache = {}

    def _slot_sprites(self, it, slot=None):
        """(idle, hover) RGBA sprites, drawn at the 1.12x hover size so scaling always reduces."""
        s = SS
        D = (slot or self.slot) * 1.12 * s         # disc diameter at full hover size, supersampled
        m = 30 * self.scale * s                    # margin for ring + glow
        C = int(D + 2 * m)
        c = C / 2
        sub = it.kind == "menu"
        fan = sub and self._fans_out(it)
        col = _chrome(it)
        hue = col or (self.c_hi if sub else self.c_accent)
        mode = self.cfg.get("tag_colors", "tint")
        tint = bool(col) and (mode in ("tint", "both") or bool(it.tag))
        soft = bool(col) and mode in ("glow", "both")
        icon = None
        try:
            icon = self.icon_for(it)
        except Exception:
            icon = None
        ins = int(D - 16 * 1.12 * self.scale * s)
        if icon is not None:
            icon = icon.convert("RGBA").resize((ins, ins), Image.LANCZOS)
            mask = Image.new("L", (ins, ins), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, ins - 1, ins - 1), fill=255)
            icon.putalpha(ImageChops.multiply(icon.getchannel("A"), mask))
        solid = bool(col) and bool(it.tag) and sub and icon is None   # a tag slot: solid disc in the tag colour
        fill = _mix(self.c_bg, col, 0.6) + (255,) if solid else (
            _mix(self.c_bg, col, 0.45) + (235,) if tint else _rgba(self.c_bg, 0.92))

        def disc(hover):
            im = Image.new("RGBA", (C, C), (0, 0, 0, 0))
            if hover:                              # glow + soft outer ring
                glow = Image.new("RGBA", (C, C), (0, 0, 0, 0))
                gr = D / 2 + 4 * self.scale * s
                ImageDraw.Draw(glow).ellipse((c - gr, c - gr, c + gr, c + gr), fill=_rgba(hue, 0.55))
                glow = glow.filter(ImageFilter.GaussianBlur(12 * self.scale * s))
                im.alpha_composite(glow)
                rr = D / 2 + 3 * self.scale * s
                ImageDraw.Draw(im).ellipse((c - rr, c - rr, c + rr, c + rr), fill=_rgba(hue, 0.20))
            d = ImageDraw.Draw(im)
            r = D / 2
            border = _rgba(hue, 1.0) if hover else (_rgba(col, 0.9) if tint else _rgba(self.c_text, 0.10))
            d.ellipse((c - r, c - r, c + r, c + r), fill=fill, outline=border,
                      width=max(1, int((3 if tint and not hover else 2) * self.scale * s)))
            if icon is not None:
                im.alpha_composite(icon, (int(c - ins / 2), int(c - ins / 2)))
            elif it.kind == "auto":                # an auto slot nothing has filled yet: faint, no disc
                gd = ImageDraw.Draw(im)
                l, t_, r_, b_ = gd.textbbox((0, 0), "+", font=self.f_glyph)
                gd.text((c - (r_ - l) / 2 - l, c - (b_ - t_) / 2 - t_), "+", font=self.f_glyph,
                        fill=_rgba(self.c_text, 0.35))
            elif it.kind == "tag":                 # a tag with no brushes (or no such tag): faint, no tint
                _glyph_tag(ImageDraw.Draw(im), c, c, ins * 0.42, _rgba(it.color or self.c_text, 0.35))
            elif solid:                            # tag slot: the disc is the tag colour
                _glyph_tag(ImageDraw.Draw(im), c, c, ins * 0.46, _rgba(self.c_text, 0.9))
            else:                                  # placeholder disc with a short glyph
                pr = ins / 2
                ph = Image.new("RGBA", (C, C), (0, 0, 0, 0))
                pd = ImageDraw.Draw(ph)
                for k in range(12, 0, -1):         # cheap radial gradient
                    t = k / 12
                    g = tuple(int(a + (b - a) * (1 - t)) for a, b in zip((0x2a, 0x2a, 0x35), (0x5a, 0x5a, 0x6a)))
                    rr = pr * t
                    pd.ellipse((c - rr, c - rr, c + rr, c + rr), fill=g + (255,))
                im.alpha_composite(ph)
                gd = ImageDraw.Draw(im)
                if it.kind == "browser":           # the brush browser: a 2x2 grid
                    _glyph_grid(gd, c, c, ins * 0.46, _rgba(it.color or self.c_text, 0.95))
                else:
                    glyph = it.label if len(it.label) <= 4 else "".join(w[0] for w in it.label.split()[:2]).upper()
                    l, t_, r_, b_ = gd.textbbox((0, 0), glyph, font=self.f_glyph)
                    gd.text((c - (r_ - l) / 2 - l, c - (b_ - t_) / 2 - t_), glyph, font=self.f_glyph,
                            fill=_rgba(self.c_text, 0.9))
            if sub:                                # submenu badge, bottom-right: a fan, or an arrow for a ring
                u = self.scale * s
                bw = 14 * u
                bx, by = c + r * 0.62, c + r * 0.62
                d.rounded_rectangle((bx - bw / 2, by - bw / 2, bx + bw / 2, by + bw / 2), radius=4 * u,
                                    fill=(0, 0, 0, 217), outline=_rgba(self.c_hi, 1.0), width=max(1, int(u)))
                if fan:
                    _glyph_fan(d, bx - 4 * u, by + 4 * u, 8 * u, _rgba(self.c_hi, 1.0))
                else:
                    tri = 3.5 * u
                    d.polygon([(bx - tri * 0.7, by - tri), (bx - tri * 0.7, by + tri), (bx + tri, by)],
                              fill=_rgba(self.c_hi, 1.0))
            out = im.resize((int(C / s), int(C / s)), Image.LANCZOS)
            if soft and not hover:                 # soft halo in the tag colour, blurred at 1x
                n = out.size[0]
                gr = D / 2 / s + 2 * self.scale
                halo = Image.new("RGBA", (n, n), (0, 0, 0, 0))
                ImageDraw.Draw(halo).ellipse((n / 2 - gr, n / 2 - gr, n / 2 + gr, n / 2 + gr), fill=_rgba(col, 0.4))
                halo = halo.filter(ImageFilter.GaussianBlur(8 * self.scale))
                halo.alpha_composite(out)
                out = halo
            return out
        return disc(False), disc(True)

    def _label_sprites(self, it, slot=None):
        if self.cfg.get("labels", "name") == "none":
            return None
        s = SS
        font = self.f_label
        tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        text = it.label
        maxw = (slot or self.slot) * 1.9 * s
        if tmp.textbbox((0, 0), text, font=font)[2] > maxw:
            while len(text) > 1 and tmp.textbbox((0, 0), text + "…", font=font)[2] > maxw:
                text = text[:-1]
            text += "…"
        l, t, r, b = tmp.textbbox((0, 0), text, font=font)
        pad = int(6 * self.scale * s)
        Wd, Hd = r - l + 2 * pad, b - t + 2 * pad
        out = []
        for hover in (False, True):
            hue = (_chrome(it) or (self.c_hi if it.kind == "menu" else self.c_accent)) if hover else self.c_text
            im = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
            sh = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0))
            ImageDraw.Draw(sh).text((pad - l, pad - t + self.scale * s), text, font=font, fill=(0, 0, 0, 205))
            im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(2.2 * self.scale * s)))
            ImageDraw.Draw(im).text((pad - l, pad - t), text, font=font, fill=_rgba(hue, 1.0))
            out.append(im.resize((max(1, int(Wd / s)), max(1, int(Hd / s))), Image.LANCZOS))
        return out

    def _dot_sprite(self):
        s = SS
        d = 10 * self.scale * s
        m = 14 * self.scale * s
        C = int(d + 2 * m)
        c = C / 2
        im = Image.new("RGBA", (C, C), (0, 0, 0, 0))
        g = Image.new("RGBA", (C, C), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse((c - d / 2, c - d / 2, c + d / 2, c + d / 2), fill=_rgba(self.c_accent, 0.9))
        im.alpha_composite(g.filter(ImageFilter.GaussianBlur(5 * self.scale * s)))
        ImageDraw.Draw(im).ellipse((c - d / 2, c - d / 2, c + d / 2, c + d / 2), fill=_rgba(self.c_accent, 1.0))
        return im.resize((int(C / s), int(C / s)), Image.LANCZOS)

    def _fan_lines(self, anchor, anchor_r, pos, cs, color=""):
        """Dashed lines from a fan's slot out to each of its slots, in color if it has one: (image, top-left
        relative to the ring centre)."""
        s = SS
        m = 4 * self.scale
        xs, ys = [anchor[0]] + [p[0] for p in pos], [anchor[1]] + [p[1] for p in pos]
        x0, y0 = math.floor(min(xs) - m), math.floor(min(ys) - m)
        w, h = math.ceil(max(xs) + m) - x0, math.ceil(max(ys) + m) - y0
        im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        col = _rgba(color or self.c_lines, 0.75)
        lw = max(1, int(1.3 * self.scale * s))
        dash, gap = 5 * self.scale, 4 * self.scale
        ax, ay = anchor
        for px, py in pos:
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
        hit = (self.R + self.slot * 0.62 + 6 * self.scale) * s   # invisible disc so clicks land on us
        d.ellipse((cx - hit, cy - hit, cx + hit, cy + hit), fill=(0, 0, 0, 1))
        lw = max(1, int(self.scale * s))
        for frac, a in ((0.28, 0.05), (0.52, 0.03), (0.76, 0.02)):
            r = self.R * frac * s
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=_rgba(self.c_lines, a), width=lw)
        r0, r1 = 8 * self.scale * s, (self.R - self.slot / 2 - 6 * self.scale) * s
        for (ux, uy), it in zip(self.seats, self.items):
            colr = _rgba(_chrome(it), 0.35) if _chrome(it) else (
                _rgba(self.c_hi, 0.35) if it.kind == "menu" else _rgba(self.c_lines, 0.30))
            d.line((cx + ux * r0, cy + uy * r0, cx + ux * r1, cy + uy * r1), fill=colr, width=lw)
        title = " ".join(self.menu.title.upper())                 # letter-spaced caps
        hint = "release to pick" if self.mode == "hold" else "click to cancel"
        for text, dy, colr in ((title, 18, _rgba(self.c_accent, 0.85)), (hint, 30, (255, 255, 255, 56))):
            l, t, r_, b = d.textbbox((0, 0), text, font=self.f_title)
            d.text((cx - (r_ - l) / 2 - l, cy + dy * self.scale * s - (b - t) / 2 - t), text, font=self.f_title,
                   fill=colr)
        self._static_cache = im.resize((self.rsize, self.rsize), Image.LANCZOS)
        return self._static_cache

    def _base(self, el):
        """A fresh canvas holding the invisible hit surface of the open fans and the ring's static layer
        (which fades in over the first 100 ms)."""
        fading = self.anim["dur"] > 0 and el < 100
        key = (self.mode, tuple(self.open), self.size)
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
            r = fan.cslot * 0.62 + 6 * self.scale
            for px, py in fan.pos:
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
        dx, dy = -ux * self.R * travel, -uy * self.R * travel
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
                ImageDraw.Draw(halo).ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=_rgba(self.c_accent, 0.12))
                canvas.alpha_composite(halo.filter(ImageFilter.GaussianBlur(rad * 0.35 + 1)))
        if a.get("ripples"):                       # two accent rings expanding from the dot
            d = ImageDraw.Draw(canvas)
            for delay in (0, 140):
                p = (el - delay) / 1000
                if 0 < p < 1:
                    rr = 5 * self.scale * (0.1 + 23.9 * EASE_OUT(p))
                    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=_rgba(self.c_accent, 0.9 * (1 - p)),
                              width=max(1, int(1.5 * self.scale)))
        ds = 1.0
        if a.get("dot_pop"):                       # 0 -> 1.35 -> 1 over 420 ms
            p = min(1.0, el / 420)
            ds = 1.35 * EASE_OUT(p / 0.6) if p < 0.6 else 1.35 - 0.35 * EASE((p - 0.6) / 0.4)
        if ds > 0.02:
            dot = self._dot
            k = max(1, int(dot.size[0] * ds))
            dd = dot if k == dot.size[0] else dot.resize((k, k), Image.BILINEAR)
            _blit(canvas, dd, cx - k / 2, cy - k / 2)
        order = sorted(range(self.n), key=lambda i: self.hv[i][1])  # hovered slot drawn last (on top)
        for i in order:
            sc, alpha, dx, dy, rot, blur = self._slot_state(i, now)
            ux, uy = self.seats[i]
            self._draw_slot(canvas, ((), i), self.sprites[i], self.labels[i], cx + ux * self.R + dx,
                            cy + uy * self.R + dy, sc, alpha, self._hover_val(self.hv, i, now), rot, blur, self.slot)
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
        for k in sorted(range(len(fan.items)), key=lambda j: fan.hv[j][1]):
            e, alpha = 1.0, 1.0
            if dur > 0:
                ek = el - stagger * k
                e = curve(min(1.0, max(0.0, ek / dur)))
                alpha = min(1.0, max(0.0, ek / fade))
            px, py = fan.pos[k]
            self._draw_slot(canvas, (fan.path, k), fan.sprites[k], fan.labels[k], cx + ax + (px - ax) * e,
                            cy + ay + (py - ay) * e, 0.6 + 0.4 * e, alpha, self._hover_val(fan.hv, k, now), 0, 0.0,
                            fan.cslot)

    def _draw_slot(self, canvas, key, sprites, labels, px, py, sc, alpha, h, rot, blur, slot):
        """One slot (and its label) centred on px, py. key: blend cache key of that slot."""
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
        if spr is None:
            return
        _blit(canvas, spr, px - wk / 2, py - wk / 2)
        if labels is not None:
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
        over = how in ("disc", "wedge") or math.hypot(lx - self.centre[0], ly - self.centre[1]) <= (
            self.R + self.slot * 0.62 + 6 * self.scale)
        if self.mode == "click" and not over and (W.key_down(W.VK_LBUTTON) or W.key_down(0x02)):
            self._finish(None, "clicked outside")
            return
        if self._flick_or_hand_off(lx, ly, path, how):
            return
        self._update_open(path, how, now)
        hover = path if how in ("disc", "sector") else None
        if hover != self.hover:
            self.hover = hover
            self._apply_hover(now)
        key = (self.mode, self.hover, tuple(self.open))
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
