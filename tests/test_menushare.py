"""Sharing one menu: the pure functions of menushare and the Api methods export_menu, pick_menu_import and
apply_menu_import. Nothing here opens a window or touches the real %APPDATA%."""
import copy
import json
import os
import types

import pytest

import assets
import menushare
import tags
import webapi
from test_studio_api import _fake_webview, api   # noqa: F401  (api is a fixture)


def _cfg():
    return {
        "ring": {"radius": 200}, "bridge": {"mode": "x"}, "browser": {"hotkey": "Alt+B"},
        "menus": {
            "sculpt": {"title": "Sculpt", "hotkey": "Q", "swallow": True, "animation": "pop",
                       "items": [{"brush": "ClayBuildup"}, {"menu": "detail"}, {"tag": "rock"},
                                 {"menu": "tag:rock"}, {"menu": "ghost"}]},
            "detail": {"title": "Detail", "fan": True,
                       "items": [{"brush": "DamStandard"}, {"menu": "hard"}, {"menu": "sculpt"},
                                 {"steps": [{"alpha": "Alpha01"}, {"material": "Skin"}]}]},
            "hard": {"title": "Hard surface", "items": [{"browser": "metal"}, {"texture": "Bark"}]},
            "other": {"title": "Other", "hotkey": "W", "items": [{"brush": "Move"}]},
        },
    }


def _store(tmp_path, tag_map=None, items=None):
    raw = {"version": 1,
           "tags": tag_map if tag_map is not None else {
               "rock": {"label": "Rock", "color": "#A8DF23"}, "metal": {"label": "Metal", "color": "#112233"},
               "unused": {"label": "Unused", "color": "#445566"}},
           "items": items if items is not None else {
               "brush:claybuildup": ["rock", "unused", "favourite"], "brush:move": ["metal"],
               "alpha:alpha01": ["unused"]}}
    p = tmp_path / "tags.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    return tags.TagStore(str(p)).load()


# --- menu_slug ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Hard surface", "hard_surface"), ("Café Ünï", "cafe_uni"), ("  --a b--  ", "--a_b--"), ("!!!", "menu"),
    ("", "menu"), (None, "menu"), ("123", "m_123"), ("Sculpt 2", "sculpt_2"), ("a/b\\c", "a_b_c")])
def test_menu_slug(text, expected):
    assert menushare.menu_slug(text) == expected


# --- collect -----------------------------------------------------------------------------------------

def test_collect_follows_submenus_once_in_walk_order_and_survives_a_cycle():
    assert menushare.collect(_cfg(), "sculpt") == ["sculpt", "detail", "hard"]
    assert menushare.collect(_cfg(), "hard") == ["hard"]


def test_collect_skips_tag_ids_missing_targets_and_unknown_roots():
    cfg = _cfg()
    assert "tag:rock" not in menushare.collect(cfg, "sculpt") and "ghost" not in menushare.collect(cfg, "sculpt")
    assert menushare.collect(cfg, "nope") == []
    assert menushare.collect(cfg, "tag:rock") == []


# --- build -------------------------------------------------------------------------------------------

def test_build_holds_only_the_menus_without_hotkey_or_swallow(tmp_path):
    cfg = _cfg()
    before = copy.deepcopy(cfg)
    b = menushare.build(cfg, "sculpt", None, "0.12.0")
    assert cfg == before                                 # the editor's menus are not touched
    assert b["zorbit_menu"] == 1 and b["version"] == "0.12.0" and b["menu"] == "sculpt"
    assert list(b["menus"]) == ["sculpt", "detail", "hard"]
    assert "hotkey" not in b["menus"]["sculpt"] and "swallow" not in b["menus"]["sculpt"]
    assert b["menus"]["sculpt"]["animation"] == "pop" and b["menus"]["detail"]["fan"] is True
    assert not {"ring", "bridge", "browser", "config"} & set(b)
    assert "tags" not in b                               # no store given


