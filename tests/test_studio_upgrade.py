"""Studio's Api around an upgrade: files made by a newer ZOrbit, an older app still running, and the files an older
version left at the old places. Everything lives in a throw-away config folder."""
import json
import os

import pytest

import paths
import profiles
import studio
from test_studio_api import _Proc, api  # noqa: F401  (api: Studio on one pinned file)
from test_studio_profiles import _edited, _read, _title, api_profiles  # noqa: F401


# --- files made by a newer ZOrbit ---------------------------------------------------------------------

@pytest.fixture
def newer(api_profiles):
    """api_profiles after a ZOrbit 9.9.9 stamped the profiles folder with a format this build does not know."""
    with open(profiles.stamp_file(), "w", encoding="utf-8") as f:
        json.dump({"format": 2, "version": "9.9.9"}, f)
    profiles._forget()
    return api_profiles


def test_get_config_of_newer_files_reads_nothing(newer):
    res = newer.get_config()
    assert res["config"] is None and res["too_new"] is True
    assert "9.9.9" in res["error"] and res["error"] == profiles.too_new()
    assert res["profile"] == "Default" and res["profiles"] == ["Default"] and res["enabled"] is True
    assert newer._profile is None                         # nothing was pinned


def test_save_config_refuses_newer_files(newer):
    path = profiles.config_file("Default")
    before = open(path, "rb").read()
    res = newer.save_config(_edited("Changed"))
    assert res["saved"] is False and res["too_new"] is True and "9.9.9" in res["message"]
    assert open(path, "rb").read() == before
    assert not os.path.exists(path + ".bak")


def test_reset_and_restore_refuse_newer_files(newer):
    path = profiles.config_file("Default")
    with open(path + ".bak", "wb") as f:
        f.write(b'{"menus": {}}')
    before = open(path, "rb").read()
    for res in (newer.reset_config(), newer.restore_backup()):
        assert res["ok"] is False and res["too_new"] is True and "9.9.9" in res["message"]
    assert open(path, "rb").read() == before
    assert not os.path.exists(path + ".broken")


def test_profile_actions_surface_the_newer_files_message(newer):
    msg = profiles.too_new()
    assert newer.create_profile("Other", "starter") == {"ok": False, "message": msg}
    assert newer.rename_profile("Default", "Renamed") == {"ok": False, "message": msg}
    assert newer.delete_profile("Default") == {"ok": False, "message": msg}
    assert newer.switch_profile("Default") == {"ok": False, "message": msg}
    assert profiles.names() == ["Default"]


def test_imports_and_tag_writes_refuse_newer_files(newer):
    res = newer.apply_import()
    assert res["ok"] is False and res["too_new"] is True and res["config"] is None
    res = newer.apply_menu_import({"menus": {}})
    assert res["ok"] is False and res["too_new"] is True
    res = newer.create_tag("Mine")
    assert res["ok"] is False and res["too_new"] is True and "9.9.9" in res["error"]
    assert newer.tag_items(["brush:standard"], add=["favourite"])["ok"] is False
    assert newer.set_favourite_order("brush", ["standard"])["ok"] is False
    assert not os.path.exists(profiles.tags_file("Default"))


# --- an older app still running -----------------------------------------------------------------------

def _app(monkeypatch, version):
    """W.running_app answers a ZOrbit app of this version (None: no app, or its version is unknown)."""
    monkeypatch.setattr(studio.W, "running_app", lambda: (1, 2, version) if version else None, raising=False)


def test_get_status_tells_an_older_app(api, monkeypatch):
    monkeypatch.setattr(studio, "_mutex_exists", lambda name: True)
    cases = ((paths.VERSION, False), ("0.0.1", True), ("99.0.0", False), (None, False))
    for version, older in cases:
        _app(monkeypatch, version)
        res = api.get_status()
        assert res["app_version"] == version and res["app_older"] is older


def test_get_status_survives_running_app_failing(api, monkeypatch):
    def boom():
        raise OSError("gone")
    monkeypatch.setattr(studio.W, "running_app", boom, raising=False)
    res = api.get_status()
    assert res["app_version"] is None and res["app_older"] is False


@pytest.fixture
def launched(api, monkeypatch):
    """start_app with the app's mutex present and Popen counted; returns the list of Popen calls."""
    calls = []
    monkeypatch.setattr(studio, "_mutex_exists", lambda name: True)
    monkeypatch.setattr(studio, "_zbrush_running", lambda: (True, True))
    monkeypatch.setattr(studio, "START_WAIT", 0.3)
    monkeypatch.setattr(studio.time, "sleep", lambda s: None)
    monkeypatch.setattr(paths, "launch_commands", lambda: {"app": ["fake"]})
    monkeypatch.setattr(paths, "clean_env", lambda: {})
    monkeypatch.setattr(studio.subprocess, "Popen", lambda *a, **k: calls.append(a) or _Proc(True))
    return calls


def test_start_app_replaces_an_older_app(api, launched, monkeypatch):
    seen = iter(["0.0.1", "0.0.1", paths.VERSION])         # the old one, still the old one, then the new one

    monkeypatch.setattr(studio.W, "running_app", lambda: (1, 2, next(seen, paths.VERSION)), raising=False)
    res = api.start_app()
    assert len(launched) == 1
    assert res["ok"] is True and res["restarted"] is True and res["was"] == "0.0.1"


