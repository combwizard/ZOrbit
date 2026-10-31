"""Turns a menu from radial.json into the menu the ring draws: auto slots filled, tag colours stamped, tag
slots opened up. Used by the app and by the Studio's previews, so both show the same ring.

  * auto slots become the brushes usage.py picked for them (an empty slot stays a placeholder);
  * a brush, alpha, material or texture slot gets the colour of the item's first tag (also a steps slot that
    starts with one, since the ring shows that item's icon), unless ring.tag_colors and ring.tag_band are both
    "none";
  * a {"tag": key} slot whose tag exists and has installed items becomes an ordinary submenu slot, pointing
    at the synthetic menu "tag:<key>"; with no items (or no tag) it stays a "tag" slot and is drawn faint.

A tag menu lists the tag's installed items as a fan: brushes first, most used first, then alphas, materials
and textures by name. With more than TAG_SLOTS the last slot is "More..." and opens the browser on that tag
(on the tab of the first item). Item count and order of a menu never change.
The tag menus are cached until a pick, a usage.json change, a tags.json change or a rebuilt asset index; the
app builds a new Expander whenever it reloads radial.json or tags.json.
"""
import dataclasses
import threading
import time

import config as C
import usage as U
from tags import item_key

try:
    import assets
except Exception:                  # thumbnails and the asset index are optional
    assets = None

TAG_SLOTS = 12
RESCAN_ASK_S = 5.0                 # a tag fan asks for a library rescan of a kind at most this often


class Expander:
    def __init__(self, cfg, usage, tags):
        self.cfg = cfg
        self.usage = usage
        self.tags = tags
        self._cache = {}               # tag key -> ((usage.version, tags.mtime, assets.generation), Menu or None)
        self._rescanning = set()       # kinds whose index a worker thread is building again
        self._asked = {}               # kind -> when a rescan was last asked for (time.monotonic)

    def menu(self, menu):
        """The menu as the ring draws it now. Nothing is saved."""
        filled = iter(self.usage.load().slots(menu)) if U.auto_count(menu) else None
        items = []
        for it in menu.items:
            if it.kind == "auto":
                name = next(filled)
                if name:
                    it = C.Item(label=name, kind="brush", data={"brush": name}, auto=True)
            items.append(self._stamp(it))
        return dataclasses.replace(menu, items=items)

    def resolve(self, mid):
        """The menu with this id for the ring to open as a submenu; None if there is none."""
        if mid.startswith("tag:"):
            return self.tag_menu(mid[4:])
        m = self.cfg.menus.get(mid)
        return self.menu(m) if m is not None else None

    def tag_menu(self, key):
        """The fan of a tag's installed items; None if the tag does not exist or has none installed."""
        if assets is None or not self.tags.has(key):
            return None
        for kind in C.ASSET_KINDS:
            assets.index(kind)                           # a first build moves generation: let it happen before the stamp
        stamp = (self.usage.load().version, self.tags.mtime, assets.generation)   # an index rebuilt: new files
        hit = self._cache.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
        found = []                                       # (kind, name): brushes by use, then the rest by name
        missing = False
        for kind in C.ASSET_KINDS:
            index = assets.index(kind)                   # keyed as item_key() makes them
            tagged = [ik.split(":", 1)[1] for ik in self.tags.items_with(key, kind)]
            if any(k not in index for k in tagged):
                missing = True
                self._rescan_later(kind)                 # saved since the scan? the next build sees the new generation
            stems = [index[k].stem for k in tagged if k in index]
            stems = self.usage.rank(stems) if kind == "brush" else sorted(stems, key=str.lower)
            found += [(kind, n) for n in stems]
        menu = None
        if found:
            color = self.tags.color(key)
            more = len(found) > TAG_SLOTS
            fill = color if self._colours_on() else ""   # the fan's tag, not each item's own
            items = [C.Item(label=n, kind=k, data={k: n}, color=fill)
                     for k, n in found[:TAG_SLOTS - 1 if more else TAG_SLOTS]]
            if more:
                items.append(C.Item(label="More…", kind="browser", data={"browser": key, "kind": found[0][0]},
                                    color=color))
            menu = C.Menu(id="tag:" + key, title=self.tags.label(key), items=items, fan=True)
        if missing:
            self._cache.pop(key, None)                   # built again next time: a rescan may find the missing items
        else:
            self._cache[key] = (stamp, menu)             # not newer than what was read: a rescan meanwhile rebuilds it
        return menu

    def _rescan_later(self, kind):
        """Builds the index of a kind again on a worker thread (assets.rescan allows it once in a few seconds), so a
        fan never waits for a folder walk. A changed index moves assets.generation, and the next build of the fan
        starts from it."""
        now = time.monotonic()
        if kind in self._rescanning or now - self._asked.get(kind, -1e9) < RESCAN_ASK_S:
            return                                       # a fan with an uninstalled item asks at most every few seconds
        self._asked[kind] = now
        self._rescanning.add(kind)

        def run():
            try:
                assets.rescan(kind)                      # too soon after the last build: the next fan build asks again
            except Exception:
                pass
            finally:
                self._rescanning.discard(kind)

        threading.Thread(target=run, daemon=True).start()

    # --- colours and tag slots -------------------------------------------------------------------
    def _colours_on(self):
        """Slots carry their tag colour unless every way of showing it is off."""
        r = self.cfg.ring
        return r.get("tag_colors", "tint") != "none" or r.get("tag_band", "medium") != "none"

    def _asset_color(self, kind, name):
        if not self._colours_on():
            return ""
        return self.tags.color_of_item(item_key(kind, name))

    def _stamp(self, it):
        if it.kind == "tag":
            key = it.data["tag"]
            color = self.tags.color(key)
            if self.tag_menu(key) is not None:
                return C.Item(label=it.label, kind="menu", data={"menu": "tag:" + key}, icon=it.icon, tag=key,
                              color=color)
            return dataclasses.replace(it, color=color)       # missing or empty: stays, drawn faint
        first = it.data["steps"][0] if it.kind == "steps" else it.data
        got = C.asset_of(first) if it.kind in C.ASSET_KINDS or it.kind == "steps" else None
        if got:
            color = self._asset_color(*got)
            if color:
                return dataclasses.replace(it, color=color)
        return it
