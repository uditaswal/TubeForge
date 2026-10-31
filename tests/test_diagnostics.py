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


def test_ai_usage_maps_claude_and_codex_token_shapes_without_inventing_fields() -> None:
    from tubeforge.pipeline.usage_report import normalize_usage, summarize_ai_usage

    claude = normalize_usage({"input_tokens": 6, "output_tokens": 100, "cache_creation_input_tokens": 50, "cache_read_input_tokens": 10, "total_cost_usd": 0.12345})
    assert claude["total_tokens"] == 166 and claude["cost_usd"] == 0.1235
    codex = normalize_usage({"input_tokens": 1000, "cached_input_tokens": 900, "output_tokens": 40})
    assert codex["input_tokens"] == 100 and codex["cache_read_tokens"] == 900 and codex["total_tokens"] == 1040
    assert "cost_usd" not in codex
    assert summarize_ai_usage(None, None) is None
    report = summarize_ai_usage(
        {"provenance": {"provider": "host-claude-runner", "model": "m", "elapsed_seconds": 9.5},
         "usage": {"attempts": 2, "calls": [{"stage": "script", "output_tokens": 10}, {"stage": "editor", "output_tokens": 5}]}},
        {"usage": {"output_tokens": 7, "web_search_requests": 2}, "provenance": {"web_searches": 2, "elapsed_seconds": 3}})
    assert [step["stage"] for step in report["steps"]] == ["research", "script", "editor"]
    assert report["total"]["output_tokens"] == 22 and report["total"]["calls"] == 3 and report["total"]["web_searches"] == 2
    assert report["per_call_detail"] is True
