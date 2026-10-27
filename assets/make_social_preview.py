"""Draws the GitHub social preview card and writes assets/social-preview.png (1280x640).

Upload it under the repository's Settings > General > Social preview.
Run: python assets/make_social_preview.py   (needs Pillow and Windows' Segoe UI fonts)
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
W, H = 1280, 640
BG = (27, 28, 32)                          # matches the ring screenshot's backdrop
TEXT, SUB, ORANGE = (240, 240, 240), (146, 148, 154), (248, 107, 51)


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def main() -> None:
    im = Image.new("RGB", (W, H), BG)
    ring = Image.open(os.path.join(ROOT, "docs", "images", "ring.png")).convert("RGB")
    ring = ring.crop((1, 1, ring.width - 1, ring.height - 1))   # drop the black frame
    im.paste(ring, (W - ring.width - 24, (H - ring.height) // 2))

    d = ImageDraw.Draw(im)
    x = 88
    icon = Image.open(os.path.join(HERE, "icon-256.png")).convert("RGBA").resize((104, 104), Image.LANCZOS)
    im.paste(icon, (x - 6, 168), icon)
    d.text((x + 116, 220), "ZOrbit", font=font("segoeuib.ttf", 92), fill=TEXT, anchor="lm")

    d.rounded_rectangle((x, 300, x + 72, 306), radius=3, fill=ORANGE)
    d.text((x, 336), "Radial pie menu for ZBrush", font=font("segoeuisl.ttf", 40), fill=TEXT, anchor="lt")
    d.text((x, 396), "Hold Q, flick to a brush.", font=font("segoeuisl.ttf", 30), fill=SUB, anchor="lt")
    d.text((x, 456), "Free and open source  \u00b7  Windows  \u00b7  ZBrush 2022+",
           font=font("segoeui.ttf", 24), fill=SUB, anchor="lt")

    out = os.path.join(HERE, "social-preview.png")
    im.save(out, optimize=True)
    print(out)


if __name__ == "__main__":
    main()
