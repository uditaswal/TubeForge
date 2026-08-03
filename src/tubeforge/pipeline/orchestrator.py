"""Checkpointed M4 pipeline runner with no worker, lease, or live integration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.core.state_machine import PipelineSnapshot, PipelineStateMachine
from tubeforge.db.repositories import ApprovalRepository, Artifact, ArtifactRepository, ExternalOperationRepository, JobRepository, PipelineJob
from tubeforge.domain.contracts import AssetSearchRequest, PublishPrivacy, PublishRequest, VoiceRequest
from tubeforge.domain.providers import ContentProvider, MediaProvider, Publisher, VoiceProvider
from tubeforge.domain.states import ApprovalGate, JobState


class PipelineInterrupted(RuntimeError):
    """Test-only interruption after a durable checkpoint has been written."""


class PipelineOrchestrator:
    """Run one job synchronously, committing only short persistence operations."""

    def __init__(self, jobs: JobRepository, artifacts: ArtifactRepository, approvals: ApprovalRepository, content: ContentProvider, media: MediaProvider, voice: VoiceProvider, publisher: Publisher, artifact_root: Path, external_operations: ExternalOperationRepository | None = None) -> None:
        self.jobs, self.artifacts, self.approvals = jobs, artifacts, approvals
        self.content, self.media, self.voice, self.publisher = content, media, voice, publisher
        self.artifact_root, self.machine = artifact_root, PipelineStateMachine()
        self.external_operations = external_operations

    def run(self, job_id: str, *, operator_resolved: bool = False, authentication_restored: bool = False, interrupt_after: JobState | None = None, cancellation_requested: Callable[[], bool] | None = None) -> PipelineJob:
        """Advance until an approval gate, terminal state, or classified failure."""
        while True:
            job = self.jobs.get(job_id)
            if job.state in {JobState.PUBLISHED, JobState.CANCELLED, JobState.FAILED_EXHAUSTED}:
                return job
            if cancellation_requested is not None and cancellation_requested():
                cancelled = self.machine.transition(PipelineSnapshot(job.state, job.resume_state), JobState.CANCELLED)
                return self.jobs.update_state(job.id, cancelled.state, cancelled.resume_state)
            if job.state in {JobState.FAILED_RETRYABLE, JobState.FAILED_VALIDATION, JobState.AUTH_REQUIRED}:
                target = job.resume_state
                assert target is not None
                self._transition(job, target, operator_resolved=operator_resolved, authentication_restored=authentication_restored)
                continue
            try:
                self._run_stage(job)
            except (RetryableProviderError, ProviderValidationError, ProviderAuthenticationError, ValidationError) as error:
                failure = JobState.AUTH_REQUIRED if isinstance(error, ProviderAuthenticationError) else JobState.FAILED_VALIDATION if isinstance(error, (ProviderValidationError, ValidationError)) else JobState.FAILED_RETRYABLE
                failed = self.machine.transition(PipelineSnapshot(job.state), failure)
                return self.jobs.update_state(job.id, failed.state, failed.resume_state, str(error))
            job = self.jobs.get(job_id)
            if interrupt_after is job.state:
                raise PipelineInterrupted(f"interrupted after {job.state.value}")
            if job.state in {JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_APPROVAL_REQUIRED, JobState.PUBLISH_APPROVAL_REQUIRED}:
                return job

    def _run_stage(self, job: PipelineJob) -> None:
        if job.state is JobState.TOPIC_CREATED:
            self._transition(job, JobState.CONTENT_GENERATING); return
        if job.state is JobState.CONTENT_GENERATING:
            package = self._load_json_artifact(job.id, JobState.CONTENT_GENERATING, "content_package")
            if package is None:
                package = self.content.generate_package(job.request).model_dump(mode="json")
                self._checkpoint_json(job.id, JobState.CONTENT_GENERATING, "content_package", package)
            self._transition(job, JobState.CONTENT_READY); return
        if job.state is JobState.CONTENT_READY:
            self._transition(job, JobState.SCRIPT_APPROVAL_REQUIRED); return
        if job.state is JobState.SCRIPT_APPROVAL_REQUIRED:
            approval = self.approvals.approved(job.id, ApprovalGate.SCRIPT)
            if approval is None: return
            self._transition(job, JobState.ASSET_ACQUISITION, approvals=frozenset({ApprovalGate.SCRIPT})); return
        if job.state is JobState.ASSET_ACQUISITION:
            package = self._required_json(job.id, JobState.CONTENT_GENERATING, "content_package")
            if self._load_json_artifact(job.id, JobState.ASSET_ACQUISITION, "license_manifest") is None:
                assets = []
                for scene in package["scene_plans"]:
                    assets.extend(candidate.model_dump(mode="json") for candidate in self.media.search(AssetSearchRequest(queries=tuple(scene["search_queries"]), visual_type=scene["visual_type"], required_license="licensed")))
                self._checkpoint_json(job.id, JobState.ASSET_ACQUISITION, "license_manifest", {"assets": assets})
            self._transition(job, JobState.VOICE_GENERATION); return
        if job.state is JobState.VOICE_GENERATION:
            package = self._required_json(job.id, JobState.CONTENT_GENERATING, "content_package")
            if self._load_json_artifact(job.id, JobState.VOICE_GENERATION, "voice_manifest") is None:
                voices = [self.voice.synthesize(VoiceRequest(text=section["narration"], language=job.request.language, voice_id="fake-voice", section_id=section["section_id"])).model_dump(mode="json") for section in package["script_sections"]]
                self._checkpoint_json(job.id, JobState.VOICE_GENERATION, "voice_manifest", {"voices": voices})
            self._transition(job, JobState.CAPTION_GENERATION); return
        if job.state is JobState.CAPTION_GENERATION:
            self._checkpoint_generated(job.id, JobState.CAPTION_GENERATION, "captions", "captions.vtt", "WEBVTT\n\n00:00.000 --> 00:01.000\nSynthetic caption\n")
            self._transition(job, JobState.PREVIEW_RENDERING); return
        if job.state is JobState.PREVIEW_RENDERING:
            self._checkpoint_generated(job.id, JobState.PREVIEW_RENDERING, "preview", "preview.mp4", "synthetic preview")
            self._transition(job, JobState.PREVIEW_APPROVAL_REQUIRED); return
        if job.state is JobState.PREVIEW_APPROVAL_REQUIRED:
            approval = self.approvals.approved(job.id, ApprovalGate.PREVIEW)
            if approval is None: return
            self._transition(job, JobState.FINAL_RENDERING, approvals=frozenset({ApprovalGate.PREVIEW})); return
        if job.state is JobState.FINAL_RENDERING:
            self._checkpoint_generated(job.id, JobState.FINAL_RENDERING, "final", "final.mp4", "synthetic final")
            self._transition(job, JobState.PRIVATE_UPLOAD_READY); return
        if job.state is JobState.PRIVATE_UPLOAD_READY:
            self._transition(job, JobState.PRIVATE_UPLOADING); return
        if job.state is JobState.PRIVATE_UPLOADING:
            final = self._required_artifact(job.id, JobState.FINAL_RENDERING, "final")
            if self._load_json_artifact(job.id, JobState.PRIVATE_UPLOADING, "private_receipt") is None:
                result = self._upload_once(job, "private", final.path, PublishPrivacy.PRIVATE)
                self._checkpoint_json(job.id, JobState.PRIVATE_UPLOADING, "private_receipt", result.model_dump(mode="json"))
            self._transition(job, JobState.PUBLISH_APPROVAL_REQUIRED); return
        if job.state is JobState.PUBLISH_APPROVAL_REQUIRED:
            approval = self.approvals.approved(job.id, ApprovalGate.PUBLIC_PUBLISH)
            if approval is None: return
            final = self._required_artifact(job.id, JobState.FINAL_RENDERING, "final")
            if self._load_json_artifact(job.id, JobState.PUBLISH_APPROVAL_REQUIRED, "public_receipt") is None:
                result = self._upload_once(job, "public", final.path, PublishPrivacy.PUBLIC, approval.id)
                self._checkpoint_json(job.id, JobState.PUBLISH_APPROVAL_REQUIRED, "public_receipt", result.model_dump(mode="json"))
            self._transition(job, JobState.PUBLISHED, approvals=frozenset({ApprovalGate.PUBLIC_PUBLISH})); return
        raise RuntimeError(f"unsupported pipeline state: {job.state.value}")

    def _transition(self, job: PipelineJob, target: JobState, **kwargs: object) -> None:
        snapshot = self.machine.transition(PipelineSnapshot(job.state, job.resume_state), target, **kwargs)
        self.jobs.update_state(job.id, snapshot.state, snapshot.resume_state)

    def _artifact_path(self, job_id: str, filename: str) -> Path:
        return self.artifact_root / job_id / filename

    def _checkpoint_generated(self, job_id: str, stage: JobState, name: str, filename: str, contents: str) -> Artifact:
        existing = self._valid_artifact(job_id, stage, name)
        if existing: return existing
        path = self._artifact_path(job_id, filename)
        self._atomic_write(path, contents.encode())
        return self.artifacts.save(Artifact(job_id, stage, name, str(path), self._checksum(path), {"generator": "deterministic-test"}))

    def _checkpoint_json(self, job_id: str, stage: JobState, name: str, value: object) -> Artifact:
        return self._checkpoint_generated(job_id, stage, name, f"{name}.json", json.dumps(value, sort_keys=True))

    def _load_json_artifact(self, job_id: str, stage: JobState, name: str) -> dict[str, object] | None:
        artifact = self._valid_artifact(job_id, stage, name)
        return json.loads(Path(artifact.path).read_text(encoding="utf-8")) if artifact else None

    def _required_json(self, job_id: str, stage: JobState, name: str) -> dict[str, object]:
        value = self._load_json_artifact(job_id, stage, name)
        if value is None: raise ProviderValidationError(f"required checkpoint missing or invalid: {name}")
        return value

    def _required_artifact(self, job_id: str, stage: JobState, name: str) -> Artifact:
        artifact = self._valid_artifact(job_id, stage, name)
        if artifact is None: raise ProviderValidationError(f"required checkpoint missing or invalid: {name}")
        return artifact

    def _valid_artifact(self, job_id: str, stage: JobState, name: str) -> Artifact | None:
        artifact = self.artifacts.get(job_id, stage, name)
        if artifact and Path(artifact.path).is_file() and self._checksum(Path(artifact.path)) == artifact.checksum_sha256: return artifact
        return None

    @staticmethod
    def _atomic_write(path: Path, contents: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True); temporary = path.with_suffix(path.suffix + ".tmp"); temporary.write_bytes(contents); temporary.replace(path)

    @staticmethod
    def _checksum(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _metadata(self, job: PipelineJob):
        from tubeforge.domain.contracts import VideoMetadata
        return VideoMetadata.model_validate(self._required_json(job.id, JobState.CONTENT_GENERATING, "content_package")["metadata"])

    def _upload_once(self, job: PipelineJob, operation: str, path: str, privacy: PublishPrivacy, approval_id: str | None = None):
        """Use a durable key/receipt so recovery never starts a second upload."""
        key = f"{job.id}:{operation}"
        if self.external_operations is not None:
            receipt = self.external_operations.receipt(key)
            if receipt is not None:
                from tubeforge.domain.contracts import PublishResult
                return PublishResult.model_validate(receipt)
            if not self.external_operations.reserve(job.id, operation, key):
                raise ProviderValidationError(f"external operation pending reconciliation: {operation}")
        result = self.publisher.upload(PublishRequest(platform="youtube", artifact_path=path, metadata=self._metadata(job), privacy=privacy, idempotency_key=key, public_publish_approval_id=approval_id))
        if self.external_operations is not None:
            self.external_operations.complete(key, result.model_dump(mode="json"))
        return result
