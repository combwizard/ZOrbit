"""brushes.walk_sources (the one walker for the browser's list and the app's lookup), zbrush_dirs, and the tag
fans' rescan of a missing item."""
import os
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import assets
import brushes
import expand
import tags


def touch(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def junction(link, target):
    """A directory junction (no privilege needed); False when this runner cannot make one."""
    try:
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
    except OSError:
        return False
    return r.returncode == 0 and Path(link).exists()


@pytest.fixture
def two_folders(tmp_path):
    a, b = tmp_path / "first", tmp_path / "second"
    for f in ("beta.zbp", "Alpha.zbp", "Clay Buildup.zbp", "notes.txt"):
        touch(a / f)
    touch(a / "Sub" / "inner.zbp")
    touch(a / "_old" / "skipped.zbp")
    touch(b / "claybuildup.ZBP")                       # the same name as "Clay Buildup": the first folder wins
    touch(b / "only second.zbp")
    touch(b / "_hidden" / "nope.zbp")
    return a, b


def srcs(*folders):
    return [(f"folder {i}", f, True) for i, f in enumerate(folders)]


@pytest.fixture(autouse=True)
def fresh_library(monkeypatch):
    """No stored walk or index from another test: the merge and the coalescing look at them."""
    monkeypatch.setattr(assets, "_index", {})
    monkeypatch.setattr(assets, "_walks", {})
    monkeypatch.setattr(assets, "_walk_t0", {})
    monkeypatch.setattr(brushes, "_index", None)
    monkeypatch.setattr(brushes, "_walk", None)
    monkeypatch.setattr(brushes, "_walk_t0", float("-inf"))


# --- the walker -----------------------------------------------------------------------------------

def test_order_and_first_folder_wins(two_folders):
    a, b = two_folders
    w = brushes.walk_sources(srcs(a, b))
    assert [(i["label"], i["rel"], i["name"]) for i in w.items] == [
        ("folder 0", "", "Alpha"), ("folder 0", "", "beta"), ("folder 0", "", "Clay Buildup"),
        ("folder 0", "Sub", "inner"), ("folder 1", "", "only second")]      # case-insensitive order, files first
    assert w.index["claybuildup"] == a / "Clay Buildup.zbp"
    assert [s["count"] for s in w.sources] == [4, 2]                # the duplicate is counted, not listed
    assert not brushes.walk_error(w)


def test_list_and_lookup_agree(two_folders):
    w = brushes.walk_sources(srcs(*two_folders))
    assert set(w.index) == {tags._norm(i["name"]) for i in w.items}
    for i in w.items:
        assert w.index[tags._norm(i["name"])] == Path(i["path"])


def test_underscore_folders_are_skipped(two_folders):
    names = {i["name"] for i in brushes.walk_sources(srcs(*two_folders)).items}
    assert "skipped" not in names and "nope" not in names


def test_not_recursive_source(two_folders):
    a, _ = two_folders
    w = brushes.walk_sources([("x", a, False)])
    assert "inner" not in {i["name"] for i in w.items}


def test_extensions_filter(two_folders):
    a, _ = two_folders
    assert [i["name"] for i in brushes.walk_sources(srcs(a), (".txt",)).items] == ["notes"]


def test_junction_loop_ends(tmp_path):
    root = tmp_path / "lib"
    touch(root / "a.zbp")
    touch(root / "sub" / "b.zbp")
    if not junction(root / "sub" / "loop", root):
        pytest.skip("cannot make a junction here")
    w = brushes.walk_sources(srcs(root))
    assert sorted(i["name"] for i in w.items) == ["a", "b"]


def test_a_linked_folder_is_followed(tmp_path):
    root, elsewhere = tmp_path / "lib", tmp_path / "elsewhere"
    touch(root / "a.zbp")
    touch(elsewhere / "linked.zbp")
    if not junction(root / "Link", elsewhere):
        pytest.skip("cannot make a junction here")
    w = brushes.walk_sources(srcs(root))
    assert [(i["rel"], i["name"]) for i in w.items] == [("", "a"), ("Link", "linked")]


def test_missing_folder_is_not_an_error_but_a_vanished_one_is(tmp_path):
    f = tmp_path / "lib"
    touch(f / "a.zbp")
    assert brushes.walk_error(brushes.walk_sources(srcs(tmp_path / "never"))) is None
    assert brushes.walk_error(brushes.walk_sources(srcs(f))) is None
    for p in f.iterdir():
        p.unlink()
    f.rmdir()
    w = brushes.walk_sources(srcs(f))
    assert "before" in brushes.walk_error(w) and w.sources[0]["exists"] is False


def test_unreachable_drive_is_an_error():
    free = [c for c in "QRSTUVWXYZ" if not os.path.exists(c + ":\\")]
    if not free:
        pytest.skip("every drive letter is in use")
    w = brushes.walk_sources(srcs(Path(free[0] + ":\\ZBrush\\Brushes")))
    assert "cannot be reached" in brushes.walk_error(w)


def test_only_the_folder_that_cannot_be_read_keeps_its_items(two_folders):
    a, b = two_folders
    good = brushes.walk_sources(srcs(a, b))
    assert brushes.merge_walk(None, good) is good
    away = b.with_name("second away")
    b.rename(away)                                      # was there before and cannot be read now
    touch(a / "saved now.zbp")
    bad = brushes.walk_sources(srcs(a, b))
    merged = brushes.merge_walk(good, bad)
    assert merged.index["savednow"] == a / "saved now.zbp"            # the readable folder is read afresh
    assert merged.index["onlysecond"] == b / "only second.zbp"         # the unreadable one keeps what it had
    assert "second" in brushes.walk_error(merged) and "before" in brushes.walk_error(merged)
    assert merged.sources[1]["kept"] is True and merged.sources[1]["count"] == 2
    assert "kept" not in merged.sources[0] and "kept" not in good.sources[1]      # the old walk is not changed
    assert bad.sources[1]["count"] == 0 and "kept" not in bad.sources[1]
    away.rename(b)
    back = brushes.merge_walk(merged, brushes.walk_sources(srcs(a, b)))
    assert brushes.walk_error(back) is None and not any(s.get("kept") for s in back.sources)
    assert back.index == brushes.walk_sources(srcs(a, b)).index
    b.rename(away)
    forgot = brushes.merge_walk(merged, brushes.walk_sources(srcs(a)))  # the user forgot the folder: it drops out
    assert len(forgot.sources) == 1 and "onlysecond" not in forgot.index


def test_library_and_find_come_from_one_walk(two_folders, monkeypatch):
    a, b = two_folders
    monkeypatch.setattr(assets, "sources", lambda kind: srcs(a, b))
    monkeypatch.setattr(assets, "exts", lambda kind: (".zbp",))
    w = assets.library("alpha")
    assert assets.find("alpha", "CLAY buildup") == a / "Clay Buildup.zbp"
    assert assets.find("alpha", "Only  Second").name == "only second.zbp"
    assert {tags._norm(i["name"]) for i in w.items} == set(assets.index("alpha"))
    assert assets.last_walk("alpha") is w and assets.has_built("alpha") and not assets.has_built("material")
    gen = assets.generation
    assets.library("alpha")
    assert assets.generation == gen                 # nothing changed: no new generation
    touch(a / "added.zbp")
    assets.library("alpha")
    assert assets.generation == gen + 1
    away = b.with_name("second away")
    b.rename(away)
    w = assets.library("alpha")                     # an error, and nothing else changed: the same index
    assert brushes.walk_error(w) and assets.generation == gen + 1
    assert assets.last_walk("alpha") is w and w.sources[1]["kept"] is True
    touch(a / "another.zbp")
    assets.library("alpha")                         # an error, and a new file in the other folder
    assert assets.generation == gen + 2
    assert assets.find("alpha", "another") == a / "another.zbp" and assets.find("alpha", "only second")


class BlockedWalk:
    """brushes.walk_sources that, after the first call, waits for release() before it walks."""

    def __init__(self, monkeypatch):
        self.real = brushes.walk_sources
        self.calls = 0
        self.started = threading.Event()
        self.go = threading.Event()
        monkeypatch.setattr(brushes, "walk_sources", self)

    def __call__(self, *a, **k):
        self.calls += 1
        if self.calls > 1:
            self.started.set()
            assert self.go.wait(5)
        return self.real(*a, **k)


@pytest.mark.parametrize("kind", ["alpha", "brush"])
def test_a_slow_walk_does_not_hold_up_a_find(two_folders, monkeypatch, kind):
    monkeypatch.setattr(assets, "sources", lambda k: srcs(*two_folders))
    monkeypatch.setattr(assets, "exts", lambda k: (".zbp",))
    monkeypatch.setattr(brushes, "brush_sources", lambda: srcs(*two_folders))
    walk = BlockedWalk(monkeypatch)
    assets.library(kind)
    t = threading.Thread(target=assets.library, args=(kind,))
    t.start()
    try:
        assert walk.started.wait(5)
        found = []
        f = threading.Thread(target=lambda: found.append(assets.find(kind, "Clay Buildup")))
        f.start()
        f.join(0.5)
        assert found == [two_folders[0] / "Clay Buildup.zbp"]          # while the walk is still waiting
        lock = brushes._index_lock if kind == "brush" else assets._index_lock
        assert lock.acquire(timeout=0.5)
        lock.release()
    finally:
        walk.go.set()
        t.join(5)
    assert not t.is_alive()


def test_callers_waiting_for_a_walk_share_the_next_one(two_folders, monkeypatch):
    monkeypatch.setattr(assets, "sources", lambda k: srcs(*two_folders))
    monkeypatch.setattr(assets, "exts", lambda k: (".zbp",))
    walk = BlockedWalk(monkeypatch)
    assets.library("alpha")
    out = {}
    first = threading.Thread(target=lambda: out.setdefault("first", assets.library("alpha")))
    first.start()
    assert walk.started.wait(5)
    waiting = [threading.Thread(target=lambda n=n: out.setdefault(n, assets.library("alpha"))) for n in ("b", "c")]
    for w in waiting:
        w.start()
    threading.Event().wait(0.2)                         # both have asked and wait for the walk on show to end
    walk.go.set()
    for w in [first] + waiting:
        w.join(5)
    assert walk.calls - 1 <= 2                          # three callers, two walks: the first's and one for both
    assert out["b"].index == out["c"].index and out["b"] is out["c"]


def test_get_library_reports_an_unreadable_source(two_folders, monkeypatch):
    webapi = pytest.importorskip("webapi")
    monkeypatch.setattr(assets, "sources", lambda kind: srcs(*two_folders))
    monkeypatch.setattr(assets, "exts", lambda kind: (".zbp",))
    monkeypatch.setattr(assets, "_index", {})
    api = webapi.LibraryApi()
    r = api.get_library(False, "alpha")
    assert r["error"] is None and len(r["items"]) == 5
    assert r["items"][0]["category"] == "folder 0" and r["items"][3]["category"] == "folder 0/Sub"
    free = [c for c in "QRSTUVWXYZ" if not os.path.exists(c + ":\\")]
    if free:
        monkeypatch.setattr(assets, "sources", lambda kind: srcs(*two_folders) + srcs(Path(free[0] + ":\\Gone")))
        r = api.get_library(True, "alpha")
        assert "cannot be reached" in r["error"]
        assert len(r["items"]) == 5                 # what was read is still returned, with the error
        assert len(assets.index("alpha")) == 5      # and the lookup keeps what it had


# --- names in an added folder ---------------------------------------------------------------------

def own_and_added(tmp_path, *added):
    """An own source with 10.psd, then each added folder; the sources and the walk."""
    own = tmp_path / "own"
    touch(own / "10.psd")
    s = [("own", own, True)] + [(brushes.added_label(f), f, True) for f in added]
    return s, brushes.walk_sources(s, (".psd", ".png"))


def test_an_added_file_whose_name_is_taken_gets_its_subfolder(tmp_path):
    added = tmp_path / "Added"
    touch(added / "PackA" / "10.png")
    _, w = own_and_added(tmp_path, added)
    assert [i["name"] for i in w.items] == ["10", "10 (PackA)"]
    assert w.index[tags._norm("10 (PackA)")] == added / "PackA" / "10.png"
    assert w.items[1]["stem"] == "10" and w.items[1]["rel"] == "PackA"
    assert w.names == {tags._norm("10"): "10", tags._norm("10 (PackA)"): "10 (PackA)"}


def test_a_top_file_of_an_added_folder_gets_the_folder_name(tmp_path):
    added = tmp_path / "Added"
    touch(added / "10.png")
    _, w = own_and_added(tmp_path, added)
    assert [i["name"] for i in w.items] == ["10", "10 (Added)"]


def test_the_second_subfolder_gets_the_whole_path(tmp_path):
    added = tmp_path / "Added"
    touch(added / "PackA" / "a" / "10.png")
    touch(added / "PackA" / "b" / "10.png")
    _, w = own_and_added(tmp_path, added)
    assert [i["name"] for i in w.items] == ["10", "10 (PackA)", "10 (PackA, b)"]
    assert w.index[tags._norm("10 (PackA)")] == added / "PackA" / "a" / "10.png"


def test_two_added_folders_with_one_name_get_the_display_name(tmp_path):
    one, two = tmp_path / "x" / "Alphas", tmp_path / "y" / "Alphas"
    touch(one / "10.png")
    touch(two / "10.png")
    _, w = own_and_added(tmp_path, one, two)
    assert [i["name"] for i in w.items] == ["10", "10 (Alphas)", "10 (Alphas (2))"]
    assert w.index[tags._norm("10 (Alphas (2))")] == two / "10.png"


def test_a_file_beside_one_with_its_stem_is_hidden(tmp_path):
    added = tmp_path / "Added"
    touch(added / "10.png")
    touch(added / "10.psd")
    _, w = own_and_added(tmp_path, added)                # one file per stem in a folder: ZBrush would call both "10"
    assert [i["name"] for i in w.items] == ["10", "10 (Added)"]
    assert w.items[1]["path"] == str(added / "10.png")
    assert w.sources[1]["hidden"] == 1 and w.sources[1]["count"] == 2
    touch(added / "sub" / "20.png")
    touch(added / "sub" / "20.psd")
    w = brushes.walk_sources([(brushes.added_label(added), added, True)], (".png", ".psd"))
    assert [i["name"] for i in w.items] == ["10", "20"]     # with no other 10, no qualifying, still one each
    assert w.sources[0]["hidden"] == 2


def test_a_qualified_name_is_a_plain_name(tmp_path):
    import config
    added = tmp_path / "Added"
    try:
        touch(added / "a:b..c" / "10.png")
    except OSError:                                     # Windows refuses the colon; the ".." is the point
        touch(added / "a_b..c" / "10.png")
    _, w = own_and_added(tmp_path, added)
    names = [i["name"] for i in w.items]
    assert len(names) == 2 and names[1] != "10"
    assert not config._bad_asset_name(names[1])


def test_own_sources_never_qualify_or_hide(two_folders):
    w = brushes.walk_sources(srcs(*two_folders))
    assert all(i["name"] == i["stem"] for i in w.items)
    assert [s["hidden"] for s in w.sources] == [0, 0]
    assert "display" not in w.sources[0] and "base" not in w.sources[0]


def test_files_and_names_line_up_with_sources_and_index(tmp_path, two_folders):
    added = tmp_path / "Added"
    touch(added / "PackA" / "10.png")
    touch(added / "beta.zbp")
    s = srcs(*two_folders) + [(brushes.added_label(added), added, True)]
    w = brushes.walk_sources(s, (".zbp", ".png"))
    assert len(w.files) == len(w.sources) == 3
    assert [len(f) for f in w.files] == [rep["count"] for rep in w.sources]
    assert set(w.names) == set(w.index)
    assert w.names[tags._norm("beta (Added)")] == "beta (Added)"
    assert w.sources[2]["display"] == "Added" and w.sources[2]["base"] == "Added"


# --- zbrush_dirs ----------------------------------------------------------------------------------

def maxon(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setattr(brushes._installs, "find_installs", lambda: [])
    return tmp_path / "roaming" / "Maxon"


def test_stale_installpath_is_skipped(tmp_path, monkeypatch):
    m = maxon(tmp_path, monkeypatch)
    gone = tmp_path / "Uninstalled ZBrush 2027"
    gone.mkdir()                                      # the folder is there but ZBrush.exe is not
    here = tmp_path / "ZBrush 2026"
    touch(here / "ZBrush.exe")
    for name, folder in (("ZBrush 2027_AAAA", gone), ("ZBrush 2026_BBBB", here)):
        touch(m / name / "installpath.txt").write_text(str(folder), encoding="utf-8")
    assert brushes.zbrush_dirs()["install"] == here


def test_userassets_comes_from_the_newest_that_has_one(tmp_path, monkeypatch):
    m = maxon(tmp_path, monkeypatch)
    touch(m / "ZBrush 2026_BBBB" / "userassets_path.txt").write_text(str(tmp_path / "assets"), encoding="utf-8")
    (m / "ZBrush 2027_AAAA").mkdir()
    d = brushes.zbrush_dirs()
    assert d["user_assets"] == tmp_path / "assets" and d["install"] is None


@pytest.mark.skipif(os.name != "nt", reason="the ANSI code page is a Windows thing")
def test_path_files_in_the_ansi_code_page(tmp_path, monkeypatch):
    m = maxon(tmp_path, monkeypatch)
    folder = tmp_path / "Caf\u00e9 ZBrush"
    try:
        raw = str(folder).encode("mbcs")
    except UnicodeEncodeError:
        pytest.skip("this code page has no e-acute")
    touch(folder / "ZBrush.exe")
    touch(m / "ZBrush 2026_BBBB" / "installpath.txt").write_bytes(raw)
    try:
        raw.decode("utf-8")
        pytest.skip("this code page's bytes are valid UTF-8")
    except UnicodeDecodeError:
        pass
    assert brushes.zbrush_dirs()["install"] == folder


def test_path_files_in_utf8_with_a_bom(tmp_path, monkeypatch):
    m = maxon(tmp_path, monkeypatch)
    folder = tmp_path / "Z\u00fcrich"
    touch(folder / "ZBrush.exe")
    touch(m / "ZBrush 2026_BBBB" / "installpath.txt").write_bytes(b"\xef\xbb\xbf" + f'"{folder}"\r\n'.encode("utf-8"))
    assert brushes.zbrush_dirs()["install"] == folder


# --- a tag fan and a brush saved after the scan -----------------------------------------------------

class FakeAssets:
    def __init__(self):
        self.generation = 1
        self.idx = {k: {} for k in ("brush", "alpha", "material", "texture")}
        self.listed = {}                            # {kind: {key: listed name}}, as assets.names() gives
        self.rescans = []
        self.done = threading.Event()
        self.refuse = False
        self.gate = threading.Event()               # the worker waits for it, so a test sees the state before the rescan

    def index(self, kind, refresh=False):
        return self.idx[kind]

    def names(self, kind):
        return self.listed.get(kind, {})

    def rescan(self, kind, install=None):
        self.gate.wait(5)
        self.rescans.append(kind)
        self.done.set()
        if self.refuse:
            return False
        self.idx["brush"]["newbrush"] = Path("C:/x/NewBrush.zbp")
        self.generation += 1
        return True


class FakeTags:
    mtime = 1

    def has(self, key):
        return True

    def items_with(self, key, kind=None):
        return ["brush:newbrush"] if kind == "brush" else []

    def color(self, key):
        return "#ff0000"

    def label(self, key):
        return "Fresh"


class FakeUsage:
    version = 1

    def load(self):
        return self

    def rank(self, names):
        return list(names)


def expander(monkeypatch, fake):
    monkeypatch.setattr(expand, "assets", fake)
    return expand.Expander(SimpleNamespace(ring={}), FakeUsage(), FakeTags())


def wait_idle(ex, fake):
    assert fake.done.wait(5)
    for _ in range(500):
        if not ex._rescanning:
            return
        threading.Event().wait(0.01)
    raise AssertionError("the rescan thread did not finish")


def test_missing_tagged_item_triggers_a_rescan_and_the_next_build_has_it(monkeypatch):
    fake = FakeAssets()
    ex = expander(monkeypatch, fake)
    assert ex.tag_menu("fresh") is None                 # nothing installed yet: no fan, and no waiting for the walk
    fake.gate.set()
    wait_idle(ex, fake)
    assert fake.rescans == ["brush"]
    menu = ex.tag_menu("fresh")                         # the new generation: built again
    assert [i.label for i in menu.items] == ["NewBrush"]


def test_a_fan_with_a_missing_item_is_not_cached_and_asks_at_most_every_few_seconds(monkeypatch):
    fake = FakeAssets()
    fake.refuse = True
    fake.gate.set()
    fake.idx["brush"]["other"] = Path("C:/x/Other.zbp")
    tags = FakeTags()
    tags.items_with = lambda key, kind=None: ["brush:other", "brush:newbrush"] if kind == "brush" else []
    monkeypatch.setattr(expand, "assets", fake)
    ex = expand.Expander(SimpleNamespace(ring={}), FakeUsage(), tags)
    first = ex.tag_menu("fresh")
    assert [i.label for i in first.items] == ["Other"]
    wait_idle(ex, fake)
    assert "fresh" not in ex._cache                     # a menu missing an item is never served from the cache
    fake.idx["brush"]["newbrush"] = Path("C:/x/NewBrush.zbp")   # found later, same generation (the old race)
    assert sorted(i.label for i in ex.tag_menu("fresh").items) == ["NewBrush", "Other"]
    assert fake.rescans == ["brush"]                    # the second build came too soon to ask again


def test_a_refused_rescan_is_asked_again_at_the_next_build(monkeypatch):
    monkeypatch.setattr(expand, "RESCAN_ASK_S", 0)       # the few-seconds limit is the test above
    fake = FakeAssets()
    fake.refuse = True
    ex = expander(monkeypatch, fake)
    assert ex.tag_menu("fresh") is None
    fake.gate.set()
    wait_idle(ex, fake)
    fake.refuse = False
    fake.done.clear()
    fake.gate.clear()
    assert ex.tag_menu("fresh") is None                 # built again (the cache was dropped), asks again
    fake.gate.set()
    wait_idle(ex, fake)
    assert len(fake.rescans) == 2
    assert ex.tag_menu("fresh") is not None


def test_a_tag_fan_lists_the_qualified_name_of_an_item(monkeypatch):
    fake = FakeAssets()
    fake.idx["alpha"]["10(packa)"] = Path("C:/x/PackA/10.png")
    fake.idx["alpha"]["11"] = Path("C:/x/11.png")
    fake.listed["alpha"] = {"10(packa)": "10 (PackA)"}            # 11 has no entry: its stem is the name
    tg = FakeTags()
    tg.items_with = lambda key, kind=None: ["alpha:10(packa)", "alpha:11"] if kind == "alpha" else []
    monkeypatch.setattr(expand, "assets", fake)
    ex = expand.Expander(SimpleNamespace(ring={}), FakeUsage(), tg)
    menu = ex.tag_menu("fresh")
    assert [(i.kind, i.label, i.data) for i in menu.items] == [
        ("alpha", "10 (PackA)", {"alpha": "10 (PackA)"}), ("alpha", "11", {"alpha": "11"})]


# --- folders the user added are the last sources -----------------------------------------------------

@pytest.fixture
def added(tmp_path, monkeypatch):
    """studio.json in a temp config folder with one added folder per kind."""
    import json
    import paths
    folder = tmp_path / "My Packs"
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "cfg"))
    brushes._settings_cache.clear()
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "studio.json").write_text(json.dumps({"library_folders": {
        k: [str(folder)] for k in ("brush", "alpha", "material", "texture")}}), encoding="utf-8")
    return folder


