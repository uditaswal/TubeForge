"""Advisory naturalness checks. The failing fixture reproduces the faults a reviewer found in the rate-limit Short
(abstract hook that restates itself, filler, vague "other factors", an on-screen card whose numbers the voice never says).
Fixtures are test data only; nothing here is an operator approval or a claim about a published video."""
import inspect
from types import SimpleNamespace

from tubeforge.providers.content.craft import _rhythm, _spoken_forms, craft_problems, naturalness_problems, script_scorecard


def scene(vo, **display):
    return SimpleNamespace(vo=vo, template="flow", cues=(), **display)


def package(*scenes):
    return SimpleNamespace(reference_short=SimpleNamespace(scenes=list(scenes)))


BAD = package(
    scene("Speed bump, not a wall. Expect a hard wall? That is not it.", headline=("SPEED BUMP",)),
    scene("Throttling smooths traffic. Slow and steady.", heading="Smooth"),
    scene("Two dials set the limit.", heading="Two Dials", before="burst 100", after="rate 2000"),
    scene("Extra traffic gets in. Other factors can push traffic past the limit.", heading="It leaks"),
    scene("Think soft, not hard.", heading="Soft"),
)
GOOD = package(
    scene("You set a limit of 100 requests a second. API Gateway can still let more through.", headline=("100 A SECOND",)),
    scene("The burst is 200, so a full bucket can be spent at once.", heading="Burst", before="burst 200", after="rate 100"),
    scene("Separately, enforcement is best effort, so some requests above the rate still pass.", heading="Best effort"),
    scene("Don't rely on it for cost control. Use AWS Budgets to watch spend and AWS WAF to block requests.", heading="Budgets and WAF"),
)


def test_the_reviewed_script_is_flagged_on_every_deterministic_point():
    notes = " | ".join(naturalness_problems(BAD))
    assert "opening has no number and no named thing" in notes
    assert "scene 1 has filler" in notes and "that is not it" in notes
    assert "scene 2 has filler" in notes and "slow and steady" in notes
    assert "scene 3 shows 100, 2000 on screen but the narration never says it" in notes
    assert "scene 4 says 'Other factors' without naming them" in notes
    assert "scene 5 has filler" in notes and "think soft" in notes


def test_a_concrete_consistent_script_raises_no_notes():
    assert naturalness_problems(GOOD) == []


def test_a_hook_that_says_one_idea_twice_is_flagged():
    twice = package(scene("Throttling is only a speed bump. Throttling is just a speed bump, nothing more.", headline=("X",)))
    assert any("says the same idea twice" in note for note in naturalness_problems(twice))


def test_on_screen_figures_may_be_spoken_as_words_and_identifiers_with_digits_are_ignored():
    spoken = package(scene("Set the burst to two hundred and the rate to a hundred.", before="burst 200", after="rate 100"),
                     scene("Run it with the log4j2 flag.", lines=(SimpleNamespace(text="log4j2.formatMsgNoLookups=true"),)))
    assert not any("on screen" in note for note in naturalness_problems(spoken))


def test_spoken_forms_cover_digits_words_and_decimals():
    assert {"200", "two hundred"} <= _spoken_forms("200")
    assert "a hundred" in _spoken_forms("100") and "two thousand" in _spoken_forms("2,000")
    assert "ninety nine point nine" in _spoken_forms("99.9")


def test_the_advisories_are_not_hard_gates_and_the_scorecard_reports_them_with_rhythm_signals():
    assert "naturalness_problems" not in inspect.getsource(craft_problems)   # advisory: promote to a gate only after the reference set
    card = script_scorecard(BAD)
    assert card["naturalness_notes"] and "sentence_length_variation" in card and "contractions_per_100_words" in card


def test_rhythm_signals_separate_flat_robotic_prose_from_varied_spoken_prose():
    flat = _rhythm(["The system limits traffic. The system queues extra requests. The system drops the rest."])
    spoken = _rhythm(["It leaks. And that's the part nobody tells you, because the docs bury it. Don't trust it."])
    assert flat["contractions_per_100_words"] == 0 and spoken["contractions_per_100_words"] > 0
    assert spoken["sentence_length_variation"] > flat["sentence_length_variation"]
