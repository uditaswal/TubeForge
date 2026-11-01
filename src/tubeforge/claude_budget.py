"""Hard spending limits for the Claude host runner.

Every Claude CLI launch goes through one budget: a rolling 24-hour cap on calls and on dollars,
plus a per-call dollar ceiling handed to the CLI itself. Limits are read from the environment of the
runner process and fall back to conservative defaults, so a missing or invalid setting can never
mean "unlimited". The ledger is a small append-only JSONL file under ``data/run/claude``.

    TUBEFORGE_CLAUDE_MAX_CALLS_PER_DAY   default 40
    TUBEFORGE_CLAUDE_MAX_USD_PER_DAY     default 8.00
    TUBEFORGE_CLAUDE_MAX_USD_PER_CALL    default 1.50   (passed to the CLI as --max-budget-usd)
    TUBEFORGE_CLAUDE_LEDGER              default <repo>/data/run/claude/usage-ledger.jsonl
"""
from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path

DEFAULT_MAX_CALLS = 40
DEFAULT_MAX_USD = 8.00
DEFAULT_MAX_USD_PER_CALL = 1.50
WINDOW_SECONDS = 24 * 3600


class BudgetExceededError(PermissionError):
    """Refused before any model launch; the runner reports it as 'unavailable' and burns no attempt."""


def _positive(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


class ClaudeBudget:
    def __init__(self, ledger: Path, *, max_calls: int, max_usd: float, max_usd_per_call: float,
                 window_seconds: int = WINDOW_SECONDS) -> None:
        self.ledger, self.max_calls, self.max_usd = Path(ledger), max_calls, max_usd
        self.max_usd_per_call, self.window = max_usd_per_call, window_seconds

    @classmethod
    def from_env(cls) -> "ClaudeBudget":
        default = Path(__file__).resolve().parents[2] / "data" / "run" / "claude" / "usage-ledger.jsonl"
        return cls(Path(os.environ.get("TUBEFORGE_CLAUDE_LEDGER", default)),
                   max_calls=int(_positive("TUBEFORGE_CLAUDE_MAX_CALLS_PER_DAY", DEFAULT_MAX_CALLS)),
                   max_usd=_positive("TUBEFORGE_CLAUDE_MAX_USD_PER_DAY", DEFAULT_MAX_USD),
                   max_usd_per_call=_positive("TUBEFORGE_CLAUDE_MAX_USD_PER_CALL", DEFAULT_MAX_USD_PER_CALL))

    def _entries(self, now: float) -> list[dict]:
        try:
            lines = self.ledger.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        rows = []
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and now - float(row.get("at", 0)) < self.window:
                rows.append(row)
        return rows

    def usage(self, now: float | None = None) -> tuple[int, float]:
        rows = self._entries(time.time() if now is None else now)
        return sum(int(r.get("n", 1)) for r in rows), sum(float(r.get("usd") or 0) for r in rows)

    def check(self, *, headroom_calls: int = 1, now: float | None = None) -> None:
        """Raise unless ``headroom_calls`` more calls still fit under both daily limits."""
        calls, usd = self.usage(now)
        if calls + headroom_calls > self.max_calls:
            raise BudgetExceededError(
                f"Claude daily call limit reached ({calls} of {self.max_calls} in the last 24 h); "
                "raise TUBEFORGE_CLAUDE_MAX_CALLS_PER_DAY on the runner or wait for the window to roll")
        if usd >= self.max_usd:
            raise BudgetExceededError(
                f"Claude daily spend limit reached (${usd:.2f} of ${self.max_usd:.2f} in the last 24 h); "
                "raise TUBEFORGE_CLAUDE_MAX_USD_PER_DAY on the runner or wait for the window to roll")

    def record(self, *, usd: float | None, label: str = "call", calls: int = 1, now: float | None = None) -> None:
        """Append a ledger row. A launch is recorded (1 call, $0) before it starts so a failed or timed-out
        call still counts toward the call cap; the real cost follows as a 0-call row."""
        self.ledger.parent.mkdir(parents=True, exist_ok=True)
        row = json.dumps({"at": time.time() if now is None else now, "usd": float(usd or 0), "n": calls, "label": label})
        with self.ledger.open("a", encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.write(row + "\n")
