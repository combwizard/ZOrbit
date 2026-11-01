"""usage.py: brush scores, recent picks and the auto slots."""
import builtins
import json
import os
import time
from types import SimpleNamespace

import pytest

import usage
from usage import FORGET_BELOW, HALF_LIFE_S, PICKS_KEPT, Usage

T0 = 1_700_000_000.0               # a fixed "now" for tests that pass their own time


def make_menu(mid="main", auto=2, pinned=()):
    """A stand-in for config.Menu: `auto` auto slots and the given pinned brushes."""
    items = [SimpleNamespace(kind="brush", data={"brush": b}) for b in pinned]
    items += [SimpleNamespace(kind="auto", data={"auto": "brush"}) for _ in range(auto)]
    return SimpleNamespace(id=mid, items=items)


def pick(u, name, times=1, now=T0):
    for _ in range(times):
        u.record(name, now)


@pytest.fixture
def u(tmp_path):
    return Usage(str(tmp_path / "usage.json"))


# --- norm ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["Clay Buildup", "ClayBuildup", "clay buildup", "  CLAY  BUILDUP "])
def test_norm_ignores_case_and_spaces(name):
    assert usage.norm(name) == "claybuildup"


def test_norm_keeps_other_characters():
    assert usage.norm("Move_Topological-2") == "move_topological-2"


# --- scores -------------------------------------------------------------------------------------


def test_a_new_pick_scores_one(u):
    u.record("ClayBuildup", T0)
    assert u.score("claybuildup", T0) == pytest.approx(1.0)


def test_each_pick_adds_a_point(u):
    pick(u, "ClayBuildup", 3)
    assert u.score("claybuildup", T0) == pytest.approx(3.0)


def test_score_halves_after_the_half_life(u):
    u.record("ClayBuildup", T0)
    assert u.score("claybuildup", T0 + HALF_LIFE_S) == pytest.approx(0.5)
    assert u.score("claybuildup", T0 + 2 * HALF_LIFE_S) == pytest.approx(0.25)


def test_half_life_is_two_weeks():
    assert HALF_LIFE_S == 14 * 86400


def test_a_later_pick_adds_to_the_faded_score(u):
    u.record("ClayBuildup", T0)
    u.record("ClayBuildup", T0 + HALF_LIFE_S)
    assert u.score("claybuildup", T0 + HALF_LIFE_S) == pytest.approx(1.5)


def test_score_of_an_unknown_brush_is_zero(u):
    assert u.score("nothing", T0) == 0.0


def test_spellings_of_a_name_count_as_one_brush(u):
    u.record("Clay Buildup", T0)
    u.record("ClayBuildup", T0)
    assert list(u.brushes) == ["claybuildup"]
    assert u.score("claybuildup", T0) == pytest.approx(2.0)
    assert u.brushes["claybuildup"]["name"] == "ClayBuildup"


def test_recording_counts_as_a_change(u):
    before = u.version
    u.record("A", T0)
    u.record_pick("brush", "A", T0)
    assert u.version == before + 2


def test_ranked_is_best_first_with_ties_by_key(u):
    pick(u, "Bravo", 2)
    pick(u, "Alpha", 2)
    pick(u, "Charlie", 3)
    assert u.ranked(T0) == ["Charlie", "Alpha", "Bravo"]


def test_ranked_orders_by_faded_score(u):
    pick(u, "Old", 3, now=T0)
    pick(u, "New", 1, now=T0 + 3 * HALF_LIFE_S)       # 3 points fade to 0.375 by then
    assert u.ranked(T0 + 3 * HALF_LIFE_S) == ["New", "Old"]


def test_rank_puts_unknown_brushes_last_and_breaks_ties_by_name(u):
    pick(u, "Known", 2)
    assert u.rank(["zeta", "Known", "alpha"], T0) == ["Known", "alpha", "zeta"]


