"""looks.py: the look keys, the checks that read them, the built-in looks and the layering."""
import pytest

import config
import looks
import theme

ROLE_LIST = "bg, accent, highlight, text, lines"


def check(raw, allow=looks.LOOK_KEYS, prefix="x."):
    errors = []
    return looks.check_look(raw, errors, prefix, allow), errors


# --- defaults ------------------------------------------------------------------------------------------
def test_the_defaults_resolve_to_todays_rendering():
    look = looks.LookSet().global_look()
    assert look["radius"] == 145 and look["slot"] == 72 and look["dead_zone"] == 38
    assert (look["hub"], look["hub_style"], look["hub_glow"]) == (10, "dot", 1.0)
    assert look["slot_shape"] == "circle" and look["border_width"] == 2 and look["icon_scale"] == 1.0
    assert look["hub_color"] == look["colors"]["accent"] and look["label_color"] == look["colors"]["text"]
    assert look["glow_color"] == "" and look["glow_opacity"] == 0.55 and look["when_full"] == "grow"
    assert look["colors"] == theme.ring_colors("dark") and "theme" not in look
    assert (look["tap_ms"], look["timeout_s"], look["animation"], look["labels"]) == (250, 20, "smooth", "name")


def test_every_default_is_valid_for_its_own_checks():
    defaults = {**looks.BEHAVIOUR_DEFAULTS, **looks.LOOK_DEFAULTS}
    got, errors = check(defaults, allow=looks.RING_KEYS)
    assert errors == [] and got == defaults
    for key in defaults:
        assert key in looks.RING_KEYS
    assert set(looks.LOOK_KEYS) - {"colors"} == set(looks.LOOK_DEFAULTS)
    assert set(looks.BEHAVIOUR_KEYS) == set(looks.BEHAVIOUR_DEFAULTS)


@pytest.mark.parametrize("key", sorted(looks.RANGES))
def test_the_range_ends_are_valid_and_just_outside_is_not(key):
    lo, hi = looks.RANGES[key]
    allow = looks.RING_KEYS + ("size",)
    assert check({key: lo}, allow)[1] == [] and check({key: hi}, allow)[1] == []
    assert check({key: hi + 1}, allow)[1] == [f"x.{key}: {hi + 1!r} must be a number from {lo} to {hi}"]
    assert check({key: True}, allow)[1]                  # a bool is not a number


def test_the_hub_goes_up_to_64_and_the_other_tables_hold_the_new_keys():
    assert looks.RANGES["hub"] == (0, 64)
    assert looks.CHOICES["hub_style"] == ("dot", "disc", "ring", "icon")
    assert looks.CHOICES["when_full"] == ("grow", "rings", "more")
    assert looks.CHOICES["slot_shape"] == ("circle", "rounded", "squircle", "hexagon", "octagon", "diamond")
    assert looks.STYLE_KEYS == ("slot_shape", "slot_corner", "border_width", "icon_scale", "label_color",
                                "glow_color", "size", "fill_color", "border_color")
    assert looks.RING_KEYS == looks.LOOK_KEYS + looks.BEHAVIOUR_KEYS + ("look",)


# --- the built-in looks ----------------------------------------------------------------------------------
def test_the_built_in_looks_are_in_order_and_each_is_valid():
    assert list(looks.BUILTIN) == ["classic", "soft", "tiles", "crystal", "circuit", "diamonds", "minimal"]
    assert looks.BUILTIN["classic"]["look"] == {}
    for name, b in looks.BUILTIN.items():
        assert b["label"] and b["blurb"]
        got, errors = check(b["look"])
        assert errors == [] and got == b["look"], name


def test_the_built_in_looks_use_roles_only_and_no_geometry_colours_or_tag_keys():
    banned = {"radius", "slot", "dead_zone", "colors"}
    for name, b in looks.BUILTIN.items():
        for k, v in b["look"].items():
            assert k not in banned and not k.startswith("tag_"), (name, k)
            if k in looks.COLOUR_KEYS:
                assert v in looks.ROLES, (name, k, v)


def test_a_built_in_changes_only_what_it_names():
    soft = looks.LookSet(ring={"look": "soft"}).global_look()
    assert soft["slot_shape"] == "squircle" and soft["hub_style"] == "disc" and soft["border_width"] == 1
    assert soft["radius"] == 145 and soft["labels"] == "name"


# --- colours ---------------------------------------------------------------------------------------------
def test_colour_resolves_a_role_and_passes_hex_and_empty_through():
    colors = {"bg": "#000000", "accent": "#f86b33"}
    assert looks.colour("accent", colors) == "#f86b33"
    assert looks.colour("#112233", colors) == "#112233"
    assert looks.colour("", colors) == ""


