from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import wave

import pytest

from tubeforge.core.config import AppConfig, DatabaseConfig, FakeProviderConfig, PreviewRenderConfig, PublicationPreparationConfig, Settings, SourceClipConfig, VoicePipelineConfig, YouTubePublishingConfig
from tubeforge.core.errors import AmbiguousProviderError, ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.db.models import Base
from tubeforge.db.repositories import ApprovalRepository, ArtifactRepository, JobRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import AssetCandidate, ContentPackage, ContentRequest, SourceReference
from tubeforge.domain.states import ApprovalGate, ApprovalStatus, JobState
from tubeforge.pipeline.assets import AssetLimits
from tubeforge.pipeline.orchestrator import PipelineInterrupted, PipelineOrchestrator
from tubeforge.pipeline.sources import SourceSnapshot
from tubeforge.pipeline.publication import identity as publication_identity
from tubeforge.rendering.preview import checksum
from tubeforge.providers.fake import FakeContentProvider, FakeMediaProvider, FakePublisher, FakeVoiceProvider, FakeYouTubePublisher
from tubeforge.providers.media.router import VisualMediaProvider


class OfflineProbe:
    def inspect(self, path: Path) -> dict[str, object]:
        with wave.open(str(path), "rb") as stream:
            return {"duration_seconds": stream.getnframes() / stream.getframerate(), "streams": []}


class OfflineAssembler:
    def __init__(self) -> None:
        self.calls = 0

    def assemble(self, inputs: tuple[Path, ...], output: Path, *, pause_seconds: float = 0.0) -> None:
        self.calls += 1
        with wave.open(str(inputs[0]), "rb") as source:
            params = source.getparams()
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as target:
            target.setparams(params)
            for index, path in enumerate(inputs):
                with wave.open(str(path), "rb") as source:
                    target.writeframes(source.readframes(source.getnframes()))
                if index < len(inputs) - 1:
                    target.writeframes(b"\x00" * int(round(pause_seconds * params.framerate)) * params.nchannels * params.sampwidth)



class OfflineRenderer:
    def __init__(self) -> None:
        self.config = PreviewRenderConfig(minimum_free_bytes=1)
        self.template_version = "offline-renderer-v1"
        self.calls = 0

    def identity(self, segments, narration, captions, *, approval_identity=None):
        import hashlib
        return hashlib.sha256(("offline|" + str(approval_identity) + "|" + ",".join(item.asset_checksum for item in segments)).encode()).hexdigest()

    def validate(self, path: Path, expected: float) -> dict[str, object]:
        if not path.is_file() or path.stat().st_size == 0: raise ProviderValidationError("missing fake video")
        return {"duration_seconds": expected, "width": self.config.width, "height": self.config.height, "fps": self.config.fps, "video_codec": "h264", "audio_codec": "aac"}

    def render(self, segments, narration, captions, output: Path, *, cancellation_requested=None):
        if cancellation_requested and cancellation_requested(): raise RuntimeError("cancelled")
        self.calls += 1; output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(b"offline-video")
        return {"command": ["fake-ffmpeg", str(output)], "metadata": self.validate(output, segments[-1].end_seconds), "checksum_sha256": checksum(output)}


def request() -> ContentRequest:
    return ContentRequest(topic="Rain", angle="A short explainer", target_duration_seconds=60, language="en-IN", audience="general", prompt_version="test-v1", sources=(SourceReference(source_id="source-1", url="https://example.invalid/rain", title="Rain"),))


@pytest.fixture
def pipeline(tmp_path: Path):
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'pipeline.db'}"))
    Base.metadata.create_all(database.engine)
    settings = FakeProviderConfig(artifact_root=tmp_path / "provider")
    content, media, voice, publisher = FakeContentProvider(), FakeMediaProvider(settings), FakeVoiceProvider(settings), FakePublisher()
    runner = PipelineOrchestrator(JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory), content, media, voice, publisher, tmp_path / "artifacts", voice_config=VoicePipelineConfig(pause_seconds=0.15), audio_assembler=OfflineAssembler(), ffprobe=OfflineProbe(), preview_renderer=OfflineRenderer(), final_renderer=OfflineRenderer())
    try:
        yield runner, content, media, voice, publisher
    finally:
        database.dispose()


def approve(runner: PipelineOrchestrator, job_id: str, gate: ApprovalGate) -> None:
    runner.approvals.record(f"{job_id}-{gate.value}", job_id, gate)


def test_source_ingestion_checkpoints_snapshot_and_reuses_effective_request(pipeline) -> None:
    runner, content, *_ = pipeline

    class Ingestor:
        calls = 0

        def ingest(self, source: SourceReference) -> SourceSnapshot:
            self.calls += 1
            return SourceSnapshot(source.source_id, str(source.url), source.title, datetime.now(UTC), "b" * 64, "Verified evidence.", source.author)

    ingestor = Ingestor()
    runner.source_ingestor = ingestor  # type: ignore[assignment]
    runner.jobs.create("source-checkpoint", request())
    assert runner.run("source-checkpoint").state is JobState.SCRIPT_APPROVAL_REQUIRED
    packet = runner._required_json("source-checkpoint", JobState.CONTENT_GENERATING, "source_packet")
    effective = runner._required_json("source-checkpoint", JobState.CONTENT_GENERATING, "effective_content_request")
    assert packet["retrieval_mode"] == "fetched"
    assert effective["sources"][0]["excerpt"] == "Verified evidence."
    assert content.calls == ingestor.calls == 1
    assert runner.run("source-checkpoint").state is JobState.SCRIPT_APPROVAL_REQUIRED
    assert content.calls == ingestor.calls == 1


