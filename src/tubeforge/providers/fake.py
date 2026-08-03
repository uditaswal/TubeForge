"""Configurable deterministic providers used exclusively for local development and tests."""

from __future__ import annotations

import hashlib
import io
import base64
import wave
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
        # A tiny valid PCM WAV keeps offline tests realistic without a native TTS.
        frames = max(800, len(request.text.encode("utf-8")) * 80)
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(8_000)
            stream.writeframes(b"\x00\x00" * frames)
        payload = buffer.getvalue()
        destination = Path(request.output_path) if request.output_path else self.settings.artifact_root / "voice" / f"{request.phrase_id or request.section_id}.wav"
        _atomic_write(destination, payload)
        return VoiceResult(artifact_path=str(destination), duration_seconds=frames / 8_000, checksum_sha256=_checksum(payload), provider_name="fake-voice")


class FakeMediaProvider:
    """Return a rights-bearing synthetic media candidate without downloading."""

    def __init__(self, settings: FakeProviderConfig, failure: Exception | None = None) -> None:
        self.settings, self.failure, self.calls = settings, failure, 0

    def search(self, request: AssetSearchRequest) -> list[AssetCandidate]:
        self.calls += 1
        if self.failure:
            raise self.failure
        digest = _checksum("|".join(request.queries).encode())[:12]
        path = self.settings.artifact_root / "media" / f"{digest}.png"
        _atomic_write(path, base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLAtwAAAABJRU5ErkJggg=="))
        return [AssetCandidate(provider_asset_id=f"fake-{digest}", source_url=f"https://example.invalid/assets/{digest}", download_url=f"https://example.invalid/assets/{digest}.png", local_path=str(path), media_type="image", width=1, height=1, author="TubeForge fake", license_name=self.settings.media_license, attribution_text="Synthetic test asset", retrieved_at=datetime.now(UTC))]


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
