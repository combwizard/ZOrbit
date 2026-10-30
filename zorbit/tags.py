"""The user's tags on brushes, alphas, materials and textures: a sidecar file, %APPDATA%\\ZOrbit\\tags.json.

{"version": 1,
 "tags":  {"blocking": {"label": "Blocking", "color": "#F86B33"}},
 "items": {"brush:claybuildup": ["blocking"], "brush:dam_standard": ["detailing", "blocking"]}}

A tag has a key, a label and a colour. The key is a slug of the label made once when the tag is created and
never changes on a rename, so the lists in "items" and radial.json's {"tag": key} slots survive renames. The
order of "tags" is the order they are listed in. An item is "<kind>:<id>" in lower case, a brush is
"brush:" + its name, likewise alpha:, material: and texture: (item_key() is the one place that builds it). An
item can carry several tags; the first one (other than Favourites) is its colour cue in the ring. Items that are
not installed right now keep their tags.

Favourites (key FAVOURITE) is built in: it always exists, always comes first, keeps its name, and cannot be
deleted or merged away. Its colour can be changed. A file without it gets it back on load, and the next write
puts it in the file. Starring an item never changes the item's colour cue, so color_of_item() skips it.

A missing file means the three starter tags, held in memory until the first change writes the file. A file
that cannot be read (a typo from a hand edit) keeps the previous state and sets .error; the changing methods
then refuse, so the file is never overwritten. Keys this module does not know are written back untouched.

The ring app only reads (reload_if_changed() on every config poll). The Studio and the popout change tags:
each change reloads the file, applies itself and writes it back atomically while holding the named mutex
Local\\ZOrbitTags, so two processes cannot lose each other's edits.
"""
import contextlib
import ctypes
import ctypes.wintypes as w
import json
import os
import re
import threading

import fsutil
import paths

PALETTE = ("#F86B33", "#4DC8E9", "#A8DF23", "#E8413C", "#C77DFF", "#FFD166", "#5EEAD4", "#F472B6")
FAVOURITE = "favourite"                # the built-in tag; the Studio and the browser star items with it
FAVOURITE_LABEL = "Favourites"
FAVOURITE_COLOR = "#FFD166"
STARTERS = ((FAVOURITE, FAVOURITE_LABEL, FAVOURITE_COLOR),
            ("blocking", "Blocking", "#F86B33"), ("detailing", "Detailing", "#4DC8E9"))
MUTEX_NAME = "Local\\ZOrbitTags"
MUTEX_WAIT_MS = 2000
LABEL_MAX = 40
_KEY_RE = re.compile(r"[a-z][a-z0-9_-]{0,31}")
_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}")
_ITEM_RE = re.compile(r"[a-z]+:.+")
_KNOWN = ("version", "tags", "items")

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_CreateMutexW = _kernel32.CreateMutexW
_CreateMutexW.restype, _CreateMutexW.argtypes = w.HANDLE, [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
_WaitForSingleObject = _kernel32.WaitForSingleObject
_WaitForSingleObject.restype, _WaitForSingleObject.argtypes = w.DWORD, [w.HANDLE, w.DWORD]
_ReleaseMutex = _kernel32.ReleaseMutex
_ReleaseMutex.argtypes = [w.HANDLE]
_CloseHandle = _kernel32.CloseHandle
_CloseHandle.argtypes = [w.HANDLE]


def _norm(s: str) -> str:
    """Lower case without any spaces: 'Dam Standard' and 'DamStandard' are the same brush, as in
    brushes.find_brush()."""
    return "".join(str(s).split()).lower()


def item_key(kind: str, name: str) -> str:
    """'brush', ' Dam Standard ' -> 'brush:damstandard'."""
    return f"{kind}:{_norm(name)}"


@contextlib.contextmanager
def _file_lock():
    """The cross-process mutex around a read-modify-write. After 2 s without it the change goes ahead anyway."""
    h = _CreateMutexW(None, False, MUTEX_NAME)
    got = bool(h) and _WaitForSingleObject(h, MUTEX_WAIT_MS) in (0, 0x80)    # signalled / abandoned
    try:
        yield
    finally:
        if got:
            _ReleaseMutex(h)
        if h:
            _CloseHandle(h)


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9_-]+", "-", label.lower()).strip("-_")
    if not s or not s[0].isalpha():
        s = "tag-" + s
    return s[:32].rstrip("-_") or "tag"


