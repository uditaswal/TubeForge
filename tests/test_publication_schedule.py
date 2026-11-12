"""Frozen-clock scheduling, cadence and audit safety for destination deliveries."""
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from tubeforge.core.config import DatabaseConfig
from tubeforge.db.models import Base, DestinationDeliveryRecord, PublishJobRecord, PublishingAssetRecord, SocialAccountRecord
from tubeforge.db.session import create_database
from tubeforge.pipeline.delivery_queue import DeliveryQueue
from tubeforge.pipeline.manual_publish import ManualPublishService
from tubeforge.pipeline.publication_schedule import CadenceConfirmationRequired, default_slots
from tubeforge.providers.publishing.account_youtube import AccountYouTubeAdapter
from tubeforge.pipeline.delivery_executor import SafePreflightError


SLOT = datetime(2026, 11, 11, 7, 30, tzinfo=UTC)  # 13:00 IST


def _queue(tmp_path: Path, slots):
    db = create_database(DatabaseConfig(url=f'sqlite:///{tmp_path / "schedule.db"}'))
    Base.metadata.create_all(db.engine)
    with db.session_factory.begin() as session:
        session.add(SocialAccountRecord(id='ig', platform='instagram', display_name='Channel', external_account_id='ig-account', auth_type='oauth', credential_ciphertext='cipher', scopes_json='[]', token_expires_at=None, status='connected', capabilities_json='[]', is_default=False, disabled=False, last_validated_at=SLOT, created_at=SLOT, updated_at=SLOT))
        for i, slot in enumerate(slots):
            session.add(PublishJobRecord(id=f'post-{i}', asset_id=f'asset-{i}', source='test', edition=0, state='queued', metadata_json='{}', created_at=SLOT, updated_at=SLOT))
            session.add(DestinationDeliveryRecord(id=f'delivery-{i}', publish_job_id=f'post-{i}', asset_id=f'asset-{i}', account_id='ig', platform='instagram', external_account_id='ig-account', edition=0, state='pending', required=True, metadata_json='{"caption":"Caption"}', attempt_count=0, scheduled_for=slot, created_at=SLOT, updated_at=SLOT))
    return db, DeliveryQueue(db.session_factory)


def _state(db, delivery='delivery-0'):
    with db.session_factory() as session:
        row = session.get(DestinationDeliveryRecord, delivery)
        return row.state, row.error_message


def _stage(queue, start):
    claim = queue.claim_next('uploader', platforms={'instagram'}, now=start)
    assert claim and claim.kind == 'upload'
    queue.record_session(claim, 'sealed-session', expires_at=start + timedelta(hours=24), now=start + timedelta(seconds=1))
    queue.container_staged(claim, 'container', now=start + timedelta(seconds=2))
    check = queue.claim_next('processor', platforms={'instagram'}, now=start + timedelta(seconds=3))
    assert check and check.kind == 'container_check'
    queue.container_observed(check, 'ready', now=start + timedelta(seconds=4))


def test_ist_default_slots_are_dst_free():
    for day in [date(2026, 1, 1), date(2026, 7, 1), date(2026, 11, 11)]:
        first, second = default_slots(day)
        assert (first.hour, second.hour) == (13, 19)
        assert (first.utcoffset(), second.utcoffset()) == (timedelta(hours=5, minutes=30),) * 2
        assert (first.astimezone(UTC).hour, second.astimezone(UTC).hour) == (7, 13)
        assert first.astimezone(UTC).minute == second.astimezone(UTC).minute == 30


def test_on_time_container_starts_30_minutes_early_and_publishes_at_slot(tmp_path):
    db, queue = _queue(tmp_path, [SLOT])
    try:
        assert queue.claim_next('early', now=SLOT - timedelta(minutes=30, seconds=1)) is None
        _stage(queue, SLOT - timedelta(minutes=30))
        assert queue.claim_next('early', now=SLOT - timedelta(seconds=1)) is None
        claim = queue.claim_next('publisher', now=SLOT)
        assert claim and claim.kind == 'container_publish'
        queue.container_published(claim, 'media', now=SLOT + timedelta(seconds=1))
        assert _state(db)[0] == 'verifying'
    finally:
        db.dispose()


def test_late_within_grace_is_eligible_but_after_grace_is_missed(tmp_path):
    db, queue = _queue(tmp_path, [SLOT])
    try:
        start = SLOT + timedelta(minutes=29)
        _stage(queue, start)
        claim = queue.claim_next('publisher', now=start + timedelta(seconds=5))
        assert claim and claim.kind == 'container_publish'
        queue.container_published(claim, 'media', now=start + timedelta(seconds=6))
        assert _state(db)[0] == 'verifying'
    finally:
        db.dispose()
    db, queue = _queue(tmp_path / 'late', [SLOT])
    try:
        assert queue.claim_next('late-worker', now=SLOT + timedelta(minutes=30, seconds=1)) is None
        assert _state(db)[0] == 'missed'
    finally:
        db.dispose()


