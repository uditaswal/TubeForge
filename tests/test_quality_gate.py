from __future__ import annotations

from pathlib import Path

from tubeforge.core.errors import ProviderValidationError
from tubeforge.pipeline.quality import validate_final_artifact


class _Renderer:
    def validate(self, path: Path, expected: float) -> dict[str, object]:
        if path.read_bytes() == b"broken": raise ProviderValidationError("ffprobe rejected preview output")
        return {"duration_seconds": expected, "width": 1920, "height": 1080, "fps": 30, "video_codec": "h264", "audio_codec": "aac"}


def test_quality_gate_passes_with_warning_and_caption_artifact(tmp_path: Path) -> None:
    video, captions = tmp_path / "final.mp4", tmp_path / "captions.srt"
    video.write_bytes(b"x" * 2048); captions.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    report = validate_final_artifact(path=video, expected_duration=1.0, renderer=_Renderer(), captions_path=captions, captions_required=True)
    assert report.passed
    assert any(item.code == "black_frame_detection_unavailable" for item in report.findings)


def test_quality_gate_blocks_missing_captions_or_bad_probe(tmp_path: Path) -> None:
    video = tmp_path / "final.mp4"; video.write_bytes(b"broken")
    report = validate_final_artifact(path=video, expected_duration=1.0, renderer=_Renderer(), captions_path=None, captions_required=True)
    assert not report.passed
    assert report.findings[0].code == "media_probe_failed"
