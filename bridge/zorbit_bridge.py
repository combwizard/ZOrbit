"""ZOrbit bridge: the ZBrush 2026+ side of ZOrbit.

Loaded by ZBrush at startup from a folder listed in the user environment variable ZBRUSH_PLUGIN_PATH (the
installer adds this folder), or once by hand: ZScript > Python Scripting > Load.

What it does:
  * Palette Zplugin > ZOrbit with:
      Apply      carries out the pending pick (%LOCALAPPDATA%\\ZOrbit\\request.json). The app triggers it
                 either through the listener below or by pressing the bridge key; for the key route bind it
                 natively: Ctrl+Alt+click Apply, press F9, then Preferences > Hotkeys > Store. (No Python
                 hotkey on purpose: native bindings proved more reliable.)
      Start App  starts the ZOrbit app if it is not running (it also starts automatically here).
      Status     shows listener, app and last-request state.
  * Picks come as request.json actions: {"brush"|"alpha"|"material"|"texture": name, "file": path} selects that
    asset (loading it from the file first when ZBrush does not have it), {"press": path}, {"set": path,
    "value": v} and {"toggle": path} drive the interface directly. {"filepress": button, "file": path} tells
    ZBrush the next file name and then presses the button, which saves or opens that file with no dialog.
  * A hidden message-only window on ZBrush's main thread. The app posts WM_APP+1 to it after a pick, so no
    keystroke is needed. Its handle is published in listener.json only after a timer message has proved
    that ZBrush dispatches window messages to Python; if that never happens the app uses the bridge key.
  * The state channel: the app writes the interface paths a ring shows to zstate_query.json and posts WM_APP+2;
    the listener reads them here, on ZBrush's main thread, writes zstate.json (on or off, slider values and
    ranges, greyed or missing items, the current tool, brush and material) and posts WM_APP+19 back to the
    app's control window. After a pick it answers the last question again, unasked, so the app's copy is
    current before the next ring opens.
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

# --- locations -----------------------------------------------------------------------------------
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ZOrbit")
LAUNCH_FILE = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ZOrbit", "launch.json")
REQUEST_FILE = os.path.join(DATA_DIR, "request.json")
REQUEST_TXT = os.path.join(DATA_DIR, "request.txt")       # the same pick for the ZScript bridge (ZBrush 2022-2025)
LISTENER_FILE = os.path.join(DATA_DIR, "listener.json")
STATE_QUERY_FILE = os.path.join(DATA_DIR, "zstate_query.json")    # the app's question: which paths to read
STATE_FILE = os.path.join(DATA_DIR, "zstate.json")                # the answer: a snapshot of those paths
LOG_FILE = os.path.join(DATA_DIR, "bridge.log")
BRIDGE_DIR = os.path.dirname(os.path.abspath(__file__))
PALETTE = "Zplugin:ZOrbit"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(f"ZOrbit: {msg}")
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 500_000:
            os.replace(LOG_FILE, LOG_FILE + ".old")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# Before the first log line a failure would reach only ZBrush's console, so the import is logged here.
try:
    import zbrush.commands as zbc
except Exception:
    log("the plugin could not start: ZBrush's Python API could not be imported:\n" + traceback.format_exc())
    raise

WM_APP_PICK = 0x8000 + 1
WM_APP_STATE = 0x8000 + 2         # app -> listener: answer zstate_query.json (wparam query id, lparam app window)
WM_APP_STATE_READY = 0x8000 + 19  # listener -> the app's control window: zstate.json is written (wparam its id)
APP_CLASS = "ZOrbitControl"       # the only window class the state answer is posted to
STATE_V = 1                       # the zstate*.json format, and the "state" capability in listener.json
STATE_MAX_PATHS = 128             # paths read per snapshot at most; the rest are left out and `truncated` set
STATE_BUDGET_S = 0.020            # reading stops after this long, also with `truncated`
STATE_QUERY_MAX_BYTES = 256_000   # a bigger question is not read
STATE_LOG_FIRST = 10              # answers logged after a load; later only the odd one (see _answer)
STATE_LOG_SLOW_MS = 5.0           # an answer whose reads took longer than this is logged
WM_TIMER = 0x113
TIMER_VERIFY, TIMER_RETRY, TIMER_SELECT = 1, 2, 3
SELECT_TRIES = 25                 # an asset just loaded: look for its button every 40 ms, for up to a second
PUBLISH_TRIES = 10                # listener.json refused (the app has it open): tried again on the verify timer
PUBLISH_RETRY_MS = 300            # ... this long apart, about 3 s in all
# kind -> (palette its buttons live in, interface path of the button that loads a file). Maxon's own xmd_bridge
# plugin selects and loads alphas, materials and textures the same way.
ASSETS = {"brush": ("Brush", "Brush:Load Brush"), "alpha": ("Alpha", "Alpha:Import"),
          "material": ("Material", "Material:Load"), "texture": ("Texture", "Texture:Import")}
VK_LBUTTON, VK_RBUTTON = 0x01, 0x02
SM_SWAPBUTTON = 23
REQUEST_MAX_AGE_S = 10            # a request older than this is stale (its pick never went out): not carried out


# State that must survive a reload of this file (ZBrush's Python VM is shared and persistent).
S = sys.modules.setdefault("_zorbit_bridge_state", types.ModuleType("_zorbit_bridge_state"))
if not hasattr(S, "keepalive"):
    S.keepalive, S.hwnd, S.seq, S.verified, S.last = [], None, 0, False, "none yet"
if not isinstance(getattr(S, "select_pending", None), list):
    S.select_pending = []         # (interface path, tries left) per asset this pick loaded from file, in order
for _name, _value in (("pick", 0),                 # id of the last request taken from request.json
                      ("state_ctrl", None),        # the app window of the last state question, for the refresh
                      ("state_count", 0), ("state_last", ""),
                      ("publish_tries", 0)):       # tries at publishing listener.json since the listener started
    if not hasattr(S, _name):
        setattr(S, _name, _value)
del _name, _value

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
PostMessageW = _sig(user32, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
GetClassNameW = _sig(user32, "GetClassNameW", ctypes.c_int, w.HWND, w.LPWSTR, ctypes.c_int)
GetAsyncKeyState = _sig(user32, "GetAsyncKeyState", ctypes.c_short, ctypes.c_int)
GetSystemMetrics = _sig(user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
GetModuleHandleW = _sig(kernel32, "GetModuleHandleW", w.HMODULE, w.LPCWSTR)
GetCurrentThreadId = _sig(kernel32, "GetCurrentThreadId", w.DWORD)
OpenMutexW = _sig(kernel32, "OpenMutexW", w.HANDLE, w.DWORD, w.BOOL, w.LPCWSTR)
CloseHandle = _sig(kernel32, "CloseHandle", w.BOOL, w.HANDLE)
HWND_MESSAGE = w.HWND(-3)


def primary_down() -> bool:
    """The primary mouse button (the one that strokes) is down. GetAsyncKeyState reads the physical buttons, so
    with the buttons swapped in Windows' mouse settings the primary one is VK_RBUTTON."""
    return bool(GetAsyncKeyState(VK_RBUTTON if GetSystemMetrics(SM_SWAPBUTTON) else VK_LBUTTON) & 0x8000)