def test_downtime_recovery_marks_all_missed_without_burst(tmp_path):
    db, queue = _queue(tmp_path, [SLOT, SLOT + timedelta(minutes=1), SLOT + timedelta(minutes=2)])
    try:
        assert queue.claim_next('restart', now=SLOT + timedelta(hours=3)) is None
        for i in range(3):
            state, reason = _state(db, f'delivery-{i}')
            assert state == 'missed' and 'grace' in reason
        assert queue.claim_next('restart', now=SLOT + timedelta(hours=3, minutes=1)) is None
    finally:
        db.dispose()


def test_pause_resume_and_cancel_are_separate_and_fenced(tmp_path):
    db, queue = _queue(tmp_path, [SLOT, SLOT])
    try:
        assert queue.pending_action('delivery-0', 'pause', 'operator', now=SLOT - timedelta(hours=1)) == 'paused'
        assert queue.pending_action('delivery-1', 'cancel', 'operator', now=SLOT - timedelta(hours=1)) == 'cancelled'
        assert queue.claim_next('worker', now=SLOT) is None
        assert queue.pending_action('delivery-0', 'resume', 'operator', now=SLOT) == 'pending'
        claim = queue.claim_next('worker', now=SLOT)
        assert claim and claim.delivery_id == 'delivery-0'
        with pytest.raises(ValueError, match='in flight'):
            queue.pending_action('delivery-0', 'cancel', 'operator', now=SLOT + timedelta(seconds=1))
        assert _state(db, 'delivery-1')[0] == 'cancelled'
    finally:
        db.dispose()


def test_cadence_override_is_explicit_and_audited(tmp_path, monkeypatch):
    monkeypatch.setattr('tubeforge.pipeline.manual_publish.reviewed_youtube_disclosure', lambda session, asset, reviews: {'contains_synthetic_media': False, 'reviewed_identity': 'review', 'evidence_identity': 'evidence', 'record_sha256': 'record'})
    db = create_database(DatabaseConfig(url=f'sqlite:///{tmp_path / "cadence.db"}'))
    Base.metadata.create_all(db.engine)
    with db.session_factory.begin() as session:
        session.add(SocialAccountRecord(id='yt', platform='youtube', display_name='Channel', external_account_id='UC-one', auth_type='oauth', credential_ciphertext='cipher', scopes_json='[]', token_expires_at=None, status='connected', capabilities_json='[]', is_default=False, disabled=False, last_validated_at=SLOT, created_at=SLOT, updated_at=SLOT))
        for i in range(2):
            session.add(PublishingAssetRecord(id=f'asset-{i}', sha256=str(i) * 64, staged_path=str(tmp_path / f'{i}.mp4'), source_job_id=f'job-{i}', size_bytes=10, duration_seconds=30, width=1080, height=1920, state='ready', created_at=SLOT))
    drafts = ManualPublishService(db.session_factory)
    try:
        first = drafts.create_draft('asset-0', {'yt': {'title': 'One', 'caption': 'Description'}})
        drafts.submit(first.id, reviewed_identity=drafts.review_identity(first.id), actor='operator', supported_platforms={'youtube'}, scheduled_for=SLOT, now=SLOT - timedelta(hours=1))
        second = drafts.create_draft('asset-1', {'yt': {'title': 'Two', 'caption': 'Description'}})
        kwargs = dict(reviewed_identity=drafts.review_identity(second.id), actor='operator', supported_platforms={'youtube'}, scheduled_for=SLOT + timedelta(minutes=30), now=SLOT - timedelta(hours=1))
        with pytest.raises(CadenceConfirmationRequired) as exc:
            drafts.submit(second.id, **kwargs)
        assert any(w['code'] == 'minimum_spacing' for w in exc.value.warnings)
        assert drafts.deliveries(second.id)[0].state == 'draft'
        drafts.submit(second.id, cadence_override=True, **kwargs)
        with db.session_factory() as session:
            audit = json.loads(session.get(PublishJobRecord, second.id).metadata_json)['schedule']
            assert audit['cadence_override'] is True and audit['actor'] == 'operator'
            assert audit['cadence_warnings']
    finally:
        db.dispose()


