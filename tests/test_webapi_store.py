"""webapi's tag store and usage store follow the active profile (or the pinned one), and retarget_ring and
get_tag_uses read the radial.json of the profile they are given. Nothing here touches the real %APPDATA%."""
import json
import os

import pytest

import profiles
import webapi


@pytest.fixture
def two(profile_env, monkeypatch):
    """Profiles Default and B in a throw-away folder, with webapi's stores and pin reset."""
    for name in ("_store", "_usage", "_pin"):
        monkeypatch.setattr(webapi, name, None)
    profiles.ensure()
    profiles.create("B", "starter")
    return profiles.tags_file("Default"), profiles.tags_file("B")


def test_store_follows_the_active_profile(two):
    default, b = two
    assert webapi.store().path == default
    profiles.set_active("B")
    assert webapi.store().path == b
    profiles.set_active("Default")
    assert webapi.store().path == default


def test_store_is_kept_while_the_path_stays_the_same(two):
    assert webapi.store() is webapi.store()


def test_pin_holds_a_profile_while_another_is_active(two):
    default, b = two
    profiles.set_active("B")
    webapi.pin("Default")
    assert profiles.active() == "B" and webapi.store().path == default
    webapi.pin(None)
    assert webapi.store().path == b


def test_a_pin_on_a_deleted_profile_falls_back_to_the_active_one(two):
    default, b = two
    profiles.set_active("B")
    webapi.pin("Default")
    profiles.delete("Default")
    assert webapi.store().path == b
    assert webapi.usage_store().path == profiles.usage_file("B")


def test_usage_store_follows_the_active_profile_and_the_pin(two):
    default, b = two
    assert webapi.usage_store().path == profiles.usage_file("Default")
    profiles.set_active("B")
    assert webapi.usage_store().path == profiles.usage_file("B")
    webapi.pin("Default")
    assert webapi.usage_store().path == profiles.usage_file("Default")
    webapi.pin(None)
    assert webapi.usage_store().path == profiles.usage_file("B")


def test_get_usage_reads_the_usage_of_the_profile_served(two):
    profiles.set_active("B")
    with open(profiles.usage_file("B"), "w", encoding="utf-8") as f:
        json.dump({"version": 1, "picks": {"brush:clay": {"name": "Clay", "count": 3, "t": 5}}}, f)
    assert webapi.LibraryApi().get_usage("brush")["recent"][0]["name"] == "Clay"
    profiles.set_active("Default")
    assert webapi.LibraryApi().get_usage("brush")["recent"] == []


def test_get_tags_is_not_unchanged_after_a_switch_between_profiles_without_tags_files(two):
    default, b = two
    assert not os.path.exists(default) and not os.path.exists(b)
    profiles.set_active("B")
    api = webapi.TagApi()
    full = api.get_tags(since_mtime_ns=0, since_path=default)
    assert "unchanged" not in full and full["path"] == b and full["tags"]
    assert api.get_tags(since_mtime_ns=0, since_path=b) == {"unchanged": True, "mtime_ns": 0}
    assert api.get_tags(since_mtime_ns=0) == {"unchanged": True, "mtime_ns": 0}      # an old page sends no path


def test_tag_changes_land_in_the_profile_served(two):
    default, b = two
    profiles.set_active("B")
    assert webapi.TagApi().create_tag("Mine")["ok"]
    assert os.path.exists(b) and not os.path.exists(default)


def _write_ring(profile, tag):
    path = profiles.config_file(profile)
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["menus"] = {"main": {"hotkey": "q", "items": [{"tag": tag}]}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return path


def _items(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["menus"]["main"]["items"]


def test_retarget_ring_rewrites_the_profile_it_is_given(two):
    a_path, b_path = _write_ring("Default", "x"), _write_ring("B", "x")
    assert webapi.retarget_ring({"x": "y"}, profile="B") == (1, None)
    assert _items(b_path) == [{"tag": "y"}] and _items(a_path) == [{"tag": "x"}]
    assert os.path.exists(b_path + ".bak") and not os.path.exists(a_path + ".bak")


def test_retarget_ring_without_a_profile_uses_the_one_served(two):
    a_path, b_path = _write_ring("Default", "x"), _write_ring("B", "x")
    profiles.set_active("B")
    assert webapi.retarget_ring({"x": "y"}) == (1, None)
    assert _items(b_path) == [{"tag": "y"}] and _items(a_path) == [{"tag": "x"}]
    webapi.pin("Default")
    assert webapi.retarget_ring({"x": "z"}) == (1, None)
    assert _items(a_path) == [{"tag": "z"}] and _items(b_path) == [{"tag": "y"}]


def test_get_tag_uses_reads_the_profile_it_is_given(two):
    _write_ring("Default", "x")
    _write_ring("B", "y")
    profiles.set_active("B")
    api = webapi.TagApi()
    assert api.get_tag_uses() == {"ok": True, "uses": {"y": 1}}
    assert api.get_tag_uses(profile="Default") == {"ok": True, "uses": {"x": 1}}
