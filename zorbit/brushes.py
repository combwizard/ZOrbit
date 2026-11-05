"""Locate ZBrush brushes (.zbp) and produce cached icon thumbnails."""
from __future__ import annotations

import hashlib
import io
import json
import time
import os
import re
import threading
from pathlib import Path
from typing import NamedTuple

try:
    from . import installs as _installs
    from . import tags as _tags
    from . import zbp as _zbp
except ImportError:  # run as a plain module / script
    import installs as _installs
    import tags as _tags
    import zbp as _zbp

_DIR_RE = re.compile(r"^(?:Maxon )?ZBrush (\d{4})_", re.I)
_index: dict[str, Path] | None = None
_install_index: dict[str, dict[str, Path]] = {}
_index_lock = threading.Lock()
_write_lock = threading.Lock()


def _read_path(p: Path) -> Path | None:
    """The folder a ZBrush text file names. ZBrush may write it in the ANSI code page rather than UTF-8."""
    try:
        raw = p.read_bytes()
    except OSError:
        return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("mbcs")
        except (LookupError, UnicodeDecodeError):
            text = raw.decode("utf-8-sig", errors="replace")
    s = text.strip().strip("\"'").strip()
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
                if p is None:
                    continue
                if key == "install":
                    try:
                        if not (p / "ZBrush.exe").is_file():
                            continue                    # a ZBrush that was uninstalled or moved: look at the next one
                    except OSError:
                        continue
                res[key] = p
    if res["install"] is None:                  # ZBrush 2022-2025 write no installpath.txt
        try:
            found = _installs.find_installs()
        except Exception:
            found = []
        if found:
            res["install"] = Path(found[-1]["path"])
    return res


LIBRARY_KINDS = ("brush", "alpha", "material", "texture")
ADDED = "added:"            # label prefix of a folder the user added; the rest is its normcased, normalised path
_FIXED_NAMES = {"my brushes", "zbrush", "lightbox", "my alphas", "my materials", "my textures"}
_settings_cache: dict[str, tuple] = {}     # {studio.json path: (its bytes, the parsed folder lists)}


def added_label(path) -> str:
    """The label of a folder the user added. It is made from the path, so the same folder gets the same label
    whatever the case or the slashes, and a list of saved picks can name it."""
    return ADDED + os.path.normcase(os.path.normpath(str(path)))


def is_added(label) -> bool:
    return isinstance(label, str) and label.startswith(ADDED)


def _settings() -> dict:
    """{kind: [path, ...]} for every kind, from "library_folders" in studio.json. The file is read each time and
    parsed only when its bytes changed. A missing, unreadable or odd file gives empty lists; an entry that is not
    an absolute local path is left out (a network path would stall the walk), and a repeat is dropped."""
    import paths                          # at call time: the tests point CONFIG_DIR elsewhere
    path = os.path.join(paths.CONFIG_DIR, "studio.json")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        _settings_cache.pop(path, None)
        return {k: [] for k in LIBRARY_KINDS}
    hit = _settings_cache.get(path)
    if hit and hit[0] == raw:
        return {k: list(v) for k, v in hit[1].items()}
    res: dict = {k: [] for k in LIBRARY_KINDS}
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except ValueError:                    # includes UnicodeDecodeError
        data = None
    lib = data.get("library_folders") if isinstance(data, dict) else None
    if isinstance(lib, dict):
        for kind in LIBRARY_KINDS:
            seen: set = set()
            entries = lib.get(kind)
            for p in entries if isinstance(entries, list) else []:
                if not isinstance(p, str) or not p.strip() or p.strip().startswith(("\\\\", "//")):
                    continue
                if not os.path.isabs(p):
                    continue
                p = os.path.normpath(p)
                key = os.path.normcase(p)
                if key not in seen:
                    seen.add(key)
                    res[kind].append(p)
    _settings_cache[path] = (raw, res)
    return {k: list(v) for k, v in res.items()}


def user_folders(kind) -> list:
    """The folders the user added for a kind (brush, alpha, material or texture), in the order they chose."""
    return [Path(p) for p in _settings().get(kind, [])]


