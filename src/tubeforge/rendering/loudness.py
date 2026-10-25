"""Bounded FFmpeg loudness analysis of narration and encoded AAC output."""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

from tubeforge.core.errors import ProviderValidationError, RetryableProviderError

TARGET_I = -13.5
TARGET_TP = -2.5
TARGET_LRA = 11.0
LOUDNESS_VERSION = "loudnorm-narration-limiter-v4"
MUSIC_LOUDNESS_VERSION = "loudnorm-ducked-music-limiter-v3"


class LoudnessCancelled(Exception):
    pass


def _analysis(command: list[str], *, deadline: float, cancelled: Callable[[], bool] | None, poll_seconds: float) -> dict[str, float]:
    with tempfile.TemporaryFile() as diagnostics:
        try:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=diagnostics, shell=False)
        except OSError as error:
            raise ProviderValidationError("FFmpeg loudness analysis is unavailable") from error
        while process.poll() is None:
            if cancelled and cancelled():
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                raise LoudnessCancelled("loudness analysis cancelled")
            if time.monotonic() >= deadline:
                process.kill()
                process.wait()
                raise RetryableProviderError("loudness analysis timed out")
            time.sleep(poll_seconds)
        if process.returncode:
            raise RetryableProviderError("FFmpeg loudness analysis failed")
        diagnostics.seek(0)
        output = diagnostics.read().decode("utf-8", errors="replace")
    marker = output.rfind('"input_i"')
    beginning = output.rfind("{", 0, marker)
    ending = output.find("}", marker)
    if marker < 0 or beginning < 0 or ending < 0:
        raise ProviderValidationError("FFmpeg returned no complete loudness measurement")
    try:
        raw = json.loads(output[beginning:ending + 1])
        values = {key: float(raw[key]) for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}
    except (ValueError, TypeError, KeyError) as error:
        raise ProviderValidationError("FFmpeg returned invalid loudness measurements") from error
    if not all(math.isfinite(value) for value in values.values()):
        raise ProviderValidationError("FFmpeg returned non-finite loudness measurements")
    return values


def analyze(path: Path, *, ffmpeg: str, deadline: float, cancelled: Callable[[], bool] | None, poll_seconds: float,
            target_i: float = TARGET_I, target_tp: float = TARGET_TP, target_lra: float = TARGET_LRA) -> dict[str, float]:
    if not all(math.isfinite(v) for v in (target_i, target_tp, target_lra)):
        raise ValueError("loudness targets must be finite")
    return _analysis([ffmpeg, "-nostdin", "-hide_banner", "-i", str(path), "-vn", "-af", f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json", "-f", "null", "-"], deadline=deadline, cancelled=cancelled, poll_seconds=poll_seconds)


def analyze_mix(narration: Path, music: Path, *, duration: float, ffmpeg: str, deadline: float, cancelled: Callable[[], bool] | None, poll_seconds: float) -> dict[str, float]:
    graph = (
        "[0:a]asplit=2[narration_mix][speech_key];"
        "[1:a]volume=0.16[music_quiet];"
        "[music_quiet][speech_key]sidechaincompress=threshold=0.015:ratio=10:attack=20:release=350[ducked_music];"
        "[narration_mix][ducked_music]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95,"
        f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}:print_format=json[measured]"
    )
    return _analysis([ffmpeg, "-nostdin", "-hide_banner", "-i", str(narration), "-stream_loop", "-1", "-i", str(music), "-filter_complex", graph, "-map", "[measured]", "-t", f"{duration:.6f}", "-f", "null", "-"], deadline=deadline, cancelled=cancelled, poll_seconds=poll_seconds)


def second_pass_filter(measured: dict[str, float], *, ceiling: float = 0.77) -> str:
    return (f"loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}"
            f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
            f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
            f":offset={measured['target_offset']}:linear=true,alimiter=limit={ceiling}:level=false")


TIGHTER_CEILING = 0.60  # about 2.2 dB lower (0.66 still landed at -1.1 dBTP on the measured job): AAC encoding overshoots the limiter by up to ~1.4 dB on peaky voices


def validate_encoded(measured: dict[str, float]) -> None:
    # YouTube normalises to about -14 LUFS; peaky voices land a little under the -13.5 target after the limiter.
    if not -16.5 <= measured["input_i"] <= -12.5 or measured["input_tp"] > -1.0:
        raise ProviderValidationError(
            f"encoded audio is outside the Shorts loudness gate "
            f"(LUFS={measured['input_i']:.2f}, true_peak={measured['input_tp']:.2f} dBTP)"
        )
