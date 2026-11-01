"""Makes tests/fixtures/upgrade/: the files a real older ZOrbit leaves on disk, for tests/test_upgrade.py and
tools/upgrade_check.py to upgrade.

Run by hand, not by CI (the fixtures are committed, and the tags it reads are not in a shallow clone):

    python tools/make_upgrade_fixtures.py            # every release in RELEASES, then the downgrade fixture
    python tools/make_upgrade_fixtures.py v0.9.0     # only these (the downgrade fixture needs v0.12.0)

For each tag it takes the code out of git, runs that version's own modules in a subprocess against empty
%APPDATA% and %LOCALAPPDATA% folders (no pywebview, no window: only Studio's Api, tags.TagStore and usage.Usage), and
copies the data files it wrote into tests/fixtures/upgrade/<tag>/Roaming|Local/<folder>/. launch.json, logs and
caches are left out. The files are kept as that version wrote them, so do not reformat them.

Every fixture holds: the starter radial.json with its first menu retitled "Upgrade test menu" (saved the way Studio
saves, so radial.json.bak is there too), studio.json, and, for versions that have them, tags.json with one new tag
"Upgrade tag" on ClayBuildup, usage.json with one pick of ClayBuildup, and popout.json.

The downgrade fixture is the v0.12.0 one after the CURRENT code's profiles.ensure() moved it into profiles\\, and
then 0.12.0 started again: it wrote a starter radial.json at the old place, and its Studio, tag store and usage
saved the "Downgrade edit" menu title, a "Downgrade tag" and one pick of Move there. profiles.strays() finds them.
Make it again when the layout of profiles\\ changes (the fixture is a snapshot of what that build wrote).

To add a fixture for a new release: add the tag to RELEASES (folder, popout.json content or None, whether Studio
writes studio.json), run this script with the tag, and add nothing else: test_upgrade.py and upgrade_check.py pick
up every folder in tests/fixtures/upgrade. Check the files for anything personal before committing.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "tests", "fixtures", "upgrade")

# tag -> (the folder name in %APPDATA% and %LOCALAPPDATA%, what that version's popout writes to popout.json or None).
# v0.7.0 is still "Radial Menu": package radial_menu/, folders RadialMenu. It and v0.7.1 have no tags, no popout.
# v0.9.0 is the first with tags and the popout. Its Studio has no setup_done key, which later Studios decide from
# the keys it does have; that is kept. 0.12.0 also writes setup_done (set_pref asks get_prefs, which adds it).
RELEASES = {
    "v0.7.0": ("RadialMenu", None),
    "v0.7.1": ("ZOrbit", None),
    "v0.9.0": ("ZOrbit", {"size": 120, "on_top": True}),
    "v0.12.0": ("ZOrbit", {"size": 120, "side": "left", "kind": "brush", "on_top": True}),
}
LATEST = "v0.12.0"
PACKAGES = ("zorbit", "radial_menu")
# What goes into a fixture. Everything else an app writes (launch.json, logs, thumbnails, studio.log ...) stays out.
DATA = re.compile(r"(radial|tags|usage)\.json(\.bak|\.broken|\.bad)?|studio\.json|popout\.json|profile\.json"
                  r"|format\.json|leftovers\.json")

# Runs inside the old version's package folder (cwd and PYTHONPATH), so `import paths` is its paths.py. argv[1] is a
# JSON object: title, tag, brush, pick, prefs (set the two Studio preferences), popout (popout.json content or null).
# The old Studio module imports without a window (pywebview is only imported when a window opens), and importing it
# makes the starter radial.json the way a first start does.
DRIVER = '''
import json, os, sys
args = json.loads(sys.argv[1])
import paths
import studio
api = studio.Api()
made = []

with open(paths.ensure_config(), encoding="utf-8-sig") as f:
    cfg = json.load(f)
next(iter(cfg["menus"].values()))["title"] = args["title"]
res = api.save_config(cfg)                          # keeps the starter as radial.json.bak, as every Studio save does
assert res.get("saved"), res
made.append("radial.json: first menu is now " + repr(args["title"]))

if args["prefs"]:
    api.set_pref("last_screen", "menus")
    api.set_pref("check_updates", False)
    made.append("studio.json: " + json.dumps(api.get_prefs(), sort_keys=True))

try:
    import tags
except ImportError:
    tags = None                                     # before 0.9
if tags:
    store = tags.TagStore().load()
    key = store.create_tag(args["tag"])["key"]
    assert store.set_tags(tags.item_key("brush", args["brush"]), [key])["ok"]
    made.append("tags.json: " + repr(args["tag"]) + " (" + key + ") on " + args["brush"])

import usage
u = usage.Usage().load()
u.record(args["pick"])
if hasattr(u, "record_pick"):                       # the recent picks list came with 0.11
    u.record_pick("brush", args["pick"])
u.save()
made.append("usage.json: a pick of " + args["pick"])

if args["popout"] is not None:
    # the popout only writes this file from its window, so it is written here the way it does (indent=2)
    with open(paths.POPOUT_FILE, "w", encoding="utf-8") as f:
        json.dump(args["popout"], f, indent=2)
    made.append("popout.json: " + json.dumps(args["popout"]))
print("\\n".join(made))
'''


def clean_env(**extra) -> dict:
    """The environment with no ZORBIT_* and no PYTHON* variable, so nothing of this machine leaks in."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith(("ZORBIT_", "PYTHON"))}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    env.update(extra)
    return env


def run(cmd, **kw) -> str:
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", **kw)
    if done.returncode != 0:
        sys.exit(f"failed: {cmd}\n{done.stdout}\n{done.stderr}")
    return done.stdout


