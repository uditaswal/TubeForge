"""Provider factory; real network adapters are opt-in through configuration."""
from tubeforge.core.config import MediaPipelineConfig, FakeProviderConfig
from tubeforge.domain.providers import MediaProvider
from tubeforge.providers.fake import FakeMediaProvider
from tubeforge.providers.media.wikimedia import WikimediaCommonsProvider
from tubeforge.providers.media.router import VisualMediaProvider


def create_media_provider(config: MediaPipelineConfig, fake: FakeProviderConfig) -> MediaProvider:
    if config.provider == "fake":
        return FakeMediaProvider(fake)
    if config.provider == "wikimedia":
        return WikimediaCommonsProvider(config)
    if config.provider == "hybrid":
        return VisualMediaProvider(FakeMediaProvider(fake), WikimediaCommonsProvider(config))
    raise ValueError(f"unsupported media provider: {config.provider}")
