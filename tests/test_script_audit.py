"""Regression tests from the forensic audit of the rate-limit Short (docs/original-script-audit.md, plan: naturalness Round 3 / P5).

The fixtures are test data: the verbatim narration of the reviewed job ms1-pilot-rate-limit-v2, a hand-written DRAFT rewrite,
and the narration of scripts the operator did not reject. Nothing here approves or claims a better video. All new rules are advisory."""
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from tubeforge.pipeline.script_fit import spoken_words
from tubeforge.providers.content.craft import (loop_reads_as, naturalness_problems, rewrite_keeps_evidence, script_scorecard,
                                               spoken_craft_problems)
from tubeforge.providers.content.prompts import reference_word_budget

FIXTURES = Path(__file__).parent / "fixtures" / "scripts"
ORIGINAL = json.loads((FIXTURES / "api_rate_limiting_original.json").read_text())
REWRITE = json.loads((FIXTURES / "api_rate_limiting_rewrite_draft.json").read_text())
ACCEPTED = json.loads((FIXTURES / "accepted_scripts.json").read_text())["scripts"]


def package(texts):
    return SimpleNamespace(reference_short=SimpleNamespace(scenes=[SimpleNamespace(vo=t, template="flow", cues=()) for t in texts]))


def fixture_package(fixture):
    scenes = []
    for s in fixture["scenes"]:
        shown = {k: (tuple(v) if isinstance(v, list) else v) for k, v in s.get("on_screen", {}).items() if k != "caption"}
        visual = s.get("visual")
        code = SimpleNamespace(kind=visual["kind"], lines=tuple(visual.get("lines", ()))) if visual and visual.get("kind") == "code" else None
        scenes.append(SimpleNamespace(vo=s["narration"], template=s["template"], cues=(), visual=code, **shown))
    return SimpleNamespace(reference_short=SimpleNamespace(scenes=scenes))


def test_the_original_fixture_is_the_verbatim_reviewed_script():
    scenes = ORIGINAL["scenes"]
    assert [s["narration"] for s in (scenes[0], scenes[7], scenes[11])] == [
        "Your rate limiter is a speed bump, not a wall.",
        "AWS calls the limit a target, not a ceiling. Think soft, not hard.",
        "Now you know why stacking limits matters, because"]
    assert len(scenes) == 12 and sum(len(s["narration"].split()) for s in scenes) == 153 and ORIGINAL["target_seconds"] == 60
    assert all(not s["cues"] for s in scenes), "the original used no delivery cues"
    # On-screen text is separate from narration: the 'Two dials' card shows 100 and 2000, which no narration says.
    assert "ThrottlingBurstLimit" in json.dumps(scenes[9]["visual"]) and not re.search(r"\b2000\b", " ".join(s["narration"] for s in scenes))


def test_every_new_rule_flags_the_original():
    notes = " | ".join(spoken_craft_problems(fixture_package(ORIGINAL)))
    assert "'X, not Y' slogan frame (scenes 1, 8)" in notes
    assert "'bucket' starts a sentence in 5 scenes" in notes
    assert "no contraction in 153 words" in notes
    assert "scenes 5 say 'that is' / 'here is'" in notes
    assert "the ending says 'now you know'" in notes


def test_the_audit_is_in_the_regular_advisory_output_and_the_older_checks_still_catch_their_part():
    notes = " | ".join(naturalness_problems(fixture_package(ORIGINAL)))
    for expected in ("the opening has no number and no named thing", "scene 2 has filler", "scene 4 has filler", "scene 5 has filler",
                     "scene 8 has filler", "scene 9 says 'Other factors'", "shows 100, 2000 on screen", "scene 11 restates the hook's idea",
                     "no figure is carried through", "scene 4 echoes itself", "'X, not Y' slogan frame", "no contraction in 153 words"):
        assert expected in notes, expected
    assert script_scorecard(fixture_package(ORIGINAL))["contractions_per_100_words"] == 0.0


