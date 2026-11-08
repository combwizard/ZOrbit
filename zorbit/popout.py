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
                  A managed popout that sits hidden for browser.quit_after_minutes (radial.json, off by default) quits
                  by itself with exit code radiald.POPOUT_EXIT_IDLE, which is how the app tells that from a failure
  --show          show the window as soon as the page is up
  --tag KEY       ... filtered to this tag
  --kind KIND     ... on this tab: brush, alpha, material or texture (default: the tab it was last on, popout.json
                  "kind")
  --zbrush-hwnd   the ZBrush window to hand the focus back to

Talks to the app with WM_COPYDATA (ids in radiald.py):
  popout -> ZOrbitControl     1   a pick: {"v": 1, "op": "pick", "kind": "brush|alpha|material|texture", "name": ...}
                                      result 1 taken, 0 refused
  app -> ZOrbitPopoutCtl     10   SHOW {"tag": key|null, "kind": kind|null, "zbrush_hwnd": N, "toggle": bool}
                                      result 1 taken, 0 refused, 2 (radiald.SHOW_QUITTING) the popout is quitting after
                                      sitting unused: start another, which waits for it to end and then shows itself
  app -> ZOrbitPopoutCtl     12   QUIT (ignored while the browser is up; a managed strip quits with the app)
  Studio -> ZOrbitPopoutCtl  13   THEME, no payload: look at the theme now (the poll still catches the other causes)

