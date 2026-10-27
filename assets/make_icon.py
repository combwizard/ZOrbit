"""Draws the ZOrbit icon and writes assets/icon.ico (16-256 px) and assets/icon-256.png.

Run: python assets/make_icon.py   (needs Pillow)
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ORANGE, CYAN = (248, 107, 51), (77, 200, 233)
S = 1024                                   # drawn large, reduced per size


def draw(size_hint: int) -> Image.Image:
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    c = S / 2
    small = size_hint <= 24                # tiny sizes: fewer, bolder shapes
    # glow behind the disc
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((c - 430, c - 430, c + 430, c + 430), fill=ORANGE + (90,))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(40)))
    d = ImageDraw.Draw(im)
    d.ellipse((c - 470, c - 470, c + 470, c + 470), fill=(26, 27, 30, 255), outline=(255, 255, 255, 40), width=14)
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


def main():
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [draw(s).resize((s, s), Image.LANCZOS) for s in sizes]
    frames[-1].save(os.path.join(HERE, "icon.ico"), format="ICO", sizes=[(s, s) for s in sizes],
                    append_images=frames[:-1])
    frames[-1].save(os.path.join(HERE, "icon-256.png"))
    sheet = Image.new("RGBA", (sum(sizes) + 10 * len(sizes), 256), (40, 42, 48, 255))
    x = 0
    for f in frames:
        sheet.alpha_composite(f, (x, (256 - f.size[1]) // 2))
        x += f.size[0] + 10
    sheet.save(os.path.join(HERE, "icon-preview.png"))
    print("wrote icon.ico, icon-256.png, icon-preview.png")


if __name__ == "__main__":
    main()
