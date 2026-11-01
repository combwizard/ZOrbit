"""Studio's Api against a temporary radial.json: backups, the start check, the setup fallback, added ZBrush folders
and the import numbers. Nothing here opens a window or touches the real %APPDATA%."""
import json
import os
import types

import pytest

import fsutil
import paths
import studio
import theme


@pytest.fixture
def api(tmp_path, monkeypatch):
    """An Api whose radial.json, studio.json and logs live in tmp_path."""
    cfg = tmp_path / "radial.json"
    cfg.write_bytes(open(paths.DEFAULT_MENUS, "rb").read())
    monkeypatch.setenv("ZORBIT_CONFIG_FILE", str(cfg))      # profiles off: one pinned file
    monkeypatch.setattr(studio, "STUDIO_FILE", str(tmp_path / "studio.json"))
    monkeypatch.setattr(studio, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(studio, "_STARTUP_LOG", str(tmp_path / "studio.log"))
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path))
    return studio.Api()


def _default():
    with open(paths.DEFAULT_MENUS, encoding="utf-8") as f:
        return json.load(f)


# --- A: files that would be overwritten are kept -----------------------------------------------------

def test_restore_backup_keeps_the_file_it_replaces(api, tmp_path):
    (tmp_path / "radial.json.bak").write_text('{"menus": {"a": 1}}', encoding="utf-8")
    (tmp_path / "radial.json").write_text('{"menus": {"mine": 2}}', encoding="utf-8")
    res = api.restore_backup()
    assert res["ok"] and res["kept_broken"]
    assert "radial.json.broken" in res["message"]
    assert (tmp_path / "radial.json").read_text(encoding="utf-8") == '{"menus": {"a": 1}}'
    assert (tmp_path / "radial.json.broken").read_text(encoding="utf-8") == '{"menus": {"mine": 2}}'
    assert (tmp_path / "radial.json.bak").exists()


def test_restore_backup_skips_broken_when_identical_or_missing(api, tmp_path):
    (tmp_path / "radial.json.bak").write_text('{"menus": {}}', encoding="utf-8")
    (tmp_path / "radial.json").write_text('{"menus": {}}', encoding="utf-8")
    res = api.restore_backup()
    assert res["ok"] and not res["kept_broken"] and "broken" not in res["message"]
    assert not (tmp_path / "radial.json.broken").exists()
    (tmp_path / "radial.json").unlink()
    res = api.restore_backup()
    assert res["ok"] and not res["kept_broken"]
    assert not (tmp_path / "radial.json.broken").exists()


def test_save_config_keeps_a_file_that_is_not_json_as_broken(api, tmp_path):
    (tmp_path / "radial.json.bak").write_text('{"good": true}', encoding="utf-8")
    (tmp_path / "radial.json").write_text('{"menus": {oops', encoding="utf-8")
    res = api.save_config(_default())
    assert res["saved"] and res["kept_broken"]
    assert (tmp_path / "radial.json.broken").read_text(encoding="utf-8") == '{"menus": {oops'
    assert (tmp_path / "radial.json.bak").read_text(encoding="utf-8") == '{"good": true}'   # the backup stays
    json.loads((tmp_path / "radial.json").read_text(encoding="utf-8"))


def test_save_config_of_a_valid_file_makes_a_backup_not_a_broken(api, tmp_path):
    cfg = _default()
    cfg["ring"] = dict(cfg.get("ring") or {}, size=300)
    res = api.save_config(cfg)
    assert res["saved"] and not res["kept_broken"]
    assert (tmp_path / "radial.json.bak").exists()
    assert not (tmp_path / "radial.json.broken").exists()


def test_save_config_reports_text_it_cannot_write_and_leaves_no_tmp(api, tmp_path):
    before = (tmp_path / "radial.json").read_bytes()
    cfg = _default()
    cfg["menus"][next(iter(cfg["menus"]))]["title"] = "bad \ud800 character"
    res = api.save_config(cfg)
    assert not res["saved"] and res["message"].startswith("Could not save: ")
    assert (tmp_path / "radial.json").read_bytes() == before
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]