# --- carrying out a pick -------------------------------------------------------------------------
def _button_paths(palette: str, name: str, a: dict) -> list:
    """Interface paths a loaded asset's button may have, best first. ZBrush names the button after the item's
    file, not after the name in the menu: 'Clay Buildup' is the button ClayBuildup. The app puts that name in
    a['button'] when it found the file; failing that, the file's own name is tried."""
    names = [a.get("button"), name]
    f = a.get("file")
    if f:
        names.append(os.path.splitext(os.path.basename(str(f).replace("\\", "/")))[0])
    out = []
    for n in names:
        if n and f"{palette}:{n}" not in out:
            out.append(f"{palette}:{n}")
    return out


def _do_asset(kind: str, a: dict) -> str:
    palette, loader = ASSETS[kind]
    name = a[kind]
    paths = _button_paths(palette, name, a)
    path = next((p for p in paths if zbc.exists(p)), None)
    if path:
        zbc.press(path)
        # A later asset of the same kind wins over one of the pick still waiting to be selected; other kinds stay.
        S.select_pending = [e for e in S.select_pending if not e[0].startswith(palette + ":")]
        return f"{kind} {name}: selected"
    f = a.get("file")
    if f and os.path.isfile(f):
        zbc.set_next_filename(f.replace("\\", "/"))
        zbc.press(loader)
        now = next((p for p in paths if zbc.exists(p)), None)
        if now:
            zbc.press(now)
        # ZBrush finishes adding the new item only after the pick returns, so a press now may find no button or
        # not take: the listener presses it again once ZBrush is done (apply_request starts that after the last
        # action). Without a listener (the Apply button only) this is all we can do. One entry per asset, in
        # order. Until the button shows, the one named after the file is the likeliest.
        S.select_pending.append((now or (paths[0] if a.get("button") else paths[-1]), SELECT_TRIES))
        later = "; selecting it once ZBrush has added it" if S.hwnd and IsWindow(S.hwnd) else ""
        return f"{kind} {name}: loaded from {f}{later} (button there now: {bool(now)})"
    return f"{kind} {name}: NOT loaded in ZBrush and no file known"


