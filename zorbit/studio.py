"""ZOrbit Studio: the companion app (menu editor, brush library, settings, status).

A pywebview window (Windows' built-in Edge WebView2) showing studio_ui/index.html. The page calls the Api
methods below as `await window.pywebview.api.<name>(...)`; every method returns plain JSON-able data.

Started as `ZOrbit.exe --studio` (or `main.py --studio`). One instance at a time; a second launch brings
the first to the front.
"""
import base64
import copy
import ctypes
import ctypes.wintypes as w
import io
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import config as C          # noqa: E402
import assets               # noqa: E402
import brushes              # noqa: E402
import changelog            # noqa: E402
import expand               # noqa: E402
import fsutil               # noqa: E402
import installs             # noqa: E402
import looks as L           # noqa: E402
import menushare            # noqa: E402
import onboarding           # noqa: E402
import paths                # noqa: E402
import profiles           # noqa: E402
import radiald              # noqa: E402
import report               # noqa: E402
import tags                 # noqa: E402
import theme                # noqa: E402
import webapi               # noqa: E402
import webview2             # noqa: E402
import win32 as W           # noqa: E402
import winframe             # noqa: E402
import zscript_bridge       # noqa: E402

DATA_DIR = paths.DATA_DIR
UI_INDEX = os.path.join(paths.UI_DIR, "index.html")
APP_MUTEX = "Local\\ZOrbit"
STUDIO_MUTEX = "Local\\ZOrbitStudio"
TITLE = "ZOrbit Studio"
VERSION = paths.VERSION
APP_ID = "ZOrbit.Studio"           # taskbar identity, so the Studio groups under its own icon
STUDIO_FILE = os.path.join(paths.CONFIG_DIR, "studio.json")   # Studio preferences and window placement


def _theme_now():
    """The theme in force (dark, light or zbrush), from studio.json. A module function so the tests can swap it."""
    return theme.current(STUDIO_FILE)

