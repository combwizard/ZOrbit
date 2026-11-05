"""tags.py: the tag store (tags.json) and its helpers."""
import builtins
import json
import os

import pytest

import tags
from tags import FAVOURITE, PALETTE, TagStore

STARTER_KEYS = ["favourite", "blocking", "detailing"]

GOOD = {
    "version": 1,
    "tags": {"blocking": {"label": "Blocking", "color": "#F86B33"},
             "detailing": {"label": "Detailing", "color": "#4DC8E9"}},
    "items": {"brush:claybuildup": ["blocking"],
              "brush:dam_standard": ["detailing", "blocking"],
              "alpha:alpha058": ["blocking"]},
}


def keys(store):
    return [t["key"] for t in store.tags()]


def starred(*names, kind="brush"):
    """A tags.json-shaped dict with these names starred, in this order."""
    return {"version": 1, "tags": {"favourite": {"label": "Favourites", "color": "#FFD166"}},
            "items": {f"{kind}:{n}": [FAVOURITE] for n in names}}


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def good(tags_file):
    """A store loaded from a well-formed file (with Favourites missing from it)."""
    return TagStore(tags_file(GOOD)).load()


@pytest.fixture
def fresh(tmp_path):
    """A store on a file that does not exist yet."""
    return TagStore(str(tmp_path / "tags.json")).load()


# --- item_key and _slug -------------------------------------------------------------------------


@pytest.mark.parametrize("kind, name, expected", [
    ("brush", " Dam Standard ", "brush:damstandard"), ("brush", "ClayBuildup", "brush:claybuildup"),
    ("alpha", "Alpha 058", "alpha:alpha058"), ("texture", "A  B\tC", "texture:abc")])
def test_item_key_is_kind_and_the_name_in_lower_case_without_spaces(kind, name, expected):
    assert tags.item_key(kind, name) == expected


@pytest.mark.parametrize("label, slug", [
    ("Blocking", "blocking"), ("Hard Surface", "hard-surface"), ("Hard  Surface", "hard-surface"),
    ("snake_case", "snake_case"), ("3D Print", "tag-3d-print"), ("9", "tag-9"), ("!!!", "tag"),
    ("", "tag"), ("_x_", "x"), ("Détail", "d-tail"), ("WIP!", "wip")])
def test_slug_of_a_label(label, slug):
    assert tags._slug(label) == slug


def test_slug_is_at_most_32_characters_and_does_not_end_in_a_dash():
    assert tags._slug("a" * 40) == "a" * 32
    assert tags._slug("a" * 31 + " b") == "a" * 31


def test_slugs_match_the_key_rule():
    for label in ("Blocking", "3D Print", "!!!", "x" * 40, "Détail"):
        assert tags._KEY_RE.fullmatch(tags._slug(label))


# --- loading ------------------------------------------------------------------------------------


def test_a_well_formed_file_loads(good):
    assert good.error == ""
    assert good.has("blocking") and good.has("detailing")
    assert good.label("blocking") == "Blocking"
    assert good.color("detailing") == "#4DC8E9"
    assert good.items() == GOOD["items"]


def test_loading_adds_favourites_first(good):
    assert keys(good) == ["favourite", "blocking", "detailing"]
    assert good.label(FAVOURITE) == "Favourites"
    assert good.color(FAVOURITE) == tags.FAVOURITE_COLOR


def test_a_missing_file_gives_the_starter_tags_in_memory_with_no_error(fresh):
    assert fresh.error == ""
    assert keys(fresh) == STARTER_KEYS
    assert [t["label"] for t in fresh.tags()] == ["Favourites", "Blocking", "Detailing"]
    assert fresh.items() == {}
    assert fresh.mtime == 0


def test_a_missing_file_stays_missing_after_loading(fresh):
    assert not os.path.exists(fresh.path)


def test_the_starter_tags_are_the_documented_ones():
    assert tags.STARTERS == (("favourite", "Favourites", "#FFD166"), ("blocking", "Blocking", "#A8DF23"),
                             ("detailing", "Detailing", "#C77DFF"))


def test_loading_a_file_with_a_bom(tags_file, write_json):
    path = write_json(json.dumps(GOOD), "tags.json", encoding="utf-8-sig")
    assert TagStore(path).load().has("blocking")


def test_has_label_and_colour_of_an_unknown_tag(good):
    assert good.has("nope") is False
    assert good.label("nope") == ""
    assert good.color("nope") == ""


def test_exists_is_has(good):
    assert good.exists("blocking") and not good.exists("nope")


def test_tags_counts_the_items_of_each_tag(good):
    counts = {t["key"]: t["count"] for t in good.tags()}
    assert counts == {"favourite": 0, "blocking": 3, "detailing": 1}


def test_items_with_lists_item_keys_in_file_order(good):
    assert good.items_with("blocking") == ["brush:claybuildup", "brush:dam_standard", "alpha:alpha058"]
    assert good.items_with("detailing") == ["brush:dam_standard"]
    assert good.items_with("nope") == []


def test_items_with_can_be_limited_to_a_kind(good):
    assert good.items_with("blocking", "brush") == ["brush:claybuildup", "brush:dam_standard"]
    assert good.items_with("blocking", "alpha") == ["alpha:alpha058"]
    assert good.items_with("blocking", "texture") == []


def test_tagged_lists_items_with_any_tag_optionally_of_one_kind(good):
    assert good.tagged() == ["brush:claybuildup", "brush:dam_standard", "alpha:alpha058"]
    assert good.tagged("alpha") == ["alpha:alpha058"]
    assert good.tagged("material") == []


def test_tags_of_an_item_keeps_the_order_and_is_a_copy(good):
    got = good.tags_of("brush:dam_standard")
    assert got == ["detailing", "blocking"]
    got.append("x")
    assert good.tags_of("brush:dam_standard") == ["detailing", "blocking"]
    assert good.tags_of("brush:nothing") == []


