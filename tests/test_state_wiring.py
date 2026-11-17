"""The state channel in the app (issue #188, phase 4): radiald.App asks zstate.Channel after a ring is on screen, hands
the ring its marks, refreshes an open ring when the plugin's answer comes, records each pick that was handed to a ZBrush
and takes back each one it drops, and stops the channel when it quits.

No window, hook or ZBrush: the ring is the real one set up as show() sets it up, without the window; PostMessageW, the
foreground window and the process checks are faked; the data folder is a throw-away one.
"""
import ctypes.wintypes as w
import json
import os

import pytest

import radiald
import ring
import usage
import win32 as W
import zstate

PID = 4242                 # the ZBrush 2026 in front, whose plugin answers
OTHER_PID = 5151           # another ZBrush: a ZBrush 2022 to 2025, or a second 2026
LISTENER = 0x1234          # its listener window
CTRL = 0x99                # the app's control window
WORK = w.RECT(0, 0, 1920, 1040)
SYM, SIZE, CLEAR = "Transform:Activate Symmetry", "Draw:Draw Size", "Tool:Masking:Clear"
MENUS = {
    "m": {"title": "M", "hotkey": "Q", "items": [{"toggle": SYM}, {"set": SIZE, "value": 64}, {"press": CLEAR},
                                                  {"brush": "Move"}]},
    "plain": {"title": "Plain", "hotkey": "W", "items": [{"brush": "Move"}, {"brush": "Clay"}]},
}
LEGACY = {"name": "ZBrush 2022", "python": False, "path": "C:/Program Files/ZBrush 2022"}


def listener_json(path, pid=PID, **over):
    info = {"hwnd": LISTENER, "pid": pid, "verified": 1762430000.0, "state": 1}
    info.update(over)
    path.write_text(json.dumps({k: v for k, v in info.items() if v is not None}), encoding="utf-8")


class Spy:
    """Stands in for zstate.Channel: records each call; the names in `raises` raise."""

    def __init__(self, raises=()):
        self.calls = []
        self.raises = set(raises)
        self.pid = 0
        self.ready = True

    def _call(self, name, *args, **kw):
        self.calls.append((name, args, kw))
        if name in self.raises:
            raise RuntimeError(f"{name} broke")

    def ask(self, menu, resolve, **kw):
        self._call("ask", menu.id, **kw)
        self.pid = kw["pid"] if kw["enabled"] and kw["capable"] and kw["listener"] is not None else 0
        return True

    def marks(self, menu):
        self._call("marks", menu.id)
        return [zstate.Mark(lit=True) if it.kind == "toggle" else None for it in menu.items]

    def on_ready(self, snapshot_id=0):
        self._call("on_ready", snapshot_id)
        return self.ready

    def picked(self, seq, pid):
        self._call("picked", seq, pid)

    def dropped(self, seq):
        self._call("dropped", seq)

    def stop(self):
        self._call("stop")

    def named(self, name):
        return [c for c in self.calls if c[0] == name]


