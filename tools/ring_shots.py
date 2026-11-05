"""Draws the ring pictures in docs/images (ring.png, ring-light.png, ring-zbrush.png, fan.png, tag-colours.png,
animations.png, the look pictures slot-shapes.png, hub-styles.png, slot-styles.png, looks.png, second-ring.png,
more-slot.png and empty-slots.png, and the GIFs) with the real renderer, zorbit/ring.py, so they follow the ring's look whenever it
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
import colorsys
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
LAYOUT_SLOTS = [("Sculpt", "D:/Layouts/Sculpt.cfg"), ("Paint", "D:/Layouts/Paint.cfg"),   # the layout slots picture: label, path
                ("Minimal", "D:/Layouts/Minimal.cfg")]
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


def shot_layout_slots(w):
    """Three Layout slots among brushes, with their own icon."""
    w.fans(False)
    menu = w.define("layouts", ["ClayBuildup", "Move", "DamStandard", "hPolish", "TrimDynamic"], title="Sculpt")
    menu.items += [C.Item(label=label, kind="layout", data={"layout": path}) for label, path in LAYOUT_SLOTS]
    im = w.preview("layouts", hover=6, held=True, scale=RING_SCALE)
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


def save_gif(path, frames, durations, chapters=None):
    """A looping GIF. One palette for every frame (or for every chapter, when chapters gives each frame's number), and
    a frame the same as the one before is dropped (its time added to the one kept), so the file stays small enough to
    put in the README."""
    keep = []
    for f, ms, ch in zip(frames, durations, chapters or [0] * len(frames)):
        if keep and keep[-1][2] == ch and keep[-1][0].tobytes() == f.tobytes():
            keep[-1][1] += ms
        else:
            keep.append([f, ms, ch])
    palettes = {}
    for ch in {k[2] for k in keep}:
        some = [k[0] for k in keep if k[2] == ch]
        sample = some[::max(1, len(some) // 16)]
        sheet = Image.new("RGB", (sample[0].width, sample[0].height * len(sample)))
        for i, f in enumerate(sample):
            sheet.paste(f, (0, i * f.height))
        # 255: Pillow needs a free colour to make the pixels that did not change transparent (optimize=True)
        palettes[ch] = sheet.quantize(255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    out = [f.quantize(palette=palettes[ch], dither=Image.Dither.NONE) for f, _, ch in keep]
    out[0].save(path, save_all=True, append_images=out[1:], duration=[k[1] for k in keep], loop=0,
                optimize=True, disposal=1)


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


def shot_held_slot(w):
    """The Brushes ring with Move's slot waiting for a target: as it was before 0.20.0 (the rest close up) and as it is
    now (its slot holds its place as an empty outline). DamStandard is hovered in each, so the eye can follow it."""
    w.fans(False)
    items = w.cfg.menus["brushes"].items
    move = next(i for i, it in enumerate(items) if it.data.get("brush") == "Move")
    dam = next(i for i, it in enumerate(items) if it.data.get("brush") == "DamStandard")
    empty = C.Item(label="", kind="empty", data={"empty": True})
    return gallery([look_panel(w, "Before 0.20.0", "A slot with no target yet: the rest close up", hover=dam - 1, big=True,
                               fields={"items": items[:move] + items[move + 1:]}),
                    look_panel(w, "Now", "A slot with no target yet holds its place", hover=dam, big=True,
                               fields={"items": items[:move] + [empty] + items[move + 1:]})], 2)


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


# --- the trailer -------------------------------------------------------------------------------------
TRAILER_BOX = (480, 485)                       # where the ring stays, always; the caption goes under it
TRAILER_SIZE = (480, 548)
TRAILER_SCALE = 0.92
TRAILER_SWEEP_MS = 60                          # a slider or a zoom: one frame every so long, to keep the file small
TRAILER_PACE = 1.15                            # every hold and slider takes this much longer than shot_trailer says
TRAILER_MARGIN = 10                            # what fit() leaves clear inside the box


def open_ages(opened, clock, open_path):
    """{fan path: seconds since it opened} for the fans on open_path, None for one that has settled."""
    ages = {}
    for k in range(1, len(open_path) + 1):
        age = round(clock - opened.get(open_path[:k], clock), 3)
        ages[open_path[:k]] = None if age > 0.5 else age
    return ages


class Trailer:
    """One ring on a canvas of a fixed size, whose settings change under a caption. The cursor glides to the slot a
    frame hovers, and a slot only lights up once the cursor is there. fit() eases the ring smaller and aside when
    something would not fit (a fan, a full ring), so the canvas never grows. Anything that still leaves the box is
    listed in self.clipped."""

    def __init__(self, w):
        self.w = w
        self.frames, self.times, self.chapters = [], [], []
        self.chapter = 0
        self.zoom, self.zoom_to = TRAILER_SCALE, TRAILER_SCALE
        self.shift, self.shift_to = (0.0, 0.0), (0.0, 0.0)
        self.cur = (40.0, 60.0)
        self.clock = 0.0
        self.opened = {}                       # fan path -> when it opened
        self.was_open = ()
        self.clipped = set()
        self.last = (None, None)

    def next_chapter(self):
        self.chapter += 1

    def put(self, canvas, ms):
        if self.frames and self.chapters[-1] == self.chapter and self.frames[-1].tobytes() == canvas.tobytes():
            self.times[-1] += ms
        else:
            self.frames.append(canvas)
            self.times.append(ms)
            self.chapters.append(self.chapter)
        self.clock += ms / 1000

    def picture(self, menu, world, **state):
        key = (menu, id(world), self.zoom, repr(sorted(state.items(), key=lambda kv: kv[0])))
        if self.last[0] != key:
            self.last = (key, (world or self.w).preview(menu, held=True, scale=self.zoom, **state))
        return self.last[1]

    def fit(self, *states):
        """Sets where the ring eases to: small enough, and moved over enough, for all of these states to fit in the
        box. A state is a dict of frame() arguments. No states: back to its normal size in the middle."""
        self.zoom_to, self.shift_to = TRAILER_SCALE, (0.0, 0.0)
        if not states:
            return
        left = top = right = bottom = 0.0
        for st in states:
            st = dict(st)
            menu = st.pop("menu", "brushes")
            world = st.pop("world", None) or self.w
            im = world.preview(menu, held=True, scale=TRAILER_SCALE, **st)
            cx, cy = im.info["centre"]
            box = im.getchannel("A").getbbox()
            left, top = min(left, box[0] - cx), min(top, box[1] - cy)
            right, bottom = max(right, box[2] - cx), max(bottom, box[3] - cy)
        room = 2 * TRAILER_MARGIN
        k = min(1.0, (TRAILER_BOX[0] - room) / (right - left), (TRAILER_BOX[1] - room) / (bottom - top))
        self.zoom_to = TRAILER_SCALE * k
        self.shift_to = (-(left + right) / 2 * k, -(top + bottom) / 2 * k)

    def ease_view(self):
        self.zoom += (self.zoom_to - self.zoom) * 0.3
        if abs(self.zoom - self.zoom_to) < 0.003:
            self.zoom = self.zoom_to
        x, y = (self.shift[i] + (self.shift_to[i] - self.shift[i]) * 0.3 for i in (0, 1))
        self.shift = (self.shift_to[0] if abs(x - self.shift_to[0]) < 0.5 else x,
                      self.shift_to[1] if abs(y - self.shift_to[1]) < 0.5 else y)

    def frame(self, title, value, menu="brushes", hover=None, open_path=(), at=None, world=None, bg=BG,
              ink=(TEXT, MUTED), ms=FRAME_MS, **state):
        """One frame. state goes to World.preview (look, styles, fields, tagged, animation, t)."""
        self.ease_view()
        open_path = tuple(open_path)
        im = self.picture(menu, world, hover=hover, open_path=list(open_path) or None,
                          open_age=open_ages(self.opened, self.clock, open_path), **state)
        if hover is not None and "hover_at" in im.info:
            at = (im.info["hover_at"][0] - im.info["centre"][0] + CURSOR_OFFSET[0],
                  im.info["hover_at"][1] - im.info["centre"][1] + CURSOR_OFFSET[1])
        if at is not None:
            x, y = (self.cur[i] + (at[i] - self.cur[i]) * 0.3 for i in (0, 1))
            self.cur = (at[0] if abs(x - at[0]) < 0.6 else x, at[1] if abs(y - at[1]) < 0.6 else y)
            if hover is not None and (self.cur[0] - at[0]) ** 2 + (self.cur[1] - at[1]) ** 2 > (28 * self.zoom) ** 2:
                open_path = self.was_open              # still on its way: nothing lit, no new fan
                im = self.picture(menu, world, hover=None, open_path=list(open_path) or None,
                                  open_age=open_ages(self.opened, self.clock, open_path), **state)
        self.opened = {open_path[:k]: self.opened.get(open_path[:k], self.clock)
                       for k in range(1, len(open_path) + 1)}
        self.was_open = open_path
        cx, cy = TRAILER_BOX[0] / 2 + self.shift[0], TRAILER_BOX[1] / 2 + self.shift[1]
        x, y = int(round(cx - im.info["centre"][0])), int(round(cy - im.info["centre"][1]))
        box = im.getchannel("A").getbbox()
        if box and (x + box[0] < 0 or y + box[1] < 0 or x + box[2] > TRAILER_BOX[0] or y + box[3] > TRAILER_BOX[1]):
            self.clipped.add(f"{title}: {value}")
        canvas = Image.new("RGBA", TRAILER_SIZE, bg + (255,))
        canvas.paste(im, (x, y), im)
        canvas.paste(bg + (255,), (0, TRAILER_BOX[1], TRAILER_SIZE[0], TRAILER_SIZE[1]))
        with_cursor(canvas, cx + self.cur[0], cy + self.cur[1])
        caption(canvas, ((title, font("segoeuib.ttf", 19), TRAILER_BOX[1] + 19, ink[0]),
                         (value, font("segoeui.ttf", 15), TRAILER_BOX[1] + 44, ink[1])))
        self.put(canvas.convert("RGB"), ms)

    def settle(self, title, value, **state):
        """Frames of this state until the ring is where fit() said. A fan opens after this, so it opens inside the box."""
        while self.zoom != self.zoom_to or self.shift != self.shift_to:
            self.frame(title, value, ms=TRAILER_SWEEP_MS, **state)

    def hold(self, title, value, seconds, **state):
        for _ in range(max(1, round(seconds * TRAILER_PACE * 1000 / FRAME_MS))):
            self.frame(title, value, **state)

    def steps(self, title, values, seconds, **common):
        """One setting going through its values: values is [(the value to show, frame arguments), ...]."""
        for value, state in values:
            self.hold(title, value, seconds, **{**common, **state})

    def sweep(self, title, fmt, stops, seconds, state, **common):
        """A slider moved smoothly through stops. state(v) gives the frame arguments for the value v."""
        n = max(1, round(seconds * TRAILER_PACE * 1000 / TRAILER_SWEEP_MS / (len(stops) - 1)))
        for a, b in zip(stops, stops[1:]):
            for k in range(1, n + 1):
                v = a + (b - a) * ease(k / n)
                self.frame(title, fmt.format(v), ms=TRAILER_SWEEP_MS, **{**common, **state(v)})

    def play(self, title, value, animation, seconds, after=0.25, **common):
        """The ring opening around the cursor, with this open animation."""
        self.cur = (0.0, 0.0)
        for k in range(max(1, round(seconds * 1000 / FRAME_MS))):
            self.frame(title, value, at=(0, 0), animation=animation, t=k * FRAME_MS / 1000, **common)
        self.hold(title, value, after, at=(0, 0), **common)


def hue(h):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 0.72, 0.97)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def shot_trailer(w):
    """The ring's settings in turn on one ring, with a caption naming each the way Studio's Look screen does. The most
    striking come first, to catch the eye, and the plain sliders last, so it ends on the ring as it starts and loops."""
    w.fans(False)
    t = Trailer(w)
    items = w.cfg.menus["brushes"].items
    empty = C.Item(label="", kind="empty", data={"empty": True})

    t.next_chapter()
    t.play("The ring", "as it starts", "smooth", 0.3, after=0.4)

    t.next_chapter()
    t.steps("Looks", [(b["label"], {"look": name}) for name, b in looks.BUILTIN.items()], 0.6, hover=1)

    # The canvas never grows: the ring zooms out first, and only then does the fan open.
    t.next_chapter()
    w.fans(True)
    open_more = {"hover": (7,), "open_path": [7]}
    in_more = {"hover": (7, 2), "open_path": [7]}
    open_tools = {"hover": (8,), "open_path": [8]}
    on_sub = {"hover": (8, 7), "open_path": [8]}
    open_sub = {"hover": (8, 7), "open_path": [8, 7]}
    in_sub = {"hover": (8, 7, 3), "open_path": [8, 7]}
    beside = "A submenu opens beside its slot"
    nested = "One fan inside another"
    t.hold("Fans", beside, 0.35, hover=(7,))
    t.fit(open_more, in_more)
    t.settle("Fans", beside, hover=(7,))
    t.hold("Fans", beside, 0.5, **open_more)
    t.hold("Fans", beside, 0.5, **in_more)
    t.fit(open_more, in_more, open_tools, on_sub)
    t.settle("Fans", nested, **in_more)
    t.hold("Fans", nested, 0.5, **open_tools)
    t.hold("Fans", nested, 0.3, **on_sub)
    t.fit(open_tools, on_sub, open_sub, in_sub)
    t.settle("Fans", nested, **on_sub)
    t.hold("Fans", nested, 0.4, **open_sub)
    t.hold("Fans", nested, 0.6, **in_sub)
    t.hold("Fans", nested, 0.3, hover=1)
    t.fit()
    t.settle("Fans", nested, hover=1)
    w.fans(False)

    t.next_chapter()
    t.steps("Tag colours", [(n, {"look": {"tag_colors": v, "tag_band": "none", "tag_glow_opacity": 0.7}})
                            for n, v in (("Off", "none"), ("Icon tint", "tint"), ("Glow", "glow"),
                                         ("Tint and glow", "both"))], 0.45, menu="tags", tagged=True, hover=0)
    t.steps("Tag colours: Band", [(n, {"look": {"tag_band": n.lower()}})
                                  for n in ("Hairline", "Narrow", "Medium", "Wide")], 0.3, menu="tags", tagged=True,
            hover=0)

    t.next_chapter()
    t.steps("Slot shape", [(SHAPE_NAMES[s], {"look": {"slot_shape": s}})
                           for s in looks.SLOT_SHAPES[1:] + looks.SLOT_SHAPES[:1]], 0.45, hover=2)

    t.next_chapter()
    t.sweep("Colours", "Accent and lines", [0.05, 1.05], 1.8,
            lambda v: {"look": {"colors": {"accent": hue(v), "lines": hue(v)}}}, hover=1)
    t.next_chapter()
    t.hold("Theme", "Dark", 0.6, hover=1)
    t.next_chapter()
    light = World("light")
    light.fans(False)
    t.hold("Theme", "Light", 0.7, hover=1, world=light, bg=BG_LIGHT, ink=((27, 28, 32), (70, 72, 80)))
    scheme = stock_scheme()
    if scheme is not None:
        t.next_chapter()
        zbrush_colors.current = lambda: scheme
        zb = World("zbrush")
        zb.fans(False)
        t.hold("Theme", "Match ZBrush", 0.7, hover=1, world=zb, bg=BG_ZBRUSH)

    t.next_chapter()
    full = w.define("trailer-full", BRUSHES_14)
    rings = {"menu": "trailer-full", "look": {"when_full": "rings"}}

    def grow(n):
        return {"menu": "trailer-full", "fields": {"items": full.items[:n]}, "look": {"when_full": "grow"}}

    t.fit(dict(hover=0, **grow(14)), dict(hover=11, **rings))
    t.settle("When full: Grow", "9 brushes", hover=8, **grow(9))
    for n in range(9, 15):
        t.hold("When full: Grow", f"{n} brushes", 0.22, hover=n - 1, **grow(n))
    t.hold("When full: Second ring", "14 brushes", 0.9, hover=11, **rings)
    t.hold("When full: More slot", "the first eight, then More", 0.9, hover=8, menu="trailer-full",
           look={"when_full": "more"})
    t.fit()

    t.next_chapter()
    styles = {}
    for name, i, style, what in (("Standard", 0, {"size": 1.25}, "bigger"),
                                 ("ClayBuildup", 1, {"label_color": "highlight"}, "label colour"),
                                 ("Move", 2, {"border_color": "#7bd88f"}, "rim colour"),
                                 ("DamStandard", 3, {"slot_shape": "rounded", "slot_corner": 0.42}, "its own shape"),
                                 ("TrimDynamic", 4, {"border_width": 6, "border_color": "highlight"}, "thick rim"),
                                 ("hPolish", 5, {"glow_color": "#7bd88f"}, "glow colour"),
                                 ("Inflate", 6, {"icon_scale": 0.6}, "smaller icon"),
                                 ("Tools", 8, {"fill_color": "#5b4a9a"}, "fill colour")):
        styles = {**styles, i: style}
        t.hold("One slot", f"{name}: {what}", 0.4, hover=i, styles=styles)

    t.next_chapter()
    t.steps("Glow colour", [("Automatic", {"look": {"glow_opacity": 0.9}, "hover": 4}),
                            ("Highlight", {"look": {"glow_opacity": 0.9, "glow_color": "highlight"}, "hover": 5}),
                            ("Green", {"look": {"glow_opacity": 0.9, "glow_color": "#7bd88f"}, "hover": 6}),
                            ("Pink", {"look": {"glow_opacity": 0.9, "glow_color": "#ff6fb5"}, "hover": 0})], 0.5)
    t.sweep("Glow strength", "{:.0%}", [0.55, 1, 0, 0.55], 1.0, lambda v: {"look": {"glow_opacity": round(v, 3)}},
            hover=0)

    t.next_chapter()
    its = list(items)
    t.hold("Empty slots", "A full ring", 0.3, hover=1, fields={"items": its})
    for n in (2, 6, 4, 0):
        its = list(its)
        its[n] = empty
        t.hold("Empty slots", f"{items[n].label} deleted: its slot stays", 0.35, hover=1, fields={"items": its})
    t.steps("Empty slots", [("They take the slot shape", {"look": {"slot_shape": s}})
                            for s in ("hexagon", "diamond", "rounded")], 0.35, hover=1, fields={"items": its})

    t.next_chapter()
    icon = {"fields": {"icon": HUB_ICON}}
    t.steps("Hub style", [(HUB_NAMES[s], {"look": {"hub_style": s, "hub": HUB_BIG}, **icon})
                          for s in looks.HUB_STYLES], 0.45, at=(0, 0))
    t.sweep("Hub size", "{:.0f} px", [40, 64, 0, 40], 1.0, lambda v: {"look": {"hub_style": "ring", "hub": round(v)}},
            at=(0, 0))
    t.sweep("Hub glow", "{:.0%}", [1, 0, 1], 0.8,
            lambda v: {"look": {"hub_style": "disc", "hub": HUB_BIG, "hub_glow": round(v, 3)}}, at=(0, 0))
    t.steps("Hub colour", [(n, {"look": {"hub_style": "disc", "hub": HUB_BIG, "hub_color": c}})
                           for n, c in (("Accent", "accent"), ("Highlight", "highlight"), ("Green", "#7bd88f"))],
            0.3, at=(0, 0))

    t.next_chapter()
    t.steps("Labels", [("Icon only", {"look": {"labels": "none"}}), ("Icon and name", {})], 0.45, hover=1)
    t.steps("Label colour", [(n, {"look": {"label_color": c}})
                             for n, c in (("Highlight", "highlight"), ("Accent", "accent"), ("Green", "#7bd88f"))],
            0.3, hover=1)
    t.sweep("Ring radius", "{:.0f} px", [145, 172, 105, 145], 1.5, lambda v: {"look": {"radius": round(v)}}, hover=1)
    t.sweep("Slot size", "{:.0f} px", [72, 92, 46, 72], 1.5, lambda v: {"look": {"slot": round(v)}}, hover=1)
    t.sweep("Corner roundness", "{:.0%}", [0.28, 0.0, 0.5, 0.28], 1.2,
            lambda v: {"look": {"slot_shape": "rounded", "slot_corner": round(v, 3)}}, hover=2)
    t.sweep("Rim width", "{:.0f} px", [2, 6, 0, 2], 0.9, lambda v: {"look": {"border_width": round(v)}}, hover=3)
    t.sweep("Icon size", "{:.0%}", [1, 0.5, 1], 0.9, lambda v: {"look": {"icon_scale": round(v, 3)}}, hover=3)
    if t.clipped:
        print("the trailer leaves its box at:", "; ".join(sorted(t.clipped)))
    return t.frames, t.times, t.chapters


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
    "held-slot": ("held-slot.png", shot_held_slot,
                  "the Brushes ring with Move's slot waiting for a target, before 0.20.0 and now, DamStandard hovered in each"),
    "layout-slots": ("layout-slots.png", shot_layout_slots,
                     "five brushes with three Layout slots, the Paint slot hovered"),
    "command-open": ("command-open.gif", shot_command_open,
                     "the command lights up, the ring opens at the cursor, a flick picks ClayBuildup"),
    "trailer-readme": ("trailer-readme.gif", shot_trailer,
                       "one ring going through the ring settings in turn, with a caption naming each: looks, fans, "
                       "tag colours, shapes, colours, theme, when full, slot styles, glow, empty slots, hub, labels "
                       "and sizes, for the top of the README"),
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
