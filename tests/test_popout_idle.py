"""A hidden browser that the app started quits after a while unused (browser.quit_after_minutes in radial.json) and
starts again on the next press. This is the browser's half: the timer, the setting it follows, and the answer to a
SHOW that arrives while it is going. No window is opened and nothing sleeps; the clock is a number the test moves."""
import ctypes
import json

import pytest

import popout
import profiles
import radiald
import win32 as W

MIN = 60


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def after(self, seconds):
        self.t += seconds


class _Window:
    def __init__(self):
        self.js, self.hidden, self.destroyed = [], 0, 0

    def evaluate_js(self, code):
        self.js.append(code)

    def hide(self):
        self.hidden += 1

    def destroy(self):
        self.destroyed += 1


class Up:
    """Whether the window is visible; the Popout's visible() reads it."""
    def __init__(self, value=False):
        self.value = value

    def __call__(self):
        return self.value


@pytest.fixture
def setting(tmp_path, monkeypatch):
    """setting(value) writes browser.quit_after_minutes (missing for None) into the radial.json the browser reads;
    setting(text=...) writes the file's text as it is."""
    path = tmp_path / "radial.json"
    monkeypatch.setenv("ZORBIT_CONFIG_FILE", str(path))

    def write(value=None, text=None, **browser):
        if text is None:
            if value is not None:
                browser["quit_after_minutes"] = value
            text = json.dumps({"menus": {}, "browser": {"hotkey": "Alt+B", **browser}})
        path.write_text(text, encoding="utf-8")
    return write


@pytest.fixture
def quits(monkeypatch):
    """What pop.quit was asked: [(why, idle)]. The real quit ends the process; see the tests of quit below."""
    calls = []
    monkeypatch.setattr(popout.Popout, "quit", lambda self, why="", idle=False: calls.append((why, idle)))
    return calls


def _pop(monkeypatch, tmp_path, managed=True, up=False, **opts):
    monkeypatch.setattr(popout, "STATE_FILE", str(tmp_path / "popout.json"))
    pop = popout.Popout({"tag": None, "kind": None, "managed": managed, **opts})
    pop.window = _Window()
    pop.hwnd = 0x1234
    pop.ready = True
    pop.clock = Clock()
    pop._now = pop.clock
    pop._hidden_at = None if opts.get("show") else pop.clock.t        # as __init__ did, on the test's clock
    pop.up = Up(up)
    monkeypatch.setattr(pop, "visible", pop.up)
    return pop


@pytest.fixture
def pop(monkeypatch, tmp_path):
    return _pop(monkeypatch, tmp_path)


# --- the timer ---------------------------------------------------------------------------------


def test_off_by_default_a_hidden_browser_stays_however_long(pop, setting, quits):
    setting()                                              # no quit_after_minutes at all
    pop.idle_tick()
    pop.clock.after(30 * 24 * 3600)
    pop.idle_tick()
    assert quits == []


def test_zero_is_off(pop, setting, quits):
    setting(0)
    pop.idle_tick()
    pop.clock.after(7 * 24 * 3600)
    pop.idle_tick()
    assert quits == []


def test_a_missing_or_unreadable_radial_json_is_off(pop, tmp_path, monkeypatch, quits):
    monkeypatch.setenv("ZORBIT_CONFIG_FILE", str(tmp_path / "nothing.json"))
    pop.idle_tick()
    pop.clock.after(7 * 24 * 3600)
    pop.idle_tick()
    assert quits == []


def test_it_quits_once_hidden_for_the_time_and_not_before(pop, setting, quits):
    setting(30)
    pop.idle_tick()                                        # the countdown starts from the hidden start (the Popout was built)
    pop.clock.after(30 * MIN - 1)
    pop.idle_tick()
    assert quits == []
    pop.clock.after(1)
    pop.idle_tick()
    assert len(quits) == 1 and quits[0][1] is True
    assert "30 minutes" in quits[0][0]


def test_the_countdown_runs_from_the_hidden_start_not_from_the_first_look(pop, setting, quits):
    setting(10)
    pop.clock.after(10 * MIN)                              # nobody looked until now: the browser has been hidden all along
    pop.idle_tick()
    assert len(quits) == 1


