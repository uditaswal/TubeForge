"""Validated, non-secret application configuration."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPOSITORY_ROOT / "config" / "default.yaml"


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
    provider: str = Field(default="fake", pattern=r"^(fake|wikimedia)$")
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

class CodexProviderConfig(BaseModel):
    """Non-secret limits for the opt-in Codex CLI content adapter."""

    model_config = ConfigDict(extra="forbid")

    executable: str = Field(default="codex", min_length=1, max_length=4_096)
    model: str = Field(default="gpt-5.2-codex", min_length=1, max_length=200)
    timeout_seconds: int = Field(default=900, ge=1, le=7_200)
    max_output_bytes: int = Field(default=2_000_000, ge=1_024, le=20_000_000)
    max_diagnostic_bytes: int = Field(default=8_192, ge=256, le=65_536)
    reservation_seconds: int = Field(default=1_200, ge=10, le=14_400)
    repair_attempt_limit: int = Field(default=0, ge=0, le=5)
    prompt_template_version: str = Field(default="m6-content-v1", min_length=1, max_length=100)
    max_prompt_chars: int = Field(default=60_000, ge=1_000, le=200_000)

    @field_validator("executable", "model", "prompt_template_version")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value


class PiperProviderConfig(BaseModel):
    """Opt-in local Piper settings; paths are resolved from the repository root."""

    model_config = ConfigDict(extra="forbid")

    executable: Path | str = "piper"
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

class RenderProfile(BaseModel):
    """Bounded deterministic profile for the low-resolution review render."""

    model_config = ConfigDict(extra="forbid")
    width: int = Field(default=854, ge=160, le=3840)
    height: int = Field(default=480, ge=90, le=2160)
    fps: int = Field(default=30, ge=1, le=60)
    pixel_format: str = Field(default="yuv420p", pattern=r"^[A-Za-z0-9_]+$")
    video_codec: str = Field(default="libx264", pattern=r"^[A-Za-z0-9_.-]+$")
    audio_codec: str = Field(default="aac", pattern=r"^[A-Za-z0-9_.-]+$")
    audio_bitrate: str = Field(default="128k", pattern=r"^[0-9]+[kKmM]$")
    threads: int = Field(default=1, ge=1, le=4)
    timeout_seconds: int = Field(default=900, ge=1, le=7200)
    ffprobe_timeout_seconds: int = Field(default=30, ge=1, le=300)
    minimum_free_bytes: int = Field(default=250_000_000, ge=1)
    sync_tolerance_seconds: float = Field(default=0.25, ge=0.01, le=2)
    caption_font_size: int = Field(default=26, ge=12, le=96)
    renderer_version: str = Field(default="m9-preview-v1", min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_16_by_9(self) -> "RenderProfile":
        if abs(self.width / self.height - 16 / 9) > 0.02:
            raise ValueError("preview resolution must be 16:9")
        return self



class PreviewRenderConfig(RenderProfile):
    """Bounded deterministic profile for the low-resolution review render."""


class FinalRenderConfig(RenderProfile):
    """Bounded deterministic profile for final source rendering."""

    width: int = Field(default=1920, ge=160, le=3840)
    height: int = Field(default=1080, ge=90, le=2160)
    audio_bitrate: str = "160k"
    renderer_version: str = "m10-final-v1"

class PipelineConfig(BaseModel):
    """Safe provider selection and deterministic M7 voice settings."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="fake", pattern=r"^(fake|codex|piper)$")
    fake: FakeProviderConfig = Field(default_factory=FakeProviderConfig)
    codex: CodexProviderConfig = Field(default_factory=CodexProviderConfig)
    piper: PiperProviderConfig = Field(default_factory=PiperProviderConfig)
    voice: VoicePipelineConfig = Field(default_factory=VoicePipelineConfig)
    preview: PreviewRenderConfig = Field(default_factory=PreviewRenderConfig)
    final: FinalRenderConfig = Field(default_factory=FinalRenderConfig)
    media: MediaPipelineConfig = Field(default_factory=MediaPipelineConfig)


class WorkerConfig(BaseModel):
    """Conservative lease and retry settings for a single homelab worker."""

    model_config = ConfigDict(extra="forbid")

    max_active_jobs: int = Field(default=1, ge=1, le=1)
    lease_seconds: int = Field(default=300, ge=10, le=3600)
    max_attempts: int = Field(default=3, ge=1, le=20)
    retry_base_seconds: int = Field(default=30, ge=1, le=3600)
    retry_max_seconds: int = Field(default=900, ge=1, le=86_400)


class Settings(BaseModel):
    """Complete non-secret TubeForge configuration."""

    model_config = ConfigDict(extra="forbid")

    app: AppConfig
    database: DatabaseConfig
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)


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
    settings = Settings.model_validate(raw_config)
    validate_selected_provider(settings)
    return settings


def validate_selected_provider(settings: Settings) -> None:
    """Fail early only for the explicitly selected external executable."""
    if settings.pipeline.provider == "piper":
        piper = settings.pipeline.piper
        if piper.model_path is None:
            raise RuntimeError("pipeline.piper.model_path is required when pipeline.provider is piper")
        model = _resolve_path(piper.model_path)
        if not model.is_file():
            raise RuntimeError("pipeline.piper.model_path does not exist or is not a file")
        if piper.config_path is not None and not _resolve_path(piper.config_path).is_file():
            raise RuntimeError("pipeline.piper.config_path does not exist or is not a file")
        _validate_executable(piper.executable, "pipeline.piper.executable")
        return
    if settings.pipeline.provider != "codex":
        return
    codex = settings.pipeline.codex
    _validate_executable(codex.executable, "pipeline.codex.executable")


def _resolve_path(value: Path) -> Path:
    return value if value.is_absolute() else REPOSITORY_ROOT / value


def _validate_executable(value: Path | str, field_name: str) -> None:
    executable = Path(value)
    if executable.parent != Path("."):
        if not _resolve_path(executable).is_file():
            raise RuntimeError(f"{field_name} does not exist or is not a file")
    elif shutil.which(str(value)) is None:
        raise RuntimeError(f"{field_name} is not on PATH; install it or set an explicit executable path")
