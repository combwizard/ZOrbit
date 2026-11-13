"""ZBrush's state on the ring: what to ask the plugin, what it answered, and what that makes the ring draw.

The plugin inside ZBrush (ZBrush 2026 and later) reads a few items' state in one go, on ZBrush's main thread, when the
app posts it a window message. The app and the plugin talk through two small files and two window messages (see issue
#188, "Design", section 1):

  * zstate_query.json, written by the app (atomically): {"v": 1, "id", "time", "paths": [{"p": path, "k": kind}]}, kind
    "press", "set" or "toggle". Query is that file; paths_for() chooses the paths from a menu.
  * WM_APP_STATE (app -> the plugin's listener, wparam the query id, lparam the app's control window) asks the plugin to
    answer the query it finds in the file.
  * zstate.json, written by the plugin (atomically): the state of each path asked ("ok", "disabled", "missing" or
    "error", the value, for a Set the slider's range), a few facts about ZBrush (extras), and "pick", the id of the last
    request the plugin carried out. Snapshot is that file, parse_snapshot() reads it.
  * WM_APP_STATE_READY (the plugin -> the app's control window, wparam the snapshot id) says the file is new.

Nothing here waits. Channel asks after the ring is on screen, keeps one question in flight, and hands the ring marks for
what it knows: Cache holds the entries of the snapshots, drawable only while they are fresh and not older than the last
pick, and marks_for() turns a menu's items into Mark objects, one per item (a pip lit or hollow on a Toggle or on the Set
slot whose value is the current one, a value chip on a Set, a dimmed slot for an item ZBrush does not have or has greyed).
With no listener, an old plugin, or the setting off, nothing is asked and Channel.marks() gives None: the ring is as it
was.

This module needs no Windows calls: Channel is handed the function that posts a window message, the windows, the data
folder and the clocks, and never imports radiald.
"""
import collections
import json
import math
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal

VERSION = 1                                  # "v" of both files
WM_APP = 0x8000                              # win32.WM_APP (tests check the two agree)
WM_APP_STATE = WM_APP + 2                    # app -> the plugin's listener: answer the query in zstate_query.json
WM_APP_STATE_READY = WM_APP + 19             # the plugin -> the app's control window: zstate.json is new
QUERY_FILE = "zstate_query.json"
STATE_FILE = "zstate.json"
MAX_PATHS = 128                              # paths in one query
MAX_FILE = 256 * 1024                        # a snapshot file over this is refused
CACHE_TTL_S = 30.0                           # an entry older than this is not drawn
LOST_S = 2.0                                 # a question with no answer after this long counts as lost
FAN_DEPTH = 3                                # fans inside fans whose items are queried (ring.FAN_DEPTH)
KINDS = ("press", "set", "toggle")           # the item kinds that are queried
_RANK = {"press": 0, "toggle": 1, "set": 2}  # a path asked for twice is asked as the kind that tells the most
STATUSES = ("ok", "disabled", "missing", "error")
_ASSET_MENUS = ("tag:", "recent:")           # synthetic fans of assets and files: nothing in them is queried
_KEPT_QUERIES = 8                            # queries whose paths are remembered, to tell a late reply's keys
_MAX_HELD = 512                              # entries the cache keeps before it drops the old ones
_EXTRA_STR = ("tool", "brush", "brush_file", "material")
_EXTRA_BOOL = ("edit", "edit_enabled")


# --- what to ask ---------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Query:
    """One question: the paths to read, each with how the ring uses it. paths: a tuple of (path, kind)."""
    id: int
    time: float
    paths: tuple = ()

    def to_dict(self) -> dict:
        return {"v": VERSION, "id": self.id, "time": self.time,
                "paths": [{"p": p, "k": k} for p, k in self.paths]}

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


def _item_path(it):
    """(path, kind) of a Press, Set or Toggle item, else None."""
    if it.kind not in KINDS:
        return None
    p = it.data.get(it.kind)
    return (p, it.kind) if isinstance(p, str) and p else None


