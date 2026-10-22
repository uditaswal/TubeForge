"""Configuration-only provider selection at the application boundary."""

from sqlalchemy.orm import Session, sessionmaker

from tubeforge.core.config import Settings
from tubeforge.core.errors import ProviderValidationError
from tubeforge.db.repositories import GenerationCacheRepository
from tubeforge.domain.contracts import ContentPackage, ContentRequest
from tubeforge.domain.providers import ContentProvider
from tubeforge.providers.content.host_runner import HostRunnerContentProvider
from tubeforge.providers.fake import FakeContentProvider, FixedScriptContentProvider


class ClaudeHostRunnerContentProvider(HostRunnerContentProvider):
    """Same worker-side client and acceptance rules; a different host runner."""

    provider_name = "host-claude-runner"
    script_owner = "claude"


class ScriptOwnerRouter:
    """Send each job to the script owner it selected (Codex by default).

    Evidence attributes mirror the delegate that handled the last call so the
    orchestrator records the correct provenance without knowing about routing.
    """

    def __init__(self, providers: dict[str, ContentProvider]) -> None:
        self.providers = providers
        self._last: ContentProvider | None = None

    def _for(self, request: ContentRequest) -> ContentProvider:
        try:
            provider = self.providers[request.script_owner]
        except KeyError:
            raise ProviderValidationError(
                f"script owner {request.script_owner!r} is not enabled in this TubeForge configuration") from None
        self._last = provider
        return provider

    def generate_package(self, request: ContentRequest) -> ContentPackage:
        return self._for(request).generate_package(request)

    def research_sources(self, request: ContentRequest) -> dict:
        provider = self._for(request)
        researcher = getattr(provider, "research_sources", None)
        if researcher is None:
            raise ProviderValidationError("selected script owner cannot research topics")
        return researcher(request)

    @property
    def last_provenance(self):
        return getattr(self._last, "last_provenance", None)

    @property
    def last_usage(self):
        return getattr(self._last, "last_usage", None)


def create_content_provider(settings: Settings, session_factory: sessionmaker[Session]) -> ContentProvider:
    """Return fake content by default; create Codex only after explicit selection."""
    if settings.pipeline.content_provider == "fake":
        return FakeContentProvider()
    if settings.pipeline.content_provider == "fixed":
        return FixedScriptContentProvider()
    cache = GenerationCacheRepository(session_factory)
    codex = HostRunnerContentProvider(settings.pipeline.codex, cache)
    if not settings.pipeline.claude.enabled:
        return codex
    return ScriptOwnerRouter({"codex": codex, "claude": ClaudeHostRunnerContentProvider(settings.pipeline.claude, cache)})
