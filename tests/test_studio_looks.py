"""Studio's look API: get_options()["looks"], resolve_look, preview_look(s), preview_ring with more: menus, the
looks in the settings and menu files, and the parity fixtures. Nothing here opens a window."""
import importlib.util
import json
import os
import types

import pytest

import looks
import paths
import studio
from test_studio_api import _fake_webview, api   # noqa: F401  (api is a fixture)
from test_menushare import _file, _pick, _save_to, tagfile   # noqa: F401  (tagfile is a fixture)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def cfg_of(n=12, **menu):
    return {"ring": {"look": "soft", "hub": 14},
            "looks": {"Mine": {"slot_shape": "hexagon", "colors": {"accent": "#22cc88"}}},
            "menus": {"main": {"title": "Main", "hotkey": "Q", "items": [{"brush": f"B{i}"} for i in range(n)],
                               **menu},
                      "fan": {"title": "Fan", "fan": True, "items": [{"brush": f"F{i}"} for i in range(14)]}}}


# --- get_options -------------------------------------------------------------------------------------
def test_the_options_look_schema_covers_every_look_key_and_the_slot_only_ones(api):
    opts = api.get_options()
    schema = opts["looks"]["schema"]
    assert set(schema) == set(looks.LOOK_KEYS) | {"size", "fill_color", "border_color"}
    assert json.loads(json.dumps(opts["looks"])) == opts["looks"]               # plain data
    groups = {s["group"] for s in schema.values()}
    assert groups == {"Slots", "Hub", "Glow", "Labels", "Colours", "Tag colours", "When full"}
    assert schema["hub"]["group"] == "Hub" and schema["glow_color"]["group"] == "Glow"
    assert schema["tag_band"]["group"] == "Tag colours" and schema["when_full"]["group"] == "When full"


def test_the_options_schema_kinds_ranges_choices_and_defaults(api):
    schema = api.get_options()["looks"]["schema"]
    assert schema["radius"] == {"group": "Slots", "default": 145, "full": False, "kind": "range", "min": 60, "max": 400,
                                "levels": ["global", "menu"]}
    assert schema["slot_corner"]["min"] == 0 and schema["slot_corner"]["max"] == 0.5
    assert schema["slot_shape"]["kind"] == "choice" and schema["slot_shape"]["choices"] == list(looks.SLOT_SHAPES)
    assert schema["when_full"]["choices"] == ["grow", "rings", "more"] and schema["when_full"]["default"] == "grow"
    assert schema["hub_color"]["kind"] == "colour" and schema["hub_color"]["default"] == "accent"
    assert schema["glow_color"]["allow_empty"] is True and schema["hub_color"]["allow_empty"] is False
    assert schema["colors"]["kind"] == "colors" and schema["colors"]["choices"] == list(looks.ROLES)
    assert schema["labels"]["choices"] == ["name", "none"]
    for k, spec in schema.items():
        if spec["kind"] == "range":
            assert spec["min"] <= spec["max"], k
        if spec["kind"] == "choice":
            assert spec["default"] in spec["choices"], k


def test_the_options_levels(api):
    schema = api.get_options()["looks"]["schema"]
    assert schema["radius"]["levels"] == ["global", "menu"]
    assert schema["hub"]["levels"] == ["global", "menu"]
    assert schema["slot_shape"]["levels"] == ["global", "menu", "slot"]
    assert schema["glow_color"]["levels"] == ["global", "menu", "slot"]
    assert schema["tag_colors"]["levels"] == ["global", "menu"]
    for k in ("size", "fill_color", "border_color"):
        assert schema[k]["levels"] == ["slot"]
    for k, spec in schema.items():
        assert ("slot" in spec["levels"]) == (k in looks.STYLE_KEYS), k


def test_the_options_mark_what_only_full_mode_shows(api):
    schema = api.get_options()["looks"]["schema"]
    simple = {k for k, s in schema.items() if not s["full"]}
    assert simple == {"radius", "slot", "dead_zone", "slot_shape", "labels", "when_full"}