def _do_file(a: dict) -> str:
    """Sets the next file name, then presses the button that uses it (Document:Export writes it, File:Open reads it)."""
    button, f = a["filepress"], a.get("file")
    if not zbc.exists(button):                            # before the name is set: it would wait for another button
        return f"file {button}: no such interface item"
    if not f:
        return f"file {button}: no file given"
    f = str(f).replace("\\", "/")
    zbc.set_next_filename(f)
    zbc.press(button)
    return f"file {button}: ok, file {f}"


def _do_action(a: dict) -> str:
    if "filepress" in a:
        return _do_file(a)
    for kind in ASSETS:
        if kind in a:
            res = _do_asset(kind, a)
            if kind == "brush":
                # Still switched: the note only explains a brush that seems not to take outside Edit mode.
                res += "" if zbc.get("Transform:Edit") else " (Edit mode is off)"
            return res
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
    if (not str(sender or "").startswith("listener") and primary_down()
            and S.hwnd and IsWindow(S.hwnd)):
        SetTimer(S.hwnd, TIMER_RETRY, 40, None)           # the bridge key mid-stroke: wait like a listener pick does
        log(f"apply ({sender or 'button'}): the left mouse button is down; waiting for the stroke to end")
        return
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
    if not isinstance(req, dict):
        log(f"apply ({sender or 'button'}): unreadable request: not an object")
        return
    rid = req.get("id")
    try:
        age = time.time() - float(req.get("time"))
    except (TypeError, ValueError):
        age = 0.0                                         # no time in it: carry it out
    # A pick held back for a stroke was fresh when it arrived; the stroke can last longer than the limit (the app
    # waits up to 30 s), so the age only counts for a request applied as it comes in.
    if age > REQUEST_MAX_AGE_S and not str(sender or "").endswith("after stroke"):
        log(f"apply ({sender or 'button'}): request #{req.get('id')} is {age:.0f} s old; ignored")
        _picked(rid)                                      # dropped, but the state after it is the one the app waits for
        _refresh_state(f"after pick #{rid}")
        return
    S.select_pending = []                                 # a newer pick wins over items still waiting to be selected
    if S.hwnd and IsWindow(S.hwnd):
        KillTimer(S.hwnd, TIMER_SELECT)
    results = []
    for a in req.get("actions", []):
        try:
            results.append(_do_action(a))
        except Exception as e:
            results.append(f"{a!r}: FAILED {type(e).__name__}: {e}")
    listening = bool(S.hwnd and IsWindow(S.hwnd))
    later = ""
    if S.select_pending and listening:
        # The other actions have already run; these are pressed one after another once ZBrush shows them.
        later = " (selected after the pick: " + ", ".join(p for p, _ in S.select_pending) + ")"
    S.last = f"#{req.get('id')} '{req.get('label')}' via {sender or 'button'}: " + "; ".join(results) + later
    log(S.last)
    if S.select_pending and listening:
        SetTimer(S.hwnd, TIMER_SELECT, 40, None)          # the items this pick loaded, once ZBrush shows them
    else:
        S.select_pending = []
    # Toggles and sliders are current now; the brush of a load is not until _select_pending has pressed it, and
    # it sends the state once more when its queue is empty. The id is set only now: a question answered while an
    # action ran (a long load can pump messages) must not claim this pick.
    _picked(rid)
    _refresh_state(f"after pick #{rid}")