def test_save_config_reports_a_value_that_is_not_json(api, tmp_path):
    cfg = _default()
    cfg["loop"] = cfg                                   # circular
    res = api.save_config(cfg, allow_unusable=True)
    assert not res["saved"] and res["message"].startswith("Could not save: ")
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".tmp")]


def test_write_atomic_removes_its_tmp_when_the_text_cannot_be_encoded(tmp_path):
    target = tmp_path / "x.json"
    with pytest.raises(UnicodeEncodeError):
        fsutil.write_atomic(str(target), "\ud800")
    assert not target.exists()
    assert os.listdir(tmp_path) == []


# --- D: start_app waits, and tells slow from failed ---------------------------------------------------

class _Proc:
    def __init__(self, alive, on_start=None):
        self._alive = alive
        if on_start:
            on_start()

    def poll(self):
        return None if self._alive else 1


@pytest.fixture
def launch(api, tmp_path, monkeypatch):
    monkeypatch.setattr(studio, "_mutex_exists", lambda name: False)
    monkeypatch.setattr(studio, "_zbrush_running", lambda: (True, True))
    monkeypatch.setattr(studio, "START_WAIT", 0.3)
    monkeypatch.setattr(studio.time, "sleep", lambda s: None)
    monkeypatch.setattr(paths, "launch_commands", lambda: {"app": ["fake"]})
    monkeypatch.setattr(paths, "clean_env", lambda: {})

    def start(alive, writes=None):
        def on_start():
            if writes:
                with open(tmp_path / "radiald.log", "a", encoding="utf-8") as f:
                    f.write(writes)
        monkeypatch.setattr(studio.subprocess, "Popen", lambda *a, **k: _Proc(alive, on_start))
        return api.start_app()
    return start


def test_start_app_still_starting_when_the_process_is_alive(launch):
    res = launch(alive=True)
    assert res["ok"] is False and res["starting"] is True
    assert "still starting" in res["message"] and "Status turns green" in res["message"]


def test_start_app_failure_shows_only_lines_from_this_launch(launch, tmp_path):
    (tmp_path / "radiald.log").write_text("old line 1\nold line 2\n", encoding="utf-8")
    res = launch(alive=False, writes="new line\nboom\n")
    assert res["ok"] is False and not res.get("starting") and res["reason"] == "failed"
    assert res["lines"] == ["new line", "boom"] and res["log"] == res["lines"]
    assert "did not start" in res["message"]


def test_start_app_failure_with_nothing_written_has_no_old_lines(launch, tmp_path):
    (tmp_path / "radiald.log").write_text("old line\n", encoding="utf-8")
    res = launch(alive=False)
    assert res["lines"] == []


def test_start_app_succeeds_when_the_mutex_appears(launch, monkeypatch):
    calls = iter([False, False, True])                   # not running, then still not, then up
    monkeypatch.setattr(studio, "_mutex_exists", lambda name: next(calls, True))
    res = launch(alive=True)
    assert res["ok"] and res["running"]


# --- F: a failed setup check is not "nothing found" -------------------------------------------------

