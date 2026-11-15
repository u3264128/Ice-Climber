#!/usr/bin/env python3
"""Minimal dependency-free PNG reader (8-bit RGB / RGBA, non-interlaced)."""
from __future__ import annotations

import struct
import zlib


def paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def read_png(path) -> tuple[int, int, list[bytes]]:
    """Return (width, height, rows of RGB triples)."""
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos = 8
    width = height = bitdepth = ctype = 0
    idat = b""
    palette = []
    while pos < len(data):
        (length,), tag = struct.unpack(">I", data[pos:pos + 4]), data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, bitdepth, ctype = struct.unpack(">IIBB", payload[:10])
        elif tag == b"IDAT":
            idat += payload
        elif tag == b"PLTE":
            palette = [payload[i:i + 3] for i in range(0, len(payload), 3)]
        elif tag == b"IEND":
            break
    raw = zlib.decompress(idat)

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    assert bitdepth == 8, f"unsupported bit depth {bitdepth}"
    stride = width * channels
    rows, prev = [], bytearray(stride)
    p = 0
    for y in range(height):
        f = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        for x in range(stride):
            a = line[x - channels] if x >= channels else 0
            b = prev[x]
            c = prev[x - channels] if x >= channels else 0
            if f == 1:
                line[x] = (line[x] + a) & 0xFF
            elif f == 2:
                line[x] = (line[x] + b) & 0xFF
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 0xFF
            elif f == 4:
                line[x] = (line[x] + paeth(a, b, c)) & 0xFF
        prev = line
        rows.append(bytes(line))

    if ctype == 3:      # palette
        rows = [bytes(c for px in row for c in palette[px]) for row in rows]
    elif channels == 1:  # greyscale
        rows = [bytes(v for v in row for _ in range(3)) for row in rows]
    elif channels == 2:  # grey+alpha
        rows = [bytes(v for px in [row[i] for i in range(0, len(row), 2)]
                      for v in (px, px, px)) for row in rows]
    elif channels == 4:  # rgba -> rgb
        rows = [bytes(c for px in range(len(row) // 4)
                      for c in row[px * 4:px * 4 + 3]) for row in rows]
    return width, height, rows


def ascii_preview(path, cell=4, chars=" .:-=+*#%@"):
    w, h, rows = read_png(path)
    out = []
    for y in range(0, h - cell + 1, cell * 2):
        line = ""
        for x in range(0, w - cell + 1, cell):
            tot = n = 0
            for dy in range(cell * 2):
                for dx in range(cell):
                    r, g, b = rows[y + dy][ (x + dx) * 3 : (x + dx) * 3 + 3 ]
                    tot += (r * 299 + g * 587 + b * 114) // 1000
                    n += 1
            line += chars[min(9, tot // n * 10 // 256)]
        out.append(line)
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    w, h, rows = read_png(sys.argv[1])
    colors = {}
    for row in rows:
        for i in range(0, len(row), 3):
            colors[row[i:i + 3]] = colors.get(row[i:i + 3], 0) + 1
    print(f"{w}x{h}, {len(colors)} distinct colours")
    for col, n in sorted(colors.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {col.hex()} x{n}")
    if len(sys.argv) > 2 and sys.argv[2] == "-a":
        print(ascii_preview(sys.argv[1]))