@pytest.fixture
def env(tmp_path, monkeypatch):
    for c in (ring._sprite_cache, ring._slot_cache, ring._static_layers, ring._fan_line_cache):
        c.clear()
    for name in ("_prefetch", "_schedule_prewarm", "_prune_icons"):
        monkeypatch.setattr(radiald.App, name, lambda self: None)
    monkeypatch.setattr(radiald.App, "icon_for", lambda self, item: None)
    ev = {"events": [], "lines": [], "front": PID, "first_marks": [], "pick_posts": []}
    data = tmp_path / "data"

    def show(self, x, y):                     # Ring.show without the window: placed and prepared, first frame marked
        ev["events"].append(("show", os.path.exists(data / zstate.QUERY_FILE)))
        self._place(x, y, *W.monitor_for_point(x, y))
        self._prepare()
        ev["first_marks"].append(self._marks.get(()))
    monkeypatch.setattr(ring.Ring, "show", show)
    monkeypatch.setattr(W, "monitor_for_point", lambda x, y: (WORK, 1.0))
    monkeypatch.setattr(W, "SetTimer", lambda *a: 1)
    monkeypatch.setattr(W, "KillTimer", lambda *a: 0)
    monkeypatch.setattr(W, "nudge_mouse", lambda: None)
    monkeypatch.setattr(W, "primary_down", lambda: False)
    monkeypatch.setattr(W, "IsWindow", lambda hwnd: True)
    monkeypatch.setattr(W, "GetForegroundWindow", lambda: 77)
    monkeypatch.setattr(W, "window_pid", lambda hwnd: ev["front"])

    def post(hwnd, msg, wparam, lparam):      # the app's own posts: picks to the listener
        ev["pick_posts"].append((int(getattr(hwnd, "value", hwnd) or 0), msg, wparam))
        return 1
    monkeypatch.setattr(W, "PostMessageW", post)
    monkeypatch.setattr(radiald, "log", ev["lines"].append)
    listener = tmp_path / "listener.json"
    listener_json(listener)
    monkeypatch.setattr(radiald, "LISTENER_FILE", str(listener))
    monkeypatch.setattr(radiald, "REQUEST_FILE", str(tmp_path / "request.json"))
    radial = tmp_path / "radial.json"
    radial.write_text(json.dumps({"menus": MENUS}), encoding="utf-8")
    app = radiald.App(str(radial))
    app.usage = usage.Usage(str(tmp_path / "usage.json"))
    app.ctrl = CTRL
    app.load_config(force=True, balloon=False)
    monkeypatch.setattr(app, "_exe_of", lambda pid, cache=None: app.target_exe)
    monkeypatch.setattr(app.activity, "note_open", lambda *a, **k: None)
    monkeypatch.setattr(app.activity, "note_pick", lambda *a, **k: None)
    monkeypatch.setattr(app.activity, "note_ack", lambda *a, **k: None)
    monkeypatch.setattr(app.activity, "note_route", lambda *a, **k: None)
    monkeypatch.setattr(app, "_toast", lambda text: None)

    def channel_post(hwnd, msg, wparam, lparam):    # the channel's posts: questions to the listener
        ev["events"].append(("post", int(getattr(hwnd, "value", hwnd)), msg, wparam, lparam))
        return True
    app.state = zstate.Channel(channel_post, CTRL, str(data), log=ev["lines"].append)
    ev.update(app=app, data=data, listener=listener)
    return ev


def open_ring(env, menu_id="m"):
    app = env["app"]
    app.open_menu(app.cfg.menus[menu_id], (500, 400), held=True)
    return app.ring


def answer(env, qid=None, pid=PID, pick=0, items=None):
    """The plugin's zstate.json for the newest question (or qid)."""
    items = items if items is not None else {SYM: {"s": "ok", "v": 1.0}, SIZE: {"s": "ok", "v": 32.0, "min": 1.0,
                                                                                  "max": 1000.0},
                                             CLEAR: {"s": "missing"}}
    snap = {"v": 1, "id": qid if qid is not None else env["app"].state._id, "pick": pick, "pid": pid,
            "session": "429428", "time": 1762430000.2, "ms": 1.5, "truncated": False, "extras": {}, "items": items}
    (env["data"] / zstate.STATE_FILE).write_text(json.dumps(snap), encoding="utf-8")
    return snap["id"]


def ready(env, qid):
    return env["app"]._ctrl_proc(CTRL, radiald.WM_APP_STATE_READY, qid, 0)


# --- asking ------------------------------------------------------------------------------------------------------------
def test_the_message_number_is_zstates_and_the_free_one_between_18_and_20():
    assert radiald.WM_APP_STATE_READY == zstate.WM_APP_STATE_READY == W.WM_APP + 19
    numbers = [v for k, v in vars(radiald).items() if k.startswith(("WM_APP_", "WM_HOOK_"))]
    assert len(numbers) == len(set(numbers))


def test_a_ring_open_asks_once_after_the_ring_is_shown(env):
    r = open_ring(env)
    assert env["events"] == [("show", False), ("post", LISTENER, zstate.WM_APP_STATE, 1, CTRL)]
    q = json.loads((env["data"] / zstate.QUERY_FILE).read_text(encoding="utf-8"))
    assert q["id"] == 1 and [p["p"] for p in q["paths"]] == [SYM, SIZE, CLEAR]
    assert r._marks_fn is not None and env["app"].state.pid == PID


def test_the_listener_lookup_gives_the_flag_and_picks_still_get_the_window(env):
    app = env["app"]
    hwnd, capable = app._listener_info(PID)
    assert hwnd.value == LISTENER and capable is True
    assert app._listener(PID).value == LISTENER
    listener_json(env["listener"], state=None)
    assert app._listener_info(PID)[1] is False and app._listener(PID).value == LISTENER


