"""The order of Favourites: the pure rules in zorbit/studio_ui/favorder.js, run by tests/js/fav_order.js (skipped when
node is not installed), and the API method and the fan of a Favourites slot."""
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import config as C
import expand
import tags
import webapi
from tags import FAVOURITE, TagStore

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_the_rules_of_the_order_in_javascript():
    run = subprocess.run([NODE, os.path.join(ROOT, "tests", "js", "fav_order.js")], cwd=ROOT, capture_output=True,
                         text=True, timeout=60, encoding="utf-8")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "fav order checks pass" in run.stdout


# --- the fan --------------------------------------------------------------------------------------
class FakeAssets:
    generation = 1

    def __init__(self, **by_kind):
        self.idx = {k: {} for k in C.ASSET_KINDS}
        for kind, names in by_kind.items():
            self.idx[kind] = {tags._norm(n): Path(f"C:/x/{n}.zbp") for n in names}

    def index(self, kind):
        return self.idx[kind]

    def rescan(self, kind):
        pass


class ByName:
    version = 1

    def load(self):
        return self

    def rank(self, names):
        """Most used first: here, whatever comes last in the alphabet."""
        return sorted(names, key=str.lower, reverse=True)


def fan(tmp_path, monkeypatch, items, order=None, **by_kind):
    """An Expander on a real tags.json with these items and these orders, and its store."""
    monkeypatch.setattr(expand, "assets", FakeAssets(**by_kind))
    raw = {"version": 1, "tags": {"rock": {"label": "Rock", "color": "#A8DF23"}}, "items": items}
    store = TagStore(str(tmp_path / "tags.json"))
    store.import_tags(raw, "replace")
    for kind, names in (order or {}).items():
        assert store.set_favourite_order(kind, names)["ok"]
    return expand.Expander(SimpleNamespace(ring={}), ByName(), store), store


def labels(menu):
    return [(i.kind, i.label) for i in menu.items]


STARS = {"brush:apple": [FAVOURITE], "brush:pear": [FAVOURITE], "brush:plum": [FAVOURITE],
         "alpha:one": [FAVOURITE], "alpha:two": [FAVOURITE], "alpha:ten": [FAVOURITE]}
INSTALLED = {"brush": ["Apple", "Pear", "Plum"], "alpha": ["One", "Two", "Ten"]}


def test_a_favourites_fan_with_no_order_is_most_used_brushes_then_the_rest_by_name(tmp_path, monkeypatch):
    ex, _ = fan(tmp_path, monkeypatch, STARS, **INSTALLED)
    assert labels(ex.tag_menu(FAVOURITE)) == [("brush", "Plum"), ("brush", "Pear"), ("brush", "Apple"),
                                              ("alpha", "One"), ("alpha", "Ten"), ("alpha", "Two")]


def test_a_favourites_fan_follows_the_order_of_a_kind_with_brushes_still_first(tmp_path, monkeypatch):
    ex, _ = fan(tmp_path, monkeypatch, STARS, {"brush": ["pear", "apple", "plum"]}, **INSTALLED)
    assert labels(ex.tag_menu(FAVOURITE))[:3] == [("brush", "Pear"), ("brush", "Apple"), ("brush", "Plum")]
    assert labels(ex.tag_menu(FAVOURITE))[3:] == [("alpha", "One"), ("alpha", "Ten"), ("alpha", "Two")]   # no order: by name

    ex, _ = fan(tmp_path, monkeypatch, STARS, {"alpha": ["two", "one", "ten"]}, **INSTALLED)
    assert labels(ex.tag_menu(FAVOURITE)) == [("brush", "Plum"), ("brush", "Pear"), ("brush", "Apple"),
                                              ("alpha", "Two"), ("alpha", "One"), ("alpha", "Ten")]


def test_a_fan_skips_a_saved_item_that_is_not_installed_and_keeps_the_others_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr(expand.Expander, "_rescan_later", lambda self, kind: None)
    ex, _ = fan(tmp_path, monkeypatch, STARS, {"brush": ["plum", "apple", "pear"]}, brush=["Plum", "Pear"])
    assert labels(ex.tag_menu(FAVOURITE)) == [("brush", "Plum"), ("brush", "Pear")]


def test_another_tag_on_the_same_items_does_not_follow_the_order(tmp_path, monkeypatch):
    items = {k: [FAVOURITE, "rock"] for k in STARS}
    ex, _ = fan(tmp_path, monkeypatch, items, {"brush": ["pear", "apple", "plum"]}, **INSTALLED)
    assert labels(ex.tag_menu("rock")) == [("brush", "Plum"), ("brush", "Pear"), ("brush", "Apple"),
                                           ("alpha", "One"), ("alpha", "Ten"), ("alpha", "Two")]


