import json
import logging
import os
import time

import pytest

from tubeforge.core import app_logging
from tubeforge.core.app_logging import JsonFormatter, RotatingLogHandler, job_context, redact


@pytest.fixture
def logger(tmp_path, request):
    handler = RotatingLogHandler(tmp_path, "svc", max_bytes=400 if "rotates" in request.node.name else 100_000, retention_days=5)
    handler.setFormatter(JsonFormatter("svc"))
    log = logging.getLogger("rotation-test")
    log.handlers, log.propagate = [handler], False
    log.setLevel(logging.INFO)
    yield log, tmp_path, handler
    handler.close()


def test_rotates_to_numbered_log_files(logger):
    log, directory, _ = logger
    for index in range(30):
        log.info("line %s %s", index, "x" * 40)
    names = sorted(path.name for path in directory.iterdir())
    assert "svc.log" in names and "svc.1.log" in names and "svc.2.log" in names
    assert not any(name.startswith("svc.log.") for name in names)
    assert all(json.loads(line)["service"] == "svc" for line in (directory / "svc.1.log").read_text().splitlines())


def test_purges_rotated_files_older_than_retention(logger):
    log, directory, handler = logger
    old, fresh = directory / "svc.7.log", directory / "svc.1.log"
    for path in (old, fresh):
        path.write_text("{}\n")
    stale = time.time() - 6 * 86400
    os.utime(old, (stale, stale))
    handler.purge()
    assert not old.exists() and fresh.exists()


def test_structured_fields_job_id_and_event_flattening(logger):
    log, directory, handler = logger
    with job_context("job-123"):
        log.info(json.dumps({"event": "job_claimed", "state": "QUEUED"}))
        log.info("http", extra={"event": "http_request", "status": 502, "duration_ms": 12.5})
    handler.flush()
    first, second = [json.loads(line) for line in (directory / "svc.log").read_text().splitlines()]
    assert first["event"] == "job_claimed" and first["job_id"] == "job-123" and first["state"] == "QUEUED"
    assert second["status"] == 502 and second["duration_ms"] == 12.5 and "rss_mb" in second


def test_exceptions_logged_with_traceback_and_type(logger):
    log, directory, handler = logger
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("failed")
    handler.flush()
    record = json.loads((directory / "svc.log").read_text().splitlines()[0])
    assert record["error_type"] == "ValueError" and "boom" in record["traceback"]


@pytest.mark.parametrize("secret", [
    "Authorization: Bearer abcdefghijklmnop12345",
    "password=hunter2hunter2",
    "https://x.test/cb?code=4/0AbCdEfG&state=zzz",
    "key sk-abcdefghijklmnop1234567890",
    "ya29.a0AfH6SMBxxxxxxxxxxxxxxxx",
    "token " + ".".join(["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0In0", "abcdefghijk"]),
])
def test_redacts_secrets(secret):
    cleaned = redact(secret)
    assert "[REDACTED]" in cleaned
    for leaked in ("abcdefghijklmnop12345", "hunter2", "4/0AbCdEfG", "zzz", "sk-abcdefghijklmnop", "ya29.a0", "eyJhbGci"):
        assert leaked not in cleaned


def test_sensitive_extra_keys_redacted_but_token_counts_kept(logger):
    log, directory, handler = logger
    log.info("x", extra={"api_key": "abc", "tokens_used": 1200, "job_state": "RENDERING_PREVIEW"})
    handler.flush()
    record = json.loads((directory / "svc.log").read_text().splitlines()[0])
    assert record["api_key"] == "[REDACTED]" and record["tokens_used"] == 1200 and record["job_state"] == "RENDERING_PREVIEW"


def test_process_stats_reports_memory():
    assert app_logging.process_stats()["rss_mb"] > 0
