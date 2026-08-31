"""Small transaction-scoped repositories for deterministic pipeline state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets

from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.domain.contracts import ContentRequest
from tubeforge.domain.states import ApprovalGate, ApprovalStatus, JobState
from tubeforge.db.models import AnalyticsSnapshotRecord, ApprovalRecord, ArtifactRecord, AssetCacheRecord, ChannelBaselineRecord, CreatorSourceRecord, ExperimentOutcomeRecord, ExternalOperationRecord, GenerationCacheRecord, HeavyWorkLeaseRecord, JobEventRecord, LearningEventRecord, NextVideoBriefRecord, NextVideoRecommendationRecord, OptimizationCandidateRecord, OptimizationCandidateSetRecord, OptimizationExecutionRecord, OptimizationExperimentRecord, OptimizationProposalRecord, PerformanceEvaluationRecord, PipelineJobRecord, PublicationObservationRecord, PublicationRecord, SourceMediaRecord


@dataclass(frozen=True, slots=True)
class PipelineJob:
    id: str
    request: ContentRequest
    state: JobState
    resume_state: JobState | None
    failure_message: str | None
    claim_owner: str | None = None
    attempt_count: int = 0
    next_retry_at: datetime | None = None
    cancellation_requested_at: datetime | None = None
    authentication_restored_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Artifact:
    job_id: str
    stage: JobState
    name: str
    path: str
    checksum_sha256: str
    provenance: dict[str, object]


@dataclass(frozen=True, slots=True)
class JobEvent:
    id: int
    job_id: str
    event_type: str
    details: dict[str, object]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SourceMedia:
    job_id: str
    provider: str
    source_url: str
    external_id: str | None
    creator_id: str | None
    title: str | None
    duration_seconds: float | None
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class GenerationCacheReservation:
    cache_key: str
    token: str


@dataclass(frozen=True, slots=True)
class CachedGeneration:
    package: dict[str, object]
    provenance: dict[str, object]
    usage: dict[str, object]


class JobRepository:
    """Persist jobs without retaining a session across provider work."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create(self, job_id: str, request: ContentRequest) -> PipelineJob:
        now = datetime.now(UTC)
        record = PipelineJobRecord(
            id=job_id, request_json=request.model_dump_json(), state=JobState.TOPIC_CREATED.value,
            resume_state=None, failure_message=None, created_at=now, updated_at=now,
            claim_owner=None, claimed_at=None, lease_expires_at=None, heartbeat_at=None,
            attempt_count=0, next_retry_at=None, cancellation_requested_at=None,
            authentication_restored_at=None,
        )
        try:
            with self._session_factory.begin() as session:
                session.add(record)
        except IntegrityError as error:
            raise ValueError(f"job already exists: {job_id}") from error
        return _job_from_record(record)

    def get(self, job_id: str) -> PipelineJob:
        with self._session_factory() as session:
            record = session.get(PipelineJobRecord, job_id)
            if record is None:
                raise KeyError(f"job not found: {job_id}")
            return _job_from_record(record)

    def list_recent(self, *, limit: int = 50) -> list[PipelineJob]:
        """Return a bounded newest-first view for the private local dashboard."""
        with self._session_factory() as session:
            rows = session.scalars(select(PipelineJobRecord).order_by(PipelineJobRecord.updated_at.desc(), PipelineJobRecord.id.desc()).limit(limit))
            return [_job_from_record(row) for row in rows]

    def delete_completed_or_paused(self, job_id: str) -> list[Artifact]:
        """Remove a non-running local generation and return its registered files.

        A claimed or actively processing job is deliberately never deletable: this
        keeps a worker from writing a checkpoint after its database row vanished.
        Publication states are also excluded because they can represent a remote
        side effect that must remain auditable.
        """
        deletable = {
            JobState.SCRIPT_APPROVAL_REQUIRED,
            JobState.PREVIEW_READY,
            JobState.FINAL_READY,
            JobState.FAILED_RETRYABLE,
            JobState.FAILED_VALIDATION,
            JobState.FAILED_EXHAUSTED,
            JobState.CANCELLED,
        }
        with self._session_factory.begin() as session:
            record = session.get(PipelineJobRecord, job_id)
            if record is None:
                raise KeyError(f"job not found: {job_id}")
            if record.claim_owner is not None or JobState(record.state) not in deletable:
                raise ValueError("only paused, completed, cancelled, or failed local generations can be deleted")
            artifacts = [_artifact_from_record(row) for row in session.scalars(
                select(ArtifactRecord).where(ArtifactRecord.job_id == job_id)
            )]
            session.execute(delete(ApprovalRecord).where(ApprovalRecord.job_id == job_id))
            session.execute(delete(ArtifactRecord).where(ArtifactRecord.job_id == job_id))
            session.execute(delete(ExternalOperationRecord).where(ExternalOperationRecord.job_id == job_id))
            session.execute(delete(SourceMediaRecord).where(SourceMediaRecord.job_id == job_id))
            session.execute(delete(PipelineJobRecord).where(PipelineJobRecord.id == job_id))
            return artifacts

    def claim_oldest_eligible(self, worker_id: str, *, now: datetime, lease_seconds: int) -> PipelineJob | None:
        """Atomically lease the oldest runnable job; provider work occurs after commit.

        The conditional UPDATE is the correctness primitive on SQLite and remains
        valid on PostgreSQL, where callers may additionally benefit from row locks.
        """
        blocked = {
            JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY,
            JobState.PUBLICATION_APPROVAL_REQUIRED, JobState.PUBLICATION_READY, JobState.CANCELLED, JobState.FAILED_VALIDATION,
            JobState.AUTH_REQUIRED, JobState.FAILED_EXHAUSTED,
            JobState.PUBLICATION_VERIFICATION_PENDING,
            JobState.FAILED_RETRYABLE,
            # Retained only so M8 rows remain readable; never resume them
            # automatically because they may represent external side effects.
            JobState.PREVIEW_APPROVAL_REQUIRED, JobState.PRIVATE_UPLOAD_READY,
            JobState.PRIVATE_UPLOADING, JobState.PUBLISH_APPROVAL_REQUIRED,
            JobState.PUBLISHED,
        }
        runnable = [state.value for state in JobState if state not in blocked]
        lease_expiry = now + __import__("datetime").timedelta(seconds=lease_seconds)
        with self._session_factory.begin() as session:
            # Reclaiming abandoned leases is deliberately part of the brief transaction.
            session.execute(update(PipelineJobRecord).where(PipelineJobRecord.lease_expires_at.is_not(None), PipelineJobRecord.lease_expires_at <= now).values(claim_owner=None, claimed_at=None, lease_expires_at=None, heartbeat_at=None))
            def approved(gate: ApprovalGate):
                return exists(
                    select(ApprovalRecord.id).where(
                        ApprovalRecord.job_id == PipelineJobRecord.id,
                        ApprovalRecord.gate == gate.value,
                        ApprovalRecord.status == ApprovalStatus.APPROVED.value,
                    )
                )

            eligible = or_(
                PipelineJobRecord.state.in_(runnable),
                # Only explicit auto-review jobs may re-enter an approval
                # state without a recorded human decision. Manual jobs remain
                # paused and cannot starve automatic work in FIFO order.
                and_(
                    PipelineJobRecord.state.in_([JobState.SCRIPT_APPROVAL_REQUIRED.value, JobState.PREVIEW_READY.value]),
                    func.json_extract(PipelineJobRecord.request_json, "$.review_mode") == "auto",
                ),
                and_(PipelineJobRecord.state == JobState.SCRIPT_APPROVAL_REQUIRED.value, approved(ApprovalGate.SCRIPT)),
                and_(PipelineJobRecord.state == JobState.PREVIEW_READY.value, approved(ApprovalGate.PREVIEW)),
                and_(PipelineJobRecord.state == JobState.PUBLICATION_APPROVAL_REQUIRED.value, approved(ApprovalGate.PUBLICATION_PREPARATION)),
                and_(PipelineJobRecord.state == JobState.PUBLICATION_READY.value, approved(ApprovalGate.PUBLISH)),
                and_(PipelineJobRecord.state == JobState.FAILED_RETRYABLE.value, PipelineJobRecord.next_retry_at <= now),
                and_(PipelineJobRecord.state == JobState.AUTH_REQUIRED.value, PipelineJobRecord.authentication_restored_at.is_not(None)),
                and_(PipelineJobRecord.state == JobState.PUBLICATION_VERIFICATION_PENDING.value, PipelineJobRecord.next_retry_at <= now),
            )
            candidate = session.scalar(select(PipelineJobRecord.id).where(eligible, PipelineJobRecord.claim_owner.is_(None)).order_by(PipelineJobRecord.created_at, PipelineJobRecord.id).limit(1))
            if candidate is None:
                return None
            result = session.execute(update(PipelineJobRecord).where(PipelineJobRecord.id == candidate, PipelineJobRecord.claim_owner.is_(None)).values(claim_owner=worker_id, claimed_at=now, heartbeat_at=now, lease_expires_at=lease_expiry, updated_at=now))
            if result.rowcount != 1:
                return None
            return _job_from_record(session.get(PipelineJobRecord, candidate))

    def heartbeat(self, job_id: str, worker_id: str, *, now: datetime, lease_seconds: int) -> bool:
        with self._session_factory.begin() as session:
            result = session.execute(update(PipelineJobRecord).where(PipelineJobRecord.id == job_id, PipelineJobRecord.claim_owner == worker_id).values(heartbeat_at=now, lease_expires_at=now + __import__("datetime").timedelta(seconds=lease_seconds), updated_at=now))
            return result.rowcount == 1

    def owns_lease(self, job_id: str, worker_id: str, *, now: datetime) -> bool:
        """Return whether this worker still owns an unexpired job claim."""
        with self._session_factory() as session:
            return session.scalar(
                select(PipelineJobRecord.id).where(
                    PipelineJobRecord.id == job_id,
                    PipelineJobRecord.claim_owner == worker_id,
                    PipelineJobRecord.lease_expires_at.is_not(None),
                    PipelineJobRecord.lease_expires_at > now,
                )
            ) is not None

    def update_state_if_claimed(self, job_id: str, worker_id: str, *, now: datetime, state: JobState, resume_state: JobState | None = None, failure_message: str | None = None) -> PipelineJob | None:
        """Persist a transition only while the caller still owns the live lease."""
        with self._session_factory.begin() as session:
            record = session.scalar(
                select(PipelineJobRecord).where(
                    PipelineJobRecord.id == job_id,
                    PipelineJobRecord.claim_owner == worker_id,
                    PipelineJobRecord.lease_expires_at.is_not(None),
                    PipelineJobRecord.lease_expires_at > now,
                )
            )
            if record is None:
                return None
            record.state, record.resume_state, record.failure_message = state.value, (resume_state.value if resume_state else None), failure_message
            record.updated_at = now
            session.flush()
            return _job_from_record(record)

    def release_claim(self, job_id: str, worker_id: str) -> None:
        with self._session_factory.begin() as session:
            session.execute(update(PipelineJobRecord).where(PipelineJobRecord.id == job_id, PipelineJobRecord.claim_owner == worker_id).values(claim_owner=None, claimed_at=None, heartbeat_at=None, lease_expires_at=None))

    def request_cancellation(self, job_id: str, *, now: datetime) -> None:
        with self._session_factory.begin() as session:
            session.execute(update(PipelineJobRecord).where(PipelineJobRecord.id == job_id).values(cancellation_requested_at=now, updated_at=now))

    def mark_authentication_restored(self, job_id: str, *, now: datetime) -> None:
        with self._session_factory.begin() as session:
            session.execute(update(PipelineJobRecord).where(PipelineJobRecord.id == job_id, PipelineJobRecord.state == JobState.AUTH_REQUIRED.value).values(authentication_restored_at=now, updated_at=now))

    def schedule_retry(self, job_id: str, worker_id: str, *, now: datetime, next_retry_at: datetime, exhausted: bool) -> PipelineJob:
        with self._session_factory.begin() as session:
            record = session.get(PipelineJobRecord, job_id)
            if record is None or record.claim_owner != worker_id: raise KeyError(f"job is not claimed by {worker_id}")
            record.attempt_count += 1
            record.state = (JobState.FAILED_EXHAUSTED if exhausted else JobState.FAILED_RETRYABLE).value
            record.next_retry_at = None if exhausted else next_retry_at
            record.claim_owner = record.claimed_at = record.heartbeat_at = record.lease_expires_at = None
            record.updated_at = now
            session.flush(); return _job_from_record(record)

    def defer_verification(self, job_id: str, worker_id: str, *, now: datetime, next_retry_at: datetime) -> PipelineJob:
        """Release a pending M14 check without consuming a transient-failure retry."""
        with self._session_factory.begin() as session:
            record = session.get(PipelineJobRecord, job_id)
            if record is None or record.claim_owner != worker_id: raise KeyError(f"job is not claimed by {worker_id}")
            record.next_retry_at = next_retry_at
            record.claim_owner = record.claimed_at = record.heartbeat_at = record.lease_expires_at = None
            record.updated_at = now; session.flush(); return _job_from_record(record)

    def update_state(self, job_id: str, state: JobState, resume_state: JobState | None = None, failure_message: str | None = None) -> PipelineJob:
        with self._session_factory.begin() as session:
            record = session.get(PipelineJobRecord, job_id)
            if record is None:
                raise KeyError(f"job not found: {job_id}")
            record.state, record.resume_state, record.failure_message = state.value, (resume_state.value if resume_state else None), failure_message
            record.updated_at = datetime.now(UTC)
            session.flush()
            return _job_from_record(record)


