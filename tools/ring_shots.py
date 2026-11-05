"""Draws the ring pictures in docs/images (ring.png, ring-light.png, ring-zbrush.png, fan.png, tag-colours.png,
animations.png, the look pictures slot-shapes.png, hub-styles.png, slot-styles.png, looks.png, second-ring.png,
more-slot.png and empty-slots.png, and the three GIFs) with the real renderer, zorbit/ring.py, so they follow the ring's look whenever it
changes. No window is opened and no ZBrush is needed, but the brush pictures come from the installed ZBrush's
presets, so a ZBrush has to be installed.

The pictures show a fresh install, not the developer's own setup: the script points %APPDATA%, %LOCALAPPDATA% and
the tags file at a throw-away folder before it imports anything from zorbit, so it gets the starter menus and the
starter tags, and your own radial.json, tags.json and usage.json are neither read nor written. The mouse cursor is
drawn on afterwards, as the renderer does not draw one.

The starter menus have no tags on their brushes, so the tag colours show only in the tag picture, which tags its
brushes in the sandbox's own tags file.

Run: python tools/ring_shots.py                         (every picture)
     python tools/ring_shots.py ring fan                (only those)
     python tools/ring_shots.py --out DIR ...           (somewhere else than docs/images, to look first)
"""
import atexit
import dataclasses
import glob
import math
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Before any zorbit module is imported: paths.py works out where the config and data live when it is first imported.
SANDBOX = tempfile.mkdtemp(prefix="zorbit-ring-shots-")
for _f in glob.glob(os.path.expandvars(r"%APPDATA%\Maxon\*\installpath.txt")):   # so ZBrush is found, nothing else
    _dest = os.path.join(SANDBOX, "Roaming", "Maxon", os.path.basename(os.path.dirname(_f)))
    os.makedirs(_dest, exist_ok=True)
    shutil.copy(_f, _dest)
os.environ["APPDATA"] = os.path.join(SANDBOX, "Roaming")
os.environ["LOCALAPPDATA"] = os.path.join(SANDBOX, "Local")
os.environ["ZORBIT_TAGS_FILE"] = os.path.join(SANDBOX, "Roaming", "ZOrbit", "tags.json")
os.environ["ZORBIT_USAGE_FILE"] = os.path.join(SANDBOX, "Local", "ZOrbit", "usage.json")
atexit.register(shutil.rmtree, SANDBOX, ignore_errors=True)
sys.path.insert(0, os.path.join(ROOT, "zorbit"))

from PIL import Image, ImageChops, ImageDraw, ImageFont  # noqa: E402

import paths  # noqa: E402

assert os.path.commonpath([paths.CONFIG_DIR, SANDBOX]) == SANDBOX, "the config folder is outside the sandbox"
assert os.path.commonpath([paths.DATA_DIR, SANDBOX]) == SANDBOX, "the data folder is outside the sandbox"

import config as C  # noqa: E402
import expand  # noqa: E402
import installs  # noqa: E402
import looks  # noqa: E402
import radiald  # noqa: E402
import tags  # noqa: E402
import zbrush_colors  # noqa: E402
from ring import Ring  # noqa: E402

OUT = os.path.join(ROOT, "docs", "images")
BG = (27, 28, 32)                              # the docs' dark page colour, as in every picture
BG_LIGHT = (200, 203, 210)                     # a light ZBrush canvas, behind the Light theme's ring
BG_ZBRUSH = (52, 52, 52)                       # close to ZBrush's document colour, behind the Match ZBrush ring
TEXT, MUTED = (236, 237, 240), (170, 173, 182)  # caption colours under the animation panels
FONTS = os.path.expandvars(r"%WINDIR%\Fonts")

# The tag picture: the ring's eight brushes in order from the top, clockwise, and the tag each carries.
TAG_ITEMS = [("ClayBuildup", "blocking"), ("ClayTubes", "blocking"), ("Move", "blocking"), ("Smooth", None),
             ("hPolish", "detailing"), ("Pinch", "detailing"), ("TrimDynamic", "detailing"), ("DamStandard", None)]
# The animation picture: each open animation and the millisecond it is caught at.
ANIMATIONS = [("spiral", 340), ("fancy", 160), ("ripple", 140), ("breath", 220), ("mist", 200)]
PANEL = (260, 320)                             # one animation panel, and where its ring centre sits in it
PANEL_CENTRE = (130, 137)
PANEL_SCALE = 0.6
PANEL_BIG, PANEL_BIG_CENTRE, PANEL_BIG_SCALE = (340, 390), (170, 176), 0.78   # a larger panel, for the hub pictures
RING_SCALE = 1.342                             # makes the ring pictures 600 pixels square
FILE_SLOTS = [("Capture", "capture", ""), ("Hero", "tool", "D:/Models/Hero.ztl"),   # the file slots picture: label, type, path
              ("Blockout", "project", "D:/Projects/Blockout")]
COMMAND = 'ZOrbit.exe --open "brushes"'            # the command animation: what it shows, its band's height and its lit colour
COMMAND_BAND, COMMAND_ON = 56, (255, 122, 61)
FAN_SCALE = 0.95                               # the fan picture is a little smaller, about 594 pixels wide