def paths_for(menu, resolve, cap=MAX_PATHS) -> list:
    """The paths to ask about for a menu, as (path, kind) pairs, in order: the menu's own press, set and toggle items;
    then the items of the fan submenus, down to FAN_DEPTH; then the items of the ring submenus one level down (they ask
    again when they open: this only warms their first frame). A path used twice is asked once, as the kind that tells
    the most (set over toggle over press). Steps, asset, capture, file and tag items are never queried. At most cap paths.
    resolve(menu_id) gives a submenu as expand.Expander.resolve does (None if there is none)."""
    got = {}                                 # path -> kind, in the order the paths first appear

    def take(items):
        for it in items:
            pk = _item_path(it)
            if pk is None:
                continue
            p, k = pk
            if p not in got:
                got[p] = k
            elif _RANK[k] > _RANK[got[p]]:
                got[p] = k

    def sub(item):
        mid = item.data.get("menu") if item.kind == "menu" else None
        if not isinstance(mid, str) or mid.startswith(_ASSET_MENUS):
            return None
        try:
            return resolve(mid)
        except Exception:                    # a menu that cannot be built is not a reason to stop the ring
            return None

    take(menu.items)
    rings = []                               # ring submenus found on the way: handled last
    seen_rings = set()

    def fans(m, depth, path):
        for it in m.items:
            s = sub(it)
            if s is None or not s.items or s.id in path:
                continue
            if getattr(s, "fan", False):
                if depth < FAN_DEPTH:
                    take(s.items)
                    fans(s, depth + 1, path | {s.id})
            elif s.id != menu.id and s.id not in seen_rings:
                seen_rings.add(s.id)
                rings.append(s)

    fans(menu, 0, frozenset((menu.id,)))
    for r in rings:
        take(r.items)
    return list(got.items())[:cap]


# --- what the plugin answered --------------------------------------------------------------------------------------
class SnapshotError(ValueError):
    """zstate.json cannot be used: the message says why."""


@dataclass(frozen=True)
class Entry:
    """The state of one path. status: "ok", "disabled", "missing" or "error". value: the number a set or toggle has now
    (None when it has none, or the file's value was not a plain number). lo, hi: a slider's range, else None."""
    status: str
    value: float | None = None
    lo: float | None = None
    hi: float | None = None


@dataclass(frozen=True)
class Snapshot:
    id: int
    pid: int
    session: str = ""
    pick: int = 0                            # the id of the last request the plugin carried out before this snapshot
    time: float = 0.0
    ms: float = 0.0
    truncated: bool = False
    extras: dict = field(default_factory=dict)    # tool, brush, brush_file, material, edit, edit_enabled (those that were valid)
    items: dict = field(default_factory=dict)     # path -> Entry

    def only(self, asked):
        """The snapshot with only the paths that were asked for: the app never trusts a file's keys."""
        asked = set(asked)
        return Snapshot(self.id, self.pid, self.session, self.pick, self.time, self.ms, self.truncated, self.extras,
                        {p: e for p, e in self.items.items() if p in asked})


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _number(x):
    """x as a float when it is a finite number (not a bool, a string or NaN), else None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    try:
        f = float(x)
    except OverflowError:
        return None
    return f if math.isfinite(f) else None


def _entry(raw) -> Entry:
    if not isinstance(raw, dict):
        return Entry("error")
    status = raw.get("s")
    if status not in STATUSES:
        status = "error"                     # drawn neutral
    return Entry(status, _number(raw.get("v")), _number(raw.get("min")), _number(raw.get("max")))


def parse_snapshot(raw, asked=None) -> Snapshot:
    """The snapshot in the text or bytes of zstate.json. Raises SnapshotError for a file over MAX_FILE bytes, text that
    is not JSON, an object that is not one, a "v" other than 1, or an id or pid that is not a whole number. A value that
    is not a plain finite number (a bool, a string, NaN) is dropped from its entry; a status the app does not know
    becomes "error". asked: the paths the query had; the file's other keys are dropped (all are kept when it is None)."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8", "replace")
    if len(raw) > MAX_FILE:
        raise SnapshotError(f"the file is over {MAX_FILE // 1024} KB")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError) as e:    # UnicodeDecodeError and JSONDecodeError are both ValueErrors
        raise SnapshotError(f"not JSON ({e.__class__.__name__})") from None
    if not isinstance(data, dict):
        raise SnapshotError("not an object")
    if not _is_int(data.get("v")) or data["v"] != VERSION:
        raise SnapshotError(f"v is {data.get('v')!r}, not {VERSION}")
    if not _is_int(data.get("id")) or not _is_int(data.get("pid")):
        raise SnapshotError("id or pid is not a whole number")
    items = data.get("items")
    items = items if isinstance(items, dict) else {}
    extras_raw = data.get("extras")
    extras_raw = extras_raw if isinstance(extras_raw, dict) else {}
    extras = {k: extras_raw[k] for k in _EXTRA_STR if isinstance(extras_raw.get(k), str)}
    extras.update({k: extras_raw[k] for k in _EXTRA_BOOL if isinstance(extras_raw.get(k), bool)})
    session = data.get("session")
    snap = Snapshot(id=data["id"], pid=data["pid"], session=session if isinstance(session, str) else "",
                    pick=data["pick"] if _is_int(data.get("pick")) else 0,
                    time=_number(data.get("time")) or 0.0, ms=_number(data.get("ms")) or 0.0,
                    truncated=data.get("truncated") is True, extras=extras,
                    items={p: _entry(e) for p, e in items.items() if isinstance(p, str)})
    return snap.only(asked) if asked is not None else snap


