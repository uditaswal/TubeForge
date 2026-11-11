"""A fake container provider exercises crash boundaries without a live account."""
from datetime import UTC, datetime, timedelta
import hashlib
from pathlib import Path

from cryptography.fernet import Fernet
from sqlalchemy import select

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base, DestinationDeliveryRecord, PublishJobRecord, PublishingAssetRecord, SocialAccountRecord
from tubeforge.db.session import create_database
from tubeforge.pipeline.delivery_executor import ContainerObservation, ContainerReceipt, DeliveryExecutor, ProviderRateLimitHint, RemoteObservation, RemoteSession, UploadReceipt
from tubeforge.pipeline.delivery_queue import DeliveryQueue
from tubeforge.security.secrets import TokenCipher


class FakeContainer:
    def __init__(self):
        self.opened = self.uploaded = self.published = 0
        self.is_published = False
        self.fail_after_publish = False
        self.fail_after_upload = False
        self.processing = False
        self.retry_hint = None
        self.rate_limited = False

    def open_session(self, **kwargs):
        self.opened += 1
        return RemoteSession('container-session', datetime.now(UTC) + timedelta(hours=24))

    def upload(self, *, heartbeat, **kwargs):
        assert heartbeat()
        self.uploaded += 1
        if self.fail_after_upload:
            raise TimeoutError('remote outcome unknown')
        return ContainerReceipt('container-1')

    def inspect_session(self, **kwargs):
        return ContainerReceipt('container-1')

    def inspect_container(self, **kwargs):
        assert kwargs['container_id'] == 'container-1'
        if self.rate_limited:
            raise ProviderRateLimitHint(42)
        if self.is_published:
            return ContainerObservation('published', 'media-1', 'https://example.invalid/media-1')
        return ContainerObservation('processing' if self.processing else 'ready', retry_after_seconds=self.retry_hint)

    def publish_container(self, *, heartbeat, **kwargs):
        assert heartbeat()
        assert not self.is_published, 'double publish'
        self.published += 1
        self.is_published = True
        if self.fail_after_publish:
            raise TimeoutError('publish accepted, response lost')
        return UploadReceipt('media-1', 'https://example.invalid/media-1')

    def inspect(self, **kwargs):
        return RemoteObservation('published', 'ig-account', caption='Reviewed caption', remote_url='https://example.invalid/media-1')


class FakeCredentials:
    def resolve(self, account_id, owner):
        return {'token': 'fake'}


