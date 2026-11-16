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


REFERENCE_OUTPUT_CONTRACT_VERSION = "reference-output-v2"
MAX_WHISPERS_PER_VIDEO = 2


def split_delivery_cues(narration: str) -> tuple[str, list[dict]]:
    """Clean narration plus bound cue dicts; malformed cues degrade to plain speech, never a rejection."""
    import re
    from tubeforge.rendering.shorts.cues import has_cues, parse
    if not isinstance(narration, str) or not has_cues(narration):
        return narration, []
    try:
        clean, cues = parse(narration)
    except ValueError:
        stripped = re.sub(r"\[(?:pause(?:\s+[0-9.]+)?|breath|whisper|/whisper)\]", " ", narration, flags=re.I)
        stripped = re.sub(r"(?<!\w)\*+|\*+(?!\w)", "", stripped)
        return " ".join(stripped.split()), []
    return clean, [cue.model_dump(exclude_none=True) for cue in cues]


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
    claims = package.get("claims", [])
    if not isinstance(claims, list):
        raise ProviderValidationError("reference output requires cited claims")
    claim_sources = {}
    trusted_sources = {source.source_id for source in request.sources}
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("claim_id"), str) or not isinstance(claim.get("source_ids"), (list, tuple)):
            raise ProviderValidationError("reference claims require explicit source identities")
        claim_id = claim["claim_id"]
        source_ids = claim["source_ids"]
        if claim_id in claim_sources or any(not isinstance(source, str) or source not in trusted_sources for source in source_ids):
            raise ProviderValidationError("reference claims contain duplicate or unknown source identities")
        claim_sources[claim_id] = set(source_ids)
    sections = list(sections)
    bound = []
    for index, (scene, section) in enumerate(zip(scenes, sections, strict=True)):
        if not isinstance(scene, dict) or not isinstance(section, dict) or scene.get("scene_id") != section.get("scene_id"):
            raise ProviderValidationError("reference scenes are not in narration order")
        clean, cue_list = split_delivery_cues(section.get("narration", ""))
        if "vo" in scene:
            if scene["vo"] not in (section.get("narration"), clean):
                raise ProviderValidationError("reference speech echo conflicts with canonical narration")
        claim_ids = section.get("claim_ids", [])
        if not isinstance(claim_ids, (list, tuple)) or any(not isinstance(claim, str) or claim not in claim_sources for claim in claim_ids):
            raise ProviderValidationError("reference section cites an unknown claim")
        cited = set().union(*(claim_sources[claim] for claim in claim_ids))
        if "source_ids" in scene:
            echoed_sources = scene["source_ids"]
            if not isinstance(echoed_sources, (list, tuple)) or any(not isinstance(source, str) for source in echoed_sources) or set(echoed_sources) != cited:
                raise ProviderValidationError("reference visual sources differ from narrated claims")
        if len(cited) > 3:
            raise ProviderValidationError("reference scene cites more sources than the renderer supports")
        scene = {**scene, "source_ids": [source.source_id for source in request.sources if source.source_id in cited]}
        sections[index] = {**section, "narration": clean}
        scene = {key: value for key, value in scene.items() if key != "cues"}
        bound.append({**scene, "vo": clean, **({"cues": cue_list} if cue_list else {})})
    whispers = 0  # a whole video may whisper at most twice; extras degrade to normal speech
    for scene in bound:
        kept = []
        for cue in scene.get("cues", []):
            if cue["kind"] == "whisper":
                whispers += 1
                if whispers > MAX_WHISPERS_PER_VIDEO:
                    continue
            kept.append(cue)
        if kept:
            scene["cues"] = kept
        else:
            scene.pop("cues", None)
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
    return {**package, "script_sections": sections, "reference_short": topic, "scene_plans": plans}


def require_source_excerpts(request: ContentRequest) -> None:
    if not any(source.excerpt and source.excerpt.strip() for source in request.sources):
        raise InsufficientSourcesError("Provide approved source excerpts supporting this brief before generating narration.")
