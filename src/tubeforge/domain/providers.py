"""Typed provider interfaces. Adapters implement these without leaking SDK types."""

from __future__ import annotations

from typing import Callable, Protocol

from tubeforge.domain.contracts import (
    AssetCandidate,
    MediaSearchRequest,
    ContentPackage,
    ContentRequest,
    PublishRequest,
    PublishResult,
    AnalyticsSnapshotData,
    VoiceRequest,
    VoiceResult,
)


class ContentProvider(Protocol):
    def generate_package(self, request: ContentRequest) -> ContentPackage:
        """Create exactly one validated content package for a request."""


class VoiceProvider(Protocol):
    def synthesize(self, request: VoiceRequest) -> VoiceResult:
        """Synthesize one narration section."""


class MediaProvider(Protocol):
    def search(self, request: MediaSearchRequest) -> list[AssetCandidate]:
        """Return licensed media candidates without downloading them."""


class Publisher(Protocol):
    def upload(self, request: PublishRequest) -> PublishResult:
        """Upload a prepared artifact using the caller's idempotency key."""


class YouTubePublisher(Protocol):
    """Narrow M13 boundary: reads are distinct from remote mutations."""
    def authenticated_channel_id(self) -> str: ...
    def create_or_resume_video(self, request: PublishRequest, *, resume_token: str | None = None, cancellation_requested: Callable[[], bool] | None = None) -> str: ...
    def apply_metadata(self, remote_video_id: str, request: PublishRequest) -> None: ...
    def set_thumbnail(self, remote_video_id: str, thumbnail_path: str) -> None: ...
    def fetch_video(self, remote_video_id: str) -> dict[str, object] | None: ...
    def fetch_publication_snapshot(self, remote_video_id: str): ...
    def fetch_video_analytics(self, remote_video_id: str, channel_id: str, report_start, report_end) -> AnalyticsSnapshotData: ...
