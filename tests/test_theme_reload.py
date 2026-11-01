"""radiald.App reloads the config when the theme changes, and its toast takes the theme's pill."""
import json
import os
import struct
import time

import pytest

import paths
import radiald
import theme
import zbrush_colors


@pytest.fixture
def app(tmp_path, monkeypatch):
    for name in ("_prefetch", "_schedule_prewarm", "_prune_icons"):
        monkeypatch.setattr(radiald.App, name, lambda self: None)
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path))
    radial = tmp_path / "radial.json"
    radial.write_text(json.dumps({"menus": {"a": {"title": "A", "hotkey": "Q", "items": [{"brush": "Move"}]}}}),
                      encoding="utf-8")
    return radiald.App(str(radial))


def set_theme(tmp_path, name):
    (tmp_path / "studio.json").write_text(json.dumps({"theme": name}), encoding="utf-8")


def test_a_theme_change_reloads_the_config_without_the_file_changing(app, tmp_path):
    app.load_config(force=True, balloon=False)
    assert "theme" not in app.cfg.ring
    first = app.cfg
    app.load_config(balloon=False)
    assert app.cfg is first                                    # nothing changed: nothing reloaded
    set_theme(tmp_path, "light")
    app.load_config(balloon=False)
    assert app.cfg is not first and app.cfg.ring["theme"] == "light"
    assert app.cfg.ring["colors"] == theme.ring_colors("light")
    set_theme(tmp_path, "dark")
    app.load_config(balloon=False)
    assert "theme" not in app.cfg.ring


def test_a_broken_file_is_not_loaded_again_for_the_same_theme(app, tmp_path, monkeypatch):
    app.load_config(force=True, balloon=False)
    (tmp_path / "radial.json").write_text("{ not json", encoding="utf-8")
    set_theme(tmp_path, "light")
    calls = []
    real = radiald.C.load
    monkeypatch.setattr(radiald.C, "load", lambda *a, **k: calls.append(k) or real(*a, **k))
    for _ in range(3):
        app.load_config(balloon=False)
    assert len(calls) == 1 and calls[0]["theme"] == "light"


def test_the_toast_takes_the_pill_of_the_theme_and_keeps_its_text_readable(app, monkeypatch):
    shown = []
    monkeypatch.setattr("toast.show", lambda text, log, **k: shown.append(k))
    app.cfg = radiald.C.Config(path=app.cfg_path, mtime=0.0)
    app.cfg.ring["theme"] = "light"
    app.cfg.ring["colors"] = theme.ring_colors("light")
    app._toast("x")
    assert shown[-1]["pill"] == theme.preset("light")["toast"]["pill"] and shown[-1]["colour"] == "#1b1c20"
    app.cfg.ring["colors"] = dict(theme.ring_colors("light"), text="#f0f0f0")     # a dark-theme colour kept under Light
    app._toast("x")
    assert shown[-1]["colour"] == theme.preset("light")["toast"]["text"]
    app.cfg.ring["theme"] = "dark"
    app._toast("x")
    assert shown[-1]["pill"] == theme.preset("dark")["toast"]["pill"] and shown[-1]["colour"] == "#f0f0f0"


# --- Match ZBrush --------------------------------------------------------------------------------------------------

def _scheme_bytes(colours, count=57):
    """A UI colours chunk in the layout tools/icolors_probe.py found: tag, 2 bytes, length, 10 floats, count, colours."""
    values = [(128, 128, 128)] * count
    for name, rgb in colours.items():
        values[zbrush_colors.PATCHES[name]] = rgb
    body = struct.pack("<10f", *([0.5] * 10)) + struct.pack("<I", count)
    body += struct.pack(f"<{count}f", *(r + g / 256 + b / 65536 for r, g, b in values))
    return b"junk before the block" + zbrush_colors.TAG + struct.pack("<H", 1) + struct.pack("<I", len(body)) + body


