"""Window-frame helpers shared by the Studio and the popout browser: finding a pywebview window by title,
removing its title bar while keeping the resizable frame, restoring a saved placement, WebView2 drag regions,
and getting a window to the foreground. Plain Win32 through ctypes, so nothing touches .NET off the UI thread."""
import ctypes
import ctypes.wintypes as w
import time

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT]
user32.SetWindowPos.restype = w.BOOL
user32.GetWindowLongW.argtypes = [w.HWND, ctypes.c_int]
user32.GetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_long]
user32.SetWindowLongW.restype = ctypes.c_long
user32.GetForegroundWindow.restype = w.HWND
user32.SetForegroundWindow.argtypes = [w.HWND]
user32.BringWindowToTop.argtypes = [w.HWND]
user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
user32.GetWindowThreadProcessId.restype = w.DWORD
user32.AttachThreadInput.argtypes = [w.DWORD, w.DWORD, w.BOOL]
user32.AllowSetForegroundWindow.argtypes = [w.DWORD]
kernel32.GetCurrentThreadId.restype = w.DWORD

HWND_TOPMOST = -1


class WINDOWPLACEMENT(ctypes.Structure):
    _fields_ = [("length", w.UINT), ("flags", w.UINT), ("showCmd", w.UINT), ("ptMinPosition", w.POINT),
                ("ptMaxPosition", w.POINT), ("rcNormalPosition", w.RECT)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]


def main_window(title, pid=None, include_hidden=False):
    """The largest visible top-level window with this exact title (optionally in process pid).
    pywebview also creates a tiny helper window with the same title, so FindWindow alone picks wrongly.
    Size comes from the window's normal (restored) rectangle, so a minimised window still counts.
    include_hidden: do not skip invisible windows (a window created hidden, like the popout)."""
    best, best_area = None, 0
    EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user32.EnumWindows.argtypes = [EnumProc, w.LPARAM]

    def visit(h, _):
        nonlocal best, best_area
        if not include_hidden and not user32.IsWindowVisible(h):
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
        wp = WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(wp)
        if user32.GetWindowPlacement(h, ctypes.byref(wp)):
            r = wp.rcNormalPosition
        else:
            r = w.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
        area = (r.right - r.left) * (r.bottom - r.top)
        if area > best_area:
            best, best_area = h, area
        return True
    user32.EnumWindows(EnumProc(visit), 0)
    return best if best_area > 200 * 200 else None


def saved_window(saved, min_w, min_h):
    """A saved window ({"x", "y", "width", "height", "maximized"}, as read from the preferences file) as
    (x, y, width, height, maximized) in pixels, or None. Shrunk to fit its screen, and centred on the nearest
    screen when that monitor is gone or the header is out of reach."""
    s = saved
    try:
        x, y, wd, ht = (int(s[k]) for k in ("x", "y", "width", "height"))
        maxed = bool(s.get("maximized"))
    except (TypeError, KeyError, ValueError, AttributeError):
        return None

    user32.MonitorFromRect.restype = w.HMONITOR
    user32.MonitorFromRect.argtypes = [ctypes.POINTER(w.RECT), w.DWORD]
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
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


def work_area(hwnd) -> w.RECT:
    user32.MonitorFromWindow.restype = w.HMONITOR
    user32.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(mi))
    return mi.rcWork


def custom_frame(title, placement=None, pid=None, topmost=False, toolwindow=False, maximizable=True,
                 on_hwnd=None, include_hidden=False):
    """Removes the Windows title bar but keeps the resizable frame (native resize and Aero Snap), and
    themes the remaining 1 px border and corners. The page draws its own header (see index.html).
    placement: saved_window()'s result, applied exactly (create_window only gets it to within a pixel).
    pid: only a window of that process counts. topmost: keep the window above others. toolwindow: no taskbar
    button. maximizable=False: no maximise box. on_hwnd(hwnd): called once the window is found, before the
    frame is changed. include_hidden: also find a window that was created hidden.
    Plain Win32 only: touching window.native (a .NET Form) from pywebview's worker thread deadlocks."""
    try:
        hwnd = None
        for _ in range(100):                                                       # up to ~10 s for the window
            hwnd = main_window(title, pid, include_hidden=include_hidden)
            if hwnd:
                break
            time.sleep(0.1)
        if not hwnd:
            return
        if on_hwnd:
            on_hwnd(hwnd)
        GWL_STYLE, WS_CAPTION = -16, 0x00C00000
        WS_KEEP = 0x00040000 | 0x00080000 | 0x00020000 | 0x00010000      # THICKFRAME SYSMENU MIN MAX boxes
        if not maximizable:
            WS_KEEP &= ~0x00010000                                       # no MAXIMIZEBOX
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        user32.SetWindowLongW(hwnd, GWL_STYLE, (style & ~WS_CAPTION) | WS_KEEP)
        if toolwindow:
            GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x00000080, 0x00040000
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)   # no taskbar button
        dwm = ctypes.WinDLL("dwmapi")
        dwm.DwmSetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
        for attr, val in ((20, 1),                       # immersive dark mode
                          (33, 2),                       # rounded corners
                          (34, 0x00352F2B)):             # border colour #2b2f35 (COLORREF is 0x00bbggrr)
            v = ctypes.c_int(val)
            dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)
        flags = 0x0001 | 0x0002 | 0x0010 | 0x0020                      # NOSIZE NOMOVE NOACTIVATE FRAMECHANGED
        if topmost:
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        else:
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, flags | 0x0004)                 # NOZORDER
        if placement:
            x, y, wd, ht, maxed = placement
            user32.SetWindowPos(hwnd, None, x, y, wd, ht, 0x0004 | 0x0010)             # NOZORDER NOACTIVATE
            if maxed:
                user32.ShowWindow(hwnd, 3)                                         # SW_MAXIMIZE
    except Exception:
        pass


def enable_drag_regions():
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


def force_foreground(hwnd) -> bool:
    """Brings the window to the front. SetForegroundWindow alone is refused when another process owns the
    foreground, so if that did not work the thread is briefly attached to the foreground window's thread
    (which lends it the right) around BringWindowToTop + SetForegroundWindow. True when the window ended up
    in front."""
    user32.SetForegroundWindow(hwnd)
    if user32.GetForegroundWindow() == hwnd:
        return True
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, fg_thread, False)
    return user32.GetForegroundWindow() == hwnd


def allow_set_foreground(pid=-1) -> bool:
    """Lets process pid (default: any process) take the foreground; call it from the process that has it."""
    return bool(user32.AllowSetForegroundWindow(pid & 0xFFFFFFFF))
