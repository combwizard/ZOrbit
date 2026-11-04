"""Commands from other programs: the arguments, the exit codes, and what the running app does with a command."""
import ctypes
import json

import pytest

import commands
import config
import paths
import profiles
import radiald
import win32 as W

LISTENER_HWND, LISTENER_PID, OTHER_PID = 500, 63380, 70000


# --- the arguments --------------------------------------------------------------------------------
@pytest.mark.parametrize("args, want", [
    (["--open", "brushes"], {"op": "open", "menu": "brushes"}),
    (["--pick", "brush:ClayBuildup"], {"op": "pick", "kind": "brush", "name": "ClayBuildup"}),
    (["--pick", "alpha:Alpha 58"], {"op": "pick", "kind": "alpha", "name": "Alpha 58"}),
    (["--press", "Tool:Masking:Clear"], {"op": "press", "path": "Tool:Masking:Clear"}),
    (["--toggle", "Transform:Activate Symmetry"], {"op": "toggle", "path": "Transform:Activate Symmetry"}),
    (["--set", "Draw:Draw Size", "64"], {"op": "set", "path": "Draw:Draw Size", "value": 64}),
    (["--set", "Draw:Z Intensity", "12.5"], {"op": "set", "path": "Draw:Z Intensity", "value": 12.5}),
    (["--set", "Draw:Offset", "-3"], {"op": "set", "path": "Draw:Offset", "value": -3}),
    (["--browser"], {"op": "browser", "kind": None, "tag": None}),
    (["--browser", "--kind", "alpha"], {"op": "browser", "kind": "alpha", "tag": None}),
    (["--browser", "--tag", "fav", "--kind", "brush"], {"op": "browser", "kind": "brush", "tag": "fav"}),
    (["--profile", "next"], {"op": "profile", "name": "next"}),
    (["--profile", "Hard surface"], {"op": "profile", "name": "Hard surface"}),
])
def test_the_arguments_become_a_command(args, want):
    assert commands.parse(args) == {"v": 1, **want}


@pytest.mark.parametrize("args", [
    [], ["--nothing"], ["--open"], ["--open", "a", "b"], ["--open", ""], ["--pick", "ClayBuildup"], ["--pick", "tool:x"],
    ["--pick", "brush:"], ["--pick", r"brush:..\..\secret"], ["--pick", "brush:a/b"], ["--pick", "brush:a:b"],
    ["--pick", "brush:a\nb"], ["--press"], ["--press", ""], ["--press", "a\nb"], ["--press", "x" * 201], ["--set", "A:B"],
    ["--set", "A:B", "lots"], ["--set", "A:B", "nan"], ["--set", "A:B", "inf"], ["--set", "A:B", "1e20"], ["--toggle"], ["--browser", "--kind"],
    ["--browser", "--kind", "tool"], ["--browser", "extra"], ["--profile"], ["--profile", ""],
])
def test_arguments_that_make_no_sense_are_refused(args):
    with pytest.raises(commands.CommandError):
        commands.parse(args)


@pytest.mark.parametrize("msg", [
    None, [], "open", {}, {"op": "open", "menu": "a"}, {"v": 2, "op": "open", "menu": "a"}, {"v": 1, "op": "format c:"},
    {"v": 1, "op": "open", "menu": 3}, {"v": 1, "op": "pick", "kind": "brush", "name": None},
    {"v": 1, "op": "set", "path": "A:B"}, {"v": 1, "op": "set", "path": "A:B", "value": True},
    {"v": 1, "op": "set", "path": "A:B", "value": "1"}, {"v": 1, "op": "set", "path": "A:B", "value": float("inf")},
    {"v": 1, "op": "set", "path": "A:B", "value": 1 << 400}, {"v": 1, "op": "set", "path": "A:B", "value": 1e20},
    {"v": 1, "op": "browser", "tag": 3}, {"v": 1, "op": "browser", "kind": "tool"}, {"v": 1, "op": "profile", "name": ["a"]},
])
def test_what_another_program_sends_is_checked_as_strictly(msg):
    assert commands.check(msg)


def test_the_kinds_are_the_app_s_kinds():
    assert commands.ASSET_KINDS == config.ASSET_KINDS


def test_it_does_not_load_the_app():
    src = open(commands.__file__, encoding="utf-8").read()
    assert "import radiald" not in src and "import config" not in src and "import studio" not in src


