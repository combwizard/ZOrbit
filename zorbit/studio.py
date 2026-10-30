"""ZOrbit Studio: the companion app (menu editor, brush library, settings, status).

A pywebview window (Windows' built-in Edge WebView2) showing studio_ui/index.html. The page calls the Api
methods below as `await window.pywebview.api.<name>(...)`; every method returns plain JSON-able data.

Started as `ZOrbit.exe --studio` (or `main.py --studio`). One instance at a time; a second launch brings
the first to the front.
"""
import base64
import ctypes
import ctypes.wintypes as w
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C          # noqa: E402
import brushes              # noqa: E402
import expand               # noqa: E402
import fsutil               # noqa: E402
import installs             # noqa: E402
import paths                # noqa: E402
import radiald              # noqa: E402
import tags                 # noqa: E402
import webapi               # noqa: E402
import winframe             # noqa: E402
import zscript_bridge       # noqa: E402

DATA_DIR = paths.DATA_DIR
CONFIG_FILE = paths.ensure_config()
UI_INDEX = os.path.join(paths.UI_DIR, "index.html")
APP_MUTEX = "Local\\ZOrbit"
STUDIO_MUTEX = "Local\\ZOrbitStudio"
TITLE = "ZOrbit Studio"
VERSION = paths.VERSION
APP_ID = "ZOrbit.Studio"           # taskbar identity, so the Studio groups under its own icon
STUDIO_FILE = os.path.join(paths.CONFIG_DIR, "studio.json")   # Studio preferences and window placement
SAMPLE_SLOTS = 8            # brushes on the tag colours sample ring (preview_tags)
RELEASES_API = "https://api.github.com/repos/combwizard/zorbit/releases/latest"
RELEASES_URL = "https://github.com/combwizard/zorbit/releases"

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
OpenMutexW = kernel32.OpenMutexW
OpenMutexW.restype, OpenMutexW.argtypes = w.HANDLE, [w.DWORD, w.BOOL, w.LPCWSTR]
CreateMutexW = kernel32.CreateMutexW
CreateMutexW.restype, CreateMutexW.argtypes = w.HANDLE, [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [w.HANDLE]
IsWindow = user32.IsWindow
IsWindow.argtypes = [w.HWND]


def _mutex_exists(name) -> bool:
    h = OpenMutexW(0x00100000, False, name)
    if h:
        CloseHandle(h)
        return True
    # An app running elevated owns a mutex this process may not open: access denied still means it exists.
    return ctypes.get_last_error() == 5          # ERROR_ACCESS_DENIED


def _tail(path, n=40):
    """The last n lines of a text file; only its last 64 KB are read, so a huge log costs nothing."""
    try:
        with open(path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - 65536))
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    if size > 65536:
        lines = lines[1:]                        # the first line may be cut in half
    return lines[-n:] if n > 0 else []


def _zbrush_running():
    """(running, check_ok): whether a ZBrush.exe process exists, and whether the process check itself worked."""
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ZBrush.exe", "/NH"], capture_output=True,
                             text=True, errors="replace", timeout=5, creationflags=0x08000000).stdout
        return "zbrush.exe" in (out or "").lower(), True
    except (OSError, subprocess.SubprocessError, ValueError):
        return False, False


