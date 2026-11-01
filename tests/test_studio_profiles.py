"""Studio's Api with profiles on: which profile each call reads and writes, the profile list calls, and the files a
profile can be made from. Everything lives in a throw-away config folder."""
import json
import os
import types

import pytest

import paths
import profiles
import studio
import webapi
from test_studio_api import _fake_webview, api  # noqa: F401  (api: Studio on one pinned file)


@pytest.fixture
def api_profiles(profile_env, monkeypatch):
    """An Api on a fresh profiles folder (Default made by profiles.ensure)."""
    config_dir, data_dir = profile_env
    profiles.ensure()
    monkeypatch.setattr(studio, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(studio, "STUDIO_FILE", str(config_dir / "studio.json"))
    monkeypatch.setattr(studio, "_STARTUP_LOG", str(data_dir / "studio.log"))
    monkeypatch.setattr(webapi, "_store", None)
    monkeypatch.setattr(webapi, "_usage", None)
    monkeypatch.setattr(webapi, "_pin", None)
    monkeypatch.setattr(webapi, "_ensured", True)
    return studio.Api()


def _menus():
    with open(paths.DEFAULT_MENUS, encoding="utf-8") as f:
        return json.load(f)


def _read(name):
    with open(profiles.config_file(name), encoding="utf-8") as f:
        return json.load(f)


def _edited(title):
    cfg = _menus()
    next(iter(cfg["menus"].values()))["title"] = title
    return cfg


def _title(cfg):
    return next(iter(cfg["menus"].values()))["title"]


def _dialog(api, monkeypatch, answer, seen=None):
    _fake_webview(monkeypatch)

    def dialog(*args, **kwargs):
        if seen is not None:
            seen.update(kwargs)
        return answer
    api._window = types.SimpleNamespace(create_file_dialog=dialog)


def _export(tmp_path, content, name="Studio set.json"):
    f = tmp_path / name
    f.write_text(json.dumps(content), encoding="utf-8")
    return str(f)


# --- reading ------------------------------------------------------------------------------------------

def test_get_config_reports_the_profile(api_profiles):
    res = api_profiles.get_config()
    assert res["config"] is not None
    assert res["profile"] == "Default" and res["active"] == "Default"
    assert res["profiles"] == ["Default"] and res["enabled"] is True
    assert res["path"] == profiles.config_file("Default")


def test_get_config_of_a_profile_that_is_gone(api_profiles):
    res = api_profiles.get_config("Nope")
    assert res["config"] is None and res["error"] == "Profile Nope no longer exists."
    assert api_profiles._profile is None


def test_get_profiles_is_cheap_and_complete(api_profiles):
    assert api_profiles.get_profiles() == {"ok": True, "enabled": True, "active": "Default", "editing": None,
                                           "names": ["Default"]}
    api_profiles.get_config()
    assert api_profiles.get_profiles()["editing"] == "Default"


def test_profiles_are_off_while_a_menus_file_is_pinned(api, tmp_path):
    res = api.get_config()
    assert res["enabled"] is False and res["profile"] == "Default" and res["profiles"] == ["Default"]
    assert res["path"] == profiles.config_file() == str(tmp_path / "radial.json")
    made = api.create_profile("B", "starter")
    assert made["ok"] is False and "Profiles are off" in made["message"]


# --- making, switching, saving ------------------------------------------------------------------------

def test_create_profile_lists_it_and_does_not_switch(api_profiles):
    res = api_profiles.create_profile("B", "starter")
    assert res["ok"] and res["name"] == "B" and res["message"] == "Made the profile B."
    assert res["names"] == ["B", "Default"] and res["active"] == "Default" and res["editing"] is None
    assert api_profiles.get_profiles()["names"] == ["B", "Default"]


def test_create_profile_refuses_a_bad_name_and_a_non_string(api_profiles):
    assert api_profiles.create_profile("Default", "starter")["ok"] is False
    res = api_profiles.create_profile(None, "starter")
    assert res == {"ok": False, "message": "Give the profile a name."}
    assert api_profiles.create_profile("C", "file") == {"ok": False, "message": "Pick the file first."}


def test_switch_profile_returns_its_config(api_profiles):
    api_profiles.create_profile("B", "starter")
    res = api_profiles.switch_profile("B")
    assert res["ok"] and res["profile"] == "B" and res["config"] is not None
    assert res["path"] == profiles.config_file("B") and res["active"] == "B"
    assert profiles.active() == "B"
    assert api_profiles._profile == "B"


def test_switch_to_nothing_says_so(api_profiles):
    res = api_profiles.switch_profile("Nope")
    assert res["ok"] is False and "There is no profile called Nope." in res["message"]
    assert api_profiles.switch_profile(5)["ok"] is False


def test_save_goes_back_to_the_profile_the_editor_loaded(api_profiles):
    api_profiles.get_config()                        # the editor holds Default
    api_profiles.create_profile("B", "starter")
    profiles.set_active("B")                         # another window switched meanwhile
    before = _title(_read("B"))
    res = api_profiles.save_config(_edited("Only in Default"), profile="Default")
    assert res["saved"] is True
    assert _title(_read("Default")) == "Only in Default"
    assert _title(_read("B")) == before


def test_save_without_a_name_uses_the_profile_get_config_served(api_profiles):
    api_profiles.create_profile("B", "starter")
    api_profiles.get_config("B")
    assert api_profiles.save_config(_edited("In B"))["saved"] is True
    assert _title(_read("B")) == "In B"
    assert _title(_read("Default")) != "In B"


def test_recovery_calls_follow_the_profile_the_editor_holds(api_profiles):
    api_profiles.create_profile("B", "starter")
    api_profiles.get_config("B")
    api_profiles.save_config(_edited("One"))
    api_profiles.save_config(_edited("Two"))
    assert _title(json.loads(open(profiles.config_file("B") + ".bak", encoding="utf-8").read())) == "One"
    assert api_profiles.restore_backup()["ok"] is True
    assert _title(_read("B")) == "One"
    assert api_profiles.reset_config()["ok"] is True
    assert _read("B") == _menus() and _title(_read("Default")) == _title(_menus())


# --- a profile that goes away or changes name ----------------------------------------------------------

def test_delete_the_profile_being_edited_asks_for_a_reload(api_profiles):
    api_profiles.create_profile("B", "starter")
    api_profiles.get_config("Default")
    res = api_profiles.delete_profile("Default")
    assert res["ok"] and res["reload"] is True and res["editing"] is None
    assert res["names"] == ["B"] and res["active"] == "B"
    assert "profiles\\.deleted" in res["message"] and "30 days" in res["message"]
    assert api_profiles.get_config()["profile"] == "B"


def test_save_to_a_deleted_profile_writes_nothing(api_profiles):
    api_profiles.create_profile("B", "starter")
    api_profiles.get_config("Default")
    api_profiles.delete_profile("Default")
    res = api_profiles.save_config(_edited("Late"), profile="Default")
    assert res["saved"] is False and res["profile_missing"] is True
    assert "Default no longer exists" in res["message"]
    assert not os.path.exists(profiles.profile_dir("Default"))
    assert api_profiles.restore_backup(profile="Default")["ok"] is False
    assert api_profiles.reset_config(profile="Default")["ok"] is False
    assert profiles.names() == ["B"]


def test_deleting_another_profile_leaves_the_editor_alone(api_profiles):
    api_profiles.create_profile("B", "starter")
    api_profiles.get_config("Default")
    res = api_profiles.delete_profile("B")
    assert res["ok"] and res["reload"] is False and res["editing"] == "Default"
    assert api_profiles.delete_profile("Default")["ok"] is False        # the last one stays


def test_rename_moves_the_pointer_and_the_editor(api_profiles):
    api_profiles.create_profile("B", "starter")
    api_profiles.switch_profile("B")
    res = api_profiles.rename_profile("B", "Work")
    assert res["ok"] and res["name"] == "Work" and res["message"] == "Renamed B to Work."
    assert res["names"] == ["Default", "Work"] and res["active"] == "Work" and res["editing"] == "Work"
    assert profiles.active() == "Work"
    assert api_profiles.save_config(_edited("Renamed"))["saved"] is True
    assert _title(_read("Work")) == "Renamed"
    assert webapi._pin == "Work"


def test_rename_of_another_profile_keeps_editing(api_profiles):
    api_profiles.create_profile("B", "starter")
    api_profiles.get_config("Default")
    res = api_profiles.rename_profile("B", "Work")
    assert res["editing"] == "Default" and res["names"] == ["Default", "Work"]
    assert api_profiles.rename_profile("Nope", "X")["ok"] is False
    assert api_profiles.rename_profile("Work", 3)["ok"] is False


# --- the tags and usage follow the editor --------------------------------------------------------------

def test_the_stores_follow_the_profile_the_editor_holds(api_profiles):
    api_profiles.create_profile("B", "starter")
    api_profiles.get_config("B")
    assert webapi.store().path == profiles.tags_file("B")
    assert webapi.usage_store().path == profiles.usage_file("B")
    assert api_profiles._tags_path() == profiles.tags_file("B")
    api_profiles.get_config("Default")
    assert webapi.store().path == profiles.tags_file("Default")


# --- imports are for one profile -----------------------------------------------------------------------

def test_apply_import_refuses_a_file_read_for_another_profile(api_profiles):
    api_profiles.get_config()
    api_profiles._pending_import = {"path": "x.json", "kind": "config", "config": _menus(), "tags": None,
                                    "profile": "Other"}
    res = api_profiles.apply_import()
    assert res["ok"] is False and res["message"] == "The profile changed. Pick the file again."
    assert res["config"] is None and res["problems"] == [] and res["tags_message"] == ""


def test_apply_menu_import_refuses_a_file_read_for_another_profile(api_profiles):
    api_profiles.get_config()
    api_profiles._pending_menu_import = {"path": "x.json", "menus": {"a": {"items": []}}, "root": "a", "tags": None,
                                         "profile": "Other"}
    res = api_profiles.apply_menu_import(_menus())
    assert res == {"ok": False, "message": "The profile changed. Pick the file again."}


def test_pick_import_stamps_the_profile_and_a_switch_clears_it(api_profiles, tmp_path, monkeypatch):
    api_profiles.create_profile("B", "starter")
    api_profiles.get_config("Default")
    _dialog(api_profiles, monkeypatch, [_export(tmp_path, _menus(), "radial.json")])
    assert api_profiles.pick_import()["ok"]
    assert api_profiles._pending_import["profile"] == "Default"
    api_profiles.switch_profile("B")
    assert api_profiles._pending_import is None


# --- making a profile from a file ----------------------------------------------------------------------

def _tags_section():
    return {"version": 1, "tags": {"metal": {"label": "Metal", "color": "#112233"}}, "items": {}}


def test_a_settings_export_becomes_a_profile(api_profiles, tmp_path, monkeypatch):
    export = _export(tmp_path, {"zorbit_settings": 1, "version": "1.2.3", "config": _edited("From a file"),
                                "tags": _tags_section()}, "My: set?.json")
    _dialog(api_profiles, monkeypatch, [export])
    res = api_profiles.pick_profile_file()
    assert res["ok"] and res["path"] == export and res["name"] == "My set"
    assert res["menus"] == len(_menus()["menus"]) and res["has_tags"] is True
    assert res["tags"] == 2 and res["version"] == "1.2.3"           # Metal and the built-in Favourites
    made = api_profiles.create_profile("Imported", "file")
    assert made["ok"] and made["names"] == ["Default", "Imported"]
    assert _title(_read("Imported")) == "From a file"
    tags_json = json.loads(open(profiles.tags_file("Imported"), encoding="utf-8").read())
    assert "metal" in tags_json["tags"]
    assert api_profiles._pending_profile_file is None
    assert api_profiles.create_profile("Again", "file")["message"] == "Pick the file first."


def test_a_plain_radial_json_becomes_a_profile_without_tags(api_profiles, tmp_path, monkeypatch):
    _dialog(api_profiles, monkeypatch, [_export(tmp_path, _menus(), "radial.json")])
    res = api_profiles.pick_profile_file()
    assert res["ok"] and res["name"] == "radial" and res["has_tags"] is False and res["tags"] == 0
    assert api_profiles.create_profile("Plain", "file")["ok"]
    assert not os.path.exists(profiles.tags_file("Plain"))


def test_the_offered_name_is_free(api_profiles, tmp_path, monkeypatch):
    _dialog(api_profiles, monkeypatch, [_export(tmp_path, _menus(), "Default.json")])
    assert api_profiles.pick_profile_file()["name"] == "Default 2"
    _dialog(api_profiles, monkeypatch, [_export(tmp_path, _menus(), "CON.json")])
    assert api_profiles.pick_profile_file()["name"] == "Imported"


def test_a_menu_file_cannot_become_a_profile(api_profiles, tmp_path, monkeypatch):
    _dialog(api_profiles, monkeypatch, [_export(tmp_path, {"zorbit_menu": 1, "menu": "a", "menus": {}}, "m.json")])
    res = api_profiles.pick_profile_file()
    assert res["ok"] is False
    assert "m.json is a menu file, not a settings file. Import it with Import menu... under the Menus list." \
        == res["message"]


def test_a_tags_only_file_cannot_become_a_profile(api_profiles, tmp_path, monkeypatch):
    _dialog(api_profiles, monkeypatch, [_export(tmp_path, _tags_section(), "tags.json")])
    res = api_profiles.pick_profile_file()
    assert res == {"ok": False, "message": "tags.json has no menus in it, so it cannot become a profile."}
    assert api_profiles._pending_profile_file is None


def test_cancelling_the_profile_file_dialog(api_profiles, monkeypatch):
    _dialog(api_profiles, monkeypatch, None)
    assert api_profiles.pick_profile_file() == {"ok": False, "cancelled": True}


# --- folders and export --------------------------------------------------------------------------------

def test_open_folder_profiles_and_config(api_profiles, monkeypatch):
    opened = []
    monkeypatch.setattr(studio.os, "startfile", opened.append, raising=False)
    api_profiles.create_profile("B", "starter")
    assert api_profiles.open_folder("profiles") is True
    api_profiles.get_config("B")
    api_profiles.open_folder("config")
    api_profiles.open_folder("app")
    assert opened == [profiles.root(), profiles.profile_dir("B"), profiles.profile_dir("B")]


def test_export_names_the_profile(api_profiles, tmp_path, monkeypatch):
    api_profiles.create_profile("Work", "starter")
    api_profiles.get_config("Work")
    seen = {}
    target = tmp_path / "out.json"
    _dialog(api_profiles, monkeypatch, [str(target)], seen)
    res = api_profiles.export_settings(_menus())
    assert res["ok"] and "this profile's menus, settings and tags" in res["message"]
    assert seen["save_filename"].startswith("ZOrbit Work ") and seen["save_filename"].endswith(".json")
    assert json.loads(target.read_text(encoding="utf-8"))["config"] == _menus()
