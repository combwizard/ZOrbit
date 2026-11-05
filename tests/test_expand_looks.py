"""expand.py and the look system: tag colours are always stamped, and a menu whose look says when_full "more" is
paged into a first page with a More slot and the synthetic menus "more:<id>" behind it."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import config
import expand


class FakeUsage:
    """Fills every auto slot with Auto1, Auto2... in order, and counts how often it was asked."""
    version = 1

    def __init__(self):
        self.asked = 0

    def load(self):
        return self

    def slots(self, menu):
        self.asked += 1
        n = sum(1 for it in menu.items if it.kind == "auto")
        return [f"Auto{i + 1}" for i in range(n)]


class FakeTags:
    mtime = 0

    def __init__(self, item_colour=""):
        self.item_colour = item_colour

    def has(self, key):
        return False

    def color(self, key):
        return "#ff0000"

    def color_of_item(self, key):
        return self.item_colour


def load(tmp_path, menus, **top):
    p = tmp_path / "radial.json"
    p.write_text(json.dumps({"menus": menus, **top}), encoding="utf-8")
    return config.load(str(p))


def brushes(n, prefix="B"):
    return [{"brush": f"{prefix}{i}"} for i in range(n)]


def menu(items, **settings):
    return {"hotkey": "Q", "items": items, **settings}


def expander(cfg, tags=None, usage=None):
    return expand.Expander(cfg, usage or FakeUsage(), tags or FakeTags())


def labels(m):
    return [it.label for it in m.items]


MORE = {"ring": {"when_full": "more"}}


# --- capacity -----------------------------------------------------------------------------------------
@pytest.mark.parametrize("radius, slot, expected", [(145, 72, 9), (100, 72, 6), (400, 32, 62), (60, 160, 1)])
def test_the_capacity_of_a_ring(radius, slot, expected):
    assert expand._capacity(radius, slot) == expected


@pytest.mark.parametrize("count", [3, 8, 9, 12, 30])
def test_the_needed_radius_fits_the_count_and_one_pixel_less_does_not(count):
    r = expand.needed_radius(count, 72)
    assert expand._capacity(r, 72) >= count > expand._capacity(r - 1, 72)


# --- paging -------------------------------------------------------------------------------------------
def test_twelve_items_at_the_defaults_become_eight_and_a_more_slot(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(12))}, **MORE)
    m = expander(cfg).menu(cfg.menus["main"])
    assert labels(m) == [f"B{i}" for i in range(8)] + ["More"]
    more = m.items[-1]
    assert (more.kind, more.data) == ("menu", {"menu": "more:main"})


def test_more_main_has_the_rest(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(12), title="Mine", animation="pop")}, **MORE)
    ex = expander(cfg)
    rest = ex.resolve("more:main")
    assert labels(rest) == [f"B{i}" for i in range(8, 12)]
    assert (rest.id, rest.title, rest.hotkey, rest.animation) == ("more:main", "Mine", None, "pop")
    assert rest.look == cfg.menus["main"].look and not rest.fan


def test_a_menu_that_fits_is_not_cut_and_has_no_more_menu(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(9))}, **MORE)
    ex = expander(cfg)
    assert labels(ex.menu(cfg.menus["main"])) == [f"B{i}" for i in range(9)]
    assert ex.resolve("more:main") is None


def test_ten_items_are_eight_and_more_and_two_more(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(10))}, **MORE)
    ex = expander(cfg)
    assert len(ex.menu(cfg.menus["main"]).items) == 9
    assert labels(ex.resolve("more:main")) == ["B8", "B9"]


def test_thirty_items_page_again_in_more_more(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(30))}, **MORE)
    ex = expander(cfg)
    first = ex.menu(cfg.menus["main"])
    second = ex.resolve("more:main")
    third = ex.resolve("more:more:main")
    fourth = ex.resolve("more:more:more:main")
    assert labels(first)[:8] == [f"B{i}" for i in range(8)] and first.items[-1].data == {"menu": "more:main"}
    assert labels(second)[:8] == [f"B{i}" for i in range(8, 16)] and second.items[-1].data == {"menu": "more:more:main"}
    assert labels(third)[:8] == [f"B{i}" for i in range(16, 24)]
    assert third.items[-1].data == {"menu": "more:more:more:main"}
    assert labels(fourth) == [f"B{i}" for i in range(24, 30)]
    assert ex.resolve("more:more:more:more:main") is None
    names = [n for m in (first, second, third, fourth) for n in labels(m) if n != "More"]
    assert names == [f"B{i}" for i in range(30)]               # nothing lost, nothing twice


def test_auto_slots_in_the_overflow_are_filled_once_and_in_order(tmp_path):
    items = brushes(6) + [{"auto": "brush"}] * 6
    cfg = load(tmp_path, {"main": menu(items)}, **MORE)
    usage = FakeUsage()
    ex = expander(cfg, usage=usage)
    first = ex.menu(cfg.menus["main"])
    rest = ex.resolve("more:main")
    assert labels(first)[:8] == ["B0", "B1", "B2", "B3", "B4", "B5", "Auto1", "Auto2"]
    assert labels(rest) == ["Auto3", "Auto4", "Auto5", "Auto6"]
    assert all(it.auto for it in rest.items) and usage.asked == 2     # once for the menu, once for resolving more:


def test_menu_of_a_more_menu_is_returned_unchanged(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(6) + [{"auto": "brush"}] * 6)}, **MORE)
    usage = FakeUsage()
    ex = expander(cfg, usage=usage)
    rest = ex.resolve("more:main")
    asked = usage.asked
    assert ex.menu(rest) is rest
    assert usage.asked == asked


def test_a_fan_menu_is_never_paged(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(2) + [{"menu": "fan"}]), "fan": {"fan": True, "items": brushes(14)}},
               **MORE)
    ex = expander(cfg)
    assert len(ex.menu(cfg.menus["fan"]).items) == 14
    assert ex.resolve("more:fan") is None


def test_a_tag_menu_is_never_paged(tmp_path, monkeypatch):
    cfg = load(tmp_path, {"main": menu(brushes(2))}, **MORE)
    ex = expander(cfg)
    monkeypatch.setattr(ex, "tag_menu", lambda key: "the tag menu")
    assert ex.resolve("tag:x") == "the tag menu"
    assert ex.resolve("more:tag:x") is None


def test_a_ring_with_room_for_fewer_than_three_is_not_cut(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(12))}, ring={"when_full": "more", "radius": 60, "slot": 160})
    assert expand._capacity(60, 160) < 3
    ex = expander(cfg)
    assert len(ex.menu(cfg.menus["main"]).items) == 12
    assert ex.resolve("more:main") is None


@pytest.mark.parametrize("mode", ["grow", "rings"])
def test_grow_and_rings_leave_the_menu_alone(tmp_path, mode):
    cfg = load(tmp_path, {"main": menu(brushes(30))}, ring={"when_full": mode})
    ex = expander(cfg)
    assert len(ex.menu(cfg.menus["main"]).items) == 30
    assert ex.resolve("more:main") is None


def test_the_look_of_the_menu_decides_not_the_ring(tmp_path):
    menus = {"main": menu(brushes(12), look={"when_full": "more"}), "other": menu(brushes(12))}
    cfg = load(tmp_path, menus)
    ex = expander(cfg)
    assert len(ex.menu(cfg.menus["main"]).items) == 9
    assert len(ex.menu(cfg.menus["other"]).items) == 12


def test_the_radius_and_slot_of_the_look_set_the_page_size(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(12), look={"when_full": "more", "radius": 100})})
    assert len(expander(cfg).menu(cfg.menus["main"]).items) == 6               # 5 and More
    cfg = load(tmp_path, {"main": menu(brushes(12))}, ring={"when_full": "more", "radius": 250})
    assert len(expander(cfg).menu(cfg.menus["main"]).items) == 12              # all of them fit


def test_a_more_menu_keeps_the_look_of_its_parent(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(12), look={"when_full": "more", "slot_shape": "hexagon"})})
    rest = expander(cfg).resolve("more:main")
    assert rest.look["slot_shape"] == "hexagon" and rest.look["when_full"] == "more"


def test_an_unknown_menu_has_no_more_menu(tmp_path):
    cfg = load(tmp_path, {"main": menu(brushes(12))}, **MORE)
    assert expander(cfg).resolve("more:nope") is None


# --- empty slots --------------------------------------------------------------------------------------
EMPTY = {"empty": True}


def test_empty_slots_keep_their_positions_through_fill(tmp_path):
    items = [{"brush": "A"}, EMPTY, {"auto": "brush"}, EMPTY, EMPTY, {"brush": "B"}]
    cfg = load(tmp_path, {"main": menu(items)})
    m = expander(cfg).menu(cfg.menus["main"])
    assert [it.kind for it in m.items] == ["brush", "empty", "brush", "empty", "empty", "brush"]
    assert labels(m) == ["A", "", "Auto1", "", "", "B"]


def test_empty_slots_count_toward_the_page(tmp_path):
    items = brushes(4) + [EMPTY] * 7 + [{"brush": "Z"}]      # 12 slots: eight, then a More slot
    cfg = load(tmp_path, {"main": menu(items)}, **MORE)
    m = expander(cfg).menu(cfg.menus["main"])
    assert [it.kind for it in m.items] == ["brush"] * 4 + ["empty"] * 4 + ["menu"]
    assert m.items[-1].data == {"menu": "more:main"}


def test_the_more_menu_drops_the_empty_slots(tmp_path):
    items = brushes(8) + [EMPTY, {"brush": "X"}, EMPTY, {"brush": "Y"}]
    cfg = load(tmp_path, {"main": menu(items)}, **MORE)
    ex = expander(cfg)
    assert labels(ex.resolve("more:main")) == ["X", "Y"]
    assert ex._whole("more:main").id == "more:main"


def test_a_page_whose_rest_is_all_empty_has_no_more_slot(tmp_path):
    items = brushes(7) + [EMPTY] * 5
    cfg = load(tmp_path, {"main": menu(items)}, **MORE)
    ex = expander(cfg)
    m = ex.menu(cfg.menus["main"])
    assert [it.kind for it in m.items] == ["brush"] * 7 + ["empty", "empty"]
    assert ex.resolve("more:main") is None


def test_a_menu_of_only_empty_slots_is_expanded_as_it_is(tmp_path):
    cfg = load(tmp_path, {"main": menu([EMPTY] * 8)})
    assert [it.kind for it in expander(cfg).menu(cfg.menus["main"]).items] == ["empty"] * 8


# --- tag colours --------------------------------------------------------------------------------------
@pytest.mark.parametrize("ring", [{"tag_colors": "none", "tag_band": "none"}, {"tag_colors": "none"}, {}])
def test_a_slot_always_carries_its_tag_colour(tmp_path, ring):
    cfg = load(tmp_path, {"main": menu([{"brush": "Standard"}])}, ring=ring)
    it = expander(cfg, tags=FakeTags("#abcdef")).menu(cfg.menus["main"]).items[0]
    assert it.color == "#abcdef"


def test_a_steps_slot_that_starts_with_a_brush_carries_its_colour(tmp_path):
    cfg = load(tmp_path, {"main": menu([{"steps": [{"brush": "Standard"}, {"press": "A:B"}]}])},
               ring={"tag_colors": "none", "tag_band": "none"})
    assert expander(cfg, tags=FakeTags("#abcdef")).menu(cfg.menus["main"]).items[0].color == "#abcdef"


# --- how many slots a tag fan holds (ring.tag_limit) ---------------------------------------------------
class TagFanAssets:
    """A stand-in for the asset index: n installed brushes, and a generation that never moves."""
    generation = 1

    def __init__(self, n):
        self.brushes = {f"brush:{i:02d}": Path(f"C:/x/B{i:02d}.zbp") for i in range(n)}

    def index(self, kind):
        return {k.split(":", 1)[1]: p for k, p in self.brushes.items()} if kind == "brush" else {}

    def names(self, kind):
        return {}


class TagFanTags:
    mtime = 1

    def __init__(self, n):
        self.n = n

    def has(self, key):
        return True

    def items_with(self, key, kind=None):
        return [f"brush:{i:02d}" for i in range(self.n)] if kind == "brush" else []

    def color(self, key):
        return "#ff0000"

    def label(self, key):
        return "Fan"


class FanUsage:
    version = 1

    def load(self):
        return self

    def rank(self, names):
        return list(names)


def tag_fan(monkeypatch, tmp_path, n, **ring):
    monkeypatch.setattr(expand, "assets", TagFanAssets(n))
    cfg = load(tmp_path, {"main": menu(brushes(3))}, ring=ring)
    return expand.Expander(cfg, FanUsage(), TagFanTags(n)), cfg


def test_a_tag_fan_holds_twelve_slots_unless_the_ring_says_otherwise(monkeypatch, tmp_path):
    ex, cfg = tag_fan(monkeypatch, tmp_path, 20)
    assert cfg.ring["tag_limit"] == 12 == expand.TAG_SLOTS
    items = ex.tag_menu("fan").items
    assert len(items) == 12 and items[-1].kind == "browser" and items[-1].label == "More…"
    assert [i.label for i in items[:11]] == [f"B{i:02d}" for i in range(11)]


@pytest.mark.parametrize("limit", [4, 7, 12, 24])
def test_the_tag_limit_sets_the_slots_of_a_fan_with_more_items(monkeypatch, tmp_path, limit):
    ex, _ = tag_fan(monkeypatch, tmp_path, 30, tag_limit=limit)
    items = ex.tag_menu("fan").items
    assert len(items) == limit and items[-1].kind == "browser"
    assert [i.label for i in items[:-1]] == [f"B{i:02d}" for i in range(limit - 1)]


def test_a_fan_that_fits_the_limit_has_no_more_slot(monkeypatch, tmp_path):
    ex, _ = tag_fan(monkeypatch, tmp_path, 9, tag_limit=9)
    items = ex.tag_menu("fan").items
    assert len(items) == 9 and all(i.kind == "brush" for i in items)
    ex, _ = tag_fan(monkeypatch, tmp_path, 9, tag_limit=8)
    assert len(ex.tag_menu("fan").items) == 8


def test_changing_the_tag_limit_rebuilds_a_cached_fan(monkeypatch, tmp_path):
    ex, cfg = tag_fan(monkeypatch, tmp_path, 30, tag_limit=6)
    first = ex.tag_menu("fan")
    assert len(first.items) == 6 and ex.tag_menu("fan") is first            # served from the cache
    cfg.ring["tag_limit"] = 10                                              # the same Expander, another setting
    assert len(ex.tag_menu("fan").items) == 10
    cfg.ring["tag_limit"] = 6
    assert len(ex.tag_menu("fan").items) == 6


@pytest.mark.parametrize("bad", [True, 1, "8", 8.5, None])
def test_a_tag_limit_that_is_not_usable_falls_back_to_twelve(monkeypatch, tmp_path, bad):
    ex, cfg = tag_fan(monkeypatch, tmp_path, 30)
    cfg.ring["tag_limit"] = bad
    assert len(ex.tag_menu("fan").items) == 12

