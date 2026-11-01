"""Audio warnings locate defects; they never substitute for listening."""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

from tubeforge.rendering.shorts.audio_health import music_under_speech, scan_samples, scan_wav


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


def test_music_under_speech_flags_a_loud_bed_during_active_voice():
    rate = 1000
    t = np.arange(rate) / rate
    voice = (np.sin(2 * np.pi * 17 * t) * .3).astype(np.float32)        # loud, clearly active speech
    quiet_bed = (np.sin(2 * np.pi * 220 * t) * .005).astype(np.float32)  # well under the margin
    loud_bed = (np.sin(2 * np.pi * 220 * t) * .25).astype(np.float32)    # close to the voice level

    quiet_report = music_under_speech(voice, quiet_bed, rate)
    assert quiet_report["windows_masked"] == 0

    loud_report = music_under_speech(voice, loud_bed, rate)
    assert loud_report["windows_masked"] > 0
    assert loud_report["warnings"][0]["start"] == 0.0


def test_music_under_speech_ignores_a_loud_bed_during_silence():
    rate = 1000
    t = np.arange(rate) / rate
    silent_voice = np.zeros(rate, np.float32)
    loud_bed = (np.sin(2 * np.pi * 220 * t) * .25).astype(np.float32)
    report = music_under_speech(silent_voice, loud_bed, rate)
    assert report["windows_masked"] == 0   # loud bed under silence is not "music over speech"


def test_music_under_speech_rejects_mismatched_or_multichannel_input():
    with pytest.raises(ValueError):
        music_under_speech(np.zeros(10, np.float32), np.zeros(20, np.float32), 1000)
    with pytest.raises(ValueError):
        music_under_speech(np.zeros((10, 2), np.float32), np.zeros((10, 2), np.float32), 1000)


def test_invalid_samples_are_reported_and_warning_count_is_bounded():
    audio = np.full(120 * 1000, .1, np.float32)
    audio[100:200] = np.nan
    for second in range(1, 119, 2):
        audio[second * 1000:(second + 1) * 1000] = 1.0
    report = scan_samples(audio, 1000)
    assert report["warnings"][0]["kind"] == "invalid"
    assert len(report["warnings"]) <= 100
    assert report["scope"] == "advisory_signal_only"