def _version_key(v):
    """'v0.5.1' or '0.5.1' -> (0, 5, 1); None for anything else."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def _png_data_url(im) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=False)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _title_path(p: str) -> str:
    """'TOOL:MASKING:CLEAR' -> 'Tool:Masking:Clear' (ZBrush item paths ignore case)."""
    return ":".join(seg if not seg.isupper() else seg.title() for seg in p.split(":"))


class Api(webapi.LibraryApi, webapi.TagApi):
    def __init__(self):
        self._window = None    # underscore: pywebview must not expose (and crawl) it to JS
        self._dirty = False            # the page's last report of unsaved changes (set_dirty); informational
        self._allow_close = False      # set by close_now(): the next close goes through
        self._ask_sent = 0.0           # when we last asked the page to show the close dialog
        self._ask_acked = True         # whether the page answered that request

    # --- config ----------------------------------------------------------------------------------
    def _load_dict(self, cfg: dict):
        """Validates a config dict by loading it through the real loader. Returns (Config, problems)."""
        os.makedirs(DATA_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="studio_", suffix=".json", dir=DATA_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f)
            loaded = C.load(tmp, tags.TagStore(radiald.tags_path()).load())   # tag names checked like the app does
            return loaded, loaded.errors
        except Exception as e:
            return None, [f"config could not be read: {e}"]
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def get_config(self):
        """radial.json as the page edits it, with the loader's problems. When the file cannot be read or is
        not a JSON object, config is None and error says why (with line and column when the parser knows),
        so the page can offer to restore the backup or start again instead of failing to open."""
        out = {"config": None, "problems": [], "path": CONFIG_FILE, "defaults": C.DEFAULT_RING,
               "mtime_ns": None, "backup_exists": os.path.isfile(CONFIG_FILE + ".bak")}
        try:
            mtime_ns = os.stat(CONFIG_FILE).st_mtime_ns       # before reading: a later change shows as a conflict
            with open(CONFIG_FILE, encoding="utf-8-sig") as f:
                raw = json.load(f)
        except json.JSONDecodeError as e:
            out["error"] = f"{e.msg} at line {e.lineno}, column {e.colno}"
            return out
        except UnicodeDecodeError as e:
            out["error"] = f"the file is not valid UTF-8 text (bad byte at position {e.start})"
            return out
        except FileNotFoundError:
            out["error"] = "radial.json does not exist"
            return out
        except (OSError, ValueError, RecursionError) as e:
            out["error"] = getattr(e, "strerror", None) or str(e) or "the file could not be read"
            return out
        if not isinstance(raw, dict):
            out["error"] = "the file is not a JSON object"
            return out
        _, problems = self._load_dict(raw)
        out.update(config=raw, problems=problems, mtime_ns=mtime_ns)
        return out

    def validate(self, cfg):
        _, problems = self._load_dict(cfg)
        return {"problems": problems}

    def save_config(self, cfg, mtime_ns=None, force=False, allow_unusable=False):
        """Writes radial.json. The app notices the change within half a second. Saves even with problems (the
        loader skips bad items) and reports them, but refuses a config no ring can open from unless allow_unusable.
        mtime_ns is the file's time when the page loaded it: if the file has changed since, nothing is written
        (conflict) unless force. allow_unusable saves a config no ring can open from. The two flags are separate
        so confirming one warning never skips the other. The previous version is kept as radial.json.bak, only
        when it was valid JSON and differs, so a corrupt or unchanged file never replaces a good backup."""
        if not isinstance(cfg, dict) or not isinstance(cfg.get("menus"), dict):
            return {"saved": False, "message": "The config is not an object with a menus section."}
        exists = os.path.isfile(CONFIG_FILE)
        if mtime_ns is not None and exists and not force:
            try:
                now_ns = os.stat(CONFIG_FILE).st_mtime_ns
            except OSError:
                now_ns = None
            try:
                # The page holds this as a JS double (53 bits), which rounds a 1.7e18 ns value by up to ~128 ns,
                # so compare with a 1 microsecond slack. A real edit is never that close to the loaded time.
                changed = now_ns is not None and abs(now_ns - int(mtime_ns)) > 1000
            except (TypeError, ValueError, OverflowError):
                changed = now_ns is not None
            if changed:
                return {"saved": False, "conflict": True, "mtime_ns": now_ns,
                        "message": "radial.json changed on disk since Studio loaded it."}
        loaded, problems = self._load_dict(cfg)
        if not allow_unusable and (loaded is None or not loaded.menus
                                   or not any(m.hotkey for m in loaded.menus.values())):
            return {"saved": False, "blocked": True, "problems": problems,
                    "message": "Saving this would leave the app with no ring that can open."}
        text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
        try:
            if exists:
                with open(CONFIG_FILE, "rb") as f:
                    old_bytes = f.read()
                try:
                    old = old_bytes.decode("utf-8-sig")
                    json.loads(old)
                    if old.replace("\r\n", "\n") != text:
                        fsutil.write_atomic(CONFIG_FILE + ".bak", old_bytes)
                except ValueError:
                    pass                                   # corrupt: not worth keeping as the backup
            fsutil.write_atomic(CONFIG_FILE, text)
            st = os.stat(CONFIG_FILE)
        except OSError as e:
            return {"saved": False, "message": f"radial.json could not be written: {e.strerror or e}"}
        return {"saved": True, "problems": problems, "time": time.time(), "mtime_ns": st.st_mtime_ns}

    def restore_backup(self):
        """Puts radial.json.bak back as radial.json, if the backup is readable JSON. The backup stays."""
        bak = CONFIG_FILE + ".bak"
        try:
            with open(bak, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            return {"ok": False, "message": "There is no radial.json.bak to restore."}
        except OSError as e:
            return {"ok": False, "message": f"radial.json.bak could not be read: {e.strerror or e}"}
        try:
            if not isinstance(json.loads(data.decode("utf-8-sig")), dict):
                return {"ok": False, "message": "radial.json.bak is not a JSON object, so it was not restored."}
        except ValueError as e:
            return {"ok": False, "message": f"radial.json.bak is not valid JSON ({e}), so it was not restored."}
        try:
            fsutil.write_atomic(CONFIG_FILE, data)
        except OSError as e:
            return {"ok": False, "message": f"radial.json could not be written: {e.strerror or e}"}
        return {"ok": True, "message": "Restored radial.json from radial.json.bak."}

    def reset_config(self):
        """Starts again from the shipped default menus. The file being replaced is first kept as
        radial.json.broken (a previous .broken is overwritten), so nothing is lost."""
        try:
            with open(paths.DEFAULT_MENUS, "rb") as f:
                default = f.read()
            if os.path.isfile(CONFIG_FILE):
                with open(CONFIG_FILE, "rb") as f:
                    current = f.read()
                if current != default:
                    fsutil.write_atomic(CONFIG_FILE + ".broken", current)
            else:
                os.makedirs(paths.CONFIG_DIR, exist_ok=True)
            fsutil.write_atomic(CONFIG_FILE, default)
        except OSError as e:
            return {"ok": False, "message": f"Could not start again from the defaults: {e.strerror or e}"}
        return {"ok": True, "message": "Started again from the default menus. The old file is kept as "
                                       "radial.json.broken."}

    # --- ring preview ----------------------------------------------------------------------------
    def preview_ring(self, cfg, menu_id, hover=None, scale=1.0, open_path=None):
        """PNG data URL of the ring exactly as the app draws it. hover: item index or None. open_path: item
        indices of the fan submenus to show open ([2], or [2, 1] for a fan inside it). With a fan open the
        image is not square around the ring: width, height and centre (x, y) place the ring in it."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None or menu_id not in loaded.menus:
            return {"image": None, "problems": problems or [f"menu {menu_id!r} has no usable items"]}
        from ring import Ring
        app = radiald.App(CONFIG_FILE)
        app.cfg = loaded
        ex = expand.Expander(loaded, app.usage, app.tags.load())
        menu = ex.menu(loaded.menus[menu_id])             # as the app would fill it now; nothing is saved
        im = Ring.preview(menu, loaded.ring, app.icon_for, hover=hover, scale=float(scale),
                          submenus=ex.resolve,
                          open_path=[int(i) for i in open_path] if open_path else None)
        cx, cy = im.info.get("centre", (im.size[0] / 2, im.size[1] / 2))
        return {"image": _png_data_url(im), "size": im.size[0], "width": im.size[0], "height": im.size[1],
                "centre": [cx, cy], "problems": problems}

    def preview_tags(self, cfg, hover=None, scale=1.0):
        """preview_ring of a sample ring for the tag colour settings: SAMPLE_SLOTS installed brushes, the
        user's tagged ones first, coloured with the user's tags (two slots per tag, one slot left plain) so
        every tag setting shows even when no menu has a tagged brush."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None:
            return {"image": None, "problems": problems}
        from ring import Ring
        app = radiald.App(CONFIG_FILE)
        app.cfg = loaded
        store = app.tags.load()
        index = {k.replace(" ", ""): p for k, p in brushes.brush_index().items()}
        names = []
        for ik in store.tagged("brush"):
            if ik.split(":", 1)[1] in index:
                names.append(index[ik.split(":", 1)[1]].stem)
        for p in index.values():
            if len(names) >= SAMPLE_SLOTS:
                break
            if p.stem not in names:
                names.append(p.stem)
        if not names:
            return {"image": None, "problems": problems + ["no brushes found to draw a sample ring"]}
        names = names[:SAMPLE_SLOTS]
        colors = [t["color"] for t in store.tags()] or [tags.PALETTE[0]]
        on = loaded.ring.get("tag_colors", "tint") != "none" or loaded.ring.get("tag_band", "medium") != "none"
        items = []
        for i, n in enumerate(names):
            color = store.color_of_item(tags.item_key("brush", n)) or (
                "" if i == len(names) - 1 else colors[(i // 2) % len(colors)])
            items.append(C.Item(label=n, kind="brush", data={"brush": n}, color=color if on else ""))
        menu = C.Menu(id="sample", title="Sample", items=items)
        im = Ring.preview(menu, loaded.ring, app.icon_for, hover=hover, scale=float(scale))
        cx, cy = im.info.get("centre", (im.size[0] / 2, im.size[1] / 2))
        return {"image": _png_data_url(im), "size": im.size[0], "width": im.size[0], "height": im.size[1],
                "centre": [cx, cy], "problems": problems}

    def preview_animation(self, cfg, menu_id, fps=30, ring_anim=False):
        """Open-animation frames as PNG data URLs (played back by the Studio), plus the frame interval.
        ring_anim: play ring.animation even if the menu has its own (the Settings screen)."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None or menu_id not in loaded.menus:
            return {"frames": [], "interval_ms": 33, "problems": problems}
        import dataclasses
        from ring import Ring
        app = radiald.App(CONFIG_FILE)
        app.cfg = loaded
        ex = expand.Expander(loaded, app.usage, app.tags.load())
        menu = ex.menu(loaded.menus[menu_id])
        if ring_anim:
            menu = dataclasses.replace(menu, animation="")
        frames = Ring.preview_frames(menu, loaded.ring, app.icon_for, fps=int(fps), submenus=ex.resolve)
        return {"frames": [_png_data_url(f) for f in frames], "interval_ms": round(1000 / int(fps)),
                "problems": problems}

    def get_auto_slots(self, cfg, menu_id):
        """The brushes the app would put into the menu's auto slots now, in order (None: empty)."""
        loaded, _ = self._load_dict(cfg)
        if loaded is None or menu_id not in loaded.menus:
            return {"slots": []}
        import usage
        return {"slots": usage.Usage().load().slots(loaded.menus[menu_id])}

    def get_options(self):
        """Choices the UI offers: animation modes, label modes, action kinds, defaults."""
        return {"animations": list(C.ANIMATIONS), "labels": list(C.LABEL_MODES), "actions": list(C.ACTION_KEYS),
                "tag_colors": list(C.TAG_COLOR_MODES), "tag_bands": list(C.TAG_BANDS),
                "tint_styles": list(C.TINT_STYLES), "tint_blends": list(C.TINT_BLENDS), "ring_defaults": C.DEFAULT_RING, "ring_ranges": C._RING_RANGES}

    # --- suggestions for press/set/toggle targets ------------------------------------------------
    def get_suggestions(self):
        sug, seen = [], set()

        def add(path, source):
            k = path.replace(" ", "").lower()
            if k not in seen:
                seen.add(k)
                sug.append({"path": path, "source": source})
        ua = brushes.zbrush_dirs().get("user_assets")
        if ua:
            hk = os.path.join(str(ua), "ZStartup", "HotKeys", "StartupHotkeys.txt")
            for line in _tail(hk, 10000):
                m = re.match(r"\s*\[([^,\]]+),\d+\]\s*(?://\s*(.*))?", line)
                if m and not m.group(1).upper().startswith(("BRUSH:", "CM")):
                    add(_title_path(m.group(1)), f"your hotkeys ({(m.group(2) or '').strip()})")
        for p in ("Tool:Masking:Clear", "Tool:Masking:Inverse", "Tool:Masking:ViewMask", "Transform:Activate Symmetry",
                  "Transform:PolyF", "Transform:Solo", "Tool:Geometry:Divide", "Tool:Geometry:Lower Res",
                  "Tool:Geometry:Higher Res", "Draw:Draw Size", "Draw:Z Intensity", "Stroke:LazyMouse",
                  "Stroke:SubDivide Size", "Brush:Auto Masking:BackfaceMask", "Tool:Polygroups:Auto Groups"):
            add(p, "common")
        return sug

    # --- app status / control --------------------------------------------------------------------
    _extras = (0.0, "auto", False)             # (checked at, bridge_mode, legacy_only): the slow bits, refreshed every 30 s

    def _status_extras(self):
        """bridge_mode from the saved config and whether only a ZBrush 2022 to 2025 is installed. Both need file
        reads and an install scan, so they are cached: the status polls every 3 s and they change rarely."""
        at, mode, legacy = self._extras
        if time.monotonic() - at < 30:
            return mode, legacy
        try:
            mode = C.load(CONFIG_FILE).bridge_mode
        except Exception:
            mode = "auto"
        if mode not in ("auto", "message", "key"):
            mode = "auto"
        try:
            found = installs.find_installs()
            legacy = (not any(e["python"] for e in found)) and any(
                e["year"] and 2022 <= e["year"] <= 2025 for e in found)
        except Exception:
            legacy = False
        self._extras = (time.monotonic(), mode, legacy)
        return mode, legacy

    def get_status(self):
        listener = None
        try:
            with open(os.path.join(DATA_DIR, "listener.json"), encoding="utf-8") as f:
                info = json.load(f)
            listener = {"verified": bool(info.get("verified")), "alive": bool(IsWindow(int(info["hwnd"])))}
        except (OSError, ValueError, KeyError, TypeError):
            pass
        picks = [l for l in _tail(os.path.join(DATA_DIR, "bridge.log"), 200) if " #" in l]
        zs_log = os.path.join(DATA_DIR, "zscript_bridge.log")       # ZBrush 2022-2025: only the last pick
        try:
            if not picks or os.path.getmtime(zs_log) > os.path.getmtime(os.path.join(DATA_DIR, "bridge.log")):
                zs = _tail(zs_log, 1)
                if zs:
                    when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(zs_log)))
                    picks.append(f"{when} {zs[0]} (ZScript bridge)")
        except OSError:
            pass
        app_log = _tail(os.path.join(DATA_DIR, "radiald.log"), 40)
        zbrush_running, check_ok = _zbrush_running()
        bridge_mode, legacy_only = self._status_extras()
        return {"app_running": _mutex_exists(APP_MUTEX), "zbrush_running": zbrush_running,
                "listener": listener, "last_pick": picks[-1] if picks else None, "app_log": app_log,
                "data_dir": DATA_DIR, "bridge_mode": bridge_mode, "legacy_only": legacy_only,
                "checked_at": time.time(), "zbrush_check_ok": check_ok}

    def start_app(self):
        if _mutex_exists(APP_MUTEX):
            return {"ok": True, "running": True, "message": "The app is already running."}
        zb_running, zb_checked = _zbrush_running()
        if zb_checked and not zb_running:                  # a failed check is not "not running": let the launch try
            return {"ok": False, "running": False, "reason": "zbrush",
                    "message": "ZBrush is not running. The app starts together with ZBrush."}
        p = subprocess.Popen(paths.launch_commands()["app"], cwd=os.path.dirname(paths.PKG_DIR),
                             env=paths.clean_env(), creationflags=0x00000008 | 0x00000200, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline:
            if _mutex_exists(APP_MUTEX):
                return {"ok": True, "running": True, "message": "Started."}
            if p.poll() is not None:
                break
            time.sleep(0.2)
        else:
            if _mutex_exists(APP_MUTEX):
                return {"ok": True, "running": True, "message": "Started."}
        return {"ok": False, "running": False, "reason": "failed",
                "message": "The app did not start. The last lines of its log:",
                "log": _tail(os.path.join(DATA_DIR, "radiald.log"), 8)}

    # --- ZScript bridge for ZBrush 2022-2025 -----------------------------------------------------
    def _legacy_installs(self):
        """ZBrush installations without the Python API: found ones plus folders the user added."""
        found = installs.find_installs()
        seen = {os.path.normcase(e["path"]) for e in found}
        found = [dict(e, added=False) for e in found]
        for p in _read_studio_file().get("zbrush_folders", []):
            e = installs.entry(p) if isinstance(p, str) else None
            if e and os.path.normcase(e["path"]) not in seen:
                seen.add(os.path.normcase(e["path"]))
                found.append(dict(e, added=True))        # added by hand: the page offers to forget these
        return [e for e in found if not e["python"]]

    def get_zscript_bridge(self):
        rows = [dict(e, **zscript_bridge.status(e["path"])) for e in self._legacy_installs()]
        return {"installs": rows, "bundled": bool(zscript_bridge.bundled())}

    def _known_legacy(self, path):
        for e in self._legacy_installs():
            if os.path.normcase(e["path"]) == os.path.normcase(str(path)):
                return e
        return None

    def install_zscript_bridge(self, path):
        """Copies the plugin into that ZBrush (asks for administrator rights when the folder needs them)."""
        if self._known_legacy(path) is None:
            return {"ok": False, "message": "That folder is not a ZBrush 2022-2025 installation."}
        return zscript_bridge.install(path)

    def remove_zscript_bridge(self, path):
        if self._known_legacy(path) is None:
            return {"ok": False, "message": "That folder is not a ZBrush 2022-2025 installation."}
        return zscript_bridge.remove(path)

    def add_zbrush_folder(self):
        """Folder picker for a ZBrush that was not found automatically; remembered in studio.json."""
        import webview
        picked = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not picked:
            return {"ok": False, "cancelled": True}
        folder = picked[0] if isinstance(picked, (list, tuple)) else picked
        for cand in (folder, os.path.dirname(folder), os.path.dirname(os.path.dirname(folder))):
            e = installs.entry(cand)                 # also accepts ZStartup or ZPlugs64 picked by mistake
            if e:
                break
        if not e:
            return {"ok": False, "message": "No ZBrush.exe in that folder."}
        if e["python"]:
            return {"ok": False, "message": f"{e['name']} has the Python API: it uses the regular bridge, "
                                           "which the installer already set up."}
        if os.path.normcase(e["path"]) in {os.path.normcase(x["path"]) for x in self._legacy_installs()}:
            return {"ok": True, "message": f"{e['name']} is already listed.", "already": True}
        with _studio_lock:                     # read, change and write as one step
            data = _read_studio_file()
            folders = [p for p in data.get("zbrush_folders", []) if isinstance(p, str)]
            if os.path.normcase(e["path"]) not in {os.path.normcase(p) for p in folders}:
                folders.append(e["path"])
            data["zbrush_folders"] = folders
            _write_studio_file(data)
        return {"ok": True, "message": f"Added {e['name']}."}

    def forget_zbrush_folder(self, path):
        """Drops a folder added by hand from studio.json (never an automatically found one)."""
        key = os.path.normcase(os.path.normpath(str(path)))
        with _studio_lock:                     # read, change and write as one step
            data = _read_studio_file()
            folders = [p for p in data.get("zbrush_folders", []) if isinstance(p, str)]
            kept = [p for p in folders if os.path.normcase(os.path.normpath(p)) != key]
            if len(kept) == len(folders):
                return {"ok": False, "message": "That folder was not added by hand, so it cannot be forgotten."}
            data["zbrush_folders"] = kept
            _write_studio_file(data)
        e = installs.entry(path)
        return {"ok": True, "message": f"Forgot {e['name'] if e else os.path.basename(os.path.normpath(str(path)))}."}

    # --- Studio preferences (not part of the menus; saved straight away) --------------------------
    _PREFS_DEFAULTS = {"show_licence": True, "check_updates": True, "last_screen": "menus"}

    def get_prefs(self):
        prefs = dict(self._PREFS_DEFAULTS)
        prefs.update({k: v for k, v in _read_studio_file().items()
                      if k in self._PREFS_DEFAULTS and type(v) is type(self._PREFS_DEFAULTS[k])})   # a hand edit of the wrong type is ignored
        return prefs

    def set_pref(self, key, value):
        if key not in self._PREFS_DEFAULTS or type(value) is not type(self._PREFS_DEFAULTS[key]):
            return self.get_prefs()
        with _studio_lock:                     # read, change and write as one step
            data = _read_studio_file()             # keeps the other keys (window placement)
            data[key] = value
            _write_studio_file(data)
        return self.get_prefs()

    def check_update(self):
        """Asks GitHub for the latest release. {"current", "latest", "url", "newer"}; latest is None when the
        check is off (no request is made) or GitHub could not be reached."""
        out = {"current": VERSION, "latest": None, "url": f"{RELEASES_URL}/tag/v{VERSION}", "newer": False}
        if not self.get_prefs()["check_updates"]:
            return out
        try:
            import urllib.request
            req = urllib.request.Request(RELEASES_API, headers={
                "Accept": "application/vnd.github+json", "User-Agent": f"ZOrbitStudio/{VERSION}"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.load(r)
        except Exception as e:
            _startup(f"update check failed: {e!r}")
            return out
        tag = data.get("tag_name") if isinstance(data, dict) else None
        latest, current = _version_key(tag), _version_key(VERSION)
        if latest is None:
            return out
        out["latest"] = "%d.%d.%d" % latest
        out["newer"] = current is not None and latest > current
        if out["newer"]:
            out["url"] = f"{RELEASES_URL}/tag/{tag}"
        return out

    def open_url(self, url):
        """Opens one of the project's own links in the default browser (nothing else is allowed)."""
        allowed = ("https://github.com/combwizard/zorbit", "https://www.gnu.org/licenses/gpl-3.0.html")
        ok = isinstance(url, str) and any(url == a or url.startswith(a + c) for a in allowed for c in "/?#")
        if ok:
            os.startfile(url)
            return True
        return False

    def open_folder(self, which="data"):
        """'data' opens the logs folder; 'config' (and the older name 'app') and anything else open the folder
        radial.json is in."""
        folder = DATA_DIR if which == "data" else paths.CONFIG_DIR
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)
        return True

    def open_browser(self):
        """Opens the brush browser: asks the running one to show itself (it may be a hidden pre-warmed one, or
        one the user closed), else starts a new one that shows itself. Not --managed: the browser needs no app.
        {"ok": bool, "started": bool, "error"}."""
        try:
            import win32
            ctl = win32.find_message_window(radiald.POPOUT_CLASS)
            if ctl:
                payload = json.dumps({"tag": None, "zbrush_hwnd": 0, "toggle": False}).encode("utf-8")
                r = win32.send_copydata(ctl, radiald.COPYDATA_SHOW, payload)
                if r == 1:
                    return {"ok": True, "started": False}
                _startup(f"open_browser: SHOW to {ctl} answered {r}; starting a new one")
            subprocess.Popen(paths.launch_commands()["popout"] + ["--show"], env=paths.clean_env(),
                             creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                             close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return {"ok": True, "started": True}
        except Exception as e:
            _startup(f"open_browser failed: {e!r}")
            return {"ok": False, "started": False, "error": "Could not open the brush browser: " + str(e)}

    # --- window (custom title bar; plain Win32 so nothing touches .NET off the UI thread) ---------
    def get_app_info(self):
        return {"version": VERSION, "title": TITLE}

    def _hwnd(self):
        if not getattr(self, "_hwnd_cache", None) or not IsWindow(self._hwnd_cache):
            self._hwnd_cache = winframe.main_window(TITLE, os.getpid())
        return self._hwnd_cache

    def win_minimize(self):
        h = self._hwnd()
        if h:
            user32.ShowWindow(h, 6)                                                # SW_MINIMIZE
        return True

    def win_toggle_maximize(self):
        """Native maximise/restore. Maximised size is limited to the work area by winframe.custom_frame's
        WM_GETMINMAXINFO handler, so the taskbar stays visible. Returns the new state."""
        h = self._hwnd()
        if not h:
            return False
        user32.ShowWindow(h, 9 if user32.IsZoomed(h) else 3)                        # SW_RESTORE / SW_MAXIMIZE
        return bool(user32.IsZoomed(h))

    def win_is_maximized(self):
        h = self._hwnd()
        return bool(h and user32.IsZoomed(h))

    def set_dirty(self, dirty):
        """The page reports whether it has unsaved changes (only when that flips). Informational only: closing
        does not trust it, the page is always asked (see _on_closing)."""
        self._dirty = bool(dirty)
        return True

    def close_now(self):
        """Close for real (after the page's own Save / Discard decision)."""
        self._allow_close = True
        return self.win_close()

    def win_close(self):
        h = self._hwnd()
        if h:
            user32.PostMessageW(h, 0x0010, 0, 0)                                    # WM_CLOSE
        return True


_STARTUP_LOG = os.path.join(DATA_DIR, "studio.log")


_T0 = None


def _startup(msg):
    """One line in studio.log: seconds since this process was created, then msg. Shows where a slow start
    spends its time (for example a launch through ZScript's ShellExecute in ZBrush 2022-2025)."""
    global _T0
    try:
        if _T0 is None:
            import win32
            _T0 = win32.process_created(os.getpid()) or time.time()
            msg += f"; started by {win32.launch_chain()}; cwd {os.getcwd()}"
        if os.path.exists(_STARTUP_LOG) and os.path.getsize(_STARTUP_LOG) > 200_000:
            os.replace(_STARTUP_LOG, _STARTUP_LOG + ".old")
        with open(_STARTUP_LOG, "a", encoding="utf-8") as f:
            now = time.time()
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}.{int(now * 1000) % 1000:03d} "
                    f"+{now - _T0:6.2f} s  {msg}\n")
    except Exception:
        pass


_studio_lock = threading.RLock()        # prefs, added folders and window placement all read-modify-write this file


def _read_studio_file() -> dict:
    with _studio_lock:
        try:
            with open(STUDIO_FILE, encoding="utf-8-sig") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}