def test_the_fan_is_built_again_when_the_order_changes(tmp_path, monkeypatch):
    ex, store = fan(tmp_path, monkeypatch, STARS, {"brush": ["pear", "apple", "plum"]}, **INSTALLED)
    first = ex.tag_menu(FAVOURITE)
    assert ex.tag_menu(FAVOURITE) is first                     # served from the cache
    assert store.set_favourite_order("brush", ["apple", "plum", "pear"])["ok"]
    assert labels(ex.tag_menu(FAVOURITE))[:3] == [("brush", "Apple"), ("brush", "Plum"), ("brush", "Pear")]
    assert store.set_favourite_order("brush", None)["ok"]      # back to most used
    assert labels(ex.tag_menu(FAVOURITE))[:3] == [("brush", "Plum"), ("brush", "Pear"), ("brush", "Apple")]


def test_the_fan_cache_goes_by_the_order_even_when_the_file_time_stays_the_same(tmp_path, monkeypatch):
    """The stat of a file written twice in quick succession can repeat. The order itself is in the stamp."""
    ex, store = fan(tmp_path, monkeypatch, STARS, {"brush": ["pear", "apple", "plum"]}, **INSTALLED)
    ex.tag_menu(FAVOURITE)
    mtime = store.mtime
    store.set_favourite_order("brush", ["plum", "apple", "pear"])
    store.mtime = mtime
    assert labels(ex.tag_menu(FAVOURITE))[:3] == [("brush", "Plum"), ("brush", "Apple"), ("brush", "Pear")]


def test_a_star_reaches_the_fan_at_the_end_of_the_order(tmp_path, monkeypatch):
    items = {k: v for k, v in STARS.items() if k != "brush:apple"}
    ex, store = fan(tmp_path, monkeypatch, items, {"brush": ["plum", "pear"]}, **INSTALLED)
    assert store.tag_items(["brush:apple"], add=[FAVOURITE])["ok"]
    assert labels(ex.tag_menu(FAVOURITE))[:3] == [("brush", "Plum"), ("brush", "Pear"), ("brush", "Apple")]


def test_the_order_does_not_change_how_a_fan_is_cut(tmp_path, monkeypatch):
    many = [f"B{i:02d}" for i in range(20)]
    items = {f"brush:{n.lower()}": [FAVOURITE] for n in many}
    ex, _ = fan(tmp_path, monkeypatch, items, {"brush": [n.lower() for n in reversed(many)]}, brush=many)
    menu = ex.tag_menu(FAVOURITE)
    assert [i.label for i in menu.items[:2]] == ["B19", "B18"]
    assert menu.items[-1].kind == "browser" and len(menu.items) == 12


# --- the API --------------------------------------------------------------------------------------
@pytest.fixture
def api(tmp_path, monkeypatch):
    path = str(tmp_path / "tags.json")
    store = TagStore(path)
    store.import_tags({"version": 1, "tags": {"rock": {"label": "Rock", "color": "#A8DF23"}},
                       "items": {"brush:a": [FAVOURITE], "brush:b": [FAVOURITE], "brush:c": [FAVOURITE]}}, "replace")
    monkeypatch.setattr(webapi, "store", lambda: store)
    return webapi.TagApi()


def test_the_api_answers_with_the_snapshot_so_every_browser_repaints(api):
    res = api.set_favourite_order("brush", ["c", "a", "b"])
    assert res["ok"] and res["favourite_order"] == {"brush": ["c", "a", "b"]}
    assert res["tags"] and res["items"] and res["mtime_ns"]    # the rest of the snapshot, as any tag call


def test_the_api_clears_with_none_and_get_tags_tells_it_too(api):
    api.set_favourite_order("brush", ["c", "a", "b"])
    assert api.get_tags()["favourite_order"] == {"brush": ["c", "a", "b"]}
    assert api.set_favourite_order("brush")["favourite_order"] == {}
    assert api.get_tags()["favourite_order"] == {}


def test_the_api_passes_a_refusal_on_with_the_order_as_it_was(api):
    api.set_favourite_order("brush", ["c", "a", "b"])
    res = api.set_favourite_order("sound", ["x"])
    assert res["ok"] is False and "sound" in res["error"]
    assert res["favourite_order"] == {"brush": ["c", "a", "b"]}


def test_a_snapshot_field_stays_empty_for_an_untouched_store(tmp_path, monkeypatch):
    store = TagStore(str(tmp_path / "none.json")).load()
    monkeypatch.setattr(webapi, "store", lambda: store)
    assert webapi.TagApi().get_tags()["favourite_order"] == {}


def test_the_kinds_with_an_order_are_the_kinds_of_tags():
    assert tags.ORDER_KINDS == C.ASSET_KINDS
