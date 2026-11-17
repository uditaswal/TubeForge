"""The clip engine's single entry point.

``ClipEngine.run`` turns one source video into rendered vertical clips: download,
transcribe the engaging parts, let the AI pick the best standalone moments, then
render each one. Everything it needs from the host (where to keep state, how to
report progress, how to ask for cancellation, how to reach the AI) is passed in,
so this package imports nothing from the rest of TubeForge.

State lives in a ``ClipStore``: a resumed run reads the checkpoint and cached
analysis and renders only the clips that are still missing. Each clip is rendered
into a scratch folder and moved into place only when it is complete, so a
cancelled or crashed run never leaves a half-written clip behind.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol

from .cancellation import TaskCancelled
from .config import Config, get_config, set_config_override
from .runner_model import Transport, set_transport
from .services.video_service import VideoService
from .utils.async_helpers import run_in_thread
from .youtube_source import load_time_map, localize_segment, restore_clip_timeline

logger = logging.getLogger(__name__)

ENGINE_VERSION = "clips-v1"
MAX_CLIPS = 12

ProgressCallback = Callable[[int, str], Awaitable[None]]
CancelCallback = Callable[[], Awaitable[bool]]
ClipCallback = Callable[[int, int, Dict[str, Any]], Awaitable[None]]


class ClipStore(Protocol):
    """What the engine needs to remember between attempts."""

    def load_checkpoint(self, key: str) -> Dict[str, Any]: ...

    def save_checkpoint(self, key: str, patch: Dict[str, Any]) -> None: ...

    def get_cache(self, key: str) -> Optional[Dict[str, Any]]: ...

    def put_cache(self, key: str, value: Dict[str, Any]) -> None: ...


class FileClipStore:
    """A ``ClipStore`` kept as small JSON files, written atomically."""

    def __init__(self, folder: Path) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def _path(self, kind: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode()).hexdigest()[:40]
        return self.folder / f"{kind}-{digest}.json"

    @staticmethod
    def _read(path: Path) -> Optional[Dict[str, Any]]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _write(path: Path, value: Dict[str, Any]) -> None:
        handle, temporary = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(value, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def load_checkpoint(self, key: str) -> Dict[str, Any]:
        return self._read(self._path("checkpoint", key)) or {}

    def save_checkpoint(self, key: str, patch: Dict[str, Any]) -> None:
        current = self.load_checkpoint(key)
        current.update(patch)
        self._write(self._path("checkpoint", key), current)

    def get_cache(self, key: str) -> Optional[Dict[str, Any]]:
        return self._read(self._path("cache", key))

    def put_cache(self, key: str, value: Dict[str, Any]) -> None:
        self._write(self._path("cache", key), value)


@dataclass(frozen=True)
class ClipRequest:
    """What to make. ``work_dir`` holds the download, scratch files and finished clips."""

    url: str
    work_dir: Path
    source_type: str = "youtube"
    clip_count: int = 5
    clip_length: str = "auto"
    captions: bool = True
    engaging_only: bool = True
    caption_template: str = "default"
    max_video_duration: Optional[int] = None
    max_clip_seconds: Optional[float] = None
    max_download_bytes: Optional[int] = None

    def __post_init__(self) -> None:
        if not 1 <= self.clip_count <= MAX_CLIPS:
            raise ValueError(f"clip_count must be between 1 and {MAX_CLIPS}")
        if self.source_type not in {"youtube", "upload"}:
            raise ValueError("source_type must be youtube or upload")


@dataclass
class ClipRunResult:
    clips: List[Dict[str, Any]] = field(default_factory=list)
    summary: Optional[str] = None
    key_topics: Optional[List[str]] = None
    stage_seconds: Dict[str, float] = field(default_factory=dict)
    resumed_clips: int = 0


def clip_cache_key(request: ClipRequest) -> str:
    material = json.dumps(
        [ENGINE_VERSION, request.url, request.source_type, request.clip_length, request.engaging_only],
        sort_keys=True,
    )
    return hashlib.sha256(material.encode()).hexdigest()


def build_engine_config(request: ClipRequest, *, whisper_model: Optional[str] = None) -> Config:
    """The engine's settings for one run, taken from the request and the host."""
    config = Config()
    config.temp_dir = str(Path(request.work_dir) / "temp")
    config.max_clips = request.clip_count
    config.analysis_strategy = "signals" if request.engaging_only else "full"
    config.transcription_provider = "whisper"
    config.llm = "runner"
    config.llm_fallbacks = []
    if whisper_model:
        config.whisper_model = whisper_model
    if request.max_video_duration:
        config.max_video_duration = request.max_video_duration
    if request.max_download_bytes:
        config.youtube_download_max_bytes = request.max_download_bytes
    return config


