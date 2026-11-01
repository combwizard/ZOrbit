"""profiles.py: the profile folders, the pointer, the first-run migration, and fsutil.named_lock."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time

import pytest

import fsutil
import paths
import profiles
from profiles import ProfileError

ZORBIT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "zorbit")
BRIDGE = {"mode": "key", "key": "F11"}
BROWSER = {"hotkey": "Alt+G"}
RING = {"radius": 160, "animation": "pop"}
ACTIVE_RAW = {"bridge": BRIDGE, "browser": BROWSER, "ring": RING,
              "menus": {"side": {"title": "Side", "items": [{"brush": "Standard"}]},
                        "main": {"title": "Main", "hotkey": "W", "items": [{"brush": "ClayBuildup"}]}}}


def put(path, content):
    """Writes text (or bytes) to path, making its folder."""
    path = str(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content if isinstance(content, bytes) else content.encode("utf-8"))
    return path


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def make_profile(cfg_dir, name, raw=None):
    """profiles\\<name>\\radial.json holding raw (a dict); returns the folder."""
    folder = cfg_dir / "profiles" / name
    put(folder / "radial.json", json.dumps(raw if raw is not None else {"menus": {}}))
    return folder


def default_bytes():
    with open(paths.DEFAULT_MENUS, "rb") as f:
        return f.read()


def snapshot(folder):
    """{relative path: st_mtime_ns} of every file and folder under folder."""
    out = {}
    for dirpath, dirs, files in os.walk(folder):
        for n in dirs + files:
            p = os.path.join(dirpath, n)
            out[os.path.relpath(p, folder)] = os.stat(p).st_mtime_ns
    return out


def staging(cfg_dir):
    return [n for n in os.listdir(cfg_dir / "profiles") if n.startswith(".staging")]


@pytest.fixture
def active_profile(profile_env):
    """A first-run profile set up whose Default holds ACTIVE_RAW, a tags.json, a usage.json and a .bak."""
    cfg_dir, data_dir = profile_env
    profiles.ensure()
    folder = cfg_dir / "profiles" / "Default"
    put(folder / "radial.json", json.dumps(ACTIVE_RAW))
    put(folder / "radial.json.bak", "old menus")
    put(folder / "tags.json", '{"version": 1, "tags": {}, "items": {}}')
    put(folder / "usage.json", '{"brushes": {}}')
    return cfg_dir, folder


# --- valid_name ---------------------------------------------------------------------------------


@pytest.mark.parametrize("name, why", [
    ("", "Give the profile a name."), ("   ", "Give the profile a name."),
    ("x" * 61, "Keep the name under 60 characters."),
    (".hidden", "A name cannot start with a dot."), ("ends.", "A name cannot end with a dot or a space."),
    ("CON", "That name is reserved by Windows."), ("con.txt", "That name is reserved by Windows."),
    ("COM1", "That name is reserved by Windows."), ("lpt9", "That name is reserved by Windows."),
    ("Nul", "That name is reserved by Windows."), ("aux.x.y", "That name is reserved by Windows.")])
def test_valid_name_refuses(profile_env, name, why):
    assert profiles.valid_name(name) == why


@pytest.mark.parametrize("char", list('\\/:*?"<>|') + ["\x00", "\x1f", "\t", "\n"])
def test_valid_name_refuses_each_forbidden_character(profile_env, char):
    assert profiles.valid_name(f"a{char}b") == 'A name cannot contain \\ / : * ? " < > |'


@pytest.mark.parametrize("name", ["Hard surface", "Zbrush 2026", "Szkice", "Žaba", "日本語", "x" * 60, "Con2", "COM10",
                                  "a.b", "  padded  "])
def test_valid_name_accepts(profile_env, name):
    assert profiles.valid_name(name) == ""


def test_valid_name_refuses_a_duplicate_ignoring_case(active_profile):
    assert profiles.valid_name("default") == "There is already a profile called default."
    assert profiles.valid_name("Default", existing=["Other"]) == ""
    assert profiles.valid_name("OTHER", existing=["Other"]) != ""


def test_valid_name_treats_two_spellings_of_one_letter_alike(active_profile):
    make_profile(active_profile[0], "Café")
    assert profiles.valid_name("Café") != ""


def test_unique_name_adds_a_number(active_profile):
    make_profile(active_profile[0], "Hard")
    make_profile(active_profile[0], "Hard 2")
    assert profiles.unique_name("Free") == "Free"
    assert profiles.unique_name("hard") == "hard 3"
    assert len(profiles.unique_name("Default")) == len("Default 2")


# --- ensure: a fresh install --------------------------------------------------------------------


def test_ensure_on_a_fresh_install_makes_default_from_the_shipped_menus(profile_env):
    cfg_dir, _ = profile_env
    path = profiles.ensure()
    assert path == str(cfg_dir / "profiles" / "Default" / "radial.json")
    with open(path, "rb") as f:
        assert f.read() == default_bytes()
    assert read(cfg_dir / "profile.json") == {"active": "Default"}
    assert profiles.active() == "Default"
    assert profiles.names() == ["Default"]


def test_ensure_leaves_no_staging_folder(profile_env):
    profiles.ensure()
    assert staging(profile_env[0]) == []


# --- ensure: migrating the root files ------------------------------------------------------------


def test_ensure_moves_the_root_files_into_default(profile_env):
    cfg_dir, data_dir = profile_env
    files = {cfg_dir / "radial.json": "menus", cfg_dir / "radial.json.bak": "menus bak",
             cfg_dir / "radial.json.broken": "menus broken", cfg_dir / "tags.json": "tags",
             cfg_dir / "tags.json.bak": "tags bak", data_dir / "usage.json": "usage",
             data_dir / "usage.json.bad": "usage bad"}
    for p, text in files.items():
        put(p, text)
    profiles.ensure()
    default = cfg_dir / "profiles" / "Default"
    for p, text in files.items():
        assert (default / p.name).read_bytes() == text.encode()
        assert (cfg_dir / "pre-profiles" / p.name).read_bytes() == text.encode()
        assert not p.exists()


def test_ensure_leaves_the_per_pc_files_at_the_root(profile_env):
    cfg_dir, _ = profile_env
    for n in ("studio.json", "popout.json", "launch.json"):
        put(cfg_dir / n, "{}")
    profiles.ensure()
    assert all((cfg_dir / n).exists() for n in ("studio.json", "popout.json", "launch.json"))


def test_ensure_takes_a_radial_menu_install_when_the_root_has_nothing(profile_env):
    cfg_dir, data_dir = profile_env
    old_cfg = cfg_dir.parent / "RadialMenu"
    old_data = data_dir.parent / "RadialMenu"
    put(old_cfg / "radial.json", "old menus")
    put(old_cfg / "radial.json.bak", "old bak")
    put(old_cfg / "studio.json", '{"old": true}')
    put(old_data / "usage.json", "old usage")
    profiles.ensure()
    default = cfg_dir / "profiles" / "Default"
    assert (default / "radial.json").read_bytes() == b"old menus"
    assert (default / "radial.json.bak").read_bytes() == b"old bak"
    assert (default / "usage.json").read_bytes() == b"old usage"
    assert (cfg_dir / "studio.json").read_bytes() == b'{"old": true}'
    assert (old_cfg / "radial.json").exists()              # the old install is left as it was


def test_ensure_prefers_the_root_file_to_the_radial_menu_one(profile_env):
    cfg_dir, _ = profile_env
    put(cfg_dir.parent / "RadialMenu" / "radial.json", "old")
    put(cfg_dir / "radial.json", "new")
    profiles.ensure()
    assert (cfg_dir / "profiles" / "Default" / "radial.json").read_bytes() == b"new"


def test_paths_legacy_sources_follow_the_folders(profile_env):
    cfg_dir, data_dir = profile_env
    (old_cfg, new_cfg, _), (old_data, new_data, _) = paths.legacy_sources()
    assert (old_cfg, new_cfg) == (str(cfg_dir.parent / "RadialMenu"), str(cfg_dir))
    assert (old_data, new_data) == (str(data_dir.parent / "RadialMenu"), str(data_dir))


def test_paths_ensure_config_hands_over_to_profiles(profile_env):
    assert paths.ensure_config() == str(profile_env[0] / "profiles" / "Default" / "radial.json")


# --- ensure: running again, strays, repairs ------------------------------------------------------


def test_a_second_ensure_changes_nothing(profile_env):
    cfg_dir, data_dir = profile_env
    put(cfg_dir / "radial.json", "menus")
    put(data_dir / "usage.json", "usage")
    profiles.ensure()
    before = (snapshot(cfg_dir), snapshot(data_dir))
    time.sleep(0.02)
    profiles.ensure()
    assert (snapshot(cfg_dir), snapshot(data_dir)) == before


def test_a_stray_empty_default_folder_is_replaced(profile_env):
    cfg_dir, _ = profile_env
    (cfg_dir / "profiles" / "Default").mkdir(parents=True)
    put(cfg_dir / "profiles" / "Default" / "notes.txt", "stray")
    profiles.ensure()
    assert (cfg_dir / "profiles" / "Default" / "radial.json").is_file()
    assert not (cfg_dir / "profiles" / "Default" / "notes.txt").exists()


def test_a_stale_staging_folder_is_removed_and_a_fresh_one_kept(profile_env):
    cfg_dir, _ = profile_env
    stale, fresh = cfg_dir / "profiles" / ".staging-x", cfg_dir / "profiles" / ".staging-y"
    stale.mkdir(parents=True)
    fresh.mkdir()
    old = time.time() - 7200
    os.utime(stale, (old, old))
    profiles.ensure()
    assert not stale.exists()
    assert fresh.exists()


def test_ensure_purges_old_deleted_profiles_only(active_profile):
    cfg_dir, _ = active_profile
    old, new = cfg_dir / "profiles" / ".deleted" / "Old-20200101-000000", cfg_dir / "profiles" / ".deleted" / "New-x"
    put(old / "radial.json", "{}")
    put(new / "radial.json", "{}")
    when = time.time() - 31 * 86400
    os.utime(old, (when, when))
    profiles.ensure()
    assert not old.exists()
    assert new.exists()


def test_ensure_writes_a_missing_pointer(profile_env):
    cfg_dir, _ = profile_env
    make_profile(cfg_dir, "Default")
    make_profile(cfg_dir, "Zed")
    profiles.ensure()
    assert read(cfg_dir / "profile.json") == {"active": "Default"}
    assert profiles.names() == ["Default", "Zed"]


def test_ensure_rewrites_a_corrupt_pointer(profile_env):
    cfg_dir, _ = profile_env
    make_profile(cfg_dir, "Alpha")
    put(cfg_dir / "profile.json", "{nope")
    profiles.ensure()
    assert read(cfg_dir / "profile.json") == {"active": "Alpha"}


def test_ensure_rewrites_a_pointer_naming_a_missing_folder(profile_env):
    cfg_dir, _ = profile_env
    make_profile(cfg_dir, "Default")
    make_profile(cfg_dir, "Zed")
    put(cfg_dir / "profile.json", '{"active": "Gone"}')
    assert profiles.ensure().endswith(os.path.join("Default", "radial.json"))
    assert read(cfg_dir / "profile.json") == {"active": "Default"}


def test_active_with_a_dangling_pointer_does_not_write(profile_env):
    cfg_dir, _ = profile_env
    make_profile(cfg_dir, "Alpha")
    put(cfg_dir / "profile.json", '{"active": "Gone"}')
    before = (cfg_dir / "profile.json").read_bytes()
    assert profiles.active() == "Alpha"
    assert (cfg_dir / "profile.json").read_bytes() == before


def test_active_follows_a_pointer_written_by_another_process(active_profile):
    cfg_dir, _ = active_profile
    make_profile(cfg_dir, "Other")
    assert profiles.active() == "Default"
    put(cfg_dir / "profile.json", '{"active": "Other"}')
    assert profiles.active() == "Other"


def test_active_gives_back_the_on_disk_spelling(active_profile):
    make_profile(active_profile[0], "Hard Surface")
    put(active_profile[0] / "profile.json", '{"active": "hard surface"}')
    assert profiles.active() == "Hard Surface"


# --- names --------------------------------------------------------------------------------------


def test_names_ignores_dot_folders_and_folders_without_menus_and_sorts_ignoring_case(profile_env):
    cfg_dir, _ = profile_env
    for n in ("beta", "Alpha", "Zed"):
        make_profile(cfg_dir, n)
    make_profile(cfg_dir, ".staging-1")
    make_profile(cfg_dir, ".deleted")
    (cfg_dir / "profiles" / "Empty").mkdir()
    put(cfg_dir / "profiles" / "note.txt", "not a folder")
    assert profiles.names() == ["Alpha", "beta", "Zed"]


def test_canonical_and_exists(active_profile):
    assert profiles.canonical("DEFAULT") == "Default"
    assert profiles.canonical("nope") is None
    assert profiles.canonical("..\\Default") is None
    assert profiles.canonical(None) is None
    assert profiles.exists("default") and not profiles.exists("other")


# --- the pointer --------------------------------------------------------------------------------


def test_signature_is_none_before_the_pointer_and_changes_when_it_is_written(active_profile):
    cfg_dir, _ = active_profile
    (cfg_dir / "profile.json").unlink()
    assert profiles.signature() is None
    make_profile(cfg_dir, "Other")
    profiles.set_active("Other")
    first = profiles.signature()
    assert first is not None
    profiles.set_active("Default")
    assert profiles.signature() != first


def test_set_active_switches_and_keeps_other_keys(active_profile):
    cfg_dir, _ = active_profile
    make_profile(cfg_dir, "Other")
    put(cfg_dir / "profile.json", '{"active": "Default", "note": 1}')
    profiles.set_active("other")
    assert read(cfg_dir / "profile.json") == {"active": "Other", "note": 1}
    assert profiles.active() == "Other"


def test_set_active_refuses_an_unknown_profile(active_profile):
    with pytest.raises(ProfileError, match="There is no profile called Nope."):
        profiles.set_active("Nope")


def test_set_active_writes_over_an_unreadable_pointer(active_profile):
    cfg_dir, _ = active_profile
    put(cfg_dir / "profile.json", "{nope")
    profiles.set_active("Default")
    assert read(cfg_dir / "profile.json") == {"active": "Default"}


# --- create -------------------------------------------------------------------------------------


def test_create_starter_has_the_shipped_menus_and_this_pcs_bridge_and_browser(active_profile):
    cfg_dir, _ = active_profile
    assert profiles.create("Fresh", "starter") == "Fresh"
    folder = cfg_dir / "profiles" / "Fresh"
    cfg = read(folder / "radial.json")
    shipped = json.loads(default_bytes())
    assert cfg["menus"] == shipped["menus"] and cfg["ring"] == shipped["ring"]
    assert cfg["bridge"] == BRIDGE and cfg["browser"] == BROWSER
    assert sorted(os.listdir(folder)) == ["radial.json"]
    assert staging(cfg_dir) == []


def test_create_empty_has_one_empty_menu_on_the_first_hotkey_and_the_ring(active_profile):
    cfg_dir, _ = active_profile
    profiles.create("Blank", "empty")
    cfg = read(cfg_dir / "profiles" / "Blank" / "radial.json")
    assert cfg["menus"] == {"main": {"title": "Main", "hotkey": "W", "items": []}}
    assert cfg["ring"] == RING and cfg["bridge"] == BRIDGE and cfg["browser"] == BROWSER


def test_create_empty_keeps_the_looks_the_ring_may_name(active_profile):
    cfg_dir, folder = active_profile
    raw = json.loads((folder / "radial.json").read_text(encoding="utf-8"))
    raw["looks"] = {"Mine": {"slot_shape": "hexagon"}}
    raw["ring"] = {**raw.get("ring", {}), "look": "Mine"}
    put(folder / "radial.json", json.dumps(raw))
    profiles.create("Blank", "empty")
    cfg = read(cfg_dir / "profiles" / "Blank" / "radial.json")
    assert cfg["looks"] == {"Mine": {"slot_shape": "hexagon"}} and cfg["ring"]["look"] == "Mine"


def test_create_empty_without_looks_has_no_looks_section(active_profile):
    cfg_dir, _ = active_profile
    profiles.create("Blank", "empty")
    assert "looks" not in read(cfg_dir / "profiles" / "Blank" / "radial.json")


def test_create_empty_falls_back_to_q_when_no_menu_has_a_hotkey(active_profile):
    cfg_dir, folder = active_profile
    put(folder / "radial.json", json.dumps({"menus": {"a": {"items": []}}}))
    profiles.create("Blank", "empty")
    assert read(cfg_dir / "profiles" / "Blank" / "radial.json")["menus"]["main"]["hotkey"] == "Q"


def test_create_copy_brings_menus_tags_and_usage_but_not_the_backups(active_profile):
    cfg_dir, folder = active_profile
    profiles.create("Twin", "copy")
    twin = cfg_dir / "profiles" / "Twin"
    assert sorted(os.listdir(twin)) == ["radial.json", "tags.json", "usage.json"]
    for n in ("radial.json", "tags.json", "usage.json"):
        assert (twin / n).read_bytes() == (folder / n).read_bytes()


def test_create_file_writes_the_menus_and_the_tags_and_replaces_the_bridge(active_profile):
    cfg_dir, _ = active_profile
    other = {"bridge": {"mode": "message"}, "browser": {"hotkey": "Alt+Z"}, "ring": {"radius": 99},
             "menus": {"m": {"title": "M", "hotkey": "E", "items": []}}}
    tags = {"version": 1, "tags": {"wip": {"label": "WIP", "color": "#A8DF23"}}, "items": {}}
    profiles.create("Shared", "file", {"config": other, "tags": tags})
    folder = cfg_dir / "profiles" / "Shared"
    cfg = read(folder / "radial.json")
    assert cfg["bridge"] == BRIDGE and cfg["browser"] == BROWSER
    assert cfg["ring"] == {"radius": 99} and cfg["menus"] == other["menus"]
    assert read(folder / "tags.json") == tags


def test_create_file_without_tags_writes_no_tags_file(active_profile):
    cfg_dir, _ = active_profile
    profiles.create("Shared", "file", {"config": {"menus": {}}, "tags": None})
    assert os.listdir(cfg_dir / "profiles" / "Shared") == ["radial.json"]


def test_create_returns_the_name_as_written(active_profile):
    assert profiles.create("  Padded  ", "empty") == "Padded"
    assert "Padded" in profiles.names()


@pytest.mark.parametrize("name", ["default", "DEFAULT"])
def test_create_refuses_a_duplicate_ignoring_case(active_profile, name):
    with pytest.raises(ProfileError, match="There is already a profile called"):
        profiles.create(name, "starter")
    assert staging(active_profile[0]) == []


def test_create_refuses_a_bad_name_and_an_unknown_source(active_profile):
    with pytest.raises(ProfileError, match="cannot contain"):
        profiles.create("a/b", "starter")
    with pytest.raises(ProfileError):
        profiles.create("Fine", "magic")
    assert profiles.names() == ["Default"] and staging(active_profile[0]) == []


def test_create_refuses_a_file_bundle_that_is_not_a_menus_object(active_profile):
    with pytest.raises(ProfileError):
        profiles.create("Bad", "file", {"config": []})
    assert profiles.names() == ["Default"] and staging(active_profile[0]) == []


def test_create_refuses_menus_that_cannot_be_read_and_leaves_nothing_behind(active_profile):
    cfg_dir, folder = active_profile
    put(folder / "radial.json", "{nope")                    # a copy of this file is not a profile
    with pytest.raises(ProfileError, match="The menus could not be read"):
        profiles.create("Twin", "copy")
    assert profiles.names() == ["Default"] and staging(cfg_dir) == []


def test_create_replaces_a_stray_folder_of_the_same_name(active_profile):
    cfg_dir, _ = active_profile
    put(cfg_dir / "profiles" / "Stray" / "junk.txt", "x")
    profiles.create("Stray", "starter")
    assert os.listdir(cfg_dir / "profiles" / "Stray") == ["radial.json"]


# --- rename -------------------------------------------------------------------------------------


def test_rename_a_profile_that_is_not_active(active_profile):
    cfg_dir, _ = active_profile
    make_profile(cfg_dir, "Old")
    assert profiles.rename("old", "New") == "New"
    assert profiles.names() == ["Default", "New"]
    assert profiles.active() == "Default"


def test_rename_the_active_profile_moves_the_pointer(active_profile):
    cfg_dir, _ = active_profile
    assert profiles.rename("Default", "Main") == "Main"
    assert read(cfg_dir / "profile.json")["active"] == "Main"
    assert profiles.active() == "Main"
    assert (cfg_dir / "profiles" / "Main" / "radial.json").is_file()


def test_rename_may_change_only_the_case(active_profile):
    cfg_dir, _ = active_profile
    make_profile(cfg_dir, "hard")
    assert profiles.rename("hard", "Hard") == "Hard"
    assert "Hard" in os.listdir(cfg_dir / "profiles")


def test_rename_to_the_same_name_does_nothing(active_profile):
    assert profiles.rename("Default", "Default") == "Default"


def test_rename_refuses_an_existing_target_and_an_unknown_source(active_profile):
    make_profile(active_profile[0], "Other")
    with pytest.raises(ProfileError, match="There is already a profile called other"):
        profiles.rename("Default", "other")
    with pytest.raises(ProfileError, match="There is no profile called Nope"):
        profiles.rename("Nope", "Fine")


def test_a_rename_that_cannot_move_the_folder_leaves_everything_as_it_was(active_profile, monkeypatch):
    cfg_dir, _ = active_profile
    monkeypatch.setattr(fsutil, "REPLACE_PAUSES", (0,))

    def held(*_a):
        raise PermissionError(13, "in use")
    real_rename = os.rename
    monkeypatch.setattr(os, "rename", held)
    with pytest.raises(ProfileError, match="The folder could not be renamed"):
        profiles.rename("Default", "Main")
    monkeypatch.setattr(os, "rename", real_rename)
    assert read(cfg_dir / "profile.json")["active"] == "Default"
    assert profiles.names() == ["Default"]


# --- delete -------------------------------------------------------------------------------------


def test_the_last_profile_cannot_be_deleted(active_profile):
    with pytest.raises(ProfileError, match="The last profile cannot be deleted."):
        profiles.delete("Default")
    assert profiles.names() == ["Default"]


def test_delete_a_profile_that_is_not_active_moves_it_aside(active_profile):
    cfg_dir, _ = active_profile
    make_profile(cfg_dir, "Spare")
    assert profiles.delete("spare") == "Default"
    assert profiles.names() == ["Default"]
    (kept,) = os.listdir(cfg_dir / "profiles" / ".deleted")
    assert kept.startswith("Spare-") and (cfg_dir / "profiles" / ".deleted" / kept / "radial.json").is_file()


def test_delete_the_active_profile_switches_to_default_first(active_profile):
    cfg_dir, _ = active_profile
    make_profile(cfg_dir, "Alpha")
    profiles.set_active("Alpha")
    assert profiles.delete("Alpha") == "Default"
    assert read(cfg_dir / "profile.json")["active"] == "Default"


def test_delete_the_active_default_switches_to_the_first_other_one(active_profile):
    cfg_dir, _ = active_profile
    make_profile(cfg_dir, "Zed")
    make_profile(cfg_dir, "beta")
    assert profiles.delete("Default") == "beta"
    assert profiles.active() == "beta"


def test_a_deleted_profile_is_kept_for_30_days_from_the_deletion(active_profile):
    cfg_dir, _ = active_profile
    folder = make_profile(cfg_dir, "Spare")
    long_ago = time.time() - 90 * 86400
    os.utime(folder, (long_ago, long_ago))                  # untouched for months before it was deleted
    profiles.delete("Spare")
    profiles.ensure()
    assert len(os.listdir(cfg_dir / "profiles" / ".deleted")) == 1


def test_a_delete_that_cannot_move_the_folder_restores_the_pointer(active_profile, monkeypatch):
    cfg_dir, _ = active_profile
    make_profile(cfg_dir, "Alpha")
    monkeypatch.setattr(fsutil, "REPLACE_PAUSES", (0,))

    def held(*_a):
        raise PermissionError(13, "in use")
    real_rename = os.rename
    monkeypatch.setattr(os, "rename", held)
    with pytest.raises(ProfileError, match="The folder could not be removed"):
        profiles.delete("Default")
    monkeypatch.setattr(os, "rename", real_rename)
    assert read(cfg_dir / "profile.json")["active"] == "Default"
    assert profiles.names() == ["Alpha", "Default"]


# --- the environment overrides ------------------------------------------------------------------


def test_a_pinned_menus_file_turns_profiles_off(profile_env, monkeypatch, tmp_path):
    pinned = str(tmp_path / "pinned.json")
    monkeypatch.setenv("ZORBIT_CONFIG_FILE", pinned)
    assert not profiles.enabled()
    assert profiles.names() == ["Default"]
    assert profiles.config_file() == pinned
    assert profiles.ensure() == pinned
    assert not (profile_env[0] / "profiles").exists() and not (profile_env[0] / "profile.json").exists()
    for call in (lambda: profiles.create("X", "starter"), lambda: profiles.rename("Default", "X"),
                 lambda: profiles.delete("Default"), lambda: profiles.set_active("Default")):
        with pytest.raises(ProfileError, match="Profiles are off while a menus file is pinned."):
            call()


def test_a_pinned_tags_or_usage_file_leaves_profiles_on(active_profile, monkeypatch, tmp_path):
    cfg_dir, folder = active_profile
    monkeypatch.setenv("ZORBIT_TAGS_FILE", str(tmp_path / "t.json"))
    monkeypatch.setenv("ZORBIT_USAGE_FILE", str(tmp_path / "u.json"))
    assert profiles.enabled()
    assert profiles.tags_file() == str(tmp_path / "t.json")
    assert profiles.usage_file() == str(tmp_path / "u.json")
    assert profiles.config_file() == str(folder / "radial.json")
    assert profiles.tags_file("Default") == str(folder / "tags.json")      # a named profile ignores the override
    assert profiles.usage_file("Default") == str(folder / "usage.json")


def test_file_paths_without_overrides_follow_the_active_profile(active_profile):
    cfg_dir, folder = active_profile
    assert profiles.profile_dir() == str(folder)
    assert (profiles.config_file(), profiles.tags_file(), profiles.usage_file()) == (
        str(folder / "radial.json"), str(folder / "tags.json"), str(folder / "usage.json"))


# --- several processes starting together --------------------------------------------------------


def test_eight_threads_starting_together_make_one_default(profile_env):
    cfg_dir, data_dir = profile_env
    put(cfg_dir / "radial.json", "original menus")
    put(data_dir / "usage.json", "original usage")
    barrier, errors = threading.Barrier(8), []

    def start():
        try:
            barrier.wait()
            profiles.ensure()
        except BaseException as e:
            errors.append(e)
    threads = [threading.Thread(target=start) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert profiles.names() == ["Default"]
    assert (cfg_dir / "profiles" / "Default" / "radial.json").read_bytes() == b"original menus"
    assert (cfg_dir / "profiles" / "Default" / "usage.json").read_bytes() == b"original usage"
    assert staging(cfg_dir) == []


def test_two_processes_starting_together_make_one_default(tmp_path):
    cfg_dir = tmp_path / "Roaming" / "ZOrbit"
    data_dir = tmp_path / "Local" / "ZOrbit"
    put(cfg_dir / "radial.json", "original menus")
    put(cfg_dir / "tags.json", "original tags")
    data_dir.mkdir(parents=True)
    env = {k: v for k, v in os.environ.items()
           if k not in ("ZORBIT_CONFIG_FILE", "ZORBIT_TAGS_FILE", "ZORBIT_USAGE_FILE")}
    env.update(APPDATA=str(tmp_path / "Roaming"), LOCALAPPDATA=str(tmp_path / "Local"), PYTHONPATH=ZORBIT_DIR)
    code = "import profiles; print(profiles.ensure())"
    procs = [subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True) for _ in range(2)]
    results = [p.communicate(timeout=60) for p in procs]
    assert [p.returncode for p in procs] == [0, 0], results
    default = cfg_dir / "profiles" / "Default"
    assert sorted(os.listdir(cfg_dir / "profiles")) == ["Default", "format.json"]
    assert (default / "radial.json").read_bytes() == b"original menus"
    assert (default / "tags.json").read_bytes() == b"original tags"
    assert json.loads((cfg_dir / "profile.json").read_text()) == {"active": "Default"}


# --- fsutil.named_lock --------------------------------------------------------------------------


def test_named_lock_yields_true_when_free():
    with fsutil.named_lock("Local\\ZOrbitTestLockFree", 100) as got:
        assert got is True


def test_named_lock_can_be_taken_again_by_the_same_thread():
    with fsutil.named_lock("Local\\ZOrbitTestLockNested", 100) as outer:
        with fsutil.named_lock("Local\\ZOrbitTestLockNested", 100) as inner:
            assert outer is True and inner is True


def test_named_lock_gives_up_while_another_thread_holds_it():
    name, held, release, result = "Local\\ZOrbitTestLockBusy", threading.Event(), threading.Event(), []

    def hold():
        with fsutil.named_lock(name, 100):
            held.set()
            release.wait(10)
    t = threading.Thread(target=hold)
    t.start()
    assert held.wait(10)
    with fsutil.named_lock(name, 100) as got:
        result.append(got)
    release.set()
    t.join()
    assert result == [False]


# --- the format stamp ----------------------------------------------------------------------------


def stamp(cfg_dir):
    return cfg_dir / "profiles" / "format.json"


def write_stamp(cfg_dir, fmt=2, version="9.9.9"):
    data = {"format": fmt}
    if version is not None:
        data["version"] = version
    put(stamp(cfg_dir), json.dumps(data))


def test_ensure_stamps_a_fresh_install(profile_env):
    cfg_dir, _ = profile_env
    profiles.ensure()
    assert read(stamp(cfg_dir)) == {"format": profiles.FORMAT, "version": paths.VERSION}


def test_ensure_stamps_a_migration_and_the_stamp_is_not_a_profile(profile_env):
    cfg_dir, data_dir = profile_env
    put(cfg_dir / "radial.json", "menus")
    put(data_dir / "usage.json", "usage")
    profiles.ensure()
    assert read(stamp(cfg_dir))["format"] == 1
    assert profiles.names() == ["Default"]


def test_ensure_stamps_profiles_from_before_the_stamp_once(profile_env):
    cfg_dir, data_dir = profile_env
    make_profile(cfg_dir, "Default")
    put(cfg_dir / "profile.json", '{"active": "Default"}')
    assert not stamp(cfg_dir).exists()
    profiles.ensure()
    assert read(stamp(cfg_dir)) == {"format": 1, "version": paths.VERSION}
    before = (snapshot(cfg_dir), snapshot(data_dir))
    time.sleep(0.02)
    profiles.ensure()
    assert (snapshot(cfg_dir), snapshot(data_dir)) == before


def test_ensure_stamps_when_it_repairs_a_lost_pointer(profile_env):
    cfg_dir, _ = profile_env
    make_profile(cfg_dir, "Alpha")
    profiles.ensure()
    assert read(cfg_dir / "profile.json") == {"active": "Alpha"}
    assert read(stamp(cfg_dir))["format"] == 1


def test_a_newer_format_makes_ensure_touch_nothing(active_profile):
    cfg_dir, folder = active_profile
    write_stamp(cfg_dir)
    before = snapshot(cfg_dir)
    time.sleep(0.02)
    assert profiles.ensure() == str(folder / "radial.json")
    assert snapshot(cfg_dir) == before


def test_a_newer_format_does_not_migrate_or_repair(profile_env):
    cfg_dir, _ = profile_env
    put(cfg_dir / "radial.json", "menus")
    write_stamp(cfg_dir)
    profiles.ensure()
    assert profiles.names() == []
    assert (cfg_dir / "radial.json").exists()
    make_profile(cfg_dir, "Alpha")
    put(cfg_dir / "profile.json", "{nope")
    profiles.ensure()
    assert (cfg_dir / "profile.json").read_text() == "{nope"


def test_too_new_names_the_version_that_wrote_the_files(active_profile):
    assert profiles.too_new() == ""
    write_stamp(active_profile[0], 2, "9.9.9")
    assert profiles.too_new() == ("These files were made by ZOrbit 9.9.9, which is newer than this one "
                                  f"({paths.VERSION}). Install ZOrbit 9.9.9 or newer.")


def test_too_new_without_a_usable_version(active_profile):
    for version in (None, "", "  ", 7):
        write_stamp(active_profile[0], 2, version)
        profiles._forget()
        assert "a newer ZOrbit" in profiles.too_new()
        assert profiles.too_new().endswith("Install the newest ZOrbit.")


def test_too_new_follows_the_stamp_file(active_profile):
    cfg_dir, _ = active_profile
    write_stamp(cfg_dir, 2, "9.9.9")
    assert profiles.too_new()
    write_stamp(cfg_dir, profiles.FORMAT, "0.1.0")
    assert profiles.too_new() == ""


@pytest.mark.parametrize("text", ["{nope", "[]", '{"format": "2"}', '{"format": true}', '{"format": 2.5}',
                                  '{"format": 1}', '{"format": 0}', "{}"])
def test_an_unreadable_or_current_stamp_is_not_too_new(active_profile, text):
    put(stamp(active_profile[0]), text)
    assert profiles.too_new() == ""
    assert profiles.ensure()


def test_a_missing_stamp_is_not_too_new(profile_env):
    assert profiles.too_new() == ""


def test_the_changing_functions_refuse_when_the_files_are_too_new(active_profile):
    cfg_dir, _ = active_profile
    make_profile(cfg_dir, "Other")
    write_stamp(cfg_dir)
    before = snapshot(cfg_dir)
    time.sleep(0.02)
    calls = (lambda: profiles.create("New", "starter"), lambda: profiles.rename("Other", "Renamed"),
             lambda: profiles.delete("Other"), lambda: profiles.set_active("Other"),
             lambda: profiles._write_pointer("Other"))
    for call in calls:
        with pytest.raises(ProfileError, match="9.9.9"):
            call()
    assert snapshot(cfg_dir) == before


def test_repairing_the_pointer_leaves_the_stamp_alone(profile_env):
    cfg_dir, _ = profile_env
    profiles.ensure()
    before = (stamp(cfg_dir).read_bytes(), os.stat(stamp(cfg_dir)).st_mtime_ns)
    time.sleep(0.02)
    put(cfg_dir / "profile.json", "{nope")
    profiles.ensure()
    assert read(cfg_dir / "profile.json") == {"active": "Default"}
    assert (stamp(cfg_dir).read_bytes(), os.stat(stamp(cfg_dir)).st_mtime_ns) == before


def test_too_new_is_empty_while_a_menus_file_is_pinned(active_profile, monkeypatch):
    write_stamp(active_profile[0])
    monkeypatch.setenv("ZORBIT_CONFIG_FILE", "x.json")
    assert profiles.too_new() == ""


# --- leftovers -----------------------------------------------------------------------------------

STRAY_MENUS = {"menus": {"main": {"title": "Edited", "hotkey": "Q", "items": [{"brush": "Standard"}]}}}


def refuse_radial(monkeypatch):
    """shutil.move fails for radial.json, as when something holds the file during the first run."""
    real = shutil.move

    def flaky(src, dst, *a, **k):
        if os.path.basename(src) == "radial.json":
            raise PermissionError("held")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(profiles.shutil, "move", flaky)
    return real


def test_a_file_that_could_not_be_moved_is_recorded_as_a_leftover(profile_env, monkeypatch):
    cfg_dir, _ = profile_env
    put(cfg_dir / "radial.json", json.dumps(STRAY_MENUS))
    put(cfg_dir / "tags.json", "{}")
    refuse_radial(monkeypatch)
    profiles.ensure()
    st = os.stat(cfg_dir / "radial.json")
    assert read(cfg_dir / "profiles" / "leftovers.json") == {
        "radial.json": {"folder": "config", "size": st.st_size, "mtime_ns": st.st_mtime_ns}}
    assert (cfg_dir / "pre-profiles" / "tags.json").exists()
    assert profiles.names() == ["Default"]


def test_no_leftovers_file_when_everything_moved(profile_env):
    cfg_dir, _ = profile_env
    put(cfg_dir / "radial.json", json.dumps(STRAY_MENUS))
    profiles.ensure()
    assert not (cfg_dir / "profiles" / "leftovers.json").exists()


def test_a_leftover_is_not_a_stray_and_is_moved_by_tidy_leftovers(profile_env, monkeypatch):
    cfg_dir, _ = profile_env
    put(cfg_dir / "radial.json", json.dumps(STRAY_MENUS))
    with monkeypatch.context() as m:
        refuse_radial(m)
        profiles.ensure()
        assert profiles.strays()["menus"] is None
        profiles.tidy_leftovers()                          # still held: stays listed
        assert (cfg_dir / "radial.json").exists()
        assert "radial.json" in read(cfg_dir / "profiles" / "leftovers.json")
    profiles.tidy_leftovers()
    assert not (cfg_dir / "radial.json").exists()
    assert read(cfg_dir / "pre-profiles" / "radial.json") == STRAY_MENUS
    assert not (cfg_dir / "profiles" / "leftovers.json").exists()
    assert profiles.strays()["menus"] is None


def test_a_leftover_that_changed_afterwards_is_a_stray(profile_env, monkeypatch):
    cfg_dir, _ = profile_env
    put(cfg_dir / "radial.json", json.dumps(STRAY_MENUS))
    refuse_radial(monkeypatch)
    profiles.ensure()
    assert profiles.strays()["menus"] is None
    later = dict(STRAY_MENUS, ring={"radius": 150})
    put(cfg_dir / "radial.json", json.dumps(later))
    os.utime(cfg_dir / "radial.json", (1_000_000_000, 1_000_000_000))
    assert profiles.strays()["menus"] == str(cfg_dir / "radial.json")
    profiles.tidy_leftovers()                              # a changed file is not moved, and its entry goes
    assert (cfg_dir / "radial.json").exists()
    assert not (cfg_dir / "profiles" / "leftovers.json").exists()


def test_tidy_leftovers_drops_entries_whose_file_is_gone_and_never_raises(profile_env):
    cfg_dir, _ = profile_env
    profiles.ensure()
    profiles.tidy_leftovers()                              # no leftovers.json
    put(cfg_dir / "profiles" / "leftovers.json",
        json.dumps({"radial.json": {"folder": "config", "size": 1, "mtime_ns": 1}, "junk": 5}))
    profiles.tidy_leftovers()
    assert not (cfg_dir / "profiles" / "leftovers.json").exists()
    put(cfg_dir / "profiles" / "leftovers.json", "{nope")
    profiles.tidy_leftovers()


# --- strays --------------------------------------------------------------------------------------


def starter_raw():
    return json.loads(default_bytes().decode("utf-8-sig"))


def starter_tags_raw():
    return {"version": 1, "tags": {"favourite": {"label": "Favourites", "color": "#FFD166"},
                                   "blocking": {"label": "Blocking", "color": "#A8DF23"},
                                   "detailing": {"label": "Detailing", "color": "#C77DFF"}}, "items": {}}


@pytest.fixture
def migrated(profile_env):
    """profile_env after the first run, so the root files that appear now are what an older ZOrbit wrote."""
    profiles.ensure()
    return profile_env


def test_a_fresh_migrated_sandbox_has_no_strays(migrated):
    assert profiles.strays() == {"menus": None, "tags": None, "usage": None, "when": None}


def test_strays_reports_nothing_before_the_first_profile(profile_env):
    cfg_dir, data_dir = profile_env
    put(cfg_dir / "radial.json", json.dumps(STRAY_MENUS))
    put(cfg_dir / "tags.json", json.dumps(starter_tags_raw() | {"items": {"brush:a": ["blocking"]}}))
    put(data_dir / "usage.json", '{"brushes": {}}')
    assert profiles.strays() == {"menus": None, "tags": None, "usage": None, "when": None}


def test_strays_reports_nothing_while_a_menus_file_is_pinned(migrated, monkeypatch):
    put(migrated[0] / "radial.json", json.dumps(STRAY_MENUS))
    monkeypatch.setenv("ZORBIT_CONFIG_FILE", "x.json")
    assert profiles.strays()["menus"] is None


def test_the_shipped_starter_menus_are_not_a_stray(migrated):
    put(migrated[0] / "radial.json", default_bytes())
    assert profiles.strays()["menus"] is None


def test_starter_menus_with_only_bridge_and_browser_changed_are_not_a_stray(migrated):
    raw = starter_raw()
    raw["bridge"] = {"mode": "key", "key": "F9"}
    raw["browser"] = {"hotkey": "Alt+B"}
    put(migrated[0] / "radial.json", json.dumps(raw, indent=2))
    assert profiles.strays()["menus"] is None


def test_starter_menus_with_other_line_endings_or_indentation_are_not_a_stray(migrated):
    cfg_dir, _ = migrated
    put(cfg_dir / "radial.json", default_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert profiles.strays()["menus"] is None
    put(cfg_dir / "radial.json", json.dumps(starter_raw(), indent=4, ensure_ascii=False).encode("utf-8-sig"))
    assert profiles.strays()["menus"] is None
    put(cfg_dir / "radial.json", json.dumps(starter_raw(), separators=(",", ":")))
    assert profiles.strays()["menus"] is None


def test_menus_with_an_edited_title_are_a_stray(migrated):
    cfg_dir, _ = migrated
    raw = starter_raw()
    raw["menus"]["brushes"]["title"] = "My brushes"
    path = put(cfg_dir / "radial.json", json.dumps(raw))
    found = profiles.strays()
    assert found["menus"] == path
    assert found["tags"] is None and found["usage"] is None
    assert found["when"] == pytest.approx(os.stat(path).st_mtime)


def test_a_radial_menu_copy_at_the_root_is_not_a_stray(migrated):
    cfg_dir, _ = migrated
    old = cfg_dir.parent / "RadialMenu"
    text = json.dumps(STRAY_MENUS)
    put(old / "radial.json", text)
    put(cfg_dir / "radial.json", text)
    assert profiles.strays()["menus"] is None
    put(cfg_dir / "radial.json", text + " ")                  # edited since: no longer the same file
    assert profiles.strays()["menus"] == str(cfg_dir / "radial.json")


def test_starter_tags_are_not_a_stray_and_tagged_items_are(migrated):
    cfg_dir, _ = migrated
    put(cfg_dir / "tags.json", json.dumps(starter_tags_raw()))
    assert profiles.strays()["tags"] is None
    raw = starter_tags_raw()
    raw["items"] = {"brush:claybuildup": ["blocking"]}
    path = put(cfg_dir / "tags.json", json.dumps(raw))
    assert profiles.strays()["tags"] == path


def test_changed_tags_are_a_stray(migrated):
    cfg_dir, _ = migrated
    raw = starter_tags_raw()
    raw["tags"]["sculpt"] = {"label": "Sculpt", "color": "#4DC8E9"}
    put(cfg_dir / "tags.json", json.dumps(raw))
    assert profiles.strays()["tags"] == str(cfg_dir / "tags.json")
    raw = starter_tags_raw()
    raw["tags"]["blocking"]["color"] = "#112233"
    put(cfg_dir / "tags.json", json.dumps(raw))
    assert profiles.strays()["tags"] == str(cfg_dir / "tags.json")


def test_usage_at_the_data_root_is_a_stray_unless_it_is_the_radial_menu_one(migrated):
    cfg_dir, data_dir = migrated
    text = json.dumps({"brushes": {"pinch": {"name": "Pinch", "score": 1.0, "t": 1000.0}}})
    put(data_dir.parent / "RadialMenu" / "usage.json", text)
    put(data_dir / "usage.json", text)
    assert profiles.strays()["usage"] is None
    path = put(data_dir / "usage.json", text.replace("1.0", "2.0"))
    assert profiles.strays()["usage"] == path


def test_siblings_and_temp_files_are_never_strays(migrated):
    cfg_dir, data_dir = migrated
    for n in ("radial.json.bak", "radial.json.broken", "tags.json.bak", "radial.json.1234.tmp"):
        put(cfg_dir / n, json.dumps(STRAY_MENUS))
    for n in ("usage.json.bad", "usage.json.1234.tmp"):
        put(data_dir / n, '{"brushes": {}}')
    assert profiles.strays() == {"menus": None, "tags": None, "usage": None, "when": None}


@pytest.mark.parametrize("text", ["{nope", "[]", "5", ""])
def test_a_root_file_that_is_not_a_json_object_is_ignored(migrated, text):
    cfg_dir, data_dir = migrated
    put(cfg_dir / "radial.json", text)
    put(cfg_dir / "tags.json", text)
    put(data_dir / "usage.json", text)
    assert profiles.strays() == {"menus": None, "tags": None, "usage": None, "when": None}


def test_when_is_the_newest_stray(migrated):
    cfg_dir, data_dir = migrated
    a = put(cfg_dir / "radial.json", json.dumps(STRAY_MENUS))
    b = put(data_dir / "usage.json", '{"brushes": {}}')
    os.utime(a, (1_700_000_000, 1_700_000_000))
    os.utime(b, (1_700_000_500, 1_700_000_500))
    found = profiles.strays()
    assert (found["menus"], found["usage"]) == (a, b)
    assert found["when"] == 1_700_000_500


def test_strays_reports_nothing_when_the_files_are_too_new(migrated):
    put(migrated[0] / "radial.json", json.dumps(STRAY_MENUS))
    write_stamp(migrated[0])
    assert profiles.strays()["menus"] is None


# --- set_aside -----------------------------------------------------------------------------------


def aside_folders(cfg_dir):
    return sorted(n for n in os.listdir(cfg_dir / "pre-profiles") if os.path.isdir(cfg_dir / "pre-profiles" / n))


def test_set_aside_moves_a_file_and_its_siblings_into_a_stamped_folder(migrated):
    cfg_dir, data_dir = migrated
    for n in ("radial.json", "radial.json.bak", "radial.json.broken", "radial.json.bad"):
        put(cfg_dir / n, n)
    put(cfg_dir / "tags.json", "tags")
    put(cfg_dir / "tags.json.bak", "tags bak")
    put(data_dir / "usage.json", "usage")
    put(data_dir / "usage.json.bad", "usage bad")
    put(cfg_dir / "other.json", "stays")
    folder = profiles.set_aside([str(cfg_dir / "radial.json"), str(cfg_dir / "tags.json"),
                                 str(data_dir / "usage.json")])
    assert os.path.dirname(folder) == str(cfg_dir / "pre-profiles")
    assert len(os.path.basename(folder)) == len("20260101-120000")
    assert sorted(os.listdir(folder)) == ["radial.json", "radial.json.bad", "radial.json.bak", "radial.json.broken",
                                          "tags.json", "tags.json.bak", "usage.json", "usage.json.bad"]
    assert (cfg_dir / "other.json").exists()
    assert not any((cfg_dir / n).exists() for n in ("radial.json", "radial.json.bak", "tags.json"))
    assert not (data_dir / "usage.json").exists()
    with open(os.path.join(folder, "usage.json"), encoding="utf-8") as f:
        assert f.read() == "usage"


def test_two_set_asides_in_one_second_get_distinct_folders(migrated, monkeypatch):
    cfg_dir, _ = migrated
    monkeypatch.setattr(profiles.time, "strftime", lambda fmt: "20260101-120000")
    put(cfg_dir / "radial.json", "one")
    first = profiles.set_aside([str(cfg_dir / "radial.json")])
    put(cfg_dir / "radial.json", "two")
    second = profiles.set_aside([str(cfg_dir / "radial.json")])
    put(cfg_dir / "radial.json", "three")
    third = profiles.set_aside([str(cfg_dir / "radial.json")])
    assert [os.path.basename(f) for f in (first, second, third)] == ["20260101-120000", "20260101-120000-2",
                                                                      "20260101-120000-3"]
    assert (cfg_dir / "pre-profiles" / "20260101-120000-2" / "radial.json").read_text() == "two"


def test_set_aside_with_nothing_to_move_returns_none_and_makes_no_folder(migrated):
    cfg_dir, _ = migrated
    assert profiles.set_aside([str(cfg_dir / "radial.json")]) is None
    assert profiles.set_aside([]) is None
    assert not (cfg_dir / "pre-profiles").exists() or aside_folders(cfg_dir) == []


def test_set_aside_leaves_a_file_it_cannot_move(migrated, monkeypatch):
    cfg_dir, _ = migrated
    put(cfg_dir / "radial.json", "menus")
    put(cfg_dir / "tags.json", "tags")

    def refuse(src, dst, *a, **k):
        if os.path.basename(src) == "radial.json":
            raise PermissionError("held")
        return real(src, dst, *a, **k)
    real = shutil.move
    monkeypatch.setattr(profiles.shutil, "move", refuse)
    folder = profiles.set_aside([str(cfg_dir / "radial.json"), str(cfg_dir / "tags.json")])
    assert os.listdir(folder) == ["tags.json"]
    assert (cfg_dir / "radial.json").exists()
    assert profiles.set_aside([str(cfg_dir / "radial.json")]) is None
    assert aside_folders(cfg_dir) == [os.path.basename(folder)]


# --- create from strays --------------------------------------------------------------------------


def test_create_strays_takes_the_old_menus_and_tags(active_profile):
    cfg_dir, folder = active_profile
    stray_menus = dict(STRAY_MENUS, bridge={"mode": "old"}, browser={"hotkey": "Alt+Z"})
    tags = starter_tags_raw()
    tags["items"] = {"brush:standard": ["blocking"]}
    put(cfg_dir / "radial.json", json.dumps(stray_menus))
    put(cfg_dir / "radial.json.bak", "bak")
    put(cfg_dir / "tags.json", json.dumps(tags))
    assert profiles.create("Older", "strays") == "Older"
    made = cfg_dir / "profiles" / "Older"
    raw = read(made / "radial.json")
    assert raw["menus"]["main"]["title"] == "Edited"
    assert raw["bridge"] == BRIDGE and raw["browser"] == BROWSER       # this PC's, not the old file's
    assert read(made / "tags.json") == tags
    assert not (made / "usage.json").exists()
    assert profiles.active() == "Default"
    assert not (cfg_dir / "radial.json").exists() and not (cfg_dir / "tags.json").exists()
    assert not (cfg_dir / "radial.json.bak").exists()
    [stamped] = aside_folders(cfg_dir)
    assert sorted(os.listdir(cfg_dir / "pre-profiles" / stamped)) == ["radial.json", "radial.json.bak", "tags.json"]
    assert profiles.strays()["menus"] is None
    assert staging(cfg_dir) == []


def test_create_strays_with_only_tags_uses_the_starter_menus(active_profile):
    cfg_dir, _ = active_profile
    tags = starter_tags_raw()
    tags["items"] = {"brush:standard": ["detailing"]}
    put(cfg_dir / "tags.json", json.dumps(tags))
    profiles.create("Tags only", "strays")
    made = cfg_dir / "profiles" / "Tags only"
    expected = starter_raw()
    expected.update(bridge=BRIDGE, browser=BROWSER)
    assert read(made / "radial.json") == expected
    assert read(made / "tags.json") == tags
    assert not (cfg_dir / "tags.json").exists()


def test_create_strays_with_only_menus_has_no_tags_file(active_profile):
    cfg_dir, _ = active_profile
    put(cfg_dir / "radial.json", json.dumps(STRAY_MENUS))
    profiles.create("Menus only", "strays")
    assert not (cfg_dir / "profiles" / "Menus only" / "tags.json").exists()


def test_create_strays_leaves_the_usage_stray_for_absorb_stray_usage(active_profile):
    cfg_dir, folder = active_profile
    data_dir = cfg_dir.parent.parent / "Local" / "ZOrbit"
    put(cfg_dir / "radial.json", json.dumps(STRAY_MENUS))
    put(data_dir / "usage.json", '{"brushes": {}}')
    profiles.create("Older", "strays")
    assert (data_dir / "usage.json").exists()


def test_create_strays_with_no_strays_is_refused(active_profile):
    cfg_dir, _ = active_profile
    put(cfg_dir / "radial.json", default_bytes())              # an untouched starter is no stray
    put(cfg_dir / "tags.json", json.dumps(starter_tags_raw()))
    with pytest.raises(ProfileError, match="There are no files from an older version to bring in."):
        profiles.create("Older", "strays")
    assert profiles.names() == ["Default"]
    assert staging(cfg_dir) == []
    assert (cfg_dir / "radial.json").exists()


def test_create_strays_that_fails_to_build_sets_nothing_aside(active_profile, monkeypatch):
    import config
    cfg_dir, _ = active_profile
    put(cfg_dir / "radial.json", json.dumps(STRAY_MENUS))

    def refuse(path, *a, **k):
        raise ValueError("no")
    monkeypatch.setattr(config, "load", refuse)
    with pytest.raises(ProfileError, match="The menus could not be read"):
        profiles.create("Older", "strays")
    assert profiles.names() == ["Default"]
    assert (cfg_dir / "radial.json").exists()
    assert not (cfg_dir / "pre-profiles").exists() or aside_folders(cfg_dir) == []
    assert staging(cfg_dir) == []


# --- absorb_stray_usage --------------------------------------------------------------------------

T = 1_800_000_000.0


def test_absorb_stray_usage_adds_the_old_scores_and_counts_once(active_profile):
    import usage
    cfg_dir, folder = active_profile
    data_dir = cfg_dir.parent.parent / "Local" / "ZOrbit"
    mine = usage.Usage(str(folder / "usage.json"))
    mine.record("ClayBuildup", T)
    mine.record_pick("brush", "ClayBuildup", T)
    mine.save()
    stray = {"brushes": {"claybuildup": {"name": "ClayBuildup", "score": 2.0, "t": T},
                         "pinch": {"name": "Pinch", "score": 4.0, "t": T}},
             "picks": {"brush:claybuildup": {"name": "ClayBuildup", "count": 5, "t": T + 10}}}
    put(data_dir / "usage.json", json.dumps(stray))
    put(data_dir / "usage.json.bad", "old bad")
    assert profiles.absorb_stray_usage(now=T) == 2
    after = usage.Usage(str(folder / "usage.json")).load()
    assert after.score("claybuildup", T) == pytest.approx(3.0)
    assert after.score("pinch", T) == pytest.approx(4.0)
    assert after.picks["brush:claybuildup"]["count"] == 6
    assert not (data_dir / "usage.json").exists() and not (data_dir / "usage.json.bad").exists()
    [stamped] = aside_folders(cfg_dir)
    assert read(cfg_dir / "pre-profiles" / stamped / "usage.json") == stray
    assert profiles.absorb_stray_usage(now=T) == 0
    assert usage.Usage(str(folder / "usage.json")).load().score("claybuildup", T) == pytest.approx(3.0)


def test_absorb_stray_usage_with_nothing_to_absorb_is_zero(active_profile):
    cfg_dir, _ = active_profile
    assert profiles.absorb_stray_usage() == 0
    assert not (cfg_dir / "pre-profiles").exists()


def test_absorb_stray_usage_goes_into_the_active_profile(active_profile):
    import usage
    cfg_dir, _ = active_profile
    data_dir = cfg_dir.parent.parent / "Local" / "ZOrbit"
    make_profile(cfg_dir, "Other")
    profiles.set_active("Other")
    put(data_dir / "usage.json", json.dumps({"brushes": {"pinch": {"name": "Pinch", "score": 1.0, "t": T}}}))
    assert profiles.absorb_stray_usage(now=T) == 1
    assert usage.Usage(str(cfg_dir / "profiles" / "Other" / "usage.json")).load().score("pinch", T) == 1.0
    assert usage.Usage(str(cfg_dir / "profiles" / "Default" / "usage.json")).load().brushes == {}
