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
        self.answer = True                                # what __popoutPen gives back; a page still loading has none

    def evaluate_js(self, js):
        self.js.append(js)
        return self.answer


@pytest.fixture
def pop(monkeypatch):
    p = popout.Popout({"tag": None, "kind": None, "managed": True, "show": False, "zbrush": 0})
    p.window, p.ctl, p.ready, p.up = _Window(), 0x99, True, True
    p._loaded.set()
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


def told(win):
    return [js.split("__popoutPen(")[1].split(")")[0] for js in win.window.js]


def add_extra(p, eid="e1"):
    """Another browser window, made, loaded and up."""
    ext = popout.ExtraWindow(p, eid, {"id": eid})
    ext.window, ext.ready, ext.up = _Window(), True, True
    ext._loaded.set()
    ext.visible = lambda: ext.up
    p.extras.append(ext)
    return ext


def deliver(p, monkeypatch):
    """What the control window's thread does with the WM_APP_PEN messages posted to it."""
    monkeypatch.setattr(popout.W, "watch_raw_mouse", lambda hwnd, on: True)
    for msg, wp in list(p.posted):
        if msg == popout.WM_APP_PEN:
            p._ctl_proc(p.ctl, msg, wp, 0)
    p.posted.clear()


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


def test_a_page_that_is_not_ready_is_told_on_the_next_report(pop):
    pop.window.answer = None                              # no __popoutPen yet
    feed(pop, PEN)
    run_work(pop)
    pop.window.answer = True
    feed(pop, PEN)                                        # the same device: told again, since the page never had it
    run_work(pop)
    assert told(pop) == ["true", "true"]
    feed(pop, PEN)
    assert pop._work.empty()


def test_raw_input_is_watched_only_while_the_browser_is_up(pop):
    pop._pen_check()
    pop._pen_check()
    assert pop.posted == [(popout.WM_APP_PEN, 1)]
    pop.up = False
    pop._pen_check()
    assert pop.posted[-1] == (popout.WM_APP_PEN, 0)
    pop.up = True
    pop._pen_check()
    pop.mode = "strip"                                    # the strip leaves ZBrush the pen: nothing to scroll there
    pop._pen_check()
    assert pop.posted == [(popout.WM_APP_PEN, 1), (popout.WM_APP_PEN, 0), (popout.WM_APP_PEN, 1), (popout.WM_APP_PEN, 0)]


def test_turning_the_watch_on_starts_the_page_again_from_a_mouse(pop, monkeypatch):
    monkeypatch.setattr(popout.W, "watch_raw_mouse", lambda hwnd, on: True)
    feed(pop, PEN)
    run_work(pop)                                         # the page has the pen; then the window goes, and comes back
    pop._pen_watch(True)
    run_work(pop)
    assert told(pop) == ["true", "false"]                 # the mouse may have moved while nobody watched
    feed(pop, PEN)
    run_work(pop)
    assert told(pop) == ["true", "false", "true"]


def test_a_report_that_cannot_be_read_still_frees_the_input(pop, monkeypatch):
    freed = []
    monkeypatch.setattr(popout.W, "DefWindowProcW", lambda *a: freed.append(a[1]) or 0)
    monkeypatch.setattr(pop, "_on_raw_mouse", lambda lparam: 1 / 0)
    pop._ctl_proc(pop.ctl, W.WM_INPUT, 0, 0)
    pop._ctl_proc(pop.ctl, W.WM_INPUT, 0, 0)
    assert freed == [W.WM_INPUT, W.WM_INPUT] and pop._raw_failed