def test_scores_for_brushes_are_keyed_by_norm_and_by_plain_lower_case(u):
    u.record("Clay Buildup", T0)
    got = u.scores_for("brush", T0)
    assert got["claybuildup"] == pytest.approx(1.0)
    assert got["clay buildup"] == pytest.approx(1.0)


def test_scores_for_other_kinds_are_pick_counts(u):
    u.record_pick("alpha", "Alpha 01", T0)
    u.record_pick("alpha", "Alpha 01", T0)
    u.record_pick("material", "Skin", T0)
    assert u.scores_for("alpha")["alpha01"] == 2.0
    assert "skin" not in u.scores_for("alpha")


# --- recent picks -------------------------------------------------------------------------------


def test_record_pick_counts_and_keeps_the_latest_time_and_name(u):
    u.record_pick("alpha", "Alpha 01", 100.0)
    u.record_pick("alpha", "alpha01", 200.0)
    assert u.picks == {"alpha:alpha01": {"name": "alpha01", "count": 2, "t": 200.0}}


def test_recent_is_newest_first_and_per_kind(u):
    u.record_pick("alpha", "Old", 100.0)
    u.record_pick("alpha", "New", 300.0)
    u.record_pick("texture", "Other", 200.0)
    assert [e["name"] for e in u.recent("alpha")] == ["New", "Old"]
    assert [e["name"] for e in u.recent("texture")] == ["Other"]
    assert u.recent("alpha")[0] == {"name": "New", "t": 300.0, "count": 1}


def test_recent_respects_the_limit(u):
    for i in range(5):
        u.record_pick("alpha", f"A{i}", 100.0 + i)
    assert [e["name"] for e in u.recent("alpha", limit=2)] == ["A4", "A3"]


def test_forget_takes_a_recent_off_but_keeps_the_brush_score(u):
    u.record("Pinch", T0)
    u.record_pick("brush", "Pinch", T0)
    assert u.forget("brush", "pinch") is True
    assert u.recent("brush") == []
    assert u.score("pinch", T0) == pytest.approx(1.0)


def test_forget_of_something_not_there_is_false(u):
    assert u.forget("brush", "nothing") is False


# --- the file -----------------------------------------------------------------------------------


def test_a_missing_file_loads_empty(u):
    u.load()
    assert (u.brushes, u.menus, u.picks) == ({}, {}, {})


def test_save_and_load_round_trip(tmp_path):
    path = str(tmp_path / "usage.json")
    a = Usage(path)
    now = time.time()
    a.record("ClayBuildup", now)
    a.record("ClayBuildup", now)
    a.record_pick("brush", "ClayBuildup", now)
    a.record_pick("alpha", "Alpha 01", now)
    a.slots(make_menu("main", auto=2), now)
    a.save()
    b = Usage(path).load()
    assert b.brushes == a.brushes
    assert b.menus == a.menus
    assert b.picks == a.picks


def test_save_creates_the_folder(tmp_path):
    path = tmp_path / "deep" / "er" / "usage.json"
    Usage(str(path)).save()
    assert json.loads(path.read_text(encoding="utf-8")) == {"brushes": {}, "menus": {}, "picks": {}}


def test_load_right_after_save_does_not_read_again(u):
    u.record("A", time.time())
    u.save()
    version = u.version
    u.load()
    assert u.version == version


def test_load_reads_again_when_the_file_changed(usage_file, tmp_path):
    path = usage_file({"brushes": {}})
    a = Usage(path).load()
    assert a.brushes == {}
    now = time.time()
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"brushes": {"pinch": {"name": "Pinch", "score": 2.0, "t": now}}}, f)
    os.utime(path, (now + 10, now + 10))
    a.load()
    assert list(a.brushes) == ["pinch"]


def test_load_twice_without_a_change_keeps_the_version(usage_file):
    a = Usage(usage_file({"brushes": {}})).load()
    version = a.version
    a.load()
    assert a.version == version


