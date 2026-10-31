"""Small file helpers shared by the app, the Studio and the tag store."""
import os
import time

REPLACE_PAUSES = (0.05, 0.1, 0.2, 0.4, 0.8)       # seconds between tries when another process holds the file


def _held(e: OSError) -> bool:
    """True if another process has the file open (a scanner, a sync client, the other writer)."""
    return isinstance(e, PermissionError) or getattr(e, "winerror", None) in (5, 32)


def _replace(tmp, path):
    """os.replace, tried again a few times when the target is held open for a moment."""
    for pause in REPLACE_PAUSES:
        try:
            os.replace(tmp, path)
            return
        except OSError as e:
            if not _held(e):
                raise
            time.sleep(pause)
    os.replace(tmp, path)


def write_atomic(path, data):
    """Writes str (as UTF-8 text) or bytes to path.tmp, flushes it to disk, then swaps it in, so a crash or a
    power cut leaves either the old file or the new one, never half of one. A target another process holds open is
    tried again up to five times (50 ms to 800 ms apart) before the error is raised."""
    tmp = f"{path}.{os.getpid()}.tmp"            # per process: two writers never share a half-written file
    try:
        if isinstance(data, bytes):
            f = open(tmp, "wb")
        else:
            f = open(tmp, "w", encoding="utf-8")
        with f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        _replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
