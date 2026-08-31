from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import pytest

from tubeforge.core.config import PiperProviderConfig
from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import VoiceRequest
from tubeforge.providers.voice.piper import PiperVoiceProvider


def _write_wave(path: Path, *, frames: int = 800) -> None:
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8_000)
        stream.writeframes(b"\x00\x00" * frames)


def _request(output: Path) -> VoiceRequest:
    return VoiceRequest(
        section_id="section-1",
        phrase_id="phrase-1",
        text="A locally generated narration phrase.",
        language="en",
        voice_id="test-voice",
        output_path=str(output),
    )


def test_valid_cached_wave_is_reused_without_starting_piper(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    output = tmp_path / "cached.wav"
    _write_wave(output)
    provider = PiperVoiceProvider(PiperProviderConfig(model_path=model))

    def unexpected(*args, **kwargs):
        raise AssertionError("a valid Piper cache entry must be reused")

    monkeypatch.setattr(subprocess, "run", unexpected)
    result = provider.synthesize(_request(output))

    assert result.artifact_path == str(output)
    assert result.duration_seconds == 0.1
    assert provider.calls == 0


def test_oversized_cached_wave_is_regenerated_and_atomically_replaced(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    output = tmp_path / "cached.wav"
    _write_wave(output, frames=2_000)
    provider = PiperVoiceProvider(PiperProviderConfig(model_path=model, max_output_bytes=1_024))

    def synthesize(command, **kwargs):
        generated = Path(command[command.index("--output_file") + 1])
        _write_wave(generated, frames=200)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", synthesize)
    result = provider.synthesize(_request(output))

    assert provider.calls == 1
    assert result.duration_seconds == 0.025
    assert output.stat().st_size < 1_024
    assert not list(tmp_path.glob("piper-*.wav"))


def test_truncated_cached_wave_is_regenerated(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    output = tmp_path / "cached.wav"
    _write_wave(output, frames=800)
    output.write_bytes(output.read_bytes()[:-100])
    provider = PiperVoiceProvider(PiperProviderConfig(model_path=model))

    def synthesize(command, **kwargs):
        generated = Path(command[command.index("--output_file") + 1])
        _write_wave(generated, frames=400)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", synthesize)
    result = provider.synthesize(_request(output))

    assert provider.calls == 1
    assert result.duration_seconds == 0.05
    with wave.open(str(output), "rb") as stream:
        assert len(stream.readframes(stream.getnframes())) == 800


def test_piper_rejects_output_with_unexpected_configured_sample_rate(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    output = tmp_path / "narration.wav"
    provider = PiperVoiceProvider(PiperProviderConfig(model_path=model, sample_rate=16_000))

    def synthesize(command, **kwargs):
        generated = Path(command[command.index("--output_file") + 1])
        _write_wave(generated)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    monkeypatch.setattr(subprocess, "run", synthesize)

    with pytest.raises(ProviderValidationError, match="invalid audio"):
        provider.synthesize(_request(output))

    assert not output.exists()
    assert not list(tmp_path.glob("piper-*.wav"))


def test_packaged_python_module_mode_uses_piper_short_flags(tmp_path: Path) -> None:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"model")
    provider = PiperVoiceProvider(PiperProviderConfig(executable="python", model_path=model))
    command = provider.command(_request(tmp_path / "voice.wav"), tmp_path / "voice.wav")
    assert command[:3] == ["python", "-m", "piper"]
    assert "-m" in command and "-f" in command
