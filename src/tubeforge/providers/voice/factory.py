"""Configuration-only voice provider selection."""

from tubeforge.core.config import Settings
from tubeforge.domain.providers import VoiceProvider
from tubeforge.providers.fake import FakeVoiceProvider
from tubeforge.providers.voice.piper import PiperVoiceProvider


def create_voice_provider(settings: Settings) -> VoiceProvider:
    """Fake stays the safe default; Piper is only constructed after selection."""
    if settings.pipeline.provider == "piper":
        return PiperVoiceProvider(settings.pipeline.piper)
    return FakeVoiceProvider(settings.pipeline.fake)
