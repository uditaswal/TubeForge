from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tubeforge.core.errors import ProviderValidationError
from tubeforge.domain.contracts import SourceReference
from tubeforge.pipeline.sources import SourceIngestor, SourceSnapshot, _RejectRedirects, source_packet


def test_source_packet_deduplicates_content_hashes() -> None:
    first = SourceSnapshot("a", "https://docs.example/a", "A", datetime.now(UTC), "a" * 64, "facts")
    second = SourceSnapshot("b", "https://docs.example/b", "B", datetime.now(UTC), "a" * 64, "same facts")
    assert source_packet((first, second))["sources"] == [first.as_dict()]
    assert first.as_reference().excerpt == "facts"


def test_ingestor_rejects_non_allowlisted_and_private_sources() -> None:
    ingestor = SourceIngestor(frozenset({"docs.example"}))
    with pytest.raises(ProviderValidationError, match="HTTPS"):
        ingestor.ingest(SourceReference(source_id="x", url="http://docs.example/x", title="x"))
    with pytest.raises(ProviderValidationError, match="not allowed"):
        ingestor.ingest(SourceReference(source_id="x", url="https://example.invalid/x", title="x"))


def test_redirects_are_rejected_before_following_the_target() -> None:
    with pytest.raises(ProviderValidationError, match="redirects"):
        _RejectRedirects().redirect_request(None, None, 302, "redirect", {}, "https://other.example")
