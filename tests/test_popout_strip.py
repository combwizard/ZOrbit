"""The browser's strip (#40): its settings in popout.json, where it goes the first time, the switches between the strip
and the browser, showing it without taking the foreground, the pick that hands nothing back, and fitting the window to
the page. No window is opened: the Win32 calls the Popout makes are recorded instead."""
import ctypes.wintypes as w
import json

import pytest

import popout
import toast
import win32 as W

TOOL, NOACT, APP = W.WS_EX_TOOLWINDOW, W.WS_EX_NOACTIVATE, popout.WS_EX_APPWINDOW
WORK = (0, 0, 1920, 1040)


# --- popout.json --------------------------------------------------------------------------------------
def test_the_strip_is_off_and_vertical_on_brushes_until_set():
    assert popout.strip_state({}) == {"on": False, "orient": "vertical", "kind": "brush", "window": None, "wrap": False}
    assert popout.strip_state(None)["on"] is False


def test_the_strip_settings_are_read_back():
    st = {"strip_on": True, "strip": {"orient": "horizontal", "kind": "alpha", "window": {"x": -1200, "y": 40}, "wrap": True}}
    assert popout.strip_state(st) == {"on": True, "orient": "horizontal", "kind": "alpha", "window": (-1200, 40), "wrap": True}


@pytest.mark.parametrize("bad", [
    {"strip_on": 1, "strip": {"orient": "diagonal", "kind": "tool", "window": {"x": "1", "y": 2}, "wrap": "yes"}},
    {"strip_on": "true", "strip": {"window": {"x": True, "y": 2}}},
    {"strip_on": None, "strip": {"window": [10, 20]}},
    {"strip": "vertical"},
    {"strip": {"window": {"x": 1.5, "y": 2}}},
])
def test_a_value_that_is_not_what_it_should_be_counts_as_missing(bad):
    assert popout.strip_state(bad) == popout.strip_state({})


def _state(tmp_path):
    return json.loads((tmp_path / "popout.json").read_text(encoding="utf-8"))


def test_strip_set_saves_what_it_names_and_keeps_the_rest(pop, tmp_path):
    popout._update_state(window={"x": 1, "y": 2, "width": 800, "height": 600, "maximized": False}, size=120)
    popout._update_strip(window={"x": 5, "y": 6})
    assert pop.strip_set({"orient": "horizontal"}) == {"on": False, "orient": "horizontal", "kind": "brush", "wrap": False}
    pop.strip_set({"kind": "material", "wrap": True})
    st = _state(tmp_path)
    assert st["strip"] == {"window": {"x": 5, "y": 6}, "orient": "horizontal", "kind": "material", "wrap": True}
    assert st["window"]["width"] == 800 and st["size"] == 120               # the browser's own keys stay


@pytest.mark.parametrize("bad", [{"orient": "up"}, {"kind": "tool"}, {"wrap": 1}, None, "horizontal", {"window": {"x": 0, "y": 0}}])
def test_strip_set_leaves_out_a_bad_value(pop, tmp_path, bad):
    pop.strip_set(bad)
    assert "strip" not in _state(tmp_path) if (tmp_path / "popout.json").exists() else True


def test_the_page_gets_the_strip_settings_and_the_mode(pop):
    pop.strip_set({"orient": "horizontal", "kind": "texture"})
    got = popout.PopoutApi(pop).popout_get_state()
    assert got["mode"] == "browser"
    assert got["strip"] == {"on": False, "orient": "horizontal", "kind": "texture", "wrap": False}


# --- where it goes the first time ------------------------------------------------------------------------
def test_vertical_goes_against_the_left_edge_of_zbrush_centred_top_to_bottom():
    assert popout.strip_first_place("vertical", (64, 400), (100, 50, 1700, 1000), WORK, 8) == (108, 325)


def test_horizontal_goes_against_the_top_of_zbrush_centred_across():
    assert popout.strip_first_place("horizontal", (600, 64), (100, 50, 1700, 1000), WORK, 8) == (600, 58)


def test_without_zbrush_the_work_area_is_used():
    assert popout.strip_first_place("vertical", (64, 400), None, WORK, 8) == (8, 320)
    assert popout.strip_first_place("horizontal", (600, 64), None, WORK, 8) == (660, 8)


