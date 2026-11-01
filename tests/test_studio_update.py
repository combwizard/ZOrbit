"""Studio's own update: which release file it trusts, the checked download, and the command line it gives Setup.
Nothing here reaches GitHub, starts a process or touches the real %LOCALAPPDATA%."""
import hashlib
import io
import json
import urllib.error

import pytest

import paths
import studio

SETUP = b"MZ pretend setup " * 1000
SHA = hashlib.sha256(SETUP).hexdigest()
NAME = "ZOrbitSetup-9.0.0.exe"
URL = studio.DOWNLOAD_URL + "v9.0.0/" + NAME


def _release(digest=True, body_hash=SHA, url=URL, size=len(SETUP), name=NAME):
    asset = {"name": name, "browser_download_url": url, "size": size}
    if digest:
        asset["digest"] = "sha256:" + (SHA if digest is True else digest)
    body = "Download it.\n\n```\n" + (f"{body_hash}  {name}\n" if body_hash else "") + "```\n"
    return {"tag_name": "v9.0.0", "body": body, "assets": [asset]}


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


@pytest.fixture
def api(tmp_path, monkeypatch):
    cfg = tmp_path / "radial.json"
    cfg.write_bytes(open(paths.DEFAULT_MENUS, "rb").read())
    monkeypatch.setenv("ZORBIT_CONFIG_FILE", str(cfg))
    monkeypatch.setattr(studio, "STUDIO_FILE", str(tmp_path / "studio.json"))
    monkeypatch.setattr(studio, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(studio, "_STARTUP_LOG", str(tmp_path / "studio.log"))
    monkeypatch.setattr(paths, "CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(studio, "_installed_here", lambda: True)
    return studio.Api()


def _serve(monkeypatch, release, payload=SETUP, calls=None):
    """urlopen answers the releases API with release and the setup URL with payload (an exception is raised)."""
    import urllib.request

    def fake(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        if calls is not None:
            calls.append(url)
        if url == studio.RELEASES_API:
            return _Resp(json.dumps(release).encode())
        if isinstance(payload, Exception):
            raise payload
        return _Resp(payload)
    monkeypatch.setattr(urllib.request, "urlopen", fake)


# --- which file is trusted ------------------------------------------------------------------------------

def test_the_setup_is_taken_with_the_hash_github_and_the_notes_agree_on():
    s = studio._setup_asset(_release(), "9.0.0")
    assert s == {"name": NAME, "url": URL, "size": len(SETUP), "sha256": SHA, "version": "9.0.0"}
    assert studio._setup_asset(_release(digest=False), "9.0.0")["sha256"] == SHA        # notes only
    assert studio._setup_asset(_release(body_hash=None), "9.0.0")["sha256"] == SHA       # digest only


@pytest.mark.parametrize("rel", [
    _release(digest=False, body_hash=None),                                    # no hash anywhere
    _release(digest="0" * 64),                                                 # the two hashes disagree
    _release(url="https://example.com/v9.0.0/" + NAME),                        # not this project's releases
    _release(url=studio.DOWNLOAD_URL + "v9.0.0/Other.exe"),                    # a different file behind the name
    _release(size=0),
    _release(size=studio.SETUP_MAX_BYTES + 1),
    _release(name="ZOrbit-9.0.0-portable.zip"),                                # no setup in the release
    "not a release",
])
def test_a_setup_without_a_trusted_hash_or_from_elsewhere_is_not_offered(rel):
    assert studio._setup_asset(rel, "9.0.0") is None


def test_check_update_offers_the_install_only_for_an_installed_copy(api, monkeypatch):
    _serve(monkeypatch, _release())
    u = api.check_update()
    assert u["newer"] and u["latest"] == "9.0.0" and u["can_install"]
    monkeypatch.setattr(studio, "_installed_here", lambda: False)             # portable copy or checkout
    u = api.check_update()
    assert u["newer"] and not u["can_install"]


def test_dont_remind_me_again_skips_that_version_only(api, monkeypatch):
    _serve(monkeypatch, _release())
    assert api.check_update()["skipped"] is False
    api.set_pref("skipped_version", "9.0.0")
    u = api.check_update()
    assert u["skipped"] and u["newer"] and u["can_install"]         # still offered in Settings
    newer = _release(url=studio.DOWNLOAD_URL + "v9.1.0/ZOrbitSetup-9.1.0.exe", name="ZOrbitSetup-9.1.0.exe")
    newer["tag_name"] = "v9.1.0"
    newer["assets"][0]["name"] = "ZOrbitSetup-9.1.0.exe"
    _serve(monkeypatch, newer)
    u = api.check_update()
    assert u["latest"] == "9.1.0" and not u["skipped"]              # a newer release is pointed out again


def test_skipped_version_takes_only_a_version(api):
    assert api.set_pref("skipped_version", "nonsense")["skipped_version"] == ""
    assert api.set_pref("skipped_version", "0.15.0")["skipped_version"] == "0.15.0"
    assert api.set_pref("skipped_version", "")["skipped_version"] == ""


def test_a_checkout_is_never_an_installed_copy(monkeypatch):
    monkeypatch.setattr(paths, "FROZEN", False)
    assert studio._installed_here() is False


def test_check_update_clears_old_setups_when_nothing_is_newer(api, monkeypatch, tmp_path):
    old = tmp_path / "updates" / "ZOrbitSetup-0.1.0.exe"
    old.parent.mkdir()
    old.write_bytes(b"x")
    rel = _release()
    rel["tag_name"] = "v" + studio.VERSION
    _serve(monkeypatch, rel)
    assert api.check_update()["can_install"] is False
    assert not old.exists()


# --- the download -----------------------------------------------------------------------------------------

def test_the_download_is_checked_and_kept(api, monkeypatch, tmp_path):
    calls = []
    _serve(monkeypatch, _release(), calls=calls)
    api.check_update()
    r = api.download_update()
    assert r["ok"] and r["version"] == "9.0.0"
    dest = tmp_path / "updates" / NAME
    assert dest.read_bytes() == SETUP and not (tmp_path / "updates" / (NAME + ".part")).exists()
    p = api.get_update_progress()
    assert p["state"] == "ready" and p["done"] == p["total"] == len(SETUP)
    calls.clear()
    assert api.download_update()["ok"] and calls == []                           # already there: not fetched again


@pytest.mark.parametrize("payload, words", [
    (SETUP[:-1] + b"!", "SHA-256"),
    (SETUP[:100], "stopped before the end"),
    (SETUP + b"extra", "bigger than"),
    (urllib.error.URLError("no route"), "connection"),
    (urllib.error.HTTPError(URL, 404, "Not Found", {}, None), "404"),
])
def test_a_bad_download_is_deleted_and_said(api, monkeypatch, tmp_path, payload, words):
    _serve(monkeypatch, _release(), payload=payload)
    api.check_update()
    r = api.download_update()
    assert not r["ok"] and words in r["message"]
    assert not list(tmp_path.glob("updates/*"))                                  # no setup and no .part left
    p = api.get_update_progress()
    assert p["state"] == "failed" and words in p["message"]


def test_download_without_a_checked_release_says_so(api):
    r = api.download_update()
    assert not r["ok"] and "Check for updates" in r["message"]


# --- the hand-over to Setup -------------------------------------------------------------------------------

@pytest.fixture
def launched(api, monkeypatch):
    """Popen and the window close are recorded, not done."""
    seen = {"args": None, "closed": False}

    def popen(args, **kw):
        seen["args"] = args
    monkeypatch.setattr(studio.subprocess, "Popen", popen)
    monkeypatch.setattr(api, "win_close", lambda: seen.update(closed=True))
    monkeypatch.setattr(studio, "_mutex_exists", lambda name: name == studio.APP_MUTEX)
    return seen


def test_install_starts_setup_silently_and_closes_studio(api, monkeypatch, tmp_path, launched):
    _serve(monkeypatch, _release())
    api.check_update()
    assert api.download_update()["ok"]
    r = api.install_update()
    assert r["ok"] and launched["closed"] and api._allow_close
    args = launched["args"]
    assert args[0] == str(tmp_path / "updates" / NAME)
    for flag in ("/SILENT", "/NOCANCEL", "/NORESTART", "/RELAUNCH=1", "/STARTAPP=1"):
        assert flag in args
    assert f"/LOG={tmp_path / 'update-setup.log'}" in args


def test_install_leaves_the_app_off_when_it_was_not_running(api, monkeypatch, launched):
    monkeypatch.setattr(studio, "_mutex_exists", lambda name: False)
    _serve(monkeypatch, _release())
    api.check_update()
    api.download_update()
    api.install_update()
    assert "/STARTAPP=1" not in launched["args"] and "/RELAUNCH=1" in launched["args"]


def test_install_refuses_a_setup_that_changed_after_the_check(api, monkeypatch, tmp_path, launched):
    _serve(monkeypatch, _release())
    api.check_update()
    api.download_update()
    (tmp_path / "updates" / NAME).write_bytes(b"swapped")
    r = api.install_update()
    assert not r["ok"] and "changed on disk" in r["message"]
    assert launched["args"] is None and not launched["closed"] and not api._allow_close


def test_install_refuses_before_a_download_or_in_a_portable_copy(api, monkeypatch, launched):
    assert not api.install_update()["ok"]
    _serve(monkeypatch, _release())
    api.check_update()
    api.download_update()
    monkeypatch.setattr(studio, "_installed_here", lambda: False)
    r = api.install_update()
    assert not r["ok"] and "not installed with Setup" in r["message"]
    assert launched["args"] is None and not launched["closed"]


# --- the release notes in the dialog -----------------------------------------------------------------------

RELEASE_BODY = """Download **ZOrbitSetup-9.0.0.exe** and run it. `ZOrbit-9.0.0-portable.zip` is the portable version. SHA256:

```
%s  ZOrbitSetup-9.0.0.exe
```

More about this release on the blog: https://zorbit.lol/docs/blog/zorbit-9-0-0/


The ring got rounder. Say so on [#32](https://github.com/combwizard/zorbit/issues/32).

### Added

- A **Shape** setting,
  wrapped over two lines.
- A [blog](https://zorbit.lol/docs/blog/).

### Fixed

- A crash.
""" % SHA


def test_release_notes_drop_the_download_head_and_keep_the_changelog_section():
    import changelog
    n = changelog.release_notes(RELEASE_BODY, "9.0.0")
    assert n["summary"] == ["The ring got rounder. Say so on #32."]
    assert n["items"] == ["A **Shape** setting, wrapped over two lines.", "A blog.", "A crash."]
    assert n["blog"] == "https://zorbit.lol/docs/blog/zorbit-9-0-0/"
    assert changelog.release_notes(None, "9.0.0") == {"summary": [], "items": [], "blog": ""}


def test_release_notes_keep_at_most_the_item_limit():
    import changelog
    body = "\n".join(f"- item {i}" for i in range(100))
    assert len(changelog.release_notes(body, "9.0.0")["items"]) == changelog.NOTES_MAX_ITEMS


def test_check_update_hands_the_notes_to_the_dialog(api, monkeypatch):
    rel = _release()
    rel["body"] = RELEASE_BODY
    rel["published_at"] = "2026-11-20T10:00:00Z"
    _serve(monkeypatch, rel)
    n = api.check_update()["notes"]
    assert n["version"] == "9.0.0" and n["date"] == "2026-11-20" and n["url"].endswith("/tag/v9.0.0")
    assert n["items"][-1] == "A crash."
    assert api.check_update()["can_install"]                     # the hash in the same body still counts


def test_no_notes_when_nothing_is_newer(api, monkeypatch):
    rel = _release()
    rel["tag_name"] = "v" + studio.VERSION
    _serve(monkeypatch, rel)
    assert api.check_update()["notes"] is None
