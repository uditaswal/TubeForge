"""Offline unit coverage for the official M13 Google client adapter."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from tubeforge.core.config import YouTubePublishingConfig
from tubeforge.core.errors import AmbiguousProviderError, ProviderAuthenticationError, ProviderCancellation, ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import PublishPrivacy, PublishRequest, VideoMetadata
from tubeforge.providers.publishing.youtube import YouTubeDataApiPublisher, _classify_google_error


def config(tmp_path, **values):
    return YouTubePublishingConfig(enabled=True, dry_run=False, client_secret_path=tmp_path / "client.json", token_storage_path=tmp_path / "token.json", expected_channel_id="channel-1", **values)


def request(tmp_path) -> PublishRequest:
    video = tmp_path / "video.mp4"; video.write_bytes(b"small-fixture")
    return PublishRequest(platform="youtube", artifact_path=str(video), metadata=VideoMetadata(title_options=("Title",), description="Description", tags=("one", "two")), privacy=PublishPrivacy.PRIVATE, idempotency_key="identity")


def test_import_and_constructor_have_no_auth_or_browser_side_effects(tmp_path) -> None:
    publisher = YouTubeDataApiPublisher(config(tmp_path), build_service=Mock())
    assert publisher._service is None


def test_missing_or_malformed_token_is_headless_and_redacted(tmp_path) -> None:
    publisher = YouTubeDataApiPublisher(config(tmp_path))
    with pytest.raises(ProviderAuthenticationError, match="token is missing") as missing:
        publisher._client()
    assert "refresh-secret" not in str(missing.value)
    config(tmp_path).token_storage_path.write_text("{bad", encoding="utf-8")
    with pytest.raises(ProviderAuthenticationError, match="token is invalid"):
        publisher._client()


def test_valid_and_refreshable_credentials_build_without_interactive_authorization(tmp_path) -> None:
    settings = config(tmp_path); settings.token_storage_path.write_text("{}", encoding="utf-8")
    valid = Mock(valid=True)
    service = Mock()
    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=valid) as load:
        assert YouTubeDataApiPublisher(settings, build_service=Mock(return_value=service))._client() is service
    load.assert_called_once_with(str(settings.token_storage_path), ("https://www.googleapis.com/auth/youtube.upload",))
    refreshable = Mock(valid=False, expired=True, refresh_token="refresh-secret", to_json=Mock(return_value="{}"))
    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=refreshable):
        YouTubeDataApiPublisher(settings, build_service=Mock())._client()
    refreshable.refresh.assert_called_once()


def test_refresh_failure_and_interactive_credentials_are_redacted(tmp_path) -> None:
    settings = config(tmp_path); settings.token_storage_path.write_text("{}", encoding="utf-8")
    refreshable = Mock(valid=False, expired=True, refresh_token="refresh-secret")
    refreshable.refresh.side_effect = RuntimeError("refresh-secret")
    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=refreshable):
        with pytest.raises(ProviderAuthenticationError, match="refresh failed") as failure:
            YouTubeDataApiPublisher(settings, build_service=Mock())._client()
    assert "refresh-secret" not in str(failure.value)
    interactive = Mock(valid=False, expired=False, refresh_token=None)
    with patch("google.oauth2.credentials.Credentials.from_authorized_user_file", return_value=interactive):
        with pytest.raises(ProviderAuthenticationError, match="cannot be refreshed"):
            YouTubeDataApiPublisher(settings, build_service=Mock())._client()


def test_channel_lookup_and_upload_request_are_file_backed_and_resumable(tmp_path) -> None:
    settings = config(tmp_path, chunk_size_bytes=262_144)
    operation = Mock(); operation.next_chunk.side_effect = [(Mock(), None), (Mock(), {"id": "video-1"})]
    videos = Mock(); videos.insert.return_value = operation
    service = Mock(); service.channels().list().execute.return_value = {"items": [{"id": "channel-1"}]}; service.videos.return_value = videos
    publisher = YouTubeDataApiPublisher(settings, build_service=Mock()); publisher._service = service
    assert publisher.authenticated_channel_id() == "channel-1"
    with patch("googleapiclient.http.MediaFileUpload") as media_upload:
        assert publisher.create_or_resume_video(request(tmp_path)) == "video-1"
    media_upload.assert_called_once_with(str(tmp_path / "video.mp4"), resumable=True, chunksize=262_144)
    assert videos.insert.call_args.kwargs["body"] == {"snippet": {"title": "Title", "description": "Description", "tags": ["one", "two"]}, "status": {"privacyStatus": "private"}}


def test_upload_cancellation_and_error_classification_are_safe(tmp_path) -> None:
    operation = Mock(); operation.next_chunk.return_value = (Mock(), None)
    service = Mock(); service.videos().insert.return_value = operation
    publisher = YouTubeDataApiPublisher(config(tmp_path), build_service=Mock()); publisher._service = service
    with pytest.raises(ProviderCancellation): publisher.create_or_resume_video(request(tmp_path), cancellation_requested=lambda: True)
    class HttpFailure(Exception):
        def __init__(self, status): self.resp = type("Response", (), {"status": status})()
    assert isinstance(_classify_google_error(HttpFailure(401)), ProviderAuthenticationError)
    assert isinstance(_classify_google_error(HttpFailure(403)), ProviderValidationError)
    assert isinstance(_classify_google_error(HttpFailure(429)), RetryableProviderError)
    assert isinstance(_classify_google_error(HttpFailure(503)), RetryableProviderError)
    assert isinstance(_classify_google_error(RuntimeError("access-token"), ambiguous=True), AmbiguousProviderError)


def test_reconciliation_parses_remote_state_and_malformed_responses(tmp_path) -> None:
    service = Mock(); service.videos().list().execute.return_value = {"items": [{"snippet": {"title": "Title", "description": "Description"}, "status": {"privacyStatus": "unlisted"}, "processingDetails": {"processingStatus": "processing"}}]}
    publisher = YouTubeDataApiPublisher(config(tmp_path), build_service=Mock()); publisher._service = service
    assert publisher.fetch_video("video-1") == {"privacy": "unlisted", "title": "Title", "description": "Description", "processing": "processing"}
    service.videos().list().execute.return_value = {"items": []}
    assert publisher.fetch_video("missing") is None


def test_analytics_request_is_read_only_and_normalizes_partial_results(tmp_path) -> None:
    reports = Mock(); reports.query.return_value.execute.return_value = {
        "columnHeaders": [{"name": "views"}, {"name": "estimatedMinutesWatched"}, {"name": "impressionsClickThroughRate"}],
        "rows": [[0, 2.5, 4.2]],
    }
    service = Mock(); service.reports.return_value = reports
    publisher = YouTubeDataApiPublisher(config(tmp_path), build_service=Mock()); publisher._analytics_service = service
    from datetime import date
    snapshot = publisher.fetch_video_analytics("video-1", "channel-1", date(2026, 1, 1), date(2026, 1, 2))
    assert snapshot.metrics["views"].value == 0 and snapshot.metrics["estimatedMinutesWatched"].value == 2.5
    assert snapshot.metrics["likes"].availability.value == "unavailable" and snapshot.completeness == "partial"
    assert reports.query.call_args.kwargs["filters"] == "video==video-1"
    assert reports.query.call_args.kwargs["ids"] == "channel==channel-1"
    assert service.videos.call_count == service.thumbnails.call_count == 0
