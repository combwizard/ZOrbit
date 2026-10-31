"""Is the Microsoft Edge WebView2 runtime installed? pywebview falls back to the old Internet Explorer engine
without it, which cannot show the browser or the Studio, so the windows check first and say what is missing.
Read from the registry the way pywebview does (webview/platforms/winforms.py, _is_chromium). Standard library
and ctypes only: it runs before pywebview is imported."""
import ctypes
import winreg

DOWNLOAD_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"
MESSAGE = ("ZOrbit needs the Microsoft Edge WebView2 runtime for this window. "
           f"Install it from {DOWNLOAD_URL} and try again.")
MIN_VERSION = (86, 0, 622, 0)           # the oldest runtime pywebview accepts

# The Evergreen runtime first, then the Beta, Dev and Canary channels, which pywebview also accepts.
_CLIENTS = ("{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}", "{2CD8A007-E189-409D-A2C8-9AF4EF3C72AA}",
            "{0D50BFEC-CD6A-4F9A-964C-C7416E3ACB10}", "{65C35B14-6C1D-4122-AC46-7148CC9D6497}")
_PATHS = (r"SOFTWARE\Microsoft\EdgeUpdate\Clients\{}", r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{}")


def _parse(version: str):
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        return None


def installed() -> str | None:
    """The version of the WebView2 runtime ("124.0.2478.51"), or None when there is none. Looks in HKLM and
    HKCU, in the 64-bit view and under WOW6432Node."""
    for client in _CLIENTS:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for template in _PATHS:
                for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
                    try:
                        with winreg.OpenKey(hive, template.format(client), 0, winreg.KEY_READ | view) as key:
                            version = str(winreg.QueryValueEx(key, "pv")[0])
                    except OSError:
                        continue
                    parsed = _parse(version)
                    if parsed and parsed >= MIN_VERSION:
                        return version
    return None


def require(log, show_message: bool = True) -> bool:
    """True when the runtime is there. Otherwise logs a line through log, tells the user in a message box (plain
    Win32: pywebview cannot be used to show it) unless show_message is false, and returns False. A hidden
    pre-warm passes False, so nothing pops up that nobody asked for."""
    version = installed()
    if version:
        log(f"WebView2 runtime {version}")
        return True
    log("the Microsoft Edge WebView2 runtime is not installed; the window cannot open")
    if show_message:
        try:
            MB_OK, MB_ICONERROR, MB_SETFOREGROUND = 0x0, 0x10, 0x10000
            ctypes.WinDLL("user32").MessageBoxW(None, MESSAGE, "ZOrbit", MB_OK | MB_ICONERROR | MB_SETFOREGROUND)
        except Exception as e:
            log(f"could not show the message: {e!r}")
    return False
