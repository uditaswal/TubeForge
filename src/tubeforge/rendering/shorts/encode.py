"""Bounded raw-RGB encoder and post-encode gates for the shared scene library."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import subprocess
import tempfile
import time
from collections.abc import Callable

import numpy as np
from PIL import Image

from tubeforge.rendering.loudness import analyze
from .audio_health import scan_samples
from .timeline import Timeline


class RenderCancelled(RuntimeError):
    pass


def swap_used_kib():
    fields = dict((parts[0].rstrip(":"), int(parts[1])) for line in Path("/proc/meminfo").read_text().splitlines()
                  if (parts := line.split())[0] in {"SwapTotal:", "SwapFree:"})
    return fields["SwapTotal"] - fields["SwapFree"]


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked(command, *, deadline, cancelled):
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        try:
            while process.poll() is None:
                if cancelled():
                    raise RenderCancelled("local render cancelled")
                if time.monotonic() > deadline:
                    raise TimeoutError("local renderer subprocess timed out")
                time.sleep(.1)
            if process.returncode:
                stderr.seek(0)
                raise ValueError(stderr.read(8000).decode(errors="replace"))
            stdout.seek(0)
            return stdout.read()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()


def encode(timeline: Timeline, audio: Path, destination: Path, *, draft=False,
           cancelled: Callable[[], bool] = lambda: False, budget_rtf=10.0, max_swap_growth_kib=524288, motion=True,
           ffmpeg="ffmpeg", ffprobe="ffprobe", plates=None, narration_health=None):
    """Promote only a fully decoded, measured video. Caller owns job fencing.

    The cancelled callback must also return True on ownership loss. Destination
    should be the worker's lease-local staging path; the repository promotes
    that staged artifact under its usual ownership fence.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    width, height = (720, 1280) if draft else (1080, 1920)
    started = time.monotonic()
    deadline = started + max(60, timeline.duration * budget_rtf)
    initial_swap = swap_used_kib()
    animator = None
    if motion:
        from .motion import Animator
        animator = Animator(timeline.renderer, plates=plates)
    report = {"schema_version": "reference-video-qa-v1", "passed": False,
              "topic_sha256": hashlib.sha256(timeline.topic.model_dump_json().encode()).hexdigest(),
              "audio_sha256": file_hash(audio), "layout": timeline.renderer.validate(),
              "alignment": [s.alignment for s in timeline.timings], "draft": draft,
              "narration_health": narration_health,
              "budget_realtime_factor": budget_rtf, "motion": motion,
              "plates": {str(i): (plates.entry(i).get("kind"), (plates.entry(i).get("evidence") or {}).get("asset_id"))
                         for i in range(len(timeline.topic.scenes)) if plates is not None and plates.entry(i)}}
    qa_path = destination.with_suffix(".qa.json")
    try:
        with tempfile.TemporaryDirectory(prefix="reference-render-", dir=destination.parent) as directory:
            temporary = Path(directory) / "encoded.mp4"
            command = [ffmpeg, "-y", "-v", "error", "-filter_threads", "1", "-f", "rawvideo", "-pix_fmt", "rgb24",
                       "-s", f"{width}x{height}", "-r", "30", "-i", "pipe:0", "-i", str(audio),
                       "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-threads", "2", "-preset",
                       "veryfast" if draft else "fast", "-tune", "zerolatency", "-crf", "20", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t",
                       f"{timeline.duration:.6f}", "-movflags", "+faststart", str(temporary)]
            with tempfile.TemporaryFile() as diagnostics:
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                           stderr=diagnostics, bufsize=0)
                selector = selectors.DefaultSelector()
                try:
                    os.set_blocking(process.stdin.fileno(), False)
                    selector.register(process.stdin, selectors.EVENT_WRITE)
                    previous_event, raw, events = None, None, 0
                    peak_rss = 0
                    for frame_index in range(round(timeline.duration * 30)):
                        if cancelled():
                            raise RenderCancelled("render cancelled or worker ownership lost")
                        if time.monotonic() > deadline:
                            raise TimeoutError("render exceeded its local realtime budget")
                        current_swap = swap_used_kib()
                        if current_swap - initial_swap > max_swap_growth_kib:
                            report.update(swap_growth_kib=current_swap - initial_swap,
                                          peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                          stopped_at_frame=frame_index)
                            raise MemoryError("host swap grew during render")
                        peak_rss = max(peak_rss, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
                        event = (timeline.state(frame_index / 30), frame_index / 30) if animator else timeline.event(frame_index / 30)
                        if animator is not None or event != previous_event:
                            frame = animator.frame(*event) if animator else timeline.renderer.frame(*event)
                            if draft:
                                frame = frame.resize((width, height), Image.Resampling.LANCZOS)
                            raw = frame.tobytes()
                            previous_event, events = event, events + 1
                        view = memoryview(raw)
                        while view:
                            if cancelled():
                                raise RenderCancelled("render cancelled or worker ownership lost")
                            if time.monotonic() > deadline:
                                raise TimeoutError("encoder pipe stalled beyond render budget")
                            if process.poll() is not None:
                                diagnostics.seek(0)
                                raise ValueError("FFmpeg stopped: " + diagnostics.read(8000).decode(errors="replace"))
                            if selector.select(timeout=.1):
                                try:
                                    view = view[os.write(process.stdin.fileno(), view):]
                                except BlockingIOError:
                                    continue
                    selector.unregister(process.stdin)
                    process.stdin.close()
                    while process.poll() is None:
                        if cancelled():
                            raise RenderCancelled("render cancelled or worker ownership lost")
                        if time.monotonic() > deadline:
                            raise TimeoutError("encoder finalization timed out")
                        time.sleep(.1)
                    if process.returncode:
                        diagnostics.seek(0)
                        raise ValueError(diagnostics.read(8000).decode(errors="replace"))
                finally:
                    selector.close()
                    if process.poll() is None:
                        process.kill()
                        process.wait()
                    if not process.stdin.closed:
                        process.stdin.close()
            render_seconds = time.monotonic() - started
            qa_deadline = time.monotonic() + 120
            probe = json.loads(checked([ffprobe, "-v", "error", "-show_streams", "-show_format",
                                       "-of", "json", str(temporary)], deadline=qa_deadline, cancelled=cancelled))
            video = next(s for s in probe["streams"] if s["codec_type"] == "video")
            sound = next(s for s in probe["streams"] if s["codec_type"] == "audio")
            if (video["width"], video["height"], video["avg_frame_rate"], video["codec_name"]) != (width, height, "30/1", "h264"):
                raise ValueError("encoded video specs differ from reference target")
            if sound["codec_name"] != "aac" or int(sound["sample_rate"]) != 48000:
                raise ValueError("encoded audio must be AAC at 48 kHz")
            duration = float(probe["format"]["duration"])
            if not 25 <= duration <= 45 or abs(duration - timeline.duration) > .1:
                raise ValueError("encoded duration differs from accepted timeline")
            checked([ffmpeg, "-v", "error", "-xerror", "-i", str(temporary), "-f", "null", "-"],
                    deadline=qa_deadline, cancelled=cancelled)
            loudness = analyze(temporary, ffmpeg=ffmpeg, deadline=qa_deadline, cancelled=cancelled, poll_seconds=.1)
            decoded_audio = checked([ffmpeg, "-v", "error", "-i", str(temporary), "-vn", "-ac", "1",
                                     "-ar", "48000", "-f", "f32le", "pipe:1"],
                                    deadline=qa_deadline, cancelled=cancelled)
            if len(decoded_audio) % 4:
                raise ValueError("encoded audio diagnostic returned incomplete float samples")
            audio_health = scan_samples(np.frombuffer(decoded_audio, dtype="<f4"), 48000,
                                        scene_starts=tuple(t.start for t in timeline.timings))
            audio_health["artifact_sha256"] = file_hash(temporary)
            report.update(probe=probe, loudness=loudness, full_decode=True,
                          audio_health=audio_health,
                          render_seconds=render_seconds, realtime_factor=render_seconds / duration,
                          distinct_frame_events=events, frames=round(timeline.duration * 30),
                          peak_process_rss_kib=peak_rss, peak_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                          swap_growth_kib=swap_used_kib() - initial_swap)
            if not -15 <= loudness["input_i"] <= -13 or loudness["input_tp"] > -1.5:
                raise ValueError(f"encoded audio fails reference gate: {loudness}")
            if report["swap_growth_kib"] > max_swap_growth_kib:
                raise MemoryError("host swap grew during render")
            if cancelled():
                raise RenderCancelled("ownership lost before local promotion")
            report.update(passed=True, video_sha256=file_hash(temporary))
            temporary.replace(destination)
    except Exception as error:
        report["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        if plates is not None:
            plates.release()
        qa_path.write_text(json.dumps(report, indent=2) + "\n")
    return report
