"""Versioned, display-preserving speech preparation for reviewed Shorts copy."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

_WORD = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
_DECIMAL = re.compile(r"(?<=\d)[.,](?=\d)")
_CORE = re.compile(r"^([^\w$]*)(.*?)([^\w%]*?)$", re.UNICODE)
_ACRONYMS = {"AI", "API", "CPU", "GPU", "PHP"}
VERSION = "spoken-v1"


@dataclass(frozen=True)
class SpokenScene:
    text: str
    alignment_text: str
    display_spans: tuple[tuple[int, int], ...]
    applied: tuple[dict[str, str | int], ...]


def _integer(number: int) -> str:
    small = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
             "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen",
             "eighteen", "nineteen")
    tens = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
    if number < 20:
        return small[number]
    if number < 100:
        return tens[number // 10] + (" " + small[number % 10] if number % 10 else "")
    return small[number // 100] + " hundred" + (" " + _integer(number % 100) if number % 100 else "")


def _replacement(core: str, lexicon: dict[str, str]) -> tuple[str, str | None]:
    if core.casefold() in lexicon:
        return lexicon[core.casefold()], "lexicon"
    if core in _ACRONYMS:
        return " ".join(core), "acronym"
    if re.fullmatch(r"(?:100|[1-9]?\d)%", core):
        return _integer(int(core[:-1])) + " percent", "percent"
    if re.fullmatch(r"\$(?:[1-9]\d{0,2}|0)", core):
        amount = int(core[1:])
        return _integer(amount) + (" dollar" if amount == 1 else " dollars"), "currency"
    if re.fullmatch(r"(?:[1-9]\d{0,2}|0)", core):
        return _integer(int(core)), "integer"
    return core, None


def validated_lexicon(lexicon: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in lexicon.items():
        normalized = key.casefold()
        if (not _WORD.fullmatch(key) or not value.strip() or "\n" in value or
                len(value) > 100 or normalized in result or not all(_WORD.fullmatch(part) for part in value.split())):
            raise ValueError("pronunciation lexicon requires unique single display tokens and nonempty spoken words")
        result[normalized] = " ".join(value.split())
    return result


def profile_hash(*, profile: str, lexicon: dict[str, str], group_size: int, voice_processing: str) -> str:
    material = {"version": VERSION, "profile": profile, "lexicon": validated_lexicon(lexicon),
                "group_size": group_size, "voice_processing": voice_processing}
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def prepare_spoken(display: str, *, profile: str, lexicon: dict[str, str]) -> SpokenScene:
    if profile not in {"off", VERSION}:
        raise ValueError("unsupported spoken profile")
    terms = validated_lexicon(lexicon)
    spoken: list[str] = []
    spans: list[tuple[int, int]] = []
    applied: list[dict[str, str | int]] = []
    count = 0
    for index, token in enumerate(display.split()):
        if profile == "off":
            replacement, reason = token, None
        else:
            match = _CORE.fullmatch(token)
            if match is None or not match.group(2):
                raise ValueError("narration contains an unmappable display token")
            prefix, core, suffix = match.groups()
            result, reason = _replacement(core, terms)
            replacement = prefix + result + suffix
        aligned = _DECIMAL.sub("’", replacement)
        size = len(_WORD.findall(aligned))
        if not size:
            raise ValueError("spoken replacement would remove a reviewed word")
        spans.append((count, count + size))
        count += size
        spoken.append(replacement)
        if reason:
            applied.append({"display_index": index, "display": token, "spoken": replacement, "rule": reason})
    text = " ".join(spoken)
    return SpokenScene(text, _DECIMAL.sub("’", text), tuple(spans), tuple(applied))


def collapse_alignment(measured, spans: tuple[tuple[int, int], ...]):
    """One visual-caption interval per original display word, with full spoken coverage."""
    if not spans or spans[0][0] != 0 or spans[-1][1] != len(measured):
        raise ValueError("spoken alignment does not cover reviewed display words")
    result = []
    previous = 0
    for first, end in spans:
        if first != previous or end <= first:
            raise ValueError("spoken/display mapping has a gap or overlap")
        result.append((measured[first].start_seconds, measured[end - 1].end_seconds))
        previous = end
    return tuple(result)
