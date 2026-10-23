"""Vendored brand logos (Simple Icons, CC0 files) drawn as badges; kept apart from the procedural icons.

``assets/logos/png`` holds white-on-transparent 512 px masks rasterised once from ``assets/logos/svg``.
The scene JSON only names a slug from ``LOGO_NAMES``; nothing is fetched at render time.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "assets" / "logos"
_INDEX = json.loads((ROOT / "index.json").read_text(encoding="utf-8"))["logos"]
LOGO_NAMES = tuple(sorted(_INDEX))
SCALE = 4


def logo_catalogue() -> str:
    """``slug (Title)`` pairs for the writer prompt."""
    return ", ".join(f"{slug} ({_INDEX[slug]['title']})" for slug in LOGO_NAMES)


def _colour(hex_value: str) -> tuple[int, int, int]:
    r, g, b = (int(hex_value[i:i + 2], 16) for i in (0, 2, 4))
    # Very light brand colours vanish on the light disc, very dark ones are fine there.
    if 0.299 * r + 0.587 * g + 0.114 * b > 205:
        return 0x1B, 0x24, 0x33
    return r, g, b


@lru_cache(maxsize=64)
def logo_badge(slug: str, diameter: int):
    """Light disc with the logo in its brand colour, supersampled for smooth edges."""
    from PIL import Image, ImageDraw  # lazy: the catalogue is also read where Pillow is not installed
    if slug not in _INDEX:
        raise ValueError(f"unknown logo: {slug}")
    big = diameter * SCALE
    disc = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(disc).ellipse((0, 0, big - 1, big - 1), fill="#f4f7ff", outline="#53e0ef", width=round(big * .035))
    inner = round(big * .6)
    mask = Image.open(ROOT / "png" / f"{slug}.png").convert("RGBA").getchannel("A")
    box = mask.getbbox()
    if box:
        mask = mask.crop(box)
    mask.thumbnail((inner, inner), Image.Resampling.LANCZOS)
    tint = Image.new("RGBA", mask.size, _colour(_INDEX[slug]["hex"]) + (255,))
    tint.putalpha(mask)
    disc.alpha_composite(tint, ((big - mask.width) // 2, (big - mask.height) // 2))
    return disc.resize((diameter, diameter), Image.Resampling.LANCZOS)