def _with_favourite(tags: dict) -> dict:
    """The tags with Favourites first: added with its default colour when missing, and its name put back when a
    hand edit changed it (the colour is the user's to change). Returns a new dict."""
    fav = dict(tags.get(FAVOURITE) or {"color": FAVOURITE_COLOR})
    fav["label"] = FAVOURITE_LABEL
    return {FAVOURITE: fav, **{k: t for k, t in tags.items() if k != FAVOURITE}}


def _parse(raw: dict):
    """(tags, items, extra) from a tags.json-shaped dict. Whatever is malformed is left out: a tag without a
    usable key or name, a colour that is not #RRGGBB (the first palette colour is used), tag keys in an item
    list that no tag has (Favourites counts as a tag that always exists, see _with_favourite). Shared by load() and the settings import, so both read a file the same way."""
    tags, items = {}, {}
    raw_tags, raw_items = raw.get("tags"), raw.get("items")
    for k, t in (raw_tags.items() if isinstance(raw_tags, dict) else ()):
        label = t.get("label") if isinstance(t, dict) else None
        label = label.strip()[:LABEL_MAX].strip() if isinstance(label, str) else ""
        if isinstance(k, str) and _KEY_RE.fullmatch(k) and label:
            color = t.get("color")
            ok = isinstance(color, str) and _COLOR_RE.fullmatch(color)
            tags[k] = {"label": label, "color": color.upper() if ok else PALETTE[0]}
    for ik, lst in (raw_items.items() if isinstance(raw_items, dict) else ()):
        if not isinstance(ik, str) or not isinstance(lst, list):
            continue
        keys = list(dict.fromkeys(k for k in lst if isinstance(k, str) and (k in tags or k == FAVOURITE)))
        if keys:                                       # unknown tag keys are dropped here
            items.setdefault(_norm(ik), keys)
    extra = {k: v for k, v in raw.items() if k not in _KNOWN}
    return tags, items, extra


