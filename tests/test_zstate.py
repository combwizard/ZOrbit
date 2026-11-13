"""zstate.py: the query the app writes, the snapshot the plugin answers with, the cache, the marks the ring draws and the
conversation between the two (Channel). The sample query and snapshot are the ones in issue #188 (design, section 1);
the plugin's tests parse the same text."""
import json
import os

import pytest

import config as C
import zstate as Z

# The sample query and snapshot of the design, as written there (the elided path in brush_file filled in).
SAMPLE_QUERY = """
{"v": 1, "id": 42, "time": 1762430000.1,
 "paths": [{"p": "Transform:Activate Symmetry", "k": "toggle"},
           {"p": "Draw:Draw Size", "k": "set"}, {"p": "Tool:Masking:Clear", "k": "press"}]}
"""
SAMPLE_SNAPSHOT = """
{"v": 1, "id": 42, "pick": 17, "pid": 9120, "session": "429428",
 "time": 1762430000.13, "ms": 1.9, "truncated": false,
 "extras": {"tool": "SimpleBrush", "brush": "Standard", "brush_file": "C:/Users/u/ZBrush/Standard.zbp",
            "material": "MatCap Red Wax", "edit": true, "edit_enabled": true},
 "items": {"Transform:Activate Symmetry": {"s": "ok", "v": 1.0},
           "Draw:Draw Size": {"s": "ok", "v": 64.0, "min": 1.0, "max": 1000.0},
           "Tool:Masking:Clear": {"s": "missing"}}}
"""
SYM, SIZE, CLEAR = "Transform:Activate Symmetry", "Draw:Draw Size", "Tool:Masking:Clear"


# --- menus ----------------------------------------------------------------------------------------------------------
def press(path):
    return C.Item(label=path.split(":")[-1], kind="press", data={"press": path})


def toggle(path):
    return C.Item(label=path.split(":")[-1], kind="toggle", data={"toggle": path})


def setv(path, value):
    return C.Item(label=f"{path.split(':')[-1]} {value}", kind="set", data={"set": path, "value": value})


def sub(mid):
    return C.Item(label=mid, kind="menu", data={"menu": mid})


def brush(name):
    return C.Item(label=name, kind="brush", data={"brush": name})


def menu(mid, *items, fan=False):
    return C.Menu(id=mid, title=mid, items=list(items), fan=fan)


def resolver(*menus):
    by_id = {m.id: m for m in menus}
    return by_id.get


def paths(m, *rest):
    return Z.paths_for(m, resolver(*rest))


# --- the sample text, both ends -----------------------------------------------------------------------------------
def test_the_sample_query_is_what_paths_for_and_query_make():
    m = menu("main", toggle(SYM), setv(SIZE, 64), press(CLEAR))
    q = Z.Query(id=42, time=1762430000.1, paths=tuple(paths(m)))
    assert q.to_dict() == json.loads(SAMPLE_QUERY)
    assert json.loads(q.to_json()) == json.loads(SAMPLE_QUERY)


def test_the_sample_snapshot_parses():
    snap = Z.parse_snapshot(SAMPLE_SNAPSHOT)
    assert (snap.id, snap.pick, snap.pid, snap.session) == (42, 17, 9120, "429428")
    assert (snap.time, snap.ms, snap.truncated) == (1762430000.13, 1.9, False)
    assert snap.extras == {"tool": "SimpleBrush", "brush": "Standard", "brush_file": "C:/Users/u/ZBrush/Standard.zbp",
                           "material": "MatCap Red Wax", "edit": True, "edit_enabled": True}
    assert snap.items == {SYM: Z.Entry("ok", 1.0), SIZE: Z.Entry("ok", 64.0, 1.0, 1000.0), CLEAR: Z.Entry("missing")}
    assert Z.parse_snapshot(SAMPLE_SNAPSHOT.encode("utf-8")) == snap
    assert Z.parse_snapshot(SAMPLE_SNAPSHOT, asked=[SYM, SIZE, CLEAR]) == snap


# --- the parser ---------------------------------------------------------------------------------------------------
def doc(**over):
    d = json.loads(SAMPLE_SNAPSHOT)
    d.update(over)
    return json.dumps({k: v for k, v in d.items() if v is not Ellipsis})


@pytest.mark.parametrize("bad", [
    doc(v=2), doc(v=Ellipsis), doc(v=True), doc(v="1"),
    doc(id="42"), doc(id=Ellipsis), doc(id=True), doc(id=4.5),
    doc(pid="9120"), doc(pid=Ellipsis), doc(pid=False),
    "", "{", "not json", "[]", "null", "42", '"x"', "\xff\xfe",
])
def test_a_snapshot_that_is_not_one_is_refused(bad):
    with pytest.raises(Z.SnapshotError):
        Z.parse_snapshot(bad)


