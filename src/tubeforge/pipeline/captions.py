"""Deterministic phrase-level SRT and WebVTT writing."""

from __future__ import annotations

import html
import textwrap
from dataclasses import dataclass

from tubeforge.pipeline.narration import NarrationPhrase


@dataclass(frozen=True, slots=True)
class TimedPhrase:
    phrase: NarrationPhrase
    start_seconds: float
    end_seconds: float


def timed_phrases(phrases: tuple[NarrationPhrase, ...], durations: tuple[float, ...], pause_seconds: float) -> tuple[TimedPhrase, ...]:
    if len(phrases) != len(durations):
        raise ValueError("phrase and duration counts differ")
    cursor = 0.0; output: list[TimedPhrase] = []
    for phrase, duration in zip(phrases, durations, strict=True):
        if duration <= 0:
            raise ValueError("caption phrase durations must be positive")
        end = cursor + duration
        output.append(TimedPhrase(phrase, cursor, end))
        cursor = end + pause_seconds
    return tuple(output)


def _timestamp(seconds: float, separator: str) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds_part:02}{separator}{milliseconds:03}"


def _cue_text(value: str, line_length: int, *, vtt: bool) -> str:
    text = " ".join(value.split())
    if not text:
        raise ValueError("caption text must not be empty")
    if vtt:
        text = html.escape(text, quote=False)
    else:
        text = text.replace("-->", "→")
    return "\n".join(textwrap.wrap(text, width=line_length, break_long_words=False, break_on_hyphens=False) or [text])


def render_srt(cues: tuple[TimedPhrase, ...], line_length: int = 42) -> str:
    rows: list[str] = []
    previous = 0.0
    for index, cue in enumerate(cues, 1):
        if cue.start_seconds < previous or cue.end_seconds <= cue.start_seconds:
            raise ValueError("caption timestamps must increase without overlap")
        rows.extend((str(index), f"{_timestamp(cue.start_seconds, ',')} --> {_timestamp(cue.end_seconds, ',')}", _cue_text(cue.phrase.text, line_length, vtt=False), ""))
        previous = cue.end_seconds
    return "\n".join(rows)


def render_vtt(cues: tuple[TimedPhrase, ...], line_length: int = 42) -> str:
    rows = ["WEBVTT", ""]
    previous = 0.0
    for cue in cues:
        if cue.start_seconds < previous or cue.end_seconds <= cue.start_seconds:
            raise ValueError("caption timestamps must increase without overlap")
        rows.extend((f"{_timestamp(cue.start_seconds, '.')} --> {_timestamp(cue.end_seconds, '.')}", _cue_text(cue.phrase.text, line_length, vtt=True), ""))
        previous = cue.end_seconds
    return "\n".join(rows)
