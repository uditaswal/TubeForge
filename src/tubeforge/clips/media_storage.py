"""Local-only media storage.

The clip pipeline keeps every file on local disk under the job's work folder.
This module keeps the small surface the pipeline calls so no object storage is
involved: ``enabled`` is always false and the helpers are no-ops.
"""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

STORAGE_ERRORS = (OSError,)
_workspace: ContextVar[dict | None] = ContextVar("media_workspace", default=None)


class MediaStorage:
    enabled = False

    def local_path(self, reference: str) -> Path:
        return Path(reference)

    def source_reference(self, url: str) -> str:
        return url

    def validate_source(self, url: str, user_id: str | None = None) -> str:
        raise ValueError("Remote object sources are not supported")

    def signed_url(self, reference: str, name: str, expires_in: int = 300) -> str:
        raise ValueError("Remote object sources are not supported")

    def restore_youtube_metadata(self, video_id: str, path: Path) -> None:
        return None

    def save_source_metadata(self, path: Path) -> None:
        return None

    def store_capped_source(self, path: Path) -> None:
        return None
