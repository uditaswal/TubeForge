from __future__ import annotations

from pathlib import Path

from tubeforge.core.config import KokoroProviderConfig, PiperProviderConfig
from tubeforge.core.errors import RetryableProviderError
from tubeforge.domain.contracts import VoiceRequest, VoiceResult
from tubeforge.providers.voice.hybrid import HybridVoiceProvider


def _request(voice_id: str) -> VoiceRequest:
    return VoiceRequest(text="A practical engineering lesson.", language="en", voice_id=voice_id, section_id="section-1")


class _KokoroUnavailable:
    settings = KokoroProviderConfig(voices=("af_bella",))

    def synthesize(self, request: VoiceRequest) -> VoiceResult:
        raise RetryableProviderError("model download unavailable")


class _Piper:
    settings = PiperProviderConfig(model_path=Path("voice.onnx"), voice_id="piper-safe")

    def __init__(self) -> None:
        self.request: VoiceRequest | None = None

    def synthesize(self, request: VoiceRequest) -> VoiceResult:
        self.request = request
        return VoiceResult(artifact_path="/tmp/piper.wav", duration_seconds=1.0, checksum_sha256="a" * 64, provider_name="piper")


def test_kokoro_failure_uses_configured_piper_voice() -> None:
    piper = _Piper()
    provider = HybridVoiceProvider(_KokoroUnavailable(), piper)  # type: ignore[arg-type]

    result = provider.synthesize(_request("af_bella"))

    assert result.provider_name == "piper"
    assert piper.request is not None and piper.request.voice_id == "piper-safe"


def test_explicit_piper_selection_bypasses_kokoro() -> None:
    piper = _Piper()
    provider = HybridVoiceProvider(_KokoroUnavailable(), piper)  # type: ignore[arg-type]

    provider.synthesize(_request("piper"))

    assert piper.request is not None and piper.request.voice_id == "piper-safe"