SHOW: a hidden window appears (afresh: no search, this tag only, on the given tab); one that is visible comes to the front; one that
is already in front hands the keyboard back to ZBrush when asked to toggle (the hotkey), but never closes. A pick
and Esc hand the keyboard back to ZBrush too. Keep on top (popout.json "on_top", on by default) is the pin button in the header.
The strip: the same window can instead be a small strip of one tab's favourites that stays on top of everything,
has no taskbar button and never takes the keyboard (WS_EX_NOACTIVATE, shown with SW_SHOWNOACTIVATE). popout.json
"strip_on" makes it the window's resting state: it shows by itself once the page is up, and the browser's close button
goes back to it. Its own settings are under "strip" (see strip_state). One page draws both: __popoutShow takes the
mode, and in strip mode answers the strip's size, which the window is fitted to (winframe.set_fitted; the page asks
again through popout_strip_size when its content changes). A SHOW always means the browser. A click in the strip picks
at once: ZBrush still has the foreground, so nothing is handed back. The name of the thumbnail under the mouse is a
toast.show_beside pill on the control window's thread, which can draw outside the window.
While a ZBrush runs and another program has the foreground the strip is hidden (strip_tick, every THEME_POLL_S; ShowWindow
only, strip_on and the mode stay), and comes back with ZBrush; with none running it stays. A managed popout's strip goes with
the app (QUIT, or the app's window gone) and strip_on stays, so the next pre-warm brings it back; one started by hand keeps it.
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
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C          # noqa: E402
import fsutil               # noqa: E402
import paths                # noqa: E402
import profiles             # noqa: E402
import radiald              # noqa: E402
import theme                # noqa: E402
import webapi               # noqa: E402
import webview2              # noqa: E402
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
THEME_POLL_S = 0.5                 # how often a visible window looks for a new theme (a few hundred bytes read)
POLL_S = 3.0                       # --managed: how often to look for the app, and
POLL_MISSES = 2                    # ... how many misses in a row mean it has quit
WM_APP_STOP = W.WM_APP + 1         # control window: leave the message loop
WM_APP_PILL = W.WM_APP + 2         # control window: put up or take down the strip's name pill, or a note (see _pill)
WM_APP_PEN = W.WM_APP + 3          # control window: start (wParam 1) or stop (0) watching which device moves the cursor
STRIP_ORIENTS = ("vertical", "horizontal")
STRIP_START = (64, 420)            # logical pixels: a strip's size until the page has measured it
STRIP_MARGIN = 8                   # logical pixels between a strip's first place and the edge of ZBrush's window
ZBRUSH_PIDS_TTL_S = 3.0            # how long the list of ZBrush's process ids is kept while the strip watches the foreground
STRIP_HIDE_AFTER_S = 1.0           # how long another program must have been in front before the strip steps aside
FAV = "favourite"                  # the Favourites tag (tags.FAVOURITE)
GWL_EXSTYLE, WS_EX_APPWINDOW = -20, 0x00040000

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
user32.GetDpiForWindow.argtypes = [w.HWND]
user32.GetDpiForWindow.restype = w.UINT
SW_HIDE, SW_MAXIMIZE, SW_RESTORE = 0, 3, 9
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
        data = fsutil.read_json_for_update(STATE_FILE)
        if data is None:                  # there but unreadable now: writing would lose the window, size and side
            _log(f"{STATE_FILE} could not be read; not saved this time")
            return
        data.update(changes)
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            fsutil.write_atomic(STATE_FILE, json.dumps(data, indent=2))
        except OSError as e:
            _log(f"could not save {STATE_FILE}: {e!r}")


def strip_state(st) -> dict:
    """The strip's settings in popout.json, read as the other keys are (a value that is not what it should be
    counts as missing): "strip_on" (bool, the strip is the window's resting state) and "strip": {"orient":
    "vertical" or "horizontal", "kind": its own tab, "window": {"x", "y"} where its corner was last (screen
    pixels), "wrap": bool, every favourite on show instead of the first ones and a +N button, "fold": bool, folded
    to its grip and buttons}. Returns {"on", "orient", "kind", "window": (x, y) or None, "wrap", "fold"}."""
    st = st if isinstance(st, dict) else {}
    s = st.get("strip") if isinstance(st.get("strip"), dict) else {}
    win, place = s.get("window"), None
    if isinstance(win, dict):
        x, y = win.get("x"), win.get("y")
        if all(isinstance(v, int) and not isinstance(v, bool) for v in (x, y)):
            place = (x, y)
    return {"on": st.get("strip_on") is True,
            "orient": s.get("orient") if s.get("orient") in STRIP_ORIENTS else "vertical",
            "kind": s.get("kind") if s.get("kind") in C.ASSET_KINDS else "brush",
            "window": place, "wrap": s.get("wrap") is True, "fold": s.get("fold") is True}


def strip_wanted(fg_pid, zbrush_pids, own_pid):
    """Should the strip be on show, given the process that owns the foreground window? True: yes. False: another program
    is in front while ZBrush runs, so the strip steps aside. None: no foreground window at this moment (a switch is under
    way), leave it as it is. With no ZBrush running at all it is True: a strip started by hand has nothing to follow.
    Compared by process id only, since a ZBrush running as administrator cannot be looked into. The popout's own
    process counts as ZBrush's: the strip's name pill and menu are its windows."""
    if not zbrush_pids:
        return True
    if not fg_pid:
        return None
    return fg_pid == own_pid or fg_pid in zbrush_pids


def pointer_source(flags, dx, dy, extra, device, pen_devices):
    """Which kind of device moved the cursor, from one raw mouse report: "pen", "mouse", or None when the report says
    nothing (a button alone, a move of nothing, ZOrbit's own nudge, an absolute move no device made).

    Why: while a Wintab program (ZBrush) has the foreground, a Wacom pen moves the cursor as a mouse, so the press that
    brings the browser to the front reaches the page as a mouse and picks up a card instead of scrolling. The page cannot
    tell it from a mouse; this can. Windows' own mouse made from pen or touch carries PEN_SIGNATURE in its extra
    information. A tablet driver that moves the cursor itself sends absolute moves, from its own device (and its buttons
    come from that device too: pen_devices, the devices seen moving absolutely). A mouse moves relatively. An absolute
    move with no device was sent by a program (remote desktop, automation), not a pen."""
    if (extra & W.PEN_SIGNATURE_MASK) == W.PEN_SIGNATURE:
        return "pen"
    if extra == W.OWN_INPUT_MARKER:
        return None
    if flags & W.MOUSE_MOVE_ABSOLUTE:
        return "pen" if device else None
    if device and device in pen_devices:
        return "pen"
    return "mouse" if dx or dy else None


def _update_strip(**changes):
    """Read-modify-write of popout.json "strip": the keys not named stay as they are."""
    with _state_lock:
        cur = _read_state().get("strip")
        cur = dict(cur) if isinstance(cur, dict) else {}
        cur.update(changes)
        _update_state(strip=cur)


def keep_inside(x, y, wd, ht, work) -> tuple:
    """(x, y) moved so a wd x ht rectangle there lies inside work (left, top, right, bottom); the top-left wins when it
    is larger than work."""
    wl, wt, wr, wb = work
    return max(wl, min(x, wr - wd)), max(wt, min(y, wb - ht))


def strip_first_place(orient, size, target, work, margin) -> tuple:
    """Where a strip of size (w, h) goes the first time, with no place saved: against the left edge of the ZBrush
    window target (left, top, right, bottom), centred on it top to bottom (vertical), or against its top, centred
    across (horizontal); margin pixels in from the edge. target None (no ZBrush window known): the work area. The
    part of target off the work area does not count (a maximised window reaches a few pixels past it), and the
    answer is kept inside work. Screen pixels, (x, y)."""
    wl, wt, wr, wb = work
    l, t, r, b = target or work
    l, t, r, b = max(l, wl), max(t, wt), min(r, wr), min(b, wb)
    if r <= l or b <= t:                                # ZBrush is on another monitor than work, or minimised
        l, t, r, b = work
    wd, ht = size
    if orient == "horizontal":
        x, y = (l + r - wd) // 2, t + margin
    else:
        x, y = l + margin, (t + b - ht) // 2
    return keep_inside(x, y, wd, ht, work)


def fit_size(fit, scale) -> tuple:
    """The window size, in physical pixels, for what the page measured ({"w", "h"}, logical pixels; see
    __popoutShow and popout_strip_size). A size the page could not have meant is kept to a sane range; something
    unreadable is STRIP_START."""
    def num(v, dflt):
        return max(16.0, min(4000.0, float(v))) if isinstance(v, (int, float)) and not isinstance(v, bool) else dflt
    fit = fit if isinstance(fit, dict) else {}
    return round(num(fit.get("w"), STRIP_START[0]) * scale), round(num(fit.get("h"), STRIP_START[1]) * scale)


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

    def merge_tags(self, src, dst):
        """Merges the tags, then points the ring items that used src at dst in radial.json (this window holds no
        menus to do it in, as Studio does). The answer adds ring_items (how many changed) and, when radial.json
        could not be updated, ring_error."""
        prof = profiles.active() if profiles.enabled() else None     # None: a pinned menus file (tests, --check)
        res = super().merge_tags(src, dst)
        if res.get("ok") and profiles.tags_file(prof) != webapi.store().path:
            res["ring_items"] = 0          # switched between the two steps: radial.json is not the one merged
            res["ring_error"] = "The profile changed during the merge, so the ring items were not updated."
        elif res.get("ok"):
            try:
                n, problem = webapi.retarget_ring({src: dst}, profile=prof)
            except Exception as e:          # the merge is done: never turn it into a failure
                n, problem = 0, f"radial.json could not be updated: {e}"
                _log(f"retarget_ring failed: {e!r}")
            res["ring_items"] = n
            if problem:
                res["ring_error"] = problem
        return res

    def popout_get_state(self):
        """What the page needs before it draws: keep on top, the thumbnail size, which side the folders and tags
        column is on and whether it is shown, the tag and the tab (kind) it was started with, else the tab it was
        last on."""
        st = _read_state()
        size = st.get("size")
        kind = self._pop.start_kind or st.get("kind")
        side = "right" if st.get("side") == "right" else "left"
        setting, sig = theme.read_setting(), theme.signature()
        effective = sig[0]
        look = theme.preset(effective)                     # Match ZBrush: the scheme's tokens for the page
        with self._pop._lock:                              # show() reads and writes it under the same lock
            self._pop._theme_seen = (setting, sig)         # show() tells the page only when this changes
        ss = strip_state(st)
        return {"on_top": self._pop.on_top, "size": size if isinstance(size, int) else None, "side": side,
                "column": st.get("column") != "hidden", "mode": self._pop.mode,
                "strip": {"on": self._pop.strip_on, "orient": ss["orient"], "kind": ss["kind"], "wrap": ss["wrap"],
                          "fold": ss["fold"]},
                "tag": self._pop.start_tag,
                "kind": kind if kind in C.ASSET_KINDS else "brush", "tags_path": profiles.tags_file(),
                "profile": profiles.active(), "theme": setting, "theme_effective": effective,
                "theme_base": look["base"], "theme_tokens": look["web"]}

    def popout_theme_changed(self, effective):
        """The page saw Windows change its app colour mode (Follow Windows): the frame follows. True."""
        if effective in theme.EFFECTIVE:
            self._pop.apply_frame_theme(theme.preset(effective)["window"])
        return True

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

    # --- the strip. Showing, hiding and resizing the window wait for the UI thread, so they are queued for the work
    # thread and the call is answered at once.
    def popout_strip_show(self):
        """The browser's strip button: the strip becomes the resting state and takes the window's place."""
        self._pop._work.put((self._pop.strip_from_browser, ()))
        return True

    def popout_strip_hide(self):
        """Hide strip in the strip's menu: no strip from now on, and the window goes."""
        self._pop._work.put((self._pop.hide_strip, ()))
        return True

    def popout_open_browser(self, fav=False):
        """Open browser in the strip: the full browser, on the strip's tab (in Favourites when fav). The strip stays
        on: the browser's close button brings it back."""
        kind = strip_state(_read_state())["kind"]
        self._pop._work.put((self._pop.open_browser, (FAV if fav else None, 0, kind, True, "Open browser")))
        return True

    def popout_strip_set(self, changes):
        """The strip's orient, kind (its tab), wrap (all favourites on show) and fold, any of them, saved. The page
        draws the change itself and then asks for the new size. The strip's settings as strip_state reads them."""
        return self._pop.strip_set(changes)

    def popout_strip_size(self, w, h):
        """The strip's page measured itself (logical pixels) after a change (more favourites, another tab or
        orientation, the menu open): the window is fitted to w x h."""
        self._pop._work.put((self._pop.fit_strip, ({"w": w, "h": h},)))
        return True

    def popout_strip_hover(self, seq, name=None, rect=None, side="right"):
        """The mouse is over a thumbnail of the strip (rect: [left, top, right, bottom] in the page), or over none
        (name None). seq orders the calls, which can arrive out of order."""
        self._pop.hover(seq, name, rect, side)
        return True

    def popout_strip_note(self, text):
        """A message from the strip's page, which has no room for its own toasts: shown near the cursor."""
        self._pop.note(str(text or "")[:300])
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
        self.exit_code = 0                   # of the process: radiald.POPOUT_EXIT_IDLE after an idle quit
        self._now = time.monotonic           # the clock of the idle quit (a test moves its own)
        self._idle_lock = threading.Lock()   # the idle quit's decision and a SHOW arriving meet here, never both
        self._hidden_at = None if opts.get("show") else self._now()   # when the window was last hidden (or we started
        #                                      hidden); None while it is up or about to be
        self._idle_minutes = 0               # browser.quit_after_minutes as last read from radial.json
        self._idle_closing = False           # decided to quit unused: a SHOW is answered "quitting"
        self.window = None
        self.hwnd = 0
        self.ctl = 0
        self.ready = False                   # page loaded and frame set: only then can the window be shown
        self.quitting = False
        self.prev_fg = 0                     # the window to hand the focus back to
        self._placed = False                 # the window has had its first position
        self._was_max = False                # it was maximised when it was last hidden
        self.session_ending = False          # Windows is shutting down, restarting or signing out: let the window close
        self._pending = None                 # (tag, zbrush hwnd, kind) to show once ready
        self._lock = threading.RLock()       # show, hide and pick run one at a time
        self._loaded = threading.Event()
        self._ctl_up = threading.Event()
        self._work = queue.SimpleQueue()     # what the control window asks for, done off its thread
        self._refs = []                      # callbacks that must outlive the calls
        self._theme_seen = None              # (setting, theme.signature()) the page was last given
        self.strip_on = strip_state(st)["on"]   # the strip is the window's resting state (popout.json "strip_on")
        self.mode = "browser"                # what the window is now: "browser" or "strip"
        self._page_strip = False             # the page was last told to draw the strip: show() must tell it otherwise
        self._app_window = False             # the window had WS_EX_APPWINDOW before it became the strip
        self._strip_home = None              # (x, y): where the strip's corner belongs; a larger size (its menu open by the
        #                                      right edge of the screen) may push it back onto the screen for a while
        self._pill_lock = threading.Lock()
        self._pill = None                    # what the control window shows next: ("name", text, rect, side), ("note", text), ("off",)
        self._pill_seq = 0                   # the newest hover call taken
        self._shows_taken = 0                # SHOWs taken from the app so far: _first_show sees one arrive while it waits
        self._fg_hidden = False              # the strip is up (mode "strip") but hidden because another program is in front
        self._fg_away_since = None           # when the foreground was first seen away from ZBrush (strip_tick's grace)
        self._zb_pids = (None, [])           # (when read, ZBrush's process ids): the strip's foreground watch, see _zbrush_pids
        self._pen_wanted = False             # the browser is up: the control window should watch raw mouse input (_pen_check)
        self._pen_devices = set()            # raw input devices seen moving the cursor absolutely: a tablet's (pointer_source)
        self._pen_last = None                # "pen" or "mouse": what moved the cursor last (control window thread)
        self._pen_told = None                # what the page was last told (__popoutPen); None: nothing yet, or a new page
        self._pen_queued = False             # a _tell_pen is waiting in the work queue
        self._pen_logged = False             # popout.log has said once that a pen was seen

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
            if msg == WM_APP_PILL:
                self._show_pill()
                return 0
            if msg == W.WM_INPUT:
                self._on_raw_mouse(lparam)             # and DefWindowProc below, which frees the input
            elif msg == WM_APP_PEN:
                self._pen_watch(bool(wparam))
                return 0
            if msg == W.WM_DESTROY:
                W.PostQuitMessage(0)
                return 0
        except Exception as e:
            _log(f"control error: {e!r}")
            return 0
        return W.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_copydata(self, lparam) -> int:
        """SHOW and QUIT from the app, THEME from Studio. Answered at once (the sender waits); the work happens on another thread."""
        cds = W.COPYDATASTRUCT.from_address(lparam)
        if cds.dwData == radiald.COPYDATA_QUIT:
            self._work.put((self.app_gone, ("the app asked",)))
            return 1
        if cds.dwData == radiald.COPYDATA_THEME:       # Studio saved a theme: look now, not at the next poll
            self._work.put((self.theme_tick, ()))
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
        with self._idle_lock:
            if self._idle_closing:                     # going: the app starts a new one rather than lose this press
                _log("SHOW while quitting unused: answered 'quitting'")
                return radiald.SHOW_QUITTING
            self._hidden_at = None                     # asked for: no idle quit before it is hidden again
            self._shows_taken += 1
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

    # --- pen or mouse: which moved the cursor last (see pointer_source) ---------------------------------
    def _pen_check(self):
        """Watch raw mouse input while the browser is up, and only then: every move anywhere is a message to this
        process. Asked after a show and at each theme poll; the control window's thread does the (un)registering."""
        want = bool(self.ready and not self.quitting and self.mode == "browser" and self.visible())
        if want != self._pen_wanted and self.ctl:
            self._pen_wanted = want
            W.PostMessageW(self.ctl, WM_APP_PEN, 1 if want else 0, 0)

    def _pen_watch(self, on):
        """Control window thread: raw mouse input on or off."""
        ok = W.watch_raw_mouse(self.ctl, on)
        if on:
            self._pen_last = None                      # the first move after this is told again, whatever it is
        if not ok:
            _log(f"raw mouse input could not be turned {'on' if on else 'off'}: {ctypes.get_last_error()}")

    def _on_raw_mouse(self, lparam):
        """Control window thread, for every mouse report while the browser is up: kept short."""
        r = W.read_raw_mouse(lparam)
        if not r:
            return
        flags, dx, dy, extra, device = r
        src = pointer_source(flags, dx, dy, extra, device, self._pen_devices)
        if flags & W.MOUSE_MOVE_ABSOLUTE and device:
            self._pen_devices.add(device)
        if src is None or src == self._pen_last:
            return
        self._pen_last = src
        if not self._pen_queued:
            self._pen_queued = True
            self._work.put((self._tell_pen, ()))

    def _tell_pen(self):
        """Work thread: the page learns whether the pen moved the cursor last (window.__popoutPen)."""
        self._pen_queued = False
        pen = self._pen_last == "pen"
        if pen == self._pen_told or not self.window:
            return
        if pen and not self._pen_logged:
            self._pen_logged = True
            _log("a pen moved the cursor: a press it makes while another program is in front scrolls the grid")
        try:
            self.window.evaluate_js(f"window.__popoutPen && __popoutPen({'true' if pen else 'false'})")
            self._pen_told = pen
        except Exception as e:
            _log(f"__popoutPen failed: {e!r}")

    # --- the window ---------------------------------------------------------------------------------
    def on_hwnd(self, hwnd):
        """From custom_frame, on the worker thread, before the frame is changed."""
        self.hwnd = int(hwnd)
        # draws without Windows' frame, resizes by its own border; sees Windows ending the session
        winframe.install_frame(hwnd, on_query_end=self.on_query_end, on_end=self.on_end_session, on_moved=self.on_moved)

    def on_moved(self):
        """WM_EXITSIZEMOVE (UI thread): the user has dragged the window. The strip's place is saved at once."""
        if self.mode == "strip":
            self._work.put((self._save_strip_place, (True,)))

    def on_query_end(self):
        """WM_QUERYENDSESSION (UI thread): the window must not veto it, as on_closing does for the close button."""
        if not self.session_ending:
            _log("Windows is ending the session; the window will close")
        self.session_ending = True

    def on_end_session(self, ending):
        """WM_ENDSESSION (UI thread). ending: the session really ends, else something cancelled it. Saves the
        window and goes: Windows stops the process soon after this returns, and it must not need the page."""
        if not ending:
            _log("the session end was cancelled")
            self.session_ending = False
            return
        self.session_ending = True
        self.quitting = True
        try:
            if self.visible():
                self._save_placement()
        except Exception as e:
            _log(f"could not save the window at session end: {e!r}")
        _log("session ended; exiting")
        threading.Timer(2.0, os._exit, args=(0,)).start()       # WinForms is closing the form; this is the backstop

    def on_loaded(self):
        _log("page loaded")
        self._pen_told = self._pen_last = None         # a new page knows nothing yet: the next move tells it
        self._loaded.set()

    def worker(self):
        """webview.start's function: frame first, then wait for the page, then take whatever was asked meanwhile."""
        try:
            winframe.custom_frame(TITLE, placement=None, pid=os.getpid(), topmost=self.on_top, toolwindow=False,
                                  maximizable=True, include_hidden=True, on_hwnd=self.on_hwnd,
                                  theme=theme.preset(theme.current())["window"])
            if not self.hwnd:
                _log("the popout window was not found; giving up")
                self.quit("no window")
                return
            _log(f"frame set on {self.hwnd}")
            if not self._loaded.wait(60):
                _log("the page did not load within 60 s")
            if winframe.frame_problem(self.hwnd):
                _log(f"the window's resize border could not be set up: {winframe.frame_problem(self.hwnd)}")
            with self._lock:
                self.ready = True
                pend, self._pending = self._pending, None
                with self._idle_lock:
                    taken = self._shows_taken      # read with ready: a SHOW from here on counts as "meanwhile"
            _log(f"ready; pending show: {pend}")
            self._first_show(pend, taken)
            if self.managed:
                threading.Thread(target=self._watch_app, daemon=True, name="popout-managed").start()
            threading.Thread(target=self._watch_theme, daemon=True, name="popout-theme").start()
        except Exception as e:
            _log(f"worker failed: {e!r}")

    def _first_show(self, pend, taken=None):
        """Once ready: the browser that was asked for while starting (--show, or a SHOW), else the strip when it is the
        resting state, up by itself and leaving the keyboard where it is; else nothing (a hidden pre-warm). taken is
        the SHOW count when ready was set; a SHOW after it means the browser is on its way."""
        if pend:
            self.request_show(pend[0], pend[1], False, pend[2])
        elif self.strip_on:
            if taken is None:
                with self._idle_lock:
                    taken = self._shows_taken
            self._wait_booted()                        # a SHOW (the browser hotkey) can arrive meanwhile: ready is true already
            with self._lock:
                with self._idle_lock:
                    asked = self._shows_taken != taken
                if self.visible() or asked:            # the browser is up or on its way: the strip must not take its place
                    _log(f"the start-up strip is skipped: {'a SHOW was taken' if asked else 'the window is up'}")
                    return
                self.show_strip("start")

    def _wait_booted(self, timeout_s=5.0):
        """Waits (up to timeout_s) for the page to have drawn itself, so the strip can be measured before it shows."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                if self.window.evaluate_js("!!window.__popoutBooted"):
                    return True
            except Exception:
                pass
            time.sleep(0.1)
        _log("the page did not draw itself in time; the strip is measured once it does")
        return False

    def _watch_theme(self):
        """While the window is up, a theme picked in Studio (or Windows' colour mode, or a new stored ZBrush scheme)
        reaches it within THEME_POLL_S, so Studio's Theme card can be tried with the browser open beside it. A theme
        picked in Studio also sends COPYDATA_THEME, which makes the same look at once; the poll stays for Windows'
        colour mode and a new ZBrush scheme."""
        while not self.quitting:
            time.sleep(THEME_POLL_S)
            try:
                self.theme_tick()
            except Exception as e:                 # never let a bad read end the watch
                _log(f"theme check failed: {e!r}")
            try:
                self.strip_tick()
            except Exception as e:
                _log(f"strip foreground check failed: {e!r}")
            try:
                self._pen_check()
            except Exception as e:
                _log(f"pen watch check failed: {e!r}")

    def theme_tick(self):
        """One look at the theme: the same sync show() does, for a visible window only (a hidden one is synced when
        it is shown)."""
        with self._lock:
            if self.ready and not self.quitting and self.visible():
                self._sync_theme()

    def _zbrush_pids(self, fresh=False) -> list:
        """Process ids of the running ZBrushes, kept ZBRUSH_PIDS_TTL_S (a snapshot of every process each half second is
        wasteful); fresh: read now."""
        now = self._now()
        at, pids = self._zb_pids
        if fresh or at is None or now - at >= ZBRUSH_PIDS_TTL_S:
            try:
                pids = W.pids_named(TARGET_EXE)
            except Exception as e:
                _log(f"could not list ZBrush's processes: {e!r}")
                pids = []
            self._zb_pids = (now, pids)
        return pids

    def strip_tick(self):
        """One look at the foreground, for the strip: while another program is in front and a ZBrush runs, the strip is
        hidden (ShowWindow, nothing else changes: strip_on stays, and the mode is still the strip); when ZBrush has the
        foreground again it comes back, without taking it. Not the user's Hide strip: that turns the strip off."""
        if not self.ready or self.quitting or self.mode != "strip":
            return
        fg = W.GetForegroundWindow()
        fg_pid = W.window_pid(fg) if fg else 0
        zpids = self._zbrush_pids()
        want = strip_wanted(fg_pid, zpids, os.getpid())
        if want is False and not self._fg_hidden:
            zpids = self._zbrush_pids(fresh=True)      # a ZBrush started since the list was read is not "another program"
            want = strip_wanted(fg_pid, zpids, os.getpid())
        if want is None:
            return
        if want:
            self._fg_away_since = None
        else:                                         # the taskbar, Alt+Tab and a quick glance elsewhere pass through
            if self._fg_away_since is None:           # here without the strip blinking: it hides after a short grace
                self._fg_away_since = self._now()
            if self._now() - self._fg_away_since < STRIP_HIDE_AFTER_S:
                return
        with self._lock:
            if self.mode != "strip" or self.quitting:
                return
            if not want and not self._fg_hidden and self.visible():
                self._fg_hidden = True
                self._pill_off()
                user32.ShowWindow(self.hwnd, SW_HIDE)
                _log(f"strip hidden: the foreground is process {fg_pid}, not ZBrush")
            elif want and self._fg_hidden:
                self._fg_hidden = False
                user32.ShowWindow(self.hwnd, W.SW_SHOWNOACTIVATE)
                winframe.user32.SetWindowPos(self.hwnd, winframe.HWND_TOPMOST, 0, 0, 0, 0,
                                             W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE)
                _log("strip shown again: ZBrush has the foreground" if zpids else "strip shown again: no ZBrush is running")

    def _watch_app(self):
        """--managed: the app owns us; when its control window has been gone for two looks in a row it has quit."""
        misses = 0
        while not self.quitting and self.managed:
            time.sleep(POLL_S)
            try:
                self.idle_tick()
            except Exception as e:                 # never let a bad read end the watch
                _log(f"idle check failed: {e!r}")
            if W.find_message_window(APP_CLASS):
                misses = 0
                continue
            misses += 1
            _log(f"the app's control window ({APP_CLASS}) is missing ({misses}/{POLL_MISSES})")
            if misses >= POLL_MISSES:
                self.app_gone("the app is gone")
                return

    def _note_shown(self):
        with self._idle_lock:
            self._hidden_at = None

    def _note_hidden(self):
        with self._idle_lock:
            self._hidden_at = self._now()

    def _read_idle_minutes(self) -> int:
        """browser.quit_after_minutes from the active profile's radial.json, read afresh so a change made while the
        browser waits takes effect without a restart. A file that cannot be read (caught mid-write, say) leaves the
        last good value."""
        try:
            with open(profiles.config_file(), encoding="utf-8-sig") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            return self._idle_minutes
        minutes = C.idle_quit_minutes(raw.get("browser") if isinstance(raw, dict) else None)
        if minutes != self._idle_minutes:
            _log(f"browser.quit_after_minutes: {minutes or 'off'} (was {self._idle_minutes or 'off'})")
        self._idle_minutes = minutes
        return minutes

    def idle_tick(self):
        """--managed: one look at whether a hidden window has sat unused for browser.quit_after_minutes (off unless the
        setting is on). Unused is the time since it was last hidden, or since a hidden start; being shown ends the
        count and hiding starts it again. A window that is up, or one nobody started (not managed), never quits. A
        strip that steps aside while another program is in front is up all the same."""
        if not self.managed or not self.ready or self.quitting or self.session_ending or self._idle_closing:
            return
        if self.visible() or self._fg_hidden:
            self._note_shown()
            return
        minutes = self._read_idle_minutes()
        with self._lock:                               # not in the middle of a show or hide
            now = self._now()
            with self._idle_lock:
                if self._hidden_at is None:            # hidden, though nothing said so
                    self._hidden_at = now
                if not minutes or self.visible() or now - self._hidden_at < minutes * 60:
                    return
                self._idle_closing = True              # from here a SHOW is refused, so none is taken and then lost
        self.quit(f"unused for {minutes} minutes (browser.quit_after_minutes)", idle=True)

    def app_gone(self, why):
        """The app quit (or told us to). A hidden window has no reason to stay; one that is up does not depend
        on the app, so it stays, no longer managed: closing it then ends the process. The strip of a managed
        popout goes with the app (strip_on stays, so the next pre-warm brings it back); one started by hand
        (the Start menu, --show) is not managed and stays, as the browser does."""
        with self._lock:
            up = self.visible() or (self.mode == "strip" and self._fg_hidden)
            if up and not self.quitting and not (self.managed and self.mode == "strip"):
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
        in the shape studio.json keeps its own. In strip mode: the strip's own place (see _save_strip_place)."""
        if self.mode == "strip":
            self._save_strip_place()
            return
        rec = winframe.placement_record(self.hwnd)
        if not rec:
            r = self._rect()
            if not r:
                return
            rec = {"x": r.left, "y": r.top, "width": r.right - r.left, "height": r.bottom - r.top,
                   "maximized": bool(user32.IsZoomed(self.hwnd))}
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
        if r and r.right - r.left >= minw and r.bottom - r.top >= minh:     # not the strip's size
            wd, ht = r.right - r.left, r.bottom - r.top
        else:
            wd, ht = round(START_SIZE[0] * scale), round(START_SIZE[1] * scale)
        wa = winframe.work_area(zb or self.prev_fg or W.GetForegroundWindow() or 0)
        return wa.left + (wa.right - wa.left - wd) // 2, wa.top + (wa.bottom - wa.top - ht) // 2, wd, ht, False

    def _on_screen(self, zb=0):
        """A window left on a monitor that has since gone is brought back onto one: centred on the screen of the
        ZBrush window the request named, else the primary one. Checked on every show, not only the first."""
        try:
            near = zb if zb and W.IsWindow(zb) else self.prev_fg
            if winframe.bring_on_screen(self.hwnd, near):
                _log("the window was off every screen; moved onto one")
        except Exception as e:
            _log(f"on-screen check failed: {e!r}")

    def _z_order(self):
        return winframe.HWND_TOPMOST if self.on_top or self.mode == "strip" else winframe.HWND_NOTOPMOST

    def request_show(self, tag, zb, toggle, kind=None):
        """The app asks for the window (SHOW), or the first launch does (--show). Never closes it: a window that is
        hidden appears, one that is up comes to the front, and one that is already in front hands the keyboard
        back to ZBrush when asked to toggle (the hotkey)."""
        with self._lock:
            if not self.ready:                         # still starting: it shows itself when it is up
                self._pending = (tag, zb, kind)
                _log(f"SHOW while starting: pending {self._pending}")
                return
            if self.mode == "strip":                   # the strip never has the keyboard: a SHOW always means the browser
                self.open_browser(tag, zb, kind, True, "SHOW")
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

    def apply_frame_theme(self, window):
        """The frame's dark mode and border for a theme's "window" palette, once the window is there. Never raises."""
        try:
            if self.hwnd:
                winframe.apply_theme(self.hwnd, window)
        except Exception as e:
            _log(f"frame theme failed: {e!r}")

    def _sync_theme(self):
        """The theme may have changed (Studio's setting, Windows' colour mode under Follow Windows, a new stored
        ZBrush scheme under Match ZBrush): when it differs from what the page was last given, set the frame and tell
        the page. Called with the lock held, by show() and, while the window is up, by theme_tick()."""
        now = (theme.read_setting(), theme.signature())   # a new stored ZBrush scheme changes the digest, not the name
        if now == self._theme_seen:
            return
        look = theme.preset(now[1][0])
        self.apply_frame_theme(look["window"])
        try:
            arg = json.dumps({"setting": now[0], "effective": now[1][0], "base": look["base"], "tokens": look["web"]})
            self.window.evaluate_js("window.__popoutTheme && __popoutTheme(" + arg + ")")
            self._theme_seen = now                 # a failed call is tried again at the next show
        except Exception as e:
            _log(f"__popoutTheme failed: {e!r}")

    def show(self, tag=None, zb=0, reset=True, kind=None):
        """Shows the window, takes the focus and puts the cursor in the search box. reset: also tell the page to
        start afresh (empty search, this tag only). Without it the page is left as it is, except that a tag
        or tab (kind) given is applied."""
        with self._lock:
            if not self.hwnd or self.quitting:
                return
            self._note_shown()
            was_visible = self.visible()
            self._remember_target(zb)
            self._sync_theme()
            if reset or tag or kind or self._page_strip:
                try:
                    arg = json.dumps({"mode": "browser", "tag": tag or None, "kind": kind or None, "reset": bool(reset)})
                    self.window.evaluate_js("window.__popoutShow && __popoutShow(" + arg + ")")
                    self._page_strip = False
                except Exception as e:
                    _log(f"__popoutShow failed: {e!r}")
            if was_visible:
                if user32.IsIconic(self.hwnd):
                    user32.ShowWindow(self.hwnd, SW_RESTORE)
                self._on_screen(zb)
                winframe.user32.SetWindowPos(self.hwnd, self._z_order(), 0, 0, 0, 0,
                                             W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_SHOWWINDOW)
            else:                                      # shown through pywebview: the form has to know it is visible, or the
                maxed = self._was_max                  # web view inside stays "hidden" and paints nothing
                if not self._placed:                   # the first time: where it was last session. After that it keeps its place
                    x, y, wd, ht, maxed = self._place(zb)
                    maxed = maxed or self._was_max     # the browser the strip took the place of was maximised
                    winframe.user32.SetWindowPos(self.hwnd, self._z_order(), x, y, wd, ht, W.SWP_NOACTIVATE)
                    self._placed = True
                else:
                    self._on_screen(zb)                # the screen it was on may be gone since it was hidden
                    winframe.user32.SetWindowPos(self.hwnd, self._z_order(), 0, 0, 0, 0,
                                                 W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE)
                self.window.show()
                winframe.user32.SetWindowPos(self.hwnd, self._z_order(), 0, 0, 0, 0,       # Show() may re-apply a stale
                                             W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE)  # TopMost: ours wins
                if maxed and not user32.IsZoomed(self.hwnd):
                    user32.ShowWindow(self.hwnd, SW_MAXIMIZE)
                self._on_screen(zb)                    # a maximised window could not be moved while it was hidden
            # Windows lets only the process that got the last input take the foreground; a no-op key from us
            # (0xE8 is an unassigned virtual key, so nothing acts on it) counts as that input.
            W.send_keys([(0xE8, False), (0xE8, True)])
            got = winframe.force_foreground(self.hwnd)
            _log(f"shown (tag={tag}, kind={kind}, reset={reset}, prev_fg={self.prev_fg}, was_visible={was_visible}, foreground={got})")
            self._focus_page()
            self._pen_check()

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
        show again when the app started it; a popout that is on its own has nothing to wait for and ends. With the
        strip on, the browser goes back to the strip instead."""
        if self.strip_on and self.mode == "browser" and not self.quitting and not self.session_ending:
            self.show_strip(why or "close")
            return
        self.hide(restore=True, why=why)
        with self._lock:
            self._leave_strip()                        # a hidden window is the browser, for the next SHOW
        if not self.managed and not self.quitting:
            self.quit("closed by the user")

    def hide(self, restore=True, why=""):
        """Hides the window. restore: give the focus back to ZBrush first (allowed while we hold it); a window that
        lost the focus to something else just goes."""
        with self._lock:
            if not self.visible():
                return False
            self._save_placement()
            if self.mode == "browser":
                self._was_max = bool(user32.IsZoomed(self.hwnd))
            else:
                self._pill_off()
            if restore and _is_target(self.prev_fg) and self._holds_foreground():
                user32.SetForegroundWindow(self.prev_fg)
            self.window.hide()
            if self.visible():                         # shown with Win32 (the strip): the form may not know it was up
                user32.ShowWindow(self.hwnd, SW_HIDE)
            self._note_hidden()
            W.nudge_mouse()
            _log(f"hidden ({why})")
            return True

    # --- the strip ----------------------------------------------------------------------------------
    def strip_from_browser(self):
        """The browser's strip button: the strip is on from now on, and takes the browser's place."""
        self.strip_on = True
        _update_state(strip_on=True)
        self.show_strip("strip button")

    def hide_strip(self):
        """Hide strip: off from now on, and the window goes (a popout on its own ends, as with the close button)."""
        self.strip_on = False
        _update_state(strip_on=False)
        self.close(why="hide strip")

    def strip_set(self, changes) -> dict:
        """Saves the strip's orient, kind, wrap and fold that changes names (the others stay); a bad value is left out.
        Returns the strip's settings as strip_state reads them back."""
        good = {}
        if isinstance(changes, dict):
            if changes.get("orient") in STRIP_ORIENTS:
                good["orient"] = changes["orient"]
            if changes.get("kind") in C.ASSET_KINDS:
                good["kind"] = changes["kind"]
            for key in ("wrap", "fold"):
                if isinstance(changes.get(key), bool):
                    good[key] = changes[key]
        if good:
            _update_strip(**good)
            _log(f"strip: {good}")
        ss = strip_state(_read_state())
        return {"on": self.strip_on, "orient": ss["orient"], "kind": ss["kind"], "wrap": ss["wrap"], "fold": ss["fold"]}

    def show_strip(self, why=""):
        """Puts the strip up in the window's place: a browser that is up is hidden first (its place kept, ZBrush given
        the keyboard back). Never activates: the foreground stays where it is."""
        with self._lock:
            if not self.hwnd or self.quitting or not self.ready:
                return
            if self.mode == "strip" and self.visible():
                return
            if self.visible():
                self.hide(restore=True, why=why or "to the strip")
            self._strip_up(why)

    def _strip_up(self, why):
        """The hidden window becomes the strip and appears (lock held)."""
        self.mode = "strip"
        self._fg_hidden = False                # a stale flag from a tick that hid the strip must not keep it hidden
        self._strip_frame(True)
        self._sync_theme()
        ss = strip_state(_read_state())
        fit = None
        try:
            arg = json.dumps({"mode": "strip", "kind": ss["kind"], "orient": ss["orient"], "wrap": ss["wrap"],
                              "fold": ss["fold"]})
            fit = self.window.evaluate_js("window.__popoutShow ? __popoutShow(" + arg + ") : null")
            self._page_strip = True
        except Exception as e:
            _log(f"__popoutShow (strip) failed: {e!r}")
        wd, ht = fit_size(fit, self._scale())
        x, y = self._strip_home = self._strip_place(ss, (wd, ht))
        if user32.IsZoomed(self.hwnd):                 # a maximised browser keeps WS_MAXIMIZE while hidden: SetWindowPos would leave it
            #                                            zoomed, and the show below would restore its old normal rectangle
            if not winframe.place_normal(self.hwnd, (x, y, x + wd, y + ht)):
                _log("the maximised state could not be cleared for the strip")
        winframe.user32.SetWindowPos(self.hwnd, winframe.HWND_TOPMOST, x, y, wd, ht, W.SWP_NOACTIVATE)
        user32.ShowWindow(self.hwnd, W.SW_SHOWNOACTIVATE)
        winframe.user32.SetWindowPos(self.hwnd, winframe.HWND_TOPMOST, 0, 0, 0, 0,
                                     W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE)
        self._note_shown()
        _log(f"strip shown ({why}; {ss['orient']}, {ss['kind']}, at {x},{y}, {wd}x{ht}, measured {fit is not None}, "
             f"foreground {W.GetForegroundWindow()})")

    def _leave_strip(self):
        """The hidden window is the browser again: its styles, its size limits and its own place (lock held). A browser
        that was maximised when the strip took its place is maximised again by show() (_was_max)."""
        if self.mode != "strip":
            return
        self._pill_off()
        if self._fg_hidden:                            # hidden by the foreground watch: that ends with the strip
            self._fg_hidden = False
            self._note_hidden()
        self.mode = "browser"
        self._strip_frame(False)
        self._placed = False                           # the browser comes back where it was, not where the strip is

    def open_browser(self, tag=None, zb=0, kind=None, reset=True, why=""):
        """The full browser in the window's place, activated as show() does: the strip's Open browser, and any SHOW
        while the strip is up. strip_on stays as it is, so the close button goes back to the strip."""
        with self._lock:
            if not self.hwnd or self.quitting:
                return
            if self.mode == "strip":
                if self.visible():
                    self.hide(restore=False, why=why or "to the browser")    # the strip never had the keyboard
                self._leave_strip()
            self.show(tag, zb, reset=reset, kind=kind)

    def _strip_frame(self, on):
        """The window's styles for the strip (on) or the browser: no taskbar button, never activated by a click, on top
        of everything, sized to its content; or what the browser has."""
        tool, noact = W.WS_EX_TOOLWINDOW, W.WS_EX_NOACTIVATE
        ex = winframe.user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        if on:
            self._app_window = bool(ex & WS_EX_APPWINDOW)      # WinForms gives the browser this one; it comes back with it
            ex = (ex | tool | noact) & ~WS_EX_APPWINDOW
        else:
            ex = (ex & ~(tool | noact)) | (WS_EX_APPWINDOW if self._app_window else 0)
        winframe.user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, ctypes.c_long(ex & 0xFFFFFFFF).value)
        if not winframe.set_fitted(self.hwnd, on):
            _log(f"the window could not be {'fitted to the strip' if on else 'made resizable again'} in time")
        winframe.user32.SetWindowPos(self.hwnd, self._z_order(), 0, 0, 0, 0,
                                     W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE | 0x0020)      # FRAMECHANGED

    def _scale(self) -> float:
        """Physical pixels per logical one for this window (the process is system DPI aware, as pywebview makes it)."""
        try:
            dpi = user32.GetDpiForWindow(self.hwnd) if self.hwnd else 0
        except Exception:
            dpi = 0
        return (dpi or winframe._system_dpi()) / 96

    def _target_rect(self):
        """The rectangle of the ZBrush window the strip goes beside the first time, or None."""
        for cand in (self.opts.get("zbrush") or 0, self.prev_fg):
            if _is_target(cand):
                break
        else:
            cand = _find_target()
        if not cand:
            return None
        r = w.RECT()
        if not user32.GetWindowRect(cand, ctypes.byref(r)) or user32.IsIconic(cand):
            return None
        return r.left, r.top, r.right, r.bottom

    def _strip_place(self, ss, size):
        """Where the strip's corner goes as it appears: its saved place, kept on the nearest screen, else beside
        ZBrush (strip_first_place)."""
        wd, ht = size
        if ss["window"]:
            x, y = ss["window"]
            return keep_inside(x, y, wd, ht, winframe._work_of((x, y, x + wd, y + ht)))
        target = self._target_rect()
        if target:
            work = winframe._work_of(target)
        else:
            wa = winframe._primary_work_area()
            work = (wa.left, wa.top, wa.right, wa.bottom)
        return strip_first_place(ss["orient"], size, target, work, round(STRIP_MARGIN * self._scale()))

    def _save_strip_place(self, moved=False):
        """popout.json "strip" "window": where the strip's corner belongs, when it is up; moved: the user has just
        dragged it, so where it is now. Takes no lock: the session's end calls it on the UI thread."""
        if self.mode != "strip" or not self.visible():
            return
        r = self._rect() if moved or not self._strip_home else None
        if r:
            self._strip_home = (r.left, r.top)
        if self._strip_home:
            _update_strip(window={"x": self._strip_home[0], "y": self._strip_home[1]})

    def fit_strip(self, fit):
        """The page's size for the strip (popout_strip_size): the window takes it with its corner where the strip
        belongs, kept on that screen (so its menu, open by the right edge, moves it left until it closes)."""
        with self._lock:
            if self.mode != "strip" or not self.hwnd or self.quitting:
                return
            wd, ht = fit_size(fit, self._scale())
            r = self._rect()
            if self.visible() and r:
                x, y = self._strip_home or (r.left, r.top)
                x, y = keep_inside(x, y, wd, ht, winframe._work_of((x, y, x + wd, y + ht)))
                winframe.user32.SetWindowPos(self.hwnd, None, x, y, wd, ht, W.SWP_NOACTIVATE | 0x0004)   # NOZORDER
            else:
                winframe.user32.SetWindowPos(self.hwnd, None, 0, 0, wd, ht, W.SWP_NOACTIVATE | W.SWP_NOMOVE | 0x0004)

    def hover(self, seq, name, rect, side):
        """The strip's page: the mouse is over the thumbnail of name (rect in the page's pixels), or off them. The
        pill is drawn on the control window's thread, which outlives any call."""
        try:
            seq = int(seq)
        except (TypeError, ValueError):
            return
        with self._pill_lock:
            if seq < self._pill_seq:
                return
            self._pill_seq = seq
            r = self._rect() if self.hwnd and self.mode == "strip" else None
            ok = r and name and isinstance(rect, list) and len(rect) == 4 and \
                all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in rect)
            if ok:
                s = self._scale()
                box = tuple(round(v * s) + (r.left if i % 2 == 0 else r.top) for i, v in enumerate(rect))
                self._pill = ("name", str(name)[:120], box, "below" if side == "below" else "right")
            else:
                self._pill = ("off",)
        self._post_pill()

    def note(self, text):
        """A message near the cursor, for the strip's page (it has no room for its own toasts)."""
        if not text:
            return
        with self._pill_lock:
            self._pill = ("note", text)
        self._post_pill()

    def _pill_off(self):
        with self._pill_lock:
            self._pill = ("off",)
        self._post_pill()

    def _post_pill(self):
        if self.ctl:
            user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
            user32.PostMessageW(self.ctl, WM_APP_PILL, 0, 0)

    def _show_pill(self):
        """On the control window's thread (its message loop runs the toast's timer): the newest pill asked for."""
        with self._pill_lock:
            p, self._pill = self._pill, None
        if not p:
            return
        import toast
        if p[0] == "off":
            toast.close()
            return
        pre = theme.preset(theme.current())["toast"]
        if p[0] == "name":
            toast.show_beside(p[1], p[2], p[3], _log, colour=pre["text"], pill=pre["pill"])
        else:
            toast.show(p[1], _log, ms=3600, colour=pre["text"], pill=pre["pill"])

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
        to ZBrush, because the app selects the item with ZBrush in front. From the strip nothing is handed back: it
        never took the focus, so ZBrush is in front already. Runs inside a js_api call: no show, hide or evaluate_js
        here."""
        if kind not in C.ASSET_KINDS:
            return {"ok": False, "error": f"Unknown kind {kind!r}."}
        if not name:
            return {"ok": False, "error": f"No {kind} to select."}
        with self._lock:
            strip = self.mode == "strip"
            if not strip:
                self._back_to_target()
        if strip and not self._zbrush_pids(fresh=True):    # a strip started by hand with no ZBrush: the pick has nowhere to go
            _log(f"pick {kind} {name!r} from the strip: no ZBrush is running")
            return {"ok": False, "error": "ZBrush is not running."}       # the page shows it as the strip's note
        app = W.find_message_window(APP_CLASS)
        payload = json.dumps({"v": 1, "op": "pick", "kind": kind, "name": name}).encode("utf-8")
        r = W.send_copydata(app, radiald.COPYDATA_PICK, payload) if app else None
        _log(f"pick {kind} {name!r}: app window {app}, result {r}")
        if r == 1:
            return {"ok": True}
        if not app:                         # the app owns the pick window and runs only while ZBrush does
            return {"ok": False, "error": "ZOrbit is not running. It starts and stops with ZBrush. "
                                          "Start ZBrush, or press Start app on Studio's Status screen."}
        if r is None:                       # the window is there but did not answer within the timeout
            return {"ok": False, "error": "ZOrbit did not answer. Try again in a moment."}
        return {"ok": False, "error": f"ZOrbit did not take that {kind}. Is it up to date?"}

    def quit(self, why="", idle=False):
        """idle: it sat unused (idle_tick); the process then exits with radiald.POPOUT_EXIT_IDLE, and the control window
        stays until the very end (_run closes it), so a press that comes now is answered 'quitting' instead of meeting
        no window."""
        with self._lock:
            if self.quitting:
                return
            self.quitting = True
            if idle:
                self.exit_code = radiald.POPOUT_EXIT_IDLE
            _log(f"quitting ({why})")
            if self.visible():
                self._save_placement()
        if not idle:
            self.stop_ctl()

        def kill():                                   # the window should close by itself; this makes sure the process ends
            time.sleep(5)
            _log("still here after 5 s; exiting")
            os._exit(self.exit_code)
        threading.Thread(target=kill, daemon=True).start()
        if self.window is None:
            os._exit(self.exit_code)
        try:
            self.window.destroy()
        except Exception as e:
            _log(f"destroy failed: {e!r}")
            os._exit(self.exit_code)

    def on_closing(self):
        """pywebview 'closing' (UI thread; False cancels): Alt+F4 and the like only close the window, which is hidden
        (or ends the process: see close)."""
        if self.quitting or self.session_ending:       # the session ending must not be vetoed: it would block shutdown
            return None
        threading.Thread(target=self.close, kwargs={"why": "close requested"}, daemon=True).start()   # hiding needs the UI thread free
        return False


FORWARD_AGAIN = None                  # _forward: the running popout is quitting; start in its place once it has gone
GONE_WAIT_S = 10                      # how long a launch waits for a quitting popout to end (it exits within 5 s)


def _forward(opts):
    """A second launch: hand our arguments to the running popout, which may still be starting up. 0 when done, 1 when
    it never came up, FORWARD_AGAIN when it is quitting after sitting unused and so cannot take them."""
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
            if r == radiald.SHOW_QUITTING or (r is None and not W.find_message_window(radiald.POPOUT_CLASS)):
                return FORWARD_AGAIN
            return 0
        time.sleep(0.1)
    _log("a popout is already running, but its control window did not appear")
    return 1


def _acquire() -> tuple:
    """(handle of the single-instance mutex, True when another popout already held it)."""
    h = kernel32.CreateMutexW(None, False, MUTEX)
    return h, ctypes.get_last_error() == W.ERROR_ALREADY_EXISTS


def _wait_until_gone() -> bool:
    """True once no process holds the mutex (the quitting popout has ended), False after GONE_WAIT_S."""
    deadline = time.monotonic() + GONE_WAIT_S
    while W.mutex_exists(MUTEX):
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True


def main(args) -> int:
    opts = _parse(args)
    _log(f"Popout {paths.VERSION} main(): {args}")
    try:
        profiles.ensure()                                # the first profile, when this is the first process to start
    except OSError as e:                                 # the window still opens: tags and usage just read nothing
        _log(f"profiles could not be set up: {e!r}")
    too_new = profiles.too_new()
    if too_new:                                          # files of a newer ZOrbit: the app says so; no window here
        _log(f"fatal: {too_new}")
        return 1
    mutex, running = _acquire()
    if running:
        code = _forward(opts)
        if code is not FORWARD_AGAIN:
            return code
        _log("the popout running is quitting after sitting unused; waiting for it to end, then starting")
        kernel32.CloseHandle(mutex)                      # ours is a handle to its mutex: it lives until we let go
        if not _wait_until_gone():
            _log(f"it did not end within {GONE_WAIT_S} s; giving up")
            return 1
        mutex, running = _acquire()
        if running:                                      # another launch was quicker: give it ours
            kernel32.CloseHandle(mutex)
            return _forward(opts) or 0
    try:
        return _run(opts, mutex)
    except Exception:                                    # the process has no console: popout.log is the only place to see why
        _log("popout failed:\n" + traceback.format_exc())
        return 1


def _run(opts, mutex) -> int:
    pop = Popout(opts)
    pop.start_ctl()
    if opts["show"]:
        pop._pending = (opts["tag"], opts["zbrush"], opts["kind"])
    if not webview2.require(_log, show_message=opts["show"]):     # a pre-warm only logs: nobody asked for a window
        pop.stop_ctl()
        return 1
    import webview
    _log("pywebview imported")
    try:                                                 # own identity, not Python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    user32.SetProcessDPIAware()                          # as pywebview does: sizes below are logical pixels
    api = PopoutApi(pop)
    window = webview.create_window(TITLE, url=UI_PAGE, js_api=api, width=START_SIZE[0], height=START_SIZE[1],
                                   min_size=MIN_SIZE, hidden=True, on_top=pop.on_top, frameless=True, easy_drag=False,
                                   background_color=theme.preset(theme.current())["window"]["background"],
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
    return pop.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
