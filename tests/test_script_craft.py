from types import SimpleNamespace

from test_reference_shorts import topic_data
from tubeforge.providers.content.craft import craft_problems
from tubeforge.rendering.shorts.schema import ShortsTopic


STOCK = {"kind": "stock", "query": "server room racks"}
CODE = {"kind": "code", "language": "rust", "lines": ["let x = 1;"]}


def package(scenes=None, hooks=(), late_stat=False, visuals=(0, 2, 3, 5)):
    data = topic_data()
    for i in visuals:
        data["scenes"][i]["visual"] = STOCK if i in (0, 4, 5, 6) else CODE
    if late_stat:
        data["scenes"][1], data["scenes"][4] = data["scenes"][4], data["scenes"][1]
    for index, update in (scenes or {}).items():
        data["scenes"][index].update(update)
    return SimpleNamespace(reference_short=ShortsTopic.model_validate(data), hook_options=hooks)


GOOD = {6: {"vo": "Still shipping new C code? Tell me why. Follow for more examples.",
            "caption": "Still shipping new C code? Tell me why. Follow for more examples."}}


def test_clean_script_passes():
    assert craft_problems(package(GOOD, late_stat=True)) == []


def test_flags_slop_early_payoff_follow_only_cta_and_echo_heading():
    problems = " | ".join(craft_problems(package(
        {1: {"vo": "Here's the thing: this synthetic example tests readable graphics and safe captions.",
             "caption": "Here's the thing: this synthetic example tests readable graphics and safe captions."},
         3: {"heading": "TESTS READABLE GRAPHICS"}},
        hooks=("Why does this game-changer matter?",))))
    assert "scene 2 uses cliché" in problems and "hook_option 1" in problems
    assert "big_stat payoff is scene 2" in problems
    assert "CTA scene must open with a one-sided challenge" in problems
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
