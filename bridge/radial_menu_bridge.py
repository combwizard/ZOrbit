"""Radial Menu bridge: the ZBrush 2026+ side of Radial Menu for ZBrush.

Loaded by ZBrush at startup from a folder listed in the user environment variable ZBRUSH_PLUGIN_PATH (the
installer adds this folder), or once by hand: ZScript > Python Scripting > Load.

What it does:
  * Palette Zplugin > Radial Menu with:
      Apply      carries out the pending pick (%LOCALAPPDATA%\\RadialMenu\\request.json). The app triggers it
                 either through the listener below or by pressing the bridge key; for the key route bind it
                 natively: Ctrl+Alt+click Apply, press F9, then Preferences > Hotkeys > Store. (No Python
                 hotkey on purpose: native bindings proved more reliable.)
      Start App  starts the Radial Menu app if it is not running (it also starts automatically here).
      Status     shows listener, app and last-request state.
  * A hidden message-only window on ZBrush's main thread. The app posts WM_APP+1 to it after a pick, so no
    keystroke is needed. Its handle is published in listener.json only after a timer message has proved
    that ZBrush dispatches window messages to Python; if that never happens the app uses the bridge key.
"""
import ctypes
import ctypes.wintypes as w
import json
import os
import subprocess
import sys
import time
import traceback
import types

import zbrush.commands as zbc

# --- locations -----------------------------------------------------------------------------------
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "RadialMenu")
LAUNCH_FILE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "RadialMenu", "launch.json")
REQUEST_FILE = os.path.join(DATA_DIR, "request.json")
REQUEST_TXT = os.path.join(DATA_DIR, "request.txt")       # the same pick for the ZScript bridge (ZBrush 2022-2025)
LISTENER_FILE = os.path.join(DATA_DIR, "listener.json")
LOG_FILE = os.path.join(DATA_DIR, "bridge.log")
BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
PALETTE = "Zplugin:Radial Menu"

WM_APP_PICK = 0x8000 + 1
WM_TIMER = 0x113
TIMER_VERIFY, TIMER_RETRY = 1, 2
VK_LBUTTON = 0x01


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(f"Radial Menu: {msg}")
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 500_000:
            os.replace(LOG_FILE, LOG_FILE + ".old")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# State that must survive a reload of this file (ZBrush's Python VM is shared and persistent).
S = sys.modules.setdefault("_radial_menu_bridge_state", types.ModuleType("_radial_menu_bridge_state"))
if not hasattr(S, "keepalive"):
    S.keepalive, S.hwnd, S.seq, S.verified, S.last = [], None, 0, False, "none yet"

# --- Win32 (own WinDLL instances so other plugins' argtypes are untouched) -----------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE),
                ("hIcon", w.HICON), ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH),
                ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON)]


def _sig(dll, name, res, *args):
    f = getattr(dll, name)
    f.restype, f.argtypes = res, list(args)
    return f


