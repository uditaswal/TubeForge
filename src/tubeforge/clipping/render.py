"""Validated vertical H.264/AAC source clip renderer."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tubeforge.core.errors import ProviderValidationError, RetryableProviderError


def extract_audio(ffmpeg: str, source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    _run([ffmpeg, "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", str(output)])


def render_vertical(ffmpeg: str, ffprobe: str, source: Path, output: Path, start: float, end: float, captions: Path | None = None) -> dict[str, object]:
    output.parent.mkdir(parents=True, exist_ok=True)
    # Keep the media suffix at the end so FFmpeg can infer the container.
    temporary = output.with_name(output.stem + ".part" + output.suffix)
    duration = end - start
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1,fps=30"
    if captions is not None:
        # The path is internal, generated under the job root.  Escape only the
        # filter syntax delimiter rather than accepting any user-supplied text.
        vf += ",subtitles='" + str(captions).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'") + "'"
    try:
        _run([ffmpeg, "-y", "-ss", f"{start:.3f}", "-i", str(source), "-t", f"{duration:.3f}", "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(temporary)])
        metadata = probe(ffprobe, temporary)
        if metadata["width"] != 1080 or metadata["height"] != 1920 or not metadata["has_audio"]:
            raise ProviderValidationError("rendered clip is not a 1080x1920 video with audio")
        temporary.replace(output)
        return metadata
    finally:
        temporary.unlink(missing_ok=True)


def probe(ffprobe: str, path: Path) -> dict[str, object]:
    completed = subprocess.run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)], text=True, capture_output=True, check=False)
    if completed.returncode: raise ProviderValidationError("ffprobe could not inspect source clip")
    raw = json.loads(completed.stdout); streams = raw.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video: raise ProviderValidationError("rendered clip has no video stream")
    return {"width": int(video["width"]), "height": int(video["height"]), "has_audio": audio is not None, "duration_seconds": float(raw.get("format", {}).get("duration") or 0)}


def _run(command: list[str]) -> None:
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=1800, check=False)
    except subprocess.TimeoutExpired as error: raise RetryableProviderError("ffmpeg source-clip operation timed out") from error
    if completed.returncode: raise ProviderValidationError((completed.stderr.strip().splitlines() or ["ffmpeg source-clip operation failed"])[-1][:1000])
