"""Where a clip job's time goes: a small, persisted list of stages with how long each took.

The engine already reports a message at the start of every step ("Downloading video...", "Generating transcript...",
"Creating clip 2/3..."). Each new message closes the previous stage and opens the next, so no step needs to be
instrumented by hand. The list lives in a JSON file next to the job's other work files and survives a restart.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

TIMINGS_FILE = "timings.json"

# (start of the engine's message, stage key, what the operator reads)
_STAGES = (
    ("downloading selected segments", "sections", "Downloading the chosen sections"),
    ("downloading video", "download", "Downloading the video (or its audio)"),
    ("storing upload", "prepare", "Preparing the video"),
    ("preparing video", "prepare", "Preparing the video"),
    ("generating transcript", "transcription", "Transcribing speech"),
    ("reading the whole video", "transcription", "Transcribing speech"),
    ("analyzing content with ai", "ai", "AI picks the moments"),
)
_CLIP = re.compile(r"creating clip (\d+)\s*/\s*(\d+)", re.IGNORECASE)


def classify(message: str) -> Optional[tuple[str, str]]:
    """(key, label) for an engine message, or None for one that is not the start of a new stage."""
    text = (message or "").strip().lower()
    clip = _CLIP.search(text)
    if clip:
        return f"render-{clip.group(1)}", f"Rendering clip {clip.group(1)} of {clip.group(2)}"
    for prefix, key, label in _STAGES:
        if text.startswith(prefix):
            return key, label
    return None


class StageClock:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.stages: list[dict] = list(data.get("stages") or [])
        except (OSError, ValueError):
            self.stages = []

    def _close(self, now: float) -> None:
        if self.stages and self.stages[-1].get("seconds") is None:
            self.stages[-1]["seconds"] = round(max(0.0, now - self.stages[-1]["started_at"]), 2)

    def tick(self, message: str, now: Optional[float] = None) -> None:
        """A step started: close the stage that was running and open the one this message names."""
        found = classify(message)
        if found is None:
            return
        now = time.time() if now is None else now
        key, label = found
        if self.stages and self.stages[-1].get("key") == key and self.stages[-1].get("seconds") is None:
            return  # the same stage reporting again (a progress update), not a new one
        self._close(now)
        self.stages.append({"key": key, "label": label, "started_at": now, "seconds": None})
        self._save()

    def close(self, now: Optional[float] = None) -> None:
        """The run (or this part of it) ended: the open stage stops here."""
        self._close(time.time() if now is None else now)
        self._save()

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, temporary = tempfile.mkstemp(dir=str(self.path.parent), prefix=".timings", suffix=".tmp")
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump({"stages": self.stages}, stream)
            os.replace(temporary, self.path)
        except OSError:
            pass  # a convenience file: a full disk must not fail the job


def summarize(stages: list[dict], now: Optional[float] = None) -> dict:
    """Rows for the Clips page: each stage's seconds (a running stage counts up to now) and the total."""
    now = time.time() if now is None else now
    rows = []
    for stage in stages:
        running = stage.get("seconds") is None
        seconds = round(max(0.0, now - stage["started_at"]), 1) if running else float(stage["seconds"])
        rows.append({"key": stage["key"], "label": stage["label"], "seconds": seconds, "running": running})
    return {"rows": rows, "total_seconds": round(sum(r["seconds"] for r in rows), 1)}