def test_entries_below_the_forget_threshold_are_dropped_on_save(u):
    now = time.time()
    u.record("Faded", now - 7 * HALF_LIFE_S)         # 1 / 128 = 0.0078
    u.record("Fresh", now)
    u.save()
    assert list(u.brushes) == ["fresh"]
    assert list(Usage(u.path).load().brushes) == ["fresh"]


def test_an_entry_just_above_the_threshold_is_kept_on_save(u):
    now = time.time()
    u.record("Faint", now - 6 * HALF_LIFE_S)         # 1 / 64 = 0.0156
    u.save()
    assert list(u.brushes) == ["faint"]
    assert FORGET_BELOW == 0.01


def test_only_the_newest_picks_are_kept_on_save(u):
    for i in range(PICKS_KEPT + 5):
        u.record_pick("alpha", f"A{i:03}", 1000.0 + i)
    u.save()
    assert len(u.picks) == PICKS_KEPT
    assert "alpha:a000" not in u.picks and "alpha:a004" not in u.picks
    assert "alpha:a005" in u.picks and f"alpha:a{PICKS_KEPT + 4:03}" in u.picks
    assert len(Usage(u.path).load().picks) == PICKS_KEPT


def test_picks_kept_is_200():
    assert PICKS_KEPT == 200


def test_saving_fewer_picks_than_the_cap_keeps_them_all(u):
    for i in range(10):
        u.record_pick("brush", f"B{i}", 1000.0 + i)
    u.save()
    assert len(u.picks) == 10


@pytest.mark.parametrize("order", [("Clay Buildup", "claybuildup"), ("claybuildup", "Clay Buildup")])
def test_brush_keys_with_and_without_spaces_merge_on_load_keeping_the_higher_score(usage_file, order):
    now = time.time()
    entries = {order[0]: {"name": "Clay Buildup", "score": 1.0, "t": now},
               order[1]: {"name": "ClayBuildup", "score": 3.0, "t": now}}
    a = Usage(usage_file({"brushes": entries})).load()
    assert list(a.brushes) == ["claybuildup"]
    assert a.brushes["claybuildup"]["score"] == 3.0
    assert a.brushes["claybuildup"]["name"] == "ClayBuildup"


def test_pick_keys_with_and_without_spaces_merge_on_load_adding_counts(usage_file):
    raw = {"picks": {"alpha:Alpha 01": {"name": "Alpha 01", "count": 2, "t": 100.0},
                     "alpha:alpha01": {"name": "alpha01", "count": 3, "t": 200.0}}}
    a = Usage(usage_file(raw)).load()
    assert a.picks == {"alpha:alpha01": {"name": "alpha01", "count": 5, "t": 200.0}}


def test_load_reads_menus_and_drops_bad_slot_and_pending_entries(usage_file):
    raw = {"menus": {"main": {"slots": ["A", 5, None], "pending": ["B", 7]}, "odd": "x"}}
    a = Usage(usage_file(raw)).load()
    assert a.menus == {"main": {"slots": ["A", None, None], "pending": ["B"]}}


def test_load_skips_entries_that_are_not_objects_or_have_no_name(usage_file):
    now = time.time()
    raw = {"brushes": {"a": "x", "b": {"score": 1, "t": now}, "c": {"name": "C", "score": 1, "t": now}}}
    assert list(Usage(usage_file(raw)).load().brushes) == ["c"]


def test_a_file_that_is_not_json_loads_empty_without_raising(usage_file):
    a = Usage(usage_file("{not json")).load()
    assert (a.brushes, a.menus, a.picks) == ({}, {}, {})


def test_auto_count_counts_auto_items_only():
    assert usage.auto_count(make_menu(auto=3, pinned=("A", "B"))) == 3


def test_empty_slots_fill_at_once_from_the_ranking(u):
    pick(u, "A", 3)
    pick(u, "B", 2)
    pick(u, "C", 1)
    assert u.slots(make_menu(auto=2), T0) == ["A", "B"]


