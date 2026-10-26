"""The ZScript bridge for ZBrush 2022-2025, which have no Python API: request format and installation.

Files:
  <ZBrush>\\ZStartup\\ZPlugs64\\RadialMenuBridge.zsc        compiled in ZBrush from bridge/zscript/RadialMenuBridge.txt
  <ZBrush>\\ZStartup\\ZPlugs64\\RadialMenuData\\bridge.cfg   written here: where picks arrive, how to start the app
  <ZBrush>\\ZStartup\\ZPlugs64\\RadialMenuData\\*.lnk        shortcuts that start the app and the Studio (see SHORTCUTS)
  %LOCALAPPDATA%\\RadialMenu\\request.txt                  every pick, next to request.json (written by the app)

ZScript cannot read environment variables or JSON, and its strings stop at 255 characters. So both files hold
one value per line, and paths are absolute, in their 8.3 short form when the long form is not plain ASCII.

ZBrush 2022-2025 load plugins only from ZStartup\\ZPlugs64 inside the installation, usually under Program
Files. install()/remove() try a plain copy first and fall back to a copy by this program run as administrator
(one UAC prompt): RadialMenu.exe --zscript-copy|--zscript-remove <staging folder> <ZPlugs64>.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import filecmp
import os
import shutil
import subprocess
import sys

import paths

PLUGIN = "RadialMenuBridge.zsc"
SOURCE = "RadialMenuBridge.txt"
DATA = "RadialMenuData"
CFG = "bridge.cfg"
MAGIC = "RADIALMENU 1"
MAX_LINE = 255                          # longest string ZScript reads in one go
REQUEST_TXT = os.path.join(paths.DATA_DIR, "request.txt")
STAGE_DIR = os.path.join(paths.DATA_DIR, "zscript_stage")


# --- text ZScript can read -----------------------------------------------------------------------
def ascii_path(p, spaces=False) -> str:
    """p itself if it is plain ASCII (and, with spaces=True, has no spaces), else its 8.3 short form when the
    volume keeps 8.3 names."""
    p = str(p or "")
    if not p or (p.isascii() and not (spaces and " " in p)):
        return p
    buf = ctypes.create_unicode_buffer(1024)
    if ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024) and buf.value.isascii():
        return buf.value
    return p


def _line(v) -> str:
    s = " ".join(str(v).splitlines()).strip()
    return s or "-"


def _value(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return _line(v)


def request_lines(seq, label, actions) -> list[str]:
    """request.txt as lines: the magic line, id, label, then per action its kind and arguments."""
    lines = [MAGIC, str(seq), _line(label)]
    for a in actions:
        if "brush" in a:
            lines += ["brush", _line(a["brush"]), _line(ascii_path(a.get("file")))]
        elif "set" in a:
            lines += ["set", _line(a["set"]), _value(a.get("value"))]
        elif "press" in a:
            lines += ["press", _line(a["press"])]
        elif "toggle" in a:
            lines += ["toggle", _line(a["toggle"])]
    return lines


def encode(lines) -> tuple[bytes, list[str]]:
    """Bytes in the ANSI code page (what ZBrush 2022-2025 use), plus problems ZScript would trip over."""
    problems, out = [], []
    for s in lines:
        b = s.encode("mbcs", errors="replace")
        if b.decode("mbcs") != s:
            problems.append(f"not representable in the Windows code page: {s!r}")
        if len(b) > MAX_LINE:
            problems.append(f"longer than {MAX_LINE} bytes, ZScript will cut it: {s!r}")
        out.append(b)
    return b"\n".join(out) + b"\n", problems


def write_request(seq, label, actions) -> list[str]:
    data, problems = encode(request_lines(seq, label, actions))
    tmp = REQUEST_TXT + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, REQUEST_TXT)        # atomic: the bridge never sees half a request
    return problems


def _command(argv) -> str:
    """A command line for ZScript's ShellExecute, without quotes where 8.3 names make that possible."""
    parts = []
    for a in argv:
        a = ascii_path(a, spaces=True) if os.path.exists(a) else a
        parts.append(f'"{a}"' if " " in a else a)
    return " ".join(parts)


