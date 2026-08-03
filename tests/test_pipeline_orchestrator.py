from __future__ import annotations

from pathlib import Path
import wave

import pytest

from tubeforge.core.config import DatabaseConfig, FakeProviderConfig, VoicePipelineConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.db.models import Base
from tubeforge.db.repositories import ApprovalRepository, ArtifactRepository, JobRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.domain.states import ApprovalGate, JobState
from tubeforge.pipeline.orchestrator import PipelineInterrupted, PipelineOrchestrator
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


def request() -> ContentRequest:
    return ContentRequest(topic="Rain", angle="A short explainer", target_duration_seconds=60, language="en-IN", audience="general", prompt_version="test-v1", sources=(SourceReference(source_id="source-1", url="https://example.invalid/rain", title="Rain"),))


@pytest.fixture
def pipeline(tmp_path: Path):
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'pipeline.db'}"))
    Base.metadata.create_all(database.engine)
    settings = FakeProviderConfig(artifact_root=tmp_path / "provider")
    content, media, voice, publisher = FakeContentProvider(), FakeMediaProvider(settings), FakeVoiceProvider(settings), FakePublisher()
    runner = PipelineOrchestrator(JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory), content, media, voice, publisher, tmp_path / "artifacts", voice_config=VoicePipelineConfig(pause_seconds=0.15), audio_assembler=OfflineAssembler(), ffprobe=OfflineProbe())
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
    assert runner.run("job-success").state is JobState.PREVIEW_APPROVAL_REQUIRED
    approve(runner, "job-success", ApprovalGate.PREVIEW)
    assert runner.run("job-success").state is JobState.PUBLISH_APPROVAL_REQUIRED
    approve(runner, "job-success", ApprovalGate.PUBLIC_PUBLISH)
    assert runner.run("job-success").state is JobState.PUBLISHED
    assert content.calls == media.calls == voice.calls == 1
    assert publisher.calls == 2
    assert runner.artifacts.get("job-success", JobState.PRIVATE_UPLOADING, "private_receipt")
    assert runner.artifacts.get("job-success", JobState.PUBLISH_APPROVAL_REQUIRED, "public_receipt")


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
    runner.run("job-duplicate"); approve(runner, "job-duplicate", ApprovalGate.PREVIEW)
    runner.run("job-duplicate")
    assert publisher.calls == 1
    runner.run("job-duplicate")
    assert content.calls == voice.calls == 1
    assert publisher.calls == 1


@pytest.mark.parametrize(("failure", "expected"), [(ProviderValidationError("bad output"), JobState.FAILED_VALIDATION), (RetryableProviderError("temporary"), JobState.FAILED_RETRYABLE), (ProviderAuthenticationError("expired"), JobState.AUTH_REQUIRED)])
def test_provider_failures_preserve_exact_stage_and_classification(tmp_path: Path, failure: Exception, expected: JobState) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'failure.db'}")); Base.metadata.create_all(database.engine)
    settings = FakeProviderConfig(artifact_root=tmp_path / "provider")
    runner = PipelineOrchestrator(JobRepository(database.session_factory), ArtifactRepository(database.session_factory), ApprovalRepository(database.session_factory), FakeContentProvider(failure), FakeMediaProvider(settings), FakeVoiceProvider(settings), FakePublisher(), tmp_path / "artifacts", audio_assembler=OfflineAssembler(), ffprobe=OfflineProbe())
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
    assert runner.run("job-gates").state is JobState.PREVIEW_APPROVAL_REQUIRED
    approve(runner, "job-gates", ApprovalGate.PREVIEW)
    assert runner.run("job-gates").state is JobState.PUBLISH_APPROVAL_REQUIRED
    assert runner.artifacts.get("job-gates", JobState.PUBLISH_APPROVAL_REQUIRED, "public_receipt") is None
