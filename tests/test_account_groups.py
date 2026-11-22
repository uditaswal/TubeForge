"""One account (person/brand) owns one connection per platform."""
from pathlib import Path

from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.models import Base


def _client(tmp_path: Path):
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'groups.db'}"), auth=AuthConfig(enabled=True))
    settings.pipeline.voice.artifact_root = tmp_path / "artifacts"
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    return app


def test_account_owns_one_connection_per_platform(tmp_path: Path) -> None:
    app = _client(tmp_path)
    with TestClient(app) as client:
        app.state.runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        csrf = {"x-csrf-token": client.cookies.get("tubeforge_csrf")}
        group = client.post("/api/account-groups", json={"name": "Example Creator", "category": "general"}, headers=csrf)
        assert group.status_code == 201 and group.json()["connections"] == []
        gid = group.json()["id"]
        for platform in ("youtube", "instagram"):
            assert client.post(f"/api/account-groups/{gid}/connections", json={"platform": platform}, headers=csrf).status_code == 201
        duplicate = client.post(f"/api/account-groups/{gid}/connections", json={"platform": "youtube"}, headers=csrf)
        assert duplicate.status_code == 409
        listed = client.get("/api/account-groups").json()
        assert [g["name"] for g in listed] == ["Example Creator"]
        assert sorted(c["platform"] for c in listed[0]["connections"]) == ["instagram", "youtube"]
        assert all(c["status"] == "unconfigured" for c in listed[0]["connections"])
        assert client.put(f"/api/account-groups/{gid}", json={"name": "Example C.", "category": "tech"}, headers=csrf).json()["name"] == "Example C."
        assert client.put(f"/api/account-groups/{gid}/default", headers=csrf).status_code == 200
        assert client.get("/api/account-groups").json()[0]["is_default"] is True
        assert client.post("/api/account-groups/missing/connections", json={"platform": "x"}, headers=csrf).status_code == 404


def test_legacy_profile_and_orphan_connections_appear_as_accounts(tmp_path: Path) -> None:
    app = _client(tmp_path)
    with TestClient(app) as client:
        app.state.runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"})
        csrf = {"x-csrf-token": client.cookies.get("tubeforge_csrf")}
        assert client.post("/api/social-accounts", json={"platform": "youtube", "display_name": "Second Channel", "category": "Tech"}, headers=csrf).status_code == 201
        orphan = app.state.runtime.accounts.create("orphan1", platform="youtube", display_name="Channel X", external_account_id=None, auth_type="oauth", credential_ciphertext=None, scopes=(), capabilities=())
        names = sorted(g["name"] for g in client.get("/api/account-groups").json())
        assert names == ["Channel X", "Second Channel"] and orphan.group_id is None
