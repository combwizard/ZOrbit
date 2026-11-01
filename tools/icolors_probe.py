"""Not shipped: which bytes of a saved ZBrush UI colours file (.cfg) belong to which Preferences > Icolors patch.

Found with it (ZBrush 2022 and 2026): each patch is one float32 = R + G/256 + B/65536, the colours follow the chunk
tag 03 80 18 04 (2 bytes, a uint32 length, 10 float32 shading values, a uint32 count, then one colour per patch), and
CustomUserInterface20xx.cfg holds the scheme in use. zorbit/zbrush_colors.py reads it for the Match ZBrush theme.

Three steps. Each writes a ZScript for ZBrush, or reads what one wrote, in OUT (%LOCALAPPDATA%/ZOrbit/icolors).
Each script gets a new name (IcolorsList_<time>.txt), so a compiled copy from an earlier run is never the one used.
A script loaded by hand starts with a note to click, so it is plain that it runs.

Traps, found the hard way:
  * A script given on ZBrush's command line is dropped without a word if it holds [IPress, "<literal path>"]; every
    press goes through a routine with the path in a variable.
  * IGetID stops the script with a box on an item that does not exist, so every lookup checks IExists first.
  * Save Ui Colors puts up a "Configuration File" box after each save. Its one button has id 2, not IDOK.
  * A ZBrush started while the last one is still closing drops its script, and one ended by force can stop at
    start-up; auto closes ZBrush only the normal way and waits until it has gone.

  python tools/icolors_probe.py list
      Writes IcolorsList_<time>.txt. In ZBrush: Zscript > Load, pick it; it runs at once. It changes nothing: it
      records every interface item near Preferences > Icolors, and which guessed patch names exist, in
      icolors_items.txt.

  python tools/icolors_probe.py run
      Reads icolors_items.txt, writes IcolorsProbe_<time>.txt. Load it the same way; it runs at once. It
      saves the current colours (base.cfg, twice, to see which bytes change on their own), then for each patch: sets
      it to a marker colour (red = the patch number, green 165, blue 90), saves the colours as pNN.cfg, and loads
      base.cfg again. The main colour is put back at the end. Do not press Store Config while it runs.

  python tools/icolors_probe.py diff
      Compares each pNN.cfg with base.cfg, prints the bytes each patch changed and how the marker is stored there
      (bytes RGB or BGR, or float32), and writes icolors_map.json.

  python tools/icolors_probe.py auto [--year=2026]
      All three with no clicks, the way tools/compile-zscript.ps1 compiles the bridge: ZBrush runs a ZScript given
      on its command line. It is started with the list script and closed, then with the probe and closed, so
      nothing it changes is stored. Close ZBrush first: only one ZBrush runs at a time.
"""
import json
import os
import re
import struct
import sys
import time


def _script_path(stem: str) -> str:
    """A new name per run (see the module docstring), the old scripts of that step removed."""
    for old in os.listdir(OUT):
        if re.fullmatch(stem + r"(_\d+)?\.(txt|zsc)", old):
            try:
                os.remove(os.path.join(OUT, old))
            except OSError:
                pass                                 # ZBrush may hold it open; a stale copy does no harm
    return os.path.join(OUT, f"{stem}_{time.strftime('%H%M%S')}.txt")

OUT = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "ZOrbit", "icolors")
G, B = 165, 90                                   # the marker's green and blue; red is the patch number
CALIBRATION = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255), (0, 0, 0), (128, 128, 128), (64, 64, 64),
               (200, 200, 200), (64, 128, 192), (1, 165, 90)]
SAVE_RE = re.compile(r"save\s*ui", re.I)
LOAD_RE = re.compile(r"load\s*ui", re.I)
# Not colour patches: buttons and sliders of the Icolors subpalette that must not be pressed in the probe.
NOT_PATCH = re.compile(r"save|load|default|reset|opacity|intensity|blend|contrast|saturation|brightness|curve|\bui\b",
                       re.I)
# Labels from Maxon's Icolors reference and an old forum post; the dry pass says which exist.
GUESSES = (["Bt%d" % i for i in range(1, 5)] + ["Sw%d" % i for i in range(1, 5)] + ["Icn%d" % i for i in range(1, 5)]
           + ["Sl%d" % i for i in range(1, 5)]
           + ["K1", "K2", "SliderSlit", "Text1", "Text2", "Numbers", "Menu1", "Menu2", "Title1", "Title2",
              "Palette1", "Palette2", "SubPalette", "Hilite", "Border", "Border2", "Main", "Main2",
              "ZScriptButtonColor", "ZScriptSwitchColor", "TextColor", "Save Ui Colors", "Load Ui Colors",
              "Default", "Default Colors"])
