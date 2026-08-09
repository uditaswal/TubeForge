"""Checkpointed M4 pipeline runner with no worker, lease, or live integration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from tubeforge.core.config import FinalRenderConfig, PreviewRenderConfig, VoicePipelineConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.core.state_machine import PipelineSnapshot, PipelineStateMachine
from tubeforge.db.repositories import ApprovalRepository, Artifact, ArtifactRepository, AssetCacheRepository, ExternalOperationRepository, JobRepository, PipelineJob
from tubeforge.domain.contracts import AssetCandidate, AssetSearchRequest, ContentPackage, PublishPrivacy, PublishRequest, VoiceRequest
from tubeforge.domain.providers import ContentProvider, MediaProvider, Publisher, VoiceProvider
from tubeforge.domain.states import ApprovalGate, JobState
from tubeforge.pipeline.assets import AssetAcquisitionCancelled, AssetAcquisitionService, AssetDownloader, AssetLimits, asset_policy_valid, attribution_manifest, scene_request, select_candidate
from tubeforge.pipeline.captions import render_srt, render_vtt, timed_phrases
from tubeforge.pipeline.narration import NarrationPhrase, segment_content_package
from tubeforge.rendering.audio import FFmpegAudioAssembler, FFprobe
from tubeforge.rendering.preview import PreviewRenderCancelled, PreviewRenderer, build_timeline


class PipelineInterrupted(RuntimeError):
    """Test-only interruption after a durable checkpoint has been written."""


class PipelineCancellation(RuntimeError):
    """Internal signal raised between costly phrase boundaries."""


class PipelineOrchestrator:
    """Run one job synchronously, committing only short persistence operations."""

    def __init__(self, jobs: JobRepository, artifacts: ArtifactRepository, approvals: ApprovalRepository, content: ContentProvider, media: MediaProvider, voice: VoiceProvider, publisher: Publisher, artifact_root: Path, external_operations: ExternalOperationRepository | None = None, voice_config: VoicePipelineConfig | None = None, audio_assembler: FFmpegAudioAssembler | None = None, ffprobe: FFprobe | None = None, asset_acquirer: AssetAcquisitionService | None = None, asset_limits: AssetLimits | None = None, preview_renderer: PreviewRenderer | None = None, final_renderer: PreviewRenderer | None = None) -> None:
        self.jobs, self.artifacts, self.approvals = jobs, artifacts, approvals
        self.content, self.media, self.voice, self.publisher = content, media, voice, publisher
        self.artifact_root, self.machine = artifact_root, PipelineStateMachine()
        self.external_operations = external_operations
        self.voice_config = voice_config or VoicePipelineConfig()
        self.audio_assembler = audio_assembler or FFmpegAudioAssembler(str(self.voice_config.ffmpeg_executable), self.voice_config.ffmpeg_threads)
        self.ffprobe = ffprobe or FFprobe(str(self.voice_config.ffprobe_executable))
        self.preview_renderer = preview_renderer or PreviewRenderer(PreviewRenderConfig())
        self.final_renderer = final_renderer or PreviewRenderer(FinalRenderConfig())
        self.asset_limits = asset_limits or AssetLimits(frozenset({"example.invalid", "upload.wikimedia.org", "commons.wikimedia.org"}), frozenset({"CC0-1.0", "CC BY 4.0", "CC BY-SA 4.0", "Public Domain"}))
        self.asset_acquirer = asset_acquirer or AssetAcquisitionService(AssetCacheRepository(artifacts._session_factory), AssetDownloader(artifact_root.parent / "cache" / "assets", self.asset_limits))

    def run(self, job_id: str, *, operator_resolved: bool = False, authentication_restored: bool = False, interrupt_after: JobState | None = None, cancellation_requested: Callable[[], bool] | None = None) -> PipelineJob:
        """Advance until an approval gate, terminal state, or classified failure."""
        while True:
            job = self.jobs.get(job_id)
            if job.state in {JobState.FINAL_READY, JobState.CANCELLED, JobState.FAILED_EXHAUSTED}:
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
            except (PipelineCancellation, AssetAcquisitionCancelled, PreviewRenderCancelled):
                cancelled = self.machine.transition(PipelineSnapshot(job.state, job.resume_state), JobState.CANCELLED)
                return self.jobs.update_state(job.id, cancelled.state, cancelled.resume_state)
            except (RetryableProviderError, ProviderValidationError, ProviderAuthenticationError, ValidationError) as error:
                failure = JobState.AUTH_REQUIRED if isinstance(error, ProviderAuthenticationError) else JobState.FAILED_VALIDATION if isinstance(error, (ProviderValidationError, ValidationError)) else JobState.FAILED_RETRYABLE
                failed = self.machine.transition(PipelineSnapshot(job.state), failure)
                return self.jobs.update_state(job.id, failed.state, failed.resume_state, str(error))
            job = self.jobs.get(job_id)
            if interrupt_after is job.state:
                raise PipelineInterrupted(f"interrupted after {job.state.value}")
            if job.state in {JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY, JobState.FINAL_READY}:
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
            package = ContentPackage.model_validate(self._required_json(job.id, JobState.CONTENT_GENERATING, "content_package"))
            manifest = self._load_json_artifact(job.id, JobState.ASSET_ACQUISITION, "asset_manifest") or {"scenes": {}}
            accepted = manifest["scenes"]
            for scene in package.scene_plans:
                if cancellation_requested and cancellation_requested(): raise PipelineCancellation("cancelled before asset search")
                current = accepted.get(scene.scene_id)
                if current and self._accepted_asset_valid(current): continue
                request = scene_request(scene)
                candidate = select_candidate(self.media.search(request), request, self.asset_limits)
                if cancellation_requested and cancellation_requested(): raise PipelineCancellation("cancelled before asset acquisition")
                path, cache_key, metadata = self.asset_acquirer.acquire(type(self.media).__name__, candidate, cancellation_requested)
                accepted[scene.scene_id] = {"scene_id": scene.scene_id, "request": request.model_dump(mode="json"), "candidate": candidate.model_dump(mode="json"), "cache_key": cache_key, "path": str(path), "checksum_sha256": metadata["checksum_sha256"], "validation": metadata}
                self._replace_json(job.id, JobState.ASSET_ACQUISITION, "asset_manifest", manifest)
            if any(not self._accepted_asset_valid(accepted.get(scene.scene_id)) for scene in package.scene_plans): raise ProviderValidationError("not every scene has a validated accepted asset")
            selected = {scene_id: AssetCandidate.model_validate(item["candidate"]) for scene_id, item in accepted.items()}
            self._replace_json(job.id, JobState.ASSET_ACQUISITION, "license_manifest", attribution_manifest(selected))
            self._transition(job, JobState.ASSETS_READY); return
        if job.state is JobState.ASSETS_READY:
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
            self._replace_json(job.id, JobState.VOICE_GENERATION, "timing_map", {"final_duration_seconds": final_duration, "expected_duration_seconds": expected_duration, "phrases": [{"phrase_id": cue.phrase.phrase_id, "section_id": cue.phrase.section_id, "start_seconds": cue.start_seconds, "end_seconds": cue.end_seconds, "duration_seconds": cue.end_seconds - cue.start_seconds} for cue in cues]})
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
            preview, identity = self._render_checkpoint(job, self.preview_renderer, JobState.PREVIEW_RENDERING, "preview", "preview.mp4", cancellation_requested)
            self._transition(job, JobState.PREVIEW_READY); return
        if job.state is JobState.PREVIEW_READY:
            manifest = self._required_json(job.id, JobState.PREVIEW_RENDERING, "preview_manifest")
            identity = str(manifest["render_identity"])
            if self.approvals.rejected(job.id, ApprovalGate.PREVIEW, reviewed_identity=identity):
                raise ProviderValidationError("preview was explicitly rejected")
            approval = self.approvals.approved(job.id, ApprovalGate.PREVIEW, reviewed_identity=identity)
            if approval is None: return
            self._transition(job, JobState.PREVIEW_APPROVED, approvals=frozenset({ApprovalGate.PREVIEW})); return
        if job.state is JobState.PREVIEW_APPROVED:
            self._transition(job, JobState.FINAL_RENDERING); return
        if job.state is JobState.FINAL_RENDERING:
            preview_manifest = self._required_json(job.id, JobState.PREVIEW_RENDERING, "preview_manifest")
            identity = str(preview_manifest["render_identity"])
            approval = self.approvals.approved(job.id, ApprovalGate.PREVIEW, reviewed_identity=identity)
            if approval is None or self.approvals.rejected(job.id, ApprovalGate.PREVIEW, reviewed_identity=identity):
                raise ProviderValidationError("final render requires approval of this exact preview")
            self._render_checkpoint(job, self.final_renderer, JobState.FINAL_RENDERING, "final", "final.mp4", cancellation_requested, approval_identity=identity, approval_id=approval.id)
            self._transition(job, JobState.FINAL_READY); return
        raise RuntimeError(f"unsupported pipeline state: {job.state.value}")

    def _render_checkpoint(self, job: PipelineJob, renderer: PreviewRenderer, stage: JobState, name: str, filename: str, cancellation_requested: Callable[[], bool] | None, *, approval_identity: str | None = None, approval_id: str | None = None) -> tuple[Artifact, str]:
        """Render only after every source checkpoint has been revalidated."""
        package = ContentPackage.model_validate(self._required_json(job.id, JobState.CONTENT_GENERATING, "content_package"))
        narration = self._required_artifact(job.id, JobState.VOICE_GENERATION, "narration")
        captions = self._required_artifact(job.id, JobState.CAPTION_GENERATION, "captions")
        timing = self._required_json(job.id, JobState.VOICE_GENERATION, "timing_map")
        assets = self._required_json(job.id, JobState.ASSET_ACQUISITION, "asset_manifest").get("scenes")
        if not isinstance(assets, dict): raise ProviderValidationError("accepted asset manifest is invalid")
        if any(not self._accepted_asset_valid(value) for value in assets.values()): raise ProviderValidationError("accepted asset was modified or is unsafe")
        segments = build_timeline(package, timing, assets, tolerance=renderer.config.sync_tolerance_seconds)
        identity = renderer.identity(segments, Path(narration.path), Path(captions.path), approval_identity=approval_identity)
        existing = self._valid_artifact(job.id, stage, name)
        manifest = self._load_json_artifact(job.id, stage, f"{name}_manifest")
        if existing and manifest and manifest.get("render_identity") == identity:
            renderer.validate(Path(existing.path), segments[-1].end_seconds)
            return existing, identity
        output = self._artifact_path(job.id, filename)
        result = renderer.render(segments, Path(narration.path), Path(captions.path), output, cancellation_requested=cancellation_requested)
        provenance = {"render_identity": identity, "inputs": {"narration": narration.checksum_sha256, "captions": captions.checksum_sha256, "assets": [segment.asset_checksum for segment in segments]}, "validation": result["metadata"], "command": result["command"], "approval_identity": approval_identity, "approval_id": approval_id}
        artifact = self.artifacts.save(Artifact(job.id, stage, name, str(output), str(result["checksum_sha256"]), provenance))
        self._replace_json(job.id, stage, f"{name}_manifest", {**provenance, "artifact_checksum": artifact.checksum_sha256})
        return artifact, identity

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


    def _accepted_asset_valid(self, value: object) -> bool:
        try:
            if not isinstance(value, dict): return False
            path=Path(str(value["path"])); validation=value["validation"]
            candidate_data = value["candidate"]
            if not isinstance(candidate_data, dict) or not {"license_name", "editorial_only", "review_required", "attribution_required"}.issubset(candidate_data): return False
            candidate = AssetCandidate.model_validate(candidate_data)
            return path.is_file() and path.stat().st_size > 0 and self._checksum(path)==value["checksum_sha256"] and validation["checksum_sha256"]==value["checksum_sha256"] and validation["validation_version"]=="m8-v1" and asset_policy_valid(candidate, self.asset_limits)
        except (KeyError, OSError, TypeError, ValueError): return False
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
