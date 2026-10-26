"""Weighted Kokoro voice blends (VoiceStudio competitive-analysis Action 12).

A blend is a new acoustic timbre, built purely from the operator's own configured voices —
same text, same word count, same alignment, only the style vector fed to Kokoro differs.
"""
from __future__ import annotations

import shutil

import numpy as np
import pytest

from tubeforge.core.config import KokoroProviderConfig
from tubeforge.domain.contracts import VoiceRequest
from tubeforge.providers.voice.kokoro import KokoroVoiceProvider
from tubeforge.providers.voice.voice_blend import parse_blend_spec, resolve_blend


def test_parse_blend_spec_normalizes_weights_to_one():
    parsed = parse_blend_spec("af_bella:0.7+af_sarah:0.3")
    assert parsed == (("af_bella", 0.7), ("af_sarah", 0.3))
    parsed2 = parse_blend_spec("af_bella:7+af_sarah:3")
    assert parsed2[0][1] == pytest.approx(0.7) and parsed2[1][1] == pytest.approx(0.3)


@pytest.mark.parametrize("bad", (
    "af_bella",                       # only one component
    "af_bella:0.5+af_bella:0.5",      # duplicate name
    "af_bella:0+af_sarah:1",          # zero weight
    "af_bella:-1+af_sarah:2",         # negative weight
    "af_bella:abc+af_sarah:1",        # not a number
    "af_bella-0.5+af_sarah-0.5",      # wrong separator
))
def test_parse_blend_spec_rejects_malformed_or_degenerate_specs(bad):
    with pytest.raises(ValueError):
        parse_blend_spec(bad)


def test_resolve_blend_weights_the_style_vectors():
    styles = {"a": np.array([1.0, 0.0], dtype=np.float32), "b": np.array([0.0, 1.0], dtype=np.float32)}
    blended = resolve_blend(lambda name: styles[name], "a:0.25+b:0.75")
    assert np.allclose(blended, [0.25, 0.75])


def test_config_rejects_blend_naming_unconfigured_voice_or_colliding_with_a_plain_voice():
    with pytest.raises(ValueError, match="unconfigured voices"):
        KokoroProviderConfig(voices=("af_bella", "af_sarah"),
                             voice_blends={"mix": "af_bella:0.5+am_michael:0.5"})
    with pytest.raises(ValueError, match="collide"):
        KokoroProviderConfig(voices=("af_bella", "af_sarah"), voice_blends={"af_bella": "af_bella:1+af_sarah:1"})


def test_config_accepts_a_valid_blend():
    settings = KokoroProviderConfig(voices=("af_bella", "af_sarah"),
                                    voice_blends={"mix": "af_bella:0.7+af_sarah:0.3"})
    assert settings.voice_blends == {"mix": "af_bella:0.7+af_sarah:0.3"}


def _real_kokoro_settings():
    import importlib.util
    from pathlib import Path

    from tubeforge.core.config import REPOSITORY_ROOT

    if importlib.util.find_spec("kokoro_onnx") is None:
        return None
    model = REPOSITORY_ROOT / "models" / "kokoro-v1.0.int8.onnx"
    voices = REPOSITORY_ROOT / "models" / "voices-v1.0.bin"
    if not model.is_file() or not voices.is_file():
        return None
    return KokoroProviderConfig(voices=("af_bella", "af_sarah"),
                                voice_blends={"blend": "af_bella:0.6+af_sarah:0.4"},
                                model_path=model, voices_path=voices)


@pytest.mark.skipif(_real_kokoro_settings() is None, reason="Kokoro runtime/model not available on this host")
def test_blend_synthesizes_real_audio_distinct_from_either_pure_voice(tmp_path):
    settings = _real_kokoro_settings()
    provider = KokoroVoiceProvider(settings)
    text = "This is a short synthetic sentence used only to compare voice timbres."

    blended = provider.synthesize(VoiceRequest(text=text, language="en", voice_id="blend",
                                               section_id="s", output_path=str(tmp_path / "blend.wav")))
    bella = provider.synthesize(VoiceRequest(text=text, language="en", voice_id="af_bella",
                                             section_id="s", output_path=str(tmp_path / "bella.wav")))
    sarah = provider.synthesize(VoiceRequest(text=text, language="en", voice_id="af_sarah",
                                             section_id="s", output_path=str(tmp_path / "sarah.wav")))

    assert blended.checksum_sha256 not in (bella.checksum_sha256, sarah.checksum_sha256)
    # Same spoken text through the same engine should take about the same time to say.
    assert abs(blended.duration_seconds - bella.duration_seconds) < 1.0
