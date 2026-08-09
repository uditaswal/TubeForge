from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import wave

import pytest

from tubeforge.core.config import AppConfig, DatabaseConfig, FakeProviderConfig, PreviewRenderConfig, Settings, VoicePipelineConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.db.models import Base
from tubeforge.db.repositories import ApprovalRepository, ArtifactRepository, JobRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import AssetCandidate, ContentRequest, SourceReference
from tubeforge.domain.states import ApprovalGate, JobState
from tubeforge.pipeline.assets import AssetLimits
from tubeforge.pipeline.orchestrator import PipelineInterrupted, PipelineOrchestrator
from tubeforge.rendering.preview import checksum
from tubeforge.providers.fake import FakeContentProvider, FakeMediaProvider, FakePublisher, FakeVoiceProvider


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
        self.calls = 0

    def identity(self, segments, narration, captions, *, approval_identity=None):
        import hashlib
        return hashlib.sha256(("offline|" + str(approval_identity) + "|" + ",".join(item.asset_checksum for item in segments)).encode()).hexdigest()

    def validate(self, path: Path, expected: float) -> dict[str, object]:
        if not path.is_file() or path.stat().st_size == 0: raise ProviderValidationError("missing fake video")
        return {"duration_seconds": expected, "width": self.config.width, "height": self.config.height}

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


def test_successful_orchestration_persists_every_checkpoint(pipeline) -> None:
    runner, content, media, voice, publisher = pipeline
    runner.jobs.create("job-success", request())
    assert runner.run("job-success").state is JobState.SCRIPT_APPROVAL_REQUIRED
    approve(runner, "job-success", ApprovalGate.SCRIPT)
    assert runner.run("job-success").state is JobState.PREVIEW_READY
    preview = runner._required_json("job-success", JobState.PREVIEW_RENDERING, "preview_manifest")
    runner.approvals.record("job-success-preview", "job-success", ApprovalGate.PREVIEW, reviewed_identity=preview["render_identity"])
    assert runner.run("job-success").state is JobState.FINAL_READY
    assert content.calls == media.calls == voice.calls == 1
    assert publisher.calls == 0
    assert runner.artifacts.get("job-success", JobState.FINAL_RENDERING, "final")


def test_interruption_resumes_from_last_checkpoint_without_regeneration(pipeline) -> None:
    runner, content, *_ = pipeline
    runner.jobs.create("job-resume", request())
    with pytest.raises(PipelineInterrupted):
        runner.run("job-resume", interrupt_after=JobState.CONTENT_READY)
    assert runner.jobs.get("job-resume").state is JobState.CONTENT_READY
    assert content.calls == 1
    assert runner.run("job-resume").state is JobState.SCRIPT_APPROVAL_REQUIRED
    assert content.calls == 1


def test_duplicate_execution_reuses_checkpoint_and_upload_receipt(pipeline) -> None:
    runner, content, _, voice, publisher = pipeline
    runner.jobs.create("job-duplicate", request())
    runner.run("job-duplicate"); approve(runner, "job-duplicate", ApprovalGate.SCRIPT)
    runner.run("job-duplicate"); preview = runner._required_json("job-duplicate", JobState.PREVIEW_RENDERING, "preview_manifest"); runner.approvals.record("job-duplicate-preview", "job-duplicate", ApprovalGate.PREVIEW, reviewed_identity=preview["render_identity"])
    runner.run("job-duplicate")
    assert publisher.calls == 0
    runner.run("job-duplicate")
    assert content.calls == voice.calls == 1
    assert publisher.calls == 0


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

    assert runner.run(job_id).state is JobState.PREVIEW_READY
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
        assert runner._required_json("job-assets", JobState.ASSET_ACQUISITION, "license_manifest")["assets"][0]["provider_asset_id"].startswith("fake-")
        calls = media.calls
        runner.run("job-assets")
        assert media.calls == calls
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
    runner, *_ = pipeline
    path = Path(__file__)
    checksum = runner._checksum(path)
    base = AssetCandidate(provider_asset_id="persisted", source_url="https://example.invalid/persisted.png", license_name="CC0-1.0", retrieved_at=datetime.now(UTC)).model_dump(mode="json")
    value = {"path": str(path), "checksum_sha256": checksum, "validation": {"checksum_sha256": checksum, "validation_version": "m8-v1"}, "candidate": base}
    assert runner._accepted_asset_valid(value)
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
