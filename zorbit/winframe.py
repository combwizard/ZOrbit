"""Window-frame helpers shared by the Studio and the popout browser: finding a pywebview window by title,
drawing without Windows' title bar, restoring a saved placement, WebView2 drag regions, and getting a window to
the foreground. Plain Win32 through ctypes, so nothing touches .NET off the UI thread.

How the frame works. The window keeps WS_CAPTION and WS_THICKFRAME, so Windows treats it like any other window:
maximise stops at the taskbar, Win+arrow and Win+Shift+arrow work on every monitor, and GetWindowPlacement is
right. Windows' own frame is removed in WM_NCCALCSIZE (the client area is the whole window; see client_rect).
pywebview is told the window is frameless, so WinForms also thinks the frame is zero wide: it restores a window
from maximised by turning the client size it kept into a window size, and the two only agree when the frame is
nothing. WebView2 would cover the whole client area, and its windows belong to another process, so a resize
border has to be a strip of the form that the control does not cover: the form's Padding (set on the UI thread,
see _set_layout) leaves it, and WM_NCHITTEST answers the resize codes there (see hit_test).

A window can also be made to fit its content (set_fitted, the browser's strip): no resize strip, no thick frame or
maximise box (so a drag to a screen edge does not snap it), and no minimum size, so the caller sizes it exactly."""
import ctypes
import ctypes.wintypes as w
import time

import theme as _theme          # the importer has put zorbit/ on sys.path

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


# --- the frame, as arithmetic on rectangles (left, top, right, bottom) --------------------------------------

HTNOWHERE, HTCLIENT = 0, 1
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = range(10, 18)
RESIZE_BORDER = 6               # logical pixels: the strip around the page where the window can be resized


def border_px(dpi=96) -> int:
    """RESIZE_BORDER in physical pixels at this DPI."""
    return round(RESIZE_BORDER * dpi / 96)


def client_rect(window, maximised, work, margin):
    """The client rectangle for a window rectangle (WM_NCCALCSIZE). A normal window has no frame to give up: all of
    it is client area. A maximised one is placed by Windows a few pixels past the work area on every side (the
    invisible border of a sizing frame), so its client area is cut back to the work area, plus margin: the strip
    of the form that is not the page (see hit_test) then lies off the screen. work: the work area of the monitor the
    window is on."""
    if not maximised:
        return tuple(window)
    left, top, right, bottom = window
    wl, wt, wr, wb = work
    return (max(left, wl - margin), max(top, wt - margin), min(right, wr + margin), min(bottom, wb + margin))


def hit_test(x, y, rect, maximised, border):
    """What WM_NCHITTEST answers for a point (screen coordinates) over a window with this rectangle: a resize code
    (HTLEFT ... HTBOTTOMRIGHT) in the border strip around the page, HTCLIENT anywhere else in the window, HTNOWHERE
    outside it. A maximised window cannot be resized, so it is all HTCLIENT. The title area is the page's own (it
    marks it with app-region: drag), and so is the maximise button: this window cannot answer HTMAXBUTTON for it."""
    left, top, right, bottom = rect
    if not (left <= x < right and top <= y < bottom):
        return HTNOWHERE
    if maximised:
        return HTCLIENT
    dl, dr, dt, db = x - left, right - 1 - x, y - top, bottom - 1 - y
    if min(dl, dr, dt, db) >= border:
        return HTCLIENT
    grip = 2 * border                                       # a corner reaches this far along each edge
    col = -1 if dl < grip else 1 if dr < grip else 0
    row = -1 if dt < grip else 1 if db < grip else 0
    on_x, on_y = min(dl, dr) < border, min(dt, db) < border
    if (on_x and row) or (on_y and col):
        return {(-1, -1): HTTOPLEFT, (-1, 1): HTTOPRIGHT, (1, -1): HTBOTTOMLEFT, (1, 1): HTBOTTOMRIGHT}[(row, col)]
    if on_x:
        return HTLEFT if col < 0 else HTRIGHT
    return HTTOP if row < 0 else HTBOTTOM


