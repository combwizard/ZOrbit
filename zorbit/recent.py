"""The Recent item, {"recent": "project" | "tool" | "any"}: a fan of the projects and tools ZBrush opened last, read
from ZBrush's own Lightbox list. expand.py turns the slot into a fan of Project and Tool items, so a pick goes through
fileitem.py like any other.

ZBrush keeps the list in ZStartup\\ConfigFiles\\LightboxRecentFiles.cfg: in the user assets folder for ZBrush 2026 and
newer (the folder its userassets_path.txt names, as for the library), and in <Public Documents>\\ZBrushData<year> for
2022 to 2025. The ZBrush is the one in front when the caller knows it, else the one the library follows
(brushes.zbrush_dirs: the newest running, else the newest installed).

The file, as measured in ZBrush 2022 to 2026: full paths separated by NUL bytes, newest first, no header, in the ANSI
code page (UTF-8 is read too). A path may mix / and \\ and the case varies (C:\\PROGRAMS\\ZBRUSH 2022/ZProjects/
DemoHead.ZPR). It holds up to about 500 entries, with repeats, folders and names with no extension. A slot shows the
.zpr or .ztl files (any case) of its kind that are on disk, each once (paths compared without case or separator
differences), newest first, at most limit of them. A network path is left out, as a Tool or Project item refuses one.

The ring opens in a few milliseconds, so the open path never touches the disk: entries() only returns the last
answer kept for that list, and asks for a new one when it is older than REFRESH_S. The answers are worked out by one
worker thread (refresh_later), which finds the file (kept for WHERE_S per ZBrush, as finding it may scan the
running processes), reads it and checks each file on disk; a slow or unplugged drive only holds up the worker. The app
asks for them when its menus load (prefetch), so the first open finds one. An exception in the worker is logged once
and leaves the old answer. A list that is missing or cannot be read gives an empty answer, also logged once.
"""
import ctypes
import os
import threading
import time
import traceback
import uuid
from pathlib import Path

import config as C

FILE_NAME = "LightboxRecentFiles.cfg"
SUBFOLDER = ("ZStartup", "ConfigFiles")
EXTS = {"project": (".zpr",), "tool": (".ztl",), "any": (".zpr", ".ztl")}
REFRESH_S = 5.0                    # an answer older than this is worked out again in the background
WHERE_S = 120.0                    # where a ZBrush keeps its list is looked up again after this long
PUBLIC_DOCUMENTS_ID = "{ED4824AF-DCE4-45A8-81E2-FC7965083634}"     # FOLDERID_PublicDocuments
clock = time.monotonic             # tests replace it
_answers = {}                      # (file, kind, limit) -> (when, [paths]): what the open path returns
_where = {}                        # the installation's path or None -> (when, the file or None, why not)
_said = set()                      # (file, reason) already logged
_lock = threading.Lock()
_pending = {}                      # (install key, kind, limit) -> (kind, limit, install, log): waiting for the worker
_worker = None                     # the worker thread while it runs; one at a time


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
    ZBrush in front; None follows the library's ZBrush, with its version as the install scan has it (the registry
    knows a year the folder's name may not have). The file need not exist. Reads the disk: never on the open path."""
    import brushes
    import installs
    if install is None:
        dirs = brushes.zbrush_dirs()
        if dirs["install"] is None:
            return None, "no ZBrush installation found"
        assets = dirs["user_assets"]
        install = installs.install_of(os.path.join(str(dirs["install"]), "ZBrush.exe")) or {
            "path": str(dirs["install"]), "year": None, "python": assets is not None}
    else:
        assets = brushes.user_assets_of(install) if install.get("python") else None
    if install.get("python"):                       # 2026 and newer: in the user assets folder
        if assets is None:
            return None, f"no user assets folder recorded for {install['path']}"
        return Path(assets).joinpath(*SUBFOLDER, FILE_NAME), ""
    if not install.get("year"):
        return None, f"cannot tell the version of {install['path']}"
    return Path(public_documents(), f"ZBrushData{install['year']}").joinpath(*SUBFOLDER, FILE_NAME), ""


