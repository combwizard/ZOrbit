"""ZOrbit browser popout: a window with the brush, alpha, material and texture libraries (one tab each),
filtered by tag, that selects the item you pick in ZBrush through the background app. A normal app window: it
has a taskbar button, snaps and maximises like any other, and stays open until the user closes it. Nothing hides
it but the close button and Alt+F4.

A pywebview window (Windows' built-in Edge WebView2) showing studio_ui/popout.html, in its own process so the
hotkey can open it in a fraction of a second: the app starts it hidden a few seconds after launch ("pre-warm")
and from then on only asks it to show. It does not need ZBrush or the app: the Studio, the tray menu and a
Start menu shortcut open it too, and it stays up when the app quits.

  ZOrbit.exe --popout [--managed] [--show] [--tag KEY] [--kind KIND] [--zbrush-hwnd N]

  --managed       started by the app: exits by itself once the app is gone, unless its window is up. A managed
                  popout whose window the user closes only hides it (the app can show it again at once); one that
                  is not managed, or has lost its app, quits when its window is closed
  --show          show the window as soon as the page is up
  --tag KEY       ... filtered to this tag
  --kind KIND     ... on this tab: brush, alpha, material or texture (default: the tab it was last on, popout.json
                  "kind")
  --zbrush-hwnd   the ZBrush window to hand the focus back to

Talks to the app with WM_COPYDATA (ids in radiald.py):
  popout -> ZOrbitControl     1   a pick: {"v": 1, "op": "pick", "kind": "brush|alpha|material|texture", "name": ...}
                                      result 1 taken, 0 refused
  app -> ZOrbitPopoutCtl     10   SHOW {"tag": key|null, "kind": kind|null, "zbrush_hwnd": N, "toggle": bool}
  app -> ZOrbitPopoutCtl     12   QUIT (ignored while the window is up)

SHOW: a hidden window appears (afresh: no search, this tag only, on the given tab); one that is visible comes to the front; one that
is already in front hands the keyboard back to ZBrush when asked to toggle (the hotkey), but never closes. A pick
and Esc hand the keyboard back to ZBrush too. Keep on top (popout.json "on_top", on by default) is the pin button in the header.
One instance at a time (Local\\ZOrbitPopout); a second launch passes its arguments on and exits.
Everything done to the window from other threads is plain Win32 or evaluate_js: touching window.native
(a .NET Form) off the UI thread deadlocks, and so does hiding or showing the window, or calling into the page,
from inside a js_api call. Never imports studio.py (that pulls in the installer code).
"""
import ctypes
import ctypes.wintypes as w
import json
import os
import queue
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C          # noqa: E402
import fsutil               # noqa: E402
import paths                # noqa: E402
import radiald              # noqa: E402
import webapi               # noqa: E402
import win32 as W           # noqa: E402
import winframe             # noqa: E402

