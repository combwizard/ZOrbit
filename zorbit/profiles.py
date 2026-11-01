"""Profiles: named sets of menus, tags and usage, one active at a time.

  %APPDATA%\\ZOrbit\\profile.json            {"active": "Default"}, the pointer every process reads fresh
  %APPDATA%\\ZOrbit\\profiles\\<name>\\        radial.json (.bak, .broken), tags.json (.bak), usage.json (.bad)
  %APPDATA%\\ZOrbit\\profiles\\.staging-*\\    a profile being built; renamed into place once it is complete
  %APPDATA%\\ZOrbit\\profiles\\.deleted\\      a deleted profile as <name>-<stamp>, purged after 30 days
  %APPDATA%\\ZOrbit\\profiles\\format.json    {"format": 1, "version": "0.12.0"}, the newest build that wrote here
  %APPDATA%\\ZOrbit\\profiles\\leftovers.json root files the first run could not move away, with their size and time
  %APPDATA%\\ZOrbit\\pre-profiles\\           the root files as they were before the first run of this version
  %APPDATA%\\ZOrbit\\pre-profiles\\<stamp>\\   files an older ZOrbit wrote at the old places afterwards, set aside
  studio.json, popout.json and launch.json stay in %APPDATA%\\ZOrbit: they belong to the PC, not to a profile.

A profile is a folder holding radial.json; any other folder under profiles\\ (a name starting with a dot, a folder
without radial.json) is not one. The pointer says which is active. A missing, unreadable or dangling pointer is not an
error: active() falls back to Default, then to the first profile, and never writes. Only ensure() repairs the pointer.

Every change (set_active, create, rename, delete, the first-run migration) runs under the named mutex
Local\\ZOrbitProfiles, so the Studio, the popout and the ring app starting together cannot trip over each other.
A profile is built in a staging folder and moved into place with one rename, so another process sees all of it or
none of it. Names are checked by valid_name(): they must work as a Windows folder name and read well in a menu.

While the environment variable ZORBIT_CONFIG_FILE pins one menus file, profiles are off: names() is just Default,
config_file() is that file, and the changing functions refuse. ZORBIT_TAGS_FILE and ZORBIT_USAGE_FILE pin their file
and leave profiles on. The three exist for tests and --check.

format.json is a stamp kept apart from profile.json (repairing an unreadable pointer overwrites it, and must never
erase the stamp). When it says a newer format than FORMAT, too_new() gives the message to show, ensure() touches
nothing and the changing functions refuse.

An older ZOrbit (0.12.0) still writes radial.json, tags.json and usage.json at the old root places. strays() finds
those files after the move, set_aside() puts them away and create(name, "strays") or absorb_stray_usage() make use
of them. leftovers.json lists the root files the first run could not move, so they are not taken for strays.

CONFIG_DIR and DATA_DIR are read from paths on every call, so a test can point them at a throw-away folder.
"""
import hashlib
import json
import os
import re
import shutil
import time
import unicodedata

import fsutil
import paths

DEFAULT = "Default"
NAME_MAX = 60
MUTEX_NAME = "Local\\ZOrbitProfiles"
MUTEX_WAIT_MS = 15000
DELETED_KEEP_S = 30 * 86400
STAGING_STALE_S = 3600
SOURCES = ("starter", "empty", "copy", "file", "strays")
FORMAT = 1                             # the layout of the profile folders; a build refuses a higher one
STRAY_MAX_BYTES = 16 << 20             # a root file bigger than this is not read, so it is not reported
# What an older ZOrbit writes at the old root places: kind -> (folder, file name). The siblings (.bak, .broken, .bad)
# and the <name>.<pid>.tmp of an interrupted write are never strays themselves, they go with their file.
STRAY_FILES = {"menus": ("config", "radial.json"), "tags": ("config", "tags.json"), "usage": ("data", "usage.json")}
SIBLINGS = (".bak", ".broken", ".bad")
# The canonical_hash() of every default_menus.json that ever shipped (git history up to 0.12.0). A root radial.json
# that hashes to one of these, or to the current file, is an untouched copy of a starter and not worth keeping.
# Made with: for every commit in `git log -- radial_menu/default_menus.json zorbit/default_menus.json`, take the file
# as it was there and run canonical_hash() on its JSON. tests/test_starters.py recomputes them and fails when one is
# missing, so add the new hash here whenever default_menus.json changes.
KNOWN_STARTERS = frozenset((
    "38745f4486313ec0f3d3600139a1bcf52cdc21de39a15317fa7061f544a7933c",
    "f2eed8ed3b164c69182472fae9482c2c996ad1d3667148b7f935b65d5866e918",
    "350804531dad1c84cf9579aa57210b51833f0879cc571f646fcc506b64c3c1be",
    "6b607e6938831e0173f3f9aaf90b62209e7379627d4a904b826d388317657d71",
    "8bf59cff465ff2f863bab477cb141f1500d09fe427797a2bdc25be126d3a4c81",
))

