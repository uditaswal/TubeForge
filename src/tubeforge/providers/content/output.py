"""Strict generation envelope; failures never enter the narration pipeline."""
from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from tubeforge.core.errors import InsufficientSourcesError
from tubeforge.domain.contracts import ContentPackage, ContentRequest, DomainModel


class ContentGenerationResult(DomainModel):
    status: Literal["ready", "insufficient_sources"]
    package: ContentPackage | None
    reason: str | None = Field(max_length=1000)

    @model_validator(mode="after")
    def require_consistent_result(self) -> ContentGenerationResult:
        if self.status == "ready":
            if self.package is None or self.reason is not None:
                raise ValueError("ready result requires a package and null reason")
        elif self.package is not None or not self.reason or not self.reason.strip():
            raise ValueError("insufficient_sources requires null package and a concrete reason")
        return self


def unwrap_generation(raw: object) -> dict:
    result = ContentGenerationResult.model_validate(raw)
    if result.status == "insufficient_sources":
        raise InsufficientSourcesError(result.reason or "Missing source support")
    assert result.package is not None
    return result.package.model_dump(mode="json")


def require_source_excerpts(request: ContentRequest) -> None:
    if not any(source.excerpt and source.excerpt.strip() for source in request.sources):
        raise InsufficientSourcesError("Provide approved source excerpts supporting this brief before generating narration.")