class ArtifactRepository:
    """Store artifact checkpoints after their on-disk content is validated."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(self, job_id: str, stage: JobState, name: str) -> Artifact | None:
        with self._session_factory() as session:
            record = session.scalar(select(ArtifactRecord).where(ArtifactRecord.job_id == job_id, ArtifactRecord.stage == stage.value, ArtifactRecord.name == name))
            return _artifact_from_record(record) if record else None

    def list_for_job(self, job_id: str) -> list[Artifact]:
        """Return registered artifacts for a job; paths remain server-controlled."""
        with self._session_factory() as session:
            records = session.scalars(
                select(ArtifactRecord)
                .where(ArtifactRecord.job_id == job_id)
                .order_by(ArtifactRecord.created_at, ArtifactRecord.stage, ArtifactRecord.name)
            )
            return [_artifact_from_record(record) for record in records]

    def save(self, artifact: Artifact) -> Artifact:
        with self._session_factory.begin() as session:
            record = session.scalar(select(ArtifactRecord).where(ArtifactRecord.job_id == artifact.job_id, ArtifactRecord.stage == artifact.stage.value, ArtifactRecord.name == artifact.name))
            if record is None:
                record = ArtifactRecord(job_id=artifact.job_id, stage=artifact.stage.value, name=artifact.name, path=artifact.path, checksum_sha256=artifact.checksum_sha256, provenance_json=json.dumps(artifact.provenance, sort_keys=True), created_at=datetime.now(UTC))
                session.add(record)
            else:
                record.path, record.checksum_sha256, record.provenance_json = artifact.path, artifact.checksum_sha256, json.dumps(artifact.provenance, sort_keys=True)
        return artifact

    def save_if_claimed(self, artifact: Artifact, worker_id: str, *, now: datetime) -> Artifact | None:
        """Save a checkpoint only if its job lease still belongs to the caller."""
        with self._session_factory.begin() as session:
            owned = session.scalar(
                select(PipelineJobRecord.id).where(
                    PipelineJobRecord.id == artifact.job_id,
                    PipelineJobRecord.claim_owner == worker_id,
                    PipelineJobRecord.lease_expires_at.is_not(None),
                    PipelineJobRecord.lease_expires_at > now,
                )
            )
            if owned is None:
                return None
            record = session.scalar(select(ArtifactRecord).where(ArtifactRecord.job_id == artifact.job_id, ArtifactRecord.stage == artifact.stage.value, ArtifactRecord.name == artifact.name))
            if record is None:
                session.add(ArtifactRecord(job_id=artifact.job_id, stage=artifact.stage.value, name=artifact.name, path=artifact.path, checksum_sha256=artifact.checksum_sha256, provenance_json=json.dumps(artifact.provenance, sort_keys=True), created_at=now))
            else:
                record.path, record.checksum_sha256, record.provenance_json = artifact.path, artifact.checksum_sha256, json.dumps(artifact.provenance, sort_keys=True)
        return artifact


class JobEventRepository:
    """Durable append-only dashboard activity, independent of Docker logs."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def append(self, job_id: str, event_type: str, **details: object) -> JobEvent:
        with self._session_factory.begin() as session:
            record = JobEventRecord(
                job_id=job_id,
                event_type=event_type,
                details_json=json.dumps(details, sort_keys=True, default=str),
                created_at=datetime.now(UTC),
            )
            session.add(record)
            session.flush()
            return _job_event_from_record(record)

    def list_for_job(self, job_id: str, *, limit: int = 100) -> list[JobEvent]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(JobEventRecord)
                .where(JobEventRecord.job_id == job_id)
                .order_by(JobEventRecord.created_at.desc(), JobEventRecord.id.desc())
                .limit(limit)
            )
            return list(reversed([_job_event_from_record(row) for row in rows]))