@pytest.mark.parametrize("case", ["setting off", "no listener", "old plugin", "listener of another ZBrush",
                                  "ZBrush 2022 in front", "unverified listener", "listener for another exe"])
def test_nothing_is_asked_and_the_ring_is_as_before(env, monkeypatch, case):
    app = env["app"]
    if case == "setting off":
        app.cfg.bridge_show_state = False
    elif case == "no listener":
        env["listener"].unlink()
    elif case == "old plugin":
        listener_json(env["listener"], state=None)
    elif case == "listener of another ZBrush":
        listener_json(env["listener"], pid=OTHER_PID)
    elif case == "ZBrush 2022 in front":            # its pick goes by the ZScript bridge; the listener is a 2026's
        env["front"] = OTHER_PID
        monkeypatch.setattr(app, "target_install", lambda: LEGACY)
    elif case == "unverified listener":
        listener_json(env["listener"], verified=None)
    else:
        monkeypatch.setattr(app, "_exe_of", lambda pid, cache=None: "notzbrush.exe")
    r = open_ring(env)
    assert env["events"] == [("show", False)]
    assert not (env["data"] / zstate.QUERY_FILE).exists() and not env["data"].exists()
    assert r._marks_fn is None and env["first_marks"] == [None]
    assert app.state.marks(r.menu) is None
    assert not [ln for ln in env["lines"] if "listener.json" in ln or "ZBrush state" in ln]


def test_turning_the_setting_off_takes_the_question_away_at_the_next_open(env):
    app = env["app"]
    open_ring(env)
    assert (env["data"] / zstate.QUERY_FILE).exists()
    app.ring = None
    app.cfg.bridge_show_state = False
    open_ring(env)
    assert not (env["data"] / zstate.QUERY_FILE).exists()
    assert [e for e in env["events"] if e[0] == "post"] == [("post", LISTENER, zstate.WM_APP_STATE, 1, CTRL)]


def test_turning_the_setting_off_takes_the_question_away_when_the_config_loads(env, tmp_path):
    app = env["app"]
    open_ring(env)
    query = env["data"] / zstate.QUERY_FILE
    radial = tmp_path / "radial.json"
    app.load_config(force=True, balloon=False)                     # still on: the question stays
    assert query.exists()
    radial.write_text(json.dumps({"bridge": {"show_state": False}, "menus": MENUS}), encoding="utf-8")
    app.load_config(force=True, balloon=False)
    assert not app.cfg.bridge_show_state and not query.exists()


BAD_LISTENERS = {"infinity": '{"hwnd": Infinity, "pid": 4242, "verified": 1, "state": 1}',
                 "nested": "[" * 100000 + "]" * 100000,
                 "pid Infinity": '{"hwnd": 4660, "pid": Infinity, "verified": 1, "state": 1}',
                 "not an object": '"listener"', "binary": "\udcff"}


@pytest.mark.parametrize("name", BAD_LISTENERS)
def test_a_bad_listener_file_never_stops_a_ring_or_a_pick(env, picks, name):
    env["listener"].write_bytes(BAD_LISTENERS[name].encode("utf-8", "surrogateescape"))
    app = env["app"]
    app.state = zstate.Channel(lambda *a: pytest.fail("asked"), CTRL, str(env["data"]), log=env["lines"].append)
    r = open_ring(env)
    assert app.ring is r and r._marks_fn is None and not env["data"].exists()
    app.ring = None
    app.send(env["item"])                               # no listener: the bridge key
    assert env["pressed"] == [7] and env["pick_posts"] == []


def test_a_lookup_that_raises_is_nothing_to_ask_and_said_once(env, monkeypatch):
    app = env["app"]

    def boom():
        raise RuntimeError("no foreground window")
    monkeypatch.setattr(app, "_front_pid", boom)
    r = open_ring(env)
    assert app.ring is r and r._marks_fn is None and env["events"] == [("show", False)]
    app.ring = None
    open_ring(env)
    assert len([ln for ln in env["lines"] if ln.startswith("ZBrush state: could not look up the listener")]) == 1


def test_a_menu_with_nothing_to_ask_writes_nothing(env):
    open_ring(env, "plain")
    assert env["events"] == [("show", False)] and not env["data"].exists()


