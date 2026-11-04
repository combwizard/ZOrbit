"""The ZScript bridge for ZBrush 2022-2025, which have no Python API: request format and installation.

Files:
  <ZBrush>\\ZStartup\\ZPlugs64\\ZOrbitBridge.zsc        compiled in ZBrush from bridge/zscript/ZOrbitBridge.txt
  <ZBrush>\\ZStartup\\ZPlugs64\\ZOrbitData\\bridge.cfg   written here: where picks arrive, how to start the app
  <ZBrush>\\ZStartup\\ZPlugs64\\ZOrbitData\\*.lnk        shortcuts that start the app and the Studio (see SHORTCUTS)
  <ZBrush>\\ZStartup\\ZPlugs64\\ZOrbitData\\install.txt  "shortcuts: ok", or why they could not be made
  %LOCALAPPDATA%\\ZOrbit\\request.txt                every pick, next to request.json (written by the app)

Before the rename the plugin was RadialMenuBridge.zsc with a RadialMenuData folder. Those count as an installed
plugin that needs an update; installing replaces them and removing removes them too.

ZScript cannot read environment variables or JSON, and its strings stop at 255 characters. So both files hold
one value per line, and paths are absolute, in their 8.3 short form when the long form is not plain ASCII.
request.txt is the magic line, id and label, then per action its kind and arguments: brush, alpha, material or
texture with the name and its file (or - when none is known), press with a path, set with a path and a value,
toggle with a path, file with the path of a button and the file ZBrush is told to use when that button is pressed.

ZBrush 2022-2025 load plugins only from ZStartup\\ZPlugs64 inside the installation, usually under Program
Files. install()/remove() try a plain copy first and fall back to this program run as administrator
(one UAC prompt): ZOrbit.exe --zscript-copy|--zscript-remove <staging folder> <ZPlugs64>. The elevated run
trusts nothing in the staging folder (the user can write there): it checks that <ZPlugs64> is a ZBrush plugin
folder, builds the plugin files itself from this build's own sources and uses the staging folder only to report
an error.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import filecmp
import json
import os
import shutil
import subprocess
import sys
import threading
import time

import installs
import paths

PLUGIN = "ZOrbitBridge.zsc"
SOURCE = "ZOrbitBridge.txt"
DATA = "ZOrbitData"
LEGACY_PLUGIN = "RadialMenuBridge.zsc"  # the same plugin from before the rename
LEGACY_DATA = "RadialMenuData"
CFG = "bridge.cfg"
NOTE = "install.txt"                    # why the shortcuts are missing, when they could not be made
MIN_YEAR = 2022
MAGIC = "ZORBIT 1"
MAX_LINE = 255                          # longest string ZScript reads in one go
ASSET_KINDS = ("brush", "alpha", "material", "texture")     # actions that carry a name and a file
REQUEST_TXT = os.path.join(paths.DATA_DIR, "request.txt")
STAGE_DIR = os.path.join(paths.DATA_DIR, "zscript_stage")
ELEVATED_WAIT = 300                     # seconds the Studio waits for the administrator prompt and the copy
BUSY = {"ok": False, "busy": True, "message": "Another install or removal is still running."}
_busy = threading.Lock()                # one install or removal at a time


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


def ascii_file(p) -> str:
    """ascii_path for a file that may not exist yet (GetShortPathName only knows files that do): the short name of
    its folder plus its own name. p itself when that is still not plain ASCII."""
    p = str(p or "")
    got = ascii_path(p)
    if got.isascii():
        return got
    folder, name = os.path.split(p)
    short = ascii_path(folder)
    return os.path.join(short, name) if folder and short.isascii() and name.isascii() else p


def legacy_path_problem(p):
    """Why ZBrush 2022-2025 cannot be given the file path p, as (kind, what), or None when it can. Their plugin
    reads one ANSI line of at most MAX_LINE bytes. kind "name": the path is not plain ASCII and has no short form;
    "long": it is too long. what completes a sentence that starts "ZBrush 2022-2025 ..."."""
    sent = ascii_file(p)
    if not sent.isascii():
        return "name", "cannot be given a name outside plain ASCII, and the volume has no short name for it"
    size = len(sent.encode("mbcs", errors="replace"))
    if size > MAX_LINE:
        return "long", f"takes a path of at most {MAX_LINE} bytes, and this one is {size}"
    return None


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
        asset = next((k for k in ASSET_KINDS if k in a), None)
        if asset:
            # The button ZBrush gave the item (named after its file, which the app found) before the name in the
            # menu, as zorbit_bridge.py tries them: Alpha:<name> misses an imported alpha whose file is named
            # otherwise, and the plugin would import it again on every pick. The file's own name can't be worked
            # out in ZScript, as the path below may be an 8.3 one.
            lines += [asset, _line(a.get("button") or a[asset]), _line(ascii_path(a.get("file")))]
        elif "filepress" in a:
            lines += ["file", _line(a["filepress"]), _line(ascii_file(a.get("file")))]
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


# The fallback when the bridge key does not reach Apply: ZBrush.exe <this script> hands it to the ZBrush that is
# already open, which presses Apply, so the plugin's own code carries out the pick. The press goes through a
# variable and a routine: ZBrush drops a script given on its command line without a word if it holds
# [IPress, "<literal path>"], and IGetID on a missing item stops it with a box, hence the IExists.
APPLY_SCRIPT = os.path.join(paths.DATA_DIR, "ApplyFallback.txt")
APPLY_TEXT = ('[VarDef, p, ""][RoutineDef, Press, [If, [IExists, #p], [IPress, #p]]]'
              '[VarSet, p, "Zplugin:ZOrbit:Apply"][RoutineCall, Press]')


def apply_script() -> bytes:
    return (APPLY_TEXT + "\r\n").encode("ascii")


def ensure_apply_script(path=None) -> str:
    """The fallback script on disk, written only when it is missing or differs. ZBrush compiles a .txt it is given
    to a .zsc beside it and may run that copy later, so a changed script removes the old .zsc. Returns the path as
    ZBrush is to be told it (the 8.3 name when the real one has spaces or is not plain ASCII, as _command does).
    OSError when it cannot be written."""
    path = path or APPLY_SCRIPT
    want = apply_script()
    try:
        with open(path, "rb") as f:
            if f.read() == want:
                return ascii_path(path, spaces=True)
    except OSError:
        pass
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(want)
    os.replace(tmp, path)
    try:
        os.remove(os.path.splitext(path)[0] + ".zsc")
    except OSError:
        pass
    return ascii_path(path, spaces=True)


def pending_request(path=None) -> int | None:
    """The number of the pick waiting in request.txt: None when there is no file, 0 when the file is not a request
    of ours (no readable number), else the number. OSError when it exists but cannot be read just now."""
    try:
        with open(path or REQUEST_TXT, "rb") as f:
            head = f.read(256).decode("ascii", errors="replace").splitlines()
    except FileNotFoundError:
        return None
    return int(head[1]) if len(head) > 1 and head[0] == MAGIC and head[1].isdigit() else 0


def _command(argv) -> str:
    """A command line for ZScript's ShellExecute, without quotes where 8.3 names make that possible."""
    parts = []
    for a in argv:
        a = ascii_path(a, spaces=True) if os.path.exists(a) else a
        parts.append(f'"{a}"' if " " in a else a)
    return " ".join(parts)


