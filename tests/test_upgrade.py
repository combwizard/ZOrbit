"""Upgrades from real older versions: the files they left on disk (tests/fixtures/upgrade/, made by
tools/make_upgrade_fixtures.py) are run through this build's first start in a separate process, the way an
installed update would, and the profile that comes out is checked. The downgrade fixture is the other way round:
files an older ZOrbit wrote at the old places after the move."""
import json
import os
import shutil
import subprocess
import sys

import pytest

import paths
import profiles

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures", "upgrade")
ZORBIT_DIR = os.path.join(os.path.dirname(HERE), "zorbit")
RELEASES = sorted(d for d in os.listdir(FIXTURES) if d != "downgrade" and os.path.isdir(os.path.join(FIXTURES, d))) \
    if os.path.isdir(FIXTURES) else []
NO_STRAYS = {"menus": None, "tags": None, "usage": None, "when": None}


def test_the_fixtures_are_there():
    assert {"v0.7.0", "v0.7.1", "v0.9.0", "v0.12.0"} <= set(RELEASES)
    assert os.path.isdir(os.path.join(FIXTURES, "downgrade"))


def copy_fixture(name, tmp_path):
    """tmp_path\\Roaming and tmp_path\\Local from the fixture."""
    for part in ("Roaming", "Local"):
        shutil.copytree(os.path.join(FIXTURES, name, part), tmp_path / part)
    return tmp_path / "Roaming", tmp_path / "Local"


