"""Records real Studio API responses from THIS machine into zorbit/studio_ui/dev/mock_data.js, so the
Studio UI can be developed in a plain browser: open studio_ui/index.html?mock in Edge.

The output contains your own paths, hotkeys and logs. It is git-ignored; never commit it.
The light previews (preview_*_light) are recorded with the theme set to light, for the Light theme in the mock.
Run: python tools/make_mock.py [OUT]   (OUT defaults to that file; tools/docs_shots.py records its own elsewhere)
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "zorbit"))
import studio  # noqa: E402


def main():
    a = studio.Api()
    cfg = a.get_config()
    lib = a.get_library()
    used = sorted({it["brush"] for m in cfg["config"]["menus"].values() for it in m["items"] if "brush" in it})
    names = used + [b["name"] for b in lib["brushes"]]          # every brush: the browser picture shows letters for any left out
    first = next(iter(cfg["config"]["menus"]))
    kinds = {}                          # the alpha, material and texture tabs: library + first 30 thumbnails
    for kind in ("alpha", "material", "texture"):
        klib = a.get_library(kind=kind)
        kinds["get_library_" + kind] = klib
        kinds["get_thumbs_" + kind] = a.get_thumbs([it["name"] for it in klib["items"][:30]], 128, kind)
    mock = {
        "get_config": cfg, "get_library": lib, "get_thumbs": a.get_thumbs(names, 128),
        "get_suggestions": a.get_suggestions(), "get_tags": a.get_tags(), "get_profiles": a.get_profiles(), "get_status": a.get_status(), "get_options": a.get_options(),
        "preview_ring": {mid: a.preview_ring(cfg["config"], mid) for mid in cfg["config"]["menus"]},
        "preview_ring_hover0": a.preview_ring(cfg["config"], first, hover=0),
        "preview_tags": a.preview_tags(cfg["config"]),
        "preview_animation": a.preview_animation(cfg["config"], first),
        **kinds,
    }
    # The same four pictures in the Light theme (dev/mock.js answers with these when the theme is light).
    real_theme_now = studio._theme_now
    studio._theme_now = lambda: "light"
    try:
        mock["preview_ring_light"] = {mid: a.preview_ring(cfg["config"], mid) for mid in cfg["config"]["menus"]}
        mock["preview_ring_hover0_light"] = a.preview_ring(cfg["config"], first, hover=0)
        mock["preview_tags_light"] = a.preview_tags(cfg["config"])
        mock["preview_animation_light"] = a.preview_animation(cfg["config"], first)
    finally:
        studio._theme_now = real_theme_now
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "zorbit", "studio_ui", "dev", "mock_data.js")
    with open(out, "w", encoding="utf-8") as f:
        f.write("// Recorded Studio API responses from a developer's machine. Generated; git-ignored.\n"
                "window.__RADIAL_MOCK__ = " + json.dumps(mock) + ";\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