def test_an_added_folder_is_the_last_source_of_a_kind(tmp_path, monkeypatch, added):
    m = maxon(tmp_path, monkeypatch)
    touch(m / "ZBrush 2026_BBBB" / "userassets_path.txt").write_text(str(tmp_path / "assets"), encoding="utf-8")
    here = tmp_path / "ZBrush 2026"
    touch(here / "ZBrush.exe")
    touch(m / "ZBrush 2026_BBBB" / "installpath.txt").write_text(str(here), encoding="utf-8")
    for kind in ("alpha", "material", "texture", "brush"):
        src = assets.sources(kind)
        assert len(src) > 1 and src[-1] == (brushes.added_label(added), added, True)
        assert not any(brushes.is_added(label) for label, _, _ in src[:-1])
    assert brushes.brush_sources()[-1] == (brushes.added_label(added), added, True)


def test_with_no_zbrush_an_added_folder_is_the_only_source(tmp_path, monkeypatch, added):
    maxon(tmp_path, monkeypatch)
    assert brushes.zbrush_dirs() == {"user_assets": None, "install": None}
    for kind in ("alpha", "brush"):
        assert assets.sources(kind) == [(brushes.added_label(added), added, True)]
    assert brushes.brush_sources() == [(brushes.added_label(added), added, True)]