_FORBIDDEN = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_cache = None                          # ((root, pointer signature), active name); only for a pointer that was good
_staging_seq = 0                       # the counter in .staging-<pid>-<n>; only changed while holding the mutex
_stamp_cache = None                    # ((stamp path, mtime_ns, size, index), too_new message) of the stamp as last read
_starter_cache = None                  # ((path, mtime_ns, size), canonical hash) of the shipped default_menus.json


class ProfileError(Exception):
    """A message for the user."""


# --- where things are ---------------------------------------------------------------------------------


def root() -> str:
    return os.path.join(paths.CONFIG_DIR, "profiles")


def pointer_file() -> str:
    return os.path.join(paths.CONFIG_DIR, "profile.json")


def stamp_file() -> str:
    return os.path.join(root(), "format.json")


def leftovers_file() -> str:
    return os.path.join(root(), "leftovers.json")


def enabled() -> bool:
    """False when ZORBIT_CONFIG_FILE pins one menus file: there is then nothing to switch between."""
    return not os.environ.get("ZORBIT_CONFIG_FILE")


def profile_dir(name=None) -> str:
    return os.path.join(root(), name if name is not None else active())


def config_file(name=None) -> str:
    """radial.json of a profile (the active one when name is None; ZORBIT_CONFIG_FILE wins then)."""
    if name is None and os.environ.get("ZORBIT_CONFIG_FILE"):
        return os.environ["ZORBIT_CONFIG_FILE"]
    return os.path.join(profile_dir(name), "radial.json")


def tags_file(name=None) -> str:
    if name is None and os.environ.get("ZORBIT_TAGS_FILE"):
        return os.environ["ZORBIT_TAGS_FILE"]
    return os.path.join(profile_dir(name), "tags.json")


def usage_file(name=None) -> str:
    if name is None and os.environ.get("ZORBIT_USAGE_FILE"):
        return os.environ["ZORBIT_USAGE_FILE"]
    return os.path.join(profile_dir(name), "usage.json")


# --- names --------------------------------------------------------------------------------------------


def _clean(name) -> str:
    """The name as it will be written: trimmed and in one Unicode form, so 'é' typed two ways is one name."""
    return unicodedata.normalize("NFC", name.strip()) if isinstance(name, str) else ""


def _fold(name) -> str:
    """The form names are compared in: one Unicode form, ignoring case."""
    return unicodedata.normalize("NFC", name).casefold()


def valid_name(name, existing=None) -> str:
    """"" when name can be a new profile's name, else why not. existing: the names already taken (default
    names()); a name equal to one of them, ignoring case, is refused."""
    name = _clean(name)
    if not name:
        return "Give the profile a name."
    if len(name) > NAME_MAX:
        return f"Keep the name under {NAME_MAX} characters."
    if _FORBIDDEN.search(name):
        return 'A name cannot contain \\ / : * ? " < > |'
    if name.startswith("."):
        return "A name cannot start with a dot."
    if name.endswith((".", " ")):
        return "A name cannot end with a dot or a space."
    if name.split(".", 1)[0].upper() in _RESERVED:
        return "That name is reserved by Windows."
    taken = {_fold(n) for n in (names() if existing is None else existing)}
    if _fold(name) in taken:
        return f"There is already a profile called {name}."
    return ""


def names() -> list:
    """The profiles, sorted ignoring case."""
    if not enabled():
        return [DEFAULT]
    r = root()
    try:
        entries = os.listdir(r)
    except OSError:
        return []
    found = [n for n in entries if not n.startswith(".") and os.path.isfile(os.path.join(r, n, "radial.json"))]
    return sorted(found, key=str.casefold)