def test_item_keys_in_the_file_are_normalised(tags_file):
    raw = {"tags": {"blocking": {"label": "Blocking", "color": "#F86B33"}},
           "items": {"brush:Clay Buildup": ["blocking"], "alpha:Alpha 058": ["blocking"]}}
    store = TagStore(tags_file(raw)).load()
    assert sorted(store.items()) == ["alpha:alpha058", "brush:claybuildup"]


def test_two_spellings_of_an_item_key_keep_the_first(tags_file):
    raw = {"tags": {"a": {"label": "A", "color": "#F86B33"}, "b": {"label": "B", "color": "#F86B33"}},
           "items": {"brush:Clay Buildup": ["a"], "brush:claybuildup": ["b"]}}
    assert TagStore(tags_file(raw)).load().items() == {"brush:claybuildup": ["a"]}


def test_unknown_tag_keys_in_item_lists_are_dropped(tags_file):
    raw = {"tags": {"a": {"label": "A", "color": "#F86B33"}},
           "items": {"brush:x": ["a", "ghost"], "brush:y": ["ghost"]}}
    assert TagStore(tags_file(raw)).load().items() == {"brush:x": ["a"]}


def test_favourite_in_an_item_list_is_kept_even_when_the_file_has_no_such_tag(tags_file):
    raw = {"tags": {}, "items": {"brush:x": ["favourite"]}}
    store = TagStore(tags_file(raw)).load()
    assert store.items() == {"brush:x": ["favourite"]}
    assert store.has(FAVOURITE)


def test_duplicate_tags_in_an_item_list_are_dropped(tags_file):
    raw = {"tags": {"a": {"label": "A", "color": "#F86B33"}}, "items": {"brush:x": ["a", "a"]}}
    assert TagStore(tags_file(raw)).load().items() == {"brush:x": ["a"]}


def test_a_tag_with_a_bad_key_or_no_name_is_left_out(tags_file):
    raw = {"tags": {"Upper": {"label": "U", "color": "#F86B33"}, "1x": {"label": "N", "color": "#F86B33"},
                    "noname": {"color": "#F86B33"}, "blank": {"label": "   "}, "notdict": "x",
                    "ok": {"label": "Fine", "color": "#F86B33"}}}
    assert keys(TagStore(tags_file(raw)).load()) == ["favourite", "ok"]


def test_a_bad_colour_becomes_the_first_palette_colour_and_a_good_one_is_upper_cased(tags_file):
    raw = {"tags": {"a": {"label": "A", "color": "red"}, "b": {"label": "B", "color": "#abcdef"},
                    "c": {"label": "C"}}}
    store = TagStore(tags_file(raw)).load()
    assert store.color("a") == PALETTE[0]
    assert store.color("b") == "#ABCDEF"
    assert store.color("c") == PALETTE[0]


def test_a_long_label_is_cut_to_40_characters(tags_file):
    raw = {"tags": {"a": {"label": "x" * 60, "color": "#F86B33"}}}
    assert TagStore(tags_file(raw)).load().label("a") == "x" * 40


def test_favourites_moves_to_the_front_and_gets_its_name_back(tags_file):
    raw = {"tags": {"blocking": {"label": "Blocking", "color": "#F86B33"},
                    "favourite": {"label": "Starred!", "color": "#112233"}}}
    store = TagStore(tags_file(raw)).load()
    assert keys(store) == ["favourite", "blocking"]
    assert store.label(FAVOURITE) == "Favourites"
    assert store.color(FAVOURITE) == "#112233"


def test_the_order_of_the_tags_in_the_file_is_kept(tags_file):
    raw = {"tags": {"zeta": {"label": "Z", "color": "#F86B33"}, "alpha": {"label": "A", "color": "#F86B33"}}}
    assert keys(TagStore(tags_file(raw)).load()) == ["favourite", "zeta", "alpha"]


def test_color_of_item_is_its_first_tag_other_than_favourites(tags_file):
    raw = {"tags": {"a": {"label": "A", "color": "#111111"}, "b": {"label": "B", "color": "#222222"}},
           "items": {"brush:x": ["favourite", "b", "a"], "brush:y": ["favourite"]}}
    store = TagStore(tags_file(raw)).load()
    assert store.color_of_item("brush:x") == "#222222"
    assert store.color_of_item("brush:y") == ""
    assert store.color_of_item("brush:nothing") == ""


def test_next_color_is_the_first_unused_palette_colour(fresh):
    assert fresh.next_color() == "#5EEAD4"            # the starters use #FFD166, #A8DF23 and #C77DFF


def test_next_color_cycles_when_the_palette_is_used_up(tags_file):
    raw = {"tags": {f"t{i}": {"label": f"T{i}", "color": c} for i, c in enumerate(PALETTE)}}
    store = TagStore(tags_file(raw)).load()
    assert store.next_color() == PALETTE[len(store.tags()) % len(PALETTE)]


def test_from_raw_builds_a_store_in_memory_only(tmp_path):
    path = str(tmp_path / "never.json")
    store = TagStore.from_raw(GOOD, path)
    assert store.has("blocking") and store.has(FAVOURITE)
    assert store.items_with("blocking", "alpha") == ["alpha:alpha058"]
    assert not os.path.exists(path)


def test_snapshot_is_what_tags_json_holds_and_a_copy(good):
    snap = good.snapshot()
    assert snap["version"] == 1
    assert list(snap["tags"]) == ["favourite", "blocking", "detailing"]
    assert snap["items"] == GOOD["items"]
    snap["tags"]["blocking"]["label"] = "Changed"
    snap["items"]["brush:claybuildup"].append("x")
    assert good.label("blocking") == "Blocking"
    assert good.tags_of("brush:claybuildup") == ["blocking"]


