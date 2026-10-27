"""The Studio's web API, in mixins so studio.Api stays readable: pywebview exposes the public methods
a js_api object inherits, and the page calls them as `await window.pywebview.api.<name>(...)`.

LibraryApi: the brush library and its thumbnails. TagApi: the user's tags (tags.py, one shared TagStore);
every changing method returns the store's result merged with a fresh snapshot, so the page needs one
call per change and never has to ask again.
"""
import base64
import os

import brushes
import radiald
import tags


class LibraryApi:
    # --- brush library ---------------------------------------------------------------------------
    def get_library(self, refresh=False):
        """All brushes ZBrush can load, first location wins (same rule the app uses), with categories.
        Also every folder searched (found or not), so the page can say where it looked."""
        try:
            if refresh:
                brushes.brush_index(refresh=True)       # find_brush, thumbnails and ring previews see new brushes
            dirs = brushes.zbrush_dirs()
            seen, items, sources = set(), [], []
            labels = {"user ZStartup/BrushPresets": "My Brushes", "install ZStartup/BrushPresets": "My Brushes",
                      "install ZData/BrushPresets": "ZBrush", "install Lightbox/Brushes": "Lightbox",
                      "install ZBrushes": "Lightbox"}
            for label, folder, _rec in brushes.brush_sources():
                src = labels.get(label, label)
                exists, count = folder.is_dir(), 0
                if exists:
                    for root, subs, files in os.walk(folder):
                        subs[:] = sorted(d for d in subs if not d.startswith("_"))
                        rel = os.path.relpath(root, folder)
                        for fn in sorted(files, key=str.lower):
                            if not fn.lower().endswith(".zbp"):
                                continue
                            count += 1
                            name = os.path.splitext(fn)[0]
                            if name.lower() in seen:
                                continue
                            seen.add(name.lower())
                            cat = src if rel == "." else f"{src}/{rel.replace(os.sep, '/')}"
                            items.append({"name": name, "source": src, "category": cat,
                                          "path": os.path.join(root, fn)})
                sources.append({"label": src, "path": str(folder), "exists": exists, "count": count})
            cats = {}
            for it in items:
                cats[it["category"]] = cats.get(it["category"], 0) + 1
            if refresh:
                brushes.cache_prune()
            return {"brushes": items, "categories": [{"id": k, "count": v} for k, v in cats.items()],
                    "sources": sources, "zbrush_found": bool(dirs.get("install") or dirs.get("user_assets")),
                    "error": None}
        except Exception as e:
            return {"brushes": [], "categories": [], "sources": [], "zbrush_found": False,
                    "error": str(e) or e.__class__.__name__}

    def get_thumbs(self, names, size=128):
        """{name: data URL or None} for a batch of brush names (cached on disk after the first decode)."""
        try:
            size = max(32, min(256, int(size)))
        except (TypeError, ValueError):
            size = 128
        out = {}
        for n in names or []:
            data = brushes.thumbnail_png(n, size)
            out[n] = "data:image/png;base64," + base64.b64encode(data).decode("ascii") if data else None
        return out


_STORE = tags.TagStore(radiald.tags_path())


class TagApi:
    # --- tags ------------------------------------------------------------------------------------
    @staticmethod
    def _tag_snapshot() -> dict:
        st = _STORE
        with st._lock:                                      # one consistent view: counts, items and mtime together
            return {"ok": True, "tags": st.tags(), "items": st.items(), "palette": list(tags.PALETTE),
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
