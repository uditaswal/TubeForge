"""Source URL validation and metadata inspection. No web server ever fetches a URL directly."""

from __future__ import annotations

import ipaddress
import json
import shutil
import subprocess
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from tubeforge.core.errors import ProviderValidationError, RetryableProviderError


class SourceProvider(Protocol):
    """Provider boundary for future YouTube, Kick, Twitch, and direct media."""

    def can_handle(self, url: str) -> bool: ...
    def inspect(self, url: str) -> dict[str, object]: ...


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

    def __init__(self, executable: str = "yt-dlp", timeout_seconds: int = 900, cookies_file: Path | str | None = None) -> None:
        self.executable, self.timeout_seconds = executable, timeout_seconds
        self.cookies_file = Path(cookies_file) if cookies_file else None

    def _extra_arguments(self) -> list[str]:
        """A JavaScript runtime for YouTube's player challenge, and the operator's cookies when they exist."""
        arguments: list[str] = []
        if not shutil.which("deno") and shutil.which("node"):
            arguments += ["--js-runtimes", "node", "--remote-components", "ejs:github"]
        if self.cookies_file is not None and self.cookies_file.is_file():
            arguments += ["--cookies", str(self.cookies_file)]
        return arguments

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
                [self.executable, "--dump-single-json", "--no-playlist", "--no-warnings", "--socket-timeout", str(self.timeout_seconds), "--retries", "0", *self._extra_arguments(), safe_url],
                text=True, capture_output=True, timeout=self.timeout_seconds, check=False,
            )
        except FileNotFoundError as error:
            raise ProviderValidationError("yt-dlp is not installed in the TubeForge worker image") from error
        except subprocess.TimeoutExpired as error:
            raise RetryableProviderError("source inspection timed out") from error
        if completed.returncode:
            if "sign in to confirm" in completed.stderr.replace("\u2019", "'").lower():
                have = self.cookies_file is not None and self.cookies_file.is_file()
                raise ProviderValidationError(("YouTube still asked to confirm this is not a bot even with your cookies: they may have expired; export them again. " if have else "YouTube asked to confirm this is not a bot. Export your YouTube cookies from a logged-in browser as a Netscape cookies.txt file, save it as data/config/youtube-cookies.txt, and retry (see docs/clips.md).") )
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


def _diagnostic(stderr: str, fallback: str) -> str:
    line = next((part.strip() for part in stderr.splitlines()[::-1] if part.strip()), fallback)
    return line[:1000]
