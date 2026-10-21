from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from tubeforge.pipeline.diagnostics import stage_measurement, summarize_stage_events


def test_cgroup_peak_is_labeled_container_lifetime(tmp_path: Path) -> None:
    (tmp_path / "memory.peak").write_text("900000000\n")
    (tmp_path / "memory.current").write_text("500000000\n")
    (tmp_path / "memory.max").write_text("1073741824\n")
    measured = stage_measurement(0, cgroup_root=tmp_path)
    assert measured["cgroup_peak_bytes"] == 900000000
    assert measured["memory_scope"] == "container_lifetime"
    assert measured["elapsed_ms"] >= 0


def test_stage_summary_keeps_attempts_and_failure_without_inventing_a_job_peak() -> None:
    events = [
        SimpleNamespace(event_type="stage_execution", details={"stage": "content_generating", "elapsed_ms": 10, "outcome": "failed", "cgroup_peak_bytes": 900, "memory_scope": "container_lifetime"}),
        SimpleNamespace(event_type="stage_execution", details={"stage": "content_generating", "elapsed_ms": 25, "outcome": "succeeded", "cgroup_peak_bytes": 950, "memory_scope": "container_lifetime"}),
    ]
    summary = summarize_stage_events(events, attempt_count=1, failure_message="source unavailable")
    assert summary["stage_metrics"]["content_generating"]["elapsed_ms"] == 35
    assert summary["stage_metrics"]["content_generating"]["executions"] == 2
    assert summary["worker_retry_count"] == 1
    assert summary["failure_reason"] == "source unavailable"
    assert "lifetime" in summary["memory_note"]
