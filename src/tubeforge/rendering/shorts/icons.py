"""Procedural vector icons: topic-independent, no fonts, files or licences.

Each icon is drawn on a 100x100 grid at 4x scale and downsampled, so strokes
stay crisp at any badge size. The scene JSON only names an icon from ICONS.
"""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw

ICON_NAMES = ("shield", "bug", "lock", "gear", "bolt", "cloud", "database", "server", "code", "chip",
              "clock", "chart_up", "chart_down", "check", "cross", "warning", "search", "document",
              "globe", "user", "rocket", "star")
SCALE = 4


def _pts(points, k):
    return [(x * k, y * k) for x, y in points]


def _line(d, points, k, col, w):
    d.line(_pts(points, k), fill=col, width=round(w * k), joint="curve")
    for x, y in (points[0], points[-1]):  # round caps
        r = w * k / 2
        d.ellipse((x * k - r, y * k - r, x * k + r, y * k + r), fill=col)


def _box(box, k):
    return tuple(v * k for v in box)


def _draw_shield(d, k, c, w):
    d.polygon(_pts([(50, 8), (86, 22), (86, 50), (50, 92), (14, 50), (14, 22)], k), outline=c, width=round(w * k))
    _line(d, [(34, 50), (46, 62), (68, 38)], k, c, w)


def _draw_bug(d, k, c, w):
    d.ellipse(_box((32, 36, 68, 86), k), outline=c, width=round(w * k))
    d.ellipse(_box((40, 14, 60, 36), k), outline=c, width=round(w * k))
    for pts in ([(32, 48), (12, 40)], [(32, 62), (10, 62)], [(32, 76), (14, 86)],
                [(68, 48), (88, 40)], [(68, 62), (90, 62)], [(68, 76), (86, 86)],
                [(44, 16), (36, 4)], [(56, 16), (64, 4)], [(50, 38), (50, 86)]):
        _line(d, pts, k, c, w * .8)


def _draw_lock(d, k, c, w):
    d.rounded_rectangle(_box((22, 44, 78, 92), k), radius=8 * k, outline=c, width=round(w * k))
    d.arc(_box((32, 10, 68, 60), k), 180, 360, fill=c, width=round(w * k))
    d.ellipse(_box((44, 58, 56, 70), k), fill=c)
    _line(d, [(50, 66), (50, 78)], k, c, w * .8)


def _draw_gear(d, k, c, w):
    cx = cy = 50
    for i in range(8):
        a = math.radians(i * 45)
        ux, uy, px, py = math.cos(a), math.sin(a), -math.sin(a), math.cos(a)
        r1, r2, hw = 28, 42, 7
        d.polygon(_pts([(cx + ux * r1 + px * hw, cy + uy * r1 + py * hw), (cx + ux * r2 + px * hw, cy + uy * r2 + py * hw),
                        (cx + ux * r2 - px * hw, cy + uy * r2 - py * hw), (cx + ux * r1 - px * hw, cy + uy * r1 - py * hw)], k), fill=c)
    d.ellipse(_box((20, 20, 80, 80), k), outline=c, width=round(w * 1.2 * k))
    d.ellipse(_box((38, 38, 62, 62), k), outline=c, width=round(w * k))


def _draw_bolt(d, k, c, w):
    d.polygon(_pts([(58, 4), (20, 56), (46, 56), (40, 96), (80, 40), (54, 40)], k), fill=c)


def _draw_cloud(d, k, c, w):
    d.ellipse(_box((8, 44, 48, 84), k), fill=c)
    d.ellipse(_box((28, 20, 74, 74), k), fill=c)
    d.ellipse(_box((52, 38, 94, 84), k), fill=c)
    d.rectangle(_box((28, 56, 72, 84), k), fill=c)


def _draw_database(d, k, c, w):
    for top in (10, 38, 66):
        d.arc(_box((20, top, 80, top + 24), k), 0, 180, fill=c, width=round(w * k))
    d.ellipse(_box((20, 8, 80, 32), k), outline=c, width=round(w * k))
    _line(d, [(20, 20), (20, 80)], k, c, w)
    _line(d, [(80, 20), (80, 80)], k, c, w)
    d.arc(_box((20, 68, 80, 92), k), 0, 180, fill=c, width=round(w * k))


def _draw_server(d, k, c, w):
    for top in (12, 40, 68):
        d.rounded_rectangle(_box((12, top, 88, top + 22), k), radius=5 * k, outline=c, width=round(w * k))
        d.ellipse(_box((22, top + 7, 30, top + 15), k), fill=c)
        _line(d, [(62, top + 11), (78, top + 11)], k, c, w * .7)


def _draw_code(d, k, c, w):
    _line(d, [(36, 26), (10, 50), (36, 74)], k, c, w)
    _line(d, [(64, 26), (90, 50), (64, 74)], k, c, w)
    _line(d, [(56, 18), (44, 82)], k, c, w * .8)


def _draw_chip(d, k, c, w):
    d.rounded_rectangle(_box((26, 26, 74, 74), k), radius=6 * k, outline=c, width=round(w * k))
    d.rectangle(_box((40, 40, 60, 60), k), fill=c)
    for p in (38, 50, 62):
        _line(d, [(p, 26), (p, 12)], k, c, w * .7)
        _line(d, [(p, 74), (p, 88)], k, c, w * .7)
        _line(d, [(26, p), (12, p)], k, c, w * .7)
        _line(d, [(74, p), (88, p)], k, c, w * .7)


