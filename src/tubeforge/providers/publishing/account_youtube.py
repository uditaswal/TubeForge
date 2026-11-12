"""Account-scoped YouTube resumable upload adapter with no file-backed token."""
from __future__ import annotations

from pathlib import Path
from datetime import UTC, datetime
import hashlib
import re
from typing import Callable
from urllib.parse import urlsplit

import httpx

from tubeforge.pipeline.delivery_executor import ProviderAuthError, ProviderQuotaError, ProviderRateLimitHint, RemoteObservation, SafePreflightError, UploadReceipt
from tubeforge.pipeline.provider_backoff import provider_hint
from tubeforge.pipeline.youtube_preflight import YouTubePreflightError, check_youtube_short


UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
THUMBNAIL_URL = "https://www.googleapis.com/upload/youtube/v3/thumbnails/set"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
CHUNK_BYTES = 8 * 1024 * 1024


class AccountYouTubeAdapter:
    """Only opens a session; the executor persists it before sending video bytes."""

    def __init__(self, client: httpx.Client | None = None, *, ffprobe: str = "ffprobe", max_bytes: int = 2_000_000_000, category_id: str = "22", self_declared_made_for_kids: bool = False, youtube_api_audited: bool = False, clock: Callable[[], datetime] | None = None) -> None:
        if not re.fullmatch(r"[0-9]{1,6}", category_id) or type(self_declared_made_for_kids) is not bool:
            raise ValueError("YouTube category or made-for-kids setting is invalid")
        self.client = client or httpx.Client(timeout=60, follow_redirects=False)
        self.ffprobe, self.max_bytes = ffprobe, max_bytes
        if type(youtube_api_audited) is not bool:
            raise ValueError("YouTube audit setting must be boolean")
        self.category_id, self.self_declared_made_for_kids = category_id, self_declared_made_for_kids
        self.youtube_api_audited = youtube_api_audited
        self.clock = clock or (lambda: datetime.now(UTC))

    def preflight(self, *, asset_path: Path, metadata: dict[str, object]) -> None:
        if metadata.get("visibility", "private") != "private":
            raise SafePreflightError("only private YouTube uploads are currently permitted")
        if type(metadata.get("contains_synthetic_media")) is not bool:
            raise SafePreflightError("reviewed synthetic-media disclosure is required")
        scheduled = metadata.get("scheduled_for")
        if scheduled is not None and self.youtube_api_audited and metadata.get("schedule_audit_allowed") is True:
            try:
                stamp = datetime.fromisoformat(str(scheduled).replace("Z", "+00:00"))
                if stamp.utcoffset() is None or stamp <= self.clock():
                    raise ValueError("past or naive time")
            except (ValueError, TypeError) as error:
                raise SafePreflightError("scheduled YouTube publish time must be in the future") from error
        digest = metadata.get("thumbnail_sha256")
        if digest is not None and _thumbnail_content(asset_path, digest) is None:
            raise SafePreflightError("reviewed thumbnail is unavailable or changed")
        try:
            check_youtube_short(asset_path, ffprobe=self.ffprobe, max_bytes=self.max_bytes)
        except YouTubePreflightError as error:
            raise SafePreflightError(str(error)) from error

    def open_session(self, *, external_account_id: str, credential: dict[str, object], asset_path: Path, metadata: dict[str, object]) -> str:
        self.preflight(asset_path=asset_path, metadata=metadata)
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
            category = _response_category(identity)
            raise SafePreflightError("YouTube channel identity could not be checked", category=category, retry_after_seconds=provider_hint(identity.headers))
        usage_hint = provider_hint(identity.headers)
        if usage_hint is not None:
            raise SafePreflightError("YouTube provider requested a delay before upload", category="retry", retry_after_seconds=usage_hint)
        try:
            channels = identity.json().get("items", [])
        except (ValueError, AttributeError) as error:
            raise SafePreflightError("YouTube channel identity response is invalid", category="retry") from error
        if not isinstance(channels, list) or len(channels) != 1 or not isinstance(channels[0], dict) or channels[0].get("id") != external_account_id:
            raise SafePreflightError("YouTube token does not belong to the selected channel", category="auth")
        status = {"privacyStatus": visibility, "selfDeclaredMadeForKids": self.self_declared_made_for_kids, "containsSyntheticMedia": metadata["contains_synthetic_media"]}
        if self.youtube_api_audited and metadata.get("schedule_audit_allowed") is True and metadata.get("scheduled_for") is not None:
            scheduled = datetime.fromisoformat(str(metadata["scheduled_for"]).replace("Z", "+00:00"))
            if scheduled <= self.clock():
                raise SafePreflightError("scheduled YouTube publish time must be in the future")
            status["publishAt"] = scheduled.astimezone(UTC).isoformat().replace("+00:00", "Z")
        response = self.client.post(
            UPLOAD_URL,
            params={"uploadType": "resumable", "part": "snippet,status"},
            headers={"Authorization": f"Bearer {access_token}", "X-Upload-Content-Length": str(asset_path.stat().st_size), "X-Upload-Content-Type": "video/mp4"},
            json={"snippet": {"title": title, "description": description, "tags": tags, "categoryId": self.category_id}, "status": status},
        )
        if response.status_code != 200:
            if response.status_code in {400, 401, 403, 429}:
                raise SafePreflightError("YouTube rejected upload session creation", category=_response_category(response), retry_after_seconds=provider_hint(response.headers))
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
        content = _thumbnail_content(asset_path, digest)
        if content is None:
            return
        try:
            self.client.post(THUMBNAIL_URL, params={"videoId": remote_id}, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "image/jpeg"}, content=content)
        except httpx.HTTPError:
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
            _raise_provider_error(response)
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
                    _raise_provider_error(response)
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
            _raise_provider_error(response)
            raise ValueError("YouTube publication inspection failed")
        usage_hint = provider_hint(response.headers)
        if usage_hint is not None:
            raise ProviderRateLimitHint(usage_hint)
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
            f"https://www.youtube.com/watch?v={remote_id}", status.get("privacyStatus"), status.get("publishAt"),
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
        _raise_provider_error(response)
        raise ValueError("YouTube upload session outcome could not be proven")

    def _status_request(self, session_id: str, access_token: str, asset_size: int) -> httpx.Response:
        return self.client.put(session_id, headers={"Authorization": f"Bearer {access_token}", "Content-Range": f"bytes */{asset_size}", "Content-Length": "0"}, content=b"")


