"""The keyboard hook's decisions (App._on_key), driven with fake key structs and a stubbed Win32 layer."""
import types

import pytest

import config
import paths
import radiald
import win32 as W


@pytest.fixture
def app(monkeypatch):
    a = radiald.App(paths.DEFAULT_MENUS)
    a.cfg = config.load(paths.DEFAULT_MENUS)
    a.slots = [m for m in a.cfg.menus.values() if m.hotkey is not None]
    a.ctrl = 1
    posted = []
    a.posted = posted
    monkeypatch.setattr(W, "PostMessageW", lambda hwnd, msg, wp, lp: posted.append(msg))
    monkeypatch.setattr(W, "modifier_down", lambda vk: False)
    monkeypatch.setattr(W, "GetForegroundWindow", lambda: 100)
    monkeypatch.setattr(a, "target_in_front", lambda: True)
    monkeypatch.setattr(W, "class_name", lambda hwnd: "Plain")
    monkeypatch.setattr(W, "focus_window", lambda hwnd: 0)
    return a


def key(vk, flags=0, extra=0):
    return types.SimpleNamespace(vkCode=vk, flags=flags, dwExtraInfo=extra)


Q = ord("Q")


def test_real_hotkey_opens_the_ring_and_is_not_swallowed_in_the_starter_menu(app):
    assert app._on_key(W.WM_KEYDOWN, key(Q)) is False
    assert app.posted == [radiald.WM_APP_OPEN]
    assert app.held_vk == Q


def test_key_injected_by_another_program_counts(app):
    assert app._on_key(W.WM_KEYDOWN, key(Q, W.LLKHF_INJECTED, 0)) is False
    assert app.posted == [radiald.WM_APP_OPEN]


def test_own_injected_key_is_ignored(app):
    app._on_key(W.WM_KEYDOWN, key(Q, W.LLKHF_INJECTED, W.OWN_INPUT_MARKER))
    assert app.posted == []
    assert app.held_vk is None


def test_marker_only_counts_on_injected_keys(app):
    app._on_key(W.WM_KEYDOWN, key(Q, 0, W.OWN_INPUT_MARKER))
    assert app.posted == [radiald.WM_APP_OPEN]


def test_hotkey_is_ignored_in_a_dialog(app, monkeypatch):
    monkeypatch.setattr(W, "class_name", lambda hwnd: "#32770")
    assert app._on_key(W.WM_KEYDOWN, key(Q)) is False
    assert app.posted == []
    assert app.held_vk is None


@pytest.mark.parametrize("cls", ["Edit", "RichEdit20W", "RICHEDIT50W", "ComboBox"])
def test_hotkey_is_ignored_in_a_text_box(app, monkeypatch, cls):
    monkeypatch.setattr(W, "focus_window", lambda hwnd: 200)
    monkeypatch.setattr(W, "class_name", lambda hwnd: cls if hwnd == 200 else "Plain")
    app._on_key(W.WM_KEYDOWN, key(Q))
    assert app.posted == []


def test_other_focus_class_does_not_block_the_hotkey(app, monkeypatch):
    monkeypatch.setattr(W, "focus_window", lambda hwnd: 200)
    monkeypatch.setattr(W, "class_name", lambda hwnd: "Static")
    app._on_key(W.WM_KEYDOWN, key(Q))
    assert app.posted == [radiald.WM_APP_OPEN]


def ring(mode):
    return types.SimpleNamespace(mode=mode)


def test_typing_closes_a_ring_waiting_for_a_click(app):
    app.ring = ring("click")
    assert app._on_key(W.WM_KEYDOWN, key(ord("S"))) is False      # the key still reaches the program
    assert app.posted == [radiald.WM_APP_TYPING]


def test_typing_does_not_close_a_held_ring_or_react_to_modifiers_and_key_ups(app):
    app.ring = ring("hold")
    app._on_key(W.WM_KEYDOWN, key(ord("S")))
    app.ring = ring("click")
    app._on_key(W.WM_KEYDOWN, key(W.VK_SHIFT))
    app._on_key(W.WM_KEYUP, key(ord("S")))
    assert app.posted == []


def test_another_hotkey_does_not_count_as_typing(app):
    app.ring = ring("click")
    app._on_key(W.WM_KEYDOWN, key(Q))
    assert app.posted == [radiald.WM_APP_OPEN]
