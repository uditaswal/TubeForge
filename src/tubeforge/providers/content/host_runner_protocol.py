"""Strict, path-free protocol for the isolated host Codex runner."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from tubeforge.domain.contracts import ContentRequest


class GenerateShortsScriptRequest(BaseModel):
    """The sole worker-to-host operation; no prompt, path, or command fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: str = Field(default="GenerateShortsScriptV1", pattern=r"^(GenerateShortsScriptV1|PreflightContentV1|ResearchSourcesV1)$")
    request: ContentRequest


class HostRunnerFailure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(pattern=r"^(timeout|unavailable|allowance_exhausted|invalid_output|quality_rejected|source_mismatch|insufficient_sources)$")
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
