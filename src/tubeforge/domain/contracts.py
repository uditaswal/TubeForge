"""Pydantic contracts exchanged between TubeForge pipeline stages and providers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class DomainModel(BaseModel):
    """Strict immutable base for portable stage and provider contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ClaimReviewStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


class SourceReference(DomainModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    url: HttpUrl
    title: str = Field(min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=300)
    retrieved_at: datetime | None = None
    content_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    excerpt: str | None = Field(default=None, max_length=24_000)


class ContentRequest(DomainModel):
    """Bounded, provider-neutral request for one structured content package."""

    topic: str = Field(min_length=1, max_length=500)
    angle: str = Field(min_length=1, max_length=1_000)
    target_duration_seconds: int = Field(ge=30, le=7_200)
    language: str = Field(min_length=2, max_length=35)
    audience: str = Field(min_length=1, max_length=200)
    sources: tuple[SourceReference, ...] = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_unique_source_ids(self) -> ContentRequest:
        _require_unique_ids(self.sources, "source_id")
        return self


class CitedClaim(DomainModel):
    """A factual assertion with durable source links and human-review signal."""

    claim_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    text: str = Field(min_length=1, max_length=4_000)
    source_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    confidence: ConfidenceLevel
    review_status: ClaimReviewStatus
    human_review_required: bool
    time_sensitive: bool = False

    @model_validator(mode="after")
    def require_review_for_uncertain_claims(self) -> CitedClaim:
        if self.confidence is ConfidenceLevel.LOW and not self.human_review_required:
            raise ValueError("low-confidence claims must require human review")
        if self.review_status is ClaimReviewStatus.NEEDS_REVIEW and not self.human_review_required:
            raise ValueError("claims needing review must require human review")
        if self.time_sensitive and not self.human_review_required:
            raise ValueError("time-sensitive claims must require human review")
        return self


class ScriptSection(DomainModel):
    section_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    narration: str = Field(min_length=1, max_length=12_000)
    scene_id: str = Field(min_length=1, max_length=64)
    claim_ids: tuple[str, ...] = Field(default=())
    contains_factual_claims: bool = False

    @model_validator(mode="after")
    def require_claims_for_factual_sections(self) -> ScriptSection:
        if self.contains_factual_claims and not self.claim_ids:
            raise ValueError("factual script sections must reference cited claims")
        return self


class ScenePlan(DomainModel):
    scene_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    visual_type: str = Field(min_length=1, max_length=100)
    search_queries: tuple[str, ...] = Field(min_length=1, max_length=10)
    on_screen_text: str | None = Field(default=None, max_length=500)
    fallback_visual: str = Field(min_length=1, max_length=100)


class Chapter(DomainModel):
    section_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=150)


class VideoMetadata(DomainModel):
    title_options: tuple[str, ...] = Field(min_length=1, max_length=10)
    description: str = Field(min_length=1, max_length=10_000)
    tags: tuple[str, ...] = Field(default=(), max_length=30)
    chapters: tuple[Chapter, ...] = Field(default=())


class ThumbnailBrief(DomainModel):
    text_options: tuple[str, ...] = Field(min_length=1, max_length=5)
    visual_direction: str = Field(min_length=1, max_length=1_000)
    accessibility_description: str = Field(min_length=1, max_length=500)


class ClipCandidate(DomainModel):
    clip_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    section_ids: tuple[str, ...] = Field(min_length=1, max_length=20)
    hook: str = Field(min_length=1, max_length=500)
    rationale: str = Field(min_length=1, max_length=1_000)
    target_duration_seconds: int = Field(ge=15, le=180)