def _response_category(response: httpx.Response) -> str:
    if response.status_code == 429:
        return "retry"
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
        errors = error.get("errors", []) if isinstance(error, dict) else []
        reasons = {item.get("reason") for item in errors if isinstance(item, dict)}
    except (ValueError, TypeError):
        reasons = set()
    if reasons & {"quotaExceeded", "dailyLimitExceeded", "uploadLimitExceeded"}:
        return "quota"
    if reasons & {"rateLimitExceeded", "userRateLimitExceeded"}:
        return "retry"
    if response.status_code in {401, 403}:
        return "auth"
    return "invalid" if response.status_code == 400 else "retry"


def _raise_provider_error(response: httpx.Response) -> None:
    category = _response_category(response)
    if category == "quota":
        raise ProviderQuotaError("YouTube quota exhausted")
    if category == "auth":
        raise ProviderAuthError("YouTube account requires reconnection")
    if response.status_code == 429 or (response.status_code == 403 and category == "retry"):
        raise ProviderRateLimitHint(provider_hint(response.headers) or 120)


def _thumbnail_content(asset_path: Path, digest: object) -> bytes | None:
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return None
    path = asset_path.parent / "thumbnails" / f"{digest}.jpg"
    try:
        if path.parent.is_symlink() or path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 2_000_000:
            return None
        content = path.read_bytes()
        return content if hashlib.sha256(content).hexdigest() == digest else None
    except OSError:
        return None


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
