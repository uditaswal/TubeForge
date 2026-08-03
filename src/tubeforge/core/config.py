"""Validated, non-secret application configuration."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class Settings(BaseModel):
    """Complete non-secret TubeForge configuration."""

    model_config = ConfigDict(extra="forbid")

    app: AppConfig
    database: DatabaseConfig


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
    return Settings.model_validate(raw_config)
