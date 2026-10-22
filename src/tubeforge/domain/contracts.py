"""Pydantic contracts exchanged between TubeForge pipeline stages and providers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator, model_serializer

from tubeforge.rendering.shorts.schema import ShortsTopic


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

    channel_identity: str = Field(default="default", pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    channel_voice_profile: str = Field(default="Clear, practical and conversational. Address the viewer directly; use complete sentences, explain unfamiliar terms, avoid hype, unsupported claims and invented personal experience.", min_length=1, max_length=4000)
    topic: str = Field(min_length=1, max_length=500)
    angle: str = Field(min_length=1, max_length=1_000)
    target_duration_seconds: int = Field(ge=25, le=7_200)
    language: str = Field(min_length=2, max_length=35)
    audience: str = Field(min_length=1, max_length=200)
    sources: tuple[SourceReference, ...] = Field(min_length=1, max_length=100)
    prompt_version: str = Field(min_length=1, max_length=100)
    notes: tuple[str, ...] = Field(default=(), max_length=30)
    review_mode: str = Field(default="manual", pattern=r"^(manual|auto)$")
    captions_enabled: bool = True
    music_track: str | None = Field(default=None, max_length=200)
    visual_style: str = Field(default="cinematic-tech", min_length=1, max_length=100)
    # Generated stills are local deterministic scene art.  Stock is limited
    # to the configured rights-safe provider; arbitrary search-engine images
    # never enter a production job because their reuse rights are unknown.
    visual_source: str = Field(default="generated", pattern=r"^(generated|stock)$")
    voice_id: str | None = Field(default=None, min_length=1, max_length=200)
    mcp_servers: tuple[str, ...] = Field(default=(), max_length=50)
    # A source-clip job is intentionally still a ContentRequest: it uses the
    # same job, lease, approval, and artifact records as generated videos.
    # The source URL is also retained in a normal SourceReference for audit.
    production_mode: str = Field(default="generated", pattern=r"^(generated|source_clip)$")
    source_url: HttpUrl | None = None
    clip_count: int = Field(default=1, ge=1, le=12)
    preset_name: str = Field(default="default", min_length=1, max_length=100)
    aspect_ratio: str = Field(default="16:9", pattern=r"^(16:9|9:16)$")
    # Which AI writes the script for this job. The default is omitted from the
    # serialized form so existing jobs, cache keys and host requests stay
    # byte-identical; only a non-default owner changes them.
    script_owner: str = Field(default="codex", pattern=r"^(codex|claude)$")
    # Which model the owner runs (Claude only): "sonnet-medium" | "opus". None = owner default.
    script_model: str | None = Field(default=None, pattern=r"^(sonnet-medium|opus)$")

    @model_serializer(mode="wrap")
    def omit_default_script_fields(self, handler):
        value = handler(self)
        if self.script_owner == "codex":
            value.pop("script_owner", None)
        if self.script_model is None:
            value.pop("script_model", None)
        return value

    @model_validator(mode="after")
    def require_unique_source_ids(self) -> ContentRequest:
        if self.prompt_version == "m6-content-v8":
            if self.aspect_ratio != "9:16" or not 25 <= self.target_duration_seconds <= 45:
                raise ValueError("reference Shorts require 9:16 and a 25–45 second target")
        elif self.target_duration_seconds < 30:
            raise ValueError("legacy requests require at least 30 seconds")
        _require_unique_ids(self.sources, "source_id")
        if any(not note.strip() for note in self.notes):
            raise ValueError("notes must not contain blank values")
        if len(set(self.mcp_servers)) != len(self.mcp_servers) or any(not name.strip() for name in self.mcp_servers):
            raise ValueError("mcp_servers must be unique and nonblank")
        if self.production_mode == "source_clip" and self.source_url is None:
            raise ValueError("source_clip requests require source_url")
        if self.production_mode == "generated" and self.source_url is not None:
            raise ValueError("generated requests must not include source_url")
        return self


def generation_request_content(request: ContentRequest) -> ContentRequest:
    """Strip v7 capture-only fields before sending semantic input to a writer."""
    if request.prompt_version not in {"m6-content-v7", "m6-content-v8"}:
        return request
    sources = tuple(source.model_copy(update={"retrieved_at": None, "content_sha256": None}) for source in request.sources)
    return request.model_copy(update={"sources": sources})


def generation_request_key_payload(request: ContentRequest) -> dict[str, object]:
    """Return semantic request inputs, excluding v7 source-capture metadata.

    Capture timestamps and excerpt hashes belong to the source_packet evidence
    artifact. The exact source text and citation remain part of generation
    identity, while adding provenance during ingestion must not cause a cache
    miss for the same reviewed request.
    """
    value = generation_request_content(request).model_dump(mode="json")
    if request.prompt_version in {"m6-content-v1", "m6-content-v2", "m6-content-v3", "m6-content-v4"} and request.channel_identity == "default" and request.channel_voice_profile == ContentRequest.model_fields["channel_voice_profile"].default:
        value.pop("channel_identity")
        value.pop("channel_voice_profile")
    return value


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
        # Reject serialized production panels rather than speaking them. This
        # checks field separation, not the script's editorial quality.
        import re
        if not self.narration.strip() or re.search(
            r"```|\[(?:ON SCREEN|HOOK|PRODUCTION|SOURCE|SCORE)[^\]]*\]|^\s*(?:ON SCREEN|Hook \d+|Sources|Production notes|Hook scores)\s*:",
            self.narration, re.I | re.M,
        ):
            raise ValueError("narration must contain audience-facing speech without production panels")
        if self.contains_factual_claims and not self.claim_ids:
            raise ValueError("factual script sections must reference cited claims")
        return self


class TerminalRevealCues(DomainModel):
    """Local spoken-word positions; timestamps are resolved after TTS."""

    command_start_word_index: int = Field(ge=0)
    command_end_word_index: int = Field(ge=0)
    output_word_index: int = Field(ge=0)
    secondary_word_index: int = Field(ge=0)
    third_word_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_order(self) -> TerminalRevealCues:
        if not (self.command_start_word_index <= self.command_end_word_index < self.output_word_index < self.secondary_word_index):
            raise ValueError("terminal reveal word indices must be ordered")
        if self.third_word_index is not None and self.third_word_index <= self.secondary_word_index:
            raise ValueError("terminal third reveal must follow the second")
        return self


class CardMotionKind(StrEnum):
    HOOK = "hook"
    CLOSE = "close"


class CardRevealCues(DomainModel):
    """Three ordered content reveals anchored to local spoken-word positions."""

    kind: CardMotionKind
    first_word_index: int = Field(ge=0)
    second_word_index: int = Field(ge=0)
    third_word_index: int = Field(ge=0)

    @model_validator(mode="after")
    def require_order(self) -> CardRevealCues:
        if not (self.first_word_index < self.second_word_index < self.third_word_index):
            raise ValueError("card reveal word indices must be ordered")
        return self


class TeachingRevealCues(DomainModel):
    """Three spoken-word anchors for a non-terminal teaching layout."""

    first_word_index: int = Field(ge=0)
    second_word_index: int = Field(ge=0)
    third_word_index: int = Field(ge=0)
    comparison_panels_first: bool = False

    @model_validator(mode="after")
    def require_order(self) -> TeachingRevealCues:
        if not (self.first_word_index < self.second_word_index < self.third_word_index):
            raise ValueError("teaching reveal word indices must be ordered")
        return self


class ScenePlan(DomainModel):
    scene_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    visual_type: str = Field(min_length=1, max_length=100)
    search_queries: tuple[str, ...] = Field(min_length=1, max_length=10)
    on_screen_text: str | None = Field(default=None, max_length=500)
    fallback_visual: str = Field(min_length=1, max_length=100)
    visual_subject: str | None = Field(default=None, min_length=1, max_length=200)
    visual_purpose: str | None = Field(default=None, min_length=1, max_length=300)
    composition: str | None = Field(default=None, min_length=1, max_length=200)
    visual_elements: tuple[str, ...] = Field(default=(), max_length=4)
    terminal_cues: TerminalRevealCues | None = None
    card_cues: CardRevealCues | None = None
    teaching_cues: TeachingRevealCues | None = None

    @model_validator(mode="after")
    def require_short_visual_elements(self) -> ScenePlan:
        if any(not item.strip() or len(item) > 80 for item in self.visual_elements):
            raise ValueError("visual elements must be nonblank and at most 80 characters")
        _validate_explicit_layout(self.visual_type, self.visual_elements, self.on_screen_text)
        if self.terminal_cues is not None and (self.visual_type != "terminal" or len(self.visual_elements) < 2):
            raise ValueError("terminal reveal cues require a terminal scene with two display elements")
        if self.terminal_cues is not None and self.terminal_cues.third_word_index is not None and len(self.visual_elements) != 3:
            raise ValueError("terminal third reveal requires a third display element")
        if self.card_cues is not None and (self.visual_type not in {"comparison", "flow_diagram", "timeline"} or len(self.visual_elements) != 3 or self.terminal_cues is not None):
            raise ValueError("card reveal cues require a comparison, flow diagram, or timeline scene with three display elements")
        if self.teaching_cues is not None and (self.visual_type not in {"flow_diagram", "comparison", "timeline", "source_card"} or len(self.visual_elements) != 3 or self.terminal_cues is not None or self.card_cues is not None):
            raise ValueError("teaching reveal cues require three non-terminal elements and no other motion cues")
        if self.teaching_cues is not None and self.teaching_cues.comparison_panels_first and self.visual_type != "comparison":
            raise ValueError("comparison panel reveal order requires a comparison scene")
        return self


def _validate_explicit_layout(kind: str, elements: tuple[str, ...], on_screen_text: str | None) -> None:
    """Keep new layout IDs lossless while leaving legacy prose scene types intact."""
    if kind in {"flow_diagram", "comparison", "timeline", "source_card"} and len(elements) != 3:
        raise ValueError(f"{kind} layout requires exactly three visual elements")
    if kind == "terminal" and (not on_screen_text or not on_screen_text.strip() or len(elements) > 3):
        raise ValueError("terminal layout requires a command and at most three output elements")


class Chapter(DomainModel):
    section_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=150)


class VideoMetadata(DomainModel):
    title_options: tuple[str, ...] = Field(min_length=1, max_length=10)
    description: str = Field(min_length=1, max_length=10_000)
    call_to_action: str | None = Field(default=None, min_length=1, max_length=300)
    tags: tuple[str, ...] = Field(default=(), max_length=30)
    chapters: tuple[Chapter, ...] = Field(default=())
    engagement_comment: str | None = Field(default=None, min_length=1, max_length=280)

    @model_serializer(mode="wrap")
    def preserve_legacy_serialization(self, handler):
        value = handler(self)
        if self.engagement_comment is None:
            value.pop("engagement_comment", None)
        return value

    @model_validator(mode="after")
    def validate_engagement_comment(self) -> VideoMetadata:
        text = (self.engagement_comment or "").casefold()
        if any(marker in text for marker in ("http://", "https://", "www.", "@", "#")):
            raise ValueError("engagement comment must not contain links, mentions or hashtags")
        if self.engagement_comment is not None and "?" not in self.engagement_comment:
            raise ValueError("engagement comment must pose a question")
        return self


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
    hook_options: tuple[str, ...] = Field(default=(), max_length=5)
    clip_candidates: tuple[ClipCandidate, ...] = Field(default=(), max_length=8)
    reference_short: ShortsTopic | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_serialization(self, handler):
        value = handler(self)
        if self.reference_short is None:
            value.pop("reference_short", None)
        return value

    @model_validator(mode="after")
    def validate_references(self) -> ContentPackage:
        if (self.request.prompt_version == "m6-content-v8") != (self.reference_short is not None):
            raise ValueError("reference scene data is required only for v8 requests")
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
                raise ValueError(f"clip {clip.clip_id!r} must contain contiguous script sections in script order (got {list(clip.section_ids)})")
        if self.reference_short is not None:
            topic = self.reference_short
            if [s.scene_id for s in topic.scenes] != [s.scene_id for s in self.script_sections]:
                raise ValueError("reference scenes must match ordered narration")
            if [s.vo for s in topic.scenes] != [s.narration for s in self.script_sections]:
                raise ValueError("reference speech differs from canonical narration")
            references = {s.source_id: s for s in self.request.sources}
            for source in topic.sources:
                approved = references.get(source.source_id)
                if approved is None or source.url != approved.url:
                    raise ValueError("reference visual cites an unapproved source URL")
                name = (approved.author or approved.title)[:42]
                if source.name != name:
                    raise ValueError("reference source label differs from trusted attribution")
            claims = {c.claim_id: c for c in self.claims}
            for scene, section in zip(topic.scenes, self.script_sections, strict=True):
                cited = {source for claim_id in section.claim_ids for source in claims[claim_id].source_ids}
                if set(scene.source_ids) != cited:
                    raise ValueError("reference visual sources differ from narrated claims")
        return self


class VideoPlanScene(DomainModel):
    """Renderer-facing scene projection with explicit local fallback intent."""

    scene_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    duration_seconds: float = Field(gt=0, le=7_200)
    narration: str = Field(min_length=1, max_length=12_000)
    visual_intent: str = Field(min_length=1, max_length=1_000)
    preferred_strategy: str = Field(min_length=1, max_length=100)
    fallback_strategy: str = Field(min_length=1, max_length=100)
    camera_direction: str = Field(default="gentle pan", min_length=1, max_length=200)
    asset_references: tuple[str, ...] = Field(default=(), max_length=20)
    visual_subject: str = Field(default="", max_length=200)
    visual_purpose: str = Field(default="", max_length=300)
    composition: str = Field(default="", max_length=200)
    on_screen_text: str = Field(default="", max_length=500)
    search_queries: tuple[str, ...] = Field(default=(), max_length=10)
    visual_elements: tuple[str, ...] = Field(default=(), max_length=4)


class VideoPlan(DomainModel):
    """Durable provider-neutral storyboard consumed by rendering and variants."""

    schema_version: str = Field(default="1.0", pattern=r"^1\.0$")
    topic: str = Field(min_length=1, max_length=500)
    notes: tuple[str, ...] = Field(default=(), max_length=30)
    target_platform: str = Field(default="youtube", min_length=1, max_length=100)
    duration_seconds: int = Field(ge=30, le=7_200)
    aspect_ratio: str = Field(default="16:9", pattern=r"^(16:9|9:16|1:1)$")
    audience: str = Field(min_length=1, max_length=200)
    language: str = Field(min_length=2, max_length=35)
    tone: str = Field(default="informative", min_length=1, max_length=100)
    hook: str = Field(min_length=1, max_length=1_000)
    cta: str = Field(default="", max_length=500)
    narration: str = Field(min_length=1, max_length=100_000)
    style: str = Field(min_length=1, max_length=100)
    caption_style: str = Field(default="readable", min_length=1, max_length=100)
    music_intent: str | None = Field(default=None, max_length=200)
    continuity_identity: str = Field(min_length=1, max_length=200)
    scenes: tuple[VideoPlanScene, ...] = Field(min_length=1, max_length=500)


def video_plan_from_package(package: ContentPackage, *, target_platform: str = "youtube", aspect_ratio: str = "16:9") -> VideoPlan:
    """Create a deterministic storyboard projection without changing old providers."""
    scenes = {scene.scene_id: scene for scene in package.scene_plans}
    duration = package.request.target_duration_seconds / len(package.script_sections)
    projected = tuple(
        VideoPlanScene(
            scene_id=section.scene_id,
            duration_seconds=duration,
            narration=section.narration,
            visual_intent=scenes[section.scene_id].visual_type,
            preferred_strategy="licensed_asset",
            fallback_strategy=scenes[section.scene_id].fallback_visual,
            visual_subject=scenes[section.scene_id].visual_subject or scenes[section.scene_id].search_queries[0],
            visual_purpose=scenes[section.scene_id].visual_purpose or scenes[section.scene_id].visual_type,
            composition=scenes[section.scene_id].composition or scenes[section.scene_id].visual_type,
            on_screen_text=scenes[section.scene_id].on_screen_text or "",
            search_queries=scenes[section.scene_id].search_queries,
            visual_elements=scenes[section.scene_id].visual_elements,
        )
        for section in package.script_sections
    )
    narration = "\n\n".join(section.narration for section in package.script_sections)
    return VideoPlan(topic=package.request.topic, notes=package.request.notes, target_platform=target_platform, duration_seconds=package.request.target_duration_seconds, aspect_ratio=aspect_ratio, audience=package.request.audience, language=package.request.language, hook=package.script_sections[0].narration[:500], narration=narration, style=package.request.visual_style, music_intent=package.request.music_track, continuity_identity=f"{package.request.visual_style}:{package.request.language}", scenes=projected)


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
    visual_source: str = Field(default="generated", pattern=r"^(generated|stock)$")
    visual_subject: str = Field(default="", max_length=200)
    visual_purpose: str = Field(default="", max_length=300)
    composition: str = Field(default="", max_length=200)
    on_screen_text: str = Field(default="", max_length=500)
    visual_elements: tuple[str, ...] = Field(default=(), max_length=4)

    @model_validator(mode="after")
    def require_safe_queries(self) -> MediaSearchRequest:
        if any(not query.strip() or len(query) > 300 for query in self.queries):
            raise ValueError("media search queries must be nonblank and bounded")
        if any("youtube.com" in query.casefold() or "youtu.be" in query.casefold() for query in self.queries):
            raise ValueError("media searches must not target YouTube videos")
        _validate_explicit_layout(self.visual_type, self.visual_elements, self.on_screen_text)
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
