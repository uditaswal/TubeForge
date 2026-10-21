"""Small, truthful measurements for one worker execution and its durable events."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from tubeforge.pipeline.retention_inventory import cgroup_memory


def stage_clock() -> float:
    return perf_counter()


def stage_measurement(started: float, *, cgroup_root: Path = Path("/sys/fs/cgroup")) -> dict[str, Any]:
    try:
        memory = cgroup_memory(cgroup_root)
    except (OSError, ValueError):
        memory = {"scope": "unavailable", "peak_bytes": None, "current_bytes": None, "limit_bytes": None}
    return {
        "elapsed_ms": max(0, round((perf_counter() - started) * 1_000)),
        "cgroup_peak_bytes": memory["peak_bytes"],
        "cgroup_current_bytes": memory["current_bytes"],
        "cgroup_limit_bytes": memory["limit_bytes"],
        # memory.peak is authoritative for the cgroup, but it is not reset for
        # this job. Never label the container-lifetime value a per-job peak.
        "memory_scope": "container_lifetime" if memory["scope"] != "unavailable" else "unavailable",
    }


def summarize_stage_events(events: list[Any], *, attempt_count: int, failure_message: str | None) -> dict[str, Any]:
    stages: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.event_type != "stage_execution":
            continue
        value = event.details
        stage = value.get("stage")
        if not isinstance(stage, str):
            continue
        item = stages.setdefault(stage, {"executions": 0, "elapsed_ms": 0, "last_outcome": None})
        item["executions"] += 1
        item["elapsed_ms"] += value.get("elapsed_ms", 0) if isinstance(value.get("elapsed_ms"), int) else 0
        item["last_outcome"] = value.get("outcome")
        item["cgroup_peak_bytes"] = value.get("cgroup_peak_bytes")
        item["memory_scope"] = value.get("memory_scope")
    return {
        "schema_version": "1.0",
        "stage_metrics": stages,
        "worker_retry_count": attempt_count,
        "failure_reason": failure_message,
        "memory_note": "memory.peak is a cgroup lifetime peak including page cache; stage values are attribution snapshots, not isolated job peaks",
        "performance_enforcement": "disabled",
    }