def placement_state(show_cmd, flags) -> bool:
    """Is the window maximised, from a WINDOWPLACEMENT's showCmd and flags (a minimised window that was maximised
    comes back maximised: WPF_RESTORETOMAXIMIZED)."""
    return show_cmd == 3 or (show_cmd == 2 and bool(flags & 2))          # SW_SHOWMAXIMIZED / SW_SHOWMINIMIZED


def workspace_origin(toolwindow, work, monitor):
    """Where the top-left of a WINDOWPLACEMENT rectangle is on the screen. GetWindowPlacement and SetWindowPlacement
    use workspace coordinates (from the corner of the primary monitor's work area) for a window that is not a tool
    window, which is not the screen's corner when the taskbar is on the top or left."""
    return (0, 0) if toolwindow else (work[0] - monitor[0], work[1] - monitor[1])


def to_screen(rect, origin):
    return (rect[0] + origin[0], rect[1] + origin[1], rect[2] + origin[0], rect[3] + origin[1])


def to_workspace(rect, origin):
    return (rect[0] - origin[0], rect[1] - origin[1], rect[2] - origin[0], rect[3] - origin[1])


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


def _primary_work_area() -> w.RECT:
    user32.MonitorFromPoint.restype = w.HMONITOR
    user32.MonitorFromPoint.argtypes = [w.POINT, w.DWORD]
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    user32.GetMonitorInfoW(user32.MonitorFromPoint(w.POINT(0, 0), 1), ctypes.byref(mi))      # MONITOR_DEFAULTTOPRIMARY
    return mi.rcWork


def on_a_screen(left, top, right, bottom, maximised=False) -> bool:
    """The rectangle is on a monitor that exists, with enough of its top edge on that monitor's work area to grab
    the header (200 px wide, not below the bottom). A maximised window only has to touch a monitor."""
    user32.MonitorFromRect.restype = w.HMONITOR
    user32.MonitorFromRect.argtypes = [ctypes.POINTER(w.RECT), w.DWORD]
    mon = user32.MonitorFromRect(ctypes.byref(w.RECT(left, top, right, bottom)), 0)       # MONITOR_DEFAULTTONULL
    if not mon:
        return False
    if maximised:
        return True
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return True
    wa = mi.rcWork
    return min(right, wa.right) - max(left, wa.left) >= 200 and wa.top - 16 <= top <= wa.bottom - 48