def test_get_setup_failure_has_an_error_and_no_installs(api, monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("registry exploded")
    monkeypatch.setattr(studio.onboarding, "snapshot", boom)
    monkeypatch.setattr(api, "_all_installs", lambda: [])
    monkeypatch.setattr(api, "_status_extras", lambda: ("auto", False))
    monkeypatch.setattr(studio, "_mutex_exists", lambda name: False)
    res = api.get_setup()
    assert res["error"] == "The setup check failed: registry exploded (see studio.log)"
    assert res["failed"] is True
    assert "installs" not in res
    assert "RuntimeError" in (tmp_path / "studio.log").read_text(encoding="utf-8")


# --- G: added ZBrush folders -------------------------------------------------------------------------

def _zbrush(tmp_path, name, python=False):
    d = tmp_path / name
    d.mkdir()
    (d / "ZBrush.exe").write_bytes(b"")
    if python:
        (d / "python312.dll").write_bytes(b"")
    return str(d)


def _fake_webview(monkeypatch):
    import sys
    fd = types.SimpleNamespace(FOLDER=1, OPEN=2, SAVE=3)
    monkeypatch.setitem(sys.modules, "webview", types.SimpleNamespace(FileDialog=fd))


def test_add_zbrush_folder_accepts_a_2026_folder(api, tmp_path, monkeypatch):
    _fake_webview(monkeypatch)
    folder = _zbrush(tmp_path, "ZBrush 2026", python=True)
    api._window = types.SimpleNamespace(create_file_dialog=lambda *a, **k: [folder])
    monkeypatch.setattr(api, "_scanned_installs", lambda: [])
    res = api.add_zbrush_folder()
    assert res["ok"] and res["python"] is True and "Added" in res["message"]
    listed = api._all_installs()
    assert [e["path"] for e in listed] == [os.path.normpath(folder)]
    assert listed[0]["added"] and listed[0]["python"]
    assert api.add_zbrush_folder()["already"] is True


def test_add_zbrush_folder_still_refuses_what_is_not_zbrush(api, tmp_path, monkeypatch):
    _fake_webview(monkeypatch)
    (tmp_path / "Other").mkdir()
    api._window = types.SimpleNamespace(create_file_dialog=lambda *a, **k: [str(tmp_path / "Other")])
    res = api.add_zbrush_folder()
    assert res["ok"] is False and "No ZBrush.exe" in res["message"]


def test_known_legacy_falls_back_to_the_folder_itself(api, tmp_path, monkeypatch):
    monkeypatch.setattr(api, "_scanned_installs", lambda: [])
    old = _zbrush(tmp_path, "ZBrush 2024")
    assert api._known_legacy(old)["year"] == 2024
    assert api._known_legacy(_zbrush(tmp_path, "ZBrush 2026", python=True)) is None   # has the Python API
    assert api._known_legacy(_zbrush(tmp_path, "ZBrush 2021")) is None               # too old
    assert api._known_legacy(str(tmp_path / "nowhere")) is None
    assert api._known_legacy("") is None and api._known_legacy(None) is None
    assert api.install_zscript_bridge(str(tmp_path / "nowhere"))["ok"] is False


# --- H: numbers for the import message ---------------------------------------------------------------

def _pick(api, tmp_path, monkeypatch, content):
    _fake_webview(monkeypatch)
    f = tmp_path / "in.json"
    f.write_text(json.dumps(content), encoding="utf-8")
    api._window = types.SimpleNamespace(create_file_dialog=lambda *a, **k: [str(f)])
    return api.pick_import()


def test_pick_import_counts_menus_and_tags(api, tmp_path, monkeypatch):
    cfg = _default()
    bundle = {"zorbit_settings": 1, "version": "1.0.0", "config": cfg,
              "tags": {"version": 1, "tags": {"rock": {"label": "Rock", "color": "#112233"}}, "items": {}}}
    res = _pick(api, tmp_path, monkeypatch, bundle)
    assert res["ok"] and res["menus"] == len(cfg["menus"]) and res["has_tags"] and res["tags"] == 1
    assert res["current_menus"] == len(cfg["menus"])
    assert res["current_tags"] >= 1                      # Favourites is always there


def test_pick_import_a_favourites_only_tags_object_counts_as_tags(api, tmp_path, monkeypatch):
    raw = {"version": 1, "tags": {"favourite": {"label": "Favourites", "color": "#FFD166"}},
           "items": {"brush:standard": ["favourite"]}}
    res = _pick(api, tmp_path, monkeypatch, raw)
    assert res["ok"] and res["has_tags"] and res["tags"] == 1 and res["menus"] == 0


def test_pick_import_an_empty_tags_object_is_not_tags(api, tmp_path, monkeypatch):
    res = _pick(api, tmp_path, monkeypatch, {"zorbit_settings": 1, "config": _default(), "tags": {"tags": {}}})
    assert res["ok"] and not res["has_tags"] and res["tags"] == 0
    assert api.apply_import("merge")["ok"]               # the file is menus only: no tag error on the way


# --- C: the first window fits the screen -------------------------------------------------------------

def test_fit_size_shrinks_to_a_laptop_work_area_and_keeps_big_screens():
    assert studio._fit_size(1920, 1040, 1.5) == {"width": 1264, "height": 677}
    assert studio._fit_size(3840, 2100, 1.0) == {"width": 1320, "height": 860}
    assert studio._fit_size(800, 400, 1.0) == {"width": 980, "height": 560}      # never below the minimum


# --- B: a session end is not vetoed ------------------------------------------------------------------

def test_closing_during_a_session_end_is_let_through(api, monkeypatch):
    monkeypatch.setattr(studio, "_remember_window", lambda hwnd: None)
    monkeypatch.setattr(api, "_hwnd", lambda: 1)
    api._on_query_end()
    assert studio._on_closing(api) is True
    api._on_end_session(False)                           # cancelled: closes are asked about again
    assert api._session_ending is False


def test_a_preference_is_not_saved_over_an_unreadable_studio_file(api, tmp_path):
    f = tmp_path / "studio.json"
    f.write_text('{"window": {"x": 1}, "zbrush_folders": ["D:/ZB"], "check_updates": false,', encoding="utf-8")
    before = f.read_bytes()
    api.set_pref("last_screen", "library")
    assert f.read_bytes() == before                       # a {} written back would lose all of it


def test_a_preference_is_saved_when_studio_json_is_missing_or_fine(api, tmp_path):
    api.set_pref("last_screen", "library")
    assert json.loads((tmp_path / "studio.json").read_text(encoding="utf-8"))["last_screen"] == "library"
    api.set_pref("check_updates", False)
    data = json.loads((tmp_path / "studio.json").read_text(encoding="utf-8"))
    assert data["last_screen"] == "library" and data["check_updates"] is False


def test_the_browser_state_is_not_saved_over_an_unreadable_file(tmp_path, monkeypatch):
    import popout
    f = tmp_path / "popout.json"
    f.write_text('{"window": [1, 2, 3, 4], "side": "right",', encoding="utf-8")
    monkeypatch.setattr(popout, "STATE_FILE", str(f))
    before = f.read_bytes()
    popout._update_state(kind="alpha")
    assert f.read_bytes() == before
    f.write_text('{"side": "right"}', encoding="utf-8")
    popout._update_state(kind="alpha")
    assert json.loads(f.read_text(encoding="utf-8")) == {"side": "right", "kind": "alpha"}


# --- What's new: seen_version and the sections the dialog shows ----------------------------------------

def _studio_json(tmp_path):
    return json.loads((tmp_path / "studio.json").read_text(encoding="utf-8"))


def test_seen_version_is_this_version_on_a_fresh_install(api, tmp_path):
    prefs = api.get_prefs()
    assert prefs["setup_done"] is False
    assert prefs["seen_version"] == paths.VERSION
    assert _studio_json(tmp_path)["seen_version"] == paths.VERSION


def test_seen_version_is_empty_for_an_existing_user(api, tmp_path):
    (tmp_path / "studio.json").write_text('{"last_screen": "library"}', encoding="utf-8")
    assert api.get_prefs()["seen_version"] == ""
    assert _studio_json(tmp_path)["seen_version"] == ""


def test_set_pref_takes_a_string_seen_version(api):
    api.set_pref("seen_version", "0.11.0")
    assert api.get_prefs()["seen_version"] == "0.11.0"
    api.set_pref("seen_version", 12)                      # not a string: ignored
    assert api.get_prefs()["seen_version"] == "0.11.0"


def test_tour_seen_is_false_on_a_fresh_install(api, tmp_path):
    assert api.get_prefs()["tour_seen"] is False
    assert _studio_json(tmp_path)["tour_seen"] is False


def test_tour_seen_is_true_for_an_existing_user(api, tmp_path):
    (tmp_path / "studio.json").write_text('{"last_screen": "library"}', encoding="utf-8")
    assert api.get_prefs()["tour_seen"] is True
    assert _studio_json(tmp_path)["tour_seen"] is True


def test_tour_seen_is_false_when_setup_was_not_done(api, tmp_path):
    (tmp_path / "studio.json").write_text('{"setup_done": false}', encoding="utf-8")
    assert api.get_prefs()["tour_seen"] is False
    assert _studio_json(tmp_path)["tour_seen"] is False


def test_tour_seen_is_true_when_setup_was_done(api, tmp_path):
    (tmp_path / "studio.json").write_text('{"setup_done": true}', encoding="utf-8")
    assert api.get_prefs()["tour_seen"] is True


def test_set_pref_takes_a_bool_tour_seen(api):
    api.set_pref("tour_seen", True)
    assert api.get_prefs()["tour_seen"] is True
    api.set_pref("tour_seen", "yes")                      # not a bool: ignored
    assert api.get_prefs()["tour_seen"] is True


def _whats_new_log(tmp_path, monkeypatch):
    f = tmp_path / "CHANGELOG.md"
    f.write_text(f"## [Unreleased]\n\nSoon.\n\n## [{paths.VERSION}] - 2026-10-31\n\n### Added\n\n- Now one.\n\n"
                 "## [0.11.0] - 2026-09-01\n\n- Then one.\n\n## [0.10.0] - 2026-08-01\n\n- Earlier.\n",
                 encoding="utf-8")
    monkeypatch.setattr(paths, "CHANGELOG", str(f))


def test_whats_new_for_an_existing_user_shows_the_current_section(api, tmp_path, monkeypatch):
    _whats_new_log(tmp_path, monkeypatch)
    (tmp_path / "studio.json").write_text('{"last_screen": "menus"}', encoding="utf-8")
    res = api.get_whats_new()
    assert res["current"] == paths.VERSION
    assert [s["version"] for s in res["sections"]] == [paths.VERSION]
    assert res["sections"][0] == {"version": paths.VERSION, "date": "2026-10-31", "summary": [],
                                  "items": ["Now one."], "url": f"{studio.RELEASES_URL}/tag/v{paths.VERSION}"}


def test_whats_new_lists_the_versions_after_the_one_seen(api, tmp_path, monkeypatch):
    _whats_new_log(tmp_path, monkeypatch)
    api.set_pref("seen_version", "0.10.0")
    res = api.get_whats_new()
    assert [s["version"] for s in res["sections"]] == [paths.VERSION, "0.11.0"]
    assert res["sections"][1]["url"] == f"{studio.RELEASES_URL}/tag/v0.11.0"


def test_whats_new_is_empty_once_this_version_was_seen(api, tmp_path, monkeypatch):
    _whats_new_log(tmp_path, monkeypatch)
    api.set_pref("seen_version", paths.VERSION)
    assert api.get_whats_new()["sections"] == []


def test_whats_new_all_current_ignores_what_was_seen(api, tmp_path, monkeypatch):
    _whats_new_log(tmp_path, monkeypatch)
    api.set_pref("seen_version", paths.VERSION)
    res = api.get_whats_new(all_current=True)
    assert [s["version"] for s in res["sections"]] == [paths.VERSION]
    assert api.get_prefs()["seen_version"] == paths.VERSION      # asking does not mark it as seen


# --- theme --------------------------------------------------------------------------------------------

def test_a_fresh_install_is_dark_and_says_what_is_in_force(api):
    prefs = api.get_prefs()
    assert prefs["theme"] == "dark" and prefs["theme_effective"] == "dark"


def test_the_theme_is_saved_and_the_effective_one_is_not(api, tmp_path):
    res = api.set_pref("theme", "light")
    assert res["theme"] == "light" and res["theme_effective"] == "light"
    assert _studio_json(tmp_path)["theme"] == "light"
    assert "theme_effective" not in _studio_json(tmp_path)


def test_follow_windows_is_accepted_and_resolved(api, tmp_path, monkeypatch):
    monkeypatch.setattr(theme, "_apps_use_light", lambda: True)
    res = api.set_pref("theme", "system")
    assert res["theme"] == "system" and res["theme_effective"] == "light"
    assert _studio_json(tmp_path)["theme"] == "system"


@pytest.mark.parametrize("value", ["blue", "", "Dark", None, 1, True, ["dark"]])
def test_an_unknown_theme_is_refused_and_nothing_is_written(api, tmp_path, value):
    api.set_pref("theme", "light")
    before = (tmp_path / "studio.json").read_text(encoding="utf-8")
    assert api.set_pref("theme", value)["theme"] == "light"
    assert (tmp_path / "studio.json").read_text(encoding="utf-8") == before


def test_an_unknown_theme_is_refused_on_a_fresh_install(api, tmp_path):
    assert api.set_pref("theme", "blue")["theme"] == "dark"
    assert "theme" not in _studio_json(tmp_path)


def test_a_hand_edited_theme_reads_as_dark(api, tmp_path):
    (tmp_path / "studio.json").write_text('{"theme": "blue", "last_screen": "library"}', encoding="utf-8")
    prefs = api.get_prefs()
    assert prefs["theme"] == "dark" and prefs["theme_effective"] == "dark"
    assert prefs["last_screen"] == "library"


def test_the_ring_defaults_follow_the_theme(api, monkeypatch):
    monkeypatch.setattr(studio, "_theme_now", lambda: "light")
    light = theme.ring_colors("light")
    assert api.get_config()["defaults"]["colors"]["bg"] == light["bg"]
    opts = api.get_options()
    assert opts["ring_defaults"]["colors"] == light
    assert opts["theme_ring_colors"] == {"dark": theme.ring_colors("dark"), "light": light}
    assert opts["themes"] == ["dark", "light", "system"]


def test_the_ring_defaults_are_dark_by_default(api):
    assert api.get_options()["ring_defaults"]["colors"] == theme.ring_colors("dark")


def test_previews_and_validation_use_the_theme(api, monkeypatch):
    monkeypatch.setattr(studio, "_theme_now", lambda: "light")
    cfg = _default()
    res = api.preview_ring(cfg, next(iter(cfg["menus"])))
    assert res["image"] and res["image"].startswith("data:image/png")
    loaded, _ = api._load_dict(cfg)
    assert loaded.ring["theme"] == "light"
    assert loaded.ring["colors"]["bg"] == theme.ring_colors("light")["bg"]


def test_setting_the_theme_without_a_window_does_not_fail(api):
    assert api.set_pref("theme", "light")["theme"] == "light"
    assert api.theme_changed("light") is True
    assert api.theme_changed("blue") is True            # ignored


def test_the_frame_is_set_when_the_window_is_there(api, monkeypatch):
    calls = []
    monkeypatch.setattr(studio.winframe, "apply_theme", lambda hwnd, window: calls.append((hwnd, window)))
    monkeypatch.setattr(studio, "IsWindow", lambda h: True)
    api._hwnd_cache = 77
    api.set_pref("theme", "light")
    assert calls == [(77, theme.PRESETS["light"]["window"])]
    api.theme_changed("dark")
    assert calls[-1] == (77, theme.PRESETS["dark"]["window"])
    api.theme_changed("system")                          # not a preset: nothing happens
    assert len(calls) == 2


def test_a_failing_frame_call_never_reaches_the_page(api, monkeypatch):
    def boom(hwnd, window):
        raise OSError("dwm")
    monkeypatch.setattr(studio.winframe, "apply_theme", boom)
    monkeypatch.setattr(studio, "IsWindow", lambda h: True)
    api._hwnd_cache = 77
    assert api.set_pref("theme", "light")["theme"] == "light"
    assert api.theme_changed("light") is True
