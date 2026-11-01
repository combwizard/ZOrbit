"""Slot shapes: drawing, icon masks, hit tests and the badge position. Pure Pillow and math, no win32.

A shape is drawn around a centre with r = its half width. Circle and rounded square make exactly the Pillow calls
the ring always made, so the default looks stay pixel for pixel the same. The other shapes are polygons: a squircle
(|x|^4 + |y|^4 = r^4), a pointy-top hexagon of circumradius r, a flat-top octagon of apothem r and a diamond that
reaches 1.15 r along the axes (it is the smallest-looking shape otherwise).

Growing a shape (a glow or a halo around a slot) moves its edge out by the same distance everywhere, so the glow
is the slot's own shape, bigger. Polygons are drawn as an outer polygon in the rim colour and an inset polygon in
the fill colour on top, so the rim has an even width.
"""
import math

from PIL import Image, ImageDraw

SHAPES = ("circle", "rounded", "squircle", "hexagon", "octagon", "diamond")
SLOT_CORNER = 0.28                  # a rounded slot's corner radius, as a share of its side
DIAMOND_K = 1.15                    # a diamond's tip reaches this many r along the axes
SQUIRCLE_POINTS = 96
_BADGE = {"circle": 0.62, "rounded": 0.66, "squircle": 0.64, "hexagon": 0.56, "octagon": 0.62, "diamond": 0.50}
_SIDES = {"hexagon": 6, "octagon": 8, "diamond": 4}
_START = {"hexagon": -90.0, "octagon": -67.5, "diamond": -90.0}      # degrees of the first vertex (y down)
_SQRT3 = math.sqrt(3)


def _known(shape):
    return shape if shape in SHAPES else "circle"


def _circ(shape, r):
    """Circumradius of a polygon shape whose size parameter is r."""
    if shape == "octagon":
        return r / math.cos(math.pi / 8)
    if shape == "diamond":
        return r * DIAMOND_K
    return r


def _points(shape, cx, cy, r, corner=SLOT_CORNER):
    """Outline of a polygon shape (hexagon, octagon, diamond, squircle) of size r, as a list of points."""
    if shape == "squircle":
        pts = []
        for k in range(SQUIRCLE_POINTS):
            t = 2 * math.pi * k / SQUIRCLE_POINTS
            ct, st = math.cos(t), math.sin(t)
            pts.append((cx + r * math.copysign(abs(ct) ** 0.5, ct), cy + r * math.copysign(abs(st) ** 0.5, st)))
        return pts
    n, big = _SIDES[shape], _circ(shape, r)
    a0 = math.radians(_START[shape])
    return [(cx + big * math.cos(a0 + 2 * math.pi * k / n), cy + big * math.sin(a0 + 2 * math.pi * k / n))
            for k in range(n)]


def _grown(shape, r, grow):
    """Size parameter of the shape pushed out by grow (an even distance from the old edge)."""
    if shape in ("hexagon", "diamond"):
        n = _SIDES[shape]
        return r + grow / math.cos(math.pi / n) / (DIAMOND_K if shape == "diamond" else 1.0)
    return r + grow


def _inset(shape, w):
    """How much smaller the size parameter gets when the edge moves in by w."""
    if shape in ("squircle", "octagon"):            # their parameter is the half width / the apothem
        return w
    return w / math.cos(math.pi / _SIDES[shape]) / (DIAMOND_K if shape == "diamond" else 1.0)


def draw(d, shape, cx, cy, r, corner=SLOT_CORNER, grow=0.0, fill=None, outline=None, width=0):
    """Draws the shape centred on cx, cy into the ImageDraw d. r: half width; grow: pixels the edge is pushed out;
    fill and outline: colours (None leaves them out); width: the rim width in pixels when there is an outline."""
    shape = _known(shape)
    kw = {}
    if fill is not None:
        kw["fill"] = fill
    if outline is not None:
        kw["outline"] = outline
        kw["width"] = width
    if shape in ("circle", "rounded"):
        gr = r + grow if grow else r
        box = (cx - gr, cy - gr, cx + gr, cy + gr)
        if shape == "rounded":
            d.rounded_rectangle(box, radius=(box[2] - box[0]) * corner, **kw)
        else:
            d.ellipse(box, **kw)
        return
    size = _grown(shape, r, grow) if grow else r
    if outline is None or width <= 0:
        if fill is not None:
            d.polygon(_points(shape, cx, cy, size, corner), fill=fill)
        return
    d.polygon(_points(shape, cx, cy, size, corner), fill=outline)           # the rim: the whole shape
    inner = size - _inset(shape, width)
    if inner > 0:                                                            # the fill, inset by the rim width
        d.polygon(_points(shape, cx, cy, inner, corner), fill=fill if fill is not None else (0, 0, 0, 0))


def icon_mask(shape, size, corner=SLOT_CORNER):
    """An L image of size x size, 255 inside the shape: icons are multiplied by it so they take the slot's shape."""
    shape = _known(shape)
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    if shape == "circle":
        d.ellipse((0, 0, size - 1, size - 1), fill=255)
    elif shape == "rounded":
        box = (0, 0, size - 1, size - 1)
        d.rounded_rectangle(box, radius=(box[2] - box[0]) * corner, fill=255)
    else:
        half = (size - 1) / 2
        d.polygon(_points(shape, half, half, half, corner), fill=255)
    return mask


def inside(shape, dx, dy, r, corner=SLOT_CORNER):
    """Whether the offset (dx, dy) from a slot's centre is on a slot of size r. A rounded slot answers anywhere in
    its box, a little generously at the corners."""
    shape = _known(shape)
    ax, ay = abs(dx), abs(dy)
    if shape == "circle":
        return math.hypot(dx, dy) <= r
    if shape == "rounded":
        return max(ax, ay) <= r
    if shape == "squircle":
        return ax ** 4 + ay ** 4 <= r ** 4
    if shape == "hexagon":
        return ax <= _SQRT3 / 2 * r and ay + ax / _SQRT3 <= r
    if shape == "octagon":
        return ax <= r and ay <= r and ax + ay <= math.sqrt(2) * r
    return ax + ay <= DIAMOND_K * r


def badge(shape):
    """How far out (share of r, along both axes) the submenu badge sits at the bottom right."""
    return _BADGE[_known(shape)]


def pad_extra(shape, D):
    """Extra canvas width a shape needs beyond a circle of diameter D (a diamond's tips go past it)."""
    if _known(shape) == "diamond":
        return (DIAMOND_K - 1) * D / 2
    return 0.0