def test_start_app_says_when_the_older_app_does_not_make_way(api, launched, monkeypatch):
    _app(monkeypatch, "0.0.1")
    res = api.start_app()
    assert len(launched) == 1
    assert res["ok"] is False and not res.get("restarted")
    assert res["message"] == ("The older app did not make way. Quit it from its tray icon and press Start app "
                              "again.")


@pytest.mark.parametrize("version", [paths.VERSION, "99.0.0", None])
def test_start_app_leaves_a_current_or_unknown_app_alone(api, launched, monkeypatch, version):
    _app(monkeypatch, version)
    res = api.start_app()
    assert launched == []
    assert res["ok"] is True and res["running"] is True and "restarted" not in res


# --- files an older version left at the old places ----------------------------------------------------

def _tags_raw(extra=True):
    tags = {"favourite": {"label": "Favourites", "color": "#FFD166"},
            "blocking": {"label": "Blocking", "color": "#A8DF23"},
            "detailing": {"label": "Detailing", "color": "#C77DFF"}}
    if extra:
        tags["sculpt"] = {"label": "Sculpt", "color": "#4DC8E9"}
    return {"version": 1, "tags": tags, "items": {"brush:standard": ["sculpt"]} if extra else {}}


@pytest.fixture
def stray_env(api_profiles):
    """api_profiles with an edited radial.json and a tags.json with one tag of its own at the old root place."""
    root = paths.CONFIG_DIR
    with open(os.path.join(root, "radial.json"), "w", encoding="utf-8") as f:
        json.dump(_edited("My old menus"), f)
    with open(os.path.join(root, "tags.json"), "w", encoding="utf-8") as f:
        json.dump(_tags_raw(), f)
    return api_profiles, root


def _aside(root):
    base = os.path.join(root, "pre-profiles")
    return sorted(os.listdir(base)) if os.path.isdir(base) else []


def test_get_strays_counts_the_old_files(stray_env):
    api, root = stray_env
    res = api.get_strays()
    assert res["found"] is True
    assert res["menus"] == len(_edited("x")["menus"])
    assert res["tags"] == 3                                # Blocking, Detailing and Sculpt, not Favourites
    assert res["when"] == pytest.approx(os.stat(os.path.join(root, "radial.json")).st_mtime, abs=5)
    assert res["name"] == "From an older version"


def test_get_strays_finds_nothing_on_a_clean_install(api_profiles):
    res = api_profiles.get_strays()
    assert res == {"found": False, "menus": None, "tags": None, "when": None,
                   "name": "From an older version"}


def test_get_strays_offers_a_name_nobody_has(stray_env):
    api, _ = stray_env
    profiles.create("From an older version", "empty")
    assert api.get_strays()["name"] == "From an older version 2"


def test_adopt_strays_makes_a_profile_and_sets_the_files_aside(stray_env):
    api, root = stray_env
    res = api.adopt_strays("profile", "Old")
    assert res["ok"] is True and res["name"] == "Old" and "Old" in res["names"]
    assert res["active"] == "Default" and res["message"] == "Made the profile Old."
    assert _title(_read("Old")) == "My old menus"
    assert not os.path.exists(os.path.join(root, "radial.json"))
    assert not os.path.exists(os.path.join(root, "tags.json"))
    [stamped] = _aside(root)
    assert sorted(os.listdir(os.path.join(root, "pre-profiles", stamped))) == ["radial.json", "tags.json"]
    assert api.get_strays()["found"] is False


def test_adopt_strays_names_the_profile_itself_when_not_given_one(stray_env):
    api, _ = stray_env
    res = api.adopt_strays("profile")
    assert res["ok"] is True and res["name"] == "From an older version"
    assert profiles.exists("From an older version")


def test_adopt_strays_aside_moves_the_files_and_makes_no_profile(stray_env):
    api, root = stray_env
    res = api.adopt_strays("aside")
    assert res["ok"] is True
    assert os.path.dirname(res["folder"]) == os.path.join(root, "pre-profiles")
    assert sorted(os.listdir(res["folder"])) == ["radial.json", "tags.json"]
    assert not os.path.exists(os.path.join(root, "radial.json"))
    assert profiles.names() == ["Default"]
    assert api.get_strays()["found"] is False


def test_adopt_strays_answers_plainly_when_it_cannot(api_profiles):
    assert api_profiles.adopt_strays("aside")["ok"] is False
    res = api_profiles.adopt_strays("profile", "Old")
    assert res["ok"] is False and "older version" in res["message"]
    assert api_profiles.adopt_strays("burn")["ok"] is False
    assert profiles.names() == ["Default"]


def test_adopt_strays_reports_a_bad_profile_name(stray_env):
    api, root = stray_env
    res = api.adopt_strays("profile", "a/b")
    assert res["ok"] is False and res["message"]
    assert os.path.exists(os.path.join(root, "radial.json"))     # nothing was moved
    assert api.adopt_strays("profile", 5)["ok"] is False


def test_open_folder_opens_pre_profiles(api_profiles, monkeypatch):
    opened = []
    monkeypatch.setattr(studio.os, "startfile", opened.append, raising=False)
    assert api_profiles.open_folder("pre-profiles") is True
    assert opened == [os.path.join(paths.CONFIG_DIR, "pre-profiles")]
    assert os.path.isdir(opened[0])
