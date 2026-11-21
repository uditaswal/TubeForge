"""Scratch space on the data disk.

Services run with ``TMPDIR=/app/data/tmp`` (see compose.yaml) so downloads, extracted audio and render scratch files never depend on
a small RAM-backed ``/tmp``. This makes sure the folder exists and clears leftovers from a crashed run: only entries not touched for a
day are removed, and only inside that dedicated folder.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)
STALE_SECONDS = 24 * 3600


def ensure_tempdir(max_age_seconds: int = STALE_SECONDS) -> Path | None:
    """Create ``$TMPDIR`` when the service sets it, and sweep entries older than ``max_age_seconds``. Never raises."""
    configured = os.environ.get("TMPDIR", "").strip()
    if not configured:
        return None
    folder = Path(configured)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        cutoff = time.time() - max_age_seconds
        for entry in folder.iterdir():
            try:
                if entry.stat().st_mtime >= cutoff:
                    continue
                shutil.rmtree(entry) if entry.is_dir() and not entry.is_symlink() else entry.unlink()
            except OSError:
                continue
    except OSError as error:
        logger.warning("Could not prepare the temp folder %s: %s", folder, error)
        return None
    return folder