# --- listener window -----------------------------------------------------------------------------
def _publish_listener():
    """Writes listener.json atomically. The app reads it on every ring open and every pick, and a file it has open
    cannot be replaced: the replace is tried three times, 2 ms apart, then the error goes to the caller."""
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = LISTENER_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"hwnd": int(S.hwnd), "pid": os.getpid(), "thread": GetCurrentThreadId(),
                   "verified": time.time(), "state": STATE_V}, f)    # state: answers WM_APP_STATE
    for attempt in range(3):
        try:
            os.replace(tmp, LISTENER_FILE)
            return
        except PermissionError:                           # the app is reading the old one this very moment
            if attempt == 2:
                raise
            time.sleep(0.002)


def _on_verified(hwnd) -> None:
    """TIMER_VERIFY: ZBrush dispatches window messages to Python, so the listener is published. A refused publish
    is tried again on the same timer, PUBLISH_TRIES times in all, then given up with one line. Never raises."""
    S.verified = True
    S.publish_tries += 1
    try:
        _publish_listener()
    except Exception as e:
        if S.publish_tries < PUBLISH_TRIES:
            SetTimer(hwnd, TIMER_VERIFY, PUBLISH_RETRY_MS, None)
        else:
            log(f"listener: could not publish listener.json in {PUBLISH_TRIES} tries ({e!r}); picks use the "
                f"bridge key and the ring shows no state until the plugin loads again")
        return
    log(f"listener verified: ZBrush dispatches window messages to Python (window {int(hwnd)}, "
        f"thread {GetCurrentThreadId()})" + (f"; published on try {S.publish_tries}" if S.publish_tries > 1 else ""))


def _select_pending(hwnd):
    """Presses the buttons of the brushes, alphas, materials and textures a pick loaded a moment ago, one after
    another in the pick's order, each once ZBrush shows it (never during a stroke). Every entry has its own tries."""
    pend = S.select_pending
    if not pend:
        KillTimer(hwnd, TIMER_SELECT)
        return
    if primary_down():
        return                                            # a stroke: wait, without using up a try
    path, tries = pend[0]
    if zbc.exists(path):
        try:
            zbc.press(path)
        except Exception as e:                            # ZBrush busy: the next tick tries again, while tries last
            if tries > 1:
                pend[0] = (path, tries - 1)
            else:
                pend.pop(0)
            log(f"{path}: press failed after loading ({e!r}); {'trying again' if tries > 1 else 'giving up'}")
        else:
            pend.pop(0)
            log(f"{path}: selected after loading ({SELECT_TRIES - tries + 1} looks)")
    elif tries <= 1:
        pend.pop(0)
        log(f"{path}: loaded, but its button did not appear within a second; not selected")
    else:
        pend[0] = (path, tries - 1)
    if not pend:
        KillTimer(hwnd, TIMER_SELECT)
        _refresh_state(f"after pick #{S.pick}, its loaded items selected")    # the brush in `extras` changed


