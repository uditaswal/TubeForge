"""Mux a HyperFrames film with the existing mastered mix and apply reference QA."""
from __future__ import annotations

import hashlib
import json
import resource
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

import numpy as np

from tubeforge.rendering.loudness import analyze

from .audio_health import scan_samples
from .encode import RenderCancelled, checked, file_hash, swap_used_kib
from .schema import REFERENCE_SHORT_MAX_SECONDS, REFERENCE_SHORT_MIN_SECONDS
from .temporal_qa import inspect_encoded_video
from .timeline import Timeline


def encode(timeline: Timeline, silent: Path, audio: Path, destination: Path, *, draft: bool,
           cancelled: Callable[[], bool] = lambda: False, budget_rtf: float = 20,
           render_started: float | None = None, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe",
           narration_health: dict | None = None, scene_report: dict | None = None) -> dict:
    """Promote only a fully decoded and measured MP4; preserve PIL's QA schema."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    started = render_started if render_started is not None else time.monotonic()
    deadline = started + max(60, timeline.duration * budget_rtf)
    initial_swap = swap_used_kib()
    width, height = (720, 1280) if draft else (1080, 1920)
    report = {"schema_version": "reference-video-qa-v1", "passed": False,
              "topic_sha256": hashlib.sha256(timeline.topic.model_dump_json().encode()).hexdigest(),
              "audio_sha256": file_hash(audio), "layout": timeline.renderer.validate(),
              "alignment": [s.alignment for s in timeline.timings], "draft": draft,
              "narration_health": narration_health, "budget_realtime_factor": budget_rtf,
              "motion": True, "plates": {}, "renderer": "hyperframes",
              "scene_count": len(timeline.topic.scenes),
              "scene_checks": [{"ok": row.get("ok", False), "errors": sum((row.get(group) or {}).get("errorCount", 0)
                               for group in ("lint", "runtime", "layout", "craft"))}
                               for row in (scene_report or {}).get("checks", [])]}
    qa_path = destination.with_suffix(".qa.json")
    try:
        with tempfile.TemporaryDirectory(prefix="hyperframes-mux-", dir=destination.parent) as scratch:
            temporary = Path(scratch) / "encoded.mp4"
            checked([ffmpeg, "-y", "-v", "error", "-i", str(silent), "-i", str(audio),
                     "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac",
                     "-b:a", "192k", "-ar", "48000", "-t", f"{timeline.duration:.6f}",
                     "-movflags", "+faststart", str(temporary)], deadline=deadline, cancelled=cancelled)
            qa_deadline = min(deadline, time.monotonic() + 120)
            probe = json.loads(checked([ffprobe, "-v", "error", "-show_streams", "-show_format",
                                        "-of", "json", str(temporary)], deadline=qa_deadline,
                                       cancelled=cancelled))
            video = next(s for s in probe["streams"] if s["codec_type"] == "video")
            sound = next(s for s in probe["streams"] if s["codec_type"] == "audio")
            if (video["width"], video["height"], video["avg_frame_rate"], video["codec_name"]) != (width, height, "30/1", "h264"):
                raise ValueError("encoded video specs differ from reference target")
            if sound["codec_name"] != "aac" or int(sound["sample_rate"]) != 48000:
                raise ValueError("encoded audio must be AAC at 48 kHz")
            duration = float(probe["format"]["duration"])
            if not REFERENCE_SHORT_MIN_SECONDS <= duration <= REFERENCE_SHORT_MAX_SECONDS or abs(duration - timeline.duration) > .1:
                raise ValueError("encoded duration differs from accepted timeline")
            checked([ffmpeg, "-v", "error", "-xerror", "-i", str(temporary), "-f", "null", "-"],
                    deadline=qa_deadline, cancelled=cancelled)
            loudness = analyze(temporary, ffmpeg=ffmpeg, deadline=qa_deadline,
                               cancelled=cancelled, poll_seconds=.1)
            decoded_audio = checked([ffmpeg, "-v", "error", "-i", str(temporary), "-vn", "-ac", "1",
                                     "-ar", "48000", "-f", "f32le", "pipe:1"],
                                    deadline=qa_deadline, cancelled=cancelled)
            if len(decoded_audio) % 4:
                raise ValueError("encoded audio diagnostic returned incomplete float samples")
            audio_health = scan_samples(np.frombuffer(decoded_audio, dtype="<f4"), 48000,
                                        scene_starts=tuple(t.start for t in timeline.timings))
            audio_health["artifact_sha256"] = file_hash(temporary)
            temporal_qa = inspect_encoded_video(temporary, duration=duration,
                scene_starts=tuple(t.start for t in timeline.timings), ffmpeg=ffmpeg,
                deadline=qa_deadline, cancelled=cancelled)
            render_seconds = time.monotonic() - started
            report.update(probe=probe, loudness=loudness, full_decode=True,
                          audio_health=audio_health, temporal_qa=temporal_qa,
                          render_seconds=render_seconds, realtime_factor=render_seconds / duration,
                          distinct_frame_events=None,
                          frames=round(timeline.duration * 30),
                          peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                          peak_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                          swap_growth_kib=swap_used_kib() - initial_swap)
            if not -15 <= loudness["input_i"] <= -13 or loudness["input_tp"] > -1.5:
                raise ValueError(f"encoded audio fails reference gate: {loudness}")
            if temporal_qa["black_intervals"]:
                report.setdefault("warnings", []).append(
                    {"code": "temporal_black_interval", "intervals": temporal_qa["black_intervals"]})
            if report["swap_growth_kib"] > 524288:
                raise MemoryError("host swap grew during render")
            if cancelled():
                raise RenderCancelled("ownership lost before local promotion")
            report.update(passed=True, video_sha256=file_hash(temporary))
            temporary.replace(destination)
    except Exception as error:
        report["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        qa_path.write_text(json.dumps(report, indent=2) + "\n")
    return report
