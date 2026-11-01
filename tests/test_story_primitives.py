"""Story renderer primitives: attack-flow diagrams, terminal windows and key-word highlight sweeps.

Fixtures are synthetic test data, never approved production narration.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from tests.test_reference_shorts import topic_data
from tubeforge.rendering.shorts import story
from tubeforge.rendering.shorts.layout import SceneRenderer
from tubeforge.rendering.shorts.schema import Flow, ShortsTopic
from tubeforge.rendering.shorts.timeline import SceneTiming, Word

VO = "This synthetic example tests readable graphics and safe caption placement."


def flow(**changes):
    data = dict(template="flow", scene_id="f", vo=VO, caption=VO, source_ids=["fixture"], heading="ATTACK PATH",
                nodes=["Attacker", "Stolen key", "Prod server", "Customer data"], reveal_words=[0, 3, 6, 8])
    return Flow.model_validate(data | changes)


def test_flow_diagram_fields_validate_and_default_to_the_stack():
    assert flow(diagram="zigzag", danger=[0, 3]).danger == (0, 3)
    with pytest.raises(ValidationError):
        flow()                                                     # 4 nodes need a diagram style
    with pytest.raises(ValidationError):
        flow(diagram="branch", nodes=["A", "B"], reveal_words=[0, 3])
    with pytest.raises(ValidationError):
        flow(diagram="zigzag", danger=[3, 0])                      # unordered
    with pytest.raises(ValidationError):
        flow(diagram="zigzag", danger=[7])                         # out of range
    plain = Flow.model_validate(dict(template="flow", scene_id="f", vo=VO, caption=VO, heading="STEPS",
                                     nodes=["A", "B"], reveal_words=[0, 3]))
    dumped = plain.model_dump(mode="json")
    assert plain.diagram == "stack" and "diagram" not in dumped and "danger" not in dumped


def test_classic_renderer_still_lays_out_a_four_node_flow():
    data = topic_data()
    scene = data["scenes"][3]
    scene.update(nodes=["INPUT", "CHECK", "FIX", "RESULT"], reveal_words=[0, 2, 4, 6], diagram="zigzag")
    report = SceneRenderer(ShortsTopic.model_validate(data)).validate()
    assert report["passed"]


def story_timeline(scenes, step=.4):
    timings, cursor = [], 0.0
    for scene in scenes:
        count = len(scene.vo.split())
        words = tuple(Word(cursor + j * step, cursor + (j + 1) * step - .05) for j in range(count))
        end = words[-1].end + .2
        timings.append(SceneTiming(cursor, end, words, "synthetic test timing; not measured speech", words[-1].end))
        cursor = end
    return SimpleNamespace(topic=SimpleNamespace(scenes=tuple(scenes), sources=()), timings=tuple(timings), duration=cursor)


def build(scenes, tmp_path):
    story.build_story(story_timeline(scenes), tmp_path / "p", plates_directory=None, manifest={"scenes": {}})
    return (tmp_path / "p" / "index.html").read_text()


def test_zigzag_diagram_draws_nodes_connectors_packets_and_danger_pulses(tmp_path):
    page = build([flow(diagram="zigzag", danger=[0, 3])], tmp_path)
    for k in range(4):
        assert f'id="s0n{k}"' in page
    for k in (1, 2, 3):
        assert f'id="s0l{k}"' in page and f'id="s0p{k}"' in page and f'id="s0h{k}"' in page
    assert page.count("rgba(255,77,61,.75)") == 2          # attacker and compromised target pulse
    assert "gsap.set(\"#s0l1\"" in page


def test_branch_diagram_fans_out_from_the_entry_node(tmp_path):
    page = build([flow(diagram="branch", danger=[0])], tmp_path)
    assert all(f'id="s0n{k}"' in page for k in range(4))
    assert page.count('id="s0l') == 3                       # one connector per target


def test_stack_flow_is_unchanged(tmp_path):
    plain = Flow.model_validate(dict(template="flow", scene_id="f", vo=VO, caption=VO, heading="STEPS",
                                     nodes=["A", "B"], reveal_words=[0, 3]))
    page = build([plain], tmp_path)
    assert 'id="s0n1"' in page and 'id="s0l' not in page and "▼" in page


def test_terminal_window_types_commands_and_labels_the_evidence(tmp_path):
    data = topic_data()["scenes"][5] | {"scene_id": "t", "caption": VO, "vo": VO}
    scene = ShortsTopic.model_validate(topic_data() | {"scenes": topic_data()["scenes"][:5] + [data] + topic_data()["scenes"][6:]}).scenes[5]
    page = build([scene], tmp_path)
    assert 'id="s0term"' in page and ">bash<" in page
    assert "ILLUSTRATIVE OUTPUT" in page
    assert page.count("$ </span>") == 1                       # one command line, typed
    assert 'check example.json' in page                       # typed text carried as data for the typing tween


def test_key_words_get_an_animated_marker_and_other_words_do_not(tmp_path):
    page = build([flow(diagram="zigzag", danger=[0])], tmp_path)
    assert '"keys": [true' in page or '"keys": [false, true' in page or '"keys": [' in page
    assert 'className="mark"' in page and "scaleX:1" in page
    groups = story._caption_groups(flow(diagram="zigzag"), [(i * .4, i * .4 + .35) for i in range(len(VO.split()))])
    flat_keys = [flag for group in groups for flag in group["keys"]]
    assert [i for i, flag in enumerate(flat_keys) if flag] == [0, 3, 6, 8]
    assert all(len(group["times"]) == len(group["words"]) for group in groups)


def test_a_diagram_flow_and_a_terminal_beat_a_captured_source_plate(tmp_path):
    from pathlib import Path
    from tubeforge.rendering.shorts.schema import SourceVisual
    from tubeforge.rendering.shorts.hyperframes_compose import source_treatment  # noqa: F401
    visual = SourceVisual(kind="source", quote="A quoted passage from the cited source page that is long enough to be valid.")
    scene = flow(diagram="zigzag", danger=[0], visual=visual, source_ids=["s"])
    plate = tmp_path / "plate.png"
    from PIL import Image
    Image.new("RGB", (400, 600), "white").save(plate)
    manifest = {"scenes": {"0": {"kind": "source", "file": "plate.png", "url": "https://example.com/x"}}}
    timeline = story_timeline([scene])
    timeline.topic.sources = (SimpleNamespace(source_id="s", url="https://example.com/x", name="Example"),)
    story.build_story(timeline, tmp_path / "p", plates_directory=tmp_path, manifest=manifest)
    page = (tmp_path / "p" / "index.html").read_text()
    assert 'id="s0n3"' in page and 'id="s0l1"' in page         # the diagram is drawn
    assert "hero-0" not in page                                 # not replaced by the screenshot card
    assert "A quoted passage" in page                           # the source still shows, as a quote