BASE_CANDIDATES = ("Preferences:Icolors", "Preferences:Icolors:Save Ui Colors", "Preferences:Icolors:Load Ui Colors",
                   "Preferences:Icolors:Default")


def zpath(p: str) -> str:
    """A path as ZScript takes it: forward slashes, under its 255-character string limit."""
    p = p.replace(os.sep, "/")
    if len(p) > 200:
        sys.exit(f"path too long for ZScript: {p}")
    return p


WRITER = """
[VarDef, zpOff, 0]
[VarDef, zpLine, ""]
// Appends zpLine and a newline to the memory block ZPMem.
[RoutineDef, ZP_Line,
	[MemWriteString, ZPMem, #zpLine, zpOff, 0]
	[VarSet, zpOff, zpOff + [StrLength, #zpLine]]
	[MemWrite, ZPMem, 10, 2, zpOff]
	[VarSet, zpOff, zpOff + 1]
]
[RoutineDef, ZP_Begin,
	[If, [MemGetSize, ZPMem], [MemDelete, ZPMem]]
	[MemCreate, ZPMem, 131072, 0]
	[VarSet, zpOff, 0]
]
"""


def _write_script(stem, lines, notes):
    """Writes a ZScript; without notes (the unattended run) every [Note] is left out, since each waits for a click."""
    if not notes:
        lines = [ln for ln in lines if "[Note," not in ln]
    script = _script_path(stem)
    with open(script, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    return script


def cmd_list(notes=True):
    os.makedirs(OUT, exist_ok=True)
    out = zpath(os.path.join(OUT, "icolors_items.txt"))
    lines = ["// ZOrbit spike: lists the items of Preferences > Icolors. Changes nothing. (tools/icolors_probe.py)",
             "[IConfig, 2022]", "[VarDef, zpBase, 0]", "[VarDef, zpId, 0]", "[VarDef, zpN, 0]", '[VarDef, zpT, ""]',
             WRITER,
             "// Runs as soon as it is loaded (no button).",
             '[Note, "ZOrbit: listing the Icolors items. This changes nothing. Click to go on."]',
             "\t[RoutineCall, ZP_Begin]"]
    for cand in BASE_CANDIDATES:                     # the first of these with an id is where the scan starts
        lines += [f'\t[VarSet, zpId, 0][If, [IExists, "{cand}"], [VarSet, zpId, [IGetID, "{cand}"]]]',   # IGetID stops on a missing item
                  f'\t[VarSet, zpLine, [StrMerge, "id ", zpId, " {cand}"]]', "\t[RoutineCall, ZP_Line]",
                  "\t[If, (zpBase == 0) && (zpId > 0), [VarSet, zpBase, zpId]]"]
    for name in GUESSES:
        path = f"Preferences:Icolors:{name}"
        lines += [f'\t[VarSet, zpLine, [StrMerge, "exists ", [IExists, "{path}"], " {path}"]]', "\t[RoutineCall, ZP_Line]"]
    lines += ["\t[If, zpBase > 0,",
              "\t\t[VarSet, zpN, 0]",
              "\t\t[Loop, 400,",
              "\t\t\t[VarSet, zpId, zpBase - 100 + zpN]",
              '\t\t\t[VarSet, zpT, ""]',
              "\t\t\t[If, [IExists, zpId], [VarSet, zpT, [IGetTitle, zpId, 1]]]",
              "\t\t\t[If, [StrLength, #zpT] > 0,",
              '\t\t\t\t[VarSet, zpLine, [StrMerge, "item ", zpId, " ", #zpT]]',
              "\t\t\t\t[RoutineCall, ZP_Line]",
              "\t\t\t]",
              "\t\t\t[VarSet, zpN, zpN + 1]",
              "\t\t]",
              "\t]",
              f'\t[MemSaveToFile, ZPMem, "{out}", 1]',
              "\t[MemDelete, ZPMem]",
              f'\t[Note, "ZOrbit: the Icolors items are in {out}"]']
    script = _write_script("IcolorsList", lines, notes)
    print(f"Wrote {script}")
    if notes:
        print("In ZBrush: Zscript > Load, pick it. It runs at once.\nThen run: python tools/icolors_probe.py run")
    return script


def _items():
    """(existing paths from the guesses, scanned items as {id: title}) from icolors_items.txt."""
    path = os.path.join(OUT, "icolors_items.txt")
    if not os.path.isfile(path):
        sys.exit(f"{path} is missing: run the list step in ZBrush first")
    with open(path, "rb") as f:
        text = f.read().split(b"\0")[0].decode("latin-1")
    exists, items = [], {}
    for line in text.splitlines():
        m = re.match(r"exists\s+([\d.]+)\s+(.*)$", line)
        if m and float(m.group(1)) > 0:
            exists.append(m.group(2).strip())
        m = re.match(r"item\s+([\d.]+)\s+(.*)$", line)
        if m:
            items[int(float(m.group(1)))] = m.group(2).strip()
    return exists, items


def cmd_run(notes=True):
    exists, items = _items()
    icolors = [t for t in items.values() if t.lower().startswith("preferences:icolors:")]
    pool = list(dict.fromkeys(icolors + exists))     # the scan's full paths first, then any guess it missed
    save = next((p for p in pool if SAVE_RE.search(p)), None)
    load = next((p for p in pool if LOAD_RE.search(p)), None)
    if not save or not load:
        sys.exit("Save Ui Colors or Load Ui Colors was not found in the list; look at icolors_items.txt")
    patches = [p for p in pool if not NOT_PATCH.search(p.split(":")[-1])]
    if not patches:
        sys.exit("no colour patches in the list; look at icolors_items.txt")
    if len(patches) > 250:
        sys.exit(f"{len(patches)} patches is more than the red channel can number")
    d = zpath(OUT + os.sep)
    # Every press goes through ZP_Press with the path in a variable: a script with [IPress, "<literal path>"] is
    # dropped without a word when ZBrush gets it on its command line.
    press = lambda path: f'[VarSet, zpP, "{path}"][RoutineCall, ZP_Press]'      # noqa: E731
    lines = ["// ZOrbit spike: sets each Icolors patch to a marker colour and saves the UI colours after each.",
             "// The colours are loaded back from base.cfg after every save, and the main colour at the end.",
             "[IConfig, 2022]", "[VarDef, zpR, -1]", "[VarDef, zpG, -1]", "[VarDef, zpB, -1]", '[VarDef, zpP, ""]',
             WRITER,
             "[RoutineDef, ZP_Press,", "\t[If, [IExists, #zpP], [IPress, #zpP]]", "]",
             "// Runs as soon as it is loaded (no button).",
             f'[Note, "ZOrbit: {len(patches)} Icolors patches, one at a time. The colours flicker and come back. '
             'Do not press Store Config. Click to start."]',
             '\t[If, [IExists, "Color:R"], [VarSet, zpR, [IGet, "Color:R"]]]',
             '\t[If, [IExists, "Color:G"], [VarSet, zpG, [IGet, "Color:G"]]]',
             '\t[If, [IExists, "Color:B"], [VarSet, zpB, [IGet, "Color:B"]]]',
             f'\t[FileNameSetNext, "{d}base.cfg"]{press(save)}',
             f'\t[FileNameSetNext, "{d}base2.cfg"]{press(save)}']
    index = {}
    for n, path in enumerate(patches, start=1):
        name = f"p{n:03d}.cfg"
        index[name] = {"path": path, "marker": [n, G, B]}
        lines += [f'\t[IColorSet, {n}, {G}, {B}]{press(path)}',
                  f'\t[FileNameSetNext, "{d}{name}"]{press(save)}',
                  f'\t[FileNameSetNext, "{d}base.cfg"]{press(load)}']
    cal_patch = next((p for p in patches if p.endswith(":Bt1")), patches[0])
    calibration = {}
    for r, g, b in CALIBRATION:                     # one patch in known colours, to read how a colour is packed
        name = f"cal_{r:02x}{g:02x}{b:02x}.cfg"
        calibration[name] = [r, g, b]
        lines += [f'\t[IColorSet, {r}, {g}, {b}]{press(cal_patch)}',
                  f'\t[FileNameSetNext, "{d}{name}"]{press(save)}',
                  f'\t[FileNameSetNext, "{d}base.cfg"]{press(load)}']
    lines += ["\t[If, zpR >= 0, [IColorSet, zpR, zpG, zpB]]",
              "\t[RoutineCall, ZP_Begin]",
              '\t[VarSet, zpLine, "done"]', "\t[RoutineCall, ZP_Line]",
              f'\t[MemSaveToFile, ZPMem, "{d}done.txt", 1]', "\t[MemDelete, ZPMem]",
              f'\t[Note, "ZOrbit: {len(patches)} patches saved. Run: python tools/icolors_probe.py diff"]']
    for old in os.listdir(OUT):                      # a previous run's files would be read as this one's
        if re.fullmatch(r"(p\d{3}|cal_[0-9a-f]{6}|base2?|p_bt1)\.cfg|done\.txt|step\.txt", old):
            os.remove(os.path.join(OUT, old))
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"save": save, "load": load, "files": index, "calibration_patch": cal_patch,
                   "calibration": calibration}, f, indent=1)
    script = _write_script("IcolorsProbe", lines, notes)
    print(f"{len(patches)} patches, save button {save!r}, load button {load!r}:")
    for n, p in enumerate(patches, start=1):
        print(f"  {n:3d}  {p}")
    print(f"Wrote {script}")
    if notes:
        print("In ZBrush: Zscript > Load, pick it. It runs at once.\nThen run: python tools/icolors_probe.py diff")
    return script


