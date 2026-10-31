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


def test_an_index_survives_a_walk_that_failed(two_folders):
    good = brushes.walk_sources(srcs(*two_folders))
    free = [c for c in "QRSTUVWXYZ" if not os.path.exists(c + ":\\")]
    if not free:
        pytest.skip("every drive letter is in use")
    bad = brushes.walk_sources(srcs(Path(free[0] + ":\\Gone")))
    keep, changed = brushes.keep_index(good.index, bad)
    assert keep is good.index and changed is False
    keep, changed = brushes.keep_index(None, bad)
    assert keep == {} and changed is True
    keep, changed = brushes.keep_index(good.index, good)
    assert changed is False


def test_library_and_find_come_from_one_walk(two_folders, monkeypatch):
    monkeypatch.setattr(assets, "sources", lambda kind: srcs(*two_folders))
    monkeypatch.setattr(assets, "exts", lambda kind: (".zbp",))
    monkeypatch.setattr(assets, "_index", {})
    w = assets.library("alpha")
    assert assets.find("alpha", "CLAY buildup") == two_folders[0] / "Clay Buildup.zbp"
    assert assets.find("alpha", "Only  Second").name == "only second.zbp"
    assert {tags._norm(i["name"]) for i in w.items} == set(assets.index("alpha"))
    gen = assets.generation
    assets.library("alpha")
    assert assets.generation == gen                 # nothing changed: no new generation
    touch(two_folders[0] / "added.zbp")
    assets.library("alpha")
    assert assets.generation == gen + 1


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
        self.rescans = []
        self.done = threading.Event()
        self.refuse = False
        self.gate = threading.Event()               # the worker waits for it, so a test sees the state before the rescan

    def index(self, kind, refresh=False):
        return self.idx[kind]

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


def test_a_refused_rescan_is_asked_again_at_the_next_build(monkeypatch):
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
