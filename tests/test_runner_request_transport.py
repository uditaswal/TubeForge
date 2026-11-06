"""Local socket and pre-invocation evidence limits; no writer processes."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from tubeforge.core.config import CodexProviderConfig
from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import ContentRequest
from tubeforge.providers.content.host_runner import HostRunnerContentProvider, _request
from tubeforge.providers.content.factory import ClaudeHostRunnerContentProvider
from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest, encode_request, receive_message


def brief(owner='codex', *, oversized=False):
    raw = json.loads((Path(__file__).parent / 'fixtures/long_form/planning_contract.json').read_text())['request']
    raw['script_owner'] = owner
    if oversized:
        raw['sources'][0]['excerpt'] = '界' * 24000
    return ContentRequest.model_validate(raw)


class FragmentedSocket:
    def __init__(self, connection):
        self.connection = connection
        self.reads = 0

    def recv(self, count):
        self.reads += 1
        return self.connection.recv(min(count, 7))

    def __getattr__(self, name):
        return getattr(self.connection, name)


@pytest.mark.parametrize('owner', ['codex', 'claude'])
def test_both_runners_read_fragmented_unicode_and_legacy_clients(monkeypatch, owner):
    from tubeforge import host_codex_runner, host_claude_runner
    runner = host_codex_runner if owner == 'codex' else host_claude_runner
    monkeypatch.setattr(runner, 'peer_uid', lambda connection: runner.WORKER_UID if owner == 'codex' else os.getuid())
    raw = brief(owner).model_dump(mode='json')
    raw['sources'][0]['excerpt'] = 'Fragments include 中文 and escaped quotes " safely.'
    message = GenerateShortsScriptRequest(request=ContentRequest.model_validate(raw))
    left, right = socket.socketpair()
    with left, right:
        left.settimeout(1)
        right.sendall(encode_request(message))  # no EOF: deployed legacy worker behavior
        fragmented = FragmentedSocket(left)
        assert runner.receive_request(fragmented) == message
        assert fragmented.reads > 1
        assert left.gettimeout() == 1


@pytest.mark.parametrize('suffix', [b'', b' '])
def test_complete_request_at_byte_boundary(suffix):
    message = GenerateShortsScriptRequest(request=brief())
    payload = encode_request(message) + suffix
    left, right = socket.socketpair()
    with left, right:
        right.sendall(payload)
        right.shutdown(socket.SHUT_WR)
        assert receive_message(left, maximum_bytes=len(payload)) == message


def test_over_limit_request_is_rejected_during_fragmented_receive():
    payload = encode_request(GenerateShortsScriptRequest(request=brief()))
    left, right = socket.socketpair()
    with left, right:
        right.sendall(payload)
        with pytest.raises(ValueError, match='exceeds'):
            receive_message(FragmentedSocket(left), maximum_bytes=len(payload)-1)


@pytest.mark.parametrize('payload', [b'', b'{"operation":', b'{broken json'])
def test_missing_or_truncated_request_fails_on_eof(payload):
    left, right = socket.socketpair()
    with left, right:
        right.sendall(payload)
        right.shutdown(socket.SHUT_WR)
        with pytest.raises((ValueError, ValidationError)):
            receive_message(left)


def test_incomplete_message_has_bounded_read_time_and_restores_socket_timeout():
    left, right = socket.socketpair()
    with left, right:
        right.sendall(b'{')
        assert left.gettimeout() is None
        with pytest.raises(ValueError, match='timed out'):
            receive_message(left, timeout_seconds=0.01)
        assert left.gettimeout() is None


@pytest.mark.parametrize('provider_type,owner', [(HostRunnerContentProvider,'codex'), (ClaudeHostRunnerContentProvider,'claude')])
@pytest.mark.parametrize('operation', ['generate_package', 'research_sources'])
def test_oversize_evidence_never_contacts_runner_or_reserves_attempt(provider_type, owner, operation):
    cache = Mock()
    cache.accepted.return_value = None
    transport = Mock(side_effect=AssertionError('must not contact runner'))
    provider = provider_type(CodexProviderConfig(), cache, transport=transport)
    with pytest.raises(ProviderValidationError, match='UTF-8 bytes'):
        getattr(provider, operation)(brief(owner, oversized=True))
    transport.assert_not_called()
    cache.reserve_or_get.assert_not_called()
    cache.consume_invocation.assert_not_called()


@pytest.mark.parametrize("wait_for_eof", [False, True])
def test_worker_transport_supports_legacy_complete_json_and_write_eof(tmp_path, wait_for_eof):
    path = str(tmp_path / 'runner.sock')
    payload = encode_request(GenerateShortsScriptRequest(request=brief()))
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(path)
        listener.listen(1)
        listener.settimeout(2)
        def legacy_server():
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(2)
                chunks = []
                while chunk := connection.recv(128):
                    chunks.append(chunk)
                    if not wait_for_eof:
                        try:
                            json.loads(b''.join(chunks))
                        except json.JSONDecodeError:
                            continue
                        break
                assert b''.join(chunks) == payload
                connection.sendall(b'{"ok":true}')
        with ThreadPoolExecutor(max_workers=1) as pool:
            server = pool.submit(legacy_server)
            assert _request(path, payload, 2) == b'{"ok":true}'
            server.result(timeout=3)


@pytest.mark.parametrize('owner', ['codex', 'claude'])
def test_peer_authorization_happens_before_any_read(monkeypatch, owner):
    from tubeforge import host_codex_runner, host_claude_runner
    runner = host_codex_runner if owner == 'codex' else host_claude_runner
    monkeypatch.setattr(runner, 'peer_uid', lambda connection: -1)
    connection = Mock()
    with pytest.raises(PermissionError):
        runner.receive_request(connection)
    connection.recv.assert_not_called()
    connection.gettimeout.assert_not_called()


def test_encoder_enforces_exact_utf8_boundary(monkeypatch):
    from tubeforge.providers.content import host_runner_protocol as protocol
    message = GenerateShortsScriptRequest(request=brief())
    payload = message.model_dump_json().encode('utf-8')
    monkeypatch.setattr(protocol, 'MAX_REQUEST_BYTES', len(payload))
    assert encode_request(message) == payload
    monkeypatch.setattr(protocol, 'MAX_REQUEST_BYTES', len(payload)-1)
    with pytest.raises(ProviderValidationError, match='UTF-8 bytes'):
        encode_request(message)
