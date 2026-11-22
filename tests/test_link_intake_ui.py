"""The Studio page has one link front door wired to the existing intake APIs."""
from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.models import Base


def test_studio_page_offers_link_intake(tmp_path) -> None:
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'link.db'}"), auth=AuthConfig(enabled=True))
    settings.pipeline.voice.artifact_root = tmp_path / "artifacts"
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    with TestClient(app) as client:
        app.state.runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        page = client.get("/").text
        for needle in ("Start from a link", "linkClip", "linkShort", "linkLong", "/api/source-clips", "/api/reference-intakes"):
            assert needle in page