def test_source_clip_pipeline_reuses_source_checkpoint_and_prepares_publication(pipeline, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner, *_ = pipeline

    class Source:
        inspect_calls = 0
        acquire_calls = 0
        def can_handle(self, url: str) -> bool: return True
        def inspect(self, url: str) -> dict[str, object]:
            self.inspect_calls += 1
            return {"url": url, "id": "video-1", "uploader": "creator", "title": "A source", "duration_seconds": None, "webpage_url": url}
        def acquire(self, url: str, destination: Path, *, captions: bool = False) -> Path:
            self.acquire_calls += 1; destination.mkdir(parents=True, exist_ok=True)
            output = destination / "source.mp4"; output.write_bytes(b"source-media"); return output

    source = Source()
    runner.source_clips = SourceClipConfig(enabled=True, min_clip_seconds=5, max_clip_seconds=10)
    runner.source_provider = source  # type: ignore[assignment]
    def fake_audio(_ffmpeg: str, _source: Path, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(100); stream.writeframes(b"\xff\x7f" * 3000)
    def fake_render(_ffmpeg: str, _ffprobe: str, _source: Path, output: Path, _start: float, _end: float, captions: Path | None = None) -> dict[str, object]:
        output.parent.mkdir(parents=True, exist_ok=True); output.write_bytes(b"clip-media")
        return {"width": 1080, "height": 1920, "has_audio": True, "duration_seconds": 10.0}
    monkeypatch.setattr("tubeforge.pipeline.orchestrator.extract_audio", fake_audio)
    monkeypatch.setattr("tubeforge.pipeline.orchestrator.probe_clip", lambda *_args: {"duration_seconds": 30.0})
    monkeypatch.setattr("tubeforge.pipeline.orchestrator.render_vertical", fake_render)
    source_request = ContentRequest(topic="A source", angle="clips", target_duration_seconds=30, language="en", audience="general", prompt_version="source-clip-v1", sources=(SourceReference(source_id="source-video", url="https://example.com/video", title="A source"),), review_mode="auto", captions_enabled=False, production_mode="source_clip", source_url="https://example.com/video", clip_count=1)
    runner.jobs.create("source-clip", source_request)
    assert runner.run("source-clip").state is JobState.FINAL_READY
    assert source.inspect_calls == source.acquire_calls == 1
    assert runner.artifacts.get("source-clip", JobState.CLIP_RENDERING, "clip_001")
    assert runner.run("source-clip").state is JobState.PUBLICATION_APPROVAL_REQUIRED
    saved_source = runner.source_media.get("source-clip")
    assert saved_source and saved_source.external_id == "video-1" and saved_source.duration_seconds == 30.0
    assert runner.run("source-clip").state is JobState.PUBLICATION_APPROVAL_REQUIRED
    assert source.inspect_calls == source.acquire_calls == 1


def test_successful_orchestration_persists_every_checkpoint(pipeline) -> None:
    runner, content, media, voice, publisher = pipeline
    runner.jobs.create("job-success", request())
    assert runner.run("job-success").state is JobState.SCRIPT_APPROVAL_REQUIRED
    approve(runner, "job-success", ApprovalGate.SCRIPT)
    assert runner.run("job-success").state is JobState.PREVIEW_READY
    preview = runner._required_json("job-success", JobState.PREVIEW_RENDERING, "preview_manifest")
    runner.approvals.record("job-success-preview", "job-success", ApprovalGate.PREVIEW, reviewed_identity=preview["render_identity"])
    assert runner.run("job-success").state is JobState.FINAL_READY
    # Content is generated once and narration is assembled once.  Media is
    # selected once per scene, preserving distinct scene visuals and the
    # asset-checkpoint contract.
    assert content.calls == 1
    # Voice synthesis is intentionally per timed phrase, not per job.
    assert voice.calls > 0
    assert media.calls == 3
    assert publisher.calls == 0
    assert runner.artifacts.get("job-success", JobState.FINAL_RENDERING, "final")
    assert runner._required_json("job-success", JobState.FINAL_READY, "quality_report")["passed"] is True


def test_interruption_resumes_from_last_checkpoint_without_regeneration(pipeline) -> None:
    runner, content, *_ = pipeline
    runner.jobs.create("job-resume", request())
    with pytest.raises(PipelineInterrupted):
        runner.run("job-resume", interrupt_after=JobState.CONTENT_READY)
    assert runner.jobs.get("job-resume").state is JobState.CONTENT_READY
    assert content.calls == 1
    assert runner.run("job-resume").state is JobState.SCRIPT_APPROVAL_REQUIRED
    assert content.calls == 1


@pytest.mark.parametrize("duration", (float("nan"), float("inf"), float("-inf"), 0.0, -1.0))
def test_voice_checkpoint_rejects_nonfinite_or_nonpositive_duration(
    pipeline, tmp_path: Path, duration: float
) -> None:
    runner, *_ = pipeline
    phrase = tmp_path / "persisted-phrase.wav"
    phrase.write_bytes(b"persisted-audio")
    result = {
        "artifact_path": str(phrase),
        "checksum_sha256": runner._checksum(phrase),
        "duration_seconds": duration,
    }

    assert not runner._result_is_valid(result)


def test_rejected_script_can_be_locally_revised_and_reapproved(pipeline) -> None:
    runner, content, *_ = pipeline
    job_id = "script-revision"
    runner.jobs.create(job_id, request())
    assert runner.run(job_id).state is JobState.SCRIPT_APPROVAL_REQUIRED
    runner.approvals.record("script-revision-rejected", job_id, ApprovalGate.SCRIPT, ApprovalStatus.REJECTED)
    original = runner._required_json(job_id, JobState.CONTENT_GENERATING, "content_package")
    original["script_sections"][0]["narration"] = original["script_sections"][0]["narration"].replace("offline", "revised", 1)
    revised = ContentPackage.model_validate(original)
    artifact = runner._replace_json(job_id, JobState.CONTENT_GENERATING, "content_package", revised.model_dump(mode="json"))
    runner.approvals.record("script-revision-approved", job_id, ApprovalGate.SCRIPT, reviewed_identity=artifact.checksum_sha256)
    assert runner.run(job_id).state is JobState.PREVIEW_READY
    assert content.calls == 1


def test_duplicate_execution_reuses_checkpoint_and_upload_receipt(pipeline) -> None:
    runner, content, _, voice, publisher = pipeline
    runner.jobs.create("job-duplicate", request())
    runner.run("job-duplicate"); approve(runner, "job-duplicate", ApprovalGate.SCRIPT)
    runner.run("job-duplicate"); preview = runner._required_json("job-duplicate", JobState.PREVIEW_RENDERING, "preview_manifest"); runner.approvals.record("job-duplicate-preview", "job-duplicate", ApprovalGate.PREVIEW, reviewed_identity=preview["render_identity"])
    runner.run("job-duplicate")
    assert publisher.calls == 0
    voice_calls = voice.calls
    runner.run("job-duplicate")
    assert content.calls == 1
    assert voice.calls == voice_calls
    assert publisher.calls == 0


def test_renderer_template_version_invalidates_preview_checkpoint(pipeline) -> None:
    runner, *_ = pipeline
    runner.jobs.create("job-renderer-version", request())
    runner.run("job-renderer-version"); approve(runner, "job-renderer-version", ApprovalGate.SCRIPT)
    assert runner.run("job-renderer-version").state is JobState.PREVIEW_READY
    old_manifest = runner._required_json("job-renderer-version", JobState.PREVIEW_RENDERING, "preview_manifest")
    calls = runner.preview_renderer.calls
    runner.preview_renderer.template_version = "offline-renderer-v2"
    assert runner.run("job-renderer-version").state is JobState.PREVIEW_READY
    refreshed = runner._required_json("job-renderer-version", JobState.PREVIEW_RENDERING, "preview_manifest")
    assert runner.preview_renderer.calls == calls + 1
    assert refreshed["render_identity"] != old_manifest["render_identity"]
    assert refreshed["renderer_template_version"] == "offline-renderer-v2"
    assert refreshed["probe"]["video_codec"] == "h264"
    assert refreshed["probe"]["audio_codec"] == "aac"
    assert refreshed["probe"]["fps"] == 30
    assert refreshed["probe"]["width"] == 854
    assert refreshed["probe"]["height"] == 480
    assert refreshed["probe"]["duration_seconds"] > 0


@pytest.mark.parametrize(("failure", "expected"), [(ProviderValidationError("bad output"), JobState.FAILED_VALIDATION), (RetryableProviderError("temporary"), JobState.FAILED_RETRYABLE), (ProviderAuthenticationError("expired"), JobState.AUTH_REQUIRED)])
def test_provider_failures_preserve_exact_stage_and_classification(tmp_path: Path, failure: Exception, expected: JobState) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'failure.db'}")); Base.metadata.create_all(database.engine)
    settings = FakeProviderConfig(artifact_root=tmp_path / "provider")
    runner = PipelineOrchestrator(JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory), FakeContentProvider(failure), FakeMediaProvider(settings), FakeVoiceProvider(settings), FakePublisher(), tmp_path / "artifacts", audio_assembler=OfflineAssembler(), ffprobe=OfflineProbe(), preview_renderer=OfflineRenderer(), final_renderer=OfflineRenderer())
    try:
        runner.jobs.create("job-failure", request())
        result = runner.run("job-failure")
        assert result.state is expected and result.resume_state is JobState.CONTENT_GENERATING
    finally:
        database.dispose()


