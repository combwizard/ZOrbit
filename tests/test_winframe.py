"""The window frame of Studio and the browser: the client rectangle WM_NCCALCSIZE gives, the resize zones
WM_NCHITTEST answers, the saved placement read back from Windows, and WinForms kept from moving a restored window
back. Mostly plain arithmetic on rectangles; the windows that are created stay hidden."""
import ctypes

import pytest

import winframe as wf

# A monitor 1920 x 1080 and its work area with the taskbar (48 px) on each side in turn.
MONITOR = (0, 0, 1920, 1080)
WORK = {
    "bottom": (0, 0, 1920, 1032),
    "top": (0, 48, 1920, 1080),
    "left": (48, 0, 1920, 1080),
    "right": (0, 0, 1872, 1080),
}
OVERHANG = 8          # what Windows adds around a maximised window with a sizing frame


def _maximised_rect(work):
    l, t, r, b = work
    return (l - OVERHANG, t - OVERHANG, r + OVERHANG, b + OVERHANG)


# --- WM_NCCALCSIZE: the client rectangle -----------------------------------------------------------------

def test_a_normal_window_is_all_client():
    assert wf.client_rect((100, 100, 900, 700), False, WORK["bottom"], 6) == (100, 100, 900, 700)


@pytest.mark.parametrize("side", sorted(WORK))
def test_maximised_client_is_the_work_area_plus_the_margin(side):
    work = WORK[side]
    got = wf.client_rect(_maximised_rect(work), True, work, 6)
    assert got == (work[0] - 6, work[1] - 6, work[2] + 6, work[3] + 6)


@pytest.mark.parametrize("side", sorted(WORK))
def test_maximised_without_a_margin_stops_at_the_taskbar(side):
    work = WORK[side]
    assert wf.client_rect(_maximised_rect(work), True, work, 0) == work


def test_the_margin_never_reaches_past_the_window():
    # a window rectangle that is smaller than the work area plus the margin keeps its own edges
    work = WORK["bottom"]
    assert wf.client_rect((0, 0, 1920, 1032), True, work, 6) == (0, 0, 1920, 1032)


def test_the_client_follows_the_monitor_the_rectangle_is_on():
    # Win+Shift+Arrow to a 2560 px monitor: Windows proposes a rectangle there and the work area is that monitor's
    work = (1920, 0, 4480, 1392)
    assert wf.client_rect(_maximised_rect(work), True, work, 0) == work


class _Params(ctypes.Structure):
    _fields_ = [("rgrc", wf.w.RECT * 3), ("lppos", ctypes.c_void_p)]


def _work_of(work):
    return lambda rect: work


def test_nccalcsize_params_get_the_client_rectangle_in_the_first_slot():
    work = WORK["left"]
    p = _Params()
    p.rgrc[0] = wf.w.RECT(*_maximised_rect(work))
    p.rgrc[1] = wf.w.RECT(1, 2, 3, 4)
    wf._nccalcsize(True, ctypes.addressof(p), True, 6, _work_of(work))
    got = p.rgrc[0]
    assert (got.left, got.top, got.right, got.bottom) == (work[0] - 6, work[1] - 6, work[2] + 6, work[3] + 6)
    assert (p.rgrc[1].left, p.rgrc[1].top) == (1, 2)         # the other two are Windows' to keep


def test_nccalcsize_without_params_works_on_the_rectangle_itself():
    work = WORK["top"]
    rc = wf.w.RECT(*_maximised_rect(work))
    wf._nccalcsize(False, ctypes.addressof(rc), True, 0, _work_of(work))
    assert (rc.left, rc.top, rc.right, rc.bottom) == work


def test_nccalcsize_leaves_a_normal_window_alone():
    p = _Params()
    p.rgrc[0] = wf.w.RECT(10, 20, 810, 620)
    wf._nccalcsize(True, ctypes.addressof(p), False, 6, _work_of(WORK["bottom"]))
    assert (p.rgrc[0].left, p.rgrc[0].top, p.rgrc[0].right, p.rgrc[0].bottom) == (10, 20, 810, 620)


# --- WM_NCHITTEST: the resize zones ------------------------------------------------------------------------

RECT = (100, 100, 900, 700)
B = 6


