"""More than one browser window (New window, Ctrl+N): each window's own settings in popout.json ("extras"), the copy a
new window starts as, the cap, the window a SHOW goes to, closing one for good, the windows that come back after the
process ended, and how long the process lives with several windows. No window is opened: pywebview's windows are fakes
and the Win32 calls are answered from a table kept by hwnd."""
import ctypes.wintypes as w
import json
import os

import pytest

import popout
import win32 as W

WORK = (0, 0, 1920, 1040)
MAIN = 0x100
OWN = os.getpid()


# --- popout.json ------------------------------------------------------------------------------------------
def test_window_settings_defaults_and_bad_values():
    assert popout.window_settings({}) == {"on_top": True, "kind": None, "side": "left", "column": True, "size": None,
                                          "window": None}
    bad = {"on_top": "no", "kind": "tool", "side": "up", "column": False, "size": True, "window": [1, 2]}
    assert popout.window_settings(bad) == popout.window_settings({}) | {"column": True}
    assert popout.window_settings({"pinned": 0})["on_top"] is False                      # the setting's earlier name
    good = {"on_top": False, "kind": "alpha", "side": "right", "column": "hidden", "size": 150,
            "window": {"x": 1, "y": 2, "width": 800, "height": 600}}
    assert popout.window_settings(good) == {"on_top": False, "kind": "alpha", "side": "right", "column": False,
                                            "size": 150, "window": good["window"]}


def test_extras_skips_bad_entries_and_keeps_to_the_cap():
    entries = [None, "x", {"id": ""}, {"id": 5}, {"id": "main"}, {"id": "a" * 41}, {"id": "a", "kind": "alpha"},
               {"id": "a", "kind": "brush"}, {"no": "id"}] + [{"id": f"w{i}"} for i in range(9)]
    got = popout.extras_state({"extras": entries})
    assert [e["id"] for e in got] == ["a", "w0", "w1", "w2", "w3"]                         # first of a repeated id wins
    assert len(got) == popout.MAX_WINDOWS - 1 and got[0]["kind"] == "alpha"
    for st in ({}, None, {"extras": "x"}, {"extras": {"id": "a"}}):
        assert popout.extras_state(st) == []


def test_a_new_window_copies_what_the_opener_shows():
    opener = popout.window_settings({"on_top": False, "kind": "alpha", "side": "right", "column": "hidden", "size": 120})
    assert popout.new_window_settings(opener, None) == {"on_top": False, "kind": "alpha", "side": "right",
                                                        "column": "hidden", "size": 120}
    asked = {"kind": "texture", "on_top": True, "column": True, "side": "left", "size": 999}
    assert popout.new_window_settings(opener, asked) == {"on_top": True, "kind": "texture", "side": "left",
                                                         "column": "shown", "size": 220}
    bad = {"kind": "tool", "on_top": 1, "column": "yes", "side": "up", "size": "90"}       # what the page sent is bad: the saved ones
    assert popout.new_window_settings(opener, bad) == popout.new_window_settings(opener, None)
    assert popout.new_window_settings(popout.window_settings({}), {}) == {"on_top": True, "side": "left", "column": "shown"}


def test_a_new_window_goes_down_and_right_of_its_opener_and_stays_on_the_screen():
    assert popout.offset_place((100, 100, 900, 700), 32, WORK) == (132, 132, 800, 600)
    assert popout.offset_place((1100, 400, 1920, 1040), 48, WORK) == (1100, 400, 820, 640)   # at the corner: kept inside


# --- the process with fake windows ----------------------------------------------------------------------------
class FakeWin:
    """A pywebview window: what its page is told, show, hide and destroy."""
    def __init__(self, env, hwnd):
        self.env, self.hwnd, self.js, self.destroyed, self.title = env, hwnd, [], 0, None

    def evaluate_js(self, code):
        self.js.append(code)
        return True

    def show(self):
        self.env.calls.append(("show", self.hwnd))
        self.env.up.add(self.hwnd)
        self.env.fg = self.hwnd                         # pywebview's show activates it

    def hide(self):
        self.env.calls.append(("hide", self.hwnd))
        self.env.up.discard(self.hwnd)

    def destroy(self):
        self.destroyed += 1
        self.env.up.discard(self.hwnd)

    def set_title(self, title):
        self.title = title