def test_bytes_that_are_not_utf8_are_refused():
    with pytest.raises(Z.SnapshotError):
        Z.parse_snapshot(b"\xff\xfe{}")


def test_deeply_nested_json_is_refused_not_raised():
    with pytest.raises(Z.SnapshotError):
        Z.parse_snapshot("[" * 100000)


def test_a_file_over_256_kb_is_refused():
    big = doc(items={f"P:{i}": {"s": "ok", "v": 1.0} for i in range(20000)})
    assert len(big) > 256 * 1024
    with pytest.raises(Z.SnapshotError):
        Z.parse_snapshot(big)
    assert len(Z.parse_snapshot(doc(items={f"P:{i}": {"s": "ok", "v": 1.0} for i in range(100)})).items) == 100


@pytest.mark.parametrize("v", [True, False, "64", "NaN", None, [1], {"a": 1}, float("nan"), float("inf"), -float("inf"),
                               10 ** 400])
def test_a_value_that_is_not_a_plain_number_is_dropped(v):
    text = json.dumps({"v": 1, "id": 1, "pid": 2, "items": {"A:B": {"s": "ok", "v": v, "min": v, "max": v}}})
    e = Z.parse_snapshot(text).items["A:B"]
    assert e == Z.Entry("ok", None, None, None)


def test_nan_written_as_json_text_is_dropped_too():
    e = Z.parse_snapshot('{"v": 1, "id": 1, "pid": 2, "items": {"A:B": {"s": "ok", "v": NaN, "max": Infinity}}}')
    assert e.items["A:B"] == Z.Entry("ok")


def test_ints_and_floats_are_numbers():
    e = Z.parse_snapshot('{"v": 1, "id": 1, "pid": 2, "items": {"A:B": {"s": "ok", "v": 3, "min": 0, "max": 10.5}}}')
    assert e.items["A:B"] == Z.Entry("ok", 3.0, 0.0, 10.5)


@pytest.mark.parametrize("entry,status", [({"s": "bogus"}, "error"), ({}, "error"), ("ok", "error"), (5, "error"),
                                          ({"s": "disabled"}, "disabled"), ({"s": "error"}, "error")])
def test_an_unknown_status_or_entry_is_drawn_neutral(entry, status):
    text = json.dumps({"v": 1, "id": 1, "pid": 2, "items": {"A:B": entry}})
    assert Z.parse_snapshot(text).items["A:B"].status == status


def test_keys_that_were_not_asked_are_dropped():
    text = doc(items={SYM: {"s": "ok", "v": 1.0}, "Evil:Path": {"s": "ok", "v": 1.0}})
    assert set(Z.parse_snapshot(text).items) == {SYM, "Evil:Path"}
    assert set(Z.parse_snapshot(text, asked=[SYM]).items) == {SYM}
    assert Z.parse_snapshot(text, asked=[]).items == {}
    assert set(Z.parse_snapshot(text).only({SYM}).items) == {SYM}


def test_extras_keep_only_the_valid_ones_and_a_missing_part_is_harmless():
    snap = Z.parse_snapshot(doc(extras={"tool": 5, "brush": "B", "edit": "yes", "edit_enabled": False, "other": 1}))
    assert snap.extras == {"brush": "B", "edit_enabled": False}
    bare = Z.parse_snapshot('{"v": 1, "id": 1, "pid": 2}')
    assert (bare.items, bare.extras, bare.pick, bare.session, bare.truncated) == ({}, {}, 0, "", False)


# --- which snapshot is taken ---------------------------------------------------------------------------------------
def snap_of(**kw):
    return Z.parse_snapshot(doc(**kw))


def test_the_snapshot_of_the_newest_query_from_the_right_zbrush_is_taken():
    assert Z.accept(snap_of(), newest=42, pid=9120)


def test_a_wrong_id_or_pid_is_not_taken():
    assert not Z.accept(snap_of(), newest=43, pid=9120)             # an older query's answer
    assert not Z.accept(snap_of(), newest=41, pid=9120)             # an id from the future
    assert not Z.accept(snap_of(), newest=42, pid=1)                # another ZBrush
    assert not Z.accept(snap_of(), newest=0, pid=9120)              # nothing was asked


def test_the_refresh_after_a_pick_is_taken_though_its_query_is_older():
    assert Z.accept(snap_of(id=40, pick=17), newest=42, pid=9120, picked=17)
    assert not Z.accept(snap_of(id=40, pick=16), newest=42, pid=9120, picked=17)    # not yet seen the pick
    assert not Z.accept(snap_of(id=40, pick=17), newest=42, pid=9120, picked=0)     # no pick of ours
    assert not Z.accept(snap_of(id=40, pick=17), newest=42, pid=1, picked=17)
    assert not Z.accept(snap_of(id=0, pick=17), newest=42, pid=9120, picked=17)