def test_reload_if_changed_notices_a_new_a_changed_and_a_removed_file(tmp_path, tags_file):
    path = tags_file(GOOD)
    store = TagStore(path).load()
    assert store.reload_if_changed() is False
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"tags": {"other": {"label": "Other", "color": "#F86B33"}}}, f)
    assert store.reload_if_changed() is True
    assert keys(store) == ["favourite", "other"]
    os.remove(path)
    assert store.reload_if_changed() is True
    assert keys(store) == STARTER_KEYS
    assert store.reload_if_changed() is False


# --- changing -----------------------------------------------------------------------------------


def test_create_tag_makes_a_key_from_the_label_and_writes_the_file(fresh):
    res = fresh.create_tag("Hard Surface")
    assert res == {"ok": True, "key": "hard-surface"}
    assert fresh.label("hard-surface") == "Hard Surface"
    assert list(read(fresh.path)["tags"]) == ["favourite", "blocking", "detailing", "hard-surface"]


def test_create_tag_takes_the_next_palette_colour(fresh):
    fresh.create_tag("One")
    fresh.create_tag("Two")
    assert fresh.color("one") == "#5EEAD4"
    assert fresh.color("two") == "#F472B6"


def test_create_tag_takes_a_given_colour_upper_cased(fresh):
    fresh.create_tag("One", "#abcdef")
    assert fresh.color("one") == "#ABCDEF"


@pytest.mark.parametrize("color", ["red", "#fff", "#12345", "", 5])
def test_create_tag_refuses_a_bad_colour(fresh, color):
    assert fresh.create_tag("One", color) == {"ok": False, "error": "A tag colour is #RRGGBB."}
    assert not fresh.has("one")


@pytest.mark.parametrize("label", ["", "   ", None, 5, "x" * 41])
def test_create_tag_refuses_a_bad_name(fresh, label):
    res = fresh.create_tag(label)
    assert res == {"ok": False, "error": "A tag name is 1 to 40 characters."}


def test_create_tag_refuses_a_name_in_use_whatever_the_case(fresh):
    res = fresh.create_tag("BLOCKING")
    assert res["ok"] is False
    assert res["exists"] == "blocking"
    assert res["error"] == "A tag called 'Blocking' already exists."


def test_create_tag_refuses_the_name_favourites(fresh):
    assert fresh.create_tag("favourites")["exists"] == FAVOURITE


def test_create_tag_trims_the_label(fresh):
    fresh.create_tag("  Spaced  ")
    assert fresh.label("spaced") == "Spaced"


def test_two_labels_with_one_slug_get_a_numbered_key(fresh):
    assert fresh.create_tag("Hard Surface")["key"] == "hard-surface"
    assert fresh.create_tag("Hard-Surface")["key"] == "hard-surface-2"
    assert fresh.create_tag("hard_surface!!")["key"] == "hard_surface"
    assert fresh.create_tag("Hard  Surface?")["key"] == "hard-surface-3"


def test_a_new_tag_whose_slug_is_a_renamed_tags_key_gets_a_numbered_key(fresh):
    fresh.rename_tag("blocking", "Layout")
    assert fresh.create_tag("Blocking") == {"ok": True, "key": "blocking-2"}


def test_a_numbered_key_still_fits_in_32_characters(fresh):
    assert fresh.create_tag("a" * 35)["key"] == "a" * 32
    key = fresh.create_tag("a" * 36)["key"]
    assert key == "a" * 30 + "-2"
    assert len(key) == 32


def test_the_file_a_change_writes_reads_back_the_same(fresh):
    fresh.create_tag("Mine")
    fresh.set_tags("brush:Clay Buildup", ["mine", "blocking"])
    again = TagStore(fresh.path).load()
    assert again.snapshot() == fresh.snapshot()
    assert again.error == ""


def test_the_file_a_change_writes_has_version_one_and_favourites_first(fresh):
    fresh.create_tag("Mine")
    data = read(fresh.path)
    assert data["version"] == 1
    assert list(data["tags"])[0] == "favourite"
    assert data["items"] == {}


def test_a_change_writes_the_starter_tags_to_the_file(fresh):
    fresh.recolor_tag("blocking", "#000000")
    assert sorted(read(fresh.path)["tags"]) == sorted(STARTER_KEYS)


def test_keys_the_module_does_not_know_are_written_back(tags_file):
    path = tags_file({**GOOD, "note": {"keep": "me"}})
    store = TagStore(path).load()
    store.create_tag("Mine")
    assert read(path)["note"] == {"keep": "me"}


def test_a_change_picks_up_what_another_process_wrote_first(tags_file):
    path = tags_file(GOOD)
    one, two = TagStore(path).load(), TagStore(path).load()
    one.create_tag("From One")
    two.create_tag("From Two")
    assert keys(TagStore(path).load()) == ["favourite", "blocking", "detailing", "from-one", "from-two"]


def test_rename_changes_the_label_and_keeps_the_key_and_the_items(good):
    assert good.rename_tag("blocking", "Layout") == {"ok": True, "key": "blocking"}
    assert good.label("blocking") == "Layout"
    assert good.items_with("blocking", "brush") == ["brush:claybuildup", "brush:dam_standard"]
    assert read(good.path)["tags"]["blocking"]["label"] == "Layout"


def test_rename_to_its_own_name_in_another_case_is_allowed(good):
    assert good.rename_tag("blocking", "BLOCKING")["ok"] is True
    assert good.label("blocking") == "BLOCKING"


def test_rename_to_another_tags_name_is_refused(good):
    res = good.rename_tag("blocking", "detailing")
    assert res["ok"] is False and res["exists"] == "detailing"
    assert good.label("blocking") == "Blocking"


def test_rename_of_an_unknown_tag_is_refused(good):
    assert good.rename_tag("nope", "X") == {"ok": False, "error": "Tag 'nope' does not exist."}


def test_favourites_cannot_be_renamed(good):
    assert good.rename_tag(FAVOURITE, "Stars") == {"ok": False, "error": "Favourites is built in and cannot be renamed."}
    assert good.label(FAVOURITE) == "Favourites"


