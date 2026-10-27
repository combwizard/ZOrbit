"""Radial Menu Studio: the companion app (menu editor, brush library, settings, status).

A pywebview window (Windows' built-in Edge WebView2) showing studio_ui/index.html. The page calls the Api
methods below as `await window.pywebview.api.<name>(...)`; every method returns plain JSON-able data.

Started as `RadialMenu.exe --studio` (or `main.py --studio`). One instance at a time; a second launch brings
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
import installs             # noqa: E402
import paths                # noqa: E402
import zscript_bridge       # noqa: E402

DATA_DIR = paths.DATA_DIR
CONFIG_FILE = paths.ensure_config()
UI_INDEX = os.path.join(paths.UI_DIR, "index.html")
APP_MUTEX = "Local\\RadialMenuForZBrush"
STUDIO_MUTEX = "Local\\RadialMenuStudio"
TITLE = "Radial Menu Studio"
VERSION = paths.VERSION
APP_ID = "RadialMenu.Studio"           # taskbar identity, so the Studio groups under its own icon
STUDIO_FILE = os.path.join(paths.CONFIG_DIR, "studio.json")   # Studio preferences and window placement

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
    return False


def _tail(path, n=40):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().splitlines()[-n:]
    except OSError:
        return []


def _png_data_url(im) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=False)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _title_path(p: str) -> str:
    """'TOOL:MASKING:CLEAR' -> 'Tool:Masking:Clear' (ZBrush item paths ignore case)."""
    return ":".join(seg if not seg.isupper() else seg.title() for seg in p.split(":"))


class Api:
    def __init__(self):
        self._window = None    # underscore: pywebview must not expose (and crawl) it to JS
        self._dirty = False            # the page has unsaved changes (reported by set_dirty)
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
            loaded = C.load(tmp)
            return loaded, loaded.errors
        except Exception as e:
            return None, [f"config could not be read: {e}"]
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def get_config(self):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            raw = json.load(f)
        _, problems = self._load_dict(raw)
        return {"config": raw, "problems": problems, "path": CONFIG_FILE, "defaults": C.DEFAULT_RING}

    def validate(self, cfg):
        _, problems = self._load_dict(cfg)
        return {"problems": problems}

    def save_config(self, cfg):
        """Writes radial.json (previous version kept as radial.json.bak). The app notices the change within
        half a second. Saves even with problems (the loader skips bad items) and reports them."""
        _, problems = self._load_dict(cfg)
        text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, encoding="utf-8") as f:
                old = f.read()
            with open(CONFIG_FILE + ".bak", "w", encoding="utf-8") as f:
                f.write(old)
        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, CONFIG_FILE)
        return {"saved": True, "problems": problems, "time": time.time()}

    # --- ring preview ----------------------------------------------------------------------------
    def preview_ring(self, cfg, menu_id, hover=None, scale=1.0):
        """PNG data URL of the ring exactly as the app draws it. hover: item index or None."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None or menu_id not in loaded.menus:
            return {"image": None, "problems": problems or [f"menu {menu_id!r} has no usable items"]}
        import radiald
        from ring import Ring
        app = radiald.App(CONFIG_FILE)
        app.cfg = loaded
        im = Ring.preview(loaded.menus[menu_id], loaded.ring, app.icon_for, hover=hover, scale=float(scale))
        return {"image": _png_data_url(im), "size": im.size[0], "problems": problems}

    def preview_animation(self, cfg, menu_id, fps=30, ring_anim=False):
        """Open-animation frames as PNG data URLs (played back by the Studio), plus the frame interval.
        ring_anim: play ring.animation even if the menu has its own (the Settings screen)."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None or menu_id not in loaded.menus:
            return {"frames": [], "interval_ms": 33, "problems": problems}
        import dataclasses
        import radiald
        from ring import Ring
        app = radiald.App(CONFIG_FILE)
        app.cfg = loaded
        menu = loaded.menus[menu_id]
        if ring_anim:
            menu = dataclasses.replace(menu, animation="")
        frames = Ring.preview_frames(menu, loaded.ring, app.icon_for, fps=int(fps))
        return {"frames": [_png_data_url(f) for f in frames], "interval_ms": round(1000 / int(fps)),
                "problems": problems}

    def get_options(self):
        """Choices the UI offers: animation modes, label modes, action kinds, defaults."""
        return {"animations": list(C.ANIMATIONS), "labels": list(C.LABEL_MODES), "actions": list(C.ACTION_KEYS),
                "ring_defaults": C.DEFAULT_RING, "ring_ranges": C._RING_RANGES}

    # --- brush library ---------------------------------------------------------------------------
    def get_library(self):
        """All brushes ZBrush can load, first location wins (same rule the app uses), with categories."""
        seen, items = set(), []
        labels = {"user ZStartup/BrushPresets": "My Brushes", "install ZStartup/BrushPresets": "My Brushes",
                  "install ZData/BrushPresets": "ZBrush", "install Lightbox/Brushes": "Lightbox",
                  "install ZBrushes": "Lightbox"}
        for label, folder, _rec in brushes.brush_sources():
            if not folder.is_dir():
                continue
            for root, dirs, files in os.walk(folder):
                dirs[:] = sorted(d for d in dirs if not d.startswith("_"))
                rel = os.path.relpath(root, folder)
                for fn in sorted(files, key=str.lower):
                    if not fn.lower().endswith(".zbp"):
                        continue
                    name = os.path.splitext(fn)[0]
                    if name.lower() in seen:
                        continue
                    seen.add(name.lower())
                    src = labels.get(label, label)
                    cat = src if rel == "." else f"{src}/{rel.replace(os.sep, '/')}"
                    items.append({"name": name, "source": src, "category": cat,
                                  "path": os.path.join(root, fn)})
        cats = {}
        for it in items:
            cats[it["category"]] = cats.get(it["category"], 0) + 1
        return {"brushes": items, "categories": [{"id": k, "count": v} for k, v in cats.items()]}

    def get_thumbs(self, names, size=128):
        """{name: data URL or None} for a batch of brush names (cached on disk after the first decode)."""
        out = {}
        for n in names or []:
            im = brushes.thumbnail(n, int(size))
            out[n] = _png_data_url(im) if im is not None else None
        return out

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
    def get_status(self):
        listener = None
        try:
            with open(os.path.join(DATA_DIR, "listener.json"), encoding="utf-8") as f:
                info = json.load(f)
            listener = {"verified": bool(info.get("verified")), "alive": bool(IsWindow(int(info["hwnd"])))}
        except (OSError, ValueError, KeyError):
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
        app_log = _tail(os.path.join(DATA_DIR, "radiald.log"), 12)
        from_win = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ZBrush.exe", "/NH"], capture_output=True,
                                  text=True, creationflags=0x08000000).stdout
        return {"app_running": _mutex_exists(APP_MUTEX), "zbrush_running": "zbrush.exe" in from_win.lower(),
                "listener": listener, "last_pick": picks[-1] if picks else None, "app_log": app_log,
                "data_dir": DATA_DIR}

    def start_app(self):
        if _mutex_exists(APP_MUTEX):
            return {"ok": True, "message": "The app is already running."}
        st = self.get_status()
        if not st["zbrush_running"]:
            return {"ok": False, "message": "ZBrush is not running. The app starts together with ZBrush."}
        subprocess.Popen(paths.launch_commands()["app"], cwd=os.path.dirname(paths.PKG_DIR),
                         env=paths.clean_env(), creationflags=0x00000008 | 0x00000200, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "message": "Started."}

    # --- ZScript bridge for ZBrush 2022-2025 -----------------------------------------------------
    def _legacy_installs(self):
        """ZBrush installations without the Python API: found ones plus folders the user added."""
        found = installs.find_installs()
        seen = {os.path.normcase(e["path"]) for e in found}
        for p in _read_studio_file().get("zbrush_folders", []):
            e = installs.entry(p) if isinstance(p, str) else None
            if e and os.path.normcase(e["path"]) not in seen:
                seen.add(os.path.normcase(e["path"]))
                found.append(e)
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
        data = _read_studio_file()
        folders = [p for p in data.get("zbrush_folders", []) if isinstance(p, str)]
        if os.path.normcase(e["path"]) not in {os.path.normcase(p) for p in folders}:
            folders.append(e["path"])
        data["zbrush_folders"] = folders
        _write_studio_file(data)
        return {"ok": True, "message": f"Added {e['name']}."}

    # --- Studio preferences (not part of the menus; saved straight away) --------------------------
    _PREFS_DEFAULTS = {"show_licence": True}

    def get_prefs(self):
        prefs = dict(self._PREFS_DEFAULTS)
        prefs.update({k: v for k, v in _read_studio_file().items() if k in self._PREFS_DEFAULTS})
        return prefs

    def set_pref(self, key, value):
        if key not in self._PREFS_DEFAULTS or type(value) is not type(self._PREFS_DEFAULTS[key]):
            return self.get_prefs()
        data = _read_studio_file()             # keeps the other keys (window placement)
        data[key] = value
        _write_studio_file(data)
        return self.get_prefs()

    def open_url(self, url):
        """Opens one of the project's own links in the default browser (nothing else is allowed)."""
        allowed = ("https://github.com/combwizard/zbrush-radial-menu", "https://www.gnu.org/licenses/gpl-3.0.html")
        if isinstance(url, str) and url.startswith(allowed):
            os.startfile(url)
            return True
        return False

    def open_folder(self, which="data"):
        os.startfile(DATA_DIR if which == "data" else paths.CONFIG_DIR)
        return True

    # --- window (custom title bar; plain Win32 so nothing touches .NET off the UI thread) ---------
    def get_app_info(self):
        return {"version": VERSION, "title": TITLE}

    def _hwnd(self):
        if not getattr(self, "_hwnd_cache", None) or not IsWindow(self._hwnd_cache):
            self._hwnd_cache = _main_window(TITLE, os.getpid())
        return self._hwnd_cache

    def win_minimize(self):
        h = self._hwnd()
        if h:
            user32.ShowWindow(h, 6)                                                # SW_MINIMIZE
        return True

    def win_toggle_maximize(self):
        """Native maximise/restore. Maximised size is limited to the work area by _custom_frame's
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
        """The page reports whether it has unsaved changes (only when that flips)."""
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


def _read_studio_file() -> dict:
    try:
        with open(STUDIO_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_studio_file(data: dict):
    os.makedirs(paths.CONFIG_DIR, exist_ok=True)
    tmp = STUDIO_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, STUDIO_FILE)


def _main_window(title=TITLE, pid=None):
    """The largest visible top-level window with this exact title (optionally in process pid).
    pywebview also creates a tiny helper window with the same title, so FindWindow alone picks wrongly."""
    best, best_area = None, 0
    EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user32.EnumWindows.argtypes = [EnumProc, w.LPARAM]

    def visit(h, _):
        nonlocal best, best_area
        if not user32.IsWindowVisible(h):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf, 256)
        if buf.value != title:
            return True
        if pid is not None:
            p = w.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(p))
            if p.value != pid:
                return True
        r = w.RECT()
        user32.GetWindowRect(h, ctypes.byref(r))
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > best_area:
            best, best_area = h, area
        return True
    user32.EnumWindows(EnumProc(visit), 0)
    return best if best_area > 200 * 200 else None


def _on_closing(api):
    """pywebview 'closing' handler (runs synchronously on the UI thread; returning False cancels).
    Every way of closing (our button, Alt+F4, taskbar, WM_CLOSE) arrives here. With unsaved changes the
    close is cancelled and the page is asked to show its dialog. That request must run on another thread:
    calling into the page from inside this handler would deadlock the UI thread."""
    if api._allow_close or not api._dirty:
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
    Taken from _limit_maximise_to_work_area's tracker: GetWindowPlacement reports the size WinForms would
    restore to, which is one caption taller than the window really was."""
    try:
        st = _subclass.get(hwnd, (None, None, None))[2]
        if not st or not st["normal"]:
            return
        left, top, right, bottom = st["normal"]
        data = _read_studio_file()
        data["window"] = {"x": left, "y": top, "width": right - left, "height": bottom - top,
                          "maximized": st["zoomed"]}
        _write_studio_file(data)
    except Exception:
        pass


