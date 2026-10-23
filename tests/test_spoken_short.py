"""Speech prep must preserve reviewed display words and bind each spoken token."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from tubeforge.rendering.shorts.spoken import (
    VERSION, collapse_alignment, prepare_spoken, profile_hash, validated_lexicon,
)


def test_spoken_forms_keep_display_words_and_cover_every_spoken_word():
    display = "PHP fixed 50% of cases for $12 in API v2.0, not RTX-4090."
    prepared = prepare_spoken(display, profile=VERSION, lexicon={"PHP": "P H P"})
    assert prepared.text == "P H P fixed fifty percent of cases for twelve dollars in A P I v2.0, not RTX-4090."
    assert len(prepared.display_spans) == len(display.split())
    assert prepared.display_spans[0] == (0, 3)
    assert prepared.display_spans[2] == (4, 6)
    assert prepared.display_spans[-1][1] == 18
    assert [row["rule"] for row in prepared.applied] == ["lexicon", "percent", "currency", "acronym"]


def test_baseline_and_profile_identity_are_distinct():
    display = "PHP fixed 50% of cases."
    baseline = prepare_spoken(display, profile="off", lexicon={})
    assert baseline.text == display and baseline.display_spans == ((0, 1), (1, 2), (2, 3), (3, 4), (4, 5))
    first = profile_hash(profile="off", lexicon={}, group_size=1, voice_processing="off")
    assert first != profile_hash(profile=VERSION, lexicon={}, group_size=1, voice_processing="off")
    assert first != profile_hash(profile="off", lexicon={"PHP": "P H P"}, group_size=1, voice_processing="off")
    assert first != profile_hash(profile="off", lexicon={}, group_size=2, voice_processing="off")
    assert first != profile_hash(profile="off", lexicon={}, group_size=1, voice_processing="gentle-v1")


def test_lexicon_rejects_deletion_and_ambiguous_keys():
    for lexicon in ({"PHP": ""}, {"PHP": "P H P", "php": "P H P"}, {"two words": "one"}, {"PHP": "P\nH\nP"}):
        with pytest.raises(ValueError, match="lexicon"):
            validated_lexicon(lexicon)


def test_alignment_collapse_rejects_missing_or_extra_spoken_words():
    words = [SimpleNamespace(start_seconds=i * .2, end_seconds=(i + 1) * .2) for i in range(5)]
    collapsed = collapse_alignment(words, ((0, 3), (3, 5)))
    assert collapsed[0] == pytest.approx((0, .6))
    assert collapsed[1] == pytest.approx((.6, 1.0))
    for spans in (((0, 3), (4, 5)), ((0, 2), (2, 4)), ((0, 3), (2, 5))):
        with pytest.raises(ValueError, match="spoken"):
            collapse_alignment(words, spans)