def test_recolor_changes_the_colour_upper_cased(good):
    assert good.recolor_tag("blocking", "#00ff00") == {"ok": True, "key": "blocking"}
    assert good.color("blocking") == "#00FF00"
    assert read(good.path)["tags"]["blocking"]["color"] == "#00FF00"


def test_favourites_can_be_recoloured(good):
    assert good.recolor_tag(FAVOURITE, "#010203")["ok"] is True
    assert TagStore(good.path).load().color(FAVOURITE) == "#010203"


def test_recolor_refuses_a_bad_colour_and_an_unknown_tag(good):
    assert good.recolor_tag("blocking", "green")["ok"] is False
    assert good.recolor_tag("nope", "#000000")["error"] == "Tag 'nope' does not exist."
    assert good.color("blocking") == "#F86B33"


def test_delete_removes_the_tag_from_every_item_and_drops_items_left_bare(good):
    assert good.delete_tag("blocking") == {"ok": True, "key": "blocking"}
    assert not good.has("blocking")
    assert good.items() == {"brush:dam_standard": ["detailing"]}
    assert "blocking" not in read(good.path)["tags"]


def test_delete_of_an_unknown_tag_is_refused(good):
    assert good.delete_tag("nope")["ok"] is False


def test_favourites_cannot_be_deleted(good):
    assert good.delete_tag(FAVOURITE) == {"ok": False, "error": "Favourites is built in and cannot be deleted."}
    assert good.has(FAVOURITE)


def test_a_refused_change_does_not_write_the_file(fresh):
    fresh.delete_tag(FAVOURITE)
    assert not os.path.exists(fresh.path)


def test_merge_moves_items_to_the_other_tag_in_the_same_place(good):
    assert good.merge_tags("blocking", "detailing") == {"ok": True, "key": "detailing"}
    assert not good.has("blocking")
    assert good.tags_of("brush:claybuildup") == ["detailing"]
    assert good.tags_of("brush:dam_standard") == ["detailing"]         # it had both: no duplicate
    assert good.tags_of("alpha:alpha058") == ["detailing"]


def test_merge_keeps_the_position_of_the_merged_tag(tags_file):
    raw = {"tags": {k: {"label": k.upper(), "color": "#F86B33"} for k in ("a", "b", "c")},
           "items": {"brush:x": ["a", "b"]}}
    store = TagStore(tags_file(raw)).load()
    store.merge_tags("a", "c")
    assert store.tags_of("brush:x") == ["c", "b"]


def test_merge_refuses_favourites_as_the_source_the_same_tag_and_unknown_tags(good):
    assert good.merge_tags(FAVOURITE, "blocking")["error"] == "Favourites is built in and cannot be merged into another tag."
    assert good.merge_tags("blocking", "blocking")["error"] == "A tag cannot be merged into itself."
    assert good.merge_tags("nope", "blocking")["error"] == "Tag 'nope' does not exist."
    assert good.merge_tags("blocking", "nope")["error"] == "Tag 'nope' does not exist."
    assert good.has("blocking")


def test_merge_into_favourites_is_allowed(good):
    assert good.merge_tags("detailing", FAVOURITE)["ok"] is True
    assert good.tags_of("brush:dam_standard") == ["favourite", "blocking"]


def test_set_tags_gives_an_item_exactly_these_tags_under_a_normalised_key(good):
    assert good.set_tags("Brush:Pinch Me", ["detailing", "blocking", "detailing"]) == {"ok": True}
    assert good.tags_of("brush:pinchme") == ["detailing", "blocking"]


def test_set_tags_with_an_empty_list_untags_the_item(good):
    good.set_tags("brush:claybuildup", [])
    assert "brush:claybuildup" not in good.items()


@pytest.mark.parametrize("ikey", ["claybuildup", "", None, "brush:", ":x"])
def test_set_tags_refuses_a_bad_item_key(good, ikey):
    assert good.set_tags(ikey, ["blocking"])["ok"] is False


def test_set_tags_refuses_an_unknown_tag(good):
    assert good.set_tags("brush:x", ["nope"]) == {"ok": False, "error": "Tag 'nope' does not exist."}
    assert "brush:x" not in good.items()


def test_tag_items_adds_at_the_end_and_removes(good):
    assert good.tag_items(["brush:claybuildup", "brush:new"], add=["detailing"], remove=["blocking"]) == {"ok": True}
    assert good.tags_of("brush:claybuildup") == ["detailing"]
    assert good.tags_of("brush:new") == ["detailing"]
    assert good.tags_of("brush:dam_standard") == ["detailing", "blocking"]


def test_tag_items_drops_an_item_left_with_no_tags(good):
    good.tag_items(["alpha:alpha058"], remove=["blocking"])
    assert "alpha:alpha058" not in good.items()


# --- import -------------------------------------------------------------------------------------

INCOMING = {
    "tags": {"blocking": {"label": "Blocking", "color": "#000001"},        # exists here: kept as it is
             "layout": {"label": "Layout", "color": "#000002"},            # new
             "detail": {"label": "DETAILING", "color": "#000003"}},        # same name as a local tag
    "items": {"brush:claybuildup": ["layout", "blocking", "detail"],
              "brush:other": ["layout"],
              "alpha:alpha058": ["blocking"]},                              # nothing new for it
}


def test_import_preview_counts_without_changing_anything(good):
    before = open(good.path, "rb").read()
    assert good.import_preview(INCOMING) == {"tags": 3, "new_tags": 1, "items": 3}
    assert open(good.path, "rb").read() == before
    assert not good.has("layout")


def test_import_preview_on_a_missing_file_does_not_create_it(fresh):
    assert fresh.import_preview(INCOMING)["new_tags"] == 1          # only Layout is new: Detailing is a starter
    assert not os.path.exists(fresh.path)


