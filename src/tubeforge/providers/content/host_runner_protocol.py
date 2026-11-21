"""Strict, path-free protocol for the isolated host Codex runner."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tubeforge.domain.contracts import ContentRequest
from tubeforge.domain.long_form_writing import LongFormHostRequest


CLIP_PROMPT_MAX_CHARS = 48_000  # keeps the whole request inside the runner's 64 KiB socket read


class GenerateShortsScriptRequest(BaseModel):
    """The sole worker-to-host operation; no prompt, path, or command fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: str = Field(default="GenerateShortsScriptV1", pattern=r"^(GenerateShortsScriptV1|PreflightContentV1|ResearchSourcesV1)$")
    request: ContentRequest


class ClipCompletionRequest(BaseModel):
    """One tool-less, bounded completion for clip selection.

    The runner answers it with the Claude CLI in print mode with no tools, no files and a fixed
    model; nothing here names a command, path or model. The prompt carries transcript text, so
    its size is bounded and the runner counts every call against the shared daily limit and a
    separate, lower clip limit.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: str = Field(default="CompleteClipPromptV1", pattern=r"^CompleteClipPromptV1$")
    system: str = Field(default="", max_length=20_000)
    prompt: str = Field(min_length=1, max_length=CLIP_PROMPT_MAX_CHARS)
    output_schema: dict[str, Any] | None = None


class HostRunnerFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^(timeout|unavailable|quota_exhausted|runner_unavailable|authentication_failed|allowance_exhausted|invalid_output|quality_rejected|source_mismatch|insufficient_sources)$")
    message: str = Field(max_length=1_000)
    invocation_started: bool = True


class HostRunnerSuccess(BaseModel):
    """The only successful host response: a package plus redacted evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    package: dict[str, Any]
    provenance: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)


class HostRunnerResponse(BaseModel):
    """Bounded envelope used on the Unix socket."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    result: HostRunnerSuccess | None = None
    failure: HostRunnerFailure | None = None


# Limits apply to UTF-8 wire bytes, independently of prompt character limits.
MAX_REQUEST_BYTES = 65_536
REQUEST_READ_SECONDS = 30.0


def encode_request(message: GenerateShortsScriptRequest | LongFormHostRequest) -> bytes:
    """Reject oversized evidence before transport or invocation reservation."""
    from tubeforge.core.errors import ProviderValidationError

    if isinstance(message,LongFormHostRequest):
        from tubeforge.long_form.wire import encode
        try:return encode(message)
        except ValueError as error:raise ProviderValidationError(str(error)) from error
    payload = message.model_dump_json().encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES:
        raise ProviderValidationError(
            f"Brief and source excerpts exceed the runner request limit "
            f"({len(payload)} > {MAX_REQUEST_BYTES} UTF-8 bytes); shorten the source packet."
        )
    return payload


def receive_message(connection, *, maximum_bytes: int = MAX_REQUEST_BYTES,
                    timeout_seconds: float = REQUEST_READ_SECONDS) -> GenerateShortsScriptRequest | LongFormHostRequest | ClipCompletionRequest:
    """Read fragmented JSON with bounded bytes/time, including legacy clients.

    New clients half-close their write side; older clients wait for a response
    without EOF, so a complete JSON value remains sufficient to end a request.
    Authorization stays with the runner and must happen before this function.
    """
    import json
    import time

    def decode(payload):
        value=json.loads(payload)
        if isinstance(value,dict) and value.get('operation')=='CompleteClipPromptV1':
            return ClipCompletionRequest.model_validate(value)
        if isinstance(value,dict) and value.get('operation') in {'PreflightLongFormV1','PrepareLongFormCallV1','LongFormStageV1','InspectLongFormCallV1'}:
            return LongFormHostRequest.model_validate(value)
        return GenerateShortsScriptRequest.model_validate(value)

    payload = bytearray()
    previous_timeout = connection.gettimeout()
    deadline = time.monotonic() + min(timeout_seconds, previous_timeout if previous_timeout is not None else timeout_seconds)
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("runner request read timed out before a complete message")
            connection.settimeout(remaining)
            try:
                chunk = connection.recv(min(8192, maximum_bytes + 1 - len(payload)))
            except TimeoutError as error:
                raise ValueError("runner request read timed out before a complete message") from error
            if not chunk:
                if not payload:
                    raise ValueError("request is missing or exceeds the runner limit")
                # Preserve strict domain validation and a bounded failure reply.
                return decode(bytes(payload))
            payload.extend(chunk)
            if len(payload) > maximum_bytes:
                raise ValueError("request is missing or exceeds the runner limit")
            try:
                json.loads(payload)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            return decode(bytes(payload))
    finally:
        connection.settimeout(previous_timeout)