class FakeUser32:
    """winframe's user32: SetWindowPos keeps each window's place and topmost bit."""
    def __init__(self, env):
        self.env = env

    def SetWindowPos(self, hwnd, after, x, y, cx, cy, flags):
        if after in (popout.winframe.HWND_TOPMOST, popout.winframe.HWND_NOTOPMOST):
            self.env.topmost[hwnd] = after == popout.winframe.HWND_TOPMOST
        if not flags & W.SWP_NOMOVE:
            self.env.rects[hwnd] = (x, y, x + cx, y + cy)
        return 1

    def GetWindowLongW(self, hwnd, idx):
        return 0

    def SetWindowLongW(self, hwnd, idx, value):
        return 1


class SyncThread:
    """threading.Thread that runs its target when started, so a test sees what the thread did."""
    def __init__(self, target=None, args=(), kwargs=None, **kw):
        self.target, self.args, self.kwargs = target, args, kwargs or {}

    def start(self):
        self.target(*self.args, **self.kwargs)


class Env:
    def __init__(self):
        self.up, self.calls, self.topmost, self.rects, self.fg = set(), [], {}, {}, 0x999
        self.next = 0x200


@pytest.fixture
def env(monkeypatch, tmp_path):
    e = Env()
    monkeypatch.setattr(popout, "STATE_FILE", str(tmp_path / "popout.json"))
    monkeypatch.setattr(popout.user32, "IsWindowVisible", lambda h: h in e.up, raising=False)
    monkeypatch.setattr(popout.user32, "IsIconic", lambda h: 0, raising=False)
    monkeypatch.setattr(popout.user32, "IsZoomed", lambda h: 0, raising=False)
    monkeypatch.setattr(popout.user32, "ShowWindow", lambda h, cmd: e.calls.append(("ShowWindow", h, cmd)) or 1,
                        raising=False)
    monkeypatch.setattr(popout.user32, "SetForegroundWindow", lambda h: e.calls.append(("SetForegroundWindow", h)),
                        raising=False)
    monkeypatch.setattr(popout.winframe, "user32", FakeUser32(e))
    monkeypatch.setattr(popout.winframe, "force_foreground", lambda h: setattr(e, "fg", h) or True)
    monkeypatch.setattr(popout.winframe, "placement_record", lambda h: None)
    monkeypatch.setattr(popout.winframe, "normal_rect", lambda h: (*e.rects[h], False) if h in e.rects else None)
    monkeypatch.setattr(popout.winframe, "bring_on_screen", lambda h, near: False)
    monkeypatch.setattr(popout.winframe, "_work_of", lambda rect: WORK)
    monkeypatch.setattr(popout.winframe, "work_area", lambda h: w.RECT(*WORK))

    def saved_window(saved, mw, mh):
        try:
            return saved["x"], saved["y"], saved["width"], saved["height"], bool(saved.get("maximized"))
        except (TypeError, KeyError):
            return None
    monkeypatch.setattr(popout.winframe, "saved_window", saved_window)
    monkeypatch.setattr(popout.BrowserWindow, "_rect", lambda self: w.RECT(*e.rects.get(self.hwnd, (0, 0, 0, 0))))
    monkeypatch.setattr(popout.BrowserWindow, "_scale", lambda self: 1.0)
    monkeypatch.setattr(popout.BrowserWindow, "_sync_theme", lambda self: None)
    monkeypatch.setattr(popout.BrowserWindow, "_focus_page", lambda self: None)
    monkeypatch.setattr(popout.W, "send_keys", lambda keys: None)
    monkeypatch.setattr(popout.W, "nudge_mouse", lambda: None)
    monkeypatch.setattr(popout.W, "GetForegroundWindow", lambda: e.fg)
    monkeypatch.setattr(popout.W, "window_pid", lambda h: OWN if h == MAIN or 0x200 <= h < 0x300 else 4242)
    monkeypatch.setattr(popout, "_is_target", lambda h: h == 0x999)
    monkeypatch.setattr(popout, "_find_target", lambda: 0x999)
    monkeypatch.setattr(popout.threading, "Thread", SyncThread)
    return e


def _pop(env, managed=True, **opts):
    pop = popout.Popout({"tag": None, "kind": None, "managed": managed, "show": False, "zbrush": 0, **opts})
    pop.window, pop.hwnd, pop.ready = FakeWin(env, MAIN), MAIN, True
    pop._loaded.set()
    env.rects[MAIN] = (100, 100, 880, 660)
    pop.quits = []
    pop.quit = lambda why="", idle=False: pop.quits.append(why)

    def open_extra(ext):                                # what _open_extra does, without pywebview
        ext.hwnd, env.next = env.next, env.next + 1
        ext.window = FakeWin(env, ext.hwnd)
        ext._loaded.set()
        ext.ready = True
        pop.opened.append(ext.id)
        return True
    pop.opened = []
    pop._open_extra = open_extra
    return pop


