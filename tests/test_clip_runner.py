"""The clip engine's AI path: typed request, worker transport and the host runner's limits."""
import asyncio
import json
import socket
import time

import pytest

from tubeforge import host_claude_runner as runner
from tubeforge.claude_budget import BudgetExceededError, ClaudeBudget
from tubeforge.clips.runner_model import RunnerError
from tubeforge.providers.content.clip_runner import ClipRunnerTransport
from tubeforge.providers.content.host_runner_protocol import CLIP_PROMPT_MAX_CHARS, ClipCompletionRequest, HostRunnerResponse, HostRunnerSuccess


@pytest.fixture
def budget(tmp_path, monkeypatch):
    value = ClaudeBudget(tmp_path / "ledger.jsonl", max_calls=10, max_usd=8.0, max_usd_per_call=1.5)
    monkeypatch.setattr(runner, "BUDGET", value)
    monkeypatch.setattr(runner, "CLIP_CALLS_PER_DAY", 2)
    return value


def fake_claude(monkeypatch, answer=None):
    seen = []

    def call_claude(prompt, schema, *, model, effort=None, web_search=False, label="launch"):
        runner.BUDGET.record(usd=None, label=label)
        seen.append({"prompt": prompt, "schema": schema, "model": model, "label": label, "web_search": web_search})
        return answer or {"ok": True}, {"total_cost_usd": 0.01}

    monkeypatch.setattr(runner, "call_claude", call_claude)
    return seen


def test_the_request_is_bounded_and_carries_no_command_path_or_model():
    request = ClipCompletionRequest(prompt="transcript", output_schema={"type": "object"})
    assert set(request.model_dump()) == {"operation", "system", "prompt", "output_schema"}
    with pytest.raises(ValueError):
        ClipCompletionRequest(prompt="x" * (CLIP_PROMPT_MAX_CHARS + 1))
    with pytest.raises(ValueError):
        ClipCompletionRequest(prompt="x", model="opus")  # type: ignore[call-arg]


def test_a_clip_completion_is_tool_less_labelled_and_counted(budget, monkeypatch):
    seen = fake_claude(monkeypatch, {"segments": []})
    result = runner.handle(ClipCompletionRequest(system="sys", prompt="pick moments", output_schema={"type": "object"}), None)
    assert result.package == {"segments": []}
    assert seen[0]["label"] == "clips" and not seen[0]["web_search"] and seen[0]["prompt"].startswith("sys")
    assert runner.clip_calls_used() == 1


def test_the_clip_sub_limit_stops_calls_before_the_shared_limit(budget, monkeypatch):
    fake_claude(monkeypatch)
    for _ in range(2):
        runner.handle(ClipCompletionRequest(prompt="p"), None)
    with pytest.raises(BudgetExceededError, match="Clip selection daily call limit"):
        runner.handle(ClipCompletionRequest(prompt="p"), None)
    budget.check()  # the shared limit (10) still has room, so Shorts are unaffected


def test_script_calls_do_not_use_up_the_clip_sub_limit(budget, monkeypatch):
    budget.record(usd=None, label="launch")
    budget.record(usd=None, label="launch")
    assert runner.clip_calls_used() == 0


def test_the_socket_dispatches_clip_requests_and_answers(budget, monkeypatch):
    fake_claude(monkeypatch, {"answer": 1})
    client, server = socket.socketpair()
    client.sendall(ClipCompletionRequest(prompt="hello").model_dump_json().encode())
    runner.serve_connection(server, None)
    response = HostRunnerResponse.model_validate_json(client.recv(65_536))
    assert response.ok and response.result.package == {"answer": 1}


def test_the_socket_reports_the_clip_limit_as_a_structured_failure(budget, monkeypatch):
    fake_claude(monkeypatch)
    monkeypatch.setattr(runner, "CLIP_CALLS_PER_DAY", 0)
    client, server = socket.socketpair()
    client.sendall(ClipCompletionRequest(prompt="hello").model_dump_json().encode())
    runner.serve_connection(server, None)
    response = HostRunnerResponse.model_validate_json(client.recv(65_536))
    assert not response.ok and response.failure.code == "quota_exhausted" and response.failure.invocation_started is False


def test_the_worker_transport_sends_a_typed_request_and_returns_json(tmp_path):
    sent = []

    def call(path, payload, timeout):
        sent.append((path, ClipCompletionRequest.model_validate_json(payload)))
        return HostRunnerResponse(ok=True, result=HostRunnerSuccess(package={"a": 1})).model_dump_json().encode()

    transport = ClipRunnerTransport(tmp_path / "claude.sock", call=call)
    assert json.loads(asyncio.run(transport("sys", "prompt", {"type": "object"}))) == {"a": 1}
    assert sent[0][1].prompt == "prompt" and sent[0][1].output_schema == {"type": "object"}


def test_the_worker_transport_refuses_an_oversized_prompt_and_reports_failures(tmp_path):
    transport = ClipRunnerTransport(tmp_path / "claude.sock", call=lambda *args: b"")
    with pytest.raises(RunnerError, match="characters"):
        asyncio.run(transport("", "x" * (CLIP_PROMPT_MAX_CHARS + 1), None))

    def refuse(path, payload, timeout):
        return HostRunnerResponse(ok=False, failure={"code": "quota_exhausted", "message": "limit", "invocation_started": False}).model_dump_json().encode()

    with pytest.raises(RunnerError, match="quota_exhausted"):
        asyncio.run(ClipRunnerTransport(tmp_path / "claude.sock", call=refuse)("", "p", None))

    def unreachable(path, payload, timeout):
        raise ConnectionRefusedError()

    with pytest.raises(RunnerError, match="not reachable"):
        asyncio.run(ClipRunnerTransport(tmp_path / "claude.sock", call=unreachable)("", "p", None))
