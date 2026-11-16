"""The loopback TLS front relays requests, cookies and redirects to the dashboard unchanged."""
from __future__ import annotations

import importlib.util
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread

import httpx
import pytest


def test_proxy_relays_over_tls(tmp_path: Path, monkeypatch) -> None:
    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            payload = body + b"|" + (self.headers.get("X-Forwarded-Proto") or "").encode()
            self.send_response(200)
            self.send_header("Set-Cookie", "tubeforge_session=abc; Path=/")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args) -> None:
            return

    upstream = HTTPServer(("127.0.0.1", 0), Upstream)
    Thread(target=upstream.serve_forever, daemon=True).start()
    monkeypatch.setenv("TUBEFORGE_TLS_UPSTREAM_PORT", str(upstream.server_port))
    spec = importlib.util.spec_from_file_location("local_tls_proxy", Path(__file__).resolve().parents[1] / "scripts" / "local_tls_proxy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        cert, key = module.certificate(tmp_path / "tls")
    except (OSError, Exception) as error:  # openssl missing
        pytest.skip(f"openssl unavailable: {error}")
    server = module.serve(0, cert, key)
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        response = httpx.post(f"https://127.0.0.1:{server.server_port}/x", content=b"hello", verify=str(cert))
        assert response.status_code == 200 and response.content == b"hello|https"
        assert response.headers["set-cookie"].startswith("tubeforge_session=abc")
    finally:
        server.shutdown()
        upstream.shutdown()
