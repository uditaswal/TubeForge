"""Bounded yt-dlp source acquisition. No web server ever fetches a URL directly."""

from __future__ import annotations

import ipaddress
import json
import subprocess
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from tubeforge.core.errors import ProviderValidationError, RetryableProviderError


class SourceProvider(Protocol):
    """Provider boundary for future YouTube, Kick, Twitch, and direct media."""

    def can_handle(self, url: str) -> bool: ...
    def inspect(self, url: str) -> dict[str, object]: ...
    def acquire(self, url: str, destination: Path, *, captions: bool = False) -> Path: ...


def validate_source_url(value: str) -> str:
    """Allow public HTTP(S) media URLs while rejecting local-network targets."""
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ProviderValidationError("source URL must be a public HTTP(S) URL without credentials")
    host = parsed.hostname.rstrip(".").casefold()
    if host == "localhost" or host.endswith(".localhost"):
        raise ProviderValidationError("local source URLs are not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return parsed.geturl()
    if not address.is_global:
        raise ProviderValidationError("private or reserved source IP addresses are not allowed")
    return parsed.geturl()


class YtDlpSourceProvider:
    """A subprocess adapter so acquisition is auditable and easy to mock."""

    def __init__(self, executable: str = "yt-dlp", timeout_seconds: int = 900) -> None:
        self.executable, self.timeout_seconds = executable, timeout_seconds

    def can_handle(self, url: str) -> bool:
        try:
            validate_source_url(url)
        except ProviderValidationError:
            return False
        return True

    def inspect(self, url: str) -> dict[str, object]:
        safe_url = validate_source_url(url)
        try:
            completed = subprocess.run(
                [self.executable, "--dump-single-json", "--no-playlist", "--no-warnings", "--socket-timeout", str(self.timeout_seconds), "--retries", "0", safe_url],
                text=True, capture_output=True, timeout=self.timeout_seconds, check=False,
            )
        except FileNotFoundError as error:
            raise ProviderValidationError("yt-dlp is not installed in the TubeForge worker image") from error
        except subprocess.TimeoutExpired as error:
            raise RetryableProviderError("source inspection timed out") from error
        if completed.returncode:
            raise ProviderValidationError(_diagnostic(completed.stderr, "source inspection failed"))
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise ProviderValidationError("yt-dlp returned invalid source metadata") from error
        duration = raw.get("duration")
        # Generic direct-media extractors often omit duration. The downloaded
        # local file is probed before analysis and becomes authoritative.
        duration_seconds = float(duration) if isinstance(duration, (int, float)) and duration > 0 else None
        return {"url": safe_url, "extractor": raw.get("extractor_key"), "id": raw.get("id"), "title": raw.get("title"), "uploader": raw.get("uploader"), "duration_seconds": duration_seconds, "webpage_url": raw.get("webpage_url") or safe_url}

    def acquire(self, url: str, destination: Path, *, captions: bool = False) -> Path:
        safe_url = validate_source_url(url)
        destination.mkdir(parents=True, exist_ok=True)
        output = destination / "source.%(ext)s"
        try:
            command = [self.executable, "--no-playlist", "--no-part", "--restrict-filenames", "--socket-timeout", str(self.timeout_seconds), "--retries", "0", "--paths", str(destination), "--output", str(output), "--format", "bv*+ba/b", "--merge-output-format", "mp4"]
            if captions:
                command.extend(["--write-auto-subs", "--sub-langs", "en", "--convert-subs", "srt"])
            completed = subprocess.run(
                [*command, safe_url],
                text=True, capture_output=True, timeout=self.timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RetryableProviderError("source acquisition timed out") from error
        if completed.returncode:
            raise ProviderValidationError(_diagnostic(completed.stderr, "source acquisition failed"))
        files = sorted(path for path in destination.glob("source.*") if path.is_file() and path.stat().st_size)
        if len(files) != 1:
            raise ProviderValidationError("source acquisition did not produce exactly one media file")
        return files[0]


def _diagnostic(stderr: str, fallback: str) -> str:
    line = next((part.strip() for part in stderr.splitlines()[::-1] if part.strip()), fallback)
    return line[:1000]