def test_merge_is_per_key_and_colors_are_per_colour_and_roles_stay():
    a = {"hub": 5, "hub_color": "accent", "colors": {"bg": "#000000", "text": "#ffffff"}}
    b = {"hub": 9, "colors": {"text": "#eeeeee"}}
    assert looks.merge(a, b, None) == {"hub": 9, "hub_color": "accent",
                                       "colors": {"bg": "#000000", "text": "#eeeeee"}}
    assert a["colors"]["text"] == "#ffffff"              # the layers are not changed


def test_resolve_colours_turns_roles_into_hex_against_the_look_colors():
    look = {"hub_color": "highlight", "glow_color": "", "label_color": "#101010", "colors": {"highlight": "#abcdef"}}
    out = looks.resolve_colours(look)
    assert (out["hub_color"], out["glow_color"], out["label_color"]) == ("#abcdef", "", "#101010")
    assert look["hub_color"] == "highlight"


def test_tag_colours_on_is_off_only_when_tint_and_band_are_both_none():
    assert looks.tag_colours_on({})
    assert looks.tag_colours_on({"tag_colors": "none"})
    assert looks.tag_colours_on({"tag_band": "none"})
    assert not looks.tag_colours_on({"tag_colors": "none", "tag_band": "none"})


# --- layering and origins --------------------------------------------------------------------------------
def make_set(theme_name="dark"):
    user = {"Mine": {"hub": 20, "slot_shape": "hexagon", "hub_color": "highlight", "colors": {"bg": "#111111"}}}
    ring = {"look": "soft", "hub": 30, "colors": {"accent": "#aa0000"}}
    return looks.LookSet(user, ring, theme_name)


def test_the_layers_in_order_and_where_each_value_came_from():
    ls = make_set("light")
    spec = {"preset": "Mine", "hub": 40, "colors": {"accent": "#00aa00"}}
    style = {"slot_shape": "diamond", "size": 1.1}
    org = ls.origins(spec, style)
    glo = ls.global_look()
    men = ls.menu_look(spec)
    slot = ls.slot_look(men, style)
    # default -> theme -> global preset -> global -> menu preset -> menu -> slot
    assert org["radius"] == {"from": "default", "name": ""}
    assert org["colors.bg"] == {"from": "menu-preset", "name": "Mine"}
    assert org["colors.text"] == {"from": "theme", "name": ""}
    assert org["border_width"] == {"from": "global-preset", "name": "soft"}
    assert org["hub"] == {"from": "menu", "name": ""}
    assert org["colors.accent"] == {"from": "menu", "name": ""}
    assert org["hub_color"] == {"from": "menu-preset", "name": "Mine"}
    assert org["slot_shape"] == {"from": "slot", "name": ""} and org["size"] == {"from": "slot", "name": ""}
    g = ls.origins()
    assert g["hub"] == {"from": "global", "name": ""} and g["colors.accent"] == {"from": "global", "name": ""}
    assert g["slot_shape"] == {"from": "global-preset", "name": "soft"}
    assert g["colors.bg"] == {"from": "theme", "name": ""}
    assert g["radius"] == {"from": "default", "name": ""}
    # the values follow the same order
    assert glo["hub"] == 30 and glo["slot_shape"] == "squircle" and glo["colors"]["accent"] == "#aa0000"
    assert glo["colors"]["bg"] == theme.ring_colors("light")["bg"] and glo["theme"] == "light"
    assert (men["hub"], men["slot_shape"], men["colors"]["bg"]) == (40, "hexagon", "#111111")
    assert (slot["slot_shape"], slot["size"], slot["hub"]) == ("diamond", 1.1, 40)


def test_the_dark_theme_is_default_origin_and_a_light_theme_is_theme_origin():
    assert make_set("dark").origins()["colors.text"]["from"] == "default"
    assert make_set("light").origins()["colors.text"]["from"] == "theme"


def test_a_role_resolves_after_the_merge_so_a_menu_colour_recolours_it():
    ls = looks.LookSet(ring={"colors": {"accent": "#aa0000"}})
    assert ls.global_look()["hub_color"] == "#aa0000"
    assert ls.menu_look({"preset": "", "colors": {"accent": "#00bb00"}})["hub_color"] == "#00bb00"
    assert ls.menu_look({"preset": "", "hub_color": "#123456"})["hub_color"] == "#123456"
    # a slot's role follows the menu's colours
    men = ls.menu_look({"preset": "", "colors": {"highlight": "#0000cc"}})
    assert ls.slot_look(men, {"glow_color": "highlight", "fill_color": "bg"})["glow_color"] == "#0000cc"
    assert ls.slot_look(men, {"fill_color": "bg"})["fill_color"] == men["colors"]["bg"]


