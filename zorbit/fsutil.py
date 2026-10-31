"""Small file helpers shared by the app, the Studio and the tag store."""
import json
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
    except BaseException:                        # an OSError, or text that cannot be encoded: leave no .tmp behind
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise

def read_json_for_update(path):
    """A JSON object file read in order to change it and write it back: the dict, {} when the file does not exist,
    or None when it exists but cannot be read just now (held open, a hand-edit typo, not an object). A caller that
    gets None must not write: writing back what it has would wipe every key the file holds. A file held open is
    tried again once, a moment later."""
    for attempt in (0, 1):
        try:
            with open(path, encoding="utf-8-sig") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else None
        except FileNotFoundError:
            return {}
        except OSError as e:
            if attempt == 0 and _held(e):
                time.sleep(REPLACE_PAUSES[1])
                continue
            return None
        except (ValueError, RecursionError):
            return None
    return None