def test_slots_with_too_few_brushes_stay_empty(u):
    pick(u, "A")
    assert u.slots(make_menu(auto=3), T0) == ["A", None, None]


def test_a_brush_that_arrives_later_fills_an_empty_slot_straight_away(u):
    pick(u, "A")
    menu = make_menu(auto=2)
    assert u.slots(menu, T0) == ["A", None]
    pick(u, "B")
    assert u.slots(menu, T0) == ["A", "B"]


def test_a_menu_with_no_auto_slots_has_no_slots(u):
    pick(u, "A")
    assert u.slots(make_menu(auto=0, pinned=("X",)), T0) == []


def test_slots_leave_out_brushes_the_menu_pins(u):
    pick(u, "A", 3)
    pick(u, "B", 2)
    pick(u, "C", 1)
    assert u.slots(make_menu(auto=2, pinned=("A",)), T0) == ["B", "C"]


def test_pinning_ignores_case_and_spaces(u):
    pick(u, "Clay Buildup", 3)
    pick(u, "B", 1)
    assert u.slots(make_menu(auto=1, pinned=("claybuildup",)), T0) == ["B"]


def test_a_brush_the_menu_now_pins_leaves_its_slot_and_the_next_best_takes_it(u):
    pick(u, "A", 3)
    pick(u, "B", 2)
    pick(u, "C", 1)
    assert u.slots(make_menu(auto=2), T0) == ["A", "B"]
    assert u.slots(make_menu(auto=2, pinned=("A",)), T0) == ["C", "B"]


def test_a_brush_keeps_its_slot_when_the_ranking_changes(u):
    pick(u, "A", 3)
    pick(u, "B", 2)
    menu = make_menu(auto=2)
    assert u.slots(menu, T0) == ["A", "B"]
    pick(u, "B", 5)                                   # B now outscores A
    assert u.slots(menu, T0) == ["A", "B"]
    u.update(menu, T0)
    assert u.slots(menu, T0) == ["A", "B"]


def test_slots_are_remembered_in_the_menu_state(u):
    pick(u, "A")
    u.slots(make_menu("main", auto=1), T0)
    assert u.menus["main"]["slots"] == ["A"]


def test_slots_returns_a_copy(u):
    pick(u, "A")
    got = u.slots(make_menu(auto=1), T0)
    got[0] = "changed"
    assert u.menus["main"]["slots"] == ["A"]


def test_each_menu_has_its_own_slots(u):
    pick(u, "A", 2)
    pick(u, "B", 1)
    first, second = make_menu("one", auto=1), make_menu("two", auto=1, pinned=("A",))
    assert u.slots(first, T0) == ["A"]
    assert u.slots(second, T0) == ["B"]


def test_a_newcomer_needs_two_evaluations_in_a_row_to_take_a_slot(u):
    pick(u, "A", 3)
    pick(u, "B", 2)
    menu = make_menu(auto=2)
    u.update(menu, T0)
    assert u.slots(menu, T0) == ["A", "B"]
    pick(u, "C", 4)                                   # C is now top, B has dropped out of the top list
    u.update(menu, T0)
    assert u.slots(menu, T0) == ["A", "B"]
    assert u.menus["main"]["pending"] == ["C"]
    u.update(menu, T0)
    assert u.slots(menu, T0) == ["A", "C"]
    assert u.menus["main"]["pending"] == []


def test_newcomers_take_the_slots_of_the_dropped_brushes_lowest_score_first(u):
    pick(u, "A", 5)
    pick(u, "B", 2)
    pick(u, "C", 3)
    menu = make_menu(auto=3)
    assert u.slots(menu, T0) == ["A", "C", "B"]       # filled in ranking order
    pick(u, "D", 4)
    pick(u, "E", 4)                                 # top three are A, D, E: B and C have dropped out
    u.update(menu, T0)
    u.update(menu, T0)
    assert u.slots(menu, T0) == ["A", "E", "D"]       # D (ranked first) takes B's slot, the lowest; E takes C's