def cfg_lines() -> list[str]:
    """bridge.cfg: magic, the folder picks arrive in (with a trailing backslash), the command lines that
    start the app and the Studio, and whether the plugin starts the app when ZBrush loads it (1/0)."""
    os.makedirs(paths.DATA_DIR, exist_ok=True)
    cmds = paths.launch_commands()
    return [MAGIC, ascii_path(paths.DATA_DIR).rstrip("\\") + "\\", _command(cmds["app"]), _command(cmds["studio"]),
            "1"]


# --- installation --------------------------------------------------------------------------------
def bundled() -> str | None:
    """The compiled plugin shipped with this build, or None (it has to be compiled in ZBrush first)."""
    p = os.path.join(paths.ZSCRIPT_DIR, PLUGIN)
    return p if os.path.isfile(p) else None


def zplugs(install_path) -> str:
    return os.path.join(str(install_path), "ZStartup", "ZPlugs64")


def status(install_path) -> dict:
    """installed: the plugin is in this ZBrush. current: it, its bridge.cfg and its shortcuts match this build."""
    dest = zplugs(install_path)
    plug, cfg = os.path.join(dest, PLUGIN), os.path.join(dest, DATA, CFG)
    installed = os.path.isfile(plug)
    current = False
    if installed and bundled():
        try:
            with open(cfg, encoding="mbcs", errors="replace") as f:
                cfg_ok = f.read().splitlines() == cfg_lines()
            links_ok = all(os.path.isfile(os.path.join(dest, DATA, n)) for n in SHORTCUTS)
            current = cfg_ok and links_ok and filecmp.cmp(plug, bundled(), shallow=False)
        except OSError:
            pass
    return {"installed": installed, "current": current, "zplugs": dest}


# The plugin starts the app and the Studio by opening these shortcuts through ZBrush's own ZFileUtils64.dll
# (ZStartup\ZPlugs64\MacroData, LaunchAppWithFile). ZScript's ShellExecute goes through cmd.exe, and on
# Windows 11 that opens a Windows Terminal window first, which takes seconds. The command lines in bridge.cfg
# are the fallback when the DLL or a shortcut is missing.
SHORTCUTS = {"app.lnk": "app", "studio.lnk": "studio"}


def _make_shortcut(path, argv) -> None:
    ps = ("$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:RM_LNK); $s.TargetPath = $env:RM_EXE; "
          "$s.Arguments = $env:RM_ARGS; $s.WorkingDirectory = $env:RM_CWD; $s.Save()")
    env = dict(paths.clean_env(), RM_LNK=path, RM_EXE=argv[0], RM_ARGS=subprocess.list2cmdline(argv[1:]),
               RM_CWD=os.path.dirname(argv[0]))
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], env=env, check=True,
                   timeout=60, creationflags=0x08000000, capture_output=True)          # CREATE_NO_WINDOW


def _stage() -> str:
    shutil.rmtree(STAGE_DIR, ignore_errors=True)
    os.makedirs(os.path.join(STAGE_DIR, DATA))
    shutil.copyfile(bundled(), os.path.join(STAGE_DIR, PLUGIN))
    data, _ = encode(cfg_lines())
    with open(os.path.join(STAGE_DIR, DATA, CFG), "wb") as f:
        f.write(data)
    cmds = paths.launch_commands()
    for name, which in SHORTCUTS.items():
        _make_shortcut(os.path.join(STAGE_DIR, DATA, name), cmds[which])
    return STAGE_DIR


def copy_staged(stage, dest) -> None:
    """Puts the staged plugin and its data folder into ZPlugs64 (also run elevated, see the module doc)."""
    os.makedirs(os.path.join(dest, DATA), exist_ok=True)
    shutil.copyfile(os.path.join(stage, PLUGIN), os.path.join(dest, PLUGIN))
    for name in (CFG, *SHORTCUTS):
        shutil.copyfile(os.path.join(stage, DATA, name), os.path.join(dest, DATA, name))


