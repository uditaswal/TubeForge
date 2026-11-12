"""Bounded, jittered provider backoff without exposing response bodies."""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import json
import math
import random
from typing import Mapping


MAX_DELAY_SECONDS = 3600


def provider_hint(headers: Mapping[str, str], *, now: datetime | None = None) -> int | None:
    """Combine Retry-After with Meta's x-app-usage pressure when supplied."""
    now = now or datetime.now(UTC)
    hints = []
    retry = headers.get('retry-after') or headers.get('Retry-After')
    if retry:
        try:
            seconds = float(retry)
            if math.isfinite(seconds):
                hints.append(max(0, math.ceil(seconds)))
        except (TypeError, ValueError):
            try:
                stamp = parsedate_to_datetime(retry)
                if stamp.tzinfo is not None:
                    hints.append(max(0, math.ceil((stamp - now).total_seconds())))
            except (TypeError, ValueError, OverflowError):
                pass
    usage = headers.get('x-app-usage') or headers.get('X-App-Usage')
    if usage:
        try:
            values = json.loads(usage)
            if isinstance(values, dict):
                pressures = [float(values[name]) for name in ('call_count', 'total_cputime', 'total_time') if name in values]
                maximum = max((value for value in pressures if math.isfinite(value)), default=0)
                if maximum >= 90:
                    hints.append(min(900, 60 + max(0, math.ceil(maximum - 90)) * 84))
        except (ValueError, TypeError):
            pass
    return min(MAX_DELAY_SECONDS, max(hints)) if hints else None


def retry_delay(hint: int | None, *, attempt: int = 1, jitter=None) -> int:
    """Never retry before an in-range hint; bound both exponential wait and jitter."""
    base = min(MAX_DELAY_SECONDS, 30 * (2 ** max(0, min(attempt - 1, 7))))
    if hint is not None:
        base = max(base, max(0, min(MAX_DELAY_SECONDS, int(hint))))
    draw = jitter if jitter is not None else random.uniform
    extra = max(0, draw(0, min(30, base * .2)))
    return min(MAX_DELAY_SECONDS, max(1, math.ceil(base + extra)))
