"""Audio warnings locate defects; they never substitute for listening."""
from __future__ import annotations

import numpy as np
import soundfile as sf

from tubeforge.rendering.shorts.audio_health import scan_samples, scan_wav


def test_locates_clipping_silence_and_relative_level_changes(tmp_path):
    rate = 1000
    t = np.arange(rate) / rate
    normal = (np.sin(2 * np.pi * 17 * t) * .1).astype(np.float32)
    audio = np.concatenate((normal, np.zeros(rate * 2, np.float32), normal * .05,
                            np.full(rate, 1.0, np.float32), normal))
    report = scan_samples(audio, rate, scene_starts=(0.0, 2.0, 4.0))
    by_kind = {item["kind"]: item for item in report["warnings"]}
    assert by_kind["silence"]["start"] == 1.0 and by_kind["silence"]["end"] == 3.0
    assert by_kind["clipping"]["start"] == 4.0 and by_kind["clipping"]["scene_index"] == 2
    assert by_kind["quiet"]["start"] == 3.0
    assert by_kind["loud"]["start"] == 4.0
    path = tmp_path / "voice.wav"
    sf.write(path, audio, rate, subtype="FLOAT")
    saved = scan_wav(path, scene_starts=(0.0, 2.0, 4.0))
    assert len(saved["artifact_sha256"]) == 64
    assert saved["warnings"] == report["warnings"]


def test_invalid_samples_are_reported_and_warning_count_is_bounded():
    audio = np.full(120 * 1000, .1, np.float32)
    audio[100:200] = np.nan
    for second in range(1, 119, 2):
        audio[second * 1000:(second + 1) * 1000] = 1.0
    report = scan_samples(audio, 1000)
    assert report["warnings"][0]["kind"] == "invalid"
    assert len(report["warnings"]) <= 100
    assert report["scope"] == "advisory_signal_only"