# --- the state channel ---------------------------------------------------------------------------
def _class_name(hwnd) -> str:
    buf = ctypes.create_unicode_buffer(256)
    n = GetClassNameW(hwnd, buf, 256)
    return buf.value[:n] if n > 0 else ""


def _app_window(hwnd):
    """hwnd when it is the app's control window, else None: the answer is never posted to a foreign window."""
    try:
        h = int(hwnd or 0)
        return h if h and _class_name(h) == APP_CLASS else None
    except Exception:
        return None


def _num(x) -> float:
    v = float(x)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"not a finite number: {x!r}")
    return v


def _item_name(title) -> str:
    """ZBrush's title of an ItemInfo slot, 'SimpleBrush.', as the name 'SimpleBrush'."""
    t = str(title).strip()
    return t[:-1] if t.endswith(".") else t


def _extras() -> dict:
    """The current tool, brush and material, and Edit mode. A read that fails leaves its key out."""
    out = {}
    reads = (("tool", lambda: _item_name(zbc.get_title("Tool:ItemInfo"))),
             ("brush", lambda: _item_name(zbc.get_title("Brush:ItemInfo"))),
             ("brush_file", lambda: str(zbc.get_title("Brush:Current Brush")).strip().replace("\\", "/")),
             ("material", lambda: _item_name(zbc.get_title("Material:ItemInfo"))),
             ("edit", lambda: bool(zbc.get("Transform:Edit"))),
             ("edit_enabled", lambda: bool(zbc.is_enabled("Transform:Edit"))))
    for key, read in reads:
        try:
            out[key] = read()
        except Exception:
            pass
    return out


def _read_item(path: str, kinds: set) -> dict:
    """One path's entry: s is ok, disabled or missing (or error when a read raised); v for set and toggle, min and
    max for set."""
    try:
        if not zbc.exists(path):
            return {"s": "missing"}
        s = "ok" if zbc.is_enabled(path) else "disabled"
    except Exception:
        return {"s": "error"}
    item = {"s": s}
    try:
        if "set" in kinds or "toggle" in kinds:
            item["v"] = _num(zbc.get(path))
        if "set" in kinds:
            item["min"], item["max"] = _num(zbc.get_min(path)), _num(zbc.get_max(path))
    except Exception:
        # A greyed item may not give its value; it stays greyed. An enabled one that cannot be read is an error.
        return {"s": s} if s == "disabled" else {"s": "error"}
    return item


def _query_paths(query: dict) -> dict:
    """{path: kinds} in the question's order, each path once with its kinds merged. Entries that are not
    {"p": str, "k": str} objects are skipped."""
    out = {}
    paths = query.get("paths")
    for e in paths if isinstance(paths, list) else ():
        if not isinstance(e, dict) or not isinstance(e.get("p"), str) or not e["p"]:
            continue
        kinds = out.setdefault(e["p"], set())
        if isinstance(e.get("k"), str):
            kinds.add(e["k"])
    return out


_clock = time.perf_counter
_answers_logged = 0               # state answers logged since this file was loaded


def _picked(rid) -> None:
    """Records the id of the request just taken from request.json, for the `pick` field of the next snapshot."""
    if isinstance(rid, int) and not isinstance(rid, bool):
        S.pick = rid


def _snapshot(query: dict) -> dict:
    """Reads the asked paths now, on ZBrush's main thread. At most STATE_MAX_PATHS paths and STATE_BUDGET_S of
    reading; whatever is left out sets `truncated`. Never raises for a read: a path whose read raises is "error"."""
    t0 = _clock()
    try:
        session = str(int(_num(zbc.zbrush_info(7))))       # 7: ZBrush's unique session id
    except Exception:
        session = ""
    extras = _extras()
    asked = _query_paths(query)
    items, truncated = {}, len(asked) > STATE_MAX_PATHS
    for i, (path, kinds) in enumerate(asked.items()):
        if i >= STATE_MAX_PATHS:
            break
        if _clock() - t0 >= STATE_BUDGET_S:
            truncated = True
            break
        items[path] = _read_item(path, kinds)
    ms = (_clock() - t0) * 1000.0
    return {"v": STATE_V, "id": query.get("id"), "pick": S.pick, "pid": os.getpid(), "session": session,
            "time": time.time(), "ms": round(ms, 2), "truncated": truncated, "extras": extras, "items": items}


