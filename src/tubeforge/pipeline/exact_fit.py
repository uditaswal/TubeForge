"""Fit an exact operator script to the video format without rewording it.

Exact mode keeps the operator's words, so a script that does not fit must be adapted around its wording, not through it:

1. Scenes are re-cut to the 8-15 spoken words the layout and voice grouping need: long scenes are split at sentence ends,
   then at clause breaks (a comma, "and", "but", "so", ...), short ones are joined to a neighbour. No word changes.
2. The video length follows the script when the requested length does not fit it (30 to 120 seconds).
3. Only when the script is longer than the longest video allows, whole low-value sentences are dropped (never the opening
   or the closing one; sentences with figures and names are kept longest). Every dropped sentence is reported verbatim.

The returned notes say what was done so nothing is changed silently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from tubeforge.pipeline.script_fit import SECTION_MAX_WORDS, SECTION_MIN_WORDS, spoken_words, split_sections
from tubeforge.providers.content.prompts import reference_word_budget

MIN_SECONDS, MAX_SECONDS = 30, 120
_TERMINAL = re.compile(r"[.!?…][\"')\]]*$")
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


_CONJUNCTIONS = {"and", "but", "so", "because", "though", "which", "then", "while", "instead", "or", "where", "when", "that"}


def _cut_cost(token: str, following: str, block_end: bool) -> float:
    """How bad it is to start a new scene right after ``token``: the operator's own break and sentence ends are free."""
    if block_end:
        return 0.0
    if token.endswith((".", "!", "?", "…", ".\"", "?\"", "!\"")):
        return .5
    if token.endswith((",", ";", ":", "—")):
        return 3.0                                 # inside a sentence: a full stop is added there
    if following.strip(",;:").lower() in _CONJUNCTIONS:
        return 3.2
    return 8.0


def _segment(blocks: list[str]) -> tuple[list[str], int]:
    """Scenes of 8-15 spoken words, in order, using only the operator's own words.

    The whole script is segmented at once (dynamic programming), because a short sentence between two long ones
    cannot be kept alone or joined to either neighbour; the cheapest cut points win: the operator's own breaks and
    sentence ends first, then clause breaks, and a mid-clause cut only when nothing else fits."""
    tokens: list[str] = []
    block_end: list[bool] = []                     # block_end[k]: a blank-line break follows token k
    for block in blocks:
        parts = block.split()
        tokens += parts
        block_end += [False] * (len(parts) - 1) + [True]
    n = len(tokens)
    if n == 0:
        return [], 0
    infinity = float("inf")
    best = [infinity] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0
    for end in range(1, n + 1):
        for start in range(end - 1, max(-1, end - 40), -1):
            count = _words(" ".join(tokens[start:end]))
            if count > SECTION_MAX_WORDS:
                break
            if count < SECTION_MIN_WORDS or best[start] == infinity:
                continue
            cut = 0.0 if start == 0 else _cut_cost(tokens[start - 1], tokens[start], block_end[start - 1])
            cost = best[start] + cut + abs(count - 11) * .05
            if cost < best[end]:
                best[end], back[end] = cost, start
    if best[n] == infinity:                        # fewer than 8 spoken words in total: nothing to re-cut
        return [" ".join(tokens)], 0
    spans: list[tuple[int, int]] = []
    end = n
    while end > 0:
        spans.append((back[end], end))
        end = back[end]
    spans.reverse()
    scenes, adjusted = [], 0
    for index, (start, stop) in enumerate(spans):
        parts = tokens[start:stop]
        if index < len(spans) - 1 and not _TERMINAL.search(parts[-1]) and not block_end[stop - 1]:
            parts[-1] = parts[-1].rstrip(",;:—") + "."     # the scene validator needs sentence punctuation where a scene ends
            adjusted += 1
        scenes.append(" ".join(parts))
    return scenes, adjusted


def rechunk(blocks: list[str]) -> list[str]:
    return _segment(blocks)[0]




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
    scenes, adjusted = _segment(blocks)
    if scenes != blocks:
        notes.append(f"Re-cut into {len(scenes)} scenes of {SECTION_MIN_WORDS}-{SECTION_MAX_WORDS} words (was {len(original_blocks)} blocks); no words changed.")
    if adjusted:
        notes.append(f"{adjusted} scene break(s) fall inside a sentence; a full stop was added there because every scene must end in sentence punctuation (punctuation only, no words).")
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