def test_build_takes_the_tags_the_menus_name_and_never_favourites(tmp_path):
    b = menushare.build(_cfg(), "sculpt", _store(tmp_path), "1")
    t = b["tags"]
    assert set(t["tags"]) == {"rock", "metal"}           # "unused" is named by no item
    assert t["tags"]["rock"] == {"label": "Rock", "color": "#A8DF23"}
    assert t["items"] == {"brush:claybuildup": ["rock"], "brush:move": ["metal"]}   # filtered; Favourites out
    assert tags.TagStore.from_raw(t).has("rock")         # a tags.json-shaped dict


def test_build_leaves_out_tags_that_are_unknown_or_absent(tmp_path):
    cfg = {"menus": {"m": {"title": "M", "items": [{"tag": "nope"}, {"tag": "favourite"}, {"brush": "A"}]}}}
    assert "tags" not in menushare.build(cfg, "m", _store(tmp_path), "1")
    bad = _store(tmp_path)
    bad.error = "broken"
    assert "tags" not in menushare.build(_cfg(), "sculpt", bad, "1")


# --- plan_import -------------------------------------------------------------------------------------

def test_plan_import_keeps_free_ids_and_titles():
    menus = {"a": {"title": "Alpha", "hotkey": "Q", "swallow": False, "items": [{"menu": "b"}]},
             "b": {"title": "Beta", "items": []}}
    out, root, renames = menushare.plan_import(menus, "a", {"menus": {"x": {"title": "X"}}})
    assert list(out) == ["a", "b"] and root == "a" and renames == []
    assert "hotkey" not in out["a"] and "swallow" not in out["a"]
    assert "hotkey" in menus["a"]                        # the input is left alone


def test_plan_import_renames_a_taken_id_and_repoints_menu_items():
    menus = {"sculpt": {"title": "Fresh", "items": [{"menu": "detail"}]},
             "detail": {"title": "Zoom", "items": [{"menu": "sculpt"}]}}
    cfg = {"menus": {"sculpt": {"title": "Old"}, "sculpt_2": {"title": "Old 2"}, "detail": {"title": "x"}}}
    out, root, renames = menushare.plan_import(menus, "sculpt", cfg)
    assert root == "sculpt_3" and list(out) == ["sculpt_3", "detail_2"]
    assert out["sculpt_3"]["items"] == [{"menu": "detail_2"}] and out["detail_2"]["items"] == [{"menu": "sculpt_3"}]
    assert renames == [{"old_id": "sculpt", "id": "sculpt_3", "old_title": "Fresh", "title": "Fresh"},
                       {"old_id": "detail", "id": "detail_2", "old_title": "Zoom", "title": "Zoom"}]


def test_plan_import_gives_an_invalid_id_one_from_its_title():
    menus = {"bad id": {"title": "Café", "items": []}, "42": {"title": "", "items": []},
             "tag:x": {"title": "T", "items": []}}
    out, root, renames = menushare.plan_import(menus, "bad id", {"menus": {}})
    assert list(out) == ["cafe", "m_42", "t"] and root == "cafe"
    assert [r["id"] for r in renames] == ["cafe", "m_42", "t"]


def test_plan_import_renames_a_taken_title_case_insensitively():
    menus = {"a": {"title": " sculpt ", "items": []}, "b": {"title": "SCULPT 2", "items": []},
             "c": {"title": "Sculpt", "items": []}}
    cfg = {"menus": {"s": {"title": "Sculpt"}}}
    out, _, renames = menushare.plan_import(menus, "a", cfg)
    titles = [m["title"] for m in out.values()]
    assert titles[1] == "SCULPT 2" and titles[0].strip().endswith("2") and titles[2] == "Sculpt 3"
    assert {r["old_id"] for r in renames} == {"a", "c"}        # b kept its title: "SCULPT 2" is free


def test_plan_import_two_incoming_menus_with_one_id_cannot_clash():
    out, _, _ = menushare.plan_import({"a": {"title": "A", "items": []}}, "a", {"menus": {"a": {"title": "B"}}})
    assert list(out) == ["a_2"]


# --- missing_assets ----------------------------------------------------------------------------------

