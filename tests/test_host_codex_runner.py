from __future__ import annotations

import copy
import json
import re
import socket
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import func, select

from tubeforge import host_codex_runner as runner
from tubeforge.core.config import CodexProviderConfig, DatabaseConfig, Settings
from tubeforge.db.models import Base, GenerationCacheRecord
from tubeforge.db.repositories import GenerationCacheRepository
from tubeforge.db.session import create_database
from tubeforge.domain.contracts import ContentPackage, ContentRequest, SourceReference
from tubeforge.providers.content.factory import create_content_provider
from tubeforge.providers.content.host_runner import HostRunnerContentProvider
from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest
from tubeforge.providers.content.prompts import build_content_prompt
from tubeforge.providers.fake import FakeContentProvider


def caption_timing_request() -> GenerateShortsScriptRequest:
    fixture = Path(__file__).parent / "fixtures" / "host_codex_caption_timing_request.json"
    return GenerateShortsScriptRequest.model_validate_json(fixture.read_text(encoding="utf-8"))


def overlong_package(request: GenerateShortsScriptRequest) -> dict[str, object]:
    package = FakeContentProvider().generate_package(request.request).model_dump(mode="json")
    package["scene_plans"][1]["fallback_visual"] = "Portrait editor timeline with clear waveforms and readable highlighted captions while the current word stays in sync with spoken narration"
    package["scene_plans"][-1]["fallback_visual"] = "A vertical finished video frame with a bright current-word caption, a balanced scene transition, and waveform timing markers underneath"
    return package


def test_overlong_fallbacks_are_shortened_only_at_word_boundaries() -> None:
    raw = overlong_package(caption_timing_request())
    original = copy.deepcopy(raw)

    normalized, changes = runner.normalize_fallback_visuals(raw)

    assert raw == original
    assert len(changes) == 2
    assert [change["field"] for change in changes] == ["scene_plans.1.fallback_visual", f"scene_plans.{len(raw['scene_plans']) - 1}.fallback_visual"]
    assert all(change["method"] == "word_boundary_truncation" for change in changes)
    assert all(change["original_length"] > 100 and change["normalized_length"] <= 100 for change in changes)
    for change in changes:
        index = int(change["field"].split(".")[1])
        before = original["scene_plans"][index]["fallback_visual"]
        after = normalized["scene_plans"][index]["fallback_visual"]
        assert before.startswith(after + " ")
    restored = copy.deepcopy(normalized)
    for change in changes:
        index = int(change["field"].split(".")[1])
        restored["scene_plans"][index]["fallback_visual"] = original["scene_plans"][index]["fallback_visual"]
    assert restored == original
    assert ContentPackage.model_validate(normalized).request == caption_timing_request().request


def test_fallback_without_safe_boundary_still_fails_domain_validation() -> None:
    raw = overlong_package(caption_timing_request())
    raw["scene_plans"][1]["fallback_visual"] = "X" * 101
    normalized, changes = runner.normalize_fallback_visuals(raw)
    assert normalized["scene_plans"][1]["fallback_visual"] == "X" * 101
    assert all(change["field"] != "scene_plans.1.fallback_visual" for change in changes)
    with pytest.raises(ValueError, match="fallback_visual"):
        ContentPackage.model_validate(normalized)


def test_run_request_records_normalization_without_retry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    request = caption_timing_request()
    raw = overlong_package(request)
    launches: list[list[str]] = []
    monkeypatch.setattr(runner, "bubblewrap_args", lambda _workspace: ["fixed-codex-command"])

    def fake_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        launches.append(command)
        output = next((tmp_path / "outputs").glob("*/content-package.schema.json")).with_name("content-package.json")
        output.write_text(json.dumps(raw), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, b'{"usage":{"input_tokens":7}}\n', b"")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    result = runner.run_request(request, root=tmp_path)
    assert launches == [["fixed-codex-command"]]
    assert result.usage == {"input_tokens": 7}
    assert result.package["request"] == raw["request"]
    assert result.package["claims"] == raw["claims"]
    assert result.package["script_sections"] == raw["script_sections"]
    assert len(result.provenance["normalizations"]) == 2
    assert not list((tmp_path / "outputs").iterdir())
    runner.consume_invocation(request, tmp_path)
    with pytest.raises(runner.AllowanceExhaustedError):
        runner.consume_invocation(request, tmp_path)


