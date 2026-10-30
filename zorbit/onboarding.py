"""What the Studio's Setup screen needs to know: is ZBrush found, will it load the bridge, did it.

snapshot() builds the get_setup answer from facts it reads itself (the ZBRUSH_PLUGIN_PATH variable, running
ZBrush processes, the ZScript plugin files and logs) plus what the Studio hands in (the installs, the listener
and last-pick files it already parses). Nothing here changes anything except register_plugin_path(), which
mirrors packaging/installer.iss RegisterBridge: it adds the bridge folder to the user's ZBRUSH_PLUGIN_PATH, keeps
every other entry and never removes one.

All times are epoch seconds (floats) and everything returned is JSON-able.
"""
import ntpath
import os
import sys
import time
import winreg

import activity
import installs as installs_mod
import paths
import win32 as W
import zscript_bridge

ENV_KEY = "Environment"
ENV_VALUE = "ZBRUSH_PLUGIN_PATH"
START_GRACE = 90          # seconds after ZBrush starts during which "not loaded yet" is still "starting"
BRIDGE_FILES = ("zorbit_bridge.py", "radial_bridge.py", "radialmenu_bridge.py")    # ours and the old names


# --- ZBRUSH_PLUGIN_PATH ----------------------------------------------------------------------------
def plugin_path_entries() -> tuple[list[str], int | None, float | None]:
    """(entries, registry type, last write of the Environment key). Entries are the ';' separated parts of the
    user's ZBRUSH_PLUGIN_PATH, trimmed, empties dropped. The type is winreg.REG_SZ or REG_EXPAND_SZ, None when
    the variable is not there. The last-write time belongs to the whole Environment key, not to this one
    variable: any user variable written since counts, which is close enough to say 'changed after ZBrush
    started'."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, ENV_KEY, 0, winreg.KEY_READ)
    except OSError:
        return [], None, None
    with key:
        try:
            mtime = winreg.QueryInfoKey(key)[2] / 1e7 - 11644473600       # FILETIME (100 ns since 1601) -> epoch
        except OSError:
            mtime = None
        try:
            value, regtype = winreg.QueryValueEx(key, ENV_VALUE)
        except OSError:
            return [], None, mtime
    if not isinstance(value, str) or regtype not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
        return [], None, mtime
    return [p.strip() for p in value.split(";") if p.strip()], regtype, mtime


def _same_dir(a: str, b: str) -> bool:
    """Whether two folder names are the same folder as Windows sees it: case, slashes, quotes, a trailing
    backslash and %VARIABLES% do not matter."""
    def norm(x):
        return ntpath.normcase(ntpath.normpath(os.path.expandvars(str(x).strip().strip('"')))).rstrip("\\")
    return norm(a) == norm(b)


def is_registered(dir: str | None, entries: list[str]) -> bool:
    return bool(dir) and any(_same_dir(dir, e) for e in entries)


def other_zorbit_entries(dir: str | None, entries: list[str]) -> list[dict]:
    """Entries that are not dir but look like a ZOrbit (or Radial Menu) bridge folder: a second copy of the
    plugin that ZBrush would also load. Only reported, never removed."""
    out = []
    for e in entries:
        if dir and _same_dir(dir, e):
            continue
        real = os.path.expandvars(e.strip().strip('"'))
        low = e.lower()
        bridge_like = ntpath.basename(ntpath.normpath(real)).lower() == "bridge" and any(
            os.path.isfile(os.path.join(real, f)) for f in BRIDGE_FILES)
        if bridge_like or "zorbit" in low or "radialmenu" in low:
            out.append({"path": e, "exists": os.path.isdir(real)})
    return out


def register_plugin_path(dir: str) -> dict:
    """Adds dir to the user's ZBRUSH_PLUGIN_PATH, like the installer does, and tells running programs. The
    caller must pass a folder it computed itself (paths.bridge_dir()), never one the UI sent."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, ENV_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            try:
                current, regtype = winreg.QueryValueEx(key, ENV_VALUE)
            except OSError:
                current, regtype = "", winreg.REG_SZ
            if not isinstance(current, str) or regtype not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ):
                current, regtype = "", winreg.REG_SZ
            entries = [p.strip() for p in current.split(";") if p.strip()]
            if is_registered(dir, entries):
                return {"ok": True, "changed": False, "message": "Already registered.", "value": current}
            base = current.strip().rstrip(";")
            value = base + ";" + dir if base else dir
            winreg.SetValueEx(key, ENV_VALUE, 0, regtype, value)
    except OSError as e:
        return {"ok": False, "changed": False, "message": f"Could not change {ENV_VALUE}: {e}", "value": None}
    W.broadcast_setting_change(ENV_KEY)          # a failed broadcast is not an error: restarting ZBrush is needed anyway
    return {"ok": True, "changed": True, "message": "Registered. Restart ZBrush so it loads the plugin.",
            "value": value}


