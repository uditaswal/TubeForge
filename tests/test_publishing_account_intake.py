"""Unverified browser claims must not become publishable connections."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, DatabaseConfig, Settings
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
