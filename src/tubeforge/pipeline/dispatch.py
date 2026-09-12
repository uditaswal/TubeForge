"""Idempotent multi-account dispatch without coupling pipeline to vendor SDKs."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.db.models import PublicationAttemptRecord
from tubeforge.domain.contracts import PublishRequest, VideoMetadata
from tubeforge.domain.providers import Publisher


class PublicationDispatcher:
    def __init__(self, session_factory: sessionmaker[Session], publishers: dict[str, Publisher]) -> None: self._session_factory, self.publishers = session_factory, publishers

    def dispatch(self, *, job_id: str, account_id: str, platform: str, artifact_path: str, metadata: VideoMetadata) -> PublicationAttemptRecord:
        key = hashlib.sha256(f"{job_id}:{account_id}:{artifact_path}".encode()).hexdigest()
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            record = session.scalar(select(PublicationAttemptRecord).where(PublicationAttemptRecord.idempotency_key == key))
            if record is None:
                record = PublicationAttemptRecord(id=uuid4().hex, job_id=job_id, account_id=account_id, platform=platform, idempotency_key=key, state="pending", attempt_count=0, remote_id=None, remote_url=None, error_message=None, retry_eligible=False, metadata_json=metadata.model_dump_json(), started_at=None, finished_at=None, created_at=now, updated_at=now); session.add(record); session.flush()
            if record.state == "succeeded": return record
            record.state, record.attempt_count, record.started_at, record.updated_at = "publishing", record.attempt_count + 1, now, now
        publisher = self.publishers.get(platform)
        if publisher is None:
            return self._finish(key, state="unsupported", error_message=f"no publisher configured for {platform}", retry_eligible=False)
        try:
            result = publisher.upload(PublishRequest(platform=platform, artifact_path=artifact_path, metadata=metadata, privacy="private", idempotency_key=key))
        except RetryableProviderError as error:
            return self._finish(key, state="failed", error_message=str(error), retry_eligible=True)
        except (ProviderAuthenticationError, ProviderValidationError) as error:
            return self._finish(key, state="failed", error_message=str(error), retry_eligible=False)
        return self._finish(key, state="succeeded", remote_id=result.remote_id, remote_url=None, retry_eligible=False)

    def _finish(self, key: str, *, state: str, remote_id: str | None = None, remote_url: str | None = None, error_message: str | None = None, retry_eligible: bool) -> PublicationAttemptRecord:
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            record = session.scalar(select(PublicationAttemptRecord).where(PublicationAttemptRecord.idempotency_key == key)); assert record is not None
            record.state, record.remote_id, record.remote_url, record.error_message, record.retry_eligible, record.finished_at, record.updated_at = state, remote_id, remote_url, error_message, retry_eligible, now, now
            session.flush(); return record
