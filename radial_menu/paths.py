"""Where things live, both in a source checkout and in the installed (PyInstaller) build.

  %APPDATA%\\RadialMenu\\radial.json      the user's menus and settings (created from default_menus.json)
  %APPDATA%\\RadialMenu\\launch.json      how to start the app and the Studio (read by the ZBrush bridge)
  %LOCALAPPDATA%\\RadialMenu\\            logs, thumbnail cache, request/listener exchange with ZBrush
"""
import json
import os
import shutil
import sys

APP_NAME = "Radial Menu"
VERSION = "0.2.0"
FROZEN = bool(getattr(sys, "frozen", False))
PKG_DIR = os.path.dirname(os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", PKG_DIR) if FROZEN else PKG_DIR
UI_DIR = os.path.join(RESOURCE_DIR, "studio_ui")
DEFAULT_MENUS = os.path.join(RESOURCE_DIR, "default_menus.json")
ICON = os.path.join(RESOURCE_DIR, "icon.ico") if FROZEN else os.path.join(os.path.dirname(PKG_DIR), "assets", "icon.ico")

DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "RadialMenu")
CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "RadialMenu")
CONFIG_FILE = os.path.join(CONFIG_DIR, "radial.json")
LAUNCH_FILE = os.path.join(CONFIG_DIR, "launch.json")


def ensure_config() -> str:
    """The user's config path; created from the shipped defaults on first run."""
    if not os.path.exists(CONFIG_FILE):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        shutil.copyfile(DEFAULT_MENUS, CONFIG_FILE)
    return CONFIG_FILE


def launch_commands() -> dict:
    """Command lines that start the background app and the Studio from this installation."""
    if FROZEN:
        exe = sys.executable
        return {"app": [exe, "--exit-with-zbrush"], "studio": [exe, "--studio"]}
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.isfile(pyw):
        pyw = sys.executable
    main = os.path.join(PKG_DIR, "main.py")
    return {"app": [pyw, "-I", main, "--exit-with-zbrush"], "studio": [pyw, "-I", main, "--studio"]}


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