# --- paths_for ---------------------------------------------------------------------------------------------------
def test_own_items_come_first_in_order_and_only_press_set_toggle_are_asked():
    m = menu("main", press("A:One"), brush("Standard"), toggle("A:Two"), setv("A:Three", 5),
             C.Item("Steps", "steps", {"steps": [{"press": "A:Four"}]}), C.Item("", "empty", {"empty": True}),
             C.Item("Cap", "capture", {"capture": ""}), C.Item("T", "tag", {"tag": "x"}), C.Item("", "auto", {"auto": "brush"}))
    assert paths(m) == [("A:One", "press"), ("A:Two", "toggle"), ("A:Three", "set")]


def test_a_path_used_twice_is_asked_once_as_the_kind_that_tells_most():
    m = menu("main", press("A:X"), toggle("A:X"), toggle("A:Y"), setv("A:Y", 1), press("A:Z"), press("A:Z"),
             setv("A:W", 1), toggle("A:W"))
    assert paths(m) == [("A:X", "toggle"), ("A:Y", "set"), ("A:Z", "press"), ("A:W", "set")]


def test_fans_follow_the_own_items_down_to_three_deep():
    f1 = menu("f1", press("F:1"), sub("f2"), fan=True)
    f2 = menu("f2", press("F:2"), sub("f3"), fan=True)
    f3 = menu("f3", press("F:3"), sub("f4"), fan=True)
    f4 = menu("f4", press("F:4"), fan=True)
    m = menu("main", sub("f1"), press("M:1"))
    assert paths(m, f1, f2, f3, f4) == [("M:1", "press"), ("F:1", "press"), ("F:2", "press"), ("F:3", "press")]


def test_fans_are_read_before_ring_submenus_and_ring_submenus_only_one_level():
    ring = menu("ring", press("R:1"), sub("deep"))
    deep = menu("deep", press("D:1"))
    fan = menu("fan", press("F:1"), fan=True)
    m = menu("main", sub("ring"), sub("fan"), press("M:1"))
    assert paths(m, ring, deep, fan) == [("M:1", "press"), ("F:1", "press"), ("R:1", "press")]


def test_a_ring_submenu_in_a_fan_warms_too_and_a_fan_in_a_ring_submenu_does_not():
    fan = menu("fan", sub("ring"), fan=True)
    ring = menu("ring", press("R:1"), sub("fan2"))
    fan2 = menu("fan2", press("F:2"), fan=True)
    assert paths(menu("main", sub("fan")), fan, ring, fan2) == [("R:1", "press")]


def test_menus_that_point_back_do_not_loop():
    a = menu("a", press("A:1"), sub("b"), sub("a"), fan=True)
    b = menu("b", press("B:1"), sub("a"), fan=True)
    m = menu("main", sub("a"), sub("main"))
    assert paths(m, a, b, m) == [("A:1", "press"), ("B:1", "press")]


def test_tag_and_recent_fans_are_not_even_resolved():
    seen = []

    def resolve(mid):
        seen.append(mid)
        return None
    m = menu("main", sub("tag:fav"), sub("recent:tool"), sub("gone"), press("M:1"))
    assert Z.paths_for(m, resolve) == [("M:1", "press")]
    assert seen == ["gone"]


def test_a_resolver_that_fails_or_finds_nothing_leaves_the_rest():
    def resolve(mid):
        raise RuntimeError(mid)
    assert Z.paths_for(menu("main", sub("x"), press("M:1")), resolve) == [("M:1", "press")]


def test_at_most_128_paths_and_the_own_items_win():
    own = [press(f"O:{i}") for i in range(100)]
    fan = menu("fan", *[press(f"F:{i}") for i in range(100)], fan=True)
    got = paths(menu("main", *own, sub("fan")), fan)
    assert len(got) == 128
    assert [p for p, _ in got[:100]] == [f"O:{i}" for i in range(100)]
    assert got[100] == ("F:0", "press") and got[-1] == ("F:27", "press")
    assert len(Z.paths_for(menu("main", *own), resolver(), cap=10)) == 10


def test_a_menu_with_nothing_to_ask_asks_nothing():
    assert paths(menu("main", brush("Standard"), sub("tag:x"))) == []


# --- the cache -------------------------------------------------------------------------------------------------
def merged(cache, now=0.0, **kw):
    snap = snap_of(**kw)
    cache.merge(snap, now)
    return snap


def test_a_fresh_entry_is_drawable_for_its_zbrush_only():
    c = Z.Cache()
    merged(c)
    assert c.get(SYM, 9120, 1.0) == Z.Entry("ok", 1.0)
    assert c.get(SYM, 1, 1.0) is None                       # another ZBrush in front
    assert c.get("Not:Asked", 9120, 1.0) is None