DefWindowProcW = _sig(user32, "DefWindowProcW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
RegisterClassExW = _sig(user32, "RegisterClassExW", w.ATOM, ctypes.POINTER(WNDCLASSEXW))
CreateWindowExW = _sig(user32, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                       w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)
DestroyWindow = _sig(user32, "DestroyWindow", w.BOOL, w.HWND)
IsWindow = _sig(user32, "IsWindow", w.BOOL, w.HWND)
SetTimer = _sig(user32, "SetTimer", ctypes.c_size_t, w.HWND, ctypes.c_size_t, w.UINT, ctypes.c_void_p)
KillTimer = _sig(user32, "KillTimer", w.BOOL, w.HWND, ctypes.c_size_t)
GetAsyncKeyState = _sig(user32, "GetAsyncKeyState", ctypes.c_short, ctypes.c_int)
GetModuleHandleW = _sig(kernel32, "GetModuleHandleW", w.HMODULE, w.LPCWSTR)
GetCurrentThreadId = _sig(kernel32, "GetCurrentThreadId", w.DWORD)
OpenMutexW = _sig(kernel32, "OpenMutexW", w.HANDLE, w.DWORD, w.BOOL, w.LPCWSTR)
CloseHandle = _sig(kernel32, "CloseHandle", w.BOOL, w.HANDLE)
HWND_MESSAGE = w.HWND(-3)


# --- carrying out a pick -------------------------------------------------------------------------
def _do_brush(a: dict) -> str:
    name = a["brush"]
    path = f"Brush:{name}"
    if zbc.exists(path):
        zbc.press(path)
        return f"brush {name}: selected"
    f = a.get("file")
    if f and os.path.isfile(f):
        zbc.set_next_filename(f.replace("\\", "/"))
        zbc.press("Brush:Load Brush")
        if zbc.exists(path):
            zbc.press(path)
        return f"brush {name}: loaded from {f}"
    return f"brush {name}: NOT loaded in ZBrush and no .zbp file known"


def _do_action(a: dict) -> str:
    if "brush" in a:
        # Still switched: the note only explains a brush that seems not to take outside Edit mode.
        return _do_brush(a) + ("" if zbc.get("Transform:Edit") else " (Edit mode is off)")
    for kind in ("press", "set", "toggle"):
        if kind in a:
            path = a[kind]
            if not zbc.exists(path):
                return f"{kind} {path}: no such interface item"
            if kind == "press":
                zbc.press(path)
            elif kind == "set":
                zbc.set(path, a["value"])
            else:
                zbc.toggle(path)
            return f"{kind} {path}" + (f" = {a['value']}" if kind == "set" else "") + ": ok"
    return f"unknown action {a!r}"


def apply_request(sender: str = "") -> None:
    """Button callback and listener entry point: carry out request.json, then delete it."""
    try:
        with open(REQUEST_FILE, encoding="utf-8") as f:
            req = json.load(f)
        os.remove(REQUEST_FILE)
        try:
            os.remove(REQUEST_TXT)
        except OSError:
            pass
    except FileNotFoundError:
        log(f"apply ({sender or 'button'}): no pending request")
        return
    except Exception as e:
        log(f"apply ({sender or 'button'}): unreadable request: {e!r}")
        try:
            os.remove(REQUEST_FILE)
        except OSError:
            pass
        return
    results = []
    for a in req.get("actions", []):
        try:
            results.append(_do_action(a))
        except Exception as e:
            results.append(f"{a!r}: FAILED {type(e).__name__}: {e}")
    S.last = f"#{req.get('id')} '{req.get('label')}' via {sender or 'button'}: " + "; ".join(results)
    log(S.last)


# --- listener window -----------------------------------------------------------------------------
def _publish_listener():
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = LISTENER_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"hwnd": int(S.hwnd), "pid": os.getpid(), "thread": GetCurrentThreadId(),
                   "verified": time.time()}, f)
    os.replace(tmp, LISTENER_FILE)


def _wndproc(hwnd, msg, wparam, lparam):
    try:
        if msg == WM_APP_PICK:
            if GetAsyncKeyState(VK_LBUTTON) & 0x8000:      # never switch tools in the middle of a stroke
                SetTimer(hwnd, TIMER_RETRY, 40, None)
            else:
                apply_request("listener")
            return 0
        if msg == WM_TIMER and wparam == TIMER_RETRY:
            if not GetAsyncKeyState(VK_LBUTTON) & 0x8000:
                KillTimer(hwnd, TIMER_RETRY)
                apply_request("listener, after stroke")
            return 0
        if msg == WM_TIMER and wparam == TIMER_VERIFY:
            KillTimer(hwnd, TIMER_VERIFY)
            S.verified = True
            _publish_listener()
            log(f"listener verified: ZBrush dispatches window messages to Python (window {int(hwnd)}, "
                f"thread {GetCurrentThreadId()})")
            return 0
    except Exception:
        log("listener error:\n" + traceback.format_exc())
        return 0
    return DefWindowProcW(hwnd, msg, wparam, lparam)


def start_listener() -> None:
    if S.hwnd and IsWindow(S.hwnd):
        DestroyWindow(S.hwnd)                             # from a previous load; same thread
    S.hwnd, S.verified = None, False
    try:
        os.remove(LISTENER_FILE)                          # republished once verified
    except OSError:
        pass
    S.seq += 1
    proc = WNDPROC(_wndproc)
    S.keepalive.append(proc)                              # never freed: Windows may still hold it
    hinst = GetModuleHandleW(None)
    cls = f"RadialMenuBridge{S.seq}"
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = proc
    wc.hInstance = hinst
    wc.lpszClassName = cls
    if not RegisterClassExW(ctypes.byref(wc)):
        log(f"listener: RegisterClassExW failed ({ctypes.get_last_error()}); bridge key only")
        return
    hwnd = CreateWindowExW(0, cls, "Radial Menu bridge", 0, 0, 0, 0, 0, HWND_MESSAGE, None, hinst, None)
    if not hwnd:
        log(f"listener: CreateWindowExW failed ({ctypes.get_last_error()}); bridge key only")
        return
    S.hwnd = hwnd
    SetTimer(hwnd, TIMER_VERIFY, 200, None)


