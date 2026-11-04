"""The Capture item, {"capture": "<folder>"}: where its picture goes and what it is called.

The app turns the pick into the general file action of the bridges, {"filepress": "Document:Export", "file": path}:
ZBrush is told the next file name, then Document:Export is pressed, and the document is written there with no
dialog. Document:Export saves the canvas document at its own size, so the ring is never in the picture, whether it
is on screen when ZBrush gets round to the pick or not.

The name is ZBrush_YYYY-MM-DD_HH-MM-SS.png in local time, taken when the pick is made (ZBrush may hold the pick
back for a stroke). A name that is taken, on disk or by a pick ZBrush has not written yet, gets _2, _3 and so on,
so nothing is overwritten. Only .png is used: ZBrush 2022 does not write .jpg and 2026 stalls on it.
"""
import ctypes
import os
import time
import uuid

import zscript_bridge

BUTTON = "Document:Export"
EXTENSION = ".png"
clock = time.time                  # tests replace it
_issued = set()                    # names handed out; the file may not be on disk yet when the next pick comes
_ISSUED_MAX = 200
MAX_PATH_CHARS = 259               # Windows takes a path up to 259 characters, then the end of the string
MAX_LEGACY_BYTES = 255             # ZBrush 2022-2025 is given the path as ANSI bytes, in a buffer of 255
PICTURES_FOLDER_ID = "{33E28130-4E1E-4676-835A-98395C3BC3BB}"     # FOLDERID_Pictures
_S_OK = 0


class CaptureError(Exception):
    """kind "folder": the folder cannot be made or written to; "name": ZBrush 2022-2025 could not be given the
    folder's name (its plugin reads the ANSI code page and the volume has no short name for it).
    reason is the line for the log."""

    def __init__(self, kind, reason):
        super().__init__(reason)
        self.kind, self.reason = kind, reason


def _probe(folder):
    """Makes and removes a file in folder: whether a PNG can be written there is not something os.access can tell.
    The name is unique to each call, so a probe that could not be removed never stops the next capture."""
    p = os.path.join(folder, f".zorbit-write-test-{os.getpid()}-{uuid.uuid4().hex}")
    with open(p, "xb"):
        pass
    try:
        os.remove(p)
    except OSError:
        pass                       # the file was made, so the folder is writable; the leftover does no harm


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


def _windows_pictures():
    """The Pictures folder Windows gives (it may be moved, for example into OneDrive), or None when it cannot say."""
    try:
        guid = _GUID.from_buffer_copy(uuid.UUID(PICTURES_FOLDER_ID).bytes_le)
        raw = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(raw)) != _S_OK:
            return None
        try:
            return raw.value or None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(raw)
    except Exception:
        return None


def default_folder() -> str:
    """The ZBrush folder in Windows' Pictures folder: where an item with no folder saves. Worked out at each pick,
    so a menu passed to another PC saves into that user's own folder. Without Windows' answer, Pictures under the
    user's home folder."""
    pictures = _windows_pictures() or os.path.join(os.path.expanduser("~"), "Pictures")
    return os.path.join(pictures, "ZBrush")


def _forward(p):
    return str(p).replace("\\", "/")


def target(folder, legacy=False) -> str:
    """The file for a capture into folder, with forward slashes. The folder is made if it is missing.
    legacy: the ZBrush in front is a 2022-2025 one, whose plugin must be given an ASCII path (or 8.3 name).
    An empty folder is default_folder(). Raises CaptureError."""
    folder = str(folder or "").strip() or default_folder()
    if not (os.path.splitdrive(folder)[0] and os.path.isabs(folder)):
        raise CaptureError("folder", f"capture folder {folder!r} is not a full path")
    stem = "ZBrush_" + time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(clock()))
    n = 1
    while True:
        path = os.path.join(folder, stem + ("" if n == 1 else f"_{n}") + EXTENSION)
        key = os.path.normcase(path)
        if key not in _issued and not os.path.exists(path):
            break
        n += 1
    if len(path) > MAX_PATH_CHARS:      # checked before the folder is made, so a refused path writes nothing
        raise CaptureError("folder", f"capture folder {folder!r} cannot be used: the picture's path is {len(path)} "
                                     f"characters, and Windows takes at most {MAX_PATH_CHARS}")
    try:
        os.makedirs(folder, exist_ok=True)
        _probe(folder)
    except OSError as e:
        raise CaptureError("folder", f"capture folder {folder!r} cannot be used: {e}") from e
    if legacy and not zscript_bridge.ascii_file(path).isascii():
        raise CaptureError("name", f"capture folder {folder!r}: ZBrush 2022-2025 cannot be given a name outside "
                                   f"plain ASCII, and the volume has no short name for it")
    if legacy:
        size = len(zscript_bridge.ascii_file(path).encode("mbcs", errors="replace"))
        if size > MAX_LEGACY_BYTES:
            raise CaptureError("folder", f"capture folder {folder!r} cannot be used: ZBrush 2022-2025 takes a path of "
                                         f"at most {MAX_LEGACY_BYTES} bytes, and this one is {size}")
    if len(_issued) >= _ISSUED_MAX:
        _issued.clear()            # by now the files of the old names are on disk
    _issued.add(key)
    return _forward(path)
