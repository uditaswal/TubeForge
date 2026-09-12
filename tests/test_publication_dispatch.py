from __future__ import annotations

from pathlib import Path

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import VideoMetadata
from tubeforge.pipeline.dispatch import PublicationDispatcher
from tubeforge.providers.fake import FakePublisher


def test_dispatch_is_idempotent_per_target_and_records_unsupported(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'dispatch.db'}")); Base.metadata.create_all(database.engine)
    try:
        publisher = FakePublisher(); dispatcher = PublicationDispatcher(database.session_factory, {"youtube": publisher})
        metadata = VideoMetadata(title_options=("Title",), description="Description")
        first = dispatcher.dispatch(job_id="job", account_id="yt-1", platform="youtube", artifact_path="/safe/final.mp4", metadata=metadata)
        repeated = dispatcher.dispatch(job_id="job", account_id="yt-1", platform="youtube", artifact_path="/safe/final.mp4", metadata=metadata)
        unsupported = dispatcher.dispatch(job_id="job", account_id="snap-1", platform="snapchat", artifact_path="/safe/final.mp4", metadata=metadata)
        assert first.state == repeated.state == "succeeded" and first.id == repeated.id
        assert publisher.calls == 1
        assert unsupported.state == "unsupported" and not unsupported.retry_eligible
    finally:
        database.dispose()
