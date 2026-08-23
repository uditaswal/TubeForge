"""A tiny real-FFmpeg acceptance test for the safe offline configuration."""

from __future__ import annotations

import shutil
from argparse import Namespace
from pathlib import Path
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.config import Config

from tubeforge.core.config import (
    AppConfig,
    DatabaseConfig,
    FakeProviderConfig,
    FinalRenderConfig,
    MediaPipelineConfig,
    PipelineConfig,
    PreviewRenderConfig,
    Settings,
    VoicePipelineConfig,
)
from tubeforge.core.runtime import create_runtime
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.states import ApprovalGate, JobState
from tubeforge.workers.service import WorkerService


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="requires local ffmpeg and ffprobe",
)


def _migrate(path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{path}"])
    command.upgrade(config, "head")


def test_fake_job_creates_a_playable_preview_and_final(tmp_path: Path) -> None:
    database_path = tmp_path / "pipeline.db"
    _migrate(database_path)
    settings = Settings(
        app=AppConfig(name="TubeForge acceptance", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{database_path}"),
        pipeline=PipelineConfig(
            fake=FakeProviderConfig(artifact_root=tmp_path / "fake"),
            voice=VoicePipelineConfig(artifact_root=tmp_path / "artifacts"),
            media=MediaPipelineConfig(cache_root=tmp_path / "cache", min_width=1, min_height=1),
            preview=PreviewRenderConfig(width=320, height=180, minimum_free_bytes=1, timeout_seconds=10),
            final=FinalRenderConfig(width=320, height=180, minimum_free_bytes=1, timeout_seconds=10),
        ),
    )
    runtime = create_runtime(settings)
    try:
        request = ContentRequest(
            topic="Rain",
            angle="A short offline explainer",
            target_duration_seconds=30,
            language="en-IN",
            audience="general",
            prompt_version="ffmpeg-acceptance-v1",
            sources=(SourceReference(source_id="rain", url="https://example.invalid/rain", title="Rain"),),
        )
        job = runtime.jobs.create("ffmpeg-e2e", request)
        # A deterministic clock makes lease ownership assertions independent of
        # SQLite's timezone text representation on Windows test hosts.
        worker = WorkerService(
            "ffmpeg-worker",
            runtime.jobs,
            runtime.orchestrator,
            settings.worker,
            clock=lambda: datetime(2026, 8, 23, tzinfo=UTC),
        )
        assert worker.run_once().state is JobState.SCRIPT_APPROVAL_REQUIRED
        runtime.approvals.record("script", job.id, ApprovalGate.SCRIPT, actor="test")
        second = worker.run_once()
        assert second is not None and second.state is JobState.PREVIEW_READY, second.failure_message if second else "no eligible job"
        preview_manifest = runtime.artifacts.get(job.id, JobState.PREVIEW_RENDERING, "preview_manifest")
        assert preview_manifest is not None
        import json

        preview_identity = json.loads(Path(preview_manifest.path).read_text(encoding="utf-8"))["render_identity"]
        runtime.approvals.record("preview", job.id, ApprovalGate.PREVIEW, actor="test", reviewed_identity=preview_identity)
        assert worker.run_once().state is JobState.FINAL_READY
        assert worker.run_once().state is JobState.PUBLICATION_APPROVAL_REQUIRED
        final = runtime.artifacts.get(job.id, JobState.FINAL_RENDERING, "final")
        assert final is not None and Path(final.path).is_file()
        timing = runtime.artifacts.get(job.id, JobState.VOICE_GENERATION, "timing_map")
        assert timing is not None
        expected = json.loads(Path(timing.path).read_text(encoding="utf-8"))["final_duration_seconds"]
        assert abs(expected - request.target_duration_seconds) <= request.target_duration_seconds * 0.20
        metadata = runtime.orchestrator.final_renderer.validate(Path(final.path), expected)
        assert metadata["width"] == 320 and metadata["height"] == 180
        assert metadata["audio_codec"] == "aac"
        assert abs(metadata["duration_seconds"] - request.target_duration_seconds) <= request.target_duration_seconds * 0.20
    finally:
        runtime.database.dispose()
