"""Brush usage, the brushes it puts into a menu's auto slots ({"auto": "brush"} items), and the recent picks.

Every brush picked from a ring scores a point, and points fade with a two-week half-life. A menu's auto slots
hold its best-scoring brushes, leaving out the brushes that menu already has as ordinary (pinned) items.

The ring should not reshuffle under the user's hand, so:
  * a brush keeps its slot (and its position) until another brush takes it;
  * a newcomer must make the top list at two evaluations in a row (one per pick) before it takes a slot,
    and it takes the slot of the lowest-scoring brush that has dropped out of the top list;
  * an empty slot fills straight away.
Fading scales every score by the same factor, so the order only changes when a pick comes in.

Recent picks are separate: every brush, alpha, material or texture picked (from a ring or from the browser) is
noted in "picks" with a count and the time of the last pick, the newest 200 kept. Nothing fades there: the
browser lists them newest first, and "most used" for anything but brushes is the plain count.

A name is keyed in lower case without spaces (norm(), as tags.json does): "Clay Buildup" and "ClayBuildup" are
one brush. Keys written with spaces by an earlier version are merged when the file is read.

%APPDATA%\\ZOrbit\\profiles\\<profile>\\usage.json (one per profile; written by the app; the Studio and the browser
write it only to forget a recent):
{"brushes": {"claybuildup": {"name": "ClayBuildup", "score": 3.2, "t": 1761550000.0}},   # score as of t
 "menus": {"<menu id>": {"slots": ["ClayBuildup", null], "pending": ["Pinch"]}},
 "picks": {"alpha:alpha_01": {"name": "Alpha_01", "count": 4, "t": 1761550000.0}}}       # key: kind:norm(name)
"""
import json
import math
import os
import shutil
import time

import fsutil
import profiles

HALF_LIFE_S = 14 * 86400
FORGET_BELOW = 0.01                    # a single pick drops out after about 3 months
PICKS_KEPT = 200                       # recent picks across all kinds; the oldest go on save


def norm(name) -> str:
    """The key of a name: lower case, no spaces (the same rule as tags.item_key)."""
    return "".join(str(name).split()).lower()


def _entries(raw: dict, section: str) -> list:
    """The (key, entry) pairs of a section of the file; a section of the wrong type has none."""
    part = raw.get(section)
    return list(part.items()) if isinstance(part, dict) else []


def _parse(raw: dict, now: float | None = None) -> tuple:
    """(brushes, menus, picks) from a usage.json-shaped dict. A bad entry is skipped, not the entries after it;
    two spellings of one name are merged (brushes: the higher faded score; picks: both counts, the newer pick)."""
    now = time.time() if now is None else now
    brushes, menus, picks = {}, {}, {}
    for k, e in _entries(raw, "brushes"):
        try:
            if isinstance(e, dict) and isinstance(e.get("name"), str):
                new = {"name": e["name"], "score": float(e["score"]), "t": float(e["t"])}
                k = norm(k)
                old = brushes.get(k)
                if old is None or Usage._faded(new, now) > Usage._faded(old, now):   # two spellings: higher score
                    brushes[k] = new
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            continue
    for mid, st in _entries(raw, "menus"):
        try:
            if isinstance(st, dict):
                menus[mid] = {"slots": [s if isinstance(s, str) else None for s in st.get("slots") or []],
                              "pending": [s for s in st.get("pending") or [] if isinstance(s, str)]}
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    for k, e in _entries(raw, "picks"):
        try:
            if isinstance(e, dict) and isinstance(e.get("name"), str):
                new = {"name": e["name"], "count": int(e["count"]), "t": float(e["t"])}
                kind, _, name = k.partition(":")
                k = f"{kind}:{norm(name)}"
                old = picks.get(k)
                if old is not None:                    # two spellings: the newer pick, with both counts
                    count = old["count"] + new["count"]
                    new = dict(new if new["t"] >= old["t"] else old, count=count)
                picks[k] = new
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            continue
    return brushes, menus, picks


def auto_count(menu) -> int:
    return sum(1 for it in menu.items if it.kind == "auto")


def _pinned(menu) -> set:
    return {norm(it.data["brush"]) for it in menu.items if it.kind == "brush"}


