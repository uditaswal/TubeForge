"""Layout fixtures are synthetic test data, never approved production narration."""
import pytest
from pydantic import ValidationError

from tubeforge.rendering.shorts.layout import Canvas, LayoutError, SceneRenderer, background
from tubeforge.rendering.shorts.schema import ShortsTopic


def topic_data():
    common = dict(vo="This synthetic example tests readable graphics and safe caption placement.",
                  caption="Readable graphics stay clear of these captions.", source_ids=["fixture"],
                  reveal_words=[0, 3])
    definitions = [
        dict(template="hook", headline=["WHAT", "CHANGES?"], chips=["COMPARE", "CHECK"],
             reveal_words=[0]),
        dict(template="big_stat", heading="MEASURE THE CHANGE", before=76, after=24, unit="%",
             before_label="BEFORE", after_label="AFTER"),
        dict(template="before_after", heading="BEFORE → AFTER", before="MANUAL STEPS", after="CHECKED OUTPUT"),
        dict(template="flow", heading="VERIFY EACH STEP", nodes=["INPUT", "CHECK", "RESULT"], reveal_words=[0, 3, 6]),
        dict(template="checklist", heading="KEEP THE EVIDENCE", items=["Source", "Measurement", "Review"], reveal_words=[0, 3, 6]),
        dict(template="terminal", heading="CHECK THE RESULT", evidence_label="ILLUSTRATIVE OUTPUT",
             lines=[dict(kind="command", text="check example.json"), dict(kind="output", text="validation passed")]),
        dict(template="cta", headline="Follow for more examples", subline="ONE CLEAR IDEA AT A TIME",
             chips=["LEARN", "TEST", "BUILD"], reveal_words=[0, 2, 5],
             vo="Follow for more examples and test each idea yourself."),
    ]
    return dict(title="Synthetic geometry test", sources=[dict(source_id="fixture", name="Synthetic test data",
                url="https://example.com/test-fixture")],
                scenes=[dict(common, **{"scene_id": f"scene-{i}"}) | definition for i, definition in enumerate(definitions)])


def test_all_templates_geometry_and_first_frame():
    renderer = SceneRenderer(ShortsTopic.model_validate(topic_data()))
    report = renderer.validate()
    assert report["passed"]
    assert len(report["scenes"]) == 7
    hook = renderer.compose(0, revealed=0)
    assert sum(m.key.startswith("headline") for m in hook.marks) == 2
    assert all(m.font_size >= 84 for m in hook.marks if m.key.startswith("headline"))
    # Caption event reuse is bounded, but the active highlight changes pixels.
    first = renderer.frame(0, chunk=0)
    assert renderer.frame(0, chunk=0) is first
    assert renderer.frame(0, chunk=0, active=1).tobytes() != first.tobytes()


def test_caption_never_shrinks_and_long_token_fails():
    data = topic_data()
    data["scenes"][0]["caption"] = "X" * 100
    with pytest.raises(LayoutError, match="caption_token_overflow"):
        SceneRenderer(ShortsTopic.model_validate(data))
    renderer = SceneRenderer(ShortsTopic.model_validate(topic_data()))
    for groups in renderer.groups:
        assert all(1 <= len(group) <= 3 for group in groups)


def test_reject_model_geometry_unknown_source_and_missing_follow():
    for mutate in (
        lambda data: data["scenes"][1].update(x=100),
        lambda data: data["scenes"][1].update(source_ids=["invented"]),
        lambda data: data["scenes"][-1].update(headline="Subscribe now"),
    ):
        data = topic_data()
        mutate(data)
        with pytest.raises(ValidationError):
            ShortsTopic.model_validate(data)


def test_layout_rejects_overlaps_and_safe_zone_intrusions():
    canvas = Canvas(background().copy())
    canvas.box("first", (100, 500, 600, 700))
    with pytest.raises(LayoutError, match="box_collision"):
        canvas.box("second", (500, 600, 800, 800))
    with pytest.raises(LayoutError, match="caption_collision"):
        canvas.box("caption_cover", (100, 1250, 800, 1400))
    with pytest.raises(LayoutError, match="safe_bounds"):
        canvas.box("right_rail", (900, 500, 1000, 700))
    with pytest.raises(LayoutError, match="text_overflow"):
        canvas.text("unreadable", "A very long label " * 20, (495, 900), size=50, minimum=40)


def test_source_labels_and_reveals_are_real_pixels():
    renderer = SceneRenderer(ShortsTopic.model_validate(topic_data()))
    for index in range(1, 6):
        hidden, shown = renderer.frame(index, 0), renderer.frame(index, 3)
        assert hidden.tobytes() != shown.tobytes()
        assert any(m.role == "source" for m in renderer.compose(index).marks)


def fixture_timeline():
    from tubeforge.rendering.shorts.timeline import SceneTiming, Timeline, Word
    data = topic_data()
    for scene in data["scenes"]:
        scene["caption"] = scene["vo"]
    topic = ShortsTopic.model_validate(data)
    timings = []
    for i, scene in enumerate(topic.scenes):
        count = len(scene.vo.split())
        step = 3.65 / count
        words = tuple(Word(i * 4 + j * step, i * 4 + (j + 1) * step) for j in range(count))
        timings.append(SceneTiming(i * 4, (i + 1) * 4, words, "synthetic test timing; not measured speech"))
    return Timeline(topic, tuple(timings))


def test_timing_binds_exact_words_tail_and_reveal():
    from dataclasses import replace
    from tubeforge.rendering.shorts.timeline import Timeline
    timeline = fixture_timeline()
    assert timeline.event(4)[0:2] == (1, 1)
    assert timeline.event(5.2)[0:2] == (1, 2)
    assert timeline.event(3.8)[2] is None
    bad = list(timeline.timings)
    bad[-1] = replace(bad[-1], end=bad[-1].end + .4)
    with pytest.raises(ValueError, match="speech tail"):
        Timeline(timeline.topic, tuple(bad))


def test_real_encoder_and_cancel_preserve_existing_output(tmp_path):
    import json
    import shutil
    import subprocess
    from tubeforge.rendering.shorts.encode import RenderCancelled, encode
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required for real encoder test")
    timeline = fixture_timeline()
    audio = tmp_path / "tone.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=48000:duration=28",
                    "-af", "loudnorm=I=-14:TP=-2.5:LRA=9", "-ar", "48000", str(audio)], check=True)
    target = tmp_path / "fixture.mp4"
    report = encode(timeline, audio, target, draft=True, motion=False)
    assert report["passed"] and report["full_decode"]
    assert report["distinct_frame_events"] < report["frames"] / 4
    assert report["loudness"]["input_tp"] <= -1.5
    target.with_suffix(".passed-qa.json").write_text(json.dumps(report, indent=2))
    original = target.read_bytes()
    with pytest.raises(RenderCancelled):
        encode(timeline, audio, target, draft=True, motion=False, cancelled=lambda: True)
    assert target.read_bytes() == original
    assert json.loads(target.with_suffix(".qa.json").read_text())["passed"] is False