@pytest.mark.parametrize("point, code", [
    ((500, 100), wf.HTTOP), ((500, 105), wf.HTTOP),
    ((500, 106), wf.HTCLIENT),
    ((100, 400), wf.HTLEFT), ((105, 400), wf.HTLEFT), ((106, 400), wf.HTCLIENT),
    ((899, 400), wf.HTRIGHT), ((894, 400), wf.HTRIGHT), ((893, 400), wf.HTCLIENT),
    ((500, 699), wf.HTBOTTOM), ((500, 694), wf.HTBOTTOM), ((500, 693), wf.HTCLIENT),
])
def test_edges(point, code):
    assert wf.hit_test(*point, RECT, False, B) == code


@pytest.mark.parametrize("point, code", [
    ((100, 100), wf.HTTOPLEFT), ((102, 108), wf.HTTOPLEFT), ((108, 102), wf.HTTOPLEFT),
    ((899, 100), wf.HTTOPRIGHT), ((891, 103), wf.HTTOPRIGHT), ((897, 109), wf.HTTOPRIGHT),
    ((100, 699), wf.HTBOTTOMLEFT), ((108, 697), wf.HTBOTTOMLEFT), ((103, 690), wf.HTBOTTOMLEFT),
    ((899, 699), wf.HTBOTTOMRIGHT), ((891, 697), wf.HTBOTTOMRIGHT), ((896, 690), wf.HTBOTTOMRIGHT),
])
def test_corners(point, code):
    assert wf.hit_test(*point, RECT, False, B) == code


def test_a_corner_reaches_further_along_the_edge_than_the_edge_width():
    assert wf.hit_test(111, 102, RECT, False, B) == wf.HTTOPLEFT       # 11 px along: still the corner
    assert wf.hit_test(113, 102, RECT, False, B) == wf.HTTOP           # 13 px along: the plain top edge


def test_the_title_area_and_the_maximise_button_are_the_page_s():
    # the header is client area (the page drags it with app-region); the maximise button sits in it
    assert wf.hit_test(500, 130, RECT, False, B) == wf.HTCLIENT
    assert wf.hit_test(RECT[2] - 40, RECT[1] + 14, RECT, False, B) == wf.HTCLIENT


def test_outside_the_window_is_nowhere():
    assert wf.hit_test(99, 400, RECT, False, B) == wf.HTNOWHERE
    assert wf.hit_test(500, 700, RECT, False, B) == wf.HTNOWHERE


def test_a_maximised_window_has_no_resize_zones():
    for point in ((500, 100), (100, 400), (100, 100), (899, 699)):
        assert wf.hit_test(*point, RECT, True, B) == wf.HTCLIENT


def test_the_border_scales_with_the_screen_scale():
    assert [wf.border_px(d) for d in (96, 120, 144, 192)] == [6, 8, 9, 12]


# --- saved placement ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("show_cmd, flags, maximised", [
    (1, 0, False),            # SW_SHOWNORMAL
    (3, 0, True),             # SW_SHOWMAXIMIZED
    (2, 0, False),            # minimised from normal
    (2, 2, True),             # minimised from maximised (WPF_RESTORETOMAXIMIZED)
])
def test_placement_state(show_cmd, flags, maximised):
    assert wf.placement_state(show_cmd, flags) is maximised


def test_workspace_origin_follows_the_taskbar_on_the_primary_monitor():
    assert wf.workspace_origin(False, WORK["bottom"], MONITOR) == (0, 0)
    assert wf.workspace_origin(False, WORK["top"], MONITOR) == (0, 48)
    assert wf.workspace_origin(False, WORK["left"], MONITOR) == (48, 0)
    assert wf.workspace_origin(False, WORK["right"], MONITOR) == (0, 0)


def test_a_tool_window_is_in_screen_coordinates():
    assert wf.workspace_origin(True, WORK["top"], MONITOR) == (0, 0)


def test_workspace_rectangles_become_screen_rectangles_and_back():
    rc = (100, 100, 900, 700)
    for side in WORK:
        origin = wf.workspace_origin(False, WORK[side], MONITOR)
        screen = wf.to_screen(rc, origin)
        assert screen == (100 + origin[0], 100 + origin[1], 900 + origin[0], 700 + origin[1])
        assert wf.to_workspace(screen, origin) == rc


