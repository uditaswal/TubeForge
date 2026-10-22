"""Unverified browser claims must not become publishable connections."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.models import Base


def test_account_intake_is_unconfigured_and_rejects_browser_credentials(tmp_path: Path) -> None:
    settings = Settings(
        app=AppConfig(name="TubeForge test", environment="test"),
        database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'accounts.db'}"),
    )
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    with TestClient(app) as client:
        rejected = client.post("/api/social-accounts", json={
            "platform": "youtube", "display_name": "Claimed channel",
            "external_account_id": "channel-id", "credential": {"refresh_token": "secret"},
        })
        assert rejected.status_code == 422
        assert "secret" not in rejected.text
        created = client.post("/api/social-accounts", json={
            "platform": "youtube", "display_name": "Future channel",
        })
        assert created.status_code == 201
        assert created.json()["status"] == "unconfigured"
        assert created.json()["capabilities"] == []
        accounts = client.get("/api/social-accounts").json()
        assert len(accounts) == 1
        assert accounts[0]["external_account_id"] is None
        assert accounts[0]["scopes"] == []
        assert accounts[0]["status"] == "unconfigured"
        assert app.state.runtime.accounts.credential_ciphertext(accounts[0]["id"]) is None
        dashboard = client.get("/")
        assert dashboard.status_code == 200
        assert "Publishing accounts" in dashboard.text
        assert "Connections require verified platform authorization" in dashboard.text
        assert "fetch('/api/social-accounts')" in dashboard.text
        with app.state.database.engine.begin() as connection:
            connection.execute(text("UPDATE social_accounts SET status='connected' WHERE id=:id"), {"id": accounts[0]["id"]})
        assert client.get("/api/social-accounts").json()[0]["status"] == "verification_required"


def test_named_account_profiles_and_defaults_are_durable(tmp_path: Path) -> None:
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 'profiles.db'}"), auth=AuthConfig(enabled=True))
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    with TestClient(app) as client:
        app.state.runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.get("/api/social-accounts").status_code == 401
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        csrf = {"x-csrf-token": client.cookies.get("tubeforge_csrf")}
        accounts = []
        for platform, name, category in (("youtube", "Virtual World Master", "Tech"), ("instagram", "Virtual World Master", "Tech"), ("snapchat", "History Channel", "History"), ("x", "History Channel", "History")):
            response = client.post("/api/social-accounts", json={"platform": platform, "display_name": name, "category": category, "default_description": f"More {category.lower()} videos soon."}, headers=csrf)
            assert response.status_code == 201
            assert response.json()["status"] == "unconfigured"
            accounts.append(response.json())
        assert len({item["id"] for item in accounts}) == 4
        assert client.put(f"/api/social-accounts/{accounts[0]['id']}/profile", json={"display_name": "Virtual World Master", "category": "Technology"}).status_code == 403
        updated = client.put(f"/api/social-accounts/{accounts[0]['id']}/profile", json={"display_name": "Virtual World Master", "category": "Technology", "default_description": "A clearer default."}, headers=csrf)
        assert updated.status_code == 200
        assert updated.json()["category"] == "Technology"
        assert client.put(f"/api/social-accounts/{accounts[0]['id']}/profile", json={"display_name": "", "category": "Tech", "default_description": ""}, headers=csrf).status_code == 422
        assert client.put("/api/social-accounts/missing/profile", json={"display_name": "X", "category": "Tech"}, headers=csrf).status_code == 404
        dashboard = client.get("/").text
        assert "accountProfileForm" in dashboard
        assert "Default video description" in dashboard
        assert "tubeforge:accounts-changed" in dashboard
    reopened = create_app(settings)
    with TestClient(reopened) as client:
        assert client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"}).status_code == 200
        saved = client.get("/api/social-accounts").json()
        assert len(saved) == 4
        assert next(item for item in saved if item["id"] == accounts[0]["id"])["default_description"] == "A clearer default."
