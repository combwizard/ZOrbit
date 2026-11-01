"""Upgrades the fixtures in tests/fixtures/upgrade with a built ZOrbit.exe, from outside.

    python tools/upgrade_check.py dist\\ZOrbit\\ZOrbit.exe
    python tools/upgrade_check.py --python            # zorbit\\main.py of this checkout instead of an exe

Each older version's files (made by tools/make_upgrade_fixtures.py) are copied to a temporary folder, `--check` is
run on them with %APPDATA% and %LOCALAPPDATA% pointing there, and the layout it leaves is looked at: the menus in
profiles\\Default, the old files in pre-profiles\\, the stamp, studio.json where it was. For the downgrade fixture
(an older ZOrbit's files at the old places beside a profile) `--check` must exit 0 and leave them alone.
One line per fixture; the exit code is 1 when any fails. Standard library only: it does not import zorbit, so it
tests the packaged build, not the source it came from.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(REPO, "tests", "fixtures", "upgrade")
KINDS = ("radial.json", "tags.json", "usage.json")           # a file with this name, or this name and a dot, is data


def clean_env(roaming, local) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("ZORBIT_", "PYTHON"))}
    env.update(APPDATA=roaming, LOCALAPPDATA=local, PYTHONDONTWRITEBYTECODE="1")
    return env


def read_bytes(path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_json(path):
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def plain_files(folder) -> dict:
    """{name: bytes} of the plain files in a folder; empty when there is none."""
    if not os.path.isdir(folder):
        return {}
    return {n: read_bytes(os.path.join(folder, n)) for n in sorted(os.listdir(folder))
            if os.path.isfile(os.path.join(folder, n))}


def is_data(name) -> bool:
    return any(name == k or name.startswith(k + ".") for k in KINDS)


def first_title(cfg) -> str:
    return next(iter(cfg["menus"].values()))["title"]


def run_check(command, roaming, local) -> str:
    """Runs `<command> --check`; returns "" when it exits 0, else what went wrong."""
    try:
        done = subprocess.run([*command, "--check"], env=clean_env(roaming, local), cwd=os.path.dirname(roaming),
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    except subprocess.TimeoutExpired:
        return "--check did not finish in 120 s"
    except OSError as e:
        return f"could not run {command[0]}: {e}"
    if done.returncode != 0:
        return f"--check exited with {done.returncode}: " + (done.stdout + done.stderr).strip()[-600:]
    return ""


def check_release(name, command, work) -> str:
    """"" when the fixture upgraded as it should, else why not."""
    roaming, local = os.path.join(work, "Roaming"), os.path.join(work, "Local")
    shutil.copytree(os.path.join(FIXTURES, name, "Roaming"), roaming)
    shutil.copytree(os.path.join(FIXTURES, name, "Local"), local)
    legacy = os.path.isdir(os.path.join(roaming, "RadialMenu"))
    folder = "RadialMenu" if legacy else "ZOrbit"
    old_cfg, old_data = os.path.join(roaming, folder), os.path.join(local, folder)
    had_cfg, had_data = plain_files(old_cfg), plain_files(old_data)
    cfg_dir = os.path.join(roaming, "ZOrbit")
    default = os.path.join(cfg_dir, "profiles", "Default")

    why = run_check(command, roaming, local)
    if why:
        return why
    if not os.path.isfile(os.path.join(default, "radial.json")):
        return "profiles\\Default\\radial.json was not made"
    if first_title(read_json(os.path.join(default, "radial.json"))) != "Upgrade test menu":
        return "the Default profile does not hold the edited menu title"
    for fname, data in {**had_cfg, **had_data}.items():
        if is_data(fname) and read_bytes(os.path.join(default, fname)) != data:
            return f"profiles\\Default\\{fname} is not the old {fname}"
    if not os.path.isfile(os.path.join(cfg_dir, "profiles", "format.json")):
        return "profiles\\format.json was not written"
    if read_json(os.path.join(cfg_dir, "profile.json")).get("active") != "Default":
        return "profile.json does not point at Default"
    if read_bytes(os.path.join(cfg_dir, "studio.json")) != had_cfg["studio.json"]:
        return "studio.json is not where or what it was"
    if legacy:
        if plain_files(old_cfg) != had_cfg or plain_files(old_data) != had_data:
            return "the RadialMenu folders were changed"
    else:
        kept = os.path.join(cfg_dir, "pre-profiles")
        for folder_, files in ((cfg_dir, had_cfg), (os.path.join(local, "ZOrbit"), had_data)):
            for fname, data in files.items():
                if not is_data(fname):
                    continue
                if os.path.exists(os.path.join(folder_, fname)):
                    return f"{fname} is still at the old place"
                if not os.path.isfile(os.path.join(kept, fname)) or read_bytes(os.path.join(kept, fname)) != data:
                    return f"pre-profiles\\{fname} is not the old {fname}"
    return ""


def check_downgrade(command, work) -> str:
    """--check on files an older ZOrbit wrote beside a profile: it exits 0 and sets nothing aside."""
    roaming, local = os.path.join(work, "Roaming"), os.path.join(work, "Local")
    shutil.copytree(os.path.join(FIXTURES, "downgrade", "Roaming"), roaming)
    shutil.copytree(os.path.join(FIXTURES, "downgrade", "Local"), local)

    def state():
        return {top: {os.path.relpath(os.path.join(here, n), top): read_bytes(os.path.join(here, n))
                      for here, _, names in os.walk(top) for n in names} for top in (roaming, local)}

    stray = [os.path.join(roaming, "ZOrbit", "radial.json"), os.path.join(roaming, "ZOrbit", "tags.json"),
             os.path.join(local, "ZOrbit", "usage.json")]
    if not all(os.path.isfile(p) for p in stray):
        return "the downgrade fixture has no stray files"
    before = state()
    why = run_check(command, roaming, local)
    if why:
        return why
    after = state()
    for top in (roaming, local):
        # --check may write a log or a stamp of its own; the data files must be as they were
        moved = sorted(p for p, data in before[top].items()
                       if is_data(os.path.basename(p)) and after[top].get(p) != data)
        if moved:
            return "--check changed " + ", ".join(moved)
        new = sorted(p for p in after[top] if p not in before[top] and "pre-profiles" in p)
        if new:
            return "--check set files aside: " + ", ".join(new)
    return ""


def main(argv) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if "--python" in argv:
        command = [sys.executable, os.path.join(REPO, "zorbit", "main.py")]
    elif len(args) == 1:
        command = [os.path.abspath(args[0])]
        if not os.path.isfile(command[0]):
            print(f"{command[0]} does not exist")
            return 2
    else:
        print(__doc__.split("\n\n")[0])
        return 2
    names = sorted(d for d in os.listdir(FIXTURES) if os.path.isdir(os.path.join(FIXTURES, d)))
    if len(names) < 2 or "downgrade" not in names:
        print(f"{FIXTURES} holds no fixtures; run tools/make_upgrade_fixtures.py")
        return 2
    failed = 0
    for name in names:
        work = tempfile.mkdtemp(prefix="zorbit-upgrade-")
        try:
            why = check_downgrade(command, work) if name == "downgrade" else check_release(name, command, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
        print(f"{'ok  ' if not why else 'FAIL'} {name}" + (f": {why}" if why else ""))
        failed += bool(why)
    print(f"{len(names) - failed} of {len(names)} upgrades are as they should be")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
