"""The Capture item: the name and folder of the picture (capture.py), how the app turns the item into the request
for the bridges (radiald._actions), and what it does when the folder cannot be used."""
import ctypes
import json
import os
import time
import types

import pytest

import capture
import config
import paths
import radiald
import win32 as W
import zscript_bridge


def at(*t):
    """A clock reading the local time y, m, d, h, min, s."""
    stamp = time.mktime((*t, 0, 0, -1))
    return lambda: stamp


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(capture, "_issued", set())
    monkeypatch.setattr(capture, "clock", at(2026, 11, 4, 12, 0, 5))


# --- the name ------------------------------------------------------------------------------------
def test_the_name_is_the_local_time(tmp_path):
    got = capture.target(str(tmp_path))
    assert got == (str(tmp_path) + "/ZBrush_2026-11-04_12-00-05.png").replace("\\", "/")


def test_a_second_pick_in_the_same_second_gets_a_number(tmp_path):
    first = capture.target(str(tmp_path))
    open(first, "wb").close()                     # ZBrush has written the first
    second = capture.target(str(tmp_path))
    open(second, "wb").close()
    third = capture.target(str(tmp_path))
    assert [os.path.basename(p) for p in (first, second, third)] == [
        "ZBrush_2026-11-04_12-00-05.png", "ZBrush_2026-11-04_12-00-05_2.png", "ZBrush_2026-11-04_12-00-05_3.png"]


def test_a_name_handed_out_but_not_written_yet_is_not_handed_out_again(tmp_path):
    # ZBrush may still be waiting for the pen when the next pick comes: nothing is on disk, the names still differ.
    names = [os.path.basename(capture.target(str(tmp_path))) for _ in range(3)]
    assert names == ["ZBrush_2026-11-04_12-00-05.png", "ZBrush_2026-11-04_12-00-05_2.png",
                     "ZBrush_2026-11-04_12-00-05_3.png"]


def test_a_file_that_is_there_is_never_the_name(tmp_path):
    (tmp_path / "ZBrush_2026-11-04_12-00-05.png").write_bytes(b"mine")
    assert capture.target(str(tmp_path)).endswith("12-00-05_2.png")
    assert (tmp_path / "ZBrush_2026-11-04_12-00-05.png").read_bytes() == b"mine"


def test_the_probe_file_is_removed(tmp_path):
    capture.target(str(tmp_path))
    assert os.listdir(tmp_path) == []


def test_a_probe_left_by_an_earlier_run_does_not_stop_a_capture(tmp_path):
    (tmp_path / f".zorbit-write-test-{os.getpid()}").write_bytes(b"")
    assert capture.target(str(tmp_path)).endswith("12-00-05.png")


def test_a_probe_that_cannot_be_removed_does_not_stop_the_captures(tmp_path, monkeypatch):
    def locked(path):
        raise PermissionError(32, "The process cannot access the file")
    monkeypatch.setattr(capture.os, "remove", locked)           # an antivirus lock
    first = capture.target(str(tmp_path))
    second = capture.target(str(tmp_path))
    assert first.endswith("12-00-05.png") and second.endswith("12-00-05_2.png")
    assert len(os.listdir(tmp_path)) == 2                       # two probes left, with different names


# --- the folder ----------------------------------------------------------------------------------
def test_a_missing_folder_is_made(tmp_path):
    folder = tmp_path / "shots" / "zbrush"
    got = capture.target(str(folder))
    assert folder.is_dir() and os.path.dirname(got) == str(folder).replace("\\", "/")


def test_a_folder_that_is_a_file_is_refused(tmp_path):
    (tmp_path / "shots").write_bytes(b"x")
    with pytest.raises(capture.CaptureError) as e:
        capture.target(str(tmp_path / "shots"))
    assert e.value.kind == "folder" and "shots" in e.value.reason


def test_a_folder_that_cannot_be_written_to_is_refused(tmp_path, monkeypatch):
    def deny(path, *a, **k):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(capture, "_probe", deny)
    with pytest.raises(capture.CaptureError) as e:
        capture.target(str(tmp_path))
    assert e.value.kind == "folder" and "Access is denied" in e.value.reason


