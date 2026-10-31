"""A one-line message near the cursor, for the moments the app knows why a pick went nowhere.

render() draws the pill (Pillow only, so tests can run it); show() puts it in a layered, topmost tool window that
never takes focus and ignores the mouse, and destroys it after a while through a WM_TIMER on that window. One toast
at a time: a new one replaces the old. Everything runs on the app's message-loop thread. show() never raises.
"""
import ctypes
import traceback

from PIL import Image, ImageDraw

import win32 as W

CLASS_NAME = "ZOrbitToast"
TIMER_CLOSE = 1
WS_EX_TRANSPARENT = 0x20          # clicks go to the window below
TEXT = "#f0f0f0"                  # the ring's default text colour
PILL = (24, 25, 29, 235)
FONT_PX, PAD_X, PAD_Y, MAX_W = 12, 12, 6, 520      # unscaled pixels
SS = 3                            # drawn this much larger, then reduced
_hwnd = None
_class_registered = False
_wndproc_ref = None


def render(text, scale=1.0, colour=TEXT):
    """The toast as an RGBA image: text on a rounded dark pill, one line, cut short with an ellipsis if long."""
    import ring as R
    s = scale * SS
    font = R._font_for(text, int(FONT_PX * s), bold=False)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text = R._shorten(probe, text, font, (MAX_W - 2 * PAD_X) * s)
    l, _, r, _ = probe.textbbox((0, 0), text, font=font, anchor="ls")
    top, bottom = probe.textbbox((0, 0), "Åg", font=font, anchor="ls")[1::2]
    px, py = int(PAD_X * s), int(PAD_Y * s)
    wd, ht = r - l + 2 * px, bottom - top + 2 * py
    im = Image.new("RGBA", (wd, ht), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, wd - 1, ht - 1), radius=ht / 2, fill=PILL)
    d.text((px - l, py - top), text, font=font, fill=R._rgba(colour, 1.0), anchor="ls")
    return im.resize((max(1, round(wd / SS)), max(1, round(ht / SS))), Image.LANCZOS)


def _wndproc(hwnd, msg, wparam, lparam):
    try:
        if msg == W.WM_TIMER:
            W.KillTimer(hwnd, TIMER_CLOSE)
            W.DestroyWindow(hwnd)
            return 0
        if msg == W.WM_MOUSEACTIVATE:
            return W.MA_NOACTIVATE
        if msg == W.WM_DESTROY:
            global _hwnd
            if _hwnd == hwnd:
                _hwnd = None
    except Exception:
        return 0
    return W.DefWindowProcW(hwnd, msg, wparam, lparam)


def _register_class():
    global _class_registered, _wndproc_ref
    if _class_registered:
        return
    _wndproc_ref = W.WNDPROC(_wndproc)
    wc = W.WNDCLASSEXW()
    wc.cbSize = ctypes.sizeof(W.WNDCLASSEXW)
    wc.lpfnWndProc = _wndproc_ref
    wc.hInstance = W.GetModuleHandleW(None)
    wc.lpszClassName = CLASS_NAME
    if not W.RegisterClassExW(ctypes.byref(wc)):
        raise ctypes.WinError(ctypes.get_last_error())
    _class_registered = True


def _paint(hwnd, im, x, y):
    """Hands im (premultiplied here) to the layered window at (x, y) through a throw-away DIB."""
    from PIL import ImageChops
    r, g, b, a = im.split()
    data = Image.merge("RGBA", tuple(ImageChops.multiply(c, a) for c in (r, g, b)) + (a,)).tobytes("raw", "BGRA")
    wd, ht = im.size
    screen = W.GetDC(None)
    hbmp = mem = old = None
    try:
        bih = W.BITMAPINFOHEADER()
        bih.biSize = ctypes.sizeof(W.BITMAPINFOHEADER)
        bih.biWidth, bih.biHeight, bih.biPlanes, bih.biBitCount = wd, -ht, 1, 32
        bits = ctypes.c_void_p()
        hbmp = W.CreateDIBSection(screen, ctypes.byref(bih), 0, ctypes.byref(bits), None, 0)
        mem = W.CreateCompatibleDC(screen)
        old = W.SelectObject(mem, hbmp)
        ctypes.memmove(bits, data, len(data))
        blend = W.BLENDFUNCTION(W.AC_SRC_OVER, 0, 255, W.AC_SRC_ALPHA)
        W.UpdateLayeredWindow(hwnd, screen, ctypes.byref(W.w.POINT(x, y)), ctypes.byref(W.w.SIZE(wd, ht)), mem,
                              ctypes.byref(W.w.POINT(0, 0)), 0, ctypes.byref(blend), W.ULW_ALPHA)
    finally:
        if mem:
            W.SelectObject(mem, old)
            W.DeleteDC(mem)
        if hbmp:
            W.DeleteObject(hbmp)
        W.ReleaseDC(None, screen)


def close():
    global _hwnd
    hwnd, _hwnd = _hwnd, None
    if hwnd is not None and W.IsWindow(hwnd):
        W.DestroyWindow(hwnd)


def show(text, log, ms=1800, colour=TEXT):
    """Shows text just below the cursor for ms milliseconds. Never raises, never takes the focus."""
    global _hwnd
    try:
        x, y = W.cursor_pos()
        work, scale = W.monitor_for_point(x, y)
        im = render(text, scale, colour)
        wd, ht = im.size
        left = max(work.left, min(x - wd // 2, work.right - wd))
        top = y + int(26 * scale)                       # clear of the arrow
        if top + ht > work.bottom:
            top = y - ht - int(10 * scale)
        top = max(work.top, min(top, work.bottom - ht))
        _register_class()
        close()
        ex = W.WS_EX_NOACTIVATE | W.WS_EX_TOPMOST | W.WS_EX_TOOLWINDOW | W.WS_EX_LAYERED | WS_EX_TRANSPARENT
        hwnd = W.CreateWindowExW(ex, CLASS_NAME, "ZOrbit toast", W.WS_POPUP, left, top, wd, ht,
                                 None, None, W.GetModuleHandleW(None), None)
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        _hwnd = hwnd
        try:
            _paint(hwnd, im, left, top)
            W.ShowWindow(hwnd, W.SW_SHOWNOACTIVATE)
            W.SetWindowPos(hwnd, W.HWND_TOPMOST, 0, 0, 0, 0,
                           W.SWP_NOMOVE | W.SWP_NOSIZE | W.SWP_NOACTIVATE | W.SWP_SHOWWINDOW)
            W.SetTimer(hwnd, TIMER_CLOSE, max(200, int(ms)), None)
        except Exception:
            close()
            raise
    except Exception:
        try:
            log(f"toast failed ({text!r}):\n" + traceback.format_exc())
        except Exception:
            pass
