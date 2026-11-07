"""The Recent item, {"recent": "project" | "tool" | "any"}: a fan of the projects and tools ZBrush opened last, read
from ZBrush's own Lightbox list. expand.py turns the slot into a fan of Project and Tool items, so a pick goes through
fileitem.py like any other.

ZBrush keeps the list in ZStartup\\ConfigFiles\\LightboxRecentFiles.cfg: in the user assets folder for ZBrush 2026 and
newer (the folder its userassets_path.txt names, as for the library), and in <Public Documents>\\ZBrushData<year> for
2022 to 2025. The ZBrush is the one in front when the caller knows it, else the one the library follows
(brushes.zbrush_dirs: the newest running, else the newest installed).

The file, as measured in ZBrush 2022 to 2026: full paths separated by NUL bytes, newest first, no header, in the ANSI
code page. A path may mix / and \\ and the case varies (C:\\PROGRAMS\\ZBRUSH 2022/ZProjects/DemoHead.ZPR). It holds up
to about 500 entries, with repeats, folders and names with no extension. entries() keeps the .zpr or .ztl files (any
case) the slot lists that are on disk, each once (paths compared without case or separator differences), newest
first, at most limit of them. A network path is left out, as a Tool or Project item refuses one.

The answer is kept for CACHE_S, and read again sooner when the file's time or size changes. A file that is missing or
cannot be read gives an empty list, and log() is told once per file and reason.
"""
import ctypes
import os
import time
import uuid
from pathlib import Path

import config as C

FILE_NAME = "LightboxRecentFiles.cfg"
SUBFOLDER = ("ZStartup", "ConfigFiles")
EXTS = {"project": (".zpr",), "tool": (".ztl",), "any": (".zpr", ".ztl")}
KIND_OF_EXT = {".zpr": "project", ".ztl": "tool"}
CACHE_S = 5.0                      # an answer is reused this long while the file's time and size stay the same
PUBLIC_DOCUMENTS_ID = "{ED4824AF-DCE4-45A8-81E2-FC7965083634}"     # FOLDERID_PublicDocuments
clock = time.monotonic             # tests replace it
_cache = {}                        # (file, kind, limit) -> ((mtime_ns, size), when, [paths])
_where = {}                        # the installation's path or None -> (when, the file or None, why not)
_said = set()                      # (file, reason) already logged


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


def public_documents() -> str:
    """Windows' Public Documents folder (%PUBLIC%\\Documents unless it was moved), else %PUBLIC%\\Documents."""
    try:
        guid = _GUID.from_buffer_copy(uuid.UUID(PUBLIC_DOCUMENTS_ID).bytes_le)
        raw = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(raw)) == 0:
            try:
                if raw.value:
                    return raw.value
            finally:
                ctypes.windll.ole32.CoTaskMemFree(raw)
    except Exception:
        pass
    public = os.environ.get("PUBLIC") or os.path.join(os.environ.get("SystemDrive", "C:") + os.sep, "Users", "Public")
    return os.path.join(public, "Documents")


def list_file(install=None):
    """(the LightboxRecentFiles.cfg of a ZBrush, or None; why there is none). install: an installs.entry dict of the
    ZBrush in front; None follows the library's ZBrush. The file need not exist."""
    import brushes
    import installs
    if install is None:
        dirs = brushes.zbrush_dirs()
        if dirs["install"] is None:
            return None, "no ZBrush installation found"
        assets = dirs["user_assets"]
        install = installs.entry(dirs["install"]) or {"path": str(dirs["install"]), "year": None,
                                                      "python": assets is not None}
    else:
        assets = brushes.user_assets_of(install) if install.get("python") else None
    if install.get("python"):                       # 2026 and newer: in the user assets folder
        if assets is None:
            return None, f"no user assets folder recorded for {install['path']}"
        return Path(assets).joinpath(*SUBFOLDER, FILE_NAME), ""
    if not install.get("year"):
        return None, f"cannot tell the version of {install['path']}"
    return Path(public_documents(), f"ZBrushData{install['year']}").joinpath(*SUBFOLDER, FILE_NAME), ""


def parse(data: bytes, kind: str) -> list:
    """The paths of the list that a slot of this kind shows, newest first, each once; not checked on disk."""
    exts = EXTS[kind]
    out, seen = [], set()
    for raw in data.decode("mbcs", errors="replace").split("\0"):
        text = raw.strip()
        if not text.lower().endswith(exts) or text.startswith(("\\\\", "//")):
            continue                                # another kind, a folder, no extension, or a network path
        if not (os.path.splitdrive(text)[0] and os.path.isabs(text)):
            continue                                # not a full path: it would be looked up from the app's folder
        path = os.path.normpath(text)
        key = os.path.normcase(path)
        if key not in seen:
            seen.add(key)
            out.append(path)
    return out


def item_kind(path) -> str:
    """"project" or "tool": the item a path of the list becomes."""
    return KIND_OF_EXT[os.path.splitext(str(path))[1].lower()]


def label(path) -> str:
    """A fan item's label: the file's name without its extension."""
    return os.path.splitext(os.path.basename(str(path)))[0]


def _say(log, path, reason):
    if log is not None and (str(path), reason) not in _said:
        _said.add((str(path), reason))
        log(f"recent files: {reason}; the recent slot stays empty")


def _file_for(install, log):
    key = os.path.normcase(str(install["path"])) if install else None
    hit = _where.get(key)
    now = clock()
    if hit is None or now - hit[0] >= CACHE_S:      # finding it may scan the running processes: not at every open
        hit = _where[key] = (now, *list_file(install))
    if hit[1] is None:
        _say(log, "", hit[2])
    return hit[1]


def entries(kind, limit, install=None, log=None) -> list:
    """Up to limit paths of the files ZBrush opened last that a {"recent": kind} slot lists, newest first. install:
    the ZBrush in front (an installs.entry dict), None for the library's. log: told once of a list that cannot be
    read."""
    if kind not in C.RECENT_KINDS or limit < 1:
        return []
    path = _file_for(install, log)
    if path is None:
        return []
    try:
        st = os.stat(path)
    except OSError as e:
        _say(log, path, f"{path} is not there" if isinstance(e, FileNotFoundError) else f"{path} cannot be read: {e}")
        return []
    key, stamp, now = (os.path.normcase(str(path)), kind, limit), (st.st_mtime_ns, st.st_size), clock()
    hit = _cache.get(key)
    if hit is not None and hit[0] == stamp and now - hit[1] < CACHE_S:
        return list(hit[2])
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        _say(log, path, f"{path} cannot be read: {e}")
        return []
    found = []
    for p in parse(data, kind):
        if os.path.isfile(p):                       # a file deleted or on a drive not plugged in drops out
            found.append(p)
            if len(found) >= limit:
                break
    _cache[key] = (stamp, now, found)
    return list(found)


def reset():
    """Forgets every cached answer and what was logged (tests)."""
    _cache.clear()
    _where.clear()
    _said.clear()
