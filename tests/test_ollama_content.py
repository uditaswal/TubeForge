from __future__ import annotations

import json
from pathlib import Path

import pytest

from tubeforge.core.config import DatabaseConfig, OllamaProviderConfig, Settings
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.db.models import Base
from tubeforge.db.repositories import GenerationCacheRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentPackage, ContentRequest, SourceReference
from tubeforge.providers.content.ollama import OllamaContentProvider, OllamaResponse
from tubeforge.providers.content.prompts import build_content_prompt, validate_video_package


def request() -> ContentRequest:
    return ContentRequest(topic="Why Rome fell", angle="A short explainer", target_duration_seconds=60, language="en", audience="general", prompt_version="m26-v1", sources=(SourceReference(source_id="source-1", url="https://example.invalid/rome", title="Rome reference"),))


def package(value: ContentRequest) -> dict[str, object]:
    sections = [{"section_id": f"section-{index}", "narration": f"Narration for scene {index} explains Roman history with enough meaningful sourced words for an engaging short video.", "scene_id": f"scene-{index}", "claim_ids": ["claim-1"], "contains_factual_claims": True} for index in range(1, 7)]
    scenes = [{"scene_id": f"scene-{index}", "visual_type": "illustration", "search_queries": [f"Roman scene {index}"], "fallback_visual": "synthetic_illustration"} for index in range(1, 7)]
    return {"schema_version": "1.0", "request": value.model_dump(mode="json"), "claims": [{"claim_id": "claim-1", "text": "Rome changed over time.", "source_ids": ["source-1"], "confidence": "high", "review_status": "verified", "human_review_required": False}], "script_sections": sections, "scene_plans": scenes, "metadata": {"title_options": ["Why Rome Fell"], "description": "A sourced explanation."}, "thumbnail_brief": {"text_options": ["ROME"], "visual_direction": "Roman skyline", "accessibility_description": "A Roman skyline"}, "clip_candidates": []}


@pytest.fixture
def resources(tmp_path: Path):
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'cache.db'}"))
    Base.metadata.create_all(database.engine)
    try:
        yield GenerationCacheRepository(database.session_factory), database.session_factory
    finally:
        database.dispose()


def response_for(value: ContentRequest) -> OllamaResponse:
    envelope = {"response": json.dumps(package(value)), "done": True, "prompt_eval_count": 120, "eval_count": 340}
    return OllamaResponse(200, json.dumps(envelope).encode())


def test_valid_generation_uses_structured_request_and_persistent_cache(resources) -> None:
    cache, _ = resources
    calls: list[dict[str, object]] = []

    def transport(url: str, payload: bytes, connect: int, inference: int, limit: int) -> OllamaResponse:
        decoded = json.loads(payload)
        calls.append(decoded)
        assert url == "http://ollama.lan:11434" and connect == 4 and inference == 90 and limit > 0
        return response_for(request())

    provider = OllamaContentProvider(OllamaProviderConfig(base_url="http://ollama.lan:11434", model="small-model", connection_timeout_seconds=4, inference_timeout_seconds=90), cache, transport=transport)
    assert len(provider.generate_package(request()).scene_plans) == 6
    assert provider.last_usage == {"prompt_eval_count": 120, "eval_count": 340, "validation_attempts": 1}
    assert calls[0]["stream"] is False and isinstance(calls[0]["format"], dict)
    assert provider.generate_package(request()).metadata.title_options == ("Why Rome Fell",)
    assert len(calls) == 1


def test_shorts_structured_format_requires_six_developed_narration_sections(resources) -> None:
    cache, _ = resources
    value = short_request().model_copy(update={"prompt_version": "schema-bounds-v1"})
    captured: dict[str, object] = {}

    def transport(_url: str, payload: bytes, *_args) -> OllamaResponse:
        captured.update(json.loads(payload))
        accepted = short_package(value)
        return OllamaResponse(200, json.dumps({"response": accepted.model_dump_json(), "done": True}).encode())

    OllamaContentProvider(OllamaProviderConfig(retries=0), cache, transport=transport).generate_package(value)
    schema = captured["format"]
    assert schema["properties"]["script_sections"]["minItems"] == 6
    assert schema["properties"]["script_sections"]["maxItems"] == 6
    assert schema["$defs"]["ScriptSection"]["properties"]["narration"]["minLength"] == 105


def test_retries_transient_transport_and_server_failures(resources) -> None:
    cache, _ = resources
    outcomes: list[object] = [OSError("offline"), OllamaResponse(503, b"busy"), response_for(request())]

    def transport(*_) -> OllamaResponse:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    provider = OllamaContentProvider(OllamaProviderConfig(retries=2), cache, transport=transport)
    assert provider.generate_package(request()).script_sections[0].scene_id == "scene-1"
    assert not outcomes


