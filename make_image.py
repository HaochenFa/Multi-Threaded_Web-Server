#!/usr/bin/env python3
"""Generate a minimal valid 120x120 PNG for www/image.png (stdlib only)."""
import zlib
import struct
import os


def make_png(width=120, height=120):
    raw = b""
    for _ in range(height):
        raw += b"\x00"                       # filter byte per scanline
        for _ in range(width):
            raw += bytes([70, 130, 180])     # steel-blue RGB
    compressed = zlib.compress(raw)

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = chunk(b"IHDR", struct.pack(
        ">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", compressed)
    iend = chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


os.makedirs("www", exist_ok=True)
with open("www/image.png", "wb") as f:
    f.write(make_png())
print("Created www/image.png (120x120 steel-blue PNG)")
