import socket
import pytest

import tubeforge.host_claude_runner as runner
from tubeforge.claude_budget import BudgetExceededError
from tubeforge.providers.content.host_runner_protocol import HostRunnerResponse


def _serve(monkeypatch, raising):
    """Run serve_connection against a socketpair whose request handler raises `raising`."""
    left, right = socket.socketpair()
    monkeypatch.setattr(runner, "receive_request", lambda connection: type("R", (), {"operation": "GenerateShortsScriptV1"})())
    def boom(request, model):
        raise raising
    monkeypatch.setattr(runner, "handle", boom)
    runner.serve_connection(left, None)
    data = right.recv(65536)
    right.close()
    return HostRunnerResponse.model_validate_json(data).failure


@pytest.mark.parametrize("error,code,started", [
    (BudgetExceededError("daily call cap reached"), "quota_exhausted", False),
    (runner.RunnerUnavailableError("Claude CLI not found"), "runner_unavailable", False),
    (PermissionError("runner accepts only the operator's own UID"), "authentication_failed", False),
    (RuntimeError("Claude CLI reported an error: rate limit reached"), "invalid_output", True),   # message text is never read as a quota signal
    (TimeoutError("too slow"), "timeout", True),
])
def test_runner_failures_use_structured_codes(monkeypatch, error, code, started):
    failure = _serve(monkeypatch, error)
    assert failure.code == code and failure.invocation_started is started


def test_a_missing_cli_binary_is_runner_unavailable(monkeypatch):
    monkeypatch.delenv("TUBEFORGE_CLAUDE_BIN", raising=False)
    monkeypatch.setattr(runner.shutil, "which", lambda name: None)
    monkeypatch.setattr(runner.glob, "glob", lambda pattern: [])
    with pytest.raises(runner.RunnerUnavailableError):
        runner.claude_binary()


def test_an_unlaunchable_cli_is_runner_unavailable_and_the_budget_cap_is_quota(monkeypatch):
    monkeypatch.setattr(runner.BUDGET, "check", lambda: None)
    monkeypatch.setattr(runner.BUDGET, "record", lambda **kw: None)
    monkeypatch.setattr(runner, "build_command", lambda *a, **k: ["/nonexistent/claude"])
    with pytest.raises(runner.RunnerUnavailableError):
        runner.call_claude("p", {}, model="m")
