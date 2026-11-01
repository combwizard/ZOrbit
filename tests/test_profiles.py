"""profiles.py: the profile folders, the pointer, the first-run migration, and fsutil.named_lock."""
import json
import os
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
    assert sorted(os.listdir(cfg_dir / "profiles")) == ["Default"]
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
