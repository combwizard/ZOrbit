"""config.py: loading and checking radial.json, and reading hotkeys."""
import copy
import json

import pytest

import config
import paths
import tags
import theme

GOOD_MENUS = {"main": {"title": "Main", "hotkey": "Q", "items": [{"brush": "Standard"}]}}


@pytest.fixture
def load(radial_file):
    """load(raw, tags=None) -> Config for a radial.json holding raw."""
    def run(raw, tag_store=None):
        return config.load(radial_file(raw), tag_store)
    return run


@pytest.fixture
def load_menus(load):
    """load_menus(menus, **top) -> Config for {"menus": menus, **top}."""
    def run(menus, tag_store=None, **top):
        return load({"menus": menus, **top}, tag_store)
    return run


def problems(cfg, text):
    return [e for e in cfg.errors if text in e]


def one_item_menu(*items, **settings):
    return {"hotkey": "Q", "items": list(items), **settings}


# --- the shipped default menus ------------------------------------------------------------------


def test_default_menus_load_without_problems():
    cfg = config.load(paths.DEFAULT_MENUS, tags.TagStore.from_raw({}))
    assert cfg.errors == []


def test_default_menus_load_without_a_tag_store():
    assert config.load(paths.DEFAULT_MENUS).errors == []


def test_default_menus_submenu_targets_exist():
    cfg = config.load(paths.DEFAULT_MENUS)
    targets = [it.data["menu"] for m in cfg.menus.values() for it in m.items if it.kind == "menu"]
    assert targets
    assert all(t in cfg.menus for t in targets)


def test_default_more_brushes_slot_has_a_picture():
    with open(paths.DEFAULT_MENUS, encoding="utf-8") as f:
        raw = json.load(f)
    slot = next(it for it in raw["menus"]["brushes"]["items"] if it.get("menu") == "more")
    assert slot.get("icon")


def test_starter_tag_colours_differ_from_the_ring_accent_and_highlight():
    ring = {c.lower() for c in (config.DEFAULT_RING["colors"]["accent"], config.DEFAULT_RING["colors"]["highlight"])}
    assert not {c.lower() for _, _, c in tags.STARTERS[1:]} & ring
    assert not {c.lower() for c in tags.PALETTE[:6]} & ring


def test_default_menus_hotkeys_parse():
    with open(paths.DEFAULT_MENUS, encoding="utf-8") as f:
        raw = json.load(f)
    hotkeys = [m["hotkey"] for m in raw["menus"].values() if "hotkey" in m] + [raw["browser"]["hotkey"]]
    assert hotkeys
    assert all(config.parse_hotkey(h) is not None for h in hotkeys)
    cfg = config.load(paths.DEFAULT_MENUS)
    assert cfg.menus["brushes"].hotkey is not None
    assert cfg.browser_key is not None


def test_starter_brushes_menu_lets_its_hotkey_through():
    with open(paths.DEFAULT_MENUS, encoding="utf-8") as f:
        assert json.load(f)["menus"]["brushes"]["swallow"] is False
    assert config.load(paths.DEFAULT_MENUS).menus["brushes"].swallow is False


def test_default_menus_bridge_settings():
    cfg = config.load(paths.DEFAULT_MENUS)
    assert cfg.bridge_mode == "auto"
    assert cfg.bridge_key == config.parse_hotkey("F9")


def test_loading_does_not_change_the_default_ring():
    before = copy.deepcopy(config.DEFAULT_RING)
    cfg = config.load(paths.DEFAULT_MENUS)
    cfg.ring["colors"]["bg"] = "#000000"
    cfg.ring["radius"] = 99
    assert config.DEFAULT_RING == before


# --- parse_hotkey -------------------------------------------------------------------------------


@pytest.mark.parametrize("text, vk", [("q", 0x51), ("Q", 0x51), ("a", 0x41), ("z", 0x5A), ("0", 0x30), ("9", 0x39)])
def test_parse_hotkey_letters_and_digits(text, vk):
    assert config.parse_hotkey(text).vk == vk


@pytest.mark.parametrize("n", range(1, 25))
def test_parse_hotkey_function_keys(n):
    assert config.parse_hotkey(f"F{n}").vk == 0x70 + n - 1


def test_parse_hotkey_function_keys_are_case_insensitive():
    assert config.parse_hotkey("f9").vk == 0x78


@pytest.mark.parametrize("text", ["F0", "F25", "F100"])
def test_parse_hotkey_rejects_function_keys_out_of_range(text):
    assert config.parse_hotkey(text) is None


@pytest.mark.parametrize("text, vk", [
    ("space", 0x20), ("tab", 0x09), ("enter", 0x0D), ("backspace", 0x08), ("insert", 0x2D), ("delete", 0x2E),
    ("home", 0x24), ("end", 0x23), ("pageup", 0x21), ("pagedown", 0x22), ("Space", 0x20), ("PageUp", 0x21)])
def test_parse_hotkey_named_keys(text, vk):
    assert config.parse_hotkey(text).vk == vk


@pytest.mark.parametrize("text, vk", [
    ("`", 0xC0), ("~", 0xC0), ("-", 0xBD), ("=", 0xBB), ("[", 0xDB), ("]", 0xDD), ("\\", 0xDC), (";", 0xBA),
    ("'", 0xDE), (",", 0xBC), (".", 0xBE), ("/", 0xBF)])
def test_parse_hotkey_punctuation(text, vk):
    assert config.parse_hotkey(text).vk == vk


def test_parse_hotkey_modifiers():
    hk = config.parse_hotkey("Ctrl+Alt+Shift+G")
    assert (hk.ctrl, hk.alt, hk.shift, hk.vk) == (True, True, True, 0x47)


