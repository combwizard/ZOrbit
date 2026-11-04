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


class Stub(types.ModuleType):
    """zbrush.commands: records every call; `items` is the set of interface paths that exist."""

    def __init__(self):
        super().__init__("zbrush.commands")
        self.items = set()
        self.calls = []
        self.values = {}
        self.fail_buttons = set()
        self.on_press = {}

    def _rec(self, *call):
        self.calls.append(call)

    def exists(self, path):
        return path in self.items

    def press(self, path):
        self._rec("press", path)
        if path in self.on_press:
            self.on_press[path]()

    def set(self, path, value):
        self._rec("set", path, value)

    def toggle(self, path):
        self._rec("toggle", path)

    def get(self, path):
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
    monkeypatch.setattr(mod, "primary_down", lambda: False)
    mod.S.select_pending = []
    mod.S.hwnd = None
    mod.stub = stub
    mod.timers = []
    monkeypatch.setattr(mod, "SetTimer", lambda hwnd, tid, ms, cb: mod.timers.append(("set", tid)))
    monkeypatch.setattr(mod, "KillTimer", lambda hwnd, tid: mod.timers.append(("kill", tid)))
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