# --- the app -------------------------------------------------------------------------------------
def _launch(kind: str):
    """Command line for 'app' or 'studio' from %APPDATA%/RadialMenu/launch.json, which the installer writes
    and the app refreshes every time it starts."""
    try:
        with open(LAUNCH_FILE, encoding="utf-8") as f:
            cmd = json.load(f).get(kind)
        if isinstance(cmd, list) and cmd and os.path.isfile(cmd[0]):
            return cmd
    except Exception:
        pass
    return None


def _spawn(cmd, errlog_name=None):
    flags = 0x00000008 | 0x00000200                       # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    # ZBrush's process environment is set up for ZBrush's embedded Python; a different Python that inherits
    # PYTHONHOME/PYTHONPATH can die before running a line, so drop every PYTHON* variable.
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
    os.makedirs(DATA_DIR, exist_ok=True)
    out = open(os.path.join(DATA_DIR, errlog_name), "a", encoding="utf-8") if errlog_name else subprocess.DEVNULL
    try:
        return subprocess.Popen(cmd, cwd=os.path.dirname(cmd[0]), env=env, creationflags=flags, close_fds=True,
                                stdin=subprocess.DEVNULL, stdout=out, stderr=out)
    finally:
        if errlog_name:
            out.close()


def _not_installed():
    zbc.message_ok("Radial Menu: the app was not found.\n\nRun the Radial Menu installer again, or start "
                   "\"Radial Menu Studio\" from the Start menu once.", "Radial Menu")


def app_running() -> bool:
    h = OpenMutexW(0x00100000, False, "Local\\RadialMenuForZBrush")   # SYNCHRONIZE
    if h:
        CloseHandle(h)
        return True
    return False


def start_app(sender: str = "") -> None:
    if app_running():
        if sender:
            log("app already running")
        return
    cmd = _launch("app")
    if not cmd:
        log("app not found: launch.json missing or stale")
        if sender:
            _not_installed()
        return
    p = _spawn(cmd, "app_stderr.log")
    log(f"started app pid {p.pid}: {' '.join(cmd)}")


def open_studio(sender: str = "") -> None:
    """Opens Radial Menu Studio, the companion app (menu editor, brush library, settings)."""
    cmd = _launch("studio")
    if not cmd:
        _not_installed()
        return
    _spawn(cmd)
    log("opened Studio")


def status(sender: str = "") -> None:
    pending = "yes" if os.path.exists(REQUEST_FILE) else "no"
    zbc.message_ok(
        f"Listener: {'verified, window ' + str(int(S.hwnd)) if S.verified else 'NOT verified (bridge key only)'}\n"
        f"App running: {'yes' if app_running() else 'no'}\n"
        f"Pending request: {pending}\n"
        f"Last pick: {S.last}\n"
        f"Logs: {DATA_DIR}", "Radial Menu")


def install() -> None:
    if not zbc.exists(PALETTE):
        zbc.add_subpalette(PALETTE, 0)
    for name, info, fn in (("Studio", "Opens Radial Menu Studio: edit menus, browse brushes, settings.", open_studio),
                           ("Apply", "Carries out the Radial Menu pick. Bind F9 to it natively.", apply_request),
                           ("Start App", "Starts the Radial Menu app if it is not running.", start_app),
                           ("Status", "Shows the Radial Menu bridge state.", status)):
        path = f"{PALETTE}:{name}"
        if zbc.exists(path):
            zbc.delete_interface_item(path)
        zbc.add_button(path, info, fn)
    for p in (REQUEST_FILE, REQUEST_TXT):          # a pick left by a ZBrush that quit before applying it
        try:
            os.remove(p)
            log(f"removed a pick left over from earlier: {os.path.basename(p)}")
        except OSError:
            pass
    start_listener()
    try:
        start_app()
    except Exception:
        log("could not start the app:\n" + traceback.format_exc())
    log(f"bridge loaded from {BRIDGE_DIR}")


# ZBrush runs plugin files at startup without promising __name__ == "__main__", so install
# unconditionally. Tests import this file with RADIAL_BRIDGE_NO_INSTALL=1 and call install() themselves.
if not os.environ.get("RADIAL_BRIDGE_NO_INSTALL"):
    install()
