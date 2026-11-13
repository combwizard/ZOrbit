"""ZOrbit app: owns the menu hotkeys and the overlay, hands picks to the ZBrush bridge.

How it works:
  * The menu hotkey never goes through ZBrush. A low-level keyboard hook sees it, checks that ZBrush is the
    foreground app, opens the ring and swallows the key so ZBrush never acts on it. The hook runs on its own
    thread (HookThread), so nothing the main thread is busy with can make Windows drop it for being slow.
  * The ring is a non-activating layered window, destroyed after every pick.
  * A pick is written atomically to %LOCALAPPDATA%\\ZOrbit\\request.json and handed to the bridge
    inside ZBrush, either by a window message to the bridge's listener (no keystroke) or by a bare bridge
    key bound natively in ZBrush (held modifiers released first). Then a zero-distance mouse move wakes
    the pen/cursor tracking.
  * The same pick also goes to request.txt for the ZScript bridge of ZBrush 2022-2025 (no Python API, so no
    listener: those always get the bridge key, and brushes, alphas, materials and textures load from their own
    installation's files). It is only written when such an installation exists.
  * Brush picks are counted in usage.json; a menu's auto slots are filled from those counts as it opens.
  * tags.json (the user's tags on brushes, alphas, materials and textures) is watched with radial.json: tag
    slots open a fan of the items with that tag, and a slot is drawn in the colour of its item's first tag
    (expand.py does both).
  * The browser (brushes, alphas, materials, textures) is a separate popout process (popout.py): a normal window
    that stays open until the user closes it. It is opened by browser.hotkey, a "browser" ring item or the tray
    menu. The app finds its message-only window and sends it WM_COPYDATA; an asset picked there comes back the
    same way, to the control
    window, and goes through the normal hand-off once ZBrush has the focus again. The hotkey never closes the
    window: pressed over the browser it hands the keyboard back to ZBrush. The browser outlives the app.

Started through main.py (ZOrbit.exe), normally by the ZBrush bridge when ZBrush launches; it exits when
the last ZBrush process has gone. Only one instance runs at a time.
"""
import argparse
import collections
import contextlib
import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import activity             # noqa: E402
import capture              # noqa: E402
import commands             # noqa: E402
import config as C          # noqa: E402
import expand               # noqa: E402
import fileitem             # noqa: E402
import fsutil               # noqa: E402
import installs             # noqa: E402
import paths                # noqa: E402
import profiles             # noqa: E402
import recent               # noqa: E402
import tags                 # noqa: E402
import theme                # noqa: E402
import usage                # noqa: E402
import win32 as W           # noqa: E402
import zscript_bridge       # noqa: E402

try:
    import assets           # noqa: E402
    import brushes          # noqa: E402  (assets imports it too; the library folders are read through it)
except Exception:           # thumbnails are optional
    assets = None

DATA_DIR = paths.DATA_DIR
LOG_FILE = os.path.join(DATA_DIR, "radiald.log")
REQUEST_FILE = os.path.join(DATA_DIR, "request.json")
LISTENER_FILE = os.path.join(DATA_DIR, "listener.json")
LIB_DIRS_EVERY = 5.0            # seconds between looks at which ZBrush is running, for the library folders
BRIDGE_LOG = os.path.join(DATA_DIR, "bridge.log")      # written by the plugin inside ZBrush
ZSCRIPT_LOG = os.path.join(DATA_DIR, "zscript_bridge.log")   # the ZScript plugin's last pick, rewritten each time
MUTEX_NAME = "Local\\ZOrbit"
TAKEOVER_MUTEX = "Local\\ZOrbitTakeover"      # held while a new app replaces an older one
POPOUT_MUTEX = "Local\\ZOrbitPopout"          # the browser's (popout.MUTEX)
TAKEOVER_LOCK_MS = 10000       # how long a second new app waits for the first one to finish taking over
TAKEOVER_QUIT_S = 8            # how long the old app gets to end after the quit message
TAKEOVER_BROWSER_S = 3         # ... and its hidden browser to end after that

WM_APP_PICK = W.WM_APP + 1            # to the bridge listener inside ZBrush
WM_APP_OPEN = W.WM_APP + 10           # hook -> control window: open menu (wparam = menu slot)
WM_APP_KEYUP = W.WM_APP + 11          # hook -> control window: the held hotkey went up
WM_APP_CANCEL = W.WM_APP + 12         # hook -> control window: Esc
WM_APP_MASK = W.WM_APP + 13           # hook -> control window: inject the Alt menu-mask key
WM_APP_BROWSER = W.WM_APP + 14        # hook -> control window: the browser hotkey
WM_APP_BROWSER_PICK = W.WM_APP + 15   # control window -> itself: a brush was picked in the popout
WM_APP_TYPING = W.WM_APP + 16         # hook -> control window: a key was typed while a tapped ring waited for a click
WM_APP_COMMAND = W.WM_APP + 17        # control window -> itself: run the next command from another program
WM_APP_PROFILE = W.WM_APP + 18        # hook -> control window: the next-profile hotkey
WM_HOOK_REHOOK = W.WM_APP + 20        # main thread -> hook thread: install the hook again
WM_HOOK_RELEASE_HELD = W.WM_APP + 21  # main thread -> hook thread: let go of the held hotkey (wparam = its vk)
WM_HOOK_RELEASE_BROWSER = W.WM_APP + 22   # ... and of the browser hotkey
WM_HOOK_RELEASE_PROFILE = W.WM_APP + 23   # ... and of the next-profile hotkey
HOOK_START_S = 5                      # how long run() waits for the hook thread to install the hook
HOOK_STOP_S = 2                       # ... and to end it
ACK_WAIT_S = 0.5                      # a listener pick not picked up in this long falls back to the bridge key
RESULT_TRIES = 30                     # ticks (100 ms) to wait for the plugin to log what a picked-up request did
ACK_HOLD_MAX_S = 30                   # ... but not while the left button is down, for this long at most
LEGACY_SCAN_S = 60                    # how long the scan for ZBrush 2022-2025 installations is kept
TIMER_WATCH, TIMER_ACK, TIMER_REHOOK, TIMER_CONFIG, TIMER_BROWSER_PICK, TIMER_PREWARM, TIMER_POPOUT_SHOW, \
    TIMER_ZS_RESULT, TIMER_COMMAND, TIMER_APPLY, TIMER_RING_WARM = range(1, 12)
RING_WARM_WAIT_MS = 1000              # ring warm-up starts this long after the last change (a slider drag saves often)
RING_WARM_PICK_MS = 2000              # ... and this long after a pick that changed an auto slot
RING_WARM_STEP_MS = 10                # one picture per tick while it runs
RING_WARM_HOLD_MS = 100               # how often it looks again while something more urgent is going on
RING_WARM_TICK_S = 0.004              # pictures already there are walked past in one tick for at most this long
RING_WARM_RECENT_S = 4.0              # a plan with recent slots waits at most this long for the first recent-files answer
RING_WARM_SHARE = 0.75                # warm-up fills at most this share of each ring cache, so it never pushes out
                                      # what it drew a moment ago, and leaves room for what is opened by hand
COMMAND_WAIT_S = 2                    # how long a command's pick waits for the one before it to be taken
ZS_RESULT_S = 15                      # how long to look for the ZScript plugin's line about a pick (a stroke delays it)
RECENT_PREFETCH_S = 30                # while ZBrush is in front, the recent slots' lists are read again this often
APPLY_KEY_WAIT_S = 1.0                # a ZBrush 2022-2025 pick still in request.txt this long after the key: run the script
APPLY_SCRIPT_WAIT_S = 6.0             # ... and still there this long after that (4 s measured): drop it
APPLY_BUSY_MAX_S = 300                # a ZBrush Windows calls not responding is waited for this long at most
COPYDATA_PICK, COPYDATA_SHOW, COPYDATA_QUIT = 1, 10, 12   # WM_COPYDATA ids: popout -> app, app -> popout
COPYDATA_THEME = 13                                       # Studio -> popout: look at the theme now (no payload)
SHOW_QUITTING = 2                     # a popout's answer to SHOW (1 taken, 0 refused): quitting, unused
POPOUT_EXIT_IDLE = 20                 # its exit code then; any other non-zero code is a failure
COPYDATA_COMMAND = commands.COPYDATA                      # another program -> app: ZOrbit.exe --pick and the rest
POPOUT_CLASS = "ZOrbitPopoutCtl"      # the popout's message-only control window
POPOUT_START_S = 15                   # a popout asked to show gets this long to appear before we ask again
THUMB_PX = 128                        # thumbnail cache size, shared with the Studio
TEXT_CLASSES = frozenset({"Edit", "RichEdit20W", "RICHEDIT50W", "ComboBox"})   # focused windows that take typing
DIALOG_CLASS = "#32770"               # the class of native Windows dialogs (Save As, message boxes)
STUCK_KEY_S = 30                      # a swallowed hotkey the hook never saw go up is let go after this long


def tags_path():
    """tags.json of the active profile; the environment variable ZORBIT_TAGS_FILE points tests and --check
    at another file."""
    return profiles.tags_file()


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {msg}"
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    if sys.stdout:
        try:
            print(line, flush=True)
        except Exception:
            pass


# What the user is told when the app knows why a pick went nowhere (docs/troubleshooting.md lists them).
MSG_NO_CONNECTION = "No plugin listener in ZBrush (bridge mode is Message). Check Zplugin > ZOrbit > Status."
MSG_NO_ANSWER = "The plugin did not answer (bridge mode is Message). Check Zplugin > ZOrbit > Status."
MSG_BRIDGE_NO_RESPONSE = "ZBrush did not take the pick. Check Zplugin > ZOrbit > Apply."
MSG_NOT_FRONT = "ZBrush was not the front window, nothing sent"
MSG_EMPTY_SLOT = "This slot is empty"
MSG_EMPTY_MENU = "That menu has nothing usable in it"
MSG_PICK_FAILED = "ZBrush could not carry out that pick. See bridge.log."
MSG_COMMAND_TEXT = "A dialog or text box has the focus, nothing sent"
MSG_COMMAND_PINNED = "This ZOrbit runs on one menus file, so it has no profiles"
MSG_COMMAND_FROZEN = "Your files were changed by a newer ZOrbit, so the profile stays"
MSG_COMMAND_NO_MENUS = "ZOrbit has no menus loaded"
MSG_CAPTURE_FOLDER = "The capture folder cannot be used, nothing sent. See radiald.log."
MSG_CAPTURE_NAME = "ZBrush 2022-2025 cannot save to that capture folder's name, nothing sent"
MSG_FILE_MISSING = "That file is not there, nothing sent. See radiald.log."
MSG_FOLDER_MISSING = "That folder is not there, nothing sent. See radiald.log."
MSG_NO_PROJECT = "No project in that folder, nothing sent"
MSG_FILE_NAME = "ZBrush 2022-2025 cannot read that file's name, nothing sent"
MSG_FILE_LONG = "That path is too long for ZBrush 2022-2025, nothing sent. See radiald.log."
# fileitem.FileItemError.kind -> the message near the cursor
_FILE_MESSAGES = {"file": MSG_FILE_MISSING, "folder": MSG_FOLDER_MISSING, "empty": MSG_NO_PROJECT,
                  "name": MSG_FILE_NAME, "long": MSG_FILE_LONG}
TIP_FROZEN = f"ZOrbit {paths.VERSION}: your files were changed by a newer ZOrbit"

# A line of bridge.log: "2026-10-31 12:00:00 #7 'Clay' via listener: brush Clay: ...; press Tool:X: ..."
_PLUGIN_LINE = re.compile(r"^([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9:]{8}) #([0-9]+) '(.*)' via ([^:]*): (.*)$")
_PLUGIN_BAD = re.compile(r"^([a-z]+) (.+): (NOT loaded in ZBrush and no file known|no such interface item)"
                         r"(?: \(Edit mode is off\))?$")


def _read_bytes(path):
    """The whole file, or None when it cannot be read (not there yet, or being written)."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def _zscript_result(seq, before, path=None):
    """What the ZScript plugin did with pick number seq: its line in zscript_bridge.log without the "#seq " in
    front, or None while the file has no line for it. The plugin rewrites the file with the last pick only and
    stamps no time, and the numbers start again with every run of the app, so a line counts only once the file
    differs from `before`, its bytes when the pick was sent."""
    data = _read_bytes(path or ZSCRIPT_LOG)
    if data is None or data == before:
        return None
    line = data.decode("mbcs", errors="replace").strip().splitlines()      # ZScript writes the ANSI code page
    head = f"#{seq} "
    if not line or not line[0].startswith(head):
        return None
    return line[0][len(head):]


def _problems(result):
    """The messages for what went wrong in a plugin's result, its "; "-separated steps (empty when all went well)."""
    problems = []
    for part in result.split("; "):
        if part.startswith("file ") and ": ok, file " in part:      # a file saved or opened, even in a folder named FAILED
            continue
        if "FAILED" in part:
            problems.append(MSG_PICK_FAILED)
            continue
        bad = _PLUGIN_BAD.match(part)
        if bad:
            what = bad.group(2)
            problems.append(f"{what} could not be found in ZBrush" if bad.group(3).startswith("NOT")
                            else f"{what} is not a ZBrush button")
    return problems