# --- several browser windows: one watch for the process, each page told on its own ---------------------------
def test_an_extra_window_shown_while_the_pen_is_in_use_is_told_at_once(pop, monkeypatch):
    pop._pen_check()
    deliver(pop, monkeypatch)                             # the watch is on: the first page starts from a mouse
    run_work(pop)
    feed(pop, PEN)
    run_work(pop)
    assert told(pop) == ["false", "true"]
    ext = add_extra(pop)
    pop._pen_check(tell=True)                             # what its show() asks: the watch is on already
    assert pop.posted == [(popout.WM_APP_PEN, popout.PEN_TELL)]
    deliver(pop, monkeypatch)
    run_work(pop)
    assert told(ext) == ["true"] and told(pop) == ["false", "true"]    # the first page knew already
    pop._pen_check(tell=True)                             # every page knows: nothing to post
    assert pop.posted == []


def test_an_extra_window_is_told_by_the_next_report_too(pop):
    feed(pop, PEN)
    run_work(pop)
    ext = add_extra(pop)
    feed(pop, PEN)                                        # the same device: the new page has not heard it
    run_work(pop)
    assert told(ext) == ["true"] and told(pop) == ["true"]
    feed(pop, MOUSE)
    run_work(pop)
    assert told(ext) == ["true", "false"] and told(pop) == ["true", "false"]


def test_a_reloaded_page_is_told_again_and_only_it(pop):
    ext = add_extra(pop)
    feed(pop, PEN)
    run_work(pop)
    ext.on_loaded()
    feed(pop, PEN)
    run_work(pop)
    assert told(ext) == ["true", "true"] and told(pop) == ["true"]


def test_one_page_that_does_not_answer_leaves_the_others_told(pop):
    ext = add_extra(pop)
    ext.window.answer = None
    feed(pop, PEN)
    run_work(pop)
    feed(pop, PEN)
    run_work(pop)
    assert told(pop) == ["true"] and told(ext) == ["true", "true"]
    ext.window.answer = True
    feed(pop, PEN)
    run_work(pop)
    assert told(ext) == ["true", "true", "true"]
    feed(pop, PEN)
    assert pop._work.empty()


def test_turning_the_watch_on_starts_every_page_again_from_a_mouse(pop, monkeypatch):
    ext = add_extra(pop)
    pop._pen_check()
    deliver(pop, monkeypatch)
    run_work(pop)
    feed(pop, PEN)
    run_work(pop)
    pop.up = ext.up = False
    pop._pen_check()
    pop.up = ext.up = True
    pop._pen_check()
    assert pop.posted == [(popout.WM_APP_PEN, 0), (popout.WM_APP_PEN, 1)]
    deliver(pop, monkeypatch)
    run_work(pop)
    assert told(pop) == told(ext) == ["false", "true", "false"]


def test_the_watch_stays_on_while_any_browser_window_is_up(pop):
    ext = add_extra(pop)
    pop._pen_check()
    pop.up = False                                        # the first window hidden: the other one is still up
    pop._pen_check()
    assert pop.posted == [(popout.WM_APP_PEN, 1)]
    pop.up, pop.mode = True, "strip"                      # the first window is the strip: the other one still counts
    pop._pen_check()
    assert pop.posted == [(popout.WM_APP_PEN, 1)]
    ext.up = False                                        # the last browser window hidden
    pop._pen_check()
    assert pop.posted == [(popout.WM_APP_PEN, 1), (popout.WM_APP_PEN, 0)]
    ext.up = True
    pop._pen_check()
    ext.closing = True                                    # closed for good (it may still be visible a moment)
    pop._pen_check()
    assert pop.posted[-2:] == [(popout.WM_APP_PEN, 1), (popout.WM_APP_PEN, 0)]


def test_the_strip_page_is_not_told(pop):
    ext = add_extra(pop)
    pop.mode = "strip"                                    # the strip leaves ZBrush the pen: nothing to scroll there
    feed(pop, PEN)
    run_work(pop)
    assert told(pop) == [] and told(ext) == ["true"]


def test_a_tell_that_arrives_after_the_watch_went_off_does_nothing(pop, monkeypatch):
    pop._ctl_proc(pop.ctl, popout.WM_APP_PEN, popout.PEN_TELL, 0)
    assert pop._work.empty()