def test_parse_hotkey_without_modifiers_has_none_set():
    hk = config.parse_hotkey("G")
    assert (hk.ctrl, hk.alt, hk.shift) == (False, False, False)


@pytest.mark.parametrize("a, b", [("Ctrl+Shift+1", "Shift+Ctrl+1"), ("Alt+Ctrl+F5", "Ctrl+Alt+F5"),
                                  ("Shift+Alt+Ctrl+Q", "Ctrl+Alt+Shift+Q")])
def test_parse_hotkey_modifier_order_does_not_matter(a, b):
    x, y = config.parse_hotkey(a), config.parse_hotkey(b)
    assert (x.vk, x.ctrl, x.alt, x.shift) == (y.vk, y.ctrl, y.alt, y.shift)


def test_parse_hotkey_modifiers_are_case_insensitive_and_control_is_ctrl():
    hk = config.parse_hotkey("CONTROL+alt+g")
    assert (hk.ctrl, hk.alt, hk.shift) == (True, True, False)


def test_parse_hotkey_a_modifier_on_punctuation():
    hk = config.parse_hotkey("Ctrl+/")
    assert (hk.vk, hk.ctrl) == (0xBF, True)


def test_parse_hotkey_keeps_the_text_without_outer_spaces():
    assert config.parse_hotkey("  Alt+G ").text == "Alt+G"


def test_parse_hotkey_allows_spaces_around_the_plus():
    hk = config.parse_hotkey("Ctrl + G")
    assert (hk.vk, hk.ctrl) == (0x47, True)


@pytest.mark.parametrize("text", ["", "   ", None, 5, [], "ab", "Foo", "Foo+G", "Ctrl+", "+", "Ctrl+Alt", "Q+", "Ctrl++",
                                  "F1+F2", "numpad1", "é"])
def test_parse_hotkey_invalid_text_gives_none(text):
    assert config.parse_hotkey(text) is None


# --- bridge -------------------------------------------------------------------------------------


def test_bridge_defaults_when_missing(load_menus):
    cfg = load_menus(GOOD_MENUS)
    assert cfg.bridge_mode == "auto"
    assert cfg.bridge_key.vk == 0x78
    assert cfg.errors == []


@pytest.mark.parametrize("mode", ["auto", "message", "key"])
def test_bridge_mode_accepts_the_three_modes(load_menus, mode):
    cfg = load_menus(GOOD_MENUS, bridge={"mode": mode})
    assert cfg.bridge_mode == mode
    assert cfg.errors == []


def test_unknown_bridge_mode_falls_back_to_auto(load_menus):
    cfg = load_menus(GOOD_MENUS, bridge={"mode": "telepathy"})
    assert cfg.bridge_mode == "auto"
    assert problems(cfg, "bridge.mode 'telepathy' unknown; using auto")


@pytest.mark.parametrize("key", ["Ctrl+F9", "Shift+F9", "Ctrl+Alt+F9", "Ctrl+Shift+F9"])
def test_bridge_key_with_ctrl_or_shift_is_rejected_and_f9_used(load_menus, key):
    cfg = load_menus(GOOD_MENUS, bridge={"key": key})
    assert cfg.bridge_key == config.parse_hotkey("F9")
    assert problems(cfg, "bridge.key must not use Ctrl or Shift")


@pytest.mark.parametrize("key", ["Alt+F9", "Alt+F11", "F10", "Alt+F10"])
def test_bridge_key_with_alt_or_f10_is_rejected_and_f9_used(load_menus, key):
    # ZBrush 2022 and 2025 ran no Apply for these when ZOrbit sent them (tested with the key stored in ZBrush).
    cfg = load_menus(GOOD_MENUS, bridge={"key": key})
    assert cfg.bridge_key == config.parse_hotkey("F9")
    assert problems(cfg, f"bridge.key {key!r} does not reach ZBrush")


@pytest.mark.parametrize("key", ["F11", "F12", "F8"])
def test_bridge_key_bare_f_keys_other_than_f10_are_accepted(load_menus, key):
    cfg = load_menus(GOOD_MENUS, bridge={"key": key})
    assert cfg.bridge_key == config.parse_hotkey(key)
    assert cfg.errors == []


def test_bridge_key_can_be_another_bare_key(load_menus):
    assert load_menus(GOOD_MENUS, bridge={"key": "F12"}).bridge_key.vk == 0x7B


def test_bridge_key_not_understood_falls_back_to_f9(load_menus):
    cfg = load_menus(GOOD_MENUS, bridge={"key": "banana"})
    assert cfg.bridge_key == config.parse_hotkey("F9")
    assert problems(cfg, "bridge.key 'banana' not understood; using F9")


def test_empty_bridge_key_is_f9_without_a_problem(load_menus):
    cfg = load_menus(GOOD_MENUS, bridge={"key": ""})
    assert cfg.bridge_key == config.parse_hotkey("F9")
    assert cfg.errors == []


# --- ring ---------------------------------------------------------------------------------------


def test_ring_values_are_read(load_menus):
    cfg = load_menus(GOOD_MENUS, ring={"radius": 200, "animation": "bounce", "labels": "none", "flick": False,
                                       "tag_band": "wide", "tag_band_opacity": 0.8,
                                       "colors": {"bg": "#101010"}})
    assert cfg.errors == []
    assert cfg.ring["radius"] == 200
    assert cfg.ring["animation"] == "bounce"
    assert cfg.ring["labels"] == "none"
    assert cfg.ring["flick"] is False
    assert cfg.ring["tag_band"] == "wide"
    assert cfg.ring["tag_band_opacity"] == 0.8
    assert cfg.ring["colors"]["bg"] == "#101010"
    assert cfg.ring["colors"]["accent"] == config.DEFAULT_RING["colors"]["accent"]


