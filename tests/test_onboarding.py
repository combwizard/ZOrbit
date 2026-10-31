"""onboarding.register_plugin_path against a fake winreg: the real registry is never touched.

Windows uses the user value of ZBRUSH_PLUGIN_PATH and ignores the machine one, so with no user value yet the new
one has to start from the machine entries (the same rule as RegisterBridge in packaging/installer.iss).
"""
import types

import pytest

import onboarding

REG_SZ, REG_EXPAND_SZ = 1, 2
USER, MACHINE = "HKCU", "HKLM"
BRIDGE = r"C:\Apps\ZOrbit\bridge"


class _Key:
    def __init__(self, root):
        self.root = root

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def reg(monkeypatch):
    """Installs the fake winreg; returns (values, writes). values maps (root, name) to (data, type)."""
    values, writes = {}, []

    def open_key(root, sub, reserved=0, access=0):
        if root == MACHINE and access & ~1:
            raise PermissionError("HKLM is opened read only")
        return _Key(root)

    def query(key, name):
        try:
            return values[(key.root, name)]
        except KeyError:
            raise FileNotFoundError(name) from None

    def set_value(key, name, reserved, regtype, data):
        assert key.root == USER, "only the user value may be written"
        writes.append((name, regtype, data))
        values[(key.root, name)] = (data, regtype)

    fake = types.SimpleNamespace(
        HKEY_CURRENT_USER=USER, HKEY_LOCAL_MACHINE=MACHINE, KEY_READ=1, KEY_SET_VALUE=2,
        REG_SZ=REG_SZ, REG_EXPAND_SZ=REG_EXPAND_SZ,
        OpenKey=open_key, QueryValueEx=query, SetValueEx=set_value)
    monkeypatch.setattr(onboarding, "winreg", fake)
    monkeypatch.setattr(onboarding.W, "broadcast_setting_change", lambda key: None)
    return values, writes


def test_no_user_value_no_machine_value(reg):
    values, writes = reg
    out = onboarding.register_plugin_path(BRIDGE)
    assert out["ok"] and out["changed"]
    assert writes == [("ZBRUSH_PLUGIN_PATH", REG_SZ, BRIDGE)]


def test_no_user_value_starts_from_machine_entries(reg):
    values, writes = reg
    values[(MACHINE, "ZBRUSH_PLUGIN_PATH")] = (r"D:\Shared\Plugins;E:\More;", REG_SZ)
    out = onboarding.register_plugin_path(BRIDGE)
    assert out["ok"] and out["changed"]
    assert writes == [("ZBRUSH_PLUGIN_PATH", REG_SZ, r"D:\Shared\Plugins;E:\More;" + BRIDGE)]
    assert values[(MACHINE, "ZBRUSH_PLUGIN_PATH")] == (r"D:\Shared\Plugins;E:\More;", REG_SZ)    # untouched


def test_user_value_wins_over_machine_value(reg):
    values, writes = reg
    values[(MACHINE, "ZBRUSH_PLUGIN_PATH")] = (r"D:\Shared\Plugins", REG_SZ)
    values[(USER, "ZBRUSH_PLUGIN_PATH")] = (r"F:\Mine", REG_SZ)
    out = onboarding.register_plugin_path(BRIDGE)
    assert out["changed"]
    assert writes == [("ZBRUSH_PLUGIN_PATH", REG_SZ, r"F:\Mine;" + BRIDGE)]      # no machine entry copied in


def test_already_registered_writes_nothing(reg):
    values, writes = reg
    values[(USER, "ZBRUSH_PLUGIN_PATH")] = (r"F:\Mine;c:\apps\zorbit\bridge\;", REG_SZ)
    out = onboarding.register_plugin_path(BRIDGE)
    assert out["ok"] and not out["changed"]
    assert writes == []


def test_registered_in_the_machine_value_writes_nothing(reg):
    values, writes = reg
    values[(MACHINE, "ZBRUSH_PLUGIN_PATH")] = (BRIDGE, REG_SZ)
    out = onboarding.register_plugin_path(BRIDGE)
    assert out["ok"] and not out["changed"]
    assert writes == []


def test_expand_sz_is_kept(reg):
    values, writes = reg
    values[(USER, "ZBRUSH_PLUGIN_PATH")] = (r"%USERPROFILE%\ZPlugins", REG_EXPAND_SZ)
    onboarding.register_plugin_path(BRIDGE)
    assert writes == [("ZBRUSH_PLUGIN_PATH", REG_EXPAND_SZ, r"%USERPROFILE%\ZPlugins;" + BRIDGE)]


def test_expand_sz_machine_value_gives_an_expand_sz_user_value(reg):
    values, writes = reg
    values[(MACHINE, "ZBRUSH_PLUGIN_PATH")] = (r"%ProgramData%\ZPlugins", REG_EXPAND_SZ)
    onboarding.register_plugin_path(BRIDGE)
    assert writes == [("ZBRUSH_PLUGIN_PATH", REG_EXPAND_SZ, r"%ProgramData%\ZPlugins;" + BRIDGE)]