# --- the exit codes -------------------------------------------------------------------------------
def test_no_app_running_is_exit_code_2(monkeypatch):
    monkeypatch.setattr(W, "find_message_window", lambda cls: 0)
    assert commands.main(["--open", "brushes"]) == 2


def test_an_app_that_does_not_answer_is_exit_code_2(monkeypatch):
    monkeypatch.setattr(W, "find_message_window", lambda cls: 9)
    monkeypatch.setattr(W, "send_copydata", lambda *a, **k: None)
    assert commands.main(["--open", "brushes"]) == 2


@pytest.mark.parametrize("answer, code", [(1, 0), (0, 1)])
def test_the_app_s_answer_is_the_exit_code(monkeypatch, answer, code):
    sent = []
    monkeypatch.setattr(W, "find_message_window", lambda cls: sent.append(cls) or 9)
    monkeypatch.setattr(W, "send_copydata", lambda h, dw, data, timeout_ms: sent.append((h, dw, json.loads(data))) or answer)
    assert commands.main(["--pick", "brush:Clay"]) == code
    assert sent == ["ZOrbitControl", (9, 2, {"v": 1, "op": "pick", "kind": "brush", "name": "Clay"})]


def test_bad_arguments_are_exit_code_1_and_reach_nobody(monkeypatch):
    monkeypatch.setattr(W, "find_message_window", lambda cls: pytest.fail("looked for the app"))
    assert commands.main(["--pick", "nonsense"]) == 1


def test_it_says_nothing_when_there_is_nowhere_to_say_it(monkeypatch):
    monkeypatch.setattr("sys.stderr", None)
    monkeypatch.setattr(W, "find_message_window", lambda cls: 0)
    assert commands.main(["--open", "brushes"]) == 2


# --- the running app ------------------------------------------------------------------------------
@pytest.fixture
def app(monkeypatch, tmp_path):
    a = radiald.App(paths.DEFAULT_MENUS)
    a.cfg = config.load(paths.DEFAULT_MENUS)
    a.cfg.bridge_mode = "auto"
    a.ctrl = 1
    a.posted, a.pressed, a.routes, a.toasts, a.opened, a.browsed, a.picks, a.self_posts = [], [], [], [], [], [], [], []
    listener = tmp_path / "listener.json"
    listener.write_text(json.dumps({"hwnd": LISTENER_HWND, "pid": LISTENER_PID, "verified": True}))
    monkeypatch.setattr(radiald, "LISTENER_FILE", str(listener))
    monkeypatch.setattr(radiald, "REQUEST_FILE", str(tmp_path / "request.json"))
    monkeypatch.setattr(W, "IsWindow", lambda hwnd: True)
    monkeypatch.setattr(W, "SetTimer", lambda *a_: 1)
    monkeypatch.setattr(W, "KillTimer", lambda *a_: 0)
    monkeypatch.setattr(W, "nudge_mouse", lambda: None)
    monkeypatch.setattr(W, "cursor_pos", lambda: (10, 20))

    def post(hwnd, msg, wparam, lparam):
        if msg == radiald.WM_APP_PICK:
            a.posted.append((int(hwnd.value), wparam))
        else:
            a.self_posts.append(msg)
        return 1
    monkeypatch.setattr(W, "PostMessageW", post)
    monkeypatch.setattr(a, "_exe_of", lambda pid, cache=None: a.target_exe)
    monkeypatch.setattr(a, "_write_request", lambda item, legacy: (a.picks.append(item), 7)[1])
    monkeypatch.setattr(a, "_drop_request", lambda seq: None)
    monkeypatch.setattr(a, "target_install", lambda: None)
    monkeypatch.setattr(a, "press_bridge_key", lambda seq: (a.pressed.append(seq), (True, ""))[1])
    monkeypatch.setattr(a.activity, "note_pick", lambda seq, item, route, sent, source, *r, **k: a.routes.append((route, source)))
    monkeypatch.setattr(a, "_toast", a.toasts.append)
    monkeypatch.setattr(a, "_record_pick", lambda item: None)
    monkeypatch.setattr(a, "load_config", lambda *a_, **k: None)
    monkeypatch.setattr(a, "_check_profile", lambda *a_, **k: None)
    monkeypatch.setattr(a, "open_menu", lambda menu, pos, held, nested=False: a.opened.append((menu.id, pos, held)))
    monkeypatch.setattr(a, "open_browser", lambda tag=None, toggle=False, kind=None: a.browsed.append((tag, kind, toggle)))
    in_front(a, monkeypatch, True)
    monkeypatch.setattr(W, "pids_named", lambda name: [LISTENER_PID])
    return a