def test_youtube_schedule_respects_audit_snapshot_and_rejects_past(tmp_path, monkeypatch):
    monkeypatch.setattr('tubeforge.providers.publishing.account_youtube.check_youtube_short', lambda *args, **kwargs: None)
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'video')
    bodies = []
    calls = []
    def respond(request):
        calls.append(request.method)
        if request.method == 'GET':
            return httpx.Response(200, json={'items': [{'id': 'UC-one'}]})
        bodies.append(json.loads(request.content))
        return httpx.Response(200, headers={'Location': 'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test'})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    metadata = {'title': 'Title', 'caption': 'Description', 'contains_synthetic_media': False, 'scheduled_for': SLOT.isoformat(), 'schedule_audit_allowed': True}
    try:
        private = AccountYouTubeAdapter(client, youtube_api_audited=False, clock=lambda: SLOT - timedelta(hours=1))
        private.open_session(external_account_id='UC-one', credential={'token': 'fake'}, asset_path=video, metadata=metadata)
        assert bodies[-1]['status']['privacyStatus'] == 'private' and 'publishAt' not in bodies[-1]['status']
        audited = AccountYouTubeAdapter(client, youtube_api_audited=True, clock=lambda: SLOT - timedelta(hours=1))
        audited.open_session(external_account_id='UC-one', credential={'token': 'fake'}, asset_path=video, metadata={**metadata, 'schedule_audit_allowed': False})
        assert 'publishAt' not in bodies[-1]['status']
        audited.open_session(external_account_id='UC-one', credential={'token': 'fake'}, asset_path=video, metadata=metadata)
        assert bodies[-1]['status']['publishAt'] == '2026-11-11T07:30:00Z'
        before = (len(bodies), len(calls))
        late = AccountYouTubeAdapter(client, youtube_api_audited=True, clock=lambda: SLOT + timedelta(seconds=1))
        with pytest.raises(SafePreflightError, match='future'):
            late.open_session(external_account_id='UC-one', credential={'token': 'fake'}, asset_path=video, metadata=metadata)
        assert (len(bodies), len(calls)) == before
    finally:
        client.close()


def test_audited_schedule_requires_confirmation_and_freezes_audit_choice(tmp_path, monkeypatch):
    monkeypatch.setattr('tubeforge.pipeline.manual_publish.reviewed_youtube_disclosure', lambda session, asset, reviews: {'contains_synthetic_media': False, 'reviewed_identity': 'review', 'evidence_identity': 'evidence', 'record_sha256': 'record'})
    db = create_database(DatabaseConfig(url=f'sqlite:///{tmp_path / "audit.db"}'))
    Base.metadata.create_all(db.engine)
    with db.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id='asset', sha256='b' * 64, staged_path=str(tmp_path / 'final.mp4'), source_job_id='job', size_bytes=10, duration_seconds=30, width=1080, height=1920, state='ready', created_at=SLOT))
        session.add(SocialAccountRecord(id='yt', platform='youtube', display_name='Channel', external_account_id='UC-one', auth_type='oauth', credential_ciphertext='cipher', scopes_json='[]', token_expires_at=None, status='connected', capabilities_json='[]', is_default=False, disabled=False, last_validated_at=SLOT, created_at=SLOT, updated_at=SLOT))
    drafts = ManualPublishService(db.session_factory)
    try:
        post = drafts.create_draft('asset', {'yt': {'title': 'Title', 'caption': 'Description'}})
        args = dict(reviewed_identity=drafts.review_identity(post.id), actor='operator', supported_platforms={'youtube'}, scheduled_for=SLOT, now=SLOT - timedelta(hours=1), youtube_api_audited=True)
        with pytest.raises(ValueError, match='explicit confirmation'):
            drafts.submit(post.id, **args)
        assert drafts.deliveries(post.id)[0].state == 'draft'
        drafts.submit(post.id, allow_future_public_youtube=True, **args)
        delivery = drafts.deliveries(post.id)[0]
        assert delivery.youtube_schedule_audited is True
        with db.session_factory() as session:
            audit = json.loads(session.get(PublishJobRecord, post.id).metadata_json)['schedule']
            assert audit['youtube_publication_confirmed'] is True
    finally:
        db.dispose()


def test_claim_crossing_grace_cannot_start_a_late_remote_mutation(tmp_path):
    db, queue = _queue(tmp_path, [SLOT])
    try:
        claim = queue.claim_next('worker', now=SLOT + timedelta(minutes=29, seconds=59), lease_seconds=120)
        assert claim and claim.scheduled_for is not None
        queue.mark_missed(claim, now=SLOT + timedelta(minutes=30, seconds=1))
        assert _state(db)[0] == 'missed'
        with pytest.raises(ValueError, match='ownership'):
            queue.record_session(claim, 'too-late', now=SLOT + timedelta(minutes=30, seconds=2))
    finally:
        db.dispose()