@pytest.fixture
def zb(tmp_path, monkeypatch):
    """PUBLIC and APPDATA in tmp_path, no ZBrush running; store(colours) writes a stored 2026 scheme."""
    monkeypatch.setenv("PUBLIC", str(tmp_path / "Public"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setattr(zbrush_colors, "running_year", lambda: None)
    zbrush_colors._reset()
    path = tmp_path / "Public" / "Documents" / "ZBrushData2026" / "ZStartup" / "CustomUserInterface2026.cfg"

    def store(colours):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(_scheme_bytes(colours))
        os.utime(path, (time.time(), time.time()))
        zbrush_colors._reset()
    yield store
    zbrush_colors._reset()


WARM = {"main": (19, 9, 9), "bt1": (23, 18, 18), "sw1": (255, 104, 0), "text2": (236, 238, 238), "palette1": (67, 67, 67)}
COOL = {"main": (9, 14, 30), "bt1": (18, 24, 44), "sw1": (0, 200, 255), "text2": (236, 238, 238), "palette1": (40, 50, 80)}


def test_a_new_stored_scheme_reloads_the_config_under_the_same_setting(app, tmp_path, zb):
    zb(WARM)
    set_theme(tmp_path, "zbrush")
    app.load_config(force=True, balloon=False)
    first = app.cfg
    assert first.ring["theme"] == "zbrush" and first.ring["colors"]["bg"] == "#171212"
    app.load_config(balloon=False)
    assert app.cfg is first                                    # nothing changed: nothing reloaded
    zb(COOL)                                                   # Store Config in ZBrush; radial.json untouched
    app.load_config(balloon=False)
    assert app.cfg is not first and app.cfg.ring["colors"]["bg"] == "#12182c"
    again = app.cfg
    app.load_config(balloon=False)
    assert app.cfg is again


def test_the_theme_is_logged_once_with_the_year(app, tmp_path, zb, monkeypatch):
    logged = []
    monkeypatch.setattr(radiald, "log", logged.append)
    zb(WARM)
    set_theme(tmp_path, "zbrush")
    app.load_config(force=True, balloon=False)
    app.load_config(balloon=False)
    zb(COOL)
    app.load_config(balloon=False)
    lines = [m for m in logged if m.startswith("theme:")]
    assert lines == ["theme: zbrush (ZBrush 2026)"] * 2


def test_a_broken_file_is_not_loaded_again_for_the_same_scheme(app, tmp_path, zb, monkeypatch):
    zb(WARM)
    set_theme(tmp_path, "zbrush")
    app.load_config(force=True, balloon=False)
    (tmp_path / "radial.json").write_text("{ not json", encoding="utf-8")
    calls = []
    real = radiald.C.load
    monkeypatch.setattr(radiald.C, "load", lambda *a, **k: calls.append(k) or real(*a, **k))
    for _ in range(3):
        app.load_config(balloon=False)
    assert len(calls) == 1 and calls[0]["theme"] == "zbrush"
    zb(COOL)                                                   # a new scheme is tried once more
    for _ in range(3):
        app.load_config(balloon=False)
    assert len(calls) == 2


def test_zbrush_without_a_stored_scheme_loads_as_dark(app, tmp_path, zb):
    set_theme(tmp_path, "zbrush")
    app.load_config(force=True, balloon=False)
    assert "theme" not in app.cfg.ring
    zb(WARM)                                                   # the first Store Config switches it on
    app.load_config(balloon=False)
    assert app.cfg.ring["theme"] == "zbrush"


def test_the_toast_takes_the_zbrush_pill(app, zb, monkeypatch):
    zb(WARM)
    shown = []
    monkeypatch.setattr("toast.show", lambda text, log, **k: shown.append(k))
    app.cfg = radiald.C.Config(path=app.cfg_path, mtime=0.0)
    app.cfg.ring["theme"] = "zbrush"
    app.cfg.ring["colors"] = theme.ring_colors("zbrush")
    app._toast("x")
    assert shown[-1]["pill"] == theme.preset("zbrush")["toast"]["pill"]
    assert shown[-1]["colour"] == theme.ring_colors("zbrush")["text"]