def test_ring_defaults_when_missing(load_menus):
    assert load_menus(GOOD_MENUS).ring == config.DEFAULT_RING


@pytest.mark.parametrize("key, value", [
    ("radius", 5), ("radius", 5000), ("slot", 10), ("dead_zone", 500), ("hub", 99), ("hub", -1),
    ("tap_ms", -1), ("timeout_s", 1),
    ("tag_band_opacity", 1.5), ("tag_glow_opacity", -0.1), ("tag_tint_opacity", 2)])
def test_out_of_range_ring_values_fall_back_to_the_default(load_menus, key, value):
    cfg = load_menus(GOOD_MENUS, ring={key: value})
    assert cfg.ring[key] == config.DEFAULT_RING[key]
    assert problems(cfg, f"ring.{key}:")


@pytest.mark.parametrize("key, value", [("radius", "big"), ("radius", None), ("slot", [72]), ("tap_ms", "250")])
def test_non_numeric_ring_values_fall_back_to_the_default(load_menus, key, value):
    cfg = load_menus(GOOD_MENUS, ring={key: value})
    assert cfg.ring[key] == config.DEFAULT_RING[key]
    assert problems(cfg, f"ring.{key}:")


@pytest.mark.parametrize("key, value", [
    ("animation", "wobble"), ("labels", "icons"), ("tag_colors", "neon"), ("tag_band", "huge"),
    ("tag_tint_style", "dotted"), ("tag_tint_blend", "screen"), ("slot_shape", "hexagon")])
def test_unknown_ring_choices_fall_back_to_the_default(load_menus, key, value):
    cfg = load_menus(GOOD_MENUS, ring={key: value})
    assert cfg.ring[key] == config.DEFAULT_RING[key]
    assert problems(cfg, f"ring.{key}: {value!r} unknown")


def test_the_slot_shape_is_read_and_defaults_to_a_circle(load_menus):
    assert load_menus(GOOD_MENUS, ring={"slot_shape": "rounded"}).ring["slot_shape"] == "rounded"
    assert load_menus(GOOD_MENUS).ring["slot_shape"] == "circle"


@pytest.mark.parametrize("key", ["flick", "hover_submenus"])
def test_ring_switches_must_be_booleans(load_menus, key):
    cfg = load_menus(GOOD_MENUS, ring={key: "no"})
    assert cfg.ring[key] is True
    assert problems(cfg, f"ring.{key}: 'no' must be true or false")


def test_a_bad_ring_colour_keeps_the_default(load_menus):
    cfg = load_menus(GOOD_MENUS, ring={"colors": {"bg": "red", "text": "#fff"}})
    assert cfg.ring["colors"] == config.DEFAULT_RING["colors"]
    assert problems(cfg, "ring.colors.bg: 'red' is not a #rrggbb colour")
    assert problems(cfg, "ring.colors.text: '#fff' is not a #rrggbb colour")


def test_misspelt_ring_key_suggests_the_right_one(load_menus):
    cfg = load_menus(GOOD_MENUS, ring={"radious": 100})
    assert problems(cfg, "ring.radious: unknown setting (did you mean radius?)")
    assert cfg.ring["radius"] == config.DEFAULT_RING["radius"]


def test_unrelated_ring_key_is_reported_without_a_suggestion(load_menus):
    cfg = load_menus(GOOD_MENUS, ring={"qqqqqq": 1})
    assert cfg.errors == ["ring.qqqqqq: unknown setting"]


# --- the theme ----------------------------------------------------------------------------------
def test_a_light_theme_gives_the_light_colours_and_says_so(radial_file):
    cfg = config.load(radial_file({"menus": GOOD_MENUS}), theme="light")
    assert cfg.ring["colors"] == theme.ring_colors("light")
    assert cfg.ring["theme"] == "light"
    assert not cfg.errors


def test_a_colour_set_in_the_file_wins_over_the_light_default(radial_file):
    path = radial_file({"menus": GOOD_MENUS, "ring": {"colors": {"accent": "#123456"}}})
    cfg = config.load(path, theme="light")
    assert cfg.ring["colors"]["accent"] == "#123456"
    assert cfg.ring["colors"]["bg"] == theme.ring_colors("light")["bg"]


def test_the_dark_theme_changes_nothing(radial_file):
    cfg = config.load(radial_file({"menus": GOOD_MENUS}), theme="dark")
    assert cfg.ring == config.DEFAULT_RING
    assert "theme" not in cfg.ring


def test_a_theme_key_in_the_file_is_an_unknown_setting(load_menus):
    cfg = load_menus(GOOD_MENUS, ring={"theme": "light"})
    assert problems(cfg, "ring.theme: unknown setting")
    assert "theme" not in cfg.ring


def test_an_unknown_theme_name_loads_as_dark(radial_file):
    cfg = config.load(radial_file({"menus": GOOD_MENUS}), theme="blue")
    assert cfg.ring == config.DEFAULT_RING


def test_default_ring_has_the_colours_of_the_theme_and_no_theme_key():
    light = config.default_ring("light")
    assert light["colors"] == theme.ring_colors("light")
    assert "theme" not in light
    assert {k: v for k, v in light.items() if k != "colors"} == {k: v for k, v in config.DEFAULT_RING.items() if k != "colors"}
    assert config.default_ring() == config.DEFAULT_RING
    assert config.default_ring("light") is not config.default_ring("light")


