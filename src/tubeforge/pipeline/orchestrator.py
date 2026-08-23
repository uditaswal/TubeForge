"""Checkpointed M4 pipeline runner with no worker, lease, or live integration."""

from __future__ import annotations

import hashlib
import json
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from tubeforge.core.config import FinalRenderConfig, PreviewRenderConfig, PublicationPreparationConfig, PublicationVerificationConfig, Settings, VoicePipelineConfig, YouTubePublishingConfig
from tubeforge.core.errors import AmbiguousProviderError, ProviderAuthenticationError, ProviderCancellation, ProviderValidationError, RemoteResourceMissingError, RetryableProviderError
from tubeforge.core.state_machine import PipelineSnapshot, PipelineStateMachine
from tubeforge.db.repositories import ApprovalRepository, Artifact, ArtifactRepository, AssetCacheRepository, ExternalOperationRepository, JobRepository, PipelineJob, PublicationRepository
from tubeforge.domain.contracts import AssetCandidate, AssetSearchRequest, ContentPackage, ContentRequest, PublishPrivacy, PublishRequest, RemoteProcessingState, RemotePublicationSnapshot, SourceReference, VideoMetadata, VoiceRequest
from tubeforge.domain.providers import ContentProvider, MediaProvider, Publisher, VoiceProvider
from tubeforge.domain.states import ApprovalGate, JobState
from tubeforge.pipeline.assets import AssetAcquisitionCancelled, AssetAcquisitionService, AssetDownloader, AssetLimits, asset_policy_valid, attribution_manifest, scene_request, select_candidate
from tubeforge.pipeline.captions import render_srt, render_vtt, timed_phrases
from tubeforge.pipeline.narration import NarrationPhrase, segment_content_package
from tubeforge.pipeline.publication import identity as publication_identity, metadata_from_package, render_thumbnail, validate_thumbnail
from tubeforge.pipeline.sources import SourceIngestor, source_packet
from tubeforge.rendering.audio import FFmpegAudioAssembler, FFprobe
from tubeforge.rendering.preview import PreviewRenderCancelled, PreviewRenderer, build_timeline


class PipelineInterrupted(RuntimeError):
    """Test-only interruption after a durable checkpoint has been written."""


class PipelineCancellation(RuntimeError):
    """Internal signal raised between costly phrase boundaries."""


class PipelineOwnershipLost(PipelineCancellation):
    """The worker no longer owns this job, so it must not promote work."""


_ownership_check: ContextVar[Callable[..., bool] | None] = ContextVar("tubeforge_ownership_check", default=None)


