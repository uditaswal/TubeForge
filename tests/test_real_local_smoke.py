"""Opt-in real M24/M25 acceptance test using Piper, FFmpeg, and the orchestrator."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
import struct
import wave
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from tubeforge.providers.media.local_graphics import STYLE_VERSION as STORYBOARD_STYLE_VERSION

from tubeforge.core.config import (
    AppConfig,
    CodexProviderConfig,
    DatabaseConfig,
    FakeProviderConfig,
    FinalRenderConfig,
    MediaPipelineConfig,
    PipelineConfig,
    PiperProviderConfig,
    PreviewRenderConfig,
    Settings,
    ShortsFinalRenderConfig,
    ShortsPreviewRenderConfig,
    VoicePipelineConfig,
)
from tubeforge.core.runtime import create_runtime
from tubeforge.domain.contracts import ContentPackage, ContentRequest, SourceReference
from tubeforge.domain.states import ApprovalGate, JobState
from tubeforge.workers.service import WorkerService
from tubeforge.providers.content.prompts import validate_video_package


MODEL_ENV = "TUBEFORGE_SMOKE_PIPER_MODEL"
TOPIC_ENV = "TUBEFORGE_SMOKE_TOPIC"
PROMPT_VERSION_ENV = "TUBEFORGE_SMOKE_PROMPT_VERSION"
VISUAL_SOURCE_ENV = "TUBEFORGE_SMOKE_VISUAL_SOURCE"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _requirements() -> tuple[Path | None, str | None]:
    raw_model = os.environ.get(MODEL_ENV)
    if not raw_model:
        return None, f"set {MODEL_ENV} to an installed Piper ONNX voice model"
    model = Path(raw_model).expanduser().resolve()
    if not model.is_file():
        return None, f"{MODEL_ENV} does not identify a file"
    missing = [name for name in ("piper", "ffmpeg", "ffprobe") if shutil.which(name) is None]
    return (model, None) if not missing else (None, f"missing real smoke executables: {', '.join(missing)}")


PIPER_MODEL, SKIP_REASON = _requirements()
pytestmark = pytest.mark.skipif(SKIP_REASON is not None, reason=SKIP_REASON or "real tools unavailable")
CODEX_SKIP_REASON = None if shutil.which("codex") else "Codex CLI is not installed on PATH"


def _migrate(path: Path) -> None:
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{path}"])
    command.upgrade(config, "head")


def _probe(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height,avg_frame_rate,sample_rate,channels", "-of", "json", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
        shell=False,
    )
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    return json.loads(completed.stdout)


def _visual_frame_digest(video: Path, timestamp: float) -> str:
    """Hash the upper visual region, excluding the burned-caption area.

    Full-frame hashes are not sufficient evidence of scene changes because
    distinct subtitle text can make otherwise identical visuals hash
    differently.  The production captions are bottom-aligned, so crop the
    upper half before decoding the frame used by this acceptance check.
    """
    completed = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "crop=iw:floor(ih/2):0:0",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=30,
        shell=False,
    )
    assert completed.returncode == 0 and completed.stdout, completed.stderr.decode(errors="replace")
    return hashlib.sha256(completed.stdout).hexdigest()


def _decoded_audio_rms(path: Path) -> float:
    """Decode the first audio stream and prove it contains an audible signal."""
    completed = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "8000",
            "-f",
            "s16le",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
        shell=False,
    )
    assert completed.returncode == 0 and len(completed.stdout) >= 16_000, completed.stderr.decode(errors="replace")
    sample_count = len(completed.stdout) // 2
    samples = struct.unpack(f"<{sample_count}h", completed.stdout[: sample_count * 2])
    rms = math.sqrt(sum(sample * sample for sample in samples) / sample_count)
    # PCM silence has an RMS of zero. Leave generous headroom for quiet Piper
    # voices while still rejecting an empty/silent narration track.
    assert rms >= 10.0, f"decoded audio is effectively silent (RMS={rms:.3f})"
    return rms


@pytest.mark.parametrize(
    ("content_provider", "artifact_stem"),
    (
        pytest.param("fixed", "fixed_piper_six_scene_smoke", id="fixed"),
        pytest.param(
            "codex",
            "codex_generated_smoke",
            id="codex",
            marks=pytest.mark.skipif(CODEX_SKIP_REASON is not None, reason=CODEX_SKIP_REASON or "Codex unavailable"),
        ),
    ),
)
def test_piper_job_creates_real_six_scene_smoke_video(
    tmp_path: Path, content_provider: str, artifact_stem: str
) -> None:
    """Exercise the fixed and live-LLM providers through the real pipeline."""
    assert PIPER_MODEL is not None
    database_path = tmp_path / "real-smoke.db"
    _migrate(database_path)
    smoke_root = REPOSITORY_ROOT / "artifacts" / "smoke"
    work_root = tmp_path / "artifacts"
    settings = Settings(
        app=AppConfig(name="TubeForge real smoke", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{database_path}"),
        pipeline=PipelineConfig(
            content_provider=content_provider,
            voice_provider="piper",
            fake=FakeProviderConfig(artifact_root=tmp_path / "synthetic-visuals"),
            codex=CodexProviderConfig(executable="codex", timeout_seconds=900),
            piper=PiperProviderConfig(model_path=PIPER_MODEL, cache_root=tmp_path / "piper-cache", timeout_seconds=300),
            voice=VoicePipelineConfig(artifact_root=work_root),
            media=MediaPipelineConfig(provider="hybrid", cache_root=tmp_path / "asset-cache", min_width=64, min_height=64),
            preview=PreviewRenderConfig(width=640, height=360, minimum_free_bytes=1, timeout_seconds=900),
            final=FinalRenderConfig(width=640, height=360, minimum_free_bytes=1, timeout_seconds=900),
        ),
    )
    runtime = create_runtime(settings)
    try:
        request = ContentRequest(
            topic=os.environ.get(TOPIC_ENV, "How TubeForge builds a local narrated video"),
            angle="A practical one-minute engineering roadmap",
            target_duration_seconds=60,
            language="en",
            audience="general",
            prompt_version=os.environ.get(PROMPT_VERSION_ENV, "m24-real-smoke-v1"),
            sources=(SourceReference(source_id="local-design", url="https://example.invalid/tubeforge", title="TubeForge local pipeline"),),
            visual_source=os.environ.get(VISUAL_SOURCE_ENV, "generated"),
        )
        job = runtime.jobs.create("m24-real-local-smoke", request)
        worker = WorkerService("real-smoke-worker", runtime.jobs, runtime.orchestrator, settings.worker, clock=lambda: datetime(2026, 8, 24, tzinfo=UTC))

        assert worker.run_once().state is JobState.SCRIPT_APPROVAL_REQUIRED
        runtime.approvals.record("real-smoke-script", job.id, ApprovalGate.SCRIPT, actor="automated-real-smoke")
        preview = worker.run_once()
        assert preview is not None and preview.state is JobState.PREVIEW_READY, preview.failure_message if preview else "no job"
        preview_manifest = runtime.artifacts.get(job.id, JobState.PREVIEW_RENDERING, "preview_manifest")
        assert preview_manifest is not None
        preview_identity = json.loads(Path(preview_manifest.path).read_text(encoding="utf-8"))["render_identity"]
        runtime.approvals.record("real-smoke-preview", job.id, ApprovalGate.PREVIEW, actor="automated-real-smoke", reviewed_identity=preview_identity)
        assert worker.run_once().state is JobState.FINAL_READY

        final = runtime.artifacts.get(job.id, JobState.FINAL_RENDERING, "final")
        timing_artifact = runtime.artifacts.get(job.id, JobState.VOICE_GENERATION, "timing_map")
        narration_artifact = runtime.artifacts.get(job.id, JobState.VOICE_GENERATION, "narration")
        asset_manifest = runtime.artifacts.get(job.id, JobState.ASSET_ACQUISITION, "asset_manifest")
        content_artifact = runtime.artifacts.get(job.id, JobState.CONTENT_GENERATING, "content_package")
        assert final and timing_artifact and narration_artifact and asset_manifest and content_artifact
        timing = json.loads(Path(timing_artifact.path).read_text(encoding="utf-8"))
        assets = json.loads(Path(asset_manifest.path).read_text(encoding="utf-8"))["scenes"]
        content = json.loads(Path(content_artifact.path).read_text(encoding="utf-8"))
        assert len(assets) >= 6
        assert len({value["path"] for value in assets.values()}) == len(assets)
        assert len({value["checksum_sha256"] for value in assets.values()}) == len(assets)
        if request.visual_source == "stock":
            # Stock remains preferred, but a sparse verified Commons result
            # must not prevent a safe local-video render.
            for asset in assets.values():
                fallback = asset.get("fallback")
                if fallback is not None:
                    assert fallback["to"] == "local generated CC0 scene art"
                    assert asset["request"]["visual_source"] == "stock"
                    assert asset["resolved_request"]["visual_source"] == "generated"

        smoke_root.mkdir(parents=True, exist_ok=True)
        accepted_video = smoke_root / f"{artifact_stem}.mp4"
        temporary_video = accepted_video.with_suffix(".part.mp4")
        shutil.copyfile(final.path, temporary_video)
        temporary_video.replace(accepted_video)

        accepted_narration = smoke_root / f"{artifact_stem}.wav"
        temporary_narration = accepted_narration.with_suffix(".part.wav")
        shutil.copyfile(narration_artifact.path, temporary_narration)
        temporary_narration.replace(accepted_narration)

        video_probe = _probe(accepted_video)
        audio_probe = _probe(accepted_narration)
        video_streams = video_probe["streams"]
        video_stream = next(stream for stream in video_streams if stream.get("codec_type") == "video")
        muxed_audio_stream = next(stream for stream in video_streams if stream.get("codec_type") == "audio")
        narration_stream = next(stream for stream in audio_probe["streams"] if stream.get("codec_type") == "audio")
        assert video_stream["codec_name"] == "h264"
        assert (video_stream["width"], video_stream["height"]) == (640, 360)
        fps_numerator, fps_denominator = str(video_stream["avg_frame_rate"]).split("/", 1)
        assert float(fps_numerator) / float(fps_denominator) == pytest.approx(settings.pipeline.final.fps, abs=0.01)
        assert muxed_audio_stream["codec_name"] == "aac"
        assert int(muxed_audio_stream["sample_rate"]) > 0
        assert int(muxed_audio_stream["channels"]) > 0
        assert narration_stream["codec_name"] == "pcm_s16le"
        assert int(narration_stream["sample_rate"]) == 48_000
        assert int(narration_stream["channels"]) == 1
        narration_duration = float(audio_probe["format"]["duration"])
        video_duration = float(video_probe["format"]["duration"])
        assert 60 <= narration_duration <= 90
        assert video_duration == pytest.approx(narration_duration, abs=settings.pipeline.final.sync_tolerance_seconds)
        assert int(video_probe["format"]["size"]) > 0
        narration_rms = _decoded_audio_rms(accepted_narration)
        video_audio_rms = _decoded_audio_rms(accepted_video)

        probe_record = smoke_root / f"{artifact_stem}.ffprobe.json"
        temporary_probe = probe_record.with_suffix(".part.json")
        temporary_probe.write_text(
            json.dumps(
                {
                    "narration": {**audio_probe, "decoded_rms": narration_rms},
                    "video": {**video_probe, "decoded_audio_rms": video_audio_rms},
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary_probe.replace(probe_record)

        section_scenes = {section["section_id"]: section["scene_id"] for section in content["script_sections"]}
        scene_groups: dict[str, list[dict[str, object]]] = {}
        for phrase in timing["phrases"]:
            scene_groups.setdefault(section_scenes[phrase["section_id"]], []).append(phrase)
        midpoints = [(float(group[0]["start_seconds"]) + float(group[-1]["end_seconds"])) / 2 for group in scene_groups.values()]
        assert len(midpoints) >= 6
        assert len({_visual_frame_digest(accepted_video, timestamp) for timestamp in midpoints}) == len(midpoints)
    finally:
        runtime.database.dispose()


def test_piper_short_renders_real_1080x1920_with_word_alignment(tmp_path: Path) -> None:
    """Prove the complete sourced, portrait, captioned, music-mixed Shorts path."""
    assert PIPER_MODEL is not None
    writer_evidence = REPOSITORY_ROOT / "artifacts" / "smoke" / "ollama_shorts_content.json"
    if not writer_evidence.is_file():
        pytest.skip("run the real Ollama writer acceptance before the full Shorts render")
    accepted_package = ContentPackage.model_validate(json.loads(writer_evidence.read_text(encoding="utf-8"))["package"])
    validate_video_package(accepted_package, accepted_package.request, provider_name="Ollama evidence")

    class AcceptedLocalWriter:
        def generate_package(self, request: ContentRequest) -> ContentPackage:
            return accepted_package.model_copy(update={"request": request})

    database_path = tmp_path / "real-shorts-smoke.db"
    _migrate(database_path)
    smoke_root = REPOSITORY_ROOT / "artifacts" / "smoke"
    work_root = tmp_path / "artifacts"
    settings = Settings(
        app=AppConfig(name="TubeForge Shorts smoke", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{database_path}"),
        pipeline=PipelineConfig(
            content_provider="fake",
            voice_provider="piper",
            fake=FakeProviderConfig(artifact_root=tmp_path / "synthetic-visuals"),
            piper=PiperProviderConfig(model_path=PIPER_MODEL, cache_root=tmp_path / "piper-cache", timeout_seconds=300),
            voice=VoicePipelineConfig(artifact_root=work_root),
            media=MediaPipelineConfig(provider="hybrid", cache_root=tmp_path / "asset-cache", min_width=64, min_height=64),
            shorts_preview=ShortsPreviewRenderConfig(width=360, height=640, minimum_free_bytes=1, timeout_seconds=900, threads=2),
            shorts_final=ShortsFinalRenderConfig(minimum_free_bytes=1, timeout_seconds=1800, threads=2),
        ),
    )
    runtime = create_runtime(settings)
    try:
        runtime.orchestrator.content = AcceptedLocalWriter()
        music_buffer = tmp_path / "quiet-circuit.wav"
        sample_rate = 16_000
        with wave.open(str(music_buffer), "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(sample_rate)
            stream.writeframes(b"".join(struct.pack("<h", round(1_200 * math.sin(2 * math.pi * 110 * index / sample_rate))) for index in range(sample_rate * 4)))
        assert runtime.orchestrator.music_catalog is not None
        runtime.orchestrator.music_catalog.upload(
            name="Quiet Circuit acceptance bed",
            filename=music_buffer.name,
            payload=music_buffer.read_bytes(),
            source_url="https://example.invalid/music/quiet-circuit",
            license_name="CC BY 4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            attribution_required=True,
            attribution="Quiet Circuit acceptance bed — TubeForge test — CC BY 4.0",
            publishing_allowed=True,
        )
        request = accepted_package.request.model_copy(update={"music_track": "Quiet Circuit acceptance bed", "prompt_version": "shorts-quality-e2e-v1"})
        job = runtime.jobs.create("shorts-real-local-smoke", request)
        worker = WorkerService("shorts-smoke-worker", runtime.jobs, runtime.orchestrator, settings.worker)
        assert worker.run_once().state is JobState.SCRIPT_APPROVAL_REQUIRED
        content_artifact = runtime.artifacts.get(job.id, JobState.CONTENT_GENERATING, "content_package")
        assert content_artifact is not None
        content = json.loads(Path(content_artifact.path).read_text(encoding="utf-8"))
        assert 108 <= len(" ".join(section["narration"] for section in content["script_sections"]).split()) <= 166
        runtime.approvals.record("shorts-smoke-script", job.id, ApprovalGate.SCRIPT, actor="automated-real-smoke", reviewed_identity=content_artifact.checksum_sha256)
        preview = worker.run_once()
        assert preview is not None and preview.state is JobState.PREVIEW_READY, preview.failure_message if preview else "no job"
        preview_manifest = runtime.artifacts.get(job.id, JobState.PREVIEW_RENDERING, "preview_manifest")
        assert preview_manifest is not None
        preview_identity = json.loads(Path(preview_manifest.path).read_text(encoding="utf-8"))["render_identity"]
        runtime.approvals.record("shorts-smoke-preview", job.id, ApprovalGate.PREVIEW, actor="automated-real-smoke", reviewed_identity=preview_identity)
        completed = worker.run_once()
        assert completed is not None and completed.state is JobState.FINAL_READY, completed.failure_message if completed else "no job"

        final = runtime.artifacts.get(job.id, JobState.FINAL_RENDERING, "final")
        narration = runtime.artifacts.get(job.id, JobState.VOICE_GENERATION, "narration")
        timing_artifact = runtime.artifacts.get(job.id, JobState.VOICE_GENERATION, "timing_map")
        captions = runtime.artifacts.get(job.id, JobState.CAPTION_GENERATION, "captions")
        quality_artifact = runtime.artifacts.get(job.id, JobState.FINAL_READY, "quality_report")
        asset_manifest = runtime.artifacts.get(job.id, JobState.ASSET_ACQUISITION, "asset_manifest")
        final_manifest = runtime.artifacts.get(job.id, JobState.FINAL_RENDERING, "final_manifest")
        assert final and narration and timing_artifact and captions and quality_artifact and asset_manifest and final_manifest
        timing = json.loads(Path(timing_artifact.path).read_text(encoding="utf-8"))
        quality = json.loads(Path(quality_artifact.path).read_text(encoding="utf-8"))
        assets = json.loads(Path(asset_manifest.path).read_text(encoding="utf-8"))
        render_record = json.loads(Path(final_manifest.path).read_text(encoding="utf-8"))
        assert timing["alignment"]["verified"] and timing["alignment"]["first_word_seconds"] <= 3
        assert quality["passed"] and quality["shorts"]["maximum_visual_hold_seconds"] <= 3
        assert len(set(quality["shorts"]["motion_variants"])) == 4
        assert assets["quality"]["profile"].startswith(f"{STORYBOARD_STYLE_VERSION}:")
        assert assets["quality"]["scene_count"] == assets["quality"]["unique_scene_count"] == 6
        assert render_record["inputs"]["music"]["license_name"] == "CC BY 4.0"
        assert "sidechaincompress=" in ";".join(render_record["command"])
        assert Path(captions.path).suffix == ".ass" and "PlayResX: 1080" in Path(captions.path).read_text(encoding="utf-8")

        published = worker.run_once()
        assert published is not None and published.state is JobState.PUBLICATION_APPROVAL_REQUIRED
        metadata_artifact = runtime.artifacts.get(job.id, JobState.PUBLICATION_PREPARING, "metadata")
        assert metadata_artifact is not None
        metadata = json.loads(Path(metadata_artifact.path).read_text(encoding="utf-8"))
        assert "Music: Quiet Circuit acceptance bed" in metadata["description"]
        assert settings.pipeline.youtube.dry_run and not settings.pipeline.youtube.enabled

        smoke_root.mkdir(parents=True, exist_ok=True)
        accepted_video = smoke_root / "shorts_piper_1080x1920_smoke.mp4"
        temporary_video = accepted_video.with_suffix(".part.mp4")
        shutil.copyfile(final.path, temporary_video); temporary_video.replace(accepted_video)
        accepted_narration = smoke_root / "shorts_piper_1080x1920_smoke.wav"
        temporary_narration = accepted_narration.with_suffix(".part.wav")
        shutil.copyfile(narration.path, temporary_narration); temporary_narration.replace(accepted_narration)
        probe = _probe(accepted_video)
        video = next(stream for stream in probe["streams"] if stream.get("codec_type") == "video")
        assert (video["width"], video["height"]) == (1080, 1920)
        numerator, denominator = str(video["avg_frame_rate"]).split("/", 1)
        assert float(numerator) / float(denominator) == pytest.approx(30, abs=0.01)
        assert 30 <= float(probe["format"]["duration"]) <= 55
        narration_rms = _decoded_audio_rms(accepted_narration)
        mixed_rms = _decoded_audio_rms(accepted_video)
        audio_mix_ratio = mixed_rms / narration_rms
        assert narration_rms >= 10
        assert 0.75 <= audio_mix_ratio <= 1.35
        evidence = smoke_root / "shorts_piper_1080x1920_smoke.json"
        evidence.write_text(json.dumps({"probe": probe, "timing": timing["alignment"], "quality": quality, "visuals": assets["quality"], "music": render_record["inputs"]["music"], "audio": {"narration_rms": narration_rms, "mixed_rms": mixed_rms, "mixed_to_narration_ratio": audio_mix_ratio}, "publication_state": published.state}, indent=2, sort_keys=True, default=str), encoding="utf-8")
        contact_sheet = smoke_root / "shorts_piper_1080x1920_contact_sheet.png"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(accepted_video), "-vf", "fps=1/8,scale=270:480,tile=3x2", "-frames:v", "1", str(contact_sheet)], check=True, timeout=180)
    finally:
        runtime.database.dispose()
