"""Encrypted account credentials with a fenced cross-process refresh lease."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable
from uuid import uuid4

import httpx
from sqlalchemy import or_, update
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.db.models import SocialAccountRecord
from tubeforge.security.secrets import TokenCipher


GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


class CredentialBusy(RuntimeError):
    """Another worker owns the account's refresh lease."""


class CredentialReconnectRequired(RuntimeError):
    """The provider rejected the refresh token or no refresh route exists."""


class CredentialRefreshTemporary(RuntimeError):
    """The refresh request failed without proof that access was revoked."""


@dataclass(frozen=True, slots=True)
class RefreshedCredential:
    value: dict[str, object]
    expires_at: datetime


class GoogleCredentialRefresher:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=15, follow_redirects=False)

    def __call__(self, credential: dict[str, object]) -> RefreshedCredential:
        if credential.get("token_uri") != GOOGLE_TOKEN_URL:
            raise CredentialReconnectRequired("Google token endpoint is invalid")
        required = ("client_id", "client_secret", "refresh_token")
        if any(not isinstance(credential.get(key), str) or not credential[key] for key in required):
            raise CredentialReconnectRequired("Google offline credential is incomplete")
        try:
            response = self.client.post(GOOGLE_TOKEN_URL, data={
                "grant_type": "refresh_token",
                "client_id": credential["client_id"],
                "client_secret": credential["client_secret"],
                "refresh_token": credential["refresh_token"],
            })
        except httpx.HTTPError as error:
            raise CredentialRefreshTemporary("Google token refresh is temporarily unavailable") from error
        if response.status_code == 400 and response.json().get("error") == "invalid_grant":
            raise CredentialReconnectRequired("Google refresh access was revoked")
        if response.status_code != 200:
            raise CredentialRefreshTemporary("Google token refresh was not accepted")
        data = response.json()
        token, lifetime = data.get("access_token"), data.get("expires_in")
        if not isinstance(token, str) or not token or not isinstance(lifetime, int) or lifetime < 60:
            raise CredentialRefreshTemporary("Google returned an invalid refreshed credential")
        expires_at = datetime.now(UTC) + timedelta(seconds=lifetime)
        updated = {**credential, "token": token, "expiry": expires_at.isoformat()}
        if isinstance(data.get("refresh_token"), str) and data["refresh_token"]:
            updated["refresh_token"] = data["refresh_token"]
        return RefreshedCredential(updated, expires_at)


class AccountCredentialManager:
    def __init__(
        self, session_factory: sessionmaker[Session], cipher: TokenCipher,
        refreshers: dict[str, Callable[[dict[str, object]], RefreshedCredential]],
    ) -> None:
        self.session_factory, self.cipher, self.refreshers = session_factory, cipher, refreshers

    def resolve(self, account_id: str, owner: str, *, now: datetime | None = None, minimum_lifetime_seconds: int = 300) -> dict[str, object]:
        if not account_id or not owner or minimum_lifetime_seconds < 0:
            raise ValueError("account, owner and nonnegative lifetime are required")
        started_at = now or datetime.now(UTC)
        with self.session_factory() as session:
            row = session.get(SocialAccountRecord, account_id)
            if row is None or row.disabled or row.status != "connected" or not row.credential_ciphertext:
                raise CredentialReconnectRequired("destination account needs reconnection")
            original_ciphertext = row.credential_ciphertext
            platform = row.platform
            expiry = _utc(row.token_expires_at) if row.token_expires_at else None
        if expiry is None or expiry > started_at + timedelta(seconds=minimum_lifetime_seconds):
            return self.cipher.decrypt(original_ciphertext)
        refresher = self.refreshers.get(platform)
        if refresher is None:
            raise CredentialReconnectRequired("destination credential has no refresh route")
        fence = uuid4().hex
        with self.session_factory.begin() as session:
            acquired = session.execute(update(SocialAccountRecord).where(
                SocialAccountRecord.id == account_id,
                SocialAccountRecord.status == "connected",
                SocialAccountRecord.disabled.is_(False),
                SocialAccountRecord.credential_ciphertext == original_ciphertext,
                or_(SocialAccountRecord.credential_refresh_lease_expires_at.is_(None), SocialAccountRecord.credential_refresh_lease_expires_at <= started_at),
            ).values(
                credential_refresh_owner=owner, credential_refresh_fence=fence,
                credential_refresh_lease_expires_at=started_at + timedelta(seconds=120),
            ))
            if acquired.rowcount != 1:
                raise CredentialBusy("destination credential refresh is already in progress")
        try:
            refreshed = refresher(self.cipher.decrypt(original_ciphertext))
            finished_at = now or datetime.now(UTC)
            if not isinstance(refreshed.expires_at, datetime) or _utc(refreshed.expires_at) <= finished_at + timedelta(seconds=minimum_lifetime_seconds):
                raise CredentialRefreshTemporary("refreshed credential expires too soon")
            if not isinstance(refreshed.value.get("token"), str) or not refreshed.value["token"]:
                raise CredentialRefreshTemporary("refreshed credential has no access token")
            sealed = self.cipher.encrypt(refreshed.value)
            with self.session_factory.begin() as session:
                saved = session.execute(update(SocialAccountRecord).where(
                    SocialAccountRecord.id == account_id,
                    SocialAccountRecord.credential_ciphertext == original_ciphertext,
                    SocialAccountRecord.credential_refresh_owner == owner,
                    SocialAccountRecord.credential_refresh_fence == fence,
                    SocialAccountRecord.credential_refresh_lease_expires_at > finished_at,
                    SocialAccountRecord.status == "connected",
                ).values(
                    credential_ciphertext=sealed,
                    token_expires_at=refreshed.expires_at,
                    credential_refresh_owner=None,
                    credential_refresh_fence=None,
                    credential_refresh_lease_expires_at=None,
                    updated_at=finished_at,
                ))
                if saved.rowcount != 1:
                    raise CredentialBusy("destination credential changed during refresh")
            return refreshed.value
        except CredentialReconnectRequired:
            self._release(account_id, owner, fence, original_ciphertext, reconnect=True)
            raise
        except Exception as error:
            self._release(account_id, owner, fence, original_ciphertext, reconnect=False)
            if isinstance(error, (CredentialBusy, CredentialRefreshTemporary)):
                raise
            raise CredentialRefreshTemporary("destination credential refresh failed") from error

    def _release(self, account_id: str, owner: str, fence: str, original_ciphertext: str, *, reconnect: bool) -> None:
        with self.session_factory.begin() as session:
            values: dict[str, object] = {
                "credential_refresh_owner": None,
                "credential_refresh_fence": None,
                "credential_refresh_lease_expires_at": None,
            }
            if reconnect:
                values["status"] = "reconnect_required"
            session.execute(update(SocialAccountRecord).where(
                SocialAccountRecord.id == account_id,
                SocialAccountRecord.credential_ciphertext == original_ciphertext,
                SocialAccountRecord.credential_refresh_owner == owner,
                SocialAccountRecord.credential_refresh_fence == fence,
            ).values(**values))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
