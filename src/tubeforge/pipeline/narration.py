"""Pure, deterministic approved-script narration segmentation."""

from __future__ import annotations

import hashlib
import re
import unicodedata

from pydantic import Field

from tubeforge.domain.contracts import ContentPackage, DomainModel


class NarrationPhrase(DomainModel):
    """One stable phrase with its source section and claim relationships."""

    phrase_id: str = Field(pattern=r"^phrase-[a-f0-9]{16}$")
    section_id: str
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    claim_ids: tuple[str, ...] = ()


_BOUNDARY = re.compile(r"(?<=[.!?])(?=\s|$)")
_ABBREVIATION = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc|e\.g|i\.e|U\.S|U\.K)\.$", re.I)


def normalize_narration_text(text: str) -> str:
    """NFC-normalize and collapse whitespace without changing meaningful punctuation."""
    return " ".join(unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n").split())


def split_phrases(text: str) -> tuple[str, ...]:
    """Split sentences predictably, avoiding ordinary abbreviations and decimals."""
    normalized = normalize_narration_text(text)
    if not normalized:
        return ()
    phrases: list[str] = []
    start = 0
    for match in _BOUNDARY.finditer(normalized):
        candidate = normalized[start : match.start() + 1].strip()
        if _ABBREVIATION.search(candidate) or re.search(r"\d\.\d$", candidate):
            continue
        if candidate:
            phrases.append(candidate)
        start = match.end()
    tail = normalized[start:].strip()
    if tail:
        phrases.append(tail)
    return tuple(phrases)


def segment_content_package(package: ContentPackage) -> tuple[NarrationPhrase, ...]:
    """Return ordered, stable phrases; identical text in a section retains its ID."""
    result: list[NarrationPhrase] = []
    ordinal = 0
    for section in package.script_sections:
        occurrences: dict[str, int] = {}
        for text in split_phrases(section.narration):
            occurrences[text] = occurrences.get(text, 0) + 1
            material = f"m7|{section.section_id}|{text}|{occurrences[text]}".encode("utf-8")
            result.append(NarrationPhrase(
                phrase_id=f"phrase-{hashlib.sha256(material).hexdigest()[:16]}",
                section_id=section.section_id,
                ordinal=ordinal,
                text=text,
                claim_ids=section.claim_ids,
            ))
            ordinal += 1
    return tuple(result)