# --- the snapshot ----------------------------------------------------------------------------------
def _bridge_info(dir: str | None) -> dict:
    if not dir:
        return {"dir": None, "dir_ok": False, "kind": "missing"}
    if not paths.FROZEN:
        kind = "checkout"
    elif _same_dir(dir, os.path.join(os.path.dirname(sys.executable), "bridge")):
        kind = "installed"
    else:
        kind = "portable"
    return {"dir": dir, "dir_ok": os.path.isfile(os.path.join(dir, "zorbit_bridge.py")), "kind": kind}


def _mtime(p: str) -> float | None:
    try:
        return os.path.getmtime(p)
    except OSError:
        return None


def _listener_view(listener: dict | None) -> dict | None:
    """The listener as the page gets it, with whether listener.json is left over from a ZBrush that is gone."""
    if not listener:
        return None
    pid, verified = listener.get("pid"), listener.get("verified")
    alive = bool(listener.get("alive"))
    stale = not alive
    if not stale and isinstance(pid, int):
        created = W.process_created(pid)
        stale = (created is None or os.path.basename(W.process_image(pid)).lower() != "zbrush.exe"
                 or bool(verified and created > verified))
    return {"verified": verified, "alive": alive, "pid": pid, "stale": stale}


def _modern_proc(proc: dict, listener: dict | None, registered: bool, key_mtime: float | None) -> None:
    pid, started, age = proc["pid"], proc["started"], proc["age"]
    if listener and listener["pid"] == pid and listener["alive"] and not listener["stale"]:
        proc.update(state="loaded", evidence="listener", why="the bridge is listening in this ZBrush")
    elif started is None:
        proc.update(state="unknown", evidence=None, why="could not read when this ZBrush started")
    elif not registered:
        proc.update(state="not_loaded", evidence=None, why="ZBRUSH_PLUGIN_PATH does not point at the plugin")
    elif key_mtime and key_mtime > started:
        proc.update(state="restart", evidence="env_mtime", why="started before the plugin was set up")
    elif age < START_GRACE:
        proc.update(state="starting", evidence=None, why="started a moment ago")
    else:
        proc.update(state="not_loaded", evidence=None,
                    why="registered, but the plugin did not start; see bridge.log")


def _legacy_proc(proc: dict, install: dict) -> None:
    started, age = proc["started"], proc["age"]
    plugin = install["plugin"]
    if started is None:
        proc.update(state="unknown", evidence=None, why="could not read when this ZBrush started")
        return
    zsc = [m for m in (_mtime(os.path.join(plugin.get("zplugs") or "", n))
                       for n in (zscript_bridge.PLUGIN, zscript_bridge.LEGACY_PLUGIN)) if m]
    hotkey = _mtime(os.path.join(paths.DATA_DIR, "zscript_hotkey.log"))
    launch = _mtime(os.path.join(paths.DATA_DIR, "zscript_launch.log"))
    if zsc and max(zsc) > started:
        proc.update(state="restart", evidence="zsc_mtime", why="started before the plugin was installed")
    elif hotkey and hotkey >= started:
        proc.update(state="loaded", evidence="hotkey_log", why="the plugin wrote its log after this start")
    elif launch and launch >= started:
        proc.update(state="loaded", evidence="launch_log", why="the plugin wrote its log after this start")
    elif not plugin.get("installed"):
        proc.update(state="not_loaded", evidence=None, why="the ZScript plugin is not installed in this ZBrush")
    elif age < START_GRACE:
        proc.update(state="starting", evidence=None, why="started a moment ago")
    else:
        proc.update(state="not_loaded", evidence=None,
                    why="installed, but the plugin left no log after this start")