def drain(pop):
    """Runs what was queued for the work thread (popout.json "last_used")."""
    while not pop._work.empty():
        fn, args = pop._work.get()
        fn(*args)


def state(tmp_path):
    return json.loads((tmp_path / "popout.json").read_text(encoding="utf-8"))


@pytest.fixture
def pop(env):
    return _pop(env)


def shown_main(pop, env):
    pop.request_show(None, 0, False)
    assert MAIN in env.up
    return pop


def test_new_window_copies_the_opener_and_opens_beside_it(pop, env, tmp_path):
    popout._update_state(on_top=False, kind="alpha", side="right", column="hidden", size=140)
    shown_main(pop, env)
    x0, y0 = env.rects[MAIN][:2]                                       # centred on the work area: nothing was saved
    got = popout.PopoutApi(pop).popout_new_window({"kind": "material", "on_top": False, "column": False, "side": "right",
                                                    "size": 140})
    assert got == {"ok": True, "windows": 2, "max_windows": popout.MAX_WINDOWS}
    ext = pop.extras[0]
    entry = state(tmp_path)["extras"][0]
    assert entry == {"id": ext.id, "on_top": False, "side": "right", "column": "hidden", "kind": "material", "size": 140,
                     "window": {"x": x0 + 32, "y": y0 + 32, "width": 780, "height": 560, "maximized": False}}
    assert ext.hwnd in env.up and env.rects[ext.hwnd] == (x0 + 32, y0 + 32, x0 + 812, y0 + 592)   # where it was meant to go
    assert env.topmost[ext.hwnd] is False and env.fg == ext.hwnd                           # its own Keep on top, in front
    assert any('"reset": true' in js for js in ext.window.js)                              # afresh: no search, All
    assert any("__popoutWindows" in js and '"windows": 2' in js for js in pop.window.js)   # the opener's button counts it
    st = state(tmp_path)
    assert (st["kind"], st["on_top"], st["size"]) == ("alpha", False, 140)                 # the first window's own: untouched
    api = popout.PopoutApi(ext).popout_get_state()
    assert (api["extra"], api["kind"], api["side"], api["column"], api["size"], api["on_top"]) == \
        (True, "material", "right", False, 140, False)
    assert api["windows"] == 2 and popout.PopoutApi(pop).popout_get_state()["extra"] is False


def test_at_most_six_windows(pop, env, tmp_path):
    shown_main(pop, env)
    api = popout.PopoutApi(pop)
    for n in range(2, popout.MAX_WINDOWS + 1):
        assert api.popout_new_window({})["windows"] == n
    got = popout.PopoutApi(pop.extras[-1]).popout_new_window({})
    assert got == {"ok": False, "error": popout.CAP_MESSAGE, "windows": 6, "max_windows": 6}
    assert got["error"] == "Six browser windows are open. Close one to open another."
    assert len(state(tmp_path)["extras"]) == 5 and len(pop.extras) == 5
    pop.extras[0].close("close button")                                                   # one closed: one more can open
    assert api.popout_new_window({})["ok"] is True


def test_each_window_writes_its_own_settings(pop, env, tmp_path):
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({"on_top": True})
    ext = pop.extras[0]
    a, b = popout.PopoutApi(pop), popout.PopoutApi(ext)
    b.popout_set_on_top(False)
    assert env.topmost[ext.hwnd] is False and env.topmost[MAIN] is True                   # pinned one, not the other
    assert ext.on_top is False and pop.on_top is True
    b.popout_set_size(150)
    b.popout_set_side("right")
    b.popout_set_column(False)
    b.popout_set_kind("texture")
    a.popout_set_kind("alpha")
    st = state(tmp_path)
    e = st["extras"][0]
    assert (e["on_top"], e["size"], e["side"], e["column"], e["kind"]) == (False, 150, "right", "hidden", "texture")
    assert st.get("on_top", True) is True and "size" not in st and "side" not in st and st["kind"] == "alpha"
    a.popout_set_on_top(False)
    assert state(tmp_path)["on_top"] is False and state(tmp_path)["extras"][0]["on_top"] is False


def test_a_show_goes_to_the_window_used_last(pop, env, tmp_path, monkeypatch):
    released = []
    monkeypatch.setattr(pop, "release_focus", lambda: released.append(1))
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    ext = pop.extras[0]
    drain(pop)
    assert pop.last_used is ext and state(tmp_path)["last_used"] == ext.id
    env.fg = 0x999                                                     # ZBrush in front
    pop.request_show("blocking", 0, True, "alpha")
    assert env.fg == ext.hwnd
    assert any('"tag": "blocking"' in js and '"kind": "alpha"' in js for js in ext.window.js)
    assert not any('"tag": "blocking"' in js for js in pop.window.js)
    pop.request_show(None, 0, True)                                    # in front: the hotkey hands the keyboard back
    assert released == [1]
    pop.on_activate()                                                  # the user clicked into the first window
    drain(pop)
    assert pop.last_used is pop and state(tmp_path)["last_used"] == "main"
    env.fg = 0x999
    pop.request_show(None, 0, True)
    assert env.fg == MAIN


