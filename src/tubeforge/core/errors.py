"""Typed operational failures used by provider adapters and the pipeline."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for an expected provider operation failure."""


class RetryableProviderError(ProviderError):
    """A transient failure that can safely resume at the current stage."""


class ProviderValidationError(ProviderError):
    """An invalid provider result that needs operator correction."""


class InsufficientSourcesError(ProviderValidationError):
    """A blocked brief; never a narration result or automatic retry."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"insufficient_sources: {reason}")


class ProviderAuthenticationError(ProviderError):
    """Authentication must be restored before retrying the operation."""


class AmbiguousProviderError(ProviderValidationError):
    """A remote mutation may have succeeded; automatic recreation is unsafe."""


class RemoteResourceMissingError(ProviderValidationError):
    """A previously recorded remote resource is absent and needs reconciliation."""


class ProviderCancellation(ProviderError):
    """A provider observed cancellation before completing a safe boundary."""
