"""Run one job at a time: while a focus is set, the worker takes only that job and everything else waits.

The focus is a small JSON file in the shared data folder (web server and worker both see it), so it needs no database
change and survives restarts. It ends by itself when the focused job reaches a resting state, and the operator can
release it at any time. Nothing is paused or changed on the other jobs: they simply are not picked up until it ends.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

from tubeforge.domain.states import JobState

# States where the focused job has nothing more to run; the focus ends so the queue moves again.
FOCUS_ENDS = frozenset({
    JobState.FINAL_READY, JobState.SCRIPT_APPROVAL_REQUIRED, JobState.PREVIEW_READY, JobState.PUBLICATION_APPROVAL_REQUIRED,
    JobState.PUBLICATION_READY, JobState.PUBLICATION_VERIFICATION_PENDING, JobState.CANCELLED, JobState.FAILED_VALIDATION,
    JobState.FAILED_EXHAUSTED, JobState.AUTH_REQUIRED, JobState.PUBLISHED,
})


class JobFocus:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def current(self) -> dict | None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) and value.get("job_id") else None

    def job_id(self) -> str | None:
        current = self.current()
        return str(current["job_id"]) if current else None

    def set(self, job_id: str, actor: str = "local-dashboard") -> dict:
        record = {"job_id": job_id, "actor": actor, "since": time.time()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=str(self.path.parent), prefix=".focus", suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(record, stream)
        os.replace(temporary, self.path)
        return record

    def clear(self) -> bool:
        try:
            self.path.unlink()
            return True
        except OSError:
            return False


def focus_path(artifact_root: Path) -> Path:
    """data/run/job-focus.json, next to the artifacts folder."""
    return Path(artifact_root).parent / "run" / "job-focus.json"
