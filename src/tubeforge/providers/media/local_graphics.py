"""Deterministic production-safe motion-graphics source frames."""

from __future__ import annotations

import hashlib
import struct
import zlib
from datetime import UTC, datetime
from pathlib import Path

from tubeforge.core.config import FakeProviderConfig
from tubeforge.domain.contracts import AssetCandidate, MediaSearchRequest


STYLE_VERSION = "portrait-motion-v1"
PALETTE_ID = "midnight-cyan-violet-amber"
_NAVY = (8, 14, 31)
_CYAN = (63, 220, 238)
_VIOLET = (127, 111, 238)
_AMBER = (251, 191, 36)


class LocalMotionGraphicsProvider:
    """Create coherent, rights-safe scene art without an external generator.

    Every frame shares one reference palette and safe central composition, but
    the approved scene query selects a distinct layout, focal position, and
    accent. The renderer supplies the motion so these source frames remain
    deterministic, cacheable, and straightforward to inspect.
    """

    def __init__(self, settings: FakeProviderConfig) -> None:
        self.settings = settings
        self.calls = 0

    def search(self, request: MediaSearchRequest) -> list[AssetCandidate]:
        self.calls += 1
        identity = "|".join((request.scene_id, request.visual_type, *request.queries))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        portrait = request.orientation == "portrait"
        width, height = (1080, 1920) if portrait else (1920, 1080)
        layout = int(digest[:2], 16) % 4
        path = self.settings.artifact_root / "motion-graphics" / f"{digest[:16]}-{width}x{height}.png"
        _atomic_write(path, _graphic_png(width, height, digest, layout))
        version = f"{STYLE_VERSION}:{PALETTE_ID}:layout-{layout}"
        return [
            AssetCandidate(
                provider_asset_id=f"local-motion-{digest[:20]}",
                source_url=f"https://example.invalid/local-motion/{digest[:16]}.png",
                download_url=f"https://example.invalid/local-motion/{digest[:16]}.png",
                source_version=version,
                local_path=str(path),
                media_type="image",
                width=width,
                height=height,
                author="TubeForge local motion graphics",
                license_name=self.settings.media_license,
                attribution_text=f"TubeForge {PALETTE_ID} generated scene art",
                retrieved_at=datetime.now(UTC),
            )
        ]