def cfg_lines(data_dir=None) -> list[str]:
    """bridge.cfg: magic, the folder picks arrive in (with a trailing backslash), the command lines that
    start the app and the Studio, and whether the plugin starts the app when ZBrush loads it (1/0).
    data_dir: the user's data folder when this runs elevated as another account (whose own LOCALAPPDATA
    would be the wrong place for picks to arrive)."""
    if data_dir is None:
        data_dir = paths.DATA_DIR
        os.makedirs(data_dir, exist_ok=True)
    cmds = paths.launch_commands()
    return [MAGIC, ascii_path(data_dir).rstrip("\\") + "\\", _command(cmds["app"]), _command(cmds["studio"]),
            "1"]


# --- installation --------------------------------------------------------------------------------
def bundled() -> str | None:
    """The compiled plugin shipped with this build, or None (it has to be compiled in ZBrush first)."""
    p = os.path.join(paths.ZSCRIPT_DIR, PLUGIN)
    return p if os.path.isfile(p) else None


def zplugs(install_path) -> str:
    return os.path.join(str(install_path), "ZStartup", "ZPlugs64")


def status(install_path) -> dict:
    """installed: the plugin (or the one from before the rename) is in this ZBrush. current: it, its bridge.cfg
    and its shortcuts match this build, and the old one is gone."""
    dest = zplugs(install_path)
    plug, cfg = os.path.join(dest, PLUGIN), os.path.join(dest, DATA, CFG)
    legacy = os.path.isfile(os.path.join(dest, LEGACY_PLUGIN))
    installed = os.path.isfile(plug) or legacy
    current = False
    if installed and not legacy and bundled():
        try:
            with open(cfg, encoding="mbcs", errors="replace") as f:
                cfg_ok = f.read().splitlines() == cfg_lines()
            links_ok = shortcuts_skipped(dest) is not None or all(
                os.path.isfile(os.path.join(dest, DATA, n)) for n in SHORTCUTS)
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


