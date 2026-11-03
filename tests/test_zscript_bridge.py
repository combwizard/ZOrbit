"""zscript_bridge.py: the request file ZScript reads, bridge.cfg, and installing the plugin for ZBrush 2022-2025."""
import os
import subprocess

import pytest

import paths
import zscript_bridge as zb

BAD = "\U0001F600"          # outside every ANSI code page


def make_zbrush(root, name="ZBrush 2024"):
    """A fake installation folder with ZBrush.exe; returns (install path, its ZPlugs64)."""
    install = root / name
    plugs = install / "ZStartup" / "ZPlugs64"
    plugs.mkdir(parents=True)
    (install / "ZBrush.exe").write_bytes(b"")
    return str(install), str(plugs)


@pytest.fixture
def fake_build(tmp_path, monkeypatch):
    """A compiled plugin to ship, a staging folder in tmp, and fixed launch commands."""
    zsc = tmp_path / "ZOrbitBridge.zsc"
    zsc.write_bytes(b"compiled")
    monkeypatch.setattr(zb, "bundled", lambda: str(zsc))
    monkeypatch.setattr(zb, "STAGE_DIR", str(tmp_path / "stage"))
    monkeypatch.setattr(paths, "launch_commands",
                        lambda: {"app": ["C:/x/app.exe", "--a"], "studio": ["C:/x/app.exe", "--s"], "popout": []})
    return zsc


def shortcuts_ok(monkeypatch):
    def make(path, argv):
        open(path, "wb").close()
    monkeypatch.setattr(zb, "_make_shortcut", make)


def shortcuts_fail(monkeypatch, exc):
    def make(path, argv):
        raise exc
    monkeypatch.setattr(zb, "_make_shortcut", make)


def bad_cfg(monkeypatch):
    monkeypatch.setattr(zb, "cfg_lines", lambda d=None: ["ZORBIT 1", f"C:\\Data{BAD}\\", "app", "studio", "1"])


# --- request.txt ---------------------------------------------------------------------------------
def test_request_lines_per_action_kind():
    lines = zb.request_lines(7, "Clay\nBuildup", [
        {"brush": "ClayBuildup", "file": "C:/b/ClayBuildup.ZBP"},
        {"alpha": "Alpha 01"},
        {"press": "Tool:Move"},
        {"set": "Draw:Draw Size", "value": 32.0},
        {"set": "Draw:Z Intensity", "value": 12.5},
        {"toggle": "Transform:Edit"},
        {"unknown": 1},
    ])
    assert lines == ["ZORBIT 1", "7", "Clay Buildup",
                     "brush", "ClayBuildup", "C:/b/ClayBuildup.ZBP",
                     "alpha", "Alpha 01", "-",
                     "press", "Tool:Move",
                     "set", "Draw:Draw Size", "32",
                     "set", "Draw:Z Intensity", "12.5",
                     "toggle", "Transform:Edit"]


def test_request_lines_name_an_asset_by_its_button():
    # An imported item's button is named after its file: the plugin looks for Alpha:<that>, not the menu name.
    lines = zb.request_lines(1, "Rock", [
        {"alpha": "Rock Cliff", "file": "C:/a/RockCliff_01.psd", "button": "RockCliff_01"},
        {"texture": "Bark", "file": None},
    ])
    assert lines[3:] == ["alpha", "RockCliff_01", "C:/a/RockCliff_01.psd", "texture", "Bark", "-"]


def test_request_lines_empty_label_and_value_become_a_dash():
    lines = zb.request_lines(1, "", [{"set": "A:B", "value": ""}])
    assert lines == ["ZORBIT 1", "1", "-", "set", "A:B", "-"]


def test_encode_reports_code_page_problem():
    data, problems = zb.encode(["plain", f"x{BAD}"])
    assert len(problems) == 1 and "code page" in problems[0]
    assert data.startswith(b"plain\n") and data.endswith(b"\n")


def test_encode_reports_the_255_limit():
    _, ok = zb.encode(["a" * 255])
    _, too_long = zb.encode(["a" * 256])
    assert ok == []
    assert len(too_long) == 1 and "255" in too_long[0]


