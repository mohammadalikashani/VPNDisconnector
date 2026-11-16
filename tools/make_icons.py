#!/usr/bin/env python3
"""Generates extension/icons/icon{16,32,48,128}.png (no dependencies).

Design: orange rounded square, white globe ring with a diagonal slash
("this site skips the VPN").
"""
import math
import os
import struct
import zlib

ORANGE = (217, 119, 6)
WHITE = (255, 255, 255)
SS = 4  # supersampling for anti-aliasing


def coverage(fn, x, y, size):
    hits = 0
    for sy in range(SS):
        for sx in range(SS):
            u = (x + (sx + 0.5) / SS) / size
            v = (y + (sy + 0.5) / SS) / size
            hits += fn(u, v)
    return hits / (SS * SS)


def in_bg(u, v, r=0.22):
    # rounded square in unit coordinates
    cx = min(max(u, r), 1 - r)
    cy = min(max(v, r), 1 - r)
    return (u - cx) ** 2 + (v - cy) ** 2 <= r * r


def in_fg(u, v):
    d = math.hypot(u - 0.5, v - 0.5)
    ring = 0.22 <= d <= 0.31
    meridian = abs(u - 0.5) <= 0.035 and d <= 0.31
    equator = abs(v - 0.5) <= 0.035 and d <= 0.31
    # slash from top-right to bottom-left
    slash_dist = abs((u - 0.5) + (v - 0.5)) / math.sqrt(2)
    slash = slash_dist <= 0.05 and d <= 0.40
    gap = 0.05 < slash_dist <= 0.10 and d <= 0.40  # cut-out around the slash
    return (ring or meridian or equator or slash) and not gap


def render(size):
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter: none
        for x in range(size):
            a_bg = coverage(in_bg, x, y, size)
            a_fg = coverage(lambda u, v: in_bg(u, v) and in_fg(u, v), x, y, size)
            if a_bg == 0:
                row += bytes((0, 0, 0, 0))
                continue
            t = a_fg / a_bg
            rgb = [round(ORANGE[i] * (1 - t) + WHITE[i] * t) for i in range(3)]
            row += bytes((*rgb, round(255 * a_bg)))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "extension", "icons")
    os.makedirs(out, exist_ok=True)
    for s in (16, 32, 48, 128):
        with open(os.path.join(out, f"icon{s}.png"), "wb") as f:
            f.write(render(s))
        print(f"icon{s}.png")
