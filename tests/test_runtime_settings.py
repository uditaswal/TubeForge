"""Runtime settings store, the Settings page/API, prompt-size fitting and the automatic retry of rejected scripts."""
import json
import re

import pytest

from tubeforge.core import runtime_settings as rs
from tubeforge.core.config import AppConfig, AuthConfig, DatabaseConfig, Settings


@pytest.fixture
def store(tmp_path, monkeypatch):
    shared = rs.RuntimeSettings(tmp_path / "runtime-settings.json")
    monkeypatch.setattr(rs, "_shared", shared)
    return shared


def _settings(tmp_path):
    return Settings(app=AppConfig(name="test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{tmp_path / 's.db'}"), auth=AuthConfig(enabled=True))


def test_store_validates_persists_audits_and_resets(store, tmp_path):
    settings = _settings(tmp_path)
    assert store.value("prompt.margin_chars", 2500) == 2500
    row = store.update("prompt.margin_chars", 4000, "operator", settings)
    assert row["value"] == 4000 and row["overridden"] and row["updated_by"] == "operator"
    assert rs.RuntimeSettings(store.path).value("prompt.margin_chars", 2500) == 4000       # a second process sees it
    for key, bad in [("prompt.margin_chars", 10**9), ("prompt.margin_chars", "5"), ("prompt.margin_chars", True),
                     ("generation.auto_retry_rejected", 1), ("nope", 1)]:
        with pytest.raises(rs.SettingError):
            store.update(key, bad, "operator", settings)
    assert store.audit()[0]["new"] == 4000
    assert store.reset("prompt.margin_chars", "operator", settings)["overridden"] is False
    assert store.value("prompt.margin_chars", 2500) == 2500 and store.audit()[0]["new"] == "default"


def test_unreadable_or_invalid_file_never_blocks_and_attempt_limit_is_not_a_setting(store):
    store.path.write_text("{not json")
    assert store.value("worker.max_attempts", 3) == 3
    store.path.write_text(json.dumps({"values": {"worker.max_attempts": 999}}))
    assert store.value("worker.max_attempts", 3) == 3                                          # out of range: default wins
    assert not any("invocation" in d.key or "attempt_limit" in d.key for d in rs.DEFINITIONS)


def test_claude_prompt_limit_is_clamped_to_the_runner_ceiling(store, monkeypatch):
    monkeypatch.setenv("TUBEFORGE_CLAUDE_MAX_PROMPT_CHARS", "90000")
    store.update("prompt.max_chars_claude", 150_000, "operator", None) if False else None
    store.path.write_text(json.dumps({"values": {"prompt.max_chars_claude": 150_000, "prompt.max_chars_codex": 150_000}}))
    assert rs.effective_max_prompt_chars("claude", 75_000, store) == 90_000
    assert rs.effective_max_prompt_chars("codex", 75_000, store) == 150_000


def _client(tmp_path):
    from fastapi.testclient import TestClient
    from tubeforge.api.app import create_app
    from tubeforge.db.models import Base
    from tubeforge.db.session import create_database
    settings = _settings(tmp_path)
    db = create_database(settings.database)
    Base.metadata.create_all(db.engine)
    return TestClient(create_app(settings)), db


def test_settings_api_requires_login_and_csrf_and_round_trips(store, tmp_path):
    client, db = _client(tmp_path)
    with client:
        assert client.get("/api/runtime-settings").status_code == 401
        client.app.state.runtime.auth.create_admin("operator", "correct-horse-battery-staple")
        client.post("/login", json={"username": "operator", "password": "correct-horse-battery-staple"})
        listing = client.get("/api/runtime-settings").json()
        assert {r["key"] for r in listing["settings"]} == {d.key for d in rs.DEFINITIONS}
        assert client.put("/api/runtime-settings/worker.max_attempts", json={"value": 5}).status_code == 403   # no CSRF token
        client.headers["x-csrf-token"] = client.cookies["tubeforge_csrf"]
        saved = client.put("/api/runtime-settings/worker.max_attempts", json={"value": 5}).json()
        assert saved["value"] == 5 and saved["overridden"] and saved["updated_by"] == "operator"
        assert store.value("worker.max_attempts", 3) == 5
        assert client.put("/api/runtime-settings/worker.max_attempts", json={"value": 99}).status_code == 422
        assert client.put("/api/runtime-settings/unknown.key", json={"value": 1}).status_code == 422
        assert client.delete("/api/runtime-settings/worker.max_attempts").json()["overridden"] is False
        assert client.get("/api/runtime-settings").json()["audit"][0]["new"] == "default"
        page = client.get("/settings")
        assert page.status_code == 200 and "Settings" in page.text and "/settings" in client.get("/batch").text
    db.dispose()


def test_settings_page_script_parses():
    quickjs = pytest.importorskip("quickjs")
    from tubeforge.api.runtime_settings import render_settings_html
    script = re.search(r"<script>(.*?)</script>", render_settings_html("operator"), re.S).group(1)
    quickjs.Context().eval("(function(){" + script + "\n})")          # parse only, do not run


# --- prompt-size fitting -----------------------------------------------------------------------------------------

