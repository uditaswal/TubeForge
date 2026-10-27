"""Licensed, cause-driven sound effects with a deterministic per-video budget."""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from .encode import checked

SFX_ROOT = Path(__file__).resolve().parents[2] / "assets" / "sfx"
_MANIFEST = json.loads((SFX_ROOT / "manifest.json").read_text())
CUE_PEAK = .18
RISER_CUE = "riser"
TAKES = {"number": ("pop", "ping"), "typed": ("key-press", "typing"),
         "whoosh": ("whoosh-short", "whoosh"), "payoff": ("riser", "impact-bass-1")}
PRIORITY = {"payoff": 0, "number": 1, "typed": 2, "whoosh": 3}


def schedule(scene_starts: tuple[float, ...], templates: tuple[str, ...], duration: float, *,
             reveal_times: tuple[float, ...] | None = None,
             hard_topic_changes: frozenset[int] = frozenset(),
             max_per_minute: int = 4, min_gap_s: float = 6.0) -> tuple[list[dict], list[dict]]:
    """Select strongest on-screen causes first; the final payoff may break the gap.

    A hard topic change must be explicitly marked; ordinary cuts are silent.
    The rate cap is proportional to duration, rounded down (30 s permits two).
    """
    if len(scene_starts) != len(templates) or (reveal_times is not None and len(reveal_times) != len(templates)):
        raise ValueError("sound-effect timings must name every scene")
    if max_per_minute < 0 or min_gap_s < 0 or duration <= 0:
        raise ValueError("invalid sound-effect budget")
    if any(i <= 0 or i >= len(templates) for i in hard_topic_changes):
        raise ValueError("hard topic change index is outside the scene list")
    candidates = []
    for index, template in enumerate(templates[1:], 1):
        if index == len(templates) - 1 and template in {"cta", "loop"}:
            cause = "payoff"
        elif template == "big_stat":
            cause = "number"
        elif template == "terminal":
            cause = "typed"
        elif index in hard_topic_changes:
            cause = "whoosh"
        else:
            continue
        at = (reveal_times[index] if reveal_times is not None and cause in {"number", "typed"}
              else scene_starts[index])
        if not scene_starts[index] <= at < duration:
            raise ValueError("sound-effect reveal lies outside the video")
        candidates.append({"scene_index": index, "template": template, "cause": cause, "at_seconds": at})
    limit = math.floor(duration * max_per_minute / 60 + 1e-9)
    chosen, dropped = [], []
    for candidate in sorted(candidates, key=lambda c: (PRIORITY[c["cause"]], c["at_seconds"], c["scene_index"])):
        at, cause = candidate["at_seconds"], candidate["cause"]
        if len(chosen) >= limit:
            reason = "rate_cap"
        elif cause == "whoosh" and any(c["cause"] == "whoosh" and abs(c["at_seconds"] - at) < 10 for c in chosen):
            reason = "whoosh_gap"
        elif cause != "payoff" and any(c["cause"] != "payoff" and abs(c["at_seconds"] - at) < min_gap_s for c in chosen):
            reason = "min_gap"
        else:
            chosen.append(candidate)
            continue
        dropped.append({**candidate, "reason": reason})
    chosen.sort(key=lambda c: (c["at_seconds"], c["scene_index"]))
    used = {cause: 0 for cause in TAKES}
    previous = None
    for candidate in chosen:
        cause = candidate["cause"]
        takes = TAKES[cause]
        offset = used[cause] % len(takes)
        cue = takes[offset] if takes[offset] != previous else takes[(offset + 1) % len(takes)]
        candidate["cue"] = cue
        used[cause] += 1
        previous = cue
    dropped.sort(key=lambda c: (c["at_seconds"], c["scene_index"]))
    return chosen, dropped


def load(name: str, sample_rate: int, *, ffmpeg: str, deadline: float, cancelled) -> np.ndarray:
    """Decode a vendored cue to mono float32 PCM at sample_rate, peak-normalized to 1.0."""
    entry = _MANIFEST.get(name)
    if entry is None:
        raise ValueError(f"unknown sound-effect cue: {name!r}")
    path = SFX_ROOT / entry["file"]
    raw = checked([ffmpeg, "-y", "-v", "error", "-i", str(path), "-ar", str(sample_rate),
                   "-ac", "1", "-f", "f32le", "-"], deadline=deadline, cancelled=cancelled)
    samples = np.frombuffer(raw, dtype=np.float32).copy()
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak < 1e-6:
        raise ValueError(f"sound-effect cue decoded to silence: {name!r}")
    return samples / peak


def place(effects: np.ndarray, cue: np.ndarray, start: int, *, peak: float = CUE_PEAK) -> None:
    """Add a normalized cue; trim a pre-roll that begins before zero."""
    if start >= len(effects):
        raise ValueError("sound-effect cue starts at or after the end of the mastered audio")
    source_offset = max(0, -start)
    dest_start = max(0, start)
    count = min(len(cue) - source_offset, len(effects) - dest_start)
    if count <= 0:
        return
    effects[dest_start:dest_start + count] += (cue[source_offset:source_offset + count] * peak).astype(np.float32)
