import pytest

from test_reference_content import candidate
from tubeforge import host_claude_runner as runner
from tubeforge.providers.content.host_runner_protocol import GenerateShortsScriptRequest
from tubeforge.providers.content.prompts import RECIPES, build_content_prompt, writers_room_block


def request_for(tmp_path):
    request, _, _ = candidate()
    return GenerateShortsScriptRequest(operation="GenerateShortsScriptV1", request=request), request


ANGLE = {"chosen_index": 1, "theses": [
    {"thesis": f"verdict {i}", "proof": f"proof {i}", "twist": f"twist {i}", "why_now": f"now {i}", "recipe": "case_study"} for i in range(3)]}


def test_angle_pass_returns_the_chosen_thesis_and_counts_its_own_allowance(tmp_path, monkeypatch):
    host, _ = request_for(tmp_path)
    calls = []
    monkeypatch.setattr(runner, "call_claude", lambda task, schema, **kw: (calls.append(task) or ANGLE, {"total_cost_usd": .02, "output_tokens": 300}))
    usage = {"attempts": 0, "total_cost_usd": 0.0}
    chosen, note = runner.angle_pass(host, tmp_path, model="m", effort="medium", usage_total=usage)
    assert chosen["thesis"] == "verdict 1" and note["ran"] and usage["attempts"] == 1 and "REQUEST=" in calls[0]
    # a second angle pass for the identical request is refused (its own limit of one) and degrades quietly
    again, note2 = runner.angle_pass(host, tmp_path, model="m", effort="medium", usage_total=usage)
    assert again is None and "AllowanceExhausted" in note2["error"] and len(calls) == 1


def test_angle_failure_never_fails_the_job(tmp_path, monkeypatch):
    host, _ = request_for(tmp_path)

    def boom(*a, **k):
        raise RuntimeError("cli down")
    monkeypatch.setattr(runner, "call_claude", boom)
    chosen, note = runner.angle_pass(host, tmp_path, model="m", effort="medium", usage_total={"attempts": 0, "total_cost_usd": 0.0})
    assert chosen is None and "cli down" in note["error"]


def test_editor_pass_keeps_the_draft_when_the_edit_is_invalid(tmp_path, monkeypatch):
    host, _ = request_for(tmp_path)
    monkeypatch.setattr(runner, "call_claude", lambda *a, **k: ({"status": "ready", "package": {}, "reason": None}, {"total_cost_usd": .1}))
    package, normalizations, note = runner.editor_pass(host, tmp_path, {}, model="m", effort="medium", schema={}, version="m6-content-v8",
                                                       usage_total={"attempts": 0, "total_cost_usd": 0.0})
    assert package is None and not note["applied"] and note["reason"] and note["calls"] == 2  # edit + one repair, then the draft stands


def test_prompt_carries_the_chosen_thesis_and_its_recipe():
    request, _, _ = candidate()
    room = {**ANGLE["theses"][1], "recipe": "versus"}
    prompt = build_content_prompt(request, template_version="m6-content-v8", max_chars=60000, writers_room=room)
    assert "WRITERS' ROOM BRIEF" in prompt and "verdict 1" in prompt and RECIPES["versus"][:30] in prompt
    assert "WRITERS' ROOM BRIEF" not in build_content_prompt(request, template_version="m6-content-v8", max_chars=60000)
    assert writers_room_block(None) == ""


def test_hooks_must_not_share_one_formula():
    from types import SimpleNamespace
    from test_script_craft import package
    from tubeforge.providers.content.craft import craft_problems
    same = tuple(f"Your code {i} fails, but why?" for i in range(5))
    p = package(late_stat=True)
    p.hook_options = same
    assert any("question mark" in x for x in craft_problems(p)) and any("'but'" in x for x in craft_problems(p))


def test_web_searches_run_by_the_cli_helper_model_are_counted(monkeypatch):
    import json
    import subprocess
    envelope = {"is_error": False, "structured_output": {"ok": True}, "total_cost_usd": .1,
                "usage": {"server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0}},
                "modelUsage": {"claude-sonnet-5-5": {"webSearchRequests": 0}, "claude-haiku-5-5": {"webSearchRequests": 3}}}
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=json.dumps(envelope).encode(), stderr=b""))
    monkeypatch.setattr(runner, "claude_binary", lambda: "claude")
    _, usage = runner.call_claude("p", {"type": "object"}, model="m", web_search=True)
    assert usage["web_search_requests"] == 3
    envelope["modelUsage"]["claude-haiku-5-5"]["webSearchRequests"] = 0
    _, usage = runner.call_claude("p", {"type": "object"}, model="m", web_search=True)
    assert usage["web_search_requests"] == 0  # a model answering from memory is still refused by run_research
