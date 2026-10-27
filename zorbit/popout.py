"""ZOrbit brush browser popout: a small always-on-top window over ZBrush that lists the brush library, filtered by
tag, and selects the brush you pick in ZBrush through the background app.

A pywebview window (Windows' built-in Edge WebView2) showing studio_ui/popout.html, in its own process so the
hotkey can open it in a fraction of a second: the app starts it hidden a few seconds after launch ("pre-warm")
and from then on only asks it to show or hide.

  ZOrbit.exe --popout [--managed] [--show] [--tag KEY] [--zbrush-hwnd N]

  --managed       started by the app: exits by itself once the app is gone
  --show          show the window as soon as the page is up
  --tag KEY       ... filtered to this tag
  --zbrush-hwnd   the ZBrush window to hand the focus back to

Talks to the app with WM_COPYDATA (ids in radiald.py):
  popout -> ZOrbitControl     1   a pick: {"v": 1, "op": "pick", "kind": "brush", "name": ...}   result 1 taken, 0 refused
  app -> ZOrbitPopoutCtl     10   SHOW {"tag": key|null, "zbrush_hwnd": N, "toggle": bool}
  app -> ZOrbitPopoutCtl     12   QUIT

One instance at a time (Local\\ZOrbitPopout); a second launch passes its arguments on and exits.
The window is a tool window without a taskbar button. Unless pinned it hides when another window takes the
focus. Everything done to the window from other threads is plain Win32 or evaluate_js: touching window.native
(a .NET Form) off the UI thread deadlocks. Never imports studio.py (that pulls in the installer code).
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
SHOW_GRACE_S = 0.4                 # after a show, losing the focus for a moment is not a reason to hide
WM_ACTIVATE, WA_INACTIVE = 0x0006, 0
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
user32.GetWindowLongPtrW.restype = ctypes.c_void_p
user32.GetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_void_p
user32.SetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_void_p]
user32.CallWindowProcW.restype = ctypes.c_ssize_t
user32.CallWindowProcW.argtypes = [ctypes.c_void_p, w.HWND, w.UINT, w.WPARAM, w.LPARAM]
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


_state_lock = threading.RLock()       # window rectangle, pin and thumbnail size all read-modify-write popout.json


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
    """--popout [--managed] [--show] [--tag KEY] [--zbrush-hwnd N] [--debug]; an unreadable value is ignored."""
    o = {"managed": "--managed" in args, "show": "--show" in args, "tag": None, "zbrush": 0, "debug": "--debug" in args}
    for flag, key in (("--tag", "tag"), ("--zbrush-hwnd", "zbrush")):
        if flag in args and args.index(flag) + 1 < len(args):
            v = args[args.index(flag) + 1]
            if key == "zbrush":
                try:
                    o[key] = int(v)
                except ValueError:
                    pass
            elif v and not v.startswith("--"):
                o[key] = v
    return o


def _show_payload(tag, zbrush, toggle=False) -> bytes:
    return json.dumps({"tag": tag or None, "zbrush_hwnd": int(zbrush or 0), "toggle": bool(toggle)}).encode("utf-8")


class PopoutApi(webapi.LibraryApi, webapi.TagApi):
    """What the page calls. get_library, get_thumbs and the tag methods come from the mixins."""

    def __init__(self, pop):
        self._pop = pop          # underscore: pywebview must not expose (and crawl) it to JS

    def popout_get_state(self):
        """What the page needs before it draws: the pin, the thumbnail size, the tag it was started with."""
        st = _read_state()
        size = st.get("size")
        return {"pinned": self._pop.pinned, "size": size if isinstance(size, int) else None, "tag": self._pop.start_tag,
                "tags_path": radiald.tags_path()}

    def popout_pick(self, name):
        """Selects a brush in ZBrush: hides the window (stays up when pinned), then asks the app. {"ok": bool, "error"}."""
        return self._pop.pick(str(name or ""))

    def popout_hide(self):
        self._pop.hide(restore=True, why="page")
        return True

    def popout_set_pinned(self, flag):
        self._pop.set_pinned(bool(flag))
        return True

    def popout_set_size(self, px):
        """The thumbnail size the slider ended on."""
        try:
            _update_state(size=max(84, min(220, int(px))))
        except (TypeError, ValueError):
            return False
        return True

    def popout_log(self, msg):
        """A line from the page (script errors) into popout.log."""
        _log("page: " + str(msg)[:500])
        return True


class Popout:
    """The window and everything that happens to it: show, hide, pick, the control window the app talks to."""

    def __init__(self, opts):
        self.opts = opts
        self.start_tag = opts["tag"]
        self.pinned = bool(_read_state().get("pinned"))
        self.window = None
        self.hwnd = 0
        self.ctl = 0
        self.ready = False                   # page loaded and frame set: only then can the window be shown
        self.quitting = False
        self.prev_fg = 0                     # the window to hand the focus back to
        self.shown_at = 0.0
        self._pending = None                 # (tag, zbrush hwnd) to show once ready
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
            self._work.put((self.quit, ("the app asked",)))
            return 1
        if cds.dwData != radiald.COPYDATA_SHOW or not cds.lpData or not 0 < cds.cbData <= 4096:
            return 0
        try:
            msg = json.loads(ctypes.string_at(cds.lpData, cds.cbData).decode("utf-8"))
            tag = msg.get("tag")
            tag = tag if isinstance(tag, str) and tag else None
            zb = msg.get("zbrush_hwnd")
            zb = zb if isinstance(zb, int) and not isinstance(zb, bool) else 0
            toggle = bool(msg.get("toggle"))
        except (ValueError, AttributeError):
            _log("SHOW refused: unreadable payload")
            return 0
        self._work.put((self.request_show, (tag, zb, toggle)))
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
        style = winframe.user32.GetWindowLongW(hwnd, -16)                      # GWL_STYLE: custom_frame only ever adds
        winframe.user32.SetWindowLongW(hwnd, -16, style & ~0x00010000)         # styles, so the maximise box goes here
        self._watch_activation(self.hwnd)

    def on_loaded(self):
        _log("page loaded")
        self._loaded.set()

    def worker(self):
        """webview.start's function: frame first, then wait for the page, then take whatever was asked meanwhile."""
        try:
            winframe.custom_frame(TITLE, placement=None, pid=os.getpid(), topmost=True, toolwindow=True,
                                  maximizable=False, include_hidden=True, on_hwnd=self.on_hwnd)
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
                self.request_show(pend[0], pend[1], False)
            if self.opts["managed"]:
                threading.Thread(target=self._watch_app, daemon=True, name="popout-managed").start()
        except Exception as e:
            _log(f"worker failed: {e!r}")

    def _watch_app(self):
        """--managed: the app owns us; when its control window has been gone for two looks in a row it has quit."""
        misses = 0
        while not self.quitting:
            time.sleep(POLL_S)
            if W.find_message_window(APP_CLASS):
                misses = 0
                continue
            misses += 1
            _log(f"the app's control window ({APP_CLASS}) is missing ({misses}/{POLL_MISSES})")
            if misses >= POLL_MISSES:
                self.quit("the app is gone")
                return

    def visible(self) -> bool:
        return bool(self.hwnd and user32.IsWindowVisible(self.hwnd))

    def _holds_foreground(self) -> bool:
        fg = W.GetForegroundWindow()
        return bool(fg) and W.window_pid(fg) == os.getpid()

    def _rect(self):
        r = w.RECT()
        return r if user32.GetWindowRect(self.hwnd, ctypes.byref(r)) else None

    def _save_rect(self):
        r = self._rect()
        if r and r.right - r.left > 100 and r.bottom - r.top > 100:
            _update_state(window={"x": r.left, "y": r.top, "width": r.right - r.left, "height": r.bottom - r.top,
                                  "maximized": False})

    def _place(self, zb):
        """(x, y, w, h) for a window that is about to appear: where it was last time, else centred on the screen ZBrush is on."""
        r = self._rect()
        scale = user32.GetDpiForSystem() / 96 if hasattr(user32, "GetDpiForSystem") else 1.0
        minw, minh = round(MIN_SIZE[0] * scale), round(MIN_SIZE[1] * scale)
        saved = winframe.saved_window(_read_state().get("window"), minw, minh)
        if saved:
            return saved[:4]
        wd, ht = (r.right - r.left, r.bottom - r.top) if r else (round(START_SIZE[0] * scale), round(START_SIZE[1] * scale))
        wa = winframe.work_area(zb or self.prev_fg or W.GetForegroundWindow() or 0)
        return wa.left + (wa.right - wa.left - wd) // 2, wa.top + (wa.bottom - wa.top - ht) // 2, wd, ht

    def request_show(self, tag, zb, toggle):
        """The app asks for the window (SHOW), or the first launch does (--show)."""
        with self._lock:
            if not self.ready:                         # still starting: it shows itself when it is up; a second press cancels
                self._pending = None if (toggle and self._pending) else (tag, zb)
                _log(f"SHOW while starting: pending {self._pending}")
                return
            if toggle and self.visible():
                _log("SHOW toggle: hiding")
                self.hide(restore=True, why="toggle")
                return
            self.show(tag, zb)

    def show(self, tag=None, zb=0, reset=True):
        """Shows the window over everything, takes the focus and puts the cursor in the search box. reset: also
        tell the page to start afresh (empty search, this tag only)."""
        with self._lock:
            if not self.hwnd or self.quitting:
                return
            was_visible = self.visible()
            fg = W.GetForegroundWindow()
            if zb and W.IsWindow(zb):
                self.prev_fg = zb
            elif fg and W.window_pid(fg) != os.getpid():
                self.prev_fg = int(fg)
            if reset:
                try:
                    self.window.evaluate_js("window.__popoutShow && __popoutShow(" + json.dumps({"tag": tag or None}) + ")")
                except Exception as e:
                    _log(f"__popoutShow failed: {e!r}")
            self.shown_at = time.monotonic()
            if was_visible:
                W.SetWindowPos(self.hwnd, W.HWND_TOPMOST, 0, 0, 0, 0, W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_SHOWWINDOW)
            else:                                      # placed while hidden, then shown through pywebview: the form has to
                x, y, wd, ht = self._place(zb)         # know it is visible, or the web view inside stays "hidden" and paints nothing
                W.SetWindowPos(self.hwnd, W.HWND_TOPMOST, x, y, wd, ht, W.SWP_NOACTIVATE)
                self.window.show()
            # Windows lets only the process that got the last input take the foreground; a no-op key from us
            # (0xE8 is an unassigned virtual key, so nothing acts on it) counts as that input.
            W.send_keys([(0xE8, False), (0xE8, True)])
            got = winframe.force_foreground(self.hwnd)
            _log(f"shown (tag={tag}, prev_fg={self.prev_fg}, was_visible={was_visible}, foreground={got})")
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

    def hide(self, restore=True, why=""):
        """Hides the window. restore: give the focus back to ZBrush first (allowed while we hold it); a window that
        lost the focus to something else just goes."""
        with self._lock:
            if not self.visible():
                return False
            self._save_rect()
            if restore and self.prev_fg and W.IsWindow(self.prev_fg) and self._holds_foreground():
                user32.SetForegroundWindow(self.prev_fg)
            self.window.hide()
            W.nudge_mouse()
            _log(f"hidden ({why})")
            return True

    def set_pinned(self, flag):
        with self._lock:
            self.pinned = flag
            _update_state(pinned=flag)
            _log(f"pinned: {flag}")

    def pick(self, name) -> dict:
        """The page picked a brush. The window gets out of the way first (pinned: only the focus goes back to ZBrush),
        because the app selects the brush with ZBrush in front."""
        if not name:
            return {"ok": False, "error": "No brush to select."}
        with self._lock:
            was_visible = self.visible()
            if self.pinned:
                if self.prev_fg and W.IsWindow(self.prev_fg):
                    user32.SetForegroundWindow(self.prev_fg)
            else:
                self.hide(restore=True, why="pick")
        app = W.find_message_window(APP_CLASS)
        payload = json.dumps({"v": 1, "op": "pick", "kind": "brush", "name": name}).encode("utf-8")
        r = W.send_copydata(app, radiald.COPYDATA_PICK, payload) if app else None
        _log(f"pick {name!r}: app window {app}, result {r}")
        if r == 1:
            return {"ok": True}
        if was_visible and not self.pinned:
            self.show(reset=False)                    # nothing was selected: bring the window back with its search intact
        return {"ok": False, "error": "ZOrbit is not running" if r is None else "ZOrbit did not take that brush. Is it up to date?"}

    def quit(self, why=""):
        with self._lock:
            if self.quitting:
                return
            self.quitting = True
            _log(f"quitting ({why})")
            if self.visible():
                self._save_rect()
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
        """pywebview 'closing' (UI thread; False cancels): Alt+F4 and the like only hide the window."""
        if self.quitting:
            return None
        if self.visible():          # hidden from another thread: this one is the UI thread, which pywebview's hide() needs free
            threading.Thread(target=self.hide, kwargs={"restore": False, "why": "close requested"}, daemon=True).start()
        return False

    # --- losing the focus ---------------------------------------------------------------------------
    def _watch_activation(self, hwnd):
        """Subclasses the window to see WM_ACTIVATE (everything is passed on). Runs on the UI thread, so it only starts
        a short timer: the check itself looks at who has the foreground, because a click inside the web view also
        moves the activation between windows of this process."""
        GWLP_WNDPROC = -4
        original = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)

        def proc(h, msg, wp, lp):
            r = user32.CallWindowProcW(original, h, msg, wp, lp)
            if msg == WM_ACTIVATE and (wp & 0xFFFF) == WA_INACTIVE:
                threading.Timer(0.05, self._check_inactive, args=(0,)).start()
            return r
        cb = W.WNDPROC(proc)
        self._refs.append(cb)
        user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(cb, ctypes.c_void_p))

    def _check_inactive(self, tries):
        if self.pinned or self.quitting or not self.visible():
            return
        fg = W.GetForegroundWindow()
        if fg and (W.window_pid(fg) == os.getpid() or _owned_by(fg, self.hwnd)):
            return                                      # the focus is still ours (inside the web view, or a popup of it)
        wait = SHOW_GRACE_S - (time.monotonic() - self.shown_at)
        if wait > 0 or (not fg and tries < 2):          # just shown, or between two windows: look again
            threading.Timer(max(wait, 0) + 0.05, self._check_inactive, args=(tries + 1,)).start()
            return
        self.hide(restore=False, why="lost the focus")


