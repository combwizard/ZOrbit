"""Where things live, both in a source checkout and in the installed (PyInstaller) build.

  %APPDATA%\\ZOrbit\\radial.json      the user's menus and settings (created from default_menus.json)
  %APPDATA%\\ZOrbit\\tags.json        the user's brush tags
  %APPDATA%\\ZOrbit\\popout.json      window placement of the browser popout
  %APPDATA%\\ZOrbit\\launch.json      how to start the app, the Studio and the browser popout
                                    (read by the ZBrush bridge)
  %LOCALAPPDATA%\\ZOrbit\\            logs, thumbnail cache, request/listener exchange with ZBrush,
                                    activity.json (what the app last did with a ring, for the Setup screen)
  bridge_dir()                      the folder of zorbit_bridge.py that ZBRUSH_PLUGIN_PATH points at

ZOrbit used to be called Radial Menu and kept these in RadialMenu folders; ensure_config() copies them over.
"""
import json
import os
import shutil
import sys

APP_NAME = "ZOrbit"
VERSION = "0.10.1"
FROZEN = bool(getattr(sys, "frozen", False))
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", PKG_DIR) if FROZEN else PKG_DIR
UI_DIR = os.path.join(RESOURCE_DIR, "studio_ui")
# The ZScript bridge for ZBrush 2022-2025 (compiled .zsc plus its source), copied into each ZBrush by the Studio.
ZSCRIPT_DIR = (os.path.join(RESOURCE_DIR, "zscript") if FROZEN
               else os.path.join(os.path.dirname(PKG_DIR), "bridge", "zscript"))
DEFAULT_MENUS = os.path.join(RESOURCE_DIR, "default_menus.json")
ICON = os.path.join(RESOURCE_DIR, "icon.ico") if FROZEN else os.path.join(os.path.dirname(PKG_DIR), "assets", "icon.ico")
BROWSER_ICON = (os.path.join(RESOURCE_DIR, "browser.ico") if FROZEN
                else os.path.join(os.path.dirname(PKG_DIR), "assets", "browser.ico"))

DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ZOrbit")
CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ZOrbit")
CONFIG_FILE = os.path.join(CONFIG_DIR, "radial.json")
LAUNCH_FILE = os.path.join(CONFIG_DIR, "launch.json")
TAGS_FILE = os.path.join(CONFIG_DIR, "tags.json")
POPOUT_FILE = os.path.join(CONFIG_DIR, "popout.json")

# What carries over from a Radial Menu install. launch.json is left out (rewritten on every start), and so are
# logs and the thumbnail cache.
_LEGACY = ((os.path.join(os.path.dirname(CONFIG_DIR), "RadialMenu"), CONFIG_DIR,
            ("radial.json", "radial.json.bak", "studio.json")),
           (os.path.join(os.path.dirname(DATA_DIR), "RadialMenu"), DATA_DIR, ("usage.json",)))


def _migrate_legacy() -> None:
    """Copies the user's files from the Radial Menu folders. The old folders are left as they were."""
    for old, new, names in _LEGACY:
        for name in names:
            src, dst = os.path.join(old, name), os.path.join(new, name)
            if os.path.isfile(src) and not os.path.exists(dst):
                try:
                    os.makedirs(new, exist_ok=True)
                    shutil.copy2(src, dst)
                except OSError:
                    pass


def ensure_config() -> str:
    """The user's config path; on first run copied from a Radial Menu install, else from the shipped defaults."""
    if not os.path.exists(CONFIG_FILE):
        _migrate_legacy()
    if not os.path.exists(CONFIG_FILE):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        shutil.copyfile(DEFAULT_MENUS, CONFIG_FILE)
    return CONFIG_FILE


def bridge_dir() -> str | None:
    """The folder ZBRUSH_PLUGIN_PATH has to list so ZBrush 2026+ loads the Python bridge, or None when this
    build has none. Installed: <app>\\bridge. Portable zip: bridge\\ sits beside the ZOrbit\\ folder. Checkout:
    <repo>\\bridge (what tools/dev-install.ps1 registers)."""
    if not FROZEN:
        d = os.path.join(os.path.dirname(PKG_DIR), "bridge")
        return d if os.path.isfile(os.path.join(d, "zorbit_bridge.py")) else None
    here = os.path.dirname(sys.executable)
    for d in (os.path.join(here, "bridge"), os.path.join(os.path.dirname(here), "bridge")):
        if os.path.isfile(os.path.join(d, "zorbit_bridge.py")):
            return d
    return None


def launch_commands() -> dict:
    """Command lines that start the background app, the Studio and the browser popout from this
    installation."""
    if FROZEN:
        exe = sys.executable
        return {"app": [exe, "--exit-with-zbrush"], "studio": [exe, "--studio"], "popout": [exe, "--popout"]}
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        pyw = sys.executable
    main = os.path.join(PKG_DIR, "main.py")
    return {"app": [pyw, "-I", main, "--exit-with-zbrush"], "studio": [pyw, "-I", main, "--studio"],
            "popout": [pyw, "-I", main, "--popout"]}


def write_launch_file() -> None:
    """Records how to start this installation, for the ZBrush bridge. Refreshed on every start, so a moved or
    updated installation fixes itself the next time it runs."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = dict(launch_commands(), version=VERSION, frozen=FROZEN)
        tmp = LAUNCH_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, LAUNCH_FILE)
    except OSError:
        pass


def clean_env() -> dict:
    """Environment for child processes, without PYTHON* variables (ZBrush sets them for its own Python)."""
    return {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