def _draw_clock(d, k, c, w):
    d.ellipse(_box((8, 8, 92, 92), k), outline=c, width=round(w * k))
    _line(d, [(50, 50), (50, 24)], k, c, w)
    _line(d, [(50, 50), (68, 62)], k, c, w)


def _arrow_head(d, k, c, tip, a):
    x, y = tip
    d.polygon(_pts([(x, y), (x - 14 * math.cos(a - .5), y - 14 * math.sin(a - .5)),
                    (x - 14 * math.cos(a + .5), y - 14 * math.sin(a + .5))], k), fill=c)


def _draw_chart_up(d, k, c, w):
    _line(d, [(12, 10), (12, 88), (92, 88)], k, c, w * .8)
    _line(d, [(24, 70), (44, 50), (58, 60), (80, 28)], k, c, w)
    _arrow_head(d, k, c, (88, 18), math.atan2(-10, 8))


def _draw_chart_down(d, k, c, w):
    _line(d, [(12, 10), (12, 88), (92, 88)], k, c, w * .8)
    _line(d, [(24, 24), (44, 44), (58, 36), (80, 68)], k, c, w)
    _arrow_head(d, k, c, (88, 78), math.atan2(10, 8))


def _draw_check(d, k, c, w):
    _line(d, [(16, 52), (40, 76), (86, 24)], k, c, w * 1.3)


def _draw_cross(d, k, c, w):
    _line(d, [(22, 22), (78, 78)], k, c, w * 1.3)
    _line(d, [(78, 22), (22, 78)], k, c, w * 1.3)


def _draw_warning(d, k, c, w):
    d.polygon(_pts([(50, 10), (94, 86), (6, 86)], k), outline=c, width=round(w * k))
    _line(d, [(50, 38), (50, 62)], k, c, w)
    d.ellipse(_box((45, 68, 55, 78), k), fill=c)


def _draw_search(d, k, c, w):
    d.ellipse(_box((10, 10, 66, 66), k), outline=c, width=round(w * k))
    _line(d, [(58, 58), (90, 90)], k, c, w * 1.3)


def _draw_document(d, k, c, w):
    d.polygon(_pts([(22, 6), (58, 6), (78, 26), (78, 94), (22, 94)], k), outline=c, width=round(w * k))
    _line(d, [(58, 6), (58, 26), (78, 26)], k, c, w * .8)
    for y, x2 in ((46, 66), (60, 66), (74, 52)):
        _line(d, [(34, y), (x2, y)], k, c, w * .7)


def _draw_globe(d, k, c, w):
    d.ellipse(_box((8, 8, 92, 92), k), outline=c, width=round(w * k))
    d.ellipse(_box((32, 8, 68, 92), k), outline=c, width=round(w * .8 * k))
    for y in (30, 50, 70):
        _line(d, [(14, y), (86, y)], k, c, w * .7)


def _draw_user(d, k, c, w):
    d.ellipse(_box((32, 10, 68, 46), k), outline=c, width=round(w * k))
    d.arc(_box((14, 56, 86, 128), k), 180, 360, fill=c, width=round(w * k))


def _draw_rocket(d, k, c, w):
    d.polygon(_pts([(50, 4), (68, 30), (68, 66), (32, 66), (32, 30)], k), outline=c, width=round(w * k))
    d.ellipse(_box((42, 30, 58, 46), k), outline=c, width=round(w * .8 * k))
    d.polygon(_pts([(32, 50), (14, 76), (32, 68)], k), fill=c)
    d.polygon(_pts([(68, 50), (86, 76), (68, 68)], k), fill=c)
    d.polygon(_pts([(42, 72), (50, 96), (58, 72)], k), fill=c)


def _draw_star(d, k, c, w):
    pts = []
    for i in range(10):
        r = 44 if i % 2 == 0 else 18
        a = math.radians(-90 + i * 36)
        pts.append((50 + r * math.cos(a), 54 + r * math.sin(a)))
    d.polygon(_pts(pts, k), fill=c)


_DRAWERS = {name: globals()[f"_draw_{name}"] for name in ICON_NAMES}


@lru_cache(maxsize=256)
def icon_image(name: str, size: int, color: str = "#f4f7ff") -> Image.Image:
    """RGBA icon of ``size`` px square, drawn supersampled."""
    if name not in _DRAWERS:
        raise ValueError(f"unknown icon: {name}")
    big = Image.new("RGBA", (size * SCALE, size * SCALE), (0, 0, 0, 0))
    _DRAWERS[name](ImageDraw.Draw(big), size * SCALE / 100, color, 7)
    return big.resize((size, size), Image.Resampling.LANCZOS)


@lru_cache(maxsize=64)
def badge(name: str, diameter: int, fill: str = "#183c46", ring: str = "#53e0ef", glyph: str = "#f4f7ff") -> Image.Image:
    """Circular badge with the icon centred; supersampled ring for smooth edges."""
    big = Image.new("RGBA", (diameter * SCALE, diameter * SCALE), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.ellipse((0, 0, diameter * SCALE - 1, diameter * SCALE - 1), fill=fill, outline=ring, width=round(diameter * SCALE * .035))
    out = big.resize((diameter, diameter), Image.Resampling.LANCZOS)
    inner = round(diameter * .56)
    out.alpha_composite(icon_image(name, inner, glyph), ((diameter - inner) // 2, (diameter - inner) // 2))
    return out
