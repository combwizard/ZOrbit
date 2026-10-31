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