class ContentPackage(DomainModel):
    """Validated single-call creative plan consumed by deterministic stages."""

    schema_version: str = Field(pattern=r"^1\.0$")
    request: ContentRequest
    claims: tuple[CitedClaim, ...] = Field(min_length=1, max_length=500)
    script_sections: tuple[ScriptSection, ...] = Field(min_length=1, max_length=500)
    scene_plans: tuple[ScenePlan, ...] = Field(min_length=1, max_length=500)
    metadata: VideoMetadata
    thumbnail_brief: ThumbnailBrief
    clip_candidates: tuple[ClipCandidate, ...] = Field(default=(), max_length=8)

    @model_validator(mode="after")
    def validate_references(self) -> ContentPackage:
        _require_unique_ids(self.claims, "claim_id")
        _require_unique_ids(self.script_sections, "section_id")
        _require_unique_ids(self.scene_plans, "scene_id")
        _require_unique_ids(self.clip_candidates, "clip_id")
        source_ids = {source.source_id for source in self.request.sources}
        claim_ids = {claim.claim_id for claim in self.claims}
        section_ids = [section.section_id for section in self.script_sections]
        scene_ids = {scene.scene_id for scene in self.scene_plans}
        _require_known_references(
            (source_id for claim in self.claims for source_id in claim.source_ids), source_ids, "source"
        )
        _require_known_references(
            (claim_id for section in self.script_sections for claim_id in section.claim_ids), claim_ids, "claim"
        )
        _require_known_references((section.scene_id for section in self.script_sections), scene_ids, "scene")
        _require_known_references((chapter.section_id for chapter in self.metadata.chapters), set(section_ids), "section")
        section_positions = {section_id: index for index, section_id in enumerate(section_ids)}
        for clip in self.clip_candidates:
            _require_known_references(clip.section_ids, set(section_ids), "section")
            positions = [section_positions[section_id] for section_id in clip.section_ids]
            if positions != list(range(min(positions), max(positions) + 1)):
                raise ValueError(f"clip {clip.clip_id!r} must contain contiguous script sections")
        return self


class VoiceRequest(DomainModel):
    """Provider-neutral request for a single stable narration phrase."""

    text: str = Field(min_length=1, max_length=12_000)
    language: str = Field(min_length=2, max_length=35)
    voice_id: str = Field(min_length=1, max_length=200)
    section_id: str = Field(min_length=1, max_length=64)
    phrase_id: str | None = Field(default=None, min_length=1, max_length=100)
    output_path: str | None = Field(default=None, max_length=4_096)
    settings: tuple[tuple[str, str], ...] = ()


class VoiceResult(DomainModel):
    artifact_path: str = Field(min_length=1, max_length=4_096)
    duration_seconds: float = Field(gt=0)
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_name: str = Field(min_length=1, max_length=100)


class MediaSearchRequest(DomainModel):
    """Provider-neutral, deterministic request derived from one approved scene."""

    scene_id: str = Field(min_length=1, max_length=64)
    queries: tuple[str, ...] = Field(min_length=1, max_length=10)
    visual_type: str = Field(min_length=1, max_length=100)
    required_license: str = Field(min_length=1, max_length=200)
    orientation: str = Field(default="landscape", pattern=r"^(landscape|portrait|square|any)$")

    @model_validator(mode="after")
    def require_safe_queries(self) -> MediaSearchRequest:
        if any(not query.strip() or len(query) > 300 for query in self.queries):
            raise ValueError("media search queries must be nonblank and bounded")
        if any("youtube.com" in query.casefold() or "youtu.be" in query.casefold() for query in self.queries):
            raise ValueError("media searches must not target YouTube videos")
        return self


AssetSearchRequest = MediaSearchRequest