def test_missing_assets_lists_what_find_cannot_find_steps_included(monkeypatch):
    have = {("brush", "ClayBuildup"), ("alpha", "Alpha01")}

    def find(kind, name, install=None):
        return "p" if (kind, name) in have else None
    monkeypatch.setattr(assets, "find", find)
    out = menushare.missing_assets(menushare.build(_cfg(), "sculpt", None, "1")["menus"])
    assert out == {"brush": ["DamStandard"], "material": ["Skin"], "texture": ["Bark"]}


def test_missing_assets_treats_a_failing_scan_as_found(monkeypatch):
    def find(kind, name, install=None):
        raise RuntimeError("scan broke")
    monkeypatch.setattr(assets, "find", find)
    assert menushare.missing_assets({"m": {"items": [{"brush": "A"}]}}) == {}


# --- Api: export_menu --------------------------------------------------------------------------------

def _save_to(api, monkeypatch, path, seen=None):
    _fake_webview(monkeypatch)

    def dialog(*a, **k):
        if seen is not None:
            seen.update(k)
        return [str(path)] if path else None
    api._window = types.SimpleNamespace(create_file_dialog=dialog)


def test_export_menu_writes_the_file_and_says_what_went_in(api, tmp_path, monkeypatch):
    seen = {}
    _save_to(api, monkeypatch, tmp_path / "out.json", seen)
    cfg = _cfg()
    cfg["menus"]["sculpt"]["title"] = "Sc:ulpt/x"
    res = api.export_menu(cfg, "sculpt")
    assert res["ok"] and res["path"] == str(tmp_path / "out.json")
    assert res["message"] == f'Saved "Sc:ulpt/x" and its 2 submenus to {res["path"]}.'
    assert seen["save_filename"] == "Sc_ulpt_x menu.json"
    assert seen["file_types"] == ("ZOrbit menu (*.json)", "All files (*.*)")
    data = json.loads((tmp_path / "out.json").read_text(encoding="utf-8"))
    assert list(data["menus"]) == ["sculpt", "detail", "hard"] and data["version"] == studio_version()


def studio_version():
    import studio
    return studio.VERSION


def test_export_menu_message_for_none_and_one_submenu(api, tmp_path, monkeypatch):
    _save_to(api, monkeypatch, tmp_path / "a.json")
    assert api.export_menu(_cfg(), "other")["message"] == f'Saved "Other" to {tmp_path / "a.json"}.'
    cfg = _cfg()
    cfg["menus"]["hard"]["items"] = [{"menu": "other"}]
    assert 'Saved "Hard surface" and its 1 submenu to ' in api.export_menu(cfg, "hard")["message"]


def test_export_menu_refuses_unknown_and_tag_ids_and_honours_cancel(api, tmp_path, monkeypatch):
    _save_to(api, monkeypatch, tmp_path / "a.json")
    assert api.export_menu(_cfg(), "nope")["ok"] is False
    assert api.export_menu(_cfg(), "tag:rock")["ok"] is False
    assert api.export_menu("x", "sculpt")["ok"] is False
    assert not (tmp_path / "a.json").exists()
    _save_to(api, monkeypatch, None)
    res = api.export_menu(_cfg(), "sculpt")
    assert res["ok"] is False and res["cancelled"] is True


def test_export_menu_adds_the_tags_note_when_tags_json_is_broken(api, tmp_path, monkeypatch):
    (tmp_path / "tags.json").write_text("{oops", encoding="utf-8")
    monkeypatch.setenv("ZORBIT_TAGS_FILE", str(tmp_path / "tags.json"))
    _save_to(api, monkeypatch, tmp_path / "a.json")
    res = api.export_menu(_cfg(), "sculpt")
    assert res["ok"] and " The tags are not in it: " in res["message"]
    assert "tags" not in json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))


# --- Api: pick_menu_import / apply_menu_import -------------------------------------------------------

