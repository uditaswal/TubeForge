"""Cross-worker token refresh stays encrypted, fenced, and account scoped."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
import httpx
import pytest

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base, SocialAccountRecord
from tubeforge.db.session import create_database
from tubeforge.security.account_credentials import AccountCredentialManager, CredentialBusy, CredentialReconnectRequired, GoogleCredentialRefresher, RefreshedCredential
from tubeforge.security.secrets import TokenCipher


def _account(database, cipher: TokenCipher, now: datetime) -> None:
    with database.session_factory.begin() as session:
        session.add(SocialAccountRecord(id="yt", platform="youtube", display_name="Channel", external_account_id="UC-real", auth_type="oauth", credential_ciphertext=cipher.encrypt({"token": "old", "refresh_token": "refresh"}), scopes_json="[]", token_expires_at=now - timedelta(minutes=1), status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))


def test_refresh_is_fenced_and_saved_encrypted_once(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'tokens.db'}"))
    Base.metadata.create_all(database.engine)
    cipher = TokenCipher(Fernet.generate_key().decode())
    now = datetime.now(UTC)
    _account(database, cipher, now)
    calls = 0
    manager = None

    def refresh(old):
        nonlocal calls
        calls += 1
        with pytest.raises(CredentialBusy):
            manager.resolve("yt", "other-worker", now=now)
        return RefreshedCredential({**old, "token": "new"}, now + timedelta(hours=1))

    manager = AccountCredentialManager(database.session_factory, cipher, {"youtube": refresh})
    try:
        assert manager.resolve("yt", "worker", now=now)["token"] == "new"
        assert manager.resolve("yt", "other-worker", now=now)["token"] == "new"
        assert calls == 1
        with database.session_factory() as session:
            row = session.get(SocialAccountRecord, "yt")
            assert "new" not in row.credential_ciphertext
            assert row.credential_refresh_owner is row.credential_refresh_fence is row.credential_refresh_lease_expires_at is None
            assert cipher.decrypt(row.credential_ciphertext)["token"] == "new"
    finally:
        database.dispose()


def test_revoked_refresh_marks_reconnect_and_reconnect_fences_old_write(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'revoked.db'}"))
    Base.metadata.create_all(database.engine)
    cipher = TokenCipher(Fernet.generate_key().decode())
    now = datetime.now(UTC)
    _account(database, cipher, now)

    def revoked(_):
        raise CredentialReconnectRequired("revoked")

    manager = AccountCredentialManager(database.session_factory, cipher, {"youtube": revoked})
    try:
        with pytest.raises(CredentialReconnectRequired):
            manager.resolve("yt", "worker", now=now)
        with database.session_factory() as session:
            assert session.get(SocialAccountRecord, "yt").status == "reconnect_required"
        with database.session_factory.begin() as session:
            row = session.get(SocialAccountRecord, "yt")
            row.status = "connected"
            row.credential_ciphertext = cipher.encrypt({"token": "reconnected", "refresh_token": "fresh"})

        def racing_refresh(old):
            with database.session_factory.begin() as session:
                row = session.get(SocialAccountRecord, "yt")
                row.credential_ciphertext = cipher.encrypt({"token": "newer-connection", "refresh_token": "fresh"})
                row.credential_refresh_owner = row.credential_refresh_fence = row.credential_refresh_lease_expires_at = None
            return RefreshedCredential({**old, "token": "stale-refresh"}, now + timedelta(hours=1))

        manager = AccountCredentialManager(database.session_factory, cipher, {"youtube": racing_refresh})
        with pytest.raises(CredentialBusy):
            manager.resolve("yt", "worker", now=now)
        with database.session_factory() as session:
            row = session.get(SocialAccountRecord, "yt")
            assert cipher.decrypt(row.credential_ciphertext)["token"] == "newer-connection"
    finally:
        database.dispose()


def test_google_refresh_uses_official_token_endpoint_and_handles_revocation() -> None:
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.method == "POST" and str(request.url) == "https://oauth2.googleapis.com/token"
        assert b"grant_type=refresh_token" in request.content
        if calls == 1:
            return httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600})
        return httpx.Response(400, json={"error": "invalid_grant"})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    refresher = GoogleCredentialRefresher(client)
    credential = {"token_uri": "https://oauth2.googleapis.com/token", "client_id": "client", "client_secret": "secret", "refresh_token": "refresh", "token": "old"}
    try:
        new = refresher(credential)
        assert new.value["token"] == "new-access" and new.value["refresh_token"] == "refresh"
        with pytest.raises(CredentialReconnectRequired):
            refresher(credential)
        assert calls == 2
    finally:
        client.close()
