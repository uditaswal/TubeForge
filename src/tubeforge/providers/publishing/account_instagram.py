"""Account-scoped Instagram Reels adapter (Instagram Login, resumable upload from local disk).

Flow: preflight (identity, publishing quota, public-post confirmation) -> create a REELS
container with ``upload_type=resumable`` -> record the container -> send bytes to the
rupload host -> wait for ``FINISHED`` -> ``media_publish`` exactly once.  A container that
is already ``PUBLISHED`` is never re-published and its media id is never guessed.
"""
from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Callable
from urllib.parse import urlsplit

import httpx

from tubeforge.pipeline.delivery_executor import RemoteObservation, SafePreflightError, UploadReceipt

GRAPH = "https://graph.instagram.com/v21.0"
RUPLOAD = "https://rupload.facebook.com/ig-api-upload/v21.0"
MAX_BYTES = 300 * 1024 * 1024
CAPTION_LIMIT = 2_200
HASHTAG_LIMIT = 30
CONTAINER_LIFETIME_SECONDS = 24 * 3600


def instagram_full_caption(metadata: dict[str, object]) -> str:
    """Caption plus the reviewed hashtag block: the one text that is sent and later compared."""
    caption = str(metadata.get("caption") or "").strip()
    tags = metadata.get("hashtags") or []
    block = " ".join(tag for tag in tags if isinstance(tag, str)) if isinstance(tags, list) else ""
    return f"{caption}\n\n{block}" if block else caption


