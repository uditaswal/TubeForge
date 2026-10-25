#!/usr/bin/env python3
"""Draw "Chip", the TubeForge mascot: one static RGBA sprite (original art, no external assets).

Usage: python scripts/make_mascot.py [output.png]   (default: src/tubeforge/assets/brand/mascot.png)
The sprite is composited as a single cached layer, so using it costs no extra render time.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE, K = 512, 4  # output size, supersampling factor
NAVY, NAVY_DARK, VISOR = "#1d3f73", "#0e2243", "#06101f"
CYAN, CYAN_SOFT, AMBER, WHITE = "#53e0ef", "#2b9fb3", "#ffc46b", "#f4f7ff"


def px(v: float) -> int:
    return round(v * K)


def glow(canvas: Image.Image, draw_fn, colour: str, blur: float, strength: float) -> None:
    """Soft coloured light behind a shape: blur only the mask so the colour stays clean."""
    mask = Image.new("L", canvas.size, 0)
    draw_fn(ImageDraw.Draw(mask), 255)
    layer = Image.new("RGBA", canvas.size, colour)
    layer.putalpha(mask.filter(ImageFilter.GaussianBlur(px(blur))).point(lambda v: int(v * strength)))
    canvas.alpha_composite(layer)


def gradient(box, top: str, bottom: str, radius: int, canvas: Image.Image) -> None:
    x0, y0, x1, y1 = box
    strip = Image.new("RGBA", (x1 - x0, y1 - y0))
    sd = ImageDraw.Draw(strip)
    t, b = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (top, bottom))
    for y in range(strip.height):
        f = y / max(1, strip.height - 1)
        sd.line([(0, y), (strip.width, y)], fill=tuple(round(t[j] + (b[j] - t[j]) * f) for j in range(3)) + (255,))
    mask = Image.new("L", strip.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, strip.width - 1, strip.height - 1), radius=radius, fill=255)
    canvas.paste(strip, (x0, y0), mask)


def draw() -> Image.Image:
    big = Image.new("RGBA", (SIZE * K, SIZE * K), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    # --- antenna with an amber beacon
    d.line([(px(256), px(96)), (px(256), px(52))], fill=CYAN, width=px(9))
    glow(big, lambda g, v: g.ellipse((px(232), px(14), px(280), px(62)), fill=v), AMBER, 14, .9)
    d.ellipse((px(238), px(20), px(274), px(56)), fill=AMBER, outline="#fff1d1", width=px(3))
    d.ellipse((px(246), px(26), px(256), px(36)), fill="#fff7e6")
    # --- body (little torso) with chest light and a circuit trace
    glow(big, lambda g, v: g.rounded_rectangle((px(176), px(352), px(336), px(480)), px(40), fill=v), CYAN, 16, .35)
    gradient((px(180), px(356), px(332), px(476)), NAVY, NAVY_DARK, px(38), big)
    d.rounded_rectangle((px(180), px(356), px(332), px(476)), px(38), outline=CYAN, width=px(6))
    d.ellipse((px(236), px(386), px(276), px(426)), fill=VISOR, outline=CYAN_SOFT, width=px(4))
    glow(big, lambda g, v: g.ellipse((px(246), px(396), px(266), px(416)), fill=v), CYAN, 6, .9)
    d.ellipse((px(246), px(396), px(266), px(416)), fill=CYAN)
    d.line([(px(206), px(448)), (px(236), px(448)), (px(246), px(438))], fill=CYAN_SOFT, width=px(5), joint="curve")
    d.line([(px(306), px(448)), (px(276), px(448)), (px(266), px(438))], fill=CYAN_SOFT, width=px(5), joint="curve")
    # --- head
    glow(big, lambda g, v: g.rounded_rectangle((px(92), px(92), px(420), px(352)), px(76), fill=v), CYAN, 22, .45)
    gradient((px(96), px(96), px(416), px(348)), "#27508f", NAVY_DARK, px(74), big)
    d.rounded_rectangle((px(96), px(96), px(416), px(348)), px(74), outline=CYAN, width=px(8))
    for cx in (96, 416):  # ear pods
        d.ellipse((px(cx - 22), px(188), px(cx + 22), px(256)), fill=NAVY_DARK, outline=CYAN, width=px(6))
        d.ellipse((px(cx - 9), px(210), px(cx + 9), px(234)), fill=CYAN)
    # circuit traces on the forehead (echoes the ProTech mark)
    d.line([(px(150), px(124)), (px(196), px(124)), (px(212), px(140))], fill=CYAN_SOFT, width=px(5), joint="curve")
    d.line([(px(362), px(124)), (px(316), px(124)), (px(300), px(140))], fill=CYAN_SOFT, width=px(5), joint="curve")
    for p in ((150, 124), (362, 124)):
        d.ellipse((px(p[0] - 8), px(p[1] - 8), px(p[0] + 8), px(p[1] + 8)), fill=CYAN)
    # visor face
    d.rounded_rectangle((px(128), px(156), px(384), px(322)), px(54), fill=VISOR, outline="#14305a", width=px(6))
    for ex in (196, 316):  # eyes: glowing rounded ovals with a highlight
        glow(big, lambda g, v, ex=ex: g.ellipse((px(ex - 30), px(196), px(ex + 30), px(268)), fill=v), CYAN, 9, .8)
        d.ellipse((px(ex - 28), px(196), px(ex + 28), px(266)), fill=CYAN)
        d.ellipse((px(ex - 12), px(205), px(ex + 2), px(224)), fill=WHITE)
    d.arc((px(222), px(246), px(290), px(300)), 20, 160, fill=CYAN, width=px(8))  # smile
    d.line([(px(168), px(176)), (px(222), px(168))], fill=CYAN_SOFT, width=px(7))  # raised brow
    d.line([(px(290), px(170)), (px(344), px(178))], fill=CYAN_SOFT, width=px(7))
    # --- arms (drawn over the head edge so the waving hand stays visible)
    wave = [(184, 384), (96, 372), (58, 300)]
    d.line([(px(x), px(y)) for x, y in wave], fill=NAVY, width=px(30), joint="curve")
    d.line([(px(x), px(y)) for x, y in wave], fill=CYAN, width=px(6), joint="curve")
    for x, y in wave[:2]:
        d.ellipse((px(x - 15), px(y - 15), px(x + 15), px(y + 15)), fill=NAVY, outline=CYAN, width=px(5))
    d.ellipse((px(30), px(256), px(86), px(312)), fill=WHITE, outline=CYAN, width=px(6))
    d.line([(px(328), px(384)), (px(372), px(440))], fill=NAVY, width=px(28))
    d.line([(px(328), px(384)), (px(372), px(440))], fill=CYAN, width=px(5))
    d.ellipse((px(356), px(424), px(392), px(460)), fill=WHITE, outline=CYAN, width=px(6))
    return big.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "src/tubeforge/assets/brand/mascot.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    draw().save(target, optimize=True)
    print(target, target.stat().st_size)