def test_import_preview_of_something_that_is_not_a_tags_file(good):
    assert good.import_preview({}) == {"tags": 0, "new_tags": 0, "items": 0}


def test_two_incoming_tags_with_one_name_count_as_one_new_tag(good):
    raw = {"tags": {"x": {"label": "Same", "color": "#000001"}, "y": {"label": "same", "color": "#000002"}}}
    assert good.import_preview(raw)["new_tags"] == 1


def test_import_merge_adds_new_tags_and_joins_same_named_ones(good):
    res = good.import_tags(INCOMING)
    assert res == {"ok": True, "mode": "merge", "added": 1, "renamed": {"detail": "detailing"}, "items": 2}
    assert keys(good) == ["favourite", "blocking", "detailing", "layout"]
    assert good.label("detailing") == "Detailing"
    assert good.color("blocking") == "#F86B33"                      # local colour wins
    assert good.color("layout") == "#000002"


def test_import_merge_adds_the_file_s_tags_after_the_items_own(good):
    good.import_tags(INCOMING)
    assert good.tags_of("brush:claybuildup") == ["blocking", "layout", "detailing"]
    assert good.tags_of("brush:other") == ["layout"]
    assert good.tags_of("alpha:alpha058") == ["blocking"]
    assert good.tags_of("brush:dam_standard") == ["detailing", "blocking"]


def test_import_merge_is_written_to_the_file(good):
    good.import_tags(INCOMING)
    assert TagStore(good.path).load().snapshot() == good.snapshot()


def test_import_merge_twice_changes_nothing_the_second_time(good):
    good.import_tags(INCOMING)
    again = good.import_tags(INCOMING)
    assert again["added"] == 0 and again["items"] == 0


def test_import_merge_is_the_default_mode(good):
    assert good.import_tags(INCOMING)["mode"] == "merge"


def test_import_merge_into_a_missing_file_creates_it_with_the_starters_and_the_new_tags(fresh):
    assert fresh.import_tags(INCOMING)["ok"] is True
    assert keys(fresh) == ["favourite", "blocking", "detailing", "layout"]
    assert os.path.exists(fresh.path)


def test_import_replace_swaps_the_tags_and_items(good):
    res = good.import_tags(INCOMING, "replace")
    assert res == {"ok": True, "mode": "replace", "added": 3, "renamed": {}, "items": 2}
    assert keys(good) == ["favourite", "blocking", "layout", "detail"]
    assert good.color("blocking") == "#000001"
    assert good.items() == {"brush:claybuildup": ["layout", "blocking", "detail"], "brush:other": ["layout"],
                            "alpha:alpha058": ["blocking"]}
    assert "brush:dam_standard" not in good.items()


def test_import_replace_copies_the_old_file_to_a_bak_first(good):
    old = open(good.path, "rb").read()
    good.import_tags(INCOMING, "replace")
    assert open(good.path + ".bak", "rb").read() == old
    assert read(good.path)["tags"]["layout"]["label"] == "Layout"


def test_import_replace_without_an_existing_file_writes_no_bak(fresh):
    fresh.import_tags(INCOMING, "replace")
    assert os.path.exists(fresh.path)
    assert not os.path.exists(fresh.path + ".bak")


def test_import_replace_keeps_favourites_and_the_keys_it_does_not_know(tags_file):
    path = tags_file({**GOOD, "note": 1})
    store = TagStore(path).load()
    store.import_tags({"tags": {"x": {"label": "X", "color": "#000001"}}}, "replace")
    assert keys(store) == ["favourite", "x"]
    assert read(path)["note"] == 1


def test_import_replace_counts_only_items_whose_tags_changed(good):
    raw = {"tags": {"blocking": {"label": "Blocking", "color": "#F86B33"}},
           "items": {"brush:claybuildup": ["blocking"], "brush:new": ["blocking"]}}
    assert good.import_tags(raw, "replace")["items"] == 1


@pytest.mark.parametrize("mode", ["merge", "replace"])
@pytest.mark.parametrize("raw", [{}, {"tags": {}}, {"tags": {"Bad Key": {"label": "X"}}}, [], "text", None])
def test_import_of_a_file_with_no_tags_is_refused(good, mode, raw):
    before = good.snapshot()
    assert good.import_tags(raw, mode) == {"ok": False, "error": "There are no tags in that file."}
    assert good.snapshot() == before


def test_import_with_an_unknown_mode_is_refused(good):
    assert good.import_tags(INCOMING, "append") == {"ok": False, "error": "Import tags as 'merge' or 'replace'."}


# --- a file that cannot be read -----------------------------------------------------------------


def test_a_malformed_file_sets_the_error_and_a_fresh_store_has_the_starter_tags(tags_file):
    store = TagStore(tags_file("{ not json")).load()
    assert store.error.startswith("tags.json could not be read")
    assert keys(store) == ["favourite", "blocking", "detailing"]
    assert store.items() == {}


def test_a_top_level_list_is_a_malformed_file(tags_file):
    store = TagStore(tags_file("[1, 2]")).load()
    assert store.error == "tags.json could not be read: the top level must be an object"


def test_a_malformed_file_remembers_its_time_so_it_is_not_read_again_until_it_changes(tags_file):
    path = tags_file("{ not json")
    store = TagStore(path).load()
    assert store.mtime == os.stat(path).st_mtime_ns
    assert store.reload_if_changed() is False


def test_a_file_that_goes_bad_keeps_the_last_good_tags_and_sets_the_error(good):
    with open(good.path, "w", encoding="utf-8") as f:
        f.write("{ not json")
    assert good.reload_if_changed() is True
    assert good.error
    assert keys(good) == ["favourite", "blocking", "detailing"]
    assert good.items() == GOOD["items"]


def test_the_error_clears_when_the_file_is_fixed(good):
    with open(good.path, "w", encoding="utf-8") as f:
        f.write("{ not json")
    good.reload_if_changed()
    with open(good.path, "w", encoding="utf-8") as f:
        json.dump({"tags": {"new": {"label": "New", "color": "#F86B33"}}}, f)
    assert good.reload_if_changed() is True
    assert good.error == ""
    assert keys(good) == ["favourite", "new"]


