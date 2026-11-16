from __future__ import annotations

import socket

from tubeforge import host_claude_runner


def test_a_client_that_hangs_up_without_a_request_does_not_stop_the_runner() -> None:
    # Reproduces the crash: an empty connection made receive_request fail, and the error reply then hit a closed
    # socket (BrokenPipeError) that was not caught, which ended the whole runner process.
    server_side, client_side = socket.socketpair()
    client_side.close()
    host_claude_runner.serve_connection(server_side, None)  # must return normally


def test_a_client_that_hangs_up_before_the_reply_is_tolerated(monkeypatch) -> None:
    server_side, client_side = socket.socketpair()
    client_side.close()
    monkeypatch.setattr(host_claude_runner, "receive_request", lambda connection: (_ for _ in ()).throw(ValueError("boom")))
    host_claude_runner.serve_connection(server_side, None)


def test_reference_preflight_matches_claude_worker_contract(monkeypatch, tmp_path) -> None:
    from test_reference_content import candidate
    from tubeforge.db.session import create_database
    from tubeforge.db.models import Base
    from tubeforge.db.repositories import GenerationCacheRepository
    from tubeforge.core.config import DatabaseConfig
    from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest
    from tubeforge.providers.content.host_runner import HostRunnerContentProvider
    from tubeforge.core.config import CodexProviderConfig

    request, _, _ = candidate()
    monkeypatch.setattr(host_claude_runner, "claude_binary", lambda: "/fake/claude")
    readiness = host_claude_runner.handle(GenerateShortsScriptRequest(operation="PreflightContentV1", request=request), None)
    db = create_database(DatabaseConfig(url=f"sqlite:///{tmp_path / 'preflight.db'}"))
    Base.metadata.create_all(db.engine)
    try:
        provider = HostRunnerContentProvider(CodexProviderConfig(), GenerationCacheRepository(db.session_factory))
        provider.script_owner = "claude"
        provider._require_reference_preflight(request, readiness)
    finally:
        db.dispose()