@dataclass
class ClipAnalysis:
    """What the AI chose: the source file on disk and the moments to render."""

    video_path: str
    segments: List[Dict[str, Any]]
    summary: Optional[str] = None
    key_topics: Optional[List[str]] = None


class ClipEngine:
    def __init__(
        self,
        store: ClipStore,
        *,
        transport: Optional[Transport] = None,
        whisper_model: Optional[str] = None,
    ) -> None:
        self.store = store
        self.transport = transport
        self.whisper_model = whisper_model

    @contextlib.contextmanager
    def _session(self, request: ClipRequest):
        """The engine's settings and AI transport, for the length of one stage."""
        if self.transport is not None:
            set_transport(self.transport)
        set_config_override(build_engine_config(request, whisper_model=self.whisper_model))
        try:
            yield
        finally:
            set_config_override(None)
            if self.transport is not None:
                set_transport(None)

    @staticmethod
    def _keys(request: ClipRequest) -> tuple[str, str]:
        cache_key = clip_cache_key(request)
        return cache_key, f"{cache_key}:{request.clip_count}"

    async def run(
        self,
        request: ClipRequest,
        *,
        progress: Optional[ProgressCallback] = None,
        should_cancel: Optional[CancelCallback] = None,
        on_clip: Optional[ClipCallback] = None,
    ) -> ClipRunResult:
        analysis = await self.analyze(request, progress=progress, should_cancel=should_cancel)
        return await self.render(request, analysis, progress=progress, should_cancel=should_cancel, on_clip=on_clip)

    async def analyze(
        self,
        request: ClipRequest,
        *,
        progress: Optional[ProgressCallback] = None,
        should_cancel: Optional[CancelCallback] = None,
    ) -> ClipAnalysis:
        """Download, transcribe the engaging parts and let the AI pick the moments. Resumable."""
        work_dir = Path(request.work_dir)
        (work_dir / "temp").mkdir(parents=True, exist_ok=True)
        cache_key, input_key = self._keys(request)
        saved = self.store.load_checkpoint(input_key).get("analysis")
        if saved and Path(saved["video_path"]).is_file():
            return ClipAnalysis(**saved)

        async def check_cancelled() -> None:
            if should_cancel and await should_cancel():
                raise TaskCancelled()

        async def report(percent: int, message: str, status: str = "processing") -> None:
            await check_cancelled()
            if progress:
                await progress(percent, message)

        with self._session(request):
            await check_cancelled()
            cache = self.store.get_cache(cache_key) or {}
            checkpoint = dict(self.store.load_checkpoint(input_key))

            async def save_checkpoint(patch: Dict[str, Any]) -> None:
                self.store.save_checkpoint(input_key, patch)
                checkpoint.update(patch)

            pipeline = await VideoService.process_video_complete(
                url=request.url,
                source_type=request.source_type,
                task_id=hashlib.sha256(input_key.encode()).hexdigest()[:16],
                caption_template=request.caption_template,
                add_subtitles=request.captions,
                max_video_duration=request.max_video_duration,
                cached_transcript=cache.get("transcript_text"),
                cached_analysis_json=cache.get("analysis_json"),
                progress_callback=report,
                should_cancel=should_cancel,
                clip_length=request.clip_length,
                checkpoint=checkpoint,
                checkpoint_callback=save_checkpoint,
            )
        segments = list(pipeline.get("segments_to_render") or [])[: request.clip_count]
        if not segments:
            raise ValueError("No usable clip segments were selected for this video.")
        self.store.put_cache(
            cache_key,
            {"transcript_text": pipeline.get("transcript"), "analysis_json": pipeline.get("analysis_json")},
        )
        analysis = ClipAnalysis(
            video_path=str(pipeline["video_path"]),
            segments=segments,
            summary=pipeline.get("summary"),
            key_topics=pipeline.get("key_topics"),
        )
        self.store.save_checkpoint(input_key, {"analysis": analysis.__dict__})
        return analysis

    async def render(
        self,
        request: ClipRequest,
        analysis: Optional[ClipAnalysis] = None,
        *,
        progress: Optional[ProgressCallback] = None,
        should_cancel: Optional[CancelCallback] = None,
        on_clip: Optional[ClipCallback] = None,
    ) -> ClipRunResult:
        """Render the chosen moments, one clip at a time. Finished clips are never redone."""
        work_dir = Path(request.work_dir)
        clips_dir = work_dir / "clips"
        scratch_dir = work_dir / "scratch"
        clips_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(scratch_dir, ignore_errors=True)  # a crashed attempt's half-written files
        scratch_dir.mkdir(parents=True, exist_ok=True)
        _, input_key = self._keys(request)
        if analysis is None:
            saved = self.store.load_checkpoint(input_key).get("analysis")
            if not saved:
                raise ValueError("The clip analysis is missing; analyze the source first.")
            analysis = ClipAnalysis(**saved)
        video_path = Path(analysis.video_path)
        result = ClipRunResult(summary=analysis.summary, key_topics=analysis.key_topics)

        async def check_cancelled() -> None:
            if should_cancel and await should_cancel():
                raise TaskCancelled()

        async def report(percent: int, message: str) -> None:
            await check_cancelled()
            if progress:
                await progress(percent, message)

        try:
            with self._session(request):
                time_map = await run_in_thread(load_time_map, video_path)
                finished: Dict[str, Dict[str, Any]] = dict(self.store.load_checkpoint(input_key).get("clips") or {})
                segments = analysis.segments
                total = len(segments)
                render_started = perf_counter()
                for index, segment in enumerate(segments):
                    await check_cancelled()
                    position = str(index + 1)
                    existing = finished.get(position)
                    if existing and Path(existing["path"]).is_file():
                        result.resumed_clips += 1
                        continue
                    await report(70 + int(((index + 1) / total) * 25), f"Creating clip {index + 1}/{total}...")
                    render_segment = localize_segment(segment, time_map) if time_map else segment
                    max_seconds = request.max_clip_seconds or (
                        float(segment["max_seconds"]) if segment.get("max_seconds") else 60.0
                    )
                    info = await VideoService.create_single_clip(
                        video_path,
                        render_segment,
                        index,
                        scratch_dir,
                        caption_template=request.caption_template,
                        add_subtitles=request.captions,
                        max_clip_seconds=max_seconds,
                    )
                    await check_cancelled()
                    if info is None:
                        raise ValueError(f"Could not render clip {index + 1}. Retry to create the missing clips.")
                    if time_map:
                        info = await run_in_thread(restore_clip_timeline, info, time_map, segment)
                    info = self._promote(info, clips_dir, position)
                    finished[position] = info
                    self.store.save_checkpoint(input_key, {"clips": finished})
                    if on_clip:
                        await on_clip(index, total, info)
                result.stage_seconds["render_seconds"] = round(perf_counter() - render_started, 3)
                result.clips = [finished[key] for key in sorted(finished, key=int) if int(key) <= total]
                if not result.clips:
                    raise ValueError("No clips could be rendered. Please try again.")
                await report(100, "Complete!")
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)
        if len(result.clips) == len(analysis.segments):
            await run_in_thread(self._cleanup_source, video_path, request)
        return result

    @staticmethod
    def _promote(info: Dict[str, Any], clips_dir: Path, position: str) -> Dict[str, Any]:
        """Move a finished clip and its source map from scratch into the clips folder."""
        source = Path(info["path"])
        target = clips_dir / f"clip-{int(position):02d}{source.suffix}"
        os.replace(source, target)
        sidecar = source.with_suffix(".source_map.json")
        if sidecar.is_file():
            os.replace(sidecar, target.with_suffix(".source_map.json"))
        promoted = dict(info)
        promoted["path"] = str(target)
        promoted["filename"] = target.name
        return promoted

    @staticmethod
    def _cleanup_source(video_path: Path, request: ClipRequest) -> None:
        """Drop the multi-gigabyte download once the clips exist; keep word timings."""
        try:
            if request.source_type == "youtube":
                from .youtube_utils import cleanup_downloaded_files, extract_video_id

                video_id = extract_video_id(request.url)
                if video_id:
                    cleanup_downloaded_files(video_id, source_path=video_path)
                    return
            sidecar = video_path.with_name(f"{video_path.stem}.transcription.mp3")
            sidecar.unlink(missing_ok=True)
        except Exception:
            logger.warning("Could not clean up the downloaded source", exc_info=True)