def test_validation_and_auth_recovery_require_explicit_resolution(pipeline) -> None:
    runner, content, *_ = pipeline
    content.failure = ProviderValidationError("invalid")
    runner.jobs.create("job-recovery", request())
    assert runner.run("job-recovery").state is JobState.FAILED_VALIDATION
    with pytest.raises(Exception, match="operator resolution"):
        runner.run("job-recovery")
    content.failure = None
    assert runner.run("job-recovery", operator_resolved=True).state is JobState.SCRIPT_APPROVAL_REQUIRED


def test_all_approval_gates_fail_closed(pipeline) -> None:
    runner, *rest = pipeline
    runner.jobs.create("job-gates", request())
    assert runner.run("job-gates").state is JobState.SCRIPT_APPROVAL_REQUIRED
    approve(runner, "job-gates", ApprovalGate.SCRIPT)
    assert runner.run("job-gates").state is JobState.PREVIEW_READY
    preview = runner._required_json("job-gates", JobState.PREVIEW_RENDERING, "preview_manifest"); runner.approvals.record("job-gates-preview", "job-gates", ApprovalGate.PREVIEW, reviewed_identity=preview["render_identity"])
    assert runner.run("job-gates").state is JobState.FINAL_READY
    assert runner.artifacts.get("job-gates", JobState.FINAL_READY, "public_receipt") is None


