"""A new app replaces an older one that holds the single-instance mutex. No real windows or processes: win32 is faked."""
import contextlib

import pytest

import paths
import profiles
import radiald

W = radiald.W
OLD = (4242, 77, "0.0.1")
NEW_VERSION = paths.VERSION


@pytest.fixture(autouse=True)
def quiet(tmp_path, monkeypatch):
    """Nothing here may touch the real log or sleep."""
    monkeypatch.setattr(radiald, "DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(radiald, "LOG_FILE", str(tmp_path / "data" / "radiald.log"))
    monkeypatch.setattr(radiald, "_trim_log", lambda *a, **k: None)
    monkeypatch.setattr(radiald.time, "sleep", lambda s: None)


class World:
    """The Windows calls claim_instance makes, as recordable fakes."""

    def __init__(self, monkeypatch, existed=True, running=OLD, quits=True, browser_polls=0, elevated=False):
        self.calls, self.closed, self.lock_state = [], [], []
        self.quit_args = None
        self.polls = browser_polls
        self.running = running
        self.quits = quits
        self.elevated = elevated
        self.existed = existed
        m = monkeypatch.setattr
        m(W, "create_mutex", lambda name: (11, self.existed))
        m(W, "running_app", lambda: self.running)
        m(W, "ask_to_quit", self._ask)
        m(W, "mutex_exists", self._probe)
        m(W, "process_elevated", lambda pid: self.elevated)
        m(W, "process_created", lambda pid: None)
        m(W, "launch_chain", lambda depth=2: "test")
        m(W, "CloseHandle", self.closed.append)
        m(radiald.fsutil, "named_lock", self._lock)

    def _ask(self, pid, tid, wait_s):
        self.calls.append("ask_to_quit")
        self.quit_args = (pid, tid, wait_s)
        return self.quits

    def _probe(self, name):
        self.calls.append(("probe", name))
        if self.polls > 0:
            self.polls -= 1
            return True
        return False

    @contextlib.contextmanager
    def _lock(self, name, wait_ms):
        self.lock_state.append(("enter", name, wait_ms))
        try:
            yield True
        finally:
            self.lock_state.append(("exit", name))


@pytest.fixture
def world(monkeypatch):
    return World(monkeypatch)


def claim(**kw):
    lines = []
    return radiald.claim_instance(log=lines.append, **kw), lines


# --- the decision --------------------------------------------------------------------------------
def test_takeover_plan_takes_over_an_older_app():
    plan = radiald.takeover_plan((1, 2, "0.11.9"), "0.12.0")
    assert plan[0] == "take" and "0.11.9" in plan[1]
    assert radiald.takeover_plan((1, 2, "0.9.0"), "0.12.0")[0] == "take"      # numbers, not text


def test_takeover_plan_leaves_the_same_or_a_newer_app_alone():
    assert radiald.takeover_plan((1, 2, "0.12.0"), "0.12.0") == ("exit", "same version")
    action, why = radiald.takeover_plan((1, 2, "0.13.0"), "0.12.0")
    assert action == "exit" and why == "newer version 0.13.0"


def test_takeover_plan_with_no_tray_window_or_a_strange_version():
    assert radiald.takeover_plan(None, "0.12.0") == ("exit", "version unknown")
    assert radiald.takeover_plan((1, 2, "beta"), "0.12.0") == ("exit", "version unknown")


# --- claim_instance ------------------------------------------------------------------------------
def test_with_no_other_instance_the_handle_comes_back_and_nothing_is_asked(monkeypatch):
    w = World(monkeypatch, existed=False)
    handle, _ = claim()
    assert handle == 11 and w.calls == [] and w.lock_state == []


def test_an_older_app_that_quits_is_replaced(world):
    handle, lines = claim()
    assert handle == 11
    assert world.quit_args[:2] == (OLD[0], OLD[1]) and world.quit_args[2] > 0
    assert world.closed == []
    assert any(l == "taking over from ZOrbit 0.0.1 (pid 4242)" for l in lines)


def test_an_older_app_that_does_not_quit_keeps_the_instance(monkeypatch):
    w = World(monkeypatch, quits=False)
    handle, lines = claim()
    assert handle is None and w.closed == [11]
    assert any("another instance is already running; exiting" in l and "it did not quit in time" in l for l in lines)


def test_an_elevated_older_app_is_reported_as_access_denied(monkeypatch):
    w = World(monkeypatch, quits=False, elevated=None)
    handle, lines = claim()
    assert handle is None and w.closed == [11]
    assert any("access denied" in l for l in lines)


@pytest.mark.parametrize("running, why", [((9, 8, NEW_VERSION), "same version"),
                                          ((9, 8, "99.0.0"), "newer version 99.0.0"),
                                          (None, "version unknown")])
def test_a_current_newer_or_unknown_app_is_left_alone(monkeypatch, running, why):
    w = World(monkeypatch, running=running)
    handle, lines = claim()
    assert handle is None and w.closed == [11]
    assert "ask_to_quit" not in w.calls
    assert any("another instance is already running; exiting" in l and why in l for l in lines)


def test_a_visible_old_browser_is_waited_for_briefly_then_left(monkeypatch):
    w = World(monkeypatch, browser_polls=10 ** 6)
    ticks = iter(range(0, 100))
    monkeypatch.setattr(radiald.time, "monotonic", lambda: next(ticks))
    handle, lines = claim()
    assert handle == 11
    assert ("probe", radiald.POPOUT_MUTEX) in w.calls
    assert any("browser window is still open" in l for l in lines)


def test_a_hidden_old_browser_that_ends_is_not_reported(monkeypatch):
    w = World(monkeypatch, browser_polls=2)
    handle, lines = claim()
    assert handle == 11 and w.polls == 0
    assert not any("still open" in l for l in lines)


def test_the_takeover_lock_is_held_until_the_caller_lets_go(world):
    with contextlib.ExitStack() as hold:
        handle, _ = claim(hold=hold)
        assert handle == 11
        assert [s[0] for s in world.lock_state] == ["enter"]
        assert world.lock_state[0][1] == radiald.TAKEOVER_MUTEX
    assert [s[0] for s in world.lock_state] == ["enter", "exit"]


def test_the_takeover_lock_is_released_when_the_claim_fails(monkeypatch):
    w = World(monkeypatch, quits=False)
    with contextlib.ExitStack() as hold:
        handle, _ = claim(hold=hold)
        assert handle is None
    assert [s[0] for s in w.lock_state] == ["enter", "exit"]


def test_without_a_hold_the_lock_is_released_before_the_claim_returns(world):
    claim()
    assert [s[0] for s in world.lock_state] == ["enter", "exit"]


def test_the_lock_is_released_when_something_in_the_claim_raises(world, monkeypatch):
    monkeypatch.setattr(W, "running_app", lambda: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        claim()
    assert [s[0] for s in world.lock_state] == ["enter", "exit"]


# --- main ----------------------------------------------------------------------------------------
class Order:
    """Records the steps main() takes, with fakes for each."""

    def __init__(self, monkeypatch, claims=11):
        self.steps, self.apps = [], []
        order = self
        m = monkeypatch.setattr

        def claim_instance(log=None, hold=None):
            order.steps.append("claim")
            return claims
        m(radiald, "claim_instance", claim_instance)
        m(profiles, "ensure", lambda: order.steps.append("ensure") or "x")
        m(profiles, "tidy_leftovers", lambda: order.steps.append("tidy"))
        m(profiles, "absorb_stray_usage", lambda now=None: order.steps.append("absorb") or 0)
        m(radiald, "check", lambda path: order.steps.append("check") or 0)

        class FakeApp:
            def __init__(self, *a, **k):
                order.apps.append(a)
                order.steps.append("app")

            def run(self, mutex=None, hold=None):
                order.steps.append(("run", mutex))
                return 0
        m(radiald, "App", FakeApp)


def test_main_claims_before_it_touches_the_files(profile_env, monkeypatch):
    o = Order(monkeypatch)
    assert radiald.main([]) == 0
    assert o.steps == ["claim", "ensure", "tidy", "absorb", "app", ("run", 11)]


def test_main_exits_quietly_when_the_claim_fails(profile_env, monkeypatch):
    o = Order(monkeypatch, claims=None)
    assert radiald.main([]) == 0
    assert o.steps == ["claim"]


def test_main_logs_the_usage_it_took_in(profile_env, monkeypatch):
    o = Order(monkeypatch)
    lines = []
    monkeypatch.setattr(radiald, "log", lines.append)
    monkeypatch.setattr(profiles, "absorb_stray_usage", lambda now=None: 3)
    radiald.main([])
    assert "usage: added 3 brushes from an older version" in lines


def test_check_claims_nothing_and_absorbs_nothing(profile_env, monkeypatch):
    o = Order(monkeypatch)
    assert radiald.main(["--check"]) == 0
    assert o.steps == ["ensure", "check"]


def test_a_pinned_start_neither_tidies_nor_absorbs(profile_env, monkeypatch, tmp_path):
    o = Order(monkeypatch)
    assert radiald.main(["--config", str(tmp_path / "radial.json")]) == 0
    assert o.steps == ["claim", "app", ("run", 11)]


def test_files_from_a_newer_zorbit_stop_the_start(profile_env, monkeypatch):
    o = Order(monkeypatch)
    shown, closed = [], []
    monkeypatch.setattr(profiles, "too_new", lambda: "These files were made by ZOrbit 9.9.9.")
    monkeypatch.setattr(radiald, "_show_fatal", shown.append)
    monkeypatch.setattr(W, "CloseHandle", closed.append)
    assert radiald.main([]) == 1
    assert o.apps == [] and "tidy" not in o.steps and "absorb" not in o.steps
    assert shown == ["These files were made by ZOrbit 9.9.9."]
    assert closed == [11]


def test_check_with_files_from_a_newer_zorbit_prints_the_message(profile_env, monkeypatch, capsys):
    o = Order(monkeypatch)
    monkeypatch.setattr(profiles, "too_new", lambda: "These files were made by ZOrbit 9.9.9.")
    assert radiald.main(["--check"]) == 1
    assert "ZOrbit 9.9.9" in capsys.readouterr().out
    assert "check" not in o.steps and "claim" not in o.steps