def test_the_options_hold_roles_built_ins_reserved_names_and_the_name_rule(api):
    opts = api.get_options()
    lk = opts["looks"]
    assert lk["roles"] == ["bg", "accent", "highlight", "text", "lines"]
    assert [b["id"] for b in lk["builtin"]] == list(looks.BUILTIN)
    assert len(lk["builtin"]) == 7
    assert all(set(b) == {"id", "label", "blurb", "look"} for b in lk["builtin"])
    assert next(b for b in lk["builtin"] if b["id"] == "classic")["look"] == {}
    assert "__proto__" in lk["reserved"] and lk["menu_prefixes"] == ["tag:", "more:"]
    assert lk["name"]["max"] == 32 and lk["name"]["pattern"]
    assert len(opts["slot_shapes"]) == 6 and opts["hub_styles"] == ["dot", "disc", "ring", "icon"]
    assert opts["when_full"] == ["grow", "rings", "more"]


def test_the_options_defaults_follow_the_theme(api, monkeypatch):
    monkeypatch.setattr(studio, "_theme_now", lambda: "light")
    assert api.get_options()["looks"]["schema"]["hub"]["default"] == 10


# --- resolve_look ------------------------------------------------------------------------------------
def test_resolve_look_of_the_ring(api):
    res = api.resolve_look(cfg_of())
    assert res["values"]["slot_shape"] == "squircle" and res["values"]["hub"] == 14
    assert res["origins"]["slot_shape"] == {"from": "global-preset", "name": "soft"}
    assert res["origins"]["hub"] == {"from": "global", "name": ""}
    assert res["origins"]["radius"] == {"from": "default", "name": ""}
    assert res["preset"] == {"name": "soft", "builtin": True} and res["fit"] is None and res["problems"] == []


def test_resolve_look_of_a_menu_has_the_menu_origins_and_the_fit(api):
    res = api.resolve_look(cfg_of(look={"preset": "Mine", "radius": 100, "when_full": "more"}), "main")
    assert res["values"]["slot_shape"] == "hexagon" and res["values"]["radius"] == 100
    assert res["values"]["colors"]["accent"] == "#22cc88" and res["values"]["hub"] == 14
    assert res["origins"]["slot_shape"] == {"from": "menu-preset", "name": "Mine"}
    assert res["origins"]["radius"] == {"from": "menu", "name": ""}
    assert res["origins"]["colors.accent"] == {"from": "menu-preset", "name": "Mine"}
    assert res["origins"]["hub"] == {"from": "global", "name": ""}
    assert res["preset"] == {"name": "Mine", "builtin": False}
    assert res["fit"] == {"items": 12, "capacity": 6, "needed_radius": 174, "full": True, "when_full": "more"}


def test_resolve_look_fit_when_the_menu_fits_and_for_a_fan(api):
    res = api.resolve_look(cfg_of(n=5), "main")
    assert res["fit"] == {"items": 5, "capacity": 9, "needed_radius": 77, "full": False, "when_full": "grow"}
    assert res["preset"] is None                      # the menu has no look of its own: the ring's soft shows through
    assert api.resolve_look(cfg_of(), "fan")["fit"] is None


def test_resolve_look_of_a_slot_puts_the_style_over_the_menu(api):
    cfg = cfg_of(look="Mine")
    cfg["menus"]["main"]["items"][2]["style"] = {"slot_shape": "diamond", "glow_color": "highlight", "size": 1.2}
    res = api.resolve_look(cfg, "main", 2)
    assert res["values"]["slot_shape"] == "diamond" and res["values"]["size"] == 1.2
    assert res["values"]["glow_color"] == res["values"]["colors"]["highlight"]
    assert res["origins"]["slot_shape"] == {"from": "slot", "name": ""}
    assert res["origins"]["size"] == {"from": "slot", "name": ""}
    assert res["origins"]["hub"] == {"from": "global", "name": ""}
    assert res["origins"]["border_width"] == {"from": "global-preset", "name": "soft"}
    assert res["preset"] is None and res["fit"]["items"] == 12
    other = api.resolve_look(cfg, "main", 1)
    assert other["values"]["slot_shape"] == "hexagon" and other["origins"]["slot_shape"]["from"] == "menu-preset"


def test_resolve_look_with_a_slot_out_of_range_is_the_menu(api):
    cfg = cfg_of()
    assert api.resolve_look(cfg, "main", 99)["values"] == api.resolve_look(cfg, "main")["values"]
    assert api.resolve_look(cfg, "main", True)["origins"] == api.resolve_look(cfg, "main")["origins"]


def test_resolve_look_with_an_unknown_menu_gives_the_ring_and_says_so(api):
    res = api.resolve_look(cfg_of(), "nope")
    assert res["values"]["hub"] == 14 and res["fit"] is None
    assert any("'nope' not found" in p for p in res["problems"])


