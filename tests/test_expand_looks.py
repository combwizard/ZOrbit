"""expand.py and the look system: tag colours are always stamped, and a menu whose look says when_full "more" is
paged into a first page with a More slot and the synthetic menus "more:<id>" behind it."""
import json

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
