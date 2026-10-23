"""Bounded, advisory signal checks for exact narration and encoded Shorts audio."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import soundfile as sf


WINDOW_SECONDS = 0.1
MAX_SECONDS = 120
MAX_WARNINGS = 100


def scan_samples(samples: np.ndarray, sample_rate: int, *, scene_starts: tuple[float, ...] = ()) -> dict:
    """Locate signal defects; this is not a naturalness or speech-coverage score."""
    if sample_rate <= 0:
        raise ValueError("audio health requires a positive sample rate")
    audio = np.asarray(samples)
    if audio.ndim not in (1, 2) or (audio.ndim == 2 and not 1 <= audio.shape[1] <= 8):
        raise ValueError("audio health requires mono or bounded multichannel samples")
    duration = len(audio) / sample_rate
    if duration > MAX_SECONDS + WINDOW_SECONDS:
        raise ValueError("audio health scan exceeds the two-minute Short limit")
    width = max(1, round(sample_rate * WINDOW_SECONDS))
    levels: list[float] = []
    clipped: list[bool] = []
    invalid: list[bool] = []
    for start in range(0, len(audio), width):
        chunk = audio[start:start + width]
        finite = np.isfinite(chunk)
        invalid.append(not bool(finite.all()))
        safe = np.where(finite, chunk, 0).astype(np.float64)
        if safe.ndim == 1:
            safe = safe[:, None]
        rms = float(np.sqrt(np.max(np.mean(safe * safe, axis=0))))
        levels.append(20 * np.log10(max(rms, 1e-12)))
        clipped.append(bool(np.count_nonzero(np.abs(safe) >= .999) >= 3))
    values = np.asarray(levels)
    active = values[values > -50]
    baseline = float(np.median(active)) if len(active) else -50.0
    if not len(audio):
        return {"schema_version": "audio-health-v1", "scope": "advisory_signal_only",
                "duration_seconds": 0.0, "sample_rate": sample_rate,
                "baseline_active_dbfs": baseline,
                "warnings": [{"kind": "empty", "start": 0.0, "end": 0.0, "scene_index": None}],
                "truncated": False}
    checks = [
        ("invalid", np.asarray(invalid, dtype=bool), 0),
        ("clipping", np.asarray(clipped, dtype=bool), 0),
        ("silence", values <= -50, 1.0 if len(active) else 0),
        ("quiet", (values > -50) & (values < baseline - 12), 0.5),
        ("loud", values > baseline + 12, 0.5),
    ]
    warnings = []
    for kind, mask, minimum in checks:
        if not len(mask):
            continue
        edges = np.diff(np.concatenate(([False], mask, [False])).astype(np.int8))
        for first, last in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True):
            begin, end = float(first * width / sample_rate), float(min(last * width / sample_rate, duration))
            if end - begin + 1e-8 < minimum:
                continue
            scene = sum(begin >= start for start in scene_starts) - 1 if scene_starts else None
            warnings.append({"kind": kind, "start": round(begin, 3), "end": round(end, 3),
                             "scene_index": int(max(0, scene)) if scene is not None else None})
    warnings.sort(key=lambda item: (item["start"], item["kind"]))
    truncated = len(warnings) > MAX_WARNINGS
    return {"schema_version": "audio-health-v1", "scope": "advisory_signal_only",
            "duration_seconds": round(duration, 3), "sample_rate": sample_rate,
            "baseline_active_dbfs": round(baseline, 2), "warnings": warnings[:MAX_WARNINGS],
            "truncated": truncated}


def scan_wav(path: Path, *, scene_starts: tuple[float, ...] = ()) -> dict:
    with sf.SoundFile(path) as source:
        if len(source) / source.samplerate > MAX_SECONDS + WINDOW_SECONDS:
            raise ValueError("audio health scan exceeds the two-minute Short limit")
        audio = source.read(dtype="float32", always_2d=True)
        result = scan_samples(audio, source.samplerate, scene_starts=scene_starts)
    result["artifact_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result
