"""Sharing one menu: the pure parts of Export menu... and Import menu... (no dialogs, no window).

A menu file holds one menu, the submenus it opens, and the tags its Tag and Browser items name, so it works on its
own on another PC. studio.py does the dialogs and the writing; this module builds the file's contents, plans the
ids and titles the menus get when they come in, and looks for brushes the PC does not have.
"""
import copy
import re
import time
import unicodedata

import config as C
import tags as T

MENU_FORMAT = 1              # the "zorbit_menu" number of a menu file
_VALID_ID = re.compile(r"[A-Za-z0-9_-]+")
_PC_KEYS = ("hotkey", "swallow")      # belong to one PC's keyboard: never in a menu file, never imported


def menu_slug(s) -> str:
    """A menu id made from a title ('Hard surface' -> 'hard_surface'); the same rule as menuSlug in app.js."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    out = re.sub(r"[^a-z0-9_-]+", "_", s).strip("_") or "menu"
    return f"m_{out}" if out.isdigit() else out


def _menus(cfg) -> dict:
    menus = cfg.get("menus") if isinstance(cfg, dict) else None
    return menus if isinstance(menus, dict) else {}


def _items(menu) -> list:
    items = menu.get("items") if isinstance(menu, dict) else None
    return [it for it in items if isinstance(it, dict)] if isinstance(items, list) else []


def collect(cfg, menu_id) -> list:
    """The menu and every submenu it opens (items of type menu, followed down, each once), in file order: the root
    first, then submenus as the walk first meets them (depth first, item order). Ids that start with 'tag:' and ids
    that are not in the config are skipped."""
    menus = _menus(cfg)
    seen, order = set(), []

    def walk(mid):
        if mid in seen or not isinstance(mid, str) or mid.startswith("tag:") or mid not in menus:
            return
        seen.add(mid)
        order.append(mid)
        for it in _items(menus[mid]):
            walk(it.get("menu"))

    walk(menu_id)
    return order


def _clean(menu) -> dict:
    out = copy.deepcopy(menu) if isinstance(menu, dict) else {}
    for k in _PC_KEYS:
        out.pop(k, None)
    return out


def _tag_keys(menus) -> list:
    """The keys the Tag and Browser items of these menus name, in order of first use."""
    keys = []
    for m in menus.values():
        for it in _items(m):
            for k in ("tag", "browser"):
                v = it.get(k)
                if isinstance(v, str) and v and v not in keys:
                    keys.append(v)
    return keys


def _tags_for(menus, store):
    """A tags.json-shaped dict with the tags the menus name (and the items that carry them), or None."""
    if store is None or getattr(store, "error", None):
        return None
    keys = [k for k in _tag_keys(menus) if k != T.FAVOURITE and store.has(k)]
    if not keys:
        return None
    want = set(keys)
    items = {}
    for ik, lst in store.items().items():
        kept = [k for k in lst if k in want]
        if kept:
            items[ik] = kept
    return {"version": 1, "tags": {k: {"label": store.label(k), "color": store.color(k)} for k in keys},
            "items": items}


def build(cfg, menu_id, store, version) -> dict:
    """The contents of a menu file. store: a loaded tags.TagStore, or None (then there is no 'tags' section)."""
    menus = _menus(cfg)
    ids = collect(cfg, menu_id)
    out_menus = {mid: _clean(menus[mid]) for mid in ids}
    bundle = {"zorbit_menu": MENU_FORMAT, "version": version, "exported": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "menu": menu_id, "menus": out_menus}
    tag_part = _tags_for(out_menus, store)
    if tag_part:
        bundle["tags"] = tag_part
    return bundle


def _title_key(t) -> str:
    return str(t or "").strip().casefold()


def plan_import(bundle_menus, root, cfg):
    """Gives each incoming menu an id and title that are free in cfg['menus'] and among the menus already placed.
    A taken id gets _2, _3...; an id that is not valid is made from the title; a taken title gets 2, 3....
    Returns (menus_out, root_out, renames): the menus under their new ids (same order), the root's new id, and a
    list of {"old_id", "id", "old_title", "title"} for the menus whose id or title changed. {"menu": old} items are
    pointed at the new ids, and a label that was the old title becomes the new one; hotkey and swallow are removed."""
    taken = set(_menus(cfg)) | C.RESERVED_MENU_IDS
    titles = {_title_key(m.get("title")) for m in _menus(cfg).values() if isinstance(m, dict)}
    new_id, new_title, renames = {}, {}, []
    for old, m in bundle_menus.items():
        m = m if isinstance(m, dict) else {}
        title = m.get("title") if isinstance(m.get("title"), str) else ""
        nid = old
        valid = (bool(_VALID_ID.fullmatch(old)) and not old.isdigit() and not old.startswith("tag:")
                 and old not in C.RESERVED_MENU_IDS)
        if not valid or old in taken:
            base = old if valid else menu_slug(title or old)      # a taken id is numbered, a bad one made anew
            nid, n = base, 2
            while nid in taken:
                nid, n = f"{base}_{n}", n + 1
        taken.add(nid)
        ntitle, n = title, 2
        if title.strip():
            while _title_key(ntitle) in titles:
                ntitle, n = f"{title} {n}", n + 1
            titles.add(_title_key(ntitle))
        new_id[old], new_title[old] = nid, ntitle
        if nid != old or ntitle != title:
            renames.append({"old_id": old, "id": nid, "old_title": title, "title": ntitle})
    out = {}
    for old, m in bundle_menus.items():
        m = _clean(m)
        if "title" in m or new_title[old]:
            m["title"] = new_title[old]
        if isinstance(m.get("items"), list):
            for it in m["items"]:
                if isinstance(it, dict) and isinstance(it.get("menu"), str) and it["menu"] in new_id:
                    target = it["menu"]
                    it["menu"] = new_id[target]
                    old_title = (bundle_menus[target] or {}).get("title") if isinstance(bundle_menus[target], dict) else None
                    if old_title and it.get("label") == old_title:      # a label that showed the title follows it
                        it["label"] = new_title[target]
        out[new_id[old]] = m
    return out, new_id.get(root, root), renames


def _asset_names(menus):
    """(kind, name) of every brush, alpha, material and texture the items name, steps included."""
    for m in menus.values():
        for it in _items(m):
            got = C.asset_of(it)
            if got:
                yield got
            for s in it.get("steps") if isinstance(it.get("steps"), list) else ():
                got = C.asset_of(s) if isinstance(s, dict) else None
                if got:
                    yield got


def missing_assets(menus) -> dict:
    """{"brush": [names], ...} of the assets the items name that assets.find cannot find on this PC (sorted,
    unique, only kinds that have any). A scan that fails counts as found: it never blocks an import."""
    import assets
    names = {}
    for kind, name in _asset_names(menus):
        names.setdefault(kind, set()).add(name)
    out = {}
    for kind in C.ASSET_KINDS:
        gone = set()
        for name in names.get(kind, ()):
            try:
                if assets.find(kind, name) is None:
                    gone.add(name)
            except Exception:
                pass
        if gone:
            out[kind] = sorted(gone)
    return out
