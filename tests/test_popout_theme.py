"""The browser window follows the theme: popout_get_state carries it, and show() tells a window that was hidden
while the theme changed. No window is opened; the Popout is built on its options only."""
import json
import os
import struct
import time

import pytest

import popout
import theme
import zbrush_colors


class _Window:
    def __init__(self):
        self.js = []

    def evaluate_js(self, code):
        self.js.append(code)


def _pop(monkeypatch, tmp_path):
    monkeypatch.setattr(popout, "STATE_FILE", str(tmp_path / "popout.json"))
    pop = popout.Popout({"tag": None, "kind": None, "managed": False})
    pop.window = _Window()
    pop.hwnd = 0x1234
    return pop


@pytest.fixture
def frames(monkeypatch):
    calls = []
    monkeypatch.setattr(popout.winframe, "apply_theme", lambda hwnd, window: calls.append((hwnd, window)))
    return calls


def _set(monkeypatch, setting, effective):
    monkeypatch.setattr(theme, "read_setting", lambda path=None: setting)
    monkeypatch.setattr(theme, "current", lambda path=None: effective)


def _arg(code):
    """The JSON the page was called with."""
    start = code.index("__popoutTheme(", code.index("&&")) + len("__popoutTheme(")
    return json.loads(code[start:-1])


def test_get_state_carries_the_theme_and_records_it(monkeypatch, tmp_path):
    pop = _pop(monkeypatch, tmp_path)
    _set(monkeypatch, "system", "light")
    state = popout.PopoutApi(pop).popout_get_state()
    assert state["theme"] == "system" and state["theme_effective"] == "light"
    assert pop._theme_seen == ("system", ("light", ""))


def test_get_state_is_dark_without_a_studio_json(monkeypatch, tmp_path):
    monkeypatch.setattr(theme, "_default_path", lambda: str(tmp_path / "none.json"))
    pop = _pop(monkeypatch, tmp_path)
    state = popout.PopoutApi(pop).popout_get_state()
    assert (state["theme"], state["theme_effective"]) == ("dark", "dark")


def test_sync_does_nothing_while_the_theme_is_unchanged(monkeypatch, tmp_path, frames):
    pop = _pop(monkeypatch, tmp_path)
    _set(monkeypatch, "dark", "dark")
    pop._theme_seen = ("dark", ("dark", ""))
    pop._sync_theme()
    assert pop.window.js == [] and frames == []


def test_sync_tells_the_page_and_the_frame_when_it_changed(monkeypatch, tmp_path, frames):
    pop = _pop(monkeypatch, tmp_path)
    pop._theme_seen = ("dark", ("dark", ""))
    _set(monkeypatch, "light", "light")
    pop._sync_theme()
    assert len(pop.window.js) == 1
    assert pop.window.js[0].startswith("window.__popoutTheme && __popoutTheme(")
    assert _arg(pop.window.js[0]) == {"setting": "light", "effective": "light", "base": "light", "tokens": {}}
    assert frames == [(0x1234, theme.PRESETS["light"]["window"])]
    assert pop._theme_seen == ("light", ("light", ""))
    pop._sync_theme()                                    # once only
    assert len(pop.window.js) == 1 and len(frames) == 1


def test_sync_notices_a_new_setting_with_the_same_effective_theme(monkeypatch, tmp_path, frames):
    pop = _pop(monkeypatch, tmp_path)
    pop._theme_seen = ("dark", ("dark", ""))
    _set(monkeypatch, "system", "dark")
    pop._sync_theme()
    assert _arg(pop.window.js[0]) == {"setting": "system", "effective": "dark", "base": "dark", "tokens": {}}
    assert pop._theme_seen == ("system", ("dark", ""))


def test_sync_runs_when_the_page_was_never_given_a_theme(monkeypatch, tmp_path, frames):
    pop = _pop(monkeypatch, tmp_path)
    _set(monkeypatch, "dark", "dark")
    pop._sync_theme()
    assert len(pop.window.js) == 1


