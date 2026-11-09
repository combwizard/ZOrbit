"""Turns a menu from radial.json into the menu the ring draws: auto slots filled, tag colours stamped, tag
slots opened up. Used by the app and by the Studio's previews, so both show the same ring.

  * auto slots become the brushes usage.py picked for them (an empty slot stays a placeholder);
  * {"empty": true} slots stay where they are and count toward a page, but the More menu leaves them out;
  * a brush, alpha, material or texture slot gets the colour of the item's first tag (also a steps slot that
    starts with one, since the ring shows that item's icon). The colour is always stamped; whether it shows is the
    ring's call, made per look (tag_colors and tag_band);
  * a {"tag": key} slot whose tag exists and has installed items becomes an ordinary submenu slot, pointing
    at the synthetic menu "tag:<key>"; with no items (or no tag) it stays a "tag" slot and is drawn faint;
  * a {"recent": kind} slot whose list has files becomes a submenu slot pointing at "recent:<kind>", a fan of Project
    and Tool items made from ZBrush's recent files (recent.py); with none it stays a "recent" slot and is drawn faint.

  * a menu whose look has when_full "more" and more items than fit its ring at the radius shows the first
    capacity - 1 of them and a "More" slot that opens the synthetic menu "more:<id>" with the rest (paged again
    in the same way when that is too long: "more:more:<id>"). Fan menus and tag menus are never paged.

A tag menu lists the tag's installed items as a fan: brushes first, most used first, then alphas, materials
and textures by name. On Favourites, a kind with its own order (tags.favourite_order) follows it instead; brushes
still come first. With more than ring.tag_limit (12 unless set) the last slot is "More..." and opens the
browser on that tag (on the tab of the first item). Item count and order of a menu never change.
The tag menus are cached until a pick, a usage.json change, a tags.json change or a rebuilt asset index; the
app builds a new Expander whenever it reloads radial.json or tags.json.

A recent fan holds the newest ring.tag_limit files of ZBrush's list that are on disk, with no More slot. Its items
are made fresh from the list, so a pick goes through the Project or Tool action and counts nowhere. The list comes from
recent.py's last answer, never from the disk, so the ring opens at once; a worker thread keeps the answers fresh, and
prefetch_recent() asks for them when the menus load.
"""
import dataclasses
import math
import threading
import time

import config as C
import layout
import recent
import usage as U
from tags import FAVOURITE, item_key

try:
    import assets
except Exception:                  # thumbnails and the asset index are optional
    assets = None

TAG_SLOTS = 12                     # slots in a tag fan unless ring.tag_limit says otherwise
RESCAN_ASK_S = 5.0                 # a tag fan asks for a library rescan of a kind at most this often
MORE_PREFIX = "more:"              # the id prefix of the menu a More slot opens
RECENT_PREFIX = "recent:"          # the id prefix of the fan a recent slot opens
MORE_CAP = 256                     # more slots than any ring holds: the most fit_count is asked to count


def _capacity(radius, slot) -> int:
    """How many slots of this size sit round a ring of this radius with the gap the ring keeps between neighbours
    (layout.fit_count, the ring's own rule). At least 1. Per-slot style sizes are not counted here."""
    return max(1, layout.fit_count([slot] * MORE_CAP, radius))


def needed_radius(count, slot) -> int:
    """The smallest radius (whole pixels) at which count slots of this size sit round a ring with the usual gap."""
    if count < 2:
        return 0
    return int(math.ceil(layout.needed_radius([slot] * count) - 1e-6))