def test_review_gates_smoke_packet_is_typed_and_prompt_bounded() -> None:
    fixture = Path(__file__).parent / "fixtures" / "host_codex_review_gates_request.json"
    request = GenerateShortsScriptRequest.model_validate_json(fixture.read_text(encoding="utf-8"))
    assert request.request.aspect_ratio == "9:16"
    assert request.request.target_duration_seconds == 45
    assert request.request.sources[0].excerpt
    prompt = build_content_prompt(request.request, template_version=request.request.prompt_version, max_chars=60_000)
    assert "REQUEST=" in prompt
    assert "Copy ContentPackage.request exactly from REQUEST" in prompt
    assert "topic-specific tension or payoff" in prompt
    assert "next bug" not in prompt


def test_caption_timing_packet_is_distinct_and_source_grounded() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    request = GenerateShortsScriptRequest.model_validate_json(
        (fixtures / "host_codex_caption_timing_request.json").read_text(encoding="utf-8")
    )
    exhausted = GenerateShortsScriptRequest.model_validate_json(
        (fixtures / "host_codex_review_gates_request.json").read_text(encoding="utf-8")
    )
    assert request.request.target_duration_seconds == 45
    assert request.request.aspect_ratio == "9:16"
    assert request.request.topic != exhausted.request.topic
    assert request.request.angle != exhausted.request.angle
    assert request.request.sources[0].excerpt != exhausted.request.sources[0].excerpt
    excerpt = request.request.sources[0].excerpt or ""
    assert "local waveform aligner" in excerpt
    assert "The currently spoken word is yellow" in excerpt
    readme = (Path(__file__).resolve().parents[1] / "readme.md").read_text(encoding="utf-8")
    assert re.sub(r"\s+", " ", excerpt) in re.sub(r"\s+", " ", readme)
    prompt = build_content_prompt(request.request, template_version=request.request.prompt_version, max_chars=60_000)
    assert "Copy ContentPackage.request exactly from REQUEST" in prompt
    assert "next bug" not in prompt


def test_codex_output_schema_requires_every_object_property() -> None:
    schema = runner.codex_output_schema()

    def check(value: object) -> None:
        if isinstance(value, dict):
            assert "default" not in value
            assert "minLength" not in value
            assert "maxLength" not in value
            assert value.get("format") != "uri"
            if value.get("type") == "object":
                assert value["additionalProperties"] is False
                assert set(value["required"]) == set(value["properties"])
            for child in value.values():
                check(child)
        elif isinstance(value, list):
            for child in value:
                check(child)

    check(schema)
    assert "time_sensitive" in schema["$defs"]["CitedClaim"]["required"]
    assert "clip_candidates" in schema["required"]


def test_host_enforces_two_invocations_across_reopens(tmp_path: Path) -> None:
    request = GenerateShortsScriptRequest(request=ContentRequest(
        topic="A source-grounded test", angle="Explain one point", target_duration_seconds=35,
        language="en", audience="general", prompt_version="m6-content-v4",
        sources=(SourceReference(source_id="source-1", url="https://example.invalid/source", title="Source", excerpt="One point."),),
        aspect_ratio="9:16",
    ))
    runner.consume_invocation(request, tmp_path)
    runner.consume_invocation(request, tmp_path)
    with pytest.raises(runner.AllowanceExhaustedError):
        runner.consume_invocation(request, tmp_path)


def test_cli_failure_detail_excludes_generated_text() -> None:
    events = b'{"type":"item.completed","item":{"text":"private source"}}\n{"type":"turn.failed","error":{"message":"model unavailable"}}\n'
    assert runner.cli_failure_detail(events, b"Reading prompt from stdin") == "model unavailable"