def test_show_syncs_the_theme_before_telling_the_page_to_show(monkeypatch, tmp_path, frames):
    pop = _pop(monkeypatch, tmp_path)
    order = []

    class Stop(Exception):
        pass

    def sync():
        order.append("theme")
        raise Stop                                       # nothing after this touches a real window
    monkeypatch.setattr(pop, "_sync_theme", sync)
    monkeypatch.setattr(pop, "visible", lambda: order.append("visible") or True)
    monkeypatch.setattr(pop, "_remember_target", lambda zb: order.append("target"))
    with pytest.raises(Stop):
        pop.show(tag="x")
    assert order == ["visible", "target", "theme"] and pop.window.js == []


def test_a_failing_page_call_is_logged_and_tried_again(monkeypatch, tmp_path, frames):
    pop = _pop(monkeypatch, tmp_path)
    logged = []
    monkeypatch.setattr(popout, "_log", logged.append)

    def boom(code):
        raise RuntimeError("no page")
    pop.window.evaluate_js = boom
    pop._theme_seen = ("dark", ("dark", ""))
    _set(monkeypatch, "light", "light")
    pop._sync_theme()
    assert pop._theme_seen == ("dark", ("dark", "")) and any("__popoutTheme failed" in m for m in logged)


def test_the_frame_follows_the_page_under_follow_windows(monkeypatch, tmp_path, frames):
    pop = _pop(monkeypatch, tmp_path)
    api = popout.PopoutApi(pop)
    assert api.popout_theme_changed("light") is True
    assert frames == [(0x1234, theme.PRESETS["light"]["window"])]
    assert api.popout_theme_changed("blue") is True      # not a preset: ignored
    assert len(frames) == 1


def test_the_frame_is_left_alone_before_the_window_exists(monkeypatch, tmp_path, frames):
    pop = _pop(monkeypatch, tmp_path)
    pop.hwnd = 0
    assert popout.PopoutApi(pop).popout_theme_changed("light") is True
    assert frames == []


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


def _studio_setting(monkeypatch, tmp_path, name):
    studio = tmp_path / "studio.json"
    studio.write_text(json.dumps({"theme": name}), encoding="utf-8")
    monkeypatch.setattr(theme, "_default_path", lambda: str(studio))


def test_get_state_carries_the_base_and_tokens(monkeypatch, tmp_path, zb):
    zb(WARM)
    _studio_setting(monkeypatch, tmp_path, "zbrush")
    pop = _pop(monkeypatch, tmp_path)
    state = popout.PopoutApi(pop).popout_get_state()
    assert state["theme"] == "zbrush" and state["theme_effective"] == "zbrush" and state["theme_base"] == "dark"
    assert state["theme_tokens"]["--bg1"] == "#130909"
    assert pop._theme_seen == ("zbrush", theme.signature())


def test_get_state_has_no_tokens_for_a_fixed_theme(monkeypatch, tmp_path, zb):
    _studio_setting(monkeypatch, tmp_path, "light")
    state = popout.PopoutApi(_pop(monkeypatch, tmp_path)).popout_get_state()
    assert state["theme_base"] == "light" and state["theme_tokens"] == {}


def test_sync_notices_a_new_scheme_under_the_same_setting(monkeypatch, tmp_path, zb, frames):
    zb(WARM)
    _studio_setting(monkeypatch, tmp_path, "zbrush")
    pop = _pop(monkeypatch, tmp_path)
    popout.PopoutApi(pop).popout_get_state()
    pop._sync_theme()
    assert pop.window.js == [] and frames == []          # nothing stored since the page was given the theme
    zb(COOL)
    pop._sync_theme()
    assert len(pop.window.js) == 1
    arg = _arg(pop.window.js[0])
    assert arg["setting"] == "zbrush" and arg["effective"] == "zbrush" and arg["base"] == "dark"
    assert arg["tokens"]["--bg1"] == "#090e1e"
    assert frames == [(0x1234, theme.preset("zbrush")["window"])]
    pop._sync_theme()                                    # once only
    assert len(pop.window.js) == 1


def test_the_frame_follows_zbrush(monkeypatch, tmp_path, zb, frames):
    zb(WARM)
    pop = _pop(monkeypatch, tmp_path)
    assert popout.PopoutApi(pop).popout_theme_changed("zbrush") is True
    assert frames == [(0x1234, theme.preset("zbrush")["window"])]
