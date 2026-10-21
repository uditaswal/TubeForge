from __future__ import annotations

import io
import math
import struct
import wave
from pathlib import Path

import pytest

from tubeforge.core.errors import ProviderValidationError
from tubeforge.pipeline.music import MusicCatalog
from tubeforge.rendering.preview import PreviewRenderer, TimelineSegment
from tubeforge.core.config import PreviewRenderConfig


def _tone() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16_000)
        stream.writeframes(b"".join(struct.pack("<h", round(2_000 * math.sin(2 * math.pi * 220 * index / 16_000))) for index in range(16_000)))
    return buffer.getvalue()


def test_music_catalog_requires_real_publishable_terms_and_retains_provenance(tmp_path: Path) -> None:
    catalog = MusicCatalog(tmp_path / "music")
    record = catalog.upload(
        name="Quiet Circuit",
        filename="quiet.wav",
        payload=_tone(),
        source_url="https://creator.example/quiet-circuit",
        license_name="CC BY 4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        attribution_required=True,
        attribution="Quiet Circuit by Example Creator — CC BY 4.0",
        publishing_allowed=True,
    )

    assert catalog.resolve("Quiet Circuit") == record
    assert Path(record.path).is_file()
    assert record.attribution_required and record.duration_seconds == pytest.approx(1.0, abs=0.02)

    Path(record.path).write_bytes(b"tampered")
    with pytest.raises(ProviderValidationError, match="unavailable"):
        catalog.resolve("Quiet Circuit")

    with pytest.raises(ProviderValidationError, match="actual licence"):
        catalog.upload(
            name="Vague track",
            filename="vague.wav",
            payload=_tone(),
            source_url="https://creator.example/vague",
            license_name="royalty-free",
            license_url="https://creator.example/terms",
            attribution_required=False,
            attribution="",
            publishing_allowed=True,
        )
    with pytest.raises(ProviderValidationError, match="publishing use"):
        catalog.upload(
            name="Not cleared", filename="uncleared.wav", payload=_tone(),
            source_url="https://creator.example/uncleared", license_name="CC BY 4.0",
            license_url="https://creativecommons.org/licenses/by/4.0/",
            attribution_required=False, attribution="", publishing_allowed=False,
        )


def test_renderer_ducks_quiet_music_beneath_narration(tmp_path: Path) -> None:
    asset = tmp_path / "asset.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"narration")
    music = tmp_path / "music.wav"; music.write_bytes(b"music")
    captions = tmp_path / "captions.ass"; captions.write_text("[Script Info]\n", encoding="utf-8")
    renderer = PreviewRenderer(PreviewRenderConfig())
    command = renderer.command(
        (TimelineSegment("scene", "section", 0, 1, asset, "a" * 64, "image"),),
        narration,
        captions,
        tmp_path / "preview.mp4",
        music=music,
    )
    graph = command[command.index("-filter_complex") + 1]

    assert "volume=0.16" in graph
    assert "sidechaincompress=" in graph
    assert "amix=inputs=2:duration=first:normalize=0" in graph
    assert command.count("-stream_loop") == 1


def test_normalized_music_graph_keeps_ducking_before_loudness_pass(tmp_path: Path) -> None:
    renderer = PreviewRenderer(PreviewRenderConfig(audio_normalization_enabled=True))
    asset = tmp_path / "asset.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"speech")
    music = tmp_path / "music.wav"; music.write_bytes(b"music")
    captions = tmp_path / "captions.ass"; captions.write_text("[Script Info]\n", encoding="utf-8")
    scene = (TimelineSegment("scene", "section", 0, 1, asset, "a" * 64, "image"),)
    command = renderer.command(scene, narration, captions, tmp_path / "out.mp4", music=music, audio_filter="loudnorm=I=-13.5")
    graph = command[command.index("-filter_complex") + 1]
    assert graph.index("sidechaincompress") < graph.index("amix=inputs=2") < graph.index("loudnorm=I=-13.5")
    assert "alimiter=limit=0.95,loudnorm=I=-13.5,apad=pad_dur=10[outa]" in graph