def canonical(name):
    """The spelling a profile has on disk (name matched ignoring case), or None when there is no such profile or
    name is not a plain name."""
    if not isinstance(name, str) or valid_name(name, ()):
        return None
    key = _fold(_clean(name))
    return next((n for n in names() if _fold(n) == key), None)


def exists(name) -> bool:
    return canonical(name) is not None


def unique_name(base) -> str:
    """base when no profile has it, else 'base 2', 'base 3' ... (as many characters of base as fit)."""
    taken = {_fold(n) for n in names()}
    base = _clean(base)
    if _fold(base) not in taken:
        return base
    n = 2
    while True:
        suffix = f" {n}"
        cand = base[:NAME_MAX - len(suffix)].rstrip() + suffix
        if _fold(cand) not in taken:
            return cand
        n += 1


# --- the pointer --------------------------------------------------------------------------------------


def signature():
    """(mtime, size, file index) of profile.json, or None when there is none: changes whenever the pointer is
    written. The index is there because two writes in one clock tick can leave the same time and size, and every
    write_atomic() makes a new file."""
    try:
        st = os.stat(pointer_file())
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def pointer():
    """The active name as profile.json says it, or None when the file is missing, unreadable or has no string."""
    data = fsutil.read_json_for_update(pointer_file())
    value = data.get("active") if data else None
    return value if isinstance(value, str) else None


def _forget() -> None:
    """Drops the remembered active name and stamp (tests that swap the folders under it)."""
    global _cache, _stamp_cache, _starter_cache
    _cache = _stamp_cache = _starter_cache = None


def too_new() -> str:
    """"" normally. When format.json says a newer format than this build knows, the message to show: nothing is
    written then, and ensure() leaves the files alone. A missing or unreadable stamp is not too new. Remembered
    until the stamp changes."""
    global _stamp_cache
    if not enabled():
        return ""
    path = stamp_file()
    try:
        st = os.stat(path)
    except OSError:
        return ""
    key = (path, st.st_mtime_ns, st.st_size, st.st_ino)     # the index: two writes in one tick
    if _stamp_cache and _stamp_cache[0] == key:
        return _stamp_cache[1]
    data = fsutil.read_json_for_update(path)
    if data is None:                               # held open or not JSON: look again next time
        return ""
    fmt, version, msg = data.get("format"), data.get("version"), ""
    if isinstance(fmt, int) and not isinstance(fmt, bool) and fmt > FORMAT:
        if isinstance(version, str) and version.strip():
            v = version.strip()[:40]
            msg = (f"These files were made by ZOrbit {v}, which is newer than this one ({paths.VERSION}). "
                   f"Install ZOrbit {v} or newer.")
        else:
            msg = (f"These files were made by a newer ZOrbit than this one ({paths.VERSION}). "
                   "Install the newest ZOrbit.")
    _stamp_cache = (key, msg)
    return msg


def _write_stamp() -> None:
    """Writes format.json. The caller holds the mutex."""
    os.makedirs(root(), exist_ok=True)
    fsutil.write_atomic(stamp_file(), json.dumps({"format": FORMAT, "version": paths.VERSION}, indent=2))


def active() -> str:
    """The active profile: the pointer's when that profile exists, else Default, else the first one, else Default.
    Never writes; ensure() is what repairs the pointer. Remembered until profile.json changes."""
    global _cache
    if not enabled():
        return DEFAULT
    key = (root(), signature())
    if key[1] is not None and _cache and _cache[0] == key \
            and os.path.isfile(os.path.join(key[0], _cache[1], "radial.json")):
        return _cache[1]
    name = canonical(pointer())
    if name is not None:
        _cache = (key, name)
        return name
    return canonical(DEFAULT) or next(iter(names()), DEFAULT)


def _write_pointer(name) -> None:
    """Writes profile.json, keeping any other key it holds. The caller holds the mutex."""
    _need_current()
    path = pointer_file()
    data = fsutil.read_json_for_update(path)
    data = dict(data) if data else {}              # unreadable (None) is written over: the pointer is all it held
    data["active"] = name
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fsutil.write_atomic(path, json.dumps(data, indent=2))
    _forget()