def in_front(a, monkeypatch, front, pid=LISTENER_PID):
    monkeypatch.setattr(W, "GetForegroundWindow", lambda: 77)
    monkeypatch.setattr(W, "window_pid", lambda hwnd: pid)
    monkeypatch.setattr(a, "target_in_front", lambda on_hook=False: front)
    monkeypatch.setattr(a, "_is_text_target", lambda fg: False)


def command(a, *args) -> int:
    """Takes a command as the app would, runs what it queued, and gives back the answer the sender sees."""
    answer = a._take_command(commands.parse(list(args)))
    for _ in list(a.self_posts):
        a._run_command()
    a.self_posts.clear()
    return answer


def test_a_message_comes_in_through_copydata(app, monkeypatch):
    raw = json.dumps({"v": 1, "op": "press", "path": "Tool:Masking:Clear"}).encode()
    buf = ctypes.create_string_buffer(raw, len(raw))
    cds = W.COPYDATASTRUCT(commands.COPYDATA, len(raw), ctypes.cast(buf, ctypes.c_void_p))
    assert app._on_copydata(0, ctypes.addressof(cds)) == 1
    assert app.self_posts == [radiald.WM_APP_COMMAND]


@pytest.mark.parametrize("raw", [b"not json", b"[]", b'{"v": 1, "op": "nope"}', b'{"op": "open", "menu": "a"}'])
def test_a_bad_message_is_refused_and_nothing_runs(app, raw):
    buf = ctypes.create_string_buffer(raw, len(raw))
    cds = W.COPYDATASTRUCT(commands.COPYDATA, len(raw), ctypes.cast(buf, ctypes.c_void_p))
    assert app._on_copydata(0, ctypes.addressof(cds)) == 0
    assert app.picks == [] and app.opened == []


def test_a_browser_pick_still_comes_in_as_before(app):
    raw = json.dumps({"v": 1, "op": "pick", "kind": "brush", "name": "Clay"}).encode()
    buf = ctypes.create_string_buffer(raw, len(raw))
    cds = W.COPYDATASTRUCT(radiald.COPYDATA_PICK, len(raw), ctypes.cast(buf, ctypes.c_void_p))
    assert app._on_copydata(0, ctypes.addressof(cds)) == 1
    assert app._browser_pick.data == {"brush": "Clay"} and app.self_posts == [radiald.WM_APP_BROWSER_PICK]


@pytest.mark.parametrize("args, kind, data", [
    (["--pick", "brush:Clay"], "brush", {"brush": "Clay"}),
    (["--pick", "texture:Rock"], "texture", {"texture": "Rock"}),
    (["--press", "Tool:Masking:Clear"], "press", {"press": "Tool:Masking:Clear"}),
    (["--toggle", "Transform:Activate Symmetry"], "toggle", {"toggle": "Transform:Activate Symmetry"}),
    (["--set", "Draw:Draw Size", "64"], "set", {"set": "Draw:Draw Size", "value": 64}),
])
def test_a_pick_does_what_a_slot_does(app, args, kind, data):
    assert command(app, *args) == 1
    assert app.picks[0].kind == kind and app.picks[0].data == data
    assert app.posted == [(LISTENER_HWND, 7)] and app.routes == [("listener", "command")]


def test_an_asset_pick_counts_in_recent_under_the_name_of_its_file(app, monkeypatch):
    recorded = []
    monkeypatch.setattr(app, "_record_pick", recorded.append)
    monkeypatch.setattr(radiald.assets, "find", lambda kind, name: f"D:/ZBrush/{name.upper()}.zbp")
    command(app, "--pick", "brush:clay")
    assert [i.data for i in recorded] == [{"brush": "CLAY"}]


def test_a_mistyped_name_is_still_tried_but_does_not_count(app, monkeypatch):
    recorded = []
    monkeypatch.setattr(app, "_record_pick", recorded.append)
    monkeypatch.setattr(radiald.assets, "find", lambda kind, name: None)
    assert command(app, "--pick", "brush:Clya") == 1
    assert recorded == [] and app.picks[0].data == {"brush": "Clya"}