class AssetCandidate(DomainModel):
    """Rights-bearing media candidate. Free-to-view metadata is insufficient."""

    provider_asset_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,299}$")
    source_url: HttpUrl
    download_url: HttpUrl | None = None
    source_version: str | None = Field(default=None, max_length=200)
    local_path: str | None = Field(default=None, max_length=4096)
    media_type: str = Field(default="image", pattern=r"^(image|video)$")
    width: int | None = Field(default=None, ge=1, le=20_000)
    height: int | None = Field(default=None, ge=1, le=20_000)
    duration_seconds: float | None = Field(default=None, gt=0, le=86_400)
    author: str | None = Field(default=None, max_length=300)
    license_name: str = Field(min_length=1, max_length=300)
    license_url: HttpUrl | None = None
    attribution_text: str | None = Field(default=None, max_length=2_000)
    attribution_required: bool = False
    editorial_only: bool = False
    review_required: bool = False
    retrieved_at: datetime

    @model_validator(mode="after")
    def require_complete_rights(self) -> AssetCandidate:
        if self.license_name.casefold() in {"unknown", "free", "free to view", "n/a"}:
            raise ValueError("asset licence must be explicitly reusable")
        if self.attribution_required and not self.attribution_text:
            raise ValueError("attribution-required assets need attribution text")
        return self


class PublishPrivacy(StrEnum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class PublishRequest(DomainModel):
    platform: str = Field(min_length=1, max_length=100)
    artifact_path: str = Field(min_length=1, max_length=4_096)
    metadata: VideoMetadata
    privacy: PublishPrivacy
    idempotency_key: str = Field(min_length=1, max_length=200)
    public_publish_approval_id: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_explicit_approval_for_public_publish(self) -> PublishRequest:
        if self.privacy is PublishPrivacy.PUBLIC and not self.public_publish_approval_id:
            raise ValueError("public publishing requires an explicit public approval id")
        return self


class PublishResult(DomainModel):
    platform: str = Field(min_length=1, max_length=100)
    remote_id: str = Field(min_length=1, max_length=500)
    privacy: PublishPrivacy
    receipt_id: str = Field(min_length=1, max_length=500)


class RemoteProcessingState(StrEnum):
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class RemotePublicationSnapshot(DomainModel):
    """Provider-neutral, read-only view of a single persisted remote video ID."""

    video_id: str = Field(min_length=1, max_length=500)
    exists: bool
    processing: RemoteProcessingState = RemoteProcessingState.UNKNOWN
    processing_reason: str | None = Field(default=None, max_length=1_000)
    privacy: PublishPrivacy | None = None
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=10_000)
    tags: tuple[str, ...] | None = Field(default=None, max_length=100)
    # Data API exposes generated thumbnail URLs, not proof of exact uploaded bytes.
    thumbnail_present: bool | None = None


class MetricAvailability(StrEnum):
    """Meaning of an analytics metric; missing data is never silently zero."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_YET_REPORTED = "not_yet_reported"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


class AnalyticsMetric(DomainModel):
    """A normalized metric value. Percentage values use 0--100 semantics."""

    value: float | int | None = None
    availability: MetricAvailability = MetricAvailability.AVAILABLE

    @model_validator(mode="after")
    def require_value_when_available(self) -> "AnalyticsMetric":
        if self.availability is MetricAvailability.AVAILABLE and self.value is None:
            raise ValueError("available metrics require a value")
        if self.availability is not MetricAvailability.AVAILABLE and self.value is not None:
            raise ValueError("unavailable metrics must not contain a value")
        return self


class AnalyticsSnapshotData(DomainModel):
    """Read-only, provider-neutral analytics response for one video/report window."""

    video_id: str = Field(min_length=1, max_length=500)
    channel_id: str = Field(min_length=1, max_length=200)
    report_start: date
    report_end: date
    observed_at: datetime
    metrics: dict[str, AnalyticsMetric]
    completeness: str = Field(default="complete", pattern=r"^(complete|partial|unavailable)$")
    source: str = Field(default="youtube-analytics", min_length=1, max_length=100)
    query_version: str = Field(default="1", min_length=1, max_length=100)


def _require_unique_ids(items: tuple[object, ...], field_name: str) -> None:
    values = [getattr(item, field_name) for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} values must be unique")


def _require_known_references(references: Iterable[str], known_ids: set[str], label: str) -> None:
    for reference in references:
        if reference not in known_ids:
            raise ValueError(f"unknown {label} reference: {reference!r}")