def test_a_show_after_the_window_used_last_closed_goes_to_the_first(pop, env, monkeypatch):
    shown_main(pop, env)
    pop.close("close button")                                          # the first window hidden, the process managed
    assert MAIN not in env.up
    pop.request_show(None, 0, False)
    popout.PopoutApi(pop).popout_new_window({})
    ext = pop.extras[0]
    assert pop.last_used is ext
    ext.close("close button")
    assert pop.last_used is pop
    pop.close("close button")
    pop.request_show(None, 0, False)
    assert MAIN in env.up and env.fg == MAIN


def test_closing_another_window_removes_it_for_good(pop, env, tmp_path):
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    popout.PopoutApi(pop).popout_new_window({})
    ext, other = pop.extras
    popout.PopoutApi(ext).popout_hide()                                # its X
    assert ext.window.destroyed == 1 and ext not in pop.extras and ext.closing
    assert [e["id"] for e in state(tmp_path)["extras"]] == [other.id]
    assert any('"windows": 2' in js for js in pop.window.js[-1:])      # the count goes down on the pages left
    assert pop.quits == []


def test_alt_f4_on_another_window_closes_it_for_good_but_a_quit_keeps_it(pop, env, tmp_path):
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    popout.PopoutApi(pop).popout_new_window({})
    ext, other = pop.extras
    assert ext.on_closing() is False                                   # Alt+F4: cancelled, and closed by close()
    assert ext.closing and [e["id"] for e in state(tmp_path)["extras"]] == [other.id]
    pop.quitting = True
    assert other.on_closing() is None                                  # the process quitting: it just goes
    assert [e["id"] for e in state(tmp_path)["extras"]] == [other.id] and not other.closing


def test_a_session_end_keeps_the_other_windows_and_saves_where_they_are(pop, env, tmp_path, monkeypatch):
    monkeypatch.setattr(popout.threading, "Timer", lambda *a, **k: type("T", (), {"start": lambda self: None})())
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    ext = pop.extras[0]
    monkeypatch.setattr(popout.winframe, "placement_record",
                        lambda h: {"x": 7, "y": 8, "width": 700, "height": 500, "maximized": h == MAIN})
    pop.on_query_end()
    assert ext.on_closing() is None
    pop.on_end_session(True)
    st = state(tmp_path)
    assert st["extras"][0]["window"] == {"x": 7, "y": 8, "width": 700, "height": 500, "maximized": False}
    assert st["window"]["maximized"] is True


def test_quit_saves_and_destroys_every_window_and_keeps_the_others_listed(env, tmp_path, monkeypatch):
    pop = _pop(env)
    del pop.quit                                                       # the real one
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    ext = pop.extras[0]
    exits, started = [], []

    class Recorded:
        def __init__(self, target=None, **kw):
            started.append(target)

        def start(self):
            pass
    monkeypatch.setattr(popout.threading, "Thread", Recorded)
    monkeypatch.setattr(popout.os, "_exit", exits.append)
    monkeypatch.setattr(pop, "stop_ctl", lambda: None)
    monkeypatch.setattr(popout.winframe, "placement_record",
                        lambda h: {"x": 50, "y": 60, "width": 700, "height": 500, "maximized": False})
    pop.quit("the app asked")
    assert ext.window.destroyed == 1 and pop.window.destroyed == 1
    assert state(tmp_path)["extras"][0]["id"] == ext.id
    assert state(tmp_path)["extras"][0]["window"]["x"] == 50


def _with_extras(tmp_path, n=2, last=None):
    entries = [{"id": f"e{i}", "kind": "alpha", "on_top": False,
                "window": {"x": 300 + i, "y": 200, "width": 700, "height": 500, "maximized": False}} for i in range(n)]
    popout._update_state(extras=entries, last_used=last or "main")
    return [e["id"] for e in entries]


