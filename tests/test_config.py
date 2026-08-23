from pathlib import Path

import pytest
from pydantic import ValidationError

from tubeforge.core.config import Settings, load_settings


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

def test_media_provider_defaults_to_fake_and_wikimedia_is_explicit() -> None:
    from tubeforge.core.config import FakeProviderConfig, MediaPipelineConfig
    from tubeforge.providers.fake import FakeMediaProvider
    from tubeforge.providers.media.factory import create_media_provider
    from tubeforge.providers.media.wikimedia import WikimediaCommonsProvider
    assert isinstance(create_media_provider(MediaPipelineConfig(), FakeProviderConfig()), FakeMediaProvider)
    assert isinstance(create_media_provider(MediaPipelineConfig(provider="wikimedia"), FakeProviderConfig()), WikimediaCommonsProvider)

def test_default_yaml_uses_safe_fake_media_policy() -> None:
    settings = load_settings()
    assert settings.pipeline.media.provider == "fake"
    assert settings.pipeline.media.max_redirects == 0
    assert not settings.pipeline.sources.enabled


def test_source_ingestion_needs_explicit_hosts() -> None:
    with pytest.raises(ValidationError, match="source ingestion requires"):
        Settings.model_validate({
            "app": {"name": "Test", "environment": "test"},
            "database": {"url": "sqlite:///./test.db"},
            "pipeline": {"sources": {"enabled": True}},
        })
