"""The ZBrush 2026+ plugin (bridge/zorbit_bridge.py), run against a stub of zbrush.commands.

The plugin needs ZBrush's embedded Python only for the `zbrush.commands` import, so a stub that records its calls
stands in for it. Its Win32 calls are replaced where a test would otherwise touch the real window system.
"""
import importlib.util
import json
import os
import sys
import time
import types
from pathlib import Path

import pytest

BRIDGE = Path(__file__).resolve().parent.parent / "bridge" / "zorbit_bridge.py"
APP_HWND = 5678                   # the app's control window in the state channel tests


class Stub(types.ModuleType):
    """zbrush.commands: records every call; `items` is the set of interface paths that exist."""

    def __init__(self):
        super().__init__("zbrush.commands")
        self.items = set()
        self.calls = []
        self.values = {}
        self.fail_buttons = set()
        self.on_press = {}
        self.disabled = set()     # paths that exist but are greyed
        self.ranges = {}          # path -> (min, max)
        self.titles = {}          # path -> get_title
        self.raising = set()      # paths whose reads (not exists) raise, as ZBrush's API does for a bad path
        self.session = 429428.0

    def _rec(self, *call):
        self.calls.append(call)

    def _read(self, path):
        if path in self.raising:
            raise SystemError(f"returned a result with an exception set ({path})")

    def exists(self, path):
        return path in self.items

    def is_enabled(self, path):
        self._read(path)
        return path not in self.disabled

    def get_min(self, path):
        self._read(path)
        return self.ranges.get(path, (0.0, 1.0))[0]

    def get_max(self, path):
        self._read(path)
        return self.ranges.get(path, (0.0, 1.0))[1]

    def get_title(self, path):
        self._read(path)
        return self.titles[path]

    def zbrush_info(self, info):
        return self.session if info == 7 else 0.0

    def press(self, path):
        self._rec("press", path)
        if path in self.on_press:
            self.on_press[path]()

    def set(self, path, value):
        self._rec("set", path, value)

    def toggle(self, path):
        self._rec("toggle", path)

    def get(self, path):
        self._read(path)
        return self.values.get(path, 1)

    def set_next_filename(self, name):
        self._rec("set_next_filename", name)

    def add_subpalette(self, path, pos):
        self._rec("add_subpalette", path)
        self.items.add(path)

    def add_button(self, path, info, fn):
        self._rec("add_button", path)
        if path in self.fail_buttons:
            raise RuntimeError(f"cannot add {path}")
        self.items.add(path)

    def delete_interface_item(self, path):
        self._rec("delete_interface_item", path)
        self.items.discard(path)

    def message_ok(self, text, title=""):
        self._rec("message_ok", text)

    def presses(self):
        return [c[1] for c in self.calls if c[0] == "press"]


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    stub = Stub()
    pkg = types.ModuleType("zbrush")
    pkg.commands = stub
    monkeypatch.setitem(sys.modules, "zbrush", pkg)
    monkeypatch.setitem(sys.modules, "zbrush.commands", stub)
    monkeypatch.setenv("RADIAL_BRIDGE_NO_INSTALL", "1")
    # A fresh S, as in a ZBrush that has not loaded the plugin yet: the module's own defaults fill it.
    monkeypatch.setitem(sys.modules, "_zorbit_bridge_state", types.ModuleType("_zorbit_bridge_state"))
    spec = importlib.util.spec_from_file_location("zorbit_bridge_under_test", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(mod, "DATA_DIR", str(data))
    monkeypatch.setattr(mod, "REQUEST_FILE", str(data / "request.json"))
    monkeypatch.setattr(mod, "REQUEST_TXT", str(data / "request.txt"))
    monkeypatch.setattr(mod, "LISTENER_FILE", str(data / "listener.json"))
    monkeypatch.setattr(mod, "LOG_FILE", str(data / "bridge.log"))
    monkeypatch.setattr(mod, "STATE_QUERY_FILE", str(data / "zstate_query.json"))
    monkeypatch.setattr(mod, "STATE_FILE", str(data / "zstate.json"))
    monkeypatch.setattr(mod, "primary_down", lambda: False)
    mod.stub = stub
    mod.timers = []
    monkeypatch.setattr(mod, "SetTimer", lambda hwnd, tid, ms, cb: mod.timers.append(("set", tid)))
    monkeypatch.setattr(mod, "KillTimer", lambda hwnd, tid: mod.timers.append(("kill", tid)))
    # The state channel's window calls: APP_HWND is the app's control window, every other window is foreign.
    mod.posted = []
    monkeypatch.setattr(mod, "_class_name", lambda h: "ZOrbitControl" if h == APP_HWND else "Notepad")
    monkeypatch.setattr(mod, "PostMessageW", lambda h, msg, wp, lp: mod.posted.append((h, msg, wp, lp)) or 1)
    return mod


def listening(bridge, monkeypatch):
    """Gives the plugin a live listener window, so a pick may leave items to select afterwards."""
    bridge.S.hwnd = 1234
    monkeypatch.setattr(bridge, "IsWindow", lambda h: True)


def send(bridge, actions, age=0.0, label="test"):
    with open(bridge.REQUEST_FILE, "w", encoding="utf-8") as f:
        json.dump({"id": 1, "time": time.time() - age, "label": label, "actions": actions}, f)
    bridge.apply_request("listener")


def log_text(bridge):
    try:
        return Path(bridge.LOG_FILE).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def test_brush_that_exists_is_pressed(bridge):
    bridge.stub.items.add("Brush:Standard")
    send(bridge, [{"brush": "Standard", "file": None}])
    assert bridge.stub.presses() == ["Brush:Standard"]
    assert bridge.S.select_pending == []
    assert "brush Standard: selected" in log_text(bridge)
    assert not os.path.exists(bridge.REQUEST_FILE)


def test_brush_with_a_file_and_no_button_is_loaded_and_queued(bridge, tmp_path, monkeypatch):
    """With a listener; without one the pick cannot select afterwards and the queue is dropped."""
    listening(bridge, monkeypatch)
    zbp = tmp_path / "ClayBuildup.zbp"
    zbp.write_bytes(b"x")
    send(bridge, [{"brush": "Clay Buildup", "file": str(zbp).replace("\\", "/"), "button": "ClayBuildup"}])
    assert bridge.stub.presses() == ["Brush:Load Brush"]
    assert ("set_next_filename", str(zbp).replace("\\", "/")) in bridge.stub.calls
    assert bridge.S.select_pending == [("Brush:ClayBuildup", bridge.SELECT_TRIES)]


def test_the_pick_log_says_what_is_selected_afterwards(bridge, tmp_path, monkeypatch):
    listening(bridge, monkeypatch)
    zbp = tmp_path / "ClayBuildup.zbp"
    zbp.write_bytes(b"x")
    send(bridge, [{"brush": "Clay Buildup", "file": str(zbp)}])
    assert "(selected after the pick: Brush:ClayBuildup)" in log_text(bridge)
    assert ("set", bridge.TIMER_SELECT) in bridge.timers


def test_two_assets_not_loaded_yet_queue_two_entries_in_order(bridge, tmp_path, monkeypatch):
    listening(bridge, monkeypatch)
    brush, alpha = tmp_path / "Dam.zbp", tmp_path / "Soft.psd"
    brush.write_bytes(b"x")
    alpha.write_bytes(b"x")
    send(bridge, [{"brush": "Dam", "file": str(brush)}, {"alpha": "Soft", "file": str(alpha)}])
    assert [p for p, _ in bridge.S.select_pending] == ["Brush:Dam", "Alpha:Soft"]


def test_a_later_asset_that_is_loaded_keeps_the_earlier_pending_entries(bridge, tmp_path, monkeypatch):
    listening(bridge, monkeypatch)
    brush = tmp_path / "Dam.zbp"
    brush.write_bytes(b"x")
    bridge.stub.items.add("Alpha:Round")
    send(bridge, [{"brush": "Dam", "file": str(brush)}, {"alpha": "Round", "file": None}])
    assert [p for p, _ in bridge.S.select_pending] == ["Brush:Dam"]
    assert bridge.stub.presses()[-1] == "Alpha:Round"


def test_pending_entries_are_pressed_one_by_one(bridge, tmp_path, monkeypatch):
    listening(bridge, monkeypatch)
    bridge.S.select_pending = [("Brush:Dam", 3), ("Alpha:Soft", 3)]
    bridge.stub.items.update({"Brush:Dam", "Alpha:Soft"})
    bridge._select_pending(1234)
    assert bridge.stub.presses() == ["Brush:Dam"]
    assert ("kill", bridge.TIMER_SELECT) not in bridge.timers
    bridge._select_pending(1234)
    assert bridge.stub.presses() == ["Brush:Dam", "Alpha:Soft"]
    assert bridge.S.select_pending == []
    assert ("kill", bridge.TIMER_SELECT) in bridge.timers


def test_a_pending_entry_that_never_appears_is_given_up_after_its_tries(bridge):
    bridge.S.select_pending = [("Brush:Gone", 2), ("Alpha:Soft", 2)]
    bridge._select_pending(1)
    assert bridge.S.select_pending == [("Brush:Gone", 1), ("Alpha:Soft", 2)]
    bridge._select_pending(1)
    assert bridge.S.select_pending == [("Alpha:Soft", 2)]
    assert "did not appear" in log_text(bridge)


def test_pending_entries_wait_during_a_stroke(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "primary_down", lambda: True)
    bridge.S.select_pending = [("Brush:Dam", 5)]
    bridge.stub.items.add("Brush:Dam")
    bridge._select_pending(1)
    assert bridge.stub.presses() == []
    assert bridge.S.select_pending == [("Brush:Dam", 5)]


def test_button_by_the_file_name_when_the_menu_name_has_spaces(bridge, tmp_path):
    """The app finds ClayBuildup.zbp for 'Clay Buildup'; ZBrush's button is ClayBuildup."""
    zbp = tmp_path / "ClayBuildup.zbp"
    zbp.write_bytes(b"x")
    bridge.stub.items.add("Brush:ClayBuildup")
    send(bridge, [{"brush": "Clay Buildup", "file": str(zbp)}])
    assert bridge.stub.presses() == ["Brush:ClayBuildup"]
    assert bridge.S.select_pending == []


def test_the_button_the_app_names_is_preferred(bridge):
    bridge.stub.items.update({"Brush:Clay Buildup", "Brush:CB"})
    send(bridge, [{"brush": "Clay Buildup", "file": None, "button": "CB"}])
    assert bridge.stub.presses() == ["Brush:CB"]


def test_the_file_name_button_is_used_after_loading_too(bridge, tmp_path, monkeypatch):
    listening(bridge, monkeypatch)
    zbp = tmp_path / "ClayBuildup.zbp"
    zbp.write_bytes(b"x")
    bridge.stub.on_press["Brush:Load Brush"] = lambda: bridge.stub.items.add("Brush:ClayBuildup")
    send(bridge, [{"brush": "Clay Buildup", "file": str(zbp)}])
    assert bridge.stub.presses() == ["Brush:Load Brush", "Brush:ClayBuildup"]
    assert bridge.S.select_pending == [("Brush:ClayBuildup", bridge.SELECT_TRIES)]


def test_a_request_older_than_ten_seconds_is_ignored(bridge):
    bridge.stub.items.add("Brush:Standard")
    send(bridge, [{"brush": "Standard"}], age=11)
    assert bridge.stub.presses() == []
    assert "ignored" in log_text(bridge)
    assert not os.path.exists(bridge.REQUEST_FILE)


def test_an_unreadable_request_is_removed(bridge):
    Path(bridge.REQUEST_FILE).write_text("{not json", encoding="utf-8")
    bridge.apply_request("listener")
    assert not os.path.exists(bridge.REQUEST_FILE)
    assert "unreadable request" in log_text(bridge)
    assert bridge.stub.presses() == []


def test_install_goes_on_when_one_button_fails(bridge):
    bridge.stub.fail_buttons.add("Zplugin:ZOrbit:Apply")
    bridge.start_listener = lambda: None
    bridge.start_app = lambda sender="": None
    bridge.install()
    added = [c[1] for c in bridge.stub.calls if c[0] == "add_button"]
    assert added == ["Zplugin:ZOrbit:Studio", "Zplugin:ZOrbit:Apply", "Zplugin:ZOrbit:Start App",
                     "Zplugin:ZOrbit:Status"]
    text = log_text(bridge)
    assert "could not create the button Apply" in text
    assert "bridge loaded" in text and "1 part(s) failed" in text


def test_a_failing_listener_does_not_stop_install(bridge):
    def boom():
        raise OSError("no window")
    bridge.start_listener = boom
    bridge.start_app = lambda sender="": None
    bridge.install()
    text = log_text(bridge)
    assert "could not start the listener" in text
    assert "bridge loaded" in text


def test_a_failed_import_is_written_to_the_log(tmp_path, monkeypatch):
    """No zbrush module at all: the error reaches bridge.log before it is raised again."""
    monkeypatch.setitem(sys.modules, "zbrush", None)
    monkeypatch.setitem(sys.modules, "zbrush.commands", None)
    monkeypatch.setenv("RADIAL_BRIDGE_NO_INSTALL", "1")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    spec = importlib.util.spec_from_file_location("zorbit_bridge_no_zbrush", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    with pytest.raises(ImportError):
        spec.loader.exec_module(mod)
    text = (tmp_path / "ZOrbit" / "bridge.log").read_text(encoding="utf-8")
    assert "the plugin could not start" in text
    assert "ImportError" in text or "ModuleNotFoundError" in text


def test_a_request_held_back_for_a_long_stroke_is_still_carried_out(bridge):
    # The app waits up to 30 s for a stroke to end; the plugin's age limit must not drop that pick.
    bridge.stub.items.add("Brush:Standard")
    with open(bridge.REQUEST_FILE, "w", encoding="utf-8") as f:
        json.dump({"id": 1, "time": time.time() - 25, "label": "test", "actions": [{"brush": "Standard"}]}, f)
    bridge.apply_request("listener, after stroke")
    assert bridge.stub.presses() == ["Brush:Standard"]
    assert "ignored" not in log_text(bridge)


def test_the_app_output_log_moves_aside_when_it_grows(bridge, monkeypatch, tmp_path):
    # The app prints every log line, so app_stderr.log would gain a copy of radiald.log on every start.
    errlog = Path(bridge.DATA_DIR) / "app_stderr.log"
    errlog.write_bytes(b"x" * 200_001)
    started = []
    monkeypatch.setattr(bridge.subprocess, "Popen", lambda cmd, **kw: started.append(kw["stdout"].name))
    bridge._spawn([str(tmp_path / "ZOrbit.exe")], "app_stderr.log")
    assert (Path(bridge.DATA_DIR) / "app_stderr.log.old").stat().st_size == 200_001
    assert errlog.stat().st_size == 0 and started == [str(errlog)]
    bridge._spawn([str(tmp_path / "ZOrbit.exe")], "app_stderr.log")     # small again: kept as it is
    assert (Path(bridge.DATA_DIR) / "app_stderr.log.old").stat().st_size == 200_001


# --- the file action: set the next file name, then press ---------------------------------------
def test_a_file_action_sets_the_file_and_then_presses_the_button(bridge):
    bridge.stub.items.add("Document:Export")
    send(bridge, [{"filepress": "Document:Export", "file": "C:/Users/you/Pictures/ZBrush_2026-11-04_12-00-05.png"}])
    assert bridge.stub.calls == [("set_next_filename", "C:/Users/you/Pictures/ZBrush_2026-11-04_12-00-05.png"),
                                 ("press", "Document:Export")]
    assert "file Document:Export: ok, file C:/Users/you/Pictures/ZBrush_2026-11-04_12-00-05.png" in log_text(bridge)


def test_a_file_action_with_a_missing_button_sets_no_file_and_presses_nothing(bridge):
    send(bridge, [{"filepress": "Document:Export", "file": "C:/Users/you/a.png"}])
    assert bridge.stub.calls == []
    assert "file Document:Export: no such interface item" in log_text(bridge)


def test_a_file_action_with_a_backslash_path_goes_to_zbrush_with_forward_slashes(bridge):
    bridge.stub.items.add("Document:Export")
    send(bridge, [{"filepress": "Document:Export", "file": "C:\\Users\\you\\a.png"}])
    assert bridge.stub.calls[0] == ("set_next_filename", "C:/Users/you/a.png")


def test_a_file_action_without_a_file_is_not_pressed(bridge):
    bridge.stub.items.add("Document:Export")
    send(bridge, [{"filepress": "Document:Export"}])
    assert bridge.stub.calls == []
    assert "file Document:Export: no file given" in log_text(bridge)


def test_a_file_action_runs_in_order_with_the_actions_around_it(bridge):
    bridge.stub.items.update({"Tool:Masking:Clear", "Document:Export"})
    send(bridge, [{"press": "Tool:Masking:Clear"}, {"filepress": "Document:Export", "file": "C:/Users/you/a.png"}])
    assert bridge.stub.presses() == ["Tool:Masking:Clear", "Document:Export"]


# --- the state channel: WM_APP_STATE, zstate_query.json in, zstate.json out ---------------------
def ask(bridge, paths, qid=42, ctrl=APP_HWND, wparam=None, **extra):
    """The app's side: writes the question and posts WM_APP_STATE to the listener."""
    q = {"v": 1, "id": qid, "time": time.time(), "paths": [{"p": p, "k": k} for p, k in paths]}
    q.update(extra)
    Path(bridge.STATE_QUERY_FILE).write_text(json.dumps(q), encoding="utf-8")
    return bridge._wndproc(1234, bridge.WM_APP_STATE, qid if wparam is None else wparam, ctrl)


def answer(bridge):
    return json.loads(Path(bridge.STATE_FILE).read_text(encoding="utf-8"))


def zbrush_with_state(bridge):
    """A ZBrush with a mesh in Edit mode, Symmetry on and Draw Size 64; Tool:Masking is not there."""
    s = bridge.stub
    s.items.update({"Transform:Activate Symmetry", "Draw:Draw Size", "Transform:Edit", "Edit:Undo"})
    s.values.update({"Transform:Activate Symmetry": 1.0, "Draw:Draw Size": 64.0, "Transform:Edit": 1.0})
    s.ranges["Draw:Draw Size"] = (1.0, 1000.0)
    s.disabled.add("Edit:Undo")
    s.titles.update({"Tool:ItemInfo": "SimpleBrush.", "Brush:ItemInfo": "Standard.",
                     "Brush:Current Brush": "C:\\Users\\you\\ZBrush\\BrushPresets\\Standard.zbp",
                     "Material:ItemInfo": "MatCap Red Wax."})


def test_the_snapshot_has_the_statuses_values_ranges_and_extras(bridge):
    zbrush_with_state(bridge)
    assert ask(bridge, [("Transform:Activate Symmetry", "toggle"), ("Draw:Draw Size", "set"),
                        ("Tool:Masking:Clear", "press"), ("Edit:Undo", "press")]) == 0
    snap = answer(bridge)
    assert snap["items"] == {"Transform:Activate Symmetry": {"s": "ok", "v": 1.0},
                             "Draw:Draw Size": {"s": "ok", "v": 64.0, "min": 1.0, "max": 1000.0},
                             "Tool:Masking:Clear": {"s": "missing"},
                             "Edit:Undo": {"s": "disabled"}}
    assert list(snap["items"]) == ["Transform:Activate Symmetry", "Draw:Draw Size", "Tool:Masking:Clear",
                                   "Edit:Undo"]
    assert snap["extras"] == {"tool": "SimpleBrush", "brush": "Standard",
                              "brush_file": "C:/Users/you/ZBrush/BrushPresets/Standard.zbp",
                              "material": "MatCap Red Wax", "edit": True, "edit_enabled": True}
    assert snap["v"] == 1 and snap["id"] == 42 and snap["pick"] == 0
    assert snap["pid"] == os.getpid() and snap["session"] == "429428"
    assert snap["truncated"] is False and isinstance(snap["ms"], float)
    assert abs(snap["time"] - time.time()) < 5
    assert bridge.posted == [(APP_HWND, bridge.WM_APP_STATE_READY, 42, 0)]
    assert sorted(os.listdir(bridge.DATA_DIR)) == ["bridge.log", "zstate.json", "zstate_query.json"]   # no tmp
    assert bridge.stub.calls == []                        # nothing pressed, set or toggled: reads only


def test_a_greyed_toggle_keeps_its_value(bridge):
    bridge.stub.items.add("Transform:Edit")
    bridge.stub.disabled.add("Transform:Edit")
    bridge.stub.values["Transform:Edit"] = 0.0
    ask(bridge, [("Transform:Edit", "toggle")])
    assert answer(bridge)["items"]["Transform:Edit"] == {"s": "disabled", "v": 0.0}


def test_a_path_asked_twice_is_read_once_with_its_kinds_merged(bridge):
    zbrush_with_state(bridge)
    ask(bridge, [("Draw:Draw Size", "press"), ("Draw:Draw Size", "set")])
    assert answer(bridge)["items"] == {"Draw:Draw Size": {"s": "ok", "v": 64.0, "min": 1.0, "max": 1000.0}}


def test_the_question_is_answered_during_a_stroke(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "primary_down", lambda: True)
    zbrush_with_state(bridge)
    ask(bridge, [("Draw:Draw Size", "set")])
    assert answer(bridge)["items"]["Draw:Draw Size"]["v"] == 64.0
    assert bridge.posted and bridge.timers == []          # answered now, no timer to wait for the pen


def test_a_read_that_raises_gives_error_for_that_path_only(bridge):
    zbrush_with_state(bridge)
    bridge.stub.items.add("Draw:Broken")
    bridge.stub.raising.add("Draw:Broken")
    ask(bridge, [("Draw:Broken", "set"), ("Draw:Draw Size", "set")])
    items = answer(bridge)["items"]
    assert items["Draw:Broken"] == {"s": "error"}
    assert items["Draw:Draw Size"]["s"] == "ok"
    assert bridge.posted


def test_a_value_that_is_not_a_number_gives_error_and_the_file_stays_json(bridge):
    bridge.stub.items.add("Draw:Odd")
    bridge.stub.values["Draw:Odd"] = float("nan")
    ask(bridge, [("Draw:Odd", "toggle")])
    assert answer(bridge)["items"]["Draw:Odd"] == {"s": "error"}


def test_an_extra_that_cannot_be_read_is_left_out(bridge):
    zbrush_with_state(bridge)
    del bridge.stub.titles["Material:ItemInfo"]
    bridge.stub.raising.add("Transform:Edit")
    ask(bridge, [])
    extras = answer(bridge)["extras"]
    assert "material" not in extras and "edit" not in extras and "edit_enabled" not in extras
    assert extras["brush"] == "Standard"


@pytest.mark.parametrize("asked, truncated", [(128, False), (129, True)])
def test_no_more_than_128_paths_are_read(bridge, asked, truncated):
    paths = [(f"Draw:Item {i}", "press") for i in range(asked)]
    bridge.stub.items.update(p for p, _ in paths)
    ask(bridge, paths + [("Draw:Item 0", "set")])         # a path asked twice counts once
    snap = answer(bridge)
    assert len(snap["items"]) == bridge.STATE_MAX_PATHS == 128
    assert "Draw:Item 127" in snap["items"] and "Draw:Item 128" not in snap["items"]
    assert snap["truncated"] is truncated


def test_reading_stops_after_the_time_budget(bridge, monkeypatch):
    """Each look at the clock is 6 ms later: the first three paths fit in 20 ms, the fourth does not."""
    ticks = iter(range(0, 10_000, 6))
    monkeypatch.setattr(bridge, "_clock", lambda: next(ticks) / 1000.0)
    paths = [(f"Draw:Item {i}", "press") for i in range(10)]
    bridge.stub.items.update(p for p, _ in paths)
    ask(bridge, paths)
    snap = answer(bridge)
    assert list(snap["items"]) == ["Draw:Item 0", "Draw:Item 1", "Draw:Item 2"]
    assert snap["truncated"] is True
    assert snap["ms"] > 20
    assert bridge.posted                                  # a cut answer is still an answer


def test_the_id_in_the_file_is_answered_not_the_one_in_the_message(bridge):
    ask(bridge, [], qid=43, wparam=42)                    # the app asked 42, then 43 replaced the file
    assert answer(bridge)["id"] == 43
    assert bridge.posted[-1][2] == 43


def test_a_foreign_window_gets_no_answer(bridge):
    zbrush_with_state(bridge)
    ask(bridge, [("Draw:Draw Size", "set")], ctrl=999)
    assert bridge.posted == []
    assert not os.path.exists(bridge.STATE_FILE)
    assert bridge.S.state_ctrl is None
    assert "not ZOrbit's" in log_text(bridge)


def test_a_question_of_another_version_or_unreadable_is_not_answered(bridge):
    ask(bridge, [], v=2)
    Path(bridge.STATE_QUERY_FILE).write_text("{half", encoding="utf-8")
    bridge._wndproc(1234, bridge.WM_APP_STATE, 1, APP_HWND)
    os.remove(bridge.STATE_QUERY_FILE)
    bridge._wndproc(1234, bridge.WM_APP_STATE, 1, APP_HWND)
    assert bridge.posted == [] and not os.path.exists(bridge.STATE_FILE)
    text = log_text(bridge)
    assert "not a version 1 question" in text and "unreadable zstate_query.json" in text
    assert "no zstate_query.json" in text


def test_the_listener_publishes_the_state_capability(bridge):
    bridge.S.hwnd = 1234
    bridge._publish_listener()
    info = json.loads(Path(bridge.LISTENER_FILE).read_text(encoding="utf-8"))
    assert info["state"] == 1 and info["hwnd"] == 1234 and info["pid"] == os.getpid()


def test_a_pick_sends_the_state_again_unasked(bridge):
    zbrush_with_state(bridge)
    ask(bridge, [("Transform:Activate Symmetry", "toggle")])
    assert answer(bridge)["pick"] == 0
    bridge.stub.on_press["Transform:Activate Symmetry"] = (
        lambda: bridge.stub.values.update({"Transform:Activate Symmetry": 0.0}))
    send(bridge, [{"press": "Transform:Activate Symmetry"}])
    snap = answer(bridge)
    assert snap["pick"] == 1 and snap["id"] == 42
    assert snap["items"]["Transform:Activate Symmetry"]["v"] == 0.0
    assert len(bridge.posted) == 2
    assert "state #42 (after pick #1)" in log_text(bridge)


def test_no_unasked_state_before_the_first_question(bridge):
    bridge.stub.items.add("Brush:Standard")
    send(bridge, [{"brush": "Standard"}])
    assert bridge.posted == [] and not os.path.exists(bridge.STATE_FILE)
    assert bridge.S.pick == 1


def test_no_unasked_state_once_the_app_window_is_gone(bridge, monkeypatch):
    ask(bridge, [])
    monkeypatch.setattr(bridge, "_class_name", lambda h: "")
    send(bridge, [])
    assert len(bridge.posted) == 1


def test_a_stale_pick_still_counts_as_taken_and_sends_the_state(bridge):
    """The app waits for a snapshot with pick >= its id; a pick dropped as stale changed nothing, so the state
    after it is the one to wait for."""
    ask(bridge, [])
    send(bridge, [{"press": "Edit:Undo"}], age=11)
    assert answer(bridge)["pick"] == 1 and len(bridge.posted) == 2


def test_the_state_is_sent_again_once_the_loaded_brush_is_selected(bridge, tmp_path, monkeypatch):
    listening(bridge, monkeypatch)
    zbrush_with_state(bridge)
    ask(bridge, [])
    zbp = tmp_path / "Dam.zbp"
    zbp.write_bytes(b"x")
    send(bridge, [{"brush": "Dam", "file": str(zbp)}])
    assert len(bridge.posted) == 2 and answer(bridge)["extras"]["brush"] == "Standard"   # not selected yet
    bridge.stub.items.add("Brush:Dam")
    bridge.stub.on_press["Brush:Dam"] = lambda: bridge.stub.titles.update({"Brush:ItemInfo": "Dam."})
    bridge._select_pending(1234)
    assert bridge.S.select_pending == []
    assert len(bridge.posted) == 3 and answer(bridge)["extras"]["brush"] == "Dam"
    bridge._select_pending(1234)                          # a tick on an empty queue sends nothing more
    assert len(bridge.posted) == 3


def test_the_state_is_not_sent_while_loaded_items_still_wait(bridge, monkeypatch):
    listening(bridge, monkeypatch)
    ask(bridge, [])
    bridge.S.select_pending = [("Brush:Dam", 3), ("Alpha:Soft", 3)]
    bridge.stub.items.update({"Brush:Dam", "Alpha:Soft"})
    bridge._select_pending(1234)
    assert len(bridge.posted) == 1
    bridge._select_pending(1234)
    assert len(bridge.posted) == 2


def test_each_answer_logs_its_timing(bridge):
    zbrush_with_state(bridge)
    ask(bridge, [("Draw:Draw Size", "set"), ("Tool:Masking:Clear", "press")])
    text = log_text(bridge)
    assert "state #42 (asked): 2 paths in " in text
    assert "ms after the question was written (1 missing)" in text


def test_a_failure_while_answering_is_logged_and_not_raised(bridge, monkeypatch):
    def boom(snap):
        raise OSError("disk full")
    monkeypatch.setattr(bridge, "_write_state", boom)
    assert ask(bridge, []) == 0
    assert bridge.posted == []
    assert "state (asked) error" in log_text(bridge) and "disk full" in log_text(bridge)


def test_status_shows_the_state_channel(bridge):
    bridge.status()
    assert "State channel: not asked yet" in bridge.stub.calls[-1][1]
    ask(bridge, [])
    bridge.status()
    assert "State channel: 1 answer(s), last #42 (asked)" in bridge.stub.calls[-1][1]


def test_a_question_answered_while_a_pick_runs_does_not_claim_that_pick(bridge):
    """A long press (a load with a progress bar) can let ZBrush dispatch the listener's messages."""
    bridge.stub.items.add("Tool:Load Tool")
    ask(bridge, [])
    during = []
    bridge.stub.on_press["Tool:Load Tool"] = lambda: (ask(bridge, [], qid=43), during.append(answer(bridge)))
    send(bridge, [{"press": "Tool:Load Tool"}])
    assert during[0]["id"] == 43 and during[0]["pick"] == 0
    assert answer(bridge)["pick"] == 1 and bridge.S.pick == 1


def test_the_tmp_file_is_named_for_this_process(bridge, monkeypatch):
    moved = []
    real = os.replace
    monkeypatch.setattr(bridge.os, "replace", lambda a, b: (moved.append((a, b)), real(a, b)))
    ask(bridge, [])
    assert moved == [(f"{bridge.STATE_FILE}.{os.getpid()}.tmp", bridge.STATE_FILE)]


def test_the_refreshes_stop_when_the_app_removes_its_question(bridge):
    ask(bridge, [])
    os.remove(bridge.STATE_QUERY_FILE)
    before = log_text(bridge)
    send(bridge, [])
    assert len(bridge.posted) == 1 and bridge.S.state_ctrl is None
    assert "zstate_query.json" not in log_text(bridge)[len(before):]     # stopping is normal: nothing logged
    send(bridge, [])
    assert len(bridge.posted) == 1
    ask(bridge, [], qid=50)                                # asking again starts them again
    send(bridge, [])
    assert len(bridge.posted) == 3 and answer(bridge)["pick"] == 1


def test_a_question_that_turns_bad_stops_the_refreshes_with_one_log_line(bridge):
    ask(bridge, [])
    Path(bridge.STATE_QUERY_FILE).write_text('{"v": 2, "id": 1}', encoding="utf-8")
    send(bridge, [])
    send(bridge, [])
    assert len(bridge.posted) == 1 and bridge.S.state_ctrl is None
    assert log_text(bridge).count("no more unasked answers") == 1


def test_a_bad_question_asked_does_not_start_the_refreshes(bridge):
    ask(bridge, [], v=2)
    assert bridge.S.state_ctrl is None


def test_a_question_file_being_replaced_does_not_stop_the_refreshes(bridge, monkeypatch):
    ask(bridge, [])
    real_read = bridge._read_query
    bridge._read_query = lambda: (None, ("busy", "zstate_query.json could not be read: PermissionError"))
    send(bridge, [])
    bridge._read_query = real_read
    assert len(bridge.posted) == 1 and bridge.S.state_ctrl == APP_HWND
    send(bridge, [])
    assert len(bridge.posted) == 2


def test_a_question_file_that_cannot_be_opened_is_busy(bridge, monkeypatch):
    real_open = open

    def locked(path, *a, **kw):
        if str(path) == bridge.STATE_QUERY_FILE:
            raise PermissionError(13, "in use")
        return real_open(path, *a, **kw)
    monkeypatch.setattr("builtins.open", locked)
    q, problem = bridge._read_query()
    monkeypatch.setattr("builtins.open", real_open)
    assert q is None and problem[0] == "busy"


def state_lines(bridge):
    return [ln.split(" state ")[1].split(" ")[0] for ln in log_text(bridge).splitlines() if " state #" in ln]


def test_after_ten_answers_only_the_odd_one_is_logged(bridge, monkeypatch):
    monkeypatch.setattr(bridge, "_clock", lambda: 0.0)
    for i in range(12):
        ask(bridge, [], qid=i)
    assert state_lines(bridge) == [f"#{i}" for i in range(10)]
    assert bridge.S.state_count == 12 and bridge.S.state_last.startswith("#11 (asked)")    # Status sees them all

    ask(bridge, [(f"Draw:Item {i}", "press") for i in range(129)], qid=20)    # cut short
    bridge.stub.items.add("Draw:Broken")
    bridge.stub.raising.add("Draw:Broken")
    ask(bridge, [("Draw:Broken", "set")], qid=21)                             # a read raised
    monkeypatch.setattr(bridge, "PostMessageW", lambda *a: 0)
    ask(bridge, [], qid=22)                                                   # not posted
    monkeypatch.setattr(bridge, "PostMessageW", lambda *a: 1)
    ticks = iter(range(0, 10_000, 3))
    monkeypatch.setattr(bridge, "_clock", lambda: next(ticks) / 1000.0)
    ask(bridge, [("Draw:A", "press")], qid=23)                                # slow: 6 ms of reads
    monkeypatch.setattr(bridge, "_clock", lambda: 0.0)
    ask(bridge, [("Draw:A", "press")], qid=24)                                # ordinary again: not logged
    assert state_lines(bridge)[10:] == ["#20", "#21", "#22", "#23"]


def test_a_request_that_is_not_an_object_is_dropped(bridge):
    bridge.stub.items.add("Brush:Standard")
    Path(bridge.REQUEST_FILE).write_text("[1, 2]", encoding="utf-8")
    bridge.apply_request("listener")
    assert "unreadable request: not an object" in log_text(bridge)
    assert bridge.stub.calls == [] and not os.path.exists(bridge.REQUEST_FILE)


def test_a_reload_over_the_state_of_an_older_plugin_fills_in_the_new_fields(tmp_path, monkeypatch):
    """ZBrush's Python keeps S between loads; one left by a plugin from before the state channel lacks its fields."""
    pkg = types.ModuleType("zbrush")
    pkg.commands = Stub()
    monkeypatch.setitem(sys.modules, "zbrush", pkg)
    monkeypatch.setitem(sys.modules, "zbrush.commands", pkg.commands)
    monkeypatch.setenv("RADIAL_BRIDGE_NO_INSTALL", "1")
    old = types.ModuleType("_zorbit_bridge_state")
    old.keepalive, old.hwnd, old.seq, old.verified, old.last = ["proc"], 77, 3, True, "#9 'Standard' via listener"
    old.select_pending = [("Brush:Dam", 4)]
    monkeypatch.setitem(sys.modules, "_zorbit_bridge_state", old)
    spec = importlib.util.spec_from_file_location("zorbit_bridge_reloaded", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.S is old
    assert (old.pick, old.state_ctrl, old.state_count, old.state_last) == (0, None, 0, "")
    assert (old.hwnd, old.seq, old.select_pending) == (77, 3, [("Brush:Dam", 4)])     # what it had stays
