"""Cross-process lock around the shared YouTube cache, using a lock file."""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import os
import tempfile
from pathlib import Path


@contextlib.contextmanager
def advisory_lock(name: str):
    folder = Path(os.environ.get("TUBEFORGE_CLIPS_LOCK_DIR") or tempfile.gettempdir())
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"clips-{hashlib.sha256(name.encode()).hexdigest()[:24]}.lock"
    with open(path, "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