def _read_query():
    """(question, None) or (None, (kind, why)): kind is "missing" (no file: the app has stopped asking), "bad"
    (not a question this plugin answers) or "busy" (the file could not be opened just now)."""
    try:
        with open(STATE_QUERY_FILE, "rb") as f:
            raw = f.read(STATE_QUERY_MAX_BYTES + 1)
    except FileNotFoundError:
        return None, ("missing", "there is no zstate_query.json")
    except OSError as e:
        return None, ("busy", f"zstate_query.json could not be read: {e!r}")
    if len(raw) > STATE_QUERY_MAX_BYTES:
        return None, ("bad", f"zstate_query.json is over {STATE_QUERY_MAX_BYTES} bytes")
    try:
        q = json.loads(raw.decode("utf-8"))
    except ValueError as e:
        return None, ("bad", f"unreadable zstate_query.json: {e!r}")
    qid = q.get("id") if isinstance(q, dict) else None
    if not isinstance(q, dict) or q.get("v") != STATE_V or not isinstance(qid, int) or isinstance(qid, bool) \
            or qid < 0:
        return None, ("bad", f"zstate_query.json is not a version {STATE_V} question with an id")
    return q, None


def _write_state(snap: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = f"{STATE_FILE}.{os.getpid()}.tmp"               # two ZBrush instances may answer at the same moment
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, allow_nan=False)
    for attempt in range(3):
        try:
            os.replace(tmp, STATE_FILE)                   # atomic: the app never reads half a snapshot
            return
        except PermissionError:                           # the app is reading the old one this very moment
            if attempt == 2:
                raise
            time.sleep(0.002)


def _answer(ctrl, why: str, q: dict) -> bool:
    """Takes the snapshot for question q, writes zstate.json and posts WM_APP_STATE_READY to ctrl, the app's
    control window. Never raises: it runs from the listener and from ZBrush's Apply button. True when posted.
    The first STATE_LOG_FIRST answers after a load are logged (the round trip is measured from them), later ones
    only when something is off: cut short, not posted, slow, or a read that raised."""
    global _answers_logged
    try:
        snap = _snapshot(q)
        _write_state(snap)
        posted = bool(PostMessageW(ctrl, WM_APP_STATE_READY, snap["id"], 0))
        statuses = [e["s"] for e in snap["items"].values()]
        counts = ", ".join(f"{statuses.count(s)} {s}" for s in ("missing", "disabled", "error") if s in statuses)
        lag = ""
        try:
            if why == "asked":
                lag = f", {(snap['time'] - float(q.get('time'))) * 1000:.0f} ms after the question was written"
        except (TypeError, ValueError):
            pass
        S.state_count += 1
        S.state_last = (f"#{snap['id']} ({why}): {len(snap['items'])} paths in {snap['ms']:.1f} ms{lag}"
                        + (f" ({counts})" if counts else "") + (", truncated" if snap["truncated"] else "")
                        + ("" if posted else ", NOT posted to the app"))
        if (_answers_logged < STATE_LOG_FIRST or snap["truncated"] or not posted or snap["ms"] > STATE_LOG_SLOW_MS
                or "error" in statuses):
            _answers_logged += 1
            log("state " + S.state_last)
        return posted
    except Exception:
        log(f"state ({why}) error:\n" + traceback.format_exc())
        return False