def _reason(e) -> str:
    """One short line saying why the shortcut step failed."""
    text = ""
    if isinstance(e, subprocess.CalledProcessError):
        err = e.stderr or b""
        text = err.decode("utf-8", "replace") if isinstance(err, bytes) else str(err)
    text = " ".join(text.split()) or " ".join(f"{type(e).__name__}: {e}".split())
    return text[:200]


def shortcuts_skipped(dest) -> str | None:
    """The reason in ZOrbitData/install.txt (under dest) when the shortcuts could not be made, else None."""
    try:
        with open(os.path.join(dest, DATA, NOTE), encoding="utf-8", errors="replace") as f:
            for line in f.read().splitlines():
                if line.startswith("shortcuts:"):
                    why = line[len("shortcuts:"):].strip()
                    return None if why in ("", "ok") else why
    except OSError:
        pass
    return None


def build_plugin_files(folder, user_data=None) -> str | None:
    """Writes the plugin and its data folder (bridge.cfg, shortcuts) into folder, from this build's own sources:
    the bundled .zsc, cfg_lines() and launch_commands(). The data folder goes first, the plugin last. The
    shortcuts are optional (PowerShell may be locked down): when they cannot be made the plugin falls back to the
    command lines in bridge.cfg, install.txt records why, and that reason is returned (None when all is well)."""
    src = bundled()
    if not src:
        raise FileNotFoundError(f"This build has no compiled ZScript bridge ({PLUGIN}).")
    data_dir = os.path.join(folder, DATA)
    os.makedirs(data_dir, exist_ok=True)
    data, _ = encode(cfg_lines(user_data))           # user_data: the account's data folder when run elevated
    with open(os.path.join(data_dir, CFG), "wb") as f:
        f.write(data)
    cmds = paths.launch_commands()
    skipped = None
    try:
        for name, which in SHORTCUTS.items():
            _make_shortcut(os.path.join(data_dir, name), cmds[which])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
        skipped = _reason(e)
        for name in SHORTCUTS:
            try:
                os.remove(os.path.join(data_dir, name))
            except OSError:
                pass
    with open(os.path.join(data_dir, NOTE), "w", encoding="utf-8") as f:
        f.write(f"shortcuts: {skipped or 'ok'}\n")
    shutil.copyfile(src, os.path.join(folder, PLUGIN))
    return skipped


def cfg_problem(data_dir=None) -> str | None:
    """Why bridge.cfg cannot be read by the plugin from this account, or None. ZScript reads the file in the
    ANSI code page with lines of at most 255 bytes, so a data folder that is neither plain ASCII nor available
    as an 8.3 short name cannot be passed on."""
    lines = cfg_lines(data_dir)
    folder = lines[1] if len(lines) > 1 else ""
    if encode([folder])[1]:
        if len(folder.encode("mbcs", errors="replace")) > MAX_LINE:
            return (f"The ZBrush 2022 to 2025 plugin cannot find ZOrbit's data folder from this account: the path "
                    f"{folder} is longer than {MAX_LINE} characters. Move the data folder somewhere shorter, "
                    f"then try again.")
        return (f"The ZBrush 2022 to 2025 plugin cannot find ZOrbit's data folder from this account: the path "
                f"{folder} has characters outside the Windows code page and 8.3 short names are off. Move the "
                f"data folder or turn on 8.3 names (fsutil 8dot3name set 0), then try again.")
    for label, line in zip(("start the app", "open the Studio"), lines[2:4]):
        if encode([line])[1]:
            return (f"The ZBrush 2022 to 2025 plugin cannot use the command that has to {label}: it has characters "
                    f"outside the Windows code page, or is longer than {MAX_LINE} characters, and has no 8.3 short "
                    f"name. Install ZOrbit in a plain path, then try again.")
    return None


def _installed_message(dest) -> str:
    why = shortcuts_skipped(dest)
    if why:
        return ("Installed without the start shortcuts (PowerShell is restricted here): the plugin starts ZOrbit "
                "the slower way. Restart ZBrush so it loads the plugin.")
    return "Installed. Restart ZBrush so it loads the plugin."


def _stage() -> str:
    shutil.rmtree(STAGE_DIR, ignore_errors=True)
    os.makedirs(STAGE_DIR)
    build_plugin_files(STAGE_DIR)
    return STAGE_DIR