def test_a_window_that_is_up_never_quits_and_hiding_it_starts_the_time_again(pop, setting, quits):
    setting(10)
    pop.up.value = True
    pop.clock.after(10 * MIN * 5)
    pop.idle_tick()
    assert quits == []                                     # up for ages: a visible window never counts
    pop.up.value = False                                   # hidden now (the hide itself calls _note_hidden)
    pop._note_hidden()
    pop.clock.after(10 * MIN - 1)
    pop.idle_tick()
    assert quits == []
    pop.clock.after(1)
    pop.idle_tick()
    assert len(quits) == 1


def test_a_window_found_up_by_the_tick_cancels_the_countdown(pop, setting, quits):
    setting(10)
    pop.idle_tick()
    pop.clock.after(9 * MIN)
    pop.up.value = True
    pop.idle_tick()                                        # shown by something that did not say so
    pop.up.value = False
    pop.clock.after(5 * MIN)
    pop.idle_tick()                                        # 14 minutes since the start, but only 5 since it was last up
    assert quits == []


def test_hide_and_show_move_the_countdown(monkeypatch, tmp_path, setting, quits):
    pop = _pop(monkeypatch, tmp_path, up=True)
    setting(10)
    monkeypatch.setattr(pop, "_save_placement", lambda: None)
    monkeypatch.setattr(popout, "_is_target", lambda hwnd: False)
    monkeypatch.setattr(popout.user32, "IsZoomed", lambda hwnd: 0, raising=False)
    monkeypatch.setattr(W, "nudge_mouse", lambda: None)
    pop.clock.after(100 * MIN)
    assert pop.hide() is True                              # the X button: starts the time over, from now
    assert pop._hidden_at == pop.clock.t
    pop.up.value = False
    pop.clock.after(10 * MIN - 1)
    pop.idle_tick()
    assert quits == []
    # show() puts the window up and clears the countdown
    for name in ("_remember_target", "_sync_theme", "_on_screen", "_focus_page"):
        monkeypatch.setattr(pop, name, lambda *a, **k: None)
    monkeypatch.setattr(pop, "_place", lambda zb: (0, 0, 100, 100, False))
    monkeypatch.setattr(popout.winframe, "user32", type("U", (), {"SetWindowPos": staticmethod(lambda *a: 1)}))
    monkeypatch.setattr(popout.winframe, "force_foreground", lambda hwnd: True)
    monkeypatch.setattr(popout.W, "send_keys", lambda keys: None)
    monkeypatch.setattr(popout.user32, "IsIconic", lambda hwnd: 0, raising=False)
    pop.window.show = lambda: setattr(pop.up, "value", True)
    pop.show("tag")
    assert pop._hidden_at is None and pop.up.value
    pop.clock.after(5 * 24 * 3600)
    pop.idle_tick()
    assert quits == []


def test_hiding_and_showing_again_and_again_never_quits_while_up(pop, setting, quits):
    setting(10)
    for _ in range(50):
        pop._note_shown()
        pop.up.value = True
        pop.clock.after(9 * MIN)
        pop.idle_tick()
        pop._note_hidden()
        pop.up.value = False
        pop.clock.after(9 * MIN)
        pop.idle_tick()
    assert quits == []


def test_a_browser_nobody_started_never_quits(monkeypatch, tmp_path, setting, quits):
    pop = _pop(monkeypatch, tmp_path, managed=False)       # Studio, the Start menu, the command line
    setting(1)
    pop.idle_tick()
    pop.clock.after(7 * 24 * 3600)
    pop.idle_tick()
    assert quits == []


def test_a_browser_that_lost_its_app_stops_counting(pop, setting, quits):
    setting(10)
    pop.idle_tick()
    pop.up.value = True
    pop.app_gone("the app is gone")                        # a window that is up stays, no longer managed
    assert pop.managed is False and quits == []
    pop.up.value = False
    pop.clock.after(7 * 24 * 3600)
    pop.idle_tick()
    assert quits == []


