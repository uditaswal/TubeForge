from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import time
import wave

import pytest

from tubeforge.core.config import PreviewRenderConfig, ShortsFinalRenderConfig
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.pipeline.alignment import WordTiming
from tubeforge.pipeline.captions import render_highlighted_ass
from tubeforge.rendering.preview import PreviewRenderCancelled, PreviewRenderer, TimelineSegment, build_timeline, parse_frame_rate
from tubeforge.rendering.loudness import LoudnessCancelled, second_pass_filter, validate_encoded


class StaticProbe:
    def __init__(self, frame_rate: str = "30000/1001", *, video_codec: str = "h264", audio_codec: str = "aac", sample_rate: int = 48_000) -> None:
        self.frame_rate = frame_rate
        self.video_codec = video_codec
        self.audio_codec = audio_codec
        self.sample_rate = sample_rate

    def inspect(self, path: Path) -> dict[str, object]:
        return {
            "format": {"duration": "1.0"},
            "streams": [
                {"codec_type": "video", "codec_name": self.video_codec, "width": 854, "height": 480, "avg_frame_rate": self.frame_rate},
                {"codec_type": "audio", "codec_name": self.audio_codec, "sample_rate": str(self.sample_rate), "channels": 2},
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


def test_validation_rejects_unexpected_audio_sample_rate(tmp_path: Path) -> None:
    output = tmp_path / "preview.mp4"; output.write_bytes(b"video")
    with pytest.raises(ProviderValidationError, match="expected_sample_rate=48000"):
        PreviewRenderer(PreviewRenderConfig(), probe=StaticProbe(sample_rate=96_000)).validate(output, 1.0)


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


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg is required for process diagnostics")
def test_ffmpeg_failure_preserves_bounded_stderr_tail(tmp_path: Path) -> None:
    renderer = PreviewRenderer(PreviewRenderConfig(minimum_free_bytes=1))
    missing = tmp_path / "missing-input.mp4"
    with pytest.raises(RetryableProviderError, match="FFmpeg preview render failed") as error:
        renderer._run_command(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(missing), "-f", "null", "-"],
            cancellation_requested=None,
            deadline=time.monotonic() + 10,
        )
    assert "No such file or directory" in str(error.value)


def test_loudness_opt_in_changes_render_identity_and_finish_graph(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset = tmp_path / "asset.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"narration")
    captions = tmp_path / "captions.ass"; captions.write_text("[Script Info]\n", encoding="utf-8")
    segments = (TimelineSegment("scene", "section", 0, 1, asset, "a" * 64, "image"),)
    standard = PreviewRenderer(ShortsFinalRenderConfig())
    normalized = PreviewRenderer(ShortsFinalRenderConfig(audio_normalization_enabled=True))
    assert standard.identity(segments, narration, captions) != normalized.identity(segments, narration, captions)
    normalized_identity = normalized.identity(segments, narration, captions)
    monkeypatch.setattr("tubeforge.rendering.preview.LOUDNESS_VERSION", "loudness-test-version")
    assert normalized.identity(segments, narration, captions) != normalized_identity
    command = normalized._bounded_finish_command(tmp_path / "list.txt", narration, captions, tmp_path / "out.mp4", 1, None, "loudnorm=I=-13.5")
    graph = command[command.index("-filter_complex") + 1]
    assert "[1:a]loudnorm=I=-13.5,apad=pad_dur=10[outa]" in graph
    assert command[command.index("-ar") + 1] == "48000"


def test_encoded_loudness_gate_rejects_unbounded_peak() -> None:
    measured = {"input_i": -14.4, "input_tp": -1.2}
    validate_encoded(measured)
    assert "measured_I=-16.0" in second_pass_filter({"input_i": -16.0, "input_tp": 0.0, "input_lra": 2.0, "input_thresh": -26.0, "target_offset": 1.0})
    assert "alimiter=limit=0.77:level=false" in second_pass_filter({"input_i": -16.0, "input_tp": 0.0, "input_lra": 2.0, "input_thresh": -26.0, "target_offset": 1.0})
    with pytest.raises(ProviderValidationError, match="outside the Shorts loudness gate"):
        validate_encoded({"input_i": -14.4, "input_tp": -0.9})


def test_cancelled_music_analysis_never_promotes_a_render(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset = tmp_path / "asset.png"; asset.write_bytes(b"asset")
    narration = tmp_path / "narration.wav"; narration.write_bytes(b"speech")
    captions = tmp_path / "captions.ass"; captions.write_text("[Script Info]\n", encoding="utf-8")
    music = tmp_path / "music.wav"; music.write_bytes(b"music")
    output = tmp_path / "preview.mp4"

    def cancel_analysis(*_args, **_kwargs):
        raise LoudnessCancelled("loudness analysis cancelled")

    monkeypatch.setattr("tubeforge.rendering.preview.analyze_music_mix", cancel_analysis)
    renderer = PreviewRenderer(PreviewRenderConfig(audio_normalization_enabled=True, minimum_free_bytes=1))
    with pytest.raises(PreviewRenderCancelled, match="loudness analysis cancelled"):
        renderer.render((TimelineSegment("scene", "section", 0, 1, asset, "a" * 64, "image"),), narration, captions, output, music=music)
    assert not output.exists()
    assert not (tmp_path / "preview.part.mp4").exists()


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
    renderer = PreviewRenderer(ShortsFinalRenderConfig(video_crf=18))
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
    assert segment[segment.index("-crf") + 1] == "14"
    second = renderer._bounded_segment_command(1, scene, 75, tmp_path / "segment-0001.mp4")
    assert "[0:v]" in second[second.index("-filter_complex") + 1]
    assert "[1:v]" not in second[second.index("-filter_complex") + 1]
    assert "[v1]" in second[second.index("-filter_complex") + 1]
    assert finish[finish.index("-f") + 1] == "concat"
    assert "sidechaincompress=" in finish[finish.index("-filter_complex") + 1]
    assert "subtitles=" in finish[finish.index("-filter_complex") + 1]
    assert finish[finish.index("-crf") + 1] == "18"
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


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="FFmpeg is required for the real timeline render")
def test_bounded_render_preserves_scene_pauses_and_late_caption_cues(tmp_path: Path) -> None:
    """A concat may be shorter than speech; the gap and final cue must survive encoding."""
    assets = []
    for name, color in (("first", "red"), ("second", "blue")):
        asset = tmp_path / f"{name}.png"
        subprocess.run(
            ["ffmpeg", "-nostdin", "-y", "-v", "error", "-f", "lavfi", "-i", f"color=c={color}:s=1080x1920", "-frames:v", "1", str(asset)],
            check=True, capture_output=True, timeout=30,
        )
        assets.append(asset)

    narration = tmp_path / "narration.wav"
    with wave.open(str(narration), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(48_000)
        output.writeframes(bytes(int(2 * 48_000 * 2.5)))

    words = (
        WordTiming("PAUSE", "pause", "section-1", 0, 1.10, 1.25),
        WordTiming("CUE", "pause", "section-1", 1, 1.25, 1.40),
        WordTiming("FINAL", "final", "section-2", 2, 2.10, 2.25),
        WordTiming("CUE", "final", "section-2", 3, 2.25, 2.45),
    )
    captions = tmp_path / "captions.ass"
    captions.write_text(
        render_highlighted_ass(words, width=1080, height=1920, font_size=84, margin_vertical=470, margin_horizontal=96, center_x=490, words_per_cue=2),
        encoding="utf-8",
    )
    segments = (
        TimelineSegment("scene-1", "section-1", 0.0, 1.0, assets[0], "a" * 64, "image"),
        TimelineSegment("scene-2", "section-2", 1.5, 2.5, assets[1], "b" * 64, "image"),
    )
    output = tmp_path / "timeline.mp4"
    renderer = PreviewRenderer(ShortsFinalRenderConfig(image_motion_enabled=False, threads=1, minimum_free_bytes=1, timeout_seconds=120))
    padded_segment = tmp_path / "first-with-pause.mp4"
    subprocess.run(renderer._bounded_segment_command(0, segments[0], 30, padded_segment, tail_pad_frames=15), check=True, capture_output=True, timeout=60)
    segment_info = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(padded_segment)],
        check=True, capture_output=True, text=True, timeout=30,
    )
    assert float(segment_info.stdout) == pytest.approx(1.5, abs=0.04)
    renderer.render(segments, narration, captions, output)

    def pixel_from(path: Path, seconds: float | None = None, x: int = 540, y: int = 900) -> tuple[int, int, int]:
        filters = f"crop=2:2:{x}:{y},format=rgb24" if seconds is None else f"select='gte(t,{seconds:.3f})',crop=2:2:{x}:{y},format=rgb24"
        result = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-i", str(path), "-vf", filters, "-frames:v", "1", "-f", "rawvideo", "-"],
            check=True, capture_output=True, timeout=30,
        )
        assert len(result.stdout) == 12
        return tuple(result.stdout[:3])  # type: ignore[return-value]

    first_color = pixel_from(assets[0])
    second_color = pixel_from(assets[1])
    during_pause = pixel_from(output, 1.25)
    after_pause = pixel_from(output, 1.75)
    distance = lambda left, right: sum((a - b) ** 2 for a, b in zip(left, right, strict=True))
    assert distance(during_pause, first_color) < distance(during_pause, second_color)
    assert distance(after_pause, second_color) < distance(after_pause, first_color)

    cue = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-i", str(output), "-vf", "select='gte(t,2.20)',crop=800:180:90:1330,format=gray", "-frames:v", "1", "-f", "rawvideo", "-"],
        check=True, capture_output=True, timeout=30,
    )
    assert sum(value > 120 for value in cue.stdout) > 100