def test_the_older_zbrush_installs_do_not_search_added_folders(tmp_path, added):
    for kind in ("alpha", "material", "texture", "brush"):
        assert not any(brushes.is_added(label) for label, _, _ in assets.install_sources(tmp_path / "ZBrush 2022", kind))
    assert not any(brushes.is_added(label) for label, _, _ in brushes.install_brush_sources(tmp_path / "ZBrush 2022"))


def test_source_labels_name_an_added_folder_by_its_display_name(added):
    for kind in ("alpha", "brush"):
        labels = assets.source_labels(kind)
        assert labels[brushes.added_label(added)] == "My Packs"
        assert labels[brushes.added_label(added)] == brushes.display_names([added])[0]
    assert assets.source_labels("alpha")["install ZData/Alphas"] == "ZBrush"


def test_name_of_and_names_read_the_last_walk(tmp_path):
    assert assets.name_of("alpha", "10") is None and assets.names("alpha") == {}
    pack = tmp_path / "Pack"
    touch(pack / "10.png")
    touch(tmp_path / "Other" / "10.png")
    walk = brushes.walk_sources([("first", tmp_path / "first", True),
                                 (brushes.added_label(tmp_path / "Pack"), pack, True),
                                 (brushes.added_label(tmp_path / "Other"), tmp_path / "Other", True)], (".png",))
    assets._walks["alpha"] = walk
    assert assets.name_of("alpha", "10 (Pack)") is None
    assert assets.name_of("alpha", "10") == "10"
    assert assets.name_of("alpha", "10 (Other)") == "10 (Other)"
    assert assets.name_of("alpha", "10(other)") == "10 (Other)"            # any spelling
    assert assets.names("alpha") is walk.names