def _write_studio_file(data: dict):
    with _studio_lock:
        os.makedirs(paths.CONFIG_DIR, exist_ok=True)
        fsutil.write_atomic(STUDIO_FILE, json.dumps(data, indent=2))


def _on_closing(api):
    """pywebview 'closing' handler (runs synchronously on the UI thread; returning False cancels).
    Every way of closing (our button, Alt+F4, taskbar, WM_CLOSE) arrives here. The close is cancelled and the
    page is always asked, whatever set_dirty last said: the page closes at once when it has nothing unsaved,
    and shows its dialog when it has. That request must run on another thread: calling into the page from
    inside this handler would deadlock the UI thread."""
    if api._allow_close:
        _remember_window(api._hwnd())
        return None
    now = time.time()
    if not api._ask_acked and now - api._ask_sent > 4.0:
        _remember_window(api._hwnd())
        return None                    # the page did not answer the last request: never trap the user
    api._ask_sent, api._ask_acked = now, False

    def ask():
        try:
            ok = api._window.evaluate_js(
                "window.__studioRequestClose ? window.__studioRequestClose() : false")
        except Exception:
            ok = False
        if ok:
            api._ask_acked = True
        else:                          # no dialog available: close rather than trap the user
            api._allow_close = True
            api.win_close()
    threading.Thread(target=ask, daemon=True).start()
    return False


