"""One offline, migrated-database walk from a job through the M23 brief."""

from __future__ import annotations

import hashlib
import json
import wave
from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config

from tubeforge.core.config import AnalyticsConfig, DatabaseConfig, FakeProviderConfig, LearningConfig, OptimizationConfig, PerformanceConfig, PreviewRenderConfig, VoicePipelineConfig, YouTubePublishingConfig
from tubeforge.db.repositories import AnalyticsRepository, ApprovalRepository, ArtifactRepository, JobRepository, LearningRepository, OptimizationRepository, PublicationRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.states import ApprovalGate, JobState
from tubeforge.pipeline.learning import ChannelLearningService, ExperimentEvaluationService
from tubeforge.pipeline.optimization import OptimizationCandidateService, OptimizationExecutor, approval_identity
from tubeforge.pipeline.orchestrator import PipelineOrchestrator
from tubeforge.pipeline.performance import AnalyticsIngestionService, PerformanceService
from tubeforge.providers.fake import FakeContentProvider, FakeMediaProvider, FakePublisher, FakeVoiceProvider, FakeYouTubePublisher
from tubeforge.rendering.preview import checksum


class _Probe:
    def inspect(self, path: Path) -> dict[str, object]:
        with wave.open(str(path), "rb") as stream:
            return {"duration_seconds": stream.getnframes() / stream.getframerate(), "streams": []}


class _Assembler:
    def assemble(self, inputs: tuple[Path, ...], output: Path, *, pause_seconds: float = 0.0) -> None:
        with wave.open(str(inputs[0]), "rb") as source:
            parameters = source.getparams()
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as target:
            target.setparams(parameters)
            for path in inputs:
                with wave.open(str(path), "rb") as source:
                    target.writeframes(source.readframes(source.getnframes()))


class _Renderer:
    """Portable rendering boundary used only because this host has no FFmpeg."""

    def __init__(self) -> None:
        self.config = PreviewRenderConfig(minimum_free_bytes=1)
        self.template_version = "integration-fake-renderer-v1"

    def identity(self, segments, narration, captions, *, approval_identity=None) -> str:
        return hashlib.sha256(f"{approval_identity}|{narration}|{captions}".encode()).hexdigest()

    def validate(self, path: Path, expected: float) -> dict[str, object]:
        assert path.is_file() and path.stat().st_size
        return {"duration_seconds": expected, "width": self.config.width, "height": self.config.height, "fps": self.config.fps, "video_codec": "h264", "audio_codec": "aac"}

    def render(self, segments, narration, captions, output: Path, *, cancellation_requested=None) -> dict[str, object]:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"offline-rendered-video")
        return {"command": ["offline-renderer", str(output)], "metadata": self.validate(output, segments[-1].end_seconds), "checksum_sha256": checksum(output)}


