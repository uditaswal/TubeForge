"""Per-generation routing between local art and rights-safe stock media."""

from __future__ import annotations

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import AssetCandidate, MediaSearchRequest
from tubeforge.providers.fake import FakeMediaProvider
from tubeforge.providers.media.wikimedia import WikimediaCommonsProvider


class VisualMediaProvider:
    """Keep the user-selected visual source durable and truthful.

    ``generated`` uses TubeForge's local scene-art generator. ``stock`` uses
    Wikimedia Commons only, where the adapter retains only public-domain/CC0
    candidates that can be used without an attribution overlay. Google Image
    results are deliberately not a source: a search result is not licensing
    evidence and would undermine the existing asset policy.
    """

    def __init__(self, generated: FakeMediaProvider, stock: WikimediaCommonsProvider) -> None:
        self.generated, self.stock = generated, stock

    def search(self, request: MediaSearchRequest) -> list[AssetCandidate]:
        if request.visual_source == "generated":
            return self.generated.search(request)
        if request.visual_source == "stock":
            return self.stock.search(request)
        raise ProviderValidationError("unsupported visual source")

    @staticmethod
    def provider_name(request: MediaSearchRequest) -> str:
        return "local-generated" if request.visual_source == "generated" else "wikimedia-commons"
