"""Runs the clip engine for a clip job, between TubeForge's durable stages.

Cancellation surfaces as ``tubeforge.clips.cancellation.TaskCancelled``. The engine is asynchronous; the worker is not. Each stage opens its own event loop, so a worker
that dies mid-stage simply repeats that stage and the engine's file-backed checkpoint resumes it.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable, Protocol

from tubeforge.core.config import SourceClipConfig


class ClipRunner(Protocol):
    def analyze(self, job_id: str, work_dir: Path, params: dict[str, Any], cancelled: Callable[[], bool] | None) -> dict[str, Any]: ...

    def render(self, job_id: str, work_dir: Path, params: dict[str, Any], cancelled: Callable[[], bool] | None) -> list[dict[str, Any]]: ...


class EngineClipRunner:
    def __init__(self, config: SourceClipConfig, *, transport=None, whisper_model: str | None = None) -> None:
        self.config, self.transport, self.whisper_model = config, transport, whisper_model

    def _engine(self, work_dir: Path):
        # Imported here so a worker image without the clip dependencies still starts and runs Shorts.
        from tubeforge.clips.engine import ClipEngine, FileClipStore

        return ClipEngine(FileClipStore(work_dir / "state"), transport=self.transport, whisper_model=self.whisper_model)

    @staticmethod
    def request(work_dir: Path, params: dict[str, Any]):
        from tubeforge.clips.engine import ClipRequest

        return ClipRequest(
            url=params["source_url"], work_dir=work_dir, clip_count=int(params["clip_count"]),
            captions=bool(params["captions"]), engaging_only=bool(params.get("engaging_only", True)),
            max_clip_seconds=float(params["max_clip_seconds"]) if params.get("max_clip_seconds") else None,
            max_video_duration=int(params["max_source_seconds"]) if params.get("max_source_seconds") else None,
        )

    @staticmethod
    def _cancel(cancelled: Callable[[], bool] | None):
        async def should_cancel() -> bool:
            return bool(cancelled and cancelled())
        return should_cancel

    def analyze(self, job_id, work_dir, params, cancelled=None):
        analysis = asyncio.run(self._engine(work_dir).analyze(self.request(work_dir, params), should_cancel=self._cancel(cancelled)))
        return {"video_path": analysis.video_path, "segments": analysis.segments, "summary": analysis.summary, "key_topics": analysis.key_topics}

    def render(self, job_id, work_dir, params, cancelled=None):
        result = asyncio.run(self._engine(work_dir).render(self.request(work_dir, params), should_cancel=self._cancel(cancelled)))
        return result.clips