@pytest.mark.parametrize("change", ["narration", "captions", "timing", "asset", "deleted_preview", "tampered_preview"])
def test_stale_preview_inputs_require_a_new_preview_approval(pipeline, change: str) -> None:
    runner, *_ = pipeline
    job_id = f"stale-{change}"
    runner.jobs.create(job_id, request())
    runner.run(job_id); approve(runner, job_id, ApprovalGate.SCRIPT)
    assert runner.run(job_id).state is JobState.PREVIEW_READY
    old_manifest = runner._required_json(job_id, JobState.PREVIEW_RENDERING, "preview_manifest")
    runner.approvals.record(f"{job_id}-preview", job_id, ApprovalGate.PREVIEW, reviewed_identity=old_manifest["render_identity"])

    if change == "narration":
        artifact = runner._required_artifact(job_id, JobState.VOICE_GENERATION, "narration")
        path = Path(artifact.path); path.write_bytes(path.read_bytes() + b"changed")
        runner._save_file(job_id, JobState.VOICE_GENERATION, "narration", path, artifact.provenance)
    elif change == "captions":
        artifact = runner._required_artifact(job_id, JobState.CAPTION_GENERATION, "captions")
        path = Path(artifact.path); path.write_bytes(path.read_bytes() + b"\nNOTE changed\n")
        runner._save_file(job_id, JobState.CAPTION_GENERATION, "captions", path, artifact.provenance)
    elif change == "timing":
        timing = runner._required_json(job_id, JobState.VOICE_GENERATION, "timing_map")
        timing["review_marker"] = "changed"
        runner._replace_json(job_id, JobState.VOICE_GENERATION, "timing_map", timing)
    elif change == "asset":
        manifest = runner._required_json(job_id, JobState.ASSET_ACQUISITION, "asset_manifest")
        asset = manifest["scenes"]["scene-1"]
        path = Path(asset["path"]); path.write_bytes(path.read_bytes() + b"changed")
        asset["checksum_sha256"] = runner._checksum(path)
        asset["validation"]["checksum_sha256"] = asset["checksum_sha256"]
        runner._replace_json(job_id, JobState.ASSET_ACQUISITION, "asset_manifest", manifest)
    else:
        preview = runner._required_artifact(job_id, JobState.PREVIEW_RENDERING, "preview")
        path = Path(preview.path)
        if change == "deleted_preview": path.unlink()
        else: path.write_bytes(b"tampered-preview")

    state = runner.run(job_id).state
    if change == "asset":
        # A byte-level asset mutation cannot be rendered into a fresh preview:
        # the acquisition provenance must remain safe and decodable.
        assert state is JobState.FAILED_VALIDATION
        return
    assert state is JobState.PREVIEW_READY
    refreshed = runner._required_json(job_id, JobState.PREVIEW_RENDERING, "preview_manifest")
    assert refreshed["render_identity"] != old_manifest["render_identity"]
    assert runner.run(job_id).state is JobState.PREVIEW_READY
    runner.approvals.record(f"{job_id}-new-preview", job_id, ApprovalGate.PREVIEW, reviewed_identity=refreshed["render_identity"])
    assert runner.run(job_id).state is JobState.FINAL_READY


def test_explicit_render_profiles_reach_default_renderers(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'profiles.db'}")); Base.metadata.create_all(database.engine)
    settings = FakeProviderConfig(artifact_root=tmp_path / "provider")
    app_settings = Settings(
        app=AppConfig(name="test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'profiles.db'}"),
        pipeline={"fake": {"artifact_root": str(tmp_path / "provider")}, "voice": {"artifact_root": str(tmp_path / "artifacts")}, "preview": {"width": 1280, "height": 720}, "final": {"width": 1280, "height": 720}},
    )
    runner = PipelineOrchestrator.from_settings(
        app_settings, JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory),
        FakeContentProvider(), FakeMediaProvider(settings), FakeVoiceProvider(settings), FakePublisher(),
    )
    try:
        assert runner.preview_renderer.config.width == 1280
        assert runner.final_renderer.config.width == 1280
    finally:
        database.dispose()


def test_shorts_pipeline_checkpoints_word_alignment_and_highlighted_captions(pipeline) -> None:
    runner, *_ = pipeline
    portrait_preview = OfflineRenderer()
    runner.shorts_preview_renderer = portrait_preview  # type: ignore[assignment]
    # The silent fake voice intentionally uses a slower synthetic pace than
    # the measured Piper model used by the real Shorts acceptance test.
    runner.voice_config = runner.voice_config.model_copy(update={"target_duration_tolerance_ratio": 0.5})
    job_id = "shorts-alignment"
    short_request = request().model_copy(update={"target_duration_seconds": 45, "preset_name": "shorts", "aspect_ratio": "9:16"})
    runner.jobs.create(job_id, short_request)

    assert runner.run(job_id).state is JobState.SCRIPT_APPROVAL_REQUIRED
    approve(runner, job_id, ApprovalGate.SCRIPT)
    result = runner.run(job_id)
    assert result.state is JobState.PREVIEW_READY, result.failure_message

    timing = runner._required_json(job_id, JobState.VOICE_GENERATION, "timing_map")
    captions = runner._required_artifact(job_id, JobState.CAPTION_GENERATION, "captions")
    plan = runner._required_json(job_id, JobState.CONTENT_GENERATING, "video_plan")
    assert timing["alignment"]["provider"] == "local-waveform-v1"
    assert timing["alignment"]["verified"] and timing["alignment"]["first_word_seconds"] <= 3
    assert timing["words"] and timing["words"][-1]["end_seconds"] == pytest.approx(timing["final_duration_seconds"])
    assert Path(captions.path).suffix == ".ass"
    caption_text = Path(captions.path).read_text(encoding="utf-8")
    assert "PlayResX: 1080" in caption_text and "Dialogue:" in caption_text
    assert plan["aspect_ratio"] == "9:16"
    assert portrait_preview.calls == 1

