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


def unwrap_generation(raw: object, *, request: ContentRequest | None = None) -> dict:
    # The writer owns narration/claims/scenes, not the immutable input packet.
    # Compatibility: validate any legacy echo instead of silently overwriting it.
    if request is not None and isinstance(raw, dict) and isinstance(raw.get("package"), dict):
        package = dict(raw["package"])
        if "request" in package:
            from tubeforge.providers.content.prompts import normalize_content_request
            echoed = ContentRequest.model_validate(package["request"])
            if normalize_content_request(echoed) != normalize_content_request(request):
                from tubeforge.core.errors import ProviderValidationError
                raise ProviderValidationError("Generated request echo differs from the trusted request")
        package["request"] = request.model_dump(mode="json")
        if request.prompt_version == "m6-content-v8":
            package = bind_reference_output(package, request)
        raw = {**raw, "package": package}
    result = ContentGenerationResult.model_validate(raw)
    if result.status == "insufficient_sources":
        raise InsufficientSourcesError(result.reason or "Missing source support")
    assert result.package is not None
    return result.package.model_dump(mode="json")


def bind_reference_output(package: dict, request: ContentRequest) -> dict:
    """Bind narration and trusted attribution; never invent scene content."""
    from tubeforge.core.errors import ProviderValidationError
    topic = package.get("reference_short")
    sections = package.get("script_sections")
    if not isinstance(topic, dict) or not isinstance(sections, list):
        raise ProviderValidationError("reference output requires scenes and canonical script sections")
    scenes = topic.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != len(sections):
        raise ProviderValidationError("reference scene count differs from narration")
    bound = []
    for scene, section in zip(scenes, sections, strict=True):
        if not isinstance(scene, dict) or not isinstance(section, dict) or scene.get("scene_id") != section.get("scene_id"):
            raise ProviderValidationError("reference scenes are not in narration order")
        if "vo" in scene and scene["vo"] != section.get("narration"):
            raise ProviderValidationError("reference speech echo conflicts with canonical narration")
        bound.append({**scene, "vo": section["narration"]})
    sources = [{"source_id": s.source_id, "name": (s.author or s.title)[:42], "url": str(s.url)} for s in request.sources]
    if "sources" in topic and topic["sources"] != sources:
        raise ProviderValidationError("reference source echo conflicts with trusted request")
    metadata = package.get("metadata", {})
    title = metadata.get("title_options", [request.topic])[0]
    topic = {**topic, "scenes": bound, "sources": sources, "title": title}
    # The legacy review UI still consumes scene_plans. This projection carries
    # exact display strings; the new renderer consumes only reference_short.
    plans = []
    for scene in bound:
        template = scene.get("template", "")
        heading = scene.get("heading") or scene.get("headline") or ""
        if isinstance(heading, (list, tuple)):
            heading = " / ".join(heading)
        elements = scene.get("nodes") or scene.get("items") or scene.get("chips") or []
        plans.append({"scene_id": scene["scene_id"], "visual_type": "reference_short",
                      "search_queries": [request.topic], "on_screen_text": heading,
                      "fallback_visual": "Reference template; fail closed on invalid geometry",
                      "visual_subject": heading or template, "visual_purpose": scene["vo"],
                      "composition": template, "visual_elements": elements})
    if "scene_plans" in package and package["scene_plans"] != plans:
        raise ProviderValidationError("legacy scene echo conflicts with reference projection")
    return {**package, "reference_short": topic, "scene_plans": plans}


def require_source_excerpts(request: ContentRequest) -> None:
    if not any(source.excerpt and source.excerpt.strip() for source in request.sources):
        raise InsufficientSourcesError("Provide approved source excerpts supporting this brief before generating narration.")
