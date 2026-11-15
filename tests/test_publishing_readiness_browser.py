"""Opt-in signed-in publishing readiness check against an isolated fake stack."""
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import threading
import time

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('TUBEFORGE_PUBLISH_BROWSER') != '1', reason='opt-in Chromium smoke')


def test_publishing_readiness_responsive_and_signed_in(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from playwright.sync_api import sync_playwright
    import uvicorn
    from test_api_workflow import _migrate
    from tubeforge.api.app import create_app
    from tubeforge.core.config import Settings, AppConfig, AuthConfig, DatabaseConfig
    from tubeforge.db.models import DestinationDeliveryRecord, PublishJobRecord, PublishingAssetRecord, SocialAccountRecord, YouTubeQuotaChargeRecord
    from tubeforge.pipeline.youtube_quota import YouTubeQuotaLedger
    from tubeforge.publishing_worker.presence import PublisherWorkerPresence

    monkeypatch.setenv('TUBEFORGE_ACCOUNT_ENCRYPTION_KEY', Fernet.generate_key().decode())
    monkeypatch.setenv('TUBEFORGE_GOOGLE_OAUTH_CLIENT_ID', 'local-test-client')
    monkeypatch.setenv('TUBEFORGE_GOOGLE_OAUTH_CLIENT_SECRET', 'local-test-secret')
    monkeypatch.setenv('TUBEFORGE_GOOGLE_OAUTH_REDIRECT_URI', 'http://127.0.0.1:62065/oauth/youtube/callback')
    db = tmp_path / 'browser.db'
    _migrate(db)
    settings = Settings(app=AppConfig(name='Publishing browser test', environment='test'), database=DatabaseConfig(url=f'sqlite:///{db}'), auth=AuthConfig(enabled=True))
    settings.pipeline.voice.artifact_root = tmp_path / 'artifacts'
    app = create_app(settings)
    runtime = app.state.runtime
    runtime.auth.create_admin('local-reviewer', 'temporary-only-test-password')
    now = datetime.now(UTC)
    staging = tmp_path / 'publishing' / 'staging'
    staging.mkdir(parents=True)
    fake_media = b'fake video for readiness checks'
    digest = hashlib.sha256(fake_media).hexdigest()
    (staging / f'{digest}.mp4').write_bytes(fake_media)
    with runtime.database.session_factory.begin() as session:
        session.add(SocialAccountRecord(id='fake-account', platform='youtube', display_name='Fake channel', external_account_id='UC-fake', auth_type='oauth', credential_ciphertext='fake-encrypted-value', scopes_json='[]', token_expires_at=None, status='connected', capabilities_json='[]', is_default=False, disabled=False, last_validated_at=now, created_at=now, updated_at=now))
        session.add(YouTubeQuotaChargeRecord(id='fake-charge', quota_day=YouTubeQuotaLedger._day(now), delivery_id='fake-delivery', units=1600, created_at=now))
        session.add(PublishingAssetRecord(id='fake-asset', sha256=digest, staged_path=str(staging / f'{digest}.mp4'), source_job_id='fake-job', size_bytes=len(fake_media), duration_seconds=1, width=90, height=160, state='reserved', created_at=now))
        session.add(PublishJobRecord(id='fake-post', asset_id='fake-asset', source='test', edition=0, state='attention_required', metadata_json='{}', created_at=now, updated_at=now))
        session.add(DestinationDeliveryRecord(id='fake-delivery', publish_job_id='fake-post', asset_id='fake-asset', account_id='fake-account', platform='youtube', external_account_id='UC-fake', edition=0, state='quota_paused', paused_from_state='pending', required=True, metadata_json=json.dumps({'title': 'Fake reviewed title', 'caption': 'Fake reviewed description', 'contains_synthetic_media': False}), attempt_count=1, error_message='YouTube quota exhausted', created_at=now, updated_at=now))
    PublisherWorkerPresence(runtime.database.session_factory).heartbeat('fake-publisher', {'youtube'})
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen()
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    worker = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
    worker.start()
    deadline = time.monotonic() + 15
    while not server.started and worker.is_alive() and time.monotonic() < deadline:
        time.sleep(.05)
    assert server.started
    evidence = Path(os.environ.get('TUBEFORGE_PUBLISH_BROWSER_EVIDENCE', str(tmp_path / 'screenshots')))
    evidence.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox', '--disable-dev-shm-usage'])
            try:
                for name, width, height in [('desktop', 1440, 1000), ('tablet', 768, 1024), ('mobile', 390, 844)]:
                    with runtime.database.session_factory.begin() as session:
                        delivery = session.get(DestinationDeliveryRecord, 'fake-delivery')
                        delivery.state, delivery.paused_from_state, delivery.error_message = 'quota_paused', 'pending', 'YouTube quota exhausted'
                        session.get(PublishJobRecord, 'fake-post').state = 'attention_required'
                    context = browser.new_context(viewport={'width': width, 'height': height})
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    base = f'http://127.0.0.1:{listener.getsockname()[1]}'
                    assert context.request.post(base + '/login', data={'username': 'local-reviewer', 'password': 'temporary-only-test-password'}).ok
                    PublisherWorkerPresence(runtime.database.session_factory).heartbeat('fake-publisher', {'youtube'})
                    page.goto(base + '/#publishing', wait_until='domcontentloaded')
                    page.get_by_text('estimated upload quota 8400 / 10000 units remaining', exact=False).wait_for()
                    assert page.get_by_text('worker online', exact=False).count() >= 1
                    assert page.get_by_text('audit pending: private only', exact=False).count() >= 1
                    page.get_by_text('Review exact video, destinations and activity').click()
                    resume = page.get_by_role('button', name='Resume after quota is available')
                    assert resume.is_visible()
                    overflow = page.evaluate("[...document.querySelectorAll('body *')].filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(0,8).map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:e.getBoundingClientRect().right}))")
                    assert not page.evaluate('document.documentElement.scrollWidth > innerWidth'), overflow
                    assert not errors
                    page.screenshot(path=str(evidence / f'{name}.png'), full_page=True)
                    resume.click()
                    page.get_by_text('Destination moved to pending.', exact=False).wait_for()
                    with runtime.database.session_factory() as session:
                        assert session.get(DestinationDeliveryRecord, 'fake-delivery').state == 'pending'
                    if name in {'desktop', 'tablet', 'mobile'}:
                        sample = {'id': 'sample-post', 'state': 'draft', 'asset_sha256': 'a' * 64,
                                  'video_url': '/sample.mp4', 'reviewed_identity': 'b' * 64,
                                  'submitted_at': None, 'destinations': [{'id': 'sample-delivery',
                                  'account_id': 'fake-account', 'platform': 'youtube',
                                  'external_account_id': 'Example channel', 'state': 'draft',
                                  'attempt_count': 0, 'metadata': {'title': 'How a small habit changes your day',
                                  'caption': 'A practical idea, ready for your review.', 'visibility': 'private',
                                  'contains_synthetic_media': False}, 'attempts': []}]}
                        received = []
                        page.route('**/api/publishing/drafts', lambda route: route.fulfill(json=[sample]))
                        page.route('**/api/publishing/slots?*', lambda route: route.fulfill(json={'timezone': 'Asia/Kolkata', 'slots': ['2030-01-10T13:00:00+05:30', '2030-01-10T19:00:00+05:30']}))
                        def schedule(route):
                            received.append(route.request.post_data_json)
                            if len(received) == 1:
                                route.fulfill(status=409, json={'detail': {'warnings': ['Two posts are close together']}})
                            else:
                                route.fulfill(json={'id': 'sample-post', 'state': 'pending'})
                        page.route('**/api/publishing/drafts/sample-post/schedule', schedule)
                        page.get_by_role('button', name='Refresh publishing activity').click()
                        page.get_by_text('Review exact video, destinations and activity').click()
                        page.locator('.schedule-box input[type=date]').fill('2030-01-10')
                        page.wait_for_function("document.querySelector('.schedule-box select').options.length === 2")
                        page.locator('#publishDraftHistory .event').screenshot(path=str(evidence / f'schedule-sample-{name}.png'))
                        page.locator('.schedule-box input[type=checkbox]').check()
                        page.get_by_role('button', name='Schedule private upload').click()
                        page.get_by_text('Cadence warning:', exact=False).wait_for()
                        page.get_by_role('button', name='Override warning and schedule').click()
                        page.get_by_text('Schedule saved. Waiting for the publisher worker.').wait_for()
                        assert received[0]['reviewed_identity'] == 'b' * 64
                        assert received[0]['scheduled_for'] == '2030-01-10T13:00:00+05:30'
                        assert not received[0]['allow_future_public_youtube']
                        assert not received[0]['cadence_override'] and received[1]['cadence_override']
                        review_item = {'id': 'sample-short', 'short': {'title': 'How a small habit changes your day', 'hook': 'Start here', 'beats': [], 'cta': ''}, 'state': 'approved', 'decision': 'approved', 'production_state': 'ready', 'available': True, 'qa_ok': True, 'reviewed_identity': 'c' * 64, 'disclosure': {'eligible': True, 'platform_disclosure_required': False}, 'qa': {'output': '[]'}, 'thumbnail_url': None}
                        page.route('**/api/batch-plans/review*', lambda route: route.fulfill(json=[review_item]))
                        page.route('**/api/batch-plans/sample-short/post-defaults?*', lambda route: route.fulfill(json={'youtube': {'title': 'How a small habit changes your day', 'caption': 'A practical idea, ready for your review.'}, 'instagram': {'caption': 'A practical idea. #habits'}}))
                        prepared = []
                        def prepare(route):
                            prepared.append(route.request.post_data_json)
                            route.fulfill(status=201, json={'id': 'sample-post'})
                        page.route('**/api/batch-plans/sample-short/prepare-post', prepare)
                        page.goto(base + '/batch/review', wait_until='domcontentloaded')
                        page.get_by_role('button', name='How a small habit changes your day · approved · ready').click()
                        page.get_by_role('button', name='Choose destinations').click()
                        page.get_by_text('youtube · Fake channel').wait_for()
                        page.locator('#preparePost').screenshot(path=str(evidence / f'prepare-sample-{name}.png'))
                        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
                        page.locator('#preparePost input[type=checkbox]').check()
                        page.get_by_role('button', name='Create draft').click()
                        page.get_by_text('Draft created. Review its exact details in Publishing before any submission.').wait_for()
                        assert prepared[0] == {'reviewed_identity': 'c' * 64, 'destination_account_ids': ['fake-account']}
                    assert not errors
                    context.close()
            finally:
                browser.close()
    finally:
        server.should_exit = True
        worker.join(15)
        listener.close()
        from sqlalchemy import delete, select, func
        from tubeforge.db.models import AdminUserRecord, AuthSessionRecord
        with runtime.database.session_factory.begin() as session:
            session.execute(delete(AuthSessionRecord))
            session.execute(delete(AdminUserRecord).where(AdminUserRecord.username == 'local-reviewer'))
        with runtime.database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(AdminUserRecord).where(AdminUserRecord.username == 'local-reviewer')) == 0
        runtime.database.dispose()
    assert not worker.is_alive()
