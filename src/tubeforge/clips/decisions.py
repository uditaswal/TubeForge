"""A short audit log of the choices a clip run made, so "why this clip?" and "why no captions?" have an answer.

One JSON line per decision goes to ``decisions.jsonl`` in the run's work folder: which engagement signals existed, which
parts of the video were transcribed, what the AI picked and what was dropped afterwards, and for each clip whether faces
were tracked or the crop fell back to the default, and whether captions were burned in or skipped (and why).

Logging never changes a result: every failure here is swallowed, and without an active run (tests, the editor) it does nothing.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)
DECISIONS_FILE = "decisions.jsonl"

_lock = threading.Lock()
_path: Optional[Path] = None
_clip: Optional[int] = None


def begin(work_dir: Path | str) -> None:
    """Start writing this run's decisions into ``work_dir`` (appends, so a resumed run keeps the earlier lines)."""
    global _path, _clip
    _path, _clip = Path(work_dir) / DECISIONS_FILE, None


def end() -> None:
    global _path, _clip
    _path, _clip = None, None


def set_clip(number: Optional[int]) -> None:
    """Later decisions belong to this clip (1-based), or to no clip when ``None``."""
    global _clip
    _clip = number


def record(area: str, outcome: str, reason: str = "", **facts: Any) -> None:
    """Add one decision: ``area`` (signals, windows, candidates, faces, layout, captions...), what happened and why."""
    path = _path
    if path is None:
        return
    entry: dict[str, Any] = {"at": round(time.time(), 1), "area": area, "outcome": outcome}
    if reason:
        entry["reason"] = reason
    if _clip is not None:
        entry["clip"] = _clip
    if facts:
        entry["facts"] = facts
    try:
        line = json.dumps(entry, default=str, ensure_ascii=False)
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
    except Exception:
        logger.debug("Could not record a clip decision", exc_info=True)


def read(work_dir: Path | str) -> list[dict[str, Any]]:
    """Every recorded decision, oldest first; unreadable lines are skipped."""
    try:
        lines = (Path(work_dir) / DECISIONS_FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries
