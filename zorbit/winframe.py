"""Window-frame helpers shared by the Studio and the popout browser: finding a pywebview window by title,
removing its title bar while keeping the resizable frame, restoring a saved placement, maximising to the work
area instead of over the taskbar, WebView2 drag regions, and getting a window to the foreground. Plain Win32
through ctypes, so nothing touches .NET off the UI thread."""
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

HWND_TOPMOST, HWND_NOTOPMOST = -1, -2


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


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", w.POINT), ("ptMaxSize", w.POINT), ("ptMaxPosition", w.POINT),
                ("ptMinTrackSize", w.POINT), ("ptMaxTrackSize", w.POINT)]


class _WINDOWPOS(ctypes.Structure):
    _fields_ = [("hwnd", w.HWND), ("hwndInsertAfter", w.HWND), ("x", ctypes.c_int), ("y", ctypes.c_int),
                ("cx", ctypes.c_int), ("cy", ctypes.c_int), ("flags", w.UINT)]


_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_subclass = {}                     # keeps the callback and the original proc alive for the window's life


def _same_monitor(a, b) -> bool:
    user32.MonitorFromRect.restype = w.HMONITOR
    user32.MonitorFromRect.argtypes = [ctypes.POINTER(w.RECT), w.DWORD]
    return user32.MonitorFromRect(ctypes.byref(w.RECT(*a)), 2) == user32.MonitorFromRect(ctypes.byref(w.RECT(*b)), 2)


def limit_maximise_to_work_area(hwnd):
    """Subclasses the window to answer WM_GETMINMAXINFO. Without a caption Windows maximises over the
    whole monitor (taskbar included); this makes double-click, Win+Up, snap-to-top and our button all
    maximise to the work area, with the usual invisible-border overhang. It also tracks the window's normal
    (restored) rectangle (see normal_rect) and makes a restore land on it. Everything else passes through."""
    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    user32.GetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.SetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.CallWindowProcW.restype = _LRESULT
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    GWLP_WNDPROC, WM_GETMINMAXINFO, WM_WINDOWPOSCHANGING, WM_WINDOWPOSCHANGED = -4, 0x0024, 0x0046, 0x0047
    WM_ENTERSIZEMOVE, WM_EXITSIZEMOVE = 0x0231, 0x0232
    SWP_NOSIZE, SWP_NOMOVE = 0x0001, 0x0002
    if hwnd in _subclass:
        return
    original = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)
    # WinForms still believes the window has a caption, and on restore asks for a size that is one caption
    # taller. A second resize to fix that afterwards makes WebView2 flash black, so the restore itself is
    # given the last normal rectangle instead. In a drag off the top (or after Win+Shift+Arrow moved the
    # maximised window to another screen) Windows' position is kept and only the size is corrected.
    st = {"zoomed": bool(user32.IsZoomed(hwnd)), "normal": None, "sizemove": False}

    def proc(h, msg, wp, lp):
        if msg == WM_ENTERSIZEMOVE or msg == WM_EXITSIZEMOVE:
            st["sizemove"] = msg == WM_ENTERSIZEMOVE
        elif msg == WM_WINDOWPOSCHANGING and st["zoomed"] and st["normal"]:
            try:
                pos = _WINDOWPOS.from_address(lp)
                if not pos.flags & SWP_NOSIZE and not user32.IsZoomed(h) and not user32.IsIconic(h):
                    left, top, right, bottom = st["normal"]
                    asked = (pos.x, pos.y, pos.x + pos.cx, pos.y + pos.cy)
                    if not st["sizemove"] and _same_monitor(asked, st["normal"]):
                        pos.x, pos.y = left, top
                        pos.flags &= ~SWP_NOMOVE
                    pos.cx, pos.cy = right - left, bottom - top
            except Exception:
                pass
        r = user32.CallWindowProcW(original, h, msg, wp, lp)
        if msg == WM_WINDOWPOSCHANGED:
            zoomed, iconic = bool(user32.IsZoomed(h)), bool(user32.IsIconic(h))
            if not zoomed and not iconic:
                rc = w.RECT()
                user32.GetWindowRect(h, ctypes.byref(rc))
                st["normal"] = (rc.left, rc.top, rc.right, rc.bottom)
            if not iconic:
                st["zoomed"] = zoomed
        elif msg == WM_GETMINMAXINFO:
            try:
                mi = _MONITORINFO()
                mi.cbSize = ctypes.sizeof(_MONITORINFO)
                user32.MonitorFromWindow.restype = w.HMONITOR
                user32.MonitorFromWindow.argtypes = [w.HWND, w.DWORD]
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
    _subclass[hwnd] = (cb, original, st)
    user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(cb, ctypes.c_void_p))