def test_an_entry_is_drawn_for_under_thirty_seconds():
    c = Z.Cache()
    merged(c, now=100.0)
    assert c.get(SYM, 9120, 129.9) is not None
    assert c.get(SYM, 9120, 130.0) is None
    assert c.get(SYM, 9120, 500.0) is None


def test_after_a_pick_the_cache_waits_for_a_snapshot_that_saw_it():
    c = Z.Cache()
    merged(c, now=0.0, pick=17)
    c.picked(18)
    assert c.get(SYM, 9120, 1.0) is None
    merged(c, now=2.0, pick=17)                             # an answer taken before the pick was carried out
    assert c.get(SYM, 9120, 3.0) is None
    merged(c, now=4.0, pick=18)
    assert c.get(SYM, 9120, 5.0) is not None
    merged(c, now=6.0, pick=20)                             # a later pick seen as well
    assert c.get(SYM, 9120, 7.0) is not None


def test_an_old_pick_does_not_hold_back_a_newer_snapshot_and_picks_only_count_up():
    c = Z.Cache()
    c.picked(18)
    c.picked(5)
    assert c.floor == 18
    merged(c, now=0.0, pick=25)
    assert c.get(SYM, 9120, 1.0) is not None


def test_an_entry_the_refresh_did_not_ask_about_stays_hidden_until_asked_again():
    c = Z.Cache()
    merged(c, now=0.0, pick=1, items={SYM: {"s": "ok", "v": 1.0}, SIZE: {"s": "ok", "v": 5.0}})
    c.picked(2)
    merged(c, now=1.0, pick=2, items={SYM: {"s": "ok", "v": 0.0}})
    assert c.get(SYM, 9120, 2.0) == Z.Entry("ok", 0.0)
    assert c.get(SIZE, 9120, 2.0) is None


def test_entries_merge_across_replies():
    c = Z.Cache()
    merged(c, now=0.0, items={SYM: {"s": "ok", "v": 1.0}})
    merged(c, now=1.0, items={SIZE: {"s": "ok", "v": 5.0}})
    assert c.get(SYM, 9120, 2.0) is not None and c.get(SIZE, 9120, 2.0) is not None
    merged(c, now=3.0, items={SYM: {"s": "ok", "v": 0.0}})
    assert c.get(SYM, 9120, 4.0).value == 0.0


@pytest.mark.parametrize("over", [{"pid": 7}, {"session": "other"}])
def test_a_restarted_zbrush_drops_the_cache(over):
    c = Z.Cache()
    merged(c, now=0.0, items={SYM: {"s": "ok", "v": 1.0}})
    c.picked(99)
    merged(c, now=1.0, pick=0, items={SIZE: {"s": "ok", "v": 5.0}}, **over)
    assert c.get(SYM, 9120, 2.0) is None
    assert c.get(SIZE, over.get("pid", 9120), 2.0) == Z.Entry("ok", 5.0)    # and the old picks do not hide the new ZBrush


def test_the_cache_does_not_grow_without_end():
    c = Z.Cache()
    for i in range(0, 1200, 100):
        c.merge(Z.Snapshot(id=i, pid=1, items={f"P:{i + j}": Z.Entry("ok", 1.0) for j in range(100)}), now=float(i))
    assert len(c._held) < 600


# --- format_value -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("v,lo,hi,target,text", [
    (64, 1, 1000, None, "64"),                       # span 100 or more: no decimals
    (64.6, 1, 1000, None, "65"),
    (12.34, 0, 100, None, "12"),
    (12.34, 0, 50, None, "12.3"),                    # span 10 or more: one
    (12.0, 0, 50, None, "12"),                       # trailing zeros go
    (2.345, 0, 5, None, "2.35"),                     # span 1 or more: two (2.345 is stored a hair high here)
    (2.5, 0, 5, None, "2.5"),
    (0.1234, 0, 0.5, None, "0.123"),                 # span under 1: three
    (0.5, 0, 0.5, None, "0.5"),
    (64, 1, 1000, 0.5, "64"),                        # as many decimals as the slot's own value, then trimmed
    (64.25, 1, 1000, 0.25, "64.25"),
    (64.25, 1, 1000, 64.5, "64.2"),
    (0.42, 0, 1, 0.4, "0.42"),
    (3.14159, 0, 100, 3.14159, "3.142"),             # the slot's own decimals are capped at three
    (3, 0, 100, 3.14159, "3"),
    (0.12345, 0, 0.5, None, "0.123"),
    (-0.123, 0, 0.5, None, "-0.12"),                 # five characters at most: a decimal goes
    (-0.0001, 0, 100, None, "0"),                    # no "-0"
    (12345, 0, 20000, None, "12.3k"),
    (12500, 0, 20000, None, "12.5k"),
    (12000, 0, 20000, None, "12k"),
    (10000, 0, 20000, None, "10k"),
    (9999.9, 0, 20000, None, "10k"),
    (9999, 0, 20000, None, "9999"),
    (-15000, 0, 20000, None, "-15k"),
    (-12345, 0, 20000, None, "-12k"),
    (1234567, 0, 2000000, None, "1235k"),
    (0.5, None, None, None, "0.5"),                  # no range: at most two decimals
    (0.12345, None, None, None, "0.12"),
    (64.0, None, None, None, "64"),
    (1234.5678, None, None, None, "1235"),          # five characters at most: the decimals go
    (7, 5, 5, None, "7"),                            # an empty range counts as none
    (7.126, 9, 5, None, "7.13"),
    (float("nan"), 0, 10, None, ""),
    (float("inf"), 0, 10, None, ""),
    (None, 0, 10, None, ""),
])
def test_format_value(v, lo, hi, target, text):
    got = Z.format_value(v, lo, hi, target)
    assert got == text
    assert len(got) <= 5


