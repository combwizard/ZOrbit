"""ZBrush 2022-2025: when the bridge key does not reach Zplugin > ZOrbit > Apply, the app runs a small fixed script
that presses Apply, and when that fails too it drops the pick so a later press of the key cannot apply it."""
import os
import types

import pytest

import config
import paths
import radiald
import zscript_bridge as zb
import win32 as W

EXE_DIR = r"C:\Users\you\ZBrush 2022"
LEGACY = {"name": "ZBrush 2022", "year": 2022, "path": EXE_DIR, "python": False, "supported": True}


class Env:
    """The app with everything outside it faked: files in tmp_path, the clock a number, process starts recorded."""

    def __init__(self, monkeypatch, tmp_path):
        self.tmp = tmp_path
        self.req_json = tmp_path / "request.json"
        self.req_txt = tmp_path / "request.txt"
        self.script = tmp_path / "ApplyFallback.txt"
        self.lines, self.toasts, self.started, self.routes, self.timers = [], [], [], [], []
        self.key = (True, None)                 # what press_bridge_key answers
        self.fail_start = False
        self.running = {"zbrush.exe"}
        self.mouse_down = False
        self.hung = False                       # what IsHungAppWindow answers
        self.window = True                      # ... and IsWindow, for ZBrush's window
        monkeypatch.setattr(W, "GetForegroundWindow", lambda: 4242)
        monkeypatch.setattr(W, "IsWindow", lambda hwnd: self.window)
        monkeypatch.setattr(W, "IsHungAppWindow", lambda hwnd: self.hung)
        monkeypatch.setattr(radiald, "REQUEST_FILE", str(self.req_json))
        monkeypatch.setattr(zb, "REQUEST_TXT", str(self.req_txt))
        monkeypatch.setattr(zb, "APPLY_SCRIPT", str(self.script))
        monkeypatch.setattr(radiald, "ZSCRIPT_LOG", str(tmp_path / "zscript_bridge.log"))
        monkeypatch.setattr(radiald, "log", self.lines.append)
        monkeypatch.setattr(W, "SetTimer", lambda ctrl, tid, *a: self.timers.append(("set", tid)))
        monkeypatch.setattr(W, "KillTimer", lambda ctrl, tid: self.timers.append(("kill", tid)))
        monkeypatch.setattr(W, "primary_down", lambda: self.mouse_down)
        monkeypatch.setattr(W, "nudge_mouse", lambda: None)
        monkeypatch.setattr(W, "running_exe_names", lambda: self.running)
        monkeypatch.setattr(radiald.subprocess, "Popen", self._popen)
        a = self.app = radiald.App(paths.DEFAULT_MENUS)
        a.cfg = config.load(paths.DEFAULT_MENUS)
        a.ctrl = 1
        monkeypatch.setattr(a, "_toast", self.toasts.append)
        monkeypatch.setattr(a, "target_install", lambda: LEGACY)
        monkeypatch.setattr(a, "target_in_front", lambda on_hook=False: True)
        monkeypatch.setattr(a, "press_bridge_key", lambda seq: self.key)
        monkeypatch.setattr(a, "_write_request", self._write_request)
        monkeypatch.setattr(a.activity, "note_pick", lambda *x, **k: None)
        monkeypatch.setattr(a.activity, "note_route", lambda *x, **k: self.routes.append(x))
        self.item = next(iter(a.cfg.menus.values())).items[0]

    def _popen(self, argv, **kw):
        if self.fail_start:
            raise OSError("no")
        self.started.append((argv, kw))
        return types.SimpleNamespace()

    def _write_request(self, item, legacy=None):
        self.app._seq += 1
        self.req_json.write_text("{}")
        zb.write_request(self.app._seq, "Clay", [{"press": "Tool:X"}])
        return self.app._seq

    def send(self):
        self.app.send(self.item)
        self.at = self.app._apply_watch["at"] if self.app._apply_watch else None
        return self.app._seq

    def taken(self):
        """The plugin's Apply reads the pick and deletes both files."""
        self.req_txt.unlink()
        self.req_json.unlink()

    def tick(self, seconds):
        """One timer tick, `seconds` after the key was pressed."""
        self.app._apply_tick(self.at + seconds)


