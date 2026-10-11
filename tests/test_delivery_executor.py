"""An offline adapter proves upload receipts need remote verification."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base, DestinationDeliveryRecord, PublishJobRecord, PublishingAssetRecord, SocialAccountRecord
from tubeforge.db.session import create_database
from tubeforge.pipeline.delivery_executor import DeliveryExecutor, RemoteObservation, UploadReceipt
from tubeforge.pipeline.delivery_queue import DeliveryQueue
from tubeforge.pipeline.manual_publish import ManualPublishService
from tubeforge.security.account_credentials import AccountCredentialManager, RefreshedCredential
from tubeforge.security.secrets import TokenCipher


def _submit(draft: ManualPublishService, post_id: str) -> None:
    draft.submit(post_id, reviewed_identity=draft.review_identity(post_id), actor="operator", supported_platforms={"youtube"})


class OfflineYouTube:
    def __init__(self) -> None:
        self.opened = 0
        self.uploaded = 0
        self.observation = RemoteObservation("published", "UC-real", "Reviewed title", "Reviewed description", "https://example.invalid/watch/remote", "private")

    def open_session(self, *, external_account_id, credential, asset_path, metadata):
        assert external_account_id == "UC-real" and credential["refresh_token"] == "secret"
        assert asset_path.read_bytes() == b"known final video"
        self.opened += 1
        return "resumable-session-1"

    def upload(self, *, session_id, external_account_id, credential, asset_path, metadata, heartbeat):
        assert session_id == "resumable-session-1" and heartbeat()
        self.uploaded += 1
        return UploadReceipt("remote", "https://example.invalid/watch/remote")

    def inspect(self, *, remote_id, external_account_id, credential):
        assert remote_id == "remote" and external_account_id == "UC-real"
        return self.observation

    def inspect_session(self, *, session_id, credential, asset_size):
        assert session_id == "resumable-session-1" and asset_size == len(b"known final video")
        return UploadReceipt("remote", "https://example.invalid/watch/remote")

    def resume_session(self, *, session_id, credential, asset_path, heartbeat):
        assert session_id == "resumable-session-1" and asset_path.read_bytes() == b"known final video" and heartbeat()
        return UploadReceipt("remote", "https://example.invalid/watch/remote")


def test_executor_requires_matching_remote_observation_before_parent_success(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'executor.db'}"))
    Base.metadata.create_all(database.engine)
    stage_root = tmp_path / "staging"
    stage_root.mkdir()
    content = b"known final video"
    digest = hashlib.sha256(content).hexdigest()
    path = stage_root / f"{digest}.mp4"
    path.write_bytes(content)
    cipher = TokenCipher(Fernet.generate_key().decode())
    now = datetime.now(UTC)
    with database.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id="asset", sha256=digest, staged_path=str(path), source_job_id="job", size_bytes=len(content), duration_seconds=30, width=1080, height=1920, state="ready", created_at=now))
        session.add(SocialAccountRecord(id="yt", platform="youtube", display_name="Channel", external_account_id="UC-real", auth_type="oauth", credential_ciphertext=cipher.encrypt({"refresh_token": "secret", "token": "old"}), scopes_json="[]", token_expires_at=now - timedelta(minutes=1), status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    draft = ManualPublishService(database.session_factory)
    adapter = OfflineYouTube()
    manager = AccountCredentialManager(database.session_factory, cipher, {"youtube": lambda old: RefreshedCredential({**old, "token": "fresh"}, datetime.now(UTC) + timedelta(hours=1))})
    executor = DeliveryExecutor(database.session_factory, DeliveryQueue(database.session_factory), cipher, stage_root, {"youtube": adapter}, manager)
    try:
        post = draft.create_draft("asset", {"yt": {"title": "Reviewed title", "caption": "Reviewed description"}})
        _submit(draft, post.id)
        assert executor.run_once("worker") is not None
        with database.session_factory() as session:
            assert session.get(PublishJobRecord, post.id).state == "verifying"
            assert cipher.decrypt(session.get(SocialAccountRecord, "yt").credential_ciphertext)["token"] == "fresh"
            sealed_session = session.scalar(select(DestinationDeliveryRecord)).remote_session_id
            assert sealed_session != "resumable-session-1"
            assert cipher.decrypt(sealed_session)["session_id"] == "resumable-session-1"
        assert executor.run_once("worker") is not None
        with database.session_factory() as session:
            assert session.get(PublishJobRecord, post.id).state == "published"
            assert session.scalar(select(DestinationDeliveryRecord)).remote_id == "remote"
        assert executor.run_once("worker") is None
        assert (adapter.opened, adapter.uploaded) == (1, 1)
    finally:
        database.dispose()


def test_executor_rejects_changed_staged_bytes_before_remote_work(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'corrupt.db'}"))
    Base.metadata.create_all(database.engine)
    stage_root = tmp_path / "staging"
    stage_root.mkdir()
    digest = hashlib.sha256(b"original").hexdigest()
    path = stage_root / f"{digest}.mp4"
    path.write_bytes(b"changed!")
    cipher = TokenCipher(Fernet.generate_key().decode())
    now = datetime.now(UTC)
    with database.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id="asset", sha256=digest, staged_path=str(path), source_job_id="job", size_bytes=8, duration_seconds=30, width=1080, height=1920, state="ready", created_at=now))
        session.add(SocialAccountRecord(id="yt", platform="youtube", display_name="Channel", external_account_id="UC-real", auth_type="oauth", credential_ciphertext=cipher.encrypt({"refresh_token": "secret"}), scopes_json="[]", token_expires_at=None, status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    draft = ManualPublishService(database.session_factory)
    adapter = OfflineYouTube()
    executor = DeliveryExecutor(database.session_factory, DeliveryQueue(database.session_factory), cipher, stage_root, {"youtube": adapter})
    try:
        post = draft.create_draft("asset", {"yt": {"title": "Reviewed title", "caption": "Reviewed description"}})
        _submit(draft, post.id)
        assert executor.run_once("worker") is not None
        with database.session_factory() as session:
            assert session.get(PublishJobRecord, post.id).state == "partial_failure"
        assert adapter.opened == 0
    finally:
        database.dispose()


def test_ambiguous_upload_stays_blocked_for_reconciliation(tmp_path: Path) -> None:
    class TimedOutUpload(OfflineYouTube):
        def upload(self, **kwargs):
            self.uploaded += 1
            raise TimeoutError("the provider may have accepted the bytes")

    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'timeout.db'}"))
    Base.metadata.create_all(database.engine)
    stage_root = tmp_path / "staging"
    stage_root.mkdir()
    content = b"known final video"
    digest = hashlib.sha256(content).hexdigest()
    path = stage_root / f"{digest}.mp4"
    path.write_bytes(content)
    cipher = TokenCipher(Fernet.generate_key().decode())
    now = datetime.now(UTC)
    with database.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id="asset", sha256=digest, staged_path=str(path), source_job_id="job", size_bytes=len(content), duration_seconds=30, width=1080, height=1920, state="ready", created_at=now))
        session.add(SocialAccountRecord(id="yt", platform="youtube", display_name="Channel", external_account_id="UC-real", auth_type="oauth", credential_ciphertext=cipher.encrypt({"refresh_token": "secret"}), scopes_json="[]", token_expires_at=None, status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    draft = ManualPublishService(database.session_factory)
    adapter = TimedOutUpload()
    executor = DeliveryExecutor(database.session_factory, DeliveryQueue(database.session_factory), cipher, stage_root, {"youtube": adapter})
    try:
        post = draft.create_draft("asset", {"yt": {"title": "Reviewed title", "caption": "Reviewed description"}})
        _submit(draft, post.id)
        assert executor.run_once("worker") is not None
        assert executor.run_once("worker") is None
        with database.session_factory() as session:
            assert session.get(PublishJobRecord, post.id).state == "attention_required"
            assert session.scalar(select(DestinationDeliveryRecord)).state == "unknown_outcome"
        delivery_id = draft.deliveries(post.id)[0].id
        with pytest.raises(ValueError, match="inspect the saved"):
            executor.queue.request_action(delivery_id, "resume", "operator")
        executor.queue.request_action(delivery_id, "inspect", "operator")
        with pytest.raises(ValueError, match="already pending"):
            executor.queue.request_action(delivery_id, "inspect", "operator")
        assert executor.run_requested_action("reconciler") == delivery_id
        assert executor.run_requested_action("reconciler") is None
        with database.session_factory() as session:
            assert session.scalar(select(DestinationDeliveryRecord)).state == "verifying"
        assert executor.run_once("worker") is not None
        with database.session_factory() as session:
            assert session.get(PublishJobRecord, post.id).state == "published"
        assert adapter.opened == adapter.uploaded == 1
    finally:
        database.dispose()


def test_explicit_resume_uses_saved_session_without_reopening_upload(tmp_path: Path) -> None:
    class InterruptedUpload(OfflineYouTube):
        def upload(self, **kwargs):
            self.uploaded += 1
            raise TimeoutError("the provider received some bytes")

        def inspect_session(self, **kwargs):
            return None

        def resume_session(self, **kwargs):
            self.resumed += 1
            return super().resume_session(**kwargs)

    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'resume.db'}"))
    Base.metadata.create_all(database.engine)
    stage_root = tmp_path / "staging"
    stage_root.mkdir()
    content = b"known final video"
    digest = hashlib.sha256(content).hexdigest()
    path = stage_root / f"{digest}.mp4"
    path.write_bytes(content)
    cipher = TokenCipher(Fernet.generate_key().decode())
    now = datetime.now(UTC)
    with database.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id="asset", sha256=digest, staged_path=str(path), source_job_id="job", size_bytes=len(content), duration_seconds=30, width=1080, height=1920, state="ready", created_at=now))
        session.add(SocialAccountRecord(id="yt", platform="youtube", display_name="Channel", external_account_id="UC-real", auth_type="oauth", credential_ciphertext=cipher.encrypt({"refresh_token": "secret"}), scopes_json="[]", token_expires_at=None, status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    draft = ManualPublishService(database.session_factory)
    adapter = InterruptedUpload()
    adapter.resumed = 0
    executor = DeliveryExecutor(database.session_factory, DeliveryQueue(database.session_factory), cipher, stage_root, {"youtube": adapter})
    try:
        post = draft.create_draft("asset", {"yt": {"title": "Reviewed title", "caption": "Reviewed description"}})
        delivery_id = draft.deliveries(post.id)[0].id
        _submit(draft, post.id)
        executor.run_once("worker")
        assert executor.run_once("worker") is None
        executor.queue.request_action(delivery_id, "inspect", "operator")
        assert executor.run_requested_action("reconciler") == delivery_id
        with database.session_factory() as session:
            assert session.get(DestinationDeliveryRecord, delivery_id).state == "unknown_outcome"
        executor.queue.request_action(delivery_id, "resume", "operator")
        assert executor.run_requested_action("reconciler") == delivery_id
        executor.run_once("worker")
        with database.session_factory() as session:
            assert session.get(PublishJobRecord, post.id).state == "published"
        assert (adapter.opened, adapter.uploaded, adapter.resumed) == (1, 1, 1)
    finally:
        database.dispose()
