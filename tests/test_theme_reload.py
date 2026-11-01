"""radiald.App reloads the config when the theme changes, and its toast takes the theme's pill."""
import json

import pytest

import paths
import radiald
import theme


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
