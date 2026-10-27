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
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from tubeforge.core.config import REPOSITORY_ROOT, ReferenceShortConfig
from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentPackage
from tubeforge.rendering.shorts.audio import master
from tubeforge.rendering.shorts.encode import RenderCancelled, encode, file_hash
from tubeforge.rendering.shorts import plates as plates_module
from tubeforge.rendering.shorts.layout import LayoutError, RenderOptions
from tubeforge.rendering.shorts.prepare import prepare
from tubeforge.rendering.shorts.review import write_layout_review
from tubeforge.rendering.shorts.schema import ShortsTopic
from tubeforge.rendering.shorts.timeline import SceneTiming, Timeline, Word

RENDERER_VERSION = "reference-short-v1/render-3"  # sparse caused SFX budget
HYPERFRAMES_RENDERER_VERSION = "reference-short-v1/hyperframes-2"


def renderer_version(config: ReferenceShortConfig) -> str:
    return HYPERFRAMES_RENDERER_VERSION if config.renderer == "hyperframes" else RENDERER_VERSION


def is_reference(package: ContentPackage) -> bool:
    return package.reference_short is not None


def resolve(path: Path) -> Path:
    return path if path.is_absolute() else REPOSITORY_ROOT / path


OPTIONS_FILE = "render_options.json"


def write_options(directory: Path, *, show_sources: bool, watermark: str | None, mascot: bool = False) -> None:
    """Persist the operator's display choices beside the timeline; defaults leave no file (older jobs unchanged)."""
    path = directory / OPTIONS_FILE
    if not show_sources and not watermark and not mascot:
        path.unlink(missing_ok=True)
        return
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"show_sources": bool(show_sources), "watermark": watermark or None, **({"mascot": True} if mascot else {})}, sort_keys=True))


def load_options(directory: Path) -> RenderOptions:
    try:
        data = json.loads((directory / OPTIONS_FILE).read_text())
    except (OSError, ValueError):
        return RenderOptions()
    return RenderOptions(show_sources=bool(data.get("show_sources")), watermark=data.get("watermark") or None, mascot=bool(data.get("mascot")))


def options_identity(directory: Path) -> str:
    path = directory / OPTIONS_FILE
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "none"


def layout_review(topic: ShortsTopic, directory: Path) -> list[Path]:
    """Contact sheet with safe-zone rails, from the same compositor as the video."""
    try:
        return [write_layout_review(topic, directory, load_options(directory.parent))]
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


def load_plates(topic: ShortsTopic, directory: Path, ffmpeg: str = "ffmpeg"):
    manifest = plates_module.load_manifest(directory)
    return plates_module.Plates(topic, directory, manifest, ffmpeg), plates_module.card_indices(topic, manifest)


def plates_identity(directory: Path) -> str:
    path = directory / plates_module.MANIFEST
    return file_hash(path) if path.is_file() else "none"


def load_timeline(topic: ShortsTopic, directory: Path) -> Timeline:
    data = json.loads((directory / "timeline.json").read_text())
    if data.get("topic_sha256") != file_hash(directory / "topic.json"):
        raise ProviderValidationError("reference timeline belongs to a different topic")
    if data.get("narration_sha256") != file_hash(directory / "narration.wav"):
        raise ProviderValidationError("reference narration audio changed after alignment")
    timings = tuple(SceneTiming(row["start"], row["end"], tuple(Word(**w) for w in row["words"]),
                                row["alignment"], row["voice_end"]) for row in data["scenes"])
    try:
        return Timeline(topic, timings, plates_module.card_indices(topic, plates_module.load_manifest(directory)), load_options(directory))
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
           draft: bool, cancelled: Callable[[], bool], bed: "Path | str | None" = "synthesized",
           sfx_enabled: bool = True) -> dict:
    """Master audio then encode; returns the library's QA report (passed).

    ``bed`` is the resolved music choice (``music.resolve_bed``'s caller passes the concrete
    source through): ``"synthesized"`` (default, preserves prior behavior for any caller that
    does not pass it), ``None`` for real silence, or a ``Path`` to an approved catalog file.

    ``sfx_enabled`` defaults to **True**; see ``audio.master``'s docstring for the 26-27 Oct
    back-and-forth that settled on this.
    """
    starts = tuple(t.start for t in timeline.timings)
    templates = tuple(scene.template for scene in timeline.topic.scenes)
    reveal_times = tuple(t.words[s.reveal_words[0]].start
                         for s, t in zip(timeline.topic.scenes, timeline.timings, strict=True))
    try:
        mix = master(directory / "narration.wav", starts, directory / "mix",
                     templates=templates, title=timeline.topic.title, bed=bed, sfx_enabled=sfx_enabled,
                     sfx_max_per_minute=config.sfx.max_per_minute,
                     sfx_min_gap_s=config.sfx.min_gap_s, sfx_peak=config.sfx.peak,
                     reveal_times=reveal_times,
                     cancelled=cancelled, ffmpeg=config.ffmpeg_executable)
        narration_health = json.loads((directory / "mix" / "audio-provenance.json").read_text())["narration_health"]
        if getattr(config, "renderer", "pil") == "hyperframes":
            from tubeforge.rendering.shorts.hyperframes_compose import render_silent
            from tubeforge.rendering.shorts.hyperframes_encode import encode as hyperframes_encode
            started = time.monotonic()
            destination.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="hyperframes-stage-", dir=destination.parent) as scratch:
                silent = Path(scratch) / "silent.mp4"
                scene_report = render_silent(timeline, silent, draft=draft, cancelled=cancelled,
                                             budget_rtf=config.budget_realtime_factor,
                                             ffmpeg=config.ffmpeg_executable)
                return hyperframes_encode(timeline, silent, mix, destination, draft=draft,
                                          cancelled=cancelled, budget_rtf=config.budget_realtime_factor,
                                          render_started=started, ffmpeg=config.ffmpeg_executable,
                                          ffprobe=config.ffprobe_executable,
                                          narration_health=narration_health, scene_report=scene_report)
        return encode(timeline, mix, destination, draft=draft, cancelled=cancelled,
                      budget_rtf=config.budget_realtime_factor, ffmpeg=config.ffmpeg_executable,
                      ffprobe=config.ffprobe_executable,
                      plates=load_plates(timeline.topic, directory, config.ffmpeg_executable)[0],
                      narration_health=narration_health)
    except RenderCancelled:
        raise
    except (ValueError, MemoryError, TimeoutError, LayoutError) as error:
        raise ProviderValidationError(f"reference render failed its gate: {error}") from error


def render_identity(topic: ShortsTopic, narration_sha: str, timeline_sha: str, *, draft: bool,
                    approval_identity: str | None, plates_sha: str = "none", options_sha: str = "none",
                    music_sha: str = "none", renderer: str = "pil") -> str:
    material = {"renderer": RENDERER_VERSION, "draft": draft, "topic": hashlib.sha256(
        topic.model_dump_json().encode()).hexdigest(), "narration": narration_sha,
        "timeline": timeline_sha, "approval": approval_identity}
    if plates_sha != "none":
        material["plates"] = plates_sha
    if options_sha != "none":
        material["options"] = options_sha
    if music_sha != "none":
        material["music"] = music_sha
    if renderer != "pil":
        material["renderer_choice"] = renderer
    return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