class _Locked:
    """The mutex around a change. strict: raise ProfileError when it is not got in time, else go ahead anyway
    (start-up must not fail because another process is slow)."""

    def __init__(self, strict=True):
        self._strict = strict
        self._cm = None

    def __enter__(self):
        self._cm = fsutil.named_lock(MUTEX_NAME, MUTEX_WAIT_MS)
        got = self._cm.__enter__()
        if not got and self._strict:
            self._cm.__exit__(None, None, None)
            raise ProfileError("Another ZOrbit window is changing profiles. Try again in a moment.")
        return got

    def __exit__(self, *exc):
        return self._cm.__exit__(*exc)


def _need_enabled() -> None:
    if not enabled():
        raise ProfileError("Profiles are off while a menus file is pinned.")


def _need_current() -> None:
    """Refuses, before anything is written, when the files were made by a newer ZOrbit."""
    msg = too_new()
    if msg:
        raise ProfileError(msg)


def set_active(name) -> None:
    _need_enabled()
    _need_current()
    with _Locked():
        cur = canonical(name)
        if cur is None:
            raise ProfileError(f"There is no profile called {name}.")
        _write_pointer(cur)


# --- first run and housekeeping -----------------------------------------------------------------------


def _holds(name) -> bool:
    """True when name is a plain name whose folder holds radial.json (a pointer that works)."""
    return isinstance(name, str) and not valid_name(name, ()) \
        and os.path.isfile(os.path.join(root(), name, "radial.json"))


def _old(folder, seconds) -> bool:
    try:
        return time.time() - os.stat(folder).st_mtime > seconds
    except OSError:
        return False


def _purge(parent, keep_s, prefix="") -> None:
    """Removes the folders of parent that start with prefix and have not changed for keep_s seconds. Best effort."""
    try:
        entries = os.listdir(parent)
    except OSError:
        return
    for n in entries:
        p = os.path.join(parent, n)
        if n.startswith(prefix) and os.path.isdir(p) and _old(p, keep_s):
            shutil.rmtree(p, ignore_errors=True)


def _housekeeping() -> None:
    _purge(os.path.join(root(), ".deleted"), DELETED_KEEP_S)
    _purge(root(), STAGING_STALE_S, ".staging-")


def _new_staging(tag=None) -> str:
    global _staging_seq
    _staging_seq += 1
    path = os.path.join(root(), f".staging-{os.getpid()}-{tag or _staging_seq}")
    shutil.rmtree(path, ignore_errors=True)        # a leftover of an earlier process with the same pid
    os.makedirs(path)
    return path


def _rename_dir(src, dst) -> None:
    """os.rename, tried again a few times when something (a scanner, an open folder window) holds the folder."""
    for pause in (*fsutil.REPLACE_PAUSES, None):
        try:
            os.rename(src, dst)
            return
        except OSError as e:
            if pause is None or not fsutil._held(e):
                raise
            time.sleep(pause)


def _migrate() -> None:
    """Builds profiles\\Default from the root files, a Radial Menu install, or the shipped defaults. Under the mutex."""
    cfg, data = paths.CONFIG_DIR, paths.DATA_DIR
    (old_cfg, _, _), (old_data, _, _) = paths.legacy_sources()
    # (folder, Radial Menu folder to fall back to, file name)
    plan = ((cfg, old_cfg, "radial.json"), (cfg, old_cfg, "radial.json.bak"), (cfg, None, "radial.json.broken"),
            (cfg, None, "tags.json"), (cfg, None, "tags.json.bak"),
            (data, old_data, "usage.json"), (data, None, "usage.json.bad"))
    os.makedirs(root(), exist_ok=True)
    _purge(root(), STAGING_STALE_S, ".staging-")
    stage = _new_staging("ensure")
    try:
        for folder, legacy, name in plan:
            for d in (folder, legacy):
                src = os.path.join(d, name) if d else ""
                if src and os.path.isfile(src):
                    shutil.copy2(src, os.path.join(stage, name))
                    break
        if not os.path.isfile(os.path.join(stage, "radial.json")):
            with open(paths.DEFAULT_MENUS, "rb") as f:
                fsutil.write_atomic(os.path.join(stage, "radial.json"), f.read())
        dest = os.path.join(root(), DEFAULT)
        if os.path.isdir(dest) and not os.path.isfile(os.path.join(dest, "radial.json")):
            shutil.rmtree(dest)                    # a stray folder from a half-done attempt
        try:
            _rename_dir(stage, dest)
        except OSError:
            if not os.path.isfile(os.path.join(dest, "radial.json")):
                raise                              # nobody else made it either
    finally:
        shutil.rmtree(stage, ignore_errors=True)   # gone already after a rename; the loser's copy otherwise
    _write_pointer(DEFAULT)
    try:
        _write_stamp()                             # a profile that works beats a stamp: tried again later
    except OSError:
        pass
    left = _keep_originals(plan)
    if left:
        where = {name: ("config" if folder == cfg else "data") for folder, _, name in plan}
        _record_leftovers({n: where[n] for n in left})
    _carry_studio_json()