def test_resolve_look_reports_the_loaders_problems(api):
    cfg = cfg_of(look="Nope")
    assert any("look 'Nope' unknown" in p for p in api.resolve_look(cfg, "main")["problems"])


@pytest.mark.parametrize("junk", [None, 5, "x", [], {}])
def test_resolve_look_survives_a_config_that_is_not_one(api, junk):
    res = api.resolve_look(junk, "main")
    assert set(res) == {"values", "origins", "preset", "fit", "problems"}


# --- previews ----------------------------------------------------------------------------------------
def test_preview_looks_draws_every_built_in_and_user_look(api):
    res = api.preview_looks(cfg_of())
    assert list(res["looks"]) == list(looks.BUILTIN) + ["Mine"]
    for name, pic in res["looks"].items():
        assert pic["image"].startswith("data:image/png;base64,"), name
        assert pic["width"] > 0 and pic["height"] > 0 and len(pic["centre"]) == 2
    assert res["problems"] == []
    assert res["looks"]["classic"]["image"] != res["looks"]["crystal"]["image"]


def test_preview_looks_filters_by_names_and_reports_an_unknown_one(api):
    res = api.preview_looks(cfg_of(), names=["soft", "Gone", "Mine"], scale=0.4)
    assert list(res["looks"]) == ["soft", "Mine"]
    assert any("'Gone' unknown" in p for p in res["problems"])
    assert api.preview_looks(cfg_of(), names=[])["looks"] == {}


def test_preview_looks_scale_changes_the_size(api):
    small = api.preview_looks(cfg_of(), names=["soft"], scale=0.3)["looks"]["soft"]
    big = api.preview_looks(cfg_of(), names=["soft"], scale=0.6)["looks"]["soft"]
    assert big["width"] > small["width"]


def test_preview_look_of_a_preset_and_of_raw_keys(api):
    base = api.preview_look(cfg_of())
    hexes = api.preview_look(cfg_of(), preset="crystal")
    raw = api.preview_look(cfg_of(), look={"slot_shape": "octagon", "hub": 30})
    for res in (base, hexes, raw):
        assert res["image"].startswith("data:image/png") and res["problems"] == []
    assert len({base["image"], hexes["image"], raw["image"]}) == 3
    assert api.preview_look(cfg_of(), preset="crystal")["image"] == hexes["image"]


def test_preview_look_of_a_preset_matches_the_gallery_picture(api):
    one = api.preview_look(cfg_of(), preset="tiles", scale=0.5)
    gallery = api.preview_looks(cfg_of(), names=["tiles"], scale=0.5)["looks"]["tiles"]
    assert one["image"] == gallery["image"]


def test_preview_look_reports_a_look_nobody_has_and_bad_keys(api):
    res = api.preview_look(cfg_of(), preset="Gone", look={"hub": 9999, "bogus": 1})
    assert res["image"]
    text = " ".join(res["problems"])
    assert "look 'Gone' unknown" in text and "hub" in text and "bogus" in text


def test_preview_look_over_a_menu_keeps_the_menus_own_keys(api):
    cfg = cfg_of(look={"hub": 40})
    keep = api.preview_look(cfg, preset="minimal", base="main")
    drop = api.preview_look(cfg, preset="minimal")
    assert keep["image"] != drop["image"]
    assert any("not found" in p for p in api.preview_look(cfg, preset="minimal", base="zzz")["problems"])


def test_the_look_pictures_are_kept_for_the_next_call(api, monkeypatch):
    studio._look_images.clear()
    api.preview_looks(cfg_of(), names=["soft"])
    n = len(studio._look_images)
    import ring
    monkeypatch.setattr(ring.Ring, "preview", classmethod(lambda *a, **k: pytest.fail("drawn again")))
    assert api.preview_looks(cfg_of(), names=["soft"])["looks"]["soft"]["image"]
    assert len(studio._look_images) == n


def test_the_look_picture_cache_is_bounded(api, monkeypatch):
    studio._look_images.clear()
    monkeypatch.setattr(studio, "LOOK_IMAGES", 3)
    for hub in range(10, 18):
        api.preview_look(cfg_of(), look={"hub": hub})
    assert len(studio._look_images) == 3


def test_preview_ring_draws_with_the_menus_look(api):
    plain = api.preview_ring(cfg_of(n=5), "main")
    styled = api.preview_ring(cfg_of(n=5, look="Mine"), "main")
    assert plain["image"] and styled["image"] and plain["image"] != styled["image"]
    assert styled["fit"] == {"items": 5, "capacity": 9, "needed_radius": 77, "full": False, "when_full": "grow"}


