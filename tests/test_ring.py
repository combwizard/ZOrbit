"""ring.py: radius growth, fonts for other scripts, label pills, draw order and the sprite cache.

Nothing here opens a window: Ring.preview and the sprite methods only need Pillow.
"""
import copy
import dataclasses
import math
import os
import shutil
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

import config
import ring
import shapes
import theme

SEGOE = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeuib.ttf")
needs_fonts = pytest.mark.skipif(not os.path.isfile(SEGOE), reason="needs the Windows fonts folder")


def make_menu(n=4, mid="m", labels=None, title="Test"):
    labels = labels or [f"Item {i}" for i in range(n)]
    items = [config.Item(lb, "brush", {"brush": lb}) for lb in labels]
    return SimpleNamespace(id=mid, title=title, items=items, animation="", fan=False)


def make_cfg(**over):
    cfg = copy.deepcopy(config.DEFAULT_RING)
    cfg.update(over)
    return cfg


def make_ring(menu=None, icon_for=None, log=None, **over):
    return ring.Ring(menu or make_menu(), make_cfg(**over), icon_for or (lambda it: None), lambda *a: None,
                     log or (lambda m: None), held=False)


@pytest.fixture(autouse=True)
def empty_sprite_cache():
    ring._sprite_cache.clear()
    yield
    ring._sprite_cache.clear()


# --- radius ------------------------------------------------------------------------------------
def test_radius_stays_at_its_setting_while_neighbours_have_room():
    r = make_ring(make_menu(4))
    r._geometry(1.0)
    assert r.R == 145


@pytest.mark.parametrize("n", [12, 24])
def test_radius_grows_until_neighbouring_slots_are_one_and_a_quarter_slots_apart(n):
    r = make_ring(make_menu(n))
    r._geometry(1.0)
    assert r.R > 145
    assert r.R == pytest.approx(1.25 * 72 / (2 * math.sin(math.pi / n)))
    (x0, y0), (x1, y1) = r.seats[0], r.seats[1]
    assert math.hypot((x1 - x0) * r.R, (y1 - y0) * r.R) == pytest.approx(1.25 * 72)


def test_radius_growth_follows_the_scale_and_the_rest_of_the_geometry():
    r1, r2 = make_ring(make_menu(24)), make_ring(make_menu(24))
    r1._geometry(1.0)
    r2._geometry(2.0)
    assert r2.R == pytest.approx(2 * r1.R)
    assert r2.flick_r == pytest.approx(r2.R + r2.slot * 0.56)
    assert r2.rsize >= 2 * (r2.R + r2.slot / 2)


def test_a_bigger_setting_beats_the_minimum():
    r = make_ring(make_menu(12), radius=300)
    r._geometry(1.0)
    assert r.R == 300


def test_one_slot_needs_no_growth():
    r = make_ring(make_menu(1))
    r._geometry(1.0)
    assert r.R == 145


# --- fonts -------------------------------------------------------------------------------------
@needs_fonts
def test_latin_greek_and_cyrillic_text_uses_segoe(monkeypatch):
    for text in ("Clear Mask", "Café", "Ωmega", "Привет", "Wait…"):
        assert ring._font_for(text, 12).path.lower().endswith("segoeuib.ttf")
    assert ring._font_for("Clear Mask", 12, bold=False).path.lower().endswith("segoeui.ttf")


@needs_fonts
def test_cjk_text_takes_a_cjk_font_when_the_file_exists(tmp_path, monkeypatch):
    for name in ("msyhbd.ttc", "YuGothB.ttc", "malgunbd.ttf", "segoeuib.ttf"):
        shutil.copy(SEGOE, tmp_path / name)               # any font file will do: the choice is by name
    monkeypatch.setattr(ring, "_fonts_dir", lambda: str(tmp_path))
    assert ring._font_for("中文笔刷", 12).path.endswith("msyhbd.ttc")
    assert ring._font_for("ブラシ", 12).path.endswith("YuGothB.ttc")       # kana: Yu Gothic first
    assert ring._font_for("브러시", 12).path.endswith("malgunbd.ttf")       # Hangul: Malgun first
    assert ring._font_for("Latin 中文", 12).path.endswith("msyhbd.ttc")     # one wide character is enough
    assert ring._font_for("Latin only", 12).path.endswith("segoeuib.ttf")


@needs_fonts
def test_cjk_text_falls_back_to_the_next_font_and_then_to_segoe(tmp_path, monkeypatch):
    shutil.copy(SEGOE, tmp_path / "malgunbd.ttf")
    monkeypatch.setattr(ring, "_fonts_dir", lambda: str(tmp_path))
    assert ring._font_for("中文", 12).path.endswith("malgunbd.ttf")        # no YaHei or Yu Gothic here
    other = tmp_path / "other"                              # (loaded fonts are cached by path, so a new folder)
    other.mkdir()
    shutil.copy(SEGOE, other / "segoeuib.ttf")
    monkeypatch.setattr(ring, "_fonts_dir", lambda: str(other))
    assert ring._font_for("中文", 12).path.endswith("segoeuib.ttf")


def test_no_fonts_at_all_still_gives_a_font(tmp_path, monkeypatch):
    monkeypatch.setattr(ring, "_fonts_dir", lambda: str(tmp_path))
    assert ring._font_for("中文", 12) is not None
    assert ring._font_for("abc", 12) is not None


@needs_fonts
def test_loaded_fonts_are_cached_by_file_and_size():
    assert ring._font_for("abc", 13) is ring._font_for("def", 13)
    assert ring._font_for("abc", 13) is not ring._font_for("abc", 14)


@needs_fonts
def test_a_cjk_label_renders_with_ink():
    r = make_ring(make_menu(labels=["中文笔刷", "ブラシ", "브러시", "x"]))
    r._geometry(1.0)
    r._prepare()
    for lab in r.labels[:3]:
        assert lab[0].getchannel("A").getbbox() is not None


