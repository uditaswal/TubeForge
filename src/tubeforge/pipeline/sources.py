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
from tubeforge.core.errors import InsufficientSourcesError
from tubeforge.domain.contracts import SourceReference
from tubeforge.providers.content.prompts import reject_instruction_spoofing


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
    """Extract article text, including inert templates, without executing scripts."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.article_parts: list[str] = []
        self._ignored = 0
        self._template = False
        self._stack: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        article = tag == "article" or values.get("itemprop") == "articleBody" or bool(classes & {"post-content", "post-body", "w-richtext"})
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self._stack.append((tag, article))
        if tag == "script" and (values.get("type") or "").lower() in {"text/template", "text/x-template"}:
            self._template = True
        elif tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self._template:
            self._template = False
        elif tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] == tag:
                del self._stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._ignored:
            return
        if self._template:
            nested = _TextExtractor()
            nested.feed(data)
            data = " ".join(nested.article_parts or nested.parts)
        self.parts.append(data)
        if any(article for _, article in self._stack):
            self.article_parts.append(data)


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
            raw = " ".join(extractor.article_parts or extractor.parts)
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


def approved_excerpt_snapshot(source: SourceReference, *, captured_at: datetime) -> dict[str, object]:
    """Bind exactly the operator/channel-approved excerpt, not a mutable URL."""
    if not source.excerpt or not source.excerpt.strip():
        raise InsufficientSourcesError(f"Source {source.source_id} has no approved excerpt")
    for field in ("title", "author", "excerpt"):
        reject_instruction_spoofing(getattr(source, field), field=f"sources.{source.source_id}.{field}")
    excerpt = source.excerpt.strip()
    value = source.model_dump(mode="json")
    value["excerpt"] = excerpt
    value["content_sha256"] = hashlib.sha256(excerpt.encode("utf-8")).hexdigest()
    value["captured_at"] = captured_at.isoformat()
    value["snapshot_kind"] = "approved_excerpt"
    value["untrusted"] = True
    if source.content_sha256 and source.content_sha256 != value["content_sha256"]:
        value["original_content_sha256"] = source.content_sha256
    return value


def resolve_source_packet(
    supplied: tuple[SourceReference, ...], *, channel_approved: tuple[SourceReference, ...] = (),
    ingestor: SourceIngestor | None = None, captured_at: datetime,
) -> dict[str, object]:
    """Prefer supplied excerpts, then approved channel excerpts, then opt-in retrieval."""
    selected = tuple(source for source in supplied if source.excerpt and source.excerpt.strip())
    mode = "operator_supplied"
    if not selected:
        selected = tuple(source for source in channel_approved if source.excerpt and source.excerpt.strip())
        mode = "channel_approved"
    if selected:
        if len(selected) > 8:
            selected = selected[:8]
        entries = [approved_excerpt_snapshot(source, captured_at=captured_at) for source in selected]
        if len({item["source_id"] for item in entries}) != len(entries):
            raise ProviderValidationError("source packet has duplicate source IDs")
        return {"schema_version": "1.1", "retrieval_mode": mode, "sources": entries}
    if ingestor is None:
        raise InsufficientSourcesError("Provide approved source excerpts or configure channel-approved sources before script generation")
    candidates = supplied[:8] or channel_approved[:8]
    if not candidates:
        raise InsufficientSourcesError("No source references are available for bounded retrieval")
    snapshots = tuple(ingestor.ingest(source) for source in candidates)
    for item in snapshots:
        reject_instruction_spoofing(item.excerpt, field=f"sources.{item.source_id}.excerpt")
    return {"retrieval_mode": "fetched", **source_packet(snapshots)}
