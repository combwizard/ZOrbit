"""Studio's Api against a temporary radial.json: backups, the start check, the setup fallback, added ZBrush folders
and the import numbers. Nothing here opens a window or touches the real %APPDATA%."""
import json
import os
import struct
import types

import pytest

import fsutil
import paths
import studio
import theme
import zbrush_colors


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


def test_choose_folder_returns_the_picked_path_or_none(api, tmp_path, monkeypatch):
    _fake_webview(monkeypatch)
    api._window = types.SimpleNamespace(create_file_dialog=lambda *a, **k: [str(tmp_path)])
    assert api.choose_folder() == str(tmp_path)
    api._window = types.SimpleNamespace(create_file_dialog=lambda *a, **k: None)
    assert api.choose_folder() is None


def test_choose_file_returns_the_picked_path_for_tool_project_and_layout_only(api, tmp_path, monkeypatch):
    _fake_webview(monkeypatch)
    opened = []

    def dialog(*a, **k):
        opened.append((a, k))
        return [str(tmp_path / "Hero.ztl")]
    api._window = types.SimpleNamespace(create_file_dialog=dialog)
    assert api.choose_file("tool") == str(tmp_path / "Hero.ztl")
    assert opened[-1] == ((2,), {"file_types": ("ZBrush tool (*.ztl)",)})     # FileDialog.OPEN, the tool filter
    assert api.choose_file("project") == str(tmp_path / "Hero.ztl")
    assert opened[-1][1]["file_types"] == ("ZBrush project (*.zpr)",)
    assert api.choose_file("layout") == str(tmp_path / "Hero.ztl")
    assert opened[-1][1]["file_types"] == ("ZBrush UI layout (*.cfg)",)
    assert api.choose_file("capture") is None and api.choose_file(["tool"]) is None and api.choose_file("") is None
    assert len(opened) == 3                                                  # a kind it refuses never opens a dialog
    api._window = types.SimpleNamespace(create_file_dialog=lambda *a, **k: None)
    assert api.choose_file("tool") is None


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


def test_a_saved_theme_nudges_the_browser_and_a_refused_one_does_not(api, monkeypatch):
    nudges = []
    monkeypatch.setattr(studio, "_tell_popout_theme", lambda: nudges.append(1))
    api.set_pref("theme", "blue")
    api.set_pref("check_updates", False)
    assert nudges == []
    api.set_pref("theme", "light")
    assert nudges == [1]


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


def test_the_ring_defaults_follow_the_theme(api, zb, monkeypatch):
    monkeypatch.setattr(studio, "_theme_now", lambda: "light")
    light = theme.ring_colors("light")
    assert api.get_config()["defaults"]["colors"]["bg"] == light["bg"]
    opts = api.get_options()
    assert opts["ring_defaults"]["colors"] == light
    assert opts["theme_ring_colors"] == {"dark": theme.ring_colors("dark"), "light": light}
    assert opts["themes"] == ["dark", "light", "system", "zbrush"]


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


def test_an_item_with_its_own_glow_colour_previews_and_validates(api):
    cfg = _default()
    mid = next(iter(cfg["menus"]))
    cfg["menus"][mid]["items"][0]["style"] = {"glow_color": "#ff8800"}
    res = api.preview_ring(cfg, mid)
    assert res["image"].startswith("data:image/png") and not res.get("problems")
    cfg["menus"][mid]["items"][1]["style"] = {"glow_color": "orange"}
    assert any("style.glow_color: 'orange'" in p for p in api.preview_ring(cfg, mid).get("problems", []))


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


# --- Match ZBrush --------------------------------------------------------------------------------------------------

def _scheme_bytes(colours, count=57):
    """A UI colours chunk in the layout tools/icolors_probe.py found: tag, 2 bytes, length, 10 floats, count, colours."""
    values = [(128, 128, 128)] * count
    for name, rgb in colours.items():
        values[zbrush_colors.PATCHES[name]] = rgb
    body = struct.pack("<10f", *([0.5] * 10)) + struct.pack("<I", count)
    body += struct.pack(f"<{count}f", *(r + g / 256 + b / 65536 for r, g, b in values))
    return b"junk before the block" + zbrush_colors.TAG + b"\x01\x00" + struct.pack("<I", len(body)) + body


