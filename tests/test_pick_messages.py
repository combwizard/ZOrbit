"""The short messages shown near the cursor when a pick goes nowhere: each cause has its own, and each fits the
toast on one line."""
import time

import pytest
from PIL import Image, ImageDraw

import config
import paths
import radiald
import ring
import toast
import win32 as W


@pytest.fixture
def app(monkeypatch, tmp_path):
    a = radiald.App(paths.DEFAULT_MENUS)
    a.cfg = config.load(paths.DEFAULT_MENUS)
    a.ctrl = 1
    a.toasts = []
    monkeypatch.setattr(a, "_toast", a.toasts.append)
    monkeypatch.setattr(W, "KillTimer", lambda *a_: 0)
    monkeypatch.setattr(W, "primary_down", lambda: False)
    monkeypatch.setattr(W, "nudge_mouse", lambda: None)
    req = tmp_path / "request.json"
    req.write_text("{}")
    monkeypatch.setattr(radiald, "REQUEST_FILE", str(req))
    return a


def _timed_out(app, mode, key):
    app.cfg.bridge_mode, app.cfg.bridge_key = mode, key
    now = time.time()
    app._ack = [5, now - 1, now - 1, False]
    app._check_ack()
    return app.toasts


def test_listener_that_does_not_answer_in_message_mode_says_so(app):
    assert _timed_out(app, "message", None) == [radiald.MSG_NO_ANSWER]
    assert "bridge mode is Message" in radiald.MSG_NO_ANSWER


def test_listener_that_does_not_answer_in_auto_mode_without_a_key_names_the_missing_key(app):
    assert _timed_out(app, "auto", None) == [radiald.MSG_NO_ANSWER_NO_KEY]
    assert "no bridge key" in radiald.MSG_NO_ANSWER_NO_KEY


def test_no_listener_in_message_mode_has_its_own_message(app, monkeypatch):
    app.cfg.bridge_mode = "message"
    monkeypatch.setattr(app, "_write_request", lambda item, legacy: 3)
    monkeypatch.setattr(app, "target_install", lambda: None)
    monkeypatch.setattr(app, "_front_pid", lambda: 1)
    monkeypatch.setattr(app, "_listener", lambda pid: None)
    monkeypatch.setattr(app, "_drop_request", lambda seq: None)
    monkeypatch.setattr(app.activity, "note_pick", lambda *a_, **k: None)
    item = next(iter(app.cfg.menus.values())).items[0]
    app.send(item)
    assert app.toasts == [radiald.MSG_NO_CONNECTION]
    assert "No plugin listener" in radiald.MSG_NO_CONNECTION


def test_no_bridge_key_has_its_own_message(app):
    app.cfg.bridge_key = None
    assert app.press_bridge_key(9) == (False, "no bridge key configured")
    assert app.toasts == [radiald.MSG_NO_KEY]
    assert "Choose one in Studio" in radiald.MSG_NO_KEY


def test_the_messages_are_different_and_fit_the_toast_on_one_line():
    msgs = [radiald.MSG_NO_CONNECTION, radiald.MSG_NO_ANSWER, radiald.MSG_NO_ANSWER_NO_KEY, radiald.MSG_NOT_FRONT,
            radiald.MSG_NO_KEY, radiald.MSG_EMPTY_SLOT, radiald.MSG_EMPTY_MENU, radiald.MSG_PICK_FAILED]
    assert len(set(msgs)) == len(msgs)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for m in msgs:
        font = ring._font_for(m, toast.FONT_PX, bold=False)
        assert probe.textlength(m, font=font) <= toast.MAX_W - 2 * toast.PAD_X, m
