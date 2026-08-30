from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import pytest

from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.rendering.audio import FFmpegAudioAssembler, FFprobe


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "narration.wav"
    path.write_bytes(b"not-empty")
    return path


def _completed(payload: dict[str, object]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(["ffprobe"], 0, json.dumps(payload).encode(), b"")


def test_ffprobe_accepts_complete_audio_stream_metadata(tmp_path: Path, monkeypatch) -> None:
    path = _artifact(tmp_path)
    payload = {
        "format": {"duration": "61.25"},
        "streams": [
            {
                "codec_type": "audio",
                "codec_name": "pcm_s16le",
                "sample_rate": "22050",
                "channels": 1,
            }
        ],
    }
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _completed(payload))

    inspected = FFprobe().inspect(path)

    assert inspected["duration_seconds"] == 61.25
    assert inspected["streams"] == payload["streams"]


@pytest.mark.parametrize(
    "payload",
    (
        {"format": {"duration": "61.25"}, "streams": []},
        {
            "format": {"duration": "61.25"},
            "streams": [{"codec_type": "video", "codec_name": "h264"}],
        },
        {
            "format": {"duration": "61.25"},
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "pcm_s16le",
                    "sample_rate": "0",
                    "channels": 1,
                }
            ],
        },
    ),
)
def test_ffprobe_rejects_duration_without_usable_audio_stream(
    tmp_path: Path, monkeypatch, payload: dict[str, object]
) -> None:
    path = _artifact(tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _completed(payload))

    with pytest.raises(ProviderValidationError, match="ffprobe returned invalid"):
        FFprobe().inspect(path)


def test_ffprobe_rejects_non_utf8_output_as_validation_error(tmp_path: Path, monkeypatch) -> None:
    path = _artifact(tmp_path)
    completed = subprocess.CompletedProcess(["ffprobe"], 0, b"\xff", b"")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(ProviderValidationError, match="invalid duration data"):
        FFprobe().inspect(path)


def test_ffprobe_rejects_nonfinite_duration(tmp_path: Path, monkeypatch) -> None:
    path = _artifact(tmp_path)
    payload = {
        "format": {"duration": "NaN"},
        "streams": [{"codec_type": "audio", "codec_name": "pcm_s16le", "sample_rate": "22050", "channels": 1}],
    }
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: _completed(payload))

    with pytest.raises(ProviderValidationError, match="audio stream metadata"):
        FFprobe().inspect(path)


def test_ffprobe_command_requests_stream_type_used_by_validation(tmp_path: Path) -> None:
    command = FFprobe().command(tmp_path / "narration.wav")

    projection = command[command.index("-show_entries") + 1]
    assert "stream=codec_type," in projection


def test_audio_assembler_normalizes_piper_phrases_and_pauses_before_concat(tmp_path: Path) -> None:
    command = FFmpegAudioAssembler().command(
        (tmp_path / "phrase-one.wav", tmp_path / "phrase-two.wav"),
        tmp_path / "narration.wav",
        0.15,
    )

    filters = command[command.index("-filter_complex") + 1]
    assert command.count("-i") == 3
    assert "anullsrc=r=48000:cl=mono" in command
    assert filters.count("aresample=48000,aformat=sample_fmts=s16:channel_layouts=mono") == 3
    assert "[n0][n1][n2]concat=n=3:v=0:a=1[outa]" in filters


def test_audio_assembler_rejects_nonfinite_pause(tmp_path: Path) -> None:
    phrase = tmp_path / "phrase.wav"
    phrase.write_bytes(b"audio")

    with pytest.raises(ProviderValidationError, match="finite and nonnegative"):
        FFmpegAudioAssembler().assemble((phrase,), tmp_path / "narration.wav", pause_seconds=float("nan"))


def test_audio_assembler_removes_stale_temporary_before_run(tmp_path: Path, monkeypatch) -> None:
    phrase = tmp_path / "phrase.wav"
    phrase.write_bytes(b"audio")
    output = tmp_path / "narration.wav"
    temporary = tmp_path / "narration.tmp.wav"
    temporary.write_bytes(b"stale-output")

    def successful_without_output(*args, **kwargs):
        assert not temporary.exists()
        return subprocess.CompletedProcess(args[0], 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", successful_without_output)

    with pytest.raises(RetryableProviderError, match="assembly failed"):
        FFmpegAudioAssembler().assemble((phrase,), output)
    assert not temporary.exists()
    assert not output.exists()


def _write_normalized_wave(path: Path) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(48_000)
        stream.writeframes(b"\x00\x00" * 480)


def test_audio_assembler_promotes_only_validated_normalized_wave(tmp_path: Path, monkeypatch) -> None:
    phrase = tmp_path / "phrase.wav"
    phrase.write_bytes(b"audio")
    output = tmp_path / "narration.wav"
    temporary = tmp_path / "narration.tmp.wav"

    def successful_process(*args, **kwargs):
        _write_normalized_wave(temporary)
        return subprocess.CompletedProcess(args[0], 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", successful_process)

    FFmpegAudioAssembler().assemble((phrase,), output)

    assert output.is_file()
    assert not temporary.exists()


def test_audio_assembler_rejects_corrupt_success_output_before_promotion(tmp_path: Path, monkeypatch) -> None:
    phrase = tmp_path / "phrase.wav"
    phrase.write_bytes(b"audio")
    output = tmp_path / "narration.wav"
    temporary = tmp_path / "narration.tmp.wav"

    def successful_process_with_corrupt_output(*args, **kwargs):
        temporary.write_bytes(b"not a wave file" * 8)
        return subprocess.CompletedProcess(args[0], 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", successful_process_with_corrupt_output)

    with pytest.raises(RetryableProviderError, match="assembly failed"):
        FFmpegAudioAssembler().assemble((phrase,), output)
    assert not temporary.exists()
    assert not output.exists()


@pytest.mark.parametrize(
    ("failure", "message"),
    (
        (subprocess.TimeoutExpired(["ffmpeg"], 1), "timed out"),
        (FileNotFoundError("ffmpeg"), "unavailable"),
    ),
)
def test_audio_assembler_cleans_partial_output_on_process_exception(
    tmp_path: Path, monkeypatch, failure: Exception, message: str
) -> None:
    phrase = tmp_path / "phrase.wav"
    phrase.write_bytes(b"audio")
    output = tmp_path / "narration.wav"
    temporary = tmp_path / "narration.tmp.wav"

    def fail_after_partial(*args, **kwargs):
        temporary.write_bytes(b"partial")
        raise failure

    monkeypatch.setattr(subprocess, "run", fail_after_partial)

    with pytest.raises((RetryableProviderError, ProviderValidationError), match=message):
        FFmpegAudioAssembler().assemble((phrase,), output)
    assert not temporary.exists()
    assert not output.exists()
