"""The app follows the profile pointer: a switch reloads menus, tags and usage without a restart."""
import json
import os

import pytest

import profiles
import radiald


@pytest.fixture
def two(profile_env, monkeypatch):
    """profile_env with Default and B, B's first hotkey different from Default's."""
    for name in ("_prefetch", "_schedule_prewarm", "_prune_icons"):
        monkeypatch.setattr(radiald.App, name, lambda self: None)
    profiles.ensure()
    profiles.create("B", "starter")
    path = profiles.config_file("B")
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    menu = next(m for m in raw["menus"].values() if m.get("hotkey"))
    menu["hotkey"] = "Alt+F9"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    return raw


def hotkeys(app):
    return [m.hotkey.text for m in app.slots]


def inside(path, name):
    return os.path.dirname(path) == os.path.join(profiles.root(), name)


def make_app():
    app = radiald.App(None)
    app.load_config(force=True, balloon=False)
    return app


def test_an_app_starts_on_the_active_profile(two):
    app = radiald.App(None)
    assert app.profile == "Default" and not app._pinned
    assert inside(app.cfg_path, "Default")
    assert inside(app.tags.path, "Default")
    assert inside(app.usage.path, "Default")


def test_a_new_pointer_switches_the_profile_on_the_next_check(two):
    app = make_app()
    before_hook, before_keys = app._hook_state, hotkeys(app)
    assert "Alt+F9" not in before_keys
    profiles.set_active("B")
    app._check_profile()
    assert app.profile == "B"
    for path in (app.cfg_path, app.tags.path, app.usage.path):
        assert inside(path, "B")
    assert app.expander.usage is app.usage
    assert app.expander.tags is app.tags
    assert app._have_cfg
    assert "Alt+F9" in hotkeys(app) and hotkeys(app) != before_keys
    assert app._hook_state is not before_hook


def test_a_switch_waits_for_an_open_ring_and_a_pending_pick(two):
    app = make_app()
    profiles.set_active("B")
    app.ring = object()
    app._check_profile()
    assert app.profile == "Default"
    app.ring = None
    app._browser_pick = object()
    app._check_profile()
    assert app.profile == "Default"
    app._browser_pick = None
    app._check_profile()
    assert app.profile == "B"


def test_a_pointer_to_a_missing_folder_is_waited_for_then_given_up(two):
    app = make_app()
    with open(profiles.pointer_file(), "w", encoding="utf-8") as f:
        json.dump({"active": "Nope"}, f)
    for _ in range(19):
        app._check_profile()
    assert app.profile == "Default"
    app._check_profile()
    assert app.profile == profiles.active() == "Default"


def test_a_folder_that_appears_in_time_is_switched_to(two):
    app = make_app()
    with open(profiles.pointer_file(), "w", encoding="utf-8") as f:
        json.dump({"active": "Later"}, f)
    for _ in range(5):
        app._check_profile()
    assert app.profile == "Default"
    profiles.create("Later", "starter")
    app._check_profile()
    assert app.profile == "Later"


def test_a_pinned_app_never_follows_the_pointer(two, tmp_path):
    path = tmp_path / "radial.json"
    path.write_text(json.dumps({"menus": {"a": {"title": "A", "hotkey": "Q", "items": [{"brush": "Move"}]}}}),
                    encoding="utf-8")
    app = radiald.App(str(path))
    assert app._pinned and app.profile is None and app.cfg_path == str(path)
    profiles.set_active("B")
    app._check_profile()
    assert app.profile is None and app.cfg_path == str(path)


def test_an_app_given_a_profile_is_pinned_to_it(two):
    app = radiald.App(None, profile="B")
    assert app._pinned and app.profile == "B" and inside(app.cfg_path, "B")
    profiles.set_active("Default")
    app._check_profile()
    assert app.profile == "B"


class FakeTray:
    def __init__(self):
        self.calls = []

    def notify(self, title, text):
        self.calls.append(("notify", title, text))

    def set_tip(self, text):
        self.calls.append(("set_tip", text))

    def set_profile(self, name):
        self.calls.append(("set_profile", name))


def test_the_tray_command_switches_and_says_so(two):
    app = make_app()
    app.tray = FakeTray()
    app._tray_command("profile:B")
    assert app.profile == "B"
    assert ("set_profile", "B") in app.tray.calls
    assert ("notify", "ZOrbit", "Profile: B") in app.tray.calls


def test_the_tray_command_for_a_missing_profile_only_says_so(two):
    app = make_app()
    app.tray = FakeTray()
    app._tray_command("profile:Nope")
    assert app.profile == "Default"
    assert app.tray.calls == [("notify", "ZOrbit", "There is no profile called Nope.")]


def test_a_broken_profile_runs_without_menus_and_the_tray_says_so(two):
    with open(profiles.config_file("B"), "w", encoding="utf-8") as f:
        f.write("{ not json")
    app = make_app()
    app.tray = FakeTray()
    profiles.set_active("B")
    app._check_profile(notify=True)
    assert app.profile == "B" and app.slots == [] and not app._have_cfg
    assert any(c[0] == "notify" and c[1] == "ZOrbit cannot read the menus file" and "Profile B" in c[2]
               for c in app.tray.calls)