def bring_on_screen(hwnd, near=0) -> bool:
    """A window that was left on a monitor that is gone (or half off one) is centred on the work area of the
    window near (a ZBrush window), else of the primary monitor. Moves only; the size is kept, shrunk to fit.
    A maximised window comes down to its normal size there and is maximised again, unless it is hidden: then it is
    left as it is, and the caller asks again once it is shown. A minimised window is left alone. True when it was moved."""
    if user32.IsIconic(hwnd):
        return False
    r = w.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return False
    zoomed = bool(user32.IsZoomed(hwnd))
    if on_a_screen(r.left, r.top, r.right, r.bottom, zoomed):
        return False
    user32.IsWindow.argtypes = [w.HWND]
    wa = work_area(near) if near and user32.IsWindow(near) else _primary_work_area()
    if zoomed:
        if not user32.IsWindowVisible(hwnd):           # SetWindowPlacement would show it: ask again once it is shown
            return False
        user32.SetWindowPlacement.argtypes = [w.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
        wp = WINDOWPLACEMENT()
        wp.length = ctypes.sizeof(wp)
        if not user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
            return False
        n = wp.rcNormalPosition
        nw, nh = min(n.right - n.left, wa.right - wa.left), min(n.bottom - n.top, wa.bottom - wa.top)
        nx, ny = wa.left + (wa.right - wa.left - nw) // 2, wa.top + (wa.bottom - wa.top - nh) // 2
        origin = _workspace_origin(hwnd)
        n.left, n.top, n.right, n.bottom = to_workspace((nx, ny, nx + nw, ny + nh), origin)
        wp.showCmd = 1                                 # SW_SHOWNORMAL: while maximised it would only change where it restores to
        if not user32.SetWindowPlacement(hwnd, ctypes.byref(wp)):
            return False
        user32.ShowWindow(hwnd, 3)                     # SW_MAXIMIZE, on the screen it is now on
        return True
    wd, ht = min(r.right - r.left, wa.right - wa.left), min(r.bottom - r.top, wa.bottom - wa.top)
    x, y = wa.left + (wa.right - wa.left - wd) // 2, wa.top + (wa.bottom - wa.top - ht) // 2
    user32.SetWindowPos(hwnd, None, x, y, wd, ht, 0x0004 | 0x0010)             # NOZORDER NOACTIVATE
    return True


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", w.RECT * 3), ("lppos", ctypes.c_void_p)]


_LRESULT = ctypes.c_ssize_t
_WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
_subclass = {}                     # keeps the callback and the original proc alive for the window's life
_WM_LAYOUT = 0x8000 + 0x5A         # WM_APP + n, to the window itself: set its Padding and BackColor on the UI thread
_WM_FIT = 0x8000 + 0x5B            # ... and this one: fit the content or not (set_fitted), wparam 1 or 0


def _work_of(rect):
    """The work area (left, top, right, bottom) of the monitor nearest this rectangle."""
    user32.MonitorFromRect.restype = w.HMONITOR
    user32.MonitorFromRect.argtypes = [ctypes.POINTER(w.RECT), w.DWORD]
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    user32.GetMonitorInfoW(user32.MonitorFromRect(ctypes.byref(w.RECT(*rect)), 2), ctypes.byref(mi))   # NEAREST
    wa = mi.rcWork
    return wa.left, wa.top, wa.right, wa.bottom


def _nccalcsize(wparam, lparam, maximised, margin, work_of=_work_of):
    """WM_NCCALCSIZE in place: the first rectangle is the window's new rectangle on the way in (with wparam, in
    an NCCALCSIZE_PARAMS; without it the lparam is the rectangle) and its client rectangle on the way out."""
    rc = _NCCALCSIZE_PARAMS.from_address(lparam).rgrc[0] if wparam else w.RECT.from_address(lparam)
    if not maximised:
        return                                     # the client area is the whole window
    window = (rc.left, rc.top, rc.right, rc.bottom)
    rc.left, rc.top, rc.right, rc.bottom = client_rect(window, True, work_of(window), margin)


class _WINDOWPOS(ctypes.Structure):
    _fields_ = [("hwnd", w.HWND), ("after", w.HWND), ("x", ctypes.c_int), ("y", ctypes.c_int), ("cx", ctypes.c_int),
                ("cy", ctypes.c_int), ("flags", w.UINT)]


def _hold_at(pos, rect):
    """Rewrites a WINDOWPOS (WM_WINDOWPOSCHANGING) so the window stays at rect (left, top, right, bottom)."""
    pos.x, pos.y, pos.cx, pos.cy = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
    pos.flags &= ~0x0003                               # not SWP_NOSIZE or SWP_NOMOVE


def _post_layout(hwnd, border=-1, color=-1):
    """Asks the window's own procedure (install_frame's) to set the form's Padding (border, in pixels) and BackColor
    (a COLORREF) on the UI thread; -1 leaves one as it is. Posted, so it is safe from any thread and cannot wait on
    a thread that is waiting on this one. Does nothing for a window that install_frame has not been given."""
    if hwnd in _subclass:
        user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        user32.PostMessageW(hwnd, _WM_LAYOUT, border & 0xFFFFFFFF, color)


def _set_layout(hwnd, border, color):
    """On the UI thread (the window procedure): the form's Padding leaves the strip around the page that the
    WebView2 control does not cover, and its BackColor is what shows in that strip. Dock.Fill honours Padding."""
    import System
    import System.Windows.Forms as WinForms
    from System.Drawing import Color
    form = WinForms.Control.FromHandle(System.IntPtr(hwnd))
    if form is None:
        raise RuntimeError("no form for the window")
    if border >= 0:
        form.Padding = WinForms.Padding(border)
    if color >= 0:
        form.BackColor = Color.FromArgb(255, color & 255, (color >> 8) & 255, (color >> 16) & 255)


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", w.POINT), ("ptMaxSize", w.POINT), ("ptMaxPosition", w.POINT),
                ("ptMinTrackSize", w.POINT), ("ptMaxTrackSize", w.POINT)]


