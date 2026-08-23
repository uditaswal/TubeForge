"""Configurable deterministic providers used exclusively for local development and tests."""

from __future__ import annotations

import hashlib
import io
import struct
import wave
import zlib
from datetime import UTC, datetime
from pathlib import Path

from tubeforge.core.config import FakeProviderConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderCancellation, ProviderValidationError, RetryableProviderError
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
        _atomic_write(path, _solid_png(64, 64, (49, 130, 189)))
        return [AssetCandidate(provider_asset_id=f"fake-{digest}", source_url=f"https://example.invalid/assets/{digest}", download_url=f"https://example.invalid/assets/{digest}.png", local_path=str(path), media_type="image", width=64, height=64, author="TubeForge fake", license_name=self.settings.media_license, attribution_text="Synthetic test asset", retrieved_at=datetime.now(UTC))]


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


class FakeYouTubePublisher:
    """Deterministic in-memory M13 fake; it never contacts YouTube."""
    def __init__(self, channel_id: str = "fake-channel", failure: Exception | None = None, *, outcomes: dict[str, list[Exception | None]] | None = None) -> None:
        self.channel_id, self.failure, self.creates, self.create_calls, self.metadata_calls, self.thumbnail_calls, self.reconcile_calls, self.channel_lookup_calls, self.analytics_calls = channel_id, failure, 0, 0, 0, 0, 0, 0, 0
        self.outcomes = outcomes or {}; self.videos: dict[str, dict[str, object]] = {}
    def _outcome(self, operation: str) -> None:
        values = self.outcomes.get(operation, [])
        if values:
            failure = values.pop(0)
            if failure: raise failure
        if self.failure: raise self.failure
    def authenticated_channel_id(self) -> str:
        self.channel_lookup_calls += 1; self._outcome("channel_lookup"); return self.channel_id
    def create_or_resume_video(self, request: PublishRequest, *, resume_token: str | None = None, cancellation_requested=None) -> str:
        self.create_calls += 1
        self._outcome("create")
        if cancellation_requested and cancellation_requested(): raise ProviderCancellation("fake upload cancelled")
        key = request.idempotency_key; remote_id = f"fake-{_checksum(key.encode())[:16]}"
        if remote_id not in self.videos: self.creates += 1; self.videos[remote_id] = {"privacy": request.privacy.value}
        return remote_id
    def apply_metadata(self, remote_video_id: str, request: PublishRequest) -> None:
        self.metadata_calls += 1
        self._outcome("metadata")
        self.videos[remote_video_id]["metadata"] = request.metadata.model_dump(mode="json")
    def set_thumbnail(self, remote_video_id: str, thumbnail_path: str) -> None:
        self.thumbnail_calls += 1
        self._outcome("thumbnail")
        self.videos[remote_video_id]["thumbnail"] = thumbnail_path
    def fetch_video(self, remote_video_id: str) -> dict[str, object] | None:
        self.reconcile_calls += 1; self._outcome("reconcile"); return self.videos.get(remote_video_id)
    def fetch_publication_snapshot(self, remote_video_id: str):
        from tubeforge.domain.contracts import RemotePublicationSnapshot
        value = self.fetch_video(remote_video_id)
        if value is None: return RemotePublicationSnapshot(video_id=remote_video_id, exists=False)
        return RemotePublicationSnapshot(video_id=remote_video_id, exists=True, processing=value.get("processing", "succeeded"), privacy=value.get("privacy"), title=(value.get("metadata") or {}).get("title_options", [value.get("title")])[0], description=(value.get("metadata") or {}).get("description", value.get("description")), tags=tuple((value.get("metadata") or {}).get("tags", value.get("tags", ()))) if value.get("tags") is not None or value.get("metadata") else None, thumbnail_present=bool(value.get("thumbnail")) if "thumbnail" in value else None)

    def fetch_video_analytics(self, remote_video_id, channel_id, report_start, report_end):
        from datetime import UTC, datetime
        from tubeforge.domain.contracts import AnalyticsMetric, AnalyticsSnapshotData
        self.analytics_calls += 1; self._outcome("analytics")
        scripted = self.videos.get(remote_video_id, {}).get("analytics", {})
        metrics = {name: AnalyticsMetric.model_validate(value) for name, value in scripted.items()}
        return AnalyticsSnapshotData(video_id=remote_video_id, channel_id=channel_id, report_start=report_start, report_end=report_end, observed_at=datetime.now(UTC), metrics=metrics, completeness="complete" if metrics else "unavailable")


def _atomic_write(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_bytes(payload)
    temporary.replace(destination)


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _solid_png(width: int, height: int, color: tuple[int, int, int]) -> bytes:
    """Build a valid, dependency-free RGB PNG for offline media tests."""
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


__all__ = ["FakeContentProvider", "FakeMediaProvider", "FakePublisher", "FakeVoiceProvider", "ProviderAuthenticationError", "ProviderValidationError", "RetryableProviderError"]