def test_assets_stage_acquires_validated_fake_asset_and_reuses_checkpoint(tmp_path: Path) -> None:
    from tubeforge.db.repositories import AssetCacheRepository
    from tubeforge.pipeline.assets import AssetAcquisitionService, AssetDownloader, AssetLimits
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'assets.db'}")); Base.metadata.create_all(database.engine)
    settings = FakeProviderConfig(artifact_root=tmp_path / "provider")
    media = FakeMediaProvider(settings)
    runner = PipelineOrchestrator(JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory), FakeContentProvider(), media, FakeVoiceProvider(settings), FakePublisher(), tmp_path / "artifacts", audio_assembler=OfflineAssembler(), ffprobe=OfflineProbe(), preview_renderer=OfflineRenderer(), final_renderer=OfflineRenderer(), asset_acquirer=AssetAcquisitionService(AssetCacheRepository(database.session_factory), AssetDownloader(tmp_path / "cache", AssetLimits(frozenset({"example.invalid"}), frozenset({"CC0-1.0"})))))
    try:
        runner.jobs.create("job-assets", request())
        assert runner.run("job-assets").state is JobState.SCRIPT_APPROVAL_REQUIRED
        approve(runner, "job-assets", ApprovalGate.SCRIPT)
        assert runner.run("job-assets").state is JobState.PREVIEW_READY
        manifest = runner._required_json("job-assets", JobState.ASSET_ACQUISITION, "asset_manifest")
        accepted = manifest["scenes"]["scene-1"]
        assert Path(accepted["path"]).is_file() and accepted["validation"]["media_type"] == "image"
        assert accepted["request"]["visual_source"] == "generated"
        assert accepted["visual_route"]["strategy"] == "generated_still"
        assert runner._required_json("job-assets", JobState.ASSET_ACQUISITION, "license_manifest")["assets"][0]["provider_asset_id"].startswith("fake-")
        calls = media.calls
        runner.run("job-assets")
        assert media.calls == calls
    finally:
        database.dispose()


def test_stock_asset_shortage_falls_back_to_local_cc0_art_with_provenance(tmp_path: Path) -> None:
    from tubeforge.db.repositories import AssetCacheRepository
    from tubeforge.pipeline.assets import AssetAcquisitionService, AssetDownloader

    class EmptyStock:
        def search(self, _request):
            return []

    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'stock-fallback.db'}")); Base.metadata.create_all(database.engine)
    settings = FakeProviderConfig(artifact_root=tmp_path / "provider")
    media = VisualMediaProvider(FakeMediaProvider(settings), EmptyStock())
    limits = AssetLimits(frozenset({"example.invalid"}), frozenset({"CC0-1.0"}))
    runner = PipelineOrchestrator(JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory), FakeContentProvider(), media, FakeVoiceProvider(settings), FakePublisher(), tmp_path / "artifacts", audio_assembler=OfflineAssembler(), ffprobe=OfflineProbe(), preview_renderer=OfflineRenderer(), final_renderer=OfflineRenderer(), asset_limits=limits, asset_acquirer=AssetAcquisitionService(AssetCacheRepository(database.session_factory), AssetDownloader(tmp_path / "cache", limits)))
    try:
        runner.jobs.create("stock-fallback", request().model_copy(update={"visual_source": "stock"}))
        assert runner.run("stock-fallback").state is JobState.SCRIPT_APPROVAL_REQUIRED
        approve(runner, "stock-fallback", ApprovalGate.SCRIPT)
        assert runner.run("stock-fallback").state is JobState.PREVIEW_READY
        accepted = runner._required_json("stock-fallback", JobState.ASSET_ACQUISITION, "asset_manifest")["scenes"]["scene-1"]
        assert accepted["request"]["visual_source"] == "stock"
        assert accepted["resolved_request"]["visual_source"] == "generated"
        assert accepted["visual_route"]["strategy"] == "generated_still"
        assert accepted["fallback"]["to"] == "local generated CC0 scene art"
        assert accepted["candidate"]["license_name"] == "CC0-1.0"
    finally:
        database.dispose()


def test_stock_search_outage_falls_back_to_local_cc0_art_with_provenance(tmp_path: Path) -> None:
    from tubeforge.db.repositories import AssetCacheRepository
    from tubeforge.pipeline.assets import AssetAcquisitionService, AssetDownloader

    class UnavailableStock:
        def search(self, _request):
            raise RetryableProviderError("Wikimedia search unavailable")

    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'stock-outage-fallback.db'}")); Base.metadata.create_all(database.engine)
    settings = FakeProviderConfig(artifact_root=tmp_path / "provider")
    media = VisualMediaProvider(FakeMediaProvider(settings), UnavailableStock())
    limits = AssetLimits(frozenset({"example.invalid"}), frozenset({"CC0-1.0"}))
    runner = PipelineOrchestrator(JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory), FakeContentProvider(), media, FakeVoiceProvider(settings), FakePublisher(), tmp_path / "artifacts", audio_assembler=OfflineAssembler(), ffprobe=OfflineProbe(), preview_renderer=OfflineRenderer(), final_renderer=OfflineRenderer(), asset_limits=limits, asset_acquirer=AssetAcquisitionService(AssetCacheRepository(database.session_factory), AssetDownloader(tmp_path / "cache", limits)))
    try:
        runner.jobs.create("stock-outage-fallback", request().model_copy(update={"visual_source": "stock"}))
        assert runner.run("stock-outage-fallback").state is JobState.SCRIPT_APPROVAL_REQUIRED
        approve(runner, "stock-outage-fallback", ApprovalGate.SCRIPT)
        assert runner.run("stock-outage-fallback").state is JobState.PREVIEW_READY
        accepted = runner._required_json("stock-outage-fallback", JobState.ASSET_ACQUISITION, "asset_manifest")["scenes"]["scene-1"]
        assert accepted["fallback"]["reason"] == "Wikimedia search unavailable"
        assert accepted["resolved_request"]["visual_source"] == "generated"
        assert accepted["candidate"]["license_name"] == "CC0-1.0"
    finally:
        database.dispose()