def _set_fit(hwnd, st, fitted):
    """On the UI thread (the window procedure): a fitted window has no Padding (no resize strip) and no MinimumSize,
    which WinForms would otherwise hold it to; leaving fitted puts back the ones it had."""
    import System
    import System.Windows.Forms as WinForms
    from System.Drawing import Size
    form = WinForms.Control.FromHandle(System.IntPtr(hwnd))
    if form is None:
        raise RuntimeError("no form for the window")
    if fitted:
        if st["min"] is None:
            st["min"] = (form.MinimumSize.Width, form.MinimumSize.Height)
        form.MinimumSize = Size(0, 0)
        form.Padding = WinForms.Padding(0)
    else:
        if st["min"] is not None:
            form.MinimumSize = Size(*st["min"])
            st["min"] = None
        form.Padding = WinForms.Padding(st["border"])


def install_frame(hwnd, on_query_end=None, on_end=None, on_moved=None):
    """Subclasses the window to draw without Windows' frame. WM_NCCALCSIZE makes the client area the whole window
    (a maximised one is cut back to the work area, see client_rect); WM_NCHITTEST answers the resize codes in the
    strip around the page (see hit_test); WinForms is kept from undoing where Windows restored the window (see
    WM_WINDOWPOSCHANGED below). Everything else passes through, so the maximise, restore, snap and Win+Shift+arrow
    behaviour is Windows' own. A message from _post_layout sets the strip up.
    Windows shutting down, restarting or signing out: on_query_end() is called on WM_QUERYENDSESSION, before the
    window is asked to close, and the answer is always "yes, go ahead"; on_end(ending) on WM_ENDSESSION (ending is
    false when something else cancelled it). on_moved() is called when the user has finished moving or sizing the
    window (WM_EXITSIZEMOVE). All run on the UI thread: keep them short. Nothing in the procedure
    may raise into Windows, so each part guards itself and falls back to the window's own procedure."""
    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    user32.GetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.SetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.CallWindowProcW.restype = _LRESULT
    user32.CallWindowProcW.argtypes = [ctypes.c_void_p, w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    user32.IsZoomed.argtypes = user32.IsIconic.argtypes = [w.HWND]
    user32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
    GWLP_WNDPROC, WM_NCCALCSIZE, WM_NCHITTEST = -4, 0x0083, 0x0084
    WM_QUERYENDSESSION, WM_ENDSESSION = 0x0011, 0x0016
    WM_WINDOWPOSCHANGING, WM_WINDOWPOSCHANGED = 0x0046, 0x0047
    WM_GETMINMAXINFO, WM_EXITSIZEMOVE = 0x0024, 0x0232
    if hwnd in _subclass:
        return
    original = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)
    st = {"border": 0, "error": None,          # border: the strip's width once the form has it, else nothing is claimed
          "plain": True, "hold": None,         # plain: neither maximised nor minimised; hold: see WM_WINDOWPOSCHANGED
          "fit": False, "min": None,           # fit: set_fitted; min: the form's MinimumSize while it is off
          "fit_done": None}                    # an Event set_fitted waits on

    def proc(h, msg, wp, lp):
        if msg == WM_GETMINMAXINFO and st["fit"]:
            r = user32.CallWindowProcW(original, h, msg, wp, lp)
            try:                                       # no smallest size: the caller makes it as small as its content
                mmi = _MINMAXINFO.from_address(lp)
                mmi.ptMinTrackSize.x = mmi.ptMinTrackSize.y = 1
            except Exception:
                pass
            return r
        if msg == WM_EXITSIZEMOVE and on_moved:
            try:
                on_moved()
            except Exception:
                pass
        if msg == WM_QUERYENDSESSION or msg == WM_ENDSESSION:
            try:
                if msg == WM_QUERYENDSESSION and on_query_end:
                    on_query_end()
                elif msg == WM_ENDSESSION and on_end:
                    on_end(bool(wp))
            except Exception:
                pass
            r = user32.CallWindowProcW(original, h, msg, wp, lp)     # WinForms raises FormClosing / FormClosed
            return 1 if msg == WM_QUERYENDSESSION else r
        if msg == WM_WINDOWPOSCHANGED:
            # Windows has just restored the window to the right place, which is on another monitor if it was moved
            # there while maximised. WinForms answers this message by moving it to where it was when it was maximised,
            # so for as long as WinForms has the message, the window stays where Windows put it.
            outer = st["hold"]                         # WinForms' own move lands here too, nested: it keeps the hold
            try:
                plain = not user32.IsZoomed(h) and not user32.IsIconic(h)
                if plain and not st["plain"]:
                    rc = w.RECT()
                    user32.GetWindowRect(h, ctypes.byref(rc))
                    st["hold"] = (rc.left, rc.top, rc.right, rc.bottom)
                st["plain"] = plain
            except Exception:
                pass
            try:
                return user32.CallWindowProcW(original, h, msg, wp, lp)
            finally:
                st["hold"] = outer
        try:
            if msg == WM_WINDOWPOSCHANGING:
                if st["hold"]:
                    _hold_at(_WINDOWPOS.from_address(lp), st["hold"])
            elif msg == WM_NCCALCSIZE:
                if not user32.IsIconic(h):
                    _nccalcsize(wp, lp, bool(user32.IsZoomed(h)), st["border"])
                    return 0
            elif msg == WM_NCHITTEST:
                rc = w.RECT()
                user32.GetWindowRect(h, ctypes.byref(rc))
                x, y = ctypes.c_short(lp & 0xFFFF).value, ctypes.c_short((lp >> 16) & 0xFFFF).value
                code = hit_test(x, y, (rc.left, rc.top, rc.right, rc.bottom),
                                bool(user32.IsZoomed(h)) or bool(user32.IsIconic(h)), 0 if st["fit"] else st["border"])
                if code not in (HTCLIENT, HTNOWHERE):
                    return code
            elif msg == _WM_LAYOUT:
                border, color = wp & 0xFFFFFFFF, lp & 0xFFFFFFFF if lp >= 0 else -1
                try:
                    _set_layout(h, -1 if border == 0xFFFFFFFF or st["fit"] else border, color)   # fitted: no strip until it is not
                    if border != 0xFFFFFFFF:
                        st["border"] = border
                        user32.SetWindowPos(h, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
                except Exception as e:                             # the strip is then missing: say so (frame_problem)
                    st["error"] = repr(e)
                return 0
            elif msg == _WM_FIT:
                try:
                    st["fit"] = bool(wp)
                    _set_fit(h, st, st["fit"])
                except Exception as e:
                    st["error"] = repr(e)
                finally:
                    if st["fit_done"]:
                        st["fit_done"].set()
                return 0
        except Exception:
            pass
        return user32.CallWindowProcW(original, h, msg, wp, lp)
    cb = _WNDPROC(proc)
    _subclass[hwnd] = (cb, original, st)
    user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(cb, ctypes.c_void_p))


