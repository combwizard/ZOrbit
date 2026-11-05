"""The Tool, Project and Layout items, {"tool": "<.ztl file>"}, {"project": "<.zpr file or folder>"} and
{"layout": "<.cfg file>"}: which file the pick names.

The app turns the pick into the general file action of the bridges, {"filepress": button, "file": path}: ZBrush is
told the next file name, then the button is pressed, and the file is read with no dialog. Tool:Load Tool takes a .ZTL,
File:Open a .ZPR, Preferences:Config:Load Ui a UI layout (.cfg). A layout lasts until ZBrush closes: nothing here
presses Store Config. File:Open over a project with unsaved changes still shows ZBrush's own "save changes?" box and
waits for the answer: nothing here works around it.

A project given as a folder means the newest .zpr directly in it (not in its subfolders), by modified time, a tie going
to the name that sorts last. It is looked up at each pick, so a project saved since needs no change to the menu.
A file that is not there is not an error when the menus load (a drive may be unplugged), only when it is picked.
"""
import os

import config as C
import zscript_bridge

BUTTONS = {"tool": "Tool:Load Tool", "project": "File:Open", "layout": "Preferences:Config:Load Ui"}
_VERBS = {"tool": "loads ", "project": "opens ", "layout": "loads the layout "}


class FileItemError(Exception):
    """kind "file": the file is not there; "folder": the project folder is not there or cannot be read; "empty": it has
    no .zpr; "name" and "long": ZBrush 2022-2025 cannot be given the path (see zscript_bridge.legacy_path_problem).
    reason is the line for the log."""

    def __init__(self, kind, reason):
        super().__init__(reason)
        self.kind, self.reason = kind, reason


def forward(p) -> str:
    return str(p).replace("\\", "/")


def _kind(action) -> str:
    return next(k for k in C.FILE_EXTS if k in action)


def _newest(folder) -> str:
    """The newest .zpr directly in folder; FileItemError when there is none."""
    ext, best = C.FILE_EXTS["project"], None
    try:
        with os.scandir(folder) as entries:
            for e in entries:
                try:
                    if e.name.lower().endswith(ext) and e.is_file():
                        key = (e.stat().st_mtime_ns, e.name.casefold(), e.name)
                        if best is None or key > best[0]:
                            best = (key, e.path)
                except OSError:
                    continue                  # an entry that vanished or cannot be read is not the newest
    except OSError as e:
        what = "is not there" if isinstance(e, FileNotFoundError) else (
            "is not a folder" if isinstance(e, NotADirectoryError) else f"cannot be read: {e}")
        raise FileItemError("folder", f"project folder {folder!r} {what}") from e
    if best is None:
        raise FileItemError("empty", f"project folder {folder!r} has no {ext} file in it")
    return best[1]


def resolve(action, legacy=False):
    """(button, path) for a Tool, Project or Layout action: the button to press and the file ZBrush is told to use, with
    forward slashes. legacy: the ZBrush in front is a 2022-2025 one, whose plugin must be given an ASCII path.
    Raises FileItemError."""
    kind = _kind(action)
    text = str(action[kind]).strip()
    if kind == "project" and C.project_is_folder(text):
        path = _newest(text)
    elif os.path.isfile(text):
        path = text
    else:
        raise FileItemError("file", f"{kind} file {text!r} is not there")
    problem = zscript_bridge.legacy_path_problem(path) if legacy else None
    if problem:
        why, what = problem
        raise FileItemError(why, f"{kind} {text!r}: ZBrush 2022-2025 {what}")
    return BUTTONS[kind], forward(path)


def describe(action) -> str:
    """What the item would do now, for --check."""
    kind = _kind(action)
    text = forward(str(action[kind]).strip())
    if kind == "project" and C.project_is_folder(text):
        try:
            return f"opens the newest of {text}: {os.path.basename(resolve(action)[1])}"
        except FileItemError as e:
            return f"opens the newest of {text}, " + ("no .zpr there" if e.kind == "empty" else "not there")
    return _VERBS[kind] + text + ("" if os.path.isfile(text) else ", not there")