TITLE = "ZOrbit Browser"
APP_ID = "ZOrbit.Browser"
MUTEX = "Local\\ZOrbitPopout"
UI_PAGE = os.path.join(paths.UI_DIR, "popout.html")
LOG_FILE = os.path.join(paths.DATA_DIR, "popout.log")
STATE_FILE = os.environ.get("ZORBIT_POPOUT_FILE") or paths.POPOUT_FILE      # the variable is for tests
APP_CLASS = os.environ.get("ZORBIT_POPOUT_APP_CLASS") or "ZOrbitControl"    # ... and so is this one
START_SIZE = (780, 560)            # logical pixels, until the user has resized it
MIN_SIZE = (560, 380)
POLL_S = 3.0                       # --managed: how often to look for the app, and
POLL_MISSES = 2                    # ... how many misses in a row mean it has quit
WM_APP_STOP = W.WM_APP + 1         # control window: leave the message loop

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
user32.IsWindowVisible.argtypes = [w.HWND]
user32.SetForegroundWindow.argtypes = [w.HWND]
user32.SetFocus.argtypes = [w.HWND]
user32.SetFocus.restype = w.HWND
user32.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
user32.GetWindowThreadProcessId.restype = w.DWORD
user32.AttachThreadInput.argtypes = [w.DWORD, w.DWORD, w.BOOL]
user32.IsIconic.argtypes = [w.HWND]
user32.IsZoomed.argtypes = [w.HWND]
user32.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
SW_MAXIMIZE, SW_RESTORE = 3, 9
kernel32.GetCurrentThreadId.restype = w.DWORD
kernel32.CreateMutexW.restype, kernel32.CreateMutexW.argtypes = w.HANDLE, [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
kernel32.CloseHandle.argtypes = [w.HANDLE]

_T0 = None
_log_lock = threading.Lock()


def _log(msg):
    """One line in popout.log: seconds since this process was created, then msg. Shows where a slow start
    spends its time."""
    global _T0
    try:
        with _log_lock:
            if _T0 is None:
                _T0 = W.process_created(os.getpid()) or time.time()
                msg += f"; started by {W.launch_chain()}; cwd {os.getcwd()}"
            os.makedirs(paths.DATA_DIR, exist_ok=True)
            if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 200_000:
                os.replace(LOG_FILE, LOG_FILE + ".old")
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                now = time.time()
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}.{int(now * 1000) % 1000:03d} "
                        f"+{now - _T0:6.2f} s  [{os.getpid()}] {msg}\n")
    except Exception:
        pass


_state_lock = threading.RLock()       # window rectangle, keep on top and thumbnail size all read-modify-write popout.json


def _read_state() -> dict:
    with _state_lock:
        try:
            with open(STATE_FILE, encoding="utf-8-sig") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}


def _update_state(**changes):
    with _state_lock:
        data = _read_state()
        data.update(changes)
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            fsutil.write_atomic(STATE_FILE, json.dumps(data, indent=2))
        except OSError as e:
            _log(f"could not save {STATE_FILE}: {e!r}")


def _parse(args) -> dict:
    """--popout [--managed] [--show] [--tag KEY] [--kind KIND] [--zbrush-hwnd N] [--debug]; an unreadable value
    is ignored."""
    o = {"managed": "--managed" in args, "show": "--show" in args, "tag": None, "kind": None, "zbrush": 0,
         "debug": "--debug" in args}
    for flag, key in (("--tag", "tag"), ("--kind", "kind"), ("--zbrush-hwnd", "zbrush")):
        if flag in args and args.index(flag) + 1 < len(args):
            v = args[args.index(flag) + 1]
            if key == "zbrush":
                try:
                    o[key] = int(v)
                except ValueError:
                    pass
            elif key == "kind":
                if v in C.ASSET_KINDS:
                    o[key] = v
            elif v and not v.startswith("--"):
                o[key] = v
    return o


def _show_payload(tag, zbrush, toggle=False, kind=None) -> bytes:
    return json.dumps({"tag": tag or None, "kind": kind or None, "zbrush_hwnd": int(zbrush or 0),
                       "toggle": bool(toggle)}).encode("utf-8")


TARGET_EXE = os.environ.get("ZORBIT_POPOUT_TARGET_EXE") or "zbrush.exe"   # the variable is for tests


def _is_target(hwnd) -> bool:
    """hwnd is a live window of ZBrush (the app the picks are for)."""
    try:
        return bool(hwnd) and bool(W.IsWindow(hwnd)) and \
            os.path.basename(W.process_image(W.window_pid(hwnd))).lower() == TARGET_EXE
    except Exception:
        return False


def _find_target() -> int:
    """The largest visible top-level ZBrush window, or 0."""
    best, area = 0, 0
    EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

    def visit(h, _):
        nonlocal best, area
        if user32.IsWindowVisible(h) and _is_target(h):
            r = w.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            a = (r.right - r.left) * (r.bottom - r.top)
            if a > area:
                best, area = int(h), a
        return True
    user32.EnumWindows(EnumProc(visit), 0)
    return best


