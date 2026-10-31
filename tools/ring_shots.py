"""Draws the ring pictures in docs/images (ring.png, fan.png, tag-colours.png, animations.png and the two GIFs) with
the real renderer, zorbit/ring.py, so they follow the ring's look whenever it changes. No window is opened and no
ZBrush is needed, but the brush pictures come from the installed ZBrush's presets, so a ZBrush has to be installed.

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
import glob
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
atexit.register(shutil.rmtree, SANDBOX, ignore_errors=True)
sys.path.insert(0, os.path.join(ROOT, "zorbit"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

import paths  # noqa: E402

assert os.path.commonpath([paths.CONFIG_DIR, SANDBOX]) == SANDBOX, "the config folder is outside the sandbox"
assert os.path.commonpath([paths.DATA_DIR, SANDBOX]) == SANDBOX, "the data folder is outside the sandbox"

import config as C  # noqa: E402
import expand  # noqa: E402
import radiald  # noqa: E402
import tags  # noqa: E402
from ring import Ring  # noqa: E402

OUT = os.path.join(ROOT, "docs", "images")
BG = (27, 28, 32)                              # the docs' dark page colour, as in every picture
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
RING_SCALE = 1.342                             # makes the ring pictures 600 pixels square
FAN_SCALE = 0.95                               # the fan picture is a little smaller, about 594 pixels wide


class World:
    """The starter menus and tags in the sandbox, loaded the way Studio's ring preview loads them."""

    def __init__(self):
        self.app = radiald.App(paths.ensure_config())
        assert os.path.commonpath([self.app.tags.path, SANDBOX]) == SANDBOX, "the tags file is outside the sandbox"
        store = self.app.tags.load()
        for brush, tag in TAG_ITEMS:               # in the sandbox's tags file, never the real one
            if tag:
                store.set_tags(tags.item_key("brush", brush), [tag])
        plain = tags.TagStore(os.path.join(SANDBOX, "untagged.json")).load()   # the starter tags, nothing tagged
        cfg = C.load(paths.CONFIG_FILE, store)
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

    def preview(self, menu_id, animation="", tagged=False, **kw):
        ex = self.ex[tagged]
        menu = ex.menu(self.cfg.menus[menu_id])
        if animation:
            menu.animation = animation
        return Ring.preview(menu, self.cfg.ring, self.app.icon_for, submenus=ex.resolve, **kw)


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


def on_background(im, size=None, at=(0, 0)):
    """The ring picture laid on the page colour, on a canvas of size (the picture's own by default)."""
    canvas = Image.new("RGBA", size or im.size, BG + (255,))
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


# name -> (file, function, what it shows)
SHOTS = {
    "ring": ("ring.png", shot_ring, "the starter Brushes menu in hold mode, ClayBuildup hovered, cursor on it"),
    "fan": ("fan.png", shot_fan, "More Brushes fanned out to the left, ClayTubes in the fan hovered, cursor on it"),
    "tag-colours": ("tag-colours.png", shot_tags, "eight brushes in two tags and two untagged, ClayBuildup hovered"),
    "animations": ("animations.png", shot_animations, "the five open animations part way through opening"),
    "open-animation": ("open-animation.gif", shot_open_animation,
                       "the ring opens, two brushes are hovered, More Brushes opens as a ring, a flick picks ClayTubes"),
    "fan-out": ("fan-out.gif", shot_fan_out,
                "More Brushes fans out, then Tools, SubDivide fans out above it, a flick past 1.00 picks it"),
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
    w = World()
    for name in args or SHOTS:
        file, make, _ = SHOTS[name]
        result = make(w)
        path = os.path.join(OUT, file)
        if isinstance(result, tuple):          # a GIF: (frames, milliseconds for each)
            save_gif(path, *result)
        else:
            result.convert("RGB").save(path, optimize=True)
        print("wrote", path)


if __name__ == "__main__":
    main(sys.argv[1:])