def accept(snap, *, newest, pid, picked=0) -> bool:
    """Whether the app takes this snapshot: it came from the ZBrush the query went to (pid), and its id is the newest
    asked (newest), or it is the plugin's refresh after a pick of ours (picked is the id of our last pick: the snapshot
    saw it carried out, and answers a query we asked, so no later than the newest)."""
    if not newest or snap.pid != pid:
        return False
    if snap.id == newest:
        return True
    return picked > 0 and snap.pick >= picked and 0 < snap.id < newest


# --- what is known -------------------------------------------------------------------------------------------------
@dataclass
class _Held:
    entry: Entry
    at: float                                # when the app merged it (its clock)
    pick: int                                # the pick the snapshot it came from had seen


class Cache:
    """The entries of the snapshots so far, one per path, from the ZBrush that answered last. An entry is drawable when
    it is from the ZBrush in front (pid), under ttl seconds old, and not older than the last pick: picked(seq) is told
    of each pick, and an entry whose snapshot had not yet seen pick seq (its "pick" is lower) stays undrawable until a
    newer snapshot replaces it. A different pid or session (ZBrush was restarted) drops everything."""

    def __init__(self, ttl=CACHE_TTL_S):
        self.ttl = ttl
        self.pid = 0
        self.session = ""
        self.floor = 0                       # the id of the last pick sent
        self._held = {}

    def merge(self, snap, now):
        if (snap.pid, snap.session) != (self.pid, self.session):
            self._held.clear()
            self.pid, self.session = snap.pid, snap.session
            self.floor = 0                   # the picks counted so far went to another ZBrush
        for p, e in snap.items.items():
            self._held[p] = _Held(e, now, snap.pick)
        if len(self._held) > _MAX_HELD:
            self._held = {p: h for p, h in self._held.items() if now - h.at < self.ttl}

    def picked(self, seq):
        self.floor = max(self.floor, seq)

    def get(self, path, pid, now):
        """The entry for path when it may be drawn, else None."""
        h = self._held.get(path)
        if h is None or pid != self.pid or now - h.at >= self.ttl or h.pick < self.floor:
            return None
        return h.entry

    def clear(self):
        self._held.clear()
        self.pid, self.session, self.floor = 0, "", 0


# --- what to draw --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Mark:
    """What the ring adds to one slot. lit: True (a filled pip and an outline), False (a hollow pip) or None (no pip).
    value_text: the text of the value chip, or None. dim: the slot is drawn faint (the item is missing or disabled)."""
    lit: bool | None = None
    value_text: str | None = None
    dim: bool = False


def _own_places(x) -> int:
    """How many decimals a number is written with (64.0 and 100 have none, 0.25 has two), at most 3."""
    f = _number(x)
    if f is None:
        return 0
    exp = Decimal(repr(f)).normalize().as_tuple().exponent
    return min(3, max(0, -exp)) if isinstance(exp, int) else 0


def _trim(s: str) -> str:
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _render(v, lo, hi, target=None):
    """(text, half): the text of v for the chip and half of the last digit it shows, in v's own units."""
    v = _number(v)
    if v is None:
        return "", 0.0
    lo, hi = _number(lo), _number(hi)
    if lo is not None and hi is not None and hi > lo:
        span = hi - lo
        base = 0 if span >= 100 else 1 if span >= 10 else 2 if span >= 1 else 3
        places = min(3, max(base, _own_places(target)))
    else:
        places = 2                           # no range: at most two decimals
    for p in range(places, -1, -1):
        shown = f"{v:.{p}f}"
        if abs(float(shown)) >= 10000:
            break
        text = _trim(shown)
        if len(text) <= 5:
            return text, 0.5 * 10 ** -p
    for unit, div in (("k", 1e3), ("M", 1e6), ("G", 1e9)):
        for p in (1, 0):
            text = _trim(f"{v / div:.{p}f}") + unit
            if len(text) <= 5:
                return text, 0.5 * div * 10 ** -p
    mantissa, _, exp = f"{v:.0e}".partition("e")      # beyond any slider: the least that fits, as -1e12
    return f"{mantissa}e{int(exp)}", abs(v)


