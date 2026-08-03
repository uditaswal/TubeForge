"""Typed operational failures used by provider adapters and the pipeline."""

from __future__ import annotations


class ProviderError(RuntimeError):
    """Base class for an expected provider operation failure."""


class RetryableProviderError(ProviderError):
    """A transient failure that can safely resume at the current stage."""


class ProviderValidationError(ProviderError):
    """An invalid provider result that needs operator correction."""


class ProviderAuthenticationError(ProviderError):
    """Authentication must be restored before retrying the operation."""
