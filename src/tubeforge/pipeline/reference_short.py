"""Adapter between the durable job pipeline and ``rendering/shorts``.

For packages carrying ``reference_short`` scenes (prompt ``m6-content-v8``) the
orchestrator calls these functions instead of the legacy phrase/segment path.
This module owns no layout or timing logic: geometry, QA and encoding live in
``tubeforge.rendering.shorts``. It only maps durable job artifacts to that
library and back, and never approves anything.
"""
from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path

from tubeforge.core.config import REPOSITORY_ROOT, ReferenceShortConfig
from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentPackage
from tubeforge.rendering.shorts.audio import master
from tubeforge.rendering.shorts.encode import RenderCancelled, encode, file_hash
from tubeforge.rendering.shorts.layout import LayoutError
from tubeforge.rendering.shorts.prepare import prepare
from tubeforge.rendering.shorts.review import write_layout_review
from tubeforge.rendering.shorts.schema import ShortsTopic
from tubeforge.rendering.shorts.timeline import SceneTiming, Timeline, Word

RENDERER_VERSION = "reference-short-v1/render-1"


def is_reference(package: ContentPackage) -> bool:
    return package.reference_short is not None


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def layout_review(topic: ShortsTopic, directory: Path) -> list[Path]:
    """Contact sheet with safe-zone rails, from the same compositor as the video."""
    try:
        return [write_layout_review(topic, directory)]
    except LayoutError as error:
        raise ProviderValidationError(f"reference scene layout rejected: {error}") from error


def prepare_speech(topic: ShortsTopic, directory: Path, config: ReferenceShortConfig, *,
                   voice: str | None, cancelled: Callable[[], bool]) -> Timeline:
    """Kokoro speech then forced alignment, one model per child process."""
    if config.alignment_model_path is None:
        raise ProviderValidationError("pipeline.reference_short.alignment_model_path is not configured")
    model = resolve(config.alignment_model_path)
    if not model.is_dir():
        raise ProviderValidationError("reference alignment model directory is missing")
    settings_path = resolve(Path(os.environ.get("TUBEFORGE_CONFIG", "config/default.yaml")))
    try:
        return prepare(topic, directory, config=settings_path, alignment_model=model,
                       voice=voice or config.voice, cancelled=cancelled)
    except RenderCancelled:
        raise
    except (ValueError, TimeoutError) as error:
        raise ProviderValidationError(f"reference speech preparation failed: {error}") from error


def load_timeline(topic: ShortsTopic, directory: Path) -> Timeline:
    data = json.loads((directory / "timeline.json").read_text())
    if data.get("topic_sha256") != file_hash(directory / "topic.json"):
        raise ProviderValidationError("reference timeline belongs to a different topic")
    if data.get("narration_sha256") != file_hash(directory / "narration.wav"):
        raise ProviderValidationError("reference narration audio changed after alignment")
    timings = tuple(SceneTiming(row["start"], row["end"], tuple(Word(**w) for w in row["words"]),
                                row["alignment"], row["voice_end"]) for row in data["scenes"])
    try:
        return Timeline(topic, timings)
    except (ValueError, LayoutError) as error:
        raise ProviderValidationError(f"reference timeline rejected: {error}") from error


def srt_from_timeline(timeline: Timeline) -> str:
    """Reviewer-facing SRT of the displayed caption chunks (the video burns its own)."""
    def stamp(value: float) -> str:
        ms = round(value * 1000)
        return f"{ms // 3_600_000:02}:{ms // 60_000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"
    rows, number = [], 1
    for index, (scene, timing) in enumerate(zip(timeline.topic.scenes, timeline.timings, strict=True)):
        offset = 0
        for group in timeline.renderer.groups[index]:
            words = timing.words[offset:offset + len(group)]
            rows.append(f"{number}\n{stamp(words[0].start)} --> {stamp(words[-1].end)}\n{' '.join(group)}\n")
            number += 1
            offset += len(group)
    return "\n".join(rows)


def render(timeline: Timeline, directory: Path, destination: Path, config: ReferenceShortConfig, *,
           draft: bool, cancelled: Callable[[], bool]) -> dict:
    """Master audio then encode; returns the library's QA report (passed)."""
    starts = tuple(t.start for t in timeline.timings)
    try:
        mix = master(directory / "narration.wav", starts, directory / "mix", cancelled=cancelled,
                     ffmpeg=config.ffmpeg_executable)
        return encode(timeline, mix, destination, draft=draft, cancelled=cancelled,
                      budget_rtf=config.budget_realtime_factor, ffmpeg=config.ffmpeg_executable,
                      ffprobe=config.ffprobe_executable)
    except RenderCancelled:
        raise
    except (ValueError, MemoryError, TimeoutError, LayoutError) as error:
        raise ProviderValidationError(f"reference render failed its gate: {error}") from error


def render_identity(topic: ShortsTopic, narration_sha: str, timeline_sha: str, *, draft: bool,
                    approval_identity: str | None) -> str:
    material = {"renderer": RENDERER_VERSION, "draft": draft, "topic": hashlib.sha256(
        topic.model_dump_json().encode()).hexdigest(), "narration": narration_sha,
        "timeline": timeline_sha, "approval": approval_identity}
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
