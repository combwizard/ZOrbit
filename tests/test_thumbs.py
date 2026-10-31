"""Thumbnails for big libraries: LibraryApi.get_thumbs decodes on a small pool, reduces big images as it opens
them, keeps a bounded in-memory cache, never stores a failure, and get_library gives a signature the page can
send back to skip a refresh. The images are made here with Pillow; no binary file is checked in."""
import base64
import io
import os
import threading
from pathlib import Path

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

import assets  # noqa: E402
import brushes  # noqa: E402

webapi = pytest.importorskip("webapi")


@pytest.fixture(autouse=True)
def fresh_cache():
    assets.THUMBS.clear()
    yield
    assets.THUMBS.clear()


def noise(w, h, colour=None):
    """A w x h image that is cheap to build and has detail for a decoder to chew on."""
    base = Image.effect_noise((256, 256), 60).convert("RGB")
    if colour:
        base = Image.blend(base, Image.new("RGB", base.size, colour), 0.8)
    return base.resize((w, h))


def decode(url):
    assert url.startswith("data:image/png;base64,")
    return Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))


@pytest.fixture
def big(tmp_path):
    jpg, png = tmp_path / "big_wood.jpg", tmp_path / "big_stone.png"
    noise(4096, 3072).save(jpg, quality=85)
    noise(4096, 2048).save(png, compress_level=1)
    return jpg, png


def test_big_jpeg_and_png_come_back_as_thumbnails(big):
    api = webapi.LibraryApi()
    out = api.get_thumbs([str(p) for p in big], 128, "texture")
    assert list(out) == [str(p) for p in big]
    for url in out.values():
        im = decode(url)
        assert im.size == (128, 128)                       # fitted, centred on a transparent square
        assert im.mode == "RGBA"
    assert decode(out[str(big[1])]).getpixel((64, 2))[3] == 0      # the 2:1 png leaves bands above and below


def test_a_big_jpeg_is_decoded_at_reduced_scale(big, monkeypatch):
    seen = {}
    real = Image.Image.draft

    def spy(self, mode, size):
        real(self, mode, size)
        seen["size"] = self.size                           # what the decoder will produce

    monkeypatch.setattr(Image.Image, "draft", spy)
    im = assets._pillow(big[0], 128)
    assert max(im.size) == 128
    assert max(seen["size"]) <= 1024                       # decoded at an eighth or so of 4096, not at full size


def test_a_batch_of_names_is_decoded_on_several_threads(big, tmp_path, monkeypatch):
    names = []
    for i in range(8):
        p = tmp_path / f"t{i}.png"
        noise(300 + i, 300).save(p)
        names.append(str(p))
    threads = set()
    real = assets.thumbnail_png

    def spy(kind, name, size=96):
        threads.add(threading.get_ident())
        return real(kind, name, size)

    monkeypatch.setattr(assets, "thumbnail_png", spy)
    out = webapi.LibraryApi().get_thumbs(names + names[:3] + [None, 5], 96, "texture")
    assert list(out) == names                              # in order, repeats and non-names dropped
    assert all(out.values())
    assert 1 < len(threads) <= webapi.THUMB_WORKERS


def test_a_small_batch_and_unknown_kind(big):
    api = webapi.LibraryApi()
    assert api.get_thumbs([], 128, "texture") == {}
    assert api.get_thumbs(None, 128, "texture") == {}
    one = api.get_thumbs([str(big[0])], 9999, "texture")             # size is clamped to 256
    assert decode(one[str(big[0])]).size == (256, 256)
    assert api.get_thumbs([str(big[0]), "x"], 128, "nonsense") == {str(big[0]): None, "x": None}


def test_a_broken_image_gives_none_and_is_not_remembered(tmp_path):
    p = tmp_path / "broken.png"
    p.write_bytes(b"this is not a picture")
    api = webapi.LibraryApi()
    assert api.get_thumbs([str(p)], 128, "texture") == {str(p): None}
    assert api.get_thumbs([str(p), str(p) + "2"], 128, "texture")[str(p)] is None
    assert len(assets.THUMBS) == 0                         # nothing stored for it, in memory
    assert not list(brushes._cache_dir().glob("texture_broken_*"))     # nor on disk
    noise(600, 400).save(p)                                # the same path, now a real picture (a copy that finished)
    url = api.get_thumbs([str(p)], 128, "texture")[str(p)]
    assert url and decode(url).size == (128, 128)


def test_a_replaced_file_is_read_again(tmp_path):
    p = tmp_path / "swap.png"
    noise(500, 500, (255, 0, 0)).save(p)
    api = webapi.LibraryApi()
    red = decode(api.get_thumbs([str(p)], 64, "texture")[str(p)]).getpixel((32, 32))
    old = p.stat().st_mtime_ns
    noise(500, 500, (0, 0, 255)).save(p)
    os.utime(p, ns=(old + 5_000_000_000, old + 5_000_000_000))
    blue = decode(api.get_thumbs([str(p)], 64, "texture")[str(p)]).getpixel((32, 32))
    assert red[0] > red[2] and blue[2] > blue[0]