class AccountInstagramAdapter:
    def __init__(self, client: httpx.Client | None = None, *, poll_seconds: float = 5.0, max_polls: int = 120, sleep: Callable[[float], None] = time.sleep) -> None:
        self.client = client or httpx.Client(timeout=60, follow_redirects=False)
        self.poll_seconds, self.max_polls, self._sleep = poll_seconds, max_polls, sleep

    # -- preflight and container -------------------------------------------------
    def open_session(self, *, external_account_id: str, credential: dict[str, object], asset_path: Path, metadata: dict[str, object]) -> str:
        token = _token(credential)
        caption = instagram_full_caption(metadata)
        if not caption or len(caption) > CAPTION_LIMIT or len(_tags(metadata)) > HASHTAG_LIMIT:
            raise SafePreflightError("Instagram caption or hashtags are invalid")
        if metadata.get("confirm_public") is not True:
            raise SafePreflightError("Instagram posts are public at once; explicit confirmation is missing")
        size = asset_path.stat().st_size
        if size <= 0 or size > MAX_BYTES:
            raise SafePreflightError("video size is outside Instagram's Reels limit")
        identity = self._get(f"{GRAPH}/me", token, {"fields": "user_id,account_type"}, retry_ok=True)
        if str(identity.get("user_id") or "") != external_account_id:
            raise SafePreflightError("Instagram token does not belong to the selected account", category="auth")
        limit = self._get(f"{GRAPH}/{external_account_id}/content_publishing_limit", token, {"fields": "quota_usage,config"}, retry_ok=True)
        rows = limit.get("data") if isinstance(limit.get("data"), list) else []
        if rows and isinstance(rows[0], dict):
            used = rows[0].get("quota_usage")
            total = (rows[0].get("config") or {}).get("quota_total", 100) if isinstance(rows[0].get("config"), dict) else 100
            if isinstance(used, int) and isinstance(total, int) and used >= total:
                raise SafePreflightError("Instagram's 24-hour publishing limit is reached", category="retry")
        response = self.client.post(f"{GRAPH}/{external_account_id}/media", headers=_bearer(token), data={
            "media_type": "REELS", "upload_type": "resumable", "caption": caption, "share_to_feed": "true",
        })
        data = _json(response)
        container, uri = data.get("id"), data.get("uri")
        if response.status_code != 200 or not isinstance(container, str) or not container or not isinstance(uri, str):
            raise ValueError("Instagram did not open a resumable container")
        _rupload_url(uri, container)
        return json.dumps({"c": container, "u": uri}, separators=(",", ":"))

    # -- upload and publish ------------------------------------------------------
    def upload(self, *, session_id: str, external_account_id: str, credential: dict[str, object], asset_path: Path, metadata: dict[str, object], heartbeat: Callable[[], bool]) -> UploadReceipt:
        container, uri = _session(session_id)
        token = _token(credential)
        self._send(uri, token, asset_path, 0, heartbeat)
        return self._finish(container, external_account_id, token, heartbeat)

    def resume_session(self, *, session_id: str, credential: dict[str, object], asset_path: Path, heartbeat: Callable[[], bool], metadata: dict[str, object] | None = None) -> UploadReceipt:
        container, uri = _session(session_id)
        token = _token(credential)
        metadata_caption = instagram_full_caption(metadata) if metadata else None
        state = self._status(container, token)
        if state in {"PUBLISHED", "ERROR", "EXPIRED"}:
            raise ValueError(f"Instagram container is {state}; it cannot be continued")
        if state != "FINISHED":
            offset = self._offset(uri, token)
            if offset < asset_path.stat().st_size:
                self._send(uri, token, asset_path, offset, heartbeat)
        user = self._user_id(token)
        self._refuse_if_already_posted(user, token, metadata_caption)
        return self._finish(container, user, token, heartbeat)

    def inspect_session(self, *, session_id: str, credential: dict[str, object], asset_size: int) -> UploadReceipt | None:
        container, _ = _session(session_id)
        state = self._status(container, _token(credential))
        if state == "PUBLISHED":
            raise ValueError("Instagram reports the container published but exposes no media id; check the account")
        if state in {"ERROR", "EXPIRED"}:
            raise ValueError(f"Instagram container is {state}")
        return None  # not provably published: the operator may resume the same container

    def inspect(self, *, remote_id: str, external_account_id: str, credential: dict[str, object]) -> RemoteObservation:
        token = _token(credential)
        response = self.client.get(f"{GRAPH}/{remote_id}", headers=_bearer(token), params={"fields": "id,permalink,caption,owner,media_type"})
        error = _json(response).get("error")
        error = error if isinstance(error, dict) else {}
        if response.status_code == 400 and (error.get("code") == 33 or (error.get("code") == 100 and error.get("error_subcode") == 33)):
            return RemoteObservation("missing")
        if response.status_code != 200:
            raise ValueError("Instagram publication inspection failed")
        data = _json(response)
        if data.get("id") != remote_id:
            raise ValueError("Instagram returned an inconsistent media identity")
        owner = (data.get("owner") or {}).get("id") if isinstance(data.get("owner"), dict) else None
        return RemoteObservation("published", str(owner or ""), None, data.get("caption"), data.get("permalink"))

    # -- internals ---------------------------------------------------------------
    def _finish(self, container: str, user_id: str, token: str, heartbeat: Callable[[], bool]) -> UploadReceipt:
        for _ in range(self.max_polls):
            if not heartbeat():
                raise RuntimeError("delivery lease was lost while Instagram processed the video")
            state = self._status(container, token)
            if state == "FINISHED":
                break
            if state in {"ERROR", "EXPIRED", "PUBLISHED"}:
                raise ValueError(f"Instagram container is {state}")
            self._sleep(self.poll_seconds)
        else:
            raise ValueError("Instagram is still processing the video; reconcile the saved container")
        if not heartbeat():
            raise RuntimeError("delivery lease was lost before publishing")
        response = self.client.post(f"{GRAPH}/{user_id}/media_publish", headers=_bearer(token), data={"creation_id": container})
        media = _json(response).get("id")
        if response.status_code != 200 or not isinstance(media, str) or not media:
            raise ValueError("Instagram publish outcome needs reconciliation")
        permalink = None
        try:
            info = self.client.get(f"{GRAPH}/{media}", headers=_bearer(token), params={"fields": "permalink"})
            permalink = _json(info).get("permalink") if info.status_code == 200 else None
        except httpx.HTTPError:
            permalink = None
        return UploadReceipt(media, permalink if isinstance(permalink, str) else None)

    def _refuse_if_already_posted(self, user_id: str, token: str, caption: str | None) -> None:
        """A lost publish response may not yet show as PUBLISHED; never publish again if the post exists."""
        data = self._get(f"{GRAPH}/{user_id}/media", token, {"fields": "id,caption,timestamp", "limit": "10"})
        rows = data.get("data") if isinstance(data.get("data"), list) else []
        if caption is None and rows:
            raise ValueError("recent posts exist and the reviewed caption is unavailable; check the account")
        if any(isinstance(row, dict) and row.get("caption") == caption for row in rows):
            raise ValueError("a recent post with the reviewed caption already exists; check the account before retrying")

    def _send(self, uri: str, token: str, asset_path: Path, offset: int, heartbeat: Callable[[], bool]) -> None:
        size = asset_path.stat().st_size
        if size <= 0 or size > MAX_BYTES or offset < 0 or offset >= size or not heartbeat():
            raise ValueError("video size, offset or delivery lease is invalid")
        with asset_path.open("rb") as stream:
            stream.seek(offset)
            body = stream.read()
        response = self.client.post(uri, headers={"Authorization": f"OAuth {token}", "offset": str(offset), "file_size": str(size)}, content=body)
        if response.status_code != 200 or _json(response).get("success") is not True:
            raise ValueError("Instagram upload outcome needs reconciliation")

    def _offset(self, uri: str, token: str) -> int:
        response = self.client.get(uri, headers={"Authorization": f"OAuth {token}"})
        value = _json(response).get("file_offset")
        if response.status_code != 200 or not isinstance(value, int) or value < 0:
            raise ValueError("Instagram upload offset could not be proven")
        return value

    def _status(self, container: str, token: str) -> str:
        data = self._get(f"{GRAPH}/{container}", token, {"fields": "status_code"})
        state = data.get("status_code")
        if not isinstance(state, str):
            raise ValueError("Instagram container status is unavailable")
        return state

    def _user_id(self, token: str) -> str:
        user = str(self._get(f"{GRAPH}/me", token, {"fields": "user_id"}).get("user_id") or "")
        if not user:
            raise ValueError("Instagram account identity is unavailable")
        return user

    def _get(self, url: str, token: str, params: dict[str, str], *, retry_ok: bool = False) -> dict[str, object]:
        try:
            response = self.client.get(url, headers=_bearer(token), params=params)
        except httpx.HTTPError as error:
            if retry_ok:
                raise SafePreflightError("Instagram is temporarily unavailable", category="retry") from error
            raise
        if response.status_code != 200:
            if retry_ok:
                raise SafePreflightError("Instagram could not be checked", category="auth" if response.status_code in {401, 403} else "retry")
            raise ValueError("Instagram request failed")
        return _json(response)


def _tags(metadata: dict[str, object]) -> list[str]:
    tags = metadata.get("hashtags") or []
    return [tag for tag in tags if isinstance(tag, str)] if isinstance(tags, list) else []


def _token(credential: dict[str, object]) -> str:
    token = credential.get("token")
    if not isinstance(token, str) or not token:
        raise SafePreflightError("Instagram access token is unavailable", category="auth")
    return token


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _json(response: httpx.Response) -> dict[str, object]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _rupload_url(uri: str, container: str) -> None:
    parsed = urlsplit(uri)
    if parsed.scheme != "https" or parsed.hostname != "rupload.facebook.com" or parsed.port not in {None, 443} or parsed.username or parsed.password or parsed.fragment or container not in parsed.path:
        raise ValueError("Instagram returned an invalid upload URL")


def _session(session_id: str) -> tuple[str, str]:
    try:
        data = json.loads(session_id)
        container, uri = data["c"], data["u"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("saved Instagram session is invalid") from error
    if not isinstance(container, str) or not isinstance(uri, str):
        raise ValueError("saved Instagram session is invalid")
    _rupload_url(uri, container)
    return container, uri
