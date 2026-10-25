"""Licensed sound-effect cues, placed by scene-template cause (video-quality review §4.5).

19 Pixabay Content License effects (``assets/sfx/``, provenance in
``assets/sfx/LICENSE-pixabay.md``) replace the inaudible filtered-noise accent that used
to play on every cut. Each scene *entered* picks one effect from its template, so the sound
has a cause on screen instead of repeating the same whoosh everywhere (the HyperFrames sound
guide's "most common tell"). The final scene (``cta``/``loop``) gets the cinematic riser
instead, built to crest exactly on the payoff cut.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .encode import checked

SFX_ROOT = Path(__file__).resolve().parents[2] / "assets" / "sfx"
_MANIFEST = json.loads((SFX_ROOT / "manifest.json").read_text())

# One effect per destination template: what the viewer is cutting *into* is the cause.
# "hook" never appears here (scene 0 has no incoming cut); any template this map does not
# name (a future scene type) falls back to "whoosh-short" rather than failing the render.
CUE_BY_TEMPLATE = {
    "big_stat": "pop",            # a number landing
    "before_after": "whoosh-short",
    "flow": "whoosh-short",
    "checklist": "click",         # an item being checked off
    "terminal": "key-press",
    "cta": "impact-bass-1",       # the headline/payoff lands
}
RISER_TEMPLATES = {"cta", "loop"}
FALLBACK_CUE = "whoosh-short"
RISER_CUE = "riser"

# Target peak amplitude for a placed cue, relative to the voice peak (.75, see audio.py).
# Between the music bed (~.12 before duck) and the voice: audible, not dominant; the final
# loudnorm/limiter pass corrects the overall mix level and true peak afterward.
CUE_PEAK = .30


def cue_for_template(template: str) -> str:
    if template in RISER_TEMPLATES:
        return RISER_CUE
    return CUE_BY_TEMPLATE.get(template, FALLBACK_CUE)


def load(name: str, sample_rate: int, *, ffmpeg: str, deadline: float, cancelled) -> np.ndarray:
    """Decode a vendored cue to mono float32 PCM at ``sample_rate``, peak-normalized to 1.0."""
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


def place(effects: np.ndarray, cue: np.ndarray, start: int) -> None:
    """Add a peak-normalized cue into the effects track at ``start``.

    A cue that would start before t=0 (the riser needs more lead time than the render has)
    is trimmed from its front so its tail still lands at the intended cut — that is the
    designed behavior, not a bug. A cue placed at or past the end of the track is a real
    scheduling bug (a scene cue sits after the audio ends) and raises rather than silently
    dropping the effect, matching the strict-cue-placement contract this replaces.
    """
    if start >= len(effects):
        raise ValueError("sound-effect cue starts at or after the end of the mastered audio")
    source_offset = max(0, -start)
    dest_start = max(0, start)
    count = min(len(cue) - source_offset, len(effects) - dest_start)
    if count <= 0:
        return
    effects[dest_start:dest_start + count] += (cue[source_offset:source_offset + count] * CUE_PEAK).astype(np.float32)