def test_format_value_is_never_longer_than_five_characters():
    for v in (0, 1, -1, 0.001, -0.001, 99.995, -99.995, 999.9, 9999.5, -9999.5, 12345.6, -99999, 1e6, 1e9, -1e12, 1e30):
        for lo, hi in ((None, None), (0, 1), (0, 10), (0, 100), (0, 1e6)):
            assert len(Z.format_value(v, lo, hi, 0.123)) <= 5, (v, lo, hi)


# --- marks_for ---------------------------------------------------------------------------------------------------
def marks(m, items, pid=9120, now=1.0, **kw):
    c = Z.Cache()
    c.merge(snap_of(items=items, **kw), 0.0)
    return Z.marks_for(m, c, pid, now)


def test_a_toggle_is_lit_hollow_or_without_a_pip():
    m = menu("main", toggle(SYM), toggle(SIZE), toggle(CLEAR), toggle("Other:Path"))
    got = marks(m, {SYM: {"s": "ok", "v": 1.0}, SIZE: {"s": "ok", "v": 0.0}, CLEAR: {"s": "ok"}})
    assert got == [Z.Mark(True, None, False), Z.Mark(False, None, False), None, None]


def test_a_toggle_that_is_not_one_or_zero_is_lit_when_it_is_not_zero():
    m = menu("main", toggle("A:B"))
    assert marks(m, {"A:B": {"s": "ok", "v": 0.5}}) == [Z.Mark(True)]
    assert marks(m, {"A:B": {"s": "ok", "v": -2.0}}) == [Z.Mark(True)]
    assert marks(m, {"A:B": {"s": "ok", "v": "on"}}) is None                  # not a number: no state to draw


def test_missing_and_disabled_items_are_dimmed_and_error_is_neutral():
    m = menu("main", press("A:One"), toggle("A:Two"), setv("A:Three", 5), press("A:Four"), toggle("A:Five"))
    got = marks(m, {"A:One": {"s": "missing"}, "A:Two": {"s": "disabled", "v": 1.0}, "A:Three": {"s": "missing"},
                    "A:Four": {"s": "error"}, "A:Five": {"s": "error", "v": 1.0}})
    assert got == [Z.Mark(None, None, True), Z.Mark(True, None, True), Z.Mark(None, None, True), None, None]


def test_a_press_that_is_there_has_no_mark():
    assert marks(menu("main", press("A:One")), {"A:One": {"s": "ok"}}) is None


def test_a_set_shows_its_value_and_lights_when_the_target_is_the_value():
    m = menu("main", setv(SIZE, 64))
    rng = {"s": "ok", "min": 1.0, "max": 1000.0}
    assert marks(m, {SIZE: {**rng, "v": 64.0}}) == [Z.Mark(True, "64", False)]
    assert marks(m, {SIZE: {**rng, "v": 65.0}}) == [Z.Mark(None, "65", False)]            # never hollow
    assert marks(m, {SIZE: {**rng, "v": 64.4}}) == [Z.Mark(True, "64", False)]            # within half the last digit shown
    assert marks(m, {SIZE: {**rng, "v": 64.6}}) == [Z.Mark(None, "65", False)]
    assert marks(m, {SIZE: {"s": "ok", "v": 64.0}}) == [Z.Mark(True, "64", False)]        # no range
    assert marks(m, {SIZE: {"s": "disabled", **{"v": 64.0}}}) == [Z.Mark(True, "64", True)]


def test_a_set_without_a_known_value_has_no_chip():
    m = menu("main", setv(SIZE, 64))
    assert marks(m, {SIZE: {"s": "ok"}}) is None
    assert marks(m, {SIZE: {"s": "ok", "v": True}}) is None


