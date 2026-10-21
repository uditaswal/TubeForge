"""Validated, non-secret application configuration."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from tubeforge.domain.contracts import SourceReference


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / "config" / "default.yaml"
SUPPORTED_VIDEO_ENCODERS = {"libx264": "h264", "libx265": "hevc"}
SUPPORTED_AUDIO_ENCODERS = {"aac": "aac", "libopus": "opus"}


class AppConfig(BaseModel):
    """Settings for the local FastAPI process."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    environment: str = Field(pattern=r"^(development|test|production)$")
    bind_host: str = "127.0.0.1"
    port: int = Field(default=8080, ge=1, le=65535)


class DatabaseConfig(BaseModel):
    """Portable SQLAlchemy database settings for the initial SQLite backend."""

    model_config = ConfigDict(extra="forbid")

    url: str
    busy_timeout_ms: int = Field(default=5000, ge=0, le=120_000)

    @field_validator("url")
    @classmethod
    def require_sqlite_url(cls, value: str) -> str:
        """Keep the first deployment constrained to a local SQLite database."""
        if not value.startswith("sqlite:///"):
            raise ValueError("database.url must be a sqlite:/// URL in Phase 1")
        return value


class FakeProviderConfig(BaseModel):
    """Non-secret deterministic provider settings used by development and tests."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    artifact_root: Path = Path("./data/fake-artifacts")
    voice_id: str = Field(default="fake-voice", min_length=1, max_length=200)
    media_license: str = Field(default="CC0-1.0", min_length=1, max_length=200)

class MediaPipelineConfig(BaseModel):
    """Safe, provider-neutral M8 asset acquisition policy."""

    model_config = ConfigDict(extra="forbid")
    provider: str = Field(default="fake", pattern=r"^(fake|wikimedia|hybrid)$")
    cache_root: Path = Path("./data/cache/assets")
    allowed_hosts: tuple[str, ...] = ("upload.wikimedia.org", "commons.wikimedia.org")
    allowed_licenses: tuple[str, ...] = ("CC0-1.0", "CC BY 4.0", "CC BY-SA 4.0", "Public Domain")
    allowed_media_types: tuple[str, ...] = ("image", "video")
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_redirects: int = Field(default=0, ge=0, le=5)
    max_bytes: int = Field(default=100_000_000, ge=1_024, le=2_000_000_000)
    max_width: int = Field(default=12_000, ge=1, le=20_000)
    max_height: int = Field(default=12_000, ge=1, le=20_000)
    max_duration_seconds: float = Field(default=900, gt=0, le=86_400)
    min_width: int = Field(default=64, ge=1, le=20_000)
    min_height: int = Field(default=64, ge=1, le=20_000)
    allowed_extensions: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp", ".mp4", ".webm", ".mov")
    retries: int = Field(default=3, ge=0, le=10)
    wikimedia_api_url: str = "https://commons.wikimedia.org/w/api.php"

    @field_validator("allowed_hosts", "allowed_licenses", "allowed_media_types", "allowed_extensions")
    @classmethod
    def require_nonempty_unique_values(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(item.strip() for item in value if item.strip())
        if not normalized or len({item.casefold() for item in normalized}) != len(normalized):
            raise ValueError("must contain unique nonblank values")
        return normalized


class SourceIngestionConfig(BaseModel):
    """Opt-in, bounded retrieval policy for the factual sources of one job."""

    model_config = ConfigDict(extra="forbid")

    research_enabled: bool = False
    enabled: bool = False
    allowed_hosts: tuple[str, ...] = ()
    timeout_seconds: int = Field(default=20, ge=1, le=300)
    max_bytes: int = Field(default=2_000_000, ge=1_024, le=20_000_000)
    max_chars: int = Field(default=24_000, ge=1_000, le=24_000)
    channel_approved: dict[str, tuple[SourceReference, ...]] = Field(default_factory=dict)

    @field_validator("allowed_hosts")
    @classmethod
    def require_unique_hosts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(host.strip().casefold() for host in value if host.strip())
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_hosts must contain unique nonblank values")
        return normalized

    @model_validator(mode="after")
    def require_hosts_when_enabled(self) -> "SourceIngestionConfig":
        if self.enabled and not self.allowed_hosts:
            raise ValueError("source ingestion requires at least one allowed host when enabled")
        if any(not channel.strip() or any(not source.excerpt or not source.excerpt.strip() for source in sources) for channel, sources in self.channel_approved.items()):
            raise ValueError("channel-approved sources require a channel name and approved excerpts")
        return self


class SourceClipConfig(BaseModel):
    """Local, opt-in acquisition and vertical clip rendering policy."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    ytdlp_executable: str = Field(default="yt-dlp", min_length=1, max_length=4096)
    timeout_seconds: int = Field(default=120, ge=5, le=1_800)
    ffmpeg_executable: str = Field(default="ffmpeg", min_length=1, max_length=4096)
    ffprobe_executable: str = Field(default="ffprobe", min_length=1, max_length=4096)
    max_source_duration_seconds: int = Field(default=14_400, ge=30, le=86_400)
    min_clip_seconds: float = Field(default=15, ge=5, le=600)
    max_clip_seconds: float = Field(default=60, ge=10, le=900)
    padding_seconds: float = Field(default=3, ge=0, le=30)
    analysis_window_seconds: float = Field(default=0.5, ge=0.1, le=5)

    @model_validator(mode="after")
    def clip_bounds_are_ordered(self) -> "SourceClipConfig":
        if self.min_clip_seconds > self.max_clip_seconds:
            raise ValueError("source_clips.min_clip_seconds must not exceed max_clip_seconds")
        return self

