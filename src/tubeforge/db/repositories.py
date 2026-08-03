"""Small transaction-scoped repositories for deterministic pipeline state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.domain.contracts import ContentRequest
from tubeforge.domain.states import ApprovalGate, ApprovalStatus, JobState
from tubeforge.db.models import ApprovalRecord, ArtifactRecord, PipelineJobRecord


@dataclass(frozen=True, slots=True)
class PipelineJob:
    id: str
    request: ContentRequest
    state: JobState
    resume_state: JobState | None
    failure_message: str | None


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
    return PipelineJob(record.id, ContentRequest.model_validate_json(record.request_json), JobState(record.state), JobState(record.resume_state) if record.resume_state else None, record.failure_message)


def _artifact_from_record(record: ArtifactRecord) -> Artifact:
    return Artifact(record.job_id, JobState(record.stage), record.name, record.path, record.checksum_sha256, json.loads(record.provenance_json))
