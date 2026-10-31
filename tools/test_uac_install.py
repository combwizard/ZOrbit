"""Tests installing, updating and removing the ZScript plugin (ZBrush 2022-2025) in a ZBrush under Program Files,
where the plain copy is refused and ZOrbit runs its helper as administrator (the UAC prompt).

It needs no real ZBrush. It makes a fake one, "%ProgramFiles%\\ZOrbit UAC test", with an empty ZBrush.exe, the
plugin from before the rename (RadialMenuBridge.zsc) and another plugin (SomeoneElse.zsc) that must survive. Then
it runs the checkout's own zscript_bridge.install() and remove() against it, as Studio does, and checks every file.

Run it from a normal terminal, not as administrator: the test is that the plain copy fails and the helper takes
over. Each step that shows a UAC prompt says first which button to press; a full run has five prompts, seven with
--exe. On a test machine with UAC set to elevate without prompting, no prompt shows at all; add --no-decline
there, because that step needs you to press No.

Run: python tools/test_uac_install.py                    (the whole test)
     python tools/test_uac_install.py --exe PATH         (also the installed build's helper, ZOrbit.exe)
     python tools/test_uac_install.py --no-uac           (only the checks that need no administrator)
     python tools/test_uac_install.py --no-decline       (skip the step where you press No)
     python tools/test_uac_install.py --keep             (leave the fake ZBrush in place afterwards)

Not covered: a standard Windows account, where UAC asks for another account's password and the helper runs as
that account, and a real ZBrush loading the plugin.
"""
import argparse
import ctypes
import ctypes.wintypes as w
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "zorbit"))
import paths                    # noqa: E402
import zscript_bridge as zb     # noqa: E402

TEST_NAME = "ZOrbit UAC test"
MARKER = "zorbit-uac-test.txt"
OTHER = "SomeoneElse.zsc"


def test_root() -> str:
    return os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), TEST_NAME)


# --- the elevated side: make and delete the fake ZBrush ------------------------------------------
def elevated(action, root) -> int:
    if os.path.normcase(os.path.normpath(root)) != os.path.normcase(test_root()):
        return 2                                        # only ever this one folder
    if os.path.isdir(root):
        if not os.path.isfile(os.path.join(root, MARKER)):
            return 3                                    # a folder of that name that this script did not make
        shutil.rmtree(root)
    if action == "--elevated-cleanup":
        return 0
    dest = zb.zplugs(root)
    legacy_data = os.path.join(dest, zb.LEGACY_DATA)
    os.makedirs(legacy_data)
    for p in (os.path.join(root, MARKER), os.path.join(root, "ZBrush.exe")):
        open(p, "wb").close()
    with open(os.path.join(dest, zb.LEGACY_PLUGIN), "wb") as f:
        f.write(b"old plugin")
    for name in (zb.CFG, *zb.SHORTCUTS):
        with open(os.path.join(legacy_data, name), "wb") as f:
            f.write(b"old")
    with open(os.path.join(dest, OTHER), "wb") as f:
        f.write(b"not ours")
    return 0


# --- the normal side ------------------------------------------------------------------------------
def run_as_admin(exe, params) -> tuple[int | None, str]:
    """Runs exe as administrator and waits. (exit code, "") or (None, why it did not run)."""
    sei = zb._SHELLEXECUTEINFOW()
    sei.cbSize = ctypes.sizeof(sei)
    sei.fMask = 0x00000040 | 0x00000400                 # SEE_MASK_NOCLOSEPROCESS | SEE_MASK_FLAG_NO_UI
    sei.lpVerb, sei.lpFile, sei.nShow = "runas", exe, 0
    sei.lpParameters = subprocess.list2cmdline(params)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    if not shell32.ShellExecuteExW(ctypes.byref(sei)):
        err = ctypes.get_last_error()
        return None, "declined at the prompt" if err == 1223 else f"could not start it (error {err})"
    k32 = ctypes.WinDLL("kernel32")
    k32.WaitForSingleObject.argtypes, k32.WaitForSingleObject.restype = [w.HANDLE, w.DWORD], w.DWORD
    k32.GetExitCodeProcess.argtypes = [w.HANDLE, ctypes.POINTER(w.DWORD)]
    k32.CloseHandle.argtypes = [w.HANDLE]
    k32.WaitForSingleObject(sei.hProcess, 0xFFFFFFFF)
    code = w.DWORD(1)
    k32.GetExitCodeProcess(sei.hProcess, ctypes.byref(code))
    k32.CloseHandle(sei.hProcess)
    return code.value, ""


