"""Deterministic, local M12 publication-preparation primitives."""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path
from typing import Any

from tubeforge.core.config import PublicationPreparationConfig
from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentPackage


def identity(value: object) -> str:
    """Return a canonical durable identity without timestamps or paths."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _clean(value: str) -> str:
    if any(ord(character) < 32 and character not in "\n\t" for character in value):
        raise ProviderValidationError("metadata contains control characters")
    return " ".join(value.replace("\t", " ").split())


def metadata_from_package(package: ContentPackage, timing: dict[str, Any], config: PublicationPreparationConfig) -> dict[str, object]:
    """Normalize the approved package into locally validated publish metadata."""
    title = _clean(package.metadata.title_options[0])
    description = package.metadata.description.replace("\r\n", "\n").replace("\r", "\n").strip()
    if any(ord(character) < 32 and character not in "\n\t" for character in description):
        raise ProviderValidationError("metadata contains control characters")
    tags: list[str] = []
    for raw in package.metadata.tags:
        tag = _clean(raw)
        if not tag:
            raise ProviderValidationError("metadata contains an empty tag")
        if len(tag) > config.tag_max_length:
            raise ProviderValidationError("metadata tag exceeds configured length")
        if tag.casefold() not in {item.casefold() for item in tags}:
            tags.append(tag)
    if not title or len(title) > config.title_max_length:
        raise ProviderValidationError("metadata title violates configured limits")
    if not description or len(description) > config.description_max_length:
        raise ProviderValidationError("metadata description violates configured limits")
    if len(tags) > config.tag_max_count or sum(len(item) for item in tags) > config.tag_payload_max_length:
        raise ProviderValidationError("metadata tags exceed configured limits")
    chapters = derive_chapters(package, timing)
    result: dict[str, object] = {"title": title, "description": description, "tags": tags, "chapters": chapters, "validation": "accepted"}
    if package.metadata.engagement_comment:
        result["engagement_comment"] = _clean(package.metadata.engagement_comment)
    return result


def derive_chapters(package: ContentPackage, timing: dict[str, Any]) -> list[dict[str, object]]:
    """Derive chapters solely from the authoritative persisted narration timeline."""
    by_section: dict[str, float] = {}
    duration = float(timing.get("final_duration_seconds", 0))
    for phrase in timing.get("phrases", []):
        section_id = phrase.get("section_id")
        start = phrase.get("start_seconds")
        if not isinstance(section_id, str) or not isinstance(start, (int, float)) or start < 0 or start >= duration:
            raise ProviderValidationError("timing map contains an invalid chapter timestamp")
        by_section.setdefault(section_id, float(start))
    chapters: list[dict[str, object]] = []
    for chapter in package.metadata.chapters:
        if chapter.section_id not in by_section:
            return []
        timestamp = by_section[chapter.section_id]
        if chapters and timestamp <= float(chapters[-1]["start_seconds"]):
            raise ProviderValidationError("chapter timestamps must increase")
        chapters.append({"section_id": chapter.section_id, "label": _clean(chapter.label), "start_seconds": timestamp, "timestamp": _format_timestamp(timestamp)})
    return chapters


def _format_timestamp(seconds: float) -> str:
    whole = int(seconds)
    return f"{whole // 3600}:{whole % 3600 // 60:02d}:{whole % 60:02d}" if whole >= 3600 else f"{whole // 60}:{whole % 60:02d}"


def render_thumbnail(output: Path, *, thumbnail_identity: str, title: str, width: int, height: int) -> None:
    """Write a deterministic valid RGB PNG with a bounded title overlay."""
    digest = bytes.fromhex(thumbnail_identity)
    pixels = bytearray(bytes((digest[index % len(digest)] for index in range(width * height * 3))))
    # A small built-in bitmap face avoids machine-specific fonts and dependencies.
    glyphs = {"A":"01110100011000111111000110001","B":"111101000111110100011000111110","C":"011111000010000100001000001111","D":"111101000110001100011000111110","E":"111111000011110100001000011111","F":"111111000011110100001000010000","G":"011111000010000101111000101111","H":"100011000111111100011000110001","I":"111110010000100001000010011111","J":"001110001000010000101001001100","K":"100011001011100100101001010001","L":"100001000010000100001000011111","M":"100011101110101100011000110001","N":"100011100110101100111000110001","O":"011101000110001100011000101110","P":"111101000110001111101000010000","Q":"011101000110001100011010101101","R":"111101000110001111101001010001","S":"011111000001110000011000111110","T":"111110010000100001000010000100","U":"100011000110001100011000101110","V":"100011000110001100010101000100","W":"100011000110001101011101110001","X":"100011000101010001000101010001","Y":"100011000101010001000010000100","Z":"111110000100010001000100011111","0":"011101000110011101011100101110","1":"001000110000100001000010001110","2":"011101000100010001000100011111","3":"111100000100110000011000111110","4":"000100011001010111110001000010","5":"111111000011110000011000111110","6":"011111000011110100011000101110","7":"111110000100010001000100001000","8":"011101000101110100011000101110","9":"011101000110001011110000101110","?":"011101000100010001000000000100"," ":"000000000000000000000000000000"}
    scale = max(2, min(width // 100, height // 28))
    text = title.upper()[: min(36, max(1, width // (6 * scale)))]
    text_width = len(text) * 6 * scale
    origin_x, origin_y = max(0, (width - text_width) // 2), max(0, height - 9 * scale)
    for index, character in enumerate(text):
        glyph = glyphs.get(character, glyphs["?"])
        for row in range(5):
            for column in range(5):
                if glyph[row * 5 + column] == "1":
                    for y in range(origin_y + row * scale, min(height, origin_y + (row + 1) * scale)):
                        for x in range(origin_x + (index * 6 + column) * scale, min(width, origin_x + (index * 6 + column + 1) * scale)):
                            offset = (y * width + x) * 3
                            pixels[offset:offset + 3] = b"\xff\xff\xff"
    raw = b"".join(bytes([0]) + pixels[row * width * 3:(row + 1) * width * 3] for row in range(height))
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def validate_thumbnail(path: Path, config: PublicationPreparationConfig) -> dict[str, object]:
    """Validate exactly the portable PNG format emitted by the M12 renderer."""
    if not path.is_file() or path.stat().st_size == 0:
        raise ProviderValidationError("thumbnail output is missing or empty")
    if path.stat().st_size > config.thumbnail_max_bytes:
        raise ProviderValidationError("thumbnail exceeds configured size")
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ProviderValidationError("thumbnail is not a supported PNG")
    width, height = struct.unpack(">II", data[16:24])
    if (width, height) != (config.thumbnail_width, config.thumbnail_height):
        raise ProviderValidationError("thumbnail dimensions do not match configuration")
    return {"format": "png", "width": width, "height": height, "file_size_bytes": len(data)}
