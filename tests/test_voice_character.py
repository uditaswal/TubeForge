"""Per-channel acoustic voice character: optional voice/blend + speed (M-AU3).

Config-only and opt-in: a channel absent from `channel_voice_characters` must behave exactly
as before this feature existed.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from tubeforge.core.config import ChannelVoiceCharacter, CodexProviderConfig
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.providers.content.youtube_skills import channel_voice_character_for
from tubeforge.rendering.shorts.prepare import channel_scaled_speed


def _minimal_request(**overrides):
    return ContentRequest(
        topic="t", angle="a", target_duration_seconds=60, language="en", audience="general",
        prompt_version="m6-content-v7",
        sources=(SourceReference(source_id="operator-notes", url="https://local.invalid/x", title="t", excerpt="e"),),
        **overrides,
    )


def test_channel_without_a_character_is_unaffected():
    config = CodexProviderConfig()
    assert channel_voice_character_for(config, "default", None) == (None, 1.0)
    assert channel_voice_character_for(config, "default", "af_bella") == ("af_bella", 1.0)


def test_channel_character_supplies_voice_and_speed_when_operator_did_not_choose():
    config = CodexProviderConfig(channel_voice_characters={"news": ChannelVoiceCharacter(voice_id="am_michael", speed_scale=1.1)})
    assert channel_voice_character_for(config, "news", None) == ("am_michael", 1.1)


def test_operators_explicit_voice_choice_wins_but_channel_speed_still_applies():
    config = CodexProviderConfig(channel_voice_characters={"news": ChannelVoiceCharacter(voice_id="am_michael", speed_scale=1.1)})
    assert channel_voice_character_for(config, "news", "af_sarah") == ("af_sarah", 1.1)


def test_unconfigured_channel_falls_back_to_default_identity():
    config = CodexProviderConfig(default_channel_identity="news", channel_voice_characters={"news": ChannelVoiceCharacter(voice_id="am_michael")})
    assert channel_voice_character_for(config, None, None) == ("am_michael", 1.0)


def test_channel_voice_character_speed_scale_is_bounded():
    with pytest.raises(ValidationError):
        ChannelVoiceCharacter(voice_id="af_bella", speed_scale=2.0)
    with pytest.raises(ValidationError):
        ChannelVoiceCharacter(voice_id="af_bella", speed_scale=0.1)


def test_channel_voice_characters_reject_bad_identities():
    with pytest.raises(ValidationError):
        CodexProviderConfig(channel_voice_characters={"bad id!": ChannelVoiceCharacter(voice_id="af_bella")})


def test_content_request_voice_speed_scale_defaults_unchanged_and_is_bounded():
    assert ContentRequest.model_fields["voice_speed_scale"].default == 1.0
    assert _minimal_request().voice_speed_scale == 1.0
    with pytest.raises(ValidationError):
        _minimal_request(voice_speed_scale=5.0)


def test_channel_scaled_speed_is_unchanged_at_scale_one():
    assert channel_scaled_speed(1.15, 1.0) == 1.15


def test_channel_scaled_speed_clamps_to_the_renderer_safe_bounds():
    assert channel_scaled_speed(1.15, 1.3) == pytest.approx(1.4)  # 1.495 clamped down to the ceiling
    assert channel_scaled_speed(0.85, 0.7) == pytest.approx(0.8)  # 0.595 clamped up to the floor
    assert channel_scaled_speed(1.15, 0.7) == pytest.approx(0.805)  # inside bounds: left unclamped
