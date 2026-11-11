"""Instagram Reels adapter: preflight, resumable upload, one publish, safe reconciliation."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from tubeforge.pipeline.delivery_executor import SafePreflightError
from tubeforge.providers.publishing.account_instagram import AccountInstagramAdapter, instagram_full_caption

URI = "https://rupload.facebook.com/ig-api-upload/v21.0/container-1"
CRED = {"token": "tok"}
META = {"caption": "Hook line", "hashtags": ["#a", "#b"], "confirm_public": True}


class Fake:
    def __init__(self, statuses=("FINISHED",), quota=0, user="1784", publish_status=200, offset=0):
        self.statuses, self.quota, self.user, self.publish_status, self.offset = list(statuses), quota, user, publish_status, offset
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append(f"{request.method} {request.url.host}{path}")
        if request.url.host == "rupload.facebook.com":
            if request.method == "GET":
                return httpx.Response(200, json={"file_offset": self.offset})
            assert request.headers["Authorization"] == "OAuth tok" and request.headers["offset"] == str(self.offset) and request.headers["file_size"]
            return httpx.Response(200, json={"success": True})
        assert request.headers["Authorization"] == "Bearer tok"
        if path.endswith("/me"):
            return httpx.Response(200, json={"user_id": self.user})
        if path.endswith("/content_publishing_limit"):
            return httpx.Response(200, json={"data": [{"quota_usage": self.quota, "config": {"quota_total": 100}}]})
        if path.endswith("/1784/media") and request.method == "POST":
            assert b"REELS" in request.content and b"resumable" in request.content and b"Hook+line" in request.content
            return httpx.Response(200, json={"id": "container-1", "uri": URI})
        if path.endswith("/media_publish"):
            assert b"creation_id=container-1" in request.content
            return httpx.Response(self.publish_status, json={"id": "media-9"} if self.publish_status == 200 else {})
        if path.endswith("/container-1"):
            return httpx.Response(200, json={"status_code": self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]})
        if path.endswith("/media-9"):
            return httpx.Response(200, json={"id": "media-9", "permalink": "https://www.instagram.com/reel/abc/", "caption": instagram_full_caption(META), "owner": {"id": "1784"}})
        return httpx.Response(404)


def adapter(fake: Fake) -> AccountInstagramAdapter:
    return AccountInstagramAdapter(httpx.Client(transport=httpx.MockTransport(fake)), poll_seconds=0, max_polls=5, sleep=lambda _: None)


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "v.mp4"
    path.write_bytes(b"reel bytes")
    return path


def test_full_flow_publishes_once_and_inspect_matches(video: Path) -> None:
    fake = Fake(statuses=("IN_PROGRESS", "FINISHED"))
    ig = adapter(fake)
    session = ig.open_session(external_account_id="1784", credential=CRED, asset_path=video, metadata=META)
    assert not any("media_publish" in call or "rupload" in call for call in fake.calls)  # session recorded before bytes
    receipt = ig.upload(session_id=session, external_account_id="1784", credential=CRED, asset_path=video, metadata=META, heartbeat=lambda: True)
    assert receipt.remote_id == "media-9" and receipt.remote_url == "https://www.instagram.com/reel/abc/"
    assert sum("media_publish" in call for call in fake.calls) == 1
    seen = ig.inspect(remote_id="media-9", external_account_id="1784", credential=CRED)
    assert seen.state == "published" and seen.external_account_id == "1784" and seen.caption == "Hook line\n\n#a #b"


def test_preflight_refusals_make_no_container(video: Path) -> None:
    for fake, meta, category in (
        (Fake(), {**META, "confirm_public": False}, "invalid"),
        (Fake(user="other"), META, "auth"),
        (Fake(quota=100), META, "retry"),
        (Fake(), {"caption": "x" * 2300, "confirm_public": True}, "invalid"),
    ):
        with pytest.raises(SafePreflightError) as error:
            adapter(fake).open_session(external_account_id="1784", credential=CRED, asset_path=video, metadata=meta)
        assert error.value.category == category
        assert not any(call.startswith("POST") for call in fake.calls)


def test_untrusted_upload_host_is_rejected(video: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/me"):
            return httpx.Response(200, json={"user_id": "1784"})
        if request.url.path.endswith("/content_publishing_limit"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"id": "container-1", "uri": "https://evil.example/container-1"})

    ig = AccountInstagramAdapter(httpx.Client(transport=httpx.MockTransport(respond)))
    with pytest.raises(ValueError):
        ig.open_session(external_account_id="1784", credential=CRED, asset_path=video, metadata=META)
    with pytest.raises(ValueError):
        ig.inspect_session(session_id='{"c":"container-1","u":"https://evil.example/container-1"}', credential=CRED, asset_size=1)


def test_publish_failure_is_not_retried_and_published_container_is_never_republished(video: Path) -> None:
    session = '{"c":"container-1","u":"%s"}' % URI
    failing = Fake(publish_status=500)
    with pytest.raises(ValueError):
        adapter(failing).upload(session_id=session, external_account_id="1784", credential=CRED, asset_path=video, metadata=META, heartbeat=lambda: True)
    assert sum("media_publish" in call for call in failing.calls) == 1  # no blind second publish
    published = Fake(statuses=("PUBLISHED",))
    ig = adapter(published)
    with pytest.raises(ValueError, match="no media id"):
        ig.inspect_session(session_id=session, credential=CRED, asset_size=10)
    with pytest.raises(ValueError):
        ig.resume_session(session_id=session, credential=CRED, asset_path=video, heartbeat=lambda: True)
    assert not any("media_publish" in call for call in published.calls)


def test_reconcile_and_resume_unpublished_container(video: Path) -> None:
    session = '{"c":"container-1","u":"%s"}' % URI
    finished = Fake(statuses=("FINISHED",))
    assert adapter(finished).inspect_session(session_id=session, credential=CRED, asset_size=10) is None
    assert adapter(finished).resume_session(session_id=session, credential=CRED, asset_path=video, heartbeat=lambda: True).remote_id == "media-9"
    expired = Fake(statuses=("EXPIRED",))
    with pytest.raises(ValueError):
        adapter(expired).inspect_session(session_id=session, credential=CRED, asset_size=10)
    # partial upload: resumes the same container from the server's offset, then publishes
    partial = Fake(statuses=("IN_PROGRESS", "IN_PROGRESS", "FINISHED"), offset=4)
    assert adapter(partial).resume_session(session_id=session, credential=CRED, asset_path=video, heartbeat=lambda: True).remote_id == "media-9"
    assert any(call.startswith("POST rupload") for call in partial.calls) and not any(call.endswith("/1784/media") for call in partial.calls)


def test_missing_remote_media(video: Path) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 100}})

    ig = AccountInstagramAdapter(httpx.Client(transport=httpx.MockTransport(respond)))
    assert ig.inspect(remote_id="gone", external_account_id="1784", credential=CRED).state == "missing"
