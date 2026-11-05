"""Configuration-only provider selection at the application boundary."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from tubeforge.core.config import Settings
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError, ProviderAuthenticationError, ProviderCancellation
from tubeforge.db.repositories import GenerationCacheRepository, CachedGeneration, GenerationExhausted
from tubeforge.domain.contracts import ContentPackage, ContentRequest, ScriptRoutingEvidence
from tubeforge.domain.providers import ContentProvider
from tubeforge.providers.content.host_runner import HostRunnerContentProvider
from tubeforge.providers.content.routing_errors import RunnerFallbackFailure
from tubeforge.providers.fake import FakeContentProvider, FixedScriptContentProvider


class ClaudeHostRunnerContentProvider(HostRunnerContentProvider):
    """Same worker-side client and acceptance rules; a different host runner."""

    provider_name = "host-claude-runner"
    script_owner = "claude"


class ScriptOwnerRouter:
    """Durable one-shot routing; writers retain their validation and cache gates."""

    def __init__(self, providers: dict[str, ContentProvider], cache=None) -> None:
        self.providers, self.cache = providers, cache
        self._last = None
        self._provenance = self._usage = None

    @staticmethod
    def _owner(request):
        return {"claude_only": "claude", "codex_only": "codex"}.get(request.script_routing_mode, request.script_owner)

    def _for(self, request):
        owner = self._owner(request)
        try:
            provider = self.providers[owner]
        except KeyError:
            raise ProviderValidationError(f"script owner {owner!r} is not enabled in this TubeForge configuration") from None
        self._last = provider
        return provider

    @staticmethod
    def _request(request, owner):
        return request.model_copy(update={"script_owner": owner, "script_routing_mode": None,
                                          "script_model": request.script_model if owner == "claude" else None})

    @staticmethod
    def _cause(owner, error):
        # Only structured categories leave the boundary; runner text can contain credentials.
        code = getattr(error, "code", None) or ("authentication_failed" if isinstance(error, ProviderAuthenticationError)
                    else "cancelled" if isinstance(error, ProviderCancellation)
                    else "transient_failure" if isinstance(error, RetryableProviderError) else "validation_failed")
        return {"owner": owner, "code": code, "invocation_started": getattr(error, "invocation_started", None),
                "usage": getattr(error, "usage", {})}

    def generate_package(self, request):
        self._provenance = self._usage = None
        if request.script_routing_mode is None:
            return self._for(request).generate_package(request)
        preferred = self._owner(request)
        self._for(request)  # Disabled primaries fail closed.
        model = f"routing-v1/{request.script_routing_mode}/{preferred}"
        reservation = None
        if self.cache:
            seconds = sum(getattr(getattr(p, "config", None), "reservation_seconds", 1200) for p in self.providers.values())
            reservation = self.cache.reserve_or_get(request, "script-owner-router", model, request.prompt_version,
                now=datetime.now(UTC), reservation_seconds=seconds)
            if isinstance(reservation, CachedGeneration):
                value = ContentPackage.model_validate(reservation.package)
                owner = value.script_routing.actual_owner
                if owner not in self.providers:
                    raise ProviderValidationError("cached script provider is disabled; review routing policy")
                provider = self.providers[owner]
                cached_reader = getattr(provider, "cached_package", None)
                if cached_reader:
                    accepted = cached_reader(self._request(request, owner))
                    if accepted is None:
                        raise ProviderValidationError("accepted writer cache is unavailable; operator review required")
                self._last, self._provenance, self._usage = provider, reservation.provenance, reservation.usage
                return value.model_copy(update={"request": request})
            if isinstance(reservation, GenerationExhausted):
                failure = self.cache.failure(reservation.cache_key)
                raise ProviderValidationError(failure.get("message", "automatic fallback already failed; operator review required"))
            if reservation is None:
                raise RetryableProviderError("script routing is already reserved; retry after its lease expires")
        attempts = []
        fallback_attempted = False
        try:
            owner = preferred
            provider = self.providers[owner]
            try:
                package = provider.generate_package(self._request(request, owner))
            except RunnerFallbackFailure as primary_error:
                attempts.append(self._cause(owner, primary_error))
                if request.script_routing_mode != "automatic":
                    raise
                owner = "codex" if preferred == "claude" else "claude"
                if owner not in self.providers:
                    raise ProviderValidationError("fallback provider is disabled") from primary_error
                fallback_attempted = True
                provider = self.providers[owner]
                try:
                    package = provider.generate_package(self._request(request, owner))
                except Exception as fallback_error:
                    attempts.append(self._cause(owner, fallback_error))
                    # Cancellation remains cancellation; never convert it into acceptance/retry.
                    if isinstance(fallback_error, ProviderCancellation):
                        raise
                    raise ProviderValidationError("Automatic fallback failed: " + "; ".join(f"{a['owner']}: {a['code']}" for a in attempts)) from fallback_error
            self._last = provider
            usage = dict(getattr(provider, "last_usage", None) or {})
            attempts.append({"owner": owner, "code": "accepted", "usage": usage})
            self._usage = {**usage, "usage_scope": "successful_provider_only", "routing_attempts": attempts,
                           "usage_complete": all(a["code"] == "accepted" or a.get("invocation_started") is False or bool(a.get("usage")) for a in attempts)}
            evidence = ScriptRoutingEvidence(mode=request.script_routing_mode, preferred_owner=preferred, actual_owner=owner,
                provider=getattr(provider, "provider_name", owner), attempts=tuple(attempts), usage=self._usage)
            package = package.model_copy(update={"request": request, "script_routing": evidence})
            self._provenance = {**(getattr(provider, "last_provenance", None) or {}), "script_routing": evidence.model_dump(mode="json")}
            if self.cache and not self.cache.accept(reservation, package.model_dump(mode="json"), self._provenance, self._usage, now=datetime.now(UTC)):
                raise RetryableProviderError("routing reservation expired before acceptance")
            return package
        except Exception as error:
            if self.cache:
                # A failed fallback is terminal for this policy/source packet. Never cycle on restart.
                self.cache.release_after_invocation_failure(reservation, maximum=0 if fallback_attempted else 2,
                    failure={"message": "Automatic fallback failed: " + "; ".join(f"{a['owner']}: {a['code']}" for a in attempts) if fallback_attempted else "primary writer failed", "attempts": attempts}, now=datetime.now(UTC))
            raise

    def research_sources(self, request):
        # Research is once per exact brief, on the preferred owner only. Never replay it on fallback.
        provider = self._for(request)
        researcher = getattr(provider, "research_sources", None)
        if researcher is None:
            raise ProviderValidationError("selected script owner cannot research topics")
        return researcher(self._request(request, self._owner(request)))

    @property
    def last_provenance(self):
        return self._provenance if self._provenance is not None else getattr(self._last, "last_provenance", None)

    @property
    def last_usage(self):
        return self._usage if self._usage is not None else getattr(self._last, "last_usage", None)


def create_content_provider(settings: Settings, session_factory: sessionmaker[Session]) -> ContentProvider:
    """Return fake content by default; create Codex only after explicit selection."""
    if settings.pipeline.content_provider == "fake":
        return FakeContentProvider()
    if settings.pipeline.content_provider == "fixed":
        return FixedScriptContentProvider()
    cache = GenerationCacheRepository(session_factory)
    codex = HostRunnerContentProvider(settings.pipeline.codex, cache)
    providers = {"codex": codex}
    if settings.pipeline.claude.enabled:
        providers["claude"] = ClaudeHostRunnerContentProvider(settings.pipeline.claude, cache)
    return ScriptOwnerRouter(providers, cache)