DEFAULT_SIZE = (1320, 860)  # the first window, in logical pixels, when it fits the screen (see _fit_size)
MIN_SIZE = (980, 560)       # the smallest the window can be made
START_WAIT = 10.0          # seconds start_app waits for the app's mutex (or, for an older app, its new version)
SAMPLE_SLOTS = 8           # slots on the sample ring (preview_tags, preview_look): 7 brushes and a submenu
SAMPLE_BRUSHES = ("ClayBuildup", "Move", "hPolish", "Standard", "DamStandard", "Inflat", "TrimDynamic")  # no library
LOOK_IMAGES = 64           # look pictures kept for the next preview_look(s) with the same look, theme and size
SETTINGS_FORMAT = 1         # the "zorbit_settings" number of an exported settings file
IMPORT_MAX_BYTES = 5 * 1024 * 1024    # a settings file is a few hundred KB at most; refuse anything bigger
RELEASES_API = "https://api.github.com/repos/combwizard/zorbit/releases/latest"
RELEASES_URL = "https://github.com/combwizard/zorbit/releases"
DOWNLOAD_URL = RELEASES_URL + "/download/"    # a release's files; the only place Studio downloads a setup from
SETUP_MAX_BYTES = 300 * 1024 * 1024           # the setup is about 30 MB; anything far bigger is not ours
# The uninstall entry Setup writes (installer.iss AppId; PrivilegesRequired=lowest puts it under HKCU).
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\{6F1B7C52-3D4A-4E8B-9A57-2C0E81D4B9A3}_is1"

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
OpenMutexW = kernel32.OpenMutexW
OpenMutexW.restype, OpenMutexW.argtypes = w.HANDLE, [w.DWORD, w.BOOL, w.LPCWSTR]
CreateMutexW = kernel32.CreateMutexW
CreateMutexW.restype, CreateMutexW.argtypes = w.HANDLE, [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
CloseHandle = kernel32.CloseHandle
CloseHandle.argtypes = [w.HANDLE]
IsWindow = user32.IsWindow
IsWindow.argtypes = [w.HWND]


def _mutex_exists(name) -> bool:
    h = OpenMutexW(0x00100000, False, name)
    if h:
        CloseHandle(h)
        return True
    # An app running elevated owns a mutex this process may not open: access denied still means it exists.
    return ctypes.get_last_error() == 5          # ERROR_ACCESS_DENIED


class UpdateError(Exception):
    """A downloaded setup that cannot be used; the text is shown to the user."""


def _update_dir() -> str:
    return os.path.join(DATA_DIR, "updates")


def _clear_updates():
    """Deletes the downloaded setups (best effort: one that is still running stays until next time)."""
    try:
        names = os.listdir(_update_dir())
    except OSError:
        return
    for name in names:
        try:
            os.remove(os.path.join(_update_dir(), name))
        except OSError:
            pass


def _file_sha256(path) -> str | None:
    """The file's SHA-256 in lower-case hex, None when it cannot be read."""
    import hashlib
    if not path:
        return None
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _setup_asset(release, version) -> dict | None:
    """The release's ZOrbitSetup-<version>.exe as {"name", "url", "size", "sha256", "version"}, or None when it has
    none, it is not on this project's releases, or its SHA-256 is not known. The hash comes from GitHub's own digest
    of the file and from the "<sha256>  <name>" line the release notes carry; when both are there they must agree."""
    if not isinstance(release, dict):
        return None
    name = f"ZOrbitSetup-{version}.exe"
    asset = next((a for a in release.get("assets") or [] if isinstance(a, dict) and a.get("name") == name), None)
    if not asset:
        return None
    url, size = asset.get("browser_download_url"), asset.get("size")
    # Without regard to case: GitHub's API spells the repository as it is named (ZOrbit), and treats any spelling alike.
    if not isinstance(url, str) or not url.casefold().startswith(DOWNLOAD_URL.casefold()) or not url.endswith("/" + name):
        return None
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= SETUP_MAX_BYTES:
        return None
    hashes = set()
    digest = asset.get("digest")
    if isinstance(digest, str) and re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        hashes.add(digest[7:].lower())
    body = release.get("body")
    if isinstance(body, str):
        for m in re.finditer(r"^\s*([0-9a-fA-F]{64})\s+\*?" + re.escape(name) + r"\s*$", body, re.M):
            hashes.add(m.group(1).lower())
    if len(hashes) != 1:
        return None
    return {"name": name, "url": url, "size": size, "sha256": hashes.pop(), "version": version}


def _installed_here() -> bool:
    """Whether this is the copy Setup installed (so its setup can update it): a portable copy or a checkout is not."""
    if not paths.FROZEN:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
            app = winreg.QueryValueEx(k, "Inno Setup: App Path")[0]
    except OSError:
        return False
    here = os.path.dirname(os.path.abspath(sys.executable))
    return isinstance(app, str) and os.path.normcase(os.path.abspath(app)) == os.path.normcase(here)


_TLS = []                       # [context or None] once built


def _tls_context():
    """The SSL context for Studio's requests to GitHub. truststore lets Windows check the certificate, as Edge does,
    so a root certificate Windows has not fetched yet (common on a fresh Windows) is fetched instead of failing.
    Python's own check only trusts the roots already in the store. None (Python's default) if truststore is missing."""
    if not _TLS:
        try:
            import ssl
            import truststore
            _TLS.append(truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        except Exception as e:
            _startup(f"truststore unavailable, using Python's certificate check: {e!r}")
            _TLS.append(None)
    return _TLS[0]


def _urlopen(req, timeout):
    import urllib.request
    return urllib.request.urlopen(req, timeout=timeout, context=_tls_context())


def _download_problem(e) -> str:
    """What to tell the user about a failed update download."""
    import urllib.error
    if isinstance(e, UpdateError):
        return str(e)
    if isinstance(e, urllib.error.HTTPError):
        return f"GitHub answered {e.code} for the setup file. Try again later, or download it from GitHub."
    if isinstance(e, OSError) and not isinstance(e, urllib.error.URLError) and getattr(e, "filename", None):
        return f"The setup could not be saved: {e.strerror or e}"
    return "The download did not work. Check your connection and try again."


def _tail(path, n=40):
    """The last n lines of a text file; only its last 64 KB are read, so a huge log costs nothing."""
    try:
        with open(path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - 65536))
            data = f.read()
    except OSError:
        return []
    lines = data.decode("utf-8", errors="replace").splitlines()
    if size > 65536:
        lines = lines[1:]                        # the first line may be cut in half
    return lines[-n:] if n > 0 else []


def _log_since(path, offset, n=8):
    """The last n lines of a text file that were written after its first offset bytes (its size before a launch).
    A file that is now smaller than offset was replaced (rotated): all of it is new."""
    try:
        with open(path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            start = offset if size >= offset else 0
            f.seek(max(start, size - 65536))
            data = f.read()
    except OSError:
        return []
    return data.decode("utf-8", errors="replace").splitlines()[-n:]


def _zbrush_running():
    """(running, check_ok): whether a ZBrush.exe process exists, and whether the process check itself worked."""
    try:
        return bool(W.pids_named("zbrush.exe")), True      # a process snapshot: no tasklist.exe every 3 seconds
    except OSError:
        return False, False


def _png_data_url(im) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=False)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


_look_images = OrderedDict()             # (look json, theme, scale, hover, sample) -> the preview_look dict
_look_images_lock = threading.Lock()


def _look_image(key, make):
    """The cached picture for key, else make() (a dict) stored under it. Oldest first out past LOOK_IMAGES."""
    with _look_images_lock:
        hit = _look_images.get(key)
        if hit is not None:
            _look_images.move_to_end(key)
            return dict(hit)
    out = make()
    with _look_images_lock:
        _look_images[key] = out
        while len(_look_images) > LOOK_IMAGES:
            _look_images.popitem(last=False)
    return dict(out)


def _title_path(p: str) -> str:
    """'TOOL:MASKING:CLEAR' -> 'Tool:Masking:Clear' (ZBrush item paths ignore case)."""
    return ":".join(seg if not seg.isupper() else seg.title() for seg in p.split(":"))


MACRO_MAX_FILES = 500           # .txt files read for macros, across every macro folder
MACRO_MAX_ENTRIES = 2000        # entries listed from one folder, so a huge folder costs a bounded amount
MACRO_READ_BYTES = 65536        # the most of a macro file that is read
_MACRO_BUTTON = re.compile(r"\[\s*ibutton", re.IGNORECASE)


def _macro_txt_files(folder):
    """(files, subfolders) directly in folder, each sorted by name: files as (name without .txt, path) for the .txt
    files, subfolders as (name, path). Both empty when the folder cannot be read."""
    files, subs = [], []
    try:
        with os.scandir(folder) as it:
            entries = []
            for e in it:
                entries.append(e)
                if len(entries) >= MACRO_MAX_ENTRIES:
                    break
            entries.sort(key=lambda e: e.name.lower())
            for e in entries:
                try:
                    if e.is_dir(follow_symlinks=False):
                        subs.append((e.name, e.path))
                    elif e.name.lower().endswith(".txt") and e.is_file():
                        files.append((e.name[:-4], e.path))
                except OSError:
                    continue
    except OSError:
        return [], []
    return files, subs


def _macro_candidates(folders):
    """(label, name, path) for each .txt file in the macro folders. A file directly in a folder has the label
    'Macros'; a file in one of its subfolders has that subfolder's name. Only one level is looked at."""
    for folder in folders:
        top, subs = _macro_txt_files(folder)
        for name, path in top:
            yield "Macros", name, path
        for sub, sub_path in subs:
            if ":" in sub or "," in sub:
                continue                # not a path ZBrush can name
            for name, path in _macro_txt_files(sub_path)[0]:
                yield sub, name, path


def _macro_paths(folders) -> list:
    """Paths such as 'Macro:Misc:Toggle See-Through' for the macros with a button in these folders, sorted by name.
    ZBrush gives a macro a button only when its file has [IButton (one without ran once when ZBrush compiled it),
    so the others are left out. ZBrush goes by the name: the same name in two folders gives one path, capitals do
    not matter, and the first folder wins. At most MACRO_MAX_FILES files are read, and only their first
    MACRO_READ_BYTES. A missing or unreadable folder is skipped."""
    found, read = {}, 0                                 # name key -> (name, path)
    for label, name, path in _macro_candidates(folders):
        key = name.replace(" ", "").lower()             # the same way add() compares paths
        if not name.strip() or ":" in name or "," in name or key in found:
            continue
        if read >= MACRO_MAX_FILES:
            break
        read += 1
        try:
            with open(path, "rb") as f:
                head = f.read(MACRO_READ_BYTES)
        except OSError:
            continue
        if _MACRO_BUTTON.search(head.decode("utf-8", errors="replace")):
            found[key] = (name, f"Macro:{label}:{name}")
    return [path for _, path in sorted(found.values(), key=lambda v: v[0].lower())]


def _retag(cfg: dict, renamed: dict) -> dict:
    """Points the {"tag": key} and {"browser": key} slots of every menu at the local key when an imported tag
    joined a local tag of the same name (renamed = {incoming key: local key}). Changes cfg and returns it."""
    C.retag(cfg, renamed)
    return cfg


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _name_from_file(file_name: str) -> str:
    """A profile name to offer for a settings file: its name without the extension, with what a profile name cannot
    hold turned into spaces and cut to fit. "Imported" when nothing usable is left."""
    stem = os.path.splitext(file_name)[0]
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", stem)
    stem = re.sub(r" {2,}", " ", stem).strip(" .")[:profiles.NAME_MAX].strip(" .")
    return stem if not profiles.valid_name(stem, ()) else "Imported"


class Api(webapi.LibraryApi, webapi.TagApi):
    def __init__(self):
        self._window = None    # underscore: pywebview must not expose (and crawl) it to JS
        self._pending_import = None    # the file pick_import read, until apply_import uses it
        self._pending_menu_import = None    # the same for pick_menu_import and apply_menu_import
        self._dirty = False            # the page's last report of unsaved changes (set_dirty); informational
        self._allow_close = False      # set by close_now(): the next close goes through
        self._ask_sent = 0.0           # when we last asked the page to show the close dialog
        self._ask_acked = True         # whether the page answered that request
        self._session_ending = False   # Windows is shutting down, restarting or signing out: never veto the close
        self._profile = None           # the profile get_config last served, which saves go back to; None before that
        self._pending_profile_file = None    # the file pick_profile_file read, until create_profile uses it
        self._upd_lock = threading.Lock()    # guards _upd and _upd_release
        self._upd_dl = threading.Lock()      # held for the whole of a download
        self._upd_release = None             # _setup_asset() of the newer release check_update last saw
        self._upd = {"state": "idle", "version": "", "done": 0, "total": 0, "message": "", "file": ""}
        try:
            profiles.ensure()
        except OSError as e:
            _startup(f"profiles could not be set up: {e!r}")

    # --- profiles: which files an editor call works on ----------------------------------------------
    def _prof(self, name=None):
        """The profile a call is about: name (as it is spelt on disk), else the one the editor holds, else the
        active one. None for a name that is no profile."""
        return profiles.canonical(name) if name else (self._profile or profiles.active())

    def _cfg_path(self, name=None):
        """radial.json of that profile. Profiles off (a pinned file): that file, whatever the name. A name that is no
        profile gives a path in a folder that never exists, never the active profile's file."""
        if not profiles.enabled():
            return profiles.config_file()
        made = self._prof(name)
        return profiles.config_file(made) if made else os.path.join(profiles.root(), ".missing", "radial.json")

    @staticmethod
    def _too_new(**extra):
        """None normally. When the profile files were made by a newer ZOrbit: {"ok": False, "message", "too_new":
        True} plus extra, which every writing call answers with before it touches anything."""
        msg = profiles.too_new()
        return dict(extra, ok=False, message=msg, too_new=True) if msg else None

    def _tags_path(self):
        return profiles.tags_file(self._prof() if profiles.enabled() else None)

    def _usage_path(self):
        return profiles.usage_file(self._prof() if profiles.enabled() else None)

    def _preview_app(self):
        """An App for the previews, on the files of the profile the editor holds, not of the active one."""
        if profiles.enabled():
            return radiald.App(self._cfg_path(), profile=self._prof())
        return radiald.App(self._cfg_path())

    # --- config ----------------------------------------------------------------------------------
    def _load_dict(self, cfg: dict, store=None):
        """Validates a config dict by loading it through the real loader. Returns (Config, problems).
        store: the TagStore the tag names are checked against; the user's tags when not given."""
        os.makedirs(DATA_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="studio_", suffix=".json", dir=DATA_DIR)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(cfg, f)
            # tag names are checked like the app does
            loaded = C.load(tmp, store or tags.TagStore(self._tags_path()).load(), theme=_theme_now())
            return loaded, loaded.errors
        except Exception as e:
            return None, [f"config could not be read: {e}"]
        finally:
            try:
                os.remove(tmp)
            except OSError:
                pass

    def get_config(self, profile=None):
        """radial.json as the page edits it, with the loader's problems. When the file cannot be read or is
        not a JSON object, config is None and error says why (with line and column when the parser knows),
        so the page can offer to restore the backup or start again instead of failing to open. profile: the one to
        load (the editor's own, else the active one, when not given); it becomes the one saves go back to. Files
        made by a newer ZOrbit are not read: config is None, error is the message and too_new is True."""
        name = self._prof(profile)
        path = profiles.config_file(name if profiles.enabled() else None)
        out = {"config": None, "problems": [], "path": path, "defaults": C.default_ring(_theme_now()), "mtime_ns": None,
               "backup_exists": os.path.isfile(path + ".bak"), "profile": name, "active": profiles.active(),
               "profiles": profiles.names(), "enabled": profiles.enabled()}
        newer = profiles.too_new()
        if newer:                                  # files of a newer ZOrbit: read nothing, pin nothing
            out.update(error=newer, too_new=True)
            return out
        if name is None or (profiles.enabled() and not os.path.isfile(path)):
            out["error"] = f"Profile {name or profile} no longer exists."
            return out
        if name != self._profile:                  # another profile: what was read for the last one is stale
            self._pending_import = self._pending_menu_import = self._pending_profile_file = None
        self._profile = name
        webapi.pin(name if profiles.enabled() else None)
        try:
            mtime_ns = os.stat(path).st_mtime_ns       # before reading: a later change shows as a conflict
            with open(path, encoding="utf-8-sig") as f:
                raw = json.load(f)
        except json.JSONDecodeError as e:
            out["error"] = f"{e.msg} at line {e.lineno}, column {e.colno}"
            return out
        except UnicodeDecodeError as e:
            out["error"] = f"the file is not valid UTF-8 text (bad byte at position {e.start})"
            return out
        except FileNotFoundError:
            out["error"] = "radial.json does not exist"
            return out
        except (OSError, ValueError, RecursionError) as e:
            out["error"] = getattr(e, "strerror", None) or str(e) or "the file could not be read"
            return out
        if not isinstance(raw, dict):
            out["error"] = "the file is not a JSON object"
            return out
        _, problems = self._load_dict(raw)
        out.update(config=raw, problems=problems, mtime_ns=mtime_ns)
        return out

    def validate(self, cfg):
        _, problems = self._load_dict(cfg)
        return {"problems": problems}

    def _missing_profile(self, path, profile):
        """The save_config answer when the profile's folder has gone (deleted from another window), else None."""
        if profiles.enabled() and not os.path.isdir(os.path.dirname(path)):
            name = self._prof(profile) or profile or self._profile
            return {"saved": False, "profile_missing": True,
                    "message": f"Profile {name} no longer exists. Switch to another profile, or make it again."}
        return None

    def save_config(self, cfg, mtime_ns=None, force=False, allow_unusable=False, profile=None):
        """Writes radial.json. The app notices the change within half a second. Saves even with problems (the
        loader draws a bad item as an empty slot) and reports them, but refuses a config no ring can open from unless
        allow_unusable.
        mtime_ns is the file's time when the page loaded it: if the file has changed since, nothing is written
        (conflict) unless force. allow_unusable saves a config no ring can open from. The two flags are separate
        so confirming one warning never skips the other. The previous version is kept as radial.json.bak, only
        when it was valid JSON and differs, so a corrupt or unchanged file never replaces a good backup. A file
        that is not valid JSON is kept as radial.json.broken instead (kept_broken in the result).
        profile: the profile the editor loaded cfg from; it is saved there even if another one is active now. A
        profile that has been deleted since answers profile_missing and nothing is written. Files made by a newer
        ZOrbit are never written: saved is False and too_new is True."""
        newer = self._too_new()
        if newer:
            return {"saved": False, "message": newer["message"], "too_new": True}
        path = self._cfg_path(profile)
        gone = self._missing_profile(path, profile)
        if gone:
            return gone
        if not isinstance(cfg, dict) or not isinstance(cfg.get("menus"), dict):
            return {"saved": False, "message": "The config is not an object with a menus section."}
        exists = os.path.isfile(path)
        if mtime_ns is not None and exists and not force:
            try:
                now_ns = os.stat(path).st_mtime_ns
            except OSError:
                now_ns = None
            try:
                # The page holds this as a JS double (53 bits), which rounds a 1.7e18 ns value by up to ~128 ns,
                # so compare with a 1 microsecond slack. A real edit is never that close to the loaded time.
                changed = now_ns is not None and abs(now_ns - int(mtime_ns)) > 1000
            except (TypeError, ValueError, OverflowError):
                changed = now_ns is not None
            if changed:
                return {"saved": False, "conflict": True, "mtime_ns": now_ns,
                        "message": "radial.json changed on disk since Studio loaded it."}
        loaded, problems = self._load_dict(cfg)
        if not allow_unusable and (loaded is None or not loaded.menus
                                   or not any(m.hotkey for m in loaded.menus.values())):
            return {"saved": False, "blocked": True, "problems": problems,
                    "message": "Saving this would leave the app with no ring that can open."}
        try:
            text = json.dumps(cfg, indent=2, ensure_ascii=False) + "\n"
            data = text.encode("utf-8")                    # before anything is touched: a bad character stops here
        except (UnicodeEncodeError, TypeError, ValueError, RecursionError) as e:
            return {"saved": False, "message": f"Could not save: {e}"}
        kept_broken = False
        try:
            if exists:
                with open(path, "rb") as f:
                    old_bytes = f.read()
                try:
                    old = old_bytes.decode("utf-8-sig")
                    json.loads(old)
                    if old.replace("\r\n", "\n") != text:
                        fsutil.write_atomic(path + ".bak", old_bytes)
                except (ValueError, RecursionError):
                    # Not valid JSON: it never becomes the backup (that stays the last good version), but it is
                    # not lost either. Saved over, it is kept as radial.json.broken.
                    fsutil.write_atomic(path + ".broken", old_bytes)
                    kept_broken = True
            fsutil.write_atomic(path, data)
            st = os.stat(path)
        except OSError as e:
            return {"saved": False, "message": f"radial.json could not be written: {e.strerror or e}"}
        except (UnicodeEncodeError, TypeError, ValueError) as e:
            return {"saved": False, "message": f"Could not save: {e}"}
        self._extras = (0.0, "auto", False)            # Status reads the new bridge mode at once
        return {"saved": True, "problems": problems, "time": time.time(), "mtime_ns": st.st_mtime_ns,
                "kept_broken": kept_broken}

    def restore_backup(self, profile=None):
        """Puts radial.json.bak back as radial.json, if the backup is readable JSON. The backup stays, and the
        radial.json it replaces is first kept as radial.json.broken (unless it is missing or the same). profile: as
        for save_config; the recovery screen gives none and gets the profile the editor holds."""
        newer = self._too_new()
        if newer:
            return newer
        path = self._cfg_path(profile)
        if self._missing_profile(path, profile):
            return {"ok": False, "message": "That profile no longer exists. Switch to another profile."}
        bak = path + ".bak"
        try:
            with open(bak, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            return {"ok": False, "message": "There is no radial.json.bak to restore."}
        except OSError as e:
            return {"ok": False, "message": f"radial.json.bak could not be read: {e.strerror or e}"}
        try:
            if not isinstance(json.loads(data.decode("utf-8-sig")), dict):
                return {"ok": False, "message": "radial.json.bak is not a JSON object, so it was not restored."}
        except ValueError as e:
            return {"ok": False, "message": f"radial.json.bak is not valid JSON ({e}), so it was not restored."}
        kept = False
        try:
            try:
                with open(path, "rb") as f:
                    current = f.read()
            except FileNotFoundError:
                current = None
            if current is not None and current != data:       # what is being replaced is kept, as reset_config does
                fsutil.write_atomic(path + ".broken", current)
                kept = True
            fsutil.write_atomic(path, data)
        except OSError as e:
            return {"ok": False, "message": f"radial.json could not be written: {e.strerror or e}"}
        self._extras = (0.0, "auto", False)
        return {"ok": True, "kept_broken": kept,
                "message": "Restored radial.json from radial.json.bak."
                           + (" The file it replaced is kept as radial.json.broken." if kept else "")}

    def reset_config(self, profile=None):
        """Starts again from the shipped default menus. The file being replaced is first kept as
        radial.json.broken (a previous .broken is overwritten), so nothing is lost. profile: as for restore_backup."""
        newer = self._too_new()
        if newer:
            return newer
        path = self._cfg_path(profile)
        if self._missing_profile(path, profile):
            return {"ok": False, "message": "That profile no longer exists. Switch to another profile."}
        try:
            with open(paths.DEFAULT_MENUS, "rb") as f:
                default = f.read()
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    current = f.read()
                if current != default:
                    fsutil.write_atomic(path + ".broken", current)
            else:
                os.makedirs(os.path.dirname(path), exist_ok=True)
            fsutil.write_atomic(path, default)
        except OSError as e:
            return {"ok": False, "message": f"Could not start again from the defaults: {e.strerror or e}"}
        return {"ok": True, "message": "Started again from the default menus. The old file is kept as "
                                       "radial.json.broken."}

    # --- profiles --------------------------------------------------------------------------------
    def _profile_list(self, **extra):
        """What every profile answer carries, so the page can redraw its list from any of them."""
        return dict(extra, names=profiles.names(), active=profiles.active(), editing=self._profile)

    @staticmethod
    def _need_name(name):
        """An error answer for a name argument that is not a string, else None."""
        if isinstance(name, str):
            return None
        return {"ok": False, "message": "Give the profile a name."}

    def get_profiles(self):
        """The profiles, which one is active and which one the editor holds. Cheap: the page asks on every focus."""
        return self._profile_list(ok=True, enabled=profiles.enabled())

    def switch_profile(self, name):
        """Makes a profile the active one (the app follows within half a second) and returns its config, as
        get_config does, for the editor to load."""
        bad = self._need_name(name)
        if bad:
            return bad
        try:
            profiles.set_active(name)
        except profiles.ProfileError as e:
            return {"ok": False, "message": str(e)}
        self._extras = (0.0, "auto", False)            # Status reads the bridge mode again
        return dict(self.get_config(name), ok=True)

    def pick_profile_file(self):
        """Asks for a settings file to make a profile from, reads and checks it. Writes nothing; create_profile
        with the source "file" makes the profile from what is read here."""
        self._pending_profile_file = None
        found, answer = self._ask_settings_file(need_menus=True)
        if answer:
            return answer
        snap = found["info"].snapshot() if found["info"] is not None else None
        self._pending_profile_file = {"path": found["path"], "config": found["cfg"], "tags": snap}
        return {"ok": True, "path": found["path"], "name": profiles.unique_name(_name_from_file(found["name"])),
                "menus": len(found["cfg"]["menus"]), "has_tags": snap is not None,
                "tags": len(snap["tags"]) if snap else 0, "problems": found["problems"],
                "version": found["version"]}

    def create_profile(self, name, source):
        """Makes a profile. source: "starter", "empty", "copy" (of the active profile) or "file" (the one
        pick_profile_file read). It does not switch to it: the page calls switch_profile."""
        bad = self._need_name(name)
        if bad:
            return bad
        bundle = None
        if source == "file":
            pend = self._pending_profile_file
            if not pend:
                return {"ok": False, "message": "Pick the file first."}
            bundle = {"config": pend["config"], "tags": pend["tags"]}
        try:
            made = profiles.create(name, source, bundle)
        except profiles.ProfileError as e:
            return {"ok": False, "message": str(e)}
        if source == "file":
            self._pending_profile_file = None
        return self._profile_list(ok=True, name=made, message=f"Made the profile {made}.")

    def rename_profile(self, old, new):
        """Renames a profile. The editor follows when it holds that profile."""
        bad = self._need_name(old) or self._need_name(new)
        if bad:
            return bad
        was = profiles.canonical(old)
        try:
            made = profiles.rename(old, new)
        except profiles.ProfileError as e:
            return {"ok": False, "message": str(e)}
        if was is not None and was == self._profile:
            self._profile = made
            webapi.pin(made)
        return self._profile_list(ok=True, name=made, message=f"Renamed {old} to {made}.")

    def delete_profile(self, name):
        """Moves a profile to profiles\\.deleted, where it is kept for 30 days. When the editor held it, reload is
        True: the page then calls get_config() and takes up the active profile."""
        bad = self._need_name(name)
        if bad:
            return bad
        was = profiles.canonical(name)
        try:
            profiles.delete(name)
        except profiles.ProfileError as e:
            return {"ok": False, "message": str(e)}
        reload = was is not None and was == self._profile
        if reload:
            self._profile = None
            webapi.pin(None)
        return self._profile_list(ok=True, reload=reload,
                                  message=f"Deleted {name}. It is kept under profiles\\.deleted for 30 days.")

    # --- files an older ZOrbit left at the old places -----------------------------------------------
    STRAYS_NAME = "From an older version"

    def get_strays(self):
        """What an older ZOrbit left at the old root places, for the page to offer: {"found", "menus", "tags",
        "when", "name"}. menus is the number of menus in the old radial.json and tags the number of tags of its own
        in the old tags.json (Favourites not counted); each is None when that file is not there. found is True when
        either is. name is a profile name to offer. Only reads."""
        found = profiles.strays()
        menus = tag_count = None
        if found["menus"]:
            raw = profiles._read_object(found["menus"]) or {}
            menus = len(raw["menus"]) if isinstance(raw.get("menus"), dict) else 0
        if found["tags"]:
            raw = profiles._read_object(found["tags"]) or {}
            tag_count = len([k for k in tags._parse(raw)[0] if k != tags.FAVOURITE])
        return {"found": menus is not None or tag_count is not None, "menus": menus, "tags": tag_count,
                "when": found["when"], "name": profiles.unique_name(self.STRAYS_NAME)}

    def adopt_strays(self, action, name=""):
        """Deals with the files get_strays reported. action "profile": makes a profile from them (named name, else
        the offered name; it does not switch to it) and sets the files aside; the answer is a profile answer, as
        create_profile gives. action "aside": moves them to pre-profiles\\<time>\\ without making a profile; {"ok",
        "folder"}. Anything that goes wrong is {"ok": False, "message"}."""
        newer = self._too_new()
        if newer:
            return newer
        if action == "profile":
            bad = self._need_name(name) if name else None
            if bad:
                return bad
            try:
                made = profiles.create(name or profiles.unique_name(self.STRAYS_NAME), "strays")
            except profiles.ProfileError as e:
                return {"ok": False, "message": str(e)}
            return self._profile_list(ok=True, name=made, message=f"Made the profile {made}.")
        if action == "aside":
            found = profiles.strays()
            files = [p for p in (found["menus"], found["tags"]) if p]
            if not files:
                return {"ok": False, "message": "There are no files from an older version to set aside."}
            folder = profiles.set_aside(files)
            if not folder:
                return {"ok": False, "message": "The files could not be moved. Close anything that has them open."}
            return {"ok": True, "folder": folder}
        return {"ok": False, "message": "Choose to make a profile or to set the files aside."}

    # --- tags: the store writes tags.json, so Studio refuses first when the files are from a newer ZOrbit.
    # merge_tags stays the plain mixin one (a test pins that); the Studio page cannot reach it past the recovery screen.
    def _tag_refusal(self):
        newer = self._too_new()
        return self._tag_result({"ok": False, "error": newer["message"], "too_new": True}) if newer else None

    def create_tag(self, label, color=None):
        return self._tag_refusal() or super().create_tag(label, color)

    def rename_tag(self, key, label):
        return self._tag_refusal() or super().rename_tag(key, label)

    def recolor_tag(self, key, color):
        return self._tag_refusal() or super().recolor_tag(key, color)

    def delete_tag(self, key):
        return self._tag_refusal() or super().delete_tag(key)

    def set_item_tags(self, item_key, tag_keys):
        return self._tag_refusal() or super().set_item_tags(item_key, tag_keys)

    def tag_items(self, item_keys, add=None, remove=None):
        return self._tag_refusal() or super().tag_items(item_keys, add, remove)

    def set_favourite_order(self, kind, names=None):
        return self._tag_refusal() or super().set_favourite_order(kind, names)

    # --- ring preview ----------------------------------------------------------------------------
    def preview_ring(self, cfg, menu_id, hover=None, scale=1.0, open_path=None):
        """PNG data URL of the ring exactly as the app draws it. hover: item index or None. open_path: item
        indices of the fan submenus to show open ([2], or [2, 1] for a fan inside it). With a fan open the
        image is not square around the ring: width, height and centre (x, y) place the ring in it. menu_id may be
        a "more:<id>" menu (the rest of a paged menu). fit: how the items compare with what the ring holds at its
        radius (see _fit); layout: the renderer's layout map when it gives one, and with a More slot its full also
        says more_items, how many items More opens with."""
        loaded, problems = self._load_dict(cfg)
        paged = isinstance(menu_id, str) and menu_id.startswith(expand.MORE_PREFIX)
        if loaded is None or not isinstance(menu_id, str) or (menu_id not in loaded.menus and not paged):
            return {"image": None, "problems": problems or [f"menu {menu_id!r} has no usable items"]}
        from ring import Ring
        app = self._preview_app()
        app.cfg = loaded
        ex = expand.Expander(loaded, app.usage, app.tags.load())
        menu = ex.resolve(menu_id) if paged else ex.menu(loaded.menus[menu_id])   # as the app would fill it now
        if menu is None:
            return {"image": None, "problems": problems or [f"menu {menu_id!r} has no usable items"]}
        count = len(ex._whole(menu_id).items) if paged else len(loaded.menus[menu_id].items)
        im = Ring.preview(menu, loaded.ring, app.icon_for, hover=hover, scale=float(scale),
                          submenus=ex.resolve,
                          open_path=[int(i) for i in open_path] if open_path else None)
        out = self._ring_result(im, problems)
        out["fit"] = self._fit(menu.look or loaded.ring, menu.fan, count)
        full = out.get("layout", {}).get("full")
        if full and full.get("more_slot") is not None:
            full["more_items"] = len(ex._whole(expand.MORE_PREFIX + menu_id).items)
        return out

    @staticmethod
    def _ring_result(im, problems):
        """The common part of the ring previews: the picture, its size, where the ring's centre is, the layout map."""
        cx, cy = im.info.get("centre", (im.size[0] / 2, im.size[1] / 2))
        out = {"image": _png_data_url(im), "size": im.size[0], "width": im.size[0], "height": im.size[1],
               "centre": [cx, cy], "problems": problems}
        if im.info.get("layout") is not None:
            out["layout"] = im.info["layout"]
        return out

    @staticmethod
    def _fit(look, fan, count):
        """How many items a ring of this look holds at its radius against how many the menu has: {"items",
        "capacity", "needed_radius", "full", "when_full"}; None for a fan (it is not laid out as a ring)."""
        if fan:
            return None
        k = expand._capacity(look.get("radius", 145), look.get("slot", 72))
        return {"items": count, "capacity": k, "needed_radius": expand.needed_radius(count, look.get("slot", 72)),
                "full": count > k, "when_full": look.get("when_full", "grow")}

    def _sample_menu(self, loaded, app, mid="sample", look=None):
        """The ring the look previews draw: SAMPLE_SLOTS - 1 brushes (the user's tagged ones first, then others from
        the library, else fixed names) and a submenu slot. The brushes carry the user's tag colours, two slots
        to a tag, so every tag setting shows even when no menu has a tagged brush; the submenu slot is plain.
        look: the resolved look the menu is drawn with (None: the ring's own)."""
        store = app.tags.load()
        listed = assets.names("brush")
        index = {k.replace(" ", ""): (listed.get(k) or p.stem) for k, p in brushes.brush_index().items()}
        names = []
        for ik in store.tagged("brush"):
            if ik.split(":", 1)[1] in index:
                names.append(index[ik.split(":", 1)[1]])
        for n in index.values():
            if len(names) >= SAMPLE_SLOTS - 1:
                break
            if n not in names:
                names.append(n)
        names = (names or list(SAMPLE_BRUSHES))[:SAMPLE_SLOTS - 1]
        colors = [t["color"] for t in store.tags()] or [tags.PALETTE[0]]
        items = [C.Item(label=n, kind="brush", data={"brush": n},
                        color=store.color_of_item(tags.item_key("brush", n)) or colors[(i // 2) % len(colors)])
                 for i, n in enumerate(names)]
        items.append(C.Item(label="Sculpt", kind="menu", data={"menu": "sample_sub"}))
        return C.Menu(id=mid, title="Sample", items=items, look=look)

    def preview_tags(self, cfg, hover=None, scale=1.0, menu_id=None):
        """preview_ring of a sample ring for the tag colour settings (see _sample_menu). menu_id: a menu of cfg
        whose look the sample is drawn with, else the ring's."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None:
            return {"image": None, "problems": problems}
        from ring import Ring
        app = self._preview_app()
        app.cfg = loaded
        mine = loaded.menus.get(menu_id) if isinstance(menu_id, str) else None
        menu = self._sample_menu(loaded, app, look=mine.look if mine is not None else None)
        im = Ring.preview(menu, loaded.ring, app.icon_for, hover=hover, scale=float(scale))
        return self._ring_result(im, problems)

    # --- looks: the previews and the numbers behind the Look screen ------------------------------
    def _look_spec(self, loaded, preset, look, base, problems):
        """The look_spec ({"preset": name or "", **keys}) that preview_look draws: the preset and the raw look keys
        over the base ("global", or the id of a menu whose own look keys stay)."""
        spec = {}
        if isinstance(base, str) and base not in ("global", "default"):
            if base in loaded.menus:
                spec = dict(loaded.menus[base].look_spec)
            else:
                problems.append(f"menu {base!r} not found; using the ring's look")
        if preset:
            if isinstance(preset, str) and loaded.looks.preset(preset) is not None:
                spec["preset"] = preset
            else:
                problems.append(f"look {preset!r} unknown")
        if isinstance(look, dict):
            errors = []
            spec.update(L.check_look({k: v for k, v in look.items() if k != "preset"}, errors, "look.", L.LOOK_KEYS))
            problems.extend(errors)
        spec.setdefault("preset", "")
        return spec

    @staticmethod
    def _resolver(loaded, base):
        """The LookSet a look picture is resolved with. base "default": the defaults and the theme only, so the
        picture shows the look itself and does not change with the user's own ring settings; otherwise the loaded
        config's (the ring's look and settings under it)."""
        if base == "default":
            return L.LookSet(user=loaded.looks.user, ring={}, theme=loaded.looks.theme)
        return loaded.looks

    def _render_look(self, loaded, app, sample, spec, mid, hover, scale, looks=None):
        """One look picture: {"image", "size", "width", "height", "centre"} of the sample ring drawn with the
        look the spec resolves to (with looks, a LookSet, else the loaded config's). Pictures are kept for the
        next call with the same look, theme and size."""
        from ring import Ring
        import dataclasses
        resolved = (looks or loaded.looks).menu_look(spec)
        sig = tuple((it.label, it.kind, it.color) for it in sample.items)
        hover = tuple(hover) if isinstance(hover, (list, tuple)) else hover
        key = (json.dumps(resolved, sort_keys=True), resolved.get("theme", "dark"), round(float(scale), 3), hover, sig)

        def make():
            menu = dataclasses.replace(sample, id=mid, look=resolved)
            im = Ring.preview(menu, loaded.ring, app.icon_for, hover=hover, scale=float(scale))
            out = self._ring_result(im, [])
            del out["problems"]
            return out

        return _look_image(key, make)

    def preview_look(self, cfg, preset=None, look=None, base="global", hover=None, scale=0.5):
        """The sample ring drawn with a look: preset (a built-in or user look name) and/or look (a raw dict of look
        keys) laid over base ("global": the ring's look; "default": the defaults and the theme only; or a menu id:
        that menu's own look keys stay). Returns
        {"image", "size", "width", "height", "centre", "problems"}."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None:
            return {"image": None, "problems": problems}
        app = self._preview_app()
        app.cfg = loaded
        sample = self._sample_menu(loaded, app)
        spec = self._look_spec(loaded, preset, look, base, problems)
        live = isinstance(look, dict) and bool(look)
        mid = "preset:" + (spec["preset"] or "~live") + ("~live" if live and spec["preset"] else "")
        if isinstance(base, str) and base in loaded.menus:
            mid += "@" + base
        if base == "default":
            mid += "~default"
        out = self._render_look(loaded, app, sample, spec, mid, hover, scale, self._resolver(loaded, base))
        out["problems"] = problems
        return out

    def preview_looks(self, cfg, names=None, base="global", scale=0.5):
        """preview_look for several looks at once, for the gallery: {"looks": {name: {"image", "size", "width",
        "height", "centre"}}, "problems"}. names: the looks to draw (the built-in ones and the user's when not
        given); a name that is no look is left out and reported. base as for preview_look; the gallery uses
        "default", so a card shows the look itself and only changes with the theme, the tags or that look."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None:
            return {"looks": {}, "problems": problems}
        app = self._preview_app()
        app.cfg = loaded
        sample = self._sample_menu(loaded, app)
        out, notes = {}, []
        looks = self._resolver(loaded, base)
        for name in (loaded.looks.names() if names is None else names):
            spec = self._look_spec(loaded, name, None, base, notes)
            if not spec["preset"]:
                continue
            mid = "preset:" + name + ("~default" if base == "default" else "")
            out[name] = self._render_look(loaded, app, sample, spec, mid, None, scale, looks)
        return {"looks": out, "problems": problems + list(dict.fromkeys(notes))}

    def resolve_look(self, cfg, menu_id=None, slot=None):
        """The look at one level of cfg, with where each value comes from. No menu_id: the ring's look; a menu_id: that
        menu's; a slot as well (an index into the menu's items in radial.json): that slot's, its style over the
        menu's. Returns {"values": the resolved look (roles as #rrggbb), "origins": {key: {"from": default | theme |
        global-preset | global | menu-preset | menu | slot, "name": the preset's name for the two preset origins},
        colours as "colors.accent"}, "preset": {"name", "builtin"} of the preset set at that level or None,
        "fit": {"items", "capacity", "needed_radius", "full", "when_full"} for a menu (None otherwise, and for a
        fan), "problems": the loader's}."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None:
            return {"values": {}, "origins": {}, "preset": None, "fit": None, "problems": problems}
        menu = loaded.menus.get(menu_id) if isinstance(menu_id, str) else None
        if menu_id is not None and menu is None:
            problems = problems + [f"menu {menu_id!r} not found"]
        if menu is None:
            name = loaded.looks.ring.get("look") or ""
            res = loaded.looks.explain()
            fit = None
        else:
            style = None
            raw_items = (cfg.get("menus") or {}).get(menu_id, {}).get("items") if isinstance(cfg, dict) else None
            if isinstance(slot, int) and not isinstance(slot, bool) and isinstance(raw_items, list) \
                    and 0 <= slot < len(raw_items):
                raw = raw_items[slot].get("style") if isinstance(raw_items[slot], dict) else None
                style = L.check_style(raw, [], "") if raw is not None else {}
            res = loaded.looks.explain(menu.look_spec, style)
            name = (menu.look_spec.get("preset") or "") if style is None else ""
            fit = self._fit(menu.look or loaded.ring, menu.fan, len(menu.items))
        preset = {"name": name, "builtin": name in L.BUILTIN} if name and loaded.looks.preset(name) is not None else None
        return {"values": res["values"], "origins": res["origins"], "preset": preset, "fit": fit,
                "problems": problems}

    def preview_animation(self, cfg, menu_id, fps=30, ring_anim=False):
        """Open-animation frames as PNG data URLs (played back by the Studio), plus the frame interval.
        ring_anim: play ring.animation even if the menu has its own (the Settings screen)."""
        loaded, problems = self._load_dict(cfg)
        if loaded is None or menu_id not in loaded.menus:
            return {"frames": [], "interval_ms": 33, "problems": problems}
        import dataclasses
        from ring import Ring
        app = self._preview_app()
        app.cfg = loaded
        ex = expand.Expander(loaded, app.usage, app.tags.load())
        menu = ex.menu(loaded.menus[menu_id])
        if ring_anim:
            menu = dataclasses.replace(menu, animation="")
        frames = Ring.preview_frames(menu, loaded.ring, app.icon_for, fps=int(fps), submenus=ex.resolve)
        return {"frames": [_png_data_url(f) for f in frames], "interval_ms": round(1000 / int(fps)),
                "problems": problems}

    def get_auto_slots(self, cfg, menu_id):
        """The brushes the app would put into the menu's auto slots now, in order (None: empty)."""
        loaded, _ = self._load_dict(cfg)
        if loaded is None or menu_id not in loaded.menus:
            return {"slots": []}
        import usage
        return {"slots": usage.Usage(self._usage_path()).load().slots(loaded.menus[menu_id])}

    # the look keys by group, in the order the Look screen shows them; "full" keys are left out of the Simple mode
    _LOOK_GROUPS = (
        ("Slots", ("radius", "slot", "dead_zone", "slot_shape", "slot_corner", "border_width", "icon_scale", "size",
                   "fill_color", "border_color")),
        ("Hub", ("hub", "hub_style", "hub_color", "hub_glow")),
        ("Glow", ("glow_color", "glow_opacity")),
        ("Labels", ("labels", "label_color")),
        ("Colours", ("colors",)),
        ("Tag colours", ("tag_colors", "tag_band", "tag_band_opacity", "tag_glow_opacity", "tag_tint_opacity",
                         "tag_tint_style", "tag_tint_blend")),
        ("When full", ("when_full",)))
    _SIMPLE_LOOK_KEYS = ("radius", "slot", "dead_zone", "slot_shape", "labels", "when_full")

    def _look_options(self):
        """get_options()["looks"]: what the Look screen builds its controls from (see get_options)."""
        ring = C.default_ring(_theme_now())
        defaults = {**L.STYLE_DEFAULTS, **{k: ring[k] for k in L.LOOK_KEYS if k in ring}}
        schema = {}
        for group, keys in self._LOOK_GROUPS:
            for k in keys:
                spec = {"group": group, "default": defaults.get(k), "full": k not in self._SIMPLE_LOOK_KEYS}
                if k == "colors":
                    spec.update(kind="colors", choices=list(L.ROLES))
                elif k in L.COLOUR_KEYS:
                    spec.update(kind="colour", allow_empty=k in L.EMPTY_COLOUR_KEYS)
                elif k in L.RANGES:
                    spec.update(kind="range", min=L.RANGES[k][0], max=L.RANGES[k][1])
                else:
                    spec.update(kind="choice", choices=list(L.CHOICES[k]))
                spec["levels"] = ["slot"] if k in L.STYLE_DEFAULTS else \
                    ["global", "menu"] + (["slot"] if k in L.STYLE_KEYS else [])
                schema[k] = spec
        return {"schema": schema, "roles": list(L.ROLES),
                "builtin": [{"id": k, "label": v["label"], "blurb": v["blurb"], "look": dict(v["look"])}
                            for k, v in L.BUILTIN.items()],
                "reserved": sorted(L.RESERVED_MENU_IDS), "menu_prefixes": ["tag:", "more:", "recent:"],
                "name": {"max": 32, "pattern": r"^[\p{L}\p{N}_](?:[\p{L}\p{N}_ -]{0,30}[\p{L}\p{N}_])?$",
                         "flags": "u"}}

    def get_options(self):
        """Choices the UI offers: animation modes, label modes, action kinds, defaults. "looks" describes the look
        keys (schema: per key its group, kind range | choice | colour | colors, min and max, choices, default, the
        levels it can be set at and whether it is shown in Full mode only), the theme roles, the built-in looks,
        the reserved names and what a look's name may be."""
        return {"looks": self._look_options(), "hub_styles": list(L.HUB_STYLES), "when_full": list(L.WHEN_FULL),
                "animations": list(C.ANIMATIONS), "labels": list(C.LABEL_MODES), "actions": list(C.ACTION_KEYS),
                "asset_kinds": list(C.ASSET_KINDS), "tag_colors": list(C.TAG_COLOR_MODES),
                "tag_bands": list(C.TAG_BANDS), "favourite_tag": tags.FAVOURITE,
                "tint_styles": list(C.TINT_STYLES), "tint_blends": list(C.TINT_BLENDS),
                "slot_shapes": list(C.SLOT_SHAPES), "ring_defaults": C.default_ring(_theme_now()),
                "ring_ranges": C._RING_RANGES, "themes": list(theme.NAMES),
                "theme_ring_colors": {n: theme.ring_colors(n) for n in theme.CONCRETE
                                      + (("zbrush",) if theme.effective("zbrush") == "zbrush" else ())}}

    # --- suggestions for press/set/toggle targets ------------------------------------------------
    def get_suggestions(self):
        sug, seen = [], set()

        def add(path, source):
            k = path.replace(" ", "").lower()
            if k not in seen:
                seen.add(k)
                sug.append({"path": path, "source": source})
        ua = brushes.zbrush_dirs().get("user_assets")
        if ua:
            hk = os.path.join(str(ua), "ZStartup", "HotKeys", "StartupHotkeys.txt")
            for line in _tail(hk, 10000):
                m = re.match(r"\s*\[([^,\]]+),\d+\]\s*(?://\s*(.*))?", line)
                if m and not m.group(1).upper().startswith(("BRUSH:", "CM")):
                    note = (m.group(2) or "").strip()
                    add(_title_path(m.group(1)), f"your hotkeys ({note})" if note else "your hotkeys")
        for p in ("Tool:Masking:Clear", "Tool:Masking:Inverse", "Tool:Masking:ViewMask", "Transform:Activate Symmetry",
                  "Transform:Pf", "Transform:Solo", "Tool:Geometry:Divide", "Tool:Geometry:Lower Res",
                  "Tool:Geometry:Higher Res", "Draw:Draw Size", "Draw:Z Intensity", "Stroke:LazyMouse",
                  "Stroke:SubDivide Size", "Brush:Auto Masking:BackfaceMask", "Tool:Polygroups:Auto Groups"):
            add(p, "common")
        folders = []                                    # where ZBrush 2026 and newer keep macros, and 2022 to 2025
        try:
            for e in self._all_installs():
                if e.get("python"):
                    folders.append(os.path.join(e["path"], "ZData", "Macros"))
                    if ua:
                        folders.append(os.path.join(str(ua), "ZStartup", "Macros"))
                else:
                    folders.append(os.path.join(e["path"], "ZStartup", "Macros"))
        except OSError:
            folders = []
        for p in _macro_paths(list(dict.fromkeys(folders))):
            add(p, "macro")
        return sug

    # --- app status / control --------------------------------------------------------------------
    _extras = (0.0, "auto", False)             # (checked at, bridge_mode, legacy_only): the slow bits, refreshed every 30 s

    def _status_extras(self):
        """bridge_mode from the saved config and whether only a ZBrush 2022 to 2025 is installed. Both need file
        reads and an install scan, so they are cached: the status polls every 3 s and they change rarely."""
        at, mode, legacy = self._extras
        if time.monotonic() - at < 30:
            return mode, legacy
        try:
            mode = C.load(profiles.config_file()).bridge_mode
        except Exception:
            mode = "auto"
        if mode not in ("auto", "message", "key"):
            mode = "auto"
        try:
            found = installs.find_installs()
            legacy = (not any(e["python"] for e in found)) and any(
                e["year"] and 2022 <= e["year"] <= 2025 for e in found)
        except Exception:
            legacy = False
        self._extras = (time.monotonic(), mode, legacy)
        return mode, legacy

    def _listener_info(self):
        """listener.json as {verified (when, epoch seconds, or None), alive (its window exists), pid (the ZBrush
        that wrote it), hwnd}, or None when there is no readable file. The file outlives a ZBrush that crashed,
        so 'alive' only says the window handle is still valid."""
        try:
            with open(os.path.join(DATA_DIR, "listener.json"), encoding="utf-8") as f:
                info = json.load(f)
            hwnd = int(info["hwnd"])
            verified, pid = info.get("verified"), info.get("pid")
            return {"verified": float(verified) if isinstance(verified, (int, float)) and verified else None,
                    "alive": bool(IsWindow(hwnd)), "pid": pid if isinstance(pid, int) else None, "hwnd": hwnd}
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _last_pick_info(self):
        """The last pick ZBrush carried out, from bridge.log (2026+) or zscript_bridge.log (2022-2025, only the
        last pick): {text (the log line, as the Status screen shows it), at (epoch seconds), seq, ok, source
        ('bridge' or 'zscript')}, or None. ok is False when ZBrush reported a problem with it."""
        bridge_log = os.path.join(DATA_DIR, "bridge.log")
        picks = [l for l in _tail(bridge_log, 200) if " #" in l]
        source, mtime = "bridge", None
        zs_log = os.path.join(DATA_DIR, "zscript_bridge.log")
        try:
            if not picks or os.path.getmtime(zs_log) > os.path.getmtime(bridge_log):
                zs = _tail(zs_log, 1)
                if zs:
                    mtime = os.path.getmtime(zs_log)
                    when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
                    picks.append(f"{when} {zs[0]} (ZScript bridge)")
                    source = "zscript"
        except OSError:
            pass
        if not picks:
            return None
        text = picks[-1]
        try:
            at = time.mktime(time.strptime(text[:19], "%Y-%m-%d %H:%M:%S"))      # log lines start with the time
        except (ValueError, OverflowError):
            at = mtime
            if at is None:
                try:
                    at = os.path.getmtime(bridge_log)
                except OSError:
                    at = time.time()
        m = re.search(r"#(\d+)", text)
        ok = not any(bad in text for bad in ("FAILED", "NOT loaded", "no such interface item"))
        return {"text": text, "at": at, "seq": int(m.group(1)) if m else None, "ok": ok, "source": source}

    @staticmethod
    def _running_version():
        """The version of the app running now, as a string, or None when none runs or it cannot be told."""
        try:
            found = W.running_app()
        except Exception as e:                     # a window that vanishes mid-read must not break Status
            _startup(f"running_app failed: {e!r}")
            return None
        ver = found[2] if found else None
        return ver if isinstance(ver, str) and paths.version_key(ver) else None

    @staticmethod
    def _older_than_studio(ver) -> bool:
        """True when ver is a version older than this Studio. False when either is unknown."""
        theirs, mine = paths.version_key(ver), paths.version_key(VERSION)
        return theirs is not None and mine is not None and theirs < mine

    # --- Copy report ------------------------------------------------------------------------------
    @staticmethod
    def _windows_version():
        return f"Windows {platform.release()} (build {sys.getwindowsversion().build})"

    def _report_zbrush(self):
        """(every ZBrush known, with a running one the scan missed, and the running ones for report.zbrush_lines). A
        process whose image cannot be read is one running as administrator, as on the Setup screen."""
        known = list(self._all_installs())
        seen = {os.path.normcase(e["path"]) for e in known}
        procs = []
        for pid in W.pids_named("zbrush.exe"):
            image = W.process_image(pid)
            e = installs.install_of(image) if image else None
            elevated = W.process_elevated(pid) if image else True
            if e and os.path.normcase(e["path"]) not in seen:
                seen.add(os.path.normcase(e["path"]))
                known.append(e)
            procs.append({"pid": pid, "path": e["path"] if e else None, "year": e.get("year") if e else None,
                          "admin": "yes" if elevated else "no" if elevated is False else "cannot tell"})
        return known, procs

    @staticmethod
    def _report_menus():
        """(bridge mode, bridge key, problems) of the menus file the app uses."""
        newer = profiles.too_new()
        if newer:
            return "not read", "not read", [newer]
        store = tags.TagStore(profiles.tags_file(profiles.active() if profiles.enabled() else None)).load()
        cfg = C.load(profiles.config_file(), store, theme=_theme_now())
        return cfg.bridge_mode, cfg.bridge_key.text, list(cfg.errors)

    def get_bug_url(self):
        """The bug form with its version fields filled in."""
        try:
            known, procs = self._report_zbrush()
            years = [p["year"] for p in procs if p["year"]] or [e["year"] for e in known if e.get("year")]
        except Exception as e:
            _startup(f"get_bug_url: no ZBrush version: {e!r}")
            years = []
        return report.bug_url(VERSION, str(max(years)) if years else "", self._windows_version())

    def get_report(self, cards=None):
        """The text of Copy report, with the user name and folders hidden. cards: [[title, text]], the Status cards as
        the screen shows them. A part that cannot be read says so; the others still go in."""
        def part(fn, fallback):
            try:
                return fn()
            except Exception as e:
                _startup(f"get_report: {fn.__name__}: {e!r}")
                return fallback(e)
        clean = report.current_redactor()
        known, procs = part(self._report_zbrush, lambda e: ([], []))
        mode, key, problems = part(self._report_menus, lambda e: ("unknown", "unknown", [f"could not be read: {e!r}"]))
        kind = "Setup" if _installed_here() else "portable" if paths.FROZEN else "source"
        facts = [("ZOrbit", f"{VERSION} ({kind})"), ("Windows", self._windows_version()),
                 ("App running", part(self._running_version, lambda e: None) or "none"),
                 ("Profile in use", profiles.active() if profiles.enabled() else "none (one pinned menus file)"),
                 ("Bridge mode", mode), ("Bridge key", key)]
        shown = [f"{c[0]}: {c[1]}"[:report.LINE_CHARS] for c in (cards if isinstance(cards, list) else [])[:8]
                 if isinstance(c, list) and len(c) == 2 and all(isinstance(x, str) for x in c)]
        modern, legacy = any(e.get("python") for e in known), any(not e.get("python") for e in known)
        library = part(lambda: report.library_folder_lines(self.get_library_folders()["folders"]),
                       lambda e: [f"could not be read: {e!r}"])
        sections = [("ZBrush", report.zbrush_lines(known, procs)), ("Library folders", library),
                    ("Status cards", shown or ["(not shown yet)"]),
                    ("Problems in the menus file", problems or ["none"])]
        sections += report.log_sections(DATA_DIR, modern, legacy, clean)
        return {"ok": True, "text": report.build(facts, sections, clean)}

    def get_status(self):
        info = self._listener_info()
        listener = {"verified": bool(info["verified"]), "alive": info["alive"]} if info else None
        pick = self._last_pick_info()
        app_log = _tail(os.path.join(DATA_DIR, "radiald.log"), 40)
        zbrush_running, check_ok = _zbrush_running()
        bridge_mode, legacy_only = self._status_extras()
        app_version = self._running_version()
        return {"app_running": _mutex_exists(APP_MUTEX), "zbrush_running": zbrush_running,
                "app_version": app_version, "app_older": self._older_than_studio(app_version),
                "listener": listener, "last_pick": pick["text"] if pick else None, "app_log": app_log,
                "data_dir": DATA_DIR, "bridge_mode": bridge_mode, "legacy_only": legacy_only,
                "checked_at": time.time(), "zbrush_check_ok": check_ok}

    def start_app(self):
        """Starts the app. One that runs already is left alone, unless it is older than this Studio: then the
        new one is started anyway (it takes the place of the old one itself) and this waits for the running version
        to become this one. {"ok", "running", "message"}, plus restarted and was when an older app made way."""
        was = None
        if _mutex_exists(APP_MUTEX):
            was = self._running_version()
            if not self._older_than_studio(was):
                return {"ok": True, "running": True, "message": "The app is already running."}
        zb_running, zb_checked = _zbrush_running()
        if zb_checked and not zb_running:                  # a failed check is not "not running": let the launch try
            return {"ok": False, "running": False, "reason": "zbrush",
                    "message": "ZBrush is not running. The app starts together with ZBrush."}
        app_log = os.path.join(DATA_DIR, "radiald.log")
        try:
            log_before = os.path.getsize(app_log)
        except OSError:
            log_before = 0
        p = subprocess.Popen(paths.launch_commands()["app"], cwd=os.path.dirname(paths.PKG_DIR),
                             env=paths.clean_env(), creationflags=0x00000008 | 0x00000200, close_fds=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + START_WAIT
        if was:
            while time.monotonic() < deadline and self._running_version() != VERSION:
                if p.poll() is not None:
                    break
                time.sleep(0.2)
            if self._running_version() == VERSION:
                return {"ok": True, "running": True, "restarted": True, "was": was,
                        "message": f"Started the new app. It took the place of version {was}."}
            return {"ok": False, "running": True, "reason": "older", "was": was,
                    "message": "The older app did not make way. Quit it from its tray icon and press Start app "
                               "again."}
        while time.monotonic() < deadline:
            if _mutex_exists(APP_MUTEX):
                return {"ok": True, "running": True, "message": "Started."}
            if p.poll() is not None:
                break
            time.sleep(0.2)
        if _mutex_exists(APP_MUTEX):
            return {"ok": True, "running": True, "message": "Started."}
        if p.poll() is None:                    # still alive: slow, not failed (a first start is scanned by Windows)
            return {"ok": False, "running": False, "starting": True,
                    "message": "The app is still starting (a first start can take a few seconds while Windows "
                               "scans it). Status turns green when it is up."}
        lines = _log_since(app_log, log_before)      # only what this launch wrote, not an earlier run's lines
        return {"ok": False, "running": False, "reason": "failed", "lines": lines, "log": lines,
                "message": "The app did not start." + (" The last lines of its log:" if lines else
                                                       " It wrote nothing to its log.")}

    # --- ZScript bridge for ZBrush 2022-2025 -----------------------------------------------------
    _scan = (0.0, [])                          # (when, installs.find_installs()): Setup asks every second or so

    def _scanned_installs(self):
        """installs.find_installs(), kept for a few seconds (it reads the registry and lists folders)."""
        at, found = self._scan
        if not at or time.monotonic() - at >= 5:
            found = installs.find_installs()
            self._scan = (time.monotonic(), found)
        return list(found)

    def _all_installs(self):
        """Every ZBrush installation: found ones plus folders the user added."""
        found = self._scanned_installs()
        seen = {os.path.normcase(e["path"]) for e in found}
        found = [dict(e, added=False) for e in found]
        for p in _read_studio_file().get("zbrush_folders", []):
            e = installs.entry(p) if isinstance(p, str) else None
            if e and os.path.normcase(e["path"]) not in seen:
                seen.add(os.path.normcase(e["path"]))
                found.append(dict(e, added=True))        # added by hand: the page offers to forget these
        return found

    def _legacy_installs(self):
        """ZBrush installations without the Python API (2022-2025)."""
        return [e for e in self._all_installs() if not e["python"]]

    def get_zscript_bridge(self):
        rows = [dict(e, **zscript_bridge.status(e["path"])) for e in self._legacy_installs()]
        return {"installs": rows, "bundled": bool(zscript_bridge.bundled())}

    # --- Setup screen ----------------------------------------------------------------------------
    def get_setup(self):
        """Everything the Setup screen shows, read fresh each call (the installs scan and the process list are
        cheap). When the check itself fails the answer is only {now, checked_at, failed: True, error}: no installs
        list, which the page could take for 'nothing found'. The traceback goes to studio.log."""
        try:
            mode, _ = self._status_extras()
            return onboarding.snapshot(self._all_installs(), self._listener_info(), self._last_pick_info(), mode,
                                       bool(zscript_bridge.bundled()), app_running=_mutex_exists(APP_MUTEX))
        except Exception as e:
            if getattr(self, "_setup_err", None) != repr(e):          # polled every second: log a repeat once
                self._setup_err = repr(e)
                import traceback
                _startup("get_setup failed:\n" + traceback.format_exc().rstrip())
            # Deliberately nothing else: an empty installs list would read as "no ZBrush found". The page shows
            # the error and keeps whatever it showed before.
            return {"now": time.time(), "checked_at": time.time(), "failed": True,
                    "error": f"The setup check failed: {e} (see studio.log)"}

    def register_plugin_path(self):
        """Adds this build's bridge folder to the user's ZBRUSH_PLUGIN_PATH. Takes no argument on purpose: the
        folder is always the one this installation ships, never something the page sends."""
        d = paths.bridge_dir()
        if not d or not os.path.isfile(os.path.join(d, "zorbit_bridge.py")):
            return {"ok": False, "changed": False, "message": "The plugin folder is missing. Reinstall ZOrbit.",
                    "restart": True}
        return dict(onboarding.register_plugin_path(d), restart=True)

    def _known_legacy(self, path):
        """The ZBrush 2022-2025 installation at this folder, or None. The scan and the added folders are looked at
        first; a folder neither knows (a ZBrush found only by its running process) is checked directly. Anything
        that is not a ZBrush folder without the Python API, or is older than 2022, is refused."""
        if not isinstance(path, str) or not path.strip():
            return None
        for e in self._legacy_installs():
            if os.path.normcase(e["path"]) == os.path.normcase(os.path.normpath(path)):
                return e
        e = installs.entry(path)
        if e and not e["python"] and e["supported"] and (e["year"] is None or e["year"] <= 2025):
            return e
        return None

    def install_zscript_bridge(self, path):
        """Copies the plugin into that ZBrush (asks for administrator rights when the folder needs them)."""
        if self._known_legacy(path) is None:
            return {"ok": False, "message": "That folder is not a ZBrush 2022-2025 installation."}
        return zscript_bridge.install(path)

    def remove_zscript_bridge(self, path):
        if self._known_legacy(path) is None:
            return {"ok": False, "message": "That folder is not a ZBrush 2022-2025 installation."}
        return zscript_bridge.remove(path)

    def choose_folder(self):
        """Folder picker for a capture item's folder: the chosen path as text, or None when cancelled."""
        import webview
        picked = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not picked:
            return None
        return str(picked[0] if isinstance(picked, (list, tuple)) else picked)

    def choose_file(self, kind):
        """File picker for a Tool, a Project or a Layout item: the chosen path as text, or None when cancelled or the kind
        is not one of those three."""
        import webview
        if kind not in ("tool", "project", "layout"):                  # a tuple, so an odd value from the page never raises here
            return None
        filters = {"tool": ("ZBrush tool (*.ztl)",), "project": ("ZBrush project (*.zpr)",),
                   "layout": ("ZBrush UI layout (*.cfg)",)}
        picked = self._window.create_file_dialog(webview.FileDialog.OPEN, file_types=filters[kind])
        if not picked:
            return None
        return str(picked[0] if isinstance(picked, (list, tuple)) else picked)

    def add_zbrush_folder(self):
        """Folder picker for a ZBrush that was not found automatically; remembered in studio.json."""
        import webview
        picked = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        if not picked:
            return {"ok": False, "cancelled": True}
        folder = picked[0] if isinstance(picked, (list, tuple)) else picked
        for cand in (folder, os.path.dirname(folder), os.path.dirname(os.path.dirname(folder))):
            e = installs.entry(cand)                 # also accepts ZStartup or ZPlugs64 picked by mistake
            if e:
                break
        if not e:
            return {"ok": False, "message": "No ZBrush.exe in that folder."}
        if os.path.normcase(e["path"]) in {os.path.normcase(x["path"]) for x in self._all_installs()}:
            return {"ok": True, "message": f"{e['name']} is already listed.", "already": True,
                    "python": e["python"]}
        with _studio_lock:                     # read, change and write as one step
            data = _studio_for_update()
            if data is None:
                return {"ok": False, "message": STUDIO_UNREADABLE}
            folders = [p for p in data.get("zbrush_folders", []) if isinstance(p, str)]
            if os.path.normcase(e["path"]) not in {os.path.normcase(p) for p in folders}:
                folders.append(e["path"])
            data["zbrush_folders"] = folders
            _write_studio_file(data)
        return {"ok": True, "python": e["python"], "message": f"Added {e['name']}."}

    def forget_zbrush_folder(self, path):
        """Drops a folder added by hand from studio.json (never an automatically found one)."""
        key = os.path.normcase(os.path.normpath(str(path)))
        with _studio_lock:                     # read, change and write as one step
            data = _studio_for_update()
            if data is None:
                return {"ok": False, "message": STUDIO_UNREADABLE}
            folders = [p for p in data.get("zbrush_folders", []) if isinstance(p, str)]
            kept = [p for p in folders if os.path.normcase(os.path.normpath(p)) != key]
            if len(kept) == len(folders):
                return {"ok": False, "message": "That folder was not added by hand, so it cannot be forgotten."}
            data["zbrush_folders"] = kept
            _write_studio_file(data)
        e = installs.entry(path)
        return {"ok": True, "message": f"Forgot {e['name'] if e else os.path.basename(os.path.normpath(str(path)))}."}

    def get_library_folders(self):
        """The folders the user added, per kind, for the Library screen. count, hidden and error come from the last
        walk of that kind in this process (None when there was none, or it did not reach the folder)."""
        out = {}
        for kind in brushes.LIBRARY_KINDS:
            folders = brushes.user_folders(kind)
            try:
                walk = assets.last_walk(kind)
            except Exception as e:
                _startup(f"get_library_folders: last_walk({kind}): {e!r}")
                walk = None
            found = {s.get("label"): s for s in (walk.sources if walk else [])}
            rows = []
            for f, name in zip(folders, brushes.display_names(folders)):
                src = found.get(brushes.added_label(f))
                rows.append({"path": str(f), "name": name, "exists": os.path.isdir(f),
                             "count": src.get("count") if src else None,
                             "hidden": (src.get("hidden") or 0) if src else None,
                             "error": src.get("error") if src else None})
            out[kind] = rows
        return {"ok": True, "folders": out}

    def add_library_folder(self, kind, path=None, index=None):
        """Folder picker for a folder of the user's own brushes, alphas, materials or textures; remembered per kind in
        studio.json. Refuses a network folder, one ZBrush's own folders already cover and one that overlaps a folder
        already added (everything in it would be listed twice). It goes at the end of the list, or at index when that
        is given (an index past the end is the end).

        With path no dialog opens: that is Undo on a forgotten folder, which puts it back where it was. A folder that
        has gone missing since can be put back too, as the list may hold one."""
        import webview
        if kind not in brushes.LIBRARY_KINDS:
            return {"ok": False, "message": "Unknown kind."}
        restore = path is not None
        if restore:
            if not isinstance(path, str) or not path.strip():
                return {"ok": False, "message": "That folder cannot be found."}
            picked = path
        else:
            picked = self._window.create_file_dialog(webview.FileDialog.FOLDER)
            if not picked:
                return {"ok": False, "cancelled": True}
        p = os.path.normpath(str(picked[0] if isinstance(picked, (list, tuple)) else picked))
        if p.startswith(("\\\\", "//")):
            return {"ok": False, "message": "That is a network folder. Add a folder on this PC."}
        if (not os.path.isdir(p)) if not restore else (not os.path.isabs(p)):   # a put-back may be missing, never relative
            return {"ok": False, "message": "That folder cannot be found."}
        zb_name = self._zbrush_folder_overlap(kind, p)
        if zb_name:
            return {"ok": False, "message": f"ZOrbit already searches that folder: it is part of ZBrush ({zb_name})."}
        have = [str(f) for f in brushes.user_folders(kind)]
        names = brushes.display_names(have)
        key = os.path.normcase(p)
        for f, name in zip(have, names):
            if os.path.normcase(f) == key:
                return {"ok": True, "already": True, "message": f"{name} is already listed.",
                        "folders": self.get_library_folders()["folders"]}
        for f, name in zip(have, names):
            if _inside(p, f):
                return {"ok": False, "message": f"{name} is already searched, and this one is inside it."}
            if _inside(f, p):
                return {"ok": False, "message": f"{name} is already searched, and this one would contain it."}
        with _studio_lock:                     # read, change and write as one step
            data = _studio_for_update()
            if data is None:
                return {"ok": False, "message": STUDIO_UNREADABLE}
            lib = data.get("library_folders")
            if not isinstance(lib, dict):
                lib = {}
            if not isinstance(lib.get(kind), list):
                lib[kind] = []
            at = index if isinstance(index, int) and not isinstance(index, bool) and index >= 0 else len(lib[kind])
            lib[kind].insert(min(at, len(lib[kind])), p)
            data["library_folders"] = lib
            _write_studio_file(data)
        folders = self.get_library_folders()["folders"]
        name = next((r["name"] for r in folders[kind] if os.path.normcase(r["path"]) == key), os.path.basename(p))
        return {"ok": True, "message": f"Put {name} back." if restore else f"Added {name}.", "folders": folders}

    def _zbrush_folder_overlap(self, kind, p):
        """The name of the ZBrush folder that p is, is inside or contains; None when it overlaps none of them."""
        labels = assets.source_labels(kind)
        for label, folder, _recursive in assets.sources(kind):      # the named library first
            if not brushes.is_added(label) and (_inside(p, str(folder)) or _inside(str(folder), p)):
                return labels.get(label) or "the ZBrush folder"
        dirs = brushes.zbrush_dirs()
        for d in (dirs.get("install"), dirs.get("user_assets")):
            if d and (_inside(p, str(d)) or _inside(str(d), p)):
                return "the ZBrush folder"
        return None

    def forget_library_folder(self, kind, path):
        """Takes a folder out of the list of that kind. The folder itself is not touched. The answer has the path as
        it was listed ("removed") and its place in the list ("index"), which add_library_folder takes to put it back."""
        if kind not in brushes.LIBRARY_KINDS:
            return {"ok": False, "message": "Unknown kind."}
        key = os.path.normcase(os.path.normpath(str(path)))
        with _studio_lock:                     # read, change and write as one step
            data = _studio_for_update()
            if data is None:
                return {"ok": False, "message": STUDIO_UNREADABLE}
            lib = data.get("library_folders")
            listed = lib.get(kind) if isinstance(lib, dict) else None
            listed = listed if isinstance(listed, list) else []
            hit = [i for i, f in enumerate(listed) if isinstance(f, str) and os.path.normcase(os.path.normpath(f)) == key]
            if not hit:
                return {"ok": False, "message": "That folder is not in the list."}
            kept = [f for i, f in enumerate(listed) if i not in hit]
            have = brushes.user_folders(kind)
            name = next((n for f, n in zip(have, brushes.display_names(have)) if os.path.normcase(str(f)) == key),
                        os.path.basename(key))
            lib[kind] = kept
            data["library_folders"] = lib
            _write_studio_file(data)
        return {"ok": True, "message": f"Forgot {name}. The folder itself was not touched.",
                "removed": listed[hit[0]], "index": hit[0], "folders": self.get_library_folders()["folders"]}

    # --- import / export (menus, settings and tags in one file) -----------------------------------
    def _export_name(self):
        """The file name export_settings offers: the profile's name in it, so exports of two profiles differ."""
        day = time.strftime("%Y-%m-%d")
        if not profiles.enabled():
            return f"ZOrbit settings {day}.json"
        return f"ZOrbit {self._prof()} {day}.json"          # a profile name is a valid file name already

    def export_settings(self, cfg):
        """Saves what the editor shows (cfg, unsaved edits included) and the tags as one settings file, to a
        place the user picks: this profile's menus, settings and tags. studio.json and usage.json are left out."""
        import webview
        if not isinstance(cfg, dict) or not isinstance(cfg.get("menus"), dict):
            return {"ok": False, "message": "There are no menus to export."}
        picked = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=self._export_name(),
            file_types=("ZOrbit settings (*.json)", "All files (*.*)"))
        if not picked:
            return {"ok": False, "cancelled": True, "message": "Export cancelled."}
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        if not os.path.splitext(path)[1]:
            path += ".json"
        store = tags.TagStore(self._tags_path()).load()
        bundle = {"zorbit_settings": SETTINGS_FORMAT, "version": VERSION,
                  "exported": time.strftime("%Y-%m-%dT%H:%M:%S"), "config": cfg}
        note = ""
        if store.error:                  # a broken tags.json: the menus are still worth saving
            note = f" The tags are not in it: {store.error}."
        else:
            bundle["tags"] = store.snapshot()
        try:
            fsutil.write_atomic(path, json.dumps(bundle, indent=2, ensure_ascii=False) + "\n")
        except (OSError, TypeError, ValueError) as e:
            return {"ok": False, "message": f"The settings could not be saved: {getattr(e, 'strerror', None) or e}"}
        return {"ok": True, "path": path,
                "message": f"Saved this profile's menus, settings and tags to {path}.{note}"}

    @staticmethod
    def _read_import_file(path, what):
        """Reads a file an import asked for: (raw, None), or (None, message) when it is too big, not text, not JSON
        or not a JSON object. what names the kind of file in the messages ('ZOrbit settings file')."""
        name = os.path.basename(path)
        try:
            if os.path.getsize(path) > IMPORT_MAX_BYTES:
                return None, f"{name} is too big to be a {what} (over {IMPORT_MAX_BYTES // (1024 * 1024)} MB)."
            with open(path, "rb") as f:
                data = f.read(IMPORT_MAX_BYTES + 1)
            if len(data) > IMPORT_MAX_BYTES:
                return None, f"{name} is too big to be a {what}."
            raw = json.loads(data.decode("utf-8-sig"))
        except json.JSONDecodeError as e:
            return None, f"{name} is not valid JSON: {e.msg} at line {e.lineno}, column {e.colno}."
        except UnicodeDecodeError:
            return None, f"{name} is not a text file."
        except (OSError, ValueError, RecursionError) as e:
            return None, f"{name} could not be read: {getattr(e, 'strerror', None) or e}"
        if not isinstance(raw, dict):
            return None, f"{name} is not a {what} (the top level is not a JSON object)."
        return raw, None

    def _ask_settings_file(self, need_menus=False):
        """Asks for a settings file (an export, or a plain radial.json or tags.json), reads it and sorts out what it
        holds. Returns (found, None), or (None, answer) where answer is the cancel or refusal to give the page.
        found: path, name, kind ("bundle", "config" or "tags"), version, cfg (or None), tags (the raw tags the file
        really holds, else None), info (those tags as a TagStore, else None), problems (the loader's, for cfg).
        need_menus: a file with no menus is refused (a profile cannot be made from tags alone)."""
        import webview

        def refuse(msg):
            return None, {"ok": False, "message": msg}

        picked = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("ZOrbit settings (*.json)", "All files (*.*)"))
        if not picked:
            return None, {"ok": False, "cancelled": True}
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        name = os.path.basename(path)
        raw, error = self._read_import_file(path, "ZOrbit settings file")
        if error:
            return refuse(error)

        if "zorbit_menu" in raw:            # a shared menu: its "menus" would otherwise replace all of yours
            return refuse(f"{name} is a menu file, not a settings file. Import it with Import menu... under the "
                          "Menus list.")
        if "zorbit_settings" in raw:
            kind, version = "bundle", raw.get("version")
            fmt = raw["zorbit_settings"]
            if isinstance(fmt, int) and fmt > SETTINGS_FORMAT:
                return refuse(f"{name} was made by a newer ZOrbit{f' ({version})' if isinstance(version, str) else ''}. "
                              "Update ZOrbit to import it.")
            cfg, tags_raw = raw.get("config"), raw.get("tags")
        elif isinstance(raw.get("menus"), dict):
            kind, version, cfg, tags_raw = "config", None, raw, None
        elif isinstance(raw.get("tags"), dict) or isinstance(raw.get("items"), dict):
            kind, version, cfg, tags_raw = "tags", None, None, raw
        else:
            return refuse(f"{name} is not a ZOrbit settings file. It should be a settings export, a radial.json "
                          "or a tags.json.")
        version = version if isinstance(version, str) else ""
        if cfg is not None and (not isinstance(cfg, dict) or not isinstance(cfg.get("menus"), dict)
                                or not cfg["menus"]):
            return refuse(f"The menus in {name} are missing or not valid.")
        tags_raw = tags_raw if isinstance(tags_raw, dict) else None
        # The tags the file really holds. TagStore.from_raw always adds Favourites, which would make every tags
        # object "have tags"; a file whose tags section is empty or malformed has none, while one holding only the
        # Favourites tag counts (it carries the starred items).
        info = tags.TagStore.from_raw(tags_raw) if tags_raw is not None else None
        has_tags = bool(tags_raw is not None and tags._parse(tags_raw)[0])
        if not has_tags:
            tags_raw, info = None, None
        if cfg is None and need_menus:
            return refuse(f"{name} has no menus in it, so it cannot become a profile.")
        if cfg is None and not has_tags:
            return refuse(f"{name} has no menus and no tags in it.")
        problems = []
        if cfg is not None:
            loaded, problems = self._load_dict(cfg, info)
            if loaded is None:
                return refuse(f"The menus in {name} could not be read: {problems[0] if problems else 'unknown error'}")
        return {"path": path, "name": name, "kind": kind, "version": version, "cfg": cfg, "tags": tags_raw,
                "info": info, "problems": problems}, None

    def pick_import(self):
        """Asks for a settings file (an export, or a plain radial.json or tags.json), reads and checks it and
        returns what it holds. Writes nothing; apply_import() does the work with what is read here."""
        self._pending_import = None
        found, answer = self._ask_settings_file()
        if answer:
            return answer
        cfg, tags_raw, has_tags = found["cfg"], found["tags"], found["tags"] is not None
        out = {"ok": True, "path": found["path"], "kind": found["kind"], "has_config": cfg is not None,
               "menus": len(cfg["menus"]) if cfg is not None else 0, "has_tags": has_tags,
               "tags": 0, "new_tags": 0, "items": 0, "problems": found["problems"], "version": found["version"]}
        store = tags.TagStore(self._tags_path()).load()
        if has_tags:
            out.update(store.import_preview(tags_raw))
        # What a replace would throw away, so the page can say "The file's 4 menus replace your 7".
        out["current_menus"] = self._current_menu_count()
        out["current_tags"] = 0 if store.error else len(store.tags())
        self._pending_import = {"path": found["path"], "kind": found["kind"], "config": cfg, "tags": tags_raw,
                                "profile": self._prof()}
        return out

    def _current_menu_count(self) -> int:
        """How many menus radial.json holds now (0 when it is missing or unreadable)."""
        try:
            with open(self._cfg_path(), encoding="utf-8-sig") as f:
                menus = json.load(f).get("menus")
            return len(menus) if isinstance(menus, dict) else 0
        except (OSError, ValueError, AttributeError, RecursionError):
            return 0

    def apply_import(self, tag_mode="merge"):
        """Does what pick_import read. tag_mode: 'merge' or 'replace' the tags, or 'none' to leave them.
        The tags are saved straight away; the menus and settings come back as config for the editor to load
        (radial.json is not written: Save does that). Slots that point at a tag which joined a local tag of the
        same name are pointed at the local one."""
        newer = self._too_new(config=None, problems=[], tags_message="")
        if newer:
            return newer
        pend = self._pending_import
        if not pend:
            return {"ok": False, "config": None, "problems": [], "tags_message": "",
                    "message": "There is nothing to import. Pick the file again."}
        if pend.get("profile") != self._prof():     # the editor moved to another profile after the file was read
            return {"ok": False, "config": None, "problems": [], "tags_message": "",
                    "message": "The profile changed. Pick the file again."}
        if tag_mode not in ("merge", "replace", "none"):
            return {"ok": False, "config": None, "problems": [], "tags_message": "",
                    "message": "Import the tags as merge, replace or none."}
        if pend["tags"] is None:
            tag_mode = "none"
        if pend["config"] is None and tag_mode == "none":
            return {"ok": False, "config": None, "problems": [], "tags_message": "",
                    "message": "There is nothing to import: the file has only tags, and they were left out."}
        renamed, tags_message = {}, ""
        if tag_mode != "none":
            res = webapi.store().import_tags(pend["tags"], tag_mode)
            if not res.get("ok"):
                return {"ok": False, "config": None, "problems": [], "tags_message": "",
                        "message": res.get("error") or "The tags could not be imported."}
            renamed = res["renamed"]
            if tag_mode == "replace":
                tags_message = (f"Replaced the tags with the {_plural(res['added'], 'tag')} from the file. "
                                "The old ones are kept in tags.json.bak.")
            else:
                tags_message = f"Merged the tags: {_plural(res['added'], 'new tag')} added"
                if renamed:
                    tags_message += f", {_plural(len(renamed), 'tag')} matched an existing tag by name"
                tags_message += "."
        cfg, problems = None, []
        if pend["config"] is not None:
            cfg = _retag(copy.deepcopy(pend["config"]), renamed)
            _, problems = self._load_dict(cfg)          # against the tags as they are now
        self._pending_import = None
        return {"ok": True, "config": cfg, "problems": problems, "tags_message": tags_message,
                "message": tags_message or "Loaded the menus and settings into the editor."}

    # --- sharing one menu (the menu, its submenus and the tags they use, as a small file) ---------
    def export_menu(self, cfg, menu_id):
        """Saves one menu of the editor (cfg, unsaved edits included) and the submenus it opens as a menu file, to a
        place the user picks. See menushare.build for what the file holds."""
        import webview
        menus = cfg.get("menus") if isinstance(cfg, dict) else None
        if not isinstance(menus, dict) or not isinstance(menu_id, str) \
                or menu_id.startswith(("tag:", "more:", "recent:")) or not isinstance(menus.get(menu_id), dict):
            return {"ok": False, "message": "There is no such menu to export."}
        title = str(menus[menu_id].get("title") or menu_id)
        fname = re.sub(r'[\\/:*?"<>|]', "_", f"{title} menu.json")
        picked = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=fname, file_types=("ZOrbit menu (*.json)", "All files (*.*)"))
        if not picked:
            return {"ok": False, "cancelled": True, "message": "Export cancelled."}
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        if not os.path.splitext(path)[1]:
            path += ".json"
        store = tags.TagStore(self._tags_path()).load()
        bundle = menushare.build(cfg, menu_id, None if store.error else store, VERSION)
        note = f" The tags are not in it: {store.error}." if store.error else ""
        # build() has cleaned the menus already, so count what was there before: the raw menus of the same ids
        left = menushare.left_out({mid: menus[mid] for mid in menushare.collect(cfg, menu_id)})
        if left:
            note += f" {_plural(left, 'Tool, Project or Layout item')} left out of the file, because their paths belong to this PC."
        subs = len(bundle["menus"]) - 1
        what = f'"{title}"' + (f" and its {_plural(subs, 'submenu')}" if subs else "")
        try:
            fsutil.write_atomic(path, json.dumps(bundle, indent=2, ensure_ascii=False) + "\n")
        except (OSError, TypeError, ValueError) as e:
            return {"ok": False, "message": f"The menu could not be saved: {getattr(e, 'strerror', None) or e}"}
        return {"ok": True, "path": path, "message": f"Saved {what} to {path}.{note}"}

    def _menu_problems(self, cfg, store=None):
        """The loader's problems for imported menus on their own. An imported menu has no hotkey, so the loader's
        'no menu has a hotkey' is left out: it says nothing about the menus the user already has."""
        _, problems = self._load_dict(cfg, store)
        return [p for p in problems if not p.startswith("no menu has a hotkey")]

    @staticmethod
    def _import_looks(menus_out, bundle_looks, cfg):
        """How the looks of a menu file come in next to the looks of cfg: (looks_out, renamed, joined) as
        menushare.plan_looks gives them. The imported menus (menus_out) are pointed at the names the looks get."""
        mine = cfg.get("looks") if isinstance(cfg, dict) and isinstance(cfg.get("looks"), dict) else {}
        looks_out, renamed, joined = menushare.plan_looks(bundle_looks, mine)
        C.relook(menus_out, renamed)
        return looks_out, renamed, joined

    @staticmethod
    def _looks_message(looks_out, renamed, joined) -> str:
        """One sentence on the looks a menu file brought, "" when it brought none."""
        bits = []
        if looks_out:
            bits.append(f"Added {_plural(len(looks_out), 'look')} to yours")
        n = sum(1 for new in renamed.values() if new in looks_out)
        if n:
            bits.append(f"{_plural(n, 'look')} got a new name because yours has one with that name")
        if joined:
            bits.append(f"{_plural(len(joined), 'look')} matched one of yours")
        return ("; ".join(bits) + ".") if bits else ""

    @staticmethod
    def _looks_for(cfg, menus_out, looks_out):
        """The looks that checking imported menus needs: those of cfg and the new ones that the menus name."""
        mine = cfg.get("looks") if isinstance(cfg, dict) and isinstance(cfg.get("looks"), dict) else {}
        return menushare.looks_used({"looks": {**mine, **looks_out}}, menus_out)

    def pick_menu_import(self, cfg):
        """Asks for a menu file, reads and checks it and returns what it holds and how it would come in next to the
        menus of cfg. Writes nothing; apply_menu_import() does the work with what is read here."""
        import webview
        self._pending_menu_import = None
        picked = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("ZOrbit menu (*.json)", "All files (*.*)"))
        if not picked:
            return {"ok": False, "cancelled": True}
        path = picked[0] if isinstance(picked, (list, tuple)) else picked
        name = os.path.basename(path)
        raw, error = self._read_import_file(path, "ZOrbit menu file")
        if error:
            return {"ok": False, "message": error}
        version = raw.get("version") if isinstance(raw.get("version"), str) else ""
        if "zorbit_menu" not in raw:
            if "zorbit_settings" in raw or isinstance(raw.get("menus"), dict):
                return {"ok": False, "message": f"{name} is a settings file, not a menu. "
                                                "Import it in Settings > Import and export."}
            return {"ok": False, "message": f"{name} is not a ZOrbit menu file."}
        fmt = raw["zorbit_menu"]
        if isinstance(fmt, int) and not isinstance(fmt, bool) and fmt > menushare.MENU_FORMAT:
            return {"ok": False, "message": f"{name} was made by a newer ZOrbit{f' ({version})' if version else ''}. "
                                            "Update ZOrbit to import it."}
        menus, root = raw.get("menus"), raw.get("menu")
        if not isinstance(menus, dict) or not menus or not all(isinstance(m, dict) for m in menus.values()) \
                or root not in menus:
            return {"ok": False, "message": f"The menu in {name} is not valid."}
        tags_raw = raw.get("tags") if isinstance(raw.get("tags"), dict) else None
        if tags_raw is not None and not tags._parse(tags_raw)[0]:
            tags_raw = None
        looks_raw = raw.get("looks") if isinstance(raw.get("looks"), dict) else {}
        menus_out, root_out, renames = menushare.plan_import(menus, root, cfg if isinstance(cfg, dict) else {})
        looks_out, looks_renamed, looks_joined = self._import_looks(menus_out, looks_raw, cfg)
        store = tags.TagStore(self._tags_path()).load()
        counts, known = {"tags": 0, "new_tags": 0, "items": 0}, store
        if tags_raw is not None:
            counts = store.import_preview(tags_raw)
            merged = store.snapshot()
            for k, t in tags._parse(tags_raw)[0].items():
                merged["tags"].setdefault(k, t)
            known = tags.TagStore.from_raw(merged)       # the user's tags plus the file's: none reads as unknown
        problems = self._menu_problems({"menus": menus_out, "looks": self._looks_for(cfg, menus_out, looks_out)}, known)
        self._pending_menu_import = {"path": path, "menus": menus, "root": root, "tags": tags_raw,
                                     "looks": looks_raw, "profile": self._prof()}
        return {"ok": True, "path": path, "version": version, "root": root_out,
                "title": menus_out[root_out].get("title") or root_out,
                "menus": [{"id": mid, "title": m.get("title") or mid,
                           "items": len(m["items"]) if isinstance(m.get("items"), list) else 0}
                          for mid, m in menus_out.items()],
                "renames": renames, "tags": counts["tags"], "new_tags": counts["new_tags"],
                "tagged_items": counts["items"], "missing": menushare.missing_assets(menus_out),
                "looks": {"added": list(looks_out), "joined": looks_joined, "renamed": looks_renamed},
                "problems": problems}

    def apply_menu_import(self, cfg):
        """Does what pick_menu_import read: the plan is made again against cfg (the editor may have changed since).
        The tags the file brings are merged and saved straight away; the menus come back for the editor to add
        (radial.json is not written: Save does that)."""
        newer = self._too_new()
        if newer:
            return newer
        pend = self._pending_menu_import
        if not pend:
            return {"ok": False, "message": "There is nothing to import. Pick the file again."}
        if pend.get("profile") != self._prof():
            return {"ok": False, "message": "The profile changed. Pick the file again."}
        menus_out, root_out, _ = menushare.plan_import(pend["menus"], pend["root"],
                                                       cfg if isinstance(cfg, dict) else {})
        looks_out, looks_renamed, looks_joined = self._import_looks(menus_out, pend.get("looks") or {}, cfg)
        renamed, tags_message = {}, ""
        if pend["tags"] is not None:
            res = webapi.store().import_tags(pend["tags"], "merge")
            if res.get("ok"):
                renamed = res["renamed"]
                bits = []
                if res["added"]:
                    bits.append(f"Added {_plural(res['added'], 'tag')} to yours")
                if renamed:
                    n = len(renamed)
                    bits.append(f"{n if bits else _plural(n, 'tag')} joined a tag of yours with the same name")
                tags_message = ("; ".join(bits) + ".") if bits else "You already had the tags it uses."
            else:
                tags_message = f"The tags were not added: {res.get('error') or 'they could not be imported'}."
            C.retag({"menus": menus_out}, renamed)
        problems = self._menu_problems({"menus": menus_out, "looks": self._looks_for(cfg, menus_out, looks_out)})
        # (against the tags as they are now)
        self._pending_menu_import = None
        title = menus_out[root_out].get("title") or root_out
        subs = len(menus_out) - 1
        message = f'Added "{title}"' + (f" and its {_plural(subs, 'submenu')}" if subs else "") + " to the editor."
        return {"ok": True, "menus": menus_out, "root": root_out, "title": title, "problems": problems,
                "tags_message": tags_message, "message": message, "looks": looks_out,
                "looks_renamed": looks_renamed, "looks_joined": looks_joined,
                "looks_message": self._looks_message(looks_out, looks_renamed, looks_joined)}

    # --- Studio preferences (not part of the menus; saved straight away) --------------------------
    # mode is "" until Studio decides it at first start (Simple for a fresh install, Full for an existing setup).
    # seen_version is the version whose "What's new" was closed last ("" until it has been shown once).
    # tour_seen is whether the tour of Studio has been offered (a fresh install gets the offer after Setup; an existing user does not).
    # theme is dark, light, system (follow Windows) or zbrush; get_prefs adds theme_effective (the one in force),
    # theme_base, theme_tokens, theme_sig and theme_source.
    _PREFS_DEFAULTS = {"check_updates": True, "last_screen": "menus", "setup_done": False, "mode": "",
                       "seen_version": "", "tour_seen": False, "theme": "dark", "skipped_version": ""}
    # Keys an earlier Studio already wrote: a studio.json with any of them belongs to someone who has used the
    # Studio, so the Setup screen is not forced on them after an update.
    _USED_KEYS = ("window", "last_screen", "check_updates", "zbrush_folders")
    # Keys a past Studio wrote that nothing reads now: dropped from studio.json the next time a preference is saved.
    _RETIRED_KEYS = ("show_licence",)

    def get_prefs(self):
        with _studio_lock:
            data = _read_studio_file()
            # once: existing users skip Setup, a fresh install gets it. (An unreadable file reads as {}: it is
            # left alone rather than overwritten with just this key.)
            changed = False
            if "setup_done" not in data and (data or not os.path.exists(STUDIO_FILE)):
                data["setup_done"] = any(k in data for k in self._USED_KEYS)
                changed = True
            # the same for "What's new": a fresh install has nothing to tell, an existing user sees this
            # version's section once
            if "seen_version" not in data and (data or not os.path.exists(STUDIO_FILE)):
                data["seen_version"] = VERSION if data.get("setup_done") is False else ""
                changed = True
            # the tour of Studio: offered once to someone new, never to someone who had already used Studio
            if "tour_seen" not in data and (data or not os.path.exists(STUDIO_FILE)):
                data["tour_seen"] = data.get("setup_done") is not False
                changed = True
            if changed:
                try:
                    _write_studio_file(data)
                except OSError:
                    pass                             # the answer below is the same; it is decided again next time
        prefs = dict(self._PREFS_DEFAULTS)
        prefs.update({k: v for k, v in data.items()
                      if k in self._PREFS_DEFAULTS and type(v) is type(self._PREFS_DEFAULTS[k])})   # a hand edit of the wrong type is ignored
        if prefs["theme"] not in theme.NAMES:
            prefs["theme"] = theme.DEFAULT            # a hand edit to a name that does not exist
        prefs["theme_effective"] = theme.effective(prefs["theme"])     # computed, never stored
        look = theme.preset(prefs["theme"])
        prefs["theme_base"] = look["base"]                             # dark or light: the page's data-theme
        prefs["theme_tokens"] = look["web"] if prefs["theme_effective"] == "zbrush" else {}
        prefs["theme_sig"] = theme.signature(STUDIO_FILE)[1]           # the scheme's digest, "" unless zbrush
        src = theme.source() if prefs["theme"] == "zbrush" else None   # what Match ZBrush reads, for the Settings line
        prefs["theme_source"] = dict(src, stored=int(src["stored"])) if src else None
        return prefs

    def set_pref(self, key, value):
        if key not in self._PREFS_DEFAULTS or type(value) is not type(self._PREFS_DEFAULTS[key]):
            return self.get_prefs()
        if key == "mode" and value not in ("", "simple", "full"):
            return self.get_prefs()
        if key == "theme" and value not in theme.NAMES:
            return self.get_prefs()
        if key == "skipped_version" and value and paths.version_key(value) is None:
            return self.get_prefs()
        with _studio_lock:                     # read, change and write as one step
            data = _studio_for_update()            # keeps the other keys (window placement)
            if data is None:
                return self.get_prefs()            # not saved: the page still shows what the file says
            for old in self._RETIRED_KEYS:
                data.pop(old, None)
            data[key] = value
            _write_studio_file(data)
        if key == "theme":
            self._apply_frame_theme()
            _tell_popout_theme()
        return self.get_prefs()

    def check_update(self):
        """Asks GitHub for the latest release. {"current", "latest", "url", "newer", "can_install", "skipped"};
        latest is None when the check is off (no request is made) or GitHub could not be reached. can_install: Studio
        can download and install it itself (an installed copy, and the release has a setup file with a known
        SHA-256). installed, with a newer release: this is the copy Setup installed, so the dialog can say why
        can_install is false. skipped: the user chose "Don't remind me again" for this version (skipped_version), so the top
        does not point it out; a newer one is pointed out again. notes: the newer release's notes for the update
        dialog, {"version", "date", "url", "summary", "items", "blog"} (changelog.release_notes), else None."""
        out = {"current": VERSION, "latest": None, "url": f"{RELEASES_URL}/tag/v{VERSION}", "newer": False,
               "can_install": False, "skipped": False, "notes": None}
        prefs = self.get_prefs()
        if not prefs["check_updates"]:
            return out
        try:
            import urllib.request
            req = urllib.request.Request(RELEASES_API, headers={
                "Accept": "application/vnd.github+json", "User-Agent": f"ZOrbitStudio/{VERSION}"})
            with _urlopen(req, timeout=8) as r:
                data = json.load(r)
        except Exception as e:
            _startup(f"update check failed: {e!r}")
            return out
        tag = data.get("tag_name") if isinstance(data, dict) else None
        latest, current = paths.version_key(tag), paths.version_key(VERSION)
        if latest is None:
            return out
        out["latest"] = "%d.%d.%d" % latest
        out["newer"] = current is not None and latest > current
        if out["newer"]:
            out["url"] = f"{RELEASES_URL}/tag/{tag}"
            setup = _setup_asset(data, out["latest"])
            with self._upd_lock:
                if self._upd["state"] != "downloading":
                    self._upd_release = setup
            if not setup:
                _startup(f"update: {tag} has no setup file Studio can trust, so it offers the download page")
            out["installed"] = _installed_here()
            out["can_install"] = bool(setup) and out["installed"]
            out["skipped"] = paths.version_key(prefs["skipped_version"]) == latest
            published = data.get("published_at")
            date = published[:10] if isinstance(published, str) and re.match(r"\d{4}-\d{2}-\d{2}", published) else ""
            out["notes"] = dict(changelog.release_notes(data.get("body"), out["latest"]),
                                version=out["latest"], date=date, url=out["url"])
        elif current is not None:
            _clear_updates()                   # an update that is installed now, or never was: its setup can go
        return out

    def get_update_progress(self):
        """Where the update download is: {"state": "idle" | "downloading" | "ready" | "failed", "version", "done",
        "total", "message"}. done and total are bytes."""
        with self._upd_lock:
            return dict(self._upd)

    def download_update(self):
        """Downloads the setup of the release check_update found, into %LOCALAPPDATA%\\ZOrbit\\updates, and checks
        its size and SHA-256. Blocks until it is done. A call while a download runs waits for that one. A setup
        that is already there and checks out is not fetched again. {"ok", "version", "message"}."""
        with self._upd_dl:                                 # one download at a time; a second caller waits for it
            with self._upd_lock:
                setup, st = self._upd_release, dict(self._upd)
            if not setup:
                return {"ok": False, "message": "There is no update to download. Check for updates first."}
            if st["state"] == "ready" and st["version"] == setup["version"] \
                    and _file_sha256(st["file"]) == setup["sha256"]:
                return {"ok": True, "version": setup["version"], "message": ""}
            with self._upd_lock:
                self._upd = {"state": "downloading", "version": setup["version"], "done": 0,
                             "total": setup["size"], "message": "", "file": ""}
            dest = os.path.join(_update_dir(), setup["name"])
            _startup(f"update: downloading {setup['url']}")
            try:
                if _file_sha256(dest) != setup["sha256"]:
                    _clear_updates()
                    os.makedirs(_update_dir(), exist_ok=True)
                    self._fetch_setup(setup, dest)
            except Exception as e:
                msg = _download_problem(e)
                _startup(f"update: download failed: {e!r}")
                with self._upd_lock:
                    self._upd.update(state="failed", message=msg)
                return {"ok": False, "version": setup["version"], "message": msg}
            _startup(f"update: {setup['name']} downloaded and checked")
            with self._upd_lock:
                self._upd.update(state="ready", done=setup["size"], file=dest)
            return {"ok": True, "version": setup["version"], "message": ""}

    def _fetch_setup(self, setup, dest):
        """Streams the setup to dest + ".part" and moves it into place only when its size and SHA-256 match."""
        import hashlib
        import urllib.request
        part = dest + ".part"
        h, done = hashlib.sha256(), 0
        req = urllib.request.Request(setup["url"], headers={"User-Agent": f"ZOrbitStudio/{VERSION}"})
        try:
            with _urlopen(req, timeout=30) as r, open(part, "wb") as f:
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    done += len(chunk)
                    if done > setup["size"]:
                        raise UpdateError("The download is bigger than GitHub says the file is.")
                    h.update(chunk)
                    f.write(chunk)
                    with self._upd_lock:
                        self._upd["done"] = done
            if done != setup["size"]:
                raise UpdateError("The download stopped before the end of the file.")
            if h.hexdigest() != setup["sha256"]:
                raise UpdateError("The downloaded file does not match the SHA-256 of the release, so it was "
                                  "deleted.")
            os.replace(part, dest)
        finally:
            try:
                os.remove(part)
            except OSError:
                pass

    def install_update(self):
        """Starts the downloaded setup (silent, it reopens Studio when it is done, and the app when it was running)
        and closes Studio without asking: the page has dealt with unsaved changes first. The file is checked
        again first. {"ok", "message"}; on ok the window is closing."""
        with self._upd_lock:
            st = dict(self._upd)
            setup = self._upd_release
        if st["state"] != "ready" or not setup or st["version"] != setup["version"]:
            return {"ok": False, "message": "The update has not been downloaded yet."}
        if not _installed_here():
            return {"ok": False, "message": "This copy of ZOrbit was not installed with Setup, so it cannot "
                                            "update itself. Download the new version from GitHub."}
        if _file_sha256(st["file"]) != setup["sha256"]:
            with self._upd_lock:
                self._upd.update(state="idle", file="")
            return {"ok": False, "message": "The downloaded setup changed on disk since it was checked. "
                                            "Download it again."}
        args = [st["file"], "/SILENT", "/SP-", "/NOCANCEL", "/NORESTART", "/CLOSEAPPLICATIONS",
                f"/LOG={os.path.join(DATA_DIR, 'update-setup.log')}", "/RELAUNCH=1"]
        if _mutex_exists(APP_MUTEX):
            args.append("/STARTAPP=1")
        try:
            subprocess.Popen(args, cwd=_update_dir(), env=paths.clean_env(), close_fds=True,
                             creationflags=0x00000008 | 0x00000200,     # DETACHED_PROCESS, CREATE_NEW_PROCESS_GROUP
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            _startup(f"update: setup did not start: {e!r}")
            return {"ok": False, "message": f"Setup did not start: {e.strerror or e}"}
        _startup(f"update: started {os.path.basename(st['file'])}; closing for the install")
        self._allow_close = True
        self.win_close()
        return {"ok": True, "message": ""}

    def get_whats_new(self, all_current=False):
        """The "What's new" sections: every version after seen_version (the one the user last closed the
        dialog for), up to this one, newest first. all_current: only this version's section, whatever was
        seen (the Settings button). {"current", "sections": [{"version", "date", "summary", "items", "url"}],
        "url"}. The page sets seen_version itself when the dialog closes."""
        seen = "" if all_current else self.get_prefs()["seen_version"]
        sections = []
        for s in changelog.since(changelog.read(), seen, VERSION):
            shown = changelog.summary_of(s)
            url = RELEASES_URL if s["version"] == "Unreleased" else f"{RELEASES_URL}/tag/v{s['version']}"
            sections.append({"version": s["version"], "date": s["date"], "summary": shown["text"],
                             "items": shown["items"], "url": url})
        return {"current": VERSION, "sections": sections, "url": f"{RELEASES_URL}/tag/v{VERSION}"}

    def open_url(self, url):
        """Opens one of the project's own links in the default browser (nothing else is allowed)."""
        allowed = ("https://github.com/combwizard/zorbit", "https://zorbit.lol/docs",
                   "https://www.gnu.org/licenses/gpl-3.0.html")
        ok = isinstance(url, str) and any(url == a or url.startswith(a + c) for a in allowed for c in "/?#")
        if ok:
            os.startfile(url)
            return True
        return False

    def open_folder(self, which="data"):
        """'data' opens the logs folder; 'profiles' the folder holding every profile; 'pre-profiles' the folder
        where files of an older version are set aside; 'config' (and the older name 'app') and anything else open
        the folder of the profile the editor holds, where radial.json is."""
        if which == "data":
            folder = DATA_DIR
        elif which == "profiles":
            folder = profiles.root()
        elif which == "pre-profiles":
            folder = os.path.join(paths.CONFIG_DIR, "pre-profiles")
        else:
            folder = os.path.dirname(self._cfg_path())
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)
        return True

    def open_browser(self, kind=None):
        """Opens the browser (on the tab of this kind: brush, alpha, material or texture; None keeps its last tab):
        asks the running one to show itself (it may be a hidden pre-warmed one, or one the user closed), else
        starts a new one that shows itself. Not --managed: the browser needs no app.
        {"ok": bool, "started": bool, "error"}."""
        kind = kind if kind in C.ASSET_KINDS else None
        try:
            import win32
            ctl = win32.find_message_window(radiald.POPOUT_CLASS)
            if ctl:
                payload = json.dumps({"tag": None, "kind": kind, "zbrush_hwnd": 0, "toggle": False}).encode("utf-8")
                r = win32.send_copydata(ctl, radiald.COPYDATA_SHOW, payload)
                if r == 1:
                    return {"ok": True, "started": False}
                _startup(f"open_browser: SHOW to {ctl} answered {r}; starting a new one")
            subprocess.Popen(paths.launch_commands()["popout"] + ["--show"] + (["--kind", kind] if kind else []),
                             env=paths.clean_env(),
                             creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                             close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return {"ok": True, "started": True}
        except Exception as e:
            _startup(f"open_browser failed: {e!r}")
            return {"ok": False, "started": False, "error": "Could not open the browser: " + str(e)}

    # --- window (custom title bar; plain Win32 so nothing touches .NET off the UI thread) ---------
    def get_app_info(self):
        return {"version": VERSION, "title": TITLE}

    def _hwnd(self):
        if not getattr(self, "_hwnd_cache", None) or not IsWindow(self._hwnd_cache):
            self._hwnd_cache = winframe.main_window(TITLE, os.getpid())
        return self._hwnd_cache

    def _apply_frame_theme(self, window=None):
        """Sets the frame (dark mode, border) to a theme's window palette; the setting in force when not given.
        Plain Win32, so it is safe off the UI thread. Does nothing before the window exists; never raises."""
        try:
            h = getattr(self, "_hwnd_cache", None)
            if not h or not IsWindow(h):
                return
            winframe.apply_theme(h, window or theme.preset(_theme_now())["window"])
        except Exception:
            pass

    def theme_changed(self, effective):
        """The page saw Windows change its app colour mode (Follow Windows): the frame follows. True."""
        if effective in theme.EFFECTIVE:
            self._apply_frame_theme(theme.preset(effective)["window"])
        return True

    def win_minimize(self):
        h = self._hwnd()
        if h:
            user32.ShowWindow(h, 6)                                                # SW_MINIMIZE
        return True

    def win_toggle_maximize(self):
        """Native maximise/restore. The window has a sizing frame and a caption style (see winframe), so Windows
        maximises it to the work area and the taskbar stays visible. Returns the new state."""
        h = self._hwnd()
        if not h:
            return False
        user32.ShowWindow(h, 9 if user32.IsZoomed(h) else 3)                        # SW_RESTORE / SW_MAXIMIZE
        return bool(user32.IsZoomed(h))

    def win_is_maximized(self):
        h = self._hwnd()
        return bool(h and user32.IsZoomed(h))

    def set_dirty(self, dirty):
        """The page reports whether it has unsaved changes (only when that flips). Informational only: closing
        does not trust it, the page is always asked (see _on_closing)."""
        self._dirty = bool(dirty)
        return True

    def close_now(self):
        """Close for real (after the page's own Save / Discard decision)."""
        self._allow_close = True
        return self.win_close()

    def _on_query_end(self):
        """WM_QUERYENDSESSION (UI thread, answered yes by winframe): the FormClosing that follows must not be
        cancelled to ask the page about unsaved changes, or the user's shutdown would be blocked by Studio."""
        if not self._session_ending:
            _startup("Windows is ending the session; the window will close without asking")
        self._session_ending = True

    def _on_end_session(self, ending):
        """WM_ENDSESSION (UI thread). ending: the session really ends, else something cancelled it. Saves the
        window placement and goes: Windows stops the process soon after this returns."""
        if not ending:
            _startup("the session end was cancelled")
            self._session_ending = False
            return
        self._session_ending = True
        _remember_window(getattr(self, "_hwnd_cache", None) or 0)

    def win_close(self):
        h = self._hwnd()
        if h:
            user32.PostMessageW(h, 0x0010, 0, 0)                                    # WM_CLOSE
        return True


_STARTUP_LOG = os.path.join(DATA_DIR, "studio.log")


_T0 = None


def _startup(msg):
    """One line in studio.log: seconds since this process was created, then msg. Shows where a slow start
    spends its time (for example a launch through ZScript's ShellExecute in ZBrush 2022-2025)."""
    global _T0
    try:
        if _T0 is None:
            import win32
            _T0 = win32.process_created(os.getpid()) or time.time()
            msg += f"; started by {win32.launch_chain()}; cwd {os.getcwd()}"
        if os.path.exists(_STARTUP_LOG) and os.path.getsize(_STARTUP_LOG) > 200_000:
            os.replace(_STARTUP_LOG, _STARTUP_LOG + ".old")
        with open(_STARTUP_LOG, "a", encoding="utf-8") as f:
            now = time.time()
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now))}.{int(now * 1000) % 1000:03d} "
                    f"+{now - _T0:6.2f} s  {msg}\n")
    except Exception:
        pass


