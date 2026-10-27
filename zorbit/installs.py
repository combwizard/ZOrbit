"""Finds the ZBrush installations on this machine (stdlib only).

Public API:
  find_installs() -> list of {"name", "year", "path", "python"} sorted by year, newest last
  install_of(exe_path) -> that dict for a running ZBrush.exe

"python" is whether the installation has ZBrush's Python API (2026 and later): those load the Python bridge,
older ones (2022-2025) need the ZScript bridge. Sources, all optional: the uninstall entries in the registry,
%APPDATA%\\Maxon\\*\\installpath.txt (written by recent versions), and the usual Program Files folders.
"""
from __future__ import annotations

import glob
import os
import re
import winreg

_YEAR_RE = re.compile(r"\b(20\d\d)\b")
_UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"


def _norm(p) -> str:
    return os.path.normcase(os.path.normpath(str(p)))


def has_python_api(path) -> bool:
    return bool(glob.glob(os.path.join(str(path), "python3*.dll")))


def entry(path, name_hint="") -> dict | None:
    path = os.path.normpath(str(path).strip().strip('"'))
    if not os.path.isfile(os.path.join(path, "ZBrush.exe")):
        return None
    m = _YEAR_RE.search(name_hint) or _YEAR_RE.search(os.path.basename(path))
    year = int(m.group(1)) if m else None
    name = f"ZBrush {year}" if year else os.path.basename(path)
    return {"name": name, "year": year, "path": path, "python": has_python_api(path)}


def _from_registry():
    views = ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY), (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
             (winreg.HKEY_CURRENT_USER, 0))
    for hive, view in views:
        try:
            root = winreg.OpenKey(hive, _UNINSTALL, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with root:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                try:
                    with winreg.OpenKey(root, sub) as k:
                        name = str(winreg.QueryValueEx(k, "DisplayName")[0])
                        if "zbrush" not in name.lower():
                            continue
                        loc = ""
                        for value in ("InstallLocation", "DisplayIcon", "UninstallString"):
                            try:
                                loc = str(winreg.QueryValueEx(k, value)[0]).strip().strip('"')
                            except OSError:
                                continue
                            if loc:
                                break
                except OSError:
                    continue
                # DisplayIcon/UninstallString point at a file inside the installation; walk up to ZBrush.exe.
                d = loc if os.path.isdir(loc) else os.path.dirname(loc)
                for _ in range(3):
                    if not d or os.path.isfile(os.path.join(d, "ZBrush.exe")):
                        break
                    d = os.path.dirname(d)
                if d:
                    yield d, name


def _from_appdata():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return
    for f in glob.glob(os.path.join(appdata, "Maxon", "*", "installpath.txt")):
        try:
            with open(f, encoding="utf-8-sig", errors="replace") as fh:
                p = fh.read().strip().strip("\"'").strip()
        except OSError:
            continue
        if p:
            yield p, os.path.basename(os.path.dirname(f))


def _from_folders():
    for base in {os.environ.get("ProgramFiles"), os.environ.get("ProgramW6432"), r"C:\Program Files"}:
        if not base:
            continue
        for pattern in ("Maxon ZBrush 20*", "ZBrush 20*", os.path.join("Pixologic", "ZBrush 20*"),
                        os.path.join("Maxon", "ZBrush 20*")):
            for d in glob.glob(os.path.join(base, pattern)):
                yield d, os.path.basename(d)


def find_installs() -> list[dict]:
    found = {}
    for source in (_from_registry, _from_appdata, _from_folders):
        try:
            for path, hint in source():
                e = entry(path, hint)
                if e is None:
                    continue
                key = _norm(e["path"])
                if key not in found or (found[key]["year"] is None and e["year"]):
                    found[key] = e
        except OSError:
            continue
    return sorted(found.values(), key=lambda e: (e["year"] or 0, e["path"].lower()))


def install_of(exe_path) -> dict | None:
    """The installation a running ZBrush.exe belongs to (year from the registry when the folder lacks one)."""
    if not exe_path:
        return None
    d = os.path.dirname(str(exe_path))
    e = entry(d)
    if e is None:
        return None
    if e["year"] is None:
        for other in find_installs():
            if _norm(other["path"]) == _norm(d):
                return other
    return e