def _placement(monkeypatch, show_cmd, flags, rc, origin):
    monkeypatch.setattr(wf, "_read_placement", lambda hwnd: (show_cmd, flags, rc))
    monkeypatch.setattr(wf, "_workspace_origin", lambda hwnd: origin)


def test_normal_rect_is_the_restore_rectangle_in_screen_coordinates(monkeypatch):
    _placement(monkeypatch, 1, 0, (100, 100, 900, 700), (0, 48))        # taskbar along the top
    assert wf.normal_rect(1) == (100, 148, 900, 748, False)


def test_a_maximised_window_reports_the_size_it_restores_to(monkeypatch):
    _placement(monkeypatch, 3, 0, (200, 150, 1000, 750), (0, 0))
    assert wf.normal_rect(1) == (200, 150, 1000, 750, True)


def test_placement_record_is_what_the_preferences_files_keep(monkeypatch):
    _placement(monkeypatch, 3, 0, (200, 150, 1000, 750), (48, 0))
    assert wf.placement_record(1) == {"x": 248, "y": 150, "width": 800, "height": 600, "maximized": True}


def test_no_placement_means_no_record(monkeypatch):
    monkeypatch.setattr(wf, "_read_placement", lambda hwnd: None)
    assert wf.normal_rect(1) is None
    assert wf.placement_record(1) is None


def test_an_empty_rectangle_is_not_a_record(monkeypatch):
    _placement(monkeypatch, 1, 0, (0, 0, 0, 0), (0, 0))
    assert wf.placement_record(1) is None


# --- the window procedure, on a real window that is never shown ----------------------------------------------

@pytest.fixture
def plain_window():
    """A hidden top-level window (class Static) with the usual overlapped-window style, 800 x 600 at (100, 100)."""
    u = wf.user32
    u.CreateWindowExW.restype = wf.w.HWND
    u.CreateWindowExW.argtypes = [wf.w.DWORD, wf.w.LPCWSTR, wf.w.LPCWSTR, wf.w.DWORD, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wf.w.HWND, wf.w.HMENU, wf.w.HINSTANCE, wf.w.LPVOID]
    u.SendMessageW.argtypes = [wf.w.HWND, wf.w.UINT, wf.w.WPARAM, wf.w.LPARAM]
    u.SendMessageW.restype = ctypes.c_ssize_t
    u.DestroyWindow.argtypes = [wf.w.HWND]
    hwnd = u.CreateWindowExW(0, "Static", "zorbit-winframe-test", 0x00CF0000, 100, 100, 800, 600, None, None, None, None)
    assert hwnd and not u.IsWindowVisible(hwnd)
    yield hwnd
    u.DestroyWindow(hwnd)
    wf._subclass.pop(hwnd, None)


def test_the_client_area_is_the_whole_window_and_the_edges_resize(plain_window):
    u, h = wf.user32, plain_window
    calls = []
    wf.install_frame(h, on_query_end=lambda: calls.append("query"))
    u.SetWindowPos(h, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)         # FRAMECHANGED: asks NCCALCSIZE
    client = wf.w.RECT()
    u.GetClientRect(h, ctypes.byref(client))
    assert (client.right, client.bottom) == (800, 600)

    def ask(x, y):
        return u.SendMessageW(h, 0x0084, 0, ((y & 0xFFFF) << 16) | (x & 0xFFFF))
    assert ask(500, 100) != wf.HTTOP                                          # no strip before the form has its Padding
    wf._subclass[h][2]["border"] = 6                                          # as _set_layout does
    assert ask(500, 100) == wf.HTTOP
    assert ask(100, 300) == wf.HTLEFT
    assert ask(899, 699) == wf.HTBOTTOMRIGHT
    assert ask(100, 100) == wf.HTTOPLEFT
    assert ask(500, 300) not in (wf.HTTOP, wf.HTLEFT, wf.HTBOTTOMRIGHT, wf.HTTOPLEFT)
    assert u.SendMessageW(h, 0x0011, 0, 0) == 1 and calls == ["query"]       # WM_QUERYENDSESSION: always yes


def test_hold_at_keeps_the_window_where_windows_put_it():
    pos = wf._WINDOWPOS(0, 0, 78, 78, 1320, 860, 0x0001 | 0x0002 | 0x0004)      # NOSIZE NOMOVE NOZORDER
    wf._hold_at(pos, (3500, 100, 4800, 900))
    assert (pos.x, pos.y, pos.cx, pos.cy) == (3500, 100, 1300, 800)
    assert pos.flags == 0x0004                                                  # it may move and size; the rest stays