@pytest.fixture
def zb(tmp_path, monkeypatch):
    """PUBLIC and APPDATA in tmp_path, no ZBrush running; store(year, colours) writes a stored scheme."""
    monkeypatch.setenv("PUBLIC", str(tmp_path / "Public"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setattr(zbrush_colors, "running_year", lambda: None)
    zbrush_colors._reset()

    def store(year=2026, colours=None):
        folder = tmp_path / "Public" / "Documents" / f"ZBrushData{year}" / "ZStartup"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"CustomUserInterface{year}.cfg"
        path.write_bytes(_scheme_bytes(colours or {"main": (19, 9, 9), "bt1": (23, 18, 18), "sw1": (255, 104, 0),
                                                  "text2": (236, 238, 238), "palette1": (67, 67, 67)}))
        zbrush_colors._reset()
        return path
    yield store
    zbrush_colors._reset()


def test_match_zbrush_with_a_stored_scheme(api, zb):
    zb(2026)
    res = api.set_pref("theme", "zbrush")
    assert res["theme"] == "zbrush" and res["theme_effective"] == "zbrush"
    assert res["theme_base"] == "dark" and "--bg1" in res["theme_tokens"]
    assert res["theme_source"]["year"] == 2026 and isinstance(res["theme_source"]["stored"], int)
    assert res["theme_sig"] and res["theme_sig"] == api.get_prefs()["theme_sig"]


def test_match_zbrush_without_a_stored_scheme_is_dark(api, zb):
    res = api.set_pref("theme", "zbrush")
    assert res["theme"] == "zbrush" and res["theme_effective"] == "dark"
    assert res["theme_base"] == "dark" and res["theme_tokens"] == {}
    assert res["theme_source"] is None and res["theme_sig"] == ""


def test_the_fixed_themes_carry_no_tokens_or_source(api, zb):
    zb(2026)
    res = api.set_pref("theme", "light")
    assert res["theme_base"] == "light" and res["theme_tokens"] == {} and res["theme_source"] is None
    assert res["theme_sig"] == ""


def test_a_new_stored_scheme_changes_the_signature(api, zb):
    zb(2026)
    api.set_pref("theme", "zbrush")
    first = api.get_prefs()
    zb(2026, {"main": (30, 30, 60), "bt1": (50, 50, 90), "sw1": (0, 200, 255), "text2": (240, 240, 240)})
    second = api.get_prefs()
    assert second["theme_sig"] != first["theme_sig"] and second["theme_tokens"]["--bg1"] != first["theme_tokens"]["--bg1"]


def test_the_options_offer_zbrush_colours_only_with_a_scheme(api, zb):
    assert "zbrush" not in api.get_options()["theme_ring_colors"]
    zb(2026)
    colours = api.get_options()["theme_ring_colors"]
    assert colours["zbrush"] == theme.ring_colors("zbrush") and set(colours) == {"dark", "light", "zbrush"}


def test_theme_changed_accepts_zbrush(api, zb, monkeypatch):
    assert api.theme_changed("zbrush") is True          # no window: nothing to do
    zb(2026)
    calls = []
    monkeypatch.setattr(studio, "IsWindow", lambda h: True)
    monkeypatch.setattr(studio.winframe, "apply_theme", lambda hwnd, window: calls.append((hwnd, window)))
    api._hwnd_cache = 77
    assert api.theme_changed("zbrush") is True
    assert calls == [(77, theme.preset("zbrush")["window"])]


# --- Copy report ---------------------------------------------------------------------------------
@pytest.fixture
def report_api(api, tmp_path, monkeypatch):
    home = "C:/Users/brush"
    monkeypatch.setenv("USERPROFILE", home.replace("/", os.sep))
    monkeypatch.setenv("USERNAME", "brush")
    monkeypatch.setenv("LOCALAPPDATA", (home + "/AppData/Local").replace("/", os.sep))
    (tmp_path / "radiald.log").write_text(
        "2026-11-04 10:00:00 old line\n2026-11-04 10:00:01 ZOrbit starting (pid 7, python 3.14)\n"
        "2026-11-04 10:00:02 brush Clay: selected\n"
        "2026-11-04 10:00:03 config at C:/Users/brush/AppData/Local/ZOrbit/x\n", encoding="utf-8")
    monkeypatch.setattr(api, "_all_installs", lambda: [
        {"name": "ZBrush 2023", "year": 2023, "path": "C:/ZB2023", "python": False},
        {"name": "ZBrush 2026", "year": 2026, "path": "C:/ZB2026", "python": True}])
    monkeypatch.setattr(studio.W, "pids_named", lambda name: [11])
    monkeypatch.setattr(studio.W, "process_image", lambda pid: "C:/ZB2023/ZBrush.exe")
    monkeypatch.setattr(studio.W, "process_elevated", lambda pid: False)
    monkeypatch.setattr(studio.installs, "install_of", lambda image: {"name": "ZBrush 2023", "year": 2023,
                                                                      "path": "C:/ZB2023", "python": False})
    monkeypatch.setattr(api, "_running_version", lambda: "0.18.1")
    return api


def test_the_report_holds_the_facts_and_hides_the_folders(report_api):
    res = report_api.get_report([["ZBrush", "Running"], ["Last pick", "Nothing picked yet"]])
    text = res["text"]
    assert res["ok"] and f"ZOrbit: {paths.VERSION} (source)" in text and "Windows: Windows " in text
    assert "Bridge mode: auto" in text and "Bridge key: F9" in text and "App running: 0.18.1" in text
    assert "ZBrush 2023 (2022 to 2025): C:/ZB2023: running as pid 11, administrator: no" in text
    assert "ZBrush 2026 (2026 and newer): C:/ZB2026: not running" in text
    assert "ZBrush: Running\nLast pick: Nothing picked yet" in text
    assert "--- Problems in the menus file ---\nnone" in text
    assert "%LOCALAPPDATA%/ZOrbit/x" in text and "C:/Users" not in text
    assert "brush Clay: selected" in text
    for name in ("--- radiald.log ---", "--- bridge.log ---", "--- zscript_bridge.log ---", "--- popout.log ---",
                 "--- studio.log ---"):
        assert name in text


def test_a_part_that_cannot_be_read_leaves_the_rest_of_the_report(report_api, monkeypatch):
    def boom():
        raise OSError("no scan today")
    monkeypatch.setattr(report_api, "_report_zbrush", boom)
    monkeypatch.setattr(report_api, "_report_menus", boom)
    text = report_api.get_report()["text"]
    assert "--- ZBrush ---\nnone found" in text and "Bridge mode: unknown" in text
    assert "could not be read: OSError('no scan today')" in text and "--- radiald.log ---" in text


@pytest.mark.parametrize("cards", [None, "x", [["only title"]], [[1, 2]], {"a": "b"}])
def test_bad_cards_are_left_out(report_api, cards):
    assert "--- Status cards ---\n(not shown yet)" in report_api.get_report(cards)["text"]


def test_a_zbrush_running_as_administrator_says_so(report_api, monkeypatch):
    monkeypatch.setattr(studio.W, "process_image", lambda pid: "")
    assert "A ZBrush outside the list: pid 11, administrator: yes" in report_api.get_report()["text"]


def test_the_bug_link_names_the_zbrush_that_runs_and_opens(report_api):
    url = report_api.get_bug_url()
    assert f"zorbit={paths.VERSION}" in url and "zbrush=2023" in url and "windows=Windows" in url
    assert "brush" not in url.replace("zbrush", "")
    assert url.startswith("https://github.com/combwizard/zorbit/")


def test_the_bug_link_falls_back_to_the_newest_zbrush_known(report_api, monkeypatch):
    monkeypatch.setattr(studio.W, "pids_named", lambda name: [])
    assert "zbrush=2026" in report_api.get_bug_url()


# --- macros in the path suggestions ------------------------------------------------------------------

BUTTON = "[IButton,???,0,0,0]\nCommands\n"


def _macro(folder, name, text=BUTTON):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / (name + ".txt")).write_bytes(text.encode("utf-8"))


def test_a_macro_with_a_button_is_listed_under_the_macros_folder(tmp_path):
    _macro(tmp_path, "Toggle See-Through")
    assert studio._macro_paths([str(tmp_path)]) == ["Macro:Macros:Toggle See-Through"]


def test_the_button_marker_is_found_in_any_case_and_spacing(tmp_path):
    _macro(tmp_path, "Lower", "[ibutton ,???,0]\n")
    _macro(tmp_path, "Upper", "[ IButton,???,0]\n")
    assert studio._macro_paths([str(tmp_path)]) == ["Macro:Macros:Lower", "Macro:Macros:Upper"]


def test_a_file_without_a_button_is_left_out(tmp_path):
    _macro(tmp_path, "Bare", "Lot\nof commands\n")
    assert studio._macro_paths([str(tmp_path)]) == []


def test_a_subfolder_gives_its_own_name_in_the_path(tmp_path):
    _macro(tmp_path / "Misc", "Toggle See-Through")
    assert studio._macro_paths([str(tmp_path)]) == ["Macro:Misc:Toggle See-Through"]


def test_a_file_two_levels_down_is_not_listed(tmp_path):
    _macro(tmp_path / "Misc" / "Deep", "Hidden")
    assert studio._macro_paths([str(tmp_path)]) == []


def test_the_same_name_in_two_folders_gives_one_path(tmp_path):
    _macro(tmp_path / "one", "Toggle")
    _macro(tmp_path / "two" / "Misc", "toggle")
    assert studio._macro_paths([str(tmp_path / "one"), str(tmp_path / "two")]) == ["Macro:Macros:Toggle"]


def test_a_missing_folder_gives_nothing(tmp_path):
    assert studio._macro_paths([str(tmp_path / "nope")]) == []


def test_only_txt_files_are_listed(tmp_path):
    _macro(tmp_path, "Toggle")
    (tmp_path / "Other.zsc").write_bytes(BUTTON.encode())
    (tmp_path / "Old.txt.bak").write_bytes(BUTTON.encode())
    assert studio._macro_paths([str(tmp_path)]) == ["Macro:Macros:Toggle"]


def test_a_name_with_a_comma_is_skipped(tmp_path):
    _macro(tmp_path, "Real")
    _macro(tmp_path, "Comma, here")
    assert studio._macro_paths([str(tmp_path)]) == ["Macro:Macros:Real"]


def test_a_name_with_a_colon_is_skipped(tmp_path, monkeypatch):
    _macro(tmp_path, "Real")
    real = str(tmp_path / "Real.txt")
    monkeypatch.setattr(studio, "_macro_txt_files", lambda d: ([("A:B", real)], []))     # Windows cannot hold a colon in a name
    assert studio._macro_paths([str(tmp_path)]) == []


def test_bytes_that_are_not_text_do_not_break_the_scan(tmp_path):
    (tmp_path / "Junk.txt").write_bytes(b"\xff\xfe\x80\x81 junk")
    (tmp_path / "Mixed.txt").write_bytes(b"\xff\x80 [IButton,???,0]")
    assert studio._macro_paths([str(tmp_path)]) == ["Macro:Macros:Mixed"]


def test_only_the_first_64_kb_of_a_file_is_read(tmp_path):
    _macro(tmp_path, "Late", "x" * 65536 + "[IButton,???,0]")
    assert studio._macro_paths([str(tmp_path)]) == []


def test_the_scan_stops_at_the_file_cap(tmp_path):
    for i in range(studio.MACRO_MAX_FILES + 100):
        _macro(tmp_path, f"m{i:04d}")
    assert len(studio._macro_paths([str(tmp_path)])) == studio.MACRO_MAX_FILES


def test_the_suggestions_keep_their_sources_and_add_macros_last(api, tmp_path, monkeypatch):
    ua = tmp_path / "userassets"
    _macro(ua / "ZStartup" / "Macros", "Tab")
    install = tmp_path / "ZBrush 2026"
    _macro(install / "ZData" / "Macros" / "Misc", "Toggle See-Through")
    _macro(install / "ZData" / "Macros", "toggle see-through")     # the same name again
    monkeypatch.setattr(studio.brushes, "zbrush_dirs", lambda: {"install": None, "user_assets": str(ua)})
    monkeypatch.setattr(api, "_all_installs", lambda: [{"name": "ZBrush 2026", "year": 2026, "path": str(install),
                                                        "python": True, "supported": True}])
    sug = api.get_suggestions()
    keys = [s["path"].replace(" ", "").lower() for s in sug]
    assert len(keys) == len(set(keys))
    assert "tool:masking:clear" in keys and "stroke:lazymouse" in keys
    macros = [s for s in sug if s["source"] == "macro"]
    assert [s["path"] for s in macros] == ["Macro:Macros:Tab", "Macro:Macros:toggle see-through"]
    assert sug.index(macros[0]) > max(i for i, s in enumerate(sug) if s["source"] == "common")


def test_a_2022_install_reads_its_startup_macros_only(api, tmp_path, monkeypatch):
    install = tmp_path / "ZBrush 2022"
    _macro(install / "ZStartup" / "Macros", "Old")
    _macro(install / "ZData" / "Macros", "New")
    monkeypatch.setattr(studio.brushes, "zbrush_dirs", lambda: {"install": None, "user_assets": None})
    monkeypatch.setattr(api, "_all_installs", lambda: [{"name": "ZBrush 2022", "year": 2022, "path": str(install),
                                                        "python": False, "supported": True}])
    assert [s["path"] for s in api.get_suggestions() if s["source"] == "macro"] == ["Macro:Macros:Old"]


# --- library folders (issue #170) ----------------------------------------------------------------------
@pytest.fixture
def lib(api, tmp_path, monkeypatch):
    """The api with a fake ZBrush (install and user assets folders under tmp_path) and a folder dialog the test steers:
    lib.pick(path) sets what the next dialog returns (None cancels)."""
    import brushes
    _fake_webview(monkeypatch)
    install, user = tmp_path / "ZB" / "ZBrush 2026", tmp_path / "ZB" / "Data"
    for d in (install, user / "ZStartup" / "BrushPresets", tmp_path / "mine"):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(brushes, "zbrush_dirs", lambda: {"install": install, "user_assets": user})
    state = {"next": None}
    api._window = types.SimpleNamespace(
        create_file_dialog=lambda *a, **k: [str(state["next"])] if state["next"] is not None else None)
    api.pick = lambda p: state.update(next=p)
    api.install, api.user = install, user
    return api


def _folders(tmp_path):
    return json.loads((tmp_path / "studio.json").read_text(encoding="utf-8")).get("library_folders")


def test_a_library_folder_is_added_and_listed(lib, tmp_path):
    (tmp_path / "mine" / "Clay").mkdir()
    lib.pick(tmp_path / "mine" / "Clay")
    res = lib.add_library_folder("brush")
    assert res["ok"] and res["message"] == "Added Clay."
    row = res["folders"]["brush"][0]
    assert row == {"path": str(tmp_path / "mine" / "Clay"), "name": "Clay", "exists": True, "count": None,
                   "hidden": None, "error": None}
    assert res["folders"]["alpha"] == [] and res["folders"]["texture"] == []
    assert lib.get_library_folders()["folders"] == res["folders"]
    assert _folders(tmp_path) == {"brush": [str(tmp_path / "mine" / "Clay")]}


def test_a_listed_folder_that_vanished_is_listed_as_missing(lib, tmp_path):
    (tmp_path / "studio.json").write_text(json.dumps({"library_folders": {"alpha": [str(tmp_path / "gone")]}}),
                                          encoding="utf-8")
    row = lib.get_library_folders()["folders"]["alpha"][0]
    assert row["exists"] is False and row["name"] == "gone"


def test_the_count_comes_from_the_last_walk(lib, tmp_path, monkeypatch):
    import assets
    import brushes
    folder = tmp_path / "mine"
    (tmp_path / "studio.json").write_text(json.dumps({"library_folders": {"alpha": [str(folder)]}}), encoding="utf-8")
    src = {"label": brushes.added_label(folder), "count": 330, "hidden": 2, "error": None}
    monkeypatch.setattr(assets, "last_walk", lambda kind: types.SimpleNamespace(sources=[src]) if kind == "alpha" else None)
    row = lib.get_library_folders()["folders"]["alpha"][0]
    assert (row["count"], row["hidden"], row["error"]) == (330, 2, None)
    src.update(count=0, error="drive not ready")
    del src["hidden"]
    row = lib.get_library_folders()["folders"]["alpha"][0]
    assert (row["count"], row["hidden"], row["error"]) == (0, 0, "drive not ready")


def test_a_folder_already_listed_is_not_added_twice(lib, tmp_path):
    lib.pick(tmp_path / "mine")
    assert lib.add_library_folder("texture")["ok"]
    lib.pick(str(tmp_path / "mine").upper() + "/")
    res = lib.add_library_folder("texture")
    assert res["ok"] and res["already"] is True and "already listed" in res["message"]
    assert len(_folders(tmp_path)["texture"]) == 1


def test_the_same_folder_can_be_listed_for_two_kinds(lib, tmp_path):
    lib.pick(tmp_path / "mine")
    assert lib.add_library_folder("alpha")["ok"] and lib.add_library_folder("material")["ok"]


def test_a_library_folder_is_forgotten_and_the_others_keep_their_order(lib, tmp_path):
    for n in ("a", "b", "c"):
        (tmp_path / "mine" / n).mkdir()
        lib.pick(tmp_path / "mine" / n)
        lib.add_library_folder("brush")
    res = lib.forget_library_folder("brush", str(tmp_path / "mine" / "B"))
    assert res["ok"] and res["message"] == "Forgot b. The folder itself was not touched."
    assert [r["name"] for r in res["folders"]["brush"]] == ["a", "c"]
    assert (tmp_path / "mine" / "b").is_dir()
    res = lib.forget_library_folder("brush", str(tmp_path / "mine" / "b"))
    assert res == {"ok": False, "message": "That folder is not in the list."}
    assert lib.forget_library_folder("alpha", str(tmp_path / "mine" / "a"))["ok"] is False


def test_an_unknown_kind_is_refused_without_a_dialog(lib, tmp_path):
    lib.pick(tmp_path / "mine")
    for kind in ("tool", "", None, ["brush"]):
        assert lib.add_library_folder(kind) == {"ok": False, "message": "Unknown kind."}
    assert not (tmp_path / "studio.json").exists()


def test_a_cancelled_dialog_adds_nothing(lib, tmp_path):
    lib.pick(None)
    assert lib.add_library_folder("brush") == {"ok": False, "cancelled": True}
    assert not (tmp_path / "studio.json").exists()


def test_a_network_folder_is_refused(lib, tmp_path):
    lib.pick("//server/share/brushes")
    res = lib.add_library_folder("brush")
    assert res["ok"] is False and "network folder" in res["message"]
    assert not (tmp_path / "studio.json").exists()


def test_a_folder_that_is_not_there_is_refused(lib, tmp_path):
    lib.pick(tmp_path / "nowhere")
    res = lib.add_library_folder("brush")
    assert res == {"ok": False, "message": "That folder cannot be found."}


def test_a_folder_zbrush_already_searches_is_refused(lib, tmp_path):
    (lib.install / "ZData" / "Sub").mkdir(parents=True)
    (tmp_path / "ZB" / "Data2").mkdir()
    for inside in (lib.install, lib.user, lib.install / "ZData" / "Sub", lib.user / "ZStartup" / "BrushPresets"):
        lib.pick(inside)
        res = lib.add_library_folder("brush")
        assert res["ok"] is False and "already searches that folder" in res["message"], inside
    lib.pick(tmp_path / "ZB")                                     # holds ZBrush: everything in it would be listed twice
    assert "already searches that folder" in lib.add_library_folder("alpha")["message"]
    lib.pick(lib.user / "ZStartup" / "BrushPresets")
    assert "(My Brushes)" in lib.add_library_folder("brush")["message"]
    assert not (tmp_path / "studio.json").exists()


def test_a_folder_that_only_starts_like_a_zbrush_folder_is_fine(lib, tmp_path):
    beside = tmp_path / "ZB" / "ZBrush 2026 beta"
    beside.mkdir()
    lib.pick(beside)
    assert lib.add_library_folder("brush")["ok"] is True


def test_a_folder_inside_or_around_an_added_one_is_refused(lib, tmp_path):
    (tmp_path / "mine" / "deep").mkdir()
    lib.pick(tmp_path / "mine")
    assert lib.add_library_folder("alpha")["ok"]
    lib.pick(tmp_path / "mine" / "deep")
    res = lib.add_library_folder("alpha")
    assert res["ok"] is False and res["message"] == "mine is already searched, and this one is inside it."
    assert lib.add_library_folder("brush")["ok"]                  # another kind has its own list
    lib.forget_library_folder("alpha", str(tmp_path / "mine"))
    assert lib.add_library_folder("alpha")["ok"]
    lib.pick(tmp_path / "mine")
    res = lib.add_library_folder("alpha")
    assert res["ok"] is False and res["message"] == "deep is already searched, and this one would contain it."
    assert len(_folders(tmp_path)["alpha"]) == 1


def test_adding_keeps_the_other_kinds_and_the_other_keys(lib, tmp_path):
    other = str(tmp_path / "elsewhere")
    (tmp_path / "studio.json").write_text(json.dumps({"check_updates": False, "library_folders": {"alpha": [other]}}),
                                          encoding="utf-8")
    lib.pick(tmp_path / "mine")
    assert lib.add_library_folder("brush")["ok"]
    data = json.loads((tmp_path / "studio.json").read_text(encoding="utf-8"))
    assert data["check_updates"] is False
    assert data["library_folders"] == {"alpha": [other], "brush": [str(tmp_path / "mine")]}


def test_a_library_entry_that_is_not_a_dict_or_list_is_replaced(lib, tmp_path):
    (tmp_path / "studio.json").write_text(json.dumps({"library_folders": ["x"]}), encoding="utf-8")
    lib.pick(tmp_path / "mine")
    assert lib.add_library_folder("brush")["ok"]
    assert _folders(tmp_path) == {"brush": [str(tmp_path / "mine")]}
    (tmp_path / "studio.json").write_text(json.dumps({"library_folders": {"brush": "x"}}), encoding="utf-8")
    assert lib.add_library_folder("brush")["ok"]
    assert _folders(tmp_path) == {"brush": [str(tmp_path / "mine")]}


def test_library_folders_are_not_changed_over_an_unreadable_studio_file(lib, tmp_path):
    f = tmp_path / "studio.json"
    f.write_text('{"library_folders": {"brush": ["D:/Lib"]}, "check_updates": false,', encoding="utf-8")
    before = f.read_bytes()
    lib.pick(tmp_path / "mine")
    res = lib.add_library_folder("brush")
    assert res == {"ok": False, "message": studio.STUDIO_UNREADABLE}
    assert lib.forget_library_folder("brush", "D:/Lib") == {"ok": False, "message": studio.STUDIO_UNREADABLE}
    assert f.read_bytes() == before


def test_inside_is_about_whole_folder_names():
    assert studio._inside(r"D:\ZBrush 2026\ZData", r"D:\ZBrush 2026")
    assert studio._inside("d:/zbrush 2026/", r"D:\ZBrush 2026")
    assert not studio._inside(r"D:\ZBrush 2026 beta", r"D:\ZBrush 2026")
    assert not studio._inside(r"D:\ZBrush 2026", r"D:\ZBrush 2026\ZData")


def test_the_report_lists_the_library_folders_with_the_name_hidden(report_api, tmp_path):
    (tmp_path / "studio.json").write_text(json.dumps({"library_folders": {
        "brush": ["C:/Users/brush/Lib/Brushes"], "alpha": [str(tmp_path)]}}), encoding="utf-8")
    text = report_api.get_report()["text"]
    assert "--- Library folders ---\n" in text
    assert "Brushes: C:/Users/brush/Lib/Brushes" not in text and "brush/Lib" not in text
    assert "Brushes: %USERPROFILE%" in text and "Lib" in text and ": missing" in text
    assert "Alphas: " in text and "Materials: none added" in text and "Textures: none added" in text


def test_a_library_part_that_fails_leaves_the_rest_of_the_report(report_api, monkeypatch):
    def boom():
        raise OSError("no listing")
    monkeypatch.setattr(report_api, "get_library_folders", boom)
    text = report_api.get_report()["text"]
    assert "--- Library folders ---\ncould not be read: OSError('no listing')" in text
    assert "--- Status cards ---" in text
