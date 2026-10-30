"""ctypes declarations for the Win32 calls the ZOrbit app needs.

Own WinDLL instances (not ctypes.windll), so argtypes set here never leak into other code in the process.
All signatures are declared explicitly: on 64-bit Windows an undeclared LPARAM/HWND is silently
truncated to 32 bits.
"""
import ctypes
import ctypes.wintypes as w
import os

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
try:
    shcore = ctypes.WinDLL("shcore", use_last_error=True)
except OSError:
    shcore = None

LRESULT = ctypes.c_ssize_t
ULONG_PTR = ctypes.c_size_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, w.WPARAM, w.LPARAM)


def _sig(dll, name, res, *args):
    f = getattr(dll, name)
    f.restype, f.argtypes = res, list(args)
    return f


# --- structures ----------------------------------------------------------------------------------
class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE),
                ("hIcon", w.HICON), ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH),
                ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON)]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _INPUTUNION)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", w.DWORD), ("biWidth", w.LONG), ("biHeight", w.LONG), ("biPlanes", w.WORD),
                ("biBitCount", w.WORD), ("biCompression", w.DWORD), ("biSizeImage", w.DWORD),
                ("biXPelsPerMeter", w.LONG), ("biYPelsPerMeter", w.LONG), ("biClrUsed", w.DWORD),
                ("biClrImportant", w.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", w.BYTE), ("BlendFlags", w.BYTE), ("SourceConstantAlpha", w.BYTE),
                ("AlphaFormat", w.BYTE)]


class COPYDATASTRUCT(ctypes.Structure):
    _fields_ = [("dwData", ULONG_PTR), ("cbData", w.DWORD), ("lpData", ctypes.c_void_p)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD), ("th32ProcessID", w.DWORD),
                ("th32DefaultHeapID", ULONG_PTR), ("th32ModuleID", w.DWORD), ("cntThreads", w.DWORD),
                ("th32ParentProcessID", w.DWORD), ("pcPriClassBase", w.LONG), ("dwFlags", w.DWORD),
                ("szExeFile", w.WCHAR * 260)]


