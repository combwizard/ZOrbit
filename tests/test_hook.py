"""The keyboard hook's decisions (App._on_key), driven with fake key structs and a stubbed Win32 layer, and the
hook thread's start, stop and failure paths with a fake SetWindowsHookExW."""
import ctypes
import json
import time
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
    a._set_slots([m for m in a.cfg.menus.values() if m.hotkey is not None], a.cfg.browser_key)
    a.ctrl = 1
    posted = []
    a.posted = posted
    monkeypatch.setattr(W, "PostMessageW", lambda hwnd, msg, wp, lp: posted.append(msg))
    monkeypatch.setattr(W, "modifier_down", lambda vk: False)
    monkeypatch.setattr(W, "GetForegroundWindow", lambda: 100)
    monkeypatch.setattr(a, "target_in_front", lambda on_hook=False: True)
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


def test_hook_state_is_built_from_two_menus_and_a_browser_key():
    def menu(vk, ctrl=False, alt=False, shift=False, swallow=False):
        return types.SimpleNamespace(hotkey=config.Hotkey(vk, ctrl, alt, shift), swallow=swallow)

    state = radiald.HookState.build([menu(ord("Q")), menu(ord("W"), alt=True, swallow=True)],
                                    config.Hotkey(ord("B"), shift=True))
    assert state.slots == ((ord("Q"), False, False, False, False, 0), (ord("W"), False, True, False, True, 1))
    assert state.browser == (ord("B"), False, False, True)
    assert radiald.HookState.build([], None) == radiald.HookState((), None)


def test_load_config_swaps_in_a_new_snapshot(tmp_path, monkeypatch):
    path = tmp_path / "radial.json"
    path.write_text(json.dumps({"menus": {
        "a": {"title": "A", "hotkey": "Q", "swallow": False, "items": [{"brush": "Standard"}]},
        "b": {"title": "B", "hotkey": "Alt+W", "swallow": True, "items": [{"brush": "Move"}]},
        "c": {"title": "C", "items": [{"brush": "Move"}]}},
        "browser": {"hotkey": "Shift+B"}}), encoding="utf-8")
    monkeypatch.setenv("ZORBIT_TAGS_FILE", str(tmp_path / "tags.json"))
    a = radiald.App(str(path))
    monkeypatch.setattr(a, "_prefetch", lambda: None)
    monkeypatch.setattr(a, "_schedule_prewarm", lambda: None)
    before = a._hook_state
    a.load_config(force=True)
    assert a._hook_state is not before
    assert [m.id for m in a.slots] == ["a", "b"]            # the hook's slot index is the position in App.slots
    assert a._hook_state.slots == ((ord("Q"), False, False, False, False, 0),
                                   (ord("W"), False, True, False, True, 1))
    assert a._hook_state.browser == (ord("B"), False, False, True)


def test_on_key_uses_the_snapshot_and_a_browser_key_opens_the_browser(app, monkeypatch):
    app._hook_state = radiald.HookState((), (ord("B"), False, False, False))
    assert app._on_key(W.WM_KEYDOWN, key(Q)) is False         # no slots in the snapshot, whatever App.slots says
    assert app.posted == []
    assert app._on_key(W.WM_KEYDOWN, key(ord("B"))) is True
    assert app.posted == [radiald.WM_APP_BROWSER]
    assert app._browser_vk == ord("B")
    assert app._on_key(W.WM_KEYUP, key(ord("B"))) is True and app._browser_vk is None


def test_escape_cancels_an_open_ring(app):
    app.ring = ring("hold")
    assert app._on_key(W.WM_KEYDOWN, key(W.VK_ESCAPE)) is True
    assert app.posted == [radiald.WM_APP_CANCEL]


def test_the_main_thread_lets_go_of_a_key_through_the_hook_thread(app):
    app.held_vk = Q
    app._on_hook_command(radiald.WM_HOOK_RELEASE_HELD, ord("S"), 0)      # not the key that was stuck
    assert app.held_vk == Q
    app._on_hook_command(radiald.WM_HOOK_RELEASE_HELD, Q, 0)
    assert app.held_vk is None and app.posted == [radiald.WM_APP_KEYUP]
    app._browser_vk = ord("B")
    app._on_hook_command(radiald.WM_HOOK_RELEASE_BROWSER, ord("B"), 0)
    assert app._browser_vk is None


# --- the hook thread, with no real hook installed ----------------------------------------------------------------
@pytest.fixture
def fake_hook(monkeypatch):
    """Replaces SetWindowsHookExW and UnhookWindowsHookEx; the thread and its message loop are real."""
    calls = types.SimpleNamespace(set=[], unhooked=[], result=0x1234)

    def set_hook(kind, proc, module, tid):
        calls.set.append((kind, tid))
        return calls.result

    monkeypatch.setattr(W, "SetWindowsHookExW", set_hook)
    monkeypatch.setattr(W, "UnhookWindowsHookEx", lambda h: calls.unhooked.append(h) or 1)
    return calls


def make_thread(commands=None):
    logged = []
    t = radiald.HookThread(lambda wparam, kb: False, lambda *a: (commands if commands is not None else []).append(a), logged.append)
    t.logged = logged
    return t


def test_hook_thread_installs_on_its_own_thread_and_stops_cleanly(fake_hook):
    t = make_thread()
    t.start_and_wait()
    try:
        assert t.is_alive() and t.error is None and t.handle == 0x1234
        assert t.thread_id and t.thread_id != W.GetCurrentThreadId()
        assert fake_hook.set == [(W.WH_KEYBOARD_LL, 0)]
    finally:
        t.stop()
    assert not t.is_alive()
    assert fake_hook.unhooked == [0x1234]                      # the thread took its own hook out


def test_hook_thread_reinstalls_on_request_without_a_gap(fake_hook):
    t = make_thread()
    t.start_and_wait()
    try:
        fake_hook.result = 0x5678
        assert t.post(radiald.WM_HOOK_REHOOK)
        for _ in range(100):
            if t.handle == 0x5678:
                break
            time.sleep(0.02)
        assert t.handle == 0x5678
        assert fake_hook.unhooked == [0x1234]                  # the old hook goes only after the new one is in
        assert "hook re-installed" in t.logged
    finally:
        t.stop()
    assert fake_hook.unhooked == [0x1234, 0x5678]


def test_hook_thread_passes_other_thread_messages_to_the_command_handler(fake_hook):
    seen = []
    t = make_thread(seen)
    t.start_and_wait()
    try:
        t.post(radiald.WM_HOOK_RELEASE_HELD, 81)
        for _ in range(100):
            if seen:
                break
            time.sleep(0.02)
    finally:
        t.stop()
    assert seen == [(radiald.WM_HOOK_RELEASE_HELD, 81, 0)]


def test_hook_install_failure_is_reported_to_the_caller(fake_hook):
    fake_hook.result = 0
    ctypes.set_last_error(5)
    t = make_thread()
    with pytest.raises(OSError):
        t.start_and_wait()
    t.join(2)
    assert not t.is_alive() and isinstance(t.error, OSError)
    assert fake_hook.unhooked == []
    assert t.post(radiald.WM_HOOK_REHOOK) is False             # nothing to post to any more


def test_app_start_and_stop_hook(fake_hook):
    a = radiald.App(paths.DEFAULT_MENUS)
    a.start_hook()
    assert a._hook.is_alive()
    hook = a._hook
    a.stop_hook()
    assert a._hook is None and not hook.is_alive()
    a.stop_hook()                                              # stopping twice is harmless
