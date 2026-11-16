"""Seven simulated days: three reviewed posts per day across two fake platforms."""
from collections import Counter
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path
import json
import os

from cryptography.fernet import Fernet
from sqlalchemy import select

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base, DestinationDeliveryRecord, PublishJobRecord, PublishingAssetRecord, SocialAccountRecord
from tubeforge.db.session import create_database
from tubeforge.pipeline.delivery_executor import ContainerObservation, ContainerReceipt, DeliveryExecutor, RemoteObservation, RemoteSession, UploadReceipt
from tubeforge.pipeline.delivery_queue import DeliveryQueue
from tubeforge.security.secrets import TokenCipher


def test_seven_day_fake_publishing_soak_has_no_duplicates_or_lost_posts(tmp_path: Path, monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)
    monkeypatch.setattr('tubeforge.pipeline.delivery_executor.datetime', Clock)
    monkeypatch.setattr('tubeforge.pipeline.delivery_queue.datetime', Clock)
    monkeypatch.setattr('tubeforge.pipeline.youtube_quota.datetime', Clock)
    db = create_database(DatabaseConfig(url=f'sqlite:///{tmp_path / "soak.db"}'))
    Base.metadata.create_all(db.engine)
    stage = tmp_path / 'staging'
    stage.mkdir()
    cipher = TokenCipher(Fernet.generate_key().decode())
    with db.session_factory.begin() as session:
        for account_id, platform, external in [('yt', 'youtube', 'UC-fake'), ('ig', 'instagram', 'ig-fake')]:
            session.add(SocialAccountRecord(id=account_id, platform=platform, display_name=account_id, external_account_id=external, auth_type='oauth', credential_ciphertext=cipher.encrypt({'token': 'fake'}), scopes_json='[]', token_expires_at=None, status='connected', capabilities_json='[]', is_default=False, disabled=False, last_validated_at=Clock.current, created_at=Clock.current, updated_at=Clock.current))
    class Credentials:
        def resolve(self, account_id, owner):
            return {'token': 'fake'}
    class YouTube:
        youtube_api_audited = False
        def __init__(self):
            self.opens = Counter()
            self.uploads = Counter()
            self.posts = {}
        def open_session(self, *, metadata, **kwargs):
            key = metadata['title']
            self.opens[key] += 1
            return f'session-{key}'
        def upload(self, *, metadata, heartbeat, **kwargs):
            assert heartbeat()
            key = metadata['title']
            self.uploads[key] += 1
            assert self.uploads[key] == 1
            self.posts['yt-' + key] = (key, metadata['caption'])
            return UploadReceipt('yt-' + key)
        def inspect(self, *, remote_id, **kwargs):
            title, caption = self.posts[remote_id]
            return RemoteObservation('published', 'UC-fake', title, caption, privacy='private')
    class Instagram:
        def __init__(self):
            self.opens = Counter()
            self.uploads = Counter()
            self.publishes = Counter()
            self.containers = {}
            self.posts = {}
        def open_session(self, *, metadata, **kwargs):
            assert metadata['confirm_public'] is True
            key = metadata['caption']
            self.opens[key] += 1
            return RemoteSession('ig-' + key, Clock.now(UTC) + timedelta(hours=24))
        def upload(self, *, session_id, metadata, heartbeat, **kwargs):
            assert heartbeat()
            self.uploads[session_id] += 1
            assert self.uploads[session_id] == 1
            self.containers[session_id] = metadata['caption']
            return ContainerReceipt(session_id)
        def inspect_container(self, **kwargs):
            return ContainerObservation('ready')
        def publish_container(self, *, container_id, heartbeat, **kwargs):
            assert heartbeat()
            self.publishes[container_id] += 1
            assert self.publishes[container_id] == 1
            self.posts['media-' + container_id] = self.containers[container_id]
            return UploadReceipt('media-' + container_id)
        def inspect(self, *, remote_id, **kwargs):
            return RemoteObservation('published', 'ig-fake', caption=self.posts[remote_id])
    youtube, instagram = YouTube(), Instagram()
    executor = DeliveryExecutor(db.session_factory, DeliveryQueue(db.session_factory), cipher, stage, {'youtube': youtube, 'instagram': instagram}, Credentials())
    def drain():
        for _ in range(200):
            if executor.run_once('soak-worker') is None:
                return
        raise AssertionError('worker did not reach idle')
    try:
        first_day = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
        for day in range(7):
            Clock.current = first_day + timedelta(days=day)
            with db.session_factory.begin() as session:
                for index in range(3):
                    key = f'day-{day}-post-{index}'
                    content = key.encode()
                    digest = hashlib.sha256(content).hexdigest()
                    path = stage / f'{digest}.mp4'
                    path.write_bytes(content)
                    slot = Clock.current + timedelta(hours=7 + index * 3, minutes=30)
                    session.add(PublishingAssetRecord(id='asset-' + key, sha256=digest, staged_path=str(path), source_job_id='job-' + key, size_bytes=len(content), duration_seconds=30, width=1080, height=1920, state='reserved', created_at=Clock.current))
                    session.add(PublishJobRecord(id='post-' + key, asset_id='asset-' + key, source='test', edition=0, state='queued', metadata_json='{}', scheduled_at=slot, created_at=Clock.current, updated_at=Clock.current))
                    for account_id, platform, external in [('yt', 'youtube', 'UC-fake'), ('ig', 'instagram', 'ig-fake')]:
                        metadata = {'title': key, 'caption': key, 'visibility': 'private'} if platform == 'youtube' else {'caption': key}
                        session.add(DestinationDeliveryRecord(id=f'{account_id}-{key}', publish_job_id='post-' + key, asset_id='asset-' + key, account_id=account_id, platform=platform, external_account_id=external, edition=0, state='pending', required=True, metadata_json=json.dumps(metadata), scheduled_for=slot, attempt_count=0, created_at=Clock.current, updated_at=Clock.current))
                    session.flush()
                    from tubeforge.pipeline.manual_publish import ManualPublishService
                    post = session.get(PublishJobRecord, 'post-' + key)
                    asset = session.get(PublishingAssetRecord, 'asset-' + key)
                    deliveries = [session.get(DestinationDeliveryRecord, f'{account_id}-{key}') for account_id in ('yt', 'ig')]
                    post.reviewed_identity = ManualPublishService._review_identity(asset, deliveries)
                    post.metadata_json = json.dumps({'public_confirmation': {'account_ids': ['ig'], 'actor': 'fake-operator', 'reviewed_identity': post.reviewed_identity}})
            drain()  # YouTube uploads privately ahead of the slot.
            for index in range(3):
                slot = first_day + timedelta(days=day, hours=7 + index * 3, minutes=30)
                Clock.current = slot - timedelta(minutes=30)
                drain()  # Instagram container may be created, but not published yet.
                assert sum(instagram.publishes.values()) == day * 3 + index
                Clock.current = slot
                drain()
        with db.session_factory() as session:
            deliveries = list(session.scalars(select(DestinationDeliveryRecord)))
            posts = list(session.scalars(select(PublishJobRecord)))
            assert len(deliveries) == 42 and all(row.state == 'published' and row.remote_id for row in deliveries)
            assert len(posts) == 21 and all(row.state == 'published' for row in posts)
            assert len({(row.platform, row.remote_id) for row in deliveries}) == 42
        assert len(youtube.posts) == len(instagram.posts) == 21
        assert sum(youtube.uploads.values()) == sum(instagram.uploads.values()) == sum(instagram.publishes.values()) == 21
        assert all(count == 1 for counts in (youtube.opens, youtube.uploads, instagram.opens, instagram.uploads, instagram.publishes) for count in counts.values())
        evidence = os.environ.get('TUBEFORGE_SOAK_EVIDENCE')
        if evidence:
            destination = Path(evidence)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps({'days': 7, 'posts_per_day': 3, 'platforms': ['youtube', 'instagram'], 'posts': 21, 'deliveries': 42, 'terminal_states': {'published': 42}, 'duplicates': 0, 'lost': 0, 'provider': 'fake'}, indent=2) + '\n')
    finally:
        db.dispose()