@pytest.fixture
def env(monkeypatch, tmp_path):
    return Env(monkeypatch, tmp_path)


def test_the_key_works_so_nothing_else_happens(env):
    env.send()
    assert env.app._apply_watch is not None and ("set", radiald.TIMER_APPLY) in env.timers
    env.taken()
    env.tick(0.2)
    env.tick(2)
    assert env.started == [] and env.toasts == [] and env.routes == []
    assert env.app._apply_watch is None and ("kill", radiald.TIMER_APPLY) in env.timers
    assert not env.script.exists()


def test_nothing_happens_before_the_key_had_its_second(env):
    env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S - 0.1)
    assert env.started == [] and env.app._apply_watch is not None


def test_still_there_after_a_second_runs_the_install_s_exe_once_with_the_script(env):
    env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    assert len(env.started) == 1
    argv, kw = env.started[0]
    assert argv == [os.path.join(EXE_DIR, "ZBrush.exe"), str(env.script)]
    assert kw["env"] == paths.clean_env() and kw["cwd"] == EXE_DIR
    assert kw["creationflags"] & radiald.subprocess.DETACHED_PROCESS
    assert env.script.read_bytes() == zb.apply_script()
    assert any("did not reach Apply" in l and "fallback" in l for l in env.lines)
    assert env.toasts == []
    for s in (1.2, 2, 3, 5):                     # waiting on, never started twice
        env.tick(s)
    assert len(env.started) == 1


def test_the_fallback_worked_so_it_is_a_success_with_no_message(env):
    seq = env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    env.taken()
    env.tick(2.5)
    assert env.toasts == [] and env.app._apply_watch is None
    assert env.routes == [(seq, "zscript-fallback", True)]
    assert env.req_txt.exists() is False


def test_the_result_line_is_still_copied_after_the_fallback_worked(env):
    seq = env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    env.taken()
    env.tick(2.5)
    assert env.app._zs_result is not None and env.app._zs_result[0] == seq
    (env.tmp / "zscript_bridge.log").write_bytes(f"#{seq} 'Clay': press Tool:X: ok\n".encode("mbcs"))
    env.app._zs_result_tick()
    assert f"pick #{seq} result: 'Clay': press Tool:X: ok" in env.lines


def test_a_fallback_that_fails_drops_the_pick_and_says_so_once(env):
    seq = env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    env.tick(radiald.APPLY_KEY_WAIT_S + radiald.APPLY_SCRIPT_WAIT_S - 0.1)
    assert env.toasts == [] and env.req_txt.exists()           # not yet
    env.tick(radiald.APPLY_KEY_WAIT_S + radiald.APPLY_SCRIPT_WAIT_S)
    assert env.toasts == [radiald.MSG_BRIDGE_NO_RESPONSE]
    assert not env.req_txt.exists() and not env.req_json.exists()
    assert env.routes == [(seq, "zscript", False, "ZBrush did not take the pick")]
    assert env.app._apply_watch is None and len(env.started) == 1
    assert any(f"pick #{seq}" in l and "request removed" in l for l in env.lines)


def test_the_misleading_no_result_line_is_not_logged_for_a_dropped_pick(env):
    env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    env.tick(10)
    assert env.app._zs_result is None
    assert ("kill", radiald.TIMER_ZS_RESULT) in env.timers
    assert not any("wrote no result" in l for l in env.lines)
    assert env.toasts == [radiald.MSG_BRIDGE_NO_RESPONSE]


