"""The opt-in renderer cannot change or reuse the default PIL route."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tubeforge.core.config import ReferenceShortConfig
from tubeforge.pipeline import reference_short
from tubeforge.rendering.shorts import hyperframes_compose, hyperframes_encode


def _timeline():
    topic = SimpleNamespace(title="Fixture", scenes=[SimpleNamespace(template="hook", reveal_words=(0,))],
                            model_dump_json=lambda: '{"fixture":true}')
    return SimpleNamespace(topic=topic, timings=[SimpleNamespace(start=0, words=(SimpleNamespace(start=.1),))], duration=30)


def _master(monkeypatch):
    def fake_master(narration, starts, output, **kwargs):
        output.mkdir()
        (output / "audio-provenance.json").write_text(json.dumps({"narration_health": {"ok": True}}))
        (output / "mix.wav").write_bytes(b"audio")
        return output / "mix.wav"
    monkeypatch.setattr(reference_short, "master", fake_master)


def test_default_config_and_pil_render_call_are_unchanged(tmp_path, monkeypatch):
    config = ReferenceShortConfig()
    assert config.renderer == "pil"
    _master(monkeypatch)
    called = []
    monkeypatch.setattr(reference_short, "encode", lambda *args, **kwargs:
                        called.append((args, kwargs)) or {"passed": True})
    monkeypatch.setattr(reference_short, "load_plates", lambda *args: ("plates", ()))
    monkeypatch.setattr(hyperframes_compose, "render_silent", lambda *a, **k:
                        pytest.fail("default PIL route used HyperFrames"))
    result = reference_short.render(_timeline(), tmp_path, tmp_path / "out.mp4", config,
                                    draft=True, cancelled=lambda: False)
    assert result == {"passed": True}
    assert called[0][0][1] == tmp_path / "mix" / "mix.wav"
    assert called[0][1] == {"draft": True, "cancelled": called[0][1]["cancelled"],
                            "budget_rtf": 12.0, "ffmpeg": "ffmpeg", "ffprobe": "ffprobe",
                            "plates": "plates", "narration_health": {"ok": True}}


def test_hyperframes_flag_routes_silent_film_and_same_mix(tmp_path, monkeypatch):
    _master(monkeypatch)
    calls = []
    def fake_silent(timeline, destination, **kwargs):
        calls.append(("silent", destination, kwargs))
        destination.write_bytes(b"silent")
        return {"scene_count": 1, "checks": [{"ok": True}]}
    def fake_mux(timeline, silent, mix, destination, **kwargs):
        calls.append(("mux", silent, mix, kwargs))
        return {"passed": True}
    monkeypatch.setattr(hyperframes_compose, "render_silent", fake_silent)
    monkeypatch.setattr(hyperframes_encode, "encode", fake_mux)
    config = ReferenceShortConfig(renderer="hyperframes")
    result = reference_short.render(_timeline(), tmp_path, tmp_path / "out.mp4", config,
                                    draft=True, cancelled=lambda: False)
    assert result == {"passed": True}
    assert [row[0] for row in calls] == ["silent", "mux"]
    assert calls[1][2] == tmp_path / "mix" / "mix.wav"
    assert calls[1][3]["scene_report"]["scene_count"] == 1
    assert not calls[0][1].exists()  # stage-local scratch is removed


def test_renderer_identity_changes_only_for_opt_in():
    topic = _timeline().topic
    base = reference_short.render_identity(topic, "n", "t", draft=True, approval_identity=None)
    assert base == "6b834b3eda9574d159c24b0d54ee641af957dcda28c7a36fe0cff759bf4fe591"
    assert base == reference_short.render_identity(topic, "n", "t", draft=True,
                                                   approval_identity=None, renderer="pil")
    assert base != reference_short.render_identity(topic, "n", "t", draft=True,
                                                   approval_identity=None, renderer="hyperframes")
    with pytest.raises(ValueError):
        ReferenceShortConfig(renderer="unknown")


def test_story_style_routes_code_report_to_final_qa(tmp_path,monkeypatch):
    from tubeforge.rendering.shorts import story
    _master(monkeypatch)
    reference_short.write_options(tmp_path,show_sources=False,watermark=None,style='story')
    report={'checks':[{'ok':True}],'code_animation':[{'mode':'word_anchored','version':'story-code-v1'}]}
    def silent(timeline,destination,**kwargs):
        destination.write_bytes(b'silent')
        return report
    captured=[]
    monkeypatch.setattr(story,'render_silent',silent)
    monkeypatch.setattr(hyperframes_encode,'encode',lambda *args,**kwargs:captured.append(kwargs) or {'passed':True})
    result=reference_short.render(_timeline(),tmp_path,tmp_path/'out.mp4',ReferenceShortConfig(),
        draft=True,cancelled=lambda:False)
    assert result['passed']
    assert captured[0]['scene_report']['code_animation'] == report['code_animation']