_studio_lock = threading.RLock()        # prefs, added folders and window placement all read-modify-write this file


def _read_studio_file() -> dict:
    with _studio_lock:
        try:
            with open(STUDIO_FILE, encoding="utf-8-sig") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}


STUDIO_UNREADABLE = ("studio.json could not be read just now, so nothing was changed. If it keeps happening, "
                     "fix or delete it (it is in %APPDATA%\\ZOrbit).")


def _tell_popout_theme():
    """Tells an open browser to look at the theme now, so a pick in Studio shows there at once instead of at the
    browser's next poll. No browser running is fine; so is one that does not answer."""
    try:
        hwnd = W.find_message_window(radiald.POPOUT_CLASS)
        if hwnd:
            W.send_copydata(hwnd, radiald.COPYDATA_THEME, b"")
    except Exception as e:                      # the browser's own poll still gets there
        _startup(f"browser theme nudge failed: {e!r}")


def _studio_for_update() -> dict | None:
    """studio.json to change and write back, or None when it is there but cannot be read now: writing back {} then
    would lose the window placement, the added ZBrush folders and every preference."""
    with _studio_lock:
        data = fsutil.read_json_for_update(STUDIO_FILE)
        if data is None:
            _startup("studio.json could not be read; a change was not saved")
        return data


