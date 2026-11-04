"""The Tool and Project items: which file the pick names (fileitem.py), how the app turns the item into the request
for the bridges (radiald._actions), and what it does when the file or folder is not there."""
import json
import os

import pytest

import config
import fileitem
import radiald
import zscript_bridge
from test_capture import app  # noqa: F401  (a fixture: the app with its files in a throw-away folder)


def make(path, age=0):
    """A file at path, `age` seconds older than the base time. The time is set, never waited for."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    stamp = 1_800_000_000 - age
    os.utime(path, (stamp, stamp))
    return path


def fwd(p):
    return str(p).replace("\\", "/")


def tool_item(path, label="Hero"):
    return config.Item(label=label, kind="tool", data={"tool": str(path)})


def project_item(path, label="Hero"):
    return config.Item(label=label, kind="project", data={"project": str(path)})


def request(app):
    return json.loads((app.tmpdata / "request.json").read_text(encoding="utf-8"))


# --- which file -------------------------------------------------------------------------------------
def test_a_tool_is_loaded_with_load_tool(tmp_path):
    f = make(tmp_path / "Hero.ztl")
    assert fileitem.resolve({"tool": str(f)}) == ("Tool:Load Tool", fwd(f))


def test_a_project_file_is_opened_with_file_open(tmp_path):
    f = make(tmp_path / "Hero.zpr")
    assert fileitem.resolve({"project": str(f)}) == ("File:Open", fwd(f))


@pytest.mark.parametrize("name,key", [("Hero.ZTL", "tool"), ("Hero.Ztl", "tool"), ("Hero.ZPR", "project")])
def test_the_extension_may_be_in_any_case(tmp_path, name, key):
    f = make(tmp_path / name)
    assert fileitem.resolve({key: str(f)})[1] == fwd(f)


def test_a_tool_file_that_is_not_there_is_an_error_that_names_it(tmp_path):
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"tool": str(tmp_path / "Gone.ztl")})
    assert e.value.kind == "file" and "Gone.ztl" in e.value.reason


def test_a_project_file_that_is_not_there_is_an_error(tmp_path):
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"project": str(tmp_path / "Gone.zpr")})
    assert e.value.kind == "file"


def test_a_folder_in_place_of_a_tool_file_is_an_error(tmp_path):
    (tmp_path / "Hero.ztl").mkdir()
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"tool": str(tmp_path / "Hero.ztl")})
    assert e.value.kind == "file"


# --- a folder: the newest project in it -------------------------------------------------------------
def test_a_folder_gives_the_newest_project_by_time(tmp_path):
    make(tmp_path / "Blockout_011.zpr", age=500)
    new = make(tmp_path / "Blockout_012.zpr", age=10)
    make(tmp_path / "Blockout_010.zpr", age=900)
    assert fileitem.resolve({"project": str(tmp_path)}) == ("File:Open", fwd(new))


def test_the_time_wins_over_the_name(tmp_path):
    make(tmp_path / "z_last_by_name.zpr", age=500)
    new = make(tmp_path / "a_first_by_name.zpr", age=10)
    assert fileitem.resolve({"project": str(tmp_path)})[1] == fwd(new)


def test_a_project_saved_after_the_menu_was_loaded_is_found_at_pick_time(tmp_path):
    make(tmp_path / "Blockout_011.zpr", age=100)
    assert fileitem.resolve({"project": str(tmp_path)})[1].endswith("Blockout_011.zpr")
    make(tmp_path / "Blockout_012.zpr", age=1)
    assert fileitem.resolve({"project": str(tmp_path)})[1].endswith("Blockout_012.zpr")


def test_a_tie_picks_the_name_that_sorts_last(tmp_path):
    make(tmp_path / "Blockout_011.zpr", age=5)
    make(tmp_path / "Blockout_012.zpr", age=5)
    make(tmp_path / "Blockout_010.zpr", age=5)
    assert fileitem.resolve({"project": str(tmp_path)})[1].endswith("Blockout_012.zpr")


def test_a_tie_does_not_depend_on_the_case_of_the_names(tmp_path):
    make(tmp_path / "b.zpr", age=5)
    make(tmp_path / "C.ZPR", age=5)
    assert fileitem.resolve({"project": str(tmp_path)})[1].endswith("C.ZPR")


def test_other_files_and_subfolders_are_ignored(tmp_path):
    old = make(tmp_path / "Mine.zpr", age=900)
    make(tmp_path / "newer.ztl", age=1)
    make(tmp_path / "newer.zpr.bak", age=1)
    make(tmp_path / "notes.txt", age=1)
    make(tmp_path / "sub" / "deeper.zpr", age=1)
    (tmp_path / "folder.zpr").mkdir()
    assert fileitem.resolve({"project": str(tmp_path)})[1] == fwd(old)


def test_an_upper_case_extension_counts_in_a_folder(tmp_path):
    make(tmp_path / "Old.zpr", age=500)
    new = make(tmp_path / "New.ZPR", age=5)
    assert fileitem.resolve({"project": str(tmp_path)})[1] == fwd(new)


@pytest.mark.parametrize("path", ["{}/", "{}\\"])
def test_a_trailing_slash_on_the_folder_is_fine(tmp_path, path):
    new = make(tmp_path / "Hero.zpr")
    assert fileitem.resolve({"project": path.format(tmp_path)})[1] == fwd(new)


def test_a_folder_with_a_dot_in_its_name_is_a_folder_when_it_is_there(tmp_path):
    folder = tmp_path / "Blockout.v2"
    new = make(folder / "a.zpr")
    assert fileitem.resolve({"project": str(folder)})[1] == fwd(new)


def test_a_folder_with_no_project_is_an_error(tmp_path):
    make(tmp_path / "Hero.ztl")
    (tmp_path / "sub").mkdir()
    make(tmp_path / "sub" / "deep.zpr")
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"project": str(tmp_path)})
    assert e.value.kind == "empty"


def test_an_empty_folder_is_an_error(tmp_path):
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"project": str(tmp_path)})
    assert e.value.kind == "empty"


def test_a_folder_that_is_not_there_is_an_error(tmp_path):
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"project": str(tmp_path / "Unplugged")})
    assert e.value.kind == "folder" and "Unplugged" in e.value.reason


def test_a_missing_folder_with_a_dot_in_its_name_is_not_there(tmp_path):
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"project": str(tmp_path / "Work" / "v1.3")})
    assert e.value.kind == "folder" and "v1.3" in e.value.reason and "is not there" in e.value.reason


def test_an_existing_file_that_is_not_a_zpr_is_not_a_folder_to_search(tmp_path):
    f = make(tmp_path / "Hero.png")
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"project": str(f)})
    assert e.value.kind == "folder" and "is not a folder" in e.value.reason


def test_describe_says_a_missing_dotted_folder_is_not_there(tmp_path):
    folder = tmp_path / "v1.3"
    assert fileitem.describe({"project": str(folder)}) == f"opens the newest of {fwd(folder)}, not there"


def test_a_folder_that_cannot_be_read_is_an_error(tmp_path, monkeypatch):
    def denied(path):
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(fileitem.os, "scandir", denied)
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"project": str(tmp_path)})
    assert e.value.kind == "folder" and "Access is denied" in e.value.reason


# --- ZBrush 2022-2025 read ANSI -----------------------------------------------------------------------
def test_zbrush_2026_gets_a_name_outside_ascii_as_it_is(tmp_path):
    f = make(tmp_path / "Gr\u00f6\u00dfe.ztl")
    assert fileitem.resolve({"tool": str(f)})[1] == fwd(f)


def test_a_name_the_plugin_cannot_read_is_refused_for_2022_to_2025(tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_file", lambda p: p)       # a volume with no 8.3 names
    f = make(tmp_path / "Gr\u00f6\u00dfe.ztl")
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"tool": str(f)}, legacy=True)
    assert e.value.kind == "name"


def test_a_name_with_a_short_form_is_fine_for_2022_to_2025(tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_file", lambda p: "C:/GRSSE~1.ZTL" if not p.isascii() else p)
    f = make(tmp_path / "Gr\u00f6\u00dfe.ztl")
    assert fileitem.resolve({"tool": str(f)}, legacy=True)[1] == fwd(f)      # the app keeps the real name


def test_a_plain_name_needs_nothing_for_2022_to_2025(tmp_path):
    f = make(tmp_path / "Hero.zpr")
    assert fileitem.resolve({"project": str(f)}, legacy=True)[1] == fwd(f)


def test_a_path_too_long_for_2022_to_2025_is_refused_by_its_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_file", lambda p: p)
    pad = zscript_bridge.MAX_LINE + 1 - len(str(tmp_path / "x" / "Hero.ztl"))
    f = make(tmp_path / ("x" * (1 + pad)) / "Hero.ztl")
    assert len(str(f)) == zscript_bridge.MAX_LINE + 1
    with pytest.raises(fileitem.FileItemError) as e:
        fileitem.resolve({"tool": str(f)}, legacy=True)
    assert e.value.kind == "long" and "255 bytes" in e.value.reason
    assert fileitem.resolve({"tool": str(f)})[1] == fwd(f)        # ZBrush 2026 is not held to it


def test_a_path_of_exactly_the_2022_to_2025_limit_is_fine(tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_file", lambda p: p)
    pad = zscript_bridge.MAX_LINE - len(str(tmp_path / "x" / "Hero.ztl"))
    f = make(tmp_path / ("x" * (1 + pad)) / "Hero.ztl")
    assert len(str(f)) == zscript_bridge.MAX_LINE
    assert fileitem.resolve({"tool": str(f)}, legacy=True)[1] == fwd(f)


# --- the app ----------------------------------------------------------------------------------------
def test_the_pick_becomes_the_general_file_action_for_a_tool(app, tmp_path):
    f = make(tmp_path / "Hero.ztl")
    app.send(tool_item(f))
    assert request(app)["actions"] == [{"filepress": "Tool:Load Tool", "file": fwd(f)}]
    assert app.toasts == []


def test_the_pick_becomes_the_general_file_action_for_a_project(app, tmp_path):
    f = make(tmp_path / "Hero.zpr")
    app.send(project_item(f))
    assert request(app)["actions"] == [{"filepress": "File:Open", "file": fwd(f)}]


def test_a_project_folder_sends_the_newest_project(app, tmp_path):
    make(tmp_path / "Blockout_011.zpr", age=60)
    new = make(tmp_path / "Blockout_012.zpr", age=1)
    app.send(project_item(tmp_path))
    assert request(app)["actions"] == [{"filepress": "File:Open", "file": fwd(new)}]
    new.unlink()                                                # picked again later: whatever is newest then
    app.send(project_item(tmp_path))
    assert request(app)["actions"][0]["file"].endswith("Blockout_011.zpr")


def test_both_in_steps_go_out_in_order(app, tmp_path):
    t, p = make(tmp_path / "Hero.ztl"), make(tmp_path / "Hero.zpr")
    steps = config.Item(label="Both", kind="steps", data={"steps": [
        {"press": "Tool:Masking:Clear"}, {"tool": str(t)}, {"project": str(p)}]})
    app.send(steps)
    assert request(app)["actions"] == [{"press": "Tool:Masking:Clear"},
                                       {"filepress": "Tool:Load Tool", "file": fwd(t)},
                                       {"filepress": "File:Open", "file": fwd(p)}]


def test_the_request_text_for_zbrush_2022_to_2025_names_button_and_file(app, tmp_path):
    t, p = make(tmp_path / "Hero.ztl"), make(tmp_path / "Hero.zpr")
    app._legacy_installed = lambda: True
    app.send(config.Item(label="Both", kind="steps", data={"steps": [{"tool": str(t)}, {"project": str(p)}]}))
    lines = (app.tmpdata / "request.txt").read_text(encoding="mbcs").splitlines()
    assert lines[3:8] == ["file", "Tool:Load Tool", fwd(t), "file", "File:Open"] and lines[8] == fwd(p)


def test_zbrush_2022_to_2025_in_front_gets_a_checked_name(app, tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_file", lambda p: p)
    f = make(tmp_path / "Gr\u00f6\u00dfe.zpr")
    app.send(project_item(f), install={"python": False, "name": "ZBrush 2024", "path": "C:/zb"})
    assert app.toasts == [radiald.MSG_FILE_NAME]
    assert not (app.tmpdata / "request.json").exists() and not (app.tmpdata / "request.txt").exists()


def test_a_path_too_long_for_2022_to_2025_sends_nothing_and_says_so(app, tmp_path, monkeypatch):
    monkeypatch.setattr(zscript_bridge, "ascii_file", lambda p: p)
    pad = zscript_bridge.MAX_LINE + 1 - len(str(tmp_path / "x" / "Hero.ztl"))
    f = make(tmp_path / ("x" * (1 + pad)) / "Hero.ztl")
    app.send(tool_item(f), install={"python": False, "name": "ZBrush 2024", "path": "C:/zb"})
    assert app.toasts == [radiald.MSG_FILE_LONG]
    assert not (app.tmpdata / "request.json").exists()


def test_a_file_that_is_not_there_sends_nothing_and_says_so(app, tmp_path):
    app.send(tool_item(tmp_path / "Gone.ztl"))
    assert app.toasts == [radiald.MSG_FILE_MISSING]
    assert not (app.tmpdata / "request.json").exists() and not (app.tmpdata / "request.txt").exists()
    [(seq, it, route, sent, source, menu, reason)] = app.notes
    assert (route, sent) == ("none", False) and "Gone.ztl" in reason


def test_a_project_that_is_not_there_sends_nothing_and_says_so(app, tmp_path):
    app.send(project_item(tmp_path / "Gone.zpr"))
    assert app.toasts == [radiald.MSG_FILE_MISSING] and not (app.tmpdata / "request.json").exists()


def test_a_folder_that_is_not_there_sends_nothing_and_says_so(app, tmp_path):
    app.send(project_item(tmp_path / "Unplugged"))
    assert app.toasts == [radiald.MSG_FOLDER_MISSING] and not (app.tmpdata / "request.json").exists()


def test_a_folder_with_no_project_sends_nothing_and_says_so(app, tmp_path):
    make(tmp_path / "Hero.ztl")
    app.send(project_item(tmp_path))
    assert app.toasts == [radiald.MSG_NO_PROJECT] and not (app.tmpdata / "request.json").exists()
    [(seq, it, route, sent, source, menu, reason)] = app.notes
    assert (route, sent) == ("none", False) and "no .zpr" in reason


def test_a_failure_part_way_through_steps_sends_none_of_them_and_says_it_once(app, tmp_path):
    t = make(tmp_path / "Hero.ztl")
    steps = config.Item(label="Both", kind="steps", data={"steps": [
        {"press": "Tool:Masking:Clear"}, {"tool": str(t)}, {"project": str(tmp_path / "Gone.zpr")},
        {"tool": str(tmp_path / "Gone2.ztl")}]})
    app.send(steps)
    assert app.toasts == [radiald.MSG_FILE_MISSING]
    assert not (app.tmpdata / "request.json").exists() and not (app.tmpdata / "request.txt").exists()
    assert len(app.notes) == 1


def test_a_stale_request_is_left_alone_when_the_pick_is_refused(app, tmp_path):
    (app.tmpdata / "request.json").write_text("{}")             # an earlier pick, still waiting
    app.send(tool_item(tmp_path / "Gone.ztl"))
    assert (app.tmpdata / "request.json").read_text() == "{}"
    assert app.toasts == [radiald.MSG_FILE_MISSING]


def test_these_picks_do_not_count_in_recent_or_the_auto_slots(app, tmp_path, monkeypatch):
    recorded = []
    monkeypatch.setattr(app.usage, "record_pick", lambda *a: recorded.append(a))
    monkeypatch.setattr(app.usage, "record", lambda *a: recorded.append(a))
    for it in (tool_item(tmp_path / "a.ztl"), project_item(tmp_path / "a.zpr")):
        app._record_pick(it)
        assert app._known_item(it) is it
    assert recorded == []


@pytest.mark.parametrize("result", ["file Tool:Load Tool: ok, file D:/FAILED/Hero.ztl",
                                    "file File:Open: ok, file D:/Projects/FAILED/Hero.zpr"])
def test_a_file_in_a_folder_named_failed_is_not_a_failure(result):
    assert radiald._problems(result) == []


def test_a_button_zbrush_does_not_have_is_reported(app):
    assert radiald._problems("file File:Open: no such interface item") == ["File:Open is not a ZBrush button"]


def test_check_lists_the_items_with_what_they_open(tmp_path, capsys):
    folder = tmp_path / "Blockout"
    make(folder / "Blockout_001.zpr")
    cfg = tmp_path / "radial.json"
    cfg.write_text(json.dumps({"menus": {"main": {"hotkey": "Q", "items": [
        {"tool": str(tmp_path / "Hero.ztl")}, {"project": str(tmp_path / "Hero.zpr"), "label": "Old"},
        {"project": str(folder)}, {"project": str(tmp_path / "Unplugged")}, {"brush": "Standard"}]}}}),
        encoding="utf-8")
    assert radiald.check(str(cfg)) == 0
    out = capsys.readouterr().out
    assert f"tool    Hero  (loads {fwd(tmp_path)}/Hero.ztl, not there)" in out
    assert f"project Old  (opens {fwd(tmp_path)}/Hero.zpr, not there)" in out
    assert f"project Blockout  (opens the newest of {fwd(folder)}: Blockout_001.zpr)" in out
    assert f"project Unplugged  (opens the newest of {fwd(tmp_path)}/Unplugged, not there)" in out
