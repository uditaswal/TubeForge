"""Local file sources. A source file already on disk needs no copying or restore."""

from __future__ import annotations

from pathlib import Path


def read_upload_reference(path: Path) -> str | None:
    return None


def upload_needs_remote_copy(url: str) -> bool:
    return False


async def materialize_stored_upload(url: str) -> Path | None:
    return None


async def persist_local_upload(*args, **kwargs) -> None:
    return None


async def ensure_local_upload_durable(path: Path) -> None:
    return None
