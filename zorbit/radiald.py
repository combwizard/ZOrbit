"""ZOrbit app: owns the menu hotkeys and the overlay, hands picks to the ZBrush bridge.

How it works:
  * The menu hotkey never goes through ZBrush. A low-level keyboard hook sees it, checks that ZBrush is the
    foreground app, opens the ring and swallows the key so ZBrush never acts on it.
  * The ring is a non-activating layered window, destroyed after every pick.
  * A pick is written atomically to %LOCALAPPDATA%\\ZOrbit\\request.json and handed to the bridge
    inside ZBrush, either by a window message to the bridge's listener (no keystroke) or by a bare bridge
    key bound natively in ZBrush (held modifiers released first). Then a zero-distance mouse move wakes
    the pen/cursor tracking.
  * The same pick also goes to request.txt for the ZScript bridge of ZBrush 2022-2025 (no Python API, so no
    listener: those always get the bridge key, and brushes load from their own installation's .zbp files).
  * Brush picks are counted in usage.json; a menu's auto slots are filled from those counts as it opens.
  * tags.json (the user's brush tags) is watched with radial.json: tag slots open a fan of the brushes with
    that tag, and a slot is drawn in the colour of its brush's first tag (expand.py does both).
  * The brush browser is a separate popout process (popout.py): a normal window that stays open until the user
    closes it. It is opened by browser.hotkey, a "browser" ring item or the tray menu. The app finds its
    message-only window and sends it WM_COPYDATA; a brush picked there comes back the same way, to the control
    window, and goes through the normal hand-off once ZBrush has the focus again. The hotkey never closes the
    window: pressed over the browser it hands the keyboard back to ZBrush. The browser outlives the app.

Started through main.py (ZOrbit.exe), normally by the ZBrush bridge when ZBrush launches; it exits when
the last ZBrush process has gone. Only one instance runs at a time.
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C          # noqa: E402
import expand               # noqa: E402
import installs             # noqa: E402
import paths                # noqa: E402
import tags                 # noqa: E402
import usage                # noqa: E402
import win32 as W           # noqa: E402
import zscript_bridge       # noqa: E402

try:
    import brushes          # noqa: E402
except Exception:           # thumbnails are optional
    brushes = None

DATA_DIR = paths.DATA_DIR
LOG_FILE = os.path.join(DATA_DIR, "radiald.log")
REQUEST_FILE = os.path.join(DATA_DIR, "request.json")
LISTENER_FILE = os.path.join(DATA_DIR, "listener.json")
MUTEX_NAME = "Local\\ZOrbit"

WM_APP_PICK = W.WM_APP + 1            # to the bridge listener inside ZBrush
WM_APP_OPEN = W.WM_APP + 10           # hook -> control window: open menu (wparam = menu slot)
WM_APP_KEYUP = W.WM_APP + 11          # hook -> control window: the held hotkey went up
WM_APP_CANCEL = W.WM_APP + 12         # hook -> control window: Esc
WM_APP_MASK = W.WM_APP + 13           # hook -> control window: inject the Alt menu-mask key
WM_APP_BROWSER = W.WM_APP + 14        # hook -> control window: the browser hotkey
WM_APP_BROWSER_PICK = W.WM_APP + 15   # control window -> itself: a brush was picked in the popout
TIMER_WATCH, TIMER_ACK, TIMER_REHOOK, TIMER_CONFIG, TIMER_BROWSER_PICK, TIMER_PREWARM, TIMER_POPOUT_SHOW = range(1, 8)
COPYDATA_PICK, COPYDATA_SHOW, COPYDATA_QUIT = 1, 10, 12   # WM_COPYDATA ids: popout -> app, app -> popout
POPOUT_CLASS = "ZOrbitPopoutCtl"      # the popout's message-only control window
POPOUT_START_S = 15                   # a popout asked to show gets this long to appear before we ask again
THUMB_PX = 128                        # thumbnail cache size, shared with the Studio


def tags_path():
    """tags.json; the environment variable ZORBIT_TAGS_FILE points tests and --check at another file."""
    return os.environ.get("ZORBIT_TAGS_FILE") or paths.TAGS_FILE


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}.{int(time.time() * 1000) % 1000:03d} {msg}"
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    if sys.stdout:
        try:
            print(line, flush=True)
        except Exception:
            pass


def _trim_log(max_bytes=1_000_000):
    try:
        if os.path.getsize(LOG_FILE) > max_bytes:
            with open(LOG_FILE, "rb") as f:
                f.seek(-max_bytes // 2, os.SEEK_END)
                tail = f.read()
            with open(LOG_FILE, "wb") as f:
                f.write(tail)
    except OSError:
        pass


class App:
    def __init__(self, cfg_path, target_exe="zbrush.exe", exit_with_target=False, accept_injected=False,
                 no_tray=False):
        self.cfg_path = cfg_path
        self.target_exe = target_exe.lower()
        self.exit_with_target = exit_with_target
        self.accept_injected = accept_injected
        self.no_tray = no_tray
        self.tray = None
        self.cfg = None
        self._bad_mtime = None          # mtime of a radial.json that failed to load
        self.slots = []                 # menus with hotkeys, indexed for WM_APP_OPEN
        self.ring = None
        self.held_vk = None             # hotkey vk currently held (between our keydown and keyup)
        self.held_swallow = False
        self.hook = None
        self.ctrl = None
        self._pid_exe = {}
        self._pid_install = {}          # pid -> installs.install_of() of the ZBrush.exe behind it
        self._icons = {}
        self._seq = 0
        self._ack = None                # (seq, deadline) of a message-mode pick awaiting pickup
        self._target_misses = 0
        self.usage = usage.Usage()
        self.tags = tags.TagStore(tags_path())
        self.expander = None            # expand.Expander of the current config, tags and usage
        self._refs = []                 # ctypes callbacks that must outlive their registration
        self._browser_vk = None         # the browser hotkey while it is down (its repeats and key-up are ours)
        self._popout_proc = None        # subprocess.Popen of the popout we last started
        self._popout_spawning = False   # a thread is starting it right now
        self._popout_pending = None     # (tag, toggle) to SHOW once a popout started hidden has its window
        self._popout_started = 0.0      # when we last spawned the popout process
        self._popout_show = False       # ... and whether that spawn asked it to show itself
        self._prewarmed = False         # a pre-warm spawn is scheduled or done for this popout
        self._popout_pid = (0.0, 0)     # (valid until, pid of the popout's control window), for the hook
        self._popout_zb = None          # (ZBrush hwnd, its install) from when the browser was last opened
        self._browser_pick = None       # brush Item picked in the popout, waiting for ZBrush to have focus
        self._browser_pick_deadline = 0.0

    # --- config ----------------------------------------------------------------------------------
    def load_config(self, force=False) -> None:
        if self.tags.reload_if_changed():          # new tag labels and colours show in the next ring
            if self.tags.error:
                log(f"tags: {self.tags.error}; keeping the previous tags")
            else:
                log(f"tags loaded: {len(self.tags.tags())} tags, {len(self.tags.tagged('brush'))} tagged brushes")
            force = True
        try:
            mtime = os.stat(self.cfg_path).st_mtime
        except OSError:
            mtime = None                           # missing: reported once, by the load below
        if not force and ((self.cfg and mtime == self.cfg.mtime) or mtime == self._bad_mtime):
            return
        try:
            cfg = C.load(self.cfg_path, self.tags)
        except Exception as e:
            self._bad_mtime = mtime                # logged once per broken version, not on every poll
            log(f"config error, keeping previous config: {e!r}")
            return
        self.cfg = cfg
        self.expander = expand.Expander(cfg, self.usage, self.tags)
        self.slots = [m for m in cfg.menus.values() if m.hotkey]
        for err in cfg.errors:
            log(f"config: {err}")
        log(f"config loaded: {len(cfg.menus)} menus, hotkeys: "
            + ", ".join(f"{m.hotkey.text}->{m.id}" for m in self.slots)
            + f"; bridge mode={cfg.bridge_mode} key={cfg.bridge_key.text if cfg.bridge_key else None}"
            + f"; browser hotkey={cfg.browser_key.text if cfg.browser_key else None}")
        self._prefetch()
        self._schedule_prewarm()

    def _prefetch(self):
        if brushes is None:
            return
        names = set()
        for m in self.cfg.menus.values():
            for it in m.items:
                acts = it.data["steps"] if it.kind == "steps" else [it.data]
                names.update(a["brush"] for a in acts if "brush" in a)
        self.usage.load()
        for m in self.cfg.menus.values():
            if usage.auto_count(m):
                names.update(n for n in self.usage.slots(m) if n)
            for it in m.items:
                if it.kind == "tag":               # warm the fan before it opens
                    tm = self.expander.tag_menu(it.data["tag"])
                    if tm is not None:
                        names.update(i.data["brush"] for i in tm.items if i.kind == "brush")
        size = THUMB_PX
        threading.Thread(target=brushes.prefetch, args=(sorted(names), size), daemon=True).start()

    def icon_for(self, item):
        if brushes is None:
            return None
        size = THUMB_PX
        src = item.icon
        if not src:
            acts = item.data["steps"] if item.kind == "steps" else [item.data]
            src = next((a["brush"] for a in acts if "brush" in a), "")
        if not src:
            return None
        key = (src, size)
        if key not in self._icons:
            im = None
            if src.lower().endswith(".png") and os.path.isfile(src):
                from PIL import Image
                im = Image.open(src).convert("RGBA")
            else:
                im = brushes.thumbnail(src, size)
            self._icons[key] = im
        return self._icons[key]

    # --- target detection ------------------------------------------------------------------------
    def target_in_front(self) -> bool:
        fg = W.GetForegroundWindow()
        if not fg:
            return False
        pid = W.window_pid(fg)
        exe = self._pid_exe.get(pid)
        if exe is None:
            exe = os.path.basename(W.process_image(pid)).lower()
            if len(self._pid_exe) > 256:
                self._pid_exe.clear()
            self._pid_exe[pid] = exe
        return exe == self.target_exe

    def target_install(self) -> dict | None:
        """The ZBrush installation of the foreground window (if that is ZBrush)."""
        fg = W.GetForegroundWindow()
        if not fg or not self.target_in_front():
            return None
        pid = W.window_pid(fg)
        if pid not in self._pid_install:
            if len(self._pid_install) > 32:
                self._pid_install.clear()
            try:
                self._pid_install[pid] = installs.install_of(W.process_image(pid))
            except Exception:
                self._pid_install[pid] = None
        return self._pid_install[pid]

    def _popout_in_front(self) -> bool:
        """The popout is the foreground app, so its hotkey must reach us to hand the keyboard back to ZBrush. The
        pid of its control window is cached for a second: this runs inside the keyboard hook."""
        fg = W.GetForegroundWindow()
        if not fg:
            return False
        now = time.time()
        until, pid = self._popout_pid
        if now >= until:
            hwnd = W.find_message_window(POPOUT_CLASS)
            pid = W.window_pid(hwnd) if hwnd else 0
            self._popout_pid = (now + 1.0, pid)
        return bool(pid) and W.window_pid(fg) == pid

    # --- keyboard hook ---------------------------------------------------------------------------
    def _hook_proc(self, ncode, wparam, lparam):
        try:
            if ncode == 0:
                r = self._on_key(wparam, W.KBDLLHOOKSTRUCT.from_address(lparam))
                if r:
                    return 1
        except Exception:
            log("hook error:\n" + traceback.format_exc())
        return W.CallNextHookEx(self.hook, ncode, wparam, lparam)

    def _on_key(self, wparam, kb) -> bool:
        """Returns True to swallow the key. Must stay fast: Windows drops slow hooks."""
        if (kb.flags & W.LLKHF_INJECTED) and not self.accept_injected:
            return False
        vk = kb.vkCode
        down = wparam in (W.WM_KEYDOWN, W.WM_SYSKEYDOWN)
        up = wparam in (W.WM_KEYUP, W.WM_SYSKEYUP)
        if self.held_vk is not None and vk == self.held_vk:
            if up:
                self.held_vk = None
                W.PostMessageW(self.ctrl, WM_APP_KEYUP, vk, 0)
            return self.held_swallow       # auto-repeat downs and the final up
        if self._browser_vk is not None and vk == self._browser_vk:
            if up:
                self._browser_vk = None
            return True                    # the browser key's repeats and key-up: never a ring's key-up
        if down and vk == W.VK_ESCAPE and self.ring is not None:
            W.PostMessageW(self.ctrl, WM_APP_CANCEL, 0, 0)
            return True
        if not down or vk in W.MODIFIER_VKS:
            return False
        ctrl, alt, shift = (W.modifier_down(W.VK_CONTROL), W.modifier_down(W.VK_MENU),
                            W.modifier_down(W.VK_SHIFT))
        for slot, m in enumerate(self.slots):
            hk = m.hotkey
            if hk.vk == vk and hk.ctrl == ctrl and hk.alt == alt and hk.shift == shift:
                if not self.target_in_front():
                    return False
                self.held_vk, self.held_swallow = vk, m.swallow
                W.PostMessageW(self.ctrl, WM_APP_OPEN, slot, 0)
                if m.swallow and alt:
                    W.PostMessageW(self.ctrl, WM_APP_MASK, 0, 0)
                return m.swallow
        bk = self.browser_key
        if bk is not None and bk.vk == vk and bk.ctrl == ctrl and bk.alt == alt and bk.shift == shift:
            if self.target_in_front() or self._popout_in_front():
                self._browser_vk = vk          # not held_vk: a ring held open on another key keeps its own
                if alt:
                    W.PostMessageW(self.ctrl, WM_APP_MASK, 0, 0)
                W.PostMessageW(self.ctrl, WM_APP_BROWSER, 0, 0)
                return True
        return False

    def install_hook(self):
        if self.hook:
            W.UnhookWindowsHookEx(self.hook)
        proc = W.HOOKPROC(self._hook_proc)
        self._refs.append(proc)
        self._refs = self._refs[-4:]            # old procs kept a little while for in-flight calls
        self.hook = W.SetWindowsHookExW(W.WH_KEYBOARD_LL, proc, W.GetModuleHandleW(None), 0)
        if not self.hook:
            raise ctypes.WinError(ctypes.get_last_error())

    # --- control window --------------------------------------------------------------------------
    def _ctrl_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_APP_OPEN:
                self.open_slot(wparam)
                return 0
            if msg == WM_APP_KEYUP:
                if self.ring is not None:
                    self.ring.key_released()
                return 0
            if msg == WM_APP_CANCEL:
                if self.ring is not None:
                    self.ring.cancel("escape")
                return 0
            if msg == WM_APP_MASK:
                W.send_keys([(W.VK_MENU_MASK, False), (W.VK_MENU_MASK, True)])
                return 0
            if msg == WM_APP_BROWSER:
                if self.ring is not None:
                    self.ring.cancel("browser")
                self.open_browser(None, toggle=True)
                return 0
            if msg == WM_APP_BROWSER_PICK:
                self._browser_pick_queued()
                return 0
            if msg == W.WM_COPYDATA:
                return self._on_copydata(wparam, lparam)
            if msg == W.WM_TIMER:
                if wparam == TIMER_WATCH:
                    self._watch_target()
                elif wparam == TIMER_ACK:
                    self._check_ack()
                elif wparam == TIMER_REHOOK and self.ring is None and self.held_vk is None:
                    self.install_hook()         # Windows silently drops hooks that ever timed out
                elif wparam == TIMER_CONFIG:
                    self.load_config()          # a new or changed hotkey must work before any ring opens
                elif wparam == TIMER_BROWSER_PICK:
                    self._browser_pick_tick()
                elif wparam == TIMER_PREWARM:
                    W.KillTimer(self.ctrl, TIMER_PREWARM)
                    self._prewarm()
                elif wparam == TIMER_POPOUT_SHOW:
                    self._popout_show_tick()
                return 0
        except Exception:
            log("control error:\n" + traceback.format_exc())
            return 0
        return W.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _create_ctrl(self):
        proc = W.WNDPROC(self._ctrl_proc)
        self._refs_ctrl = proc
        wc = W.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(W.WNDCLASSEXW)
        wc.lpfnWndProc = proc
        wc.hInstance = W.GetModuleHandleW(None)
        wc.lpszClassName = "ZOrbitControl"
        if not W.RegisterClassExW(ctypes.byref(wc)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.ctrl = W.CreateWindowExW(0, "ZOrbitControl", "ZOrbit control", 0, 0, 0, 0, 0,
                                      W.HWND_MESSAGE, None, wc.hInstance, None)
        if not self.ctrl:
            raise ctypes.WinError(ctypes.get_last_error())

    # --- tray icon -------------------------------------------------------------------------------
    def _create_tray(self):
        if self.no_tray:
            return
        try:
            from tray import Tray
            tray = Tray(f"ZOrbit {paths.VERSION}", paths.ICON, self._tray_command, log)
            self.tray = tray
            ok = tray.create()
            log(f"tray icon {'added' if ok else 'not added yet (will retry)'}")
        except Exception:
            log("tray unavailable:\n" + traceback.format_exc())

    def _destroy_tray(self):
        tray, self.tray = self.tray, None
        if tray is None:
            return
        try:
            tray.destroy()
        except Exception:
            log("tray destroy error:\n" + traceback.format_exc())

    def _tray_command(self, name):
        try:
            if name == "browser":
                log("tray: opening the brush browser")
                self.open_browser(None, toggle=False)
            elif name == "studio":
                subprocess.Popen(paths.launch_commands()["studio"], env=paths.clean_env(),
                                 creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                                 close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                log("tray: opening the Studio")
            elif name == "reload":
                self.load_config(force=True)
                log("tray: menus reloaded")
            elif name == "logs":
                os.makedirs(paths.DATA_DIR, exist_ok=True)
                os.startfile(paths.DATA_DIR)
            elif name == "quit":
                log("tray: quit requested")
                W.PostQuitMessage(0)
        except Exception:
            log(f"tray command {name!r} failed:\n" + traceback.format_exc())

    # --- menus -----------------------------------------------------------------------------------
    def open_slot(self, slot):
        self.load_config()                         # picks up edits to radial.json on every open
        if slot >= len(self.slots):
            return
        menu = self.slots[slot]
        if self.ring is not None:
            same = self.ring.menu.id == menu.id
            self.ring.cancel("reopened")
            if same:
                return                             # pressing the hotkey again closes the ring
        self.open_menu(menu, W.cursor_pos(), held=self.held_vk is not None)

    def _record_pick(self, item):
        """Counts a brush pick and lets the auto slots of every menu react to it."""
        if item.kind != "brush":
            return
        self.usage.load().record(item.data["brush"])
        autos = [m for m in self.cfg.menus.values() if usage.auto_count(m)]
        for m in autos:
            before = self.usage.slots(m)
            self.usage.update(m)
            after = self.usage.menus[m.id]["slots"]
            if after != before:
                log(f"auto slots of '{m.id}': {before} -> {after}")
        self.usage.menus = {m.id: self.usage.menus[m.id] for m in autos}
        try:
            self.usage.save()
        except OSError as e:
            log(f"could not save usage.json: {e!r}")

    def open_menu(self, menu, pos, held, nested=False):
        from ring import Ring
        menu = self.expander.menu(menu)
        ring = Ring(menu, self.cfg.ring, self.icon_for, self._on_ring_done, log, held=held, nested=nested,
                    submenus=self.expander.resolve)
        self.ring = ring
        try:
            ring.show(*pos)
        except Exception:
            log("could not show ring:\n" + traceback.format_exc())
            self.ring = None
            return
        self._ring_centre = pos

    def _on_ring_done(self, item, reason, at=None):
        self.ring = None
        if item is None:
            return
        if item.kind == "menu":
            sub = self.expander.resolve(item.data["menu"])
            if sub is not None and at is not None:  # flicked or hovered: centred on its slot, still held if so
                self.open_menu(sub, at, held=self.held_vk is not None, nested=True)
            elif sub is not None:
                self.open_menu(sub, W.cursor_pos(), held=False)   # re-centred on the pick
            return
        if item.kind in ("auto", "tag"):
            log(f"empty {item.kind} slot picked; nothing sent")
            return
        if item.kind == "browser":
            self.open_browser(item.data["browser"] or None)
            return
        self.send(item)
        try:
            self._record_pick(item)
        except Exception:
            log("usage error:\n" + traceback.format_exc())

    # --- brush browser popout --------------------------------------------------------------------
    @property
    def browser_key(self):
        return self.cfg.browser_key if self.cfg else None

    def _spawn_popout(self, show, tag=None, zb_hwnd=0):
        """Starts the popout process on a worker thread: this runs on the keyboard hook's thread, and a process
        start that outlasts Windows' low-level hook timeout gets the hook dropped."""
        cmd = paths.launch_commands()["popout"] + ["--managed"]
        if show:
            cmd.append("--show")
            if tag:
                cmd += ["--tag", tag]
            cmd += ["--zbrush-hwnd", str(zb_hwnd)]
        self._popout_started, self._popout_show, self._popout_spawning = time.time(), show, True

        def start():
            try:
                self._popout_proc = subprocess.Popen(
                    cmd, env=paths.clean_env(),
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                    close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                log(f"popout started: {cmd}")
            except Exception:
                self._popout_proc = None
                log(f"could not start the popout {cmd}:\n" + traceback.format_exc())
            finally:
                self._popout_spawning = False
        threading.Thread(target=start, daemon=True).start()

    def open_browser(self, tag=None, toggle=False):
        """Shows the brush browser, starting its process if none is running. toggle (the hotkey): if it is already
        the front window, ZBrush gets the keyboard back instead; the window itself stays open."""
        fg = W.GetForegroundWindow()
        if fg and self.target_in_front():          # remembered for the pick: the popout takes the focus away
            self._popout_zb = (int(fg), self.target_install())
        zb = self._popout_zb[0] if self._popout_zb else 0
        hwnd = W.find_message_window(POPOUT_CLASS)
        if hwnd:
            payload = json.dumps({"tag": tag or None, "zbrush_hwnd": zb, "toggle": bool(toggle)}).encode("utf-8")
            r = W.send_copydata(hwnd, COPYDATA_SHOW, payload)
            log(f"browser: SHOW sent to popout {hwnd} (tag={tag or None}, toggle={bool(toggle)}, zbrush={zb}): "
                + ("no answer within 0.5 s" if r is None else f"result {r}"))
            return
        self._prewarmed = False                    # the popout is gone: the next config load may warm it again
        if self._spawning():
            if self._popout_show:
                log("popout starting; ignoring")    # it shows itself when it is up
            else:                                  # a pre-warm is still coming up: show it as soon as it is there
                self._popout_pending = (tag, bool(toggle))
                W.SetTimer(self.ctrl, TIMER_POPOUT_SHOW, 100, None)
                log("popout warming up; showing it when it is ready")
            return
        self._spawn_popout(True, tag, zb)

    def _spawning(self) -> bool:
        """A popout we started is still coming up: its process lives and has had less than POPOUT_START_S."""
        if time.time() - self._popout_started >= POPOUT_START_S:
            return False
        p = self._popout_proc
        return self._popout_spawning or (p is not None and p.poll() is None)

    def _popout_show_tick(self):
        pend = self._popout_pending
        if pend is None:
            W.KillTimer(self.ctrl, TIMER_POPOUT_SHOW)
            return
        if W.find_message_window(POPOUT_CLASS):
            W.KillTimer(self.ctrl, TIMER_POPOUT_SHOW)
            self._popout_pending = None
            self.open_browser(pend[0], toggle=False)   # it was not up yet: a toggle must not hand the focus away
        elif not self._spawning():
            W.KillTimer(self.ctrl, TIMER_POPOUT_SHOW)
            self._popout_pending = None
            log("popout did not come up; the next press starts it again")

    def _wants_browser(self) -> bool:
        cfg = self.cfg
        return bool(cfg and (cfg.browser_key or any(it.kind == "browser" for m in cfg.menus.values()
                                                    for it in m.items)))

    def _schedule_prewarm(self):
        """Starts the popout hidden a few seconds after launch, so the first press is quick. A one-shot timer:
        loading the config must not wait for a process start."""
        if self.ctrl is None or self._prewarmed or not self._wants_browser():
            return
        self._prewarmed = True
        W.SetTimer(self.ctrl, TIMER_PREWARM, 3000, None)

    def _prewarm(self):
        if W.find_message_window(POPOUT_CLASS) or self._spawning():
            return
        log("browser: pre-warming the popout")
        self._spawn_popout(False)

    def _on_copydata(self, wparam, lparam) -> int:
        """WM_COPYDATA from the popout: 1 = accepted, 0 = refused. Only a brush name is taken from the payload;
        the .zbp is looked up by send() as for any other pick."""
        try:
            cds = W.COPYDATASTRUCT.from_address(lparam)
            if cds.dwData != COPYDATA_PICK or not cds.lpData or not 0 < cds.cbData <= 4096:
                log(f"copydata refused: dwData={cds.dwData} cbData={cds.cbData}")
                return 0
            raw = ctypes.string_at(cds.lpData, cds.cbData)     # copied here: the sender's buffer dies on return
            msg = json.loads(raw.decode("utf-8"))
        except (ValueError, OSError) as e:                     # includes UnicodeDecodeError, JSONDecodeError
            log(f"copydata refused: unreadable payload ({e!r})")
            return 0
        name = msg.get("name") if isinstance(msg, dict) else None
        if (not isinstance(msg, dict) or msg.get("v") != 1 or msg.get("op") != "pick"
                or msg.get("kind") != "brush" or not isinstance(name, str) or not name or len(name) > 120
                or any(c in name for c in "\\/:") or ".." in name or any(ord(c) < 32 for c in name)):
            log(f"copydata refused: not a valid pick ({str(msg)[:80]!r})")
            return 0
        self._browser_pick = C.Item(label=name, kind="brush", data={"brush": name})
        W.PostMessageW(self.ctrl, WM_APP_BROWSER_PICK, 0, 0)
        return 1

    def _browser_pick_queued(self):
        """The popout hands the focus back to ZBrush before it sends the pick, but activation finishes on its own
        time and press_bridge_key refuses while ZBrush is not in front: wait for it (at most 0.5 s)."""
        ins = self._popout_zb[1] if self._popout_zb else None
        legacy = ins is not None and not ins["python"]      # only the bridge key can reach it: needs the focus
        self._browser_pick_deadline = time.time() + (2.0 if legacy else 0.5)
        W.SetTimer(self.ctrl, TIMER_BROWSER_PICK, 30, None)

    def _browser_pick_tick(self):
        item = self._browser_pick
        if item is None:
            W.KillTimer(self.ctrl, TIMER_BROWSER_PICK)
            return
        ins = self._popout_zb[1] if self._popout_zb else None
        legacy = ins is not None and not ins["python"]
        in_front = self.target_in_front()
        if not (in_front or (not legacy and self._listener() is not None)
                or time.time() >= self._browser_pick_deadline):
            return
        W.KillTimer(self.ctrl, TIMER_BROWSER_PICK)
        self._browser_pick = None
        if legacy and not in_front:
            log(f"pick from browser '{item.label}' dropped: ZBrush did not get the focus back in 2 s")
            return
        log(f"pick from browser '{item.label}'")
        self.send(item, install=ins)
        try:
            self._record_pick(item)
        except Exception:
            log("usage error:\n" + traceback.format_exc())

    # --- hand-off to ZBrush ----------------------------------------------------------------------
    def _actions(self, item, legacy=None):
        """legacy: the ZBrush 2022-2025 installation in front, whose own .zbp files must be used."""
        acts = item.data["steps"] if item.kind == "steps" else [item.data]
        out = []
        for a in acts:
            a = dict(a)
            if "brush" in a and brushes is not None:
                p = brushes.find_brush(a["brush"], legacy["path"] if legacy else None)
                a["file"] = str(p).replace("\\", "/") if p else None
            out.append(a)
        return out

    def _write_request(self, item, legacy=None) -> int:
        self._seq += 1
        actions = self._actions(item, legacy)
        req = {"id": self._seq, "time": time.time(), "label": item.label, "actions": actions}
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = REQUEST_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(req, f)
        os.replace(tmp, REQUEST_FILE)              # atomic: the bridge never sees half a request
        try:
            for p in zscript_bridge.write_request(self._seq, item.label, actions):
                log(f"pick #{self._seq}: request.txt: {p}")
        except OSError as e:
            log(f"pick #{self._seq}: could not write request.txt: {e!r}")
        return self._seq

    def _listener(self):
        try:
            with open(LISTENER_FILE, encoding="utf-8") as f:
                info = json.load(f)
            hwnd = W.w.HWND(int(info["hwnd"]))
            if info.get("verified") and W.IsWindow(hwnd):
                return hwnd
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None

    def send(self, item, install=None):
        """install: the ZBrush installation to hand off to, when it is not the one in front right now (a pick
        from the browser arrives after the focus has moved)."""
        ins = install if install is not None else self.target_install()
        legacy = ins if ins is not None and not ins["python"] else None
        seq = self._write_request(item, legacy)
        mode = self.cfg.bridge_mode
        if legacy is not None:
            # A listener can only be a ZBrush 2026+ (perhaps running as well), never the one in front.
            log(f"pick #{seq} '{item.label}': {legacy['name']} in front, so the ZScript bridge (bridge key)")
            self.press_bridge_key(seq)
            W.nudge_mouse()
            return
        listener = self._listener() if mode in ("auto", "message") else None
        if listener is not None:
            ok = W.PostMessageW(listener, WM_APP_PICK, seq, 0)
            log(f"pick #{seq} '{item.label}' -> listener {int(listener.value)} (posted={bool(ok)})")
            if ok:
                self._ack = (seq, time.time() + 0.5)
                W.SetTimer(self.ctrl, TIMER_ACK, 100, None)
                W.nudge_mouse()
                return
        if mode == "message":
            log(f"pick #{seq}: no live listener in ZBrush and bridge mode is 'message'; nothing sent")
            return
        self.press_bridge_key(seq)
        W.nudge_mouse()

    def _check_ack(self):
        if self._ack is None:
            W.KillTimer(self.ctrl, TIMER_ACK)
            return
        seq, deadline = self._ack
        pending = os.path.exists(REQUEST_FILE)
        if not pending:
            self._ack = None
            W.KillTimer(self.ctrl, TIMER_ACK)
            return
        if time.time() < deadline:
            return
        self._ack = None
        W.KillTimer(self.ctrl, TIMER_ACK)
        if self.cfg.bridge_mode == "auto" and self.cfg.bridge_key:
            log(f"pick #{seq}: listener did not pick it up in 0.5 s; falling back to the bridge key")
            self.press_bridge_key(seq)
        else:
            log(f"pick #{seq}: listener did not pick it up in 0.5 s")

    def press_bridge_key(self, seq):
        key = self.cfg.bridge_key
        if key is None:
            log(f"pick #{seq}: no bridge key configured; nothing sent")
            return
        if not self.target_in_front():
            log(f"pick #{seq}: ZBrush is not in front; bridge key not sent (it would land in another app)")
            return
        held = [vk for vk in (0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5) if W.key_down(vk)]
        events = [(vk, True) for vk in held]                     # release what the user still holds
        mods = [vk for vk, on in ((W.VK_MENU, key.alt),) if on]  # bridge keys allow Alt only
        events += [(vk, False) for vk in mods] + [(key.vk, False), (key.vk, True)]
        events += [(vk, True) for vk in reversed(mods)]
        n = W.send_keys(events)
        still = [vk for vk in held if W.key_down(vk)]
        if still:
            W.send_keys([(vk, False) for vk in still])
        log(f"pick #{seq} -> bridge key {key.text} (sent {n} events; released/restored {held}/{still})")

    # --- lifetime --------------------------------------------------------------------------------
    def _watch_target(self):
        if not self.exit_with_target:
            return
        if self.target_exe in W.running_exe_names():
            self._target_misses = 0
            return
        self._target_misses += 1
        if self._target_misses >= 2:
            log(f"{self.target_exe} is no longer running; exiting")
            W.PostQuitMessage(0)

    def run(self) -> int:
        os.makedirs(DATA_DIR, exist_ok=True)
        _trim_log()
        mutex = W.CreateMutexW(None, False, MUTEX_NAME)
        created = W.process_created(os.getpid())
        started = f"{time.time() - created:.2f} s after its process was created" if created else "?"
        if ctypes.get_last_error() == W.ERROR_ALREADY_EXISTS:
            log(f"another instance is already running; exiting ({started}; started by {W.launch_chain()})")
            return 0
        W.make_dpi_aware()
        log(f"ZOrbit starting (pid {os.getpid()}, python {sys.version.split()[0]}, "
            f"thumbnails={'on' if brushes else 'off'}; {started}; started by {W.launch_chain()})")
        self.load_config(force=True)
        if self.cfg is None:
            return 1
        self._create_ctrl()
        self._schedule_prewarm()
        self.install_hook()
        W.SetTimer(self.ctrl, TIMER_WATCH, 3000, None)
        W.SetTimer(self.ctrl, TIMER_REHOOK, 120000, None)
        W.SetTimer(self.ctrl, TIMER_CONFIG, 500, None)
        self._create_tray()
        msg = W.w.MSG()
        try:
            while W.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                W.TranslateMessage(ctypes.byref(msg))
                W.DispatchMessageW(ctypes.byref(msg))
        finally:
            self._destroy_tray()
        popout = W.find_message_window(POPOUT_CLASS)
        if popout:
            W.send_copydata(popout, COPYDATA_QUIT, b"{}")
        if self.hook:
            W.UnhookWindowsHookEx(self.hook)
        W.CloseHandle(mutex)
        log("ZOrbit stopped")
        return 0


def check(cfg_path) -> int:
    store = tags.TagStore(tags_path()).load()
    cfg = C.load(cfg_path, store)
    print(f"{cfg_path}: {len(cfg.menus)} menus, bridge mode={cfg.bridge_mode} "
          f"key={cfg.bridge_key.text if cfg.bridge_key else None}, "
          f"browser hotkey={cfg.browser_key.text if cfg.browser_key else None}")
    for m in cfg.menus.values():
        print(f"  [{m.id}] '{m.title}' hotkey={m.hotkey.text if m.hotkey else '-'} swallow={m.swallow}")
        for it in m.items:
            extra = ""
            if it.kind == "brush" and brushes is not None:
                p = brushes.find_brush(it.data["brush"])
                extra = f"  ({p})" if p else "  (no .zbp found: must already be loaded in ZBrush)"
            elif it.kind == "tag":
                key = it.data["tag"]
                n = len(store.items_with(key, "brush"))
                extra = (f"  ({n} brush{'' if n == 1 else 'es'} tagged)" if store.has(key)
                         else f"  (tag {key!r} does not exist)")
            print(f"      {it.kind:7s} {it.label}{extra}")
    problems = ([f"tags: {store.error}"] if store.error else []) + cfg.errors
    for e in problems:
        print(f"  PROBLEM: {e}")
    return 1 if problems else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default=None, help="menus file (default: %%APPDATA%%\\ZOrbit\\radial.json)")
    ap.add_argument("--exit-with-zbrush", action="store_true", help="quit when ZBrush.exe has exited")
    ap.add_argument("--target-exe", default="ZBrush.exe", help=argparse.SUPPRESS)
    ap.add_argument("--accept-injected", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--no-tray", action="store_true", help="do not show the notification-area icon")
    ap.add_argument("--check", action="store_true", help="validate the config and exit")
    a = ap.parse_args(argv)
    if a.config is None:
        a.config = paths.ensure_config()
    if a.check:
        return check(a.config)
    try:
        return App(a.config, a.target_exe, a.exit_with_zbrush, a.accept_injected, a.no_tray).run()
    except Exception:
        log("fatal:\n" + traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
