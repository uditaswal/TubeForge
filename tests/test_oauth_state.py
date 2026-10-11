"""OAuth handshakes survive restarts and reject replay or cross-session use."""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import text

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base
from tubeforge.db.session import create_database
from tubeforge.security.oauth_state import OAuthStateStore
from tubeforge.security.secrets import TokenCipher


def test_oauth_state_is_durable_bound_and_single_use(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'oauth.db'}"))
    Base.metadata.create_all(database.engine)
    try:
        cipher = TokenCipher(Fernet.generate_key().decode())
        store = OAuthStateStore(database.session_factory, cipher)
        now = datetime.now(UTC)
        state = store.begin(platform="youtube", account_id="account-1", session_id="studio-1", redirect_uri="https://studio.example/callback", code_verifier="pkce-secret", now=now)
        with database.engine.connect() as connection:
            stored = connection.execute(text("SELECT verifier_ciphertext FROM oauth_connections")).scalar_one()
        assert "pkce-secret" not in stored
        restarted = OAuthStateStore(database.session_factory, cipher)
        assert restarted.consume(state, platform="youtube", session_id="other", now=now) is None
        assert restarted.consume(state, platform="instagram", session_id="studio-1", now=now) is None
        connection = restarted.consume(state, platform="youtube", session_id="studio-1", now=now)
        assert connection is not None
        assert connection.account_id == "account-1"
        assert connection.code_verifier == "pkce-secret"
        assert restarted.consume(state, platform="youtube", session_id="studio-1", now=now) is None
        # Reconnection to a missing local account must be rejected before
        # a credential is staged or marked connected.
        with pytest.raises(ValueError, match="identity does not match"):
            restarted.stage_verified(state, session_id="studio-1", external_id="UC-one", label="One", credential={"refresh_token": "secret"}, scopes=("upload",), expires_at=None, now=now)
        fresh = store.begin(platform="youtube", account_id=None, session_id="studio-1", redirect_uri="https://studio.example/callback", now=now)
        assert restarted.consume(fresh, platform="youtube", session_id="studio-1", now=now)
        candidate = restarted.stage_verified(fresh, session_id="studio-1", external_id="UC-one", label="My channel", credential={"refresh_token": "secret"}, scopes=("upload",), expires_at=None, now=now)
        assert candidate.external_id == "UC-one"
        with database.engine.connect() as db_connection:
            assert db_connection.execute(text("SELECT COUNT(*) FROM social_accounts WHERE status='connected'")).scalar_one() == 0
        account_id = restarted.confirm(fresh, session_id="studio-1", now=now)
        assert account_id
        with pytest.raises(ValueError, match="unavailable"):
            restarted.confirm(fresh, session_id="studio-1", now=now)
        with database.engine.connect() as db_connection:
            row = db_connection.execute(text("SELECT external_account_id, status, credential_ciphertext FROM social_accounts WHERE id=:id"), {"id": account_id}).one()
            pending_ciphertext = db_connection.execute(text("SELECT candidate_credential_ciphertext FROM oauth_connections WHERE state_hash=:hash"), {"hash": hashlib.sha256(fresh.encode()).hexdigest()}).scalar_one()
        assert row[0:2] == ("UC-one", "connected") and "secret" not in row[2]
        assert pending_ciphertext is None
        expired = store.begin(platform="youtube", account_id=None, session_id="studio-1", redirect_uri="https://studio.example/callback", now=now)
        assert restarted.consume(expired, platform="youtube", session_id="studio-1", now=now + timedelta(minutes=11)) is None
        with pytest.raises(ValueError, match="HTTPS"):
            store.begin(platform="youtube", account_id=None, session_id="studio-1", redirect_uri="http://studio.example/callback")
    finally:
        database.dispose()
