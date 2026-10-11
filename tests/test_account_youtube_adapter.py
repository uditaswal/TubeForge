"""YouTube resumable upload follows the official session and observation flow."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from tubeforge.pipeline.delivery_executor import SafePreflightError
from tubeforge.providers.publishing.account_youtube import AccountYouTubeAdapter


def test_account_youtube_records_session_before_bytes_and_inspects_private_post(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video bytes")
    calls: list[str] = []
    session = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=one"

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        assert request.headers["Authorization"] == "Bearer scoped-token"
        if request.method == "GET" and request.url.path.endswith("/channels"):
            return httpx.Response(200, json={"items": [{"id": "UC-real"}]})
        if request.method == "POST":
            assert request.url.params["uploadType"] == "resumable"
            assert request.headers["X-Upload-Content-Length"] == str(video.stat().st_size)
            assert b'"privacyStatus":"private"' in request.content
            return httpx.Response(200, headers={"Location": session})
        if request.method == "PUT":
            assert str(request.url) == session
            assert request.headers["Content-Range"] == f"bytes 0-{video.stat().st_size - 1}/{video.stat().st_size}"
            assert request.content == video.read_bytes()
            return httpx.Response(201, json={"id": "video-id"})
        assert request.method == "GET" and request.url.params["id"] == "video-id"
        return httpx.Response(200, json={"items": [{"id": "video-id", "snippet": {"channelId": "UC-real", "title": "Title", "description": "Description"}, "status": {"privacyStatus": "private"}, "processingDetails": {"processingStatus": "succeeded"}}]})

    client = httpx.Client(transport=httpx.MockTransport(respond), follow_redirects=False)
    adapter = AccountYouTubeAdapter(client)
    credential = {"token": "scoped-token"}
    metadata = {"title": "Title", "caption": "Description"}
    opened = adapter.open_session(external_account_id="UC-real", credential=credential, asset_path=video, metadata=metadata)
    assert opened == session and calls == ["GET", "POST"]
    receipt = adapter.upload(session_id=opened, external_account_id="UC-real", credential=credential, asset_path=video, metadata=metadata, heartbeat=lambda: True)
    assert receipt.remote_id == "video-id" and calls == ["GET", "POST", "PUT"]
    observed = adapter.inspect(remote_id=receipt.remote_id, external_account_id="UC-real", credential=credential)
    assert observed.state == "published" and observed.external_account_id == "UC-real" and observed.privacy == "private"
    client.close()


def test_account_youtube_rejects_untrusted_session_url_without_upload(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video bytes")
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.method == "GET":
            return httpx.Response(200, json={"items": [{"id": "UC-real"}]})
        return httpx.Response(200, headers={"Location": "https://example.invalid/capture"})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    adapter = AccountYouTubeAdapter(client)
    with pytest.raises(ValueError, match="invalid resumable"):
        adapter.open_session(external_account_id="UC-real", credential={"token": "scoped-token"}, asset_path=video, metadata={"title": "Title", "caption": "Description"})
    assert calls == 2
    client.close()


def test_account_youtube_refuses_different_channel_before_opening_session(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video bytes")
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        return httpx.Response(200, json={"items": [{"id": "UC-other"}]})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    adapter = AccountYouTubeAdapter(client)
    with pytest.raises(SafePreflightError, match="selected channel"):
        adapter.open_session(external_account_id="UC-real", credential={"token": "scoped-token"}, asset_path=video, metadata={"title": "Title", "caption": "Description"})
    assert calls == ["GET"]
    client.close()


def test_account_youtube_reconciles_saved_session_without_media_bytes() -> None:
    responses = [httpx.Response(308, headers={"Range": "bytes=0-3"}), httpx.Response(201, json={"id": "video-id"})]
    session = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=one"
    calls = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        assert request.method == "PUT" and str(request.url) == session
        assert request.content == b"" and request.headers["Content-Range"] == "bytes */11"
        calls += 1
        return responses.pop(0)

    client = httpx.Client(transport=httpx.MockTransport(respond))
    adapter = AccountYouTubeAdapter(client)
    try:
        assert adapter.inspect_session(session_id=session, credential={"token": "scoped-token"}, asset_size=11) is None
        receipt = adapter.inspect_session(session_id=session, credential={"token": "scoped-token"}, asset_size=11)
        assert receipt is not None and receipt.remote_id == "video-id" and calls == 2
    finally:
        client.close()


def test_account_youtube_resumes_only_missing_bytes_on_saved_session(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"hello world")
    session = "https://www.googleapis.com/upload/youtube/v3/videos?upload_id=one"
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT" and str(request.url) == session
        calls.append(request.headers["Content-Range"])
        if len(calls) == 1:
            assert request.content == b""
            return httpx.Response(308, headers={"Range": "bytes=0-4"})
        assert request.headers["Content-Range"] == "bytes 5-10/11"
        assert request.content == b" world"
        return httpx.Response(201, json={"id": "video-id"})

    client = httpx.Client(transport=httpx.MockTransport(respond))
    adapter = AccountYouTubeAdapter(client)
    try:
        receipt = adapter.resume_session(session_id=session, credential={"token": "scoped-token"}, asset_path=video, heartbeat=lambda: True)
        assert receipt.remote_id == "video-id" and calls == ["bytes */11", "bytes 5-10/11"]
    finally:
        client.close()
