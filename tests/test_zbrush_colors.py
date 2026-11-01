"""Match ZBrush: reading the colour scheme ZBrush stores, choosing which ZBrush's, and the theme made from it.
The files here are built byte by byte in the layout tools/icolors_probe.py found; no ZBrush file is used."""
import os
import struct
import time

import pytest

import theme
import zbrush_colors as Z

STOCK = {"main": (36, 36, 36), "main2": (40, 40, 40), "bt1": (68, 68, 68), "sw1": (255, 119, 0),
         "k1": (241, 112, 0), "text1": (78, 78, 78), "text2": (233, 236, 235), "palette1": (62, 62, 62),
         "palette2": (62, 62, 62), "border2": (44, 44, 44)}
WARM = {"main": (19, 9, 9), "main2": (21, 14, 14), "bt1": (23, 18, 18), "sw1": (255, 104, 0), "k1": (0, 162, 255),
        "text1": (78, 78, 78), "text2": (236, 238, 238), "palette1": (67, 67, 67), "palette2": (3, 3, 3),
        "border2": (29, 27, 27)}


def pack(rgb):
    r, g, b = rgb
    return r + g / 256 + b / 65536


def scheme_bytes(colours=None, count=57, lead=b"\x10\x27\x00\x00\x03\x00\x00\x00junk before the block", tail=b""):
    """A UI colours chunk: the tag, 2 bytes, a length, 10 shading floats, the count, then the colours."""
    values = [(128, 128, 128)] * count
    for name, rgb in (colours or {}).items():
        values[Z.PATCHES[name]] = rgb
    body = struct.pack("<10f", *([0.5] * 10)) + struct.pack("<I", count) + struct.pack(f"<{count}f", *map(pack, values))
    return lead + Z.TAG + b"\x01\x00" + struct.pack("<I", len(body)) + body + tail