def normal_rect(hwnd):
    """The window's normal (restored) rectangle as tracked by limit_maximise_to_work_area: (left, top, right,
    bottom, maximised), or None when it is not tracked or has not been placed yet. GetWindowPlacement is no
    good for this: it reports the size WinForms would restore to, which is one caption taller than the window."""
    st = _subclass.get(hwnd, (None, None, None))[2]
    if not st or not st["normal"]:
        return None
    return (*st["normal"], bool(st["zoomed"]))


def placement_record(hwnd):
    """normal_rect as the dict the preferences files keep under "window" (saved_window reads it back), or None."""
    r = normal_rect(hwnd)
    if not r:
        return None
    left, top, right, bottom, maxed = r
    return {"x": left, "y": top, "width": right - left, "height": bottom - top, "maximized": maxed}


def custom_frame(title, placement=None, pid=None, topmost=False, toolwindow=False, maximizable=True,
                 on_hwnd=None, include_hidden=False):
    """Removes the Windows title bar but keeps the resizable frame (native resize and Aero Snap), and
    themes the remaining 1 px border and corners. The page draws its own header (see index.html).
    placement: saved_window()'s result, applied exactly (create_window only gets it to within a pixel).
    pid: only a window of that process counts. topmost: keep the window above others. toolwindow: no taskbar
    button. maximizable=False: no maximise box. on_hwnd(hwnd): called once the window is found, before the
    frame is changed. include_hidden: also find a window that was created hidden.
    A hidden window is not maximised here (that would show it): show it with show_placed. Every size change
    of a visible WebView2 window flashes black, so the Studio applies all this while hidden and shows once.
    Returns the window handle, or None.
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
            if maxed and user32.IsWindowVisible(hwnd):
                user32.ShowWindow(hwnd, 3)                                         # SW_MAXIMIZE
        return hwnd
    except Exception:
        return None


def show_placed(hwnd, maximized=False):
    """Shows a window that custom_frame placed while hidden, in one step: SW_SHOWMAXIMIZED goes from hidden to
    maximised without first showing the normal size. Then brings it to the front."""
    user32.ShowWindow(hwnd, 3 if maximized else 5)                         # SW_SHOWMAXIMIZED / SW_SHOW
    force_foreground(hwnd)
    _focus_content(hwnd)


def _focus_content(hwnd):
    """Gives keyboard focus to the window's largest child (the WebView2 control). pywebview focuses it when
    the form is first shown, which for a window created hidden is before the real show, and a maximised show
    loses it. SetFocus only works within one input queue, so this thread is attached to the window's."""
    best, best_area = None, 0
    EnumProc = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user32.EnumChildWindows.argtypes = [w.HWND, EnumProc, w.LPARAM]
    user32.GetParent.restype = w.HWND
    user32.SetFocus.argtypes = [w.HWND]

    def visit(h, _):
        nonlocal best, best_area
        if user32.GetParent(h) == hwnd:
            r = w.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            area = (r.right - r.left) * (r.bottom - r.top)
            if area > best_area:
                best, best_area = h, area
        return True
    user32.EnumChildWindows(hwnd, EnumProc(visit), 0)
    if not best:
        return
    target = user32.GetWindowThreadProcessId(hwnd, None)
    me = kernel32.GetCurrentThreadId()
    attached = bool(target != me and user32.AttachThreadInput(me, target, True))
    try:
        user32.SetFocus(best)
    finally:
        if attached:
            user32.AttachThreadInput(me, target, False)


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
