"""Pydantic contracts exchanged between TubeForge pipeline stages and providers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
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
    text: str = Field(min_length=1, max_length=12_000)
    language: str = Field(min_length=2, max_length=35)
    voice_id: str = Field(min_length=1, max_length=200)
    section_id: str = Field(min_length=1, max_length=64)


class VoiceResult(DomainModel):
    artifact_path: str = Field(min_length=1, max_length=4_096)
    duration_seconds: float = Field(gt=0)
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_name: str = Field(min_length=1, max_length=100)


class AssetSearchRequest(DomainModel):
    queries: tuple[str, ...] = Field(min_length=1, max_length=10)
    visual_type: str = Field(min_length=1, max_length=100)
    required_license: str = Field(min_length=1, max_length=200)


class AssetCandidate(DomainModel):
    provider_asset_id: str = Field(min_length=1, max_length=300)
    source_url: HttpUrl
    author: str | None = Field(default=None, max_length=300)
    license_name: str = Field(min_length=1, max_length=300)
    attribution_text: str | None = Field(default=None, max_length=2_000)
    retrieved_at: datetime


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


def _require_unique_ids(items: tuple[object, ...], field_name: str) -> None:
    values = [getattr(item, field_name) for item in items]
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} values must be unique")


def _require_known_references(references: Iterable[str], known_ids: set[str], label: str) -> None:
    for reference in references:
        if reference not in known_ids:
            raise ValueError(f"unknown {label} reference: {reference!r}")