def test_a_newer_pick_takes_over_the_watch_and_is_not_dropped_by_the_old_timer(env):
    env.send()
    first = env.app._apply_watch
    env.tick(0.5)
    env.app._seq = 2                                             # pick 2 arrives 5 s later and replaces the file
    zb.write_request(2, "Other", [{"press": "Tool:Y"}])
    env.app._watch_apply(2, LEGACY, now=first["at"] + 5)
    assert env.app._apply_watch["seq"] == 2
    # pick 1's give-up time (7 s) has come: its watch is gone, so pick 2 is not dropped, it gets its own turn
    env.app._apply_tick(first["at"] + radiald.APPLY_KEY_WAIT_S + radiald.APPLY_SCRIPT_WAIT_S)
    assert env.toasts == [] and env.req_txt.exists() and len(env.started) == 1
    assert zb.pending_request(str(env.req_txt)) == 2


def test_a_request_of_another_number_is_never_dropped_by_the_watch(env):
    seq = env.send()
    # a pick that is not a bridge-key pick (a listener one) replaced the file
    zb.write_request(seq + 1, "Other", [{"press": "Tool:Y"}])
    env.tick(radiald.APPLY_KEY_WAIT_S + 1)
    env.tick(60)
    assert env.started == [] and env.toasts == [] and env.routes == []
    assert env.req_txt.exists() and env.req_json.exists()
    assert env.app._apply_watch is None


def test_a_replacement_during_the_fallback_ends_the_watch_quietly(env):
    seq = env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    zb.write_request(seq + 1, "Other", [{"press": "Tool:Y"}])
    env.tick(60)
    assert len(env.started) == 1 and env.toasts == [] and env.routes == [] and env.req_txt.exists()


def test_a_start_that_fails_is_logged_not_raised_and_the_pick_is_still_dropped_in_time(env):
    env.fail_start = True
    env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    assert any("could not run" in l for l in env.lines)
    env.tick(radiald.APPLY_KEY_WAIT_S + 2)
    assert env.started == [] and env.toasts == []              # no second try
    env.tick(radiald.APPLY_KEY_WAIT_S + radiald.APPLY_SCRIPT_WAIT_S)
    assert env.toasts == [radiald.MSG_BRIDGE_NO_RESPONSE] and not env.req_txt.exists()


def test_an_unreadable_script_folder_is_a_failed_start_too(env, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(zb, "ensure_apply_script", boom)
    env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    assert env.started == [] and any("could not run" in l for l in env.lines)


def test_no_zbrush_running_means_no_start(env):
    env.running = set()
    env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    assert env.started == [] and any("not running" in l for l in env.lines)


def test_a_key_that_was_not_sent_has_no_watch(env):
    env.key = (False, "ZBrush is not in front")
    env.send()
    assert env.app._apply_watch is None and env.started == []
    assert not env.req_txt.exists() and not env.req_json.exists()
    assert ("set", radiald.TIMER_APPLY) not in env.timers


def test_a_zbrush_2026_pick_never_uses_it(env, monkeypatch):
    modern = dict(LEGACY, name="ZBrush 2026", year=2026, python=True)
    monkeypatch.setattr(env.app, "target_install", lambda: modern)
    monkeypatch.setattr(env.app, "_listener", lambda pid: None)
    monkeypatch.setattr(env.app, "_front_pid", lambda: 1)
    env.send()
    assert env.app._apply_watch is None and ("set", radiald.TIMER_APPLY) not in env.timers
    assert env.started == []


def test_the_left_button_down_holds_the_watch_back(env):
    env.send()
    env.mouse_down = True
    env.tick(radiald.APPLY_KEY_WAIT_S + 3)
    assert env.started == []                                     # a stroke delays the key, so nothing yet
    env.mouse_down = False
    w = env.app._apply_watch
    env.app._apply_tick(w["deadline"] - 0.01)
    assert env.started == []
    env.app._apply_tick(w["deadline"])
    assert len(env.started) == 1


def test_a_stroke_does_not_hold_it_for_ever(env):
    env.send()
    env.mouse_down = True
    env.tick(radiald.ACK_HOLD_MAX_S + 1)
    env.tick(radiald.ACK_HOLD_MAX_S + 1 + radiald.APPLY_KEY_WAIT_S)
    assert len(env.started) == 1


def test_a_file_that_cannot_be_read_yet_is_waited_for(env, monkeypatch):
    env.send()
    monkeypatch.setattr(zb, "pending_request", lambda *a: (_ for _ in ()).throw(PermissionError()))
    env.tick(radiald.APPLY_KEY_WAIT_S + 1)
    assert env.started == [] and env.app._apply_watch is not None


# --- a ZBrush that is busy -----------------------------------------------------------------------
def test_a_zbrush_not_responding_is_waited_for_past_the_give_up_time_without_a_drop_or_message(env):
    env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)                          # the script has been started once
    env.hung = True
    for s in (5, 8, 20, 60, 200):
        env.tick(s)
    assert env.toasts == [] and env.routes == [] and env.req_txt.exists() and env.req_json.exists()
    assert env.app._apply_watch is not None and len(env.started) == 1