def test_only_the_brush_that_dropped_out_gives_up_its_slot(u):
    pick(u, "A", 5)
    pick(u, "B", 2)
    pick(u, "C", 3)
    menu = make_menu(auto=3)
    u.slots(menu, T0)
    pick(u, "D", 10)                                  # top three: D, A, C. Only B dropped out
    u.update(menu, T0)
    u.update(menu, T0)
    assert u.slots(menu, T0) == ["A", "C", "D"]


def test_a_challenger_that_misses_one_evaluation_starts_again(u):
    pick(u, "A", 3)
    pick(u, "B", 2)
    menu = make_menu(auto=2)
    u.update(menu, T0)
    pick(u, "C", 4)
    u.update(menu, T0)                                # C pending
    assert u.menus["main"]["pending"] == ["C"]
    pick(u, "D", 10)
    pick(u, "E", 9)                                   # top two are now D and E; C is not among them
    u.update(menu, T0)
    assert u.menus["main"]["pending"] == ["D", "E"]
    assert u.slots(menu, T0) == ["A", "B"]


def test_a_brush_that_is_in_the_top_list_is_not_a_challenger(u):
    pick(u, "A", 3)
    pick(u, "B", 2)
    menu = make_menu(auto=2)
    u.update(menu, T0)
    pick(u, "B", 5)
    u.update(menu, T0)
    assert u.menus["main"]["pending"] == []
    assert u.slots(menu, T0) == ["A", "B"]


def test_update_ignores_pinned_brushes_when_choosing_the_top_list(u):
    pick(u, "Pinned", 9)
    pick(u, "A", 3)
    menu = make_menu(auto=1, pinned=("Pinned",))
    u.update(menu, T0)
    assert u.slots(menu, T0) == ["A"]
    assert u.menus["main"]["pending"] == []


def test_update_counts_as_a_change(u):
    pick(u, "A")
    before = u.version
    u.update(make_menu(auto=1), T0)
    assert u.version > before


def test_slots_survive_a_save_and_load(tmp_path):
    path = str(tmp_path / "usage.json")
    a = Usage(path)
    now = time.time()
    a.record("A", now)
    a.record("B", now)
    menu = make_menu(auto=2)
    a.update(menu, now)
    a.save()
    b = Usage(path).load()
    assert b.slots(menu, now) == a.slots(menu, now)


# --- files that cannot be read ------------------------------------------------------------------


def make_unreadable(monkeypatch, path):
    """Makes opening `path` fail with OSError (as a file held by a scanner would) until monkeypatch.undo()."""
    real_open = builtins.open

    def flaky(file, *args, **kwargs):
        if file == path:
            raise OSError("locked")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky)


def test_a_file_that_cannot_be_read_keeps_the_state_and_the_time_so_the_next_load_retries(usage_file, monkeypatch):
    path = usage_file({})
    a = Usage(path).load()
    a.record("ClayBuildup", time.time())
    before = a.mtime
    now = time.time()
    os.utime(path, (now + 10, now + 10))                 # the file "changed", so load() tries to read it
    make_unreadable(monkeypatch, path)
    a.load()
    monkeypatch.undo()
    assert list(a.brushes) == ["claybuildup"]
    assert a.mtime == before


def test_save_after_a_failed_load_does_not_write_an_empty_file(usage_file, monkeypatch):
    now = time.time()
    path = usage_file({"brushes": {"claybuildup": {"name": "ClayBuildup", "score": 2.0, "t": now}}})
    a = Usage(path).load()
    os.utime(path, (now + 10, now + 10))
    make_unreadable(monkeypatch, path)
    a.load()
    monkeypatch.undo()
    a.save()
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["brushes"]


