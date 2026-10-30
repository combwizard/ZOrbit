"""Draws the ZOrbit icons and writes assets/icon.ico (16-256 px) and assets/icon-256.png (the app), assets/browser.ico
and assets/browser-256.png (the browser popout), and assets/icon-preview.png (both, one row each).

Run: python assets/make_icon.py   (needs Pillow)
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ORANGE, CYAN = (248, 107, 51), (77, 200, 233)
S = 1024                                   # drawn large, reduced per size


def _disc() -> Image.Image:
    """The dark disc with its orange glow and pale outline, shared by both icons."""
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    c = S / 2
    # glow behind the disc
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((c - 430, c - 430, c + 430, c + 430), fill=ORANGE + (90,))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40)))
    d = ImageDraw.Draw(im)
    d.ellipse((c - 470, c - 470, c + 470, c + 470), fill=(26, 27, 30, 255), outline=(255, 255, 255, 40), width=14)
    return im


def draw(size_hint: int) -> Image.Image:
    im = _disc()
    c = S / 2
    small = size_hint <= 24                # tiny sizes: fewer, bolder shapes
    d = ImageDraw.Draw(im)
    if not small:
        d.ellipse((c - 300, c - 300, c + 300, c + 300), outline=ORANGE + (80,), width=12)
    n = 6
    r_ring = 300
    r_dot = 92 if small else 74
    w = 0 if small else 44
    for i in range(n):
        a = math.radians(-90 + 360 / n * i)
        x, y = c + r_ring * math.cos(a), c + r_ring * math.sin(a)
        col = CYAN if i == 2 else ORANGE
        if small:
            d.ellipse((x - r_dot, y - r_dot, x + r_dot, y + r_dot), fill=col + (255,))
        else:
            d.ellipse((x - r_dot, y - r_dot, x + r_dot, y + r_dot), fill=(26, 27, 30, 255), outline=col + (255,), width=w)
    # glowing centre dot
    cg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(cg).ellipse((c - 120, c - 120, c + 120, c + 120), fill=ORANGE + (200,))
    im.alpha_composite(cg.filter(ImageFilter.GaussianBlur(36)))
    d = ImageDraw.Draw(im)
    rc = 110 if small else 84
    d.ellipse((c - rc, c - rc, c + rc, c + rc), fill=ORANGE + (255,))
    return im


def draw_browser(size_hint: int) -> Image.Image:
    """Same disc, then the 2x2 grid of rounded tiles of the browser glyph: three orange, bottom right cyan."""
    im = _disc()
    c = S / 2
    small = size_hint <= 32                # small sizes: bigger, filled tiles (a 44 px outline is under 2 px here)
    tile, gap = (260, 90) if small else (235, 118)    # the glyph's 6:3 tile to gap, 1/4 disc per tile
    r = round(tile * 1.3 / 6)              # the glyph's rx 1.3 of a 6 unit tile
    w = 0 if small else 44
    d = ImageDraw.Draw(im)
    for i in range(4):
        col = CYAN if i == 3 else ORANGE
        x0 = c - gap / 2 - tile if i % 2 == 0 else c + gap / 2
        y0 = c - gap / 2 - tile if i < 2 else c + gap / 2
        box = (x0, y0, x0 + tile, y0 + tile)
        if small:
            d.rounded_rectangle(box, r, fill=col + (255,))
        else:
            d.rounded_rectangle(box, r, fill=(26, 27, 30, 255), outline=col + (255,), width=w)
    return im


def main():
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    rows = []
    for name, fn in (("icon", draw), ("browser", draw_browser)):
        frames = [fn(s).resize((s, s), Image.LANCZOS) for s in sizes]
        frames[-1].save(os.path.join(HERE, name + ".ico"), format="ICO", sizes=[(s, s) for s in sizes],
                        append_images=frames[:-1])
        frames[-1].save(os.path.join(HERE, name + "-256.png"))
        rows.append(frames)
    sheet = Image.new("RGBA", (sum(sizes) + 10 * len(sizes), 256 * len(rows)), (40, 42, 48, 255))
    for n, frames in enumerate(rows):
        x = 0
        for f in frames:
            sheet.alpha_composite(f, (x, 256 * n + (256 - f.size[1]) // 2))
            x += f.size[0] + 10
    sheet.save(os.path.join(HERE, "icon-preview.png"))
    print("wrote icon.ico, icon-256.png, browser.ico, browser-256.png, icon-preview.png")


if __name__ == "__main__":
    main()
