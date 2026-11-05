import pytest
from tubeforge.rendering.shorts.editor import EditorScene, EditorRenderer


def test_newline_moves_cursor_without_consuming_next_character():
    scene = EditorScene(("abc", "def"), start=0, typing_seconds=7)
    assert scene.cursor(3) == (0, 3)
    assert scene.cursor(4) == (1, 0)
    assert scene.cursor(5) == (1, 1)
    assert scene.cursor(20) == (1, 3)


def test_timing_is_clamped_and_reproducible():
    scene = EditorScene(("print('hello')",))
    renderer = EditorRenderer(scene)
    assert scene.count(-1) == 0
    assert scene.count(scene.duration) == len(scene.text)
    assert renderer.frame(1.5).tobytes() == renderer.frame(1.5).tobytes()
    assert renderer.frame(0).tobytes() != renderer.frame(2).tobytes()
    # The longest supported line and its cursor fit inside the right safe edge.
    assert 140 + 30*renderer.advance + 3 < 930
    assert renderer.frame(1).size == (1080, 1920)


@pytest.mark.parametrize('kwargs', [dict(lines=("x"*31,)), dict(lines=("x\ty",)),
    dict(lines=("x",), typing_seconds=0), dict(lines=("x",), hold_seconds=.5),
    dict(lines=("x",), start=float('nan'))])
def test_invalid_or_unreadable_scenes_fail(kwargs):
    with pytest.raises(ValueError):
        EditorScene(**kwargs)
