"""Select configured Kokoro voices while preserving Piper as the safe fallback."""

from __future__ import annotations

from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import VoiceRequest, VoiceResult
from tubeforge.providers.voice.kokoro import KokoroVoiceProvider
from tubeforge.providers.voice.piper import PiperVoiceProvider


class HybridVoiceProvider:
    provider_name = "kokoro-with-piper-fallback"

    def __init__(self, kokoro: KokoroVoiceProvider, piper: PiperVoiceProvider) -> None:
        self.kokoro, self.piper = kokoro, piper
        self.settings = piper.settings

    def synthesize(self, request: VoiceRequest) -> VoiceResult:
        if request.voice_id in self.kokoro.settings.voices and self.kokoro.settings.enabled:
            try:
                return self.kokoro.synthesize(request)
            except (ProviderValidationError, RetryableProviderError):
                # The requested voice is unavailable; render reliably with the
                # installed Piper model instead of failing a durable job.
                return self.piper.synthesize(request.model_copy(update={"voice_id": self.piper.settings.voice_id}))
        return self.piper.synthesize(request.model_copy(update={"voice_id": self.piper.settings.voice_id}))