def _move_to_keep(src, name) -> bool:
    """Moves one root file into pre-profiles\\ under its own name. False when it could not be moved."""
    keep = os.path.join(paths.CONFIG_DIR, "pre-profiles")
    try:
        os.makedirs(keep, exist_ok=True)
        shutil.move(src, os.path.join(keep, name))
        return True
    except (OSError, shutil.Error):
        return False


def _keep_originals(plan) -> list:
    """Moves the root files the profile was built from into pre-profiles\\, in case the user wants them back.
    Best effort: a file another process holds stays where it is, which does no harm. Returns the names of the
    files that could not be moved."""
    left = []
    for folder, _, name in plan:
        src = os.path.join(folder, name)
        if os.path.isfile(src) and not _move_to_keep(src, name):
            left.append(name)
    return left


def _folder(kind) -> str:
    return paths.CONFIG_DIR if kind == "config" else paths.DATA_DIR


def _record_leftovers(found) -> None:
    """Writes leftovers.json for {name: "config" | "data"}: the size and time of each file as it is now, which is
    what a copy of it in the profile has too (copy2 keeps the time). Best effort."""
    out = {}
    for name, kind in found.items():
        try:
            st = os.stat(os.path.join(_folder(kind), name))
        except OSError:
            continue
        out[name] = {"folder": kind, "size": st.st_size, "mtime_ns": st.st_mtime_ns}
    if out:
        try:
            fsutil.write_atomic(leftovers_file(), json.dumps(out, indent=2))
        except OSError:
            pass


def _read_leftovers() -> dict:
    """{name: {"folder", "size", "mtime_ns"}} from leftovers.json; whatever is malformed is left out."""
    data = fsutil.read_json_for_update(leftovers_file())
    out = {}
    for name, e in (data or {}).items():
        if isinstance(e, dict) and e.get("folder") in ("config", "data") and isinstance(name, str) \
                and all(isinstance(e.get(k), int) and not isinstance(e.get(k), bool) for k in ("size", "mtime_ns")):
            out[name] = e
    return out


