"""What the app last did with a ring, for the Studio's Setup screen ("try the ring once").

%LOCALAPPDATA%\\ZOrbit\\activity.json (written by the app only, rewritten whole on every event):
{"v": 1, "pid": 4242, "started": 1761800000.1,          # the app that wrote it, and when it started
 "opens": 7, "picks": 3,                                 # counts since that start
 "ring": {"at": 1761800123.4, "menu": "brushes"},        # the last root ring opened (submenus do not count)
 "pick": {"at": 1761800125.0, "seq": 3, "menu": "brushes", "kind": "brush", "label": "ClayBuildup",
          "route": "listener", "sent": true, "reason": null,      # route: listener | key | zscript | none
          "source": "ring", "ack": null}}                         # source: ring | browser; ack: picked_up | timeout

The file is disposable: it is written without fsync (a flick can pick 100 ms after the ring opened, so nothing
here may wait), and a half-written or hand-edited file reads as None.
"""
import json
import os
import time

VERSION = 1


class Activity:
    def __init__(self, path: str, log=None):
        self.path = path
        self._log = log
        self._warned = False
        self.data = {"v": VERSION, "pid": os.getpid(), "started": time.time(), "opens": 0, "picks": 0,
                     "ring": None, "pick": None}
        # Nothing is written until the first event: the Studio builds a radiald.App for its ring previews too,
        # and a fresh record from there must not wipe what the real app has recorded.

    # --- events -----------------------------------------------------------------------------------
    def note_open(self, menu_id: str, nested: bool = False) -> None:
        """A ring was shown. Only a root ring (not a submenu opened from a slot) counts as 'the ring opened'."""
        if nested:
            return
        self.data["opens"] += 1
        self.data["ring"] = {"at": time.time(), "menu": menu_id}
        self._write()

    def note_pick(self, seq: int, item, route: str, sent: bool, source: str = "ring", menu=None,
                  reason=None) -> None:
        """A pick left the app (or could not). item has .kind and .label; route is how it went."""
        self.data["picks"] += 1
        self.data["pick"] = {"at": time.time(), "seq": int(seq), "menu": menu,
                             "kind": getattr(item, "kind", None), "label": getattr(item, "label", None),
                             "route": route, "sent": bool(sent), "reason": reason, "source": source, "ack": None}
        self._write()

    def note_ack(self, seq: int, result: str) -> None:
        """The message route's outcome for pick seq: 'picked_up' (request.json vanished) or 'timeout'."""
        p = self.data.get("pick")
        if p and p.get("seq") == seq:
            p["ack"] = result
            self._write()

    def note_route(self, seq: int, route: str, sent: bool = True, reason=None) -> None:
        """Pick seq went out again another way (the bridge-key fallback after a listener timeout)."""
        p = self.data.get("pick")
        if p and p.get("seq") == seq:
            p["route"] = route
            p["sent"] = bool(sent)
            p["reason"] = reason
            self._write()

    # --- file -------------------------------------------------------------------------------------
    def _write(self) -> None:
        tmp = self.path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
            os.replace(tmp, self.path)
        except OSError as e:
            if not self._warned and self._log:
                self._warned = True
                self._log(f"could not write {os.path.basename(self.path)}: {e!r}")


def read(path: str) -> dict | None:
    """The file's contents, or None when it is missing, unreadable, half-written or not in the shape above."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("v") != VERSION:
        return None
    for k, t in (("pid", int), ("started", (int, float)), ("opens", int), ("picks", int)):
        if not isinstance(d.get(k), t):
            return None
    for k in ("ring", "pick"):
        v = d.get(k)
        if v is not None and (not isinstance(v, dict) or not isinstance(v.get("at"), (int, float))):
            return None
    return d
