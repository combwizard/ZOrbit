"""Commands from other programs: ZOrbit.exe --open, --pick, --press, --set, --toggle, --browser and --profile find the
ZOrbit app that is running, pass it the command as WM_COPYDATA and quit. They never start a second app and show no
window. A Stream Deck, a tablet's software, AutoHotkey or a script can all run a program.

Imports only what a button press can afford: main.py runs this before anything heavy. radiald.py checks what arrives
with check(), because any program can send this message.

Exit code: 0 the app took the command, 1 it refused (or the arguments are wrong), 2 no app answered.
"""
import json
import math
import sys

OPTIONS = ("--open", "--pick", "--press", "--set", "--toggle", "--browser", "--profile")
ASSET_KINDS = ("brush", "alpha", "material", "texture")       # config.ASSET_KINDS, without importing it
APP_CLASS = "ZOrbitControl"                                    # the app's message-only control window
COPYDATA = 2                                                   # dwData of a command (radiald.py lists the others)
OK, REFUSED, NO_APP = 0, 1, 2
WAIT_MS = 2000                                                 # the app may be busy drawing a ring or handing off
MAX_TEXT = 200
MAX_VALUE = 1e12                                               # far past any ZBrush slider; a bigger one is a mistake
USAGE = ("Use one of: --open <menu>, --pick brush|alpha|material|texture:<name>, --press <item path>, "
         "--set <item path> <value>, --toggle <item path>, --browser [--kind <kind>] [--tag <tag>], "
         "--profile <name>|next")


class CommandError(ValueError):
    pass


def _good_text(text) -> bool:
    return isinstance(text, str) and 0 < len(text) <= MAX_TEXT and not any(ord(c) < 32 for c in text)


def good_name(name) -> bool:
    """A brush, alpha, material or texture name: a name in ZBrush, never a path."""
    return (isinstance(name, str) and 0 < len(name) <= 120 and not any(c in name for c in "\\/:") and ".." not in name
            and not any(ord(c) < 32 for c in name))


def _good_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and abs(value) <= MAX_VALUE
    except OverflowError:                                      # an int too big for a float
        return False


def _number(text):
    try:
        value = float(text)
    except ValueError:
        raise CommandError(f"{text!r} is not a number.") from None
    if not _good_number(value):
        raise CommandError(f"{text!r} is not a number ZBrush could use.")
    return int(value) if value.is_integer() else value


def parse(args) -> dict:
    """The command for the arguments after ZOrbit.exe. Raises CommandError when they make no sense."""
    if not args or args[0] not in OPTIONS:
        raise CommandError(USAGE)
    option, rest = args[0], list(args[1:])
    if option == "--browser":
        msg = {"v": 1, "op": "browser", "kind": None, "tag": None}
        while rest:
            flag, value = rest[0], rest[1] if len(rest) > 1 else None
            if flag not in ("--kind", "--tag") or value is None:
                raise CommandError(USAGE)
            msg[flag[2:]] = value
            rest = rest[2:]
    else:
        count = 2 if option == "--set" else 1
        if len(rest) != count:
            raise CommandError(USAGE)
        if option == "--open":
            msg = {"v": 1, "op": "open", "menu": rest[0]}
        elif option == "--profile":
            msg = {"v": 1, "op": "profile", "name": rest[0]}
        elif option == "--pick":
            kind, sep, name = rest[0].partition(":")
            if not sep:
                raise CommandError("--pick needs a kind and a name, such as brush:ClayBuildup.")
            msg = {"v": 1, "op": "pick", "kind": kind, "name": name}
        elif option == "--set":
            msg = {"v": 1, "op": "set", "path": rest[0], "value": _number(rest[1])}
        else:
            msg = {"v": 1, "op": option[2:], "path": rest[0]}
    problem = check(msg)
    if problem:
        raise CommandError(problem)
    return msg


def check(msg) -> str | None:
    """Why this command cannot be right, whatever state the app is in; None when it is well formed."""
    if not isinstance(msg, dict) or msg.get("v") != 1:
        return "Not a command."
    op = msg.get("op")
    if op == "open":
        return None if _good_text(msg.get("menu")) else "That is not a menu id."
    if op == "pick":
        if msg.get("kind") not in ASSET_KINDS:
            return f"The kind must be one of {', '.join(ASSET_KINDS)}."
        return None if good_name(msg.get("name")) else "That is not a name: it cannot be empty or a path."
    if op in ("press", "set", "toggle"):
        if not _good_text(msg.get("path")):
            return "That is not an item path."
        if op == "set":
            if not _good_number(msg.get("value")):
                return "The value must be a number ZBrush could use."
        return None
    if op == "browser":
        kind, tag = msg.get("kind"), msg.get("tag")
        if kind is not None and kind not in ASSET_KINDS:
            return f"The kind must be one of {', '.join(ASSET_KINDS)}."
        return None if tag is None or _good_text(tag) else "That is not a tag."
    if op == "profile":
        return None if _good_text(msg.get("name")) else "That is not a profile name."
    return "Not a command."


def describe(msg) -> str:
    """The command for the log. Control characters come out escaped."""
    if not isinstance(msg, dict):
        return repr(msg)[:120]
    return repr({k: v for k, v in msg.items() if k != "v"})[:300]


def _say(text) -> None:
    """The exe has no console, so there is only somewhere to say it when the output was redirected."""
    if sys.stderr is not None:
        try:
            print(f"ZOrbit: {text}", file=sys.stderr)
        except (OSError, ValueError):
            pass


def main(args) -> int:
    try:
        msg = parse(args)
    except CommandError as e:
        _say(e)
        return REFUSED
    import win32 as W
    hwnd = W.find_message_window(APP_CLASS)
    if not hwnd:
        _say("ZOrbit is not running.")
        return NO_APP
    answer = W.send_copydata(hwnd, COPYDATA, json.dumps(msg).encode("utf-8"), timeout_ms=WAIT_MS)
    if answer is None:
        _say("ZOrbit did not answer. It may be busy, or running as administrator when this is not.")
        return NO_APP
    if answer != 1:
        _say("ZOrbit refused the command. radiald.log says why.")
        return REFUSED
    return OK