# --- user32 --------------------------------------------------------------------------------------
DefWindowProcW = _sig(user32, "DefWindowProcW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
RegisterClassExW = _sig(user32, "RegisterClassExW", w.ATOM, ctypes.POINTER(WNDCLASSEXW))
CreateWindowExW = _sig(user32, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                       w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)
DestroyWindow = _sig(user32, "DestroyWindow", w.BOOL, w.HWND)
IsWindow = _sig(user32, "IsWindow", w.BOOL, w.HWND)
ShowWindow = _sig(user32, "ShowWindow", w.BOOL, w.HWND, ctypes.c_int)
SetWindowPos = _sig(user32, "SetWindowPos", w.BOOL, w.HWND, w.HWND, ctypes.c_int, ctypes.c_int,
                    ctypes.c_int, ctypes.c_int, w.UINT)
UpdateLayeredWindow = _sig(user32, "UpdateLayeredWindow", w.BOOL, w.HWND, w.HDC, ctypes.POINTER(w.POINT),
                           ctypes.POINTER(w.SIZE), w.HDC, ctypes.POINTER(w.POINT), w.COLORREF,
                           ctypes.POINTER(BLENDFUNCTION), w.DWORD)
SetTimer = _sig(user32, "SetTimer", ULONG_PTR, w.HWND, ULONG_PTR, w.UINT, ctypes.c_void_p)
KillTimer = _sig(user32, "KillTimer", w.BOOL, w.HWND, ULONG_PTR)
GetMessageW = _sig(user32, "GetMessageW", ctypes.c_int, ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
TranslateMessage = _sig(user32, "TranslateMessage", w.BOOL, ctypes.POINTER(w.MSG))
DispatchMessageW = _sig(user32, "DispatchMessageW", LRESULT, ctypes.POINTER(w.MSG))
PostMessageW = _sig(user32, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
PostQuitMessage = _sig(user32, "PostQuitMessage", None, ctypes.c_int)
SetWindowsHookExW = _sig(user32, "SetWindowsHookExW", w.HHOOK, ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD)
UnhookWindowsHookEx = _sig(user32, "UnhookWindowsHookEx", w.BOOL, w.HHOOK)
CallNextHookEx = _sig(user32, "CallNextHookEx", LRESULT, w.HHOOK, ctypes.c_int, w.WPARAM, w.LPARAM)
GetAsyncKeyState = _sig(user32, "GetAsyncKeyState", ctypes.c_short, ctypes.c_int)
GetCursorPos = _sig(user32, "GetCursorPos", w.BOOL, ctypes.POINTER(w.POINT))
GetForegroundWindow = _sig(user32, "GetForegroundWindow", w.HWND)
GetWindowThreadProcessId = _sig(user32, "GetWindowThreadProcessId", w.DWORD, w.HWND, ctypes.POINTER(w.DWORD))
FindWindowExW = _sig(user32, "FindWindowExW", w.HWND, w.HWND, w.HWND, w.LPCWSTR, w.LPCWSTR)
SendMessageTimeoutW = _sig(user32, "SendMessageTimeoutW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT,
                           w.UINT, ctypes.POINTER(ULONG_PTR))
SendInput = _sig(user32, "SendInput", w.UINT, w.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
GetDC = _sig(user32, "GetDC", w.HDC, w.HWND)
ReleaseDC = _sig(user32, "ReleaseDC", ctypes.c_int, w.HWND, w.HDC)
LoadCursorW = _sig(user32, "LoadCursorW", w.HANDLE, w.HINSTANCE, ctypes.c_void_p)
MonitorFromPoint = _sig(user32, "MonitorFromPoint", w.HMONITOR, w.POINT, w.DWORD)
GetMonitorInfoW = _sig(user32, "GetMonitorInfoW", w.BOOL, w.HMONITOR, ctypes.POINTER(MONITORINFO))
try:
    SetProcessDpiAwarenessContext = _sig(user32, "SetProcessDpiAwarenessContext", w.BOOL, ctypes.c_void_p)
except AttributeError:
    SetProcessDpiAwarenessContext = None

# --- gdi32 ---------------------------------------------------------------------------------------
CreateCompatibleDC = _sig(gdi32, "CreateCompatibleDC", w.HDC, w.HDC)
DeleteDC = _sig(gdi32, "DeleteDC", w.BOOL, w.HDC)
CreateDIBSection = _sig(gdi32, "CreateDIBSection", w.HBITMAP, w.HDC, ctypes.POINTER(BITMAPINFOHEADER),
                        w.UINT, ctypes.POINTER(ctypes.c_void_p), w.HANDLE, w.DWORD)
SelectObject = _sig(gdi32, "SelectObject", w.HGDIOBJ, w.HDC, w.HGDIOBJ)
DeleteObject = _sig(gdi32, "DeleteObject", w.BOOL, w.HGDIOBJ)

# --- kernel32 ------------------------------------------------------------------------------------
GetModuleHandleW = _sig(kernel32, "GetModuleHandleW", w.HMODULE, w.LPCWSTR)
CreateMutexW = _sig(kernel32, "CreateMutexW", w.HANDLE, ctypes.c_void_p, w.BOOL, w.LPCWSTR)
OpenProcess = _sig(kernel32, "OpenProcess", w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
CloseHandle = _sig(kernel32, "CloseHandle", w.BOOL, w.HANDLE)
QueryFullProcessImageNameW = _sig(kernel32, "QueryFullProcessImageNameW", w.BOOL, w.HANDLE, w.DWORD,
                                  w.LPWSTR, ctypes.POINTER(w.DWORD))
CreateToolhelp32Snapshot = _sig(kernel32, "CreateToolhelp32Snapshot", w.HANDLE, w.DWORD, w.DWORD)
Process32FirstW = _sig(kernel32, "Process32FirstW", w.BOOL, w.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
Process32NextW = _sig(kernel32, "Process32NextW", w.BOOL, w.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
GetCurrentThreadId = _sig(kernel32, "GetCurrentThreadId", w.DWORD)
GetProcessTimes = _sig(kernel32, "GetProcessTimes", w.BOOL, w.HANDLE, *[ctypes.POINTER(w.FILETIME)] * 4)

if shcore is not None:
    GetDpiForMonitor = _sig(shcore, "GetDpiForMonitor", ctypes.c_long, w.HMONITOR, ctypes.c_int,
                            ctypes.POINTER(w.UINT), ctypes.POINTER(w.UINT))
else:
    GetDpiForMonitor = None

# --- constants -----------------------------------------------------------------------------------
WS_POPUP = 0x80000000
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x8, 0x80, 0x80000, 0x08000000
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = w.HWND(-1)
HWND_MESSAGE = w.HWND(-3)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40
WM_DESTROY, WM_TIMER = 0x2, 0x113
WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP = 0x100, 0x101, 0x104, 0x105
WM_LBUTTONDOWN, WM_LBUTTONUP, WM_RBUTTONDOWN, WM_MOUSEACTIVATE = 0x201, 0x202, 0x204, 0x21
WM_APP = 0x8000
WM_COPYDATA = 0x004A
WM_SETTINGCHANGE = 0x001A
HWND_BROADCAST = w.HWND(0xFFFF)
SMTO_BLOCK, SMTO_ABORTIFHUNG = 0x1, 0x2
MA_NOACTIVATE = 3
WH_KEYBOARD_LL = 13
LLKHF_INJECTED = 0x10
ULW_ALPHA = 0x2
AC_SRC_OVER, AC_SRC_ALPHA = 0x0, 0x1
MONITOR_DEFAULTTONEAREST = 2
MDT_EFFECTIVE_DPI = 0
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP = 0x2
MOUSEEVENTF_MOVE = 0x1
ERROR_ALREADY_EXISTS = 183
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x2
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

VK_SHIFT, VK_CONTROL, VK_MENU, VK_ESCAPE, VK_LBUTTON = 0x10, 0x11, 0x12, 0x1B, 0x01
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_MENU_MASK = 0xE8        # unassigned vk: injected to stop a swallowed Alt combo opening the window menu
MODIFIER_SIDES = {VK_SHIFT: (0xA0, 0xA1), VK_CONTROL: (0xA2, 0xA3), VK_MENU: (0xA4, 0xA5)}
MODIFIER_VKS = {0x10, 0x11, 0x12, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5, VK_LWIN, VK_RWIN}


# --- helpers -------------------------------------------------------------------------------------
def key_down(vk: int) -> bool:
    return bool(GetAsyncKeyState(vk) & 0x8000)


def modifier_down(vk: int) -> bool:
    """Generic modifier (VK_SHIFT/CONTROL/MENU), either side."""
    return key_down(vk) or any(key_down(s) for s in MODIFIER_SIDES.get(vk, ()))


def cursor_pos() -> tuple[int, int]:
    pt = w.POINT()
    GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def send_keys(events) -> int:
    """events: iterable of (vk, is_up). Sends them as one SendInput batch."""
    events = list(events)
    arr = (INPUT * len(events))()
    for i, (vk, up) in enumerate(events):
        arr[i].type = INPUT_KEYBOARD
        arr[i].u.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, 0)
    return SendInput(len(events), arr, ctypes.sizeof(INPUT))


def nudge_mouse() -> None:
    """Zero-distance relative move: makes Windows emit a real WM_MOUSEMOVE, which wakes the target app's
    (and the Wacom driver's) cursor tracking after an overlay disappears from under the pen."""
    arr = (INPUT * 1)()
    arr[0].type = INPUT_MOUSE
    arr[0].u.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_MOVE, 0, 0)
    SendInput(1, arr, ctypes.sizeof(INPUT))


def process_image(pid: int) -> str:
    h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        n = w.DWORD(1024)
        return buf.value if QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ""
    finally:
        CloseHandle(h)


def window_pid(hwnd) -> int:
    pid = w.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def find_message_window(cls: str) -> int:
    """A message-only window of the given class, as an int hwnd (0 when there is none). FindWindowW cannot see
    message-only windows; they hang off HWND_MESSAGE."""
    return int(FindWindowExW(HWND_MESSAGE, None, cls, None) or 0)


def send_copydata(hwnd, dw: int, payload: bytes, timeout_ms: int = 500) -> int | None:
    """WM_COPYDATA with dwData=dw and payload to a window of another process. Returns the window's result,
    or None when it did not answer within timeout_ms (hung or gone). The call is synchronous but never blocks
    on a hung window."""
    buf = ctypes.create_string_buffer(payload, len(payload) or 1)      # alive until the call returns
    cds = COPYDATASTRUCT(dw, len(payload), ctypes.cast(buf, ctypes.c_void_p))
    result = ULONG_PTR()
    ok = SendMessageTimeoutW(hwnd, WM_COPYDATA, 0, ctypes.addressof(cds), SMTO_ABORTIFHUNG,   # not BLOCK: the hook must still run
                             timeout_ms, ctypes.byref(result))
    return int(ctypes.c_ssize_t(result.value).value) if ok else None


def running_exe_names() -> set[str]:
    """Lowercased exe names of all running processes."""
    names = set()
    snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return names
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            names.add(pe.szExeFile.lower())
            ok = Process32NextW(snap, ctypes.byref(pe))
    finally:
        CloseHandle(snap)
    return names


def pids_named(name: str) -> list[int]:
    """Process ids of every running process whose exe name is name (case does not matter)."""
    want, pids = name.lower(), []
    snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return pids
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            if pe.szExeFile.lower() == want:
                pids.append(int(pe.th32ProcessID))
            ok = Process32NextW(snap, ctypes.byref(pe))
    finally:
        CloseHandle(snap)
    return pids


def broadcast_setting_change(topic: str = "Environment") -> bool:
    """Tells every top-level window that a setting changed (WM_SETTINGCHANGE), so Explorer and the programs it
    starts afterwards pick up a new user environment variable. A hung window is skipped after 2 seconds, so this
    never blocks for long. True when the broadcast went through."""
    buf = ctypes.create_unicode_buffer(topic)            # alive until the call returns
    result = ULONG_PTR()
    ok = SendMessageTimeoutW(HWND_BROADCAST, WM_SETTINGCHANGE, 0, ctypes.addressof(buf), SMTO_ABORTIFHUNG,
                             2000, ctypes.byref(result))
    return bool(ok)


def process_created(pid: int) -> float | None:
    """When a process was created, as a Unix timestamp."""
    h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        ft = [w.FILETIME() for _ in range(4)]
        if not GetProcessTimes(h, *[ctypes.byref(f) for f in ft]):
            return None
        return (ft[0].dwHighDateTime << 32 | ft[0].dwLowDateTime) / 1e7 - 11644473600
    finally:
        CloseHandle(h)


def parent_pid(pid: int) -> int | None:
    snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return None
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            if pe.th32ProcessID == pid:
                return pe.th32ParentProcessID
            ok = Process32NextW(snap, ctypes.byref(pe))
    finally:
        CloseHandle(snap)
    return None


def launch_chain(depth: int = 2) -> str:
    """'cmd.exe (pid 1, 0.12 s earlier) <- ZBrush.exe (...)': who started this process, and how long before
    it. For logs: a slow start through ZScript's ShellExecute shows up here."""
    me = os.getpid()
    t0 = process_created(me)
    out, pid = [], me
    for _ in range(depth):
        pid = parent_pid(pid)
        if not pid:
            break
        created = process_created(pid)
        name = os.path.basename(process_image(pid)) or "?"
        out.append(f"{name} (pid {pid}, {t0 - created:.2f} s earlier)" if t0 and created else f"{name} (pid {pid})")
    return " <- ".join(out) or "?"


def monitor_for_point(x: int, y: int) -> tuple[w.RECT, float]:
    """Work area of the monitor under (x, y) and its DPI scale (1.0 = 96 dpi)."""
    hmon = MonitorFromPoint(w.POINT(x, y), MONITOR_DEFAULTTONEAREST)
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(MONITORINFO)
    GetMonitorInfoW(hmon, ctypes.byref(mi))
    scale = 1.0
    if GetDpiForMonitor is not None:
        dx, dy = w.UINT(), w.UINT()
        if GetDpiForMonitor(hmon, MDT_EFFECTIVE_DPI, ctypes.byref(dx), ctypes.byref(dy)) == 0:
            scale = dx.value / 96.0
    return mi.rcWork, scale


def make_dpi_aware() -> None:
    if SetProcessDpiAwarenessContext is not None:
        SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # PER_MONITOR_AWARE_V2