class PopoutApi(webapi.LibraryApi, webapi.TagApi):
    """What the page calls. get_library, get_thumbs and the tag methods come from the mixins."""

    def __init__(self, pop):
        self._pop = pop          # underscore: pywebview must not expose (and crawl) it to JS

    def popout_get_state(self):
        """What the page needs before it draws: keep on top, the thumbnail size, which side the folders and tags
        column is on and whether it is shown, the tag and the tab (kind) it was started with, else the tab it was
        last on."""
        st = _read_state()
        size = st.get("size")
        kind = self._pop.start_kind or st.get("kind")
        side = "right" if st.get("side") == "right" else "left"
        return {"on_top": self._pop.on_top, "size": size if isinstance(size, int) else None, "side": side,
                "column": st.get("column") != "hidden",
                "tag": self._pop.start_tag,
                "kind": kind if kind in C.ASSET_KINDS else "brush", "tags_path": radiald.tags_path()}

    def popout_pick(self, name, kind="brush"):
        """Selects a brush, alpha, material or texture in ZBrush: hands the focus back to ZBrush, then asks the
        app. The window stays open. {"ok": bool, "error"}."""
        return self._pop.pick(str(name or ""), kind)

    def popout_hide(self):
        """The close button. Answered at once: the window is closed on another thread, because hiding it from
        inside this call would wait for the UI thread."""
        threading.Thread(target=self._pop.close, kwargs={"why": "close button"}, daemon=True).start()
        return True

    def popout_release_focus(self):
        """Esc with nothing left to clear: the keyboard goes back to ZBrush. The window stays open."""
        self._pop.release_focus()
        return True

    def popout_set_on_top(self, flag):
        self._pop.set_on_top(bool(flag))
        return True

    def popout_set_size(self, px):
        """The thumbnail size the slider ended on."""
        try:
            _update_state(size=max(84, min(220, int(px))))
        except (TypeError, ValueError):
            return False
        return True

    def popout_set_side(self, side):
        """Which side of the window the folders and tags column is on: "left" (the default) or "right"."""
        if side not in ("left", "right"):
            return False
        _update_state(side=side)
        return True

    def popout_set_column(self, shown):
        """Whether the folders and tags column is shown (popout.json "column": "shown" or "hidden")."""
        _update_state(column="shown" if shown else "hidden")
        return True

    def popout_set_kind(self, kind):
        """The tab the user ended on, shown again the next time the window starts."""
        if kind not in C.ASSET_KINDS:
            return False
        _update_state(kind=kind)
        return True

    def popout_log(self, msg):
        """A line from the page (script errors) into popout.log."""
        _log("page: " + str(msg)[:500])
        return True


