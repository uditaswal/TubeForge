"""Small transaction-scoped repositories for deterministic pipeline state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import secrets

from sqlalchemy import and_, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.domain.contracts import ContentRequest
from tubeforge.domain.states import ApprovalGate, ApprovalStatus, JobState
from tubeforge.db.models import ApprovalRecord, ArtifactRecord, AssetCacheRecord, ExternalOperationRecord, GenerationCacheRecord, PipelineJobRecord


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

    def claim_oldest_eligible(self, worker_id: str, *, now: datetime, lease_seconds: int) -> PipelineJob | None:
        """Atomically lease the oldest runnable job; provider work occurs after commit.

        The conditional UPDATE is the correctness primitive on SQLite and remains
        valid on PostgreSQL, where callers may additionally benefit from row locks.
        """
        blocked = {
            JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY,
            JobState.FINAL_READY, JobState.CANCELLED, JobState.FAILED_VALIDATION,
            JobState.AUTH_REQUIRED, JobState.FAILED_EXHAUSTED,
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

    def record(self, approval_id: str, job_id: str, gate: ApprovalGate, status: ApprovalStatus = ApprovalStatus.APPROVED, *, actor: str | None = None, reviewed_identity: str | None = None, audit: dict[str, object] | None = None) -> None:
        """Store one immutable human decision; duplicate requests are idempotent."""
        with self._session_factory.begin() as session:
            existing = session.get(ApprovalRecord, approval_id)
            if existing is not None:
                if (existing.job_id, existing.gate, existing.status, existing.reviewed_identity) != (job_id, gate.value, status.value, reviewed_identity):
                    raise ValueError(f"approval id conflicts with existing decision: {approval_id}")
                return
            session.add(ApprovalRecord(id=approval_id, job_id=job_id, gate=gate.value, status=status.value, created_at=datetime.now(UTC), actor=actor, reviewed_identity=reviewed_identity, audit_json=json.dumps(audit or {}, sort_keys=True)))

    def approved(self, job_id: str, gate: ApprovalGate, *, reviewed_identity: str | None = None) -> ApprovalRecord | None:
        with self._session_factory() as session:
            query = select(ApprovalRecord).where(ApprovalRecord.job_id == job_id, ApprovalRecord.gate == gate.value, ApprovalRecord.status == ApprovalStatus.APPROVED.value)
            if reviewed_identity is not None:
                query = query.where(ApprovalRecord.reviewed_identity == reviewed_identity)
            return session.scalar(query.order_by(ApprovalRecord.created_at.desc()))

    def rejected(self, job_id: str, gate: ApprovalGate, *, reviewed_identity: str | None = None) -> ApprovalRecord | None:
        with self._session_factory() as session:
            query = select(ApprovalRecord).where(ApprovalRecord.job_id == job_id, ApprovalRecord.gate == gate.value, ApprovalRecord.status == ApprovalStatus.REJECTED.value)
            if reviewed_identity is not None:
                query = query.where(ApprovalRecord.reviewed_identity == reviewed_identity)
            return session.scalar(query.order_by(ApprovalRecord.created_at.desc()))


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

    def accept(self, reservation: AssetCacheReservation, asset: CachedAsset, *, now: datetime) -> bool:
        with self._session_factory.begin() as session:
            result=session.execute(update(AssetCacheRecord).where(AssetCacheRecord.cache_key==reservation.cache_key,AssetCacheRecord.state=="reserved",AssetCacheRecord.reservation_token==reservation.token).values(state="accepted",path=asset.path,checksum_sha256=asset.checksum_sha256,metadata_json=json.dumps(asset.metadata,sort_keys=True),reservation_token=None,reservation_expires_at=None,updated_at=_as_utc(now),accepted_at=_as_utc(now),failure_message=None))
            return result.rowcount==1