def _zbrush_exe(year):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "zorbit"))
    import installs
    found = next((i["path"] for i in installs.find_installs() if i["year"] == year), None)
    exe = found and os.path.join(found, "ZBrush.exe")
    if not exe or not os.path.isfile(exe):
        sys.exit(f"ZBrush {year} is not installed")
    return exe


def _zbrush_pids():
    import subprocess
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ZBrush.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return [int(row.split('","')[1]) for row in out.splitlines() if row.startswith('"ZBrush.exe"')]


SAVED_BOX = "Configuration File"
HEADER = 16          # the first bytes: byte 8 changes with any content (a checksum, it seems), so they are skipped


def _boxes(pid):
    """(hwnd, title) of every visible dialog box of the process."""
    import ctypes
    import ctypes.wintypes as w
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found = []

    def cb(h, _):
        p = w.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and user32.IsWindowVisible(h):
            cls, title = ctypes.create_unicode_buffer(64), ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(h, cls, 64)
            user32.GetWindowTextW(h, title, 128)
            if cls.value == "#32770":
                found.append((h, title.value))
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(cb), 0)
    return found


def _click_only_button(h):
    """Presses a message box's one button. Its id is 2, not IDOK, so WM_COMMAND IDOK does nothing."""
    import ctypes
    import ctypes.wintypes as w
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowExW.restype = w.HWND
    btn = user32.FindWindowExW(h, None, "Button", None)
    user32.PostMessageW(h, 0x0111, user32.GetDlgCtrlID(btn) if btn else 2, btn or 0)     # WM_COMMAND


