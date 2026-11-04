"""The app's half of the browser's idle quit (browser.quit_after_minutes): it tells a quit after sitting unused from a
crash by the exit code, keeps the browser gone until it is asked for, and does not lose the press that arrives as the
browser is quitting. The processes and threads are fakes; nothing is started."""
import json

import pytest

import config
import paths
import radiald
import win32 as W


class FakePopen:
    made = []

    def __init__(self, cmd, **kw):
        self.cmd, self.code = cmd, FakePopen.exit_code
        FakePopen.made.append(self)

    def wait(self):
        return self.code

    def poll(self):
        return None if self.code is None else self.code


class Thread:
    """Runs its target when started (a watcher that waits for a fake process ends at once), or never when held."""
    held = False

    def __init__(self, target=None, **kw):
        self.target = target

    def start(self):
        if not Thread.held:
            self.target()


@pytest.fixture
def app(monkeypatch):
    FakePopen.made, FakePopen.exit_code, Thread.held = [], 0, False
    a = radiald.App(paths.DEFAULT_MENUS)
    a.cfg = config.load(paths.DEFAULT_MENUS)
    a.cfg.browser_quit_minutes = 30
    a.ctrl = 1
    a.timers, a.logged, a.sent = [], [], []
    a.windows = {radiald.POPOUT_CLASS: 0}                 # the browser's control window: 0 = none
    a.answers = [1]                                       # what SHOW is answered, in turn
    monkeypatch.setattr(W, "SetTimer", lambda hwnd, tid, ms, cb: a.timers.append(tid) or 1)
    monkeypatch.setattr(W, "KillTimer", lambda hwnd, tid: 1)
    monkeypatch.setattr(W, "GetForegroundWindow", lambda: 0)
    monkeypatch.setattr(W, "find_message_window", lambda cls: a.windows.get(cls, 0))

    def send(hwnd, dw, payload, timeout_ms=500):
        a.sent.append((dw, json.loads(payload)))
        return a.answers.pop(0) if len(a.answers) > 1 else a.answers[0]
    monkeypatch.setattr(W, "send_copydata", send)
    monkeypatch.setattr(radiald.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(radiald.threading, "Thread", Thread)
    monkeypatch.setattr(radiald, "log", a.logged.append)
    a.spawns = []                                         # every _spawn_popout(show, tag, zb_hwnd, kind), also when held
    real = a._spawn_popout
    monkeypatch.setattr(a, "_spawn_popout", lambda *args: a.spawns.append(args) or real(*args))
    return a


def started(app):
    return [p.cmd for p in FakePopen.made]


def prewarms(app):
    return app.timers.count(radiald.TIMER_PREWARM)


def run_idle_quit(app):
    """The app starts a browser hidden and it exits with the idle code."""
    FakePopen.exit_code = radiald.POPOUT_EXIT_IDLE
    app._spawn_popout(False)
    FakePopen.exit_code = 0


# --- told apart from a crash -------------------------------------------------------------------


def test_an_idle_quit_is_logged_as_a_choice_and_not_as_a_failure(app):
    run_idle_quit(app)
    assert app._popout_idle_quit is app._popout_proc
    assert any("quit after sitting unused" in s for s in app.logged)
    assert not any("exited with code" in s for s in app.logged)


@pytest.mark.parametrize("code", [0, 1, 3, -1, 0xC0000005])
def test_any_other_exit_is_logged_as_before_and_is_not_an_idle_quit(app, code):
    FakePopen.exit_code = code
    app._spawn_popout(False)
    assert app._popout_idle_quit is None
    assert f"popout exited with code {code}" + (" (popout.log says why)" if code else "") in app.logged


def test_the_idle_code_is_not_one_of_the_ordinary_ones():
    assert radiald.POPOUT_EXIT_IDLE not in (0, 1) and radiald.SHOW_QUITTING not in (0, 1)


# --- it stays gone until asked for ---------------------------------------------------------------


def test_after_an_idle_quit_a_config_load_does_not_start_it_again(app):
    app._prewarmed = False                               # a press earlier made the next load free to pre-warm
    run_idle_quit(app)
    app._schedule_prewarm()
    assert prewarms(app) == 0
    app._prewarm()                                       # even a timer already running
    assert len(FakePopen.made) == 1


def test_a_profile_switch_and_a_reload_leave_it_gone_however_often_they_come(app):
    app._prewarmed = False
    run_idle_quit(app)
    for _ in range(5):
        app._schedule_prewarm()
        app._prewarm()
    assert prewarms(app) == 0 and len(FakePopen.made) == 1


def test_after_a_crash_the_next_config_load_warms_it_as_before(app):
    app._prewarmed = False
    FakePopen.exit_code = 1
    app._spawn_popout(False)
    FakePopen.exit_code = 0
    app._schedule_prewarm()
    assert prewarms(app) == 1
    app._prewarm()
    assert len(FakePopen.made) == 2


def test_with_the_setting_off_an_exit_with_that_code_does_not_hold_it_back(app):
    app.cfg.browser_quit_minutes = 0                     # turned off while it ran; the code only says what happened
    app._prewarmed = False
    run_idle_quit(app)
    app._schedule_prewarm()
    assert prewarms(app) == 1


def test_turning_the_setting_off_after_an_idle_quit_lets_it_warm_again(app):
    app._prewarmed = True                                # the start-up pre-warm
    run_idle_quit(app)
    app._schedule_prewarm()
    assert prewarms(app) == 0
    app.cfg.browser_quit_minutes = 0
    app._schedule_prewarm()
    assert prewarms(app) == 1


def test_turning_it_on_again_does_not_bring_back_a_stale_idle_quit(app):
    run_idle_quit(app)
    app.cfg.browser_quit_minutes = 0
    app._schedule_prewarm()
    app._prewarm()
    app.cfg.browser_quit_minutes = 30
    FakePopen.exit_code = None                           # the browser that was warmed is up
    assert app._popout_idle_quit is None


def test_a_browser_without_the_setting_never_changes_what_the_app_does(app):
    app.cfg.browser_quit_minutes = 0
    app._schedule_prewarm()
    assert prewarms(app) == 1
    app._prewarm()
    assert started(app)[0][-1] == "--managed"


# --- the next press ---------------------------------------------------------------------------


def test_a_press_after_an_idle_quit_starts_it_once_and_shown(app):
    run_idle_quit(app)
    app.spawns.clear()
    Thread.held = True                                   # the new process is coming up
    app.open_browser(None, toggle=True)
    assert len(app.spawns) == 1 and app.spawns[0][0] is True        # shown
    app.open_browser(None, toggle=True)                  # a second press during the slow start
    app.open_browser(None, toggle=False)
    assert len(app.spawns) == 1


def test_the_command_of_the_press_after_an_idle_quit_shows_and_is_managed(app):
    run_idle_quit(app)
    FakePopen.made.clear()
    app.open_browser("tagkey", kind="alpha")
    cmd = FakePopen.made[0].cmd
    assert "--managed" in cmd and "--show" in cmd and cmd[cmd.index("--tag") + 1] == "tagkey"
    assert cmd[cmd.index("--kind") + 1] == "alpha"


def test_after_the_press_a_config_load_is_free_to_warm_but_finds_it_up(app):
    run_idle_quit(app)
    FakePopen.exit_code = None
    app.open_browser(None)
    app.windows[radiald.POPOUT_CLASS] = 55               # it is up
    app._schedule_prewarm()
    app._prewarm()
    assert len(FakePopen.made) == 2                      # the idle one, then the press: no third


def test_a_show_that_is_taken_starts_nothing(app):
    app.windows[radiald.POPOUT_CLASS] = 55
    app.open_browser(None, toggle=True)
    assert app.spawns == [] and len(app.sent) == 1


def test_a_press_met_by_quitting_starts_a_new_one_that_shows_itself(app):
    app.windows[radiald.POPOUT_CLASS] = 55               # the old one is going but its window still answers
    app.answers = [radiald.SHOW_QUITTING]
    Thread.held = True
    app.open_browser("tagkey", toggle=True, kind="texture")
    assert [(a[0], a[1], a[3]) for a in app.spawns] == [(True, "tagkey", "texture")]
    assert any("popout is quitting" in s for s in app.logged)


def test_presses_while_the_old_one_is_still_quitting_start_one_new_one_only(app):
    app.windows[radiald.POPOUT_CLASS] = 55
    app.answers = [radiald.SHOW_QUITTING]
    Thread.held = True
    for _ in range(4):
        app.open_browser(None, toggle=True)
    assert len(app.spawns) == 1


def test_a_press_met_by_a_window_that_vanished_mid_call_starts_a_new_one(app):
    seen = iter([55, 0])
    app.windows = type("Gone", (), {"get": lambda self, cls, d=0: next(seen)})()
    app.answers = [None]
    Thread.held = True
    app.open_browser(None)
    assert len(app.spawns) == 1


def test_a_window_that_does_not_answer_but_is_still_there_is_left_alone_as_before(app):
    app.windows[radiald.POPOUT_CLASS] = 55
    app.answers = [None]
    app.open_browser(None)
    assert app.spawns == []
    assert any("no answer within 0.5 s" in s for s in app.logged)


def test_a_refused_show_that_is_not_the_quitting_answer_is_left_alone_as_before(app):
    app.windows[radiald.POPOUT_CLASS] = 55
    app.answers = [0]
    app.open_browser(None)
    assert app.spawns == []
