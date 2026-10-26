# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Radial Menu for ZBrush (onedir, windowed).

Build:  pyinstaller packaging/radial_menu.spec --noconfirm --distpath dist --workpath build
Result: dist/RadialMenu/RadialMenu.exe

SPECPATH (provided by PyInstaller) is the directory holding this file, i.e. <repo>/packaging.
"""
import os
import re

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo,
)

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "radial_menu")
ICON = os.path.join(ROOT, "assets", "icon.ico")
BUILD_DIR = os.path.join(ROOT, "build")
os.makedirs(BUILD_DIR, exist_ok=True)

# --- version: single source of truth is radial_menu\paths.py -------------------------------------------------
with open(os.path.join(SRC, "paths.py"), encoding="utf-8") as f:
    VERSION = re.search(r'^VERSION\s*=\s*"([^"]+)"', f.read(), re.M).group(1)
_nums = [int(n) for n in re.findall(r"\d+", VERSION)[:4]]
VERSION_TUPLE = tuple(_nums + [0] * (4 - len(_nums)))

# --- version resource (generated file, shown in Explorer > Properties > Details) -----------------------------
version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=VERSION_TUPLE, prodvers=VERSION_TUPLE, mask=0x3F, flags=0x0, OS=0x40004,
                      fileType=0x1, subtype=0x0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "combwizard"),
            StringStruct("FileDescription", "Radial Menu for ZBrush"),
            StringStruct("FileVersion", VERSION),
            StringStruct("InternalName", "RadialMenu"),
            StringStruct("LegalCopyright", "GPL-3.0"),
            StringStruct("OriginalFilename", "RadialMenu.exe"),
            StringStruct("ProductName", "Radial Menu for ZBrush"),
            StringStruct("ProductVersion", VERSION),
        ])]),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)
VERSION_FILE = os.path.join(BUILD_DIR, "version_info.txt")
with open(VERSION_FILE, "w", encoding="utf-8") as f:
    f.write(str(version_info))

# --- data files ---------------------------------------------------------------------------------------------
datas = []
UI = os.path.join(SRC, "studio_ui")
for dirpath, dirnames, filenames in os.walk(UI):
    dirnames[:] = [d for d in dirnames if not (d == "dev" and os.path.normcase(dirpath) == os.path.normcase(UI))]
    rel = os.path.relpath(dirpath, SRC)           # studio_ui, studio_ui\sub, ...
    for name in filenames:
        datas.append((os.path.join(dirpath, name), rel))
datas.append((os.path.join(SRC, "default_menus.json"), "."))
datas.append((ICON, "."))                          # bundle root: paths.ICON = RESOURCE_DIR\icon.ico

# --- pywebview (WinForms + Edge WebView2 backend) and pythonnet ---------------------------------------------
# pyinstaller-hooks-contrib ships hook-webview.py (js files, webview\lib DLLs) and hook-clr_loader / hook-pythonnet;
# collect explicitly as well so a missing or older hooks package cannot silently drop them.
binaries = []
hiddenimports = []
for pkg in ("webview", "clr_loader", "pythonnet"):
    try:
        datas += collect_data_files(pkg)
        binaries += collect_dynamic_libs(pkg)
        hiddenimports += collect_submodules(pkg)
    except Exception as exc:                       # package not installed: let the build fail loudly below
        print(f"WARNING: could not collect {pkg}: {exc}")
hiddenimports += ["clr", "webview.platforms.winforms",
                  "webview.platforms.edgechromium"]
hiddenimports = [h for h in hiddenimports if not h.startswith(("webview.platforms.gtk", "webview.platforms.qt",
                                                                 "webview.platforms.cocoa", "webview.platforms.android",
                                                                 "webview.platforms.cef", "webview.platforms.mshtml"))]

# The app modules import each other as top-level modules; some are imported inside functions.
for mod in ("config", "win32", "ring", "radiald", "studio", "brushes", "zbp", "paths", "tray"):
    if os.path.isfile(os.path.join(SRC, mod + ".py")):
        hiddenimports.append(mod)

excludes = ["tkinter", "_tkinter", "turtle", "unittest", "pydoc", "doctest", "test", "lib2to3",
            "matplotlib", "numpy", "scipy", "pandas", "IPython", "pytest",
            "PyQt5", "PyQt6", "PySide2", "PySide6", "qtpy", "gi", "cefpython3",
            "PIL.ImageTk", "PIL._tkinter_finder"]

a = Analysis(
    [os.path.join(SRC, "main.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,                         # onedir
    name="RadialMenu",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                                     # UPX-packed binaries trigger antivirus heuristics
    console=False,                                 # windowed: no console window
    icon=ICON,
    version=VERSION_FILE,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="RadialMenu",
)