def frame_problem(hwnd):
    """Why the resize strip around the page could not be set up (text for the log), or None when it was, or has not
    been tried yet."""
    st = _subclass.get(hwnd, (None, None, None))[2]
    return st["error"] if st else None


def set_fitted(hwnd, fitted, wait_s=1.0) -> bool:
    """Makes a window that install_frame has been given fit its content (fitted) or be an ordinary resizable one
    again. Fitted: no resize strip or resize codes, no thick frame or maximise box (a drag to a screen edge must not
    snap it, nor a double-click on its drag area maximise it), and no minimum size, WinForms' or Windows', so
    SetWindowPos can make it as small as its content. Not fitted: what it had before. Change it while the window is
    hidden. The form's part runs on the UI thread; this waits up to wait_s for it, so a SetWindowPos after it is
    not held to the old minimum. True when the UI thread did it in time. Never from the UI thread itself."""
    import threading
    sub = _subclass.get(hwnd)
    if not sub:
        return False
    st = sub[2]
    GWL_STYLE, BITS = -16, 0x00040000 | 0x00010000                  # WS_THICKFRAME WS_MAXIMIZEBOX
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    user32.SetWindowLongW(hwnd, GWL_STYLE, (style & ~BITS) if fitted else (style | BITS))
    done = threading.Event()
    st["fit_done"] = done
    user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    user32.PostMessageW(hwnd, _WM_FIT, 1 if fitted else 0, 0)
    ok = done.wait(wait_s)
    user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)   # FRAMECHANGED
    return ok


