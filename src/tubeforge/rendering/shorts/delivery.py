"""Turn delivery cues into audio: segment planning, procedural breaths, whisper and stress DSP.

Kokoro has no SSML, stress or whisper control, so cues are realised around it: speech is
synthesised in short segments and joined with real silence and a quiet procedural breath;
stressed words get a slower, louder render of their own; whispered spans are re-excited with
envelope-shaped noise. These are approximations of human delivery, deliberately modest, and
a scene without cues never goes through this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

import numpy as np

from .cues import Cue

BREATH_SECONDS = 0.30
BREATH_PEAK = 0.035            # about -29 dBFS: audible between words, never a distraction
EMPHASIS_GAIN_DB = 2.5
EMPHASIS_SPEED = 0.92          # relative to the voice's configured speed
EMPHASIS_LEAD_SECONDS = 0.05   # tiny lift-off before a stressed word when no explicit pause
WHISPER_GAIN_DB = -7.0
WHISPER_SPEED = 0.9
EDGE_FADE_SECONDS = 0.006


@dataclass(frozen=True)
class Segment:
    text: str
    style: str = "plain"          # plain | emphasis | whisper
    pause_before: float = 0.0
    breath_before: bool = False


ACRONYM_GAP_BEFORE, ACRONYM_GAP_AFTER = 0.08, 0.10
_PUNCTUATED = (",", ".", ";", ":", "!", "?", "\u2014", ")", "\u2026")


def spelling_gaps(applied: Sequence[dict], display_words: Sequence[str], terms: Sequence[str] = ()) -> tuple[Cue, ...]:
    """Short silences around the *listed* hard-to-hear replacements only (``terms``, case-insensitive).

    Splitting speech into pieces costs roughly 0.3 s per boundary whatever the gap, and most acronyms are heard
    fine without one, so gaps are opt-in per term. The list is data-driven: LDAP ("el dap") and Log4j were the words
    Whisper lost without a gap ("over LDAP" came back as "app"). A side that already has punctuation (``JNDI,``) keeps
    its natural pause and gets no extra gap. Anchors are display-word indices, like script cues.
    """
    wanted = {term.casefold() for term in terms}
    gaps: dict[int, float] = {}
    count = len(display_words)
    for row in applied:
        if row.get("rule") not in {"acronym", "lexicon"} or len(str(row.get("spoken", "")).split()) < 2:
            continue
        index = int(row["display_index"])
        if display_words[index].strip(".,;:!?\"'()").casefold() not in wanted:
            continue
        if ACRONYM_GAP_BEFORE and index > 0 and not display_words[index - 1].endswith(_PUNCTUATED):
            gaps[index] = max(gaps.get(index, 0.0), ACRONYM_GAP_BEFORE)
        if ACRONYM_GAP_AFTER and index + 1 < count and not display_words[index].endswith(_PUNCTUATED):
            gaps[index + 1] = max(gaps.get(index + 1, 0.0), ACRONYM_GAP_AFTER)
    return tuple(Cue(kind="pause", at=at, seconds=seconds) for at, seconds in sorted(gaps.items()))


def plan(tokens: Sequence[str], cues: Sequence[Cue]) -> list[Segment]:
    """Group spoken tokens into segments at every style change, pause and breath."""
    if not tokens:
        return []
    style = ["plain"] * len(tokens)
    for cue in cues:
        if cue.kind in {"emphasis", "whisper"}:
            for index in range(cue.at, min(cue.end, len(tokens))):
                style[index] = cue.kind
    pauses: dict[int, float] = {}
    breaths: set[int] = set()
    for cue in cues:
        if cue.kind == "pause":
            pauses[cue.at] = pauses.get(cue.at, 0.0) + cue.seconds
        elif cue.kind == "breath":
            breaths.add(cue.at)
    segments: list[Segment] = []
    current: list[str] = []
    meta = (0.0, False)
    for index, token in enumerate(tokens):
        boundary = index > 0 and (style[index] != style[index - 1] or index in pauses or index in breaths)
        if boundary:
            segments.append(Segment(" ".join(current), style[index - 1], *meta))
            current, meta = [], (0.0, False)
        if index in pauses or index in breaths:
            meta = (pauses.get(index, 0.0), index in breaths)
        current.append(token)
    segments.append(Segment(" ".join(current), style[-1], *meta))
    return segments


def _bandpass(signal: np.ndarray, rate: int, low: float, high: float) -> np.ndarray:
    spectrum = np.fft.rfft(signal)
    freqs = np.fft.rfftfreq(len(signal), 1 / rate)
    mask = np.clip((freqs - low) / 150.0, 0, 1) * np.clip((high - freqs) / 150.0, 0, 1)
    return np.fft.irfft(spectrum * mask, n=len(signal))


def _rms(signal: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(signal)))) if len(signal) else 0.0


def breath(rate: int) -> np.ndarray:
    """A soft inhale: band-limited noise with a slow rise and a quicker fall (deterministic)."""
    count = round(BREATH_SECONDS * rate)
    noise = _bandpass(np.random.default_rng(7).standard_normal(count), rate, 250, 3500)
    rise = round(.45 * count)
    envelope = np.concatenate([np.sin(np.linspace(0, np.pi / 2, rise)) ** 2,
                               np.cos(np.linspace(0, np.pi / 2, count - rise)) ** 2])
    noise = noise * envelope
    return (noise / max(float(np.max(np.abs(noise))), 1e-9) * BREATH_PEAK).astype(np.float32)


def emphasize(signal: np.ndarray) -> np.ndarray:
    boosted = signal * 10 ** (EMPHASIS_GAIN_DB / 20)
    return (np.tanh(boosted / .95) * .95).astype(np.float32)   # soft-limit, never clip


def whisper(signal: np.ndarray, rate: int) -> np.ndarray:
    """Re-excite the speech envelope with noise (no voicing) and keep consonant detail."""
    if not len(signal) or _rms(signal) < 1e-5:
        return signal
    frame = max(1, round(.012 * rate))
    envelope = np.sqrt(np.convolve(np.square(signal), np.ones(frame) / frame, mode="same"))
    noise = _bandpass(np.random.default_rng(11).standard_normal(len(signal)), rate, 700, 7500)
    noise = noise / max(_rms(noise), 1e-9) * envelope
    detail = _bandpass(signal, rate, 1200, 8000)
    out = .8 * noise + .35 * detail
    out *= _rms(signal) / max(_rms(out), 1e-9) * 10 ** (WHISPER_GAIN_DB / 20)
    return out.astype(np.float32)


def _faded(signal: np.ndarray, rate: int) -> np.ndarray:
    edge = min(len(signal) // 2, round(EDGE_FADE_SECONDS * rate))
    if edge > 1:
        signal = signal.copy()
        signal[:edge] *= np.linspace(0, 1, edge)
        signal[-edge:] *= np.linspace(1, 0, edge)
    return signal


def render(segments: Sequence[Segment], synth: Callable[[str, float], np.ndarray], rate: "int | Callable[[], int]", *,
           emphasis: bool = True) -> np.ndarray:
    """Synthesise and join segments. ``synth(text, speed_scale)`` returns trimmed mono float32 speech."""
    pieces: list[np.ndarray] = []
    for number, segment in enumerate(segments):
        if segment.style == "whisper":
            audio = synth(segment.text, WHISPER_SPEED)
            audio = whisper(audio, rate() if callable(rate) else rate)
        elif segment.style == "emphasis" and emphasis:
            audio = emphasize(synth(segment.text, EMPHASIS_SPEED))
        else:
            audio = synth(segment.text, 1.0)
        sample_rate = rate() if callable(rate) else rate
        if number:
            if segment.breath_before:
                pieces.append(np.zeros(round(.04 * sample_rate), dtype=np.float32))
                pieces.append(breath(sample_rate))
            gap = segment.pause_before
            if not gap and not segment.breath_before and segment.style == "emphasis" and emphasis:
                gap = EMPHASIS_LEAD_SECONDS
            if gap:
                pieces.append(np.zeros(round(gap * sample_rate), dtype=np.float32))
        pieces.append(_faded(np.asarray(audio, dtype=np.float32), sample_rate))
    return np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)
