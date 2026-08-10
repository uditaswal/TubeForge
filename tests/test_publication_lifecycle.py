from datetime import UTC, datetime, timedelta

from tubeforge.core.config import PublicationVerificationConfig, YouTubePublishingConfig
from tubeforge.domain.contracts import PublishPrivacy, RemoteProcessingState, RemotePublicationSnapshot
from tubeforge.pipeline.orchestrator import PipelineOrchestrator
from tubeforge.providers.fake import FakeYouTubePublisher


def _runner() -> PipelineOrchestrator:
    runner = object.__new__(PipelineOrchestrator)
    runner.youtube_config = YouTubePublishingConfig()
    runner.verification_config = PublicationVerificationConfig(maximum_processing_wait_seconds=300)
    return runner


def test_publication_health_detects_drift_and_processing_timeout() -> None:
    runner = _runner()
    package = {"metadata": {"title": "Expected", "description": "Text\n", "tags": ["one", "two"]}}
    ready = RemotePublicationSnapshot(video_id="remote", exists=True, processing=RemoteProcessingState.SUCCEEDED, privacy=PublishPrivacy.PRIVATE, title="Expected", description="Text\n", tags=("two", "one"), thumbnail_present=None)
    assert runner._publication_health(package, datetime.now(UTC), ready)[0] == "healthy"
    drifted = ready.model_copy(update={"privacy": PublishPrivacy.PUBLIC, "title": "Changed"})
    health, drift, _ = runner._publication_health(package, datetime.now(UTC), drifted)
    assert health == "drift_detected" and set(drift) == {"privacy", "title"}
    processing = ready.model_copy(update={"processing": RemoteProcessingState.PROCESSING})
    assert runner._publication_health(package, datetime.now(UTC) - timedelta(seconds=301), processing)[0] == "intervention_required"


def test_fake_lifecycle_lookup_is_read_only() -> None:
    publisher = FakeYouTubePublisher()
    publisher.videos["remote"] = {"privacy": "private", "processing": "succeeded"}
    snapshot = publisher.fetch_publication_snapshot("remote")
    assert snapshot.exists and publisher.create_calls == publisher.metadata_calls == publisher.thumbnail_calls == 0
