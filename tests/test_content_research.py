from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from tubeforge import host_codex_runner as runner
from tubeforge.core.errors import InsufficientSourcesError
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.pipeline.sources import SourceSnapshot
from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest
from tubeforge.providers.content.research import ResearchResult, fetch_research_packet, needs_research, research_prompt


def brief():
    return ContentRequest(topic="Why companies adopt Rust", angle="Does AI reduce migration work?",
        target_duration_seconds=60, language="en", audience="general", prompt_version="m6-content-v7",
        sources=(SourceReference(source_id="operator-notes", url="https://local.invalid/operator-notes", title="Brief", excerpt="AI makes migration easy"),))


def research():
    return {"status": "ready", "assessment": "Adoption exists; AI causation needs evidence.", "sources": [
        {"source_id": "one", "url": "https://example.com/one", "title": "First"},
        {"source_id": "two", "url": "https://example.org/two", "title": "Second"}]}


def test_notes_are_hypotheses_and_explicit_sources_are_preserved():
    assert needs_research(brief())
    assert "hypothesis" in research_prompt(brief())
    assert not needs_research(brief().model_copy(update={"sources": (SourceReference(source_id="provided", url="https://example.com/doc", title="Doc", excerpt="Evidence"),)}))


def test_packet_uses_fetched_text_not_model_assessment():
    class Fetcher:
        def __init__(self, hosts, **kwargs):
            assert hosts == frozenset({"example.com", "example.org"})
            assert kwargs["max_chars"] == 5000
        def ingest(self, source):
            return SourceSnapshot(source.source_id, str(source.url), source.title, datetime.now(UTC), source.source_id * 32, ("Fetched " + source.source_id + " ") * 30)
    packet = fetch_research_packet(ResearchResult.model_validate(research()), ingestor_factory=Fetcher)
    assert packet["retrieval_mode"] == "codex_researched"
    assert [s["excerpt"] for s in packet["sources"]] == [("Fetched one ") * 30, ("Fetched two ") * 30]
    assert all(s["untrusted"] for s in packet["sources"])
    with pytest.raises(InsufficientSourcesError):
        fetch_research_packet(ResearchResult(status="insufficient_sources", assessment="No evidence", sources=()))


def test_research_host_uses_web_search_and_reuses_durable_result(monkeypatch, tmp_path):
    request = GenerateShortsScriptRequest(operation="ResearchSourcesV1", request=brief())
    monkeypatch.setattr(runner, "bubblewrap_args", lambda _: ["codex", "exec"])
    calls = []
    def fake_run(command, **kwargs):
        calls.append(command)
        output = next((tmp_path / "outputs").glob("*/content-package.schema.json")).with_name("content-package.json")
        output.write_text(json.dumps(research()))
        return subprocess.CompletedProcess(command, 0, b'{"type":"item.completed","item":{"type":"web_search"}}\n{"usage":{"input_tokens":123}}\n', b'')
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run_research(request, root=tmp_path)
    assert calls == [["codex", "--search", "exec"]]
    assert result.usage["input_tokens"] == 123
    assert runner.run_research(request, root=tmp_path) == result
    assert len(calls) == 1
    assert not list((tmp_path / "outputs").iterdir())


def test_research_without_web_activity_is_rejected_and_not_retried(monkeypatch, tmp_path):
    request = GenerateShortsScriptRequest(operation="ResearchSourcesV1", request=brief())
    monkeypatch.setattr(runner, "bubblewrap_args", lambda _: ["codex", "exec"])
    def fake_run(command, **kwargs):
        output = next((tmp_path / "outputs").glob("*/content-package.schema.json")).with_name("content-package.json")
        output.write_text(json.dumps(research()))
        return subprocess.CompletedProcess(command, 0, b'', b'')
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="web search"):
        runner.run_research(request, root=tmp_path)
    with pytest.raises(runner.AllowanceExhaustedError):
        runner.run_research(request, root=tmp_path)


@pytest.mark.parametrize("url", ["http://example.com", "https://name:secret@example.com", "https://example.com:444"])
def test_research_rejects_unsafe_url_syntax(url):
    raw = research(); raw["sources"][0]["url"] = url
    with pytest.raises(ValueError): ResearchResult.model_validate(raw)


def test_three_researched_sources_fit_production_prompt_budget():
    from tubeforge.providers.content.prompts import build_content_prompt
    sources = tuple(SourceReference(source_id=f"s{i}", url=f"https://example.com/{i}", title=f"Evidence {i}", excerpt="a" * 3333) for i in range(3))
    request = brief().model_copy(update={"sources": sources})
    assert len(build_content_prompt(request, template_version=request.prompt_version, max_chars=60000)) <= 60000


def test_soft_redirect_is_excluded_and_never_counts_as_evidence():
    raw = research()
    raw["sources"].append({"source_id": "redirect", "url": "https://example.net/redirect", "title": "Redirect"})
    class Fetcher:
        def __init__(self, *args, **kwargs): pass
        def ingest(self, source):
            text = "Redirect Click here to be redirected." if source.source_id == "redirect" else "Substantive source text. " * 30
            return SourceSnapshot(source.source_id, str(source.url), source.title, datetime.now(UTC), source.source_id * 32, text)
    packet = fetch_research_packet(ResearchResult.model_validate(raw), ingestor_factory=Fetcher)
    assert [s["source_id"] for s in packet["sources"]] == ["one", "two"]
    assert packet["excluded_sources"][0]["source_id"] == "redirect"
    raw["sources"].pop(0)
    with pytest.raises(InsufficientSourcesError, match="substantive"):
        fetch_research_packet(ResearchResult.model_validate(raw), ingestor_factory=Fetcher)


def test_overlong_assessment_is_clipped_on_a_sentence_instead_of_failing_validation():
    from tubeforge.providers.content.research import ASSESSMENT_LIMIT, ResearchResult, clip_assessment
    sources = [{"source_id": "one", "url": "https://example.com/one", "title": "One"},
               {"source_id": "two", "url": "https://example.com/two", "title": "Two"}]
    long = {"status": "ready", "assessment": "Supported claim. " * 200, "sources": sources}
    with pytest.raises(Exception):
        ResearchResult.model_validate(long)
    clipped = ResearchResult.model_validate(clip_assessment(long))
    assert len(clipped.assessment) <= ASSESSMENT_LIMIT and clipped.assessment.endswith("claim.")
    short = {"status": "ready", "assessment": "Fine.", "sources": sources}
    assert clip_assessment(short) is short
