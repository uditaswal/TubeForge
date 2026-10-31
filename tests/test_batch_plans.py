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