@pytest.fixture
def zb(tmp_path, monkeypatch):
    """PUBLIC and APPDATA in tmp_path, no ZBrush running; store(year, colours, where, age) writes a scheme file."""
    monkeypatch.setenv("PUBLIC", str(tmp_path / "Public"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.setattr(Z, "running_year", lambda: None)
    Z._reset()

    def store(year, colours, where="public", age=0.0, data=None):
        if where == "public":
            folder = tmp_path / "Public" / "Documents" / f"ZBrushData{year}" / "ZStartup"
        else:
            folder = tmp_path / "Roaming" / "Maxon" / f"ZBrush {year}_0C9212BE" / "ZStartup" / "UserInterfaceLayouts"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"CustomUserInterface{year}.cfg"
        path.write_bytes(data if data is not None else scheme_bytes(colours))
        t = time.time() - age
        os.utime(path, (t, t))
        Z._reset()
        return path
    yield store
    Z._reset()


# --- decoding -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("count", [56, 57])
def test_the_colours_are_read_after_any_leading_bytes(count):
    got = Z.decode(scheme_bytes(WARM, count=count))
    assert len(got) == count
    for name, rgb in WARM.items():
        assert got[Z.PATCHES[name]] == rgb


def test_every_8_bit_value_survives_the_packing():
    colours = {"main": (255, 255, 255), "main2": (0, 0, 0), "bt1": (1, 2, 3), "bt2": (254, 1, 255), "bt3": (0, 255, 0)}
    got = Z.decode(scheme_bytes(colours))
    for name, rgb in colours.items():
        assert got[Z.PATCHES[name]] == rgb


@pytest.mark.parametrize("data", [b"", b"no tag here at all", Z.TAG + b"\x00" * 20,
                                  scheme_bytes(count=12), scheme_bytes(count=500)[:200]])
def test_files_without_a_colour_block_give_none(data):
    assert Z.decode(data) is None


def test_a_count_running_past_the_end_gives_none():
    data = scheme_bytes(STOCK)
    assert Z.decode(data[:-20]) is None


def test_a_stray_tag_before_the_real_one_is_skipped():
    assert Z.decode(scheme_bytes(WARM, lead=b"xx" + Z.TAG + b"\xff" * 60))[0] == WARM["main"]


# --- which ZBrush ---------------------------------------------------------------------------------------------------

def test_no_stored_scheme_is_none_and_match_zbrush_is_dark(zb):
    assert Z.current() is None
    assert theme.effective("zbrush") == "dark"
    assert theme.preset("zbrush") is theme.PRESETS["dark"]
    assert theme.signature.__call__  # exists
    assert theme.source() is None


def test_the_newest_version_wins_over_a_more_recently_stored_older_one(zb):
    zb(2022, STOCK, age=0)                     # stored just now
    zb(2026, WARM, age=86400 * 400)            # stored long ago
    s = Z.current()
    assert s.year == 2026 and s.get("main") == WARM["main"]


def test_the_running_zbrush_wins_over_a_newer_version(zb, monkeypatch):
    zb(2022, STOCK)
    zb(2026, WARM)
    monkeypatch.setattr(Z, "running_year", lambda: 2022)
    Z._reset()
    assert Z.current().year == 2022


def test_a_running_zbrush_with_no_stored_scheme_falls_back_to_the_newest(zb, monkeypatch):
    zb(2026, WARM)
    monkeypatch.setattr(Z, "running_year", lambda: 2027)
    Z._reset()
    assert Z.current().year == 2026


def test_of_one_versions_two_copies_the_one_stored_last_is_used(zb):
    zb(2026, STOCK, where="public", age=100)
    zb(2026, WARM, where="appdata", age=0)
    assert Z.current().get("main") == WARM["main"]


def test_a_file_that_does_not_decode_gives_way_to_the_next(zb):
    zb(2026, None, data=b"not a scheme")
    zb(2025, WARM)
    assert Z.current().year == 2025


def test_a_new_store_is_seen_and_changes_the_signature(zb, tmp_path, monkeypatch):
    path = zb(2026, STOCK)
    (tmp_path / "studio.json").write_text('{"theme": "zbrush"}', encoding="utf-8")
    first = theme.signature(str(tmp_path / "studio.json"))
    assert first[0] == "zbrush" and first[1]
    path.write_bytes(scheme_bytes(WARM))       # Store Config again, other colours; no new glob needed
    second = theme.signature(str(tmp_path / "studio.json"))
    assert second[0] == "zbrush" and second[1] != first[1]
    assert theme.ring_colors("zbrush")["bg"] == "#171212"


# --- the theme made from it -----------------------------------------------------------------------------------------

HEX = "#%02x%02x%02x"


def test_a_dark_scheme_maps_onto_the_dark_base(zb):
    zb(2026, WARM)
    p = theme.preset("zbrush")
    assert p["base"] == "dark" and p["label"] == "ZBrush 2026"
    assert p["ring"]["colors"] == {"bg": HEX % WARM["bt1"], "accent": HEX % WARM["sw1"], "highlight": HEX % WARM["k1"],
                                   "text": HEX % WARM["text2"], "lines": HEX % WARM["sw1"]}
    assert p["ring"]["pill"] == theme.PRESETS["dark"]["ring"]["pill"]
    assert p["window"] == {"background": HEX % WARM["main"], "dwm_dark": 1, "border": HEX % WARM["border2"]}
    assert p["toast"]["pill"] == WARM["main2"] + (235,)
    web = p["web"]
    assert web["--bg1"] == HEX % WARM["main"] and web["--bg0"] == HEX % WARM["palette2"]
    assert web["--accent"] == HEX % WARM["sw1"] and web["--cyan"] == HEX % WARM["k1"]


def test_the_presets_keep_one_shape(zb):
    zb(2026, WARM)
    keys = lambda d: {k: keys(v) if isinstance(v, dict) and k != "web" else None for k, v in d.items()}   # noqa: E731
    assert keys(theme.preset("zbrush")) == keys(theme.PRESETS["dark"]) == keys(theme.PRESETS["light"])


def test_a_light_scheme_maps_onto_the_light_base(zb):
    zb(2026, {"main": (220, 220, 220), "bt1": (240, 240, 240), "text2": (20, 20, 20), "sw1": (180, 60, 10),
              "palette2": (200, 200, 200)})
    p = theme.preset("zbrush")
    assert p["base"] == "light" and p["window"]["dwm_dark"] == 0
    assert p["ring"]["pill"] == theme.PRESETS["light"]["ring"]["pill"]
    assert p["web"]["--bg0"] == "#c8c8c8"                     # darker than Main, as the light base's deepest panel is


def test_unreadable_text_falls_back_to_text1_then_to_the_base(zb):
    zb(2026, dict(WARM, text2=(25, 20, 20)))                  # Text2 almost the button colour
    assert theme.ring_colors("zbrush")["text"] == HEX % WARM["text1"] or \
        theme.ring_colors("zbrush")["text"] == theme.PRESETS["dark"]["ring"]["colors"]["text"]
    zb(2026, dict(WARM, text1=(25, 20, 20), text2=(25, 20, 20)))
    assert theme.ring_colors("zbrush")["text"] == theme.PRESETS["dark"]["ring"]["colors"]["text"]


def test_a_highlight_the_same_hue_as_the_accent_takes_the_bases(zb):
    zb(2022, STOCK)                                           # stock ZBrush: switches and K1 both orange
    assert theme.ring_colors("zbrush")["highlight"] == theme.PRESETS["dark"]["ring"]["colors"]["highlight"]


def test_every_ring_and_web_text_reads_on_what_it_sits_on(zb):
    zb(2026, WARM)
    p = theme.preset("zbrush")
    ring = p["ring"]["colors"]
    assert theme.contrast(ring["text"], theme._rgb(ring["bg"]) + (255,)) >= 4.5
    assert theme.contrast(p["toast"]["text"], p["toast"]["pill"]) >= 4.5
    web = p["web"]
    for bg in ("--bg1", "--bg3"):
        assert theme.contrast(web["--text"], theme._rgb(web[bg]) + (255,)) >= 4.5
        assert theme.contrast(web["--sub"], theme._rgb(web[bg]) + (255,)) >= 4.5
    assert theme.contrast(web["--on-accent"], theme._rgb(web["--accent"]) + (255,)) >= 4.5


def test_config_takes_the_zbrush_colours_as_defaults_and_the_file_still_wins(zb, radial_file):
    import config
    zb(2026, WARM)
    path = radial_file({"ring": {"colors": {"accent": "#123456"}},
                        "menus": {"m": {"title": "M", "hotkey": "Q", "items": [{"brush": "Move"}]}}})
    cfg = config.load(path, theme="zbrush")
    assert cfg.ring["theme"] == "zbrush"
    assert cfg.ring["colors"]["bg"] == HEX % WARM["bt1"] and cfg.ring["colors"]["accent"] == "#123456"
