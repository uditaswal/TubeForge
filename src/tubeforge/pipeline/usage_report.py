"""One normalized view of the AI tokens, cost and time a job spent on its script and research.

Claude reports fresh input, cache writes, cache reads and output separately (its `input_tokens` excludes cache).
Codex reports `input_tokens` *including* `cached_input_tokens`. Both are mapped onto the same four buckets so the
dashboard can show one table. Nothing here is estimated: a field the provider did not report stays absent.
"""

from __future__ import annotations

from typing import Any


def _count(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0


def normalize_usage(usage: dict[str, Any] | None) -> dict[str, Any]:
    usage = usage if isinstance(usage, dict) else {}
    if "cached_input_tokens" in usage:  # Codex: cached tokens are a subset of input_tokens
        cached = _count(usage.get("cached_input_tokens"))
        fresh, cache_write, cache_read = max(0, _count(usage.get("input_tokens")) - cached), 0, cached
    else:  # Claude
        fresh = _count(usage.get("input_tokens"))
        cache_write, cache_read = _count(usage.get("cache_creation_input_tokens")), _count(usage.get("cache_read_input_tokens"))
    output = _count(usage.get("output_tokens"))
    result: dict[str, Any] = {"input_tokens": fresh, "cache_write_tokens": cache_write, "cache_read_tokens": cache_read,
                              "output_tokens": output, "total_tokens": fresh + cache_write + cache_read + output}
    cost = usage.get("total_cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool):
        result["cost_usd"] = round(float(cost), 4)
    return result


def _add(total: dict[str, Any], part: dict[str, Any]) -> None:
    for key in ("input_tokens", "cache_write_tokens", "cache_read_tokens", "output_tokens", "total_tokens"):
        total[key] = total.get(key, 0) + part.get(key, 0)
    if "cost_usd" in part:
        total["cost_usd"] = round(total.get("cost_usd", 0.0) + part["cost_usd"], 4)


def summarize_ai_usage(evidence: dict[str, Any] | None, research: dict[str, Any] | None) -> dict[str, Any] | None:
    """`evidence` is the saved content_generation_evidence; `research` the saved source_research (either may be absent)."""
    steps: list[dict[str, Any]] = []
    provenance = (evidence or {}).get("provenance") or {}
    usage = (evidence or {}).get("usage") or {}
    calls = usage.get("calls") if isinstance(usage.get("calls"), list) else []
    if research and isinstance(research.get("usage"), dict):
        searches = _count((research.get("provenance") or {}).get("web_searches") or research["usage"].get("web_search_requests"))
        steps.append({"stage": "research", "calls": 1, "web_searches": searches,
                      "seconds": (research.get("provenance") or {}).get("elapsed_seconds"), **normalize_usage(research["usage"])})
    if calls:  # one row per Claude call (angle, script, script repair, editor)
        steps.extend({"stage": str(call.get("stage", "call")), "calls": 1, **normalize_usage(call)} for call in calls if isinstance(call, dict))
    elif usage:  # older jobs and Codex: only a script-level total exists
        steps.append({"stage": "script", "calls": _count(usage.get("attempts")) or 1, "seconds": provenance.get("elapsed_seconds"),
                      **normalize_usage(usage)})
    if not steps:
        return None
    total: dict[str, Any] = {}
    for step in steps:
        _add(total, step)
    total["calls"] = sum(step["calls"] for step in steps)
    total["web_searches"] = sum(step.get("web_searches", 0) for step in steps)
    seconds = [value for value in (s.get("seconds") for s in steps) if isinstance(value, (int, float))]
    return {"provider": provenance.get("provider"), "model": provenance.get("model"), "effort": provenance.get("effort"),
            "script_seconds": provenance.get("elapsed_seconds"), "per_call_detail": bool(calls), "steps": steps, "total": total,
            "note": "Reported by the model CLI for this job's script and research calls only; local voice, render and QA use no tokens."}
