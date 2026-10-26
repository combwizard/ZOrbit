"""Decoder for the embedded icon of ZBrush .zbp brush files (stdlib only).

Public API: decode_zbp_icon(path) -> (width, height, mode, pixels) | None
mode is "RGB" (interleaved) or "L". Never raises.

File structure (all little-endian):
  0x00  b"ZBrush File?Copyright 1977-..."  (one filler byte, sometimes '*')
  0x84  float32 width, float32 height of the embedded icon (96 or 512)
  ...   a short header chunk stream ending in the marker 00 00 02 00
  then  uint32 block count, `count` uint32 compressed sizes, optionally one
        more uint32, then RLE data; blocks follow each other, one `size` each.
Current files (ZBrush 4.7+) put the count at 0xEC; older files (3.x - 4.4)
have shorter headers, so the count sits at 0xE0 or 0xE8 and is found through
the marker. Block layouts: one block = 4 planar planes of dim*dim (old, 96px);
eight blocks = horizontal strips of dim x dim/8 (new, 512px).
"""
from __future__ import annotations

import struct

_MAGIC = b"ZBrush File"
_COPYRIGHT = b"Copyright 1977-"
_DIM_OFF = 0x84
_COUNT_OFF = 0xEC
_MARKER = b"\x00\x00\x02\x00"
_MAX_DIM = 4096


def _unrle(data, pos: int, end: int, want: int):
    """Decode RLE from data[pos:end] until `want` bytes exist.

    Returns (bytearray, bytes_consumed)."""
    out = bytearray()
    ext = out.extend
    n = 0
    start = pos
    while pos < end and n < want:
        c = data[pos]
        pos += 1
        if c < 128:
            if pos >= end:
                break
            if c:
                ext(data[pos:pos + 1] * c)
                n += c
            pos += 1
        else:
            k = 256 - c
            ext(data[pos:pos + k])
            n += k
            pos += k
    return out, pos - start


def _planar_rgb(dim: int, buf):
    plen = dim * dim
    pb, pg, pr = (bytes(buf[i * plen:(i + 1) * plen]) for i in range(3))
    if pb == pg == pr:
        return dim, dim, "L", pb
    rgb = bytearray(plen * 3)
    rgb[0::3] = pr
    rgb[1::3] = pg
    rgb[2::3] = pb
    return dim, dim, "RGB", bytes(rgb)


def _parse(d: bytes, dim: int, count_off: int, extra: int, strict: bool):
    if count_off + 4 > len(d):
        return None
    count = struct.unpack_from("<I", d, count_off)[0]
    sizes_off = count_off + 4
    if not (1 <= count <= 64) or sizes_off + 4 * count + extra > len(d):
        return None
    sizes = struct.unpack_from("<%dI" % count, d, sizes_off)
    pos = sizes_off + 4 * count + extra
    blocks = [s for s in sizes if s]
    n = len(blocks)

    if n == 1:
        # Old format: one block, 4 planar planes of dim*dim (B, G, R, unused).
        plen = dim * dim
        buf, used = _unrle(d, pos, min(pos + blocks[0], len(d)), plen * 4)
        if len(buf) < plen * 3:
            return None
        if strict and not (len(buf) == plen * 4 and 0 <= blocks[0] - used <= 16):
            return None
        return _planar_rgb(dim, buf)

    if n >= 8 and dim > 96 and dim % 8 == 0:
        # New format: 8 horizontal strips, each 4 planes of dim * dim/8
        # (plane 0 is the grey icon). Extra blocks after the 8th are ignored.
        plen = dim * (dim // 8)
        rows = []
        for sz in blocks[:8]:
            end = pos + sz
            if end > len(d):
                return None
            buf, _ = _unrle(d, pos, end, plen * 4)
            if len(buf) < plen:
                return None
            rows.append(bytes(buf[:plen]))
            pos = end
        return dim, dim, "L", b"".join(rows)

    return None


def _decode(path):
    with open(path, "rb") as f:
        d = f.read()
    if not d.startswith(_MAGIC) or _COPYRIGHT not in d[:0x30] or len(d) < 0xF8:
        return None
    a, b = struct.unpack_from("<ff", d, _DIM_OFF)
    if a != b or a != int(a) or not (16 <= a <= _MAX_DIM):
        return None
    dim = int(a)

    r = _parse(d, dim, _COUNT_OFF, 4, False)
    if r is not None:
        return r
    # Older header layouts: the count follows the 00 00 02 00 marker.
    i = d.find(_MARKER, 0xB0, 0x100)
    while i >= 0:
        for extra in (4, 0, 8):
            r = _parse(d, dim, i + 4, extra, True)
            if r is not None:
                return r
        i = d.find(_MARKER, i + 1, 0x100)
    return None


def decode_zbp_icon(path):
    try:
        return _decode(path)
    except Exception:
        return None