def _run_in_zbrush(exe, script, wait_for, timeout=240):
    """As tools/compile-zscript.ps1 does: ZBrush runs a ZScript given on its command line. Waits until wait_for
    exists and has stopped growing, then closes this ZBrush (nothing was stored, so its colours are not kept).
    Without the file in time, ZBrush is left open so a script error can be read there."""
    import subprocess
    t0 = time.time()
    while _zbrush_pids() and time.time() - t0 < 30:   # a ZBrush started while the last one is still closing drops its script
        time.sleep(1)
    time.sleep(3)
    print(f"Running {os.path.basename(script)} in {exe} ...")
    proc = subprocess.Popen([exe, script], cwd=os.path.dirname(exe))
    t0, size, oks, last = time.time(), -1, 0, time.time()
    while time.time() - last < timeout and proc.poll() is None:
        time.sleep(0.25)
        for h, title in _boxes(proc.pid):
            if title == SAVED_BOX:                    # "UI configuration-file has been saved successfully", after each save
                _click_only_button(h)
                oks, last = oks + 1, time.time()       # progress: the timeout counts from the last save
            else:
                sys.exit(f"ZBrush shows a box titled {title!r}; it is left open to read. Close ZBrush to go on.")
        if os.path.isfile(wait_for):
            now = os.path.getsize(wait_for)
            if now > 0 and now == size:
                break
            size = now
    if not os.path.isfile(wait_for):
        sys.exit("ZBrush quit without running the script" if proc.poll() is not None else
                 f"no {os.path.basename(wait_for)} {timeout} s after the last save ({oks} saves); ZBrush is left open")
    if oks:
        print(f"  {oks} saves")
    print(f"  done in {time.time() - t0:.0f} s; closing ZBrush")
    # Only ever the normal close: a ZBrush ended by force asks about recovering files at its next start, and then
    # the script given on its command line never runs.
    subprocess.run(["taskkill", "/PID", str(proc.pid)], capture_output=True)
    t1 = time.time()
    while _zbrush_pids() and time.time() - t1 < 45:
        time.sleep(1)
    if _zbrush_pids():
        sys.exit("ZBrush did not close by itself (a prompt?). Close it, then run again with --keep-list.")


