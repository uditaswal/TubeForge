"""Craft gate against fact dumps. The Log4Shell pilot narration (accurate and sourced, but a list of version numbers
and jargon) is the failing fixture; a plain-language rewrite is the passing one. Fixtures are test data only."""
from types import SimpleNamespace

from tubeforge.providers.content.craft import fact_dump_problems

PILOT = [  # narration of the 1 Nov pilot, as spoken
    "Unnoticed since 2013, one logging bug got the highest severity score.",
    "Log4j is a Java tool that writes down user input. Enterprise software uses it everywhere.",
    "By default, Log4j 2 swaps expressions inside a logged string for real values.",
    "One expression, jndi, can point at a URL. Log4j then loads data from there.",
    "Attackers place the string in a logged header like User-Agent. Log4j then fetches it.",
    "Even with execution disabled, attackers still steal secret environment variables through the URL.",
    "Wiz and EY say 93 percent of enterprise cloud environments were affected.",
    "Blocking the word jndi was easy to dodge with a lowercase trick.",
    "Version 2.15.0 restricted lookups, 2.16.0 disabled JNDI features, and 2.17.1 closed two more holes.",
    "On older versions, remove the JndiLookup class. The no-lookups setting alone was later found unreliable.",
    "Unnoticed since 2013, Log4j simply obeyed a string it should have only logged.",
    "That is why I would check every Log4j version, because bugs stay",
]
GOOD = [
    "One line in a log file let strangers run code on millions of servers.",
    "Log4j is a free tool that almost every Java program uses to write down what happened.",
    "Here is the trick. If the text it writes down contains a certain pattern, Log4j goes and fetches whatever that points to.",
    "So an attacker types that pattern into a chat box, a username, even a browser name.",
    "The server dutifully logs it, fetches the attacker's file and runs it. That is the whole attack.",
    "It sat there for years before anyone noticed, because nobody thought to doubt a logging library.",
    "The first fix was not enough, so patches kept coming for weeks. That is why you could not just update once.",
    "If your company runs Java software, ask your vendor one question: which Log4j do you ship?",
    "Because the bug was not clever. It was a feature nobody thought to question.",
    "One line in a log file let strangers run code on millions of servers.",
]


def package(lines):
    return SimpleNamespace(reference_short=SimpleNamespace(scenes=[SimpleNamespace(vo=text, template="flow") for text in lines]))


def test_the_pilot_script_is_flagged_for_its_version_litany_and_for_never_speaking_to_the_viewer():
    problems = fact_dump_problems(package(PILOT))
    assert any("scene 9" in p and "3 version numbers" in p for p in problems)
    assert any("what it means for the viewer" in p for p in problems)


def test_a_plain_language_script_passes():
    assert fact_dump_problems(package(GOOD)) == []


def test_too_many_numbers_in_one_scene_and_one_sentence_are_flagged():
    lines = list(GOOD)
    lines[2] = "It scored 10 out of 10, hit 93 percent of clouds and spread to 500 countries in 7 days."
    problems = fact_dump_problems(package(lines))
    assert any("scene 3 packs" in p for p in problems) or any("scene 3 has a sentence" in p for p in problems)


def test_numbers_on_consecutive_scenes_and_a_video_wide_total_are_flagged():
    lines = ["Plain opening here that says nothing numeric at all today.",
             "It rose 10 percent in 2 weeks.", "Then it fell 20 percent in 3 days.", "Because that means you should check twice.",
             "Plain closing line that tells you what to do next time around.", "So you check, then you fix, then you move on."]
    problems = fact_dump_problems(package(lines))
    assert any("both stack numbers" in p for p in problems)


def test_repeated_openings_and_jargon_pileups_are_flagged():
    lines = ["Log4j runs everywhere in Java.", "Log4j reads the string you send.", "Log4j then fetches the file.", "Log4j runs the code it fetched.",
             "The JNDI, LDAP, RMI and DNS lookups all trigger it.", "That means you must patch today because attackers move fast.",
             "So you patch and you check the version twice because it matters."]
    problems = fact_dump_problems(package(lines))
    assert any("4 scenes start with 'log4j'" in p for p in problems)
    assert any("piles up" in p and "scene 5" in p for p in problems)


def test_the_new_gate_runs_inside_craft_problems_on_a_real_package():
    from tubeforge.providers.content import craft
    assert "fact_dump_problems(package)" in open(craft.__file__).read()


def test_the_writer_prompt_and_the_editor_both_carry_the_story_shape_rules():
    from tubeforge.host_claude_runner import EDITOR_INSTRUCTIONS
    from tubeforge.providers.content import prompts
    source = open(prompts.__file__).read()
    for needle in ("STORY SHAPE", "at most one number per scene", "NUMBERS:", "JARGON:", "SOURCES:"):
        assert needle in source
    assert "listener test" in EDITOR_INSTRUCTIONS and "two numbers per scene" in EDITOR_INSTRUCTIONS


def test_scorecard_separates_the_pilot_from_a_plain_script():
    from tubeforge.providers.content.craft import script_scorecard
    bad, good = script_scorecard(package(PILOT)), script_scorecard(package(GOOD))
    assert bad["version_numbers"] == 3 and good["version_numbers"] == 0
    assert bad["fact_dump_problems"] > 0 == good["fact_dump_problems"]
    assert good["viewer_address_share"] > bad["viewer_address_share"]


def test_prompt_states_the_two_limits_the_writer_kept_breaking():
    from tubeforge.providers.content import prompts
    source = open(prompts.__file__).read()
    assert "terminal lines at most 26 characters in total" in source and "log4j2.formatMsgNoLookups=true" in source
    assert "DIFFERENT words than the voice-over" in source and "PATCH ONE FAILED" in source


def test_a_score_without_its_scale_is_flagged_and_an_explained_one_is_not():
    from tubeforge.providers.content.craft import unexplained_score_problems
    bad = package(["Log4Shell scored a perfect ten, and all it took was logging text.", *GOOD[1:]])
    flagged = unexplained_score_problems(bad)
    assert len(flagged) == 1 and "scene 1" in flagged[0] and "what it measures" in flagged[0]
    assert unexplained_score_problems(package(["Apache gave it the top danger rating, ten out of ten.", *GOOD[1:]])) == []
    assert unexplained_score_problems(package(["It was rated critical by the vendor.", *GOOD[1:]])) == []          # no figure, nothing to explain
    assert unexplained_score_problems(package(["Apache scored it a perfect ten.", *GOOD[1:]]))                     # the second pilot-script line


def test_filler_phrases_are_banned():
    from tubeforge.providers.content.craft import BANNED_PHRASES
    assert "think about that" in BANNED_PHRASES


def test_only_the_repairable_rules_are_hard():
    lines = ["Plain opening here that says nothing numeric at all today.",
             "It rose 10 percent in 2 weeks.", "Then it fell 20 percent in 3 days.", "Because that means you should check twice.",
             "Plain closing line that tells you what to do next time around.", "So you check, then you fix, then you move on."]
    assert any("both stack numbers" in p for p in fact_dump_problems(package(lines)))
    assert not any("both stack numbers" in p for p in fact_dump_problems(package(lines), hard_only=True))
    assert any("version numbers" in p for p in fact_dump_problems(package(PILOT), hard_only=True))