def decode(data: bytes) -> str:
    """The list's text: UTF-8 when it is that, else the ANSI code page ZBrush writes (as brushes._read_path does)."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("mbcs", errors="replace")
        except LookupError:
            return data.decode("utf-8", errors="replace")


def parse(data: bytes, kind: str) -> list:
    """The paths of the list that a slot of this kind shows, newest first, each once; not checked on disk."""
    exts = EXTS[kind]
    out, seen = [], set()
    for raw in decode(data).split("\0"):
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
    """"project" or "tool": the item a path of the list becomes (by its ending, so a file named only .zpr is one)."""
    return "project" if str(path).lower().endswith(".zpr") else "tool"


def label(path) -> str:
    """A fan item's label: the file's name without its extension (a name that is only .zpr or .ztl stays whole)."""
    name = os.path.basename(str(path))
    return name[:-4] if len(name) > 4 and name.lower().endswith((".zpr", ".ztl")) else name


def _say(log, path, reason):
    if log is not None and (str(path), reason) not in _said:
        _said.add((str(path), reason))
        try:
            log(f"recent files: {reason}; the recent slot stays empty")
        except Exception:
            pass


def _ikey(install):
    return os.path.normcase(str(install["path"])) if install else None


# --- the open path: cached answers only -------------------------------------------------------------
def entries(kind, limit, install=None, log=None) -> list:
    """Up to limit paths of the files ZBrush opened last that a {"recent": kind} slot lists, newest first, as last
    worked out; [] before the first answer. Never reads the disk. An answer that is missing or older than REFRESH_S
    is asked of the worker, so the next open has a fresh one. install: the ZBrush in front (an installs.entry dict),
    None for the library's; while the one in front has no answer yet, the library's is used. log: told once of a list
    that cannot be read."""
    if kind not in C.RECENT_KINDS or limit < 1:
        return []
    now = clock()
    where = _where.get(_ikey(install))
    if where is None or now - where[0] >= WHERE_S:
        refresh_later(kind, limit, install, log)
    if where is None and install is not None:
        where = _where.get(None)                    # not looked up yet: the library's ZBrush, usually the same one
    if where is None or where[1] is None:
        return []
    hit = _answers.get((os.path.normcase(str(where[1])), kind, limit))
    if hit is None or now - hit[0] >= REFRESH_S:
        refresh_later(kind, limit, install, log)
    return list(hit[1]) if hit is not None else []


def prefetch(kinds, limit, install=None, log=None):
    """Asks the worker for the answers of these kinds now, so the first ring finds them (the app does this when its
    menus load). install: the ZBrush in front, if one is; the library's ZBrush is asked for too."""
    for kind in kinds:
        if kind in C.RECENT_KINDS and limit >= 1:
            refresh_later(kind, limit, None, log)
            if install is not None:
                refresh_later(kind, limit, install, log)


# --- the worker -----------------------------------------------------------------------------------
def refresh_later(kind, limit, install=None, log=None):
    """Has the worker thread work out this answer. A request already waiting is not added twice, and only one worker
    runs at a time."""
    global _worker
    with _lock:
        _pending[(_ikey(install), kind, limit)] = (kind, limit, install, log)
        if _worker is None:
            _worker = threading.Thread(target=_work, name="recent-files", daemon=True)
            _worker.start()


def _work():
    global _worker
    while True:
        with _lock:
            if not _pending:
                _worker = None
                return
            _, args = _pending.popitem()
        refresh(*args)


def refresh(kind, limit, install=None, log=None):
    """Works out one answer now and keeps it (the worker's job; tests call it directly). Reads the disk. An exception
    is logged once and the old answer stays."""
    try:
        _refresh(kind, limit, install, log)
    except Exception as e:
        _say(log, "", f"could not be read ({e!r})")
        if log is not None and ("trace", repr(e)) not in _said:
            _said.add(("trace", repr(e)))
            try:
                log("recent files:\n" + traceback.format_exc())
            except Exception:
                pass


def _refresh(kind, limit, install, log):
    ikey, now = _ikey(install), clock()
    where = _where.get(ikey)
    if where is None or now - where[0] >= WHERE_S:
        where = _where[ikey] = (now, *list_file(install))
    path = where[1]
    if path is None:
        _say(log, "", where[2])
        return
    key = (os.path.normcase(str(path)), kind, limit)
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        _say(log, path, f"{path} is not there" if isinstance(e, FileNotFoundError) else f"{path} cannot be read: {e}")
        _answers[key] = (now, [])
        return
    found = []
    for p in parse(data, kind):
        if os.path.isfile(p):                       # a file deleted or on a drive not plugged in drops out
            found.append(p)
            if len(found) >= limit:
                break
    _answers[key] = (now, found)


def wait(timeout=5.0) -> bool:
    """Waits until the worker has nothing left to do (tests, and Studio's previews). True when it finished."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with _lock:
            if _worker is None and not _pending:
                return True
        time.sleep(0.005)
    return False


def reset():
    """Forgets every answer and what was logged (tests)."""
    wait(2.0)
    _answers.clear()
    _where.clear()
    _said.clear()
