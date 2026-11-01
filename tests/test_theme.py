"""The theme setting: what studio.json may say, how "system" asks Windows, and the presets themselves."""
import json
import os
import re

import pytest

import theme


class _Reg:
    """A stand-in for winreg: one value, or an error when the key or value is missing."""
    HKEY_CURRENT_USER = object()
    REG_DWORD = 4

    def __init__(self, value=None, kind=4, error=None):
        self._value, self._kind, self._error = value, kind, error

    def OpenKey(self, root, sub):
        if self._error is not None:
            raise self._error
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def QueryValueEx(self, key, name):
        if self._value is None:
            raise FileNotFoundError(name)
        return self._value, self._kind


@pytest.mark.parametrize("name", ["dark", "light"])
def test_a_preset_name_is_its_own_effective_theme(name):
    assert theme.effective(name) == name


@pytest.mark.parametrize("name", ["blue", "", None, 3, "Dark "])
def test_anything_unknown_is_dark(name):
    assert theme.effective(name) == "dark"


@pytest.mark.parametrize("reg, expected", [
    (_Reg(value=0), "dark"),
    (_Reg(value=1), "light"),
    (_Reg(value=None), "light"),                               # the value is missing
    (_Reg(error=FileNotFoundError("Personalize")), "light"),   # the key is missing
    (_Reg(error=PermissionError("no")), "light"),
    (_Reg(value=0, kind=1), "light"),                          # a string 0 is not the dark switch
])
def test_system_follows_windows_app_mode(monkeypatch, reg, expected):
    monkeypatch.setattr(theme, "winreg", reg)
    assert theme.effective("system") == expected


def test_system_without_a_registry_is_dark(monkeypatch):
    monkeypatch.setattr(theme, "winreg", None)
    assert theme.effective("system") == "dark"


def test_a_missing_file_reads_as_dark(tmp_path):
    assert theme.read_setting(str(tmp_path / "studio.json")) == "dark"


@pytest.mark.parametrize("content", ["{not json", "[1, 2]", '{"theme": 1}', '{"theme": "blue"}',
                                     '{"theme": "Dark"}', '{"mode": "full"}'])
def test_odd_files_read_as_dark(tmp_path, content):
    p = tmp_path / "studio.json"
    p.write_text(content, encoding="utf-8")
    assert theme.read_setting(str(p)) == "dark"


@pytest.mark.parametrize("name", ["light", "system", "dark"])
def test_a_setting_is_read_as_stored(tmp_path, name):
    p = tmp_path / "studio.json"
    p.write_text(json.dumps({"theme": name, "mode": "full"}), encoding="utf-8")
    assert theme.read_setting(str(p)) == name


def test_a_bom_is_fine(tmp_path):
    p = tmp_path / "studio.json"
    p.write_bytes(b'\xef\xbb\xbf{"theme": "light"}')
    assert theme.read_setting(str(p)) == "light"


def test_a_rewritten_file_is_read_again(tmp_path):
    p = tmp_path / "studio.json"
    p.write_text('{"theme": "light"}', encoding="utf-8")
    assert theme.read_setting(str(p)) == "light"
    p.write_text('{"theme": "dark" }', encoding="utf-8")    # the same size and, as a CI runner can, the same time
    os.utime(p, ns=(1, 2))
    assert theme.read_setting(str(p)) == "dark"
    p.write_text('{"theme": "system", "mode": "full"}', encoding="utf-8")
    assert theme.read_setting(str(p)) == "system"
    p.unlink()
    assert theme.read_setting(str(p)) == "dark"


def test_the_default_path_is_studio_json_in_the_config_folder(monkeypatch, tmp_path):
    import paths
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path))
    (tmp_path / "studio.json").write_text('{"theme": "light"}', encoding="utf-8")
    assert theme.read_setting() == "light"
    assert theme.current() == "light"


def test_current_resolves_system(monkeypatch, tmp_path):
    p = tmp_path / "studio.json"
    p.write_text('{"theme": "system"}', encoding="utf-8")
    monkeypatch.setattr(theme, "winreg", _Reg(value=0))
    assert theme.current(str(p)) == "dark"
    monkeypatch.setattr(theme, "winreg", _Reg(value=1))
    assert theme.current(str(p)) == "light"


HEX = re.compile(r"^#[0-9a-f]{6}$")


def _keys(d):
    return {k: _keys(v) if isinstance(v, dict) else None for k, v in d.items()}


def test_every_preset_has_the_same_shape_and_valid_colours():
    assert set(theme.PRESETS) == set(theme.CONCRETE)
    shapes = {name: _keys(p) for name, p in theme.PRESETS.items()}
    assert shapes["dark"] == shapes["light"]
    for p in theme.PRESETS.values():
        for c in p["ring"]["colors"].values():
            assert HEX.match(c), c
        assert set(p["ring"]["colors"]) == {"bg", "accent", "highlight", "text", "lines"}
        for role in ("pill", "hint", "badge"):
            assert len(p["ring"][role]) == 4 and all(0 <= v <= 255 for v in p["ring"][role])
        assert len(p["ring"]["placeholder"]) == 2 and all(len(c) == 3 for c in p["ring"]["placeholder"])
        assert len(p["toast"]["pill"]) == 4 and HEX.match(p["toast"]["text"])
        assert HEX.match(p["window"]["background"]) and HEX.match(p["window"]["border"])
        assert p["window"]["dwm_dark"] in (0, 1)


def test_preset_and_ring_colors_resolve_the_setting(monkeypatch):
    monkeypatch.setattr(theme, "winreg", _Reg(value=1))
    assert theme.preset("system") is theme.PRESETS["light"]
    assert theme.preset("blue") is theme.PRESETS["dark"]
    colours = theme.ring_colors("light")
    assert colours == theme.PRESETS["light"]["ring"]["colors"]
    colours["bg"] = "#000000"                          # a copy: the preset is untouched
    assert theme.PRESETS["light"]["ring"]["colors"]["bg"] == "#f3f4f6"


def test_colorref_is_bgr():
    assert theme.colorref("#2b2f35") == 0x00352F2B
    assert theme.colorref("#ff0000") == 0x0000FF


def test_the_toast_text_reads_on_its_pill():
    for p in theme.PRESETS.values():
        assert theme.contrast(p["toast"]["text"], p["toast"]["pill"]) > 7
    assert theme.contrast("#ffffff", (255, 255, 255, 255)) == pytest.approx(1.0)