class SourceMediaRepository:
    """Persist source identity separately from mutable job request JSON."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(self, media: SourceMedia) -> SourceMedia:
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            record = session.scalar(select(SourceMediaRecord).where(SourceMediaRecord.job_id == media.job_id))
            values = {
                "provider": media.provider, "source_url": media.source_url,
                "external_id": media.external_id, "creator_id": media.creator_id,
                "title": media.title, "duration_seconds": media.duration_seconds,
                "metadata_json": json.dumps(media.metadata, sort_keys=True),
            }
            if record is None:
                record = SourceMediaRecord(job_id=media.job_id, created_at=now, updated_at=now, **values)
                session.add(record)
            else:
                for key, value in values.items(): setattr(record, key, value)
                record.updated_at = now
            session.flush()
        return media

    def get(self, job_id: str) -> SourceMedia | None:
        with self._session_factory() as session:
            record = session.scalar(select(SourceMediaRecord).where(SourceMediaRecord.job_id == job_id))
            if record is None: return None
            return SourceMedia(record.job_id, record.provider, record.source_url, record.external_id, record.creator_id, record.title, record.duration_seconds, json.loads(record.metadata_json))


class HeavyWorkLeaseRepository:
    """Database-backed singleton admission lease shared by all worker processes."""

    LEASE_NAME = "pipeline-heavy-work"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def acquire(self, owner: str, *, now: datetime, lease_seconds: int) -> bool:
        """Claim the global lease if it is absent, expired, or already ours."""
        now = _as_utc(now)
        expires_at = now + timedelta(seconds=lease_seconds)
        try:
            with self._session_factory.begin() as session:
                record = session.get(HeavyWorkLeaseRecord, self.LEASE_NAME)
                if record is None:
                    session.add(HeavyWorkLeaseRecord(name=self.LEASE_NAME, owner=owner, acquired_at=now, heartbeat_at=now, lease_expires_at=expires_at))
                    return True
                if record.owner != owner and record.lease_expires_at is not None and _as_utc(record.lease_expires_at) > now:
                    return False
                record.owner, record.acquired_at, record.heartbeat_at, record.lease_expires_at = owner, now, now, expires_at
                return True
        except IntegrityError:
            # A simultaneous first insert won. Re-read under a fresh transaction.
            return self.acquire(owner, now=now, lease_seconds=lease_seconds)

    def heartbeat(self, owner: str, *, now: datetime, lease_seconds: int) -> bool:
        now = _as_utc(now)
        with self._session_factory.begin() as session:
            result = session.execute(
                update(HeavyWorkLeaseRecord)
                .where(
                    HeavyWorkLeaseRecord.name == self.LEASE_NAME,
                    HeavyWorkLeaseRecord.owner == owner,
                    HeavyWorkLeaseRecord.lease_expires_at.is_not(None),
                    HeavyWorkLeaseRecord.lease_expires_at > now,
                )
                .values(heartbeat_at=now, lease_expires_at=now + timedelta(seconds=lease_seconds))
            )
            return result.rowcount == 1

    def owns(self, owner: str, *, now: datetime) -> bool:
        now = _as_utc(now)
        with self._session_factory() as session:
            return session.scalar(
                select(HeavyWorkLeaseRecord.name).where(
                    HeavyWorkLeaseRecord.name == self.LEASE_NAME,
                    HeavyWorkLeaseRecord.owner == owner,
                    HeavyWorkLeaseRecord.lease_expires_at.is_not(None),
                    HeavyWorkLeaseRecord.lease_expires_at > now,
                )
            ) is not None

    def release(self, owner: str) -> None:
        with self._session_factory.begin() as session:
            session.execute(
                update(HeavyWorkLeaseRecord)
                .where(HeavyWorkLeaseRecord.name == self.LEASE_NAME, HeavyWorkLeaseRecord.owner == owner)
                .values(owner=None, acquired_at=None, heartbeat_at=None, lease_expires_at=None)
            )


class PublicationRepository:
    """Persist M13 remote progress before each externally visible operation."""
    def __init__(self, session_factory: sessionmaker[Session]) -> None: self._session_factory = session_factory
    def get(self, publication_identity: str) -> PublicationRecord | None:
        with self._session_factory() as session: return session.scalar(select(PublicationRecord).where(PublicationRecord.publication_identity == publication_identity))
    def ensure(self, job_id: str, identity: str, package_identity: str, channel_id: str, provenance: dict[str, object]) -> PublicationRecord:
        with self._session_factory.begin() as session:
            record = session.scalar(select(PublicationRecord).where(PublicationRecord.publication_identity == identity))
            if record is None:
                record = PublicationRecord(job_id=job_id, publication_identity=identity, package_identity=package_identity, channel_id=channel_id, state="pending", remote_video_id=None, metadata_applied=False, thumbnail_applied=False, provenance_json=json.dumps(provenance, sort_keys=True), error_message=None, created_at=datetime.now(UTC), updated_at=datetime.now(UTC)); session.add(record)
            session.flush(); return record
    def update(self, identity: str, **values: object) -> PublicationRecord:
        with self._session_factory.begin() as session:
            record = session.scalar(select(PublicationRecord).where(PublicationRecord.publication_identity == identity))
            if record is None: raise KeyError(identity)
            for key, value in values.items(): setattr(record, key, value)
            record.updated_at = datetime.now(UTC); session.flush(); return record
    def observe(self, identity: str, health: str, snapshot: dict[str, object], drift: dict[str, object]) -> None:
        with self._session_factory.begin() as session:
            session.add(PublicationObservationRecord(publication_identity=identity, health=health, snapshot_json=json.dumps(snapshot, sort_keys=True), drift_json=json.dumps(drift, sort_keys=True), observed_at=datetime.now(UTC)))
    def observations(self, identity: str) -> list[PublicationObservationRecord]:
        with self._session_factory() as session:
            return list(session.scalars(select(PublicationObservationRecord).where(PublicationObservationRecord.publication_identity == identity).order_by(PublicationObservationRecord.id)))
    def healthy_with_remote_ids(self) -> list[PublicationRecord]:
        with self._session_factory() as session:
            return list(session.scalars(select(PublicationRecord).where(PublicationRecord.state == "healthy", PublicationRecord.remote_video_id.is_not(None))))


class AnalyticsRepository:
    """Small durable store for independent M15/M16 observational work."""
    def __init__(self, session_factory: sessionmaker[Session]) -> None: self._session_factory = session_factory
    def save_snapshot(self, values: dict[str, object]) -> AnalyticsSnapshotRecord:
        with self._session_factory.begin() as session:
            record = session.scalar(select(AnalyticsSnapshotRecord).where(AnalyticsSnapshotRecord.snapshot_identity == values["snapshot_identity"]))
            if record is None:
                record = AnalyticsSnapshotRecord(**values); session.add(record)
            session.flush(); return record
    def snapshots(self, publication_identity: str) -> list[AnalyticsSnapshotRecord]:
        with self._session_factory() as session:
            return list(session.scalars(select(AnalyticsSnapshotRecord).where(AnalyticsSnapshotRecord.publication_identity == publication_identity).order_by(AnalyticsSnapshotRecord.observed_at)))
    def snapshot(self, identity: str) -> AnalyticsSnapshotRecord | None:
        with self._session_factory() as session: return session.scalar(select(AnalyticsSnapshotRecord).where(AnalyticsSnapshotRecord.snapshot_identity == identity))
    def channel_latest_snapshots(self, channel_id: str) -> list[AnalyticsSnapshotRecord]:
        with self._session_factory() as session:
            rows = list(session.scalars(select(AnalyticsSnapshotRecord).where(AnalyticsSnapshotRecord.channel_id == channel_id).order_by(AnalyticsSnapshotRecord.publication_identity, AnalyticsSnapshotRecord.observed_at.desc())))
            seen: set[str] = set(); return [row for row in rows if not (row.publication_identity in seen or seen.add(row.publication_identity))]
    def latest_snapshots(self) -> list[AnalyticsSnapshotRecord]:
        with self._session_factory() as session:
            rows = list(session.scalars(select(AnalyticsSnapshotRecord).order_by(AnalyticsSnapshotRecord.publication_identity, AnalyticsSnapshotRecord.observed_at.desc())))
            seen: set[str] = set(); latest = []
            for row in rows:
                if row.publication_identity not in seen: seen.add(row.publication_identity); latest.append(row)
            return latest
    def save_evaluation(self, values: dict[str, object]) -> PerformanceEvaluationRecord:
        with self._session_factory.begin() as session:
            record = session.scalar(select(PerformanceEvaluationRecord).where(PerformanceEvaluationRecord.evaluation_identity == values["evaluation_identity"]))
            if record is None: record = PerformanceEvaluationRecord(**values); session.add(record)
            session.flush(); return record
    def save_proposal(self, values: dict[str, object]) -> OptimizationProposalRecord:
        with self._session_factory.begin() as session:
            record = session.scalar(select(OptimizationProposalRecord).where(OptimizationProposalRecord.proposal_identity == values["proposal_identity"]))
            if record is None: record = OptimizationProposalRecord(**values); session.add(record)
            session.flush(); return record
    def proposal(self, identity: str) -> OptimizationProposalRecord | None:
        with self._session_factory() as session: return session.scalar(select(OptimizationProposalRecord).where(OptimizationProposalRecord.proposal_identity == identity))
    def evaluation(self, identity: str) -> PerformanceEvaluationRecord | None:
        with self._session_factory() as session: return session.scalar(select(PerformanceEvaluationRecord).where(PerformanceEvaluationRecord.evaluation_identity == identity))


class OptimizationRepository:
    """Durable M17--M19 candidate, execution, and experiment state."""
    def __init__(self, session_factory: sessionmaker[Session]) -> None: self._session_factory = session_factory
    def save_set(self, values: dict[str, object]) -> OptimizationCandidateSetRecord:
        with self._session_factory.begin() as session:
            row = session.scalar(select(OptimizationCandidateSetRecord).where(OptimizationCandidateSetRecord.generation_identity == values["generation_identity"]))
            if row is None: row = OptimizationCandidateSetRecord(**values); session.add(row)
            session.flush(); return row
    def save_candidate(self, values: dict[str, object]) -> OptimizationCandidateRecord:
        with self._session_factory.begin() as session:
            row = session.scalar(select(OptimizationCandidateRecord).where(OptimizationCandidateRecord.candidate_identity == values["candidate_identity"]))
            if row is None: row = OptimizationCandidateRecord(**values); session.add(row)
            session.flush(); return row
    def candidate(self, identity: str) -> OptimizationCandidateRecord | None:
        with self._session_factory() as session: return session.scalar(select(OptimizationCandidateRecord).where(OptimizationCandidateRecord.candidate_identity == identity))
    def select(self, identity: str) -> OptimizationCandidateRecord:
        with self._session_factory.begin() as session:
            row = session.scalar(select(OptimizationCandidateRecord).where(OptimizationCandidateRecord.candidate_identity == identity))
            if row is None: raise KeyError(identity)
            row.state = "SELECTED"; session.flush(); return row
    def execution(self, identity: str) -> OptimizationExecutionRecord | None:
        with self._session_factory() as session: return session.scalar(select(OptimizationExecutionRecord).where(OptimizationExecutionRecord.execution_identity == identity))
    def save_execution(self, values: dict[str, object]) -> OptimizationExecutionRecord:
        with self._session_factory.begin() as session:
            row = session.scalar(select(OptimizationExecutionRecord).where(OptimizationExecutionRecord.execution_identity == values["execution_identity"]))
            if row is None: row = OptimizationExecutionRecord(**values); session.add(row)
            session.flush(); return row
    def update_execution(self, identity: str, **values: object) -> OptimizationExecutionRecord:
        with self._session_factory.begin() as session:
            row = session.scalar(select(OptimizationExecutionRecord).where(OptimizationExecutionRecord.execution_identity == identity))
            if row is None: raise KeyError(identity)
            for key, value in values.items(): setattr(row, key, value)
            row.updated_at = datetime.now(UTC); session.flush(); return row
    def save_experiment(self, values: dict[str, object]) -> OptimizationExperimentRecord:
        with self._session_factory.begin() as session:
            row = session.scalar(select(OptimizationExperimentRecord).where(OptimizationExperimentRecord.execution_identity == values["execution_identity"]))
            if row is None: row = OptimizationExperimentRecord(**values); session.add(row)
            session.flush(); return row
    def experiments(self) -> list[OptimizationExperimentRecord]:
        with self._session_factory() as session: return list(session.scalars(select(OptimizationExperimentRecord).order_by(OptimizationExperimentRecord.started_at)))

class LearningRepository:
    """Durable, idempotent M20--M23 outcomes, channel learning, and briefs."""
    def __init__(self, session_factory: sessionmaker[Session]) -> None: self._session_factory = session_factory
    def _save(self, model, key: str, values: dict[str, object]):
        with self._session_factory.begin() as session:
            row = session.scalar(select(model).where(getattr(model, key) == values[key]))
            if row is None: row = model(**values); session.add(row)
            session.flush(); return row
    def save_outcome(self, values: dict[str, object]) -> ExperimentOutcomeRecord: return self._save(ExperimentOutcomeRecord, "outcome_identity", values)
    def save_event(self, values: dict[str, object]) -> LearningEventRecord: return self._save(LearningEventRecord, "event_identity", values)
    def save_baseline(self, values: dict[str, object]) -> ChannelBaselineRecord: return self._save(ChannelBaselineRecord, "baseline_identity", values)
    def save_recommendation(self, values: dict[str, object]) -> NextVideoRecommendationRecord: return self._save(NextVideoRecommendationRecord, "recommendation_identity", values)
    def save_brief(self, values: dict[str, object]) -> NextVideoBriefRecord: return self._save(NextVideoBriefRecord, "brief_identity", values)
    def active_recommendations(self, channel_id: str) -> list[NextVideoRecommendationRecord]:
        with self._session_factory() as session: return list(session.scalars(select(NextVideoRecommendationRecord).where(NextVideoRecommendationRecord.channel_id == channel_id, NextVideoRecommendationRecord.status == "ACTIVE").order_by(NextVideoRecommendationRecord.created_at)))


class ApprovalRepository:
    """Record and query explicit approval gates."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, approval_id: str, job_id: str, gate: ApprovalGate, status: ApprovalStatus = ApprovalStatus.APPROVED, *, actor: str | None = None, reviewed_identity: str | None = None, audit: dict[str, object] | None = None) -> None:
        """Store one immutable human decision; duplicate requests are idempotent."""
        with self._session_factory.begin() as session:
            existing = session.get(ApprovalRecord, approval_id)
            if existing is not None:
                if (existing.job_id, existing.gate, existing.status, existing.reviewed_identity) != (job_id, gate.value, status.value, reviewed_identity):
                    raise ValueError(f"approval id conflicts with existing decision: {approval_id}")
                return
            decision = self._decision_query(job_id, gate, reviewed_identity)
            effective = session.scalar(decision)
            if effective is not None:
                if effective.status != status.value:
                    raise ValueError("approval decision conflicts with existing decision")
                return
            session.add(ApprovalRecord(id=approval_id, job_id=job_id, gate=gate.value, status=status.value, created_at=datetime.now(UTC), actor=actor, reviewed_identity=reviewed_identity, decision_identity=self._decision_identity(reviewed_identity), audit_json=json.dumps(audit or {}, sort_keys=True)))

    @staticmethod
    def _decision_identity(reviewed_identity: str | None) -> str:
        """Return the non-null database key for a reviewed identity."""
        return reviewed_identity or ""

    @staticmethod
    def _decision_query(job_id: str, gate: ApprovalGate, reviewed_identity: str | None):
        return select(ApprovalRecord).where(
            ApprovalRecord.job_id == job_id,
            ApprovalRecord.gate == gate.value,
            ApprovalRecord.decision_identity == ApprovalRepository._decision_identity(reviewed_identity),
        )

    def decision(self, job_id: str, gate: ApprovalGate, *, reviewed_identity: str | None = None) -> ApprovalRecord | None:
        with self._session_factory() as session:
            return session.scalar(self._decision_query(job_id, gate, reviewed_identity))

    def approved(self, job_id: str, gate: ApprovalGate, *, reviewed_identity: str | None = None) -> ApprovalRecord | None:
        with self._session_factory() as session:
            decision = session.scalar(self._decision_query(job_id, gate, reviewed_identity))
            return decision if decision and decision.status == ApprovalStatus.APPROVED.value else None

    def rejected(self, job_id: str, gate: ApprovalGate, *, reviewed_identity: str | None = None) -> ApprovalRecord | None:
        with self._session_factory() as session:
            decision = session.scalar(self._decision_query(job_id, gate, reviewed_identity))
            return decision if decision and decision.status == ApprovalStatus.REJECTED.value else None


