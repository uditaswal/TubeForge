"""The Claude runner refuses calls beyond a rolling daily call/dollar cap and caps each call's spend."""
import json
import time

import pytest

from tubeforge.claude_budget import BudgetExceededError, ClaudeBudget


def budget(tmp_path, **changes):
    values = dict(max_calls=3, max_usd=1.0, max_usd_per_call=0.5) | changes
    return ClaudeBudget(tmp_path / "ledger.jsonl", **values)


def test_calls_are_capped_and_refused_before_launch(tmp_path):
    b = budget(tmp_path)
    for _ in range(3):
        b.check(); b.record(usd=None)
    with pytest.raises(BudgetExceededError, match="call limit"):
        b.check()
    assert b.usage()[0] == 3


def test_a_job_needs_headroom_for_all_its_possible_calls(tmp_path):
    b = budget(tmp_path, max_calls=6)
    b.record(usd=None); b.record(usd=None)
    b.check(headroom_calls=4)
    with pytest.raises(BudgetExceededError):
        b.check(headroom_calls=5)


def test_spend_cap_uses_recorded_cost_and_cost_rows_do_not_count_as_calls(tmp_path):
    b = budget(tmp_path)
    b.record(usd=None, label="launch"); b.record(usd=0.6, label="cost", calls=0)
    b.record(usd=None, label="launch"); b.record(usd=0.5, label="cost", calls=0)
    assert b.usage() == (2, pytest.approx(1.1))
    with pytest.raises(BudgetExceededError, match="spend limit"):
        b.check()


def test_old_entries_roll_out_of_the_window(tmp_path):
    b = budget(tmp_path)
    old = time.time() - 25 * 3600
    for _ in range(3):
        b.record(usd=0.4, now=old)
    b.check()                                   # all three are older than 24 h
    assert b.usage() == (0, 0)


def test_failed_launches_still_count_and_bad_ledger_lines_are_ignored(tmp_path):
    b = budget(tmp_path)
    b.record(usd=None)                          # a launch that never reported a cost
    b.ledger.write_text(b.ledger.read_text() + "not json\n" + json.dumps(["x"]) + "\n")
    assert b.usage()[0] == 1


def test_invalid_or_zero_environment_values_fall_back_to_safe_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEFORGE_CLAUDE_LEDGER", str(tmp_path / "l.jsonl"))
    monkeypatch.setenv("TUBEFORGE_CLAUDE_MAX_CALLS_PER_DAY", "0")
    monkeypatch.setenv("TUBEFORGE_CLAUDE_MAX_USD_PER_DAY", "abc")
    monkeypatch.setenv("TUBEFORGE_CLAUDE_MAX_USD_PER_CALL", "-3")
    b = ClaudeBudget.from_env()
    assert (b.max_calls, b.max_usd, b.max_usd_per_call) == (40, 8.0, 1.5)
    monkeypatch.setenv("TUBEFORGE_CLAUDE_MAX_CALLS_PER_DAY", "12")
    assert ClaudeBudget.from_env().max_calls == 12


def test_runner_command_carries_the_per_call_ceiling_and_call_claude_checks_first(tmp_path, monkeypatch):
    from tubeforge import host_claude_runner as runner
    command = runner.build_command({"type": "object"}, model="m")
    assert command[command.index("--max-budget-usd") + 1] == f"{runner.BUDGET.max_usd_per_call:.2f}"
    monkeypatch.setattr(runner, "BUDGET", budget(tmp_path, max_calls=1))
    runner.BUDGET.record(usd=None)
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: pytest.fail("must not launch the CLI"))
    with pytest.raises(BudgetExceededError):
        runner.call_claude("p", {}, model="m")
