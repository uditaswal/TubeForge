"""Per-generation routing between local art and rights-safe stock media."""

from __future__ import annotations

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import AssetCandidate, MediaSearchRequest
from tubeforge.domain.providers import MediaProvider
from tubeforge.providers.media.wikimedia import WikimediaCommonsProvider


class VisualMediaProvider:
    """Keep the user-selected visual source durable and truthful.

    ``generated`` uses TubeForge's local scene-art generator. ``stock`` uses
    Wikimedia Commons only, where the adapter retains only public-domain/CC0
    candidates that can be used without an attribution overlay. Google Image
    results are deliberately not a source: a search result is not licensing
    evidence and would undermine the existing asset policy.
    """

    def __init__(self, generated: MediaProvider, stock: WikimediaCommonsProvider) -> None:
        self.generated, self.stock = generated, stock

    def search(self, request: MediaSearchRequest) -> list[AssetCandidate]:
        if request.visual_source == "generated":
            return self.generated.search(request)
        if request.visual_source == "stock":
            return self.stock.search(request)
        raise ProviderValidationError("unsupported visual source")

    def search_local_fallback(self, request: MediaSearchRequest) -> list[AssetCandidate]:
        """Return generated CC0 scene art only after stock selection finds none.

        The caller records this as a fallback rather than presenting it as a
        Wikimedia result.  This keeps the stock path rights-safe without
        leaving a generation permanently blocked by sparse Commons metadata.
        """
        if request.visual_source != "stock":
            raise ProviderValidationError("local fallback is only available for stock requests")
        return self.generated.search(request.model_copy(update={"visual_source": "generated"}))

    @staticmethod
    def provider_name(request: MediaSearchRequest) -> str:
        return "local-generated" if request.visual_source == "generated" else "wikimedia-commons"