def _saved_window(min_w, min_h):
    """Last session's window as (x, y, width, height, maximized) in pixels, or None. Shrunk to fit its
    screen, and centred on the nearest screen when that monitor is gone or the header is out of reach."""
    s = _read_studio_file().get("window")
    try:
        x, y, wd, ht = (int(s[k]) for k in ("x", "y", "width", "height"))
        maxed = bool(s.get("maximized"))
    except (TypeError, KeyError, ValueError, AttributeError):
        return None

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]
    user32.MonitorFromRect.restype = w.HMONITOR
    user32.MonitorFromRect.argtypes = [ctypes.POINTER(w.RECT), w.DWORD]
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    mon = user32.MonitorFromRect(ctypes.byref(w.RECT(x, y, x + wd, y + ht)), 2)   # MONITOR_DEFAULTTONEAREST
    if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return None
    wa = mi.rcWork
    wd = min(max(wd, min_w), wa.right - wa.left)
    ht = min(max(ht, min_h), wa.bottom - wa.top)
    header_visible = min(x + wd, wa.right) - max(x, wa.left) >= 200 and wa.top <= y <= wa.bottom - 48
    if not header_visible:
        x = wa.left + (wa.right - wa.left - wd) // 2
        y = wa.top + (wa.bottom - wa.top - ht) // 2
    return x, y, wd, ht, maxed


