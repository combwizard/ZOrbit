"""zbp.py: the icon decoder, tested on small .zbp files made here, one per layout it knows."""
import heapq
import os
import struct

import pytest

import brushes
import installs
import zbp

MAGIC = b"ZBrush File?Copyright 1977-2020 Pixologic"


# --- a small encoder: header, RLE, Huffman --------------------------------------------------------

def rle(data: bytes) -> bytes:
    """ZBrush's RLE: c < 128 repeats the next byte c times; c >= 128 copies the next 256 - c bytes."""
    out, i, lit = bytearray(), 0, bytearray()

    def flush():
        while lit:
            chunk, lit[:] = lit[:128], lit[128:]
            out.append(256 - len(chunk))
            out.extend(chunk)

    while i < len(data):
        j = i
        while j < len(data) and data[j] == data[i] and j - i < 127:
            j += 1
        if j - i >= 3:
            flush()
            out += bytes([j - i, data[i]])
            i = j
        else:
            lit.append(data[i])
            i += 1
    flush()
    return bytes(out)


def huffman(inner: bytes) -> bytes:
    """A block as ZBrush writes the "huf1" ones, around the bytes `inner`."""
    freq = {}
    for b in inner:
        freq[b] = freq.get(b, 0) + 1
    if len(freq) < 2:
        freq[(inner[0] + 1) & 255] = 1
    heap = [(n, i, (s,)) for i, (s, n) in enumerate(sorted(freq.items()))]
    heapq.heapify(heap)
    depth = {s: 0 for s in freq}
    uid = len(heap)
    while len(heap) > 1:
        a, b = heapq.heappop(heap), heapq.heappop(heap)
        for s in a[2] + b[2]:
            depth[s] += 1
        heapq.heappush(heap, (a[0] + b[0], uid, a[2] + b[2]))
        uid += 1
    order = sorted(depth, key=lambda s: (depth[s], s))
    assert depth[order[-1]] <= 15
    codes, code, prev = {}, 0, depth[order[0]]
    for s in order:
        code <<= depth[s] - prev
        prev = depth[s]
        codes[s] = (code, depth[s])
        code += 1
    bits = "".join(format(codes[b][0], "0%db" % codes[b][1]) for b in inner)
    bits += "0" * (-len(bits) % 8)
    stream = int(bits, 2).to_bytes(len(bits) // 8, "big") if bits else b""
    lens = [depth[s] for s in order]
    if len(lens) % 2:
        lens.append(0)
    nibbles = bytes((lens[i] << 4) | lens[i + 1] for i in range(0, len(lens), 2))
    nsym = len(order)
    t = 6 + len(nibbles)
    return (struct.pack("<II4sI", 2, len(inner), b"1fuh", len(inner)) + b"\x00" + struct.pack("<I", len(stream))
            + stream + b"\x00" * 10 + bytes(order) + struct.pack("<II", t, nsym) + bytes([min(lens[:nsym]), 4])
            + nibbles)


def header(dim, count_off: int, fixed: bool = False) -> bytearray:
    h = bytearray(count_off)
    h[:len(MAGIC)] = MAGIC
    if fixed:
        struct.pack_into("<II", h, 0x84, dim << 16, dim << 16)
    else:
        struct.pack_into("<ff", h, 0x84, float(dim), float(dim))
    h[count_off - 4:count_off] = b"\x00\x00\x02\x00"
    return h


def zbp_file(dim, blocks, *, count_off=0xEC, extra=4, fixed=False, tail=b"\x00" * 64) -> bytes:
    """count at count_off (0xEC is the current layout), then the sizes, `extra` bytes, then the blocks."""
    body = struct.pack("<I", len(blocks)) + b"".join(struct.pack("<I", len(b)) for b in blocks)
    return bytes(header(dim, count_off, fixed)) + body + b"\x00" * extra + b"".join(blocks) + tail


def planes(dim, rgb=True) -> bytes:
    """Four planes of dim * dim: B, G, R and an unused one. Smooth enough to give runs and literals."""
    n = dim * dim
    b = bytes((i // dim * 3) & 255 for i in range(n))
    g = bytes(((i % dim) * 5) & 255 for i in range(n)) if rgb else b
    r = bytes((i // 7) & 255 for i in range(n)) if rgb else b
    return b + g + r + bytes(n)


@pytest.fixture
def write(tmp_path):
    def put(data, name="b.zbp"):
        p = tmp_path / name
        p.write_bytes(data)
        return p
    return put


# --- layouts --------------------------------------------------------------------------------------

def test_one_block_current_header(write):
    dim = 16
    planar = planes(dim)
    w, h, mode, pix = zbp.decode_zbp_icon(write(zbp_file(dim, [rle(planar)])))
    assert (w, h, mode) == (16, 16, "RGB")
    n = dim * dim
    assert pix[0::3] == planar[2 * n:3 * n] and pix[1::3] == planar[n:2 * n] and pix[2::3] == planar[:n]


def test_one_block_grey_gives_L(write):
    dim = 16
    planar = planes(dim, rgb=False)
    w, h, mode, pix = zbp.decode_zbp_icon(write(zbp_file(dim, [rle(planar)])))
    assert mode == "L" and pix == planar[:dim * dim]


def test_one_block_fixed_point_dimension(write):
    dim = 16
    r = zbp.decode_zbp_icon(write(zbp_file(dim, [rle(planes(dim))], fixed=True)))
    assert r is not None and r[:2] == (16, 16)


@pytest.mark.parametrize("extra", [4, 0, 8])
def test_one_block_older_header_found_through_the_marker(write, extra):
    dim = 16
    data = zbp_file(dim, [rle(planes(dim)), b""], count_off=0xE8, extra=extra)
    r = zbp.decode_zbp_icon(write(data))
    assert r is not None and r[:2] == (16, 16)


def test_eight_strips(write):
    dim = 128
    plen = dim * (dim // 8)
    strips = [bytes(((s * 31 + i // 3) & 255) for i in range(plen)) for s in range(8)]
    blocks = [rle(s + bytes(plen * 3)) for s in strips]
    w, h, mode, pix = zbp.decode_zbp_icon(write(zbp_file(dim, blocks)))
    assert (w, h, mode) == (128, 128, "L")
    assert pix == b"".join(strips)


def test_huffman_block_in_the_old_header(write):
    """The curve brushes and some IMM inserts: the RLE data sits in a Huffman coded block."""
    dim = 16
    planar = planes(dim)
    block = huffman(rle(planar))
    assert zbp._unhuf(block, 0, len(block)) == rle(planar)
    data = zbp_file(dim, [block, b""], count_off=0xE8, extra=0)
    w, h, mode, pix = zbp.decode_zbp_icon(write(data))
    assert (w, h, mode) == (16, 16, "RGB")
    n = dim * dim
    assert pix[0::3] == planar[2 * n:3 * n] and pix[2::3] == planar[:n]


def test_huffman_block_in_the_current_header(write):
    dim = 16
    planar = planes(dim, rgb=False)
    r = zbp.decode_zbp_icon(write(zbp_file(dim, [huffman(rle(planar))])))
    assert r is not None and r[2] == "L" and r[3] == planar[:dim * dim]


def test_huffman_strips(write):
    dim = 128
    plen = dim * (dim // 8)
    strips = [bytes(((s * 17 + i // 5) & 255) for i in range(plen)) for s in range(8)]
    blocks = [huffman(rle(s + bytes(plen * 3))) for s in strips]
    r = zbp.decode_zbp_icon(write(zbp_file(dim, blocks)))
    assert r is not None and r[3] == b"".join(strips)


# --- damaged and foreign files ----------------------------------------------------------------------

def test_huffman_damage_is_none_not_an_error(write):
    dim = 16
    block = bytearray(huffman(rle(planes(dim))))
    block[8:12] = b"abcd"                                   # not a huf1 block any more: read as RLE, which fails
    assert zbp.decode_zbp_icon(write(zbp_file(dim, [bytes(block), b""], count_off=0xE8, extra=0))) is None
    good = huffman(rle(planes(dim)))
    assert zbp._unhuf(good[:len(good) - 30], 0, len(good) - 30) is None        # the table is cut off
    bad = bytearray(good)
    bad[-3] ^= 0xFF                                         # a code length changes: the code is no longer complete
    assert zbp._unhuf(bytes(bad), 0, len(bad)) is None


def test_truncated_data_is_none(write):
    data = zbp_file(16, [rle(planes(16))])
    assert zbp.decode_zbp_icon(write(data[:0xF4])) is None
    assert zbp.decode_zbp_icon(write(data[:0xF4 + 20])) is None


def test_not_a_zbp(write, tmp_path):
    assert zbp.decode_zbp_icon(write(b"")) is None
    assert zbp.decode_zbp_icon(write(os.urandom(2000))) is None
    assert zbp.decode_zbp_icon(tmp_path / "missing.zbp") is None
    bad_dim = bytearray(zbp_file(16, [rle(planes(16))]))
    struct.pack_into("<ff", bad_dim, 0x84, 16.0, 32.0)
    assert zbp.decode_zbp_icon(write(bytes(bad_dim))) is None


# --- the real thing -------------------------------------------------------------------------------

def _stock_brushes():
    try:
        found = installs.find_installs()
    except Exception:
        return []
    for e in reversed(found):                                # the newest installation first
        files = []
        for _, folder, _ in brushes.install_brush_sources(e["path"]):
            for root, _subs, names in os.walk(folder):
                files += [os.path.join(root, n) for n in names if n.lower().endswith(".zbp")]
        if files:
            return files
    return []


def test_stock_brushes_of_an_installed_zbrush_decode():
    files = _stock_brushes()
    if not files:
        pytest.skip("no ZBrush installation with brushes on this PC")
    bad = [f for f in files if zbp.decode_zbp_icon(f) is None]
    assert len(bad) <= 0.05 * len(files), bad[:10]
