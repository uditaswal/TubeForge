from types import SimpleNamespace

from test_reference_shorts import topic_data
from tubeforge.providers.content.craft import craft_problems
from tubeforge.rendering.shorts.schema import ShortsTopic


STOCK = {"kind": "stock", "query": "server room racks"}
CODE = {"kind": "code", "language": "rust", "lines": ["let x = 1;"]}


def make_loop(data):
    """Turn the fixture's legacy CTA into the loop scene: same frame as scene 1, no follow request, open-ended sentence."""
    hook = data["scenes"][0]
    loop = {k: v for k, v in hook.items() if k not in {"scene_id", "vo", "caption", "visual"}}
    loop.update(scene_id="scene-6", template="loop", reveal_words=[0], source_ids=hook["source_ids"],
                vo="And that is exactly why the real question is", caption="And that is exactly why the real question is")
    data["scenes"][-1] = loop
    return data


def package(scenes=None, hooks=(), late_stat=False, visuals=(0, 2, 3, 5), legacy_cta=False):
    data = topic_data() if legacy_cta else make_loop(topic_data())
    for i in visuals:
        data["scenes"][i]["visual"] = STOCK if i in (0, 4, 5, 6) else CODE
    if late_stat:
        data["scenes"][1], data["scenes"][4] = data["scenes"][4], data["scenes"][1]
    for index, update in (scenes or {}).items():
        data["scenes"][index].update(update)
    return SimpleNamespace(reference_short=ShortsTopic.model_validate(data), hook_options=hooks)


GOOD = {}


def test_clean_script_passes():
    assert craft_problems(package(GOOD, late_stat=True)) == []


def test_flags_slop_early_payoff_and_echo_heading():
    problems = " | ".join(craft_problems(package(
        {1: {"vo": "Here's the thing: this synthetic example tests readable graphics and safe captions.",
             "caption": "Here's the thing: this synthetic example tests readable graphics and safe captions."},
         3: {"heading": "TESTS READABLE GRAPHICS"}},
        hooks=("Why does this game-changer matter?",))))
    assert "scene 2 uses cliché" in problems and "hook_option 1" in problems
    assert "big_stat payoff is scene 2" in problems
    assert "scene 4 heading" in problems


def test_too_many_rhetorical_questions():
    text = "Is this synthetic example testing readable graphics and safe captions?"
    problems = craft_problems(package({**GOOD, 1: {"vo": text, "caption": text},
                                       2: {"vo": text, "caption": text}, 3: {"vo": text, "caption": text}}, late_stat=True))
    assert any("rhetorical questions" in p for p in problems)


def test_visual_rules():
    from tubeforge.providers.content.craft import visual_problems
    assert visual_problems(package(late_stat=True)) == []
    few = " | ".join(visual_problems(package(visuals=(0, 5))))
    assert "only 2 of 7 scenes" in few and "two consecutive scenes" in few
    assert any("more than 3 stock" in p for p in visual_problems(package(visuals=(0, 4, 5, 6))))


def test_comment_only_code_visual_is_rejected():
    from tubeforge.providers.content.craft import visual_problems
    data_pkg = package(late_stat=True)
    scenes = list(data_pkg.reference_short.scenes)
    scenes[2] = scenes[2].model_copy(update={"visual": scenes[2].visual.model_copy(update={"lines": ("// only a comment",)})})
    data_pkg.reference_short = data_pkg.reference_short.model_copy(update={"scenes": tuple(scenes)})
    assert any("only comments" in p for p in visual_problems(data_pkg))


def test_jargon_and_unspeakable_numbers_are_rejected():
    from tubeforge.providers.content.craft import SPEECH_UNSAFE
    bad = package({1: {"vo": "No cutover. The bill was $120,000 and 3.4x faster on 1,383 MB machines.", "caption": "No cutover. The bill was $120,000 and 3.4x faster on 1,383 MB machines."}}, late_stat=True)
    problems = " | ".join(craft_problems(bad))
    assert "cliché" in problems and "voice reads badly" in problems
    assert not SPEECH_UNSAFE.search("The bill was 120 thousand dollars, 3.4 times faster, 14.5 weeks, 76% fewer bugs.")


def test_thumbnail_text_must_be_short_and_not_repeat_the_opening():
    pkg = package(GOOD, late_stat=True)
    opening = pkg.reference_short.scenes[0].vo
    pkg.thumbnail_brief = SimpleNamespace(text_options=[" ".join(opening.split()[:3]), "ONE TWO THREE FOUR", "TAKE IT OFFLINE"])
    problems = " | ".join(craft_problems(pkg))
    assert "text_option 1" in problems and "text_option 2" in problems and "text_option 3" not in problems


def test_loop_ending_rules():
    from tubeforge.providers.content.craft import loop_problems
    assert loop_problems(package(late_stat=True)) == []
    closed = " | ".join(loop_problems(package({6: {"vo": "That is exactly why the real question matters.", "caption": "That is exactly why the real question matters."}})))
    assert "no final full stop" in closed
    changed = " | ".join(loop_problems(package({6: {"headline": ["SOMETHING", "ELSE"]}})))
    assert "copy scene 1's headline" in changed
    legacy = " | ".join(loop_problems(package(legacy_cta=True)))
    assert "template loop" in legacy
    greeting = " | ".join(loop_problems(package({0: {"vo": "Hello guys welcome back to the channel everyone today.", "caption": "Hello guys welcome back to the channel everyone today."}})))
    assert "greeting" in greeting


def test_loop_scene_rejects_follow_requests_but_legacy_cta_still_validates():
    import pytest
    from pydantic import ValidationError
    data = make_loop(topic_data())
    data["scenes"][-1]["vo"] = "Follow for more examples and test each idea yourself and again"
    data["scenes"][-1]["caption"] = data["scenes"][-1]["vo"]
    with pytest.raises(ValidationError, match="follow or subscribe"):
        ShortsTopic.model_validate(data)
    assert ShortsTopic.model_validate(topic_data()).scenes[-1].template == "cta"  # saved legacy jobs keep rendering