class PipelineOrchestrator:
    """Run one job synchronously, committing only short persistence operations."""

    def __init__(self, jobs: JobRepository, artifacts: ArtifactRepository, approvals: ApprovalRepository, content: ContentProvider, media: MediaProvider, voice: VoiceProvider, publisher: Publisher, artifact_root: Path, external_operations: ExternalOperationRepository | None = None, voice_config: VoicePipelineConfig | None = None, audio_assembler: FFmpegAudioAssembler | None = None, ffprobe: FFprobe | None = None, asset_acquirer: AssetAcquisitionService | None = None, asset_limits: AssetLimits | None = None, preview_renderer: PreviewRenderer | None = None, final_renderer: PreviewRenderer | None = None, preview_config: PreviewRenderConfig | None = None, final_config: FinalRenderConfig | None = None, publication_config: PublicationPreparationConfig | None = None, youtube_config: YouTubePublishingConfig | None = None, verification_config: PublicationVerificationConfig | None = None, source_ingestor: SourceIngestor | None = None) -> None:
        self.jobs, self.artifacts, self.approvals = jobs, artifacts, approvals
        self.content, self.media, self.voice, self.publisher = content, media, voice, publisher
        self.artifact_root, self.machine = artifact_root, PipelineStateMachine()
        self.external_operations = external_operations
        self.voice_config = voice_config or VoicePipelineConfig()
        self.audio_assembler = audio_assembler or FFmpegAudioAssembler(str(self.voice_config.ffmpeg_executable), self.voice_config.ffmpeg_threads)
        self.ffprobe = ffprobe or FFprobe(str(self.voice_config.ffprobe_executable))
        self.preview_renderer = preview_renderer or PreviewRenderer(preview_config or PreviewRenderConfig())
        self.final_renderer = final_renderer or PreviewRenderer(final_config or FinalRenderConfig())
        self.publication_config = publication_config or PublicationPreparationConfig()
        self.youtube_config = youtube_config or YouTubePublishingConfig()
        self.verification_config = verification_config or PublicationVerificationConfig()
        self.publications = PublicationRepository(artifacts._session_factory)
        self.asset_limits = asset_limits or AssetLimits(frozenset({"example.invalid", "upload.wikimedia.org", "commons.wikimedia.org"}), frozenset({"CC0-1.0", "CC BY 4.0", "CC BY-SA 4.0", "Public Domain"}))
        self.asset_acquirer = asset_acquirer or AssetAcquisitionService(AssetCacheRepository(artifacts._session_factory), AssetDownloader(artifact_root.parent / "cache" / "assets", self.asset_limits))
        self.source_ingestor = source_ingestor

    @classmethod
    def from_settings(cls, settings: Settings, jobs: JobRepository, artifacts: ArtifactRepository, approvals: ApprovalRepository, content: ContentProvider, media: MediaProvider, voice: VoiceProvider, publisher: Publisher, external_operations: ExternalOperationRepository | None = None) -> "PipelineOrchestrator":
        """Application-bound constructor that preserves configured render profiles."""
        return cls(
            jobs, artifacts, approvals, content, media, voice, publisher,
            settings.pipeline.voice.artifact_root, external_operations,
            voice_config=settings.pipeline.voice, preview_config=settings.pipeline.preview,
            final_config=settings.pipeline.final, publication_config=settings.pipeline.publication, youtube_config=settings.pipeline.youtube, verification_config=settings.pipeline.verification,
        )

    def run(self, job_id: str, *, operator_resolved: bool = False, authentication_restored: bool = False, interrupt_after: JobState | None = None, cancellation_requested: Callable[[], bool] | None = None, ownership_check: Callable[..., bool] | None = None) -> PipelineJob:
        """Run with an optional worker-owned execution guard."""
        token = _ownership_check.set(ownership_check)
        try:
            def guarded_cancellation() -> bool:
                return bool(cancellation_requested and cancellation_requested()) or bool(ownership_check and not ownership_check())

            try:
                return self._run(job_id, operator_resolved=operator_resolved, authentication_restored=authentication_restored, interrupt_after=interrupt_after, cancellation_requested=guarded_cancellation)
            except PipelineOwnershipLost:
                return self.jobs.get(job_id)
        finally:
            _ownership_check.reset(token)

    def _run(self, job_id: str, *, operator_resolved: bool = False, authentication_restored: bool = False, interrupt_after: JobState | None = None, cancellation_requested: Callable[[], bool] | None = None) -> PipelineJob:
        """Advance until an approval gate, terminal state, or classified failure."""
        while True:
            self._ensure_ownership()
            job = self.jobs.get(job_id)
            if job.state in {JobState.CANCELLED, JobState.FAILED_EXHAUSTED, JobState.PUBLISHED} or (job.state is JobState.PUBLICATION_READY and not self.youtube_config.enabled):
                return job
            if cancellation_requested is not None and cancellation_requested():
                self._ensure_ownership(force=True)
                cancelled = self.machine.transition(PipelineSnapshot(job.state, job.resume_state), JobState.CANCELLED)
                self._update_state(job.id, cancelled.state, cancelled.resume_state)
                return self.jobs.get(job.id)
            if job.state in {JobState.FAILED_RETRYABLE, JobState.FAILED_VALIDATION, JobState.AUTH_REQUIRED}:
                target = job.resume_state
                assert target is not None
                self._transition(job, target, operator_resolved=operator_resolved, authentication_restored=authentication_restored)
                continue
            try:
                self._run_stage(job, cancellation_requested)
            except PipelineOwnershipLost:
                return self.jobs.get(job.id)
            except (PipelineCancellation, ProviderCancellation, AssetAcquisitionCancelled, PreviewRenderCancelled):
                self._ensure_ownership(force=True)
                cancelled = self.machine.transition(PipelineSnapshot(job.state, job.resume_state), JobState.CANCELLED)
                self._update_state(job.id, cancelled.state, cancelled.resume_state)
                return self.jobs.get(job.id)
            except (RetryableProviderError, ProviderValidationError, ProviderAuthenticationError, ValidationError) as error:
                self._ensure_ownership(force=True)
                failure = JobState.AUTH_REQUIRED if isinstance(error, ProviderAuthenticationError) else JobState.FAILED_VALIDATION if isinstance(error, (ProviderValidationError, ValidationError)) else JobState.FAILED_RETRYABLE
                failed = self.machine.transition(PipelineSnapshot(job.state), failure)
                self._update_state(job.id, failed.state, failed.resume_state, str(error))
                return self.jobs.get(job.id)
            job = self.jobs.get(job_id)
            if interrupt_after is job.state:
                raise PipelineInterrupted(f"interrupted after {job.state.value}")
            if job.state in {JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY, JobState.FINAL_READY, JobState.PUBLICATION_APPROVAL_REQUIRED, JobState.PUBLICATION_READY, JobState.PUBLICATION_VERIFICATION_PENDING}:
                return job

    def _run_stage(self, job: PipelineJob, cancellation_requested: Callable[[], bool] | None = None) -> None:
        if job.state is JobState.TOPIC_CREATED:
            self._transition(job, JobState.CONTENT_GENERATING); return
        if job.state is JobState.CONTENT_GENERATING:
            package = self._load_json_artifact(job.id, JobState.CONTENT_GENERATING, "content_package")
            if package is None:
                package = self.content.generate_package(self._effective_content_request(job)).model_dump(mode="json")
                self._checkpoint_json(job.id, JobState.CONTENT_GENERATING, "content_package", package)
            self._transition(job, JobState.CONTENT_READY); return
        if job.state is JobState.CONTENT_READY:
            self._transition(job, JobState.SCRIPT_APPROVAL_REQUIRED); return
        if job.state is JobState.SCRIPT_APPROVAL_REQUIRED:
            package = self._required_artifact(job.id, JobState.CONTENT_GENERATING, "content_package")
            # New revisions require approval of these exact bytes.  The fallback
            # preserves pre-revision jobs created before identities were added.
            approval = self.approvals.approved(job.id, ApprovalGate.SCRIPT, reviewed_identity=package.checksum_sha256)
            if approval is None:
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
            if not self._preview_is_current(job):
                self._transition(job, JobState.PREVIEW_RENDERING); return
            manifest = self._required_json(job.id, JobState.PREVIEW_RENDERING, "preview_manifest")
            identity = str(manifest["render_identity"])
            approval = self.approvals.decision(job.id, ApprovalGate.PREVIEW, reviewed_identity=identity)
            if approval is not None and approval.status == "rejected":
                raise ProviderValidationError("preview was explicitly rejected")
            if approval is None or approval.status != "approved": return
            self._transition(job, JobState.PREVIEW_APPROVED, approvals=frozenset({ApprovalGate.PREVIEW})); return
        if job.state is JobState.PREVIEW_APPROVED:
            self._transition(job, JobState.FINAL_RENDERING); return
        if job.state is JobState.FINAL_RENDERING:
            if not self._preview_is_current(job):
                self._transition(job, JobState.PREVIEW_RENDERING); return
            preview_manifest = self._required_json(job.id, JobState.PREVIEW_RENDERING, "preview_manifest")
            identity = str(preview_manifest["render_identity"])
            approval = self.approvals.decision(job.id, ApprovalGate.PREVIEW, reviewed_identity=identity)
            if approval is None or approval.status != "approved":
                raise ProviderValidationError("final render requires approval of this exact preview")
            self._render_checkpoint(job, self.final_renderer, JobState.FINAL_RENDERING, "final", "final.mp4", cancellation_requested, approval_identity=identity, approval_id=approval.id)
            self._transition(job, JobState.FINAL_READY); return
        if job.state is JobState.FINAL_READY:
            self._required_artifact(job.id, JobState.FINAL_RENDERING, "final")
            self._transition(job, JobState.PUBLICATION_PREPARING); return
        if job.state is JobState.PUBLICATION_PREPARING:
            self._publication_checkpoints(job, cancellation_requested)
            self._transition(job, JobState.PUBLICATION_APPROVAL_REQUIRED); return
        if job.state is JobState.PUBLICATION_APPROVAL_REQUIRED:
            package = self._publication_package(job)
            effective_identity = str(package["publication_identity"])
            decision = self.approvals.decision(job.id, ApprovalGate.PUBLICATION_PREPARATION, reviewed_identity=effective_identity)
            if decision is not None and decision.status == "rejected":
                raise ProviderValidationError("publication preparation was explicitly rejected")
            if decision is None or decision.status != "approved":
                return
            package["effective_approval_id"] = decision.id
            self._replace_json(job.id, JobState.PUBLICATION_PREPARING, "publication_package", package)
            self._transition(job, JobState.PUBLICATION_READY, approvals=frozenset({ApprovalGate.PUBLICATION_PREPARATION})); return
        if job.state is JobState.PUBLICATION_READY:
            self._publish_checkpoint(job, cancellation_requested); return
        if job.state is JobState.PUBLISHING:
            self._publish_checkpoint(job, cancellation_requested); return
        if job.state is JobState.PUBLICATION_VERIFICATION_PENDING:
            self._verify_publication(job, cancellation_requested); return
        if job.state is JobState.PUBLICATION_RECONCILING:
            self._transition(job, JobState.PUBLISHED); return
        raise RuntimeError(f"unsupported pipeline state: {job.state.value}")

    def _publish_checkpoint(self, job: PipelineJob, cancellation_requested: Callable[[], bool] | None) -> None:
        """M13's only mutating boundary; each remote step follows a durable update."""
        self._ensure_ownership(force=True)
        package = self._required_json(job.id, JobState.PUBLICATION_PREPARING, "publication_package")
        config = self.youtube_config
        if not config.enabled or config.dry_run: return
        provider = self.publisher
        if not all(hasattr(provider, name) for name in ("authenticated_channel_id", "create_or_resume_video", "apply_metadata", "set_thumbnail", "fetch_video")):
            raise ProviderValidationError("configured publisher does not implement the YouTube publishing boundary")
        channel = provider.authenticated_channel_id()
        if channel != config.expected_channel_id: raise ProviderAuthenticationError("authenticated YouTube channel does not match configured channel")
        intent = {"package_identity": package["publication_identity"], "channel_id": channel, "privacy": config.privacy, "implementation_version": config.implementation_version}
        identity = publication_identity(intent)
        decision = self.approvals.approved(job.id, ApprovalGate.PUBLISH, reviewed_identity=identity)
        if decision is None: return
        record = self.publications.ensure(job.id, identity, str(package["publication_identity"]), channel, intent)
        if record.state == "creation_ambiguous":
            raise ProviderValidationError("upload outcome is ambiguous; reconcile manually before a new upload")
        if cancellation_requested and cancellation_requested(): raise PipelineCancellation("cancelled before YouTube mutation")
        metadata = VideoMetadata(title_options=(str(package["metadata"]["title"]),), description=str(package["metadata"]["description"]), tags=tuple(package["metadata"]["tags"]))
        request = PublishRequest(platform="youtube", artifact_path=str(package["final_video"]["path"]), metadata=metadata, privacy=PublishPrivacy(config.privacy), idempotency_key=identity)
        if record.remote_video_id is None:
            if provider.authenticated_channel_id() != channel:
                raise ProviderAuthenticationError("authenticated YouTube channel changed before upload")
            self._ensure_ownership(force=True)
            try: remote_id = provider.create_or_resume_video(request, cancellation_requested=cancellation_requested)
            except AmbiguousProviderError as error:
                self._ensure_ownership(force=True)
                self.publications.update(identity, state="creation_ambiguous", error_message="remote creation outcome unknown")
                raise ProviderValidationError("upload outcome is ambiguous; no automatic retry will create another video") from error
            self._ensure_ownership(force=True)
            record = self.publications.update(identity, remote_video_id=remote_id, state="remote_created")
        else:
            remote = provider.fetch_video(str(record.remote_video_id))
            if remote is None:
                self.publications.update(identity, state="reconciliation_required", error_message="recorded remote video is missing")
                raise RemoteResourceMissingError("recorded YouTube video is missing; manual reconciliation required")
        if cancellation_requested and cancellation_requested(): raise PipelineCancellation("cancelled after YouTube video creation")
        if not record.metadata_applied:
            if provider.authenticated_channel_id() != channel:
                raise ProviderAuthenticationError("authenticated YouTube channel changed before metadata update")
            self._ensure_ownership(force=True)
            provider.apply_metadata(str(record.remote_video_id), request)
            self._ensure_ownership(force=True)
            record = self.publications.update(identity, metadata_applied=True, state="metadata_applied")
        if cancellation_requested and cancellation_requested(): raise PipelineCancellation("cancelled before YouTube thumbnail update")
        if not record.thumbnail_applied:
            if provider.authenticated_channel_id() != channel:
                raise ProviderAuthenticationError("authenticated YouTube channel changed before thumbnail update")
            self._ensure_ownership(force=True)
            provider.set_thumbnail(str(record.remote_video_id), str(package["thumbnail"]["path"]))
            self._ensure_ownership(force=True)
            record = self.publications.update(identity, thumbnail_applied=True, state="thumbnail_applied")
        # Upload mutations are complete. M14 performs the first read-only health check separately.
        self.publications.update(identity, state="verification_pending")
        self._transition(job, JobState.PUBLISHING, approvals=frozenset({ApprovalGate.PUBLISH})) if job.state is JobState.PUBLICATION_READY else None
        if job.state is JobState.PUBLISHING: self._transition(job, JobState.PUBLICATION_VERIFICATION_PENDING)

    def _verify_publication(self, job: PipelineJob, cancellation_requested: Callable[[], bool] | None) -> None:
        """M14's strictly read-only remote reconciliation boundary."""
        if not self.verification_config.enabled:
            self._transition(job, JobState.PUBLICATION_RECONCILING); return
        if cancellation_requested and cancellation_requested():
            raise PipelineCancellation("cancelled before publication reconciliation")
        package = self._required_json(job.id, JobState.PUBLICATION_PREPARING, "publication_package")
        identity = publication_identity({"package_identity": package["publication_identity"], "channel_id": self.youtube_config.expected_channel_id, "privacy": self.youtube_config.privacy, "implementation_version": self.youtube_config.implementation_version})
        record = self.publications.get(identity)
        if record is None or not record.remote_video_id or record.package_identity != str(package["publication_identity"]):
            raise ProviderValidationError("publication identity is inconsistent; manual reconciliation required")
        provider = self.publisher
        if not hasattr(provider, "fetch_publication_snapshot"):
            raise ProviderValidationError("configured publisher cannot perform read-only publication reconciliation")
        snapshot: RemotePublicationSnapshot = provider.fetch_publication_snapshot(str(record.remote_video_id))
        if cancellation_requested and cancellation_requested():
            raise PipelineCancellation("cancelled after publication reconciliation")
        health, drift, message = self._publication_health(package, record.created_at, snapshot)
        self._ensure_ownership(force=True)
        self.publications.observe(identity, health, snapshot.model_dump(mode="json"), drift)
        self.publications.update(identity, state=health, error_message=message)
        if health == "healthy":
            self._transition(job, JobState.PUBLICATION_RECONCILING); return
        if health == "pending": return
        raise ProviderValidationError(message or f"publication health is {health}")

    def _publication_health(self, package: dict[str, object], created_at: datetime, snapshot: RemotePublicationSnapshot) -> tuple[str, dict[str, object], str | None]:
        if not snapshot.exists:
            return "remote_missing", {}, "recorded remote video is missing; TubeForge will not recreate it"
        if snapshot.processing is RemoteProcessingState.FAILED:
            return "failed", {}, snapshot.processing_reason or "YouTube processing failed"
        if snapshot.processing in {RemoteProcessingState.PROCESSING, RemoteProcessingState.UNKNOWN}:
            elapsed = (datetime.now(UTC) - created_at).total_seconds()
            if elapsed > self.verification_config.maximum_processing_wait_seconds:
                return "intervention_required", {}, "YouTube processing exceeded the configured wait limit"
            return "pending", {}, None
        expected = package["metadata"]
        drift: dict[str, object] = {}
        if snapshot.privacy is None or snapshot.privacy.value != self.youtube_config.privacy: drift["privacy"] = {"expected": self.youtube_config.privacy, "observed": snapshot.privacy.value if snapshot.privacy else None}
        if snapshot.title != expected["title"]: drift["title"] = {"expected": expected["title"], "observed": snapshot.title}
        if snapshot.description != expected["description"]: drift["description"] = {"expected": expected["description"], "observed": snapshot.description}
        if snapshot.tags is not None and {tag.casefold() for tag in snapshot.tags} != {str(tag).casefold() for tag in expected["tags"]}: drift["tags"] = {"expected": expected["tags"], "observed": list(snapshot.tags)}
        # Exact thumbnail bytes cannot be proven through Data API; missing metadata is a known problem.
        if snapshot.thumbnail_present is False: drift["thumbnail"] = {"expected": "present", "observed": "absent"}
        if drift: return "drift_detected", drift, "remote publication differs from approved package"
        return "healthy", {"thumbnail": "verification_limited" if snapshot.thumbnail_present is None else "present"}, None

    def _publication_checkpoints(self, job: PipelineJob, cancellation_requested: Callable[[], bool] | None) -> None:
        """Build independent, locally validated M12 metadata and thumbnail checkpoints."""
        final = self._required_artifact(job.id, JobState.FINAL_RENDERING, "final")
        final_manifest = self._required_json(job.id, JobState.FINAL_RENDERING, "final_manifest")
        content = self._required_artifact(job.id, JobState.CONTENT_GENERATING, "content_package")
        package = ContentPackage.model_validate(self._required_json(job.id, JobState.CONTENT_GENERATING, "content_package"))
        timing = self._required_json(job.id, JobState.VOICE_GENERATION, "timing_map")
        metadata_inputs = {"content_identity": content.checksum_sha256, "final_render_identity": final_manifest.get("render_identity"), "generator": {"provider": "deterministic-local", "model": None}, "template_version": self.publication_config.metadata_template_version, "config": self.publication_config.model_dump(mode="json", include={"title_max_length", "description_max_length", "tag_max_count", "tag_max_length", "tag_payload_max_length", "metadata_template_version"}), "timing_identity": self._required_artifact(job.id, JobState.VOICE_GENERATION, "timing_map").checksum_sha256}
        metadata_identity = publication_identity(metadata_inputs)
        current = self._load_json_artifact(job.id, JobState.PUBLICATION_PREPARING, "metadata")
        if current is None or current.get("metadata_identity") != metadata_identity:
            data = metadata_from_package(package, timing, self.publication_config)
            self._replace_json(job.id, JobState.PUBLICATION_PREPARING, "metadata", {**data, "metadata_identity": metadata_identity, "provenance": {**metadata_inputs, "validation": data["validation"]}})
        metadata = self._required_json(job.id, JobState.PUBLICATION_PREPARING, "metadata")
        assets = self._required_json(job.id, JobState.ASSET_ACQUISITION, "asset_manifest").get("scenes", {})
        if not isinstance(assets, dict) or not assets or any(not self._accepted_asset_valid(value) for value in assets.values()):
            raise ProviderValidationError("thumbnail requires currently approved source assets")
        thumbnail_inputs = {"asset_identities": sorted(str(value["checksum_sha256"]) for value in assets.values()), "content_identity": content.checksum_sha256, "title": metadata["title"], "template_version": self.publication_config.thumbnail_template_version, "dimensions": [self.publication_config.thumbnail_width, self.publication_config.thumbnail_height], "renderer_version": "m12-local-png-v1"}
        thumbnail_identity = publication_identity(thumbnail_inputs)
        thumbnail = self._valid_artifact(job.id, JobState.PUBLICATION_PREPARING, "thumbnail")
        thumbnail_manifest = self._load_json_artifact(job.id, JobState.PUBLICATION_PREPARING, "thumbnail_provenance")
        reusable = thumbnail is not None and thumbnail_manifest is not None and thumbnail_manifest.get("thumbnail_identity") == thumbnail_identity
        if reusable:
            validate_thumbnail(Path(thumbnail.path), self.publication_config)
        else:
            if cancellation_requested and cancellation_requested():
                raise PipelineCancellation("cancelled before thumbnail generation")
            output = self._artifact_path(job.id, "thumbnail.png")
            temporary = output.with_suffix(".png.tmp")
            try:
                render_thumbnail(temporary, thumbnail_identity=thumbnail_identity, title=str(metadata["title"]), width=self.publication_config.thumbnail_width, height=self.publication_config.thumbnail_height)
                validation = validate_thumbnail(temporary, self.publication_config)
                if cancellation_requested and cancellation_requested():
                    raise PipelineCancellation("cancelled before thumbnail promotion")
                temporary.replace(output)
                thumbnail = self._save_file(job.id, JobState.PUBLICATION_PREPARING, "thumbnail", output, {"thumbnail_identity": thumbnail_identity, **thumbnail_inputs, **validation})
                self._replace_json(job.id, JobState.PUBLICATION_PREPARING, "thumbnail_provenance", {"thumbnail_identity": thumbnail_identity, "artifact_checksum": thumbnail.checksum_sha256, **thumbnail_inputs, **validation})
            finally:
                temporary.unlink(missing_ok=True)
        self._replace_json(job.id, JobState.PUBLICATION_PREPARING, "publication_package", self._publication_package(job, final=final, metadata=metadata))

    def _publication_package(self, job: PipelineJob, *, final: Artifact | None = None, metadata: dict[str, object] | None = None) -> dict[str, object]:
        final = final or self._required_artifact(job.id, JobState.FINAL_RENDERING, "final")
        final_manifest = self._required_json(job.id, JobState.FINAL_RENDERING, "final_manifest")
        metadata = metadata or self._required_json(job.id, JobState.PUBLICATION_PREPARING, "metadata")
        thumbnail = self._required_artifact(job.id, JobState.PUBLICATION_PREPARING, "thumbnail")
        thumbnail_provenance = self._required_json(job.id, JobState.PUBLICATION_PREPARING, "thumbnail_provenance")
        value = {"final_video": {"path": final.path, "checksum_sha256": final.checksum_sha256, "render_identity": final_manifest.get("render_identity")}, "metadata": {key: metadata[key] for key in ("title", "description", "tags", "chapters", "metadata_identity")}, "thumbnail": {"path": thumbnail.path, "checksum_sha256": thumbnail.checksum_sha256, "thumbnail_identity": thumbnail_provenance["thumbnail_identity"]}, "provenance": {"metadata": metadata["provenance"], "thumbnail": thumbnail_provenance}}
        return {**value, "publication_identity": publication_identity(value), "effective_approval_id": None}

    def _render_checkpoint(self, job: PipelineJob, renderer: PreviewRenderer, stage: JobState, name: str, filename: str, cancellation_requested: Callable[[], bool] | None, *, approval_identity: str | None = None, approval_id: str | None = None) -> tuple[Artifact, str]:
        """Render only after every source checkpoint has been revalidated."""
        segments, narration, captions, input_identity, inputs = self._render_inputs(job, renderer)
        source_render_identity = self._render_identity(
            renderer, segments, narration, captions, input_identity, approval_identity,
        )
        existing = self._valid_artifact(job.id, stage, name)
        manifest = self._load_json_artifact(job.id, stage, f"{name}_manifest")
        if existing and manifest and manifest.get("source_render_identity") == source_render_identity and manifest.get("input_identity") == input_identity and manifest.get("renderer_template_version") == renderer.template_version:
            renderer.validate(Path(existing.path), segments[-1].end_seconds)
            return existing, str(manifest["render_identity"])
        output = self._artifact_path(job.id, filename)
        self._ensure_ownership(force=True)
        result = renderer.render(segments, Path(narration.path), Path(captions.path), output, cancellation_requested=cancellation_requested)
        self._ensure_ownership(force=True)
        identity = hashlib.sha256(json.dumps({"source_render_identity": source_render_identity, "artifact_checksum": result["checksum_sha256"], "render_instance": uuid.uuid4().hex}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        provenance = {"render_identity": identity, "source_render_identity": source_render_identity, "renderer_template_version": renderer.template_version, "input_identity": input_identity, "inputs": inputs, "probe": result["metadata"], "validation": result["metadata"], "command": result["command"], "approval_identity": approval_identity, "approval_id": approval_id}
        artifact = self._save_artifact(Artifact(job.id, stage, name, str(output), str(result["checksum_sha256"]), provenance))
        self._replace_json(job.id, stage, f"{name}_manifest", {**provenance, "artifact_checksum": artifact.checksum_sha256})
        return artifact, identity

    def _render_inputs(self, job: PipelineJob, renderer: PreviewRenderer) -> tuple[tuple, Artifact, Artifact, str, dict[str, object]]:
        """Return checksummed render inputs used to bind preview approval."""
        content = self._required_artifact(job.id, JobState.CONTENT_GENERATING, "content_package")
        package = ContentPackage.model_validate(self._required_json(job.id, JobState.CONTENT_GENERATING, "content_package"))
        narration = self._required_artifact(job.id, JobState.VOICE_GENERATION, "narration")
        captions = self._required_artifact(job.id, JobState.CAPTION_GENERATION, "captions")
        timing_artifact = self._required_artifact(job.id, JobState.VOICE_GENERATION, "timing_map")
        timing = self._required_json(job.id, JobState.VOICE_GENERATION, "timing_map")
        assets = self._required_json(job.id, JobState.ASSET_ACQUISITION, "asset_manifest").get("scenes")
        if not isinstance(assets, dict): raise ProviderValidationError("accepted asset manifest is invalid")
        if any(not self._accepted_asset_valid(value) for value in assets.values()): raise ProviderValidationError("accepted asset was modified or is unsafe")
        segments = build_timeline(package, timing, assets, tolerance=renderer.config.sync_tolerance_seconds)
        inputs = {"content": content.checksum_sha256, "timing_map": timing_artifact.checksum_sha256, "narration": narration.checksum_sha256, "captions": captions.checksum_sha256, "assets": [{"scene_id": segment.scene_id, "checksum_sha256": segment.asset_checksum} for segment in segments]}
        input_identity = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return segments, narration, captions, input_identity, inputs

    def _preview_is_current(self, job: PipelineJob) -> bool:
        """Fail closed when the approved preview or any of its inputs changed."""
        try:
            preview = self._required_artifact(job.id, JobState.PREVIEW_RENDERING, "preview")
            manifest = self._required_json(job.id, JobState.PREVIEW_RENDERING, "preview_manifest")
            segments, narration, captions, input_identity, inputs = self._render_inputs(job, self.preview_renderer)
            expected_source_identity = self._render_identity(
                self.preview_renderer, segments, narration, captions, input_identity,
            )
            if manifest.get("artifact_checksum") != preview.checksum_sha256:
                return False
            if manifest.get("input_identity") != input_identity or manifest.get("inputs") != inputs:
                return False
            if manifest.get("source_render_identity") != expected_source_identity or manifest.get("renderer_template_version") != self.preview_renderer.template_version:
                return False
            self.preview_renderer.validate(Path(preview.path), segments[-1].end_seconds)
            return True
        except ProviderValidationError:
            return False

    @staticmethod
    def _render_identity(renderer: PreviewRenderer, segments: tuple, narration: Artifact, captions: Artifact, input_identity: str, approval_identity: str | None = None) -> str:
        """Bind renderer settings and every durable input into one render identity."""
        renderer_identity = renderer.identity(
            segments, Path(narration.path), Path(captions.path), approval_identity=approval_identity,
        )
        material = {"renderer_identity": renderer_identity, "input_identity": input_identity}
        return hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def _transition(self, job: PipelineJob, target: JobState, **kwargs: object) -> None:
        snapshot = self.machine.transition(PipelineSnapshot(job.state, job.resume_state), target, **kwargs)
        self._update_state(job.id, snapshot.state, snapshot.resume_state)

    def _ensure_ownership(self, *, force: bool = False) -> None:
        check = _ownership_check.get()
        if check is not None and not check(force=force):
            raise PipelineOwnershipLost("worker lease ownership was lost")

    def _update_state(self, job_id: str, state: JobState, resume_state: JobState | None = None, failure_message: str | None = None) -> None:
        self._ensure_ownership(force=True)
        check = _ownership_check.get()
        if check is None:
            self.jobs.update_state(job_id, state, resume_state, failure_message)
            return
        worker_id, clock = self._ownership_context(check)
        if worker_id is None:
            raise PipelineOwnershipLost("worker ownership callback does not identify its owner")
        now = clock()
        result = self.jobs.update_state_if_claimed(job_id, worker_id, now=now, state=state, resume_state=resume_state, failure_message=failure_message)
        if result is None:
            raise PipelineOwnershipLost("worker lease ownership was lost before state transition")

    def _artifact_path(self, job_id: str, filename: str) -> Path:
        return self.artifact_root / job_id / filename

    def _checkpoint_generated(self, job_id: str, stage: JobState, name: str, filename: str, contents: str) -> Artifact:
        existing = self._valid_artifact(job_id, stage, name)
        encoded = contents.encode()
        if existing and Path(existing.path).read_bytes() == encoded:
            return existing
        self._ensure_ownership(force=True)
        path = self._artifact_path(job_id, filename)
        self._atomic_write(path, encoded)
        return self._save_artifact(Artifact(job_id, stage, name, str(path), self._checksum(path), {"generator": "deterministic"}))

    def _checkpoint_json(self, job_id: str, stage: JobState, name: str, value: object) -> Artifact:
        return self._checkpoint_generated(job_id, stage, name, f"{name}.json", json.dumps(value, sort_keys=True))

    def _replace_json(self, job_id: str, stage: JobState, name: str, value: object) -> Artifact:
        path = self._artifact_path(job_id, f"{name}.json")
        contents = json.dumps(value, sort_keys=True).encode()
        self._ensure_ownership(force=True)
        if not path.is_file() or path.read_bytes() != contents:
            self._atomic_write(path, contents)
        return self._save_artifact(Artifact(job_id, stage, name, str(path), self._checksum(path), {"generator": "deterministic"}))

    def _save_file(self, job_id: str, stage: JobState, name: str, path: Path, provenance: dict[str, object]) -> Artifact:
        if not path.is_file() or path.stat().st_size == 0:
            raise ProviderValidationError(f"generated artifact missing or empty: {name}")
        self._ensure_ownership(force=True)
        return self._save_artifact(Artifact(job_id, stage, name, str(path), self._checksum(path), provenance))

    def _save_artifact(self, artifact: Artifact) -> Artifact:
        self._ensure_ownership(force=True)
        check = _ownership_check.get()
        if check is None:
            return self.artifacts.save(artifact)
        worker_id, clock = self._ownership_context(check)
        now = clock()
        if worker_id is None:
            raise PipelineOwnershipLost("worker ownership callback does not identify its owner")
        saved = self.artifacts.save_if_claimed(artifact, worker_id, now=now)
        if saved is None:
            raise PipelineOwnershipLost("worker lease ownership was lost before checkpoint promotion")
        return saved

    @staticmethod
    def _ownership_context(check: Callable[..., bool]) -> tuple[str | None, Callable[[], datetime]]:
        """Read ownership metadata from either a callback or its bound object."""
        owner = getattr(check, "__self__", None)
        worker_id = getattr(check, "worker_id", None) or getattr(owner, "worker_id", None)
        clock = getattr(check, "clock", None) or getattr(owner, "clock", None) or (lambda: datetime.now(UTC))
        return worker_id, clock

    def _effective_content_request(self, job: PipelineJob) -> ContentRequest:
        """Checkpoint the exact, provenance-bearing request used for generation.

        Offline/fake runs retain operator-supplied metadata without network I/O.
        When source ingestion is enabled, immutable bounded snapshots replace
        those references before the content adapter receives the request.
        """
        existing = self._load_json_artifact(job.id, JobState.CONTENT_GENERATING, "effective_content_request")
        if existing is not None:
            return ContentRequest.model_validate(existing)

        packet = self._load_json_artifact(job.id, JobState.CONTENT_GENERATING, "source_packet")
        if packet is None:
            if self.source_ingestor is None:
                packet = {
                    "schema_version": "1.0",
                    "retrieval_mode": "operator_supplied",
                    "sources": [source.model_dump(mode="json") for source in job.request.sources],
                }
            else:
                snapshots = tuple(self.source_ingestor.ingest(source) for source in job.request.sources)
                packet = {"retrieval_mode": "fetched", **source_packet(snapshots)}
            self._checkpoint_json(job.id, JobState.CONTENT_GENERATING, "source_packet", packet)

        sources = packet.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ProviderValidationError("source packet contains no usable sources")
        allowed = set(SourceReference.model_fields)
        references = tuple(
            SourceReference.model_validate({key: value for key, value in item.items() if key in allowed})
            for item in sources if isinstance(item, dict)
        )
        if not references:
            raise ProviderValidationError("source packet contains no valid source references")
        request = job.request.model_copy(update={"sources": references})
        self._checkpoint_json(job.id, JobState.CONTENT_GENERATING, "effective_content_request", request.model_dump(mode="json"))
        return request

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
        self._ensure_ownership(force=True)
        key = f"{job.id}:{operation}"
        if self.external_operations is not None:
            receipt = self.external_operations.receipt(key)
            if receipt is not None:
                from tubeforge.domain.contracts import PublishResult
                return PublishResult.model_validate(receipt)
            if not self.external_operations.reserve(job.id, operation, key):
                raise ProviderValidationError(f"external operation pending reconciliation: {operation}")
        self._ensure_ownership(force=True)
        result = self.publisher.upload(PublishRequest(platform="youtube", artifact_path=path, metadata=self._metadata(job), privacy=privacy, idempotency_key=key, public_publish_approval_id=approval_id))
        self._ensure_ownership(force=True)
        if self.external_operations is not None:
            self.external_operations.complete(key, result.model_dump(mode="json"))
        return result