# --- menus and their settings -------------------------------------------------------------------


def test_misspelt_menu_key_suggests_the_right_one(load_menus):
    cfg = load_menus({"main": {"titel": "Main", "hotkey": "Q", "items": [{"brush": "Standard"}]}})
    assert problems(cfg, "menu main: unknown setting 'titel' (did you mean title?)")
    assert cfg.menus["main"].title == "main"


def test_menu_title_defaults_to_its_id(load_menus):
    assert load_menus({"main": one_item_menu({"brush": "Standard"})}).menus["main"].title == "main"


def test_menu_settings_are_read(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "Standard"}, title="Brushes", swallow=False,
                                            animation="spiral", fan=True)})
    m = cfg.menus["main"]
    assert (m.title, m.swallow, m.animation, m.fan) == ("Brushes", False, "spiral", True)
    assert cfg.errors == []


def test_menu_defaults_are_swallow_true_and_no_fan(load_menus):
    m = load_menus({"main": one_item_menu({"brush": "Standard"})}).menus["main"]
    assert (m.swallow, m.fan, m.animation) == (True, False, "")


def test_unknown_menu_animation_is_dropped(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "Standard"}, animation="wobble")})
    assert cfg.menus["main"].animation == ""
    assert problems(cfg, "menu main: animation 'wobble' unknown; using ring.animation")


def test_swallow_must_be_a_boolean(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "Standard"}, swallow="no")})
    assert cfg.menus["main"].swallow is True
    assert problems(cfg, "menu main: swallow 'no' must be true or false; using true")


def test_menu_ids_starting_with_tag_are_reserved(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "Standard"}),
                      "tag:blocking": {"items": [{"brush": "Standard"}]}})
    assert "tag:blocking" not in cfg.menus
    assert problems(cfg, "menu tag:blocking: ids starting with 'tag:' are reserved")


@pytest.mark.parametrize("mid", ["__proto__", "constructor", "toString"])
def test_menu_ids_a_javascript_object_already_has_are_reserved(load_menus, mid):
    cfg = load_menus({"main": one_item_menu({"brush": "Standard"}),
                      mid: {"items": [{"brush": "Standard"}]}})
    assert mid not in cfg.menus
    assert problems(cfg, f"menu {mid}: that id is reserved, give the menu another")


def test_a_menu_that_is_not_an_object_is_skipped(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "Standard"}), "odd": ["x"]})
    assert list(cfg.menus) == ["main"]
    assert problems(cfg, "menu odd: not an object")


def test_a_bom_at_the_start_of_the_file_is_accepted(write_json):
    text = json.dumps({"menus": GOOD_MENUS})
    cfg = config.load(write_json(text, "radial.json", encoding="utf-8-sig"))
    assert cfg.errors == []
    assert "main" in cfg.menus


def test_config_remembers_its_path_and_mtime(radial_file):
    import os
    path = radial_file({"menus": GOOD_MENUS})
    cfg = config.load(path)
    assert cfg.path == path
    assert cfg.mtime == os.stat(path).st_mtime


def test_a_file_that_is_not_json_raises(write_json):
    with pytest.raises(ValueError):
        config.load(write_json("{not json", "radial.json"))


# --- hotkeys across menus -----------------------------------------------------------------------


def test_menu_hotkey_is_parsed(load_menus):
    assert load_menus({"main": one_item_menu({"brush": "Standard"}, hotkey="Alt+G")}).menus["main"].hotkey.alt


def test_duplicate_hotkey_is_reported_and_the_second_menu_loses_it(load_menus):
    cfg = load_menus({"a": one_item_menu({"brush": "A"}, hotkey="Q"),
                      "b": one_item_menu({"brush": "B"}, hotkey="Q")})
    assert cfg.menus["a"].hotkey is not None
    assert cfg.menus["b"].hotkey is None
    assert problems(cfg, "menu b: hotkey 'Q' already used by menu a")


def test_duplicate_hotkey_ignores_case_and_modifier_order(load_menus):
    cfg = load_menus({"a": one_item_menu({"brush": "A"}, hotkey="Ctrl+Shift+q"),
                      "b": one_item_menu({"brush": "B"}, hotkey="Shift+Ctrl+Q")})
    assert cfg.menus["b"].hotkey is None
    assert problems(cfg, "already used by menu a")


def test_same_key_with_other_modifiers_is_not_a_duplicate(load_menus):
    cfg = load_menus({"a": one_item_menu({"brush": "A"}, hotkey="Q"),
                      "b": one_item_menu({"brush": "B"}, hotkey="Alt+Q")})
    assert cfg.menus["a"].hotkey and cfg.menus["b"].hotkey
    assert cfg.errors == []


def test_hotkey_not_understood_is_reported(load_menus):
    cfg = load_menus({"a": one_item_menu({"brush": "A"}, hotkey="Q"),
                      "b": one_item_menu({"brush": "B"}, hotkey="Blah")})
    assert cfg.menus["b"].hotkey is None
    assert problems(cfg, "menu b: hotkey 'Blah' not understood")


def test_menus_without_a_hotkey_are_allowed_as_submenus(load_menus):
    cfg = load_menus({"a": one_item_menu({"menu": "b"}, hotkey="Q"), "b": {"items": [{"brush": "B"}]}})
    assert cfg.menus["b"].hotkey is None
    assert cfg.errors == []


def test_no_menu_hotkey_is_a_problem(load_menus):
    cfg = load_menus({"a": {"items": [{"brush": "A"}]}})
    assert cfg.errors == ["no menu has a hotkey, so nothing can open the ring"]


