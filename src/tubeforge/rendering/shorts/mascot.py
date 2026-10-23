"""The Chip mascot: one static sprite, placed in free space only, so it adds no render cost and never covers content."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image

SPRITE = Path(__file__).resolve().parents[2] / "assets" / "brand" / "mascot.png"
SIZE = 170
# Candidate slots, tried in order; the first that touches no mark of the scene wins, otherwise the mascot is hidden for that scene.
RIGHT, LEFT, ABOVE_CAPTION, TOP = 930, 60, 1292, 232


@lru_cache(maxsize=4)
def sprite(size: int = SIZE) -> Image.Image:
    image = Image.open(SPRITE).convert("RGBA")
    box = image.getbbox()
    if box:
        image = image.crop(box)
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    return image


def slots(size: int = SIZE) -> list[tuple[float, float, float, float]]:
    """Bounds of each candidate position for a sprite no larger than ``size``."""
    image = sprite(size)
    w, h = image.size
    return [
        (RIGHT - w, ABOVE_CAPTION - h, RIGHT, ABOVE_CAPTION),   # bottom-right, just above the caption band
        (LEFT, ABOVE_CAPTION - h, LEFT + w, ABOVE_CAPTION),     # bottom-left
        (RIGHT - w, TOP, RIGHT, TOP + h),                       # top-right under the progress bar
        (LEFT, TOP, LEFT + w, TOP + h),                         # top-left
    ]


def place(canvas, intersects, size: int = SIZE) -> tuple[float, float, float, float] | None:
    """Paste the mascot into the first free slot and record it as a mark; None when the scene is too full."""
    image = sprite(size)
    for bounds in slots(size):
        if not any(intersects(bounds, mark.bounds) for mark in canvas.marks):
            at = (round(bounds[0]), round(bounds[1]))
            if canvas.image.mode == "RGBA":
                canvas.image.alpha_composite(image, at)
            else:
                canvas.image.paste(image, at, image)
            return bounds
    return None