def test_write_request_is_atomic_and_returns_problems(tmp_path, monkeypatch):
    target = tmp_path / "request.txt"
    monkeypatch.setattr(zb, "REQUEST_TXT", str(target))
    assert zb.write_request(3, "Pick", [{"press": "Tool:Move"}]) == []
    assert target.read_bytes() == b"ZORBIT 1\n3\nPick\npress\nTool:Move\n"
    assert not (tmp_path / "request.txt.tmp").exists()
    assert zb.write_request(4, BAD, []) != []


# --- bridge.cfg ----------------------------------------------------------------------------------
def test_cfg_lines_with_a_fake_data_dir(monkeypatch):
    monkeypatch.setattr(paths, "launch_commands",
                        lambda: {"app": ["C:/x y/app.exe", "--a"], "studio": ["C:/x/s.exe"], "popout": []})
    lines = zb.cfg_lines("C:\\Users\\you\\AppData\\Local\\ZOrbit")
    assert lines == ["ZORBIT 1", "C:\\Users\\you\\AppData\\Local\\ZOrbit\\", '"C:/x y/app.exe" --a',
                     "C:/x/s.exe", "1"]


def test_cfg_problem_names_the_data_folder():
    assert zb.cfg_problem("C:\\Data\\ZOrbit") is None
    msg = zb.cfg_problem(f"C:\\Data{BAD}\\ZOrbit")
    assert "cannot find ZOrbit's data folder" in msg
    assert "8dot3name" in msg and BAD in msg


def test_cfg_problem_for_a_path_over_255():
    assert "longer than 255" in zb.cfg_problem("C:\\" + "d" * 300)


def test_cfg_problem_for_an_app_command(monkeypatch):
    monkeypatch.setattr(paths, "launch_commands",
                        lambda: {"app": [f"C:/{BAD}/app.exe"], "studio": ["C:/x/s.exe"], "popout": []})
    assert "start the app" in zb.cfg_problem("C:\\Data\\ZOrbit")


# --- check_dest ----------------------------------------------------------------------------------
def test_check_dest(tmp_path):
    _, plugs = make_zbrush(tmp_path)
    assert zb.check_dest(plugs) is None
    assert "ZStartup" in zb.check_dest(str(tmp_path / "somewhere"))
    assert "ZStartup" in zb.check_dest("relative\\ZStartup\\ZPlugs64")
    other = tmp_path / "NoExe" / "ZStartup" / "ZPlugs64"
    other.mkdir(parents=True)
    assert "ZBrush.exe" in zb.check_dest(str(other))


# --- remove_from ---------------------------------------------------------------------------------
def test_remove_from_deletes_only_ours(tmp_path):
    dest = tmp_path / "ZPlugs64"
    (dest / zb.DATA).mkdir(parents=True)
    (dest / zb.LEGACY_DATA).mkdir()
    for f in (zb.PLUGIN, zb.LEGACY_PLUGIN, f"{zb.DATA}/{zb.CFG}", f"{zb.DATA}/{zb.NOTE}", f"{zb.DATA}/app.lnk",
              f"{zb.LEGACY_DATA}/{zb.CFG}", f"{zb.LEGACY_DATA}/app.lnk", "Other.zsc", f"{zb.DATA}/mine.txt"):
        (dest / f).write_bytes(b"x")
    zb.remove_from(str(dest), legacy_only=True)
    assert not (dest / zb.LEGACY_PLUGIN).exists() and not (dest / zb.LEGACY_DATA).exists()
    assert (dest / zb.PLUGIN).exists() and (dest / zb.DATA / zb.CFG).exists()
    zb.remove_from(str(dest))
    assert not (dest / zb.PLUGIN).exists() and not (dest / zb.DATA / zb.CFG).exists()
    assert not (dest / zb.DATA / zb.NOTE).exists() and not (dest / zb.DATA / "app.lnk").exists()
    assert (dest / "Other.zsc").exists()
    assert (dest / zb.DATA / "mine.txt").exists()          # a folder that is not empty is left alone


# --- building and status -------------------------------------------------------------------------
def test_status_of_an_empty_folder(tmp_path):
    install, plugs = make_zbrush(tmp_path)
    assert zb.status(install) == {"installed": False, "current": False, "zplugs": plugs}


def test_status_current_with_shortcuts(tmp_path, fake_build, monkeypatch):
    shortcuts_ok(monkeypatch)
    install, plugs = make_zbrush(tmp_path)
    assert zb.build_plugin_files(plugs) is None
    st = zb.status(install)
    assert st["installed"] and st["current"]