def run_ensure(tmp_path):
    """This build's profiles.ensure() in its own process, on the folders under tmp_path."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ZORBIT_", "PYTHON"))}
    env.update(APPDATA=str(tmp_path / "Roaming"), LOCALAPPDATA=str(tmp_path / "Local"), PYTHONPATH=ZORBIT_DIR,
               PYTHONDONTWRITEBYTECODE="1")
    done = subprocess.run([sys.executable, "-c", "import profiles; profiles.ensure()"], env=env, cwd=str(tmp_path),
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr


def point_at(tmp_path, monkeypatch):
    """This process looks at the copies: paths.CONFIG_DIR and DATA_DIR, with profiles on. Returns both."""
    for var in ("ZORBIT_CONFIG_FILE", "ZORBIT_TAGS_FILE", "ZORBIT_USAGE_FILE"):
        monkeypatch.delenv(var, raising=False)
    cfg_dir, data_dir = tmp_path / "Roaming" / "ZOrbit", tmp_path / "Local" / "ZOrbit"
    monkeypatch.setattr(paths, "CONFIG_DIR", str(cfg_dir))
    monkeypatch.setattr(paths, "DATA_DIR", str(data_dir))
    profiles._forget()
    return cfg_dir, data_dir


def snapshot(top):
    """{relative path: (modification time, size)} of every file under top."""
    out = {}
    for here, _, names in os.walk(top):
        for n in names:
            p = os.path.join(here, n)
            st = os.stat(p)
            out[os.path.relpath(p, top)] = (st.st_mtime_ns, st.st_size)
    return out


def contents(folder):
    """{file name: bytes} of the plain files in a folder (empty when there is none)."""
    if not os.path.isdir(folder):
        return {}
    return {n: open(os.path.join(folder, n), "rb").read() for n in sorted(os.listdir(folder))
            if os.path.isfile(os.path.join(folder, n))}


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def first_title(cfg):
    return next(iter(cfg["menus"].values()))["title"]


# --- an older version's files, moved into the Default profile -------------------------------------------


@pytest.mark.parametrize("name", RELEASES)
def test_an_old_install_becomes_the_default_profile(name, tmp_path, monkeypatch):
    roaming, local = copy_fixture(name, tmp_path)
    legacy = (roaming / "RadialMenu").is_dir()              # Radial Menu, before the rename to ZOrbit
    folder = "RadialMenu" if legacy else "ZOrbit"
    old_cfg, old_data = roaming / folder, local / folder
    had = {"menus": contents(old_cfg), "usage": contents(old_data)}
    had_tags = "tags.json" in had["menus"]
    studio_before = had["menus"]["studio.json"]
    assert "radial.json" in had["menus"] and "usage.json" in had["usage"]
    legacy_before = {"cfg": contents(old_cfg), "data": contents(old_data)}

    run_ensure(tmp_path)
    cfg_dir, data_dir = point_at(tmp_path, monkeypatch)
    default = cfg_dir / "profiles" / "Default"

    # the profile holds the user's menus (and tags and usage) byte for byte
    assert first_title(read(default / "radial.json")) == "Upgrade test menu"
    assert (default / "radial.json").read_bytes() == had["menus"]["radial.json"]
    assert (default / "radial.json.bak").read_bytes() == had["menus"]["radial.json.bak"]
    assert (default / "usage.json").read_bytes() == had["usage"]["usage.json"]
    usage_file = read(default / "usage.json")
    assert any(e["name"] == "ClayBuildup" for e in usage_file["brushes"].values())
    assert (default / "tags.json").exists() == had_tags
    if had_tags:
        tags_file = read(default / "tags.json")
        key = next(k for k, t in tags_file["tags"].items() if t["label"] == "Upgrade tag")
        assert key in tags_file["items"]["brush:claybuildup"]
        assert (default / "tags.json").read_bytes() == had["menus"]["tags.json"]
    assert read(cfg_dir / "profile.json") == {"active": "Default"}
    assert read(cfg_dir / "profiles" / "format.json")["format"] == profiles.FORMAT
    assert profiles.names() == ["Default"] and profiles.active() == "Default"

    # studio.json and popout.json belong to the PC: still at the root, as they were
    assert (cfg_dir / "studio.json").read_bytes() == studio_before
    if "popout.json" in had["menus"]:
        assert (cfg_dir / "popout.json").read_bytes() == had["menus"]["popout.json"]

    if legacy:
        # the Radial Menu folders are copied from and left as they were; nothing was set aside
        assert {"cfg": contents(old_cfg), "data": contents(old_data)} == legacy_before
        assert not (cfg_dir / "pre-profiles").exists()
    else:
        # the root files went to pre-profiles\, and nothing of the three kinds is left at the old places
        kept = cfg_dir / "pre-profiles"
        for kind, folder in (("menus", cfg_dir), ("usage", data_dir)):
            for fname, data in had[kind].items():
                if fname.split(".")[0] in ("radial", "tags", "usage"):
                    assert (kept / fname).read_bytes() == data
                    assert not (folder / fname).exists()

    # what comes out reads with the current loaders
    import config
    import tags
    import usage
    store = tags.TagStore(str(default / "tags.json")).load()
    assert not store.error
    cfg = config.load(str(default / "radial.json"), store)
    assert not cfg.errors and next(iter(cfg.menus.values())).title == "Upgrade test menu"
    assert "claybuildup" in usage.Usage(str(default / "usage.json")).load().brushes

    # nothing is left over for the Studio to offer, and a second start writes nothing
    assert profiles.strays() == NO_STRAYS
    before = snapshot(tmp_path)
    run_ensure(tmp_path)
    assert snapshot(tmp_path) == before
    profiles._forget()
    assert profiles.strays() == NO_STRAYS


# --- the Studio's first-run decision on an old studio.json -------------------------------------------


@pytest.mark.parametrize("name", RELEASES)
def test_an_old_studio_json_skips_the_setup_screen(name, tmp_path, monkeypatch):
    """Whoever had a Studio before is not sent to Setup, with or without a setup_done key (v0.9.0 had none)."""
    import studio
    roaming, _ = copy_fixture(name, tmp_path)
    src = next(p / "studio.json" for p in (roaming / "ZOrbit", roaming / "RadialMenu") if (p / "studio.json").exists())
    raw = read(src)
    if name == "v0.9.0":
        assert "setup_done" not in raw                        # the case this test is here for
    cfg = tmp_path / "radial.json"
    cfg.write_bytes(open(paths.DEFAULT_MENUS, "rb").read())
    monkeypatch.setenv("ZORBIT_CONFIG_FILE", str(cfg))        # profiles off: nothing else is touched
    monkeypatch.setattr(studio, "STUDIO_FILE", str(src))
    monkeypatch.setattr(studio, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(studio, "_STARTUP_LOG", str(tmp_path / "studio.log"))
    prefs = studio.Api().get_prefs()
    assert prefs["setup_done"] is True
    assert read(src)["setup_done"] is True
    assert prefs["check_updates"] is False                    # the user's own choice is kept
    assert prefs["tour_seen"] is True                         # nor offered the tour


# --- an older ZOrbit started again after the move ------------------------------------------------------


def test_files_an_older_version_wrote_after_the_move_are_strays(tmp_path, monkeypatch):
    copy_fixture("downgrade", tmp_path)
    cfg_dir, data_dir = point_at(tmp_path, monkeypatch)
    assert read(cfg_dir / "profile.json") == {"active": "Default"}
    assert first_title(read(cfg_dir / "profiles" / "Default" / "radial.json")) == "Upgrade test menu"
    found = profiles.strays()
    assert found["menus"] == str(cfg_dir / "radial.json")      # edited, so not taken for a starter
    assert found["tags"] == str(cfg_dir / "tags.json")
    assert found["usage"] == str(data_dir / "usage.json")
    assert found["when"]


def test_a_profile_can_be_made_from_the_strays(tmp_path, monkeypatch):
    copy_fixture("downgrade", tmp_path)
    cfg_dir, data_dir = point_at(tmp_path, monkeypatch)
    studio_before = (cfg_dir / "studio.json").read_bytes()
    assert profiles.create("Old", "strays") == "Old"
    assert first_title(read(profiles.config_file("Old"))) == "Downgrade edit"
    tags_file = read(profiles.tags_file("Old"))
    key = next(k for k, t in tags_file["tags"].items() if t["label"] == "Downgrade tag")
    assert key in tags_file["items"]["brush:claybuildup"]
    assert profiles.active() == "Default"                       # making a profile does not switch to it
    # the files went to pre-profiles\<stamp>\, with their .bak, and are gone from the old places
    stamps = [d for d in os.listdir(cfg_dir / "pre-profiles") if (cfg_dir / "pre-profiles" / d).is_dir()]
    assert len(stamps) == 1
    assert sorted(os.listdir(cfg_dir / "pre-profiles" / stamps[0])) == ["radial.json", "radial.json.bak", "tags.json"]
    assert first_title(read(cfg_dir / "pre-profiles" / stamps[0] / "radial.json")) == "Downgrade edit"
    for name in ("radial.json", "radial.json.bak", "tags.json"):
        assert not (cfg_dir / name).exists()
    found = profiles.strays()
    assert found["menus"] is None and found["tags"] is None
    assert found["usage"] == str(data_dir / "usage.json")       # create() leaves usage to absorb_stray_usage()
    assert (cfg_dir / "studio.json").read_bytes() == studio_before


def test_stray_usage_is_added_once(tmp_path, monkeypatch):
    copy_fixture("downgrade", tmp_path)
    cfg_dir, data_dir = point_at(tmp_path, monkeypatch)
    mine = profiles.usage_file()
    assert "brush:move" not in read(mine)["picks"] and "brush:claybuildup" in read(mine)["picks"]
    made = read(data_dir / "usage.json")["brushes"]["move"]["t"]     # the fixture's own time: nothing fades
    assert profiles.absorb_stray_usage(now=made) == 1           # one brush: Move
    after = read(mine)
    assert after["picks"]["brush:move"]["count"] == 1
    assert after["picks"]["brush:claybuildup"]["count"] == 1     # what the profile had is kept
    assert not (data_dir / "usage.json").exists()
    assert profiles.strays()["usage"] is None
    stamps = [d for d in os.listdir(cfg_dir / "pre-profiles") if (cfg_dir / "pre-profiles" / d).is_dir()]
    assert len(stamps) == 1 and (cfg_dir / "pre-profiles" / stamps[0] / "usage.json").is_file()
    before = open(mine, "rb").read()
    assert profiles.absorb_stray_usage() == 0                   # the file is gone: nothing is counted twice
    assert open(mine, "rb").read() == before
