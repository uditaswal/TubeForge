"""Multi-scene HyperFrames routing and frame-boundary guarantees."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from tubeforge.rendering.shorts import hyperframes_compose as film
from tubeforge.rendering.shorts.timeline import SceneTiming, Word


def _timeline():
    scenes = [SimpleNamespace(template="hook", scene_id="s0"),
              SimpleNamespace(template="flow", scene_id="s1")]
    timings = [SceneTiming(0, 1.047, (Word(.2, .4),), "whisper"),
               SceneTiming(1.047, 2.011, (Word(1.2, 1.5),), "whisper")]
    return SimpleNamespace(topic=SimpleNamespace(scenes=scenes), timings=timings, duration=2.011)


def test_scene_plan_uses_global_edges_and_relative_words():
    assert film.scene_plan(_timeline()) == [
        (0, 31, [(.2, .4)]),
        (31, 60, [(1.2 - 1.047, 1.5 - 1.047)]),
    ]


def test_scene_plan_rejects_unsupported_template():
    timeline = _timeline()
    timeline.topic.scenes[1].template = "unknown"
    with pytest.raises(ValueError, match="s1: unknown"):
        film.scene_plan(timeline)


def test_render_silent_builds_every_scene_and_joins_to_exact_frame_count(tmp_path, monkeypatch):
    built, commands = [], []

    def builder(scene, words, duration, project):
        built.append((scene.template, words, duration))
        project.mkdir()

    monkeypatch.setattr(film, "BUILDERS", {"hook": builder, "flow": builder})
    monkeypatch.setattr(film.cli, "check", lambda *a, **kw: {"ok": True})
    monkeypatch.setattr(film.cli, "render", lambda project, output, **kw: output.write_bytes(b"clip"))

    def checked(command, **kwargs):
        commands.append(command)
        if "-filter_complex" in command:
            Path(command[-1]).write_bytes(b"joined")
        return b""

    monkeypatch.setattr(film, "checked", checked)
    output = tmp_path / "silent.mp4"
    report = film.render_silent(_timeline(), output, draft=True, hyperframes_bin="stub")
    assert [row[0] for row in built] == ["hook", "flow"]
    assert built[1][1][0][0] == pytest.approx(.153)
    assert report["scene_count"] == 2 and report["frames"] == 60
    assert output.read_bytes() == b"joined"
    graph = commands[0][commands[0].index("-filter_complex") + 1]
    assert "trim=end_frame=31" in graph and "trim=end_frame=29" in graph
    assert "concat=n=2:v=1:a=0" in graph
    assert graph.count("fade=t=") == 2
