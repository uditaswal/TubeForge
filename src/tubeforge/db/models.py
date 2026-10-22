"""SQLAlchemy declarative metadata for TubeForge persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    """Base class for future persisted domain models."""


class TopicRecord(Base):
    """Operator backlog item, reserved atomically before a generation is made."""

    __tablename__ = "topics"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready", index=True)
    options_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    generation_job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    reserved_by: Mapped[str | None] = mapped_column(String(128))
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    failure_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AdminUserRecord(Base):
    __tablename__ = "admin_users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    disabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuthSessionRecord(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SocialAccountRecord(Base):
    """Non-secret destination identity; credential payload is encrypted separately."""
    __tablename__ = "social_accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    default_description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    external_account_id: Mapped[str | None] = mapped_column(String(300), index=True)
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False)
    credential_ciphertext: Mapped[str | None] = mapped_column(Text)
    credential_refresh_owner: Mapped[str | None] = mapped_column(String(128))
    credential_refresh_fence: Mapped[str | None] = mapped_column(String(64))
    credential_refresh_lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unconfigured")
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    is_default: Mapped[bool] = mapped_column(nullable=False, default=False)
    disabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VideoDestinationIntentRecord(Base):
    """Local destination and metadata snapshot captured with a generation job."""
    __tablename__ = "video_destination_intents"
    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OAuthConnectionRecord(Base):
    """One short-lived, single-use authorization attempt bound to a Studio session."""
    __tablename__ = "oauth_connections"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(64))
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    verifier_ciphertext: Mapped[str | None] = mapped_column(Text)
    redirect_uri: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    candidate_external_id: Mapped[str | None] = mapped_column(String(300))
    candidate_label: Mapped[str | None] = mapped_column(String(200))
    candidate_credential_ciphertext: Mapped[str | None] = mapped_column(Text)
    candidate_scopes_json: Mapped[str | None] = mapped_column(Text)
    candidate_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublishingAssetRecord(Base):
    """Immutable canonical media copy shared by manual and scheduled delivery."""
    __tablename__ = "publishing_assets"
    __table_args__ = (UniqueConstraint("sha256", name="uq_publishing_assets_sha256"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    staged_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublishJobRecord(Base):
    """One manual or automated selection of a canonical asset."""
    __tablename__ = "publish_jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    asset_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    edition: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_identity: Mapped[str | None] = mapped_column(String(64))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[str | None] = mapped_column(String(64))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DestinationDeliveryRecord(Base):
    """One durable delivery identity shared by manual and automation paths."""
    __tablename__ = "destination_deliveries"
    __table_args__ = (UniqueConstraint("asset_id", "account_id", "edition", name="uq_destination_delivery_identity"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    publish_job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(300), nullable=False)
    edition: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    required: Mapped[bool] = mapped_column(nullable=False, default=True)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    remote_id: Mapped[str | None] = mapped_column(String(500))
    remote_url: Mapped[str | None] = mapped_column(Text)
    remote_session_id: Mapped[str | None] = mapped_column(Text)
    requested_action: Mapped[str | None] = mapped_column(String(32))
    requested_by: Mapped[str | None] = mapped_column(String(64))
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    claim_owner: Mapped[str | None] = mapped_column(String(128))
    claim_token: Mapped[str | None] = mapped_column(String(64))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DeliveryAttemptRecord(Base):
    """Audit trail for one fenced upload attempt or read-only verification."""
    __tablename__ = "delivery_attempts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    delivery_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    claim_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    remote_session_id: Mapped[str | None] = mapped_column(Text)
    remote_id: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PublisherWorkerHeartbeatRecord(Base):
    """Current publisher process presence, separate from delivery claim leases."""
    __tablename__ = "publisher_worker_heartbeats"
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    platforms_json: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class PublicationAttemptRecord(Base):
    __tablename__ = "publication_attempts"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_publication_attempts_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    remote_id: Mapped[str | None] = mapped_column(String(500))
    remote_url: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_eligible: Mapped[bool] = mapped_column(nullable=False, default=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScheduleRecord(Base):
    """Durable cron trigger; scheduling work is separate from worker execution."""

    __tablename__ = "schedules"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    cron: Mapped[str] = mapped_column(String(120), nullable=False)
    timezone: Mapped[str] = mapped_column(String(100), nullable=False, default="UTC")
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    options_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ScheduleRunRecord(Base):
    """Immutable schedule history and duplicate-fire fence."""

    __tablename__ = "schedule_runs"
    __table_args__ = (UniqueConstraint("schedule_id", "run_key", name="uq_schedule_runs_schedule_key"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    schedule_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_key: Mapped[str] = mapped_column(String(120), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    topic_id: Mapped[str | None] = mapped_column(String(64), index=True)
    job_id: Mapped[str | None] = mapped_column(String(64), index=True)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PipelineJobRecord(Base):
    """Durable state and request data for one deterministic pipeline run."""

    __tablename__ = "pipeline_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    video_description: Mapped[str | None] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(64), nullable=False)
    resume_state: Mapped[str | None] = mapped_column(String(64))
    failure_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claim_owner: Mapped[str | None] = mapped_column(String(128))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    authentication_restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HeavyWorkLeaseRecord(Base):
    """One durable admission lease for resource-intensive pipeline execution."""

    __tablename__ = "heavy_work_leases"

    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str | None] = mapped_column(String(128))
    acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class ExternalOperationRecord(Base):
    """Durable idempotency reservation and receipt for external side effects."""

    __tablename__ = "external_operations"
    __table_args__ = (UniqueConstraint("idempotency_key", name="uq_external_operations_idempotency_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    receipt_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ArtifactRecord(Base):
    """A validated checkpoint artifact; binaries remain on disk."""

    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class JobEventRecord(Base):
    """Immutable operator-facing lifecycle history for one generation."""

    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class SourceMediaRecord(Base):
    """Normalized, non-binary provenance for a source-video job."""

    __tablename__ = "source_media"
    __table_args__ = (UniqueConstraint("job_id", name="uq_source_media_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(300), index=True)
    creator_id: Mapped[str | None] = mapped_column(String(300), index=True)
    title: Mapped[str | None] = mapped_column(String(500))
    duration_seconds: Mapped[float | None] = mapped_column()
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CreatorSourceRecord(Base):
    """Future scheduler input; no polling worker is enabled by this milestone."""

    __tablename__ = "creator_sources"
    __table_args__ = (UniqueConstraint("provider", "creator_url", name="uq_creator_sources_provider_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    creator_url: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    check_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_content_id: Mapped[str | None] = mapped_column(String(300))
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublicationRecord(Base):
    """Non-secret durable progress for one external publication intent."""
    __tablename__ = "publications"
    __table_args__ = (UniqueConstraint("publication_identity", name="uq_publications_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    publication_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    package_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    remote_video_id: Mapped[str | None] = mapped_column(String(200))
    metadata_applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    thumbnail_applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublicationObservationRecord(Base):
    """Compact append-only M14 remote observations; contains no credentials."""
    __tablename__ = "publication_observations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    health: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    drift_json: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AnalyticsSnapshotRecord(Base):
    """Append-only M15 normalized observations, keyed to prevent retry duplicates."""
    __tablename__ = "analytics_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_identity", name="uq_analytics_snapshots_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    remote_video_id: Mapped[str] = mapped_column(String(200), nullable=False)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False)
    snapshot_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    report_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    report_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    views: Mapped[int | None] = mapped_column(Integer)
    impressions: Mapped[int | None] = mapped_column(Integer)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    provenance_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PerformanceEvaluationRecord(Base):
    __tablename__ = "performance_evaluations"
    __table_args__ = (UniqueConstraint("evaluation_identity", name="uq_performance_evaluations_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evaluation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_identities_json: Mapped[str] = mapped_column(Text, nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    dimensions_json: Mapped[str] = mapped_column(Text, nullable=False)
    derived_metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    recommendations_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OptimizationProposalRecord(Base):
    __tablename__ = "optimization_proposals"
    __table_args__ = (UniqueConstraint("proposal_identity", name="uq_optimization_proposals_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    remote_video_id: Mapped[str] = mapped_column(String(200), nullable=False)
    evaluation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale_json: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OptimizationCandidateSetRecord(Base):
    __tablename__ = "optimization_candidate_sets"
    __table_args__ = (UniqueConstraint("generation_identity", name="uq_optimization_candidate_sets_generation"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    proposal_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    template_version: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OptimizationCandidateRecord(Base):
    __tablename__ = "optimization_candidates"
    __table_args__ = (UniqueConstraint("candidate_identity", name="uq_optimization_candidates_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_set_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    publication_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    proposal_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500))
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    thumbnail_identity: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OptimizationExecutionRecord(Base):
    __tablename__ = "optimization_executions"
    __table_args__ = (UniqueConstraint("execution_identity", name="uq_optimization_executions_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    candidate_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    title_applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    thumbnail_applied: Mapped[bool] = mapped_column(nullable=False, default=False)
    prechange_json: Mapped[str] = mapped_column(Text, nullable=False)
    preview_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OptimizationExperimentRecord(Base):
    __tablename__ = "optimization_experiments"
    __table_args__ = (UniqueConstraint("execution_identity", name="uq_optimization_experiments_execution"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    publication_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    candidate_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    proposal_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_snapshot_identity: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_dimensions: Mapped[str] = mapped_column(String(64), nullable=False)
    experiment_version: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class ExperimentOutcomeRecord(Base):
    __tablename__ = "experiment_outcomes"
    __table_args__ = (UniqueConstraint("outcome_identity", name="uq_experiment_outcomes_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    outcome_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    baseline_snapshot_identity: Mapped[str | None] = mapped_column(String(64))
    post_snapshot_identities_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class LearningEventRecord(Base):
    __tablename__ = "learning_events"
    __table_args__ = (UniqueConstraint("event_identity", name="uq_learning_events_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class ChannelBaselineRecord(Base):
    __tablename__ = "channel_baselines"
    __table_args__ = (UniqueConstraint("baseline_identity", name="uq_channel_baselines_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    baseline_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_version: Mapped[str] = mapped_column(String(100), nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    statistics_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class NextVideoRecommendationRecord(Base):
    __tablename__ = "next_video_recommendations"
    __table_args__ = (UniqueConstraint("recommendation_identity", name="uq_next_video_recommendations_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    recommendation_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    recommendation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    recommendation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class NextVideoBriefRecord(Base):
    __tablename__ = "next_video_briefs"
    __table_args__ = (UniqueConstraint("brief_identity", name="uq_next_video_briefs_identity"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    brief_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    recommendation_identities_json: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssetCacheRecord(Base):
    """Durable single-writer reservation for validated on-disk media."""
    __tablename__ = "asset_cache"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_asset_cache_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    reservation_token: Mapped[str | None] = mapped_column(String(64))
    reservation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    path: Mapped[str | None] = mapped_column(Text)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[str | None] = mapped_column(Text)
    failure_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalRecord(Base):
    """An immutable approved/rejected gate decision for a job."""

    __tablename__ = "approvals"
    # SQL unique constraints allow multiple NULL values.  Keep the nullable
    # public identity for legacy records, but constrain a normalized key.
    __table_args__ = (UniqueConstraint("job_id", "gate", "decision_identity", name="uq_approvals_decision"),)

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    gate: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str | None] = mapped_column(String(200))
    reviewed_identity: Mapped[str | None] = mapped_column(String(64), index=True)
    decision_identity: Mapped[str] = mapped_column(String(64), nullable=False, server_default="")
    audit_json: Mapped[str | None] = mapped_column(Text)


class GenerationCacheRecord(Base):
    """A single-writer reservation and accepted content generation by cache key."""

    __tablename__ = "generation_cache"
    __table_args__ = (UniqueConstraint("cache_key", name="uq_generation_cache_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_request_json: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    reservation_token: Mapped[str | None] = mapped_column(String(64))
    reservation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    package_json: Mapped[str | None] = mapped_column(Text)
    provenance_json: Mapped[str | None] = mapped_column(Text)
    usage_json: Mapped[str | None] = mapped_column(Text)
    invocation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