def format_value(v, lo=None, hi=None, target=None) -> str:
    """The text of a slider's value for the chip. With a range (lo, hi): a span of 100 or more gives no decimals, 10 or
    more one, 1 or more two, else three; at least as many decimals as the slot's own target has; trailing zeros are
    removed. 10000 or more is written 12.5k. At most 5 characters. With no range, at most 2 decimals."""
    return _render(v, lo, hi, target)[0]


def _matches(v, lo, hi, target) -> bool:
    """The current value is the slot's target, within half of the last digit the chip shows."""
    t = _number(target)
    if t is None:
        return False
    half = _render(v, lo, hi, target)[1]
    return abs(v - t) <= half + 1e-9 * max(1.0, abs(t))


def marks_for(menu, cache, pid, now):
    """The marks for a menu's items from what the cache may draw: a list as long as menu.items holding a Mark or None for
    each item, or None when no item gets a mark.
      * Press: dimmed when ZBrush has no such item or it is disabled, else no mark.
      * Toggle: lit (a filled pip) when its value is not 0, hollow when it is 0, no pip without a known value.
      * Set: a chip with the current value, and lit when the slot's target is the current value (never hollow, so a row
        of presets lights only the one that is on). When several Set slots of the menu use one path, no chip is shown.
      * Any of them dimmed when missing or disabled. An "error" entry is drawn neutral. Steps and every other kind never
        get a mark."""
    sets = collections.Counter(p for p, k in (pk for pk in map(_item_path, menu.items) if pk) if k == "set")
    out, any_mark = [], False
    for it in menu.items:
        pk = _item_path(it)
        e = cache.get(pk[0], pid, now) if pk else None
        m = None
        if e is not None and e.status != "error":
            dim = e.status in ("missing", "disabled")
            kind = pk[1]
            if kind == "toggle":
                lit = None if e.value is None else e.value != 0
                m = Mark(lit, None, dim) if (dim or lit is not None) else None
            elif kind == "set":
                text, lit = None, None
                if e.value is not None:
                    if sets[pk[0]] == 1:
                        text = _render(e.value, e.lo, e.hi, it.data.get("value"))[0]
                    lit = True if _matches(e.value, e.lo, e.hi, it.data.get("value")) else None
                m = Mark(lit, text, dim) if (dim or lit or text) else None
            else:
                m = Mark(None, None, True) if dim else None
        any_mark = any_mark or m is not None
        out.append(m)
    return out if any_mark else None