class TagStore:
    def __init__(self, path=None):
        self.path = path or paths.TAGS_FILE
        self.error = ""                   # why the file could not be read (the previous state is kept)
        self.mtime = 0                    # st_mtime_ns of the file as loaded; 0 when it does not exist
        self._lock = threading.RLock()
        self._sig = "unread"              # (st_mtime_ns, st_size) of the file as loaded; None: missing
        self._tags = {}                   # key -> {"label", "color"}, in display order
        self._items = {}                  # item key -> [tag key], first = colour cue
        self._extra = {}                  # top-level keys we do not know, written back as they were

    # --- file ------------------------------------------------------------------------------------
    def _stat(self):
        try:
            st = os.stat(self.path)
        except OSError:
            return None
        return (st.st_mtime_ns, st.st_size)

    def load(self) -> "TagStore":
        """Reads the file. Missing: the starter tags, in memory only. Unreadable: the previous state stays."""
        with self._lock:
            sig = self._stat()
            self._sig = sig
            if sig is None:
                self.error, self.mtime, self._extra = "", 0, {}
                self._tags = {k: {"label": lb, "color": c} for k, lb, c in STARTERS}
                self._items = {}
                return self
            try:
                with open(self.path, encoding="utf-8-sig") as f:
                    raw = json.load(f)
                if not isinstance(raw, dict):
                    raise ValueError("the top level must be an object")
            except OSError as e:                      # locked or held by a scanner: try again next poll
                self.error = f"tags.json could not be read: {e}"
                self._sig = "unread"
                return self
            except ValueError as e:                   # a typo from a hand edit: wait for the file to change
                self.error = f"tags.json could not be read: {e}"
                self.mtime = sig[0]
                return self
            self._tags, self._items, self._extra = _parse(raw)
            self._tags = _with_favourite(self._tags)
            self.error, self.mtime = "", sig[0]
            return self

    def reload_if_changed(self) -> bool:
        """Loads the file if it changed (or appeared, or went away) since the last load. True if it did."""
        with self._lock:
            if self._stat() == self._sig:
                return False
            self.load()
            return True

    def _write(self) -> None:
        data = {"version": 1, "tags": self._tags, "items": self._items}
        data.update(self._extra)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fsutil.write_atomic(self.path, json.dumps(data, indent=1, ensure_ascii=False) + "\n")
        self._sig = self._stat()
        self.mtime = self._sig[0] if self._sig else 0

    def _change(self, apply) -> dict:
        """Reload, apply(), write. apply returns a result dict; the file is written only when it says ok."""
        with self._lock:
            try:
                with _file_lock():
                    self.load()
                    if self.error:
                        return {"ok": False, "error": self.error}
                    res = apply()
                    if res.get("ok"):
                        self._write()
                    return res
            except OSError as e:
                self._sig = "unread"                      # memory may be ahead of the file: read it again
                return {"ok": False, "error": f"tags.json could not be written: {e.strerror or e}"}

    # --- reading ---------------------------------------------------------------------------------
    def tags(self) -> list:
        """[{key, label, color, count}] in display order; count = items carrying the tag."""
        with self._lock:
            count = dict.fromkeys(self._tags, 0)
            for lst in self._items.values():
                for k in lst:
                    count[k] += 1
            return [{"key": k, "label": t["label"], "color": t["color"], "count": count[k]}
                    for k, t in self._tags.items()]

    def items(self) -> dict:
        """{item key: [tag key]} as a copy."""
        with self._lock:
            return {ik: list(lst) for ik, lst in self._items.items()}

    def snapshot(self) -> dict:
        """The tags and items as tags.json holds them, as copies: what an export writes."""
        with self._lock:
            return {"version": 1,
                    "tags": {k: dict(t) for k, t in self._tags.items()},
                    "items": {ik: list(lst) for ik, lst in self._items.items()}}

    @classmethod
    def from_raw(cls, raw: dict, path=None) -> "TagStore":
        """A store held in memory only, with the tags of a tags.json-shaped dict (nothing is read or written)."""
        st = cls(path)
        st._tags, st._items, st._extra = _parse(raw)
        st._tags = _with_favourite(st._tags)
        return st

    def has(self, key) -> bool:
        return key in self._tags

    exists = has

    def label(self, key) -> str:
        t = self._tags.get(key)
        return t["label"] if t else ""

    def color(self, key) -> str:
        t = self._tags.get(key)
        return t["color"] if t else ""

    def tags_of(self, ikey) -> list:
        return list(self._items.get(ikey, ()))

    def items_with(self, key, kind=None) -> list:
        """Item keys carrying the tag (optionally only one kind, e.g. 'brush'), in file order."""
        with self._lock:
            pre = kind + ":" if kind else ""
            return [ik for ik, lst in self._items.items() if key in lst and ik.startswith(pre)]

    def tagged(self, kind=None) -> list:
        """Item keys that carry at least one tag (optionally only one kind)."""
        with self._lock:
            pre = kind + ":" if kind else ""
            return [ik for ik in self._items if ik.startswith(pre)]

    def color_of_item(self, ikey) -> str:
        """The colour of the item's first tag other than Favourites, '' if it has none: a star is not a colour."""
        return next((self.color(k) for k in self._items.get(ikey, ()) if k != FAVOURITE), "")

    def next_color(self) -> str:
        """The first palette colour no tag uses; when all are taken, the palette cycles."""
        with self._lock:
            used = {t["color"] for t in self._tags.values()}
            return next((c for c in PALETTE if c not in used), PALETTE[len(self._tags) % len(PALETTE)])

    # --- changing --------------------------------------------------------------------------------
    def _check_label(self, label, ignore=None):
        """(clean label, None) or (None, error result). A clash is case-insensitive and names the other tag."""
        label = label.strip() if isinstance(label, str) else ""
        if not 1 <= len(label) <= LABEL_MAX:
            return None, {"ok": False, "error": f"A tag name is 1 to {LABEL_MAX} characters."}
        low = label.casefold()
        other = next((k for k, t in self._tags.items() if k != ignore and t["label"].casefold() == low), None)
        if other:
            return None, {"ok": False, "exists": other,
                          "error": f"A tag called '{self._tags[other]['label']}' already exists."}
        return label, None

    @staticmethod
    def _check_color(color):
        if isinstance(color, str) and _COLOR_RE.fullmatch(color):
            return color.upper(), None
        return None, {"ok": False, "error": "A tag colour is #RRGGBB."}

    @staticmethod
    def _built_in(what):
        return {"ok": False, "error": f"Favourites is built in and cannot be {what}."}

    @staticmethod
    def _unknown(key):
        return {"ok": False, "error": f"Tag '{key}' does not exist."}

    @staticmethod
    def _item(ikey):
        ikey = _norm(ikey) if isinstance(ikey, str) else ""
        return ikey if _ITEM_RE.fullmatch(ikey) else None

    def _drop_tag(self, key) -> None:
        del self._tags[key]
        for ik in list(self._items):
            self._items[ik] = [k for k in self._items[ik] if k != key]
            if not self._items[ik]:
                del self._items[ik]

    def create_tag(self, label, color=None) -> dict:
        def apply():
            lb, err = self._check_label(label)
            if err:
                return err
            c, err = self._check_color(color) if color is not None else (self.next_color(), None)
            if err:
                return err
            base = _slug(lb)
            key, n = base, 2
            while key in self._tags:
                suffix = f"-{n}"
                key, n = base[:32 - len(suffix)] + suffix, n + 1
            self._tags[key] = {"label": lb, "color": c}
            return {"ok": True, "key": key}
        return self._change(apply)

    def rename_tag(self, key, label) -> dict:
        def apply():
            if key == FAVOURITE:
                return self._built_in("renamed")
            if key not in self._tags:
                return self._unknown(key)
            lb, err = self._check_label(label, ignore=key)
            if err:
                return err
            self._tags[key]["label"] = lb
            return {"ok": True, "key": key}
        return self._change(apply)

    def recolor_tag(self, key, color) -> dict:
        def apply():
            if key not in self._tags:
                return self._unknown(key)
            c, err = self._check_color(color)
            if err:
                return err
            self._tags[key]["color"] = c
            return {"ok": True, "key": key}
        return self._change(apply)

    def delete_tag(self, key) -> dict:
        def apply():
            if key == FAVOURITE:
                return self._built_in("deleted")
            if key not in self._tags:
                return self._unknown(key)
            self._drop_tag(key)
            return {"ok": True, "key": key}
        return self._change(apply)

    def merge_tags(self, src, dst) -> dict:
        """Moves src's items to dst (in src's place in each list, so a colour cue stays) and deletes src."""
        def apply():
            if src == FAVOURITE:
                return self._built_in("merged into another tag")
            for k in (src, dst):
                if k not in self._tags:
                    return self._unknown(k)
            if src == dst:
                return {"ok": False, "error": "A tag cannot be merged into itself."}
            for lst in self._items.values():
                if src in lst:
                    if dst in lst:
                        lst.remove(src)
                    else:
                        lst[lst.index(src)] = dst
            self._drop_tag(src)
            return {"ok": True, "key": dst}
        return self._change(apply)

    def set_tags(self, ikey, keys) -> dict:
        """Gives an item exactly these tags (first = colour cue). An empty list untags it."""
        def apply():
            ik = self._item(ikey)
            if ik is None:
                return {"ok": False, "error": f"'{ikey}' is not an item key like 'brush:name' "
                                              f"(or alpha:, material:, texture:)."}
            keys_ = list(dict.fromkeys(keys or ()))
            for k in keys_:
                if k not in self._tags:
                    return self._unknown(k)
            if keys_:
                self._items[ik] = keys_
            else:
                self._items.pop(ik, None)
            return {"ok": True}
        return self._change(apply)

    def _merge_plan(self, in_tags):
        """(renamed, added) for merging these incoming tags into the current ones. A key that exists here is
        kept as it is. A new key whose name matches a tag here (case-insensitive, as _check_label compares)
        maps to that tag: renamed[incoming] = local. Any other new key is added."""
        names = {t["label"].casefold(): k for k, t in self._tags.items()}
        renamed, added = {}, []
        for k, t in in_tags.items():
            if k in self._tags:
                continue
            low = t["label"].casefold()
            if low in names:
                renamed[k] = names[low]
            else:
                names[low] = k                           # two incoming tags with one name become one tag
                added.append(k)
        return renamed, added

    def import_preview(self, raw) -> dict:
        """What importing this tags.json-shaped dict would do, without doing it:
        {"tags": n in the file, "new_tags": n a merge would add, "items": n tagged items in the file}."""
        in_tags, in_items, _ = _parse(raw)
        with self._lock:
            self.reload_if_changed()
            _, added = self._merge_plan(in_tags)
        return {"tags": len(in_tags), "new_tags": len(added), "items": len(in_items)}

    def import_tags(self, raw, mode="merge") -> dict:
        """Brings in the tags of a tags.json-shaped dict.
        'replace': the tags and items of the file take the place of the current ones (the current file is first
        copied to tags.json.bak, and keys this module does not know stay).
        'merge': tags that exist here keep their name and colour; a tag with the name of a local tag under
        another key joins that one; the rest are added. Each item keeps its tags here and gains the file's after
        them. Returns {"ok", "mode", "added", "renamed": {incoming key: local key}, "items"}; items = the number
        of items whose tags changed."""
        if mode not in ("merge", "replace"):
            return {"ok": False, "error": "Import tags as 'merge' or 'replace'."}
        in_tags, in_items, _ = _parse(raw if isinstance(raw, dict) else {})

        def apply():
            if not in_tags:
                return {"ok": False, "error": "There are no tags in that file."}
            if mode == "replace":
                try:
                    with open(self.path, "rb") as f:
                        old = f.read()
                except FileNotFoundError:
                    old = None
                if old is not None:
                    fsutil.write_atomic(self.path + ".bak", old)
                changed = sum(1 for ik, lst in in_items.items() if self._items.get(ik) != lst)
                self._tags = _with_favourite({k: dict(t) for k, t in in_tags.items()})
                self._items = {ik: list(lst) for ik, lst in in_items.items()}
                return {"ok": True, "mode": mode, "added": len(in_tags), "renamed": {}, "items": changed}
            renamed, added = self._merge_plan(in_tags)
            for k in added:
                self._tags[k] = dict(in_tags[k])
            changed = 0
            for ik, lst in in_items.items():
                mine = self._items.get(ik, [])
                new = mine + [k for k in dict.fromkeys(renamed.get(k, k) for k in lst) if k not in mine]
                if new != mine:
                    self._items[ik] = new
                    changed += 1
            return {"ok": True, "mode": mode, "added": len(added), "renamed": renamed, "items": changed}
        return self._change(apply)

    def tag_items(self, ikeys, add=(), remove=()) -> dict:
        """Adds tags to (at the end of each list) and removes tags from many items at once."""
        def apply():
            norm = [self._item(k) for k in ikeys or ()]
            if None in norm:
                return {"ok": False, "error": "Item keys look like 'brush:name' (or alpha:, material:, texture:)."}
            for k in add or ():
                if k not in self._tags:
                    return self._unknown(k)
            for ik in dict.fromkeys(norm):
                lst = [k for k in self._items.get(ik, []) if k not in (remove or ())]
                lst += [k for k in dict.fromkeys(add or ()) if k not in lst]
                if lst:
                    self._items[ik] = lst
                else:
                    self._items.pop(ik, None)
            return {"ok": True}
        return self._change(apply)
