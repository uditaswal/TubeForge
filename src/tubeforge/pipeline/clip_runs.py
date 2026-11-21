"""Runs the clip engine for a clip job, between TubeForge's durable stages.

Cancellation surfaces as ``tubeforge.clips.cancellation.TaskCancelled``. The engine is asynchronous; the worker is not. Each stage opens its own event loop, so a worker
that dies mid-stage simply repeats that stage and the engine's file-backed checkpoint resumes it.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from tubeforge.core.config import SourceClipConfig


class ClipRunner(Protocol):
    def analyze(self, job_id: str, work_dir: Path, params: dict[str, Any], cancelled: Callable[[], bool] | None) -> dict[str, Any]: ...

    def render(self, job_id: str, work_dir: Path, params: dict[str, Any], cancelled: Callable[[], bool] | None) -> list[dict[str, Any]]: ...


PROGRESS_FILE = "progress.json"


def write_progress(work_dir: Path, stage: str, percent: int, message: str) -> None:
    """Record what the engine is doing right now (read by the Clips page; never part of the job's durable state)."""
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=str(work_dir), prefix=".progress", suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump({"stage": stage, "percent": int(percent), "message": message, "updated_at": time.time()}, stream)
        os.replace(temporary, work_dir / PROGRESS_FILE)
    except OSError:
        pass  # progress is a convenience; a full disk must not fail the job


class EngineClipRunner:
    def __init__(self, config: SourceClipConfig, *, transport=None, whisper_model: str | None = None, keepalive_seconds: float = 30.0) -> None:
        self.config, self.transport, self.whisper_model, self.keepalive_seconds = config, transport, whisper_model, keepalive_seconds

    @contextlib.contextmanager
    def _keepalive(self, cancelled: Callable[[], bool] | None):
        """Poll the worker's guard while a long stage runs: a download or render can take far longer than
        the lease, and the guard renews the job and heavy-work leases only when it is polled."""
        stop = threading.Event()

        def poll() -> None:
            while not stop.wait(self.keepalive_seconds):
                try:
                    if cancelled:
                        cancelled()
                except Exception:  # a failed poll must never stop the stage; the next one retries
                    pass

        thread = threading.Thread(target=poll, daemon=True, name="clip-lease-keepalive")
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=5)

    def _engine(self, work_dir: Path, params: dict[str, Any] | None = None):
        # Imported here so a worker image without the clip dependencies still starts and runs Shorts.
        from tubeforge.clips.engine import ClipEngine, FileClipStore

        return ClipEngine(FileClipStore(work_dir / "state"), transport=self.transport, whisper_model=(params or {}).get("whisper_model") or self.whisper_model)

    @staticmethod
    def request(work_dir: Path, params: dict[str, Any]):
        from tubeforge.clips.engine import ClipRequest

        return ClipRequest(
            url=params["source_url"], work_dir=work_dir, clip_count=int(params["clip_count"]),
            captions=bool(params["captions"]), engaging_only=bool(params.get("engaging_only", True)),
            max_clip_seconds=float(params["max_clip_seconds"]) if params.get("max_clip_seconds") else None,
            max_video_duration=int(params["max_source_seconds"]) if params.get("max_source_seconds") else None,
            max_download_bytes=int(params["max_download_bytes"]) if params.get("max_download_bytes") else None,
            source_window=tuple(params["source_window"]) if params.get("source_window") else None,
            cache_dir=Path(params["cache_dir"]) if params.get("cache_dir") else None,
            instructions=params.get("instructions") or None,
            direct_sections=params.get("direct_sections"), download_connections=params.get("download_connections"),
            cookies_file=Path(params["cookies_file"]) if params.get("cookies_file") else None,
            **{name: params[name] for name in ("signal_windows", "signal_window_before", "signal_window_after", "whisper_threads", "max_height", "cache_days", "analysis_window_max_chars") if params.get(name)},
        )

    @staticmethod
    def _cancel(cancelled: Callable[[], bool] | None):
        async def should_cancel() -> bool:
            return bool(cancelled and cancelled())
        return should_cancel

    @staticmethod
    def _progress(work_dir: Path, stage: str):
        from tubeforge.clips.stage_clock import StageClock, TIMINGS_FILE
        clock = StageClock(work_dir / TIMINGS_FILE)

        async def report(percent: int, message: str) -> None:
            write_progress(work_dir, stage, percent, message)
            clock.tick(message)
        return report

    @staticmethod
    def _close_timings(work_dir: Path) -> None:
        """This part of the run ended (or failed): the stage that was open stops counting here."""
        from tubeforge.clips.stage_clock import StageClock, TIMINGS_FILE
        StageClock(work_dir / TIMINGS_FILE).close()

    @staticmethod
    def _adopt_earlier_downloads(work_dir: Path, params: dict[str, Any]) -> None:
        """Videos that earlier jobs downloaded into their own folders join the shared cache, so a retry is not a new download."""
        if not params.get("cache_dir"):
            return
        from tubeforge.clips.youtube_source import adopt_cache_dirs

        artifact_root = work_dir.parent.parent  # <artifacts>/<job>/clip-work
        folders = [folder for folder in artifact_root.glob("*/clip-work/temp/youtube-cache/*") if folder.is_dir()]
        adopt_cache_dirs(folders, Path(params["cache_dir"]))

    def analyze(self, job_id, work_dir, params, cancelled=None):
        write_progress(work_dir, "analyze", 5, "Starting")
        self._adopt_earlier_downloads(work_dir, params)
        try:
            with self._keepalive(cancelled):
                analysis = asyncio.run(self._engine(work_dir, params).analyze(self.request(work_dir, params), progress=self._progress(work_dir, "analyze"), should_cancel=self._cancel(cancelled)))
        finally:
            self._close_timings(work_dir)
        return {"video_path": analysis.video_path, "segments": analysis.segments, "summary": analysis.summary, "key_topics": analysis.key_topics}

    def render(self, job_id, work_dir, params, cancelled=None):
        write_progress(work_dir, "render", 70, "Starting to render")
        try:
            with self._keepalive(cancelled):
                result = asyncio.run(self._engine(work_dir, params).render(self.request(work_dir, params), progress=self._progress(work_dir, "render"), should_cancel=self._cancel(cancelled)))
        finally:
            self._close_timings(work_dir)
        return result.clips