def _migrate(database_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{database_path}"])
    command.upgrade(config, "head")


def _request() -> ContentRequest:
    return ContentRequest(topic="Rain", angle="A 30-second offline explainer", target_duration_seconds=30, language="en-IN", audience="general", prompt_version="integration-v1", sources=(SourceReference(source_id="rain-source", url="https://example.invalid/rain", title="Rain"),))


def _metrics(views: int) -> dict[str, dict[str, object]]:
    available = lambda value: {"value": value, "availability": "available"}
    return {"views": available(views), "estimatedMinutesWatched": available(views), "averageViewDuration": available(30), "averageViewPercentage": available(60), "impressions": available(2_000), "impressionsClickThroughRate": available(2.0), "likes": available(max(1, views // 10)), "comments": available(1), "subscribersGained": available(1), "subscribersLost": available(0)}


def test_migrated_offline_job_reaches_m23_brief_and_resumes(tmp_path: Path) -> None:
    database_path = tmp_path / "integration.db"
    _migrate(database_path)
    database = create_database(DatabaseConfig(url=f"sqlite:///{database_path}"))
    try:
        settings = FakeProviderConfig(artifact_root=tmp_path / "providers")
        jobs, artifacts, approvals = JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory)
        runner = PipelineOrchestrator(jobs, artifacts, approvals, FakeContentProvider(), FakeMediaProvider(settings), FakeVoiceProvider(settings), FakePublisher(), tmp_path / "artifacts", voice_config=VoicePipelineConfig(), audio_assembler=_Assembler(), ffprobe=_Probe(), preview_renderer=_Renderer(), final_renderer=_Renderer())
        job_id = "offline-e2e"
        jobs.create(job_id, _request())
        assert runner.run(job_id).state is JobState.SCRIPT_APPROVAL_REQUIRED
        approvals.record("script", job_id, ApprovalGate.SCRIPT, actor="integration")
        assert runner.run(job_id).state is JobState.PREVIEW_READY
        preview = runner._required_json(job_id, JobState.PREVIEW_RENDERING, "preview_manifest")
        approvals.record("preview", job_id, ApprovalGate.PREVIEW, reviewed_identity=preview["render_identity"], actor="integration")
        assert runner.run(job_id).state is JobState.FINAL_READY
        assert runner.run(job_id).state is JobState.PUBLICATION_APPROVAL_REQUIRED
        package = runner._required_json(job_id, JobState.PUBLICATION_PREPARING, "publication_package")
        thumbnail = runner._required_artifact(job_id, JobState.PUBLICATION_PREPARING, "thumbnail")
        assert Path(thumbnail.path).is_file() and Path(thumbnail.path).stat().st_size > 0
        approvals.record("publication", job_id, ApprovalGate.PUBLICATION_PREPARATION, reviewed_identity=package["publication_identity"], actor="integration")
        assert runner.run(job_id).state is JobState.PUBLICATION_READY

        # M13's real orchestration remains dry-run: it must make no provider mutation.
        youtube = FakeYouTubePublisher()
        runner.publisher = youtube
        runner.youtube_config = YouTubePublishingConfig(enabled=True, dry_run=True, client_secret_path=tmp_path / "client.json", token_storage_path=tmp_path / "token.json", expected_channel_id="fake-channel")
        publication_id = hashlib.sha256(b"offline-publication").hexdigest()
        approvals.record("publish", job_id, ApprovalGate.PUBLISH, reviewed_identity=publication_id, actor="integration")
        assert runner.run(job_id).state is JobState.PUBLICATION_READY
        assert youtube.create_calls == youtube.metadata_calls == youtube.thumbnail_calls == 0

        # Continue the post-publication loop through real repositories and services.
        publications = PublicationRepository(database.session_factory)
        publications.ensure(job_id, publication_id, str(package["publication_identity"]), "fake-channel", {"integration": True})
        publications.update(publication_id, state="healthy", remote_video_id="offline-video", created_at=datetime.now(UTC) - timedelta(days=4))
        youtube.videos["offline-video"] = {"privacy": "private", "title": str(package["metadata"]["title"]), "description": str(package["metadata"]["description"]), "tags": tuple(package["metadata"]["tags"]), "analytics": _metrics(500)}
        health, _, _ = runner._publication_health(package, datetime.now(UTC), youtube.fetch_publication_snapshot("offline-video"))
        assert health == "healthy"

        analytics, optimization, learning = AnalyticsRepository(database.session_factory), OptimizationRepository(database.session_factory), LearningRepository(database.session_factory)
        baseline = AnalyticsIngestionService(publications, analytics, youtube, AnalyticsConfig(initial_delay_hours=0)).collect(publication_id)
        assert baseline is not None and baseline.views == 500
        evaluation = PerformanceService(publications, analytics, PerformanceConfig(min_views_for_retention=1, min_impressions_for_ctr=1)).evaluate(publication_id)
        assert evaluation is not None
        proposal = analytics.proposal(hashlib.sha256(json.dumps({"evaluation": evaluation.evaluation_identity, "action": "TITLE_AND_THUMBNAIL", "version": "m16-proposal-v1"}, sort_keys=True, separators=(",", ":")).encode()).hexdigest())
        assert proposal is not None
        candidate = OptimizationCandidateService(publications, analytics, optimization, OptimizationConfig(), runner.publication_config, tmp_path.parents[1] / "o").generate(proposal.proposal_identity, current_title=str(package["metadata"]["title"]))[0]
        optimization.select(candidate.candidate_identity)
        binding = approval_identity(publication=publication_id, candidate=candidate.candidate_identity, proposal=proposal.proposal_identity, evaluation=evaluation.evaluation_identity, remote_video="offline-video", expected_title=str(package["metadata"]["title"]), executor_version="m18-v1")
        approvals.record("optimization", job_id, ApprovalGate.OPTIMIZATION, reviewed_identity=binding, actor="integration")
        assert OptimizationExecutor(publications, analytics, optimization, approvals, youtube, OptimizationConfig()).execute(candidate.candidate_identity).state == "DRY_RUN"
        applied = OptimizationExecutor(publications, analytics, optimization, approvals, youtube, OptimizationConfig.model_validate({"execution": {"enabled": True, "dry_run": False}})).execute(candidate.candidate_identity)
        assert applied is not None and applied.state == "APPLIED" and youtube.create_calls == 0

        youtube.videos["offline-video"]["analytics"] = _metrics(1_500)
        assert AnalyticsIngestionService(publications, analytics, youtube, AnalyticsConfig(initial_delay_hours=0)).collect(publication_id, now=datetime.now(UTC) + timedelta(days=1)) is not None
        outcome = ExperimentEvaluationService(analytics, optimization, publications, learning, LearningConfig(minimum_post_hours=1, minimum_views=1)).evaluate(applied.execution_identity, now=datetime.now(UTC) + timedelta(days=2))
        assert outcome is not None
        channel = ChannelLearningService(analytics, learning, LearningConfig(minimum_history_videos=1))
        assert channel.recommend("fake-channel")
        brief = channel.brief("fake-channel")
        assert json.loads(brief.recommendation_identities_json) and jobs.get(job_id).state is JobState.PUBLICATION_READY

        # Fresh objects against the same DB/artifact root prove durable checkpoints resume.
        restarted = PipelineOrchestrator(JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory), FakeContentProvider(), FakeMediaProvider(settings), FakeVoiceProvider(settings), FakePublisher(), tmp_path / "artifacts", voice_config=VoicePipelineConfig(), audio_assembler=_Assembler(), ffprobe=_Probe(), preview_renderer=_Renderer(), final_renderer=_Renderer())
        assert restarted.run(job_id).state is JobState.PUBLICATION_READY
    finally:
        database.dispose()
