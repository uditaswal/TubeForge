"""Signed-in schedule controls preserve review and pending-action boundaries."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from tubeforge.api.app import create_app
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings
from tubeforge.db.models import Base, PublishingAssetRecord, SocialAccountRecord
from tubeforge.pipeline.manual_publish import ManualPublishService
from tubeforge.publishing_worker.presence import PublisherWorkerPresence


def test_signed_in_schedule_and_distinct_pending_controls(tmp_path: Path, monkeypatch):
    monkeypatch.setenv('TUBEFORGE_ACCOUNT_ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setattr('tubeforge.pipeline.manual_publish.reviewed_youtube_disclosure', lambda session, asset, reviews: {'contains_synthetic_media': False, 'reviewed_identity': 'review', 'evidence_identity': 'evidence', 'record_sha256': 'record'})
    settings = Settings(app=AppConfig(name='schedule test', environment='test'), database=DatabaseConfig(url=f'sqlite:///{tmp_path / "api.db"}'), auth=AuthConfig(enabled=True))
    app = create_app(settings)
    Base.metadata.create_all(app.state.database.engine)
    runtime = app.state.runtime
    now = datetime.now(UTC)
    with runtime.database.session_factory.begin() as session:
        session.add(PublishingAssetRecord(id='asset', sha256='a' * 64, staged_path=str(tmp_path / 'asset.mp4'), source_job_id='job', size_bytes=10, duration_seconds=30, width=1080, height=1920, state='ready', created_at=now))
        session.add(SocialAccountRecord(id='yt', platform='youtube', display_name='Channel', external_account_id='UC-one', auth_type='oauth', credential_ciphertext='fake', scopes_json='[]', token_expires_at=None, status='connected', capabilities_json='[]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
    drafts = ManualPublishService(runtime.database.session_factory)
    post = drafts.create_draft('asset', {'yt': {'title': 'Title', 'caption': 'Description'}})
    identity = drafts.review_identity(post.id)
    PublisherWorkerPresence(runtime.database.session_factory).heartbeat('worker', {'youtube'})
    with TestClient(app) as client:
        runtime.auth.create_admin('operator', 'temporary-test-password')
        assert client.get('/api/publishing/slots?day=2026-11-11').status_code == 401
        assert client.post('/login', json={'username': 'operator', 'password': 'temporary-test-password'}).status_code == 200
        csrf = {'x-csrf-token': client.cookies['tubeforge_csrf']}
        slots = client.get('/api/publishing/slots?day=2026-11-11').json()
        assert slots == {'timezone': 'Asia/Kolkata', 'slots': ['2026-11-11T13:00:00+05:30', '2026-11-11T19:00:00+05:30']}
        state = client.get('/api/publishing/status').json()['readiness']['youtube']
        assert state['audit_state'] == 'audit pending: private only' and state['youtube_api_audited'] is False
        url = f'/api/publishing/drafts/{post.id}/schedule'
        payload = {'reviewed_identity': identity, 'scheduled_for': (now + timedelta(days=1)).isoformat()}
        assert client.post(url, json=payload).status_code == 403
        scheduled = client.post(url, json=payload, headers=csrf)
        assert scheduled.status_code == 200, scheduled.text
        delivery_id = scheduled.json()['destinations'][0]['id']
        listed = client.get('/api/publishing/drafts').json()[0]
        assert listed['scheduled_for'] and listed['destinations'][0]['scheduled_for']
        assert listed['destinations'][0]['can_pause_pending'] and listed['destinations'][0]['can_cancel_pending']
        action_url = f'/api/publishing/deliveries/{delivery_id}/pending-action'
        assert client.post(action_url, json={'action': 'pause'}, headers=csrf).json()['state'] == 'paused'
        paused = client.get('/api/publishing/drafts').json()[0]['destinations'][0]
        assert paused['can_resume_pending'] and not paused['can_pause_pending']
        assert client.post(action_url, json={'action': 'resume'}, headers=csrf).json()['state'] == 'pending'
        assert client.post(action_url, json={'action': 'cancel'}, headers=csrf).json()['state'] == 'cancelled'
        assert client.post(action_url, json={'action': 'resume'}, headers=csrf).status_code == 409