def test_bubblewrap_uses_only_the_pinned_root_owned_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = tmp_path / "opt" / "tubeforge-codex-runner" / "codex-runtime"
    node = runtime / "node" / "bin" / "node"
    entrypoint = runtime / "lib" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
    node.parent.mkdir(parents=True)
    entrypoint.parent.mkdir(parents=True)
    node.write_text("", encoding="utf-8")
    entrypoint.write_text("", encoding="utf-8")
    bwrap = tmp_path / "bwrap"
    bwrap.write_text("", encoding="utf-8")
    codex_home = tmp_path / "private-codex-home"
    codex_home.mkdir()
    workspace = tmp_path / "work"
    workspace.mkdir()
    monkeypatch.setattr(runner, "CODEX_RUNTIME", runtime)
    monkeypatch.setattr(runner, "CODEX_NODE", node)
    monkeypatch.setattr(runner, "CODEX_ENTRYPOINT", entrypoint)
    monkeypatch.setattr(runner, "CODEX_HOME", codex_home)
    monkeypatch.setattr(runner, "BWRAP", str(bwrap))

    args = runner.bubblewrap_args(workspace)

    assert str(node) in args and str(entrypoint) in args
    assert str(runtime) in args
    assert "/home/uditaswal" not in " ".join(args)
    assert "/codex-home" in args
    assert "--unshare-all" in args and "--share-net" in args
    assert {"--ignore-user-config", "--ignore-rules", "--skip-git-repo-check"}.issubset(args)
    assert args[args.index("--model") + 1] == "gpt-5.6-sol"
    assert "/usr" not in args and "/bin" not in args
    assert "/etc/resolv.conf" in args
    assert "/etc/ssl/certs" in args
    assert args[args.index("--setenv") + 2] == "/tmp"
    assert "codex" not in args[args.index("--") + 1 :]


def test_runtime_contract_matches_the_fixed_bubblewrap_layout() -> None:
    repository = Path(__file__).resolve().parents[1]
    instructions = (repository / "docs" / "tubeforge-codex-runner-runtime.md").read_text(encoding="utf-8")
    unit = (repository / "docs" / "tubeforge-codex-runner.service").read_text(encoding="utf-8")

    assert "/opt/tubeforge-codex-runner/codex-runtime/node/bin/node" in instructions
    assert "@openai/codex@0.149.0" in instructions
    assert "--prefix /opt/tubeforge-codex-runner/codex-runtime" in instructions
    assert "/home/uditaswal/.nvm" not in instructions + unit
    assert "ReadOnlyPaths=/opt/tubeforge-codex-runner/codex-runtime" in unit


def test_non_worker_peer_is_rejected_before_request_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    left, right = socket.socketpair()
    try:
        monkeypatch.setattr(runner, "peer_uid", lambda _connection: 999)
        with pytest.raises(PermissionError, match="UID 1000"):
            runner.receive_request(left)
    finally:
        left.close()
        right.close()


def test_production_content_selection_uses_the_typed_host_runner(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'runner.db'}"))
    Base.metadata.create_all(database.engine)
    try:
        settings = Settings.model_validate(
            {
                "app": {"name": "x", "environment": "production"},
                "database": {"url": f"sqlite:///{tmp_path / 'runner.db'}"},
                "pipeline": {
                    "content_provider": "codex",
                    "codex": {"socket_path": "/run/tubeforge-codex/codex.sock"},
                },
            }
        )
        provider = create_content_provider(settings, database.session_factory)
        assert isinstance(provider, HostRunnerContentProvider)
        assert provider.config.model == "gpt-5.6-sol"
        assert provider.config.socket_path == Path("/run/tubeforge-codex/codex.sock")
    finally:
        database.dispose()


def test_unsupported_prompt_does_not_consume_a_generation_attempt(tmp_path: Path) -> None:
    database = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'preflight.db'}"))
    Base.metadata.create_all(database.engine)
    try:
        request = caption_timing_request().request.model_copy(update={"prompt_version": "unsupported-brief"})
        provider = HostRunnerContentProvider(
            CodexProviderConfig(),
            GenerationCacheRepository(database.session_factory),
            transport=lambda *_args: pytest.fail("invalid prompt reached host runner"),
        )
        with pytest.raises(ValueError, match="unsupported Codex content prompt template"):
            provider.generate_package(request)
        with database.session_factory() as session:
            assert session.scalar(select(func.count()).select_from(GenerationCacheRecord)) == 0
    finally:
        database.dispose()