def _write_studio_file(data: dict):
    with _studio_lock:
        os.makedirs(paths.CONFIG_DIR, exist_ok=True)
        fsutil.write_atomic(STUDIO_FILE, json.dumps(data, indent=2))


def _inside(a, b) -> bool:
    """True when folder a is folder b or inside it (case and slashes ignored). A separator is appended, so
    D:\\ZBrush 2026 beta is not taken for being inside D:\\ZBrush 2026."""
    a = os.path.normcase(os.path.normpath(str(a))).rstrip("\\/") + os.sep
    b = os.path.normcase(os.path.normpath(str(b))).rstrip("\\/") + os.sep
    return a.startswith(b)


def _on_closing(api):
    """pywebview 'closing' handler (runs synchronously on the UI thread; returning False cancels).
    Every way of closing (our button, Alt+F4, taskbar, WM_CLOSE) arrives here. The close is cancelled and the
    page is always asked, whatever set_dirty last said: the page closes at once when it has nothing unsaved,
    and shows its dialog when it has. That request must run on another thread: calling into the page from
    inside this handler would deadlock the UI thread."""
    if api._session_ending:               # Windows is shutting down: a cancelled close would block it
        _remember_window(api._hwnd())
        return True
    if api._allow_close:
        _remember_window(api._hwnd())
        return None
    now = time.time()
    if not api._ask_acked and now - api._ask_sent > 4.0:
        _remember_window(api._hwnd())
        return None                    # the page did not answer the last request: never trap the user
    api._ask_sent, api._ask_acked = now, False

    def ask():
        try:
            ok = api._window.evaluate_js(
                "window.__studioRequestClose ? window.__studioRequestClose() : false")
        except Exception:
            ok = False
        if ok:
            api._ask_acked = True
        else:                          # no dialog available: close rather than trap the user
            api._allow_close = True
            api.win_close()
    threading.Thread(target=ask, daemon=True).start()
    return False


