"""Known black and frozen encoded intervals must be located in real media."""
import subprocess
import time

import numpy as np

from tubeforge.rendering.shorts.temporal_qa import inspect_encoded_video


def test_encoded_black_and_freeze_intervals(tmp_path):
    frame = 160 * 284
    samples = np.concatenate([np.full(frame * 4, 255, np.uint8),
                              np.zeros(frame * 4, np.uint8),
                              np.full(frame * 8, 255, np.uint8)])
    path = tmp_path / "known-defects.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray",
                    "-s", "160x284", "-r", "4", "-i", "pipe:0", "-c:v", "libx264", str(path)],
                   input=samples.tobytes(), check=True, capture_output=True)
    report = inspect_encoded_video(path, duration=4, scene_starts=(0, 1, 2, 3),
                                   ffmpeg="ffmpeg", deadline=time.monotonic() + 20,
                                   cancelled=lambda: False)
    assert report["sample_count"] == 16
    assert any(row["start"] <= 1 and row["end"] >= 2 for row in report["black_intervals"])
    assert any(row["end"] - row["start"] >= 1 for row in report["freeze_intervals"])