def _on_state_query(wparam, lparam) -> None:
    """WM_APP_STATE. Not held back during a stroke: reads change nothing in ZBrush."""
    ctrl = _app_window(lparam)
    if ctrl is None:
        log(f"state: question #{wparam} from a window that is not ZOrbit's ({lparam}); not answered")
        return
    q, problem = _read_query()
    if q is None:
        log(f"state: asked, but {problem[1]}; not answered")
        return
    S.state_ctrl = ctrl                                   # a question (again): picks send the state from now on
    _answer(ctrl, "asked", q)


def _refresh_state(why: str) -> None:
    """After a pick: answers the last question again, unasked, so the app's copy is current before the next ring
    opens. Only once this ZBrush has been asked, and only while that app window is still there. The app deletes
    its question when it stops asking (the setting turned off): then the refreshes stop too, until it asks again."""
    try:
        ctrl = _app_window(S.state_ctrl)
        if ctrl is None:
            return
        q, problem = _read_query()
        if q is None:
            if problem[0] == "bad":
                log(f"state: {problem[1]}; no more unasked answers until the app asks again")
            if problem[0] != "busy":                      # a file just being replaced does not stop the refreshes
                S.state_ctrl = None
            return
        _answer(ctrl, why, q)
    except Exception:
        log("state refresh error:\n" + traceback.format_exc())


def _wndproc(hwnd, msg, wparam, lparam):
    try:
        if msg == WM_APP_STATE:
            _on_state_query(wparam, lparam)
            return 0
        if msg == WM_APP_PICK:
            if primary_down():                             # never switch tools in the middle of a stroke
                SetTimer(hwnd, TIMER_RETRY, 40, None)
            else:
                apply_request("listener")
            return 0
        if msg == WM_TIMER and wparam == TIMER_RETRY:
            if not primary_down():
                KillTimer(hwnd, TIMER_RETRY)
                apply_request("listener, after stroke")
            return 0
        if msg == WM_TIMER and wparam == TIMER_SELECT:
            _select_pending(hwnd)
            return 0
        if msg == WM_TIMER and wparam == TIMER_VERIFY:
            KillTimer(hwnd, TIMER_VERIFY)
            _on_verified(hwnd)
            return 0
    except Exception:
        log("listener error:\n" + traceback.format_exc())
        return 0
    return DefWindowProcW(hwnd, msg, wparam, lparam)


def start_listener() -> None:
    if S.hwnd and IsWindow(S.hwnd):
        DestroyWindow(S.hwnd)                             # from a previous load; same thread
    S.hwnd, S.verified, S.publish_tries = None, False, 0
    try:
        os.remove(LISTENER_FILE)                          # republished once verified
    except OSError:
        pass
    S.seq += 1
    proc = WNDPROC(_wndproc)
    S.keepalive.append(proc)                              # never freed: Windows may still hold it
    hinst = GetModuleHandleW(None)
    cls = f"ZOrbitBridge{S.seq}"
    wc = WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = proc
    wc.hInstance = hinst
    wc.lpszClassName = cls
    if not RegisterClassExW(ctypes.byref(wc)):
        log(f"listener: RegisterClassExW failed ({ctypes.get_last_error()}); bridge key only")
        return
    hwnd = CreateWindowExW(0, cls, "ZOrbit bridge", 0, 0, 0, 0, 0, HWND_MESSAGE, None, hinst, None)
    if not hwnd:
        log(f"listener: CreateWindowExW failed ({ctypes.get_last_error()}); bridge key only")
        return
    S.hwnd = hwnd
    SetTimer(hwnd, TIMER_VERIFY, 200, None)