def test_nothing_happens_before_the_page_is_ready_or_once_it_is_ending(pop, setting, quits):
    setting(1)
    pop.idle_tick()
    pop.clock.after(MIN)
    pop.ready = False
    pop.idle_tick()
    pop.ready, pop.quitting = True, True
    pop.idle_tick()
    pop.quitting, pop.session_ending = False, True
    pop.idle_tick()
    assert quits == []
    pop.session_ending = False
    pop.idle_tick()
    assert len(quits) == 1


def test_the_watch_looks_at_the_clock_every_poll_for_a_managed_browser(pop, setting, quits, monkeypatch):
    setting(1)
    seen = []

    def sleep(s):
        seen.append(s)
        pop.clock.after(MIN)
        if len(seen) == 2:
            pop.quitting = True
    monkeypatch.setattr(popout.time, "sleep", sleep)
    monkeypatch.setattr(popout.W, "find_message_window", lambda cls: 99)       # the app is up
    pop._watch_app()
    assert seen == [popout.POLL_S] * 2 and len(quits) >= 1


# --- the setting, followed while it waits -------------------------------------------------------


def test_a_changed_setting_takes_effect_at_the_next_tick(pop, setting, quits):
    setting(60)
    pop.idle_tick()
    pop.clock.after(20 * MIN)
    pop.idle_tick()
    assert quits == []
    setting(15)                                            # shortened in Studio or the file: no restart
    pop.idle_tick()
    assert len(quits) == 1


def test_a_setting_turned_off_while_it_waits_cancels_the_quit(pop, setting, quits):
    setting(10)
    pop.idle_tick()
    pop.clock.after(9 * MIN)
    setting(0)
    pop.idle_tick()
    pop.clock.after(30 * MIN)
    pop.idle_tick()
    assert quits == []


def test_a_setting_turned_on_late_counts_from_the_hide(pop, setting, quits):
    setting(0)
    pop.idle_tick()
    pop.clock.after(100 * MIN)
    setting(30)
    pop.idle_tick()
    assert len(quits) == 1                                 # hidden 100 minutes already: that is unused time


def test_a_radial_json_caught_half_written_keeps_the_last_good_setting(pop, setting, quits):
    setting(30)
    pop.idle_tick()
    setting(text='{"menus": {}, "browser": {"quit_af')
    pop.clock.after(29 * MIN)
    pop.idle_tick()
    assert quits == [] and pop._idle_minutes == 30
    pop.clock.after(2 * MIN)
    pop.idle_tick()
    assert len(quits) == 1


@pytest.mark.parametrize("bad", [-5, 1441, 2.5, True, "30", None, []])
def test_a_bad_value_is_off_as_the_app_reads_it(pop, setting, quits, bad):
    setting(text=json.dumps({"menus": {}, "browser": {"quit_after_minutes": bad}}))
    pop.idle_tick()
    pop.clock.after(7 * 24 * 3600)
    pop.idle_tick()
    assert quits == []


def test_it_reads_the_active_profile_when_no_file_is_pinned(profile_env, monkeypatch, tmp_path, quits):
    monkeypatch.delenv("ZORBIT_CONFIG_FILE", raising=False)
    path = profiles.ensure()
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    raw.setdefault("browser", {})["quit_after_minutes"] = 5
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    pop = _pop(monkeypatch, tmp_path)
    pop.idle_tick()
    pop.clock.after(5 * MIN)
    pop.idle_tick()
    assert len(quits) == 1


def test_the_setting_is_not_read_while_the_window_is_up(pop, setting, monkeypatch):
    setting(10)
    reads = []
    monkeypatch.setattr(pop, "_read_idle_minutes", lambda: reads.append(1) or 10)
    pop.up.value = True
    pop.idle_tick()
    assert reads == []


# --- a press and the quit meet ------------------------------------------------------------------


def _show_message(payload=None, dw=radiald.COPYDATA_SHOW):
    data = json.dumps(payload or {"tag": None, "kind": None, "zbrush_hwnd": 0, "toggle": False}).encode()
    buf = ctypes.create_string_buffer(data, len(data))
    cds = W.COPYDATASTRUCT(dw, len(data), ctypes.cast(buf, ctypes.c_void_p))
    return buf, cds


