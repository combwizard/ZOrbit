"""The app reads the library again when the user changes the library folders in Studio (studio.json)."""
import json
import threading
from pathlib import Path

import pytest

import assets
import brushes
import paths
import radiald


def touch(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


@pytest.fixture(autouse=True)
def fresh_library(monkeypatch, tmp_path):
    """No stored walk or index from another test, no ZBrush, and a studio.json of the test's own."""
    monkeypatch.setattr(assets, "_index", {})
    monkeypatch.setattr(assets, "_walks", {})
    monkeypatch.setattr(assets, "_walk_t0", {})
    monkeypatch.setattr(brushes, "_index", None)
    monkeypatch.setattr(brushes, "_walk", None)
    monkeypatch.setattr(brushes, "_walk_t0", float("-inf"))
    monkeypatch.setattr(brushes, "zbrush_dirs", lambda: {"install": None, "user_assets": None})
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "config").mkdir()


def set_folders(**kinds):
    with open(Path(paths.CONFIG_DIR) / "studio.json", "w", encoding="utf-8") as f:
        json.dump({"library_folders": {k: [str(p) for p in v] for k, v in kinds.items()}}, f)


def wait_done(app, timeout=10):
    t = app._lib_rebuild
    if t is not None:
        t.join(timeout)
        assert not t.is_alive()
    assert app._lib_rebuild is None


@pytest.fixture
def app():
    return radiald.App(paths.DEFAULT_MENUS)


def test_first_check_only_stores(app, monkeypatch):
    calls = []
    monkeypatch.setattr(assets, "library", lambda kind: calls.append(kind))
    assets._index["alpha"] = {}
    app._check_library_folders()
    assert app._lib_sig == brushes.user_folders_signature()
    assert app._lib_rebuild is None and not calls


def test_a_new_folder_is_read(app, tmp_path):
    rock = touch(tmp_path / "mine" / "Rock Face.png")
    set_folders()
    assert assets.index("alpha") == {}                  # built, from no folder
    assert assets.has_built("alpha") and not assets.has_built("brush")
    app._check_library_folders()
    gen = assets.generation
    set_folders(alpha=[tmp_path / "mine"])
    app._check_library_folders()
    wait_done(app)
    assert assets.generation == gen + 1
    assert assets.find("alpha", "Rock Face") == rock
    assert not assets.has_built("brush")               # a kind never built is left for later


def test_a_change_during_a_rebuild_is_not_lost(app, monkeypatch, tmp_path):
    entered, release = threading.Event(), threading.Event()
    seen = []

    def slow(kind):
        seen.append(brushes.user_folders_signature())
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(assets, "library", slow)
    assets._index["alpha"] = {}
    set_folders()
    app._check_library_folders()
    set_folders(alpha=[tmp_path / "one"])
    app._check_library_folders()
    assert entered.wait(10)
    first = app._lib_rebuild
    set_folders(alpha=[tmp_path / "one", tmp_path / "two"])
    app._check_library_folders()
    assert app._lib_rebuild is first                    # no second thread: the running one goes round again
    release.set()
    wait_done(app)
    assert len(seen) == 2
    assert seen[-1] == brushes.user_folders_signature()     # the last pass read the latest folders


def test_unchanged_does_nothing(app, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(assets, "library", lambda kind: calls.append(kind))
    assets._index["alpha"] = {}
    set_folders(alpha=[tmp_path / "one"])
    for _ in range(3):
        app._check_library_folders()
    assert app._lib_rebuild is None and not calls


def test_a_failed_read_logs_once(app, monkeypatch):
    lines = []
    monkeypatch.setattr(radiald, "log", lines.append)

    def broken():
        raise OSError("no")

    monkeypatch.setattr(brushes, "user_folders_signature", broken)
    for _ in range(3):
        app._check_library_folders()
    assert len(lines) == 1 and app._lib_sig is None