# --- answers -----------------------------------------------------------------------------------------------------------
def test_the_answer_marks_the_open_ring(env, monkeypatch):
    r = open_ring(env)
    assert r._marks.get(()) is None                     # nothing known yet: neutral
    refreshed = []
    real = ring.Ring.refresh_marks
    monkeypatch.setattr(ring.Ring, "refresh_marks", lambda self: (refreshed.append(self), real(self)))
    assert ready(env, answer(env)) == 0
    assert refreshed == [r]
    marks = r._marks[()]
    assert marks[0] is not None and marks[1] is not None and marks[2] is not None and marks[3] is None
    assert r.sprites is not r._plain                    # the marked copies, never the kept list


def test_an_answer_with_no_ring_open_is_kept_and_drawn_in_the_next_rings_first_frame(env, monkeypatch):
    app = env["app"]
    open_ring(env)
    app.ring = None                                     # the ring closed before the answer came
    calls = []
    monkeypatch.setattr(ring.Ring, "refresh_marks", lambda self: calls.append(self))
    assert ready(env, answer(env)) == 0 and calls == []
    open_ring(env)
    assert env["first_marks"][-1] is not None          # from the cache, before the new question is written


def test_an_answer_the_channel_does_not_take_refreshes_nothing(env, monkeypatch):
    open_ring(env)
    calls = []
    monkeypatch.setattr(ring.Ring, "refresh_marks", lambda self: calls.append(self))
    ready(env, answer(env, pid=OTHER_PID))
    ready(env, 99)                                      # an id never asked
    assert calls == []


def test_the_first_frame_never_shows_the_state_of_another_zbrush(env):
    app = env["app"]
    open_ring(env)
    ready(env, answer(env))                             # the ZBrush in front answered
    app.ring = None
    env["front"] = OTHER_PID                            # a second ZBrush 2026 comes to the front
    listener_json(env["listener"], pid=OTHER_PID)
    r = open_ring(env)
    assert env["first_marks"][-1] is None and r._marks.get(()) is None
    assert app.state.pid == OTHER_PID


def test_a_ring_asks_through_the_refresh_when_the_cache_is_already_there(env, monkeypatch):
    """The first frame shows no marks when the last question went elsewhere (here: a ring over a ZBrush 2022); the
    refresh after the question shows what is still known about this ZBrush straight away."""
    app = env["app"]
    open_ring(env)
    ready(env, answer(env))
    app.ring = None
    env["front"] = OTHER_PID
    monkeypatch.setattr(app, "target_install", lambda: LEGACY)
    open_ring(env)
    app.ring = None
    assert app.state.pid == 0
    env["front"] = PID
    r = open_ring(env)
    assert env["first_marks"][-1] is None and r._marks.get(()) is not None


# --- picks -------------------------------------------------------------------------------------------------------------
@pytest.fixture
def picks(env, monkeypatch):
    """The app with a Spy channel and the hand-off faked: _write_request gives seq 7, the bridge key is pressed."""
    app = env["app"]
    app.state = spy = Spy()
    app.cfg.bridge_mode = "auto"
    env["request"] = request = env["data"].parent / "request.json"
    env["pressed"] = []

    def write_request(item, legacy=None):
        request.write_text("{}")
        return 7
    monkeypatch.setattr(app, "_write_request", write_request)
    monkeypatch.setattr(app, "target_install", lambda: None)
    monkeypatch.setattr(app, "press_bridge_key", lambda seq: (env["pressed"].append(seq), (True, None))[1])
    monkeypatch.setattr(app, "_watch_zscript_result", lambda seq, before: None)
    monkeypatch.setattr(app, "_watch_apply", lambda seq, legacy: None)
    env["item"] = radiald.C.Item(label="Sym", kind="toggle", data={"toggle": SYM})
    return spy


def test_a_pick_to_the_listener_is_recorded_once_even_when_the_bridge_key_takes_it_over(env, picks):
    app = env["app"]
    app.send(env["item"])
    assert env["pick_posts"] == [(LISTENER, radiald.WM_APP_PICK, 7)]
    assert picks.named("picked") == [("picked", (7, PID), {})]
    app._ack[1] = 0                                     # not picked up in time: the bridge key carries it
    app._check_ack()
    assert env["pressed"] == [7]
    assert picks.named("picked") == [("picked", (7, PID), {})] and picks.named("dropped") == []