def export(tag, dest) -> str:
    """The code of a tag, taken out of git into dest. Returns the package folder."""
    listing = subprocess.run(["git", "ls-tree", "--name-only", tag], cwd=REPO, capture_output=True, text=True)
    if listing.returncode != 0:
        sys.exit(f"{tag} is not a tag in this checkout: {listing.stderr.strip()}")
    pkg = next((p for p in PACKAGES if p in listing.stdout.split()), None)
    if pkg is None:
        sys.exit(f"{tag} has none of {PACKAGES}")
    tar = subprocess.run(["git", "archive", "--format=tar", tag, pkg], cwd=REPO, capture_output=True, check=True)
    with tarfile.open(fileobj=io.BytesIO(tar.stdout)) as t:
        t.extractall(dest, filter="data")
    return os.path.join(dest, pkg)


def drive(pkg, roaming, local, **args) -> None:
    """Runs DRIVER with that version's modules against these folders."""
    base = dict(title="Upgrade test menu", tag="Upgrade tag", brush="ClayBuildup", pick="ClayBuildup",
                prefs=True, popout=None)
    base.update(args)
    with tempfile.TemporaryDirectory() as tmp:
        script = os.path.join(tmp, "driver.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(DRIVER)
        env = clean_env(APPDATA=roaming, LOCALAPPDATA=local, PYTHONPATH=pkg)
        print(run([sys.executable, script, json.dumps(base)], cwd=pkg, env=env).rstrip())


def ensure_with_current_code(roaming, local) -> None:
    """The first start of this checkout on these folders, in its own process."""
    env = clean_env(APPDATA=roaming, LOCALAPPDATA=local, PYTHONPATH=os.path.join(REPO, "zorbit"))
    run([sys.executable, "-c", "import profiles; profiles.ensure()"], cwd=roaming, env=env)


def copy_data(roaming, local, dest) -> list:
    """Copies the data files of the two app folders into dest\\Roaming and dest\\Local, keeping the folder names and
    the folders inside (profiles\\, pre-profiles\\). Returns the relative paths."""
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    found = []
    for label, top in (("Roaming", roaming), ("Local", local)):
        for here, _, names in os.walk(top):
            for name in sorted(names):
                if DATA.fullmatch(name):
                    rel = os.path.relpath(os.path.join(here, name), top)
                    target = os.path.join(dest, label, rel)
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    shutil.copyfile(os.path.join(here, name), target)
                    found.append(os.path.join(label, rel))
    return sorted(found)


def check_private(dest) -> None:
    """The pre-commit hook refuses a Windows user folder in a text file; so does this, before anything is committed."""
    bad = re.compile(rb"[Cc]:\\\\?[Uu]sers\\\\?(?!you\b)[A-Za-z0-9_-]+")
    for here, _, names in os.walk(dest):
        for name in names:
            with open(os.path.join(here, name), "rb") as f:
                hit = bad.search(f.read())
            if hit:
                sys.exit(f"{os.path.join(here, name)} holds a personal path: {hit.group().decode()}")


def make_release(tag, work) -> str:
    """Makes one release's fixture. Returns the scratch folder holding the app folders as the release left them."""
    folder, popout = RELEASES[tag]
    pkg = export(tag, os.path.join(work, "code-" + tag))
    scratch = os.path.join(work, "data-" + tag)
    roaming, local = os.path.join(scratch, "Roaming"), os.path.join(scratch, "Local")
    os.makedirs(roaming)
    os.makedirs(local)
    print(f"\n== {tag}  ({os.path.basename(pkg)}, folders {folder})")
    drive(pkg, roaming, local, popout=popout)
    for top in (roaming, local):
        if not os.path.isdir(os.path.join(top, folder)):
            sys.exit(f"{tag} did not write to a {folder} folder under {top}")
    found = copy_data(roaming, local, os.path.join(OUT, tag))
    print("\n".join("  " + p for p in found))
    return scratch


def make_downgrade(work, scratch) -> None:
    """The v0.12.0 files, moved by this checkout's ensure(), then touched again by 0.12.0."""
    folder, _ = RELEASES[LATEST]
    pkg = os.path.join(work, "code-" + LATEST, "zorbit")
    roaming, local = os.path.join(work, "down", "Roaming"), os.path.join(work, "down", "Local")
    shutil.copytree(os.path.join(scratch, "Roaming"), roaming)
    shutil.copytree(os.path.join(scratch, "Local"), local)
    print(f"\n== downgrade  ({LATEST} files, moved by this checkout, then {LATEST} again)")
    ensure_with_current_code(roaming, local)
    # 0.12.0 finds no radial.json at the old place and makes a starter there; its Studio and the tag store and usage
    # file do the same. studio.json is already moved or kept where it is: a downgrade changes nothing there.
    drive(pkg, roaming, local, title="Downgrade edit", tag="Downgrade tag", pick="Move", prefs=False)
    found = copy_data(roaming, local, os.path.join(OUT, "downgrade"))
    print("\n".join("  " + p for p in found))


def main(argv) -> int:
    tags = argv or list(RELEASES)
    unknown = [t for t in tags if t not in RELEASES]
    if unknown:
        sys.exit(f"unknown tag {unknown}; the releases are {list(RELEASES)}")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, ".gitattributes"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# Kept byte for byte as the old versions wrote them: no line ending conversion.\n* -text\n")
    work = tempfile.mkdtemp(prefix="zorbit-fixtures-")
    try:
        scratches = {t: make_release(t, work) for t in tags}
        if LATEST in scratches:
            make_downgrade(work, scratches[LATEST])
        check_private(OUT)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(f"\nWritten to {os.path.relpath(OUT, REPO)}. Nothing is committed.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