# --- WinForms moving a restored window back ----------------------------------------------------------------

def _pos(x, y, cx=1320, cy=860, flags=0x0004):
    return wf._WINDOWPOS(0, 0, x, y, cx, cy, flags)


@pytest.fixture
def forms(plain_window, monkeypatch):
    """The frame's procedure over a stand-in for WinForms, which moves the window to (78, 78) twice when it hears that
    the window changed, the second time after a nested change message. No window is shown or really moved."""
    h = plain_window
    wf.install_frame(h)
    state = {"zoomed": False, "iconic": False, "seen": []}
    cb = wf._subclass[h][0]
    monkeypatch.setattr(wf.user32, "IsZoomed", lambda _: state["zoomed"])
    monkeypatch.setattr(wf.user32, "IsIconic", lambda _: state["iconic"])

    def original(_proc, hwnd, msg, wp, lp):
        if msg == 0x0047 and not state.get("nested"):
            state["nested"] = True
            for _ in range(2):
                stale = _pos(78, 78)
                cb(hwnd, 0x0046, 0, ctypes.addressof(stale))
                state["seen"].append((stale.x, stale.y, stale.cx, stale.cy))
                changed = _pos(stale.x, stale.y)
                cb(hwnd, 0x0047, 0, ctypes.addressof(changed))
            state["nested"] = False
        return 0
    monkeypatch.setattr(wf.user32, "CallWindowProcW", original)

    def changed():
        pos = _pos(0, 0)
        cb(h, 0x0047, 0, ctypes.addressof(pos))
    state["changed"], state["cb"], state["hwnd"] = changed, cb, h
    return state


HELD = (100, 100, 800, 600)      # plain_window's rectangle as x, y, width, height: where Windows put it
STALE = (78, 78, 1320, 860)


@pytest.mark.parametrize("was", ["zoomed", "iconic"])
def test_a_restored_window_stays_where_windows_put_it(forms, was):
    forms[was] = True
    forms["changed"]()
    assert forms["seen"][-2:] == [STALE, STALE]          # still maximised or minimised: not its business
    forms["seen"].clear()
    forms[was] = False
    forms["changed"]()
    assert forms["seen"] == [HELD, HELD]                 # both of WinForms' moves, the nested change between them


def test_a_window_that_was_not_maximised_is_not_held(forms):
    forms["changed"]()
    assert forms["seen"] == [STALE, STALE]


def test_the_hold_ends_with_the_message(forms):
    forms["zoomed"] = True
    forms["changed"]()
    forms["zoomed"] = False
    forms["changed"]()
    later = _pos(78, 78)
    forms["cb"](forms["hwnd"], 0x0046, 0, ctypes.addressof(later))
    assert (later.x, later.y) == (78, 78)                # the user's own move, afterwards


# --- bring_on_screen -----------------------------------------------------------------------------------------

def test_a_hidden_maximised_window_is_left_for_after_it_is_shown(plain_window, monkeypatch):
    calls = []
    monkeypatch.setattr(wf.user32, "IsZoomed", lambda _: True)
    monkeypatch.setattr(wf, "on_a_screen", lambda *a: False)
    monkeypatch.setattr(wf.user32, "SetWindowPlacement", lambda *a: calls.append(a) or True)
    assert wf.bring_on_screen(plain_window) is False     # SetWindowPlacement would have shown it
    assert not calls
    assert not wf.user32.IsWindowVisible(plain_window)


def test_on_activate_is_called_when_the_window_is_activated_not_deactivated(plain_window):
    u, h = wf.user32, plain_window
    calls = []
    wf.install_frame(h, on_activate=lambda: calls.append(1))
    u.SendMessageW(h, 0x0006, 0, 0)                                      # WA_INACTIVE
    assert calls == []
    u.SendMessageW(h, 0x0006, 1, 0)                                      # WA_ACTIVE (the Static class answers it with one more)
    n = len(calls)
    assert n >= 1
    u.SendMessageW(h, 0x0006, 0x10000, 0)                                # minimised, inactive: the high word is not the state
    assert len(calls) == n
    u.SendMessageW(h, 0x0006, 2, 0)                                      # WA_CLICKACTIVE
    assert len(calls) > n