def test_a_menu_that_lost_its_hotkey_to_a_typo_still_leaves_the_no_hotkey_problem(load_menus):
    cfg = load_menus({"a": one_item_menu({"brush": "A"}, hotkey="Blah")})
    assert problems(cfg, "no menu has a hotkey")


def test_browser_hotkey_is_read(load_menus):
    cfg = load_menus(GOOD_MENUS, browser={"hotkey": "Alt+B"})
    assert (cfg.browser_key.vk, cfg.browser_key.alt) == (0x42, True)
    assert cfg.errors == []


def test_browser_hotkey_used_by_a_menu_is_reported_and_dropped(load_menus):
    cfg = load_menus(GOOD_MENUS, browser={"hotkey": "Q"})
    assert cfg.browser_key is None
    assert problems(cfg, "browser.hotkey 'Q' already used by menu main")


def test_browser_hotkey_not_understood_is_reported(load_menus):
    cfg = load_menus(GOOD_MENUS, browser={"hotkey": "Blah"})
    assert cfg.browser_key is None
    assert problems(cfg, "browser.hotkey 'Blah' not understood")


def test_browser_section_that_is_not_an_object_is_reported(load_menus):
    cfg = load_menus(GOOD_MENUS, browser="Alt+B")
    assert cfg.browser_key is None
    assert problems(cfg, "browser: must be an object")


# --- submenus and menus with nothing in them ----------------------------------------------------


def test_submenu_pointing_at_a_missing_menu_is_dropped(load_menus):
    cfg = load_menus({"main": one_item_menu({"menu": "ghost"}, {"brush": "Standard"})})
    assert [it.kind for it in cfg.menus["main"].items] == ["brush"]
    assert problems(cfg, "menu main item 1: submenu 'ghost' does not exist")


def test_menu_with_no_items_is_dropped(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "Standard"}), "empty": {"items": []}})
    assert list(cfg.menus) == ["main"]
    assert problems(cfg, "menu empty: no usable items")


def test_menu_with_no_items_key_is_dropped(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "Standard"}), "bare": {"title": "Bare"}})
    assert "bare" not in cfg.menus
    assert problems(cfg, "menu bare: no usable items")


def test_menu_whose_items_are_all_invalid_is_dropped(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "Standard"}), "bad": {"items": [{"nothing": 1}]}})
    assert "bad" not in cfg.menus
    assert problems(cfg, "menu bad item 1: needs exactly one of")
    assert problems(cfg, "menu bad: no usable items")


def test_submenu_item_pointing_at_a_dropped_menu_is_dropped_too(load_menus):
    cfg = load_menus({"main": one_item_menu({"menu": "bad"}, {"brush": "Standard"}),
                      "bad": {"items": [{"nothing": 1}]}})
    assert [it.kind for it in cfg.menus["main"].items] == ["brush"]
    assert problems(cfg, "menu main item 1: submenu 'bad' has no usable items")


def test_dropping_a_menu_cascades_up_through_menus_that_only_held_it(load_menus):
    cfg = load_menus({"main": one_item_menu({"menu": "mid"}, {"brush": "Standard"}),
                      "mid": {"items": [{"menu": "bad"}]},
                      "bad": {"items": []}})
    assert list(cfg.menus) == ["main"]
    assert [it.kind for it in cfg.menus["main"].items] == ["brush"]
    assert problems(cfg, "menu mid item 1: submenu 'bad' has no usable items")
    assert problems(cfg, "menu mid: no usable items")
    assert problems(cfg, "menu main item 1: submenu 'mid' has no usable items")


def test_a_menu_whose_only_item_is_a_dropped_submenu_is_dropped_with_its_hotkey(load_menus):
    cfg = load_menus({"main": one_item_menu({"menu": "bad"}), "bad": {"items": []}})
    assert cfg.menus == {}
    assert problems(cfg, "menu main: no usable items")


def test_item_numbers_in_problems_count_from_one_in_the_file(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "A"}, {"brush": ""}, {"brush": "C"})})
    assert problems(cfg, "menu main item 2: 'brush' must be a non-empty string")
    assert [it.label for it in cfg.menus["main"].items] == ["A", "C"]


def test_menus_missing_is_a_problem_and_no_menus(load):
    cfg = load({"bridge": {"mode": "auto"}})
    assert cfg.menus == {}
    assert problems(cfg, "menus: must be a non-empty object")


@pytest.mark.parametrize("menus", [[], ["a"], "main", 5, {}])
def test_menus_that_are_not_a_filled_object_give_a_problem_naming_the_section(load, menus):
    cfg = load({"menus": menus})
    assert cfg.menus == {}
    assert problems(cfg, "menus: must be a non-empty object")


# --- tag items ----------------------------------------------------------------------------------


def test_tag_item_with_an_unknown_tag_is_reported_but_the_slot_stays(load_menus):
    store = tags.TagStore.from_raw({"tags": {"blocking": {"label": "Blocking", "color": "#F86B33"}}})
    cfg = load_menus({"main": one_item_menu({"tag": "nope"}, {"tag": "blocking"})}, store)
    assert problems(cfg, "menu main item 1: tag 'nope' does not exist; the slot stays empty")
    assert [it.tag for it in cfg.menus["main"].items] == ["nope", "blocking"]
    assert len(cfg.errors) == 1


def test_tag_item_with_a_known_tag_is_labelled_by_the_tag(load_menus):
    store = tags.TagStore.from_raw({"tags": {"blocking": {"label": "Blocking!", "color": "#F86B33"}}})
    cfg = load_menus({"main": one_item_menu({"tag": "blocking"})}, store)
    assert cfg.errors == []
    assert cfg.menus["main"].items[0].label == "Blocking!"


