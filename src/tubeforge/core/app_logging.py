"""Persistent, rotating, redacted JSON-lines application logs.

Each process writes ``<service>.log``; when it reaches the size threshold it is
renamed ``<service>.1.log`` (older ones shift to ``.2.log`` …) and a fresh
``<service>.log`` starts. Rotated files older than the retention window are
deleted, so the directory stays bounded.

Environment (all optional):
  TUBEFORGE_LOG_DIR             default <repo>/data/logs (git-ignored; /app/data/logs in Docker)
  TUBEFORGE_LOG_MAX_MB          size threshold per file, default 10
  TUBEFORGE_LOG_RETENTION_DAYS  default 5
  TUBEFORGE_LOG_LEVEL           default INFO
  TUBEFORGE_LOG_HEARTBEAT_SECONDS  process/memory sample interval, default 60 (0 disables)
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator

from tubeforge.core.config import REPOSITORY_ROOT

job_id_var: ContextVar[str | None] = ContextVar("tubeforge_log_job_id", default=None)
request_id_var: ContextVar[str | None] = ContextVar("tubeforge_log_request_id", default=None)

_SENSITIVE_KEY = re.compile(r"(pass(word|wd)?|secret|token|api[_-]?key|authorization|cookie|csrf|credential|private[_-]?key|session)", re.I)
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"), r"\1 [REDACTED]"),
    (re.compile(r"(?i)((?:pass(?:word|wd)?|secret|token|api[_-]?key|access_token|refresh_token|client_secret|authorization|cookie)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,;}]{3,}"), r"\1[REDACTED]"),
    (re.compile(r"\b(sk-[A-Za-z0-9_-]{12,}|ya29\.[A-Za-z0-9._-]{10,}|1//[A-Za-z0-9._-]{10,}|gh[pousr]_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{20,})"), "[REDACTED]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), "[REDACTED]"),
    (re.compile(r"(?i)([?&](?:key|token|code|state|access_token|api_key|client_secret)=)[^&\s]+"), r"\1[REDACTED]"),
)
_BENIGN_KEY = re.compile(r"(tokens?_(used|count|in|out|total)|(max|num|input|output|total)_tokens|session_hours|session_id_count)", re.I)
_STANDARD = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


def redact(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _clean(value: Any, key: str = "") -> Any:
    if key and _SENSITIVE_KEY.search(key) and not _BENIGN_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _clean(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, str):
        return redact(value)
    return value


def process_stats() -> dict[str, Any]:
    """Cheap Linux process sample without psutil: RSS, peak RSS, threads, open fds, CPU seconds."""
    stats: dict[str, Any] = {}
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                stats["rss_mb"] = round(int(line.split()[1]) / 1024, 1)
            elif line.startswith("VmHWM:"):
                stats["rss_peak_mb"] = round(int(line.split()[1]) / 1024, 1)
            elif line.startswith("Threads:"):
                stats["threads"] = int(line.split()[1])
        stats["open_fds"] = len(os.listdir("/proc/self/fd"))
    except OSError:
        pass
    stats["cpu_seconds"] = round(time.process_time(), 2)
    return stats


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str) -> None:
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self.service,
            "logger": record.name,
            "pid": record.process,
        }
        # Existing worker/orchestrator code logs ``json.dumps({"event": ...})``; flatten it.
        if message.startswith("{") and message.endswith("}"):
            try:
                parsed = json.loads(message)
            except ValueError:
                parsed = None
            if isinstance(parsed, dict) and "event" in parsed:
                payload.update(_clean(parsed))
                message = ""
        if message:
            payload["msg"] = redact(message)
        job_id = job_id_var.get()
        if job_id and "job_id" not in payload:
            payload["job_id"] = job_id
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        for key, value in record.__dict__.items():
            if key not in _STANDARD and key not in payload:
                payload[key] = _clean(value, key)
        if record.exc_info:
            payload["error_type"] = record.exc_info[0].__name__ if record.exc_info[0] else None
            payload["traceback"] = redact(self.formatException(record.exc_info))
        payload.update({k: v for k, v in process_stats().items() if k in {"rss_mb"} and "rss_mb" not in payload})
        return json.dumps(payload, default=str, ensure_ascii=False)


class RotatingLogHandler(RotatingFileHandler):
    """``svc.log`` → ``svc.1.log`` → ``svc.2.log`` …; rotated files expire by age."""

    def __init__(self, directory: Path, service: str, max_bytes: int, retention_days: float) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.service, self.directory, self.retention_seconds = service, directory, retention_days * 86400
        self._last_purge = 0.0
        super().__init__(directory / f"{service}.log", maxBytes=max_bytes, backupCount=200, encoding="utf-8", delay=True)
        self.namer = self._numbered_name
        self.purge()

    def _numbered_name(self, default_name: str) -> str:
        # RotatingFileHandler asks for "<service>.log.N"; we want "<service>.N.log".
        path = Path(default_name)
        match = re.fullmatch(rf"{re.escape(self.service)}\.log\.(\d+)", path.name)
        return str(path.with_name(f"{self.service}.{match.group(1)}.log")) if match else default_name

    def purge(self) -> None:
        cutoff = time.time() - self.retention_seconds
        for path in self.directory.glob(f"{self.service}.*.log"):
            if re.fullmatch(rf"{re.escape(self.service)}\.\d+\.log", path.name):
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink()
                except OSError:
                    pass
        self._last_purge = time.time()

    def doRollover(self) -> None:
        super().doRollover()
        self.purge()

    def emit(self, record: logging.LogRecord) -> None:
        # A quiet service may never roll over, so also purge hourly.
        if time.time() - self._last_purge > 3600:
            self.purge()
        super().emit(record)


_configured: dict[str, str] = {}


def configure_logging(service: str) -> Path:
    """Attach the rotating JSON file handler (plus stderr) to the root logger. Idempotent."""
    log_dir = Path(os.environ.get("TUBEFORGE_LOG_DIR") or REPOSITORY_ROOT / "data" / "logs")
    if _configured.get("service") == service:
        return log_dir
    level = getattr(logging, os.environ.get("TUBEFORGE_LOG_LEVEL", "INFO").upper(), logging.INFO)
    max_bytes = int(float(os.environ.get("TUBEFORGE_LOG_MAX_MB", "10")) * 1024 * 1024)
    retention = float(os.environ.get("TUBEFORGE_LOG_RETENTION_DAYS", "5"))
    formatter = JsonFormatter(service)
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, "_tubeforge", False):
            root.removeHandler(handler)
    file_handler = RotatingLogHandler(log_dir, service, max_bytes, retention)
    stream = logging.StreamHandler()  # keep `docker compose logs` useful, same JSON shape
    for handler in (file_handler, stream):
        handler.setFormatter(formatter)
        handler._tubeforge = True  # type: ignore[attr-defined]
        root.addHandler(handler)
    # uvicorn installs its own handlers; route its records through ours instead.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        named = logging.getLogger(name)
        named.handlers.clear()
        named.propagate = True
    _configured["service"] = service
    logging.getLogger(__name__).info(
        "logging_started", extra={"event": "logging_started", "log_dir": str(log_dir), "max_mb": max_bytes / 1048576, "retention_days": retention}
    )
    _instrument_outbound_http()
    _start_heartbeat()
    return log_dir


def _instrument_outbound_http() -> None:
    """Log every outbound urllib/httpx call: host, path (no query), status code, duration."""
    import urllib.error
    import urllib.parse
    import urllib.request

    log = logging.getLogger("tubeforge.outbound")

    def record(method: str, url: str, status: int | None, started: float, error: str | None = None) -> None:
        parts = urllib.parse.urlsplit(str(url))
        failed = error is not None or (status or 0) >= 400
        log.log(logging.WARNING if failed else logging.INFO, "outbound_http", extra={
            "event": "outbound_http", "method": method, "host": parts.hostname, "path": parts.path, "status": status,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1), **({"error": error} if error else {}),
        })

    if not getattr(urllib.request.OpenerDirector.open, "_tubeforge", False):
        original = urllib.request.OpenerDirector.open

        def open_logged(self, fullurl, data=None, timeout=None):  # type: ignore[no-untyped-def]
            url = fullurl if isinstance(fullurl, str) else fullurl.full_url
            method = "GET" if data is None and not hasattr(fullurl, "get_method") else getattr(fullurl, "get_method", lambda: "POST")()
            started = time.perf_counter()
            try:
                response = original(self, fullurl, data, timeout) if timeout is not None else original(self, fullurl, data)
            except urllib.error.HTTPError as error:
                record(method, url, error.code, started, error=f"HTTPError {error.code}")
                raise
            except Exception as error:
                record(method, url, None, started, error=type(error).__name__)
                raise
            record(method, url, getattr(response, "status", None), started)
            return response

        open_logged._tubeforge = True  # type: ignore[attr-defined]
        urllib.request.OpenerDirector.open = open_logged  # type: ignore[method-assign]

    try:
        import httpx
    except ImportError:
        return
    if not getattr(httpx.Client.send, "_tubeforge", False):
        original_send = httpx.Client.send

        def send_logged(self, request, **kwargs):  # type: ignore[no-untyped-def]
            started = time.perf_counter()
            try:
                response = original_send(self, request, **kwargs)
            except Exception as error:
                record(request.method, str(request.url), None, started, error=type(error).__name__)
                raise
            record(request.method, str(request.url), response.status_code, started)
            return response

        send_logged._tubeforge = True  # type: ignore[attr-defined]
        httpx.Client.send = send_logged  # type: ignore[method-assign]


def _start_heartbeat() -> None:
    interval = float(os.environ.get("TUBEFORGE_LOG_HEARTBEAT_SECONDS", "60"))
    if interval <= 0:
        return
    def loop() -> None:
        log = logging.getLogger("tubeforge.process")
        while True:
            time.sleep(interval)
            log.info("process_stats", extra={"event": "process_stats", **process_stats()})
    threading.Thread(target=loop, name="log-heartbeat", daemon=True).start()


@contextmanager
def job_context(job_id: str) -> Iterator[None]:
    token = job_id_var.set(job_id)
    try:
        yield
    finally:
        job_id_var.reset(token)


@contextmanager
def timed(logger: logging.Logger, event: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Log ``event`` with ``duration_ms`` (and ``status: error`` + the exception) on exit."""
    extra: dict[str, Any] = dict(fields)
    started = time.perf_counter()
    try:
        yield extra
    except Exception:
        extra["status"] = "error"
        logger.exception(event, extra={"event": event, "duration_ms": round((time.perf_counter() - started) * 1000, 1), **extra})
        raise
    else:
        logger.info(event, extra={"event": event, "duration_ms": round((time.perf_counter() - started) * 1000, 1), **extra})