def test_a_button_is_not_looked_up_as_an_asset(app, monkeypatch):
    recorded = []
    monkeypatch.setattr(app, "_record_pick", recorded.append)
    monkeypatch.setattr(radiald.assets, "find", lambda kind, name: pytest.fail("looked up a button"))
    command(app, "--press", "Tool:Masking:Clear")
    assert [i.kind for i in recorded] == ["press"]


# --- several picks close together -----------------------------------------------------------------
def test_a_pick_waits_for_the_last_one_to_be_taken(app, monkeypatch, tmp_path):
    request = tmp_path / "request.json"
    request.write_text("{}")
    timers = []
    monkeypatch.setattr(W, "SetTimer", lambda hwnd, tid, ms, cb: timers.append(tid))
    assert command(app, "--pick", "brush:Second") == 1
    assert app.picks == [] and timers == [radiald.TIMER_COMMAND] and len(app._commands) == 1
    request.unlink()
    app._run_command()
    assert [i.data for i in app.picks] == [{"brush": "Second"}] and not app._commands


def test_a_waiting_pick_goes_anyway_after_the_wait(app, monkeypatch, tmp_path):
    (tmp_path / "request.json").write_text("{}")
    assert command(app, "--pick", "brush:Second") == 1
    assert app.picks == []
    app._command_wait = 0.0
    app._run_command()
    assert len(app.picks) == 1 and app._command_wait is None


def test_commands_keep_their_order_behind_a_waiting_pick(app, monkeypatch, tmp_path):
    request = tmp_path / "request.json"
    request.write_text("{}")
    app._take_command(commands.parse(["--pick", "brush:Second"]))
    app._take_command(commands.parse(["--browser"]))
    app._run_command()
    assert app.picks == [] and app.browsed == []
    request.unlink()
    app._run_command()
    assert len(app.picks) == 1 and len(app.browsed) == 1


def test_something_other_than_a_pick_does_not_wait(app, monkeypatch, tmp_path):
    (tmp_path / "request.json").write_text("{}")
    assert command(app, "--browser") == 1 and len(app.browsed) == 1


def test_a_pick_closes_an_open_ring_first(app, monkeypatch):
    closed = []
    app.ring = type("R", (), {"cancel": lambda self, why: closed.append(why)})()
    command(app, "--pick", "brush:Clay")
    assert closed == ["command"] and len(app.picks) == 1


def test_no_zbrush_in_front_still_reaches_the_only_listener(app, monkeypatch):
    in_front(app, monkeypatch, False, pid=OTHER_PID)
    assert command(app, "--pick", "brush:Clay") == 1
    assert app.posted == [(LISTENER_HWND, 7)] and app.toasts == []


@pytest.mark.parametrize("why", ["no listener for it", "two running", "key mode", "message mode, two running"])
def test_no_zbrush_in_front_and_no_listener_to_use_is_refused(app, monkeypatch, why):
    in_front(app, monkeypatch, False, pid=OTHER_PID)
    if why == "no listener for it":
        monkeypatch.setattr(W, "pids_named", lambda name: [OTHER_PID])
    elif why == "key mode":
        app.cfg.bridge_mode = "key"
    else:
        monkeypatch.setattr(W, "pids_named", lambda name: [LISTENER_PID, OTHER_PID])
        app.cfg.bridge_mode = "message" if why.startswith("message") else "auto"
    assert command(app, "--press", "Tool:Masking:Clear") == 0
    assert app.picks == [] and app.toasts == [radiald.MSG_NOT_FRONT]


def test_in_front_without_a_listener_uses_the_same_route_as_a_ring_pick(app, monkeypatch):
    in_front(app, monkeypatch, True, pid=OTHER_PID)            # ZBrush 2022 to 2025, or a plugin not loaded
    assert command(app, "--pick", "brush:Clay") == 1
    assert app.posted == [] and app.pressed == [7] and app.routes == [("key", "command")]


def test_a_dialog_or_text_box_in_front_refuses_like_a_hotkey(app, monkeypatch):
    monkeypatch.setattr(app, "_is_text_target", lambda fg: True)
    assert command(app, "--pick", "brush:Clay") == 0
    assert app.picks == [] and app.toasts == [radiald.MSG_COMMAND_TEXT]
    app.toasts.clear()
    assert command(app, "--open", next(iter(app.cfg.menus))) == 0
    assert app.opened == [] and app.toasts == [radiald.MSG_COMMAND_TEXT]