def test_a_cut_short_cache_file_is_not_served(tmp_path):
    p = tmp_path / "cut.png"
    noise(400, 400).save(p)
    good = assets.thumbnail_png("texture", p, 64)
    assert good and assets._png_ok(good)
    cfile = assets._cache_file("texture", p, 64)
    cfile.write_bytes(good[:len(good) // 2])               # a half-written file left behind
    again = assets.thumbnail_png("texture", p, 64)
    assert assets._png_ok(again) and again == cfile.read_bytes()


def test_the_memory_cache_evicts_the_least_recently_used():
    c = assets.ThumbCache(max_entries=3, max_bytes=10_000)
    for k in "abc":
        c.put(k, k * 10)
    assert c.get("a")                                      # a is now the newest
    c.put("d", "d" * 10)
    assert c.get("b") is None and c.get("a") and c.get("c") and c.get("d")
    assert len(c) == 3


def test_the_memory_cache_holds_to_a_byte_budget():
    c = assets.ThumbCache(max_entries=100, max_bytes=100)
    for i in range(10):
        c.put(i, "x" * 30)
    assert len(c) == 3 and c.get(9) and c.get(0) is None
    c.put("big", "y" * 500)                                # bigger than the whole budget: it does not stay
    assert len(c) == 0
    c.put(1, "x" * 30)
    c.put(1, "x" * 40)                                     # replacing an entry counts its new size only
    assert len(c) == 1 and c._bytes == 40


def test_the_browser_cache_is_bounded(tmp_path, monkeypatch):
    small = assets.ThumbCache(max_entries=4)
    monkeypatch.setattr(assets, "THUMBS", small)
    for i in range(10):
        p = tmp_path / f"n{i}.png"
        noise(200, 200, (i * 20, 0, 0)).save(p)
        assert assets.thumb_data_url("texture", p, 64)
    assert len(small) == 4


def test_a_cached_picture_is_not_decoded_twice(big, monkeypatch):
    api = webapi.LibraryApi()
    api.get_thumbs([str(big[1])], 128, "texture")
    monkeypatch.setattr(assets, "thumbnail_png", lambda *a, **k: pytest.fail("decoded again"))
    assert api.get_thumbs([str(big[1])], 128, "texture")[str(big[1])]


# --- get_library's signature -----------------------------------------------------------------------

@pytest.fixture
def folder(tmp_path, monkeypatch):
    d = tmp_path / "Alphas"
    d.mkdir()
    for n in ("one", "two", "three"):
        (d / f"{n}.zbp").write_bytes(b"x")
    monkeypatch.setattr(assets, "sources", lambda kind: [("folder", d, True)])
    monkeypatch.setattr(assets, "exts", lambda kind: (".zbp",))
    monkeypatch.setattr(assets, "_index", {})
    monkeypatch.setattr(webapi, "_lib_cache", {})
    return d


def test_the_library_signature_skips_an_unchanged_refresh(folder):
    api = webapi.LibraryApi()
    first = api.get_library(False, "alpha")
    assert len(first["items"]) == 3 and first["signature"] and "unchanged" not in first
    same = api.get_library(True, "alpha", first["signature"])
    assert same["unchanged"] is True and same["signature"] == first["signature"]
    assert "items" not in same and "categories" not in same and same["sources"]
    again = api.get_library(False, "alpha")                # without since: the full list, from the stored payload
    assert again["items"] == first["items"] and again["signature"] == first["signature"]


def test_the_library_signature_moves_when_a_file_does(folder):
    api = webapi.LibraryApi()
    sig = api.get_library(False, "alpha")["signature"]
    (folder / "four.zbp").write_bytes(b"x")
    r = api.get_library(True, "alpha", sig)
    assert "unchanged" not in r and len(r["items"]) == 4 and r["signature"] != sig
    (folder / "four.zbp").unlink()
    (folder / "Sub").mkdir()
    (folder / "Sub" / "one.zbp").write_bytes(b"x")         # same names, different list
    (folder / "two.zbp").unlink()
    (folder / "Sub" / "two.zbp").write_bytes(b"x")
    r2 = api.get_library(True, "alpha", sig)
    assert "unchanged" not in r2 and r2["signature"] != sig


def test_a_brush_library_has_the_old_key_only_when_it_has_items(folder, monkeypatch):
    monkeypatch.setattr(brushes, "brush_sources", lambda: [("folder", folder, True)])
    monkeypatch.setattr(brushes, "_index", None)
    api = webapi.LibraryApi()
    r = api.get_library(False, "brush")
    assert r["brushes"] is r["items"] and len(r["items"]) == 3
    assert "brushes" not in api.get_library(False, "brush", r["signature"])