class World:
    """The starter menus and tags in the sandbox, loaded the way Studio's ring preview loads them."""

    def __init__(self, theme="dark"):
        self.app = radiald.App(paths.ensure_config())
        assert os.path.commonpath([self.app.tags.path, SANDBOX]) == SANDBOX, "the tags file is outside the sandbox"
        store = self.app.tags.load()
        for brush, tag in TAG_ITEMS:               # in the sandbox's tags file, never the real one
            if tag:
                store.set_tags(tags.item_key("brush", brush), [tag])
        plain = tags.TagStore(os.path.join(SANDBOX, "untagged.json")).load()   # the starter tags, nothing tagged
        cfg = C.load(self.app.cfg_path, store, theme=theme)
        assert not cfg.errors, cfg.errors
        self.fan_menus = [cfg.menus[m] for m in ("more", "tools", "subdiv")]
        cfg.menus["tags"] = C.Menu(id="tags", title="Tags", items=[
            C.Item(label=b, kind="brush", data={"brush": b}) for b, _ in TAG_ITEMS])
        self.app.cfg = cfg
        self.cfg = cfg
        self.ex = {False: expand.Expander(cfg, self.app.usage, plain), True: expand.Expander(cfg, self.app.usage, store)}

    def fans(self, on):
        """The starter menus open as rings; the fan pictures show More Brushes, Tools and SubDivide as fans."""
        for m in self.fan_menus:
            m.fan = on

    def define(self, menu_id, brushes, look=None, title="Brushes"):
        """A menu of brushes (names, or (name, label) pairs) added to the loaded config, so the Expander can page it
        and resolve its more: menu. look: a preset name or a dict of look keys, as for preview()."""
        items = [C.Item(label=b[1] if isinstance(b, tuple) else b, kind="brush",
                        data={"brush": b[0] if isinstance(b, tuple) else b}) for b in brushes]
        menu = C.Menu(id=menu_id, title=title, items=items)
        if look is not None:
            menu.look = self.resolve_look(look)
        self.cfg.menus[menu_id] = menu
        return menu

    def resolve_look(self, look):
        """The complete look of a menu with this look: a preset name, or a dict of look keys (it may name a
        "preset" too), laid over the ring's, the way the config does for a menu's look."""
        return self.cfg.looks.menu_look({"preset": look} if isinstance(look, str) else dict(look))

    def preview(self, menu_id, animation="", tagged=False, ring=None, look=None, styles=None, fields=None, **kw):
        """The ring picture of a menu. look: a preset name or a dict of look keys for this menu only (menu.look).
        styles: {item index: style dict} for single slots (item.style). fields: other Menu fields to set (icon)."""
        ex = self.ex[tagged]
        base = self.cfg.menus[menu_id]
        changes = dict(fields or {})
        if look is not None:
            changes["look"] = self.resolve_look(look)
        if styles:
            changes["items"] = [dataclasses.replace(it, style=dict(styles[i])) if i in styles else it
                                for i, it in enumerate(base.items)]
        if changes:
            base = dataclasses.replace(base, **changes)
        menu = ex.menu(base)
        if animation:
            menu.animation = animation
        return Ring.preview(menu, ring or self.cfg.ring, self.app.icon_for, submenus=ex.resolve, **kw)