def test_a_hung_zbrush_is_not_given_the_script(env):
    env.send()
    env.hung = True
    env.tick(radiald.APPLY_KEY_WAIT_S + 0.5)
    env.tick(radiald.APPLY_KEY_WAIT_S + 3)
    assert env.started == []
    env.hung = False                                            # answering again: the script goes then, once
    env.tick(radiald.APPLY_KEY_WAIT_S + 3 + radiald.APPLY_KEY_WAIT_S)
    assert len(env.started) == 1


def test_when_zbrush_answers_again_the_time_starts_over_and_the_pick_can_still_land(env):
    seq = env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    env.hung = True
    env.tick(20)
    env.hung = False
    env.tick(20 + radiald.APPLY_SCRIPT_WAIT_S - 0.1)
    assert env.toasts == [] and env.req_txt.exists()
    env.taken()                                                 # the queued key lands
    env.tick(20 + radiald.APPLY_SCRIPT_WAIT_S)
    assert env.toasts == [] and env.app._apply_watch is None
    assert env.routes == [(seq, "zscript-fallback", True)]


def test_when_zbrush_answers_again_and_still_has_not_taken_it_the_pick_is_dropped(env):
    env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    env.hung = True
    env.tick(20)
    env.hung = False
    env.tick(20 + radiald.APPLY_SCRIPT_WAIT_S)
    assert env.toasts == [radiald.MSG_BRIDGE_NO_RESPONSE] and not env.req_txt.exists()


def test_a_zbrush_hung_for_ever_is_waited_for_only_up_to_the_cap(env):
    env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    env.hung = True
    env.tick(radiald.APPLY_BUSY_MAX_S - 5)
    assert env.toasts == [] and env.req_txt.exists()
    env.tick(radiald.APPLY_BUSY_MAX_S + 1)                      # past the cap, the extended time is up
    assert env.toasts == [radiald.MSG_BRIDGE_NO_RESPONSE] and not env.req_txt.exists()
    assert env.app._apply_watch is None


def test_a_late_pick_after_a_busy_spell_does_not_get_a_no_result_line(env):
    seq = env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    env.hung = True
    env.tick(40)
    assert env.app._zs_result[2] == env.at + 40 + radiald.ZS_RESULT_S
    env.hung = False
    env.taken()
    env.tick(41)
    (env.tmp / "zscript_bridge.log").write_bytes(f"#{seq} 'Clay': press Tool:X: ok\n".encode("mbcs"))
    env.app._zs_result_tick()
    assert f"pick #{seq} result: 'Clay': press Tool:X: ok" in env.lines
    assert not any("wrote no result" in l for l in env.lines)


