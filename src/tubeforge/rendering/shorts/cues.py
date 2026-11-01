"""Inline delivery cues for Shorts narration: pauses, breaths, emphasis and whispers.

The script author may annotate a scene's ``vo`` with a small, fixed tag set::

    [pause 0.4]            silence before the next word (0.15-0.9 s; bare ``[pause]`` = 0.35 s)
    [breath]               an audible breath before the next word
    *word*  /  *two words* stressed delivery of 1-2 words
    [whisper]...[/whisper] hushed delivery of 2-8 consecutive words

``parse`` removes the tags and returns the *clean* narration (what is displayed, captioned,
counted and aligned) plus structured cues anchored to clean-word indices. Everything
downstream of the scene schema therefore keeps seeing plain narration; only the speech
synthesiser reads the cues. A scene without tags parses to itself with no cues.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PAUSE_SECONDS = 0.35
MIN_PAUSE_SECONDS, MAX_PAUSE_SECONDS = 0.15, 0.9
MAX_CUES_PER_SCENE = 4
MAX_EMPHASIS_WORDS, MAX_EMPHASIS_PER_SCENE = 2, 2
MIN_WHISPER_WORDS, MAX_WHISPER_WORDS = 2, 8

_TAG = re.compile(r"\[(pause)(?:\s+([0-9]*\.?[0-9]+))?\]|\[(breath)\]|\[(whisper)\]|\[(/whisper)\]", re.I)
_MARK_PAUSE, _MARK_BREATH, _MARK_OPEN, _MARK_CLOSE = "", "", "", ""
_PAUSE_TOKEN = re.compile(_MARK_PAUSE + r"([0-9.]*)" + _MARK_PAUSE)
_SENTINELS = (_MARK_PAUSE, _MARK_BREATH, _MARK_OPEN, _MARK_CLOSE)
_ANY_MARK = re.compile(r"^(?:\*|" + _MARK_PAUSE + r"[0-9.]*" + _MARK_PAUSE + "|" + _MARK_BREATH + "|" +
                       _MARK_OPEN + "|" + _MARK_CLOSE + ")")


_MARKS = ("(?:\\*|" + _MARK_PAUSE + "[0-9.]*" + _MARK_PAUSE + "|" + _MARK_BREATH + "|" + _MARK_OPEN + "|" +
          _MARK_CLOSE + ")")
# "*broke*." / "logs[/whisper]," -> markers move behind trailing punctuation so the word keeps it.
_PUNCT_AFTER_MARK = re.compile("((?:" + _MARKS + ")+)([.,;:!?\u2026)\"'\u2019\u201d]+)$")


class Cue(BaseModel):
    """One delivery instruction anchored to clean-narration word indices."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["pause", "breath", "emphasis", "whisper"]
    at: int = Field(ge=0, le=60)                 # pause/breath: before this word; span cues: first word
    end: int | None = Field(default=None, ge=1, le=61)  # span cues: one past the last word
    seconds: float | None = Field(default=None, ge=0.03, le=MAX_PAUSE_SECONDS)  # script pauses are held to MIN_PAUSE_SECONDS in validate_cues; automatic gaps may be shorter

    @model_validator(mode="after")
    def shape(self):
        span = self.kind in {"emphasis", "whisper"}
        if span != (self.end is not None) or (span and self.end <= self.at):
            raise ValueError(f"{self.kind} cue has an invalid word range")
        if (self.kind == "pause") != (self.seconds is not None):
            raise ValueError("only pause cues carry a duration")
        return self


def _protect(text: str) -> str:
    """Swap spaced tags for single-token sentinels so whitespace splitting keeps them intact."""
    if any(mark in text for mark in _SENTINELS):
        raise ValueError("narration contains a reserved character")

    def swap(match: re.Match) -> str:
        if match.group(1):
            seconds = match.group(2)
            return f"{_MARK_PAUSE}{seconds if seconds is not None else DEFAULT_PAUSE_SECONDS}{_MARK_PAUSE}"
        if match.group(3):
            return _MARK_BREATH
        return _MARK_OPEN if match.group(4) else _MARK_CLOSE

    return _TAG.sub(swap, text)


def has_cues(text: str) -> bool:
    return bool(_TAG.search(text)) or "*" in text


def strip(text: str) -> str:
    """Clean narration only (raises ``ValueError`` on malformed tags)."""
    return parse(text)[0]