@pytest.mark.parametrize("change", [
    lambda s: s.create_tag("X"), lambda s: s.rename_tag("blocking", "X"), lambda s: s.recolor_tag("blocking", "#000000"),
    lambda s: s.delete_tag("blocking"), lambda s: s.merge_tags("blocking", "detailing"),
    lambda s: s.set_tags("brush:x", ["blocking"]), lambda s: s.tag_items(["brush:x"], add=["blocking"]),
    lambda s: s.import_tags(INCOMING), lambda s: s.import_tags(INCOMING, "replace")])
def test_every_change_is_refused_on_a_malformed_file_and_the_file_is_left_alone(tags_file, change):
    path = tags_file("{ not json")
    store = TagStore(path).load()
    res = change(store)
    assert res["ok"] is False
    assert res["error"].startswith("tags.json could not be read")
    assert open(path, encoding="utf-8").read() == "{ not json"
    assert not os.path.exists(path + ".bak")


def test_a_file_that_cannot_be_opened_keeps_the_state_and_is_tried_again(good, monkeypatch):
    real_open = builtins.open

    def locked(file, *args, **kwargs):
        if file == good.path:
            raise PermissionError("locked")
        return real_open(file, *args, **kwargs)

    os.utime(good.path, (1_800_000_000, 1_800_000_000))
    monkeypatch.setattr(builtins, "open", locked)
    assert good.reload_if_changed() is True
    monkeypatch.undo()
    assert good.error.startswith("tags.json could not be read")
    assert keys(good) == ["favourite", "blocking", "detailing"]
    assert good.reload_if_changed() is False           # not at the very next poll (that reloaded every ring)...
    good._retry_at = 1.0                                # ...but once RETRY_S has passed
    assert good.reload_if_changed() is True
    assert good.error == ""


# --- a first load of a file that cannot be read ----------------------------------------------


def test_a_malformed_file_on_a_fresh_store_still_has_the_starter_tags(tags_file):
    store = TagStore(tags_file("{ not json")).load()
    assert store.error
    assert store.has("blocking")
    assert store.has("detailing")
    assert store.has(FAVOURITE)


def test_the_starter_tags_of_a_malformed_file_are_not_written(tags_file):
    path = tags_file("{ not json")
    store = TagStore(path).load()
    assert store.create_tag("X")["ok"] is False
    assert open(path, encoding="utf-8").read() == "{ not json"


def test_an_unreadable_tags_file_is_not_reported_as_changed_on_every_poll(tmp_path, monkeypatch):
    path = tmp_path / "tags.json"
    path.mkdir()                                          # a folder in its place: open() fails with an OSError
    store = TagStore(str(path)).load()
    assert store.error and store.has("blocking")          # the starter tags in memory
    assert store.reload_if_changed() is False             # same file, retry not due: no reload, no ring rebuild
    monkeypatch.setattr(store, "_retry_at", 1.0)          # due: it reads again, but nothing changed
    assert store.reload_if_changed() is False
    assert store.error


# --- the order of Favourites ----------------------------------------------------------------------
def test_an_older_file_has_no_order_and_a_write_leaves_the_key_out(tags_file):
    store = TagStore(tags_file(starred("a", "b"))).load()
    assert store.favourite_order("brush") == []
    assert store.favourite_orders() == {}
    assert "favourite_order" not in store.snapshot()
    store.tag_items(["brush:c"], add=[FAVOURITE])
    assert "favourite_order" not in read(store.path)
    assert read(store.path)["version"] == 1


def test_a_good_order_is_read_with_its_names_normalised(tags_file):
    raw = starred("a", "b", "dam_standard")
    raw["favourite_order"] = {"brush": ["Dam Standard", "b", "a"]}
    raw["items"]["brush:damstandard"] = raw["items"].pop("brush:dam_standard")
    assert TagStore(tags_file(raw)).load().favourite_order("brush") == ["damstandard", "b", "a"]


@pytest.mark.parametrize("bad", [
    "not an object", 3, None, ["brush"], {"brush": "a"}, {"brush": 3}, {"brush": None}, {"brush": {"a": 1}},
    {"sound": ["a"]}, {"": ["a"]}, {"brush": []}, {"brush": [1, None, {}, []]}, {"brush": ["  "]},
])
def test_a_malformed_order_is_dropped(tags_file, bad):
    raw = starred("a", "b")
    raw["favourite_order"] = bad
    store = TagStore(tags_file(raw)).load()
    assert store.error == ""
    assert store.favourite_orders() == {}
    assert store.items_with(FAVOURITE, "brush") == ["brush:a", "brush:b"]


def test_junk_in_a_list_goes_and_the_rest_stays(tags_file):
    raw = starred("a", "b", "c")
    raw["favourite_order"] = {"brush": ["c", 7, None, "c", "A", "b", "a"], "sound": ["a"]}
    assert TagStore(tags_file(raw)).load().favourite_orders() == {"brush": ["c", "a", "b"]}


def test_a_name_without_a_star_is_dropped_and_a_star_without_a_name_goes_at_the_end(tags_file):
    """What an older ZOrbit leaves: it writes the list back as it was, while it stars and unstars."""
    raw = starred("b", "c", "new")
    raw["favourite_order"] = {"brush": ["unstarred", "c", "b"]}
    assert TagStore(tags_file(raw)).load().favourite_order("brush") == ["c", "b", "new"]


def test_each_kind_has_its_own_order(tags_file):
    raw = starred("a", "b")
    raw["items"].update({"alpha:a": [FAVOURITE], "alpha:b": [FAVOURITE]})
    store = TagStore(tags_file(raw)).load()
    assert store.set_favourite_order("alpha", ["b", "a"])["ok"]
    assert store.favourite_order("alpha") == ["b", "a"]
    assert store.favourite_order("brush") == []