def test_a_maximised_zbrush_counts_only_on_the_work_area():
    # a maximised window reaches 8 px past the work area on every side
    assert popout.strip_first_place("vertical", (64, 400), (-8, -8, 1928, 1048), WORK, 8) == (8, 320)


def test_a_zbrush_on_another_monitor_falls_back_to_the_work_area():
    assert popout.strip_first_place("vertical", (64, 400), (2000, 0, 3900, 1000), WORK, 8) == (8, 320)


def test_a_strip_taller_than_zbrush_is_kept_on_the_screen():
    assert popout.strip_first_place("vertical", (64, 900), (100, 700, 900, 1000), WORK, 8) == (108, 140)


def test_keep_inside():
    assert popout.keep_inside(1900, -20, 64, 400, WORK) == (1856, 0)
    assert popout.keep_inside(-3000, 2000, 64, 400, WORK) == (0, 640)
    assert popout.keep_inside(10, 10, 4000, 4000, WORK) == (0, 0)          # larger than the screen: the corner wins


def test_fit_size_scales_and_guards():
    assert popout.fit_size({"w": 64, "h": 400}, 1.5) == (96, 600)
    assert popout.fit_size({"w": 63.6, "h": 0}, 1.0) == (64, 16)
    assert popout.fit_size({"w": "64", "h": True}, 1.0) == popout.STRIP_START
    assert popout.fit_size(None, 2.0) == (popout.STRIP_START[0] * 2, popout.STRIP_START[1] * 2)


# --- the window, with Win32 recorded ----------------------------------------------------------------------
class _Window:
    """pywebview's window: what the page is told, and show / hide."""
    def __init__(self, pop, fit=None):
        self.pop, self.js, self.fit = pop, [], fit or {"w": 64, "h": 400}

    def evaluate_js(self, code):
        self.js.append(code)
        if "__popoutShow" in code and '"mode": "strip"' in code:
            return self.fit
        return True

    def show(self):
        self.pop.calls.append(("show",))
        self.pop.up = True

    def hide(self):
        self.pop.calls.append(("hide",))
        self.pop.up = False

    def destroy(self):
        pass


class _User32:
    """winframe's user32: styles and SetWindowPos."""
    def __init__(self, pop):
        self.pop, self.ex = pop, 0x50108                   # what WinForms gives the browser: APPWINDOW, TOPMOST and two more

    def GetWindowLongW(self, hwnd, idx):
        return self.ex

    def SetWindowLongW(self, hwnd, idx, value):
        self.ex = value & 0xFFFFFFFF
        return 1

    def SetWindowPos(self, hwnd, after, x, y, cx, cy, flags):
        self.pop.calls.append(("pos", after, x, y, cx, cy, flags))
        if not flags & W.SWP_NOMOVE:
            self.pop.rect = (x, y, x + cx, y + cy) if not flags & W.SWP_NOSIZE else self.pop.rect
        elif not flags & W.SWP_NOSIZE:
            self.pop.rect = (self.pop.rect[0], self.pop.rect[1], self.pop.rect[0] + cx, self.pop.rect[1] + cy)
        return 1


