"""Writes tests/fixtures/look_cases.json: radial.json snippets, a target in them (the ring, a menu or one slot) and the
look the real loader and looks.LookSet.explain give for that target. Another resolver (the Studio's look.js) has to
give the same values and origins for the same snippet; tests/test_look_parity.py checks that.

Run: python tools/make_look_cases.py            (rewrites the file; tests/test_studio_looks.py fails if it is stale)
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "zorbit"))

OUT = os.path.join(ROOT, "tests", "fixtures", "look_cases.json")

ITEMS = [{"brush": "ClayBuildup"}, {"brush": "Move"}, {"brush": "Standard"}]


def _menu(look=None, style=None, slot=0):
    items = [dict(it) for it in ITEMS]
    if style is not None:
        items[slot]["style"] = style
    menu = {"title": "Main", "hotkey": "Q", "items": items}
    if look is not None:
        menu["look"] = look
    return {"main": menu}


# (name, theme, ring, looks, menus, target); the target is {} for the ring, {"menu": id} or {"menu": id, "slot": n}
CASES = [
    ("ring at the defaults", "dark", {}, {}, None, {}),
    ("ring size and shape keys", "dark", {"radius": 180, "slot": 80, "slot_shape": "hexagon", "hub": 20}, {}, None, {}),
    ("ring colours merge key by key", "dark", {"colors": {"accent": "#ff8800"}, "hub_color": "accent"}, {}, None, {}),
    ("light theme", "light", {}, {}, None, {}),
    ("light theme with a ring colour", "light", {"colors": {"highlight": "#00aa55"}, "glow_color": "highlight"}, {},
     None, {}),
    ("ring with a built-in look", "dark", {"look": "soft"}, {}, None, {}),
    ("ring keys win over the ring's look", "dark", {"look": "crystal", "hub": 30, "slot_shape": "circle"}, {}, None, {}),
    ("ring with a user look", "dark", {"look": "Mine"},
     {"Mine": {"slot_shape": "octagon", "hub_style": "ring", "colors": {"lines": "#336699"}, "hub_color": "lines"}},
     None, {}),
    ("ring with a look nobody has", "dark", {"look": "Gone", "hub": 12}, {}, None, {}),
    ("ring with a value out of range", "dark", {"radius": 5000, "slot": 90}, {}, None, {}),
    ("menu with no look of its own", "dark", {"look": "tiles"}, {}, _menu(), {"menu": "main"}),
    ("menu named after a built-in look", "dark", {}, {}, _menu("minimal"), {"menu": "main"}),
    ("menu look over the ring's look", "dark", {"look": "soft", "hub": 14}, {}, _menu("tiles"), {"menu": "main"}),
    ("menu with a preset and keys of its own", "dark", {}, {},
     _menu({"preset": "crystal", "hub": 40, "slot_shape": "diamond"}), {"menu": "main"}),
    ("menu with keys and no preset", "dark", {"look": "circuit"}, {},
     _menu({"labels": "none", "colors": {"accent": "#ff00aa"}}), {"menu": "main"}),
    ("menu colours move a role", "dark", {}, {},
     _menu({"colors": {"accent": "#22cc88"}, "hub_color": "accent", "glow_color": "accent"}), {"menu": "main"}),
    ("menu with a user look", "dark", {}, {"Bold": {"border_width": 5, "glow_opacity": 0.9, "when_full": "more"}},
     _menu("Bold"), {"menu": "main"}),
    ("menu look nobody has", "dark", {"hub": 22}, {}, _menu("Nope"), {"menu": "main"}),
    ("menu on the light theme", "light", {}, {}, _menu({"preset": "soft", "colors": {"bg": "#ffffff"}}),
     {"menu": "main"}),
    ("slot with a shape and a glow", "dark", {}, {}, _menu(None, {"slot_shape": "hexagon", "glow_color": "#ff8800"}),
     {"menu": "main", "slot": 0}),
    ("slot style roles follow the menu colours", "dark", {}, {},
     _menu({"colors": {"highlight": "#aa44ff"}}, {"glow_color": "highlight", "label_color": "accent"}),
     {"menu": "main", "slot": 0}),
    ("slot with the slot-only keys", "dark", {}, {},
     _menu(None, {"size": 1.2, "fill_color": "#112233", "border_color": "lines", "icon_scale": 0.8}, slot=1),
     {"menu": "main", "slot": 1}),
    ("slot over a menu preset", "dark", {"look": "soft"}, {},
     _menu({"preset": "tiles", "hub": 18}, {"slot_corner": 0.4, "border_width": 0}), {"menu": "main", "slot": 0}),
    ("another slot has no style", "dark", {}, {}, _menu({"preset": "diamonds"}, {"slot_shape": "circle"}),
     {"menu": "main", "slot": 2}),
]


def _case(name, theme, ring, looks, menus, target):
    return {"name": name, "theme": theme, "ring": ring, "looks": looks, "menus": menus or _menu(), "target": target}


def expected(case) -> dict:
    """{"values", "origins", "problems"} of a case, from the real loader and LookSet.explain."""
    import config as C
    cfg = {"ring": case["ring"], "menus": case["menus"]}
    if case["looks"]:
        cfg["looks"] = case["looks"]
    fd, tmp = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        loaded = C.load(tmp, None, theme=case["theme"])
    finally:
        os.remove(tmp)
    target = case["target"]
    if not target:
        res = loaded.looks.explain()
    else:
        menu = loaded.menus[target["menu"]]
        style = menu.items[target["slot"]].style if "slot" in target else None
        res = loaded.looks.explain(menu.look_spec, style)
    return {"values": res["values"], "origins": res["origins"], "problems": list(loaded.errors)}


def build_cases() -> list:
    out = []
    for args in CASES:
        case = _case(*args)
        case["expected"] = expected(case)
        out.append(case)
    return out


def main():
    cases = build_cases()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(cases, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    print(f"wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