class Popout:
    """The window and everything that happens to it: show, close, pick, the control window the app talks to."""

    def __init__(self, opts):
        self.opts = opts
        self.start_tag = opts["tag"]
        self.start_kind = opts["kind"]
        st = _read_state()
        if isinstance(st.get("on_top"), bool):
            self.on_top = st["on_top"]
        elif "pinned" in st:                  # the setting's earlier name; read once, then on_top is what is saved
            self.on_top = bool(st["pinned"])
        else:
            self.on_top = True
        self.managed = opts["managed"]       # the app owns us; false once it is gone, or when it never was
        self.window = None
        self.hwnd = 0
        self.ctl = 0
        self.ready = False                   # page loaded and frame set: only then can the window be shown
        self.quitting = False
        self.prev_fg = 0                     # the window to hand the focus back to
        self._placed = False                 # the window has had its first position
        self._was_max = False                # it was maximised when it was last hidden
        self._pending = None                 # (tag, zbrush hwnd, kind) to show once ready
        self._lock = threading.RLock()       # show, hide and pick run one at a time
        self._loaded = threading.Event()
        self._ctl_up = threading.Event()
        self._work = queue.SimpleQueue()     # what the control window asks for, done off its thread
        self._refs = []                      # callbacks that must outlive the calls

    # --- control window: how the app reaches us -------------------------------------------------------
    def start_ctl(self):
        threading.Thread(target=self._ctl_main, daemon=True, name="popout-ctl").start()
        threading.Thread(target=self._work_main, daemon=True, name="popout-work").start()
        self._ctl_up.wait(3)

    def _ctl_main(self):
        try:
            proc = W.WNDPROC(self._ctl_proc)
            self._refs.append(proc)
            wc = W.WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(W.WNDCLASSEXW)
            wc.lpfnWndProc = proc
            wc.hInstance = W.GetModuleHandleW(None)
            wc.lpszClassName = radiald.POPOUT_CLASS
            if not W.RegisterClassExW(ctypes.byref(wc)):
                raise ctypes.WinError(ctypes.get_last_error())
            self.ctl = W.CreateWindowExW(0, radiald.POPOUT_CLASS, "ZOrbit popout control", 0, 0, 0, 0, 0,
                                         W.HWND_MESSAGE, None, wc.hInstance, None)
            if not self.ctl:
                raise ctypes.WinError(ctypes.get_last_error())
            _log(f"control window {self.ctl} up")
        except Exception as e:
            _log(f"control window failed: {e!r}")
            self._ctl_up.set()
            return
        self._ctl_up.set()
        msg = w.MSG()
        while W.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            W.TranslateMessage(ctypes.byref(msg))
            W.DispatchMessageW(ctypes.byref(msg))

    def _ctl_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == W.WM_COPYDATA:
                return self._on_copydata(lparam)
            if msg == WM_APP_STOP:
                W.DestroyWindow(hwnd)
                return 0
            if msg == W.WM_DESTROY:
                W.PostQuitMessage(0)
                return 0
        except Exception as e:
            _log(f"control error: {e!r}")
            return 0
        return W.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_copydata(self, lparam) -> int:
        """SHOW and QUIT from the app. Answered at once (the sender waits); the work happens on another thread."""
        cds = W.COPYDATASTRUCT.from_address(lparam)
        if cds.dwData == radiald.COPYDATA_QUIT:
            self._work.put((self.app_gone, ("the app asked",)))
            return 1
        if cds.dwData != radiald.COPYDATA_SHOW or not cds.lpData or not 0 < cds.cbData <= 4096:
            return 0
        try:
            msg = json.loads(ctypes.string_at(cds.lpData, cds.cbData).decode("utf-8"))
            tag = msg.get("tag")
            tag = tag if isinstance(tag, str) and tag else None
            kind = msg.get("kind")
            kind = kind if kind in C.ASSET_KINDS else None
            zb = msg.get("zbrush_hwnd")
            zb = zb if isinstance(zb, int) and not isinstance(zb, bool) else 0
            toggle = bool(msg.get("toggle"))
        except (ValueError, AttributeError):
            _log("SHOW refused: unreadable payload")
            return 0
        self._work.put((self.request_show, (tag, zb, toggle, kind)))
        return 1

    def _work_main(self):
        while True:
            fn, args = self._work.get()
            try:
                fn(*args)
            except Exception as e:
                _log(f"{getattr(fn, '__name__', fn)} failed: {e!r}")

    def stop_ctl(self):
        if self.ctl:
            W.PostMessageW(self.ctl, WM_APP_STOP, 0, 0)

    # --- the window ---------------------------------------------------------------------------------
    def on_hwnd(self, hwnd):
        """From custom_frame, on the worker thread, before the frame is changed."""
        self.hwnd = int(hwnd)
        winframe.limit_maximise_to_work_area(hwnd)           # maximise stops at the taskbar; tracks the normal rectangle

    def on_loaded(self):
        _log("page loaded")
        self._loaded.set()

    def worker(self):
        """webview.start's function: frame first, then wait for the page, then take whatever was asked meanwhile."""
        try:
            winframe.custom_frame(TITLE, placement=None, pid=os.getpid(), topmost=self.on_top, toolwindow=False,
                                  maximizable=True, include_hidden=True, on_hwnd=self.on_hwnd)
            if not self.hwnd:
                _log("the popout window was not found; giving up")
                self.quit("no window")
                return
            _log(f"frame set on {self.hwnd}")
            if not self._loaded.wait(60):
                _log("the page did not load within 60 s")
            with self._lock:
                self.ready = True
                pend, self._pending = self._pending, None
            _log(f"ready; pending show: {pend}")
            if pend:
                self.request_show(pend[0], pend[1], False, pend[2])
            if self.managed:
                threading.Thread(target=self._watch_app, daemon=True, name="popout-managed").start()
        except Exception as e:
            _log(f"worker failed: {e!r}")

    def _watch_app(self):
        """--managed: the app owns us; when its control window has been gone for two looks in a row it has quit."""
        misses = 0
        while not self.quitting and self.managed:
            time.sleep(POLL_S)
            if W.find_message_window(APP_CLASS):
                misses = 0
                continue
            misses += 1
            _log(f"the app's control window ({APP_CLASS}) is missing ({misses}/{POLL_MISSES})")
            if misses >= POLL_MISSES:
                self.app_gone("the app is gone")
                return

    def app_gone(self, why):
        """The app quit (or told us to). A hidden window has no reason to stay; one that is up does not depend
        on the app, so it stays, no longer managed: closing it then ends the process."""
        with self._lock:
            if self.visible() and not self.quitting:
                _log("app gone; staying open (the window is up)")
                self.managed = False
                return
        self.quit(why)

    def visible(self) -> bool:
        return bool(self.hwnd and user32.IsWindowVisible(self.hwnd))

    def _holds_foreground(self) -> bool:
        fg = W.GetForegroundWindow()
        return bool(fg) and W.window_pid(fg) == os.getpid()

    def _rect(self):
        r = w.RECT()
        return r if user32.GetWindowRect(self.hwnd, ctypes.byref(r)) else None

    def _save_placement(self):
        """popout.json "window": the normal (restored) rectangle from the tracker and whether it is maximised,
        in the shape studio.json keeps its own."""
        rec = winframe.placement_record(self.hwnd)
        if not rec:
            r = self._rect()
            if not r:
                return
            rec = {"x": r.left, "y": r.top, "width": r.right - r.left, "height": r.bottom - r.top, "maximized": False}
        if rec["width"] > 100 and rec["height"] > 100:
            _update_state(window=rec)

    def _place(self, zb):
        """(x, y, w, h, maximised) for a window that is about to appear for the first time: where it was last time,
        else centred on the screen ZBrush is on."""
        r = self._rect()
        scale = user32.GetDpiForSystem() / 96 if hasattr(user32, "GetDpiForSystem") else 1.0
        minw, minh = round(MIN_SIZE[0] * scale), round(MIN_SIZE[1] * scale)
        saved = winframe.saved_window(_read_state().get("window"), minw, minh)
        if saved:
            return saved
        wd, ht = (r.right - r.left, r.bottom - r.top) if r else (round(START_SIZE[0] * scale), round(START_SIZE[1] * scale))
        wa = winframe.work_area(zb or self.prev_fg or W.GetForegroundWindow() or 0)
        return wa.left + (wa.right - wa.left - wd) // 2, wa.top + (wa.bottom - wa.top - ht) // 2, wd, ht, False

    def _z_order(self):
        return winframe.HWND_TOPMOST if self.on_top else winframe.HWND_NOTOPMOST

    def request_show(self, tag, zb, toggle, kind=None):
        """The app asks for the window (SHOW), or the first launch does (--show). Never closes it: a window that is
        hidden appears, one that is up comes to the front, and one that is already in front hands the keyboard
        back to ZBrush when asked to toggle (the hotkey)."""
        with self._lock:
            if not self.ready:                         # still starting: it shows itself when it is up
                self._pending = (tag, zb, kind)
                _log(f"SHOW while starting: pending {self._pending}")
                return
            if not self.visible():
                self.show(tag, zb, kind=kind)
            elif self._holds_foreground():
                self._remember_target(zb)
                if toggle:
                    _log("SHOW toggle: in front; the keyboard goes back to ZBrush")
                    self.release_focus()
                else:
                    self.show(tag, zb, reset=False, kind=kind)    # already in front: the search box gets the cursor
            else:
                self.show(tag, zb, reset=False, kind=kind)

    def _remember_target(self, zb=0):
        """The window the focus goes back to: the ZBrush window the app named, else ZBrush in front, else the one
        remembered, else any ZBrush window. Opened from the Studio, the tray or the Start menu, the window in front
        is not ZBrush, and handing a pick to it would lose the pick."""
        fg = W.GetForegroundWindow()
        for cand in (zb, int(fg) if fg else 0, self.prev_fg):
            if _is_target(cand):
                self.prev_fg = int(cand)
                return
        self.prev_fg = _find_target()

    def _back_to_target(self) -> bool:
        """Gives ZBrush the foreground (looked up again if the remembered window is gone) and wakes the pen."""
        if not _is_target(self.prev_fg):
            self.prev_fg = _find_target()
        if not self.prev_fg:
            return False
        user32.SetForegroundWindow(self.prev_fg)
        W.nudge_mouse()                                # a zero move: the pen and cursor tracking wake up in ZBrush
        return True

    def show(self, tag=None, zb=0, reset=True, kind=None):
        """Shows the window, takes the focus and puts the cursor in the search box. reset: also tell the page to
        start afresh (empty search, this tag only). Without it the page is left as it is, except that a tag
        or tab (kind) given is applied."""
        with self._lock:
            if not self.hwnd or self.quitting:
                return
            was_visible = self.visible()
            self._remember_target(zb)
            if reset or tag or kind:
                try:
                    arg = json.dumps({"tag": tag or None, "kind": kind or None, "reset": bool(reset)})
                    self.window.evaluate_js("window.__popoutShow && __popoutShow(" + arg + ")")
                except Exception as e:
                    _log(f"__popoutShow failed: {e!r}")
            if was_visible:
                if user32.IsIconic(self.hwnd):
                    user32.ShowWindow(self.hwnd, SW_RESTORE)
                winframe.user32.SetWindowPos(self.hwnd, self._z_order(), 0, 0, 0, 0,
                                             W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_SHOWWINDOW)
            else:                                      # shown through pywebview: the form has to know it is visible, or the
                maxed = self._was_max                  # web view inside stays "hidden" and paints nothing
                if not self._placed:                   # the first time: where it was last session. After that it keeps its place
                    x, y, wd, ht, maxed = self._place(zb)
                    winframe.user32.SetWindowPos(self.hwnd, self._z_order(), x, y, wd, ht, W.SWP_NOACTIVATE)
                    self._placed = True
                else:
                    winframe.user32.SetWindowPos(self.hwnd, self._z_order(), 0, 0, 0, 0,
                                                 W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE)
                self.window.show()
                winframe.user32.SetWindowPos(self.hwnd, self._z_order(), 0, 0, 0, 0,       # Show() may re-apply a stale
                                             W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE)  # TopMost: ours wins
                if maxed and not user32.IsZoomed(self.hwnd):
                    user32.ShowWindow(self.hwnd, SW_MAXIMIZE)
            # Windows lets only the process that got the last input take the foreground; a no-op key from us
            # (0xE8 is an unassigned virtual key, so nothing acts on it) counts as that input.
            W.send_keys([(0xE8, False), (0xE8, True)])
            got = winframe.force_foreground(self.hwnd)
            _log(f"shown (tag={tag}, kind={kind}, reset={reset}, prev_fg={self.prev_fg}, was_visible={was_visible}, foreground={got})")
            self._focus_page()

    def _focus_page(self):
        """The search box gets the cursor: the page does it, and when the web view itself has no focus yet (the
        form has it, not the browser inside) the browser window is given it with Win32."""
        has = False
        try:
            has = bool(self.window.evaluate_js("window.__popoutFocus ? __popoutFocus() : false"))
        except Exception as e:
            _log(f"__popoutFocus failed: {e!r}")
        if has:
            return
        found = []
        Enum = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

        def visit(h, _):
            buf = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, buf, 64)
            if buf.value.startswith("Chrome_WidgetWin"):
                found.append(h)
            return True
        user32.EnumChildWindows.argtypes = [w.HWND, Enum, w.LPARAM]
        user32.EnumChildWindows(self.hwnd, Enum(visit), 0)
        if not found:
            _log("no web view child window to focus")
            return
        child = found[0]
        me = kernel32.GetCurrentThreadId()
        tid = user32.GetWindowThreadProcessId(child, None)
        attached = bool(tid and tid != me and user32.AttachThreadInput(me, tid, True))
        try:
            user32.SetFocus(child)
        finally:
            if attached:
                user32.AttachThreadInput(me, tid, False)
        try:
            has = bool(self.window.evaluate_js("window.__popoutFocus ? __popoutFocus() : false"))
        except Exception:
            pass
        _log(f"web view focused with Win32 ({len(found)} child windows): page has focus {has}")

    def release_focus(self):
        """The keyboard goes back to the window that had it before (ZBrush). The window stays open. Allowed because
        this process holds the foreground when the user presses Esc or the hotkey in it."""
        if self._back_to_target():
            _log(f"focus handed back to {self.prev_fg}")
        else:
            _log("no ZBrush window to hand the focus back to")

    def close(self, why=""):
        """The user closed the window (the X button, Alt+F4, the taskbar). It is hidden, and kept for the app to
        show again when the app started it; a popout that is on its own has nothing to wait for and ends."""
        self.hide(restore=True, why=why)
        if not self.managed and not self.quitting:
            self.quit("closed by the user")

    def hide(self, restore=True, why=""):
        """Hides the window. restore: give the focus back to ZBrush first (allowed while we hold it); a window that
        lost the focus to something else just goes."""
        with self._lock:
            if not self.visible():
                return False
            self._save_placement()
            self._was_max = bool(user32.IsZoomed(self.hwnd))
            if restore and _is_target(self.prev_fg) and self._holds_foreground():
                user32.SetForegroundWindow(self.prev_fg)
            self.window.hide()
            W.nudge_mouse()
            _log(f"hidden ({why})")
            return True

    def set_on_top(self, flag):
        with self._lock:
            self.on_top = flag
            _update_state(on_top=flag)
            if self.hwnd:
                winframe.user32.SetWindowPos(self.hwnd, self._z_order(), 0, 0, 0, 0,
                                             W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE)
        # The form keeps its own TopMost (set once at creation) and may put it back when it is shown; show() sets
        # ours again after that. Never window.on_top: pywebview sets the form's TopMost on the calling thread, which
        # holds the GIL while the UI thread needs it for winframe's window procedure, and both hang.
        _log(f"keep on top: {flag}")

    def pick(self, name, kind="brush") -> dict:
        """The page picked a brush, alpha, material or texture. The window stays where it is; the focus goes back
        to ZBrush, because the app selects the item with ZBrush in front. Runs inside a js_api call: no show, hide
        or evaluate_js here."""
        if kind not in C.ASSET_KINDS:
            return {"ok": False, "error": f"Unknown kind {kind!r}."}
        if not name:
            return {"ok": False, "error": f"No {kind} to select."}
        with self._lock:
            self._back_to_target()
        app = W.find_message_window(APP_CLASS)
        payload = json.dumps({"v": 1, "op": "pick", "kind": kind, "name": name}).encode("utf-8")
        r = W.send_copydata(app, radiald.COPYDATA_PICK, payload) if app else None
        _log(f"pick {kind} {name!r}: app window {app}, result {r}")
        if r == 1:
            return {"ok": True}
        if not app:                         # the app owns the pick window and runs only while ZBrush does
            return {"ok": False, "error": "ZOrbit is not running. It starts and stops with ZBrush."}
        if r is None:                       # the window is there but did not answer within the timeout
            return {"ok": False, "error": "ZOrbit did not answer. Try again in a moment."}
        return {"ok": False, "error": f"ZOrbit did not take that {kind}. Is it up to date?"}

    def quit(self, why=""):
        with self._lock:
            if self.quitting:
                return
            self.quitting = True
            _log(f"quitting ({why})")
            if self.visible():
                self._save_placement()
        self.stop_ctl()

        def kill():                                   # the window should close by itself; this makes sure the process ends
            time.sleep(5)
            _log("still here after 5 s; exiting")
            os._exit(0)
        threading.Thread(target=kill, daemon=True).start()
        if self.window is None:
            os._exit(0)
        try:
            self.window.destroy()
        except Exception as e:
            _log(f"destroy failed: {e!r}")
            os._exit(0)

    def on_closing(self):
        """pywebview 'closing' (UI thread; False cancels): Alt+F4 and the like only close the window, which is hidden
        (or ends the process: see close)."""
        if self.quitting:
            return None
        threading.Thread(target=self.close, kwargs={"why": "close requested"}, daemon=True).start()   # hiding needs the UI thread free
        return False


