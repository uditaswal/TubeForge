"""Small transaction-scoped repositories for deterministic pipeline state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.domain.contracts import ContentRequest
from tubeforge.domain.states import ApprovalGate, ApprovalStatus, JobState
from tubeforge.db.models import ApprovalRecord, ArtifactRecord, ExternalOperationRecord, PipelineJobRecord


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

    def claim_oldest_eligible(self, worker_id: str, *, now: datetime, lease_seconds: int) -> PipelineJob | None:
        """Atomically lease the oldest runnable job; provider work occurs after commit.

        The conditional UPDATE is the correctness primitive on SQLite and remains
        valid on PostgreSQL, where callers may additionally benefit from row locks.
        """
        runnable = [state.value for state in JobState if state not in {
            JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_APPROVAL_REQUIRED,
            JobState.PUBLISH_APPROVAL_REQUIRED, JobState.PUBLISHED, JobState.CANCELLED,
            JobState.FAILED_VALIDATION, JobState.AUTH_REQUIRED, JobState.FAILED_EXHAUSTED,
            JobState.FAILED_RETRYABLE,
        }]
        lease_expiry = now + __import__("datetime").timedelta(seconds=lease_seconds)
        with self._session_factory.begin() as session:
            # Reclaiming abandoned leases is deliberately part of the brief transaction.
            session.execute(update(PipelineJobRecord).where(PipelineJobRecord.lease_expires_at.is_not(None), PipelineJobRecord.lease_expires_at <= now).values(claim_owner=None, claimed_at=None, lease_expires_at=None, heartbeat_at=None))
            eligible = or_(
                PipelineJobRecord.state.in_(runnable),
                and_(PipelineJobRecord.state == JobState.FAILED_RETRYABLE.value, PipelineJobRecord.next_retry_at <= now),
                and_(PipelineJobRecord.state == JobState.AUTH_REQUIRED.value, PipelineJobRecord.authentication_restored_at.is_not(None)),
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

    def save(self, artifact: Artifact) -> Artifact:
        with self._session_factory.begin() as session:
            record = session.scalar(select(ArtifactRecord).where(ArtifactRecord.job_id == artifact.job_id, ArtifactRecord.stage == artifact.stage.value, ArtifactRecord.name == artifact.name))
            if record is None:
                record = ArtifactRecord(job_id=artifact.job_id, stage=artifact.stage.value, name=artifact.name, path=artifact.path, checksum_sha256=artifact.checksum_sha256, provenance_json=json.dumps(artifact.provenance, sort_keys=True), created_at=datetime.now(UTC))
                session.add(record)
            else:
                record.path, record.checksum_sha256, record.provenance_json = artifact.path, artifact.checksum_sha256, json.dumps(artifact.provenance, sort_keys=True)
        return artifact


class ApprovalRepository:
    """Record and query explicit approval gates."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def record(self, approval_id: str, job_id: str, gate: ApprovalGate, status: ApprovalStatus = ApprovalStatus.APPROVED) -> None:
        try:
            with self._session_factory.begin() as session:
                session.add(ApprovalRecord(id=approval_id, job_id=job_id, gate=gate.value, status=status.value, created_at=datetime.now(UTC)))
        except IntegrityError as error:
            raise ValueError(f"approval already exists: {approval_id}") from error

    def approved(self, job_id: str, gate: ApprovalGate) -> ApprovalRecord | None:
        with self._session_factory() as session:
            return session.scalar(select(ApprovalRecord).where(ApprovalRecord.job_id == job_id, ApprovalRecord.gate == gate.value, ApprovalRecord.status == ApprovalStatus.APPROVED.value).order_by(ApprovalRecord.created_at.desc()))


def _job_from_record(record: PipelineJobRecord) -> PipelineJob:
    return PipelineJob(record.id, ContentRequest.model_validate_json(record.request_json), JobState(record.state), JobState(record.resume_state) if record.resume_state else None, record.failure_message, record.claim_owner, record.attempt_count, record.next_retry_at, record.cancellation_requested_at, record.authentication_restored_at)


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
