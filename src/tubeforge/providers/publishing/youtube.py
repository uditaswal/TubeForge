"""Official Google-client M13 adapter; headless operation never starts OAuth UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from tubeforge.core.config import YouTubePublishingConfig
from tubeforge.core.errors import AmbiguousProviderError, ProviderAuthenticationError, ProviderCancellation, ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import PublishPrivacy, PublishRequest, RemoteProcessingState, RemotePublicationSnapshot

SCOPES = ("https://www.googleapis.com/auth/youtube.upload",)


class YouTubeDataApiPublisher:
    """Small adapter around official clients, with file-backed resumable uploads."""
    def __init__(self, config: YouTubePublishingConfig, *, build_service: Callable[..., Any] | None = None) -> None:
        self.config = config; self._build_service = build_service; self._service: Any | None = None

    def _client(self) -> Any:
        if self._service is not None: return self._service
        if self.config.client_secret_path is None or self.config.token_storage_path is None:
            raise ProviderAuthenticationError("YouTube OAuth paths are not configured")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
        except ImportError as error:
            raise ProviderValidationError("install TubeForge Google publishing dependencies") from error
        token = Path(self.config.token_storage_path)
        if not token.is_file():
            raise ProviderAuthenticationError("YouTube token is missing; run explicit interactive authorization before headless publishing")
        try: credentials = Credentials.from_authorized_user_file(str(token), SCOPES)
        except Exception as error: raise ProviderAuthenticationError("YouTube token is invalid") from error
        if not credentials.valid:
            if credentials.expired and credentials.refresh_token:
                try: credentials.refresh(Request()); token.write_text(credentials.to_json(), encoding="utf-8")
                except Exception as error: raise ProviderAuthenticationError("YouTube token refresh failed") from error
            else: raise ProviderAuthenticationError("YouTube token cannot be refreshed; run explicit interactive authorization")
        self._service = (self._build_service or build)("youtube", "v3", credentials=credentials, cache_discovery=False); return self._service

    def authenticated_channel_id(self) -> str:
        response = self._client().channels().list(part="id", mine=True).execute()
        items = response.get("items", [])
        if not items or not items[0].get("id"): raise ProviderAuthenticationError("authenticated Google account has no YouTube channel")
        return str(items[0]["id"])

    def create_or_resume_video(self, request: PublishRequest, *, resume_token: str | None = None, cancellation_requested: Callable[[], bool] | None = None) -> str:
        try:
            from googleapiclient.http import MediaFileUpload
            body = {"snippet": {"title": request.metadata.title_options[0], "description": request.metadata.description, "tags": list(request.metadata.tags)}, "status": {"privacyStatus": request.privacy.value}}
            media = MediaFileUpload(request.artifact_path, resumable=True, chunksize=self.config.chunk_size_bytes)
            operation = self._client().videos().insert(part="snippet,status", body=body, media_body=media)
            response = None
            while response is None:
                if cancellation_requested and cancellation_requested():
                    raise ProviderCancellation("YouTube upload cancelled before next resumable chunk")
                _, response = operation.next_chunk()
            remote_id = response.get("id")
            if not remote_id: raise ProviderValidationError("YouTube upload did not return a video id")
            return str(remote_id)
        except (ProviderCancellation, ProviderValidationError): raise
        except Exception as error: raise _classify_google_error(error, ambiguous=True) from error

    def apply_metadata(self, remote_video_id: str, request: PublishRequest) -> None:
        try: self._client().videos().update(part="snippet,status", body={"id": remote_video_id, "snippet": {"title": request.metadata.title_options[0], "description": request.metadata.description, "tags": list(request.metadata.tags)}, "status": {"privacyStatus": request.privacy.value}}).execute()
        except Exception as error: raise _classify_google_error(error) from error

    def set_thumbnail(self, remote_video_id: str, thumbnail_path: str) -> None:
        try: self._client().thumbnails().set(videoId=remote_video_id, media_body=thumbnail_path).execute()
        except Exception as error: raise _classify_google_error(error) from error

    def fetch_video(self, remote_video_id: str) -> dict[str, object] | None:
        snapshot = self.fetch_publication_snapshot(remote_video_id)
        return None if not snapshot.exists else {"privacy": snapshot.privacy.value if snapshot.privacy else None, "title": snapshot.title, "description": snapshot.description, "processing": snapshot.processing.value}

    def fetch_publication_snapshot(self, remote_video_id: str) -> RemotePublicationSnapshot:
        try:
            items = self._client().videos().list(part="snippet,status,processingDetails", id=remote_video_id).execute().get("items", [])
            if not items: return RemotePublicationSnapshot(video_id=remote_video_id, exists=False)
            item = items[0]; details = item.get("processingDetails", {}) or {}; status = str(details.get("processingStatus", "unknown"))
            processing = {"processing": RemoteProcessingState.PROCESSING, "succeeded": RemoteProcessingState.SUCCEEDED, "failed": RemoteProcessingState.FAILED}.get(status, RemoteProcessingState.UNKNOWN)
            snippet = item.get("snippet", {}) or {}; remote_status = item.get("status", {}) or {}
            privacy = remote_status.get("privacyStatus")
            return RemotePublicationSnapshot(video_id=remote_video_id, exists=True, processing=processing, processing_reason=details.get("processingFailureReason") or details.get("processingIssuesAvailability"), privacy=PublishPrivacy(privacy) if privacy in {"private", "unlisted", "public"} else None, title=snippet.get("title"), description=snippet.get("description"), tags=tuple(snippet["tags"]) if isinstance(snippet.get("tags"), list) else None, thumbnail_present=bool((snippet.get("thumbnails") or {})))
        except Exception as error: raise _classify_google_error(error) from error


def _classify_google_error(error: Exception, *, ambiguous: bool = False) -> Exception:
    status = getattr(getattr(error, "resp", None), "status", None)
    if status in {401}: return ProviderAuthenticationError("YouTube authentication failed")
    if status in {403, 404, 400}: return ProviderValidationError("YouTube rejected the publication request")
    if status in {408, 429, 500, 502, 503, 504}: return RetryableProviderError("YouTube temporary failure")
    return AmbiguousProviderError("YouTube upload result is unknown; reconcile before any new upload") if ambiguous else RetryableProviderError("YouTube request failed")