# --- label pills -------------------------------------------------------------------------------
def test_a_label_sits_on_a_soft_dark_pill():
    r = make_ring()
    r._geometry(1.0)
    r._prepare()
    for idle_or_hover in r.labels[0]:
        w, h = idle_or_hover.size
        a = idle_or_hover.getchannel("A")
        assert a.getpixel((0, 0)) == 0                       # the corner is outside the rounded pill
        assert 100 <= a.getpixel((3, h // 2)) <= 160         # left of the text, on the pill: about 55 percent
        assert 100 <= a.getpixel((w - 4, h // 2)) <= 160
        assert a.getpixel((w // 2, 0)) == 0                  # the sprite keeps a margin above the pill


def test_a_label_pill_is_bright_under_the_light_theme():
    r = prepared(make_menu(), theme="light", colors=theme.ring_colors("light"))
    for sprite in r.labels[0]:
        h = sprite.size[1]
        red, green, blue, alpha = sprite.getpixel((3, h // 2))        # left of the text, on the pill
        assert min(red, green, blue) > 240 and 180 <= alpha <= 230


def test_the_hint_is_dark_under_the_light_theme_and_pale_under_the_dark():
    for name, dark in (("light", True), ("dark", False)):
        r = prepared(make_menu(), theme=name, colors=theme.ring_colors(name))
        draw = ring.ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        hints = [c for *_, c in r._caption(draw)[1:]]
        assert hints and all((sum(c[:3]) < 200) == dark for c in hints)


def test_every_label_has_the_same_pill_height():
    r = make_ring(make_menu(labels=["Pyg", "Tools", "x"]))
    r._geometry(1.0)
    r._prepare()
    assert len({lab[0].size[1] for lab in r.labels}) == 1


def test_no_labels_means_no_label_sprites():
    r = make_ring(labels="none")
    r._geometry(1.0)
    r._prepare()
    assert r.labels == [None] * 4


def test_a_long_label_is_shortened():
    r = make_ring(make_menu(labels=["A very long brush name that cannot fit", "b", "c", "d"]))
    r._geometry(1.0)
    r._prepare()
    assert r.labels[0][0].size[0] <= r.slot * 1.9 + 24


# --- draw order --------------------------------------------------------------------------------
def test_every_disc_is_drawn_before_any_label(monkeypatch):
    r = make_ring(make_menu(8))
    r._geometry(1.0)
    r._relayout()
    r._prepare()
    r.t0 = 0.0
    calls = []
    monkeypatch.setattr(r, "_draw_disc", lambda *a, **k: calls.append("disc"))
    monkeypatch.setattr(r, "_draw_label", lambda *a, **k: calls.append("label"))
    r._compose(10.0)
    assert calls == ["disc"] * 8 + ["label"] * 8


# --- title and hint ----------------------------------------------------------------------------
def test_hint_wording_follows_the_state():
    r = make_ring()
    r._armed, r.mode = False, "hold"
    assert r._hint_lines() == [("move into the ring",)]
    r._armed = True
    assert r._hint_lines()[0] == ("release or flick to pick",)
    r.cfg["flick"] = False
    assert r._hint_lines() == [("release to pick",)]
    r.mode = "click"
    assert r._hint_lines()[0] == ("click a slot, centre or right-click cancels",)


def test_the_smallest_ring_draws_without_text_across_its_slots():
    r = make_ring(make_menu(6, title="A rather long menu title"), radius=60, slot=32)
    r._geometry(1.0)
    r._relayout()
    r._prepare()
    draw = ring.ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    free = (r.R - r.slot * 0.62 - 4) * ring.SS
    for text, font, dy, _ in r._caption(draw):
        box = draw.textbbox((0, 0), text, font=font)
        half = (box[2] - box[0]) / 2
        assert math.hypot(half, dy * ring.SS) <= free + 1, text
    assert r._static().size == (r.rsize, r.rsize)


def test_a_long_title_is_cut_short_in_a_small_ring():
    r = make_ring(make_menu(4, title="A rather long menu title"), radius=60, slot=32)
    r._geometry(1.0)
    r._prepare()
    draw = ring.ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    assert r._caption(draw)[0][0].endswith("…")


def test_a_short_title_is_left_alone():
    r = make_ring(make_menu(4, title="Tools"))
    r._geometry(1.0)
    r._prepare()
    draw = ring.ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    assert r._caption(draw)[0][0] == "T O O L S"


# --- sprite cache ------------------------------------------------------------------------------
def prepared(menu, icon_for=None, log=None, **over):
    r = make_ring(menu, icon_for, log, **over)
    r._geometry(1.0)
    r._prepare()
    return r


def test_the_same_menu_reuses_its_sprites_and_says_so():
    logs = []
    menu = make_menu(5)
    a = prepared(menu, log=logs.append)
    b = prepared(menu, log=logs.append)
    assert b.sprites[0] is a.sprites[0] and b.labels[3] is a.labels[3] and b._dot is a._dot
    assert "built in" in logs[0] and "from cache" in logs[1]
    assert all("ring 'm' sprites" in line for line in logs)


def test_a_new_label_gives_new_sprites():
    a = prepared(make_menu(labels=["a", "b", "c", "d"]))
    b = prepared(make_menu(labels=["a", "b", "c", "e"]))
    assert b.sprites[3] is not a.sprites[3]
    assert b.labels[3] is not a.labels[3]


@pytest.mark.parametrize("over", [{"slot": 60}, {"labels": "none"}, {"tag_colors": "none"},
                                  {"colors": dict(config.DEFAULT_RING["colors"], accent="#112233")},
                                  {"theme": "light", "colors": theme.ring_colors("light")}])
def test_settings_that_reach_a_sprite_give_new_sprites(over):
    menu = make_menu()
    a = prepared(menu)
    b = prepared(menu, **over)
    assert b.sprites[0] is not a.sprites[0]


def test_settings_that_do_not_reach_a_sprite_keep_them():
    menu = make_menu()
    a = prepared(menu)
    b = prepared(menu, radius=200, tap_ms=100, animation="pop")
    assert b.sprites[0] is a.sprites[0]


def test_the_scale_is_part_of_the_key():
    menu = make_menu()
    a = make_ring(menu)
    a._geometry(1.0)
    a._prepare()
    b = make_ring(menu)
    b._geometry(2.0)
    b._prepare()
    assert b.sprites[0] is not a.sprites[0]
    assert b.sprites[0][0].size[0] > a.sprites[0][0].size[0]


def test_an_icon_that_turns_up_later_gives_new_sprites():
    menu = make_menu()
    icons = {}
    a = prepared(menu, icon_for=lambda it: icons.get(it.label))
    icons["Item 0"] = Image.new("RGBA", (64, 64), (200, 30, 30, 255))
    b = prepared(menu, icon_for=lambda it: icons.get(it.label))
    assert b.sprites[0] is not a.sprites[0]
    c = prepared(menu, icon_for=lambda it: Image.new("RGBA", (64, 64), (200, 30, 30, 255)) if it.label == "Item 0"
                 else None)
    assert c.sprites[0] is b.sprites[0]                      # equal pixels in another object: same key


def test_a_changed_icon_gives_new_sprites():
    menu = make_menu()
    a = prepared(menu, icon_for=lambda it: Image.new("RGBA", (64, 64), (1, 2, 3, 255)))
    b = prepared(menu, icon_for=lambda it: Image.new("RGBA", (64, 64), (1, 2, 4, 255)))
    assert b.sprites[0] is not a.sprites[0]


def test_icon_for_is_asked_once_per_item_on_a_miss():
    calls = []
    menu = make_menu(3)
    prepared(menu, icon_for=lambda it: calls.append(it.label))
    assert sorted(calls) == ["Item 0", "Item 1", "Item 2"]


def test_a_failing_icon_is_no_icon():
    def boom(it):
        raise RuntimeError("no icon")
    r = prepared(make_menu(), icon_for=boom)
    assert r.sprites[0][0].size[0] > 0


def test_only_the_eight_latest_menus_are_kept():
    for i in range(10):
        prepared(make_menu(2, mid=f"menu{i}"))
    assert len(ring._sprite_cache) == ring.SPRITE_MENUS == 8
    assert {k[0] for k in ring._sprite_cache} == {f"menu{i}" for i in range(2, 10)}


def test_a_menu_used_again_stays_longest():
    first = make_menu(2, mid="first")
    prepared(first)
    for i in range(7):
        prepared(make_menu(2, mid=f"m{i}"))
    prepared(first)                                          # now the most recent
    prepared(make_menu(2, mid="newest"))
    assert "first" in {k[0] for k in ring._sprite_cache}


# --- a whole render ----------------------------------------------------------------------------
def test_preview_renders_a_ring_and_a_hovered_ring():
    menu = make_menu(11, title="Tools")
    cfg = make_cfg()
    plain = ring.Ring.preview(menu, cfg, lambda it: None)
    hot = ring.Ring.preview(menu, cfg, lambda it: None, hover=2)
    assert plain.mode == "RGBA" and plain.size == hot.size
    assert plain.getchannel("A").getbbox() is not None
    assert plain.tobytes() != hot.tobytes()
    assert plain.info["centre"] == (plain.size[0] // 2, plain.size[1] // 2)


def test_preview_says_where_the_hovered_slot_is_and_can_draw_the_hold_hint():
    menu, cfg = make_menu(8), make_cfg()
    hot = ring.Ring.preview(menu, cfg, lambda it: None, hover=0)
    (cx, cy), (hx, hy) = hot.info["centre"], hot.info["hover_at"]
    assert hx == cx and hy < cy                              # slot 0 is straight above the centre
    assert "hover_at" not in ring.Ring.preview(menu, cfg, lambda it: None).info
    assert ring.Ring.preview(menu, cfg, lambda it: None, hover=(0,)).tobytes() == hot.tobytes()
    held = ring.Ring.preview(menu, cfg, lambda it: None, hover=0, held=True)
    assert held.size == hot.size and held.tobytes() != hot.tobytes()   # the hint under the title differs


def test_the_dot_grows_with_the_hub_setting_and_is_part_of_the_sprite_key():
    small, big = prepared(make_menu(4), hub=10), prepared(make_menu(4), hub=30)
    assert big._dot.size[0] > small._dot.size[0]
    assert small._dot.size[0] == int((10 + 2 * 14) * ring.SS) // ring.SS   # the default look is unchanged
    assert big._dot is not small._dot                                       # not served from the hub 10 entry


def test_no_hub_means_no_dot_and_the_ring_still_renders():
    menu = make_menu(6, title="Tools")
    r = prepared(menu, hub=0)
    assert r._dot is None
    assert ring.Ring.preview_frames(menu, make_cfg(hub=0, animation="pop"), lambda it: None, fps=20)
    flat = ring.Ring.preview(menu, make_cfg(hub=0), lambda it: None)
    dotted = ring.Ring.preview(menu, make_cfg(), lambda it: None)
    cx, cy = flat.info["centre"]
    assert flat.getpixel((cx, cy))[3] < dotted.getpixel((cx, cy))[3]     # nothing drawn where the dot sits


def test_a_big_dot_pushes_the_title_down_to_keep_its_gap():
    draw = ring.ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    dys = []
    for hub in (10, 40):
        r = prepared(make_menu(4, title="Tools"), hub=hub)
        dys.append(r._caption(draw)[0][2])
    assert dys == [18, 18 + 15]


def test_a_rounded_slot_is_hit_on_its_corner_where_a_circle_is_not():
    how = {}
    for shape in ("circle", "rounded"):
        r = prepared(make_menu(4), slot_shape=shape)
        r.centre = (0, 0)
        cx, cy = r.seats[1][0] * r.R, r.seats[1][1] * r.R    # the slot on the right of the ring
        assert r._hit(cx, cy) == ((1,), "disc")
        assert r._hit(cx + r.slot * 0.55, cy)[1] != "disc"   # past the edge either way
        how[shape] = r._hit(cx + r.slot * 0.45, cy + r.slot * 0.45)[1]   # inside the square, outside its circle
    assert how == {"circle": "sector", "rounded": "disc"}


def test_rounded_slots_render_and_change_the_sprite_key():
    menu = make_menu(5)
    a, b = prepared(menu), prepared(menu, slot_shape="rounded")
    assert a._sprite_key() != b._sprite_key()
    assert a.sprites[0] is not b.sprites[0] and a.sprites[0][0].tobytes() != b.sprites[0][0].tobytes()
    shaped = ring.Ring.preview(menu, make_cfg(slot_shape="rounded"), lambda it: None)
    assert shaped.size == ring.Ring.preview(menu, make_cfg(), lambda it: None).size


def _hover_edge(r, i=0):
    """The hover sprite of slot i and a pixel just outside its disc, where the glow is."""
    sprite = r.sprites[i][1]
    n = sprite.size[0]
    return sprite.getpixel((n // 2 + int(r.slot * 1.12 / 2 + 4 * r.scale), n // 2))


def test_a_glow_colour_changes_the_sprite_key_and_the_hover_glow():
    plain, blue = make_menu(3), make_menu(3)
    blue.items[0] = dataclasses.replace(blue.items[0], glow="#0000ff")
    a, b = prepared(plain), prepared(blue)
    assert a._sprite_key() != b._sprite_key()
    ar, ag, ab, aa = _hover_edge(a)
    br, bg, bb, ba = _hover_edge(b)
    assert ar > ab and bb > br and ba > 0          # the accent is orange; the glow colour is blue
    assert b.sprites[1][1].tobytes() == a.sprites[1][1].tobytes()      # the next slot is untouched


def test_a_glow_colour_beats_the_tag_colour_for_the_glow_only():
    tagged = make_menu(3)
    tagged.items[0] = dataclasses.replace(tagged.items[0], color="#ff0000")
    both = make_menu(3)
    both.items[0] = dataclasses.replace(both.items[0], color="#ff0000", glow="#0000ff")
    t, g = prepared(tagged), prepared(both)
    tr, _, tb, _ = _hover_edge(t)
    gr, _, gb, _ = _hover_edge(g)
    assert tr > tb and gb > gr
    assert g.sprites[0][0].tobytes() == t.sprites[0][0].tobytes()      # idle (tint mode): fill and rim unchanged


def test_a_glow_colour_shows_the_idle_halo_without_a_tag():
    plain, blue = make_menu(3), make_menu(3)
    blue.items[0] = dataclasses.replace(blue.items[0], glow="#0000ff")
    a, b = prepared(plain, tag_colors="glow"), prepared(blue, tag_colors="glow")
    assert b.sprites[0][0].tobytes() != a.sprites[0][0].tobytes()
    assert b.sprites[1][0].tobytes() == a.sprites[1][0].tobytes()      # no glow field, no halo, as before
    n = b.sprites[0][0].size[0]
    assert b.sprites[0][0].getpixel((n // 2 + int(b.slot / 2 + 6 * b.scale), n // 2))[3] > 0
    off = prepared(blue, tag_colors="tint")                            # the halo follows the Glow switch
    assert off.sprites[0][0].tobytes() == prepared(plain, tag_colors="tint").sprites[0][0].tobytes()


def test_preview_window_grows_with_the_item_count():
    cfg = make_cfg()
    small = ring.Ring.preview(make_menu(6), cfg, lambda it: None)
    large = ring.Ring.preview(make_menu(24), cfg, lambda it: None)
    assert large.size[0] > small.size[0]


def test_preview_frames_run_through_the_open_animation():
    frames = ring.Ring.preview_frames(make_menu(6), make_cfg(animation="pop"), lambda it: None, fps=20)
    assert len(frames) > 2 and all(f.mode == "RGBA" for f in frames)


def test_default_font_is_a_fallback_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(ring, "_fonts_dir", lambda: str(tmp_path))
    im = ring.Ring.preview(make_menu(5, labels=["中文", "a", "b", "c", "d"]), make_cfg(), lambda it: None)
    assert im.getchannel("A").getbbox() is not None
    assert isinstance(ring._font(12), (ImageFont.FreeTypeFont, ImageFont.ImageFont))


# --- shapes ------------------------------------------------------------------------------------
ALL_SHAPES = ("circle", "rounded", "squircle", "hexagon", "octagon", "diamond")


def styled(item, **extra):
    """A copy of a config.Item with extra attributes (style, glow ...): the ring only reads attributes, so this works
    whatever fields config.Item has."""
    ns = SimpleNamespace(**{f.name: getattr(item, f.name) for f in dataclasses.fields(item)})
    for k, v in extra.items():
        setattr(ns, k, v)
    return ns


def menu_with(n=3, **extra):
    """A menu whose first slot has the extra attributes."""
    m = make_menu(n)
    m.items[0] = styled(m.items[0], **extra)
    return m


def test_shapes_lists_the_six_and_ring_still_exports_the_corner():
    assert shapes.SHAPES == ALL_SHAPES
    assert ring.SLOT_CORNER == shapes.SLOT_CORNER == 0.28


def test_inside_circle_and_rounded_match_the_old_hit_tests():
    r = 36
    assert shapes.inside("circle", 25, 25, r) and not shapes.inside("circle", 26, 26, r)       # hypot <= r
    assert shapes.inside("rounded", 36, 36, r) and not shapes.inside("rounded", 36.5, 0, r)    # the whole box


def test_inside_squircle_is_between_a_circle_and_a_box():
    r = 36
    assert shapes.inside("squircle", 35, 0, r) and not shapes.inside("squircle", 37, 0, r)
    assert shapes.inside("squircle", 30, 30, r) and not shapes.inside("squircle", 31, 31, r)   # 0.84 r on the diagonal


def test_inside_hexagon_is_pointy_top_and_rejects_the_box_corner():
    r = 36
    assert shapes.inside("hexagon", 0, 35, r) and not shapes.inside("hexagon", 0, 37, r)       # points up and down
    assert shapes.inside("hexagon", 31, 0, r) and not shapes.inside("hexagon", 32, 0, r)       # flat sides at 0.866 r
    assert shapes.inside("hexagon", 31, 17, r) and not shapes.inside("hexagon", 31, 19, r)     # the slanted edge
    assert not shapes.inside("hexagon", 28, 28, r)                                             # a box corner


def test_inside_octagon_is_flat_top_with_cut_corners():
    r = 36
    assert shapes.inside("octagon", 36, 10, r) and not shapes.inside("octagon", 37, 0, r)
    assert shapes.inside("octagon", 25, 25, r) and not shapes.inside("octagon", 26, 26, r)     # corner cut at 1.414 r


def test_inside_diamond_reaches_past_r_on_the_axes_only():
    r = 36
    assert shapes.inside("diamond", 41, 0, r) and not shapes.inside("diamond", 42, 0, r)
    assert shapes.inside("diamond", 20, 20, r) and not shapes.inside("diamond", 21, 21, r)
    assert not shapes.inside("diamond", 36, 36, r)


def test_an_unknown_shape_is_a_circle():
    assert shapes.inside("blob", 25, 25, 36) and not shapes.inside("blob", 26, 26, 36)


def test_circle_and_rounded_draw_with_the_pillow_calls_the_ring_always_made():
    for shape in ("circle", "rounded"):
        a, b = Image.new("RGBA", (200, 200)), Image.new("RGBA", (200, 200))
        shapes.draw(ImageDraw.Draw(a), shape, 100.0, 100.0, 60.0, 0.28, grow=7.5, fill=(10, 20, 30, 200),
                    outline=(200, 100, 50, 255), width=5)
        box = (100.0 - 67.5, 100.0 - 67.5, 100.0 + 67.5, 100.0 + 67.5)
        d = ImageDraw.Draw(b)
        if shape == "circle":
            d.ellipse(box, fill=(10, 20, 30, 200), outline=(200, 100, 50, 255), width=5)
        else:
            d.rounded_rectangle(box, radius=(box[2] - box[0]) * 0.28, fill=(10, 20, 30, 200),
                                outline=(200, 100, 50, 255), width=5)
        assert a.tobytes() == b.tobytes()


def test_the_icon_mask_of_a_circle_and_a_rounded_square_is_what_the_ring_always_used():
    for shape in ("circle", "rounded"):
        want = Image.new("L", (80, 80), 0)
        d = ImageDraw.Draw(want)
        if shape == "circle":
            d.ellipse((0, 0, 79, 79), fill=255)
        else:
            d.rounded_rectangle((0, 0, 79, 79), radius=79 * 0.28, fill=255)
        assert shapes.icon_mask(shape, 80).tobytes() == want.tobytes()


@pytest.mark.parametrize("shape", ALL_SHAPES)
def test_every_shape_draws_a_rim_around_a_fill_and_masks_an_icon(shape):
    im = Image.new("RGBA", (200, 200))
    shapes.draw(ImageDraw.Draw(im), shape, 100, 100, 60, 0.28, fill=(0, 0, 255, 255), outline=(255, 0, 0, 255),
                width=6)
    assert im.getpixel((100, 100)) == (0, 0, 255, 255) and im.getpixel((2, 2)) == (0, 0, 0, 0)
    assert any(im.getpixel((x, 100)) == (255, 0, 0, 255) for x in range(100, 180))      # a rim between fill and edge
    mask = shapes.icon_mask(shape, 80)
    assert mask.size == (80, 80) and mask.getpixel((40, 40)) == 255 and mask.getbbox() is not None
    assert shapes.inside(shape, 0, 0, 1) and shapes.pad_extra(shape, 200) >= 0 and 0.4 < shapes.badge(shape) < 0.8


def test_the_rim_is_even_on_a_polygon_and_zero_width_means_no_rim():
    im = Image.new("RGBA", (200, 200))
    shapes.draw(ImageDraw.Draw(im), "hexagon", 100, 100, 60, fill=(0, 0, 255, 255), outline=(255, 0, 0, 255), width=8)
    top = [y for y in range(0, 100) if im.getpixel((100, y)) == (255, 0, 0, 255)]
    side = [x for x in range(100, 200) if im.getpixel((x, 100)) == (255, 0, 0, 255)]
    assert 6 <= len(top) <= 10 and 6 <= len(side) <= 10
    flat = Image.new("RGBA", (200, 200))
    shapes.draw(ImageDraw.Draw(flat), "hexagon", 100, 100, 60, fill=(0, 0, 255, 255), outline=(255, 0, 0, 255),
                width=0)
    assert (255, 0, 0, 255) not in {flat.getpixel((100, y)) for y in range(200)}
    assert flat.getpixel((100, 100)) == (0, 0, 255, 255)


def test_a_grown_polygon_is_bigger_by_the_same_distance_on_each_edge():
    plain, grown = Image.new("RGBA", (300, 300)), Image.new("RGBA", (300, 300))
    for im, g in ((plain, 0), (grown, 12)):
        shapes.draw(ImageDraw.Draw(im), "octagon", 150, 150, 60, grow=g, fill=(255, 255, 255, 255))
    pb, gb = plain.getchannel("A").getbbox(), grown.getchannel("A").getbbox()
    assert abs((gb[3] - gb[1]) - (pb[3] - pb[1]) - 24) <= 2 and abs((gb[2] - gb[0]) - (pb[2] - pb[0]) - 24) <= 2


def test_only_a_diamond_needs_extra_canvas():
    assert [shapes.pad_extra(s, 240) for s in ALL_SHAPES] == [0.0, 0.0, 0.0, 0.0, 0.0, pytest.approx(18.0)]


def test_every_shape_renders_a_distinct_sprite_and_a_whole_ring():
    menu = make_menu(5)
    seen = {}
    for shape in ALL_SHAPES:
        r = prepared(menu, slot_shape=shape)
        idle, hover = r.sprites[0]
        assert idle.getchannel("A").getbbox() is not None and hover.getchannel("A").getbbox() is not None
        seen[shape] = idle.tobytes()
        assert ring.Ring.preview(menu, make_cfg(slot_shape=shape), lambda it: None, hover=1).size[0] > 0
    assert len(set(seen.values())) == 6


def test_a_diamond_sprite_has_room_for_its_tips_and_the_others_keep_the_circle_size():
    sizes = {shape: prepared(make_menu(4), slot_shape=shape).sprites[0][0].size[0] for shape in ALL_SHAPES}
    assert len({sizes[s] for s in ALL_SHAPES if s != "diamond"}) == 1 and sizes["diamond"] > sizes["circle"]


@pytest.mark.parametrize("shape,hit", [("circle", True), ("rounded", True), ("squircle", True), ("hexagon", False),
                                       ("octagon", True), ("diamond", False)])
def test_a_slot_is_hit_where_its_shape_is(shape, hit):
    r = prepared(make_menu(4), slot_shape=shape)
    r.centre = (0, 0)
    cx, cy = r.seats[1][0] * r.R, r.seats[1][1] * r.R
    assert r._hit(cx, cy) == ((1,), "disc")
    off = r.slot * 0.35                                       # on the box's diagonal, out towards its corner
    assert (r._hit(cx + off, cy + off)[1] == "disc") == hit


def test_a_slot_with_its_own_shape_is_hit_in_that_shape():
    menu = menu_with(4, style={"slot_shape": "diamond"})
    r = prepared(menu)
    r.centre = (0, 0)
    ux, uy = r.seats[0]
    top = (ux * r.R, uy * r.R)
    assert r._hit(top[0] + r.slot * 0.55, top[1])[1] == "disc"      # a diamond's tip reaches past a circle's edge
    assert r._hit(top[0] + r.slot * 0.4, top[1] + r.slot * 0.4)[1] != "disc"


# --- per-slot style ----------------------------------------------------------------------------
def slot_px(r, i=0, hover=False, dx=0, dy=0):
    sprite = r.sprites[i][1 if hover else 0]
    n = sprite.size[0]
    return sprite.getpixel((n // 2 + dx, n // 2 + dy))


def _rgb_of(hexcol):
    return tuple(int(hexcol.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))


def test_a_slot_style_leaves_its_neighbours_byte_equal():
    base = prepared(make_menu(4))
    st = prepared(menu_with(4, style={"slot_shape": "hexagon", "fill_color": "#ff0000", "border_color": "#00ff00",
                                      "border_width": 5, "icon_scale": 0.6, "label_color": "#0000ff",
                                      "glow_color": "#ffff00"}))
    assert st.sprites[0][0].tobytes() != base.sprites[0][0].tobytes()
    assert st.sprites[0][1].tobytes() != base.sprites[0][1].tobytes()
    for i in (1, 2, 3):
        assert st.sprites[i][0].tobytes() == base.sprites[i][0].tobytes()
        assert st.sprites[i][1].tobytes() == base.sprites[i][1].tobytes()
        assert st.labels[i][0].tobytes() == base.labels[i][0].tobytes()


def test_a_slot_style_is_part_of_the_sprite_key():
    a, b = prepared(make_menu(3)), prepared(menu_with(3, style={"border_width": 4}))
    assert a._sprite_key() != b._sprite_key()
    c = prepared(menu_with(3, style={"border_width": 5}))
    assert b._sprite_key() != c._sprite_key()
    same = prepared(menu_with(3, style={"border_width": 5}))
    assert same._sprite_key() == c._sprite_key()


def test_a_slot_fill_colour_replaces_the_theme_background():
    base, red = prepared(make_menu(3)), prepared(menu_with(3, style={"fill_color": "#ff0000"}))
    r, g, b, a = slot_px(red, 0, dx=33)            # inside the disc, outside the placeholder gradient
    br, bg, bb, ba = slot_px(base, 0, dx=33)
    assert r > br + 30 and a > 0


def test_a_slot_fill_colour_can_name_a_theme_role():
    by_role = prepared(menu_with(3, style={"fill_color": "accent"}))
    by_hex = prepared(menu_with(3, style={"fill_color": config.DEFAULT_RING["colors"]["accent"]}))
    assert by_role.sprites[0][0].tobytes() == by_hex.sprites[0][0].tobytes()


def test_a_slot_border_colour_and_width_set_the_idle_rim():
    r = prepared(menu_with(3, style={"border_color": "#00ff00", "border_width": 6}))
    n = r.sprites[0][0].size[0]
    px = r.sprites[0][0].getpixel((n // 2 + int(r.slot * 1.12 / 2) - 3, n // 2))      # the middle of the 6 px rim
    assert px[1] > 150 and px[0] < 100 and px[3] > 200


def test_border_width_zero_draws_no_rim_and_the_hover_keeps_one():
    plain, flat = prepared(make_menu(3)), prepared(menu_with(3, style={"border_width": 0}))
    assert flat.sprites[0][0].tobytes() != plain.sprites[0][0].tobytes()
    assert flat.sprites[0][1].tobytes() == plain.sprites[0][1].tobytes()       # the hover rim is at least 2 px


def test_the_global_border_width_changes_the_rim_and_2_is_todays():
    thin, thick = prepared(make_menu(3), border_width=1), prepared(make_menu(3), border_width=6)
    assert thin.sprites[0][0].tobytes() != thick.sprites[0][0].tobytes()
    assert prepared(make_menu(3), border_width=2).sprites[0][0].tobytes() == prepared(make_menu(3)).sprites[0][0].tobytes()


def test_a_tinted_idle_rim_is_a_step_wider_than_the_base_rim():
    def tagged(**over):
        m = make_menu(3)
        m.items[0] = dataclasses.replace(m.items[0], color="#ff0000", tag="t")
        return prepared(m, **over)
    assert tagged(border_width=3).sprites[0][0].tobytes() != tagged().sprites[0][0].tobytes()
    assert tagged(border_width=0).sprites[0][0].tobytes() != tagged().sprites[0][0].tobytes()   # 0: no rim, tinted or not


def test_icon_scale_shrinks_the_icon_inside_its_slot():
    def icon(it):
        return Image.new("RGBA", (64, 64), (255, 255, 255, 255)) if it.label == "Item 0" else None
    full, half = prepared(make_menu(3), icon), prepared(menu_with(3, style={"icon_scale": 0.5}), icon)
    near = int(full.slot * 0.4)
    assert min(slot_px(full, 0, dx=near)[:3]) > 250      # the full icon reaches 0.4 slot widths out
    assert min(slot_px(half, 0, dx=near)[:3]) < 250
    assert min(slot_px(half, 0)[:3]) > 250
    assert prepared(make_menu(3), icon, icon_scale=0.5).sprites[0][0].tobytes() == half.sprites[0][0].tobytes()


def _pixels(im):
    raw = im.tobytes()
    return zip(raw[0::4], raw[1::4], raw[2::4], raw[3::4])


def _ink(sprite):
    """Mean colour of a label's solid pixels (the text; the pill is see-through)."""
    px = [p for p in _pixels(sprite) if p[3] >= 200]
    return tuple(sum(p[k] for p in px) / len(px) for k in range(3)) if px else None


def test_a_slot_label_colour_wins_over_the_look_over_the_theme_text():
    text = _rgb_of(config.DEFAULT_RING["colors"]["text"])
    a = prepared(make_menu(3))
    b = prepared(make_menu(3), label_color="#ff0000")
    c = prepared(menu_with(3, style={"label_color": "#00ff00"}), label_color="#ff0000")
    assert max(abs(x - y) for x, y in zip(_ink(a.labels[0][0]), text)) < 40
    ar, ag, ab = _ink(b.labels[0][0])
    assert ar > 200 and ag < 60 and ab < 60
    cr, cg, cb = _ink(c.labels[0][0])
    assert cg > 200 and cr < 60 and cb < 60
    assert c.labels[1][0].tobytes() == b.labels[1][0].tobytes()            # the other slots follow the look
    assert a.labels[0][1].tobytes() == c.labels[0][1].tobytes()            # the hover name keeps its accent


def test_a_look_label_colour_can_be_a_theme_role():
    a = prepared(make_menu(2), label_color="accent")
    r, g, b = _ink(a.labels[0][0])
    assert r > 200 and b < 120


def test_a_slot_glow_colour_colours_the_hover_glow_and_beats_the_legacy_glow():
    both = prepared(menu_with(3, glow="#0000ff", style={"glow_color": "#00ff00"}))
    gr, gg, gb, ga = _hover_edge(both)
    assert gg > gr and gg > gb and ga > 0                      # green: the style wins over the old glow field
    legacy = prepared(menu_with(3, glow="#0000ff"))
    lr, lg, lb, la = _hover_edge(legacy)
    assert lb > lr and lb > lg                                  # blue: the old glow field still works
    role = prepared(menu_with(3, style={"glow_color": "highlight"}))
    assert _hover_edge(role)[:3] != _hover_edge(prepared(make_menu(3)))[:3]


def test_a_style_glow_colour_shows_the_idle_halo_and_a_look_glow_colour_alone_does_not():
    plain = prepared(make_menu(3), tag_colors="glow")
    styled_ = prepared(menu_with(3, style={"glow_color": "#0000ff"}), tag_colors="glow")
    assert styled_.sprites[0][0].tobytes() != plain.sprites[0][0].tobytes()
    blue = prepared(make_menu(3), tag_colors="glow", glow_color="#0000ff")
    r, g, b, a = _hover_edge(blue)
    assert b > r and a > 0                                             # the hover glow takes the look's colour
    assert blue.sprites[0][0].tobytes() == plain.sprites[0][0].tobytes()      # but no halo from it alone


def test_the_glow_opacity_scales_the_hover_glow():
    low, mid, high = (prepared(make_menu(3), glow_opacity=v) for v in (0.2, 0.55, 1.0))
    assert _hover_edge(low)[3] < _hover_edge(mid)[3] < _hover_edge(high)[3]
    assert mid.sprites[0][1].tobytes() == prepared(make_menu(3)).sprites[0][1].tobytes()   # 0.55 is today's look
    assert prepared(make_menu(3), glow_opacity=0.0).sprites[0][1].tobytes() != mid.sprites[0][1].tobytes()


def test_a_tag_slot_takes_the_base_fill_of_its_style():
    plain = menu_with(3, color="#ff0000", tag="t")
    white = menu_with(3, color="#ff0000", tag="t", style={"fill_color": "#ffffff"})
    assert prepared(white).sprites[0][0].tobytes() != prepared(plain).sprites[0][0].tobytes()


# --- a menu's own look -------------------------------------------------------------------------
def test_a_menu_look_overrides_colours_and_geometry_but_not_behaviour():
    menu = make_menu(4)
    menu.look = {"radius": 200, "slot": 60, "hub": 20, "colors": {"accent": "#00ff00"}, "flick": False, "tap_ms": 1}
    r = prepared(menu)
    assert r.R == 200 and r.slot == 60 and r.look.hub == 20 and r.look.accent == "#00ff00"
    assert r.cfg["flick"] is True and r.cfg["tap_ms"] == 250 and r.cfg["radius"] == 145     # behaviour stays global
    assert r.look.bg == config.DEFAULT_RING["colors"]["bg"]                                    # colours merge per key


def test_a_menu_look_changes_the_sprites_and_a_plain_menu_is_unchanged():
    a = prepared(make_menu(4))
    menu = make_menu(4)
    menu.look = {"slot_shape": "hexagon"}
    b = prepared(menu)
    assert a.sprites[0][0].tobytes() != b.sprites[0][0].tobytes() and a._sprite_key() != b._sprite_key()
    assert prepared(make_menu(4)).sprites[0][0].tobytes() == a.sprites[0][0].tobytes()


def test_no_look_and_an_empty_look_are_the_same_ring():
    menu = make_menu(4)
    menu.look = {}
    assert prepared(menu).sprites[0][0].tobytes() == prepared(make_menu(4)).sprites[0][0].tobytes()
    menu.look = None
    assert prepared(menu).look.slot_shape == "circle"


def test_a_look_is_read_only_and_ignores_nonsense():
    r = prepared(make_menu(2), slot_shape="blob", hub_style="swirl", border_width="wide", icon_scale=7)
    assert r.look.slot_shape == "circle" and r.look.hub_style == "dot"
    assert r.look.border_width == 2 and r.look.icon_scale == 1.0
    with pytest.raises(AttributeError):
        r.look.slot = 5


def test_roles_resolve_against_the_theme_and_hex_passes_through():
    col = {"bg": "#111111", "accent": "#222222", "highlight": "#333333", "text": "#444444", "lines": "#555555"}
    assert [ring._role(v, col) for v in ("bg", "accent", "highlight", "text", "lines")] == [
        "#111111", "#222222", "#333333", "#444444", "#555555"]
    assert ring._role("#abcdef", col) == "#abcdef" and ring._role("", col) == "" and ring._role(None, col) == ""
    assert ring._role("lines", {"accent": "#222222"}) == "#222222"      # lines falls back to the accent


def test_a_look_names_its_colour_roles_for_the_hub_and_the_labels():
    r = prepared(make_menu(2), hub_color="highlight", label_color="accent", glow_color="highlight")
    col = r.cfg["colors"]
    assert (r.look.hub_color, r.look.label_color, r.look.glow_color) == (col["highlight"], col["accent"],
                                                                         col["highlight"])
    plain = prepared(make_menu(2))
    assert plain.look.hub_color == col["accent"] and plain.look.glow_color == "" and plain.look.label_color == col["text"]


# --- fans with a look of their own -------------------------------------------------------------
def fan_ring(fan_look=None, ring_look=None):
    sub = SimpleNamespace(id="s", title="Sub", animation="", fan=True,
                          items=[config.Item(f"S{i}", "brush", {"brush": f"S{i}"}) for i in range(3)])
    if fan_look is not None:
        sub.look = fan_look
    menu = make_menu(4)
    menu.items[1] = config.Item("Sub", "menu", {"menu": "s"})
    if ring_look is not None:
        menu.look = ring_look
    r = ring.Ring(menu, make_cfg(), lambda it: None, lambda *a: None, lambda m: None, held=False,
                  submenus=lambda mid: sub if mid == "s" else None)
    r._geometry(1.0)
    r._relayout()
    r._prepare()
    return r, r._fan((1,))


def test_a_fan_without_a_look_takes_the_rings():
    r, fan = fan_ring()
    assert fan.look is r.look
    r2, fan2 = fan_ring(ring_look={"slot_shape": "diamond"})
    assert fan2.look is r2.look and fan2.look.slot_shape == "diamond"


def test_a_fan_with_its_own_look_is_drawn_in_it_and_the_ring_is_not():
    r, plain = fan_ring()
    r2, fan = fan_ring(fan_look={"slot_shape": "hexagon", "colors": {"accent": "#00ff00"}})
    assert fan.look is not r2.look and fan.look.slot_shape == "hexagon" and r2.look.slot_shape == "circle"
    assert fan.look.accent == "#00ff00" and fan.look.bg == r2.look.bg
    assert fan.sprites[0][0].tobytes() != plain.sprites[0][0].tobytes()
    assert r2.sprites[0][0].tobytes() == r.sprites[0][0].tobytes()            # the ring's own slots are untouched
    assert r2.cfg == r.cfg                                                    # and the settings were never swapped


def test_a_fan_slot_keeps_its_size_whatever_its_look_says():
    r, fan = fan_ring(fan_look={"slot": 150, "radius": 400})
    assert fan.cslot == pytest.approx(r.slot * ring.FAN_SLOT)
    assert fan.sprites[0][0].size[0] == fan_ring()[1].sprites[0][0].size[0]


def test_fan_lines_use_the_fans_lines_colour():
    r, plain = fan_ring()
    r2, own = fan_ring(fan_look={"colors": {"lines": "#00ff00"}})
    assert own.lines[0].tobytes() != plain.lines[0].tobytes()


def test_a_fan_is_hit_in_its_own_shape():
    r, fan = fan_ring(fan_look={"slot_shape": "diamond"})
    plain_ring, plain = fan_ring()
    rr = fan.cslot / 2 * 1.12 + 4
    for ring_, f in ((r, fan), (plain_ring, plain)):
        ring_.open = [1]
        ring_.centre = (0, 0)
    px, py = fan.pos[0]
    assert r._hit(px + rr * 1.1, py)[0] == (1, 0)            # past a circle's edge, in the tip
    assert plain_ring._hit(plain.pos[0][0] + rr * 1.1, plain.pos[0][1])[0] != (1, 0)


# --- hub styles --------------------------------------------------------------------------------
def test_each_hub_style_draws_a_different_hub():
    menu = make_menu(4, title="Tools")
    dots = {st: prepared(menu, hub=30, hub_style=st)._dot.tobytes() for st in ring.HUB_STYLES}
    assert len(set(dots.values())) == 4
    for st in ring.HUB_STYLES:
        assert prepared(menu, hub=30, hub_style=st)._dot.getchannel("A").getbbox() is not None


def test_a_ring_hub_is_hollow_and_a_dot_is_not():
    menu = make_menu(4)
    hollow = prepared(menu, hub=40, hub_style="ring", hub_glow=0.0)._dot
    solid = prepared(menu, hub=40, hub_style="dot")._dot
    c = hollow.size[0] // 2
    assert hollow.getpixel((c, c))[3] == 0 and solid.getpixel((c, c))[3] == 255
    assert hollow.getpixel((c + 18, c))[3] > 200                                     # the rim, 20 px out


def test_the_hub_takes_its_colour_role_and_glow():
    plain = prepared(make_menu(4), hub=30)
    hi = prepared(make_menu(4), hub=30, hub_color="highlight")
    c = plain._dot.size[0] // 2
    assert plain._dot.getpixel((c, c))[:3] == _rgb_of(config.DEFAULT_RING["colors"]["accent"])
    assert hi._dot.getpixel((c, c))[:3] == _rgb_of(config.DEFAULT_RING["colors"]["highlight"])
    none = prepared(make_menu(4), hub=30, hub_glow=0.0)._dot
    edge = (c + 18, c)
    assert none.getpixel(edge)[3] == 0 and plain._dot.getpixel(edge)[3] > 0          # no glow outside the dot


def test_the_default_hub_is_the_dot_it_always_was():
    assert prepared(make_menu(4))._dot.tobytes() == prepared(make_menu(4), hub_style="dot", hub_color="accent",
                                                              hub_glow=1.0)._dot.tobytes()


def test_no_hub_is_no_dot_for_every_style():
    for st in ring.HUB_STYLES:
        assert prepared(make_menu(4), hub=0, hub_style=st)._dot is None


def test_the_icon_hub_shows_the_menus_icon_or_a_monogram_of_its_title():
    menu = make_menu(4, title="Brush Tools")
    menu.icon = "tools.png"
    seen = []

    def icon_for(it):
        seen.append((it.kind, it.icon, it.label))
        return Image.new("RGBA", (64, 64), (0, 255, 0, 255)) if it.kind == "menu" else None
    withicon = prepared(menu, icon_for, hub=40, hub_style="icon")
    assert ("menu", "tools.png", "Brush Tools") in seen
    c = withicon._dot.size[0] // 2
    assert withicon._dot.getpixel((c, c))[:3] == (0, 255, 0)
    asked = []
    mono = prepared(make_menu(4, title="Brush Tools"), lambda it: asked.append(it.kind), hub=40, hub_style="icon")
    assert "menu" not in asked                                                 # no icon set: icon_for is not asked
    other = prepared(make_menu(4, title="Zed"), hub=40, hub_style="icon")
    assert mono._dot.tobytes() != withicon._dot.tobytes() and mono._dot.tobytes() != other._dot.tobytes()
    gone = make_menu(4, title="Brush Tools")
    gone.icon = "gone.png"                                                     # an icon that is not found: monogram
    assert prepared(gone, lambda it: None, hub=40, hub_style="icon")._dot.tobytes() == mono._dot.tobytes()


def test_the_hub_icon_is_part_of_the_sprite_key():
    menu = make_menu(4)
    menu.icon = "a.png"
    red = prepared(menu, lambda it: Image.new("RGBA", (8, 8), (255, 0, 0, 255)) if it.kind == "menu" else None,
                   hub=30, hub_style="icon")
    blue = prepared(menu, lambda it: Image.new("RGBA", (8, 8), (0, 0, 255, 255)) if it.kind == "menu" else None,
                    hub=30, hub_style="icon")
    assert red._sprite_key() != blue._sprite_key() and red._dot is not blue._dot
    assert prepared(make_menu(4), hub=30, hub_style="dot")._sprite_key()[4] is None


def test_the_hub_sets_the_title_push_and_where_the_spokes_start():
    draw = ring.ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for hub, dy in ((10, 18), (40, 33)):                                       # pinned: hub 10 and 40
        assert prepared(make_menu(4, title="Tools"), hub=hub)._caption(draw)[0][2] == dy
    # a hollow hub shows what is inside it, so spokes start at its edge; under a solid dot they stay as they were
    hollow = prepared(make_menu(4), hub=40, hub_style="ring")
    solid = prepared(make_menu(4), hub=40)
    assert hollow._static().tobytes() != solid._static().tobytes()
    assert solid._static().tobytes() == prepared(make_menu(4), hub=40, hub_color="text")._static().tobytes()


def test_the_ripples_and_dot_take_the_hub_colour():
    r = prepared(make_menu(4), hub_color="#00ff00", hub=30, animation="ripple")
    r._relayout()
    r.t0 = 0.0
    frame = r._compose(0.2)
    assert any(p[1] > 200 and p[0] < 60 and p[3] > 100 for p in _pixels(frame))     # the hub and its ripple are green


# --- the More slot -----------------------------------------------------------------------------
def test_a_more_slot_is_three_dots_with_no_submenu_badge():
    more, plain_sub = config.Item("More", "menu", {"menu": "more:m"}), config.Item("More", "menu", {"menu": "tools"})
    a, b = make_menu(3), make_menu(3)
    a.items.append(more)
    b.items.append(plain_sub)
    ra, rb = prepared(a), prepared(b)
    assert ra.sprites[3][0].tobytes() != rb.sprites[3][0].tobytes()
    n = ra.sprites[3][0].size[0]
    bx = n // 2 + int(ra.slot * 1.12 / 2 * 0.62)
    assert ra.sprites[3][0].getpixel((bx, bx)) != rb.sprites[3][0].getpixel((bx, bx))   # the badge is on the other only
    assert ring._is_more(more) and not ring._is_more(plain_sub)
    assert ring.Ring.preview(a, make_cfg(), lambda it: None).getchannel("A").getbbox() is not None


def test_the_more_glyph_draws_three_separate_dots():
    im = Image.new("RGBA", (60, 20))
    ring._glyph_more(ImageDraw.Draw(im), 30, 10, 40, (255, 255, 255, 255))
    row = [im.getpixel((x, 10))[3] > 0 for x in range(60)]
    assert sum(1 for i in range(1, 60) if row[i] and not row[i - 1]) == 3


# --- the sprite key ----------------------------------------------------------------------------
NEW_LOOK_KEYS = ("slot_shape", "slot_corner", "border_width", "icon_scale", "hub", "hub_style", "hub_color", "hub_glow",
                 "glow_color", "glow_opacity", "label_color", "labels")


def test_every_ring_setting_is_classified_as_in_the_sprites_or_not_exactly_once():
    keys = set(config.DEFAULT_RING) | set(NEW_LOOK_KEYS)
    in_key, out = set(ring.SPRITE_LOOK_KEYS), set(ring.NOT_IN_SPRITES)
    assert len(ring.SPRITE_LOOK_KEYS) == len(in_key) and not in_key & out, in_key & out
    assert keys <= in_key | out, sorted(keys - in_key - out)


def test_each_sprite_setting_changes_the_key_and_each_other_one_does_not():
    base = prepared(make_menu(3))._sprite_key()
    changes = {"slot": 60, "slot_shape": "squircle", "slot_corner": 0.4, "border_width": 4, "icon_scale": 0.7,
               "hub": 22, "hub_style": "ring", "hub_color": "text", "hub_glow": 0.5, "glow_color": "#123456",
               "glow_opacity": 0.2, "labels": "none", "label_color": "accent", "tag_colors": "glow",
               "tag_glow_opacity": 0.1, "tag_tint_opacity": 0.9, "tag_tint_style": "flat", "tag_tint_blend": "overlay",
               "theme": "light"}
    for k, v in changes.items():
        assert prepared(make_menu(3), **{k: v})._sprite_key() != base, k
    same = {"radius": 200, "dead_zone": 60, "tap_ms": 5, "timeout_s": 3, "animation": "pop", "flick": False,
            "hover_submenus": False, "tag_band": "wide", "tag_band_opacity": 0.1}
    for k, v in same.items():
        assert prepared(make_menu(3), **{k: v})._sprite_key() == base, k
    col = dict(config.DEFAULT_RING["colors"])
    for role in ("bg", "accent", "highlight", "text"):
        assert prepared(make_menu(3), colors=dict(col, **{role: "#010203"}))._sprite_key() != base, role


def test_the_key_starts_with_the_menu_id_and_has_the_scale_fourth():
    key = prepared(make_menu(2, mid="abc"))._sprite_key()
    assert key[0] == "abc" and key[3] == 1.0


# --- the cache keeps one entry per menu and scale ----------------------------------------------
def test_a_changed_setting_replaces_the_menus_entry_instead_of_adding_one():
    menu = make_menu(3, mid="slider")
    for slot in (40, 50, 60, 70, 80):
        prepared(menu, slot=slot)
    assert [k[0] for k in ring._sprite_cache] == ["slider"]


def test_another_scale_of_the_same_menu_lives_next_to_it():
    menu = make_menu(3, mid="two")
    for scale in (1.0, 1.5):
        r = make_ring(menu)
        r._geometry(scale)
        r._prepare()
    assert sorted(k[3] for k in ring._sprite_cache) == [1.0, 1.5]
    r = make_ring(menu, slot=50)
    r._geometry(1.5)
    r._prepare()
    assert sorted(k[3] for k in ring._sprite_cache) == [1.0, 1.5]


def test_replacing_does_not_push_other_menus_out_of_the_cache():
    for i in range(7):
        prepared(make_menu(2, mid=f"keep{i}"))
    for slot in range(40, 60, 4):
        prepared(make_menu(2, mid="dragged"), slot=slot)
    assert {k[0] for k in ring._sprite_cache} == {f"keep{i}" for i in range(7)} | {"dragged"}
