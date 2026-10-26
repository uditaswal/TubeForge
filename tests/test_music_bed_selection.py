"""Resolving a job's `music_track` into synthesized / silence / a real catalog track.

Before this, every reference-short render got the code-synthesized bed unconditionally,
regardless of what (or whether) the operator picked in the Studio dropdown — "No background
music" did nothing (video-quality review §4.5 / operator finding, 26 Oct). Now the choice is
three explicit, named options, and only an explicit pick changes the render; an untouched
job keeps today's exact behavior.
"""
from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tubeforge.core.errors import ProviderValidationError
from tubeforge.pipeline.music import (
    NO_MUSIC_NAME,
    RESERVED_MUSIC_NAMES,
    SYNTHESIZED_MUSIC_NAME,
    MusicCatalog,
    MusicSelection,
    resolve_bed,
)
from tubeforge.rendering.shorts.audio import SR, load_track_bed


def _tone_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(b"".join(struct.pack("<h", round(2_000 * math.sin(2 * math.pi * 220 * i / 16_000)))
                                   for i in range(16_000 * 3)))  # 3 s
    return buffer.getvalue()


def _catalog(tmp_path: Path) -> MusicCatalog:
    catalog = MusicCatalog(tmp_path / "music")
    catalog.upload(name="Quiet Circuit", filename="quiet.wav", payload=_tone_wav(),
                   source_url="https://creator.example/quiet-circuit", license_name="CC BY 4.0",
                   license_url="https://creativecommons.org/licenses/by/4.0/",
                   attribution_required=True, attribution="Quiet Circuit — CC BY 4.0", publishing_allowed=True)
    return catalog


def test_unset_music_track_resolves_to_synthesized_preserving_prior_default():
    assert resolve_bed(None, None) == MusicSelection("synthesized")
    assert resolve_bed(None, SYNTHESIZED_MUSIC_NAME) == MusicSelection("synthesized")


def test_no_background_music_resolves_to_real_silence():
    assert resolve_bed(None, NO_MUSIC_NAME) == MusicSelection("silence")


def test_a_real_track_name_resolves_through_the_catalog(tmp_path):
    catalog = _catalog(tmp_path)
    selection = resolve_bed(catalog, "Quiet Circuit")
    assert selection.kind == "track" and selection.record.name == "Quiet Circuit"


def test_a_track_name_with_no_catalog_configured_fails_loudly():
    with pytest.raises(ProviderValidationError, match="no approved catalog"):
        resolve_bed(None, "Quiet Circuit")


def test_an_unknown_track_name_fails_loudly(tmp_path):
    catalog = _catalog(tmp_path)
    with pytest.raises(ProviderValidationError, match="unavailable"):
        resolve_bed(catalog, "Not Uploaded")


def test_upload_rejects_a_name_that_collides_with_a_reserved_name(tmp_path):
    catalog = MusicCatalog(tmp_path / "music")
    for reserved in RESERVED_MUSIC_NAMES:
        with pytest.raises(ProviderValidationError, match="reserved"):
            catalog.upload(name=reserved, filename="x.wav", payload=_tone_wav(),
                           source_url="https://creator.example/x", license_name="CC BY 4.0",
                           license_url="https://creativecommons.org/licenses/by/4.0/",
                           attribution_required=False, attribution="", publishing_allowed=True)


def test_load_track_bed_trims_loops_fades_and_matches_synth_peak(tmp_path):
    # A short real track (1 s) tiled to fill a longer count, with edge fades and the same
    # pre-duck peak (.12) the synthesized bed targets.
    sr = SR
    short = (np.sin(2 * np.pi * 440 * np.arange(sr) / sr)).astype(np.float32)
    path = tmp_path / "short.wav"
    sf.write(path, short, sr, subtype="PCM_16")
    count = sr * 5  # 5 s, longer than the 1 s source: exercises the tile/loop path
    bed = load_track_bed(path, count, ffmpeg="ffmpeg", deadline=__import__("time").monotonic() + 30, cancelled=lambda: False)
    assert len(bed) == count
    assert abs(float(np.max(np.abs(bed))) - 0.12) < 0.01
    assert bed[0] == pytest.approx(0.0, abs=1e-4)  # fade-in starts at silence
    assert abs(bed[-1]) < 1e-3  # fade-out ends near silence


def test_load_track_bed_trims_a_longer_track_to_fit(tmp_path):
    sr = SR
    long = (np.sin(2 * np.pi * 440 * np.arange(sr * 10) / sr)).astype(np.float32)
    path = tmp_path / "long.wav"
    sf.write(path, long, sr, subtype="PCM_16")
    count = sr * 3
    bed = load_track_bed(path, count, ffmpeg="ffmpeg", deadline=__import__("time").monotonic() + 30, cancelled=lambda: False)
    assert len(bed) == count


def test_load_track_bed_rejects_a_silent_file(tmp_path):
    path = tmp_path / "silent.wav"
    sf.write(path, np.zeros(SR, np.float32), SR, subtype="PCM_16")
    with pytest.raises(ValueError, match="silence"):
        load_track_bed(path, SR, ffmpeg="ffmpeg", deadline=__import__("time").monotonic() + 30, cancelled=lambda: False)


def _record_stub():
    from tubeforge.pipeline.music import MusicTrackRecord
    return MusicTrackRecord(name="Quiet Circuit", path="/music/quiet.wav", checksum_sha256="a" * 64,
                            source_url="https://creator.example/quiet", license_name="CC BY 4.0",
                            license_url="https://creativecommons.org/licenses/by/4.0/", duration_seconds=12.0)


def test_orchestrator_identifies_and_resolves_each_music_selection_kind():
    from tubeforge.pipeline.orchestrator import PipelineOrchestrator

    record = _record_stub()
    assert PipelineOrchestrator._music_identity(MusicSelection("synthesized")) == "synthesized"
    assert PipelineOrchestrator._music_identity(MusicSelection("silence")) == "silence"
    assert PipelineOrchestrator._music_identity(MusicSelection("track", record)) == f"track:{record.checksum_sha256}"
    assert PipelineOrchestrator._music_bed(MusicSelection("synthesized")) == "synthesized"
    assert PipelineOrchestrator._music_bed(MusicSelection("silence")) is None
    assert PipelineOrchestrator._music_bed(MusicSelection("track", record)) == Path(record.path)