def test_a_missing_preset_falls_back_to_the_level_above():
    ls = looks.LookSet(ring={"look": "gone", "hub": 7})
    assert ls.global_look()["hub"] == 7 and ls.global_look()["slot_shape"] == "circle"
    assert ls.origins()["slot_shape"]["from"] == "default"
    men = ls.menu_look({"preset": "gone2"})
    assert men == ls.global_look()
    assert ls.origins({"preset": "gone2"})["hub"]["from"] == "global"


def test_no_spec_means_the_global_look_and_every_call_returns_a_fresh_dict():
    ls = make_set()
    assert ls.menu_look() == ls.global_look() == ls.menu_look({})
    ls.global_look()["colors"]["bg"] = "#ffffff"
    assert ls.global_look()["colors"]["bg"] != "#ffffff"
    assert looks.BUILTIN["soft"]["look"] == {"slot_shape": "squircle", "border_width": 1, "icon_scale": 0.92,
                                             "glow_opacity": 0.7, "hub_style": "disc", "hub_glow": 0.6}


def test_explain_gives_values_and_origins_at_the_level_asked_for():
    ls = make_set()
    assert ls.explain()["values"] == ls.global_look()
    spec, style = {"preset": "Mine"}, {"size": 0.8}
    e = ls.explain(spec, style)
    assert e["values"] == ls.slot_look(ls.menu_look(spec), style) and e["values"]["size"] == 0.8
    assert e["origins"] == ls.origins(spec, style)
    assert set(ls.origins()) >= set(looks.LOOK_DEFAULTS) | set(looks.BEHAVIOUR_DEFAULTS)


# --- the message table -----------------------------------------------------------------------------------
@pytest.mark.parametrize("raw, message", [
    ({"hub": 99}, "x.hub: 99 must be a number from 0 to 64"),
    ({"radius": "big"}, "x.radius: 'big' must be a number from 60 to 400"),
    ({"flick": "no"}, "x.flick: 'no' must be true or false"),
    ({"animation": "wobble"}, "x.animation: 'wobble' unknown; one of " + ", ".join(looks.ANIMATIONS)),
    ({"labels": "icons"}, "x.labels: 'icons' unknown; one of name, none"),
    ({"hub_style": "star"}, "x.hub_style: 'star' unknown; one of dot, disc, ring, icon"),
    ({"when_full": 3}, "x.when_full: 3 unknown; one of grow, rings, more"),
    ({"colors": {"bg": "red"}}, "x.colors.bg: 'red' is not a #rrggbb colour"),
    ({"colors": {"accent": "highlight"}}, "x.colors.accent: 'highlight' is not a #rrggbb colour"),
    ({"colors": {"hilight": "#000000"}}, "x.colors.hilight: unknown colour (did you mean highlight?)"),
    ({"colors": 5}, 'x.colors: must be an object like {"accent": "#f86b33"}'),
    ({"hub_color": "pink"}, f"x.hub_color: 'pink' is not a #rrggbb colour or a theme colour ({ROLE_LIST})"),
    ({"hub_color": ""}, f"x.hub_color: '' is not a #rrggbb colour or a theme colour ({ROLE_LIST})"),
    ({"label_color": "#fff"}, f"x.label_color: '#fff' is not a #rrggbb colour or a theme colour ({ROLE_LIST})"),
    ({"glow_color": 5}, f"x.glow_color: 5 is not a #rrggbb colour or a theme colour ({ROLE_LIST})"),
    ({"radious": 100}, "x.radious: unknown setting (did you mean radius?)"),
    ({"qqqqqq": 1}, "x.qqqqqq: unknown setting"),
    ({"tap_ms": 5}, "x.tap_ms: is a ring setting, not part of a look; ignored"),
    ({"animation": "fade"}, "x.animation: is a ring setting, not part of a look; ignored"),
    ({"look": "soft"}, "x.look: is a ring setting, not part of a look; ignored")])
def test_look_messages(raw, message):
    got, errors = check(raw, allow=looks.LOOK_KEYS if "ring setting" in message else looks.RING_KEYS)
    assert errors == [message] and got == {}


def test_colour_keys_take_a_role_or_hex_and_some_take_empty():
    ok = {"hub_color": "lines", "label_color": "#a0b0c0", "glow_color": "", "fill_color": "bg", "border_color": ""}
    got, errors = check(ok, allow=looks.LOOK_KEYS + ("fill_color", "border_color"))
    assert errors == [] and got == ok
    assert check({"fill_color": "pink"}, looks.STYLE_KEYS)[1]


def test_a_bad_value_is_left_out_and_the_rest_is_kept_in_order():
    got, errors = check({"hub": 99, "radius": 100, "slot_shape": "blob", "labels": "none",
                         "colors": {"bg": "#000000", "text": "no"}})
    assert got == {"radius": 100, "labels": "none", "colors": {"bg": "#000000"}}
    assert [e.split(":")[0] for e in errors] == ["x.hub", "x.slot_shape", "x.colors.text"]


