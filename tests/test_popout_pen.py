"""The browser tells the page whether a pen or a mouse moved the cursor last, so the press that brings it to the front
scrolls the grid when a pen made it (while ZBrush has the foreground, a Wacom pen reaches the page as a mouse). No
window is opened: raw input reports are handed in, and what the page is told is recorded."""
import ctypes

import pytest

import popout
import win32 as W

PEN_DEV, MOUSE_DEV = 0x4D2, 0x929
SIG = W.PEN_SIGNATURE | 0x06                              # what Windows' mouse from a Wacom pen carried on the test PC


@pytest.mark.parametrize("flags, dx, dy, extra, device, known, want", [
    (0, 3, -1, 0, MOUSE_DEV, set(), "mouse"),             # a mouse moves relatively
    (0, 0, 0, 0, MOUSE_DEV, set(), None),                 # a button alone says nothing
    (W.MOUSE_MOVE_ABSOLUTE | 2, 31000, 9000, 0x1C4F, PEN_DEV, set(), "pen"),   # Wacom's own absolute moves (ZBrush in front)
    (0, 5, 5, SIG, 0, set(), "pen"),                      # Windows' mouse made from the pen (the browser in front)
    (0, 0, 0, SIG, 0, set(), "pen"),
    (0, 0, 0, 0x2E5, PEN_DEV, {PEN_DEV}, "pen"),          # the tablet's own button, from a device seen moving absolutely
    (W.MOUSE_MOVE_ABSOLUTE, 100, 100, 0, 0, set(), None), # an absolute move no device made: remote desktop, automation
    (0, 0, 0, W.OWN_INPUT_MARKER, 0, set(), None),        # ZOrbit's own nudge
    (0, 4, 0, 0, 0, set(), "mouse"),                      # a program's relative move moves like a mouse
])
def test_pointer_source(flags, dx, dy, extra, device, known, want):
    assert popout.pointer_source(flags, dx, dy, extra, device, known) == want


def test_the_raw_mouse_report_is_read_at_the_right_offsets():
    """The button fields are a union with a ULONG: without the padding after usFlags every field after it is off by two."""
    assert ctypes.sizeof(W.RAWMOUSE) == 24
    assert W.RAWMOUSE.lLastX.offset == 12 and W.RAWMOUSE.ulExtraInformation.offset == 20
    assert W.RAWINPUTMOUSE.mouse.offset == ctypes.sizeof(W.RAWINPUTHEADER)


class _Window:
    def __init__(self):
        self.js = []

    def evaluate_js(self, js):
        self.js.append(js)


@pytest.fixture
def pop(monkeypatch):
    p = popout.Popout({"tag": None, "kind": None, "managed": True, "show": False, "zbrush": 0})
    p.window, p.ctl, p.ready, p.up = _Window(), 0x99, True, True
    monkeypatch.setattr(p, "visible", lambda: p.up)
    p.reports, p.posted = [], []
    monkeypatch.setattr(popout.W, "read_raw_mouse", lambda lparam: p.reports.pop(0))
    monkeypatch.setattr(popout.W, "PostMessageW", lambda hwnd, msg, wp, lp: p.posted.append((msg, wp)) or True)
    return p


def feed(p, *reports):
    for r in reports:
        p.reports.append(r)
        p._on_raw_mouse(0)


def run_work(p):
    while not p._work.empty():
        fn, args = p._work.get_nowait()
        fn(*args)


def told(p):
    return [js.split("__popoutPen(")[1].rstrip(")") for js in p.window.js]


MOUSE = (0, 2, 1, 0, MOUSE_DEV)
PEN = (W.MOUSE_MOVE_ABSOLUTE, 30000, 20000, 0x1C50, PEN_DEV)


def test_the_page_is_told_once_per_change_of_device(pop):
    feed(pop, MOUSE, MOUSE, PEN, PEN, PEN)
    run_work(pop)
    assert told(pop) == ["true"]                          # one call, queued by the mouse, which tells the newest: the pen
    feed(pop, (0, 0, 0, 0x2E5, PEN_DEV), MOUSE, MOUSE)    # the tablet's button is still the pen
    run_work(pop)
    assert told(pop) == ["true", "false"]


def test_a_quick_change_back_queues_one_call_that_tells_the_newest(pop):
    feed(pop, PEN, MOUSE, PEN, MOUSE)
    assert pop._work.qsize() == 1
    run_work(pop)
    assert told(pop) == ["false"]                         # only the newest: the mouse
    feed(pop, MOUSE)
    run_work(pop)
    assert told(pop) == ["false"]                         # the page knows already
    feed(pop, PEN)
    run_work(pop)
    assert told(pop) == ["false", "true"]


def test_a_new_page_is_told_again(pop):
    feed(pop, PEN)
    run_work(pop)
    pop.on_loaded()
    feed(pop, PEN)                                        # the same device: a reloaded page still hears it
    run_work(pop)
    assert told(pop) == ["true", "true"]


def test_raw_input_is_watched_only_while_the_browser_is_up(pop):
    pop._pen_check()
    pop._pen_check()
    assert pop.posted == [(popout.WM_APP_PEN, 1)]
    pop.up = False
    pop._pen_check()
    assert pop.posted[-1] == (popout.WM_APP_PEN, 0)
    pop.up, pop.mode = True, "strip"                      # the strip leaves ZBrush the pen: nothing to scroll there
    pop._pen_check()
    assert pop.posted == [(popout.WM_APP_PEN, 1), (popout.WM_APP_PEN, 0)]


def test_turning_the_watch_on_forgets_the_last_device(pop, monkeypatch):
    monkeypatch.setattr(popout.W, "watch_raw_mouse", lambda hwnd, on: True)
    feed(pop, PEN)
    pop._pen_watch(True)
    assert pop._pen_last is None
