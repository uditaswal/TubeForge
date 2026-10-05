"""Ollama content provider for local or remote open-source inference."""

from __future__ import annotations

import http.client
import json
import logging
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import urlsplit

from pydantic import ValidationError

from tubeforge.core.config import OllamaProviderConfig
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.db.repositories import CachedGeneration, GenerationCacheRepository
from tubeforge.domain.contracts import ClaimReviewStatus, ConfidenceLevel, ContentPackage, ContentRequest
from tubeforge.providers.content.prompts import build_content_prompt, validate_video_package


@dataclass(frozen=True, slots=True)
class OllamaResponse:
    status: int
    body: bytes


Transport = Callable[[str, bytes, int, int, int], OllamaResponse]
logger = logging.getLogger(__name__)


class OllamaContentProvider:
    """Generate and persist a production ContentPackage through Ollama's API."""

    provider_name = "ollama"

    def __init__(self, config: OllamaProviderConfig, cache: GenerationCacheRepository, *, transport: Transport | None = None, clock: Callable[[], datetime] | None = None) -> None:
        self.config, self.cache = config, cache
        self._transport = transport or _post_json
        self._clock = clock or (lambda: datetime.now(UTC))
        self.last_provenance: dict[str, object] | None = None
        self.last_usage: dict[str, object] | None = None

    def generate_package(self, request: ContentRequest) -> ContentPackage:
        now = self._now()
        reservation = self.cache.reserve_or_get(request, self.provider_name, self.config.model, request.prompt_version, now=now, reservation_seconds=self.config.reservation_seconds)
        if isinstance(reservation, CachedGeneration):
            package = self._validate(reservation.package, request)
            self.last_provenance, self.last_usage = reservation.provenance, reservation.usage
            return package
        if reservation is None:
            raise RetryableProviderError("Ollama generation is already reserved; retry after the reservation expires")
        try:
            prompt = build_content_prompt(request, template_version=self.config.prompt_template_version, max_chars=self.config.max_prompt_chars)
            usage: dict[str, object] = {}
            package: ContentPackage | None = None
            validation_error: ProviderValidationError | None = None
            for validation_attempt in range(self.config.validation_retries + 1):
                retry_prompt = prompt
                if validation_error is not None:
                    retry_prompt += (
                        "\nThe previous JSON was rejected by a local safety/quality validator: "
                        + str(validation_error)[:1_000]
                        + ". Regenerate the complete ContentPackage JSON and correct that issue without weakening source grounding."
                    )
                raw, attempt_usage = self._invoke(retry_prompt, request=request)
                usage = {**attempt_usage, "validation_attempts": validation_attempt + 1}
                try:
                    package = self._validate(raw, request)
                    break
                except ProviderValidationError as error:
                    validation_error = error
                    logger.warning("Ollama draft rejected by local validator (attempt %s): %s", validation_attempt + 1, error)
            if package is None:
                assert validation_error is not None
                raise validation_error
            provenance: dict[str, object] = {"cache_key": reservation.cache_key, "generated_at": self._now().isoformat(), "model": self.config.model, "provider": self.provider_name, "base_url": self.config.base_url, "prompt_template_version": self.config.prompt_template_version, "validation_attempts": usage["validation_attempts"]}
            if not self.cache.accept(reservation, package.model_dump(mode="json"), provenance, usage, now=self._now()):
                raise RetryableProviderError("Ollama generation reservation expired before validated result could be accepted")
        except Exception:
            self.cache.abandon(reservation)
            raise
        self.last_provenance, self.last_usage = provenance, usage
        return package

    def _invoke(self, prompt: str, *, request: ContentRequest | None = None) -> tuple[Any, dict[str, object]]:
        schema = ContentPackage.model_json_schema()
        if request is not None and request.aspect_ratio == "9:16":
            # Ollama uses this schema as a decoding grammar. Small local models
            # can acknowledge a prose word budget yet still emit terse fields;
            # structural bounds ensure six meaningfully developed narration
            # sections reach the unchanged local duration gate.
            sections = schema.get("properties", {}).get("script_sections")
            if isinstance(sections, dict):
                sections["minItems"] = 6
                sections["maxItems"] = 6
            plans = schema.get("properties", {}).get("scene_plans")
            if isinstance(plans, dict):
                plans["minItems"] = 6
                plans["maxItems"] = 6
            script_definition = schema.get("$defs", {}).get("ScriptSection")
            if isinstance(script_definition, dict):
                narration = script_definition.get("properties", {}).get("narration")
                if isinstance(narration, dict):
                    narration["minLength"] = 105
                    narration["maxLength"] = 260
        payload = json.dumps({"model": self.config.model, "prompt": prompt, "stream": False, "format": schema}, separators=(",", ":")).encode()
        response: OllamaResponse | None = None
        for attempt in range(self.config.retries + 1):
            try:
                response = self._transport(self.config.base_url, payload, self.config.connection_timeout_seconds, self.config.inference_timeout_seconds, self.config.max_response_bytes)
            except (OSError, TimeoutError) as error:
                if attempt >= self.config.retries:
                    raise RetryableProviderError("Ollama endpoint could not be reached before the configured timeout") from error
                continue
            if response.status >= 500 and attempt < self.config.retries:
                continue
            break
        assert response is not None
        if response.status in {401, 403}:
            raise ProviderAuthenticationError("Ollama endpoint rejected authentication")
        if response.status == 429 or response.status >= 500:
            raise RetryableProviderError(f"Ollama endpoint returned transient HTTP {response.status}")
        if not 200 <= response.status < 300:
            raise ProviderValidationError(f"Ollama endpoint returned HTTP {response.status}")
        try:
            envelope = json.loads(response.body)
            if not isinstance(envelope, dict) or envelope.get("done") is not True:
                raise ProviderValidationError("Ollama response did not report a completed generation")
            content = envelope["response"]
            raw = json.loads(content) if isinstance(content, str) else content
        except ProviderValidationError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise ProviderValidationError("Ollama response did not contain valid structured JSON") from error
        usage = {key: envelope[key] for key in ("prompt_eval_count", "eval_count", "total_duration") if key in envelope}
        return raw, usage

    def _validate(self, raw: Any, request: ContentRequest) -> ContentPackage:
        if not isinstance(raw, dict):
            raise ProviderValidationError("Ollama output failed ContentPackage validation")
        # The request and source packet are authority-bearing inputs, not model
        # output. Local models frequently normalize or paraphrase echoed fields;
        # replace that copy with the immutable original before schema/reference
        # validation so the model can neither alter nor invent provenance.
        authoritative = {**raw, "request": request.model_dump(mode="json")}
        claims = raw.get("claims")
        sections = raw.get("script_sections")
        claim_ids = [str(value.get("claim_id")) for value in claims if isinstance(value, dict) and value.get("claim_id")] if isinstance(claims, list) else []
        if claim_ids and isinstance(sections, list):
            # Some small structured-output models correctly create cited
            # claims but omit the redundant section->claim edge. Binding a
            # factual section to every generated claim is conservative and
            # reviewable; ContentPackage still rejects any claim whose source
            # ID is absent from the immutable request packet.
            authoritative["script_sections"] = [
                {**value, "claim_ids": claim_ids}
                if isinstance(value, dict) and value.get("contains_factual_claims") is True and not value.get("claim_ids")
                else value
                for value in sections
            ]
        try:
            package = ContentPackage.model_validate(authoritative)
        except ValidationError as error:
            issue = error.errors(include_input=False)[0]
            field = ".".join(str(part) for part in issue.get("loc", ())) or "root"
            message = str(issue.get("msg", "invalid value"))
            raise ProviderValidationError(f"Ollama output failed ContentPackage validation at {field}: {message}") from error
        validate_video_package(package, request, provider_name="Ollama")
        claims = tuple(claim.model_copy(update={"review_status": ClaimReviewStatus.NEEDS_REVIEW, "human_review_required": True}) if claim.time_sensitive or claim.confidence in {ConfidenceLevel.LOW, ConfidenceLevel.MEDIUM} else claim for claim in package.claims)
        return package.model_copy(update={"claims": claims})

    def _now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo else value.replace(tzinfo=UTC)


def _post_json(base_url: str, payload: bytes, connection_timeout: int, inference_timeout: int, max_bytes: int) -> OllamaResponse:
    parsed = urlsplit(base_url)
    connection_type = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    connection = connection_type(parsed.hostname, parsed.port, timeout=connection_timeout)
    path = (parsed.path.rstrip("/") if parsed.path else "") + "/api/generate"
    try:
        connection.request("POST", path, body=payload, headers={"Content-Type": "application/json", "Accept": "application/json"})
        if connection.sock is not None:
            connection.sock.settimeout(inference_timeout)
        response = connection.getresponse()
        body = response.read(max_bytes + 1)
        if len(body) > max_bytes:
            raise ProviderValidationError("Ollama response exceeded configured response limit")
        return OllamaResponse(response.status, body)
    except socket.timeout as error:
        raise TimeoutError from error
    finally:
        connection.close()
