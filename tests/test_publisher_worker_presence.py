"""Studio readiness follows actual recent publisher worker heartbeats."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base
from tubeforge.db.session import create_database
from tubeforge.publishing_worker.presence import PublisherWorkerPresence


def test_publisher_presence_expires_and_tracks_only_running_adapters(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'heartbeat.db'}"))
    Base.metadata.create_all(database.engine)
    presence = PublisherWorkerPresence(database.session_factory)
    now = datetime.now(UTC)
    try:
        assert presence.live_platforms(now=now) == set()
        presence.heartbeat("worker-a", {"youtube"}, now=now)
        assert presence.live_platforms(now=now + timedelta(seconds=20)) == {"youtube"}
        assert presence.live_platforms(now=now + timedelta(seconds=31)) == set()
        presence.heartbeat("worker-a", {"youtube"}, now=now + timedelta(seconds=40))
        presence.heartbeat("worker-b", {"instagram"}, now=now + timedelta(seconds=41))
        assert presence.live_platforms(now=now + timedelta(seconds=42)) == {"youtube", "instagram"}
        presence.stop("worker-a")
        assert presence.live_platforms(now=now + timedelta(seconds=42)) == {"instagram"}
    finally:
        database.dispose()
