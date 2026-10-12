from __future__ import annotations

from pathlib import Path

import pytest

from tubeforge.core.config import PreviewRenderConfig, ShortsFinalRenderConfig
from tubeforge.core.errors import ProviderValidationError
from tubeforge.rendering.preview import PreviewRenderCancelled, PreviewRenderer, TimelineSegment, build_timeline, parse_frame_rate


class StaticProbe:
    def __init__(self, frame_rate: str = "30000/1001", *, video_codec: str = "h264", audio_codec: str = "aac") -> None:
        self.frame_rate = frame_rate
        self.video_codec = video_codec
        self.audio_codec = audio_codec

    def inspect(self, path: Path) -> dict[str, object]:
        return {
            "format": {"duration": "1.0"},
            "streams": [
                {"codec_type": "video", "codec_name": self.video_codec, "width": 854, "height": 480, "avg_frame_rate": self.frame_rate},
                {"codec_type": "audio", "codec_name": self.audio_codec, "sample_rate": "44100", "channels": 2},
            ],
        }


class RunningProcess:
    def __init__(self, command: list[str]) -> None:
        self.command = command
        self.returncode: int | None = None
        self.terminated = False
        self.waited = False
        Path(command[-1]).write_bytes(b"partial")

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        self.returncode = -15
        return self.returncode


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
    graph = command[command.index("-filter_complex") + 1]
    assert "scale=2560:1440" in graph
    assert "zoompan=" in graph and "s=1280x720" in graph
    assert "tpad=stop_mode=clone:stop_duration=10" in command[command.index("-filter_complex") + 1]
    assert "apad=pad_dur=10[outa]" in command[command.index("-filter_complex") + 1]
    assert "-shortest" not in command
    assert command[command.index("-t") + 1] == "1.000000"
    assert command[-1].endswith("preview.mp4.part")


def test_frame_rate_and_encoder_validation_are_explicit() -> None:
    assert parse_frame_rate("30000/1001") == pytest.approx(29.97003)
    with pytest.raises(ProviderValidationError):
        parse_frame_rate("0/0")
    with pytest.raises(ProviderValidationError):
        parse_frame_rate("NaN/1")
    with pytest.raises(ValueError, match="unsupported video encoder"):
        PreviewRenderConfig(video_codec="vp9")
    with pytest.raises(ValueError, match="unsupported audio encoder"):
        PreviewRenderConfig(audio_codec="mp3")


def test_validation_enforces_configured_rational_fps_and_records_probe_values(tmp_path: Path) -> None:
    output = tmp_path / "preview.mp4"; output.write_bytes(b"video")
    renderer = PreviewRenderer(PreviewRenderConfig(fps=30), probe=StaticProbe())
    metadata = renderer.validate(output, 1.0)
    assert metadata["fps"] == pytest.approx(29.97003)
    assert metadata["video_codec"] == "h264"
    assert metadata["audio_codec"] == "aac"
    with pytest.raises(ProviderValidationError, match="stream metadata"):
        PreviewRenderer(PreviewRenderConfig(fps=24), probe=StaticProbe()).validate(output, 1.0)


def test_validation_rejects_nonfinite_container_duration(tmp_path: Path) -> None:
    output = tmp_path / "preview.mp4"; output.write_bytes(b"video")

    class NonfiniteProbe(StaticProbe):
        def inspect(self, path: Path) -> dict[str, object]:
            data = super().inspect(path)
            data["format"] = {"duration": "NaN"}
            return data

    with pytest.raises(ProviderValidationError, match="stream metadata"):
        PreviewRenderer(PreviewRenderConfig(), probe=NonfiniteProbe()).validate(output, 1.0)


def test_timeline_rejects_nonfinite_persisted_timing() -> None:
    class Package:
        script_sections = ()

    timing = {"phrases": [{"section_id": "section", "start_seconds": "NaN", "end_seconds": 1}], "final_duration_seconds": 1}
    with pytest.raises(ProviderValidationError, match="timing map"):
        build_timeline(Package(), timing, {}, tolerance=0.01)  # type: ignore[arg-type]


