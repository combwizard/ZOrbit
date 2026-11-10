"""A tag fan that opens as a ring of its own (no room by a screen edge, or deeper than a fan can go) shows its items in
the tag's colour, as the fan does: radiald.App._on_ring_done -> Expander.resolve -> App.open_menu, with no window.
The Recent fan opened as a ring keeps its items as they are too."""
import json
from pathlib import Path

import pytest

import config as C
import expand
import radiald
import recent
import ring
import tags
from tags import TagStore

ROCK, WOOD = "#a8df23", "#3355ff"
RECENT = ["D:/Projects/One.zpr", "D:/Models/Two.ztl"]


class FakeAssets:
    """Apple and Pear are installed brushes."""
    generation = 1

    def __init__(self):
        self.idx = {k: {} for k in C.ASSET_KINDS}
        self.idx["brush"] = {tags._norm(n): Path(f"C:/x/{n}.zbp") for n in ("Apple", "Pear")}

    def index(self, kind):
        return self.idx[kind]

    def names(self, kind):
        return {}

    def rescan(self, kind):
        pass


@pytest.fixture
def app(tmp_path, monkeypatch):
    for name in ("_prefetch", "_schedule_prewarm", "_prune_icons"):
        monkeypatch.setattr(radiald.App, name, lambda self: None)
    monkeypatch.setattr(radiald.App, "icon_for", lambda self, item: None)
    monkeypatch.setattr(ring.Ring, "show", lambda self, x, y: None)          # no window
    monkeypatch.setattr(radiald, "log", lambda m: None)
    monkeypatch.setattr(expand, "assets", FakeAssets())
    monkeypatch.setattr(recent, "entries", lambda kind, limit, install=None, log=None: RECENT[:limit])
    monkeypatch.setattr(recent, "prefetch", lambda *a, **k: None)
    store = TagStore(str(tmp_path / "tags.json"))
    # Apple carries Wood first and Rock second, so its own colour is Wood's; Pear carries Rock only.
    store.import_tags({"version": 1, "tags": {"rock": {"label": "Rock", "color": ROCK},
                                              "wood": {"label": "Wood", "color": WOOD}},
                       "items": {"brush:apple": ["wood", "rock"], "brush:pear": ["rock"]}}, "replace")
    radial = tmp_path / "radial.json"
    radial.write_text(json.dumps({"menus": {"h": {"title": "H", "hotkey": "Q", "items": [
        {"brush": "Apple"}, {"tag": "rock"}, {"recent": "any"}]}}}), encoding="utf-8")
    a = radiald.App(str(radial))
    a.tags = store
    a.load_config(force=True, balloon=False)
    return a


def open_as_ring(app, k):
    """Clicks slot k of the hotkey ring when its submenu opens as a ring of its own; the items that ring is given."""
    item = app.expander.menu(app.cfg.menus["h"]).items[k]
    assert item.kind == "menu"
    app._on_ring_done(item, "click")
    items, app.ring = app.ring.items, None
    return items


def test_a_tag_fan_opened_as_a_ring_shows_its_items_in_the_tags_colour(app):
    fan = app.expander.resolve("tag:rock")                    # the fan form
    ringed = open_as_ring(app, 1)                              # the same menu, opened as a ring of its own
    assert sorted((it.label, it.color.lower()) for it in fan.items) == [("Apple", ROCK), ("Pear", ROCK)]
    assert [(it.label, it.color.lower()) for it in ringed] == [(it.label, it.color.lower()) for it in fan.items]
    assert app.expander.menu(app.cfg.menus["h"]).items[0].color.lower() == WOOD   # in a ring of its own: its own tag


def test_a_recent_fan_opened_as_a_ring_keeps_its_items(app):
    fan = app.expander.resolve("recent:any")
    assert open_as_ring(app, 2) == fan.items
