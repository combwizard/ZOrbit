"""Notification-area (system tray) icon for the ZOrbit app, ctypes only.

Shell_NotifyIcon callbacks need a normal top-level window: the app's control window is message-only, so it
cannot receive them (nor the broadcast "TaskbarCreated" message). Tray therefore owns a hidden, never-shown
WS_POPUP tool window, created on the calling thread. That thread must pump messages (the app's GetMessage
loop does), and create()/destroy() must be called from it.

    tray = Tray("ZOrbit 1.0", icon_path, on_command)
    tray.create()
    ...
    tray.destroy()

on_command(name) is called with "browser", "studio", "reload", "logs" or "quit".
"""
import ctypes
import ctypes.wintypes as w
import os
import time

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_shell32 = ctypes.WinDLL("shell32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


def _sig(dll, name, res, *args):
    f = getattr(dll, name)
    f.restype, f.argtypes = res, list(args)
    return f


class _WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", w.UINT), ("style", w.UINT), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE),
                ("hIcon", w.HICON), ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH),
                ("lpszMenuName", w.LPCWSTR), ("lpszClassName", w.LPCWSTR), ("hIconSm", w.HICON)]


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", w.DWORD), ("Data2", w.WORD), ("Data3", w.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128),
                ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
                ("uVersion", w.UINT),                       # union with uTimeout
                ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD), ("guidItem", _GUID),
                ("hBalloonIcon", w.HICON)]