def test_user_value_of_another_type_is_replaced_by_ours(reg):
    values, writes = reg
    values[(USER, "ZBRUSH_PLUGIN_PATH")] = (b"\x00\x01", 3)         # REG_BINARY
    onboarding.register_plugin_path(BRIDGE)
    assert writes == [("ZBRUSH_PLUGIN_PATH", REG_SZ, BRIDGE)]


# --- the why texts of a running ZBrush: they are shown to the user, so each says what to do ----------
def _proc(pid=4000, started=1000.0, age=600.0):
    return {"pid": pid, "started": started, "age": age, "state": "unknown", "evidence": None, "why": ""}


def test_modern_not_registered_says_press_fix(monkeypatch):
    p = _proc()
    onboarding._modern_proc(p, None, False, None)
    assert p["state"] == "not_loaded"
    assert p["why"] == "ZBrush does not know where the plugin is. Press Fix in step 1, then restart ZBrush."


def test_modern_registered_but_not_loaded_says_what_to_try(monkeypatch):
    monkeypatch.setattr(onboarding, "_old_launcher", lambda *a: False)
    p = _proc()
    onboarding._modern_proc(p, None, True, 500.0)
    assert p["state"] == "not_loaded"
    assert p["why"].startswith("ZBrush has not loaded the plugin. Close it completely and start it from the Start menu")
    assert "bridge.log" in p["why"] and "if it exists" in p["why"]
    assert "ZBRUSH_PLUGIN_PATH" not in p["why"]


def test_modern_started_from_an_old_launcher_says_so(monkeypatch):
    monkeypatch.setattr(onboarding, "_old_launcher", lambda *a: True)
    p = _proc()
    onboarding._modern_proc(p, None, True, 500.0)
    assert p["state"] == "not_loaded" and p["evidence"] == "launcher"
    assert "already open" in p["why"] and "Start menu" in p["why"]


def test_modern_started_before_registering_is_a_restart():
    p = _proc(started=1000.0)
    onboarding._modern_proc(p, None, True, 2000.0)
    assert p["state"] == "restart"


def test_modern_live_listener_is_loaded():
    p = _proc(pid=4000)
    onboarding._modern_proc(p, {"pid": 4000, "alive": True, "stale": False}, False, None)
    assert p["state"] == "loaded" and p["evidence"] == "listener"


def test_legacy_not_loaded_names_the_launch_log(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding.paths, "DATA_DIR", str(tmp_path))
    p = _proc()
    onboarding._legacy_proc(p, {"plugin": {"installed": True, "zplugs": str(tmp_path)}})
    assert p["state"] == "not_loaded"
    assert "zscript_launch.log" in p["why"] and "Start menu" in p["why"]


def test_legacy_plugin_missing_says_press_install(tmp_path, monkeypatch):
    monkeypatch.setattr(onboarding.paths, "DATA_DIR", str(tmp_path))
    p = _proc()
    onboarding._legacy_proc(p, {"plugin": {"installed": False, "zplugs": str(tmp_path)}})
    assert p["state"] == "not_loaded" and "Press Install in step 1" in p["why"]


def test_old_launcher_needs_an_older_parent_that_is_not_explorer(monkeypatch):
    times = {10: 400.0, 11: 400.0, 12: 1200.0}
    images = {10: r"C:\Tools\launcher.exe", 11: r"C:\Windows\explorer.exe", 12: r"C:\Tools\later.exe"}
    parents = {4000: 10, 4001: 11, 4002: 12}
    monkeypatch.setattr(onboarding.W, "parent_pid", lambda pid: parents.get(pid))
    monkeypatch.setattr(onboarding.W, "process_created", lambda pid: times.get(pid))
    monkeypatch.setattr(onboarding.W, "process_image", lambda pid: images.get(pid, ""))
    assert onboarding._old_launcher(4000, 1000.0, 500.0) is True
    assert onboarding._old_launcher(4001, 1000.0, 500.0) is False       # Explorer got the new environment
    assert onboarding._old_launcher(4002, 1000.0, 500.0) is False       # the parent is newer than the registration
    assert onboarding._old_launcher(4000, 1000.0, None) is False


def test_elevated_zbrush_counts_as_loaded_only_with_its_own_live_listener(monkeypatch):
    live = {"pid": 4000, "alive": True, "verified": 900.0, "hwnd": 77}
    monkeypatch.setattr(onboarding.W, "window_pid", lambda hwnd: 4000)
    assert onboarding._listener_owned_by(live, 4000) is True
    assert onboarding._listener_owned_by(live, 4001) is False                       # another process
    assert onboarding._listener_owned_by(dict(live, verified=None), 4000) is False
    assert onboarding._listener_owned_by(dict(live, alive=False), 4000) is False
    assert onboarding._listener_owned_by(None, 4000) is False
    monkeypatch.setattr(onboarding.W, "window_pid", lambda hwnd: 999)              # the window belongs to someone else
    assert onboarding._listener_owned_by(live, 4000) is False
