"""Shared generated-Short duration bounds; requested duration is a writing target."""

SHORTS_MIN_DURATION_SECONDS = 30
SHORTS_MAX_DURATION_SECONDS = 120


def shorts_duration_allowed(duration_seconds: float) -> bool:
    return SHORTS_MIN_DURATION_SECONDS <= duration_seconds <= SHORTS_MAX_DURATION_SECONDS