def place_normal(hwnd, rect, show_cmd=4):
    """SetWindowPlacement: the window's normal (restored) rectangle becomes rect (screen pixels), and its show state
    show_cmd (default SW_SHOWNOACTIVATE). That is the way to take a hidden window out of the maximised state: a hidden
    maximised window keeps WS_MAXIMIZE through SetWindowPos, and showing it would bring back its old normal rectangle.
    It also shows the window. True when Windows took it."""
    user32.GetWindowPlacement.argtypes = [w.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
    user32.SetWindowPlacement.argtypes = [w.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(wp)
    if not user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        return False
    wp.flags = 0                                       # not WPF_RESTORETOMAXIMIZED
    wp.showCmd = show_cmd
    n = wp.rcNormalPosition
    n.left, n.top, n.right, n.bottom = to_workspace(rect, _workspace_origin(hwnd))
    return bool(user32.SetWindowPlacement(hwnd, ctypes.byref(wp)))


def _read_placement(hwnd):
    """(showCmd, flags, rcNormalPosition) from GetWindowPlacement, the rectangle in workspace coordinates; None if
    Windows does not say."""
    user32.GetWindowPlacement.argtypes = [w.HWND, ctypes.POINTER(WINDOWPLACEMENT)]
    wp = WINDOWPLACEMENT()
    wp.length = ctypes.sizeof(wp)
    if not user32.GetWindowPlacement(hwnd, ctypes.byref(wp)):
        return None
    n = wp.rcNormalPosition
    return wp.showCmd, wp.flags, (n.left, n.top, n.right, n.bottom)


def _workspace_origin(hwnd):
    user32.MonitorFromPoint.restype = w.HMONITOR
    user32.MonitorFromPoint.argtypes = [w.POINT, w.DWORD]
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    user32.GetMonitorInfoW(user32.MonitorFromPoint(w.POINT(0, 0), 1), ctypes.byref(mi))      # MONITOR_DEFAULTTOPRIMARY
    toolwindow = bool(user32.GetWindowLongW(hwnd, -20) & 0x00000080)                        # WS_EX_TOOLWINDOW
    wa, mon = mi.rcWork, mi.rcMonitor
    return workspace_origin(toolwindow, (wa.left, wa.top), (mon.left, mon.top))


def normal_rect(hwnd):
    """The window's normal (restored) rectangle in screen coordinates, from GetWindowPlacement: (left, top, right,
    bottom, maximised), or None when Windows does not say or the window has no size yet."""
    got = _read_placement(hwnd)
    if not got:
        return None
    show_cmd, flags, rc = got
    if rc[2] <= rc[0] or rc[3] <= rc[1]:
        return None
    return (*to_screen(rc, _workspace_origin(hwnd)), placement_state(show_cmd, flags))


def placement_record(hwnd):
    """normal_rect as the dict the preferences files keep under "window" (saved_window reads it back), or None."""
    r = normal_rect(hwnd)
    if not r:
        return None
    left, top, right, bottom, maxed = r
    return {"x": left, "y": top, "width": right - left, "height": bottom - top, "maximized": maxed}


def apply_theme(hwnd, window):
    """Sets the frame's dark mode, corners and border colour from a theme preset's "window" part. Plain Win32,
    so it may run on any thread, and again on a window that is already up."""
    dwm = ctypes.WinDLL("dwmapi")
    dwm.DwmSetWindowAttribute.argtypes = [w.HWND, w.DWORD, ctypes.c_void_p, w.DWORD]
    for attr, val in ((20, window["dwm_dark"]),          # immersive dark mode
                      (33, 2),                           # rounded corners
                      (34, _theme.colorref(window["border"]))):   # border colour (COLORREF is 0x00bbggrr)
        v = ctypes.c_int(val)
        dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), 4)
    if window.get("background"):                       # the strip around the page (see install_frame) is the form's colour
        _post_layout(hwnd, color=_theme.colorref(window["background"]))