def test_favourite_tag_always_exists_in_a_store(load_menus):
    cfg = load_menus({"main": one_item_menu({"tag": "favourite"})}, tags.TagStore.from_raw({}))
    assert cfg.errors == []
    assert cfg.menus["main"].items[0].label == "Favourites"


def test_tag_items_are_not_checked_without_a_tag_store(load_menus):
    cfg = load_menus({"main": one_item_menu({"tag": "nope"})})
    assert cfg.errors == []
    assert cfg.menus["main"].items[0].label == "nope"


def test_browser_item_with_an_unknown_tag_is_reported(load_menus):
    cfg = load_menus({"main": one_item_menu({"browser": "nope"})}, tags.TagStore.from_raw({}))
    assert problems(cfg, "menu main item 1: tag 'nope' does not exist; the browser opens unfiltered")
    assert cfg.menus["main"].items[0].kind == "browser"


def test_browser_item_with_an_empty_tag_is_not_checked(load_menus):
    cfg = load_menus({"main": one_item_menu({"browser": ""})}, tags.TagStore.from_raw({}))
    assert cfg.errors == []
    assert cfg.menus["main"].items[0].label == "Browser"


@pytest.mark.parametrize("kind", ["brush", "alpha", "material", "texture"])
def test_browser_item_kind_accepts_the_asset_kinds(load_menus, kind):
    assert load_menus({"main": one_item_menu({"browser": "", "kind": kind})}).errors == []


def test_browser_item_kind_must_be_an_asset_kind(load_menus):
    cfg = load_menus({"main": one_item_menu({"browser": "", "kind": "tool"}, {"brush": "A"})})
    assert problems(cfg, "browser 'kind' must be one of brush, alpha, material, texture")
    assert [it.kind for it in cfg.menus["main"].items] == ["brush"]


def test_browser_item_value_must_be_a_string(load_menus):
    cfg = load_menus({"main": one_item_menu({"browser": 5}, {"brush": "A"})})
    assert problems(cfg, "'browser' must be a string")


# --- items --------------------------------------------------------------------------------------


@pytest.mark.parametrize("item", [
    {"brush": "Standard"}, {"alpha": "Alpha 58"}, {"material": "SkinShade4"}, {"texture": "Txtr01"},
    {"press": "Tool:Masking:Clear"}, {"set": "Draw:Draw Size", "value": 64}, {"toggle": "Transform:PolyF"},
    {"steps": [{"press": "Tool:Masking:Clear"}]}, {"auto": "brush"}, {"tag": "blocking"}, {"browser": ""}])
def test_each_action_type_loads(load_menus, item):
    cfg = load_menus({"main": one_item_menu(item)})
    assert cfg.errors == []
    assert cfg.menus["main"].items[0].kind == next(iter(item))


def test_menu_item_loads_when_the_target_exists(load_menus):
    cfg = load_menus({"main": one_item_menu({"menu": "sub"}), "sub": {"title": "Sub Menu", "items": [{"brush": "A"}]}})
    assert cfg.errors == []
    assert cfg.menus["main"].items[0].label == "Sub Menu"


def test_item_that_is_not_an_object_is_reported(load_menus):
    cfg = load_menus({"main": one_item_menu("Standard", {"brush": "A"})})
    assert problems(cfg, "menu main item 1: not an object")


def test_item_with_two_actions_is_reported(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "A", "press": "B"}, {"brush": "C"})})
    assert problems(cfg, "menu main item 1: needs exactly one of")


def test_item_label_and_icon_are_kept_and_not_part_of_the_action_data(load_menus):
    it = load_menus({"main": one_item_menu({"brush": "Inflat", "label": "Inflate", "icon": "Standard"})}) \
        .menus["main"].items[0]
    assert (it.label, it.icon, it.data) == ("Inflate", "Standard", {"brush": "Inflat"})


def test_a_glow_colour_is_read_onto_the_item_and_is_not_part_of_the_action_data(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "Inflat", "glow": "#ff8800"}, {"brush": "Standard"})})
    it = cfg.menus["main"].items[0]
    assert (it.glow, it.data) == ("#ff8800", {"brush": "Inflat"})
    assert cfg.menus["main"].items[1].glow == ""
    assert not problems(cfg, "unknown setting")


@pytest.mark.parametrize("glow", ["orange", "#ff88", "ff8800", 5])
def test_a_glow_that_is_not_rrggbb_is_reported_and_dropped_but_the_item_stays(load_menus, glow):
    cfg = load_menus({"main": one_item_menu({"brush": "Inflat", "glow": glow}, {"brush": "Standard"})})
    assert problems(cfg, "menu main item 1: glow")
    assert problems(cfg, "is not a #rrggbb colour")
    assert [(it.data["brush"], it.glow) for it in cfg.menus["main"].items] == [("Inflat", ""), ("Standard", "")]


@pytest.mark.parametrize("item, label", [
    ({"brush": "ClayBuildup"}, "ClayBuildup"), ({"press": "Tool:Masking:Clear"}, "Clear"),
    ({"toggle": "Transform:PolyF"}, "PolyF"), ({"set": "Draw:Draw Size", "value": 1}, "Draw Size"),
    ({"steps": [{"brush": "A"}]}, "Steps"), ({"auto": "brush"}, "Auto"), ({"browser": ""}, "Browser")])
def test_default_labels(load_menus, item, label):
    assert load_menus({"main": one_item_menu(item)}).menus["main"].items[0].label == label