def _job_from_record(record: PipelineJobRecord) -> PipelineJob:
    return PipelineJob(record.id, ContentRequest.model_validate_json(record.request_json), JobState(record.state), JobState(record.resume_state) if record.resume_state else None, record.failure_message, record.claim_owner, record.attempt_count, record.next_retry_at, record.cancellation_requested_at, record.authentication_restored_at)


def _job_event_from_record(record: JobEventRecord) -> JobEvent:
    return JobEvent(record.id, record.job_id, record.event_type, json.loads(record.details_json), record.created_at)


class ExternalOperationRepository:
    """Persist idempotency reservations and completed receipts for publishers."""
    def __init__(self, session_factory: sessionmaker[Session]) -> None: self._session_factory = session_factory
    def receipt(self, key: str) -> dict[str, object] | None:
        with self._session_factory() as session:
            record = session.scalar(select(ExternalOperationRecord).where(ExternalOperationRecord.idempotency_key == key))
            return json.loads(record.receipt_json) if record and record.receipt_json else None
    def reserve(self, job_id: str, operation: str, key: str) -> bool:
        try:
            with self._session_factory.begin() as session:
                session.add(ExternalOperationRecord(job_id=job_id, operation=operation, idempotency_key=key, receipt_json=None, created_at=datetime.now(UTC), completed_at=None))
            return True
        except IntegrityError:
            return False
    def complete(self, key: str, receipt: dict[str, object]) -> None:
        with self._session_factory.begin() as session:
            record = session.scalar(select(ExternalOperationRecord).where(ExternalOperationRecord.idempotency_key == key))
            if record: record.receipt_json, record.completed_at = json.dumps(receipt, sort_keys=True), datetime.now(UTC)


