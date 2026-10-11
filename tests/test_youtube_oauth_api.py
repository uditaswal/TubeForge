"""Signed-in channel connection requires remote discovery and exact confirmation."""
from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.security.google_oauth import GoogleAccountOAuth, VerifiedGoogleAccount


def test_youtube_connection_requires_identity_confirmation(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "oauth-api.db"
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{db_path}"])
    command.upgrade(config, "head")
    monkeypatch.setenv("TUBEFORGE_ACCOUNT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("TUBEFORGE_GOOGLE_OAUTH_CLIENT_ID", "client.apps.googleusercontent.com")
    monkeypatch.setenv("TUBEFORGE_GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("TUBEFORGE_GOOGLE_OAUTH_REDIRECT_URI", "https://studio.example/oauth/youtube/callback")
    settings = Settings(app=AppConfig(name="test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{db_path}"), auth=AuthConfig(enabled=True))
    with TestClient(create_app(settings)) as client:
        runtime = client.app.state.runtime
        runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.post("/api/oauth/youtube/start", json={}).status_code == 401
        client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"})
        csrf = client.cookies.get("tubeforge_csrf")
        assert client.get("/api/oauth/youtube/status").json()["configured"] is True
        started = client.post("/api/oauth/youtube/start", json={}, headers={"x-csrf-token": csrf})
        assert started.status_code == 200
        authorization_url = started.json()["authorization_url"]
        assert urlsplit(authorization_url).hostname == "accounts.google.com"
        query = parse_qs(urlsplit(authorization_url).query)
        assert query["code_challenge"] and query["state"]
        state = query["state"][0]
        verified = VerifiedGoogleAccount("UC-verified", "Verified Shorts", {"refresh_token": "secret-refresh"}, ("youtube.upload",), datetime.now(UTC))
        with patch.object(GoogleAccountOAuth, "exchange_and_discover", return_value=verified):
            assert client.get("/oauth/youtube/callback", params={"state": "wrong", "code": "code"}, follow_redirects=False).status_code == 400
            callback = client.get("/oauth/youtube/callback", params={"state": state, "code": "code"}, follow_redirects=False)
        assert callback.status_code == 200
        assert "UC-verified" in callback.text
        assert "secret-refresh" not in callback.text
        assert client.get("/api/social-accounts").json() == []
        confirmed = client.post("/api/oauth/youtube/confirm", json={"state": state}, headers={"x-csrf-token": csrf})
        assert confirmed.status_code == 200
        assert confirmed.json()["external_account_id"] == "UC-verified"
        assert confirmed.json()["status"] == "connected"
        assert client.post("/api/oauth/youtube/confirm", json={"state": state}, headers={"x-csrf-token": csrf}).status_code == 409
        ciphertext = runtime.accounts.credential_ciphertext(confirmed.json()["id"])
        assert ciphertext and "secret-refresh" not in ciphertext
        assert runtime.token_cipher.decrypt(ciphertext)["refresh_token"] == "secret-refresh"
        reconnect = client.post("/api/oauth/youtube/start", json={"account_id": confirmed.json()["id"]}, headers={"x-csrf-token": csrf})
        assert reconnect.status_code == 200
        reconnect_state = parse_qs(urlsplit(reconnect.json()["authorization_url"]).query)["state"][0]
        different = VerifiedGoogleAccount("UC-other", "Other channel", {"refresh_token": "other-secret"}, ("youtube.upload",), datetime.now(UTC))
        with patch.object(GoogleAccountOAuth, "exchange_and_discover", return_value=different):
            rejected = client.get("/oauth/youtube/callback", params={"state": reconnect_state, "code": "code"}, follow_redirects=False)
        assert rejected.status_code == 400
        assert client.get("/api/social-accounts").json()[0]["external_account_id"] == "UC-verified"
        assert runtime.token_cipher.decrypt(runtime.accounts.credential_ciphertext(confirmed.json()["id"]))["refresh_token"] == "secret-refresh"
