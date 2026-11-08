"""Versioned, display-preserving speech preparation for reviewed Shorts copy."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

_WORD = re.compile(r"[^\W_]+(?:[’'-][^\W_]+)*", re.UNICODE)
_DECIMAL = re.compile(r"(?<=\d)[.,](?=\d)")
_CORE = re.compile(r"^([^\w$]*)(.*?)([^\w%]*?)$", re.UNICODE)
# Letter names the voice reads reliably (bare capitals such as "A P I" are often swallowed or mis-said).
# Measured with Kokoro + Whisper (1 Nov 2026): "ay" is spoken as "eye" ("ay pee eye" -> "IPI") and bare "A P I" is swallowed
# ("PI"); "eh" is recognised as the letter A in API, AI, AWS, IAM, NAT. Every other letter name below was recognised as spelled.
_LETTER_NAMES = {"A": "eh", "B": "bee", "C": "see", "D": "dee", "E": "ee", "F": "eff", "G": "jee", "H": "aitch",
                 "I": "eye", "J": "jay", "K": "kay", "L": "el", "M": "em", "N": "en", "O": "oh", "P": "pee",
                 "Q": "cue", "R": "ar", "S": "ess", "T": "tee", "U": "you", "V": "vee", "W": "double-you",
                 "X": "ex", "Y": "why", "Z": "zee"}
# All-caps words people say as words, not letter by letter.
_SPOKEN_AS_WORDS = {"NASA", "NATO", "LASER", "SCUBA", "RAM", "ROM", "PIN", "OPEC", "UNESCO", "FIFA", "ASCII", "NOT", "AND",
                    "THE", "FOR", "ALL", "NEW", "NOW", "YES", "BUT", "ARE", "WAS", "ONE", "TWO", "OK"}
# Technical words the voice gets wrong; lower-case keys, applied beneath any configured lexicon.
DEFAULT_LEXICON = {"readme": "read me", "json": "jason", "yaml": "yammel", "gui": "gooey", "todo": "to do", "fixme": "fix me",
                   "jndi": "jay en dee eye", "ldap": "el dap", "log4j": "log four jay", "nginx": "engine ex",
                   "kubectl": "cube control", "sudo": "pseudo", "sql": "sequel", "iot": "eye oh tee", "oauth": "oh auth"}
VERSION = "spoken-v1"
RULES_REVISION = 2  # bumped when acronym rules change so cached narration is re-synthesised
_VOWELS = set("AEIOU")


def _reads_as_word(core: str) -> bool:
    """Five- or six-letter capitals with a pronounceable shape (README, STDOUT-like clusters excluded) are words, not initialisms."""
    letters = core.rstrip("s") if core.endswith("s") and core[:-1].isupper() else core
    if not 5 <= len(letters) <= 6 or sum(c in _VOWELS for c in letters) < 2:
        return False
    return not re.search(r"[^AEIOU]{3}", letters)


@dataclass(frozen=True)
class SpokenScene:
    text: str
    alignment_text: str
    display_spans: tuple[tuple[int, int], ...]
    applied: tuple[dict[str, str | int], ...]
    tokens: tuple[str, ...] = ()  # spoken form of each display word, in order (for cue segmentation)


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


def _year(number: int) -> str:
    if number % 100 == 0 and number % 1000:
        return _integer(number // 100) + " hundred"
    if 2000 <= number <= 2009:
        return "two thousand" + (" " + _integer(number % 10) if number % 10 else "")
    return _integer(number // 100) + " " + (_integer(number % 100) if number % 100 >= 10 else
                                           ("oh " + _integer(number % 100) if number % 100 else "hundred"))


def _spell(core: str) -> str:
    plural = len(core) > 2 and core.endswith("s") and core[:-1].isupper()
    letters = core[:-1] if plural else core
    names = [_LETTER_NAMES[c] for c in letters]
    return " ".join(names) + ("s" if plural else "")


def _replacement(core: str, lexicon: dict[str, str]) -> tuple[str, str | None]:
    if core.casefold() in lexicon:
        return lexicon[core.casefold()], "lexicon"
    if core.casefold() in DEFAULT_LEXICON:
        return DEFAULT_LEXICON[core.casefold()], "lexicon"
    if re.fullmatch(r"[A-Z]{2,6}s?", core) and core.rstrip("s") not in _SPOKEN_AS_WORDS and core not in _SPOKEN_AS_WORDS and not _reads_as_word(core):
        return _spell(core), "acronym"
    if re.fullmatch(r"v?\d{1,3}(?:\.\d{1,3}){1,3}", core):
        parts = core.lstrip("v").split(".")
        return ("version " if core.startswith("v") else "") + " point ".join(
            _integer(int(part)) if (part == "0" or not part.startswith("0")) else " ".join(_integer(int(c)) for c in part)
            for part in parts), "version"
    if re.fullmatch(r"(?:19|20)\d\d", core):
        return _year(int(core)), "year"
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


def profile_hash(*, profile: str, lexicon: dict[str, str], group_size: int, voice_processing: str,
                 delivery: str = "off") -> str:
    material = {"version": VERSION, "rules": RULES_REVISION, "profile": profile, "lexicon": validated_lexicon(lexicon),
                "group_size": group_size, "voice_processing": voice_processing}
    if delivery != "off":
        material["delivery"] = delivery  # absent when off, so existing profile hashes are unchanged
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
    return SpokenScene(text, _DECIMAL.sub("’", text), tuple(spans), tuple(applied), tuple(spoken))


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
