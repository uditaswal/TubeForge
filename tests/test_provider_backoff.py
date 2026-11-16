"""Provider hints are bounded and mutation outcomes remain conservative."""
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from tubeforge.pipeline.delivery_executor import ProviderRateLimitHint, SafePreflightError
from tubeforge.pipeline.provider_backoff import provider_hint, retry_delay
from tubeforge.providers.publishing.account_youtube import AccountYouTubeAdapter


def test_retry_after_and_meta_usage_are_combined_and_jittered():
    now = datetime(2026, 11, 11, 12, 0, tzinfo=UTC)
    assert provider_hint({'Retry-After': '120'}, now=now) == 120
    assert provider_hint({'Retry-After': 'Wed, 11 Nov 2026 12:02:00 GMT'}, now=now) == 120
    assert provider_hint({'x-app-usage': '{"call_count":95,"total_time":45}'}, now=now) == 480
    assert provider_hint({'Retry-After': '99999'}, now=now) == 3600
    assert provider_hint({'x-app-usage': 'not-json', 'Retry-After': 'bad'}, now=now) is None
    assert retry_delay(120, attempt=1, jitter=lambda low, high: high) == 144
    assert retry_delay(None, attempt=4, jitter=lambda low, high: 0) == 240
    assert retry_delay(99999, attempt=100, jitter=lambda low, high: high) == 3600


@pytest.mark.parametrize(('status', 'reason', 'category'), [
    (403, 'quotaExceeded', 'quota'), (403, 'rateLimitExceeded', 'retry'), (401, 'authError', 'auth'),
])
def test_youtube_identity_errors_are_classified_before_upload(tmp_path: Path, monkeypatch, status, reason, category):
    monkeypatch.setattr('tubeforge.providers.publishing.account_youtube.check_youtube_short', lambda *args, **kwargs: None)
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'fake')
    requests = []
    def respond(request):
        requests.append(request.method)
        return httpx.Response(status, headers={'Retry-After': '75'}, json={'error': {'errors': [{'reason': reason}]}})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        adapter = AccountYouTubeAdapter(client)
        with pytest.raises(SafePreflightError) as exc:
            adapter.open_session(external_account_id='channel', credential={'token': 'fake'}, asset_path=video, metadata={'title': 'Title', 'caption': 'Description', 'contains_synthetic_media': False})
        assert exc.value.category == category and requests == ['GET']
        if category == 'retry':
            assert exc.value.retry_after_seconds == 75
    finally:
        client.close()


def test_read_only_usage_hint_delays_before_session_creation(tmp_path: Path, monkeypatch):
    monkeypatch.setattr('tubeforge.providers.publishing.account_youtube.check_youtube_short', lambda *args, **kwargs: None)
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'fake')
    calls = []
    def respond(request):
        calls.append(request.method)
        return httpx.Response(200, headers={'x-app-usage': '{"call_count":95}'}, json={'items': [{'id': 'channel'}]})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(SafePreflightError) as exc:
            AccountYouTubeAdapter(client).open_session(external_account_id='channel', credential={'token': 'fake'}, asset_path=video, metadata={'title': 'Title', 'caption': 'Description', 'contains_synthetic_media': False})
        assert exc.value.category == 'retry' and exc.value.retry_after_seconds == 480
        assert calls == ['GET']
    finally:
        client.close()


def test_upload_rate_limit_does_not_open_a_second_session(tmp_path: Path):
    video = tmp_path / 'video.mp4'
    video.write_bytes(b'fake')
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429, headers={'Retry-After': '90'})))
    try:
        with pytest.raises(ProviderRateLimitHint) as exc:
            AccountYouTubeAdapter(client).upload(session_id='https://www.googleapis.com/upload/youtube/v3/videos?upload_id=test', external_account_id='channel', credential={'token': 'fake'}, asset_path=video, metadata={}, heartbeat=lambda: True)
        assert exc.value.retry_after_seconds == 90
    finally:
        client.close()


def test_google_refresh_honors_retry_after_and_auth_failure_needs_reconnect():
    from tubeforge.security.account_credentials import CredentialReconnectRequired, CredentialRefreshTemporary, GoogleCredentialRefresher
    responses = [httpx.Response(429, headers={'Retry-After': '75'}), httpx.Response(400, json={'error': 'invalid_client'})]
    client = httpx.Client(transport=httpx.MockTransport(lambda request: responses.pop(0)))
    credential = {'token_uri': 'https://oauth2.googleapis.com/token', 'client_id': 'fake', 'client_secret': 'fake', 'refresh_token': 'fake'}
    try:
        refresh = GoogleCredentialRefresher(client)
        with pytest.raises(CredentialRefreshTemporary) as error:
            refresh(credential)
        assert error.value.retry_after_seconds == 75
        with pytest.raises(CredentialReconnectRequired):
            refresh(credential)
    finally:
        client.close()