def test_malformed_and_too_short_outputs_fail_before_cache_acceptance(resources) -> None:
    cache, _ = resources

    def malformed(*_) -> OllamaResponse:
        return OllamaResponse(200, b'{"response":"not json","done":true}')

    with pytest.raises(ProviderValidationError, match="structured JSON"):
        OllamaContentProvider(OllamaProviderConfig(retries=0), cache, transport=malformed).generate_package(request())

    other_request = request().model_copy(update={"prompt_version": "short-v1"})
    short = package(other_request)
    short["script_sections"] = short["script_sections"][:1]  # type: ignore[index]
    short["scene_plans"] = short["scene_plans"][:1]  # type: ignore[index]

    def too_short(*_) -> OllamaResponse:
        return OllamaResponse(200, json.dumps({"response": json.dumps(short), "done": True}).encode())

    with pytest.raises(ProviderValidationError, match="at least six"):
        OllamaContentProvider(OllamaProviderConfig(retries=0), cache, transport=too_short).generate_package(other_request)


def test_incomplete_generation_is_rejected_and_not_cached(resources) -> None:
    cache, _ = resources
    value = request().model_copy(update={"prompt_version": "interrupted-v1"})
    calls = 0

    def interrupted(*_) -> OllamaResponse:
        nonlocal calls
        calls += 1
        return OllamaResponse(200, json.dumps({"response": json.dumps(package(value)), "done": False}).encode())

    provider = OllamaContentProvider(OllamaProviderConfig(retries=0), cache, transport=interrupted)
    with pytest.raises(ProviderValidationError, match="completed generation"):
        provider.generate_package(value)
    with pytest.raises(ProviderValidationError, match="completed generation"):
        provider.generate_package(value)
    assert calls == 2


def test_exhausted_connection_failure_is_retryable(resources) -> None:
    cache, _ = resources

    def offline(*_) -> OllamaResponse:
        raise TimeoutError

    with pytest.raises(RetryableProviderError, match="timeout"):
        OllamaContentProvider(OllamaProviderConfig(retries=1), cache, transport=offline).generate_package(request())

    # A failed owner releases only its own fenced reservation, so the next job
    # attempt reaches inference immediately instead of waiting for expiry.
    recovered = OllamaContentProvider(OllamaProviderConfig(retries=0), cache, transport=lambda *_: response_for(request()))
    assert len(recovered.generate_package(request()).scene_plans) == 6


def test_ollama_is_not_selectable_in_pipeline_configuration(resources) -> None:
    with pytest.raises(ValueError, match="content_provider"):
        Settings.model_validate({"app": {"name": "x", "environment": "test"}, "database": {"url": "sqlite:///x.db"}, "pipeline": {"content_provider": "ollama"}})
    with pytest.raises(ValueError, match="credentials"):
        OllamaProviderConfig(base_url="http://user:password@localhost:11434")


def test_ollama_configuration_is_normalized_before_transport() -> None:
    config = OllamaProviderConfig(
        base_url="  http://inference-box.local:11434/api/  ",
        model="  qwen2.5:3b  ",
        prompt_template_version="  m6-content-v1  ",
    )
    assert config.base_url == "http://inference-box.local:11434/api"
    assert config.model == "qwen2.5:3b"
    assert config.prompt_template_version == "m6-content-v1"

    with pytest.raises(ValueError, match="blank"):
        OllamaProviderConfig(model="   ")
    with pytest.raises(ValueError, match="blank"):
        OllamaProviderConfig(prompt_template_version="\t")


def short_request() -> ContentRequest:
    source = SourceReference(
        source_id="source-1",
        url="https://example.invalid/debugging",
        title="Approved debugging brief",
        excerpt="Your fastest debugging shortcut is finding the first observable failure. Later errors can hide the original cause. Start where behavior first differs from the expected result. Write down one assumption about that boundary, design the smallest focused check that can prove it wrong, change one variable, and record clear evidence before another edit. Move forward only after the current boundary behaves correctly. Apply the method to your next bug, save the result, and share the habit with your team.",
    )
    return request().model_copy(
        update={
            "topic": "A debugging habit that saves hours",
            "angle": "Trace the first observable failure",
            "target_duration_seconds": 45,
            "prompt_version": "shorts-source-v2",
            "sources": (source,),
            "preset_name": "shorts",
            "aspect_ratio": "9:16",
        }
    )


def short_package(value: ContentRequest) -> ContentPackage:
    raw = package(value)
    sections = raw["script_sections"]
    assert isinstance(sections, list)
    bodies = (
        "Your fastest debugging shortcut is finding the first observable failure.",
        "Start where behavior first differs from the expected result, because later errors often hide the original cause completely. That boundary matters most.",
        "Write down one assumption about that boundary, then design the smallest check that can prove it wrong quickly. Keep the check focused.",
        "Change only one variable for each check, and record the evidence before another edit makes the result ambiguous. Evidence prevents repeated guesses.",
        "Move forward only after the current boundary behaves correctly, repeating the same method until the failure disappears. Preserve each clear result.",
        "Try this on your next bug, save the result, and share the habit with your team.",
    )
    for section, narration in zip(sections, bodies, strict=True):
        section["narration"] = narration
    return ContentPackage.model_validate(raw)


