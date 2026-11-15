#!/usr/bin/env python3
"""Loopback-only HTTPS front for the dashboard so Meta accepts an https redirect URI.

Run on the machine where you open the browser (the SSH tunnel forwards 62065 to it):
    python scripts/local_tls_proxy.py            # temporary loopback TLS front
The certificate is self-signed for localhost and is created under data/run/tls (git-ignored);
accept the browser warning once. Sign in to Studio through this origin before connecting
Instagram, because the session cookie belongs to the origin that set it.
"""
from __future__ import annotations

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import ssl
import subprocess
import sys

UPSTREAM = (os.environ.get("TUBEFORGE_TLS_UPSTREAM_HOST", "127.0.0.1"), int(os.environ.get("TUBEFORGE_TLS_UPSTREAM_PORT", "62065")))
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding", "upgrade"}


class Proxy(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
        headers["X-Forwarded-Proto"] = "https"
        connection = http.client.HTTPConnection(*UPSTREAM, timeout=120)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in HOP and key.lower() != "content-length":
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except OSError:
            self.send_error(502, "dashboard is not reachable")
        finally:
            connection.close()

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _forward

    def log_message(self, *args: object) -> None:  # request lines can carry OAuth codes
        return


def certificate(directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    cert, key = directory / "localhost.crt", directory / "localhost.key"
    if not cert.is_file() or not key.is_file():
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "365", "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1", "-keyout", str(key), "-out", str(cert)], check=True, capture_output=True)
        key.chmod(0o600)
    return cert, key


def serve(port: int, cert: Path, key: Path) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Proxy)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    server.socket = context.wrap_socket(server.socket, server_side=True)
    return server


if __name__ == "__main__":
    port = int(os.environ.get("TUBEFORGE_TLS_PORT", "0"))
    cert, key = certificate(Path(os.environ.get("TUBEFORGE_TLS_DIR", "data/run/tls")))
    server = serve(port, cert, key)
    print(f"Temporary TLS front on localhost port {server.server_port} (Ctrl+C to stop)", file=sys.stderr)
    server.serve_forever()
