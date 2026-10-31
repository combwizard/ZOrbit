"""Decoder for the embedded icon of ZBrush .zbp brush files (stdlib only).

Public API: decode_zbp_icon(path) -> (width, height, mode, pixels) | None
mode is "RGB" (interleaved) or "L". Never raises.

File structure (all little-endian):
  0x00  b"ZBrush File?Copyright 1977-..."  (one filler byte, sometimes '*')
  0x84  float32 width, float32 height of the embedded icon (96 or 512); a few
        files (old .zmt materials) store the pair as 16.16 fixed point instead
  ...   a short header chunk stream ending in the marker 00 00 02 00
  then  uint32 block count, `count` uint32 compressed sizes, optionally one
        more uint32, then RLE data; blocks follow each other, one `size` each.
A block is RLE data, or (a few stock brushes, such as the curve brushes and some IMM inserts) a Huffman
coded stream that holds the RLE data; see _unhuf for that layout.
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

_HUF_TAG = b"1fuh"             # "huf1" read backwards
_MAX_HUF_OUT = 1 << 24


def _unhuf(d, pos: int, end: int):
    """The bytes inside a Huffman coded block d[pos:end], or None when the block is not one (or is damaged).

    Layout of a block (little-endian):
      u32 2, u32 n, b"1fuh", u32 n   n is the length of the data inside
      u8 0, u32 m                    m is the length of the bit stream
      bit stream                     MSB first, canonical code, n symbols
      symbols                        the nsym byte values in code order
      u32 t, u32 nsym, 2 bytes, then nsym code lengths as nibbles, high nibble first  (t = 4 + 2 + nibble bytes)
    A code is canonical when the symbols are listed by growing length; the shortest code is all zeros. The code
    lengths must fill the code space exactly."""
    blk = d[pos:end]
    ln = len(blk)
    if ln < 40 or blk[8:12] != _HUF_TAG:
        return None
    method, n, tag, n2 = struct.unpack_from("<I I 4s I", blk, 0)
    if method != 2 or n != n2 or not (0 < n <= _MAX_HUF_OUT):
        return None
    m = struct.unpack_from("<I", blk, 17)[0]
    start = 21
    for nsym in range(1, 257):
        t = 6 + (nsym + 1) // 2
        tpos = ln - 4 - t
        if tpos < start + m or struct.unpack_from("<II", blk, tpos) != (t, nsym):
            continue
        symoff = tpos - nsym
        if symoff < start + m:
            continue
        syms = blk[symoff:tpos]
        packed = blk[tpos + 10:]
        lens = []
        for b in packed:
            lens += (b >> 4, b & 15)
        lens = lens[:nsym]
        if min(lens) < 1 or sum(1 << (15 - x) for x in lens) != 1 << 15:
            continue
        # canonical code: per length, the first code and the index of its first symbol
        count = [0] * 16
        for x in lens:
            count[x] += 1
        first, index, code, i = [0] * 16, [0] * 16, 0, 0
        for x in range(1, 16):
            first[x], index[x] = code, i
            code = (code + count[x]) << 1
            i += count[x]
        out = bytearray()
        code = cl = 0
        try:
            for b in blk[start:start + m]:
                for k in range(7, -1, -1):
                    code = (code << 1) | ((b >> k) & 1)
                    cl += 1
                    if cl > 15:
                        return None
                    if count[cl] and code - first[cl] < count[cl]:
                        if code < first[cl]:
                            return None
                        out.append(syms[index[cl] + code - first[cl]])
                        code = cl = 0
                        if len(out) == n:
                            return bytes(out)
        except IndexError:
            return None
        return None
    return None


def _block(d, pos: int, end: int, want: int):
    """(bytes, slack) of one block: the RLE data decoded until `want` bytes exist (inside a Huffman coded stream
    when the block is one). slack is how many bytes of the block were left over."""
    inner = _unhuf(d, pos, end)
    if inner is not None:
        buf, used = _unrle(inner, 0, len(inner), want)
        return buf, len(inner) - used
    buf, used = _unrle(d, pos, end, want)
    return buf, (end - pos) - used


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
        buf, slack = _block(d, pos, min(pos + blocks[0], len(d)), plen * 4)
        if len(buf) < plen * 3:
            return None
        if strict and not (len(buf) == plen * 4 and 0 <= slack <= 16):
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
            buf, _ = _block(d, pos, end, plen * 4)
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
    if a == b and a == int(a) and 16 <= a <= _MAX_DIM:
        dim = int(a)
    else:
        ia, ib = struct.unpack_from("<II", d, _DIM_OFF)      # 16.16 fixed point, e.g. 0x00600000 = 96
        if ia != ib or ia & 0xFFFF or not (16 <= ia >> 16 <= _MAX_DIM):
            return None
        dim = ia >> 16

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
