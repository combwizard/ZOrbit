"""Locate ZBrush brushes (.zbp) and produce cached icon thumbnails."""
from __future__ import annotations

import io
import time
import os
import re
import threading
from pathlib import Path

try:
    from . import installs as _installs
    from . import zbp as _zbp
except ImportError:  # run as a plain module / script
    import installs as _installs
    import zbp as _zbp

_DIR_RE = re.compile(r"^(?:Maxon )?ZBrush (\d{4})_", re.I)
_index: dict[str, Path] | None = None
_install_index: dict[str, dict[str, Path]] = {}
_index_lock = threading.Lock()
_write_lock = threading.Lock()


def _read_path(p: Path) -> Path | None:
    try:
        s = p.read_text(encoding="utf-8-sig", errors="replace").strip().strip("\"'").strip()
    except OSError:
        return None
    return Path(s) if s else None


def zbrush_dirs() -> dict:
    res = {"install": None, "user_assets": None}
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return res
    root = Path(appdata) / "Maxon"
    cands = []
    try:
        for d in root.iterdir():
            m = _DIR_RE.match(d.name)
            if m and d.is_dir():
                cands.append((int(m.group(1)), d.name, d))
    except OSError:
        return res
    for _, _, d in sorted(cands, reverse=True):
        for key, fn in (("install", "installpath.txt"), ("user_assets", "userassets_path.txt")):
            if res[key] is None:
                p = _read_path(d / fn)
                if p is not None:
                    res[key] = p
    if res["install"] is None:                  # ZBrush 2022-2025 write no installpath.txt
        try:
            found = _installs.find_installs()
        except Exception:
            found = []
        if found:
            res["install"] = Path(found[-1]["path"])
    return res


def _scan(folder: Path, recursive: bool, out: dict[str, Path]) -> None:
    if not folder.is_dir():
        return
    stack = [folder]
    while stack:
        cur = stack.pop()
        try:
            entries = sorted(os.scandir(cur), key=lambda e: e.name.lower())
        except OSError:
            continue
        subdirs = []
        for e in entries:
            try:
                if e.is_dir():
                    if recursive and not e.name.startswith("_"):
                        subdirs.append(Path(e.path))
                elif e.name.lower().endswith(".zbp"):
                    out.setdefault(Path(e.name).stem.lower(), Path(e.path))
            except OSError:
                pass
        stack.extend(reversed(subdirs))


def brush_sources() -> list[tuple[str, Path, bool]]:
    dirs = zbrush_dirs()
    src = []
    ua, ins = dirs["user_assets"], dirs["install"]
    if ua:
        src.append(("user ZStartup/BrushPresets", ua / "ZStartup" / "BrushPresets", True))
    if ins:
        src += install_brush_sources(ins)
    return src


def install_brush_sources(ins) -> list[tuple[str, Path, bool]]:
    """ZBrush 2022-2025 keep the user's brushes in the installation's ZStartup and Lightbox's in ZBrushes."""
    ins = Path(ins)
    return [("install ZStartup/BrushPresets", ins / "ZStartup" / "BrushPresets", True),
            ("install ZData/BrushPresets", ins / "ZData" / "BrushPresets", True),
            ("install Lightbox/Brushes", ins / "Lightbox" / "Brushes", True),
            ("install ZBrushes", ins / "ZBrushes", True)]


def brush_index(refresh: bool = False) -> dict[str, Path]:
    global _index
    with _index_lock:
        if _index is None or refresh:
            idx: dict[str, Path] = {}
            for _, folder, rec in brush_sources():
                _scan(folder, rec, idx)
            _index = idx
        return _index


def install_index(ins) -> dict[str, Path]:
    """Brushes of one ZBrush installation only (an older ZBrush may not load a newer version's .zbp)."""
    key = os.path.normcase(str(ins))
    with _index_lock:
        if key not in _install_index:
            idx: dict[str, Path] = {}
            for _, folder, rec in install_brush_sources(ins):
                _scan(folder, rec, idx)
            _install_index[key] = idx
        return _install_index[key]


def find_brush(name, install=None) -> Path | None:
    """The .zbp for a brush name. install: search only that ZBrush installation's folders."""
    try:
        key = str(name).replace(" ", "").lower()
        idx = install_index(install) if install else brush_index()
        p = idx.get(key)
        if p is not None:
            return p
        for k, v in idx.items():
            if k.replace(" ", "") == key:
                return v
    except Exception:
        pass
    return None


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "RadialMenu" / "thumbs"


def thumbnail(name_or_path, size: int = 96):
    try:
        from PIL import Image

        p = Path(str(name_or_path))
        if not (p.suffix.lower() == ".zbp" and p.is_file()):
            p = find_brush(str(name_or_path))
        if p is None:
            return None
        mtime = p.stat().st_mtime_ns
        cdir = _cache_dir()
        cfile = cdir / f"{p.stem}_{mtime}_{size}.png"
        try:
            with Image.open(cfile) as im:
                return im.convert("RGBA")
        except Exception:
            pass
        r = _zbp.decode_zbp_icon(p)
        if r is None:
            return None
        w, h, mode, pix = r
        im = Image.frombytes(mode, (w, h), pix).convert("RGBA")
        if (w, h) != (size, size):
            im = im.resize((size, size), Image.LANCZOS)
        try:
            with _write_lock:
                cdir.mkdir(parents=True, exist_ok=True)
                tmp = cdir / f"{cfile.name}.{os.getpid()}.{threading.get_ident()}.tmp"
                im.save(tmp, format="PNG")
                os.replace(tmp, cfile)
        except Exception:
            pass
        return im
    except Exception:
        return None


_PNG_SIG = bytes.fromhex("89504e470d0a1a0a")


def thumbnail_png(name_or_path, size: int = 96) -> bytes | None:
    """PNG bytes of a brush icon. A cached file is returned as it is, without a decode or a re-encode."""
    try:
        p = Path(str(name_or_path))
        if not (p.suffix.lower() == ".zbp" and p.is_file()):
            p = find_brush(str(name_or_path))
        if p is None:
            return None
        cfile = _cache_dir() / f"{p.stem}_{p.stat().st_mtime_ns}_{size}.png"
        try:
            data = cfile.read_bytes()
            if data.startswith(_PNG_SIG):
                return data
        except OSError:
            pass
        im = thumbnail(p, size)                 # decodes the icon and writes the cache file
        if im is None:
            return None
        try:
            data = cfile.read_bytes()
            if data.startswith(_PNG_SIG):
                return data
        except OSError:
            pass
        buf = io.BytesIO()                      # the cache write failed: encode once in memory
        im.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def cache_prune(max_files: int = 4000) -> None:
    """Delete the oldest cached thumbnails when the cache holds more than max_files. Best effort."""
    try:
        files, stale = [], time.time() - 3600
        with os.scandir(_cache_dir()) as it:
            for e in it:
                try:
                    if e.name.lower().endswith(".tmp") and e.is_file() and e.stat().st_mtime < stale:
                        os.remove(e.path)                 # a write that never finished
                    elif e.name.lower().endswith(".png") and e.is_file():
                        files.append((e.stat().st_mtime, e.path))
                except OSError:
                    pass
        extra = len(files) - int(max_files)
        if extra <= 0:
            return
        files.sort()
        for _, path in files[:extra]:
            try:
                os.remove(path)
            except OSError:
                pass
    except Exception:
        pass


def prefetch(names, size: int = 96) -> None:
    for n in names:
        try:
            thumbnail(n, size)
        except Exception:
            pass