def cursor(scale=1.0):
    """The Windows arrow, white with a dark outline, tip at (0, 0), as an RGBA image and the margin before the tip."""
    ss, pad = 4, 2
    pts = [(0, 0), (0, 17), (4.2, 13.4), (7.2, 20.2), (9.9, 19), (6.9, 12.4), (12.4, 12.4)]
    k = scale * ss
    w, h = int((14 + 2 * pad) * k), int((22 + 2 * pad) * k)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    poly = [(int((x + pad) * k), int((y + pad) * k)) for x, y in pts]
    d = ImageDraw.Draw(im)
    d.polygon(poly, fill=(255, 255, 255, 255), outline=(14, 15, 18, 255), width=max(1, int(1.4 * k)))
    return im.resize((w // ss, h // ss), Image.LANCZOS), int(pad * scale)


def on_background(im, size=None, at=(0, 0), bg=BG):
    """The ring picture laid on the page colour (or bg), on a canvas of size (the picture's own by default)."""
    canvas = Image.new("RGBA", size or im.size, bg + (255,))
    canvas.alpha_composite(im, at)
    return canvas


def with_cursor(canvas, x, y, scale=1.0):
    """The arrow's tip at (x, y)."""
    cur, pad = cursor(scale)
    canvas.alpha_composite(cur, (int(round(x)) - pad, int(round(y)) - pad))
    return canvas


def hovered(im):
    """Where the cursor goes for the hovered slot: a touch below and right of its centre."""
    x, y = im.info["hover_at"]
    return x + 3, y + 5


def font(name, px):
    return ImageFont.truetype(os.path.join(FONTS, name), px)


# --- the pictures ------------------------------------------------------------------------------------
def shot_ring(w):
    w.fans(False)
    im = w.preview("brushes", hover=1, held=True, scale=RING_SCALE)
    return with_cursor(on_background(im), *hovered(im))


def shot_ring_light(w):
    """The same ring as shot_ring, in the Light theme, over a light canvas."""
    w.fans(False)
    im = w.preview("brushes", hover=1, held=True, scale=RING_SCALE)
    return with_cursor(on_background(im, bg=BG_LIGHT), *hovered(im))


def stock_scheme():
    """ZBrush's stock colours as a zbrush_colors.Scheme, read from the newest installed ZBrush that ships
    ZStartup/UserInterfaceColors/Z4R8_default.cfg, or None (with a message) when there is none. Nothing from
    Maxon is kept in the repository."""
    for e in sorted(installs.find_installs(), key=lambda e: e["year"] or 0, reverse=True):
        path = os.path.join(e["path"], "ZStartup", "UserInterfaceColors", "Z4R8_default.cfg")
        try:
            with open(path, "rb") as f:
                colours = zbrush_colors.decode(f.read())
        except OSError:
            continue
        if colours:
            return zbrush_colors.Scheme(e["year"] or 0, path, os.path.getmtime(path), colours, "stock")
    return None


def shot_ring_zbrush(w):
    """The same ring as shot_ring, in the theme a stock ZBrush scheme gives, over a mid-dark grey canvas."""
    w.fans(False)
    im = w.preview("brushes", hover=1, held=True, scale=RING_SCALE)
    return with_cursor(on_background(im, bg=BG_ZBRUSH), *hovered(im))


def shot_fan(w):
    w.fans(True)
    im = w.preview("brushes", hover=(7, 2), open_path=[7], held=True, scale=FAN_SCALE)
    return with_cursor(on_background(im), *hovered(im))


def shot_tags(w):
    im = w.preview("tags", tagged=True, hover=0, held=True, scale=RING_SCALE)
    return with_cursor(on_background(im), *hovered(im))


def animation_panel(w, name, ms):
    im = w.preview("brushes", animation=name, t=ms / 1000, scale=PANEL_SCALE, held=True)
    cx, cy = im.info["centre"]
    panel = Image.new("RGBA", PANEL, BG + (255,))
    panel.alpha_composite(im, (int(round(PANEL_CENTRE[0] - cx)), int(round(PANEL_CENTRE[1] - cy))))
    with_cursor(panel, PANEL_CENTRE[0] + 1, PANEL_CENTRE[1] + 2, 0.75)
    d = ImageDraw.Draw(panel)
    for text, f, y, colour in ((name, font("segoeuib.ttf", 17), 276, TEXT),
                               (f"{ms} ms after opening", font("segoeui.ttf", 14), 302, MUTED)):
        box = d.textbbox((0, 0), text, font=f)
        d.text(((PANEL[0] - (box[2] - box[0])) / 2 - box[0], y - (box[3] - box[1]) / 2 - box[1]), text, font=f,
               fill=colour)
    return panel


def shot_animations(w):
    canvas = Image.new("RGBA", (PANEL[0] * len(ANIMATIONS), PANEL[1]), BG + (255,))
    for i, (name, ms) in enumerate(ANIMATIONS):
        canvas.alpha_composite(animation_panel(w, name, ms), (i * PANEL[0], 0))
    return canvas


# --- the look pictures -------------------------------------------------------------------------------
BRUSHES_14 = ["Standard", "ClayBuildup", "Move", "DamStandard", "TrimDynamic", "hPolish", ("Inflat", "Inflate"),
              "Pinch", "Clay", "ClayTubes", "Move Topological", "SnakeHook", "Flatten", "Layer"]
HUB_BIG = 40                                   # a hub big enough to see its style
HUB_ICON = "ClayBuildup"                       # the icon of the hub in the "icon" style
SHAPE_NAMES = {"circle": "Circle", "rounded": "Rounded square", "squircle": "Squircle", "hexagon": "Hexagon",
               "octagon": "Octagon", "diamond": "Diamond"}
HUB_NAMES = {"dot": "Dot", "disc": "Disc", "ring": "Ring", "icon": "Menu icon"}


def caption(panel, lines):
    """Centred lines of text on a panel: (text, font, y of the middle, colour)."""
    d = ImageDraw.Draw(panel)
    for text, f, y, colour in lines:
        box = d.textbbox((0, 0), text, font=f)
        d.text(((panel.width - (box[2] - box[0])) / 2 - box[0], y - (box[3] - box[1]) / 2 - box[1]), text, font=f,
               fill=colour)


def look_panel(w, title, sub, hover=1, big=False, **kw):
    """A panel like the animation ones: the Brushes ring settled, a slot hovered with the cursor on it, a bold
    title and a muted line under it. big: a larger panel and ring, for a picture with fewer panels. kw goes to
    World.preview (look, styles, fields)."""
    size, centre, scale, ys = (PANEL_BIG, PANEL_BIG_CENTRE, PANEL_BIG_SCALE, (348, 374)) if big else (
        PANEL, PANEL_CENTRE, PANEL_SCALE, (276, 302))
    im = w.preview("brushes", hover=hover, held=True, scale=scale, **kw)
    cx, cy = im.info["centre"]
    panel = Image.new("RGBA", size, BG + (255,))
    panel.alpha_composite(im, (int(round(centre[0] - cx)), int(round(centre[1] - cy))))
    hx, hy = hovered(im)
    with_cursor(panel, centre[0] + hx - cx, centre[1] + hy - cy, 0.75 if not big else 0.9)
    caption(panel, ((title, font("segoeuib.ttf", 17), ys[0], TEXT), (sub, font("segoeui.ttf", 14), ys[1], MUTED)))
    return panel


def gallery(panels, columns):
    """The panels in rows of `columns`, each row centred."""
    w, h = panels[0].size
    rows = [panels[i:i + columns] for i in range(0, len(panels), columns)]
    canvas = Image.new("RGBA", (w * columns, h * len(rows)), BG + (255,))
    for r, row in enumerate(rows):
        left = (columns - len(row)) * w // 2
        for c, panel in enumerate(row):
            canvas.alpha_composite(panel, (left + c * w, r * h))
    return canvas


def shot_slot_shapes(w):
    w.fans(False)
    return gallery([look_panel(w, SHAPE_NAMES[s], f"slot_shape: {s}",
                               look={"slot_shape": s}) for s in looks.SLOT_SHAPES], 3)


def shot_hub_styles(w):
    w.fans(False)
    return gallery([look_panel(w, HUB_NAMES[s], f"hub_style: {s}", look={"hub_style": s, "hub": HUB_BIG},
                               fields={"icon": HUB_ICON}, big=True) for s in looks.HUB_STYLES], 2)


def shot_slot_styles(w):
    """One ring, eight slots styled one way each (the table in docs/appearance.md names them)."""
    w.fans(False)
    styles = {0: {"size": 1.25},                                   # Standard: a bigger slot
              1: {"label_color": "highlight"},                     # ClayBuildup: another label colour
              2: {"border_color": "#7bd88f"},                      # Move: a rim colour
              3: {"slot_shape": "rounded", "slot_corner": 0.42},   # DamStandard: a rounder square
              4: {"border_width": 6, "border_color": "highlight"},  # TrimDynamic: a thick rim
              5: {"glow_color": "#7bd88f"},                        # hPolish: a glow colour (hovered below)
              6: {"icon_scale": 0.6},                              # Inflate: a smaller icon
              8: {"fill_color": "#5b4a9a"}}                        # Tools: a fill colour (no picture covers it)
    im = w.preview("brushes", hover=5, held=True, scale=RING_SCALE, styles=styles)
    return with_cursor(on_background(im), *hovered(im))


def shot_looks(w):
    w.fans(False)
    panels = [look_panel(w, b["label"], f'ring.look: "{name}"', look=name) for name, b in looks.BUILTIN.items()]
    return gallery(panels, 4)


def shot_second_ring(w):
    """14 brushes with when_full "rings": nine on the inner ring, five on an outer ring, one of them hovered."""
    w.fans(False)
    w.define("full14", BRUSHES_14, look={"when_full": "rings"})
    im = w.preview("full14", hover=11, held=True, scale=0.95)
    return with_cursor(on_background(im), *hovered(im))


def shot_file_slots(w):
    """A Capture, a Tool and a Project slot among brushes, with their own icons: the camera, the cube and the folder."""
    w.fans(False)
    menu = w.define("files", ["ClayBuildup", "Move", "DamStandard", "hPolish", "TrimDynamic"], title="Sculpt")
    menu.items += [C.Item(label=label, kind=kind, data={kind: value}) for label, kind, value in FILE_SLOTS]
    im = w.preview("files", hover=7, held=True, scale=RING_SCALE)
    return with_cursor(on_background(im), *hovered(im))


def command_band(frame, text, pressed):
    """The frame with the command above it, as a button on a device or a line in a script would send it."""
    f = font("consola.ttf", 16)
    out = Image.new("RGB", (frame.width, frame.height + COMMAND_BAND), BG)
    out.paste(frame, (0, COMMAND_BAND))
    d = ImageDraw.Draw(out)
    box = d.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0] + 32, box[3] - box[1] + 22
    x, y = (out.width - w) // 2, (COMMAND_BAND - h) // 2 + 4
    d.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=(38, 40, 47), outline=COMMAND_ON if pressed else (78, 81, 91),
                        width=2 if pressed else 1)
    d.text((x + 16 - box[0], y + 11 - box[1]), text, font=f, fill=COMMAND_ON if pressed else TEXT)
    return out


