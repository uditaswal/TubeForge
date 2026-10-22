from PIL import Image

from tubeforge.pipeline.capture import CARD_HEIGHT, CARD_WIDTH, _public, draw_highlight, plan_clip


def test_plan_clip_uses_full_width_and_never_exceeds_the_card_aspect():
    rects = [{"x": 40, "y": 800, "w": 450, "h": 26}, {"x": 40, "y": 826, "w": 300, "h": 26}]
    x, y, w, h = plan_clip(rects, 540, 5000)
    assert (x, w) == (0, 540) and h <= 540 * CARD_HEIGHT / CARD_WIDTH + 1e-6
    assert y <= 800 and y + h >= 852  # the whole match stays inside the crop


def test_plan_clip_aligns_to_the_paragraph_when_it_fits():
    rects = [{"x": 40, "y": 830, "w": 450, "h": 26}]
    block = {"y": 800.0, "h": 150.0}
    x, y, w, h = plan_clip(rects, 540, 5000, block)
    assert y == 790.0 and y + h == 960.0  # block top/bottom plus 10 px padding, no partial extra lines


def test_plan_clip_falls_back_to_matched_lines_for_tall_blocks():
    rects = [{"x": 40, "y": 830, "w": 450, "h": 26}, {"x": 40, "y": 856, "w": 450, "h": 26}]
    x, y, w, h = plan_clip(rects, 540, 5000, {"y": 100.0, "h": 2000.0})
    assert y == 820.0 and y + h == 892.0  # exactly the matched lines plus 10 px padding


def test_plan_clip_ignores_a_container_that_is_not_the_paragraph():
    rects = [{"x": 40, "y": 830, "w": 450, "h": 26}]
    x, y, w, h = plan_clip(rects, 540, 5000, {"y": 700.0, "h": 400.0})
    assert y == 820.0 and h == 46.0


def test_plan_clip_stays_inside_short_documents():
    x, y, w, h = plan_clip([{"x": 10, "y": 20, "w": 100, "h": 20}], 540, 150)
    assert y >= 0 and y + h <= 150 + 1e-6


def test_highlight_changes_only_the_matched_region():
    base = Image.new("RGB", (810, 400), "white")
    marked = draw_highlight(base, [{"x": 100, "y": 100, "w": 200, "h": 30}], (0, 0, 810, 400))
    assert marked.getpixel((150, 115)) != (255, 255, 255) and marked.getpixel((600, 300)) == (255, 255, 255)


def test_private_and_unresolvable_hosts_are_rejected():
    cache = {}
    assert not _public("localhost", cache) and not _public("127.0.0.1", cache) and not _public("10.0.0.5", cache)
    assert not _public("does-not-exist.invalid", cache)
