"""Account-scoped YouTube resumable upload adapter with no file-backed token."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Callable
from urllib.parse import urlsplit

import httpx

from tubeforge.pipeline.delivery_executor import RemoteObservation, SafePreflightError, UploadReceipt


UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
CHUNK_BYTES = 8 * 1024 * 1024


class AccountYouTubeAdapter:
    """Only opens a session; the executor persists it before sending video bytes."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=60, follow_redirects=False)

    def open_session(self, *, external_account_id: str, credential: dict[str, object], asset_path: Path, metadata: dict[str, object]) -> str:
        access_token = _token(credential)
        title = metadata.get("title")
        description = metadata.get("caption")
        visibility = metadata.get("visibility", "private")
        if not isinstance(title, str) or not title or not isinstance(description, str) or visibility not in {"private", "unlisted", "public"}:
            raise SafePreflightError("YouTube metadata is invalid")
        tags = metadata.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise SafePreflightError("YouTube tags are invalid")
        try:
            identity = self.client.get(CHANNELS_URL, params={"part": "id", "mine": "true"}, headers={"Authorization": f"Bearer {access_token}"})
        except httpx.HTTPError as error:
            raise SafePreflightError("YouTube channel identity check is unavailable", category="retry") from error
        if identity.status_code != 200:
            raise SafePreflightError("YouTube channel identity could not be checked", category="auth" if identity.status_code in {401, 403} else "retry")
        try:
            channels = identity.json().get("items", [])
        except (ValueError, AttributeError) as error:
            raise SafePreflightError("YouTube channel identity response is invalid", category="retry") from error
        if not isinstance(channels, list) or len(channels) != 1 or not isinstance(channels[0], dict) or channels[0].get("id") != external_account_id:
            raise SafePreflightError("YouTube token does not belong to the selected channel", category="auth")
        response = self.client.post(
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={"Authorization": f"Bearer {access_token}", "X-Upload-Content-Length": str(asset_path.stat().st_size), "X-Upload-Content-Type": "video/mp4"},
            json={"snippet": {"title": title, "description": description, "tags": tags, "categoryId": "22"}, "status": {"privacyStatus": visibility}},
        )
        if response.status_code != 200:
            raise ValueError("YouTube did not open a resumable upload session")
        session_id = response.headers.get("Location", "")
        _session_url(session_id)
        return session_id

    def upload(self, *, session_id: str, external_account_id: str, credential: dict[str, object], asset_path: Path, metadata: dict[str, object], heartbeat: Callable[[], bool]) -> UploadReceipt:
        _session_url(session_id)
        access_token = _token(credential)
        receipt = self._send_from(session_id, access_token, asset_path, 0, heartbeat)
        self._apply_thumbnail(receipt.remote_id, access_token, asset_path, metadata)
        return receipt

    def _apply_thumbnail(self, remote_id: str, access_token: str, asset_path: Path, metadata: dict[str, object]) -> None:
        """Best effort: the video is already uploaded, so a thumbnail failure must never change the delivery outcome."""
        digest = metadata.get("thumbnail_sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            return
        path = asset_path.parent / "thumbnails" / f"{digest}.jpg"
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
                return
            self.client.post(THUMBNAIL_URL, params={"videoId": remote_id}, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/jpeg"}, content=path.read_bytes())
        except (httpx.HTTPError, OSError):
            return

    def resume_session(self, *, session_id: str, credential: dict[str, object], asset_path: Path, heartbeat: Callable[[], bool]) -> UploadReceipt:
        """Query Google first, then continue only the same saved session URI."""
        _session_url(session_id)
        access_token = _token(credential)
        size = asset_path.stat().st_size
        if size <= 0 or not heartbeat():
            raise ValueError("canonical video or delivery lease is unavailable")
        response = self._status_request(session_id, access_token, size)
        if response.status_code in {200, 201}:
            return _receipt(response)
        if response.status_code != 308:
            raise ValueError("saved YouTube session cannot be resumed safely")
        acknowledged = _acknowledged(response, size)
        offset = acknowledged + 1
        if offset >= size:
            raise ValueError("YouTube session acknowledged all bytes without a video ID")
        return self._send_from(session_id, access_token, asset_path, offset, heartbeat)

    def _send_from(self, session_id: str, access_token: str, asset_path: Path, offset: int, heartbeat: Callable[[], bool]) -> UploadReceipt:
        size = asset_path.stat().st_size
        if size <= 0 or offset < 0 or offset >= size:
            raise ValueError("video size or upload offset is invalid")
        with asset_path.open("rb") as stream:
            stream.seek(offset)
            while offset < size:
                if not heartbeat():
                    raise RuntimeError("delivery lease was lost before the next upload chunk")
                chunk = stream.read(CHUNK_BYTES)
                if not chunk:
                    raise ValueError("video ended before its recorded size")
                end = offset + len(chunk) - 1
                response = self.client.put(
                    session_id,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "video/mp4", "Content-Range": f"bytes {offset}-{end}/{size}"},
                    content=chunk,
                )
                if response.status_code in {200, 201}:
                    return _receipt(response)
                if response.status_code != 308:
                    raise ValueError("YouTube upload outcome needs session reconciliation")
                # A partial acknowledgement must cover exactly this chunk. Any
                # unexpected range is reconciled from the saved session URI.
                if _acknowledged(response, size) != end:
                    raise ValueError("YouTube acknowledged an unexpected upload range")
                offset = end + 1
        raise ValueError("YouTube did not confirm a video ID after the final chunk")

    def inspect(self, *, remote_id: str, external_account_id: str, credential: dict[str, object]) -> RemoteObservation:
        access_token = _token(credential)
        response = self.client.get(
            VIDEOS_URL,
            params={"part": "snippet,status,processingDetails", "id": remote_id},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code != 200:
            raise ValueError("YouTube publication inspection failed")
        items = response.json().get("items", [])
        if not items:
            return RemoteObservation("missing")
        if len(items) != 1 or items[0].get("id") != remote_id:
            raise ValueError("YouTube returned an inconsistent video identity")
        item = items[0]
        snippet = item.get("snippet") or {}
        status = item.get("status") or {}
        processing = (item.get("processingDetails") or {}).get("processingStatus")
        if processing == "failed":
            return RemoteObservation("failed", str(snippet.get("channelId") or ""), snippet.get("title"), snippet.get("description"), privacy=status.get("privacyStatus"))
        return RemoteObservation(
            "published" if processing == "succeeded" else "processing",
            str(snippet.get("channelId") or ""), snippet.get("title"), snippet.get("description"),
            f"https://www.youtube.com/watch?v={remote_id}", status.get("privacyStatus"),
        )

    def inspect_session(self, *, session_id: str, credential: dict[str, object], asset_size: int) -> UploadReceipt | None:
        """Google's empty PUT reports completed IDs or a 308 incomplete range."""
        _session_url(session_id)
        if asset_size <= 0:
            raise ValueError("canonical video size is invalid")
        response = self._status_request(session_id, _token(credential), asset_size)
        if response.status_code == 308:
            return None
        if response.status_code in {200, 201}:
            return _receipt(response)
        raise ValueError("YouTube upload session outcome could not be proven")

    def _status_request(self, session_id: str, access_token: str, asset_size: int) -> httpx.Response:
        return self.client.put(session_id, headers={"Authorization": f"Bearer {access_token}", "Content-Range": f"bytes */{asset_size}", "Content-Length": "0"}, content=b"")


def _token(credential: dict[str, object]) -> str:
    token = credential.get("token")
    if not isinstance(token, str) or not token:
        raise SafePreflightError("YouTube access token is unavailable", category="auth")
    return token


def _session_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or parsed.hostname != "www.googleapis.com" or parsed.port not in {None, 443} or parsed.username or parsed.password or not parsed.path.startswith("/upload/youtube/v3/videos") or parsed.fragment:
        raise ValueError("YouTube returned an invalid resumable session URL")


def _receipt(response: httpx.Response) -> UploadReceipt:
    data = response.json()
    remote_id = data.get("id") if isinstance(data, dict) else None
    if not isinstance(remote_id, str) or not remote_id:
        raise ValueError("YouTube upload response omitted the video ID")
    return UploadReceipt(remote_id, f"https://www.youtube.com/watch?v={remote_id}")


def _acknowledged(response: httpx.Response, size: int) -> int:
    value = response.headers.get("Range", "")
    if not value:
        return -1
    match = re.fullmatch(r"bytes=0-(\d+)", value)
    if match is None:
        raise ValueError("YouTube returned an invalid upload range")
    end = int(match.group(1))
    if end < 0 or end >= size:
        raise ValueError("YouTube acknowledged bytes outside the video")
    return end