def copy_staged(stage, dest) -> None:
    """Puts the staged plugin and its data folder into ZPlugs64 (the plain copy; never run elevated)."""
    os.makedirs(os.path.join(dest, DATA), exist_ok=True)
    shutil.copyfile(os.path.join(stage, PLUGIN), os.path.join(dest, PLUGIN))
    for name in (CFG, NOTE, *SHORTCUTS):
        src = os.path.join(stage, DATA, name)
        if os.path.isfile(src):                          # the shortcuts are missing when they could not be made
            shutil.copyfile(src, os.path.join(dest, DATA, name))
        elif os.path.isfile(os.path.join(dest, DATA, name)):
            os.remove(os.path.join(dest, DATA, name))    # not left over from an earlier install
    remove_from(dest, legacy_only=True)


def remove_from(dest, legacy_only=False) -> None:
    """Deletes only what build_plugin_files() puts there, and the same files from before the rename."""
    names = [(LEGACY_PLUGIN, LEGACY_DATA)] + ([] if legacy_only else [(PLUGIN, DATA)])
    for plugin, data in names:
        for p in (os.path.join(dest, plugin), *(os.path.join(dest, data, n) for n in (CFG, NOTE, *SHORTCUTS))):
            if os.path.exists(p):
                os.remove(p)
        try:
            os.rmdir(os.path.join(dest, data))
        except OSError:
            pass                        # not empty (or gone): leave it


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("fMask", w.ULONG), ("hwnd", w.HWND), ("lpVerb", w.LPCWSTR),
                ("lpFile", w.LPCWSTR), ("lpParameters", w.LPCWSTR), ("lpDirectory", w.LPCWSTR), ("nShow", ctypes.c_int),
                ("hInstApp", w.HINSTANCE), ("lpIDList", ctypes.c_void_p), ("lpClass", w.LPCWSTR),
                ("hkeyClass", w.HKEY), ("dwHotKey", w.DWORD), ("hIconOrMonitor", w.HANDLE), ("hProcess", w.HANDLE)]


