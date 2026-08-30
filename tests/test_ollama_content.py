from __future__ import annotations

import json
from pathlib import Path

import pytest

from tubeforge.core.config import DatabaseConfig, OllamaProviderConfig, Settings
from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.db.models import Base
from tubeforge.db.repositories import GenerationCacheRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.providers.content.factory import create_content_provider
from tubeforge.providers.content.ollama import OllamaContentProvider, OllamaResponse


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
    assert provider.last_usage == {"prompt_eval_count": 120, "eval_count": 340}
    assert calls[0]["stream"] is False and isinstance(calls[0]["format"], dict)
    assert provider.generate_package(request()).metadata.title_options == ("Why Rome Fell",)
    assert len(calls) == 1


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


def test_ollama_is_selectable_and_remote_url_is_validated(resources) -> None:
    _, session_factory = resources
    settings = Settings.model_validate({"app": {"name": "x", "environment": "test"}, "database": {"url": "sqlite:///x.db"}, "pipeline": {"content_provider": "ollama", "ollama": {"base_url": "http://inference-box.local:11434", "model": "qwen"}}})
    assert isinstance(create_content_provider(settings, session_factory), OllamaContentProvider)
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