def _remember_window(hwnd):
    """Saves the window's normal (restored) rectangle and whether it is maximised, for the next launch
    (winframe.placement_record reads it from GetWindowPlacement)."""
    try:
        rec = winframe.placement_record(hwnd)
        if not rec:
            return
        with _studio_lock:                     # read, change and write as one step
            data = _studio_for_update()
            if data is None:
                return
            data["window"] = rec
            _write_studio_file(data)
    except Exception:
        pass


def _fit_size(work_w, work_h, scale):
    """The first window's size in logical pixels: DEFAULT_SIZE, shrunk to fit a work area of work_w x work_h
    physical pixels (a 1080p laptop at 150 percent has about 1280 x 690 logical), never below MIN_SIZE."""
    margin = 16
    wd = min(DEFAULT_SIZE[0], int(work_w / scale) - margin)
    ht = min(DEFAULT_SIZE[1], int(work_h / scale) - margin)
    return {"width": max(MIN_SIZE[0], wd), "height": max(MIN_SIZE[1], ht)}


def _default_geometry(scale):
    """The window size used when no placement was saved (or it could not be used)."""
    try:
        wa = winframe._primary_work_area()
        if wa.right > wa.left and wa.bottom > wa.top:
            return _fit_size(wa.right - wa.left, wa.bottom - wa.top, scale)
    except Exception:
        pass
    return {"width": DEFAULT_SIZE[0], "height": DEFAULT_SIZE[1]}