def test_a_window_that_is_gone_with_zbrush_closed_drops_the_pick_without_a_message(env):
    seq = env.send()
    env.window, env.running = False, set()
    env.tick(0.2)
    assert env.toasts == [] and not env.req_txt.exists() and not env.req_json.exists()
    assert env.app._apply_watch is None and env.started == []
    assert env.routes == [(seq, "zscript", False, "ZBrush closed before it took the pick")]
    assert env.app._zs_result is None and not any("wrote no result" in l for l in env.lines)
    assert any("has closed" in l for l in env.lines)


def test_a_window_that_is_gone_while_zbrush_still_runs_changes_nothing(env):
    env.send()
    env.window = False                                          # a menu or box that was in front closed
    env.tick(radiald.APPLY_KEY_WAIT_S)
    assert len(env.started) == 1 and env.toasts == [] and env.req_txt.exists()
    env.tick(radiald.APPLY_KEY_WAIT_S + radiald.APPLY_SCRIPT_WAIT_S)
    assert env.toasts == [radiald.MSG_BRIDGE_NO_RESPONSE]


def test_no_window_to_ask_about_means_the_old_timing(env, monkeypatch):
    monkeypatch.setattr(env.app, "target_in_front", lambda on_hook=False: False)
    env.hung = True
    env.send()
    assert env.app._apply_watch["hwnd"] is None
    env.tick(radiald.APPLY_KEY_WAIT_S)
    assert len(env.started) == 1


def test_the_script_is_given_to_zbrush_by_its_short_name(env, monkeypatch):
    short = "C:\\USERS\\YOUR~1\\APPLYF~1.TXT"
    monkeypatch.setattr(zb, "ascii_path", lambda p, spaces=False: short if (spaces and p == str(env.script)) else p)
    env.send()
    env.tick(radiald.APPLY_KEY_WAIT_S)
    assert env.started[0][0] == [os.path.join(EXE_DIR, "ZBrush.exe"), short]


# --- the script ----------------------------------------------------------------------------------
def test_the_script_is_the_one_measured_and_never_presses_a_literal_path():
    text = zb.apply_script().decode("ascii")
    assert text.splitlines() == [
        '[VarDef, p, ""][RoutineDef, Press, [If, [IExists, #p], [IPress, #p]]]'
        '[VarSet, p, "Zplugin:ZOrbit:Apply"][RoutineCall, Press]']
    assert '[IPress, "' not in text and "[IGetID" not in text
    assert text.endswith("\r\n")


def test_the_script_is_written_when_missing_or_different_and_reused_otherwise(tmp_path):
    p = tmp_path / "a.txt"
    assert zb.ensure_apply_script(str(p)) == str(p)
    assert p.read_bytes() == zb.apply_script()
    first = p.stat().st_mtime_ns
    os.utime(p, ns=(first - 5_000_000_000, first - 5_000_000_000))
    old = p.stat().st_mtime_ns
    zb.ensure_apply_script(str(p))
    assert p.stat().st_mtime_ns == old                          # same content: left alone
    p.write_bytes(b"old script\r\n")
    (tmp_path / "a.zsc").write_bytes(b"compiled from the old one")
    zb.ensure_apply_script(str(p))
    assert p.read_bytes() == zb.apply_script()
    assert not (tmp_path / "a.zsc").exists()                    # a stale compiled copy would be run instead


def test_the_pending_number_is_read_from_the_second_line(tmp_path):
    p = tmp_path / "request.txt"
    assert zb.pending_request(str(p)) is None
    zb.REQUEST_TXT, keep = str(p), zb.REQUEST_TXT
    try:
        zb.write_request(41, "Clay", [{"press": "Tool:X"}])
    finally:
        zb.REQUEST_TXT = keep
    assert zb.pending_request(str(p)) == 41
    p.write_bytes(b"something else\n")
    assert zb.pending_request(str(p)) == 0


def test_the_message_fits_the_toast_and_names_the_button():
    assert "Zplugin > ZOrbit > Apply" in radiald.MSG_BRIDGE_NO_RESPONSE
