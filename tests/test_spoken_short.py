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


def test_legacy_per_scene_manifest_resumes_as_default_profile():
    from tubeforge.rendering.shorts.prepare import _upgrade_legacy_manifest
    scenes = [SimpleNamespace(scene_id="s0", vo="PHP fixed 50% of bugs."), SimpleNamespace(scene_id="s1", vo="Try it.")]
    records = [{"scene_id": "s0", "file": "voice-00.wav", "sha256": "a", "provider": "kokoro", "warning": None, "duration": 1.0},
               {"scene_id": "s1", "file": "voice-01.wav", "sha256": "b", "provider": "kokoro", "warning": None, "duration": 1.0}]
    manifest = _upgrade_legacy_manifest(SimpleNamespace(scenes=scenes), records)
    assert manifest["profile_sha256"] == profile_hash(profile="off", lexicon={}, group_size=1, voice_processing="off")
    first = manifest["groups"][0]
    assert first["spoken_text"] == scenes[0].vo and first["scene_ids"] == ["s0"]
    assert first["display_spans"] == [[[0, 1], [1, 2], [2, 3], [3, 4], [4, 5]]]
    assert first["file"] == first["raw_file"] and first["sha256"] == first["raw_sha256"]
    with pytest.raises(ValueError, match="no longer matches"):
        _upgrade_legacy_manifest(SimpleNamespace(scenes=scenes), records[:1])
    records[1]["scene_id"] = "other"
    with pytest.raises(ValueError, match="no longer matches"):
        _upgrade_legacy_manifest(SimpleNamespace(scenes=scenes), records)


def test_production_config_enables_the_operator_heard_speech_profile():
    from pathlib import Path

    import yaml

    from tubeforge.core.config import ReferenceShortConfig
    raw = yaml.safe_load((Path(__file__).resolve().parents[1] / "config" / "production.yaml").read_text())
    short = ReferenceShortConfig.model_validate(raw["pipeline"]["reference_short"])
    assert (short.spoken_profile, short.speech_group_size, short.voice_processing) == ("spoken-v1", 2, "gentle-v1")


def test_overlap_alignment_repair_makes_word_times_monotonic_and_inside_the_phrase():
    from tubeforge.pipeline.alignment import _regularize_overlap
    spoken = [("a", 0.0, 0.0, 1.0), ("b", 0.05, 0.3, 1.0), ("c", 0.28, 0.5, 1.0), ("d", 0.45, 2.04, 1.0)]
    fixed = _regularize_overlap(spoken, 2.0)
    assert all(end - start >= 0.0199 for _, start, end, _ in fixed)
    assert all(fixed[i][2] <= fixed[i + 1][1] + 1e-9 for i in range(len(fixed) - 1))
    assert fixed[0][1] >= 0 and fixed[-1][2] <= 2.0
