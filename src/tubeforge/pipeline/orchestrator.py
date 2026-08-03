"""Checkpointed M4 pipeline runner with no worker, lease, or live integration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from tubeforge.core.config import VoicePipelineConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.core.state_machine import PipelineSnapshot, PipelineStateMachine
from tubeforge.db.repositories import ApprovalRepository, Artifact, ArtifactRepository, ExternalOperationRepository, JobRepository, PipelineJob
from tubeforge.domain.contracts import AssetSearchRequest, ContentPackage, PublishPrivacy, PublishRequest, VoiceRequest
from tubeforge.domain.providers import ContentProvider, MediaProvider, Publisher, VoiceProvider
from tubeforge.domain.states import ApprovalGate, JobState
from tubeforge.pipeline.captions import render_srt, render_vtt, timed_phrases
from tubeforge.pipeline.narration import NarrationPhrase, segment_content_package
from tubeforge.rendering.audio import FFmpegAudioAssembler, FFprobe


class PipelineInterrupted(RuntimeError):
    """Test-only interruption after a durable checkpoint has been written."""


class PipelineCancellation(RuntimeError):
    """Internal signal raised between costly phrase boundaries."""


class PipelineOrchestrator:
    """Run one job synchronously, committing only short persistence operations."""

    def __init__(self, jobs: JobRepository, artifacts: ArtifactRepository, approvals: ApprovalRepository, content: ContentProvider, media: MediaProvider, voice: VoiceProvider, publisher: Publisher, artifact_root: Path, external_operations: ExternalOperationRepository | None = None, voice_config: VoicePipelineConfig | None = None, audio_assembler: FFmpegAudioAssembler | None = None, ffprobe: FFprobe | None = None) -> None:
        self.jobs, self.artifacts, self.approvals = jobs, artifacts, approvals
        self.content, self.media, self.voice, self.publisher = content, media, voice, publisher
        self.artifact_root, self.machine = artifact_root, PipelineStateMachine()
        self.external_operations = external_operations
        self.voice_config = voice_config or VoicePipelineConfig()
        self.audio_assembler = audio_assembler or FFmpegAudioAssembler(str(self.voice_config.ffmpeg_executable), self.voice_config.ffmpeg_threads)
        self.ffprobe = ffprobe or FFprobe(str(self.voice_config.ffprobe_executable))

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
                self._run_stage(job, cancellation_requested)
            except PipelineCancellation:
                cancelled = self.machine.transition(PipelineSnapshot(job.state, job.resume_state), JobState.CANCELLED)
                return self.jobs.update_state(job.id, cancelled.state, cancelled.resume_state)
            except (RetryableProviderError, ProviderValidationError, ProviderAuthenticationError, ValidationError) as error:
                failure = JobState.AUTH_REQUIRED if isinstance(error, ProviderAuthenticationError) else JobState.FAILED_VALIDATION if isinstance(error, (ProviderValidationError, ValidationError)) else JobState.FAILED_RETRYABLE
                failed = self.machine.transition(PipelineSnapshot(job.state), failure)
                return self.jobs.update_state(job.id, failed.state, failed.resume_state, str(error))
            job = self.jobs.get(job_id)
            if interrupt_after is job.state:
                raise PipelineInterrupted(f"interrupted after {job.state.value}")
            if job.state in {JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_APPROVAL_REQUIRED, JobState.PUBLISH_APPROVAL_REQUIRED}:
                return job

    def _run_stage(self, job: PipelineJob, cancellation_requested: Callable[[], bool] | None = None) -> None:
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
            package = ContentPackage.model_validate(self._required_json(job.id, JobState.CONTENT_GENERATING, "content_package"))
            phrases = segment_content_package(package)
            if not phrases:
                raise ProviderValidationError("approved script contains no narration phrases")
            self._replace_json(job.id, JobState.VOICE_GENERATION, "segmentation_manifest", {"phrases": [phrase.model_dump(mode="json") for phrase in phrases]})
            existing = self._load_json_artifact(job.id, JobState.VOICE_GENERATION, "voice_manifest") or {"voices": []}
            accepted = {item["phrase_id"]: item for item in existing.get("voices", [])}
            voice_id = getattr(getattr(self.voice, "settings", None), "voice_id", "fake-voice")
            for phrase in phrases:
                if cancellation_requested is not None and cancellation_requested():
                    raise PipelineCancellation("cancelled before phrase synthesis")
                result = accepted.get(phrase.phrase_id)
                if result is None or not self._result_is_valid(result):
                    response = self.voice.synthesize(VoiceRequest(text=phrase.text, language=job.request.language, voice_id=voice_id, section_id=phrase.section_id, phrase_id=phrase.phrase_id))
                    result = {**response.model_dump(mode="json"), "phrase_id": phrase.phrase_id, "section_id": phrase.section_id, "claim_ids": list(phrase.claim_ids), "text": phrase.text}
                    accepted[phrase.phrase_id] = result
                    self._replace_json(job.id, JobState.VOICE_GENERATION, "voice_manifest", {"voices": [accepted[item.phrase_id] for item in phrases if item.phrase_id in accepted]})
            measured = []
            for phrase in phrases:
                item = accepted[phrase.phrase_id]
                measured.append({**item, "duration_seconds": float(self.ffprobe.inspect(Path(str(item["artifact_path"]))) ["duration_seconds"])})
            self._replace_json(job.id, JobState.VOICE_GENERATION, "voice_manifest", {"voices": measured})
            assembly_key = hashlib.sha256(json.dumps({"pause_seconds": self.voice_config.pause_seconds, "phrases": [(item["phrase_id"], item["checksum_sha256"]) for item in measured]}, sort_keys=True).encode()).hexdigest()
            narration = self._valid_artifact(job.id, JobState.VOICE_GENERATION, "narration")
            narration_path = self._artifact_path(job.id, "narration.wav")
            if narration is None or narration.provenance.get("assembly_key") != assembly_key:
                if cancellation_requested is not None and cancellation_requested():
                    raise PipelineCancellation("cancelled before narration assembly")
                self.audio_assembler.assemble(tuple(Path(str(item["artifact_path"])) for item in measured), narration_path, pause_seconds=self.voice_config.pause_seconds)
                narration = self._save_file(job.id, JobState.VOICE_GENERATION, "narration", narration_path, {"generator": "ffmpeg", "phrase_count": len(measured), "assembly_key": assembly_key})
            final_duration = float(self.ffprobe.inspect(Path(narration.path))["duration_seconds"])
            durations = tuple(float(item["duration_seconds"]) for item in measured)
            expected_duration = sum(durations) + self.voice_config.pause_seconds * (len(durations) - 1)
            if abs(final_duration - expected_duration) > self.voice_config.duration_tolerance_seconds:
                raise ProviderValidationError("assembled narration duration exceeds configured tolerance")
            cues = timed_phrases(phrases, durations, self.voice_config.pause_seconds)
            self._replace_json(job.id, JobState.VOICE_GENERATION, "timing_map", {"final_duration_seconds": final_duration, "expected_duration_seconds": expected_duration, "phrases": [{"phrase_id": cue.phrase.phrase_id, "start_seconds": cue.start_seconds, "end_seconds": cue.end_seconds, "duration_seconds": cue.end_seconds - cue.start_seconds} for cue in cues]})
            self._transition(job, JobState.CAPTION_GENERATION); return
        if job.state is JobState.CAPTION_GENERATION:
            package = ContentPackage.model_validate(self._required_json(job.id, JobState.CONTENT_GENERATING, "content_package"))
            phrases = segment_content_package(package)
            voices = self._required_json(job.id, JobState.VOICE_GENERATION, "voice_manifest")["voices"]
            durations = tuple(float(item["duration_seconds"]) for item in voices)
            cues = timed_phrases(phrases, durations, self.voice_config.pause_seconds)
            self._checkpoint_generated(job.id, JobState.CAPTION_GENERATION, "captions_srt", "captions.srt", render_srt(cues, self.voice_config.caption_line_length))
            self._checkpoint_generated(job.id, JobState.CAPTION_GENERATION, "captions", "captions.vtt", render_vtt(cues, self.voice_config.caption_line_length))
            self._required_artifact(job.id, JobState.VOICE_GENERATION, "narration")
            self._required_artifact(job.id, JobState.CAPTION_GENERATION, "captions_srt")
            self._required_artifact(job.id, JobState.CAPTION_GENERATION, "captions")
            self._transition(job, JobState.VOICE_READY); return
        if job.state is JobState.VOICE_READY:
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
        encoded = contents.encode()
        if existing and Path(existing.path).read_bytes() == encoded:
            return existing
        path = self._artifact_path(job_id, filename)
        self._atomic_write(path, encoded)
        return self.artifacts.save(Artifact(job_id, stage, name, str(path), self._checksum(path), {"generator": "deterministic"}))

    def _checkpoint_json(self, job_id: str, stage: JobState, name: str, value: object) -> Artifact:
        return self._checkpoint_generated(job_id, stage, name, f"{name}.json", json.dumps(value, sort_keys=True))

    def _replace_json(self, job_id: str, stage: JobState, name: str, value: object) -> Artifact:
        path = self._artifact_path(job_id, f"{name}.json")
        contents = json.dumps(value, sort_keys=True).encode()
        if not path.is_file() or path.read_bytes() != contents:
            self._atomic_write(path, contents)
        return self.artifacts.save(Artifact(job_id, stage, name, str(path), self._checksum(path), {"generator": "deterministic"}))

    def _save_file(self, job_id: str, stage: JobState, name: str, path: Path, provenance: dict[str, object]) -> Artifact:
        if not path.is_file() or path.stat().st_size == 0:
            raise ProviderValidationError(f"generated artifact missing or empty: {name}")
        return self.artifacts.save(Artifact(job_id, stage, name, str(path), self._checksum(path), provenance))

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

    def _result_is_valid(self, result: object) -> bool:
        if not isinstance(result, dict):
            return False
        try:
            path = Path(str(result["artifact_path"]))
            return path.is_file() and path.stat().st_size > 0 and self._checksum(path) == result["checksum_sha256"] and float(result["duration_seconds"]) > 0
        except (KeyError, OSError, ValueError, TypeError):
            return False

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