def self_as_admin(action, root) -> tuple[int | None, str]:
    return run_as_admin(sys.executable, ["-I", os.path.abspath(__file__), action, root])


class Results:
    def __init__(self):
        self.failed = 0

    def check(self, ok, what, detail=""):
        print(f"  {'PASS' if ok else 'FAIL'}  {what}" + (f": {detail}" if detail and not ok else ""))
        if not ok:
            self.failed += 1
        return ok


def prompt(button):
    print(f"\n  >> A UAC prompt opens now. Press {button}.")


def first_token(cmd) -> str:
    return cmd[1:cmd.index('"', 1)] if cmd.startswith('"') else cmd.split(" ", 1)[0]


def helper_checks(r: Results):
    """elevated_main() refuses a folder that is not a ZBrush plugin folder. Needs no administrator."""
    print("\nThe helper refuses a wrong target")
    with tempfile.TemporaryDirectory() as tmp:
        stage = os.path.join(tmp, "zscript_stage")
        os.makedirs(stage)
        err = os.path.join(stage, "error.txt")
        no_exe = os.path.join(tmp, "NoZBrush", "ZStartup", "ZPlugs64")
        os.makedirs(no_exe)
        cases = [
            ("not a ZPlugs64 folder", ["--zscript-copy", stage, tmp], "is not a ZBrush ZStartup"),
            ("no ZBrush.exe next to ZStartup", ["--zscript-copy", stage, no_exe], "There is no ZBrush.exe"),
            ("removal from a wrong folder", ["--zscript-remove", stage, tmp], "is not a ZBrush ZStartup"),
            ("wrong arguments", ["--zscript-copy", stage], "Usage:"),
        ]
        for what, args, expect in cases:
            if os.path.exists(err):
                os.remove(err)
            code = zb.elevated_main(args)
            msg = open(err, encoding="utf-8").read() if os.path.exists(err) else ""
            r.check(code == 1 and expect in msg, what, f"exit {code}, error.txt {msg!r}")
        r.check(not os.listdir(no_exe), "nothing written to the refused folder")


