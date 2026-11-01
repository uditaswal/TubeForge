import pytest
from tubeforge.batch_plans import parse_batch

GOOD = '''## Short\n```yaml\nid: hello\ntitle: Hello\nconcept: Explain a real thing\nbeats:\n  - {t: 0, point: Hook}\nnarration: |\n  Exact text.\n```\n'''


def test_good_defaults_and_opaque_narration():
    plan = parse_batch(GOOD)
    assert not plan.errors
    assert plan.shorts[0].length_s == 60
    assert plan.shorts[0].ending == 'loop'
    assert plan.shorts[0].narration == 'Exact text.\n'


@pytest.mark.parametrize('text, message', [
    (GOOD.replace('id: hello\n', ''), 'id:'),
    (GOOD + GOOD, 'duplicate id'),
    (GOOD.replace('title: Hello', 'length_s: 29\ntitle: Hello'), 'length_s:'),
    (GOOD.replace('title: Hello', 'title: ['), 'invalid YAML'),
    (GOOD.replace('concept: Explain a real thing\n', ''), 'concept:'),
    (GOOD.replace('id: hello', 'id: hello\nid: other'), 'duplicate YAML'),
    ('No headings', 'expected'),
    (GOOD.replace('```\n', ''), 'unclosed'),
])
def test_errors_are_line_numbered(text, message):
    errors = parse_batch(text).errors
    assert errors and any(message in error.message for error in errors)
    assert all(error.line >= 1 for error in errors)


def test_beat_time_ranges_are_accepted_and_keep_their_end():
    from tubeforge.batch_plans import parse_batch
    plan = parse_batch('## One\n```yaml\nid: one\ntitle: One\nconcept: C\nbeats:\n  - {t: "0-10", point: Hook}\n  - {t: 10, point: Core}\n  - {t: "40\u201360s", point: End}\n```\n')
    assert not plan.errors
    assert [(b.t, b.end) for b in plan.shorts[0].beats] == [(0.0, 10.0), (10.0, None), (40.0, 60.0)]
    bad = parse_batch('## One\n```yaml\nid: one\ntitle: One\nconcept: C\nbeats:\n  - {t: "10-5", point: Hook}\n```\n')
    assert bad.errors


def test_shipped_example_plan_parses_cleanly():
    from pathlib import Path
    from tubeforge.batch_plans import parse_batch
    plan = parse_batch((Path(__file__).resolve().parents[1] / "examples" / "batch-plan-example.md").read_text())
    assert not plan.errors and [s.id for s in plan.shorts] == [
        "sd-001-sql-vs-nosql", "sd-002-in-memory-cache", "sd-003-load-balancing"]