def _send(pop, **kw):
    buf, cds = _show_message(**kw)
    return pop._on_copydata(ctypes.addressof(cds))


def test_a_show_is_taken_and_queued_and_ends_the_countdown(pop, setting, quits):
    setting(10)
    pop.idle_tick()
    pop.clock.after(10 * MIN - 1)
    assert _send(pop) == 1
    assert pop._work.get_nowait()[0] == pop.request_show
    pop.clock.after(5)                                     # past the time, but the press came first
    pop.idle_tick()                                        # (the window is not up yet: request_show runs on another thread)
    assert quits == []


def test_a_show_that_arrives_once_the_browser_has_decided_to_quit_is_refused_not_lost(pop, setting, quits):
    setting(10)
    pop.idle_tick()
    pop.clock.after(10 * MIN)
    pop.idle_tick()
    assert len(quits) == 1
    assert _send(pop) == radiald.SHOW_QUITTING             # the app starts a new browser rather than wait for this one
    assert pop._work.empty()


def test_other_messages_are_still_answered_as_before_while_it_quits(pop, setting, quits):
    setting(10)
    pop.idle_tick()
    pop.clock.after(10 * MIN)
    pop.idle_tick()
    assert _send(pop, dw=radiald.COPYDATA_THEME, payload={}) == 1
    assert _send(pop, dw=radiald.COPYDATA_QUIT, payload={}) == 1


def test_a_refused_show_after_the_decision_does_not_cancel_it(pop, setting, quits):
    setting(10)
    pop.idle_tick()
    pop.clock.after(10 * MIN)
    pop.idle_tick()
    _send(pop)
    pop.idle_tick()
    assert len(quits) == 1                                 # asked once; quit() ignores a second ask itself


# --- quit, and how the app can tell ------------------------------------------------------------------


@pytest.fixture
def ending(monkeypatch):
    """What quit does to the process, without doing it: threads are recorded, not started, and os._exit is a list."""
    exits, started = [], []

    class FakeThread:
        def __init__(self, target=None, **kw):
            started.append(target)

        def start(self):
            pass
    monkeypatch.setattr(popout.threading, "Thread", FakeThread)
    monkeypatch.setattr(popout.os, "_exit", lambda code: exits.append(code))
    return exits, started


def test_an_idle_quit_exits_with_the_idle_code_and_leaves_the_control_window_to_answer(pop, monkeypatch, ending):
    stopped = []
    monkeypatch.setattr(pop, "stop_ctl", lambda: stopped.append(1))
    pop.quit("unused for 30 minutes", idle=True)
    assert pop.quitting and pop.exit_code == radiald.POPOUT_EXIT_IDLE
    assert pop.window.destroyed == 1
    assert stopped == []                                   # a press now is answered "quitting", not met by a missing window
    pop.quit("again", idle=True)
    assert pop.window.destroyed == 1                       # once


def test_any_other_quit_exits_with_zero_and_closes_the_control_window_at_once(pop, monkeypatch, ending):
    stopped = []
    monkeypatch.setattr(pop, "stop_ctl", lambda: stopped.append(1))
    pop.quit("the app is gone")
    assert pop.exit_code == 0 and stopped == [1]


def test_the_backstop_and_a_failed_destroy_use_the_same_code(pop, monkeypatch, ending):
    exits, started = ending
    monkeypatch.setattr(pop, "stop_ctl", lambda: None)
    pop.window.destroy = lambda: 1 / 0
    pop.quit("unused", idle=True)
    assert exits == [radiald.POPOUT_EXIT_IDLE]
    monkeypatch.setattr(popout.time, "sleep", lambda s: None)
    started[0]()                                           # the 5 s backstop thread
    assert exits == [radiald.POPOUT_EXIT_IDLE] * 2