def _system_dpi() -> int:
    try:
        return user32.GetDpiForSystem() or 96
    except Exception:
        return 96


def custom_frame(title, placement=None, pid=None, topmost=False, toolwindow=False, maximizable=True,
                 on_hwnd=None, include_hidden=False, theme=None):
    """Draws the window without Windows' title bar and frame, and keeps what a framed window does (native
    resize, Aero Snap, maximise to the work area; see the top of this file), and themes the border and corners.
    The page draws its own header (see index.html). The window must have been created frameless
    (create_window(frameless=True, easy_drag=False)), so WinForms agrees that the frame is zero wide.
    placement: saved_window()'s result, applied exactly (create_window only gets it to within a pixel).
    pid: only a window of that process counts. topmost: keep the window above others. toolwindow: no taskbar
    button. maximizable=False: no maximise box. on_hwnd(hwnd): called once the window is found, before the
    frame is changed (it installs the window procedure, install_frame, which is done here if it did not).
    include_hidden: also find a window that was created hidden. theme: the "window" part of a
    theme preset (dark mode, border colour); the dark preset when not given.
    A hidden window is not maximised here (that would show it): show it with show_placed. Every size change
    of a visible WebView2 window flashes black, so the Studio applies all this while hidden and shows once.
    Returns the window handle, or None.
    Plain Win32 only: touching window.native (a .NET Form) from pywebview's worker thread deadlocks."""
    try:
        theme_window = theme or _theme.PRESETS["dark"]["window"]
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
        install_frame(hwnd)                                              # no-op when on_hwnd did it
        GWL_STYLE, WS_CAPTION, WS_MAXIMIZEBOX = -16, 0x00C00000, 0x00010000
        WS_KEEP = 0x00040000 | 0x00080000 | 0x00020000 | WS_MAXIMIZEBOX  # THICKFRAME SYSMENU MIN MAX boxes
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if not maximizable:
            style &= ~WS_MAXIMIZEBOX
            WS_KEEP &= ~WS_MAXIMIZEBOX
        # WS_CAPTION and WS_THICKFRAME are what make Windows maximise to the work area and snap the window; the
        # caption is not drawn, since install_frame answers WM_NCCALCSIZE with no frame at all
        user32.SetWindowLongW(hwnd, GWL_STYLE, style | WS_CAPTION | WS_KEEP)
        if toolwindow:
            GWL_EXSTYLE, WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = -20, 0x00000080, 0x00040000
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (ex | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)   # no taskbar button
        apply_theme(hwnd, theme_window)
        _post_layout(hwnd, border=border_px(_system_dpi()))
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
