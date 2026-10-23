"""Manual drafts reserve exact canonical content and destination identities."""
from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from tubeforge.db.models import DestinationDeliveryRecord, PublishJobRecord, PublishingAssetRecord, SocialAccountRecord


class ManualPublishService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def create_draft(self, asset_id: str, destination_metadata: dict[str, dict[str, object]]) -> PublishJobRecord:
        if not destination_metadata:
            raise ValueError("select at least one destination")
        now = datetime.now(UTC)
        post_id = uuid4().hex
        try:
            with self.session_factory.begin() as session:
                asset = session.get(PublishingAssetRecord, asset_id)
                if asset is None or asset.state not in {"ready", "reserved"}:
                    raise ValueError("canonical video is not available for publishing")
                post = PublishJobRecord(
                    id=post_id, asset_id=asset.id, source="manual", edition=0,
                    state="draft", metadata_json=json.dumps({"source_job_id": asset.source_job_id, "sha256": asset.sha256}, sort_keys=True),
                    scheduled_at=None, created_at=now, updated_at=now,
                )
                session.add(post)
                for account_id, metadata in destination_metadata.items():
                    account = session.get(SocialAccountRecord, account_id)
                    if account is None or account.disabled or account.status != "connected" or account.last_validated_at is None or not account.external_account_id or not account.credential_ciphertext:
                        raise ValueError(f"destination account is not verified: {account_id}")
                    if account.platform not in {"youtube", "instagram"}:
                        raise ValueError("destination platform does not support publishing")
                    self._validate_metadata(account.platform, metadata)
                    session.add(DestinationDeliveryRecord(
                        id=uuid4().hex, publish_job_id=post_id, asset_id=asset.id,
                        account_id=account.id, platform=account.platform,
                        external_account_id=account.external_account_id, edition=0,
                        state="draft", required=True, metadata_json=json.dumps(metadata, sort_keys=True),
                        remote_id=None, remote_url=None, remote_session_id=None,
                        attempt_count=0, error_message=None, created_at=now, updated_at=now,
                    ))
                asset.state = "reserved"
                session.flush()
                return post
        except IntegrityError as error:
            raise ValueError("this video is already reserved for a selected destination") from error

    def deliveries(self, post_id: str) -> list[DestinationDeliveryRecord]:
        with self.session_factory() as session:
            return list(session.scalars(select(DestinationDeliveryRecord).where(DestinationDeliveryRecord.publish_job_id == post_id).order_by(DestinationDeliveryRecord.account_id)))

    def review_identity(self, post_id: str) -> str:
        with self.session_factory() as session:
            post = session.get(PublishJobRecord, post_id)
            if post is None:
                raise KeyError(post_id)
            asset = session.get(PublishingAssetRecord, post.asset_id)
            deliveries = list(session.scalars(select(DestinationDeliveryRecord).where(DestinationDeliveryRecord.publish_job_id == post_id)))
            if asset is None or not deliveries:
                raise ValueError("publish draft is incomplete")
            return self._review_identity(asset, deliveries)

    def submit(self, post_id: str, *, reviewed_identity: str, actor: str, supported_platforms: set[str]) -> PublishJobRecord:
        """Queue the exact reviewed artifact and destination snapshots atomically."""
        if not actor or len(actor) > 64 or not supported_platforms:
            raise ValueError("operator and live destination worker are required")
        now = datetime.now(UTC)
        with self.session_factory.begin() as session:
            post = session.get(PublishJobRecord, post_id)
            if post is None:
                raise KeyError(post_id)
            if post.state != "draft":
                raise ValueError("only a draft can be submitted")
            asset = session.get(PublishingAssetRecord, post.asset_id)
            if asset is None or asset.state != "reserved":
                raise ValueError("canonical video is no longer reserved")
            deliveries = list(session.scalars(select(DestinationDeliveryRecord).where(DestinationDeliveryRecord.publish_job_id == post_id)))
            if not deliveries:
                raise ValueError("draft has no destinations")
            if reviewed_identity != self._review_identity(asset, deliveries):
                raise ValueError("reviewed video or destination details changed; review the draft again")
            for delivery in deliveries:
                if delivery.platform not in supported_platforms:
                    raise ValueError("selected destination has no live publisher worker")
                if delivery.platform != "youtube" or json.loads(delivery.metadata_json).get("visibility", "private") != "private":
                    raise ValueError("manual submission currently supports private YouTube posts only")
                account = session.get(SocialAccountRecord, delivery.account_id)
                if account is None or account.disabled or account.status != "connected" or account.last_validated_at is None or not account.credential_ciphertext or account.external_account_id != delivery.external_account_id:
                    raise ValueError("destination account needs reconnection before submission")
                if delivery.state != "draft":
                    raise ValueError("destination is no longer a draft")
                delivery.state = "pending"
                delivery.updated_at = now
            post.state = "queued"
            post.reviewed_identity = reviewed_identity
            post.submitted_at = now
            post.submitted_by = actor
            post.updated_at = now
            session.flush()
            return post

    @staticmethod
    def _review_identity(asset: PublishingAssetRecord, deliveries: list[DestinationDeliveryRecord]) -> str:
        document = {
            "asset_sha256": asset.sha256,
            "destinations": [
                {"account_id": item.account_id, "external_account_id": item.external_account_id,
                 "platform": item.platform, "edition": item.edition,
                 "metadata": json.loads(item.metadata_json)}
                for item in sorted(deliveries, key=lambda item: item.account_id)
            ],
        }
        return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def list_recent(self, *, limit: int = 50) -> list[PublishJobRecord]:
        with self.session_factory() as session:
            return list(session.scalars(select(PublishJobRecord).order_by(PublishJobRecord.created_at.desc(), PublishJobRecord.id.desc()).limit(limit)))

    @staticmethod
    def _validate_metadata(platform: str, metadata: dict[str, object]) -> None:
        allowed = {"caption", "title", "tags", "hashtags", "visibility", "thumbnail_sha256"} if platform == "youtube" else {"caption", "hashtags"}
        if set(metadata) - allowed:
            raise ValueError("unsupported destination metadata field")
        caption = metadata.get("caption")
        if not isinstance(caption, str) or not caption.strip():
            raise ValueError("destination caption is required")
        if platform == "youtube" and (len(caption.encode("utf-8")) > 5_000 or "<" in caption or ">" in caption):
            raise ValueError("YouTube description must be at most 5000 UTF-8 bytes and omit angle brackets")
        if platform == "instagram" and len(caption) > 2_200:
            raise ValueError("Instagram caption must be at most 2200 characters")
        hashtags = metadata.get("hashtags", [])
        if not isinstance(hashtags, list) or len(hashtags) > 30 or any(not isinstance(tag, str) or not tag.startswith("#") or len(tag) < 2 for tag in hashtags):
            raise ValueError("hashtags must be a list of up to 30 nonempty #tags")
        thumbnail = metadata.get("thumbnail_sha256")
        if thumbnail is not None and (platform != "youtube" or not isinstance(thumbnail, str) or len(thumbnail) != 64 or any(c not in "0123456789abcdef" for c in thumbnail)):
            raise ValueError("thumbnail reference is invalid")
        if platform == "youtube":
            if metadata.get("visibility", "private") not in {"private", "unlisted", "public"}:
                raise ValueError("YouTube visibility is invalid")
            title = metadata.get("title")
            if not isinstance(title, str) or not title.strip() or len(title) > 100 or "<" in title or ">" in title:
                raise ValueError("YouTube title is required, at most 100 characters, and must omit angle brackets")
            tags = metadata.get("tags", [])
            if not isinstance(tags, list) or len(tags) > 30 or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
                raise ValueError("YouTube keyword tags must be a list of nonempty strings")