@pytest.fixture
def pop(monkeypatch, tmp_path):
    monkeypatch.setattr(popout, "STATE_FILE", str(tmp_path / "popout.json"))
    p = popout.Popout({"tag": None, "kind": None, "managed": True, "show": False, "zbrush": 0})
    p.calls, p.up, p.rect, p.fg = [], False, (500, 300, 1280, 860), 0x777
    p.window = _Window(p)
    p.hwnd, p.ctl, p.ready = 0x1234, 0, True
    u = _User32(p)
    p.u32 = u
    monkeypatch.setattr(p, "visible", lambda: p.up)
    monkeypatch.setattr(p, "_rect", lambda: w.RECT(*p.rect))
    monkeypatch.setattr(p, "_sync_theme", lambda: None)
    monkeypatch.setattr(p, "_focus_page", lambda: None)
    monkeypatch.setattr(p, "_scale", lambda: 1.0)
    monkeypatch.setattr(p, "_place", lambda zb: (40, 50, 780, 560, False))
    monkeypatch.setattr(popout.winframe, "user32", u)
    monkeypatch.setattr(popout.winframe, "set_fitted", lambda hwnd, on: p.calls.append(("fitted", on)) or True)
    monkeypatch.setattr(popout.winframe, "force_foreground", lambda hwnd: p.calls.append(("force_foreground",)) or True)
    monkeypatch.setattr(popout.winframe, "placement_record", lambda hwnd: None)
    monkeypatch.setattr(popout.winframe, "bring_on_screen", lambda hwnd, near: False)
    monkeypatch.setattr(popout.winframe, "_work_of", lambda rect: WORK)
    monkeypatch.setattr(popout.winframe, "_primary_work_area", lambda: w.RECT(*WORK))

    def show_window(hwnd, cmd):
        p.calls.append(("ShowWindow", cmd))
        p.up = cmd != popout.SW_HIDE
        return 1
    monkeypatch.setattr(popout.user32, "ShowWindow", show_window, raising=False)
    monkeypatch.setattr(popout.user32, "IsIconic", lambda hwnd: 0, raising=False)
    monkeypatch.setattr(popout.user32, "IsZoomed", lambda hwnd: 0, raising=False)
    monkeypatch.setattr(popout.user32, "SetForegroundWindow", lambda hwnd: p.calls.append(("SetForegroundWindow", hwnd)), raising=False)
    monkeypatch.setattr(popout.W, "send_keys", lambda keys: p.calls.append(("send_keys",)))
    monkeypatch.setattr(popout.W, "nudge_mouse", lambda: p.calls.append(("nudge",)))
    monkeypatch.setattr(popout.W, "GetForegroundWindow", lambda: p.fg)
    monkeypatch.setattr(popout, "_is_target", lambda hwnd: False)
    monkeypatch.setattr(popout, "_find_target", lambda: 0)
    return p


def names(p):
    return [c[0] for c in p.calls]


def strip_style(p):
    return bool(p.u32.ex & TOOL) and bool(p.u32.ex & NOACT) and not p.u32.ex & APP


def test_the_strip_button_turns_it_on_and_puts_it_up_in_the_browsers_place(pop, tmp_path):
    pop.up = True                                          # the browser is up
    pop.strip_from_browser()
    assert _state(tmp_path)["strip_on"] is True and pop.strip_on
    assert pop.mode == "strip" and pop.up
    assert names(pop).index("hide") < names(pop).index("ShowWindow")
    assert ("ShowWindow", W.SW_SHOWNOACTIVATE) in pop.calls
    assert ("fitted", True) in pop.calls and strip_style(pop)
    assert "force_foreground" not in names(pop) and "send_keys" not in names(pop) and "show" not in names(pop)
    assert any(c[0] == "pos" and c[1] == popout.winframe.HWND_TOPMOST and c[6] & W.SWP_NOACTIVATE for c in pop.calls)
    assert any('"mode": "strip"' in js for js in pop.window.js)


def test_the_strip_is_sized_to_what_the_page_measured_and_placed_beside_zbrush(pop):
    pop.window.fit = {"w": 64, "h": 420}
    pop.show_strip("test")
    sized = [c for c in pop.calls if c[0] == "pos" and c[4] == 64]
    assert sized and sized[0][2:6] == (8, 310, 64, 420)    # no ZBrush: the left edge of the work area, centred


def test_a_saved_place_is_used_and_kept_on_the_screen(pop):
    popout._update_strip(window={"x": 1900, "y": 100})
    pop.show_strip("test")
    assert pop.rect[:2] == (1856, 100)


def test_open_browser_puts_the_browser_back_with_its_own_styles_and_activates_it(pop, tmp_path):
    pop.strip_from_browser()
    pop.calls.clear()
    pop.open_browser(None, 0, "alpha", True, "Open browser")
    assert pop.mode == "browser" and pop.strip_on
    assert ("fitted", False) in pop.calls
    assert not pop.u32.ex & (TOOL | NOACT) and pop.u32.ex & APP           # as WinForms had it
    assert "show" in names(pop) and "force_foreground" in names(pop)
    assert any('"mode": "browser"' in js and '"kind": "alpha"' in js for js in pop.window.js)
    assert _state(tmp_path)["strip"]["window"] == {"x": 8, "y": 320}     # where the strip was, for next time