def main():
    _startup(f"Studio {VERSION} main()")
    mutex = CreateMutexW(None, False, STUDIO_MUTEX)       # before the slow import: a second launch exits fast
    if ctypes.get_last_error() == 183:                     # already open: bring it forward
        _startup("already open: bringing it forward")
        hwnd = winframe.main_window(TITLE)
        if hwnd:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)                                             # SW_RESTORE
            else:
                user32.ShowWindow(hwnd, 5)                 # SW_SHOW: keeps a maximised window maximised
            user32.SetForegroundWindow(hwnd)
        return 0
    if not webview2.require(_startup):          # says so in a message box; without the runtime pywebview would fall back to IE
        CloseHandle(mutex)
        return 1
    try:                                                    # the first profile, before the page asks for menus
        profiles.ensure()
    except OSError as e:
        _startup(f"profiles could not be set up: {e!r}")
    import webview
    _startup("pywebview imported")
    try:                                                    # own taskbar identity and icon, not Python's
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    # pywebview makes the process system-DPI aware when it starts and scales sizes by that DPI. Doing it
    # first means the saved window pixels and the monitor checks use the same coordinates as the window.
    user32.SetProcessDPIAware()
    scale = user32.GetDpiForSystem() / 96
    min_size = MIN_SIZE
    placement = winframe.saved_window(_read_studio_file().get("window"),
                                      round(min_size[0] * scale), round(min_size[1] * scale))
    if placement:
        x, y, wd, ht, _maxed = placement
        geometry = {"x": round(x / scale), "y": round(y / scale), "width": round(wd / scale),
                    "height": round(ht / scale)}
    else:
        geometry = _default_geometry(scale)
    api = Api()
    # frameless: WinForms then counts no frame around the page, which is what winframe.custom_frame leaves
    window = webview.create_window(TITLE, url=UI_INDEX, js_api=api, **geometry, hidden=True,
                                   frameless=True, easy_drag=False,
                                   min_size=min_size, text_select=False,
                                   background_color=theme.preset(_theme_now())["window"]["background"])
    api._window = window
    window.events.closing += lambda: _on_closing(api)
    window.events.loaded += lambda: _startup("page loaded")
    winframe.enable_drag_regions()
    icon = paths.ICON if os.path.isfile(paths.ICON) else None
    webview.start(_frame_and_show, (window, placement, api),
                  debug="--debug" in sys.argv, icon=icon)                     # worker thread
    CloseHandle(mutex)
    return 0