def test_auto_item_must_be_a_known_kind(load_menus):
    cfg = load_menus({"main": one_item_menu({"auto": "alpha"}, {"brush": "A"})})
    assert problems(cfg, "'auto' must be one of brush")


@pytest.mark.parametrize("item", [{"brush": ""}, {"brush": "  "}, {"brush": 5}, {"press": None}, {"toggle": ["x"]}])
def test_action_values_must_be_non_empty_strings(load_menus, item):
    cfg = load_menus({"main": one_item_menu(item, {"brush": "A"})})
    assert problems(cfg, "must be a non-empty string")


# --- set ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("value", [64, 0, -3, 0.25, 1e3])
def test_set_accepts_a_number(load_menus, value):
    assert load_menus({"main": one_item_menu({"set": "Draw:Draw Size", "value": value})}).errors == []


def test_set_without_a_value_is_reported(load_menus):
    cfg = load_menus({"main": one_item_menu({"set": "Draw:Draw Size"}, {"brush": "A"})})
    assert problems(cfg, "menu main item 1: 'set' needs a 'value'")


@pytest.mark.parametrize("value", ["64", True, False, None, [1]])
def test_set_value_must_be_a_number(load_menus, value):
    cfg = load_menus({"main": one_item_menu({"set": "Draw:Draw Size", "value": value}, {"brush": "A"})})
    assert problems(cfg, "menu main item 1: 'set' value must be a number")
    assert len(cfg.menus["main"].items) == 1


# --- steps --------------------------------------------------------------------------------------


def test_steps_of_plain_actions_are_accepted(load_menus):
    steps = [{"press": "Tool:Masking:Clear"}, {"brush": "Standard"}, {"alpha": "A"}, {"material": "M"},
             {"texture": "T"}, {"set": "Draw:Draw Size", "value": 8}, {"toggle": "Transform:PolyF"}]
    assert load_menus({"main": one_item_menu({"steps": steps})}).errors == []


def test_steps_cannot_be_nested(load_menus):
    cfg = load_menus({"main": one_item_menu({"steps": [{"steps": [{"brush": "A"}]}]}, {"brush": "B"})})
    assert problems(cfg, "menu main item 1 step 1: 'steps' must be a non-empty list")
    assert [it.kind for it in cfg.menus["main"].items] == ["brush"]


@pytest.mark.parametrize("step", [{"menu": "sub"}, {"auto": "brush"}, {"tag": "blocking"}, {"browser": ""}])
def test_steps_cannot_open_menus_hold_auto_slots_or_open_tags_and_the_browser(load_menus, step):
    cfg = load_menus({"main": one_item_menu({"steps": [{"brush": "A"}, step]}, {"brush": "B"}),
                      "sub": {"items": [{"brush": "C"}]}})
    assert problems(cfg, "menu main item 1 step 2: steps cannot open menus, nest steps, be auto slots")
    assert [it.kind for it in cfg.menus["main"].items] == ["brush"]


@pytest.mark.parametrize("steps", [[], "press", {"press": "x"}, None])
def test_steps_must_be_a_non_empty_list(load_menus, steps):
    cfg = load_menus({"main": one_item_menu({"steps": steps}, {"brush": "B"})})
    assert problems(cfg, "menu main item 1: 'steps' must be a non-empty list")


def test_a_bad_step_is_reported_with_its_number(load_menus):
    cfg = load_menus({"main": one_item_menu({"steps": [{"brush": "A"}, {"set": "X"}]}, {"brush": "B"})})
    assert problems(cfg, "menu main item 1 step 2: 'set' needs a 'value'")


def test_step_that_is_not_an_object_is_reported(load_menus):
    cfg = load_menus({"main": one_item_menu({"steps": ["A"]}, {"brush": "B"})})
    assert problems(cfg, "menu main item 1 step 1: not an object")


# --- sections of the wrong type, fan, names and icons ------------------------------------------


def test_bridge_section_that_is_not_an_object_is_reported_and_defaults_are_used(load):
    cfg = load({"bridge": "F9", "menus": GOOD_MENUS})
    assert problems(cfg, "bridge:")
    assert cfg.bridge_mode == "auto"
    assert cfg.bridge_key == config.parse_hotkey("F9")
    assert "main" in cfg.menus


def test_ring_section_that_is_not_an_object_is_reported_and_defaults_are_used(load):
    cfg = load({"ring": "big", "menus": GOOD_MENUS})
    assert problems(cfg, "ring:")
    assert cfg.ring == config.DEFAULT_RING
    assert "main" in cfg.menus


def test_top_level_list_is_refused_with_a_plain_message(load):
    with pytest.raises(ValueError, match="radial.json must be a JSON object"):
        load([{"menus": GOOD_MENUS}])


def test_fan_that_is_not_a_boolean_is_reported_and_treated_as_false(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "A"}, fan="false")})
    assert problems(cfg, "menu main: fan")
    assert cfg.menus["main"].fan is False


@pytest.mark.parametrize("name", ["a\\b", "a/b", "C:Standard", "..", "a..b", "..\\evil"])
def test_brush_name_with_a_path_in_it_is_reported_and_the_item_skipped(load_menus, name):
    cfg = load_menus({"main": one_item_menu({"brush": name}, {"brush": "Standard"})})
    assert problems(cfg, "menu main item 1:")
    assert [it.data["brush"] for it in cfg.menus["main"].items] == ["Standard"]