def test_the_close_button_goes_back_to_the_strip_while_it_is_on(pop, monkeypatch):
    quits = []
    monkeypatch.setattr(pop, "quit", lambda why="", idle=False: quits.append(why))
    pop.managed = False
    pop.strip_from_browser()
    pop.open_browser()
    pop.close(why="close button")
    assert pop.mode == "strip" and pop.up and quits == []


def test_the_close_button_hides_as_before_with_the_strip_off(pop, monkeypatch):
    quits = []
    monkeypatch.setattr(pop, "quit", lambda why="", idle=False: quits.append(why))
    pop.up = True
    pop.managed = False
    pop.close(why="close button")
    assert not pop.up and pop.mode == "browser" and quits == ["closed by the user"]


def test_hide_strip_turns_it_off_and_hides_the_window(pop, tmp_path, monkeypatch):
    quits = []
    monkeypatch.setattr(pop, "quit", lambda why="", idle=False: quits.append(why))
    pop.strip_from_browser()
    pop.hide_strip()
    assert _state(tmp_path)["strip_on"] is False and not pop.strip_on
    assert not pop.up and pop.mode == "browser"            # hidden, and the browser for the next SHOW
    assert quits == []                                      # managed: the app can show it again
    assert ("fitted", False) in pop.calls


@pytest.mark.parametrize("toggle", [False, True])
def test_a_show_while_the_strip_is_up_always_means_the_browser(pop, toggle):
    pop.strip_from_browser()
    pop.calls.clear()
    pop.request_show("blocking", 0, toggle, None)
    assert pop.mode == "browser" and pop.up and pop.strip_on
    assert "force_foreground" in names(pop)
    assert any('"tag": "blocking"' in js for js in pop.window.js)


def test_a_show_after_hide_strip_shows_the_browser(pop):
    pop.strip_from_browser()
    pop.hide_strip()
    pop.request_show(None, 0, False, None)
    assert pop.mode == "browser" and pop.up


def test_ready_with_the_strip_on_shows_the_strip_without_taking_the_foreground(pop, monkeypatch):
    monkeypatch.setattr(pop, "_wait_booted", lambda timeout_s=5.0: True)
    pop.strip_on = True
    pop._first_show(None)
    assert pop.mode == "strip" and pop.up
    assert ("ShowWindow", W.SW_SHOWNOACTIVATE) in pop.calls
    assert not {"force_foreground", "send_keys", "show", "SetForegroundWindow"} & set(names(pop))


def test_ready_with_a_show_asked_for_shows_the_browser_even_with_the_strip_on(pop):
    pop.strip_on = True
    pop._first_show(("blocking", 0, None))
    assert pop.mode == "browser" and "force_foreground" in names(pop)


def test_ready_with_the_strip_off_shows_nothing(pop):
    pop._first_show(None)
    assert not pop.up and pop.calls == []


def test_the_strip_stays_on_top_with_keep_on_top_off(pop):
    pop.on_top = False
    pop.show_strip("test")
    assert pop._z_order() == popout.winframe.HWND_TOPMOST
    pop.open_browser()
    assert pop._z_order() == popout.winframe.HWND_NOTOPMOST


# --- the pick ---------------------------------------------------------------------------------------------
@pytest.fixture
def app_window(monkeypatch):
    sent = []
    monkeypatch.setattr(popout.W, "find_message_window", lambda cls: 99)
    monkeypatch.setattr(popout.W, "send_copydata", lambda hwnd, dw, payload, timeout_ms=500: sent.append(payload) or 1)
    return sent


def test_a_pick_from_the_strip_hands_nothing_back(pop, app_window, monkeypatch):
    back = []
    monkeypatch.setattr(pop, "_back_to_target", lambda: back.append(1) or True)
    pop.show_strip("test")
    pop.calls.clear()
    assert pop.pick("Anchors", "brush") == {"ok": True}
    assert back == [] and "nudge" not in names(pop) and "SetForegroundWindow" not in names(pop)
    assert json.loads(app_window[0])["name"] == "Anchors"