def test_a_relative_folder_is_refused(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(capture.CaptureError) as e:
        capture.target("shots")
    assert e.value.kind == "folder" and not (tmp_path / "shots").exists()


PICTURE_NAME = "ZBrush_2026-11-04_12-00-05.png"


def folder_for(tmp_path, total):
    """A folder whose picture's path is total characters long."""
    folder = tmp_path / ("a" * (total - len(str(tmp_path)) - 2 * len(os.sep) - len(PICTURE_NAME)))
    assert len(os.path.join(str(folder), PICTURE_NAME)) == total
    return folder


def test_a_path_of_exactly_the_longest_windows_takes_is_fine(tmp_path):
    folder = folder_for(tmp_path, capture.MAX_PATH_CHARS)
    assert capture.target(str(folder)).endswith(PICTURE_NAME) and folder.is_dir()


def test_a_path_one_character_too_long_is_refused_and_nothing_is_written(tmp_path):
    folder = folder_for(tmp_path, capture.MAX_PATH_CHARS + 1)
    with pytest.raises(capture.CaptureError) as e:
        capture.target(str(folder))
    assert e.value.kind == "folder" and "260 characters" in e.value.reason
    assert not folder.exists() and os.listdir(tmp_path) == []
    assert capture.target(str(tmp_path)).endswith(PICTURE_NAME)  # the refused name was not remembered


def test_a_path_too_long_for_2022_to_2025_is_refused_by_its_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_file", lambda p: p)   # no short names: the path is sent as it is
    folder = folder_for(tmp_path, capture.MAX_LEGACY_BYTES + 1)
    with pytest.raises(capture.CaptureError) as e:
        capture.target(str(folder), legacy=True)
    assert e.value.kind == "folder" and "255 bytes" in e.value.reason
    assert os.listdir(folder) == []                              # the folder was made to ask Windows its short name, no picture
    assert capture.target(str(folder)).endswith(PICTURE_NAME)        # ZBrush 2026 is not held to the byte limit


def test_a_path_of_exactly_the_2022_to_2025_limit_is_fine(tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_file", lambda p: p)
    folder = folder_for(tmp_path, capture.MAX_LEGACY_BYTES)
    assert capture.target(str(folder), legacy=True).endswith(PICTURE_NAME)


# --- ZBrush 2022-2025 read ANSI ---------------------------------------------------------------
def test_zbrush_2026_gets_the_folder_as_it_is(tmp_path):
    folder = tmp_path / "Gr\u00f6\u00dfe \u65e5\u672c"
    got = capture.target(str(folder))
    assert folder.is_dir() and "Gr\u00f6\u00dfe \u65e5\u672c" in got


def test_a_folder_name_the_plugin_cannot_read_is_refused_for_2022_to_2025(tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_path", lambda p, spaces=False: p)       # a volume with no 8.3 names
    with pytest.raises(capture.CaptureError) as e:
        capture.target(str(tmp_path / "Gr\u00f6\u00dfe"), legacy=True)
    assert e.value.kind == "name"


def test_a_folder_with_a_short_name_is_fine_for_2022_to_2025(tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_path", lambda p, spaces=False: p if p.isascii() else "C:/GRSSE~1")
    got = capture.target(str(tmp_path / "Gr\u00f6\u00dfe"), legacy=True)
    assert "Gr\u00f6\u00dfe" in got                                  # the app keeps the real name; request.txt gets the short one


def test_a_plain_folder_needs_nothing_for_2022_to_2025(tmp_path):
    assert capture.target(str(tmp_path / "plain"), legacy=True).endswith(".png")


# --- the app ---------------------------------------------------------------------------------------
@pytest.fixture
def app(monkeypatch, tmp_path):
    a = radiald.App(paths.DEFAULT_MENUS)
    a.cfg = config.load(paths.DEFAULT_MENUS)
    a.ctrl = 1
    a.toasts, a.notes, a.dropped = [], [], []
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(radiald, "DATA_DIR", str(data))
    monkeypatch.setattr(radiald, "REQUEST_FILE", str(data / "request.json"))
    monkeypatch.setattr(zscript_bridge, "REQUEST_TXT", str(data / "request.txt"))
    monkeypatch.setattr(a, "_legacy_installed", lambda: False)
    monkeypatch.setattr(a, "_toast", a.toasts.append)
    monkeypatch.setattr(a, "_drop_request", a.dropped.append)
    monkeypatch.setattr(a, "target_install", lambda: None)
    monkeypatch.setattr(a, "_front_pid", lambda: 1)
    monkeypatch.setattr(a, "_listener", lambda pid: None)
    monkeypatch.setattr(a, "press_bridge_key", lambda seq: (True, None))
    monkeypatch.setattr(a.activity, "note_pick", lambda *x, **k: a.notes.append(x))
    monkeypatch.setattr(W, "nudge_mouse", lambda: None)
    a.tmpdata = data
    return a


def item(folder, label="Capture"):
    return config.Item(label=label, kind="capture", data={"capture": str(folder)})


def request(app):
    return json.loads((app.tmpdata / "request.json").read_text(encoding="utf-8"))


def test_the_pick_becomes_the_general_file_action(app, tmp_path):
    app.send(item(tmp_path / "shots"))
    [act] = request(app)["actions"]
    assert act == {"filepress": "Document:Export",
                   "file": (str(tmp_path / "shots") + "/ZBrush_2026-11-04_12-00-05.png").replace("\\", "/")}
    assert (tmp_path / "shots").is_dir() and app.toasts == []


def test_a_capture_in_steps_is_turned_into_the_action_too(app, tmp_path):
    steps = config.Item(label="Shot", kind="steps", data={"steps": [{"press": "Tool:Masking:Clear"},
                                                                    {"capture": str(tmp_path)}]})
    app.send(steps)
    acts = request(app)["actions"]
    assert acts[0] == {"press": "Tool:Masking:Clear"} and acts[1]["filepress"] == "Document:Export"
    assert acts[1]["file"].endswith("ZBrush_2026-11-04_12-00-05.png")


def test_two_picks_in_one_second_get_two_names(app, tmp_path):
    app.send(item(tmp_path))
    first = request(app)["actions"][0]["file"]
    app.send(item(tmp_path))
    assert request(app)["actions"][0]["file"] != first and request(app)["actions"][0]["file"].endswith("_2.png")


def test_the_request_text_for_zbrush_2022_to_2025_names_the_file(app, tmp_path):
    app.send(item(tmp_path))
    lines = (app.tmpdata / "request.txt").read_text(encoding="utf-8") if (app.tmpdata / "request.txt").exists() else ""
    assert lines == ""                        # only written when a ZBrush 2022-2025 is installed
    app._legacy_installed = lambda: True
    app.send(item(tmp_path))
    lines = (app.tmpdata / "request.txt").read_text(encoding="mbcs").splitlines()
    assert lines[3:5] == ["file", "Document:Export"] and lines[5].endswith("_2.png")


def test_a_folder_that_cannot_be_made_sends_nothing_and_says_so(app, tmp_path, monkeypatch):
    (tmp_path / "blocked").write_bytes(b"x")
    app.send(item(tmp_path / "blocked" / "shots"))
    assert app.toasts == [radiald.MSG_CAPTURE_FOLDER]
    assert not (app.tmpdata / "request.json").exists() and not (app.tmpdata / "request.txt").exists()
    [(seq, it, route, sent, source, menu, reason)] = app.notes
    assert (route, sent) == ("none", False) and "capture folder" in reason


def test_a_folder_that_cannot_be_written_to_sends_nothing_and_says_so(app, tmp_path, monkeypatch):
    def deny(path):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(capture, "_probe", deny)
    app.send(item(tmp_path))
    assert app.toasts == [radiald.MSG_CAPTURE_FOLDER]
    assert not (app.tmpdata / "request.json").exists()


def test_a_stale_request_is_not_left_behind_for_the_next_bridge_key(app, tmp_path, monkeypatch):
    (app.tmpdata / "request.json").write_text("{}")             # an earlier pick, still waiting
    (tmp_path / "blocked").write_bytes(b"x")
    app.send(item(tmp_path / "blocked" / "shots"))
    assert app.toasts == [radiald.MSG_CAPTURE_FOLDER]
    assert (app.tmpdata / "request.json").read_text() == "{}"   # not ours to remove, and not replaced by a capture


def test_a_folder_name_that_2022_to_2025_cannot_read_sends_nothing_and_says_so(app, tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_path", lambda p, spaces=False: p)
    ins = {"python": False, "name": "ZBrush 2024", "path": "C:/zb"}
    app.send(item(tmp_path / "Gr\u00f6\u00dfe"), install=ins)
    assert app.toasts == [radiald.MSG_CAPTURE_NAME]
    assert not (app.tmpdata / "request.json").exists()


def test_a_capture_does_not_count_in_recent_or_the_auto_slots(app, tmp_path, monkeypatch):
    recorded = []
    monkeypatch.setattr(app.usage, "record_pick", lambda *a: recorded.append(a))
    monkeypatch.setattr(app.usage, "record", lambda *a: recorded.append(a))
    app._record_pick(item(tmp_path))
    assert recorded == [] and app._known_item(item(tmp_path)).kind == "capture"


def test_check_lists_the_capture_item_with_its_folder(tmp_path, capsys):
    cfg = tmp_path / "radial.json"
    cfg.write_text(json.dumps({"menus": {"main": {"hotkey": "Q", "items": [
        {"capture": "C:/Users/you/Pictures/ZBrush"}, {"brush": "Standard"}]}}}), encoding="utf-8")
    assert radiald.check(str(cfg)) == 0
    assert "capture Capture  (saves into C:/Users/you/Pictures/ZBrush)" in capsys.readouterr().out


# --- the default folder ----------------------------------------------------------------------------
def refusing_windows(monkeypatch):
    """Windows refuses to say where its Pictures folder is, so the fallback is used."""
    def refused(*a):
        return -2147024891                                       # E_ACCESSDENIED
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(
        shell32=types.SimpleNamespace(SHGetKnownFolderPath=refused)), raising=False)


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A home folder, and no answer from Windows about its Pictures folder (the fallback)."""
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path / "home") if p == "~" else p)
    refusing_windows(monkeypatch)
    return tmp_path / "home"


def test_the_default_folder_is_pictures_zbrush_in_the_home_folder(home):
    assert capture.default_folder() == str(home / "Pictures" / "ZBrush")


def test_the_default_folder_is_in_the_pictures_folder_windows_gives(home, monkeypatch, tmp_path):
    moved = tmp_path / "OneDrive" / "Pictures"                   # Pictures moved out of the home folder
    monkeypatch.setattr(capture, "_windows_pictures", lambda: str(moved))
    assert capture.default_folder() == str(moved / "ZBrush")
    assert not (home / "Pictures").exists()


def test_the_default_folder_falls_back_when_windows_refuses(home):
    assert capture._windows_pictures() is None
    assert capture.default_folder() == str(home / "Pictures" / "ZBrush")


def test_the_default_folder_falls_back_when_the_windows_call_raises(home, monkeypatch):
    def broken(*a):
        raise OSError("no shell32")
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(
        shell32=types.SimpleNamespace(SHGetKnownFolderPath=broken)), raising=False)
    assert capture._windows_pictures() is None
    assert capture.default_folder() == str(home / "Pictures" / "ZBrush")


@pytest.mark.skipif(os.name != "nt", reason="asks Windows for its Pictures folder")
def test_windows_gives_the_real_pictures_folder():
    got = capture._windows_pictures()
    assert got is not None and os.path.basename(got) == "Pictures"


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_an_empty_folder_saves_into_the_default_folder_and_makes_it(home, empty):
    got = capture.target(empty)
    assert (home / "Pictures" / "ZBrush").is_dir()
    assert os.path.dirname(got) == str(home / "Pictures" / "ZBrush").replace("\\", "/")


def test_a_default_folder_zbrush_2022_to_2025_cannot_be_given_fails_the_same_way(home, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_path", lambda p, spaces=False: p)
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(home / "Gr\u00f6\u00dfe") if p == "~" else p)
    with pytest.raises(capture.CaptureError) as e:
        capture.target("", legacy=True)
    assert e.value.kind == "name"


def test_the_app_sends_an_empty_capture_to_the_default_folder(app, home):
    app.send(item(""))
    [act] = request(app)["actions"]
    assert os.path.dirname(act["file"]) == str(home / "Pictures" / "ZBrush").replace("\\", "/")


def test_an_empty_capture_in_check_says_where_it_saves(home, tmp_path, capsys):
    cfg = tmp_path / "radial.json"
    cfg.write_text(json.dumps({"menus": {"main": {"hotkey": "Q", "items": [{"capture": ""}, {"brush": "A"}]}}}),
                   encoding="utf-8")
    assert radiald.check(str(cfg)) == 0
    assert f"(saves into {capture.default_folder()})" in capsys.readouterr().out
