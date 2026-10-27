"""Render every reference Shorts scene with HyperFrames and join a silent film."""
from __future__ import annotations

import os
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

from tubeforge.rendering.hyperframes_proto import cli, compose

from .encode import RenderCancelled, checked, swap_used_kib
from .timeline import Timeline

FPS = 30
SCENE_IN_SECONDS = .3  # motion.py: outgoing first, incoming second
BUILDERS = {
    "hook": compose.build_hook_project,
    "loop": compose.build_loop_project,
    "big_stat": compose.build_big_stat_project,
    "before_after": compose.build_before_after_project,
    "flow": compose.build_flow_project,
    "checklist": compose.build_checklist_project,
    "terminal": compose.build_terminal_project,
}


def scene_plan(timeline: Timeline) -> list[tuple[int, int, list[tuple[float, float]]]]:
    """Use global frame edges so rounding never adds or drops a scene."""
    result = []
    previous = 0
    for scene, timing in zip(timeline.topic.scenes, timeline.timings, strict=True):
        if scene.template not in BUILDERS:
            raise ValueError(f"HyperFrames has no builder for scene {scene.scene_id}: {scene.template}")
        end = round(timing.end * FPS)
        if end <= previous:
            raise ValueError(f"HyperFrames scene {scene.scene_id} has no video frames")
        words = [(word.start - timing.start, word.end - timing.start) for word in timing.words]
        result.append((previous, end, words))
        previous = end
    if previous != round(timeline.duration * FPS):
        raise ValueError("HyperFrames frame plan differs from the timeline")
    return result


def _filter(parts: list[tuple[int, int, list[tuple[float, float]]]], *, draft: bool) -> str:
    width, height = (720, 1280) if draft else (1080, 1920)
    chains = []
    for index, (start, end, _) in enumerate(parts):
        frames = end - start
        filters = [f"[{index}:v]fps={FPS}", "tpad=stop_mode=clone:stop_duration=0.1",
                   f"trim=end_frame={frames}", "setpts=PTS-STARTPTS",
                   f"scale={width}:{height}:flags=lanczos", "format=yuv420p"]
        # The PIL motion layer fades outgoing content for the first half of its 0.3s
        # boundary, then raises incoming content for the second half. A whole-frame
        # fade through the same navy ground preserves the cue with separate clips.
        if index:
            filters.append("fade=t=in:st=0:d=0.15:color=0x080f1f")
        if index < len(parts) - 1:
            filters.append(f"fade=t=out:st={(frames / FPS) - .15:.6f}:d=0.15:color=0x080f1f")
        chains.append(",".join(filters) + f"[v{index}]")
    chains.append("".join(f"[v{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[out]")
    return ";".join(chains)


def render_silent(timeline: Timeline, destination: Path, *, draft: bool,
                  cancelled: Callable[[], bool] = lambda: False, budget_rtf: float = 20,
                  ffmpeg: str = "ffmpeg", hyperframes_bin: str | None = None) -> dict:
    """Produce one silent MP4, or raise before promoting an incomplete film."""
    parts = scene_plan(timeline)
    binary = hyperframes_bin or os.environ.get("TUBEFORGE_HYPERFRAMES_BIN") or shutil.which("hyperframes")
    if not binary:
        raise ValueError("hyperframes binary is unavailable; set TUBEFORGE_HYPERFRAMES_BIN")
    initial_swap = swap_used_kib()

    def guarded_cancelled() -> bool:
        if swap_used_kib() - initial_swap > 524288:
            raise MemoryError("host swap grew more than 512 MiB during HyperFrames render")
        available = next((int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()
                          if line.startswith("MemAvailable:")), 0)
        if available < 524288:
            raise MemoryError("host has less than 512 MiB available during HyperFrames render")
        return cancelled()

    if guarded_cancelled():
        raise RenderCancelled("render cancelled or worker ownership lost")
    destination.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + max(60, timeline.duration * budget_rtf)
    with tempfile.TemporaryDirectory(prefix="hyperframes-render-", dir=destination.parent) as scratch:
        root = Path(scratch)
        env = {"TMPDIR": str(root), "HYPERFRAMES_EXTRACT_CACHE_DIR": str(root / "cache")}
        clips = []
        checks = []
        for index, (scene, timing, (_, end, words)) in enumerate(zip(
                timeline.topic.scenes, timeline.timings, parts, strict=True)):
            if guarded_cancelled():
                raise RenderCancelled("render cancelled or worker ownership lost")
            project = root / f"scene-{index:02d}"
            BUILDERS[scene.template](scene, words, timing.end - timing.start, project)
            checks.append(cli.check(project, hyperframes_bin=binary, timeout=max(1, deadline-time.monotonic()),
                                    extra_env=env, cancelled=guarded_cancelled))
            clip = root / f"scene-{index:02d}.mp4"
            cli.render(project, clip, quality="draft" if draft else "high", hyperframes_bin=binary,
                       timeout=max(1, deadline-time.monotonic()), workers=1, extra_env=env,
                       cancelled=guarded_cancelled)
            clips.append(clip)
        temporary = root / "joined.mp4"
        command = [ffmpeg, "-y", "-v", "error"]
        for clip in clips:
            command.extend(["-i", str(clip)])
        command.extend(["-filter_complex", _filter(parts, draft=draft), "-map", "[out]",
                        "-an", "-c:v", "libx264", "-threads", "2", "-preset", "veryfast",
                        "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS),
                        "-movflags", "+faststart", str(temporary)])
        checked(command, deadline=deadline, cancelled=guarded_cancelled)
        checked([ffmpeg, "-v", "error", "-xerror", "-i", str(temporary), "-f", "null", "-"],
                deadline=deadline, cancelled=guarded_cancelled)
        if guarded_cancelled():
            raise RenderCancelled("ownership lost before HyperFrames promotion")
        temporary.replace(destination)
    return {"scene_count": len(parts), "frames": round(timeline.duration * FPS),
            "duration": timeline.duration, "checks": checks,
            "render_seconds": time.monotonic() - started}
