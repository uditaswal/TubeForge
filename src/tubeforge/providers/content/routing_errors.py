"""Worker-side routing signals; the host protocol owns the error taxonomy."""
from tubeforge.core.app_logging import redact
from tubeforge.core.errors import RetryableProviderError


class RunnerFallbackFailure(RetryableProviderError):
    def __init__(self, code, message, *, invocation_started=False, usage=None):
        if code not in {'quota_exhausted', 'runner_unavailable'}:
            raise ValueError('not a fallback-eligible runner code')
        self.code, self.invocation_started = code, invocation_started
        self.usage = usage or {}
        super().__init__(redact(message)[:1000])