def test_a_fallback_that_fails_drops_the_pick(env, picks, monkeypatch):
    app = env["app"]
    app.send(env["item"])
    monkeypatch.setattr(app, "press_bridge_key", lambda seq: (False, "ZBrush is not in front"))
    app._ack[1] = 0
    app._check_ack()
    assert picks.named("picked") == [("picked", (7, PID), {})] and picks.named("dropped") == [("dropped", (7,), {})]
    assert not env["request"].exists()


@pytest.mark.parametrize("route", ["no listener", "key mode"])
def test_a_pick_by_the_bridge_key_is_recorded_for_the_zbrush_in_front(env, picks, route):
    app = env["app"]
    if route == "no listener":
        env["listener"].unlink()
    else:
        app.cfg.bridge_mode = "key"
    app.send(env["item"])
    assert env["pressed"] == [7] and env["pick_posts"] == []
    assert picks.named("picked") == [("picked", (7, PID), {})]


def test_a_pick_by_the_zscript_bridge_is_recorded_for_the_zbrush_in_front(env, picks, monkeypatch):
    app = env["app"]
    env["front"] = OTHER_PID
    monkeypatch.setattr(app, "target_install", lambda: LEGACY)
    app.send(env["item"])
    assert env["pressed"] == [7]
    assert picks.named("picked") == [("picked", (7, OTHER_PID), {})]


def test_a_command_pick_is_recorded_for_the_zbrush_it_was_for(env, picks):
    app = env["app"]
    env["front"] = OTHER_PID                            # not the one in front: the command named its ZBrush
    app.send(env["item"], source="command", pid=PID)
    assert picks.named("picked") == [("picked", (7, PID), {})]


@pytest.mark.parametrize("route", ["key not sent", "message mode, no listener", "zscript key not sent"])
def test_a_pick_that_was_never_handed_off_is_dropped_not_recorded(env, picks, monkeypatch, route):
    app = env["app"]
    if route == "message mode, no listener":
        app.cfg.bridge_mode = "message"
        env["listener"].unlink()
    else:
        env["listener"].unlink()
        monkeypatch.setattr(app, "press_bridge_key", lambda seq: (False, "ZBrush is not in front"))
        if route == "zscript key not sent":
            monkeypatch.setattr(app, "target_install", lambda: LEGACY)
    app.send(env["item"])
    assert picks.named("picked") == [] and picks.named("dropped") == [("dropped", (7,), {})]


def test_every_drop_that_removes_the_request_takes_the_pick_back(env, picks):
    app = env["app"]
    env["request"].write_text("{}")
    app._drop_request(12)
    env["request"].write_text("{}")
    app._give_up_apply(13, "ZBrush did not take the pick", toast=False)
    assert picks.named("dropped") == [("dropped", (12,), {}), ("dropped", (13,), {})]


def test_a_request_already_taken_is_not_taken_back(env, picks):
    """The listener took request.json between _check_ack's look and the drop: ZBrush applies the pick."""
    env["request"].unlink(missing_ok=True)
    env["app"]._drop_request(12)
    assert picks.named("dropped") == []


def test_a_request_that_cannot_be_removed_is_not_taken_back(env, picks, monkeypatch):
    env["request"].write_text("{}")
    real = os.remove

    def remove(p):
        if os.path.abspath(p) == os.path.abspath(str(env["request"])):
            raise PermissionError("the plugin has it open")
        real(p)
    monkeypatch.setattr(radiald.os, "remove", remove)
    env["app"]._drop_request(12)
    assert picks.named("dropped") == [] and env["request"].exists()
    assert [ln for ln in env["lines"] if "could not remove request.json" in ln]


def test_a_browser_pick_to_the_listener_is_recorded_for_the_zbrush_the_browser_was_opened_from(env, picks,
                                                                                               monkeypatch):
    app = env["app"]
    env["front"] = OTHER_PID                            # the focus has not come back to ZBrush yet
    monkeypatch.setattr(app, "_browser_zb_pid", lambda: PID)
    app.send(radiald.C.Item(label="Clay", kind="brush", data={"brush": "Clay"}), source="browser")
    assert env["pick_posts"] == [(LISTENER, radiald.WM_APP_PICK, 7)]
    assert picks.named("picked") == [("picked", (7, PID), {})]