@pytest.mark.parametrize("icon", ["\\\\server\\share\\x.png", "//server/share/x.png"])
def test_icon_that_is_a_network_path_is_reported_and_dropped_but_the_item_stays(load_menus, icon):
    cfg = load_menus({"main": one_item_menu({"brush": "Evil", "icon": icon}, {"brush": "Standard"})})
    assert problems(cfg, "menu main item 1: icon")
    assert problems(cfg, "not a network path")
    assert [(it.data["brush"], it.icon) for it in cfg.menus["main"].items] == [("Evil", ""), ("Standard", "")]


def test_icon_that_is_a_local_path_is_kept(load_menus, tmp_path):
    png = tmp_path / "a.png"
    png.write_bytes(b"x")
    cfg = load_menus({"main": one_item_menu({"brush": "A", "icon": str(png)})})
    assert not problems(cfg, "icon")
    assert cfg.menus["main"].items[0].icon == str(png)


@pytest.mark.parametrize("icon", ["Standard", "ClayTubes", "Move Topological", "Clay.v2", "my brush"])
def test_icon_that_is_a_brush_name_is_not_flagged(load_menus, icon):
    cfg = load_menus({"main": one_item_menu({"brush": "A", "icon": icon})})
    assert not problems(cfg, "icon")
    assert cfg.menus["main"].items[0].icon == icon


@pytest.mark.parametrize("icon", ["icons\\a.png", "icons/a.png", ".\\a.png", "a.png", "clay.PNG", "mat.zmt",
                                  "\\icons\\a.png", "C:a.png", "sub\\Standard"])
def test_icon_that_is_a_relative_path_is_reported_but_the_item_stays(load_menus, icon):
    cfg = load_menus({"main": one_item_menu({"brush": "A", "icon": icon}, {"brush": "Standard"})})
    assert problems(cfg, f"menu main item 1: icon '{icon}' must be a full path, such as C:\\Art\\clay.png")
    assert [(it.data["brush"], it.icon) for it in cfg.menus["main"].items] == [("A", icon), ("Standard", "")]


def test_icon_with_a_full_path_to_a_missing_file_is_a_warning_that_keeps_the_item(load_menus, tmp_path):
    missing = str(tmp_path / "gone.png")
    cfg = load_menus({"main": one_item_menu({"brush": "A", "icon": missing})})
    assert problems(cfg, f"menu main item 1: icon file not found: {missing}")
    assert cfg.menus["main"].items[0].icon == missing


@pytest.mark.parametrize("kind", ["alpha", "material", "texture"])
def test_other_asset_names_with_a_path_in_them_are_reported_too(load_menus, kind):
    cfg = load_menus({"main": one_item_menu({kind: "a\\b"}, {"brush": "Standard"})})
    assert problems(cfg, f"menu main item 1: {kind} name 'a\\b' must not contain \\ / : or ..")
    assert [it.kind for it in cfg.menus["main"].items] == ["brush"]


def test_a_step_with_a_path_in_its_name_skips_the_item(load_menus):
    cfg = load_menus({"main": one_item_menu({"steps": [{"brush": "A"}, {"alpha": "../x"}]}, {"brush": "B"})})
    assert problems(cfg, "menu main item 1 step 2: alpha name")
    assert [it.kind for it in cfg.menus["main"].items] == ["brush"]


def test_browser_section_that_is_not_an_object_is_reported(load):
    cfg = load({"browser": "Alt+B", "menus": GOOD_MENUS})
    assert problems(cfg, "browser:")
    assert cfg.browser_key is None


@pytest.mark.parametrize("value", [True, False])
def test_a_ring_number_must_not_be_a_boolean(load, value):
    cfg = load({"ring": {"radius": value, "tag_band_opacity": value}, "menus": GOOD_MENUS})
    assert problems(cfg, "ring.radius")
    assert problems(cfg, "ring.tag_band_opacity")
    assert cfg.ring["radius"] == config.DEFAULT_RING["radius"]


@pytest.mark.parametrize("raw, text", [
    ({"ring": {"colors": {"hilight": "#000000"}}}, "ring.colors.hilight: unknown colour (did you mean highlight?)"),
    ({"bridge": {"mod": "key"}}, "bridge.mod: unknown setting (did you mean mode?)"),
    ({"browser": {"hotkeys": "Alt+B"}}, "browser.hotkeys: unknown setting (did you mean hotkey?)")])
def test_unknown_keys_in_small_sections_get_a_suggestion(load, raw, text):
    cfg = load({**raw, "menus": GOOD_MENUS})
    assert problems(cfg, text)


def test_unknown_key_in_an_item_gets_a_suggestion(load_menus):
    cfg = load_menus({"main": one_item_menu({"brush": "A", "lable": "Hi"})})
    assert problems(cfg, "menu main item 1: unknown setting 'lable' (did you mean label?)")
    assert "main" in cfg.menus


def test_known_item_keys_are_not_reported(load_menus):
    cfg = load_menus({"main": one_item_menu({"set": "Draw:Draw Size", "value": 5, "label": "S", "icon": "x"},
                                            {"browser": "", "kind": "alpha"})})
    assert not problems(cfg, "unknown setting")


class BrokenTags:
    error = "Expecting value: line 1 column 2 (char 1)"

    def has(self, key):
        return False

    def label(self, key):
        return ""


def test_tags_that_could_not_be_read_are_reported_once_not_per_slot(load_menus):
    cfg = load_menus({"main": one_item_menu({"tag": "a"}, {"tag": "b"}, {"tag": "c"}, {"browser": "d"})},
                     BrokenTags())
    assert problems(cfg, "tags.json could not be read: Expecting value")
    assert len([e for e in cfg.errors if "tags.json" in e]) == 1
    assert not problems(cfg, "does not exist")
    assert "tag slots stay empty until it is fixed" in problems(cfg, "tags.json")[0]