def user_folders_signature() -> tuple:
    """All the lists as one value the app can compare to see that the user changed them."""
    s = _settings()
    return tuple((k, tuple(s[k])) for k in LIBRARY_KINDS)


def _safe(s) -> str:
    """A folder name as a label that is also a plain name: no slash, colon or "..", never empty."""
    s = re.sub(r"[\\/:]+", " ", str(s))
    while ".." in s:
        s = s.replace("..", ".")
    return re.sub(r" +", " ", s).strip() or "folder"


def display_names(folders) -> list:
    """What each folder is called in the browser: its own name, or Drive X for a drive root. A name that is
    taken (by one of ZBrush's own libraries or by an earlier folder, case ignored) gets (2), (3) and so on."""
    taken = set(_FIXED_NAMES)
    out = []
    for f in folders:
        f = str(f)
        name = Path(f).name
        if not name:
            letter = os.path.splitdrive(f)[0].rstrip(":\\/")
            name = f"Drive {letter.upper()}" if letter else "folder"
        name = _safe(name)
        cand, n = name, 1
        while cand.lower() in taken:
            n += 1
            cand = f"{name} ({n})"
        taken.add(cand.lower())
        out.append(cand)
    return out


class Walk(NamedTuple):
    items: list           # [{"label", "rel", "name", "path"}] in list order; a name seen before is left out
    index: dict           # {tags._norm(name): Path}; the first folder that has the name wins
    sources: list         # [{"label", "path", "exists", "count", "error", "skipped"}], one per folder searched


_seen_lock = threading.Lock()
_seen_folders: set[str] = set()    # folders that were there on an earlier walk


def _real(p) -> str:
    try:
        return os.path.normcase(os.path.realpath(p))
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(p))


def walk_sources(sources, exts: tuple = (".zbp",)) -> Walk:
    """Walks the folders once, in priority order, and returns the list and the lookup index together, so the
    browser's list and the app's find() cannot disagree.

    One rule for both: the files of a folder before its subfolders, each sorted by name without regard to case;
    subfolders that start with "_" are skipped; links and junctions are followed, but a folder is entered once
    per source (by its real path), so a loop ends; the first folder that has a name (case and spaces ignored)
    wins. A source that cannot be read is reported in its "error", not raised: one that was there on an earlier
    walk and is not now, one on a drive that cannot be reached, or one whose top folder cannot be listed."""
    items: list = []
    index: dict = {}
    reports: list = []
    for label, folder, recursive in sources:
        folder = Path(folder)
        rep = {"label": label, "path": str(folder), "exists": False, "count": 0, "error": None, "skipped": 0}
        reports.append(rep)
        try:
            rep["exists"] = folder.is_dir()
        except OSError:
            rep["exists"] = False
        key = os.path.normcase(str(folder))
        if not rep["exists"]:
            with _seen_lock:
                was = key in _seen_folders
            try:
                drive_gone = bool(folder.anchor) and not os.path.exists(folder.anchor)
            except OSError:
                drive_gone = True
            if was:
                rep["error"] = f"{folder} was there before and cannot be read now"
            elif drive_gone:
                rep["error"] = f"The drive of {folder} cannot be reached"
            continue
        with _seen_lock:
            _seen_folders.add(key)
        top = os.path.normcase(os.path.abspath(folder))

        def onerror(e, rep=rep, folder=folder, top=top):
            if os.path.normcase(os.path.abspath(str(e.filename or ""))) == top:
                rep["error"] = f"{folder} cannot be read: {e.strerror or e}"
            else:
                rep["skipped"] += 1

        visited = {_real(folder)}
        for root, subs, files in os.walk(folder, onerror=onerror, followlinks=True):
            if recursive:
                keep = []
                for d in sorted(subs, key=lambda n: (n.lower(), n)):
                    if d.startswith("_"):
                        continue
                    r = _real(os.path.join(root, d))
                    if r not in visited:
                        visited.add(r)
                        keep.append(d)
                subs[:] = keep
            else:
                subs[:] = []
            rel = os.path.relpath(root, folder)
            rel = "" if rel == "." else rel.replace(os.sep, "/")
            for fn in sorted(files, key=lambda n: (n.lower(), n)):
                if not fn.lower().endswith(exts):
                    continue
                rep["count"] += 1
                name = os.path.splitext(fn)[0]
                nk = _tags._norm(name)
                if nk in index:
                    continue
                path = os.path.join(root, fn)
                index[nk] = Path(path)
                items.append({"label": label, "rel": rel, "name": name, "path": path})
    return Walk(items, index, reports)


