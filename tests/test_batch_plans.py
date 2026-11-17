import pytest
from tubeforge.batch_plans import parse_batch

GOOD = '''## Short\n```yaml\nid: hello\ntitle: Hello\nconcept: Explain a real thing\nbeats:\n  - {t: 0, point: Hook}\nnarration: |\n  Exact text.\n```\n'''


def test_good_defaults_and_opaque_narration():
    plan = parse_batch(GOOD)
    assert not plan.errors
    assert plan.shorts[0].length_s == 60
    assert plan.shorts[0].ending == 'loop'
    assert plan.shorts[0].narration == 'Exact text.\n'


@pytest.mark.parametrize('text, note', [
    (GOOD.replace('id: hello\n', ''), 'id set to `hello`'),
    (GOOD + GOOD, 'was already used: renamed to `hello-2`'),
    (GOOD.replace('title: Hello', 'length_s: 29\ntitle: Hello'), 'length_s set to 30'),
    (GOOD.replace('title: Hello', 'title: ['), 'formatting problem'),
    (GOOD.replace('concept: Explain a real thing\n', ''), 'no concept: used the title'),
    (GOOD.replace('id: hello', 'id: hello\nid: other'), 'appears twice'),
    (GOOD.replace('```\n', '', 1).replace('narration', 'narration', 1)[:-4], 'not closed'),
    (GOOD.replace('beats:\n  - {t: 0, point: Hook}\n', ''), None),
])
def test_small_mistakes_are_repaired_and_reported_instead_of_refused(text, note):
    plan = parse_batch(text)
    assert not plan.errors and plan.shorts
    if note:
        assert any(note in item.message for item in plan.warnings), [w.message for w in plan.warnings]
    assert all(item.line >= 1 for item in plan.warnings)


@pytest.mark.parametrize('text, message', [
    ('No headings', 'must be a list'),
    ('## Empty section\n', 'nothing to read'),
    ('## Only text\n```yaml\njust: [unclosed\nand: {broken\n```\n', 'could not read'),
])
def test_only_unreadable_sections_are_errors_and_they_are_line_numbered(text, message):
    errors = parse_batch(text).errors
    assert errors and any(message in error.message for error in errors)
    assert all(error.line >= 1 for error in errors)


def test_the_loose_forms_people_actually_write_are_understood():
    plan = parse_batch(
        "# My plan\n## Docker alternative\n~~~yml\ntitle: This Docker alternative is almost 8x faster and written in Rust and more words to be long enough for sure ok\n"
        "length_s: 45s\nending: Loop\nbeats:\n  - Hook with the number\n  - {time: '0:10', text: The proof}\n  - 130\nsources: [https://example.com/a, not a link]\n"
        "thumbnail: BIG TEXT\ntags: rust, docker\nmystery_field: 1\nscript_mode: wild\n~~~\n")
    assert not plan.errors, plan.errors
    short = plan.shorts[0]
    assert short.id and short.concept == short.title[:100].rstrip() and short.length_s == 45 and short.ending == 'loop'
    assert [b.point for b in short.beats][:2] == ['Hook with the number', 'The proof'] and short.beats[1].t == 10.0
    assert [str(u) for u in short.sources] == ['https://example.com/a'] and short.thumbnail.text == 'BIG TEXT' and short.tags == ['rust', 'docker']
    notes = ' | '.join(w.message for w in plan.warnings)
    for fragment in ('unknown field `mystery_field`', 'is not an http(s) link', 'is not assist or exact', 'title shortened'):
        assert fragment in notes, notes


def test_a_list_of_shorts_and_a_headingless_block_are_accepted():
    listed = parse_batch("```yaml\n- id: a\n  title: A\n  concept: x\n- id: b\n  title: B\n  concept: y\n```\n")
    assert [s.id for s in listed.shorts] == ['a', 'b'] and not listed.errors
    bare = parse_batch("id: solo\ntitle: Solo\nconcept: one\n")
    assert [s.id for s in bare.shorts] == ['solo']


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
