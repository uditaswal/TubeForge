"""Deterministic phrase-level SRT and WebVTT writing."""

from __future__ import annotations

import html
import re
import textwrap
from dataclasses import dataclass

from tubeforge.pipeline.narration import NarrationPhrase
from tubeforge.pipeline.alignment import WordTiming


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


def render_highlighted_ass(
    words: tuple[WordTiming, ...],
    *,
    width: int,
    height: int,
    font_size: int,
    margin_vertical: int,
    margin_horizontal: int,
    words_per_cue: int = 3,
    phrases: tuple[TimedPhrase, ...] | None = None,
) -> str:
    """Render word-timed, safe-area portrait captions with active highlighting."""
    if not words:
        raise ValueError("highlighted captions require aligned words")
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        f"Style: Shorts,Arial,{font_size},&H00FFFFFF,&H0000D7FF,&H00101010,&H80000000,"
        f"1,0,0,0,100,100,0,0,1,6,2,2,{margin_horizontal},{margin_horizontal},{margin_vertical},1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )
    rows = [header]
    caption_words = _caption_words(words, phrases)
    for index, word in enumerate(caption_words):
        phrase_start = index
        while phrase_start and caption_words[phrase_start - 1].phrase_id == word.phrase_id:
            phrase_start -= 1
        group_start = phrase_start + ((index - phrase_start) // words_per_cue) * words_per_cue
        group = caption_words[group_start : group_start + words_per_cue]
        group = tuple(candidate for candidate in group if candidate.phrase_id == word.phrase_id)
        rendered = []
        for candidate in group:
            value = _ass_escape(candidate.word.upper())
            rendered.append(f"{{\\c&H0000D7FF&\\b1}}{value}{{\\rShorts}}" if candidate.ordinal == word.ordinal else value)
        lengths = [len(candidate.word) for candidate in group]
        if sum(lengths) + max(0, len(group) - 1) > 16 and len(rendered) > 1:
            choices = []
            for split_at in range(1, len(group)):
                first = sum(lengths[:split_at]) + split_at - 1
                second = sum(lengths[split_at:]) + len(group) - split_at - 1
                choices.append((max(first, second), abs(first - second), split_at))
            longest, _, split_at = min(choices)
            if longest > 18:
                raise ValueError("highlighted caption exceeds portrait line width")
            cue_text = " ".join(rendered[:split_at]) + r"\N" + " ".join(rendered[split_at:])
        else:
            if sum(lengths) + max(0, len(group) - 1) > 18:
                raise ValueError("highlighted caption exceeds portrait line width")
            cue_text = " ".join(rendered)
        rows.append(
            "Dialogue: 0,"
            f"{_ass_timestamp(word.start_seconds)},{_ass_timestamp(word.end_seconds)},"
            f"Shorts,,{margin_horizontal},{margin_horizontal},{margin_vertical},,{cue_text}\n"
        )
    return "".join(rows)


def _caption_words(words: tuple[WordTiming, ...], phrases: tuple[TimedPhrase, ...] | None) -> tuple[WordTiming, ...]:
    """Keep punctuation and CLI tokens intact while using the aligned word times."""
    if phrases is None:
        return words
    by_phrase: dict[str, list[WordTiming]] = {}
    for word in words:
        by_phrase.setdefault(word.phrase_id, []).append(word)
    output: list[WordTiming] = []
    for cue in phrases:
        aligned = by_phrase.pop(cue.phrase.phrase_id, None)
        if not aligned:
            raise ValueError("highlighted captions are missing phrase word timings")
        tokens = cue.phrase.text.split()
        expected = [match for token in tokens for match in re.findall(r"[^\W_]+(?:[’'-][^\W_]+)*", token, re.UNICODE)]
        if [value.casefold() for value in expected] != [word.word.casefold() for word in aligned]:
            raise ValueError("highlighted caption text differs from aligned narration")
        cursor = 0
        for token in tokens:
            count = len(re.findall(r"[^\W_]+(?:[’'-][^\W_]+)*", token, re.UNICODE))
            if count == 0:
                if not output or output[-1].phrase_id != cue.phrase.phrase_id:
                    raise ValueError("highlighted caption has isolated punctuation")
                prior = output[-1]
                output[-1] = WordTiming(prior.word + " " + token, prior.phrase_id, prior.section_id, prior.ordinal, prior.start_seconds, prior.end_seconds)
                continue
            span = aligned[cursor : cursor + count]
            output.append(WordTiming(token, cue.phrase.phrase_id, cue.phrase.section_id, span[0].ordinal, span[0].start_seconds, span[-1].end_seconds))
            cursor += count
    if by_phrase:
        raise ValueError("highlighted captions contain unreferenced word timings")
    return tuple(output)


def _ass_timestamp(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds_part, fraction = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{seconds_part:02}.{fraction:02}"


def _ass_escape(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
