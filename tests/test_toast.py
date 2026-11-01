"""toast.py's image (no window) and radiald's reading of the plugin's result from bridge.log."""
import os
import time

import pytest

import radiald
import theme
import toast

SEGOE = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segoeui.ttf")
needs_fonts = pytest.mark.skipif(not os.path.isfile(SEGOE), reason="needs the Windows fonts folder")


def pixels(im):
    data = im.tobytes()
    return list(zip(data[0::4], data[1::4], data[2::4], data[3::4]))


# --- the image ---------------------------------------------------------------------------------
@needs_fonts
def test_render_makes_a_short_pill_with_text_pixels():
    im = toast.render("This slot is empty", 1.0)
    assert im.mode == "RGBA"
    assert 80 < im.width < toast.MAX_W and 16 < im.height < 60
    px = pixels(im)
    assert any(p[3] > 0 and p[0] < 60 for p in px)                       # the dark pill
    assert any(p[3] > 200 and p[0] > 200 and p[1] > 200 for p in px)     # light text on it
    assert im.getpixel((0, 0))[3] == 0                                   # rounded: the corner is clear


@needs_fonts
def test_render_scales_with_the_monitor():
    one, two = toast.render("Menus reloaded", 1.0), toast.render("Menus reloaded", 2.0)
    assert two.width == pytest.approx(one.width * 2, abs=4)
    assert two.height == pytest.approx(one.height * 2, abs=4)


@needs_fonts
def test_render_cuts_a_long_message_short():
    im = toast.render("word " * 200, 1.0)
    assert im.width <= toast.MAX_W + 2


@needs_fonts
def test_render_uses_the_given_colour():
    im = toast.render("Menus reloaded", 1.0, colour="#00ff00")
    assert any(p[3] > 200 and p[1] > 200 and p[0] < 80 for p in pixels(im))


@needs_fonts
def test_render_takes_the_pill_of_the_theme_and_is_dark_by_default():
    light = theme.preset("light")["toast"]
    on_light = toast.render("Menus reloaded", 1.0, colour=light["text"], pill=light["pill"])
    on_dark = toast.render("Menus reloaded", 1.0)
    for im, bright in ((on_light, True), (on_dark, False)):
        red, green, blue, alpha = im.getpixel((4, im.height // 2))      # left of the text, on the pill
        assert alpha > 200 and (min(red, green, blue) > 200) == bright and (max(red, green, blue) < 60) != bright


def test_show_logs_and_does_not_raise_when_it_cannot_draw(monkeypatch):
    logs = []
    monkeypatch.setattr(toast, "render", lambda *a, **k: 1 / 0)
    monkeypatch.setattr(toast.W, "cursor_pos", lambda: (10, 10))
    monkeypatch.setattr(toast.W, "monitor_for_point", lambda x, y: (None, 1.0))
    toast.show("x", logs.append)
    assert logs and "toast failed" in logs[0]


# --- bridge.log --------------------------------------------------------------------------------
def stamp(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


@pytest.fixture
def bridge_log(tmp_path):
    path = tmp_path / "bridge.log"

    def write(*lines, raw=None):
        path.write_text(raw if raw is not None else "\n".join(lines) + "\n", encoding="utf-8")
        return str(path)
    return write


def test_a_pick_that_worked_has_no_problems(bridge_log):
    now = time.time()
    p = bridge_log(f"{stamp(now)} #7 'Clay Buildup' via listener: brush Clay Buildup: selected")
    assert radiald._plugin_result(7, now, p) == []


def test_a_failed_action_gives_the_general_message(bridge_log):
    now = time.time()
    p = bridge_log(f"{stamp(now)} #3 'X' via listener: {{'press': 'a'}}: FAILED KeyError: 'a'")
    assert radiald._plugin_result(3, now, p) == [radiald.MSG_PICK_FAILED]


def test_an_asset_that_was_not_loaded_is_named(bridge_log):
    now = time.time()
    p = bridge_log(f"{stamp(now)} #4 'Nope' via listener: brush Nope: NOT loaded in ZBrush and no file known")
    assert radiald._plugin_result(4, now, p) == ["Nope could not be found in ZBrush"]


def test_a_missing_button_is_named_with_its_path(bridge_log):
    now = time.time()
    p = bridge_log(f"{stamp(now)} #5 'Hide' via listener, after stroke: press Tool:Subtool:Nothing: no such interface item")
    assert radiald._plugin_result(5, now, p) == ["Tool:Subtool:Nothing is not a ZBrush button"]


def test_only_the_failing_part_of_a_pick_with_several_actions_counts(bridge_log):
    now = time.time()
    p = bridge_log(f"{stamp(now)} #6 'Combo' via listener: brush A: selected; alpha B: NOT loaded in ZBrush and no "
                   f"file known; press Tool:X: ok (selected after the pick: Brush:A)")
    assert radiald._plugin_result(6, now, p) == ["B could not be found in ZBrush"]


def test_no_line_for_the_pick_yet_is_none(bridge_log):
    now = time.time()
    p = bridge_log(f"{stamp(now)} #1 'A' via listener: brush A: selected")
    assert radiald._plugin_result(2, now, p) is None
    assert radiald._plugin_result(2, now, p + ".missing") is None


def test_a_line_from_an_older_run_with_the_same_number_is_ignored(bridge_log):
    now = time.time()
    p = bridge_log(f"{stamp(now - 3600)} #1 'Old' via listener: brush Old: NOT loaded in ZBrush and no file known")
    assert radiald._plugin_result(1, now, p) is None


def test_only_the_last_4_kb_are_read_and_the_newest_line_wins(bridge_log):
    now = time.time()
    old = f"{stamp(now)} #9 'Old' via listener: brush Old: NOT loaded in ZBrush and no file known\n"
    filler = "".join(f"{stamp(now)} other line {i} " + "x" * 60 + "\n" for i in range(150))
    new = f"{stamp(now)} #9 'New' via listener: brush New: selected\n"
    p = bridge_log(raw=old + filler + new)
    assert os.path.getsize(p) > 8192
    assert radiald._plugin_result(9, now, p) == []
    p = bridge_log(raw=old + filler)                       # the failing line is beyond the tail
    assert radiald._plugin_result(9, now, p) is None
