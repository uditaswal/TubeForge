"""Manual drafts freeze exact account and metadata snapshots before dispatch."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base, PublishJobRecord, PublishingAssetRecord, SocialAccountRecord
from tubeforge.db.session import create_database
from tubeforge.pipeline.manual_publish import ManualPublishService


def test_manual_draft_reserves_exact_accounts_and_excludes_default_duplicate(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'draft.db'}"))
    Base.metadata.create_all(database.engine)
    now = datetime.now(UTC)
    with database.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id="asset", sha256="a" * 64, staged_path=str(tmp_path / "asset.mp4"), source_job_id="job", size_bytes=42, duration_seconds=30, width=1080, height=1920, state="ready", created_at=now))
        for account_id, platform, remote_id in (("yt", "youtube", "UC-real"), ("ig", "instagram", "ig-real")):
            session.add(SocialAccountRecord(id=account_id, platform=platform, display_name=account_id, external_account_id=remote_id, auth_type="oauth", credential_ciphertext="encrypted", scopes_json="[]", token_expires_at=None, status="connected", capabilities_json='["upload_video"]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    service = ManualPublishService(database.session_factory)
    metadata = {
        "yt": {"title": "The title", "caption": "A sourced description", "tags": ["science"]},
        "ig": {"caption": "A short hook #science", "hashtags": ["#science"]},
    }
    try:
        post = service.create_draft("asset", metadata)
        assert post.state == "draft" and post.source == "manual" and post.edition == 0
        metadata["yt"]["title"] = "Changed after save"
        deliveries = service.deliveries(post.id)
        assert [(item.account_id, item.external_account_id, item.state) for item in deliveries] == [("ig", "ig-real", "draft"), ("yt", "UC-real", "draft")]
        assert json.loads(deliveries[1].metadata_json)["title"] == "The title"
        with database.session_factory() as session:
            assert session.get(PublishingAssetRecord, "asset").state == "reserved"
        with pytest.raises(ValueError, match="already reserved"):
            service.create_draft("asset", {"yt": {"title": "Again", "caption": "Again"}})
        with pytest.raises(ValueError, match="unsupported destination metadata"):
            service.create_draft("asset", {"ig": {"caption": "Hi", "access_token": "never store"}})
        with database.session_factory() as session:
            assert len(list(session.scalars(select(PublishJobRecord)))) == 1
    finally:
        database.dispose()