def test_status_outdated_when_shortcuts_vanish_without_a_note(tmp_path, fake_build, monkeypatch):
    shortcuts_ok(monkeypatch)
    install, plugs = make_zbrush(tmp_path)
    zb.build_plugin_files(plugs)
    os.remove(os.path.join(plugs, zb.DATA, "app.lnk"))
    st = zb.status(install)
    assert st["installed"] and not st["current"]


@pytest.mark.parametrize("exc", [
    subprocess.CalledProcessError(1, "powershell", stderr=b"Cannot invoke method.\r\nConstrained Language mode"),
    OSError("blocked by AppLocker"),
    subprocess.TimeoutExpired("powershell", 60),
])
def test_missing_shortcuts_are_recorded_and_status_stays_current(tmp_path, fake_build, monkeypatch, exc):
    shortcuts_fail(monkeypatch, exc)
    install, plugs = make_zbrush(tmp_path)
    why = zb.build_plugin_files(plugs)
    assert why and "\n" not in why and len(why) <= 200
    data = os.path.join(plugs, zb.DATA)
    assert not any(f.endswith(".lnk") for f in os.listdir(data))
    assert open(os.path.join(data, zb.NOTE), encoding="utf-8").read() == f"shortcuts: {why}\n"
    assert zb.shortcuts_skipped(plugs) == why
    assert os.path.isfile(os.path.join(plugs, zb.PLUGIN))
    assert zb.status(install)["current"]


def test_failed_shortcut_reason_comes_from_stderr(tmp_path, fake_build, monkeypatch):
    shortcuts_fail(monkeypatch, subprocess.CalledProcessError(1, "ps", stderr=b"  Language   mode \r\n blocks it "))
    _, plugs = make_zbrush(tmp_path)
    assert zb.build_plugin_files(plugs) == "Language mode blocks it"


def test_a_note_saying_ok_does_not_excuse_missing_shortcuts(tmp_path, fake_build, monkeypatch):
    shortcuts_ok(monkeypatch)
    install, plugs = make_zbrush(tmp_path)
    zb.build_plugin_files(plugs)
    os.remove(os.path.join(plugs, zb.DATA, "studio.lnk"))
    assert zb.shortcuts_skipped(plugs) is None
    assert not zb.status(install)["current"]


def test_status_not_current_when_cfg_differs(tmp_path, fake_build, monkeypatch):
    shortcuts_ok(monkeypatch)
    install, plugs = make_zbrush(tmp_path)
    zb.build_plugin_files(plugs)
    with open(os.path.join(plugs, zb.DATA, zb.CFG), "ab") as f:
        f.write(b"extra\n")
    assert not zb.status(install)["current"]


def test_status_of_the_old_plugin_is_installed_but_not_current(tmp_path, fake_build):
    install, plugs = make_zbrush(tmp_path)
    open(os.path.join(plugs, zb.LEGACY_PLUGIN), "wb").close()
    st = zb.status(install)
    assert st["installed"] and not st["current"]


# --- install -------------------------------------------------------------------------------------
def test_install_refuses_a_data_folder_the_plugin_cannot_read(tmp_path, fake_build, monkeypatch):
    install, plugs = make_zbrush(tmp_path)
    bad_cfg(monkeypatch)
    monkeypatch.setattr(zb, "_stage", lambda: pytest.fail("must not stage"))
    res = zb.install(install)
    assert not res["ok"]
    assert "cannot find ZOrbit's data folder" in res["message"] and "fsutil 8dot3name set 0" in res["message"]
    assert not os.path.exists(os.path.join(plugs, zb.PLUGIN))


def test_install_refuses_zbrush_before_2022(tmp_path, fake_build, monkeypatch):
    install, plugs = make_zbrush(tmp_path, "ZBrush 2021")
    monkeypatch.setattr(zb, "_stage", lambda: pytest.fail("must not stage"))
    res = zb.install(install)
    assert res == {"ok": False, "message": "ZBrush 2021 is not supported (2022 or newer)."}


def test_install_copies_everything(tmp_path, fake_build, monkeypatch):
    shortcuts_ok(monkeypatch)
    install, plugs = make_zbrush(tmp_path)
    res = zb.install(install)
    assert res == {"ok": True, "elevated": False, "message": "Installed. Restart ZBrush so it loads the plugin."}
    assert set(os.listdir(os.path.join(plugs, zb.DATA))) == {zb.CFG, zb.NOTE, "app.lnk", "studio.lnk"}
    assert zb.status(install)["current"]


