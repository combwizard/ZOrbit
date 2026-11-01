"""The profile entries of the tray menu (the Tray itself needs a window, so only the pure part is tested)."""
import tray


def test_entries_get_ids_doubled_ampersands_and_a_check_mark():
    out = tray.menu_entries(["A", "B&C", "x" * 50], "B&C")
    assert [e[0] for e in out] == [100, 101, 102]
    assert out[0] == (100, "A", False)
    assert out[1] == (101, "B&&C", True)


def test_a_long_name_is_cut_to_forty_characters():
    text = tray.menu_entries(["x" * 50], "x")[0][1]
    assert text == "x" * 37 + "..."
    assert len(text) == tray.PROFILE_TEXT_MAX
    assert tray.menu_entries(["y" * 40], "y")[0][1] == "y" * 40


def test_the_list_is_cut_at_thirty_but_keeps_the_active_profile():
    names = [f"P{i:02d}" for i in range(35)]
    out = tray.menu_entries(names, "P34")
    assert len(out) == 30
    assert out[-1] == (129, "P34", True)
    assert [e[1] for e in out[:-1]] == names[:29]
    plain = tray.menu_entries(names, "P03")
    assert len(plain) == 30 and plain[3][2] and plain[-1][1] == "P29"


def test_no_names_give_no_entries():
    assert tray.menu_entries([], "Default") == []


def test_set_profile_changes_the_default_tip():
    t = tray.Tray("ZOrbit 1", None, lambda name: None)
    assert t.set_tip(None) is True and t.tip == "ZOrbit 1"
    t.set_profile("Sculpt")
    assert t.tip == "ZOrbit 1: Sculpt"
    t.set_tip("menus file cannot be read")
    t.set_tip(None)
    assert t.tip == "ZOrbit 1: Sculpt"