def _remember_window(hwnd):
    """Saves the window's normal (restored) rectangle and whether it is maximised, for the next launch.
    Taken from winframe's tracker (limit_maximise_to_work_area): GetWindowPlacement reports the size WinForms
    would restore to, which is one caption taller than the window really was."""
    try:
        rec = winframe.placement_record(hwnd)
        if not rec:
            return
        with _studio_lock:                     # read, change and write as one step
            data = _read_studio_file()
            data["window"] = rec
            _write_studio_file(data)
    except Exception:
        pass


def main():
    _startup(f"Studio {VERSION} main()")
    mutex = CreateMutexW(None, False, STUDIO_MUTEX)       # before the slow import: a second launch exits fast
    if ctypes.get_last_error() == 183:                     # already open: bring it forward
        _startup("already open: bringing it forward")
        hwnd = winframe.main_window(TITLE)
        if hwnd:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)                                             # SW_RESTORE
            else:
                user32.ShowWindow(hwnd, 5)                 # SW_SHOW: keeps a maximised window maximised
            user32.SetForegroundWindow(hwnd)
        return 0
    import webview
    _startup("pywebview imported")
    try:                                                    # own taskbar identity and icon, not Python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    # pywebview makes the process system-DPI aware when it starts and scales sizes by that DPI. Doing it
    # first means the saved window pixels and the monitor checks use the same coordinates as the window.
    user32.SetProcessDPIAware()
    scale = user32.GetDpiForSystem() / 96
    min_size = (980, 640)
    placement = winframe.saved_window(_read_studio_file().get("window"),
                                      round(min_size[0] * scale), round(min_size[1] * scale))
    if placement:
        x, y, wd, ht, _maxed = placement
        geometry = {"x": round(x / scale), "y": round(y / scale), "width": round(wd / scale),
                    "height": round(ht / scale)}
    else:
        geometry = {"width": 1320, "height": 860}
    api = Api()
    window = webview.create_window(TITLE, url=UI_INDEX, js_api=api, **geometry,
                                   min_size=min_size, background_color="#1b1c20", text_select=False)
    api._window = window
    window.events.closing += lambda: _on_closing(api)
    window.events.shown += lambda: _startup("window shown")
    window.events.loaded += lambda: _startup("page loaded")
    winframe.enable_drag_regions()
    icon = paths.ICON if os.path.isfile(paths.ICON) else None
    webview.start(lambda: winframe.custom_frame(TITLE, placement, pid=os.getpid(),
                                                on_hwnd=winframe.limit_maximise_to_work_area),
                  debug="--debug" in sys.argv, icon=icon)                     # custom_frame: worker thread
    CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    sys.exit(main())