def shot_command_open(w):
    """A command opens the ring at the cursor, the cursor hovers ClayBuildup, and a flick picks it."""
    w.fans(False)
    r = Reel(w, 1.0)
    at = r.offset("brushes", (1,), None)
    r.frames.append((None, (0, 0), 900))       # the command before it runs, with no ring yet
    r.new_ring()
    r.hold("brushes", (0, 0), 0.8)
    r.move("brushes", (0, 0), at, 0.4, (1,), ())
    r.hold("brushes", at, 0.5, (1,))
    r.flick("brushes", at, (at[0] * 1.6, at[1] * 1.6), (1,), ())
    frames, durations = r.save()
    return [command_band(fr, COMMAND, 1 <= i <= 6) for i, fr in enumerate(frames)], durations


def shot_more_slot(w):
    """14 brushes with when_full "more": the ring with More hovered, and the ring More opens beside it."""
    w.fans(False)
    w.define("full14", BRUSHES_14, look={"when_full": "more"})
    first = w.preview("full14", hover=8, held=True, scale=0.95)
    rest = w.ex[False].resolve("more:full14")
    assert rest is not None and len(rest.items) == 14 - 8, "the More slot should hold the last six brushes"
    second = Ring.preview(rest, w.cfg.menus["full14"].look, w.app.icon_for, submenus=w.ex[False].resolve,
                          hover=None, held=True, scale=0.95)
    gap, pad = 70, 20
    height = max(first.height, second.height) + 2 * pad + 40
    canvas = Image.new("RGBA", (first.width + second.width + gap + 2 * pad, height), BG + (255,))
    ring_y = pad
    for im, x in ((first, pad), (second, pad + first.width + gap)):
        canvas.alpha_composite(im, (x, ring_y + (max(first.height, second.height) - im.height) // 2))
    with_cursor(canvas, pad + hovered(first)[0], ring_y + (max(first.height, second.height) - first.height) // 2
                + hovered(first)[1])
    d = ImageDraw.Draw(canvas)                                      # an arrow from the first ring to the second
    y = ring_y + max(first.height, second.height) // 2
    x0, x1 = pad + first.width + 12, pad + first.width + gap - 12
    d.line([(x0, y), (x1, y)], fill=MUTED, width=3)
    d.polygon([(x1 + 8, y), (x1 - 4, y - 8), (x1 - 4, y + 8)], fill=MUTED)
    base = ring_y + max(first.height, second.height) + 14
    for x, wide, title, sub in ((pad, first.width, "More slot", 'when_full: "more", the first eight brushes'),
                                (pad + first.width + gap, second.width, "More opens the rest", "the other six brushes")):
        strip = Image.new("RGBA", (wide, 56), BG + (255,))
        caption(strip, ((title, font("segoeuib.ttf", 17), 14, TEXT), (sub, font("segoeui.ttf", 14), 40, MUTED)))
        canvas.alpha_composite(strip, (x, base - 14))
    return canvas


def save_gif(path, frames, durations):
    """A looping GIF. One palette for every frame, and a frame the same as the one before is dropped (its time added
    to the one kept), so the file stays small enough to put in the README."""
    keep = []
    for f, ms in zip(frames, durations):
        if keep and keep[-1][0].tobytes() == f.tobytes():
            keep[-1][1] += ms
        else:
            keep.append([f, ms])
    step = max(1, len(keep) // 16)
    sample = [f for f, _ in keep[::step]]
    sheet = Image.new("RGB", (sample[0].width, sample[0].height * len(sample)))
    for i, f in enumerate(sample):
        sheet.paste(f, (0, i * f.height))
    palette = sheet.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f, _ in keep]
    out[0].save(path, save_all=True, append_images=out[1:], duration=[ms for _, ms in keep], loop=0,
                optimize=False, disposal=1)


# --- the GIFs ----------------------------------------------------------------------------------------
FRAME_MS = 40                                  # one GIF frame; the cursor and the animations move in these steps
SETTLED_S = 0.8                                # after this long a ring is drawn settled, not mid-animation
CURSOR_OFFSET = (3, 5)                         # the arrow's tip, from a slot's centre, when it is on that slot


def ease(p):
    return p * p * (3 - 2 * p)


class Reel:
    """Frames of a ring with a cursor moving over it, kept as (ring picture, cursor, milliseconds). The cursor is
    relative to the ring centre, and a new ring (a submenu opened as a ring) starts with the cursor in its centre,
    as the app centres it on the cursor. save() lays the pictures out on one fixed canvas."""

    def __init__(self, w, scale):
        self.w, self.scale = w, scale
        self.clock = 0.0                       # seconds since the reel began
        self.born = 0.0                        # when the ring on show was opened
        self.opened = {}                       # fan path -> when it opened
        self.frames = []
        self.cache = {}
        self.near = 0.55 * w.cfg.ring.get("slot", 72) * scale   # how close the cursor is "on" a slot, in pixels

    def new_ring(self):
        self.born, self.opened = self.clock, {}

    def offset(self, menu_id, path, open_path):
        """Where the arrow's tip goes for the slot at path, from the ring centre."""
        im = self.w.preview(menu_id, hover=path, open_path=open_path or None, held=True, scale=self.scale)
        (hx, hy), (cx, cy) = im.info["hover_at"], im.info["centre"]
        return hx - cx + CURSOR_OFFSET[0], hy - cy + CURSOR_OFFSET[1]

    def shot(self, menu_id, hover=None, open_path=()):
        """The ring now, with the fans open as they were (a fan that opens now starts now)."""
        open_path = tuple(open_path)
        prefixes = [open_path[:k] for k in range(1, len(open_path) + 1)]
        self.opened = {p: t for p, t in self.opened.items() if p in prefixes}
        for p in prefixes:
            self.opened.setdefault(p, self.clock)
        age = self.clock - self.born
        ages = {p: round(self.clock - t, 3) for p, t in self.opened.items()}
        key = (menu_id, hover, open_path, None if age > SETTLED_S else round(age, 3), tuple(sorted(ages.items())))
        if key not in self.cache:
            self.cache[key] = self.w.preview(menu_id, hover=hover, open_path=list(open_path) or None, held=True,
                                             scale=self.scale, t=None if age > SETTLED_S else age, open_age=ages)
        return self.cache[key]

    def add(self, im, cur, ms=FRAME_MS):
        self.frames.append((im, cur, ms))
        self.clock += ms / 1000

    def hold(self, menu_id, cur, seconds, hover=None, open_path=()):
        for _ in range(max(1, round(seconds * 1000 / FRAME_MS))):
            self.add(self.shot(menu_id, hover, open_path), cur)

    def move(self, menu_id, a, b, seconds, to_hover, to_open, from_hover=None, from_open=()):
        """The cursor from a to b. The ring shows the old slot hovered while the cursor is near it, nothing hovered
        in between (the fans of the old slot stay), and the new slot once the cursor is near that."""
        n = max(1, round(seconds * 1000 / FRAME_MS))
        for i in range(1, n + 1):
            p = ease(i / n)
            cur = (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)
            if (cur[0] - b[0]) ** 2 + (cur[1] - b[1]) ** 2 <= self.near ** 2:
                self.add(self.shot(menu_id, to_hover, to_open), cur)
            elif (cur[0] - a[0]) ** 2 + (cur[1] - a[1]) ** 2 <= self.near ** 2:
                self.add(self.shot(menu_id, from_hover, from_open), cur)
            else:
                self.add(self.shot(menu_id, None, from_open), cur)

    def flick(self, menu_id, a, b, hover, open_path, seconds=0.12, after=0.8):
        """The cursor flicks on from a to b, the ring goes, and the last picture stays up for a moment."""
        n = max(1, round(seconds * 1000 / FRAME_MS))
        for i in range(1, n + 1):
            p = i / n
            self.add(self.shot(menu_id, hover, open_path), (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p))
        self.frames.append((None, b, int(after * 1000)))

    def save(self, margin=12):
        """(frames, milliseconds): the pictures on one canvas that holds every ring and cursor position."""
        pad = int(24 * self.scale)
        left = top = right = bottom = 0
        for im, cur, _ in self.frames:
            if im is not None:
                cx, cy = im.info["centre"]
                left, top = max(left, cx), max(top, cy)
                right, bottom = max(right, im.size[0] - cx), max(bottom, im.size[1] - cy)
            left, top = max(left, pad - cur[0]), max(top, pad - cur[1])
            right, bottom = max(right, cur[0] + pad), max(bottom, cur[1] + pad)
        left, top, right, bottom = (int(v) + margin for v in (left, top, right, bottom))
        out = []
        for im, cur, _ in self.frames:
            canvas = Image.new("RGBA", (left + right, top + bottom), BG + (255,))
            if im is not None:
                cx, cy = im.info["centre"]
                canvas.alpha_composite(im, (int(round(left - cx)), int(round(top - cy))))
            out.append(with_cursor(canvas, left + cur[0], top + cur[1]).convert("RGB"))
        return out, [ms for _, _, ms in self.frames]


def shot_open_animation(w):
    """Holding Q: the ring opens, the cursor hovers two brushes, More Brushes opens as a ring on hover, and a flick
    picks ClayTubes."""
    w.fans(False)
    r = Reel(w, 1.0)
    at = {i: r.offset("brushes", (i,), None) for i in (1, 2, 7)}
    tubes = r.offset("more", (2,), None)
    r.new_ring()
    r.hold("brushes", (0, 0), 0.8)             # opening, with the cursor in the centre
    r.move("brushes", (0, 0), at[1], 0.4, (1,), ())
    r.hold("brushes", at[1], 0.4, (1,))
    r.move("brushes", at[1], at[2], 0.3, (2,), (), (1,))
    r.hold("brushes", at[2], 0.4, (2,))
    r.move("brushes", at[2], at[7], 0.6, (7,), (), (2,))
    r.hold("brushes", at[7], 0.3, (7,))
    r.new_ring()                               # More Brushes opens, centred on the cursor
    r.hold("more", (0, 0), 0.7)
    r.move("more", (0, 0), tubes, 0.4, (2,), ())
    r.hold("more", tubes, 0.5, (2,))
    r.flick("more", tubes, (tubes[0] * 1.6, tubes[1] * 1.6), (2,), ())
    return r.save()


def shot_fan_out(w):
    """Holding Q: hovering More Brushes fans its brushes out to the left; moving to Tools fans out its switches,
    SubDivide fans out its sizes above that, and a flick past 1.00 picks it."""
    w.fans(True)
    r = Reel(w, 0.85)
    more, tubes = r.offset("brushes", (7,), None), r.offset("brushes", (7, 2), [7])
    tools, subdiv = r.offset("brushes", (8,), None), r.offset("brushes", (8, 7), [8])
    size = r.offset("brushes", (8, 7, 3), [8, 7])
    r.new_ring()
    r.hold("brushes", (0, 0), 0.8)
    r.move("brushes", (0, 0), more, 0.5, (7,), (7,))
    r.hold("brushes", more, 0.6, (7,), (7,))
    r.move("brushes", more, tubes, 0.35, (7, 2), (7,), (7,), (7,))
    r.hold("brushes", tubes, 0.5, (7, 2), (7,))
    r.move("brushes", tubes, tools, 0.7, (8,), (8,), None, (7,))
    r.hold("brushes", tools, 0.7, (8,), (8,))
    r.move("brushes", tools, subdiv, 0.4, (8, 7), (8, 7), (8,), (8,))
    r.hold("brushes", subdiv, 0.7, (8, 7), (8, 7))
    r.move("brushes", subdiv, size, 0.35, (8, 7, 3), (8, 7), (8, 7), (8, 7))
    r.hold("brushes", size, 0.4, (8, 7, 3), (8, 7))
    past = (size[0] + (size[0] - subdiv[0]) * 0.8, size[1] + (size[1] - subdiv[1]) * 0.8)
    r.flick("brushes", size, past, (8, 7, 3), (8, 7))
    return r.save()


def shot_empty_slots(w):
    """The Brushes ring as shipped, then with Move deleted: keep_slots off (the rest close up) and on (Move's slot
    stays empty). DamStandard is hovered in each, so the eye can follow it."""
    w.fans(False)
    items = w.cfg.menus["brushes"].items
    move = next(i for i, it in enumerate(items) if it.data.get("brush") == "Move")
    dam = next(i for i, it in enumerate(items) if it.data.get("brush") == "DamStandard")
    empty = C.Item(label="", kind="empty", data={"empty": True})
    closed = items[:move] + items[move + 1:]
    kept = items[:move] + [empty] + items[move + 1:]
    return gallery([look_panel(w, "As shipped", "the starter Brushes menu", hover=dam, big=True),
                    look_panel(w, "Keep slots in place off", "Move deleted: the rest close up", hover=dam - 1,
                               big=True, fields={"items": closed}),
                    look_panel(w, "Keep slots in place on", "Move deleted: its slot stays empty", hover=dam,
                               big=True, fields={"items": kept})], 3)


def bezier_ease(t, x1=0.42, y1=0.0, x2=0.58, y2=1.0):
    """CSS ease-in-out: the progress for time t (0 to 1), as the browser works it out for Studio's glide."""
    def at(u, a, b):
        return 3 * (1 - u) ** 2 * u * a + 3 * (1 - u) * u ** 2 * b + u ** 3
    lo, hi = 0.0, 1.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if at(mid, x1, x2) < t:
            lo = mid
        else:
            hi = mid
    return at((lo + hi) / 2, y1, y2)


GLIDE_MS = 250                                 # Studio's swap: the pictures of the two slots glide across in this time
GLIDE_FRAME_MS = 20


def slot_geometry(im, i):
    """Slot i of a ring picture: where it is from the ring centre, how far, its angle and its size."""
    s = next(s for s in im.info["layout"]["slots"] if s["i"] == i)
    return {"x": s["x"], "y": s["y"], "r": (s["x"] ** 2 + s["y"] ** 2) ** 0.5,
            "a": math.degrees(math.atan2(s["x"], -s["y"])), "size": s["size"]}


def glide_frame(before, after, moves, ms):
    """The ring part way through Studio's swap. The old picture has holes where the moved slots were, and a copy of
    each moved slot's picture glides along an arc to the other's place (app.js, makeRingView: glide). moves is
    [(from slot, to slot), ...]; ms is the time since the drop. Returns the picture and its ring centre."""
    if ms >= GLIDE_MS:
        return after
    cx, cy = before.info["centre"]
    base = before.copy()
    mask = Image.new("L", base.size, 255)
    md = ImageDraw.Draw(mask)
    for i in {i for m in moves for i in m}:
        g = slot_geometry(before, i)
        rad = g["size"] * 0.56
        md.ellipse([cx + g["x"] - rad, cy + g["y"] - rad, cx + g["x"] + rad, cy + g["y"] + rad], fill=0)
    alpha = ImageChops.multiply(base.getchannel("A"), mask)
    base.putalpha(alpha)
    p = bezier_ease(ms / GLIDE_MS)
    for n, (a, b) in enumerate(moves):
        f, t = slot_geometry(before, a), slot_geometry(before, b)
        d = ((t["a"] - f["a"] + 540) % 360) - 180                          # the short way round
        mid = (f["r"] + t["r"]) / 2 + ((-1 if n else 1) * 0.45 * f["size"] if len(moves) > 1 else 0)
        r = f["r"] + (mid - f["r"]) * (p / 0.5) if p < 0.5 else mid + (t["r"] - mid) * ((p - 0.5) / 0.5)
        ang = math.radians(f["a"] + d * p)
        gs = int(round(f["size"] * 1.2))
        box = (int(round(cx + f["x"] - gs / 2)), int(round(cy + f["y"] - gs / 2)))
        ghost = before.crop((box[0], box[1], box[0] + gs, box[1] + gs))
        base.alpha_composite(ghost, (int(round(cx + r * math.sin(ang) - gs / 2)), int(round(cy - r * math.cos(ang) - gs / 2))))
    base.info = dict(before.info)
    return base


def drag_hint(canvas, x, y, text):
    """The small hint Studio shows under the pointer while an item is dragged over a slot."""
    f = font("segoeui.ttf", 13)
    d = ImageDraw.Draw(canvas)
    box = d.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0] + 20, box[3] - box[1] + 14
    if x + w > canvas.width - 6:                                            # no room on the right of the pointer: to its left
        x -= w + 28
    d.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=(38, 40, 47, 255), outline=(78, 81, 91, 255))
    d.text((x + 10 - box[0], y + 7 - box[1]), text, font=f, fill=TEXT)


