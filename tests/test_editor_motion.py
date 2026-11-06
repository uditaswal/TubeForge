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


def test_line_windows_hold_completed_text_until_next_speech_anchor():
    scene = EditorScene(("abc", "def"), start=0, typing_seconds=5,
                        line_windows=((0, 1), (3, 4)))
    assert scene.count(.5) == 1
    assert scene.count(2) == 3
    assert scene.cursor(2) == (0, 3)
    assert scene.cursor(3) == (1, 0)
    assert scene.count(4) == 7
    assert scene.count(6) == 7


@pytest.mark.parametrize('windows', [((0, 1),), ((0, 2), (1, 3)),
    ((0, 1), (2, 8)), ((0, 1), (2, float('nan')))])
def test_invalid_line_windows_fail(windows):
    with pytest.raises(ValueError):
        EditorScene(("abc", "def"), start=0, line_windows=windows)


def test_multiline_string_lexing_preserves_text_and_colour():
    scene = EditorScene(('text = """first', 'second"""'))
    renderer = EditorRenderer(scene)
    second = [cell for cell in renderer.cells if cell[0] >= len(scene.lines[0])+1]
    assert ''.join(cell[1] for cell in second) == scene.lines[1]
    assert all(cell[3] == '#a4dfa0' for cell in second)


def test_control_characters_cannot_change_layout():
    with pytest.raises(ValueError):
        EditorScene(('abc\rdef',))


def test_card_primitive_uses_native_visual_zone_and_cursor_stays_inside():
    scene = EditorScene(('x' * 30,) * 6)
    renderer = EditorRenderer(scene, card_only=True)
    frame = renderer.revealed_frame(len(scene.text))
    assert frame.size == (810, 670)
    x = round(renderer.text_x + 30*renderer.advance)
    y = renderer.text_y + 7 + 5*renderer.row_height
    assert x+3 < 810 and y+43 < 596  # above evidence label
    assert frame.getpixel((x, y)) == (101, 234, 212)
    assert renderer.revealed_frame(len(scene.text), cursor_visible=False).getpixel((x, y)) != (101, 234, 212)