def test_setting_an_order_writes_it_and_a_new_store_reads_it(tags_file):
    store = TagStore(tags_file(starred("a", "b", "c"))).load()
    assert store.set_favourite_order("brush", ["c", "a", "b"]) == {"ok": True}
    assert read(store.path)["favourite_order"] == {"brush": ["c", "a", "b"]}
    assert read(store.path)["version"] == 1
    assert TagStore(store.path).load().favourite_order("brush") == ["c", "a", "b"]


def test_names_are_normalised_and_a_name_twice_counts_once(tags_file):
    store = TagStore(tags_file(starred("damstandard", "b"))).load()
    assert store.set_favourite_order("brush", ["B", "Dam Standard", "b"])["ok"]
    assert store.favourite_order("brush") == ["b", "damstandard"]


@pytest.mark.parametrize("empty", [None, [], ()])
def test_clearing_an_order_takes_the_key_out_of_the_file(tags_file, empty):
    store = TagStore(tags_file(starred("a", "b"))).load()
    store.set_favourite_order("brush", ["b", "a"])
    assert store.set_favourite_order("brush", empty) == {"ok": True}
    assert store.favourite_order("brush") == []
    assert "favourite_order" not in read(store.path)
    assert store.items_with(FAVOURITE, "brush") == ["brush:a", "brush:b"]        # the stars stay


def test_clearing_one_kind_leaves_the_other(tags_file):
    raw = starred("a", "b")
    raw["items"].update({"alpha:a": [FAVOURITE], "alpha:b": [FAVOURITE]})
    store = TagStore(tags_file(raw)).load()
    store.set_favourite_order("brush", ["b", "a"])
    store.set_favourite_order("alpha", ["b", "a"])
    store.set_favourite_order("brush", None)
    assert store.favourite_orders() == {"alpha": ["b", "a"]}


@pytest.mark.parametrize("kind", ["sound", "", None, 3, ["brush"]])
def test_an_unknown_kind_is_refused_and_nothing_is_written(tags_file, kind):
    store = TagStore(tags_file(starred("a", "b"))).load()
    before = open(store.path, "rb").read()
    assert store.set_favourite_order(kind, ["b", "a"])["ok"] is False
    assert open(store.path, "rb").read() == before


@pytest.mark.parametrize("keys", ["ab", 3, {"a": 1}, ["a", 3], [None]])
def test_a_list_that_is_not_names_is_refused(tags_file, keys):
    store = TagStore(tags_file(starred("a", "b"))).load()
    store.set_favourite_order("brush", ["b", "a"])
    assert store.set_favourite_order("brush", keys)["ok"] is False
    assert store.favourite_order("brush") == ["b", "a"]


def test_a_broken_file_refuses_an_order_and_stays_as_it_is(tags_file):
    store = TagStore(tags_file("{ not json")).load()
    assert store.set_favourite_order("brush", ["a"])["ok"] is False
    assert open(store.path, encoding="utf-8").read() == "{ not json"


# rule 4: a saved name whose item is not on show right now keeps its place
def test_a_reorder_keeps_the_names_not_on_show_in_their_places(tags_file):
    raw = starred("off1", "b", "c", "off2", "e")
    raw["favourite_order"] = {"brush": ["off1", "b", "c", "off2", "e"]}
    store = TagStore(tags_file(raw)).load()
    assert store.set_favourite_order("brush", ["e", "c", "b"])["ok"]
    assert store.favourite_order("brush") == ["off1", "e", "c", "off2", "b"]
    assert read(store.path)["favourite_order"]["brush"] == ["off1", "e", "c", "off2", "b"]


def test_the_first_drag_puts_a_star_not_on_show_at_the_end(tags_file):
    store = TagStore(tags_file(starred("off", "a", "b"))).load()
    assert store.set_favourite_order("brush", ["b", "a"])["ok"]
    assert store.favourite_order("brush") == ["b", "a", "off"]


def test_a_name_in_the_request_without_a_star_is_left_out(tags_file):
    """Another window took the star off while this one was dragging."""
    store = TagStore(tags_file(starred("a", "b"))).load()
    assert store.set_favourite_order("brush", ["b", "gone", "a"])["ok"]
    assert store.favourite_order("brush") == ["b", "a"]


def test_a_star_from_another_window_during_a_drag_goes_at_the_end(tags_file):
    store = TagStore(tags_file(starred("a", "b"))).load()
    other = TagStore(store.path).load()
    assert other.tag_items(["brush:new"], add=[FAVOURITE])["ok"]
    assert store.set_favourite_order("brush", ["b", "a"])["ok"]
    assert store.favourite_order("brush") == ["b", "a", "new"]


# rule 3: stars
def test_a_star_goes_at_the_end_of_the_order_and_only_of_its_kind(tags_file):
    store = TagStore(tags_file(starred("a", "b"))).load()
    store.set_favourite_order("brush", ["b", "a"])
    assert store.tag_items(["brush:c", "alpha:x"], add=[FAVOURITE])["ok"]
    assert store.favourite_orders() == {"brush": ["b", "a", "c"]}


def test_a_star_on_a_tab_with_no_order_makes_no_order(tags_file):
    store = TagStore(tags_file(starred("a", "b"))).load()
    assert store.tag_items(["brush:c"], add=[FAVOURITE])["ok"]
    assert store.favourite_order("brush") == []


def test_unstarring_takes_a_name_out_and_a_new_star_puts_it_at_the_end(tags_file):
    store = TagStore(tags_file(starred("a", "b", "c"))).load()
    store.set_favourite_order("brush", ["a", "b", "c"])
    assert store.tag_items(["brush:a"], remove=[FAVOURITE])["ok"]
    assert store.favourite_order("brush") == ["b", "c"]
    assert read(store.path)["favourite_order"]["brush"] == ["b", "c"]
    assert store.tag_items(["brush:a"], add=[FAVOURITE])["ok"]
    assert store.favourite_order("brush") == ["b", "c", "a"]


