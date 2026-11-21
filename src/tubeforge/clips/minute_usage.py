import math


def charged_duration(duration_seconds: float | None) -> int:
    """Whole seconds, rounded up, for a verified positive source duration."""
    if (
        isinstance(duration_seconds, bool)
        or not isinstance(duration_seconds, (int, float))
        or not math.isfinite(duration_seconds)
        or duration_seconds <= 0
    ):
        raise ValueError("A verified positive source duration is required")
    return math.ceil(duration_seconds)