def test_install_without_shortcuts_says_so_and_is_current(tmp_path, fake_build, monkeypatch):
    shortcuts_fail(monkeypatch, subprocess.CalledProcessError(1, "ps", stderr=b"blocked"))
    install, plugs = make_zbrush(tmp_path)
    res = zb.install(install)
    assert res["ok"]
    assert res["message"].startswith("Installed without the start shortcuts (PowerShell is restricted here)")
    assert set(os.listdir(os.path.join(plugs, zb.DATA))) == {zb.CFG, zb.NOTE}
    assert zb.status(install)["current"]


def test_reinstall_with_shortcuts_replaces_an_old_note(tmp_path, fake_build, monkeypatch):
    install, plugs = make_zbrush(tmp_path)
    shortcuts_fail(monkeypatch, OSError("no"))
    zb.install(install)
    shortcuts_ok(monkeypatch)
    res = zb.install(install)
    assert res["message"].startswith("Installed.")
    assert zb.shortcuts_skipped(plugs) is None
    assert os.path.isfile(os.path.join(plugs, zb.DATA, "app.lnk"))


def test_elevated_main_refuses_a_bad_data_folder(tmp_path, fake_build, monkeypatch):
    install, plugs = make_zbrush(tmp_path)
    stage = tmp_path / "zscript_stage"
    stage.mkdir()
    bad_cfg(monkeypatch)
    assert zb.elevated_main(["--zscript-copy", str(stage), plugs]) == 1
    assert "8dot3name" in (stage / "error.txt").read_text(encoding="utf-8")
    assert not os.path.exists(os.path.join(plugs, zb.PLUGIN))


def test_elevated_main_installs_without_shortcuts(tmp_path, fake_build, monkeypatch):
    shortcuts_fail(monkeypatch, OSError("no"))
    install, plugs = make_zbrush(tmp_path)
    stage = tmp_path / "zscript_stage"
    stage.mkdir()
    assert zb.elevated_main(["--zscript-copy", str(stage), plugs]) == 0
    assert zb.shortcuts_skipped(plugs)


# --- the uninstaller's question --------------------------------------------------------------------

def test_installed_in_lists_known_folders_with_the_plugin(tmp_path, monkeypatch):
    a, a_plugs = make_zbrush(tmp_path, "ZBrush 2022")
    b, b_plugs = make_zbrush(tmp_path, "ZBrush 2023")          # no plugin
    c, c_plugs = make_zbrush(tmp_path, "ZBrush 2024")          # the old name, added by hand in Studio
    d, d_plugs = make_zbrush(tmp_path, "ZBrush 2025")          # listed twice, once with another case
    open(os.path.join(a_plugs, zb.PLUGIN), "wb").close()
    open(os.path.join(c_plugs, zb.LEGACY_PLUGIN), "wb").close()
    open(os.path.join(d_plugs, zb.PLUGIN), "wb").close()
    monkeypatch.setattr(zb.installs, "find_installs",
                        lambda: [{"path": a}, {"path": b}, {"path": d}, {"path": d.upper()}])
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "studio.json").write_text('{"zbrush_folders": ["%s", 7]}' % c.replace("\\", "\\\\"), encoding="utf-8")
    monkeypatch.setattr(paths, "CONFIG_DIR", str(cfg))
    assert zb.installed_in() == [a_plugs, d_plugs, c_plugs]


def test_installed_in_without_studio_file(tmp_path, monkeypatch):
    monkeypatch.setattr(zb.installs, "find_installs", lambda: [])
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "missing"))
    assert zb.installed_in() == []


def test_list_main_writes_one_folder_per_line_with_a_bom(tmp_path, monkeypatch):
    a, a_plugs = make_zbrush(tmp_path, "ZBrush 2022")
    open(os.path.join(a_plugs, zb.PLUGIN), "wb").close()
    monkeypatch.setattr(zb, "installed_in", lambda: [a_plugs])
    out = tmp_path / "list.txt"
    assert zb.list_main(["--zscript-list", str(out)]) == 0
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and raw.endswith(b"\r\n")
    assert raw.decode("utf-8-sig").splitlines() == [a_plugs]
    assert zb.list_main(["--zscript-list"]) == 1
    assert zb.list_main(["--zscript-list", str(tmp_path / "no" / "dir" / "x.txt")]) == 1
