"""Durable, fenced destination work; remote operations live outside transactions."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.db.models import DeliveryAttemptRecord, DestinationDeliveryRecord, PublishJobRecord, PublisherWorkerHeartbeatRecord, SocialAccountRecord


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
    remote_container_id: str | None = None
    remote_session_expires_at: datetime | None = None
    scheduled_for: datetime | None = None
    attempt_number: int = 1


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
            session.execute(text("BEGIN IMMEDIATE"))
            self._recover_expired(session, now)
            missed = session.scalars(select(DestinationDeliveryRecord).where(
                DestinationDeliveryRecord.claim_owner.is_(None),
                DestinationDeliveryRecord.scheduled_for.is_not(None),
                DestinationDeliveryRecord.scheduled_for < now - timedelta(minutes=30),
                DestinationDeliveryRecord.state.in_({"pending", "retry_wait", "container_processing", "container_ready"}),
            )).all()
            for row in missed:
                row.state, row.error_message, row.updated_at = "missed", "scheduled slot passed the 30-minute grace period", now
                row.next_retry_at = None
                self._refresh_parent(session, row.publish_job_id, now)
            upload_due = or_(DestinationDeliveryRecord.platform != "instagram", DestinationDeliveryRecord.scheduled_for.is_(None), DestinationDeliveryRecord.scheduled_for <= now + timedelta(minutes=30))
            publish_due = or_(DestinationDeliveryRecord.scheduled_for.is_(None), DestinationDeliveryRecord.scheduled_for <= now)
            eligibility = [
                DestinationDeliveryRecord.claim_owner.is_(None),
                or_(
                    (DestinationDeliveryRecord.state == "pending") & upload_due,
                    (DestinationDeliveryRecord.state == "retry_wait") & (DestinationDeliveryRecord.next_retry_at <= now) & upload_due,
                    (DestinationDeliveryRecord.state == "verifying") & or_(DestinationDeliveryRecord.next_retry_at.is_(None), DestinationDeliveryRecord.next_retry_at <= now),
                    (DestinationDeliveryRecord.state == "container_processing") & or_(DestinationDeliveryRecord.next_retry_at.is_(None), DestinationDeliveryRecord.next_retry_at <= now),
                    (DestinationDeliveryRecord.state == "container_ready") & publish_due & or_(DestinationDeliveryRecord.next_retry_at.is_(None), DestinationDeliveryRecord.next_retry_at <= now),
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
                kind = {"verifying": "verify", "container_processing": "container_check", "container_ready": "container_publish"}.get(row.state, "upload")
                # During downtime recovery, allow one overdue publication and
                # defer another for the same account instead of bursting them.
                if kind == "container_publish" and row.scheduled_for and _utc(row.scheduled_for) < now:
                    heartbeat = session.get(PublisherWorkerHeartbeatRecord, owner)
                    recovering = heartbeat is None or _utc(heartbeat.started_at) > _utc(row.scheduled_for)
                    if recovering:
                        attempt_time = func.coalesce(DeliveryAttemptRecord.finished_at, DeliveryAttemptRecord.started_at)
                        latest = session.scalar(select(func.max(attempt_time)).join(
                            DestinationDeliveryRecord, DeliveryAttemptRecord.delivery_id == DestinationDeliveryRecord.id,
                        ).where(
                            DestinationDeliveryRecord.account_id == row.account_id,
                            DestinationDeliveryRecord.id != row.id,
                            DeliveryAttemptRecord.kind == "container_publish",
                            DeliveryAttemptRecord.state.in_({"accepted", "unknown_outcome"}),
                            attempt_time > now - timedelta(minutes=30),
                        ))
                        if latest is not None:
                            row.next_retry_at = _utc(latest) + timedelta(minutes=30)
                            row.error_message = "overdue publication delayed to avoid a recovery burst"
                            row.updated_at = now
                            continue
                if kind in {"container_check", "container_publish"}:
                    if not row.remote_container_id or not row.remote_session_id or not row.remote_session_expires_at:
                        row.state, row.error_message, row.updated_at = "unknown_outcome", "saved container identity or expiry is missing", now
                        self._refresh_parent(session, row.publish_job_id, now)
                        continue
                    if _utc(row.remote_session_expires_at) <= now:
                        row.state, row.error_message, row.updated_at = "failed", "remote container expired before publication", now
                        self._refresh_parent(session, row.publish_job_id, now)
                        continue
                if kind == "verify" and not row.remote_id:
                    row.state = "unknown_outcome"
                    row.error_message = "remote publication identity is missing"
                    row.updated_at = now
                    self._refresh_parent(session, row.publish_job_id, now)
                    continue
                token = uuid4().hex
                new_state = {"verify": "verifying", "container_check": "container_processing", "container_publish": "publishing"}.get(kind, "uploading")
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
                return DeliveryClaim(row.id, row.publish_job_id, owner, token, kind, row.platform, row.account_id, row.external_account_id, row.remote_id, row.remote_session_id, row.remote_container_id, row.remote_session_expires_at, row.scheduled_for, max(1, row.attempt_count))
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
            if row.state != "unknown_outcome" or row.claim_owner is not None or not row.remote_session_id or row.remote_id:
                raise ValueError("this destination has no inspectable uncertain upload session")
            if row.requested_action:
                raise ValueError("a reconciliation action is already pending")
            if action == "resume":
                if row.remote_container_id:
                    raise ValueError("a saved container cannot be resumed as an upload")
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

    def pending_action(self, delivery_id: str, action: str, actor: str, *, now: datetime | None = None) -> str:
        """Pause, resume or cancel only local, unclaimed pending work."""
        if action not in {"pause", "resume", "cancel"} or not actor or len(actor) > 64:
            raise ValueError("valid pending action and operator are required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            session.execute(text("BEGIN IMMEDIATE"))
            self._recover_expired(session, now)
            row = session.get(DestinationDeliveryRecord, delivery_id)
            if row is None:
                raise KeyError(delivery_id)
            resuming_quota = action == "resume" and row.state == "quota_paused"
            if row.claim_owner or (row.remote_id and not resuming_quota):
                raise ValueError("delivery is in flight or already remote; pending action is unavailable")
            if row.platform == "youtube" and row.remote_session_id and not resuming_quota:
                raise ValueError("YouTube session already started; reconcile the remote outcome")
            eligible = {"pending", "retry_wait", "container_processing", "container_ready"}
            if action == "resume":
                if row.state not in {"paused", "quota_paused"} or row.paused_from_state not in eligible | {"verifying", "unknown_outcome"}:
                    raise ValueError("only a paused pending or quota-limited delivery can be resumed")
                row.state, row.paused_from_state = row.paused_from_state, None
            elif action == "pause":
                if row.state not in eligible:
                    raise ValueError("only an unclaimed pending delivery can be paused")
                row.paused_from_state, row.state = row.state, "paused"
            else:
                if row.state not in eligible | {"paused"}:
                    raise ValueError("only an unclaimed pending delivery can be cancelled")
                row.state, row.paused_from_state, row.next_retry_at = "cancelled", None, None
            audit_detail = f"{action} requested by {actor}"
            row.error_message = audit_detail if action == "cancel" else None
            row.updated_at = now
            session.add(DeliveryAttemptRecord(id=uuid4().hex, delivery_id=row.id, claim_token=uuid4().hex,
                kind=action, state=row.state, remote_session_id=row.remote_session_id, remote_id=None,
                error_message=audit_detail, started_at=now, finished_at=now))
            self._refresh_parent(session, row.publish_job_id, now)
            return row.state

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
            elif row.remote_container_id:
                new_state, reason = "container_processing", None
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
                or_(DestinationDeliveryRecord.next_retry_at.is_(None), DestinationDeliveryRecord.next_retry_at <= now),
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
            if row is None or row.state != "unknown_outcome" or row.claim_owner is not None or not row.remote_session_id or row.remote_id or (row.next_retry_at is not None and _utc(row.next_retry_at) > now) or (resume and row.remote_container_id):
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
            return DeliveryClaim(row.id, row.publish_job_id, owner, token, "resume" if resume else "reconcile", row.platform, row.account_id, row.external_account_id, None, row.remote_session_id, row.remote_container_id, row.remote_session_expires_at, row.scheduled_for, max(1, row.attempt_count))

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

    def reconciliation_unresolved(self, claim: DeliveryClaim, reason: str, *, retry_at: datetime | None = None, now: datetime | None = None) -> None:
        if claim.kind not in {"reconcile", "resume"}:
            raise ValueError("reconciliation claim is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "reconciling")
            row.state, row.error_message = "unknown_outcome", reason[:500]
            row.next_retry_at = retry_at
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "unresolved", row.error_message, now
            self._refresh_parent(session, row.publish_job_id, now)

    def record_session(self, claim: DeliveryClaim, remote_session_id: str, *, expires_at: datetime | None = None, now: datetime | None = None) -> None:
        if claim.kind != "upload" or not remote_session_id:
            raise ValueError("upload session identity is required")
        now = now or datetime.now(UTC)
        if expires_at is not None and (expires_at.tzinfo is None or expires_at <= now):
            raise ValueError("remote session expiry must be in the future and timezone aware")
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "uploading")
            if row.remote_session_id and row.remote_session_id != remote_session_id:
                raise ValueError("remote upload session identity changed")
            row.remote_session_id = remote_session_id
            row.remote_session_expires_at = expires_at
            row.updated_at = now
            attempt = self._attempt(session, claim)
            attempt.remote_session_id = remote_session_id

    def container_staged(self, claim: DeliveryClaim, container_id: str, *, now: datetime | None = None) -> None:
        """Persist the uploaded container before any publication attempt."""
        if claim.kind not in {"upload", "reconcile", "resume"} or not container_id:
            raise ValueError("uploaded container identity is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            state = "uploading" if claim.kind == "upload" else "reconciling"
            row = self._owned(session, claim, now, state)
            if not row.remote_session_id or not row.remote_session_expires_at:
                raise ValueError("container session and expiry must be recorded first")
            if row.remote_container_id and row.remote_container_id != container_id:
                raise ValueError("remote container identity changed")
            row.remote_container_id = container_id
            row.state = "container_processing" if _utc(row.remote_session_expires_at) > now else "failed"
            row.error_message = None if row.state == "container_processing" else "remote container expired before publication"
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "container_staged", row.error_message, now
            self._refresh_parent(session, row.publish_job_id, now)

    def container_observed(self, claim: DeliveryClaim, state: str, *, retry_at: datetime | None = None, remote_id: str | None = None, remote_url: str | None = None, now: datetime | None = None) -> None:
        if claim.kind not in {"container_check", "reconcile"} or state not in {"processing", "ready", "published", "expired", "failed"}:
            raise ValueError("invalid container observation")
        now = now or datetime.now(UTC)
        if state == "processing" and (retry_at is None or retry_at <= now):
            raise ValueError("container processing needs a future retry time")
        if state == "published" and not remote_id:
            raise ValueError("published container needs a remote media identity")
        with self.session_factory.begin() as session:
            owned_state = "reconciling" if claim.kind == "reconcile" else "container_processing"
            row = self._owned(session, claim, now, owned_state)
            if not row.remote_container_id or row.remote_container_id != claim.remote_container_id:
                raise ValueError("container identity changed")
            # A publish whose outcome is unknown is never reissued just because
            # an observation still reports processing or ready.
            if claim.kind == "reconcile" and state != "published":
                row.state, row.error_message = "unknown_outcome", "publish outcome remains unknown; do not publish again"
            elif state == "processing":
                row.state, row.next_retry_at, row.error_message = "container_processing", retry_at, None
            elif state == "ready":
                row.state, row.next_retry_at, row.error_message = "container_ready", None, None
            elif state == "published":
                row.state, row.remote_id, row.remote_url, row.error_message = "verifying", remote_id, remote_url, None
            else:
                row.state, row.error_message = "failed", f"remote container {state} before publication"
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = state, row.error_message, now
            if remote_id:
                attempt.remote_id = remote_id
            self._refresh_parent(session, row.publish_job_id, now)

    def container_published(self, claim: DeliveryClaim, remote_id: str, *, remote_url: str | None = None, now: datetime | None = None) -> None:
        if claim.kind != "container_publish" or not remote_id:
            raise ValueError("container publication receipt is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "publishing")
            if not row.remote_container_id or row.remote_container_id != claim.remote_container_id:
                raise ValueError("container identity changed")
            row.state, row.remote_id, row.remote_url = "verifying", remote_id, remote_url
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.remote_id, attempt.state, attempt.finished_at = remote_id, "accepted", now
            self._refresh_parent(session, row.publish_job_id, now)

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

    def auth_required(self, claim: DeliveryClaim, reason: str, *, credential_ciphertext: str | None = None, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            owned_state = {"verify": "verifying", "container_check": "container_processing", "container_publish": "publishing"}.get(claim.kind, "uploading")
            row = self._owned(session, claim, now, owned_state)
            row.state, row.error_message = "auth_required", reason[:500]
            if credential_ciphertext is not None:
                account = session.get(SocialAccountRecord, claim.account_id)
                if (account is not None and account.credential_ciphertext == credential_ciphertext
                        and account.external_account_id == claim.external_account_id and account.status == "connected"):
                    account.status = "reconnect_required"
                    account.updated_at = now
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "auth_required", row.error_message, now
            self._refresh_parent(session, row.publish_job_id, now)

    def uncertain(self, claim: DeliveryClaim, reason: str, *, retry_at: datetime | None = None, now: datetime | None = None) -> None:
        """Stop automatic retries when a remote mutation may have occurred."""
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "publishing" if claim.kind == "container_publish" else "uploading")
            row.state, row.error_message = "unknown_outcome", reason[:500]
            row.next_retry_at = retry_at
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "unknown_outcome", reason[:500], now
            self._refresh_parent(session, row.publish_job_id, now)

    def quota_pause(self, claim: DeliveryClaim, reason: str, *, now: datetime | None = None) -> None:
        """Stop automatic work; saved sessions require inspection after resumption."""
        now = now or datetime.now(UTC)
        states = {"upload": "uploading", "verify": "verifying", "container_check": "container_processing"}
        if claim.kind not in states:
            raise ValueError("quota pause requires a pre-mutation or read-only claim")
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, states[claim.kind])
            if row.remote_id:
                resume_state = "verifying"
            elif claim.kind == "container_check" and row.remote_container_id:
                resume_state = "container_processing"
            elif row.remote_session_id:
                resume_state = "unknown_outcome"
            else:
                resume_state = "pending"
            row.state, row.paused_from_state, row.error_message, row.next_retry_at = "quota_paused", resume_state, reason[:500], None
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "quota_paused", row.error_message, now
            self._refresh_parent(session, row.publish_job_id, now)

    def mark_missed(self, claim: DeliveryClaim, *, now: datetime | None = None) -> None:
        """Fence a slot that crossed its grace period before a remote mutation."""
        if claim.kind not in {"upload", "container_publish"}:
            raise ValueError("upload or container-publish claim is required")
        now = now or datetime.now(UTC)
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "uploading" if claim.kind == "upload" else "publishing")
            if not row.scheduled_for or _utc(row.scheduled_for) + timedelta(minutes=30) >= now:
                raise ValueError("scheduled delivery is not beyond its grace period")
            if claim.kind == "upload" and row.remote_session_id:
                raise ValueError("started remote session requires reconciliation")
            row.state, row.error_message = "missed", "scheduled slot passed the 30-minute grace period"
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "missed", row.error_message, now
            self._refresh_parent(session, row.publish_job_id, now)

    def container_defer(self, claim: DeliveryClaim, reason: str, *, retry_at: datetime | None = None, fail: bool = False, now: datetime | None = None) -> None:
        """Release a container claim only while no publish mutation has begun."""
        if claim.kind not in {"container_check", "container_publish"}:
            raise ValueError("container claim is required")
        now = now or datetime.now(UTC)
        if not fail and (retry_at is None or retry_at <= now):
            raise ValueError("deferred container requires a future retry")
        with self.session_factory.begin() as session:
            row = self._owned(session, claim, now, "container_processing" if claim.kind == "container_check" else "publishing")
            row.state = "failed" if fail else "container_processing"
            row.next_retry_at = None if fail else retry_at
            row.error_message = reason[:500]
            self._release(row, now)
            attempt = self._attempt(session, claim)
            attempt.state, attempt.error_message, attempt.finished_at = "failed" if fail else "deferred", reason[:500], now
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
            if row.state in {"uploading", "publishing"}:
                action = "publish" if row.state == "publishing" else "upload"
                row.state, row.error_message = "unknown_outcome", f"{action} lease expired; reconcile before retry"
                if attempt is not None:
                    attempt.state, attempt.error_message, attempt.finished_at = "unknown_outcome", row.error_message, now
            elif row.state == "container_processing" and attempt is not None:
                attempt.state, attempt.error_message, attempt.finished_at = "interrupted", "container inspection lease expired", now
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
        elif all(state == "cancelled" for state in states):
            post.state = "cancelled"
        elif all(state == "missed" for state in states):
            post.state = "missed"
        elif "unknown_outcome" in states or "reconciling" in states or "quota_paused" in states:
            post.state = "attention_required"
        elif any(state in {"failed", "auth_required", "missed", "cancelled"} for state in states):
            post.state = "partial_failure"
        elif all(state == "paused" for state in states):
            post.state = "paused"
        elif "paused" in states:
            post.state = "partially_paused"
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
