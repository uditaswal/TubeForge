from __future__ import annotations

from pathlib import Path

from tubeforge.core.config import PreviewRenderConfig
from tubeforge.rendering.preview import PreviewRenderer, TimelineSegment


def test_preview_command_uses_argument_array_and_profile(tmp_path: Path) -> None:
    asset = tmp_path / "asset.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"narration")
    captions = tmp_path / "captions.vtt"; captions.write_text("WEBVTT\n", encoding="utf-8")
    renderer = PreviewRenderer(PreviewRenderConfig(width=1280, height=720, fps=24))
    command = renderer.command(
        (TimelineSegment("scene", "section", 0, 1, asset, "a" * 64, "image"),),
        narration, captions, tmp_path / "preview.mp4.part",
    )
    assert command[0] == "ffmpeg"
    assert "-filter_complex" in command
    assert "shell=True" not in command
    assert "scale=1280:720" in command[command.index("-filter_complex") + 1]
    assert command[-1].endswith("preview.mp4.part")
