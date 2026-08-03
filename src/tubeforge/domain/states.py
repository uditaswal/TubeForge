"""Enums shared by the deterministic pipeline and its future persistence layer."""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Lifecycle classification of a job without naming its current stage."""

    ACTIVE = "active"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class PipelineStage(StrEnum):
    """Normal Phase 1 workflow stages, in their only forward order."""

    TOPIC_CREATED = "topic_created"
    CONTENT_GENERATING = "content_generating"
    CONTENT_READY = "content_ready"
    SCRIPT_APPROVAL_REQUIRED = "script_approval_required"
    ASSET_ACQUISITION = "asset_acquisition"
    ASSETS_READY = "assets_ready"
    VOICE_GENERATION = "voice_generation"
    VOICE_READY = "voice_ready"
    CAPTION_GENERATION = "caption_generation"
    PREVIEW_RENDERING = "preview_rendering"
    PREVIEW_APPROVAL_REQUIRED = "preview_approval_required"
    FINAL_RENDERING = "final_rendering"
    PRIVATE_UPLOAD_READY = "private_upload_ready"
    PRIVATE_UPLOADING = "private_uploading"
    PUBLISH_APPROVAL_REQUIRED = "publish_approval_required"
    PUBLISHED = "published"


class JobState(StrEnum):
    """All state-machine states, including recoverable and terminal outcomes."""

    TOPIC_CREATED = PipelineStage.TOPIC_CREATED
    CONTENT_GENERATING = PipelineStage.CONTENT_GENERATING
    CONTENT_READY = PipelineStage.CONTENT_READY
    SCRIPT_APPROVAL_REQUIRED = PipelineStage.SCRIPT_APPROVAL_REQUIRED
    ASSET_ACQUISITION = PipelineStage.ASSET_ACQUISITION
    ASSETS_READY = PipelineStage.ASSETS_READY
    VOICE_GENERATION = PipelineStage.VOICE_GENERATION
    VOICE_READY = PipelineStage.VOICE_READY
    CAPTION_GENERATION = PipelineStage.CAPTION_GENERATION
    PREVIEW_RENDERING = PipelineStage.PREVIEW_RENDERING
    PREVIEW_APPROVAL_REQUIRED = PipelineStage.PREVIEW_APPROVAL_REQUIRED
    FINAL_RENDERING = PipelineStage.FINAL_RENDERING
    PRIVATE_UPLOAD_READY = PipelineStage.PRIVATE_UPLOAD_READY
    PRIVATE_UPLOADING = PipelineStage.PRIVATE_UPLOADING
    PUBLISH_APPROVAL_REQUIRED = PipelineStage.PUBLISH_APPROVAL_REQUIRED
    PUBLISHED = PipelineStage.PUBLISHED
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_VALIDATION = "failed_validation"
    AUTH_REQUIRED = "auth_required"
    FAILED_EXHAUSTED = "failed_exhausted"
    CANCELLED = "cancelled"


class ApprovalGate(StrEnum):
    """Human decisions that must be recorded independently."""

    SCRIPT = "script"
    PREVIEW = "preview"
    PUBLIC_PUBLISH = "public_publish"


class ApprovalStatus(StrEnum):
    """Status of an immutable human approval decision."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class FailureStatus(StrEnum):
    """Failure classifications used for deterministic recovery policy."""

    RETRYABLE = "retryable"
    VALIDATION = "validation"
    AUTH_REQUIRED = "auth_required"
    CANCELLED = "cancelled"
