#!/usr/bin/env python3
"""Minimal dependency-free PNG writer (RGB, 8-bit, no interlace)."""
from __future__ import annotations

import struct
import zlib


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def write_png(path, width: int, height: int, rows: list[bytes]) -> None:
    """rows: list of `height` byte-strings, each 3*width RGB triples."""
    raw = b"".join(b"\x00" + row for row in rows)
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(raw, 9))
           + _chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


class Canvas:
    """Tiny RGB pixel canvas with rectangle blitting."""

    def __init__(self, width: int, height: int, fill=(0, 0, 0)):
        self.w, self.h = width, height
        self.buf = bytearray(bytes(fill * (width * height)))

    def px(self, x: int, y: int, rgb):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i:i + 3] = bytes(rgb)

    def blit(self, x0: int, y0: int, tile: list[list], palette: dict):
        """tile: 2D list of palette-index values (ints)."""
        for y, row in enumerate(tile):
            for x, idx in enumerate(row):
                self.px(x0 + x, y0 + y, palette[idx])

    def save(self, path):
        write_png(path, self.w, self.h,
                  [bytes(self.buf[r * self.w * 3:(r + 1) * self.w * 3])
                   for r in range(self.h)])