def test_preview_ring_keeps_empty_slots_in_the_layout_and_the_count(api):
    cfg = cfg_of(n=0, keep_slots=True)
    cfg["menus"]["main"]["items"] = [{"brush": "B0"}, {"empty": True}, {"empty": True}, {"brush": "B3"},
                                     {"empty": True}]
    res = api.preview_ring(cfg, "main")
    assert res["image"].startswith("data:image/png") and not res["problems"]
    assert [s["i"] for s in res["layout"]["slots"]] == [0, 1, 2, 3, 4]
    assert res["fit"]["items"] == 5


def test_preview_ring_of_a_menu_of_only_empty_slots_draws_outlines(api):
    cfg = cfg_of(n=0, keep_slots=True)
    cfg["menus"]["main"]["items"] = [{"empty": True}] * 8
    res = api.preview_ring(cfg, "main")
    assert res["image"].startswith("data:image/png") and not res["problems"]
    assert len(res["layout"]["slots"]) == 8 and res["fit"]["items"] == 8


def test_get_options_lists_the_empty_action(api):
    assert "empty" in api.get_options()["actions"]


def test_preview_ring_of_a_fan_menu_has_no_fit(api):
    assert api.preview_ring(cfg_of(), "fan")["fit"] is None


def test_preview_ring_passes_the_layout_map_through_when_the_renderer_gives_one(api, monkeypatch):
    import ring
    real = ring.Ring.preview.__func__

    def preview(cls, *a, **k):
        im = real(cls, *a, **k)
        im.info["layout"] = {"slots": []}
        return im
    monkeypatch.setattr(ring.Ring, "preview", classmethod(preview))
    assert api.preview_ring(cfg_of(n=5), "main")["layout"] == {"slots": []}
    assert api.preview_tags(cfg_of())["layout"] == {"slots": []}


def test_preview_ring_accepts_more_menus(api):
    cfg = cfg_of(look={"when_full": "more"})
    first = api.preview_ring(cfg, "main")
    rest = api.preview_ring(cfg, "more:main")
    assert first["image"] and rest["image"] and first["image"] != rest["image"]
    assert first["fit"]["items"] == 12 and first["fit"]["full"] is True
    assert rest["fit"]["items"] == 12 - (first["fit"]["capacity"] - 1) and rest["fit"]["full"] is False
    assert rest["problems"] == []


def test_preview_ring_of_a_more_menu_that_does_not_exist(api):
    res = api.preview_ring(cfg_of(n=3, look={"when_full": "more"}), "more:main")
    assert res["image"] is None and res["problems"]
    assert api.preview_ring(cfg_of(), "more:nope")["image"] is None


def test_preview_tags_can_use_a_menus_look(api):
    cfg = cfg_of(look="Mine")
    plain = api.preview_tags(cfg)
    mine = api.preview_tags(cfg, menu_id="main")
    assert plain["image"] and mine["image"] and plain["image"] != mine["image"]
    assert api.preview_tags(cfg, menu_id="nope")["image"] == plain["image"]


def test_the_sample_menu_has_eight_slots_with_tag_colours_and_a_submenu(api):
    loaded, _ = api._load_dict(cfg_of())
    app = api._preview_app()
    app.cfg = loaded
    menu = api._sample_menu(loaded, app)
    assert len(menu.items) == studio.SAMPLE_SLOTS
    assert sum(1 for it in menu.items if it.color) >= 2
    subs = [it for it in menu.items if it.kind == "menu"]
    assert len(subs) == 1 and menu.items[-1] is subs[0] and not subs[0].color
    assert menu.look is None


# --- export and import -------------------------------------------------------------------------------
def test_export_settings_includes_the_looks(api, tmp_path, monkeypatch):
    _save_to(api, monkeypatch, tmp_path / "all.json")
    cfg = cfg_of()
    assert api.export_settings(cfg)["ok"]
    bundle = json.loads((tmp_path / "all.json").read_text(encoding="utf-8"))
    assert bundle["config"]["looks"] == cfg["looks"] and bundle["config"]["ring"] == cfg["ring"]