def remove_from(dest) -> None:
    """Deletes only what copy_staged() puts there."""
    for p in (os.path.join(dest, PLUGIN), *(os.path.join(dest, DATA, n) for n in (CFG, *SHORTCUTS))):
        if os.path.exists(p):
            os.remove(p)
    try:
        os.rmdir(os.path.join(dest, DATA))
    except OSError:
        pass                            # not empty (or gone): leave it


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("fMask", w.ULONG), ("hwnd", w.HWND), ("lpVerb", w.LPCWSTR),
                ("lpFile", w.LPCWSTR), ("lpParameters", w.LPCWSTR), ("lpDirectory", w.LPCWSTR), ("nShow", ctypes.c_int),
                ("hInstApp", w.HINSTANCE), ("lpIDList", ctypes.c_void_p), ("lpClass", w.LPCWSTR),
                ("hkeyClass", w.HKEY), ("dwHotKey", w.DWORD), ("hIconOrMonitor", w.HANDLE), ("hProcess", w.HANDLE)]


def _run_elevated(args) -> tuple[bool, str]:
    """Runs this program with args as administrator and waits. (ok, message)."""
    if paths.FROZEN:
        exe, params = sys.executable, args
    else:
        pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
        exe = pyw if os.path.isfile(pyw) else sys.executable
        params = ["-I", os.path.join(paths.PKG_DIR, "main.py")] + list(args)
    sei = _SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = 0x00000040 | 0x00000400                   # SEE_MASK_NOCLOSEPROCESS | SEE_MASK_FLAG_NO_UI
    sei.lpVerb, sei.lpFile, sei.nShow = "runas", exe, 0
    sei.lpParameters = subprocess.list2cmdline(params)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    if not shell32.ShellExecuteExW(ctypes.byref(sei)):
        err = ctypes.get_last_error()
        return False, "Cancelled." if err == 1223 else f"Could not ask for administrator rights (error {err})."
    k32 = ctypes.windll.kernel32
    k32.WaitForSingleObject(sei.hProcess, 60000)
    code = w.DWORD(1)
    k32.GetExitCodeProcess(sei.hProcess, ctypes.byref(code))
    k32.CloseHandle(sei.hProcess)
    if code.value == 0:
        return True, ""
    try:
        with open(os.path.join(STAGE_DIR, "error.txt"), encoding="utf-8") as f:
            return False, f.read().strip()
    except OSError:
        return False, f"The copy as administrator failed (exit code {code.value})."


def install(install_path) -> dict:
    if not bundled():
        return {"ok": False, "message": "This build has no compiled ZScript bridge (RadialMenuBridge.zsc)."}
    dest = zplugs(install_path)
    try:
        stage = _stage()
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "message": f"Could not prepare the plugin files: {e}"}
    try:
        copy_staged(stage, dest)
        return {"ok": True, "elevated": False, "message": "Installed. Restart ZBrush so it loads the plugin."}
    except PermissionError:
        pass
    except OSError as e:
        return {"ok": False, "message": f"Could not copy the plugin: {e}"}
    ok, msg = _run_elevated(["--zscript-copy", stage, dest])
    return {"ok": ok, "elevated": True, "message": "Installed. Restart ZBrush so it loads the plugin." if ok else msg}


def remove(install_path) -> dict:
    dest = zplugs(install_path)
    try:
        remove_from(dest)
        return {"ok": True, "elevated": False, "message": "Removed. Restart ZBrush to unload it."}
    except PermissionError:
        pass
    except OSError as e:
        return {"ok": False, "message": f"Could not remove the plugin: {e}"}
    shutil.rmtree(STAGE_DIR, ignore_errors=True)
    os.makedirs(STAGE_DIR, exist_ok=True)
    ok, msg = _run_elevated(["--zscript-remove", STAGE_DIR, dest])
    return {"ok": ok, "elevated": True, "message": "Removed. Restart ZBrush to unload it." if ok else msg}


def elevated_main(args) -> int:
    """Entry for the elevated copy: --zscript-copy|--zscript-remove <stage> <dest>. Errors go to the staging
    folder, which the caller reads (this process may run as another user, with another LOCALAPPDATA)."""
    try:
        if args[0] == "--zscript-copy":
            copy_staged(args[1], args[2])
        else:
            remove_from(args[2])
        return 0
    except Exception as e:
        try:
            with open(os.path.join(args[1], "error.txt"), "w", encoding="utf-8") as f:
                f.write(f"{type(e).__name__}: {e}")
        except OSError:
            pass
        return 1
