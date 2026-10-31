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