class Expander:
    def __init__(self, cfg, usage, tags, front=None, log=None, wait_recent=False):
        """front: a callable giving the ZBrush installation in front (installs.entry), or None, for the recent files
        of that ZBrush; without it they are the library's ZBrush's. log: told once of a recent list that cannot be
        read. wait_recent: wait (briefly) for a fresh recent answer instead of showing the last one (Studio's
        previews, which are not on the ring's open path)."""
        self.cfg = cfg
        self.usage = usage
        self.tags = tags
        self.front = front
        self.log = log
        self.wait_recent = wait_recent
        self._recent_said = False      # a recent fan that could not be built was logged
        self._recent_waited = False    # wait_recent has waited once: a stuck worker blocks a preview only once
        self._cache = {}               # tag key -> ((usage.version, tags.mtime, assets.generation, limit, orders), Menu or None)
        self._rescanning = set()       # kinds whose index a worker thread is building again
        self._asked = {}               # kind -> when a rescan was last asked for (time.monotonic)

    def menu(self, menu):
        """The menu as the ring draws it now. Nothing is saved. A paged menu (when_full "more") comes back with its
        More slot; a "more:" menu comes back as it is, already filled and cut."""
        if menu.id.startswith(MORE_PREFIX):
            return menu
        return self._page(self._fill(menu))

    def _fill(self, menu):
        """The menu with its auto slots filled and its tag colours stamped, not yet cut to a page."""
        filled = iter(self.usage.load().slots(menu)) if U.auto_count(menu) else None
        items = []
        for it in menu.items:
            if it.kind == "auto":
                name = next(filled)
                if name:
                    it = dataclasses.replace(it, label=name, kind="brush", data={"brush": name}, auto=True)
            items.append(self._stamp(it))
        return dataclasses.replace(menu, items=items)

    def _page_size(self, menu) -> int:
        """How many slots one page of the menu holds, the More slot included; 0 when the menu is not paged."""
        look = menu.look or self.cfg.ring
        if look.get("when_full", "grow") != "more" or menu.fan:
            return 0
        k = _capacity(look.get("radius", 145), look.get("slot", 72))
        return k if k >= 3 else 0

    def _page(self, whole):
        """A filled menu cut to its first page: K - 1 items and a More slot that opens more:<id>."""
        k = self._page_size(whole)
        if not k or len(whole.items) <= k:
            return whole
        if all(it.kind == "empty" for it in whole.items[k - 1:]):
            return dataclasses.replace(whole, items=whole.items[:k])     # nothing to put behind a More slot
        more = C.Item(label="More", kind="menu", data={"menu": MORE_PREFIX + whole.id})
        return dataclasses.replace(whole, items=whole.items[:k - 1] + [more])

    def _whole(self, mid):
        """The menu with this id and all its items, filled and stamped, before any cut; None if there is none. For
        "more:<id>" that is what the page before it left out."""
        if mid.startswith(MORE_PREFIX):
            parent = self._whole(mid[len(MORE_PREFIX):])
            k = self._page_size(parent) if parent is not None else 0
            if not k or len(parent.items) <= k:
                return None                              # the parent has no More slot
            rest = [it for it in parent.items[k - 1:] if it.kind != "empty"]    # a list has no positions to keep
            if not rest:
                return None
            return dataclasses.replace(parent, id=mid, hotkey=None, items=rest)
        m = self.cfg.menus.get(mid)
        return self._fill(m) if m is not None else None

    def resolve(self, mid):
        """The menu with this id for the ring to open as a submenu; None if there is none."""
        if mid.startswith("tag:"):
            return self.tag_menu(mid[4:])
        if mid.startswith(RECENT_PREFIX):
            return self.recent_menu(mid[len(RECENT_PREFIX):])
        if mid.startswith(MORE_PREFIX):
            whole = self._whole(mid)
            return self._page(whole) if whole is not None else None
        m = self.cfg.menus.get(mid)
        return self.menu(m) if m is not None else None

    def _tag_limit(self):
        """How many slots a tag fan holds: ring.tag_limit, TAG_SLOTS when the ring does not say."""
        got = self.cfg.ring.get("tag_limit", TAG_SLOTS)
        return got if isinstance(got, int) and not isinstance(got, bool) and got >= 2 else TAG_SLOTS

    def tag_menu(self, key):
        """The fan of a tag's installed items; None if the tag does not exist or has none installed."""
        if assets is None or not self.tags.has(key):
            return None
        for kind in C.ASSET_KINDS:
            assets.index(kind)                           # a first build moves generation: let it happen before the stamp
        limit = self._tag_limit()
        orders = {k: self.tags.favourite_order(k) for k in C.ASSET_KINDS} if key == FAVOURITE else {}   # your own orders
        stamp = (self.usage.load().version, self.tags.mtime, assets.generation, limit, orders)   # an index rebuilt: new files
        hit = self._cache.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
        found = []                                       # (kind, name): brushes by use, then the rest by name, or your order
        missing = False
        for kind in C.ASSET_KINDS:
            index = assets.index(kind)                   # keyed as item_key() makes them
            tagged = [ik.split(":", 1)[1] for ik in self.tags.items_with(key, kind)]
            if any(k not in index for k in tagged):
                missing = True
                self._rescan_later(kind)                 # saved since the scan? the next build sees the new generation
            listed = assets.names(kind)                  # the listed names: "10 (PackA)", not the stem 10
            if orders.get(kind):                         # it holds exactly the kind's starred items (tags._synced)
                stems = [listed.get(k) or index[k].stem for k in orders[kind] if k in index]
            else:
                stems = [listed.get(k) or index[k].stem for k in tagged if k in index]
                stems = self.usage.rank(stems) if kind == "brush" else sorted(stems, key=str.lower)
            found += [(kind, n) for n in stems]
        menu = None
        if found:
            color = self.tags.color(key)
            more = len(found) > limit
            fill = color                                 # the fan's tag, not each item's own
            items = [C.Item(label=n, kind=k, data={k: n}, color=fill)
                     for k, n in found[:limit - 1 if more else limit]]
            if more:
                items.append(C.Item(label="More…", kind="browser", data={"browser": key, "kind": found[0][0]},
                                    color=color))
            menu = C.Menu(id="tag:" + key, title=self.tags.label(key), items=items, fan=True)
        if missing:
            self._cache.pop(key, None)                   # built again next time: a rescan may find the missing items
        else:
            self._cache[key] = (stamp, menu)             # not newer than what was read: a rescan meanwhile rebuilds it
        return menu

    def recent_menu(self, kind):
        """The fan of a {"recent": kind} slot: a Project or Tool item for each of the newest files of ZBrush's recent
        list, at most a tag fan's slots and no More slot; None when the list has none."""
        if kind not in C.RECENT_KINDS:
            return None
        try:
            install = self.front() if self.front is not None else None
            limit = self._tag_limit()
            paths = recent.entries(kind, limit, install, self.log)
            if self.wait_recent and not self._recent_waited and not recent.known(kind, limit, install):
                self._recent_waited = True               # only the very first read is waited for, 2 s at most
                if recent.wait(2.0):
                    paths = recent.entries(kind, limit, install, self.log)
            if not paths:
                return None
            items = [C.Item(label=recent.label(p), kind=recent.item_kind(p), data={recent.item_kind(p): p})
                     for p in paths]
            return C.Menu(id=RECENT_PREFIX + kind, title=C.RECENT_LABELS[kind], items=items, fan=True)
        except Exception as e:                           # never stops a ring from opening: the slot stays empty
            if self.log is not None and not self._recent_said:
                self._recent_said = True
                self.log(f"recent fan {kind!r} could not be built: {e!r}; the slot stays empty")
            return None

    def prefetch_recent(self):
        """Asks recent.py for the answers the menus' recent slots need, so the first ring finds them. Returns at
        once: the work is done on recent.py's worker thread."""
        kinds = {it.data.get("recent") for m in self.cfg.menus.values() for it in m.items if it.kind == "recent"}
        if not kinds:
            return
        try:
            install = self.front() if self.front is not None else None
        except Exception:
            install = None
        recent.prefetch(sorted(k for k in kinds if isinstance(k, str)), self._tag_limit(), install, self.log)

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
    def _asset_color(self, kind, name):
        return self.tags.color_of_item(item_key(kind, name))

    def _stamp(self, it):
        if it.kind == "tag":
            key = it.data["tag"]
            color = self.tags.color(key)
            if self.tag_menu(key) is not None:
                return dataclasses.replace(it, kind="menu", data={"menu": "tag:" + key}, tag=key, color=color)
            return dataclasses.replace(it, color=color)       # missing or empty: stays, drawn faint
        if it.kind == "recent":
            if self.recent_menu(it.data["recent"]) is not None:
                return dataclasses.replace(it, kind="menu", data={"menu": RECENT_PREFIX + it.data["recent"]})
            return it                                         # nothing in the list: stays, drawn faint
        first = it.data["steps"][0] if it.kind == "steps" else it.data
        got = C.asset_of(first) if it.kind in C.ASSET_KINDS or it.kind == "steps" else None
        if got:
            color = self._asset_color(*got)
            if color:
                return dataclasses.replace(it, color=color)
        return it
