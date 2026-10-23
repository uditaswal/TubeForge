"""Configuration-only voice provider selection."""

from tubeforge.core.config import Settings
from tubeforge.domain.providers import VoiceProvider
from tubeforge.providers.fake import FakeVoiceProvider
from tubeforge.providers.voice.piper import PiperVoiceProvider
from tubeforge.providers.voice.piper_http import PiperHttpVoiceProvider
from tubeforge.providers.voice.kokoro import KokoroVoiceProvider
from tubeforge.providers.voice.hybrid import HybridVoiceProvider


def create_voice_provider(settings: Settings) -> VoiceProvider:
    """Fake stays the safe default; Piper is only constructed after selection."""
    if settings.pipeline.voice_provider == "piper":
        return PiperVoiceProvider(settings.pipeline.piper)
    if settings.pipeline.voice_provider == "piper-http":
        return PiperHttpVoiceProvider(settings.pipeline.piper)
    if settings.pipeline.voice_provider == "kokoro":
        return KokoroVoiceProvider(settings.pipeline.kokoro)
    if settings.pipeline.voice_provider == "hybrid":
        return HybridVoiceProvider(KokoroVoiceProvider(settings.pipeline.kokoro), PiperVoiceProvider(settings.pipeline.piper))
    if settings.pipeline.voice_provider == "hybrid-http":
        return HybridVoiceProvider(KokoroVoiceProvider(settings.pipeline.kokoro), PiperHttpVoiceProvider(settings.pipeline.piper))
    return FakeVoiceProvider(settings.pipeline.fake)