def test_set_tags_stars_and_unstars_like_tag_items(tags_file):
    raw = starred("a", "b")
    raw["tags"]["rock"] = {"label": "Rock", "color": "#A8DF23"}
    store = TagStore(tags_file(raw)).load()
    store.set_favourite_order("brush", ["b", "a"])
    assert store.set_tags("brush:b", ["rock"])["ok"]              # keeps another tag, loses the star
    assert store.favourite_order("brush") == ["a"]
    assert store.set_tags("brush:b", ["rock", FAVOURITE])["ok"]
    assert store.favourite_order("brush") == ["a", "b"]
    assert store.set_tags("brush:a", [])["ok"]
    assert store.favourite_order("brush") == ["b"]


def test_another_tag_coming_or_going_leaves_the_order_alone(tags_file):
    raw = starred("a", "b")
    raw["tags"]["rock"] = {"label": "Rock", "color": "#A8DF23"}
    store = TagStore(tags_file(raw)).load()
    store.set_favourite_order("brush", ["b", "a"])
    store.tag_items(["brush:a"], add=["rock"])
    store.tag_items(["brush:a"], remove=["rock"])
    store.delete_tag("rock")
    assert store.favourite_order("brush") == ["b", "a"]


def test_merging_a_tag_into_favourites_stars_its_items_at_the_end(tags_file):
    raw = starred("a", "b")
    raw["tags"]["rock"] = {"label": "Rock", "color": "#A8DF23"}
    raw["items"]["brush:c"] = ["rock"]
    store = TagStore(tags_file(raw)).load()
    store.set_favourite_order("brush", ["b", "a"])
    assert store.merge_tags("rock", FAVOURITE)["ok"]
    assert store.favourite_order("brush") == ["b", "a", "c"]


def test_the_last_item_leaving_ends_the_order(tags_file):
    store = TagStore(tags_file(starred("a"))).load()
    store.set_favourite_order("brush", ["a"])
    assert store.tag_items(["brush:a"], remove=[FAVOURITE])["ok"]
    assert store.favourite_orders() == {}
    assert "favourite_order" not in read(store.path)
    assert store.tag_items(["brush:b"], add=[FAVOURITE])["ok"]
    assert store.favourite_order("brush") == []                   # most used again, not an order of one


# export and import
def test_snapshot_and_from_raw_carry_the_order_and_a_copy_is_a_copy(tags_file):
    store = TagStore(tags_file(starred("a", "b"))).load()
    store.set_favourite_order("brush", ["b", "a"])
    snap = store.snapshot()
    assert snap["favourite_order"] == {"brush": ["b", "a"]}
    assert TagStore.from_raw(snap).favourite_order("brush") == ["b", "a"]
    assert TagStore.from_raw(snap).snapshot() == snap
    snap["favourite_order"]["brush"].append("x")
    assert store.favourite_order("brush") == ["b", "a"]
    store.favourite_order("brush").append("x")
    assert store.favourite_order("brush") == ["b", "a"]


def test_import_replace_takes_the_order_of_the_file(tags_file):
    store = TagStore(tags_file(starred("a", "b"))).load()
    store.set_favourite_order("brush", ["b", "a"])
    incoming = starred("x", "y", "z")
    incoming["favourite_order"] = {"brush": ["z", "x", "y"]}
    assert store.import_tags(incoming, "replace")["ok"]
    assert store.favourite_orders() == {"brush": ["z", "x", "y"]}
    assert read(store.path)["favourite_order"] == {"brush": ["z", "x", "y"]}


def test_import_replace_with_a_file_without_an_order_leaves_most_used(tags_file):
    store = TagStore(tags_file(starred("a", "b"))).load()
    store.set_favourite_order("brush", ["b", "a"])
    assert store.import_tags(starred("a", "b"), "replace")["ok"]
    assert store.favourite_orders() == {}
    assert "favourite_order" not in read(store.path)


def test_import_merge_keeps_your_order_takes_none_and_puts_new_stars_at_the_end(tags_file):
    store = TagStore(tags_file(starred("a", "b"))).load()
    store.set_favourite_order("brush", ["b", "a"])
    incoming = starred("z", "a")
    incoming["favourite_order"] = {"brush": ["a", "z"], "alpha": ["q"]}
    incoming["items"]["alpha:q"] = [FAVOURITE]
    assert store.import_tags(incoming, "merge")["ok"]
    assert store.favourite_orders() == {"brush": ["b", "a", "z"]}


def test_import_merge_onto_a_tab_with_no_order_stays_most_used(tags_file):
    store = TagStore(tags_file(starred("a", "b"))).load()
    incoming = starred("z")
    incoming["favourite_order"] = {"brush": ["z"]}
    assert store.import_tags(incoming, "merge")["ok"]
    assert store.favourite_orders() == {}


def test_import_preview_ignores_the_order(good):
    raw = dict(INCOMING, favourite_order={"brush": ["claybuildup"]})
    assert good.import_preview(raw) == good.import_preview(INCOMING)


def test_an_unknown_key_beside_the_order_is_still_written_back(tags_file):
    raw = starred("a", "b")
    raw["from_the_future"] = {"x": 1}
    store = TagStore(tags_file(raw)).load()
    store.set_favourite_order("brush", ["b", "a"])
    on_disk = read(store.path)
    assert on_disk["from_the_future"] == {"x": 1} and on_disk["favourite_order"] == {"brush": ["b", "a"]}


def test_reload_if_changed_sees_an_order_changed_in_another_process(tags_file):
    store = TagStore(tags_file(starred("a", "b"))).load()
    other = TagStore(store.path).load()
    other.set_favourite_order("brush", ["b", "a"])
    assert store.reload_if_changed() is True
    assert store.favourite_order("brush") == ["b", "a"]