def shot_slot_move(w):
    """Studio's ring preview with Keep slots in place on: a brush is dragged onto an empty slot and glides there, then
    two brushes swap places, passing each other on an outer and an inner lane."""
    w.fans(False)
    items = list(w.cfg.menus["brushes"].items)
    move = next(i for i, it in enumerate(items) if it.data.get("brush") == "Move")
    empty = C.Item(label="", kind="empty", data={"empty": True})
    s0 = items[:move] + [empty] + items[move + 1:]
    s1 = list(s0)
    s1[move], s1[move + 1] = s0[move + 1], s0[move]                         # DamStandard moves into the empty slot
    s2 = list(s1)
    s2[1], s2[5] = s1[5], s1[1]                                             # ClayBuildup and hPolish swap
    scale = 0.9
    pic = lambda its, hover=None: w.preview("brushes", hover=hover, held=True, scale=scale, fields={"items": its})
    ring = {k: pic(v) for k, v in (("s0", s0), ("s1", s1), ("s2", s2))}
    margin = 70
    cx, cy = ring["s0"].info["centre"]
    size = (ring["s0"].width + 2 * margin, ring["s0"].height + 2 * margin)
    out, times = [], []

    def put(im, cur=None, drag=None, hint=None, ms=FRAME_MS):
        canvas = Image.new("RGBA", size, BG + (255,))
        canvas.alpha_composite(im, (int(round(margin + cx - im.info["centre"][0])), int(round(margin + cy - im.info["centre"][1]))))
        if drag is not None:                                                # the picture of the brush being dragged
            gs = drag.width
            canvas.alpha_composite(drag, (int(round(margin + cx + cur[0] - gs / 2)), int(round(margin + cy + cur[1] - gs / 2))))
        if hint:
            drag_hint(canvas, margin + cx + cur[0] + 16, margin + cy + cur[1] + 22, hint)
        if cur is not None:
            with_cursor(canvas, margin + cx + cur[0], margin + cy + cur[1], 0.9)
        out.append(canvas.convert("RGB"))
        times.append(ms)

    def slot_at(im, i):
        g = slot_geometry(im, i)
        return g["x"] + CURSOR_OFFSET[0], g["y"] + CURSOR_OFFSET[1]

    def lift(im, i):
        """A translucent copy of slot i's picture, to ride along with the pointer."""
        g = slot_geometry(im, i)
        gs = int(round(g["size"] * 1.1))
        c = im.info["centre"]
        crop = im.crop((int(c[0] + g["x"] - gs / 2), int(c[1] + g["y"] - gs / 2), int(c[0] + g["x"] - gs / 2) + gs, int(c[1] + g["y"] - gs / 2) + gs))
        crop.putalpha(crop.getchannel("A").point(lambda v: int(v * 0.78)))
        return crop

    def travel(a, b, ms, im, hover_from=None, drag=None, hint=None, hint_from=0.7):
        n = max(1, round(ms / FRAME_MS))
        for k in range(1, n + 1):
            p = ease(k / n)
            cur = (a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p)
            put(im, cur, drag, hint if (drag is not None and k / n >= hint_from) else None)

    def still(im, cur, ms):
        for _ in range(max(1, round(ms / FRAME_MS))):
            put(im, cur)

    def drop(before, after, moves, cur):
        for t in range(GLIDE_FRAME_MS, GLIDE_MS + 1, GLIDE_FRAME_MS):
            put(glide_frame(before, after, moves, t), cur, ms=GLIDE_FRAME_MS)

    away = (ring["s0"].width - cx - 10, -cy + 30)                           # outside the ring, top right
    # one: DamStandard onto the empty slot
    src, dst = slot_at(ring["s0"], move + 1), slot_at(ring["s0"], move)
    still(ring["s0"], away, 700)
    travel(away, src, 450, ring["s0"])
    still(pic(s0, move + 1), src, 300)
    travel(src, dst, 520, ring["s0"], drag=lift(ring["s0"], move + 1), hint="Move to empty slot")
    still_drag = lift(ring["s0"], move + 1)
    for _ in range(8):
        put(ring["s0"], dst, still_drag, "Move to empty slot")
    drop(ring["s0"], ring["s1"], [(move + 1, move)], dst)
    still(ring["s1"], dst, 900)
    # two: ClayBuildup and hPolish swap
    a, b = slot_at(ring["s1"], 1), slot_at(ring["s1"], 5)
    travel(dst, a, 450, ring["s1"])
    still(pic(s1, 1), a, 300)
    travel(a, b, 700, ring["s1"], drag=lift(ring["s1"], 1), hint="Swap with hPolish")
    still_drag = lift(ring["s1"], 1)
    for _ in range(8):
        put(ring["s1"], b, still_drag, "Swap with hPolish")
    drop(ring["s1"], ring["s2"], [(1, 5), (5, 1)], b)
    still(ring["s2"], b, 1300)
    return out, times


