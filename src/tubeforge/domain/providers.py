"""Typed provider interfaces. Adapters implement these without leaking SDK types."""

from __future__ import annotations

from typing import Protocol

from tubeforge.domain.contracts import (
    AssetCandidate,
    MediaSearchRequest,
    ContentPackage,
    ContentRequest,
    PublishRequest,
    PublishResult,
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
