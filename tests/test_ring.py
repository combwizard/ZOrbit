"""ring.py: radius growth, fonts for other scripts, label pills, draw order and the sprite cache.

Nothing here opens a window: Ring.preview and the sprite methods only need Pillow.
"""
import copy
import math
import os
import shutil
from types import SimpleNamespace

import pytest
from PIL import Image, ImageFont

import config
import ring

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
                                  {"colors": dict(config.DEFAULT_RING["colors"], accent="#112233")}])
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
