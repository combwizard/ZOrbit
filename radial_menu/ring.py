"""The radial overlay: round icon slots on a ring, animated, in a non-activating layered window.

Look: slots of round icons around a glowing accent centre dot,
hairline spokes and faint guide rings; hover = accent border, soft ring, glow, 1.12x scale and accent label;
submenus use the highlight colour and a small badge. Selection is by angle outside a dead zone.

Motion: every slot is a pre-rendered sprite (idle and hover look). Each frame only scales, fades, moves,
rotates or blurs sprites and composites them, so a frame costs a few milliseconds. Open animations are
staggered per slot (modes below); hover eases over 120 ms; closing is instant so picks never wait.

The window never takes focus (WS_EX_NOACTIVATE from creation, MA_NOACTIVATE on clicks), so the target app
keeps keyboard focus and sees every key-up.

Lifecycle: Ring(...).show(x, y) -> owner calls key_released() when the hotkey goes up -> the ring calls
on_done(item_or_None, reason) exactly once and destroys itself.
"""
import ctypes
import math
import os
import time

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import win32 as W

SS = 3                      # supersampling for sprites (drawn large, reduced once)
TIMER_TICK = 1
CLASS_NAME = "RadialMenuRing"
HOVER_MS = 120
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


def _fade(im, a: float):
    if a >= 0.999:
        return im
    if a <= 0.001:
        return None
    out = im.copy()
    out.putalpha(out.getchannel("A").point([int(v * a) for v in range(256)]))
    return out


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