def test_one_bad_brush_entry_keeps_the_other_brushes_the_menus_and_the_picks(usage_file):
    now = time.time()
    raw = {"brushes": {"good1": {"name": "Good1", "score": 1, "t": now},
                       "bad": {"name": "Bad", "score": "x", "t": now},
                       "good2": {"name": "Good2", "score": 1, "t": now}},
           "menus": {"main": {"slots": ["Good1"], "pending": []}},
           "picks": {"brush:good1": {"name": "Good1", "count": 1, "t": now}}}
    a = Usage(usage_file(raw)).load()
    assert sorted(a.brushes) == ["good1", "good2"]
    assert a.menus["main"]["slots"] == ["Good1"]
    assert list(a.picks) == ["brush:good1"]


def test_a_file_that_is_not_json_is_copied_to_bad_and_the_state_is_kept(usage_file):
    path = usage_file({"brushes": {"a": {"name": "A", "score": 1, "t": time.time()}}})
    a = Usage(path).load()
    now = time.time()
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not json")
    os.utime(path, (now + 10, now + 10))
    a.load()
    assert list(a.brushes) == ["a"]
    assert a.mtime == os.stat(path).st_mtime
    with open(path + ".bad", encoding="utf-8") as f:
        assert f.read() == "{not json"


def test_a_bad_file_is_not_parsed_again_until_it_changes(usage_file, monkeypatch):
    path = usage_file("{not json")
    a = Usage(path).load()
    version = a.version
    monkeypatch.setattr(json, "load", lambda f: pytest.fail("parsed again"))
    assert a.load().version == version


def test_a_top_level_list_is_a_bad_file(usage_file):
    path = usage_file([1, 2])
    a = Usage(path).load()
    assert (a.brushes, a.menus, a.picks) == ({}, {}, {})
    assert os.path.exists(path + ".bad")


def test_a_bad_menu_entry_does_not_lose_the_picks(usage_file):
    now = time.time()
    raw = {"menus": {"bad": {"slots": 5}, "main": {"slots": ["A"], "pending": []}},
           "picks": {"brush:a": {"name": "A", "count": 1, "t": now}, "brush:b": {"name": "B", "count": "x", "t": now}}}
    a = Usage(usage_file(raw)).load()
    assert list(a.menus) == ["main"]
    assert list(a.picks) == ["brush:a"]


# --- fsutil.write_atomic ------------------------------------------------------------------------


def test_write_atomic_tries_again_when_the_file_is_held_open(tmp_path, monkeypatch):
    import fsutil
    target = str(tmp_path / "x.json")
    real_replace, calls = os.replace, []

    def flaky(src, dst):
        calls.append(src)
        if len(calls) < 3:
            raise PermissionError(13, "held")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", flaky)
    monkeypatch.setattr(fsutil.time, "sleep", lambda s: None)
    fsutil.write_atomic(target, "hello")
    assert len(calls) == 3
    assert open(target, encoding="utf-8").read() == "hello"


def test_write_atomic_gives_up_after_the_last_try_and_removes_its_temp_file(tmp_path, monkeypatch):
    import fsutil
    target = str(tmp_path / "x.json")
    pauses = []

    def held(src, dst):
        raise PermissionError(13, "held")

    monkeypatch.setattr(os, "replace", held)
    monkeypatch.setattr(fsutil.time, "sleep", pauses.append)
    with pytest.raises(PermissionError):
        fsutil.write_atomic(target, "hello")
    assert pauses == [0.05, 0.1, 0.2, 0.4, 0.8]
    assert os.listdir(tmp_path) == []


def test_write_atomic_does_not_retry_other_errors(tmp_path, monkeypatch):
    import fsutil
    calls = []

    def broken(src, dst):
        calls.append(1)
        raise OSError(28, "disk full")

    monkeypatch.setattr(os, "replace", broken)
    with pytest.raises(OSError):
        fsutil.write_atomic(str(tmp_path / "x.json"), "hello")
    assert len(calls) == 1


# --- _parse and absorb ---------------------------------------------------------------------------