def test_the_half_digit_follows_the_precision_the_slot_shows():
    m = menu("main", setv("D:Focal", 0.25))
    rng = {"s": "ok", "min": 0.0, "max": 1.0}                           # two decimals are shown: 0.25
    assert marks(m, {"D:Focal": {**rng, "v": 0.25}}) == [Z.Mark(True, "0.25", False)]
    assert marks(m, {"D:Focal": {**rng, "v": 0.254}}) == [Z.Mark(True, "0.25", False)]
    assert marks(m, {"D:Focal": {**rng, "v": 0.256}}) == [Z.Mark(None, "0.26", False)]
    fine = {"s": "ok", "min": 0.0, "max": 0.5}                          # three decimals are shown
    assert marks(m, {"D:Focal": {**fine, "v": 0.254}}) == [Z.Mark(None, "0.254", False)]


def test_several_sets_of_one_slider_show_no_chip_and_only_the_matching_one_lights():
    m = menu("main", setv(SIZE, 16), setv(SIZE, 64), setv(SIZE, 256), setv("D:Other", 1))
    rng = {"s": "ok", "min": 1.0, "max": 1000.0}
    got = marks(m, {SIZE: {**rng, "v": 64.0}, "D:Other": {"s": "ok", "v": 3.0}})
    assert got == [None, Z.Mark(True, None, False), None, Z.Mark(None, "3", False)]
    assert marks(m, {SIZE: {**rng, "v": 5.0}}) is None


def test_a_row_of_presets_is_dimmed_together_when_the_slider_is_missing():
    m = menu("main", setv(SIZE, 16), setv(SIZE, 64))
    assert marks(m, {SIZE: {"s": "missing"}}) == [Z.Mark(None, None, True)] * 2


def test_steps_assets_and_empty_slots_never_get_a_mark_and_the_list_is_as_long_as_the_menu():
    m = menu("main", C.Item("S", "steps", {"steps": [{"press": SYM}]}), brush("Standard"), sub("x"), toggle(SYM),
             C.Item("", "empty", {"empty": True}))
    got = marks(m, {SYM: {"s": "ok", "v": 1.0}})
    assert got == [None, None, None, Z.Mark(True), None]
    assert len(got) == len(m.items)


def test_nothing_to_draw_is_none():
    m = menu("main", toggle(SYM), brush("Standard"))
    assert marks(m, {}) is None
    assert marks(m, {SYM: {"s": "ok", "v": 1.0}}, pid=1) is None                # another ZBrush
    assert marks(m, {SYM: {"s": "ok", "v": 1.0}}, now=99.0) is None             # too old
    assert marks(menu("main"), {}) is None


def test_marks_are_comparable_and_hashable_so_the_ring_can_key_a_picture_on_one():
    assert Z.Mark(True, "5", False) == Z.Mark(True, "5", False)
    assert len({Z.Mark(True), Z.Mark(True), Z.Mark(False), Z.Mark(None, None, True)}) == 3
    assert Z.Mark() == Z.Mark(None, None, False)


# --- Channel ---------------------------------------------------------------------------------------------------
LISTENER, CTRL, PID = 0x1234, 0x99, 9120


class Rig:
    """A Channel with a fake post, a clock the test moves and a throw-away data folder."""

    def __init__(self, tmp_path, post_ok=True):
        self.dir = str(tmp_path / "data")
        self.t = 100.0
        self.sent = []
        self.lines = []
        self.post_ok = post_ok
        self.ch = Z.Channel(self.post, CTRL, self.dir, clock=lambda: self.t, wall=lambda: 1762430000.1, log=self.lines.append)
        self.menu = menu("main", toggle(SYM), setv(SIZE, 64), press(CLEAR))

    def post(self, hwnd, msg, wparam, lparam):
        self.sent.append((hwnd, msg, wparam, lparam))
        return self.post_ok

    def ask(self, **kw):
        args = dict(pid=PID, listener=LISTENER, capable=True, enabled=True)
        args.update(kw)
        return self.ch.ask(self.menu, resolver(), **args)

    def query(self):
        with open(os.path.join(self.dir, Z.QUERY_FILE), encoding="utf-8") as f:
            return json.load(f)

    def answer(self, text=None, **over):
        """The plugin writes zstate.json (the sample, with changes) and posts READY; returns what on_ready says."""
        d = json.loads(text or SAMPLE_SNAPSHOT)
        d.update(over)
        os.makedirs(self.dir, exist_ok=True)
        with open(os.path.join(self.dir, Z.STATE_FILE), "w", encoding="utf-8") as f:
            json.dump(d, f)
        return self.ch.on_ready(d["id"])


@pytest.fixture
def rig(tmp_path):
    return Rig(tmp_path)


def test_the_message_numbers_are_the_ones_the_plugin_uses():
    import win32 as W
    assert Z.WM_APP == W.WM_APP
    assert Z.WM_APP_STATE == W.WM_APP + 2
    assert Z.WM_APP_STATE_READY == W.WM_APP + 19