def test_open_opens_the_menu_as_a_tap_at_the_cursor(app):
    menu = next(iter(app.cfg.menus))
    assert command(app, "--open", menu) == 1
    assert app.opened == [(menu, (10, 20), False)]


def test_a_menu_with_no_hotkey_can_be_opened(app):
    app.slots = []
    menu = next(iter(app.cfg.menus))
    assert command(app, "--open", menu) == 1 and len(app.opened) == 1


def test_open_refuses_an_unknown_menu_and_says_which(app):
    assert command(app, "--open", "nope") == 0
    assert app.opened == [] and app.toasts == ["There is no menu called nope"]


def test_open_needs_zbrush_in_front_even_with_a_listener(app, monkeypatch):
    in_front(app, monkeypatch, False, pid=OTHER_PID)
    assert command(app, "--open", next(iter(app.cfg.menus))) == 0
    assert app.opened == [] and app.toasts == [radiald.MSG_NOT_FRONT]


def test_open_again_closes_the_ring_like_the_hotkey(app):
    menu = next(iter(app.cfg.menus))
    closed = []
    app.ring = type("R", (), {"cancel": lambda self, why: closed.append(why),
                              "menu": type("M", (), {"id": menu})()})()
    assert command(app, "--open", menu) == 1
    assert closed == ["command"] and app.opened == []


def test_a_menu_removed_after_the_check_says_so(app):
    menu = next(iter(app.cfg.menus))
    assert app._take_command(commands.parse(["--open", menu])) == 1
    del app.cfg.menus[menu]
    app._run_command()
    assert app.opened == [] and app.toasts == [f"There is no menu called {menu}"]


def test_browser_opens_on_a_tab_and_a_tag(app, monkeypatch):
    monkeypatch.setattr(app.tags, "has", lambda key: key == "fav")
    assert command(app, "--browser", "--kind", "alpha", "--tag", "fav") == 1
    assert command(app, "--browser") == 1
    assert app.browsed == [("fav", "alpha", False), (None, None, False)]


def test_browser_works_with_zbrush_behind(app, monkeypatch):
    in_front(app, monkeypatch, False, pid=OTHER_PID)
    assert command(app, "--browser") == 1 and len(app.browsed) == 1


def test_browser_refuses_an_unknown_tag(app, monkeypatch):
    monkeypatch.setattr(app.tags, "has", lambda key: False)
    assert command(app, "--browser", "--tag", "nope") == 0
    assert app.browsed == [] and app.toasts == ["There is no tag called nope"]


# --- profiles -------------------------------------------------------------------------------------
@pytest.fixture
def three(app, monkeypatch):
    names = ["Alpha", "Beta", "Gamma"]
    made = []
    monkeypatch.setattr(profiles, "names", lambda: list(names))
    monkeypatch.setattr(profiles, "canonical", lambda n: next((x for x in names if x.lower() == n.lower()), None))
    monkeypatch.setattr(profiles, "set_active", made.append)
    app._pinned = False
    app.profile = "Beta"
    app.made = made
    return app


def test_profile_switches_by_name_whatever_the_case(three):
    assert command(three, "--profile", "gamma") == 1
    assert three.made == ["Gamma"] and three.toasts == ["Profile: Gamma"]


@pytest.mark.parametrize("now, then", [("Alpha", "Beta"), ("Beta", "Gamma"), ("Gamma", "Alpha"), ("Gone", "Alpha")])
def test_profile_next_steps_round(three, now, then):
    three.profile = now
    assert command(three, "--profile", "next") == 1
    assert three.made == [then]


def test_profile_next_with_one_profile_stays(three, monkeypatch):
    monkeypatch.setattr(profiles, "names", lambda: ["Beta"])
    assert command(three, "--profile", "next") == 1 and three.made == ["Beta"]


def test_profile_refuses_an_unknown_name(three):
    assert command(three, "--profile", "Nope") == 0
    assert three.made == [] and three.toasts == ["There is no profile called Nope"]


def test_profile_refuses_a_pinned_menus_file_and_newer_files(three):
    three._pinned = True
    assert command(three, "--profile", "next") == 0
    three._pinned, three._frozen = False, True
    assert command(three, "--profile", "next") == 0
    assert three.made == [] and len(three.toasts) == 2