@pytest.fixture
def tagfile(tmp_path, monkeypatch):
    """The user's tags.json (webapi's store and the files read fresh) in tmp_path, holding one tag, 'mine'."""
    p = tmp_path / "tags.json"
    p.write_text(json.dumps({"version": 1, "tags": {"mine": {"label": "Mine", "color": "#010203"},
                                                    "metal": {"label": "Metal", "color": "#112233"}},
                             "items": {}}), encoding="utf-8")
    monkeypatch.setenv("ZORBIT_TAGS_FILE", str(p))
    monkeypatch.setattr(webapi, "_store", None)
    monkeypatch.setattr(webapi, "_ensured", True)       # the api fixture puts CONFIG_DIR in tmp_path: no first-run move
    return p


def _file(tmp_path, content, name="menu.json"):
    f = tmp_path / name
    f.write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
    return f


def _pick(api, monkeypatch, path, cfg):
    _fake_webview(monkeypatch)
    api._window = types.SimpleNamespace(create_file_dialog=lambda *a, **k: [str(path)])
    return api.pick_menu_import(cfg)


def _bundle(**over):
    b = {"zorbit_menu": 1, "version": "0.12.0", "menu": "sculpt",
         "menus": {"sculpt": {"title": "Sculpt", "items": [{"brush": "ClayBuildup"}, {"menu": "detail"},
                                                           {"tag": "rock"}, {"browser": "steel"}]},
                   "detail": {"title": "Detail", "fan": True, "items": [{"brush": "DamStandard"}]}},
         "tags": {"version": 1,
                  "tags": {"rock": {"label": "Rock", "color": "#A8DF23"},
                           "steel": {"label": "metal", "color": "#999999"}},
                  "items": {"brush:claybuildup": ["rock"]}}}
    b.update(over)
    return b


def test_pick_menu_import_previews_without_writing(api, tmp_path, monkeypatch, tagfile):
    monkeypatch.setattr(assets, "find", lambda kind, name, install=None: None if name == "DamStandard" else "p")
    before = tagfile.read_bytes()
    cfg = {"menus": {"sculpt": {"title": "Sculpt", "items": [{"brush": "A"}]}}}
    res = _pick(api, monkeypatch, _file(tmp_path, _bundle()), cfg)
    assert res["ok"] and res["version"] == "0.12.0" and res["path"].endswith("menu.json")
    assert res["root"] == "sculpt_2" and res["title"] == "Sculpt 2"
    assert res["menus"] == [{"id": "sculpt_2", "title": "Sculpt 2", "items": 4},
                            {"id": "detail", "title": "Detail", "items": 1}]
    assert res["renames"] == [{"old_id": "sculpt", "id": "sculpt_2", "old_title": "Sculpt", "title": "Sculpt 2"}]
    assert (res["tags"], res["new_tags"], res["tagged_items"]) == (2, 1, 1)     # metal is already there by name
    assert res["missing"] == {"brush": ["DamStandard"]}
    assert res["problems"] == []                          # "rock" comes with the file, so it is not unknown
    assert tagfile.read_bytes() == before and cfg["menus"].keys() == {"sculpt"}


def test_pick_menu_import_reports_a_tag_nobody_has(api, tmp_path, monkeypatch, tagfile):
    b = _bundle()
    del b["tags"]
    res = _pick(api, monkeypatch, _file(tmp_path, b), {"menus": {}})
    assert res["ok"] and res["tags"] == 0 and res["problems"]


def test_pick_menu_import_refuses_what_is_not_a_menu_file(api, tmp_path, monkeypatch, tagfile):
    cfg = {"menus": {}}
    settings = {"zorbit_settings": 1, "config": {"menus": {}}}
    res = _pick(api, monkeypatch, _file(tmp_path, settings, "s.json"), cfg)
    assert res == {"ok": False, "message": "s.json is a settings file, not a menu. "
                                           "Import it in Settings > Import and export."}
    res = _pick(api, monkeypatch, _file(tmp_path, {"menus": {"a": {}}}, "r.json"), cfg)
    assert "r.json is a settings file, not a menu." in res["message"]
    res = _pick(api, monkeypatch, _file(tmp_path, {"tags": {}}, "t.json"), cfg)
    assert res["message"] == "t.json is not a ZOrbit menu file."