def test_shorts_prompt_loads_skill_and_preserves_legacy_validation() -> None:
    value = short_request()
    prompt = build_content_prompt(value, template_version="m6-content-v4", max_chars=60_000)
    assert "This is a YouTube Short" in prompt
    assert "approved source excerpts" in prompt
    assert "RESOURCE yt-script/automation.md" in prompt
    assert "108 to 166 words" in prompt

    accepted = short_package(value)
    validate_video_package(accepted, value, provider_name="Ollama")

    no_cta_sections = list(accepted.script_sections)
    no_cta_sections[-1] = no_cta_sections[-1].model_copy(update={"narration": "The method ends by preserving the evidence for the next investigation."})
    no_cta = accepted.model_copy(update={"script_sections": tuple(no_cta_sections)})
    with pytest.raises(ProviderValidationError, match="call to action"):
        validate_video_package(no_cta, value, provider_name="Ollama")

    unsupported = value.model_copy(update={"sources": (value.sources[0].model_copy(update={"excerpt": None}),)})
    unsupported_package = accepted.model_copy(update={"request": unsupported})
    with pytest.raises(ProviderValidationError, match="approved source excerpt"):
        validate_video_package(unsupported_package, unsupported, provider_name="Ollama")

    repeated_sections = tuple(section.model_copy(update={"narration": "Use this method. " + section.narration}) for section in accepted.script_sections)
    with pytest.raises(ProviderValidationError, match="repeat the same opening"):
        validate_video_package(accepted.model_copy(update={"script_sections": repeated_sections}), value, provider_name="Ollama")

    invented_sections = list(accepted.script_sections)
    invented_sections[2] = invented_sections[2].model_copy(update={"narration": "Configure Kubernetes clusters, database replicas, network proxies, and cloud dashboards before rebuilding the deployment pipeline from scratch."})
    with pytest.raises(ProviderValidationError, match="outside the approved source"):
        validate_video_package(accepted.model_copy(update={"script_sections": tuple(invented_sections)}), value, provider_name="Ollama")


def test_ollama_can_regenerate_a_locally_rejected_shorts_package(resources) -> None:
    cache, _ = resources
    value = short_request().model_copy(update={"prompt_version": "shorts-retry-v2"})
    accepted = short_package(value)
    rejected_sections = list(accepted.script_sections)
    rejected_sections[-1] = rejected_sections[-1].model_copy(update={"narration": "The method ends by preserving clear evidence for the next investigation."})
    rejected = accepted.model_copy(update={"script_sections": tuple(rejected_sections)})
    outcomes = [rejected, accepted]
    prompts: list[str] = []

    def transport(_url: str, payload: bytes, *_: int) -> OllamaResponse:
        request_payload = json.loads(payload)
        prompts.append(request_payload["prompt"])
        result = outcomes.pop(0)
        return OllamaResponse(200, json.dumps({"response": result.model_dump_json(), "done": True}).encode())

    provider = OllamaContentProvider(OllamaProviderConfig(validation_retries=1, retries=0), cache, transport=transport)
    assert provider.generate_package(value).script_sections[-1].narration.startswith("Try this")
    assert len(prompts) == 2 and "previous JSON was rejected" in prompts[1]
    assert provider.last_usage == {"validation_attempts": 2}


def test_ollama_cannot_rewrite_authoritative_request_or_sources(resources) -> None:
    cache, _ = resources
    value = request().model_copy(update={"prompt_version": "authority-v2"})
    raw = package(value)
    raw["request"] = {**raw["request"], "topic": "model rewrite", "sources": [{"source_id": "invented", "url": "https://example.invalid/invented", "title": "Invented"}]}  # type: ignore[index]

    provider = OllamaContentProvider(
        OllamaProviderConfig(retries=0),
        cache,
        transport=lambda *_: OllamaResponse(200, json.dumps({"response": json.dumps(raw), "done": True}).encode()),
    )
    accepted = provider.generate_package(value)
    assert accepted.request == value
    assert accepted.claims[0].source_ids == ("source-1",)


def test_ollama_binds_factual_sections_to_generated_cited_claims_when_edge_is_omitted(resources) -> None:
    cache, _ = resources
    value = short_request().model_copy(update={"prompt_version": "missing-claim-edge-v1"})
    raw = short_package(value).model_dump(mode="json")
    for section in raw["script_sections"]:
        section["contains_factual_claims"] = True
        section["claim_ids"] = []

    def transport(*_) -> OllamaResponse:
        return OllamaResponse(200, json.dumps({"response": json.dumps(raw), "done": True}).encode())

    generated = OllamaContentProvider(OllamaProviderConfig(retries=0), cache, transport=transport).generate_package(value)
    assert all(section.claim_ids == ("claim-1",) for section in generated.script_sections)
