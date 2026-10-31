"""The Studio's web API, in mixins so studio.Api stays readable: pywebview exposes the public methods
a js_api object inherits, and the page calls them as `await window.pywebview.api.<name>(...)`.

LibraryApi: the brush, alpha, material and texture libraries and their thumbnails. TagApi: the user's tags
(tags.py, one shared TagStore); every changing method returns the store's result merged with a fresh snapshot,
so the page needs one call per change and never has to ask again. The recent picks and use counts (usage.py) are
read through LibraryApi.get_usage().
"""
import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import assets
import brushes
import config as C
import fsutil
import paths
import radiald
import tags
import usage

_USAGE = usage.Usage()                # usage.json is written by the app; load() is cached on its mtime
THUMB_WORKERS = 4                     # Pillow and zlib let go of the GIL while they decode: 4 images at a time
_pool = None                          # made on the first batch of more than one name, then kept for the session
_pool_lock = threading.Lock()
_lib_cache: dict = {}                 # kind -> (signature, items, categories): the payload of the last walk


def _usage_payload(kind: str) -> dict:
    """The recent picks and the use scores of one kind, as the page wants them."""
    _USAGE.load()
    try:
        mtime_ns = os.stat(_USAGE.path).st_mtime_ns
    except OSError:
        mtime_ns = 0
    return {"ok": True, "kind": kind, "recent": _USAGE.recent(kind), "scores": _USAGE.scores_for(kind),
            "mtime_ns": mtime_ns}


def _thumb_pool() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=THUMB_WORKERS, thread_name_prefix="thumb")
        return _pool


def library_signature(walk) -> str:
    """A short hash of what a walk found: every item's name and path, and each folder's report. Equal
    signatures mean the browser's list is already right."""
    h = hashlib.blake2b(digest_size=12)
    for it in walk.items:
        h.update(it["name"].encode("utf-8", "surrogatepass"))
        h.update(b"\0")
        h.update(str(it["path"]).encode("utf-8", "surrogatepass"))
        h.update(b"\n")
    for rep in walk.sources:
        h.update(repr((rep["label"], str(rep["path"]), rep["exists"], rep["count"], rep["error"])).encode("utf-8", "surrogatepass"))
    return h.hexdigest()


class LibraryApi:
    # --- asset libraries -------------------------------------------------------------------------
    def get_library(self, refresh=False, kind="brush", since=None):
        """All brushes, alphas, materials or textures ZBrush can load (kind), first location wins (same rule
        the app uses), with categories. Also every folder searched (found or not), so the page can say where
        it looked. A brush library is also returned as "brushes" (the old key).

        "signature" is a hash of what was found. Pass the one the page holds as since: when the folders still
        give the same list, the answer is {"unchanged": True, "signature", "kind", "sources", "zbrush_found",
        "error"} with no items or categories (and no "brushes"), so nothing big crosses the bridge."""
        out = {"kind": kind, "items": [], "categories": [], "sources": [], "zbrush_found": False, "error": None,
               "signature": ""}
        if kind not in assets.ALL_KINDS:
            out["error"] = "unknown kind"
            return out
        try:
            walk = assets.library(kind)                 # the list and the lookup find() uses come from one walk
            dirs = brushes.zbrush_dirs()
            labels = assets.source_labels(kind)
            sig = library_signature(walk)
            same = bool(since) and since == sig
            cached = _lib_cache.get(kind)
            if cached and cached[0] == sig:
                items, categories = cached[1], cached[2]
            elif same:
                items, categories = [], []
            else:
                items, cats = [], {}
                for it in walk.items:
                    src = labels.get(it["label"], it["label"])
                    cat = f"{src}/{it['rel']}" if it["rel"] else src
                    cats[cat] = cats.get(cat, 0) + 1
                    items.append({"name": it["name"], "source": src, "category": cat, "path": it["path"]})
                categories = [{"id": k, "count": v} for k, v in cats.items()]
                _lib_cache[kind] = (sig, items, categories)
            sources = []
            for rep in walk.sources:
                sources.append({"label": labels.get(rep["label"], rep["label"]), "path": rep["path"],
                                "exists": rep["exists"], "count": rep["count"], "error": rep["error"]})
            if refresh:
                brushes.cache_prune(8000)
            out.update(items=items, categories=categories, sources=sources, signature=sig,
                       zbrush_found=bool(dirs.get("install") or dirs.get("user_assets")),
                       error=brushes.walk_error(walk))   # the browser keeps the list it had when a rescan reports one
            if same:
                for k in ("items", "categories"):
                    del out[k]
                out["unchanged"] = True
                return out
        except Exception as e:
            out.update(items=[], categories=[], sources=[], zbrush_found=False,
                       error=str(e) or e.__class__.__name__)
        if kind == "brush":
            out["brushes"] = out["items"]
        return out

    def get_usage(self, kind="brush"):
        """What was picked lately (newest first) and how much each name is used, for the browser's Recent and
        Most used. scores are keyed by the lower-case name."""
        return _usage_payload(kind)

    def forget_recent(self, kind, name):
        """Takes a name off the Recent list. The same payload as get_usage(), with ok = whether it was there."""
        try:
            _USAGE.load()
            gone = _USAGE.forget(kind, name)
            if gone:
                _USAGE.save()
        except OSError:
            gone = False
        out = _usage_payload(kind)
        out["ok"] = gone
        return out

    def get_thumbs(self, names, size=128, kind="brush"):
        """{name: data URL or None} for a batch of names of one kind. The pictures come from a bounded
        in-memory cache, then the disk cache, and are decoded on a small pool of threads when they are in
        neither, so a batch costs about the slowest quarter of its images, not the sum. A name that cannot be
        decoded gives None and is tried again next time. A batch of a few names is as cheap as a few names."""
        try:
            size = max(32, min(256, int(size)))
        except (TypeError, ValueError):
            size = 128
        names = list(dict.fromkeys(n for n in (names or []) if isinstance(n, str)))
        if kind not in assets.ALL_KINDS or not names:
            return {n: None for n in names}
        if len(names) == 1:
            return {names[0]: assets.thumb_data_url(kind, names[0], size)}
        urls = _thumb_pool().map(lambda n: assets.thumb_data_url(kind, n, size), names)
        return dict(zip(names, urls))


