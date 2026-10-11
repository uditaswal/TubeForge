"""Durable, session-bound OAuth state for publishing account connections."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import secrets
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.db.models import OAuthConnectionRecord, SocialAccountRecord
from tubeforge.security.secrets import TokenCipher


@dataclass(frozen=True, slots=True)
class PendingConnection:
    platform: str
    account_id: str | None
    redirect_uri: str
    code_verifier: str | None


@dataclass(frozen=True, slots=True)
class ConnectionCandidate:
    platform: str
    external_id: str
    label: str
    account_id: str | None


class OAuthStateStore:
    def __init__(self, session_factory: sessionmaker[Session], cipher: TokenCipher) -> None:
        self.session_factory = session_factory
        self.cipher = cipher

    def begin(
        self,
        *,
        platform: str,
        account_id: str | None,
        session_id: str,
        redirect_uri: str,
        code_verifier: str | None = None,
        now: datetime | None = None,
    ) -> str:
        parsed = urlsplit(redirect_uri)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("OAuth callback must be a configured HTTPS URL")
        if platform not in {"youtube", "instagram"} or not session_id:
            raise ValueError("invalid OAuth connection context")
        now = now or datetime.now(UTC)
        state = secrets.token_urlsafe(40)
        verifier = self.cipher.encrypt({"code_verifier": code_verifier}) if code_verifier else None
        with self.session_factory.begin() as session:
            session.execute(delete(OAuthConnectionRecord).where(OAuthConnectionRecord.expires_at <= now))
            session.add(OAuthConnectionRecord(
                state_hash=_state_hash(state), platform=platform, account_id=account_id,
                session_id=session_id, verifier_ciphertext=verifier, redirect_uri=redirect_uri,
                created_at=now, expires_at=now + timedelta(minutes=10), consumed_at=None,
            ))
        return state

    def consume(
        self, state: str, *, platform: str, session_id: str, now: datetime | None = None,
    ) -> PendingConnection | None:
        now = now or datetime.now(UTC)
        if not state or len(state) > 200:
            return None
        with self.session_factory.begin() as session:
            row = session.execute(
                update(OAuthConnectionRecord)
                .where(
                    OAuthConnectionRecord.state_hash == _state_hash(state),
                    OAuthConnectionRecord.platform == platform,
                    OAuthConnectionRecord.session_id == session_id,
                    OAuthConnectionRecord.consumed_at.is_(None),
                    OAuthConnectionRecord.expires_at > now,
                )
                .values(consumed_at=now)
                .returning(
                    OAuthConnectionRecord.platform, OAuthConnectionRecord.account_id,
                    OAuthConnectionRecord.redirect_uri, OAuthConnectionRecord.verifier_ciphertext,
                )
            ).first()
        if row is None:
            return None
        verifier = self.cipher.decrypt(row.verifier_ciphertext).get("code_verifier") if row.verifier_ciphertext else None
        if verifier is not None and not isinstance(verifier, str):
            raise ValueError("OAuth verifier is invalid")
        return PendingConnection(row.platform, row.account_id, row.redirect_uri, verifier)

    def stage_verified(
        self, state: str, *, session_id: str, external_id: str, label: str,
        credential: dict[str, object], scopes: tuple[str, ...], expires_at: datetime | None,
        now: datetime | None = None,
    ) -> ConnectionCandidate:
        now = now or datetime.now(UTC)
        if not external_id or not label or not credential:
            raise ValueError("verified account identity and credential are required")
        with self.session_factory.begin() as session:
            row = session.get(OAuthConnectionRecord, _state_hash(state))
            if row is None or row.session_id != session_id or row.consumed_at is None or _as_utc(row.expires_at) <= now or row.candidate_external_id is not None:
                raise ValueError("OAuth attempt is not ready for identity confirmation")
            if row.account_id:
                account = session.get(SocialAccountRecord, row.account_id)
                if account is None or account.platform != row.platform or (account.external_account_id and account.external_account_id != external_id):
                    raise ValueError("reconnected account identity does not match")
            row.candidate_external_id = external_id
            row.candidate_label = label[:200]
            row.candidate_credential_ciphertext = self.cipher.encrypt(credential)
            row.candidate_scopes_json = json.dumps(scopes)
            row.candidate_token_expires_at = expires_at
            return ConnectionCandidate(row.platform, external_id, row.candidate_label, row.account_id)

    def confirm(self, state: str, *, session_id: str, now: datetime | None = None) -> str:
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = session.get(OAuthConnectionRecord, _state_hash(state))
            if row is None or row.session_id != session_id or row.consumed_at is None or row.confirmed_at is not None or _as_utc(row.expires_at) <= now or not row.candidate_external_id or not row.candidate_credential_ciphertext:
                raise ValueError("OAuth account confirmation is unavailable or expired")
            duplicate = session.scalar(select(SocialAccountRecord).where(
                SocialAccountRecord.platform == row.platform,
                SocialAccountRecord.external_account_id == row.candidate_external_id,
            ))
            if duplicate is not None and duplicate.id != row.account_id:
                raise ValueError("this remote account is already connected")
            account = session.get(SocialAccountRecord, row.account_id) if row.account_id else None
            if row.account_id and (account is None or account.platform != row.platform or (account.external_account_id and account.external_account_id != row.candidate_external_id)):
                raise ValueError("reconnected account identity does not match")
            if account is None:
                account = SocialAccountRecord(id=uuid4().hex, platform=row.platform, display_name=row.candidate_label or row.candidate_external_id, external_account_id=row.candidate_external_id, auth_type="oauth", credential_ciphertext=row.candidate_credential_ciphertext, scopes_json=row.candidate_scopes_json or "[]", token_expires_at=row.candidate_token_expires_at, status="connected", capabilities_json=json.dumps(("upload_video",)), is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now)
                session.add(account)
            else:
                account.display_name = row.candidate_label or row.candidate_external_id
                account.external_account_id = row.candidate_external_id
                account.credential_ciphertext = row.candidate_credential_ciphertext
                account.credential_refresh_owner = None
                account.credential_refresh_fence = None
                account.credential_refresh_lease_expires_at = None
                account.scopes_json = row.candidate_scopes_json or "[]"
                account.token_expires_at = row.candidate_token_expires_at
                account.status = "connected"
                account.disabled = False
                account.last_validated_at = now
                account.updated_at = now
            row.confirmed_at = now
            row.candidate_credential_ciphertext = None
            row.verifier_ciphertext = None
            session.flush()
            return account.id


def _state_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