class CodexProviderConfig(BaseModel):
    """Non-secret limits for the worker-to-host Codex runner client."""

    model_config = ConfigDict(extra="forbid")

    executable: str = Field(default="codex", min_length=1, max_length=4_096)
    model: str = Field(default="gpt-5.6-sol", min_length=1, max_length=200)
    timeout_seconds: int = Field(default=900, ge=1, le=7_200)
    max_output_bytes: int = Field(default=2_000_000, ge=1_024, le=20_000_000)
    max_diagnostic_bytes: int = Field(default=8_192, ge=256, le=65_536)
    reservation_seconds: int = Field(default=1_200, ge=10, le=14_400)
    repair_attempt_limit: int = Field(default=0, ge=0, le=5)
    voice_profiles: dict[str, str] = Field(default_factory=dict)
    default_channel_identity: str = Field(default="default", pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    prompt_template_version: str = Field(default="m6-content-v7", min_length=1, max_length=100)
    max_prompt_chars: int = Field(default=60_000, ge=1_000, le=200_000)
    socket_path: Path = Path("/run/tubeforge-codex/codex.sock")
    socket_timeout_seconds: int = Field(default=490, ge=1, le=600)
    invocation_limit: int = Field(default=2, ge=1, le=2)

    @field_validator("voice_profiles")
    @classmethod
    def validate_voice_profiles(cls, profiles: dict[str, str]) -> dict[str, str]:
        import re
        if len(profiles) > 100:
            raise ValueError("at most 100 channel voice profiles")
        for identity, profile in profiles.items():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", identity) or not profile.strip() or len(profile) > 4000:
                raise ValueError("voice profiles require bounded channel IDs and nonblank text up to 4000 characters")
        return profiles

    @field_validator("executable", "model", "prompt_template_version")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class OllamaProviderConfig(BaseModel):
    """Bounded settings for an opt-in local or LAN Ollama content adapter."""

    model_config = ConfigDict(extra="forbid")

    base_url: str = "http://127.0.0.1:11434"
    model: str = Field(default="llama3.2:3b", min_length=1, max_length=200)
    connection_timeout_seconds: int = Field(default=10, ge=1, le=300)
    inference_timeout_seconds: int = Field(default=300, ge=1, le=7_200)
    max_response_bytes: int = Field(default=2_000_000, ge=1_024, le=20_000_000)
    retries: int = Field(default=2, ge=0, le=5)
    validation_retries: int = Field(default=0, ge=0, le=3)
    reservation_seconds: int = Field(default=600, ge=10, le=14_400)
    prompt_template_version: str = Field(default="m6-content-v2", min_length=1, max_length=100)
    max_prompt_chars: int = Field(default=60_000, ge=1_000, le=200_000)

    @field_validator("base_url")
    @classmethod
    def require_safe_http_base_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("must not contain credentials, query parameters, or a fragment")
        return normalized

    @field_validator("model", "prompt_template_version")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

class PiperProviderConfig(BaseModel):
    """Opt-in local Piper settings; paths are resolved from the repository root."""

    model_config = ConfigDict(extra="forbid")

    executable: Path | str = "piper"
    server_url: str | None = None
    listen_host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    listen_port: int = Field(default=5000, ge=1, le=65_535)
    model_path: Path | None = None
    config_path: Path | None = None
    voice_id: str = Field(default="piper", min_length=1, max_length=200)
    speaker: int | None = Field(default=None, ge=0, le=10_000)
    output_format: str = Field(default="wav", pattern=r"^wav$")
    sample_rate: int | None = Field(default=None, ge=8_000, le=96_000)
    timeout_seconds: int = Field(default=120, ge=1, le=3_600)
    max_output_bytes: int = Field(default=100_000_000, ge=1_024, le=2_000_000_000)
    max_diagnostic_bytes: int = Field(default=8_192, ge=256, le=65_536)
    threads: int = Field(default=1, ge=1, le=4)
    cache_root: Path = Path("./data/cache/tts")
    adapter_version: str = Field(default="m7-piper-v1", min_length=1, max_length=100)

    @field_validator("server_url")
    @classmethod
    def validate_server_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from urllib.parse import urlsplit
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("pipeline.piper.server_url must be an HTTP(S) base URL without credentials, query or fragment")
        return normalized


class KokoroProviderConfig(BaseModel):
    """Optional higher-naturalness local Kokoro voices with Piper fallback."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    voices: tuple[str, ...] = ("af_bella", "af_sarah", "am_michael")
    model_path: Path | None = None
    voices_path: Path | None = None
    cache_root: Path = Path("./data/cache/kokoro")
    sample_rate: int = Field(default=24_000, ge=8_000, le=96_000)
    max_output_bytes: int = Field(default=100_000_000, ge=1_024, le=2_000_000_000)
    adapter_version: str = Field(default="m24-kokoro-v1", min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_distinct_voices(self) -> "KokoroProviderConfig":
        if not self.voices or len(set(self.voices)) != len(self.voices):
            raise ValueError("pipeline.kokoro.voices must be nonempty and unique")
        if any(not voice.strip() for voice in self.voices):
            raise ValueError("pipeline.kokoro.voices must be nonblank")
        return self


class VoicePipelineConfig(BaseModel):
    """Deterministic narration, assembly, and phrase-caption limits."""

    model_config = ConfigDict(extra="forbid")

    artifact_root: Path = Path("./data/artifacts")
    ffmpeg_executable: Path | str = "ffmpeg"
    ffprobe_executable: Path | str = "ffprobe"
    ffmpeg_threads: int = Field(default=1, ge=1, le=4)
    pause_seconds: float = Field(default=0.15, ge=0, le=5)
    caption_line_length: int = Field(default=42, ge=10, le=120)
    duration_tolerance_seconds: float = Field(default=0.15, ge=0.01, le=2)
    # Real local voices have model- and punctuation-dependent pacing. A
    # one-minute editorial request therefore accepts 42--78 seconds by
    # default; the final timing map still remains exact to the produced audio.
    target_duration_tolerance_ratio: float = Field(default=0.30, ge=0.01, le=0.50)
    alignment_provider: str = Field(default="local-waveform-v1", pattern=r"^(local-waveform-v1|whisper-base-en-dtw-v1)$")
    alignment_model_path: Path | None = None
    alignment_model_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def require_pinned_audio_grounded_model(self) -> "VoicePipelineConfig":
        if self.alignment_provider != "local-waveform-v1" and (self.alignment_model_path is None or self.alignment_model_sha256 is None):
            raise ValueError("audio-grounded alignment requires a local model path and SHA-256 pin")
        return self

class RenderProfile(BaseModel):
    """Bounded deterministic profile for the low-resolution review render."""

    model_config = ConfigDict(extra="forbid")
    width: int = Field(default=854, ge=160, le=3840)
    height: int = Field(default=480, ge=90, le=2160)
    fps: int = Field(default=30, ge=1, le=60)
    fps_tolerance: float = Field(default=0.05, ge=0, le=0.25)
    pixel_format: str = Field(default="yuv420p", pattern=r"^[A-Za-z0-9_]+$")
    video_codec: str = Field(default="libx264", pattern=r"^[A-Za-z0-9_.-]+$")
    video_crf: int = Field(default=23, ge=0, le=51)
    audio_codec: str = Field(default="aac", pattern=r"^[A-Za-z0-9_.-]+$")
    audio_bitrate: str = Field(default="128k", pattern=r"^[0-9]+[kKmM]$")
    audio_sample_rate: int = Field(default=48_000, ge=22_050, le=96_000)
    threads: int = Field(default=1, ge=1, le=4)
    timeout_seconds: int = Field(default=900, ge=1, le=7200)
    ffprobe_timeout_seconds: int = Field(default=30, ge=1, le=300)
    minimum_free_bytes: int = Field(default=250_000_000, ge=1)
    sync_tolerance_seconds: float = Field(default=0.25, ge=0.01, le=2)
    caption_font_size: int = Field(default=26, ge=12, le=96)
    caption_margin_vertical: int = Field(default=36, ge=0, le=800)
    caption_margin_horizontal: int = Field(default=40, ge=0, le=800)
    caption_center_x: int | None = Field(default=None, ge=0, le=3840)
    word_highlight_captions: bool = False
    scene_max_duration_seconds: float = Field(default=7_200, ge=0.5, le=7_200)
    image_motion_enabled: bool = True
    image_motion_zoom: float = Field(default=1.08, ge=1.0, le=1.25)
    image_motion_overscan: float = Field(default=2.0, ge=1.0, le=2.0)
    bounded_memory: bool = False
    audio_normalization_enabled: bool = False
    renderer_version: str = Field(default="m9-preview-v1", min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_supported_aspect_ratio(self) -> "RenderProfile":
        ratio = self.width / self.height
        if min(abs(ratio - 16 / 9), abs(ratio - 9 / 16)) > 0.02:
            raise ValueError("render resolution must be 16:9 or 9:16")
        if self.video_codec not in SUPPORTED_VIDEO_ENCODERS:
            raise ValueError(f"unsupported video encoder: {self.video_codec}")
        if self.audio_codec not in SUPPORTED_AUDIO_ENCODERS:
            raise ValueError(f"unsupported audio encoder: {self.audio_codec}")
        return self



class PreviewRenderConfig(RenderProfile):
    """Bounded deterministic profile for the low-resolution review render."""


class FinalRenderConfig(RenderProfile):
    """Bounded deterministic profile for final source rendering."""

    width: int = Field(default=1920, ge=160, le=3840)
    height: int = Field(default=1080, ge=90, le=2160)
    audio_bitrate: str = "160k"
    renderer_version: str = "m10-final-v1"


class ShortsPreviewRenderConfig(RenderProfile):
    """Fast portrait review render using the same timing as the final Short."""

    width: int = 540
    height: int = 960
    caption_font_size: int = 46
    caption_margin_vertical: int = 180
    caption_margin_horizontal: int = 48
    word_highlight_captions: bool = True
    scene_max_duration_seconds: float = 3.0
    image_motion_overscan: float = 1.25
    renderer_version: str = "shorts-preview-v1"


class ShortsFinalRenderConfig(RenderProfile):
    """YouTube Shorts export profile."""

    width: int = 1080
    height: int = 1920
    fps: int = 30
    audio_bitrate: str = "160k"
    audio_sample_rate: int = Field(default=48_000, ge=48_000, le=48_000)
    caption_font_size: int = Field(default=84, ge=84, le=96)
    caption_margin_vertical: int = 470
    caption_margin_horizontal: int = 96
    caption_center_x: int = Field(default=490, ge=60, le=930)
    word_highlight_captions: bool = True
    scene_max_duration_seconds: float = 3.0
    image_motion_overscan: float = 1.25
    bounded_memory: bool = True
    minimum_free_bytes: int = 500_000_000
    renderer_version: str = "shorts-final-v4"


class PublicationPreparationConfig(BaseModel):
    """Local M12 metadata and thumbnail policy, enforced before approval."""

    model_config = ConfigDict(extra="forbid")
    title_max_length: int = Field(default=100, ge=1, le=500)
    description_max_length: int = Field(default=5_000, ge=1, le=10_000)
    tag_max_count: int = Field(default=30, ge=1, le=100)
    tag_max_length: int = Field(default=100, ge=1, le=500)
    tag_payload_max_length: int = Field(default=500, ge=1, le=2_000)
    metadata_template_version: str = Field(default="m12-metadata-v1", min_length=1, max_length=100)
    thumbnail_template_version: str = Field(default="m12-thumbnail-v1", min_length=1, max_length=100)
    thumbnail_width: int = Field(default=1280, ge=160, le=3840)
    thumbnail_height: int = Field(default=720, ge=90, le=2160)
    thumbnail_max_bytes: int = Field(default=2_000_000, ge=1_024, le=10_000_000)

    @model_validator(mode="after")
    def require_16_by_9_thumbnail(self) -> "PublicationPreparationConfig":
        if abs(self.thumbnail_width / self.thumbnail_height - 16 / 9) > 0.02:
            raise ValueError("thumbnail resolution must be 16:9")
        return self


class YouTubePublishingConfig(BaseModel):
    """Explicitly opt-in, secret-free configuration for M13 publication."""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    dry_run: bool = True
    provider: str = Field(default="youtube", pattern=r"^youtube$")
    client_secret_path: Path | None = None
    token_storage_path: Path | None = None
    expected_channel_id: str | None = Field(default=None, min_length=1, max_length=200)
    privacy: str = Field(default="private", pattern=r"^(private|unlisted|public)$")
    chunk_size_bytes: int = Field(default=8_388_608, ge=262_144, le=64_000_000)
    implementation_version: str = Field(default="m13-youtube-v1", min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_external_paths_when_enabled(self) -> "YouTubePublishingConfig":
        if self.enabled and (self.client_secret_path is None or self.token_storage_path is None or self.expected_channel_id is None):
            raise ValueError("enabled YouTube publishing requires client_secret_path, token_storage_path, and expected_channel_id")
        return self

class PublicationVerificationConfig(BaseModel):
    """Bounded, passive M14 processing verification policy."""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    pending_poll_seconds: int = Field(default=300, ge=30, le=86_400)
    maximum_processing_wait_seconds: int = Field(default=86_400, ge=300, le=604_800)

class AnalyticsConfig(BaseModel):
    """Bounded post-publication, read-only collection policy."""
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    initial_delay_hours: int = Field(default=24, ge=0, le=720)
    collection_interval_hours: int = Field(default=24, ge=1, le=720)
    collection_horizon_days: int = Field(default=30, ge=1, le=3650)
    query_version: str = Field(default="m15-v1", min_length=1, max_length=100)

class PerformanceConfig(BaseModel):
    """Deterministic M16 evaluation thresholds."""
    model_config = ConfigDict(extra="forbid")
    evaluator_version: str = Field(default="m16-v1", min_length=1, max_length=100)
    proposal_version: str = Field(default="m16-proposal-v1", min_length=1, max_length=100)
    min_views_for_retention: int = Field(default=100, ge=0)
    min_impressions_for_ctr: int = Field(default=500, ge=0)
    baseline_min_videos: int = Field(default=5, ge=1)

class OptimizationCandidateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    max_title_candidates: int = Field(default=3, ge=1, le=3)
    max_thumbnail_candidates: int = Field(default=2, ge=1, le=3)
    template_version: str = Field(default="m17-v1", min_length=1, max_length=100)

class OptimizationExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    dry_run: bool = True
    executor_version: str = Field(default="m18-v1", min_length=1, max_length=100)

class OptimizationExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minimum_observation_hours: int = Field(default=24, ge=1, le=8760)
    evaluation_window_days: int = Field(default=7, ge=1, le=365)

class OptimizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: OptimizationCandidateConfig = Field(default_factory=OptimizationCandidateConfig)
    execution: OptimizationExecutionConfig = Field(default_factory=OptimizationExecutionConfig)
    experiment: OptimizationExperimentConfig = Field(default_factory=OptimizationExperimentConfig)

class LearningConfig(BaseModel):
    """Deterministic M20--M23 post-experiment learning policy."""
    model_config = ConfigDict(extra="forbid")
    evaluator_version: str = Field(default="m20-v1", min_length=1, max_length=100)
    recommendation_version: str = Field(default="m22-v1", min_length=1, max_length=100)
    brief_template_version: str = Field(default="m23-v1", min_length=1, max_length=100)
    minimum_post_hours: int = Field(default=24, ge=1, le=8760)
    minimum_views: int = Field(default=100, ge=0)
    minimum_history_videos: int = Field(default=3, ge=1, le=1000)
    max_active_recommendations: int = Field(default=5, ge=1, le=20)

class MusicTrackConfig(BaseModel):
    """An operator-approved background track; arbitrary URLs are never accepted per job."""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    path: Path | None = None
    source_url: str = Field(min_length=1, max_length=2_000)
    license_name: str = Field(min_length=1, max_length=300)
    license_url: str = Field(min_length=1, max_length=2_000)
    attribution_required: bool = False
    attribution: str = Field(default="", max_length=1_000)
    publishing_allowed: bool = True

    @model_validator(mode="after")
    def require_publishable_rights_record(self) -> "MusicTrackConfig":
        if self.license_name.strip().casefold() in {"free", "royalty free", "royalty-free", "unknown", "n/a"}:
            raise ValueError("music must record the actual licence name")
        if not self.publishing_allowed:
            raise ValueError("configured music must permit publishing")
        if self.attribution_required and not self.attribution.strip():
            raise ValueError("attribution-required music needs attribution text")
        return self

class VideoPresetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duration_seconds: int = Field(default=60, ge=30, le=7_200)
    captions_enabled: bool = True
    music_track: str | None = Field(default=None, max_length=200)
    visual_style: str = Field(default="cinematic-tech", min_length=1, max_length=100)
    review_mode: str = Field(default="manual", pattern=r"^(manual|auto)$")
    mcp_servers: tuple[str, ...] = ()
    aspect_ratio: str = Field(default="16:9", pattern=r"^(16:9|9:16)$")
    minimum_duration_seconds: int = Field(default=30, ge=30, le=7_200)
    maximum_duration_seconds: int = Field(default=7_200, ge=30, le=7_200)

    @model_validator(mode="after")
    def require_duration_within_preset_bounds(self) -> "VideoPresetConfig":
        if self.minimum_duration_seconds > self.maximum_duration_seconds:
            raise ValueError("preset minimum duration cannot exceed maximum duration")
        if not self.minimum_duration_seconds <= self.duration_seconds <= self.maximum_duration_seconds:
            raise ValueError("preset duration must be within its configured bounds")
        return self

class VideoGenerationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_preset: str = Field(default="default", min_length=1, max_length=100)
    presets: dict[str, VideoPresetConfig] = Field(default_factory=lambda: {"default": VideoPresetConfig()})
    music_catalog: tuple[MusicTrackConfig, ...] = ()

    @model_validator(mode="after")
    def require_default_preset(self) -> "VideoGenerationConfig":
        if self.default_preset not in self.presets:
            raise ValueError("video_generation.default_preset must name a configured preset")
        if len({track.name for track in self.music_catalog}) != len(self.music_catalog):
            raise ValueError("video_generation.music_catalog track names must be unique")
        return self

class PipelineConfig(BaseModel):
    """Safe provider selection and deterministic M7 voice settings."""

    model_config = ConfigDict(extra="forbid")

    # ``provider`` is retained only to read older configuration files. New
    # deployments select the independent content and voice adapters below.
    provider: str | None = Field(default=None, pattern=r"^(fake|codex|piper)$")
    content_provider: str = Field(default="fake", pattern=r"^(fake|fixed|codex)$")
    voice_provider: str = Field(default="fake", pattern=r"^(fake|piper|piper-http|kokoro|hybrid)$")
    fake: FakeProviderConfig = Field(default_factory=FakeProviderConfig)
    codex: CodexProviderConfig = Field(default_factory=CodexProviderConfig)
    piper: PiperProviderConfig = Field(default_factory=PiperProviderConfig)
    kokoro: KokoroProviderConfig = Field(default_factory=KokoroProviderConfig)
    voice: VoicePipelineConfig = Field(default_factory=VoicePipelineConfig)
    preview: PreviewRenderConfig = Field(default_factory=PreviewRenderConfig)
    final: FinalRenderConfig = Field(default_factory=FinalRenderConfig)
    shorts_preview: ShortsPreviewRenderConfig = Field(default_factory=ShortsPreviewRenderConfig)
    shorts_final: ShortsFinalRenderConfig = Field(default_factory=ShortsFinalRenderConfig)
    publication: PublicationPreparationConfig = Field(default_factory=PublicationPreparationConfig)
    youtube: YouTubePublishingConfig = Field(default_factory=YouTubePublishingConfig)
    verification: PublicationVerificationConfig = Field(default_factory=PublicationVerificationConfig)
    analytics: AnalyticsConfig = Field(default_factory=AnalyticsConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)
    learning: LearningConfig = Field(default_factory=LearningConfig)
    media: MediaPipelineConfig = Field(default_factory=MediaPipelineConfig)
    sources: SourceIngestionConfig = Field(default_factory=SourceIngestionConfig)
    source_clips: SourceClipConfig = Field(default_factory=SourceClipConfig)
    video_generation: VideoGenerationConfig = Field(default_factory=VideoGenerationConfig)

    @model_validator(mode="after")
    def normalize_legacy_provider(self) -> "PipelineConfig":
        """Map legacy one-provider settings without blocking Codex plus Piper."""
        if self.provider is None:
            return self
        if self.provider == "fake":
            if self.content_provider != "fake" or self.voice_provider != "fake":
                raise ValueError("legacy pipeline.provider=fake conflicts with explicit provider selection")
            return self
        expected_content = "codex" if self.provider == "codex" else "fake"
        expected_voice = "piper" if self.provider == "piper" else "fake"
        if self.content_provider != "fake" or self.voice_provider != "fake":
            if (self.content_provider, self.voice_provider) != (expected_content, expected_voice):
                raise ValueError("legacy pipeline.provider conflicts with explicit provider selection")
        else:
            self.content_provider = expected_content
            self.voice_provider = expected_voice
        return self


class WorkerConfig(BaseModel):
    """Conservative lease and retry settings for a single homelab worker."""

    model_config = ConfigDict(extra="forbid")

    max_active_jobs: int = Field(default=1, ge=1, le=1)
    lease_seconds: int = Field(default=300, ge=10, le=3600)
    heartbeat_seconds: int = Field(default=60, ge=1, le=600)
    max_attempts: int = Field(default=3, ge=1, le=20)
    retry_base_seconds: int = Field(default=30, ge=1, le=3600)
    retry_max_seconds: int = Field(default=900, ge=1, le=86_400)

    @model_validator(mode="after")
    def require_heartbeat_before_expiry(self) -> "WorkerConfig":
        if self.heartbeat_seconds >= self.lease_seconds:
            raise ValueError("worker.heartbeat_seconds must be shorter than worker.lease_seconds")
        return self


class SchedulerConfig(BaseModel):
    """Dedicated scheduler poller; it only creates normal durable jobs."""
    model_config = ConfigDict(extra="forbid")
    poll_seconds: int = Field(default=15, ge=1, le=300)
    topic_reservation_seconds: int = Field(default=600, ge=30, le=3600)


class AuthConfig(BaseModel):
    """Local dashboard authentication; no credentials belong in YAML."""

    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    session_hours: int = Field(default=12, ge=1, le=720)
    secure_cookies: bool = False
    login_attempt_limit: int = Field(default=5, ge=1, le=20)
    login_window_seconds: int = Field(default=300, ge=30, le=3600)


class Settings(BaseModel):
    """Complete non-secret TubeForge configuration."""

    model_config = ConfigDict(extra="forbid")

    app: AppConfig
    database: DatabaseConfig
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)


def load_settings(config_path: Path | None = None) -> Settings:
    """Load and validate YAML settings from a safe, explicit configuration file."""
    selected_path = config_path or Path(os.environ.get("TUBEFORGE_CONFIG", DEFAULT_CONFIG_PATH))
    try:
        raw_config: Any = yaml.safe_load(selected_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RuntimeError(f"configuration file not found: {selected_path}") from error
    except yaml.YAMLError as error:
        raise RuntimeError(f"invalid YAML configuration: {selected_path}") from error

    if not isinstance(raw_config, dict):
        raise RuntimeError(f"configuration must be a YAML mapping: {selected_path}")
    # The TTS endpoint is deployment-specific (loopback, a local service name,
    # or another private address); keep it out of the production code path.
    tts_endpoint = os.environ.get("TUBEFORGE_PIPER_SERVER_URL")
    if tts_endpoint:
        raw_config.setdefault("pipeline", {}).setdefault("piper", {})["server_url"] = tts_endpoint
    tts_listen_host = os.environ.get("TUBEFORGE_PIPER_LISTEN_HOST")
    if tts_listen_host:
        raw_config.setdefault("pipeline", {}).setdefault("piper", {})["listen_host"] = tts_listen_host
    tts_listen_port = os.environ.get("TUBEFORGE_PIPER_LISTEN_PORT")
    if tts_listen_port:
        raw_config.setdefault("pipeline", {}).setdefault("piper", {})["listen_port"] = tts_listen_port
    settings = Settings.model_validate(raw_config)
    validate_selected_provider(settings)
    return settings


def validate_selected_provider(settings: Settings) -> None:
    """Fail early for every explicitly selected external executable.

    Content and voice providers are independent. In particular, validating
    Piper must not skip Codex validation for the real LLM-to-video topology.
    """
    if settings.pipeline.voice_provider in {"piper", "piper-http", "hybrid"}:
        piper = settings.pipeline.piper
        if piper.model_path is None:
            raise RuntimeError("pipeline.piper.model_path is required when pipeline.provider is piper")
        model = _resolve_path(piper.model_path)
        if not model.is_file():
            raise RuntimeError("pipeline.piper.model_path does not exist or is not a file")
        if piper.config_path is not None and not _resolve_path(piper.config_path).is_file():
            raise RuntimeError("pipeline.piper.config_path does not exist or is not a file")
        if settings.pipeline.voice_provider != "piper-http":
            _validate_executable(piper.executable, "pipeline.piper.executable")
    if settings.pipeline.voice_provider == "piper-http" and not settings.pipeline.piper.server_url:
        raise RuntimeError("pipeline.piper.server_url is required when pipeline.voice_provider is piper-http")
    if settings.pipeline.voice_provider == "kokoro":
        kokoro = settings.pipeline.kokoro
        if kokoro.model_path is None or not _resolve_path(kokoro.model_path).is_file():
            raise RuntimeError("pipeline.kokoro.model_path must name an installed Kokoro ONNX model")
        if kokoro.voices_path is None or not _resolve_path(kokoro.voices_path).is_file():
            raise RuntimeError("pipeline.kokoro.voices_path must name an installed Kokoro voice pack")
    if settings.pipeline.content_provider == "codex":
        codex = settings.pipeline.codex
        if not codex.socket_path.is_absolute():
            raise RuntimeError("pipeline.codex.socket_path must be an absolute Unix-socket path")


def _resolve_path(value: Path) -> Path:
    return value if value.is_absolute() else REPOSITORY_ROOT / value


def _validate_executable(value: Path | str, field_name: str) -> None:
    executable = Path(value)
    if executable.parent != Path("."):
        if not _resolve_path(executable).is_file():
            raise RuntimeError(f"{field_name} does not exist or is not a file")
    elif shutil.which(str(value)) is None:
        raise RuntimeError(f"{field_name} is not on PATH; install it or set an explicit executable path")