def test_a_pick_from_the_browser_still_hands_the_focus_back(pop, app_window, monkeypatch):
    back = []
    monkeypatch.setattr(pop, "_back_to_target", lambda: back.append(1) or True)
    pop.up = True
    assert pop.pick("Anchors", "brush") == {"ok": True}
    assert back == [1]


# --- fitting the window to the page -----------------------------------------------------------------------
def test_the_size_call_is_answered_at_once_and_the_window_resized_on_the_work_thread(pop):
    pop.show_strip("test")
    pop.calls.clear()
    assert popout.PopoutApi(pop).popout_strip_size(600, 64) is True
    assert pop.calls == []                                  # nothing done inside the js_api call
    fn, args = pop._work.get_nowait()
    fn(*args)
    assert pop.calls[-1][2:6] == (8, 320, 600, 64)          # the corner stays where the strip belongs


def test_a_larger_size_by_the_screen_edge_moves_it_back_and_it_returns_after(pop):
    popout._update_strip(window={"x": 1850, "y": 100})
    pop.show_strip("test")
    pop.fit_strip({"w": 180, "h": 330})                     # the menu open
    assert pop.rect[:2] == (1740, 100)
    pop.fit_strip({"w": 64, "h": 400})                      # closed again
    assert pop.rect[:2] == (1850, 100)


def test_a_move_saves_the_strips_new_place(pop, tmp_path):
    pop.show_strip("test")
    pop.rect = (300, 200, 364, 600)                         # the user dragged it by the grip
    pop.on_moved()
    fn, args = pop._work.get_nowait()
    fn(*args)
    assert _state(tmp_path)["strip"]["window"] == {"x": 300, "y": 200}
    pop.fit_strip({"w": 64, "h": 500})
    assert pop.rect[:2] == (300, 200)


def test_a_move_of_the_browser_saves_nothing_of_the_strip(pop):
    pop.on_moved()
    assert pop._work.empty()


def test_the_size_is_ignored_once_the_window_is_the_browser(pop):
    pop.fit_strip({"w": 64, "h": 400})
    assert pop.calls == []


# --- the name pill ------------------------------------------------------------------------------------------
def test_hover_turns_the_page_rectangle_into_screen_pixels_and_drops_an_older_call(pop, monkeypatch):
    posted = []
    monkeypatch.setattr(pop, "_post_pill", lambda: posted.append(pop._pill))
    pop.show_strip("test")
    monkeypatch.setattr(pop, "_scale", lambda: 1.5)
    pop.hover(2, "Anchors", [0, 10, 64, 58], "right")
    assert posted[-1] == ("name", "Anchors", (8, 335, 104, 407), "right")
    pop.hover(1, None, None, "right")                       # older than the one shown: arrived late
    assert len(posted) == 1
    pop.hover(3, None, None, "right")
    assert posted[-1] == ("off",)


def test_a_note_is_queued_for_the_control_window(pop, monkeypatch):
    monkeypatch.setattr(pop, "_post_pill", lambda: None)
    popout.PopoutApi(pop).popout_strip_note("ZOrbit is not running.")
    assert pop._pill == ("note", "ZOrbit is not running.")


def test_beside_puts_the_pill_to_the_right_or_below_and_flips_at_the_edge():
    assert toast.beside((8, 100, 72, 148), (120, 30), "right", WORK, 8) == (80, 109)
    assert toast.beside((1850, 100, 1914, 148), (120, 30), "right", WORK, 8) == (1722, 109)
    assert toast.beside((100, 8, 148, 72), (120, 30), "below", WORK, 8) == (64, 80)
    assert toast.beside((100, 1000, 148, 1040), (120, 30), "below", WORK, 8) == (64, 962)


def test_set_fitted_does_nothing_to_a_window_without_the_frame():
    assert popout.winframe.set_fitted(0xDEAD, True) is False


def test_a_fitted_window_has_no_resize_border():
    # install_frame passes border 0 to hit_test while the window is fitted: all of it is the page
    assert popout.winframe.hit_test(1, 1, (0, 0, 64, 400), False, 0) == popout.winframe.HTCLIENT
