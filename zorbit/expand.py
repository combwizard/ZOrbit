"""Turns a menu from radial.json into the menu the ring draws: auto slots filled, tag colours stamped, tag
slots opened up. Used by the app and by the Studio's previews, so both show the same ring.

  * auto slots become the brushes usage.py picked for them (an empty slot stays a placeholder);
  * a brush slot gets the colour of the brush's first tag (also a steps slot that starts with a brush, since
    the ring shows that brush's icon), unless ring.tag_colors is "none";
  * a {"tag": key} slot whose tag exists and has installed brushes becomes an ordinary submenu slot, pointing
    at the synthetic menu "tag:<key>"; with no brushes (or no tag) it stays a "tag" slot and is drawn faint.

A tag menu lists the tag's installed brushes, most used first, as a fan. With more than TAG_SLOTS the last
slot is "More..." and opens the brush browser on that tag. Item count and order of a menu never change.
The tag menus are cached until a pick, a usage.json change or a tags.json change; the app builds a new
Expander whenever it reloads radial.json or tags.json.
"""
import dataclasses

import config as C
import usage as U
from tags import item_key

try:
    import brushes
except Exception:                  # thumbnails and the brush index are optional
    brushes = None

TAG_SLOTS = 12


class Expander:
    def __init__(self, cfg, usage, tags):
        self.cfg = cfg
        self.usage = usage
        self.tags = tags
        self._cache = {}               # tag key -> ((usage.version, tags.mtime), Menu or None)

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
        """The fan of a tag's installed brushes; None if the tag does not exist or has none installed."""
        if brushes is None or not self.tags.has(key):
            return None
        stamp = (self.usage.load().version, self.tags.mtime)
        hit = self._cache.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
        index = {k.replace(" ", ""): p for k, p in brushes.brush_index().items()}   # keys as item_key() makes them
        found = [index[ik.split(":", 1)[1]].stem for ik in self.tags.items_with(key, "brush")
                 if ik.split(":", 1)[1] in index]
        menu = None
        if found:
            names = self.usage.rank(found)
            color = self.tags.color(key)
            more = len(names) > TAG_SLOTS
            fill = "" if self.cfg.ring.get("tag_colors") == "none" else color   # the fan's tag, not each brush's own
            items = [C.Item(label=n, kind="brush", data={"brush": n}, color=fill)
                     for n in names[:TAG_SLOTS - 1 if more else TAG_SLOTS]]
            if more:
                items.append(C.Item(label="More…", kind="browser", data={"browser": key}, color=color))
            menu = C.Menu(id="tag:" + key, title=self.tags.label(key), items=items, fan=True)
        self._cache[key] = (stamp, menu)
        return menu

    # --- colours and tag slots -------------------------------------------------------------------
    def _brush_color(self, name):
        if self.cfg.ring.get("tag_colors") == "none":
            return ""
        return self.tags.color_of_item(item_key("brush", name))

    def _stamp(self, it):
        if it.kind == "tag":
            key = it.data["tag"]
            color = self.tags.color(key)
            if self.tag_menu(key) is not None:
                return C.Item(label=it.label, kind="menu", data={"menu": "tag:" + key}, icon=it.icon, tag=key,
                              color=color)
            return dataclasses.replace(it, color=color)       # missing or empty: stays, drawn faint
        first = it.data["steps"][0] if it.kind == "steps" else it.data
        if it.kind in ("brush", "steps") and "brush" in first:
            color = self._brush_color(first["brush"])
            if color:
                return dataclasses.replace(it, color=color)
        return it
