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
    assert _timed_out(app, "message", config.parse_hotkey("F9")) == [radiald.MSG_NO_ANSWER]
    assert "bridge mode is Message" in radiald.MSG_NO_ANSWER


def test_listener_that_does_not_answer_in_auto_mode_falls_back_to_the_bridge_key(app, monkeypatch):
    pressed = []
    monkeypatch.setattr(app, "press_bridge_key", lambda seq: (pressed.append(seq), (True, ""))[1])
    assert _timed_out(app, "auto", config.parse_hotkey("F9")) == []
    assert pressed == [5]


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


def test_the_messages_are_different_and_fit_the_toast_on_one_line():
    msgs = [radiald.MSG_NO_CONNECTION, radiald.MSG_NO_ANSWER, radiald.MSG_NOT_FRONT, radiald.MSG_EMPTY_SLOT,
            radiald.MSG_EMPTY_MENU, radiald.MSG_PICK_FAILED, radiald.MSG_COMMAND_TEXT,
            radiald.MSG_COMMAND_PINNED, radiald.MSG_COMMAND_FROZEN, radiald.MSG_COMMAND_NO_MENUS,
            radiald.MSG_CAPTURE_FOLDER, radiald.MSG_CAPTURE_NAME, radiald.MSG_FILE_MISSING,
            radiald.MSG_FOLDER_MISSING, radiald.MSG_NO_PROJECT, radiald.MSG_FILE_NAME, radiald.MSG_FILE_LONG]
    assert len(set(msgs)) == len(msgs)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    for m in msgs:
        font = ring._font_for(m, toast.FONT_PX, bold=False)
        assert probe.textlength(m, font=font) <= toast.MAX_W - 2 * toast.PAD_X, m


def test_a_capture_that_could_not_be_made_has_its_own_messages():
    assert "capture folder" in radiald.MSG_CAPTURE_FOLDER
    assert "2022" in radiald.MSG_CAPTURE_NAME


def test_a_tool_or_project_that_could_not_be_sent_has_its_own_messages():
    assert radiald.MSG_FILE_MISSING.startswith("That file is not there, nothing sent")
    assert radiald.MSG_FOLDER_MISSING.startswith("That folder is not there, nothing sent")
    assert radiald.MSG_NO_PROJECT == "No project in that folder, nothing sent"
    assert "2022" in radiald.MSG_FILE_NAME and "2022" in radiald.MSG_FILE_LONG
    for m in (radiald.MSG_FILE_MISSING, radiald.MSG_FOLDER_MISSING, radiald.MSG_FILE_LONG):
        assert m.endswith("See radiald.log.")        # the log says which file