def test_an_ask_writes_the_query_and_posts_one_message(rig):
    assert rig.ask() is True
    assert rig.sent == [(LISTENER, Z.WM_APP_STATE, 1, CTRL)]
    q = rig.query()
    assert q["v"] == 1 and q["id"] == 1 and q["time"] == 1762430000.1
    assert q["paths"] == json.loads(SAMPLE_QUERY)["paths"]
    assert not os.path.exists(os.path.join(rig.dir, Z.QUERY_FILE + ".tmp"))


def test_while_a_question_waits_a_new_ask_only_rewrites_the_file(rig):
    rig.ask()
    rig.menu = menu("main", toggle("A:New"))
    rig.t += 0.5
    assert rig.ask() is True
    assert len(rig.sent) == 1                                          # still the one message
    assert rig.query()["id"] == 2 and rig.query()["paths"] == [{"p": "A:New", "k": "toggle"}]


def test_a_question_with_no_answer_for_two_seconds_is_lost_and_asked_again_with_one_log_line(rig):
    rig.ask()
    rig.t += 1.9
    rig.ask()
    assert len(rig.sent) == 1
    rig.t += 0.2
    rig.ask()
    assert [s[2] for s in rig.sent] == [1, 3]
    rig.t += 3
    rig.ask()
    assert len(rig.sent) == 3
    assert len([ln for ln in rig.lines if "no answer" in ln]) == 1


def test_an_answer_ends_the_wait_so_the_next_ask_posts_again(rig):
    rig.ask()
    assert rig.answer() is False                                       # the sample is id 42: not the id asked
    rig.t += 0.1
    assert rig.answer(id=1) is True
    rig.ask()
    assert [s[2] for s in rig.sent] == [1, 2]


@pytest.mark.parametrize("kw", [{"capable": False}, {"enabled": False}, {"listener": None}, {"pid": 0}])
def test_nothing_is_asked_without_the_capability_the_switch_the_listener_or_a_zbrush(rig, kw):
    assert rig.ask(**kw) is False
    assert rig.sent == []
    assert not os.path.exists(rig.dir) or not os.listdir(rig.dir)
    assert rig.ch.marks(rig.menu) is None


def test_turning_it_off_stops_marks_that_were_known(rig):
    rig.ask()
    rig.answer(id=1)
    assert rig.ch.marks(rig.menu) is not None
    rig.ask(enabled=False)
    assert rig.ch.marks(rig.menu) is None


def test_a_menu_with_nothing_to_ask_posts_nothing(rig):
    rig.menu = menu("main", brush("Standard"))
    assert rig.ask() is False
    assert rig.sent == []


def test_a_post_that_fails_is_not_a_question_in_flight(tmp_path):
    rig = Rig(tmp_path, post_ok=False)
    assert rig.ask() is False
    rig.post_ok = True
    rig.t += 0.1
    assert rig.ask() is True and len(rig.sent) == 2
    assert len([ln for ln in rig.lines if "could not post" in ln]) == 1


def test_a_query_file_that_cannot_be_written_is_logged_once_and_asks_nothing(rig, monkeypatch):
    def fail(*a, **k):
        raise PermissionError("denied")
    monkeypatch.setattr(os, "replace", fail)
    assert rig.ask() is False and rig.ask() is False
    assert rig.sent == []
    assert len([ln for ln in rig.lines if "could not write" in ln]) == 1


def test_the_answer_to_the_newest_query_gives_marks(rig):
    rig.ask()
    assert rig.ch.marks(rig.menu) is None                              # nothing known yet: a neutral ring
    assert rig.answer(id=1) is True
    assert rig.ch.marks(rig.menu) == [Z.Mark(True), Z.Mark(True, "64", False), Z.Mark(None, None, True)]
    assert rig.ch.cache.get(SYM, PID, rig.t).value == 1.0


def test_marks_come_from_the_cache_while_a_new_question_waits(rig):
    rig.ask()
    rig.answer(id=1)
    rig.t += 5
    rig.ask()
    assert rig.ch.marks(rig.menu) is not None
    rig.t += 30
    assert rig.ch.marks(rig.menu) is None                              # too old to draw


def test_a_late_reply_is_ignored_and_the_newest_query_is_asked_for_again(rig):
    rig.ask()
    rig.menu = menu("main", toggle("A:New"))
    rig.ask()                                                          # query 2 rewrites the file, no message
    assert rig.answer(id=1) is False                                   # the plugin read query 1 before the rewrite
    assert rig.ch.cache.get(SYM, PID, rig.t) is None
    assert [s[2] for s in rig.sent] == [1, 2]                          # it is free now: one more message for query 2
    assert rig.answer(id=2, items={"A:New": {"s": "ok", "v": 1.0}}) is True
    assert rig.ch.marks(rig.menu) == [Z.Mark(True)]


def test_a_reply_from_another_zbrush_is_ignored(rig):
    rig.ask()
    assert rig.answer(id=1, pid=1) is False
    assert rig.ch.marks(rig.menu) is None
    assert rig.ch._flight is not None                                  # still waiting for the right one