def _graphic_png(width: int, height: int, digest: str, layout: int) -> bytes:
    """Draw a crisp brand-consistent scene frame using only the standard library."""
    seed = int(digest[:16], 16)
    pixels = bytearray(width * height * 3)
    for y in range(height):
        vertical = y / max(1, height - 1)
        for x in range(width):
            horizontal = x / max(1, width - 1)
            glow = max(0.0, 1.0 - (((horizontal - 0.5) / 0.8) ** 2 + ((vertical - 0.38) / 0.7) ** 2))
            noise = ((x * 13 + y * 7 + seed) % 19) / 19
            offset = (y * width + x) * 3
            pixels[offset] = min(255, int(_NAVY[0] + 12 * glow + 2 * noise))
            pixels[offset + 1] = min(255, int(_NAVY[1] + 19 * glow + 3 * noise))
            pixels[offset + 2] = min(255, int(_NAVY[2] + 32 * glow + 5 * noise))

    accent = (_CYAN, _VIOLET, _AMBER)[seed % 3]
    secondary = (_VIOLET, _AMBER, _CYAN)[seed % 3]
    unit = min(width, height)
    safe_left, safe_right = int(width * 0.12), int(width * 0.88)
    safe_top, safe_bottom = int(height * 0.10), int(height * 0.68)

    # A restrained reference grid unifies all scenes and keeps the lower
    # caption region visually quiet.
    for index in range(1, 6):
        x = safe_left + (safe_right - safe_left) * index // 6
        _line(pixels, width, height, x, safe_top, x, safe_bottom, (24, 49, 76), max(1, unit // 540))
    for index in range(1, 5):
        y = safe_top + (safe_bottom - safe_top) * index // 5
        _line(pixels, width, height, safe_left, y, safe_right, y, (24, 49, 76), max(1, unit // 540))

    focus_x = int(width * (0.34 + ((seed >> 8) % 33) / 100))
    focus_y = int(height * (0.25 + ((seed >> 16) % 22) / 100))
    radius = max(70, int(unit * 0.16))
    if layout == 0:
        _circle(pixels, width, height, focus_x, focus_y, radius, (18, 35, 62))
        _ring(pixels, width, height, focus_x, focus_y, radius, accent, max(5, unit // 150))
        for step in range(5):
            angle_x = safe_left + step * (safe_right - safe_left) // 4
            _line(pixels, width, height, focus_x, focus_y, angle_x, safe_bottom, secondary, max(3, unit // 230))
            _circle(pixels, width, height, angle_x, safe_bottom, max(8, unit // 70), accent)
    elif layout == 1:
        card_w, card_h = int(width * 0.58), int(height * 0.12)
        for step in range(4):
            x = safe_left + (step % 2) * int(width * 0.12)
            y = safe_top + step * int(height * 0.13)
            _rect(pixels, width, height, x, y, min(width - safe_left, x + card_w), y + card_h, (18, 36, 61))
            _rect(pixels, width, height, x, y, x + max(7, unit // 90), y + card_h, accent if step % 2 == 0 else secondary)
            _circle(pixels, width, height, x + int(card_w * 0.78), y + card_h // 2, max(12, unit // 46), secondary)
    elif layout == 2:
        points: list[tuple[int, int]] = []
        for step in range(6):
            x = safe_left + step * (safe_right - safe_left) // 5
            y = safe_bottom - int((0.18 + ((seed >> (step * 5)) & 31) / 50) * (safe_bottom - safe_top))
            points.append((x, y))
        for first, second in zip(points, points[1:]):
            _line(pixels, width, height, *first, *second, accent, max(5, unit // 150))
        for index, (x, y) in enumerate(points):
            _circle(pixels, width, height, x, y, max(11, unit // 55), secondary if index % 2 else accent)
    else:
        center_x = width // 2
        for step in range(5):
            radius_step = radius + step * max(24, unit // 20)
            _ring(pixels, width, height, center_x, focus_y, radius_step, accent if step % 2 == 0 else secondary, max(3, unit // 260))
        _circle(pixels, width, height, center_x, focus_y, max(22, unit // 28), _AMBER)

    # The small top marker supplies visual rhythm while leaving narration
    # captions and platform UI safe areas clear.
    _rect(pixels, width, height, safe_left, int(height * 0.055), safe_left + int(width * 0.18), int(height * 0.062), accent)
    rows = b"".join(b"\x00" + pixels[y * width * 3 : (y + 1) * width * 3] for y in range(height))
    return _png(width, height, rows)


def _rect(data: bytearray, width: int, height: int, left: int, top: int, right: int, bottom: int, color: tuple[int, int, int]) -> None:
    for y in range(max(0, top), min(height, bottom)):
        start = (y * width + max(0, left)) * 3
        stop = (y * width + min(width, right)) * 3
        data[start:stop] = bytes(color) * max(0, min(width, right) - max(0, left))


def _circle(data: bytearray, width: int, height: int, cx: int, cy: int, radius: int, color: tuple[int, int, int]) -> None:
    radius_squared = radius * radius
    for y in range(max(0, cy - radius), min(height, cy + radius + 1)):
        dy = y - cy
        half = int(max(0, radius_squared - dy * dy) ** 0.5)
        _rect(data, width, height, cx - half, y, cx + half + 1, y + 1, color)


def _ring(data: bytearray, width: int, height: int, cx: int, cy: int, radius: int, color: tuple[int, int, int], thickness: int) -> None:
    _circle(data, width, height, cx, cy, radius, color)
    _circle(data, width, height, cx, cy, max(1, radius - thickness), (18, 35, 62))


def _line(data: bytearray, width: int, height: int, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int], thickness: int) -> None:
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    for step in range(steps + 1):
        x = round(x0 + (x1 - x0) * step / steps)
        y = round(y0 + (y1 - y0) * step / steps)
        _rect(data, width, height, x - thickness, y - thickness, x + thickness + 1, y + thickness + 1, color)


def _png(width: int, height: int, raw: bytes) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, level=6)) + chunk(b"IEND", b"")


def _atomic_write(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)


__all__ = ["LocalMotionGraphicsProvider", "PALETTE_ID", "STYLE_VERSION"]