def test_scripts_the_operator_did_not_reject_raise_no_new_notes_except_one_true_positive():
    found = {name: spoken_craft_problems(package(data["scenes"])) for name, data in ACCEPTED.items()}
    assert {name: notes for name, notes in found.items() if notes} == {
        "pilot-idempotency": ["no contraction in 149 words; a person says 'it's', 'that's', 'doesn't' (read it aloud: the voice sounds like a manual)"]}


@pytest.mark.parametrize("text, expected", [
    (["A speed bump, not a wall.", "Soft, not hard.", "A target, not a ceiling."], True),
    (["A speed bump, not a wall.", "Soft, not hard."], False),            # two is a style, three is a tic
    (["It isn't a wall, and nothing else."], False),
])
def test_slogan_frame(text, expected):
    notes = spoken_craft_problems(package(text))
    assert any("slogan frame" in n for n in notes) is expected


def test_a_noun_that_names_the_topic_in_the_hook_may_start_many_sentences():
    topic_scenes = ["Redis changed caching forever."] + [f"Redis does step {n}." for n in range(1, 7)]
    assert not any("starts a sentence" in n for n in spoken_craft_problems(package(topic_scenes)))
    other = ["Caching changed forever."] + [f"The bucket does step {n}." for n in range(1, 7)]
    assert any("'bucket' starts a sentence in 6 scenes" in n for n in spoken_craft_problems(package(other)))


def test_contractions_and_closing_announcements():
    spoken = ["It's a limit, and that's fine. " * 3] * 4
    assert spoken_craft_problems(package(spoken)) == []
    assert any("ending says 'so remember'" in n for n in spoken_craft_problems(package(["Set it up.", "So remember, limits stack."])))
    assert not any("ending says" in n for n in spoken_craft_problems(package(["Set it up.", "Stack two limits and test the second."])))


def test_the_rewrite_draft_is_clean_keeps_the_evidence_and_is_sized_for_speech():
    assert naturalness_problems(fixture_package(REWRITE)) == []
    assert rewrite_keeps_evidence(ORIGINAL, REWRITE) == []
    counts = [spoken_words(s["narration"]) for s in REWRITE["scenes"]]
    assert all(8 <= n <= 15 for n in counts), counts
    budget = reference_word_budget(60)
    assert budget["aim_low"] - 5 <= sum(counts) <= budget["max"], sum(counts)
    assert script_scorecard(fixture_package(REWRITE))["contractions_per_100_words"] > 0
    assert "speed bump" not in " ".join(s["narration"] for s in REWRITE["scenes"]).lower(), "a rewrite must not reuse the original's slogan"
    assert loop_reads_as(fixture_package(REWRITE)).startswith("So stack your limits, because one gate is never enough, and you hit")


def test_a_rewrite_that_drops_a_claim_a_source_or_a_figure_is_reported():
    broken = json.loads(json.dumps(REWRITE))
    broken["scenes"][5]["claim_ids"] = []
    broken["scenes"][5]["narration"] = broken["scenes"][5]["narration"].replace("429", "error")
    broken["scenes"][0]["narration"] = broken["scenes"][0]["narration"].replace("429", "error")
    for scene in broken["scenes"]:
        scene["source_ids"] = [s for s in scene["source_ids"] if s != "gravitee-token-bucket"]
    problems = " | ".join(rewrite_keeps_evidence(ORIGINAL, broken))
    assert "figure 429 was dropped" in problems and "source gravitee-token-bucket is no longer used" in problems
    invented = json.loads(json.dumps(REWRITE))
    invented["scenes"][1]["claim_ids"] = ["c99"]
    assert any("c99 is not one of the original's claims" in p for p in rewrite_keeps_evidence(ORIGINAL, invented))


def test_the_audit_document_quotes_every_original_sentence_exactly():
    audit = (Path(__file__).parents[1] / "docs" / "original-script-audit.md").read_text()
    for scene in ORIGINAL["scenes"]:
        for sentence in re.split(r"(?<=[.!?])\s+", scene["narration"]):
            assert sentence in audit, f"the audit does not quote {sentence!r} verbatim"