def retarget_ring(renamed: dict) -> tuple:
    """Rewrites radial.json so the {"tag": key} and {"browser": key} slots named in renamed ({old key: new key})
    use the new key. For the browser window, which holds no menus: Studio does the same inside its editor, where
    Undo can take it back. Returns (items changed, problem or None). Nothing is written when the file is missing,
    cannot be read or is not a JSON object, or holds no matching item. The file as it was is kept as
    radial.json.bak (as Studio's Save does), and the new one is swapped in atomically. The app and Studio notice
    the change by the file's time."""
    path = paths.CONFIG_FILE
    try:
        with open(path, "rb") as f:
            old = f.read()
    except FileNotFoundError:
        return 0, None
    except OSError as e:
        return 0, f"radial.json could not be read: {e.strerror or e}"
    try:
        cfg = json.loads(old.decode("utf-8-sig"))
    except (ValueError, RecursionError):
        return 0, "radial.json is not valid JSON, so its ring items were not changed."
    if not isinstance(cfg, dict):
        return 0, "radial.json is not a JSON object, so its ring items were not changed."
    n = C.retag(cfg, renamed)
    if not n:
        return 0, None
    try:
        data = (json.dumps(cfg, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        fsutil.write_atomic(path + ".bak", old)
        fsutil.write_atomic(path, data)
    except (OSError, ValueError, RecursionError) as e:
        return 0, f"radial.json could not be written: {getattr(e, 'strerror', None) or e}"
    return n, None


_STORE = tags.TagStore(radiald.tags_path())


class TagApi:
    # --- tags ------------------------------------------------------------------------------------
    @staticmethod
    def _tag_snapshot() -> dict:
        st = _STORE
        with st._lock:                                      # one consistent view: counts, items and mtime together
            tag_list = [dict(t, builtin=True) if t["key"] == tags.FAVOURITE else t for t in st.tags()]
            return {"ok": True, "tags": tag_list, "items": st.items(), "palette": list(tags.PALETTE),
                    "mtime_ns": st.mtime, "path": st.path, "error": st.error or None}

    def get_tags(self, since_mtime_ns=None):
        """All tags with counts, and which tags every tagged item carries. Pass the last mtime_ns to get
        {"unchanged": true} when nothing changed (the page asks again whenever its window gets focus)."""
        _STORE.reload_if_changed()
        try:       # the page holds the time as a JS double, which rounds a 1.7e18 ns value: 1 microsecond slack
            same = since_mtime_ns is not None and abs(int(since_mtime_ns) - _STORE.mtime) <= 1000
        except (TypeError, ValueError, OverflowError):
            same = False
        if same and not _STORE.error:
            return {"unchanged": True, "mtime_ns": _STORE.mtime}
        return self._tag_snapshot()

    def get_tag_uses(self):
        """How many ring items point at each tag, read from radial.json: {"ok": True, "uses": {tag key: n}}. A Tag
        slot ({"tag": key}) and a Browser slot ({"browser": key}) each count once. The browser window holds no
        menus, so its tag manager asks for this to say what deleting a tag touches. A file that cannot be read
        gives {"ok": False, "uses": {}}."""
        uses = {}
        try:
            with open(paths.CONFIG_FILE, encoding="utf-8-sig") as f:
                menus = (json.load(f) or {}).get("menus") or {}
            for m in menus.values():
                for it in (m.get("items") or []) if isinstance(m, dict) else ():
                    for k in ("tag", "browser"):
                        if isinstance(it, dict) and isinstance(it.get(k), str) and it[k]:
                            uses[it[k]] = uses.get(it[k], 0) + 1
                            break
        except (OSError, ValueError, AttributeError, RecursionError):
            return {"ok": False, "uses": {}}
        return {"ok": True, "uses": uses}

    def _tag_result(self, res: dict) -> dict:
        out = self._tag_snapshot()
        out.update(res)
        out["error"] = res.get("error") or out["error"]
        return out

    def create_tag(self, label, color=None):
        return self._tag_result(_STORE.create_tag(label, color))

    def rename_tag(self, key, label):
        return self._tag_result(_STORE.rename_tag(key, label))

    def recolor_tag(self, key, color):
        return self._tag_result(_STORE.recolor_tag(key, color))

    def delete_tag(self, key):
        return self._tag_result(_STORE.delete_tag(key))

    def merge_tags(self, src, dst):
        return self._tag_result(_STORE.merge_tags(src, dst))

    def set_item_tags(self, item_key, tag_keys):
        return self._tag_result(_STORE.set_tags(item_key, tag_keys))

    def tag_items(self, item_keys, add=None, remove=None):
        return self._tag_result(_STORE.tag_items(item_keys, add or (), remove or ()))
