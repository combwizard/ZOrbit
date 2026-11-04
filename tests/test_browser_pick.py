"""Which ZBrush a pick from the browser goes to. A browser opened from Studio has no ZBrush on record, because only
the app's own open_browser notes one. Its picks must still reach the listener when only one ZBrush is running."""
import json

import pytest

import config
import paths
import radiald
import win32 as W

LISTENER_HWND, LISTENER_PID, OTHER_PID = 500, 63380, 70000


@pytest.fixture
def app(monkeypatch, tmp_path):
    a = radiald.App(paths.DEFAULT_MENUS)
    a.cfg = config.load(paths.DEFAULT_MENUS)
    a.cfg.bridge_mode = "auto"
    a.ctrl = 1
    a.posted, a.pressed, a.routes = [], [], []
    listener = tmp_path / "listener.json"
    listener.write_text(json.dumps({"hwnd": LISTENER_HWND, "pid": LISTENER_PID, "verified": True}))
    monkeypatch.setattr(radiald, "LISTENER_FILE", str(listener))
    monkeypatch.setattr(radiald, "REQUEST_FILE", str(tmp_path / "request.json"))
    monkeypatch.setattr(W, "IsWindow", lambda hwnd: True)
    monkeypatch.setattr(W, "SetTimer", lambda *a_: 1)
    monkeypatch.setattr(W, "KillTimer", lambda *a_: 0)
    monkeypatch.setattr(W, "nudge_mouse", lambda: None)
    monkeypatch.setattr(W, "PostMessageW", lambda hwnd, msg, seq, _: a.posted.append(int(hwnd.value)) or 1)
    monkeypatch.setattr(a, "_exe_of", lambda pid, cache=None: a.target_exe)
    monkeypatch.setattr(a, "_write_request", lambda item, legacy: 7)
    monkeypatch.setattr(a, "_drop_request", lambda seq: None)
    monkeypatch.setattr(a, "target_install", lambda: None)
    monkeypatch.setattr(a, "press_bridge_key", lambda seq: (a.pressed.append(seq), (True, ""))[1])
    monkeypatch.setattr(a.activity, "note_pick", lambda seq, item, route, *r, **k: a.routes.append(route))
    return a


def _running(monkeypatch, *pids):
    monkeypatch.setattr(W, "pids_named", lambda name: list(pids))


def _pick(app):
    app.send(next(iter(app.cfg.menus.values())).items[0], source="browser")


def test_no_zbrush_on_record_and_one_running_goes_to_its_listener(app, monkeypatch):
    app._popout_zb = None
    _running(monkeypatch, LISTENER_PID)
    _pick(app)
    assert app.posted == [LISTENER_HWND] and app.pressed == [] and app.routes == ["listener"]


def test_the_browser_pick_does_not_wait_for_the_focus_when_the_listener_will_take_it(app, monkeypatch):
    app._popout_zb = None
    _running(monkeypatch, LISTENER_PID)
    monkeypatch.setattr(app, "target_in_front", lambda: False)
    monkeypatch.setattr(app, "_record_pick", lambda item: None)
    app._browser_pick = next(iter(app.cfg.menus.values())).items[0]
    app._browser_pick_deadline = float("inf")
    app._browser_pick_tick()
    assert app._browser_pick is None and app.posted == [LISTENER_HWND]


def test_a_zbrush_on_record_that_has_closed_counts_as_none_on_record(app, monkeypatch):
    app._popout_zb = (111, None)
    monkeypatch.setattr(W, "IsWindow", lambda hwnd: int(hwnd.value) != 111)
    _running(monkeypatch, LISTENER_PID)
    _pick(app)
    assert app.posted == [LISTENER_HWND] and app.routes == ["listener"]


def test_no_zbrush_on_record_and_two_running_cannot_tell_so_uses_the_bridge_key(app, monkeypatch):
    app._popout_zb = None
    _running(monkeypatch, LISTENER_PID, OTHER_PID)
    _pick(app)
    assert app.posted == [] and app.pressed == [7] and app.routes == ["key"]


def test_no_zbrush_running_uses_the_bridge_key(app, monkeypatch):
    app._popout_zb = None
    _running(monkeypatch)
    _pick(app)
    assert app.posted == [] and app.pressed == [7]


def test_key_mode_waits_for_the_focus_even_with_a_listener_there(app, monkeypatch):
    app.cfg.bridge_mode = "key"
    app._popout_zb = None
    _running(monkeypatch, LISTENER_PID)
    monkeypatch.setattr(app, "target_in_front", lambda: False)
    item = next(iter(app.cfg.menus.values())).items[0]
    app._browser_pick = item
    app._browser_pick_deadline = float("inf")
    app._browser_pick_tick()
    assert app._browser_pick is item and app.pressed == [] and app.posted == []


def test_key_mode_presses_the_key_once_zbrush_is_in_front(app, monkeypatch):
    app.cfg.bridge_mode = "key"
    app._popout_zb = None
    _running(monkeypatch, LISTENER_PID)
    monkeypatch.setattr(app, "target_in_front", lambda: True)
    monkeypatch.setattr(app, "_record_pick", lambda item: None)
    app._browser_pick = next(iter(app.cfg.menus.values())).items[0]
    app._browser_pick_deadline = float("inf")
    app._browser_pick_tick()
    assert app._browser_pick is None and app.pressed == [7] and app.posted == []


def test_message_mode_with_two_running_drops_the_pick_and_says_so(app, monkeypatch):
    app.cfg.bridge_mode = "message"
    app._popout_zb = None
    toasts = []
    monkeypatch.setattr(app, "_toast", toasts.append)
    _running(monkeypatch, LISTENER_PID, OTHER_PID)
    _pick(app)
    assert app.posted == [] and app.pressed == [] and toasts == [radiald.MSG_NO_CONNECTION]


def test_the_zbrush_on_record_wins_over_the_only_one_running(app, monkeypatch):
    app._popout_zb = (111, None)
    monkeypatch.setattr(W, "window_pid", lambda hwnd: OTHER_PID)
    _running(monkeypatch, LISTENER_PID)
    _pick(app)
    assert app.posted == [] and app.pressed == [7]