def _same_file(path, entry) -> bool:
    """True when the file at path still has the size and time a leftovers.json entry recorded."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    return st.st_size == entry["size"] and st.st_mtime_ns == entry["mtime_ns"]


def tidy_leftovers() -> None:
    """Tries again to move the files leftovers.json lists into pre-profiles\\, and forgets the entries whose file
    has gone, been moved or changed since. Best effort: it never raises OSError."""
    try:
        if not enabled() or too_new() or not os.path.isfile(leftovers_file()):
            return
        with _Locked(strict=False):
            entries = _read_leftovers()
            keep = {}
            for name, e in entries.items():
                src = os.path.join(_folder(e["folder"]), name)
                if _same_file(src, e) and not _move_to_keep(src, name):
                    keep[name] = e
            if keep == entries:
                return
            if keep:
                fsutil.write_atomic(leftovers_file(), json.dumps(keep, indent=2))
            else:
                os.remove(leftovers_file())
    except OSError:
        pass


def _carry_studio_json() -> None:
    """studio.json is per PC and stays at the root, but a Radial Menu one is worth carrying over."""
    (old_cfg, _, _), _ = paths.legacy_sources()
    old, new = os.path.join(old_cfg, "studio.json"), os.path.join(paths.CONFIG_DIR, "studio.json")
    try:
        if os.path.isfile(old) and not os.path.exists(new):
            shutil.copy2(old, new)
    except OSError:
        pass


def ensure() -> str:
    """The active profile's radial.json, making the first profile when there is none yet. OSError is not caught:
    the caller decides what a start without menus means. When the files were made by a newer ZOrbit (too_new())
    nothing is written or migrated; the path is returned as it is, and the caller shows the message."""
    if not enabled() or too_new():
        return config_file()
    if _holds(pointer()):                          # the usual start: nothing is written, no mutex taken
        _housekeeping()
        if not os.path.isfile(stamp_file()):       # profiles from before the stamp: put it there, once
            with _Locked(strict=False):
                if not os.path.isfile(stamp_file()):
                    try:
                        _write_stamp()
                    except OSError:
                        pass
        return config_file()
    with _Locked(strict=False):
        if _holds(pointer()):                      # the other process finished first
            return config_file()
        if names():                                # profiles exist but the pointer is lost: point at one
            _write_pointer(active())
            if not os.path.isfile(stamp_file()):
                _write_stamp()
            return config_file()
        _migrate()
    return config_file()


# --- files an older ZOrbit writes at the old places ---------------------------------------------------


def canonical_hash(obj) -> str:
    """SHA-256 (hex) of a radial.json dict without its bridge and browser sections, as compact JSON with sorted keys:
    the same for the same menus whatever the indentation, line endings or key order of the file."""
    body = {k: v for k, v in obj.items() if k not in ("bridge", "browser")}
    text = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _starter_hashes() -> frozenset:
    """KNOWN_STARTERS and the hash of the default_menus.json this build ships."""
    global _starter_cache
    try:
        st = os.stat(paths.DEFAULT_MENUS)
        key = (paths.DEFAULT_MENUS, st.st_mtime_ns, st.st_size)
        if not _starter_cache or _starter_cache[0] != key:
            _starter_cache = (key, canonical_hash(_read_object(paths.DEFAULT_MENUS) or {}))
        return KNOWN_STARTERS | {_starter_cache[1]}
    except OSError:
        return KNOWN_STARTERS


def _read_object(path):
    """The JSON object in a small file, or None when it is missing, too big, unreadable or not an object."""
    try:
        if os.path.getsize(path) > STRAY_MAX_BYTES:
            return None
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _same_bytes(a, b) -> bool:
    try:
        if os.path.getsize(a) != os.path.getsize(b) or os.path.getsize(a) > STRAY_MAX_BYTES:
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            return fa.read() == fb.read()
    except OSError:
        return False


def _only_starter_tags(raw) -> bool:
    """True for a tags.json that holds the three starter tags as shipped and nothing tagged."""
    import tags                                    # here, not at the top: tags imports this module
    found, items, _ = tags._parse(raw)
    got = [(k, t["label"], t["color"]) for k, t in tags._with_favourite(found).items()]
    return got == [(k, label, color.upper()) for k, label, color in tags.STARTERS] and not items


def strays() -> dict:
    """The files an older ZOrbit wrote at the old root places after the move into profiles\\:
    {"menus": path or None, "tags": ..., "usage": ..., "when": newest modification time or None}. Only reads.
    Nothing is reported when profiles are off, before the first profile exists (the root files are the data then),
    or when the files are too new. A root file is not a stray when it is a leftover the first run could not move,
    is the Radial Menu file 0.12.0 copies back on every start, is an untouched starter (radial.json, tags.json), or
    does not parse as a JSON object."""
    out = {"menus": None, "tags": None, "usage": None, "when": None}
    if not enabled() or too_new() or not names():
        return out
    left = _read_leftovers()
    (old_cfg, _, _), (old_data, _, _) = paths.legacy_sources()
    old = {"config": old_cfg, "data": old_data}
    for kind, (folder, name) in STRAY_FILES.items():
        path = os.path.join(_folder(folder), name)
        try:
            st = os.stat(path)
        except OSError:
            continue
        if name in left and left[name]["folder"] == folder and _same_file(path, left[name]):
            continue
        if kind != "tags" and _same_bytes(path, os.path.join(old[folder], name)):
            continue
        raw = _read_object(path)
        if raw is None:
            continue
        try:
            if kind == "menus" and canonical_hash(raw) in _starter_hashes():
                continue
            if kind == "tags" and _only_starter_tags(raw):
                continue
        except (ValueError, TypeError, AttributeError, RecursionError):
            continue
        out[kind] = path
        out["when"] = max(out["when"] or 0.0, st.st_mtime)
    return out


def set_aside(files) -> "str | None":
    """Moves each file, and its .bak, .broken and .bad beside it, into pre-profiles\\<YYYYMMDD-HHMMSS>\\ (with -2,
    -3 ... added when that folder exists). Returns the folder, or None when nothing was moved. Never deletes: a file
    that cannot be moved stays where it is."""
    with _Locked(strict=False):
        base = os.path.join(paths.CONFIG_DIR, "pre-profiles", time.strftime("%Y%m%d-%H%M%S"))
        dest, n = base, 1
        while os.path.exists(dest):
            n += 1
            dest = f"{base}-{n}"
        moved = False
        for path in files:
            for src in (path, *(path + s for s in SIBLINGS)):
                if not os.path.isfile(src):
                    continue
                try:
                    os.makedirs(dest, exist_ok=True)
                    shutil.move(src, os.path.join(dest, os.path.basename(src)))
                    moved = True
                except (OSError, shutil.Error):
                    pass
        if not moved:
            try:
                os.rmdir(dest)                     # made for a move that then failed
            except OSError:
                pass
        return dest if moved else None


def absorb_stray_usage(now=None) -> int:
    """Adds the usage.json an older ZOrbit wrote at the old place to the active profile's usage and sets the file
    aside. It is moved first, so a crash loses the merge but never counts it twice. Returns how many brushes were
    added or updated (0 when there was nothing). Never raises OSError."""
    try:
        with _Locked(strict=False):
            path = strays()["usage"]
            folder = set_aside([path]) if path else None
            if not folder:
                return 0
            raw = fsutil.read_json_for_update(os.path.join(folder, os.path.basename(path)))
            if not raw:
                return 0
            import usage                           # here, not at the top: usage imports this module
            mine = usage.Usage(usage_file()).load()
            taken = mine.absorb(raw, now)
            mine.save()
            return taken
    except OSError:
        return 0


# --- building a profile -------------------------------------------------------------------------------


def _sections(raw) -> dict:
    """The bridge and browser sections of a raw radial.json that are objects: they belong to this PC, so every new
    profile takes them from the active one."""
    return {k: raw[k] for k in ("bridge", "browser") if isinstance(raw, dict) and isinstance(raw.get(k), dict)}


def _first_hotkey(raw) -> str:
    menus = raw.get("menus") if isinstance(raw, dict) else None
    for m in (menus.values() if isinstance(menus, dict) else ()):
        hk = m.get("hotkey") if isinstance(m, dict) else None
        if isinstance(hk, str) and hk.strip():
            return hk
    return "Q"


def _dump(path, obj, indent) -> None:
    fsutil.write_atomic(path, json.dumps(obj, indent=indent, ensure_ascii=False) + "\n")


def _build(stage, source, bundle) -> list:
    """Fills the staging folder for one of the sources of create(). Returns the root files it took from, which
    create() sets aside once the profile is in place (only "strays" has any)."""
    here = active()
    raw = fsutil.read_json_for_update(config_file(here)) or {}      # unreadable or missing: no sections to take
    mine = _sections(raw)
    out = os.path.join(stage, "radial.json")
    if source == "starter":
        with open(paths.DEFAULT_MENUS, encoding="utf-8-sig") as f:
            cfg = json.load(f)
        cfg.update(mine)
        _dump(out, cfg, 2)
    elif source == "empty":
        cfg = dict(mine)
        if isinstance(raw.get("ring"), dict):
            cfg["ring"] = raw["ring"]
        cfg["menus"] = {"main": {"title": "Main", "hotkey": _first_hotkey(raw), "items": []}}
        _dump(out, cfg, 2)
    elif source == "copy":
        for name, src in (("radial.json", config_file(here)), ("tags.json", tags_file(here)),
                          ("usage.json", usage_file(here))):
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(stage, name))
    elif source == "file":
        imported = bundle.get("config") if isinstance(bundle, dict) else None
        if not isinstance(imported, dict):
            raise ProfileError("That is not a menus file.")
        cfg = {k: v for k, v in imported.items() if k not in ("bridge", "browser")}   # from another PC
        cfg.update(mine)
        _dump(out, cfg, 2)
        tags = bundle.get("tags")
        if isinstance(tags, dict):
            _dump(os.path.join(stage, "tags.json"), tags, 1)
    elif source == "strays":
        found = strays()
        if not (found["menus"] or found["tags"]):
            raise ProfileError("There are no files from an older version to bring in.")
        if found["menus"]:
            old_cfg = _read_object(found["menus"])
            if old_cfg is None:
                raise ProfileError("That is not a menus file.")
            cfg = {k: v for k, v in old_cfg.items() if k not in ("bridge", "browser")}
        else:
            with open(paths.DEFAULT_MENUS, encoding="utf-8-sig") as f:
                cfg = json.load(f)
        cfg.update(mine)
        _dump(out, cfg, 2)
        if found["tags"]:
            shutil.copy2(found["tags"], os.path.join(stage, "tags.json"))
        return [p for p in (found["menus"], found["tags"]) if p]
    else:
        raise ProfileError(f"Unknown way to make a profile: {source}.")
    return []


def create(name, source, bundle=None) -> str:
    """Makes a profile and returns its name. source: "starter" (the shipped menus), "empty" (one empty menu, the ring
    settings of the active profile), "copy" (the active profile's menus, tags and usage) or "file" (bundle is
    {"config": dict, "tags": dict or None}, read from a menus file) or "strays" (the radial.json and tags.json an
    older ZOrbit wrote at the old root places, see strays(); the shipped menus when only tags.json is there; the
    files are set aside once the profile exists). Every source takes bridge and browser from the active profile."""
    _need_enabled()
    _need_current()
    name = _clean(name)
    with _Locked():
        msg = valid_name(name)
        if msg:
            raise ProfileError(msg)
        os.makedirs(root(), exist_ok=True)
        stage = _new_staging()
        try:
            used = _build(stage, source, bundle)
            import config                          # here, not at the top: this module stays free of the menu code
            try:
                config.load(os.path.join(stage, "radial.json"))
            except Exception as e:
                raise ProfileError(f"The menus could not be read: {e}") from e
            dest = os.path.join(root(), name)
            if os.path.isdir(dest) and not os.path.isfile(os.path.join(dest, "radial.json")):
                shutil.rmtree(dest, ignore_errors=True)    # a stray folder with no menus in it
            _rename_dir(stage, dest)
        except ProfileError:
            shutil.rmtree(stage, ignore_errors=True)
            raise
        except Exception as e:
            shutil.rmtree(stage, ignore_errors=True)
            raise ProfileError(f"The profile could not be made: {e}") from e
        if used:
            set_aside(used)
        return name


def rename(old, new) -> str:
    """Renames a profile and returns the new name. The pointer is moved first when it is the active one, so no
    reader is left pointing at a folder that has gone."""
    _need_enabled()
    _need_current()
    with _Locked():
        cur = canonical(old)
        if cur is None:
            raise ProfileError(f"There is no profile called {old}.")
        new = _clean(new)
        if new == cur:
            return cur
        msg = valid_name(new, [n for n in names() if n != cur])    # so only the case can change
        if msg:
            raise ProfileError(msg)
        was_active = active() == cur
        if was_active:
            _write_pointer(new)
        try:
            _rename_dir(os.path.join(root(), cur), os.path.join(root(), new))
        except OSError as e:
            if was_active:
                _write_pointer(cur)
            raise ProfileError("The folder could not be renamed. Close any folder window showing this profile "
                               "and try again.") from e
        return new


def delete(name) -> str:
    """Moves a profile to profiles\\.deleted\\ (purged after 30 days) and returns the active profile, which is a
    different one when the active profile was deleted."""
    _need_enabled()
    _need_current()
    with _Locked():
        cur = canonical(name)
        if cur is None:
            raise ProfileError(f"There is no profile called {name}.")
        others = [n for n in names() if n != cur]
        if not others:
            raise ProfileError("The last profile cannot be deleted.")
        was_active = active() == cur
        if was_active:
            _write_pointer(next((n for n in others if n.casefold() == DEFAULT.casefold()), others[0]))
        grave = os.path.join(root(), ".deleted")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(grave, f"{cur}-{stamp}")
        n = 1
        while os.path.exists(dest):                # deleted and made again within one second
            n += 1
            dest = os.path.join(grave, f"{cur}-{stamp}-{n}")
        try:
            os.makedirs(grave, exist_ok=True)
            _rename_dir(os.path.join(root(), cur), dest)
        except OSError as e:
            if was_active:
                _write_pointer(cur)
            raise ProfileError("The folder could not be removed. Close any folder window showing this profile "
                               "and try again.") from e
        try:
            os.utime(dest)                         # the 30 days count from now, not from the last edit
        except OSError:
            pass
        return active()