def walk_error(walk: Walk) -> str | None:
    """The first source error of a walk, or None when every folder was read."""
    for s in walk.sources:
        if s["error"]:
            return s["error"]
    return None


def keep_index(old: dict | None, walk: Walk) -> tuple:
    """(index to keep, changed). A walk that could not read a source does not replace an index that was built:
    a drive that is away for a minute must not make every brush lose its picture."""
    if old is not None and (walk_error(walk) or old == walk.index):
        return old, False
    return walk.index, True


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


def library() -> tuple:
    """Walks the brush folders once and stores the lookup index. (Walk, whether the stored index changed)."""
    global _index
    with _index_lock:
        walk = walk_sources(brush_sources(), (".zbp",))
        _index, changed = keep_index(_index, walk)
        return walk, changed


def brush_index(refresh: bool = False) -> dict[str, Path]:
    global _index
    with _index_lock:
        if _index is None or refresh:
            walk = walk_sources(brush_sources(), (".zbp",))
            _index, _ = keep_index(_index, walk)
        return _index


def has_index() -> bool:
    return _index is not None


def has_install_index(ins) -> bool:
    return os.path.normcase(str(ins)) in _install_index


def forget_install_index(ins) -> None:
    with _index_lock:
        _install_index.pop(os.path.normcase(str(ins)), None)


def install_index(ins) -> dict[str, Path]:
    """Brushes of one ZBrush installation only (an older ZBrush may not load a newer version's .zbp)."""
    key = os.path.normcase(str(ins))
    with _index_lock:
        if key not in _install_index:
            _install_index[key] = walk_sources(install_brush_sources(ins), (".zbp",)).index
        return _install_index[key]


def find_brush(name, install=None) -> Path | None:
    """The .zbp for a brush name (case and spaces ignored). install: search only that installation's folders."""
    try:
        idx = install_index(install) if install else brush_index()
        return idx.get(_tags._norm(name))
    except Exception:
        return None


def _cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "ZOrbit" / "thumbs"


def _cache_tag(p) -> str:
    """Eight hex characters from the file's full path (case ignored), for the cache file name. A name, a time and
    a size do not tell apart two packs in different folders that both hold a 10.png and were copied or unzipped
    with their timestamps kept; the path does."""
    return hashlib.blake2b(os.path.normcase(str(p)).encode("utf-8", "surrogatepass"), digest_size=4).hexdigest()


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
        cfile = cdir / f"{p.stem}_{_cache_tag(p)}_{mtime}_{size}.png"
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
            im.save(tmp, format="PNG")                  # outside the lock: the encodes of a batch run side by side
            os.replace(tmp, cfile)
        except Exception:
            pass
        return im
    except Exception:
        return None


_PNG_SIG = bytes.fromhex("89504e470d0a1a0a")
_PNG_END = bytes.fromhex("49454e44ae426082")   # the IEND chunk: a PNG that lacks it was cut short


def thumbnail_png(name_or_path, size: int = 96) -> bytes | None:
    """PNG bytes of a brush icon. A cached file is returned as it is, without a decode or a re-encode."""
    try:
        p = Path(str(name_or_path))
        if not (p.suffix.lower() == ".zbp" and p.is_file()):
            p = find_brush(str(name_or_path))
        if p is None:
            return None
        cfile = _cache_dir() / f"{p.stem}_{_cache_tag(p)}_{p.stat().st_mtime_ns}_{size}.png"
        try:
            data = cfile.read_bytes()
            if data.startswith(_PNG_SIG) and data.endswith(_PNG_END):
                return data
        except OSError:
            pass
        im = thumbnail(p, size)                 # decodes the icon and writes the cache file
        if im is None:
            return None
        try:
            data = cfile.read_bytes()
            if data.startswith(_PNG_SIG) and data.endswith(_PNG_END):
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