# --- user32 --------------------------------------------------------------------------------------
_DefWindowProcW = _sig(_user32, "DefWindowProcW", LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_RegisterClassExW = _sig(_user32, "RegisterClassExW", w.ATOM, ctypes.POINTER(_WNDCLASSEXW))
_UnregisterClassW = _sig(_user32, "UnregisterClassW", w.BOOL, w.LPCWSTR, w.HINSTANCE)
_CreateWindowExW = _sig(_user32, "CreateWindowExW", w.HWND, w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD,
                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                        w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID)
_DestroyWindow = _sig(_user32, "DestroyWindow", w.BOOL, w.HWND)
_RegisterWindowMessageW = _sig(_user32, "RegisterWindowMessageW", w.UINT, w.LPCWSTR)
_LoadImageW = _sig(_user32, "LoadImageW", w.HANDLE, w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int,
                   ctypes.c_int, w.UINT)
_LoadIconW = _sig(_user32, "LoadIconW", w.HICON, w.HINSTANCE, ctypes.c_void_p)
_DestroyIcon = _sig(_user32, "DestroyIcon", w.BOOL, w.HICON)
_GetSystemMetrics = _sig(_user32, "GetSystemMetrics", ctypes.c_int, ctypes.c_int)
_CreatePopupMenu = _sig(_user32, "CreatePopupMenu", w.HMENU)
_AppendMenuW = _sig(_user32, "AppendMenuW", w.BOOL, w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR)
_SetMenuDefaultItem = _sig(_user32, "SetMenuDefaultItem", w.BOOL, w.HMENU, w.UINT, w.UINT)
_DestroyMenu = _sig(_user32, "DestroyMenu", w.BOOL, w.HMENU)
_TrackPopupMenu = _sig(_user32, "TrackPopupMenu", w.BOOL, w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int,
                       ctypes.c_int, w.HWND, ctypes.c_void_p)
_SetForegroundWindow = _sig(_user32, "SetForegroundWindow", w.BOOL, w.HWND)
_PostMessageW = _sig(_user32, "PostMessageW", w.BOOL, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_GetCursorPos = _sig(_user32, "GetCursorPos", w.BOOL, ctypes.POINTER(w.POINT))
_SetTimer = _sig(_user32, "SetTimer", ctypes.c_size_t, w.HWND, ctypes.c_size_t, w.UINT, ctypes.c_void_p)
_KillTimer = _sig(_user32, "KillTimer", w.BOOL, w.HWND, ctypes.c_size_t)
# --- shell32 / kernel32 --------------------------------------------------------------------------
_Shell_NotifyIconW = _sig(_shell32, "Shell_NotifyIconW", w.BOOL, w.DWORD, ctypes.POINTER(NOTIFYICONDATAW))
_GetModuleHandleW = _sig(_kernel32, "GetModuleHandleW", w.HMODULE, w.LPCWSTR)

# --- constants -----------------------------------------------------------------------------------
NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_SHOWTIP = 0x1, 0x2, 0x4, 0x80
NOTIFYICON_VERSION_4 = 4
WM_NULL, WM_DESTROY, WM_TIMER, WM_CONTEXTMENU = 0x0, 0x2, 0x113, 0x7B
WM_LBUTTONUP, WM_LBUTTONDBLCLK, WM_RBUTTONUP = 0x202, 0x203, 0x205
NIN_KEYSELECT = 0x401
WM_TRAY = 0x8000 + 40                       # WM_APP + 40: our callback message
WS_POPUP, WS_EX_TOOLWINDOW = 0x80000000, 0x80
IMAGE_ICON, LR_LOADFROMFILE = 1, 0x10
SM_CXSMICON = 49
IDI_APPLICATION = 32512
MF_STRING, MF_SEPARATOR = 0x0, 0x800
TPM_RIGHTBUTTON, TPM_NONOTIFY, TPM_RETURNCMD = 0x2, 0x80, 0x100
ERROR_CLASS_ALREADY_EXISTS = 1410
TIMER_RETRY = 1

CLASS_NAME = "ZOrbitTray"
ICON_ID = 1
CMD_STUDIO, CMD_RELOAD, CMD_LOGS, CMD_QUIT, CMD_BROWSER = 1, 2, 3, 4, 5
MENU_ITEMS = [(CMD_BROWSER, "Brush browser", "browser"), (CMD_STUDIO, "Open Studio", "studio"),
              (CMD_RELOAD, "Reload menus", "reload"), (CMD_LOGS, "Open logs folder", "logs"), None,
              (CMD_QUIT, "Quit ZOrbit", "quit")]
_CMD_NAMES = {i[0]: i[2] for i in MENU_ITEMS if i}


def _signed16(v: int) -> int:
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


class Tray:
    def __init__(self, app_title, icon_path, on_command, log=None):
        self.title = str(app_title)
        self.icon_path = icon_path
        self.on_command = on_command
        self._log = log or (lambda msg: None)
        self.hwnd = None
        self.added = False                  # the shell currently shows our icon
        self.version4 = False
        self.last_add_ok = False            # result of the most recent NIM_ADD
        self.last_delete_ok = None          # result of NIM_DELETE in destroy()
        self._hicon = None
        self._own_icon = False              # hicon was loaded by us (must be destroyed)
        self._proc = None                   # keeps the WNDPROC alive
        self._hinst = None
        self._class_registered = False
        self._taskbar_msg = 0
        self._menu_open = False
        self._retries = 0
        self._last_studio = 0.0

    # --- lifetime --------------------------------------------------------------------------------
    def create(self) -> bool:
        """Creates the hidden window and adds the icon. Returns whether the icon is shown; if Explorer is not
        ready yet the window stays and the icon is added when it is (retry timer / TaskbarCreated)."""
        if self.hwnd:
            return self.added
        self._hinst = _GetModuleHandleW(None)
        self._taskbar_msg = _RegisterWindowMessageW("TaskbarCreated")
        self._proc = WNDPROC(self._wndproc)
        wc = _WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(_WNDCLASSEXW)
        wc.lpfnWndProc = self._proc
        wc.hInstance = self._hinst
        wc.lpszClassName = CLASS_NAME
        if _RegisterClassExW(ctypes.byref(wc)):
            self._class_registered = True
        elif ctypes.get_last_error() != ERROR_CLASS_ALREADY_EXISTS:
            raise ctypes.WinError(ctypes.get_last_error())
        hwnd = _CreateWindowExW(WS_EX_TOOLWINDOW, CLASS_NAME, self.title, WS_POPUP, 0, 0, 0, 0,
                                None, None, self._hinst, None)
        if not hwnd:
            err = ctypes.get_last_error()
            self._unregister_class()
            raise ctypes.WinError(err)
        self.hwnd = hwnd
        self._load_icon()
        if not self._add():
            self._log("tray: icon not added yet; will retry")
            _SetTimer(self.hwnd, TIMER_RETRY, 2000, None)
        return self.added

    def destroy(self) -> None:
        if self.hwnd:
            _KillTimer(self.hwnd, TIMER_RETRY)
            self.last_delete_ok = self._notify(NIM_DELETE) if self.added else False
            self.added = False
            _DestroyWindow(self.hwnd)
            self.hwnd = None
        self._unregister_class()
        if self._hicon and self._own_icon:
            _DestroyIcon(self._hicon)
        self._hicon = None
        self._proc = None

    def _unregister_class(self):
        if self._class_registered:
            _UnregisterClassW(CLASS_NAME, self._hinst)
            self._class_registered = False

    # --- icon ------------------------------------------------------------------------------------
    def _load_icon(self):
        size = _GetSystemMetrics(SM_CXSMICON) or 16
        h = None
        if self.icon_path and os.path.isfile(self.icon_path):
            h = _LoadImageW(None, self.icon_path, IMAGE_ICON, size, size, LR_LOADFROMFILE)
        if h:
            self._own_icon = True
        else:
            self._log(f"tray: could not load icon {self.icon_path!r}; using the default application icon")
            h = _LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))
            self._own_icon = False
        self._hicon = h

    def _data(self, flags=0) -> NOTIFYICONDATAW:
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = ICON_ID
        nid.uFlags = flags
        return nid

    def _notify(self, op, nid=None) -> bool:
        return bool(_Shell_NotifyIconW(op, ctypes.byref(nid or self._data())))

    def _add(self) -> bool:
        nid = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._hicon
        nid.szTip = self.title[:127]
        self.last_add_ok = self.added = self._notify(NIM_ADD, nid)
        if self.added:
            ver = self._data()
            ver.uVersion = NOTIFYICON_VERSION_4
            self.version4 = self._notify(NIM_SETVERSION, ver)
            if not self.version4:
                self._log("tray: NOTIFYICON_VERSION_4 not accepted; using legacy callbacks")
            _KillTimer(self.hwnd, TIMER_RETRY)
        return self.added

    # --- window procedure ------------------------------------------------------------------------
    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAY:
                self._on_callback(wparam, lparam)
                return 0
            if msg == WM_TIMER and wparam == TIMER_RETRY:
                self._retries += 1
                if self.added or self._add() or self._retries >= 15:
                    _KillTimer(hwnd, TIMER_RETRY)
                return 0
            if self._taskbar_msg and msg == self._taskbar_msg:
                self._log("tray: Explorer restarted; re-adding the icon")
                self._add()
                return 0
        except Exception as e:
            self._log(f"tray: callback error: {e!r}")
            return 0
        return _DefWindowProcW(hwnd, msg, wparam, lparam)

    def _on_callback(self, wparam, lparam):
        event = lparam & 0xFFFF                 # v4 and legacy both carry the mouse message in the low word
        if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK, NIN_KEYSELECT):
            now = time.monotonic()              # a double-click delivers an up and a dblclk: open only once
            if now - self._last_studio > 1.5:
                self._last_studio = now
                self._command("studio")
        elif event == (WM_CONTEXTMENU if self.version4 else WM_RBUTTONUP):
            if self.version4:
                x, y = _signed16(wparam), _signed16(wparam >> 16)
                if x == 0 and y == 0:
                    x, y = self._cursor()
            else:
                x, y = self._cursor()
            self.show_menu(x, y)

    @staticmethod
    def _cursor():
        pt = w.POINT()
        _GetCursorPos(ctypes.byref(pt))
        return pt.x, pt.y

    def _command(self, name):
        try:
            self.on_command(name)
        except Exception as e:
            self._log(f"tray: command {name!r} failed: {e!r}")

    # --- menu ------------------------------------------------------------------------------------
    def build_menu(self):
        """Creates the popup menu (caller must DestroyMenu it). Returns the HMENU."""
        menu = _CreatePopupMenu()
        if not menu:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            for item in MENU_ITEMS:
                if item is None:
                    _AppendMenuW(menu, MF_SEPARATOR, 0, None)
                else:
                    _AppendMenuW(menu, MF_STRING, item[0], item[1])
            _SetMenuDefaultItem(menu, CMD_STUDIO, False)     # bold
        except Exception:
            _DestroyMenu(menu)
            raise
        return menu

    def show_menu(self, x, y):
        if self._menu_open or not self.hwnd:
            return
        self._menu_open = True
        menu = self.build_menu()
        try:
            _SetForegroundWindow(self.hwnd)          # without this the menu never closes on outside clicks
            cmd = _TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY, x, y, 0,
                                  self.hwnd, None)
            _PostMessageW(self.hwnd, WM_NULL, 0, 0)
        finally:
            _DestroyMenu(menu)
            self._menu_open = False
        name = _CMD_NAMES.get(cmd)
        if name:
            self._command(name)