def test_a_menu_with_a_preset_goes_out_and_comes_in_under_a_new_name(api, tmp_path, monkeypatch, tagfile):
    mine = cfg_of(n=3, look={"preset": "Mine", "hub": 22})
    _save_to(api, monkeypatch, tmp_path / "menu.json")
    assert api.export_menu(mine, "main")["ok"]
    bundle = json.loads((tmp_path / "menu.json").read_text(encoding="utf-8"))
    assert bundle["looks"] == mine["looks"]
    other = {"looks": {"Mine": {"slot_shape": "octagon"}}, "menus": {}}      # a different look of the same name
    pick = _pick(api, monkeypatch, tmp_path / "menu.json", other)
    assert pick["ok"] and pick["problems"] == []
    assert pick["looks"] == {"added": ["Mine 2"], "joined": [], "renamed": {"Mine": "Mine 2"}}
    done = api.apply_menu_import(other)
    assert done["looks"] == {"Mine 2": mine["looks"]["Mine"]}
    assert done["menus"]["main"]["look"] == {"preset": "Mine 2", "hub": 22}
    merged = {"looks": {**other["looks"], **done["looks"]}, "menus": done["menus"]}
    loaded, errors = api._load_dict(merged)
    assert [e for e in errors if not e.startswith("no menu has a hotkey")] == []
    assert loaded.menus["main"].look["slot_shape"] == "hexagon" and loaded.menus["main"].look["hub"] == 22
    again = _pick(api, monkeypatch, tmp_path / "menu.json", merged)           # the same file into the merged editor
    assert again["looks"] == {"added": ["Mine 3"], "joined": [], "renamed": {"Mine": "Mine 3"}}   # matched by name
    own = _pick(api, monkeypatch, tmp_path / "menu.json", {"looks": mine["looks"], "menus": {}})
    assert own["looks"] == {"added": [], "joined": ["Mine"], "renamed": {}}


# --- the parity fixtures -----------------------------------------------------------------------------
def _generator():
    spec = importlib.util.spec_from_file_location("make_look_cases", os.path.join(ROOT, "tools", "make_look_cases.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_look_cases_fixture_is_what_the_generator_writes():
    with open(os.path.join(ROOT, "tests", "fixtures", "look_cases.json"), encoding="utf-8") as f:
        on_disk = json.load(f)
    fresh = json.loads(json.dumps(_generator().build_cases(), sort_keys=True))
    assert on_disk == fresh, "run: python tools/make_look_cases.py"


def test_the_look_cases_cover_every_level_and_origin():
    cases = _generator().build_cases()
    assert len(cases) >= 20
    levels = {("slot" if "slot" in c["target"] else "menu" if c["target"] else "ring") for c in cases}
    assert levels == {"ring", "menu", "slot"}
    origins = {o["from"] for c in cases for o in c["expected"]["origins"].values()}
    assert origins == {"default", "theme", "global-preset", "global", "menu-preset", "menu", "slot"}
    assert any(c["expected"]["problems"] for c in cases)


def test_the_look_options_fixture_is_what_the_generator_writes():
    with open(os.path.join(ROOT, "tests", "fixtures", "look_options.json"), encoding="utf-8") as f:
        on_disk = json.load(f)
    fresh = json.loads(json.dumps(_generator().build_options(), sort_keys=True))
    assert on_disk == fresh, "run: python tools/make_look_cases.py"


def test_a_gallery_picture_on_the_default_base_ignores_the_users_own_settings(api):
    # base "default": the look over the defaults and the theme, so moving Hub size (or picking a global look) does not
    # redraw a card; the global base still follows them (Classic sets no hub of its own)
    a, b = cfg_of(), cfg_of()
    b["ring"] = {"look": "tiles", "hub": 40, "slot_shape": "diamond"}
    for name in ("classic", "soft", "Mine"):
        da = api.preview_looks(a, names=[name], base="default")["looks"][name]["image"]
        db = api.preview_looks(b, names=[name], base="default")["looks"][name]["image"]
        assert da == db
    ga = api.preview_looks(a, names=["classic"], base="global")["looks"]["classic"]["image"]
    gb = api.preview_looks(b, names=["classic"], base="global")["looks"]["classic"]["image"]
    assert ga != gb


def test_the_default_base_draws_the_look_as_it_is(api):
    plain = api.preview_look(cfg_of(), preset="classic", base="default")
    assert plain["problems"] == [] and plain["image"]
    assert api.preview_look({"menus": cfg_of()["menus"]}, preset="classic", base="default")["image"] == plain["image"]
    assert api.preview_look(cfg_of(), preset="crystal", base="default")["image"] != plain["image"]
