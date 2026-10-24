"""Bounded, frame-wide black/freeze inspection of the actual encoded video."""
from __future__ import annotations

import numpy as np

from .encode import checked, file_hash

SAMPLE_FPS = 4
WIDTH, HEIGHT = 160, 284


def _intervals(mask, *, sample_fps: int, minimum_seconds: float, scene_starts: tuple[float, ...]):
    result = []
    first = None
    for index in range(len(mask) + 1):
        active = index < len(mask) and bool(mask[index])
        if active and first is None:
            first = index
        if not active and first is not None:
            start, end = first / sample_fps, index / sample_fps
            if end - start >= minimum_seconds:
                midpoint = (start + end) / 2
                scene_index = max(0, sum(midpoint >= at for at in scene_starts) - 1)
                result.append({"start": round(start, 3), "end": round(end, 3),
                               "scene_index": scene_index})
            first = None
    return result


def inspect_encoded_video(path, *, duration: float, scene_starts: tuple[float, ...],
                          ffmpeg: str, deadline: float, cancelled):
    """Inspect every quarter-second sample; freeze is advisory, black is a gate.

    Small, fast grayscale frames detect failed encoded output, not semantic
    relevance or readable text. Deliberately static cards can be freeze warnings.
    """
    raw = checked([ffmpeg, "-v", "error", "-i", str(path), "-an", "-vf",
                   f"fps={SAMPLE_FPS},scale={WIDTH}:{HEIGHT},format=gray", "-f", "rawvideo", "pipe:1"],
                  deadline=deadline, cancelled=cancelled)
    frame_bytes = WIDTH * HEIGHT
    if len(raw) % frame_bytes or len(raw) < frame_bytes * max(2, int(duration * SAMPLE_FPS) - 2):
        raise ValueError("temporal video inspection returned incomplete frames")
    frames = np.frombuffer(raw, np.uint8).reshape(-1, HEIGHT, WIDTH)
    means = frames.mean(axis=(1, 2))
    p95 = np.percentile(frames, 95, axis=(1, 2))
    black = (means < 10) & (p95 < 18)
    changes = np.abs(np.diff(frames.astype(np.int16), axis=0)).mean(axis=(1, 2))
    # A pairwise zero-delta interval covers both frames, so prepend false and
    # report only runs lasting at least one second.
    frozen = np.concatenate(([False], changes < .08))
    black_intervals = _intervals(black, sample_fps=SAMPLE_FPS, minimum_seconds=.5,
                                 scene_starts=scene_starts)
    frozen_intervals = _intervals(frozen, sample_fps=SAMPLE_FPS, minimum_seconds=1.0,
                                  scene_starts=scene_starts)
    return {"schema_version": "temporal-video-qa-v1", "artifact_sha256": file_hash(path),
            "sample_fps": SAMPLE_FPS, "sample_count": len(frames),
            "black_intervals": black_intervals, "freeze_intervals": frozen_intervals,
            "minimum_mean_luma": round(float(means.min()), 2),
            "scope": "encoded_frame_signal_only; static cards may be intentional"}