def _work_area(hwnd) -> w.RECT:
    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]
    user32.MonitorFromWindow.restype = w.HMONITOR
    user32.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
    return mi.rcWork


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", w.POINT), ("ptMaxSize", w.POINT), ("ptMaxPosition", w.POINT),
                ("ptMinTrackSize", w.POINT), ("ptMaxTrackSize", w.POINT)]


_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_subclass = {}                     # keeps the callback and the original proc alive for the window's life


def _limit_maximise_to_work_area(hwnd):
    """Subclasses the window to answer WM_GETMINMAXINFO only. Without a caption Windows maximises over the
    whole monitor (taskbar included); this makes double-click, Win+Up, snap-to-top and our button all
    maximise to the work area, with the usual invisible-border overhang. Everything else passes through."""
    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    user32.GetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.SetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.CallWindowProcW.restype = _LRESULT
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    GWLP_WNDPROC, WM_GETMINMAXINFO, WM_WINDOWPOSCHANGED = -4, 0x0024, 0x0047
    WM_FIX_RESTORE = 0x8000 + 77
    if hwnd in _subclass:
        return
    original = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)
    # WinForms still believes the window has a caption, and on restore re-applies a size that is one caption
    # taller. So remember the last normal rectangle and put it back right after any restore.
    st = {"zoomed": bool(user32.IsZoomed(hwnd)), "normal": None, "pending": None}

    def proc(h, msg, wp, lp):
        if msg == WM_FIX_RESTORE:
            rc = st.pop("pending", None)
            st["pending"] = None
            if rc and not user32.IsZoomed(h) and not user32.IsIconic(h):
                user32.SetWindowPos(h, None, rc[0], rc[1], rc[2] - rc[0], rc[3] - rc[1], 0x0014)
            return 0
        r = user32.CallWindowProcW(original, h, msg, wp, lp)
        if msg == WM_WINDOWPOSCHANGED:
            zoomed, iconic = bool(user32.IsZoomed(h)), bool(user32.IsIconic(h))
            if st["zoomed"] and not zoomed and not iconic and st["normal"]:
                st["pending"] = st["normal"]
                user32.PostMessageW(h, WM_FIX_RESTORE, 0, 0)
            elif not zoomed and not iconic and not st["pending"]:
                rc = w.RECT()
                user32.GetWindowRect(h, ctypes.byref(rc))
                st["normal"] = (rc.left, rc.top, rc.right, rc.bottom)
            if not iconic:
                st["zoomed"] = zoomed
        elif msg == WM_GETMINMAXINFO:
            try:
                class MONITORINFO(ctypes.Structure):
                    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT),
                                ("dwFlags", w.DWORD)]
                user32.MonitorFromWindow.restype = w.HMONITOR
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                user32.GetMonitorInfoW(user32.MonitorFromWindow(h, 2), ctypes.byref(mi))
                b = user32.GetSystemMetrics(32) + user32.GetSystemMetrics(92)   # SIZEFRAME + PADDEDBORDER
                mm = _MINMAXINFO.from_address(lp)
                wa, mon = mi.rcWork, mi.rcMonitor
                mm.ptMaxPosition.x = wa.left - mon.left - b
                mm.ptMaxPosition.y = wa.top - mon.top - b
                mm.ptMaxSize.x = wa.right - wa.left + 2 * b
                mm.ptMaxSize.y = wa.bottom - wa.top + 2 * b
            except Exception:
                pass
        return r
    cb = _WNDPROC(proc)
    _subclass[hwnd] = (cb, original, st)
    user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(cb, ctypes.c_void_p))


