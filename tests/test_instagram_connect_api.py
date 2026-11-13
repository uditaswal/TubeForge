"""Signed-in Instagram connection needs exact identity confirmation."""
from __future__ import annotations

from argparse import Namespace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.security.instagram_oauth import InstagramAccountOAuth, VerifiedInstagramAccount


def _client(tmp_path: Path, monkeypatch, configured: bool = True) -> TestClient:
    db_path = tmp_path / "ig.db"
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.cmd_opts = Namespace(x=[f"database_url=sqlite:///{db_path}"])
    command.upgrade(config, "head")
    monkeypatch.setenv("TUBEFORGE_ACCOUNT_ENCRYPTION_KEY", Fernet.generate_key().decode())
    for name, value in (("TUBEFORGE_INSTAGRAM_APP_ID", "app"), ("TUBEFORGE_INSTAGRAM_APP_SECRET", "secret"), ("TUBEFORGE_INSTAGRAM_OAUTH_REDIRECT_URI", "https://localhost:62065/oauth/instagram/callback")):
        if configured:
            monkeypatch.setenv(name, value)
        else:
            monkeypatch.delenv(name, raising=False)
    settings = Settings(app=AppConfig(name="test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{db_path}"), auth=AuthConfig(enabled=True))
    return TestClient(create_app(settings))


def test_unconfigured_reports_truthfully(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch, configured=False) as client:
        client.app.state.runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"})
        status = client.get("/api/oauth/instagram/status").json()
        assert status["configured"] is False and status["reason"]


def test_connect_requires_confirmation_and_rejects_other_identity_on_reconnect(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, monkeypatch) as client:
        runtime = client.app.state.runtime
        runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        assert client.post("/api/oauth/instagram/start", json={}).status_code == 401
        client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"})
        csrf = client.cookies.get("tubeforge_csrf")
        assert client.get("/api/oauth/instagram/status").json()["configured"] is True
        started = client.post("/api/oauth/instagram/start", json={}, headers={"x-csrf-token": csrf})
        url = started.json()["authorization_url"]
        assert urlsplit(url).hostname == "www.instagram.com"
        state = parse_qs(urlsplit(url).query)["state"][0]
        verified = VerifiedInstagramAccount("1784", "@shorts", {"token": "secret-long", "token_type": "instagram_long_lived"}, ("instagram_business_basic",), datetime.now(UTC) + timedelta(days=60))
        with patch.object(InstagramAccountOAuth, "exchange_and_discover", return_value=verified):
            assert client.get("/oauth/instagram/callback", params={"state": "wrong", "code": "c"}).status_code == 400
            callback = client.get("/oauth/instagram/callback", params={"state": state, "code": "c#_"})
        assert callback.status_code == 200 and "@shorts" in callback.text and "secret-long" not in callback.text
        assert client.get("/api/social-accounts").json() == []
        confirmed = client.post("/api/oauth/instagram/confirm", json={"state": state}, headers={"x-csrf-token": csrf})
        assert confirmed.status_code == 200 and confirmed.json()["external_account_id"] == "1784"
        assert client.post("/api/oauth/instagram/confirm", json={"state": state}, headers={"x-csrf-token": csrf}).status_code == 409
        sealed = runtime.accounts.credential_ciphertext(confirmed.json()["id"])
        assert "secret-long" not in sealed and runtime.token_cipher.decrypt(sealed)["token"] == "secret-long"
        assert client.post("/api/oauth/instagram/start", json={"account_id": "nope"}, headers={"x-csrf-token": csrf}).status_code == 404
        again = client.post("/api/oauth/instagram/start", json={"account_id": confirmed.json()["id"]}, headers={"x-csrf-token": csrf})
        second = parse_qs(urlsplit(again.json()["authorization_url"]).query)["state"][0]
        other = VerifiedInstagramAccount("9999", "@other", {"token": "x"}, ("instagram_business_basic",), datetime.now(UTC) + timedelta(days=60))
        with patch.object(InstagramAccountOAuth, "exchange_and_discover", return_value=other):
            assert client.get("/oauth/instagram/callback", params={"state": second, "code": "c"}).status_code == 400
        assert client.get("/api/social-accounts").json()[0]["external_account_id"] == "1784"