def test_the_ring_look_key_is_left_to_the_caller():
    got, errors = check({"look": "soft", "hub": 3}, allow=looks.RING_KEYS, prefix="ring.")
    assert errors == [] and got == {"hub": 3}


# --- names and presets -----------------------------------------------------------------------------------
@pytest.mark.parametrize("name, ok", [
    ("My look", True), ("a", True), ("A-b_c 9", True), ("x" * 32, True), ("é look", True),
    ("", False), ("x" * 33, False), (" lead", False), ("trail ", False), ("a.b", False), ("a:b", False),
    ("tab\tx", False), ("new\nline", False), ("-x", False), ("x-", False),
    ("soft", False), ("Soft", False), ("CLASSIC", False), ("constructor", False), ("__proto__", False),
    ("toString", False)])
def test_valid_name(name, ok):
    assert (looks.valid_name(name) == "") is ok, looks.valid_name(name)


def test_valid_name_messages():
    assert looks.valid_name("a.b") == "name must be 1 to 32 letters, digits, spaces, - or _"
    assert looks.valid_name("Soft") == "that name is a built-in look or is reserved, give it another"
    assert looks.valid_name("__proto__").startswith("that name is a built-in look or is reserved")


def test_check_presets_reads_valid_looks_and_reports_the_rest():
    errors = []
    raw = {"Good": {"hub": 12, "colors": {"bg": "#101010"}}, "Based": {"preset": "soft", "hub": 5},
           "Bad.name": {}, "soft": {}, "Not": [1], "Dupe": {}, "dupe": {}, "Deep": {"hub": 99, "tap_ms": 3}}
    out = looks.check_presets(raw, errors)
    assert out == {"Good": {"hub": 12, "colors": {"bg": "#101010"}}, "Based": {"hub": 5}, "Dupe": {}, "Deep": {}}
    assert errors == [
        "looks.Based.preset: a look cannot be based on another look; ignored",
        "looks.Bad.name: name must be 1 to 32 letters, digits, spaces, - or _; ignored",
        "looks.soft: that name is a built-in look or is reserved, give it another; ignored",
        "looks.Not: not an object; ignored",
        "looks.dupe: same name as 'Dupe' apart from capitals; ignored",
        "looks.Deep.hub: 99 must be a number from 0 to 64",
        "looks.Deep.tap_ms: is a ring setting, not part of a look; ignored"]


def test_check_presets_with_nothing_or_the_wrong_type():
    errors = []
    assert looks.check_presets(None, errors) == {} and errors == []
    assert looks.check_presets([1], errors) == {}
    assert errors == ['looks: must be an object like {"My look": {"slot_shape": "hexagon"}}; ignored']


def test_check_style_prefix_and_wrong_type():
    errors = []
    assert looks.check_style({"size": 2, "glow_color": "accent"}, errors, "menu m item 3") == {"glow_color": "accent"}
    assert errors == ["menu m item 3: style.size: 2 must be a number from 0.75 to 1.25"]
    errors = []
    assert looks.check_style("big", errors, "menu m item 3") == {}
    assert errors == ['menu m item 3: style must be an object like {"slot_shape": "hexagon"}; ignored']


def test_did_you_mean_is_shared_with_config():
    assert config._did_you_mean is looks.did_you_mean
    assert looks.did_you_mean("hubb", ["hub", "slot"]) == " (did you mean hub?)"
    assert looks.did_you_mean("zzzzzz", ["hub"]) == ""


# --- through config.load ---------------------------------------------------------------------------------
def test_config_round_trips_the_layers(radial_file):
    raw = {"looks": {"Mine": {"hub": 20, "hub_color": "highlight"}},
           "ring": {"look": "Mine", "colors": {"highlight": "#0000ff"}},
           "menus": {"main": {"hotkey": "Q", "look": {"preset": "tiles", "hub": 33},
                              "items": [{"brush": "A", "style": {"glow_color": "highlight"}}]}}}
    cfg = config.load(radial_file(raw))
    assert cfg.errors == []
    assert cfg.ring["hub"] == 20 and cfg.ring["hub_color"] == "#0000ff"
    m = cfg.menus["main"]
    assert m.look == cfg.looks.menu_look(m.look_spec)
    assert (m.look["hub"], m.look["slot_shape"], m.look["hub_style"]) == (33, "rounded", "ring")
    assert m.look["hub_color"] == "#0000ff"          # Mine's role, resolved by the ring's highlight
    assert m.items[0].glow == "#0000ff" and m.items[0].style == {"glow_color": "highlight"}
    assert cfg.looks.names()[-1] == "Mine"
