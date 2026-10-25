"""Reference Short ending choice (loop vs comment debate) and 25-90 second length."""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from test_reference_shorts import topic_data
from test_script_craft import make_loop
from tubeforge.domain.contracts import ContentRequest, SourceReference
from tubeforge.providers.content.craft import craft_problems, debate_problems
from tubeforge.providers.content.prompts import (
    build_content_prompt, incomplete_sections, narration_word_limits, reference_word_budget,
)
from tubeforge.rendering.shorts.schema import ShortsTopic


def request(seconds=60, **extra):
    return ContentRequest(topic="Railway incident", angle="Rotate your keys", target_duration_seconds=seconds, language="en",
                          audience="developers", aspect_ratio="9:16", prompt_version="m6-content-v8",
                          sources=(SourceReference(source_id="fixture", title="Source", url="https://example.com/a",
                                                   excerpt="Railway urged all users to rotate their secret keys."),), **extra)


def debate_data():
    data = topic_data()
    data["scenes"][-1].update(headline="Comment rotate or wait", subline="PICK A SIDE",
                              chips=["ROTATE", "WAIT"], reveal_words=[0, 3],
                              vo="I say rotate every key today. Comment rotate or wait, and tell me why?")
    return data


def test_ending_defaults_to_loop_and_is_omitted_from_the_serialized_request():
    assert request().ending == "loop" and "ending" not in request().model_dump(mode="json")
    assert request(ending="debate").model_dump(mode="json")["ending"] == "debate"
    with pytest.raises(ValidationError):
        request(ending="follow")


def test_reference_shorts_accept_up_to_ninety_seconds_and_no_more():
    assert request(90).target_duration_seconds == 90
    with pytest.raises(ValidationError):
        request(91)


def test_word_budget_scales_with_the_target_and_stays_inside_the_limits():
    short, long = reference_word_budget(40), reference_word_budget(90)
    assert (short["aim_low"], short["aim_high"]) == (76, 86)
    assert long["aim_low"] > 160 and long["max"] <= 205
    assert long["scenes_high"] <= 16 and short["scenes_low"] >= 6
    low, high = narration_word_limits(request(60))
    assert low < reference_word_budget(60)["aim_low"] < reference_word_budget(60)["aim_high"] < high


def test_prompt_states_the_target_length_and_the_chosen_ending():
    loop = build_content_prompt(request(60), template_version="m6-content-v8", max_chars=90000)
    debate = build_content_prompt(request(60, ending="debate"), template_version="m6-content-v8", max_chars=90000)
    budget = reference_word_budget(60)
    assert f"{budget['aim_low']}–{budget['aim_high']} words" in loop and "under 60 seconds" in loop
    assert "LOOP ENDING" in loop and "DEBATE ENDING" not in loop
    assert "DEBATE ENDING" in debate and "LOOP ENDING" not in debate


def test_schema_takes_sixteen_scenes_and_a_comment_prompt_cta():
    data = debate_data()
    middle = data["scenes"][1:-1]
    for index in range(8):
        extra = copy.deepcopy(middle[index % len(middle)])
        extra["scene_id"] = f"extra-{index}"
        data["scenes"].insert(-1, extra)
    assert len(data["scenes"]) == 15 and ShortsTopic.model_validate(data)
    bad = debate_data()
    bad["scenes"][-1].update(headline="Buy it now", vo="Buy it now and test each idea yourself.")
    with pytest.raises(ValidationError):
        ShortsTopic.model_validate(bad)


def test_debate_ending_rules():
    last = ShortsTopic.model_validate(debate_data()).scenes[-1]
    assert debate_problems(last) == []
    follow = copy.deepcopy(debate_data())
    follow["scenes"][-1].update(headline="Follow for more", vo="Follow for more and comment your side below today, please?")
    assert any("follow" in text for text in debate_problems(ShortsTopic.model_validate(follow).scenes[-1]))
    statement = copy.deepcopy(debate_data())
    statement["scenes"][-1]["vo"] = "I say rotate every key today. Comment rotate or wait."
    assert any("question" in text for text in debate_problems(ShortsTopic.model_validate(statement).scenes[-1]))
    package = SimpleNamespace(request=request(ending="debate"), hook_options=(), reference_short=ShortsTopic.model_validate(make_loop(topic_data())))
    assert any("cta" in text for text in craft_problems(package))


def test_open_ended_loop_line_is_not_flagged_as_missing_punctuation():
    sections = lambda texts: [SimpleNamespace(section_id=f"s{i}", narration=t) for i, t in enumerate(texts)]
    loop = SimpleNamespace(reference_short=ShortsTopic.model_validate(make_loop(topic_data())),
                           script_sections=sections(["One.", "Two!", "Three?", "Four.", "Five.", "And that is exactly why the real question is"]))
    assert incomplete_sections(loop) == []
    loop.script_sections[1] = SimpleNamespace(section_id="s1", narration="No stop")
    assert incomplete_sections(loop) == ["s1"]
    legacy = SimpleNamespace(reference_short=ShortsTopic.model_validate(topic_data()), script_sections=sections(["One.", "Ends open"]))
    assert incomplete_sections(legacy) == ["s1"]


def test_studio_api_passes_the_ending_and_enforces_the_ninety_second_preset(tmp_path):
    from fastapi.testclient import TestClient
    from test_api_workflow import _migrate
    from tubeforge.api.app import create_app
    from tubeforge.core.config import AppConfig, DatabaseConfig, Settings, VideoPresetConfig

    database = tmp_path / "ending.db"
    _migrate(database)
    settings = Settings(app=AppConfig(name="TubeForge test", environment="test"), database=DatabaseConfig(url=f"sqlite:///{database}"))
    settings.pipeline.video_generation.presets["reference-short"] = VideoPresetConfig(
        duration_seconds=60, minimum_duration_seconds=30, maximum_duration_seconds=90, aspect_ratio="9:16", prompt_version="m6-content-v8")
    brief = {"title": "Railway", "notes": ["Rotate keys"], "preset": "reference-short",
             "source_url": "https://example.com/a", "source_title": "A", "source_excerpt": "Railway told all users to rotate keys."}
    with TestClient(create_app(settings)) as client:
        default = client.post("/api/videos", json=brief)
        assert default.status_code == 201
        job = client.app.state.runtime.jobs.get(default.json()["id"])
        assert job.request.target_duration_seconds == 60 and job.request.ending == "loop"
        debate = client.post("/api/videos", json={**brief, "ending": "debate", "duration_seconds": 90})
        assert debate.status_code == 201
        assert client.app.state.runtime.jobs.get(debate.json()["id"]).request.ending == "debate"
        assert client.post("/api/videos", json={**brief, "duration_seconds": 91}).status_code == 422
        assert client.post("/api/videos", json={**brief, "ending": "follow"}).status_code == 422
        page = client.get("/").text
        assert "videoEnding" in page and "Debate: close on a question" in page
