"""ZBrush's interface colours (Preferences > Icolors), read from the scheme it stores, for the Match ZBrush theme.

ZBrush writes its interface, colours included, to ZStartup\\CustomUserInterface<year>.cfg on Preferences > Config >
Store Config: in %PUBLIC%\\Documents\\ZBrushData<year>, and for 2026.1 and newer also in
%APPDATA%\\Maxon\\ZBrush <year>_<id>\\ZStartup\\UserInterfaceLayouts. The version used is the ZBrush that is running,
else the newest version with a stored scheme; of that version's copies, the one stored last.

The format was found with tools/icolors_probe.py and is the same in ZBrush 2022 and 2026: after the chunk tag
03 80 18 04 come 2 bytes, a uint32 length, 10 float32 shading values, a uint32 count, then one float32 per patch, a
colour packed as R + G/256 + B/65536. This module only reads; it never writes a ZBrush file. Of the zorbit modules it
imports only win32 (to see which ZBrush runs), and that at call time, since theme.py imports this module.
"""
import re
import glob
import hashlib
import os
import struct
import time
from dataclasses import dataclass

TAG = b"\x03\x80\x18\x04"
COLOURS_AT = 54                 # from the tag: 4 tag + 2 + 4 length + 40 shading + 4 count
MIN_COUNT, MAX_COUNT = 40, 200  # 57 in current files, 56 in the shipped Z4R8 presets
# Where each Icolors patch sits in the list of colours.
PATCHES = {"main": 0, "main2": 1, "bt1": 2, "bt2": 3, "bt3": 4, "bt4": 5, "sw1": 6, "sw2": 7, "sw3": 8, "sw4": 9,
           "icn1": 10, "icn2": 11, "icn3": 12, "icn4": 13, "sl1": 14, "sl2": 15, "sl3": 16, "sl4": 17, "k1": 18,
           "k2": 19, "text1": 20, "text2": 21, "numbers": 22, "menu1": 28, "menu2": 29, "title1": 30, "title2": 31,
           "palette1": 32, "palette2": 33, "hilite": 47, "border": 48, "border2": 49, "sliderslit": 52}
GLOB_EVERY = 5.0                # seconds between looks for new scheme files; the files themselves are read each time


@dataclass(frozen=True)
class Scheme:
    year: int
    path: str
    mtime: float                # when ZBrush stored it
    colours: tuple              # (r, g, b) per patch, in file order
    digest: str                 # of the colours: changes when a new scheme is stored

    def get(self, name):
        i = PATCHES[name]
        return self.colours[i] if i < len(self.colours) else None


def _unpack(v: float):
    if not (0 <= v < 256):
        return None
    r = int(v)
    rest = (v - r) * 256
    g = int(rest)
    b = round((rest - g) * 256)
    if b == 256:                                     # rounding up past the last step of blue
        g, b = g + 1, 0
    return r, min(g, 255), b


def decode(data: bytes):
    """The colours of a ZBrush UI colours block as a tuple of (r, g, b), or None when data holds none."""
    at = data.find(TAG)
    while at >= 0:
        start = at + COLOURS_AT
        if start <= len(data):
            (count,) = struct.unpack_from("<I", data, start - 4)
            if MIN_COUNT <= count <= MAX_COUNT and start + 4 * count <= len(data):
                colours = tuple(_unpack(v) for v in struct.unpack_from(f"<{count}f", data, start))
                if all(c is not None for c in colours):
                    return colours
        at = data.find(TAG, at + 1)                  # the tag bytes can turn up elsewhere; try the next one
    return None


def scheme_files():
    """[(path, year)] of every CustomUserInterface<year>.cfg ZBrush may have stored."""
    public = os.environ.get("PUBLIC") or os.path.join(os.environ.get("SystemDrive", "C:") + os.sep, "Users", "Public")
    appdata = os.environ.get("APPDATA") or ""
    patterns = [os.path.join(public, "Documents", "ZBrushData20*", "ZStartup", "CustomUserInterface20*.cfg")]
    if appdata:
        patterns.append(os.path.join(appdata, "Maxon", "*ZBrush 20*", "ZStartup", "UserInterfaceLayouts",
                                     "CustomUserInterface20*.cfg"))
    out = []
    for pattern in patterns:
        for p in glob.glob(pattern):
            name = os.path.basename(p)
            year = name[len("CustomUserInterface"):len("CustomUserInterface") + 4]
            if year.isdigit():
                out.append((p, int(year)))
    return out


_YEAR_RE = re.compile(r"(?<!\d)(20\d\d)(?!\d)")
_files = {"at": 0.0, "key": None, "list": [], "running": None}
_last = {"path": None, "bytes": None, "scheme": None}


def _reset():
    """Forgets the cached file list, running version and scheme (tests)."""
    _files.update(at=0.0, key=None, list=[], running=None)
    _last.update(path=None, bytes=None, scheme=None)


def running_year():
    """The version of the ZBrush that is running (the newest, if several), or None."""
    try:
        import win32 as W
        years = [int(m.group(1)) for pid in W.pids_named("ZBrush.exe")
                 for m in [_YEAR_RE.search(W.process_image(pid))] if m]
    except Exception:
        return None
    return max(years) if years else None


def _ordered(files, running):
    """The candidates in the order they are tried: the running version's first, then the newest version first, and
    within a version the copy stored last first."""
    dated = []
    for path, year in files:
        try:
            dated.append((year == running, year, os.path.getmtime(path), path))
        except OSError:
            pass
    return sorted(dated, reverse=True)


def current():
    """The scheme of the ZBrush in use (see the module docstring), or None. The file is read on every call (it is
    small, and a stat can miss a quick rewrite) and decoded again only when its bytes changed. A file that does not
    decode gives way to the next candidate. Which files exist and which ZBrush runs is looked at every GLOB_EVERY s."""
    key = (os.environ.get("PUBLIC"), os.environ.get("APPDATA"))
    if key != _files["key"] or time.time() - _files["at"] > GLOB_EVERY:
        _files.update(at=time.time(), key=key, list=scheme_files(), running=running_year())
    for _, year, mtime, path in _ordered(_files["list"], _files["running"]):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            continue
        if path == _last["path"] and data == _last["bytes"]:
            return _last["scheme"]
        colours = decode(data)
        if colours is None:
            continue
        digest = hashlib.sha1(struct.pack(f"<{3 * len(colours)}B", *(v for c in colours for v in c))).hexdigest()[:12]
        scheme = Scheme(year, path, mtime, colours, digest)
        _last.update(path=path, bytes=data, scheme=scheme)
        return scheme
    return None
