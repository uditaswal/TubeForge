"""Weighted blends of Kokoro's own voice style vectors (VoiceStudio competitive-analysis
Action 12, ported from the idea in Kokoro-FastAPI, Apache-2.0: "blend voices by ratio as a
voice-design primitive"). A blend is a new acoustic timbre for the channel, built purely from
the operator's own bundled voice set — no new model, no new audio, no change to what text is
spoken or how it times: the result is still one Kokoro style vector, the same shape and the
same contract as a plain named voice.

A spec is ``"name:weight+name:weight[+...]"``, e.g. ``"af_bella:0.7+af_sarah:0.3"``. Weights
need not already sum to 1 — they are normalized here — but must be positive, and at least two
distinct voices must be named (a one-voice "blend" is just that voice; spell it as a plain
voice_id instead, so every blend name on screen names something actually different).
"""
from __future__ import annotations

import re

import numpy as np

_COMPONENT = re.compile(r"^([A-Za-z0-9_]+):([0-9]*\.?[0-9]+)$")


def parse_blend_spec(spec: str) -> tuple[tuple[str, float], ...]:
    """Validate and normalize a blend spec; weights sum to 1.0 in the returned tuple."""
    parts = spec.split("+")
    if len(parts) < 2:
        raise ValueError(f"voice blend {spec!r} needs at least two name:weight components")
    parsed: list[tuple[str, float]] = []
    seen: set[str] = set()
    for part in parts:
        match = _COMPONENT.fullmatch(part.strip())
        if match is None:
            raise ValueError(f"voice blend component {part!r} is not 'name:weight'")
        name, weight = match.group(1), float(match.group(2))
        if weight <= 0 or not np.isfinite(weight):
            raise ValueError(f"voice blend weight for {name!r} must be a finite positive number")
        if name in seen:
            raise ValueError(f"voice blend names {name!r} more than once")
        seen.add(name)
        parsed.append((name, weight))
    total = sum(weight for _, weight in parsed)
    return tuple((name, weight / total) for name, weight in parsed)


def resolve_blend(get_voice_style, spec: str) -> np.ndarray:
    """Build the blended style vector. ``get_voice_style`` is ``Kokoro.get_voice_style``."""
    components = parse_blend_spec(spec)
    blended = None
    for name, weight in components:
        style = np.asarray(get_voice_style(name), dtype=np.float32)
        blended = style * weight if blended is None else blended + style * weight
    return blended.astype(np.float32)
