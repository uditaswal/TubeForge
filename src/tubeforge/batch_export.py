"""Atomic, checksum-bound export of an approved batch Short for later publishing.

An export is a folder holding the reviewed final video, its thumbnail and a ``package.json`` with
everything an uploader needs (title, description, tags, thumbnail text, source URLs, QA result and
the reviewed checksums). Nothing here uploads, schedules or calls a platform; ``publish_at`` is
carried as metadata only. ``verify`` re-checks the folder against its own manifest so a consumer
never trusts a stale or altered package.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PACKAGE_VERSION = "batch-export-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def folder_name(short: dict) -> str:
    day = (short.get("publish_at") or "")[:10] or "undated"
    return f"{re.sub(r'[^a-z0-9-]', '-', short['id'].lower())}-{day}"


def _place(source: Path, destination: Path) -> None:
    shutil.copy2(source, destination)  # a real copy: later edits to the source can never alter a staged export


def build_package(*, short: dict, job_id: str, package: dict | None, qa: dict, checksums: dict,
                  identity: str, actor: str, thumbnail_text: str | None) -> dict:
    metadata = (package or {}).get("metadata") or {}
    titles = metadata.get("title_options") or []
    tags = list(dict.fromkeys([*(short.get("tags") or []), *(metadata.get("tags") or [])]))
    sources = list(dict.fromkeys([*(str(url) for url in short.get("sources") or []),
                                  *(str(s.get("url")) for s in (package or {}).get("request", {}).get("sources", []) if isinstance(s, dict) and s.get("url"))]))
    return {
        "version": PACKAGE_VERSION, "published": False,
        "plan_id": short["id"], "job_id": job_id, "channel": short.get("channel"),
        "title": short["title"], "suggested_titles": titles[:5],
        "description": metadata.get("description") or short.get("hook") or short.get("concept", ""),
        "tags": tags, "thumbnail_text": thumbnail_text or (short.get("thumbnail") or {}).get("text") or None,
        "publish_at_metadata": short.get("publish_at"), "source_urls": sources,
        "qa": {"exit_code": qa.get("exit_code"), "artifact_checksum": qa.get("artifact_checksum")},
        "reviewed_identity": identity, "approved_by": actor, "checksums": checksums,
        "exported_at": datetime.now(UTC).isoformat(),
    }


def write_export(root: Path, *, name: str, final: Path, thumbnail: Path | None, package: dict) -> dict:
    """Build the folder beside its final location, verify it, then swap it in atomically."""
    root.mkdir(parents=True, exist_ok=True)
    target, scratch = root / name, root / f".{name}.tmp-{uuid4().hex[:8]}"
    scratch.mkdir()
    try:
        _place(final, scratch / "final.mp4")
        files = {"final.mp4": _sha256(scratch / "final.mp4")}
        if files["final.mp4"] != package["checksums"].get("final"):
            raise ValueError("final video changed while exporting")
        if thumbnail is not None:
            _place(thumbnail, scratch / "thumbnail.jpg")
            files["thumbnail.jpg"] = _sha256(scratch / "thumbnail.jpg")
            if files["thumbnail.jpg"] != package["checksums"].get("thumbnail"):
                raise ValueError("thumbnail changed while exporting")
        document = {**package, "files": files}
        (scratch / "package.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        old = None
        if target.exists():
            old = root / f".{name}.old-{uuid4().hex[:8]}"
            os.replace(target, old)
        os.replace(scratch, target)
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)
    except BaseException:
        shutil.rmtree(scratch, ignore_errors=True)
        raise
    return {"path": str(target), "identity": package["reviewed_identity"], "files": files}


def verify(path: Path, *, identity: str | None = None) -> dict:
    """Status of an export folder: ``current`` only if every file still matches its manifest."""
    try:
        document = json.loads((path / "package.json").read_text(encoding="utf-8"))
        for filename, checksum in document["files"].items():
            if _sha256(path / filename) != checksum:
                return {"status": "invalid", "reason": f"{filename} changed after export"}
    except (OSError, ValueError, KeyError):
        return {"status": "missing", "reason": "export folder or manifest unavailable"}
    if identity is not None and document.get("reviewed_identity") != identity:
        return {"status": "stale", "reason": "reviewed artifact changed after this export"}
    return {"status": "current", "package": document}
