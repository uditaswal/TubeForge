"""Durable, fenced destination work; remote operations live outside transactions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.db.models import DeliveryAttemptRecord, DestinationDeliveryRecord, PublishJobRecord, SocialAccountRecord


@dataclass(frozen=True, slots=True)
class DeliveryClaim:
    delivery_id: str
    post_id: str
    owner: str
    token: str
    kind: str
    platform: str
    account_id: str
    external_account_id: str
    remote_id: str | None
    remote_session_id: str | None


class DeliveryQueue:
    """Conservative at-least-once queue: expired uploads require reconciliation."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def claim_next(self, owner: str, *, platforms: set[str] | None = None, now: datetime | None = None, lease_seconds: int = 120) -> DeliveryClaim | None:
        if not owner or lease_seconds < 1:
            raise ValueError("a worker owner and positive lease are required")
        now = now or datetime.now(UTC)
        if platforms is not None and not platforms:
            return None
        with self.session_factory.begin() as session:
            self._recover_expired(session, now)
            eligibility = [
                DestinationDeliveryRecord.claim_owner.is_(None),
                or_(
                    DestinationDeliveryRecord.state == "pending",
                    (DestinationDeliveryRecord.state == "retry_wait") & (DestinationDeliveryRecord.next_retry_at <= now),
                    (DestinationDeliveryRecord.state == "verifying") & or_(DestinationDeliveryRecord.next_retry_at.is_(None), DestinationDeliveryRecord.next_retry_at <= now),
                ),
            ]
            if platforms is not None:
                eligibility.append(DestinationDeliveryRecord.platform.in_(platforms))
            rows = session.scalars(select(DestinationDeliveryRecord).where(*eligibility).order_by(DestinationDeliveryRecord.created_at, DestinationDeliveryRecord.id).limit(20)).all()
            for row in rows:
                same_account_claim = session.scalar(select(DestinationDeliveryRecord.id).where(
                    DestinationDeliveryRecord.account_id == row.account_id,
                    DestinationDeliveryRecord.id != row.id,
                    DestinationDeliveryRecord.claim_owner.is_not(None),
                    DestinationDeliveryRecord.lease_expires_at > now,
                ).limit(1))
                if same_account_claim is not None:
                    continue
                account = session.get(SocialAccountRecord, row.account_id)
                if account is None or account.disabled or account.status != "connected" or account.last_validated_at is None or not account.credential_ciphertext or account.external_account_id != row.external_account_id:
                    row.state = "auth_required"
                    row.error_message = "destination account needs reconnection"
                    row.updated_at = now
                    self._refresh_parent(session, row.publish_job_id, now)
                    continue
                kind = "verify" if row.state == "verifying" else "upload"
                if kind == "verify" and not row.remote_id:
                    row.state = "unknown_outcome"
                    row.error_message = "remote publication identity is missing"
                    row.updated_at = now
                    self._refresh_parent(session, row.publish_job_id, now)
                    continue
                token = uuid4().hex
                new_state = "verifying" if kind == "verify" else "uploading"
                result = session.execute(update(DestinationDeliveryRecord).where(
                    DestinationDeliveryRecord.id == row.id,
                    DestinationDeliveryRecord.claim_owner.is_(None),
                    DestinationDeliveryRecord.state == row.state,
                ).values(
                    state=new_state, claim_owner=owner, claim_token=token,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    next_retry_at=None, attempt_count=DestinationDeliveryRecord.attempt_count + (kind == "upload"),
                    updated_at=now,
                ))
                if result.rowcount != 1:
                    continue
                session.add(DeliveryAttemptRecord(
                    id=uuid4().hex, delivery_id=row.id, claim_token=token, kind=kind,
                    state="started", remote_session_id=row.remote_session_id,
                    remote_id=row.remote_id, error_message=None, started_at=now, finished_at=None,
                ))
                post = session.get(PublishJobRecord, row.publish_job_id)
                if post is not None and post.state == "queued":
                    post.state = "dispatching"
                    post.updated_at = now
                return DeliveryClaim(row.id, row.publish_job_id, owner, token, kind, row.platform, row.account_id, row.external_account_id, row.remote_id, row.remote_session_id)
        return None

    def heartbeat(self, claim: DeliveryClaim, *, now: datetime | None = None, lease_seconds: int = 120) -> bool:
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            result = session.execute(update(DestinationDeliveryRecord).where(
                DestinationDeliveryRecord.id == claim.delivery_id,
                DestinationDeliveryRecord.claim_owner == claim.owner,
                DestinationDeliveryRecord.claim_token == claim.token,
                DestinationDeliveryRecord.lease_expires_at > now,
            ).values(lease_expires_at=now + timedelta(seconds=lease_seconds), updated_at=now))
            return result.rowcount == 1

    def request_action(self, delivery_id: str, action: str, actor: str, *, now: datetime | None = None) -> None:
        """Durably ask a worker to inspect or continue one saved session."""
        if action not in {"inspect", "resume"} or not actor or len(actor) > 64:
            raise ValueError("a valid action and operator are required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            self._recover_expired(session, now)
            row = session.get(DestinationDeliveryRecord, delivery_id)
            if row is None:
                raise KeyError(delivery_id)
            if row.platform != "youtube" or row.state != "unknown_outcome" or row.claim_owner is not None or not row.remote_session_id or row.remote_id:
                raise ValueError("this destination has no inspectable uncertain upload session")
            if row.requested_action:
                raise ValueError("a reconciliation action is already pending")
            if action == "resume":
                latest = session.scalar(select(DeliveryAttemptRecord).where(
                    DeliveryAttemptRecord.delivery_id == delivery_id,
                    DeliveryAttemptRecord.kind.in_({"reconcile", "resume"}),
                ).order_by(DeliveryAttemptRecord.started_at.desc(), DeliveryAttemptRecord.id.desc()).limit(1))
                if latest is None or latest.kind != "reconcile" or latest.state != "unresolved" or not (latest.error_message or "").startswith("remote upload is incomplete"):
                    raise ValueError("inspect the saved remote session before requesting continuation")
            changed = session.execute(update(DestinationDeliveryRecord).where(
                DestinationDeliveryRecord.id == delivery_id,
                DestinationDeliveryRecord.state == "unknown_outcome",
                DestinationDeliveryRecord.claim_owner.is_(None),
                DestinationDeliveryRecord.requested_action.is_(None),
            ).values(requested_action=action, requested_by=actor, requested_at=now, updated_at=now))
            if changed.rowcount != 1:
                raise ValueError("destination changed while requesting reconciliation")

    def retry_after_reconnect(self, delivery_id: str, actor: str, *, now: datetime | None = None) -> str:
        """Release auth-required work only after the exact account reconnects."""
        if not actor or len(actor) > 64:
            raise ValueError("a valid operator is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            self._recover_expired(session, now)
            row = session.get(DestinationDeliveryRecord, delivery_id)
            if row is None:
                raise KeyError(delivery_id)
            if row.state != "auth_required" or row.claim_owner is not None:
                raise ValueError("only an unclaimed auth-required destination can be resumed")
            account = session.get(SocialAccountRecord, row.account_id)
            if account is None or account.disabled or account.status != "connected" or account.external_account_id != row.external_account_id or not account.credential_ciphertext or account.last_validated_at is None:
                raise ValueError("reconnect the exact destination account first")
            if row.remote_id:
                new_state, reason = "verifying", None
            elif row.remote_session_id:
                new_state, reason = "unknown_outcome", "account reconnected; inspect the saved remote session before retry"
            else:
                new_state, reason = "pending", None
            changed = session.execute(update(DestinationDeliveryRecord).where(
                DestinationDeliveryRecord.id == delivery_id,
                DestinationDeliveryRecord.state == "auth_required",
                DestinationDeliveryRecord.claim_owner.is_(None),
            ).values(state=new_state, error_message=reason, next_retry_at=None,
                     requested_action=None, requested_by=actor, requested_at=now, updated_at=now))
            if changed.rowcount != 1:
                raise ValueError("destination changed during reconnect retry")
            session.add(DeliveryAttemptRecord(
                id=uuid4().hex, delivery_id=delivery_id, claim_token=uuid4().hex,
                kind="requeue", state="accepted" if new_state != "unknown_outcome" else "attention_required",
                remote_session_id=None, remote_id=row.remote_id,
                error_message=reason or f"requested by {actor}",
                started_at=now, finished_at=now,
            ))
            self._refresh_parent(session, row.publish_job_id, now)
            return new_state

    def next_requested_action(self, *, platforms: set[str]) -> tuple[str, str] | None:
        if not platforms:
            return None
        now = datetime.now(UTC)
        with self.session_factory.begin() as session:
            self._recover_expired(session, now)
            rows = session.scalars(select(DestinationDeliveryRecord).where(
                DestinationDeliveryRecord.state == "unknown_outcome",
                DestinationDeliveryRecord.claim_owner.is_(None),
                DestinationDeliveryRecord.requested_action.in_({"inspect", "resume"}),
                DestinationDeliveryRecord.platform.in_(platforms),
            ).order_by(DestinationDeliveryRecord.requested_at, DestinationDeliveryRecord.id).limit(20)).all()
            for row in rows:
                busy = session.scalar(select(DestinationDeliveryRecord.id).where(
                    DestinationDeliveryRecord.account_id == row.account_id,
                    DestinationDeliveryRecord.id != row.id,
                    DestinationDeliveryRecord.claim_owner.is_not(None),
                    DestinationDeliveryRecord.lease_expires_at > now,
                ).limit(1))
                if busy is None:
                    return row.id, row.requested_action
            return None

    def claim_reconciliation(self, delivery_id: str, owner: str, *, resume: bool = False, now: datetime | None = None, lease_seconds: int = 120) -> DeliveryClaim | None:
        """Claim only an uncertain delivery with a saved session for read-only status."""
        if not delivery_id or not owner or lease_seconds < 1:
            raise ValueError("delivery, worker owner and positive lease are required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            self._recover_expired(session, now)
            row = session.get(DestinationDeliveryRecord, delivery_id)
            if row is None or row.state != "unknown_outcome" or row.claim_owner is not None or not row.remote_session_id or row.remote_id:
                return None
            other = session.scalar(select(DestinationDeliveryRecord.id).where(
                DestinationDeliveryRecord.account_id == row.account_id,
                DestinationDeliveryRecord.id != row.id,
                DestinationDeliveryRecord.claim_owner.is_not(None),
                DestinationDeliveryRecord.lease_expires_at > now,
            ).limit(1))
            if other is not None:
                return None
            token = uuid4().hex
            changed = session.execute(update(DestinationDeliveryRecord).where(
                DestinationDeliveryRecord.id == delivery_id,
                DestinationDeliveryRecord.state == "unknown_outcome",
                DestinationDeliveryRecord.claim_owner.is_(None),
            ).values(state="reconciling", claim_owner=owner, claim_token=token,
                     lease_expires_at=now + timedelta(seconds=lease_seconds),
                     requested_action=None, updated_at=now))
            if changed.rowcount != 1:
                return None
            session.add(DeliveryAttemptRecord(
                id=uuid4().hex, delivery_id=row.id, claim_token=token, kind="resume" if resume else "reconcile",
                state="started", remote_session_id=row.remote_session_id, remote_id=None,
                error_message=None, started_at=now, finished_at=None,
            ))
            return DeliveryClaim(row.id, row.publish_job_id, owner, token, "resume" if resume else "reconcile", row.platform, row.account_id, row.external_account_id, None, row.remote_session_id)

    def reconciled_uploaded(self, claim: DeliveryClaim, remote_id: str, *, remote_url: str | None = None, now: datetime | None = None) -> None:
        if claim.kind not in {"reconcile", "resume"} or not remote_id:
            raise ValueError("reconciled remote publication ID is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "reconciling")
            row.remote_id, row.remote_url, row.state = remote_id, remote_url, "verifying"
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.remote_id, attempt.state, attempt.finished_at = remote_id, "accepted", now
            self._refresh_parent(session, row.publish_job_id, now)

    def reconciliation_unresolved(self, claim: DeliveryClaim, reason: str, *, now: datetime | None = None) -> None:
        if claim.kind not in {"reconcile", "resume"}:
            raise ValueError("reconciliation claim is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "reconciling")
            row.state, row.error_message = "unknown_outcome", reason[:500]
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "unresolved", row.error_message, now
            self._refresh_parent(session, row.publish_job_id, now)

    def record_session(self, claim: DeliveryClaim, remote_session_id: str, *, now: datetime | None = None) -> None:
        if claim.kind != "upload" or not remote_session_id:
            raise ValueError("upload session identity is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "uploading")
            if row.remote_session_id and row.remote_session_id != remote_session_id:
                raise ValueError("remote upload session identity changed")
            row.remote_session_id = remote_session_id
            row.updated_at = now
            attempt = self._attempt(session, claim)
            attempt.remote_session_id = remote_session_id

    def upload_accepted(self, claim: DeliveryClaim, remote_id: str, *, remote_url: str | None = None, now: datetime | None = None) -> None:
        if claim.kind != "upload" or not remote_id:
            raise ValueError("remote publication ID is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "uploading")
            if not row.remote_session_id:
                raise ValueError("remote upload session must be recorded before acceptance")
            row.remote_id, row.remote_url, row.state = remote_id, remote_url, "verifying"
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.remote_id, attempt.state, attempt.finished_at = remote_id, "accepted", now
            self._refresh_parent(session, row.publish_job_id, now)

    def verified_published(self, claim: DeliveryClaim, *, remote_url: str | None = None, now: datetime | None = None) -> None:
        if claim.kind != "verify":
            raise ValueError("publication needs a read-only verification claim")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "verifying")
            if not row.remote_id or row.remote_id != claim.remote_id:
                raise ValueError("remote publication identity changed")
            row.state = "published"
            if remote_url:
                row.remote_url = remote_url
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.finished_at = "verified", now
            self._refresh_parent(session, row.publish_job_id, now)

    def verification_pending(self, claim: DeliveryClaim, *, retry_at: datetime, now: datetime | None = None) -> None:
        if claim.kind != "verify":
            raise ValueError("read-only verification claim is required")
        now = now or datetime.now(UTC)
        if retry_at <= now:
            raise ValueError("verification retry must be in the future")
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "verifying")
            row.next_retry_at = retry_at
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.finished_at = "processing", now

    def preflight_failed(self, claim: DeliveryClaim, reason: str, *, authentication: bool = False, now: datetime | None = None) -> None:
        """Use only before any remote mutation or session creation starts."""
        if claim.kind != "upload":
            raise ValueError("upload claim is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "uploading")
            if row.remote_session_id:
                raise ValueError("remote session exists; reconcile instead")
            row.state, row.error_message = ("auth_required" if authentication else "failed"), reason[:500]
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = row.state, row.error_message, now
            self._refresh_parent(session, row.publish_job_id, now)

    def preflight_retry(self, claim: DeliveryClaim, reason: str, *, retry_at: datetime, now: datetime | None = None) -> None:
        if claim.kind != "upload":
            raise ValueError("upload claim is required")
        now = now or datetime.now(UTC)
        if retry_at <= now:
            raise ValueError("retry must be in the future")
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "uploading")
            if row.remote_session_id:
                raise ValueError("remote session exists; reconcile instead")
            row.state, row.error_message, row.next_retry_at = "retry_wait", reason[:500], retry_at
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "retry_wait", row.error_message, now
            self._refresh_parent(session, row.publish_job_id, now)

    def auth_required(self, claim: DeliveryClaim, reason: str, *, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "verifying" if claim.kind == "verify" else "uploading")
            row.state, row.error_message = "auth_required", reason[:500]
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "auth_required", row.error_message, now
            self._refresh_parent(session, row.publish_job_id, now)

    def uncertain(self, claim: DeliveryClaim, reason: str, *, now: datetime | None = None) -> None:
        """Stop automatic retries when a remote mutation may have occurred."""
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "uploading")
            row.state, row.error_message = "unknown_outcome", reason[:500]
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "unknown_outcome", reason[:500], now
            self._refresh_parent(session, row.publish_job_id, now)

    def remote_missing(self, claim: DeliveryClaim, *, now: datetime | None = None) -> None:
        self.verification_attention(claim, "recorded remote post is missing; reconcile manually", now=now)

    def verification_attention(self, claim: DeliveryClaim, reason: str, *, now: datetime | None = None) -> None:
        if claim.kind != "verify":
            raise ValueError("read-only verification claim is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "verifying")
            row.state, row.error_message = "unknown_outcome", reason[:500]
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "unknown_outcome", row.error_message, now
            self._refresh_parent(session, row.publish_job_id, now)

    def _recover_expired(self, session: Session, now: datetime) -> None:
        expired = session.scalars(select(DestinationDeliveryRecord).where(
            DestinationDeliveryRecord.lease_expires_at.is_not(None),
            DestinationDeliveryRecord.lease_expires_at <= now,
            DestinationDeliveryRecord.claim_owner.is_not(None),
        )).all()
        for row in expired:
            attempt = session.scalar(select(DeliveryAttemptRecord).where(DeliveryAttemptRecord.claim_token == row.claim_token))
            if row.state == "uploading":
                row.state, row.error_message = "unknown_outcome", "upload lease expired; reconcile before retry"
                if attempt is not None:
                    attempt.state, attempt.error_message, attempt.finished_at = "unknown_outcome", row.error_message, now
            elif row.state == "verifying" and attempt is not None:
                attempt.state, attempt.error_message, attempt.finished_at = "interrupted", "verification lease expired", now
            elif row.state == "reconciling":
                row.state, row.error_message = "unknown_outcome", "reconciliation lease expired; inspect the saved session again"
                if attempt is not None:
                    attempt.state, attempt.error_message, attempt.finished_at = "interrupted", row.error_message, now
            self._release(row, now)
            self._refresh_parent(session, row.publish_job_id, now)

    @staticmethod
    def _refresh_parent(session: Session, post_id: str, now: datetime) -> None:
        session.flush()
        states = list(session.scalars(select(DestinationDeliveryRecord.state).where(
            DestinationDeliveryRecord.publish_job_id == post_id,
            DestinationDeliveryRecord.required.is_(True),
        )))
        post = session.get(PublishJobRecord, post_id)
        if post is None or post.state == "draft" or not states:
            return
        if all(state == "published" for state in states):
            post.state = "published"
        elif "unknown_outcome" in states or "reconciling" in states:
            post.state = "attention_required"
        elif any(state in {"failed", "auth_required"} for state in states):
            post.state = "partial_failure"
        elif "verifying" in states:
            post.state = "verifying"
        else:
            post.state = "dispatching"
        post.updated_at = now

    @staticmethod
    def _owned(session: Session, claim: DeliveryClaim, now: datetime, state: str) -> DestinationDeliveryRecord:
        row = session.get(DestinationDeliveryRecord, claim.delivery_id)
        if row is None or row.claim_owner != claim.owner or row.claim_token != claim.token or row.state != state or row.lease_expires_at is None or _utc(row.lease_expires_at) <= now:
            raise ValueError("destination lease ownership was lost")
        return row

    @staticmethod
    def _attempt(session: Session, claim: DeliveryClaim) -> DeliveryAttemptRecord:
        attempt = session.scalar(select(DeliveryAttemptRecord).where(DeliveryAttemptRecord.claim_token == claim.token))
        if attempt is None:
            raise ValueError("delivery attempt is missing")
        return attempt

    @staticmethod
    def _release(row: DestinationDeliveryRecord, now: datetime) -> None:
        row.claim_owner = row.claim_token = row.lease_expires_at = None
        row.updated_at = now


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