def test_cancellation_terminates_reaps_and_removes_partial_output(tmp_path: Path) -> None:
    asset = tmp_path / "asset.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"narration")
    captions = tmp_path / "captions.vtt"; captions.write_text("WEBVTT\n", encoding="utf-8")
    created: list[RunningProcess] = []

    def factory(command, **_kwargs):
        process = RunningProcess(command)
        created.append(process)
        return process

    checks = iter((False, False, True))
    renderer = PreviewRenderer(PreviewRenderConfig(minimum_free_bytes=1), process_factory=factory, poll_seconds=0)
    with pytest.raises(PreviewRenderCancelled, match="cancelled during FFmpeg"):
        renderer.render(
            (TimelineSegment("scene", "section", 0, 1, asset, "a" * 64, "image"),), narration, captions,
            tmp_path / "preview.mp4", cancellation_requested=lambda: next(checks),
        )
    assert created[0].terminated and created[0].waited
    assert not (tmp_path / "preview.mp4.part").exists()
    assert not (tmp_path / "preview.mp4").exists()


def test_renderer_template_version_changes_identity(tmp_path: Path) -> None:
    asset = tmp_path / "asset.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"narration")
    captions = tmp_path / "captions.vtt"; captions.write_text("WEBVTT\n", encoding="utf-8")
    segments = (TimelineSegment("scene", "section", 0, 1, asset, "a" * 64, "image"),)
    config = PreviewRenderConfig()
    assert PreviewRenderer(config, template_version="one").identity(segments, narration, captions) != PreviewRenderer(config, template_version="two").identity(segments, narration, captions)


def test_image_motion_can_be_disabled_without_changing_video_asset_handling(tmp_path: Path) -> None:
    asset = tmp_path / "asset.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"narration")
    captions = tmp_path / "captions.vtt"; captions.write_text("WEBVTT\n", encoding="utf-8")
    renderer = PreviewRenderer(PreviewRenderConfig(image_motion_enabled=False))
    command = renderer.command(
        (TimelineSegment("scene", "section", 0, 1, asset, "a" * 64, "image"),),
        narration,
        captions,
        tmp_path / "preview.mp4.part",
    )
    assert "zoompan=" not in command[command.index("-filter_complex") + 1]


def test_bounded_final_commands_use_one_scene_at_a_time_and_keep_audio_mix(tmp_path: Path) -> None:
    renderer = PreviewRenderer(ShortsFinalRenderConfig())
    asset = tmp_path / "scene.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"speech")
    captions = tmp_path / "captions.ass"; captions.write_text("[Script Info]\n", encoding="utf-8")
    music = tmp_path / "music.wav"; music.write_bytes(b"music")
    scene = TimelineSegment("scene", "section", 0, 2.5, asset, "a" * 64, "image")
    segment = renderer._bounded_segment_command(0, scene, 75, tmp_path / "segment-0000.mp4")
    finish = renderer._bounded_finish_command(tmp_path / "segments.txt", narration, captions, tmp_path / "final.mp4", 2.5, music)

    assert renderer.config.bounded_memory
    assert segment.count("-i") == 1 and "zoompan=" in segment[segment.index("-filter_complex") + 1]
    assert segment[segment.index("-frames:v") + 1] == "75"
    second = renderer._bounded_segment_command(1, scene, 75, tmp_path / "segment-0001.mp4")
    assert "[0:v]" in second[second.index("-filter_complex") + 1]
    assert "[1:v]" not in second[second.index("-filter_complex") + 1]
    assert "[v1]" in second[second.index("-filter_complex") + 1]
    assert finish[finish.index("-f") + 1] == "concat"
    assert "sidechaincompress=" in finish[finish.index("-filter_complex") + 1]
    assert "subtitles=" in finish[finish.index("-filter_complex") + 1]
    assert finish[-1].endswith("final.mp4")


def test_bounded_render_cancellation_removes_segments_and_partial_output(tmp_path: Path) -> None:
    asset = tmp_path / "scene.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"speech")
    captions = tmp_path / "captions.ass"; captions.write_text("[Script Info]\n", encoding="utf-8")
    segment = TimelineSegment("scene", "section", 0, 1, asset, "a" * 64, "image")
    created: list[RunningProcess] = []

    def factory(command, **_kwargs):
        process = RunningProcess(command)
        created.append(process)
        return process

    checks = iter((False, False, False, True))
    renderer = PreviewRenderer(ShortsFinalRenderConfig(minimum_free_bytes=1), process_factory=factory, poll_seconds=0)
    with pytest.raises(PreviewRenderCancelled, match="cancelled during FFmpeg"):
        renderer.render((segment,), narration, captions, tmp_path / "final.mp4", cancellation_requested=lambda: next(checks))

    assert created[0].terminated and created[0].waited
    assert not (tmp_path / "final.mp4").exists()
    assert not (tmp_path / "final.part.mp4").exists()
    assert not list(tmp_path.glob("final.part.segments-*"))
