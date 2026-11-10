"""A submenu with auto slots that opens as a ring keeps its auto slots where they were when it opens: the path
radiald.App._on_ring_done -> Expander.resolve -> App.open_menu fills the menu once, not twice. No window is made."""
import json
import time

import pytest

import radiald
import ring
import usage

MENUS = {"h": {"title": "H", "hotkey": "Q", "items": [{"brush": "Move"}, {"menu": "s", "label": "Sub"}]},
         "s": {"title": "S", "items": [{"auto": "brush"}, {"auto": "brush"}, {"auto": "brush"}]}}


@pytest.fixture
def app(tmp_path, monkeypatch):
    for name in ("_prefetch", "_schedule_prewarm", "_prune_icons"):
        monkeypatch.setattr(radiald.App, name, lambda self: None)
    monkeypatch.setattr(radiald.App, "icon_for", lambda self, item: None)
    monkeypatch.setattr(ring.Ring, "show", lambda self, x, y: None)          # no window
    monkeypatch.setattr(radiald, "log", lambda m: None)
    now = time.time()
    # Saved in an order that is not the ranking: Beta has the higher score, but Alpha holds the first slot.
    raw = {"brushes": {"alpha": {"name": "Alpha", "score": 1.0, "t": now - 3600},
                       "beta": {"name": "Beta", "score": 3.0, "t": now}},
           "menus": {"s": {"slots": ["Alpha", "Beta", None], "pending": []}}}
    (tmp_path / "usage.json").write_text(json.dumps(raw), encoding="utf-8")
    radial = tmp_path / "radial.json"
    radial.write_text(json.dumps({"menus": MENUS}), encoding="utf-8")
    a = radiald.App(str(radial))
    a.usage = usage.Usage(str(tmp_path / "usage.json")).load()
    a.load_config(force=True, balloon=False)
    return a


def shown(app):
    return [it.label for it in app.expander.resolve("s").items]


def open_sub(app):
    """Clicks the Sub slot of the hotkey ring: the submenu opens as a ring of its own, as the app opens it."""
    sub = app.expander.menu(app.cfg.menus["h"]).items[1]
    app._on_ring_done(sub, "click")
    labels = [it.label for it in app.ring.items]
    app.ring = None
    return labels


def state(app):
    return json.loads(json.dumps(app.usage.menus["s"]))


def test_opening_a_submenu_with_auto_slots_keeps_their_order(app):
    before = state(app)
    assert shown(app) == ["Alpha", "Beta", "Auto"]
    for _ in range(2):
        assert open_sub(app) == ["Alpha", "Beta", "Auto"]
        assert state(app) == before and shown(app) == ["Alpha", "Beta", "Auto"]


def test_a_menu_filled_once_is_not_filled_again(app):
    once = app.expander.resolve("s")
    assert app.expander.menu(once) is once
    assert app.expander.menu(app.expander.menu(app.cfg.menus["h"])).items == app.expander.menu(app.cfg.menus["h"]).items


def test_the_order_still_changes_by_the_top_of_the_list_twice_in_a_row(app):
    pick = radiald.C.Item(label="Clay", kind="brush", data={"brush": "Clay"})
    app._record_pick(pick)                          # an empty slot takes a newly picked brush
    assert state(app)["slots"] == ["Alpha", "Beta", "Clay"]
    app.usage.brushes["clay"]["score"] = 0.1        # Clay has faded since
    app.usage.save()
    delta = radiald.C.Item(label="Delta", kind="brush", data={"brush": "Delta"})
    for _ in range(4):
        app.usage.record("Delta")                   # Delta is used a lot, so it makes the top three
    app._record_pick(delta)                         # the first time at the top: it waits
    first = state(app)
    assert first["slots"] == ["Alpha", "Beta", "Clay"] and "Delta" in first["pending"]
    open_sub(app)
    open_sub(app)
    assert state(app) == first                      # opening the submenu changes nothing
    app._record_pick(delta)                         # the second time in a row: it takes the weakest slot
    assert state(app)["slots"] == ["Alpha", "Beta", "Delta"]
    assert open_sub(app) == ["Alpha", "Beta", "Delta"]


def test_a_pick_lands_in_the_slot_the_ranking_gives_it(tmp_path, monkeypatch):
    """Two empty auto slots and an older brush, Clay, that never filled one. Picking Smooth counts it first and then
    fills the slots from the ranking, so Smooth (picked just now) comes before Clay (a week old)."""
    for name in ("_prefetch", "_schedule_prewarm", "_prune_icons"):
        monkeypatch.setattr(radiald.App, name, lambda self: None)
    monkeypatch.setattr(radiald, "log", lambda m: None)
    raw = {"brushes": {"clay": {"name": "Clay", "score": 1.0, "t": time.time() - 7 * 86400}}}
    (tmp_path / "usage.json").write_text(json.dumps(raw), encoding="utf-8")
    radial = tmp_path / "radial.json"
    radial.write_text(json.dumps({"menus": {"m": {"title": "M", "hotkey": "Q",
                                                  "items": [{"auto": "brush"}, {"auto": "brush"}]}}}), encoding="utf-8")
    a = radiald.App(str(radial))
    a.usage = usage.Usage(str(tmp_path / "usage.json")).load()
    a.load_config(force=True, balloon=False)
    a._record_pick(radiald.C.Item(label="Smooth", kind="brush", data={"brush": "Smooth"}))
    assert a.usage.menus["m"]["slots"] == ["Smooth", "Clay"]