import sys
from types import SimpleNamespace

from tubeforge.core.config import KokoroProviderConfig
from tubeforge.domain.contracts import VoiceRequest
from tubeforge.providers.voice.kokoro import KokoroVoiceProvider


def test_model_and_voice_bytes_bind_cache_and_model_lifetime(tmp_path, monkeypatch):
    constructions = []
    class Runtime:
        def __init__(self, *paths):
            constructions.append(paths)
        def create(self, *args, **kwargs):
            return [.1, -.1] * 1000, 24000
    monkeypatch.setitem(sys.modules, "kokoro_onnx", SimpleNamespace(Kokoro=Runtime))
    model, voices = tmp_path / "model.onnx", tmp_path / "voices.bin"
    model.write_bytes(b"first model")
    voices.write_bytes(b"first voice pack")
    provider = KokoroVoiceProvider(KokoroProviderConfig(model_path=model, voices_path=voices,
                                                       cache_root=tmp_path / "cache"))
    request = VoiceRequest(text="A short test sentence.", language="en", voice_id="af_bella", section_id="s1")
    first = provider.synthesize(request)
    assert provider.synthesize(request).artifact_path == first.artifact_path
    assert provider.calls == 1
    provider.synthesize(request.model_copy(update={"text": "A different test sentence."}))
    assert len(constructions) == 1
    model.write_bytes(b"changed model")
    second = provider.synthesize(request)
    assert first.artifact_path != second.artifact_path
    assert len(constructions) == 2
    voices.write_bytes(b"changed voice pack")
    third = provider.synthesize(request)
    assert second.artifact_path != third.artifact_path
    assert len(constructions) == 3
