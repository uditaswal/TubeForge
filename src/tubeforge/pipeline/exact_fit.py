"""Fit an exact operator script to the video format without rewording it.

Exact mode keeps the operator's words, so a script that does not fit must be adapted around its wording, not through it:

1. Scenes are re-cut to the 8-15 spoken words the layout and voice grouping need: long scenes are split at sentence ends,
   then at clause breaks (a comma, "and", "but", "so", ...), short ones are joined to a neighbour. No word changes.
2. The video length follows the script when the requested length does not fit it (30 to 90 seconds).
3. Only when the script is longer than the longest video allows, whole low-value sentences are dropped (never the opening
   or the closing one; sentences with figures and names are kept longest). Every dropped sentence is reported verbatim.

The returned notes say what was done so nothing is changed silently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from tubeforge.pipeline.script_fit import SECTION_MAX_WORDS, SECTION_MIN_WORDS, spoken_words, split_sections
from tubeforge.providers.content.prompts import reference_word_budget

MIN_SECONDS, MAX_SECONDS = 30, 90
_SENTENCE = re.compile(r"(?<=[.!?…])\s+")
_CLAUSE = re.compile(r"(?<=[,;:])\s+|\s+(?=(?:and|but|so|because|though|which|then|while|instead)\b)", re.I)


@dataclass(frozen=True)
class ExactFit:
    text: str
    length_s: int
    notes: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.notes)


def _words(text: str) -> int:
    return spoken_words(text)


def _split_long(text: str) -> list[str]:
    """Split one over-long scene into parts of 8-15 words at the clause break nearest the middle; hard-split as a last resort."""
    if _words(text) <= SECTION_MAX_WORDS:
        return [text]
    tokens = text.split()
    candidates = []
    for match in _CLAUSE.finditer(text):
        before, after = text[:match.start()].strip(), text[match.end():].strip()
        if before and after and _words(before) >= SECTION_MIN_WORDS and _words(after) >= SECTION_MIN_WORDS:
            candidates.append((abs(_words(before) - _words(after)), before, after))
    if candidates:
        _, before, after = min(candidates)
    else:
        middle = len(tokens) // 2
        before, after = " ".join(tokens[:middle]), " ".join(tokens[middle:])
    return _split_long(before) + _split_long(after)


def rechunk(blocks: list[str]) -> list[str]:
    """Scenes of 8-15 words, in order, using only the operator's own words."""
    scenes: list[str] = []
    for block in blocks:
        if SECTION_MIN_WORDS <= _words(block) <= SECTION_MAX_WORDS:
            scenes.append(block)                   # already a good scene: keep the operator's own break
            continue
        pending = ""
        for sentence in (s.strip() for s in _SENTENCE.split(block) if s.strip()):
            for part in _split_long(sentence):
                joined = f"{pending} {part}".strip()
                if pending and _words(joined) > SECTION_MAX_WORDS:
                    scenes.append(pending)
                    pending = part
                else:
                    pending = joined
                if _words(pending) >= SECTION_MIN_WORDS and _words(pending) >= 11:
                    scenes.append(pending)
                    pending = ""
        if pending:
            scenes.append(pending)
    merged: list[str] = []                         # a scene still under 8 words joins its neighbour when the pair fits
    for scene in scenes:
        if merged and (_words(scene) < SECTION_MIN_WORDS or _words(merged[-1]) < SECTION_MIN_WORDS) \
                and _words(merged[-1]) + _words(scene) <= SECTION_MAX_WORDS:
            merged[-1] = f"{merged[-1]} {scene}"
        else:
            merged.append(scene)
    return merged


def _value(sentence: str) -> int:
    """Higher means keep longer: figures and names carry the facts."""
    figures = len(re.findall(r"\b\d[\d,.]*\b", sentence)) + len(re.findall(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|hundred|thousand|million|percent|half)\b", sentence, re.I))
    names = len(re.findall(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-z]+", sentence))
    return 3 * figures + 2 * names + min(_words(sentence), 15) // 5


def _trim(blocks: list[str], word_limit: int) -> tuple[list[str], list[str]]:
    sentences: list[tuple[int, str]] = []          # (block index, sentence)
    for index, block in enumerate(blocks):
        sentences += [(index, s.strip()) for s in _SENTENCE.split(block) if s.strip()]
    removed: list[str] = []
    while sum(_words(s) for _, s in sentences) > word_limit and len(sentences) > 2:
        order = range(1, len(sentences) - 1)       # never the opening or the closing sentence
        victim = min(order, key=lambda i: (_value(sentences[i][1]), -i))
        removed.append(sentences.pop(victim)[1])
    grouped: dict[int, list[str]] = {}
    for index, sentence in sentences:
        grouped.setdefault(index, []).append(sentence)
    return [" ".join(parts) for _, parts in sorted(grouped.items())], removed


def fit_exact_script(script: str, length_s: int) -> ExactFit:
    """Return the script re-cut and length-matched, plus human-readable notes of everything that was adapted."""
    notes: list[str] = []
    original_blocks = split_sections(script)
    blocks = original_blocks
    longest = reference_word_budget(MAX_SECONDS)
    if sum(_words(b) for b in blocks) > longest["max"]:
        blocks, removed = _trim(blocks, longest["aim_high"])
        notes.append(f"Too long for a {MAX_SECONDS} second video: dropped {len(removed)} lower-value sentence(s) without rewording the rest: "
                     + " | ".join(f"\"{s}\"" for s in removed))
    scenes = rechunk(blocks)
    if scenes != blocks:
        notes.append(f"Re-cut into {len(scenes)} scenes of {SECTION_MIN_WORDS}-{SECTION_MAX_WORDS} words (was {len(original_blocks)} blocks); no words changed.")
    total = sum(_words(s) for s in scenes)
    chosen = max(MIN_SECONDS, min(MAX_SECONDS, length_s))
    budget = reference_word_budget(chosen)
    if not budget["floor"] <= total <= budget["max"]:
        chosen = max(MIN_SECONDS, min(MAX_SECONDS, round(total / 2.7)))
        while chosen < MAX_SECONDS and total > reference_word_budget(chosen)["max"]:
            chosen += 1
    if chosen != length_s:
        notes.append(f"Video length set to {chosen} seconds to fit the script ({total} words; you asked for {length_s}).")
    return ExactFit("\n\n".join(scenes), chosen, tuple(notes))