def snapshot(all_installs: list[dict], listener: dict | None, last_pick: dict | None, bridge_mode: str,
             bundled: bool, app_running: bool = False) -> dict:
    """The get_setup answer. all_installs: every ZBrush the Studio knows, found or added by hand, as
    {name, year, path, python, added}. listener: Api._listener_info(), last_pick: Api._last_pick_info()."""
    now = time.time()
    bridge = _bridge_info(paths.bridge_dir())
    entries, _regtype, key_mtime = plugin_path_entries()
    registered = is_registered(bridge["dir"], entries)
    env = {"registered": registered, "entries": entries, "other_zorbit": other_zorbit_entries(bridge["dir"], entries),
           "key_mtime": key_mtime, "can_fix": bool(bridge["dir_ok"] and not registered)}

    rows, index = [], {}

    def row(e: dict, added: bool) -> dict:
        key = ntpath.normcase(ntpath.normpath(e["path"]))
        if key in index:
            return index[key]
        r = {"name": e["name"], "year": e["year"], "path": e["path"], "python": bool(e["python"]),
             "added": added, "kind": "modern" if e["python"] else "legacy", "procs": []}
        if e["python"]:
            r["plugin"] = {"state": "no_bridge" if not bridge["dir_ok"] else ("ok" if registered else "unregistered")}
            r["ready"] = bool(registered and bridge["dir_ok"])
        else:
            try:
                st = zscript_bridge.status(e["path"])
            except OSError:
                st = {"installed": False, "current": False, "zplugs": zscript_bridge.zplugs(e["path"])}
            state = "missing" if not st["installed"] else ("ok" if st["current"] else "outdated")
            r["plugin"] = dict(st, state=state)
            r["ready"] = bool(st["installed"])
        index[key] = r
        rows.append(r)
        return r

    for e in all_installs:
        row(e, bool(e.get("added")))

    # Running ZBrushes: each one belongs to an install, or is elevated (its image cannot be read).
    unmatched = []
    pids = W.pids_named("zbrush.exe")
    for pid in pids:
        started = W.process_created(pid)
        image = W.process_image(pid)
        if not image:
            unmatched.append({"pid": pid, "started": started, "elevated": True})
            continue
        e = installs_mod.install_of(image)
        if e is None:
            unmatched.append({"pid": pid, "started": started, "elevated": False})
            continue
        r = row(e, False)                        # a ZBrush the scan missed still gets a row
        r["procs"].append({"pid": pid, "started": started, "age": (now - started) if started else None,
                           "state": "unknown", "evidence": None, "why": ""})

    lview = _listener_view(listener)
    legacy_running = sum(len(r["procs"]) for r in rows if r["kind"] == "legacy")
    for r in rows:
        for proc in r["procs"]:
            if r["kind"] == "modern":
                _modern_proc(proc, lview, registered, key_mtime)
            else:
                _legacy_proc(proc, r)
                if legacy_running > 1 and proc["state"] == "loaded":
                    proc["why"] = "shared log; cannot tell which"

    reasons = []
    if rows and not any(r["ready"] for r in rows):
        reasons.append("No ZBrush has the plugin set up.")
    for r in rows:
        if r["procs"] and not r["ready"]:
            reasons.append(f"{r['name']} is running without the plugin set up.")

    return {"now": now, "checked_at": now, "bridge": bridge, "env": env, "installs": rows,
            "unmatched_procs": unmatched, "zbrush": {"running": bool(pids), "check_ok": True},
            "listener": lview, "app": {"running": bool(app_running)}, "bridge_mode": bridge_mode,
            "bundled": bool(bundled), "activity": activity.read(os.path.join(paths.DATA_DIR, "activity.json")),
            "last_pick": last_pick, "hard_fail": bool(reasons), "hard_reasons": reasons}
