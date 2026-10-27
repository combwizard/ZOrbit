"""Export the brush icons the landing page ring shows, from a local ZBrush install.

Usage:  python site/export_brush_icons.py
Writes site/brush-icons/<Brush-Name>.png for every brush (and item icon) in
zorbit/default_menus.json. GitHub Pages cannot run ZBrush, so the PNGs are committed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent
ROOT = SITE.parent
sys.path.insert(0, str(ROOT / "zorbit"))

import brushes  # noqa: E402

SIZE = 128


def names() -> list[str]:
    cfg = json.loads((ROOT / "zorbit" / "default_menus.json").read_text(encoding="utf-8"))
    out: list[str] = []
    for menu in cfg["menus"].values():
        for it in menu.get("items", []):
            for key in ("icon", "brush"):
                n = it.get(key)
                if n and n not in out:
                    out.append(n)
    return out


def main() -> int:
    dst = SITE / "brush-icons"
    dst.mkdir(exist_ok=True)
    missing = []
    for n in names():
        data = brushes.thumbnail_png(n, SIZE)
        if data is None:
            missing.append(n)
            continue
        (dst / f"{n.replace(' ', '-')}.png").write_bytes(data)
        print(f"{n} -> {n.replace(' ', '-')}.png")
    if missing:
        print("No icon found for: " + ", ".join(missing), file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
