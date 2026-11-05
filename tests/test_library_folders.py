"""The folders the user added for brushes, alphas, materials and textures: the reader of studio.json and the
names the browser shows for them."""
import json

import pytest

import brushes
import config
import paths


@pytest.fixture
def studio(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path))
    brushes._settings_cache.clear()
    f = tmp_path / "studio.json"

    def write(data):
        f.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
    write.file = f
    return write


def test_no_file_gives_empty_lists(studio):
    assert all(brushes.user_folders(k) == [] for k in brushes.LIBRARY_KINDS)
    sig = brushes.user_folders_signature()
    assert isinstance(sig, tuple)
    assert sig == tuple((k, ()) for k in ("brush", "alpha", "material", "texture"))


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", '{"library_folders": 5}', '{"library_folders": {"alpha": "x"}}',
                                  '{"library_folders": {"alpha": 5, "brush": null}}', "", "\xff"])
def test_odd_files_give_empty_lists(studio, text):
    studio(text)
    assert all(brushes.user_folders(k) == [] for k in brushes.LIBRARY_KINDS)


def test_bad_entries_are_skipped_and_good_ones_kept(studio):
    studio({"library_folders": {"alpha": [5, None, "", "  ", ["x"], "rel\\dir", "\\\\srv\\x", "//srv/x",
                                          " \\\\srv\\y", "D:\\Good"]}})
    assert brushes.user_folders("alpha") == [brushes.Path("D:\\Good")]
    assert brushes.user_folders("brush") == []


def test_paths_are_normalised_and_kept_in_order(studio):
    studio({"library_folders": {"brush": ["D:/B/x/../y", "D:/A"], "texture": ["E:\\T"]}})
    assert brushes._settings()["brush"] == ["D:\\B\\y", "D:\\A"]
    assert brushes.user_folders_signature()[3] == ("texture", ("E:\\T",))


def test_repeats_collapse_to_the_first(studio):
    studio({"library_folders": {"material": ["D:/A", "d:\\a\\", "D:\\B"]}})
    assert brushes._settings()["material"] == ["D:\\A", "D:\\B"]


def test_a_rewritten_file_is_read_again(studio):
    studio({"library_folders": {"alpha": ["D:\\One"]}})
    assert brushes._settings()["alpha"] == ["D:\\One"]
    studio({"library_folders": {"alpha": ["D:\\Two"]}})
    assert brushes._settings()["alpha"] == ["D:\\Two"]
    studio.file.unlink()
    assert brushes._settings()["alpha"] == []
    assert not brushes._settings_cache


def test_the_file_is_parsed_only_when_it_changed(studio, monkeypatch):
    studio({"library_folders": {"alpha": ["D:\\One"]}})
    calls = []
    real = json.loads
    monkeypatch.setattr(brushes.json, "loads", lambda *a, **k: calls.append(1) or real(*a, **k))
    brushes._settings()
    brushes._settings()
    assert len(calls) == 1
    studio({"library_folders": {"alpha": ["D:\\Two"]}})
    brushes._settings()
    assert len(calls) == 2


def test_the_lists_returned_are_copies(studio):
    studio({"library_folders": {"alpha": ["D:\\One"]}})
    brushes._settings()["alpha"].append("D:\\Other")
    assert brushes._settings()["alpha"] == ["D:\\One"]


def test_display_names():
    assert brushes.display_names(["D:\\Lib\\Alphas"]) == ["Alphas"]
    assert brushes.display_names([]) == []
    assert brushes.display_names(["D:\\a\\Alphas", "E:\\b\\alphas", "F:\\Alphas", "G:\\c"]) == [
        "Alphas", "alphas (2)", "Alphas (3)", "c"]


def test_display_names_avoid_the_fixed_ones():
    assert brushes.display_names(["D:\\ZBrush"]) == ["ZBrush (2)"]
    assert brushes.display_names(["D:\\My Brushes", "E:\\lightbox"]) == ["My Brushes (2)", "lightbox (2)"]


def test_a_drive_root_is_named_after_the_drive():
    assert brushes.display_names(["D:\\"]) == ["Drive D"]
    assert brushes.display_names(["d:\\", "D:/"]) == ["Drive D", "Drive D (2)"]


@pytest.mark.parametrize("name", ["a:b..c", "x\\y/z", "....", "::", " . ", "a...b"])
def test_a_name_is_never_a_path(name):
    safe = brushes._safe(name)
    assert safe and not config._bad_asset_name(safe)
    out = brushes.display_names(["D:\\" + name])[0]
    assert not config._bad_asset_name(out)


def test_safe_values():
    assert brushes._safe("a:b..c") == "a b.c"
    assert brushes._safe("a\\\\//b") == "a b"
    assert brushes._safe(":") == "folder"


def test_added_label_and_is_added():
    a = brushes.added_label("D:/My/Lib/")
    assert a == brushes.added_label("d:\\my\\lib")
    assert a.startswith(brushes.ADDED)
    assert brushes.is_added(a)
    assert not brushes.is_added("ZBrush")
    assert not brushes.is_added(None)