def _request(sizes, **extra):
    from tubeforge.domain.contracts import ContentRequest, SourceReference
    sentence = "This sentence explains one idea about interview practice. "
    sources = tuple(SourceReference(source_id=f"s{i}", url=f"https://example.org/{i}", title=f"Source {i}", excerpt=(sentence * (n // len(sentence) + 1))[:n])
                    for i, n in enumerate(sizes))
    return ContentRequest(topic="T", angle="A", target_duration_seconds=60, language="en", audience="general", prompt_version="m6-content-v8", aspect_ratio="9:16",
                          script_owner="claude", sources=sources, **extra)


def test_fit_leaves_a_request_that_already_fits_untouched():
    from tubeforge.pipeline.prompt_budget import fit_request, prompt_length
    request = _request([3000, 3000])
    fitted, report = fit_request(request, max_chars=prompt_length(request) + 5000, margin=1000)
    assert fitted is request and not report.changed


def test_fit_trims_the_longest_excerpts_at_sentence_ends_and_keeps_short_ones():
    from tubeforge.pipeline.prompt_budget import fit_request, prompt_length
    request = _request([16_000, 12_000, 2_000])
    limit = prompt_length(request) - 9_000
    fitted, report = fit_request(request, max_chars=limit + 2_500, margin=2_500)
    assert report.changed and report.prompt_after <= limit and report.prompt_before > limit
    lengths = [len(s.excerpt) for s in fitted.sources]
    assert lengths[2] == 2_000                                           # the short source is not touched
    assert lengths[0] < 16_000 and lengths[1] < 12_000 and abs(lengths[0] - lengths[1]) < 120   # one shared cap
    assert all(s.excerpt.endswith(".") for s in fitted.sources[:2])      # cut at a sentence end, not mid-word
    assert fitted.sources[0].excerpt == request.sources[0].excerpt[:lengths[0]]   # an exact prefix, so hashing stays exact


def test_fit_refuses_with_numbers_when_trimming_cannot_help_or_is_off():
    from tubeforge.pipeline.prompt_budget import PromptTooLarge, fit_request, prompt_length
    request = _request([16_000, 12_000])
    with pytest.raises(PromptTooLarge, match="Trimming is turned off"):
        fit_request(request, max_chars=prompt_length(request) - 100, margin=0, auto_trim=False)
    with pytest.raises(PromptTooLarge, match="even with every source excerpt cut"):
        fit_request(request, max_chars=prompt_length(_request([1_500, 1_500])) - 1_000, margin=0)


def test_video_request_builder_applies_the_budget(store, tmp_path):
    from fastapi import HTTPException
    from tubeforge.api.app import _fit_prompt
    settings = _settings(tmp_path)
    request = _request([24_000, 24_000, 24_000])
    fitted = _fit_prompt(request, settings)                           # 3 long pages used to exceed the ceiling
    from tubeforge.pipeline.prompt_budget import prompt_length
    assert prompt_length(fitted) <= 90_000 - 2_500 and len(fitted.sources[0].excerpt) < 24_000
    store.update("prompt.auto_trim_sources", False, "operator", settings)
    with pytest.raises(HTTPException) as refused:
        _fit_prompt(request, settings)
    assert refused.value.status_code == 422 and "too large for one script prompt" in refused.value.detail


# --- automatic retry of a rejected script ------------------------------------------------------------------------

def _rejecting_provider(tmp_path, calls):
    from sqlalchemy import select  # noqa: F401
    from tests.test_youtube_skills import request
    from tubeforge.core.config import CodexProviderConfig
    from tubeforge.db.models import Base
    from tubeforge.db.repositories import GenerationCacheRepository
    from tubeforge.db.session import create_database
    from tubeforge.providers.content import youtube_skills as skills
    from tubeforge.providers.content.host_runner import HostRunnerContentProvider
    from tubeforge.providers.content.host_runner_protocol import HostRunnerResponse, HostRunnerSuccess
    from tubeforge.providers.content.prompts import build_content_prompt, prompt_evidence
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path}/cache.db"))
    Base.metadata.create_all(database.engine)
    config = CodexProviderConfig()
    ask = request().model_copy(update={"target_duration_seconds": 60})

    def transport(_path, payload, _timeout):
        data = json.loads(payload)
        calls.append(data["operation"])
        if data["operation"] == "PreflightContentV1":
            prompt = build_content_prompt(ask, template_version=skills.SKILL_TEMPLATE, max_chars=config.max_prompt_chars)
            ready = HostRunnerSuccess(package={}, provenance={"resource_hashes": skills.preflight(), "prompt_sha256": prompt_evidence(prompt)["prompt_sha256"]})
            return HostRunnerResponse(ok=True, result=ready).model_dump_json().encode()
        return HostRunnerResponse(ok=False, failure={"code": "invalid_output", "message": "script failed the hook gate", "invocation_started": True}).model_dump_json().encode()

    return HostRunnerContentProvider(config, GenerationCacheRepository(database.session_factory), transport=transport), ask, database


def test_rejected_script_retries_automatically_but_never_beyond_the_two_attempt_allowance(store, tmp_path):
    from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
    calls = []
    provider, ask, database = _rejecting_provider(tmp_path, calls)
    with pytest.raises(RetryableProviderError, match="retrying automatically"):       # attempt 1 rejected, one attempt left
        provider.generate_package(ask)
    with pytest.raises(ProviderValidationError) as spent:                              # attempt 2 rejected: allowance spent
        provider.generate_package(ask)
    assert not isinstance(spent.value, RetryableProviderError)
    with pytest.raises(ProviderValidationError, match="two-attempt limit"):            # a third try is refused by the cache
        provider.generate_package(ask)
    assert calls.count("PreflightContentV1") == 3 and len([c for c in calls if c != "PreflightContentV1"]) == 2   # exactly two writer calls
    database.dispose()


def test_auto_retry_can_be_switched_off_from_the_settings(store, tmp_path):
    from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
    store.update("generation.auto_retry_rejected", False, "operator", _settings(tmp_path))
    provider, ask, database = _rejecting_provider(tmp_path, [])
    with pytest.raises(ProviderValidationError) as rejected:
        provider.generate_package(ask)
    assert not isinstance(rejected.value, RetryableProviderError)
    database.dispose()
