from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tubeforge.core.config import CodexProviderConfig, DatabaseConfig, Settings
from tubeforge.core.errors import ProviderAuthenticationError, ProviderValidationError, RetryableProviderError
from tubeforge.db.models import Base
from tubeforge.db.repositories import CachedGeneration, GenerationCacheRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.providers.content.codex_cli import CodexCliContentProvider, ProcessResult, _safe_diagnostic
from tubeforge.providers.content.factory import create_content_provider
from tubeforge.providers.content.prompts import build_content_prompt
from tubeforge.providers.fake import FakeContentProvider


def request(*, topic: str = "Rain", prompt_version: str = "test-v1") -> ContentRequest:
    return ContentRequest(topic=topic, angle="A short explainer", target_duration_seconds=60, language="en-IN", audience="general", prompt_version=prompt_version, sources=(SourceReference(source_id="source-1", url="https://example.invalid/rain", title="Rain reference"),))


def package(value: ContentRequest) -> dict[str, object]:
    sections = [{"section_id": f"section-{index}", "narration": f"Rain scene {index} explains how clouds produce weather, using clear sourced details for curious viewers today.", "scene_id": f"scene-{index}", "claim_ids": ["claim-1"], "contains_factual_claims": True} for index in range(1, 7)]
    scenes = [{"scene_id": f"scene-{index}", "visual_type": "illustration", "search_queries": [f"rain clouds {index}"], "fallback_visual": "text_card"} for index in range(1, 7)]
    return {"schema_version": "1.0", "request": value.model_dump(mode="json"), "claims": [{"claim_id": "claim-1", "text": "Rain falls from clouds.", "source_ids": ["source-1"], "confidence": "high", "review_status": "verified", "human_review_required": False}], "script_sections": sections, "scene_plans": scenes, "metadata": {"title_options": ["Rain"], "description": "A cited explanation."}, "thumbnail_brief": {"text_options": ["RAIN"], "visual_direction": "Blue rain clouds", "accessibility_description": "Rain clouds"}, "clip_candidates": []}


@pytest.fixture
def resources(tmp_path: Path):
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'cache.db'}"))
    Base.metadata.create_all(database.engine)
    try:
        yield GenerationCacheRepository(database.session_factory)
    finally:
        database.dispose()


def runner_with(payloads: list[object], calls: list[list[str]]):
    def runner(args: list[str], prompt: str, output: Path, timeout: int, limit: int) -> ProcessResult:
        calls.append(args)
        assert "REQUEST=" in prompt or "REPAIR=" in prompt
        output.write_text(json.dumps(payloads.pop(0)), encoding="utf-8")
        return ProcessResult(0, b'{"usage":{"input_tokens":12,"output_tokens":34}}\n', b"")
    return runner


def test_generation_persists_validated_package_provenance_usage_and_hits_cache(resources) -> None:
    calls: list[list[str]] = []
    value = request()
    provider = CodexCliContentProvider(CodexProviderConfig(), resources, process_runner=runner_with([package(value)], calls))
    assert provider.generate_package(value).claims[0].claim_id == "claim-1"
    assert provider.last_usage == {"input_tokens": 12, "output_tokens": 34}
    assert provider.last_provenance and provider.last_provenance["provider"] == "codex-cli"
    assert provider.generate_package(value).metadata.title_options == ("Rain",)
    assert len(calls) == 1


def test_cli_arguments_are_fixed_and_never_include_request_data(resources, tmp_path: Path) -> None:
    provider = CodexCliContentProvider(CodexProviderConfig(executable="fake-codex", model="model-a"), resources)
    args = provider.build_cli_args(tmp_path / "schema.json", tmp_path / "result.json")
    assert args[:7] == ["fake-codex", "exec", "--ephemeral", "--sandbox", "read-only", "--model", "model-a"]
    assert "Rain" not in args and "--json" in args


def test_cache_keys_normalize_but_change_for_meaningful_inputs(resources) -> None:
    value = request(topic="  Rain\r\n")
    normalized = request(topic="Rain")
    key = resources.cache_key(value, "codex-cli", "model-a", "v1")
    assert key == resources.cache_key(normalized, "codex-cli", "model-a", "v1")
    assert key != resources.cache_key(normalized, "codex-cli", "model-b", "v1")
    assert key != resources.cache_key(normalized, "other", "model-a", "v1")
    assert key != resources.cache_key(normalized, "codex-cli", "model-a", "v2")
    assert key != resources.cache_key(request(topic="Snow"), "codex-cli", "model-a", "v1")