def _plugin_result(seq, since=0.0, path=None):
    """What the plugin did with pick number seq, from the last 4 KB of bridge.log: None while the log has no line
    for it, else the list of messages for what went wrong (empty when all went well). since is the epoch time of
    the pick; a line stamped earlier is from an older run of the app that used the same number."""
    try:
        with open(path or BRIDGE_LOG, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - 4096))
            lines = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        m = _PLUGIN_LINE.match(line)
        if not m or int(m.group(2)) != seq:
            continue
        try:
            at = time.mktime(time.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"))
        except (ValueError, OverflowError):
            at = None
        if at is not None and at < since - 2:          # the log's clock has whole seconds
            return None
        return _problems(m.group(5))
    return None


def _trim_log(max_bytes=1_000_000):
    try:
        if os.path.getsize(LOG_FILE) > max_bytes:
            with open(LOG_FILE, "rb") as f:
                f.seek(-max_bytes // 2, os.SEEK_END)
                tail = f.read()
            with open(LOG_FILE, "wb") as f:
                f.write(tail)
    except OSError:
        pass


@dataclass(frozen=True)
class HookState:
    """What the keyboard hook needs to know about the config, as one immutable value. load_config builds a new one
    and swaps it into App._hook_state in a single assignment; the hook thread reads that attribute once per key
    and never sees a half-updated config.

    slots: one (vk, ctrl, alt, shift, swallow, slot) tuple per menu with a hotkey; slot is the index
    WM_APP_OPEN carries (App.slots[slot] is the menu).
    browser: (vk, ctrl, alt, shift) of the browser hotkey, or None.
    profile: the same for the next-profile hotkey, or None."""
    slots: tuple = ()
    browser: tuple | None = None
    profile: tuple | None = None

    @staticmethod
    def build(menus, browser_key, profile_key=None):
        """menus: the menus with a hotkey, in App.slots order. browser_key, profile_key: a config.Hotkey or None."""
        slots = tuple((m.hotkey.vk, m.hotkey.ctrl, m.hotkey.alt, m.hotkey.shift, bool(m.swallow), i)
                      for i, m in enumerate(menus))
        bk = None if browser_key is None else (browser_key.vk, browser_key.ctrl, browser_key.alt, browser_key.shift)
        pk = None if profile_key is None else (profile_key.vk, profile_key.ctrl, profile_key.alt, profile_key.shift)
        return HookState(slots, bk, pk)


class HookThread(threading.Thread):
    """Owns the WH_KEYBOARD_LL hook. A low-level hook is called on the thread that installed it, from inside that
    thread's message loop, and Windows silently removes a hook whose callback is too slow to return. So the hook
    lives on a thread that does nothing else: the main thread's file polling, sprite building and process starts
    cannot delay it.

    on_key(wparam, kb) -> bool runs on this thread and returns True to swallow the key. on_command(msg, wparam,
    lparam) also runs on this thread, for the thread messages posted with post(). The thread ends when stop()
    posts WM_QUIT to it.

    start_and_wait() returns once the hook is installed, and raises the error if it could not be."""

    def __init__(self, on_key, on_command, log_fn):
        super().__init__(name="ZOrbitHook", daemon=True)
        self._on_key = on_key
        self._on_command = on_command
        self._log = log_fn
        self.handle = None                  # the HHOOK; only this thread changes it
        self.thread_id = 0
        self.error = None                   # why the hook could not be installed, else None
        self.ready = threading.Event()      # set once the first install has succeeded or failed
        self._proc = W.HOOKPROC(self._callback)     # the ctypes callback must live as long as the hook

    def start_and_wait(self, timeout=HOOK_START_S):
        self.start()
        if not self.ready.wait(timeout):
            raise TimeoutError(f"the keyboard hook thread did not start within {timeout} s")
        if self.error is not None:
            raise self.error

    def post(self, msg, wparam=0, lparam=0) -> bool:
        """Posts a thread message to the hook thread's loop. False when it is gone or not running yet."""
        return bool(self.thread_id) and bool(W.PostThreadMessageW(self.thread_id, msg, wparam, lparam))

    def stop(self, timeout=HOOK_STOP_S) -> None:
        if not self.is_alive():
            return
        self.post(W.WM_QUIT)
        self.join(timeout)
        if self.is_alive():                 # stuck inside a callback: the process is ending, so just say so
            self._log(f"hook thread did not stop within {timeout} s")

    def _callback(self, ncode, wparam, lparam):
        try:
            if ncode == 0 and self._on_key(wparam, W.KBDLLHOOKSTRUCT.from_address(lparam)):
                return 1
        except Exception:
            self._log("hook error:\n" + traceback.format_exc())
        return W.CallNextHookEx(self.handle, ncode, wparam, lparam)

    def _install(self):
        """Installs the hook (this thread only), then removes the one it replaces, so there is no gap."""
        new = W.SetWindowsHookExW(W.WH_KEYBOARD_LL, self._proc, W.GetModuleHandleW(None), 0)
        if not new:
            raise ctypes.WinError(ctypes.get_last_error())
        old, self.handle = self.handle, new
        if old:
            W.UnhookWindowsHookEx(old)

    def run(self):
        msg = W.w.MSG()
        try:
            self.thread_id = W.GetCurrentThreadId()
            # The thread has no message queue until it first calls a message function, and PostThreadMessage
            # fails until it has one. Peek once before anyone is told the thread is ready.
            W.PeekMessageW(ctypes.byref(msg), None, W.WM_USER, W.WM_USER, W.PM_NOREMOVE)
            self._install()
        except Exception as e:
            self.error = e
            self.thread_id = 0              # a stale id could one day be another thread's: post() must refuse it
            self.ready.set()
            return
        self.ready.set()
        try:
            # The hook callbacks are delivered from inside GetMessageW, so this loop is what keeps the hook alive.
            while W.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                try:
                    if msg.message == WM_HOOK_REHOOK:
                        self._install()
                        self._log("hook re-installed")
                    else:
                        self._on_command(msg.message, msg.wParam, msg.lParam)
                except Exception:
                    self._log("hook thread error:\n" + traceback.format_exc())
        finally:
            if self.handle:
                W.UnhookWindowsHookEx(self.handle)
                self.handle = None
            self.thread_id = 0


class App:
    def __init__(self, cfg_path=None, target_exe="zbrush.exe", exit_with_target=False, no_tray=False, profile=None):
        # An explicit path (--config, tests, tools/ring_shots.py) or profile= (a Studio preview) pins the app to it:
        # it never follows the profile pointer.
        self._pinned = cfg_path is not None or profile is not None or not profiles.enabled()
        self.profile = None if cfg_path is not None else (profile or profiles.active())
        self.cfg_path = cfg_path or profiles.config_file(self.profile)
        self._profile_sig = profiles.signature()
        self._profile_wait = 0          # ticks spent waiting for a pointer's folder to appear
        self._frozen = False            # the files were made by a newer ZOrbit: no switching, nothing written
        self.target_exe = target_exe.lower()
        self.exit_with_target = exit_with_target
        self.no_tray = no_tray
        self.tray = None
        self.cfg = None
        self._bad_sig = None            # (mtime, size) of a radial.json that failed to load
        self._theme = "dark"            # the theme the config was last loaded under
        self._theme_sig = ("dark", "")  # theme.signature() of that load: the name, and for zbrush the scheme's digest
        self._lib_sig = None            # (user_folders_signature, dirs_signature) last seen; None before the first check
        self._lib_sig_failed = False    # reading it failed (logged once until it works again)
        self._lib_dirs = None           # brushes.dirs_signature() from the last process scan, LIB_DIRS_EVERY apart
        self._lib_dirs_t = -LIB_DIRS_EVERY
        self._lib_rebuild = None        # the thread reading the library again, or None
        self._lib_again = False         # the folders changed (again): the thread makes one more pass
        self._lib_lock = threading.Lock()   # guards _lib_rebuild and _lib_again, so a change is never lost
        self.slots = []                 # menus with hotkeys, indexed for WM_APP_OPEN
        self._commands = collections.deque()    # (what to do, whether it is a pick) for commands from other programs
        self._command_wait = None       # when the pick at the head of that queue has to stop waiting
        self.ring = None
        # Threads. The keyboard hook runs on its own thread (HookThread). Rules that keep the two safe:
        #  * The hook thread reads the config only through self._hook_state, one immutable HookState that
        #    load_config replaces whole.
        #  * held_vk, held_swallow, _browser_vk and _profile_vk are written by the hook thread only (the main thread
        #    asks it to let go with WM_HOOK_RELEASE_*). The main thread reads them as hints: an attribute read is
        #    atomic, and
        #    a value that is a moment stale only delays what the next timer tick would do anyway.
        #  * self.ring is read once into a local by the hook; a cancel posted to a ring that has just closed is
        #    harmless because _ctrl_proc looks at self.ring again.
        #  * _hook_exe and _popout_pid belong to the hook thread; the main thread has its own _pid_exe.
        self.held_vk = None             # hotkey vk currently held (between our keydown and keyup); hook thread writes
        self.held_swallow = False
        self._hook = None               # the HookThread
        self._hook_state = HookState()  # what the hook thread reads; swapped by load_config
        self.ctrl = None
        self._pid_exe = {}              # pid -> exe name, for the main thread
        self._hook_exe = {}             # the same for the hook thread, so neither ever writes the other's dict
        self._pid_install = {}          # pid -> installs.install_of() of the ZBrush.exe behind it
        self._icons = {}
        self._seq = 0
        self._ack = None                # [seq, deadline, give up at, logged] of a message-mode pick awaiting pickup
        self._pick_time = 0.0           # when that pick was handed over
        self._result = None             # [seq, since, ticks left]: a picked-up request whose outcome is not logged yet
        self._zs_result = None          # [seq, bytes of zscript_bridge.log before, give up at]: a ZScript pick to log
        self._apply_watch = None        # {seq, at, deadline, wait, ran, exe}: a ZBrush 2022-2025 pick not yet taken from request.txt
        self._config_error = None       # why the last load of radial.json failed, else None
        self._have_cfg = False          # self.cfg came from a radial.json that loaded (not the empty stand-in)
        self._unreadable = set()        # pids of foreground windows whose process could not be read, logged
        self._elevated = {}             # pid of a running ZBrush -> True when it looks elevated (checked every 3 s)
        self._token_check = None        # whether process_elevated() can be trusted here (tested on our own process)
        self._listener_skipped = set()  # pids whose mismatch with listener.json was logged
        self._stuck = {}                # "held" / "browser" / "profile" -> when the tick first saw it held with no ring
        self._legacy_scan = (0.0, False)    # (when, whether a ZBrush 2022-2025 is installed)
        self._target_misses = 0
        self.usage = usage.Usage(None if cfg_path is not None else profiles.usage_file(self.profile))
        self.activity = activity.Activity(os.path.join(DATA_DIR, "activity.json"), log)   # for the Studio's Setup screen
        self._activity_menu = None      # id of the root ring last opened, so a pick can say which ring it came from
        self.tags = tags.TagStore(tags_path() if cfg_path is not None else profiles.tags_file(self.profile))
        self.expander = None            # expand.Expander of the current config, tags and usage
        self._recent_at = 0.0           # time.monotonic() of the last periodic recent prefetch (_recent_tick)
        self._browser_vk = None         # the browser hotkey while it is down (its repeats and key-up are ours); hook thread writes
        self._profile_vk = None         # the same for the next-profile hotkey; hook thread writes
        self._popout_proc = None        # subprocess.Popen of the popout we last started
        self._popout_spawning = False   # a thread is starting it right now
        self._popout_pending = None     # (tag, toggle, kind) to SHOW once a popout started hidden has its window
        self._popout_started = 0.0      # when we last spawned the popout process
        self._popout_show = False       # ... and whether that spawn asked it to show itself
        self._prewarmed = False         # a pre-warm spawn is scheduled or done for this popout
        self._popout_idle_quit = None   # the Popen that quit unused by itself: no pre-warm until asked for
        self._popout_pid = (0.0, 0)     # (valid until, pid of the popout's control window); hook thread only
        self._popout_zb = None          # (ZBrush hwnd, its install) from when the browser was last opened
        self._browser_pick = None       # brush Item picked in the popout, waiting for ZBrush to have focus
        self._browser_pick_deadline = 0.0
        self._prefetch_threads = []     # the threads still reading the menus' thumbnails (see _prefetch)
        self._warm = None               # the ring warm-up under way (see _warm_tick), or None
        self._warm_gen = 0              # moved by every change that makes a warm-up plan out of date
        self._warm_why = "start"        # what asked for the next warm-up
        self._warm_scale = None         # the display scale the last warm-up was planned for
        self._zb_monitor = None         # (work area, scale) of ZBrush's monitor when it was last seen in front

    # --- library folders -------------------------------------------------------------------------
    def _check_library_folders(self) -> None:
        """Reads the library again when the user changed the folders in Studio ("library_folders" in studio.json,
        read on each tick with a bytes-compared cache). The walk runs on its own thread; a change while it runs
        makes it go round once more."""
        if assets is None:
            return
        try:
            now = time.monotonic()
            if now - self._lib_dirs_t >= LIB_DIRS_EVERY:   # which ZBrush's folders: a process scan, so not every tick
                self._lib_dirs_t = now
                self._lib_dirs = brushes.dirs_signature()
            sig = (brushes.user_folders_signature(), self._lib_dirs)
        except Exception as e:
            if not self._lib_sig_failed:
                log(f"library folders: cannot read them: {e!r}")
                self._lib_sig_failed = True
            return
        self._lib_sig_failed = False
        if self._lib_sig is None:              # the first look: what the indexes are (or will be) built from
            self._lib_sig = sig
            return
        if sig == self._lib_sig:
            return
        why = "library folders changed" if sig[0] != self._lib_sig[0] else "the ZBrush in use changed"
        self._lib_sig = sig
        log(f"{why}: reading the library again")
        with self._lib_lock:
            self._lib_again = True
            if self._lib_rebuild is None:
                t = threading.Thread(target=self._rebuild_libraries, name="library-rebuild", daemon=True)
                self._lib_rebuild = t
                t.start()

    def _rebuild_libraries(self) -> None:
        """Walks every kind already built again, so the ring and the tag fans find what the new folders hold.
        A kind never built is built from the new folders the first time it is wanted."""
        done = set()
        try:
            while True:
                with self._lib_lock:            # cleared in the same hold as the last look, so no change slips by
                    if not self._lib_again:
                        self._lib_rebuild = None
                        break
                    self._lib_again = False
                for kind in assets.ALL_KINDS:
                    if not assets.has_built(kind):
                        continue
                    try:
                        assets.library(kind)
                        done.add(kind)
                    except Exception as e:
                        log(f"library: cannot read the {kind} folders again: {e!r}")
        except Exception:
            log("library rebuild error:\n" + traceback.format_exc())
            with self._lib_lock:
                self._lib_rebuild = None
            return
        log(f"library read again: {len(done)} kinds, generation {assets.generation}")

    # --- config ----------------------------------------------------------------------------------
    def load_config(self, force=False, balloon=True) -> None:
        if self.tags.reload_if_changed():          # new tag labels and colours show in the next ring
            if self.tags.error:
                log(f"tags: {self.tags.error}; keeping the previous tags")
            else:
                log(f"tags loaded: {len(self.tags.tags())} tags, {len(self.tags.tagged())} tagged items")
            force = True
        try:
            st = os.stat(self.cfg_path)
            mtime, bad = st.st_mtime, (st.st_mtime, st.st_size)
        except OSError:
            mtime = bad = None                     # missing: reported once, by the load below
        sig = theme.signature()                    # a change of theme (or a new stored ZBrush scheme) reloads the config
        eff = sig[0]
        if not force and sig == self._theme_sig and ((self.cfg and mtime == self.cfg.mtime) or bad == self._bad_sig):
            return
        if sig != self._theme_sig:
            src = theme.source() if eff == "zbrush" else None
            log(f"theme: {eff}" + (f" (ZBrush {src['year']})" if src else ""))
        try:
            cfg = C.load(self.cfg_path, self.tags, theme=eff)
        except Exception as e:
            self._theme = eff                      # a broken file is not loaded again on every tick for the same theme
            self._theme_sig = sig
            fresh = bad != self._bad_sig
            self._bad_sig = bad                    # logged once per broken version, not on every poll. The size is part
            # of it: an editor that truncates and then writes can leave the whole file with the half-written file's
            # mtime, and the next poll must still read it.
            self._config_error = str(e) or repr(e)
            if self._have_cfg:
                log(f"config error, keeping previous config: {e!r}")
            else:                                  # nothing loaded yet: run with no menus until the file is fixed
                log(f"cannot load radial.json: {self._config_error}; open Studio to fix it "
                    f"(the file is re-read as soon as it changes)")
                self.cfg = C.Config(path=self.cfg_path, mtime=0.0)
                self.expander = expand.Expander(self.cfg, self.usage, self.tags, front=self.target_install, log=log)
                self._set_slots([], None)
                self._warm_soon("no menus")        # drops a plan for the menus that went
            self._menus_problem(announce=fresh and balloon)
            return
        self._config_error = None
        self._menus_problem(clear=True)
        self._have_cfg = True
        self._theme = eff
        self._theme_sig = sig
        self.cfg = cfg
        self.expander = expand.Expander(cfg, self.usage, self.tags, front=self.target_install, log=log)
        self._set_slots([m for m in cfg.menus.values() if m.hotkey], cfg.browser_key, cfg.profile_key)
        for err in cfg.errors:
            log(f"config: {err}")
        log(f"config loaded: {len(cfg.menus)} menus, theme={eff}, hotkeys: "
            + ", ".join(f"{m.hotkey.text}->{m.id}" for m in self.slots)
            + f"; bridge mode={cfg.bridge_mode} key={cfg.bridge_key.text}"
            + f"; browser hotkey={cfg.browser_key.text if cfg.browser_key else None}"
            + f"; next profile hotkey={cfg.profile_key.text if cfg.profile_key else None}")
        self.expander.prefetch_recent()            # on recent.py's worker: the first ring finds the recent lists
        self._prefetch()
        self._prune_icons()
        self._schedule_prewarm()
        self._warm_soon("menus loaded")            # the first open finds its pictures drawn

    def _check_profile(self, notify=False):
        """Follows the profile pointer: when Studio or the tray has pointed it at another profile, switches to it."""
        if self._pinned:
            return
        if not self._frozen and profiles.too_new():
            self._freeze()
        if self._frozen:
            return
        sig = profiles.signature()
        if sig == self._profile_sig:
            return
        want = profiles.pointer()
        if not want or want == self.profile:
            self._profile_sig = sig
            return
        if not os.path.isfile(profiles.config_file(want)):     # a create or rename still in progress
            self._profile_wait += 1
            if self._profile_wait < 20:                        # about 10 s of ticks
                return
            log(f"profile: {want!r} never appeared; falling back")
            want = profiles.active()
            if want == self.profile:
                self._profile_sig = sig
                self._profile_wait = 0
                return
        if self.ring is not None or self._browser_pick is not None:
            return          # never under an open ring or a pending pick: the ring holds expander.resolve and the
                            # pick records into usage
        self._profile_wait = 0
        self._switch_profile(want, notify)
        self._profile_sig = sig

    def _freeze(self):
        """The files were made by a newer ZOrbit (it was installed over this running app, or a second copy ran).
        The app keeps working on what it has loaded, but never switches profile and never writes usage."""
        self._frozen = True
        msg = profiles.too_new()
        log(f"profiles: {msg} Nothing will be written or switched until ZOrbit is restarted.")
        if self.tray is not None:
            try:
                self.tray.set_tip(TIP_FROZEN)
                self.tray.notify("ZOrbit", msg)
            except Exception:
                log("tray notice failed:\n" + traceback.format_exc())

    def _switch_profile(self, name, notify=False):
        """Loads another profile's menus, tags and usage. The icons, the popout and the activity stay as they are."""
        try:
            log(f"profile: {self.profile} -> {name}")
            self.profile = name
            self.cfg_path = profiles.config_file(name)
            self.tags = tags.TagStore(profiles.tags_file(name))
            self.usage = usage.Usage(profiles.usage_file(name))     # new: its cache and picks must not carry over
            self._bad_sig = None
            self._config_error = None
            self._have_cfg = False      # a broken file then runs with no menus, not the old profile's ring
            self._activity_menu = None
            self.load_config(force=True, balloon=False)
            if self.tray is not None:
                self.tray.set_profile(name)
                if self._config_error:
                    self.tray.notify("ZOrbit cannot read the menus file", f"Profile {name}: {self._config_error}")
                elif notify:
                    self.tray.notify("ZOrbit", f"Profile: {name}")
        except Exception:
            log("profile switch failed:\n" + traceback.format_exc())

    def _set_slots(self, menus, browser_key, profile_key=None):
        """Sets the menus that have hotkeys and hands the hook thread the matching snapshot in one assignment."""
        self.slots = menus
        self._hook_state = HookState.build(menus, browser_key, profile_key)

    def _menus_problem(self, announce=False, clear=False):
        """Puts a menus file that cannot be read in the tray tooltip while it lasts (clear=True takes it out), and
        with announce shows a balloon once."""
        if self.tray is None:
            return
        try:
            if self._frozen:
                self.tray.set_tip(TIP_FROZEN)
                return
            if clear:
                self.tray.set_tip(None)
                return
            self.tray.set_tip(f"ZOrbit {paths.VERSION}: menus file cannot be read")
            if announce:
                self.tray.notify("ZOrbit cannot read your menus file",
                                 "Open Studio to fix it. The previous menus stay in use." if self._have_cfg
                                 else "Open Studio to fix it. No menus open until then.")
        except Exception:
            log("tray notice failed:\n" + traceback.format_exc())

    def _toast(self, text):
        """A short message near the cursor. Never raises."""
        try:
            import toast
            ring = self.cfg.ring if self.cfg else {}
            pre = theme.preset(ring.get("theme", "dark"))["toast"]
            text_colour = (ring.get("colors") or {}).get("text") or pre["text"]
            if theme.contrast(text_colour, pre["pill"]) < 3:      # a colour of the other theme: keep the message readable
                text_colour = pre["text"]
            toast.show(text, log, colour=text_colour, pill=pre["pill"])
        except Exception:
            log("toast failed:\n" + traceback.format_exc())

    def _prune_icons(self):
        """Drops cached icons of items no menu uses any more (best effort: one missed only costs a rebuild)."""
        if assets is None or not self._icons:
            return
        used = set()
        for m in self.cfg.menus.values():
            for it in m.items:
                used.add(self._icon_id(it))
                if it.kind == "tag":
                    tm = self.expander.tag_menu(it.data["tag"])
                    if tm is not None:
                        used.update(self._icon_id(i) for i in tm.items)
            if usage.auto_count(m):
                used.update(("brush", n) for n in self.usage.slots(m) if n)
        for key in [k for k in self._icons if k[:2] not in used]:
            del self._icons[key]

    def _prefetch(self):
        if assets is None:
            return
        pairs = set()
        for m in self.cfg.menus.values():
            for it in m.items:
                acts = it.data["steps"] if it.kind == "steps" else [it.data]
                pairs.update(g for g in map(C.asset_of, acts) if g)
        self.usage.load()
        for m in self.cfg.menus.values():
            if usage.auto_count(m):
                pairs.update(("brush", n) for n in self.usage.slots(m) if n)
            for it in m.items:
                if it.kind == "tag":               # warm the fan before it opens
                    tm = self.expander.tag_menu(it.data["tag"])
                    if tm is not None:
                        pairs.update(g for g in (C.asset_of(i.data) for i in tm.items) if g)
        size = THUMB_PX
        # Kept, so the ring warm-up waits for it: icon_for would otherwise decode on the main thread the same pictures
        # this thread is decoding and writing to the thumbnail cache. Every one still running is kept, not only the
        # newest: a second load can come while the first load's thread is still reading.
        t = threading.Thread(target=assets.prefetch, args=(sorted(pairs), size), daemon=True)
        self._prefetch_threads = [p for p in self._prefetch_threads if p.is_alive()] + [t]
        t.start()

    @staticmethod
    def _icon_kind(src):
        """The asset kind an explicit icon path decodes as. A .png is an image to show as it is, and anything
        that is not a file is a brush name."""
        ext = os.path.splitext(src)[1].lower()
        if ext == ".png" or not os.path.isfile(src):
            return "brush"
        if ext == ".zmt":
            return "material"
        if ext == ".exr":
            return "texture"
        return "alpha" if ext in assets.EXTS["alpha"] else "brush"

    def _icon_id(self, item):
        """(kind, src) of the picture an item shows: its icon path, else the asset it picks. None for neither."""
        src = item.icon
        kind = self._icon_kind(src) if src else "brush"
        if not src:
            acts = item.data["steps"] if item.kind == "steps" else [item.data]
            kind, src = next((g for g in map(C.asset_of, acts) if g), ("brush", ""))
        return (kind, src) if src else None

    def icon_for(self, item):
        if assets is None:
            return None
        ident = self._icon_id(item)
        if ident is None:
            return None
        kind, src = ident
        size = THUMB_PX
        try:
            mtime = os.stat(src).st_mtime_ns if os.path.isfile(src) else None   # a replaced file shows anew
        except OSError:
            mtime = None
        key = (kind, src, size, assets.generation, mtime)     # a rebuilt asset index shows anew too
        im = self._icons.get(key)
        if im is None:
            if src.lower().endswith(".png") and os.path.isfile(src):
                from PIL import Image
                im = Image.open(src).convert("RGBA")
            else:
                im = assets.thumbnail(kind, src, size)
            if im is not None:                 # a miss is not kept: the file may turn up later
                for old in [k for k in self._icons if k[:3] == key[:3]]:
                    del self._icons[old]       # the older versions of this picture
                self._icons[key] = im
        return im

    # --- target detection ------------------------------------------------------------------------
    def _exe_of(self, pid, cache=None):
        """Lowercased exe name of a process ('' when it cannot be read), cached. The hook thread passes its own
        cache (self._hook_exe) so that each dict has one thread writing and clearing it."""
        if cache is None:
            cache = self._pid_exe
        exe = cache.get(pid)
        if exe is None:
            exe = os.path.basename(W.process_image(pid)).lower()
            if len(cache) > 256:
                cache.clear()
            cache[pid] = exe
        return exe

    def target_in_front(self, on_hook=False) -> bool:
        """ZBrush is the foreground app. on_hook is True when the keyboard hook thread asks. (_unreadable is shared:
        a set add is atomic, and at worst a pid is logged twice.)"""
        fg = W.GetForegroundWindow()
        if not fg:
            return False
        pid = W.window_pid(fg)
        exe = self._exe_of(pid, self._hook_exe if on_hook else None)
        if not exe and pid not in self._unreadable and len(self._unreadable) < 20:
            self._unreadable.add(pid)
            log(f"foreground window's process could not be read (is ZBrush running as administrator?); "
                f"hotkeys ignored (pid {pid})")
        return exe == self.target_exe

    def target_install(self) -> dict | None:
        """The ZBrush installation of the foreground window (if that is ZBrush)."""
        fg = W.GetForegroundWindow()
        if not fg or not self.target_in_front():
            return None
        pid = W.window_pid(fg)
        if pid not in self._pid_install:
            if len(self._pid_install) > 32:
                self._pid_install.clear()
            try:
                self._pid_install[pid] = installs.install_of(W.process_image(pid))
            except Exception:
                self._pid_install[pid] = None
        return self._pid_install[pid]

    def _popout_in_front(self) -> bool:
        """The popout is the foreground app, so its hotkey must reach us to hand the keyboard back to ZBrush. The
        pid of its control window is cached for a second. Only the hook thread calls this, and so only it writes
        self._popout_pid."""
        fg = W.GetForegroundWindow()
        if not fg:
            return False
        now = time.time()
        until, pid = self._popout_pid
        if now >= until:
            hwnd = W.find_message_window(POPOUT_CLASS)
            pid = W.window_pid(hwnd) if hwnd else 0
            self._popout_pid = (now + 1.0, pid)
        return bool(pid) and W.window_pid(fg) == pid

    # --- keyboard hook ---------------------------------------------------------------------------
    def _on_key(self, wparam, kb) -> bool:
        """Returns True to swallow the key. Runs on the hook thread, so it only reads the immutable HookState and
        must stay fast: Windows drops slow hooks."""
        if (kb.flags & W.LLKHF_INJECTED) and kb.dwExtraInfo == W.OWN_INPUT_MARKER:
            return False                   # ZOrbit's own key; keys from tablet drivers and macro tools count
        state = self._hook_state            # read once: a config reload swaps the whole object
        ring = self.ring                    # read once; may close a moment later (see __init__)
        vk = kb.vkCode
        down = wparam in (W.WM_KEYDOWN, W.WM_SYSKEYDOWN)
        up = wparam in (W.WM_KEYUP, W.WM_SYSKEYUP)
        if self.held_vk is not None and vk == self.held_vk:
            if up:
                self.held_vk = None
                W.PostMessageW(self.ctrl, WM_APP_KEYUP, vk, 0)
            return self.held_swallow       # auto-repeat downs and the final up
        if self._browser_vk is not None and vk == self._browser_vk:
            if up:
                self._browser_vk = None
            return True                    # the browser key's repeats and key-up: never a ring's key-up
        if self._profile_vk is not None and vk == self._profile_vk:
            if up:
                self._profile_vk = None
            return True                    # the same for the next-profile key, whatever HookState says by now
        if down and vk == W.VK_ESCAPE and ring is not None:
            W.PostMessageW(self.ctrl, WM_APP_CANCEL, 0, 0)
            return True
        if not down or vk in W.MODIFIER_VKS:
            return False
        mods = (W.modifier_down(W.VK_CONTROL), W.modifier_down(W.VK_MENU), W.modifier_down(W.VK_SHIFT))
        ctrl, alt, shift = mods
        for hvk, hctrl, halt, hshift, swallow, slot in state.slots:
            if hvk == vk and (hctrl, halt, hshift) == mods:
                if not self.target_in_front(on_hook=True) or self._is_text_target(W.GetForegroundWindow()):
                    return False
                self.held_vk, self.held_swallow = vk, swallow
                W.PostMessageW(self.ctrl, WM_APP_OPEN, slot, 1)     # lparam 1: opened by a held key
                if swallow and alt:
                    W.PostMessageW(self.ctrl, WM_APP_MASK, 0, 0)
                return swallow
        if state.browser is not None and state.browser == (vk, ctrl, alt, shift):
            if ((self.target_in_front(on_hook=True) and not self._is_text_target(W.GetForegroundWindow()))
                    or self._popout_in_front()):
                self._browser_vk = vk          # not held_vk: a ring held open on another key keeps its own
                if alt:
                    W.PostMessageW(self.ctrl, WM_APP_MASK, 0, 0)
                W.PostMessageW(self.ctrl, WM_APP_BROWSER, 0, 0)
                return True
        if state.profile is not None and state.profile == (vk, ctrl, alt, shift):
            if self.target_in_front(on_hook=True) and not self._is_text_target(W.GetForegroundWindow()):
                self._profile_vk = vk
                if alt:
                    W.PostMessageW(self.ctrl, WM_APP_MASK, 0, 0)
                W.PostMessageW(self.ctrl, WM_APP_PROFILE, 0, 0)
                return True
        if ring is not None and ring.mode == "click":
            W.PostMessageW(self.ctrl, WM_APP_TYPING, 0, 0)     # typing closes a ring that was tapped open
        return False

    def _on_hook_command(self, msg, wparam, lparam):
        """A thread message to the hook thread. This is how the main thread changes held_vk, _browser_vk and
        _profile_vk, so that only the hook thread ever writes them. A key is let go only if it is still the one that
        was seen stuck: it may have come up, or another one gone down, since."""
        if msg == WM_HOOK_RELEASE_HELD and self.held_vk == wparam:
            self.held_vk = None
            W.PostMessageW(self.ctrl, WM_APP_KEYUP, wparam, 0)
        elif msg == WM_HOOK_RELEASE_BROWSER and self._browser_vk == wparam:
            self._browser_vk = None
        elif msg == WM_HOOK_RELEASE_PROFILE and self._profile_vk == wparam:
            self._profile_vk = None

    @staticmethod
    def _is_text_target(fg) -> bool:
        """The foreground window is a native Windows dialog, or has a text box in focus. Nothing is cached: the
        focus moves between key presses. ZBrush draws its own text fields, so those are not seen here."""
        if not fg:
            return False
        if W.class_name(fg) == DIALOG_CLASS:
            return True
        return W.class_name(W.focus_window(fg)) in TEXT_CLASSES

    def _held_down(self) -> bool:
        return self.held_vk is not None and W.key_down(self.held_vk)

    def _check_stuck_keys(self):
        """The hook is what clears held_vk, _browser_vk and _profile_vk. If it missed a key-up (Windows dropped it,
        or another program ate the key) the hotkey would stay dead, so this tick covers for it. A key the hook
        swallows never shows in GetAsyncKeyState, so those can only be let go after STUCK_KEY_S with no ring open.
        This only reads the keys; letting go is a message to the hook thread, which owns them."""
        vk = self.held_vk
        if vk is not None and not self.held_swallow and not W.key_down(vk):
            self._stuck["up"] = self._stuck.get("up", 0) + 1     # twice in a row: the key state may lag the hook
            if self._stuck["up"] >= 2:
                log(f"hotkey (vk {vk:#x}) is up but the hook never saw it; released")
                self._hook_post(WM_HOOK_RELEASE_HELD, vk)
        else:
            self._stuck.pop("up", None)
        now = time.monotonic()
        for name, on in (("held", self.held_vk is not None and self.ring is None),
                         ("browser", self._browser_vk is not None),
                         ("profile", self._profile_vk is not None)):
            if not on:
                self._stuck.pop(name, None)
            elif now - self._stuck.setdefault(name, now) >= STUCK_KEY_S:
                del self._stuck[name]
                log(f"{name} hotkey still down after {STUCK_KEY_S} s and the hook never saw it go up; released")
                if name == "held":
                    self._hook_post(WM_HOOK_RELEASE_HELD, self.held_vk or 0)
                elif name == "browser":
                    self._hook_post(WM_HOOK_RELEASE_BROWSER, self._browser_vk or 0)
                else:
                    self._hook_post(WM_HOOK_RELEASE_PROFILE, self._profile_vk or 0)

    def start_hook(self):
        """Starts the hook thread and waits for it to install the hook. Raises if it cannot."""
        self._hook = HookThread(self._on_key, self._on_hook_command, log)
        self._hook.start_and_wait()

    def stop_hook(self):
        hook, self._hook = self._hook, None
        if hook is not None:
            hook.stop()

    def _hook_post(self, msg, wparam=0):
        if self._hook is None or not self._hook.post(msg, wparam):
            log(f"could not reach the hook thread (message {msg:#x})")

    # --- control window --------------------------------------------------------------------------
    def _ctrl_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_APP_OPEN:
                self.open_slot(wparam, held=bool(lparam))
                return 0
            if msg == WM_APP_KEYUP:
                if self.ring is not None:
                    self.ring.key_released()
                return 0
            if msg == WM_APP_CANCEL:
                if self.ring is not None:
                    self.ring.cancel("escape")
                return 0
            if msg == WM_APP_TYPING:
                if self.ring is not None and self.ring.mode == "click":
                    self.ring.cancel("typing")
                return 0
            if msg == WM_APP_MASK:
                W.send_keys([(W.VK_MENU_MASK, False), (W.VK_MENU_MASK, True)])
                return 0
            if msg == WM_APP_BROWSER:
                if self.ring is not None:
                    self.ring.cancel("browser")
                self.open_browser(None, toggle=True)
                return 0
            if msg == WM_APP_BROWSER_PICK:
                self._browser_pick_queued()
                return 0
            if msg == WM_APP_COMMAND:
                self._run_command()
                return 0
            if msg == WM_APP_PROFILE:
                self._hotkey_profile()
                return 0
            if msg == W.WM_COPYDATA:
                return self._on_copydata(wparam, lparam)
            if msg == W.WM_TIMER:
                if wparam == TIMER_WATCH:
                    self._watch_target()
                    self._recent_tick()
                elif wparam == TIMER_ACK:
                    self._check_ack()
                elif wparam == TIMER_REHOOK and self.ring is None and not self._held_down():
                    self._hook_post(WM_HOOK_REHOOK)     # Windows silently drops hooks that ever timed out
                elif wparam == TIMER_CONFIG:
                    self._check_stuck_keys()
                    self._check_profile()       # before load_config, so a renamed-away path is never read first
                    self._check_library_folders()
                    self.load_config()          # a new or changed hotkey must work before any ring opens
                    self._check_warm_scale()
                elif wparam == TIMER_RING_WARM:
                    self._warm_tick()
                elif wparam == TIMER_BROWSER_PICK:
                    self._browser_pick_tick()
                elif wparam == TIMER_PREWARM:
                    W.KillTimer(self.ctrl, TIMER_PREWARM)
                    self._prewarm()
                elif wparam == TIMER_POPOUT_SHOW:
                    self._popout_show_tick()
                elif wparam == TIMER_ZS_RESULT:
                    self._zs_result_tick()
                elif wparam == TIMER_APPLY:
                    self._apply_tick()
                elif wparam == TIMER_COMMAND:
                    W.KillTimer(self.ctrl, TIMER_COMMAND)
                    self._run_command()
                return 0
        except Exception:
            log("control error:\n" + traceback.format_exc())
            return 0
        return W.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _create_ctrl(self):
        proc = W.WNDPROC(self._ctrl_proc)
        self._refs_ctrl = proc
        wc = W.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(W.WNDCLASSEXW)
        wc.lpfnWndProc = proc
        wc.hInstance = W.GetModuleHandleW(None)
        wc.lpszClassName = "ZOrbitControl"
        if not W.RegisterClassExW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.ctrl = W.CreateWindowExW(0, "ZOrbitControl", "ZOrbit control", 0, 0, 0, 0, 0,
                                      W.HWND_MESSAGE, None, wc.hInstance, None)
        if not self.ctrl:
            raise ctypes.WinError(ctypes.get_last_error())

    # --- tray icon -------------------------------------------------------------------------------
    def _create_tray(self):
        if self.no_tray:
            return
        try:
            from tray import Tray
            source = None if self._pinned else (lambda: (profiles.names(), self.profile))
            tray = Tray(f"ZOrbit {paths.VERSION}", paths.ICON, self._tray_command, log, profile_source=source)
            self.tray = tray
            ok = tray.create()
            if not self._pinned:
                tray.set_profile(self.profile)
            log(f"tray icon {'added' if ok else 'not added yet (will retry)'}")
        except Exception:
            log("tray unavailable:\n" + traceback.format_exc())

    def _destroy_tray(self):
        tray, self.tray = self.tray, None
        if tray is None:
            return
        try:
            tray.destroy()
        except Exception:
            log("tray destroy error:\n" + traceback.format_exc())

    def _tray_command(self, name):
        try:
            if name == "browser":
                log("tray: opening the browser")
                self.open_browser(None, toggle=False)
            elif name == "studio":
                subprocess.Popen(paths.launch_commands()["studio"], env=paths.clean_env(),
                                 creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                                 close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                log("tray: opening the Studio")
            elif name == "reload":
                self.load_config(force=True, balloon=False)
                if self._config_error:
                    log(f"tray: reload failed: {self._config_error}")
                    if self.tray is not None:
                        self.tray.notify("ZOrbit cannot read your menus file", self._config_error)
                else:
                    log("tray: menus reloaded")
                    if self.tray is not None:
                        self.tray.notify("ZOrbit", "Menus reloaded")
            elif name.startswith("profile:"):
                try:
                    profiles.set_active(name[len("profile:"):])
                except profiles.ProfileError as e:
                    log(f"tray: {e}")
                    if self.tray is not None:
                        self.tray.notify("ZOrbit", str(e))
                else:
                    self._check_profile(notify=True)
            elif name == "logs":
                os.makedirs(paths.DATA_DIR, exist_ok=True)
                os.startfile(paths.DATA_DIR)
            elif name == "quit":
                log("tray: quit requested")
                W.PostQuitMessage(0)
        except Exception:
            log(f"tray command {name!r} failed:\n" + traceback.format_exc())

    # --- menus -----------------------------------------------------------------------------------
    def open_slot(self, slot, held=True):
        """held: the hotkey was down when the hook saw it (the hook says so in the message, because by the time
        this runs the key may be up already)."""
        self._check_profile()
        self.load_config()                         # picks up edits to radial.json on every open
        if slot >= len(self.slots):
            return
        menu = self.slots[slot]
        if self.ring is not None:
            same = self.ring.menu.id == menu.id
            self.ring.cancel("reopened")
            if same:
                return                             # pressing the hotkey again closes the ring
        self.open_menu(menu, W.cursor_pos(), held=held)

    def _record_pick(self, item):
        """Notes a brush, alpha, material or texture pick in the recent list; a brush pick is also counted for the
        auto slots, and every menu's auto slots react to it."""
        if item.kind not in C.ASSET_KINDS:
            return
        self.usage.load()
        self.usage.record_pick(item.kind, item.data[item.kind])
        if item.kind == "brush":                  # the auto slots follow brushes only
            autos = [m for m in self.cfg.menus.values() if usage.auto_count(m)]
            # What the rings last showed (and warm-up drew): a copy of the stored slots. Not slots(), which would fill
            # an empty slot from the ranking before this pick is counted, and so change where the pick lands.
            shown = [list(self.usage.menus.get(m.id, {}).get("slots", [])) for m in autos]
            self.usage.record(item.data["brush"])
            for m in autos:
                before = self.usage.slots(m)
                self.usage.update(m)
                after = self.usage.menus[m.id]["slots"]
                if after != before:
                    log(f"auto slots of '{m.id}': {before} -> {after}")
            self.usage.menus = {m.id: self.usage.menus[m.id] for m in autos}
            if shown != [self.usage.menus[m.id]["slots"] for m in autos]:
                # an empty slot took the brush, or one gave way: warm-up walks past what it has and draws the new slots
                self._warm_soon("auto slots changed", RING_WARM_PICK_MS)
        if self._frozen:                          # files of a newer ZOrbit: never written
            return
        try:
            self.usage.save()
        except OSError as e:
            log(f"could not save usage.json: {e!r}")

    def open_menu(self, menu, pos, held, nested=False):
        from ring import Ring
        menu = self.expander.menu(menu)
        ring = Ring(menu, self.cfg.ring, self.icon_for, self._on_ring_done, log, held=held, nested=nested,
                    submenus=self.expander.resolve)
        self.ring = ring
        try:
            ring.show(*pos)
        except Exception:
            log("could not show ring:\n" + traceback.format_exc())
            self.ring = None
            return
        self._ring_centre = pos
        self.activity.note_open(menu.id, nested)
        if not nested:
            self._activity_menu = menu.id

    def _on_ring_done(self, item, reason, at=None):
        self.ring = None
        if item is None:
            return
        if item.kind == "menu":
            sub = self.expander.resolve(item.data["menu"])
            if sub is not None and at is not None:  # flicked or hovered: centred on its slot, still held if so
                self.open_menu(sub, at, held=self.held_vk is not None, nested=True)
            elif sub is not None:
                self.open_menu(sub, W.cursor_pos(), held=False)   # re-centred on the pick
            else:
                log(f"submenu '{item.data['menu']}' has no usable items; nothing opened")
                self._toast(MSG_EMPTY_MENU)
            return
        if item.kind == "empty":                    # the ring cannot pick one; a guard
            log("empty slot picked; nothing sent")
            return
        if item.kind in ("auto", "tag", "recent"):
            log(f"empty {item.kind} slot picked; nothing sent")
            self._toast(MSG_EMPTY_SLOT)
            return
        if item.kind == "browser":
            self.open_browser(item.data["browser"] or None, kind=item.data.get("kind"))
            return
        self.send(item)
        try:
            self._record_pick(item)
        except Exception:
            log("usage error:\n" + traceback.format_exc())

    # --- ring warm-up --------------------------------------------------------------------------
    # After the menus load, the pictures the next open will look for are drawn on this thread, one per timer tick,
    # so the first press of a hotkey finds them: each hotkey menu (its slots, its sprites and the static layer with
    # the hold hint), then the slots and lines of the fans they open, then the rings their slots open one level
    # down, then the static layers with the click hint a tap leaves. It stops where a ring cache would be fuller than
    # RING_WARM_SHARE. Nothing runs while a ring is open or a pick is on its way, and a hotkey waits for at most the
    # one picture being drawn. Any change throws the plan away and starts a new one RING_WARM_WAIT_MS later.
    def _warm_soon(self, why, wait_ms=RING_WARM_WAIT_MS):
        """Drops the warm-up plan and starts a new one wait_ms after the last call, so a run of changes (Studio saves
        on every step of a slider drag) starts one warm-up. A picture already there is walked past, not drawn again."""
        self._warm_gen += 1
        self._warm = None
        self._warm_why = why
        if self.ctrl is not None:
            W.SetTimer(self.ctrl, TIMER_RING_WARM, wait_ms, None)

    def _zbrush_monitor(self):
        """(work area, scale) of the monitor holding ZBrush's window when ZBrush is in front, else None. Each answer is
        kept in _zb_monitor, so warm-up planned while another program is in front (Studio saving) still uses it."""
        fg = W.GetForegroundWindow()
        if not fg or not self.target_in_front():
            return None
        self._zb_monitor = W.monitor_for_window(fg)
        return self._zb_monitor

    def _warm_target(self):
        """(work area, scale) of the monitor the next ring most likely opens on: ZBrush's, in front now or where it
        was last seen in front, else (ZBrush not seen yet) the primary one, which holds the point 0, 0."""
        return self._zbrush_monitor() or self._zb_monitor or W.monitor_for_point(0, 0)

    def _check_warm_scale(self):
        """On the config tick: notes ZBrush's monitor while it is in front, and warms again when that monitor's scale
        is not the one the last warm-up was planned for (ZBrush moved to another monitor, or the scale changed). Focus
        moving to another program is no change."""
        mon = self._zbrush_monitor()
        if mon is None or self._warm_scale is None or self.ctrl is None:
            return
        if mon[1] != self._warm_scale:
            self._warm_scale = mon[1]
            self._warm_soon("display scale changed")

    def _warm_busy(self, w=None) -> bool:
        """Something comes first: a ring is open or its hotkey is down, a pick is on its way to ZBrush, the menus'
        thumbnails are still being read, or (for a plan w with recent slots, until its deadline) the first answer about
        ZBrush's recent files has not come yet, so the Recent fan is not planned empty."""
        if (self.ring is not None or self.held_vk is not None or self._ack is not None
                or self._browser_pick is not None or bool(self._commands) or self._apply_watch is not None
                or any(t.is_alive() for t in self._prefetch_threads)):
            return True
        if w is None or not w["recent"] or time.monotonic() >= w["recent_until"]:
            return False
        limit = self.expander._tag_limit()
        return not all(recent.known(kind, limit) for kind in w["recent"])

    def _warm_plan(self):
        """A new plan, as _warm_tick keeps it."""
        work, scale = self._warm_target()
        self._warm_scale = scale
        kinds = {it.data.get("recent") for m in self.cfg.menus.values() for it in m.items if it.kind == "recent"}
        now = time.monotonic()
        return {"gen": self._warm_gen, "jobs": self._warm_jobs(work, scale), "limits": self._warm_limits(),
                "want": {}, "drawn": 0, "found": 0, "ms": 0.0, "longest": 0.0, "steps": 0, "at": now, "scale": scale,
                "full": False, "why": self._warm_why,
                "recent": sorted(k for k in kinds if isinstance(k, str)), "recent_until": now + RING_WARM_RECENT_S}

    @staticmethod
    def _warm_limits():
        """{cache: (entries, bytes)} warm-up may fill: RING_WARM_SHARE of each ring cache's bounds."""
        import ring as R
        k = RING_WARM_SHARE
        return {"slot": (int(R.SLOT_SPRITES * k), float("inf")), "menu": (int(R.SPRITE_MENUS * k), float("inf")),
                "static": (int(R.STATIC_LAYERS * k), int(R.STATIC_BYTES * k)),
                "lines": (int(R.FAN_LINE_IMAGES * k), int(R.FAN_LINE_BYTES * k))}

    def _warm_jobs(self, work, scale):
        """The warm-up plan as Ring.warm_jobs jobs, most wanted first, each ring built the way open_menu builds it."""
        from ring import Ring
        resolve = self.expander.resolve

        def ring_of(menu, nested=False):
            return Ring.for_warmup(self.expander.menu(menu), self.cfg.ring, self.icon_for, resolve, work, scale, nested)
        hot, seen = [], set()
        for m in self.slots:                       # the hotkey menus, in full
            if m.id in seen:
                continue
            seen.add(m.id)
            r = ring_of(m)
            hot.append(r)
            yield from r.warm_jobs("menu")
        for r in hot:                              # their fans
            yield from r.warm_jobs("fans")
        subs = []
        for r in hot:                              # the rings their slots open, one level down
            for mid in r.ring_submenus():
                if mid in seen:
                    continue
                seen.add(mid)
                sub = resolve(mid)
                if sub is None or not sub.items:
                    continue
                s = ring_of(sub, nested=True)
                subs.append(s)
                yield from s.warm_jobs("menu")
        for r in hot + subs:                       # the click hint, as a tap leaves it
            yield from r.warm_jobs("click")

    def _warm_tick(self):
        """One warm-up step: plans when the wait is over, then draws one picture (walking past those already there),
        and kills its timer when the plan is done or the caches would hold no more."""
        w = self._warm
        if w is not None and w["gen"] != self._warm_gen:      # made for menus that have changed since
            w = self._warm = None
        if w is None and (self.cfg is None or not self.slots or self.expander is None):
            W.KillTimer(self.ctrl, TIMER_RING_WARM)
            return
        t0 = time.perf_counter()
        done = False
        try:
            if w is None:
                w = self._warm = self._warm_plan()
            if self._warm_busy(w):
                W.SetTimer(self.ctrl, TIMER_RING_WARM, RING_WARM_HOLD_MS, None)
                return
            W.SetTimer(self.ctrl, TIMER_RING_WARM, RING_WARM_STEP_MS, None)
            t0 = time.perf_counter()
            while True:
                job = next(w["jobs"], None)
                if job is None:
                    done = True
                    break
                cache, key, size, run = job
                want = w["want"].setdefault(cache, {})
                if key not in want:
                    entries, budget = w["limits"][cache]
                    if len(want) + 1 > entries or sum(want.values()) + size > budget:
                        w["full"] = done = True
                        break
                    want[key] = size
                if run():
                    w["drawn"] += 1
                    break
                w["found"] += 1
                if time.perf_counter() - t0 > RING_WARM_TICK_S:
                    break
        except Exception:                          # planning or a picture failed: said once, and the plan goes
            log("ring warm-up error; the rest of this warm-up is dropped:\n" + traceback.format_exc())
            W.KillTimer(self.ctrl, TIMER_RING_WARM)
            self._warm = None
            return
        ms = (time.perf_counter() - t0) * 1000
        w["ms"] += ms
        w["longest"] = max(w["longest"], ms)
        w["steps"] += 1
        if not done:
            return
        W.KillTimer(self.ctrl, TIMER_RING_WARM)
        self._warm = None
        if w["drawn"] or w["full"]:
            log(f"ring warm-up ({w['why']}): {w['drawn']} pictures drawn, {w['found']} already there, "
                f"{w['ms']:.0f} ms in {w['steps']} steps (longest {w['longest']:.0f} ms) over "
                f"{time.monotonic() - w['at']:.1f} s at scale {w['scale']:.2f}"
                + ("; stopped where the ring caches would hold no more" if w["full"] else ""))

    # --- browser popout ------------------------------------------------------------------------
    @property
    def browser_key(self):
        return self.cfg.browser_key if self.cfg else None

    def _spawn_popout(self, show, tag=None, zb_hwnd=0, kind=None):
        """Starts the popout process on a worker thread, so a slow process start never holds up the control
        window."""
        cmd = paths.launch_commands()["popout"] + ["--managed"]
        if show:
            cmd.append("--show")
            if tag:
                cmd += ["--tag", tag]
            if kind:
                cmd += ["--kind", kind]
            cmd += ["--zbrush-hwnd", str(zb_hwnd)]
        self._popout_started, self._popout_show, self._popout_spawning = time.time(), show, True

        def start():
            try:
                p = self._popout_proc = subprocess.Popen(
                    cmd, env=paths.clean_env(),
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log(f"popout started: {cmd}")
            except Exception:
                self._popout_proc = None
                log(f"could not start the popout {cmd}:\n" + traceback.format_exc())
                return
            finally:
                self._popout_spawning = False
            try:                                   # this thread has nothing else to do: it sees how the process ends
                code = p.wait()
                if code == POPOUT_EXIT_IDLE:       # its own choice (browser.quit_after_minutes), not a failure
                    self._popout_idle_quit = p
                    log("browser: the popout quit after sitting unused (browser.quit_after_minutes); "
                        "it starts again when it is asked for")
                else:
                    log(f"popout exited with code {code}" + (" (popout.log says why)" if code else ""))
            except Exception:
                log("could not wait for the popout:\n" + traceback.format_exc())
        threading.Thread(target=start, daemon=True).start()

    def open_browser(self, tag=None, toggle=False, kind=None):
        """Shows the browser, starting its process if none is running. kind: the tab to open on (brush, alpha,
        material, texture; None keeps the one it was last on). toggle (the hotkey): if it is already the front
        window, ZBrush gets the keyboard back instead; the window itself stays open."""
        kind = kind if kind in C.ASSET_KINDS else None
        fg = W.GetForegroundWindow()
        if fg and self.target_in_front():          # remembered for the pick: the popout takes the focus away
            self._popout_zb = (int(fg), self.target_install())
        zb = self._popout_zb[0] if self._popout_zb else 0
        hwnd = W.find_message_window(POPOUT_CLASS)
        if hwnd:
            payload = json.dumps({"tag": tag or None, "kind": kind, "zbrush_hwnd": zb,
                                  "toggle": bool(toggle)}).encode("utf-8")
            r = W.send_copydata(hwnd, COPYDATA_SHOW, payload)
            log(f"browser: SHOW sent to popout {hwnd} (tag={tag or None}, kind={kind}, toggle={bool(toggle)}, "
                f"zbrush={zb}): "
                + ("no answer within 0.5 s" if r is None else f"result {r}"))
            if r is None and not W.find_message_window(POPOUT_CLASS):
                r = SHOW_QUITTING                  # the window went away while we asked
            if r != SHOW_QUITTING:
                return
            # It sat unused and is quitting. A new one waits for it to be gone (popout.main) and then shows itself, so
            # this press is not lost; _spawning() below keeps a second press from starting a third.
            log("browser: the popout is quitting; starting a new one")
        self._prewarmed = False                    # the popout is gone: the next config load may warm it again
        if self._spawning():
            if self._popout_show:
                log("popout starting; ignoring")    # it shows itself when it is up
            else:                                  # a pre-warm is still coming up: show it as soon as it is there
                self._popout_pending = (tag, bool(toggle), kind)
                W.SetTimer(self.ctrl, TIMER_POPOUT_SHOW, 100, None)
                log("popout warming up; showing it when it is ready")
            return
        self._spawn_popout(True, tag, zb, kind)

    def _spawning(self) -> bool:
        """A popout we started is still coming up: its process lives and has had less than POPOUT_START_S."""
        if time.time() - self._popout_started >= POPOUT_START_S:
            return False
        p = self._popout_proc
        return self._popout_spawning or (p is not None and p.poll() is None)

    def _popout_show_tick(self):
        pend = self._popout_pending
        if pend is None:
            W.KillTimer(self.ctrl, TIMER_POPOUT_SHOW)
            return
        if W.find_message_window(POPOUT_CLASS):
            W.KillTimer(self.ctrl, TIMER_POPOUT_SHOW)
            self._popout_pending = None
            # it was not up yet: a toggle must not hand the focus away
            self.open_browser(pend[0], toggle=False, kind=pend[2])
        elif not self._spawning():
            W.KillTimer(self.ctrl, TIMER_POPOUT_SHOW)
            self._popout_pending = None
            log("popout did not come up; the next press starts it again")

    def _wants_browser(self) -> bool:
        cfg = self.cfg
        return bool(cfg and (cfg.browser_key or any(it.kind == "browser" for m in cfg.menus.values()
                                                    for it in m.items)))

    def _schedule_prewarm(self):
        """Starts the popout hidden a few seconds after launch, so the first press is quick. A one-shot timer:
        loading the config must not wait for a process start."""
        if self._popout_idle_quit_stands():
            return
        if self.ctrl is None or self._prewarmed or not self._wants_browser():
            return
        self._prewarmed = True
        W.SetTimer(self.ctrl, TIMER_PREWARM, 3000, None)

    def _popout_idle_quit_stands(self) -> bool:
        """The popout we last started quit by itself after sitting unused, and the setting is still on: it stays gone
        until someone asks for it (a press starts it; a config load or profile switch must not). Turning the setting
        off lets it be pre-warmed again."""
        if self._popout_idle_quit is None or self._popout_idle_quit is not self._popout_proc:
            return False
        if self.cfg is not None and self.cfg.browser_quit_minutes:
            return True
        self._popout_idle_quit, self._prewarmed = None, False
        return False

    def _prewarm(self):
        if W.find_message_window(POPOUT_CLASS) or self._spawning() or self._popout_idle_quit_stands():
            return
        log("browser: pre-warming the popout")
        self._spawn_popout(False)

    def _on_copydata(self, wparam, lparam) -> int:
        """WM_COPYDATA from the popout, or a command from another program: 1 = accepted, 0 = refused. Only a kind and
        a name are taken from the popout's payload; the file is looked up by send() as for any other pick."""
        try:
            cds = W.COPYDATASTRUCT.from_address(lparam)
            if cds.dwData not in (COPYDATA_PICK, COPYDATA_COMMAND) or not cds.lpData or not 0 < cds.cbData <= 4096:
                log(f"copydata refused: dwData={cds.dwData} cbData={cds.cbData}")
                return 0
            raw = ctypes.string_at(cds.lpData, cds.cbData)     # copied here: the sender's buffer dies on return
            msg = json.loads(raw.decode("utf-8"))
        except (ValueError, OSError) as e:                     # includes UnicodeDecodeError, JSONDecodeError
            log(f"copydata refused: unreadable payload ({e!r})")
            return 0
        if cds.dwData == COPYDATA_COMMAND:
            return self._take_command(msg)
        name = msg.get("name") if isinstance(msg, dict) else None
        if (not isinstance(msg, dict) or msg.get("v") != 1 or msg.get("op") != "pick"
                or msg.get("kind") not in C.ASSET_KINDS or not commands.good_name(name)):
            log(f"copydata refused: not a valid pick ({str(msg)[:80]!r})")
            return 0
        kind = msg["kind"]
        self._browser_pick = C.Item(label=name, kind=kind, data={kind: name})
        W.PostMessageW(self.ctrl, WM_APP_BROWSER_PICK, 0, 0)
        return 1

    # --- commands from other programs ------------------------------------------------------------
    def _take_command(self, msg) -> int:
        """A command from commands.py: 1 = taken, 0 = refused, which becomes its exit code. This only checks: the sender
        is waiting in SendMessage, so a ring or a hand-off runs on the next message (_run_command)."""
        why = commands.check(msg)
        if why:
            log(f"command refused: {commands.describe(msg)}: {why}")
            return 0
        why, pid = self._command_refusal(msg)
        if why:
            log(f"command refused: {commands.describe(msg)}: {why}")
            self._commands.append((lambda: self._toast(why), False))
            W.PostMessageW(self.ctrl, WM_APP_COMMAND, 0, 0)
            return 0
        log(f"command: {commands.describe(msg)}")
        self._commands.append((lambda: self._do_command(msg, pid), msg["op"] in ("pick", "press", "set", "toggle")))
        W.PostMessageW(self.ctrl, WM_APP_COMMAND, 0, 0)
        return 1

    def _command_refusal(self, msg):
        """(why this command cannot run now, or None; the process id of the ZBrush a pick goes to)."""
        op = msg["op"]
        if op == "browser":
            tag = msg.get("tag")
            return (f"There is no tag called {tag}" if tag and not self.tags.has(tag) else None), None
        if op == "profile":
            name = msg["name"]
            if self._pinned:
                return MSG_COMMAND_PINNED, None
            if self._frozen:
                return MSG_COMMAND_FROZEN, None
            return (None if name == "next" or profiles.canonical(name) else f"There is no profile called {name}"), None
        if self.cfg is None:
            return MSG_COMMAND_NO_MENUS, None
        if op == "open":
            if msg["menu"] not in self.cfg.menus:
                return f"There is no menu called {msg['menu']}", None
            if not self.target_in_front():         # like a hotkey: a ring only opens over ZBrush
                return MSG_NOT_FRONT, None
        return self._command_zbrush()

    def _command_zbrush(self):
        """(why not, or None; the process id of the ZBrush a command's pick goes to). ZOrbit never takes the focus. With
        ZBrush in front a command goes where a ring pick would. Behind another window it can only be the listener of
        the one ZBrush running, since the bridge key needs ZBrush in front."""
        fg = W.GetForegroundWindow()
        if self.target_in_front():
            return (MSG_COMMAND_TEXT, None) if self._is_text_target(fg) else (None, W.window_pid(fg))
        if self.cfg.bridge_mode in ("auto", "message"):
            pids = W.pids_named(self.target_exe)
            if len(pids) == 1 and self._listener(pids[0]) is not None:
                return None, pids[0]
        return MSG_NOT_FRONT, None

    def _run_command(self):
        """Runs what is queued, in order. A pick waits while the last pick's request has not been taken: there is one
        request file, so a second pick would replace the first (a Stream Deck multi-action sends them close together).
        After COMMAND_WAIT_S it goes anyway, as a ring pick would, since the first may be waiting for a long stroke."""
        while self._commands:
            run, is_pick = self._commands[0]
            if is_pick and os.path.exists(REQUEST_FILE):
                now = time.monotonic()
                if self._command_wait is None:
                    self._command_wait = now + COMMAND_WAIT_S
                if now < self._command_wait:
                    W.SetTimer(self.ctrl, TIMER_COMMAND, 30, None)
                    return
            self._command_wait = None
            self._commands.popleft()
            try:
                run()
            except Exception:                      # the rest must not sit here until some later command runs them
                log("command failed:\n" + traceback.format_exc())

    def _do_command(self, msg, pid):
        op = msg["op"]
        if op == "profile":
            self._command_profile(msg["name"])
            return
        again = op == "open" and self.ring is not None and self.ring.menu.id == msg["menu"]
        if self.ring is not None:
            self.ring.cancel("command")
        if op == "browser":
            self.open_browser(msg.get("tag"), kind=msg.get("kind"))
        elif op == "open":
            if not again:                          # opening it again closes it, like pressing its hotkey again
                self._command_open(msg["menu"])
        else:
            self._command_pick(msg, pid)

    def _command_open(self, menu_id):
        self._check_profile()
        self.load_config()
        menu = self.cfg.menus.get(menu_id)
        if menu is None:                           # the menus file changed since the check
            log(f"command: there is no menu {menu_id!r} any more")
            self._toast(f"There is no menu called {menu_id}")
            return
        self.open_menu(menu, W.cursor_pos(), held=False)      # no key is held: it opens as a tapped hotkey does

    def _command_pick(self, msg, pid):
        op = msg["op"]
        if op == "pick":
            kind, name = msg["kind"], msg["name"]
            item = C.Item(label=name, kind=kind, data={kind: name})
        else:
            data = {op: msg["path"]}
            if op == "set":
                data["value"] = msg["value"]
            item = C.Item(label=msg["path"].split(":")[-1], kind=op, data=data)
        self.send(item, source="command", pid=pid)
        try:
            known = self._known_item(item)
            if known is not None:
                self._record_pick(known)
        except Exception:
            log("usage error:\n" + traceback.format_exc())

    @staticmethod
    def _known_item(item):
        """The item to count in Recent and the auto slots. A ring or browser pick comes from a known item, but a command
        is typed, so a mistyped name must not go in, and another spelling must not replace the file's. None for an
        asset with no file; anything else is the item itself, which _record_pick leaves alone unless it is an asset."""
        if item.kind not in C.ASSET_KINDS:
            return item
        path = assets.find(item.kind, item.data[item.kind]) if assets is not None else None
        if path is None:
            return None
        name = assets.name_of(item.kind, item.data[item.kind])      # the listed name: a qualified one such as "10 (PackA)"
        if name is None:
            name = os.path.splitext(os.path.basename(str(path)))[0]
        return C.Item(label=name, kind=item.kind, data={item.kind: name})

    def _hotkey_profile(self):
        """The next-profile hotkey: what ZOrbit.exe --profile next does, with the same refusals."""
        why = self._command_refusal({"op": "profile", "name": "next"})[0]
        if why:
            log(f"profile hotkey refused: {why}")
            self._toast(why)
            return
        log("profile hotkey: next")
        self._command_profile("next", from_hotkey=True)
    def _command_profile(self, name, from_hotkey=False):
        names = profiles.names()
        if name == "next" and names:
            name = names[(names.index(self.profile) + 1) % len(names)] if self.profile in names else names[0]
        else:
            name = profiles.canonical(name) or name
        if self.ring is not None:                  # a profile never switches under an open ring
            self.ring.cancel("command")
        try:
            profiles.set_active(name)
        except (profiles.ProfileError, OSError) as e:
            log(f"command: profile not switched: {e}")
            self._toast(str(e))
            return
        self._check_profile()
        if from_hotkey and self.profile == name and self.cfg is not None and self.cfg.profile_key is None:
            self._toast(f"Profile: {name} (no next-profile hotkey here)")     # a one-way stop: say so on arrival
            return
        self._toast(f"Profile: {name}")

    def _browser_pick_queued(self):
        """The popout hands the focus back to ZBrush before it sends the pick, but activation finishes on its own
        time and press_bridge_key refuses while ZBrush is not in front: wait for it (at most 0.5 s)."""
        ins = self._popout_zb[1] if self._popout_zb else None
        legacy = ins is not None and not ins["python"]      # only the bridge key can reach it: needs the focus
        self._browser_pick_deadline = time.time() + (2.0 if legacy else 0.5)
        W.SetTimer(self.ctrl, TIMER_BROWSER_PICK, 30, None)

    def _browser_pick_tick(self):
        item = self._browser_pick
        if item is None:
            W.KillTimer(self.ctrl, TIMER_BROWSER_PICK)
            return
        ins = self._popout_zb[1] if self._popout_zb else None
        legacy = ins is not None and not ins["python"]
        in_front = self.target_in_front()
        by_message = not legacy and self.cfg.bridge_mode in ("auto", "message")      # key mode needs the focus
        if not (in_front or (by_message and self._listener(self._browser_zb_pid()) is not None)
                or time.time() >= self._browser_pick_deadline):
            return
        W.KillTimer(self.ctrl, TIMER_BROWSER_PICK)
        self._browser_pick = None
        if legacy and not in_front:
            log(f"pick from browser {item.kind} '{item.label}' dropped: ZBrush did not get the focus back in 2 s")
            return
        log(f"pick from browser {item.kind} '{item.label}'")
        self.send(item, install=ins, source="browser")
        try:
            self._record_pick(item)
        except Exception:
            log("usage error:\n" + traceback.format_exc())

    # --- hand-off to ZBrush ----------------------------------------------------------------------
    def _actions(self, item, legacy=None):
        """legacy: the ZBrush 2022-2025 installation in front, whose own files must be used."""
        acts = item.data["steps"] if item.kind == "steps" else [item.data]
        out = []
        for a in acts:
            a = dict(a)
            if "capture" in a:
                # ZBrush 2022-2025 get a name their plugin can read; a CaptureError stops the whole pick
                a = {"filepress": capture.BUTTON, "file": capture.target(a["capture"], legacy is not None)}
            elif any(k in a for k in C.FILE_EXTS):
                # the file is looked for now, not when the menus loaded; a FileItemError stops the whole pick
                button, path = fileitem.resolve(a, legacy is not None)
                a = {"filepress": button, "file": path}
            got = C.asset_of(a)
            if got and assets is not None:
                p = assets.find_or_rescan(got[0], got[1], legacy["path"] if legacy else None)
                a["file"] = str(p).replace("\\", "/") if p else None
                if p:
                    # ZBrush names the button of a loaded item after its file
                    a["button"] = os.path.splitext(os.path.basename(str(p)))[0]
            out.append(a)
        return out

    def _write_request(self, item, legacy=None) -> int:
        self._seq += 1
        actions = self._actions(item, legacy)
        req = {"id": self._seq, "time": time.time(), "label": item.label, "actions": actions}
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = REQUEST_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(req, f)
        os.replace(tmp, REQUEST_FILE)              # atomic: the bridge never sees half a request
        if legacy is not None or self._legacy_installed():      # only ZBrush 2022-2025 read request.txt
            try:
                for p in zscript_bridge.write_request(self._seq, item.label, actions):
                    log(f"pick #{self._seq}: request.txt: {p}")
            except OSError as e:
                log(f"pick #{self._seq}: could not write request.txt: {e!r}")
        return self._seq

    def _legacy_installed(self) -> bool:
        """Whether a ZBrush 2022-2025 (no Python API) is installed; the scan is kept for LEGACY_SCAN_S."""
        at, found = self._legacy_scan
        if at == 0.0 or time.monotonic() - at >= LEGACY_SCAN_S:
            try:
                found = any(not e["python"] for e in installs.find_installs())
            except Exception:
                found = True                       # cannot tell: write it, as before
            self._legacy_scan = (time.monotonic(), found)
        return found

    def _listener(self, pid):
        """The verified listener window of the ZBrush with process id pid (the one the pick is for), else None.
        listener.json holds whichever ZBrush wrote it last, so with two running it can be the wrong one."""
        try:
            with open(LISTENER_FILE, encoding="utf-8") as f:
                info = json.load(f)
            hwnd = W.w.HWND(int(info["hwnd"]))
            owner = int(info["pid"])
            if not (info.get("verified") and W.IsWindow(hwnd)):
                return None
        except (OSError, ValueError, KeyError, TypeError):
            return None
        if owner == pid and self._exe_of(owner) == self.target_exe:
            return hwnd
        if pid not in self._listener_skipped and len(self._listener_skipped) < 20:
            self._listener_skipped.add(pid)
            if owner != pid:
                log(f"listener.json is from pid {owner}, not the ZBrush this pick is for (pid {pid}); "
                    f"using the bridge key")
            else:
                log(f"listener.json's process (pid {owner}) is {self._exe_of(owner) or 'unreadable'}, "
                    f"not {self.target_exe}; using the bridge key")
        return None

    @staticmethod
    def _front_pid():
        fg = W.GetForegroundWindow()
        return W.window_pid(fg) if fg else 0

    def _browser_zb_pid(self):
        """Process id of the ZBrush a browser pick is for: the one the browser was opened from. When that is unknown
        (a browser opened from Studio has none on record) or gone, the only ZBrush running. 0 when it cannot tell."""
        zb = self._popout_zb[0] if self._popout_zb else 0
        if zb and W.IsWindow(W.w.HWND(zb)):
            return W.window_pid(zb)
        pids = W.pids_named(self.target_exe)
        return pids[0] if len(pids) == 1 else 0

    def _drop_request(self, seq):
        """A pick nobody will carry out must not wait for the Apply button or the bridge key press that comes
        later: that would apply it long after the user asked."""
        for p in (REQUEST_FILE, zscript_bridge.REQUEST_TXT):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
            except OSError as e:
                log(f"pick #{seq}: could not remove {os.path.basename(p)}: {e!r}")
        log(f"pick #{seq} not delivered; request removed")

    def send(self, item, install=None, source="ring", pid=None):
        """install: the ZBrush installation to hand off to, when it is not the one in front right now (a pick
        from the browser arrives after the focus has moved). source: "ring", "browser" or "command", for
        activity.json. pid: the ZBrush a command's pick is for."""
        ins = install if install is not None else self.target_install()
        legacy = ins if ins is not None and not ins["python"] else None
        try:
            seq = self._write_request(item, legacy)
        except (capture.CaptureError, fileitem.FileItemError) as e:
            log(f"pick #{self._seq} '{item.label}': {e.reason}; nothing sent")
            self.activity.note_pick(self._seq, item, "none", False, source, self._activity_menu, e.reason)
            if isinstance(e, fileitem.FileItemError):
                self._toast(_FILE_MESSAGES[e.kind])
            else:
                self._toast(MSG_CAPTURE_NAME if e.kind == "name" else MSG_CAPTURE_FOLDER)
            return
        except OSError as e:
            reason = "could not write the request file"
            log(f"pick #{self._seq} '{item.label}': {reason}: {e!r}; nothing sent")
            self.activity.note_pick(self._seq, item, "none", False, source, self._activity_menu, reason)
            return
        mode = self.cfg.bridge_mode
        if legacy is not None:
            # A listener can only be a ZBrush 2026+ (perhaps running as well), never the one in front.
            log(f"pick #{seq} '{item.label}': {legacy['name']} in front, so the ZScript bridge (bridge key)")
            before = _read_bytes(ZSCRIPT_LOG)          # before the key: the plugin may answer at once
            sent, reason = self.press_bridge_key(seq)
            self.activity.note_pick(seq, item, "zscript", sent, source, self._activity_menu, reason)
            if sent:
                self._watch_zscript_result(seq, before)
                self._watch_apply(seq, legacy)
            else:
                self._drop_request(seq)
            W.nudge_mouse()
            return
        zb_pid = pid or (self._browser_zb_pid() if source == "browser" else self._front_pid())
        listener = self._listener(zb_pid) if mode in ("auto", "message") else None
        if listener is not None:
            ok = W.PostMessageW(listener, WM_APP_PICK, seq, 0)
            log(f"pick #{seq} '{item.label}' -> listener {int(listener.value)} (posted={bool(ok)})")
            if ok:
                self.activity.note_pick(seq, item, "listener", True, source, self._activity_menu)
                now = time.time()
                self._ack = [seq, now + ACK_WAIT_S, now + ACK_HOLD_MAX_S, False]
                self._pick_time, self._result = now, None
                W.SetTimer(self.ctrl, TIMER_ACK, 100, None)
                W.nudge_mouse()
                return
        if mode == "message":
            log(f"pick #{seq}: no live listener in ZBrush and bridge mode is 'message'; nothing sent")
            self.activity.note_pick(seq, item, "none", False, source, self._activity_menu,
                                    "no live listener in ZBrush and bridge mode is 'message'")
            self._drop_request(seq)
            self._toast(MSG_NO_CONNECTION)
            return
        sent, reason = self.press_bridge_key(seq)
        self.activity.note_pick(seq, item, "key", sent, source, self._activity_menu, reason)
        if not sent:
            self._drop_request(seq)
        W.nudge_mouse()

    def _check_ack(self):
        if self._ack is None:
            if self._result is not None:
                self._result_tick()
            else:
                W.KillTimer(self.ctrl, TIMER_ACK)
            return
        seq, deadline, give_up, logged = self._ack
        pending = os.path.exists(REQUEST_FILE)
        if not pending:
            self._ack = None
            self.activity.note_ack(seq, "picked_up")
            self._result = [seq, self._pick_time, RESULT_TRIES]    # the plugin logs the outcome a moment after it
            self._result_tick()                                     # takes the request, so look now and keep looking
            return
        now = time.time()
        if now < deadline:
            return
        if W.primary_down() and now < give_up:
            # The listener holds a pick back while the left button is down, and a bridge key pressed now would apply
            # it mid-stroke: wait until the button is up, then give the listener ACK_WAIT_S more.
            self._ack[1] = now + ACK_WAIT_S
            if not logged:
                self._ack[3] = True
                log(f"pick #{seq}: left mouse button is down; waiting for the stroke to end")
            return
        self._ack = None
        W.KillTimer(self.ctrl, TIMER_ACK)
        self.activity.note_ack(seq, "timeout")
        if self.cfg.bridge_mode == "message":
            log(f"pick #{seq}: listener did not pick it up in 0.5 s")
            self._toast(MSG_NO_ANSWER)
        else:
            log(f"pick #{seq}: listener did not pick it up in 0.5 s; falling back to the bridge key")
            sent, reason = self.press_bridge_key(seq)
            self.activity.note_route(seq, "key", sent, reason)
            if not sent:
                self._drop_request(seq)

    def _result_tick(self):
        """Reads the plugin's outcome for the picked-up request from bridge.log; a toast only for a problem."""
        seq, since, left = self._result
        problems = _plugin_result(seq, since)
        if problems is None and left > 1:
            self._result[2] = left - 1
            return
        self._result = None
        W.KillTimer(self.ctrl, TIMER_ACK)
        if problems:
            log(f"pick #{seq}: ZBrush reported: {'; '.join(problems)}")
            self._toast(problems[0])

    def _watch_zscript_result(self, seq, before):
        """Copies the ZScript plugin's line about pick seq into this log once it appears, since the plugin keeps
        only the last pick. An older pick still waiting is given up: the plugin has carried out the picks in order."""
        if self._zs_result is not None:
            self._zs_result_tick(final=True)
        self._zs_result = [seq, before, time.time() + ZS_RESULT_S]
        W.SetTimer(self.ctrl, TIMER_ZS_RESULT, 100, None)

    def _zs_result_tick(self, final=False):
        seq, before, give_up = self._zs_result
        got = _zscript_result(seq, before)
        if got is None and not final and time.time() < give_up:
            return
        self._zs_result = None
        W.KillTimer(self.ctrl, TIMER_ZS_RESULT)
        if got is not None:
            log(f"pick #{seq} result: {got}")
            problems = _problems(got.split("': ", 1)[-1])       # the line is "'label': result"
            if problems:
                self._toast(problems[0])
        else:
            log(f"pick #{seq}: the ZScript plugin wrote no result" + ("" if final else f" in {ZS_RESULT_S} s") +
                " (a macro ends its script before it can; otherwise the bridge key did not reach Apply)")

    def _watch_apply(self, seq, legacy, now=None):
        """The bridge key was pressed for pick seq in a ZBrush 2022-2025 (legacy: its installation). Apply deletes
        request.txt when it reads it, so a file still there means the key did not reach Apply: after APPLY_KEY_WAIT_S
        the fixed script that presses Apply is run through ZBrush.exe, and after APPLY_SCRIPT_WAIT_S more the pick is
        dropped, so that a key bound to Apply later cannot apply it long after the user asked. A newer pick takes
        the watch over (there is one request file)."""
        now = time.time() if now is None else now
        fg = W.GetForegroundWindow()             # ZBrush's own window: press_bridge_key needed it in front
        self._apply_watch = {"seq": seq, "at": now, "deadline": now + APPLY_KEY_WAIT_S, "wait": APPLY_KEY_WAIT_S,
                             "fired": False, "ran": False, "exe": os.path.join(legacy["path"], "ZBrush.exe"),
                             "hwnd": fg if fg and self.target_in_front() else None}
        W.SetTimer(self.ctrl, TIMER_APPLY, 100, None)

    def _end_apply(self):
        self._apply_watch = None
        W.KillTimer(self.ctrl, TIMER_APPLY)

    def _apply_tick(self, now=None):
        w = self._apply_watch
        if w is None:
            W.KillTimer(self.ctrl, TIMER_APPLY)
            return
        now = time.time() if now is None else now
        seq = w["seq"]
        try:
            there = zscript_bridge.pending_request()
        except OSError:                          # being replaced just now: look again, but not for ever
            if now - w["at"] > ZS_RESULT_S:
                self._end_apply()
            return
        if there != seq:                         # taken by Apply, or replaced by a newer pick, which has its own watch
            self._end_apply()
            if there is None and w["ran"]:
                log(f"pick #{seq}: ZBrush took it after the fallback script")
                self.activity.note_route(seq, "zscript-fallback", True)
            return
        hwnd = w["hwnd"]
        if hwnd is not None and not W.IsWindow(hwnd):
            if self.target_exe not in W.running_exe_names():      # ZBrush was closed: nobody will take the pick
                self._end_apply()
                log(f"pick #{seq}: {self.target_exe} has closed; request dropped")
                self._give_up_apply(seq, "ZBrush closed before it took the pick", toast=False)
                return
            hwnd = w["hwnd"] = None                               # only the window we remembered went (a menu, a box)
        if hwnd is not None and now < w["at"] + APPLY_BUSY_MAX_S and W.IsHungAppWindow(hwnd):
            # ZBrush is busy (a big Dynamesh, a project loading) and the key waits in its queue: dropping the pick
            # now would lose it, where waiting lets it land late. No second process for a ZBrush that is not listening.
            w["deadline"] = now + w["wait"]
            if self._zs_result is not None and self._zs_result[0] == seq:
                self._zs_result[2] = now + ZS_RESULT_S            # its line comes late too, which is not "no result"
            return
        if W.primary_down() and now < w["at"] + ACK_HOLD_MAX_S:
            w["deadline"] = now + w["wait"]      # a stroke holds the key back, as it holds a listener pick back
            return
        if now < w["deadline"]:
            return
        if not w["fired"]:
            w["fired"] = True
            w["deadline"], w["wait"] = now + APPLY_SCRIPT_WAIT_S, APPLY_SCRIPT_WAIT_S
            w["ran"] = self._run_apply_script(seq, w["exe"])
            return
        self._end_apply()
        log(f"pick #{seq}: ZBrush took it neither by the bridge key nor by the fallback script; giving it up")
        self._give_up_apply(seq, "ZBrush did not take the pick", toast=True)

    def _give_up_apply(self, seq, reason, toast):
        self._drop_request(seq)
        if self._zs_result is not None and self._zs_result[0] == seq:
            self._zs_result = None               # its "no result" line would only repeat this one
            W.KillTimer(self.ctrl, TIMER_ZS_RESULT)
        self.activity.note_route(seq, "zscript", False, reason)
        if toast:
            self._toast(MSG_BRIDGE_NO_RESPONSE)

    def _run_apply_script(self, seq, exe) -> bool:
        """Starts ZBrush.exe with the script that presses Apply, which the ZBrush already open takes over and the
        new process ends. Not waited for: a box open in ZBrush can hold the script back. True when it was started."""
        log(f"pick #{seq}: the bridge key ({self.cfg.bridge_key.text}) did not reach Apply (is it bound to "
            f"Zplugin > ZOrbit > Apply?); using the fallback, a script that presses Apply")
        try:
            if self.target_exe not in W.running_exe_names():
                log(f"pick #{seq}: {self.target_exe} is not running; fallback script not started")
                return False
            script = zscript_bridge.ensure_apply_script()
            subprocess.Popen([exe, script], cwd=os.path.dirname(exe), env=paths.clean_env(),
                             creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                             close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except (OSError, ValueError, subprocess.SubprocessError) as e:
            log(f"pick #{seq}: could not run the fallback script: {e!r}")
            return False
        return True

    def press_bridge_key(self, seq):
        key = self.cfg.bridge_key
        if not self.target_in_front():
            log(f"pick #{seq}: ZBrush is not in front; bridge key not sent (it would land in another app)")
            self._toast(MSG_NOT_FRONT)
            return False, "ZBrush is not in front"
        held = [vk for vk in (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5) if W.key_down(vk)]
        events = [(vk, True) for vk in held]                     # release what the user still holds
        mods = [vk for vk, on in ((W.VK_MENU, key.alt),) if on]  # bridge keys allow Alt only
        events += [(vk, False) for vk in mods] + [(key.vk, False), (key.vk, True)]
        events += [(vk, True) for vk in reversed(mods)]
        n = W.send_keys(events)
        still = [vk for vk in held if W.key_down(vk)]
        if still:
            W.send_keys([(vk, False) for vk in still])
        log(f"pick #{seq} -> bridge key {key.text} (sent {n} events; released/restored {held}/{still})")
        return True, None

    # --- lifetime --------------------------------------------------------------------------------
    def _check_elevated(self):
        """A ZBrush running as administrator hides its process and its keys from this (normal) app, so hotkeys
        cannot work there. Looks at every ZBrush process, logs each once, and tells activity.json."""
        pids = W.pids_named(self.target_exe)
        if self._token_check is None:
            # Our own token must read as "not elevated": if even that fails, the token call cannot be trusted and
            # only an unreadable process image counts, so a normal ZBrush is never reported by mistake.
            self._token_check = W.process_elevated(os.getpid()) is False
        for pid in pids:
            if pid not in self._elevated:
                # unreadable image or token: a normal process of this user answers both, an elevated one does not
                elevated = W.process_elevated(pid) if self._token_check else False
                self._elevated[pid] = not W.process_image(pid) or elevated is not False
                if self._elevated[pid]:
                    log(f"{self.target_exe} (pid {pid}) could not be read, so it is probably running as "
                        f"administrator; hotkeys ignored in it (start ZBrush without 'Run as administrator')")
        for pid in [p for p in self._elevated if p not in pids]:
            del self._elevated[pid]
        self.activity.note_elevated(any(self._elevated.values()))

    def _recent_tick(self):
        """Every RECENT_PREFETCH_S while ZBrush is in front, has recent.py's worker read the recent slots' lists
        again, so a fan is never older than that. Returns at once; nothing happens without a recent slot."""
        now = time.monotonic()
        if self.expander is None or now - self._recent_at < RECENT_PREFETCH_S or self.target_install() is None:
            return
        self._recent_at = now
        self.expander.prefetch_recent()

    def _watch_target(self):
        _trim_log()                     # every 3 s, not only at start: a long session must not grow the log for ever
        self._check_elevated()
        if not self.exit_with_target:
            return
        if self.target_exe in W.running_exe_names():
            self._target_misses = 0
            return
        self._target_misses += 1
        if self._target_misses >= 2:
            log(f"{self.target_exe} is no longer running; exiting")
            W.PostQuitMessage(0)

    def run(self, mutex=None, hold=None) -> int:
        """mutex: the handle claim_instance() returned. Without one the app claims it here. hold: the ExitStack that
        still holds the takeover lock; it is released once the tray window exists."""
        if mutex is None:
            with contextlib.ExitStack() as hold:
                mutex = claim_instance(hold=hold)
                return 0 if mutex is None else self._serve(mutex, hold)
        return self._serve(mutex, hold)

    def _serve(self, mutex, hold) -> int:
        os.makedirs(DATA_DIR, exist_ok=True)
        created = W.process_created(os.getpid())
        started = f"{time.time() - created:.2f} s after its process was created" if created else "?"
        W.make_dpi_aware()
        log(f"ZOrbit starting (pid {os.getpid()}, python {sys.version.split()[0]}, "
            f"thumbnails={'on' if assets else 'off'}; {started}; started by {W.launch_chain()})")
        if not self._pinned:
            log(f"profile: {self.profile} ({len(profiles.names())} profiles)")
        self.load_config(force=True)
        if self.cfg is None:
            return 1
        self._create_ctrl()
        self._schedule_prewarm()
        self._warm_soon("start")                    # the load above came before the window its timer needs
        self.start_hook()
        W.SetTimer(self.ctrl, TIMER_WATCH, 3000, None)
        W.SetTimer(self.ctrl, TIMER_REHOOK, 120000, None)
        W.SetTimer(self.ctrl, TIMER_CONFIG, 500, None)
        self._create_tray()
        if hold is not None:
            hold.close()            # the takeover is over: a new app that waited now finds this one's tray window
        if self._config_error:                      # the file was already broken when the app started
            self._menus_problem(announce=True)
        msg = W.w.MSG()
        try:
            while W.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                W.TranslateMessage(ctypes.byref(msg))
                W.DispatchMessageW(ctypes.byref(msg))
        finally:
            self._destroy_tray()
            self.stop_hook()                        # ends the hook thread, which removes the hook
        popout = W.find_message_window(POPOUT_CLASS)
        if popout:
            W.send_copydata(popout, COPYDATA_QUIT, b"{}")
        W.CloseHandle(mutex)
        log("ZOrbit stopped")
        return 0


def takeover_plan(running, mine) -> tuple:
    """What a starting app does when another one holds the mutex. running: W.running_app() (pid, tid, version) or
    None; mine: this app's version. ('take', reason) when the running app is older, else ('exit', reason)."""
    if not running:
        return "exit", "version unknown"
    theirs, ours = paths.version_key(running[2]), paths.version_key(mine)
    if theirs is None or ours is None:
        return "exit", "version unknown"
    if theirs < ours:
        return "take", f"older version {running[2]}"
    if theirs == ours:
        return "exit", "same version"
    return "exit", f"newer version {running[2]}"


def _wait_browser_gone(log) -> None:
    """The old app tells a hidden browser to quit as it ends. Waits briefly for that; a browser window that is open
    stays (it is a separate process the user can see) and is left alone."""
    deadline = time.monotonic() + TAKEOVER_BROWSER_S
    while W.mutex_exists(POPOUT_MUTEX):
        if time.monotonic() >= deadline:
            log("the old browser window is still open; it stays until it is closed")
            return
        time.sleep(0.1)


def claim_instance(log=log, hold=None):
    """Claims the single-instance mutex and returns its handle, or None when another ZOrbit keeps it (the caller
    then exits). An older app that holds it is asked to quit first (takeover_plan). During a takeover the lock
    Local\\ZOrbitTakeover is entered into hold (an ExitStack the caller owns), so a second new app started at the
    same moment waits and then finds a current version; the caller closes hold once its tray window exists. Without
    hold the lock is released before this returns."""
    os.makedirs(DATA_DIR, exist_ok=True)
    _trim_log()
    mutex, already = W.create_mutex(MUTEX_NAME)
    if not already:
        return mutex
    created = W.process_created(os.getpid())
    started = f"{time.time() - created:.2f} s after its process was created" if created else "?"
    own = hold is None
    stack = contextlib.ExitStack() if own else hold
    try:
        if not stack.enter_context(fsutil.named_lock(TAKEOVER_MUTEX, TAKEOVER_LOCK_MS)):
            log("another ZOrbit is still taking over; going ahead without its lock")
        running = W.running_app()
        action, why = takeover_plan(running, paths.VERSION)
        if action == "take":
            pid, tid, version = running
            log(f"taking over from ZOrbit {version} (pid {pid})")
            if W.ask_to_quit(pid, tid, TAKEOVER_QUIT_S):
                log(f"ZOrbit {version} has quit")
                _wait_browser_gone(log)
                return mutex
            try:
                denied = W.process_elevated(pid) is not False       # the token of an elevated app cannot be read
            except Exception:
                denied = False
            why = "access denied" if denied else "it did not quit in time"
        log(f"another instance is already running; exiting ({why}; {started}; started by {W.launch_chain()})")
        W.CloseHandle(mutex)
        return None
    finally:
        if own:
            stack.close()


def _show_fatal(text) -> None:
    """The app has no window and no message loop yet, so a start that cannot go on says why in a message box."""
    try:
        W.MessageBoxW(None, text, "ZOrbit", W.MB_OK | W.MB_ICONERROR | W.MB_SETFOREGROUND)
    except Exception as e:
        log(f"could not show the message: {e!r}")


def check(cfg_path) -> int:
    store = tags.TagStore(tags_path()).load()
    cfg = C.load(cfg_path, store)
    if profiles.enabled() and cfg_path == profiles.config_file():
        print(f"profile: {profiles.active()}")
    print(f"{cfg_path}: {len(cfg.menus)} menus, bridge mode={cfg.bridge_mode} "
          f"key={cfg.bridge_key.text}, "
          f"browser hotkey={cfg.browser_key.text if cfg.browser_key else None}, "
          f"next profile hotkey={cfg.profile_key.text if cfg.profile_key else None}")
    for m in cfg.menus.values():
        print(f"  [{m.id}] '{m.title}' hotkey={m.hotkey.text if m.hotkey else '-'} swallow={m.swallow}")
        for it in m.items:
            extra = ""
            if it.kind in C.ASSET_KINDS and assets is not None:
                p = assets.find(it.kind, it.data[it.kind])
                ext = "/".join(assets.exts(it.kind))
                extra = f"  ({p})" if p else f"  (no {ext} file found: must already be loaded in ZBrush)"
            elif it.kind == "tag":
                key = it.data["tag"]
                n = len(store.items_with(key))
                extra = (f"  ({n} item{'' if n == 1 else 's'} tagged)" if store.has(key)
                         else f"  (tag {key!r} does not exist)")
            elif it.kind == "browser":
                extra = f"  (opens on {it.data.get('kind', 'brush')})"
            elif it.kind == "recent":
                where, why = recent.list_file()
                extra = f"  (reads {where})" if where else f"  ({why})"
            elif it.kind == "capture":
                extra = f"  (saves into {it.data['capture'].strip() or capture.default_folder()})"
            elif it.kind in C.FILE_EXTS:
                extra = f"  ({fileitem.describe(it.data)})"
            print(f"      {it.kind:7s} {it.label}{extra}")
    said = any(e.startswith("tags.json could not be read") for e in cfg.errors)     # config.load says it once
    problems = ([store.error] if store.error and not said else []) + cfg.errors
    for e in problems:
        print(f"  PROBLEM: {e}")
    return 1 if problems else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=None, help="pinned menus file (profiles off; tags and usage come from the active profile)")
    ap.add_argument("--exit-with-zbrush", action="store_true", help="quit when ZBrush.exe has exited")
    ap.add_argument("--target-exe", default="ZBrush.exe", help=argparse.SUPPRESS)
    ap.add_argument("--no-tray", action="store_true", help="do not show the notification-area icon")
    ap.add_argument("--check", action="store_true", help="validate the config and exit")
    a = ap.parse_args(argv)
    try:
        with contextlib.ExitStack() as hold:
            mutex = None
            if not a.check:
                mutex = claim_instance(hold=hold)       # before ensure(): a failed takeover leaves the files alone
                if mutex is None:
                    return 0
            if a.config is None:
                try:
                    profiles.ensure()
                except OSError as e:              # an unwritable %APPDATA%: say so plainly, not with a traceback
                    log(f"fatal: cannot create the first profile in {profiles.root()}: {e}")
                    return 1
                msg = profiles.too_new()
                if msg:
                    if a.check:
                        print(msg)
                        return 1
                    log(f"fatal: {msg}")
                    W.CloseHandle(mutex)
                    hold.close()
                    _show_fatal(msg)
                    return 1
                if not a.check and profiles.enabled():
                    profiles.tidy_leftovers()
                    n = profiles.absorb_stray_usage()
                    if n:
                        log(f"usage: added {n} brushes from an older version")
            if a.check:
                return check(a.config or profiles.config_file())
            return App(a.config, a.target_exe, a.exit_with_zbrush, a.no_tray).run(mutex, hold)
    except Exception:
        log("fatal:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