# name -> (file, function, what it shows)
SHOTS = {
    "ring": ("ring.png", shot_ring, "the starter Brushes menu in hold mode, ClayBuildup hovered, cursor on it"),
    "ring-light": ("ring-light.png", shot_ring_light,
                   "the same ring as ring.png in the Light theme, over a light grey canvas"),
    "ring-zbrush": ("ring-zbrush.png", shot_ring_zbrush,
                    "the same ring as ring.png in the theme a stock ZBrush scheme gives (Match ZBrush), over a dark grey"),
    "slot-shapes": ("slot-shapes.png", shot_slot_shapes,
                    "the Brushes ring in each of the six slot shapes, one panel each, the shape named under it"),
    "hub-styles": ("hub-styles.png", shot_hub_styles,
                   "the Brushes ring with a 40 px hub in each of the four hub styles, one panel each"),
    "slot-styles": ("slot-styles.png", shot_slot_styles,
                    "one Brushes ring with a style on eight slots: size, label colour, rim colour, rounder corners, "
                    "thick rim, glow colour (hovered), smaller icon, fill colour"),
    "looks": ("looks.png", shot_looks, "the Brushes ring in each of the seven built-in looks, one panel each"),
    "second-ring": ("second-ring.png", shot_second_ring,
                    "14 brushes with when_full rings: nine on the inner ring, five on an outer ring"),
    "more-slot": ("more-slot.png", shot_more_slot,
                  "14 brushes with when_full more: the ring with More hovered, and the ring More opens beside it"),
    "empty-slots": ("empty-slots.png", shot_empty_slots,
                    "the Brushes ring as shipped, then with Move deleted with Keep slots in place off and on, "
                    "DamStandard hovered in each"),
    "slot-move": ("slot-move.gif", shot_slot_move,
                  "Keep slots in place on: a brush is dragged onto an empty slot and glides there, then two brushes "
                  "swap places"),
    "fan": ("fan.png", shot_fan, "More Brushes fanned out to the left, ClayTubes in the fan hovered, cursor on it"),
    "tag-colours": ("tag-colours.png", shot_tags, "eight brushes in two tags and two untagged, ClayBuildup hovered"),
    "animations": ("animations.png", shot_animations, "the five open animations part way through opening"),
    "open-animation": ("open-animation.gif", shot_open_animation,
                       "the ring opens, two brushes are hovered, More Brushes opens as a ring, a flick picks ClayTubes"),
    "fan-out": ("fan-out.gif", shot_fan_out,
                "More Brushes fans out, then Tools, SubDivide fans out above it, a flick past 1.00 picks it"),
    "file-slots": ("file-slots.png", shot_file_slots,
                   "five brushes with a Capture, a Tool and a Project slot, the Project slot hovered"),
    "command-open": ("command-open.gif", shot_command_open,
                     "the command lights up, the ring opens at the cursor, a flick picks ClayBuildup"),
}


