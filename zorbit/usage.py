"""Brush usage, and the brushes it puts into a menu's auto slots ({"auto": "brush"} items).

Every brush picked from a ring scores a point, and points fade with a two-week half-life. A menu's auto slots
hold its best-scoring brushes, leaving out the brushes that menu already has as ordinary (pinned) items.

The ring should not reshuffle under the user's hand, so:
  * a brush keeps its slot (and its position) until another brush takes it;
  * a newcomer must make the top list at two evaluations in a row (one per pick) before it takes a slot,
    and it takes the slot of the lowest-scoring brush that has dropped out of the top list;
  * an empty slot fills straight away.
Fading scales every score by the same factor, so the order only changes when a pick comes in.

%LOCALAPPDATA%\\ZOrbit\\usage.json (written by the app only):
{"brushes": {"claybuildup": {"name": "ClayBuildup", "score": 3.2, "t": 1761550000.0}},   # score as of t
 "menus": {"<menu id>": {"slots": ["ClayBuildup", null], "pending": ["Pinch"]}}}
"""
import json
import os
import time

import paths

USAGE_FILE = os.path.join(paths.DATA_DIR, "usage.json")
HALF_LIFE_S = 14 * 86400
FORGET_BELOW = 0.01                    # a single pick drops out after about 3 months


def auto_count(menu) -> int:
    return sum(1 for it in menu.items if it.kind == "auto")


def _pinned(menu) -> set:
    return {it.data["brush"].lower() for it in menu.items if it.kind == "brush"}


class Usage:
    def __init__(self, path=USAGE_FILE):
        self.path = path
        self.mtime = None
        self.brushes = {}
        self.menus = {}

    # --- file ------------------------------------------------------------------------------------
    def load(self) -> "Usage":
        """Reads the file if it changed since the last load (or save). A missing or broken file is empty."""
        try:
            mtime = os.stat(self.path).st_mtime
        except OSError:
            mtime = None
        if mtime == self.mtime:
            return self
        self.mtime, self.brushes, self.menus = mtime, {}, {}
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
            for k, e in (raw.get("brushes") or {}).items():
                if isinstance(e, dict) and isinstance(e.get("name"), str):
                    self.brushes[k] = {"name": e["name"], "score": float(e["score"]), "t": float(e["t"])}
            for mid, st in (raw.get("menus") or {}).items():
                if isinstance(st, dict):
                    self.menus[mid] = {"slots": [s if isinstance(s, str) else None for s in st.get("slots") or []],
                                       "pending": [s for s in st.get("pending") or [] if isinstance(s, str)]}
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass
        return self

    def save(self) -> None:
        now = time.time()
        self.brushes = {k: e for k, e in self.brushes.items() if self.score(k, now) >= FORGET_BELOW}
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"brushes": self.brushes, "menus": self.menus}, f, indent=1)
        os.replace(tmp, self.path)
        self.mtime = os.stat(self.path).st_mtime

    # --- scores ----------------------------------------------------------------------------------
    def score(self, key: str, now: float) -> float:
        e = self.brushes.get(key)
        return e["score"] * 0.5 ** ((now - e["t"]) / HALF_LIFE_S) if e else 0.0

    def record(self, name: str, now: float | None = None) -> None:
        now = time.time() if now is None else now
        k = name.lower()
        self.brushes[k] = {"name": name, "score": self.score(k, now) + 1.0, "t": now}

    def ranked(self, now: float) -> list:
        """Brush names, best first (ties by name, so the order is stable)."""
        keys = sorted(self.brushes, key=lambda k: (-self.score(k, now), k))
        return [self.brushes[k]["name"] for k in keys]

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
            if name is not None and name.lower() in taken:
                name = None
            if name is not None:
                taken.add(name.lower())
            slots.append(name)
        free = (name for name in self.ranked(now) if name.lower() not in taken)
        slots = [s if s is not None else next(free, None) for s in slots]
        st["slots"] = slots
        return list(slots)

    def update(self, menu, now: float | None = None) -> None:
        """After a pick: lets a brush that made the top list twice in a row take a slot."""
        now = time.time() if now is None else now
        slots = self.slots(menu, now)
        st = self.menus[menu.id]
        pinned = _pinned(menu)
        top = [name for name in self.ranked(now) if name.lower() not in pinned][:len(slots)]
        top_keys = {name.lower() for name in top}
        held = {s.lower() for s in slots if s is not None}
        challengers = [name for name in top if name.lower() not in held]
        before = {name.lower() for name in st["pending"]}
        losers = sorted((i for i, s in enumerate(slots) if s is not None and s.lower() not in top_keys),
                        key=lambda i: self.score(slots[i].lower(), now))
        pending = []
        for name in challengers:
            if name.lower() in before and losers:
                slots[losers.pop(0)] = name
            else:
                pending.append(name)
        st["slots"], st["pending"] = slots, pending
