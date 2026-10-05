from pathlib import Path

import pytest
from pydantic import ValidationError

from tubeforge.core.config import Settings, VoicePipelineConfig, load_settings


def test_loads_fake_yaml_configuration(tmp_path: Path) -> None:
    config_file = tmp_path / "fake.yaml"
    config_file.write_text(
        """app:
  name: Test TubeForge
  environment: test
  bind_host: 127.0.0.1
  port: 9090
database:
  url: sqlite:///./test.db
  busy_timeout_ms: 1234
""",
        encoding="utf-8",
    )

    settings = load_settings(config_file)

    assert settings.app.environment == "test"
    assert settings.app.port == 9090
    assert settings.database.busy_timeout_ms == 1234
    assert settings.pipeline.content_provider == "fake"
    assert settings.pipeline.voice_provider == "fake"


def test_configuration_rejects_non_sqlite_database() -> None:
    with pytest.raises(ValidationError, match="sqlite"):
        Settings.model_validate(
            {
                "app": {"name": "Test", "environment": "test"},
                "database": {"url": "postgresql://example.invalid/tubeforge"},
            }
        )

def test_media_provider_supports_local_generated_stock_and_hybrid_routing() -> None:
    from tubeforge.core.config import FakeProviderConfig, MediaPipelineConfig
    from tubeforge.providers.fake import FakeMediaProvider
    from tubeforge.providers.media.factory import create_media_provider
    from tubeforge.providers.media.router import VisualMediaProvider
    from tubeforge.providers.media.wikimedia import WikimediaCommonsProvider
    assert isinstance(create_media_provider(MediaPipelineConfig(), FakeProviderConfig()), FakeMediaProvider)
    assert isinstance(create_media_provider(MediaPipelineConfig(provider="wikimedia"), FakeProviderConfig()), WikimediaCommonsProvider)
    assert isinstance(create_media_provider(MediaPipelineConfig(provider="hybrid"), FakeProviderConfig()), VisualMediaProvider)

def test_default_yaml_uses_safe_per_job_visual_media_policy() -> None:
    settings = load_settings()
    assert settings.pipeline.media.provider == "hybrid"
    assert settings.pipeline.media.max_redirects == 0
    assert not settings.pipeline.sources.enabled


def test_default_voice_duration_tolerance_accepts_real_local_pacing() -> None:
    config = VoicePipelineConfig()
    assert config.target_duration_tolerance_ratio == 0.30
    assert 60 * (1 + config.target_duration_tolerance_ratio) >= 78


def test_source_ingestion_needs_explicit_hosts() -> None:
    with pytest.raises(ValidationError, match="source ingestion requires"):
        Settings.model_validate({
            "app": {"name": "Test", "environment": "test"},
            "database": {"url": "sqlite:///./test.db"},
            "pipeline": {"sources": {"enabled": True}},
        })


def test_codex_and_piper_selection_requires_an_absolute_socket_path(tmp_path: Path) -> None:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    piper = tmp_path / "piper"
    piper.write_text("#!/bin/sh\n", encoding="utf-8")
    config = tmp_path / "combined.yaml"
    config.write_text(
        "\n".join(
            (
                "app:",
                "  name: TubeForge",
                "  environment: test",
                "database:",
                "  url: sqlite:///test.db",
                "pipeline:",
                "  content_provider: codex",
                "  voice_provider: piper",
                "  codex:",
                "    socket_path: relative-codex.sock",
                "  piper:",
                f"    executable: {piper}",
                f"    model_path: {model}",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="pipeline.codex.socket_path"):
        load_settings(config)
