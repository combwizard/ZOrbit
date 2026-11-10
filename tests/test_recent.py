"""The Recent item, {"recent": "project" | "tool" | "any"}: reading ZBrush's LightboxRecentFiles.cfg (recent.py), where
that file is for each ZBrush version, the item's checks and default labels (config.py), the fan the slot opens
(expand.py) and what a pick does (radiald.py)."""
import json
import os

import pytest

import config
import expand
import radiald
import recent
from test_capture import app  # noqa: F401  (a fixture: the app with its files in a throw-away folder)
from test_config import GOOD_MENUS, load, load_menus, one_item_menu, problems  # noqa: F401  (fixtures and helpers)


@pytest.fixture(autouse=True)
def fresh():
    recent.reset()
    yield
    recent.reset()


def make(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def cfg_bytes(*entries, encoding="mbcs"):
    """A LightboxRecentFiles.cfg as ZBrush writes it: the paths, each ended by a NUL, in the ANSI code page."""
    return b"".join(str(e).encode(encoding) + b"\0" for e in entries)


@pytest.fixture
def listed(tmp_path, monkeypatch):
    """listed(*entries) -> the cfg file holding those entries, which recent.entries reads from now on."""
    cfg = tmp_path / "ZStartup" / "ConfigFiles" / recent.FILE_NAME
    cfg.parent.mkdir(parents=True)
    monkeypatch.setattr(recent, "list_file", lambda install=None: (cfg, ""))

    def write(*entries):
        cfg.write_bytes(cfg_bytes(*entries))
        recent.reset()                          # the cache is keyed on the file's time and size, which may not move
        return cfg
    return write


# --- the file's format -----------------------------------------------------------------------------
def test_the_entries_are_split_on_nul_and_kept_newest_first():
    data = cfg_bytes(r"C:\A\One.zpr", r"C:\A\Two.zpr", r"C:\A\Three.zpr")
    assert recent.parse(data, "project") == [r"C:\A\One.zpr", r"C:\A\Two.zpr", r"C:\A\Three.zpr"]


def test_the_list_is_read_in_the_ansi_code_page():
    data = "C:\\Mod\u00e8les\\H\u00e9ro.ztl".encode("mbcs") + b"\0"      # as ZBrush writes it: not UTF-8
    assert recent.parse(data, "tool") == ["C:\\Mod\u00e8les\\H\u00e9ro.ztl"]


def test_bytes_that_do_not_decode_do_not_stop_the_rest():
    data = b"C:\\A\\\x81\x81bad.ztl\0" + cfg_bytes(r"C:\A\Good.ztl")
    assert recent.parse(data, "tool")[-1] == r"C:\A\Good.ztl"


@pytest.mark.parametrize("kind, kept", [
    ("project", [r"C:\A\Head.ZPR", r"C:\A\Body.zpr"]),
    ("tool", [r"C:\A\Dog.ZTL", r"C:\A\Cat.ztl"]),
    ("any", [r"C:\A\Head.ZPR", r"C:\A\Dog.ZTL", r"C:\A\Body.zpr", r"C:\A\Cat.ztl"]),
])
def test_only_projects_or_tools_are_kept_in_any_case(kind, kept):
    data = cfg_bytes(r"C:\A\Head.ZPR", r"C:\A\Dog.ZTL", r"C:\A\Notes.txt", r"C:\A\Body.zpr", r"C:\A\Cat.ztl",
                     r"C:\A\Model.obj")
    assert recent.parse(data, kind) == kept


def test_folders_names_without_an_extension_and_empty_entries_are_left_out():
    data = cfg_bytes(r"C:\Programs\ZBrush 2026\ZProjects", r"C:\A\Readme", "", r"C:\A\Hero.ztl", "   ")
    assert recent.parse(data, "any") == [r"C:\A\Hero.ztl"]


def test_a_repeat_counts_once_whatever_its_case_and_slashes():
    data = cfg_bytes("C:\\PROGRAMS\\ZBRUSH 2022/ZProjects/DemoHead.ZPR",
                     r"C:\Programs\ZBrush 2022\ZProjects\DemoHead.zpr",
                     "c:/programs/zbrush 2022/zprojects/demohead.zpr", r"C:\A\Other.zpr")
    assert recent.parse(data, "project") == [r"C:\PROGRAMS\ZBRUSH 2022\ZProjects\DemoHead.ZPR", r"C:\A\Other.zpr"]


def test_mixed_slashes_are_made_one_kind():
    assert recent.parse(cfg_bytes("C:/Programs/ZBrush 2026/Lightbox\\Tools/Dog.ZTL"), "tool") == \
        [r"C:\Programs\ZBrush 2026\Lightbox\Tools\Dog.ZTL"]


def test_network_and_relative_paths_are_left_out():
    data = cfg_bytes(r"\\server\share\Hero.ztl", "//server/share/Dog.ztl", r"Models\Cat.ztl", r"D:\Models\Ok.ztl")
    assert recent.parse(data, "tool") == [r"D:\Models\Ok.ztl"]


def test_a_fan_item_is_named_after_the_file_and_is_a_project_or_a_tool():
    assert recent.label(r"C:\A\DemoHead.ZPR") == "DemoHead" and recent.item_kind(r"C:\A\DemoHead.ZPR") == "project"
    assert recent.label(r"C:\A\my.dog.ztl") == "my.dog" and recent.item_kind(r"C:\A\my.dog.ztl") == "tool"


# --- the files on disk -----------------------------------------------------------------------------
def read(kind, limit, install=None, log=None):
    """What a slot shows once the worker has read the list: a refresh done here, then the open path's answer."""
    recent.refresh(kind, limit, install, log)
    return recent.entries(kind, limit, install, log)


def test_files_that_are_not_there_drop_out(listed, tmp_path):
    a, b = make(tmp_path / "A.zpr"), make(tmp_path / "B.zpr")
    listed(a, tmp_path / "Gone.zpr", b)
    assert read("project", 12) == [str(a), str(b)]


def test_a_folder_named_like_a_project_drops_out(listed, tmp_path):
    (tmp_path / "Odd.zpr").mkdir()
    a = make(tmp_path / "A.zpr")
    listed(tmp_path / "Odd.zpr", a)
    assert read("project", 12) == [str(a)]


def test_the_list_stops_at_the_limit_newest_first(listed, tmp_path):
    files = [make(tmp_path / f"P{i:02}.zpr") for i in range(30)]
    listed(*files)
    assert read("project", 12) == [str(f) for f in files[:12]]
    assert read("project", 4) == [str(f) for f in files[:4]]


def test_the_limit_counts_files_that_are_there(listed, tmp_path):
    a, b = make(tmp_path / "A.ztl"), make(tmp_path / "B.ztl")
    listed(*[tmp_path / f"Gone{i}.ztl" for i in range(5)], a, tmp_path / "Gone.ztl", b)
    assert read("tool", 2) == [str(a), str(b)]


def test_any_mixes_both_in_the_list_order(listed, tmp_path):
    p, t, q = make(tmp_path / "Head.zpr"), make(tmp_path / "Dog.ztl"), make(tmp_path / "Body.zpr")
    listed(p, t, q)
    assert read("any", 12) == [str(p), str(t), str(q)]
    assert read("tool", 12) == [str(t)]


def test_an_unknown_kind_or_no_room_gives_nothing(listed, tmp_path):
    listed(make(tmp_path / "A.zpr"))
    assert read("brush", 12) == [] and read("project", 0) == []


def test_a_missing_list_gives_nothing_and_is_logged_once(listed, tmp_path):
    cfg = listed()
    cfg.unlink()
    said = []
    assert read("project", 12, log=said.append) == []
    assert read("tool", 12, log=said.append) == []
    assert len(said) == 1 and "is not there" in said[0] and recent.FILE_NAME in said[0]


def test_a_list_that_cannot_be_read_gives_nothing_and_is_logged_once(listed, tmp_path, monkeypatch):
    listed(make(tmp_path / "A.zpr"))

    def refuse(self):
        raise PermissionError("locked")
    monkeypatch.setattr(recent.Path, "read_bytes", refuse)
    said = []
    assert read("project", 12, log=said.append) == []
    assert read("project", 12, log=said.append) == []
    assert len(said) == 1 and "cannot be read" in said[0]


def test_no_zbrush_gives_nothing_and_is_logged_once(monkeypatch):
    monkeypatch.setattr(recent, "list_file", lambda install=None: (None, "no ZBrush installation found"))
    said = []
    assert read("any", 12, log=said.append) == []
    assert read("any", 12, log=said.append) == []
    assert said == ["recent files: no ZBrush installation found; the recent slot stays empty"]


# --- which file ------------------------------------------------------------------------------------
def ins(year, path=r"C:\Programs\ZBrush"):
    return {"name": f"ZBrush {year}", "year": year, "path": f"{path} {year}", "python": year >= 2026,
            "supported": True}


def test_zbrush_2026_and_newer_keep_the_list_in_the_user_assets_folder(monkeypatch, tmp_path):
    import brushes
    seen = []
    monkeypatch.setattr(brushes, "user_assets_of", lambda i, stamps=None: seen.append(i["path"]) or tmp_path / "Assets")
    path, why = recent.list_file(ins(2026))
    assert path == tmp_path / "Assets" / "ZStartup" / "ConfigFiles" / "LightboxRecentFiles.cfg" and why == ""
    assert seen == [r"C:\Programs\ZBrush 2026"]


def test_zbrush_2026_with_no_user_assets_folder_and_no_stamp_has_no_list(monkeypatch):
    import brushes
    monkeypatch.setattr(brushes, "user_assets_of", lambda i, stamps=None: None)
    monkeypatch.setattr(brushes, "stamp_of", lambda i, stamps=None: None)
    path, why = recent.list_file(ins(2027))
    assert path is None and "no user assets folder" in why


def test_zbrush_2026_before_a_user_assets_folder_is_chosen_keeps_the_list_in_its_stamp_folder(monkeypatch, tmp_path):
    """A fresh ZBrush 2026 writes no userassets_path.txt until a folder is chosen, and keeps ZStartup (the recent list
    included) in its own folder under %APPDATA%\\Maxon. Found on a clean install: the slot stayed empty."""
    import brushes
    appdata = tmp_path / "AppData"
    own = appdata / "Maxon" / "Maxon ZBrush 2026_ABCD1234"
    other = appdata / "Maxon" / "ZBrush 2027_0F0F0F0F"
    put(own / "installpath.txt", r"C:\Programs\ZBrush 2026")
    put(other / "installpath.txt", r"C:\Programs\ZBrush 2027")
    put(other / "userassets_path.txt", str(tmp_path / "Assets 2027"))
    monkeypatch.setenv("APPDATA", str(appdata))
    path, why = recent.list_file(ins(2026))
    assert path == own / "ZStartup" / "ConfigFiles" / "LightboxRecentFiles.cfg" and why == ""


def test_the_stamp_folder_of_an_install_is_its_own_else_one_of_its_year(monkeypatch, tmp_path):
    import brushes
    maxon = tmp_path / "Maxon"
    a = put(maxon / "ZBrush 2026_AAAA" / "installpath.txt", r"D:\Elsewhere\ZBrush 2026").parent
    b = put(maxon / "ZBrush 2026_BBBB" / "installpath.txt", r"C:\Programs\ZBrush 2026").parent
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert brushes.stamp_of(ins(2026)) == b                      # its own, by installpath.txt
    assert brushes.stamp_of(ins(2026, path=r"E:\Moved\ZBrush")) in (a, b)   # none names it: one of its year
    assert brushes.stamp_of(ins(2028)) is None


@pytest.mark.parametrize("year", [2022, 2023, 2024, 2025])
def test_zbrush_2022_to_2025_keep_the_list_in_public_documents(monkeypatch, tmp_path, year):
    monkeypatch.setattr(recent, "public_documents", lambda: str(tmp_path / "Public" / "Documents"))
    path, why = recent.list_file(ins(year))
    assert path == tmp_path / "Public" / "Documents" / f"ZBrushData{year}" / "ZStartup" / "ConfigFiles" / \
        "LightboxRecentFiles.cfg"


def test_without_the_zbrush_in_front_the_librarys_zbrush_is_used(monkeypatch, tmp_path):
    import brushes
    exe = make(tmp_path / "ZBrush 2026" / "ZBrush.exe")
    make(exe.parent / "python311.dll")                  # ZBrush 2026 and newer: it has the Python API
    monkeypatch.setattr(brushes, "zbrush_dirs", lambda: {"install": exe.parent, "user_assets": tmp_path / "Assets"})
    path, _ = recent.list_file()
    assert path == tmp_path / "Assets" / "ZStartup" / "ConfigFiles" / "LightboxRecentFiles.cfg"


def test_without_the_zbrush_in_front_an_older_librarys_zbrush_uses_public_documents(monkeypatch, tmp_path):
    import brushes
    exe = make(tmp_path / "ZBrush 2024" / "ZBrush.exe")
    monkeypatch.setattr(brushes, "zbrush_dirs", lambda: {"install": exe.parent, "user_assets": None})
    monkeypatch.setattr(recent, "public_documents", lambda: str(tmp_path / "Docs"))
    path, _ = recent.list_file()
    assert path == tmp_path / "Docs" / "ZBrushData2024" / "ZStartup" / "ConfigFiles" / "LightboxRecentFiles.cfg"


def test_with_no_zbrush_installed_there_is_no_list(monkeypatch):
    import brushes
    monkeypatch.setattr(brushes, "zbrush_dirs", lambda: {"install": None, "user_assets": None})
    assert recent.list_file() == (None, "no ZBrush installation found")


def test_public_documents_is_a_folder_name():
    assert os.path.isabs(recent.public_documents())


# --- the item in radial.json -----------------------------------------------------------------------
@pytest.mark.parametrize("value, label", [("project", "Recent projects"), ("tool", "Recent tools"), ("any", "Recent")])
def test_the_three_values_load_with_their_default_labels(load_menus, value, label):
    cfg = load_menus({"main": one_item_menu({"recent": value})})
    assert cfg.errors == []
    it = cfg.menus["main"].items[0]
    assert (it.kind, it.label, it.data) == ("recent", label, {"recent": value})


def test_a_label_of_its_own_wins(load_menus):
    cfg = load_menus({"main": one_item_menu({"recent": "any", "label": "Lately"})})
    assert cfg.menus["main"].items[0].label == "Lately"


@pytest.mark.parametrize("value", ["projects", "Project", "", "brush", 1, None, ["project"]])
def test_any_other_value_is_a_problem_and_the_slot_is_empty(load_menus, value):
    cfg = load_menus({"main": one_item_menu({"recent": value}, {"brush": "A"})})
    assert problems(cfg, "menu main item 1: 'recent' must be project, tool or any")
    assert [it.kind for it in cfg.menus["main"].items] == ["empty", "brush"]


def test_a_recent_item_cannot_be_a_step(load_menus):
    cfg = load_menus({"main": one_item_menu({"steps": [{"brush": "A"}, {"recent": "any"}]}, {"brush": "B"})})
    assert problems(cfg, "menu main item 1 step 2: steps cannot open menus, nest steps, be auto slots, be empty slots "
                         "or open tags, the browser or recent files")


def test_menu_ids_starting_with_recent_are_reserved(load_menus):
    cfg = load_menus({**GOOD_MENUS, "recent:any": {"items": [{"brush": "A"}]}})
    assert problems(cfg, "menu recent:any: ids starting with 'recent:' are reserved")
    assert "recent:any" not in cfg.menus


# --- the fan ---------------------------------------------------------------------------------------
class _Usage:
    version = 1

    def load(self):
        return self


class _Tags:
    mtime = 0

    def color(self, key):
        return ""

    def color_of_item(self, key):
        return ""


def expander(load_menus, item, front=None, wait=True, **ring):
    """An expander of a menu with this item. wait: it waits for the worker, as Studio's previews do, so a test sees
    the fresh answer at the first open (the ring's own expander never waits)."""
    cfg = load_menus({"main": one_item_menu(item, {"brush": "A"})}, ring=ring)
    return cfg, expand.Expander(cfg, _Usage(), _Tags(), front=front, wait_recent=wait)


def test_a_recent_slot_with_files_opens_a_fan_of_project_and_tool_items(load_menus, listed, tmp_path):
    p, t = make(tmp_path / "Head.ZPR"), make(tmp_path / "Dog.ztl")
    listed(p, t)
    cfg, ex = expander(load_menus, {"recent": "any", "icon": "Standard", "style": {"size": 1.2}})
    slot = ex.menu(cfg.menus["main"]).items[0]
    assert (slot.kind, slot.data, slot.label, slot.icon, slot.style) == (
        "menu", {"menu": "recent:any"}, "Recent", "Standard", {"size": 1.2})
    fan = ex.resolve("recent:any")
    assert fan.fan and fan.id == "recent:any" and fan.title == "Recent"
    assert [(i.kind, i.label, i.data) for i in fan.items] == [("project", "Head", {"project": str(p)}),
                                                              ("tool", "Dog", {"tool": str(t)})]


def test_the_fan_holds_as_many_as_a_tag_fan_and_has_no_more_slot(load_menus, listed, tmp_path):
    listed(*[make(tmp_path / f"T{i:02}.ztl") for i in range(30)])
    cfg, ex = expander(load_menus, {"recent": "tool"}, tag_limit=6)
    fan = ex.resolve("recent:tool")
    assert [i.label for i in fan.items] == ["T00", "T01", "T02", "T03", "T04", "T05"]
    assert all(i.kind == "tool" for i in fan.items)
    cfg, ex = expander(load_menus, {"recent": "tool"})
    assert len(ex.resolve("recent:tool").items) == expand.TAG_SLOTS


def test_a_recent_slot_with_no_files_stays_a_faint_recent_slot(load_menus, listed, tmp_path):
    listed(make(tmp_path / "Dog.ztl"), tmp_path / "Gone.zpr")
    cfg, ex = expander(load_menus, {"recent": "project"})
    slot = ex.menu(cfg.menus["main"]).items[0]
    assert (slot.kind, slot.data, slot.label) == ("recent", {"recent": "project"}, "Recent projects")
    assert ex.resolve("recent:project") is None


def test_the_fan_follows_the_zbrush_in_front(load_menus, monkeypatch, tmp_path):
    asked = []

    def entries(kind, limit, install=None, log=None):
        asked.append(install)
        return [str(make(tmp_path / "A.zpr"))]
    monkeypatch.setattr(recent, "entries", entries)
    front = {"path": r"C:\Programs\ZBrush 2024", "year": 2024, "python": False}
    cfg, ex = expander(load_menus, {"recent": "project"}, front=lambda: front, wait=False)
    ex.resolve("recent:project")
    cfg, ex = expander(load_menus, {"recent": "project"}, wait=False)
    ex.resolve("recent:project")
    assert asked == [front, None]


def test_an_unknown_recent_menu_id_resolves_to_nothing(load_menus):
    cfg, ex = expander(load_menus, {"brush": "B"})
    assert ex.resolve("recent:brush") is None


# --- picks -----------------------------------------------------------------------------------------
def test_picking_an_empty_recent_slot_sends_nothing_and_says_so(app):
    app._on_ring_done(config.Item(label="Recent", kind="recent", data={"recent": "any"}), "click")
    assert app.toasts == [radiald.MSG_EMPTY_SLOT]
    assert not (app.tmpdata / "request.json").exists()


def test_a_pick_from_the_fan_opens_the_project_and_counts_nowhere(app, tmp_path, monkeypatch):
    p = make(tmp_path / "Head.ZPR")
    recorded = []
    monkeypatch.setattr(app.usage, "record_pick", lambda *a: recorded.append(a))
    monkeypatch.setattr(app.usage, "record", lambda *a: recorded.append(a))
    app._on_ring_done(config.Item(label="Head", kind="project", data={"project": str(p)}), "click")
    req = json.loads((app.tmpdata / "request.json").read_text(encoding="utf-8"))
    assert req["actions"] == [{"filepress": "File:Open", "file": str(p).replace("\\", "/")}]
    assert recorded == [] and app.toasts == []


# --- the open path reads only what the worker found ------------------------------------------------
def test_the_open_path_never_touches_the_disk(listed, tmp_path, monkeypatch):
    a = make(tmp_path / "A.zpr")
    listed(a)
    assert read("project", 12) == [str(a)]

    def refuse(*args, **kw):
        raise AssertionError("the open path touched the disk")
    monkeypatch.setattr(os, "stat", refuse)
    monkeypatch.setattr(os.path, "isfile", refuse)
    monkeypatch.setattr(recent.Path, "read_bytes", refuse)
    monkeypatch.setattr(recent, "list_file", refuse)
    asked = []
    monkeypatch.setattr(recent, "refresh_later", lambda *args: asked.append(args))
    now = [recent.clock() + 1000.0]
    monkeypatch.setattr(recent, "clock", lambda: now[0])
    assert recent.entries("project", 12) == [str(a)]      # old, but still shown...
    assert asked                                          # ...and a fresh one asked of the worker


def test_a_fresh_answer_asks_the_worker_for_nothing(listed, tmp_path, monkeypatch):
    listed(make(tmp_path / "A.zpr"))
    read("project", 12)
    asked = []
    monkeypatch.setattr(recent, "refresh_later", lambda *args: asked.append(args))
    recent.entries("project", 12)
    assert asked == []


def test_with_no_answer_yet_the_slot_is_empty_and_the_worker_fills_it(listed, tmp_path):
    a = make(tmp_path / "A.zpr")
    listed(a)
    assert recent.entries("project", 12) == []
    assert recent.wait()
    assert recent.entries("project", 12) == [str(a)]


def test_the_background_refresh_brings_the_new_list_at_the_next_open(listed, tmp_path, monkeypatch):
    a, b = make(tmp_path / "A.zpr"), make(tmp_path / "B.zpr")
    cfg = listed(a)
    now = [1000.0]
    monkeypatch.setattr(recent, "clock", lambda: now[0])
    assert read("project", 12) == [str(a)]
    cfg.write_bytes(cfg_bytes(b, a))
    assert recent.entries("project", 12) == [str(a)]      # still the last answer: it is fresh
    now[0] += recent.REFRESH_S
    assert recent.entries("project", 12) == [str(a)]      # old: shown once more, and refreshed meanwhile
    assert recent.wait()
    assert recent.entries("project", 12) == [str(b), str(a)]


def test_the_worker_runs_one_at_a_time_and_each_request_once(monkeypatch):
    import threading
    import time
    running, most, done = [0], [0], []
    lock = threading.Lock()

    def slow(kind, limit, install=None, log=None):
        with lock:
            running[0] += 1
            most[0] = max(most[0], running[0])
        time.sleep(0.05)
        with lock:
            running[0] -= 1
            done.append((kind, limit))
    monkeypatch.setattr(recent, "refresh", slow)
    for _ in range(5):
        recent.refresh_later("project", 12)
        recent.refresh_later("tool", 12)
    assert recent.wait()
    assert most[0] == 1
    assert sorted(set(done)) == [("project", 12), ("tool", 12)] and len(done) <= 4


def test_an_error_in_the_worker_is_logged_once_and_keeps_the_old_answer(listed, tmp_path, monkeypatch):
    a = make(tmp_path / "A.zpr")
    listed(a)
    assert read("project", 12) == [str(a)]

    def broken(data, kind):
        raise ValueError("bad list")
    monkeypatch.setattr(recent, "parse", broken)
    said = []
    recent.refresh("project", 12, log=said.append)
    recent.refresh("project", 12, log=said.append)
    assert recent.entries("project", 12) == [str(a)]
    assert len([s for s in said if "bad list" in s and "Traceback" not in s]) == 1
    assert len([s for s in said if "Traceback" in s]) == 1


def test_prefetch_warms_the_answers_the_menus_need(load_menus, listed, tmp_path):
    a = make(tmp_path / "A.zpr")
    listed(a)
    cfg, ex = expander(load_menus, {"recent": "project"}, wait=False)
    ex.prefetch_recent()
    assert recent.wait()
    assert ex.menu(cfg.menus["main"]).items[0].data == {"menu": "recent:project"}


def test_the_ring_never_waits_for_the_worker(load_menus, listed, tmp_path):
    listed(make(tmp_path / "A.zpr"))
    cfg, ex = expander(load_menus, {"recent": "project"}, wait=False)
    assert ex.menu(cfg.menus["main"]).items[0].kind == "recent"      # no answer yet: faint this once


# --- odd names, the text encoding, the version ------------------------------------------------------
def test_a_file_named_only_dot_zpr_is_a_project_with_its_whole_name(listed, tmp_path, load_menus):
    odd = make(tmp_path / ".zpr")
    assert recent.parse(cfg_bytes(odd), "any") == [str(odd)]
    assert recent.item_kind(odd) == "project" and recent.label(odd) == ".zpr"
    assert recent.item_kind(r"C:\A\.ZTL") == "tool" and recent.label(r"C:\A\.ZTL") == ".ZTL"
    listed(odd)
    cfg, ex = expander(load_menus, {"recent": "any"})
    fan = ex.resolve("recent:any")
    assert [(i.kind, i.label) for i in fan.items] == [("project", ".zpr")]


def test_an_error_while_building_the_fan_leaves_the_slot_empty_and_is_logged_once(load_menus, monkeypatch):
    def broken(*args, **kw):
        raise KeyError("odd")
    monkeypatch.setattr(recent, "entries", broken)
    said = []
    cfg = load_menus({"main": one_item_menu({"recent": "any"}, {"brush": "A"})})
    ex = expand.Expander(cfg, _Usage(), _Tags(), log=said.append)
    assert ex.menu(cfg.menus["main"]).items[0].kind == "recent"
    assert ex.resolve("recent:any") is None
    assert len(said) == 1 and "could not be built" in said[0]


def test_a_list_in_utf_8_is_read_as_utf_8():
    data = "C:\\Users\\you\\Mod\u00e8les\\H\u00e9ro.ztl".encode("utf-8") + b"\0"
    assert recent.parse(data, "tool") == ["C:\\Users\\you\\Mod\u00e8les\\H\u00e9ro.ztl"]


def test_a_list_that_is_not_utf_8_is_read_in_the_ansi_code_page():
    data = "C:\\Mod\u00e8les\\H\u00e9ro.ztl".encode("cp1252") + b"\0"     # \xe8 and \xe9 alone are not UTF-8
    assert recent.decode(data) == data.decode("mbcs", errors="replace")


def test_the_librarys_older_zbrush_gets_its_year_from_the_install_scan(monkeypatch, tmp_path):
    import brushes
    import installs
    exe = make(tmp_path / "ZBrush" / "ZBrush.exe")                     # a folder name with no year in it
    monkeypatch.setattr(brushes, "zbrush_dirs", lambda: {"install": exe.parent, "user_assets": None})
    monkeypatch.setattr(installs, "find_installs", lambda: [
        {"name": "ZBrush 2024", "year": 2024, "path": str(exe.parent), "python": False, "supported": True}])
    monkeypatch.setattr(recent, "public_documents", lambda: str(tmp_path / "Docs"))
    path, why = recent.list_file()
    assert path == tmp_path / "Docs" / "ZBrushData2024" / "ZStartup" / "ConfigFiles" / "LightboxRecentFiles.cfg"



# --- the worker's own failures, a stuck worker, a byte-order mark -----------------------------------
def test_an_exception_on_the_worker_thread_leaves_it_ready_for_the_next_request(listed, tmp_path, monkeypatch):
    a = make(tmp_path / "A.zpr")
    listed(a)

    def broken(*args):
        raise RuntimeError("worker broke")
    real = recent._refresh
    monkeypatch.setattr(recent, "_refresh", broken)
    said = []
    recent.refresh_later("project", 12, None, said.append)
    assert recent.wait()
    assert recent._worker is None and recent._pending == {}
    assert any("worker broke" in s for s in said)
    assert recent.entries("project", 12) == []
    monkeypatch.setattr(recent, "_refresh", real)
    recent.refresh_later("project", 12)
    assert recent.wait()
    assert recent.entries("project", 12) == [str(a)]


def test_a_thread_that_cannot_start_does_not_block_later_requests(monkeypatch):
    class NoThread:
        def __init__(self, *args, **kw):
            pass

        def start(self):
            raise RuntimeError("can't start new thread")
    monkeypatch.setattr(recent.threading, "Thread", NoThread)
    with pytest.raises(RuntimeError):
        recent.refresh_later("project", 12)
    assert recent._worker is None
    recent._pending.clear()


def test_a_stuck_worker_is_waited_for_once_per_expander(load_menus, monkeypatch):
    waits = []
    monkeypatch.setattr(recent, "wait", lambda timeout=5.0: waits.append(timeout) or False)
    monkeypatch.setattr(recent, "refresh_later", lambda *args: None)          # nothing ever answers
    cfg = load_menus({"main": one_item_menu({"recent": "project"}, {"recent": "tool"}, {"brush": "A"})})
    ex = expand.Expander(cfg, _Usage(), _Tags(), wait_recent=True)
    ex.menu(cfg.menus["main"])
    ex.resolve("recent:project")
    ex.menu(cfg.menus["main"])
    assert waits == [2.0]
    expand.Expander(cfg, _Usage(), _Tags(), wait_recent=True).menu(cfg.menus["main"])
    assert waits == [2.0, 2.0]                          # a new preview may wait once more


def test_a_stale_answer_is_shown_without_waiting(load_menus, listed, tmp_path, monkeypatch):
    a = make(tmp_path / "A.zpr")
    listed(a)
    read("project", 12)
    waits = []
    monkeypatch.setattr(recent, "wait", lambda timeout=5.0: waits.append(timeout) or True)
    monkeypatch.setattr(recent, "refresh_later", lambda *args: None)
    now = [recent.clock() + 1000.0]
    monkeypatch.setattr(recent, "clock", lambda: now[0])
    cfg, ex = expander(load_menus, {"recent": "project"})
    assert ex.menu(cfg.menus["main"]).items[0].data == {"menu": "recent:project"}
    assert waits == []


def test_a_byte_order_mark_does_not_drop_the_first_entry():
    data = b"\xef\xbb\xbf" + cfg_bytes(r"C:\A\One.zpr", r"C:\A\Two.zpr", encoding="utf-8")
    assert recent.parse(data, "project") == [r"C:\A\One.zpr", r"C:\A\Two.zpr"]


# --- the app reads the lists again while ZBrush is in front -----------------------------------------
class _Ex:
    def __init__(self):
        self.calls = 0

    def prefetch_recent(self):
        self.calls += 1


def test_the_app_reads_the_lists_again_every_half_minute_while_zbrush_is_in_front(app, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(radiald.time, "monotonic", lambda: now[0])
    front = [None]
    monkeypatch.setattr(app, "target_install", lambda: front[0])
    app.expander = ex = _Ex()
    app._recent_tick()
    assert ex.calls == 0                                # ZBrush is not in front
    front[0] = {"path": r"C:\Programs\ZBrush 2026", "year": 2026, "python": True}
    app._recent_tick()
    assert ex.calls == 1
    now[0] += radiald.RECENT_PREFETCH_S - 1
    app._recent_tick()
    assert ex.calls == 1                                # not yet
    now[0] += 1
    app._recent_tick()
    assert ex.calls == 2


def test_without_a_recent_slot_the_periodic_read_does_nothing(app, monkeypatch):
    asked = []
    monkeypatch.setattr(recent, "prefetch", lambda *args: asked.append(args))
    monkeypatch.setattr(app, "target_install", lambda: {"path": r"C:\Programs\ZBrush 2026", "python": True})
    app.expander = expand.Expander(app.cfg, _Usage(), _Tags())
    app._recent_tick()
    assert asked == []