def parse(text: str) -> tuple[str, tuple[Cue, ...]]:
    """Split annotated narration into (clean text, cues). Malformed or excessive cues raise ``ValueError``."""
    if not has_cues(text):
        return text, ()
    tokens = _protect(text).split()
    words: list[str] = []
    cues: list[Cue] = []
    emphasis_open: int | None = None
    whisper_open: int | None = None

    def apply(mark: str, index: int, *, closing: bool) -> None:
        nonlocal emphasis_open, whisper_open
        if mark == "*":
            if emphasis_open is None:
                if closing:
                    raise ValueError("emphasis marker closes nothing")
                emphasis_open = index
            else:
                cues.append(Cue(kind="emphasis", at=emphasis_open, end=index))
                emphasis_open = None
        elif mark == _MARK_OPEN:
            if whisper_open is not None or closing:
                raise ValueError("[whisper] opened twice or in the wrong place")
            whisper_open = index
        elif mark == _MARK_CLOSE:
            if whisper_open is None:
                raise ValueError("[/whisper] without [whisper]")
            cues.append(Cue(kind="whisper", at=whisper_open, end=index))
            whisper_open = None
        elif mark == _MARK_BREATH:
            cues.append(Cue(kind="breath", at=index))
        else:
            seconds = float(_PAUSE_TOKEN.fullmatch(mark).group(1) or DEFAULT_PAUSE_SECONDS)
            cues.append(Cue(kind="pause", at=index, seconds=seconds))

    for token in tokens:
        token = _PUNCT_AFTER_MARK.sub(lambda m: m.group(2) + m.group(1), token)
        prefix: list[str] = []
        while True:
            found = _ANY_MARK.match(token)
            if not found:
                break
            prefix.append(found.group(0))
            token = token[found.end():]
        suffix: list[str] = []
        while token:
            tail = re.search(r"(?:\*|" + _MARK_PAUSE + r"[0-9.]*" + _MARK_PAUSE + "|" + _MARK_BREATH + "|" +
                             _MARK_OPEN + "|" + _MARK_CLOSE + ")$", token)
            if not tail:
                break
            suffix.insert(0, tail.group(0))
            token = token[:tail.start()]
        if any(mark in token for mark in ("*", *_SENTINELS)):
            raise ValueError("cue markers must sit at word edges")
        for mark in prefix:
            apply(mark, len(words), closing=False)
        if token:
            words.append(token)
            for mark in suffix:
                apply(mark, len(words), closing=True)
        else:
            for mark in suffix:
                apply(mark, len(words), closing=True)
    if emphasis_open is not None or whisper_open is not None:
        raise ValueError("unclosed emphasis or whisper cue")
    return " ".join(words), validate_cues(tuple(cues), len(words))


def validate_cues(cues: tuple[Cue, ...], word_count: int) -> tuple[Cue, ...]:
    """Drop edge pauses/breaths that cannot be heard, then enforce the per-scene delivery budget."""
    for cue in cues:
        if cue.kind == "pause" and not MIN_PAUSE_SECONDS <= cue.seconds <= MAX_PAUSE_SECONDS:
            raise ValueError(f"a pause lasts {MIN_PAUSE_SECONDS}-{MAX_PAUSE_SECONDS} seconds")
    kept = tuple(sorted((c for c in cues if c.kind not in {"pause", "breath"} or 0 < c.at < word_count),
                        key=lambda c: (c.at, c.kind)))
    if len(kept) > MAX_CUES_PER_SCENE:
        raise ValueError(f"a scene may carry at most {MAX_CUES_PER_SCENE} delivery cues")
    emphasis = [c for c in kept if c.kind == "emphasis"]
    whispers = [c for c in kept if c.kind == "whisper"]
    if len(emphasis) > MAX_EMPHASIS_PER_SCENE or len(whispers) > 1:
        raise ValueError("too many emphasis or whisper cues in one scene")
    for cue in emphasis:
        if cue.end > word_count or cue.end - cue.at > MAX_EMPHASIS_WORDS:
            raise ValueError(f"emphasis covers 1-{MAX_EMPHASIS_WORDS} words")
    for cue in whispers:
        if cue.end > word_count or not MIN_WHISPER_WORDS <= cue.end - cue.at <= MAX_WHISPER_WORDS:
            raise ValueError(f"whisper covers {MIN_WHISPER_WORDS}-{MAX_WHISPER_WORDS} words")
        if any(e.at < cue.end and cue.at < e.end for e in emphasis):
            raise ValueError("emphasis cannot overlap a whisper")
    if len({(c.kind, c.at) for c in kept if c.kind in {"pause", "breath"}}) != len(
            [c for c in kept if c.kind in {"pause", "breath"}]):
        raise ValueError("duplicate pause or breath at the same word")
    return kept