class Usage:
    def __init__(self, path=None):
        self.path = path or profiles.usage_file()
        self.mtime = None
        self.version = 0               # counts changes in memory too, for caches keyed on the ranking
        self.brushes = {}
        self.menus = {}
        self.picks = {}                # "kind:name" (lower case) -> {"name", "count", "t"}

    # --- file ------------------------------------------------------------------------------------
    def load(self) -> "Usage":
        """Reads the file if it changed since the last load (or save). A missing file is empty. A file that cannot
        be opened (a scanner holds it) keeps what is in memory and is tried again at the next load. A file that
        cannot be parsed is copied to usage.json.bad, keeps what is in memory and is not parsed again until it
        changes. A bad entry in a good file is skipped, not the entries after it."""
        try:
            mtime = os.stat(self.path).st_mtime
        except OSError:
            mtime = None
        if mtime == self.mtime:
            return self
        if mtime is None:
            self.mtime, self.brushes, self.menus, self.picks = None, {}, {}, {}
            self.version += 1
            return self
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raise ValueError("the top level must be an object")
        except OSError:
            return self                                # mtime stays as it was: the next load tries again
        except ValueError:
            self._keep_bad()
            self.mtime = mtime
            return self
        brushes, menus, picks = _parse(raw, time.time())
        self.mtime, self.brushes, self.menus, self.picks = mtime, brushes, menus, picks
        self.version += 1
        return self

    def _keep_bad(self) -> None:
        """Copies a file that could not be parsed to <path>.bad, so a later save does not lose it (best effort)."""
        try:
            shutil.copyfile(self.path, self.path + ".bad")
        except OSError:
            pass

    def save(self) -> None:
        now = time.time()
        self.brushes = {k: e for k, e in self.brushes.items() if self.score(k, now) >= FORGET_BELOW}
        newest = sorted(self.picks, key=lambda k: self.picks[k]["t"], reverse=True)[:PICKS_KEPT]
        self.picks = {k: self.picks[k] for k in newest}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fsutil.write_atomic(self.path, json.dumps({"brushes": self.brushes, "menus": self.menus, "picks": self.picks},
                                                  indent=1))    # a temp file per process: the Studio may write too
        self.mtime = os.stat(self.path).st_mtime

    def absorb(self, raw: dict, now: float | None = None) -> int:
        """Adds another usage dict (a usage.json an older ZOrbit wrote) into this one, in memory; save() keeps it.
        Brush scores are faded to now and summed, picks have their counts summed and keep the newer time. Names
        already here stay as they are, and so do the menus' slot states. Returns how many brushes were taken;
        anything malformed is skipped."""
        if not isinstance(raw, dict):
            return 0
        now = time.time() if now is None else now
        brushes, _, picks = _parse(raw, now)
        taken = 0
        for k, e in brushes.items():
            add = self._faded(e, now)
            if not math.isfinite(add) or add < 0:
                continue
            old = self.brushes.get(k)
            self.brushes[k] = {"name": old["name"] if old else e["name"], "score": self.score(k, now) + add, "t": now}
            taken += 1
        for k, e in picks.items():
            old = self.picks.get(k)
            if old is None:
                self.picks[k] = dict(e)
            else:
                self.picks[k] = {"name": old["name"], "count": old["count"] + e["count"], "t": max(old["t"], e["t"])}
        if brushes or picks:
            self.version += 1
        return taken

    # --- scores ----------------------------------------------------------------------------------
    @staticmethod
    def _faded(e: dict, now: float) -> float:
        return e["score"] * 0.5 ** ((now - e["t"]) / HALF_LIFE_S)

    def score(self, key: str, now: float) -> float:
        """The fading score of a brush, by its key (norm() of the name)."""
        e = self.brushes.get(key)
        return self._faded(e, now) if e else 0.0

    def record(self, name: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        k = norm(name)
        self.brushes[k] = {"name": name, "score": self.score(k, now) + 1.0, "t": now}
        self.version += 1

    def record_pick(self, kind: str, name: str, now: float | None = None) -> None:
        """Notes a pick of any kind in the recent list (a brush is counted by record() as well)."""
        now = time.time() if now is None else now
        k = f"{kind}:{norm(name)}"
        old = self.picks.get(k)
        self.picks[k] = {"name": name, "count": (old["count"] if old else 0) + 1, "t": now}
        self.version += 1

    def recent(self, kind: str, limit: int = 24) -> list:
        """[{"name", "t", "count"}] of this kind, last picked first."""
        pre = kind + ":"
        found = [e for k, e in self.picks.items() if k.startswith(pre)]
        found.sort(key=lambda e: e["t"], reverse=True)
        return [{"name": e["name"], "t": e["t"], "count": e["count"]} for e in found[:limit]]

    def forget(self, kind: str, name: str) -> bool:
        """Takes one item off the recent list (in memory; save() keeps it). True if it was there. A brush's score
        stays: that is what fills the auto slots, and forgetting a recent is only tidying a list."""
        if self.picks.pop(f"{kind}:{norm(name)}", None) is None:
            return False
        self.version += 1
        return True

    def scores_for(self, kind: str, now: float | None = None) -> dict:
        """{norm(name): score} for "most used": brushes by their fading score, the other kinds by pick count
        (they have no fading). A name with spaces is also given under its plain lower-case spelling, for pages that
        look scores up with that."""
        if kind == "brush":
            now = time.time() if now is None else now
            out = {k: self.score(k, now) for k in self.brushes}
            names = [(k, e["name"]) for k, e in self.brushes.items()]
        else:
            pre = kind + ":"
            out = {k[len(pre):]: float(e["count"]) for k, e in self.picks.items() if k.startswith(pre)}
            names = [(k[len(pre):], e["name"]) for k, e in self.picks.items() if k.startswith(pre)]
        for k, name in names:
            out.setdefault(name.lower(), out[k])
        return out

    def ranked(self, now: float) -> list:
        """Brush names, best first (ties by name, so the order is stable)."""
        keys = sorted(self.brushes, key=lambda k: (-self.score(k, now), k))
        return [self.brushes[k]["name"] for k in keys]

    def rank(self, names, now: float | None = None) -> list:
        """The given brush names, best-scoring first (ties by name); unknown brushes score 0 and come last."""
        now = time.time() if now is None else now
        return sorted(names, key=lambda n: (-self.score(norm(n), now), n.lower()))

    # --- slots -----------------------------------------------------------------------------------
    def slots(self, menu, now: float | None = None) -> list:
        """The brush in each of the menu's auto slots, in order (None: still empty). Drops brushes the menu now
        pins, fills empty slots from the ranking, and remembers the result (in memory; save() keeps it)."""
        now = time.time() if now is None else now
        n = auto_count(menu)
        st = self.menus.setdefault(menu.id, {"slots": [], "pending": []})
        taken = set(_pinned(menu))
        slots = []
        for name in (st["slots"] + [None] * n)[:n]:
            if name is not None and norm(name) in taken:
                name = None
            if name is not None:
                taken.add(norm(name))
            slots.append(name)
        free = (name for name in self.ranked(now) if norm(name) not in taken)
        slots = [s if s is not None else next(free, None) for s in slots]
        st["slots"] = slots
        return list(slots)

    def update(self, menu, now: float | None = None) -> None:
        """After a pick: lets a brush that made the top list twice in a row take a slot."""
        now = time.time() if now is None else now
        slots = self.slots(menu, now)
        st = self.menus[menu.id]
        pinned = _pinned(menu)
        top = [name for name in self.ranked(now) if norm(name) not in pinned][:len(slots)]
        top_keys = {norm(name) for name in top}
        held = {norm(s) for s in slots if s is not None}
        challengers = [name for name in top if norm(name) not in held]
        before = {norm(name) for name in st["pending"]}
        losers = sorted((i for i, s in enumerate(slots) if s is not None and norm(s) not in top_keys),
                        key=lambda i: self.score(norm(slots[i]), now))
        pending = []
        for name in challengers:
            if norm(name) in before and losers:
                slots[losers.pop(0)] = name
            else:
                pending.append(name)
        st["slots"], st["pending"] = slots, pending
        self.version += 1