def _custom_frame(title=TITLE, placement=None):
    """Removes the Windows title bar but keeps the resizable frame (native resize and Aero Snap), and
    themes the remaining 1 px border and corners. The page draws its own header (see index.html).
    placement: _saved_window()'s result, applied exactly (create_window only gets it to within a pixel).
    Plain Win32 only: touching window.native (a .NET Form) from pywebview's worker thread deadlocks."""
    try:
        hwnd = None
        for _ in range(100):                                                       # up to ~10 s for the window
            hwnd = _main_window(title, os.getpid())
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            return
        _limit_maximise_to_work_area(hwnd)
        GWL_STYLE, WS_CAPTION = -16, 0x00C00000
        WS_KEEP = 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000      # THICKFRAME SYSMENU MIN MAX boxes
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE, (style & ~WS_CAPTION) | WS_KEEP)
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
        for attr, val in ((20, 1),                       # immersive dark mode
                          (33, 2),                       # rounded corners
                          (34, 0x00352F2B)):             # border colour #2b2f35 (COLORREF is 0x00bbggrr)
            v = ctypes.c_int(val)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)  # FRAMECHANGED
        if placement:
            x, y, wd, ht, maxed = placement
            user32.SetWindowPos(hwnd, None, x, y, wd, ht, 0x0004 | 0x0010)             # NOZORDER NOACTIVATE
            if maxed:
                user32.ShowWindow(hwnd, 3)                                         # SW_MAXIMIZE
    except Exception:
        pass


