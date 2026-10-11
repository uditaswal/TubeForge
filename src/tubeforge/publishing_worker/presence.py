"""Durable publishing worker heartbeat used by Studio readiness checks."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.db.models import PublisherWorkerHeartbeatRecord


class PublisherWorkerPresence:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def heartbeat(self, worker_id: str, platforms: set[str], *, now: datetime | None = None) -> None:
        if not worker_id or not platforms or any(platform not in {"youtube", "instagram"} for platform in platforms):
            raise ValueError("publisher heartbeat requires a worker and supported platforms")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = session.get(PublisherWorkerHeartbeatRecord, worker_id)
            if row is None:
                session.add(PublisherWorkerHeartbeatRecord(
                    id=worker_id, platforms_json=json.dumps(sorted(platforms)),
                    started_at=now, last_seen_at=now,
                ))
            else:
                row.platforms_json = json.dumps(sorted(platforms))
                row.last_seen_at = now

    def live_platforms(self, *, now: datetime | None = None, max_age_seconds: int = 30) -> set[str]:
        now = now or datetime.now(UTC)
        cutoff = now - timedelta(seconds=max_age_seconds)
        with self.session_factory() as session:
            rows = session.scalars(select(PublisherWorkerHeartbeatRecord).where(PublisherWorkerHeartbeatRecord.last_seen_at >= cutoff)).all()
        return {platform for row in rows for platform in json.loads(row.platforms_json) if platform in {"youtube", "instagram"}}

    def stop(self, worker_id: str) -> None:
        with self.session_factory.begin() as session:
            session.execute(delete(PublisherWorkerHeartbeatRecord).where(PublisherWorkerHeartbeatRecord.id == worker_id))