def test_pick_menu_import_refuses_a_newer_format_and_bad_menus(api, tmp_path, monkeypatch, tagfile):
    res = _pick(api, monkeypatch, _file(tmp_path, _bundle(zorbit_menu=2, version="9.0.0")), {})
    assert res["message"] == "menu.json was made by a newer ZOrbit (9.0.0). Update ZOrbit to import it."
    for bad in ({"menus": {}}, {"menus": []}, {"menus": {"sculpt": 5}}, {"menu": "ghost"}, {"menus": None}):
        res = _pick(api, monkeypatch, _file(tmp_path, _bundle(**bad)), {})
        assert res == {"ok": False, "message": "The menu in menu.json is not valid."}, bad


def test_pick_menu_import_reports_file_problems_like_pick_import(api, tmp_path, monkeypatch, tagfile):
    res = _pick(api, monkeypatch, _file(tmp_path, "{oops"), {})
    assert res["ok"] is False and res["message"].startswith("menu.json is not valid JSON: ")
    res = _pick(api, monkeypatch, _file(tmp_path, "[1]"), {})
    assert res["message"] == "menu.json is not a ZOrbit menu file (the top level is not a JSON object)."
    (tmp_path / "bin.json").write_bytes(b"\xff\xfe\x00bad")
    assert _pick(api, monkeypatch, tmp_path / "bin.json", {})["message"] == "bin.json is not a text file."
    import studio
    monkeypatch.setattr(studio, "IMPORT_MAX_BYTES", 10)
    assert "is too big to be a ZOrbit menu file (over 0 MB)." in _pick(api, monkeypatch, _file(tmp_path, _bundle()), {})["message"]


def test_pick_menu_import_cancel(api, monkeypatch):
    _fake_webview(monkeypatch)
    api._window = types.SimpleNamespace(create_file_dialog=lambda *a, **k: None)
    assert api.pick_menu_import({}) == {"ok": False, "cancelled": True}


def test_apply_menu_import_merges_tags_retags_and_clears_the_pending_file(api, tmp_path, monkeypatch, tagfile):
    cfg = {"menus": {"sculpt": {"title": "Sculpt", "items": []}}}
    assert _pick(api, monkeypatch, _file(tmp_path, _bundle()), cfg)["ok"]
    res = api.apply_menu_import(cfg)
    assert res["ok"] and res["root"] == "sculpt_2" and res["title"] == "Sculpt 2"
    assert list(res["menus"]) == ["sculpt_2", "detail"]
    assert res["menus"]["sculpt_2"]["items"][1:] == [{"menu": "detail"}, {"tag": "rock"}, {"browser": "metal"}]
    assert res["tags_message"] == "Added 1 tag to yours; 1 joined a tag of yours with the same name."
    assert webapi.store().has("rock") and webapi.store().tags_of("brush:claybuildup") == ["rock"]
    assert "hotkey" not in res["menus"]["sculpt_2"] and res["problems"] == []
    assert res["message"] == 'Added "Sculpt 2" and its 1 submenu to the editor.'
    assert api.apply_menu_import(cfg) == {"ok": False, "message": "There is nothing to import. Pick the file again."}


def test_apply_menu_import_points_tag_items_at_the_local_key(api, tmp_path, monkeypatch, tagfile):
    b = _bundle()
    b["tags"]["tags"] = {"steel": {"label": "METAL", "color": "#999999"}}
    b["tags"]["items"] = {}
    b["menus"]["sculpt"]["items"] = [{"tag": "steel"}, {"browser": "steel"}]
    cfg = {"menus": {}}
    assert _pick(api, monkeypatch, _file(tmp_path, b), cfg)["ok"]
    res = api.apply_menu_import(cfg)
    assert res["menus"]["sculpt"]["items"] == [{"tag": "metal"}, {"browser": "metal"}]
    assert res["tags_message"] == "1 tag joined a tag of yours with the same name."


def test_apply_menu_import_plans_again_against_the_editor_as_it_is_now(api, tmp_path, monkeypatch, tagfile):
    assert _pick(api, monkeypatch, _file(tmp_path, _bundle()), {"menus": {}})["root"] == "sculpt"
    now = {"menus": {"sculpt": {"title": "Mine"}, "detail": {"title": "Detail"}}}
    res = api.apply_menu_import(now)
    assert list(res["menus"]) == ["sculpt_2", "detail_2"] and res["menus"]["sculpt_2"]["items"][1] == {"menu": "detail_2"}
    assert res["menus"]["detail_2"]["title"] == "Detail 2"