def uac_checks(r: Results, root, exe, decline):
    dest = zb.zplugs(root)
    plugin, data = os.path.join(dest, zb.PLUGIN), os.path.join(dest, zb.DATA)
    other = os.path.join(dest, OTHER)

    print(f"\nMake the fake ZBrush in {root}")
    prompt("Yes")
    code, why = self_as_admin("--elevated-setup", root)
    if not r.check(code == 0, "fake ZBrush made", why or f"exit {code}"):
        return
    try:
        with open(os.path.join(dest, "probe.tmp"), "w"):
            pass
        os.remove(os.path.join(dest, "probe.tmp"))
        r.check(False, "a normal user cannot write there", "the folder is writable, so no prompt would be needed")
        return
    except PermissionError:
        r.check(True, "a normal user cannot write there")
    st = zb.status(root)
    r.check(st["installed"] and not st["current"], "Studio sees the old plugin as an update", str(st))

    print("\nUpdate: install over the plugin from before the rename")
    prompt("Yes")
    res = zb.install(root)
    r.check(res.get("ok") and res.get("elevated"), "install went through the helper", str(res))
    st = zb.status(root)
    r.check(st["current"], "plugin, bridge.cfg and shortcuts match this checkout", str(st))
    r.check(not os.path.exists(os.path.join(dest, zb.LEGACY_PLUGIN)) and
            not os.path.exists(os.path.join(dest, zb.LEGACY_DATA)), "the old plugin and its folder are gone")
    r.check(os.path.isfile(other), f"{OTHER} is untouched")
    try:
        lines = open(os.path.join(data, zb.CFG), encoding="mbcs").read().splitlines()
        want = zb.ascii_path(paths.DATA_DIR).rstrip("\\") + "\\"
        r.check(lines[1] == want, "bridge.cfg sends picks to your own data folder", f"{lines[1]!r}, want {want!r}")
    except (OSError, IndexError) as e:
        r.check(False, "bridge.cfg is readable", str(e))

    print("\nRemove")
    prompt("Yes")
    res = zb.remove(root)
    r.check(res.get("ok") and res.get("elevated"), "remove went through the helper", str(res))
    r.check(not os.path.exists(plugin) and not os.path.exists(data), "the plugin and ZOrbitData are gone")
    r.check(os.path.isfile(other), f"{OTHER} is untouched")
    r.check(not zb.status(root)["installed"], "Studio sees no plugin")

    if decline:
        print("\nDeclined: install, but say no")
        prompt("No")
        res = zb.install(root)
        r.check(not res.get("ok") and "declined" in res.get("message", ""), "Studio says it was declined", str(res))
        r.check(not os.path.exists(plugin) and not os.path.exists(data), "nothing was installed")

    if exe:
        print(f"\nThe installed build's helper: {exe}")
        shutil.rmtree(zb.STAGE_DIR, ignore_errors=True)
        os.makedirs(zb.STAGE_DIR)
        prompt("Yes")
        code, why = run_as_admin(exe, ["--zscript-copy", zb.STAGE_DIR, dest])
        err = os.path.join(zb.STAGE_DIR, "error.txt")
        detail = why or (open(err, encoding="utf-8").read() if os.path.exists(err) else f"exit {code}")
        if r.check(code == 0, "--zscript-copy succeeded", detail):
            r.check(os.path.isfile(plugin) and all(os.path.isfile(os.path.join(data, n)) for n in zb.SHORTCUTS),
                    "plugin and shortcuts are there")
            try:
                lines = open(os.path.join(data, zb.CFG), encoding="mbcs").read().splitlines()
                want = zb.ascii_path(paths.DATA_DIR).rstrip("\\") + "\\"
                r.check(lines[1] == want, "bridge.cfg sends picks to your own data folder", repr(lines[1]))
                app = first_token(lines[2])
                r.check(os.path.isfile(app) and os.path.samefile(app, exe), "bridge.cfg starts this ZOrbit.exe",
                        repr(lines[2]))
            except (OSError, IndexError) as e:
                r.check(False, "bridge.cfg is readable", str(e))
        prompt("Yes")
        code, why = run_as_admin(exe, ["--zscript-remove", zb.STAGE_DIR, dest])
        r.check(code == 0 and not os.path.exists(plugin) and not os.path.exists(data),
                "--zscript-remove took it out again", why or f"exit {code}")
        r.check(os.path.isfile(other), f"{OTHER} is untouched")
        shutil.rmtree(zb.STAGE_DIR, ignore_errors=True)


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] in ("--elevated-setup", "--elevated-cleanup"):
        return elevated(sys.argv[1], sys.argv[2])
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--exe", help="an installed ZOrbit.exe whose helper to test as well")
    ap.add_argument("--no-uac", action="store_true", help="only the checks that need no administrator")
    ap.add_argument("--no-decline", action="store_true", help="skip the step where you press No")
    ap.add_argument("--keep", action="store_true", help="leave the fake ZBrush in place afterwards")
    a = ap.parse_args()
    if a.exe and not os.path.isfile(a.exe):
        sys.exit(f"No such file: {a.exe}")
    if not zb.bundled():
        sys.exit(f"No compiled plugin in {paths.ZSCRIPT_DIR}: compile it first (tools/compile-zscript.ps1).")
    if not a.no_uac and ctypes.windll.shell32.IsUserAnAdmin():
        sys.exit("This terminal runs as administrator, so the plain copy would work and the prompt never shows. "
                 "Run it from a normal terminal.")

    r = Results()
    helper_checks(r)
    if not a.no_uac:
        root = test_root()
        try:
            uac_checks(r, root, a.exe, not a.no_decline)
        finally:
            if os.path.isdir(root) and not a.keep:
                print("\nDelete the fake ZBrush")
                prompt("Yes")
                code, why = self_as_admin("--elevated-cleanup", root)
                r.check(code == 0 and not os.path.exists(root), "fake ZBrush deleted", why or f"exit {code}")
    print(f"\n{'All checks passed.' if not r.failed else f'{r.failed} check(s) failed.'}")
    return 1 if r.failed else 0


if __name__ == "__main__":
    sys.exit(main())