def test_a_reply_for_an_id_never_asked_or_from_the_future_is_ignored(rig):
    rig.ask()
    assert rig.answer(id=7) is False
    assert rig.answer(id=0) is False
    assert rig.ch.marks(rig.menu) is None


def test_a_reply_when_nothing_was_asked_is_ignored(rig):
    assert rig.answer(id=1) is False


@pytest.mark.parametrize("write", [lambda p: p.write_bytes(b""), lambda p: p.write_bytes(b"{"),
                                   lambda p: p.write_text(json.dumps({"v": 2, "id": 1, "pid": PID})),
                                   lambda p: p.write_bytes(b"x" * (Z.MAX_FILE + 1))])
def test_a_bad_or_missing_state_file_is_ignored_and_logged_once(rig, tmp_path, write):
    rig.ask()
    path = tmp_path / "data" / Z.STATE_FILE
    write(path)
    assert rig.ch.on_ready(1) is False and rig.ch.on_ready(1) is False
    assert len([ln for ln in rig.lines if "ignored" in ln]) == 1
    os.remove(path)
    assert rig.ch.on_ready(1) is False                                 # no file at all
    assert rig.ch.marks(rig.menu) is None


def test_keys_the_query_did_not_have_never_reach_the_cache(rig):
    rig.ask()
    rig.answer(id=1, items={SYM: {"s": "ok", "v": 1.0}, "Evil:Path": {"s": "ok", "v": 1.0}})
    assert rig.ch.cache.get("Evil:Path", PID, rig.t) is None
    assert rig.ch.cache.get(SYM, PID, rig.t) is not None


def test_after_a_pick_the_old_marks_are_hidden_until_the_refresh_arrives(rig):
    rig.ask()
    rig.answer(id=1, pick=4)
    assert rig.ch.marks(rig.menu) is not None
    rig.ch.picked(5)
    assert rig.ch.marks(rig.menu) is None                              # neutral, never a stale pip
    assert rig.answer(id=1, pick=4) is True                            # an answer that predates the pick: kept, not drawn
    assert rig.ch.marks(rig.menu) is None
    assert rig.answer(id=1, pick=5, items={SYM: {"s": "ok", "v": 0.0}, SIZE: {"s": "ok", "v": 64.0},
                                           CLEAR: {"s": "missing"}}) is True      # the unasked refresh of the last query
    assert rig.ch.marks(rig.menu)[0] == Z.Mark(False)


def test_the_refresh_after_a_pick_is_taken_though_a_newer_query_was_written(rig):
    rig.ask()
    rig.answer(id=1, pick=4)
    rig.ch.picked(5)
    rig.t += 1
    rig.ask()                                                          # query 2, not yet read by the plugin
    assert rig.answer(id=1, pick=5) is True                            # the refresh answers the older query
    assert rig.ch.cache.get(SYM, PID, rig.t) is not None
    assert rig.ch._flight is not None                                  # query 2 is still to be answered


def test_a_restarted_zbrush_starts_from_nothing(rig):
    rig.ask()
    rig.answer(id=1)
    rig.t += 1
    rig.ask(pid=777, listener=0x55)
    assert rig.ch.marks(rig.menu) is None                              # not the other ZBrush's marks
    assert rig.answer(id=2, pid=777, session="new", items={SYM: {"s": "ok", "v": 0.0}}) is True
    assert rig.ch.marks(rig.menu)[0] == Z.Mark(False)


def test_a_second_zbrush_is_posted_to_even_while_the_first_is_waiting(rig):
    rig.ask()
    rig.t += 0.1
    rig.ask(pid=777, listener=0x55)
    assert [(s[0], s[2]) for s in rig.sent] == [(LISTENER, 1), (0x55, 2)]


def test_missing_paths_the_timing_and_a_cut_snapshot_are_logged_once_per_session(rig):
    rig.ask()
    rig.t += 0.012
    rig.answer(id=1, truncated=True)
    rig.ask()
    rig.answer(id=2, truncated=True)
    text = "\n".join(rig.lines)
    assert text.count("answered in") == 1 and "12 ms" in text and "plugin 1.9 ms" in text
    assert text.count(CLEAR) == 1
    assert text.count("time limit") == 1
    rig.ask()
    rig.answer(id=3, session="again")
    assert "\n".join(rig.lines).count("answered in") == 2             # a new session says it again


def test_the_channel_works_without_a_log(tmp_path):
    ch = Z.Channel(lambda *a: True, CTRL, str(tmp_path))
    assert ch.ask(menu("m", toggle(SYM)), resolver(), pid=1, listener=2, capable=True) is True
    assert ch.on_ready(1) is False
    assert ch.marks(menu("m", toggle(SYM))) is None