class Ring:
    def __init__(self, menu, ring_cfg: dict, icon_for, on_done, log, held: bool):
        """menu: config.Menu. icon_for(item) -> PIL RGBA image or None. on_done(item|None, reason).
        held: True when opened by a hotkey that is still down (enables hold-and-release picking)."""
        self.menu = menu
        self.items = menu.items
        self.cfg = ring_cfg
        self.icon_for = icon_for
        self.on_done = on_done
        self._log = log
        self.mode = "hold" if held else "click"
        self.anim_name = getattr(menu, "animation", "") or ring_cfg.get("animation", "smooth")
        self.anim = MODES.get(self.anim_name, MODES["smooth"])
        self.curve = cubic_bezier(*self.anim["curve"])
        self.hover = None
        self.done = False
        self.hwnd = None
        self._dib = None
        self._last_key = None

    # --- public ----------------------------------------------------------------------------------
    @classmethod
    def preview(cls, menu, ring_cfg: dict, icon_for, hover=None, scale=1.0, t=None):
        """Renders the ring to a PIL RGBA image without a window (Studio). t: seconds since open, or None
        for the settled look."""
        r = cls(menu, ring_cfg, icon_for, lambda *a: None, lambda m: None, held=False)
        r._geometry(scale)
        r.centre = (r.size // 2, r.size // 2)
        r._prepare()
        now = 1000.0
        r.t0 = now - (t if t is not None else 10.0)
        r._set_hover(hover, now, instant=True)
        return r._compose(now)

    @classmethod
    def preview_frames(cls, menu, ring_cfg: dict, icon_for, scale=1.0, fps=30):
        """Frames of the open animation (Studio animation preview)."""
        r = cls(menu, ring_cfg, icon_for, lambda *a: None, lambda m: None, held=False)
        r._geometry(scale)
        r.centre = (r.size // 2, r.size // 2)
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
        half = self.size // 2
        wx = min(max(x - half, work.left), work.right - self.size)
        wy = min(max(y - half, work.top), work.bottom - self.size)
        self.origin = (wx, wy)
        self.centre = (x - wx, y - wy)            # ring centre in window coords (cursor position)
        self._prepare()
        self.t0 = time.time()
        ex = W.WS_EX_NOACTIVATE | W.WS_EX_TOPMOST | W.WS_EX_TOOLWINDOW | W.WS_EX_LAYERED
        self.hwnd = W.CreateWindowExW(ex, CLASS_NAME, "Radial Menu", W.WS_POPUP, wx, wy, self.size, self.size,
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
        if (time.time() - self.t0) * 1000 < self.cfg["tap_ms"]:
            self.mode = "click"                    # quick tap: stay open, wait for a click
            self._static_cache = None              # hint text changes
            self._log("tap: ring stays open for a click")
        else:
            self._finish(self._current_hover(), "released")

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
        reach = self.R * (1.0 + max(0.0, -self.anim.get("travel", 0.0)))
        self.pad = self.slot * 0.62 + 34 * scale    # half slot at 1.12x + glow + label
        self.size = int(2 * (reach + self.pad))
        self.seats = []
        for i in range(self.n):
            a = math.radians(self.step * i)        # 0 at 12 o'clock, clockwise
            self.seats.append((math.sin(a), -math.cos(a)))

    def _index_at(self, x, y):
        dx, dy = x - self.centre[0], y - self.centre[1]
        if math.hypot(dx, dy) < self.dead:
            return None
        ang = math.degrees(math.atan2(dx, -dy)) % 360          # 0 at top, clockwise
        return int(round(ang / self.step)) % self.n

    def _current_hover(self):
        x, y = W.cursor_pos()
        i = self._index_at(x - self.origin[0], y - self.origin[1])
        return None if i is None else self.items[i]

    # --- sprites ---------------------------------------------------------------------------------
    def _prepare(self):
        col = self.cfg["colors"]
        self.c_bg, self.c_accent, self.c_hi = col["bg"], col["accent"], col["highlight"]
        self.c_text, self.c_lines = col["text"], col.get("lines", col["accent"])
        self.f_label = _font(int(11 * self.scale * SS))
        self.f_glyph = _font(int(15 * self.scale * SS))
        self.f_title = _font(int(9 * self.scale * SS))
        self.sprites = [self._slot_sprites(i, it) for i, it in enumerate(self.items)]
        self.labels = [self._label_sprites(it) for it in self.items]
        self._static_cache = None
        self._dot = self._dot_sprite()
        self.hv = [[0.0, 0.0, 0.0] for _ in self.items]       # per slot: from, to, t0
        self._blend_cache = {}

    def _slot_sprites(self, i, it):
        """(idle, hover) RGBA sprites, drawn at the 1.12x hover size so scaling always reduces."""
        s = SS
        D = self.slot * 1.12 * s                   # disc diameter at full hover size, supersampled
        m = 30 * self.scale * s                    # margin for ring + glow
        C = int(D + 2 * m)
        c = C / 2
        sub = it.kind == "menu"
        hue = self.c_hi if sub else self.c_accent
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
            border = _rgba(hue, 1.0) if hover else _rgba(self.c_text, 0.10)
            d.ellipse((c - r, c - r, c + r, c + r), fill=_rgba(self.c_bg, 0.92), outline=border,
                      width=max(1, int(2 * self.scale * s)))
            if icon is not None:
                im.alpha_composite(icon, (int(c - ins / 2), int(c - ins / 2)))
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
                glyph = it.label if len(it.label) <= 4 else "".join(w[0] for w in it.label.split()[:2]).upper()
                gd = ImageDraw.Draw(im)
                l, t_, r_, b_ = gd.textbbox((0, 0), glyph, font=self.f_glyph)
                gd.text((c - (r_ - l) / 2 - l, c - (b_ - t_) / 2 - t_), glyph, font=self.f_glyph,
                        fill=_rgba(self.c_text, 0.9))
            if sub:                                # submenu badge, bottom-right
                bw = 14 * self.scale * s
                bx, by = c + r * 0.62, c + r * 0.62
                d.rounded_rectangle((bx - bw / 2, by - bw / 2, bx + bw / 2, by + bw / 2), radius=4 * self.scale * s,
                                    fill=(0, 0, 0, 217), outline=_rgba(self.c_hi, 1.0), width=max(1, int(self.scale * s)))
                tri = 3.5 * self.scale * s
                d.polygon([(bx - tri * 0.7, by - tri), (bx - tri * 0.7, by + tri), (bx + tri, by)],
                          fill=_rgba(self.c_hi, 1.0))
            return im.resize((int(C / s), int(C / s)), Image.LANCZOS)
        return disc(False), disc(True)

    def _label_sprites(self, it):
        if self.cfg.get("labels", "name") == "none":
            return None
        s = SS
        font = self.f_label
        tmp = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        text = it.label
        maxw = self.slot * 1.9 * s
        if tmp.textbbox((0, 0), text, font=font)[2] > maxw:
            while len(text) > 1 and tmp.textbbox((0, 0), text + "…", font=font)[2] > maxw:
                text = text[:-1]
            text += "…"
        l, t, r, b = tmp.textbbox((0, 0), text, font=font)
        pad = int(6 * self.scale * s)
        Wd, Hd = r - l + 2 * pad, b - t + 2 * pad
        out = []
        for hover in (False, True):
            hue = (self.c_hi if it.kind == "menu" else self.c_accent) if hover else self.c_text
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

    def _static(self):
        """Guide rings, spokes, title and hint (no dot, no slots). Cached per hint text."""
        if self._static_cache is not None:
            return self._static_cache
        s = SS
        S = self.size * s
        cx, cy = self.centre[0] * s, self.centre[1] * s
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
            colr = _rgba(self.c_hi, 0.35) if it.kind == "menu" else _rgba(self.c_lines, 0.30)
            d.line((cx + ux * r0, cy + uy * r0, cx + ux * r1, cy + uy * r1), fill=colr, width=lw)
        title = " ".join(self.menu.title.upper())                 # letter-spaced caps
        hint = "release to pick" if self.mode == "hold" else "click to cancel"
        for text, dy, colr in ((title, 18, _rgba(self.c_accent, 0.85)), (hint, 30, (255, 255, 255, 56))):
            l, t, r_, b = d.textbbox((0, 0), text, font=self.f_title)
            d.text((cx - (r_ - l) / 2 - l, cy + dy * self.scale * s - (b - t) / 2 - t), text, font=self.f_title,
                   fill=colr)
        self._static_cache = im.resize((self.size, self.size), Image.LANCZOS)
        return self._static_cache

    # --- animation -------------------------------------------------------------------------------
    def _open_ms(self):
        a = self.anim
        tail = max(a["dur"], a["fade"], a.get("blur_ms", 0), 420 if a.get("dot_pop") else 0)
        return a["stagger"] * max(0, self.n - 1) + tail + 40

    def _set_hover(self, idx, now, instant=False):
        for i, h in enumerate(self.hv):
            target = 1.0 if i == idx else 0.0
            if h[1] != target:
                cur = self._hover_val(i, now)
                self.hv[i] = [cur, target, now - (10 if instant else 0)]

    def _hover_val(self, i, now):
        f, to, t0 = self.hv[i]
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
        return any(h[1] != self._hover_val(i, now) for i, h in enumerate(self.hv))

    def _compose(self, now):
        el = (now - self.t0) * 1000
        a = self.anim
        static = self._static()
        if a["dur"] > 0 and el < 100:                          # backdrop fades in over 100 ms
            faded = _fade(static, max(0.0, el / 100))
            canvas = faded.copy() if faded is not None else Image.new("RGBA", static.size, (0, 0, 0, 0))
            canvas.putalpha(ImageChops.lighter(canvas.getchannel("A"), static.getchannel("A").point(
                lambda v: 1 if v else 0)))                      # keep the invisible click disc
        else:
            canvas = static.copy()
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
            canvas.alpha_composite(dd, (int(cx - k / 2), int(cy - k / 2)))
        order = sorted(range(self.n), key=lambda i: self.hv[i][1])  # hovered slot drawn last (on top)
        for i in order:
            sc, alpha, dx, dy, rot, blur = self._slot_state(i, now)
            if alpha <= 0.001:
                continue
            h = self._hover_val(i, now)
            idle, hov = self.sprites[i]
            hk = round(h, 2)
            if hk <= 0.0:
                spr = idle
            elif hk >= 1.0:
                spr = hov
            else:
                spr = self._blend_cache.get((i, hk))
                if spr is None:
                    spr = Image.blend(idle, hov, hk)
                    self._blend_cache[(i, hk)] = spr
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
                continue
            ux, uy = self.seats[i]
            px, py = cx + ux * self.R + dx, cy + uy * self.R + dy
            canvas.alpha_composite(spr, (int(px - wk / 2), int(py - wk / 2)))
            if self.labels[i] is not None:
                lab = Image.blend(*self.labels[i], h) if 0 < h < 1 else self.labels[i][1 if h >= 1 else 0]
                lab = _fade(lab, alpha)
                if lab is not None:
                    ly = py + self.slot / 2 * (1.0 + 0.12 * h) * sc + 2 * self.scale
                    canvas.alpha_composite(lab, (int(px - lab.size[0] / 2), int(ly)))
        return canvas

    # --- window plumbing -------------------------------------------------------------------------
    def _render(self, now):
        self._push(self._compose(now))

    def _push(self, im):
        """Premultiply and hand the frame to Windows via UpdateLayeredWindow."""
        r, g, b, a = im.split()
        r, g, b = (ImageChops.multiply(ch, a) for ch in (r, g, b))
        data = Image.merge("RGBA", (r, g, b, a)).tobytes("raw", "BGRA")
        screen = W.GetDC(None)
        try:
            if self._dib is None:
                bih = W.BITMAPINFOHEADER()
                bih.biSize = ctypes.sizeof(W.BITMAPINFOHEADER)
                bih.biWidth, bih.biHeight = self.size, -self.size     # top-down
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
            sz = W.w.SIZE(self.size, self.size)
            pt_src = W.w.POINT(0, 0)
            W.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(pt_dst), ctypes.byref(sz), mem,
                                  ctypes.byref(pt_src), 0, ctypes.byref(blend), W.ULW_ALPHA)
        finally:
            W.ReleaseDC(None, screen)

    def _on_message(self, msg, wparam, lparam):
        if msg == W.WM_MOUSEACTIVATE:
            return W.MA_NOACTIVATE
        if msg == W.WM_TIMER and wparam == TIMER_TICK:
            self._tick()
            return 0
        if msg == W.WM_LBUTTONUP:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            i = self._index_at(x, y)
            if self.mode == "hold" and i is None:
                return 0                           # stray press in the centre while holding: ignore
            self._finish(None if i is None else self.items[i], "click")
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
        inside = 0 <= lx < self.size and 0 <= ly < self.size
        if self.mode == "click" and not inside and (W.key_down(W.VK_LBUTTON) or W.key_down(0x02)):
            self._finish(None, "clicked outside")
            return
        i = self._index_at(lx, ly)
        if i != self.hover:
            self.hover = i
            self._set_hover(i, now)
        key = (self.mode, self.hover)
        if self._animating(now) or key != self._last_key:
            self._last_key = key
            self._render(now)

    def _finish(self, item, reason):
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
        if self._dib is not None:
            hbmp, mem, old, bits = self._dib
            W.SelectObject(mem, old)
            W.DeleteObject(hbmp)
            W.DeleteDC(mem)
            self._dib = None
        self.on_done(item, reason)