def _enable_drag_regions():
    """Turns on WebView2 non-client region support, so CSS `app-region: drag` areas act as a real title bar
    (native move, Aero Snap, double-click). Patched into pywebview's own init hook, which runs on the UI
    thread once WebView2 is ready."""
    from webview.platforms import edgechromium
    original = edgechromium.EdgeChrome.on_webview_ready
    if getattr(original, "_radial_patched", False):
        return

    def on_webview_ready(self, sender, args):
        original(self, sender, args)
        try:
            sender.CoreWebView2.Settings.IsNonClientRegionSupportEnabled = True
        except Exception:
            pass
    on_webview_ready._radial_patched = True
    edgechromium.EdgeChrome.on_webview_ready = on_webview_ready


def main():
    _startup(f"Studio {VERSION} main()")
    import webview
    _startup("pywebview imported")
    mutex = CreateMutexW(None, False, STUDIO_MUTEX)
    if ctypes.get_last_error() == 183:                     # already open: bring it forward
        _startup("already open: bringing it forward")
        hwnd = _main_window(TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
        return 0
    try:                                                    # own taskbar identity and icon, not Python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    # pywebview makes the process system-DPI aware when it starts and scales sizes by that DPI. Doing it
    # first means the saved window pixels and the monitor checks use the same coordinates as the window.
    user32.SetProcessDPIAware()
    scale = user32.GetDpiForSystem() / 96
    min_size = (980, 640)
    placement = _saved_window(round(min_size[0] * scale), round(min_size[1] * scale))
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
    _enable_drag_regions()
    icon = paths.ICON if os.path.isfile(paths.ICON) else None
    webview.start(lambda: _custom_frame(placement=placement), debug="--debug" in sys.argv,
                  icon=icon)                                                  # _custom_frame: worker thread
    CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    sys.exit(main())
