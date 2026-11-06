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


RATE_LIMIT_P2 = [
    "Your AWS API Gateway limit is a target, not a wall.",
    "Throttling protects your API from being flooded with requests. It feels like a wall.",
    "Both throttles and quotas are best-effort targets, not guaranteed request ceilings. AWS says so.",
    "Requests drain a token bucket in your gateway. Each one spends a token.",
    "Worse, the bucket allows a planned overrun. Traffic can pass your limit by design.",
    "Quotas leak too. Even without a burst, AWS says clients can exceed your quotas.",
    "AWS warns against relying on either one to control costs. Same for blocking access.",
    "Use these instead. AWS Budgets monitors your costs, and AWS WAF manages your API requests.",
    "To keep people out, use real login checks. Usage plan quotas will not do it.",
    "A limit is a target. Let AWS Budgets and AWS WAF do the real work.",
    "Go ahead and set your limits if you like, but never forget that",
]
IDEMPOTENCY_P2 = [
    "Stripe remembers your first answer, even when it was a 500 error.",
    "You tap pay. The charge goes through, but the reply never reaches you.",
    "Retry blindly and your customer is charged twice. Stripe's blog calls that very bad.",
    "Your client makes up a unique ID and sends it along. The server spots repeats.",
    "The older Stripe API saves the status and full reply of your first request.",
    "Then your retry returns that saved reply. Failures included.",
    "But if your request fails its basic checks, Stripe saves nothing. Retrying is fine.",
    "Change the request details but reuse the key. Stripe returns an error.",
    "After 24 hours, Stripe can delete a key. Reusing it makes a new request.",
    "Make your key long and random. Never use an email address.",
    "My verdict: a key is memory, not magic. Your retry replays the first answer.",
    "and that is the one rule behind every safe retry, because",
]


def lines(texts):
    return package(*[scene(text) for text in texts])


def test_the_reviewed_rate_limit_script_is_flagged_where_the_reviewer_pointed():
    notes = naturalness_problems(lines(RATE_LIMIT_P2))
    joined = " | ".join(notes)
    assert "scene 3 restates the hook's idea" in joined and "scene 10 restates the hook's idea" in joined     # target, not a wall: lines 1, 3 and 10
    assert "scene 9 says 'real login checks'" in joined and "scene 10 says 'real work'" in joined or "do the real work" in joined
    assert "scene 3 names its source in the voice-over" in joined and "scene 7 names its source in the voice-over" in joined
    assert "scenes 9 use stiff uncontracted forms" in joined                                                    # "will not do it"
    assert "no figure at all" in joined                                                                         # no running example
    assert "scene 4 " not in joined and "scene 5 " not in joined                                               # the mechanism scenes are not flagged


def test_the_reviewed_idempotency_script_flags_the_label_and_the_cited_blog():
    notes = " | ".join(naturalness_problems(lines(IDEMPOTENCY_P2)))
    assert "scene 11 opens with a reviewer's label ('My verdict:')" in notes
    assert "scene 3 names its source in the voice-over" in notes and "blog calls" in notes
    assert "scene 11 restates the hook's idea ('first answer')" in notes
    assert "no figure at all" not in notes                                                                       # it has 500 and 24


def test_names_are_not_mistaken_for_a_repeated_thesis():
    texts = ["Your AWS API Gateway limit can be passed.", "The AWS API Gateway keeps a token bucket.", "A bucket holds tokens until a burst spends them.",
             "Set 100 a second and a burst of 200.", "Then the limit leaks.", "Use a budget.", "and that is the limit, because"]
    assert not any("restates the hook" in note for note in naturalness_problems(lines(texts)))


def test_loop_reads_as_joins_the_last_line_to_the_first_and_keeps_names_capitalised():
    from tubeforge.providers.content.craft import loop_reads_as
    joined = loop_reads_as(lines(["Stripe remembers your first answer.", "Stripe saves it.", "and that is the rule, because"]))
    assert joined == "and that is the rule, because Stripe remembers your first answer."
    plain = loop_reads_as(lines(["Retries are dangerous.", "They repeat.", "and that is why, because"]))
    assert plain == "and that is why, because retries are dangerous."
    assert "loop_reads_as" in script_scorecard(lines(RATE_LIMIT_P2))


def test_a_counter_starting_at_zero_and_a_trailing_comma_are_not_unspoken_figures():
    shown = package(scene("After 24 hours, a key can be deleted.", before="0", after="24 hours"),
                    scene("Set the burst to 200 and the rate to 100.", before="burst 100,", after="rate 200"))
    assert not any("on screen" in note for note in naturalness_problems(shown))
