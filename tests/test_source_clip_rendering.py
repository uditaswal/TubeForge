from __future__ import annotations

import subprocess
from pathlib import Path

from tubeforge.clipping.render import probe, render_vertical


def test_vertical_source_clip_is_h264_aac_and_9_by_16(tmp_path: Path) -> None:
    source, output = tmp_path / "source.mp4", tmp_path / "clip.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
    ], check=True, capture_output=True, text=True)
    result = render_vertical("ffmpeg", "ffprobe", source, output, 0, 2)
    assert output.is_file() and output.stat().st_size > 0
    assert result["width"] == 1080 and result["height"] == 1920 and result["has_audio"]
    assert probe("ffprobe", output)["duration_seconds"] > 1.5
