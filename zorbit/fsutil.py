"""Small file helpers shared by the app, the Studio and the tag store."""
import os


def write_atomic(path, data):
    """Writes str (as UTF-8 text) or bytes to path.tmp, flushes it to disk, then swaps it in, so a crash or a
    power cut leaves either the old file or the new one, never half of one."""
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
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