def test_a_profile_that_cannot_be_set_says_so(three, monkeypatch):
    def refuse(name):
        raise profiles.ProfileError("Those files are locked.")
    monkeypatch.setattr(profiles, "set_active", refuse)
    assert command(three, "--profile", "Gamma") == 1
    assert three.toasts == ["Those files are locked."]


def test_a_profile_switch_closes_the_ring_so_it_can_happen(three):
    closed = []
    three.ring = type("R", (), {"cancel": lambda self, why: closed.append(why)})()
    command(three, "--profile", "Gamma")
    assert closed == ["command"]


def arrive_in(a, monkeypatch, keyed):
    """Stands in for _check_profile: the app has followed the pointer to the profile just set, with or without the key."""
    def follow(*_a, **_k):
        a.profile = a.made[-1]
        a.cfg.profile_key = config.Hotkey(0x50, alt=True, text="Alt+P") if keyed else None
    monkeypatch.setattr(a, "_check_profile", follow)


def test_the_profile_hotkey_says_when_the_new_profile_has_no_key(three, monkeypatch):
    arrive_in(three, monkeypatch, keyed=False)
    hotkey_message(three)
    assert three.made == ["Gamma"] and three.toasts == ["Profile: Gamma (no next-profile hotkey here)"]


def test_the_profile_hotkey_says_only_the_name_when_the_new_profile_has_a_key(three, monkeypatch):
    arrive_in(three, monkeypatch, keyed=True)
    hotkey_message(three)
    assert three.toasts == ["Profile: Gamma"]


def test_the_profile_command_does_not_say_no_hotkey(three, monkeypatch):
    arrive_in(three, monkeypatch, keyed=False)
    assert command(three, "--profile", "Gamma") == 1
    assert three.toasts == ["Profile: Gamma"]


def hotkey_message(a):
    """What the control window does when the hook posts the next-profile hotkey."""
    return a._ctrl_proc(1, radiald.WM_APP_PROFILE, 0, 0)


def test_the_profile_hotkey_does_what_profile_next_does(three):
    hotkey_message(three)
    assert three.made == ["Gamma"] and three.toasts == ["Profile: Gamma"]
    three.profile = "Gamma"
    hotkey_message(three)
    assert three.made == ["Gamma", "Alpha"]               # round the end of the list


def test_the_profile_hotkey_shares_the_code_of_the_command(three, monkeypatch):
    named = []
    monkeypatch.setattr(three, "_command_profile", lambda name, from_hotkey=False: named.append((name, from_hotkey)))
    hotkey_message(three)
    assert named == [("next", True)]


def test_the_profile_hotkey_closes_an_open_ring(three):
    closed = []
    three.ring = type("R", (), {"cancel": lambda self, why: closed.append(why)})()
    hotkey_message(three)
    assert closed == ["command"] and three.made == ["Gamma"]


def test_the_profile_hotkey_says_why_not_on_a_pinned_menus_file_or_newer_files(three):
    three._pinned = True
    hotkey_message(three)
    three._pinned, three._frozen = False, True
    hotkey_message(three)
    assert three.made == [] and three.toasts == [radiald.MSG_COMMAND_PINNED, radiald.MSG_COMMAND_FROZEN]


def test_a_refused_profile_hotkey_does_not_touch_the_ring(three):
    closed = []
    three.ring = type("R", (), {"cancel": lambda self, why: closed.append(why)})()
    three._pinned = True
    hotkey_message(three)
    assert closed == [] and three.made == []


def test_each_command_gets_a_line_in_the_log(app, monkeypatch):
    lines = []
    monkeypatch.setattr(radiald, "log", lines.append)
    command(app, "--pick", "brush:Clay")
    command(app, "--open", "nope")
    assert any(l.startswith("command: ") and "Clay" in l for l in lines)
    assert any(l.startswith("command refused: ") and "nope" in l for l in lines)


def test_a_command_that_fails_does_not_strand_the_ones_behind_it(app, monkeypatch):
    lines = []
    monkeypatch.setattr(radiald, "log", lines.append)
    monkeypatch.setattr(app, "open_browser", lambda *a_, **k: 1 / 0)
    app._take_command(commands.parse(["--browser"]))
    app._take_command(commands.parse(["--pick", "brush:Clay"]))
    app._run_command()
    assert not app._commands and len(app.picks) == 1
    assert any(l.startswith("command failed:") and "ZeroDivisionError" in l for l in lines)