def test_the_other_windows_come_back_at_the_first_show(pop, env, tmp_path):
    ids = _with_extras(tmp_path)
    pop.request_show(None, 0, False)
    assert [e.id for e in pop.extras] == ids and pop.opened == ids
    assert all(e.hwnd in env.up for e in pop.extras)
    assert env.rects[pop.extras[1].hwnd][:2] == (301, 200)                                 # where it was
    assert env.topmost[pop.extras[0].hwnd] is False
    assert MAIN in env.up and env.fg == MAIN and pop.last_used is pop                    # the one used last has the keyboard
    pop.close("close button")
    pop.request_show(None, 0, False)
    assert pop.opened == ids                                                               # once per process


def test_the_window_used_last_answers_the_show_that_brings_it_back(pop, env, tmp_path):
    ids = _with_extras(tmp_path, last="e1")
    pop.request_show("blocking", 0, False)
    assert pop.opened[0] == "e1"                                                           # made first, the others after
    target = next(e for e in pop.extras if e.id == "e1")
    assert pop.last_used is target and env.fg == target.hwnd and MAIN not in env.up
    assert any('"tag": "blocking"' in js for js in target.window.js)
    assert sorted(pop.opened) == ids


def test_they_do_not_come_back_with_the_strip_or_a_hidden_start(pop, env, tmp_path, monkeypatch):
    _with_extras(tmp_path)
    monkeypatch.setattr(pop, "_wait_booted", lambda timeout_s=5.0: True)
    monkeypatch.setattr(pop, "_strip_up", lambda why: setattr(pop, "mode", "strip"))
    pop._first_show(None)                                             # a hidden pre-warm, the strip off
    assert pop.extras == [] and pop.opened == []
    pop.strip_on = True
    pop._first_show(None)                                             # the strip up by itself
    assert pop.mode == "strip" and pop.extras == []
    assert len(state(tmp_path)["extras"]) == 2                        # still listed for the next SHOW


def test_a_process_not_managed_ends_only_with_its_last_window(env):
    pop = _pop(env, managed=False)
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    ext = pop.extras[0]
    pop.close("close button")
    assert MAIN not in env.up and pop.quits == []                      # another window is up
    ext.close("close button")
    assert pop.quits == ["closed by the user"]


def test_a_managed_process_keeps_running_hidden_when_the_last_window_closes(pop, env):
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    pop.close("close button")
    pop.extras[0].close("close button")
    assert pop.quits == []


def test_no_idle_quit_while_another_window_is_up(env, tmp_path, monkeypatch):
    cfg = tmp_path / "radial.json"
    cfg.write_text(json.dumps({"menus": {}, "browser": {"quit_after_minutes": 10}}), encoding="utf-8")
    monkeypatch.setenv("ZORBIT_CONFIG_FILE", str(cfg))
    pop = _pop(env)
    t = [1000.0]
    pop._now = lambda: t[0]
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    pop.close("close button")                                          # the first window hidden, another one up
    pop.idle_tick()
    t[0] += 3600
    pop.idle_tick()
    assert pop.quits == []
    pop.extras[0].close("close button")
    pop.idle_tick()
    t[0] += 10 * 60
    pop.idle_tick()
    assert len(pop.quits) == 1 and "unused" in pop.quits[0]


def test_the_app_gone_with_another_window_up_keeps_the_process(pop, env):
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    pop.close("close button")
    pop.app_gone("the app is gone")
    assert pop.quits == [] and pop.managed is False
    pop.extras[0].close("close button")
    assert pop.quits == ["closed by the user"]                         # not managed from then on


def test_the_strip_still_goes_with_the_app_when_another_window_stays(pop, env, monkeypatch):
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    monkeypatch.setattr(pop, "_strip_frame", lambda on: None)
    pop.mode, pop.strip_on = "strip", True                            # the first window became the strip
    pop.app_gone("the app is gone")
    assert pop.quits == [] and pop.managed is False
    assert MAIN not in env.up and pop.mode == "browser" and pop.strip_on
    assert pop.extras[0].hwnd in env.up


def test_a_pick_from_another_window_hands_the_keyboard_back_while_the_first_is_the_strip(pop, env, monkeypatch):
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    ext = pop.extras[0]
    pop.mode = "strip"
    monkeypatch.setattr(popout.W, "find_message_window", lambda cls: 0)
    popout.PopoutApi(ext).popout_pick("Standard", "brush")
    assert ("SetForegroundWindow", 0x999) in env.calls


def test_the_theme_reaches_every_window_that_is_up(pop, env, monkeypatch):
    shown_main(pop, env)
    popout.PopoutApi(pop).popout_new_window({})
    synced = []
    monkeypatch.setattr(popout.BrowserWindow, "_sync_theme", lambda self: synced.append(self))
    pop.theme_tick()
    assert synced == [pop, pop.extras[0]]
    pop.close("close button")
    synced.clear()
    pop.theme_tick()
    assert synced == [pop.extras[0]]