def test_assets_cancellation_before_checkpoint_preserves_cache(tmp_path: Path) -> None:
    from tubeforge.db.repositories import AssetCacheRepository
    from tubeforge.pipeline.assets import AssetAcquisitionService, AssetDownloader, AssetLimits
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'cancel.db'}")); Base.metadata.create_all(database.engine)
    settings = FakeProviderConfig(artifact_root=tmp_path / "provider")
    runner = PipelineOrchestrator(JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory), FakeContentProvider(), FakeMediaProvider(settings), FakeVoiceProvider(settings), FakePublisher(), tmp_path / "artifacts", audio_assembler=OfflineAssembler(), ffprobe=OfflineProbe(), preview_renderer=OfflineRenderer(), final_renderer=OfflineRenderer(), asset_acquirer=AssetAcquisitionService(AssetCacheRepository(database.session_factory), AssetDownloader(tmp_path / "cache", AssetLimits(frozenset({"example.invalid"}), frozenset({"CC0-1.0"})))))
    try:
        runner.jobs.create("job-cancel-assets", request()); runner.run("job-cancel-assets"); approve(runner, "job-cancel-assets", ApprovalGate.SCRIPT)
        state = [False]
        def cancelled() -> bool:
            state[0] = True
            return state[0]
        assert runner.run("job-cancel-assets", cancellation_requested=cancelled).state is JobState.CANCELLED
        assert runner.artifacts.get("job-cancel-assets", JobState.ASSET_ACQUISITION, "asset_manifest") is None
    finally: database.dispose()

def test_persisted_assets_revalidate_current_policy_on_resume(pipeline) -> None:
    import struct
    import zlib
    from tubeforge.pipeline.assets import ASSET_VALIDATION_VERSION

    runner, *_ = pipeline
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    raster = (b"\0" + b"\x22\x66\xaa" * 2) * 2
    path = runner.artifact_root / "persisted.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raster)) + chunk(b"IEND", b""))
    checksum = runner._checksum(path)
    base = AssetCandidate(provider_asset_id="persisted", source_url="https://example.invalid/persisted.png", license_name="CC0-1.0", retrieved_at=datetime.now(UTC)).model_dump(mode="json")
    value = {"path": str(path), "checksum_sha256": checksum, "validation": {"checksum_sha256": checksum, "validation_version": ASSET_VALIDATION_VERSION, "media_type": "image", "width": 2, "height": 2}, "candidate": base}
    assert runner._accepted_asset_valid(value)
    value["validation"]["validation_version"] = "m8-v1"
    assert not runner._accepted_asset_valid(value)
    value["validation"]["validation_version"] = ASSET_VALIDATION_VERSION
    runner.asset_limits = AssetLimits(frozenset({"example.invalid"}), frozenset({"CC BY 4.0"}))
    assert not runner._accepted_asset_valid(value)
    runner.asset_limits = AssetLimits(frozenset({"example.invalid"}), frozenset({"CC0-1.0"}))
    value["candidate"]["review_required"] = True
    assert not runner._accepted_asset_valid(value)
    value["candidate"]["review_required"] = False
    value["candidate"]["attribution_required"] = True
    value["candidate"]["attribution_text"] = "Credit required"
    assert not runner._accepted_asset_valid(value)
    value["candidate"]["attribution_required"] = False
    value["candidate"]["attribution_text"] = None
    assert runner._accepted_asset_valid(value)
    original = path.read_bytes()
    path.write_bytes(original[:-8])
    value["checksum_sha256"] = runner._checksum(path)
    value["validation"]["checksum_sha256"] = value["checksum_sha256"]
    assert not runner._accepted_asset_valid(value)


def test_publication_preparation_is_local_resumable_and_requires_exact_approval(pipeline) -> None:
    runner, _, _, _, publisher = pipeline
    job_id = "publication-ready"
    runner.jobs.create(job_id, request())
    runner.run(job_id); approve(runner, job_id, ApprovalGate.SCRIPT)
    runner.run(job_id)
    preview = runner._required_json(job_id, JobState.PREVIEW_RENDERING, "preview_manifest")
    runner.approvals.record(f"{job_id}-preview", job_id, ApprovalGate.PREVIEW, reviewed_identity=preview["render_identity"])
    assert runner.run(job_id).state is JobState.FINAL_READY
    assert runner.run(job_id).state is JobState.PUBLICATION_APPROVAL_REQUIRED
    package = runner._required_json(job_id, JobState.PUBLICATION_PREPARING, "publication_package")
    metadata = runner._required_json(job_id, JobState.PUBLICATION_PREPARING, "metadata")
    thumbnail = runner._required_artifact(job_id, JobState.PUBLICATION_PREPARING, "thumbnail")
    assert metadata["title"] and metadata["provenance"]["template_version"] == "m12-metadata-v1"
    assert Path(thumbnail.path).is_file() and package["thumbnail"]["thumbnail_identity"]
    assert publisher.calls == 0
    runner.approvals.record(f"{job_id}-publication", job_id, ApprovalGate.PUBLICATION_PREPARATION, reviewed_identity=package["publication_identity"])
    assert runner.run(job_id).state is JobState.PUBLICATION_READY


