"""Configurable deterministic providers used exclusively for local development and tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from tubeforge.core.config import FakeProviderConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import (AssetCandidate, AssetSearchRequest, CitedClaim, ClaimReviewStatus, ConfidenceLevel, ContentPackage, ContentRequest, PublishRequest, PublishResult, ScenePlan, ScriptSection, ThumbnailBrief, VideoMetadata, VoiceRequest, VoiceResult)


class FakeContentProvider:
    """Return a stable valid package and expose injectable failure modes."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.calls = 0
        self.failure = failure

    def generate_package(self, request: ContentRequest) -> ContentPackage:
        self.calls += 1
        if self.failure:
            raise self.failure
        return ContentPackage(schema_version="1.0", request=request, claims=(CitedClaim(claim_id="claim-1", text=f"{request.topic} is explained using the supplied source.", source_ids=(request.sources[0].source_id,), confidence=ConfidenceLevel.HIGH, review_status=ClaimReviewStatus.VERIFIED, human_review_required=False),), script_sections=(ScriptSection(section_id="section-1", narration=f"{request.topic}: {request.angle}", scene_id="scene-1", claim_ids=("claim-1",), contains_factual_claims=True),), scene_plans=(ScenePlan(scene_id="scene-1", visual_type="illustration", search_queries=(request.topic,), fallback_visual="text_card"),), metadata=VideoMetadata(title_options=(request.topic,), description=request.angle), thumbnail_brief=ThumbnailBrief(text_options=(request.topic[:40],), visual_direction="Simple educational illustration", accessibility_description="Educational illustration"))


class FakeVoiceProvider:
    """Write synthetic audio bytes atomically and return their checksum."""

    def __init__(self, settings: FakeProviderConfig, failure: Exception | None = None) -> None:
        self.settings, self.failure, self.calls = settings, failure, 0

    def synthesize(self, request: VoiceRequest) -> VoiceResult:
        self.calls += 1
        if self.failure:
            raise self.failure
        payload = f"fake voice|{request.section_id}|{request.text}".encode()
        destination = self.settings.artifact_root / "voice" / f"{request.section_id}.audio"
        _atomic_write(destination, payload)
        return VoiceResult(artifact_path=str(destination), duration_seconds=max(0.1, len(request.text) / 20), checksum_sha256=_checksum(payload), provider_name="fake-voice")


class FakeMediaProvider:
    """Return a rights-bearing synthetic media candidate without downloading."""

    def __init__(self, settings: FakeProviderConfig, failure: Exception | None = None) -> None:
        self.settings, self.failure, self.calls = settings, failure, 0

    def search(self, request: AssetSearchRequest) -> list[AssetCandidate]:
        self.calls += 1
        if self.failure:
            raise self.failure
        digest = _checksum("|".join(request.queries).encode())[:12]
        return [AssetCandidate(provider_asset_id=f"fake-{digest}", source_url=f"https://example.invalid/assets/{digest}", author="TubeForge fake", license_name=self.settings.media_license, attribution_text="Synthetic test asset", retrieved_at=datetime.now(UTC))]


class FakePublisher:
    """Deterministically maps idempotency keys to receipts without network activity."""

    def __init__(self, failure: Exception | None = None) -> None:
        self.failure, self.calls, self._results = failure, 0, {}

    def upload(self, request: PublishRequest) -> PublishResult:
        self.calls += 1
        if self.failure:
            raise self.failure
        if request.idempotency_key not in self._results:
            digest = _checksum(request.idempotency_key.encode())[:16]
            self._results[request.idempotency_key] = PublishResult(platform=request.platform, remote_id=f"fake-{digest}", privacy=request.privacy, receipt_id=f"receipt-{digest}")
        return self._results[request.idempotency_key]


def _atomic_write(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


__all__ = ["FakeContentProvider", "FakeMediaProvider", "FakePublisher", "FakeVoiceProvider", "ProviderAuthenticationError", "ProviderValidationError", "RetryableProviderError"]
