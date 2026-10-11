"""Fenced destination claims never turn an uncertain upload into a duplicate."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base, DeliveryAttemptRecord, DestinationDeliveryRecord, PublishJobRecord, PublishingAssetRecord, SocialAccountRecord
from tubeforge.db.session import create_database
from tubeforge.pipeline.delivery_queue import DeliveryQueue
from tubeforge.pipeline.manual_publish import ManualPublishService


def test_delivery_claims_are_fenced_and_parent_waits_for_each_remote_receipt(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'deliveries.db'}"))
    Base.metadata.create_all(database.engine)
    now = datetime.now(UTC)
    with database.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id="asset", sha256="a" * 64, staged_path=str(tmp_path / "asset.mp4"), source_job_id="job", size_bytes=42, duration_seconds=30, width=1080, height=1920, state="ready", created_at=now))
        for account_id, platform, remote_id in (("yt", "youtube", "UC-one"), ("ig", "instagram", "ig-one")):
            session.add(SocialAccountRecord(id=account_id, platform=platform, display_name=account_id, external_account_id=remote_id, auth_type="oauth", credential_ciphertext="encrypted", scopes_json="[]", token_expires_at=None, status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    drafts = ManualPublishService(database.session_factory)
    queue = DeliveryQueue(database.session_factory)
    try:
        post = drafts.create_draft("asset", {"yt": {"title": "Title", "caption": "Description"}, "ig": {"caption": "Caption"}})
        with database.session_factory.begin() as session:
            session.get(PublishJobRecord, post.id).state = "queued"
            for delivery in session.scalars(select(DestinationDeliveryRecord).where(DestinationDeliveryRecord.publish_job_id == post.id)):
                delivery.state = "pending"
        claim1 = queue.claim_next("worker-a", platforms={"youtube"}, now=now + timedelta(seconds=1), lease_seconds=10)
        assert claim1 is not None and claim1.kind == "upload" and claim1.platform == "youtube"
        claim2 = queue.claim_next("worker-b", platforms={"instagram"}, now=now + timedelta(seconds=1), lease_seconds=10)
        assert claim2 is not None and claim2.platform == "instagram" and claim2.delivery_id != claim1.delivery_id
        assert queue.claim_next("worker-c", now=now + timedelta(seconds=1)) is None
        queue.record_session(claim1, "session-1", now=now + timedelta(seconds=2))
        queue.upload_accepted(claim1, "remote-1", now=now + timedelta(seconds=3))
        with pytest.raises(ValueError, match="ownership was lost"):
            queue.uncertain(claim1, "late timeout", now=now + timedelta(seconds=4))
        # The second upload's expired lease is never returned to the upload queue.
        verify1 = queue.claim_next("worker-c", now=now + timedelta(seconds=12))
        assert verify1 is not None and verify1.kind == "verify" and verify1.delivery_id == claim1.delivery_id
        queue.verification_pending(verify1, retry_at=now + timedelta(seconds=20), now=now + timedelta(seconds=13))
        assert queue.claim_next("worker-d", now=now + timedelta(seconds=14)) is None
        verify2 = queue.claim_next("worker-d", now=now + timedelta(seconds=20))
        assert verify2 is not None and verify2.kind == "verify" and verify2.delivery_id == claim1.delivery_id
        queue.verified_published(verify2, remote_url="https://example.invalid/post/1", now=now + timedelta(seconds=21))
        assert queue.claim_next("worker-e", now=now + timedelta(seconds=22)) is None
        with database.session_factory() as session:
            rows = list(session.scalars(select(DestinationDeliveryRecord).order_by(DestinationDeliveryRecord.id)))
            assert sorted(row.state for row in rows) == ["published", "unknown_outcome"]
            assert session.get(PublishJobRecord, post.id).state == "attention_required"
            attempts = list(session.scalars(select(DeliveryAttemptRecord)))
            assert sorted(item.state for item in attempts) == ["accepted", "processing", "unknown_outcome", "verified"]
            assert next(item for item in rows if item.state == "published").remote_session_id == "session-1"
    finally:
        database.dispose()


def test_submit_rechecks_frozen_account_identity(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'identity.db'}"))
    Base.metadata.create_all(database.engine)
    now = datetime.now(UTC)
    with database.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id="asset", sha256="a" * 64, staged_path=str(tmp_path / "asset.mp4"), source_job_id="job", size_bytes=42, duration_seconds=30, width=1080, height=1920, state="ready", created_at=now))
        session.add(SocialAccountRecord(id="yt", platform="youtube", display_name="One", external_account_id="UC-one", auth_type="oauth", credential_ciphertext="encrypted", scopes_json="[]", token_expires_at=None, status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    drafts = ManualPublishService(database.session_factory)
    try:
        post = drafts.create_draft("asset", {"yt": {"title": "Title", "caption": "Description"}})
        with pytest.raises(ValueError, match="reviewed video"):
            drafts.submit(post.id, reviewed_identity="0" * 64, actor="operator", supported_platforms={"youtube"})
        with database.session_factory.begin() as session:
            session.get(SocialAccountRecord, "yt").external_account_id = "UC-changed"
        with pytest.raises(ValueError, match="reconnection"):
            drafts.submit(post.id, reviewed_identity=drafts.review_identity(post.id), actor="operator", supported_platforms={"youtube"})
        with database.session_factory() as session:
            assert session.get(PublishJobRecord, post.id).state == "draft"
    finally:
        database.dispose()


def test_same_account_is_claimed_by_only_one_worker_at_a_time(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'serial.db'}"))
    Base.metadata.create_all(database.engine)
    now = datetime.now(UTC)
    with database.session_factory.begin() as session:
        for index in (1, 2):
            session.add(PublishingAssetRecord(id=f"asset-{index}", sha256=str(index) * 64, staged_path=str(tmp_path / f"{index}.mp4"), source_job_id=f"job-{index}", size_bytes=42, duration_seconds=30, width=1080, height=1920, state="ready", created_at=now))
        session.add(SocialAccountRecord(id="yt", platform="youtube", display_name="One", external_account_id="UC-one", auth_type="oauth", credential_ciphertext="encrypted", scopes_json="[]", token_expires_at=None, status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    drafts = ManualPublishService(database.session_factory)
    queue = DeliveryQueue(database.session_factory)
    try:
        for index in (1, 2):
            post = drafts.create_draft(f"asset-{index}", {"yt": {"title": f"Title {index}", "caption": "Description"}})
            drafts.submit(post.id, reviewed_identity=drafts.review_identity(post.id), actor="operator", supported_platforms={"youtube"})
        first = queue.claim_next("worker-a", now=now + timedelta(seconds=1))
        assert first is not None
        assert queue.claim_next("worker-b", now=now + timedelta(seconds=2)) is None
        queue.record_session(first, "session", now=now + timedelta(seconds=3))
        queue.upload_accepted(first, "remote", now=now + timedelta(seconds=4))
        verify = queue.claim_next("worker-b", now=now + timedelta(seconds=5))
        assert verify is not None and verify.kind == "verify" and verify.delivery_id == first.delivery_id
        assert queue.claim_next("worker-c", now=now + timedelta(seconds=6)) is None
        queue.verified_published(verify, now=now + timedelta(seconds=7))
        second = queue.claim_next("worker-c", now=now + timedelta(seconds=8))
        assert second is not None and second.kind == "upload" and second.delivery_id != first.delivery_id
    finally:
        database.dispose()


def test_reconnect_retry_preserves_remote_outcome_boundary(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'reconnect.db'}"))
    Base.metadata.create_all(database.engine)
    now = datetime.now(UTC)
    with database.session_factory.begin() as session:
        session.add(SocialAccountRecord(id="yt", platform="youtube", display_name="Channel", external_account_id="UC-one", auth_type="oauth", credential_ciphertext="encrypted", scopes_json="[]", token_expires_at=None, status="reconnect_required", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
        for index, remote_id, remote_session in ((1, None, None), (2, "remote-2", None), (3, None, "sealed-session")):
            session.add(PublishJobRecord(id=f"post-{index}", asset_id=f"asset-{index}", source="manual", edition=0, state="attention_required", metadata_json="{}", created_at=now, updated_at=now))
            session.add(DestinationDeliveryRecord(id=f"delivery-{index}", publish_job_id=f"post-{index}", asset_id=f"asset-{index}", account_id="yt", platform="youtube", external_account_id="UC-one", edition=0, state="auth_required", required=True, metadata_json='{"title":"Title","caption":"Description"}', remote_id=remote_id, remote_session_id=remote_session, requested_action="inspect" if index == 3 else None, attempt_count=1, error_message="destination account needs reconnection", created_at=now, updated_at=now))
    queue = DeliveryQueue(database.session_factory)
    try:
        with pytest.raises(ValueError, match="reconnect the exact"):
            queue.retry_after_reconnect("delivery-1", "operator")
        with database.session_factory.begin() as session:
            session.get(SocialAccountRecord, "yt").status = "connected"
        assert queue.retry_after_reconnect("delivery-1", "operator") == "pending"
        assert queue.retry_after_reconnect("delivery-2", "operator") == "verifying"
        assert queue.retry_after_reconnect("delivery-3", "operator") == "unknown_outcome"
        with database.session_factory() as session:
            assert session.get(DestinationDeliveryRecord, "delivery-3").remote_session_id == "sealed-session"
            assert session.get(DestinationDeliveryRecord, "delivery-3").error_message.startswith("account reconnected; inspect")
            assert session.get(DestinationDeliveryRecord, "delivery-3").requested_action is None
            assert len(list(session.scalars(select(DeliveryAttemptRecord).where(DeliveryAttemptRecord.kind == "requeue")))) == 3
        with pytest.raises(ValueError, match="only an unclaimed"):
            queue.retry_after_reconnect("delivery-1", "operator")
    finally:
        database.dispose()