def _artifact_from_record(record: ArtifactRecord) -> Artifact:
    return Artifact(record.job_id, JobState(record.stage), record.name, record.path, record.checksum_sha256, json.loads(record.provenance_json))


def _normalize_cache_value(value: object) -> object:
    """Canonicalize harmless serialization differences while preserving content."""
    import unicodedata

    if isinstance(value, str):
        return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n")).strip()
    if isinstance(value, dict):
        return {key: _normalize_cache_value(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize_cache_value(item) for item in value]
    return value


class GenerationCacheRepository:
    """Durable content cache with expiring, token-bound single-writer reservations."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @staticmethod
    def key_material(request: ContentRequest, provider: str, model: str, prompt_version: str) -> str:
        value = {
            "model": model,
            "normalized_request": _normalize_cache_value(request.model_dump(mode="json")),
            "prompt_version": prompt_version,
            "provider": provider,
        }
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def cache_key(cls, request: ContentRequest, provider: str, model: str, prompt_version: str) -> str:
        return hashlib.sha256(cls.key_material(request, provider, model, prompt_version).encode("utf-8")).hexdigest()

    def reserve_or_get(
        self, request: ContentRequest, provider: str, model: str, prompt_version: str, *, now: datetime, reservation_seconds: int
    ) -> CachedGeneration | GenerationCacheReservation | None:
        """Return accepted data, a writer token, or None while another valid writer owns it."""
        now = _as_utc(now)
        key = self.cache_key(request, provider, model, prompt_version)
        material = self.key_material(request, provider, model, prompt_version)
        token = secrets.token_hex(32)
        expires = now + timedelta(seconds=reservation_seconds)
        try:
            with self._session_factory.begin() as session:
                session.add(GenerationCacheRecord(cache_key=key, normalized_request_json=material, provider=provider, model=model, prompt_version=prompt_version, state="reserved", reservation_token=token, reservation_expires_at=expires, package_json=None, provenance_json=None, usage_json=None, created_at=now, updated_at=now, accepted_at=None))
            return GenerationCacheReservation(key, token)
        except IntegrityError:
            with self._session_factory.begin() as session:
                record = session.scalar(select(GenerationCacheRecord).where(GenerationCacheRecord.cache_key == key))
                if record is None:
                    return None
                if record.state == "accepted" and record.package_json and record.provenance_json and record.usage_json:
                    return CachedGeneration(json.loads(record.package_json), json.loads(record.provenance_json), json.loads(record.usage_json))
                expires_at = _as_utc(record.reservation_expires_at) if record.reservation_expires_at else None
                if record.state == "reserved" and expires_at and expires_at <= now:
                    statement = (
                        update(GenerationCacheRecord)
                        .where(
                            GenerationCacheRecord.cache_key == key,
                            GenerationCacheRecord.state == "reserved",
                            GenerationCacheRecord.reservation_expires_at <= now,
                        )
                        .values(
                            reservation_token=token,
                            reservation_expires_at=expires,
                            normalized_request_json=material,
                            updated_at=now,
                        )
                        .execution_options(synchronize_session=False)
                    )
                    result = session.execute(statement)
                    if result.rowcount == 1:
                        return GenerationCacheReservation(key, token)
                return None

    def accept(self, reservation: GenerationCacheReservation, package: dict[str, object], provenance: dict[str, object], usage: dict[str, object], *, now: datetime) -> bool:
        now = _as_utc(now)
        with self._session_factory.begin() as session:
            result = session.execute(
                update(GenerationCacheRecord)
                .where(
                    GenerationCacheRecord.cache_key == reservation.cache_key,
                    GenerationCacheRecord.state == "reserved",
                    GenerationCacheRecord.reservation_token == reservation.token,
                )
                .values(state="accepted", reservation_token=None, reservation_expires_at=None, package_json=json.dumps(package, sort_keys=True), provenance_json=json.dumps(provenance, sort_keys=True), usage_json=json.dumps(usage, sort_keys=True), accepted_at=now, updated_at=now)
                .execution_options(synchronize_session=False)
            )
            return result.rowcount == 1

    def abandon(self, reservation: GenerationCacheReservation) -> bool:
        """Release a failed generation reservation without disturbing a newer owner."""
        with self._session_factory.begin() as session:
            result = session.execute(
                delete(GenerationCacheRecord).where(
                    GenerationCacheRecord.cache_key == reservation.cache_key,
                    GenerationCacheRecord.state == "reserved",
                    GenerationCacheRecord.reservation_token == reservation.token,
                )
            )
            return result.rowcount == 1


def _as_utc(value: datetime) -> datetime:
    """Treat SQLite's timezone-naive storage values as UTC, as do PostgreSQL values."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

@dataclass(frozen=True, slots=True)
class AssetCacheReservation:
    cache_key: str
    token: str

@dataclass(frozen=True, slots=True)
class CachedAsset:
    path: str
    checksum_sha256: str
    metadata: dict[str, object]

class AssetCacheRepository:
    """Short-transaction durable cache ownership; IO occurs outside this class."""
    def __init__(self, session_factory: sessionmaker[Session]) -> None: self._session_factory = session_factory
    def reserve_or_get(self, key: str, *, now: datetime, reservation_seconds: int) -> CachedAsset | AssetCacheReservation | None:
        now=_as_utc(now); token=secrets.token_hex(32); expires=now+timedelta(seconds=reservation_seconds)
        try:
            with self._session_factory.begin() as session:
                record=session.scalar(select(AssetCacheRecord).where(AssetCacheRecord.cache_key==key))
                if record is None:
                    session.add(AssetCacheRecord(cache_key=key,state="reserved",reservation_token=token,reservation_expires_at=expires,path=None,checksum_sha256=None,metadata_json=None,failure_message=None,created_at=now,updated_at=now,accepted_at=None)); return AssetCacheReservation(key,token)
                if record.state=="accepted" and record.path and record.checksum_sha256 and record.metadata_json: return CachedAsset(record.path,record.checksum_sha256,json.loads(record.metadata_json))
                if record.reservation_expires_at is None or _as_utc(record.reservation_expires_at) <= now:
                    record.state="reserved"; record.reservation_token=token; record.reservation_expires_at=expires; record.updated_at=now; return AssetCacheReservation(key,token)
                return None
        except IntegrityError:
            # A competing insert committed; a fresh session observes its durable state.
            return self.reserve_or_get(key, now=now, reservation_seconds=reservation_seconds)
    def invalidate(self, key: str, *, now: datetime) -> None:
        """Release a corrupt accepted entry; the binary is deliberately retained."""
        with self._session_factory.begin() as session:
            session.execute(update(AssetCacheRecord).where(AssetCacheRecord.cache_key == key, AssetCacheRecord.state == "accepted").values(state="invalid", reservation_token=None, reservation_expires_at=None, failure_message="cached file failed revalidation", updated_at=_as_utc(now)))

    def abandon(self, reservation: AssetCacheReservation) -> bool:
        """Release a failed reservation without disturbing a replacement owner."""
        with self._session_factory.begin() as session:
            result = session.execute(
                delete(AssetCacheRecord).where(
                    AssetCacheRecord.cache_key == reservation.cache_key,
                    AssetCacheRecord.state == "reserved",
                    AssetCacheRecord.reservation_token == reservation.token,
                )
            )
            return result.rowcount == 1

    def accept(self, reservation: AssetCacheReservation, asset: CachedAsset, *, now: datetime) -> bool:
        with self._session_factory.begin() as session:
            result=session.execute(update(AssetCacheRecord).where(AssetCacheRecord.cache_key==reservation.cache_key,AssetCacheRecord.state=="reserved",AssetCacheRecord.reservation_token==reservation.token).values(state="accepted",path=asset.path,checksum_sha256=asset.checksum_sha256,metadata_json=json.dumps(asset.metadata,sort_keys=True),reservation_token=None,reservation_expires_at=None,updated_at=_as_utc(now),accepted_at=_as_utc(now),failure_message=None))
            return result.rowcount==1
