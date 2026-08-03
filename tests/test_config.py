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
    assert settings.pipeline.provider == "fake"


def test_configuration_rejects_non_sqlite_database() -> None:
    with pytest.raises(ValidationError, match="sqlite"):
        Settings.model_validate(
            {
                "app": {"name": "Test", "environment": "test"},
                "database": {"url": "postgresql://example.invalid/tubeforge"},
            }
        )
