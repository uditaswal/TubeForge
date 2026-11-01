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


SPEECH_FLOOR_DBFS = -40.0  # a window this quiet or quieter is treated as a gap between words, not active speech
MASK_MARGIN_DB = 12.0      # the ducked bed is "too loud under speech" once it comes within this many dB of the voice


def music_under_speech(voice: np.ndarray, bed: np.ndarray, sample_rate: int, *,
                       speech_floor_dbfs: float = SPEECH_FLOOR_DBFS,
                       mask_margin_db: float = MASK_MARGIN_DB) -> dict:
    """Stretches where the ducked music bed sits within ``mask_margin_db`` of active speech —
    an advisory signal that the duck curve did not pull the bed down enough, not a mixing verdict.
    ``voice`` and ``bed`` must be the same length, mono, same sample rate (the pre-limiter voice
    and the already-ducked bed, both still in ``master``'s working arrays)."""
    if sample_rate <= 0:
        raise ValueError("music-under-speech check requires a positive sample rate")
    if voice.ndim != 1 or bed.ndim != 1 or len(voice) != len(bed):
        raise ValueError("music-under-speech check requires equal-length mono voice and bed arrays")
    duration = len(voice) / sample_rate
    if duration > MAX_SECONDS + WINDOW_SECONDS:
        raise ValueError("audio health scan exceeds the two-minute Short limit")
    width = max(1, round(sample_rate * WINDOW_SECONDS))
    voice_db, bed_db = [], []
    for start in range(0, len(voice), width):
        v_rms = float(np.sqrt(np.mean(voice[start:start + width].astype(np.float64) ** 2)))
        b_rms = float(np.sqrt(np.mean(bed[start:start + width].astype(np.float64) ** 2)))
        voice_db.append(20 * np.log10(max(v_rms, 1e-12)))
        bed_db.append(20 * np.log10(max(b_rms, 1e-12)))
    voice_db, bed_db = np.asarray(voice_db), np.asarray(bed_db)
    if not len(voice_db):
        return {"schema_version": "music-under-speech-v1", "scope": "advisory_signal_only",
                "mask_margin_db": mask_margin_db, "speech_floor_dbfs": speech_floor_dbfs,
                "windows_checked": 0, "windows_masked": 0, "warnings": []}
    masked = (voice_db > speech_floor_dbfs) & (bed_db > voice_db - mask_margin_db)
    warnings = []
    edges = np.diff(np.concatenate(([False], masked, [False])).astype(np.int8))
    for first, last in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1), strict=True):
        warnings.append({"start": round(float(first * width / sample_rate), 3),
                         "end": round(float(min(last * width / sample_rate, duration)), 3)})
    return {"schema_version": "music-under-speech-v1", "scope": "advisory_signal_only",
            "mask_margin_db": mask_margin_db, "speech_floor_dbfs": speech_floor_dbfs,
            "windows_checked": int(len(voice_db)), "windows_masked": int(np.count_nonzero(masked)),
            "warnings": warnings[:MAX_WARNINGS]}
