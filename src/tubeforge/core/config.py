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


class PipelineConfig(BaseModel):
    """Safe M4 orchestration settings."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(default="fake", pattern=r"^(fake|codex)$")
    fake: FakeProviderConfig = Field(default_factory=FakeProviderConfig)
    codex: CodexProviderConfig = Field(default_factory=CodexProviderConfig)


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
    """Fail early with a non-secret explanation for an enabled Codex adapter."""
    if settings.pipeline.provider != "codex":
        return
    codex = settings.pipeline.codex
    executable = Path(codex.executable)
    if executable.parent != Path("."):
        if not executable.is_file():
            raise RuntimeError(f"pipeline.codex.executable does not exist or is not a file: {executable}")
    elif shutil.which(codex.executable) is None:
        raise RuntimeError(
            "pipeline.codex.executable is not on PATH; install Codex CLI or set an explicit executable path"
        )