def _frame_and_show(window, placement, api=None):
    """On pywebview's worker thread. The window was created hidden: every size change of a visible WebView2
    window flashes black, so the title bar, saved placement and maximise are all applied before it is first
    shown, and it is shown once the page has drawn (or after 3 s, so a slow page never leaves it invisible).
    api: when given, Windows shutting down or signing out is let through (see _on_closing)."""
    def on_hwnd(hwnd):
        if api is None:
            winframe.install_frame(hwnd)
            return
        api._hwnd_cache = hwnd
        winframe.install_frame(hwnd, on_query_end=api._on_query_end, on_end=api._on_end_session)
    hwnd = winframe.custom_frame(TITLE, placement, pid=os.getpid(), include_hidden=True, on_hwnd=on_hwnd,
                                 theme=theme.preset(_theme_now())["window"])
    window.events.loaded.wait(3)
    if hwnd:
        problem = winframe.frame_problem(hwnd)
        if problem:
            _startup(f"the window's resize border could not be set up: {problem}")
        maxed = bool(placement and placement[4])
        winframe.show_placed(hwnd, maxed)
        if maxed:
            # Shown maximised with plain Win32, WinForms never marks the form visible, so WebView2 keeps its page
            # hidden and draws nothing (a dark, empty window). pywebview's show() on the already maximised window
            # only fixes that state; it does not move or resize it.
            window.show()
    else:
        window.show()
    _startup("window shown")


if __name__ == "__main__":
    sys.exit(main())
