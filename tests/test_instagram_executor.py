"""The real Instagram adapter, driven by the real executor and queue over a fake transport."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from sqlalchemy import select

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base, DestinationDeliveryRecord, PublishJobRecord, PublishingAssetRecord, SocialAccountRecord
from tubeforge.db.session import create_database
from tubeforge.pipeline.delivery_executor import DeliveryExecutor
from tubeforge.pipeline.delivery_queue import DeliveryQueue
from tubeforge.pipeline.manual_publish import ManualPublishService
from tubeforge.providers.publishing.account_instagram import AccountInstagramAdapter, instagram_full_caption
from tubeforge.security.secrets import TokenCipher

URI = "https://rupload.facebook.com/ig-api-upload/v21.0/container-1"
META = {"caption": "Reviewed hook", "hashtags": ["#sec"], "confirm_public": True}


class Remote:
    def __init__(self, publish_ok: bool = True) -> None:
        self.publish_ok, self.state, self.calls = publish_ok, "FINISHED", []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {path.rsplit('/', 1)[-1]}")
        if request.url.host == "rupload.facebook.com":
            return httpx.Response(200, json={"success": True, "file_offset": 17})
        if path.endswith("/me"):
            return httpx.Response(200, json={"user_id": "1784"})
        if path.endswith("/content_publishing_limit"):
            return httpx.Response(200, json={"data": [{"quota_usage": 1, "config": {"quota_total": 100}}]})
        if path.endswith("/1784/media"):
            return httpx.Response(200, json={"id": "container-1", "uri": URI})
        if path.endswith("/media_publish"):
            return httpx.Response(200, json={"id": "media-9"}) if self.publish_ok else httpx.Response(500)
        if path.endswith("/container-1"):
            return httpx.Response(200, json={"status_code": self.state})
        return httpx.Response(200, json={"id": "media-9", "permalink": "https://www.instagram.com/reel/x/", "caption": instagram_full_caption(META), "owner": {"id": "1784"}})


def _setup(tmp_path: Path, remote: Remote):
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'ig.db'}"))
    Base.metadata.create_all(database.engine)
    stage = tmp_path / "staging"
    stage.mkdir()
    content = b"known final video"
    digest = hashlib.sha256(content).hexdigest()
    path = stage / f"{digest}.mp4"
    path.write_bytes(content)
    cipher = TokenCipher(Fernet.generate_key().decode())
    now = datetime.now(UTC)
    with database.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id="asset", sha256=digest, staged_path=str(path), source_job_id="job", size_bytes=len(content), duration_seconds=30, width=1080, height=1920, state="ready", created_at=now))
        session.add(SocialAccountRecord(id="ig", platform="instagram", display_name="@x", external_account_id="1784", auth_type="oauth", credential_ciphertext=cipher.encrypt({"token": "tok", "token_type": "instagram_long_lived"}), scopes_json="[]", token_expires_at=None, status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    adapter = AccountInstagramAdapter(httpx.Client(transport=httpx.MockTransport(remote)), poll_seconds=0, sleep=lambda _: None)
    executor = DeliveryExecutor(database.session_factory, DeliveryQueue(database.session_factory), cipher, stage, {"instagram": adapter})
    draft = ManualPublishService(database.session_factory)
    post = draft.create_draft("asset", {"ig": dict(META)})
    draft.submit(post.id, reviewed_identity=draft.review_identity(post.id), actor="operator", supported_platforms={"instagram"}, confirmed_public_accounts=frozenset({"ig"}))
    return database, executor, draft, post, cipher


def test_legacy_instagram_adapter_is_refused_before_any_remote_call(tmp_path: Path) -> None:
    remote = Remote()
    database, executor, draft, post, _ = _setup(tmp_path, remote)
    try:
        assert executor.run_once("worker") is not None
        with database.session_factory() as session:
            row = session.scalar(select(DestinationDeliveryRecord))
            assert row.state == "failed"
            assert "separate container" in row.error_message
        assert remote.calls == []
    finally:
        database.dispose()