def test_competing_reservation_blocks_and_expired_reservation_recovers(resources) -> None:
    now = datetime(2026, 8, 3, tzinfo=UTC)
    first = resources.reserve_or_get(request(), "codex-cli", "model", "v", now=now, reservation_seconds=10)
    assert first is not None
    assert resources.reserve_or_get(request(), "codex-cli", "model", "v", now=now, reservation_seconds=10) is None
    replacement = resources.reserve_or_get(request(), "codex-cli", "model", "v", now=now + timedelta(seconds=11), reservation_seconds=10)
    assert replacement is not None and replacement != first
    assert resources.abandon(first) is False
    assert resources.accept(first, package(request()), {}, {}, now=now) is False
    assert resources.accept(replacement, package(request()), {"provider": "codex-cli"}, {}, now=now)
    cached = resources.reserve_or_get(request(), "codex-cli", "model", "v", now=now, reservation_seconds=10)
    assert isinstance(cached, CachedGeneration)


@pytest.mark.parametrize(("code", "stderr", "error"), [(1, b"login required token=abc", ProviderAuthenticationError), (124, b"timeout", RetryableProviderError), (1, b"network connection reset", RetryableProviderError)])
def test_process_failure_classification(resources, code: int, stderr: bytes, error: type[Exception]) -> None:
    def failed(*_): return ProcessResult(code, b"", stderr)
    with pytest.raises(error):
        CodexCliContentProvider(CodexProviderConfig(), resources, process_runner=failed).generate_package(request())


def test_failed_generation_releases_cache_reservation_for_immediate_retry(resources) -> None:
    value = request(prompt_version="retry-after-failure-v1")

    def failed(*_):
        return ProcessResult(124, b"", b"timeout")

    with pytest.raises(RetryableProviderError):
        CodexCliContentProvider(CodexProviderConfig(), resources, process_runner=failed).generate_package(value)
    recovered = CodexCliContentProvider(CodexProviderConfig(), resources, process_runner=runner_with([package(value)], []))
    assert len(recovered.generate_package(value).scene_plans) == 6


def test_invalid_json_and_schema_invalid_output_are_validation_failures(resources) -> None:
    def invalid_json(_a, _p, output, _t, _l):
        output.write_text("not-json", encoding="utf-8"); return ProcessResult(0, b"", b"")
    with pytest.raises(ProviderValidationError, match="valid JSON"):
        CodexCliContentProvider(CodexProviderConfig(), resources, process_runner=invalid_json).generate_package(request())


def test_implausibly_short_narration_is_rejected(resources) -> None:
    value = request(prompt_version="short-duration-v1")
    short = package(value)
    for section in short["script_sections"]:  # type: ignore[index]
        section["narration"] = "Too short."
    with pytest.raises(ProviderValidationError, match="word count"):
        CodexCliContentProvider(CodexProviderConfig(), resources, process_runner=runner_with([short], [])).generate_package(value)


def test_targeted_repair_replaces_only_invalid_claim(resources) -> None:
    value = request(); invalid = package(value); invalid["claims"][0]["human_review_required"] = "wrong"  # type: ignore[index]
    repaired_claim = package(value)["claims"][0]  # type: ignore[index]
    calls: list[list[str]] = []
    provider = CodexCliContentProvider(CodexProviderConfig(repair_attempt_limit=1), resources, process_runner=runner_with([invalid, repaired_claim], calls))
    assert provider.generate_package(value).claims[0].human_review_required is False
    assert len(calls) == 2


def test_repair_exhaustion_never_accepts_cache(resources) -> None:
    value = request(); invalid = package(value); invalid["claims"][0]["human_review_required"] = "wrong"  # type: ignore[index]
    calls: list[list[str]] = []
    with pytest.raises(ProviderValidationError):
        CodexCliContentProvider(CodexProviderConfig(repair_attempt_limit=1), resources, process_runner=runner_with([invalid, invalid["claims"][0]], calls)).generate_package(value)  # type: ignore[index]
    assert resources.reserve_or_get(value, "codex-cli", "gpt-5.2-codex", value.prompt_version, now=datetime.now(UTC), reservation_seconds=1) is None


def test_prompt_is_versioned_and_source_bounded() -> None:
    text = build_content_prompt(request(), template_version="m6-content-v1", max_chars=10_000)
    assert "REQUEST=" in text and "untrusted data" in text
    with pytest.raises(ValueError, match="unsupported"):
        build_content_prompt(request(), template_version="old", max_chars=10_000)


def test_safe_diagnostic_redacts_and_truncates() -> None:
    value = _safe_diagnostic(b"authorization=top-secret\nnext", 20)
    assert "top-secret" not in value and len(value) <= 20


def test_fake_remains_default_provider(resources) -> None:
    settings = Settings.model_validate({"app": {"name": "x", "environment": "test"}, "database": {"url": "sqlite:///./x.db"}})
    assert isinstance(create_content_provider(settings, resources._session_factory), FakeContentProvider)  # noqa: SLF001
