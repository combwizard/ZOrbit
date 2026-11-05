"""The text behind Copy report on Studio's Status screen: what a bug report needs, in one block, with the Windows user
name and folders hidden. Studio gathers the facts (Api.get_report); this module keeps no state."""
import ctypes
import json
import ntpath
import os
import re
import time
import urllib.parse

BUG_FORM = "https://github.com/combwizard/zorbit/issues/new"
USER = "<user>"

LOG_LINES = 100           # the most lines of one log in a report
MIN_LINES = 30            # a session shorter than this still gets the lines before it: a restart can follow the fault
LOG_CHARS = 8000          # the most text of one log: GitHub takes 65,536 characters in an issue
LINE_CHARS = 1000         # the most of one line
TAIL_BYTES = 128 * 1024   # how much of a log is read
STDERR_RECENT_S = 86400   # app_stderr.log only says something about the problem at hand when it is this new

# What the line that starts a session begins with or holds. bridge.log has none: its load line comes after the lines
# that say what failed to load.
SESSION_MARKS = {"radiald.log": "ZOrbit starting (pid", "studio.log": " main()", "popout.log": "; started by "}

# C:\Users\you is not the start of a folder called you.old, you-2 or youth, but "... in C:\Users\you." ends a sentence.
_PATH_END = r"(?!\w|[.\-]\w)"
_COMMAND = re.compile(r"\.exe\b", re.I)    # a line that runs something: logs of how the app or the browser started


def _folder_pattern(path):
    """Matches a folder however a log writes it: any case, \\ or / or the \\\\ of a repr or JSON."""
    parts = [re.escape(p) for p in re.split(r"[\\/]+", path) if p]
    return re.compile(r"[\\/]+".join(parts) + _PATH_END, re.I)


def user_names(env=None, home=None):
    """The names to hide: the account's, and its home folder's when that differs (an account renamed later). Each is
    also listed as a JSON file, a Python repr or stderr, and a file: URL would write it."""
    env = os.environ if env is None else env
    home = os.path.expanduser("~") if home is None else home
    names = {env.get("USERNAME") or "", ntpath.basename(home.rstrip("\\/"))} - {""}
    forms = {f(n) for n in names for f in (lambda n: json.dumps(n)[1:-1], lambda n: n.encode("unicode_escape").decode(),
                                           urllib.parse.quote)}
    return sorted(names | forms, key=len, reverse=True)


def short_name(path):
    """The 8.3 name Windows keeps for this folder, "" when it has none. ZScript gets paths in this form and logs them,
    and for a name with no ASCII in it (Дмитрий) only Windows knows what it is."""
    buf = ctypes.create_unicode_buffer(1024)
    if not ctypes.windll.kernel32.GetShortPathNameW(str(path), buf, 1024):
        return ""
    short = ntpath.basename(buf.value.rstrip("\\/"))
    return "" if short.lower() == ntpath.basename(str(path).rstrip("\\/")).lower() else short


def _alias_pattern(name):
    """The 8.3 alias Windows would make for a long name, as a pattern, or None when no part of it survives. John Smith
    gives JOHNSM~1, Crème CRME~1, john.smith JOHN~1.SMI."""
    if "\\" in name or "%" in name or "~" in name:                # one of the written forms above, or an alias already
        return None
    stem = name.rpartition(".")[0] or name
    base = re.sub(r"[^A-Za-z0-9!#$&'()@^_`{}-]", "", re.sub(r"[+,;=\[\]]", "_", stem))[:6]
    return re.escape(base) + r"~[0-9]+(?:\.[A-Za-z0-9]{1,3})?" if base else None


def redactor(local_appdata, home, names):
    """A function that hides the folders and names in a text. %LOCALAPPDATA% and the home folder go back to their
    variable names, longest path first. The user name becomes <user> only inside a path or on a line that runs an
    .exe, so a user called brush does not eat "brush Clay: selected"."""
    folders = sorted(((p, v) for p, v in ((local_appdata, "%LOCALAPPDATA%"), (home, "%USERPROFILE%")) if p),
                     key=lambda pv: len(pv[0]), reverse=True)
    folders = [(_folder_pattern(p), v) for p, v in folders]
    in_path, in_command = [], []
    for name in names:
        n = re.escape(name)
        in_path.append(re.compile(r"(?<=[\\/])" + n + _PATH_END, re.I))
        in_command.append(re.compile(r"(?<!\w)" + n + r"(?!\w)(?!\.exe)", re.I))
        alias = _alias_pattern(name)
        if alias:
            in_path.append(re.compile(r"(?<=[\\/])" + alias + _PATH_END, re.I))

    def clean(text):
        for pattern, var in folders:
            text = pattern.sub(lambda _: var, text)
        for pattern in in_path:
            text = pattern.sub(USER, text)
        if _COMMAND.search(text):
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if _COMMAND.search(line):
                    for pattern in in_command:
                        line = pattern.sub(USER, line)
                    lines[i] = line
            text = "\n".join(lines)
        return text
    return clean


def current_redactor():
    """The redactor for the account running this."""
    home = os.path.expanduser("~")
    return redactor(os.environ.get("LOCALAPPDATA"), home, [n for n in (*user_names(home=home), short_name(home)) if n])