def test_worker_requires_both_scheduled_consent_snapshot_and_current_audit_config(tmp_path):
    from cryptography.fernet import Fernet
    from tubeforge.pipeline.delivery_executor import DeliveryExecutor
    from tubeforge.security.secrets import TokenCipher
    db = create_database(DatabaseConfig(url=f'sqlite:///{tmp_path / "snapshot.db"}'))
    Base.metadata.create_all(db.engine)
    stage = tmp_path / 'staging'
    stage.mkdir()
    data = b'fake video'
    digest = hashlib.sha256(data).hexdigest()
    path = stage / f'{digest}.mp4'
    path.write_bytes(data)
    now = datetime.now(UTC)
    cipher = TokenCipher(Fernet.generate_key().decode())
    with db.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id='asset', sha256=digest, staged_path=str(path), source_job_id='job', size_bytes=len(data), duration_seconds=30, width=1080, height=1920, state='reserved', created_at=now))
        session.add(SocialAccountRecord(id='yt', platform='youtube', display_name='Channel', external_account_id='UC-one', auth_type='oauth', credential_ciphertext=cipher.encrypt({'token': 'fake'}), scopes_json='[]', token_expires_at=None, status='connected', capabilities_json='[]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
        session.add(PublishJobRecord(id='post', asset_id='asset', source='test', edition=0, state='queued', metadata_json='{}', created_at=now, updated_at=now))
        session.add(DestinationDeliveryRecord(id='delivery', publish_job_id='post', asset_id='asset', account_id='yt', platform='youtube', external_account_id='UC-one', edition=0, state='pending', required=True, metadata_json='{"title":"Title","caption":"Description"}', scheduled_for=now + timedelta(days=1), youtube_schedule_audited=False, attempt_count=0, created_at=now, updated_at=now))
        session.flush()
        post = session.get(PublishJobRecord, 'post')
        post.reviewed_identity = ManualPublishService._review_identity(session.get(PublishingAssetRecord, 'asset'), [session.get(DestinationDeliveryRecord, 'delivery')])
    class Adapter:
        youtube_api_audited = True
    try:
        queue = DeliveryQueue(db.session_factory)
        claim = queue.claim_next('worker')
        assert claim
        executor = DeliveryExecutor(db.session_factory, queue, cipher, stage, {'youtube': Adapter()})
        _, metadata = executor._inputs(claim)
        assert metadata['schedule_audit_allowed'] is False and metadata['expect_publish_at'] is False
        with db.session_factory.begin() as session:
            session.get(DestinationDeliveryRecord, 'delivery').youtube_schedule_audited = True
        _, metadata = executor._inputs(claim)
        assert metadata['schedule_audit_allowed'] is True and metadata['expect_publish_at'] is True
        executor.adapters['youtube'].youtube_api_audited = False
        _, metadata = executor._inputs(claim)
        assert metadata['schedule_audit_allowed'] is True and metadata['expect_publish_at'] is False
    finally:
        db.dispose()



def test_downtime_recovery_does_not_burst_overdue_posts(tmp_path):
    from tubeforge.publishing_worker.presence import PublisherWorkerPresence
    db, queue = _queue(tmp_path, [SLOT, SLOT + timedelta(minutes=5)])
    restart = SLOT + timedelta(minutes=10)
    try:
        with db.session_factory.begin() as session:
            for i in range(2):
                row = session.get(DestinationDeliveryRecord, f'delivery-{i}')
                row.state = 'container_ready'
                row.remote_session_id = f'sealed-{i}'
                row.remote_container_id = f'container-{i}'
                row.remote_session_expires_at = SLOT + timedelta(hours=24)
        PublisherWorkerPresence(db.session_factory).heartbeat('restarted', {'instagram'}, now=restart)
        first = queue.claim_next('restarted', now=restart)
        assert first and first.kind == 'container_publish'
        queue.container_published(first, 'media-1', now=restart + timedelta(seconds=1))
        verification = queue.claim_next('restarted', now=restart + timedelta(seconds=2))
        assert verification and verification.kind == 'verify'
        queue.verified_published(verification, now=restart + timedelta(seconds=3))
        assert queue.claim_next('restarted', now=restart + timedelta(seconds=4)) is None
        with db.session_factory() as session:
            delayed = session.get(DestinationDeliveryRecord, 'delivery-1')
            assert delayed.state == 'container_ready' and delayed.next_retry_at is not None
            assert 'burst' in delayed.error_message
        assert queue.claim_next('restarted', now=SLOT + timedelta(minutes=36)) is None
        assert _state(db, 'delivery-1')[0] == 'missed'
    finally:
        db.dispose()
