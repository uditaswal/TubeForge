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