def test_publication_template_versions_invalidate_independent_checkpoints(pipeline) -> None:
    runner, *_ = pipeline
    job_id = "publication-version"
    runner.jobs.create(job_id, request()); runner.run(job_id); approve(runner, job_id, ApprovalGate.SCRIPT); runner.run(job_id)
    preview = runner._required_json(job_id, JobState.PREVIEW_RENDERING, "preview_manifest")
    runner.approvals.record(f"{job_id}-preview", job_id, ApprovalGate.PREVIEW, reviewed_identity=preview["render_identity"])
    runner.run(job_id); assert runner.run(job_id).state is JobState.PUBLICATION_APPROVAL_REQUIRED
    old_metadata = runner._required_json(job_id, JobState.PUBLICATION_PREPARING, "metadata")
    old_thumbnail = runner._required_json(job_id, JobState.PUBLICATION_PREPARING, "thumbnail_provenance")
    runner.publication_config = PublicationPreparationConfig(metadata_template_version="m12-metadata-v2")
    runner.jobs.update_state(job_id, JobState.PUBLICATION_PREPARING)
    assert runner.run(job_id).state is JobState.PUBLICATION_APPROVAL_REQUIRED
    assert runner._required_json(job_id, JobState.PUBLICATION_PREPARING, "metadata")["metadata_identity"] != old_metadata["metadata_identity"]
    assert runner._required_json(job_id, JobState.PUBLICATION_PREPARING, "thumbnail_provenance")["thumbnail_identity"] == old_thumbnail["thumbnail_identity"]


def test_publication_thumbnail_cleanup_on_cancellation(pipeline) -> None:
    runner, *_ = pipeline
    job_id = "publication-cancel"
    runner.jobs.create(job_id, request()); runner.run(job_id); approve(runner, job_id, ApprovalGate.SCRIPT); runner.run(job_id)
    preview = runner._required_json(job_id, JobState.PREVIEW_RENDERING, "preview_manifest")
    runner.approvals.record(f"{job_id}-preview", job_id, ApprovalGate.PREVIEW, reviewed_identity=preview["render_identity"])
    runner.run(job_id)
    assert runner.run(job_id, cancellation_requested=lambda: True).state is JobState.CANCELLED
    assert not runner._artifact_path(job_id, "thumbnail.png.tmp").exists()


def _publication_ready_for_youtube(runner: PipelineOrchestrator, job_id: str) -> str:
    """Drive the local stages, then approve the exact M13 external intent."""
    runner.jobs.create(job_id, request()); runner.run(job_id); approve(runner, job_id, ApprovalGate.SCRIPT); runner.run(job_id)
    preview = runner._required_json(job_id, JobState.PREVIEW_RENDERING, "preview_manifest")
    runner.approvals.record(f"{job_id}-preview", job_id, ApprovalGate.PREVIEW, reviewed_identity=preview["render_identity"])
    runner.run(job_id); assert runner.run(job_id).state is JobState.PUBLICATION_APPROVAL_REQUIRED
    package = runner._required_json(job_id, JobState.PUBLICATION_PREPARING, "publication_package")
    runner.approvals.record(f"{job_id}-publication", job_id, ApprovalGate.PUBLICATION_PREPARATION, reviewed_identity=package["publication_identity"])
    assert runner.run(job_id).state is JobState.PUBLICATION_READY
    identity = publication_identity({"package_identity": package["publication_identity"], "channel_id": "fake-channel", "privacy": "private", "implementation_version": "m13-youtube-v1"})
    runner.approvals.record(f"{job_id}-publish", job_id, ApprovalGate.PUBLISH, reviewed_identity=identity)
    return identity


def _enable_fake_youtube(runner: PipelineOrchestrator, publisher: FakeYouTubePublisher, tmp_path: Path) -> None:
    runner.publisher = publisher
    runner.youtube_config = YouTubePublishingConfig(enabled=True, dry_run=False, client_secret_path=tmp_path / "client.json", token_storage_path=tmp_path / "token.json", expected_channel_id="fake-channel")


def test_youtube_success_and_restart_after_remote_id_never_create_twice(pipeline, tmp_path: Path) -> None:
    runner, *_ = pipeline; publisher = FakeYouTubePublisher(); _enable_fake_youtube(runner, publisher, tmp_path)
    identity = _publication_ready_for_youtube(runner, "youtube-restart")
    package_identity = str(runner._required_json("youtube-restart", JobState.PUBLICATION_PREPARING, "publication_package")["publication_identity"])
    record = runner.publications.ensure("youtube-restart", identity, package_identity, "fake-channel", {})
    remote_id = "persisted-video"; publisher.videos[remote_id] = {"privacy": "private"}
    runner.publications.update(identity, remote_video_id=remote_id, state="remote_created")
    assert runner.run("youtube-restart").state is JobState.PUBLICATION_VERIFICATION_PENDING
    assert runner.run("youtube-restart").state is JobState.PUBLISHED
    assert publisher.create_calls == 0 and publisher.metadata_calls == publisher.thumbnail_calls == 1


