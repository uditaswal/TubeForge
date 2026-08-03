from pathlib import Path

from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, DatabaseConfig, Settings


def test_health_endpoint_checks_the_database(tmp_path: Path) -> None:
    settings = Settings(
        app=AppConfig(name="TubeForge test", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'health.db'}"),
    )

    with TestClient(create_app(settings)) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
