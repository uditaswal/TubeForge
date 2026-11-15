"""Durable, conservative YouTube upload budget with atomic reservations."""
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.db.models import DestinationDeliveryRecord, YouTubeQuotaChargeRecord
from tubeforge.pipeline.delivery_queue import DeliveryClaim


class YouTubeQuotaExhausted(ValueError):
    pass


class YouTubeQuotaLedger:
    def __init__(self, sessions: sessionmaker[Session], *, daily_units: int = 10_000, upload_units: int = 1_600):
        if daily_units <= 0 or upload_units <= 0:
            raise ValueError("YouTube quota settings must be positive")
        self.sessions, self.daily_units, self.upload_units = sessions, daily_units, upload_units

    @staticmethod
    def _day(now: datetime) -> str:
        if now.tzinfo is None:
            raise ValueError("quota clock must be timezone aware")
        return now.astimezone(ZoneInfo("America/Los_Angeles")).date().isoformat()

    def status(self, *, now: datetime | None = None) -> dict[str, object]:
        now = now or datetime.now(UTC)
        day = self._day(now)
        with self.sessions() as session:
            used = session.scalar(select(func.coalesce(func.sum(YouTubeQuotaChargeRecord.units), 0)).where(YouTubeQuotaChargeRecord.quota_day == day))
        return {"day": day, "daily_units": self.daily_units, "reserved_units": int(used), "remaining_units": max(0, self.daily_units - int(used)), "upload_units": self.upload_units}

    def reserve(self, claim: DeliveryClaim, *, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        day = self._day(now)
        if claim.platform != "youtube" or claim.kind != "upload":
            raise ValueError("YouTube upload claim is required")
        with self.sessions() as session:
            # SQLite write lock serializes the cap check and insert across workers.
            session.execute(text("BEGIN IMMEDIATE"))
            row = session.get(DestinationDeliveryRecord, claim.delivery_id)
            if (row is None or row.state != "uploading" or row.claim_owner != claim.owner
                    or row.claim_token != claim.token or row.lease_expires_at is None
                    or row.lease_expires_at.replace(tzinfo=UTC) <= now or row.remote_session_id):
                raise ValueError("delivery lease is no longer owned for quota reservation")
            existing = session.scalar(select(YouTubeQuotaChargeRecord).where(
                YouTubeQuotaChargeRecord.quota_day == day, YouTubeQuotaChargeRecord.delivery_id == claim.delivery_id,
            ))
            prior = existing.units if existing is not None else 0
            additional = max(0, self.upload_units - prior)
            if additional:
                used = int(session.scalar(select(func.coalesce(func.sum(YouTubeQuotaChargeRecord.units), 0)).where(YouTubeQuotaChargeRecord.quota_day == day)))
                if used + additional > self.daily_units:
                    raise YouTubeQuotaExhausted(f"YouTube daily upload budget exhausted: {max(0, self.daily_units - used)} units left, {additional} additional units required")
                if existing is None:
                    session.add(YouTubeQuotaChargeRecord(id=uuid4().hex, quota_day=day, delivery_id=claim.delivery_id, units=self.upload_units, created_at=now))
                else:
                    existing.units = self.upload_units
            session.commit()