def read_log(path):
    """The lines at the end of a log, or None when it cannot be read. The app and the plugin write UTF-8 and ZScript
    the ANSI code page, so a name outside ASCII has to be read right for it to be hidden at all."""
    try:
        with open(path, "rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - TAIL_BYTES))
            data = f.read()
    except OSError:
        return None
    if size > TAIL_BYTES:
        data = data.partition(b"\n")[2]          # the first line may be cut in half
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("mbcs", errors="replace")
    return text.splitlines()


def this_session(lines, mark):
    """The lines from the last one holding mark on, but at least MIN_LINES when the log has them."""
    if mark:
        for i in range(len(lines) - 1, -1, -1):
            if mark in lines[i]:
                return lines[min(i, max(0, len(lines) - MIN_LINES)):]
    return lines


def trim(lines):
    """The newest lines that fit the caps for one log."""
    kept, chars = [], 0
    for line in reversed(lines[-LOG_LINES:]):
        line = line[:LINE_CHARS]
        chars += len(line) + 1
        if chars > LOG_CHARS and kept:
            break
        kept.append(line)
    return kept[::-1]


def log_names(modern, legacy, stderr_age=None):
    """Which logs fit the setup. modern, legacy: a ZBrush 2026 and newer, or 2022 to 2025, is known. With neither known
    all of them. stderr_age: seconds since app_stderr.log was written, None when there is no such file."""
    names = ["radiald.log"]
    if modern or not legacy:
        names.append("bridge.log")
    if legacy or not modern:
        names += ["zscript_bridge.log", "zscript_hotkey.log", "zscript_launch.log"]
    names += ["popout.log", "studio.log"]
    if stderr_age is not None and stderr_age < STDERR_RECENT_S:
        names.append("app_stderr.log")
    return names


def log_sections(data_dir, modern, legacy, clean):
    """[(heading, lines)] for the logs that fit the setup. Each log is cleaned before it is cut, so a cut cannot leave
    the start of a name behind that no longer matches."""
    try:
        age = time.time() - os.path.getmtime(os.path.join(data_dir, "app_stderr.log"))
    except OSError:
        age = None
    out = []
    for name in log_names(modern, legacy, age):
        lines = read_log(os.path.join(data_dir, name))
        if lines is None:
            out.append((name, ["(no such file)"]))
            continue
        lines = trim(clean("\n".join(this_session(lines, SESSION_MARKS.get(name)))).split("\n"))
        out.append((name, lines if any(lines) else ["(empty)"]))
    return out


def zbrush_lines(all_installs, procs):
    """One line per ZBrush Studio knows, then one per running ZBrush it cannot place. procs: {pid, path (its install
    folder, None when unknown), admin ("yes", "no" or "cannot tell")}."""
    def key(p):
        return ntpath.normcase(ntpath.normpath(p))
    placed = set()
    lines = []
    for e in all_installs:
        kind = "2026 and newer" if e.get("python") else "2022 to 2025"
        here = [p for p in procs if p.get("path") and key(p["path"]) == key(e["path"])]
        placed.update(p["pid"] for p in here)
        run = "; ".join(f"running as pid {p['pid']}, administrator: {p['admin']}" for p in here) or "not running"
        lines.append(f"{e['name']} ({kind}): {e['path']}: {run}")
    for p in procs:
        if p["pid"] not in placed:
            lines.append(f"A ZBrush outside the list: pid {p['pid']}, administrator: {p['admin']}")
    return lines or ["none found"]


def library_folder_lines(folders):
    """One line per folder the user added to the library, or "<Kind>: none added". folders: {kind: [{path, exists,
    count, hidden, error}]} as Api.get_library_folders gives it."""
    lines = []
    for kind, heading in (("brush", "Brushes"), ("alpha", "Alphas"), ("material", "Materials"),
                          ("texture", "Textures")):
        rows = folders.get(kind) or []
        if not rows:
            lines.append(f"{heading}: none added")
        for row in rows:
            if row.get("error"):
                state = f"could not be read: {row['error']}"
            elif not row.get("exists"):
                state = "missing"
            else:
                state = "found"
                if row.get("count") is not None:
                    state += f", {row['count']} files"
                if row.get("hidden"):
                    state += f", {row['hidden']} hidden"
            lines.append(f"{heading}: {row['path']}: {state}")
    return lines


def bug_url(zorbit, zbrush, windows):
    """The bug form with its version fields filled in. The report is too long for a URL: it comes from the clipboard."""
    fields = {"template": "bug_report.yml", "zorbit": zorbit, "zbrush": zbrush, "windows": windows}
    return BUG_FORM + "?" + urllib.parse.urlencode({k: v for k, v in fields.items() if v})


def build(facts, sections, clean):
    """The report. facts: [(label, value)]. sections: [(heading, lines)]; a heading gets a block of its own."""
    out = ["ZOrbit report (the Windows user name and folders are hidden)", ""]
    out += [f"{label}: {value}" for label, value in facts]
    for heading, lines in sections:
        out += ["", f"--- {heading} ---", *lines]
    return clean("\n".join(out)) + "\n"
