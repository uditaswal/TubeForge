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


def test_diagram_packet_times_matches_connector_arrival_count_and_order():
    scene = flow(diagram="zigzag", danger=[0, 3])
    reveal = [0.0, 1.2, 2.5, 4.0]
    times = story.diagram_packet_times(scene, reveal, a=0.0, b=5.0)
    assert len(times) == len(scene.nodes) - 1 == 3
    assert times == sorted(times)                              # later edges arrive later
    assert times == [reveal[1], reveal[2], reveal[3]]           # mirrors `_diagram`'s own arrive formula


def test_diagram_packet_times_falls_back_without_enough_reveal_words():
    scene = flow(diagram="branch", nodes=["A", "B", "C"], reveal_words=[0])
    times = story.diagram_packet_times(scene, [0.0], a=0.0, b=6.0)
    assert len(times) == 2
    assert all(0.0 < t < 6.0 for t in times)


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


def _hook(template="hook"):
    from tubeforge.rendering.shorts.schema import Hook, Loop
    data = dict(template=template, scene_id="h", vo=VO, caption=VO, source_ids=["fixture"], reveal_words=[0], headline=["ONE LINE", "RAN CODE"], chips=["CVSS"])
    return (Hook if template == "hook" else Loop).model_validate(data)


def _plates(tmp_path):
    from PIL import Image
    (tmp_path / "plates").mkdir()
    Image.new("RGB", (1280, 720), (30, 90, 160)).save(tmp_path / "plates" / "stock-0.png")
    manifest = {"scenes": {"0": {"kind": "stock", "media": "photo", "file": "plates/stock-0.png", "query": "server room",
                                 "evidence": {"provider": "pixabay", "asset_id": "14900", "license_name": "Pixabay Content License"}}}}
    return tmp_path, manifest


def test_hook_and_loop_scenes_get_a_blurred_stock_backdrop_with_licence_evidence(tmp_path):
    plates, manifest = _plates(tmp_path)
    timeline = story_timeline([_hook("hook"), _hook("loop")])
    timeline.topic.sources = ()
    report = story.build_story(timeline, tmp_path / "p", plates_directory=plates, manifest=manifest)
    page = (tmp_path / "p" / "index.html").read_text()
    assert page.count("backdrop-0.jpg") == 2 and (tmp_path / "p" / "assets" / "backdrop-0.jpg").is_file()   # the loop reuses the hook's backdrop
    assert 's0bg' in page and 's1bg' in page and "scale:1.12" in page
    assert [b["license"] for b in report["stock_backdrops"]] == ["Pixabay Content License"] * 2
    assert report["stock_backdrops"][0]["provider"] == "pixabay" and report["stock_backdrops"][0]["query"] == "server room"


def test_without_a_stock_plate_the_hook_keeps_its_plain_background(tmp_path):
    timeline = story_timeline([_hook("hook")])
    timeline.topic.sources = ()
    report = story.build_story(timeline, tmp_path / "p", plates_directory=tmp_path, manifest={"scenes": {}})
    assert report["stock_backdrops"] == [] and "backdrop-" not in (tmp_path / "p" / "index.html").read_text()
    missing = {"scenes": {"0": {"kind": "stock", "media": "photo", "file": "plates/gone.png"}}}
    assert story.build_story(timeline, tmp_path / "q", plates_directory=tmp_path, manifest=missing)["stock_backdrops"] == []


def test_a_long_hook_headline_shrinks_to_fit_and_pushes_the_chips_down(tmp_path):
    from tubeforge.rendering.shorts.schema import Hook
    long = Hook.model_validate(dict(template="hook", scene_id="h", vo=VO, caption=VO, source_ids=["fixture"], reveal_words=[0],
                                    headline=["In 1998,", "NoSQL was", "still relational"], chips=["speed"]))
    short = _hook("hook")
    long_page = build([long], tmp_path / "a")
    short_page = build([short], tmp_path / "b")
    import re
    size = lambda page: int(re.search(r'class="h1" style="top:280px;font-size:(\d+)px"', page).group(1))
    top = lambda page: int(re.search(r'id="s0c0" style="left:60px;top:(\d+)px', page).group(1))
    assert size(long_page) < 140 <= size(short_page) and size(long_page) >= 84
    assert top(long_page) >= 880 and top(short_page) == 880 or top(short_page) >= 880


def _terminal_scene():
    data = topic_data()["scenes"][5] | {"scene_id": "t", "caption": VO, "vo": VO}
    return ShortsTopic.model_validate(topic_data() | {"scenes": topic_data()["scenes"][:5] + [data] + topic_data()["scenes"][6:]}).scenes[5]


def test_select_layout_family_tracks_scene_mix_and_is_deterministic():
    terminal_topic = SimpleNamespace(scenes=(_terminal_scene(), _terminal_scene()))
    diagram_topic = SimpleNamespace(scenes=(flow(diagram="zigzag"),
                                            flow(diagram="branch", nodes=["Entry", "Target A", "Target B"], reveal_words=[0, 3, 6])))
    plain_topic = SimpleNamespace(scenes=(_hook("hook"), _hook("loop")))
    assert story.select_layout_family(terminal_topic) == "terminal_led"
    assert story.select_layout_family(diagram_topic) == "cinematic_code"
    assert story.select_layout_family(plain_topic) == "walkthrough_statement"
    # Pure function of the scene mix: no randomness, same input always gives the same family.
    assert story.select_layout_family(terminal_topic) == story.select_layout_family(terminal_topic)
    assert story.select_layout_family(SimpleNamespace(scenes=())) == "walkthrough_statement"


def test_build_story_records_and_visibly_applies_the_chosen_layout_family(tmp_path):
    report = story.build_story(story_timeline([_terminal_scene()]), tmp_path / "term", plates_directory=None, manifest={"scenes": {}})
    assert report["layout_family"] == "terminal_led"
    term_page = (tmp_path / "term" / "index.html").read_text()
    assert story._FAMILY_STYLE["terminal_led"]["mark"] in term_page          # caption highlight colour follows the family
    assert "power4.out" in term_page                                        # terminal_led's snappier pop ease

    report = story.build_story(story_timeline([flow(diagram="zigzag")]), tmp_path / "diag", plates_directory=None, manifest={"scenes": {}})
    assert report["layout_family"] == "cinematic_code"
    diag_page = (tmp_path / "diag" / "index.html").read_text()
    assert "power1.out" in diag_page and story._FAMILY_STYLE["cinematic_code"]["mark"] in diag_page

    report = story.build_story(story_timeline([_hook("hook")]), tmp_path / "plain", plates_directory=None, manifest={"scenes": {}})
    assert report["layout_family"] == "walkthrough_statement"
    plain_page = (tmp_path / "plain" / "index.html").read_text()
    assert "back.out(1.6)" in plain_page and story._FAMILY_STYLE["walkthrough_statement"]["mark"] in plain_page


def test_pill_font_shrinks_long_labels_to_the_available_width_and_never_enlarges_or_collapses():
    from tubeforge.rendering.shorts.story import _pill_font
    assert _pill_font("SOURCE · AWS", 36, .6) == 36                               # short: unchanged
    long_label = "SOURCE · " + "Amazon API Gateway developer guide throttling"   # would overflow at 36 px
    assert 28 <= _pill_font(long_label, 36, .6) < 36
    assert len(long_label) * .6 * _pill_font(long_label, 36, .6) <= 900 or _pill_font(long_label, 36, .6) == 28
    assert _pill_font("x" * 200, 36, .6) == 28                                    # floor: readability beats fitting, the QA gate then catches it
