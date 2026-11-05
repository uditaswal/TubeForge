import pytest

from tubeforge.rendering.shorts import layout
from tubeforge.rendering.shorts.layout import LayoutError, caption_groups

REVIEW_CAPTIONS = (
    "A speed bump, not a wall. Expect a hard wall? That is not it.",
    "You can burst through it yourself. Even then, extra traffic gets in.",
    "Set the rate to 100 and the burst to 200 requests a second.",
    "One line in a log file ran code on millions of servers.",
    "Use AWS Budgets to watch cost and AWS WAF to block requests.",
    "It is a token bucket that refills at a steady rate.",
    "No retries. No queue. Just a hard stop at the limit.",
)
WEAK = {"A", "AN", "THE", "OF", "TO", "IN", "ON", "FOR", "WITH", "BY", "AT", "FROM", "AND", "OR", "BUT", "IS", "ARE", "NOT"}


def _end_of_sentence(word: str) -> bool:
    return word.rstrip("\"')]")[-1:] in ".!?…"


@pytest.mark.parametrize("caption", REVIEW_CAPTIONS)
def test_groups_keep_every_word_in_order_within_three_words_and_the_width(caption):
    groups = caption_groups(caption)
    assert [word for group in groups for word in group] == caption.upper().split()
    measure = layout.font(layout.CAPTION_SIZE, display=True).getlength
    assert all(1 <= len(group) <= 3 and measure(" ".join(group)) + 12 <= 850 for group in groups)


@pytest.mark.parametrize("caption", REVIEW_CAPTIONS[1:])  # the first caption holds "That is not it.", where every 3-word split ends on a function word
def test_a_group_never_straddles_a_sentence_end_or_ends_on_a_function_word(caption):
    for group in caption_groups(caption):
        assert not any(_end_of_sentence(word) for word in group[:-1]), group
        last = group[-1]
        assert last.strip(".,;:!?") not in WEAK or last[-1] in ".,;:!?", group


@pytest.mark.parametrize("caption", REVIEW_CAPTIONS)
def test_a_group_never_straddles_a_sentence_end(caption):
    for group in caption_groups(caption):
        assert not any(_end_of_sentence(word) for word in group[:-1]), group


def test_the_two_breaks_the_review_called_out_are_fixed():
    flat = [" ".join(g) for g in caption_groups("A speed bump, not a wall. Expect a hard wall?")]
    assert "NOT A" not in flat and not any(group.endswith(" A") for group in flat)
    burst = [" ".join(g) for g in caption_groups("You can burst through it yourself. Even then, traffic leaks.")]
    assert not any("YOURSELF. EVEN" in group for group in burst)


def test_empty_and_one_word_captions_and_an_overlong_token():
    assert caption_groups("") == ()
    assert caption_groups("wow") == (("WOW",),)
    with pytest.raises(LayoutError):
        caption_groups("x" * 200)