def test_apply_menu_import_without_tags_has_an_empty_tags_message(api, tmp_path, monkeypatch, tagfile):
    b = _bundle()
    del b["tags"]
    b["menus"]["sculpt"]["items"] = [{"brush": "A"}]
    assert _pick(api, monkeypatch, _file(tmp_path, b), {"menus": {}})["ok"]
    res = api.apply_menu_import({"menus": {}})
    assert res["ok"] and res["tags_message"] == "" and not os.path.exists(str(tagfile) + ".bak")


def test_apply_menu_import_still_brings_the_menus_when_the_tags_cannot_be_added(api, tmp_path, monkeypatch, tagfile):
    assert _pick(api, monkeypatch, _file(tmp_path, _bundle()), {"menus": {}})["ok"]
    monkeypatch.setattr(webapi.store(), "import_tags", lambda raw, mode: {"ok": False, "error": "disk full"})
    res = api.apply_menu_import({"menus": {}})
    assert res["ok"] and list(res["menus"]) == ["sculpt", "detail"]
    assert res["tags_message"] == "The tags were not added: disk full."


def test_a_full_round_trip_through_export_and_import(api, tmp_path, monkeypatch, tagfile):
    cfg = _cfg()
    cfg["menus"]["sculpt"]["items"] = cfg["menus"]["sculpt"]["items"][:3]
    _save_to(api, monkeypatch, tmp_path / "rt.json")
    store = tags.TagStore(str(tagfile)).load()
    store.import_tags({"tags": {"rock": {"label": "Rock", "color": "#A8DF23"}},
                       "items": {"brush:claybuildup": ["rock"]}})
    assert api.export_menu(cfg, "sculpt")["ok"]
    bundle = json.loads((tmp_path / "rt.json").read_text(encoding="utf-8"))
    assert bundle["tags"]["items"] == {"brush:claybuildup": ["rock"]}
    res = _pick(api, monkeypatch, tmp_path / "rt.json", {"menus": {}})
    assert res["ok"] and [m["id"] for m in res["menus"]] == ["sculpt", "detail", "hard"] and res["renames"] == []


def test_pick_import_refuses_a_menu_file_instead_of_replacing_every_menu(api, tmp_path, monkeypatch, tagfile):
    _fake_webview(monkeypatch)
    f = _file(tmp_path, _bundle())
    api._window = types.SimpleNamespace(create_file_dialog=lambda *a, **k: [str(f)])
    res = api.pick_import()
    assert res == {"ok": False, "message": "menu.json is a menu file, not a settings file. Import it with "
                                          "Import menu... under the Menus list."}


def test_apply_menu_import_says_so_when_every_tag_is_already_there(api, tmp_path, monkeypatch, tagfile):
    b = _bundle()
    b["tags"]["tags"] = {"mine": {"label": "Mine", "color": "#010203"}}
    b["tags"]["items"] = {}
    cfg = {"menus": {}}
    assert _pick(api, monkeypatch, _file(tmp_path, b), cfg)["ok"]
    assert api.apply_menu_import(cfg)["tags_message"] == "You already had the tags it uses."


def test_plan_import_a_submenu_label_that_showed_the_title_follows_the_rename():
    menus = {"a": {"title": "Main", "items": [{"menu": "b", "label": "Tools"}, {"menu": "b", "label": "Mine"},
                                             {"menu": "b"}]},
             "b": {"title": "Tools", "items": []}}
    out, _, _ = menushare.plan_import(menus, "a", {"menus": {"tools": {"title": "Tools"}}})
    assert out["a"]["items"] == [{"menu": "b", "label": "Tools 2"}, {"menu": "b", "label": "Mine"}, {"menu": "b"}]
    assert menus["a"]["items"][0]["label"] == "Tools"     # the input is left alone