# --- the conversation ----------------------------------------------------------------------------------------------
class Channel:
    """Asks the plugin, takes its answers and hands the ring marks. It does no waiting and posts at most one message while
    a question is unanswered.

    post(hwnd, msg, wparam, lparam): posts a window message and says whether it was posted (win32.PostMessageW).
    ctrl: the app's control window, passed as lparam so the plugin knows where to answer. data_dir: the folder of the two
    files. clock: a monotonic clock in seconds; wall: the wall clock written to the query. log: told one line at a time."""

    def __init__(self, post, ctrl, data_dir, clock=time.monotonic, wall=time.time, log=None):
        self.post = post
        self.ctrl = ctrl
        self.data_dir = data_dir
        self.clock = clock
        self.wall = wall
        self.log = log or (lambda msg: None)
        self.cache = Cache()
        self.pid = 0                         # the ZBrush the ring was last opened for; 0: nothing to draw
        self._id = 0                         # the id of the newest query written
        self._queries = collections.OrderedDict()    # id -> the paths asked, for the last few queries
        self._at = 0.0                       # when the newest query was written
        self._flight = None                  # (when, listener key) of the message posted and not yet answered
        self._listener = None
        self._asked_pid = 0                  # the ZBrush the newest query went to
        self._picked = 0                     # the id of the last pick sent
        self._said = set()                   # (what, who) pairs already logged: a line once per ZBrush

    # --- asking
    def ask(self, menu, resolve, *, pid, listener, capable, enabled=True) -> bool:
        """Writes the query for the menu and posts WM_APP_STATE, unless one question is already waiting for its answer
        (then only the file is rewritten: the message in flight answers the newest query). Called after the ring is shown.
        pid: the ZBrush in front. listener: its verified listener window, or None. capable: its listener.json says
        "state": 1. enabled: bridge.show_state. Without all four nothing is written or posted and marks() gives None.
        Returns whether a question is now waiting."""
        self.pid = 0
        if not enabled or not capable or listener is None or not pid:
            return False
        self.pid = pid                       # the ring draws from the cache for this ZBrush even if nothing is asked
        paths = paths_for(menu, resolve)
        if not paths:
            return False
        now = self.clock()
        key = getattr(listener, "value", listener)
        waiting = self._flight is not None and self._flight[1] == key and now - self._flight[0] < LOST_S
        if self._flight is not None and not waiting and self._flight[1] == key:
            self._note("lost", pid, f"ZBrush state: no answer from pid {pid} in {LOST_S:g} s; asking again")
        q = Query(self._id + 1, self.wall(), tuple(paths))
        try:
            self._write(q)
        except OSError as e:
            self._note("write", pid, f"ZBrush state: could not write {QUERY_FILE}: {e!r}")
            return False
        self._id = q.id
        self._queries[q.id] = frozenset(p for p, _ in q.paths)
        while len(self._queries) > _KEPT_QUERIES:
            self._queries.popitem(last=False)
        self._at, self._asked_pid, self._listener = now, pid, listener
        if waiting:
            return True
        return self._post(now, key)

    def _post(self, now, key) -> bool:
        if self.post(self._listener, WM_APP_STATE, self._id, self.ctrl):
            self._flight = (now, key)
            return True
        self._flight = None
        self._note("post", self._asked_pid, f"ZBrush state: could not post to the listener of pid {self._asked_pid}")
        return False

    def _write(self, q):
        os.makedirs(self.data_dir, exist_ok=True)
        path = os.path.join(self.data_dir, QUERY_FILE)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(q.to_json())
        os.replace(tmp, path)                # atomic: the plugin never sees half a query

    def picked(self, seq):
        """A pick with this id was sent: what the cache knew is not drawn until the plugin's refresh has seen it."""
        self._picked = max(self._picked, seq)
        self.cache.picked(seq)

    # --- answers
    def on_ready(self, snapshot_id=0) -> bool:
        """The plugin posted WM_APP_STATE_READY (wparam snapshot_id). Reads zstate.json and keeps it if it is the answer to
        the newest query, or the refresh after a pick. Returns True when the cache took new entries: the ring should draw
        its marks again. Anything else (an old query's answer, another ZBrush, a bad file) is ignored."""
        if not self._id or snapshot_id > self._id:
            return False
        try:
            snap = parse_snapshot(self._read())
        except SnapshotError as e:
            self._note("bad", self._asked_pid, f"ZBrush state: {STATE_FILE} ignored: {e}")
            return False
        if snap.pid != self._asked_pid:
            return False
        if not accept(snap, newest=self._id, pid=self._asked_pid, picked=self._picked) or snap.id not in self._queries:
            if 0 < snap.id < self._id and self._flight is not None:
                self._post(self.clock(), self._flight[1])    # the plugin is free: it answers the newest query now
            return False
        now = self.clock()
        snap = snap.only(self._queries[snap.id])
        self.cache.merge(snap, now)
        if snap.id == self._id:
            self._flight = None
        self._timing(snap, now)
        return True

    def _read(self) -> bytes:
        try:
            with open(os.path.join(self.data_dir, STATE_FILE), "rb") as f:
                return f.read(MAX_FILE + 1)
        except OSError:
            return b""

    def _timing(self, snap, now):
        who = (snap.pid, snap.session)
        if snap.truncated:
            self._note("truncated", who, f"ZBrush state: the plugin stopped at its time limit after {len(snap.items)} paths")
        for p, e in snap.items.items():
            if e.status == "missing":
                self._note("missing:" + p, who, f"ZBrush state: {p!r} is not in ZBrush (or not there now); drawn dimmed")
        self._note("timing", who, f"ZBrush state: answered in {1000 * (now - self._at):.0f} ms "
                                  f"(plugin {snap.ms:g} ms, {len(snap.items)} paths)")

    def _note(self, what, who, msg):
        """Logs msg once for this (what, who)."""
        if (what, who) not in self._said and len(self._said) < 400:
            self._said.add((what, who))
            self.log(msg)

    # --- drawing
    def marks(self, menu):
        """What the ring takes as marks=: the list of Mark or None for the menu's items, or None. Cheap: it reads the
        cache only."""
        if not self.pid:
            return None
        return marks_for(menu, self.cache, self.pid, self.clock())
