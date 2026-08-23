"""Bounded, provenance-preserving ingestion of operator-supplied web sources."""

from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from tubeforge.core.errors import ProviderValidationError, RetryableProviderError
from tubeforge.domain.contracts import SourceReference


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Immutable, bounded evidence passed to a content provider as untrusted data."""

    source_id: str
    url: str
    title: str
    retrieved_at: datetime
    content_sha256: str
    excerpt: str
    author: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "title": self.title,
            "retrieved_at": self.retrieved_at.isoformat(),
            "content_sha256": self.content_sha256,
            "excerpt": self.excerpt,
            "author": self.author,
            "untrusted": True,
        }

    def as_reference(self) -> SourceReference:
        """Convert a verified snapshot into the content-provider contract."""
        return SourceReference(
            source_id=self.source_id,
            url=self.url,
            title=self.title,
            author=self.author,
            retrieved_at=self.retrieved_at,
            content_sha256=self.content_sha256,
            excerpt=self.excerpt,
        )


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            self.parts.append(data)


class _RejectRedirects(HTTPRedirectHandler):
    """Prevent an allowlisted source URL from pivoting to another host."""

    def redirect_request(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ProviderValidationError("source redirects are not permitted")


class SourceIngestor:
    """Fetch and normalize public text without following redirects or private hosts."""

    def __init__(self, allowed_hosts: frozenset[str], *, max_bytes: int = 2_000_000, max_chars: int = 24_000, timeout_seconds: int = 20) -> None:
        self.allowed_hosts = frozenset(host.casefold() for host in allowed_hosts)
        self.max_bytes, self.max_chars, self.timeout_seconds = max_bytes, max_chars, timeout_seconds
        self._opener = build_opener(_RejectRedirects())

    def ingest(self, source: SourceReference) -> SourceSnapshot:
        parsed = urlparse(str(source.url))
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or not host or parsed.username or parsed.password or parsed.port not in {None, 443}:
            raise ProviderValidationError("source URL must be an HTTPS URL without credentials or a custom port")
        if host not in self.allowed_hosts or self._is_private(host):
            raise ProviderValidationError("source host is not allowed")
        try:
            with self._opener.open(Request(str(source.url), headers={"User-Agent": "TubeForge/0.1"}), timeout=self.timeout_seconds) as response:
                if response.geturl() != str(source.url):
                    raise ProviderValidationError("source redirects are not permitted")
                content_type = response.headers.get_content_type()
                if content_type not in {"text/html", "text/plain"}:
                    raise ProviderValidationError("source must be HTML or plain text")
                payload = response.read(self.max_bytes + 1)
        except ProviderValidationError:
            raise
        except OSError as error:
            raise RetryableProviderError("source retrieval failed") from error
        if len(payload) > self.max_bytes:
            raise ProviderValidationError("source exceeds configured byte limit")
        try:
            raw = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ProviderValidationError("source is not UTF-8 text") from error
        extractor = _TextExtractor()
        if content_type == "text/html":
            extractor.feed(raw)
            raw = " ".join(extractor.parts)
        excerpt = re.sub(r"\s+", " ", html.unescape(raw)).strip()[: self.max_chars]
        if not excerpt:
            raise ProviderValidationError("source contains no readable text")
        return SourceSnapshot(source.source_id, str(source.url), source.title, datetime.now(UTC), hashlib.sha256(payload).hexdigest(), excerpt, source.author)

    @staticmethod
    def _is_private(host: str) -> bool:
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)}
        except OSError:
            return True
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified:
                return True
        return False


def source_packet(sources: tuple[SourceSnapshot, ...]) -> dict[str, object]:
    """Return a deduplicated portable source packet suitable for a checkpoint."""
    seen: set[str] = set()
    values = []
    for source in sources:
        if source.content_sha256 not in seen:
            values.append(source.as_dict())
            seen.add(source.content_sha256)
    return {"schema_version": "1.0", "sources": values}
