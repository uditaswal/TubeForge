"""Repair loop: one-pass feedback for the display-text rules that kept rejecting drafts, plus a last-attempt heading repair."""
from tubeforge.core.errors import ProviderValidationError
from tubeforge.host_claude_runner import RULES, _validate_once, _with_preflight
from tubeforge.providers.content.craft import display_preflight, heading_repeats, normalize_headings


def draft(**changes):
    value = {
        "reference_short": {"scenes": [
            {"template": "hook", "scene_id": "s1", "vo": "One line in a log file ran code on millions of servers."},
            {"template": "flow", "scene_id": "s2", "heading": "SECRETS STILL OUT", "vo": "Attackers can still smuggle out your secrets, quietly."},
            {"template": "terminal", "scene_id": "s3", "heading": "THE LINE", "vo": "The string names a lookup.",
             "lines": [{"kind": "command", "text": "log4j2.formatMsgNoLookups=true"}, {"kind": "output", "text": "ok"}]},
            {"template": "cta", "scene_id": "s4", "vo": "Tell me which fix you would apply first."}]},
        "thumbnail_brief": {"text_options": ["TOP DANGER SCORE", "TEN OUT OF TEN FOR DANGER"]},
        "script_sections": [{"narration": "x"}] * 4,
    }
    value.update(changes)
    return value


def test_preflight_finds_all_four_recurring_problems_in_one_pass():
    problems = display_preflight(draft(), ending="loop")
    joined = " | ".join(problems)
    assert "scene 2 heading 'SECRETS STILL OUT' repeats the narration" in joined
    assert "terminal line 'log4j2.formatMsgNoLookups=true' is 32 characters" in joined
    assert "thumbnail text_option 2" in joined
    assert "final scene must use template loop" in joined
    assert len(problems) == 4


def test_a_debate_ending_expects_a_cta_scene_and_a_clean_draft_has_no_problems():
    clean = draft()
    clean["reference_short"]["scenes"][1]["heading"] = "PATCH GAP"
    clean["reference_short"]["scenes"][2]["lines"][0]["text"] = "grep -i token log"
    clean["thumbnail_brief"]["text_options"] = ["TOP DANGER SCORE"]
    assert display_preflight(clean, ending="debate") == []
    assert display_preflight(clean, ending="loop") == ["the final scene must use template loop for this request's loop ending"]


def test_a_malformed_draft_never_raises():
    assert display_preflight({}, "loop") == [] and display_preflight({"reference_short": {"scenes": [None]}}, "loop") == []


def test_one_repair_message_carries_the_original_error_and_every_extra_problem_once():
    original = ProviderValidationError("- package.reference_short.scenes.3.cta: headline must be the follow request")
    combined = _with_preflight(original, draft(), "loop")
    text = str(combined)
    assert text.startswith("- package.reference_short.scenes.3.cta") and "ALSO FIX" in text
    assert text.count("heading 'SECRETS STILL OUT'") == 1 and "thumbnail text_option 2" in text
    again = _with_preflight(ProviderValidationError("scene 2 heading 'SECRETS STILL OUT' repeats the narration; x"), draft(), "loop")
    assert str(again).count("scene 2 heading 'SECRETS STILL OUT'") == 1            # already said, not repeated
    assert _with_preflight(original, {}, "loop") is original                         # nothing extra: unchanged


def test_a_cta_close_under_a_loop_ending_names_the_template_as_root_cause_not_the_headline():
    cta_error = ProviderValidationError("- package.reference_short.scenes.3: Value error, CTA headline must be the follow request or comment prompt present in narration")
    text = str(_with_preflight(cta_error, draft(), "loop"))
    assert text.startswith("ROOT CAUSE: the final scene must use template loop")
    assert "do not reword its headline" in text and "CTA headline must be" not in text
    debate = str(_with_preflight(cta_error, draft(), "debate"))                       # a debate ending keeps the headline rule
    assert "ROOT CAUSE" not in debate and "CTA headline must be" in debate


def test_the_last_attempt_shortens_a_heading_that_repeats_its_narration_and_records_it():
    value = draft()
    value["reference_short"]["scenes"][1].update(heading="The early quick fix", vo="The early quick fix was not enough.")
    assert heading_repeats("The early quick fix", "The early quick fix was not enough.")
    notes = normalize_headings(value)
    assert value["reference_short"]["scenes"][1]["heading"] == "quick fix"
    assert notes == [{"rule": "heading_shortened", "scene_id": "s2", "from": "The early quick fix", "to": "quick fix"}]
    assert normalize_headings(value) == []                                           # already fine: idempotent
    fine = draft()
    fine["reference_short"]["scenes"][1]["heading"] = "PATCH GAP"
    assert normalize_headings(fine) == [] and fine["reference_short"]["scenes"][1]["heading"] == "PATCH GAP"


def test_validate_once_has_a_final_flag_and_the_prompt_ends_with_the_checklist():
    import inspect
    assert "final" in inspect.signature(_validate_once).parameters
    assert RULES.rstrip().splitlines()[-1].startswith("- Every terminal line") and "FINAL CHECK" in RULES


def test_the_writing_check_carries_the_review_rules_and_the_final_check_stays_last():
    from tubeforge.host_claude_runner import EDITOR_INSTRUCTIONS
    assert RULES.index("WRITING CHECK") < RULES.index("FINAL CHECK")
    for phrase in ("one running example", "One idea per sentence", "No filler", "payoff follows from the setup", "One term per concept"):
        assert phrase.lower() in RULES.lower()
    assert "(8) sense check" in EDITOR_INSTRUCTIONS and "scene before the loop line" in EDITOR_INSTRUCTIONS
    assert len(RULES) < 4_000 and len(EDITOR_INSTRUCTIONS) < 6_500     # the 75k prompt ceiling keeps its headroom


def test_the_writing_check_adds_the_second_round_of_review_rules_within_the_size_budget():
    from tubeforge.host_claude_runner import EDITOR_INSTRUCTIONS
    for phrase in ("Say the thesis at most twice", "Order: explain how it works first", "Name the thing", "Scope the claim", "Speak it", "never leave the whole script without a figure"):
        assert phrase in RULES
    for phrase in ("only in the hook and the loop line", "before how it breaks", "read straight into line 1"):
        assert phrase in EDITOR_INSTRUCTIONS
    assert RULES.index("WRITING CHECK") < RULES.index("FINAL CHECK") and RULES.rstrip().splitlines()[-1].startswith("- Every terminal line")
    assert len(RULES) < 4_500 and len(EDITOR_INSTRUCTIONS) < 7_000