def cmd_auto():
    """list, run and diff with no clicks: ZBrush is started twice with a script and closed after each."""
    year = int(next((a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("--year=")), 2026))
    exe = _zbrush_exe(year)
    if _zbrush_pids():
        sys.exit("ZBrush is running. Close it first: only one ZBrush runs at a time.")
    os.makedirs(OUT, exist_ok=True)
    items = os.path.join(OUT, "icolors_items.txt")
    if "--keep-list" not in sys.argv or not os.path.isfile(items):     # --keep-list: the list from last time
        if os.path.isfile(items):
            os.remove(items)
        _run_in_zbrush(exe, cmd_list(notes=False), items)
    script = cmd_run(notes=False)
    _run_in_zbrush(exe, script, os.path.join(OUT, "done.txt"))
    cmd_diff()


def _marker_at(data: bytes, off: int, rgb):
    """How the marker sits around a changed byte: 'RGB', 'BGR', 'float RGB' or 'float BGR', and where it starts."""
    r, g, b = rgb
    for lo in range(max(0, off - 12), off + 1):
        chunk = data[lo:lo + 3]
        if chunk == bytes((r, g, b)):
            return "RGB bytes", lo
        if chunk == bytes((b, g, r)):
            return "BGR bytes", lo
        if lo + 12 <= len(data):
            vals = struct.unpack_from("<3f", data, lo)
            for order, want in (("float RGB", (r, g, b)), ("float BGR", (b, g, r))):
                if all(abs(v - w) < 0.6 or abs(v * 255 - w) < 0.6 for v, w in zip(vals, want)):
                    return order, lo
    return None, None


def cmd_diff():
    with open(os.path.join(OUT, "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    read = lambda n: open(os.path.join(OUT, n), "rb").read()      # noqa: E731
    base = read("base.cfg")
    noise = set()
    if os.path.isfile(os.path.join(OUT, "base2.cfg")):
        base2 = read("base2.cfg")
        noise = {i for i in range(min(len(base), len(base2))) if base[i] != base2[i]}
    print(f"base.cfg: {len(base)} bytes, header {base[:8].hex(' ')}; {len(noise)} bytes change between two saves")
    out = {}
    for name, info in index["files"].items():
        p = os.path.join(OUT, name)
        if not os.path.isfile(p):
            print(f"{name}  {info['path']}: not saved")
            continue
        data = read(name)
        if len(data) != len(base):
            print(f"{name}  {info['path']}: size {len(data)} differs from the base ({len(base)})")
        changed = [i for i in range(HEADER, min(len(data), len(base))) if data[i] != base[i] and i not in noise]
        if not changed:
            print(f"{info['path']:40s} no change (not a colour patch, or the press did not take)")
            out[info["path"]] = None
            continue
        kind, start = _marker_at(data, changed[0], info["marker"])
        words = sorted({i - i % 4 for i in changed})
        shown = "; ".join(f"{o:#06x} {base[o:o + 4].hex(' ')} -> {data[o:o + 4].hex(' ')}" for o in words[:4])
        print(f"{info['path']:40s} {shown}" + (f" (+{len(words) - 4} more)" if len(words) > 4 else "")
              + (f"  marker {kind} at {start:#06x}" if kind else ""))
        out[info["path"]] = {"words": words, "base": [base[o:o + 4].hex() for o in words],
                             "marked": [data[o:o + 4].hex() for o in words], "marker": kind, "start": start}
    cal = {}
    patch = index.get("calibration_patch")
    word = (out.get(patch) or {}).get("words", [None])[0] if patch else None
    if word is not None:
        print(f"\nCalibration: {patch} at {word:#06x}, base {base[word:word + 4].hex(' ')} "
              f"(float {struct.unpack_from('<f', base, word)[0]:.4f})")
        for name, rgb in index.get("calibration", {}).items():
            p = os.path.join(OUT, name)
            if os.path.isfile(p):
                v = read(name)[word:word + 4]
                print(f"  {tuple(rgb)!s:16s} {v.hex(' ')}  float {struct.unpack('<f', v)[0]:.6f}  "
                      f"uint {int.from_bytes(v, 'little'):#010x}")
                cal[name] = {"rgb": rgb, "bytes": v.hex()}
    with open(os.path.join(OUT, "icolors_map.json"), "w", encoding="utf-8") as f:
        json.dump({"size": len(base), "header": base[:8].hex(), "patches": out, "calibration": cal}, f, indent=1)
    print(f"Wrote {os.path.join(OUT, 'icolors_map.json')}")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    {"list": cmd_list, "run": cmd_run, "diff": cmd_diff, "auto": cmd_auto}.get(step, lambda: sys.exit(__doc__))()
