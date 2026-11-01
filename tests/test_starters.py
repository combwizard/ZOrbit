"""default_menus.json: every version that ever shipped is known to profiles.strays() as an untouched starter."""
import json
import os
import subprocess

import pytest

import paths
import profiles

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = ("radial_menu/default_menus.json", "zorbit/default_menus.json")      # where the file lived over time


def git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True)


def digest(data: bytes) -> str:
    return profiles.canonical_hash(json.loads(data.decode("utf-8-sig")))


def test_the_shipped_file_is_a_known_starter():
    with open(paths.DEFAULT_MENUS, "rb") as f:
        assert digest(f.read()) in profiles.KNOWN_STARTERS, \
            "default_menus.json changed: add its canonical hash to KNOWN_STARTERS in profiles.py"


def test_every_version_in_git_history_is_a_known_starter():
    try:
        shallow = git("rev-parse", "--is-shallow-repository")
        log = git("log", "--format=%H", "--", *FILES)
    except OSError:
        pytest.skip("git is not available")
    if shallow.returncode != 0 or log.returncode != 0:
        pytest.skip("this is not a git checkout")
    if shallow.stdout.strip() == b"true":
        pytest.skip("a shallow clone has no history")
    commits = log.stdout.decode().split()
    if not commits:
        pytest.skip("no history for default_menus.json")
    missing = []
    for sha in commits:
        for name in FILES:
            shown = git("show", f"{sha}:{name}")
            if shown.returncode == 0:                     # the commit that deleted the file has no copy
                if digest(shown.stdout) not in profiles.KNOWN_STARTERS:
                    missing.append(f"{sha[:7]} {name} {digest(shown.stdout)}")
                break
    assert not missing, "add these to KNOWN_STARTERS in profiles.py:\n" + "\n".join(missing)


def test_known_starters_are_all_hex_digests():
    assert all(len(h) == 64 and set(h) <= set("0123456789abcdef") for h in profiles.KNOWN_STARTERS)
