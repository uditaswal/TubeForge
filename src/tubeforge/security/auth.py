"""Opaque, database-backed dashboard sessions with Argon2id passwords."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import secrets
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.db.models import AdminUserRecord, AuthSessionRecord

_hasher = PasswordHasher()


class AuthService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None: self._session_factory = session_factory

    def create_admin(self, username: str, password: str) -> None:
        username = username.strip()
        if len(username) < 3 or len(username) > 100 or not password or len(password) < 12:
            raise ValueError("username must be 3-100 characters and password at least 12 characters")
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            if session.scalar(select(AdminUserRecord.id).where(AdminUserRecord.username == username)):
                raise ValueError("administrator already exists")
            session.add(AdminUserRecord(id=uuid4().hex, username=username, password_hash=_hasher.hash(password), disabled=False, created_at=now, updated_at=now))

    def authenticate(self, username: str, password: str, *, session_hours: int) -> tuple[str, str] | None:
        with self._session_factory() as session:
            user = session.scalar(select(AdminUserRecord).where(AdminUserRecord.username == username.strip(), AdminUserRecord.disabled.is_(False)))
            if user is None:
                return None
            try:
                if not _hasher.verify(user.password_hash, password): return None
            except VerifyMismatchError:
                return None
            user_id = user.id
        token, csrf, now = secrets.token_urlsafe(48), secrets.token_urlsafe(32), datetime.now(UTC)
        with self._session_factory.begin() as session:
            session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.expires_at <= now))
            session.add(AuthSessionRecord(id=uuid4().hex, user_id=user_id, token_hash=_hash(token), csrf_token=csrf, expires_at=now + timedelta(hours=session_hours), created_at=now))
        return token, csrf

    def session(self, token: str | None) -> AuthSessionRecord | None:
        if not token: return None
        now = datetime.now(UTC)
        with self._session_factory() as session:
            record = session.scalar(select(AuthSessionRecord).where(AuthSessionRecord.token_hash == _hash(token), AuthSessionRecord.expires_at > now))
            return record

    def logout(self, token: str | None) -> None:
        if not token: return
        with self._session_factory.begin() as session: session.execute(delete(AuthSessionRecord).where(AuthSessionRecord.token_hash == _hash(token)))


def _hash(value: str) -> str: return hashlib.sha256(value.encode("utf-8")).hexdigest()