def _forward(opts) -> int:
    """A second launch: hand our arguments to the running popout, which may still be starting up."""
    if not opts["show"]:
        _log("a popout is already running; nothing to pass on")
        return 0
    for _ in range(30):                                 # the first one creates its control window within a moment of starting
        hwnd = W.find_message_window(radiald.POPOUT_CLASS)
        if hwnd:
            r = W.send_copydata(hwnd, radiald.COPYDATA_SHOW,
                                _show_payload(opts["tag"], opts["zbrush"], kind=opts["kind"]))
            _log(f"a popout is already running: SHOW forwarded to {hwnd} (tag={opts['tag']}, "
                 f"kind={opts['kind']}): result {r}")
            return 0
        time.sleep(0.1)
    _log("a popout is already running, but its control window did not appear")
    return 1


def main(args) -> int:
    opts = _parse(args)
    _log(f"Popout {paths.VERSION} main(): {args}")
    mutex = kernel32.CreateMutexW(None, False, MUTEX)
    if ctypes.get_last_error() == W.ERROR_ALREADY_EXISTS:
        return _forward(opts)
    pop = Popout(opts)
    pop.start_ctl()
    if opts["show"]:
        pop._pending = (opts["tag"], opts["zbrush"], opts["kind"])
    import webview
    _log("pywebview imported")
    try:                                                 # own identity, not Python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    user32.SetProcessDPIAware()                          # as pywebview does: sizes below are logical pixels
    api = PopoutApi(pop)
    window = webview.create_window(TITLE, url=UI_PAGE, js_api=api, width=START_SIZE[0], height=START_SIZE[1],
                                   min_size=MIN_SIZE, hidden=True, on_top=pop.on_top, background_color="#1a1b1e",
                                   text_select=False)
    pop.window = window
    window.events.closing += pop.on_closing
    window.events.shown += lambda: _log("window shown")
    window.events.loaded += pop.on_loaded
    winframe.enable_drag_regions()
    icon = getattr(paths, "BROWSER_ICON", paths.ICON)           # its own mark, not the app's
    if not os.path.isfile(icon):
        icon = paths.ICON if os.path.isfile(paths.ICON) else None
    webview.start(pop.worker, debug=opts["debug"], icon=icon)
    pop.stop_ctl()
    kernel32.CloseHandle(mutex)
    _log("popout stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