def _run_elevated(args) -> tuple[bool, str]:
    """Runs this program with args as administrator and waits up to ELEVATED_WAIT seconds. (ok, message)."""
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
        if err == 1223:                                   # ERROR_CANCELLED
            return False, "Administrator approval was declined. Nothing was changed."
        return False, f"Could not ask for administrator rights (error {err})."
    k32 = ctypes.WinDLL("kernel32")
    k32.WaitForSingleObject.argtypes, k32.WaitForSingleObject.restype = [w.HANDLE, w.DWORD], w.DWORD
    k32.GetExitCodeProcess.argtypes, k32.GetExitCodeProcess.restype = [w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL
    k32.CloseHandle.argtypes = [w.HANDLE]
    deadline = time.monotonic() + ELEVATED_WAIT
    waited = 0x102                                        # WAIT_TIMEOUT
    while waited == 0x102 and time.monotonic() < deadline:
        waited = k32.WaitForSingleObject(sei.hProcess, 500)
    if waited == 0x102:
        k32.CloseHandle(sei.hProcess)                     # leave the process alone: it may still finish
        return False, "The administrator prompt was not answered within five minutes. Nothing was changed."
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
    if not _busy.acquire(blocking=False):
        return dict(BUSY)
    try:
        return _install(install_path)
    finally:
        _busy.release()


def _install(install_path) -> dict:
    if not bundled():
        return {"ok": False, "message": "This build has no compiled ZScript bridge (ZOrbitBridge.zsc)."}
    e = installs.entry(install_path)
    if e and not e["supported"]:
        return {"ok": False, "message": f"ZBrush {e['year']} is not supported (2022 or newer)."}
    dest = zplugs(install_path)
    try:
        problem = cfg_problem()
    except OSError as err:
        return {"ok": False, "message": f"Could not prepare the plugin files: {err}"}
    if problem:
        return {"ok": False, "message": problem}
    try:
        stage = _stage()
    except (OSError, subprocess.SubprocessError) as e:
        return {"ok": False, "message": f"Could not prepare the plugin files: {e}"}
    try:
        copy_staged(stage, dest)
        return {"ok": True, "elevated": False, "message": _installed_message(dest)}
    except PermissionError:
        pass
    except OSError as e:
        return {"ok": False, "message": f"Could not copy the plugin: {e}"}
    # The helper builds the files itself; the staged copy is not trusted, so it does not stay around.
    shutil.rmtree(STAGE_DIR, ignore_errors=True)
    os.makedirs(STAGE_DIR, exist_ok=True)
    ok, msg = _run_elevated(["--zscript-copy", STAGE_DIR, dest])
    return {"ok": ok, "elevated": True, "message": _installed_message(dest) if ok else msg}


def remove(install_path) -> dict:
    if not _busy.acquire(blocking=False):
        return dict(BUSY)
    try:
        return _remove(install_path)
    finally:
        _busy.release()


def _remove(install_path) -> dict:
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


def installed_in() -> list[str]:
    """The ZPlugs64 folders that hold the plugin (or the one from before the rename), in every ZBrush this PC
    knows about: the installations Windows lists, the ones ZBrush recorded and the ones added by hand in Studio.
    The uninstaller asks this instead of guessing folders under Program Files."""
    folders = [i["path"] for i in installs.find_installs()]
    try:
        with open(os.path.join(paths.CONFIG_DIR, "studio.json"), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            folders += [p for p in data.get("zbrush_folders", []) if isinstance(p, str)]
    except (OSError, ValueError):
        pass
    out, seen = [], set()
    for p in folders:
        dest = os.path.normpath(zplugs(p))
        key = os.path.normcase(dest)
        if key in seen:
            continue
        seen.add(key)
        if os.path.isfile(os.path.join(dest, PLUGIN)) or os.path.isfile(os.path.join(dest, LEGACY_PLUGIN)):
            out.append(dest)
    return out


def list_main(args) -> int:
    """Entry for ZOrbit.exe --zscript-list <file>: writes installed_in() to the file, one folder per line, as
    UTF-8 with a byte order mark (Inno Setup's LoadStringsFromFile reads that). Reads only; exit code 1 when the
    file cannot be written."""
    if len(args) != 2 or args[0] != "--zscript-list":
        return 1
    try:
        with open(args[1], "w", encoding="utf-8-sig", newline="\r\n") as f:
            for dest in installed_in():
                f.write(dest + "\n")
        return 0
    except OSError:
        return 1


def check_dest(dest) -> str | None:
    """Why dest is not a ZBrush plugin folder (<ZBrush>\\ZStartup\\ZPlugs64, with ZBrush.exe in <ZBrush>), or None."""
    d = os.path.normpath(str(dest))
    parts = d.replace("/", "\\").split("\\")
    if not os.path.isabs(d) or len(parts) < 3 or [x.lower() for x in parts[-2:]] != ["zstartup", "zplugs64"]:
        return f"{dest} is not a ZBrush ZStartup\\ZPlugs64 folder."
    if not os.path.isfile(os.path.join(os.path.dirname(os.path.dirname(d)), "ZBrush.exe")):
        return f"There is no ZBrush.exe next to the ZStartup folder of {dest}."
    return None


def elevated_main(args) -> int:
    """Entry for the elevated run: --zscript-copy|--zscript-remove <stage> <dest>. It trusts neither argument:
    dest must be a ZBrush plugin folder, and the files are built here from this build's own sources, never read
    from the stage (the user can write there). The stage only receives error.txt, which the caller reads (this
    process may run as another user, with another LOCALAPPDATA)."""
    stage = args[1] if len(args) > 1 else ""
    try:
        if len(args) != 3 or args[0] not in ("--zscript-copy", "--zscript-remove"):
            raise ValueError("Usage: --zscript-copy|--zscript-remove <stage> <dest>")
        problem = check_dest(args[2])
        if problem:
            raise ValueError(problem)
        dest = os.path.normpath(args[2])
        if args[0] == "--zscript-copy":
            # The stage sits in the user's data folder (<LOCALAPPDATA>\ZOrbit\zscript_stage), so its parent
            # is where picks must arrive even when UAC ran this as another account.
            st = os.path.normpath(stage)
            user_data = os.path.dirname(st) if os.path.basename(st).lower() == "zscript_stage" and os.path.isdir(st) else None
            problem = cfg_problem(user_data)
            if problem:
                raise ValueError(problem)
            build_plugin_files(dest, user_data)
            remove_from(dest, legacy_only=True)
        else:
            remove_from(dest)
        return 0
    except Exception as e:
        msg = str(e) if isinstance(e, ValueError) else f"{type(e).__name__}: {e}"
        try:
            if os.path.basename(os.path.normpath(stage)).lower() == "zscript_stage" and os.path.isdir(stage):
                with open(os.path.join(stage, "error.txt"), "w", encoding="utf-8") as f:
                    f.write(msg)
        except OSError:
            pass
        return 1