def test_parse_merges_spellings_and_skips_bad_entries():
    raw = {"brushes": {"Clay Buildup": {"name": "Clay Buildup", "score": 1.0, "t": T0},
                       "claybuildup": {"name": "ClayBuildup", "score": 3.0, "t": T0},
                       "bad": {"name": "Bad", "score": "x", "t": T0}, "worse": 5},
           "menus": {"main": {"slots": ["A", 3], "pending": ["B", None]}, "odd": 4},
           "picks": {"alpha:Alpha 01": {"name": "Alpha 01", "count": 2, "t": T0},
                     "alpha:alpha01": {"name": "Alpha01", "count": 3, "t": T0 + 5}}}
    brushes, menus, picks = usage._parse(raw, T0)
    assert brushes == {"claybuildup": {"name": "ClayBuildup", "score": 3.0, "t": T0}}
    assert menus == {"main": {"slots": ["A", None], "pending": ["B"]}}
    assert picks == {"alpha:alpha01": {"name": "Alpha01", "count": 5, "t": T0 + 5}}


def test_absorb_sums_the_faded_scores_and_stamps_them_now(u):
    u.record("ClayBuildup", T0)
    taken = u.absorb({"brushes": {"claybuildup": {"name": "Clay Buildup", "score": 4.0, "t": T0 - HALF_LIFE_S},
                                  "pinch": {"name": "Pinch", "score": 1.0, "t": T0}}}, T0)
    assert taken == 2
    assert u.score("claybuildup", T0) == pytest.approx(1.0 + 2.0)
    assert u.brushes["claybuildup"]["name"] == "ClayBuildup"           # the name here stays
    assert u.brushes["claybuildup"]["t"] == T0
    assert u.brushes["pinch"] == {"name": "Pinch", "score": 1.0, "t": T0}


def test_absorb_sums_pick_counts_keeps_the_newest_time_and_this_name(u):
    u.record_pick("alpha", "Alpha 01", T0)
    u.absorb({"picks": {"alpha:alpha01": {"name": "ALPHA", "count": 4, "t": T0 + 100},
                        "brush:pinch": {"name": "Pinch", "count": 2, "t": T0 - 5}}}, T0)
    assert u.picks["alpha:alpha01"] == {"name": "Alpha 01", "count": 5, "t": T0 + 100}
    assert u.picks["brush:pinch"] == {"name": "Pinch", "count": 2, "t": T0 - 5}
    u.absorb({"picks": {"alpha:alpha01": {"name": "x", "count": 1, "t": T0 - 100}}}, T0)
    assert u.picks["alpha:alpha01"]["t"] == T0 + 100


def test_absorb_leaves_the_menus_alone_and_counts_a_change(u):
    u.slots(make_menu("main", auto=2), T0)
    menus, version = json.loads(json.dumps(u.menus)), u.version
    u.absorb({"menus": {"main": {"slots": ["Other"], "pending": []}},
              "brushes": {"pinch": {"name": "Pinch", "score": 1.0, "t": T0}}}, T0)
    assert u.menus == menus
    assert u.version == version + 1


def test_absorbed_brushes_that_have_faded_away_are_pruned_by_save(u):
    u.absorb({"brushes": {"old": {"name": "Old", "score": 1.0, "t": T0 - 20 * HALF_LIFE_S}}}, T0)
    assert "old" in u.brushes
    u.save()
    assert u.brushes == {}


@pytest.mark.parametrize("raw", [None, [], "x", 5, {}, {"brushes": 3, "picks": [1]}, {"brushes": {"a": 1, "b": {}}},
                                 {"brushes": {"a": {"name": "A", "score": float("nan"), "t": T0}}},
                                 {"brushes": {"a": {"name": "A", "score": "1", "t": None}}}])
def test_absorb_ignores_malformed_input(u, raw):
    u.record("Keep", T0)
    before = json.dumps([u.brushes, u.menus, u.picks], sort_keys=True)
    assert u.absorb(raw, T0) == 0
    assert json.dumps([u.brushes, u.menus, u.picks], sort_keys=True) == before