def test_an_idle_quit_says_why_in_popout_log(pop, setting, monkeypatch, ending):
    setting(30)
    lines = []
    monkeypatch.setattr(popout, "_log", lines.append)
    monkeypatch.setattr(pop, "stop_ctl", lambda: None)
    pop.idle_tick()
    pop.clock.after(30 * MIN)
    pop.idle_tick()
    assert "quitting (unused for 30 minutes (browser.quit_after_minutes))" in lines
    assert pop.exit_code == radiald.POPOUT_EXIT_IDLE and pop.window.destroyed == 1


# --- a second launch while it is going --------------------------------------------------------------


def _forward_args(tag=None):
    return {"show": True, "tag": tag, "zbrush": 0, "kind": None}


def test_a_launch_that_meets_a_quitting_browser_waits_and_starts_instead(monkeypatch):
    monkeypatch.setattr(popout.W, "find_message_window", lambda cls: 77)
    monkeypatch.setattr(popout.W, "send_copydata", lambda hwnd, dw, payload, timeout_ms=500: radiald.SHOW_QUITTING)
    assert popout._forward(_forward_args()) is popout.FORWARD_AGAIN


def test_a_launch_that_meets_a_vanishing_window_also_starts_instead(monkeypatch):
    windows = iter([77, 0])
    monkeypatch.setattr(popout.W, "find_message_window", lambda cls: next(windows))
    monkeypatch.setattr(popout.W, "send_copydata", lambda hwnd, dw, payload, timeout_ms=500: None)
    assert popout._forward(_forward_args()) is popout.FORWARD_AGAIN


def test_a_launch_that_meets_a_slow_window_is_forwarded_as_before(monkeypatch):
    monkeypatch.setattr(popout.W, "find_message_window", lambda cls: 77)
    monkeypatch.setattr(popout.W, "send_copydata", lambda hwnd, dw, payload, timeout_ms=500: None)
    assert popout._forward(_forward_args()) == 0
    monkeypatch.setattr(popout.W, "send_copydata", lambda hwnd, dw, payload, timeout_ms=500: 1)
    assert popout._forward(_forward_args()) == 0


class _Mutexes:
    """popout._acquire: the first call finds the old browser's mutex, later ones find it gone (or not)."""
    def __init__(self, answers):
        self.answers = list(answers)

    def __call__(self):
        return 1, self.answers.pop(0)


def _main_env(monkeypatch, acquire, forwards, gone=True):
    monkeypatch.setattr(popout.profiles, "ensure", lambda: "")
    monkeypatch.setattr(popout.profiles, "too_new", lambda: "")
    monkeypatch.setattr(popout, "_acquire", acquire)
    monkeypatch.setattr(popout.kernel32, "CloseHandle", lambda h: 1, raising=False)
    ran = []
    monkeypatch.setattr(popout, "_run", lambda opts, mutex: ran.append(mutex) or 0)
    monkeypatch.setattr(popout, "_forward", lambda opts: forwards.pop(0))
    monkeypatch.setattr(popout, "_wait_until_gone", lambda: gone)
    return ran


def test_a_launch_behind_a_quitting_browser_takes_over_once_it_has_gone(monkeypatch):
    ran = _main_env(monkeypatch, _Mutexes([True, False]), [popout.FORWARD_AGAIN])
    assert popout.main(["--popout", "--show"]) == 0
    assert ran == [1]


def test_a_launch_behind_a_browser_that_never_goes_gives_up_and_says_so(monkeypatch):
    ran = _main_env(monkeypatch, _Mutexes([True]), [popout.FORWARD_AGAIN], gone=False)
    assert popout.main(["--popout", "--show"]) == 1 and ran == []


def test_a_launch_beaten_to_the_mutex_by_another_is_forwarded_to_that_one(monkeypatch):
    ran = _main_env(monkeypatch, _Mutexes([True, True]), [popout.FORWARD_AGAIN, 0])
    assert popout.main(["--popout", "--show"]) == 0 and ran == []


def test_a_plain_launch_is_unchanged(monkeypatch):
    ran = _main_env(monkeypatch, _Mutexes([False]), [])
    assert popout.main(["--popout"]) == 0 and ran == [1]
    ran = _main_env(monkeypatch, _Mutexes([True]), [0])
    assert popout.main(["--popout"]) == 0 and ran == []