def test_ambiguous_creation_requires_reconciliation_and_never_recreates(pipeline, tmp_path: Path) -> None:
    runner, *_ = pipeline; publisher = FakeYouTubePublisher(outcomes={"create": [AmbiguousProviderError("unknown")]}); _enable_fake_youtube(runner, publisher, tmp_path)
    identity = _publication_ready_for_youtube(runner, "youtube-ambiguous")
    assert runner.run("youtube-ambiguous").state is JobState.FAILED_VALIDATION
    assert publisher.create_calls == 1
    assert runner.publications.get(identity).state == "creation_ambiguous"
    assert runner.run("youtube-ambiguous", operator_resolved=True).state is JobState.FAILED_VALIDATION
    assert publisher.create_calls == 1


def test_metadata_and_thumbnail_recovery_only_repeat_the_incomplete_mutation(pipeline, tmp_path: Path) -> None:
    runner, *_ = pipeline; publisher = FakeYouTubePublisher(outcomes={"metadata": [RetryableProviderError("temporary")], "thumbnail": [RetryableProviderError("temporary")]}); _enable_fake_youtube(runner, publisher, tmp_path)
    identity = _publication_ready_for_youtube(runner, "youtube-recover")
    assert runner.run("youtube-recover").state is JobState.FAILED_RETRYABLE
    assert publisher.create_calls == 1 and publisher.metadata_calls == 1 and publisher.thumbnail_calls == 0
    assert runner.publications.get(identity).remote_video_id
    assert runner.run("youtube-recover").state is JobState.FAILED_RETRYABLE
    assert publisher.create_calls == 1 and publisher.metadata_calls == 2 and publisher.thumbnail_calls == 1
    assert runner.run("youtube-recover").state is JobState.PUBLICATION_VERIFICATION_PENDING
    assert runner.run("youtube-recover").state is JobState.PUBLISHED
    assert publisher.create_calls == 1 and publisher.metadata_calls == 2 and publisher.thumbnail_calls == 2


def test_mutation_boundary_rechecks_channel_and_dry_run_has_no_mutations(pipeline, tmp_path: Path) -> None:
    runner, *_ = pipeline; publisher = FakeYouTubePublisher(); _enable_fake_youtube(runner, publisher, tmp_path)
    _publication_ready_for_youtube(runner, "youtube-channel-race")
    channels = iter(("fake-channel", "other-channel")); publisher.authenticated_channel_id = lambda: next(channels)  # type: ignore[method-assign]
    assert runner.run("youtube-channel-race").state is JobState.AUTH_REQUIRED
    assert publisher.create_calls == publisher.metadata_calls == publisher.thumbnail_calls == 0
    runner, *_ = pipeline; publisher = FakeYouTubePublisher(); runner.publisher = publisher
    runner.youtube_config = YouTubePublishingConfig(enabled=True, dry_run=True, client_secret_path=tmp_path / "client.json", token_storage_path=tmp_path / "token.json", expected_channel_id="fake-channel")
    _publication_ready_for_youtube(runner, "youtube-dry-run")
    assert runner.run("youtube-dry-run").state is JobState.PUBLICATION_READY
    assert publisher.create_calls == publisher.metadata_calls == publisher.thumbnail_calls == publisher.channel_lookup_calls == 0


def test_cancellation_after_remote_id_keeps_recovery_record_and_stops_followups(pipeline, tmp_path: Path) -> None:
    runner, *_ = pipeline; publisher = FakeYouTubePublisher(); _enable_fake_youtube(runner, publisher, tmp_path)
    identity = _publication_ready_for_youtube(runner, "youtube-cancel-after-create")
    cancelled = [False]; original = publisher.create_or_resume_video
    def create_then_cancel(*args, **kwargs):
        remote_id = original(*args, **kwargs); cancelled[0] = True; return remote_id
    publisher.create_or_resume_video = create_then_cancel  # type: ignore[method-assign]
    assert runner.run("youtube-cancel-after-create", cancellation_requested=lambda: cancelled[0]).state is JobState.CANCELLED
    record = runner.publications.get(identity)
    assert record is not None and record.remote_video_id and not record.metadata_applied and not record.thumbnail_applied
    assert publisher.create_calls == 1 and publisher.metadata_calls == publisher.thumbnail_calls == 0


def test_publishing_disabled_needs_no_authentication_or_provider_calls(pipeline) -> None:
    runner, *_ = pipeline; publisher = FakeYouTubePublisher(); runner.publisher = publisher
    _publication_ready_for_youtube(runner, "youtube-disabled")
    assert runner.run("youtube-disabled").state is JobState.PUBLICATION_READY
    assert publisher.create_calls == publisher.metadata_calls == publisher.thumbnail_calls == publisher.channel_lookup_calls == 0


def test_ownership_loss_during_content_generation_cannot_promote_checkpoint_or_state(pipeline) -> None:
    runner, *_ = pipeline
    job_id = "ownership-loss-content"
    runner.jobs.create(job_id, request())
    assert runner.jobs.claim_oldest_eligible("worker-a", now=datetime.now(UTC), lease_seconds=300)

    class LostLease:
        worker_id = "worker-a"
        clock = staticmethod(lambda: datetime.now(UTC))

        def __init__(self) -> None:
            self.calls = 0

        def __call__(self, *, force: bool = False) -> bool:
            self.calls += 1
            if self.calls == 4:
                runner.jobs.release_claim(job_id, self.worker_id)
                return False
            return True

    result = runner.run(job_id, ownership_check=LostLease())
    assert result.state is JobState.CONTENT_GENERATING
    assert runner.artifacts.get(job_id, JobState.CONTENT_GENERATING, "content_package") is None