def _owned_by(hwnd, owner) -> bool:
    """hwnd is a popup owned by our window: the web view's own context menu or an IME candidate list belong to
    another process (msedgewebview2.exe), so by pid alone they would look like the user leaving."""
    try:
        root = ctypes.windll.user32.GetAncestor(w.HWND(hwnd), 3)          # GA_ROOTOWNER
        return bool(root) and int(root) == int(owner)
    except Exception:
        return False


def _forward(opts) -> int:
    """A second launch: hand our arguments to the running popout, which may still be starting up."""
    if not opts["show"]:
        _log("a popout is already running; nothing to pass on")
        return 0
    for _ in range(30):                                 # the first one creates its control window within a moment of starting
        hwnd = W.find_message_window(radiald.POPOUT_CLASS)
        if hwnd:
            r = W.send_copydata(hwnd, radiald.COPYDATA_SHOW, _show_payload(opts["tag"], opts["zbrush"]))
            _log(f"a popout is already running: SHOW forwarded to {hwnd} (tag={opts['tag']}): result {r}")
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
        pop._pending = (opts["tag"], opts["zbrush"])
    import webview
    _log("pywebview imported")
    try:                                                 # own identity, not Python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    user32.SetProcessDPIAware()                          # as pywebview does: sizes below are logical pixels
    api = PopoutApi(pop)
    window = webview.create_window(TITLE, url=UI_PAGE, js_api=api, width=START_SIZE[0], height=START_SIZE[1],
                                   min_size=MIN_SIZE, hidden=True, on_top=True, background_color="#1b1c20",
                                   text_select=False)
    pop.window = window
    window.events.closing += pop.on_closing
    window.events.shown += lambda: _log("window shown")
    window.events.loaded += pop.on_loaded
    winframe.enable_drag_regions()
    icon = paths.ICON if os.path.isfile(paths.ICON) else None
    webview.start(pop.worker, debug=opts["debug"], icon=icon)
    pop.stop_ctl()
    kernel32.CloseHandle(mutex)
    _log("popout stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
