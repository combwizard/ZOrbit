"""Merging tags in the browser window: it holds no menus, so the backend points the ring items that used the merged
tag at the kept one in radial.json. Studio does the same inside its editor (config.retag is the shared helper)."""
import json

import pytest

import config as C
import paths
import popout
import tags
import webapi


def _menus():
    return {"menus": {"main": {"hotkey": "q", "items": [
        {"tag": "blocking"}, {"browser": "blocking", "kind": "alpha"}, {"tag": "detailing"},
        {"brush": "Standard"}, {"browser": ""}]}}}


# --- config.retag ------------------------------------------------------------------------------------

def test_retag_moves_tag_and_browser_slots_and_counts_them():
    cfg = _menus()
    assert C.retag(cfg, {"blocking": "detailing"}) == 2
    items = cfg["menus"]["main"]["items"]
    assert items[0] == {"tag": "detailing"}
    assert items[1] == {"browser": "detailing", "kind": "alpha"}
    assert items[2] == {"tag": "detailing"}
    assert items[3] == {"brush": "Standard"}


def test_retag_with_nothing_to_do_changes_nothing():
    cfg = _menus()
    before = json.dumps(cfg)
    assert C.retag(cfg, {}) == 0
    assert C.retag(cfg, {"nope": "x"}) == 0
    assert C.retag({"menus": {"a": "not a menu", "b": {"items": ["x", None]}}}, {"nope": "x"}) == 0
    assert json.dumps(cfg) == before


# --- the browser window's merge ----------------------------------------------------------------------

@pytest.fixture
def merge_env(tmp_path, monkeypatch):
    """A PopoutApi over a temporary tags.json and radial.json."""
    cfg = tmp_path / "radial.json"
    monkeypatch.setattr(paths, "CONFIG_FILE", str(cfg))
    raw = {"tags": {k: {"label": k.title(), "color": "#F86B33"} for k in ("blocking", "detailing")},
           "items": {"brush:claybuildup": ["blocking"]}}
    tfile = tmp_path / "tags.json"
    tfile.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(webapi, "_STORE", tags.TagStore(str(tfile)).load())
    return popout.PopoutApi(None), cfg


def test_merge_in_the_browser_window_rewrites_radial_json(merge_env):
    api, cfg = merge_env
    cfg.write_text(json.dumps(_menus()), encoding="utf-8")
    res = api.merge_tags("blocking", "detailing")
    assert res["ok"] and res["ring_items"] == 2 and "ring_error" not in res
    items = json.loads(cfg.read_text(encoding="utf-8"))["menus"]["main"]["items"]
    assert items[0] == {"tag": "detailing"} and items[1]["browser"] == "detailing"
    bak = json.loads((cfg.parent / "radial.json.bak").read_text(encoding="utf-8"))
    assert bak["menus"]["main"]["items"][0] == {"tag": "blocking"}       # the file as it was


def test_merge_with_no_matching_ring_items_leaves_radial_json_alone(merge_env):
    api, cfg = merge_env
    text = json.dumps({"menus": {"main": {"hotkey": "q", "items": [{"tag": "detailing"}]}}})
    cfg.write_text(text, encoding="utf-8")
    res = api.merge_tags("blocking", "detailing")
    assert res["ok"] and res["ring_items"] == 0 and "ring_error" not in res
    assert cfg.read_text(encoding="utf-8") == text
    assert not (cfg.parent / "radial.json.bak").exists()


def test_merge_with_an_unreadable_radial_json_does_not_write_it(merge_env):
    api, cfg = merge_env
    cfg.write_text('{"menus": {"main": {"items": [{"tag": "blocking"},]}}}', encoding="utf-8")     # a stray comma
    before = cfg.read_bytes()
    res = api.merge_tags("blocking", "detailing")
    assert res["ok"] and res["ring_items"] == 0 and "not valid JSON" in res["ring_error"]
    assert cfg.read_bytes() == before
    assert not (cfg.parent / "radial.json.bak").exists()


def test_merge_with_a_radial_json_that_is_not_an_object_does_not_write_it(merge_env):
    api, cfg = merge_env
    cfg.write_text("[1, 2]", encoding="utf-8")
    res = api.merge_tags("blocking", "detailing")
    assert "not a JSON object" in res["ring_error"] and cfg.read_text(encoding="utf-8") == "[1, 2]"


def test_merge_without_a_radial_json_is_fine(merge_env):
    api, cfg = merge_env
    res = api.merge_tags("blocking", "detailing")
    assert res["ok"] and res["ring_items"] == 0 and "ring_error" not in res
    assert not cfg.exists()


def test_a_refused_merge_does_not_touch_radial_json(merge_env):
    api, cfg = merge_env
    cfg.write_text(json.dumps(_menus()), encoding="utf-8")
    before = cfg.read_bytes()
    res = api.merge_tags("blocking", "blocking")
    assert not res["ok"] and "ring_items" not in res
    assert cfg.read_bytes() == before


def test_studios_merge_does_not_write_radial_json(tmp_path, monkeypatch):
    """Studio keeps its undoable in-editor retarget: its merge_tags is the plain mixin one."""
    import studio
    assert studio.Api.merge_tags is webapi.TagApi.merge_tags