def _setup(tmp_path: Path):
    db = create_database(DatabaseConfig(url=f'sqlite:///{tmp_path / "container.db"}'))
    Base.metadata.create_all(db.engine)
    stage = tmp_path / 'staging'
    stage.mkdir()
    content = b'approved fake video'
    digest = hashlib.sha256(content).hexdigest()
    (stage / f'{digest}.mp4').write_bytes(content)
    cipher = TokenCipher(Fernet.generate_key().decode())
    now = datetime.now(UTC)
    with db.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id='asset', sha256=digest, staged_path=str(stage / f'{digest}.mp4'), source_job_id='job', size_bytes=len(content), duration_seconds=30, width=1080, height=1920, state='reserved', created_at=now))
        session.add(SocialAccountRecord(id='ig', platform='instagram', display_name='Fake', external_account_id='ig-account', auth_type='oauth', credential_ciphertext=cipher.encrypt({'token': 'fake'}), scopes_json='[]', token_expires_at=None, status='connected', capabilities_json='[]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
        session.add(PublishJobRecord(id='post', asset_id='asset', source='test', edition=0, state='queued', metadata_json='{}', created_at=now, updated_at=now))
        session.add(DestinationDeliveryRecord(id='delivery', publish_job_id='post', asset_id='asset', account_id='ig', platform='instagram', external_account_id='ig-account', edition=0, state='pending', required=True, metadata_json='{"caption":"Reviewed caption"}', attempt_count=0, created_at=now, updated_at=now))
    adapter = FakeContainer()
    queue = DeliveryQueue(db.session_factory)
    executor = DeliveryExecutor(db.session_factory, queue, cipher, stage, {'instagram': adapter}, FakeCredentials())
    return db, queue, executor, adapter


def _state(db):
    with db.session_factory() as session:
        row = session.get(DestinationDeliveryRecord, 'delivery')
        return row.state, row.remote_container_id, row.remote_id, row.next_retry_at


def test_crash_between_upload_and_publish_resumes_container_once(tmp_path):
    db, queue, executor, adapter = _setup(tmp_path)
    try:
        assert executor.run_once('upload-worker') == 'delivery'
        assert _state(db)[:3] == ('container_processing', 'container-1', None)
        # A new worker takes over the durably staged container, not a new upload.
        assert executor.run_once('new-worker') == 'delivery'
        assert _state(db)[0] == 'container_ready'
        assert executor.run_once('new-worker') == 'delivery'
        assert _state(db)[:3] == ('verifying', 'container-1', 'media-1')
        assert executor.run_once('new-worker') == 'delivery'
        assert _state(db)[0] == 'published'
        assert executor.run_once('new-worker') is None
        assert (adapter.opened, adapter.uploaded, adapter.published) == (1, 1, 1)
    finally:
        db.dispose()


def test_expired_container_is_never_published(tmp_path):
    db, queue, executor, adapter = _setup(tmp_path)
    try:
        executor.run_once('worker')
        with db.session_factory.begin() as session:
            session.get(DestinationDeliveryRecord, 'delivery').remote_session_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert executor.run_once('worker') is None
        assert _state(db)[0] == 'failed'
        assert adapter.published == 0 and adapter.opened == 1
    finally:
        db.dispose()


def test_unknown_publish_outcome_requires_inspection_and_never_republishes(tmp_path):
    db, queue, executor, adapter = _setup(tmp_path)
    adapter.fail_after_publish = True
    try:
        executor.run_once('worker')
        executor.run_once('worker')
        executor.run_once('worker')
        assert _state(db)[0] == 'unknown_outcome'
        assert executor.run_once('worker') is None
        queue.request_action('delivery', 'inspect', 'operator')
        assert executor.run_requested_action('reconciler') == 'delivery'
        assert _state(db)[:3] == ('verifying', 'container-1', 'media-1')
        executor.run_once('worker')
        assert _state(db)[0] == 'published'
        assert (adapter.opened, adapter.uploaded, adapter.published) == (1, 1, 1)
    finally:
        db.dispose()


def test_crash_after_upload_reconciles_same_container(tmp_path):
    db, queue, executor, adapter = _setup(tmp_path)
    adapter.fail_after_upload = True
    try:
        executor.run_once('worker')
        assert _state(db)[0] == 'unknown_outcome'
        queue.request_action('delivery', 'inspect', 'operator')
        executor.run_requested_action('reconciler')
        assert _state(db)[:2] == ('container_processing', 'container-1')
        executor.run_once('worker')
        executor.run_once('worker')
        assert (adapter.opened, adapter.uploaded, adapter.published) == (1, 1, 1)
    finally:
        db.dispose()


def test_processing_retry_hint_is_bounded(tmp_path):
    db, queue, executor, adapter = _setup(tmp_path)
    adapter.processing = True
    adapter.retry_hint = 999999
    try:
        executor.run_once('worker')
        before = datetime.now(UTC)
        executor.run_once('worker')
        state, _, _, retry = _state(db)
        assert state == 'container_processing'
        assert 3590 <= (retry.replace(tzinfo=UTC) - before).total_seconds() <= 3601
        assert executor.run_once('worker') is None
    finally:
        db.dispose()



def test_read_only_rate_limit_hint_defers_without_new_upload_or_publish(tmp_path):
    db, queue, executor, adapter = _setup(tmp_path)
    adapter.rate_limited = True
    try:
        executor.run_once('worker')
        before = datetime.now(UTC)
        executor.run_once('worker')
        state, _, _, retry = _state(db)
        assert state == 'container_processing'
        assert 40 <= (retry.replace(tzinfo=UTC) - before).total_seconds() <= 43
        assert (adapter.opened, adapter.uploaded, adapter.published) == (1, 1, 0)
    finally:
        db.dispose()


def test_expired_publish_lease_after_remote_acceptance_reconciles_once(tmp_path):
    import pytest
    db, queue, executor, adapter = _setup(tmp_path)
    try:
        executor.run_once('uploader')
        executor.run_once('processor')
        claim = queue.claim_next('crashed-publisher', platforms={'instagram'})
        assert claim is not None and claim.kind == 'container_publish'
        receipt = adapter.publish_container(container_id='container-1', external_account_id='ig-account', credential={'token': 'fake'}, heartbeat=lambda: True)
        # Simulate a process death after the remote success and before its receipt is saved.
        with db.session_factory.begin() as session:
            session.get(DestinationDeliveryRecord, 'delivery').lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        assert queue.claim_next('replacement', platforms={'instagram'}) is None
        assert _state(db)[0] == 'unknown_outcome'
        with pytest.raises(ValueError, match='ownership'):
            queue.container_published(claim, receipt.remote_id)
        queue.request_action('delivery', 'inspect', 'operator')
        executor.run_requested_action('reconciler')
        assert _state(db)[0] == 'verifying'
        executor.run_once('verifier')
        assert _state(db)[0] == 'published'
        assert (adapter.opened, adapter.uploaded, adapter.published) == (1, 1, 1)
    finally:
        db.dispose()


def test_ambiguous_publish_is_not_retried_when_container_still_reports_ready(tmp_path):
    db, queue, executor, adapter = _setup(tmp_path)
    adapter.fail_after_publish = True
    try:
        executor.run_once('worker')
        executor.run_once('worker')
        executor.run_once('worker')
        assert _state(db)[0] == 'unknown_outcome'
        # A ready container alone does not prove that a lost publish failed.
        adapter.is_published = False
        queue.request_action('delivery', 'inspect', 'operator')
        executor.run_requested_action('reconciler')
        assert _state(db)[0] == 'unknown_outcome'
        assert executor.run_once('worker') is None
        assert adapter.published == 1
    finally:
        db.dispose()