# --- stopping ----------------------------------------------------------------------------------------------------------
def test_the_channel_is_made_with_the_control_window_and_stopped_when_the_app_quits(env, monkeypatch, tmp_path):
    app = radiald.App(str(env["app"].cfg_path))
    made = []

    class Channel(Spy):
        def __init__(self, post, ctrl, data_dir, log=None):
            super().__init__()
            made.append((post, ctrl, data_dir, log, self))
    monkeypatch.setattr(radiald.zstate, "Channel", Channel)
    monkeypatch.setattr(radiald, "DATA_DIR", str(tmp_path / "Local"))
    monkeypatch.setattr(W, "process_created", lambda pid: 0)
    monkeypatch.setattr(W, "make_dpi_aware", lambda: None)
    monkeypatch.setattr(W, "launch_chain", lambda: "test")
    monkeypatch.setattr(app, "_create_ctrl", lambda: setattr(app, "ctrl", CTRL))
    monkeypatch.setattr(app, "start_hook", lambda: None)
    monkeypatch.setattr(app, "stop_hook", lambda: None)
    monkeypatch.setattr(app, "_create_tray", lambda: None)
    monkeypatch.setattr(W, "GetMessageW", lambda *a: 0)          # the quit message is the first one
    monkeypatch.setattr(W, "find_message_window", lambda cls: 0)
    monkeypatch.setattr(W, "CloseHandle", lambda h: None)
    assert app._serve(mutex=1, hold=None) == 0
    assert len(made) == 1
    post, ctrl, data_dir, log, ch = made[0]
    assert post is W.PostMessageW and ctrl == CTRL and data_dir == str(tmp_path / "Local") and log is radiald.log
    assert app.state is ch and ch.calls == [("stop", (), {})]


def test_stop_removes_the_question_the_app_wrote(env):
    open_ring(env)
    env["app"]._state_call("stop")
    assert not (env["data"] / zstate.QUERY_FILE).exists()


# --- a channel that fails ----------------------------------------------------------------------------------------------
def test_a_channel_that_raises_in_ask_leaves_the_ring_open_with_one_log_line(env):
    app = env["app"]
    app.state = Spy(raises={"ask"})
    r = open_ring(env)
    assert app.ring is r and env["events"] == [("show", False)]
    app.ring = None
    open_ring(env)
    failed = [ln for ln in env["lines"] if ln.startswith("ZBrush state: ask failed")]
    assert len(failed) == 1


def test_a_channel_that_raises_in_marks_gives_a_ring_without_marks(env):
    app = env["app"]
    app.state = Spy(raises={"marks"})
    app.state.pid = PID
    r = open_ring(env)
    assert app.ring is r and r._marks.get(()) is None and env["first_marks"] == [None]
    assert len([ln for ln in env["lines"] if "marks failed" in ln]) == 1
    assert not [ln for ln in env["lines"] if "marks for" in ln and "ignored" in ln]    # the ring's own line: not needed


def test_marks_from_the_channel_reach_the_ring(env):
    app = env["app"]
    app.state = Spy()
    app.state.pid = PID
    r = open_ring(env)
    assert env["first_marks"][0] is not None and r._marks[()][0] is not None


def test_a_channel_that_raises_in_on_ready_refreshes_nothing_and_says_so_once(env, monkeypatch):
    app = env["app"]
    open_ring(env)
    app.state = Spy(raises={"on_ready"})
    calls = []
    monkeypatch.setattr(ring.Ring, "refresh_marks", lambda self: calls.append(self))
    assert ready(env, 1) == 0 and ready(env, 2) == 0
    assert calls == []
    assert len([ln for ln in env["lines"] if "on_ready failed" in ln]) == 1
    assert not [ln for ln in env["lines"] if ln.startswith("control error")]


def test_a_channel_that_raises_in_picked_or_dropped_leaves_the_pick_as_it_was(env, picks):
    app = env["app"]
    picks.raises = {"picked", "dropped"}
    app.send(env["item"])
    assert env["pick_posts"] == [(LISTENER, radiald.WM_APP_PICK, 7)] and app._ack[0] == 7
    app._drop_request(7)
    assert not env["request"].exists()
    assert len([ln for ln in env["lines"] if "picked failed" in ln]) == 1
    assert len([ln for ln in env["lines"] if "dropped failed" in ln]) == 1
