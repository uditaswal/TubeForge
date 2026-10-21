from __future__ import annotations

import io
import wave
from email.message import Message
from pathlib import Path

import pytest

from tubeforge.core.config import PiperProviderConfig
from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import VoiceRequest
from tubeforge.providers.voice.piper_http import PiperHttpVoiceProvider, _checksum


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(22_050)
        output.writeframes(b"\0\0" * 2_205)
    return buffer.getvalue()


class _Response:
    status = 200

    def __init__(self, body: bytes, voice: str, model: str) -> None:
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = "audio/wav"
        self.headers["X-Piper-Voice"] = voice
        self.headers["X-Piper-Model-SHA256"] = model

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, size: int) -> bytes:
        return self.body[:size]


def test_http_piper_checks_service_identity_and_caches_atomic_wave(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"pinned model")
    settings = PiperProviderConfig(
        server_url="http://127.0.0.1:5000",
        model_path=model,
        voice_id="test-voice",
        sample_rate=22_050,
        cache_root=tmp_path / "cache",
    )
    provider = PiperHttpVoiceProvider(settings)
    response = _Response(_wav(), settings.voice_id, _checksum(model))
    calls: list[object] = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: (calls.append(args[0]) or response))
    request = VoiceRequest(text="A local phrase.", language="en", voice_id="test-voice", section_id="section-1", phrase_id="phrase-1")

    first = provider.synthesize(request)
    second = provider.synthesize(request)

    assert first.checksum_sha256 == second.checksum_sha256
    assert first.duration_seconds == pytest.approx(0.1)
    assert len(calls) == 1
    assert Path(first.artifact_path).is_file()
    assert not list(Path(first.artifact_path).parent.glob("piper-http-*.wav"))


def test_http_piper_rejects_a_service_using_another_model(tmp_path: Path, monkeypatch) -> None:
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"pinned model")
    settings = PiperProviderConfig(
        server_url="http://127.0.0.1:5000", model_path=model,
        voice_id="test-voice", cache_root=tmp_path / "cache",
    )
    provider = PiperHttpVoiceProvider(settings)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: _Response(_wav(), settings.voice_id, "0" * 64),
    )

    with pytest.raises(ProviderValidationError, match="model does not match"):
        provider.synthesize(VoiceRequest(text="A phrase.", language="en", voice_id="test-voice", section_id="section-1", phrase_id="phrase-1"))
    assert not list((tmp_path / "cache").rglob("*.wav"))