# --- the app -------------------------------------------------------------------------------------
def _launch(kind: str):
    """Command line for 'app' or 'studio' from %APPDATA%/ZOrbit/launch.json, which the installer writes
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
    if errlog_name:
        # The app prints every log line too, so this file would grow by a copy of radiald.log on every start.
        errlog = os.path.join(DATA_DIR, errlog_name)
        try:
            if os.path.getsize(errlog) > 200_000:
                os.replace(errlog, errlog + ".old")
        except OSError:
            pass
    out = open(os.path.join(DATA_DIR, errlog_name), "a", encoding="utf-8") if errlog_name else subprocess.DEVNULL
    try:
        return subprocess.Popen(cmd, cwd=os.path.dirname(cmd[0]), env=env, creationflags=flags, close_fds=True,
                                stdin=subprocess.DEVNULL, stdout=out, stderr=out)
    finally:
        if errlog_name:
            out.close()


def _not_installed():
    zbc.message_ok("ZOrbit: the app was not found.\n\nIf you installed ZOrbit with its installer, start "
                   "\"ZOrbit Studio\" from the Start menu once. If you use the portable zip or run from "
                   "source, start ZOrbit.exe (or the app) once so it records where it is.", "ZOrbit")


def app_running() -> bool:
    h = OpenMutexW(0x00100000, False, "Local\\ZOrbit")   # SYNCHRONIZE
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
    """Opens ZOrbit Studio, the companion app (menu editor, brush library, settings)."""
    cmd = _launch("studio")
    if not cmd:
        _not_installed()
        return
    _spawn(cmd)
    log("opened Studio")


def status(sender: str = "") -> None:
    pending = "yes" if os.path.exists(REQUEST_FILE) else "no"
    state = f"{S.state_count} answer(s), last {S.state_last}" if S.state_count else "not asked yet"
    zbc.message_ok(
        f"Listener: {'verified, window ' + str(int(S.hwnd)) if S.verified else 'NOT verified (bridge key only)'}\n"
        f"App running: {'yes' if app_running() else 'no'}\n"
        f"Pending request: {pending}\n"
        f"Last pick: {S.last}\n"
        f"State channel: {state}\n"
        f"Logs: {DATA_DIR}", "ZOrbit")


def install() -> None:
    """Builds the palette and starts the listener and the app. Each part is tried on its own and a failure is
    logged, so one broken button does not take the rest of the palette down."""
    failed = 0

    def attempt(what, fn, *args):
        nonlocal failed
        try:
            fn(*args)
        except Exception:
            failed += 1
            log(f"could not {what}:\n" + traceback.format_exc())

    def add_palette():
        if not zbc.exists(PALETTE):
            zbc.add_subpalette(PALETTE, 0)

    def add_button(name, info, fn):
        path = f"{PALETTE}:{name}"
        if zbc.exists(path):
            zbc.delete_interface_item(path)
        zbc.add_button(path, info, fn)

    attempt("create the palette " + PALETTE, add_palette)
    for name, info, fn in (("Studio", "Opens ZOrbit Studio: edit menus, browse brushes, settings.", open_studio),
                           ("Apply", "Carries out the ZOrbit pick. Bind F9 to it natively.", apply_request),
                           ("Start App", "Starts the ZOrbit app if it is not running.", start_app),
                           ("Status", "Shows the ZOrbit bridge state.", status)):
        attempt(f"create the button {name}", add_button, name, info, fn)
    for p in (REQUEST_FILE, REQUEST_TXT):          # a pick left by a ZBrush that quit before applying it
        try:
            os.remove(p)
            log(f"removed a pick left over from earlier: {os.path.basename(p)}")
        except OSError:
            pass
    attempt("start the listener", start_listener)
    try:
        start_app()
    except Exception:
        log("could not start the app:\n" + traceback.format_exc())
    log(f"bridge loaded from {BRIDGE_DIR}" + (f" ({failed} part(s) failed, see above)" if failed else ""))


# ZBrush runs plugin files at startup without promising __name__ == "__main__", so install
# unconditionally. Tests import this file with RADIAL_BRIDGE_NO_INSTALL=1 and call install() themselves.
if not os.environ.get("RADIAL_BRIDGE_NO_INSTALL"):
    try:
        install()
    except Exception:
        log("the plugin could not start:\n" + traceback.format_exc())
        raise
