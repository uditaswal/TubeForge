"""Deterministic audio-energy highlight selection inspired by stream-clipper."""

from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Highlight:
    start_seconds: float
    end_seconds: float
    score: float
    evidence: dict[str, float]


def analyze_wav(path: Path, *, window_seconds: float, duration_seconds: float, min_duration: float, max_duration: float, padding: float, count: int) -> list[Highlight]:
    """Rank non-overlapping high-energy regions; always deterministic."""
    with wave.open(str(path), "rb") as source:
        rate, width, channels = source.getframerate(), source.getsampwidth(), source.getnchannels()
        frames_per_window = max(1, round(rate * window_seconds))
        values: list[float] = []
        while raw := source.readframes(frames_per_window):
            values.append(_rms(raw, width=width, channels=channels))
    if not values:
        return []
    ordered = sorted(values)
    baseline = ordered[max(0, int(len(ordered) * .5) - 1)]
    peak = max(values)
    # Consecutive energetic windows become a candidate. Low-contrast audio
    # still produces the strongest interval, avoiding a mysterious empty job.
    threshold = baseline + (peak - baseline) * .45
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(values):
        if value >= threshold:
            start = index if start is None else start
        elif start is not None:
            runs.append((start, index)); start = None
    if start is not None: runs.append((start, len(values)))
    if not runs:
        index = values.index(peak); runs = [(index, index + 1)]
    candidates: list[Highlight] = []
    for start, end in runs:
        center = ((start + end) / 2) * window_seconds
        length = min(max_duration, max(min_duration, (end - start) * window_seconds + padding * 2))
        clip_start = max(0.0, min(duration_seconds - length, center - length / 2))
        clip_end = min(duration_seconds, clip_start + length)
        energy = sum(values[start:end]) / max(1, end - start)
        candidates.append(Highlight(round(clip_start, 3), round(clip_end, 3), round(energy / max(peak, 1.0), 6), {"mean_rms": round(energy, 3), "threshold_rms": round(threshold, 3)}))
    selected: list[Highlight] = []
    for candidate in sorted(candidates, key=lambda item: (-item.score, item.start_seconds)):
        if all(candidate.end_seconds <= prior.start_seconds or candidate.start_seconds >= prior.end_seconds for prior in selected):
            selected.append(candidate)
        if len(selected) >= count: break
    return sorted(selected, key=lambda item: item.start_seconds)


def _rms(raw: bytes, *, width: int, channels: int) -> float:
    """Portable PCM RMS without ``audioop`` (removed in Python 3.13)."""
    if width != 2:
        raise ValueError("highlight analysis currently requires 16-bit PCM WAV")
    samples = struct.unpack("<" + "h" * (len(raw) // 2), raw)
    if channels > 1:
        samples = tuple(sum(samples[index:index + channels]) / channels for index in range(0, len(samples), channels))
    return math.sqrt(sum(sample * sample for sample in samples) / max(1, len(samples)))
