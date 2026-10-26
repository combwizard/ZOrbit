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
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C          # noqa: E402
import brushes              # noqa: E402
import paths                # noqa: E402

DATA_DIR = paths.DATA_DIR
CONFIG_FILE = paths.ensure_config()
UI_INDEX = os.path.join(paths.UI_DIR, "index.html")
APP_MUTEX = "Local\\RadialMenuForZBrush"
STUDIO_MUTEX = "Local\\RadialMenuStudio"
TITLE = "Radial Menu Studio"
VERSION = paths.VERSION
APP_ID = "RadialMenu.Studio"           # taskbar identity, so the Studio groups under its own icon

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
        """Writes radial.json (previous version kept as radial.json.bak). The app re-reads it on the next
        open. Saves even with problems (the loader skips bad items) and reports them."""
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

    def preview_animation(self, cfg, menu_id, fps=30):
        """Open-animation frames as PNG data URLs (played back by the Studio), plus the frame interval."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None or menu_id not in loaded.menus:
            return {"frames": [], "interval_ms": 33, "problems": problems}
        import radiald
        from ring import Ring
        app = radiald.App(CONFIG_FILE)
        app.cfg = loaded
        frames = Ring.preview_frames(loaded.menus[menu_id], loaded.ring, app.icon_for, fps=int(fps))
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
        labels = {"user ZStartup/BrushPresets": "My Brushes", "install ZData/BrushPresets": "ZBrush",
                  "install Lightbox/Brushes": "Lightbox"}
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

    def win_close(self):
        h = self._hwnd()
        if h:
            user32.PostMessageW(h, 0x0010, 0, 0)                                    # WM_CLOSE
        return True


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
    _subclass[hwnd] = (cb, original)
    user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(cb, ctypes.c_void_p))


def _custom_frame(title=TITLE):
    """Removes the Windows title bar but keeps the resizable frame (native resize and Aero Snap), and
    themes the remaining 1 px border and corners. The page draws its own header (see index.html).
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
    import webview
    mutex = CreateMutexW(None, False, STUDIO_MUTEX)
    if ctypes.get_last_error() == 183:                     # already open: bring it forward
        hwnd = _main_window(TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
        return 0
    try:                                                    # own taskbar identity and icon, not Python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    api = Api()
    window = webview.create_window(TITLE, url=UI_INDEX, js_api=api, width=1320, height=860,
                                   min_size=(980, 640), background_color="#1b1c20", text_select=False)
    api._window = window
    _enable_drag_regions()
    icon = paths.ICON if os.path.isfile(paths.ICON) else None
    webview.start(_custom_frame, debug="--debug" in sys.argv, icon=icon)   # _custom_frame: worker thread
    CloseHandle(mutex)
    return 0


if __name__ == "__main__":
    sys.exit(main())