def main(argv):
    global OUT
    args = list(argv)
    if "--out" in args:
        i = args.index("--out")
        OUT = os.path.abspath(args[i + 1])
        del args[i:i + 2]
    unknown = [a for a in args if a not in SHOTS]
    if unknown:
        sys.exit(f"unknown picture {unknown[0]!r}; the pictures are: {', '.join(SHOTS)}")
    os.makedirs(OUT, exist_ok=True)
    worlds = {}
    for name in args or SHOTS:
        file, make, _ = SHOTS[name]
        theme = "light" if make is shot_ring_light else "zbrush" if make is shot_ring_zbrush else "dark"
        if theme == "zbrush" and theme not in worlds:
            scheme = stock_scheme()
            if scheme is None:
                print("skipped", file, "- no installed ZBrush has ZStartup/UserInterfaceColors/Z4R8_default.cfg")
                continue
            zbrush_colors.current = lambda: scheme     # theme.py asks here for the colours Match ZBrush uses
        if theme not in worlds:                # one world for each theme, made when a picture needs it
            worlds[theme] = World(theme)
        result = make(worlds[theme])
        path = os.path.join(OUT, file)
        if isinstance(result, tuple):          # a GIF: (frames, milliseconds for each)
            save_gif(path, *result)
        else:
            result.convert("RGB").save(path, optimize=True)
        print("wrote", path)


if __name__ == "__main__":
    main(sys.argv[1:])
