"""Worker-side client for the sole typed TubeForge host Codex operation."""

from __future__ import annotations

import socket
from datetime import UTC, datetime
from typing import Callable

from tubeforge.core.config import CodexProviderConfig
from tubeforge.core.errors import InsufficientSourcesError, ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.db.repositories import CachedGeneration, GenerationCacheRepository, GenerationExhausted
from tubeforge.domain.contracts import ClaimReviewStatus, ConfidenceLevel, ContentPackage, ContentRequest, generation_request_content
from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest, HostRunnerResponse
from tubeforge.providers.content.prompts import build_content_prompt, normalize_content_request, validate_video_package


Transport = Callable[[str, bytes, int], bytes]


class HostRunnerContentProvider:
    provider_name = "host-codex-runner"
    script_owner = "codex"

    def __init__(self, config: CodexProviderConfig, cache: GenerationCacheRepository, *, transport: Transport | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self.config, self.cache = config, cache
        self._transport = transport or _request
        self._clock = clock or (lambda: datetime.now(UTC))
        self.last_provenance: dict[str, object] | None = None
        self.last_usage: dict[str, object] | None = None

    def research_sources(self, request: ContentRequest) -> dict:
        """Typed research operation; no narration cache or approval mutation."""
        self._require_owner(request)
        def call(operation):
            message = GenerateShortsScriptRequest(operation=operation, request=generation_request_content(request))
            response = HostRunnerResponse.model_validate_json(self._transport(str(self.config.socket_path), message.model_dump_json().encode(), self.config.socket_timeout_seconds))
            if not response.ok or response.result is None:
                raise ProviderValidationError(response.failure.message if response.failure else "research runner returned no result")
            return response.result
        readiness = call("PreflightContentV1")
        if "ResearchSourcesV1" not in readiness.provenance.get("operations", []):
            raise ProviderValidationError("Host runner needs the research update installed before topic research can run")
        return call("ResearchSourcesV1").model_dump(mode="json")

    def _require_owner(self, request: ContentRequest) -> None:
        if request.script_owner != self.script_owner:
            raise ProviderValidationError(f"this job's script owner is {request.script_owner!r}, which is not enabled here")

    def generate_package(self, request: ContentRequest) -> ContentPackage:
        self._require_owner(request)
        # Reject an unsupported prompt before reserving or charging a model call.
        try:
            prompt = build_content_prompt(request, template_version=request.prompt_version, max_chars=self.config.max_prompt_chars)
        except ValueError as error:  # an oversized request is a brief problem, not a transient failure to retry
            if "max_prompt_chars" not in str(error):
                raise
            raise ProviderValidationError(f"the brief and source excerpts are too large for one script prompt: {error}") from error
        host_request = generation_request_content(request)
        from tubeforge.providers.content.youtube_skills import SKILL_TEMPLATE, SKILL_TEMPLATES, preflight
        from tubeforge.providers.content.prompts import CONTENT_ENVELOPE_TEMPLATES
        if request.prompt_version in SKILL_TEMPLATES:
            hashes = preflight(template_version=request.prompt_version)
            try:
                readiness = HostRunnerResponse.model_validate_json(self._transport(str(self.config.socket_path), GenerateShortsScriptRequest(operation="PreflightContentV1", request=host_request).model_dump_json().encode(), self.config.socket_timeout_seconds))
            except OSError as error:
                # The runner socket is down or restarting (connection refused, missing socket, timeout): wait and retry, don't fail the job.
                raise RetryableProviderError(f"Script runner is not reachable ({error}); retrying automatically") from error
            except Exception as error:
                raise ProviderValidationError(f"Host skill preflight failed before invocation: {error}") from error
            if not readiness.ok or readiness.result is None or readiness.result.provenance.get("resource_hashes") != hashes:
                reason = readiness.failure.message if readiness.failure else "host skill resources differ from worker; redeploy host wheel"
                raise ProviderValidationError(f"Host skill preflight failed before invocation: {reason}")
            if request.prompt_version == SKILL_TEMPLATE:
                from tubeforge.providers.content.prompts import prompt_evidence
                if readiness.result.provenance.get("prompt_sha256") != prompt_evidence(prompt)["prompt_sha256"]:
                    raise ProviderValidationError("Host skill preflight failed before invocation: assembled prompt differs; redeploy host wheel")
            if request.prompt_version in CONTENT_ENVELOPE_TEMPLATES:
                from tubeforge.providers.content.output import require_source_excerpts
                require_source_excerpts(request)
        now = self._now()
        cached = self.cache.reserve_or_get(request, self.provider_name, self.config.model, request.prompt_version, now=now, reservation_seconds=self.config.reservation_seconds)
        if isinstance(cached, CachedGeneration):
            if request.prompt_version in SKILL_TEMPLATES and cached.provenance.get("youtube_skills", {}).get("resource_hashes") != hashes:
                raise ProviderValidationError("Cached generation uses different skill resources; operator must review a new prompt version")
            package = self._validate(cached.package, request)
            self.last_provenance, self.last_usage = cached.provenance, cached.usage
            return package
        if isinstance(cached, GenerationExhausted):
            raise ProviderValidationError("TubeForge's two-attempt limit for this exact source packet is exhausted; operator review is required")
        if cached is None:
            raise RetryableProviderError("Codex generation is already reserved; retry after the reservation expires")
        if not self.cache.consume_invocation(cached, maximum=self.config.invocation_limit, now=now):
            raise ProviderValidationError("TubeForge's two-attempt limit for this exact source packet is exhausted; operator review is required")
        response = None
        try:
            response = HostRunnerResponse.model_validate_json(self._transport(str(self.config.socket_path), GenerateShortsScriptRequest(request=host_request).model_dump_json().encode(), self.config.socket_timeout_seconds))
            if not response.ok or response.failure:
                failure = response.failure
                code = failure.code if failure else "invalid_output"
                message = failure.message if failure else "host runner returned an invalid response"
                if code == "insufficient_sources":
                    raise InsufficientSourcesError(message)
                if code == "timeout":
                    raise RetryableProviderError(message)
                if code == "unavailable":
                    raise ProviderAuthenticationError(message)
                raise ProviderValidationError(message)
            if response.result is None:
                raise ProviderValidationError("host runner omitted its result")
            package = self._validate(response.result.package, request)
            provenance = dict(response.result.provenance)
            provenance.update({"cache_key": cached.cache_key, "provider": self.provider_name, "prompt_version": request.prompt_version})
            usage = dict(response.result.usage)
            if not self.cache.accept(cached, package.model_dump(mode="json"), provenance, usage, now=self._now()):
                raise RetryableProviderError("Codex generation reservation expired before acceptance")
        except Exception as error:
            failure = {"type": type(error).__name__, "message": str(error)[:1000]}
            if response is not None and response.result is not None:
                # Retain the rejected draft for operator review without accepting it
                # or changing the durable invocation allowance.
                failure["rejected_result"] = response.result.model_dump(mode="json")
            self.cache.release_after_invocation_failure(cached, maximum=self.config.invocation_limit, failure=failure, now=self._now())
            raise
        self.last_provenance, self.last_usage = provenance, usage
        return package

    def _validate(self, raw: object, request: ContentRequest) -> ContentPackage:
        package = ContentPackage.model_validate(raw)
        if normalize_content_request(package.request) != normalize_content_request(request):
            raise ProviderValidationError("host runner output source packet differs from the requested source packet")
        validate_video_package(package, request, provider_name=self.script_owner.title())
        from tubeforge.providers.content.youtube_skills import SKILL_TEMPLATES, evaluate
        if request.prompt_version in SKILL_TEMPLATES:
            evaluate(package)
        claims = tuple(claim.model_copy(update={"review_status": ClaimReviewStatus.NEEDS_REVIEW, "human_review_required": True}) if claim.time_sensitive or claim.confidence in {ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM} else claim for claim in package.claims)
        return package.model_copy(update={"claims": claims})

    def _now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo else value.replace(tzinfo=UTC)


def _request(path: str, payload: bytes, timeout: int) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(timeout)
        connection.connect(path)
        connection.sendall(payload)
        chunks: list[bytes] = []
        total = 0
        while chunk := connection.recv(65_536):
            total += len(chunk)
            if total > 4_000_000:
                raise ProviderValidationError("host runner response exceeded the worker limit")
            chunks.append(chunk)
        if not chunks:
            raise RetryableProviderError("host runner closed without a response")
        return b"".join(chunks)
