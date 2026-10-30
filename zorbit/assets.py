"""Locate ZBrush alphas, materials and textures (and brushes, through brushes.py) and make cached thumbnails.

An asset is identified by its file stem, matched without case or spaces; the first folder that has it wins
(same rule as brushes). Every public function takes a kind first: "brush" is handled by brushes.py, so callers
need one code path for all four. Thumbnails of the three new kinds are cached beside the brush ones as
{kind}_{stem}_{mtime_ns}_{size}.png; images that are not square are fitted, centred, on a transparent square.

Decoders: materials (.zmt) hold the same icon block as a .zbp brush (zbp.py); alphas are mostly 16-bit
greyscale PSDs that Pillow cannot open, so _psd_gray reads the raw uncompressed plane; textures go through
Pillow. EXR textures are listed without a thumbnail.
"""
from __future__ import annotations

import io
import os
import struct
import threading
from pathlib import Path

try:
    from . import brushes as _brushes
    from . import zbp as _zbp
except ImportError:  # run as a plain module / script
    import brushes as _brushes
    import zbp as _zbp

KINDS = ("alpha", "material", "texture")
ALL_KINDS = ("brush",) + KINDS
EXTS = {"alpha": (".psd", ".bmp", ".jpg", ".jpeg", ".png", ".tif", ".tiff"),
        "material": (".zmt",),
        "texture": (".psd", ".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".exr")}
FOLDER = {"alpha": "Alphas", "material": "Materials", "texture": "Textures"}
LEGACY = {"alpha": "ZAlphas", "material": "ZMaterials", "texture": "ZTextures"}      # ZBrush 2022-2025

_index: dict[str, dict[str, Path]] = {}
_install_index: dict[tuple, dict[str, Path]] = {}
_index_lock = threading.Lock()
_write_lock = threading.Lock()
_PNG_SIG = bytes.fromhex("89504e470d0a1a0a")
_MAX_SIDE = 32768


def sources(kind: str) -> list[tuple[str, Path, bool]]:
    """(label, folder, recursive) for every folder searched, in priority order."""
    if kind == "brush":
        return _brushes.brush_sources()
    if kind not in FOLDER:
        return []
    dirs = _brushes.zbrush_dirs()
    ua, ins, f = dirs["user_assets"], dirs["install"], FOLDER[kind]
    src = []
    if ua:
        src.append((f"user ZStartup/{f}", ua / "ZStartup" / f, True))
        if ins:
            src += [(f"install ZData/{f}", Path(ins) / "ZData" / f, True),
                    (f"install Lightbox/{f}", Path(ins) / "Lightbox" / f, True)]
    elif ins:
        src += install_sources(ins, kind)       # 2022-2025 write no userassets_path.txt: all in the installation
    return src


def install_sources(ins, kind: str) -> list[tuple[str, Path, bool]]:
    """ZBrush 2022-2025 keep the user's assets in the installation's ZStartup and Lightbox's in Z<Folder>."""
    if kind == "brush":
        return _brushes.install_brush_sources(ins)
    if kind not in FOLDER:
        return []
    ins, f = Path(ins), FOLDER[kind]
    return [(f"install ZStartup/{f}", ins / "ZStartup" / f, True),
            (f"install ZData/{f}", ins / "ZData" / f, True),
            (f"install {LEGACY[kind]}", ins / LEGACY[kind], True)]


def source_labels(kind: str) -> dict[str, str]:
    """Display name for each source label: My <Folder>, ZBrush or Lightbox."""
    if kind == "brush":
        return {"user ZStartup/BrushPresets": "My Brushes", "install ZStartup/BrushPresets": "My Brushes",
                "install ZData/BrushPresets": "ZBrush", "install Lightbox/Brushes": "Lightbox",
                "install ZBrushes": "Lightbox"}
    if kind not in FOLDER:
        return {}
    f = FOLDER[kind]
    return {f"user ZStartup/{f}": f"My {f}", f"install ZStartup/{f}": f"My {f}", f"install ZData/{f}": "ZBrush",
            f"install Lightbox/{f}": "Lightbox", f"install {LEGACY[kind]}": "Lightbox"}


def exts(kind: str) -> tuple:
    """File extensions (lower case) of this kind."""
    return (".zbp",) if kind == "brush" else EXTS.get(kind, ())


def index(kind: str, refresh: bool = False) -> dict[str, Path]:
    """{lower-case stem: file} of everything ZBrush can load of this kind."""
    if kind == "brush":
        return _brushes.brush_index(refresh)
    with _index_lock:
        if kind not in _index or refresh:
            idx: dict[str, Path] = {}
            for _, folder, rec in sources(kind):
                _brushes._scan(folder, rec, idx, exts(kind))
            _index[kind] = idx
        return _index[kind]


def install_index(ins, kind: str) -> dict[str, Path]:
    """Assets of one ZBrush installation only (an older ZBrush may not load a newer version's files)."""
    if kind == "brush":
        return _brushes.install_index(ins)
    key = (kind, os.path.normcase(str(ins)))
    with _index_lock:
        if key not in _install_index:
            idx: dict[str, Path] = {}
            for _, folder, rec in install_sources(ins, kind):
                _brushes._scan(folder, rec, idx, exts(kind))
            _install_index[key] = idx
        return _install_index[key]


def find(kind: str, name, install=None) -> Path | None:
    """The file for an asset name. install: search only that ZBrush installation's folders."""
    if kind == "brush":
        return _brushes.find_brush(name, install)
    try:
        key = str(name).replace(" ", "").lower()
        idx = install_index(install, kind) if install else index(kind)
        p = idx.get(key)
        if p is not None:
            return p
        for k, v in idx.items():
            if k.replace(" ", "") == key:
                return v
    except Exception:
        pass
    return None


# --- thumbnails ----------------------------------------------------------------------------------

def _psd_gray(p):
    """Greyscale PIL image from the first channel of a raw (uncompressed) 8 or 16-bit PSD, else None."""
    from PIL import Image

    with open(p, "rb") as f:
        d = f.read()
    if len(d) < 30 or d[:4] != b"8BPS":
        return None
    ver, channels, h, w, depth, mode = struct.unpack_from(">H6xHIIHH", d, 4)
    if ver != 1 or mode != 1 or depth not in (8, 16) or channels < 1:
        return None
    if not (0 < w <= _MAX_SIDE and 0 < h <= _MAX_SIDE):
        return None
    pos = 26
    for _ in range(3):                          # colour mode data, image resources, layer and mask info
        if pos + 4 > len(d):
            return None
        pos += 4 + struct.unpack_from(">I", d, pos)[0]
    if pos + 2 > len(d) or struct.unpack_from(">H", d, pos)[0] != 0:
        return None                             # RLE or zip compressed: leave it to Pillow
    pos += 2
    n = w * h * (depth // 8)
    if pos + n > len(d):
        return None
    plane = d[pos:pos + n:2] if depth == 16 else d[pos:pos + n]     # 16-bit is big-endian: keep each high byte
    return Image.frombytes("L", (w, h), plane)


def _fit_square(im, size: int):
    """RGBA image scaled to fit size x size and centred on a transparent square."""
    from PIL import Image

    im = im.convert("RGBA")
    w, h = im.size
    if (w, h) == (size, size):
        return im
    s = size / max(w, h)
    nw, nh = max(1, round(w * s)), max(1, round(h * s))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(im, ((size - nw) // 2, (size - nh) // 2))
    return canvas


def _pillow(p, size: int):
    """Pillow image reduced to at most size x size."""
    from PIL import Image

    im = Image.open(p)
    if im.format == "JPEG":
        im.draft("RGB", (2 * size, 2 * size))   # the decoder skips most of the pixels
    im.load()
    if im.mode.startswith("I") or im.mode == "F":   # 16 and 32-bit greyscale: scale into 8 bit
        im = im.convert("I").point(lambda v: v * (1 / 256)).convert("L")
    im.thumbnail((size, size), Image.LANCZOS)
    return im


def _decode(kind: str, p: Path, size: int):
    from PIL import Image

    if kind == "material":
        r = _zbp.decode_zbp_icon(p)
        if r is None:
            return None
        w, h, mode, pix = r
        return _fit_square(Image.frombytes(mode, (w, h), pix), size)
    if kind == "alpha":
        im = _psd_gray(p) if p.suffix.lower() == ".psd" else None
        if im is not None:
            im.thumbnail((size, size), Image.LANCZOS)
        else:
            im = _pillow(p, size)
        return _fit_square(im, size)
    if kind == "texture" and p.suffix.lower() != ".exr":
        return _fit_square(_pillow(p, size), size)
    return None


def _resolve(kind: str, name_or_path) -> Path | None:
    p = Path(str(name_or_path))
    if p.suffix.lower() in EXTS[kind] and p.is_file():
        return p
    return find(kind, str(name_or_path))


def _cache_file(kind: str, p: Path, size: int) -> Path:
    return _brushes._cache_dir() / f"{kind}_{p.stem}_{p.stat().st_mtime_ns}_{size}.png"


def thumbnail(kind: str, name_or_path, size: int = 96):
    """RGBA PIL image (size x size) of an asset's thumbnail, None if it has none. Never raises."""
    if kind == "brush":
        return _brushes.thumbnail(name_or_path, size)
    try:
        from PIL import Image

        if kind not in FOLDER:
            return None
        p = _resolve(kind, name_or_path)
        if p is None:
            return None
        cfile = _cache_file(kind, p, size)
        try:
            with Image.open(cfile) as im:
                return im.convert("RGBA")
        except Exception:
            pass
        im = _decode(kind, p, size)
        if im is None:
            return None
        try:
            with _write_lock:
                cfile.parent.mkdir(parents=True, exist_ok=True)
                tmp = cfile.parent / f"{cfile.name}.{os.getpid()}.{threading.get_ident()}.tmp"
                im.save(tmp, format="PNG")
                os.replace(tmp, cfile)
        except Exception:
            pass
        return im
    except Exception:
        return None


def thumbnail_png(kind: str, name_or_path, size: int = 96) -> bytes | None:
    """PNG bytes of a thumbnail. A cached file is returned as it is, without a decode or a re-encode."""
    if kind == "brush":
        return _brushes.thumbnail_png(name_or_path, size)
    try:
        if kind not in FOLDER:
            return None
        p = _resolve(kind, name_or_path)
        if p is None:
            return None
        cfile = _cache_file(kind, p, size)
        try:
            data = cfile.read_bytes()
            if data.startswith(_PNG_SIG):
                return data
        except OSError:
            pass
        im = thumbnail(kind, p, size)           # decodes and writes the cache file
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


def prefetch(pairs, size: int = 96) -> None:
    """Warm the cache for (kind, name) pairs."""
    for kind, name in pairs:
        try:
            thumbnail(kind, name, size)
        except Exception:
            pass
