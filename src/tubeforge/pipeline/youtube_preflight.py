"""Local, fail-closed checks for a YouTube Short before any network call."""
from __future__ import annotations

import json
import math
from pathlib import Path
import subprocess


class YouTubePreflightError(ValueError):
    """The local asset cannot safely be submitted as a Short."""


def check_youtube_short(path: Path, *, ffprobe: str = "ffprobe", max_bytes: int = 2_000_000_000) -> None:
    """Validate the canonical file itself, not metadata supplied by the browser."""
    if max_bytes <= 0:
        raise YouTubePreflightError("YouTube upload size limit is invalid")
    try:
        size = path.stat().st_size
        if not path.is_file() or size <= 0 or size > max_bytes:
            raise YouTubePreflightError(f"YouTube video must be nonempty and at most {max_bytes} bytes")
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height:stream_tags=rotate:stream_side_data=rotation", "-of", "json", str(path)],
            capture_output=True, text=True, check=True, timeout=20,
        )
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        streams = data["streams"]
        if not isinstance(streams, list):
            raise ValueError("invalid streams")
        video = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio = [stream for stream in streams if stream.get("codec_type") == "audio"]
        if not math.isfinite(duration) or duration <= 0 or duration > 180:
            raise YouTubePreflightError("YouTube Short duration must be greater than zero and at most 180 seconds")
        if len(video) != 1 or video[0].get("codec_name") != "h264":
            raise YouTubePreflightError("YouTube Short must contain exactly one H.264 video stream")
        if len(audio) != 1 or audio[0].get("codec_name") != "aac":
            raise YouTubePreflightError("YouTube Short must contain exactly one AAC audio stream")
        width, height = int(video[0]["width"]), int(video[0]["height"])
        rotations = [((video[0].get("tags") or {}).get("rotate", 0))]
        rotations.extend(side.get("rotation", 0) for side in video[0].get("side_data_list", []))
        if any(float(rotation) % 360 for rotation in rotations) or width <= 0 or height <= 0 or width * 16 != height * 9:
            raise YouTubePreflightError("YouTube Short must be an unrotated 9:16 video")
    except YouTubePreflightError:
        raise
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, AttributeError, json.JSONDecodeError) as error:
        raise YouTubePreflightError("YouTube Short media could not be validated") from error
